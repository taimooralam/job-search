"""
Layer 2: Pain-Point Miner (JSON Mode)

Extracts structured pain-point analysis from job descriptions using LLM.
Returns JSON with 4 arrays: pain_points, strategic_needs, risks_if_unfilled, success_metrics.

Phase 1.3 Update: Full JSON output per requirements.md and feedback.md
Phase 4 Update: Added formal JSON schema validation with Pydantic
"""

import json
import re
from typing import List, Dict, Any
from pydantic import BaseModel, Field, ValidationError, field_validator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState


# ===== SCHEMA VALIDATION =====

class PainPointAnalysis(BaseModel):
    """
    Pydantic schema for pain-point analysis output.

    ROADMAP Phase 4 Quality Gates:
    - JSON-only output (no text outside JSON object)
    - Specific, business-outcome-focused language (not generic boilerplate)
    - No hallucinated company facts (only facts from job description)
    - Validated across 5+ diverse job scenarios

    Schema Enforcement:
    - All 4 required fields must be present
    - Each field is a list of non-empty strings
    - Item count constraints (relaxed for production runs):
      * pain_points: 1-8 items
      * strategic_needs: 1-8 items
      * risks_if_unfilled: 1-8 items
      * success_metrics: 1-8 items

    Content Requirements (enforced via prompt, validated via tests):
    - Focus on concrete business problems and outcomes
    - Include specific metrics/numbers where possible
    - Avoid generic HR boilerplate ("team player", "fast-paced", etc.)
    - Ground all statements in the provided job description
    """
    pain_points: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 specific technical/operational problems they need solved"
    )
    strategic_needs: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 strategic business reasons why this role matters"
    )
    risks_if_unfilled: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 consequences if this role stays empty"
    )
    success_metrics: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 measurable outcomes for success"
    )

    @field_validator('pain_points', 'strategic_needs', 'risks_if_unfilled', 'success_metrics')
    @classmethod
    def validate_non_empty_strings(cls, v: List[str]) -> List[str]:
        """Ensure all items are non-empty strings."""
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"All items must be non-empty strings, got: {item}")
        return v


# ===== PROMPT DESIGN =====

SYSTEM_PROMPT = """You are a reasoning model called "Pain-Point Miner" specializing in analyzing hiring motivations.

Your task: Analyze job descriptions to understand the deeper business drivers behind the role.

You MUST return ONLY a valid JSON object with these 4 arrays (3-6 items each):

{
  "pain_points": ["specific technical/operational problems they need solved"],
  "strategic_needs": ["why the company needs this role from a business perspective"],
  "risks_if_unfilled": ["what happens if this role stays empty"],
  "success_metrics": ["how they'll measure success once filled"]
}

**CRITICAL RULES:**
1. Output ONLY the JSON object - no text before or after
2. Each array must have 3-6 short bullet phrases (not paragraphs)
3. Focus on business outcomes, not just job requirements
4. Be specific and evidence-based

**HALLUCINATION PREVENTION:**
- Only use facts explicitly stated in the job description provided
- DO NOT invent company details (funding, products, size, history) not in the JD
- If something is unclear, infer from job requirements, don't fabricate
- When uncertain, prefer specific observable needs over speculation

**FORBIDDEN - Generic Boilerplate:**
- ❌ "Strong communication skills required"
- ❌ "Team player needed"
- ❌ "Fast-paced environment"
- ❌ "Work with stakeholders"
- ✅ Instead: "Migrate 50+ legacy APIs from monolith to microservices"
- ✅ Instead: "Reduce incident response time from 2 hours to 15 minutes"

Be concrete, technical, and tied to actual business problems stated in the JD.

NO TEXT OUTSIDE THE JSON OBJECT."""

USER_PROMPT_TEMPLATE = """Analyze this job posting and extract the underlying business drivers:

JOB TITLE: {title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description}

Return a JSON object with 4 arrays (3-6 items each):
- pain_points: Current problems/challenges they need solved
- strategic_needs: Why this role matters strategically
- risks_if_unfilled: Consequences of not filling this role
- success_metrics: How success will be measured

JSON only - no additional text:"""


class PainPointMiner:
    """
    Extracts pain points from job descriptions using LLM analysis.
    Phase 1.3: Returns JSON with 4 dimensions instead of simple bullets.
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
        Call LLM to extract pain points in JSON format.
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

    def _parse_json_response(self, llm_response: str) -> Dict[str, List[str]]:
        """
        Parse LLM JSON response into structured data with Pydantic validation.

        Returns:
            Dict with keys: pain_points, strategic_needs, risks_if_unfilled, success_metrics
            Each value is a list of strings.

        Raises:
            ValueError: If JSON parsing or validation fails
        """
        # Try to extract JSON from response (in case LLM adds extra text)
        # Look for content between { and }
        json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)

        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = llm_response.strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {llm_response[:500]}")

        # Validate with Pydantic schema
        try:
            validated = PainPointAnalysis(**data)
        except ValidationError as e:
            # Convert Pydantic validation errors to readable message
            error_messages = []
            for error in e.errors():
                field = ' -> '.join(str(x) for x in error['loc'])
                msg = error['msg']
                error_messages.append(f"{field}: {msg}")

            raise ValueError(
                f"JSON schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_messages) +
                f"\nReceived data: {json.dumps(data, indent=2)[:500]}"
            )

        # Return as dict (validated)
        return validated.model_dump()

    def extract_pain_points(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to extract pain points from job description.

        Args:
            state: Current JobState with job_description, title, company

        Returns:
            Dict with pain_points, strategic_needs, risks_if_unfilled, success_metrics
        """
        try:
            # Call LLM
            llm_response = self._call_llm(
                title=state["title"],
                company=state["company"],
                job_description=state["job_description"]
            )

            # Parse and validate JSON response (Pydantic handles all validation)
            parsed_data = self._parse_json_response(llm_response)

            print(f"✓ Extracted pain-point analysis (schema validated):")
            print(f"   - Pain points: {len(parsed_data['pain_points'])}")
            print(f"   - Strategic needs: {len(parsed_data['strategic_needs'])}")
            print(f"   - Risks if unfilled: {len(parsed_data['risks_if_unfilled'])}")
            print(f"   - Success metrics: {len(parsed_data['success_metrics'])}")

            return parsed_data

        except Exception as e:
            # Log error and return empty lists (don't block pipeline)
            error_msg = f"Layer 2 (Pain-Point Miner) failed: {str(e)}"
            print(f"✗ {error_msg}")

            return {
                "pain_points": [],
                "strategic_needs": [],
                "risks_if_unfilled": [],
                "success_metrics": [],
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
    print("LAYER 2: Pain-Point Miner (JSON Mode)")
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

        print("\nExtracted Strategic Needs:")
        for i, need in enumerate(updates.get("strategic_needs", []), 1):
            print(f"  {i}. {need}")
    else:
        print("\n⚠️  No pain-point analysis extracted")

    print("="*60 + "\n")

    return updates
