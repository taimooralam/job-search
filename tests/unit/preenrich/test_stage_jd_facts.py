from __future__ import annotations

from bson import ObjectId
import pytest

from src.layer1_4.claude_jd_extractor import ExtractedJDModel
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.stages.jd_facts import JDFactsStage
from src.preenrich.types import StageContext, StepConfig


def _sample_extracted_jd() -> dict:
    return {
        "title": "Head of Engineering",
        "company": "Acme",
        "location": "Remote (EU)",
        "remote_policy": "fully_remote",
        "role_category": "head_of_engineering",
        "seniority_level": "director",
        "competency_weights": {"delivery": 25, "process": 15, "architecture": 20, "leadership": 40},
        "responsibilities": [
            "Build the engineering team from scratch",
            "Define engineering culture and hiring bar",
            "Architect scalable systems for 100x growth",
            "Partner with CEO on product strategy",
            "Establish CI/CD and quality standards",
        ],
        "qualifications": [
            "10+ years software engineering experience",
            "5+ years leading engineering teams",
            "Experience scaling 0 to 1M+ users",
            "Strong Python, TypeScript, AWS/GCP background",
        ],
        "nice_to_haves": ["Previous CTO experience", "Startup experience", "Remote-first leadership"],
        "technical_skills": ["Python", "TypeScript", "AWS", "GCP", "CI/CD"],
        "soft_skills": ["Leadership", "Team Building", "Strategic Thinking"],
        "implied_pain_points": ["No engineering team or processes exist", "Need to move fast while building foundations"],
        "success_metrics": ["10 engineers hired in 12 months", "System architecture supports 100x growth"],
        "top_keywords": [
            "Head of Engineering",
            "Engineering Leadership",
            "Python",
            "TypeScript",
            "AWS",
            "GCP",
            "CI/CD",
            "Team Building",
            "Startup",
            "Remote",
            "Scaling",
            "Architecture",
            "Engineering Culture",
            "Hiring",
            "SaaS",
        ],
        "industry_background": "B2B SaaS",
        "years_experience_required": 10,
        "education_requirements": "BS in CS or equivalent",
        "ideal_candidate_profile": {
            "identity_statement": "A senior technical leader who can build engineering foundations while scaling execution.",
            "archetype": "builder_founder",
            "key_traits": ["systems thinker", "builder", "team mentor"],
            "experience_profile": "10+ years engineering, 5+ years leadership",
            "culture_signals": ["fast-paced", "autonomous", "remote-first"],
        },
        "salary_range": "$180k - $220k",
        "application_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "remote_location_detail": {
            "remote_anywhere": False,
            "remote_regions": ["EU"],
            "timezone_expectations": ["Overlap with CET"],
            "travel_expectation": "Quarterly travel",
            "onsite_expectation": None,
            "location_constraints": ["EU only"],
            "relocation_support": None,
            "primary_locations": ["Remote (EU)"],
            "secondary_locations": [],
            "geo_scope": "region",
            "work_authorization_notes": "Must be eligible to work in the EU",
        },
        "expectations": {
            "explicit_outcomes": ["Build the engineering team from scratch"],
            "delivery_expectations": ["Ship the roadmap"],
            "leadership_expectations": ["Hire and mentor engineers"],
            "communication_expectations": ["Partner with CEO on product strategy"],
            "collaboration_expectations": ["Work with product leadership"],
            "first_90_day_expectations": ["Assess team gaps"],
        },
        "identity_signals": {
            "primary_identity": "builder-founder engineering leader",
            "alternate_identities": ["player-coach"],
            "identity_evidence": ["Build the engineering team from scratch"],
            "career_stage_signals": ["0 to 1 leadership"],
        },
        "skill_dimension_profile": {
            "communication_skills": ["Executive communication"],
            "leadership_skills": ["Team building", "Mentoring"],
            "delivery_skills": ["Roadmap execution"],
            "architecture_skills": ["Scalable system design"],
            "process_skills": ["CI/CD"],
            "stakeholder_skills": ["CEO partnership"],
        },
        "team_context": {
            "team_size": "0 to 10 engineers",
            "reporting_to": "CEO",
            "org_scope": "Engineering",
            "management_scope": "Direct manager of engineers",
        },
        "weighting_profiles": {
            "expectation_weights": {
                "delivery": 30,
                "communication": 15,
                "leadership": 30,
                "collaboration": 10,
                "strategic_scope": 15,
            },
            "operating_style_weights": {
                "autonomy": 25,
                "ambiguity": 20,
                "pace": 20,
                "process_rigor": 15,
                "stakeholder_exposure": 20,
            },
        },
        "operating_signals": ["fast-paced startup", "high ownership"],
        "ambiguity_signals": ["Remote EU scope is implied by title and location"],
        "language_requirements": {
            "required_languages": ["English"],
            "preferred_languages": [],
            "fluency_expectations": ["Professional fluency in English"],
            "language_notes": None,
        },
        "company_description": "Growth-stage B2B SaaS company.",
        "role_description": "Own the engineering function and system architecture.",
        "residual_context": "Remote-first hiring with strong execution expectations.",
        "analysis_metadata": {
            "overall_confidence": "high",
            "field_confidence": {
                "role_category": "high",
                "seniority_level": "high",
                "ideal_candidate_profile": "high",
                "rich_contract": "medium",
            },
            "inferred_fields": ["ideal_candidate_profile"],
            "ambiguities": ["Team size inferred from build-from-scratch wording"],
            "source_coverage": {
                "used_structured_sections": True,
                "used_raw_excerpt": True,
                "tail_coverage": "full",
                "truncation_risk": "low",
            },
            "quality_checks": {
                "competency_weights_sum_100": True,
                "weighting_profile_sums_valid": True,
                "top_keywords_ranked": True,
                "duplicate_list_items_removed": True,
            },
        },
    }


