from __future__ import annotations

from scripts.benchmark_stakeholder_surface_4_2_1 import compare_stakeholder_surface, run_benchmark


def _gold() -> dict:
    return {
        "job_id": "job-1",
        "level2_job_id": "job-1",
        "research_enrichment_id": "__ref__:research_enrichment.id",
        "prompt_versions": {"discovery": "P-stakeholder-discovery@v2"},
        "prompt_metadata": {},
        "status": "completed",
        "capability_flags": {"real_discovery_enabled": True},
        "evaluator_coverage_target": ["recruiter", "hiring_manager"],
        "evaluator_coverage": [
            {
                "role": "recruiter",
                "required": True,
                "status": "real",
                "stakeholder_refs": ["candidate_rank:1"],
                "persona_refs": [],
                "coverage_confidence": {"score": 0.9, "band": "high", "basis": "real"},
            },
            {
                "role": "hiring_manager",
                "required": True,
                "status": "inferred",
                "stakeholder_refs": [],
                "persona_refs": ["persona_hiring_manager_1"],
                "coverage_confidence": {"score": 0.6, "band": "medium", "basis": "inferred"},
            },
        ],
        "real_stakeholders": [
            {
                "stakeholder_ref": "candidate_rank:1",
                "stakeholder_record_snapshot": {
                    "stakeholder_type": "recruiter",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.82, "band": "high", "basis": "official"},
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                    "candidate_rank": 1,
                    "name": "Jane Doe",
                    "current_title": "Technical Recruiter",
                    "current_company": "Acme",
                    "profile_url": "https://www.linkedin.com/in/jane-doe-acme",
                    "source_trail": ["src1"],
                    "sources": [{"source_id": "src1", "url": "https://www.linkedin.com/in/jane-doe-acme", "source_type": "public_professional_profile", "trust_tier": "secondary"}],
                    "evidence": [{"claim": "Jane Doe is a recruiter.", "source_ids": ["src1"]}],
                },
                "stakeholder_type": "recruiter",
                "role_in_process": "screening_and_process_control",
                "cv_preference_surface": {
                    "review_objectives": ["Verify credible fit"],
                    "preferred_signal_order": ["ownership_scope"],
                    "preferred_evidence_types": ["metrics"],
                    "preferred_header_bias": ["credibility_first"],
                    "title_match_preference": "moderate",
                    "keyword_bias": "medium",
                    "ai_section_preference": "embedded_only",
                    "preferred_tone": ["clear"],
                    "evidence_basis": "signals",
                    "confidence": {"score": 0.7, "band": "medium", "basis": "signals"},
                },
                "likely_priorities": [],
                "likely_reject_signals": [],
                "sources": [{"source_id": "src1", "url": "https://www.linkedin.com/in/jane-doe-acme", "source_type": "public_professional_profile", "trust_tier": "secondary"}],
                "evidence": [{"claim": "Jane Doe is a recruiter.", "source_ids": ["src1"]}],
                "confidence": {"score": 0.8, "band": "high", "basis": "signals"},
                "status": "completed",
            }
        ],
        "inferred_stakeholder_personas": [
            {
                "persona_id": "persona_hiring_manager_1",
                "persona_type": "hiring_manager",
                "coverage_gap": "hiring_manager",
                "evidence_basis": "This is inferred from role class.",
                "confidence": {"score": 0.6, "band": "medium", "basis": "inferred"},
            }
        ],
        "search_journal": [],
        "sources": [],
        "evidence": [],
        "confidence": {"score": 0.72, "band": "medium", "basis": "aggregate"},
        "unresolved_questions": [],
        "notes": [],
    }


def test_compare_stakeholder_surface_reports_schema_failure():
    result = compare_stakeholder_surface(
        {
            "job_id": "job-1",
            "gold_stakeholder_surface": _gold(),
            "candidate_stakeholder_surface": {"status": "completed"},
        }
    )
    assert result["schema_valid"] is False


def test_run_benchmark_passes_for_good_candidate():
    rows, summary = run_benchmark(
        [
            {
                "job_id": "job-1",
                "gold_stakeholder_surface": _gold(),
                "candidate_stakeholder_surface": _gold(),
                "expect_ambiguous_rejection": False,
            }
        ]
    )
    assert len(rows) == 1
    assert summary["schema_validity_pass_rate"] == 1.0
    assert summary["real_stakeholder_precision"] == 1.0
    assert summary["passes_thresholds"] is True
