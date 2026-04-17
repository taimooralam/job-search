"""
T6 — Outbox producer and consumer.

Validates:
- Producer SET NX dedupe: second enqueue call for the same queue_key is skipped
- Consumer retries on 5xx
- Consumer deadletters after MAX_DELIVERY_ATTEMPTS (5) failed attempts
- Consumer treats {"status":"duplicate"} as success (ACK)
- X-Idempotency-Key header is included in every POST

Uses mongomock + fakeredis.
"""

import json
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import MagicMock, patch, call

import mongomock
import fakeredis

from src.preenrich.outbox import (
    enqueue_ready,
    outbox_consumer_tick,
    STREAM_KEY,
    DEADLETTER_KEY,
    CONSUMER_GROUP,
    MAX_DELIVERY_ATTEMPTS,
    DEDUPE_KEY_TTL_SECONDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


def _insert_ready_job(db, jd_checksum="sha256:abc") -> ObjectId:
    """Insert a job in lifecycle='ready' and return its _id."""
    oid = ObjectId()
    db["level-2"].insert_one({
        "_id": oid,
        "lifecycle": "ready",
        "pre_enrichment": {"jd_checksum": jd_checksum},
    })
    return oid


# ---------------------------------------------------------------------------
# Producer: SET NX dedupe
# ---------------------------------------------------------------------------


def test_enqueue_ready_enqueues_single_job(mock_db, redis_client):
    """A ready job is XADD'd to the stream and lifecycle flips to 'queued'."""
    _insert_ready_job(mock_db, jd_checksum="sha256:abc")
    count = enqueue_ready(mock_db, redis_client)
    assert count == 1

    # Lifecycle should be queued now
    doc = mock_db["level-2"].find_one({"lifecycle": "queued"})
    assert doc is not None


def test_enqueue_ready_dedupe_skips_second_call(mock_db, redis_client):
    """
    Producer SET NX dedupe: second call for the same job+checksum is skipped.
    The key exists so XADD is not repeated.
    """
    job_id = _insert_ready_job(mock_db, jd_checksum="sha256:abc")

    # First enqueue
    count1 = enqueue_ready(mock_db, redis_client)
    assert count1 == 1

    # Reset lifecycle to 'ready' to simulate re-enqueue attempt
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"lifecycle": "ready"}},
    )

    # Second attempt — dedupe key is set, should skip XADD
    count2 = enqueue_ready(mock_db, redis_client)
    assert count2 == 0


def test_enqueue_ready_dedupe_key_set_with_ttl(mock_db, redis_client):
    """Producer sets Redis key with NX and EX (TTL)."""
    job_id = _insert_ready_job(mock_db, jd_checksum="sha256:xyz")
    enqueue_ready(mock_db, redis_client)

    jd_cs = "sha256:xyz"
    queue_key = f"batch-pipeline:{str(job_id)}:{jd_cs}"
    seen_key = f"preenrich:outbox_seen:{queue_key}"

    assert redis_client.exists(seen_key)
    ttl = redis_client.ttl(seen_key)
    assert ttl > 0
    assert ttl <= DEDUPE_KEY_TTL_SECONDS


def test_enqueue_ready_no_jobs_returns_zero(mock_db, redis_client):
    """Returns 0 when no ready jobs exist."""
    count = enqueue_ready(mock_db, redis_client)
    assert count == 0


# ---------------------------------------------------------------------------
# Consumer: ACK on success
# ---------------------------------------------------------------------------


def _seed_stream(redis_client, job_id="job1", jd_checksum="sha256:abc") -> None:
    """Add a message to the stream and set up the consumer group."""
    queue_key = f"batch-pipeline:{job_id}:{jd_checksum}"
    redis_client.xadd(STREAM_KEY, {
        "job_id": job_id,
        "jd_checksum": jd_checksum,
        "queue_key": queue_key,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    })


def _make_runner(status_code=200, body=None):
    """Build a mock runner_client with configurable response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = json.dumps(body or {"status": "ok"})
    if body is not None:
        resp.json.return_value = body
    else:
        resp.json.return_value = {"status": "ok"}
    runner = MagicMock()
    runner.post.return_value = resp
    return runner


def test_consumer_acks_on_200(redis_client):
    """Consumer ACKs message when runner returns 200."""
    _seed_stream(redis_client)
    runner = _make_runner(status_code=200)

    stats = outbox_consumer_tick(redis_client, runner)
    assert stats["acked"] == 1
    assert stats["retried"] == 0
    assert stats["deadlettered"] == 0


def test_consumer_acks_on_duplicate_status(redis_client):
    """Consumer ACKs message when runner returns 200 with {"status":"duplicate"}."""
    _seed_stream(redis_client)
    runner = _make_runner(status_code=200, body={"status": "duplicate"})

    stats = outbox_consumer_tick(redis_client, runner)
    assert stats["acked"] == 1


def test_consumer_sends_idempotency_key_header(redis_client):
    """Consumer includes X-Idempotency-Key header in every POST."""
    _seed_stream(redis_client, job_id="job_hdr", jd_checksum="sha256:hdr")
    runner = _make_runner(status_code=200)

    outbox_consumer_tick(redis_client, runner)

    runner.post.assert_called_once()
    _, kwargs = runner.post.call_args
    headers = kwargs.get("headers", {})
    assert "X-Idempotency-Key" in headers
    assert "batch-pipeline:job_hdr:sha256:hdr" == headers["X-Idempotency-Key"]


# ---------------------------------------------------------------------------
# Consumer: retry on 5xx
# ---------------------------------------------------------------------------


def test_consumer_retries_on_5xx(redis_client):
    """Consumer does NOT ACK on 5xx — increments delivery_count and retries."""
    _seed_stream(redis_client)
    runner = _make_runner(status_code=500)

    stats = outbox_consumer_tick(redis_client, runner)
    assert stats["retried"] == 1
    assert stats["acked"] == 0
    assert stats["deadlettered"] == 0


# ---------------------------------------------------------------------------
# Consumer: deadletter after MAX_DELIVERY_ATTEMPTS
# ---------------------------------------------------------------------------


def test_consumer_deadletters_after_max_attempts(redis_client):
    """
    After MAX_DELIVERY_ATTEMPTS failures, message routes to deadletter stream.
    """
    # Seed message with delivery_count = MAX_DELIVERY_ATTEMPTS - 1
    # so the next attempt triggers deadletter
    queue_key = "batch-pipeline:job_dl:sha256:abc"
    redis_client.xadd(STREAM_KEY, {
        "job_id": "job_dl",
        "jd_checksum": "sha256:abc",
        "queue_key": queue_key,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "delivery_count": str(MAX_DELIVERY_ATTEMPTS - 1),
    })

    runner = _make_runner(status_code=503)

    stats = outbox_consumer_tick(redis_client, runner)
    assert stats["deadlettered"] == 1
    assert stats["acked"] == 0

    # Deadletter stream should contain the message
    messages = redis_client.xrange(DEADLETTER_KEY, "-", "+")
    assert len(messages) == 1
    _, fields = messages[0]
    # Decode bytes
    decoded = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in fields.items()
    }
    assert decoded["job_id"] == "job_dl"
    assert int(decoded["delivery_count"]) == MAX_DELIVERY_ATTEMPTS


def test_max_delivery_attempts_is_five():
    """Plan §2.4 specifies 5 attempts with backoff [1,4,16,60,300]."""
    assert MAX_DELIVERY_ATTEMPTS == 5
