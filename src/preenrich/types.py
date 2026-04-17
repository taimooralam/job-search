"""
Pre-enrichment type definitions.

Defines the core data structures used across the pre-enrichment worker:
- StageStatus: lifecycle states for individual enrichment stages
- StageResult: output from a single stage run
- StageContext: input context passed to each stage
- attempt_token: deterministic idempotency key (excludes provider/model per §2.3)
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


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


@dataclass
class StepConfig:
    """Per-stage provider/model routing configuration."""

    provider: str = "claude"  # "claude" | "codex" | "embedding" | "none"
    model: Optional[str] = None
    prompt_version: str = "v1"


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
    raw = "|".join([job_id, stage, jd_checksum, prompt_version, str(attempt_number)])
    return hashlib.sha256(raw.encode()).hexdigest()
