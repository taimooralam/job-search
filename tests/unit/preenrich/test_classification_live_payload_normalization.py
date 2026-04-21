from __future__ import annotations

from bson import ObjectId

from src.preenrich.blueprint_models import ClassificationDoc
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.types import StageContext, StepConfig


def _live_payload() -> dict:
    return {
        "primary_role_category": "staff_principal_engineer",
        "secondary_role_categories": ["tech_lead", "senior_engineer"],
        "search_profiles": ["ai_senior_ic", "ai_architect"],
        "selector_profiles": ["staff-principal", "architect"],
        "tone_family": "architect",
        "taxonomy_version": "2026-04-20-v2",
        "confidence": 0.97,
        "ambiguity_score": 0.13,
        "reason_codes": [
            "title_contains_lead_but_jd_is_staff_level_architecture_ic_work",
            "technical_vision_architecture_standardization_and_cross_org_influence_match_staff_principal",
        ],
        "evidence": {
            "title": ["Lead AI Engineer"],
            "responsibilities": [
                "define and own technical vision and architecture",
                "improve internal AI tooling, shared libraries, SDKs, reference implementations",
            ],
            "qualifications": [
                "7+ years software engineering, 3+ years production GenAI/RAG",
            ],
            "keywords": ["LLMs", "RAG", "Vector databases"],
            "archetype": ["technical_architect"],
        },
        "jd_facts_agreement": {
            "title": True,
            "seniority_level": True,
            "role_category": True,
            "overall": True,
        },
        "pre_score": [
            {"category": "tech_lead", "score": 8.19},
            {"category": "senior_engineer", "score": 7.448},
            {
                "category": "staff_principal_engineer",
                "score": 3.316,
                "evidence": {"responsibilities": ["technical strategy"]},
            },
        ],
        "decision_path": [
            "start from pre-score: tech_lead highest",
            "override due stronger staff/principal signals from technical vision, architecture ownership, standards, and cross-team influence",
            "select staff_principal_engineer because JD is IC architecture-heavy and lacks people-management signals",
        ],
        "ai_taxonomy": {
            "is_ai_job": True,
            "primary_specialization": "ai_architect",
            "secondary_specializations": ["genai_llm", "mlops_llmops"],
            "intensity": "core",
            "scope_tags": ["ai_architecture", "agentic_systems", "rag", "genai_product", "mlops_llmops"],
            "legacy_ai_categories": ["ai_general"],
            "rationale": "AI is core to the role.",
        },
        "ai_relevance": {
            "relevant": True,
            "rationale": "Core AI/GenAI architecture role with production LLM, RAG, agents, and governance scope.",
        },
    }


def test_classification_doc_accepts_live_rich_codex_payload():
    doc = ClassificationDoc.model_validate(_live_payload())

    assert str(doc.primary_role_category) == "RoleCategory.staff_principal_engineer" or doc.primary_role_category.value == "staff_principal_engineer"
    assert doc.confidence == "high"
    assert doc.evidence.title_matches == ["Lead AI Engineer"]
    assert doc.evidence.responsibility_matches
    assert doc.jd_facts_agreement.agrees is True
    assert "override due stronger staff/principal signals" in doc.decision_path
    assert doc.ai_relevance["is_ai_job"] is True
    assert doc.ai_relevance["categories"] == ["ai_general"]


def _context() -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Lead AI Engineer",
            "company": "Robson Bale",
            "description": (
                "Define the technical vision and architecture for AI solutions across the organization. "
                "Mentor engineers, conduct code reviews, and build production-ready LLM, RAG, and agentic systems."
            ),
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "extraction": {
                            "title": "Lead AI Engineer",
                            "role_category": "staff_principal_engineer",
                            "seniority_level": "staff",
                            "responsibilities": [
                                "Define and own technical vision and architecture",
                                "Mentor engineers",
                                "Conduct code reviews",
                            ],
                            "qualifications": [
                                "7+ years of software engineering experience",
                                "Production GenAI and RAG experience",
                            ],
                            "top_keywords": ["LLMs", "RAG", "Vector databases"],
                            "competency_weights": {"delivery": 25, "process": 15, "architecture": 45, "leadership": 15},
                            "ideal_candidate_profile": {"archetype": "technical_architect"},
                        },
                        "merged_view": {"title": "Lead AI Engineer"},
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


def test_classification_stage_preserves_live_rich_codex_payload(monkeypatch):
    monkeypatch.setattr(
        "src.preenrich.stages.classification._invoke_codex_json",
        lambda **_: (_live_payload(), {"provider": "codex", "model": "gpt-5.4-mini", "outcome": "success", "error": None, "duration_ms": 10}),
    )

    result = ClassificationStage().run(_context())

    assert result.stage_output["primary_role_category"] == "staff_principal_engineer"
    assert result.stage_output["confidence"] == "high"
    assert result.stage_output["reason_codes"] != ["llm_validation_failed"]
    assert "override due stronger staff/principal signals" in result.stage_output["decision_path"]
