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

from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.stages.application_surface import ApplicationSurfaceStage
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.stages.jd_facts import JDFactsStage
from src.preenrich.types import StageContext, get_stage_step_config


def _load_env() -> None:
    values = dotenv_values(Path.cwd() / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _build_context(
    job_doc: dict,
    *,
    stage_name: str,
    model: str,
    transport: str = "none",
) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    jd_cs = str(pre.get("jd_checksum") or jd_checksum(description))
    company_cs = str(pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain")))
    snapshot_id = str(
        pre.get("input_snapshot_id")
        or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest())
    )
    attempt_number = int(pre.get("attempt_number", 0) or 0) + 1
    config = get_stage_step_config(stage_name)
    config.provider = "codex"
    config.primary_model = model
    config.fallback_provider = "none"
    config.fallback_model = None
    if transport != "none":
        config.transport = transport
    config.fallback_transport = "none"
    return StageContext(
        job_doc=job_doc,
        jd_checksum=jd_cs,
        company_checksum=company_cs,
        input_snapshot_id=snapshot_id,
        attempt_number=attempt_number,
        config=config,
        shadow_mode=False,
    )


def _write_json(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated jd_facts + classification + application_surface debug with heartbeat logging.")
    parser.add_argument("--job-id", required=True, help="Mongo level-2 ObjectId")
    parser.add_argument("--jd-model", default="gpt-5.2")
    parser.add_argument("--classification-model", default="gpt-5.4-mini")
    parser.add_argument("--application-model", default="gpt-5.2")
    parser.add_argument("--application-transport", default="codex_web_search")
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--jd-out", default="")
    parser.add_argument("--classification-out", default="")
    parser.add_argument("--application-out", default="")
    args = parser.parse_args()

    _load_env()
    if not os.getenv("MONGODB_URI"):
        raise RuntimeError("MONGODB_URI not set")

    os.environ["WEB_RESEARCH_ENABLED"] = "true"
    os.environ["PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED"] = "false"
    os.environ["PREENRICH_RESEARCH_PROVIDER"] = "codex"
    os.environ["PREENRICH_RESEARCH_TRANSPORT"] = args.application_transport
    os.environ["PREENRICH_RESEARCH_FALLBACK_PROVIDER"] = "none"
    os.environ["PREENRICH_RESEARCH_FALLBACK_TRANSPORT"] = "none"
    if args.timeout_seconds > 0:
        os.environ["PREENRICH_CODEX_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
        os.environ["PREENRICH_RESEARCH_TRANSPORT_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    else:
        os.environ.pop("PREENRICH_CODEX_TIMEOUT_SECONDS", None)
        os.environ.pop("CODEX_TIMEOUT_SECONDS", None)
        os.environ.pop("PREENRICH_RESEARCH_TRANSPORT_TIMEOUT_SECONDS", None)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    for noisy in ["urllib3", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.INFO)

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

    print(
        json.dumps(
            {
                "debug": {
                    "job_id": args.job_id,
                    "jd_model": args.jd_model,
                    "classification_model": args.classification_model,
                    "application_model": args.application_model,
                    "application_transport": args.application_transport,
                    "timeout_seconds": None if args.timeout_seconds <= 0 else args.timeout_seconds,
                    "heartbeat_seconds": args.heartbeat_seconds,
                    "cwd": str(Path.cwd()),
                    "mongodb_uri_present": bool(os.getenv("MONGODB_URI")),
                    "research_max_web_queries": os.getenv("PREENRICH_RESEARCH_MAX_WEB_QUERIES", "default"),
                    "research_max_fetches": os.getenv("PREENRICH_RESEARCH_MAX_FETCHES", "default"),
                }
            },
            indent=2,
        ),
        flush=True,
    )

    client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
    job = client["jobs"]["level-2"].find_one({"_id": ObjectId(args.job_id)})
    if not job:
        raise RuntimeError(f"Job not found: {args.job_id}")

    print(
        json.dumps(
            {
                "job": {
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "source": job.get("source"),
                }
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )

    jd_ctx = _build_context(dict(job), stage_name="jd_facts", model=args.jd_model)
    state["stage"] = "jd_facts"
    state["started_at"] = time.time()
    print("[STAGE_START] name=jd_facts mode=v2_only", flush=True)
    jd_started = time.time()
    jd_result = JDFactsStage().run(jd_ctx)
    jd_duration = round(time.time() - jd_started, 2)
    _write_json(Path(args.jd_out) if args.jd_out else None, jd_result.stage_output)

    job_with_jd = dict(job)
    pre = dict(job_with_jd.get("pre_enrichment") or {})
    outputs = dict(pre.get("outputs") or {})
    outputs["jd_facts"] = jd_result.stage_output
    pre["outputs"] = outputs
    pre["jd_checksum"] = jd_ctx.jd_checksum
    pre["company_checksum"] = jd_ctx.company_checksum
    pre["input_snapshot_id"] = jd_ctx.input_snapshot_id
    pre["attempt_number"] = jd_ctx.attempt_number
    job_with_jd["pre_enrichment"] = pre

    classification_ctx = _build_context(job_with_jd, stage_name="classification", model=args.classification_model)
    state["stage"] = "classification"
    state["started_at"] = time.time()
    print("[STAGE_START] name=classification mode=v2_only", flush=True)
    classification_started = time.time()
    classification_result = ClassificationStage().run(classification_ctx)
    classification_duration = round(time.time() - classification_started, 2)
    _write_json(Path(args.classification_out) if args.classification_out else None, classification_result.stage_output)

    job_with_classification = dict(job_with_jd)
    pre2 = dict(job_with_classification.get("pre_enrichment") or {})
    outputs2 = dict(pre2.get("outputs") or {})
    outputs2["classification"] = classification_result.stage_output
    pre2["outputs"] = outputs2
    job_with_classification["pre_enrichment"] = pre2

    application_ctx = _build_context(
        job_with_classification,
        stage_name="application_surface",
        model=args.application_model,
        transport=args.application_transport,
    )
    print(
        json.dumps(
            {
                "application_surface_config": {
                    "provider": application_ctx.config.provider,
                    "model": application_ctx.config.primary_model,
                    "transport": application_ctx.config.transport,
                    "max_web_queries": application_ctx.config.max_web_queries,
                    "max_fetches": application_ctx.config.max_fetches,
                }
            },
            indent=2,
        ),
        flush=True,
    )
    state["stage"] = "application_surface"
    state["started_at"] = time.time()
    print("[STAGE_START] name=application_surface mode=v2_only", flush=True)
    application_started = time.time()
    application_result = ApplicationSurfaceStage().run(application_ctx)
    application_duration = round(time.time() - application_started, 2)
    _write_json(Path(args.application_out) if args.application_out else None, application_result.stage_output)

    stop = True
    print(
        json.dumps(
            {
                "jd_facts": {
                    "duration_s": jd_duration,
                    "provider_used": jd_result.provider_used,
                    "model_used": jd_result.model_used,
                    "prompt_version": jd_result.prompt_version,
                },
                "classification": {
                    "duration_s": classification_duration,
                    "provider_used": classification_result.provider_used,
                    "model_used": classification_result.model_used,
                    "prompt_version": classification_result.prompt_version,
                },
                "application_surface": {
                    "duration_s": application_duration,
                    "provider_used": application_result.provider_used,
                    "model_used": application_result.model_used,
                    "prompt_version": application_result.prompt_version,
                    "output": application_result.stage_output,
                },
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
