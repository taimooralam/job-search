"""
Layer 1.4: JD Extractor

Extracts structured intelligence from job descriptions using LLM.
Returns ExtractedJD with role classification, competency weights, and ATS keywords.

This layer runs BEFORE Layer 2 (Pain Point Miner) and provides context for:
- Role-category-aware CV tailoring
- ATS keyword optimization
- Competency-weighted bullet selection
"""

import json
import re
from typing import Dict, Any, List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.state import JobState, ExtractedJD
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.layer1_4.prompts import (
    JD_EXTRACTION_SYSTEM_PROMPT,
    JD_EXTRACTION_USER_TEMPLATE,
)


# ===== SCHEMA VALIDATION =====

class RoleCategory(str, Enum):
    """Role category classification for CV tailoring."""
    ENGINEERING_MANAGER = "engineering_manager"
    STAFF_PRINCIPAL_ENGINEER = "staff_principal_engineer"
    DIRECTOR_OF_ENGINEERING = "director_of_engineering"
    HEAD_OF_ENGINEERING = "head_of_engineering"
    CTO = "cto"
    TECH_LEAD = "tech_lead"  # Covers Team Lead, Tech Lead, Lead Engineer
    SENIOR_ENGINEER = "senior_engineer"  # Fallback for senior IC roles


class SeniorityLevel(str, Enum):
    """Seniority level classification."""
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VP = "vp"
    C_LEVEL = "c_level"


class RemotePolicy(str, Enum):
    """Remote work policy classification."""
    FULLY_REMOTE = "fully_remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    NOT_SPECIFIED = "not_specified"


class CompetencyWeightsModel(BaseModel):
    """Competency weights with sum validation."""
    delivery: int = Field(..., ge=0, le=100, description="Shipping features, product execution")
    process: int = Field(..., ge=0, le=100, description="CI/CD, testing, quality standards")
    architecture: int = Field(..., ge=0, le=100, description="System design, technical strategy")
    leadership: int = Field(..., ge=0, le=100, description="People management, team building")

    @model_validator(mode='after')
    def validate_sum(self) -> 'CompetencyWeightsModel':
        """Ensure weights sum to exactly 100."""
        total = self.delivery + self.process + self.architecture + self.leadership
        if total != 100:
            raise ValueError(f"Competency weights must sum to 100, got {total}")
        return self


class ExtractedJDModel(BaseModel):
    """Pydantic model for JD extraction validation."""

    # Basic Info
    title: str = Field(..., min_length=3, description="Job title")
    company: str = Field(..., min_length=1, description="Company name")
    location: str = Field(default="Not specified", description="Location")
    remote_policy: RemotePolicy = Field(default=RemotePolicy.NOT_SPECIFIED)

    # Role Classification
    role_category: RoleCategory = Field(..., description="Role category for CV tailoring")
    seniority_level: SeniorityLevel = Field(..., description="Seniority level")

    # Competency Mix
    competency_weights: CompetencyWeightsModel = Field(..., description="Competency weights (sum=100)")

    # Content Extraction
    responsibilities: List[str] = Field(
        ..., min_length=3, max_length=15,
        description="Key responsibilities"
    )
    qualifications: List[str] = Field(
        ..., min_length=2, max_length=12,
        description="Required qualifications"
    )
    nice_to_haves: List[str] = Field(
        default_factory=list, max_length=10,
        description="Optional qualifications"
    )
    technical_skills: List[str] = Field(
        default_factory=list, max_length=20,
        description="Technical skills mentioned"
    )
    soft_skills: List[str] = Field(
        default_factory=list, max_length=10,
        description="Soft skills mentioned"
    )

    # Pain Points (inferred)
    implied_pain_points: List[str] = Field(
        default_factory=list, max_length=8,
        description="Inferred problems this hire solves"
    )
    success_metrics: List[str] = Field(
        default_factory=list, max_length=8,
        description="How success will be measured"
    )

    # ATS Keywords
    top_keywords: List[str] = Field(
        ..., min_length=10, max_length=20,
        description="Top 15 ATS keywords"
    )

    # Background Requirements
    industry_background: Optional[str] = Field(default=None)
    years_experience_required: Optional[int] = Field(default=None, ge=0, le=50)
    education_requirements: Optional[str] = Field(default=None)

    @field_validator('responsibilities', 'qualifications')
    @classmethod
    def validate_non_empty_strings(cls, v: List[str]) -> List[str]:
        """Ensure all items are non-empty strings."""
        return [item.strip() for item in v if item and item.strip()]

    @field_validator('top_keywords')
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        """Deduplicate and clean keywords."""
        seen = set()
        result = []
        for kw in v:
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean not in seen:
                seen.add(kw_clean)
                result.append(kw.strip())
        return result

    def to_extracted_jd(self) -> ExtractedJD:
        """Convert to TypedDict for state."""
        return ExtractedJD(
            title=self.title,
            company=self.company,
            location=self.location,
            remote_policy=self.remote_policy.value,
            role_category=self.role_category.value,
            seniority_level=self.seniority_level.value,
            competency_weights={
                "delivery": self.competency_weights.delivery,
                "process": self.competency_weights.process,
                "architecture": self.competency_weights.architecture,
                "leadership": self.competency_weights.leadership,
            },
            responsibilities=self.responsibilities,
            qualifications=self.qualifications,
            nice_to_haves=self.nice_to_haves,
            technical_skills=self.technical_skills,
            soft_skills=self.soft_skills,
            implied_pain_points=self.implied_pain_points,
            success_metrics=self.success_metrics,
            top_keywords=self.top_keywords,
            industry_background=self.industry_background,
            years_experience_required=self.years_experience_required,
            education_requirements=self.education_requirements,
        )


