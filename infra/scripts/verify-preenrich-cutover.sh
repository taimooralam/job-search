#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

blueprint_enabled="${PREENRICH_BLUEPRINT_ENABLED:-false}"
persona_compat_enabled="${PREENRICH_PERSONA_COMPAT_ENABLED:-true}"

if [[ "$blueprint_enabled" == "true" ]]; then
  stage_units=(
    scout-preenrich-worker@jd_structure.service
    scout-preenrich-worker@jd_facts.service
    scout-preenrich-worker@classification.service
    scout-preenrich-worker@research_enrichment.service
    scout-preenrich-worker@application_surface.service
    scout-preenrich-worker@job_inference.service
    scout-preenrich-worker@job_hypotheses.service
    scout-preenrich-worker@annotations.service
    scout-preenrich-worker@cv_guidelines.service
    scout-preenrich-worker@blueprint_assembly.service
  )
  if [[ "$persona_compat_enabled" == "true" ]]; then
    stage_units+=(scout-preenrich-worker@persona_compat.service)
  fi
else
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
fi

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
blueprint_enabled = os.environ.get("PREENRICH_BLUEPRINT_ENABLED", "false").lower() == "true"
persona_compat_enabled = os.environ.get("PREENRICH_PERSONA_COMPAT_ENABLED", "true").lower() == "true"


def has_index(indexes, expected_key, *, unique=None, name=None):
    for idx in indexes:
        key_items = list((idx.get("key") or {}).items())
        if key_items != expected_key:
            continue
        if unique is not None and bool(idx.get("unique")) != unique:
            continue
        if name is not None and idx.get("name") != name:
            continue
        return True
    return False

work_indexes = list(db["work_items"].list_indexes())
level2_indexes = list(db["level-2"].list_indexes())
stage_run_indexes = list(db["preenrich_stage_runs"].list_indexes())
job_run_indexes = list(db["preenrich_job_runs"].list_indexes())

required = [
    has_index(work_indexes, [("idempotency_key", 1)], unique=True),
    has_index(work_indexes, [("status", 1), ("task_type", 1), ("available_at", 1), ("priority", -1)]),
    has_index(work_indexes, [("lane", 1), ("status", 1), ("lease_expires_at", 1)]),
    has_index(work_indexes, [("subject_id", 1), ("task_type", 1), ("status", 1)]),
    has_index(level2_indexes, [("lifecycle", 1), ("pre_enrichment.orchestration", 1), ("selected_at", 1)]),
    has_index(level2_indexes, [("pre_enrichment.cv_ready_at", 1)]),
    has_index(level2_indexes, [("pre_enrichment.input_snapshot_id", 1)]),
    has_index(level2_indexes, [("pre_enrichment.pending_next_stages.idempotency_key", 1)]),
    has_index(stage_run_indexes, [("started_at", 1), ("status", 1)]),
    has_index(stage_run_indexes, [("job_id", 1), ("stage", 1), ("started_at", -1)]),
    has_index(job_run_indexes, [("started_at", 1), ("status", 1)]),
]
if not all(required):
    raise SystemExit("missing one or more required iteration-4 indexes")

if blueprint_enabled:
    required_blueprint = [
        has_index(list(db["jd_facts"].list_indexes()), [("job_id", 1), ("jd_text_hash", 1), ("extractor_version", 1), ("judge_prompt_version", 1)], unique=True),
        has_index(list(db["research_enrichment"].list_indexes()), [("job_id", 1), ("input_snapshot_id", 1), ("research_version", 1)], unique=True),
        has_index(list(db["job_inference"].list_indexes()), [("jd_facts_id", 1), ("research_enrichment_id", 1), ("prompt_version", 1), ("taxonomy_version", 1)], unique=True),
        has_index(list(db["job_hypotheses"].list_indexes()), [("jd_facts_id", 1), ("research_enrichment_id", 1), ("prompt_version", 1), ("taxonomy_version", 1)], unique=True),
        has_index(list(db["cv_guidelines"].list_indexes()), [("jd_facts_id", 1), ("job_inference_id", 1), ("research_enrichment_id", 1), ("prompt_version", 1)], unique=True),
        has_index(list(db["job_blueprint"].list_indexes()), [("job_id", 1), ("blueprint_version", 1)], unique=True),
        has_index(list(db["research_company_cache"].list_indexes()), [("cache_key", 1)], unique=True),
        has_index(list(db["research_application_cache"].list_indexes()), [("cache_key", 1)], unique=True),
        has_index(list(db["research_stakeholder_cache"].list_indexes()), [("cache_key", 1)], unique=True),
        has_index(level2_indexes, [("pre_enrichment.job_blueprint_refs.job_blueprint_id", 1)]),
        has_index(level2_indexes, [("pre_enrichment.job_blueprint_status", 1), ("pre_enrichment.job_blueprint_updated_at", -1)]),
    ]
    if not all(required_blueprint):
        raise SystemExit("missing one or more required iteration-4.1 blueprint indexes")

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

if blueprint_enabled:
    snapshot_leaks = db["level-2"].count_documents(
        {"pre_enrichment.job_blueprint_snapshot.job_hypotheses": {"$exists": True}}
    )
    if snapshot_leaks > 0:
        raise SystemExit("job_hypotheses leaked into job_blueprint_snapshot")

    stage_targets = [
        "jd_structure",
        "jd_facts",
        "classification",
        "research_enrichment",
        "application_surface",
        "job_inference",
        "job_hypotheses",
        "annotations",
        "cv_guidelines",
        "blueprint_assembly",
    ]
    if persona_compat_enabled:
        stage_targets.append("persona_compat")
    for stage in stage_targets:
        if db["work_items"].count_documents({"task_type": f"preenrich.{stage}"}) == 0:
            raise SystemExit(f"no work_items observed for blueprint stage {stage}")

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
