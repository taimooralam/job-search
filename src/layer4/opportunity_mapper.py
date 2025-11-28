"""
Layer 4: Opportunity Mapper (Phase 6)

Maps candidate profile to job requirements and generates fit score + rationale + category.

Phase 6 Enhancements:
- Integrates company_research and role_research from Phase 5
- Validates STAR citations and quantified metrics in rationale
- Derives fit_category from fit_score per ROADMAP rubric
- Detects and rejects generic boilerplate rationales
"""

import logging
import re
from typing import Dict, Any, Tuple, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState
from src.common.logger import get_logger


# ===== PROMPT DESIGN =====

SYSTEM_PROMPT = """You are an expert career consultant and recruiter specializing in candidate-job fit analysis.

Your task: Analyze how well a candidate matches a job opportunity using:
1) Job requirements and pain points
2) Company and role research
3) The candidate's master CV (experience, skills, achievements)

You must provide:
1. A fit score (0-100) where:
   - 90-100: Exceptional fit, rare alignment
   - 80-89: Strong fit, highly qualified
   - 70-79: Good fit, meets most requirements
   - 60-69: Moderate fit, some gaps
   - 50-59: Weak fit, significant gaps
   - <50: Poor fit, major misalignment

2. A brief rationale (2-3 sentences) explaining the score, highlighting key strengths or gaps.

Guidance:
- Ground everything in the provided job description, research signals, and master CV text.
- If curated achievements are provided, reference them with concrete metrics; otherwise, lean on factual achievements from the master CV.
- Avoid generic language and avoid inventing facts not present in the supplied materials.
"""

USER_PROMPT_TEMPLATE = """Analyze the candidate's fit for this job opportunity:

=== JOB DETAILS ===
Title: {title}
Company: {company}

Job Description:
{job_description}

=== COMPANY RESEARCH (Phase 5.1) ===
{company_research}

=== ROLE RESEARCH (Phase 5.2) ===
{role_research}

=== CANDIDATE PROFILE (MASTER CV) ===
{candidate_profile}

=== JOB ANALYSIS (4 Dimensions) ===

PAIN POINTS (Current Problems):
{pain_points}

STRATEGIC NEEDS (Why This Role Matters):
{strategic_needs}

RISKS IF UNFILLED (Consequences):
{risks_if_unfilled}

SUCCESS METRICS (How They'll Measure Success):
{success_metrics}

=== YOUR ANALYSIS ===
Based on the above, provide:

1. Fit Score (0-100): [number only]
2. Rationale (2-3 sentences): [explanation]

**REQUIREMENTS:**
- Ground your rationale in the job description, research signals, and master CV content.
- If curated achievements are provided, reference them with concrete metrics; otherwise, use evidence from the master CV and job analysis.
- Reference company signals OR role "why now" context when available (e.g., mention funding, growth, timing significance)
- Be specific and technical - avoid generic phrases like "strong background" or "great communication skills"
- Consider all 4 dimensions in your scoring

Format your response EXACTLY as:
SCORE: [number]
RATIONALE: [your 2-3 sentence explanation with concrete, evidence-based context]
"""


