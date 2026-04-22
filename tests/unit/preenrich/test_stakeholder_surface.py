from __future__ import annotations

import copy

from bson import ObjectId
import pytest

from src.preenrich.blueprint_models import CVPreferenceSurface, InferredStakeholderPersona, StakeholderRecord
from src.preenrich.research_transport import ResearchTransportResult
from src.preenrich.stages.stakeholder_surface import StakeholderSurfaceStage
from src.preenrich.types import StageContext, StepConfig


def _context(*, company_band: str = "high", company_score: float = 0.86, research_status: str = "completed", include_seed: bool = True) -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Senior Applied AI Engineer",
            "company": "Acme",
            "description": "Lead production AI systems with product and platform partners.",
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "merged_view": {
                            "title": "Senior Applied AI Engineer",
                            "seniority_level": "senior",
                            "responsibilities": ["Ship production AI systems", "Partner with product"],
                            "qualifications": ["Python", "LLMs"],
                        }
                    },
                    "classification": {
                        "primary_role_category": "senior_engineer",
                        "ai_taxonomy": {"intensity": "significant"},
                    },
                    "application_surface": {
                        "status": "partial",
                        "resolution_status": "unresolved",
                        "portal_family": "greenhouse",
                        "confidence": {"score": 0.4, "band": "low", "basis": "seed"},
                    },
                    "research_enrichment": {
                        "status": research_status,
                        "company_profile": {
                            "summary": "Acme builds AI workflow software.",
                            "canonical_name": "Acme",
                            "canonical_domain": "acme.example.com",
                            "canonical_url": "https://acme.example.com",
                            "identity_confidence": {"score": company_score, "band": company_band, "basis": "official"},
                            "confidence": {"score": company_score, "band": company_band, "basis": "official"},
                            "status": "partial",
                            "sources": [{"source_id": "src_company", "url": "https://acme.example.com", "source_type": "official_company_site", "fetched_at": "2026-04-21", "trust_tier": "primary"}],
                            "evidence": [{"claim": "Company identity verified.", "source_ids": ["src_company"]}],
                        },
                        "role_profile": {
                            "summary": "Senior AI role focused on shipping production systems.",
                            "mandate": ["Ship production AI systems"],
                            "collaboration_map": [],
                            "org_placement": {"function_area": "engineering"},
                            "confidence": {"score": 0.7, "band": "medium", "basis": "jd"},
                            "status": "partial",
                            "sources": [{"source_id": "src_role", "source_type": "job_document", "fetched_at": "2026-04-21", "trust_tier": "primary"}],
                            "evidence": [{"claim": "Role summary grounded in JD.", "source_ids": ["src_role"]}],
                        },
                        "application_profile": {
                            "status": "partial",
                            "resolution_status": "unresolved",
                            "portal_family": "greenhouse",
                            "confidence": {"score": 0.4, "band": "low", "basis": "seed"},
                        },
                        "stakeholder_intelligence": (
                            [
                                {
                                    "stakeholder_type": "recruiter",
                                    "identity_status": "resolved",
                                    "identity_confidence": {"score": 0.74, "band": "medium", "basis": "seed"},
                                    "identity_basis": "Seed recruiter.",
                                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                                    "candidate_rank": 7,
                                    "name": "Seed Recruiter",
                                    "current_title": "Technical Recruiter",
                                    "current_company": "Acme",
                                    "profile_url": "https://www.linkedin.com/in/seed-recruiter",
                                    "source_trail": ["src_seed"],
                                    "function": "recruiting",
                                    "relationship_to_role": "recruiter",
                                    "confidence": {"score": 0.74, "band": "medium", "basis": "seed"},
                                    "sources": [{"source_id": "src_seed", "url": "https://www.linkedin.com/in/seed-recruiter", "source_type": "public_professional_profile", "fetched_at": "2026-04-21", "trust_tier": "secondary"}],
                                    "evidence": [{"claim": "Seed recruiter exists.", "source_ids": ["src_seed"]}],
                                }
                            ]
                            if include_seed
                            else []
                        ),
                    },
                }
            },
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        config=StepConfig(
            provider="codex",
            primary_model="gpt-5.2",
            fallback_provider="none",
            transport="codex_web_search",
            fallback_transport="none",
            max_web_queries=6,
            max_fetches=8,
        ),
    )


