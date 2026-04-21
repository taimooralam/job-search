"""Tests for snapshot-first blueprint rendering on the job detail page."""

from __future__ import annotations

from bson import ObjectId

from frontend import app as frontend_app


def _base_job() -> dict:
    return {
        "_id": ObjectId(),
        "title": "Engineering Manager",
        "company": "Legacy Corp",
        "location": "Remote",
        "status": "not processed",
        "jobId": "JOB-123",
        "jobUrl": "https://legacy.example.com/jobs/123",
        "application_url": "https://legacy.example.com/apply",
        "description": "Lead engineering execution for an AI platform team.",
        "company_research": {
            "summary": "Legacy company research summary",
            "signals": [{"type": "growth", "description": "Legacy signal"}],
        },
        "role_research": {
            "summary": "Legacy role research summary",
            "business_impact": ["Legacy business impact"],
            "why_now": "Legacy urgency",
        },
        "pain_points": ["Legacy pain point"],
    }


def test_job_detail_prefers_blueprint_snapshot_when_enabled(client, mock_db, monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    mock_repo, _ = mock_db
    job = _base_job()
    job["pre_enrichment"] = {
        "job_blueprint_version": "job_blueprint.v1",
        "job_blueprint_status": "ready",
        "job_blueprint_snapshot": {
            "classification": {"primary_role_category": "engineering_manager"},
            "application_surface": {
                "status": "resolved",
                "application_url": "https://boards.greenhouse.io/acme/jobs/12345",
                "portal_family": "greenhouse",
                "is_direct_apply": True,
                "friction_signals": ["multi_step_likely"],
            },
            "company_research": {
                "summary": "Snapshot company research summary",
                "signals": [{"type": "growth", "description": "Snapshot signal"}],
                "url": "https://acme.example.com",
            },
            "role_research": {
                "summary": "Snapshot role research summary",
                "business_impact": ["Scale the platform"],
                "why_now": "Executive mandate",
            },
            "cv_guidelines": {
                "title_guidance": {"bullets": ["Mirror the leadership scope"]},
                "identity_guidance": {"bullets": ["Lead with org scale and delivery scope"]},
                "bullet_theme_guidance": {"bullets": ["Show team and delivery outcomes"]},
                "ats_keyword_guidance": {"bullets": ["python", "leadership"]},
                "cover_letter_expectations": {"bullets": ["Tie the story to company context"]},
            },
            "pain_points": ["Snapshot pain point"],
            "strategic_needs": ["Snapshot strategic need"],
            "risks_if_unfilled": ["Snapshot risk"],
            "success_metrics": ["Snapshot success metric"],
            "ats_keywords": ["python", "leadership"],
            "title_guidance": "Mirror the leadership scope",
            "identity_guidance": "Lead with org scale and delivery scope",
            "bullet_guidance": ["Show team and delivery outcomes"],
            "cover_letter_expectations": ["Tie the story to company context"],
            "job_hypotheses": {"should_not": "render"},
        },
    }
    mock_repo.find_one.return_value = job

    response = client.get(f"/job/{job['_id']}")

    assert response.status_code == 200
    data = response.data.decode("utf-8")
    assert "https://boards.greenhouse.io/acme/jobs/12345" in data
    assert 'hx-get="/job/' in data
    assert "/partials/research" in data
    assert "/partials/guidance" in data
    assert "/partials/debug" in data
    assert "Loading research snapshot" in data
    assert "Loading blueprint guidance" in data
    assert "greenhouse" in data.lower()
    assert "Legacy company research summary" not in data
    assert "Snapshot company research summary" not in data
    assert "should_not" not in data


def test_job_detail_falls_back_to_legacy_when_snapshot_missing(client, mock_db, monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    mock_repo, _ = mock_db
    job = _base_job()
    mock_repo.find_one.return_value = job

    response = client.get(f"/job/{job['_id']}")

    assert response.status_code == 200
    data = response.data.decode("utf-8")
    assert "https://legacy.example.com/apply" in data
    assert "Job Blueprint & CV Guidance" not in data
    assert "/partials/guidance" not in data
    assert "Legacy company research summary" not in data

    research_response = client.get(f"/job/{job['_id']}/partials/research")

    assert research_response.status_code == 200
    research_data = research_response.data.decode("utf-8")
    assert "Legacy company research summary" in research_data
    assert "Legacy role research summary" in research_data


def test_given_snapshot_job_when_loading_research_partial_then_snapshot_research_is_rendered(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    mock_repo, _ = mock_db
    job = _base_job()
    job["pre_enrichment"] = {
        "job_blueprint_snapshot": {
            "classification": {"primary_role_category": "engineering_manager"},
            "application_surface": {"status": "resolved"},
            "company_research": {
                "summary": "Snapshot company research summary",
                "signals": [{"type": "growth", "description": "Snapshot signal"}],
                "url": "https://acme.example.com",
            },
            "role_research": {
                "summary": "Snapshot role research summary",
                "business_impact": ["Scale the platform"],
                "why_now": "Executive mandate",
            },
            "research": {
                "application_profile": {
                    "portal_family": "greenhouse",
                    "canonical_application_url": "https://boards.greenhouse.io/acme/jobs/12345",
                    "stale_signal": "likely_stale"
                },
                "stakeholder_summary": {
                    "count": 1,
                    "counts_by_type": {"hiring_manager": 1},
                    "top_candidates": [{"name": "Jordan Smith", "title": "Engineering Manager", "stakeholder_type": "hiring_manager"}]
                }
            },
            "cv_guidelines": {},
        }
    }
    mock_repo.find_one.return_value = job

    response = client.get(f"/job/{job['_id']}/partials/research")

    assert response.status_code == 200
    data = response.data.decode("utf-8")
    assert "Snapshot company research summary" in data
    assert "Snapshot role research summary" in data
    assert "Business Signals (1)" in data
    assert "Application Intelligence" in data
    assert "may be stale" in data
    assert "Jordan Smith" in data


def test_given_snapshot_job_when_loading_guidance_partial_then_blueprint_guidance_is_rendered(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    mock_repo, _ = mock_db
    job = _base_job()
    job["pre_enrichment"] = {
        "job_blueprint_snapshot": {
            "classification": {"primary_role_category": "engineering_manager"},
            "application_surface": {"status": "resolved"},
            "company_research": {},
            "role_research": {},
            "cv_guidelines": {
                "title_guidance": {"bullets": ["Mirror the leadership scope"]},
                "identity_guidance": {"bullets": ["Lead with org scale and delivery scope"]},
                "bullet_theme_guidance": {"bullets": ["Show team and delivery outcomes"]},
                "ats_keyword_guidance": {"bullets": ["python", "leadership"]},
                "cover_letter_expectations": {"bullets": ["Tie the story to company context"]},
            },
        }
    }
    mock_repo.find_one.return_value = job

    response = client.get(f"/job/{job['_id']}/partials/guidance")

    assert response.status_code == 200
    data = response.data.decode("utf-8")
    assert "Mirror the leadership scope" in data
    assert "Tie the story to company context" in data
    assert "python" in data


def test_given_debug_panel_request_when_hypotheses_ref_exists_then_hypotheses_load_only_in_debug_panel(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    mock_repo, _ = mock_db
    hypotheses_id = ObjectId()
    job = _base_job()
    job["pre_enrichment"] = {
        "job_blueprint_refs": {"job_hypotheses_id": str(hypotheses_id)},
        "job_blueprint_snapshot": {
            "classification": {"primary_role_category": "engineering_manager"},
            "application_surface": {"status": "resolved"},
            "company_research": {},
            "role_research": {},
            "cv_guidelines": {},
            "job_hypotheses": {"should_not": "render"},
        },
    }
    mock_repo.find_one.return_value = job

    hypothesis_collection = frontend_app.get_db.return_value.__getitem__.return_value
    hypothesis_collection.find_one.return_value = {
        "_id": hypotheses_id,
        "job_id": "JOB-123",
        "hypotheses": [{"field": "team_topology", "value": "Platform org", "reasoning": "Repeated platform language"}],
    }

    shell_response = client.get(f"/job/{job['_id']}")
    assert shell_response.status_code == 200
    shell_data = shell_response.data.decode("utf-8")
    assert "should_not" not in shell_data
    assert "team_topology" not in shell_data

    debug_response = client.get(f"/job/{job['_id']}/partials/debug")

    assert debug_response.status_code == 200
    debug_data = debug_response.data.decode("utf-8")
    assert "Blueprint Hypotheses Debug" in debug_data
    assert "team_topology" in debug_data
    assert "Platform org" in debug_data
