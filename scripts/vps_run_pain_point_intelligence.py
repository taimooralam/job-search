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

from src.pipeline.tracing import PreenrichTracingSession
from src.preenrich.blueprint_config import validate_blueprint_feature_flags
from src.preenrich.blueprint_store import artifact_ref, upsert_artifact
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.stages.application_surface import ApplicationSurfaceStage
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.stages.jd_facts import JDFactsStage
from src.preenrich.stages.pain_point_intelligence import PainPointIntelligenceStage
from src.preenrich.stages.presentation_contract import PresentationContractStage
from src.preenrich.stages.research_enrichment import ResearchEnrichmentStage
from src.preenrich.stages.stakeholder_surface import StakeholderSurfaceStage
from src.preenrich.types import StageContext, StageResult, get_stage_step_config

STAGE_ORDER = [
    "jd_facts",
    "classification",
    "application_surface",
    "research_enrichment",
    "stakeholder_surface",
    "pain_point_intelligence",
    "presentation_contract",
    "blueprint_assembly",
]

STAGE_FACTORIES = {
    "jd_facts": JDFactsStage,
    "classification": ClassificationStage,
    "application_surface": ApplicationSurfaceStage,
    "research_enrichment": ResearchEnrichmentStage,
    "stakeholder_surface": StakeholderSurfaceStage,
    "pain_point_intelligence": PainPointIntelligenceStage,
    "presentation_contract": PresentationContractStage,
    "blueprint_assembly": BlueprintAssemblyStage,
}

PRIMARY_MODELS = {
    "jd_facts": "gpt-5.2",
    "classification": "gpt-5.4-mini",
    "application_surface": "gpt-5.2",
    "research_enrichment": "gpt-5.2",
    "stakeholder_surface": "gpt-5.2",
    "pain_point_intelligence": "gpt-5.4",
    "presentation_contract": "gpt-5.4",
    "blueprint_assembly": None,
}

TRANSPORTS = {
    "application_surface": "codex_web_search",
    "research_enrichment": "codex_web_search",
    "stakeholder_surface": "codex_web_search",
    "pain_point_intelligence": "none",
    "presentation_contract": "none",
}


def _load_env() -> None:
    values = dotenv_values(PROJECT_ROOT / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _configure_flags(*, supplemental_web: bool, include_presentation_contract: bool) -> None:
    os.environ["PREENRICH_BLUEPRINT_ENABLED"] = "true"
    os.environ["PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED"] = "true"
    os.environ["PREENRICH_STAKEHOLDER_SURFACE_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_INTELLIGENCE_COMPAT_PROJECTION_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_ENABLED"] = "true" if include_presentation_contract else "false"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_DOCUMENT_EXPECTATIONS_ENABLED"] = "true" if include_presentation_contract else "false"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_CV_SHAPE_EXPECTATIONS_ENABLED"] = "true" if include_presentation_contract else "false"
    os.environ["PREENRICH_PAIN_POINT_SUPPLEMENTAL_WEB_ENABLED"] = "true" if supplemental_web else "false"
    os.environ["WEB_RESEARCH_ENABLED"] = "true"


def _build_context(job_doc: dict, *, stage_name: str) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    jd_cs = str(pre.get("jd_checksum") or jd_checksum(description))
    company_cs = str(pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain")))
    snapshot_id = str(pre.get("input_snapshot_id") or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest()))
    attempt_number = int((((pre.get("stage_states") or {}).get(stage_name) or {}).get("attempt_count") or 0)) + 1
    config = get_stage_step_config(stage_name)
    config.provider = config.provider or "codex"
    config.primary_model = PRIMARY_MODELS.get(stage_name) or config.primary_model
    config.transport = TRANSPORTS.get(stage_name, config.transport)
    config.fallback_provider = "none"
    if stage_name in {"pain_point_intelligence", "presentation_contract"}:
        config.fallback_model = None
    return StageContext(
        job_doc=job_doc,
        jd_checksum=jd_cs,
        company_checksum=company_cs,
        input_snapshot_id=snapshot_id,
        attempt_number=attempt_number,
        config=config,
        shadow_mode=False,
        stage_name=stage_name,
    )


