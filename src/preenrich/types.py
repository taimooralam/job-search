"""
Pre-enrichment type definitions.

Defines the core data structures used across the pre-enrichment worker:
- StageStatus: lifecycle states for individual enrichment stages
- StageResult: output from a single stage run
- StageContext: input context passed to each stage
- attempt_token: deterministic idempotency key (excludes provider/model per §2.3)
"""

import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from src.preenrich.schema import attempt_token as _schema_attempt_token


class StageStatus(str, Enum):
    """Lifecycle states for an individual pre-enrichment stage."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    FAILED_TERMINAL = "failed_terminal"
    STALE = "stale"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """
    Output from a single stage run.

    All fields are optional so that partial results can be persisted
    even when a stage fails before producing full output.
    """

    # The Mongo patch to apply on completion (top-level legacy fields)
    output: Dict[str, Any] = field(default_factory=dict)
    # Durable stage-local output stored under pre_enrichment.outputs.<stage>.
    stage_output: Dict[str, Any] = field(default_factory=dict)
    # Collection-backed artifact writes performed by StageWorker before Phase A.
    artifact_writes: List["ArtifactWrite"] = field(default_factory=list)

    # Provenance metadata
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    prompt_version: Optional[str] = None

    # Cost/usage tracking
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost_usd: Optional[float] = None

    # Timing
    duration_ms: Optional[int] = None

    # Optional skip context
    skip_reason: Optional[str] = None
    cache_source_job_id: Optional[str] = None

    # Provider fallback provenance (Phase 2b)
    # List of attempt dicts: {provider, model, outcome, error, duration_ms, ...}
    provider_attempts: List[Dict[str, Any]] = field(default_factory=list)
    # Outcome of the first non-success attempt when fallback was triggered
    provider_fallback_reason: Optional[str] = None


@dataclass
class ArtifactWrite:
    """A collection-backed artifact to upsert during stage completion."""

    collection: str
    unique_filter: Dict[str, Any]
    document: Dict[str, Any]
    ref_name: str


# Per-stage Codex-primary defaults.  Env overrides:
#   PREENRICH_PROVIDER_<STAGE_UPPER>       e.g. PREENRICH_PROVIDER_JD_EXTRACTION=claude
#   PREENRICH_MODEL_<STAGE_UPPER>          e.g. PREENRICH_MODEL_JD_EXTRACTION=gpt-5.4
#   PREENRICH_FALLBACK_MODEL_<STAGE_UPPER> e.g. PREENRICH_FALLBACK_MODEL_JD_EXTRACTION=claude-haiku-4-5
_STAGE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "jd_extraction": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
    },
    "ai_classification": {
        "provider": "codex",
        "primary_model": "gpt-5.4-mini",
        "fallback_provider": "none",
    },
    "pain_points": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
    },
    "persona": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
    },
    "jd_facts": {
        "provider": "codex",
        "primary_model": "gpt-5.2",
        "fallback_provider": "none",
        "allow_repo_context": "false",
    },
    "classification": {
        "provider": "codex",
        "primary_model": "gpt-5.4-mini",
        "fallback_provider": "none",
        "allow_repo_context": "false",
    },
    "research_enrichment": {
        "provider": "codex",
        "primary_model": "gpt-5.2",
        "fallback_provider": "none",
        "transport": "codex_web_search",
        "fallback_transport": "none",
        "allow_repo_context": "false",
    },
    "stakeholder_surface": {
        "provider": "codex",
        "primary_model": "gpt-5.2",
        "fallback_provider": "none",
        "transport": "codex_web_search",
        "fallback_transport": "none",
        "allow_repo_context": "false",
    },
    "pain_point_intelligence": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
        "fallback_model": "gpt-5.2",
        "transport": "none",
        "fallback_transport": "none",
        "allow_repo_context": "false",
    },
    "presentation_contract": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
        "transport": "none",
        "fallback_transport": "none",
        "allow_repo_context": "false",
    },
    "application_surface": {
        "provider": "codex",
        "primary_model": "gpt-5.2",
        "fallback_provider": "none",
        "transport": "codex_web_search",
        "fallback_transport": "none",
        "allow_repo_context": "false",
    },
    "job_inference": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
    },
    "job_hypotheses": {
        "provider": "codex",
        "primary_model": "gpt-5.4-mini",
        "fallback_provider": "none",
    },
    "cv_guidelines": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
    },
    "persona_compat": {
        "provider": "codex",
        "primary_model": "gpt-5.4",
        "fallback_provider": "none",
    },
    "blueprint_assembly": {
        "provider": "none",
        "fallback_provider": "none",
    },
}


def _stage_env_key(stage: str, field_name: str) -> str:
    """Build the env-var key for a stage field override."""
    return f"PREENRICH_{field_name.upper()}_{stage.upper()}"


def get_stage_step_config(stage_name: str) -> "StepConfig":
    """
    Build a StepConfig for a named stage with env-var overrides.

    Reads PREENRICH_PROVIDER_<STAGE>, PREENRICH_MODEL_<STAGE>,
    PREENRICH_FALLBACK_MODEL_<STAGE> from the environment, falling back
    to per-stage defaults in _STAGE_DEFAULTS, then to the generic StepConfig
    defaults.

    Args:
        stage_name: Stage identifier (e.g. "jd_extraction").

    Returns:
        StepConfig with provider/model/fallback fields populated.
    """
    defaults = _STAGE_DEFAULTS.get(stage_name, {})

    provider = os.environ.get(
        _stage_env_key(stage_name, "PROVIDER"),
        defaults.get("provider", "claude"),
    )
    primary_model = os.environ.get(
        _stage_env_key(stage_name, "MODEL"),
        defaults.get("primary_model"),
    )
    fallback_provider = os.environ.get(
        _stage_env_key(stage_name, "FALLBACK_PROVIDER"),
        defaults.get("fallback_provider", "none"),
    )
    fallback_model = os.environ.get(
        _stage_env_key(stage_name, "FALLBACK_MODEL"),
        defaults.get("fallback_model"),
    )
    transport = os.environ.get(
        _stage_env_key(stage_name, "TRANSPORT"),
        defaults.get("transport", "none"),
    )
    fallback_transport = os.environ.get(
        _stage_env_key(stage_name, "FALLBACK_TRANSPORT"),
        defaults.get("fallback_transport", "none"),
    )
    allow_repo_context = os.environ.get(
        _stage_env_key(stage_name, "ALLOW_REPO_CONTEXT"),
        defaults.get("allow_repo_context", "true"),
    ).strip().lower() == "true"
    codex_workdir = os.environ.get(
        _stage_env_key(stage_name, "CODEX_WORKDIR"),
        "",
    ).strip() or None
    reasoning_effort = os.environ.get(
        _stage_env_key(stage_name, "REASONING_EFFORT"),
        os.environ.get("PREENRICH_CODEX_REASONING_EFFORT", ""),
    ).strip() or None

    if stage_name in {"research_enrichment", "application_surface", "stakeholder_surface"}:
        from src.preenrich.blueprint_config import (
            research_fallback_provider,
            research_fallback_transport,
            research_max_fetches,
            research_max_web_queries,
            research_provider,
            research_transport,
            stakeholder_surface_max_fetches,
            stakeholder_surface_max_web_queries,
        )

        provider = os.environ.get(_stage_env_key(stage_name, "PROVIDER"), research_provider())
        fallback_provider = os.environ.get(_stage_env_key(stage_name, "FALLBACK_PROVIDER"), research_fallback_provider())
        transport = os.environ.get(_stage_env_key(stage_name, "TRANSPORT"), research_transport())
        fallback_transport = os.environ.get(_stage_env_key(stage_name, "FALLBACK_TRANSPORT"), research_fallback_transport())
        if stage_name == "stakeholder_surface":
            max_web_queries = stakeholder_surface_max_web_queries()
            max_fetches = stakeholder_surface_max_fetches()
        else:
            max_web_queries = research_max_web_queries()
            max_fetches = research_max_fetches()
    else:
        max_web_queries = 0
        max_fetches = 0

    if stage_name == "pain_point_intelligence":
        from src.preenrich.blueprint_config import pain_point_supplemental_web_enabled

        if pain_point_supplemental_web_enabled():
            from src.preenrich.blueprint_config import research_max_fetches, research_max_web_queries

            max_web_queries = min(research_max_web_queries(), 2)
            max_fetches = min(research_max_fetches(), 2)
        else:
            max_web_queries = 0
            max_fetches = 0

    return StepConfig(
        provider=provider,
        primary_model=primary_model,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        transport=transport,
        fallback_transport=fallback_transport,
        max_web_queries=max_web_queries,
        max_fetches=max_fetches,
        allow_repo_context=allow_repo_context,
        codex_workdir=codex_workdir or default_codex_workdir(stage_name=stage_name, allow_repo_context=allow_repo_context),
        reasoning_effort=reasoning_effort,
    )


def default_codex_workdir(*, stage_name: str, allow_repo_context: bool) -> str:
    if allow_repo_context:
        return str(Path.cwd())
    path = Path(tempfile.gettempdir()) / "job-search-codex-isolated" / stage_name
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@dataclass
class StepConfig:
    """
    Per-stage provider/model routing configuration.

    Phase 2b fields:
        primary_model:    Codex model identifier (e.g. "gpt-5.4")
        fallback_provider: Provider to try on Codex failure (e.g. "claude")
        fallback_model:   Model for the fallback provider (e.g. "claude-haiku-4-5")
    """

    provider: str = "claude"  # "claude" | "codex" | "embedding" | "none"
    model: Optional[str] = None
    prompt_version: str = "v1"
    # Phase 2b: Codex-primary fields
    primary_model: Optional[str] = None
    fallback_provider: str = "none"
    fallback_model: Optional[str] = None
    transport: str = "none"
    fallback_transport: str = "none"
    max_web_queries: int = 0
    max_fetches: int = 0
    allow_repo_context: bool = True
    codex_workdir: Optional[str] = None
    reasoning_effort: Optional[str] = None


@runtime_checkable
class PreenrichTracerHandle(Protocol):
    """Stage-facing tracing contract for preenrich spans and events."""

    trace: Any
    trace_id: Optional[str]
    trace_url: Optional[str]
    enabled: bool

    def start_substage_span(
        self,
        stage_name: str,
        substage: str,
        metadata: Dict[str, Any],
    ) -> Any:
        """Start a child span under the active stage span."""

    def end_span(self, span: Any, *, output: Optional[Dict[str, Any]] = None) -> None:
        """Finish a span that was started by this tracing handle."""

    def record_event(self, name: str, metadata: Dict[str, Any]) -> None:
        """Emit an event correlated to the active preenrich trace."""


class NullPreenrichTracingHandle:
    """No-op tracing handle so stage code never branches on `None`."""

    trace: Any = None
    trace_id: Optional[str] = None
    trace_url: Optional[str] = None
    enabled: bool = False

    def start_substage_span(
        self,
        stage_name: str,
        substage: str,
        metadata: Dict[str, Any],
    ) -> Any:
        return None

    def end_span(self, span: Any, *, output: Optional[Dict[str, Any]] = None) -> None:
        return None

    def record_event(self, name: str, metadata: Dict[str, Any]) -> None:
        return None


@dataclass
class StageContext:
    """
    Immutable context passed to each stage run.

    Captures the job document and checksums at the moment the worker
    claims the job so that all stages in a sequence use a consistent
    input snapshot (§2.7).

    shadow_mode: When True, stage outputs are written to the shadow
    namespace (pre_enrichment.stages.<stage>.shadow_output and
    pre_enrichment.shadow_legacy_fields.*) and NOT to live top-level
    fields. Controlled by PREENRICH_SHADOW_MODE env var (default: False).
    See plan §9 Phase 3.
    """

    job_doc: Dict[str, Any]
    jd_checksum: str
    company_checksum: str
    input_snapshot_id: str
    attempt_number: int
    config: StepConfig = field(default_factory=StepConfig)
    shadow_mode: bool = False
    # Stage-scoped tracing handle so stage bodies can emit child spans without
    # needing to branch on Langfuse configuration or call the client directly.
    tracer: PreenrichTracerHandle = field(default_factory=NullPreenrichTracingHandle)
    stage_name: Optional[str] = None


def attempt_token(
    job_id: str,
    stage: str,
    jd_checksum: str,
    prompt_version: str,
    attempt_number: int,
) -> str:
    """
    Generate a deterministic idempotency token for a stage attempt.

    Intentionally excludes provider and model so that a fallback provider
    attempt does not produce a different token (§2.3 Codex review item #26).

    Args:
        job_id: MongoDB document _id as string
        stage: Stage name (e.g. "jd_structure")
        jd_checksum: Current JD checksum ("sha256:<hex>")
        prompt_version: Prompt version string (e.g. "v1")
        attempt_number: Sequential attempt counter (1-based)

    Returns:
        Hex-encoded SHA-256 of the concatenated inputs.
    """
    return _schema_attempt_token(
        job_id=job_id,
        stage=stage,
        jd_checksum=jd_checksum,
        prompt_version=prompt_version,
        attempt_number=attempt_number,
    )
