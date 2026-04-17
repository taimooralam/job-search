"""
T2 — DAG order and transitive invalidation.

Validates:
- STAGE_ORDER covers all expected stages
- invalidate("jd") propagates transitively to the full JD-dependent subgraph
- invalidate("company") propagates to company-dependent subgraph only
- invalidate("priors") propagates to annotations → persona → fit_signal
- No cross-contamination (company change does NOT stale JD-only stages)
"""

import pytest

from src.preenrich.dag import STAGE_ORDER, invalidate


# ---------------------------------------------------------------------------
# Stage order
# ---------------------------------------------------------------------------


def test_stage_order_contains_all_v1_stages():
    """STAGE_ORDER must include all 8 Phase-2 stages in the correct order.

    fit_signal was dropped from Phase 2 scope (no live consumer in BatchPipelineService
    as of Phase 2 — Phase 5 runner-skip work will wire the consumer per plan §3.6).
    """
    expected = [
        "jd_structure",
        "jd_extraction",
        "ai_classification",
        "pain_points",
        "annotations",
        "persona",
        "company_research",
        "role_research",
    ]
    assert STAGE_ORDER == expected


def test_stage_order_starts_with_jd_structure():
    """jd_structure is always first (no dependencies)."""
    assert STAGE_ORDER[0] == "jd_structure"


def test_stage_order_ends_with_fit_signal():
    """role_research is last in Phase 2 (fit_signal deferred to Phase 5)."""
    assert STAGE_ORDER[-1] == "role_research"


def test_stage_order_jd_extraction_after_structure():
    """jd_extraction comes after jd_structure."""
    assert STAGE_ORDER.index("jd_extraction") > STAGE_ORDER.index("jd_structure")


def test_stage_order_persona_after_annotations():
    """persona comes after annotations."""
    assert STAGE_ORDER.index("persona") > STAGE_ORDER.index("annotations")


def test_stage_order_role_research_after_company():
    """role_research comes after company_research."""
    assert STAGE_ORDER.index("role_research") > STAGE_ORDER.index("company_research")


# ---------------------------------------------------------------------------
# JD invalidation
# ---------------------------------------------------------------------------


def test_jd_change_invalidates_jd_stages():
    """JD change directly invalidates jd_structure through annotations."""
    stale = invalidate({"jd"})
    for stage in ("jd_structure", "jd_extraction", "ai_classification", "pain_points", "annotations"):
        assert stage in stale, f"Expected '{stage}' in stale set after JD change"


def test_jd_change_transitively_invalidates_persona():
    """persona depends on annotations → must be stale after JD change."""
    stale = invalidate({"jd"})
    assert "persona" in stale


def test_jd_change_transitively_invalidates_role_research():
    """role_research depends on jd_extraction → stale after JD change."""
    stale = invalidate({"jd"})
    assert "role_research" in stale


def test_jd_change_transitively_invalidates_role_research_includes_fit_signal_placeholder():
    """fit_signal deferred to Phase 5 — role_research is the terminal dependent for JD changes."""
    stale = invalidate({"jd"})
    # fit_signal not in Phase 2 — role_research is the deepest JD-dependent stage
    assert "role_research" in stale
    assert "fit_signal" not in stale  # Explicitly dropped from Phase 2


def test_jd_change_does_not_invalidate_company_research():
    """company_research has no JD dependency → NOT stale after JD-only change."""
    stale = invalidate({"jd"})
    assert "company_research" not in stale


# ---------------------------------------------------------------------------
# Company invalidation
# ---------------------------------------------------------------------------


def test_company_change_invalidates_company_research():
    """company change directly invalidates company_research."""
    stale = invalidate({"company"})
    assert "company_research" in stale


def test_company_change_transitively_invalidates_role_research():
    """role_research depends on company_research → stale after company change."""
    stale = invalidate({"company"})
    assert "role_research" in stale


def test_company_change_terminal_dependent_is_role_research():
    """fit_signal deferred to Phase 5 — role_research is terminal for company changes."""
    stale = invalidate({"company"})
    assert "role_research" in stale
    assert "fit_signal" not in stale  # Explicitly dropped from Phase 2


def test_company_change_does_not_invalidate_jd_stages():
    """JD-only stages are NOT stale after company-only change."""
    stale = invalidate({"company"})
    for stage in ("jd_structure", "jd_extraction", "ai_classification", "pain_points", "annotations", "persona"):
        assert stage not in stale, f"'{stage}' should NOT be stale after company-only change"


# ---------------------------------------------------------------------------
# Priors invalidation
# ---------------------------------------------------------------------------


def test_priors_change_invalidates_annotations():
    """priors change directly invalidates annotations."""
    stale = invalidate({"priors"})
    assert "annotations" in stale


def test_priors_change_transitively_invalidates_persona():
    """persona depends on annotations → stale after priors change."""
    stale = invalidate({"priors"})
    assert "persona" in stale


def test_priors_change_terminal_dependent_is_persona():
    """fit_signal deferred to Phase 5 — persona is terminal for priors changes."""
    stale = invalidate({"priors"})
    assert "persona" in stale
    assert "fit_signal" not in stale  # Explicitly dropped from Phase 2


def test_priors_change_does_not_invalidate_jd_structure():
    """jd_structure has no priors dependency."""
    stale = invalidate({"priors"})
    assert "jd_structure" not in stale


def test_priors_change_does_not_invalidate_company_research():
    """company_research has no priors dependency."""
    stale = invalidate({"priors"})
    assert "company_research" not in stale


# ---------------------------------------------------------------------------
# Combined invalidation
# ---------------------------------------------------------------------------


def test_combined_jd_and_company_covers_all_phase2_stages():
    """When both jd and company change, all 8 Phase-2 stages are stale."""
    stale = invalidate({"jd", "company"})
    # All Phase 2 stages should be covered
    for stage in STAGE_ORDER:
        assert stage in stale, f"'{stage}' should be stale when both jd and company change"


def test_empty_invalidation():
    """invalidate with no inputs returns empty set."""
    assert invalidate(set()) == set()


def test_unknown_input_is_ignored():
    """Unknown input keys produce no invalidation."""
    assert invalidate({"nonexistent_input"}) == set()
