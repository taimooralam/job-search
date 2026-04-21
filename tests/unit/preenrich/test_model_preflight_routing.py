"""Tests for iteration-4.1 model routing and preflight validation."""

from __future__ import annotations

from src.preenrich.types import get_stage_step_config
from scripts.preenrich_model_preflight import validate_stage_routing


def test_validate_stage_routing_covers_iteration41_stages():
    assert validate_stage_routing("jd_facts") == []
    assert validate_stage_routing("classification") == []
    assert validate_stage_routing("research_enrichment") == []
    assert validate_stage_routing("application_surface") == []
    assert validate_stage_routing("stakeholder_surface") == []
    assert validate_stage_routing("job_inference") == []
    assert validate_stage_routing("job_hypotheses") == []
    assert validate_stage_routing("cv_guidelines") == []
    assert validate_stage_routing("blueprint_assembly") == []


def test_stage_env_override_is_respected(monkeypatch):
    monkeypatch.setenv("PREENRICH_MODEL_JOB_INFERENCE", "gpt-5.4-mini")
    cfg = get_stage_step_config("job_inference")
    assert cfg.primary_model == "gpt-5.4-mini"


def test_jd_facts_default_model_is_pinned_to_gpt52():
    cfg = get_stage_step_config("jd_facts")
    assert cfg.primary_model == "gpt-5.2"


def test_application_surface_default_model_is_pinned_to_gpt52():
    cfg = get_stage_step_config("application_surface")
    assert cfg.primary_model == "gpt-5.2"


def test_stakeholder_surface_default_model_is_pinned_to_gpt52():
    cfg = get_stage_step_config("stakeholder_surface")
    assert cfg.primary_model == "gpt-5.2"


def test_classification_v2_preflight_requires_real_provider(monkeypatch):
    monkeypatch.setenv("PREENRICH_PROVIDER_CLASSIFICATION", "none")
    errors = validate_stage_routing("classification")
    assert "classification: active stage requires a real provider" in errors


def test_classification_shadow_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("PREENRICH_PROVIDER_CLASSIFICATION", "codex")
    monkeypatch.setenv("PREENRICH_CLASSIFICATION_SHADOW_MODE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_CLASSIFICATION_ESCALATION_MODEL", "gpt-5.4")
    errors = validate_stage_routing("classification")
    assert "classification: shadow mode is no longer supported" in errors


def test_jd_facts_v2_preflight_requires_real_provider(monkeypatch):
    monkeypatch.setenv("PREENRICH_PROVIDER_JD_FACTS", "none")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", "gpt-5.4")
    errors = validate_stage_routing("jd_facts")
    assert "jd_facts: active stage requires a real provider" in errors


def test_jd_facts_v2_preflight_requires_escalation_model_when_enabled(monkeypatch):
    monkeypatch.setenv("PREENRICH_PROVIDER_JD_FACTS", "codex")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", "true")
    monkeypatch.delenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", raising=False)
    monkeypatch.delenv("PREENRICH_JD_FACTS_ESCALATION_MODELS", raising=False)
    errors = validate_stage_routing("jd_facts")
    assert "jd_facts: escalation enabled requires PREENRICH_JD_FACTS_ESCALATION_MODEL or PREENRICH_JD_FACTS_ESCALATION_MODELS" in errors


def test_jd_facts_v2_preflight_accepts_escalation_model_list(monkeypatch):
    monkeypatch.setenv("PREENRICH_PROVIDER_JD_FACTS", "codex")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", "true")
    monkeypatch.delenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", raising=False)
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATION_MODELS", "gpt-5.3,gpt-5.4")
    assert validate_stage_routing("jd_facts") == []


def test_blueprint_assembly_uses_no_provider_default():
    cfg = get_stage_step_config("blueprint_assembly")
    assert cfg.provider == "none"
    assert cfg.primary_model is None


def test_research_preflight_requires_v2_provider(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PROVIDER_RESEARCH_ENRICHMENT", "none")
    errors = validate_stage_routing("research_enrichment")
    assert "research_enrichment: V2 enabled requires a real provider" in errors


def test_research_preflight_requires_source_attribution_for_live_compat(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PROVIDER_RESEARCH_ENRICHMENT", "codex")
    monkeypatch.setenv("PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION", "false")
    errors = validate_stage_routing("research_enrichment")
    assert "research_enrichment: live compat write requires source attribution" in errors


def test_research_preflight_requires_codex_transport_when_live_web_enabled(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PROVIDER_RESEARCH_ENRICHMENT", "codex")
    monkeypatch.setenv("PREENRICH_TRANSPORT_RESEARCH_ENRICHMENT", "none")
    errors = validate_stage_routing("research_enrichment")
    assert "research_enrichment: WEB_RESEARCH_ENABLED=true requires a codex research transport" in errors
