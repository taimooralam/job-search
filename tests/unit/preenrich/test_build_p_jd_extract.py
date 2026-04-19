from __future__ import annotations

import pytest

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


def test_build_p_jd_extract_rejects_hypothesis_payload():
    with pytest.raises(ValueError, match="must not reference job_hypotheses"):
        build_p_jd_extract(
            title="Head of Engineering",
            company="Acme",
            deterministic_hints={"job_hypotheses": {"do_not": "leak"}},
            structured_sections={},
            raw_jd_excerpt="Job description",
        )


def test_compact_raw_jd_preserves_tail_signal():
    head = "A" * 6000
    tail = "MANDATORY_TAIL_SIGNAL"
    compacted = _compact_raw_jd(f"{head}\n{tail}", limit=4000)
    assert "MANDATORY_TAIL_SIGNAL" in compacted
    assert "[... middle truncated for extraction parity ...]" in compacted
