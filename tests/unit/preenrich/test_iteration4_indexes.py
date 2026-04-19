"""Tests for the iteration-4 index migration plan."""

from scripts.migrations.iteration4_indexes import (
    TERMINAL_WORK_ITEM_STATUSES,
    TERMINAL_WORK_ITEM_TTL_SECONDS,
    build_index_plan,
)


def test_index_plan_contains_required_collections():
    plan = build_index_plan()
    assert set(plan.keys()) == {
        "level-2",
        "work_items",
        "preenrich_stage_runs",
        "preenrich_job_runs",
    }


def test_work_item_plan_includes_unique_idempotency_key_index():
    plan = build_index_plan()["work_items"]
    unique_spec = next(spec for spec in plan if spec["kwargs"]["name"] == "preenrich_idempotency_key_unique")
    assert unique_spec["keys"] == [("idempotency_key", 1)]
    assert unique_spec["kwargs"]["unique"] is True


def test_work_item_plan_uses_valid_partial_ttl_shape():
    plan = build_index_plan()["work_items"]
    ttl_spec = next(spec for spec in plan if spec["kwargs"]["name"] == "preenrich_terminal_work_items_ttl")
    assert ttl_spec["keys"] == [("updated_at", 1)]
    assert ttl_spec["kwargs"]["expireAfterSeconds"] == TERMINAL_WORK_ITEM_TTL_SECONDS
    assert ttl_spec["kwargs"]["partialFilterExpression"] == {
        "status": {"$in": list(TERMINAL_WORK_ITEM_STATUSES)}
    }
