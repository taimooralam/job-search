"""Iteration-4.1 blueprint feature flags, taxonomy, and snapshot helpers."""

from __future__ import annotations

import os
import subprocess
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


def _string(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() or default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except Exception:
        return default


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
    return True


def jd_facts_v2_live_compat_write_enabled() -> bool:
    return _flag("PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED", False)


def jd_facts_escalate_on_failure_enabled() -> bool:
    return _flag("PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED", False)


def jd_facts_escalation_model() -> str:
    return os.getenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", "gpt-5.4").strip() or "gpt-5.4"


def jd_facts_escalation_models() -> list[str]:
    raw = os.getenv("PREENRICH_JD_FACTS_ESCALATION_MODELS", "").strip()
    if raw:
        models = [item.strip() for item in raw.split(",") if item.strip()]
        if models:
            return models
    return [jd_facts_escalation_model()]


def classification_v2_enabled() -> bool:
    return True


def classification_shadow_mode_enabled() -> bool:
    return _flag("PREENRICH_CLASSIFICATION_SHADOW_MODE_ENABLED", False)


def classification_ai_taxonomy_enabled() -> bool:
    return _flag("PREENRICH_CLASSIFICATION_AI_TAXONOMY_ENABLED", True)


def classification_v2_ai_compat_write_enabled() -> bool:
    return _flag("PREENRICH_CLASSIFICATION_V2_AI_COMPAT_WRITE_ENABLED", False)


def classification_escalate_on_failure_enabled() -> bool:
    return _flag("PREENRICH_CLASSIFICATION_ESCALATE_ON_FAILURE_ENABLED", True)


def classification_escalation_model() -> str:
    return os.getenv("PREENRICH_CLASSIFICATION_ESCALATION_MODEL", "gpt-5.2").strip() or "gpt-5.2"


def classification_high_confidence_threshold() -> float:
    return float(os.getenv("PREENRICH_CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD", "0.60").strip() or "0.60")


def classification_short_circuit_margin() -> float:
    return float(os.getenv("PREENRICH_CLASSIFICATION_SHORT_CIRCUIT_MARGIN", "0.20").strip() or "0.20")


def classification_disambiguation_margin() -> float:
    return float(os.getenv("PREENRICH_CLASSIFICATION_DISAMBIGUATION_MARGIN", "0.15").strip() or "0.15")


def web_research_enabled() -> bool:
    return _flag("WEB_RESEARCH_ENABLED", False)


def research_enrichment_v2_enabled() -> bool:
    return _flag("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", False)


def research_shadow_mode_enabled() -> bool:
    return _flag("PREENRICH_RESEARCH_SHADOW_MODE_ENABLED", False)


def research_live_compat_write_enabled() -> bool:
    return _flag("PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED", False)


def research_ui_snapshot_expanded_enabled() -> bool:
    return _flag("PREENRICH_RESEARCH_UI_SNAPSHOT_EXPANDED_ENABLED", False)


def research_provider() -> str:
    return _string("PREENRICH_RESEARCH_PROVIDER", "codex")


def research_transport() -> str:
    return _string("PREENRICH_RESEARCH_TRANSPORT", "codex_web_search")


def research_fallback_provider() -> str:
    return _string("PREENRICH_RESEARCH_FALLBACK_PROVIDER", "none")


def research_fallback_transport() -> str:
    return _string("PREENRICH_RESEARCH_FALLBACK_TRANSPORT", "none")


def research_enable_stakeholders() -> bool:
    return _flag("PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS", False)


def research_enable_outreach_guidance() -> bool:
    return _flag("PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE", False)


def research_require_source_attribution() -> bool:
    return _flag("PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION", True)


def research_max_web_queries() -> int:
    return _int("PREENRICH_RESEARCH_MAX_WEB_QUERIES", 6)


def research_max_fetches() -> int:
    return _int("PREENRICH_RESEARCH_MAX_FETCHES", 4)


def research_company_cache_ttl_hours() -> int:
    return _int("PREENRICH_RESEARCH_COMPANY_CACHE_TTL_HOURS", 168)


def research_application_cache_ttl_hours() -> int:
    return _int("PREENRICH_RESEARCH_APPLICATION_CACHE_TTL_HOURS", 48)


def research_stakeholder_cache_ttl_hours() -> int:
    return _int("PREENRICH_RESEARCH_STAKEHOLDER_CACHE_TTL_HOURS", 72)


def stakeholder_surface_enabled() -> bool:
    return _flag("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", False)


def stakeholder_surface_real_discovery_enabled() -> bool:
    return _flag("PREENRICH_STAKEHOLDER_SURFACE_REAL_DISCOVERY_ENABLED", True)


def stakeholder_surface_require_source_attribution() -> bool:
    return _flag("PREENRICH_STAKEHOLDER_SURFACE_REQUIRE_SOURCE_ATTRIBUTION", True)


def stakeholder_surface_max_web_queries() -> int:
    return _int("PREENRICH_STAKEHOLDER_SURFACE_MAX_WEB_QUERIES", 6)


def stakeholder_surface_max_fetches() -> int:
    return _int("PREENRICH_STAKEHOLDER_SURFACE_MAX_FETCHES", 8)


@lru_cache(maxsize=1)
def current_git_sha() -> str:
    env_sha = _string("PREENRICH_GIT_SHA", "")
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def research_prompt_file_path() -> str:
    return str((PROJECT_ROOT / "src" / "preenrich" / "blueprint_prompts.py").resolve())


def research_transport_tuple() -> dict[str, str]:
    return {
        "provider": research_provider(),
        "transport": research_transport(),
        "fallback_provider": research_fallback_provider(),
        "fallback_transport": research_fallback_transport(),
    }


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
    if classification_shadow_mode_enabled() and classification_v2_ai_compat_write_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_CLASSIFICATION_SHADOW_MODE_ENABLED=true "
            "cannot be combined with PREENRICH_CLASSIFICATION_V2_AI_COMPAT_WRITE_ENABLED=true"
        )
    if classification_escalate_on_failure_enabled() and not classification_escalation_model():
        raise RuntimeError(
            "Invalid preenrich config: escalation enabled requires "
            "PREENRICH_CLASSIFICATION_ESCALATION_MODEL"
        )
    if research_shadow_mode_enabled() and not research_enrichment_v2_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_RESEARCH_SHADOW_MODE_ENABLED=true "
            "requires PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true"
        )
    if research_live_compat_write_enabled() and not research_enrichment_v2_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED=true "
            "requires PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true"
        )
    if research_ui_snapshot_expanded_enabled() and not research_enrichment_v2_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_RESEARCH_UI_SNAPSHOT_EXPANDED_ENABLED=true "
            "requires PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true"
        )
    if research_enable_outreach_guidance() and not research_enable_stakeholders():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE=true "
            "requires PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS=true"
        )
    if research_live_compat_write_enabled() and not research_require_source_attribution():
        raise RuntimeError(
            "Invalid preenrich config: live compat write requires "
            "PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION=true"
        )
    if stakeholder_surface_enabled() and not blueprint_enabled():
        raise RuntimeError(
            "Invalid preenrich config: PREENRICH_STAKEHOLDER_SURFACE_ENABLED=true "
            "requires PREENRICH_BLUEPRINT_ENABLED=true"
        )
