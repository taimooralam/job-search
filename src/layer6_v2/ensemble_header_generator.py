"""
Ensemble Header Generator for Tiered CV Profile Generation.

Implements tiered ensemble generation:
- Gold (85-100%): 3 sequential personas → synthesis → validation (flag ungrounded)
- Silver (70-84%): 2 sequential personas → synthesis
- Bronze/Skip (<70%): 1-pass single-shot (delegates to HeaderGenerator)

Research Foundation:
- 625 hiring managers surveyed
- Eye-tracking: first 7.4 seconds determine continue/reject
- Exact job title: 10.6x more likely to get interviews
- Optimal summary: 100-150 words, 3-5 sentences

Ensemble Strategy:
- METRIC persona: Maximize quantified achievements
- NARRATIVE persona: Compelling career transformation story
- KEYWORD persona: ATS optimization, JD terminology mirroring
- Synthesis: Combine best elements from all passes
- Validation: Flag (don't remove) ungrounded content for review
"""

import re
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.logger import get_logger
from src.common.config import Config
from src.common.llm_factory import create_tracked_llm_for_model
from src.common.tiering import (
    ProcessingTier,
    TierConfig,
    get_tier_config,
    get_tier_from_fit_score,
    CLAUDE_STANDARD,
)
from src.layer6_v2.header_generator import HeaderGenerator, ProfileResponse
from src.layer6_v2.types import (
    StitchedCV,
    ProfileOutput,
    SkillsSection,
    HeaderOutput,
    ValidationResult,
    ValidationFlags,
    EnsembleMetadata,
    HeaderGenerationContext,
)
from src.layer6_v2.prompts.header_generation import (
    METRIC_PERSONA_SYSTEM_PROMPT,
    NARRATIVE_PERSONA_SYSTEM_PROMPT,
    KEYWORD_PERSONA_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    build_persona_user_prompt,
    build_synthesis_user_prompt,
)


class PersonaType(Enum):
    """Persona types for ensemble generation."""
    METRIC = "metric"
    NARRATIVE = "narrative"
    KEYWORD = "keyword"


