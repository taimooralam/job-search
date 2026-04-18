"""Tests for the iteration-1 discovery queue foundation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import mongomock

from src.pipeline.discovery import SearchDiscoveryStore
from src.pipeline.legacy_scrape_handoff import LegacyScrapeHandoffBridge
from src.pipeline.queue import WorkItemQueue


def _db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _naive_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


def test_search_run_created_and_finalized():
    db = _db()
    store = SearchDiscoveryStore(db)
    store.ensure_indexes()

    started_at = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    ctx = store.create_search_run(
        trigger_mode="cron",
        command_mode="full",
        region_filter="eea",
        profile_filter="ai_core",
        time_filter="r43200",
        now=started_at,
    )

    running = db["search_runs"].find_one({"run_id": ctx.run_id})
    assert running is not None
    assert running["status"] == "running"
    assert running["langfuse_session_id"] == ctx.langfuse_session_id

    completed_at = started_at + timedelta(minutes=5)
    store.finalize_search_run(
        ctx.run_id,
        status="completed",
        stats={
            "raw_found": 4,
            "after_blacklist": 3,
            "after_db_dedupe": 2,
            "hits_upserted": 2,
            "work_items_created": 2,
            "legacy_handoffs_created": 1,
        },
        errors=[],
        now=completed_at,
    )

    finalized = db["search_runs"].find_one({"run_id": ctx.run_id})
    assert finalized["status"] == "completed"
    assert finalized["completed_at"] == _naive_utc(completed_at)
    assert finalized["stats"]["work_items_created"] == 2


def test_search_hit_upsert_updates_last_seen_and_times_seen():
    db = _db()
    store = SearchDiscoveryStore(db)
    store.ensure_indexes()

    first_seen = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    first = store.upsert_search_hit(
        source="linkedin",
        external_job_id="123",
        job_url="https://www.linkedin.com/jobs/view/123/",
        title="Senior AI Engineer",
        company="Acme",
        location="Remote",
        search_profile="ai_core",
        search_region="eea",
        source_cron="hourly",
        run_id="run-1",
        correlation_id="hit:linkedin:123",
        langfuse_session_id="hit:linkedin:123",
        scout_metadata={"remote_only": True},
        raw_search_payload={"job_id": "123"},
        now=first_seen,
    )

    second_seen = first_seen + timedelta(hours=1)
    second = store.upsert_search_hit(
        source="linkedin",
        external_job_id="123",
        job_url="https://www.linkedin.com/jobs/view/123/",
        title="Senior AI Engineer",
        company="Acme",
        location="Remote",
        search_profile="ai_core",
        search_region="eea",
        source_cron="hourly",
        run_id="run-2",
        correlation_id="hit:linkedin:123",
        langfuse_session_id="hit:linkedin:123",
        scout_metadata={"remote_only": True},
        raw_search_payload={"job_id": "123"},
        now=second_seen,
    )

    assert first.inserted is True
    assert second.inserted is False

    document = db["scout_search_hits"].find_one({"_id": first.hit_id})
    assert document["times_seen"] == 2
    assert document["first_seen_at"] == _naive_utc(first_seen)
    assert document["last_seen_at"] == _naive_utc(second_seen)


def test_duplicate_enqueue_prevented_by_idempotency_key():
    db = _db()
    queue = WorkItemQueue(db)
    queue.ensure_indexes()

    first = queue.enqueue(
        task_type="scrape.hit",
        lane="scrape",
        consumer_mode="legacy_jsonl",
        subject_type="search_hit",
        subject_id="abc123",
        priority=100,
        available_at=None,
        max_attempts=5,
        idempotency_key="scrape.hit:linkedin:123",
        correlation_id="hit:linkedin:123",
        payload={"job_id": "123"},
    )
    second = queue.enqueue(
        task_type="scrape.hit",
        lane="scrape",
        consumer_mode="legacy_jsonl",
        subject_type="search_hit",
        subject_id="abc123",
        priority=100,
        available_at=None,
        max_attempts=5,
        idempotency_key="scrape.hit:linkedin:123",
        correlation_id="hit:linkedin:123",
        payload={"job_id": "123"},
    )

    assert first.created is True
    assert second.created is False
    assert db["work_items"].count_documents({}) == 1


def test_legacy_bridge_writes_exactly_one_queue_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))

    db = _db()
    store = SearchDiscoveryStore(db)
    queue = WorkItemQueue(db)
    store.ensure_indexes()
    queue.ensure_indexes()

    hit = store.upsert_search_hit(
        source="linkedin",
        external_job_id="123",
        job_url="https://www.linkedin.com/jobs/view/123/",
        title="Senior AI Engineer",
        company="Acme",
        location="Remote",
        search_profile="ai_core",
        search_region="eea",
        source_cron="hourly",
        run_id="run-1",
        correlation_id="hit:linkedin:123",
        langfuse_session_id="hit:linkedin:123",
        scout_metadata={},
        raw_search_payload={"job_id": "123"},
    )
    queue.enqueue(
        task_type="scrape.hit",
        lane="scrape",
        consumer_mode="legacy_jsonl",
        subject_type="search_hit",
        subject_id=hit.hit_id,
        priority=100,
        available_at=None,
        max_attempts=5,
        idempotency_key="scrape.hit:linkedin:123",
        correlation_id="hit:linkedin:123",
        payload={
            "job_id": "123",
            "title": "Senior AI Engineer",
            "company": "Acme",
            "location": "Remote",
            "job_url": "https://www.linkedin.com/jobs/view/123/",
            "search_profile": "ai_core",
            "source_cron": "hourly",
        },
    )

    bridge = LegacyScrapeHandoffBridge(db, retry_delay_seconds=0)
    result = bridge.run_once(max_items=5)

    queue_file = tmp_path / "queue.jsonl"
    entries = [json.loads(line) for line in queue_file.read_text().splitlines() if line.strip()]

    assert result["handed_off"] == 1
    assert len(entries) == 1
    assert entries[0]["job_id"] == "123"

    work_item = db["work_items"].find_one()
    hit_doc = db["scout_search_hits"].find_one({"_id": hit.hit_id})
    assert work_item["status"] == "done"
    assert hit_doc["hit_status"] == "handed_to_legacy_scraper"


def test_failed_bridge_attempts_retry_safely(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))

    db = _db()
    store = SearchDiscoveryStore(db)
    queue = WorkItemQueue(db)
    store.ensure_indexes()
    queue.ensure_indexes()

    hit = store.upsert_search_hit(
        source="linkedin",
        external_job_id="999",
        job_url="https://www.linkedin.com/jobs/view/999/",
        title="AI Architect",
        company="Beta",
        location="Berlin",
        search_profile="ai_core",
        search_region="eea",
        source_cron="hourly",
        run_id="run-1",
        correlation_id="hit:linkedin:999",
        langfuse_session_id="hit:linkedin:999",
        scout_metadata={},
        raw_search_payload={"job_id": "999"},
    )
    queue.enqueue(
        task_type="scrape.hit",
        lane="scrape",
        consumer_mode="legacy_jsonl",
        subject_type="search_hit",
        subject_id=hit.hit_id,
        priority=100,
        available_at=None,
        max_attempts=5,
        idempotency_key="scrape.hit:linkedin:999",
        correlation_id="hit:linkedin:999",
        payload={
            "job_id": "999",
            "title": "AI Architect",
            "company": "Beta",
            "location": "Berlin",
            "job_url": "https://www.linkedin.com/jobs/view/999/",
            "search_profile": "ai_core",
            "source_cron": "hourly",
        },
    )

    from src.pipeline import legacy_scrape_handoff as handoff_module

    original_enqueue = handoff_module.enqueue_jobs

    def fail_once(*args, **kwargs):
        raise RuntimeError("queue write failed")

    monkeypatch.setattr(handoff_module, "enqueue_jobs", fail_once)
    bridge = LegacyScrapeHandoffBridge(db, retry_delay_seconds=0)
    first = bridge.run_once(max_items=5)
    first_item = db["work_items"].find_one()

    assert first["failed"] == 1
    assert first_item["status"] == "failed"

    monkeypatch.setattr(handoff_module, "enqueue_jobs", original_enqueue)
    second = bridge.run_once(max_items=5)
    second_item = db["work_items"].find_one()
    entries = [json.loads(line) for line in (tmp_path / "queue.jsonl").read_text().splitlines() if line.strip()]

    assert second["handed_off"] == 1
    assert second_item["status"] == "done"
    assert len(entries) == 1
