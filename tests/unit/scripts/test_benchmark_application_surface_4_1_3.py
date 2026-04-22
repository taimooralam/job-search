from __future__ import annotations

from scripts.benchmark_application_surface_4_1_3 import compare_application_surface, run_benchmark


def _gold() -> dict:
    return {
        "canonical_application_url": "https://www.robsonbale.com/jobs/",
        "portal_family": "custom_unknown",
        "resolution_status": "partial",
        "stale_signal": "unknown",
        "closed_signal": "unknown",
    }


def _candidate() -> dict:
    return {
        "status": "partial",
        "job_url": "https://linkedin.com/jobs/view/4401620360",
        "canonical_application_url": "https://www.robsonbale.com/jobs/",
        "resolution_status": "partial",
        "portal_family": "custom_unknown",
        "stale_signal": "unknown",
        "closed_signal": "unknown",
        "sources": [{"source_id": "s1", "source_type": "official_company_site", "trust_tier": "primary"}],
        "evidence": [{"claim": "Employer jobs portal observed", "source_ids": ["s1"]}],
        "confidence": {"score": 0.72, "band": "medium", "basis": "verified employer jobs portal"},
    }


def test_compare_application_surface_reports_schema_failure():
    comparison = compare_application_surface(_gold(), {"status": "partial", "sources": [{}]})
    assert comparison["schema_valid"] is False


def test_run_benchmark_passes_with_fixture_candidate():
    rows, summary = run_benchmark(
        [
            {
                "job_id": "job-1",
                "gold_application_surface": _gold(),
                "candidate_application_surface": _candidate(),
            }
        ],
        use_fixture_candidate=True,
    )
    assert len(rows) == 1
    assert summary["schema_validity_pass_rate"] == 1.0
    assert summary["passes_thresholds"] is True
