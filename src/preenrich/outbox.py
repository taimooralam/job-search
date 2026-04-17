"""
Durable enqueue outbox for pre-enrichment.

Implements the two-phase at-least-once delivery pattern (§2.4):

1. Producer (enqueue_ready): finds jobs in lifecycle "ready", checks Redis
   SET NX dedupe guard before XADD, then flips lifecycle to "queued" only on
   successful XADD.

2. Consumer (outbox_consumer_tick): reads from the stream via consumer-group,
   POSTs the runner's HTTP queue endpoint with X-Idempotency-Key header,
   ACKs on 2xx (including {"status":"duplicate"} from runner), retries on
   transient errors with exponential backoff, routes to deadletter after 5
   failed attempts.

Dedupe lifecycle (§2.4):
    - Producer: Redis SET NX `preenrich:outbox_seen:<queue_key>` EX 86400.
      If key already exists → skip XADD (already delivered).
    - Consumer: X-Idempotency-Key header on every runner POST.
    - Runner returning {"status":"duplicate"} → ACK as success.
    - Backoff schedule: [1, 4, 16, 60, 300] seconds (5 attempts).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Stream and consumer-group constants
STREAM_KEY = "preenrich:enqueue_outbox"
DEADLETTER_KEY = "preenrich:deadletter"
CONSUMER_GROUP = "preenrich-outbox"
MAX_DELIVERY_ATTEMPTS = 5

# Exponential backoff schedule (seconds) for consumer retries
BACKOFF_SCHEDULE = [1, 4, 16, 60, 300]

# Dedupe key TTL: 24h in seconds
DEDUPE_KEY_TTL_SECONDS = 86400


def _now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _dedupe_key(queue_key: str) -> str:
    """Build the Redis SET NX key for producer-side deduplication."""
    return f"preenrich:outbox_seen:{queue_key}"


def enqueue_ready(
    db: Any,
    redis: Any,
    now: Optional[datetime] = None,
) -> int:
    """
    Enqueue all jobs in lifecycle "ready" to the Redis outbox stream.

    For each ready job:
    1. Build queue_key = f"batch-pipeline:{job_id}:{jd_checksum}"
    2. Check Redis SET NX `preenrich:outbox_seen:<queue_key>` EX 86400.
       If key already exists, the job was already delivered — skip XADD.
    3. XADD message to preenrich:enqueue_outbox with
       {job_id, jd_checksum, queue_key}
    4. On XADD success, atomically update lifecycle to "queued" and set queued_at

    If XADD fails, the job remains in "ready" and will be retried next tick.

    Args:
        db: PyMongo database handle
        redis: Redis client with xadd(), set() (NX/EX) support
        now: Override for current time (default: UTC now). Used in tests.

    Returns:
        Number of jobs successfully enqueued.
    """
    if now is None:
        now = _now_utc()

    enqueued = 0
    cursor = db["level-2"].find({"lifecycle": "ready"})

    for job in cursor:
        job_id = str(job["_id"])
        pre = job.get("pre_enrichment", {})
        jd_cs = pre.get("jd_checksum", "")
        queue_key = f"batch-pipeline:{job_id}:{jd_cs}"

        # Producer-side dedupe: SET NX with 24h TTL
        seen_key = _dedupe_key(queue_key)
        acquired = redis.set(seen_key, "1", nx=True, ex=DEDUPE_KEY_TTL_SECONDS)
        if acquired is None or acquired is False:
            # Key already existed — already delivered; skip XADD
            logger.info(
                "Outbox dedupe: job %s already seen (queue_key=%s), skipping XADD",
                job_id,
                queue_key,
            )
            continue

        message = {
            "job_id": job_id,
            "jd_checksum": jd_cs,
            "queue_key": queue_key,
            "enqueued_at": now.isoformat(),
        }

        try:
            # XADD to Redis stream
            redis.xadd(STREAM_KEY, message)
        except Exception as exc:
            logger.warning(
                "XADD failed for job %s: %s — will retry next tick", job_id, exc
            )
            # Clear the dedupe key so the next tick can retry XADD
            try:
                redis.delete(seen_key)
            except Exception:
                pass
            continue

        # Only flip lifecycle after XADD succeeds
        result = db["level-2"].update_one(
            {"_id": job["_id"], "lifecycle": "ready"},
            {"$set": {"lifecycle": "queued", "queued_at": now}},
        )
        if result.matched_count > 0:
            enqueued += 1
            logger.info("Enqueued job %s (queue_key=%s)", job_id, queue_key)
        else:
            logger.warning(
                "Job %s lifecycle changed before queued update; XADD message orphaned",
                job_id,
            )

    return enqueued


def _is_duplicate_response(response: Any) -> bool:
    """
    Check if a runner HTTP response indicates a duplicate (idempotent replay).

    The runner returns 200 with body {"status": "duplicate"} when it has
    already processed this idempotency key.

    Args:
        response: HTTP response object with .text or .json() attribute

    Returns:
        True if the response body contains {"status": "duplicate"}
    """
    try:
        if hasattr(response, "json"):
            body = response.json()
        else:
            body = json.loads(getattr(response, "text", "{}"))
        return body.get("status") == "duplicate"
    except Exception:
        return False


def outbox_consumer_tick(
    redis: Any,
    runner_client: Any,
    consumer_name: str = "consumer-1",
    batch_size: int = 10,
) -> Dict[str, int]:
    """
    Process one tick of the outbox consumer.

    Reads pending messages from the Redis stream consumer-group, POSTs the
    runner's queue endpoint for each with X-Idempotency-Key header, and ACKs
    on HTTP 2xx (including {"status":"duplicate"} responses). On failure,
    increments the delivery_count; after MAX_DELIVERY_ATTEMPTS the message
    is routed to the deadletter stream.

    Backoff schedule: [1, 4, 16, 60, 300] seconds. The consumer does NOT
    sleep here — backoff state is tracked by delivery_count and the caller
    is responsible for scheduling retries.

    Args:
        redis: Redis client with xreadgroup(), xack(), xadd() support
        runner_client: Object with .post(queue_key, headers=...) -> response
                       (response has .status_code and .text/.json() attrs)
        consumer_name: Name of this consumer within the group
        batch_size: Max messages to read per tick

    Returns:
        Dict with counts: {"acked": N, "retried": N, "deadlettered": N}
    """
    stats = {"acked": 0, "retried": 0, "deadlettered": 0}

    # Ensure consumer group exists (idempotent)
    try:
        redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception:
        pass  # Group already exists

    # Read pending messages for this consumer
    messages = redis.xreadgroup(
        CONSUMER_GROUP,
        consumer_name,
        {STREAM_KEY: ">"},
        count=batch_size,
        block=0,
    )

    if not messages:
        return stats

    for _stream, entries in messages:
        for entry_id, fields in entries:
            # Decode bytes if needed (raw Redis client)
            decoded: Dict[str, str] = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in fields.items()
            }

            queue_key = decoded.get("queue_key", "")
            job_id = decoded.get("job_id", "")
            delivery_count = int(decoded.get("delivery_count", "0")) + 1

            # Build idempotency header for runner
            headers = {"X-Idempotency-Key": queue_key}

            try:
                response = runner_client.post(queue_key, headers=headers)
                if response.status_code in (200, 201, 202):
                    # ACK success — includes {"status":"duplicate"} which is
                    # treated as successful delivery per §2.4
                    redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
                    stats["acked"] += 1
                    logger.info(
                        "ACKed job %s (queue_key=%s, status=%d, duplicate=%s)",
                        job_id,
                        queue_key,
                        response.status_code,
                        _is_duplicate_response(response),
                    )
                else:
                    raise RuntimeError(
                        f"HTTP {response.status_code} from runner for {queue_key}"
                    )

            except Exception as exc:
                logger.warning(
                    "Outbox delivery failed for job %s (attempt %d): %s",
                    job_id,
                    delivery_count,
                    exc,
                )

                if delivery_count >= MAX_DELIVERY_ATTEMPTS:
                    # Route to deadletter
                    redis.xadd(
                        DEADLETTER_KEY,
                        {
                            "job_id": job_id,
                            "queue_key": queue_key,
                            "error": str(exc),
                            "delivery_count": str(delivery_count),
                        },
                    )
                    redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
                    stats["deadlettered"] += 1
                    logger.error(
                        "Deadlettered job %s after %d attempts",
                        job_id,
                        delivery_count,
                    )
                else:
                    # Increment delivery_count and re-add for retry
                    # (original stays pending until acked or deadlettered)
                    redis.xadd(
                        STREAM_KEY,
                        {**decoded, "delivery_count": str(delivery_count)},
                    )
                    stats["retried"] += 1

    return stats
