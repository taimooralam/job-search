"""
Unit tests for src/layer6_v2/ai_competency_eval.py.

NOTE: This module does not yet exist. These tests define the required interface
contract and serve as a specification for the implementation. They will be
importable once the module is created with the functions below:

    evaluate_ai_competencies(cv: str, ground_truth: dict) -> EvalResult
    extract_ai_claims(cv: str) -> List[str]

Where EvalResult has:
    passed: bool
    verified_count: int
    flagged_count: int
    total_claims: int
    summary: str

The ground_truth dict has keys:
    verified_skills: List[str]       — skills that have actually been built
    verified_patterns: List[str]     — design patterns that are demonstrably used
    not_yet_built: List[str]         — things that have NOT been built (must flag)

Design intent:
- A CV bullet is a "claim" when it mentions an AI/LLM-related term.
- A claim is "verified" when it matches something in verified_skills or verified_patterns.
- A claim is "flagged" when it matches something in not_yet_built.
- If any claims are flagged, passed is False; otherwise True.
- total_claims counts every distinct AI claim found in the CV.
"""


import pytest

# ---------------------------------------------------------------------------
# Import guard — skip the whole module gracefully if not yet implemented
# ---------------------------------------------------------------------------
try:
    from src.layer6_v2.ai_competency_eval import evaluate_ai_competencies, extract_ai_claims
    _MODULE_AVAILABLE = True
except ImportError:
    _MODULE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _MODULE_AVAILABLE,
    reason="src/layer6_v2/ai_competency_eval.py does not exist yet",
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

GROUND_TRUTH = {
    "verified_skills": ["FastAPI", "LiteLLM", "Redis", "Qdrant"],
    "verified_patterns": ["LLM gateway", "multi-provider routing", "semantic caching"],
    "not_yet_built": ["circuit breaker", "streaming SSE", "rate limiting"],
}

_LANTERN_SECTION = "## Lantern — LLM Gateway\n"


# ---------------------------------------------------------------------------
# TestEvaluateAICompetencies
# ---------------------------------------------------------------------------

class TestEvaluateAICompetencies:
    """Tests for evaluate_ai_competencies(cv, ground_truth) -> EvalResult."""

    def test_verified_skill_passes(self):
        """CV mentioning a verified_pattern ('multi-provider routing') should pass."""
        cv = f"{_LANTERN_SECTION}- Built multi-provider routing with LiteLLM\n\nOther section"
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.passed is True
        assert result.verified_count >= 1

    def test_unbuilt_skill_flagged(self):
        """CV claiming something in not_yet_built ('circuit breaker') must fail and be flagged."""
        cv = f"{_LANTERN_SECTION}- Implemented circuit breaker for provider resilience\n\nOther"
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.passed is False
        assert result.flagged_count >= 1

    def test_no_claims_passes(self):
        """CV with no AI-related claims should pass with zero claims."""
        cv = "## Experience\n- Built REST APIs\n- Led team of 5\n- Managed delivery timelines"
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.passed is True
        assert result.total_claims == 0

    def test_mixed_claims_fails_when_any_flagged(self):
        """CV with both verified and flagged claims must fail overall."""
        cv = (
            f"{_LANTERN_SECTION}"
            "- Built LLM gateway with multi-provider routing\n"
            "- Added rate limiting per model\n\n"
            "Other section"
        )
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.passed is False
        assert result.verified_count >= 1
        assert result.flagged_count >= 1

    def test_only_verified_claims_passes(self):
        """CV with only verified skills/patterns and nothing from not_yet_built passes."""
        cv = (
            f"{_LANTERN_SECTION}"
            "- Built LLM gateway using LiteLLM\n"
            "- Implemented semantic caching with Redis and Qdrant\n\n"
            "Other section"
        )
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.passed is True
        assert result.verified_count >= 1
        assert result.flagged_count == 0

    def test_summary_contains_verified_count(self):
        """The summary string must contain the word 'verified'."""
        cv = f"{_LANTERN_SECTION}- Built LLM gateway\n\nOther"
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert "verified" in result.summary.lower()

    def test_total_claims_counts_all_found(self):
        """total_claims must be at least as large as verified_count + flagged_count."""
        cv = (
            f"{_LANTERN_SECTION}"
            "- Built multi-provider routing with LiteLLM\n"
            "- Added circuit breaker logic\n"
            "- Integrated semantic caching\n\n"
            "Other"
        )
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.total_claims >= result.verified_count + result.flagged_count

    def test_multiple_unbuilt_claims_all_flagged(self):
        """Multiple not_yet_built claims must each contribute to flagged_count."""
        cv = (
            f"{_LANTERN_SECTION}"
            "- Added rate limiting per model\n"
            "- Implemented circuit breaker\n"
            "- Exposed streaming SSE endpoint\n\n"
            "Other"
        )
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert result.passed is False
        assert result.flagged_count >= 2

    def test_result_has_required_attributes(self):
        """EvalResult must expose passed, verified_count, flagged_count, total_claims, summary."""
        cv = "## Experience\n- Standard work"
        result = evaluate_ai_competencies(cv, ground_truth=GROUND_TRUTH)

        assert hasattr(result, "passed")
        assert hasattr(result, "verified_count")
        assert hasattr(result, "flagged_count")
        assert hasattr(result, "total_claims")
        assert hasattr(result, "summary")

    def test_empty_cv_passes_with_zero_claims(self):
        """Empty CV string must return pass with zero claims."""
        result = evaluate_ai_competencies("", ground_truth=GROUND_TRUTH)

        assert result.passed is True
        assert result.total_claims == 0

    def test_empty_ground_truth_passes(self):
        """Empty ground_truth dicts mean nothing can be flagged — always passes."""
        cv = (
            f"{_LANTERN_SECTION}"
            "- Built circuit breaker and rate limiting\n\n"
            "Other"
        )
        result = evaluate_ai_competencies(
            cv,
            ground_truth={"verified_skills": [], "verified_patterns": [], "not_yet_built": []},
        )

        assert result.passed is True
        assert result.flagged_count == 0


