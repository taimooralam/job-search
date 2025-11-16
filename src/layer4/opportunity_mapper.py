"""
Layer 4: Opportunity Mapper

Maps candidate profile to job requirements and generates fit score + rationale.
This is the SIMPLIFIED version for today's vertical slice.

FUTURE: Will expand to include hiring reasoning, timing significance, company signals analysis.
"""

import re
from typing import Dict, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState


# ===== PROMPT DESIGN =====

SYSTEM_PROMPT = """You are an expert career consultant and recruiter specializing in candidate-job fit analysis.

Your task: Analyze how well a candidate matches a job opportunity based on:
1. Job requirements and pain points
2. Company context
3. Candidate's profile (experience, skills, achievements)

You must provide:
1. A fit score (0-100) where:
   - 90-100: Exceptional fit, rare alignment
   - 80-89: Strong fit, highly qualified
   - 70-79: Good fit, meets most requirements
   - 60-69: Moderate fit, some gaps
   - 50-59: Weak fit, significant gaps
   - <50: Poor fit, major misalignment

2. A brief rationale (2-3 sentences) explaining the score, highlighting key strengths or gaps.

Be objective and evidence-based. Consider both hard skills and strategic alignment.
"""

USER_PROMPT_TEMPLATE = """Analyze the candidate's fit for this job opportunity:

=== JOB DETAILS ===
Title: {title}
Company: {company}

Company Summary:
{company_summary}

Job Description:
{job_description}

=== PAIN POINTS (What the company needs) ===
{pain_points}

=== CANDIDATE PROFILE ===
{candidate_profile}

=== YOUR ANALYSIS ===
Based on the above, provide:

1. Fit Score (0-100): [number only]
2. Rationale (2-3 sentences): [explanation]

Format your response EXACTLY as:
SCORE: [number]
RATIONALE: [your 2-3 sentence explanation]
"""


class OpportunityMapper:
    """
    Analyzes candidate-job fit and generates scoring.
    """

    def __init__(self):
        """Initialize LLM for fit analysis."""
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for objective analysis
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )

    def _format_pain_points(self, pain_points: list) -> str:
        """Format pain points list as numbered bullets."""
        if not pain_points:
            return "No pain points identified."
        return "\n".join(f"{i}. {point}" for i, point in enumerate(pain_points, 1))

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _analyze_fit(self, state: JobState) -> Tuple[int, str]:
        """
        Use LLM to analyze candidate-job fit.

        Returns:
            Tuple of (fit_score, fit_rationale)
        """
        # Format pain points
        pain_points_text = self._format_pain_points(state.get("pain_points", []))

        # Build prompt
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=USER_PROMPT_TEMPLATE.format(
                    title=state["title"],
                    company=state["company"],
                    company_summary=state.get("company_summary", "No company information available."),
                    job_description=state["job_description"],
                    pain_points=pain_points_text,
                    candidate_profile=state.get("candidate_profile", "No candidate profile provided.")
                )
            )
        ]

        # Get LLM response
        response = self.llm.invoke(messages)
        response_text = response.content.strip()

        # Parse response
        score, rationale = self._parse_llm_response(response_text)

        return score, rationale

    def map_opportunity(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to analyze candidate-job fit.

        Args:
            state: Current JobState with job details, pain points, company info, candidate profile

        Returns:
            Dict with fit_score and fit_rationale keys
        """
        try:
            print(f"   Analyzing fit for: {state['title']} at {state['company']}")

            score, rationale = self._analyze_fit(state)

            print(f"   ✓ Generated fit score: {score}/100")
            print(f"   ✓ Generated rationale ({len(rationale)} chars)")

            return {
                "fit_score": score,
                "fit_rationale": rationale
            }

        except Exception as e:
            # Complete failure - log error and return default
            error_msg = f"Layer 4 (Opportunity Mapper) failed: {str(e)}"
            print(f"   ✗ {error_msg}")

            return {
                "fit_score": None,
                "fit_rationale": None,
                "errors": state.get("errors", []) + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def opportunity_mapper_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 4: Opportunity Mapper.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    print("\n" + "="*60)
    print("LAYER 4: Opportunity Mapper")
    print("="*60)

    mapper = OpportunityMapper()
    updates = mapper.map_opportunity(state)

    # Print results
    if updates.get("fit_score") is not None:
        print(f"\nFit Score: {updates['fit_score']}/100")
        print(f"\nFit Rationale:")
        print(f"  {updates['fit_rationale']}")
    else:
        print("\n⚠️  No fit analysis generated")

    print("="*60 + "\n")

    return updates
