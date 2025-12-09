"""
ATS Keyword Density Checker.

Validates CV content for ATS optimization based on annotation requirements:
- Keyword density: must-have keywords should appear 2-4x
- Variant coverage: both acronym and full form included
- No keyword stuffing: max 4x for any keyword

Phase 5 of JD Annotation System.

Research backing:
- Keyword density: 5 mentions > 2 mentions in Greenhouse ranking → target 2-4x
- Greenhouse/Lever/Taleo don't recognize abbreviations → always include BOTH forms
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from src.common.logger import get_logger
from src.layer6_v2.types import ATSRequirement


@dataclass
class KeywordDensityResult:
    """Result of keyword density check for a single keyword."""

    keyword: str
    count: int
    min_required: int
    max_allowed: int
    meets_minimum: bool
    exceeds_maximum: bool
    variants_found: List[str] = field(default_factory=list)
    sections_found_in: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if keyword density is within acceptable range."""
        return self.meets_minimum and not self.exceeds_maximum

    @property
    def status(self) -> str:
        """Human-readable status."""
        if not self.meets_minimum:
            return f"insufficient ({self.count}/{self.min_required})"
        elif self.exceeds_maximum:
            return f"stuffing ({self.count}/{self.max_allowed})"
        else:
            return f"optimal ({self.count})"


@dataclass
class ATSValidationResult:
    """Complete ATS validation result for CV content."""

    passed: bool
    total_keywords_checked: int
    keywords_passing: int
    keywords_failing: int

    # Detailed results
    keyword_results: Dict[str, KeywordDensityResult] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    # Coverage metrics
    must_have_coverage: float = 0.0
    overall_coverage: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "total_keywords_checked": self.total_keywords_checked,
            "keywords_passing": self.keywords_passing,
            "keywords_failing": self.keywords_failing,
            "must_have_coverage": self.must_have_coverage,
            "overall_coverage": self.overall_coverage,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "keyword_results": {
                k: {
                    "keyword": v.keyword,
                    "count": v.count,
                    "min_required": v.min_required,
                    "max_allowed": v.max_allowed,
                    "is_valid": v.is_valid,
                    "status": v.status,
                    "variants_found": v.variants_found,
                }
                for k, v in self.keyword_results.items()
            },
        }


