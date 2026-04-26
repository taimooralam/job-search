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


def test_classification_forwards_tracing_kwargs_to_llm(monkeypatch):
    ctx = _context()
    ctx.tracer = object()
    calls: list[dict[str, object]] = []

    monkeypatch.setattr("src.preenrich.stages.classification.classification_short_circuit_margin", lambda: 2.0)
    monkeypatch.setattr("src.preenrich.stages.classification.classification_escalate_on_failure_enabled", lambda: False)

    def _fake_invoke_codex_json(
        *,
        prompt: str,
        model: str,
        job_id: str,
        tracer=None,
        stage_name: str | None = None,
        substage: str = "llm.primary",
        cwd: str | None = None,
        reasoning_effort: str | None = None,
    ):
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "job_id": job_id,
                "tracer": tracer,
                "stage_name": stage_name,
                "substage": substage,
                "cwd": cwd,
                "reasoning_effort": reasoning_effort,
            }
        )
        return None, {"provider": "codex", "model": model, "outcome": "error_subprocess", "error": "forced", "duration_ms": 10}

    monkeypatch.setattr("src.preenrich.stages.classification._invoke_codex_json", _fake_invoke_codex_json)

    ClassificationStage().run(ctx)

    assert len(calls) == 1
    assert calls[0]["tracer"] is ctx.tracer
    assert calls[0]["stage_name"] == "classification"
    assert calls[0]["substage"] == "llm.primary"
