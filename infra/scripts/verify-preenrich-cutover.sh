#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

stage_units=(
  scout-preenrich-worker@jd_structure.service
  scout-preenrich-worker@jd_extraction.service
  scout-preenrich-worker@ai_classification.service
  scout-preenrich-worker@pain_points.service
  scout-preenrich-worker@annotations.service
  scout-preenrich-worker@persona.service
  scout-preenrich-worker@company_research.service
  scout-preenrich-worker@role_research.service
)

sweeper_timers=(
  preenrich-root-enqueuer.timer
  preenrich-next-stage-sweeper.timer
  preenrich-stage-sweeper.timer
  preenrich-cv-ready-sweeper.timer
  preenrich-snapshot-invalidator.timer
)

for unit in "${stage_units[@]}"; do
  systemctl is-active --quiet "$unit"
done

for timer in "${sweeper_timers[@]}"; do
  systemctl is-active --quiet "$timer"
done

python - <<'PY'
import os
from pymongo import MongoClient

uri = os.environ["MONGODB_URI"]
db = MongoClient(uri)["jobs"]

work_indexes = list(db["work_items"].list_indexes())
level2_indexes = list(db["level-2"].list_indexes())
stage_run_indexes = list(db["preenrich_stage_runs"].list_indexes())
job_run_indexes = list(db["preenrich_job_runs"].list_indexes())

required = [
    any(idx.get("key") == {"idempotency_key": 1} and idx.get("unique") for idx in work_indexes),
    any(idx.get("key") == {"status": 1, "task_type": 1, "available_at": 1, "priority": -1} for idx in work_indexes),
    any(idx.get("key") == {"lane": 1, "status": 1, "lease_expires_at": 1} for idx in work_indexes),
    any(idx.get("key") == {"subject_id": 1, "task_type": 1, "status": 1} for idx in work_indexes),
    any(idx.get("key") == {"lifecycle": 1, "pre_enrichment.orchestration": 1, "selected_at": 1} for idx in level2_indexes),
    any(idx.get("key") == {"pre_enrichment.cv_ready_at": 1} for idx in level2_indexes),
    any(idx.get("key") == {"pre_enrichment.input_snapshot_id": 1} for idx in level2_indexes),
    any(idx.get("key") == {"pre_enrichment.pending_next_stages.idempotency_key": 1} for idx in level2_indexes),
    any(idx.get("key") == {"started_at": 1, "status": 1} for idx in stage_run_indexes),
    any(idx.get("key") == {"job_id": 1, "stage": 1, "started_at": -1} for idx in stage_run_indexes),
    any(idx.get("key") == {"started_at": 1, "status": 1} for idx in job_run_indexes),
]
if not all(required):
    raise SystemExit("missing one or more required iteration-4 indexes")

if db["level-2"].count_documents({
    "pre_enrichment.orchestration": "dag",
    "$or": [{"lease_owner": {"$ne": None}}, {"lease_expires_at": {"$ne": None}}],
}) > 0:
    raise SystemExit("dag-owned docs still hold legacy per-job leases")

duplicates = list(
    db["work_items"].aggregate([
        {"$group": {"_id": "$idempotency_key", "count": {"$sum": 1}}},
        {"$match": {"_id": {"$ne": None}, "count": {"$gt": 1}}},
        {"$limit": 1},
    ])
)
if duplicates:
    raise SystemExit("duplicate work_items.idempotency_key detected")

legacy_remaining = db["level-2"].count_documents({"lifecycle": {"$in": ["ready", "queued", "running"]}})
if legacy_remaining > 0:
    raise SystemExit("legacy ready/queued/running docs remain after drain")

recent_cv_ready = list(
    db["level-2"].aggregate([
        {
            "$match": {
                "lifecycle": "cv_ready",
                "$expr": {
                    "$gte": [
                        "$pre_enrichment.cv_ready_at",
                        {"$dateSubtract": {"startDate": "$$NOW", "unit": "hour", "amount": 24}},
                    ]
                },
            }
        },
        {"$count": "count"},
    ])
)
if not recent_cv_ready or recent_cv_ready[0]["count"] <= 0:
    raise SystemExit("no cv_ready written in the last 24h")
PY

python scripts/ops/verify_langfuse_retention.py >/tmp/verify-langfuse-retention.json

exit 0
