"""
persona stage — adapter over src/common/persona_builder.PersonaBuilder.

Default provider: Claude Sonnet (DOWNGRADED from Opus per plan §4).
Codex path raises NotImplementedError (Phase 6).

Dependencies: ["annotations"]
Output patch: {"jd_annotations": {... "synthesized_persona": {...}}}

The model is configurable via StepConfig so the downgrade is reversible.
Default is Sonnet ("balanced" tier). Existing full_extraction_service uses
Opus via the "quality" ClaudeCLI tier — this stage uses "balanced" by default,
which is the main cost win described in plan §4.

Callers that need Opus can set ctx.config.model = "opus" or use provider="claude"
with model override in StepConfig.
"""

import asyncio
import logging
import time
from typing import List, Optional

from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult
from src.common.persona_builder import PersonaBuilder, SynthesizedPersona

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

# Default tier for persona synthesis — downgraded from Opus (quality) to Sonnet (balanced)
DEFAULT_TIER = "balanced"


class PersonaStage:
    """
    Adapter over common.persona_builder.PersonaBuilder.

    Claude Sonnet (balanced tier) is the default. Codex support deferred to Phase 6.

    The synthesized persona is embedded back into jd_annotations.synthesized_persona,
    matching the field shape written by full_extraction_service._persist_persona().
    """

    name: str = "persona"
    dependencies: List[str] = ["annotations"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Synthesize persona from identity/passion/strength annotations.

        Args:
            ctx: Stage context. config.provider must be "claude" or "codex".
                 config.model is the tier: "balanced" (default/Sonnet), "quality" (Opus).

        Returns:
            StageResult with output patch {"jd_annotations": {...}} where
            jd_annotations.synthesized_persona is the SynthesizedPersona dict.
            If no persona-relevant annotations exist, returns a skipped result.

        Raises:
            NotImplementedError: If config.provider == "codex"
            ValueError: If unsupported provider or synthesis fails unexpectedly
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            raise NotImplementedError(
                "codex provider pending Phase 6 cutover — use provider='claude'"
            )

        if provider != "claude":
            raise ValueError(
                f"Unsupported provider '{provider}' for persona. "
                "Valid values: 'claude', 'codex' (pending)."
            )

        return self._run_claude(ctx)

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run persona synthesis via PersonaBuilder."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))

        # Use configured tier (model field carries the tier name for ClaudeCLI)
        tier = DEFAULT_TIER
        if ctx.config and ctx.config.model:
            tier = ctx.config.model

        jd_annotations = job_doc.get("jd_annotations", {})

        builder = PersonaBuilder()

        # Check if there are annotations to build a persona from
        if not builder.has_persona_annotations(jd_annotations):
            logger.info(
                "persona: no persona-relevant annotations for job %s — skipping synthesis",
                job_id,
            )
            return StageResult(
                output={},
                provider_used="claude",
                model_used=tier,
                prompt_version=PROMPT_VERSION,
                skip_reason="no_persona_annotations",
            )

        extracted_jd = job_doc.get("extracted_jd") or {}
        icp = extracted_jd.get("ideal_candidate_profile") if extracted_jd else None

        t0 = time.monotonic()
        # PersonaBuilder.synthesize is async — run in a thread pool to avoid event loop conflicts
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        builder.synthesize(jd_annotations, job_id, ideal_candidate_profile=icp),
                    )
                    persona = future.result()
            else:
                persona = loop.run_until_complete(
                    builder.synthesize(jd_annotations, job_id, ideal_candidate_profile=icp)
                )
        except RuntimeError:
            persona = asyncio.run(
                builder.synthesize(jd_annotations, job_id, ideal_candidate_profile=icp)
            )
        duration_ms = int((time.monotonic() - t0) * 1000)

        if persona is None:
            return StageResult(
                output={},
                provider_used="claude",
                model_used=tier,
                prompt_version=PROMPT_VERSION,
                skip_reason="synthesis_returned_none",
                duration_ms=duration_ms,
            )

        # Embed persona into jd_annotations.synthesized_persona
        # Matches full_extraction_service._persist_persona() shape
        updated_jd_annotations = dict(jd_annotations)
        updated_jd_annotations["synthesized_persona"] = persona.to_dict()

        patch = {
            "jd_annotations": updated_jd_annotations,
        }

        logger.debug(
            "persona: synthesized for job %s (tier=%s, duration=%dms): %s...",
            job_id,
            tier,
            duration_ms,
            persona.persona_statement[:60],
        )

        return StageResult(
            output=patch,
            provider_used="claude",
            model_used=tier,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(PersonaStage(), StageBase), (
    "PersonaStage does not satisfy StageBase protocol"
)