class ATSKeywordChecker:
    """
    Validates ATS keyword density and variant coverage.

    Uses annotation requirements to determine:
    - Which keywords are must-have vs nice-to-have
    - Required density for each keyword
    - Variant forms that should be included
    """

    # Default density requirements
    DEFAULT_MIN_OCCURRENCES = 2
    DEFAULT_MAX_OCCURRENCES = 4

    def __init__(
        self,
        ats_requirements: Optional[Dict[str, ATSRequirement]] = None,
        must_have_keywords: Optional[Set[str]] = None,
    ):
        """
        Initialize the ATS checker.

        Args:
            ats_requirements: Dict of keyword -> ATSRequirement from annotations
            must_have_keywords: Set of keywords marked as must-have
        """
        self._logger = get_logger(__name__)
        self._ats_requirements = ats_requirements or {}
        self._must_have_keywords = must_have_keywords or set()

    def check_keyword_density(
        self,
        content: str,
        keywords_to_check: List[str],
        content_sections: Optional[Dict[str, str]] = None,
    ) -> ATSValidationResult:
        """
        Check keyword density across CV content.

        Args:
            content: Full CV text content
            keywords_to_check: List of keywords to validate
            content_sections: Optional dict of section_name -> section_content
                             for per-section tracking

        Returns:
            ATSValidationResult with detailed keyword analysis
        """
        if not keywords_to_check:
            return ATSValidationResult(
                passed=True,
                total_keywords_checked=0,
                keywords_passing=0,
                keywords_failing=0,
            )

        content_lower = content.lower()
        keyword_results: Dict[str, KeywordDensityResult] = {}
        warnings: List[str] = []
        suggestions: List[str] = []

        # Track section distribution if provided
        section_counts: Dict[str, Dict[str, int]] = {}
        if content_sections:
            for section_name, section_content in content_sections.items():
                section_counts[section_name] = {}

        for keyword in keywords_to_check:
            result = self._check_single_keyword(
                keyword, content_lower, content_sections, section_counts
            )
            keyword_results[keyword] = result

            # Generate warnings and suggestions
            if not result.meets_minimum:
                is_must_have = keyword.lower() in {k.lower() for k in self._must_have_keywords}
                severity = "MUST-HAVE" if is_must_have else "Nice-to-have"
                warnings.append(
                    f"{severity} keyword '{keyword}' appears {result.count}x "
                    f"(minimum: {result.min_required})"
                )
                suggestions.append(
                    f"Add '{keyword}' to header, summary, or skills section"
                )

            if result.exceeds_maximum:
                warnings.append(
                    f"Keyword stuffing detected: '{keyword}' appears {result.count}x "
                    f"(maximum: {result.max_allowed})"
                )
                suggestions.append(
                    f"Reduce occurrences of '{keyword}' to avoid ATS penalties"
                )

        # Calculate coverage metrics
        passing = sum(1 for r in keyword_results.values() if r.is_valid)
        failing = len(keyword_results) - passing

        must_have_results = [
            r for kw, r in keyword_results.items()
            if kw.lower() in {k.lower() for k in self._must_have_keywords}
        ]
        must_have_passing = sum(1 for r in must_have_results if r.is_valid)
        must_have_coverage = (
            must_have_passing / len(must_have_results)
            if must_have_results else 1.0
        )

        overall_coverage = passing / len(keyword_results) if keyword_results else 1.0

        # Determine pass/fail (must-haves are mandatory)
        passed = must_have_coverage >= 0.8 and overall_coverage >= 0.6

        return ATSValidationResult(
            passed=passed,
            total_keywords_checked=len(keyword_results),
            keywords_passing=passing,
            keywords_failing=failing,
            keyword_results=keyword_results,
            warnings=warnings,
            suggestions=suggestions,
            must_have_coverage=must_have_coverage,
            overall_coverage=overall_coverage,
        )

    def _check_single_keyword(
        self,
        keyword: str,
        content_lower: str,
        content_sections: Optional[Dict[str, str]],
        section_counts: Dict[str, Dict[str, int]],
    ) -> KeywordDensityResult:
        """Check density for a single keyword."""
        keyword_lower = keyword.lower()

        # Get ATS requirements for this keyword
        requirement = self._ats_requirements.get(keyword_lower)
        if not requirement:
            # Check case-insensitive
            for k, v in self._ats_requirements.items():
                if k.lower() == keyword_lower:
                    requirement = v
                    break

        min_required = (
            requirement.min_occurrences if requirement
            else self.DEFAULT_MIN_OCCURRENCES
        )
        max_allowed = (
            requirement.max_occurrences if requirement
            else self.DEFAULT_MAX_OCCURRENCES
        )
        variants = requirement.variants if requirement else []

        # Count occurrences of keyword and variants
        all_forms = [keyword_lower] + [v.lower() for v in variants]
        total_count = 0
        variants_found = []

        for form in all_forms:
            # Use word boundary matching to avoid partial matches
            pattern = r'\b' + re.escape(form) + r'\b'
            matches = re.findall(pattern, content_lower, re.IGNORECASE)
            if matches:
                count = len(matches)
                total_count += count
                variants_found.append(f"{form} ({count})")

        # Track which sections contain the keyword
        sections_found_in = []
        if content_sections:
            for section_name, section_content in content_sections.items():
                section_lower = section_content.lower()
                for form in all_forms:
                    pattern = r'\b' + re.escape(form) + r'\b'
                    if re.search(pattern, section_lower, re.IGNORECASE):
                        sections_found_in.append(section_name)
                        break

        return KeywordDensityResult(
            keyword=keyword,
            count=total_count,
            min_required=min_required,
            max_allowed=max_allowed,
            meets_minimum=total_count >= min_required,
            exceeds_maximum=total_count > max_allowed,
            variants_found=variants_found,
            sections_found_in=sections_found_in,
        )

    def check_variant_coverage(
        self,
        content: str,
        keyword: str,
        variants: List[str],
    ) -> Tuple[bool, List[str]]:
        """
        Check if both canonical form and variants are present.

        Research shows Greenhouse/Lever/Taleo don't recognize abbreviations,
        so we need BOTH forms (e.g., "Kubernetes" AND "K8s").

        Args:
            content: CV text content
            keyword: Canonical keyword
            variants: List of variant forms

        Returns:
            Tuple of (all_forms_present, missing_forms)
        """
        content_lower = content.lower()
        all_forms = [keyword] + variants
        missing = []

        for form in all_forms:
            pattern = r'\b' + re.escape(form.lower()) + r'\b'
            if not re.search(pattern, content_lower, re.IGNORECASE):
                missing.append(form)

        return len(missing) == 0, missing

    def get_keyword_coverage_report(
        self,
        result: ATSValidationResult,
    ) -> str:
        """
        Generate human-readable coverage report.

        Args:
            result: ATSValidationResult from check_keyword_density

        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=== ATS KEYWORD COVERAGE REPORT ===")
        lines.append("")
        lines.append(f"Overall Status: {'PASS' if result.passed else 'FAIL'}")
        lines.append(f"Keywords Checked: {result.total_keywords_checked}")
        lines.append(f"Keywords Passing: {result.keywords_passing}")
        lines.append(f"Keywords Failing: {result.keywords_failing}")
        lines.append(f"Must-Have Coverage: {result.must_have_coverage:.0%}")
        lines.append(f"Overall Coverage: {result.overall_coverage:.0%}")
        lines.append("")

        if result.warnings:
            lines.append("WARNINGS:")
            for warning in result.warnings:
                lines.append(f"  ! {warning}")
            lines.append("")

        if result.suggestions:
            lines.append("SUGGESTIONS:")
            for suggestion in result.suggestions:
                lines.append(f"  → {suggestion}")
            lines.append("")

        lines.append("KEYWORD DETAILS:")
        for keyword, kr in sorted(
            result.keyword_results.items(),
            key=lambda x: (x[1].is_valid, -x[1].count),
        ):
            status_icon = "✓" if kr.is_valid else "✗"
            lines.append(f"  {status_icon} {keyword}: {kr.status}")
            if kr.variants_found:
                lines.append(f"      Forms found: {', '.join(kr.variants_found)}")

        return "\n".join(lines)


def check_cv_ats_compliance(
    cv_content: str,
    keywords: List[str],
    ats_requirements: Optional[Dict[str, ATSRequirement]] = None,
    must_have_keywords: Optional[Set[str]] = None,
) -> ATSValidationResult:
    """
    Convenience function to check CV ATS compliance.

    Args:
        cv_content: Full CV text content
        keywords: Keywords to check
        ats_requirements: Optional ATSRequirement config per keyword
        must_have_keywords: Keywords marked as must-have

    Returns:
        ATSValidationResult with detailed analysis
    """
    checker = ATSKeywordChecker(
        ats_requirements=ats_requirements,
        must_have_keywords=must_have_keywords,
    )
    return checker.check_keyword_density(cv_content, keywords)
