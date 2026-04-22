from __future__ import annotations

from scripts.benchmark_company_role_enrichment_4_1_3 import (
    compare_company_role_enrichment,
    run_benchmark,
)


def _gold() -> dict:
    return {
        "status": "partial",
        "company_profile": {
            "summary": "Robson Bale is a specialist AI and data recruitment firm.",
            "canonical_name": "Robson Bale",
            "canonical_domain": "robsonbale.com",
            "canonical_url": "https://www.robsonbale.com",
        },
        "role_profile": {
            "summary": "Lead AI Engineer role spanning architecture, delivery, and mentoring.",
            "role_summary": "Lead AI Engineer role spanning architecture, delivery, and mentoring.",
            "why_now": "The firm is expanding AI delivery capacity.",
            "company_context_alignment": "The role supports the firm's AI hiring and delivery practice.",
        },
    }


def _candidate() -> dict:
    return {
        "status": "partial",
        "company_profile": {
            "summary": "Robson Bale is a specialist AI and data recruitment firm.",
            "canonical_name": {"text": "Robson Bale"},
            "canonical_domain": {"value": "robsonbale.com"},
            "canonical_url": {"value": "https://www.robsonbale.com"},
            "signals": [
                {
                    "name": "growth",
                    "value": "Active AI hiring across multiple clients.",
                    "confidence": {"score": 0.6, "band": "medium", "basis": "observed"},
                }
            ],
            "sources": [{"source_id": "s1", "source_type": "official_company_site", "trust_tier": "primary"}],
            "evidence": [{"claim": "Company identity confirmed", "source_ids": ["s1"]}],
        },
        "role_profile": {
            "summary": {"text": "Lead AI Engineer role spanning architecture, delivery, and mentoring."},
            "role_summary": {"text": "Lead AI Engineer role spanning architecture, delivery, and mentoring."},
            "why_now": {"text": "The firm is expanding AI delivery capacity."},
            "company_context_alignment": {"text": "The role supports the firm's AI hiring and delivery practice."},
            "sources": [{"source_id": "s2", "source_type": "job_document", "trust_tier": "primary"}],
            "evidence": [{"claim": "Role summary grounded in JD and public company context", "source_ids": ["s2"]}],
        },
    }


def test_compare_company_role_enrichment_reports_schema_failure():
    comparison = compare_company_role_enrichment(
        _gold(),
        {
            "company_profile": {"sources": [{}]},
            "role_profile": {},
        },
    )
    assert comparison["schema_valid"] is False


def test_run_benchmark_passes_with_fixture_candidate():
    rows, summary = run_benchmark(
        [
            {
                "job_id": "job-1",
                "gold_research_enrichment": _gold(),
                "candidate_research_enrichment": _candidate(),
            }
        ]
    )
    assert len(rows) == 1
    assert summary["schema_validity_pass_rate"] == 1.0
    assert summary["company_identity_accuracy"] == 1.0
    assert summary["role_summary_factuality"] == 1.0
    assert summary["passes_thresholds"] is True
