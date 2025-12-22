"""
ATS Keyword Placement Validator.

Validates that annotated keywords appear in optimal positions in the CV:
- Headline (highest weight)
- Profile narrative (first 50-100 words)
- Core competencies
- Most recent role bullets

The top 1/3 of a CV is critical for both ATS scanning and 6-7 second human review.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import re

from src.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class KeywordPlacement:
    """Placement analysis for a single keyword."""

    keyword: str
    priority_rank: int = 0
    is_must_have: bool = False
    is_identity: bool = False
    is_core_strength: bool = False

    # Position tracking
    found_in_headline: bool = False
    found_in_narrative: bool = False
    found_in_competencies: bool = False
    found_in_first_role: bool = False

    first_occurrence_position: int = -1
    total_occurrences: int = 0
    occurrence_locations: List[str] = field(default_factory=list)

    @property
    def is_in_top_third(self) -> bool:
        """Keyword appears in headline, narrative, or competencies."""
        return (
            self.found_in_headline
            or self.found_in_narrative
            or self.found_in_competencies
        )

    @property
    def placement_score(self) -> int:
        """Score 0-100 based on optimal placement."""
        score = 0
        if self.found_in_headline:
            score += 40
        if self.found_in_narrative:
            score += 30
        if self.found_in_competencies:
            score += 20
        if self.found_in_first_role:
            score += 10
        return min(score, 100)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "priority_rank": self.priority_rank,
            "is_must_have": self.is_must_have,
            "is_identity": self.is_identity,
            "is_core_strength": self.is_core_strength,
            "found_in_headline": self.found_in_headline,
            "found_in_narrative": self.found_in_narrative,
            "found_in_competencies": self.found_in_competencies,
            "found_in_first_role": self.found_in_first_role,
            "is_in_top_third": self.is_in_top_third,
            "placement_score": self.placement_score,
            "total_occurrences": self.total_occurrences,
            "occurrence_locations": self.occurrence_locations,
        }


@dataclass
class KeywordPlacementResult:
    """Complete placement analysis for all priority keywords."""

    placements: List[KeywordPlacement] = field(default_factory=list)

    overall_score: int = 0
    must_have_score: int = 0
    identity_score: int = 0

    violations: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    total_keywords: int = 0
    keywords_in_headline: int = 0
    keywords_in_narrative: int = 0
    keywords_in_top_third: int = 0
    keywords_buried: int = 0

    @property
    def passed(self) -> bool:
        """Check if placement meets quality threshold (80%)."""
        return self.overall_score >= 80 and self.must_have_score >= 90

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "must_have_score": self.must_have_score,
            "identity_score": self.identity_score,
            "passed": self.passed,
            "violations": self.violations,
            "suggestions": self.suggestions,
            "total_keywords": self.total_keywords,
            "keywords_in_headline": self.keywords_in_headline,
            "keywords_in_narrative": self.keywords_in_narrative,
            "keywords_in_top_third": self.keywords_in_top_third,
            "keywords_buried": self.keywords_buried,
            "placements": [p.to_dict() for p in self.placements],
        }


class KeywordPlacementValidator:
    """
    Validates keyword placement in CV sections for ATS optimization.

    The validator extracts CV sections and checks if priority keywords
    from annotations appear in optimal positions (top 1/3 of CV).
    """

    def __init__(self):
        self._logger = get_logger(self.__class__.__name__)

    def validate(
        self,
        headline: str,
        narrative: str,
        competencies: List[str],
        first_role_bullets: List[str],
        priority_keywords: List[Dict[str, Any]],
    ) -> KeywordPlacementResult:
        """
        Validate keyword placement across CV sections.

        Args:
            headline: CV headline text
            narrative: Profile narrative text
            competencies: List of core competency strings
            first_role_bullets: Bullets from most recent role
            priority_keywords: List of dicts with keyword info:
                - keyword: str
                - is_must_have: bool
                - is_identity: bool
                - is_core_strength: bool
                - priority_rank: int

        Returns:
            KeywordPlacementResult with scores and feedback
        """
        placements: List[KeywordPlacement] = []

        # Normalize sections for matching
        headline_lower = headline.lower()
        narrative_lower = narrative.lower()
        competencies_lower = " ".join(competencies).lower()
        first_role_lower = " ".join(first_role_bullets).lower()

        # Analyze each priority keyword
        for i, kw_info in enumerate(priority_keywords):
            keyword = kw_info.get("keyword", "")
            if not keyword:
                continue

            placement = self._analyze_keyword_placement(
                keyword=keyword,
                priority_rank=kw_info.get("priority_rank", i + 1),
                is_must_have=kw_info.get("is_must_have", False),
                is_identity=kw_info.get("is_identity", False),
                is_core_strength=kw_info.get("is_core_strength", False),
                headline_lower=headline_lower,
                narrative_lower=narrative_lower,
                competencies_lower=competencies_lower,
                first_role_lower=first_role_lower,
            )
            placements.append(placement)

        # Calculate aggregate scores
        result = self._calculate_scores(placements)

        return result

    def _analyze_keyword_placement(
        self,
        keyword: str,
        priority_rank: int,
        is_must_have: bool,
        is_identity: bool,
        is_core_strength: bool,
        headline_lower: str,
        narrative_lower: str,
        competencies_lower: str,
        first_role_lower: str,
    ) -> KeywordPlacement:
        """Analyze placement of a single keyword."""
        keyword_lower = keyword.lower()

        # Build regex pattern for word boundary matching
        # Allow for variations (e.g., "python" matches "Python", "python3")
        pattern = re.compile(
            r"\b" + re.escape(keyword_lower) + r"\w*\b", re.IGNORECASE
        )

        placement = KeywordPlacement(
            keyword=keyword,
            priority_rank=priority_rank,
            is_must_have=is_must_have,
            is_identity=is_identity,
            is_core_strength=is_core_strength,
        )

        # Check each section
        if pattern.search(headline_lower):
            placement.found_in_headline = True
            placement.occurrence_locations.append("headline")
            placement.total_occurrences += len(pattern.findall(headline_lower))

        if pattern.search(narrative_lower):
            placement.found_in_narrative = True
            placement.occurrence_locations.append("narrative")
            placement.total_occurrences += len(pattern.findall(narrative_lower))

        if pattern.search(competencies_lower):
            placement.found_in_competencies = True
            placement.occurrence_locations.append("competencies")
            placement.total_occurrences += len(pattern.findall(competencies_lower))

        if pattern.search(first_role_lower):
            placement.found_in_first_role = True
            placement.occurrence_locations.append("first_role")
            placement.total_occurrences += len(pattern.findall(first_role_lower))

        return placement

    def _calculate_scores(
        self, placements: List[KeywordPlacement]
    ) -> KeywordPlacementResult:
        """Calculate aggregate scores and generate feedback."""
        result = KeywordPlacementResult(placements=placements)

        if not placements:
            result.overall_score = 100  # No keywords to check = pass
            result.must_have_score = 100  # No must-haves to check = pass
            result.identity_score = 100  # No identity keywords to check = pass
            return result

        result.total_keywords = len(placements)

        # Count placements
        must_have_placements = [p for p in placements if p.is_must_have]
        identity_placements = [p for p in placements if p.is_identity]

        for p in placements:
            if p.found_in_headline:
                result.keywords_in_headline += 1
            if p.found_in_narrative:
                result.keywords_in_narrative += 1
            if p.is_in_top_third:
                result.keywords_in_top_third += 1
            else:
                result.keywords_buried += 1

        # Calculate scores
        if placements:
            total_score = sum(p.placement_score for p in placements)
            result.overall_score = total_score // len(placements)

        if must_have_placements:
            must_have_in_top = sum(
                1 for p in must_have_placements if p.is_in_top_third
            )
            result.must_have_score = (must_have_in_top * 100) // len(
                must_have_placements
            )
        else:
            result.must_have_score = 100

        if identity_placements:
            identity_in_headline = sum(
                1 for p in identity_placements if p.found_in_headline
            )
            result.identity_score = (identity_in_headline * 100) // len(
                identity_placements
            )
        else:
            result.identity_score = 100

        # Generate violations and suggestions
        for p in placements:
            if p.is_must_have and not p.is_in_top_third:
                result.violations.append(
                    f"Must-have keyword '{p.keyword}' not found in top 1/3 of CV"
                )
                result.suggestions.append(
                    f"Add '{p.keyword}' to core competencies or profile narrative"
                )

            if p.is_identity and not p.found_in_headline:
                result.violations.append(
                    f"Identity keyword '{p.keyword}' not found in headline"
                )
                result.suggestions.append(
                    f"Include '{p.keyword}' in your headline/tagline"
                )

            if p.is_core_strength and not p.found_in_competencies:
                if p.total_occurrences == 0:
                    result.suggestions.append(
                        f"Consider adding '{p.keyword}' to core competencies"
                    )

        return result


def extract_priority_keywords_from_annotations(
    jd_annotations: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract priority keywords from JD annotations for placement validation.

    Args:
        jd_annotations: The jd_annotations dict from job state

    Returns:
        List of keyword dicts with priority metadata
    """
    priority_keywords = []
    annotations = jd_annotations.get("annotations", [])

    for ann in annotations:
        if not ann.get("is_active", True):
            continue

        # Get the keyword (matching_skill or first suggested keyword)
        keyword = ann.get("matching_skill")
        if not keyword:
            keywords = ann.get("suggested_keywords", [])
            keyword = keywords[0] if keywords else None

        if not keyword:
            continue

        relevance = ann.get("relevance", "")
        requirement = ann.get("requirement_type", "")
        identity = ann.get("identity", "")
        priority = ann.get("priority", 3)

        priority_keywords.append(
            {
                "keyword": keyword,
                "is_must_have": requirement == "must_have",
                "is_identity": identity in ["core_identity", "strong_identity"],
                "is_core_strength": relevance
                in ["core_strength", "extremely_relevant"],
                "priority_rank": priority,
            }
        )

    # Sort by priority rank
    priority_keywords.sort(key=lambda x: x["priority_rank"])

    return priority_keywords
