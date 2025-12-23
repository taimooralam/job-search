"""
Header & Skills Generator (Phase 5).

Generates profile summary and skills sections grounded in
the stitched experience section.

Key Principles:
1. Profile includes quantified highlights FROM experience section
2. Skills ONLY include items evidenced in experience bullets
3. JD keywords are prioritized when they have evidence
4. Skills sections use pre-defined role-based taxonomy (replaces LLM-generated categories)

Usage:
    generator = HeaderGenerator(skill_whitelist=whitelist)
    header = generator.generate(
        stitched_cv=stitched_cv,
        extracted_jd=extracted_jd,
        candidate_data=candidate_data,
    )
"""

import re
from typing import List, Dict, Set, Optional, Tuple, Any, Callable
from collections import defaultdict

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.logger import get_logger
from src.common.config import Config
from src.common.unified_llm import UnifiedLLM
from src.common.persona_builder import get_persona_guidance
from src.layer6_v2.skills_taxonomy import SkillsTaxonomy, TaxonomyBasedSkillsGenerator


def _load_role_persona(role_category: str) -> dict:
    """
    Load persona data for a role from role_skills_taxonomy.json.

    Args:
        role_category: One of the 8 role categories

    Returns:
        Dict with persona data (identity_statement, voice, power_verbs, etc.)
        or empty dict if not found.
    """
    import json
    import os

    taxonomy_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "master-cv", "role_skills_taxonomy.json"
    )
    taxonomy_path = os.path.abspath(taxonomy_path)

    try:
        with open(taxonomy_path, "r") as f:
            taxonomy_data = json.load(f)
        role_data = taxonomy_data.get("target_roles", {}).get(role_category, {})
        return role_data.get("persona", {})
    except Exception:
        return {}


def _build_profile_system_prompt_with_persona(
    jd_annotations: Optional[Dict[str, Any]] = None,
) -> str:
    """Build profile system prompt with persona context prepended."""
    from src.layer6_v2.prompts.header_generation import PROFILE_SYSTEM_PROMPT

    persona_guidance = get_persona_guidance(jd_annotations)
    if not persona_guidance:
        return PROFILE_SYSTEM_PROMPT

    persona_section = f"""=== CANDIDATE PERSONA (Frame ALL output around this identity) ===

{persona_guidance}

This persona defines WHO the candidate is as a professional.
The headline and opening of the narrative MUST embody this identity.
Frame every achievement through this persona's lens.
Avoid sounding like a generic list - BE this professional.

=============================================================================

"""
    return persona_section + PROFILE_SYSTEM_PROMPT


from src.layer6_v2.types import (
    StitchedCV,
    SkillEvidence,
    SkillsSection,
    ProfileOutput,
    ValidationResult,
    HeaderOutput,
    HeaderGenerationContext,
    HeaderProvenance,
)


def _check_third_person_voice(text: str) -> List[str]:
    """
    Check if text uses first/second person pronouns instead of third-person absent voice.

    Third-person absent voice avoids pronouns like I, my, me, you, your, we, our.
    This is a defense-in-depth validation to catch LLM non-compliance.

    Args:
        text: Text to check (typically a tagline or persona statement)

    Returns:
        List of pronoun violations found (empty list if compliant)
    """
    # Define pronoun patterns with word boundaries to avoid false positives
    # e.g., "my" in "dynamically" would be a false positive without \b
    pronoun_patterns = [
        (r'\bI\b', 'I'),           # First person singular subject
        (r'\bmy\b', 'my'),         # First person singular possessive
        (r'\bme\b', 'me'),         # First person singular object
        (r'\bmine\b', 'mine'),     # First person singular possessive pronoun
        (r'\byou\b', 'you'),       # Second person
        (r'\byour\b', 'your'),     # Second person possessive
        (r'\byours\b', 'yours'),   # Second person possessive pronoun
        (r'\bwe\b', 'we'),         # First person plural subject
        (r'\bour\b', 'our'),       # First person plural possessive
        (r'\bus\b', 'us'),         # First person plural object
        (r'\bours\b', 'ours'),     # First person plural possessive pronoun
    ]

    violations = []
    for pattern, pronoun_name in pronoun_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(pronoun_name)

    return violations


# Pydantic models for structured LLM output
class ProfileResponse(BaseModel):
    """
    Hybrid Executive Summary structured response.

    Structure:
    1. Headline: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"
    2. Tagline: Persona-driven hook, third-person absent voice (15-25 words, max 200 chars)
    3. Key Achievements: 5-6 quantified proof points (no pronouns)
    4. Core Competencies: 6-8 ATS-friendly keywords
    """
    headline: str = Field(
        description="[EXACT JD TITLE] | [X]+ Years Technology Leadership"
    )
    tagline: str = Field(
        description="15-25 word persona-driven hook (max 200 chars). Third-person absent voice (NO pronouns: I/my/you). "
                    "Embodies candidate identity. Example: 'Technology leader who thrives on building infrastructure that scales.'"
    )
    key_achievements: List[str] = Field(
        description="5-6 quantified achievements. Each starts with action verb. "
                    "No pronouns. Format: 'Achieved X by doing Y, resulting in Z'"
    )
    core_competencies: List[str] = Field(
        description="6-8 ATS-friendly keywords matching JD terminology"
    )
    highlights_used: List[str] = Field(
        description="Exact metrics from source bullets used in key_achievements"
    )
    keywords_integrated: List[str] = Field(
        description="JD keywords naturally included across tagline and achievements"
    )
    exact_title_used: str = Field(
        description="The exact title from the JD used in headline"
    )
    # 4-question framework validation (updated for new structure)
    answers_who: bool = Field(
        default=True,
        description="Tagline answers 'Who are you professionally?'"
    )
    answers_what_problems: bool = Field(
        default=True,
        description="Key achievements show 'What problems can you solve?'"
    )
    answers_proof: bool = Field(
        default=True,
        description="Key achievements provide quantified proof"
    )
    answers_why_you: bool = Field(
        default=True,
        description="Tagline differentiates 'Why should they call you?'"
    )


