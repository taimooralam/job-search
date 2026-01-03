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
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING
from pydantic import BaseModel, Field, ValidationError, field_validator
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.unified_llm import UnifiedLLM
from src.common.state import ExtractedJD
from src.common.logger import get_logger
from src.common.utils import coerce_to_list

if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger
from src.layer6_v2.cv_loader import RoleData
from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    CareerContext,
)
from src.layer6_v2.prompts.role_generation import (
    ROLE_GENERATION_SYSTEM_PROMPT,
    build_role_generation_user_prompt,
    build_role_system_prompt_with_persona,
    STAR_CORRECTION_SYSTEM_PROMPT,
    build_star_correction_user_prompt,
)
# Variant-based generation support
from src.layer6_v2.variant_selector import (
    VariantSelector,
    SelectionResult,
    select_variants_for_role,
)


# ===== SCHEMA VALIDATION =====

class GeneratedBulletModel(BaseModel):
    """Pydantic model for validating generated bullet with ARIS format (GAP-005 updated)."""

    text: str = Field(..., min_length=20, max_length=300, description="ARIS-formatted bullet text (25-40 words)")
    source_text: str = Field(..., min_length=10, description="Original achievement from source")
    source_metric: Optional[str] = Field(default=None, description="Exact metric from source")
    jd_keyword_used: Optional[str] = Field(default=None, description="JD keyword integrated")
    pain_point_addressed: Optional[str] = Field(default=None, description="Pain point addressed")
    # ARIS components (GAP-005 updated to ARIS format)
    action: Optional[str] = Field(default=None, description="What was done including skills/technologies (appears first)")
    result: Optional[str] = Field(default=None, description="Quantified outcome achieved (appears after action)")
    situation: Optional[str] = Field(default=None, description="Challenge/context tied to JD pain point (appears at end)")

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
        """Convert to RoleBullets dataclass with ARIS components (GAP-005 updated)."""
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
            hard_skills=role.hard_skills,
            soft_skills=role.soft_skills,
        )


# ===== ROLE GENERATOR CLASS =====

