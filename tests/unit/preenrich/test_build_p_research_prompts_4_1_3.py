from __future__ import annotations

from src.preenrich.blueprint_prompts import (
    build_p_application_surface,
    build_p_inferred_stakeholder_personas_v1,
    build_p_research_company,
    build_p_research_role,
    build_p_stakeholder_discovery,
    build_p_stakeholder_discovery_v2,
    build_p_stakeholder_outreach_guidance,
    build_p_stakeholder_profile_v2,
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
    assert "official-employer discovery queries" in prompt
    assert "Do not spend more than one query on tertiary job boards" in prompt


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
    assert "Do not inspect local files, prompts, tests, or use shell commands" in prompt
    assert "Use this minimal shape as a guide" in prompt
    assert '"identity_confidence"' in prompt


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
    assert "Do not inspect local files, prompts, tests, or use shell commands" in prompt
    assert "Use this minimal shape as a guide" in prompt
    assert '"collaboration_map"' in prompt


def test_transport_preamble_forbids_local_schema_discovery():
    prompt = _transport()
    assert "Do not inspect local repository files" in prompt
    assert "Do not use shell commands for schema discovery" in prompt
    assert "Do not narrate planning" in prompt


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


def test_stakeholder_surface_discovery_v2_separates_real_identity_from_journal():
    prompt = build_p_stakeholder_discovery_v2(
        canonical_company_identity={
            "canonical_name": "Acme",
            "canonical_domain": "acme.example.com",
            "aliases": ["Acme"],
            "official_urls": ["https://acme.example.com"],
            "identity_confidence": {"score": 0.9, "band": "high", "basis": "official"},
        },
        target_role_brief={"normalized_title": "Staff Engineer", "role_family": "staff_principal_engineer", "function": "engineering", "department": "platform", "seniority": "staff"},
        evaluator_coverage_target=["recruiter", "hiring_manager", "peer_technical"],
        seed_stakeholders=[],
        company_profile_excerpt={"summary": "AI company"},
        role_profile_excerpt={"summary": "Platform role"},
        application_profile_excerpt={"portal_family": "greenhouse"},
        jd_excerpt="Find the likely hiring manager or recruiter.",
        search_constraints={"public_professional_only": True, "max_queries": 6, "max_fetches": 8},
        transport_preamble=_transport(),
        job_id="job-123",
    )
    assert "Truth beats coverage" in prompt
    assert "Low-confidence or ambiguous candidates belong in search_journal" in prompt
    assert "Do not construct LinkedIn URLs" in prompt


def test_stakeholder_surface_profile_v2_rejects_cv_section_ids():
    prompt = build_p_stakeholder_profile_v2(
        stakeholder_record={"stakeholder_type": "hiring_manager", "name": "Jordan Smith"},
        target_role_brief={"normalized_title": "Staff Engineer", "role_family": "staff_principal_engineer", "function": "engineering", "department": "platform", "seniority": "staff"},
        company_profile_excerpt={"summary": "AI company"},
        role_profile_excerpt={"summary": "Platform role"},
        application_profile_excerpt={"portal_family": "greenhouse"},
        jd_excerpt="Role expects architecture and execution.",
        public_posts_fetched=[],
        coverage_context={"evaluator_coverage_target": ["recruiter", "hiring_manager"], "real_types_already_found": ["recruiter"]},
        transport_preamble=_transport(),
    )
    assert "preferred_signal_order must use abstract signal categories only" in prompt
    assert "Do not emit exact title text" in prompt


def test_inferred_persona_prompt_forbids_real_identity_fields():
    prompt = build_p_inferred_stakeholder_personas_v1(
        target_role_brief={"normalized_title": "Staff Engineer", "role_family": "staff_principal_engineer", "function": "engineering", "department": "platform", "seniority": "staff"},
        canonical_company_identity={"canonical_name": "Acme", "canonical_domain": "acme.example.com", "aliases": ["Acme"], "official_urls": ["https://acme.example.com"], "identity_confidence": {"score": 0.9, "band": "high", "basis": "official"}},
        company_profile_excerpt={"summary": "AI company"},
        role_profile_excerpt={"summary": "Platform role"},
        application_profile_excerpt={"portal_family": "greenhouse"},
        classification_excerpt={"primary_role_category": "staff_principal_engineer", "ai_taxonomy": {"intensity": "core"}},
        jd_excerpt="Role expects architecture and execution.",
        real_stakeholder_summaries=[{"stakeholder_type": "recruiter", "identity_status": "resolved"}],
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        missing_coverage_types=["hiring_manager"],
        emission_mode="coverage_gap",
    )
    assert "Never emit a name, profile_url, current_title, or current_company" in prompt
    assert 'MUST contain the literal word "inferred"' in prompt
