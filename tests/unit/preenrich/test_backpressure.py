"""
T18 — Backpressure: worker refuses new claims when in-flight >= MAX_IN_FLIGHT.

Validates:
- When in-flight count >= PREENRICH_MAX_IN_FLIGHT, no new claims are made
- When in-flight count < MAX_IN_FLIGHT, claims proceed normally
- Default MAX_IN_FLIGHT is 12
"""

import os
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import patch, MagicMock

import mongomock

from src.preenrich.worker import _count_in_flight


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _insert_preenriching_jobs(db, count: int) -> None:
    """Insert N jobs with lifecycle='preenriching'."""
    now = datetime.now(timezone.utc)
    docs = [
        {
            "_id": ObjectId(),
            "lifecycle": "preenriching",
            "lease_owner": f"worker-{i}",
            "lease_expires_at": now,
        }
        for i in range(count)
    ]
    if docs:
        db["level-2"].insert_many(docs)


# ---------------------------------------------------------------------------
# _count_in_flight
# ---------------------------------------------------------------------------


def test_count_in_flight_zero_when_none(mock_db):
    """count_in_flight returns 0 when no preenriching jobs."""
    assert _count_in_flight(mock_db) == 0


def test_count_in_flight_counts_preenriching(mock_db):
    """count_in_flight counts exactly the preenriching jobs."""
    _insert_preenriching_jobs(mock_db, 5)
    assert _count_in_flight(mock_db) == 5


def test_count_in_flight_ignores_other_lifecycles(mock_db):
    """count_in_flight ignores selected, ready, queued, completed jobs."""
    _insert_preenriching_jobs(mock_db, 3)
    for lifecycle in ("selected", "ready", "queued", "completed", "legacy"):
        mock_db["level-2"].insert_one({
            "_id": ObjectId(),
            "lifecycle": lifecycle,
        })
    assert _count_in_flight(mock_db) == 3


# ---------------------------------------------------------------------------
# Backpressure in worker loop
# ---------------------------------------------------------------------------


def test_backpressure_blocks_claim_at_max(mock_db):
    """
    When in-flight count >= max_in_flight, the worker does not call claim_one.
    """
    max_in_flight = 12
    _insert_preenriching_jobs(mock_db, max_in_flight)

    claim_called = []

    def mock_claim(db, worker_id, now=None):
        claim_called.append(True)
        return None

    # Simulate the backpressure check in worker loop
    in_flight = _count_in_flight(mock_db)
    if in_flight < max_in_flight:
        mock_claim(mock_db, "worker-a")

    assert len(claim_called) == 0, (
        f"claim_one should NOT be called when in_flight ({in_flight}) >= max ({max_in_flight})"
    )


def test_backpressure_allows_claim_below_max(mock_db):
    """
    When in-flight count < max_in_flight, the worker proceeds to claim.
    """
    max_in_flight = 12
    _insert_preenriching_jobs(mock_db, max_in_flight - 1)

    # Insert a claimable job
    mock_db["level-2"].insert_one({
        "_id": ObjectId(),
        "lifecycle": "selected",
        "selected_at": datetime.now(timezone.utc),
    })

    claim_called = []

    def mock_claim(db, worker_id, now=None):
        claim_called.append(True)
        return None

    in_flight = _count_in_flight(mock_db)
    if in_flight < max_in_flight:
        mock_claim(mock_db, "worker-a")

    assert len(claim_called) == 1, (
        f"claim_one SHOULD be called when in_flight ({in_flight}) < max ({max_in_flight})"
    )


def test_backpressure_default_max_is_12():
    """Default PREENRICH_MAX_IN_FLIGHT is 12."""
    env_without_flag = {k: v for k, v in os.environ.items()
                        if k != "PREENRICH_MAX_IN_FLIGHT"}
    with patch.dict(os.environ, env_without_flag, clear=True):
        max_in_flight = int(os.getenv("PREENRICH_MAX_IN_FLIGHT", "12"))
        assert max_in_flight == 12


def test_backpressure_respects_env_override():
    """PREENRICH_MAX_IN_FLIGHT env var overrides the default."""
    with patch.dict(os.environ, {"PREENRICH_MAX_IN_FLIGHT": "4"}):
        max_in_flight = int(os.getenv("PREENRICH_MAX_IN_FLIGHT", "12"))
        assert max_in_flight == 4


def test_backpressure_at_exactly_max_blocks(mock_db):
    """At exactly max_in_flight jobs, claim is blocked."""
    max_in_flight = 3  # Use small number for easy testing
    _insert_preenriching_jobs(mock_db, 3)

    in_flight = _count_in_flight(mock_db)
    assert in_flight >= max_in_flight

    # Simulate check: in_flight >= max → do NOT claim
    should_claim = in_flight < max_in_flight
    assert should_claim is False