def _context(*, description: str | None = None) -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Head of Engineering",
            "company": "Acme",
            "location": "Remote (EU)",
            "description": description
            or (
                "Head of Engineering - Remote (EU)\n"
                "Responsibilities:\n"
                "- Build the engineering team from scratch\n"
                "- Architect scalable systems to support 100x growth\n"
                "Requirements:\n"
                "- 10+ years software engineering experience\n"
                "- Strong Python, TypeScript, AWS/GCP background\n"
                "Preferred:\n"
                "- Startup experience\n"
                "Apply here: https://boards.greenhouse.io/acme/jobs/12345\n"
                "Compensation: $180k - $220k"
            ),
            "jobUrl": "https://boards.greenhouse.io/acme/jobs/12345",
            "processed_jd_sections": [
                {"section_type": "responsibilities", "header": "Responsibilities", "content": "- Build the engineering team\n- Architect scalable systems"},
                {"section_type": "requirements", "header": "Requirements", "content": "- 10+ years software engineering experience\n- Strong Python background"},
                {"section_type": "preferred", "header": "Preferred", "content": "- Startup experience"},
                {"section_type": "about_company", "header": "About Company", "content": "Growth-stage B2B SaaS company."},
            ],
            "pre_enrichment": {"outputs": {}},
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        config=StepConfig(
            provider="codex",
            primary_model="gpt-5.4-mini",
            fallback_provider="claude",
            fallback_model="claude-sonnet-4-6",
        ),
    )


def test_jd_facts_v2_emits_runner_parity_compat_projection(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED", "true")
    sample = _sample_extracted_jd()

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        assert "structured_sections" in prompt
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)

    result = JDFactsStage().run(_context())

    compat = result.output["extracted_jd"]
    ExtractedJDModel(**compat)
    assert compat["company"] == "Acme"
    assert compat["required_qualifications"] == compat["qualifications"]
    assert compat["key_responsibilities"] == compat["responsibilities"]
    assert compat["salary"] == "$180k - $220k"
    assert result.output["salary_range"] == "$180k - $220k"
    assert result.stage_output["extraction"]["company"] == "Acme"
    assert result.stage_output["extraction"]["language_requirements"]["required_languages"] == ["English"]
    assert result.stage_output["extraction"]["analysis_metadata"]["overall_confidence"] == "high"


