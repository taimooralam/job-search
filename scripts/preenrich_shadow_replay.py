"""
preenrich_shadow_replay.py — Phase 3 historical parity tool.

Selects already-processed level-2 jobs (lifecycle in completed/legacy with
live extracted_jd/persona/company_research fields), runs dispatcher.run_sequence()
with shadow_mode=True for each, and emits a JSONL report + Telegram summary.

Usage:
    python -m scripts.preenrich_shadow_replay --sample 20
    python -m scripts.preenrich_shadow_replay --sample 20 --tier quality
    python -m scripts.preenrich_shadow_replay --job-ids <oid1>,<oid2>
    python -m scripts.preenrich_shadow_replay --sample 5 --dry-run

Output:
    /var/lib/scout/preenrich_shadow_replay_<timestamp>.jsonl
    stdout summary
    Telegram notification
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/var/lib/scout")


# ---------------------------------------------------------------------------
# Stage instantiation
# ---------------------------------------------------------------------------

def _build_stages() -> List[Any]:
    """Instantiate all Phase 2 stages in DAG order."""
    from src.preenrich.stages import (
        JDStructureStage,
        JDExtractionStage,
        AIClassificationStage,
        PainPointsStage,
        AnnotationsStage,
        PersonaStage,
        CompanyResearchStage,
        RoleResearchStage,
    )
    return [
        JDStructureStage(),
        JDExtractionStage(),
        AIClassificationStage(),
        PainPointsStage(),
        AnnotationsStage(),
        PersonaStage(),
        CompanyResearchStage(),
        RoleResearchStage(),
    ]


# ---------------------------------------------------------------------------
# Job selection
# ---------------------------------------------------------------------------

def _select_jobs(
    db: Any,
    sample: int,
    tier: Optional[str],
    job_ids: Optional[List[str]],
) -> List[Dict[str, Any]]:
    """
    Select historical jobs for shadow replay.

    Filter: lifecycle in [completed, legacy] AND extracted_jd/persona/company_research
    all exist and are non-null. Optional tier filter. Returns up to `sample` docs.

    Args:
        db: PyMongo database handle
        sample: Max number of jobs to return
        tier: Optional tier string to filter by (e.g. "quality")
        job_ids: Optional explicit list of ObjectId hex strings

    Returns:
        List of job documents
    """
    if job_ids:
        oids = [ObjectId(j.strip()) for j in job_ids]
        docs = list(db["level-2"].find({"_id": {"$in": oids}}))
        logger.info("Explicit job selection: %d jobs", len(docs))
        return docs

    pipeline: List[Dict[str, Any]] = [
        {
            "$match": {
                "lifecycle": {"$in": ["completed", "legacy"]},
                "extracted_jd": {"$exists": True, "$ne": None},
                "persona": {"$exists": True, "$ne": None},
                "company_research": {"$exists": True, "$ne": None},
            }
        }
    ]

    if tier:
        pipeline[0]["$match"]["tier"] = tier

    pipeline.append({"$sample": {"size": sample}})

    docs = list(db["level-2"].aggregate(pipeline))
    logger.info("Selected %d historical jobs (tier=%s)", len(docs), tier or "any")
    return docs


# ---------------------------------------------------------------------------
# Per-job replay
# ---------------------------------------------------------------------------

def _replay_job(
    db: Any,
    job_doc: Dict[str, Any],
    stages: List[Any],
    worker_id: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """
    Run dispatcher.run_sequence() in shadow_mode for a single job.

    Args:
        db: PyMongo database handle
        job_doc: Full job document from level-2
        stages: Pre-built list of StageBase instances
        worker_id: Worker identity string for lease guard
        dry_run: If True, skip actual stage execution

    Returns:
        Report dict with job_id, stage outcomes, timings, cost
    """
    from src.preenrich.types import StageContext, StepConfig
    from src.preenrich.dispatcher import run_sequence
    from src.preenrich.checksums import jd_checksum as _jd_cs_fn
    from src.preenrich.checksums import company_checksum as _co_cs_fn

    job_id = str(job_doc["_id"])
    t_start = time.monotonic()

    # Acquire lease for shadow replay (upsert lease_owner)
    db["level-2"].update_one(
        {"_id": job_doc["_id"]},
        {"$set": {"lease_owner": worker_id}},
    )
    # Re-fetch so ctx has the updated doc
    job_doc = db["level-2"].find_one({"_id": job_doc["_id"]}) or job_doc

    try:
        jd_cs = _jd_cs_fn(job_doc.get("description", ""))
        company_cs = _co_cs_fn(
            job_doc.get("company", ""),
            job_doc.get("company_url", ""),
        )
    except Exception as exc:
        logger.warning("Checksum computation failed for %s: %s", job_id, exc)
        jd_cs = "sha256:unknown"
        company_cs = "sha256:unknown"

    ctx = StageContext(
        job_doc=job_doc,
        jd_checksum=jd_cs,
        company_checksum=company_cs,
        input_snapshot_id="shadow-replay",
        attempt_number=1,
        config=StepConfig(provider="claude", prompt_version="v1"),
        shadow_mode=True,
    )

    if dry_run:
        logger.info("[DRY-RUN] Would replay job %s — skipping stage execution", job_id)
        return {
            "job_id": job_id,
            "dry_run": True,
            "company": job_doc.get("company", ""),
            "title": job_doc.get("title", ""),
        }

    try:
        summary = run_sequence(db, ctx, stages, worker_id)
    except Exception as exc:
        logger.error("run_sequence failed for %s: %s", job_id, exc)
        summary = {"completed": [], "skipped": [], "failed": ["run_sequence"]}
    finally:
        # Release lease after shadow replay (restore to original lifecycle)
        db["level-2"].update_one(
            {"_id": job_doc["_id"]},
            {"$unset": {"lease_owner": ""}},
        )

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    # Read back shadow outputs and timings from Mongo
    refreshed = db["level-2"].find_one({"_id": job_doc["_id"]}) or {}
    pre = refreshed.get("pre_enrichment", {})
    stages_doc = pre.get("stages", {})

    stage_outcomes: Dict[str, Any] = {}
    total_cost_usd = 0.0
    for stage_name in summary.get("completed", []) + summary.get("skipped", []) + summary.get("failed", []):
        sdoc = stages_doc.get(stage_name, {})
        cost = sdoc.get("cost_usd") or 0.0
        total_cost_usd += cost
        stage_outcomes[stage_name] = {
            "status": sdoc.get("status", "unknown"),
            "duration_ms": sdoc.get("duration_ms"),
            "cost_usd": cost,
            "has_shadow_output": "shadow_output" in sdoc,
        }

    return {
        "job_id": job_id,
        "company": job_doc.get("company", ""),
        "title": job_doc.get("title", ""),
        "completed": summary.get("completed", []),
        "skipped": summary.get("skipped", []),
        "failed": summary.get("failed", []),
        "total_duration_ms": elapsed_ms,
        "total_cost_usd": round(total_cost_usd, 6),
        "stage_outcomes": stage_outcomes,
        "replayed_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main replay orchestration
# ---------------------------------------------------------------------------

def run_replay(
    sample: int,
    tier: Optional[str],
    job_ids: Optional[List[str]],
    dry_run: bool,
    mongodb_uri: Optional[str] = None,
) -> None:
    """
    Orchestrate the historical shadow replay.

    Args:
        sample: Number of jobs to replay
        tier: Optional tier filter
        job_ids: Optional explicit job ID list (overrides sample)
        dry_run: Skip actual LLM calls; just validate selection
        mongodb_uri: MongoDB connection URI (falls back to MONGODB_URI env var)
    """
    import pymongo

    uri = mongodb_uri or os.environ.get("MONGODB_URI", "")
    if not uri:
        logger.error("MONGODB_URI not set")
        sys.exit(1)

    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10_000)
    db = client["jobs"]
    worker_id = f"shadow-replay-{int(time.time())}"

    logger.info("Connecting to MongoDB for shadow replay (worker=%s)", worker_id)

    jobs = _select_jobs(db, sample, tier, job_ids)
    if not jobs:
        logger.warning("No eligible jobs found for replay")
        return

    if dry_run:
        logger.info("[DRY-RUN] %d jobs selected; skipping execution", len(jobs))
        for j in jobs:
            print(f"  {j['_id']}  {j.get('company', '')}  {j.get('title', '')}")
        return

    stages = _build_stages()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = OUTPUT_DIR / f"preenrich_shadow_replay_{timestamp}.jsonl"

    results: List[Dict[str, Any]] = []
    global_start = time.monotonic()

    for i, job_doc in enumerate(jobs, start=1):
        job_id_str = str(job_doc["_id"])
        logger.info("[%d/%d] Replaying %s (%s)", i, len(jobs), job_id_str, job_doc.get("company", ""))
        try:
            report = _replay_job(db, job_doc, stages, worker_id, dry_run=False)
        except Exception as exc:
            logger.error("Unexpected error for %s: %s", job_id_str, exc)
            report = {
                "job_id": job_id_str,
                "company": job_doc.get("company", ""),
                "title": job_doc.get("title", ""),
                "error": str(exc),
                "failed": ["unexpected"],
            }
        results.append(report)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report) + "\n")

    total_elapsed_s = time.monotonic() - global_start

    # --- Summary ---
    success_count = sum(1 for r in results if not r.get("failed") and not r.get("error"))
    fail_count = len(results) - success_count
    total_cost = sum(r.get("total_cost_usd", 0.0) for r in results)

    # Per-stage fail counts
    stage_fails: Dict[str, int] = {}
    for r in results:
        for sf in r.get("failed", []):
            stage_fails[sf] = stage_fails.get(sf, 0) + 1

    summary_lines = [
        f"Shadow Replay Complete — {len(results)} jobs",
        f"Success: {success_count}  Fail: {fail_count}",
        f"Total cost: ${total_cost:.4f}  Duration: {total_elapsed_s:.1f}s",
        f"Output: {out_path}",
    ]
    if stage_fails:
        summary_lines.append(f"Stage failures: {stage_fails}")

    for line in summary_lines:
        print(line)

    try:
        from src.common.telegram import send_telegram
        tg_lines = [
            "<b>Preenrich Shadow Replay</b>",
            f"Jobs: {len(results)} | Success: {success_count} | Fail: {fail_count}",
            f"Cost: ${total_cost:.4f} | Duration: {total_elapsed_s:.1f}s",
        ]
        if stage_fails:
            tg_lines.append(f"Stage failures: {stage_fails}")
        tg_lines.append(f"<code>{out_path}</code>")
        send_telegram("\n".join(tg_lines))
    except Exception as exc:
        logger.warning("Telegram notify failed: %s", exc)

    client.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Phase 3 historical shadow replay for preenrich stages."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="Number of historical jobs to replay (default: 20)",
    )
    parser.add_argument(
        "--source",
        default="historical",
        help="Source label (informational only; filter always uses historical lifecycle)",
    )
    parser.add_argument(
        "--tier",
        default=None,
        help="Optional tier filter (e.g. 'quality')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate job selection only; skip LLM calls",
    )
    parser.add_argument(
        "--job-ids",
        default=None,
        help="Comma-separated ObjectId hex strings to replay explicitly",
    )

    args = parser.parse_args()

    job_ids = [j.strip() for j in args.job_ids.split(",")] if args.job_ids else None

    run_replay(
        sample=args.sample,
        tier=args.tier,
        job_ids=job_ids,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