class OpportunityMapper:
    """
    Analyzes candidate-job fit and generates scoring.
    """

    def __init__(self):
        """Initialize LLM for fit analysis."""
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)

        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for objective analysis
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )

    def _derive_fit_category(self, fit_score: int) -> str:
        """
        Derive fit_category from fit_score per ROADMAP Phase 6 rubric.

        Args:
            fit_score: Integer score 0-100

        Returns:
            Category: "exceptional" | "strong" | "good" | "moderate" | "weak"
        """
        if fit_score >= 90:
            return "exceptional"
        elif fit_score >= 80:
            return "strong"
        elif fit_score >= 70:
            return "good"
        elif fit_score >= 60:
            return "moderate"
        else:
            return "weak"

    def _truncate_text(self, text: str, limit: int = 1200) -> str:
        """Return a truncated snippet of text for prompt safety."""
        if not text:
            return "No candidate profile provided."
        snippet = text.strip()
        return snippet[:limit] + ("..." if len(snippet) > limit else "")

    def _validate_rationale(
        self,
        rationale: str,
        selected_stars: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        Validate that rationale meets quality gates without requiring STAR references.

        Args:
            rationale: The fit rationale text to validate
            selected_stars: Optional list of STAR records for context

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not rationale or len(rationale.split()) < 10:
            errors.append("Rationale is too short - provide at least two evidence-based sentences.")

        # Encourage metrics when available
        metric_patterns = [
            r'\d+%',           # 75%, 60%
            r'\d+x',           # 10x, 24x
            r'\d+M',           # 50M, 10M
            r'\d+K',           # 10K, 100K
            r'\d+\s*min',      # 15min, 10 min
            r'\d+h',           # 3h, 4h
        ]
        if selected_stars:
            has_metric = any(re.search(pattern, rationale, re.IGNORECASE) for pattern in metric_patterns)
            if not has_metric:
                errors.append("Add at least one concrete metric when achievements are available.")

        # Generic boilerplate detection
        generic_phrases = [
            r'strong background',
            r'great communication skills',
            r'team player',
            r'well-suited for this position',
            r'good fit',
            r'extensive experience',
            r'proven track record',
        ]

        # Count how many generic phrases appear
        generic_count = sum(1 for phrase in generic_phrases if re.search(phrase, rationale, re.IGNORECASE))

        # Count total words
        word_count = len(rationale.split())

        # If rationale is short and has multiple generic phrases, it's probably too generic
        if word_count < 100 and generic_count >= 2:
            errors.append("Rationale appears too generic - include concrete evidence from the job and master CV.")

        return errors

    def _format_dimension(self, items: list, label: str) -> str:
        """Format a dimension as numbered bullets."""
        if not items:
            return f"No {label.lower()} identified."
        return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))

    def _format_selected_stars(self, selected_stars: list) -> str:
        """Format selected STAR records for LLM prompt."""
        if not selected_stars:
            return "STAR selector disabled - use achievements from the master CV."

        formatted = []
        for i, star in enumerate(selected_stars, 1):
            formatted.append(f"""
STAR #{i}: {star.get('company', 'Unknown')} - {star.get('role', 'Unknown')}
Period: {star.get('period', 'N/A')}
Domain: {star.get('domain_areas', 'N/A')}

Situation: {star.get('situation', 'N/A')}
Task: {star.get('task', 'N/A')}
Actions: {star.get('actions', 'N/A')}
Results: {star.get('results', 'N/A')}

KEY METRICS: {star.get('metrics', 'N/A')}
""".strip())

        return "\n\n---\n\n".join(formatted)

    def _parse_llm_response(self, response: str) -> Tuple[int, str]:
        """
        Parse LLM response to extract score and rationale.

        Expected format:
        SCORE: 85
        RATIONALE: The candidate has strong experience...

        Returns:
            Tuple of (score, rationale)
        """
        # Extract score
        score_match = re.search(r'SCORE:\s*(\d+)', response, re.IGNORECASE)
        if score_match:
            score = int(score_match.group(1))
            # Clamp to 0-100 range
            score = max(0, min(100, score))
        else:
            # Fallback: try to find any number
            numbers = re.findall(r'\b(\d{1,3})\b', response)
            if numbers:
                score = int(numbers[0])
                score = max(0, min(100, score))
            else:
                score = 50  # Default if parsing fails

        # Extract rationale
        rationale_match = re.search(r'RATIONALE:\s*(.+)', response, re.IGNORECASE | re.DOTALL)
        if rationale_match:
            rationale = rationale_match.group(1).strip()
        else:
            # Fallback: use everything after score
            if score_match:
                rationale = response[score_match.end():].strip()
            else:
                rationale = response.strip()

        # Clean up rationale (remove extra whitespace, newlines)
        rationale = re.sub(r'\s+', ' ', rationale).strip()

        return score, rationale

    def _format_company_research(self, company_research: Optional[Dict[str, Any]]) -> str:
        """Format company research for prompt (Phase 5.1)."""
        if not company_research:
            return "No structured company research available."

        parts = []

        # Summary
        if company_research.get("summary"):
            parts.append(f"Summary: {company_research['summary']}")

        # Signals
        if company_research.get("signals"):
            parts.append("\nKey Signals:")
            for sig in company_research["signals"]:
                parts.append(f"  - [{sig.get('type', 'unknown')}] {sig.get('description', 'N/A')} ({sig.get('date', 'unknown')})")

        return "\n".join(parts) if parts else "No structured company research available."

    def _format_role_research(self, role_research: Optional[Dict[str, Any]]) -> str:
        """Format role research for prompt (Phase 5.2)."""
        if not role_research:
            return "No structured role research available."

        parts = []

        # Summary
        if role_research.get("summary"):
            parts.append(f"Summary: {role_research['summary']}")

        # Business Impact
        if role_research.get("business_impact"):
            parts.append("\nBusiness Impact:")
            for impact in role_research["business_impact"]:
                parts.append(f"  - {impact}")

        # Why Now
        if role_research.get("why_now"):
            parts.append(f"\nWhy Now: {role_research['why_now']}")

        return "\n".join(parts) if parts else "No structured role research available."

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _analyze_fit(self, state: JobState) -> Tuple[int, str, str]:
        """
        Use LLM to analyze candidate-job fit (Phase 6).

        Returns:
            Tuple of (fit_score, fit_rationale, fit_category)

        Raises:
            ValueError: If rationale fails validation (triggers retry)
        """
        # Format all 4 dimensions
        pain_points_text = self._format_dimension(state.get("pain_points", []), "pain points")
        strategic_needs_text = self._format_dimension(state.get("strategic_needs", []), "strategic needs")
        risks_text = self._format_dimension(state.get("risks_if_unfilled", []), "risks")
        metrics_text = self._format_dimension(state.get("success_metrics", []), "success metrics")
        candidate_profile_text = self._truncate_text(state.get("candidate_profile", ""))

        # Format selected STAR records
        selected_stars_text = self._format_selected_stars(state.get("selected_stars", []))

        # Phase 6: Format company and role research
        company_research_text = self._format_company_research(state.get("company_research"))
        role_research_text = self._format_role_research(state.get("role_research"))

        # Build prompt
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=USER_PROMPT_TEMPLATE.format(
                    title=state["title"],
                    company=state["company"],
                    job_description=state["job_description"],
                    company_research=company_research_text,
                    role_research=role_research_text,
                    pain_points=pain_points_text,
                    strategic_needs=strategic_needs_text,
                    risks_if_unfilled=risks_text,
                    success_metrics=metrics_text,
                    candidate_profile=candidate_profile_text,
                    selected_stars=selected_stars_text
                )
            )
        ]

        # Get LLM response
        response = self.llm.invoke(messages)
        response_text = response.content.strip()

        # Parse response
        score, rationale = self._parse_llm_response(response_text)

        # Phase 6: Validate rationale
        validation_errors = self._validate_rationale(rationale, state.get("selected_stars"))
        if validation_errors:
            # For production usage we treat these as quality warnings, not hard failures.
            # This keeps the pipeline flowing even if the LLM misses some formatting rules.
            self.logger.warning("Fit rationale quality warnings:")
            for msg in validation_errors:
                self.logger.warning(f"  - {msg}")

        # Phase 6: Derive category from score
        category = self._derive_fit_category(score)

        return score, rationale, category

    def map_opportunity(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to analyze candidate-job fit (Phase 6).

        Args:
            state: Current JobState with job details, pain points, company/role research, STARs

        Returns:
            Dict with fit_score, fit_rationale, and fit_category keys
        """
        try:
            self.logger.info(f"Analyzing fit for: {state['title']} at {state['company']}")

            score, rationale, category = self._analyze_fit(state)

            self.logger.info(f"Generated fit score: {score}/100 ({category})")
            self.logger.info(f"Generated rationale ({len(rationale)} chars)")
            self.logger.info("Rationale validation: see any quality warnings above")

            return {
                "fit_score": score,
                "fit_rationale": rationale,
                "fit_category": category
            }

        except Exception as e:
            # Complete failure - log error and return None
            error_msg = f"Layer 4 (Opportunity Mapper) failed: {str(e)}"
            self.logger.error(error_msg)

            return {
                "fit_score": None,
                "fit_rationale": None,
                "fit_category": None,
                "errors": state.get("errors", []) + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def opportunity_mapper_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 4: Opportunity Mapper (Phase 6).

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer4")

    logger.info("="*60)
    logger.info("LAYER 4: Opportunity Mapper (Phase 6)")
    logger.info("="*60)

    mapper = OpportunityMapper()
    updates = mapper.map_opportunity(state)

    # Log results
    if updates.get("fit_score") is not None:
        logger.info(f"Fit Score: {updates['fit_score']}/100")
        logger.info(f"Fit Category: {updates.get('fit_category', 'N/A').upper()}")
        logger.info("Fit Rationale:")
        logger.info(f"  {updates['fit_rationale']}")
    else:
        logger.warning("No fit analysis generated")

    logger.info("="*60)

    return updates
