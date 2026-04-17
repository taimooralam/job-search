"""
jd_extraction stage — thin adapter over src/layer1_4/claude_jd_extractor.JDExtractor.

Supports provider routing via StageContext.config.provider:
    "claude" (default) — uses JDExtractor with Claude CLI
    "codex"            — raises NotImplementedError (Phase 6 cutover pending)

Validates the extraction output with Pydantic before emitting the patch.
"""

import logging
import time
from typing import List

from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class JDExtractionStage:
    """
    Thin adapter over layer1_4.claude_jd_extractor.JDExtractor.

    Claude is the default and only supported provider in Phase 0/1.
    Codex support is deferred to Phase 6 and raises NotImplementedError now.
    """

    name: str = "jd_extraction"
    dependencies: List[str] = ["jd_structure"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Extract structured JD fields from raw description text.

        Args:
            ctx: Stage context. config.provider must be "claude" or "codex".

        Returns:
            StageResult with output patch {"extracted_jd": <dict>}

        Raises:
            NotImplementedError: If config.provider == "codex"
            ValueError: If extraction fails or output fails Pydantic validation
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            raise NotImplementedError(
                "codex provider pending Phase 6 cutover — use provider='claude'"
            )

        if provider != "claude":
            raise ValueError(
                f"Unsupported provider '{provider}' for jd_extraction. "
                "Valid values: 'claude', 'codex' (pending)."
            )

        return self._run_claude(ctx)

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run extraction via JDExtractor (Claude CLI / UnifiedLLM)."""
        from src.layer1_4.claude_jd_extractor import JDExtractor

        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        title = job_doc.get("title", "")
        company = job_doc.get("company", "")
        description = job_doc.get("description", "")

        extractor = JDExtractor()

        t0 = time.monotonic()
        result = extractor.extract(
            job_id=job_id,
            title=title,
            company=company,
            job_description=description,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        if not result.success or result.extracted_jd is None:
            raise ValueError(
                f"JDExtractor failed for job {job_id}: {result.error}"
            )

        # Validate with Pydantic (ExtractedJD from state.py)
        from src.common.state import ExtractedJD

        extracted_dict = result.extracted_jd
        if hasattr(extracted_dict, "model_dump"):
            extracted_dict = extracted_dict.model_dump()
        elif hasattr(extracted_dict, "dict"):
            extracted_dict = extracted_dict.dict()

        # Pydantic validation — raises ValidationError on schema mismatch
        validated = ExtractedJD(**extracted_dict)
        if hasattr(validated, "model_dump"):
            output_data = validated.model_dump()
        else:
            output_data = validated.dict()

        logger.debug(
            "jd_extraction: successfully extracted for job %s (duration=%dms)",
            job_id, duration_ms,
        )

        return StageResult(
            output={"extracted_jd": output_data},
            provider_used="claude",
            model_used=getattr(result, "model", None),
            prompt_version=PROMPT_VERSION,
            tokens_input=result.input_tokens if hasattr(result, "input_tokens") else None,
            tokens_output=result.output_tokens if hasattr(result, "output_tokens") else None,
            cost_usd=result.cost_usd if hasattr(result, "cost_usd") else None,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(JDExtractionStage(), StageBase), (
    "JDExtractionStage does not satisfy StageBase protocol"
)
