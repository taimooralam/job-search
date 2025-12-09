"""
Validation rules (lints) for JD annotations.

This module enforces quality standards on annotations before they can be saved:
- core_strength annotations MUST link at least one STAR story
- gap annotations MUST include a mitigation strategy
- must_have gaps trigger warnings
- overlapping annotations are flagged for review

These rules ensure that annotations are actionable and complete.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from src.common.annotation_types import (
    JDAnnotation,
    JDAnnotations,
    TextSpan,
)


class ValidationSeverity(Enum):
    """Severity level for validation errors."""
    ERROR = "error"      # Blocks save
    WARNING = "warning"  # Allows save with warning
    INFO = "info"        # Informational only


@dataclass
class ValidationResult:
    """Result of a single validation rule."""
    rule_id: str
    passed: bool
    severity: ValidationSeverity
    message: str
    annotation_id: Optional[str] = None
    fix_hint: Optional[str] = None


@dataclass
class ValidationReport:
    """Complete validation report for annotations."""
    passed: bool                      # True if no errors (warnings allowed)
    error_count: int
    warning_count: int
    info_count: int
    results: List[ValidationResult]

    @property
    def errors(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == ValidationSeverity.ERROR and not r.passed]

    @property
    def warnings(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == ValidationSeverity.WARNING and not r.passed]

    @property
    def error_messages(self) -> List[str]:
        return [r.message for r in self.errors]


# =============================================================================
# VALIDATION RULES
# =============================================================================

def validate_core_strength_has_star(annotation: JDAnnotation) -> ValidationResult:
    """
    Rule: core_strength annotations MUST link at least one STAR story.

    Rationale: Core strengths are the candidate's strongest selling points.
    They need concrete evidence (STAR stories) to be compelling in CV/outreach.
    """
    rule_id = "core_strength_requires_star"

    if annotation.get("relevance") != "core_strength":
        return ValidationResult(
            rule_id=rule_id,
            passed=True,
            severity=ValidationSeverity.ERROR,
            message="N/A - not a core_strength annotation",
            annotation_id=annotation.get("id"),
        )

    star_ids = annotation.get("star_ids", [])
    passed = len(star_ids) > 0

    return ValidationResult(
        rule_id=rule_id,
        passed=passed,
        severity=ValidationSeverity.ERROR,
        message="Core strength annotation must link at least one STAR story" if not passed else "STAR linked",
        annotation_id=annotation.get("id"),
        fix_hint="Click 'Link STAR' and select relevant achievement stories" if not passed else None,
    )


def validate_gap_has_mitigation(annotation: JDAnnotation) -> ValidationResult:
    """
    Rule: gap annotations MUST include a mitigation strategy.

    Rationale: Gaps identified without mitigation strategies are not actionable.
    The mitigation helps frame the gap in cover letters and interviews.
    """
    rule_id = "gap_requires_mitigation"

    if annotation.get("relevance") != "gap":
        return ValidationResult(
            rule_id=rule_id,
            passed=True,
            severity=ValidationSeverity.ERROR,
            message="N/A - not a gap annotation",
            annotation_id=annotation.get("id"),
        )

    # Check for mitigation in reframe_note or has a linked concern with mitigation
    has_mitigation = bool(annotation.get("reframe_note"))
    passed = has_mitigation

    return ValidationResult(
        rule_id=rule_id,
        passed=passed,
        severity=ValidationSeverity.ERROR,
        message="Gap annotation must include a mitigation strategy in reframe notes" if not passed else "Mitigation provided",
        annotation_id=annotation.get("id"),
        fix_hint="Add a reframe note explaining how to address this gap" if not passed else None,
    )


def validate_must_have_gap_warning(annotation: JDAnnotation) -> ValidationResult:
    """
    Rule: must_have requirements marked as gap trigger warning.

    Rationale: A must-have gap is a serious red flag. The user should either:
    - Add a strong mitigation strategy, or
    - Reconsider applying to this job
    """
    rule_id = "must_have_gap_warning"

    is_must_have = annotation.get("requirement_type") == "must_have"
    is_gap = annotation.get("relevance") == "gap"

    if not (is_must_have and is_gap):
        return ValidationResult(
            rule_id=rule_id,
            passed=True,
            severity=ValidationSeverity.WARNING,
            message="N/A - not a must-have gap",
            annotation_id=annotation.get("id"),
        )

    # This is always a warning - even with mitigation
    return ValidationResult(
        rule_id=rule_id,
        passed=False,  # Always fails to show warning
        severity=ValidationSeverity.WARNING,
        message="Must-have gap detected - ensure strong mitigation or reconsider application",
        annotation_id=annotation.get("id"),
        fix_hint="Review if this is truly a blocker. If applying, ensure cover letter addresses it.",
    )


def validate_no_overlapping_spans(annotations: List[JDAnnotation]) -> List[ValidationResult]:
    """
    Rule: Annotations should not overlap significantly.

    Rationale: Overlapping annotations can cause confusion in boost calculations
    and make the annotation list hard to manage.
    """
    rule_id = "overlapping_spans"
    results = []

    # Group annotations by section
    by_section: Dict[str, List[JDAnnotation]] = {}
    for ann in annotations:
        section = ann.get("target", {}).get("section", "unknown")
        if section not in by_section:
            by_section[section] = []
        by_section[section].append(ann)

    # Check for overlaps within each section
    for section, section_anns in by_section.items():
        for i, ann1 in enumerate(section_anns):
            for ann2 in section_anns[i + 1:]:
                target1 = ann1.get("target", {})
                target2 = ann2.get("target", {})

                start1 = target1.get("char_start", 0)
                end1 = target1.get("char_end", 0)
                start2 = target2.get("char_start", 0)
                end2 = target2.get("char_end", 0)

                # Check for overlap
                overlap = max(0, min(end1, end2) - max(start1, start2))
                if overlap > 0:
                    # Calculate overlap percentage
                    len1 = end1 - start1
                    len2 = end2 - start2
                    min_len = min(len1, len2) if min(len1, len2) > 0 else 1
                    overlap_pct = overlap / min_len

                    if overlap_pct > 0.5:  # More than 50% overlap
                        results.append(ValidationResult(
                            rule_id=rule_id,
                            passed=False,
                            severity=ValidationSeverity.WARNING,
                            message=f"Annotations overlap significantly ({int(overlap_pct * 100)}%) - review for conflicts",
                            annotation_id=ann1.get("id"),
                            fix_hint="Consider merging these annotations or adjusting their boundaries",
                        ))

    # If no overlaps found, add a passing result
    if not results:
        results.append(ValidationResult(
            rule_id=rule_id,
            passed=True,
            severity=ValidationSeverity.WARNING,
            message="No significant overlaps detected",
        ))

    return results


def validate_section_coverage(
    annotations: List[JDAnnotation],
    required_sections: List[str],
    min_annotations_per_section: int = 1,
) -> List[ValidationResult]:
    """
    Rule: Each JD section should have at least minimum annotations.

    Rationale: Incomplete annotation coverage may miss important requirements.
    """
    rule_id = "section_coverage"
    results = []

    # Count annotations per section
    section_counts: Dict[str, int] = {section: 0 for section in required_sections}
    for ann in annotations:
        if ann.get("is_active", True):
            section = ann.get("target", {}).get("section", "unknown")
            if section in section_counts:
                section_counts[section] += 1

    # Check each required section
    for section, count in section_counts.items():
        passed = count >= min_annotations_per_section
        results.append(ValidationResult(
            rule_id=f"{rule_id}_{section}",
            passed=passed,
            severity=ValidationSeverity.INFO,
            message=f"Section '{section}' has {count} annotation(s)" if passed else f"Section '{section}' needs annotation ({count}/{min_annotations_per_section})",
            fix_hint=f"Review '{section}' section and add annotations" if not passed else None,
        ))

    return results


def validate_disqualifier_warning(annotation: JDAnnotation) -> ValidationResult:
    """
    Rule: Disqualifier annotations trigger a warning.

    Rationale: If user marks something as a disqualifier, they should
    seriously consider not applying to this job.
    """
    rule_id = "disqualifier_warning"

    if annotation.get("requirement_type") != "disqualifier":
        return ValidationResult(
            rule_id=rule_id,
            passed=True,
            severity=ValidationSeverity.WARNING,
            message="N/A - not a disqualifier",
            annotation_id=annotation.get("id"),
        )

    return ValidationResult(
        rule_id=rule_id,
        passed=False,
        severity=ValidationSeverity.WARNING,
        message="Disqualifier marked - consider if this job is right for you",
        annotation_id=annotation.get("id"),
        fix_hint="If this is a dealbreaker, you may want to skip this application",
    )


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================

def validate_annotations(
    jd_annotations: JDAnnotations,
    required_sections: Optional[List[str]] = None,
) -> ValidationReport:
    """
    Run all validation rules on annotations.

    Args:
        jd_annotations: The complete annotation data for a job
        required_sections: List of section IDs that need coverage

    Returns:
        ValidationReport with all validation results
    """
    results: List[ValidationResult] = []
    annotations = jd_annotations.get("annotations", [])

    # Per-annotation validations
    for ann in annotations:
        # Only validate active annotations
        if not ann.get("is_active", True):
            continue

        # Core strength must have STAR
        results.append(validate_core_strength_has_star(ann))

        # Gap must have mitigation
        results.append(validate_gap_has_mitigation(ann))

        # Must-have gap warning
        results.append(validate_must_have_gap_warning(ann))

        # Disqualifier warning
        results.append(validate_disqualifier_warning(ann))

    # Collection-level validations
    results.extend(validate_no_overlapping_spans(annotations))

    # Section coverage (if required_sections provided)
    if required_sections:
        results.extend(validate_section_coverage(annotations, required_sections))

    # Calculate summary
    error_count = len([r for r in results if r.severity == ValidationSeverity.ERROR and not r.passed])
    warning_count = len([r for r in results if r.severity == ValidationSeverity.WARNING and not r.passed])
    info_count = len([r for r in results if r.severity == ValidationSeverity.INFO and not r.passed])

    return ValidationReport(
        passed=error_count == 0,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        results=results,
    )


def validate_single_annotation(annotation: JDAnnotation) -> ValidationReport:
    """
    Validate a single annotation (for real-time validation in UI).

    Args:
        annotation: Single annotation to validate

    Returns:
        ValidationReport for just this annotation
    """
    results: List[ValidationResult] = []

    results.append(validate_core_strength_has_star(annotation))
    results.append(validate_gap_has_mitigation(annotation))
    results.append(validate_must_have_gap_warning(annotation))
    results.append(validate_disqualifier_warning(annotation))

    error_count = len([r for r in results if r.severity == ValidationSeverity.ERROR and not r.passed])
    warning_count = len([r for r in results if r.severity == ValidationSeverity.WARNING and not r.passed])
    info_count = len([r for r in results if r.severity == ValidationSeverity.INFO and not r.passed])

    return ValidationReport(
        passed=error_count == 0,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        results=results,
    )


# =============================================================================
# BOOST CALCULATION
# =============================================================================

def calculate_annotation_boost(annotation: JDAnnotation) -> Tuple[float, Dict]:
    """
    Calculate the boost factor for an annotation.

    This determines how much an annotated skill/achievement should be
    prioritized in CV generation.

    Args:
        annotation: The annotation to calculate boost for

    Returns:
        Tuple of (boost_factor, metadata_dict)
    """
    from src.common.annotation_types import (
        RELEVANCE_MULTIPLIERS,
        REQUIREMENT_MULTIPLIERS,
        PRIORITY_MULTIPLIERS,
        TYPE_MODIFIERS,
    )

    # Get multipliers with defaults
    relevance = annotation.get("relevance", "relevant")
    requirement_type = annotation.get("requirement_type", "neutral")
    priority = annotation.get("priority", 3)
    ann_type = annotation.get("annotation_type", "skill_match")

    relevance_mult = RELEVANCE_MULTIPLIERS.get(relevance, 1.0)
    requirement_mult = REQUIREMENT_MULTIPLIERS.get(requirement_type, 1.0)
    priority_mult = PRIORITY_MULTIPLIERS.get(priority, 1.0)
    type_mult = TYPE_MODIFIERS.get(ann_type, 1.0)

    # Calculate total boost
    boost = relevance_mult * requirement_mult * priority_mult * type_mult

    # Build metadata for traceability
    metadata = {
        "annotation_id": annotation.get("id"),
        "relevance": relevance,
        "relevance_mult": relevance_mult,
        "requirement_type": requirement_type,
        "requirement_mult": requirement_mult,
        "priority": priority,
        "priority_mult": priority_mult,
        "annotation_type": ann_type,
        "type_mult": type_mult,
        "total_boost": boost,
        "reframe_applied": annotation.get("reframe_note") if annotation.get("has_reframe") else None,
        "keywords_from_annotation": annotation.get("suggested_keywords", []),
    }

    return boost, metadata


def aggregate_annotation_boosts(
    annotations: List[JDAnnotation],
    resolution_strategy: str = "max_boost",
) -> Dict[str, float]:
    """
    Aggregate boosts from multiple annotations.

    Args:
        annotations: List of active annotations
        resolution_strategy: How to handle multiple annotations
            - "max_boost": Use highest boost
            - "avg_boost": Average all boosts
            - "last_write": Use most recent annotation

    Returns:
        Dict mapping annotation_id to final boost value
    """
    boosts: Dict[str, List[Tuple[float, str]]] = {}  # skill -> [(boost, ann_id), ...]

    for ann in annotations:
        if not ann.get("is_active", True):
            continue

        skill = ann.get("matching_skill", ann.get("id"))
        boost, _ = calculate_annotation_boost(ann)

        if skill not in boosts:
            boosts[skill] = []
        boosts[skill].append((boost, ann.get("id")))

    # Apply resolution strategy
    result: Dict[str, float] = {}

    for skill, boost_list in boosts.items():
        if resolution_strategy == "max_boost":
            max_boost = max(boost_list, key=lambda x: x[0])
            result[max_boost[1]] = max_boost[0]
        elif resolution_strategy == "avg_boost":
            avg = sum(b[0] for b in boost_list) / len(boost_list)
            for _, ann_id in boost_list:
                result[ann_id] = avg
        else:  # last_write - would need timestamps, default to last in list
            result[boost_list[-1][1]] = boost_list[-1][0]

    return result