def _start_trace(job_doc: dict, *, stage_name: str, ctx: StageContext, run_id: str, mode: str) -> tuple[PreenrichTracingSession, Any]:
    session = PreenrichTracingSession(
        run_id=run_id,
        session_id=f"job:{job_doc['_id']}",
        metadata={
            "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
            "level2_job_id": str(job_doc["_id"]),
            "correlation_id": f"job:{job_doc['_id']}",
            "langfuse_session_id": f"job:{job_doc['_id']}",
            "run_id": run_id,
            "worker_id": "vps_run_pain_point_intelligence",
            "task_type": f"preenrich.{stage_name}.manual",
            "stage_name": stage_name,
            "attempt_count": ctx.attempt_number,
            "attempt_token": None,
            "input_snapshot_id": ctx.input_snapshot_id,
            "jd_checksum": ctx.jd_checksum,
            "lifecycle_before": str(job_doc.get("lifecycle") or "selected"),
            "lifecycle_after": str(job_doc.get("lifecycle") or "selected"),
            "work_item_id": None,
            "mode": mode,
            "shadow_mode": False,
        },
    )
    stage_tracer = session.start_stage_span(
        stage_name,
        {
            "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
            "level2_job_id": str(job_doc["_id"]),
            "stage_name": stage_name,
            "attempt_count": ctx.attempt_number,
            "input_snapshot_id": ctx.input_snapshot_id,
            "jd_checksum": ctx.jd_checksum,
            "mode": mode,
        },
    )
    return session, stage_tracer


def _persist_stage_result(
    db: Any,
    job_doc: dict,
    *,
    stage_name: str,
    result: StageResult,
    ctx: StageContext,
    duration_ms: int,
) -> dict[str, Any]:
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

    stage_output = dict(result.stage_output or {})
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
        "output_ref": {"path": f"pre_enrichment.outputs.{stage_name}", "artifacts": artifact_refs},
        "last_error": None,
        "work_item_id": None,
        "tokens_input": result.tokens_input,
        "tokens_output": result.tokens_output,
        "cost_usd": result.cost_usd,
    }

    stage_run = {
        "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
        "level2_job_id": str(job_doc["_id"]),
        "stage": stage_name,
        "status": "completed",
        "worker_id": "vps_run_pain_point_intelligence",
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
    job_run_update = db["preenrich_job_runs"].update_one(
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
            },
        },
        upsert=True,
    )

    set_doc = {
        f"pre_enrichment.outputs.{stage_name}": stage_output,
        f"pre_enrichment.stage_states.{stage_name}": stage_state,
        "updated_at": now,
    }
    set_doc.update(dict(result.output or {}))
    db["level-2"].update_one({"_id": job_doc["_id"]}, {"$set": set_doc})
    return {
        "artifact_refs": artifact_refs,
        "stage_run_id": str(stage_run_insert.inserted_id),
        "job_run_filter": {"level2_job_id": str(job_doc["_id"])},
        "job_run_upserted_id": str(job_run_update.upserted_id) if job_run_update.upserted_id else None,
    }


