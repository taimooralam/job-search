"""
pain_points stage — thin adapter over src/layer2/pain_point_miner.PainPointMiner.

Default provider: Claude Sonnet (per plan §4).
Codex path raises NotImplementedError (Phase 6).

Dependencies: ["jd_extraction"]
Output patch: {"pain_points": list, "strategic_needs": list,
               "risks_if_unfilled": list, "success_metrics": list}

The patch field names match those written by full_extraction_service._persist_results()
so existing consumers (cv_generation_service, company_research_service, etc.) are
unchanged.
"""

import logging
import time
from typing import Any, Dict, List

from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult
from src.layer2.pain_point_miner import PainPointMiner

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class PainPointsStage:
    """
    Thin adapter over layer2.pain_point_miner.PainPointMiner.

    Claude Sonnet is the default and only supported provider in Phase 2.
    Codex support is deferred to Phase 6 and raises NotImplementedError now.
    """

    name: str = "pain_points"
    dependencies: List[str] = ["jd_extraction"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Extract pain points, strategic needs, risks and success metrics.

        Args:
            ctx: Stage context. config.provider must be "claude" or "codex".

        Returns:
            StageResult with output patch matching existing field shape.

        Raises:
            NotImplementedError: If config.provider == "codex"
            ValueError: If unsupported provider or extraction fails
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            raise NotImplementedError(
                "codex provider pending Phase 6 cutover — use provider='claude'"
            )

        if provider != "claude":
            raise ValueError(
                f"Unsupported provider '{provider}' for pain_points. "
                "Valid values: 'claude', 'codex' (pending)."
            )

        return self._run_claude(ctx)

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run pain point mining via PainPointMiner."""
        from src.common.state import JobState

        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))

        # Build JobState matching full_extraction_service._run_layer_2()
        jd_text: str = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or job_doc.get("jd_text")
            or ""
        )
        if not jd_text.strip():
            raise ValueError(f"No JD text available for pain_points on job {job_id}")

        state: JobState = {
            "job_id": job_id,
            "title": job_doc.get("title", ""),
            "company": job_doc.get("firm") or job_doc.get("company", ""),
            "job_description": jd_text,
        }

        miner = PainPointMiner(use_enhanced_format=False)

        t0 = time.monotonic()
        try:
            result: Dict[str, Any] = miner.extract_pain_points(state)
        except Exception as exc:
            raise ValueError(
                f"PainPointMiner failed for job {job_id}: {exc}"
            ) from exc
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Build patch matching full_extraction_service._persist_results() shape
        patch = {
            "pain_points": result.get("pain_points", []),
            "strategic_needs": result.get("strategic_needs", []),
            "risks_if_unfilled": result.get("risks_if_unfilled", []),
            "success_metrics": result.get("success_metrics", []),
        }

        pain_count = len(patch["pain_points"])
        logger.debug(
            "pain_points: job %s extracted %d pain points (duration=%dms)",
            job_id,
            pain_count,
            duration_ms,
        )

        return StageResult(
            output=patch,
            provider_used="claude",
            model_used=None,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(PainPointsStage(), StageBase), (
    "PainPointsStage does not satisfy StageBase protocol"
)
