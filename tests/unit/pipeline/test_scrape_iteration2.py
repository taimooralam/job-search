"""Tests for the iteration-2 native scrape worker and selector compatibility boundary."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import mongomock

from src.pipeline.discovery import SearchDiscoveryStore
from src.pipeline.queue import WorkItemQueue
from src.pipeline.scrape_common import ScrapeSuccessResult
from src.pipeline.scrape_worker import NativeScrapeWorker, ScrapeFeatureFlags
from src.services.linkedin_scraper import RateLimitError


def _db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _flags() -> ScrapeFeatureFlags:
    return ScrapeFeatureFlags(
        enable_native_worker=True,
        use_mongo_work_items=True,
        enable_legacy_jsonl_consumer=False,
        write_scored_jsonl=True,
        write_level1=True,
        selector_compat_mode=True,
        persist_selector_payload=True,
    )


def _scored_payload(job_id: str = "123") -> dict:
    return {
        "job_id": job_id,
        "title": "Senior AI Engineer",
        "company": "Acme",
        "location": "Remote",
        "job_url": f"https://linkedin.com/jobs/view/{job_id}",
        "score": 82,
        "tier": "A",
        "detected_role": "ai_engineer",
        "seniority_level": "senior",
        "is_target_role": True,
        "description": "Build agent systems",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "job_function": "Engineering",
        "industries": ["Software"],
        "work_mode": "Remote",
        "breakdown": {"title_match": 20},
        "search_profile": "ai_core",
        "source_cron": "hourly",
        "scored_at": datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
    }


def _create_hit_and_item(db, *, job_id: str, title: str, company: str = "Acme", consumer_mode: str = "native_scrape", max_attempts: int = 5):
    store = SearchDiscoveryStore(db)
    queue = WorkItemQueue(db)
    store.ensure_indexes()
    queue.ensure_indexes()

    hit = store.upsert_search_hit(
        source="linkedin",
        external_job_id=job_id,
        job_url=f"https://linkedin.com/jobs/view/{job_id}",
        title=title,
        company=company,
        location="Remote",
        search_profile="ai_core",
        search_region="de",
        source_cron="hourly",
        run_id="searchrun:test",
        correlation_id=f"hit:linkedin:{job_id}",
        langfuse_session_id="searchrun:test",
        scout_metadata={},
        raw_search_payload={"job_id": job_id, "title": title},
    )
    enqueued = queue.enqueue(
        task_type="scrape.hit",
        lane="scrape",
        consumer_mode=consumer_mode,
        subject_type="search_hit",
        subject_id=hit.hit_id,
        priority=100,
        available_at=None,
        max_attempts=max_attempts,
        idempotency_key=f"scrape.hit:linkedin:{job_id}:{consumer_mode}",
        correlation_id=f"hit:linkedin:{job_id}",
        payload={
            "job_id": job_id,
            "title": title,
            "company": company,
            "location": "Remote",
            "job_url": f"https://linkedin.com/jobs/view/{job_id}",
            "search_profile": "ai_core",
            "source_cron": "hourly",
        },
    )
    store.mark_hit_queued(
        hit.hit_id,
        consumer_mode=consumer_mode,
        work_item_id=enqueued.document["_id"],
    )
    return hit.hit_id, enqueued.document["_id"]


def test_claim_and_lease_scrape_hit_work_item():
    db = _db()
    _create_hit_and_item(db, job_id="123", title="Senior AI Engineer")
    queue = WorkItemQueue(db)

    claimed = queue.claim_next(
        task_type="scrape.hit",
        lane="scrape",
        consumer_mode="native_scrape",
        worker_name="worker-1",
    )

    assert claimed is not None
    assert claimed["status"] == "leased"
    assert claimed["lease_owner"] == "worker-1"
    assert claimed["attempt_count"] == 1


def test_blacklist_skip_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    hit_id, item_id = _create_hit_and_item(db, job_id="200", title="Senior AI Engineer", company="Joppy")
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    result = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual")

    hit = db["scout_search_hits"].find_one({"_id": hit_id})
    item = db["work_items"].find_one({"_id": item_id})
    assert result["skipped_blacklist"] == 1
    assert hit["scrape"]["status"] == "skipped_blacklist"
    assert item["status"] == "done"
    assert not (tmp_path / "scored.jsonl").exists()


def test_title_filter_skip_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    hit_id, item_id = _create_hit_and_item(db, job_id="201", title="Office Manager")
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    result = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual")

    hit = db["scout_search_hits"].find_one({"_id": hit_id})
    item = db["work_items"].find_one({"_id": item_id})
    assert result["skipped_title_filter"] == 1
    assert hit["scrape"]["status"] == "skipped_title_filter"
    assert item["status"] == "done"


def test_successful_scrape_writes_mongo_scored_jsonl_and_level1(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    hit_id, item_id = _create_hit_and_item(db, job_id="300", title="Senior AI Engineer")
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    monkeypatch.setattr(
        "src.pipeline.scrape_worker.evaluate_scrape_candidate",
        lambda payload, pool, use_proxy: ScrapeSuccessResult(
            scored_job=_scored_payload(payload["job_id"]),
            http_status=200,
            used_proxy=False,
        ),
    )

    result = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual")

    hit = db["scout_search_hits"].find_one({"_id": hit_id})
    item = db["work_items"].find_one({"_id": item_id})
    level1 = list(db["level-1"].find())
    scored_entries = [json.loads(line) for line in (tmp_path / "scored.jsonl").read_text().splitlines() if line.strip()]

    assert result["scraped_success"] == 1
    assert result["level1_upserts"] == 1
    assert result["scored_jsonl_writes"] == 1
    assert hit["scrape"]["status"] == "succeeded"
    assert hit["scrape"]["selector_handoff_status"] == "written"
    assert hit["scrape"]["selector_payload"]["job_id"] == "300"
    assert hit["scrape"]["selector_payload"]["description"] == "Build agent systems"
    assert hit["scrape"]["score"] == 82
    assert hit["scrape"]["detected_role"] == "ai_engineer"
    assert item["status"] == "done"
    assert item["result_ref"]["scored_jsonl_written"] is True
    assert item["result_ref"]["level1_upserted"] is True
    assert len(level1) == 1
    assert level1[0]["status"] == "scored"
    assert len(scored_entries) == 1
    assert scored_entries[0]["job_id"] == "300"


def test_retry_classification_for_transient_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    hit_id, item_id = _create_hit_and_item(db, job_id="400", title="Senior AI Engineer")
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    def _raise(*args, **kwargs):
        raise RateLimitError("limited")

    monkeypatch.setattr("src.pipeline.scrape_worker.evaluate_scrape_candidate", _raise)

    result = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual")

    hit = db["scout_search_hits"].find_one({"_id": hit_id})
    item = db["work_items"].find_one({"_id": item_id})
    assert result["retried"] == 1
    assert hit["scrape"]["status"] == "retry_pending"
    assert item["status"] == "failed"


def test_deadletter_after_retry_exhaustion(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    hit_id, item_id = _create_hit_and_item(db, job_id="401", title="Senior AI Engineer", max_attempts=1)
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    def _raise(*args, **kwargs):
        raise RateLimitError("limited")

    monkeypatch.setattr("src.pipeline.scrape_worker.evaluate_scrape_candidate", _raise)

    result = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual")

    hit = db["scout_search_hits"].find_one({"_id": hit_id})
    item = db["work_items"].find_one({"_id": item_id})
    assert result["deadlettered"] == 1
    assert hit["scrape"]["status"] == "deadletter"
    assert item["status"] == "deadletter"


def test_idempotent_retry_does_not_duplicate_compatibility_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    hit_id, item_id = _create_hit_and_item(db, job_id="500", title="Senior AI Engineer")
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    monkeypatch.setattr(
        "src.pipeline.scrape_worker.evaluate_scrape_candidate",
        lambda payload, pool, use_proxy: ScrapeSuccessResult(
            scored_job=_scored_payload(payload["job_id"]),
            http_status=200,
            used_proxy=False,
        ),
    )

    original_append = __import__("src.pipeline.scrape_worker", fromlist=["append_scored_unique"]).append_scored_unique
    attempts = {"count": 0}

    def _append_once_then_fail(jobs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("disk full")
        return original_append(jobs)

    monkeypatch.setattr("src.pipeline.scrape_worker.append_scored_unique", _append_once_then_fail)

    base_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    first = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=base_time)
    assert first["retried"] == 1

    monkeypatch.setattr("src.pipeline.scrape_worker.append_scored_unique", original_append)
    second = worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=base_time + timedelta(minutes=2))

    hit = db["scout_search_hits"].find_one({"_id": hit_id})
    item = db["work_items"].find_one({"_id": item_id})
    level1 = list(db["level-1"].find())
    scored_entries = [json.loads(line) for line in (tmp_path / "scored.jsonl").read_text().splitlines() if line.strip()]

    assert second["scraped_success"] == 1
    assert hit["scrape"]["selector_handoff_status"] == "written"
    assert item["status"] == "done"
    assert len(level1) == 1
    assert len(scored_entries) == 1


def test_native_legacy_split_prevents_double_processing(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    db = _db()
    native_hit_id, native_item_id = _create_hit_and_item(db, job_id="600", title="Senior AI Engineer", consumer_mode="native_scrape")
    legacy_hit_id, legacy_item_id = _create_hit_and_item(db, job_id="601", title="Senior AI Engineer", consumer_mode="legacy_jsonl")
    worker = NativeScrapeWorker(db, flags=_flags(), worker_id="worker-1", use_proxy=False)

    monkeypatch.setattr(
        "src.pipeline.scrape_worker.evaluate_scrape_candidate",
        lambda payload, pool, use_proxy: ScrapeSuccessResult(
            scored_job=_scored_payload(payload["job_id"]),
            http_status=200,
            used_proxy=False,
        ),
    )

    result = worker.run_once(max_items=5, lease_seconds=300, trigger_mode="manual")

    native_item = db["work_items"].find_one({"_id": native_item_id})
    legacy_item = db["work_items"].find_one({"_id": legacy_item_id})
    legacy_hit = db["scout_search_hits"].find_one({"_id": legacy_hit_id})

    assert result["scraped_success"] == 1
    assert native_item["status"] == "done"
    assert legacy_item["status"] == "pending"
    assert legacy_hit["scrape"]["status"] == "pending"
