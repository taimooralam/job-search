from __future__ import annotations

from bson import ObjectId

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

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str):
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


def test_jd_facts_v2_escalates_to_stronger_model_on_schema_failure(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", "gpt-5.4")
    sample = _sample_extracted_jd()
    calls: list[str] = []

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str):
        calls.append(model)
        if len(calls) == 1:
            bad = dict(sample)
            bad.pop("role_category")
            return bad, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)

    result = JDFactsStage().run(_context())

    assert calls == ["gpt-5.4-mini", "gpt-5.4"]
    assert result.model_used == "gpt-5.4"
    assert result.output["extracted_jd"]["role_category"] == "head_of_engineering"


def test_jd_facts_v2_uses_processed_sections_without_changing_schema(monkeypatch):
    monkeypatch.setenv("PREENRICH_JD_FACTS_V2_ENABLED", "true")
    sample = _sample_extracted_jd()
    captured: dict[str, str] = {}

    def _fake_invoke_codex_json(*, prompt: str, model: str, job_id: str):
        captured["prompt"] = prompt
        return sample, {"provider": "codex", "model": model, "outcome": "success", "error": None, "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.jd_facts._invoke_codex_json", _fake_invoke_codex_json)
    result = JDFactsStage().run(_context())
    assert "Responsibilities" in captured["prompt"] or "responsibilities" in captured["prompt"]
    assert result.stage_output["confirmations"]["used_processed_jd_sections"] is True


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
