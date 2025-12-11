"""
Annotation Boost Calculator for Pipeline Integration.

This module provides functions to calculate boost multipliers from JD annotations
and apply them to scoring algorithms throughout the pipeline.

Key concepts:
- Annotations with `is_active=True` influence scoring
- Multiple annotations can affect the same item (conflict resolution applies)
- Boost formula: relevance_mult × requirement_mult × priority_mult
- Keywords from annotations get injected into scoring algorithms

Usage:
    from src.common.annotation_boost import AnnotationBoostCalculator

    calculator = AnnotationBoostCalculator(annotations)
    boost = calculator.get_boost_for_text("Python programming")
    keywords = calculator.get_annotation_keywords()
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field

from src.common.annotation_types import (
    JDAnnotation,
    JDAnnotations,
    RELEVANCE_MULTIPLIERS,
    REQUIREMENT_MULTIPLIERS,
    PASSION_MULTIPLIERS,
    IDENTITY_MULTIPLIERS,
    PRIORITY_MULTIPLIERS,
    TYPE_MODIFIERS,
)


@dataclass
class BoostResult:
    """
    Result of boost calculation for a single item.
    """
    boost: float                                # Final multiplier (e.g., 3.0)
    contributing_annotations: List[str]         # IDs of annotations that contributed
    matched_keywords: List[str]                 # Keywords that matched
    reframe_notes: List[str]                    # Applicable reframe guidance
    is_disqualifier: bool = False               # True if any annotation is a disqualifier


@dataclass
class AnnotationContext:
    """
    Pre-computed annotation context for efficient lookups.
    """
    active_annotations: List[JDAnnotation]
    keywords_to_annotations: Dict[str, List[JDAnnotation]]
    star_id_to_annotations: Dict[str, List[JDAnnotation]]
    all_keywords: Set[str]
    all_ats_variants: Set[str]
    gap_annotations: List[JDAnnotation]
    core_strength_annotations: List[JDAnnotation]
    # New: passion and identity indexes
    passion_love_it_annotations: List[JDAnnotation] = field(default_factory=list)
    passion_avoid_annotations: List[JDAnnotation] = field(default_factory=list)
    identity_core_annotations: List[JDAnnotation] = field(default_factory=list)
    identity_not_me_annotations: List[JDAnnotation] = field(default_factory=list)


class AnnotationBoostCalculator:
    """
    Calculates boost multipliers from JD annotations.

    This is the central class for annotation influence on the pipeline.
    It pre-computes indexes for efficient lookup during scoring.
    """

    def __init__(
        self,
        jd_annotations: Optional[Dict[str, Any]] = None,
        conflict_resolution: str = "max_boost",
    ):
        """
        Initialize the boost calculator.

        Args:
            jd_annotations: JDAnnotations dict from job state
            conflict_resolution: How to resolve overlapping annotations
                - "max_boost": Use highest boost (default)
                - "avg_boost": Average all boosts
                - "last_write": Most recent annotation wins
        """
        self.conflict_resolution = conflict_resolution
        self.context = self._build_context(jd_annotations)

    def _build_context(self, jd_annotations: Optional[Dict[str, Any]]) -> AnnotationContext:
        """Build pre-computed indexes for efficient lookup."""
        active_annotations: List[JDAnnotation] = []
        keywords_to_annotations: Dict[str, List[JDAnnotation]] = {}
        star_id_to_annotations: Dict[str, List[JDAnnotation]] = {}
        all_keywords: Set[str] = set()
        all_ats_variants: Set[str] = set()
        gap_annotations: List[JDAnnotation] = []
        core_strength_annotations: List[JDAnnotation] = []
        # New: passion and identity tracking
        passion_love_it_annotations: List[JDAnnotation] = []
        passion_avoid_annotations: List[JDAnnotation] = []
        identity_core_annotations: List[JDAnnotation] = []
        identity_not_me_annotations: List[JDAnnotation] = []

        if not jd_annotations:
            return AnnotationContext(
                active_annotations=[],
                keywords_to_annotations={},
                star_id_to_annotations={},
                all_keywords=set(),
                all_ats_variants=set(),
                gap_annotations=[],
                core_strength_annotations=[],
            )

        annotations = jd_annotations.get("annotations", [])

        for ann in annotations:
            # Only process active annotations (default to True for backward compatibility)
            if not ann.get("is_active", True):
                continue

            active_annotations.append(ann)

            # Index by relevance level
            relevance = ann.get("relevance")
            if relevance == "gap":
                gap_annotations.append(ann)
            elif relevance == "core_strength":
                core_strength_annotations.append(ann)

            # Index by passion level
            passion = ann.get("passion")
            if passion == "love_it":
                passion_love_it_annotations.append(ann)
            elif passion == "avoid":
                passion_avoid_annotations.append(ann)

            # Index by identity level
            identity = ann.get("identity")
            if identity == "core_identity":
                identity_core_annotations.append(ann)
            elif identity == "not_identity":
                identity_not_me_annotations.append(ann)

            # Index keywords
            for keyword in ann.get("suggested_keywords", []):
                keyword_lower = keyword.lower()
                all_keywords.add(keyword_lower)
                if keyword_lower not in keywords_to_annotations:
                    keywords_to_annotations[keyword_lower] = []
                keywords_to_annotations[keyword_lower].append(ann)

            # Index ATS variants
            for variant in ann.get("ats_variants", []):
                all_ats_variants.add(variant.lower())

            # Index by STAR ID
            for star_id in ann.get("star_ids", []):
                if star_id not in star_id_to_annotations:
                    star_id_to_annotations[star_id] = []
                star_id_to_annotations[star_id].append(ann)

        return AnnotationContext(
            active_annotations=active_annotations,
            keywords_to_annotations=keywords_to_annotations,
            star_id_to_annotations=star_id_to_annotations,
            all_keywords=all_keywords,
            all_ats_variants=all_ats_variants,
            gap_annotations=gap_annotations,
            core_strength_annotations=core_strength_annotations,
            passion_love_it_annotations=passion_love_it_annotations,
            passion_avoid_annotations=passion_avoid_annotations,
            identity_core_annotations=identity_core_annotations,
            identity_not_me_annotations=identity_not_me_annotations,
        )

    def calculate_boost(self, annotation: JDAnnotation) -> float:
        """
        Calculate the boost multiplier for a single annotation.

        Formula: relevance_mult × requirement_mult × passion_mult × identity_mult × priority_mult × type_mod

        The new dimensions (passion and identity) provide:
        - Passion: How excited the candidate is about this aspect (love_it=1.5x to avoid=0.5x)
        - Identity: How strongly this defines professional identity (core_identity=2.0x to not_identity=0.3x)

        Args:
            annotation: The annotation to calculate boost for

        Returns:
            Float multiplier (e.g., 3.0 for core_strength + must_have)
        """
        # Get base multipliers with defaults
        relevance = annotation.get("relevance", "relevant")
        requirement = annotation.get("requirement_type", "neutral")
        passion = annotation.get("passion", "neutral")
        identity = annotation.get("identity", "peripheral")
        priority = annotation.get("priority", 3)
        ann_type = annotation.get("annotation_type", "skill_match")

        # Handle disqualifier (always returns 0)
        if requirement == "disqualifier":
            return 0.0

        relevance_mult = RELEVANCE_MULTIPLIERS.get(relevance, 1.0)
        requirement_mult = REQUIREMENT_MULTIPLIERS.get(requirement, 1.0)
        passion_mult = PASSION_MULTIPLIERS.get(passion, 1.0)
        identity_mult = IDENTITY_MULTIPLIERS.get(identity, 1.0)
        priority_mult = PRIORITY_MULTIPLIERS.get(priority, 1.0)
        type_mod = TYPE_MODIFIERS.get(ann_type, 1.0)

        return relevance_mult * requirement_mult * passion_mult * identity_mult * priority_mult * type_mod

    def get_boost_for_star(self, star_id: str) -> BoostResult:
        """
        Get boost for a specific STAR record.

        Used by Layer 2.5 (STAR Selector) to prioritize STAR records
        that have been linked to annotations.

        Args:
            star_id: The STAR record ID

        Returns:
            BoostResult with boost multiplier and metadata
        """
        annotations = self.context.star_id_to_annotations.get(star_id, [])

        if not annotations:
            return BoostResult(
                boost=1.0,
                contributing_annotations=[],
                matched_keywords=[],
                reframe_notes=[],
            )

        return self._calculate_combined_boost(annotations)

    def get_boost_for_text(self, text: str) -> BoostResult:
        """
        Get boost based on keyword matches in text.

        Used by variant selector to boost variants that contain
        keywords from annotations.

        Args:
            text: The text to check for keyword matches

        Returns:
            BoostResult with boost multiplier and metadata
        """
        text_lower = text.lower()
        matching_annotations: List[JDAnnotation] = []
        matched_keywords: Set[str] = set()

        # Check each keyword
        for keyword, annotations in self.context.keywords_to_annotations.items():
            if keyword in text_lower:
                matching_annotations.extend(annotations)
                matched_keywords.add(keyword)

        # Also check ATS variants
        for variant in self.context.all_ats_variants:
            if variant in text_lower:
                matched_keywords.add(variant)

        if not matching_annotations:
            return BoostResult(
                boost=1.0,
                contributing_annotations=[],
                matched_keywords=list(matched_keywords),
                reframe_notes=[],
            )

        result = self._calculate_combined_boost(matching_annotations)
        result.matched_keywords = list(matched_keywords)
        return result

    def get_boost_for_skill(self, skill: str) -> BoostResult:
        """
        Get boost for a specific skill.

        Args:
            skill: The skill name to check

        Returns:
            BoostResult with boost multiplier and metadata
        """
        skill_lower = skill.lower()
        annotations = self.context.keywords_to_annotations.get(skill_lower, [])

        if not annotations:
            return BoostResult(
                boost=1.0,
                contributing_annotations=[],
                matched_keywords=[skill] if skill_lower in self.context.all_keywords else [],
                reframe_notes=[],
            )

        return self._calculate_combined_boost(annotations)

    def _calculate_combined_boost(self, annotations: List[JDAnnotation]) -> BoostResult:
        """
        Calculate combined boost from multiple annotations.

        Uses conflict resolution strategy to combine boosts.
        """
        if not annotations:
            return BoostResult(
                boost=1.0,
                contributing_annotations=[],
                matched_keywords=[],
                reframe_notes=[],
            )

        # Deduplicate annotations by ID
        seen_ids: Set[str] = set()
        unique_annotations: List[JDAnnotation] = []
        for ann in annotations:
            ann_id = ann.get("id", "")
            if ann_id and ann_id not in seen_ids:
                seen_ids.add(ann_id)
                unique_annotations.append(ann)

        # Calculate individual boosts
        boosts: List[float] = []
        contributing_ids: List[str] = []
        reframe_notes: List[str] = []
        is_disqualifier = False

        for ann in unique_annotations:
            boost = self.calculate_boost(ann)

            if boost == 0.0:
                is_disqualifier = True

            boosts.append(boost)
            contributing_ids.append(ann.get("id", ""))

            # Collect reframe notes
            if ann.get("has_reframe") and ann.get("reframe_note"):
                reframe_notes.append(ann["reframe_note"])

        # If any annotation is a disqualifier, return 0
        if is_disqualifier:
            return BoostResult(
                boost=0.0,
                contributing_annotations=contributing_ids,
                matched_keywords=[],
                reframe_notes=reframe_notes,
                is_disqualifier=True,
            )

        # Apply conflict resolution
        if self.conflict_resolution == "max_boost":
            final_boost = max(boosts) if boosts else 1.0
        elif self.conflict_resolution == "avg_boost":
            final_boost = sum(boosts) / len(boosts) if boosts else 1.0
        else:  # last_write - use last annotation
            final_boost = boosts[-1] if boosts else 1.0

        return BoostResult(
            boost=final_boost,
            contributing_annotations=contributing_ids,
            matched_keywords=[],
            reframe_notes=reframe_notes,
        )

    def get_annotation_keywords(self) -> Set[str]:
        """
        Get all keywords from active annotations.

        Used to inject annotation keywords into JD keyword lists
        for variant scoring.

        Returns:
            Set of all keywords (lowercase)
        """
        return self.context.all_keywords

    def get_annotation_keywords_with_variants(self) -> Set[str]:
        """
        Get all keywords including ATS variants.

        Returns:
            Set of keywords and their variants (lowercase)
        """
        return self.context.all_keywords | self.context.all_ats_variants

    def get_reframe_guidance(self, text: str) -> List[str]:
        """
        Get reframe guidance notes applicable to text.

        Used to provide reframe context in CV bullet generation.

        Args:
            text: Text to check for applicable reframe guidance

        Returns:
            List of reframe notes that apply
        """
        boost_result = self.get_boost_for_text(text)
        return boost_result.reframe_notes

    def get_gaps(self) -> List[JDAnnotation]:
        """
        Get all gap annotations.

        Used for gap analysis and interview prep.

        Returns:
            List of gap annotations
        """
        return self.context.gap_annotations

    def get_core_strengths(self) -> List[JDAnnotation]:
        """
        Get all core strength annotations.

        Used to highlight strongest matches in CV.

        Returns:
            List of core_strength annotations
        """
        return self.context.core_strength_annotations

    def get_passions(self) -> List[JDAnnotation]:
        """
        Get all annotations marked as 'love_it' passion.

        Used to highlight areas of genuine enthusiasm in CV/cover letter.
        These should be emphasized to show authentic interest.

        Returns:
            List of passion=love_it annotations
        """
        return self.context.passion_love_it_annotations

    def get_avoid_areas(self) -> List[JDAnnotation]:
        """
        Get all annotations marked as 'avoid' passion.

        Used to de-emphasize areas the candidate wants to avoid.
        These should NOT be prominent in CV/cover letter.

        Returns:
            List of passion=avoid annotations
        """
        return self.context.passion_avoid_annotations

    def get_identity_core(self) -> List[JDAnnotation]:
        """
        Get all annotations marked as 'core_identity'.

        Used to build headline, tagline, and opening paragraph.
        These define who the candidate IS professionally.

        Returns:
            List of identity=core_identity annotations
        """
        return self.context.identity_core_annotations

    def get_identity_not_me(self) -> List[JDAnnotation]:
        """
        Get all annotations marked as 'not_identity'.

        Used to AVOID in introductions and headlines.
        Candidate explicitly does NOT want to be seen this way.

        Returns:
            List of identity=not_identity annotations
        """
        return self.context.identity_not_me_annotations

    def has_annotations(self) -> bool:
        """Check if there are any active annotations."""
        return len(self.context.active_annotations) > 0

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics about annotations."""
        return {
            "total_active": len(self.context.active_annotations),
            "core_strengths": len(self.context.core_strength_annotations),
            "gaps": len(self.context.gap_annotations),
            "passions_love_it": len(self.context.passion_love_it_annotations),
            "passions_avoid": len(self.context.passion_avoid_annotations),
            "identity_core": len(self.context.identity_core_annotations),
            "identity_not_me": len(self.context.identity_not_me_annotations),
            "total_keywords": len(self.context.all_keywords),
            "total_ats_variants": len(self.context.all_ats_variants),
            "stars_linked": len(self.context.star_id_to_annotations),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_annotation_boost(
    jd_annotations: Optional[Dict[str, Any]],
    star_id: Optional[str] = None,
    text: Optional[str] = None,
    skill: Optional[str] = None,
) -> float:
    """
    Convenience function to get boost multiplier.

    Args:
        jd_annotations: JDAnnotations from job state
        star_id: Optional STAR ID to get boost for
        text: Optional text to check for keyword matches
        skill: Optional skill name to check

    Returns:
        Float boost multiplier (1.0 if no match)
    """
    calculator = AnnotationBoostCalculator(jd_annotations)

    if star_id:
        return calculator.get_boost_for_star(star_id).boost
    elif text:
        return calculator.get_boost_for_text(text).boost
    elif skill:
        return calculator.get_boost_for_skill(skill).boost

    return 1.0


def get_annotation_keywords(jd_annotations: Optional[Dict[str, Any]]) -> Set[str]:
    """
    Convenience function to get all annotation keywords.

    Args:
        jd_annotations: JDAnnotations from job state

    Returns:
        Set of keywords (lowercase)
    """
    calculator = AnnotationBoostCalculator(jd_annotations)
    return calculator.get_annotation_keywords_with_variants()


def apply_annotation_boost_to_score(
    base_score: float,
    jd_annotations: Optional[Dict[str, Any]],
    text: str,
) -> Tuple[float, BoostResult]:
    """
    Apply annotation boost to a base score.

    Args:
        base_score: The original score
        jd_annotations: JDAnnotations from job state
        text: Text to match against annotation keywords

    Returns:
        Tuple of (boosted_score, BoostResult)
    """
    calculator = AnnotationBoostCalculator(jd_annotations)
    boost_result = calculator.get_boost_for_text(text)
    boosted_score = base_score * boost_result.boost
    return boosted_score, boost_result
