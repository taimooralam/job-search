"""
Phase 2a: dispatcher ctx.job_doc refresh between stages.

Tests that run_sequence() merges each stage's output patch into ctx.job_doc
in-memory after the atomic Mongo persist, so subsequent stages in the same
sequence see upstream outputs.

Uses mongomock + real-stage-like objects (not MagicMock stubs).

Test S1: happy path — second stage reads first stage's output from ctx.job_doc.
Test S2: mid-sequence failure does NOT poison ctx.job_doc for a third stage
         (the third stage sees the first stage's output untouched).
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

try:
    import mongomock
    HAS_MONGOMOCK = True
except ImportError:
    HAS_MONGOMOCK = False

from src.preenrich.dispatcher import run_sequence
from src.preenrich.types import StageContext, StageResult, StepConfig

pytestmark = pytest.mark.skipif(
    not HAS_MONGOMOCK,
    reason="mongomock not installed",
)

WORKER_ID = "ctx-refresh-worker"
JD_CHECKSUM = "sha256:" + hashlib.sha256(b"context refresh test").hexdigest()


def _make_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _insert_job(db: Any) -> Dict[str, Any]:
    from bson import ObjectId

    job_doc = {
        "_id": ObjectId(),
        "title": "AI Platform Lead",
        "company": "TestCorp",
        "description": "context refresh test",
        "lifecycle": "preenriching",
        "lease_owner": WORKER_ID,
        "lease_expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc),
        "pre_enrichment": {
            "schema_version": 1,
            "jd_checksum": JD_CHECKSUM,
            "stages": {},
        },
    }
    db["level-2"].insert_one(job_doc)
    return job_doc


def _make_ctx(db: Any, job_doc: Dict[str, Any]) -> StageContext:
    return StageContext(
        job_doc=job_doc,
        jd_checksum=JD_CHECKSUM,
        company_checksum="sha256:" + hashlib.sha256(b"testcorp").hexdigest(),
        input_snapshot_id=JD_CHECKSUM,
        attempt_number=1,
        config=StepConfig(provider="claude"),
        shadow_mode=False,
    )


# ── Real-stage-like objects (not MagicMock) ───────────────────────────────────


class _StageA:
    """Stage A: writes 'stage_a_sentinel' into the output patch."""

    name = "jd_structure"
    dependencies: List[str] = []

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(
            output={"stage_a_sentinel": "value_from_stage_a"},
            provider_used="claude",
            model_used="test",
            prompt_version="v1",
        )


class _StageB:
    """
    Stage B: asserts that ctx.job_doc["stage_a_sentinel"] is populated
    before producing its own output.  Raises if upstream is missing.
    """

    name = "jd_extraction"
    dependencies: List[str] = []  # bypass DAG prereq enforcement for this test

    saw_upstream: Optional[str] = None  # captured for assertion

    def run(self, ctx: StageContext) -> StageResult:
        upstream_val = ctx.job_doc.get("stage_a_sentinel")
        _StageB.saw_upstream = upstream_val  # store for external assertion
        if upstream_val is None:
            raise ValueError(
                "ctx.job_doc does not contain 'stage_a_sentinel' — "
                "context refresh is broken (Phase 2a)"
            )
        return StageResult(
            output={"stage_b_result": f"saw:{upstream_val}"},
            provider_used="claude",
            model_used="test",
            prompt_version="v1",
        )


class _StageFailMiddle:
    """Stage that always raises to simulate mid-sequence failure."""

    name = "ai_classification"
    dependencies: List[str] = []

    def run(self, ctx: StageContext) -> StageResult:
        raise RuntimeError("deliberate mid-sequence failure for test")


class _StageCAfterFailure:
    """
    Stage after a mid-sequence failure. Should see Stage A's output
    but NEVER gets called (run_sequence stops on first failure).
    This is used to verify that a SUCCESSFUL stage before the failing
    one left ctx.job_doc intact.
    """

    name = "pain_points"
    dependencies: List[str] = []

    saw_upstream: Optional[str] = None

    def run(self, ctx: StageContext) -> StageResult:
        _StageCAfterFailure.saw_upstream = ctx.job_doc.get("stage_a_sentinel")
        return StageResult(
            output={"stage_c_result": "should_not_run"},
            provider_used="claude",
            model_used="test",
            prompt_version="v1",
        )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDispatcherContextRefreshHappyPath:
    def test_stage_b_sees_stage_a_output_in_ctx(self):
        """
        S1 — happy path: Stage B's run() receives a ctx.job_doc containing
        Stage A's output patch fields.

        Validates that run_sequence merges stage output into ctx.job_doc
        after each successful persist (Phase 2a fix).
        """
        db = _make_db()
        job_doc = _insert_job(db)
        ctx = _make_ctx(db, job_doc)

        _StageB.saw_upstream = None  # reset

        stages = [_StageA(), _StageB()]
        summary = run_sequence(db, ctx, stages, WORKER_ID)

        assert not summary["failed"], f"Unexpected failures: {summary['failed']}"
        assert "jd_structure" in summary["completed"]
        assert "jd_extraction" in summary["completed"]

        # The critical assertion: Stage B SAW Stage A's output in ctx.job_doc
        assert _StageB.saw_upstream == "value_from_stage_a", (
            f"Stage B did not see Stage A output — got: {_StageB.saw_upstream!r}. "
            "ctx.job_doc refresh is not working (Phase 2a)."
        )

    def test_stage_a_output_in_mongo_after_sequence(self):
        """Stage A's output is persisted to Mongo (not just in-memory merge)."""
        db = _make_db()
        job_doc = _insert_job(db)
        ctx = _make_ctx(db, job_doc)

        stages = [_StageA(), _StageB()]
        run_sequence(db, ctx, stages, WORKER_ID)

        doc = db["level-2"].find_one({"_id": job_doc["_id"]})
        assert doc is not None
        assert doc.get("stage_a_sentinel") == "value_from_stage_a"
        assert doc.get("stage_b_result", "").startswith("saw:")

    def test_ctx_job_doc_contains_stage_a_output_after_sequence(self):
        """ctx.job_doc is mutated in-place with Stage A's output."""
        db = _make_db()
        job_doc = _insert_job(db)
        ctx = _make_ctx(db, job_doc)

        stages = [_StageA(), _StageB()]
        run_sequence(db, ctx, stages, WORKER_ID)

        assert ctx.job_doc.get("stage_a_sentinel") == "value_from_stage_a"
        assert ctx.job_doc.get("stage_b_result", "").startswith("saw:")


