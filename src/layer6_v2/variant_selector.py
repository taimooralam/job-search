"""
Variant Selector for CV Generation.

Selects optimal achievement variants based on JD requirements using a
weighted scoring algorithm that considers:
- Keyword overlap (40%)
- Pain point alignment (30%)
- Role category match (20%)
- Achievement keywords (10%)

Phase 4 Enhancement: Integrates JD annotation boost to prioritize variants
that contain keywords from annotations and applies reframe guidance.

This replaces LLM-based bullet generation with deterministic selection
from pre-written, interview-defensible variants.

Usage:
    selector = VariantSelector()
    selected = selector.select_variants(
        role=enhanced_role,
        extracted_jd=jd_data,
        target_count=5,
        jd_annotations=annotations,  # Phase 4
    )
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple, Any

from src.common.logger import get_logger
from src.common.annotation_boost import AnnotationBoostCalculator, BoostResult
from src.layer6_v2.variant_parser import (
    Achievement,
    AchievementVariant,
    EnhancedRoleData,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Variant type preferences by role category
# Maps JD role categories to preferred variant types (in priority order)
VARIANT_PREFERENCES: Dict[str, List[str]] = {
    # IC Track - emphasize technical depth
    "staff_principal_engineer": ["Technical", "Architecture", "Impact", "Short"],
    "software_architect": ["Architecture", "Technical", "Impact", "Short"],
    "senior_engineer": ["Technical", "Impact", "Architecture", "Short"],

    # Management Track - emphasize leadership and impact
    "engineering_manager": ["Leadership", "Impact", "Technical", "Short"],
    "director_of_engineering": ["Leadership", "Impact", "Architecture", "Strategy"],
    "head_of_engineering": ["Leadership", "Architecture", "Impact", "Strategy"],
    "vp_engineering": ["Leadership", "Strategy", "Impact", "Architecture"],
    "cto": ["Architecture", "Leadership", "Strategy", "Impact"],

    # Hybrid roles
    "tech_lead": ["Technical", "Leadership", "Architecture", "Impact"],
    "principal_engineer": ["Architecture", "Technical", "Leadership", "Impact"],

    # Default fallback
    "default": ["Technical", "Impact", "Architecture", "Short"],
}

# Scoring weights
WEIGHT_KEYWORD_OVERLAP = 0.40
WEIGHT_PAIN_POINT = 0.30
WEIGHT_ROLE_CATEGORY = 0.20
WEIGHT_ACHIEVEMENT_KEYWORDS = 0.10


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class VariantScore:
    """
    Detailed scoring breakdown for a single variant.

    Tracks individual score components for debugging and transparency.
    Phase 4: Includes annotation boost tracking.
    """

    achievement_id: str
    variant_type: str
    variant_text: str

    # Individual score components
    keyword_score: float = 0.0
    pain_point_score: float = 0.0
    role_category_score: float = 0.0
    achievement_keyword_score: float = 0.0

    # Matched items for debugging
    matched_keywords: List[str] = field(default_factory=list)
    matched_pain_point: str = ""

    # Phase 4: Annotation boost tracking
    annotation_boost: float = 1.0
    annotation_keywords_matched: List[str] = field(default_factory=list)
    annotation_ids: List[str] = field(default_factory=list)
    reframe_notes: List[str] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        """Calculate weighted total score with annotation boost."""
        base_score = (
            self.keyword_score * WEIGHT_KEYWORD_OVERLAP +
            self.pain_point_score * WEIGHT_PAIN_POINT +
            self.role_category_score * WEIGHT_ROLE_CATEGORY +
            self.achievement_keyword_score * WEIGHT_ACHIEVEMENT_KEYWORDS
        )
        # Phase 4: Apply annotation boost multiplier
        return base_score * self.annotation_boost

    @property
    def word_count(self) -> int:
        """Get word count of the variant text."""
        return len(self.variant_text.split())

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "achievement_id": self.achievement_id,
            "variant_type": self.variant_type,
            "total_score": round(self.total_score, 3),
            "keyword_score": round(self.keyword_score, 3),
            "pain_point_score": round(self.pain_point_score, 3),
            "role_category_score": round(self.role_category_score, 3),
            "achievement_keyword_score": round(self.achievement_keyword_score, 3),
            "matched_keywords": self.matched_keywords,
            "matched_pain_point": self.matched_pain_point,
            "word_count": self.word_count,
            # Phase 4: Annotation tracking
            "annotation_boost": round(self.annotation_boost, 3),
            "annotation_keywords_matched": self.annotation_keywords_matched,
            "annotation_ids": self.annotation_ids,
            "reframe_notes": self.reframe_notes,
        }


@dataclass
class SelectedVariant:
    """
    A variant that has been selected for inclusion in the CV.

    Includes the variant text, score, and traceability information.
    Phase 4: Includes annotation influence metadata.
    """

    achievement_id: str
    achievement_title: str
    variant_type: str
    text: str
    score: VariantScore

    # Traceability
    core_fact: str  # Original fact for interview prep
    keywords: List[str]  # Achievement keywords

    # Phase 4: Annotation traceability
    annotation_influenced: bool = False
    annotation_ids: List[str] = field(default_factory=list)
    annotation_keywords_used: List[str] = field(default_factory=list)
    reframe_applied: Optional[str] = None

    @property
    def total_score(self) -> float:
        """Get the total weighted score."""
        return self.score.total_score

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "achievement_id": self.achievement_id,
            "achievement_title": self.achievement_title,
            "variant_type": self.variant_type,
            "text": self.text,
            "total_score": round(self.total_score, 3),
            "score_breakdown": self.score.to_dict(),
            "core_fact": self.core_fact,
            "keywords": self.keywords,
            # Phase 4: Annotation traceability
            "annotation_influenced": self.annotation_influenced,
            "annotation_ids": self.annotation_ids,
            "annotation_keywords_used": self.annotation_keywords_used,
            "reframe_applied": self.reframe_applied,
        }


@dataclass
class SelectionResult:
    """
    Complete result of variant selection for a role.

    Contains selected variants and metadata about the selection process.
    """

    role_id: str
    company: str
    title: str
    period: str
    location: str

    selected_variants: List[SelectedVariant]

    # Selection metadata
    total_achievements: int
    total_variants_considered: int
    target_count: int

    # Coverage metrics
    jd_keywords_covered: List[str] = field(default_factory=list)
    jd_keywords_missing: List[str] = field(default_factory=list)

    @property
    def selection_count(self) -> int:
        """Get number of selected variants."""
        return len(self.selected_variants)

    @property
    def average_score(self) -> float:
        """Calculate average score of selected variants."""
        if not self.selected_variants:
            return 0.0
        return sum(v.total_score for v in self.selected_variants) / len(self.selected_variants)

    @property
    def keyword_coverage(self) -> float:
        """Calculate keyword coverage percentage."""
        total = len(self.jd_keywords_covered) + len(self.jd_keywords_missing)
        if total == 0:
            return 0.0
        return len(self.jd_keywords_covered) / total

    def get_bullet_texts(self) -> List[str]:
        """Get just the bullet texts for CV assembly."""
        return [v.text for v in self.selected_variants]

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "role_id": self.role_id,
            "company": self.company,
            "title": self.title,
            "period": self.period,
            "location": self.location,
            "selected_variants": [v.to_dict() for v in self.selected_variants],
            "selection_count": self.selection_count,
            "average_score": round(self.average_score, 3),
            "total_achievements": self.total_achievements,
            "total_variants_considered": self.total_variants_considered,
            "target_count": self.target_count,
            "keyword_coverage": round(self.keyword_coverage, 3),
            "jd_keywords_covered": self.jd_keywords_covered,
            "jd_keywords_missing": self.jd_keywords_missing,
        }


# ============================================================================
# SELECTOR CLASS
# ============================================================================

class VariantSelector:
    """
    Selects optimal achievement variants based on JD requirements.

    Uses a weighted scoring algorithm considering:
    - Keyword overlap between variant text and JD keywords
    - Pain point alignment between achievement and JD pain points
    - Role category match (IC vs management track)
    - Achievement-level keyword relevance
    """

    def __init__(
        self,
        keyword_weight: float = WEIGHT_KEYWORD_OVERLAP,
        pain_point_weight: float = WEIGHT_PAIN_POINT,
        role_category_weight: float = WEIGHT_ROLE_CATEGORY,
        achievement_keyword_weight: float = WEIGHT_ACHIEVEMENT_KEYWORDS,
    ):
        """
        Initialize the selector with custom weights.

        Args:
            keyword_weight: Weight for JD keyword overlap (default 0.40)
            pain_point_weight: Weight for pain point alignment (default 0.30)
            role_category_weight: Weight for role category match (default 0.20)
            achievement_keyword_weight: Weight for achievement keywords (default 0.10)
        """
        self._logger = get_logger(__name__)

        self.keyword_weight = keyword_weight
        self.pain_point_weight = pain_point_weight
        self.role_category_weight = role_category_weight
        self.achievement_keyword_weight = achievement_keyword_weight

    def select_variants(
        self,
        role: EnhancedRoleData,
        extracted_jd: Dict,
        target_count: int = 5,
        min_score: float = 0.1,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> SelectionResult:
        """
        Select optimal variants for a role based on JD requirements.

        Phase 4 Enhancement: Integrates annotation boost and keywords.

        Args:
            role: Enhanced role data with achievements and variants
            extracted_jd: Extracted JD data with keywords, pain points, etc.
            target_count: Target number of bullets to select
            min_score: Minimum score threshold for inclusion
            jd_annotations: Optional JDAnnotations for boost calculation

        Returns:
            SelectionResult with selected variants and metadata
        """
        self._logger.debug(f"Selecting variants for {role.metadata.company}")

        # Phase 4: Create annotation calculator
        annotation_calculator = AnnotationBoostCalculator(jd_annotations) if jd_annotations else None

        # Extract JD data
        jd_keywords = self._extract_jd_keywords(extracted_jd)

        # Phase 4: Inject annotation keywords into JD keywords
        if annotation_calculator and annotation_calculator.has_annotations():
            annotation_keywords = annotation_calculator.get_annotation_keywords_with_variants()
            jd_keywords = jd_keywords | annotation_keywords
            stats = annotation_calculator.get_stats()
            self._logger.info(
                f"📌 Annotation boost ACTIVE: {stats['total_keywords']} keywords injected"
            )

        pain_points = extracted_jd.get("implied_pain_points", [])
        role_category = extracted_jd.get("role_category", "default")

        # Score all variants
        all_scores: List[Tuple[Achievement, AchievementVariant, VariantScore]] = []

        for achievement in role.achievements:
            for variant_type, variant in achievement.variants.items():
                score = self._score_variant(
                    achievement=achievement,
                    variant=variant,
                    jd_keywords=jd_keywords,
                    pain_points=pain_points,
                    role_category=role_category,
                    annotation_calculator=annotation_calculator,
                )
                all_scores.append((achievement, variant, score))

        # Sort by total score (descending)
        all_scores.sort(key=lambda x: x[2].total_score, reverse=True)

        # Select top variants, avoiding duplicates from same achievement
        selected: List[SelectedVariant] = []
        selected_achievement_ids: Set[str] = set()

        for achievement, variant, score in all_scores:
            # Skip if we already selected from this achievement
            if achievement.id in selected_achievement_ids:
                continue

            # Skip if below minimum score
            if score.total_score < min_score:
                continue

            # Phase 4: Determine if annotation influenced this selection
            annotation_influenced = score.annotation_boost != 1.0
            reframe_applied = score.reframe_notes[0] if score.reframe_notes else None

            # Add to selection
            selected.append(SelectedVariant(
                achievement_id=achievement.id,
                achievement_title=achievement.title,
                variant_type=variant.variant_type,
                text=variant.text,
                score=score,
                core_fact=achievement.core_fact,
                keywords=achievement.keywords,
                # Phase 4: Annotation traceability
                annotation_influenced=annotation_influenced,
                annotation_ids=score.annotation_ids,
                annotation_keywords_used=score.annotation_keywords_matched,
                reframe_applied=reframe_applied,
            ))
            selected_achievement_ids.add(achievement.id)

            # Stop when we reach target count
            if len(selected) >= target_count:
                break

        # Calculate keyword coverage
        covered, missing = self._calculate_keyword_coverage(selected, jd_keywords)

        result = SelectionResult(
            role_id=role.id,
            company=role.metadata.company,
            title=role.metadata.title,
            period=role.metadata.period,
            location=role.metadata.location,
            selected_variants=selected,
            total_achievements=role.achievement_count,
            total_variants_considered=role.total_variants,
            target_count=target_count,
            jd_keywords_covered=covered,
            jd_keywords_missing=missing,
        )

        # Phase 4: Log annotation influence
        annotation_count = sum(1 for v in selected if v.annotation_influenced)
        if annotation_count > 0:
            self._logger.info(
                f"📌 {annotation_count}/{len(selected)} variants influenced by annotations"
            )

        self._logger.info(
            f"Selected {result.selection_count}/{target_count} variants for {role.metadata.company} "
            f"(avg score: {result.average_score:.2f}, keyword coverage: {result.keyword_coverage:.0%})"
        )

        return result

    def _score_variant(
        self,
        achievement: Achievement,
        variant: AchievementVariant,
        jd_keywords: Set[str],
        pain_points: List[str],
        role_category: str,
        annotation_calculator: Optional[AnnotationBoostCalculator] = None,
    ) -> VariantScore:
        """
        Score a single variant against JD requirements.

        Phase 4 Enhancement: Applies annotation boost to variant score.

        Args:
            achievement: The parent achievement
            variant: The variant to score
            jd_keywords: Set of JD keywords (lowercase)
            pain_points: List of JD pain points
            role_category: JD role category
            annotation_calculator: Optional calculator for annotation boost

        Returns:
            VariantScore with detailed breakdown
        """
        score = VariantScore(
            achievement_id=achievement.id,
            variant_type=variant.variant_type,
            variant_text=variant.text,
        )

        # 1. Keyword overlap score (40%)
        variant_words = self._extract_words(variant.text)
        matched_keywords = jd_keywords & variant_words
        if jd_keywords:
            score.keyword_score = len(matched_keywords) / len(jd_keywords)
        score.matched_keywords = list(matched_keywords)

        # 2. Pain point alignment score (30%)
        if pain_points:
            best_pain_match = 0.0
            best_pain_point = ""
            for pain_point in pain_points:
                similarity = self._text_similarity(variant.text, pain_point)
                if similarity > best_pain_match:
                    best_pain_match = similarity
                    best_pain_point = pain_point
            score.pain_point_score = best_pain_match
            score.matched_pain_point = best_pain_point if best_pain_match > 0.1 else ""
        else:
            score.pain_point_score = 0.5  # Neutral if no pain points

        # 3. Role category match score (20%)
        preferred_types = VARIANT_PREFERENCES.get(
            role_category,
            VARIANT_PREFERENCES["default"]
        )
        if variant.variant_type in preferred_types:
            # Score based on position in preference list
            position = preferred_types.index(variant.variant_type)
            score.role_category_score = 1.0 - (position * 0.2)
        else:
            score.role_category_score = 0.3  # Low score for non-preferred types

        # 4. Achievement keyword match score (10%)
        achievement_keywords = set(k.lower() for k in achievement.keywords)
        achievement_match = achievement_keywords & jd_keywords
        if achievement_keywords:
            score.achievement_keyword_score = len(achievement_match) / len(achievement_keywords)

        # Phase 4: Apply annotation boost
        if annotation_calculator and annotation_calculator.has_annotations():
            boost_result = annotation_calculator.get_boost_for_text(variant.text)
            score.annotation_boost = boost_result.boost
            score.annotation_keywords_matched = boost_result.matched_keywords
            score.annotation_ids = boost_result.contributing_annotations
            score.reframe_notes = boost_result.reframe_notes

        return score

    def _extract_jd_keywords(self, extracted_jd: Dict) -> Set[str]:
        """Extract and normalize all keywords from JD."""
        keywords = set()

        # Top keywords
        for kw in extracted_jd.get("top_keywords", []):
            keywords.add(kw.lower())

        # Technical skills
        for skill in extracted_jd.get("technical_skills", []):
            keywords.add(skill.lower())

        # Soft skills
        for skill in extracted_jd.get("soft_skills", []):
            keywords.add(skill.lower())

        return keywords

    def _extract_words(self, text: str) -> Set[str]:
        """Extract normalized words from text."""
        # Lowercase and extract words
        text = text.lower()
        words = re.findall(r'\b[a-z][a-z0-9+#]*\b', text)
        return set(words)

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        text1 = text1.lower()
        text2 = text2.lower()
        return SequenceMatcher(None, text1, text2).ratio()

    def _calculate_keyword_coverage(
        self,
        selected: List[SelectedVariant],
        jd_keywords: Set[str],
    ) -> Tuple[List[str], List[str]]:
        """Calculate which JD keywords are covered by selected variants."""
        covered = set()

        for variant in selected:
            variant_words = self._extract_words(variant.text)
            covered.update(jd_keywords & variant_words)

        missing = jd_keywords - covered
        return sorted(covered), sorted(missing)

    def select_with_selection_guide(
        self,
        role: EnhancedRoleData,
        extracted_jd: Dict,
        target_count: int = 5,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> SelectionResult:
        """
        Select variants using the role's selection guide if available.

        Phase 4: Supports JD annotations for boost calculation.

        The selection guide maps JD emphasis areas to recommended achievements.
        This is used as a hint to prioritize certain achievements.

        Args:
            role: Enhanced role data with achievements and selection guide
            extracted_jd: Extracted JD data
            target_count: Target number of bullets
            jd_annotations: Optional JDAnnotations for boost calculation

        Returns:
            SelectionResult with selected variants
        """
        if not role.selection_guide:
            return self.select_variants(role, extracted_jd, target_count, jd_annotations=jd_annotations)

        # Get role category and check selection guide
        role_category = extracted_jd.get("role_category", "")
        recommended_ids = role.selection_guide.get_recommended(role_category)

        if not recommended_ids:
            # Fall back to standard selection
            return self.select_variants(role, extracted_jd, target_count, jd_annotations=jd_annotations)

        self._logger.debug(
            f"Using selection guide for {role_category}: {recommended_ids}"
        )

        # Create a modified role with recommended achievements first
        # This ensures recommended achievements get priority
        prioritized_achievements = []
        other_achievements = []

        for achievement in role.achievements:
            if achievement.id in recommended_ids:
                prioritized_achievements.append(achievement)
            else:
                other_achievements.append(achievement)

        # Temporarily reorder achievements
        original_order = role.achievements
        role.achievements = prioritized_achievements + other_achievements

        # Run standard selection (Phase 4: with annotations)
        result = self.select_variants(role, extracted_jd, target_count, jd_annotations=jd_annotations)

        # Restore original order
        role.achievements = original_order

        return result


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def select_variants_for_role(
    role: EnhancedRoleData,
    extracted_jd: Dict,
    target_count: int = 5,
    jd_annotations: Optional[Dict[str, Any]] = None,
) -> SelectionResult:
    """
    Convenience function to select variants for a single role.

    Phase 4: Supports JD annotations for boost calculation.

    Args:
        role: Enhanced role data
        extracted_jd: Extracted JD data
        target_count: Target number of bullets
        jd_annotations: Optional JDAnnotations for boost calculation

    Returns:
        SelectionResult with selected variants
    """
    selector = VariantSelector()
    return selector.select_variants(role, extracted_jd, target_count, jd_annotations=jd_annotations)


def select_variants_for_all_roles(
    roles: Dict[str, EnhancedRoleData],
    extracted_jd: Dict,
    bullet_counts: Optional[Dict[str, int]] = None,
    jd_annotations: Optional[Dict[str, Any]] = None,
) -> Dict[str, SelectionResult]:
    """
    Select variants for all roles.

    Phase 4: Supports JD annotations for boost calculation.

    Args:
        roles: Dictionary of role_id -> EnhancedRoleData
        extracted_jd: Extracted JD data
        bullet_counts: Optional per-role bullet counts (default 5 each)
        jd_annotations: Optional JDAnnotations for boost calculation

    Returns:
        Dictionary of role_id -> SelectionResult
    """
    selector = VariantSelector()
    results = {}

    # Default bullet counts based on career stage
    default_counts = {
        "01_seven_one_entertainment": 6,  # Current role - more bullets
        "02_samdock_daypaio": 5,
        "03_ki_labs": 4,
        "04_fortis": 3,
        "05_osram": 3,
        "06_clary_icon": 2,  # Early career - fewer bullets
    }

    for role_id, role in roles.items():
        if bullet_counts and role_id in bullet_counts:
            count = bullet_counts[role_id]
        elif role_id in default_counts:
            count = default_counts[role_id]
        else:
            count = 4  # Default

        results[role_id] = selector.select_with_selection_guide(
            role, extracted_jd, count, jd_annotations=jd_annotations
        )

    return results
