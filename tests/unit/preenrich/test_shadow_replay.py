"""
Tests for preenrich_shadow_replay.py — Phase 3 historical replay tool.

Validates:
- _select_jobs: correct filter against mongomock, returns docs
- _replay_job: calls run_sequence with shadow_mode=True; shadow namespace
  populated; live fields untouched.
- run_replay dry-run: selects jobs, skips stage execution.

External deps (LLM stages) are mocked to return deterministic output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import mongomock
import pytest
from bson import ObjectId

from src.preenrich.types import StageResult, StageStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_historical_job(db: Any, company: str = "Acme", tier: str = "quality") -> Dict[str, Any]:
    """Insert a historical job with all required live fields."""
    doc = {
        "_id": ObjectId(),
        "lifecycle": "completed",
        "company": company,
        "title": "AI Engineer",
        "description": "Build LLM pipelines at scale.",
        "company_url": "acme.com",
        "tier": tier,
        "extracted_jd": {"summary": "We build AI things.", "title": "AI Engineer"},
        "persona": {"summary": "Senior engineer comfortable with uncertainty."},
        "company_research": {"summary": "Acme is a great place to work."},
        "selected_at": datetime.now(timezone.utc),
    }
    db["level-2"].insert_one(doc)
    return doc


def _mock_stage(name: str, output: Dict[str, Any]) -> MagicMock:
    stage = MagicMock()
    stage.name = name
    stage.dependencies = []
    stage.run.return_value = StageResult(
        output=output,
        provider_used="claude",
        model_used="claude-haiku-4-5",
        prompt_version="v1",
        duration_ms=5,
        cost_usd=0.0001,
    )
    return stage


# ---------------------------------------------------------------------------
# _select_jobs
# ---------------------------------------------------------------------------

class TestSelectJobs:
    """Tests for the _select_jobs helper in preenrich_shadow_replay."""

    def test_select_returns_historical_jobs(self):
        """_select_jobs returns docs matching lifecycle+field filter."""
        from scripts.preenrich_shadow_replay import _select_jobs

        client = mongomock.MongoClient()
        db = client["jobs"]
        _make_historical_job(db, "AcmeCo")

        # Insert a non-eligible job (no extracted_jd)
        db["level-2"].insert_one({
            "_id": ObjectId(),
            "lifecycle": "completed",
            "company": "BadCo",
            "title": "Role",
        })

        jobs = _select_jobs(db, sample=10, tier=None, job_ids=None)
        companies = [j["company"] for j in jobs]
        assert "AcmeCo" in companies
        assert "BadCo" not in companies

    def test_select_filters_by_tier(self):
        """_select_jobs applies tier filter when provided."""
        from scripts.preenrich_shadow_replay import _select_jobs

        client = mongomock.MongoClient()
        db = client["jobs"]
        _make_historical_job(db, "QualityCompany", tier="quality")
        _make_historical_job(db, "NormalCompany", tier="standard")

        jobs = _select_jobs(db, sample=10, tier="quality", job_ids=None)
        companies = [j["company"] for j in jobs]
        assert "QualityCompany" in companies
        assert "NormalCompany" not in companies

    def test_select_by_explicit_job_ids(self):
        """_select_jobs retrieves specific jobs by ID list."""
        from scripts.preenrich_shadow_replay import _select_jobs

        client = mongomock.MongoClient()
        db = client["jobs"]
        job1 = _make_historical_job(db, "TargetCompany")
        _make_historical_job(db, "OtherCompany")

        jobs = _select_jobs(db, sample=10, tier=None, job_ids=[str(job1["_id"])])
        assert len(jobs) == 1
        assert jobs[0]["company"] == "TargetCompany"


# ---------------------------------------------------------------------------
# _replay_job
# ---------------------------------------------------------------------------

class TestReplayJob:
    """Tests for the _replay_job function."""

    def _setup(self):
        client = mongomock.MongoClient()
        db = client["jobs"]
        return db

    def test_replay_writes_shadow_namespace(self):
        """
        _replay_job calls run_sequence with shadow_mode=True; result lands
        in pre_enrichment.shadow_legacy_fields only.
        """
        from scripts.preenrich_shadow_replay import _replay_job

        db = self._setup()
        job_doc = _make_historical_job(db)
        worker_id = "test-worker"

        mock_jd_stage = _mock_stage("jd_structure", {"processed_jd_sections": ["sec1"]})

        with (
            patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": []}),
            patch(
                "scripts.preenrich_shadow_replay._build_stages",
                return_value=[mock_jd_stage],
            ),
        ):
            report = _replay_job(db, job_doc, [mock_jd_stage], worker_id, dry_run=False)

        refreshed = db["level-2"].find_one({"_id": job_doc["_id"]})

        # Live field must NOT be written
        assert "processed_jd_sections" not in refreshed, (
            "Shadow replay must not write to live top-level fields"
        )

        # Shadow fields must exist
        shadow_fields = refreshed.get("pre_enrichment", {}).get("shadow_legacy_fields", {})
        assert "processed_jd_sections" in shadow_fields

        # Report structure
        assert report["job_id"] == str(job_doc["_id"])
        assert "completed" in report or "failed" in report

    def test_replay_dry_run_skips_execution(self):
        """_replay_job with dry_run=True returns without calling stage.run()."""
        from scripts.preenrich_shadow_replay import _replay_job

        db = self._setup()
        job_doc = _make_historical_job(db)
        worker_id = "test-worker"

        mock_stage = _mock_stage("jd_structure", {"processed_jd_sections": []})

        report = _replay_job(db, job_doc, [mock_stage], worker_id, dry_run=True)

        assert report.get("dry_run") is True
        # Stage.run should not have been called
        mock_stage.run.assert_not_called()

    def test_replay_releases_lease_after_completion(self):
        """_replay_job unsets lease_owner after run_sequence completes."""
        from scripts.preenrich_shadow_replay import _replay_job

        db = self._setup()
        job_doc = _make_historical_job(db)
        worker_id = "test-worker-lease"

        mock_stage = _mock_stage("jd_structure", {"processed_jd_sections": []})

        with patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": []}):
            _replay_job(db, job_doc, [mock_stage], worker_id, dry_run=False)

        refreshed = db["level-2"].find_one({"_id": job_doc["_id"]})
        assert "lease_owner" not in refreshed or refreshed.get("lease_owner") is None

    def test_replay_report_contains_cost_and_timing(self):
        """_replay_job report includes total_cost_usd and total_duration_ms."""
        from scripts.preenrich_shadow_replay import _replay_job

        db = self._setup()
        job_doc = _make_historical_job(db)
        worker_id = "test-worker-cost"

        mock_stage = _mock_stage("jd_structure", {"processed_jd_sections": []})

        with patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": []}):
            report = _replay_job(db, job_doc, [mock_stage], worker_id, dry_run=False)

        assert "total_duration_ms" in report
        assert "total_cost_usd" in report
        assert isinstance(report["total_duration_ms"], int)
        assert isinstance(report["total_cost_usd"], float)
