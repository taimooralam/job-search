"""
Unit tests for ATS Keyword Density Checker.

Tests the Phase 5 ATS validation functionality:
- Keyword density checking (2-4x optimal range)
- Variant coverage validation
- Must-have vs nice-to-have prioritization
- Keyword stuffing detection
"""

import pytest
from src.layer6_v2.ats_checker import (
    ATSKeywordChecker,
    check_cv_ats_compliance,
    KeywordDensityResult,
    ATSValidationResult,
)
from src.layer6_v2.types import ATSRequirement


class TestKeywordDensityResult:
    """Tests for KeywordDensityResult dataclass."""

    def test_is_valid_when_meets_minimum_not_exceeds_maximum(self):
        """Keyword is valid when within range."""
        result = KeywordDensityResult(
            keyword="Python",
            count=3,
            min_required=2,
            max_allowed=4,
            meets_minimum=True,
            exceeds_maximum=False,
        )
        assert result.is_valid is True

    def test_is_invalid_when_below_minimum(self):
        """Keyword is invalid when below minimum."""
        result = KeywordDensityResult(
            keyword="Python",
            count=1,
            min_required=2,
            max_allowed=4,
            meets_minimum=False,
            exceeds_maximum=False,
        )
        assert result.is_valid is False

    def test_is_invalid_when_exceeds_maximum(self):
        """Keyword is invalid when exceeds maximum (stuffing)."""
        result = KeywordDensityResult(
            keyword="Python",
            count=6,
            min_required=2,
            max_allowed=4,
            meets_minimum=True,
            exceeds_maximum=True,
        )
        assert result.is_valid is False

    def test_status_insufficient(self):
        """Status shows insufficient when below minimum."""
        result = KeywordDensityResult(
            keyword="Python",
            count=1,
            min_required=2,
            max_allowed=4,
            meets_minimum=False,
            exceeds_maximum=False,
        )
        assert "insufficient" in result.status
        assert "(1/2)" in result.status

    def test_status_stuffing(self):
        """Status shows stuffing when exceeds maximum."""
        result = KeywordDensityResult(
            keyword="Python",
            count=6,
            min_required=2,
            max_allowed=4,
            meets_minimum=True,
            exceeds_maximum=True,
        )
        assert "stuffing" in result.status

    def test_status_optimal(self):
        """Status shows optimal when within range."""
        result = KeywordDensityResult(
            keyword="Python",
            count=3,
            min_required=2,
            max_allowed=4,
            meets_minimum=True,
            exceeds_maximum=False,
        )
        assert "optimal" in result.status


