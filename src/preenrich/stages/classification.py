"""Iteration-4.1 classification stage."""

from __future__ import annotations

import time
from typing import Any, List

from src.common.codex_cli import CodexCLI
from src.preenrich.blueprint_config import (
    classification_ai_taxonomy_enabled,
    classification_disambiguation_margin,
    classification_escalate_on_failure_enabled,
    classification_escalation_model,
    classification_high_confidence_threshold,
    classification_short_circuit_margin,
    load_job_taxonomy,
    taxonomy_version,
)
from src.preenrich.blueprint_models import (
    AITaxonomyDoc,
    ClassificationDoc,
    ClassificationEvidence,
    JdFactsAgreement,
    PreScoreEntry,
)
from src.preenrich.blueprint_prompts import build_p_classify
from src.preenrich.stages.base import StageBase
from src.preenrich.stages.blueprint_common import (
    ai_relevance,
    apply_disambiguation_rules,
    detect_ai_taxonomy,
    score_categories_from_taxonomy,
    search_profiles_for_primary,
    selector_profiles_for_primary,
    title_family,
    tone_for_primary,
)
from src.preenrich.types import StageContext, StageResult

PROMPT_VERSION_V2 = "P-classify:v2"


def _description(job_doc: dict[str, Any]) -> str:
    return str(job_doc.get("description") or job_doc.get("job_description") or "")


def _get_processed_sections(job_doc: dict[str, Any]) -> list[dict[str, Any]]:
    pre = (job_doc.get("pre_enrichment") or {}).get("outputs") or {}
    candidates = (
        pre.get("jd_structure", {}).get("processed_jd_sections"),
        job_doc.get("processed_jd_sections"),
        (job_doc.get("jd_annotations") or {}).get("processed_jd_sections"),
    )
    for value in candidates:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _section_context(job_doc: dict[str, Any]) -> dict[str, Any]:
    sections = _get_processed_sections(job_doc)
    return {
        "used_processed_jd_sections": bool(sections),
        "sections": [
            {
                "section_type": item.get("section_type"),
                "header": item.get("header") or item.get("title"),
                "content": item.get("content") or item.get("text") or item.get("body"),
            }
            for item in sections[:8]
        ],
    }


