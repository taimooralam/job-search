"""
Annotation Header Context Builder for Phase 4.5.

This module builds the context needed to inject JD annotations into header,
summary, and skills generation. It bridges the annotation system with the
CV generation pipeline.

Key responsibilities:
1. Extract and rank annotation priorities using weighted scoring
2. Build reframe maps for skill→JD-aligned language translation
3. Generate gap mitigation clauses (reframe if possible, omit if not)
4. Extract STAR snippets for proof statements
5. Build ATS requirements for keyword coverage targeting

Usage:
    from src.layer6_v2.annotation_header_context import AnnotationHeaderContextBuilder

    builder = AnnotationHeaderContextBuilder(jd_annotations, all_stars)
    context = builder.build_context()
    # Pass context to HeaderGenerator, TaxonomyBasedSkillsGenerator, etc.
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field

from src.common.logger import get_logger
from src.common.annotation_types import (
    JDAnnotation,
    RELEVANCE_MULTIPLIERS,
    REQUIREMENT_MULTIPLIERS,
    PRIORITY_MULTIPLIERS,
)
from src.common.types import STARRecord
from src.layer6_v2.types import (
    AnnotationPriority,
    HeaderGenerationContext,
    ATSRequirement,
)

logger = get_logger(__name__)


# =============================================================================
# SCORING WEIGHTS (from plan)
# =============================================================================

# Weights for priority score calculation
WEIGHT_RELEVANCE = 0.4
WEIGHT_REQUIREMENT = 0.3
WEIGHT_USER_PRIORITY = 0.2
WEIGHT_STAR_EVIDENCE = 0.1

# Map relevance levels to numeric scores (1-5 scale for weighting)
RELEVANCE_SCORES: Dict[str, float] = {
    "core_strength": 5.0,
    "extremely_relevant": 4.0,
    "relevant": 3.0,
    "tangential": 2.0,
    "gap": 1.0,
}

# Map requirement types to numeric scores (1-5 scale for weighting)
REQUIREMENT_SCORES: Dict[str, float] = {
    "must_have": 5.0,
    "nice_to_have": 3.0,
    "disqualifier": 0.0,
    "neutral": 2.0,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_star_snippet(star: STARRecord) -> str:
    """
    Extract a one-line metric statement from a STAR record.

    Prioritizes:
    1. First metric with a number/percentage
    2. Impact summary (truncated)
    3. Condensed version (truncated)

    Returns:
        One-line snippet (≤100 chars) suitable for summary proof statement
    """
    # Try to find a good metric
    metrics = star.get("metrics", [])
    for metric in metrics:
        if metric and any(c.isdigit() for c in metric):
            return metric[:100] if len(metric) > 100 else metric

    # Fall back to impact summary
    impact = star.get("impact_summary", "")
    if impact:
        return impact[:100] + "..." if len(impact) > 100 else impact

    # Fall back to condensed version
    condensed = star.get("condensed_version", "")
    if condensed:
        return condensed[:100] + "..." if len(condensed) > 100 else condensed

    return ""


def calculate_priority_score(
    relevance: str,
    requirement_type: str,
    user_priority: int,
    has_star_evidence: bool,
) -> float:
    """
    Calculate priority score using weighted formula from plan.

    Formula:
    priority_score = (
        RELEVANCE_SCORES[relevance] * 0.4 +
        REQUIREMENT_SCORES[requirement_type] * 0.3 +
        (6 - user_priority) * 0.2 +  # Invert: 1 is highest priority
        has_star_evidence * 0.1
    )

    Returns:
        Score in range 0-5 (higher = more important)
    """
    relevance_score = RELEVANCE_SCORES.get(relevance, 3.0)
    requirement_score = REQUIREMENT_SCORES.get(requirement_type, 2.0)
    priority_score = (6 - min(max(user_priority, 1), 5))  # Invert 1-5 to 5-1
    star_score = 1.0 if has_star_evidence else 0.0

    total = (
        relevance_score * WEIGHT_RELEVANCE +
        requirement_score * WEIGHT_REQUIREMENT +
        priority_score * WEIGHT_USER_PRIORITY +
        star_score * WEIGHT_STAR_EVIDENCE
    )

    return round(total, 3)


# =============================================================================
# MAIN BUILDER CLASS
# =============================================================================

class AnnotationHeaderContextBuilder:
    """
    Builds HeaderGenerationContext from JD annotations.

    This class extracts, scores, and ranks annotation priorities, then
    builds all the context needed for annotation-driven header generation.
    """

    def __init__(
        self,
        jd_annotations: Optional[Dict[str, Any]] = None,
        all_stars: Optional[List[STARRecord]] = None,
        max_priorities: int = 10,
    ):
        """
        Initialize the builder.

        Args:
            jd_annotations: JDAnnotations dict from job state (can be None)
            all_stars: Full STAR library for snippet extraction
            max_priorities: Maximum number of priorities to include (default 10)
        """
        self.jd_annotations = jd_annotations or {}
        self.all_stars = all_stars or []
        self.max_priorities = max_priorities

        # Build STAR lookup for efficient access
        self._star_by_id: Dict[str, STARRecord] = {
            star.get("id", ""): star
            for star in self.all_stars
            if star.get("id")
        }

    def build_context(self) -> HeaderGenerationContext:
        """
        Build the complete HeaderGenerationContext.

        Returns:
            HeaderGenerationContext with priorities, reframe map, gap mitigation, etc.
        """
        if not self.jd_annotations or not self.jd_annotations.get("annotations"):
            logger.debug("No annotations found, returning empty context")
            return HeaderGenerationContext()

        # Extract and rank priorities
        priorities = self._extract_priorities()

        # Build reframe map
        reframe_map = self._build_reframe_map(priorities)

        # Generate gap mitigation (if applicable)
        gap_mitigation, gap_annotation_id = self._generate_gap_mitigation(priorities)

        # Build ATS requirements
        ats_requirements = self._build_ats_requirements()

        # Build keyword coverage targets
        keyword_targets = self._build_keyword_targets(priorities)

        return HeaderGenerationContext(
            priorities=priorities,
            gap_mitigation=gap_mitigation,
            gap_mitigation_annotation_id=gap_annotation_id,
            reframe_map=reframe_map,
            ats_requirements=ats_requirements,
            keyword_coverage_target=keyword_targets,
        )

    def _extract_priorities(self) -> List[AnnotationPriority]:
        """
        Extract and rank annotation priorities.

        Processes all active annotations and creates ranked AnnotationPriority objects.

        Returns:
            List of AnnotationPriority sorted by priority_score (descending)
        """
        annotations = self.jd_annotations.get("annotations", [])
        priorities: List[AnnotationPriority] = []

        for ann in annotations:
            # Skip inactive annotations (default to True for backward compatibility)
            if not ann.get("is_active", True):
                continue

            # Skip rejected annotations
            if ann.get("status") == "rejected":
                continue

            # Extract data from annotation
            target = ann.get("target", {})
            jd_text = target.get("text", "")
            relevance = ann.get("relevance", "relevant")
            requirement_type = ann.get("requirement_type", "neutral")
            passion = ann.get("passion", "neutral")
            identity = ann.get("identity", "peripheral")
            user_priority = ann.get("priority", 3)
            matching_skill = ann.get("matching_skill")
            reframe_note = ann.get("reframe_note")
            reframe_from = ann.get("reframe_from")
            reframe_to = ann.get("reframe_to")
            ats_variants = ann.get("ats_variants", [])
            star_ids = ann.get("star_ids", [])

            # Extract STAR snippets
            star_snippets = self._get_star_snippets(star_ids)
            has_star_evidence = len(star_snippets) > 0

            # Calculate priority score
            score = calculate_priority_score(
                relevance=relevance,
                requirement_type=requirement_type,
                user_priority=user_priority,
                has_star_evidence=has_star_evidence,
            )

            priority = AnnotationPriority(
                rank=0,  # Will be set after sorting
                jd_text=jd_text,
                matching_skill=matching_skill,
                relevance=relevance,
                requirement_type=requirement_type,
                passion=passion,
                identity=identity,
                reframe_note=reframe_note,
                reframe_from=reframe_from,
                reframe_to=reframe_to,
                ats_variants=ats_variants,
                star_snippets=star_snippets,
                annotation_ids=[ann.get("id", "")],
                priority_score=score,
            )

            priorities.append(priority)

        # Sort by priority score (descending)
        priorities.sort(key=lambda p: p.priority_score, reverse=True)

        # Assign ranks
        for i, p in enumerate(priorities):
            p.rank = i + 1

        # Limit to max_priorities
        return priorities[:self.max_priorities]

    def _get_star_snippets(self, star_ids: List[str]) -> List[str]:
        """
        Get STAR snippets for a list of STAR IDs.

        Args:
            star_ids: List of STAR record IDs

        Returns:
            List of one-line metric snippets
        """
        snippets = []
        for star_id in star_ids:
            star = self._star_by_id.get(star_id)
            if star:
                snippet = extract_star_snippet(star)
                if snippet:
                    snippets.append(snippet)
        return snippets

    def _build_reframe_map(
        self,
        priorities: List[AnnotationPriority],
    ) -> Dict[str, str]:
        """
        Build a map of skill → reframe note.

        This allows quick lookup of how to reframe a skill when generating content.

        Args:
            priorities: Ranked priorities with reframe data

        Returns:
            Dict mapping skill/text to reframe note
        """
        reframe_map: Dict[str, str] = {}

        for p in priorities:
            if p.reframe_note:
                # Map by matching skill if available
                if p.matching_skill:
                    reframe_map[p.matching_skill.lower()] = p.reframe_note

                # Also map by reframe_from if different
                if p.reframe_from and p.reframe_from.lower() not in reframe_map:
                    reframe_map[p.reframe_from.lower()] = p.reframe_note

                # Map by JD text as fallback
                if p.jd_text:
                    # Use first 50 chars as key to handle long requirements
                    key = p.jd_text[:50].lower().strip()
                    if key not in reframe_map:
                        reframe_map[key] = p.reframe_note

        return reframe_map

    def _generate_gap_mitigation(
        self,
        priorities: List[AnnotationPriority],
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate gap mitigation clause using reframe-if-possible strategy.

        User Decision: "Reframe if possible"
        - If gap has reframe_note → generate mitigation using reframe
        - If gap has no reframe_note → return None (omit from header/summary)

        Only generates ONE mitigation (for the highest-priority must-have gap).

        Args:
            priorities: Ranked priorities

        Returns:
            Tuple of (mitigation clause, annotation_id that was used) or (None, None)
        """
        # Find must-have gaps with reframe notes
        for p in priorities:
            if p.is_gap and p.is_must_have and p.reframe_note:
                # Generate mitigation using reframe guidance
                mitigation = self._format_gap_mitigation(p)
                annotation_id = p.annotation_ids[0] if p.annotation_ids else None
                return mitigation, annotation_id

        # No must-have gaps with reframes - try any gap with reframe
        for p in priorities:
            if p.is_gap and p.reframe_note:
                mitigation = self._format_gap_mitigation(p)
                annotation_id = p.annotation_ids[0] if p.annotation_ids else None
                return mitigation, annotation_id

        return None, None

    def _format_gap_mitigation(self, priority: AnnotationPriority) -> str:
        """
        Format a gap mitigation clause using reframe note.

        Args:
            priority: The gap priority with reframe_note

        Returns:
            Formatted mitigation clause for summary
        """
        # Use reframe_to if available, otherwise extract from reframe_note
        if priority.reframe_to:
            return f"Strong foundation in {priority.reframe_to}"

        # Parse reframe_note for "Frame as X" pattern
        if priority.reframe_note:
            note = priority.reframe_note
            if "frame as" in note.lower():
                # Extract the framing
                idx = note.lower().find("frame as")
                framing = note[idx + 9:].strip().strip("'\"")
                return f"Strong foundation in {framing}"
            else:
                # Use the note as-is if it's short enough
                if len(note) <= 80:
                    return note

        return ""

    def _build_ats_requirements(self) -> Dict[str, ATSRequirement]:
        """
        Build ATS requirements from annotations.

        Extracts min/max occurrences, variants, and preferred sections
        from annotations.

        Returns:
            Dict mapping keyword to ATSRequirement
        """
        ats_reqs: Dict[str, ATSRequirement] = {}
        annotations = self.jd_annotations.get("annotations", [])

        for ann in annotations:
            # Skip inactive annotations (default to True for backward compatibility)
            if not ann.get("is_active", True):
                continue

            # Get keywords from annotation (with type coercion for LLM output)
            keywords = ann.get("suggested_keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",") if k.strip()]
            elif not isinstance(keywords, list):
                keywords = []

            variants = ann.get("ats_variants", [])
            if isinstance(variants, str):
                variants = [v.strip() for v in variants.split(",") if v.strip()]
            elif not isinstance(variants, list):
                variants = []

            min_occ = ann.get("min_occurrences", 2)
            max_occ = ann.get("max_occurrences", 4)

            preferred = ann.get("preferred_sections", [])
            if isinstance(preferred, str):
                preferred = [p.strip() for p in preferred.split(",") if p.strip()]
            elif not isinstance(preferred, list):
                preferred = []

            exact_phrase = ann.get("exact_phrase_match", False)

            for keyword in keywords:
                key = keyword.lower()
                if key not in ats_reqs:
                    ats_reqs[key] = ATSRequirement(
                        min_occurrences=min_occ or 2,
                        max_occurrences=max_occ or 4,
                        variants=list(set([keyword] + variants)),
                        preferred_sections=preferred,
                        exact_phrase=exact_phrase,
                    )
                else:
                    # Merge: take max of min requirements, min of max
                    existing = ats_reqs[key]
                    existing.min_occurrences = max(
                        existing.min_occurrences, min_occ or 2
                    )
                    existing.max_occurrences = min(
                        existing.max_occurrences, max_occ or 4
                    )
                    # Merge variants
                    existing.variants = list(
                        set(existing.variants + [keyword] + variants)
                    )
                    # Merge preferred sections
                    existing.preferred_sections = list(
                        set(existing.preferred_sections + preferred)
                    )
                    # Exact phrase is true if any annotation requires it
                    existing.exact_phrase = existing.exact_phrase or exact_phrase

        return ats_reqs

    def _build_keyword_targets(
        self,
        priorities: List[AnnotationPriority],
    ) -> Dict[str, int]:
        """
        Build keyword coverage targets from priorities.

        Must-have keywords should appear ≥2 times.
        Core strength keywords should appear 2-3 times.
        Other keywords target 1-2 mentions.

        Args:
            priorities: Ranked priorities

        Returns:
            Dict mapping keyword to target mention count
        """
        targets: Dict[str, int] = {}

        for p in priorities:
            # Determine target based on requirement type and relevance
            if p.is_must_have and p.is_core_strength:
                target = 3
            elif p.is_must_have:
                target = 2
            elif p.is_core_strength:
                target = 2
            else:
                target = 1

            # Add matching skill
            if p.matching_skill:
                key = p.matching_skill.lower()
                targets[key] = max(targets.get(key, 0), target)

            # Add ATS variants
            for variant in p.ats_variants:
                key = variant.lower()
                # Variants get slightly lower target
                targets[key] = max(targets.get(key, 0), max(1, target - 1))

        return targets


# =============================================================================
# PROMPT FORMATTING UTILITIES
# =============================================================================

def format_priorities_for_prompt(
    context: HeaderGenerationContext,
    max_items: int = 6,
) -> str:
    """
    Format annotation priorities for LLM prompt injection.

    Creates a structured list of must-haves and key requirements
    for the header/summary generation prompt.

    Enhanced with passion and identity dimensions:
    - Identity items go in headlines/introductions
    - Passion items show authentic enthusiasm
    - Avoid items should be de-emphasized

    Args:
        context: The HeaderGenerationContext
        max_items: Maximum items to include

    Returns:
        Formatted string for prompt injection
    """
    if not context.has_annotations:
        return ""

    lines = ["## JD Priority Requirements (from annotations)\n"]

    # NEW: Add explicit placement rules at the top for ATS optimization
    lines.append("### CRITICAL ATS PLACEMENT RULES")
    lines.append(
        "These rules are MANDATORY for ATS optimization and 6-7 second recruiter scan:"
    )
    lines.append("")

    # Identity keywords for headline
    if context.identity_priorities:
        lines.append("**HEADLINE MUST CONTAIN:**")
        for p in context.identity_priorities[:2]:
            skill = p.matching_skill or (p.jd_text[:30] if p.jd_text else "")
            if skill:
                lines.append(f"  - '{skill}' (core identity)")
        lines.append("")

    # Must-have keywords for first 50 words
    if context.must_have_priorities:
        lines.append("**FIRST 50 WORDS OF NARRATIVE MUST CONTAIN:**")
        for p in context.must_have_priorities[:3]:
            skill = p.matching_skill or (p.jd_text[:30] if p.jd_text else "")
            if skill:
                lines.append(f"  - '{skill}' (must-have requirement)")
        lines.append("")

    # Core strengths for competencies
    core_strengths = [
        p
        for p in context.priorities
        if p.relevance in ["core_strength", "extremely_relevant"]
    ]
    if core_strengths:
        lines.append("**CORE COMPETENCIES MUST INCLUDE:**")
        for p in core_strengths[:4]:
            skill = p.matching_skill or (p.jd_text[:30] if p.jd_text else "")
            if skill:
                lines.append(f"  - '{skill}'")
        lines.append("")

    lines.append("### PLACEMENT CHECKLIST (verify before output)")
    lines.append("[ ] Identity keywords appear in headline")
    lines.append("[ ] Must-have keywords appear in first 50 words of narrative")
    lines.append("[ ] Core strengths are in core competencies section")
    lines.append("[ ] Persona framing in opening statement")
    lines.append("")

    # Identity items first - these define WHO the candidate IS
    identity_items = context.identity_priorities[:3]
    if identity_items:
        lines.append("### CORE IDENTITY (use in headline and opening statement):")
        lines.append("These define who the candidate IS professionally:")
        for p in identity_items:
            skill_text = p.matching_skill or p.jd_text[:50]
            lines.append(f"- ⭐ {skill_text}")
        lines.append("")

    # Must-haves
    must_haves = context.must_have_priorities[:3]
    if must_haves:
        lines.append("### MUST-HAVE (emphasize in headline/tagline):")
        for p in must_haves:
            skill_text = p.matching_skill or p.jd_text[:50]
            proof = f" → Proof: {p.star_snippets[0]}" if p.star_snippets else ""
            passion_marker = " 🔥" if p.is_passion else ""
            lines.append(f"- {skill_text}{proof}{passion_marker}")
        lines.append("")

    # Passion items - show authentic enthusiasm
    passion_items = [p for p in context.passion_priorities[:3] if p not in must_haves]
    if passion_items:
        lines.append("### PASSION AREAS (emphasize to show authentic enthusiasm):")
        lines.append("Candidate is genuinely excited about these - highlight to sound authentic:")
        for p in passion_items:
            skill_text = p.matching_skill or p.jd_text[:50]
            lines.append(f"- 🔥 {skill_text}")
        lines.append("")

    # Core strengths
    core_strengths = [
        p for p in context.core_strength_priorities[:3]
        if p not in must_haves and p not in identity_items
    ]
    if core_strengths:
        lines.append("### CORE STRENGTHS (highlight in summary):")
        for p in core_strengths:
            skill_text = p.matching_skill or p.jd_text[:50]
            lines.append(f"- {skill_text}")
        lines.append("")

    # Reframe guidance
    if context.reframe_map:
        lines.append("### REFRAME GUIDANCE (apply to phrasing):")
        for skill, reframe in list(context.reframe_map.items())[:3]:
            lines.append(f"- \"{skill}\" → {reframe}")
        lines.append("")

    # Gap mitigation
    if context.gap_mitigation:
        lines.append("### GAP MITIGATION (include once in summary):")
        lines.append(f"- {context.gap_mitigation}")
        lines.append("")

    # Avoid items - these should NOT be prominent
    avoid_items = context.avoid_priorities[:2]
    if avoid_items:
        lines.append("### AVOID/DE-EMPHASIZE (do NOT highlight these):")
        lines.append("Candidate can do these but doesn't want them prominent:")
        for p in avoid_items:
            skill_text = p.matching_skill or p.jd_text[:50]
            lines.append(f"- 🚫 {skill_text}")
        lines.append("")

    # Not-identity items - avoid in introductions
    not_identity_items = context.not_identity_priorities[:2]
    if not_identity_items:
        lines.append("### NOT IDENTITY (avoid in headlines/intros):")
        lines.append("Do NOT use these to introduce the candidate:")
        for p in not_identity_items:
            skill_text = p.matching_skill or p.jd_text[:50]
            lines.append(f"- ✗ {skill_text}")
        lines.append("")

    return "\n".join(lines)


def format_ats_guidance_for_prompt(context: HeaderGenerationContext) -> str:
    """
    Format ATS requirements for LLM prompt injection.

    Creates guidance on keyword usage and variants.

    Args:
        context: The HeaderGenerationContext

    Returns:
        Formatted string for prompt injection
    """
    if not context.ats_requirements:
        return ""

    lines = ["## ATS Keyword Requirements\n"]
    lines.append("Include BOTH acronym AND full form for these keywords:")

    for keyword, req in list(context.ats_requirements.items())[:10]:
        if len(req.variants) > 1:
            variants_str = " / ".join(req.variants[:3])
            lines.append(f"- {variants_str} (target: {req.min_occurrences}-{req.max_occurrences}x)")
        else:
            lines.append(f"- {keyword} (target: {req.min_occurrences}-{req.max_occurrences}x)")

    return "\n".join(lines)


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def build_header_context(
    jd_annotations: Optional[Dict[str, Any]],
    all_stars: Optional[List[STARRecord]] = None,
) -> HeaderGenerationContext:
    """
    Convenience function to build HeaderGenerationContext.

    Args:
        jd_annotations: JDAnnotations dict from job state
        all_stars: Full STAR library (optional)

    Returns:
        HeaderGenerationContext ready for header generation
    """
    builder = AnnotationHeaderContextBuilder(jd_annotations, all_stars)
    return builder.build_context()