class LegacyProfileResponse(BaseModel):
    """Legacy response format for backward compatibility."""
    profile_text: str = Field(description="2-3 sentence profile summary")
    highlights_used: List[str] = Field(description="Quantified achievements referenced")
    keywords_integrated: List[str] = Field(description="JD keywords naturally included")


class SkillExtraction(BaseModel):
    """Structured response for skill extraction from bullets."""
    leadership_skills: List[str] = Field(default_factory=list, description="Leadership skills evidenced")
    technical_skills: List[str] = Field(default_factory=list, description="Technical skills evidenced")
    platform_skills: List[str] = Field(default_factory=list, description="Platform/infrastructure skills")
    delivery_skills: List[str] = Field(default_factory=list, description="Delivery/process skills")


class HeaderGenerator:
    """
    Generates CV header sections grounded in experience.

    Features:
    - Profile summary with quantified highlights
    - Skills extraction with evidence tracking
    - JD keyword prioritization
    - Grounding validation
    - Master-CV skill whitelist to prevent hallucinations (GAP-001 fix)
    """

    # Skill category keywords for evidence matching
    SKILL_PATTERNS = {
        "Leadership": [
            r"\b(?:led|managed|mentored|coached|hired|built team|team of \d+|"
            r"cross-functional|stakeholder|collaboration|influence)\b",
        ],
        "Technical": [
            r"\b(?:python|java|typescript|javascript|go|rust|scala|kotlin|"
            r"sql|nosql|graphql|rest|api|microservices|architecture|"
            r"algorithms|data structures|machine learning|ai)\b",
        ],
        "Platform": [
            r"\b(?:aws|azure|gcp|kubernetes|docker|terraform|ci/cd|"
            r"jenkins|github actions|cloud|infrastructure|devops|"
            r"observability|monitoring|grafana|datadog)\b",
        ],
        "Delivery": [
            r"\b(?:agile|scrum|kanban|sprint|shipped|delivered|launched|"
            r"deadline|on-time|reduced time|deployment|release|"
            r"process|workflow|automation)\b",
        ],
    }

    # Category classification patterns for mapping skills to categories
    CATEGORY_CLASSIFIERS = {
        "Leadership": [
            "leadership", "lead", "manage", "mentor", "coach", "team",
            "hiring", "interviewing", "stakeholder", "communication",
            "performance", "talent", "executive",
        ],
        "Platform": [
            "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
            "ci/cd", "devops", "cloud", "infrastructure", "lambda",
            "ecs", "eks", "s3", "eventbridge", "cloudfront", "serverless",
            "monitoring", "observability", "datadog", "grafana",
        ],
        "Delivery": [
            "agile", "scrum", "kanban", "sprint", "project", "delivery",
            "quality", "tdd", "bdd", "testing", "jest", "release",
            "process", "workflow",
        ],
        # Technical is the default category for technical skills
    }

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.3,
        skill_whitelist: Optional[Dict[str, List[str]]] = None,
        lax_mode: bool = True,
        annotation_context: Optional[HeaderGenerationContext] = None,
        jd_annotations: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize the header generator.

        Args:
            model: LLM model to use (default: from step config)
            temperature: Generation temperature (default: 0.3 for consistency)
            skill_whitelist: Master-CV skill whitelist to prevent hallucinations.
                             Dict with 'hard_skills' and 'soft_skills' lists.
                             If not provided, loads from CVLoader automatically.
            lax_mode: If True (default), generate 30% more skills for manual pruning.
            annotation_context: Phase 4.5 - HeaderGenerationContext with annotation
                               priorities, reframes, and ATS requirements.
            jd_annotations: Raw jd_annotations dict containing synthesized_persona
                           for persona-framed profile generation.
            job_id: Job ID for tracking (optional)
            progress_callback: Optional callback for granular LLM progress events to Redis
        """
        self._logger = get_logger(__name__)
        self.temperature = temperature
        self.lax_mode = lax_mode
        self._job_id = job_id or "unknown"
        self._progress_callback = progress_callback

        # Store jd_annotations for persona access
        self._jd_annotations = jd_annotations
        if jd_annotations:
            persona_guidance = get_persona_guidance(jd_annotations)
            if persona_guidance:
                self._logger.info("Persona available for profile framing")

        # Phase 4.5: Store annotation context for header generation
        self._annotation_context = annotation_context
        if annotation_context and annotation_context.has_annotations:
            self._logger.info(
                f"Using annotation context: {len(annotation_context.priorities)} priorities, "
                f"{len(annotation_context.must_have_priorities)} must-haves, "
                f"{len(annotation_context.gap_priorities)} gaps"
            )

        # Store skill whitelist (GAP-001 fix: prevent hallucinated skills)
        self._skill_whitelist = skill_whitelist
        if skill_whitelist:
            self._logger.info(
                f"Using skill whitelist: {len(skill_whitelist.get('hard_skills', []))} hard, "
                f"{len(skill_whitelist.get('soft_skills', []))} soft skills"
            )

        # Initialize taxonomy-based skills generator (replaces CategoryGenerator)
        # This uses the pre-defined role-specific taxonomy instead of LLM-generated categories
        # Phase 4.5: Now accepts annotation_context for annotation-aware scoring
        self._taxonomy_generator: Optional[TaxonomyBasedSkillsGenerator] = None
        if skill_whitelist:
            try:
                taxonomy = SkillsTaxonomy()
                self._taxonomy_generator = TaxonomyBasedSkillsGenerator(
                    taxonomy=taxonomy,
                    skill_whitelist=skill_whitelist,
                    lax_mode=lax_mode,
                    annotation_context=annotation_context,
                )
                self._logger.info("Using taxonomy-based skills generator")
            except Exception as e:
                self._logger.warning(f"Failed to load skills taxonomy: {e}. Will use fallback.")
                self._taxonomy_generator = None

        # Use UnifiedLLM with step config (middle tier for header_generator)
        self._llm = UnifiedLLM(
            step_name="header_generator",
            job_id=self._job_id,
            progress_callback=progress_callback,
        )
        self._logger.info(
            f"HeaderGenerator initialized with UnifiedLLM (step=header_generator, tier={self._llm.config.tier})"
        )

    def _classify_skill_category(self, skill: str) -> str:
        """
        Classify a skill into one of the four categories.

        Uses pattern matching against CATEGORY_CLASSIFIERS.
        Default category is "Technical" for unmatched skills.

        Args:
            skill: The skill name to classify

        Returns:
            Category name: "Leadership", "Technical", "Platform", or "Delivery"
        """
        skill_lower = skill.lower()

        for category, keywords in self.CATEGORY_CLASSIFIERS.items():
            if any(kw in skill_lower for kw in keywords):
                return category

        # Default to Technical for programming languages, frameworks, etc.
        return "Technical"

    def _build_skill_lists_from_whitelist(self) -> Dict[str, List[str]]:
        """
        Build categorized skill lists from the master-CV whitelist.

        This is the GAP-001 fix: Instead of using hardcoded skill lists
        that include skills the candidate doesn't have (PHP, Java, etc.),
        we use ONLY skills from the master-CV.

        Returns:
            Dict mapping category names to lists of skills from master-CV
        """
        skill_lists: Dict[str, List[str]] = {
            "Leadership": [],
            "Technical": [],
            "Platform": [],
            "Delivery": [],
        }

        if not self._skill_whitelist:
            self._logger.warning("No skill whitelist provided - skills may be hallucinated!")
            return skill_lists

        # Classify hard skills into categories
        for skill in self._skill_whitelist.get("hard_skills", []):
            category = self._classify_skill_category(skill)
            skill_lists[category].append(skill)

        # Classify soft skills (typically Leadership or Delivery)
        for skill in self._skill_whitelist.get("soft_skills", []):
            category = self._classify_skill_category(skill)
            # Soft skills usually belong in Leadership category
            if category == "Technical":
                category = "Leadership"  # Override for soft skills
            skill_lists[category].append(skill)

        self._logger.debug(
            f"Built skill lists from whitelist: "
            f"Leadership={len(skill_lists['Leadership'])}, "
            f"Technical={len(skill_lists['Technical'])}, "
            f"Platform={len(skill_lists['Platform'])}, "
            f"Delivery={len(skill_lists['Delivery'])}"
        )

        return skill_lists

    def _extract_metrics_from_bullets(self, bullets: List[str]) -> List[str]:
        """Extract quantified metrics from bullet points."""
        metrics = []
        for bullet in bullets:
            # Look for percentages
            percentages = re.findall(r'\d+(?:\.\d+)?%', bullet)
            for pct in percentages:
                # Find context around the percentage
                match = re.search(rf'(\w+\s+)?{re.escape(pct)}', bullet)
                if match:
                    metrics.append(f"{match.group(0)}")

            # Look for numbers with context (e.g., "team of 10", "$2M")
            numbers = re.findall(
                r'(?:\$?\d+(?:,\d{3})*(?:\.\d+)?(?:M|K|B)?)\s*(?:engineers?|team|requests?|users?|transactions?)',
                bullet,
                re.IGNORECASE
            )
            metrics.extend(numbers)

        return list(set(metrics))[:5]  # Return top 5 unique metrics

    def _find_skill_evidence(
        self,
        skill: str,
        bullets: List[str],
        roles: List[str],
    ) -> Optional[SkillEvidence]:
        """
        Find evidence for a skill in the bullet points.

        Returns SkillEvidence if found, None otherwise.
        """
        skill_lower = skill.lower()
        evidence_bullets = []
        source_roles = []

        for i, bullet in enumerate(bullets):
            bullet_lower = bullet.lower()
            if skill_lower in bullet_lower:
                evidence_bullets.append(bullet)
                # Map bullet index to role (simplified - assumes sequential)
                if i < len(roles):
                    source_roles.append(roles[i])

        if evidence_bullets:
            return SkillEvidence(
                skill=skill,
                evidence_bullets=evidence_bullets[:3],  # Limit to 3 examples
                source_roles=list(set(source_roles)),
                is_jd_keyword=False,  # Will be set by caller
            )
        return None

    def _extract_skills_from_bullets(
        self,
        bullets: List[str],
        role_companies: List[str],
        jd_keywords: Optional[List[str]] = None,
    ) -> Dict[str, List[SkillEvidence]]:
        """
        Extract skills from bullets with evidence tracking.

        GAP-001 FIX: Uses master-CV whitelist instead of hardcoded skills.
        Only includes skills that:
        1. Exist in the master-CV skill whitelist, OR
        2. Are JD keywords AND have evidence in the experience bullets

        This prevents hallucinations like "Java", "PHP" appearing when the
        candidate has never used those technologies.
        """
        skills_by_category: Dict[str, List[SkillEvidence]] = {
            "Leadership": [],
            "Technical": [],
            "Platform": [],
            "Delivery": [],
        }

        combined_text = " ".join(bullets).lower()

        # GAP-001 FIX: Build skill lists from master-CV whitelist instead of hardcoded lists
        # This ensures we ONLY include skills the candidate actually has
        skill_lists = self._build_skill_lists_from_whitelist()

        # Create a set of all whitelist skills for quick lookup
        whitelist_skills_lower = set()
        if self._skill_whitelist:
            for skill in self._skill_whitelist.get("hard_skills", []):
                whitelist_skills_lower.add(skill.lower())
            for skill in self._skill_whitelist.get("soft_skills", []):
                whitelist_skills_lower.add(skill.lower())

        # GAP-001 STRICT FIX: Do NOT add JD keywords that aren't in the whitelist
        # This prevents hallucination of skills like "React", "Java", "PHP" that the
        # candidate has never used. JD keywords are used only for PRIORITIZATION,
        # not for adding new skills.
        #
        # REMOVED: Logic that added JD keywords with "evidence in bullets" - this was
        # too permissive because:
        # 1. Substring matching catches false positives (e.g., "react" in "reacted")
        # 2. Mentioning a skill in context doesn't mean proficiency
        # 3. The master CV is the source of truth for candidate skills
        #
        # JD keywords will still get prioritized in _prioritize_jd_keywords() if they
        # happen to match whitelist skills.
        if jd_keywords:
            self._logger.debug(
                f"JD keywords for prioritization only (not adding to skills): "
                f"{len(jd_keywords)} keywords"
            )

        # Extract skills with evidence
        for category, skills in skill_lists.items():
            for skill in skills:
                evidence = self._find_skill_evidence(skill, bullets, role_companies)
                if evidence:
                    skills_by_category[category].append(evidence)

        return skills_by_category

    def _prioritize_jd_keywords(
        self,
        skills_by_category: Dict[str, List[SkillEvidence]],
        jd_keywords: List[str],
    ) -> Dict[str, List[SkillEvidence]]:
        """
        Prioritize JD keywords that have evidence.

        Marks JD keywords and moves them to the front of each category.
        """
        jd_keywords_lower = {kw.lower() for kw in jd_keywords}

        for category, skills in skills_by_category.items():
            # Mark JD keywords
            for skill in skills:
                if skill.skill.lower() in jd_keywords_lower:
                    skill.is_jd_keyword = True

            # Sort: JD keywords first, then alphabetically
            skills_by_category[category] = sorted(
                skills,
                key=lambda s: (not s.is_jd_keyword, s.skill.lower())
            )

        return skills_by_category

    def validate_skills_grounded(
        self,
        skills_sections: List[SkillsSection],
        stitched_cv: StitchedCV,
    ) -> ValidationResult:
        """
        Verify all skills are evidenced in experience.

        Returns ValidationResult with grounded/ungrounded skills.
        """
        all_bullets = []
        for role in stitched_cv.roles:
            all_bullets.extend(role.bullets)
        combined_text = " ".join(all_bullets).lower()

        grounded = []
        ungrounded = []
        evidence_map: Dict[str, List[str]] = {}

        for section in skills_sections:
            for skill_evidence in section.skills:
                skill = skill_evidence.skill
                if skill.lower() in combined_text or skill_evidence.evidence_bullets:
                    grounded.append(skill)
                    evidence_map[skill] = skill_evidence.evidence_bullets
                else:
                    ungrounded.append(skill)

        return ValidationResult(
            passed=len(ungrounded) == 0,
            grounded_skills=grounded,
            ungrounded_skills=ungrounded,
            evidence_map=evidence_map,
        )

    def _calculate_years_experience(self, stitched_cv: StitchedCV) -> int:
        """
        Calculate approximate years of experience from role periods.

        Extracts years from role periods and calculates span.
        """
        import re
        years = []
        for role in stitched_cv.roles:
            # Extract years from period strings like "2020–Present", "2018-2020"
            year_matches = re.findall(r'20\d{2}|19\d{2}', role.period)
            years.extend([int(y) for y in year_matches])

        if years:
            # Calculate span from earliest to latest/current
            min_year = min(years)
            max_year = max(years) if max(years) > 2020 else 2024  # Assume current if recent
            return max(max_year - min_year, 5)  # Minimum 5 years for senior roles
        return 10  # Default for senior technical leadership

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _generate_profile_llm(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_name: str,
        regional_variant: str = "us_eu",
    ) -> Tuple[ProfileResponse, HeaderProvenance]:
        """
        Generate research-aligned profile using LLM with structured output.

        Based on research from 625 hiring managers:
        - 100-150 word narrative (3-5 sentences)
        - Headline with exact job title (10.6x interview factor)
        - Core competencies for ATS optimization
        - 4-question framework (Who/What/Proof/Why)
        - 60/30/10 content formula

        Phase 4.5: Now injects annotation context into prompt for must-have
        emphasis, reframes, and gap mitigation.

        Uses Pydantic for response validation.

        Returns:
            Tuple of (ProfileResponse, HeaderProvenance) for traceability
        """
        from src.layer6_v2.prompts.header_generation import build_profile_user_prompt
        from src.layer6_v2.annotation_header_context import (
            format_priorities_for_prompt,
            format_ats_guidance_for_prompt,
        )

        # Collect all bullets for context
        all_bullets = []
        for role in stitched_cv.roles:
            all_bullets.extend(role.bullets)

        combined_text = " ".join(all_bullets).lower()

        # Extract top metrics for grounding
        top_metrics = self._extract_metrics_from_bullets(all_bullets)

        # GAP-001 FIX: Filter JD keywords to only those evidenced in experience bullets
        jd_keywords = extracted_jd.get('top_keywords', [])[:15]
        grounded_keywords = []
        for kw in jd_keywords:
            kw_lower = kw.lower()
            # Check if keyword appears in experience OR is in whitelist
            if kw_lower in combined_text:
                grounded_keywords.append(kw)
            elif self._skill_whitelist:
                all_whitelist = (
                    self._skill_whitelist.get("hard_skills", []) +
                    self._skill_whitelist.get("soft_skills", [])
                )
                if any(kw_lower == s.lower() for s in all_whitelist):
                    grounded_keywords.append(kw)

        self._logger.debug(
            f"Profile keywords: {len(grounded_keywords)}/{len(jd_keywords)} grounded in experience"
        )

        # Calculate years of experience for headline
        years_experience = self._calculate_years_experience(stitched_cv)

        # Extract pain points for "What problems can you solve?" question
        jd_pain_points = extracted_jd.get('pain_points', [])
        if not jd_pain_points:
            # Fallback: use responsibilities as proxy for pain points
            jd_pain_points = extracted_jd.get('responsibilities', [])[:5]

        # Extract differentiators from candidate skills for "Why you?" question
        candidate_differentiators = []
        if self._skill_whitelist:
            # Use top soft skills as differentiators
            candidate_differentiators = self._skill_whitelist.get('soft_skills', [])[:3]

        # Get exact job title from JD (critical for 10.6x factor)
        exact_job_title = extracted_jd.get('title', 'Engineering Leader')
        role_category = extracted_jd.get('role_category', 'engineering_manager')

        # Phase 4.5: Build annotation guidance for prompt injection
        annotation_guidance = ""
        ats_guidance = ""
        provenance = HeaderProvenance(title_source="jd_mapping")

        if self._annotation_context and self._annotation_context.has_annotations:
            self._logger.debug("Injecting annotation context into profile prompt")

            # Format priorities for prompt
            annotation_guidance = format_priorities_for_prompt(self._annotation_context)
            ats_guidance = format_ats_guidance_for_prompt(self._annotation_context)

            # Build provenance for traceability
            provenance.tagline_keywords = self._annotation_context.top_keywords[:3]
            provenance.tagline_annotation_ids = [
                aid for p in self._annotation_context.must_have_priorities[:3]
                for aid in p.annotation_ids
            ]
            provenance.summary_annotation_ids = [
                aid for p in self._annotation_context.priorities[:5]
                for aid in p.annotation_ids
            ]
            # Collect STAR IDs from priorities
            provenance.summary_star_ids = [
                star_id
                for p in self._annotation_context.priorities[:5]
                for snippet in p.star_snippets
                for star_id in p.annotation_ids  # Approximate: use annotation IDs
            ][:5]  # Limit to 5
            # Track gap mitigation
            if self._annotation_context.gap_mitigation:
                provenance.gap_mitigation_annotation_id = (
                    self._annotation_context.gap_mitigation_annotation_id
                )
            # Track reframes
            provenance.reframes_applied = [
                aid for p in self._annotation_context.priorities
                if p.has_reframe
                for aid in p.annotation_ids
            ][:5]

            # Enhance grounded keywords with annotation keywords
            for p in self._annotation_context.priorities[:10]:
                if p.matching_skill and p.matching_skill not in grounded_keywords:
                    grounded_keywords.append(p.matching_skill)
                for variant in p.ats_variants[:2]:
                    if variant not in grounded_keywords:
                        grounded_keywords.append(variant)

            # Use annotation STAR snippets as additional proof
            annotation_proofs = []
            for p in self._annotation_context.must_have_priorities[:3]:
                annotation_proofs.extend(p.star_snippets[:1])
            if annotation_proofs:
                top_metrics = annotation_proofs[:3] + top_metrics

        # Load role persona from taxonomy for targeted generation
        role_persona = _load_role_persona(role_category)
        if role_persona:
            self._logger.debug(f"Loaded persona for {role_category}: {role_persona.get('voice', 'N/A')}")

        # Build research-aligned prompt
        user_prompt = build_profile_user_prompt(
            candidate_name=candidate_name,
            job_title=exact_job_title,
            role_category=role_category,
            top_keywords=grounded_keywords,
            experience_bullets=all_bullets[:20],
            metrics=top_metrics,
            years_experience=years_experience,
            regional_variant=regional_variant,
            jd_pain_points=jd_pain_points,
            candidate_differentiators=candidate_differentiators,
            role_persona=role_persona,
        )

        # Phase 4.5: Append annotation guidance to user prompt
        if annotation_guidance:
            user_prompt = user_prompt + "\n\n" + annotation_guidance
        if ats_guidance:
            user_prompt = user_prompt + "\n\n" + ats_guidance
        if self._annotation_context and self._annotation_context.gap_mitigation:
            user_prompt = user_prompt + f"\n\nGAP MITIGATION (include once): {self._annotation_context.gap_mitigation}"

        # Build system prompt with persona context (Phase 5: persona in SYSTEM prompt)
        system_prompt = _build_profile_system_prompt_with_persona(self._jd_annotations)

        # Add schema guidance to system prompt for JSON response
        schema_guidance = """
