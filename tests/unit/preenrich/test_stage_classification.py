from __future__ import annotations

from bson import ObjectId

from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.types import StageContext, StepConfig


def _context() -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "AI Engineering Leader",
            "company": "Acme",
            "description": (
                "Lead AI engineering delivery, manage engineers, hire engineers, conduct performance reviews, "
                "and own the roadmap for production AI systems."
            ),
            "processed_jd_sections": [
                {"section_type": "responsibilities", "header": "Responsibilities", "content": ["Manage engineers", "Lead AI engineering delivery"]},
            ],
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "extraction": {
                            "title": "AI Engineering Leader",
                            "role_category": "engineering_manager",
                            "seniority_level": "director",
                            "responsibilities": ["Manage engineers", "Hire engineers", "Lead AI engineering delivery"],
                            "qualifications": ["People management experience", "AI platform experience"],
                            "top_keywords": ["AI", "people management", "hiring"],
                            "competency_weights": {"delivery": 25, "process": 20, "architecture": 15, "leadership": 40},
                            "ideal_candidate_profile": {"archetype": "people_leader"},
                        },
                        "merged_view": {"title": "AI Engineering Leader"},
                    }
                }
            },
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        config=StepConfig(provider="codex", primary_model="gpt-5.4-mini", fallback_provider="none", fallback_model=None),
    )


def test_classification_v2_runs_deterministic_short_circuit(monkeypatch):
    result = ClassificationStage().run(_context())
    assert result.stage_output["primary_role_category"] == "engineering_manager"
    assert result.stage_output["decision_path"] == "deterministic_short_circuit"
    assert result.output["is_ai_job"] is True
    assert "extracted_jd" not in result.output


def test_classification_always_returns_v2_stage_output(monkeypatch):
    result = ClassificationStage().run(_context())
    assert result.stage_output["decision_path"] == "deterministic_short_circuit"
    assert result.stage_output["primary_role_category"] == "engineering_manager"
    assert result.output["ai_classification"]["taxonomy_version"]


def test_classification_fail_open_returns_valid_low_confidence(monkeypatch):
    ctx = _context()
    ctx.config.provider = "none"
    ctx.job_doc["pre_enrichment"]["outputs"]["jd_facts"]["extraction"] = {
        "title": "Unknown role",
        "responsibilities": [],
        "qualifications": [],
        "top_keywords": [],
    }
    result = ClassificationStage().run(ctx)
    assert result.stage_output["confidence"] == "low"
    assert result.stage_output["decision_path"] in {"fail_open", "deterministic_short_circuit"}
