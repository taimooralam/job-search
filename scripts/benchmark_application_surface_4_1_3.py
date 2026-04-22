"""Safe local benchmark harness for application_surface 4.1.3."""

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

from src.preenrich.blueprint_models import ApplicationSurfaceDoc, normalize_application_surface_payload
from src.preenrich.stages.application_surface import ApplicationSurfaceStage
from src.preenrich.types import StageContext, get_stage_step_config


def compare_application_surface(gold: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    try:
        parsed = ApplicationSurfaceDoc.model_validate(
            normalize_application_surface_payload(candidate)
        )
        row["schema_valid"] = True
    except Exception as exc:
        row["schema_valid"] = False
        row["error"] = str(exc)
        return row

    gold_url = gold.get("canonical_application_url")
    candidate_url = parsed.canonical_application_url
    gold_portal = gold.get("portal_family")
    gold_status = gold.get("resolution_status") or gold.get("status")
    candidate_status = parsed.resolution_status or parsed.status
    partial_correct = False
    if gold_status == "partial":
        partial_correct = (
            parsed.status == "partial"
            and bool(candidate_url)
            and candidate_url == gold_url
        )
    unresolved_useful = (
        parsed.status == "unresolved"
        and (
            bool(parsed.candidates)
            or bool(parsed.notes)
            or bool(parsed.sources)
            or bool(parsed.evidence)
        )
    )
    row.update(
        {
            "exact_canonical_match": candidate_url == gold_url,
            "partial_employer_portal_match": partial_correct,
            "portal_family_match": parsed.portal_family == gold_portal,
            "resolution_status_match": candidate_status == gold_status,
            "stale_signal_match": parsed.stale_signal == (gold.get("stale_signal") or parsed.stale_signal),
            "closed_signal_match": parsed.closed_signal == (gold.get("closed_signal") or parsed.closed_signal),
            "unresolved_useful": unresolved_useful,
            "has_sources": bool(parsed.sources),
            "has_evidence": bool(parsed.evidence),
        }
    )
    return row


def _run_stage(job: dict[str, Any], *, model: str) -> dict[str, Any]:
    config = get_stage_step_config("application_surface")
    config.provider = "codex"
    config.primary_model = model
    config.fallback_provider = "none"
    config.fallback_model = None
    config.transport = "codex_web_search"
    config.fallback_transport = "none"
    ctx = StageContext(
        job_doc=dict(job),
        jd_checksum="sha256:benchmark",
        company_checksum="sha256:benchmark",
        input_snapshot_id="sha256:benchmark",
        attempt_number=1,
        config=config,
    )
    result = ApplicationSurfaceStage().run(ctx)
    payload = dict(result.stage_output)
    if result.duration_ms is not None:
        payload["duration_ms"] = result.duration_ms
    return payload


def run_benchmark(
    rows: list[dict[str, Any]],
    *,
    use_fixture_candidate: bool = False,
    model: str = "gpt-5.2",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for row in rows:
        gold = row["gold_application_surface"]
        candidate = row["candidate_application_surface"] if use_fixture_candidate else _run_stage(row["job_doc"], model=model)
        comparison = compare_application_surface(gold, candidate)
        comparison["job_id"] = row.get("job_id") or str(row.get("_id") or "unknown")
        report.append(comparison)

    def _mean(field: str) -> float:
        values = [1.0 if item.get(field) else 0.0 for item in report if item.get("schema_valid")]
        return mean(values) if values else 0.0

    schema_values = [1.0 if item.get("schema_valid") else 0.0 for item in report]
    summary = {
        "schema_validity_pass_rate": mean(schema_values) if schema_values else 0.0,
        "canonical_url_exact_match": _mean("exact_canonical_match"),
        "partial_employer_portal_match": _mean("partial_employer_portal_match"),
        "portal_family_accuracy": _mean("portal_family_match"),
        "resolution_status_accuracy": _mean("resolution_status_match"),
        "stale_signal_accuracy": _mean("stale_signal_match"),
        "closed_signal_accuracy": _mean("closed_signal_match"),
        "unresolved_useful_rate": _mean("unresolved_useful"),
        "source_preservation_rate": _mean("has_sources"),
        "evidence_preservation_rate": _mean("has_evidence"),
        "passes_thresholds": (
            (mean(schema_values) if schema_values else 0.0) >= 1.0
            and _mean("resolution_status_match") >= 0.9
            and (_mean("exact_canonical_match") + _mean("partial_employer_portal_match")) >= 0.75
        ),
    }
    return report, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--use-fixture-candidate", action="store_true")
    parser.add_argument("--model", default="gpt-5.2")
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
