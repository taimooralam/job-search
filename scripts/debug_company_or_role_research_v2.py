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

from src.preenrich.blueprint_models import ApplicationProfile
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.research_transport import CodexResearchTransport
from src.preenrich.stages.research_enrichment import (
    _application_profile,
    _live_company_profile,
    _live_role_profile,
    _seed_company_profile,
)
from src.preenrich.types import StageContext, get_stage_step_config


def _load_env() -> None:
    values = dotenv_values(Path.cwd() / ".env")
    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _build_context(job_doc: dict, *, model: str, transport: str) -> StageContext:
    description = job_doc.get("description", "") or job_doc.get("job_description", "") or ""
    pre = job_doc.get("pre_enrichment") or {}
    jd_cs = str(pre.get("jd_checksum") or jd_checksum(description))
    company_cs = str(pre.get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain")))
    snapshot_id = str(pre.get("input_snapshot_id") or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest()))
    attempt_number = int(pre.get("attempt_number", 0) or 0) + 1
    config = get_stage_step_config("research_enrichment")
    config.provider = "codex"
    config.primary_model = model
    config.transport = transport
    config.fallback_provider = "none"
    config.fallback_model = None
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated company-only or role-only Codex research.")
    parser.add_argument("--surface", choices=["company", "role"], required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--research-model", default="gpt-5.2")
    parser.add_argument("--research-transport", default="codex_web_search")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--max-web-queries", type=int, default=2)
    parser.add_argument("--max-fetches", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--heartbeat-seconds", type=int, default=20)
    parser.add_argument("--jd-in", required=True)
    parser.add_argument("--classification-in", required=True)
    parser.add_argument("--application-in", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    _load_env()
    if not os.getenv("MONGODB_URI"):
        raise RuntimeError("MONGODB_URI not set")

    os.environ["WEB_RESEARCH_ENABLED"] = "true"
    os.environ["PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED"] = "true"
    os.environ["PREENRICH_RESEARCH_PROVIDER"] = "codex"
    os.environ["PREENRICH_RESEARCH_TRANSPORT"] = args.research_transport
    os.environ["PREENRICH_RESEARCH_FALLBACK_PROVIDER"] = "none"
    os.environ["PREENRICH_RESEARCH_FALLBACK_TRANSPORT"] = "none"
    os.environ["PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS"] = "false"
    os.environ["PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE"] = "false"
    os.environ["PREENRICH_RESEARCH_MAX_WEB_QUERIES"] = str(args.max_web_queries)
    os.environ["PREENRICH_RESEARCH_MAX_FETCHES"] = str(args.max_fetches)
    os.environ["PREENRICH_RESEARCH_TRANSPORT_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    os.environ["PREENRICH_REASONING_EFFORT_RESEARCH_ENRICHMENT"] = args.reasoning_effort

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    for noisy in ["urllib3", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.INFO)

    state = {"stage": args.surface, "started_at": time.time()}
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
                    "surface": args.surface,
                    "job_id": args.job_id,
                    "research_model": args.research_model,
                    "research_transport": args.research_transport,
                    "reasoning_effort": args.reasoning_effort,
                    "max_web_queries": args.max_web_queries,
                    "max_fetches": args.max_fetches,
                    "timeout_seconds": args.timeout_seconds,
                    "heartbeat_seconds": args.heartbeat_seconds,
                    "cwd": str(Path.cwd()),
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

    pre = dict(job.get("pre_enrichment") or {})
    outputs = dict(pre.get("outputs") or {})
    outputs["jd_facts"] = _read_json(args.jd_in)
    outputs["classification"] = _read_json(args.classification_in)
    outputs["application_surface"] = _read_json(args.application_in)
    pre["outputs"] = outputs
    job["pre_enrichment"] = pre

    ctx = _build_context(job, model=args.research_model, transport=args.research_transport)
    transport = CodexResearchTransport(ctx.config)
    application_profile = _application_profile(ctx, _seed_company_profile(ctx, ApplicationProfile()))
    company_seed = _seed_company_profile(ctx, application_profile)

    print(
        json.dumps(
            {
                "research_config": {
                    "provider": ctx.config.provider,
                    "model": ctx.config.primary_model,
                    "transport": ctx.config.transport,
                    "max_web_queries": ctx.config.max_web_queries,
                    "max_fetches": ctx.config.max_fetches,
                    "reasoning_effort": ctx.config.reasoning_effort,
                    "codex_workdir": ctx.config.codex_workdir,
                }
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )

    started = time.time()
    if args.surface == "company":
        profile, notes = _live_company_profile(ctx, transport, application_profile)
    else:
        profile, notes = _live_role_profile(ctx, transport, company_seed, application_profile)
    duration_s = round(time.time() - started, 2)

    stop = True
    payload = {
        "surface": args.surface,
        "duration_s": duration_s,
        "status": profile.status,
        "notes": notes,
        "profile": profile.model_dump(mode="json", exclude_none=True),
    }
    _write_json(Path(args.out) if args.out else None, payload)
    print(json.dumps(payload, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
