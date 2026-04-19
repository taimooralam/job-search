"""Tests for the iteration-4 preenrich stage registry."""

from src.preenrich.stage_registry import get_stage_definition, iter_stage_definitions, stage_registry


def test_stage_registry_contains_the_initial_eight_stages():
    assert list(stage_registry().keys()) == [
        "jd_structure",
        "jd_extraction",
        "ai_classification",
        "pain_points",
        "annotations",
        "persona",
        "company_research",
        "role_research",
    ]


def test_stage_registry_matches_required_attempt_defaults():
    registry = stage_registry()
    assert registry["jd_structure"].max_attempts == 3
    assert registry["jd_extraction"].max_attempts == 3
    assert registry["ai_classification"].max_attempts == 3
    assert registry["pain_points"].max_attempts == 3
    assert registry["annotations"].max_attempts == 3
    assert registry["persona"].max_attempts == 3
    assert registry["company_research"].max_attempts == 5
    assert registry["role_research"].max_attempts == 5


def test_stage_registry_preserves_linear_iteration_four_dag():
    assert get_stage_definition("jd_extraction").prerequisites == ("jd_structure",)
    assert get_stage_definition("ai_classification").prerequisites == ("jd_extraction",)
    assert get_stage_definition("pain_points").prerequisites == ("jd_extraction",)
    assert get_stage_definition("annotations").prerequisites == ("pain_points",)
    assert get_stage_definition("persona").prerequisites == ("annotations",)
    assert get_stage_definition("company_research").prerequisites == ("persona",)
    assert get_stage_definition("role_research").prerequisites == ("company_research",)


def test_every_registered_stage_is_required_for_cv_ready_in_initial_slice():
    assert all(stage.required_for_cv_ready for stage in iter_stage_definitions())


def test_every_registered_stage_uses_preenrich_task_type_prefix():
    assert all(stage.task_type.startswith("preenrich.") for stage in iter_stage_definitions())
