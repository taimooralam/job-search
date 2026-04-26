"""Mongo-native selector workers for iteration 3."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient

from src.common.scout_queue import append_to_pool
from src.pipeline.discovery import SearchDiscoveryStore
from src.pipeline.queue import WorkItemQueue
from src.pipeline.selector_common import (
    DEFAULT_MAIN_QUOTA,
    compute_main_selector_plan,
    compute_profile_selector_plan,
    load_selector_profiles,
    upsert_level2_job,
    upsert_low_tier_level1_job,
    utc_now,
)
from src.pipeline.selector_scheduler import SelectorFeatureFlags
from src.pipeline.selector_store import SelectorStore, pool_expiry_from
from src.pipeline.tracing import SelectorTracingSession

logger = logging.getLogger("scout_selector_worker")

ACTIVE_LIFECYCLES = {
    "selected",
    "preenriching",
    "ready_for_cv",
    "cv_generating",
    "reviewing",
    "ready_to_apply",
    "published",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Scout native selector worker")
    parser.add_argument("--limit", type=int, default=10, help="Maximum selector runs to process")
    parser.add_argument("--lease-seconds", type=int, default=600, help="Lease duration for claimed selector work items")
    parser.add_argument("--worker-id", type=str, default=None, help="Override generated worker id")
    parser.add_argument("--trigger-mode", type=str, default="single_tick", choices=["single_tick", "manual", "daemon"])
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint for the native selector worker."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    flags = SelectorFeatureFlags.from_env()
    flags.validate()
    if not (flags.enable_native_main or flags.enable_native_profiles or flags.shadow_compare_main or flags.shadow_compare_profiles):
        logger.info("Native selector worker disabled by feature flags")
        return 0

    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI not set")

    db = MongoClient(mongodb_uri)["jobs"]
    worker = NativeSelectorWorker(db, flags=flags, worker_id=args.worker_id or build_worker_id())
    result = worker.run_once(max_items=args.limit, lease_seconds=args.lease_seconds, trigger_mode=args.trigger_mode)
    logger.info("Native selector result: %s", result)
    return 0


class NativeSelectorWorker:
    """Claim selector run work items and execute native selector logic."""

    def __init__(self, db, *, flags: SelectorFeatureFlags, worker_id: str) -> None:
        self.db = db
        self.flags = flags
        self.worker_id = worker_id
        self.queue = WorkItemQueue(db)
        self.discovery = SearchDiscoveryStore(db)
        self.selector = SelectorStore(db)
        self.queue.ensure_indexes()
        self.discovery.ensure_indexes()
        self.selector.ensure_indexes()
        self.level1 = db["level-1"]
        self.level2 = db["level-2"]
        self.main_quota = int(os.getenv("SCOUT_SELECTOR_MAIN_QUOTA", str(DEFAULT_MAIN_QUOTA)))

    def run_once(
        self,
        *,
        max_items: int,
        lease_seconds: int,
        trigger_mode: str,
        now: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Process up to max_items selector runs."""
        current_time = now or utc_now()
        del trigger_mode  # Run docs already carry their trigger mode.

        stats = {
            "claimed": 0,
            "completed": 0,
            "retried": 0,
            "deadlettered": 0,
        }

        for _ in range(max_items):
            item = self.queue.claim_next(
                lane="selector",
                consumer_mode="native_selector",
                worker_name=self.worker_id,
                lease_seconds=lease_seconds,
                now=current_time,
            )
            if item is None:
                break

            stats["claimed"] += 1
            run_id = str(item.get("subject_id"))
            run = self.selector.get_run(run_id)
            if run is None:
                self.queue.mark_deadletter(item["_id"], error="selector_run_missing", now=current_time)
                stats["deadlettered"] += 1
                continue

            claimed_run = self.selector.claim_run(run_id, worker_id=self.worker_id, now=current_time)
            if claimed_run is None:
                claimed_run = self.selector.get_run(run_id)
                if claimed_run and claimed_run.get("status") == "completed":
                    self.queue.mark_done(item["_id"], result_ref={"run_id": run_id, "status": "completed"}, now=current_time)
                    stats["completed"] += 1
                    continue
                self.queue.mark_failed(item["_id"], error=f"selector_run_not_claimable:{run_id}", now=current_time)
                stats["retried"] += 1
                continue

            run = claimed_run
            tracer = SelectorTracingSession(
                run_id=run["run_id"],
                session_id=run.get("langfuse_session_id") or run["run_id"],
                metadata={
                    "worker_id": self.worker_id,
                    "run_kind": run.get("run_kind"),
                    "profile_name": run.get("profile_name"),
                    "trigger_mode": run.get("trigger_mode"),
                },
            )
            self.selector.attach_trace_metadata(
                run["run_id"],
                trace_id=tracer.trace_id,
                trace_url=tracer.trace_url,
                now=current_time,
            )

            try:
                if item["task_type"] == "select.run.main":
                    summary = self._process_main_run(run, now=current_time, tracer=tracer)
                else:
                    summary = self._process_profile_run(run, now=current_time, tracer=tracer)

                self.selector.finalize_run(
                    run["run_id"],
                    status="completed",
                    stats=summary["stats"],
                    errors=summary.get("errors", []),
                    decisions=summary.get("decisions"),
                    diff=summary.get("diff"),
                    now=current_time,
                )
                self.queue.mark_done(
                    item["_id"],
                    result_ref={"run_id": run["run_id"], "status": "completed", "stats": summary["stats"]},
                    now=current_time,
                )
                tracer.complete(output=summary)
                stats["completed"] += 1
            except Exception as exc:
                logger.exception("Selector run %s failed: %s", run["run_id"], exc)
                if run["run_kind"] == "main":
                    self.selector.release_main_leases_for_run(run["run_id"], now=current_time)
                else:
                    self.selector.release_profile_leases_for_run(run["profile_name"], run["run_id"], now=current_time)

                work_item = self.queue.mark_failed(item["_id"], error=str(exc), now=current_time)
                failed_status = "failed" if work_item.get("status") == "failed" else "deadletter"
                self.selector.finalize_run(
                    run["run_id"],
                    status=failed_status,
                    stats=(run.get("stats") or {}),
                    errors=[{"message": str(exc), "run_id": run["run_id"]}],
                    now=current_time,
                )
                tracer.record_stage(f"{failed_status}_transition", {"run_id": run["run_id"], "error": str(exc)})
                tracer.complete(output={"failed": True, "error": str(exc)})
                if failed_status == "failed":
                    stats["retried"] += 1
                else:
                    stats["deadlettered"] += 1

        return stats

    def _process_main_run(
        self,
        run: dict[str, Any],
        *,
        now: datetime,
        tracer: SelectorTracingSession,
    ) -> dict[str, Any]:
        candidates = self.selector.load_main_candidates(cutoff_at=run["cutoff_at"], run_id=run["run_id"])
        candidates = [candidate for candidate in candidates if not _already_processed_main(candidate, run["run_id"])]
        tracer.record_stage("candidate_query", {"run_id": run["run_id"], "candidates_seen": len(candidates)})
        plan = compute_main_selector_plan(candidates, db=self.db, quota=self.main_quota)

        tracer.record_stage("blacklist_filter", {"count": len(plan.filtered_blacklist)})
        tracer.record_stage("non_english_filter", {"count": len(plan.filtered_non_english)})
        tracer.record_stage("score_filter", {"count": len(plan.filtered_score)})
        tracer.record_stage("cross_location_consolidation", {"count": len(plan.duplicate_cross_location)})
        tracer.record_stage("dedupe", {"count": len(plan.duplicate_db)})

        if run.get("trigger_mode") == "shadow_compare":
            diff = self._build_main_shadow_diff(candidates, plan)
            return {
                "stats": plan.stats,
                "diff": diff,
                "decisions": _summarize_plan_decisions(plan),
                "errors": [],
            }

        self.selector.mark_main_candidates_leased([candidate["_hit_id"] for candidate in candidates], run_id=run["run_id"], now=now)
        expires_at = pool_expiry_from(now)

        pool_hit_ids = {str(candidate["_hit_id"]) for candidate in plan.pool_available}
        for candidate in plan.pool_available:
            self.selector.set_pool_status(candidate["_hit_id"], status="available", pooled_at=now, expires_at=expires_at, now=now)
        for bucket in (
            plan.filtered_blacklist,
            plan.filtered_non_english,
            plan.filtered_score,
            plan.duplicate_cross_location,
            plan.duplicate_db,
        ):
            for candidate in bucket:
                if str(candidate["_hit_id"]) not in pool_hit_ids:
                    self.selector.set_pool_status(candidate["_hit_id"], status="not_applicable", pooled_at=None, expires_at=None, now=now)

        for candidate in plan.filtered_blacklist:
            self.selector.apply_main_decision(candidate["_hit_id"], run_id=run["run_id"], decision="filtered_blacklist", reason="blacklist", now=now)
        for candidate in plan.filtered_non_english:
            self.selector.apply_main_decision(candidate["_hit_id"], run_id=run["run_id"], decision="filtered_non_english", reason="non_english", now=now)
        for candidate in plan.filtered_score:
            self.selector.apply_main_decision(candidate["_hit_id"], run_id=run["run_id"], decision="filtered_score", reason="score<=0", now=now)
        for candidate in plan.duplicate_cross_location:
            self.selector.apply_main_decision(
                candidate["_hit_id"],
                run_id=run["run_id"],
                decision="duplicate_cross_location",
                reason=f"kept:{candidate.get('_kept_job_id')}",
                now=now,
            )
        for candidate in plan.duplicate_db:
            self.selector.apply_main_decision(candidate["_hit_id"], run_id=run["run_id"], decision="duplicate_db", reason=candidate.get("_decision_reason"), now=now)

        tracer.record_stage("tier_split", {"tier_low": len(plan.tier_low), "tier_c_plus": plan.stats["inserted_level2"]})

        for candidate in plan.tier_low:
            result = upsert_low_tier_level1_job(self.level1, candidate, now=now)
            self.selector.apply_main_decision(
                candidate["_hit_id"],
                run_id=run["run_id"],
                decision="inserted_level1",
                reason="tier_low",
                level1_upserted_at=now,
                now=now,
            )
            if result.get("level1_job_id") is not None:
                tracer.record_stage("level1_write", {"hit_id": str(candidate["_hit_id"]), "level1_job_id": str(result["level1_job_id"])})

        for candidate in plan.inserted_level2_only:
            result = upsert_level2_job(
                self.level2,
                candidate,
                source_tag="linkedin_scout_cron",
                selected_for_preenrich=False,
                status=None,
                now=now,
            )
            self.selector.apply_main_decision(
                candidate["_hit_id"],
                run_id=run["run_id"],
                decision="inserted_level2_only",
                reason="tier_c_plus",
                rank=candidate.get("_rank"),
                level2_job_id=result.get("level2_job_id"),
                now=now,
            )

        for candidate in plan.selected_for_preenrich:
            result = upsert_level2_job(
                self.level2,
                candidate,
                source_tag="linkedin_scout_cron",
                selected_for_preenrich=True,
                selected_at=now,
                status="under processing",
                now=now,
            )
            self.selector.apply_main_decision(
                candidate["_hit_id"],
                run_id=run["run_id"],
                decision="selected_for_preenrich",
                reason="top_n",
                rank=candidate.get("_rank"),
                selected_at=now,
                level2_job_id=result.get("level2_job_id"),
                now=now,
            )

        tracer.record_stage("level2_write", {"inserted_level2": plan.stats["inserted_level2"]})
        tracer.record_stage("top_n_handoff", {"selected_for_preenrich": plan.stats["selected_for_preenrich"]})

        if self.flags.write_scored_pool_compat and plan.pool_available:
            append_to_pool([_strip_internal_fields(candidate) for candidate in plan.pool_available])

        return {
            "stats": plan.stats,
            "decisions": _summarize_plan_decisions(plan),
            "errors": [],
        }

    def _process_profile_run(
        self,
        run: dict[str, Any],
        *,
        now: datetime,
        tracer: SelectorTracingSession,
    ) -> dict[str, Any]:
        profiles = load_selector_profiles()
        profile_name = run.get("profile_name")
        if profile_name not in profiles:
            raise ValueError(f"Unknown selector profile: {profile_name}")
        profile = profiles[profile_name]

        candidates = self.selector.load_profile_candidates(profile_name=profile_name, cutoff_at=run["cutoff_at"], now=now)
        owned_elsewhere: list[dict[str, Any]] = []
        eligible: list[dict[str, Any]] = []
        for candidate in candidates:
            main_state = ((candidate.get("_hit_document") or {}).get("selection") or {}).get("main") or {}
            linked_doc = self.selector.get_level2_doc(main_state.get("level2_job_id"))
            if main_state.get("status") in {"pending", "leased"}:
                owned_elsewhere.append({**candidate, "_decision_reason": "main_inflight"})
            elif linked_doc and linked_doc.get("lifecycle") in ACTIVE_LIFECYCLES:
                owned_elsewhere.append({**candidate, "_decision_reason": f"main_lifecycle:{linked_doc.get('lifecycle')}"})
            else:
                eligible.append(candidate)

        tracer.record_stage("candidate_query", {"run_id": run["run_id"], "candidates_seen": len(candidates)})
        plan = compute_profile_selector_plan(eligible, db=self.db, profile=profile, now=now)
        plan.duplicate_db.extend(owned_elsewhere)

        tracer.record_stage("blacklist_filter", {"count": len(plan.filtered_blacklist)})
        tracer.record_stage("non_english_filter", {"count": len(plan.filtered_non_english)})
        tracer.record_stage("score_filter", {"count": len(plan.filtered_score)})
        tracer.record_stage("profile_ranking", {"selected": len(plan.selected), "discarded_quota": len(plan.discarded_quota)})
        tracer.record_stage("profile_specific_selections", {"profile_name": profile_name, "selected": len(plan.selected)})

        if run.get("trigger_mode") == "shadow_compare":
            diff = self._build_profile_shadow_diff(eligible, plan, profile_name=profile_name)
            return {
                "stats": plan.stats,
                "diff": diff,
                "decisions": _summarize_profile_decisions(plan),
                "errors": [],
            }

        self.selector.mark_profile_candidates_leased([candidate["_hit_id"] for candidate in candidates], profile_name=profile_name, run_id=run["run_id"], now=now)

        for candidate in plan.filtered_blacklist:
            self.selector.apply_profile_decision(candidate["_hit_id"], profile_name=profile_name, run_id=run["run_id"], decision="filtered_blacklist", reason="blacklist", now=now)
        for candidate in plan.filtered_non_english:
            self.selector.apply_profile_decision(candidate["_hit_id"], profile_name=profile_name, run_id=run["run_id"], decision="filtered_non_english", reason="non_english", now=now)
        for candidate in plan.filtered_score:
            self.selector.apply_profile_decision(candidate["_hit_id"], profile_name=profile_name, run_id=run["run_id"], decision="filtered_score", reason="score<=0", now=now)
        for candidate in plan.filtered_location:
            self.selector.apply_profile_decision(candidate["_hit_id"], profile_name=profile_name, run_id=run["run_id"], decision="filtered_location", reason="location_mismatch", now=now)
        for candidate in plan.discarded_quota:
            self.selector.apply_profile_decision(
                candidate["_hit_id"],
                profile_name=profile_name,
                run_id=run["run_id"],
                decision="discarded_quota",
                reason="quota_miss",
                rank_score=candidate.get("_rank_score"),
                now=now,
            )
        for candidate in plan.duplicate_db:
            self.selector.apply_profile_decision(
                candidate["_hit_id"],
                profile_name=profile_name,
                run_id=run["run_id"],
                decision="duplicate_db",
                reason=candidate.get("_decision_reason"),
                now=now,
            )
            self.selector.set_pool_status(candidate["_hit_id"], status="consumed", pooled_at=now, expires_at=now, now=now)

        for candidate in plan.selected:
            result = upsert_level2_job(
                self.level2,
                candidate,
                source_tag=profile.get("source_tag", f"scout_dim_{profile_name}"),
                selected_for_preenrich=True,
                selected_at=now,
                status=None,
                now=now,
            )
            self.selector.apply_profile_decision(
                candidate["_hit_id"],
                profile_name=profile_name,
                run_id=run["run_id"],
                decision="profile_selected",
                reason="profile_top_n",
                rank_score=candidate.get("_rank_score"),
                selected_at=now,
                level2_job_id=result.get("level2_job_id"),
                now=now,
            )
            self.selector.set_pool_status(candidate["_hit_id"], status="consumed", pooled_at=now, expires_at=now, now=now)

        tracer.record_stage("level2_write", {"inserted_level2": plan.stats["inserted_level2"]})
        tracer.record_stage("top_n_handoff", {"selected_for_preenrich": plan.stats["selected_for_preenrich"]})

        return {
            "stats": plan.stats,
            "decisions": _summarize_profile_decisions(plan),
            "errors": [],
        }

    def _build_main_shadow_diff(self, candidates: list[dict[str, Any]], native_plan: Any) -> dict[str, Any]:
        legacy_main = _load_legacy_module("legacy_scout_selector", "scripts/scout_selector_cron.py")

        legacy_candidates = [_strip_internal_fields(candidate) for candidate in candidates]
        legacy_filtered = legacy_main.filter_blacklisted(list(legacy_candidates))
        legacy_filtered = [
            candidate for candidate in legacy_filtered
            if not legacy_main.is_non_english_jd(candidate.get("title", ""), candidate.get("description", ""))
        ]
        legacy_filtered = [candidate for candidate in legacy_filtered if candidate.get("score", 0) > 0]
        legacy_filtered = legacy_main.consolidate_by_location(legacy_filtered)
        legacy_new = legacy_main.dedupe_against_db(legacy_filtered, self.db)
        legacy_tier_c_plus = [candidate for candidate in legacy_new if candidate.get("tier") in ("A", "B", "C")]
        legacy_tier_c_plus.sort(key=lambda candidate: candidate.get("score", 0), reverse=True)
        legacy_selected_ids = [candidate.get("job_id") for candidate in legacy_tier_c_plus[: self.main_quota]]

        native_seen = [candidate.get("job_id") for candidate in candidates]
        native_selected_ids = [candidate.get("job_id") for candidate in native_plan.selected_for_preenrich]
        return {
            "legacy_candidate_ids": native_seen,
            "native_candidate_ids": native_seen,
            "legacy_selected_ids": legacy_selected_ids,
            "native_selected_ids": native_selected_ids,
            "selected_ids_match": legacy_selected_ids == native_selected_ids,
            "filtered_counts_match": {
                "blacklist": len(native_plan.filtered_blacklist),
                "non_english": len(native_plan.filtered_non_english),
                "score": len(native_plan.filtered_score),
                "duplicate_cross_location": len(native_plan.duplicate_cross_location),
                "duplicate_db": len(native_plan.duplicate_db),
            },
        }

    def _build_profile_shadow_diff(
        self,
        candidates: list[dict[str, Any]],
        native_plan: Any,
        *,
        profile_name: str,
    ) -> dict[str, Any]:
        legacy_profile = _load_legacy_module("legacy_scout_dimensional", "scripts/scout_dimensional_selector.py")

        profile = legacy_profile.load_profile(profile_name)
        legacy_candidates = [_strip_internal_fields(candidate) for candidate in candidates]
        legacy_pool = legacy_profile.filter_blacklisted(list(legacy_candidates))
        legacy_pool = [
            candidate for candidate in legacy_pool
            if not legacy_profile.is_non_english_jd(candidate.get("title", ""), candidate.get("description", ""))
        ]
        legacy_pool = [candidate for candidate in legacy_pool if candidate.get("score", 0) > 0]
        legacy_matched = [
            candidate for candidate in legacy_pool
            if legacy_profile.matches_location(candidate, profile["location_patterns"], mode=profile.get("location_mode", "any"))
        ]
        legacy_new = legacy_profile.dedupe_against_db(legacy_matched, self.db)
        for candidate in legacy_new:
            candidate["_rank_score"] = legacy_profile.compute_rank_score(candidate, profile.get("rank_boosts", {}))
        legacy_new.sort(key=lambda candidate: candidate["_rank_score"], reverse=True)
        legacy_selected_ids = [candidate.get("job_id") for candidate in legacy_new[: profile["quota"]]]

        native_selected_ids = [candidate.get("job_id") for candidate in native_plan.selected]
        native_ranked_ids = [candidate.get("job_id") for candidate in native_plan.selected + native_plan.discarded_quota]
        return {
            "legacy_candidate_ids": [candidate.get("job_id") for candidate in candidates],
            "native_candidate_ids": [candidate.get("job_id") for candidate in candidates],
            "legacy_selected_ids": legacy_selected_ids,
            "native_selected_ids": native_selected_ids,
            "selected_ids_match": legacy_selected_ids == native_selected_ids,
            "native_ranked_ids": native_ranked_ids,
        }