class TestATSKeywordChecker:
    """Tests for ATSKeywordChecker class."""

    def test_check_keyword_density_empty_keywords(self):
        """Empty keywords list returns passed result."""
        checker = ATSKeywordChecker()
        result = checker.check_keyword_density("Some content", [])

        assert result.passed is True
        assert result.total_keywords_checked == 0

    def test_check_keyword_density_keyword_found(self):
        """Keyword is found in content."""
        checker = ATSKeywordChecker()
        content = "I am skilled in Python programming. Python is my favorite language. I love Python."

        result = checker.check_keyword_density(content, ["Python"])

        assert "Python" in result.keyword_results
        assert result.keyword_results["Python"].count == 3
        assert result.keyword_results["Python"].meets_minimum is True

    def test_check_keyword_density_keyword_not_found(self):
        """Keyword not in content fails minimum check."""
        checker = ATSKeywordChecker()
        content = "I am skilled in Java programming."

        result = checker.check_keyword_density(content, ["Python"])

        assert result.keyword_results["Python"].count == 0
        assert result.keyword_results["Python"].meets_minimum is False

    def test_check_keyword_density_with_ats_requirements(self):
        """Custom ATS requirements are respected."""
        requirements = {
            "kubernetes": ATSRequirement(
                min_occurrences=3,
                max_occurrences=5,
                variants=["K8s"],
            )
        }
        checker = ATSKeywordChecker(ats_requirements=requirements)
        content = "Kubernetes is great. K8s makes deployment easy. I use Kubernetes daily."

        result = checker.check_keyword_density(content, ["Kubernetes"])

        kr = result.keyword_results["Kubernetes"]
        assert kr.min_required == 3
        assert kr.max_allowed == 5
        assert kr.count == 3  # 2 Kubernetes + 1 K8s

    def test_check_keyword_density_variant_counting(self):
        """Variants are counted together."""
        requirements = {
            "kubernetes": ATSRequirement(
                min_occurrences=2,
                max_occurrences=4,
                variants=["K8s", "kube"],
            )
        }
        checker = ATSKeywordChecker(ats_requirements=requirements)
        content = "I use Kubernetes and K8s and kube in my work."

        result = checker.check_keyword_density(content, ["Kubernetes"])

        assert result.keyword_results["Kubernetes"].count == 3

    def test_check_keyword_density_stuffing_detection(self):
        """Detects keyword stuffing when count exceeds maximum."""
        checker = ATSKeywordChecker()
        content = "Python Python Python Python Python Python Python"

        result = checker.check_keyword_density(content, ["Python"])

        assert result.keyword_results["Python"].exceeds_maximum is True
        assert any("stuffing" in w.lower() for w in result.warnings)

    def test_check_keyword_density_must_have_priority(self):
        """Must-have keywords are prioritized in coverage."""
        checker = ATSKeywordChecker(must_have_keywords={"Python", "AWS"})
        content = "I use Python daily. AWS is my cloud platform. Python and AWS are essential."

        result = checker.check_keyword_density(content, ["Python", "AWS", "Java"])

        # Python and AWS meet requirements, Java doesn't
        assert result.keyword_results["Python"].is_valid is True
        assert result.keyword_results["AWS"].is_valid is True
        assert result.keyword_results["Java"].meets_minimum is False

    def test_check_keyword_density_case_insensitive(self):
        """Keyword matching is case-insensitive."""
        checker = ATSKeywordChecker()
        content = "python PYTHON Python PyThOn"

        result = checker.check_keyword_density(content, ["Python"])

        assert result.keyword_results["Python"].count == 4

    def test_check_keyword_density_word_boundary(self):
        """Only matches whole words, not substrings."""
        checker = ATSKeywordChecker()
        content = "I use JavaScript and Java. JavaBeans is also useful."

        result = checker.check_keyword_density(content, ["Java"])

        # Should match "Java" but not "JavaScript" or "JavaBeans"
        assert result.keyword_results["Java"].count == 1

    def test_check_keyword_density_generates_warnings(self):
        """Generates appropriate warnings for failing keywords."""
        checker = ATSKeywordChecker(must_have_keywords={"Python"})
        content = "I know a bit of Python."  # Only 1 occurrence

        result = checker.check_keyword_density(content, ["Python"])

        assert len(result.warnings) > 0
        assert any("MUST-HAVE" in w for w in result.warnings)

    def test_check_keyword_density_generates_suggestions(self):
        """Generates suggestions for improving coverage."""
        checker = ATSKeywordChecker()
        content = "I know Python."  # Only 1 occurrence

        result = checker.check_keyword_density(content, ["Python"])

        assert len(result.suggestions) > 0


class TestVariantCoverage:
    """Tests for variant coverage checking."""

    def test_check_variant_coverage_all_present(self):
        """All variants present returns True."""
        checker = ATSKeywordChecker()
        content = "I use Kubernetes and K8s in production."

        all_present, missing = checker.check_variant_coverage(
            content, "Kubernetes", ["K8s"]
        )

        assert all_present is True
        assert len(missing) == 0

    def test_check_variant_coverage_some_missing(self):
        """Missing variants are returned."""
        checker = ATSKeywordChecker()
        content = "I use Kubernetes in production."

        all_present, missing = checker.check_variant_coverage(
            content, "Kubernetes", ["K8s", "kube"]
        )

        assert all_present is False
        assert "K8s" in missing
        assert "kube" in missing

    def test_check_variant_coverage_case_insensitive(self):
        """Variant matching is case-insensitive."""
        checker = ATSKeywordChecker()
        content = "I use KUBERNETES and k8s in production."

        all_present, missing = checker.check_variant_coverage(
            content, "Kubernetes", ["K8s"]
        )

        assert all_present is True


