"""
Layer 2: Pain-Point Miner

Extracts 3-5 key business challenges/pain points from job descriptions using LLM.
This is the SIMPLIFIED version for today's vertical slice.

FUTURE: Will expand to extract strategic_needs, risks_if_unfilled, success_metrics.
"""

import re
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState


# ===== PROMPT DESIGN =====

SYSTEM_PROMPT = """You are an expert recruiter and business analyst specializing in understanding hiring needs.

Your task: Analyze job descriptions to identify the KEY BUSINESS CHALLENGES or PAIN POINTS the company is trying to solve by filling this role.

Focus on:
- Technical/operational problems they need solved
- Business challenges driving this hire
- What the company is struggling with that this person will fix

Do NOT just list job requirements. Extract the UNDERLYING PROBLEMS.
"""

USER_PROMPT_TEMPLATE = """Analyze this job posting and extract 3-5 key pain points or business challenges the company is trying to solve:

JOB TITLE: {title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description}

Return EXACTLY 3-5 pain points as a bulleted list. Each bullet should be:
- Concise (one line)
- Problem-focused (what challenge they face)
- Actionable (what needs to be addressed)

Format as:
- Pain point 1
- Pain point 2
- Pain point 3
...
"""


class PainPointMiner:
    """
    Extracts pain points from job descriptions using LLM analysis.
    """

    def __init__(self):
        """Initialize LLM client with proper configuration."""
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for focused extraction
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),  # None for OpenAI, set for OpenRouter
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_llm(self, title: str, company: str, job_description: str) -> str:
        """
        Call LLM to extract pain points.
        Retries up to 3 times with exponential backoff on failures.
        """
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=USER_PROMPT_TEMPLATE.format(
                    title=title,
                    company=company,
                    job_description=job_description
                )
            )
        ]

        response = self.llm.invoke(messages)
        return response.content

    def _parse_pain_points(self, llm_response: str) -> List[str]:
        """
        Parse LLM response into a clean list of pain points.

        Handles various bullet formats:
        - "- Pain point"
        - "* Pain point"
        - "1. Pain point"
        - "• Pain point"
        """
        # Split by newlines
        lines = llm_response.strip().split('\n')

        pain_points = []
        for line in lines:
            # Remove leading/trailing whitespace
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Remove common bullet markers
            # Matches: "- ", "* ", "• ", "1. ", "2. ", etc.
            cleaned = re.sub(r'^[\-\*•]\s*', '', line)  # Remove -, *, •
            cleaned = re.sub(r'^\d+\.\s*', '', cleaned)  # Remove 1., 2., etc.

            # Skip if line is too short (likely not a real pain point)
            if len(cleaned) < 10:
                continue

            pain_points.append(cleaned)

        return pain_points

    def extract_pain_points(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to extract pain points from job description.

        Args:
            state: Current JobState with job_description, title, company

        Returns:
            Dict with pain_points key containing list of strings
        """
        try:
            # Call LLM
            llm_response = self._call_llm(
                title=state["title"],
                company=state["company"],
                job_description=state["job_description"]
            )

            # Parse response
            pain_points = self._parse_pain_points(llm_response)

            # Validate we got a reasonable number (3-7 is acceptable)
            if len(pain_points) < 2:
                print(f"⚠️  Warning: Only extracted {len(pain_points)} pain points (expected 3-5)")
            elif len(pain_points) > 7:
                print(f"⚠️  Warning: Extracted {len(pain_points)} pain points (expected 3-5), truncating to 5")
                pain_points = pain_points[:5]

            print(f"✓ Extracted {len(pain_points)} pain points")

            return {"pain_points": pain_points}

        except Exception as e:
            # Log error and return empty list (don't block pipeline)
            error_msg = f"Layer 2 (Pain-Point Miner) failed: {str(e)}"
            print(f"✗ {error_msg}")

            return {
                "pain_points": [],
                "errors": state.get("errors", []) + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def pain_point_miner_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 2: Pain-Point Miner.

    This is the function that will be called by the LangGraph workflow.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    print("\n" + "="*60)
    print("LAYER 2: Pain-Point Miner")
    print("="*60)
    print(f"Job: {state['title']} at {state['company']}")
    print(f"Description length: {len(state['job_description'])} chars")

    miner = PainPointMiner()
    updates = miner.extract_pain_points(state)

    # Print results
    if updates.get("pain_points"):
        print("\nExtracted Pain Points:")
        for i, point in enumerate(updates["pain_points"], 1):
            print(f"  {i}. {point}")
    else:
        print("\n⚠️  No pain points extracted")

    print("="*60 + "\n")

    return updates