def build_worker_id() -> str:
    """Build a unique selector worker id."""
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def _already_processed_main(candidate: dict[str, Any], run_id: str) -> bool:
    main_state = (((candidate.get("_hit_document") or {}).get("selection") or {}).get("main") or {})
    return main_state.get("selector_run_id") == run_id and main_state.get("status") == "completed"


def _strip_internal_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidate.items()
        if not key.startswith("_")
    }


def _summarize_plan_decisions(plan: Any) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for candidate in plan.selected_for_preenrich:
        decisions.append(
            {
                "hit_id": str(candidate["_hit_id"]),
                "decision": "selected_for_preenrich",
                "rank": candidate.get("_rank"),
                "score": candidate.get("score"),
                "job_id": candidate.get("job_id"),
            }
        )
    for candidate in plan.inserted_level2_only[:25]:
        decisions.append(
            {
                "hit_id": str(candidate["_hit_id"]),
                "decision": "inserted_level2_only",
                "rank": candidate.get("_rank"),
                "score": candidate.get("score"),
                "job_id": candidate.get("job_id"),
            }
        )
    for candidate in plan.duplicate_db[:25]:
        decisions.append(
            {
                "hit_id": str(candidate["_hit_id"]),
                "decision": "duplicate_db",
                "score": candidate.get("score"),
                "job_id": candidate.get("job_id"),
            }
        )
    return decisions[:100]


def _summarize_profile_decisions(plan: Any) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for candidate in plan.selected:
        decisions.append(
            {
                "hit_id": str(candidate["_hit_id"]),
                "decision": "profile_selected",
                "rank_score": candidate.get("_rank_score"),
                "job_id": candidate.get("job_id"),
            }
        )
    for candidate in plan.discarded_quota[:25]:
        decisions.append(
            {
                "hit_id": str(candidate["_hit_id"]),
                "decision": "discarded_quota",
                "rank_score": candidate.get("_rank_score"),
                "job_id": candidate.get("job_id"),
            }
        )
    return decisions[:100]


def _load_legacy_module(module_name: str, relative_path: str):
    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load legacy selector module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main())
