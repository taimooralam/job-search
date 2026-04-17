"""
StageBase Protocol for pre-enrichment stages.

Each stage must implement:
    name: str               — unique stage identifier matching DAG names
    dependencies: list[str] — stage names this stage depends on
    run(ctx) -> StageResult — pure function, no Mongo I/O
"""

from typing import List, Protocol, runtime_checkable

from src.preenrich.types import StageContext, StageResult


@runtime_checkable
class StageBase(Protocol):
    """
    Protocol that all pre-enrichment stages must satisfy.

    Stages are pure functions from context to result. All persistence
    is handled by the dispatcher (§3 package layout).
    """

    name: str
    """Unique stage identifier. Must match a key in STAGE_ORDER (dag.py)."""

    dependencies: List[str]
    """Names of stages this stage depends on. Used for DAG validation."""

    def run(self, ctx: StageContext) -> StageResult:
        """
        Execute the stage and return a result.

        Args:
            ctx: Immutable stage context with job_doc, checksums, config

        Returns:
            StageResult with output patch and provenance metadata

        Raises:
            Any exception causes the dispatcher to treat this as a failure
            and increment retry_count.
        """
        ...