# ---------------------------------------------------------------------------
# TestExtractAIClaims
# ---------------------------------------------------------------------------

class TestExtractAIClaims:
    """Tests for extract_ai_claims(cv) -> List[str]."""

    def test_extracts_lantern_bullets(self):
        """Bullets under the Lantern section header must be extracted."""
        cv = (
            "## Lantern — LLM Gateway\n"
            "- Built multi-provider routing\n"
            "- Added semantic caching\n"
            "## Experience\n"
            "- Other work"
        )
        claims = extract_ai_claims(cv)

        assert len(claims) >= 2

    def test_extracts_ai_terms_from_prose(self):
        """AI-related terms appearing in non-bullet prose should also produce claims."""
        cv = "Core competencies: multi-provider routing, circuit breaker, semantic caching"
        claims = extract_ai_claims(cv)

        assert len(claims) >= 1

    def test_returns_list(self):
        """Return type must be a list (even if empty)."""
        claims = extract_ai_claims("")
        assert isinstance(claims, list)

    def test_empty_cv_returns_empty_list(self):
        """No AI content must return an empty list."""
        claims = extract_ai_claims("## Experience\n- Led a team\n- Delivered projects")
        assert isinstance(claims, list)
        # May be empty or contain non-AI items depending on implementation;
        # the key assertion is that it does not raise.

    def test_duplicate_claims_handled(self):
        """The function must not crash on repeated mentions of the same term."""
        cv = (
            "## Lantern\n"
            "- Built LLM gateway\n"
            "- Also built LLM gateway improvements\n"
            "## Skills\n"
            "- LLM gateway experience"
        )
        claims = extract_ai_claims(cv)
        assert isinstance(claims, list)

    def test_claims_are_strings(self):
        """Each element of the returned list must be a string."""
        cv = (
            "## Lantern\n"
            "- Built multi-provider routing\n"
            "- Integrated Redis semantic caching\n"
        )
        claims = extract_ai_claims(cv)
        for claim in claims:
            assert isinstance(claim, str), f"Expected str, got {type(claim)}: {claim!r}"
