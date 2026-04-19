"""Iteration-4.1 blueprint feature flags, taxonomy, and snapshot helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.preenrich.schema import input_snapshot_id

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
JOB_ARCHETYPES_PATH = PROJECT_ROOT / "data" / "job_archetypes.yaml"

BLUEPRINT_DAG_VERSION = "iteration4.1.v1"
BLUEPRINT_REQUIRED_SET_VERSION = "iteration4.1.required.v1"
BLUEPRINT_SNAPSHOT_VERSION = "job_blueprint.v1"


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default).lower()).strip().lower() == "true"


def blueprint_enabled() -> bool:
    return _flag("PREENRICH_BLUEPRINT_ENABLED", False)


def blueprint_snapshot_write_enabled() -> bool:
    return _flag("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", False)


def blueprint_ui_read_enabled() -> bool:
    return _flag("PREENRICH_BLUEPRINT_UI_READ_ENABLED", False)


def blueprint_compat_projections_enabled() -> bool:
    return _flag("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", True)


def persona_compat_enabled() -> bool:
    return _flag("PREENRICH_PERSONA_COMPAT_ENABLED", True)


def application_surface_enabled() -> bool:
    return _flag("PREENRICH_APPLICATION_SURFACE_ENABLED", True)


def jd_facts_v2_enabled() -> bool:
    return _flag("PREENRICH_JD_FACTS_V2_ENABLED", False)


def jd_facts_v2_live_compat_write_enabled() -> bool:
    return _flag("PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED", False)


def jd_facts_escalate_on_failure_enabled() -> bool:
    return _flag("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", True)


def jd_facts_escalation_model() -> str:
    return os.getenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", "gpt-5.4").strip() or "gpt-5.4"


def web_research_enabled() -> bool:
    return _flag("WEB_RESEARCH_ENABLED", False)


def legacy_shadow_mode_enabled() -> bool:
    return _flag("PREENRICH_SHADOW_MODE", False)


@lru_cache(maxsize=1)
def load_job_taxonomy() -> dict[str, Any]:
    with JOB_ARCHETYPES_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid taxonomy payload in {JOB_ARCHETYPES_PATH}")
    return payload


def taxonomy_version() -> str:
    payload = load_job_taxonomy()
    value = payload.get("version")
    if not value:
        raise RuntimeError(f"Missing taxonomy version in {JOB_ARCHETYPES_PATH}")
    return str(value)


def current_dag_version() -> str:
    return BLUEPRINT_DAG_VERSION if blueprint_enabled() else "iteration4.v1"


def current_required_set_version() -> str | None:
    return BLUEPRINT_REQUIRED_SET_VERSION if blueprint_enabled() else None


def current_input_snapshot_id(
    jd_checksum: str,
    company_checksum: str,
    *,
    dag_version: str | None = None,
) -> str:
    return input_snapshot_id(
        jd_checksum,
        company_checksum,
        dag_version or current_dag_version(),
        taxonomy_version=taxonomy_version() if blueprint_enabled() else None,
        required_set_version=current_required_set_version(),
    )


def validate_blueprint_feature_flags() -> None:
    if blueprint_ui_read_enabled() and not blueprint_snapshot_write_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_BLUEPRINT_UI_READ_ENABLED=true "
            "requires PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED=true"
        )
    if not blueprint_compat_projections_enabled() and not blueprint_ui_read_enabled():
        raise RuntimeError(
            "Invalid preenrich config: disabling both compat projections and UI snapshot reads "
            "leaves no reader path"
        )
    if blueprint_snapshot_write_enabled() and legacy_shadow_mode_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_SHADOW_MODE and "
            "PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED cannot both be true"
        )
    if jd_facts_v2_live_compat_write_enabled() and not jd_facts_v2_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED=true "
            "requires PREENRICH_JD_FACTS_V2_ENABLED=true"
        )
