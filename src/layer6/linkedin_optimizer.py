"""
LinkedIn Headline Optimizer (Phase 6).

Uses JD annotation keywords to suggest optimized LinkedIn headline variants
that improve visibility and relevance for target roles.

Key Features:
- Extracts top core_strength keywords from annotations
- Generates headlines under 120 chars (LinkedIn limit)
- Cross-references with LinkedIn algorithm preferences
- Provides multiple variants for A/B testing
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
import re

from src.common.annotation_types import JDAnnotation


# LinkedIn headline constraints
HEADLINE_MAX_LENGTH = 120
MIN_KEYWORDS = 2
MAX_KEYWORDS = 5

# LinkedIn algorithm preference keywords (high engagement)
# Based on LinkedIn engagement research and recruiter preferences
ALGORITHM_PREFERRED_TERMS = {
    # Role indicators
    "manager", "director", "lead", "senior", "staff", "principal",
    "head", "architect", "engineer", "developer",
    # Skills that perform well
    "ai", "ml", "cloud", "platform", "scale", "growth",
    "transformation", "strategy", "innovation",
    # Industry terms
    "fintech", "healthtech", "adtech", "saas", "b2b", "b2c",
    # Outcome words
    "builder", "leader", "driver", "enabler",
}

# Common LinkedIn headline patterns
HEADLINE_PATTERNS = [
    "{role} | {keyword1} | {keyword2} | {keyword3}",
    "{role} | {keyword1} & {keyword2} | {differentiator}",
    "{role} → {trajectory} | {keyword1} | {keyword2}",
    "{role} | Building {outcome} | {keyword1}",
    "{role} | {years}+ Years {keyword1} | {differentiator}",
]


@dataclass
class HeadlineVariant:
    """A single LinkedIn headline variant with metadata."""

    headline: str
    keywords_used: List[str]
    pattern_used: str
    algorithm_score: float  # 0.0-1.0 based on preferred term overlap
    length: int

    @property
    def is_valid(self) -> bool:
        """Check if headline meets LinkedIn constraints."""
        return self.length <= HEADLINE_MAX_LENGTH and len(self.keywords_used) >= MIN_KEYWORDS


@dataclass
class HeadlineOptimizationResult:
    """Complete result from headline optimization."""

    variants: List[HeadlineVariant]
    source_keywords: List[str]
    current_headline: Optional[str]
    improvement_rationale: str

    def get_best_variant(self) -> Optional[HeadlineVariant]:
        """Get the highest-scoring valid variant."""
        valid = [v for v in self.variants if v.is_valid]
        if not valid:
            return None
        return max(valid, key=lambda v: v.algorithm_score)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API/storage."""
        return {
            "variants": [
                {
                    "headline": v.headline,
                    "keywords_used": v.keywords_used,
                    "pattern_used": v.pattern_used,
                    "algorithm_score": v.algorithm_score,
                    "length": v.length,
                    "is_valid": v.is_valid,
                }
                for v in self.variants
            ],
            "source_keywords": self.source_keywords,
            "current_headline": self.current_headline,
            "improvement_rationale": self.improvement_rationale,
            "best_variant": self.get_best_variant().headline if self.get_best_variant() else None,
        }