def _write_json(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pain_point_intelligence on the VPS with explicit heartbeats and JSON reports.")
    parser.add_argument("--job-id", required=True, help="MongoDB level-2 ObjectId")
    parser.add_argument("--mode", choices=["stage", "chain"], default="stage")
    parser.add_argument(
        "--stage-name",
        choices=sorted(STAGE_FACTORIES),
        default="pain_point_intelligence",
        help="Stage to run when --mode=stage. Defaults to pain_point_intelligence.",
    )
    parser.add_argument("--include-presentation-contract", action="store_true", default=False)
    parser.add_argument("--supplemental-web", action="store_true", default=False)
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--report-out", default="")
    parser.add_argument("--persist", action="store_true", default=False)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    _load_env()
    _configure_flags(
        supplemental_web=args.supplemental_web,
        include_presentation_contract=args.include_presentation_contract or args.mode == "chain",
    )
    validate_blueprint_feature_flags()
    if not os.getenv("MONGODB_URI"):
        raise RuntimeError("MONGODB_URI not set")

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
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
            print(
                f"[HEARTBEAT] ts={datetime.now(timezone.utc).isoformat()} stage={state['stage']} elapsed_s={elapsed}",
                flush=True,
            )
            time.sleep(args.heartbeat_seconds)

    threading.Thread(target=heartbeat, daemon=True).start()

    stages = [args.stage_name] if args.mode == "stage" else list(STAGE_ORDER)
    if args.mode != "chain" and not args.include_presentation_contract and "presentation_contract" in stages:
        stages.remove("presentation_contract")
    if args.mode == "stage":
        print(f"[RUN_MODE] fast-path single-stage {args.stage_name}", flush=True)
    else:
        print(f"[RUN_MODE] chain={','.join(stages)}", flush=True)

    report: dict[str, Any] = {
        "summary": {"job_id": args.job_id, "mode": args.mode, "persist": args.persist, "status": "running"},
        "stages": [],
    }
    working_job = dict(job)
    exit_code = 0
    try:
        for stage_name in stages:
            ctx = _build_context(working_job, stage_name=stage_name)
            run_id = f"preenrich:{stage_name}:manual:{args.job_id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            session, stage_tracer = _start_trace(working_job, stage_name=stage_name, ctx=ctx, run_id=run_id, mode=args.mode)
            ctx.tracer = stage_tracer
            state["stage"] = stage_name
            state["started_at"] = time.time()
            print(f"[STAGE_START] name={stage_name}", flush=True)
            started = time.time()
            try:
                result = STAGE_FACTORIES[stage_name]().run(ctx)
            except Exception as exc:
                duration_ms = int((time.time() - started) * 1000)
                error_payload = {
                    "status": "failed",
                    "stage_name": stage_name,
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                stage_tracer.complete(output=error_payload)
                session.complete(output=error_payload)
                report["stages"].append(
                    {
                        "stage_name": stage_name,
                        "status": "failed",
                        "duration_ms": duration_ms,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                report["summary"]["status"] = "failed"
                report["summary"]["failed_stage"] = stage_name
                report["summary"]["error_type"] = type(exc).__name__
                report["summary"]["error"] = str(exc)
                print(json.dumps({"stage_failed": error_payload}, indent=2, ensure_ascii=False, default=str), flush=True)
                raise
            duration_ms = int((time.time() - started) * 1000)
            stage_status = result.stage_output.get("status") if isinstance(result.stage_output, dict) else "completed"
            stage_tracer.complete(
                output={
                    "status": stage_status,
                    "duration_ms": duration_ms,
                    "provider": result.provider_used,
                    "model": result.model_used,
                }
            )
            session.complete(
                output={
                    "status": stage_status,
                    "stage_name": stage_name,
                    "duration_ms": duration_ms,
                }
            )

            persist_refs: dict[str, Any] = {}
            if args.persist:
                persist_refs = _persist_stage_result(
                    db,
                    working_job,
                    stage_name=stage_name,
                    result=result,
                    ctx=ctx,
                    duration_ms=duration_ms,
                )
                working_job = db["level-2"].find_one({"_id": ObjectId(args.job_id)}) or working_job
            else:
                pre = dict(working_job.get("pre_enrichment") or {})
                outputs = dict(pre.get("outputs") or {})
                outputs[stage_name] = dict(result.stage_output or {})
                pre["outputs"] = outputs
                pre["jd_checksum"] = ctx.jd_checksum
                pre["company_checksum"] = ctx.company_checksum
                pre["input_snapshot_id"] = ctx.input_snapshot_id
                working_job["pre_enrichment"] = pre

            report["stages"].append(
                {
                    "stage_name": stage_name,
                    "status": stage_status,
                    "duration_ms": duration_ms,
                    "provider": result.provider_used,
                    "model": result.model_used,
                    "trace_ref": (result.stage_output or {}).get("trace_ref"),
                    "artifact_refs": persist_refs.get("artifact_refs", {}),
                    "stage_run_id": persist_refs.get("stage_run_id"),
                    "job_run_filter": persist_refs.get("job_run_filter"),
                    "preview": {
                        "pain_points": [item.get("statement") for item in ((result.stage_output or {}).get("pain_points") or [])[:5]],
                        "proof_map_size": len((result.stage_output or {}).get("proof_map") or []),
                        "real_stakeholders": len((result.stage_output or {}).get("real_stakeholders") or []),
                    },
                }
            )
            print(
                json.dumps(
                    {
                        "stage_complete": {
                            "stage_name": stage_name,
                            "status": stage_status,
                            "duration_ms": duration_ms,
                            "trace_url": ((result.stage_output or {}).get("trace_ref") or {}).get("trace_url"),
                        }
                    },
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                flush=True,
            )

        report["summary"]["status"] = "completed"
        if args.persist:
            now = datetime.now(timezone.utc)
            db["preenrich_job_runs"].update_one(
                {"level2_job_id": args.job_id},
                {"$set": {"status": "completed", "updated_at": now}},
                upsert=True,
            )
    except Exception:
        exit_code = 1
        if args.persist:
            now = datetime.now(timezone.utc)
            db["preenrich_job_runs"].update_one(
                {"level2_job_id": args.job_id},
                {"$set": {"status": "failed", "updated_at": now}},
                upsert=True,
            )
    finally:
        report["summary"]["stage_count"] = len(report["stages"])
        report["summary"]["final_stage"] = report["stages"][-1]["stage_name"] if report["stages"] else None
        report["summary"]["final_trace_url"] = report["stages"][-1]["trace_ref"]["trace_url"] if report["stages"] and report["stages"][-1].get("trace_ref") else None
        stop = True
        _write_json(Path(args.report_out) if args.report_out else None, report)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
