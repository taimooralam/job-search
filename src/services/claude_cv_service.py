"""
Claude CLI-Based CV Generation Service.

Orchestrates multi-agent CV generation using Claude Code CLI with:
- Claude Sonnet 4.5 for role bullet generation (parallel processing)
- Claude Opus 4.5 for profile synthesis
- Claude Haiku 4.5 for ATS validation

Integrates:
- CARS framework for bullet structure
- Role-level keywords from cv-guide
- ATS optimization from ats-guide
- Persona, annotations, pain_points from annotation editor

Usage:
    from src.services.claude_cv_service import ClaudeCVService

    service = ClaudeCVService()
    result = await service.generate_cv(job_state, candidate_data)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.claude_cli import CLIResult, ClaudeCLI
from src.layer6_v2.prompts.cv_generation_prompts import (
    ROLE_KEYWORDS,
    build_role_bullet_prompt,
    build_profile_prompt,
    build_ats_validation_prompt,
    get_role_level_from_category,
)

logger = logging.getLogger(__name__)


@dataclass
class GeneratedBullet:
    """A single generated CV bullet with metadata."""

    text: str
    keywords_used: List[str] = field(default_factory=list)
    pain_point_addressed: Optional[str] = None


@dataclass
class GeneratedRole:
    """Generated bullets for a single role."""

    role_id: str
    company: str
    title: str
    period: str
    location: Optional[str]
    bullets: List[GeneratedBullet]
    keyword_coverage: Dict[str, int] = field(default_factory=dict)
    generation_time_ms: int = 0


@dataclass
class GeneratedProfile:
    """Generated CV profile section."""

    headline: str
    tagline: str
    key_achievements: List[str]
    core_competencies: Dict[str, List[str]]
    reasoning: Dict[str, str] = field(default_factory=dict)
    word_count: int = 0
    generation_time_ms: int = 0


@dataclass
class ATSValidationResult:
    """ATS validation results from Haiku agent."""

    ats_score: int
    missing_keywords: Dict[str, List[str]]
    acronyms_to_expand: List[Dict[str, str]]
    keyword_placement_issues: List[Dict[str, str]]
    red_flags: List[Dict[str, str]]
    role_level_check: Dict[str, Any]
    fixes: List[Dict[str, str]]
    summary: Dict[str, Any]
    validation_time_ms: int = 0


@dataclass
class CVResult:
    """Complete CV generation result."""

    profile: GeneratedProfile
    roles: List[GeneratedRole]
    ats_validation: Optional[ATSValidationResult]
    total_cost_usd: float
    total_time_ms: int
    models_used: Dict[str, str]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/MongoDB serialization."""
        return {
            "profile": {
                "headline": self.profile.headline,
                "tagline": self.profile.tagline,
                "key_achievements": self.profile.key_achievements,
                "core_competencies": self.profile.core_competencies,
                "word_count": self.profile.word_count,
            },
            "roles": [
                {
                    "role_id": role.role_id,
                    "company": role.company,
                    "title": role.title,
                    "period": role.period,
                    "bullets": [b.text for b in role.bullets],
                    "keyword_coverage": role.keyword_coverage,
                }
                for role in self.roles
            ],
            "ats_validation": {
                "ats_score": self.ats_validation.ats_score,
                "missing_keywords": self.ats_validation.missing_keywords,
                "fixes_suggested": len(self.ats_validation.fixes),
            }
            if self.ats_validation
            else None,
            "metadata": {
                "total_cost_usd": self.total_cost_usd,
                "total_time_ms": self.total_time_ms,
                "models_used": self.models_used,
                "generated_at": self.generated_at,
            },
        }


