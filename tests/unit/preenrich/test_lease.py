"""
T4 — Lease-based claim, heartbeat, and expiry recovery.

Validates:
- Exactly one of two concurrent workers claims a job (S5)
- Expired lease is re-claimable by another worker (S8)
- Heartbeat renews lease only when worker_id matches
- Legacy lifecycle ("legacy") is not claimable

Uses mongomock for Mongo isolation — no real infra.
"""

import pytest
from datetime import datetime, timedelta, timezone
from bson import ObjectId

import mongomock

from src.preenrich.lease import claim_one, heartbeat, release


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Return a mongomock database handle."""
    client = mongomock.MongoClient()
    return client["jobs"]


def _insert_job(db, lifecycle: str, lease_expires_at=None, lease_owner=None) -> ObjectId:
    """Insert a minimal job document and return its _id."""
    doc = {
        "_id": ObjectId(),
        "lifecycle": lifecycle,
        "selected_at": datetime.now(timezone.utc),
        "description": "Test job description",
    }
    if lease_expires_at is not None:
        doc["lease_expires_at"] = lease_expires_at
    if lease_owner is not None:
        doc["lease_owner"] = lease_owner
    db["level-2"].insert_one(doc)
    return doc["_id"]


# ---------------------------------------------------------------------------
# Claim tests
# ---------------------------------------------------------------------------


def test_claim_one_selected_job(mock_db):
    """A job with lifecycle='selected' is claimable."""
    _insert_job(mock_db, "selected")
    result = claim_one(mock_db, worker_id="worker-a")
    assert result is not None
    assert result["lifecycle"] == "preenriching"
    assert result["lease_owner"] == "worker-a"


def test_claim_one_stale_job(mock_db):
    """A job with lifecycle='stale' is claimable."""
    _insert_job(mock_db, "stale")
    result = claim_one(mock_db, worker_id="worker-b")
    assert result is not None
    assert result["lifecycle"] == "preenriching"


def test_claim_one_returns_none_when_no_jobs(mock_db):
    """Returns None when no claimable jobs exist."""
    result = claim_one(mock_db, worker_id="worker-a")
    assert result is None


def test_claim_one_race_exactly_one_winner(mock_db):
    """
    Two workers calling claim_one on the same job: exactly one wins (S5).

    With mongomock's findOneAndUpdate, the atomic operation ensures that
    the second worker gets None (the job has already been claimed).
    """
    _insert_job(mock_db, "selected")

    result_a = claim_one(mock_db, worker_id="worker-a")
    result_b = claim_one(mock_db, worker_id="worker-b")

    # Exactly one winner
    winners = [r for r in [result_a, result_b] if r is not None]
    assert len(winners) == 1

    # The winning document is in preenriching state
    winner = winners[0]
    assert winner["lifecycle"] == "preenriching"

    # DB confirms only one preenriching job
    count = mock_db["level-2"].count_documents({"lifecycle": "preenriching"})
    assert count == 1


def test_claim_one_ignores_already_claimed_active_lease(mock_db):
    """A job whose lease has not expired cannot be claimed by another worker."""
    now = datetime.now(timezone.utc)
    future = now + timedelta(minutes=10)
    _insert_job(mock_db, "preenriching", lease_expires_at=future, lease_owner="worker-a")

    # worker-b should NOT claim this job (lease active)
    result = claim_one(mock_db, worker_id="worker-b")
    assert result is None


def test_claim_one_takes_expired_lease(mock_db):
    """A job with an expired lease can be re-claimed (S8)."""
    now = datetime.now(timezone.utc)
    expired = now - timedelta(minutes=5)
    job_id = _insert_job(mock_db, "selected", lease_expires_at=expired)

    result = claim_one(mock_db, worker_id="worker-rescue")
    assert result is not None
    assert result["lifecycle"] == "preenriching"
    assert result["lease_owner"] == "worker-rescue"


def test_claim_one_ignores_legacy_lifecycle(mock_db):
    """Jobs with lifecycle='legacy' are NOT claimable (S11, T16)."""
    _insert_job(mock_db, "legacy")
    result = claim_one(mock_db, worker_id="worker-a")
    assert result is None


def test_claim_one_ignores_ready_lifecycle(mock_db):
    """Jobs already in 'ready' state are not claimable (outbox handles them)."""
    _insert_job(mock_db, "ready")
    result = claim_one(mock_db, worker_id="worker-a")
    assert result is None


# ---------------------------------------------------------------------------
# Heartbeat tests
# ---------------------------------------------------------------------------


def test_heartbeat_renews_lease_for_owner(mock_db):
    """Heartbeat extends lease when worker_id matches."""
    job_id = _insert_job(mock_db, "preenriching", lease_owner="worker-a")
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lease_owner": "worker-a"}},
    )
    renewed = heartbeat(mock_db, job_id, worker_id="worker-a")
    assert renewed is True


def test_heartbeat_fails_for_wrong_worker(mock_db):
    """Heartbeat returns False when worker_id doesn't match lease_owner."""
    job_id = _insert_job(mock_db, "preenriching", lease_owner="worker-a")
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lease_owner": "worker-a"}},
    )
    renewed = heartbeat(mock_db, job_id, worker_id="worker-b")
    assert renewed is False


def test_heartbeat_updates_timestamps(mock_db):
    """Heartbeat updates lease_expires_at and lease_heartbeat_at."""
    now = datetime.now(timezone.utc)
    job_id = _insert_job(mock_db, "preenriching", lease_owner="worker-a")
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lease_owner": "worker-a", "lease_expires_at": now}},
    )

    heartbeat(mock_db, job_id, worker_id="worker-a", now=now)

    doc = mock_db["level-2"].find_one({"_id": job_id})
    assert doc["lease_heartbeat_at"] is not None


# ---------------------------------------------------------------------------
# Release tests
# ---------------------------------------------------------------------------


def test_release_transitions_lifecycle(mock_db):
    """release() transitions lifecycle and returns True for matching worker."""
    job_id = _insert_job(mock_db, "preenriching")
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lease_owner": "worker-a"}},
    )
    ok = release(mock_db, job_id, "worker-a", "ready")
    assert ok is True

    doc = mock_db["level-2"].find_one({"_id": job_id})
    assert doc["lifecycle"] == "ready"


def test_release_fails_for_wrong_worker(mock_db):
    """release() returns False if lease_owner doesn't match."""
    job_id = _insert_job(mock_db, "preenriching")
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lease_owner": "worker-a"}},
    )
    ok = release(mock_db, job_id, "worker-b", "ready")
    assert ok is False
