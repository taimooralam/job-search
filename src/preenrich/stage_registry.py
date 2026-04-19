"""Canonical preenrich DAG registry for iteration 4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class StageDefinition:
    """Immutable registry entry for one preenrich stage."""

    name: str
    task_type: str
    prerequisites: tuple[str, ...]
    produces_fields: tuple[str, ...]
    required_for_cv_ready: bool
    max_attempts: int
    default_priority: int
    retryable_error_tags: tuple[str, ...]
    terminal_error_tags: tuple[str, ...]
    job_fail_policy: str


DEFAULT_PRIORITY = 100
RETRYABLE_LLM_ERRORS = (
    "provider_timeout",
    "provider_rate_limit",
    "provider_5xx",
    "provider_unavailable",
    "mongo_transient",
)
TERMINAL_LLM_ERRORS = (
    "auth_failure",
    "schema_validation",
    "prompt_contract_violation",
    "unsupported_provider",
)
RETRYABLE_RESEARCH_ERRORS = (
    "provider_timeout",
    "provider_rate_limit",
    "provider_5xx",
    "provider_unavailable",
    "network_timeout",
    "search_backend_error",
    "mongo_transient",
)
TERMINAL_RESEARCH_ERRORS = (
    "auth_failure",
    "schema_validation",
    "unsupported_provider",
    "missing_required_input",
)
RETRYABLE_LOCAL_ERRORS = ("mongo_transient", "transient_io")
TERMINAL_LOCAL_ERRORS = ("missing_required_input", "unsupported_provider", "schema_validation")


STAGE_REGISTRY: dict[str, StageDefinition] = {
    "jd_structure": StageDefinition(
        name="jd_structure",
        task_type="preenrich.jd_structure",
        prerequisites=(),
        produces_fields=("processed_jd_sections",),
        required_for_cv_ready=True,
        max_attempts=3,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_LOCAL_ERRORS,
        terminal_error_tags=TERMINAL_LOCAL_ERRORS,
        job_fail_policy="fail",
    ),
    "jd_extraction": StageDefinition(
        name="jd_extraction",
        task_type="preenrich.jd_extraction",
        prerequisites=("jd_structure",),
        produces_fields=("extracted_jd",),
        required_for_cv_ready=True,
        max_attempts=3,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_LLM_ERRORS,
        terminal_error_tags=TERMINAL_LLM_ERRORS,
        job_fail_policy="fail",
    ),
    "ai_classification": StageDefinition(
        name="ai_classification",
        task_type="preenrich.ai_classification",
        prerequisites=("jd_extraction",),
        produces_fields=(
            "is_ai_job",
            "ai_categories",
            "ai_category_count",
            "ai_rationale",
            "ai_classified_at",
            "ai_classification",
        ),
        required_for_cv_ready=True,
        max_attempts=3,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_LLM_ERRORS,
        terminal_error_tags=TERMINAL_LLM_ERRORS,
        job_fail_policy="fail",
    ),
    "pain_points": StageDefinition(
        name="pain_points",
        task_type="preenrich.pain_points",
        prerequisites=("jd_extraction",),
        produces_fields=("pain_points", "strategic_needs", "risks_if_unfilled", "success_metrics"),
        required_for_cv_ready=True,
        max_attempts=3,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_LLM_ERRORS,
        terminal_error_tags=TERMINAL_LLM_ERRORS,
        job_fail_policy="fail",
    ),
    "annotations": StageDefinition(
        name="annotations",
        task_type="preenrich.annotations",
        prerequisites=("pain_points",),
        produces_fields=("jd_annotations",),
        required_for_cv_ready=True,
        max_attempts=3,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_LOCAL_ERRORS,
        terminal_error_tags=TERMINAL_LOCAL_ERRORS,
        job_fail_policy="fail",
    ),
    "persona": StageDefinition(
        name="persona",
        task_type="preenrich.persona",
        prerequisites=("annotations",),
        produces_fields=("jd_annotations",),
        required_for_cv_ready=True,
        max_attempts=3,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_LLM_ERRORS,
        terminal_error_tags=TERMINAL_LLM_ERRORS,
        job_fail_policy="fail",
    ),
    "company_research": StageDefinition(
        name="company_research",
        task_type="preenrich.company_research",
        prerequisites=("persona",),
        produces_fields=("company_research", "company_summary", "company_url"),
        required_for_cv_ready=True,
        max_attempts=5,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_RESEARCH_ERRORS,
        terminal_error_tags=TERMINAL_RESEARCH_ERRORS,
        job_fail_policy="fail",
    ),
    "role_research": StageDefinition(
        name="role_research",
        task_type="preenrich.role_research",
        prerequisites=("company_research",),
        produces_fields=("role_research",),
        required_for_cv_ready=True,
        max_attempts=5,
        default_priority=DEFAULT_PRIORITY,
        retryable_error_tags=RETRYABLE_RESEARCH_ERRORS,
        terminal_error_tags=TERMINAL_RESEARCH_ERRORS,
        job_fail_policy="fail",
    ),
}

# Reserved for later iterations once their consumers exist:
# - fit_signal
# - competency_eval


def get_stage_definition(stage_name: str) -> StageDefinition:
    """Return one registered stage or raise KeyError for unknown names."""
    return STAGE_REGISTRY[stage_name]


def iter_stage_definitions() -> tuple[StageDefinition, ...]:
    """Return the registry entries in topological order."""
    return tuple(STAGE_REGISTRY.values())


def stage_registry() -> Mapping[str, StageDefinition]:
    """Read-only registry accessor for callers that only need lookup."""
    return STAGE_REGISTRY