class ClaudeCVService:
    """
    Multi-agent CV generation using Claude Code CLI.

    Uses three-tier model architecture:
    - Sonnet (balanced): Role bullet generation (parallel)
    - Opus (quality): Profile synthesis
    - Haiku (fast): ATS validation

    Integrates prompts from cv_generation_prompts.py which embed:
    - CARS framework for bullet structure
    - Role-level keywords from cv-guide
    - ATS optimization from ats-guide
    """

    def __init__(
        self,
        timeout: int = 180,
        max_role_concurrent: int = 5,
        ats_threshold: int = 75,
    ):
        """
        Initialize the Claude CV service.

        Args:
            timeout: CLI timeout in seconds (default 180s)
            max_role_concurrent: Max concurrent role generations (default 5)
            ats_threshold: ATS score threshold for fixes (default 75)
        """
        # Three-tier CLI setup
        self.role_cli = ClaudeCLI(tier="balanced", timeout=timeout)  # Sonnet
        self.profile_cli = ClaudeCLI(tier="quality", timeout=timeout)  # Opus
        self.validator_cli = ClaudeCLI(tier="fast", timeout=60)  # Haiku

        self.timeout = timeout
        self.max_role_concurrent = max_role_concurrent
        self.ats_threshold = ats_threshold

        # Track costs
        self._total_cost = 0.0

    async def generate_cv(
        self,
        job_state: Dict[str, Any],
        candidate_data: Dict[str, Any],
    ) -> CVResult:
        """
        Generate complete CV using multi-agent pipeline.

        Pipeline:
        1. Generate role bullets in parallel (Sonnet)
        2. Generate profile (Opus)
        3. Validate ATS compliance (Haiku)
        4. Apply fixes if needed

        Args:
            job_state: Job state dict with extracted_jd, jd_annotations, pain_points
            candidate_data: Candidate data dict with roles, name, etc.

        Returns:
            CVResult with profile, roles, and ATS validation
        """
        start_time = datetime.utcnow()
        self._total_cost = 0.0

        # Extract context from job state
        extracted_jd = job_state.get("extracted_jd") or {}
        jd_annotations = job_state.get("jd_annotations") or {}
        pain_points = job_state.get("pain_points") or []

        # Extract persona and annotations context
        synthesized_persona = jd_annotations.get("synthesized_persona", {})
        persona_statement = synthesized_persona.get(
            "persona_statement",
            "Senior engineering leader with expertise in building high-performing teams",
        )
        primary_identity = synthesized_persona.get(
            "primary_identity", "Engineering Leader"
        )
        annotations = jd_annotations.get("annotations", [])

        # Get core strengths from candidate profile
        candidate_profile = job_state.get("candidate_profile") or {}
        core_strengths = candidate_profile.get(
            "core_strengths",
            ["Engineering leadership", "Technical strategy", "Team development"],
        )

        # Detect role level
        role_category = extracted_jd.get("role_category", "engineering_manager")
        role_level = get_role_level_from_category(role_category)

        # Extract priority keywords
        priority_keywords = self._extract_priority_keywords(
            extracted_jd, jd_annotations
        )

        logger.info(
            f"Starting CV generation - role_level: {role_level}, "
            f"roles: {len(candidate_data.get('roles', []))}"
        )

        # Step 1: Generate role bullets in parallel (Sonnet)
        roles = candidate_data.get("roles", [])
        generated_roles = await self._generate_roles_parallel(
            roles=roles,
            persona_statement=persona_statement,
            core_strengths=core_strengths,
            pain_points=pain_points,
            role_level=role_level,
            priority_keywords=priority_keywords,
            annotations=annotations,
        )

        # Step 2: Generate profile (Opus)
        role_bullets_summary = self._summarize_role_bullets(generated_roles)
        profile = await self._generate_profile(
            persona_statement=persona_statement,
            primary_identity=primary_identity,
            core_strengths=core_strengths,
            role_bullets_summary=role_bullets_summary,
            priority_keywords=priority_keywords,
            pain_points=pain_points,
            role_level=role_level,
        )

        # Step 3: Validate ATS compliance (Haiku)
        cv_text = self._assemble_cv_text(profile, generated_roles)
        must_have = self._get_must_have_keywords(jd_annotations)
        nice_to_have = self._get_nice_to_have_keywords(jd_annotations)

        ats_validation = await self._validate_ats(
            cv_text=cv_text,
            must_have_keywords=must_have,
            nice_to_have_keywords=nice_to_have,
            role_level=role_level,
        )

        # Step 4: Apply fixes if needed (future: could improve here)
        if ats_validation and ats_validation.ats_score < self.ats_threshold:
            logger.warning(
                f"ATS score {ats_validation.ats_score} below threshold {self.ats_threshold}"
            )
            # Future: Could re-generate with fixes

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return CVResult(
            profile=profile,
            roles=generated_roles,
            ats_validation=ats_validation,
            total_cost_usd=self._total_cost,
            total_time_ms=duration_ms,
            models_used={
                "role_generation": "sonnet",
                "profile_synthesis": "opus",
                "ats_validation": "haiku",
            },
            generated_at=datetime.utcnow().isoformat(),
        )

    async def _generate_roles_parallel(
        self,
        roles: List[Dict[str, Any]],
        persona_statement: str,
        core_strengths: List[str],
        pain_points: List[str],
        role_level: str,
        priority_keywords: List[str],
        annotations: List[Dict[str, Any]],
    ) -> List[GeneratedRole]:
        """
        Generate bullets for all roles in parallel using Sonnet.

        Args:
            roles: List of role dictionaries from candidate data
            persona_statement: Synthesized persona
            core_strengths: Key strengths
            pain_points: JD pain points
            role_level: Target role level
            priority_keywords: Must-include keywords
            annotations: JD annotations

        Returns:
            List of GeneratedRole with bullets
        """
        logger.info(f"Generating bullets for {len(roles)} roles in parallel")

        # Use semaphore for controlled concurrency
        semaphore = asyncio.Semaphore(self.max_role_concurrent)

        async def generate_role(role: Dict[str, Any]) -> GeneratedRole:
            async with semaphore:
                return await self._generate_single_role(
                    role=role,
                    persona_statement=persona_statement,
                    core_strengths=core_strengths,
                    pain_points=pain_points,
                    role_level=role_level,
                    priority_keywords=priority_keywords,
                    annotations=annotations,
                )

        # Run all role generations in parallel
        tasks = [generate_role(role) for role in roles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        generated_roles = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error generating role {i}: {result}")
                # Create fallback role
                role = roles[i]
                generated_roles.append(
                    self._create_fallback_role(role)
                )
            else:
                generated_roles.append(result)

        return generated_roles

    async def _generate_single_role(
        self,
        role: Dict[str, Any],
        persona_statement: str,
        core_strengths: List[str],
        pain_points: List[str],
        role_level: str,
        priority_keywords: List[str],
        annotations: List[Dict[str, Any]],
    ) -> GeneratedRole:
        """Generate bullets for a single role using Sonnet."""
        start_time = datetime.utcnow()

        # Extract role data
        role_title = role.get("title", "Unknown")
        role_company = role.get("company", "Unknown")
        achievements = role.get("achievements", [])
        period = role.get("period", "")
        location = role.get("location")

        # Build prompt
        prompt = build_role_bullet_prompt(
            role_title=role_title,
            role_company=role_company,
            role_achievements=achievements,
            persona_statement=persona_statement,
            core_strengths=core_strengths,
            pain_points=pain_points,
            role_level=role_level,
            priority_keywords=priority_keywords,
            annotations=annotations,
        )

        # Invoke Sonnet
        job_id = f"role-{role_company[:10]}-{role_title[:10]}".replace(" ", "-").lower()
        result = self.role_cli.invoke(
            prompt=prompt,
            job_id=job_id,
            max_turns=1,
            validate_json=True,
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if result.cost_usd:
            self._total_cost += result.cost_usd

        if not result.success:
            logger.error(f"Role generation failed for {role_company}: {result.error}")
            return self._create_fallback_role(role, duration_ms)

        # Parse result
        return self._parse_role_result(
            result=result,
            role=role,
            duration_ms=duration_ms,
        )

    def _parse_role_result(
        self,
        result: CLIResult,
        role: Dict[str, Any],
        duration_ms: int,
    ) -> GeneratedRole:
        """Parse CLI result into GeneratedRole."""
        try:
            data = result.result
            bullets_data = data.get("role_bullets", [])

            bullets = []
            for b in bullets_data:
                bullets.append(
                    GeneratedBullet(
                        text=b.get("text", ""),
                        keywords_used=b.get("keywords_used", []),
                        pain_point_addressed=b.get("pain_point_addressed"),
                    )
                )

            return GeneratedRole(
                role_id=f"{role.get('company', '')}_{role.get('title', '')}".replace(
                    " ", "_"
                ).lower(),
                company=role.get("company", "Unknown"),
                title=role.get("title", "Unknown"),
                period=role.get("period", ""),
                location=role.get("location"),
                bullets=bullets,
                keyword_coverage=data.get("keyword_coverage", {}),
                generation_time_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Error parsing role result: {e}")
            return self._create_fallback_role(role, duration_ms)

    def _create_fallback_role(
        self, role: Dict[str, Any], duration_ms: int = 0
    ) -> GeneratedRole:
        """Create fallback role when generation fails."""
        achievements = role.get("achievements", [])
        bullets = [
            GeneratedBullet(text=a, keywords_used=[], pain_point_addressed=None)
            for a in achievements[:5]
        ]

        return GeneratedRole(
            role_id=f"{role.get('company', '')}_{role.get('title', '')}".replace(
                " ", "_"
            ).lower(),
            company=role.get("company", "Unknown"),
            title=role.get("title", "Unknown"),
            period=role.get("period", ""),
            location=role.get("location"),
            bullets=bullets,
            keyword_coverage={},
            generation_time_ms=duration_ms,
        )

    async def _generate_profile(
        self,
        persona_statement: str,
        primary_identity: str,
        core_strengths: List[str],
        role_bullets_summary: str,
        priority_keywords: List[str],
        pain_points: List[str],
        role_level: str,
    ) -> GeneratedProfile:
        """Generate profile section using Opus."""
        start_time = datetime.utcnow()

        prompt = build_profile_prompt(
            persona_statement=persona_statement,
            primary_identity=primary_identity,
            core_strengths=core_strengths,
            role_bullets_summary=role_bullets_summary,
            priority_keywords=priority_keywords,
            pain_points=pain_points,
            target_role_level=role_level,
        )

        result = self.profile_cli.invoke(
            prompt=prompt,
            job_id="profile-synthesis",
            max_turns=1,
            validate_json=True,
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if result.cost_usd:
            self._total_cost += result.cost_usd

        if not result.success:
            logger.error(f"Profile generation failed: {result.error}")
            return self._create_fallback_profile(
                persona_statement, core_strengths, duration_ms
            )

        return self._parse_profile_result(result, duration_ms)

    def _parse_profile_result(
        self, result: CLIResult, duration_ms: int
    ) -> GeneratedProfile:
        """Parse CLI result into GeneratedProfile."""
        try:
            data = result.result

            headline = data.get("headline", "Engineering Leader")
            tagline = data.get("tagline", "")
            key_achievements = data.get("key_achievements", [])
            core_competencies = data.get("core_competencies", {})
            reasoning = data.get("reasoning", {})

            # Calculate word count
            text = f"{headline} {tagline} {' '.join(key_achievements)}"
            word_count = len(text.split())

            return GeneratedProfile(
                headline=headline,
                tagline=tagline,
                key_achievements=key_achievements,
                core_competencies=core_competencies,
                reasoning=reasoning,
                word_count=word_count,
                generation_time_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Error parsing profile result: {e}")
            return self._create_fallback_profile("", [], duration_ms)

    def _create_fallback_profile(
        self,
        persona_statement: str,
        core_strengths: List[str],
        duration_ms: int,
    ) -> GeneratedProfile:
        """Create fallback profile when generation fails."""
        return GeneratedProfile(
            headline="Senior Engineering Leader",
            tagline=persona_statement[:200] if persona_statement else "Engineering professional with proven track record",
            key_achievements=core_strengths[:5],
            core_competencies={"leadership": core_strengths[:3]},
            reasoning={"fallback": "Generated from fallback due to error"},
            word_count=len(persona_statement.split()) if persona_statement else 0,
            generation_time_ms=duration_ms,
        )

    async def _validate_ats(
        self,
        cv_text: str,
        must_have_keywords: List[str],
        nice_to_have_keywords: List[str],
        role_level: str,
    ) -> Optional[ATSValidationResult]:
        """Validate CV against ATS requirements using Haiku."""
        start_time = datetime.utcnow()

        prompt = build_ats_validation_prompt(
            cv_text=cv_text,
            must_have_keywords=must_have_keywords,
            nice_to_have_keywords=nice_to_have_keywords,
            target_role_level=role_level,
        )

        result = self.validator_cli.invoke(
            prompt=prompt,
            job_id="ats-validation",
            max_turns=1,
            validate_json=True,
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if result.cost_usd:
            self._total_cost += result.cost_usd

        if not result.success:
            logger.warning(f"ATS validation failed: {result.error}")
            return None

        try:
            data = result.result
            return ATSValidationResult(
                ats_score=data.get("ats_score", 0),
                missing_keywords=data.get("missing_keywords", {}),
                acronyms_to_expand=data.get("acronyms_to_expand", []),
                keyword_placement_issues=data.get("keyword_placement_issues", []),
                red_flags=data.get("red_flags", []),
                role_level_check=data.get("role_level_check", {}),
                fixes=data.get("fixes", []),
                summary=data.get("summary", {}),
                validation_time_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"Error parsing ATS validation result: {e}")
            return None

    def _extract_priority_keywords(
        self,
        extracted_jd: Dict[str, Any],
        jd_annotations: Dict[str, Any],
    ) -> List[str]:
        """Extract priority keywords from JD and annotations."""
        keywords = []

        # From extracted JD
        keywords.extend(extracted_jd.get("top_keywords", [])[:10])

        # From annotations (must-have requirements)
        annotations = jd_annotations.get("annotations", [])
        for ann in annotations:
            if ann.get("requirement_type") == "must_have":
                skill = ann.get("matching_skill", "")
                if skill:
                    keywords.append(skill)

        return list(set(keywords))[:15]

    def _get_must_have_keywords(self, jd_annotations: Dict[str, Any]) -> List[str]:
        """Get must-have keywords from annotations."""
        keywords = []
        annotations = jd_annotations.get("annotations", [])
        for ann in annotations:
            if ann.get("requirement_type") == "must_have":
                skill = ann.get("matching_skill", "")
                if skill:
                    keywords.append(skill)
                # Also include suggested keywords
                keywords.extend(ann.get("suggested_keywords", [])[:2])
        return list(set(keywords))[:15]

    def _get_nice_to_have_keywords(self, jd_annotations: Dict[str, Any]) -> List[str]:
        """Get nice-to-have keywords from annotations."""
        keywords = []
        annotations = jd_annotations.get("annotations", [])
        for ann in annotations:
            if ann.get("requirement_type") == "nice_to_have":
                skill = ann.get("matching_skill", "")
                if skill:
                    keywords.append(skill)
        return list(set(keywords))[:10]

    def _summarize_role_bullets(self, roles: List[GeneratedRole]) -> str:
        """Summarize all role bullets for profile generation."""
        summary_parts = []
        for role in roles:
            role_summary = f"{role.title} at {role.company}:\n"
            for bullet in role.bullets[:3]:  # Top 3 bullets per role
                role_summary += f"- {bullet.text}\n"
            summary_parts.append(role_summary)
        return "\n".join(summary_parts)

    def _assemble_cv_text(
        self, profile: GeneratedProfile, roles: List[GeneratedRole]
    ) -> str:
        """Assemble full CV text for validation."""
        lines = []

        # Profile
        lines.append(f"# {profile.headline}")
        lines.append(profile.tagline)
        lines.append("")

        # Key achievements
        lines.append("## KEY ACHIEVEMENTS")
        for achievement in profile.key_achievements:
            lines.append(f"- {achievement}")
        lines.append("")

        # Core competencies
        lines.append("## CORE COMPETENCIES")
        for category, skills in profile.core_competencies.items():
            lines.append(f"{category.title()}: {', '.join(skills)}")
        lines.append("")

        # Roles
        lines.append("## PROFESSIONAL EXPERIENCE")
        for role in roles:
            lines.append(f"### {role.company} - {role.title}")
            lines.append(role.period)
            for bullet in role.bullets:
                lines.append(f"- {bullet.text}")
            lines.append("")

        return "\n".join(lines)


# Convenience function for direct usage
async def generate_cv_with_claude(
    job_state: Dict[str, Any],
    candidate_data: Dict[str, Any],
    timeout: int = 180,
) -> CVResult:
    """
    Generate CV using Claude multi-agent pipeline.

    Convenience wrapper around ClaudeCVService.

    Args:
        job_state: Job state dictionary
        candidate_data: Candidate data dictionary
        timeout: CLI timeout in seconds

    Returns:
        CVResult with generated CV
    """
    service = ClaudeCVService(timeout=timeout)
    return await service.generate_cv(job_state, candidate_data)
