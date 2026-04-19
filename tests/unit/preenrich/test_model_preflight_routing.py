"""Tests for iteration-4.1 model routing and preflight validation."""

from __future__ import annotations

from src.preenrich.types import get_stage_step_config
from scripts.preenrich_model_preflight import validate_stage_routing


def test_validate_stage_routing_covers_iteration41_stages():
    assert validate_stage_routing("jd_facts") == []
    assert validate_stage_routing("classification") == []
    assert validate_stage_routing("research_enrichment") == []
    assert validate_stage_routing("application_surface") == []
    assert validate_stage_routing("job_inference") == []
    assert validate_stage_routing("job_hypotheses") == []
    assert validate_stage_routing("cv_guidelines") == []
    assert validate_stage_routing("blueprint_assembly") == []


def test_stage_env_override_is_respected(monkeypatch):
    monkeypatch.setenv("PREENRICH_MODEL_JOB_INFERENCE", "gpt-5.4-mini")
    cfg = get_stage_step_config("job_inference")
    assert cfg.primary_model == "gpt-5.4-mini"


def test_jd_facts_v2_preflight_requires_real_provider(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PROVIDER_JD_FACTS", "none")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", "gpt-5.4")
    errors = validate_stage_routing("jd_facts")
    assert "jd_facts: V2 enabled requires a real provider" in errors


def test_jd_facts_v2_preflight_requires_escalation_model_when_enabled(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PROVIDER_JD_FACTS", "codex")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", "true")
    monkeypatch.delenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", raising=False)
    errors = validate_stage_routing("jd_facts")
    assert "jd_facts: escalation enabled requires PREENRICH_JD_FACTS_ESCALATION_MODEL" in errors


def test_blueprint_assembly_uses_no_provider_default():
    cfg = get_stage_step_config("blueprint_assembly")
    assert cfg.provider == "none"
    assert cfg.primary_model is None
