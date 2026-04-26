"""Tests for iteration-4.1 blueprint registry and DAG behavior."""

from __future__ import annotations

from src.preenrich.dag import current_stage_order, invalidate
from src.preenrich.stage_registry import stage_registry


def test_blueprint_stage_registry_contains_iteration41_stage_set(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PERSONA_COMPAT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED", "false")

    assert list(stage_registry().keys()) == [
        "jd_structure",
        "jd_facts",
        "classification",
        "application_surface",
        "research_enrichment",
        "stakeholder_surface",
        "job_inference",
        "job_hypotheses",
        "annotations",
        "persona_compat",
        "cv_guidelines",
        "blueprint_assembly",
    ]


def test_job_hypotheses_is_not_required_for_cv_ready(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    registry = stage_registry()
    assert registry["job_hypotheses"].required_for_cv_ready is False
    assert registry["blueprint_assembly"].required_for_cv_ready is True
    assert registry["research_enrichment"].prerequisites == ("jd_facts", "classification", "application_surface")
    assert registry["stakeholder_surface"].prerequisites == ("jd_facts", "classification", "application_surface", "research_enrichment")


def test_persona_compat_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PERSONA_COMPAT_ENABLED", "false")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "false")

    assert "persona_compat" not in current_stage_order()
    registry = stage_registry()
    assert registry["persona_compat"].required_for_cv_ready is False
    assert "persona_compat" not in registry["blueprint_assembly"].prerequisites


def test_blueprint_invalidation_propagates_to_blueprint_assembly(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    stale = invalidate({"jd"})
    assert "jd_facts" in stale
    assert "classification" in stale
    assert "application_surface" in stale
    assert "stakeholder_surface" in stale
    assert "job_inference" in stale
    assert "cv_guidelines" in stale
    assert "blueprint_assembly" in stale


def test_stakeholder_surface_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "false")

    registry = stage_registry()
    assert "stakeholder_surface" not in current_stage_order()
    assert "stakeholder_surface" not in registry


def test_presentation_contract_is_absent_by_default(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED", "false")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_ENABLED", "false")

    registry = stage_registry()
    assert "presentation_contract" not in current_stage_order()
    assert "presentation_contract" not in registry


def test_pain_point_intelligence_is_absent_by_default(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED", "false")

    registry = stage_registry()
    assert "pain_point_intelligence" not in current_stage_order()
    assert "pain_point_intelligence" not in registry


def test_presentation_contract_can_be_enabled_without_becoming_cv_ready_gate(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_ENABLED", "true")

    registry = stage_registry()
    assert "pain_point_intelligence" in current_stage_order()
    assert registry["pain_point_intelligence"].prerequisites == (
        "jd_facts",
        "classification",
        "research_enrichment",
    )
    assert registry["pain_point_intelligence"].required_for_cv_ready is True
    assert "presentation_contract" in current_stage_order()
    assert registry["presentation_contract"].prerequisites == (
        "jd_facts",
        "classification",
        "research_enrichment",
        "stakeholder_surface",
        "pain_point_intelligence",
    )
    assert registry["presentation_contract"].required_for_cv_ready is False
