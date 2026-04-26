from __future__ import annotations

from pathlib import Path

from scripts.benchmark_research_enrichment_4_1_3 import (
    build_model_matrix,
    build_run_metadata,
    enforce_thresholds,
    load_corpus,
    run_benchmark,
)


def test_load_corpus_reads_fixture_directory():
    corpus = load_corpus(Path("tests/fixtures/research_enrichment_benchmark"))
    assert corpus
    assert {row["job_id"] for row in corpus} >= {"bench-job-1", "69e63f7e12725d7147cc499c"}


def test_run_benchmark_no_write_mode_uses_fixture_candidate():
    corpus = load_corpus(Path("tests/fixtures/research_enrichment_benchmark"))
    rows, summary = run_benchmark(corpus, use_fixture_candidate=True, no_write=True)
    assert rows[0]["write_attempted"] is False
    assert summary["no_write"] is True
    assert summary["passes_thresholds"] is True


def test_enforce_thresholds_fails_on_speculative_violations():
    summary = {
        "aggregate_scores": {
            "company_profile_factuality": 1.0,
            "role_profile_factuality": 1.0,
            "canonical_application_url_exact_match": 1.0,
            "portal_family_accuracy": 1.0,
            "stakeholder_precision_medium_high": 1.0,
            "source_attributed_claim_coverage": 1.0,
            "speculative_privacy_violations": 1.0,
            "unresolved_handling_correctness": 1.0,
            "reviewer_usefulness": 1.0,
            "outreach_guidance_actionability": 1.0,
        }
    }
    assert enforce_thresholds(summary) is False


def test_build_run_metadata_persists_prompt_and_transport_fields():
    metadata = build_run_metadata(
        prompt_version="research_enrichment_bundle@v4.1.3.1",
        provider="codex",
        model="gpt-5.4-mini",
        transport_used="none",
    )
    assert metadata["prompt_file_path"].replace("\\", "/").endswith("src/preenrich/blueprint_prompts.py")
    assert metadata["transport_used"] == "none"
    assert metadata["prompt_version"] == "research_enrichment_bundle@v4.1.3.1"


def test_build_model_matrix_defaults_to_codex_research_candidates():
    matrix = build_model_matrix()
    assert [item["model"] for item in matrix] == ["gpt-5.3", "gpt-5.2", "gpt-5.4-mini"]
