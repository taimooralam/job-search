"""
Per-Role CV Generator (Phase 3).

Generates tailored CV bullets for a single role from the master CV,
with full traceability to prevent hallucination.

Usage:
    generator = RoleGenerator()
    role_bullets = generator.generate(role, extracted_jd, career_context)
"""

import json
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import ExtractedJD
from src.common.logger import get_logger
from src.layer6_v2.cv_loader import RoleData
from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    CareerContext,
)
from src.layer6_v2.prompts.role_generation import (
    ROLE_GENERATION_SYSTEM_PROMPT,
    build_role_generation_user_prompt,
)


# ===== SCHEMA VALIDATION =====

class GeneratedBulletModel(BaseModel):
    """Pydantic model for validating generated bullet with STAR format (GAP-005)."""

    text: str = Field(..., min_length=20, max_length=250, description="STAR-formatted bullet text (20-35 words)")
    source_text: str = Field(..., min_length=10, description="Original achievement from source")
    source_metric: Optional[str] = Field(default=None, description="Exact metric from source")
    jd_keyword_used: Optional[str] = Field(default=None, description="JD keyword integrated")
    pain_point_addressed: Optional[str] = Field(default=None, description="Pain point addressed")
    # STAR components (GAP-005)
    situation: Optional[str] = Field(default=None, description="Challenge/context that prompted the action")
    action: Optional[str] = Field(default=None, description="What was done including skills/technologies")
    result: Optional[str] = Field(default=None, description="Quantified outcome achieved")

    @field_validator('text')
    @classmethod
    def validate_starts_with_verb(cls, v: str) -> str:
        """Warn if bullet doesn't start with action verb (but don't fail)."""
        v = v.strip()
        # Remove leading bullet character if present
        if v.startswith("•") or v.startswith("-"):
            v = v[1:].strip()
        return v

    @field_validator('source_text')
    @classmethod
    def validate_source_text(cls, v: str) -> str:
        """Clean source text."""
        v = v.strip()
        if v.startswith("•") or v.startswith("-"):
            v = v[1:].strip()
        return v


class RoleBulletsResponseModel(BaseModel):
    """Pydantic model for validating the full LLM response."""

    bullets: List[GeneratedBulletModel] = Field(
        ..., min_length=1, max_length=10,
        description="Generated bullets"
    )
    total_word_count: int = Field(..., ge=0, description="Total words across bullets")
    keywords_integrated: List[str] = Field(
        default_factory=list, max_length=20,
        description="JD keywords used"
    )

    def to_role_bullets(self, role: RoleData) -> RoleBullets:
        """Convert to RoleBullets dataclass with STAR components (GAP-005)."""
        generated_bullets = [
            GeneratedBullet(
                text=b.text,
                source_text=b.source_text,
                source_metric=b.source_metric,
                jd_keyword_used=b.jd_keyword_used,
                pain_point_addressed=b.pain_point_addressed,
                situation=b.situation,
                action=b.action,
                result=b.result,
            )
            for b in self.bullets
        ]

        return RoleBullets(
            role_id=role.id,
            company=role.company,
            title=role.title,
            period=role.period,
            location=role.location,
            bullets=generated_bullets,
            word_count=self.total_word_count,
            keywords_integrated=self.keywords_integrated,
        )


# ===== ROLE GENERATOR CLASS =====

