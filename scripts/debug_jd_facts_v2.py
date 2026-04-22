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
from src.preenrich.stages.jd_facts import JDFactsStage
from src.preenrich.types import StageContext, get_stage_step_config


def _load_env() -> None:
    values = dotenv_values(Path.cwd() / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _build_context(job_doc: dict, *, model: str) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    jd_cs = str(pre.get("jd_checksum") or jd_checksum(description))
    company_cs = str(pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain")))
    snapshot_id = str(
        pre.get("input_snapshot_id")
        or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest())
    )
    attempt_number = int(pre.get("attempt_number", 0) or 0) + 1
    config = get_stage_step_config("jd_facts")
    config.provider = "codex"
    config.primary_model = model
    config.fallback_provider = "none"
    config.fallback_model = None
    return StageContext(
        job_doc=job_doc,
        jd_checksum=jd_cs,
        company_checksum=company_cs,
        input_snapshot_id=snapshot_id,
        attempt_number=attempt_number,
        config=config,
        shadow_mode=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated jd_facts V2 debug with heartbeat logging.")
    parser.add_argument("--job-id", required=True, help="Mongo level-2 ObjectId")
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    args = parser.parse_args()

    _load_env()
    if not os.getenv("MONGODB_URI"):
        raise RuntimeError("MONGODB_URI not set")

    os.environ["PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED"] = "false"
    if args.timeout_seconds > 0:
        os.environ["PREENRICH_CODEX_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    else:
        os.environ.pop("PREENRICH_CODEX_TIMEOUT_SECONDS", None)
        os.environ.pop("CODEX_TIMEOUT_SECONDS", None)

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
                    "model": args.model,
                    "timeout_seconds": None if args.timeout_seconds <= 0 else args.timeout_seconds,
                    "heartbeat_seconds": args.heartbeat_seconds,
                    "cwd": str(Path.cwd()),
                    "mongodb_uri_present": bool(os.getenv("MONGODB_URI")),
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

    ctx = _build_context(job, model=args.model)
    print(
        json.dumps(
            {
                "context": {
                    "jd_checksum": ctx.jd_checksum,
                    "company_checksum": ctx.company_checksum,
                    "input_snapshot_id": ctx.input_snapshot_id,
                    "attempt_number": ctx.attempt_number,
                }
            },
            indent=2,
        ),
        flush=True,
    )

    state["stage"] = "jd_facts"
    state["started_at"] = time.time()
    print("[STAGE_START] name=jd_facts mode=v2_only", flush=True)

    started = time.time()
    result = JDFactsStage().run(ctx)
    duration = round(time.time() - started, 2)

    stop = True
    merged = result.stage_output.get("merged_view") or {}
    print(
        json.dumps(
            {
                "result": {
                    "duration_s": duration,
                    "provider_used": result.provider_used,
                    "model_used": result.model_used,
                    "prompt_version": result.prompt_version,
                    "output_keys": sorted(result.output.keys()),
                    "stage_output_keys": sorted(result.stage_output.keys()),
                    "merged_view": {
                        "title": merged.get("title"),
                        "company": merged.get("company"),
                        "location": merged.get("location"),
                        "remote_policy": merged.get("remote_policy"),
                        "application_url": merged.get("application_url"),
                        "technical_skills": (merged.get("technical_skills") or [])[:12],
                    },
                }
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
