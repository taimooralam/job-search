"""
Answer Generator Service

Generates planned answers for job application forms using LLM.
Uses job context (JD, annotations, extractions, pain points, master CV)
to generate personalized answers for common application questions.
"""

import logging
from typing import Any, Dict, List, Optional

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.database import db as database_client

logger = logging.getLogger(__name__)


class AnswerGeneratorService:
    """Generate planned answers for job application forms."""

    # Common application questions that don't require form scraping
    COMMON_QUESTIONS = [
        ("Why are you interested in this role?", "textarea"),
        ("Why do you want to work at this company?", "textarea"),
        ("What relevant experience do you have for this position?", "textarea"),
        ("What are your key strengths that make you a good fit?", "textarea"),
        ("Describe a challenging project you've worked on.", "textarea"),
        ("What is your expected salary range?", "text"),
        ("Are you authorized to work in this location?", "select"),
        ("What is your availability/notice period?", "text"),
        ("LinkedIn profile URL", "url"),
        ("Portfolio/Website URL", "url"),
    ]

    def __init__(self):
        self.llm = None  # Lazy initialization

    def _get_llm(self):
        """Lazy initialize LLM to avoid import issues."""
        if self.llm is None:
            self.llm = create_tracked_llm(
                model=Config.DEFAULT_MODEL,
                temperature=0.3,
                layer="answer_generator"
            )
        return self.llm

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

    def generate_answers(self, job: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate planned answers for a job.

        Args:
            job: Job document from MongoDB with all available context

        Returns:
            List of PlannedAnswer dicts with question, answer, field_type, source
        """
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

        for question_template, field_type in self.COMMON_QUESTIONS:
            # Customize question with company/role info
            question = question_template

            # Generate answer based on question type
            if field_type in ["url", "select"]:
                # Don't generate LLM answers for URL or select fields
                answer = self._get_static_answer(question, job)
            else:
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
                    relevant_stars=relevant_stars
                )

            if answer:
                planned_answers.append({
                    "question": question,
                    "answer": answer,
                    "field_type": field_type,
                    "source": "auto_generated"
                })

        return planned_answers

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
        relevant_stars: List[Dict[str, Any]]
    ) -> str:
        """Generate a single answer using LLM."""

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
            if company_research.get("company_summary"):
                context_parts.append(
                    f"\nCompany Context: {company_research['company_summary'][:500]}"
                )

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

        prompt = f"""You are helping a job candidate prepare answers for a job application form.

CONTEXT:
{context}

QUESTION TO ANSWER:
{question}

INSTRUCTIONS:
1. Write a professional, personalized answer that demonstrates fit for this specific role
2. Reference specific details from the job description and company context
3. Include relevant achievements or experiences where appropriate
4. Keep the answer concise but compelling (150-300 words for textarea fields)
5. Write in first person as the candidate
6. Be specific and avoid generic phrases
7. Do NOT include any preamble like "Here's an answer..." - just write the answer directly

ANSWER:"""

        try:
            llm = self._get_llm()
            response = llm.invoke(prompt)
            answer = response.content.strip()
            return answer
        except Exception as e:
            logger.error(f"Failed to generate answer for '{question}': {e}")
            return f"[Please provide your answer for: {question}]"
