"""Tests for iteration-4.1 blueprint index migration."""

from scripts.migrations.iteration41_blueprint_indexes import build_index_plan


def test_blueprint_index_plan_contains_required_collections():
    plan = build_index_plan()
    assert {
        "jd_facts",
        "job_inference",
        "job_hypotheses",
        "research_enrichment",
        "cv_guidelines",
        "job_blueprint",
        "level-2",
    }.issubset(plan.keys())


def test_job_blueprint_unique_index_is_pinned():
    spec = next(item for item in build_index_plan()["job_blueprint"] if item["kwargs"]["name"] == "job_blueprint_unique")
    assert spec["keys"] == [("job_id", 1), ("blueprint_version", 1)]
    assert spec["kwargs"]["unique"] is True
