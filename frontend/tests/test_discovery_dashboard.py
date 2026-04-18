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
    repo.get_stats.return_value = {
        "search_runs_last_24h": 2,
        "discoveries_last_24h": 5,
        "pending_scrapes": 1,
        "selector_handoffs_written": 4,
        "failures_deadletters": 1,
    }
    repo.get_hits.return_value = [_sample_hit()]
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
        }
    ]
    repo.get_queue_snapshot.return_value = {
        "native": {"pending": 1, "leased": 0, "done": 4, "failed": 1, "deadletter": 0, "total": 6},
        "legacy": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "all": {"pending": 1, "leased": 0, "done": 4, "failed": 1, "deadletter": 0, "total": 6},
    }
    repo.get_recent_failures.return_value = [
        {
            "title": "Broken job",
            "scrape": {"status": "retry_pending", "last_error": {"message": "fetch failed"}},
        }
    ]
    repo.get_langfuse_panel.return_value = {
        "public_url": "https://langfuse.example.com",
        "latest_search_run_session_id": "searchrun:session",
        "latest_scrape_run_session_id": "scraperun:session",
        "latest_hit_session_id": "hit:linkedin:123",
    }
    repo.get_hit_detail.return_value = _sample_hit()
    return repo


def test_discovery_dashboard_routes_render(client):
    repo = _sample_repo()

    with patch("frontend.intel_dashboard.get_discovery_repo", return_value=repo):
        response = client.get("/dashboard/discovery")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Discovery Debug" in html
        assert "Senior AI Engineer" in html
        assert "Native Scrape" in html
        assert "Selector Handoff" in html
        assert "Open Langfuse" in html

        stats = client.get("/dashboard/discovery/stats")
        assert stats.status_code == 200
        assert "Pending Scrapes" in stats.get_data(as_text=True)

        rows = client.get("/dashboard/discovery/rows")
        assert rows.status_code == 200
        assert "selector_handoff_written" in rows.get_data(as_text=True)

        runs = client.get("/dashboard/discovery/runs")
        assert runs.status_code == 200
        runs_html = runs.get_data(as_text=True)
        assert "Search Runs" in runs_html
        assert "Scrape Runs" in runs_html

        queue = client.get("/dashboard/discovery/queue")
        assert queue.status_code == 200
        assert "Native Queue" in queue.get_data(as_text=True)

        detail = client.get(f"/dashboard/discovery/{repo.get_hit_detail.return_value['_id']}")
        assert detail.status_code == 200
        detail_html = detail.get_data(as_text=True)
        assert "Scrape State" in detail_html
        assert "Level-1 written" in detail_html


def test_discovery_dashboard_empty_and_error_states_render_cleanly(client):
    empty_repo = MagicMock()
    empty_repo.get_stats.return_value = {
        "search_runs_last_24h": 0,
        "discoveries_last_24h": 0,
        "pending_scrapes": 0,
        "selector_handoffs_written": 0,
        "failures_deadletters": 0,
    }
    empty_repo.get_hits.return_value = []
    empty_repo.get_recent_search_runs.return_value = []
    empty_repo.get_recent_scrape_runs.return_value = []
    empty_repo.get_queue_snapshot.return_value = {
        "native": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "legacy": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
        "all": {"pending": 0, "leased": 0, "done": 0, "failed": 0, "deadletter": 0, "total": 0},
    }
    empty_repo.get_recent_failures.return_value = []
    empty_repo.get_langfuse_panel.return_value = {
        "public_url": None,
        "latest_search_run_session_id": None,
        "latest_scrape_run_session_id": None,
        "latest_hit_session_id": None,
    }
    empty_repo.get_hit_detail.return_value = None

    with patch("frontend.intel_dashboard.get_discovery_repo", return_value=empty_repo):
        response = client.get("/dashboard/discovery")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "No discovery hits available" in html
        assert "No search runs recorded yet" in html
        assert "No scrape runs recorded yet" in html

    with patch("frontend.intel_dashboard.get_discovery_repo", side_effect=RuntimeError("db unavailable")):
        response = client.get("/dashboard/discovery")
        assert response.status_code == 200
        assert "Discovery dashboard unavailable: db unavailable" in response.get_data(as_text=True)

        partial = client.get("/dashboard/discovery/stats")
        assert partial.status_code == 200
        assert "Discovery stats unavailable: db unavailable" in partial.get_data(as_text=True)
