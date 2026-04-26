from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preenrich.blueprint_config import current_git_sha, research_prompt_file_path
from src.preenrich.blueprint_models import (
    ApplicationProfile,
    CompanyProfile,
    RoleProfile,
    normalize_company_profile_payload,
    normalize_role_profile_payload,
)

DEFAULT_THRESHOLDS = {
    "company_profile_factuality": 0.95,
    "role_profile_factuality": 0.90,
    "canonical_application_url_exact_match": 0.90,
    "portal_family_accuracy": 0.95,
    "stakeholder_precision_medium_high": 0.85,
    "source_attributed_claim_coverage": 0.95,
    "speculative_privacy_violations": 0.0,
    "unresolved_handling_correctness": 0.90,
    "reviewer_usefulness": 0.80,
    "outreach_guidance_actionability": 0.80,
}


def load_corpus(corpus_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(corpus_dir)
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            items.append(json.load(handle))
    return items


def _score_match(expected: Any, actual: Any) -> float:
    if expected in (None, "", [], {}):
        return 1.0 if actual in (None, "", [], {}) else 0.0
    return 1.0 if expected == actual else 0.0


def _normalize_candidate_company_profile(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return CompanyProfile.model_validate(normalize_company_profile_payload(payload)).model_dump()
    except Exception:
        return payload


def _normalize_candidate_role_profile(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return RoleProfile.model_validate(normalize_role_profile_payload(payload)).model_dump()
    except Exception:
        return payload


def _normalize_candidate_application_profile(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return ApplicationProfile.model_validate(payload).model_dump()
    except Exception:
        return payload


def _normalize_candidate_research_enrichment(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(candidate or {})
    normalized["company_profile"] = _normalize_candidate_company_profile(dict(normalized.get("company_profile") or {}))
    normalized["role_profile"] = _normalize_candidate_role_profile(dict(normalized.get("role_profile") or {}))
    normalized["application_profile"] = _normalize_candidate_application_profile(dict(normalized.get("application_profile") or {}))
    return normalized


def compare_research_artifacts(gold: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    candidate = _normalize_candidate_research_enrichment(candidate)
    gold_company = gold.get("company_profile") or {}
    cand_company = candidate.get("company_profile") or {}
    gold_role = gold.get("role_profile") or {}
    cand_role = candidate.get("role_profile") or {}
    gold_app = gold.get("application_profile") or {}
    cand_app = candidate.get("application_profile") or {}
    gold_stakeholders = [
        item for item in (gold.get("stakeholder_intelligence") or [])
        if ((item.get("identity_confidence") or {}).get("band") in {"medium", "high"})
    ]
    cand_stakeholders = [
        item for item in (candidate.get("stakeholder_intelligence") or [])
        if ((item.get("identity_confidence") or {}).get("band") in {"medium", "high"})
    ]
    attributed_claims = 0
    attributed_hits = 0
    for subdoc in (cand_company, cand_role, cand_app):
        for evidence in subdoc.get("evidence") or []:
            attributed_claims += 1
            if evidence.get("source_ids"):
                attributed_hits += 1
    speculative_flags = 0.0
    for stakeholder in cand_stakeholders:
        if stakeholder.get("profile_url") and str(stakeholder.get("profile_url")).endswith("/in/"):
            speculative_flags += 1.0
    return {
        "company_profile_factuality": _score_match(gold_company.get("summary"), cand_company.get("summary")),
        "role_profile_factuality": _score_match(gold_role.get("summary") or gold_role.get("role_summary"), cand_role.get("summary") or cand_role.get("role_summary")),
        "canonical_application_url_exact_match": _score_match(
            gold_app.get("canonical_application_url"),
            cand_app.get("canonical_application_url"),
        ),
        "portal_family_accuracy": _score_match(gold_app.get("portal_family"), cand_app.get("portal_family")),
        "stakeholder_precision_medium_high": 1.0
        if not cand_stakeholders
        else min(1.0, len([s for s in cand_stakeholders if s.get("name") in {g.get("name") for g in gold_stakeholders}]) / len(cand_stakeholders)),
        "source_attributed_claim_coverage": 1.0 if attributed_claims == 0 else attributed_hits / attributed_claims,
        "speculative_privacy_violations": speculative_flags,
        "unresolved_handling_correctness": 1.0
        if gold.get("status") == candidate.get("status")
        else 0.0,
        "reviewer_usefulness": 1.0 if candidate.get("company_profile") and candidate.get("role_profile") and candidate.get("application_profile") else 0.0,
        "outreach_guidance_actionability": 1.0
        if not cand_stakeholders
        else min(
            1.0,
            len(
                [
                    s for s in cand_stakeholders
                    if (s.get("initial_outreach_guidance") or {}).get("initial_cold_interaction_guidance")
                ]
            )
            / len(cand_stakeholders),
        ),
    }


def build_run_metadata(
    *,
    prompt_version: str,
    provider: str,
    model: str | None,
    transport_used: str,
) -> dict[str, Any]:
    return {
        "prompt_id": "research_enrichment_bundle",
        "prompt_version": prompt_version,
        "prompt_file_path": research_prompt_file_path(),
        "git_sha": current_git_sha(),
        "provider": provider,
        "model": model,
        "transport_used": transport_used,
    }


def build_model_matrix(models: list[str] | None = None) -> list[dict[str, str]]:
    selected = models or ["gpt-5.3", "gpt-5.2", "gpt-5.4-mini"]
    return [{"provider": "codex", "model": model, "transport": "codex_web_search"} for model in selected]


def aggregate_scores(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {key: 0.0 for key in DEFAULT_THRESHOLDS}
    totals = {key: 0.0 for key in DEFAULT_THRESHOLDS}
    for row in rows:
        for key in totals:
            totals[key] += float(row["scores"].get(key, 0.0))
    return {key: totals[key] / len(rows) for key in totals}


def enforce_thresholds(summary: dict[str, Any], thresholds: dict[str, float] | None = None) -> bool:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    scores = summary.get("aggregate_scores") or {}
    for key, threshold in thresholds.items():
        value = float(scores.get(key, 0.0))
        if key == "speculative_privacy_violations":
            if value > threshold:
                return False
        elif value < threshold:
            return False
    return True


def run_benchmark(
    corpus: list[dict[str, Any]],
    *,
    use_fixture_candidate: bool = False,
    no_write: bool = True,
    metadata: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in corpus:
        gold = item.get("gold_research_enrichment") or {}
        candidate = (
            item.get("candidate_research_enrichment")
            if use_fixture_candidate
            else item.get("candidate_research_enrichment") or {}
        )
        scores = compare_research_artifacts(gold, candidate)
        rows.append(
            {
                "job_id": item.get("job_id") or item.get("_id"),
                "scores": scores,
                "status": candidate.get("status"),
                "write_attempted": False if no_write else bool(item.get("write_attempted")),
                "metadata": metadata or {},
            }
        )

    aggregate = aggregate_scores(rows)
    summary = {
        "count": len(rows),
        "no_write": no_write,
        "metadata": metadata or {},
        "aggregate_scores": aggregate,
        "passes_thresholds": enforce_thresholds({"aggregate_scores": aggregate}),
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Iteration 4.1.3 research_enrichment outputs.")
    parser.add_argument("--corpus-dir", default="tests/fixtures/research_enrichment_benchmark")
    parser.add_argument("--no-write", action="store_true", default=False)
    parser.add_argument("--use-fixture-candidate", action="store_true", default=False)
    parser.add_argument("--prompt-version", default="research_enrichment_bundle@v4.1.3.1")
    parser.add_argument("--provider", default="codex")
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--transport", default="none")
    args = parser.parse_args()

    corpus = load_corpus(args.corpus_dir)
    metadata = build_run_metadata(
        prompt_version=args.prompt_version,
        provider=args.provider,
        model=args.model,
        transport_used=args.transport,
    )
    rows, summary = run_benchmark(
        corpus,
        use_fixture_candidate=args.use_fixture_candidate,
        no_write=args.no_write,
        metadata=metadata,
    )
    print(json.dumps({"rows": rows, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