def _mock_transport(monkeypatch, *, discovery_payload=None, profile_payload=None, personas_payload=None):
    def _fake_invoke(self, *, prompt: str, job_id: str, validator=None):
        if "P-stakeholder-discovery@v2" in prompt:
            payload = discovery_payload
        elif "P-stakeholder-profile@v2" in prompt:
            payload = profile_payload
        elif "P-inferred-stakeholder-personas@v1" in prompt:
            payload = personas_payload
        else:
            payload = None
        if payload is None:
            return ResearchTransportResult(success=False, error="no fixture payload", provider_used="codex", model_used="gpt-5.2", transport_used="codex_web_search")
        try:
            validated = validator(payload) if validator else payload
            return ResearchTransportResult(success=True, payload=validated, provider_used="codex", model_used="gpt-5.2", transport_used="codex_web_search")
        except Exception as exc:  # pragma: no cover - exercised by failure tests
            return ResearchTransportResult(success=False, payload=payload, error=str(exc), provider_used="codex", model_used="gpt-5.2", transport_used="codex_web_search")

    monkeypatch.setattr("src.preenrich.research_transport.CodexResearchTransport.invoke_json", _fake_invoke)


def test_stakeholder_record_accepts_new_evaluator_types():
    record = StakeholderRecord(
        stakeholder_type="skip_level_leader",
        identity_status="resolved",
        identity_confidence={"score": 0.8, "band": "high", "basis": "official"},
        matched_signal_classes=["official_team_page_named_person", "public_profile_company_role_match"],
    )
    assert record.stakeholder_type == "skip_level_leader"


def test_cv_preference_surface_rejects_cv_section_ids():
    with pytest.raises(ValueError, match="abstract signal categories"):
        CVPreferenceSurface(preferred_signal_order=["summary"])


def test_inferred_persona_requires_inferred_basis_and_clamps_high_confidence():
    persona = InferredStakeholderPersona(
        persona_id="persona_hiring_manager_1",
        persona_type="hiring_manager",
        coverage_gap="hiring_manager",
        evidence_basis="This is inferred from role class.",
        confidence={"score": 0.93, "band": "high", "basis": "too strong"},
    )
    assert persona.confidence.band == "medium"
    assert persona.confidence.score <= 0.79


