"""
Annotation Fit Signal Calculator for Layer 4 Fit Scoring.

This module extracts fit signals from JD annotations and blends them with
LLM-based fit scores to incorporate human judgment into the scoring process.

Key concepts:
- Annotations provide human-curated signals about candidate-JD fit
- Core strength and extremely relevant annotations indicate positive fit
- Gap annotations indicate areas where candidate may not match
- Disqualifier requirement types flag potential dealbreakers
- Annotation signal (0-1) blends with LLM score (0-100) for final score

Usage:
    from src.layer4.annotation_fit_signal import AnnotationFitSignal, blend_fit_scores

    signal = AnnotationFitSignal(jd_annotations)
    print(signal.fit_signal)  # 0.75
    print(signal.to_dict())   # Full analysis

    blended_score = blend_fit_scores(llm_score=80, jd_annotations=annotations)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


# Signal weights for different annotation relevance levels
# These map to how much each annotation type contributes to the fit signal
RELEVANCE_SIGNAL_WEIGHTS = {
    "core_strength": 1.0,       # Perfect match - full positive signal
    "extremely_relevant": 0.8,  # Very strong match
    "relevant": 0.5,            # Good match
    "tangential": 0.2,          # Weak match
    "gap": -0.5,                # Missing skill - negative signal
}

# Phase 4: Passion signal weights - authentic enthusiasm indicators
PASSION_SIGNAL_WEIGHTS = {
    "love_it": 0.3,    # Genuine excitement - positive engagement signal
    "enjoy": 0.15,     # Positive but not passionate
    "neutral": 0.0,    # No signal
    "tolerate": -0.1,  # Reluctant acceptance - mild negative
    "avoid": -0.2,     # Strong preference against - negative signal
}

# Phase 4: Identity signal weights - professional self-image alignment
IDENTITY_SIGNAL_WEIGHTS = {
    "core_identity": 0.4,    # This IS who they are - strong positive
    "strong_identity": 0.25, # Strong part of identity
    "developing": 0.15,      # Growth area - mild positive
    "peripheral": 0.0,       # Not relevant to identity
    "not_identity": -0.3,    # Explicitly NOT who they are - negative
}

# Default blend weights: 70% LLM score, 30% annotation signal
DEFAULT_LLM_WEIGHT = 0.7
DEFAULT_ANNOTATION_WEIGHT = 0.3


@dataclass
class AnnotationFitSignal:
    """
    Calculator for extracting fit signals from JD annotations.

    Analyzes annotations to produce:
    - fit_signal: A 0-1 score based on annotation relevance distribution
    - passion_signal: Enthusiasm/engagement signal from passion annotations
    - identity_signal: Professional identity alignment signal
    - Counts of different annotation types
    - Disqualifier detection

    The fit_signal is calculated as:
    - Start at 0.5 (neutral)
    - Each positive annotation increases signal (weighted by relevance)
    - Each gap annotation decreases signal
    - Passion and identity signals add additional adjustments
    - Result is clamped to [0, 1]
    """

    # Computed fields
    fit_signal: float = field(default=0.5, init=False)
    core_strength_count: int = field(default=0, init=False)
    extremely_relevant_count: int = field(default=0, init=False)
    relevant_count: int = field(default=0, init=False)
    tangential_count: int = field(default=0, init=False)
    gap_count: int = field(default=0, init=False)
    has_disqualifier: bool = field(default=False, init=False)
    disqualifier_details: List[str] = field(default_factory=list, init=False)
    has_annotations: bool = field(default=False, init=False)
    total_active_annotations: int = field(default=0, init=False)

    # Phase 4: Passion dimension counters
    passion_love_it_count: int = field(default=0, init=False)
    passion_enjoy_count: int = field(default=0, init=False)
    passion_tolerate_count: int = field(default=0, init=False)
    passion_avoid_count: int = field(default=0, init=False)
    passion_signal: float = field(default=0.0, init=False)

    # Phase 4: Identity dimension counters
    identity_core_count: int = field(default=0, init=False)
    identity_strong_count: int = field(default=0, init=False)
    identity_developing_count: int = field(default=0, init=False)
    identity_not_me_count: int = field(default=0, init=False)
    identity_signal: float = field(default=0.0, init=False)

    def __init__(self, jd_annotations: Optional[Dict[str, Any]] = None):
        """
        Initialize the annotation fit signal calculator.

        Args:
            jd_annotations: JDAnnotations dict from job state (or None)
        """
        self.fit_signal = 0.5
        self.core_strength_count = 0
        self.extremely_relevant_count = 0
        self.relevant_count = 0
        self.tangential_count = 0
        self.gap_count = 0
        self.has_disqualifier = False
        self.disqualifier_details = []
        self.has_annotations = False
        self.total_active_annotations = 0

        # Phase 4: Initialize passion counters
        self.passion_love_it_count = 0
        self.passion_enjoy_count = 0
        self.passion_tolerate_count = 0
        self.passion_avoid_count = 0
        self.passion_signal = 0.0

        # Phase 4: Initialize identity counters
        self.identity_core_count = 0
        self.identity_strong_count = 0
        self.identity_developing_count = 0
        self.identity_not_me_count = 0
        self.identity_signal = 0.0

        if jd_annotations:
            self._process_annotations(jd_annotations)

    def _process_annotations(self, jd_annotations: Dict[str, Any]) -> None:
        """
        Process annotations to extract fit signal components.

        Args:
            jd_annotations: JDAnnotations dict containing annotations list
        """
        annotations = jd_annotations.get("annotations", [])

        if not annotations:
            return

        # Count active annotations by relevance level
        for ann in annotations:
            # Skip inactive annotations (default to True for backward compatibility)
            if not ann.get("is_active", True):
                continue

            self.total_active_annotations += 1
            self.has_annotations = True

            # Count by relevance level
            relevance = ann.get("relevance")
            if relevance == "core_strength":
                self.core_strength_count += 1
            elif relevance == "extremely_relevant":
                self.extremely_relevant_count += 1
            elif relevance == "relevant":
                self.relevant_count += 1
            elif relevance == "tangential":
                self.tangential_count += 1
            elif relevance == "gap":
                self.gap_count += 1

            # Check for disqualifier requirement type
            requirement_type = ann.get("requirement_type")
            if requirement_type == "disqualifier":
                self.has_disqualifier = True
                # Extract details about the disqualifier
                target = ann.get("target", {})
                text = target.get("text", "Unknown requirement")
                self.disqualifier_details.append(text)

            # Phase 4: Count by passion level
            passion = ann.get("passion")
            if passion == "love_it":
                self.passion_love_it_count += 1
            elif passion == "enjoy":
                self.passion_enjoy_count += 1
            elif passion == "tolerate":
                self.passion_tolerate_count += 1
            elif passion == "avoid":
                self.passion_avoid_count += 1

            # Phase 4: Count by identity level
            identity = ann.get("identity")
            if identity == "core_identity":
                self.identity_core_count += 1
            elif identity == "strong_identity":
                self.identity_strong_count += 1
            elif identity == "developing":
                self.identity_developing_count += 1
            elif identity == "not_identity":
                self.identity_not_me_count += 1

        # Calculate fit signal from counts
        self._calculate_fit_signal()

    def _calculate_fit_signal(self) -> None:
        """
        Calculate the fit signal based on annotation counts.

        Formula:
        - Start at 0.5 (neutral)
        - Add/subtract based on weighted annotation counts
        - Include passion and identity signals
        - Normalize and clamp to [0, 1]

        This uses a sigmoid-like approach where:
        - Many positive annotations approach 1.0
        - Many gap annotations approach 0.0
        - Mixed annotations stay around 0.5
        - Passion/identity signals provide additional adjustment
        """
        if not self.has_annotations:
            self.fit_signal = 0.5
            self.passion_signal = 0.0
            self.identity_signal = 0.0
            return

        # Calculate weighted sum of relevance signals
        positive_signal = (
            self.core_strength_count * RELEVANCE_SIGNAL_WEIGHTS["core_strength"] +
            self.extremely_relevant_count * RELEVANCE_SIGNAL_WEIGHTS["extremely_relevant"] +
            self.relevant_count * RELEVANCE_SIGNAL_WEIGHTS["relevant"] +
            self.tangential_count * RELEVANCE_SIGNAL_WEIGHTS["tangential"]
        )

        negative_signal = abs(
            self.gap_count * RELEVANCE_SIGNAL_WEIGHTS["gap"]
        )

        # Phase 4: Calculate passion signal (enthusiasm/engagement indicator)
        self.passion_signal = (
            self.passion_love_it_count * PASSION_SIGNAL_WEIGHTS["love_it"] +
            self.passion_enjoy_count * PASSION_SIGNAL_WEIGHTS["enjoy"] +
            self.passion_tolerate_count * PASSION_SIGNAL_WEIGHTS["tolerate"] +
            self.passion_avoid_count * PASSION_SIGNAL_WEIGHTS["avoid"]
        )

        # Phase 4: Calculate identity signal (professional self-image alignment)
        self.identity_signal = (
            self.identity_core_count * IDENTITY_SIGNAL_WEIGHTS["core_identity"] +
            self.identity_strong_count * IDENTITY_SIGNAL_WEIGHTS["strong_identity"] +
            self.identity_developing_count * IDENTITY_SIGNAL_WEIGHTS["developing"] +
            self.identity_not_me_count * IDENTITY_SIGNAL_WEIGHTS["not_identity"]
        )

        # Net signal includes relevance + passion + identity
        net_signal = positive_signal - negative_signal + self.passion_signal + self.identity_signal

        # Normalize using sigmoid-like function
        # This ensures signal stays bounded and doesn't explode with many annotations
        # Scale factor determines how quickly signal approaches bounds
        scale_factor = 0.3  # Tuned for reasonable sensitivity

        # Apply logistic-like transformation
        # net_signal of 0 -> fit_signal of 0.5
        # positive net_signal -> fit_signal approaches 1.0
        # negative net_signal -> fit_signal approaches 0.0
        import math
        try:
            self.fit_signal = 1.0 / (1.0 + math.exp(-scale_factor * net_signal))
        except OverflowError:
            # Handle extreme values
            self.fit_signal = 1.0 if net_signal > 0 else 0.0

        # Clamp to [0, 1] for safety
        self.fit_signal = max(0.0, min(1.0, self.fit_signal))

    def to_dict(self) -> Dict[str, Any]:
        """
        Return the complete annotation analysis as a dictionary.

        Returns:
            Dict with all annotation signal components including passion/identity
        """
        result = {
            "fit_signal": round(self.fit_signal, 4),
            "core_strength_count": self.core_strength_count,
            "extremely_relevant_count": self.extremely_relevant_count,
            "relevant_count": self.relevant_count,
            "tangential_count": self.tangential_count,
            "gap_count": self.gap_count,
            "has_disqualifier": self.has_disqualifier,
            "has_annotations": self.has_annotations,
            "total_active_annotations": self.total_active_annotations,
            # Phase 4: Passion dimension
            "passion_signal": round(self.passion_signal, 4),
            "passion_love_it_count": self.passion_love_it_count,
            "passion_enjoy_count": self.passion_enjoy_count,
            "passion_tolerate_count": self.passion_tolerate_count,
            "passion_avoid_count": self.passion_avoid_count,
            # Phase 4: Identity dimension
            "identity_signal": round(self.identity_signal, 4),
            "identity_core_count": self.identity_core_count,
            "identity_strong_count": self.identity_strong_count,
            "identity_developing_count": self.identity_developing_count,
            "identity_not_me_count": self.identity_not_me_count,
        }

        # Add disqualifier warning if present
        if self.has_disqualifier:
            result["disqualifier_warning"] = (
                f"Candidate has marked {len(self.disqualifier_details)} requirement(s) "
                f"as potential disqualifiers: {', '.join(self.disqualifier_details[:3])}"
            )
            if len(self.disqualifier_details) > 3:
                result["disqualifier_warning"] += f" and {len(self.disqualifier_details) - 3} more"

        # Phase 4: Add enthusiasm/identity warnings if extreme
        if self.passion_avoid_count >= 3:
            result["enthusiasm_warning"] = (
                f"Low enthusiasm detected: {self.passion_avoid_count} requirements marked as 'avoid'. "
                "Consider if this role aligns with candidate's interests."
            )
        if self.identity_not_me_count >= 3:
            result["identity_warning"] = (
                f"Identity mismatch detected: {self.identity_not_me_count} requirements marked as 'not me'. "
                "Role may not align with candidate's professional self-image."
            )

        return result


def blend_fit_scores(
    llm_score: int,
    jd_annotations: Optional[Dict[str, Any]],
    llm_weight: float = DEFAULT_LLM_WEIGHT,
) -> int:
    """
    Blend LLM fit score with annotation signal.

    Args:
        llm_score: The LLM-generated fit score (0-100)
        jd_annotations: JDAnnotations dict from job state (or None)
        llm_weight: Weight for LLM score (0-1). Annotation weight is 1 - llm_weight.
                   Default is 0.7 (70% LLM, 30% annotation)

    Returns:
        Blended fit score (0-100)

    When no annotations are present, returns the LLM score unchanged.
    """
    # If no annotations, return LLM score unchanged
    if not jd_annotations:
        return llm_score

    # Calculate annotation signal
    signal = AnnotationFitSignal(jd_annotations)

    # If no active annotations, return LLM score unchanged
    if not signal.has_annotations:
        return llm_score

    # Convert annotation signal (0-1) to score scale (0-100)
    annotation_score = signal.fit_signal * 100

    # Calculate annotation weight
    annotation_weight = 1.0 - llm_weight

    # Blend the scores
    blended = (llm_weight * llm_score) + (annotation_weight * annotation_score)

    # Clamp to valid range and round to integer
    blended = max(0, min(100, blended))

    return round(blended)


def get_annotation_analysis(
    jd_annotations: Optional[Dict[str, Any]],
    llm_score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Get complete annotation analysis including optional blending info.

    Args:
        jd_annotations: JDAnnotations dict from job state (or None)
        llm_score: Optional LLM score for blending info

    Returns:
        Complete annotation analysis dict
    """
    signal = AnnotationFitSignal(jd_annotations)
    analysis = signal.to_dict()

    # Add blending info if LLM score provided
    if llm_score is not None:
        analysis["llm_score"] = llm_score
        analysis["blended_score"] = blend_fit_scores(llm_score, jd_annotations)
        analysis["blend_weights"] = {
            "llm": DEFAULT_LLM_WEIGHT,
            "annotation": DEFAULT_ANNOTATION_WEIGHT,
        }

    return analysis
