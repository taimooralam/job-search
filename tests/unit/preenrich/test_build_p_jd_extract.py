from __future__ import annotations

import pytest

from src.preenrich.blueprint_config import taxonomy_version
from src.preenrich.blueprint_prompts import build_p_jd_extract
from src.preenrich.stages.jd_facts import _compact_raw_jd


def test_build_p_jd_extract_contains_runner_taxonomy_contract():
    prompt = build_p_jd_extract(
        title="Head of Engineering",
        company="Acme",
        deterministic_hints={"title": {"value": "Head of Engineering"}},
        structured_sections={"responsibilities": ["Lead the team"], "used_processed_jd_sections": True},
        raw_jd_excerpt="Lead the team and ship the roadmap.",
    )
    for slug in (
        "engineering_manager",
        "staff_principal_engineer",
        "director_of_engineering",
        "head_of_engineering",
        "vp_engineering",
        "cto",
        "tech_lead",
        "senior_engineer",
        "technical_architect",
        "people_leader",
        "execution_driver",
        "strategic_visionary",
        "domain_expert",
        "builder_founder",
        "process_champion",
        "hybrid_technical_leader",
        "fully_remote",
        "hybrid",
        "onsite",
        "not_specified",
    ):
        assert slug in prompt
    assert "Return ONLY valid JSON" in prompt
    assert "No markdown fences" in prompt
    assert f"taxonomy_version={taxonomy_version()}" in prompt
    assert "application_url" in prompt
    assert "salary_range" in prompt
    assert "language_requirements" in prompt
    assert "remote_location_detail" in prompt
    assert "weighting_profiles" in prompt
    assert "analysis_metadata" in prompt
    assert "Extraction workflow:" in prompt
    assert "extract application_url, salary_range, and language_requirements from the JD text whenever they are present" in prompt
    assert "Strict nested-shape rules" in prompt
    assert "Anti-pattern bans" in prompt
    assert "do not return expectations as a flat list" in prompt


def test_build_p_jd_extract_rejects_hypothesis_payload():
    with pytest.raises(ValueError, match="must not reference job_hypotheses"):
        build_p_jd_extract(
            title="Head of Engineering",
            company="Acme",
            deterministic_hints={"job_hypotheses": {"do_not": "leak"}},
            structured_sections={},
            raw_jd_excerpt="Job description",
        )


def test_build_p_jd_extract_uses_taxonomy_context_not_parallel_hardcoding():
    prompt = build_p_jd_extract(
        title="Head of Engineering",
        company="Acme",
        deterministic_hints={},
        structured_sections={},
        raw_jd_excerpt="English required. Apply here https://example.com/apply",
    )
    assert '"role_categories"' in prompt
    assert '"ideal_candidate_archetypes"' in prompt
    assert '"likely_archetypes"' in prompt
    assert "Use the runner-era extraction contract as the quality baseline, then add the richer 4.1.1 contract as first-class output." in prompt


def test_compact_raw_jd_preserves_tail_signal():
    head = "A" * 6000
    tail = "MANDATORY_TAIL_SIGNAL"
    compacted = _compact_raw_jd(f"{head}\n{tail}", limit=4000)
    assert "MANDATORY_TAIL_SIGNAL" in compacted
    assert "[... middle truncated for extraction parity ...]" in compacted