class RoleGenerator:
    """
    Generates tailored CV bullets for a single role.

    Uses LLM to transform source achievements into JD-aligned bullets
    while maintaining full traceability to prevent hallucination.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
        struct_logger: Optional["StructuredLogger"] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the generator with LLM.

        Args:
            model: Model to use (defaults to step config)
            temperature: Temperature for generation (defaults to 0.3 for consistency)
            job_id: Job ID for tracking (optional)
            progress_callback: Optional callback for granular LLM progress events to Redis
            struct_logger: Optional StructuredLogger for Phase 0 structured logging
            log_callback: Optional callback for Phase 0 dual-emit logging (works in-process)
        """
        self.model = model or Config.DEFAULT_MODEL
        self.temperature = temperature if temperature is not None else 0.3  # Lower for consistency
        self._job_id = job_id or "unknown"
        self._logger = get_logger(__name__)
        self._progress_callback = progress_callback
        # Phase 0 Extension: Structured logging support
        self._struct_logger = struct_logger
        self._log_callback = log_callback

        # Use UnifiedLLM with step config (middle tier for role_generator)
        self._llm = UnifiedLLM(
            step_name="role_generator",
            job_id=self._job_id,
            progress_callback=progress_callback,
        )
        self._logger.info(
            f"RoleGenerator initialized with UnifiedLLM (step=role_generator, tier={self._llm.config.tier})"
        )

    @staticmethod
    def _preview(text: str, n: int = 50) -> str:
        """Generate a preview of text: first n chars + '...' + last n chars."""
        if not text:
            return ""
        if len(text) <= n * 2 + 3:
            return text
        return f"{text[:n]}...{text[-n:]}"

    def _emit_struct_log(self, event: str, metadata: dict) -> None:
        """
        Emit structured log for Phase 0 Extension.

        Dual-emit pattern: sends to BOTH log_callback (for in-process mode)
        AND struct_logger stdout (for subprocess mode).
        """
        # Emit via log_callback (works in-process for CVGenerationService)
        if self._log_callback:
            try:
                data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "layer": 6,
                    "layer_name": "role_generator",
                    "event": f"cv_role_gen_{event}",
                    "message": metadata.get("message", event),
                    "job_id": self._job_id,
                    "metadata": metadata,
                }
                self._log_callback(json.dumps(data))
            except Exception:
                pass  # Fire-and-forget logging

        # Also emit via struct_logger stdout (works in subprocess mode)
        if self._struct_logger:
            try:
                self._struct_logger.emit(
                    event=f"cv_role_gen_{event}",
                    layer=6,
                    metadata=metadata,
                )
            except Exception:
                pass  # Fire-and-forget logging

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _call_llm(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        career_context: CareerContext,
        target_bullet_count: Optional[int] = None,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Call LLM with role generation prompt.

        Args:
            role: Role data from CV loader
            extracted_jd: Structured JD intelligence
            career_context: Career stage context
            target_bullet_count: Target number of bullets
            jd_annotations: Optional JD annotations with persona for system prompt framing

        Returns:
            Raw LLM response string (JSON)
        """
        user_prompt = build_role_generation_user_prompt(
            role=role,
            extracted_jd=extracted_jd,
            career_context=career_context,
            target_bullet_count=target_bullet_count,
            jd_annotations=jd_annotations,
        )

        # Build system prompt with persona if available
        system_prompt = build_role_system_prompt_with_persona(
            jd_annotations=jd_annotations,
            base_prompt=ROLE_GENERATION_SYSTEM_PROMPT,
        )

        # Check if persona was injected
        persona_used = None
        if jd_annotations and jd_annotations.get("synthesized_persona", {}).get("persona_statement"):
            self._logger.info("📌 Persona injected into role generation system prompt")
            persona_used = jd_annotations.get("synthesized_persona", {}).get("persona_name", "custom")

        # Phase 0: Generate session ID and emit LLM call start
        session_id = f"role_gen_{uuid.uuid4().hex[:8]}"
        import time
        start_time = time.time()

        self._emit_struct_log("llm_call_start", {
            "message": f"LLM call starting for {role.company} - {role.title}",
            "session_id": session_id,
            "role_company": role.company,
            "role_title": role.title,
            "system_prompt_preview": self._preview(system_prompt, 80),
            "user_prompt_preview": self._preview(user_prompt, 120),
            "system_prompt_length": len(system_prompt),
            "user_prompt_length": len(user_prompt),
            "persona_used": persona_used,
            "target_bullet_count": target_bullet_count,
        })

        # Use UnifiedLLM with JSON validation
        result = await self._llm.invoke(
            prompt=user_prompt,
            system=system_prompt,
            validate_json=True,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if not result.success:
            # Emit failure log
            self._emit_struct_log("llm_call_failed", {
                "message": f"LLM call FAILED for {role.company}: {result.error}",
                "session_id": session_id,
                "role_company": role.company,
                "role_title": role.title,
                "error": result.error,
                "duration_ms": duration_ms,
            })
            raise ValueError(f"LLM role generation failed: {result.error}")

        # Phase 0: Emit LLM call complete with result preview
        self._emit_struct_log("llm_call_complete", {
            "message": f"LLM call complete for {role.company}: {len(result.content)} chars",
            "session_id": session_id,
            "role_company": role.company,
            "role_title": role.title,
            "result_preview": self._preview(result.content, 150),
            "result_length": len(result.content),
            "duration_ms": duration_ms,
        })

        # Return the raw JSON content for parsing
        return result.content

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

    async def generate(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        career_context: Optional[CareerContext] = None,
        target_bullet_count: Optional[int] = None,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> RoleBullets:
        """
        Generate tailored bullets for a role.

        Args:
            role: Role data from CV loader
            extracted_jd: Structured JD intelligence from Layer 1.4
            career_context: Career stage context (built automatically if not provided)
            target_bullet_count: Target number of bullets
            jd_annotations: Optional JD annotations with persona for system prompt framing

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

        # Phase 0: Emit subphase start
        self._emit_struct_log("subphase_start", {
            "message": f"Starting bullet generation for {role.company} - {role.title}",
            "phase": 2,
            "subphase": f"role_{role.company}",
            "role_title": role.title,
            "role_company": role.company,
            "role_period": role.period,
            "career_stage": career_context.career_stage,
            "source_achievement_count": len(role.achievements),
            "target_bullet_count": target_bullet_count,
            "generation_method": "llm",
        })

        # Call LLM with persona from annotations (if available)
        llm_response = await self._call_llm(
            role=role,
            extracted_jd=extracted_jd,
            career_context=career_context,
            target_bullet_count=target_bullet_count,
            jd_annotations=jd_annotations,
        )

        # Parse and validate
        role_bullets = self._parse_response(llm_response, role)

        self._logger.info(f"Generated {role_bullets.bullet_count} bullets")
        self._logger.info(f"Word count: {role_bullets.word_count}")
        self._logger.info(f"Keywords integrated: {len(role_bullets.keywords_integrated)}")

        # Phase 0: Emit decision point with bullet details
        bullet_details = []
        for i, bullet in enumerate(role_bullets.bullets):
            bullet_details.append({
                "index": i,
                "text_preview": self._preview(bullet.text, 60),
                "word_count": bullet.word_count,
                "jd_keyword_used": bullet.jd_keyword_used,
                "source_metric": bullet.source_metric,
            })

        self._emit_struct_log("decision_point", {
            "message": f"Bullet generation complete for {role.company}: {role_bullets.bullet_count} bullets",
            "decision": "bullet_generation",
            "role_company": role.company,
            "role_title": role.title,
            "bullets_count": role_bullets.bullet_count,
            "total_word_count": role_bullets.word_count,
            "keywords_integrated": role_bullets.keywords_integrated[:10],  # Limit for log size
            "keywords_count": len(role_bullets.keywords_integrated),
            "bullet_details": bullet_details,
        })

        # Phase 0: Emit subphase complete
        self._emit_struct_log("subphase_complete", {
            "message": f"Completed bullet generation for {role.company}",
            "phase": 2,
            "subphase": f"role_{role.company}",
            "role_title": role.title,
            "role_company": role.company,
            "bullets_generated": role_bullets.bullet_count,
            "word_count": role_bullets.word_count,
            "generation_method": "llm",
        })

        return role_bullets

    def generate_from_variants(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        target_bullet_count: Optional[int] = None,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> Optional[RoleBullets]:
        """
        Generate bullets by selecting from pre-written variants.

        Phase 4: Supports JD annotations for boost calculation and keyword injection.

        This method uses the VariantSelector to choose optimal achievement
        variants based on JD requirements. It's faster and more deterministic
        than LLM generation, with zero hallucination risk since all text is
        pre-written and interview-defensible.

        Args:
            role: Role data with enhanced_data containing variants
            extracted_jd: Structured JD intelligence from Layer 1.4
            target_bullet_count: Target number of bullets (defaults to role's achievement count)
            jd_annotations: Optional JDAnnotations for boost calculation

        Returns:
            RoleBullets with selected variants, or None if role has no variants
        """
        # Check if role has variant data
        if not role.has_variants or not role.enhanced_data:
            self._logger.info(f"No variant data for {role.company} - skipping variant selection")
            return None

        self._logger.info(f"Selecting variants for: {role.company} - {role.title}")
        self._logger.info(f"Available achievements: {len(role.enhanced_data.achievements)}")
        self._logger.info(f"Total variants: {role.variant_count}")

        # Phase 0: Emit subphase start for variant selection
        self._emit_struct_log("subphase_start", {
            "message": f"Starting variant selection for {role.company} - {role.title}",
            "phase": 2,
            "subphase": f"role_{role.company}",
            "role_title": role.title,
            "role_company": role.company,
            "available_achievements": len(role.enhanced_data.achievements),
            "total_variants": role.variant_count,
            "target_bullet_count": target_bullet_count,
            "generation_method": "variant_selection",
        })

        # Build JD context for variant selection
        # Coerce all list fields to handle LLM returning strings instead of lists
        jd_context = {
            "role_category": extracted_jd.get("role_category", "default"),
            "top_keywords": coerce_to_list(extracted_jd.get("top_keywords")),
            "technical_skills": coerce_to_list(extracted_jd.get("technical_skills")),
            "soft_skills": coerce_to_list(extracted_jd.get("soft_skills")),
            "implied_pain_points": coerce_to_list(extracted_jd.get("implied_pain_points")),
        }

        # Determine target count
        if target_bullet_count is None:
            target_bullet_count = min(len(role.enhanced_data.achievements), 6)

        # Select variants using the VariantSelector (Phase 4: with annotations)
        selector = VariantSelector()
        selection_result = selector.select_variants(
            role=role.enhanced_data,
            extracted_jd=jd_context,
            target_count=target_bullet_count,
            jd_annotations=jd_annotations,
        )

        self._logger.info(f"Selected {selection_result.selection_count} variants")
        self._logger.info(f"Keyword coverage: {selection_result.keyword_coverage:.1%}")

        # Phase 4: Log annotation influence
        annotation_count = sum(1 for v in selection_result.selected_variants if v.annotation_influenced)
        if annotation_count > 0:
            self._logger.info(f"📌 {annotation_count} variants influenced by annotations")

        # Convert selected variants to GeneratedBullet format
        generated_bullets = []
        keywords_integrated = list(selection_result.jd_keywords_covered)

        for selected in selection_result.selected_variants:
            # Find the original achievement for source_text
            achievement = role.enhanced_data.get_achievement_by_id(selected.achievement_id)
            source_text = achievement.core_fact if achievement else ""

            # Extract any metrics from the variant text (simple pattern matching)
            source_metric = self._extract_metric(selected.text)

            # Create GeneratedBullet with traceability (Phase 4: annotation fields)
            bullet = GeneratedBullet(
                text=selected.text,
                source_text=source_text,
                source_metric=source_metric,
                jd_keyword_used=selected.score.matched_keywords[0] if selected.score.matched_keywords else None,
                pain_point_addressed=None,  # Variant selection doesn't track pain points per-bullet
                # STAR components not explicitly tracked in variant selection
                situation=None,
                action=None,
                result=None,
                # Phase 4: Annotation traceability
                annotation_influenced=selected.annotation_influenced,
                annotation_ids=selected.annotation_ids,
                reframe_applied=selected.reframe_applied,
                annotation_keywords_used=selected.annotation_keywords_used,
                annotation_boost=selected.score.annotation_boost,
            )
            generated_bullets.append(bullet)

        # Build RoleBullets
        role_bullets = RoleBullets(
            role_id=role.id,
            company=role.company,
            title=role.title,
            period=role.period,
            location=role.location,
            bullets=generated_bullets,
            word_count=sum(b.word_count for b in generated_bullets),
            keywords_integrated=keywords_integrated,
            hard_skills=role.hard_skills,
            soft_skills=role.soft_skills,
        )

        self._logger.info(f"Generated {role_bullets.bullet_count} bullets from variants")
        self._logger.info(f"Word count: {role_bullets.word_count}")
        self._logger.info(f"Keywords integrated: {len(keywords_integrated)}")

        # Phase 0: Emit decision point with variant selection details
        bullet_details = []
        for i, bullet in enumerate(role_bullets.bullets):
            bullet_details.append({
                "index": i,
                "text_preview": self._preview(bullet.text, 60),
                "word_count": bullet.word_count,
                "jd_keyword_used": bullet.jd_keyword_used,
                "source_metric": bullet.source_metric,
                "annotation_influenced": bullet.annotation_influenced,
            })

        self._emit_struct_log("decision_point", {
            "message": f"Variant selection complete for {role.company}: {role_bullets.bullet_count} bullets",
            "decision": "variant_selection",
            "role_company": role.company,
            "role_title": role.title,
            "bullets_count": role_bullets.bullet_count,
            "total_word_count": role_bullets.word_count,
            "keyword_coverage": selection_result.keyword_coverage,
            "keywords_integrated": keywords_integrated[:10],  # Limit for log size
            "keywords_count": len(keywords_integrated),
            "annotation_influenced_count": annotation_count,
            "bullet_details": bullet_details,
        })

        # Phase 0: Emit subphase complete
        self._emit_struct_log("subphase_complete", {
            "message": f"Completed variant selection for {role.company}",
            "phase": 2,
            "subphase": f"role_{role.company}",
            "role_title": role.title,
            "role_company": role.company,
            "bullets_generated": role_bullets.bullet_count,
            "word_count": role_bullets.word_count,
            "keyword_coverage": selection_result.keyword_coverage,
            "generation_method": "variant_selection",
        })

        return role_bullets

    def _extract_metric(self, text: str) -> Optional[str]:
        """Extract a metric (percentage, number, etc.) from bullet text."""
        import re
        # Match percentages, dollar amounts, multipliers, and large numbers
        patterns = [
            r'\d+\.?\d*%',              # 75%, 99.9%
            r'\$[\d,]+[KMB]?',          # $30M, $1,000
            r'€[\d,]+[KMB]?',           # €30M
            r'\d+x',                    # 10x
            r'\d+[\d,]*\+?\s*(users|events|requests|impressions)',  # 1M users
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    async def generate_with_variant_fallback(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        career_context: Optional[CareerContext] = None,
        target_bullet_count: Optional[int] = None,
        prefer_variants: bool = True,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> RoleBullets:
        """
        Generate bullets with variant selection first, LLM as fallback.

        This is the recommended generation method for production use:
        1. Try variant selection (fast, deterministic, zero hallucination)
        2. Fall back to LLM generation if variants unavailable

        Args:
            role: Role data from CV loader
            extracted_jd: Structured JD intelligence
            career_context: Career stage context
            target_bullet_count: Target number of bullets
            prefer_variants: If True, try variant selection first (default: True)
            jd_annotations: Optional JD annotations with persona for LLM fallback

        Returns:
            RoleBullets with generated/selected bullets
        """
        # Try variant-based generation first if preferred and available
        if prefer_variants and role.has_variants:
            variant_result = self.generate_from_variants(
                role=role,
                extracted_jd=extracted_jd,
                target_bullet_count=target_bullet_count,
                jd_annotations=jd_annotations,
            )
            if variant_result and variant_result.bullet_count > 0:
                self._logger.info(f"Used variant selection for {role.company}")
                return variant_result

        # Fall back to LLM generation with persona from annotations
        self._logger.info(f"Using LLM generation for {role.company}")
        return await self.generate(
            role=role,
            extracted_jd=extracted_jd,
            career_context=career_context,
            target_bullet_count=target_bullet_count,
            jd_annotations=jd_annotations,
        )

    async def generate_with_star_enforcement(
        self,
        role: RoleData,
        extracted_jd: ExtractedJD,
        career_context: Optional[CareerContext] = None,
        target_bullet_count: Optional[int] = None,
        max_retries: int = 2,
        star_threshold: float = 0.8,
    ) -> RoleBullets:
        """
        Generate bullets with STAR format enforcement and retry (GAP-005).

        This method:
        1. Generates initial bullets
        2. Validates STAR format using RoleQA
        3. Corrects any failing bullets
        4. Repeats up to max_retries times until threshold met

        Args:
            role: Role data from CV loader
            extracted_jd: Structured JD intelligence
            career_context: Career stage context
            target_bullet_count: Target number of bullets
            max_retries: Maximum correction attempts (default: 2)
            star_threshold: Minimum STAR coverage to pass (default: 0.8 = 80%)

        Returns:
            RoleBullets with STAR-validated bullets
        """
        # Import here to avoid circular dependency
        from src.layer6_v2.role_qa import RoleQA

        # Build career context if not provided
        if career_context is None:
            career_context = CareerContext.build(
                role_index=0,
                total_roles=1,
                is_current=role.is_current,
                target_role_category=extracted_jd.get("role_category", "staff_principal_engineer"),
            )

        # Step 1: Generate initial bullets
        role_bullets = await self.generate(
            role=role,
            extracted_jd=extracted_jd,
            career_context=career_context,
            target_bullet_count=target_bullet_count,
        )

        # Step 2: Run STAR validation
        qa = RoleQA()
        star_result = qa.check_star_format(role_bullets)

        if star_result.passed:
            self._logger.info(f"STAR validation passed ({star_result.star_coverage:.0%} coverage)")
            return role_bullets

        # Step 3: Correction loop for failing bullets
        for retry in range(max_retries):
            self._logger.info(
                f"STAR validation failed ({star_result.star_coverage:.0%}). "
                f"Retry {retry + 1}/{max_retries}..."
            )

            # Identify failing bullets by index
            failing_indices = self._identify_failing_bullets(role_bullets, qa)

            if not failing_indices:
                self._logger.info("No specific failing bullets identified - regenerating all")
                role_bullets = await self.generate(
                    role=role,
                    extracted_jd=extracted_jd,
                    career_context=career_context,
                    target_bullet_count=target_bullet_count,
                )
            else:
                # Correct each failing bullet
                for idx in failing_indices:
                    if idx < len(role_bullets.bullets):
                        bullet = role_bullets.bullets[idx]
                        missing = self._get_missing_star_elements(bullet.text, qa)
                        corrected_text = await self._correct_bullet_star(
                            bullet=bullet,
                            missing_elements=missing,
                            role=role,
                        )
                        if corrected_text:
                            # Update the bullet with corrected text
                            role_bullets.bullets[idx] = GeneratedBullet(
                                text=corrected_text,
                                source_text=bullet.source_text,
                                source_metric=bullet.source_metric,
                                jd_keyword_used=bullet.jd_keyword_used,
                                pain_point_addressed=bullet.pain_point_addressed,
                                situation=None,  # Will be re-validated
                                action=None,
                                result=None,
                            )

            # Re-validate
            star_result = qa.check_star_format(role_bullets)
            if star_result.star_coverage >= star_threshold:
                self._logger.info(
                    f"STAR validation passed after {retry + 1} retry(s) "
                    f"({star_result.star_coverage:.0%} coverage)"
                )
                break

        if not star_result.passed:
            self._logger.warning(
                f"STAR validation still below threshold after {max_retries} retries "
                f"({star_result.star_coverage:.0%} coverage). Proceeding anyway."
            )

        return role_bullets

    def _identify_failing_bullets(self, role_bullets: RoleBullets, qa) -> list[int]:
        """Identify indices of bullets that fail STAR validation."""
        failing_indices = []

        for i, bullet in enumerate(role_bullets.bullets):
            # Check if bullet has explicit STAR components
            if bullet.has_star_components:
                continue

            # Check text-based detection
            has_situation = qa._has_situation(bullet.text)
            has_action = qa._has_action_with_skill(bullet.text)
            has_result = qa._has_result(bullet.text)

            if not (has_situation and has_action and has_result):
                failing_indices.append(i)

        return failing_indices

    def _get_missing_star_elements(self, bullet_text: str, qa) -> list[str]:
        """Get list of missing STAR elements for a bullet."""
        missing = []

        if not qa._has_situation(bullet_text):
            missing.append("situation/challenge opener")
        if not qa._has_action_with_skill(bullet_text):
            missing.append("action with skill/technology")
        if not qa._has_result(bullet_text):
            missing.append("quantified result")

        return missing

    async def _correct_bullet_star(
        self,
        bullet: GeneratedBullet,
        missing_elements: list[str],
        role: RoleData,
    ) -> Optional[str]:
        """
        Call LLM to correct a bullet's STAR format.

        Returns corrected bullet text or None if correction fails.
        """
        try:
            user_prompt = build_star_correction_user_prompt(
                failed_bullet=bullet.text,
                source_text=bullet.source_text,
                missing_elements=missing_elements,
                role_title=role.title,
                company=role.company,
            )

            # Use UnifiedLLM for STAR correction (no JSON needed)
            result = await self._llm.invoke(
                prompt=user_prompt,
                system=STAR_CORRECTION_SYSTEM_PROMPT,
                validate_json=False,  # Plain text response expected
            )

            if not result.success:
                raise ValueError(f"STAR correction failed: {result.error}")

            corrected = result.content.strip()

            # Clean up the response
            if corrected.startswith('"') and corrected.endswith('"'):
                corrected = corrected[1:-1]
            if corrected.startswith("•") or corrected.startswith("-"):
                corrected = corrected[1:].strip()

            self._logger.debug(f"STAR correction: '{bullet.text[:50]}...' -> '{corrected[:50]}...'")
            return corrected

        except Exception as e:
            self._logger.warning(f"Failed to correct bullet: {e}")
            return None


async def generate_all_roles_sequential(
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
            role_bullets = await generator.generate(
                role=role,
                extracted_jd=extracted_jd,
                career_context=career_context,
            )
            results.append(role_bullets)
            logger.info(f"Generated {role_bullets.bullet_count} bullets for {role.company}")

        except Exception as e:
            logger.error(f"Failed to generate for {role.company}: {e}")
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
                hard_skills=role.hard_skills,
                soft_skills=role.soft_skills,
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


async def generate_all_roles_with_star_enforcement(
    roles: List[RoleData],
    extracted_jd: ExtractedJD,
    generator: Optional[RoleGenerator] = None,
    max_retries: int = 2,
    star_threshold: float = 0.8,
) -> List[RoleBullets]:
    """
    Generate bullets for all roles with STAR format enforcement (GAP-005).

    This is the recommended method for production use as it ensures
    all bullets follow the STAR format for maximum impact.

    Args:
        roles: List of roles from CV loader
        extracted_jd: Structured JD intelligence
        generator: RoleGenerator instance (created if not provided)
        max_retries: Max correction attempts per role (default: 2)
        star_threshold: Minimum STAR coverage to pass (default: 0.8)

    Returns:
        List of RoleBullets with STAR-validated bullets
    """
    logger = get_logger(__name__)
    generator = generator or RoleGenerator()
    results = []

    target_role_category = extracted_jd.get("role_category", "staff_principal_engineer")
    total_roles = len(roles)

    logger.info(f"\n{'='*50}")
    logger.info("STAR-ENFORCED GENERATION (GAP-005)")
    logger.info(f"Processing {total_roles} roles with STAR validation")
    logger.info(f"STAR threshold: {star_threshold:.0%}")
    logger.info(f"{'='*50}")

    star_pass_count = 0
    star_retry_count = 0

    for i, role in enumerate(roles):
        logger.info(f"\n[Role {i+1}/{total_roles}] {role.company} - {role.title}")

        # Build career context for this role
        career_context = CareerContext.build(
            role_index=i,
            total_roles=total_roles,
            is_current=role.is_current,
            target_role_category=target_role_category,
        )

        try:
            role_bullets = await generator.generate_with_star_enforcement(
                role=role,
                extracted_jd=extracted_jd,
                career_context=career_context,
                max_retries=max_retries,
                star_threshold=star_threshold,
            )
            results.append(role_bullets)

            # Track STAR validation stats
            from src.layer6_v2.role_qa import RoleQA
            qa = RoleQA()
            star_result = qa.check_star_format(role_bullets)
            if star_result.passed:
                star_pass_count += 1
            logger.info(f"  Generated {role_bullets.bullet_count} bullets (STAR: {star_result.star_coverage:.0%})")

        except Exception as e:
            logger.error(f"  Failed: {e}")
            results.append(RoleBullets(
                role_id=role.id,
                company=role.company,
                title=role.title,
                period=role.period,
                location=role.location,
                bullets=[],
                word_count=0,
                keywords_integrated=[],
                hard_skills=role.hard_skills,
                soft_skills=role.soft_skills,
            ))

    # Summary
    total_bullets = sum(rb.bullet_count for rb in results)
    total_words = sum(rb.word_count for rb in results)
    logger.info(f"\n{'='*50}")
    logger.info("STAR-ENFORCED GENERATION COMPLETE")
    logger.info(f"Total bullets: {total_bullets}")
    logger.info(f"Total words: {total_words}")
    logger.info(f"Roles with bullets: {sum(1 for rb in results if rb.bullet_count > 0)}/{total_roles}")
    logger.info(f"STAR validation passed: {star_pass_count}/{total_roles} roles")
    logger.info(f"{'='*50}")

    return results


async def generate_all_roles_from_variants(
    roles: List[RoleData],
    extracted_jd: ExtractedJD,
    generator: Optional[RoleGenerator] = None,
    bullet_counts: Optional[Dict[str, int]] = None,
    fallback_to_llm: bool = True,
    jd_annotations: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> List[RoleBullets]:
    """
    Generate bullets for all roles using variant selection.

    Phase 4: Supports JD annotations for boost calculation and keyword injection.

    This is the recommended production method for CV generation:
    - Uses pre-written, interview-defensible variant text
    - Zero hallucination risk (all text from source)
    - Fast and deterministic (no LLM calls for variant selection)
    - Falls back to LLM generation if role has no variants
    - Applies annotation boost to prioritize relevant variants (Phase 4)

    Args:
        roles: List of roles from CV loader (should have enhanced_data)
        extracted_jd: Structured JD intelligence from Layer 1.4
        generator: RoleGenerator instance (created if not provided)
        bullet_counts: Optional dict mapping role_id to target bullet count
        fallback_to_llm: If True, use LLM for roles without variants (default: True)
        jd_annotations: Optional JDAnnotations for boost calculation (Phase 4)

    Returns:
        List of RoleBullets, one per role
    """
    logger = get_logger(__name__)
    # Create generator with progress callback if not provided
    if generator is None:
        generator = RoleGenerator(progress_callback=progress_callback)
    results = []

    target_role_category = extracted_jd.get("role_category", "staff_principal_engineer")
    total_roles = len(roles)

    logger.info(f"\n{'='*50}")
    logger.info("VARIANT-BASED GENERATION")
    logger.info(f"Processing {total_roles} roles")
    logger.info(f"Target role category: {target_role_category}")
    logger.info(f"Fallback to LLM: {fallback_to_llm}")
    logger.info(f"{'='*50}")

    variant_count = 0
    llm_count = 0
    skip_count = 0

    for i, role in enumerate(roles):
        logger.info(f"\n[Role {i+1}/{total_roles}] {role.company} - {role.title}")

        # Emit progress for frontend visibility
        if progress_callback:
            progress_callback(
                "role_progress",
                f"Generating bullets for role {i+1}/{total_roles}: {role.title}",
                {
                    "role_index": i + 1,
                    "total_roles": total_roles,
                    "role_title": role.title,
                    "company": role.company,
                },
            )

        # Determine target bullet count
        target_count = None
        if bullet_counts and role.id in bullet_counts:
            target_count = bullet_counts[role.id]

        # Build career context for fallback
        career_context = CareerContext.build(
            role_index=i,
            total_roles=total_roles,
            is_current=role.is_current,
            target_role_category=target_role_category,
        )

        try:
            if role.has_variants:
                # Use variant selection (Phase 4: with annotations)
                role_bullets = generator.generate_from_variants(
                    role=role,
                    extracted_jd=extracted_jd,
                    target_bullet_count=target_count,
                    jd_annotations=jd_annotations,
                )

                if role_bullets and role_bullets.bullet_count > 0:
                    results.append(role_bullets)
                    variant_count += 1
                    # Phase 4: Log annotation influence
                    ann_count = sum(1 for b in role_bullets.bullets if b.annotation_influenced)
                    ann_info = f" [{ann_count} boosted]" if ann_count > 0 else ""
                    logger.info(
                        f"  Selected {role_bullets.bullet_count} variants "
                        f"({role_bullets.word_count} words){ann_info}"
                    )
                    continue

            # Fallback to LLM if enabled
            if fallback_to_llm:
                role_bullets = await generator.generate(
                    role=role,
                    extracted_jd=extracted_jd,
                    career_context=career_context,
                    target_bullet_count=target_count,
                )
                results.append(role_bullets)
                llm_count += 1
                logger.info(
                    f"  LLM generated {role_bullets.bullet_count} bullets "
                    f"({role_bullets.word_count} words)"
                )
            else:
                # Skip role if no variants and no fallback
                skip_count += 1
                logger.warning(f"  Skipped - no variants and LLM fallback disabled")
                results.append(RoleBullets(
                    role_id=role.id,
                    company=role.company,
                    title=role.title,
                    period=role.period,
                    location=role.location,
                    bullets=[],
                    word_count=0,
                    keywords_integrated=[],
                    hard_skills=role.hard_skills,
                    soft_skills=role.soft_skills,
                ))

        except Exception as e:
            logger.error(f"  Failed: {e}")
            results.append(RoleBullets(
                role_id=role.id,
                company=role.company,
                title=role.title,
                period=role.period,
                location=role.location,
                bullets=[],
                word_count=0,
                keywords_integrated=[],
                hard_skills=role.hard_skills,
                soft_skills=role.soft_skills,
            ))

    # Summary
    total_bullets = sum(rb.bullet_count for rb in results)
    total_words = sum(rb.word_count for rb in results)
    logger.info(f"\n{'='*50}")
    logger.info("VARIANT-BASED GENERATION COMPLETE")
    logger.info(f"Total bullets: {total_bullets}")
    logger.info(f"Total words: {total_words}")
    logger.info(f"Roles processed: {total_roles}")
    logger.info(f"  - Variant selection: {variant_count}")
    logger.info(f"  - LLM fallback: {llm_count}")
    logger.info(f"  - Skipped: {skip_count}")
    logger.info(f"{'='*50}")

    return results
