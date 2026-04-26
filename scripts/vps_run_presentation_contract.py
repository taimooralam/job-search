from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

from scripts.presentation_contract_validation_io import (
    load_validation_fixture,
    validation_target_key,
)
from src.pipeline.tracing import PreenrichTracingSession
from src.preenrich.blueprint_config import validate_blueprint_feature_flags
from src.preenrich.blueprint_models import build_truth_constrained_emphasis_rules_compact
from src.preenrich.blueprint_store import artifact_ref, upsert_artifact
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.presentation_contract import PresentationContractStage
from src.preenrich.types import StageContext, StageResult, get_stage_step_config


def _load_env() -> None:
    values = dotenv_values(PROJECT_ROOT / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _configure_flags() -> None:
    os.environ["PREENRICH_BLUEPRINT_ENABLED"] = "true"
    os.environ["PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED"] = "true"
    os.environ["PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED"] = "true"
    os.environ["PREENRICH_STAKEHOLDER_SURFACE_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_DOCUMENT_EXPECTATIONS_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_CV_SHAPE_EXPECTATIONS_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_EMPHASIS_RULES_ENABLED"] = "true"


def _build_context(job_doc: dict, *, stage_name: str, model: str) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    config = get_stage_step_config(stage_name)
    if stage_name == "presentation_contract":
        config.provider = "codex"
        config.primary_model = model
        config.fallback_provider = "none"
        config.transport = "none"
        config.fallback_transport = "none"
    return StageContext(
        job_doc=job_doc,
        jd_checksum=str(pre.get("jd_checksum") or jd_checksum(description)),
        company_checksum=str(pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain"))),
        input_snapshot_id=str(pre.get("input_snapshot_id") or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest())),
        attempt_number=int((((pre.get("stage_states") or {}).get(stage_name) or {}).get("attempt_count") or 0)) + 1,
        config=config,
        shadow_mode=False,
        stage_name=stage_name,
    )


def _known_artifact_refs(job_doc: dict[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    outputs = ((job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    for stage_output in outputs.values():
        if not isinstance(stage_output, dict):
            continue
        for key, value in (stage_output.get("artifact_refs") or {}).items():
            refs[key] = value
    refs.update(((job_doc.get("pre_enrichment") or {}).get("job_blueprint_refs") or {}))
    return refs


def _resolve_placeholders(value: Any, *, refs: dict[str, Any], now: datetime) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_placeholders(inner, refs=refs, now=now) for key, inner in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item, refs=refs, now=now) for item in value]
    if isinstance(value, str):
        if value == "__now__":
            return now
        if value.startswith("__ref__:"):
            path = value.split(":", 1)[1]
            current: Any = refs
            try:
                for part in path.split("."):
                    current = current[part]
            except Exception:
                return value
            return current
        if value.startswith("__artifact__:"):
            key = value.split(":", 1)[1]
            current = refs.get(key)
            if isinstance(current, dict) and "id" in current:
                return current["id"]
    return value


def _persist_stage_result(db: Any, job_doc: dict, *, result: StageResult, ctx: StageContext, duration_ms: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    artifact_refs: dict[str, Any] = {}
    for artifact in list(result.artifact_writes or []):
        stored = upsert_artifact(
            db,
            collection=artifact.collection,
            unique_filter=artifact.unique_filter,
            document=artifact.document,
            now=now,
        )
        artifact_refs[artifact.ref_name] = artifact_ref(stored, collection=artifact.collection)

    refs = {**_known_artifact_refs(job_doc), **artifact_refs}
    stage_output = _resolve_placeholders(dict(result.stage_output or {}), refs=refs, now=now)
    if not stage_output and not list(result.artifact_writes or []):
        stage_output = _resolve_placeholders(dict(result.output or {}), refs=refs, now=now)
    if artifact_refs:
        stage_output["artifact_refs"] = artifact_refs

    stage_state = {
        "status": "completed",
        "attempt_count": ctx.attempt_number,
        "lease_owner": None,
        "lease_expires_at": None,
        "started_at": now,
        "completed_at": now,
        "input_snapshot_id": ctx.input_snapshot_id,
        "attempt_token": None,
        "jd_checksum_at_completion": ctx.jd_checksum,
        "provider": result.provider_used,
        "model": result.model_used,
        "prompt_version": result.prompt_version or ctx.config.prompt_version,
        "output_ref": {"path": f"pre_enrichment.outputs.{ctx.stage_name}", "artifacts": artifact_refs},
        "last_error": None,
        "work_item_id": None,
        "tokens_input": result.tokens_input,
        "tokens_output": result.tokens_output,
        "cost_usd": result.cost_usd,
    }

    stage_run = {
        "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
        "level2_job_id": str(job_doc["_id"]),
        "stage": ctx.stage_name,
        "status": "completed",
        "worker_id": "vps_run_presentation_contract",
        "attempt_count": ctx.attempt_number,
        "work_item_id": None,
        "started_at": now,
        "updated_at": now,
        "duration_ms": duration_ms,
        "provider": result.provider_used,
        "model": result.model_used,
        "langfuse_session_id": f"job:{job_doc['_id']}",
        "langfuse_trace_id": stage_output.get("trace_ref", {}).get("trace_id"),
        "langfuse_trace_url": stage_output.get("trace_ref", {}).get("trace_url"),
    }
    stage_run_insert = db["preenrich_stage_runs"].insert_one(stage_run)
    stage_run_row = {**stage_run, "_id": str(stage_run_insert.inserted_id)}
    db["preenrich_job_runs"].update_one(
        {"level2_job_id": str(job_doc["_id"])},
        {
            "$setOnInsert": {
                "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
                "level2_job_id": str(job_doc["_id"]),
                "started_at": now,
            },
            "$set": {
                "status": "running",
                "updated_at": now,
                "langfuse_session_id": f"job:{job_doc['_id']}",
                "langfuse_trace_id": stage_output.get("trace_ref", {}).get("trace_id"),
                "langfuse_trace_url": stage_output.get("trace_ref", {}).get("trace_url"),
                f"stage_status_map.{ctx.stage_name}": "completed",
            },
        },
        upsert=True,
    )

    set_doc = {
        f"pre_enrichment.outputs.{ctx.stage_name}": stage_output,
        f"pre_enrichment.stage_states.{ctx.stage_name}": stage_state,
        "updated_at": now,
    }
    set_doc.update(_resolve_placeholders(dict(result.output or {}), refs=refs, now=now))
    db["level-2"].update_one(
        {"_id": job_doc["_id"]},
        {
            "$set": set_doc,
        },
    )
    return {"artifact_refs": artifact_refs, "stage_run_id": str(stage_run_insert.inserted_id), "stage_run_row": stage_run_row}


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _artifact_dir(job_id: str) -> Path:
    return PROJECT_ROOT / "reports" / "presentation-contract" / job_id / "emphasis_rules"


def _write_artifact_bundle(
    *,
    artifact_dir: Path,
    report: dict[str, Any],
    stage_output: dict[str, Any],
    blueprint_snapshot: dict[str, Any] | None,
    stage_run_row: dict[str, Any] | None,
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    emphasis = dict(stage_output.get("truth_constrained_emphasis_rules") or {})
    compact = (
        ((blueprint_snapshot or {}).get("presentation_contract_compact") or {}).get("emphasis_rules")
        if isinstance(blueprint_snapshot, dict)
        else None
    ) or (
        ((blueprint_snapshot or {}).get("presentation_contract") or {}).get("emphasis_rules")
        if isinstance(blueprint_snapshot, dict)
        else None
    ) or {}
    trace_url = (((stage_output.get("trace_ref") or {}).get("trace_url")) if isinstance(stage_output.get("trace_ref"), dict) else "") or ""
    compact = compact if isinstance(compact, dict) else {}
    if not compact and emphasis:
        compact = build_truth_constrained_emphasis_rules_compact(emphasis)
    _write_json(artifact_dir / "subdocument.json", emphasis)
    _write_json(artifact_dir / "parent_stage_output.json", stage_output)
    _write_json(artifact_dir / "snapshot_projection.json", compact if isinstance(compact, dict) else {})
    _write_json(artifact_dir / "stage_runs_row.json", stage_run_row or {})
    (artifact_dir / "trace_url.txt").write_text(trace_url, encoding="utf-8")
    run_ok_line = (
        f"PRESENTATION_CONTRACT_RUN_OK job={report.get('summary', {}).get('job_id')} "
        f"status={stage_output.get('status')} "
        f"emphasis_rules={emphasis.get('status')} "
        f"trace={trace_url or 'missing'}"
    )
    (artifact_dir / "run.log").write_text(
        "\n".join(
            [
                json.dumps(report.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps((report.get("stages") or [None])[0] or {}, ensure_ascii=False, default=str),
                run_ok_line,
            ]
        ),
        encoding="utf-8",
    )
    (artifact_dir / "mongo_writes.md").write_text(
        "\n".join(
            [
                f"- level-2.pre_enrichment.outputs.presentation_contract.truth_constrained_emphasis_rules: {bool(emphasis)}",
                f"- level-2.pre_enrichment.job_blueprint_snapshot.presentation_contract_compact.emphasis_rules: {bool(compact)}",
                f"- presentation_contract collection document: {bool(stage_output)}",
                f"- preenrich_stage_runs.stage_run_id: {(stage_run_row or {}).get('_id') or 'missing'}",
            ]
        ),
        encoding="utf-8",
    )
    topic_coverage = dict(compact.get("topic_coverage") or {})
    acceptance_lines = [
        f"- presentation_contract status: {stage_output.get('status')}",
        f"- truth_constrained_emphasis_rules status: {emphasis.get('status')}",
        f"- mandatory topic coverage count: {sum(1 for count in topic_coverage.values() if int(count or 0) >= 1)}",
        f"- forbidden_claim_patterns count: {compact.get('forbidden_claim_patterns_count') or 0}",
        f"- credibility_ladder_rules count: {compact.get('credibility_ladder_rules_count') or 0}",
        f"- title_strategy_conflict_count: {compact.get('title_strategy_conflict_count') or 0}",
        f"- ai_section_policy_conflict_count: {compact.get('ai_section_policy_conflict_count') or 0}",
        f"- dimension_weight_conflict_count: {compact.get('dimension_weight_conflict_count') or 0}",
        f"- must_signal_contradiction_count: {compact.get('must_signal_contradiction_count') or 0}",
        f"- trace url: {trace_url or 'missing'}",
        f"- stage run id: {(stage_run_row or {}).get('_id') or 'missing'}",
        f"- run ok line: {run_ok_line}",
    ]
    (artifact_dir / "acceptance.md").write_text("\n".join(acceptance_lines), encoding="utf-8")
    _write_json(artifact_dir / "run_report.json", report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run presentation_contract on the VPS with explicit heartbeats and JSON reports.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--job-id", help="MongoDB level-2 ObjectId")
    source.add_argument("--fixture", help="Path to a synthetic level-2 job fixture with upstream outputs")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--persist", action="store_true", default=False)
    parser.add_argument("--report-out", default="")
    parser.add_argument("--run-blueprint-assembly", action="store_true", default=False)
    parser.add_argument("--artifact-dir", default="")
    args = parser.parse_args()

    _load_env()
    _configure_flags()
    validate_blueprint_feature_flags()
    if args.persist and args.fixture:
        raise RuntimeError("Fixture-backed validation is read-only; rerun without --persist.")

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    db = None
    if args.fixture:
        source_kind = "fixture"
        job = load_validation_fixture(args.fixture)
        target_key = validation_target_key(job, fixture_path=args.fixture)
    else:
        source_kind = "mongo"
        target_key = str(args.job_id)
        if not os.getenv("MONGODB_URI"):
            raise RuntimeError("MONGODB_URI not set")
        client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
        db = client["jobs"]
        job = db["level-2"].find_one({"_id": ObjectId(args.job_id)})
        if not job:
            raise RuntimeError(f"Job not found: {args.job_id}")

    state = {"stage": "boot", "started_at": time.time()}
    stop = False

    def heartbeat() -> None:
        while not stop:
            elapsed = int(time.time() - state["started_at"])
            print(f"[HEARTBEAT] ts={datetime.now(timezone.utc).isoformat()} stage={state['stage']} elapsed_s={elapsed}", flush=True)
            time.sleep(args.heartbeat_seconds)

    threading.Thread(target=heartbeat, daemon=True).start()

    ctx = _build_context(dict(job), stage_name="presentation_contract", model=args.model)
    session_id = f"{source_kind}:{target_key}"
    run_id = (
        f"preenrich:presentation_contract:manual:"
        f"{source_kind}:{target_key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    session = PreenrichTracingSession(
        run_id=run_id,
        session_id=session_id,
        metadata={
            "job_id": str(job.get("job_id") or job["_id"]),
            "level2_job_id": str(job["_id"]),
            "correlation_id": session_id,
            "langfuse_session_id": session_id,
            "run_id": run_id,
            "worker_id": "vps_run_presentation_contract",
            "task_type": "preenrich.presentation_contract.manual",
            "stage_name": "presentation_contract",
            "attempt_count": ctx.attempt_number,
            "attempt_token": None,
            "input_snapshot_id": ctx.input_snapshot_id,
            "jd_checksum": ctx.jd_checksum,
            "lifecycle_before": str(job.get("lifecycle") or "selected"),
            "lifecycle_after": str(job.get("lifecycle") or "selected"),
            "work_item_id": None,
            "shadow_mode": False,
            "validation_source": source_kind,
            "validation_target": target_key,
            "fixture_path": args.fixture or "",
        },
    )
    ctx.tracer = session.start_stage_span(
        "presentation_contract",
        {
            "job_id": str(job.get("job_id") or job["_id"]),
            "level2_job_id": str(job["_id"]),
            "stage_name": "presentation_contract",
            "attempt_count": ctx.attempt_number,
            "input_snapshot_id": ctx.input_snapshot_id,
            "jd_checksum": ctx.jd_checksum,
            "mode": "stage",
            "validation_source": source_kind,
            "validation_target": target_key,
        },
    )

    report: dict[str, Any] = {
        "summary": {
            "job_id": target_key,
            "mode": "stage",
            "persist": args.persist,
            "status": "running",
            "source": {
                "kind": source_kind,
                "mongo_job_id": args.job_id or "",
                "fixture": args.fixture or "",
            },
        },
        "stages": [],
    }
    state["stage"] = "presentation_contract"
    state["started_at"] = time.time()
    print("[RUN_MODE] fast-path single-stage presentation_contract", flush=True)
    print(f"[STAGE_START] name=presentation_contract job_id={target_key}", flush=True)
    started = time.time()
    result = PresentationContractStage().run(ctx)
    duration_ms = int((time.time() - started) * 1000)
    stage_status = result.stage_output.get("status") if isinstance(result.stage_output, dict) else "completed"
    ctx.tracer.complete(
        output={
            "status": stage_status,
            "duration_ms": duration_ms,
            "provider": result.provider_used,
            "model": result.model_used,
        }
    )
    session.complete(output={"status": stage_status, "stage_name": "presentation_contract", "duration_ms": duration_ms})

    persist_refs: dict[str, Any] = {}
    if args.persist:
        if db is None:
            raise RuntimeError("Fixture-backed validation cannot persist stage results.")
        persist_refs = _persist_stage_result(db, job, result=result, ctx=ctx, duration_ms=duration_ms)

    report["stages"].append(
        {
            "stage_name": "presentation_contract",
            "status": stage_status,
            "duration_ms": duration_ms,
            "provider": result.provider_used,
            "model": result.model_used,
            "trace_ref": (result.stage_output or {}).get("trace_ref"),
            "stage_run_id": persist_refs.get("stage_run_id"),
            "output_preview": {
                "ideal_candidate_status": ((result.stage_output or {}).get("ideal_candidate_presentation_model") or {}).get("status"),
                "dimension_weights_status": ((result.stage_output or {}).get("experience_dimension_weights") or {}).get("status"),
                "emphasis_rules_status": ((result.stage_output or {}).get("truth_constrained_emphasis_rules") or {}).get("status"),
                "dimension_weight_sum": sum((((result.stage_output or {}).get("experience_dimension_weights") or {}).get("overall_weights") or {}).values()),
                "emphasis_rule_count": sum(
                    len((((result.stage_output or {}).get("truth_constrained_emphasis_rules") or {}).get(bucket)) or [])
                    for bucket in ("global_rules", "allowed_if_evidenced", "downgrade_rules", "omit_rules")
                ) + sum(
                    len(bucket or [])
                    for bucket in ((((result.stage_output or {}).get("truth_constrained_emphasis_rules") or {}).get("section_rules") or {}).values())
                ),
                "acceptable_titles_count": len((((result.stage_output or {}).get("ideal_candidate_presentation_model") or {}).get("acceptable_titles") or [])),
                "proof_ladder_length": len((((result.stage_output or {}).get("ideal_candidate_presentation_model") or {}).get("proof_ladder") or [])),
                "defaults_applied_count": len((((result.stage_output or {}).get("ideal_candidate_presentation_model") or {}).get("defaults_applied") or [])),
            },
        }
    )
    report["summary"] = {
        "job_id": target_key,
        "mode": "stage",
        "persist": args.persist,
        "status": stage_status,
        "stage_count": 1,
        "final_stage": "presentation_contract",
        "final_trace_url": ((result.stage_output or {}).get("trace_ref") or {}).get("trace_url"),
        "source": {
            "kind": source_kind,
            "mongo_job_id": args.job_id or "",
            "fixture": args.fixture or "",
        },
    }
    if args.run_blueprint_assembly:
        state["stage"] = "blueprint_assembly"
        state["started_at"] = time.time()
        refreshed_job = db["level-2"].find_one({"_id": ObjectId(args.job_id)}) if args.persist else None
        assembly_job = dict(refreshed_job or job)
        if not args.persist:
            pre = dict(assembly_job.get("pre_enrichment") or {})
            outputs = dict(pre.get("outputs") or {})
            outputs["presentation_contract"] = dict(result.stage_output or {})
            pre["outputs"] = outputs
            assembly_job["pre_enrichment"] = pre
        assembly_ctx = _build_context(assembly_job, stage_name="blueprint_assembly", model=args.model)
        print(f"[STAGE_START] name=blueprint_assembly job_id={target_key}", flush=True)
        blueprint_started = time.time()
        blueprint_result = BlueprintAssemblyStage().run(assembly_ctx)
        blueprint_duration_ms = int((time.time() - blueprint_started) * 1000)
        blueprint_persist_refs: dict[str, Any] = {}
        if args.persist:
            blueprint_persist_refs = _persist_stage_result(
                db,
                refreshed_job or job,
                result=blueprint_result,
                ctx=assembly_ctx,
                duration_ms=blueprint_duration_ms,
            )
        blueprint_snapshot = ((blueprint_result.stage_output or {}).get("snapshot") or {}) if isinstance(blueprint_result.stage_output, dict) else {}
        report["stages"].append(
            {
                "stage_name": "blueprint_assembly",
                "status": "completed",
                "duration_ms": blueprint_duration_ms,
                "provider": blueprint_result.provider_used,
                "model": blueprint_result.model_used,
                "trace_ref": None,
                "stage_run_id": blueprint_persist_refs.get("stage_run_id"),
                "output_preview": {
                    "presentation_contract_status": ((blueprint_snapshot.get("presentation_contract") or {}).get("status") if isinstance(blueprint_snapshot, dict) else None),
                    "ideal_candidate_compact_present": bool((((blueprint_snapshot.get("presentation_contract") or {}).get("ideal_candidate")) if isinstance(blueprint_snapshot, dict) else {})),
                    "dimension_weights_compact_present": bool((((blueprint_snapshot.get("presentation_contract_compact") or {}).get("dimension_weights")) if isinstance(blueprint_snapshot, dict) else {})),
                    "emphasis_rules_compact_present": bool((((blueprint_snapshot.get("presentation_contract_compact") or {}).get("emphasis_rules")) if isinstance(blueprint_snapshot, dict) else {})),
                },
            }
        )
        report["summary"] = {
            "job_id": target_key,
            "mode": "stage",
            "persist": args.persist,
            "status": stage_status,
            "stage_count": len(report["stages"]),
            "final_stage": "blueprint_assembly",
            "final_trace_url": ((result.stage_output or {}).get("trace_ref") or {}).get("trace_url"),
            "source": {
                "kind": source_kind,
                "mongo_job_id": args.job_id or "",
                "fixture": args.fixture or "",
            },
        }
    _write_json(Path(args.report_out) if args.report_out else None, report)
    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else _artifact_dir(target_key)
    _write_artifact_bundle(
        artifact_dir=artifact_dir,
        report=report,
        stage_output=dict(result.stage_output or {}),
        blueprint_snapshot=blueprint_snapshot if args.run_blueprint_assembly else None,
        stage_run_row=persist_refs.get("stage_run_row"),
    )
    print(json.dumps({"stage_complete": report["stages"][0]}, indent=2, ensure_ascii=False, default=str), flush=True)
    print(json.dumps({"runner_complete": report["summary"]}, indent=2, ensure_ascii=False, default=str), flush=True)
    print(
        "PRESENTATION_CONTRACT_RUN_OK "
        f"job={target_key} "
        f"status={stage_status} "
        f"emphasis_rules={((result.stage_output or {}).get('truth_constrained_emphasis_rules') or {}).get('status')} "
        f"trace={((result.stage_output or {}).get('trace_ref') or {}).get('trace_url') or 'missing'}",
        flush=True,
    )
    stop = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