class TestDispatcherContextRefreshMidFailure:
    def test_failure_stops_sequence_but_ctx_has_pre_failure_output(self):
        """
        S2 — mid-sequence failure: run_sequence stops at the failing stage.
        Stages after the failure are NOT called.
        ctx.job_doc still contains Stage A's output (the failure does not poison it).
        """
        db = _make_db()
        job_doc = _insert_job(db)
        ctx = _make_ctx(db, job_doc)

        _StageCAfterFailure.saw_upstream = None  # reset

        stages = [_StageA(), _StageFailMiddle(), _StageCAfterFailure()]
        summary = run_sequence(db, ctx, stages, WORKER_ID)

        # Sequence stops at the failing stage
        assert "ai_classification" in summary["failed"]
        assert "jd_structure" in summary["completed"]
        # Stage C never runs (stop on first failure)
        assert "pain_points" not in summary["completed"]
        assert "pain_points" not in summary["failed"]

        # Stage C was never called (run_sequence stops after failure)
        assert _StageCAfterFailure.saw_upstream is None, (
            "Stage C should NOT have been called after mid-sequence failure"
        )

        # ctx.job_doc still has Stage A's pre-failure output
        assert ctx.job_doc.get("stage_a_sentinel") == "value_from_stage_a", (
            "Stage A's output was poisoned by the subsequent failure — ctx.job_doc is incorrect"
        )