@dataclass
class PersonaProfileResult:
    """Result from a single persona-based generation pass."""
    persona: PersonaType
    profile: ProfileOutput
    raw_response: ProfileResponse
    metrics_found: List[str] = field(default_factory=list)
    keywords_found: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for synthesis (hybrid format)."""
        return {
            "persona": self.persona.value,
            "headline": self.profile.headline,
            "tagline": self.profile.tagline,              # NEW: Hybrid format
            "key_achievements": self.profile.key_achievements,  # NEW: Hybrid format
            "core_competencies": self.profile.core_competencies,
            "highlights_used": self.metrics_found,
            "keywords_integrated": self.keywords_found,
            # Keep narrative for backward compatibility
            "narrative": self.profile.narrative,
        }


class EnsembleHeaderGenerator:
    """
    Tiered ensemble generator for CV profiles.

    Uses multiple persona-based passes for high-fit jobs (Gold/Silver),
    falling back to single-shot for lower tiers (Bronze/Skip).
    """

    # Persona configurations by tier
    TIER_PERSONAS = {
        ProcessingTier.GOLD: [PersonaType.METRIC, PersonaType.NARRATIVE, PersonaType.KEYWORD],
        ProcessingTier.SILVER: [PersonaType.METRIC, PersonaType.KEYWORD],
        ProcessingTier.BRONZE: [],  # Uses single-shot
        ProcessingTier.SKIP: [],    # Uses single-shot
    }

    def __init__(
        self,
        tier_config: TierConfig,
        skill_whitelist: Optional[Dict[str, List[str]]] = None,
        temperature: float = 0.3,
        annotation_context: Optional[HeaderGenerationContext] = None,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the ensemble header generator.

        Args:
            tier_config: Tier configuration with model assignments
            skill_whitelist: Master-CV skills for grounding validation
            temperature: LLM temperature for generation
            annotation_context: Phase 4.5 - HeaderGenerationContext with annotation priorities
            jd_annotations: Raw jd_annotations dict containing synthesized_persona
                           for persona-framed profile generation.
        """
        self._logger = get_logger(__name__)
        self.tier_config = tier_config
        self._skill_whitelist = skill_whitelist or {}
        self.temperature = temperature

        # Store jd_annotations for persona access
        self._jd_annotations = jd_annotations

        # Phase 4.5: Store annotation context
        self._annotation_context = annotation_context
        if annotation_context and annotation_context.has_annotations:
            self._logger.info(
                f"Using annotation context: {len(annotation_context.priorities)} priorities, "
                f"{len(annotation_context.must_have_priorities)} must-haves"
            )

        # Create LLMs for generation and synthesis
        self._generation_llm = self._create_llm(tier_config.cv_model)
        self._synthesis_llm = self._create_llm(CLAUDE_STANDARD)  # Always use cheaper model

        # Fallback generator for Bronze/Skip tiers (pass annotation context and persona)
        self._fallback_generator = HeaderGenerator(
            model=tier_config.cv_model,
            skill_whitelist=skill_whitelist,
            annotation_context=annotation_context,
            jd_annotations=jd_annotations,
        )

        self._logger.info(
            f"EnsembleHeaderGenerator initialized: tier={tier_config.tier.value}, "
            f"gen_model={tier_config.cv_model}, synth_model={CLAUDE_STANDARD}"
        )

    def _create_llm(self, model: str):
        """Create an LLM instance with tracking, auto-detecting provider from model name."""
        return create_tracked_llm_for_model(
            model=model,
            temperature=self.temperature,
            layer="layer6_v2_ensemble",
        )

    def generate(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_data: Dict,
    ) -> HeaderOutput:
        """
        Generate CV header using tier-appropriate strategy.

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted job description
            candidate_data: Candidate metadata

        Returns:
            HeaderOutput with profile, skills, and ensemble metadata
        """
        start_time = time.time()
        tier = self.tier_config.tier

        self._logger.info(f"Generating header with tier={tier.value}")

        # Route to appropriate strategy
        if tier == ProcessingTier.GOLD:
            header = self._generate_gold_tier(stitched_cv, extracted_jd, candidate_data)
            passes = 3
            personas = [p.value for p in self.TIER_PERSONAS[tier]]
            synthesis_applied = True
            validation_flags = self._validate_and_flag(
                header.profile, stitched_cv, self._skill_whitelist
            )
        elif tier == ProcessingTier.SILVER:
            header = self._generate_silver_tier(stitched_cv, extracted_jd, candidate_data)
            passes = 2
            personas = [p.value for p in self.TIER_PERSONAS[tier]]
            synthesis_applied = True
            validation_flags = None  # No validation for Silver
        else:
            # Bronze/Skip: Use existing single-shot
            self._logger.info("Using single-shot generation for Bronze/Skip tier")
            header = self._fallback_generator.generate(
                stitched_cv, extracted_jd, candidate_data
            )
            passes = 1
            personas = []
            synthesis_applied = False
            validation_flags = None

        # Add ensemble metadata
        generation_time_ms = int((time.time() - start_time) * 1000)
        header.ensemble_metadata = EnsembleMetadata(
            tier_used=tier.value,
            passes_executed=passes,
            personas_used=personas,
            synthesis_model=CLAUDE_STANDARD if synthesis_applied else "",
            synthesis_applied=synthesis_applied,
            validation_flags=validation_flags,
            generation_time_ms=generation_time_ms,
        )

        self._logger.info(
            f"Header generation complete: tier={tier.value}, "
            f"passes={passes}, time={generation_time_ms}ms"
        )

        return header

    def _generate_gold_tier(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_data: Dict,
    ) -> HeaderOutput:
        """
        Gold tier: 3-pass ensemble + synthesis + validation.

        Sequential passes through all three personas, then synthesis.
        """
        self._logger.info("Gold tier: Running 3-pass ensemble generation")
        candidate_name = candidate_data.get("name", "Candidate")

        # Run 3 persona passes sequentially
        persona_results = []
        for persona in self.TIER_PERSONAS[ProcessingTier.GOLD]:
            self._logger.info(f"  Running {persona.value} persona...")
            result = self._generate_with_persona(
                persona, stitched_cv, extracted_jd, candidate_name
            )
            persona_results.append(result)

        # Synthesize best elements
        self._logger.info("  Running synthesis...")
        synthesized_profile = self._synthesize_profiles(
            persona_results, extracted_jd, candidate_data
        )

        # Generate skills using taxonomy-based approach (from fallback generator)
        skills_sections = self._fallback_generator.generate_skills(
            stitched_cv, extracted_jd
        )

        return HeaderOutput(
            profile=synthesized_profile,
            skills_sections=skills_sections,
            education=self._extract_education(candidate_data),
            contact_info=self._extract_contact_info(candidate_data),
            certifications=candidate_data.get("certifications", []),
            languages=candidate_data.get("languages", []),
        )

    def _generate_silver_tier(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_data: Dict,
    ) -> HeaderOutput:
        """
        Silver tier: 2-pass ensemble + synthesis (no validation).

        Sequential passes through metric and keyword personas, then synthesis.
        """
        self._logger.info("Silver tier: Running 2-pass ensemble generation")
        candidate_name = candidate_data.get("name", "Candidate")

        # Run 2 persona passes sequentially
        persona_results = []
        for persona in self.TIER_PERSONAS[ProcessingTier.SILVER]:
            self._logger.info(f"  Running {persona.value} persona...")
            result = self._generate_with_persona(
                persona, stitched_cv, extracted_jd, candidate_name
            )
            persona_results.append(result)

        # Synthesize best elements
        self._logger.info("  Running synthesis...")
        synthesized_profile = self._synthesize_profiles(
            persona_results, extracted_jd, candidate_data
        )

        # Generate skills
        skills_sections = self._fallback_generator.generate_skills(
            stitched_cv, extracted_jd
        )

        return HeaderOutput(
            profile=synthesized_profile,
            skills_sections=skills_sections,
            education=self._extract_education(candidate_data),
            contact_info=self._extract_contact_info(candidate_data),
            certifications=candidate_data.get("certifications", []),
            languages=candidate_data.get("languages", []),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _generate_with_persona(
        self,
        persona: PersonaType,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_name: str,
    ) -> PersonaProfileResult:
        """
        Generate profile with specific persona emphasis.

        Args:
            persona: The persona type (METRIC, NARRATIVE, or KEYWORD)
            stitched_cv: Stitched experience section
            extracted_jd: Extracted job description
            candidate_name: Name of the candidate

        Returns:
            PersonaProfileResult with generated profile
        """
        # Select system prompt based on persona
        prompt_map = {
            PersonaType.METRIC: METRIC_PERSONA_SYSTEM_PROMPT,
            PersonaType.NARRATIVE: NARRATIVE_PERSONA_SYSTEM_PROMPT,
            PersonaType.KEYWORD: KEYWORD_PERSONA_SYSTEM_PROMPT,
        }
        system_prompt = prompt_map[persona]

        # Extract inputs from stitched CV
        all_bullets = [b for role in stitched_cv.roles for b in role.bullets]
        metrics = self._extract_metrics_from_bullets(all_bullets)
        years_experience = self._calculate_years_experience(extracted_jd)

        # Build user prompt
        user_prompt = build_persona_user_prompt(
            persona=persona.value,
            candidate_name=candidate_name,
            job_title=extracted_jd.get("title", "Engineering Leader"),
            role_category=extracted_jd.get("role_category", "engineering_manager"),
            top_keywords=extracted_jd.get("top_keywords", []),
            experience_bullets=all_bullets[:20],
            metrics=metrics,
            years_experience=years_experience,
            jd_pain_points=extracted_jd.get("pain_points", []),
            candidate_differentiators=extracted_jd.get("differentiators", []),
        )

        # Call LLM with structured output
        structured_llm = self._generation_llm.with_structured_output(ProfileResponse)
        response = structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])

        # Convert to ProfileOutput (hybrid format)
        profile = ProfileOutput(
            headline=response.headline,
            tagline=response.tagline,                    # NEW: Hybrid format
            key_achievements=response.key_achievements,  # NEW: Hybrid format
            core_competencies=response.core_competencies,
            highlights_used=response.highlights_used,
            keywords_integrated=response.keywords_integrated,
            exact_title_used=response.exact_title_used,
            answers_who=response.answers_who,
            answers_what_problems=response.answers_what_problems,
            answers_proof=response.answers_proof,
            answers_why_you=response.answers_why_you,
            # Keep narrative for backward compatibility (use tagline)
            narrative=response.tagline,
        )

        return PersonaProfileResult(
            persona=persona,
            profile=profile,
            raw_response=response,
            metrics_found=response.highlights_used,
            keywords_found=response.keywords_integrated,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _synthesize_profiles(
        self,
        persona_results: List[PersonaProfileResult],
        extracted_jd: Dict,
        candidate_data: Dict,
    ) -> ProfileOutput:
        """
        Combine best elements from multiple hybrid executive summary outputs.

        Args:
            persona_results: Results from persona passes
            extracted_jd: Extracted job description
            candidate_data: Candidate metadata

        Returns:
            Synthesized ProfileOutput with hybrid format
        """
        years_experience = self._calculate_years_experience(extracted_jd)

        # Build synthesis prompt (now uses hybrid format)
        persona_outputs = [r.to_dict() for r in persona_results]
        user_prompt = build_synthesis_user_prompt(
            persona_outputs=persona_outputs,
            job_title=extracted_jd.get("title", "Engineering Leader"),
            top_keywords=extracted_jd.get("top_keywords", []),
            years_experience=years_experience,
        )

        # Call synthesis LLM (cheaper model)
        structured_llm = self._synthesis_llm.with_structured_output(ProfileResponse)
        response = structured_llm.invoke([
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        # Merge all metrics and keywords from all personas
        all_metrics = set()
        all_keywords = set()
        for result in persona_results:
            all_metrics.update(result.metrics_found)
            all_keywords.update(result.keywords_found)

        return ProfileOutput(
            headline=response.headline,
            tagline=response.tagline,                    # NEW: Hybrid format
            key_achievements=response.key_achievements,  # NEW: Hybrid format
            core_competencies=response.core_competencies,
            highlights_used=list(all_metrics),
            keywords_integrated=list(all_keywords),
            exact_title_used=response.exact_title_used,
            answers_who=response.answers_who,
            answers_what_problems=response.answers_what_problems,
            answers_proof=response.answers_proof,
            answers_why_you=response.answers_why_you,
            # Keep narrative for backward compatibility (use tagline)
            narrative=response.tagline,
        )

    def _validate_and_flag(
        self,
        profile: ProfileOutput,
        stitched_cv: StitchedCV,
        skill_whitelist: Dict[str, List[str]],
    ) -> ValidationFlags:
        """
        Validate content and flag ungrounded claims (flag & keep approach).

        Args:
            profile: The synthesized profile
            stitched_cv: Source of truth for grounding
            skill_whitelist: Allowed skills from master CV

        Returns:
            ValidationFlags with flagged content
        """
        self._logger.info("Validating and flagging ungrounded content...")

        # Collect all bullets for grounding check
        all_bullets = [b for role in stitched_cv.roles for b in role.bullets]
        all_text_lower = " ".join(all_bullets).lower()

        # Build whitelist set
        whitelist_skills = set()
        for category in skill_whitelist.values():
            if isinstance(category, list):
                whitelist_skills.update(s.lower() for s in category)

        # 1. Check metrics grounding
        ungrounded_metrics = []
        for metric in profile.highlights_used:
            # Extract numeric parts
            numbers = re.findall(r'\d+(?:\.\d+)?', metric)
            metric_grounded = False
            for num in numbers:
                if num in " ".join(all_bullets):
                    metric_grounded = True
                    break
            if not metric_grounded and numbers:
                ungrounded_metrics.append(metric)

        # 2. Check skills/keywords grounding
        ungrounded_skills = []
        for kw in profile.keywords_integrated:
            kw_lower = kw.lower()
            if kw_lower not in whitelist_skills and kw_lower not in all_text_lower:
                ungrounded_skills.append(kw)

        # 3. Check narrative for potential ungrounded claims
        flagged_claims = []
        # Look for large numbers in narrative that aren't in bullets
        narrative_numbers = re.findall(r'\$?\d+(?:,\d{3})*(?:\.\d+)?[MKmk]?(?:\s*(?:million|billion|thousand))?', profile.narrative)
        for num in narrative_numbers:
            # Normalize the number for comparison
            num_clean = num.replace(',', '').replace('$', '')
            found = False
            for bullet in all_bullets:
                if num_clean in bullet.replace(',', '').replace('$', ''):
                    found = True
                    break
            if not found:
                flagged_claims.append(f"Metric '{num}' may not be grounded")

        flags = ValidationFlags(
            ungrounded_metrics=ungrounded_metrics,
            ungrounded_skills=ungrounded_skills,
            flagged_claims=flagged_claims,
        )

        if flags.has_flags:
            self._logger.warning(
                f"Validation flags: {flags.total_flags} items flagged "
                f"(metrics={len(ungrounded_metrics)}, skills={len(ungrounded_skills)}, "
                f"claims={len(flagged_claims)})"
            )
        else:
            self._logger.info("Validation passed: all content grounded")

        return flags

    def _extract_metrics_from_bullets(self, bullets: List[str]) -> List[str]:
        """Extract quantified metrics from bullets for profile generation."""
        metrics = []
        patterns = [
            r'\$[\d,]+(?:\.\d+)?[MKBmkb]?',  # Dollar amounts
            r'\d+(?:\.\d+)?%',                # Percentages
            r'\d+x',                          # Multipliers
            r'team of \d+',                   # Team sizes
            r'\d+(?:,\d{3})+',                # Large numbers
        ]

        for bullet in bullets:
            for pattern in patterns:
                matches = re.findall(pattern, bullet, re.IGNORECASE)
                for match in matches:
                    # Add context around the metric
                    context = bullet[:100] if len(bullet) > 100 else bullet
                    metric_with_context = f"{match} ({context}...)" if len(bullet) > 100 else f"{match} ({context})"
                    if metric_with_context not in metrics:
                        metrics.append(metric_with_context)

        return metrics[:10]  # Limit to top 10 metrics

    def _calculate_years_experience(self, extracted_jd: Dict) -> int:
        """Calculate years of experience from JD or default."""
        # Try to get from JD first
        if "years_required" in extracted_jd:
            return extracted_jd["years_required"]
        # Default to 10+ for senior roles
        return 10

    def _extract_education(self, candidate_data: Dict) -> List[str]:
        """Extract education entries from candidate data."""
        education = []
        if candidate_data.get("education_masters"):
            education.append(candidate_data["education_masters"])
        if candidate_data.get("education_bachelors"):
            education.append(candidate_data["education_bachelors"])
        return education

    def _extract_contact_info(self, candidate_data: Dict) -> Dict[str, str]:
        """Extract contact info from candidate data."""
        return {
            "name": candidate_data.get("name", ""),
            "email": candidate_data.get("email", ""),
            "phone": candidate_data.get("phone", ""),
            "linkedin": candidate_data.get("linkedin", ""),
            "location": candidate_data.get("location", ""),
        }


def generate_ensemble_header(
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_data: Dict,
    fit_score: Optional[int] = None,
    tier_override: Optional[str] = None,
    skill_whitelist: Optional[Dict[str, List[str]]] = None,
    annotation_context: Optional[HeaderGenerationContext] = None,
    jd_annotations: Optional[Dict[str, Any]] = None,
) -> HeaderOutput:
    """
    Convenience function for ensemble header generation.

    Args:
        stitched_cv: Stitched experience section
        extracted_jd: Extracted job description
        candidate_data: Candidate metadata
        fit_score: Job fit score (0-100) for tier determination
        tier_override: Override tier ("GOLD", "SILVER", "BRONZE", "SKIP")
        skill_whitelist: Master-CV skills for grounding
        annotation_context: Phase 4.5 - HeaderGenerationContext with annotation priorities
        jd_annotations: Raw jd_annotations dict containing synthesized_persona for
                       persona-framed profile generation.

    Returns:
        HeaderOutput with profile, skills, and ensemble metadata
    """
    # Determine tier
    if tier_override:
        # Use bracket notation for name lookup (GOLD, SILVER, etc.)
        tier = ProcessingTier[tier_override.upper()]
    else:
        tier = get_tier_from_fit_score(fit_score)

    tier_config = get_tier_config(tier)

    generator = EnsembleHeaderGenerator(
        tier_config=tier_config,
        skill_whitelist=skill_whitelist,
        annotation_context=annotation_context,
        jd_annotations=jd_annotations,
    )

    return generator.generate(stitched_cv, extracted_jd, candidate_data)
