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
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.stages.jd_facts import JDFactsStage
from src.preenrich.types import StageContext, StepConfig


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
    return StageContext(
        job_doc=job_doc,
        jd_checksum=jd_cs,
        company_checksum=company_cs,
        input_snapshot_id=snapshot_id,
        attempt_number=attempt_number,
        config=StepConfig(
            provider="codex",
            primary_model=model,
            fallback_provider="none",
            fallback_model=None,
        ),
        shadow_mode=False,
    )


def _write_json(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated jd_facts + classification debug with heartbeat logging.")
    parser.add_argument("--job-id", required=True, help="Mongo level-2 ObjectId")
    parser.add_argument("--jd-model", default="gpt-5.2")
    parser.add_argument("--classification-model", default="gpt-5.4-mini")
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--jd-out", default="")
    parser.add_argument("--classification-out", default="")
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
                    "jd_model": args.jd_model,
                    "classification_model": args.classification_model,
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

    jd_ctx = _build_context(dict(job), model=args.jd_model)
    state["stage"] = "jd_facts"
    state["started_at"] = time.time()
    print("[STAGE_START] name=jd_facts mode=v2_only", flush=True)
    jd_started = time.time()
    jd_result = JDFactsStage().run(jd_ctx)
    jd_duration = round(time.time() - jd_started, 2)
    _write_json(Path(args.jd_out) if args.jd_out else None, jd_result.stage_output)

    job_for_classification = dict(job)
    pre = dict(job_for_classification.get("pre_enrichment") or {})
    outputs = dict(pre.get("outputs") or {})
    outputs["jd_facts"] = jd_result.stage_output
    pre["outputs"] = outputs
    pre["jd_checksum"] = jd_ctx.jd_checksum
    pre["company_checksum"] = jd_ctx.company_checksum
    pre["input_snapshot_id"] = jd_ctx.input_snapshot_id
    pre["attempt_number"] = jd_ctx.attempt_number
    job_for_classification["pre_enrichment"] = pre

    classification_ctx = _build_context(job_for_classification, model=args.classification_model)
    state["stage"] = "classification"
    state["started_at"] = time.time()
    print("[STAGE_START] name=classification mode=v2_only", flush=True)
    classification_started = time.time()
    classification_result = ClassificationStage().run(classification_ctx)
    classification_duration = round(time.time() - classification_started, 2)
    _write_json(Path(args.classification_out) if args.classification_out else None, classification_result.stage_output)

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
                    "output": classification_result.stage_output,
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
