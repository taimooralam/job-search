"""Canonical preenrich DAG registry for iteration 4 and 4.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.preenrich.blueprint_config import blueprint_enabled, persona_compat_enabled


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


LEGACY_STAGE_REGISTRY: dict[str, StageDefinition] = {
    "jd_structure": StageDefinition(
        name="jd_structure",
        task_type="preenrich.jd_structure",
        prerequisites=(),
        produces_fields=("processed_jd_sections", "jd_annotations"),
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


def _blueprint_registry() -> dict[str, StageDefinition]:
    persona_required = persona_compat_enabled()
    blueprint_assembly_prereqs = (
        "jd_facts",
        "job_inference",
        "cv_guidelines",
        "application_surface",
        "annotations",
    ) + (("persona_compat",) if persona_required else ())

    return {
        "jd_structure": StageDefinition(
            name="jd_structure",
            task_type="preenrich.jd_structure",
            prerequisites=(),
            produces_fields=("processed_jd_sections", "jd_annotations"),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LOCAL_ERRORS,
            terminal_error_tags=TERMINAL_LOCAL_ERRORS,
            job_fail_policy="fail",
        ),
        "jd_facts": StageDefinition(
            name="jd_facts",
            task_type="preenrich.jd_facts",
            prerequisites=("jd_structure",),
            produces_fields=("jd_facts", "extracted_jd"),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "classification": StageDefinition(
            name="classification",
            task_type="preenrich.classification",
            prerequisites=("jd_facts",),
            produces_fields=("classification", "ai_classification", "is_ai_job", "ai_categories"),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "application_surface": StageDefinition(
            name="application_surface",
            task_type="preenrich.application_surface",
            prerequisites=("jd_facts",),
            produces_fields=("application_surface", "application_url"),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "research_enrichment": StageDefinition(
            name="research_enrichment",
            task_type="preenrich.research_enrichment",
            prerequisites=("jd_facts", "classification", "application_surface"),
            produces_fields=("research_enrichment",),
            required_for_cv_ready=True,
            max_attempts=5,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_RESEARCH_ERRORS,
            terminal_error_tags=TERMINAL_RESEARCH_ERRORS,
            job_fail_policy="fail",
        ),
        "job_inference": StageDefinition(
            name="job_inference",
            task_type="preenrich.job_inference",
            prerequisites=("jd_facts", "classification", "research_enrichment", "application_surface"),
            produces_fields=("job_inference",),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "job_hypotheses": StageDefinition(
            name="job_hypotheses",
            task_type="preenrich.job_hypotheses",
            prerequisites=("jd_facts", "classification", "research_enrichment", "application_surface"),
            produces_fields=("job_hypotheses",),
            required_for_cv_ready=False,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "annotations": StageDefinition(
            name="annotations",
            task_type="preenrich.annotations",
            prerequisites=("jd_structure",),
            produces_fields=("jd_annotations",),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LOCAL_ERRORS,
            terminal_error_tags=TERMINAL_LOCAL_ERRORS,
            job_fail_policy="fail",
        ),
        "persona_compat": StageDefinition(
            name="persona_compat",
            task_type="preenrich.persona_compat",
            prerequisites=("annotations",),
            produces_fields=("jd_annotations",),
            required_for_cv_ready=persona_required,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "cv_guidelines": StageDefinition(
            name="cv_guidelines",
            task_type="preenrich.cv_guidelines",
            prerequisites=("jd_facts", "job_inference", "research_enrichment"),
            produces_fields=("cv_guidelines",),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LLM_ERRORS,
            terminal_error_tags=TERMINAL_LLM_ERRORS,
            job_fail_policy="fail",
        ),
        "blueprint_assembly": StageDefinition(
            name="blueprint_assembly",
            task_type="preenrich.blueprint_assembly",
            prerequisites=blueprint_assembly_prereqs,
            produces_fields=("job_blueprint", "job_blueprint_snapshot"),
            required_for_cv_ready=True,
            max_attempts=3,
            default_priority=DEFAULT_PRIORITY,
            retryable_error_tags=RETRYABLE_LOCAL_ERRORS,
            terminal_error_tags=TERMINAL_LOCAL_ERRORS,
            job_fail_policy="fail",
        ),
    }


def stage_registry() -> Mapping[str, StageDefinition]:
    return _blueprint_registry() if blueprint_enabled() else LEGACY_STAGE_REGISTRY


def get_stage_definition(stage_name: str) -> StageDefinition:
    return dict(stage_registry())[stage_name]


def iter_stage_definitions() -> tuple[StageDefinition, ...]:
    return tuple(stage_registry().values())
