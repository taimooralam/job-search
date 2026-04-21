"""Safe local benchmark harness for stakeholder_surface 4.2.1."""

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

from src.preenrich.blueprint_models import StakeholderSurfaceDoc


def _normalize_real_identities(surface: StakeholderSurfaceDoc) -> set[tuple[str, str, str]]:
    rows: set[tuple[str, str, str]] = set()
    for item in surface.real_stakeholders:
        snapshot = item.stakeholder_record_snapshot
        rows.add(
            (
                item.stakeholder_type,
                (snapshot.name or "").strip().lower(),
                (snapshot.profile_url or "").strip().lower(),
            )
        )
    return rows


def _normalize_persona_types(surface: StakeholderSurfaceDoc) -> set[str]:
    return {item.coverage_gap for item in surface.inferred_stakeholder_personas}


def _has_useful_preference_signals(surface: StakeholderSurfaceDoc) -> bool:
    def _surface_useful(payload: Any) -> bool:
        if payload is None:
            return False
        return bool(payload.review_objectives or payload.preferred_signal_order)

    for item in surface.real_stakeholders:
        if _surface_useful(item.cv_preference_surface):
            return True
    for item in surface.inferred_stakeholder_personas:
        if _surface_useful(item.cv_preference_surface):
            return True
    return False


def compare_stakeholder_surface(row: dict[str, Any]) -> dict[str, Any]:
    candidate_payload = row["candidate_stakeholder_surface"]
    gold_payload = row["gold_stakeholder_surface"]
    result: dict[str, Any] = {"job_id": row.get("job_id") or "unknown"}
    try:
        candidate = StakeholderSurfaceDoc.model_validate(candidate_payload)
        gold = StakeholderSurfaceDoc.model_validate(gold_payload)
        result["schema_valid"] = True
    except Exception as exc:
        result["schema_valid"] = False
        result["error"] = str(exc)
        return result

    candidate_real = _normalize_real_identities(candidate)
    gold_real = _normalize_real_identities(gold)
    candidate_personas = _normalize_persona_types(candidate)
    gold_personas = _normalize_persona_types(gold)
    expect_ambiguous_rejection = bool(row.get("expect_ambiguous_rejection"))

    result.update(
        {
            "status_match": candidate.status == gold.status,
            "real_identity_precision": candidate_real.issubset(gold_real) if candidate_real else (not gold_real or True),
            "inferred_persona_fallback_correct": candidate_personas == gold_personas,
            "ambiguous_rejection_correct": (
                not expect_ambiguous_rejection
                or (not candidate.real_stakeholders and any(item.outcome == "rejected_fabrication" or item.outcome == "ambiguous" for item in candidate.search_journal))
            ),
            "safety_privacy_clean": all(
                not any(key in item.model_dump() for key in ("name", "profile_url", "current_title", "current_company"))
                and item.confidence.band in {"medium", "low", "unresolved"}
                for item in candidate.inferred_stakeholder_personas
            ),
            "resolved_vs_inferred_labeling_correct": not (
                {item.stakeholder_ref for item in candidate.real_stakeholders}
                & {ref for entry in candidate.evaluator_coverage for ref in entry.persona_refs}
            ),
            "cv_preference_useful": _has_useful_preference_signals(candidate),
        }
    )
    return result


def run_benchmark(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report = [compare_stakeholder_surface(row) for row in rows]

    def _mean(field: str) -> float:
        values = [1.0 if item.get(field) else 0.0 for item in report if item.get("schema_valid")]
        return mean(values) if values else 0.0

    schema_values = [1.0 if item.get("schema_valid") else 0.0 for item in report]
    summary = {
        "schema_validity_pass_rate": mean(schema_values) if schema_values else 0.0,
        "real_stakeholder_precision": _mean("real_identity_precision"),
        "inferred_persona_fallback_accuracy": _mean("inferred_persona_fallback_correct"),
        "ambiguous_identity_rejection_accuracy": _mean("ambiguous_rejection_correct"),
        "safety_privacy_clean_rate": _mean("safety_privacy_clean"),
        "resolved_vs_inferred_labeling_accuracy": _mean("resolved_vs_inferred_labeling_correct"),
        "cv_preference_usefulness": _mean("cv_preference_useful"),
        "passes_thresholds": (
            (mean(schema_values) if schema_values else 0.0) >= 1.0
            and _mean("real_identity_precision") >= 0.85
            and _mean("inferred_persona_fallback_correct") >= 0.8
            and _mean("ambiguous_rejection_correct") >= 1.0
            and _mean("safety_privacy_clean") >= 1.0
            and _mean("resolved_vs_inferred_labeling_correct") >= 1.0
            and _mean("cv_preference_useful") >= 0.8
        ),
    }
    return report, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="evals/stakeholder_surface_4_2_1/stakeholder_surface_cases.json")
    parser.add_argument("--report-out", default="")
    args = parser.parse_args()

    rows = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    report, summary = run_benchmark(rows)
    payload = {"rows": report, "summary": summary}
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
