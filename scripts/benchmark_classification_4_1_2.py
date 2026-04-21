"""Safe local benchmark harness for classification 4.1.2."""

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

from src.preenrich.blueprint_models import ClassificationDoc
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.types import StageContext, StepConfig


def compare_classifications(gold: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    try:
        parsed = ClassificationDoc.model_validate(candidate)
        row["schema_valid"] = True
    except Exception as exc:
        row["schema_valid"] = False
        row["error"] = str(exc)
        return row

    gold_primary = gold.get("primary_role_category")
    candidate_primary = parsed.primary_role_category.value if hasattr(parsed.primary_role_category, "value") else parsed.primary_role_category
    top2 = [candidate_primary] + list(parsed.secondary_role_categories or [])
    gold_ambiguous = bool(gold.get("ambiguous"))
    candidate_ambiguous = parsed.ambiguity_score >= 0.35 or len(parsed.secondary_role_categories) > 0

    gold_ai = gold.get("ai_taxonomy") or {}
    candidate_ai = parsed.ai_taxonomy.model_dump()

    row.update(
        {
            "primary_exact_match": candidate_primary == gold_primary,
            "top2_recall": gold_primary in top2,
            "ambiguity_match": candidate_ambiguous == gold_ambiguous,
            "jd_facts_agreement_match": bool((gold.get("jd_facts_agreement") or {}).get("agrees")) == parsed.jd_facts_agreement.agrees,
            "ai_primary_exact_match": (candidate_ai.get("primary_specialization") or "none") == (gold_ai.get("primary_specialization") or "none"),
            "ai_intensity_exact_match": candidate_ai.get("intensity") == gold_ai.get("intensity"),
            "deterministic_skip": str(parsed.decision_path).startswith("deterministic"),
            "duration_ms": int(candidate.get("duration_ms") or 0),
        }
    )
    return row


def _run_stage(job: dict[str, Any], *, model: str) -> dict[str, Any]:
    ctx = StageContext(
        job_doc=dict(job),
        jd_checksum="sha256:benchmark",
        company_checksum="sha256:benchmark",
        input_snapshot_id="sha256:benchmark",
        attempt_number=1,
        config=StepConfig(
            provider="codex",
            primary_model=model,
            fallback_provider="none",
            fallback_model=None,
        ),
    )
    result = ClassificationStage().run(ctx)
    payload = dict(result.stage_output)
    if result.duration_ms is not None:
        payload["duration_ms"] = result.duration_ms
    return payload


def run_benchmark(rows: list[dict[str, Any]], *, use_fixture_candidate: bool = False, model: str = "gpt-5.4-mini") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for row in rows:
        gold = row["gold_classification"]
        if use_fixture_candidate:
            candidate = row["candidate_classification"]
        else:
            candidate = _run_stage(row["job_doc"], model=model)
        comparison = compare_classifications(gold, candidate)
        comparison["job_id"] = row.get("job_id") or str(row.get("_id") or "unknown")
        report.append(comparison)

    def _mean(field: str) -> float:
        values = [1.0 if item.get(field) else 0.0 for item in report if item.get("schema_valid")]
        return mean(values) if values else 0.0

    schema_values = [1.0 if item.get("schema_valid") else 0.0 for item in report]
    durations = [int(item.get("duration_ms") or 0) for item in report if item.get("duration_ms") is not None]
    ai_gold_positive = [item for item in report if item.get("schema_valid")]
    summary = {
        "schema_validity_pass_rate": mean(schema_values) if schema_values else 0.0,
        "primary_category_exact_match": _mean("primary_exact_match"),
        "top2_recall": _mean("top2_recall"),
        "ambiguity_detection_match": _mean("ambiguity_match"),
        "jd_facts_agreement_match": _mean("jd_facts_agreement_match"),
        "ai_primary_specialization_precision_recall": _mean("ai_primary_exact_match") if ai_gold_positive else 0.0,
        "ai_intensity_exact_match": _mean("ai_intensity_exact_match"),
        "deterministic_skip_rate": _mean("deterministic_skip"),
        "duration_p50_ms": sorted(durations)[len(durations) // 2] if durations else 0,
        "passes_thresholds": (
            (mean(schema_values) if schema_values else 0.0) >= 1.0
            and _mean("primary_exact_match") >= 0.8
            and _mean("top2_recall") >= 0.9
        ),
    }
    return report, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--use-fixture-candidate", action="store_true")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report-out", default="")
    args = parser.parse_args()

    rows = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]
    report, summary = run_benchmark(rows, use_fixture_candidate=args.use_fixture_candidate, model=args.model)
    payload = {"rows": report, "summary": summary}
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
