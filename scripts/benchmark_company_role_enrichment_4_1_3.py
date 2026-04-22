"""Safe local benchmark harness for company/role enrichment 4.1.3."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preenrich.blueprint_models import (
    CompanyProfile,
    RoleProfile,
    normalize_company_profile_payload,
    normalize_role_profile_payload,
)


def _string_match(expected: Any, actual: Any) -> float:
    expected_text = str(expected or "").strip()
    actual_text = str(actual or "").strip()
    if not expected_text and not actual_text:
        return 1.0
    return 1.0 if expected_text == actual_text else 0.0


def _has_rich_company_detail(profile: CompanyProfile) -> bool:
    return bool(
        profile.identity_detail
        or profile.mission_detail
        or profile.product_detail
        or profile.business_model_detail
        or profile.signals_rich
        or profile.recent_signals_rich
        or profile.role_relevant_signals_rich
    )


def _has_rich_role_detail(profile: RoleProfile) -> bool:
    return bool(
        profile.summary_detail
        or profile.role_summary_detail
        or profile.why_now_detail
        or profile.company_context_alignment_detail
    )


def compare_company_role_enrichment(gold: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    try:
        company = CompanyProfile.model_validate(
            normalize_company_profile_payload(candidate.get("company_profile"))
        )
        role = RoleProfile.model_validate(
            normalize_role_profile_payload(candidate.get("role_profile"))
        )
        row["schema_valid"] = True
    except Exception as exc:
        row["schema_valid"] = False
        row["error"] = str(exc)
        return row

    gold_company = gold.get("company_profile") or {}
    gold_role = gold.get("role_profile") or {}

    company_identity_correct = any(
        (
            company.canonical_domain and company.canonical_domain == gold_company.get("canonical_domain"),
            company.canonical_name and company.canonical_name == gold_company.get("canonical_name"),
            company.canonical_url and company.canonical_url == gold_company.get("canonical_url"),
        )
    )
    role_summary_actual = company_role_summary = role.summary or role.role_summary
    role_summary_gold = gold_role.get("summary") or gold_role.get("role_summary")
    company_summary_gold = gold_company.get("summary")
    status_gold = gold.get("status") or "partial"
    status_actual = candidate.get("status") or "partial"

    row.update(
        {
            "company_identity_correct": company_identity_correct,
            "company_summary_match": _string_match(company_summary_gold, company.summary) == 1.0,
            "role_summary_match": _string_match(role_summary_gold, role_summary_actual) == 1.0,
            "why_now_match": _string_match(gold_role.get("why_now"), role.why_now) == 1.0,
            "company_context_alignment_match": _string_match(
                gold_role.get("company_context_alignment"),
                role.company_context_alignment,
            )
            == 1.0,
            "source_preserved": bool(company.sources or role.sources),
            "evidence_preserved": bool(company.evidence or role.evidence),
            "richness_retained": _has_rich_company_detail(company) or _has_rich_role_detail(role),
            "compact_aliases_available": bool(company.summary and (role.summary or role.role_summary)),
            "status_match": status_actual == status_gold,
            "company_status": company.status,
            "role_status": role.status,
        }
    )
    return row


def run_benchmark(rows: list[dict[str, Any]], *, use_fixture_candidate: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for row in rows:
        gold = row["gold_research_enrichment"]
        candidate = row["candidate_research_enrichment"] if use_fixture_candidate else row.get("candidate_research_enrichment", {})
        comparison = compare_company_role_enrichment(gold, candidate)
        comparison["job_id"] = row.get("job_id") or str(row.get("_id") or "unknown")
        report.append(comparison)

    def _mean(field: str) -> float:
        values = [1.0 if item.get(field) else 0.0 for item in report if item.get("schema_valid")]
        return mean(values) if values else 0.0

    schema_values = [1.0 if item.get("schema_valid") else 0.0 for item in report]
    summary = {
        "schema_validity_pass_rate": mean(schema_values) if schema_values else 0.0,
        "company_identity_accuracy": _mean("company_identity_correct"),
        "company_summary_factuality": _mean("company_summary_match"),
        "role_summary_factuality": _mean("role_summary_match"),
        "why_now_correctness": _mean("why_now_match"),
        "role_company_alignment_usefulness": _mean("company_context_alignment_match"),
        "source_preservation_rate": _mean("source_preserved"),
        "evidence_preservation_rate": _mean("evidence_preserved"),
        "richness_retention_score": _mean("richness_retained"),
        "compact_alias_availability": _mean("compact_aliases_available"),
        "unresolved_handling_correctness": _mean("status_match"),
        "passes_thresholds": (
            (mean(schema_values) if schema_values else 0.0) >= 1.0
            and _mean("company_identity_correct") >= 0.9
            and _mean("role_summary_match") >= 0.9
            and _mean("source_preserved") >= 0.9
            and _mean("evidence_preserved") >= 0.9
        ),
    }
    return report, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default="tests/fixtures/research_enrichment_benchmark")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report-out", default="")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for path in sorted(Path(args.corpus_dir).glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    if args.limit:
        rows = rows[: args.limit]
    report, summary = run_benchmark(rows)
    payload = {"rows": report, "summary": summary}
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
