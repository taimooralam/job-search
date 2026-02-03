"""
Answer Generator Service

Generates planned answers for job application forms using LLM.
Uses job context (JD, annotations, extractions, pain points, master CV)
to generate personalized answers for application questions.

Usage:
    service = AnswerGeneratorService()

    # With form fields from scraper (preferred)
    answers = service.generate_answers(job, form_fields=scraped_fields)

    # Without form fields (raises error - form scraping required)
    answers = service.generate_answers(job)  # ValueError
"""

import logging
from typing import Any, Dict, List, Optional

from src.common.config import Config
from src.common.unified_llm import invoke_unified_sync
from src.common.database import db as database_client
from src.common.types import FormField

logger = logging.getLogger(__name__)


class AnswerGeneratorService:
    """Generate planned answers for job application forms."""

    def __init__(self):
        pass  # No initialization needed - using invoke_unified_sync directly

    def _load_star_records(self) -> List[Dict[str, Any]]:
        """
        Load STAR records from MongoDB.

        Returns:
            List of STAR record dicts
        """
        try:
            return database_client.get_all_star_records()
        except Exception as e:
            logger.warning(f"Failed to load STAR records from MongoDB: {e}")
            return []

    def generate_answers(
        self,
        job: Dict[str, Any],
        form_fields: Optional[List[FormField]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate planned answers for a job based on form fields.

        Args:
            job: Job document from MongoDB with all available context
            form_fields: List of FormField objects from the scraped application form.
                         If not provided, raises ValueError.

        Returns:
            List of PlannedAnswer dicts with question, answer, field_type, required, source

        Raises:
            ValueError: If form_fields is None (form scraping required)
        """
        if form_fields is None:
            raise ValueError(
                "form_fields is required. Use FormScraperService to scrape "
                "the application form first, then pass the fields here."
            )

        if not form_fields:
            logger.warning("Empty form_fields provided, returning empty answers")
            return []

        # Extract context from job
        company = job.get("company", "the company")
        title = job.get("title", "this role")
        location = job.get("location", "")
        job_description = job.get("job_description", "") or job.get("description", "")

        # Pipeline-generated context
        pain_points = job.get("pain_points", [])
        strategic_needs = job.get("strategic_needs", [])
        extracted_jd = job.get("extracted_jd", {})
        company_research = job.get("company_research", {})
        fit_rationale = job.get("fit_rationale", "")

        # Load STAR records for achievement context
        all_stars = self._load_star_records()
        selected_star_ids = job.get("selected_star_ids", [])
        relevant_stars = [s for s in all_stars if s.get("id") in selected_star_ids]

        # If no selected stars, use top 3 by default
        if not relevant_stars and all_stars:
            relevant_stars = all_stars[:3]

        planned_answers = []

        for field in form_fields:
            question = field.get("label", "")
            field_type = field.get("field_type", "text")
            required = field.get("required", False)
            char_limit = field.get("limit")
            options = field.get("options")

            if not question:
                continue

            # Generate answer based on field type
            if field_type in ["url", "file"]:
                # Don't generate LLM answers for URL or file upload fields
                answer = self._get_static_answer(question, job)
            elif field_type in ["select", "radio", "checkbox"] and options:
                # For select/radio/checkbox with options, pick the best option
                answer = self._select_best_option(question, options, job)
            else:
                # Generate LLM answer for text/textarea fields
                answer = self._generate_llm_answer(
                    question=question,
                    company=company,
                    title=title,
                    location=location,
                    job_description=job_description,
                    pain_points=pain_points,
                    strategic_needs=strategic_needs,
                    extracted_jd=extracted_jd,
                    company_research=company_research,
                    fit_rationale=fit_rationale,
                    relevant_stars=relevant_stars,
                    char_limit=char_limit,
                )

            if answer:
                planned_answers.append({
                    "question": question,
                    "answer": answer,
                    "field_type": field_type,
                    "required": required,
                    "max_length": char_limit,
                    "source": "auto_generated"
                })

        return planned_answers

    def _select_best_option(
        self,
        question: str,
        options: List[str],
        job: Dict[str, Any],
    ) -> Optional[str]:
        """
        Select the best option for a select/radio/checkbox field.

        Uses simple heuristics for common questions, falls back to LLM for complex ones.

        Args:
            question: The question text
            options: List of available options
            job: Job document for context

        Returns:
            The selected option or None
        """
        question_lower = question.lower()

        # Work authorization questions
        if any(kw in question_lower for kw in ["authorized", "authorization", "eligibility", "work in"]):
            # Prefer "Yes" or affirmative options
            for opt in options:
                if opt.lower() in ["yes", "yes, i am authorized", "authorized"]:
                    return opt
            # If no clear "yes", return first option (user will need to verify)
            return options[0] if options else None

        # Sponsorship questions
        if any(kw in question_lower for kw in ["sponsorship", "visa"]):
            # Look for "no sponsorship required" type options
            for opt in options:
                opt_lower = opt.lower()
                if "no" in opt_lower and "sponsorship" in opt_lower:
                    return opt
                if opt_lower in ["no", "not required"]:
                    return opt
            return options[0] if options else None

        # Gender/diversity questions - skip (personal choice)
        if any(kw in question_lower for kw in ["gender", "race", "ethnicity", "veteran", "disability"]):
            # Look for "prefer not to say" or similar
            for opt in options:
                if any(phrase in opt.lower() for phrase in ["prefer not", "decline", "not to say"]):
                    return opt
            return None  # Let user choose

        # For other questions, use LLM to select
        try:
            prompt = f"""Select the most appropriate option for this job application question.

Question: {question}
Options: {', '.join(options)}

Job: {job.get('title', '')} at {job.get('company', '')}

Return ONLY the exact text of the best option, nothing else."""

            result = invoke_unified_sync(
                prompt=prompt,
                step_name="answer_generation",
                validate_json=False,
            )

            if not result.success:
                logger.warning(f"LLM option selection failed: {result.error}")
                return options[0] if options else None

            selected = result.content.strip()

            # Verify the response is one of the options
            for opt in options:
                if selected.lower() == opt.lower() or selected in opt:
                    return opt

            return options[0] if options else None
        except Exception as e:
            logger.warning(f"Failed to select option with LLM: {e}")
            return options[0] if options else None

    def _get_static_answer(self, question: str, job: Dict[str, Any]) -> Optional[str]:
        """Get static/placeholder answers for non-LLM fields."""
        question_lower = question.lower()

        if "linkedin" in question_lower:
            return "[Your LinkedIn URL]"
        elif "portfolio" in question_lower or "website" in question_lower:
            return "[Your Portfolio/Website URL]"
        elif "authorized" in question_lower:
            return "Yes"
        elif "salary" in question_lower:
            return "[Your expected salary range]"
        elif "availability" in question_lower or "notice" in question_lower:
            return "[Your availability/notice period]"

        return None

    def _generate_llm_answer(
        self,
        question: str,
        company: str,
        title: str,
        location: str,
        job_description: str,
        pain_points: List[str],
        strategic_needs: List[str],
        extracted_jd: Dict[str, Any],
        company_research: Dict[str, Any],
        fit_rationale: str,
        relevant_stars: List[Dict[str, Any]],
        char_limit: Optional[int] = None,
    ) -> str:
        """
        Generate a single answer using LLM.

        Args:
            question: The question to answer
            company: Company name
            title: Job title
            location: Job location
            job_description: Full job description
            pain_points: List of extracted pain points
            strategic_needs: List of strategic needs
            extracted_jd: Extracted JD structure
            company_research: Company research data
            fit_rationale: Why candidate is a good fit
            relevant_stars: Relevant STAR records
            char_limit: Optional character limit for the answer

        Returns:
            Generated answer string
        """
        # Build context for LLM
        context_parts = []

        context_parts.append(f"Company: {company}")
        context_parts.append(f"Role: {title}")
        if location:
            context_parts.append(f"Location: {location}")

        if job_description:
            # Truncate JD to avoid token overflow
            jd_truncated = (
                job_description[:2000] + "..."
                if len(job_description) > 2000
                else job_description
            )
            context_parts.append(f"\nJob Description:\n{jd_truncated}")

        if pain_points:
            context_parts.append(
                f"\nKey Business Pain Points:\n- " + "\n- ".join(pain_points[:5])
            )

        if strategic_needs:
            context_parts.append(
                f"\nStrategic Needs:\n- " + "\n- ".join(strategic_needs[:3])
            )

        if extracted_jd:
            if extracted_jd.get("top_keywords"):
                context_parts.append(
                    f"\nKey Skills Required: {', '.join(extracted_jd['top_keywords'][:10])}"
                )
            if extracted_jd.get("role_category"):
                context_parts.append(f"Role Category: {extracted_jd['role_category']}")

        if company_research:
            # Handle both dict and object access patterns
            summary = (
                company_research.get("summary")
                or company_research.get("company_summary")
                or ""
            )
            if summary:
                context_parts.append(f"\nCompany Context: {summary[:500]}")

        if fit_rationale:
            context_parts.append(f"\nWhy I'm a Good Fit: {fit_rationale}")

        if relevant_stars:
            stars_text = []
            for star in relevant_stars[:3]:
                star_summary = (
                    f"- {star.get('role_title', 'Achievement')}: "
                    f"{star.get('condensed_version', star.get('impact_summary', ''))[:150]}"
                )
                stars_text.append(star_summary)
            if stars_text:
                context_parts.append(f"\nRelevant Achievements:\n" + "\n".join(stars_text))

        context = "\n".join(context_parts)

        # Determine length guidance based on char_limit
        if char_limit:
            if char_limit <= 150:
                length_guidance = f"Keep your answer under {char_limit} characters (approximately {char_limit // 5} words). Be concise."
            elif char_limit <= 500:
                length_guidance = f"Keep your answer under {char_limit} characters (approximately {char_limit // 5} words). Be thorough but concise."
            else:
                length_guidance = f"Your answer can be up to {char_limit} characters. Provide a detailed, compelling response."
        else:
            length_guidance = "Keep the answer concise but compelling (150-300 words for textarea fields)."

        prompt = f"""You are helping a job candidate prepare answers for a job application form.

CONTEXT:
{context}

QUESTION TO ANSWER:
{question}

INSTRUCTIONS:
1. Write a professional, personalized answer that demonstrates fit for this specific role
2. Reference specific details from the job description and company context
3. Include relevant achievements or experiences where appropriate
4. {length_guidance}
5. Write in first person as the candidate
6. Be specific and avoid generic phrases
7. Do NOT include any preamble like "Here's an answer..." - just write the answer directly

ANSWER:"""

        try:
            result = invoke_unified_sync(
                prompt=prompt,
                step_name="answer_generation",
                validate_json=False,
            )

            if not result.success:
                logger.error(f"Answer generation failed: {result.error}")
                return f"[Please provide your answer for: {question}]"

            answer = result.content.strip()

            # Truncate if over limit (with buffer for LLM variability)
            if char_limit and len(answer) > char_limit:
                # Find a good break point near the limit
                truncate_at = char_limit - 3  # Leave room for "..."
                # Try to break at sentence or word boundary
                last_period = answer.rfind(".", 0, truncate_at)
                last_space = answer.rfind(" ", 0, truncate_at)

                if last_period > truncate_at * 0.8:
                    answer = answer[: last_period + 1]
                elif last_space > truncate_at * 0.8:
                    answer = answer[:last_space] + "..."
                else:
                    answer = answer[:truncate_at] + "..."

            return answer
        except Exception as e:
            logger.error(f"Failed to generate answer for '{question}': {e}")
            return f"[Please provide your answer for: {question}]"
