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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

from src.pipeline.tracing import PreenrichTracingSession
from src.preenrich.blueprint_config import validate_blueprint_feature_flags
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.stages.pain_point_intelligence import PainPointIntelligenceStage
from src.preenrich.types import StageContext, get_stage_step_config


def _load_env() -> None:
    values = dotenv_values(Path.cwd() / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _configure_flags(*, supplemental_web: bool) -> None:
    os.environ["PREENRICH_BLUEPRINT_ENABLED"] = "true"
    os.environ["PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED"] = "true"
    os.environ["PREENRICH_STAKEHOLDER_SURFACE_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_INTELLIGENCE_COMPAT_PROJECTION_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_SUPPLEMENTAL_WEB_ENABLED"] = "true" if supplemental_web else "false"
    os.environ["WEB_RESEARCH_ENABLED"] = "true" if supplemental_web else os.getenv("WEB_RESEARCH_ENABLED", "false")


def _build_context(job_doc: dict, *, model: str) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    jd_cs = str(pre.get("jd_checksum") or jd_checksum(description))
    company_cs = str(pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain")))
    snapshot_id = str(pre.get("input_snapshot_id") or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest()))
    attempt_number = int(pre.get("attempt_number", 0) or 0) + 1
    config = get_stage_step_config("pain_point_intelligence")
    config.provider = "codex"
    config.primary_model = model
    config.fallback_provider = "none"
    config.transport = "none"
    config.fallback_transport = "none"
    return StageContext(
        job_doc=job_doc,
        jd_checksum=jd_cs,
        company_checksum=company_cs,
        input_snapshot_id=snapshot_id,
        attempt_number=attempt_number,
        config=config,
        shadow_mode=False,
        stage_name="pain_point_intelligence",
    )


def _write_json(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated pain_point_intelligence smoke pass with heartbeat logging.")
    parser.add_argument("--job-id", required=True, help="MongoDB level-2 ObjectId")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--supplemental-web", action="store_true", default=False)
    parser.add_argument("--report-out", default="")
    parser.add_argument("--stage-out", default="")
    args = parser.parse_args()

    _load_env()
    _configure_flags(supplemental_web=args.supplemental_web)
    validate_blueprint_feature_flags()

    if not os.getenv("MONGODB_URI"):
        raise RuntimeError("MONGODB_URI not set")

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)

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

    client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
    job = client["jobs"]["level-2"].find_one({"_id": ObjectId(args.job_id)})
    if not job:
        raise RuntimeError(f"Job not found: {args.job_id}")

    ctx = _build_context(dict(job), model=args.model)
    run_id = f"preenrich:smoke:pain_point_intelligence:{args.job_id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    session = PreenrichTracingSession(
        run_id=run_id,
        session_id=f"job:{args.job_id}",
        metadata={
            "job_id": str(job.get("job_id") or job["_id"]),
            "level2_job_id": str(job["_id"]),
            "correlation_id": f"job:{job['_id']}",
            "langfuse_session_id": f"job:{job['_id']}",
            "run_id": run_id,
            "worker_id": "smoke_pain_point_intelligence",
            "task_type": "preenrich.pain_point_intelligence.smoke",
            "stage_name": "pain_point_intelligence",
            "attempt_count": ctx.attempt_number,
            "attempt_token": None,
            "input_snapshot_id": ctx.input_snapshot_id,
            "jd_checksum": ctx.jd_checksum,
            "lifecycle_before": str(job.get("lifecycle") or "selected"),
            "lifecycle_after": str(job.get("lifecycle") or "selected"),
            "work_item_id": None,
            "shadow_mode": False,
        },
    )
    ctx.tracer = session.start_stage_span(
        "pain_point_intelligence",
        {
            "job_id": str(job.get("job_id") or job["_id"]),
            "level2_job_id": str(job["_id"]),
            "stage_name": "pain_point_intelligence",
            "attempt_count": ctx.attempt_number,
            "input_snapshot_id": ctx.input_snapshot_id,
            "jd_checksum": ctx.jd_checksum,
            "mode": "smoke",
        },
    )

    state["stage"] = "pain_point_intelligence"
    state["started_at"] = time.time()
    print(
        json.dumps(
            {
                "run": {
                    "job_id": args.job_id,
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "model": args.model,
                    "supplemental_web": args.supplemental_web,
                    "cwd": str(Path.cwd()),
                }
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    print("[STAGE_START] name=pain_point_intelligence mode=smoke", flush=True)
    started = time.time()
    result = PainPointIntelligenceStage().run(ctx)
    duration_s = round(time.time() - started, 2)

    ctx.tracer.complete(
        output={
            "status": result.stage_output.get("status"),
            "pains_count": len(result.stage_output.get("pain_points") or []),
            "proof_map_size": len(result.stage_output.get("proof_map") or []),
            "duration_s": duration_s,
        }
    )
    session.complete(
        output={
            "status": result.stage_output.get("status"),
            "stage_name": "pain_point_intelligence",
            "duration_s": duration_s,
        }
    )

    report = {
        "summary": {
            "job_id": args.job_id,
            "status": result.stage_output.get("status"),
            "source_scope": result.stage_output.get("source_scope"),
            "fail_open_reason": result.stage_output.get("fail_open_reason"),
            "pains_count": len(result.stage_output.get("pain_points") or []),
            "proof_map_size": len(result.stage_output.get("proof_map") or []),
            "unresolved_questions_count": len(result.stage_output.get("unresolved_questions") or []),
            "duration_s": duration_s,
        },
        "trace": {
            "trace_id": session.trace_id,
            "trace_url": session.trace_url,
        },
        "artifact_writes": [
            {
                "collection": item.collection,
                "ref_name": item.ref_name,
                "unique_filter": item.unique_filter,
            }
            for item in (result.artifact_writes or [])
        ],
        "stage_output_preview": {
            "pain_points": [item.get("statement") for item in (result.stage_output.get("pain_points") or [])[:5]],
            "strategic_needs": [item.get("statement") for item in (result.stage_output.get("strategic_needs") or [])[:5]],
            "risks_if_unfilled": [item.get("statement") for item in (result.stage_output.get("risks_if_unfilled") or [])[:5]],
            "success_metrics": [item.get("statement") for item in (result.stage_output.get("success_metrics") or [])[:5]],
        },
    }
    stop = True
    _write_json(Path(args.report_out) if args.report_out else None, report)
    _write_json(Path(args.stage_out) if args.stage_out else None, result.stage_output)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
