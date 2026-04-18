"""Tests for the iteration-3 Mongo-native selector family."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from src.common.dedupe import generate_dedupe_key
from src.pipeline.discovery import SearchDiscoveryStore
from src.pipeline.queue import WorkItemQueue
from src.pipeline.selector_common import compute_main_selector_plan, compute_profile_selector_plan, load_selector_profiles
from src.pipeline.selector_scheduler import SelectorFeatureFlags, SelectorScheduler
from src.pipeline.selector_store import SelectorStore
from src.pipeline.selector_worker import NativeSelectorWorker
from src.preenrich.lease import claim_one


def _db():
    return mongomock.MongoClient()["jobs"]


def _flags(*, shadow_main: bool = False, shadow_profiles: bool = False) -> SelectorFeatureFlags:
    return SelectorFeatureFlags(
        enable_native_main=not shadow_main,
        enable_native_profiles=not shadow_profiles,
        use_mongo_input=True,
        enable_legacy_main_jsonl=False,
        enable_legacy_profile_pool=False,
        shadow_compare_main=shadow_main,
        shadow_compare_profiles=shadow_profiles,
        preenrich_handoff_mode="selected_lifecycle",
        disable_runner_post=True,
        write_scored_pool_compat=False,
    )


def _payload(
    job_id: str,
    *,
    title: str,
    company: str,
    location: str,
    score: int,
    tier: str,
    description: str = "Build agent systems in English",
    detected_role: str = "ai_engineer",
) -> dict:
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "job_url": f"https://linkedin.com/jobs/view/{job_id}",
        "score": score,
        "tier": tier,
        "detected_role": detected_role,
        "seniority_level": "senior",
        "employment_type": "Full-time",
        "job_function": "Engineering",
        "industries": ["Software"],
        "work_mode": "Remote",
        "search_profile": "ai_core",
        "search_region": "de",
        "source_cron": "hourly",
        "breakdown": {"title_match": 20},
        "scored_at": datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
        "description": description,
        "seniority": "Senior",
    }


def _insert_hit(db, payload: dict, *, completed_at: datetime | None = None):
    store = SearchDiscoveryStore(db)
    store.ensure_indexes()
    completed_at = completed_at or datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    result = store.upsert_search_hit(
        source="linkedin",
        external_job_id=payload["job_id"],
        job_url=payload["job_url"],
        title=payload["title"],
        company=payload["company"],
        location=payload["location"],
        search_profile=payload["search_profile"],
        search_region=payload["search_region"],
        source_cron=payload["source_cron"],
        run_id="searchrun:test",
        correlation_id=f"hit:linkedin:{payload['job_id']}",
        langfuse_session_id=f"hit:linkedin:{payload['job_id']}",
        scout_metadata={},
        raw_search_payload={"job_id": payload["job_id"], "title": payload["title"]},
        now=completed_at - timedelta(minutes=5),
    )
    store.mark_scrape_succeeded(
        result.hit_id,
        run_id="scraperun:test",
        attempt_count=1,
        http_status=200,
        used_proxy=False,
        scored_job=payload,
        persist_selector_payload=True,
        now=completed_at,
    )
    return result.hit_id


def _schedule_main(db, when: datetime):
    scheduler = SelectorScheduler(db)
    return scheduler.schedule_main_run(scheduled_for=when, trigger_mode="manual")


def _schedule_profile(db, when: datetime, profile_name: str):
    scheduler = SelectorScheduler(db)
    return scheduler.schedule_profile_run(profile_name=profile_name, scheduled_for=when, trigger_mode="manual")


def test_main_selector_candidate_query_uses_selector_payload_only():
    db = _db()
    hit_id = _insert_hit(db, _payload("100", title="Senior AI Engineer", company="Acme", location="Berlin", score=85, tier="A"))
    missing_payload = _insert_hit(db, _payload("101", title="Principal AI Engineer", company="Beta", location="Berlin", score=75, tier="B"))
    db["scout_search_hits"].update_one({"_id": missing_payload}, {"$unset": {"scrape.selector_payload": ""}})

    store = SelectorStore(db)
    store.ensure_indexes()
    candidates = store.load_main_candidates(cutoff_at=datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc))

    assert [candidate["job_id"] for candidate in candidates] == ["100"]
    assert candidates[0]["_hit_id"] == hit_id


def test_main_selector_filter_order_and_decisions(monkeypatch):
    db = _db()
    monkeypatch.setenv("SCOUT_SELECTOR_MAIN_QUOTA", "1")
    _insert_hit(db, _payload("200", title="Senior AI Engineer", company="Joppy", location="Berlin", score=85, tier="A"))
    _insert_hit(db, _payload("201", title="高级人工智能工程师", company="Acme", location="Berlin", score=50, tier="A", description="这是一个中文职位描述，用于验证非英语过滤。"))
    _insert_hit(db, _payload("202", title="Senior AI Engineer", company="Gamma", location="Berlin", score=0, tier="D"))
    kept_id = _insert_hit(db, _payload("203", title="Senior AI Engineer", company="Delta", location="Singapore", score=55, tier="A"))
    dropped_id = _insert_hit(db, _payload("204", title="Senior AI Engineer", company="Delta", location="Berlin", score=75, tier="A"))

    _schedule_main(db, datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc))
    worker = NativeSelectorWorker(db, flags=_flags(), worker_id="worker-main")
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 31, tzinfo=timezone.utc))

    hits = {doc["external_job_id"]: doc for doc in db["scout_search_hits"].find()}
    assert hits["200"]["selection"]["main"]["decision"] == "filtered_blacklist"
    assert hits["201"]["selection"]["main"]["decision"] == "filtered_non_english"
    assert hits["202"]["selection"]["main"]["decision"] == "filtered_score"
    assert hits["203"]["selection"]["main"]["decision"] == "selected_for_preenrich"
    assert hits["204"]["selection"]["main"]["decision"] == "duplicate_cross_location"
    assert hits["204"]["selection"]["main"]["reason"] == "kept:203"
    assert hits["203"]["selection"]["pool"]["status"] == "available"
    assert hits["200"]["selection"]["pool"]["status"] == "not_applicable"
    assert kept_id != dropped_id


def test_main_selector_dedupe_parity_and_tier_split(monkeypatch):
    db = _db()
    monkeypatch.setenv("SCOUT_SELECTOR_MAIN_QUOTA", "2")
    existing_key = generate_dedupe_key("linkedin_scout", source_id="300")
    db["level-2"].insert_one({"dedupeKey": existing_key, "company": "Acme", "title": "Senior AI Engineer"})

    _insert_hit(db, _payload("300", title="Senior AI Engineer", company="Acme", location="Berlin", score=80, tier="A"))
    _insert_hit(db, _payload("301", title="AI Platform Engineer", company="NewCo", location="Berlin", score=40, tier="D"))
    _insert_hit(db, _payload("302", title="AI Staff Engineer", company="Fresh", location="Berlin", score=90, tier="A"))

    _schedule_main(db, datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc))
    worker = NativeSelectorWorker(db, flags=_flags(), worker_id="worker-main")
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 31, tzinfo=timezone.utc))

    hits = {doc["external_job_id"]: doc for doc in db["scout_search_hits"].find()}
    assert hits["300"]["selection"]["main"]["decision"] == "duplicate_db"
    assert hits["301"]["selection"]["main"]["decision"] == "inserted_level1"
    assert hits["302"]["selection"]["main"]["decision"] == "selected_for_preenrich"
    assert db["level-1"].count_documents({}) == 1
    assert db["level-2"].count_documents({"dedupeKey": generate_dedupe_key("linkedin_scout", source_id="302")}) == 1


def test_top_n_lifecycle_selected_handoff_and_preenrich_claim(monkeypatch):
    db = _db()
    monkeypatch.setenv("SCOUT_SELECTOR_MAIN_QUOTA", "1")
    _insert_hit(db, _payload("400", title="AI Architect", company="Acme", location="Berlin", score=95, tier="A"))
    _insert_hit(db, _payload("401", title="AI Staff Engineer", company="Beta", location="Berlin", score=80, tier="A"))

    _schedule_main(db, datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc))
    worker = NativeSelectorWorker(db, flags=_flags(), worker_id="worker-main")
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 31, tzinfo=timezone.utc))

    selected_doc = db["level-2"].find_one({"dedupeKey": generate_dedupe_key("linkedin_scout", source_id="400")})
    inserted_only_doc = db["level-2"].find_one({"dedupeKey": generate_dedupe_key("linkedin_scout", source_id="401")})

    assert selected_doc["lifecycle"] == "selected"
    assert "selected_at" in selected_doc
    assert inserted_only_doc.get("lifecycle") is None

    claimed = claim_one(db, "preenrich-worker")
    assert claimed is not None
    assert claimed["dedupeKey"] == selected_doc["dedupeKey"]
    assert claimed["lifecycle"] == "preenriching"


def test_profile_selector_location_filter_rank_and_dedupe(monkeypatch):
    db = _db()
    hit_500 = _insert_hit(db, _payload("500", title="Staff AI Architect", company="Acme", location="Remote, Germany", score=80, tier="A"))
    hit_501 = _insert_hit(db, _payload("501", title="AI Engineer", company="Beta", location="Berlin", score=70, tier="B"))
    hit_502 = _insert_hit(db, _payload("502", title="AI Engineer", company="Gamma", location="Tokyo", score=95, tier="A"))
    db["scout_search_hits"].update_many(
        {"_id": {"$in": [hit_500, hit_501, hit_502]}},
        {
            "$set": {
                "selection.main.status": "completed",
                "selection.main.decision": "none",
                "selection.pool.status": "available",
                "selection.pool.pooled_at": datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc),
                "selection.pool.expires_at": datetime(2026, 4, 20, 13, 0, tzinfo=timezone.utc),
            }
        },
    )

    db["level-2"].insert_one(
        {
            "dedupeKey": generate_dedupe_key("linkedin_scout", source_id="501"),
            "company": "Beta",
            "title": "AI Engineer",
        }
    )

    _schedule_profile(db, datetime(2026, 4, 18, 13, 30, tzinfo=timezone.utc), "eea_remote")
    worker = NativeSelectorWorker(db, flags=_flags(), worker_id="worker-profile")
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 31, tzinfo=timezone.utc))

    hits = {doc["external_job_id"]: doc for doc in db["scout_search_hits"].find()}
    profile_state = hits["500"]["selection"]["profiles"]["eea_remote"]
    assert profile_state["decision"] == "profile_selected"
    assert hits["501"]["selection"]["profiles"]["eea_remote"]["decision"] == "duplicate_db"
    assert hits["502"]["selection"]["profiles"]["eea_remote"]["decision"] == "filtered_location"


def test_profile_rank_score_parity_with_legacy_profile_fixture():
    db = _db()
    profile = load_selector_profiles()["global_remote"]
    candidates = [
        _payload("600", title="Staff AI Architect", company="Acme", location="Remote, Germany", score=80, tier="A"),
        _payload("601", title="AI Engineer", company="Beta", location="Remote", score=78, tier="A"),
    ]
    for candidate in candidates:
        candidate["pooled_at"] = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)

    plan = compute_profile_selector_plan(candidates, db=db, profile=profile, now=datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc))
    assert [candidate["job_id"] for candidate in plan.selected] == ["600", "601"][: profile["quota"]]
    assert plan.selected[0]["_rank_score"] > plan.selected[-1]["_rank_score"]


def test_run_creation_idempotency_and_selector_queue_claim():
    db = _db()
    scheduler = SelectorScheduler(db)
    when = datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc)
    first = scheduler.schedule_main_run(scheduled_for=when, trigger_mode="manual")
    second = scheduler.schedule_main_run(scheduled_for=when, trigger_mode="manual")

    assert first["run_created"] is True
    assert second["run_created"] is False
    assert db["selector_runs"].count_documents({}) == 1
    assert db["work_items"].count_documents({"task_type": "select.run.main"}) == 1

    queue = WorkItemQueue(db)
    claimed = queue.claim_next(
        lane="selector",
        consumer_mode="native_selector",
        worker_name="selector-worker",
        now=datetime(2026, 4, 18, 13, 1, tzinfo=timezone.utc),
    )
    assert claimed is not None
    assert claimed["task_type"] == "select.run.main"
    assert claimed["status"] == "leased"


def test_idempotent_rerun_same_window_does_not_duplicate_outputs(monkeypatch):
    db = _db()
    monkeypatch.setenv("SCOUT_SELECTOR_MAIN_QUOTA", "1")
    _insert_hit(db, _payload("700", title="AI Architect", company="Acme", location="Berlin", score=95, tier="A"))

    when = datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc)
    _schedule_main(db, when)
    worker = NativeSelectorWorker(db, flags=_flags(), worker_id="worker-main")
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 31, tzinfo=timezone.utc))

    _schedule_main(db, when)
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 32, tzinfo=timezone.utc))

    assert db["selector_runs"].count_documents({}) == 1
    assert db["level-2"].count_documents({"dedupeKey": generate_dedupe_key("linkedin_scout", source_id="700")}) == 1


def test_shadow_compare_main_and_profile_write_diffs_without_outputs(monkeypatch):
    db = _db()
    monkeypatch.setenv("SCOUT_SELECTOR_MAIN_QUOTA", "1")
    hit_id = _insert_hit(db, _payload("800", title="AI Architect", company="Acme", location="Remote, Germany", score=95, tier="A"))

    scheduler = SelectorScheduler(db)
    scheduler.schedule_main_run(scheduled_for=datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc), trigger_mode="shadow_compare")
    worker = NativeSelectorWorker(db, flags=_flags(shadow_main=True), worker_id="shadow-worker")
    worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 1, tzinfo=timezone.utc))

    run = db["selector_runs"].find_one({"run_kind": "main"})
    assert run["status"] == "completed"
    assert run["diff"]["selected_ids_match"] is True
    assert db["level-2"].count_documents({}) == 0

    db["scout_search_hits"].update_one(
        {"_id": hit_id},
        {
            "$set": {
                "selection.pool.status": "available",
                "selection.pool.pooled_at": datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc),
                "selection.pool.expires_at": datetime(2026, 4, 20, 13, 0, tzinfo=timezone.utc),
            }
        },
    )
    scheduler.schedule_profile_run(
        profile_name="global_remote",
        scheduled_for=datetime(2026, 4, 18, 13, 30, tzinfo=timezone.utc),
        trigger_mode="shadow_compare",
    )
    profile_worker = NativeSelectorWorker(db, flags=_flags(shadow_profiles=True), worker_id="shadow-profile")
    profile_worker.run_once(max_items=1, lease_seconds=300, trigger_mode="manual", now=datetime(2026, 4, 18, 13, 31, tzinfo=timezone.utc))

    profile_run = db["selector_runs"].find_one({"run_kind": "profile"})
    assert profile_run["status"] == "completed"
    assert profile_run["diff"]["selected_ids_match"] is True
    assert db["level-2"].count_documents({}) == 0


def test_flag_validation_blocks_double_processing():
    flags = SelectorFeatureFlags(
        enable_native_main=True,
        enable_native_profiles=False,
        use_mongo_input=True,
        enable_legacy_main_jsonl=True,
        enable_legacy_profile_pool=True,
        shadow_compare_main=False,
        shadow_compare_profiles=False,
        preenrich_handoff_mode="selected_lifecycle",
        disable_runner_post=True,
        write_scored_pool_compat=False,
    )
    with pytest.raises(RuntimeError, match="cannot both own"):
        flags.validate()
