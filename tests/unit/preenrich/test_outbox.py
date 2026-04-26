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
from datetime import datetime, timezone
from unittest.mock import MagicMock

import fakeredis
import mongomock
import pytest
from bson import ObjectId

from src.preenrich.outbox import (
    DEADLETTER_KEY,
    DEDUPE_KEY_TTL_SECONDS,
    MAX_DELIVERY_ATTEMPTS,
    STREAM_KEY,
    enqueue_ready,
    outbox_consumer_tick,
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


@pytest.fixture
def capture_trace_events(monkeypatch):
    captured = []

    def _fake_emit(**kwargs):
        captured.append(kwargs)
        return {"trace_id": None, "trace_url": None}

    monkeypatch.setattr("src.preenrich.outbox.emit_standalone_event", _fake_emit)
    return captured


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


def test_enqueue_ready_emits_trace_event(mock_db, redis_client, capture_trace_events):
    job_id = _insert_ready_job(mock_db, jd_checksum="sha256:trace")

    count = enqueue_ready(mock_db, redis_client)

    assert count == 1
    assert [event["name"] for event in capture_trace_events] == ["scout.preenrich.outbox.enqueue"]
    event = capture_trace_events[0]
    assert event["session_id"] == f"job:{job_id}"
    assert event["metadata"]["level2_job_id"] == str(job_id)
    assert event["metadata"]["lifecycle_before"] == "ready"
    assert event["metadata"]["lifecycle_after"] == "queued"


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


def test_consumer_retry_and_deadletter_emit_trace_events(redis_client, capture_trace_events):
    _seed_stream(redis_client, job_id="job_trace", jd_checksum="sha256:trace")
    retry_runner = _make_runner(status_code=500)

    retry_stats = outbox_consumer_tick(redis_client, retry_runner)

    assert retry_stats["retried"] == 1
    retry_event = next(event for event in capture_trace_events if event["name"] == "scout.preenrich.outbox.retry")
    assert retry_event["metadata"]["level2_job_id"] == "job_trace"
    assert retry_event["metadata"]["attempt_count"] == 1

    capture_trace_events.clear()
    queue_key = "batch-pipeline:job_trace_dl:sha256:abc"
    redis_client.xadd(
        STREAM_KEY,
        {
            "job_id": "job_trace_dl",
            "jd_checksum": "sha256:abc",
            "queue_key": queue_key,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "delivery_count": str(MAX_DELIVERY_ATTEMPTS - 1),
        },
    )
    deadletter_runner = _make_runner(status_code=503)

    deadletter_stats = outbox_consumer_tick(redis_client, deadletter_runner)

    assert deadletter_stats["deadlettered"] == 1
    deadletter_event = next(
        event for event in capture_trace_events if event["name"] == "scout.preenrich.outbox.deadletter"
    )
    assert deadletter_event["metadata"]["level2_job_id"] == "job_trace_dl"
    assert deadletter_event["metadata"]["lifecycle_after"] == "deadletter"


def test_max_delivery_attempts_is_five():
    """Plan §2.4 specifies 5 attempts with backoff [1,4,16,60,300]."""
    assert MAX_DELIVERY_ATTEMPTS == 5
