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

from scripts.presentation_contract_validation_io import (
    load_validation_fixture,
    validation_target_key,
)
from src.pipeline.tracing import PreenrichTracingSession
from src.preenrich.blueprint_config import validate_blueprint_feature_flags
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.stages.presentation_contract import PresentationContractStage
from src.preenrich.types import StageContext, get_stage_step_config


def _load_env() -> None:
    values = dotenv_values(PROJECT_ROOT / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _configure_flags() -> None:
    os.environ["PREENRICH_BLUEPRINT_ENABLED"] = "true"
    os.environ["PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED"] = "true"
    os.environ["PREENRICH_STAKEHOLDER_SURFACE_ENABLED"] = "true"
    os.environ["PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_DOCUMENT_EXPECTATIONS_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_CV_SHAPE_EXPECTATIONS_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED"] = "true"
    os.environ["PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED"] = "true"


def _build_context(job_doc: dict, *, model: str) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    ctx = StageContext(
        job_doc=job_doc,
        jd_checksum=str(pre.get("jd_checksum") or jd_checksum(description)),
        company_checksum=str(
            pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain"))
        ),
        input_snapshot_id=str(
            pre.get("input_snapshot_id") or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest())
        ),
        attempt_number=int((((pre.get("stage_states") or {}).get("presentation_contract") or {}).get("attempt_count") or 0))
        + 1,
        config=get_stage_step_config("presentation_contract"),
        shadow_mode=False,
        stage_name="presentation_contract",
    )
    ctx.config.provider = "codex"
    ctx.config.primary_model = model
    ctx.config.fallback_provider = "none"
    ctx.config.transport = "none"
    ctx.config.fallback_transport = "none"
    return ctx


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-run presentation_contract dimension weights with visible heartbeats.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--job-id", help="MongoDB level-2 ObjectId")
    source.add_argument("--fixture", help="Path to a synthetic level-2 job fixture with upstream outputs")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    args = parser.parse_args()

    _load_env()
    _configure_flags()
    validate_blueprint_feature_flags()
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)

    state = {"stage": "boot", "started_at": time.time()}
    stop = False

    def heartbeat() -> None:
        while not stop:
            elapsed = int(time.time() - state["started_at"])
            print(f"[HEARTBEAT] ts={datetime.now(timezone.utc).isoformat()} stage={state['stage']} elapsed_s={elapsed}", flush=True)
            time.sleep(args.heartbeat_seconds)

    threading.Thread(target=heartbeat, daemon=True).start()

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
        job = client["jobs"]["level-2"].find_one({"_id": ObjectId(args.job_id)})
        if not job:
            raise RuntimeError(f"Job not found: {args.job_id}")

    ctx = _build_context(dict(job), model=args.model)
    session_id = f"{source_kind}:{target_key}"
    run_id = (
        f"preenrich:smoke:presentation_contract:dimension_weights:"
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
            "worker_id": "smoke_experience_dimension_weights",
            "task_type": "preenrich.presentation_contract.smoke",
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
            "mode": "smoke",
            "validation_source": source_kind,
            "validation_target": target_key,
        },
    )

    state["stage"] = "presentation_contract"
    print(
        json.dumps(
            {
                "run": {
                    "target": target_key,
                    "source": {
                        "kind": source_kind,
                        "mongo_job_id": args.job_id or "",
                        "fixture": args.fixture or "",
                    },
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "model": args.model,
                }
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    started = time.time()
    result = PresentationContractStage().run(ctx)
    duration_s = round(time.time() - started, 2)
    dimension = result.stage_output.get("experience_dimension_weights") or {}
    session.complete(
        output={
            "status": result.stage_output.get("status"),
            "stage_name": "presentation_contract",
            "dimension_weights_status": dimension.get("status"),
            "duration_s": duration_s,
        }
    )
    stop = True

    print(
        json.dumps(
            {
                "summary": {
                    "status": result.stage_output.get("status"),
                    "dimension_weights_status": dimension.get("status"),
                    "overall_weight_sum": sum((dimension.get("overall_weights") or {}).values()),
                    "top3": sorted(
                        list((dimension.get("overall_weights") or {}).items()),
                        key=lambda item: (-item[1], item[0]),
                    )[:3],
                    "variant_count": len([v for v in (dimension.get("stakeholder_variant_weights") or {}).values() if v]),
                    "duration_s": duration_s,
                },
                "trace": {"trace_id": session.trace_id, "trace_url": session.trace_url},
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