# ===== JD EXTRACTOR CLASS =====

class JDExtractor:
    """
    Extracts structured intelligence from job descriptions.

    Uses LLM to analyze job descriptions and extract:
    - Role classification (EM, Staff, Director, Head, CTO)
    - Competency weights (delivery, process, architecture, leadership)
    - ATS keywords (top 15 for optimization)
    - Structured content (responsibilities, qualifications, skills)
    """

    def __init__(self):
        """Initialize the extractor with LLM."""
        # GAP-066: Token tracking enabled
        self.llm = create_tracked_llm(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,
            layer="layer1_4",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_llm(self, title: str, company: str, job_description: str) -> str:
        """Call LLM with JD extraction prompt."""
        messages = [
            SystemMessage(content=JD_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(
                content=JD_EXTRACTION_USER_TEMPLATE.format(
                    title=title,
                    company=company,
                    job_description=job_description
                )
            )
        ]

        response = self.llm.invoke(messages)
        return response.content

    def _parse_response(self, llm_response: str) -> ExtractedJDModel:
        """Parse and validate LLM response."""
        # Try to extract JSON from response
        json_str = llm_response.strip()

        # Remove markdown code blocks if present
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()

        # Find JSON object if wrapped in other text
        if not json_str.startswith("{"):
            json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError(f"No JSON found in response: {llm_response[:500]}")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nResponse: {json_str[:500]}")

        # Normalize enum values (handle case variations)
        if "role_category" in data:
            data["role_category"] = data["role_category"].lower().replace(" ", "_").replace("-", "_")
        if "seniority_level" in data:
            data["seniority_level"] = data["seniority_level"].lower().replace(" ", "_").replace("-", "_")
        if "remote_policy" in data:
            data["remote_policy"] = data["remote_policy"].lower().replace(" ", "_").replace("-", "_")

        try:
            return ExtractedJDModel(**data)
        except ValidationError as e:
            error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                        for err in e.errors()]
            raise ValueError(
                f"Schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_msgs)
            )

    def extract(self, state: JobState) -> Dict[str, Any]:
        """
        Extract structured JD intelligence.

        Args:
            state: Current JobState with job_description, title, company

        Returns:
            Dict with extracted_jd field for state update
        """
        logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer1_4")

        try:
            # Call LLM
            llm_response = self._call_llm(
                title=state["title"],
                company=state["company"],
                job_description=state["job_description"]
            )

            # Parse and validate
            extracted = self._parse_response(llm_response)

            # Convert to TypedDict
            extracted_jd = extracted.to_extracted_jd()

            # Log extraction summary
            logger.info(f"Role Category: {extracted.role_category.value}")
            logger.info(f"Seniority: {extracted.seniority_level.value}")
            logger.info(f"Competency Weights: D={extracted.competency_weights.delivery}% "
                       f"P={extracted.competency_weights.process}% "
                       f"A={extracted.competency_weights.architecture}% "
                       f"L={extracted.competency_weights.leadership}%")
            logger.info(f"Location: {extracted.location} ({extracted.remote_policy.value})")
            logger.info(f"Top Keywords: {', '.join(extracted.top_keywords[:5])}...")
            logger.info(f"Responsibilities: {len(extracted.responsibilities)}")
            logger.info(f"Qualifications: {len(extracted.qualifications)}")
            logger.info(f"Technical Skills: {len(extracted.technical_skills)}")

            return {"extracted_jd": extracted_jd}

        except Exception as e:
            error_msg = f"Layer 1.4 (JD Extractor) failed: {str(e)}"
            logger.error(error_msg)

            # Return None for extracted_jd (don't block pipeline)
            return {
                "extracted_jd": None,
                "errors": state.get("errors", []) + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def jd_extractor_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 1.4: JD Extractor.

    This is the function called by the LangGraph workflow.
    Runs BEFORE Layer 2 (Pain Point Miner) to provide context.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer1_4")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    logger.info("=" * 60)
    logger.info("LAYER 1.4: JD Extractor")
    logger.info("=" * 60)
    logger.info(f"Job: {state['title']} at {state['company']}")
    logger.info(f"Description length: {len(state['job_description'])} chars")

    with LayerContext(struct_logger, 1, "jd_extractor") as ctx:
        # Extract structured JD intelligence
        extractor = JDExtractor()
        updates = extractor.extract(state)

        # Log summary and add metadata
        if updates.get("extracted_jd"):
            jd = updates["extracted_jd"]
            ctx.add_metadata("role_category", jd["role_category"])
            ctx.add_metadata("keywords_count", len(jd["top_keywords"]))
            logger.info("Extraction successful:")
            logger.info(f"  Role: {jd['role_category']}")
            logger.info(f"  Keywords: {len(jd['top_keywords'])}")
            logger.info(f"  Implied pain points: {len(jd.get('implied_pain_points', []))}")
        else:
            logger.warning("JD extraction failed - downstream layers will use defaults")

    logger.info("=" * 60)

    return updates
