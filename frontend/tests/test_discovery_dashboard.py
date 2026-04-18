"""Tests for the discovery/debug dashboard routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from bson import ObjectId


def _sample_hit() -> dict:
    hit_id = ObjectId()
    return {
        "_id": hit_id,
        "title": "Senior AI Engineer",
        "company": "Acme",
        "location": "Remote",
        "search_profile": "ai_core",
        "search_region": "de",
        "hit_status": "selector_handoff_written",
        "display_status": "selector_handoff_written",
        "last_seen_at": datetime(2026, 4, 18, 9, 30, tzinfo=timezone.utc),
        "correlation_id": "hit:linkedin:123",
        "langfuse_session_id": "hit:linkedin:123",
        "run_id": "searchrun:2026-04-18T09-00-00Z:abc123",
        "times_seen": 2,
        "raw_search_payload": {"job_id": "123", "title": "Senior AI Engineer"},
        "scrape": {
            "status": "succeeded",
            "score": 82,
            "tier": "A",
            "detected_role": "ai_engineer",
            "attempt_count": 1,
            "selector_handoff_status": "written",
            "level1_upserted_at": datetime(2026, 4, 18, 9, 31, tzinfo=timezone.utc),
            "scored_jsonl_written_at": datetime(2026, 4, 18, 9, 31, tzinfo=timezone.utc),
            "last_error": None,
        },
        "selection": {
            "main": {
                "status": "completed",
                "decision": "selected_for_preenrich",
                "selector_run_id": "selectorrun:main:2026-04-18T09-55-00Z",
                "selected_at": datetime(2026, 4, 18, 9, 35, tzinfo=timezone.utc),
            },
            "pool": {
                "status": "available",
                "pooled_at": datetime(2026, 4, 18, 9, 35, tzinfo=timezone.utc),
                "expires_at": datetime(2026, 4, 20, 9, 35, tzinfo=timezone.utc),
            },
            "profiles": {
                "global_remote": {
                    "decision": "profile_selected",
                    "status": "completed",
                }
            },
        },
        "level2_state": {
            "exists": True,
            "id": str(ObjectId()),
            "lifecycle": "selected",
            "selected_at": datetime(2026, 4, 18, 9, 35, tzinfo=timezone.utc),
            "preenrich_claimed": False,
            "profile_links": {},
        },
        "trace_links": {
            "search_trace_url": "https://langfuse.example.com/search",
            "scrape_trace_url": "https://langfuse.example.com/scrape",
            "selector_trace_url": "https://langfuse.example.com/selector",
            "langfuse_session_id": "hit:linkedin:123",
        },
        "run_links": {
            "search_run": {
                "run_id": "searchrun:2026-04-18T09-00-00Z:abc123",
                "langfuse_trace_url": "https://langfuse.example.com/search",
            },
            "scrape_run": {
                "run_id": "scraperun:2026-04-18T09-10-00Z:def456",
                "langfuse_trace_url": "https://langfuse.example.com/scrape",
            },
            "selector_run": {
                "run_id": "selectorrun:main:2026-04-18T09-55-00Z",
                "langfuse_trace_url": "https://langfuse.example.com/selector",
            },
        },
        "related_work_item": {
            "_id": ObjectId(),
            "status": "done",
            "task_type": "scrape.hit",
            "consumer_mode": "native_scrape",
            "attempt_count": 1,
            "max_attempts": 5,
            "result_ref": {"scored_jsonl_written": True, "level1_upserted": True},
            "payload": {"title": "Senior AI Engineer", "job_id": "123"},
        },
    }


def _sample_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_pipeline_heartbeat.return_value = {
        "cards": [
            {
                "title": "Iteration 1",
                "subtitle": "Search -> hits -> scrape work-items",
                "primary_metric": 5,
                "primary_label": "new hits in 15m",
                "secondary_metric": 4,
                "secondary_label": "scrape work-items in 15m",
                "state": "green",
                "reason": "5 new hits in 15m; last activity 4m ago",
                "last_seen_at": datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc),
            },
            {
                "title": "Iteration 2",
                "subtitle": "Native scrape execution",
                "primary_metric": 2,
                "primary_label": "scrape successes in 15m",
                "secondary_metric": 1,
                "secondary_label": "scrape queue open",
                "state": "green",
                "reason": "2 scrape successes in 15m; last activity 2m ago",
                "last_seen_at": datetime(2026, 4, 18, 9, 10, tzinfo=timezone.utc),
            },
            {
                "title": "Iteration 3",
                "subtitle": "Selector runs -> level-2 handoff",
                "primary_metric": 3,
                "primary_label": "selector runs in 8h",
                "secondary_metric": 1,
                "secondary_label": "selected docs in 8h",
                "state": "green",
                "reason": "3 selector runs in 8h; last activity 1h ago",
                "last_seen_at": datetime(2026, 4, 18, 9, 55, tzinfo=timezone.utc),
                "selected_lifecycle": "selected",
            },
        ],
        "summary": {
            "pending_scrapes": 1,
            "pool_available": 2,
            "selected_ready": 1,
            "failures": 1,
        },
    }
    repo.search_hits_page.return_value = {
        "hits": [_sample_hit()],
        "page": {"limit": 25, "has_more": False, "next_cursor": None, "cursor": None},
        "filters": {
            "q": "",
            "window": "24h",
            "profile": "",
            "region": "",
            "scrape_status": "",
            "main_decision": "",
            "pool_status": "",
            "failures_only": False,
        },
    }
    repo.get_recent_search_runs.return_value = [
        {
            "command_mode": "full",
            "status": "completed",
            "started_at": datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc),
            "region_filter": "de",
            "profile_filter": "ai_core",
            "stats": {
                "raw_found": 6,
                "hits_upserted": 4,
                "work_items_created": 4,
                "legacy_handoffs_created": 0,
            },
            "errors": [],
            "langfuse_trace_url": "https://langfuse.example.com/search",
        }
    ]
    repo.get_recent_scrape_runs.return_value = [
        {
            "worker_id": "worker-1",
            "status": "completed",
            "started_at": datetime(2026, 4, 18, 9, 10, tzinfo=timezone.utc),
            "trigger_mode": "manual",
            "stats": {
                "claimed": 2,
                "scraped_success": 1,
                "retried": 1,
                "deadlettered": 0,
                "level1_upserts": 1,
                "scored_jsonl_writes": 1,
            },
            "langfuse_trace_url": "https://langfuse.example.com/scrape",
        }
    ]
    repo.get_recent_selector_runs.return_value = [
        {
            "run_kind": "main",
            "profile_name": None,
            "status": "completed",
            "scheduled_for": datetime(2026, 4, 18, 9, 55, tzinfo=timezone.utc),
            "trigger_mode": "manual",
            "stats": {
                "candidates_seen": 3,
                "selected_for_preenrich": 1,
                "duplicate_db": 1,
                "discarded_quota": 0,
                "tier_low_level1": 0,
                "inserted_level2": 1,
            },
            "langfuse_trace_url": "https://langfuse.example.com/selector",
        }
    ]
    repo.get_queue_snapshot.return_value = {
        "native": {"pending": 1, "leased": 0, "done": 4, "failed": 1, "deadletter": 0, "total": 6},
        "legacy": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "selector": {"pending": 1, "leased": 0, "done": 1, "failed": 0, "deadletter": 0, "total": 2},
        "all": {"pending": 1, "leased": 0, "done": 4, "failed": 1, "deadletter": 0, "total": 6},
    }
    repo.get_recent_failures.return_value = [
        {
            "kind": "scrape",
            "title": "Broken job",
            "scrape": {"status": "retry_pending", "last_error": {"message": "fetch failed"}},
        }
    ]
    repo.get_langfuse_panel.return_value = {
        "public_url": "https://langfuse.example.com",
        "latest_search_run_session_id": "searchrun:session",
        "latest_scrape_run_session_id": "scraperun:session",
        "latest_selector_run_session_id": "selectorrun:session",
        "latest_hit_session_id": "hit:linkedin:123",
        "latest_search_trace_url": "https://langfuse.example.com/search",
        "latest_scrape_trace_url": "https://langfuse.example.com/scrape",
        "latest_selector_trace_url": "https://langfuse.example.com/selector",
    }
    repo.get_hit_detail.return_value = _sample_hit()
    repo.get_hit_peek.return_value = _sample_hit()
    return repo


def test_discovery_dashboard_routes_render(client):
    repo = _sample_repo()

    with patch("frontend.intel_dashboard.get_discovery_repo", return_value=repo):
        response = client.get("/dashboard/discovery")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Discovery Debug" in html
        assert "Iteration 1" in html
        assert "Senior AI Engineer" in html
        assert "Search Discovery State" in html
        assert "Quick Peek" in html
        assert "Open Langfuse" in html

        stats = client.get("/dashboard/discovery/stats")
        assert stats.status_code == 200
        stats_html = stats.get_data(as_text=True)
        assert "Iteration 2" in stats_html
        assert "Selected Ready" in stats_html

        rows = client.get("/dashboard/discovery/rows")
        assert rows.status_code == 200
        rows_html = rows.get_data(as_text=True)
        assert "Load Older" not in rows_html
        assert "Main: selected_for_preenrich" in rows_html

        runs = client.get("/dashboard/discovery/runs")
        assert runs.status_code == 200
        runs_html = runs.get_data(as_text=True)
        assert "Search Runs" in runs_html
        assert "Scrape Runs" in runs_html
        assert "Selector Runs" in runs_html
        assert "Open trace" in runs_html

        queue = client.get("/dashboard/discovery/queue")
        assert queue.status_code == 200
        queue_html = queue.get_data(as_text=True)
        assert "Selector Queue" in queue_html
        assert "Open latest selector trace" in queue_html

        peek = client.get(f"/dashboard/discovery/peek/{repo.get_hit_peek.return_value['_id']}")
        assert peek.status_code == 200
        peek_html = peek.get_data(as_text=True)
        assert "Traceability" in peek_html
        assert "Iteration 3" in peek_html

        detail = client.get(f"/dashboard/discovery/{repo.get_hit_detail.return_value['_id']}")
        assert detail.status_code == 200
        detail_html = detail.get_data(as_text=True)
        assert "Selector State" in detail_html
        assert "Level-2 / Preenrich" in detail_html
        assert "Open selector trace" in detail_html


def test_discovery_dashboard_empty_and_error_states_render_cleanly(client):
    empty_repo = MagicMock()
    empty_repo.get_pipeline_heartbeat.return_value = {
        "cards": [],
        "summary": {
            "pending_scrapes": 0,
            "pool_available": 0,
            "selected_ready": 0,
            "failures": 0,
        },
    }
    empty_repo.search_hits_page.return_value = {
        "hits": [],
        "page": {"limit": 25, "has_more": False, "next_cursor": None, "cursor": None},
        "filters": {"q": "", "window": "24h", "profile": "", "region": "", "scrape_status": "", "main_decision": "", "pool_status": "", "failures_only": False},
    }
    empty_repo.get_recent_search_runs.return_value = []
    empty_repo.get_recent_scrape_runs.return_value = []
    empty_repo.get_recent_selector_runs.return_value = []
    empty_repo.get_queue_snapshot.return_value = {
        "native": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "legacy": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "selector": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "all": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
    }
    empty_repo.get_recent_failures.return_value = []
    empty_repo.get_langfuse_panel.return_value = {
        "public_url": None,
        "latest_search_run_session_id": None,
        "latest_scrape_run_session_id": None,
        "latest_selector_run_session_id": None,
        "latest_hit_session_id": None,
    }
    empty_repo.get_hit_detail.return_value = None
    empty_repo.get_hit_peek.return_value = None

    with patch("frontend.intel_dashboard.get_discovery_repo", return_value=empty_repo):
        response = client.get("/dashboard/discovery")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "No discovery hits match the current query" in html
        assert "No search runs recorded yet" in html
        assert "No scrape runs recorded yet" in html
        assert "No selector runs recorded yet" in html

    with patch("frontend.intel_dashboard.get_discovery_repo", side_effect=RuntimeError("db unavailable")):
        response = client.get("/dashboard/discovery")
        assert response.status_code == 200
        assert "Discovery dashboard unavailable: db unavailable" in response.get_data(as_text=True)

        partial = client.get("/dashboard/discovery/stats")
        assert partial.status_code == 200
        assert "Discovery stats unavailable: db unavailable" in partial.get_data(as_text=True)
