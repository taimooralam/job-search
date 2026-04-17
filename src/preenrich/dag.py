"""
Pre-enrichment stage DAG definition and transitive invalidation.

Defines the authoritative stage execution order and the dependency graph
used for transitive staleness propagation (§2.6).

When an input changes (JD text, company info, priors version), the
invalidate() function returns the full set of stages that must be re-run.
"""

from typing import Dict, List, Set


# Canonical execution order — dispatcher iterates in this order
STAGE_ORDER: List[str] = [
    "jd_structure",
    "jd_extraction",
    "ai_classification",
    "pain_points",
    "annotations",
    "persona",
    "company_research",
    "role_research",
    "fit_signal",
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
    "fit_signal": ["jd_structure", "jd_extraction", "ai_classification",
                   "pain_points", "annotations", "persona",
                   "company_research", "role_research"],
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


def _build_reverse_deps() -> Dict[str, Set[str]]:
    """Build reverse dependency graph (stage -> stages that depend on it)."""
    rev: Dict[str, Set[str]] = {s: set() for s in STAGE_ORDER}
    for stage, deps in _DEPENDENCIES.items():
        for dep in deps:
            rev[dep].add(stage)
    return rev


_REVERSE_DEPS: Dict[str, Set[str]] = _build_reverse_deps()


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
         'annotations', 'persona', 'role_research', 'fit_signal'}
        >>> invalidate({"company"})
        {'company_research', 'role_research', 'fit_signal'}
    """
    directly_affected: Set[str] = set()
    for inp in changed_inputs:
        directly_affected |= _INPUT_DIRECT_INVALIDATIONS.get(inp, set())

    return _transitive_closure(directly_affected)
