"""Backfill historical preenrich states for iteration 4."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pymongo import MongoClient

from src.preenrich.root_enqueuer import build_stage_states
from src.preenrich.stage_registry import iter_stage_definitions


REPORT_DIR = Path("reports")
LEGACY_COMPLETE = "completed"
LEGACY_FAILED = "failed"
LEGACY_FAILED_TERMINAL = "failed_terminal"
LEGACY_IN_PROGRESS = "in_progress"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_backfill(
    db: Any,
    *,
    now: Optional[datetime] = None,
    dry_run: bool = True,
    report_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Apply the §12.5 preenrich backfill rules, dry-run by default."""
    current_time = now or utc_now()
    counter: Counter[str] = Counter()
    changed_docs: list[dict[str, Any]] = []
    for doc in db["level-2"].find({}):
        update, tags = _compute_backfill_update(doc, current_time)
        for tag in tags:
            counter[tag] += 1
        if update:
            changed_docs.append({"_id": str(doc["_id"]), "tags": tags, "update": update})
            if not dry_run:
                db["level-2"].update_one({"_id": doc["_id"]}, update)

    report = {
        "dry_run": dry_run,
        "generated_at": current_time.isoformat(),
        "transition_counts": dict(counter),
        "changed_docs": changed_docs,
    }
    if report_path is None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"backfill-preenrich-{current_time.strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    report["report_path"] = str(report_path)
    return report


def _compute_backfill_update(doc: dict[str, Any], now: datetime) -> tuple[dict[str, Any], list[str]]:
    pre = doc.get("pre_enrichment") or {}
    stage_states = pre.get("stage_states") or {}
    legacy_stages = pre.get("stages") or {}
    tags: list[str] = []
    set_doc: dict[str, Any] = {}

    if not stage_states and legacy_stages:
        derived = _derive_stage_states_from_legacy(pre)
        if derived:
            set_doc["pre_enrichment.stage_states"] = derived
            stage_states = derived
            tags.append("bootstrap_stage_states")

    if stage_states:
        remapped = _remap_failed_terminal(stage_states)
        if remapped is not None:
            set_doc["pre_enrichment.stage_states"] = remapped
            stage_states = remapped
            tags.append("align_deadletter_enum")

    lifecycle = doc.get("lifecycle")
    if lifecycle == "ready":
        cv_ready_at = _cv_ready_at(stage_states)
        if cv_ready_at is not None:
            set_doc["lifecycle"] = "cv_ready"
            set_doc["pre_enrichment.cv_ready_at"] = cv_ready_at
            tags.append("ready_to_cv_ready")
        else:
            tags.append("legacy_partial_ready")
    elif lifecycle == "ready_for_cv":
        cv_ready_at = _cv_ready_at(stage_states)
        if cv_ready_at is not None:
            set_doc["lifecycle"] = "cv_ready"
            set_doc["pre_enrichment.cv_ready_at"] = cv_ready_at
            tags.append("ready_for_cv_to_cv_ready")
    elif lifecycle == "running" and _is_stale_lease(doc, now):
        set_doc["lifecycle"] = "stale"
        tags.append("running_to_stale")

    if lifecycle == "preenriching" and pre.get("orchestration") is None:
        set_doc["pre_enrichment.orchestration"] = "legacy"
        tags.append("bootstrap_legacy_orchestration")

    if not set_doc:
        return {}, tags
    set_doc["updated_at"] = now
    return {"$set": set_doc}, tags


def _derive_stage_states_from_legacy(pre: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = str(pre.get("input_snapshot_id") or "")
    stage_states = build_stage_states(snapshot_id)
    for stage in iter_stage_definitions():
        legacy_state = (pre.get("stages") or {}).get(stage.name) or {}
        if not legacy_state:
            continue
        status = legacy_state.get("status")
        mapped_status = {
            LEGACY_COMPLETE: "completed",
            LEGACY_FAILED: "failed",
            LEGACY_FAILED_TERMINAL: "deadletter",
            LEGACY_IN_PROGRESS: "pending",
        }.get(status, "pending")
        stage_states[stage.name].update(
            {
                "status": mapped_status,
                "attempt_count": legacy_state.get("retry_count", 0),
                "started_at": legacy_state.get("started_at"),
                "completed_at": legacy_state.get("completed_at"),
                "input_snapshot_id": legacy_state.get("input_snapshot_id") or snapshot_id,
                "attempt_token": legacy_state.get("attempt_token"),
                "jd_checksum_at_completion": legacy_state.get("jd_checksum_at_completion"),
                "provider": legacy_state.get("provider"),
                "model": legacy_state.get("model"),
                "prompt_version": legacy_state.get("prompt_version"),
                "last_error": _legacy_error(legacy_state),
                "tokens_input": legacy_state.get("tokens_input"),
                "tokens_output": legacy_state.get("tokens_output"),
                "cost_usd": legacy_state.get("cost_usd"),
            }
        )
    return stage_states


def _legacy_error(legacy_state: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not legacy_state.get("failure_context"):
        return None
    return {
        "class": legacy_state.get("status"),
        "message": legacy_state.get("failure_context"),
        "at": legacy_state.get("last_error_at"),
    }


def _remap_failed_terminal(stage_states: dict[str, Any]) -> Optional[dict[str, Any]]:
    changed = False
    updated = {}
    for name, state in stage_states.items():
        current = dict(state)
        if current.get("status") == LEGACY_FAILED_TERMINAL:
            current["status"] = "deadletter"
            changed = True
        updated[name] = current
    return updated if changed else None


def _cv_ready_at(stage_states: dict[str, Any]) -> Optional[datetime]:
    completed_at_values: list[datetime] = []
    for stage in iter_stage_definitions():
        state = stage_states.get(stage.name) or {}
        if state.get("status") != "completed":
            return None
        completed_at = state.get("completed_at")
        if completed_at:
            completed_at_values.append(completed_at)
    if not completed_at_values:
        return None
    return max(completed_at_values)


def _is_stale_lease(doc: dict[str, Any], now: datetime) -> bool:
    lease_expires_at = doc.get("lease_expires_at")
    if lease_expires_at is None:
        return True
    if lease_expires_at.tzinfo is None:
        lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
    return lease_expires_at <= now


def _get_db() -> Any:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return MongoClient(uri)["jobs"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical preenrich states for iteration 4")
    parser.add_argument("--apply", action="store_true", help="Apply updates instead of dry-run")
    args = parser.parse_args()
    report = run_backfill(_get_db(), dry_run=not args.apply)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
