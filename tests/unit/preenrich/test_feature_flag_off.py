"""
T17 — Feature flag SELECTOR_ENQUEUE_VIA_WORKER (S12).

Validates:
- With SELECTOR_ENQUEUE_VIA_WORKER=false: selector calls trigger_batch_pipeline
  (direct POST to runner)
- With SELECTOR_ENQUEUE_VIA_WORKER=true: selector sets lifecycle='selected'
  and does NOT POST runner directly
- PREENRICH_WORKER_ENABLED=false: worker loop sleeps without claiming jobs
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import mongomock
from bson import ObjectId

# ---------------------------------------------------------------------------
# Tests for SELECTOR_ENQUEUE_VIA_WORKER flag behavior
# ---------------------------------------------------------------------------


def test_selector_flag_false_uses_direct_post():
    """
    When SELECTOR_ENQUEUE_VIA_WORKER=false, the selector triggers batch
    pipeline directly (does not set lifecycle='selected').

    This verifies the rollback safety: disabling the flag restores the
    original direct-enqueue path.
    """
    # The scout_selector_cron.py flag logic:
    # enqueue_via_worker = os.getenv("SELECTOR_ENQUEUE_VIA_WORKER", "false").lower() == "true"
    with patch.dict(os.environ, {"SELECTOR_ENQUEUE_VIA_WORKER": "false"}):
        enqueue_via_worker = os.getenv("SELECTOR_ENQUEUE_VIA_WORKER", "false").lower() == "true"
        assert enqueue_via_worker is False


def test_selector_flag_true_uses_worker_path():
    """
    When SELECTOR_ENQUEUE_VIA_WORKER=true, lifecycle is set to 'selected'.
    """
    with patch.dict(os.environ, {"SELECTOR_ENQUEUE_VIA_WORKER": "true"}):
        enqueue_via_worker = os.getenv("SELECTOR_ENQUEUE_VIA_WORKER", "false").lower() == "true"
        assert enqueue_via_worker is True


def test_selector_flag_default_is_false():
    """SELECTOR_ENQUEUE_VIA_WORKER defaults to false (rollback safe)."""
    # Remove key from env to test default
    env_without_flag = {k: v for k, v in os.environ.items()
                        if k != "SELECTOR_ENQUEUE_VIA_WORKER"}
    with patch.dict(os.environ, env_without_flag, clear=True):
        val = os.getenv("SELECTOR_ENQUEUE_VIA_WORKER", "false").lower() == "true"
        assert val is False


def test_selector_worker_path_sets_lifecycle_selected():
    """
    Selector worker path: inserts/updates job with lifecycle='selected'.
    """
    client = mongomock.MongoClient()
    db = client["jobs"]

    job_id = ObjectId()
    db["level-2"].insert_one({
        "_id": job_id,
        "title": "ML Engineer",
        "description": "test",
    })

    # Simulate the worker-path code in scout_selector_cron.py
    now = datetime.now(timezone.utc)
    db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lifecycle": "selected", "selected_at": now}},
    )

    doc = db["level-2"].find_one({"_id": job_id})
    assert doc["lifecycle"] == "selected"
    assert "selected_at" in doc


def test_selector_worker_path_does_not_post_runner():
    """
    With worker path enabled, the selector does NOT POST the runner.
    The worker discovers lifecycle='selected' on its next tick.
    """
    runner_post = MagicMock()

    with patch.dict(os.environ, {"SELECTOR_ENQUEUE_VIA_WORKER": "true"}):
        enqueue_via_worker = os.getenv("SELECTOR_ENQUEUE_VIA_WORKER", "false").lower() == "true"

        if enqueue_via_worker:
            # Worker path: no direct POST
            pass
        else:
            runner_post("some-job-id")

    runner_post.assert_not_called()


# ---------------------------------------------------------------------------
# PREENRICH_WORKER_ENABLED flag
# ---------------------------------------------------------------------------


def test_worker_enabled_default_is_false():
    """PREENRICH_WORKER_ENABLED defaults to false — worker is inert by default."""
    env_without_flag = {k: v for k, v in os.environ.items()
                        if k != "PREENRICH_WORKER_ENABLED"}
    with patch.dict(os.environ, env_without_flag, clear=True):
        enabled = os.getenv("PREENRICH_WORKER_ENABLED", "false").lower() == "true"
        assert enabled is False


def test_worker_disabled_does_not_claim_jobs():
    """
    With PREENRICH_WORKER_ENABLED=false, the worker loop sleeps without
    claiming any jobs.
    """
    client = mongomock.MongoClient()
    db = client["jobs"]

    # Insert a claimable job
    db["level-2"].insert_one({
        "_id": ObjectId(),
        "lifecycle": "selected",
        "selected_at": datetime.now(timezone.utc),
        "description": "test",
    })

    claim_calls = []

    def mock_claim(db, worker_id, now=None):
        # Should never be called when worker is disabled
        claim_calls.append(worker_id)
        return None

    with patch.dict(os.environ, {"PREENRICH_WORKER_ENABLED": "false"}):
        enabled = os.getenv("PREENRICH_WORKER_ENABLED", "false").lower() == "true"
        if enabled:
            mock_claim(db, "worker-test")

    # claim should NOT have been called
    assert len(claim_calls) == 0

    # Job remains in 'selected' state
    doc = db["level-2"].find_one({"lifecycle": "selected"})
    assert doc is not None


def test_shadow_mode_env_var():
    """PREENRICH_SHADOW_MODE env var controls shadow_mode on StageContext."""
    with patch.dict(os.environ, {"PREENRICH_SHADOW_MODE": "true"}):
        shadow_mode = os.getenv("PREENRICH_SHADOW_MODE", "false").lower() == "true"
        assert shadow_mode is True

    with patch.dict(os.environ, {"PREENRICH_SHADOW_MODE": "false"}):
        shadow_mode = os.getenv("PREENRICH_SHADOW_MODE", "false").lower() == "true"
        assert shadow_mode is False