def _jd_facts_payload(job_doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    outputs = ((job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = outputs.get("jd_facts") or {}
    extraction = jd_facts.get("extraction") or {}
    merged = jd_facts.get("merged_view") or {}
    title = extraction.get("title") or merged.get("title") or job_doc.get("title") or ""
    return jd_facts, {
        "title": title,
        "company": extraction.get("company") or merged.get("company") or job_doc.get("company"),
        "jd_facts_role_category": extraction.get("role_category") or merged.get("role_category"),
        "seniority_level": extraction.get("seniority_level") or merged.get("seniority_level"),
        "responsibilities": extraction.get("responsibilities") or merged.get("responsibilities") or [],
        "qualifications": extraction.get("qualifications") or merged.get("qualifications") or merged.get("must_haves") or [],
        "top_keywords": extraction.get("top_keywords") or merged.get("top_keywords") or [],
        "competency_weights": extraction.get("competency_weights") or merged.get("competency_weights") or {},
        "ideal_candidate_archetype": ((extraction.get("ideal_candidate_profile") or {}).get("archetype"))
        or ((merged.get("ideal_candidate_profile") or {}).get("archetype")),
        "description": _description(job_doc),
    }


def _build_ai_compat_projection(doc: ClassificationDoc) -> dict[str, Any]:
    ai_taxonomy = doc.ai_taxonomy
    categories = list(ai_taxonomy.legacy_ai_categories or [])
    rationale = ai_taxonomy.rationale or ("No AI specialization signals detected." if not ai_taxonomy.is_ai_job else "AI specialization detected.")
    compat = {
        "is_ai_job": bool(ai_taxonomy.is_ai_job),
        "ai_categories": categories,
        "ai_category_count": len(categories),
        "ai_rationale": rationale,
        "ai_classification": {
            "is_ai_job": bool(ai_taxonomy.is_ai_job),
            "ai_categories": categories,
            "ai_category_count": len(categories),
            "ai_rationale": rationale,
            "taxonomy_version": doc.taxonomy_version,
            "primary_specialization": ai_taxonomy.primary_specialization,
            "intensity": ai_taxonomy.intensity,
        },
    }
    return compat


def _normalized_margin(pre_score: list[dict[str, Any]]) -> float:
    if len(pre_score) < 2:
        return 1.0
    top = float(pre_score[0]["score"])
    second = float(pre_score[1]["score"])
    base = max(abs(top), 1.0)
    return max(0.0, (top - second) / base)


def _confidence_from_margin(margin: float, *, high_threshold: float, short_circuit_margin: float) -> str:
    if margin >= high_threshold:
        return "high"
    if margin >= short_circuit_margin:
        return "medium"
    return "low"


def _secondary_categories(pre_score: list[dict[str, Any]], *, margin: float) -> list[str]:
    if len(pre_score) < 2:
        return []
    if margin <= (classification_disambiguation_margin() * 2):
        return [str(pre_score[1]["category"])]
    return []


def _invoke_codex_json(
    *,
    prompt: str,
    model: str,
    job_id: str,
    cwd: str | None = None,
    reasoning_effort: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    t0 = time.monotonic()
    cli = CodexCLI(model=model, cwd=cwd, reasoning_effort=reasoning_effort)
    result = cli.invoke(prompt, job_id=job_id, validate_json=True)
    duration_ms = int((time.monotonic() - t0) * 1000)
    return (result.result or None), {
        "provider": "codex",
        "model": model,
        "outcome": "success" if result.success else "error_subprocess",
        "error": result.error,
        "duration_ms": duration_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }


def _build_fail_open_doc(
    *,
    inputs: dict[str, Any],
    pre_score: list[dict[str, Any]],
    ai_taxonomy: AITaxonomyDoc,
    reason_codes: list[str],
    jd_facts_role_category: str | None,
) -> ClassificationDoc:
    primary = jd_facts_role_category or title_family(str(inputs.get("title") or ""))
    return ClassificationDoc(
        primary_role_category=primary,
        secondary_role_categories=[],
        search_profiles=search_profiles_for_primary(primary),
        selector_profiles=selector_profiles_for_primary(primary),
        tone_family=tone_for_primary(primary),
        taxonomy_version=taxonomy_version(),
        ambiguity_score=1.0,
        confidence="low",
        reason_codes=reason_codes or ["fail_open"],
        evidence=ClassificationEvidence(),
        jd_facts_agreement=JdFactsAgreement(
            agrees=bool(jd_facts_role_category and jd_facts_role_category == primary),
            jd_facts_role_category=jd_facts_role_category,
            reason="fail_open",
        ),
        pre_score=[PreScoreEntry.model_validate(item) for item in pre_score],
        decision_path="fail_open",
        model_used=None,
        provider_used="none",
        prompt_version=PROMPT_VERSION_V2,
        ai_taxonomy=ai_taxonomy,
        ai_relevance={"is_ai_job": ai_taxonomy.is_ai_job, "categories": ai_taxonomy.legacy_ai_categories, "rationale": ai_taxonomy.rationale},
    )


class ClassificationStage:
    name: str = "classification"
    dependencies: List[str] = ["jd_facts"]

    def _run_v2(self, ctx: StageContext) -> tuple[ClassificationDoc, dict[str, Any]]:
        taxonomy = load_job_taxonomy()
        _jd_facts_doc, inputs = _jd_facts_payload(ctx.job_doc)
        pre_score = score_categories_from_taxonomy(inputs, taxonomy)
        primary, disambiguation_reasons = apply_disambiguation_rules(
            pre_score,
            inputs,
            taxonomy,
            classification_disambiguation_margin(),
        )
        jd_facts_role_category = str(inputs.get("jd_facts_role_category") or "") or None
        margin = _normalized_margin(pre_score)
        confidence = _confidence_from_margin(
            margin,
            high_threshold=classification_high_confidence_threshold(),
            short_circuit_margin=classification_short_circuit_margin(),
        )
        ai_taxonomy = detect_ai_taxonomy(inputs, taxonomy) if classification_ai_taxonomy_enabled() else AITaxonomyDoc()
        evidence = ClassificationEvidence.model_validate((pre_score[0] or {}).get("evidence") if pre_score else {})
        agreement = JdFactsAgreement(
            agrees=bool(jd_facts_role_category and jd_facts_role_category == primary),
            jd_facts_role_category=jd_facts_role_category,
            reason="deterministic_agreement" if jd_facts_role_category and jd_facts_role_category == primary else "deterministic_disagreement" if jd_facts_role_category else "missing_jd_facts_role_category",
        )
        reason_codes = list(disambiguation_reasons)
        if not pre_score or float(pre_score[0]["score"]) <= 0:
            reason_codes.append("missing_taxonomy_signals")
            doc = _build_fail_open_doc(
                inputs=inputs,
                pre_score=pre_score,
                ai_taxonomy=ai_taxonomy,
                reason_codes=reason_codes,
                jd_facts_role_category=jd_facts_role_category,
            )
            return doc, {}

        should_call_llm = (
            margin < classification_short_circuit_margin()
            or (jd_facts_role_category is not None and jd_facts_role_category != primary)
        )

        provider_used = "none"
        model_used = None
        prompt_version = PROMPT_VERSION_V2
        llm_attempted = False
        if should_call_llm and (ctx.config.provider or "codex") != "none":
            llm_attempted = True
            prompt = build_p_classify(
                jd_facts={
                    "title": inputs["title"],
                    "jd_facts_role_category": jd_facts_role_category,
                    "seniority_level": inputs.get("seniority_level"),
                    "responsibilities": inputs.get("responsibilities"),
                    "qualifications": inputs.get("qualifications"),
                    "top_keywords": inputs.get("top_keywords"),
                    "competency_weights": inputs.get("competency_weights"),
                    "ideal_candidate_archetype": inputs.get("ideal_candidate_archetype"),
                },
                taxonomy=taxonomy,
                pre_score=pre_score[:3],
                section_context=_section_context(ctx.job_doc),
            )
            job_id = str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "unknown")
            payload: dict[str, Any] | None = None
            attempt, metadata = _invoke_codex_json(
                prompt=prompt,
                model=ctx.config.primary_model or "gpt-5.4-mini",
                job_id=job_id,
                cwd=ctx.config.codex_workdir,
                reasoning_effort=ctx.config.reasoning_effort,
            )
            payload = attempt
            provider_used = "codex"
            model_used = metadata["model"]
            if payload is None and classification_escalate_on_failure_enabled():
                attempt, metadata = _invoke_codex_json(
                    prompt=prompt,
                    model=classification_escalation_model(),
                    job_id=job_id,
                    cwd=ctx.config.codex_workdir,
                    reasoning_effort=ctx.config.reasoning_effort,
                )
                payload = attempt
                provider_used = "codex"
                model_used = metadata["model"]
            if payload is not None:
                payload.setdefault("taxonomy_version", taxonomy_version())
                payload.setdefault("search_profiles", search_profiles_for_primary(str(payload.get("primary_role_category") or primary)))
                payload.setdefault("selector_profiles", selector_profiles_for_primary(str(payload.get("primary_role_category") or primary)))
                payload.setdefault("tone_family", tone_for_primary(str(payload.get("primary_role_category") or primary)))
                payload.setdefault("pre_score", pre_score[:3])
                payload.setdefault("jd_facts_agreement", agreement.model_dump())
                payload.setdefault("ai_taxonomy", ai_taxonomy.model_dump())
                payload.setdefault("ai_relevance", {"is_ai_job": ai_taxonomy.is_ai_job, "categories": ai_taxonomy.legacy_ai_categories, "rationale": ai_taxonomy.rationale})
                payload.setdefault("reason_codes", reason_codes + ["llm_disambiguation"])
                payload.setdefault("provider_used", provider_used)
                payload.setdefault("model_used", model_used)
                payload.setdefault("prompt_version", prompt_version)
                try:
                    doc = ClassificationDoc.model_validate(payload)
                except Exception:
                    doc = None
                else:
                    return doc, metadata
            reason_codes.append("llm_validation_failed")

        primary_doc = ClassificationDoc(
            primary_role_category=primary,
            secondary_role_categories=_secondary_categories(pre_score, margin=margin),
            search_profiles=search_profiles_for_primary(primary),
            selector_profiles=selector_profiles_for_primary(primary),
            tone_family=tone_for_primary(primary),
            taxonomy_version=taxonomy_version(),
            ambiguity_score=round(max(0.0, 1.0 - margin), 4),
            confidence=confidence,
            reason_codes=reason_codes or (["deterministic_short_circuit"] if not llm_attempted else ["deterministic_after_llm_failure"]),
            evidence=evidence,
            jd_facts_agreement=agreement,
            pre_score=[PreScoreEntry.model_validate(item) for item in pre_score[:3]],
            decision_path="deterministic_short_circuit" if not llm_attempted else "deterministic_after_llm_failure",
            model_used=model_used,
            provider_used=provider_used,
            prompt_version=prompt_version,
            ai_taxonomy=ai_taxonomy,
            ai_relevance={"is_ai_job": ai_taxonomy.is_ai_job, "categories": ai_taxonomy.legacy_ai_categories, "rationale": ai_taxonomy.rationale},
        )
        return primary_doc, {}

    def run(self, ctx: StageContext) -> StageResult:
        v2_doc, _meta = self._run_v2(ctx)
        v2_ai_patch = _build_ai_compat_projection(v2_doc)
        return StageResult(
            output=v2_ai_patch,
            stage_output=v2_doc.model_dump(),
            provider_used=v2_doc.provider_used,
            model_used=v2_doc.model_used,
            prompt_version=v2_doc.prompt_version,
        )


assert isinstance(ClassificationStage(), StageBase)
