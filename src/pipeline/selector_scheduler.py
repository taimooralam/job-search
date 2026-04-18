"""Idempotent scheduling helpers for iteration-3 selector runs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pymongo.database import Database

from src.pipeline.queue import WorkItemQueue
from src.pipeline.selector_common import load_selector_profiles
from src.pipeline.selector_store import SelectorStore


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SelectorFeatureFlags:
    """Feature flags for iteration-3 selector scheduling and execution."""

    enable_native_main: bool
    enable_native_profiles: bool
    use_mongo_input: bool
    enable_legacy_main_jsonl: bool
    enable_legacy_profile_pool: bool
    shadow_compare_main: bool
    shadow_compare_profiles: bool
    preenrich_handoff_mode: str
    disable_runner_post: bool
    write_scored_pool_compat: bool

    @classmethod
    def from_env(cls) -> "SelectorFeatureFlags":
        return cls(
            enable_native_main=_env_flag("SCOUT_SELECTOR_ENABLE_NATIVE_MAIN", False),
            enable_native_profiles=_env_flag("SCOUT_SELECTOR_ENABLE_NATIVE_PROFILES", False),
            use_mongo_input=_env_flag("SCOUT_SELECTOR_USE_MONGO_INPUT", False),
            enable_legacy_main_jsonl=_env_flag("SCOUT_SELECTOR_ENABLE_LEGACY_MAIN_JSONL", True),
            enable_legacy_profile_pool=_env_flag("SCOUT_SELECTOR_ENABLE_LEGACY_PROFILE_POOL", True),
            shadow_compare_main=_env_flag("SCOUT_SELECTOR_SHADOW_COMPARE_MAIN", False),
            shadow_compare_profiles=_env_flag("SCOUT_SELECTOR_SHADOW_COMPARE_PROFILES", False),
            preenrich_handoff_mode=os.getenv("SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE", "selected_lifecycle"),
            disable_runner_post=_env_flag("SCOUT_SELECTOR_DISABLE_RUNNER_POST", True),
            write_scored_pool_compat=_env_flag("SCOUT_SELECTOR_WRITE_SCORED_POOL_COMPAT", True),
        )

    def validate(self) -> None:
        """Reject unsafe native/legacy ownership combinations."""
        if (self.enable_native_main or self.enable_native_profiles or self.shadow_compare_main or self.shadow_compare_profiles) and not self.use_mongo_input:
            raise RuntimeError("Native or shadow selector modes require SCOUT_SELECTOR_USE_MONGO_INPUT=true")
        if self.enable_native_main and self.enable_legacy_main_jsonl:
            raise RuntimeError("Native main selector and legacy main JSONL selector cannot both own the same window")
        if self.enable_native_profiles and self.enable_legacy_profile_pool:
            raise RuntimeError("Native profile selectors and legacy profile pool selectors cannot both own the same window")
        if self.enable_native_main and self.shadow_compare_main:
            raise RuntimeError("Enable either native main ownership or main shadow compare, not both")
        if self.enable_native_profiles and self.shadow_compare_profiles:
            raise RuntimeError("Enable either native profile ownership or profile shadow compare, not both")
        if (self.enable_native_main or self.enable_native_profiles) and self.preenrich_handoff_mode != "selected_lifecycle":
            raise RuntimeError("Native selector runs require SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle")


class SelectorScheduler:
    """Create idempotent selector run records plus run-level work items."""

    def __init__(self, db: Database):
        self.db = db
        self.queue = WorkItemQueue(db)
        self.store = SelectorStore(db)
        self.queue.ensure_indexes()
        self.store.ensure_indexes()

    def schedule_main_run(
        self,
        *,
        scheduled_for: datetime,
        trigger_mode: str = "timer",
        now: Optional[datetime] = None,
    ) -> dict:
        """Schedule one main selector run for the given window."""
        run, created = self.store.create_or_get_run(
            run_kind="main",
            scheduled_for=_normalize_time(scheduled_for),
            trigger_mode=trigger_mode,
            now=now,
        )
        enqueue = self.queue.enqueue(
            task_type="select.run.main",
            lane="selector",
            consumer_mode="native_selector",
            subject_type="selector_run",
            subject_id=run["run_id"],
            priority=100,
            available_at=run["scheduled_for"],
            max_attempts=3,
            idempotency_key=f"selectorrun:main:{run['scheduled_for'].isoformat()}",
            correlation_id=run["run_id"],
            payload={
                "run_kind": "main",
                "profile_name": None,
                "scheduled_for": run["scheduled_for"],
                "trigger_mode": trigger_mode,
            },
            result_ref={"run_id": run["run_id"]},
            now=now,
        )
        return {"run": run, "run_created": created, "work_item_created": enqueue.created, "work_item": enqueue.document}

    def schedule_profile_run(
        self,
        *,
        profile_name: str,
        scheduled_for: datetime,
        trigger_mode: str = "timer",
        now: Optional[datetime] = None,
    ) -> dict:
        """Schedule one profile selector run for the given window."""
        if profile_name not in load_selector_profiles():
            raise ValueError(f"Unknown selector profile: {profile_name}")

        run, created = self.store.create_or_get_run(
            run_kind="profile",
            scheduled_for=_normalize_time(scheduled_for),
            trigger_mode=trigger_mode,
            profile_name=profile_name,
            now=now,
        )
        enqueue = self.queue.enqueue(
            task_type="select.run.profile",
            lane="selector",
            consumer_mode="native_selector",
            subject_type="selector_run",
            subject_id=run["run_id"],
            priority=100,
            available_at=run["scheduled_for"],
            max_attempts=3,
            idempotency_key=f"selectorrun:profile:{profile_name}:{run['scheduled_for'].isoformat()}",
            correlation_id=run["run_id"],
            payload={
                "run_kind": "profile",
                "profile_name": profile_name,
                "scheduled_for": run["scheduled_for"],
                "trigger_mode": trigger_mode,
            },
            result_ref={"run_id": run["run_id"]},
            now=now,
        )
        return {"run": run, "run_created": created, "work_item_created": enqueue.created, "work_item": enqueue.document}


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc, second=0, microsecond=0)
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)