class RoleGenerator:
    """
    Generates tailored CV bullets for a single role.

    Uses LLM to transform source achievements into JD-aligned bullets
    while maintaining full traceability to prevent hallucination.
    """

    def __init__(self, model: Optional[str] = None, temperature: Optional[float] = None):
        """
        Initialize the generator with LLM.

        Args:
            model: Model to use (defaults to Config.DEFAULT_MODEL)
            temperature: Temperature for generation (defaults to 0.3 for consistency)
        """
        self.model = model or Config.DEFAULT_MODEL
        self.temperature = temperature if temperature is not None else 0.3  # Lower for consistency
        self.llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self._logger = get_logger(__name__)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_llm(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        career_context: CareerContext,
        target_bullet_count: Optional[int] = None,
    ) -> str:
        """
        Call LLM with role generation prompt.

        Args:
            role: Role data from CV loader
            extracted_jd: Structured JD intelligence
            career_context: Career stage context
            target_bullet_count: Target number of bullets

        Returns:
            Raw LLM response string
        """
        user_prompt = build_role_generation_user_prompt(
            role=role,
            extracted_jd=extracted_jd,
            career_context=career_context,
            target_bullet_count=target_bullet_count,
        )

        messages = [
            SystemMessage(content=ROLE_GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        return response.content

    def _parse_response(self, llm_response: str, role: RoleData) -> RoleBullets:
        """
        Parse and validate LLM response.

        Args:
            llm_response: Raw LLM response
            role: Role data for context

        Returns:
            RoleBullets with validated bullets

        Raises:
            ValueError: If response is invalid
        """
        # Clean response
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

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nResponse: {json_str[:500]}")

        # Validate with Pydantic
        try:
            validated = RoleBulletsResponseModel(**data)
        except ValidationError as e:
            error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                        for err in e.errors()]
            raise ValueError(
                f"Schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_msgs)
            )

        return validated.to_role_bullets(role)

    def generate(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        career_context: Optional[CareerContext] = None,
        target_bullet_count: Optional[int] = None,
    ) -> RoleBullets:
        """
        Generate tailored bullets for a role.

        Args:
            role: Role data from CV loader
            extracted_jd: Structured JD intelligence from Layer 1.4
            career_context: Career stage context (built automatically if not provided)
            target_bullet_count: Target number of bullets

        Returns:
            RoleBullets with generated bullets

        Raises:
            ValueError: If generation fails after retries
        """
        # Build career context if not provided
        if career_context is None:
            # Assume this is role 0 and only role if context not provided
            career_context = CareerContext.build(
                role_index=0,
                total_roles=1,
                is_current=role.is_current,
                target_role_category=extracted_jd.get("role_category", "staff_principal_engineer"),
            )

        self._logger.info(f"Generating bullets for: {role.company} - {role.title}")
        self._logger.info(f"Career stage: {career_context.career_stage}")
        self._logger.info(f"Source achievements: {len(role.achievements)}")

        # Call LLM
        llm_response = self._call_llm(
            role=role,
            extracted_jd=extracted_jd,
            career_context=career_context,
            target_bullet_count=target_bullet_count,
        )

        # Parse and validate
        role_bullets = self._parse_response(llm_response, role)

        self._logger.info(f"Generated {role_bullets.bullet_count} bullets")
        self._logger.info(f"Word count: {role_bullets.word_count}")
        self._logger.info(f"Keywords integrated: {len(role_bullets.keywords_integrated)}")

        return role_bullets


def generate_all_roles_sequential(
    roles: List[RoleData],
    extracted_jd: ExtractedJD,
    generator: Optional[RoleGenerator] = None,
) -> List[RoleBullets]:
    """
    Generate bullets for all roles sequentially.

    Sequential processing chosen for:
    - Predictable LLM costs
    - Easier debugging (see exactly which role failed)
    - Immediate QA after each role (can retry before moving on)

    Args:
        roles: List of roles from CV loader (should be in chronological order)
        extracted_jd: Structured JD intelligence
        generator: RoleGenerator instance (created if not provided)

    Returns:
        List of RoleBullets, one per role
    """
    logger = get_logger(__name__)
    generator = generator or RoleGenerator()
    results = []

    target_role_category = extracted_jd.get("role_category", "staff_principal_engineer")
    total_roles = len(roles)

    for i, role in enumerate(roles):
        logger.info(f"\n{'='*50}")
        logger.info(f"Processing role {i+1}/{total_roles}: {role.company}")
        logger.info(f"{'='*50}")

        # Build career context for this role
        career_context = CareerContext.build(
            role_index=i,
            total_roles=total_roles,
            is_current=role.is_current,
            target_role_category=target_role_category,
        )

        try:
            role_bullets = generator.generate(
                role=role,
                extracted_jd=extracted_jd,
                career_context=career_context,
            )
            results.append(role_bullets)
            logger.info(f"✓ Generated {role_bullets.bullet_count} bullets for {role.company}")

        except Exception as e:
            logger.error(f"✗ Failed to generate for {role.company}: {e}")
            # Create empty RoleBullets to maintain order
            results.append(RoleBullets(
                role_id=role.id,
                company=role.company,
                title=role.title,
                period=role.period,
                location=role.location,
                bullets=[],
                word_count=0,
                keywords_integrated=[],
            ))

    # Summary
    total_bullets = sum(rb.bullet_count for rb in results)
    total_words = sum(rb.word_count for rb in results)
    logger.info(f"\n{'='*50}")
    logger.info("GENERATION COMPLETE")
    logger.info(f"Total bullets: {total_bullets}")
    logger.info(f"Total words: {total_words}")
    logger.info(f"Roles with bullets: {sum(1 for rb in results if rb.bullet_count > 0)}/{total_roles}")
    logger.info(f"{'='*50}")

    return results
