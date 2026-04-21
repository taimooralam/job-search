"""
jd_structure stage — thin adapter over src/layer1_4/jd_processor.

Calls process_jd_sync and emits a patch with processed_jd_sections for the
legacy top-level field. Pure function; no Mongo I/O.
"""

import logging
import time
from typing import List

from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class JDStructureStage:
    """Adapter over layer1_4.jd_processor.process_jd_sync."""

    name: str = "jd_structure"
    dependencies: List[str] = []

    def run(self, ctx: StageContext) -> StageResult:
        """
        Structure the JD text into sections.

        Delegates to process_jd_sync (rule-based, no LLM cost).

        Args:
            ctx: Stage context with job_doc

        Returns:
            StageResult with output patch {"processed_jd_sections": <list>}
        """
        from src.layer1_4.jd_processor import process_jd_sync

        description = ctx.job_doc.get("description", "")
        t0 = time.monotonic()

        processed_jd, llm_metadata = process_jd_sync(description, use_llm=False)

        duration_ms = int((time.monotonic() - t0) * 1000)

        # Serialize sections for Mongo storage
        sections_data = [
            {
                "section_type": s.section_type.value,
                # Keep `title` as a compatibility alias for older consumers,
                # but source it from the actual JDSection field name.
                "title": s.header,
                "header": s.header,
                "content": s.content,
                "items": list(s.items),
                "char_start": s.char_start,
                "char_end": s.char_end,
                "index": s.index,
            }
            for s in processed_jd.sections
        ]

        logger.debug(
            "jd_structure: %d sections extracted for job %s",
            len(sections_data),
            ctx.job_doc.get("_id"),
        )

        return StageResult(
            output={
                "processed_jd_sections": sections_data,
                "jd_annotations.processed_jd_sections": sections_data,
            },
            stage_output={"processed_jd_sections": sections_data},
            provider_used=llm_metadata.backend,
            model_used=llm_metadata.model,
            prompt_version=PROMPT_VERSION,
            tokens_input=None,
            tokens_output=None,
            cost_usd=float(llm_metadata.cost_usd) if llm_metadata.cost_usd else 0.0,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(JDStructureStage(), StageBase), (
    "JDStructureStage does not satisfy StageBase protocol"
)
