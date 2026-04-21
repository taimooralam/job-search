from __future__ import annotations

from src.preenrich.blueprint_prompts import (
    build_p_application_surface,
    build_p_research_company,
    build_p_research_role,
    build_p_stakeholder_discovery,
    build_p_stakeholder_outreach_guidance,
    build_p_transport_preamble,
)


def _transport() -> str:
    return build_p_transport_preamble(
        transport_used="codex_web_search",
        max_web_queries=4,
        max_fetches=2,
        max_tool_turns=4,
    )


def test_application_surface_prompt_includes_verified_only_rules():
    prompt = build_p_application_surface(
        title="Engineer",
        company="Acme",
        location="Remote",
        job_url="https://boards.greenhouse.io/acme/jobs/123",
        ats_domains=["greenhouse.io"],
        blocked_domains=["linkedin.com"],
        transport_preamble=_transport(),
    )
    assert "canonical_application_url" in prompt
    assert "Do not invent URLs" in prompt
    assert "Never emit a URL for a different company" in prompt


def test_company_prompt_preserves_compat_fields_and_guardrails():
    prompt = build_p_research_company(
        company="Acme",
        name_variations=["Acme Inc"],
        company_url="https://acme.example.com",
        candidate_domains=["acme.example.com"],
        jd_excerpt="Build AI workflow software.",
        classification={"role_category": "engineering_manager"},
        application_profile={"portal_family": "greenhouse"},
        transport_preamble=_transport(),
    )
    assert '"summary"' in prompt or "summary" in prompt
    assert "canonical_domain" in prompt
    assert "Do not guess domains or URLs from slugs alone" in prompt


def test_role_prompt_keeps_reporting_line_unknown_without_evidence():
    prompt = build_p_research_role(
        title="Staff Engineer",
        company="Acme",
        jd_text="Lead platform work.",
        jd_facts={"title": "Staff Engineer"},
        classification={"role_category": "staff_principal_engineer"},
        company_profile={"summary": "AI company"},
        application_profile={"portal_family": "greenhouse"},
        transport_preamble=_transport(),
    )
    assert "reporting_line" in prompt
    assert "must stay unknown unless explicitly evidenced" in prompt


def test_stakeholder_discovery_prompt_enforces_identity_ladder():
    prompt = build_p_stakeholder_discovery(
        title="Engineer",
        company="Acme",
        company_profile={"summary": "AI company"},
        role_profile={"summary": "Platform role"},
        application_profile={"portal_family": "greenhouse"},
        jd_excerpt="Hiring manager may partner with platform.",
        transport_preamble=_transport(),
    )
    assert "identity ladder" in prompt.lower()
    assert "No constructed LinkedIn URLs" in prompt


def test_outreach_guidance_prompt_is_guidance_only():
    prompt = build_p_stakeholder_outreach_guidance(
        stakeholder_record={"stakeholder_type": "hiring_manager"},
        stakeholder_profile={"likely_priorities": []},
        role_profile={"summary": "Platform role"},
        company_profile={"summary": "AI company"},
        jd_facts={"title": "Engineer"},
    )
    assert "Produce guidance only, not outreach copy" in prompt
    assert "non-manipulative" in prompt