Return JSON matching this ProfileResponse schema:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word persona-driven hook (max 200 chars, third-person absent voice)",
  "key_achievements": ["5-6 quantified achievements starting with action verbs"],
  "core_competencies": ["6-8 ATS-friendly keywords"],
  "highlights_used": ["exact metrics used"],
  "keywords_integrated": ["JD keywords included"],
  "exact_title_used": "the exact title from JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
}"""
        full_system_prompt = system_prompt + "\n\n" + schema_guidance

        # Use UnifiedLLM with JSON validation
        result = await self._llm.invoke(
            prompt=user_prompt,
            system=full_system_prompt,
            validate_json=True,
        )

        if not result.success:
            raise ValueError(f"LLM profile generation failed: {result.error}")

        if not result.parsed_json:
            raise ValueError("LLM response was not valid JSON")

        # Parse into Pydantic model
        response = ProfileResponse(**result.parsed_json)
        return response, provenance

    async def generate_profile(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_name: str,
        regional_variant: str = "us_eu",
    ) -> ProfileOutput:
        """
        Generate hybrid executive summary grounded in achievements.

        Based on research from 625 hiring managers:
        - Tagline: 15-25 words, third-person absent voice (max 200 chars)
        - Key Achievements: 5-6 quantified bullets
        - Headline with exact job title (10.6x interview factor)
        - Core competencies for ATS optimization
        - 4-question framework validation

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted JD intelligence
            candidate_name: Candidate name for profile
            regional_variant: "us_eu" (default) or "gulf"

        Returns:
            ProfileOutput with hybrid executive summary structure
        """
        self._logger.info("Generating hybrid executive summary...")

        provenance = None
        try:
            response, provenance = await self._generate_profile_llm(
                stitched_cv, extracted_jd, candidate_name, regional_variant
            )

            # Build new hybrid ProfileOutput with Phase 4.5 provenance
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
                regional_variant=regional_variant,
                # Keep narrative for backward compatibility (use tagline)
                narrative=response.tagline,
                # Phase 4.5: Annotation traceability
                provenance=provenance,
                annotation_influenced=provenance.has_annotation_influence if provenance else False,
            )

            # Log 4-question framework validation
            if profile.all_four_questions_answered:
                self._logger.info("Profile answers all 4 hiring manager questions")
            else:
                missing = []
                if not profile.answers_who:
                    missing.append("Who are you?")
                if not profile.answers_what_problems:
                    missing.append("What problems?")
                if not profile.answers_proof:
                    missing.append("What proof?")
                if not profile.answers_why_you:
                    missing.append("Why you?")
                self._logger.warning(f"Profile missing answers to: {', '.join(missing)}")

            # Log hybrid format details
            self._logger.info(
                f"Hybrid summary generated: tagline={len(profile.tagline.split())} words, "
                f"achievements={len(profile.key_achievements)}, "
                f"competencies={len(profile.core_competencies)}"
            )

            # Phase 4.5: Log annotation influence
            if profile.annotation_influenced:
                self._logger.info(
                    f"Profile influenced by {provenance.total_annotations_used} annotations"
                )

            # Defense-in-depth: Validate third-person absent voice in tagline
            voice_violations = _check_third_person_voice(profile.tagline)
            if voice_violations:
                self._logger.warning(
                    f"Tagline contains first/second person pronouns (should use third-person absent voice): "
                    f"found [{', '.join(voice_violations)}] in tagline: '{profile.tagline[:100]}...'"
                )

        except Exception as e:
            self._logger.warning(f"LLM profile generation failed: {e}. Using fallback.")
            # Fallback: Template-based hybrid profile
            role_category = extracted_jd.get("role_category", "engineering_manager")
            job_title = extracted_jd.get("title", "Engineering Leader")
            profile = self._generate_fallback_profile(
                stitched_cv, role_category, candidate_name, job_title, regional_variant
            )

        self._logger.info(f"Profile generated: {profile.word_count} words")
        return profile

    def _generate_fallback_profile(
        self,
        stitched_cv: StitchedCV,
        role_category: str,
        candidate_name: str,
        job_title: str = "Engineering Leader",
        regional_variant: str = "us_eu",
    ) -> ProfileOutput:
        """
        Generate a fallback hybrid executive summary when LLM fails.

        Still follows the hybrid structure:
        - Headline with job title
        - Tagline (15-25 words, third-person absent voice)
        - Key achievements (5-6 bullets)
        - Core competencies
        """
        # Extract some metrics
        all_bullets = []
        for role in stitched_cv.roles:
            all_bullets.extend(role.bullets)
        metrics = self._extract_metrics_from_bullets(all_bullets)

        # Calculate years of experience
        years_experience = self._calculate_years_experience(stitched_cv)

        # Generate headline (research: 10.6x interview factor)
        headline = f"{job_title} | {years_experience}+ Years Technology Leadership"

        # Role-specific taglines (third-person absent voice, 15-25 words)
        taglines = {
            "engineering_manager": (
                "Engineering leader who builds high-performing teams that deliver exceptional results "
                "while developing talent for the future."
            ),
            "staff_principal_engineer": (
                "Staff engineer who designs scalable systems and drives technical excellence "
                "through cross-team influence and mentorship."
            ),
            "director_of_engineering": (
                "Engineering director who scales organizations and builds cultures of "
                "engineering excellence that attract top talent."
            ),
            "head_of_engineering": (
                "Engineering executive who builds functions from scratch and transforms "
                "organizations to deliver measurable business outcomes."
            ),
            "vp_engineering": (
                "Engineering VP who leads organizations at scale, balancing strategic vision "
                "with operational excellence to drive business outcomes."
            ),
            "cto": (
                "Technology executive who drives business transformation through strategic "
                "technology leadership and world-class engineering teams."
            ),
            "tech_lead": (
                "Hands-on technical leader who drives delivery excellence through code quality "
                "and team guidance while shipping high-impact features."
            ),
            "senior_engineer": (
                "Senior engineer who builds scalable systems and delivers high-quality code "
                "through deep technical expertise and collaborative approach."
            ),
        }

        tagline = taglines.get(role_category, taglines["engineering_manager"])

        # Generate key achievements from top metrics or generic fallbacks
        key_achievements = []

        # Try to use metrics from bullets
        for metric in metrics[:5]:
            key_achievements.append(f"Delivered {metric} through strategic initiatives")

        # If not enough metrics, add generic achievements by role
        generic_achievements_by_role = {
            "engineering_manager": [
                "Built and scaled high-performing engineering teams",
                "Established engineering culture focused on continuous improvement",
                "Drove delivery excellence across complex technical initiatives",
                "Developed talent pipeline that accelerated team growth",
                "Improved team velocity and predictability through process optimization",
            ],
            "staff_principal_engineer": [
                "Architected scalable systems serving millions of users",
                "Established technical standards adopted across the organization",
                "Led complex cross-team technical initiatives",
                "Mentored senior engineers on system design best practices",
                "Drove architectural decisions enabling business growth",
            ],
            "director_of_engineering": [
                "Scaled engineering organization across multiple teams",
                "Developed engineering managers into effective leaders",
                "Delivered complex programs on time and within budget",
                "Established strategic technical direction for the organization",
                "Built high-performing engineering culture",
            ],
            "head_of_engineering": [
                "Built engineering function from scratch",
                "Transformed engineering organization to enterprise scale",
                "Established engineering excellence practices company-wide",
                "Delivered strategic initiatives creating business value",
                "Built talent strategy that attracted top engineers",
            ],
            "vp_engineering": [
                "Led engineering organization at scale across multiple directors",
                "Drove operational excellence and delivery velocity",
                "Established strategic partnerships with executive leadership",
                "Transformed engineering practices to enterprise standards",
                "Built high-performing engineering culture at scale",
            ],
            "cto": [
                "Led technology transformation across the organization",
                "Defined technology vision enabling business growth",
                "Built and scaled world-class engineering teams",
                "Drove business outcomes through strategic technology leadership",
                "Established board-level technical communication",
            ],
            "tech_lead": [
                "Led team delivery of critical product features",
                "Established code quality standards and best practices",
                "Drove architectural decisions for team's domain",
                "Mentored junior engineers on technical excellence",
                "Delivered high-quality features on time",
            ],
            "senior_engineer": [
                "Built scalable systems serving production traffic",
                "Delivered high-impact features with quality code",
                "Optimized system performance and reliability",
                "Collaborated effectively across teams",
                "Established coding standards within the team",
            ],
        }

        generic_achievements = generic_achievements_by_role.get(
            role_category, generic_achievements_by_role["engineering_manager"]
        )

        # Fill remaining slots with generic achievements
        while len(key_achievements) < 5 and generic_achievements:
            key_achievements.append(generic_achievements.pop(0))

        # Default core competencies based on role category
        competencies_by_role = {
            "engineering_manager": [
                "Engineering Leadership", "Team Building", "People Development",
                "Agile Delivery", "Technical Strategy", "Performance Management"
            ],
            "staff_principal_engineer": [
                "System Architecture", "Technical Strategy", "Cross-team Collaboration",
                "Mentorship", "Code Quality", "Performance Optimization"
            ],
            "director_of_engineering": [
                "Organizational Leadership", "Strategic Planning", "Program Management",
                "Manager Development", "Engineering Excellence", "Stakeholder Management"
            ],
            "head_of_engineering": [
                "Function Building", "Org Design", "Executive Leadership",
                "Talent Strategy", "Engineering Culture", "Business Alignment"
            ],
            "vp_engineering": [
                "Engineering Executive", "Operational Excellence", "Strategic Delivery",
                "Organizational Scale", "Business Partnership", "Engineering Strategy"
            ],
            "cto": [
                "Technology Vision", "Executive Leadership", "Business Transformation",
                "M&A Due Diligence", "Board Communication", "Strategic Planning"
            ],
            "tech_lead": [
                "Technical Leadership", "Code Quality", "System Design",
                "Team Guidance", "Agile Delivery", "Mentorship"
            ],
            "senior_engineer": [
                "Software Development", "System Design", "Code Quality",
                "Technical Expertise", "Collaboration", "Problem Solving"
            ],
        }

        core_competencies = competencies_by_role.get(
            role_category, competencies_by_role["engineering_manager"]
        )

        return ProfileOutput(
            headline=headline,
            tagline=tagline,                      # NEW: Hybrid format
            key_achievements=key_achievements,    # NEW: Hybrid format
            core_competencies=core_competencies,
            highlights_used=metrics[:4],
            keywords_integrated=[],
            exact_title_used=job_title,
            answers_who=True,
            answers_what_problems=True,
            answers_proof=bool(metrics),
            answers_why_you=True,
            regional_variant=regional_variant,
            # Keep narrative for backward compatibility
            narrative=tagline,
        )

    def generate_skills(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
    ) -> List[SkillsSection]:
        """
        Generate skills sections grounded in experience.

        Uses the pre-defined role-based taxonomy for consistent, ATS-optimized output.
        Falls back to static categories if taxonomy is not available.

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted JD intelligence

        Returns:
            List of SkillsSection with evidence tracking
        """
        self._logger.info("Extracting skills from experience...")

        # Collect all bullets and role companies
        all_bullets = []
        role_companies = []
        for role in stitched_cv.roles:
            for bullet in role.bullets:
                all_bullets.append(bullet)
                role_companies.append(role.company)

        # Use taxonomy-based generator if available
        if self._taxonomy_generator:
            self._logger.info("Using taxonomy-based skills generator...")
            sections = self._taxonomy_generator.generate_sections(
                extracted_jd=extracted_jd,
                experience_bullets=all_bullets,
                role_companies=role_companies,
            )
            self._logger.info(f"Generated {sum(s.skill_count for s in sections)} skills across {len(sections)} sections")
            return sections

        # Fallback: Static categories (if taxonomy not available)
        self._logger.warning("Taxonomy not available, using static categories fallback")

        # Extract JD keywords for skill matching
        jd_keywords = extracted_jd.get("top_keywords", [])
        jd_technical = extracted_jd.get("technical_skills", [])
        all_jd_keywords = list(set(jd_keywords + jd_technical))

        # Extract skills with evidence using static categories
        skills_by_category = self._extract_skills_from_bullets(
            all_bullets, role_companies, jd_keywords=all_jd_keywords
        )
        skills_by_category = self._prioritize_jd_keywords(skills_by_category, jd_keywords)

        # Build static sections
        sections = []
        for category in ["Leadership", "Technical", "Platform", "Delivery"]:
            skills = skills_by_category.get(category, [])
            if skills:  # Only include categories with skills
                sections.append(SkillsSection(
                    category=category,
                    skills=skills[:8],  # Limit to 8 skills per category
                ))

        self._logger.info(f"Extracted {sum(s.skill_count for s in sections)} skills across {len(sections)} categories")
        return sections

    async def generate(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_data: Dict,
    ) -> HeaderOutput:
        """
        Generate complete header with profile, skills, and education.

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted JD intelligence
            candidate_data: Candidate info (name, email, phone, linkedin, education, certifications, languages)

        Returns:
            HeaderOutput with all header sections
        """
        self._logger.info("Generating CV header sections...")

        # Extract candidate info - support both flat dict and nested dict formats
        if "header" in candidate_data:
            # Nested format (legacy)
            candidate_name = candidate_data.get("header", {}).get("name", "Candidate")
            contact_info = candidate_data.get("header", {}).get("contact", {})
            contact_info["name"] = candidate_name
            education = candidate_data.get("education", [])
            certifications = candidate_data.get("certifications", [])
            languages = candidate_data.get("languages", [])
        else:
            # Flat format (from orchestrator)
            candidate_name = candidate_data.get("name", "Candidate")
            contact_info = {
                "name": candidate_name,
                "email": candidate_data.get("email", ""),
                "phone": candidate_data.get("phone", ""),
                "linkedin": candidate_data.get("linkedin", ""),
                "location": candidate_data.get("location", ""),
            }
            education = candidate_data.get("education", [])
            certifications = candidate_data.get("certifications", [])
            languages = candidate_data.get("languages", [])

        # Generate profile
        profile = await self.generate_profile(stitched_cv, extracted_jd, candidate_name)

        # Generate skills
        skills_sections = self.generate_skills(stitched_cv, extracted_jd)

        # Validate grounding
        validation = self.validate_skills_grounded(skills_sections, stitched_cv)
        if not validation.passed:
            self._logger.warning(
                f"Skills validation failed. Ungrounded skills: {validation.ungrounded_skills}"
            )
            # Remove ungrounded skills
            skills_sections = self._remove_ungrounded_skills(
                skills_sections, validation.ungrounded_skills
            )
            validation = self.validate_skills_grounded(skills_sections, stitched_cv)

        # Build final output
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills_sections,
            education=education,
            contact_info=contact_info,
            certifications=certifications,
            languages=languages,
            validation_result=validation,
        )

        self._logger.info(f"Header generation complete:")
        self._logger.info(f"  Profile: {profile.word_count} words")
        self._logger.info(f"  Skills: {header.total_skills_count} across {len(skills_sections)} categories")
        self._logger.info(f"  Validation: {'PASSED' if validation.passed else 'FAILED'}")

        return header

    def _remove_ungrounded_skills(
        self,
        skills_sections: List[SkillsSection],
        ungrounded: List[str],
    ) -> List[SkillsSection]:
        """Remove ungrounded skills from sections."""
        ungrounded_lower = {s.lower() for s in ungrounded}
        filtered_sections = []

        for section in skills_sections:
            filtered_skills = [
                s for s in section.skills
                if s.skill.lower() not in ungrounded_lower
            ]
            if filtered_skills:
                filtered_sections.append(SkillsSection(
                    category=section.category,
                    skills=filtered_skills,
                ))

        return filtered_sections


async def generate_header(
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_data: Dict,
    skill_whitelist: Optional[Dict[str, List[str]]] = None,
    lax_mode: bool = True,
    annotation_context: Optional[HeaderGenerationContext] = None,
    jd_annotations: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> HeaderOutput:
    """
    Convenience function to generate CV header.

    Args:
        stitched_cv: Stitched experience section
        extracted_jd: Extracted JD intelligence
        candidate_data: Candidate info (name, contact, education)
        skill_whitelist: Master-CV skill whitelist to prevent hallucinations (GAP-001).
                        If not provided, skills may be hallucinated.
        lax_mode: If True, generate 30% more skills for manual pruning.
        annotation_context: Phase 4.5 - HeaderGenerationContext with annotation priorities,
                           reframes, and ATS requirements.
        jd_annotations: Raw jd_annotations dict containing synthesized_persona for
                       persona-framed profile generation.
        job_id: Job ID for tracking (optional)
        progress_callback: Optional callback for granular LLM progress events to Redis

    Returns:
        HeaderOutput with all header sections
    """
    generator = HeaderGenerator(
        skill_whitelist=skill_whitelist,
        lax_mode=lax_mode,
        annotation_context=annotation_context,
        jd_annotations=jd_annotations,
        job_id=job_id,
        progress_callback=progress_callback,
    )
    return await generator.generate(stitched_cv, extracted_jd, candidate_data)