class LinkedInHeadlineOptimizer:
    """
    Generates optimized LinkedIn headline variants from JD annotations.

    Uses core_strength and extremely_relevant annotations to extract
    keywords that resonate with both recruiters and LinkedIn's algorithm.
    """

    def __init__(
        self,
        candidate_base_role: str = "Engineering Leader",
        years_experience: int = 11,
    ):
        """
        Initialize the optimizer.

        Args:
            candidate_base_role: Base role title for headline (e.g., "Engineering Manager")
            years_experience: Years of experience for tenure-based variants
        """
        self._base_role = candidate_base_role
        self._years = years_experience

    def extract_keywords_from_annotations(
        self,
        annotations: List[JDAnnotation],
        limit: int = MAX_KEYWORDS,
    ) -> List[str]:
        """
        Extract top keywords from annotations for headline use.

        Prioritizes core_strength and extremely_relevant annotations,
        then falls back to suggested_keywords and ats_variants.

        Args:
            annotations: List of JDAnnotation from job state
            limit: Maximum keywords to extract

        Returns:
            List of keywords ordered by relevance
        """
        if not annotations:
            return []

        keywords: List[str] = []
        seen: Set[str] = set()

        # Priority 1: Core strength matching skills
        for ann in annotations:
            if ann.get("relevance") == "core_strength" and ann.get("is_active", True):
                skill = ann.get("matching_skill")
                if skill and skill.lower() not in seen:
                    keywords.append(skill)
                    seen.add(skill.lower())

        # Priority 2: Extremely relevant matching skills
        for ann in annotations:
            if ann.get("relevance") == "extremely_relevant" and ann.get("is_active", True):
                skill = ann.get("matching_skill")
                if skill and skill.lower() not in seen:
                    keywords.append(skill)
                    seen.add(skill.lower())

        # Priority 3: Suggested keywords from annotations
        for ann in annotations:
            if ann.get("is_active", True):
                for kw in ann.get("suggested_keywords", []):
                    if kw and kw.lower() not in seen:
                        keywords.append(kw)
                        seen.add(kw.lower())
                        if len(keywords) >= limit:
                            break
            if len(keywords) >= limit:
                break

        # Priority 4: ATS variants (often contain industry-specific terms)
        for ann in annotations:
            if ann.get("is_active", True):
                for variant in ann.get("ats_variants", []):
                    if variant and variant.lower() not in seen:
                        keywords.append(variant)
                        seen.add(variant.lower())
                        if len(keywords) >= limit:
                            break
            if len(keywords) >= limit:
                break

        return keywords[:limit]

    def calculate_algorithm_score(self, headline: str) -> float:
        """
        Calculate how well a headline aligns with LinkedIn algorithm preferences.

        Score based on:
        - Presence of preferred terms (higher engagement)
        - Appropriate length (not too short)
        - Use of separators (|, →) for scannability

        Args:
            headline: The headline text to score

        Returns:
            Score from 0.0 to 1.0
        """
        headline_lower = headline.lower()
        words = set(re.findall(r'\b\w+\b', headline_lower))

        # Factor 1: Preferred terms overlap (40% weight)
        preferred_overlap = len(words.intersection(ALGORITHM_PREFERRED_TERMS))
        term_score = min(preferred_overlap / 3.0, 1.0) * 0.4

        # Factor 2: Length optimization (30% weight)
        # Optimal is 60-100 chars (enough content, not too sparse)
        length = len(headline)
        if 60 <= length <= 100:
            length_score = 0.3
        elif 40 <= length < 60 or 100 < length <= 120:
            length_score = 0.2
        else:
            length_score = 0.1

        # Factor 3: Structure (20% weight)
        # Separators improve scannability
        has_pipe = "|" in headline
        has_arrow = "→" in headline
        has_ampersand = "&" in headline
        structure_score = 0.2 if (has_pipe or has_arrow) else 0.1
        if has_ampersand:
            structure_score += 0.05

        # Factor 4: Keyword density (10% weight)
        # More unique meaningful words = better
        meaningful_words = len([w for w in words if len(w) > 3])
        density_score = min(meaningful_words / 8.0, 1.0) * 0.1

        return term_score + length_score + structure_score + density_score

    def generate_variants(
        self,
        keywords: List[str],
        target_role: Optional[str] = None,
        differentiator: Optional[str] = None,
        trajectory: Optional[str] = None,
    ) -> List[HeadlineVariant]:
        """
        Generate headline variants using extracted keywords.

        Args:
            keywords: Keywords from annotations (2-5 recommended)
            target_role: Optional target role (defaults to base role)
            differentiator: Optional unique selling point (e.g., "AdTech Scale")
            trajectory: Optional career trajectory (e.g., "Director Track")

        Returns:
            List of HeadlineVariant objects
        """
        if len(keywords) < MIN_KEYWORDS:
            return []

        role = target_role or self._base_role
        diff = differentiator or keywords[-1] if len(keywords) > 2 else "Team Builder"
        traj = trajectory or "Director Track"
        outcome = keywords[0] if keywords else "Scale"

        variants: List[HeadlineVariant] = []

        # Pattern 1: Role | KW1 | KW2 | KW3
        if len(keywords) >= 3:
            headline = f"{role} | {keywords[0]} | {keywords[1]} | {keywords[2]}"
            if len(headline) <= HEADLINE_MAX_LENGTH:
                variants.append(HeadlineVariant(
                    headline=headline,
                    keywords_used=keywords[:3],
                    pattern_used="pipe_separated",
                    algorithm_score=self.calculate_algorithm_score(headline),
                    length=len(headline),
                ))

        # Pattern 2: Role | KW1 & KW2 | Differentiator
        if len(keywords) >= 2:
            headline = f"{role} | {keywords[0]} & {keywords[1]} | {diff}"
            if len(headline) <= HEADLINE_MAX_LENGTH:
                variants.append(HeadlineVariant(
                    headline=headline,
                    keywords_used=keywords[:2] + [diff],
                    pattern_used="ampersand_combo",
                    algorithm_score=self.calculate_algorithm_score(headline),
                    length=len(headline),
                ))

        # Pattern 3: Role → Trajectory | KW1 | KW2
        if len(keywords) >= 2:
            headline = f"{role} → {traj} | {keywords[0]} | {keywords[1]}"
            if len(headline) <= HEADLINE_MAX_LENGTH:
                variants.append(HeadlineVariant(
                    headline=headline,
                    keywords_used=[traj] + keywords[:2],
                    pattern_used="trajectory_arrow",
                    algorithm_score=self.calculate_algorithm_score(headline),
                    length=len(headline),
                ))

        # Pattern 4: Role | Building {outcome} | KW1
        headline = f"{role} | Building {outcome} Solutions | {keywords[0]}"
        if len(headline) <= HEADLINE_MAX_LENGTH:
            variants.append(HeadlineVariant(
                headline=headline,
                keywords_used=[outcome, keywords[0]],
                pattern_used="builder_outcome",
                algorithm_score=self.calculate_algorithm_score(headline),
                length=len(headline),
            ))

        # Pattern 5: Role | Years+ Years KW1 | Differentiator
        headline = f"{role} | {self._years}+ Years {keywords[0]} | {diff}"
        if len(headline) <= HEADLINE_MAX_LENGTH:
            variants.append(HeadlineVariant(
                headline=headline,
                keywords_used=[keywords[0], diff],
                pattern_used="years_experience",
                algorithm_score=self.calculate_algorithm_score(headline),
                length=len(headline),
            ))

        # Sort by algorithm score descending
        variants.sort(key=lambda v: v.algorithm_score, reverse=True)

        return variants

    def optimize_headline(
        self,
        annotations: List[JDAnnotation],
        current_headline: Optional[str] = None,
        target_role: Optional[str] = None,
        differentiator: Optional[str] = None,
    ) -> HeadlineOptimizationResult:
        """
        Generate optimized headline variants from JD annotations.

        Main entry point for headline optimization.

        Args:
            annotations: List of JDAnnotation from job state
            current_headline: User's current LinkedIn headline for comparison
            target_role: Optional target role for headline
            differentiator: Optional unique selling point

        Returns:
            HeadlineOptimizationResult with variants and analysis
        """
        # Extract keywords from annotations
        keywords = self.extract_keywords_from_annotations(annotations)

        if len(keywords) < MIN_KEYWORDS:
            return HeadlineOptimizationResult(
                variants=[],
                source_keywords=keywords,
                current_headline=current_headline,
                improvement_rationale="Insufficient annotation keywords to generate headlines. "
                "Add more core_strength or extremely_relevant annotations.",
            )

        # Generate variants
        variants = self.generate_variants(
            keywords=keywords,
            target_role=target_role,
            differentiator=differentiator,
        )

        # Build rationale
        rationale_parts = [
            f"Generated {len(variants)} headline variants using {len(keywords)} keywords "
            f"from annotations: {', '.join(keywords[:3])}."
        ]

        if current_headline:
            current_score = self.calculate_algorithm_score(current_headline)
            best = max(variants, key=lambda v: v.algorithm_score) if variants else None
            if best and best.algorithm_score > current_score:
                improvement = (best.algorithm_score - current_score) / current_score * 100
                rationale_parts.append(
                    f"Best variant scores {improvement:.0f}% higher than current headline."
                )

        return HeadlineOptimizationResult(
            variants=variants,
            source_keywords=keywords,
            current_headline=current_headline,
            improvement_rationale=" ".join(rationale_parts),
        )


def suggest_linkedin_headlines(
    annotations: List[JDAnnotation],
    current_headline: Optional[str] = None,
    candidate_role: str = "Engineering Leader",
    years_experience: int = 11,
) -> HeadlineOptimizationResult:
    """
    Convenience function to generate LinkedIn headline suggestions.

    Args:
        annotations: List of JDAnnotation from job state
        current_headline: User's current LinkedIn headline
        candidate_role: Base role title for headlines
        years_experience: Years of experience for tenure patterns

    Returns:
        HeadlineOptimizationResult with variants and analysis
    """
    optimizer = LinkedInHeadlineOptimizer(
        candidate_base_role=candidate_role,
        years_experience=years_experience,
    )
    return optimizer.optimize_headline(
        annotations=annotations,
        current_headline=current_headline,
    )
