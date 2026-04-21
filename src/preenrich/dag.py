"""Pre-enrichment stage DAG definition and transitive invalidation."""

from typing import Dict, List, Set

from src.preenrich.blueprint_config import blueprint_enabled, persona_compat_enabled

# Canonical execution order — dispatcher iterates in this order.
# fit_signal is dropped from Phase 2 scope (no live consumer in BatchPipelineService
# as of Phase 2 — Phase 5 runner-skip work will wire the consumer per plan §3.6).
STAGE_ORDER: List[str] = [
    "jd_structure",
    "jd_extraction",
    "ai_classification",
    "pain_points",
    "annotations",
    "persona",
    "company_research",
    "role_research",
]

BLUEPRINT_STAGE_ORDER: List[str] = [
    "jd_structure",
    "jd_facts",
    "classification",
    "application_surface",
    "research_enrichment",
    "job_inference",
    "job_hypotheses",
    "annotations",
    "persona_compat",
    "cv_guidelines",
    "blueprint_assembly",
]

# Direct dependencies: stage -> stages it depends on
# Used to derive transitive propagation from changed inputs
_DEPENDENCIES: Dict[str, List[str]] = {
    "jd_structure": [],
    "jd_extraction": ["jd_structure"],
    "ai_classification": ["jd_extraction"],
    "pain_points": ["jd_extraction"],
    "annotations": ["jd_extraction"],
    "persona": ["annotations"],
    "company_research": [],
    "role_research": ["jd_extraction", "company_research"],
    # fit_signal deferred to Phase 5 — will be re-added when consumer is wired
}

_BLUEPRINT_DEPENDENCIES: Dict[str, List[str]] = {
    "jd_structure": [],
    "jd_facts": ["jd_structure"],
    "classification": ["jd_facts"],
    "application_surface": ["jd_facts"],
    "research_enrichment": ["jd_facts", "classification", "application_surface"],
    "job_inference": ["jd_facts", "classification", "research_enrichment", "application_surface"],
    "job_hypotheses": ["jd_facts", "classification", "research_enrichment", "application_surface"],
    "annotations": ["jd_structure"],
    "persona_compat": ["annotations"],
    "cv_guidelines": ["jd_facts", "job_inference", "research_enrichment"],
    "blueprint_assembly": ["jd_facts", "job_inference", "cv_guidelines", "application_surface", "annotations", "persona_compat"],
}

# Inputs that affect which stages are invalidated
# Each input maps to the set of stages DIRECTLY affected by it
_INPUT_DIRECT_INVALIDATIONS: Dict[str, Set[str]] = {
    # JD text change: directly invalidates JD-processing stages
    "jd": {"jd_structure", "jd_extraction", "ai_classification", "pain_points", "annotations"},
    # Company change: directly invalidates company research
    "company": {"company_research"},
    # Priors version change: directly invalidates annotation-dependent stages
    "priors": {"annotations"},
}

_BLUEPRINT_INPUT_DIRECT_INVALIDATIONS: Dict[str, Set[str]] = {
    "jd": {"jd_structure", "jd_facts", "classification", "research_enrichment", "application_surface", "job_inference", "job_hypotheses", "cv_guidelines", "blueprint_assembly", "annotations"},
    "company": {"research_enrichment", "application_surface"},
    "priors": {"annotations"},
    "taxonomy": {"classification"},
}


def _build_reverse_deps() -> Dict[str, Set[str]]:
    """Build reverse dependency graph (stage -> stages that depend on it)."""
    rev: Dict[str, Set[str]] = {s: set() for s in STAGE_ORDER}
    for stage, deps in _DEPENDENCIES.items():
        for dep in deps:
            rev[dep].add(stage)
    return rev


_REVERSE_DEPS: Dict[str, Set[str]] = _build_reverse_deps()


def current_stage_order() -> List[str]:
    order = BLUEPRINT_STAGE_ORDER if blueprint_enabled() else STAGE_ORDER
    if blueprint_enabled() and not persona_compat_enabled():
        return [stage for stage in order if stage != "persona_compat"]
    return list(order)


def _current_dependencies() -> Dict[str, List[str]]:
    deps = _BLUEPRINT_DEPENDENCIES if blueprint_enabled() else _DEPENDENCIES
    if blueprint_enabled() and not persona_compat_enabled():
        trimmed = {stage: [dep for dep in prereqs if dep != "persona_compat"] for stage, prereqs in deps.items() if stage != "persona_compat"}
        return trimmed
    return deps


def _current_input_invalidations() -> Dict[str, Set[str]]:
    mapping = _BLUEPRINT_INPUT_DIRECT_INVALIDATIONS if blueprint_enabled() else _INPUT_DIRECT_INVALIDATIONS
    if blueprint_enabled() and not persona_compat_enabled():
        return {key: {stage for stage in value if stage != "persona_compat"} for key, value in mapping.items()}
    return mapping


def _transitive_closure(initial: Set[str]) -> Set[str]:
    """
    Compute the transitive closure of stages reachable from the initial set
    via the reverse dependency graph (i.e., all stages that depend on any
    stage in the initial set, directly or transitively).

    Args:
        initial: Set of directly-affected stage names

    Returns:
        Full set of stages that need to be invalidated
    """
    result: Set[str] = set(initial)
    frontier = set(initial)

    while frontier:
        next_frontier: Set[str] = set()
        for stage in frontier:
            for dependant in _REVERSE_DEPS.get(stage, set()):
                if dependant not in result:
                    result.add(dependant)
                    next_frontier.add(dependant)
        frontier = next_frontier

    return result


def invalidate(changed_inputs: Set[str]) -> Set[str]:
    """
    Compute the full set of stages to mark stale given a set of changed inputs.

    Applies the invalidation rules from §2.6:
    - "jd" -> jd_structure, jd_extraction, ai_classification, pain_points,
               annotations, + transitive dependants (persona, role_research, fit_signal)
    - "company" -> company_research, + transitive dependants (role_research, fit_signal)
    - "priors" -> annotations, + transitive dependants (persona, fit_signal)

    Args:
        changed_inputs: Set of input keys that changed.
                        Valid keys: "jd", "company", "priors"

    Returns:
        Set of stage names that should be marked stale.

    Example:
        >>> invalidate({"jd"})
        {'jd_structure', 'jd_extraction', 'ai_classification', 'pain_points',
         'annotations', 'persona', 'role_research'}
        >>> invalidate({"company"})
        {'company_research', 'role_research'}
    """
    deps = _current_dependencies()
    direct_invalidations = _current_input_invalidations()
    reverse_deps: Dict[str, Set[str]] = {stage: set() for stage in deps}
    for stage, prereqs in deps.items():
        for prereq in prereqs:
            reverse_deps.setdefault(prereq, set()).add(stage)

    directly_affected: Set[str] = set()
    for inp in changed_inputs:
        directly_affected |= direct_invalidations.get(inp, set())

    result: Set[str] = set(directly_affected)
    frontier = set(directly_affected)
    while frontier:
        next_frontier: Set[str] = set()
        for stage in frontier:
            for dependent in reverse_deps.get(stage, set()):
                if dependent not in result:
                    result.add(dependent)
                    next_frontier.add(dependent)
        frontier = next_frontier
    return result
