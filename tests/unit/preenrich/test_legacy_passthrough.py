"""
T16 — Legacy job passthrough (S11).

Validates:
- claim_one does NOT pick up jobs with lifecycle='legacy'
- Worker correctly ignores legacy jobs (they stay in lifecycle='legacy')
- Legacy jobs are NOT transitioned to 'preenriching'

BDD S11: Given a pre-existing level-2 job with no pre_enrichment field,
when the worker ticks, then it sets lifecycle="legacy" and the job is
handled by the runner with today's Full Extraction path.
"""

from datetime import datetime, timezone

import mongomock
import pytest
from bson import ObjectId

from src.preenrich.lease import claim_one

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _insert_job(db, lifecycle: str, has_pre_enrichment: bool = False) -> ObjectId:
    """Insert a job document."""
    oid = ObjectId()
    doc = {
        "_id": oid,
        "lifecycle": lifecycle,
        "selected_at": datetime.now(timezone.utc),
        "description": "Test job description",
    }
    if has_pre_enrichment:
        doc["pre_enrichment"] = {"jd_checksum": "sha256:abc"}
    db["level-2"].insert_one(doc)
    return oid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_legacy_job_not_claimed(mock_db):
    """Worker does not claim a job with lifecycle='legacy' (S11)."""
    _insert_job(mock_db, "legacy", has_pre_enrichment=False)
    result = claim_one(mock_db, worker_id="worker-a")
    assert result is None


def test_legacy_stays_legacy_after_claim_attempt(mock_db):
    """legacy lifecycle is preserved after a claim attempt."""
    job_id = _insert_job(mock_db, "legacy", has_pre_enrichment=False)
    claim_one(mock_db, worker_id="worker-a")

    doc = mock_db["level-2"].find_one({"_id": job_id})
    assert doc["lifecycle"] == "legacy"


def test_selected_job_is_claimed_while_legacy_is_ignored(mock_db):
    """Worker claims 'selected' job while 'legacy' job is ignored."""
    _insert_job(mock_db, "legacy")
    selected_id = _insert_job(mock_db, "selected")

    result = claim_one(mock_db, worker_id="worker-a")
    assert result is not None
    assert result["_id"] == selected_id
    assert result["lifecycle"] == "preenriching"

    # Legacy job remains untouched
    legacy_doc = mock_db["level-2"].find_one({"lifecycle": "legacy"})
    assert legacy_doc is not None


def test_multiple_legacy_jobs_all_ignored(mock_db):
    """All legacy jobs are ignored when no selected/stale jobs exist."""
    for _ in range(3):
        _insert_job(mock_db, "legacy")

    result = claim_one(mock_db, worker_id="worker-a")
    assert result is None


def test_backfill_lifecycle_sets_legacy_for_no_pre_enrichment(mock_db):
    """
    The migration backfill logic sets lifecycle='legacy' for jobs without
    pre_enrichment. Simulating the migration script behavior:
    jobs without pre_enrichment field should be updated to lifecycle='legacy'.
    """
    # Insert jobs WITHOUT pre_enrichment field (pre-existing jobs)
    oid1 = ObjectId()
    oid2 = ObjectId()
    mock_db["level-2"].insert_many([
        {"_id": oid1, "title": "Old job 1", "description": "old"},
        {"_id": oid2, "title": "Old job 2", "description": "old"},
    ])

    # Simulate migration backfill
    mock_db["level-2"].update_many(
        {"pre_enrichment": {"$exists": False}},
        {"$set": {"lifecycle": "legacy"}},
    )

    # After backfill, both jobs should be legacy
    count = mock_db["level-2"].count_documents({"lifecycle": "legacy"})
    assert count == 2

    # Worker should not claim any of them
    result = claim_one(mock_db, worker_id="worker-a")
    assert result is None