class TestATSValidationResult:
    """Tests for ATSValidationResult."""

    def test_to_dict_serialization(self):
        """Result can be serialized to dict."""
        result = ATSValidationResult(
            passed=True,
            total_keywords_checked=2,
            keywords_passing=2,
            keywords_failing=0,
            must_have_coverage=1.0,
            overall_coverage=1.0,
            warnings=[],
            suggestions=[],
        )

        result_dict = result.to_dict()

        assert result_dict["passed"] is True
        assert result_dict["total_keywords_checked"] == 2
        assert result_dict["must_have_coverage"] == 1.0


class TestCoverageReport:
    """Tests for coverage report generation."""

    def test_get_keyword_coverage_report(self):
        """Report is generated with all sections."""
        checker = ATSKeywordChecker()
        content = "Python Python Python. Java."

        result = checker.check_keyword_density(content, ["Python", "Java"])
        report = checker.get_keyword_coverage_report(result)

        assert "ATS KEYWORD COVERAGE REPORT" in report
        assert "Python" in report
        assert "Java" in report


class TestConvenienceFunction:
    """Tests for check_cv_ats_compliance convenience function."""

    def test_check_cv_ats_compliance_basic(self):
        """Convenience function works correctly."""
        content = "Python Python Python AWS AWS"

        result = check_cv_ats_compliance(
            cv_content=content,
            keywords=["Python", "AWS"],
            must_have_keywords={"Python"},
        )

        assert result.keyword_results["Python"].count == 3
        assert result.keyword_results["AWS"].count == 2

    def test_check_cv_ats_compliance_with_requirements(self):
        """Convenience function respects ATS requirements."""
        content = "Kubernetes K8s Kubernetes"
        requirements = {
            "kubernetes": ATSRequirement(
                min_occurrences=2,
                max_occurrences=5,
                variants=["K8s"],
            )
        }

        result = check_cv_ats_compliance(
            cv_content=content,
            keywords=["Kubernetes"],
            ats_requirements=requirements,
        )

        assert result.keyword_results["Kubernetes"].count == 3
        assert result.passed is True


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content(self):
        """Empty content handles gracefully."""
        checker = ATSKeywordChecker()
        result = checker.check_keyword_density("", ["Python"])

        assert result.keyword_results["Python"].count == 0
        assert result.keyword_results["Python"].meets_minimum is False

    def test_special_characters_in_keyword(self):
        """Keywords with special characters are escaped properly."""
        checker = ATSKeywordChecker()
        content = "I use CI/CD pipelines. CI/CD is essential."

        result = checker.check_keyword_density(content, ["CI/CD"])

        assert result.keyword_results["CI/CD"].count == 2

    def test_hyphenated_keywords(self):
        """Hyphenated keywords are matched correctly."""
        checker = ATSKeywordChecker()
        content = "I work on real-time systems. Real-time processing is key."

        result = checker.check_keyword_density(content, ["real-time"])

        assert result.keyword_results["real-time"].count == 2

    def test_multiple_must_have_partial_coverage(self):
        """Partial must-have coverage affects pass/fail."""
        checker = ATSKeywordChecker(must_have_keywords={"Python", "AWS", "Docker"})
        content = "Python Python Python. AWS AWS."  # No Docker

        result = checker.check_keyword_density(content, ["Python", "AWS", "Docker"])

        # 2/3 must-haves covered = 66.7%, below 80% threshold
        assert result.must_have_coverage < 0.8