def test_company_unresolved_fails_open_to_inferred_only(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    ctx = _context(company_band="low", company_score=0.2)
    result = StakeholderSurfaceStage().run(ctx)
    assert result.stage_output["status"] == "inferred_only"
    assert result.stage_output["real_stakeholders"] == []
    assert result.stage_output["inferred_stakeholder_personas"]


def test_real_stakeholder_found_profiles_and_missing_roles_emit_personas(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", "true")
    _mock_transport(
        monkeypatch,
        discovery_payload={
            "stakeholder_intelligence": [
                {
                    "stakeholder_type": "hiring_manager",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.84, "band": "high", "basis": "official team page plus public profile"},
                    "identity_basis": "Official team page and public profile.",
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                    "candidate_rank": 1,
                    "name": "Jordan Smith",
                    "current_title": "Engineering Manager",
                    "current_company": "Acme",
                    "profile_url": "https://www.linkedin.com/in/jordan-smith-acme",
                    "source_trail": ["src_mgr"],
                    "function": "engineering",
                    "seniority": "manager",
                    "relationship_to_role": "likely_hiring_manager",
                    "likely_influence": "strong_input",
                    "confidence": {"score": 0.84, "band": "high", "basis": "identity"},
                    "sources": [{"source_id": "src_mgr", "url": "https://www.linkedin.com/in/jordan-smith-acme", "source_type": "public_professional_profile", "fetched_at": "2026-04-21", "trust_tier": "secondary"}],
                    "evidence": [{"claim": "Jordan Smith is an engineering manager at Acme.", "source_ids": ["src_mgr"]}],
                }
            ],
            "search_journal": [{"step": "discovery", "query": "site:acme.example.com engineering manager", "intent": "find_hiring_manager", "source_type": "company_site", "outcome": "hit", "source_ids": ["src_mgr"], "notes": ""}],
            "unresolved_markers": [],
            "notes": [],
        },
        profile_payload={
            "stakeholder_ref": "candidate_rank:1",
            "stakeholder_type": "hiring_manager",
            "role_in_process": "mandate_fit_and_delivery_risk_screen",
            "public_professional_decision_style": {
                "evidence_preference": "metrics_and_systems",
                "risk_posture": "quality_first",
                "speed_vs_rigor": "rigor_first",
                "communication_style": "concise_substantive",
                "authority_orientation": "credibility_over_title",
                "technical_vs_business_bias": "technical_first",
            },
            "cv_preference_surface": {
                "review_objectives": ["Verify shipped systems", "Verify ownership scope"],
                "preferred_signal_order": ["hands_on_implementation", "production_impact"],
                "preferred_evidence_types": ["named_systems", "metrics"],
                "preferred_header_bias": ["credibility_first"],
                "title_match_preference": "moderate",
                "keyword_bias": "medium",
                "ai_section_preference": "dedicated_if_core",
                "preferred_tone": ["clear"],
                "evidence_basis": "Public professional signals.",
                "confidence": {"score": 0.7, "band": "medium", "basis": "signals"},
            },
            "likely_priorities": [{"bullet": "Proof of shipped systems.", "basis": "signals", "source_ids": ["src_mgr"]}],
            "likely_reject_signals": [{"bullet": "Generic AI claims with no ownership.", "reason": "signals", "source_ids": ["src_mgr"]}],
            "unresolved_markers": [],
            "sources": [],
            "evidence": [],
            "confidence": {"score": 0.74, "band": "medium", "basis": "signals"},
        },
        personas_payload={
            "inferred_stakeholder_personas": [
                {
                    "persona_id": "persona_peer_technical_1",
                    "persona_type": "peer_technical",
                    "role_in_process": "technical_depth_and_execution_screen",
                    "emitted_because": "coverage_gap_despite_real",
                    "trigger_basis": ["senior_engineer", "peer_technical_coverage_gap"],
                    "coverage_gap": "peer_technical",
                    "public_professional_decision_style": {"evidence_preference": "metrics_and_systems"},
                    "cv_preference_surface": {
                        "review_objectives": ["Verify hands-on implementation"],
                        "preferred_signal_order": ["hands_on_implementation"],
                        "preferred_evidence_types": ["named_systems"],
                        "preferred_header_bias": ["credibility_first"],
                        "title_match_preference": "moderate",
                        "keyword_bias": "medium",
                        "ai_section_preference": "dedicated_if_core",
                        "preferred_tone": ["clear"],
                        "evidence_basis": "Inferred from role class.",
                        "confidence": {"score": 0.62, "band": "medium", "basis": "inferred"},
                    },
                    "likely_priorities": [{"bullet": "Proof of hands-on systems work.", "basis": "inferred", "source_ids": []}],
                    "likely_reject_signals": [{"bullet": "Tool-list CV without shipped systems.", "reason": "inferred", "source_ids": []}],
                    "unresolved_markers": [],
                    "evidence_basis": "This is inferred from role class and coverage gap.",
                    "sources": [],
                    "evidence": [],
                    "confidence": {"score": 0.62, "band": "medium", "basis": "inferred"},
                }
            ],
            "unresolved_markers": [],
            "notes": [],
        },
    )
    result = StakeholderSurfaceStage().run(_context(include_seed=False))
    assert result.stage_output["status"] == "completed"
    assert result.stage_output["real_stakeholders"][0]["stakeholder_type"] == "hiring_manager"
    assert result.stage_output["real_stakeholders"][0]["cv_preference_surface"]["preferred_signal_order"] == ["hands_on_implementation", "production_impact"]
    assert any(item["status"] == "real" and item["role"] == "hiring_manager" for item in result.stage_output["evaluator_coverage"])
    assert any(item["status"] == "inferred" and item["role"] == "peer_technical" for item in result.stage_output["evaluator_coverage"])


def test_no_hiring_manager_found_emits_inferred_hiring_manager_persona(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", "true")
    _mock_transport(
        monkeypatch,
        discovery_payload={
            "stakeholder_intelligence": [],
            "search_journal": [{"step": "discovery", "query": "site:acme.example.com hiring manager", "intent": "find_hiring_manager", "source_type": "company_site", "outcome": "miss", "source_ids": [], "notes": ""}],
            "unresolved_markers": ["no_medium_high_candidates"],
            "notes": [],
        },
        personas_payload={"inferred_stakeholder_personas": [], "unresolved_markers": [], "notes": []},
    )
    result = StakeholderSurfaceStage().run(_context())
    assert result.stage_output["status"] == "inferred_only"
    assert any(item["coverage_gap"] == "hiring_manager" for item in result.stage_output["inferred_stakeholder_personas"])


def test_search_journal_outcome_drift_is_normalized(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", "true")
    _mock_transport(
        monkeypatch,
        discovery_payload={
            "stakeholder_intelligence": [],
            "search_journal": [
                {
                    "step": "discovery",
                    "query": "site:acme.example.com engineering manager",
                    "intent": "find_hiring_manager",
                    "source_type": "company_site",
                    "outcome": "hit_but_no_named_people",
                    "source_ids": ["src_team"],
                    "notes": "Relevant team page found but no named stakeholders observed.",
                }
            ],
            "unresolved_markers": ["no_named_people_found"],
            "notes": [],
        },
        personas_payload={"inferred_stakeholder_personas": [], "unresolved_markers": [], "notes": []},
    )
    result = StakeholderSurfaceStage().run(_context())
    assert result.stage_output["status"] == "inferred_only"
    assert result.stage_output["search_journal"][1]["outcome"] == "miss"
    assert "no named stakeholders observed" in (result.stage_output["search_journal"][1]["notes"] or "").lower()


def test_ambiguous_cross_company_match_is_rejected(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", "true")
    _mock_transport(
        monkeypatch,
        discovery_payload={
            "stakeholder_intelligence": [
                {
                    "stakeholder_type": "hiring_manager",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.84, "band": "high", "basis": "official team page plus public profile"},
                    "identity_basis": "Official team page and public profile.",
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                    "candidate_rank": 1,
                    "name": "Jordan Smith",
                    "current_title": "Engineering Manager",
                    "current_company": "OtherCo",
                    "profile_url": "https://www.linkedin.com/in/jordan-smith-otherco",
                    "source_trail": ["src_mgr"],
                    "sources": [{"source_id": "src_mgr", "url": "https://www.linkedin.com/in/jordan-smith-otherco", "source_type": "public_professional_profile", "fetched_at": "2026-04-21", "trust_tier": "secondary"}],
                    "evidence": [{"claim": "Jordan Smith is an engineering manager.", "source_ids": ["src_mgr"]}],
                }
            ],
            "search_journal": [],
            "unresolved_markers": [],
            "notes": [],
        },
        personas_payload={"inferred_stakeholder_personas": [], "unresolved_markers": [], "notes": []},
    )
    result = StakeholderSurfaceStage().run(_context())
    assert result.stage_output["real_stakeholders"] == []
    assert any("Real stakeholder discovery failed" in note for note in result.stage_output["unresolved_questions"])


def test_constructed_profile_url_is_rejected(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", "true")
    _mock_transport(
        monkeypatch,
        discovery_payload={
            "stakeholder_intelligence": [
                {
                    "stakeholder_type": "hiring_manager",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.84, "band": "high", "basis": "official team page plus public profile"},
                    "identity_basis": "Official team page and public profile.",
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                    "candidate_rank": 1,
                    "name": "Jordan Smith",
                    "current_title": "Engineering Manager",
                    "current_company": "Acme",
                    "profile_url": "https://www.linkedin.com/in/jordan-smith",
                    "source_trail": ["src_mgr"],
                    "sources": [{"source_id": "src_mgr", "url": "https://www.linkedin.com/in/jordan-smith", "source_type": "public_professional_profile", "fetched_at": "2026-04-21", "trust_tier": "secondary"}],
                    "evidence": [{"claim": "Jordan Smith is an engineering manager.", "source_ids": ["src_mgr"]}],
                }
            ],
            "search_journal": [],
            "unresolved_markers": [],
            "notes": [],
        },
        personas_payload={"inferred_stakeholder_personas": [], "unresolved_markers": [], "notes": []},
    )
    result = StakeholderSurfaceStage().run(_context())
    assert result.stage_output["real_stakeholders"] == []
    assert any("Real stakeholder discovery failed" in note for note in result.stage_output["unresolved_questions"])


def test_partial_profile_enrichment_keeps_identity_and_does_not_mutate_seed(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", "true")
    _mock_transport(
        monkeypatch,
        discovery_payload={
            "stakeholder_intelligence": [
                {
                    "stakeholder_type": "hiring_manager",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.84, "band": "high", "basis": "official team page plus public profile"},
                    "identity_basis": "Official team page and public profile.",
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                    "candidate_rank": 1,
                    "name": "Jordan Smith",
                    "current_title": "Engineering Manager",
                    "current_company": "Acme",
                    "profile_url": "https://www.linkedin.com/in/jordan-smith-acme",
                    "source_trail": ["src_mgr"],
                    "sources": [{"source_id": "src_mgr", "url": "https://www.linkedin.com/in/jordan-smith-acme", "source_type": "public_professional_profile", "fetched_at": "2026-04-21", "trust_tier": "secondary"}],
                    "evidence": [{"claim": "Jordan Smith is an engineering manager.", "source_ids": ["src_mgr"]}],
                }
            ],
            "search_journal": [],
            "unresolved_markers": [],
            "notes": [],
        },
        profile_payload=None,
        personas_payload={"inferred_stakeholder_personas": [], "unresolved_markers": [], "notes": []},
    )
    ctx = _context()
    original_seed = copy.deepcopy(ctx.job_doc["pre_enrichment"]["outputs"]["research_enrichment"]["stakeholder_intelligence"])
    result = StakeholderSurfaceStage().run(ctx)
    assert result.stage_output["real_stakeholders"][0]["status"] == "identity_only"
    assert ctx.job_doc["pre_enrichment"]["outputs"]["research_enrichment"]["stakeholder_intelligence"] == original_seed
