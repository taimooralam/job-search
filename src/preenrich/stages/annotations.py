"""
annotations stage — pure-function adapter over annotation_suggester.compute_annotations.

Provider: embedding + priors (no LLM — plan §4).
Codex path not applicable (no LLM involved).

Dependencies: ["jd_structure"]
Output patch: {"jd_annotations": {...}} — specifically updates the annotations list
inside jd_annotations.

Decomposition: calls compute_annotations() which is the pure function extracted
from generate_annotations_for_job(). The shim (generate_annotations_for_job) still
works for non-preenrich callers. No Mongo write happens inside this stage — the
dispatcher is the sole writer (§3.4).
"""

import logging
import time
from typing import List

from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult
from src.services.annotation_suggester import compute_annotations

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class AnnotationsStage:
    """
    Adapter over annotation_suggester.compute_annotations.

    No LLM is used — this is purely embeddings + priors-based matching.
    The stage returns a patch containing the updated jd_annotations dict
    (with new annotations merged in). The dispatcher writes the patch atomically.

    Prerequisite: jd_structure must be completed so that jd_annotations.processed_jd_sections
    is populated in the job document.
    """

    name: str = "annotations"
    dependencies: List[str] = ["jd_structure"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Generate annotation suggestions for the job's structured JD.

        Args:
            ctx: Stage context. job_doc must have jd_annotations.processed_jd_sections.

        Returns:
            StageResult with output patch {"jd_annotations": {...}} where
            jd_annotations.annotations contains existing + new annotations.

        Raises:
            ValueError: If no processed JD sections are found in the job doc.
        """
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))

        # Verify prerequisite data is present
        jd_annotations = job_doc.get("jd_annotations", {})
        processed_sections = jd_annotations.get("processed_jd_sections", [])
        if not processed_sections:
            raise ValueError(
                f"No processed_jd_sections in job_doc for job {job_id}. "
                "jd_structure stage must complete before annotations."
            )

        t0 = time.monotonic()
        compute_result = compute_annotations(job_doc)
        duration_ms = int((time.monotonic() - t0) * 1000)

        if not compute_result["success"]:
            raise ValueError(
                f"compute_annotations failed for job {job_id}: {compute_result['error']}"
            )

        all_annotations = compute_result["all_annotations"]
        new_count = len(compute_result["new_annotations"])
        skipped = compute_result["skipped"]
        priors_version = compute_result["priors_version"]

        # Build patch: update jd_annotations.annotations in the job doc
        # We write the full jd_annotations sub-doc with annotations merged in.
        # Other fields in jd_annotations (processed_jd_sections, content_hash, etc.)
        # are preserved from the existing job_doc.
        updated_jd_annotations = dict(jd_annotations)
        updated_jd_annotations["annotations"] = all_annotations

        patch = {
            "jd_annotations": updated_jd_annotations,
        }

        logger.debug(
            "annotations: job %s created %d new annotations, skipped %d (duration=%dms, priors_version=%s)",
            job_id,
            new_count,
            skipped,
            duration_ms,
            priors_version,
        )

        result = StageResult(
            output=patch,
            provider_used="embedding",
            model_used=None,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )
        # Store priors_version in provenance for DAG invalidation tracking
        result._priors_version = priors_version  # type: ignore[attr-defined]
        return result


# Verify protocol compliance at import time
assert isinstance(AnnotationsStage(), StageBase), (
    "AnnotationsStage does not satisfy StageBase protocol"
)