def test_jd_facts_v2_escalates_to_stronger_model_on_schema_failure(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATION_MODELS", "gpt-5.3,gpt-5.4")
    sample = _sample_extracted_jd()
    calls: list[str] = []

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        calls.append(model)
        if len(calls) < 3:
            bad = dict(sample)
            bad.pop("role_category")
            return bad, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)

    result = JDFactsStage().run(_context())

    assert calls == ["gpt-5.4-mini", "gpt-5.3", "gpt-5.4"]
    assert result.model_used == "gpt-5.4"
    assert result.output["extracted_jd"]["role_category"] == "head_of_engineering"


def test_jd_facts_v2_respects_codex_only_mode(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", "true")
    ctx = _context()
    ctx.config.fallback_provider = "none"

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        return None, {"provider": "codex", "model": model, "outcome": "error_subprocess", "error": "timeout", "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)

    with pytest.raises(RuntimeError, match="codex-only extraction failed"):
        JDFactsStage().run(ctx)


def test_jd_facts_v2_uses_processed_sections_without_changing_schema(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    sample = _sample_extracted_jd()
    captured: dict[str, str] = {}

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        captured["prompt"] = prompt
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)
    result = JDFactsStage().run(_context())
    assert "Responsibilities" in captured["prompt"] or "responsibilities" in captured["prompt"]
    assert result.stage_output["confirmations"]["used_processed_jd_sections"] is True
    assert "taxonomy_version=" in captured["prompt"]


def test_jd_facts_v2_normalizes_rich_contract_shape_mismatches(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    sample = _sample_extracted_jd()
    sample["remote_location_detail"] = "100% remote; must be based in Spain"
    sample["expectations"] = ["Ship ML into production"]
    sample["team_context"] = "International fintech team"
    sample["language_requirements"] = ["Strong communication skills in English"]
    sample["residual_context"] = ["Global fintech", "Multiple hires"]
    sample["weighting_profiles"] = {
        "expectation_weights": {
            "production_ml_delivery": 40,
            "executive_communication": 10,
            "people_leadership": 20,
            "cross_functional_collaboration": 20,
            "fintech_domain_context": 10,
        },
        "operating_style_weights": {
            "remote_autonomy": 20,
            "hands_on_building": 20,
            "hands_on_execution": 25,
            "technical_quality_rigor": 20,
            "remote_communication": 15,
        },
    }

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)
    result = JDFactsStage().run(_context())

    extraction = result.stage_output["extraction"]
    assert extraction["remote_location_detail"]["location_constraints"] == ["100% remote; must be based in Spain"]
    assert extraction["expectations"]["explicit_outcomes"] == ["Ship ML into production"]
    assert extraction["team_context"]["org_scope"] == "International fintech team"
    assert extraction["language_requirements"]["fluency_expectations"] == ["Strong communication skills in English"]
    assert extraction["residual_context"] == "Global fintech Multiple hires"
    assert extraction["weighting_profiles"]["expectation_weights"]["delivery"] == 40
    assert extraction["weighting_profiles"]["operating_style_weights"]["stakeholder_exposure"] == 15


def test_jd_facts_v2_literalizes_responsibilities_and_success_metrics_for_engineering_leader(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    sample = _sample_extracted_jd()
    sample["role_category"] = "tech_lead"
    sample["responsibilities"] = ["Lead teams and set technical direction"]
    sample["success_metrics"] = ["Ship AI work"]
    ctx = _context(
        description=(
            "AI Engineering Leader – Remote (Spain) | Fintech\n"
            "A global fintech powering cross-border payments and scaling AI capability.\n"
            "Strong experience delivering applied ML solutions into production.\n"
            "Practical experience with LLMs and NLP.\n"
            "Microservices architecture and systems integration experience.\n"
            "Experience integrating third-party AI tools and APIs.\n"
            "Proven leadership / team mentoring experience.\n"
            "Investing heavily in automation, intelligence, and next-generation solutions.\n"
        )
    )

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)
    result = JDFactsStage().run(ctx)
    extraction = result.stage_output["extraction"]

    assert extraction["role_category"] == "engineering_manager"
    assert extraction["responsibilities"][0] == "Lead AI engineering team and set technical direction"
    assert "Deliver applied ML solutions into production environments" in extraction["responsibilities"]
    assert extraction["success_metrics"] == [
        "Applied ML solutions successfully deployed to production",
        "AI capability scaled across the organization",
        "Team growth and technical development",
        "Third-party AI tools effectively integrated",
        "Automation and intelligence solutions operational",
        "Measurable improvements in payment processing efficiency",
    ]


def test_jd_facts_v2_preserves_model_keyword_order_with_dedup_only(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    sample = _sample_extracted_jd()
    sample["top_keywords"] = ["Python", "AWS", "Python", "LLMs", "FinTech"]

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str, cwd: str | None = None, reasoning_effort: str | None = None):
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)
    result = JDFactsStage().run(_context())
    extraction = result.stage_output["extraction"]
    assert extraction["top_keywords"] == ["Python", "AWS", "LLMs", "FinTech"]


def test_classification_no_longer_overwrites_extracted_jd_role_category():
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"]["jd_facts"] = {"merged_view": {"title": "Head of Engineering"}}
    result = ClassificationStage().run(ctx)
    assert "extracted_jd.role_category" not in result.output


def test_blueprint_assembly_preserves_extraction_owned_fields(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"] = {
        "jd_facts": {"merged_view": _sample_extracted_jd()},
        "classification": {
            "primary_role_category": "head_of_engineering",
            "secondary_role_categories": [],
            "search_profiles": ["ai_leadership"],
            "selector_profiles": ["head-director"],
            "tone_family": "executive",
            "taxonomy_version": "2026-04-19-v1",
        },
        "research_enrichment": {"company_profile": {"summary": "Growth-stage AI company", "company_type": "employer", "url": "https://acme.example.com", "signals": []}},
        "application_surface": {"status": "resolved", "application_url": "https://boards.greenhouse.io/acme/jobs/12345", "portal_family": "greenhouse", "is_direct_apply": True, "friction_signals": []},
        "job_inference": {"semantic_role_model": {"role_mandate": "Lead engineering execution.", "expected_success_metrics": ["Ship roadmap"], "likely_screening_themes": ["leadership"], "ideal_candidate_archetypes": ["builder_founder"]}, "qualifications": {"must_have": ["Scale teams"]}},
        "cv_guidelines": {
            "title_guidance": {"title": "Title guidance", "bullets": ["Mirror the mandate"], "evidence_refs": [{"source": "jd_facts"}]},
            "identity_guidance": {"title": "Identity guidance", "bullets": ["Lead with scope"], "evidence_refs": [{"source": "jd_facts"}]},
            "bullet_theme_guidance": {"title": "Bullet guidance", "bullets": ["Show execution"], "evidence_refs": [{"source": "jd_facts"}]},
            "ats_keyword_guidance": {"title": "ATS", "bullets": ["python", "leadership"], "evidence_refs": [{"source": "jd_facts"}]},
            "cover_letter_expectations": {"title": "Cover letter", "bullets": ["Tie to company context"], "evidence_refs": [{"source": "jd_facts"}]},
        },
        "annotations": {"annotations": []},
        "persona_compat": {"status": "skipped"},
    }
    result = BlueprintAssemblyStage().run(ctx)
    assert "extracted_jd.top_keywords" not in result.output
    assert "extracted_jd.ideal_candidate_profile" not in result.output
