"""
Achievement to Pain Point Mapper.

Pre-computes mappings between candidate achievements and JD pain points
to reduce LLM cognitive load and improve bullet generation quality.

This is a pre-processing step that runs before role generation to:
1. Identify which achievements can address which pain points
2. Provide explicit guidance to the LLM
3. Ensure no pain points are missed
4. Improve traceability of generated bullets
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from src.common.logger import get_logger


@dataclass
class AchievementPainPointMatch:
    """
    A mapping between an achievement and a pain point.

    Tracks the confidence of the match and the reason for matching.
    """

    achievement: str
    pain_point: str
    confidence: float  # 0-1 score
    reason: str  # Why they match (e.g., "keyword overlap", "semantic similarity")
    matched_keywords: List[str] = field(default_factory=list)

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.confidence >= 0.7:
            return "high"
        elif self.confidence >= 0.4:
            return "medium"
        else:
            return "low"

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "achievement": self.achievement,
            "pain_point": self.pain_point,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "reason": self.reason,
            "matched_keywords": self.matched_keywords,
        }


@dataclass
class AchievementMapping:
    """
    Complete mapping result for a single achievement.

    An achievement may match multiple pain points with different confidences.
    """

    achievement: str
    best_match: Optional[AchievementPainPointMatch] = None
    all_matches: List[AchievementPainPointMatch] = field(default_factory=list)
    unmatched: bool = False  # True if no pain point match found

    @property
    def has_match(self) -> bool:
        """Check if achievement has any pain point match."""
        return self.best_match is not None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "achievement": self.achievement,
            "best_match": self.best_match.to_dict() if self.best_match else None,
            "all_matches": [m.to_dict() for m in self.all_matches],
            "unmatched": self.unmatched,
        }


class AchievementMapper:
    """
    Maps achievements to pain points using keyword overlap and semantic similarity.

    Uses a lightweight heuristic approach (no embeddings) for speed:
    - Keyword extraction and overlap scoring
    - String similarity via SequenceMatcher
    - Domain-specific keyword weighting (technical terms, action verbs)
    """

    # Domain-specific keywords that indicate strong matches
    TECHNICAL_KEYWORDS = {
        "scale", "scaling", "scalability", "performance", "latency",
        "reliability", "availability", "uptime", "sla", "slo",
        "security", "compliance", "audit", "gdpr", "soc2",
        "migration", "modernization", "refactor", "technical debt",
        "architecture", "microservices", "monolith", "distributed",
        "team", "hiring", "retention", "attrition", "growth",
        "process", "agile", "sprint", "delivery", "velocity",
        "cost", "budget", "efficiency", "optimization", "reduce",
        "automation", "ci/cd", "devops", "infrastructure",
        "data", "analytics", "ml", "ai", "pipeline",
        "customer", "user", "churn", "engagement", "satisfaction",
    }

    # Action verbs that indicate achievement types
    ACTION_VERBS = {
        "led", "built", "designed", "architected", "implemented",
        "reduced", "improved", "increased", "established", "launched",
        "scaled", "grew", "mentored", "coached", "developed",
        "optimized", "automated", "migrated", "transformed",
    }

    def __init__(
        self,
        match_threshold: float = 0.25,
        high_confidence_threshold: float = 0.6,
    ):
        """
        Initialize the mapper.

        Args:
            match_threshold: Minimum score to consider a match (default 0.25)
            high_confidence_threshold: Score for "high confidence" (default 0.6)
        """
        self.match_threshold = match_threshold
        self.high_confidence_threshold = high_confidence_threshold
        self._logger = get_logger(__name__)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase and remove punctuation except hyphens
        text = text.lower()
        text = re.sub(r"[^\w\s-]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_keywords(self, text: str) -> Set[str]:
        """
        Extract meaningful keywords from text.

        Focuses on nouns, technical terms, and action verbs.
        """
        normalized = self._normalize_text(text)
        words = set(normalized.split())

        # Filter short words (likely stop words)
        keywords = {w for w in words if len(w) > 3}

        # Add bigrams for compound terms
        word_list = normalized.split()
        for i in range(len(word_list) - 1):
            bigram = f"{word_list[i]} {word_list[i+1]}"
            if any(tech in bigram for tech in ["technical debt", "team growth", "cost reduction"]):
                keywords.add(bigram)

        return keywords

    def _extract_metrics(self, text: str) -> Set[str]:
        """Extract metrics and numbers from text."""
        metrics = set()
        # Percentages
        metrics.update(re.findall(r"\d+(?:\.\d+)?%", text))
        # Currency
        metrics.update(re.findall(r"\$\d+(?:,\d{3})*(?:\.\d+)?[KMB]?", text, re.IGNORECASE))
        # Multipliers
        metrics.update(re.findall(r"\d+x\b", text, re.IGNORECASE))
        return metrics

    def _calculate_keyword_overlap(
        self, text1: str, text2: str
    ) -> Tuple[float, Set[str]]:
        """
        Calculate keyword overlap between two texts.

        Returns:
            Tuple of (overlap_score, matched_keywords)
        """
        kw1 = self._extract_keywords(text1)
        kw2 = self._extract_keywords(text2)

        if not kw1 or not kw2:
            return 0.0, set()

        overlap = kw1 & kw2

        # Weight technical keywords higher
        technical_overlap = overlap & self.TECHNICAL_KEYWORDS
        weighted_overlap = len(overlap) + len(technical_overlap) * 0.5

        # Jaccard-like score
        union_size = len(kw1 | kw2)
        score = weighted_overlap / union_size if union_size > 0 else 0.0

        return min(score, 1.0), overlap

    def _calculate_string_similarity(self, text1: str, text2: str) -> float:
        """Calculate string similarity using SequenceMatcher."""
        norm1 = self._normalize_text(text1)
        norm2 = self._normalize_text(text2)
        return SequenceMatcher(None, norm1, norm2).ratio()

    def _score_match(
        self, achievement: str, pain_point: str
    ) -> Tuple[float, str, List[str]]:
        """
        Score how well an achievement matches a pain point.

        Returns:
            Tuple of (score, reason, matched_keywords)
        """
        # Calculate keyword overlap
        kw_score, matched_kw = self._calculate_keyword_overlap(achievement, pain_point)

        # Calculate string similarity
        string_sim = self._calculate_string_similarity(achievement, pain_point)

        # Combined score (keyword overlap weighted higher)
        combined = (kw_score * 0.7) + (string_sim * 0.3)

        # Determine reason
        if kw_score > 0.4:
            reason = f"keyword overlap ({', '.join(list(matched_kw)[:3])})"
        elif string_sim > 0.5:
            reason = "semantic similarity"
        else:
            reason = "partial match"

        return combined, reason, list(matched_kw)

    def map_achievement(
        self, achievement: str, pain_points: List[str]
    ) -> AchievementMapping:
        """
        Map a single achievement to pain points.

        Args:
            achievement: The achievement text from the CV
            pain_points: List of JD pain points

        Returns:
            AchievementMapping with best match and all matches above threshold
        """
        if not pain_points:
            return AchievementMapping(
                achievement=achievement,
                unmatched=True,
            )

        matches = []
        for pain_point in pain_points:
            score, reason, matched_kw = self._score_match(achievement, pain_point)

            if score >= self.match_threshold:
                matches.append(
                    AchievementPainPointMatch(
                        achievement=achievement,
                        pain_point=pain_point,
                        confidence=score,
                        reason=reason,
                        matched_keywords=matched_kw,
                    )
                )

        # Sort by confidence (highest first)
        matches.sort(key=lambda m: m.confidence, reverse=True)

        return AchievementMapping(
            achievement=achievement,
            best_match=matches[0] if matches else None,
            all_matches=matches,
            unmatched=len(matches) == 0,
        )

    def map_all_achievements(
        self,
        achievements: List[str],
        pain_points: List[str],
    ) -> List[AchievementMapping]:
        """
        Map all achievements to pain points.

        Args:
            achievements: List of achievement texts from the CV
            pain_points: List of JD pain points

        Returns:
            List of AchievementMapping, one per achievement
        """
        self._logger.debug(
            f"Mapping {len(achievements)} achievements to {len(pain_points)} pain points"
        )

        mappings = []
        for achievement in achievements:
            mapping = self.map_achievement(achievement, pain_points)
            mappings.append(mapping)

        # Log summary
        matched_count = sum(1 for m in mappings if m.has_match)
        high_confidence = sum(
            1 for m in mappings
            if m.best_match and m.best_match.confidence >= self.high_confidence_threshold
        )

        self._logger.info(
            f"Achievement mapping complete: {matched_count}/{len(achievements)} matched, "
            f"{high_confidence} high confidence"
        )

        return mappings

    def get_pain_point_coverage(
        self, mappings: List[AchievementMapping], pain_points: List[str]
    ) -> Dict[str, List[str]]:
        """
        Get which pain points are covered by achievements.

        Args:
            mappings: List of AchievementMapping results
            pain_points: Original list of pain points

        Returns:
            Dict mapping pain_point -> list of matching achievements
        """
        coverage = {pp: [] for pp in pain_points}

        for mapping in mappings:
            if mapping.best_match:
                pain_point = mapping.best_match.pain_point
                if pain_point in coverage:
                    coverage[pain_point].append(mapping.achievement)

        return coverage

    def format_for_prompt(
        self,
        mappings: List[AchievementMapping],
        pain_points: List[str],
        max_matches_per_achievement: int = 2,
    ) -> str:
        """
        Format mappings for inclusion in the LLM prompt.

        Args:
            mappings: List of AchievementMapping results
            pain_points: Original list of pain points
            max_matches_per_achievement: Maximum matches to show per achievement

        Returns:
            Formatted string for prompt inclusion
        """
        lines = []

        # Section 1: Achievement -> Pain Point mappings
        lines.append("=== ACHIEVEMENT TO PAIN POINT MAPPING (pre-computed) ===")
        lines.append("Use these mappings to end bullets with relevant SITUATION context:")
        lines.append("")

        for mapping in mappings:
            achievement_preview = mapping.achievement[:80] + "..." if len(mapping.achievement) > 80 else mapping.achievement

            if mapping.has_match:
                best = mapping.best_match
                lines.append(
                    f'* "{achievement_preview}"'
                )
                lines.append(
                    f'  -> addresses "{best.pain_point}" ({best.confidence_level} confidence)'
                )

                # Show secondary matches if available
                secondary = [m for m in mapping.all_matches[1:max_matches_per_achievement] if m.confidence >= 0.3]
                for alt in secondary:
                    lines.append(f'     also relates to: "{alt.pain_point}" ({alt.confidence_level})')
            else:
                lines.append(f'* "{achievement_preview}"')
                lines.append("  -> no direct pain point match (use general impact)")

            lines.append("")

        # Section 2: Pain points without coverage
        coverage = self.get_pain_point_coverage(mappings, pain_points)
        uncovered = [pp for pp, achievements in coverage.items() if not achievements]

        if uncovered:
            lines.append("=== UNCOVERED PAIN POINTS (no matching achievements) ===")
            lines.append("These pain points have no direct achievement matches. Do NOT address them:")
            for pp in uncovered:
                lines.append(f"  - {pp}")
            lines.append("")

        return "\n".join(lines)


def map_achievements_to_pain_points(
    achievements: List[str],
    pain_points: List[str],
    match_threshold: float = 0.25,
) -> Tuple[List[AchievementMapping], str]:
    """
    Convenience function to map achievements to pain points.

    Args:
        achievements: List of achievement texts from the CV
        pain_points: List of JD pain points
        match_threshold: Minimum score to consider a match

    Returns:
        Tuple of (mappings, formatted_prompt_section)
    """
    mapper = AchievementMapper(match_threshold=match_threshold)
    mappings = mapper.map_all_achievements(achievements, pain_points)
    prompt_section = mapper.format_for_prompt(mappings, pain_points)

    return mappings, prompt_section
