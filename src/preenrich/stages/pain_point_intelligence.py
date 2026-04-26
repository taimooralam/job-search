"""Iteration-4.2.3 pain_point_intelligence stage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, List

from src.preenrich.blueprint_config import (
    current_git_sha,
    pain_point_intelligence_compat_projection_enabled,
    pain_point_supplemental_web_enabled,
    research_fallback_provider,
    research_fallback_transport,
    research_provider,
    research_transport,
    stakeholder_surface_enabled,
)
from src.preenrich.blueprint_models import (
    PainPointIntelligenceDoc,
    PromptMetadata,
    build_pain_point_intelligence_compact,
    normalize_pain_point_intelligence_payload,
    pain_input_hash,
)
from src.preenrich.blueprint_prompts import PROMPT_VERSIONS, build_p_pain_point_intelligence
from src.preenrich.research_transport import CodexResearchTransport
from src.preenrich.stages.base import _invoke_codex_json_traced
from src.preenrich.types import ArtifactWrite, StageContext, StageResult, StepConfig

PROMPT_VERSION = "pain_point_intelligence@v4.2.3"
STAGE_VERSION = "pain_point_intelligence.v4.2.3"
_RECOVERABLE_REPAIR_REASONS = {
    "missing_evidence_ref",
    "duplicate_pain_id",
    "proof_map_orphan_fk",
    "enum_drift",
    "cross_category_duplication",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _job_id(ctx: StageContext) -> str:
    return str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id") or "pain-point-intelligence")


def _level2_job_id(ctx: StageContext) -> str:
    return str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "pain-point-intelligence")


def _jd_excerpt(ctx: StageContext, *, limit: int = 1800) -> str:
    description = str(ctx.job_doc.get("description") or "").strip()
    if description:
        return description[:limit]
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    merged_view = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    pieces = [
        str(merged_view.get("title") or ctx.job_doc.get("title") or "").strip(),
        "\n".join(list(merged_view.get("responsibilities") or [])[:6]),
        "\n".join(list(merged_view.get("qualifications") or [])[:6]),
    ]
    return "\n".join(piece for piece in pieces if piece)[:limit]


def _band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.2:
        return "low"
    return "unresolved"


def _prompt_metadata(ctx: StageContext) -> PromptMetadata:
    return PromptMetadata(
        prompt_id="pain_point_intelligence",
        prompt_version=PROMPT_VERSIONS["pain_point_intelligence"],
        prompt_file_path=str(__file__).replace("stages\\pain_point_intelligence.py", "blueprint_prompts.py").replace(
            "stages/pain_point_intelligence.py", "blueprint_prompts.py"
        ),
        git_sha=current_git_sha(),
        provider=ctx.config.provider or "codex",
        model=ctx.config.primary_model,
        transport_used=ctx.config.transport or "none",
        fallback_provider=ctx.config.fallback_provider,
        fallback_transport=ctx.config.fallback_transport,
    )


def _trace_event(ctx: StageContext, name: str, metadata: dict[str, Any]) -> None:
    ctx.tracer.record_event(name, {"stage_name": ctx.stage_name or "pain_point_intelligence", **metadata})


def _start_substage(ctx: StageContext, substage: str, metadata: dict[str, Any]) -> Any:
    return ctx.tracer.start_substage_span(ctx.stage_name or "pain_point_intelligence", substage, metadata)


def _end_substage(ctx: StageContext, span: Any, output: dict[str, Any]) -> None:
    ctx.tracer.end_span(span, output=output)


def _research_source_id(index: int) -> str:
    return f"research_source_{index}"


def _jd_source_id(section: str, index: int) -> str:
    return f"jd:{section}:{index}"


def _append_evidence(bag: dict[str, list[dict[str, Any]]], category: str, text: str | None, ref: str, weight: float = 0.5) -> None:
    cleaned = (text or "").strip()
    if not cleaned:
        return
    bucket = bag.setdefault(category, [])
    if any(item["text"] == cleaned and item["source_ref"] == ref for item in bucket):
        return
    if len(bucket) >= 12:
        return
    bucket.append({"text": cleaned[:280], "source_ref": ref, "weight": round(weight, 2)})


def _build_source_registry(research: dict[str, Any], jd_facts: dict[str, Any]) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(research.get("sources") or []):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "").strip() or _research_source_id(index)
        if source_id in seen:
            continue
        seen.add(source_id)
        registry.append(
            {
                "source_id": source_id,
                "url": item.get("url"),
                "source_type": item.get("source_type") or "unknown",
                "fetched_at": item.get("fetched_at"),
                "trust_tier": item.get("trust_tier") or "tertiary",
                "title": item.get("title"),
            }
        )

    merged = jd_facts.get("merged_view") or {}
    for section in ("responsibilities", "qualifications", "implied_pain_points", "success_metrics"):
        for index, text in enumerate(list(merged.get(section) or [])[:6]):
            source_id = _jd_source_id(section, index)
            if source_id in seen:
                continue
            seen.add(source_id)
            registry.append(
                {
                    "source_id": source_id,
                    "url": None,
                    "source_type": "jd_section",
                    "fetched_at": None,
                    "trust_tier": "primary",
                    "title": f"JD {section} #{index + 1}",
                    "relevance": str(text)[:120],
                }
            )
    return registry


def _build_evidence_bag(
    *,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    application_surface: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    merged = jd_facts.get("merged_view") or {}
    company_profile = research.get("company_profile") or {}
    role_profile = research.get("role_profile") or {}
    application_profile = research.get("application_profile") or application_surface or {}
    bag: dict[str, list[dict[str, Any]]] = {}

    for index, text in enumerate(list(merged.get("responsibilities") or [])[:6]):
        lower = str(text).lower()
        category = "technical" if any(token in lower for token in ("architecture", "platform", "system", "ml", "ai", "data")) else "delivery"
        _append_evidence(bag, category, str(text), f"artifact:pre_enrichment.outputs.jd_facts.merged_view.responsibilities[{index}]", 0.9)
    for index, text in enumerate(list(merged.get("qualifications") or [])[:6]):
        lower = str(text).lower()
        category = "technical" if any(token in lower for token in ("python", "architecture", "distributed", "ml", "ai", "system")) else "business"
        _append_evidence(bag, category, str(text), f"artifact:pre_enrichment.outputs.jd_facts.merged_view.qualifications[{index}]", 0.75)
    for index, text in enumerate(list(merged.get("implied_pain_points") or [])[:6]):
        _append_evidence(bag, "delivery", str(text), f"artifact:pre_enrichment.outputs.jd_facts.merged_view.implied_pain_points[{index}]", 0.8)
    for index, text in enumerate(list(merged.get("success_metrics") or [])[:6]):
        _append_evidence(bag, "business", str(text), f"artifact:pre_enrichment.outputs.jd_facts.merged_view.success_metrics[{index}]", 0.7)
    for index, text in enumerate(list((merged.get("top_keywords") or [])[:10])):
        lower = str(text).lower()
        category = "technical" if any(token in lower for token in ("ai", "ml", "architecture", "platform", "data")) else "business"
        _append_evidence(bag, category, str(text), f"artifact:pre_enrichment.outputs.jd_facts.merged_view.top_keywords[{index}]", 0.45)

    for index, item in enumerate(list(role_profile.get("business_impact") or [])[:6]):
        _append_evidence(bag, "business", str(item), f"artifact:pre_enrichment.outputs.research_enrichment.role_profile.business_impact[{index}]", 0.9)
    for index, item in enumerate(list(role_profile.get("risk_landscape") or [])[:6]):
        _append_evidence(bag, "delivery", str(item), f"artifact:pre_enrichment.outputs.research_enrichment.role_profile.risk_landscape[{index}]", 0.85)
    for index, item in enumerate(list(role_profile.get("success_metrics") or [])[:6]):
        _append_evidence(bag, "business", str(item), f"artifact:pre_enrichment.outputs.research_enrichment.role_profile.success_metrics[{index}]", 0.85)
    for index, item in enumerate(list(role_profile.get("evaluation_signals") or [])[:6]):
        _append_evidence(bag, "stakeholder", str(item), f"artifact:pre_enrichment.outputs.research_enrichment.role_profile.evaluation_signals[{index}]", 0.65)
    for index, item in enumerate(list(role_profile.get("interview_themes") or [])[:6]):
        _append_evidence(bag, "stakeholder", str(item), f"artifact:pre_enrichment.outputs.research_enrichment.role_profile.interview_themes[{index}]", 0.55)
    if role_profile.get("why_now"):
        _append_evidence(bag, "business", str(role_profile.get("why_now")), "artifact:pre_enrichment.outputs.research_enrichment.role_profile.why_now", 0.8)

    for key in ("signals", "recent_signals", "role_relevant_signals", "scale_signals"):
        for index, item in enumerate(list(company_profile.get(key) or [])[:6]):
            if isinstance(item, dict):
                text = item.get("description") or item.get("summary") or item.get("value")
            else:
                text = str(item)
            _append_evidence(bag, "org", str(text), f"artifact:pre_enrichment.outputs.research_enrichment.company_profile.{key}[{index}]", 0.7)
    maturity = company_profile.get("ai_data_platform_maturity")
    if isinstance(maturity, dict):
        _append_evidence(
            bag,
            "technical",
            str(maturity.get("summary") or maturity.get("status") or ""),
            "artifact:pre_enrichment.outputs.research_enrichment.company_profile.ai_data_platform_maturity",
            0.6,
        )

    for index, item in enumerate(list(application_profile.get("friction_signals") or [])[:6]):
        _append_evidence(bag, "application", str(item), f"artifact:pre_enrichment.outputs.research_enrichment.application_profile.friction_signals[{index}]", 0.7)
    if application_profile.get("stale_signal") not in (None, "", "unknown", "active", "open"):
        _append_evidence(bag, "application", str(application_profile.get("stale_signal")), "artifact:pre_enrichment.outputs.research_enrichment.application_profile.stale_signal", 0.5)
    if application_profile.get("closed_signal") not in (None, "", "unknown", "open"):
        _append_evidence(bag, "application", str(application_profile.get("closed_signal")), "artifact:pre_enrichment.outputs.research_enrichment.application_profile.closed_signal", 0.5)

    for index, item in enumerate(list(stakeholder_surface.get("evaluator_coverage_target") or [])[:6]):
        _append_evidence(bag, "stakeholder", str(item), f"artifact:pre_enrichment.outputs.stakeholder_surface.evaluator_coverage_target[{index}]", 0.4)

    ai_intensity = str((classification.get("ai_taxonomy") or {}).get("intensity") or "").strip().lower()
    if ai_intensity:
        _append_evidence(bag, "technical", f"ai_intensity={ai_intensity}", "artifact:pre_enrichment.outputs.classification.ai_taxonomy.intensity", 0.4)
    return bag


def _preflight_summary(
    *,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    evidence_bag: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    merged = jd_facts.get("merged_view") or {}
    return {
        "role_family": classification.get("primary_role_category"),
        "seniority": merged.get("seniority_level"),
        "ai_intensity": ((classification.get("ai_taxonomy") or {}).get("intensity")),
        "research_status": research.get("status"),
        "stakeholder_surface_status": stakeholder_surface.get("status"),
        "evidence_bag_counts": {key: len(value) for key, value in evidence_bag.items()},
        "top_keywords_top10": list(merged.get("top_keywords") or [])[:10],
        "company_identity_band": (((research.get("company_profile") or {}).get("identity_confidence") or {}).get("band")),
    }


def _extract_subpayload(raw: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get(key)
    return value if isinstance(value, dict) else raw


def _proof_targets_for_category(category: str) -> list[str]:
    mapping = {
        "technical": ["architecture", "ai", "metric"],
        "business": ["metric", "stakeholder", "leadership"],
        "delivery": ["reliability", "process", "metric"],
        "org": ["leadership", "stakeholder", "scale"],
        "stakeholder": ["stakeholder", "leadership", "process"],
        "application": ["process", "compliance", "metric"],
    }
    return mapping.get(category, ["metric"])


def _section_bias_for_proof_types(proof_types: Iterable[str]) -> list[str]:
    ordered: list[str] = ["summary", "key_achievements", "experience"]
    types = set(proof_types)
    if "ai" in types:
        ordered.insert(2, "ai_highlights")
    if "compliance" in types:
        ordered.append("core_competencies")
    return list(dict.fromkeys(ordered))


def _deterministic_fail_open_doc(
    *,
    ctx: StageContext,
    research: dict[str, Any],
    evidence_bag: dict[str, list[dict[str, Any]]],
    source_registry: list[dict[str, Any]],
    input_hash: str,
    fail_open_reason: str,
) -> PainPointIntelligenceDoc:
    pains: list[dict[str, Any]] = []
    for category in ("technical", "delivery", "business", "application", "stakeholder", "org"):
        for item in list(evidence_bag.get(category) or [])[:1]:
            statement = item["text"]
            if len(statement) > 220:
                statement = statement[:217].rstrip() + "..."
            pain_id = f"p_{category}_{abs(hash(statement)) % (16**8):08x}"
            pains.append(
                {
                    "pain_id": pain_id,
                    "category": category,
                    "statement": statement,
                    "why_now": "Derived conservatively from deterministic upstream evidence.",
                    "source_scope": "jd_only" if fail_open_reason in {"jd_only_fallback", "thin_research", "llm_terminal_failure"} else "jd_plus_research",
                    "evidence_refs": [item["source_ref"]],
                    "urgency": "medium",
                    "related_stakeholders": list((research.get("stakeholder_surface") or {}).get("evaluator_coverage_target") or [])[:2],
                    "likely_proof_targets": _proof_targets_for_category(category),
                    "confidence": {"score": 0.45 if fail_open_reason != "llm_terminal_failure" else 0.2, "band": "low" if fail_open_reason != "llm_terminal_failure" else "unresolved", "basis": "Deterministic fail-open output."},
                }
            )
        if pains:
            break

    strategic_needs = []
    for item in list(evidence_bag.get("business") or [])[:2]:
        strategic_needs.append(
            {
                "category": "business",
                "statement": item["text"],
                "evidence_refs": [item["source_ref"]],
                "confidence": {"score": 0.42, "band": "low", "basis": "Deterministic fail-open strategic need."},
            }
        )
    risks = []
    for item in list(evidence_bag.get("delivery") or [])[:2]:
        risks.append(
            {
                "category": "delivery",
                "statement": item["text"],
                "evidence_refs": [item["source_ref"]],
                "confidence": {"score": 0.42, "band": "low", "basis": "Deterministic fail-open risk."},
            }
        )
    success_metrics = []
    for item in list(evidence_bag.get("business") or [])[:2]:
        success_metrics.append(
            {
                "statement": item["text"],
                "metric_kind": "qualitative",
                "horizon": "90_day",
                "evidence_refs": [item["source_ref"]],
                "confidence": {"score": 0.4, "band": "low", "basis": "Deterministic fail-open success metric."},
            }
        )
    proof_map = []
    for pain in pains:
        proof_types = pain["likely_proof_targets"] or ["metric"]
        proof_map.append(
            {
                "pain_id": pain["pain_id"],
                "preferred_proof_type": proof_types[0],
                "preferred_evidence_shape": "Candidate-agnostic deterministic fail-open proof target.",
                "bad_proof_patterns": ["generic restatement", "tool list without scope"],
                "affected_document_sections": _section_bias_for_proof_types(proof_types),
                "rationale": "Fail-open proof preference is derived from the pain category only.",
                "confidence": {"score": 0.35, "band": "low", "basis": "Deterministic fail-open proof map."},
            }
        )

    payload = normalize_pain_point_intelligence_payload(
        {
            "job_id": _job_id(ctx),
            "level2_job_id": _level2_job_id(ctx),
            "input_snapshot_id": ctx.input_snapshot_id,
            "pain_input_hash": input_hash,
            "prompt_version": PROMPT_VERSION,
            "provider_used": ctx.config.provider,
            "model_used": ctx.config.primary_model,
            "transport_used": ctx.config.transport or "none",
            "status": "unresolved" if fail_open_reason == "llm_terminal_failure" else "partial",
            "source_scope": "jd_only",
            "pain_points": pains if fail_open_reason != "llm_terminal_failure" else [],
            "strategic_needs": strategic_needs if fail_open_reason != "llm_terminal_failure" else [],
            "risks_if_unfilled": risks if fail_open_reason != "llm_terminal_failure" else [],
            "success_metrics": success_metrics if fail_open_reason != "llm_terminal_failure" else [],
            "proof_map": proof_map if fail_open_reason not in {"llm_terminal_failure"} else [],
            "search_terms": [{"term": str(item["text"])[:96], "intent": "retrieval", "source_basis": "deterministic_fail_open"} for item in list(evidence_bag.get("technical") or [])[:2]],
            "unresolved_questions": [f"pain_point_intelligence fail-open applied: {fail_open_reason}"],
            "sources": source_registry,
            "evidence": [
                {
                    "claim": "pain_point_intelligence fail-open output was derived from deterministic upstream evidence only.",
                    "source_ids": [item["source_id"] for item in source_registry[:4] if item.get("source_id")],
                }
            ],
            "confidence": {"score": 0.2 if fail_open_reason == "llm_terminal_failure" else 0.42, "band": "unresolved" if fail_open_reason == "llm_terminal_failure" else "low", "basis": "Fail-open deterministic output."},
            "cache_refs": {"pain_input_hash": input_hash},
            "timing": {"generated_at": _now_iso()},
            "usage": {"provider": ctx.config.provider, "model": ctx.config.primary_model},
            "debug_context": {
                "evidence_bag_counts": {key: len(value) for key, value in evidence_bag.items()},
                "deterministic_validator_diffs": [],
                "llm_request_ids": [],
                "retry_reasons": [],
                "supplemental_web_queries": [],
                "normalization_events": [],
                "richer_output_retained": [],
                "rejected_output": [],
                "defaults_applied": ["deterministic_fail_open"],
            },
            "fail_open_reason": fail_open_reason,
            "trace_ref": {"trace_id": ctx.tracer.trace_id, "trace_url": ctx.tracer.trace_url},
        },
        jd_excerpt=_jd_excerpt(ctx),
    )
    doc = PainPointIntelligenceDoc.model_validate(payload)
    doc.status = "unresolved" if fail_open_reason == "llm_terminal_failure" else "partial"
    return doc


def _classify_repair_reason(errors: list[str]) -> str | None:
    joined = " | ".join(errors).lower()
    if "evidence_ref" in joined:
        return "missing_evidence_ref"
    if "pain_ids must be unique" in joined:
        return "duplicate_pain_id"
    if "proof_map pain_id does not resolve" in joined:
        return "proof_map_orphan_fk"
    if "invalid" in joined or "must be a canonical" in joined:
        return "enum_drift"
    if "cross-category duplicate" in joined:
        return "cross_category_duplication"
    return None


def _evidence_surface_key(ref: str) -> str:
    if ref.startswith("source:"):
        return "source"
    if not ref.startswith("artifact:"):
        return ref
    path = ref.split(":", 1)[1]
    if "jd_facts" in path:
        return "jd"
    if "research_enrichment" in path:
        return "research"
    if "stakeholder_surface" in path:
        return "stakeholder"
    if "application_surface" in path:
        return "application"
    return "artifact"


def _stabilize_doc(doc: PainPointIntelligenceDoc) -> PainPointIntelligenceDoc:
    diffs = list(((doc.debug_context or {}).deterministic_validator_diffs if doc.debug_context else []) or [])
    for entry in doc.pain_points:
        surfaces = {_evidence_surface_key(ref) for ref in entry.evidence_refs}
        if entry.urgency == "high" and (entry.source_scope == "jd_only" or len(surfaces) < 2):
            entry.urgency = "medium"
            diffs.append(f"clamped urgency=high -> medium for {entry.pain_id}")
    if doc.debug_context is not None:
        doc.debug_context.deterministic_validator_diffs = diffs
    return doc


def _validate_doc(
    doc: PainPointIntelligenceDoc,
    *,
    inputs: dict[str, Any],
    jd_excerpt: str,
) -> list[str]:
    errors: list[str] = []
    source_ids = {item.source_id for item in doc.sources}
    for bucket_name, entries in (
        ("pain_points", doc.pain_points),
        ("strategic_needs", doc.strategic_needs),
        ("risks_if_unfilled", doc.risks_if_unfilled),
        ("success_metrics", doc.success_metrics),
    ):
        for index, entry in enumerate(entries):
            statement = getattr(entry, "statement", None) or ""
            lower = statement.lower()
            for blocked in ("team player", "strong communicator", "passionate about", "rockstar", "ninja", "fast paced environment", "fast-paced environment"):
                if blocked in lower and blocked not in jd_excerpt.lower():
                    errors.append(f"{bucket_name}[{index}] generic boilerplate rejected: {blocked}")
            for ref in getattr(entry, "evidence_refs", []):
                if ref.startswith("source:") and ref.split(":", 1)[1] not in source_ids:
                    errors.append(f"{bucket_name}[{index}] missing_evidence_ref:{ref}")
                elif ref.startswith("artifact:") and not _artifact_ref_exists(ref.split(":", 1)[1], inputs):
                    errors.append(f"{bucket_name}[{index}] missing_evidence_ref:{ref}")
            if bucket_name == "pain_points" and getattr(entry, "urgency", None) == "high":
                surfaces = {_evidence_surface_key(ref) for ref in entry.evidence_refs}
                if entry.source_scope == "jd_only" or len(surfaces) < 2:
                    errors.append(f"{bucket_name}[{index}] unsupported urgency=high")
    for index, entry in enumerate(doc.proof_map):
        if entry.pain_id not in {item.pain_id for item in doc.pain_points}:
            errors.append(f"proof_map_orphan_fk:{entry.pain_id}")
    return errors


def _artifact_ref_exists(path: str, inputs: dict[str, Any]) -> bool:
    if path == "jd_excerpt":
        return True
    current: Any = inputs
    for segment in path.split("."):
        if isinstance(current, dict):
            match = segment
            index = None
            if segment.endswith("]") and "[" in segment:
                match, index_text = segment[:-1].split("[", 1)
                try:
                    index = int(index_text)
                except Exception:
                    return False
            if match:
                if match not in current:
                    return False
                current = current[match]
            if index is not None:
                if not isinstance(current, list) or index < 0 or index >= len(current):
                    return False
                current = current[index]
            continue
        return False
    return True


def _repair_prompt(*, base_prompt: str, raw_payload: dict[str, Any], errors: list[str]) -> str:
    return "\n".join(
        [
            base_prompt,
            "",
            "Repair pass. Keep the original structure, but fix only these deterministic validation errors:",
            *[f"- {error}" for error in errors[:10]],
            "Do not add new facts. Do not fabricate evidence_refs. Remove or downgrade unsupported claims instead.",
            "Return only the corrected `pain_point_intelligence` JSON object.",
            "Original output:",
            str(raw_payload),
        ]
    )


def _maybe_supplemental_web(
    *,
    ctx: StageContext,
    research: dict[str, Any],
    evidence_bag: dict[str, list[dict[str, Any]]],
    source_registry: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if not pain_point_supplemental_web_enabled():
        return [], [], []
    if str(research.get("status") or "unresolved") not in {"partial", "unresolved"}:
        return [], [], []
    research_count = sum(len(items) for key, items in evidence_bag.items() if key in {"technical", "business", "delivery", "org"})
    if research_count >= 3:
        return [], [], []

    supplemental_cfg = StepConfig(
        provider=research_provider(),
        primary_model=ctx.config.primary_model or "gpt-5.4",
        fallback_provider=research_fallback_provider(),
        fallback_transport=research_fallback_transport(),
        transport=research_transport(),
        max_web_queries=min(ctx.config.max_web_queries or 2, 2),
        max_fetches=min(ctx.config.max_fetches or 2, 2),
        allow_repo_context=False,
    )
    transport = CodexResearchTransport(supplemental_cfg)
    if not transport.is_live_configured():
        return [], [], []

    span = _start_substage(
        ctx,
        "supplemental_web",
        {
            "research_status": research.get("status"),
            "max_web_queries": supplemental_cfg.max_web_queries,
            "max_fetches": supplemental_cfg.max_fetches,
        },
    )
    prompt = "\n".join(
        [
            "Return ONLY valid JSON with keys evidence_snippets and sources.",
            "You are doing a bounded supplemental web check for pain-point evidence.",
            "Do not fabricate company events. Use only fetched public-professional evidence.",
            "Budget: max_web_queries=2, max_fetches=2.",
            "Schema:",
            '{"evidence_snippets":[{"category":"technical|business|delivery|org|stakeholder|application","text":"...", "source_id":"...", "weight":0.0}], "sources":[{"source_id":"...", "url":"...", "source_type":"supplemental_web", "trust_tier":"secondary"}]}',
            f"Job title: {ctx.job_doc.get('title')}",
            f"Company: {ctx.job_doc.get('company')}",
            f"JD excerpt: {_jd_excerpt(ctx, limit=1200)}",
        ]
    )
    result = transport.invoke_json(
        prompt=prompt,
        job_id=f"{_job_id(ctx)}:pain_point_intelligence:supplemental_web",
        tracer=ctx.tracer,
        stage_name=ctx.stage_name or "pain_point_intelligence",
        substage="supplemental_web",
    )
    if not result.success or not isinstance(result.payload, dict):
        _end_substage(ctx, span, {"status": "partial", "success": False, "error": result.error})
        return [], [], []
    evidence_snippets = [item for item in list(result.payload.get("evidence_snippets") or []) if isinstance(item, dict)]
    sources = [item for item in list(result.payload.get("sources") or []) if isinstance(item, dict)]
    queries = [str(item.get("text") or "")[:120] for item in evidence_snippets[:2]]
    _end_substage(ctx, span, {"status": "completed", "success": True, "evidence_count": len(evidence_snippets), "source_count": len(sources)})
    return evidence_snippets, sources, queries


class PainPointIntelligenceStage:
    name: str = "pain_point_intelligence"
    dependencies: List[str] = ["jd_facts", "classification", "research_enrichment"]

    def run(self, ctx: StageContext) -> StageResult:
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        jd_facts = outputs.get("jd_facts") or {}
        classification = outputs.get("classification") or {}
        research = outputs.get("research_enrichment") or {}
        stakeholder_surface = outputs.get("stakeholder_surface") or {}
        application_surface = outputs.get("application_surface") or {}
        existing = outputs.get("pain_point_intelligence") or {}

        mine_span = _start_substage(ctx, "evidence_mine", {"job_id": _job_id(ctx), "level2_job_id": _level2_job_id(ctx)})
        evidence_bag = _build_evidence_bag(
            jd_facts=jd_facts,
            classification=classification,
            research=research,
            stakeholder_surface=stakeholder_surface,
            application_surface=application_surface,
        )
        source_registry = _build_source_registry(research, jd_facts)
        preflight = _preflight_summary(
            jd_facts=jd_facts,
            classification=classification,
            research=research,
            stakeholder_surface=stakeholder_surface,
            evidence_bag=evidence_bag,
        )
        _end_substage(ctx, mine_span, {"status": "completed", "evidence_bag_counts": preflight["evidence_bag_counts"], "source_registry_count": len(source_registry)})

        input_hash = pain_input_hash(
            {
                "jd_facts": jd_facts.get("merged_view") or {},
                "classification": {
                    "primary_role_category": classification.get("primary_role_category"),
                    "tone_family": classification.get("tone_family"),
                    "ai_taxonomy": classification.get("ai_taxonomy") or {},
                },
                "research_input_hash": research.get("research_input_hash"),
                "research_status": research.get("status"),
                "stakeholder_coverage_digest": {
                    "status": stakeholder_surface.get("status"),
                    "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [],
                }
                if stakeholder_surface_enabled()
                else {},
                "prompt_version": PROMPT_VERSION,
            }
        )

        if (
            isinstance(existing, dict)
            and existing.get("pain_input_hash") == input_hash
            and existing.get("input_snapshot_id") == ctx.input_snapshot_id
            and existing.get("prompt_version") == PROMPT_VERSION
        ):
            _trace_event(
                ctx,
                "scout.preenrich.pain_point_intelligence.cache.hit",
                {
                    "cache_key": input_hash,
                    "hit_reason": "same_snapshot",
                    "upstream_research_status": research.get("status"),
                    "prompt_version": PROMPT_VERSION,
                },
            )
            artifact = _stabilize_doc(PainPointIntelligenceDoc.model_validate(normalize_pain_point_intelligence_payload(existing, jd_excerpt=_jd_excerpt(ctx))))
            cached_stage_output = dict(existing)
            cached_stage_output.setdefault("trace_ref", {"trace_id": ctx.tracer.trace_id, "trace_url": ctx.tracer.trace_url})
            cached_stage_output.setdefault("compact", build_pain_point_intelligence_compact(cached_stage_output))
            return StageResult(
                stage_output=cached_stage_output,
                output=self._compat_output(artifact),
                provider_used=artifact.provider_used,
                model_used=artifact.model_used,
                prompt_version=artifact.prompt_version,
            )

        _trace_event(
            ctx,
            "scout.preenrich.pain_point_intelligence.cache.miss",
            {
                "cache_key": input_hash,
                "upstream_research_status": research.get("status"),
                "prompt_version": PROMPT_VERSION,
            },
        )

        supplemental_evidence, supplemental_sources, supplemental_queries = _maybe_supplemental_web(
            ctx=ctx,
            research=research,
            evidence_bag=evidence_bag,
            source_registry=source_registry,
        )
        for item in supplemental_evidence:
            if not isinstance(item, dict):
                continue
            _append_evidence(
                evidence_bag,
                str(item.get("category") or "business"),
                str(item.get("text") or ""),
                f"source:{item.get('source_id')}" if item.get("source_id") else "source:supplemental_web",
                float(item.get("weight") or 0.55),
            )
        source_registry.extend(item for item in supplemental_sources if isinstance(item, dict))

        prompt_span = _start_substage(
            ctx,
            "prompt_build",
            {
                "evidence_bag_counts": {key: len(value) for key, value in evidence_bag.items()},
                "source_registry_count": len(source_registry),
                "supplemental_web_enabled": pain_point_supplemental_web_enabled(),
            },
        )
        prompt = build_p_pain_point_intelligence(
            preflight=preflight,
            jd_excerpt=_jd_excerpt(ctx),
            classification_excerpt={
                "primary_role_category": classification.get("primary_role_category"),
                "tone_family": classification.get("tone_family"),
                "ai_taxonomy": classification.get("ai_taxonomy") or {},
            },
            research_excerpt={
                "status": research.get("status"),
                "company_profile": research.get("company_profile") or {},
                "role_profile": research.get("role_profile") or {},
                "application_profile": research.get("application_profile") or application_surface or {},
            },
            stakeholder_surface_excerpt={
                "status": stakeholder_surface.get("status"),
                "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [],
                "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or [],
            },
            evidence_bag=evidence_bag,
            source_registry=source_registry,
        )
        _end_substage(ctx, prompt_span, {"status": "completed", "prompt_version": PROMPT_VERSION, "prompt_length": len(prompt)})

        attempts: list[dict[str, Any]] = []
        raw_doc: dict[str, Any] | None = None
        llm_attempt_model = ctx.config.primary_model or "gpt-5.4"
        llm_payload, attempt = _invoke_codex_json_traced(
            prompt=prompt,
            model=llm_attempt_model,
            job_id=f"{_job_id(ctx)}:pain_point_intelligence",
            tracer=ctx.tracer,
            stage_name=ctx.stage_name or "pain_point_intelligence",
            substage="llm_call.primary",
            codex_cwd=ctx.config.codex_workdir,
            reasoning_effort=ctx.config.reasoning_effort,
        )
        attempts.append(attempt)
        if isinstance(llm_payload, dict):
            raw_doc = _extract_subpayload(llm_payload, "pain_point_intelligence")
        if raw_doc is None and ctx.config.fallback_model:
            fallback_payload, fallback_attempt = _invoke_codex_json_traced(
                prompt=prompt,
                model=ctx.config.fallback_model,
                job_id=f"{_job_id(ctx)}:pain_point_intelligence:fallback",
                tracer=ctx.tracer,
                stage_name=ctx.stage_name or "pain_point_intelligence",
                substage="llm_call.fallback",
                codex_cwd=ctx.config.codex_workdir,
                reasoning_effort=ctx.config.reasoning_effort,
            )
            attempts.append(fallback_attempt)
            llm_attempt_model = ctx.config.fallback_model
            if isinstance(fallback_payload, dict):
                raw_doc = _extract_subpayload(fallback_payload, "pain_point_intelligence")

        if raw_doc is None:
            artifact = _deterministic_fail_open_doc(
                ctx=ctx,
                research=research,
                evidence_bag=evidence_bag,
                source_registry=source_registry,
                input_hash=input_hash,
                fail_open_reason="llm_terminal_failure",
            )
            _trace_event(
                ctx,
                "scout.preenrich.pain_point_intelligence.fail_open",
                {"fail_open_reason": "llm_terminal_failure", "pain_input_hash": input_hash},
            )
            return self._result_from_artifact(ctx, artifact)

        normalized = normalize_pain_point_intelligence_payload(raw_doc, jd_excerpt=_jd_excerpt(ctx))
        normalized.update(
            {
                "job_id": _job_id(ctx),
                "level2_job_id": _level2_job_id(ctx),
                "input_snapshot_id": ctx.input_snapshot_id,
                "pain_input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
                "prompt_metadata": _prompt_metadata(ctx).model_dump(),
                "provider_used": ctx.config.provider,
                "model_used": llm_attempt_model,
                "transport_used": ctx.config.transport or "none",
                "cache_refs": {"pain_input_hash": input_hash},
                "timing": {"generated_at": _now_iso()},
                "usage": {"provider": ctx.config.provider, "model": llm_attempt_model, "attempts": attempts},
                "trace_ref": {"trace_id": ctx.tracer.trace_id, "trace_url": ctx.tracer.trace_url},
            }
        )
        if normalized.get("debug_context"):
            normalized["debug_context"]["evidence_bag_counts"] = {key: len(value) for key, value in evidence_bag.items()}
            normalized["debug_context"]["supplemental_web_queries"] = supplemental_queries

        post_span = _start_substage(ctx, "post_pass", {"pain_input_hash": input_hash, "source_registry_count": len(source_registry)})
        doc = _stabilize_doc(PainPointIntelligenceDoc.model_validate(normalized))
        errors = _validate_doc(
            doc,
            inputs={"pre_enrichment": {"outputs": outputs}},
            jd_excerpt=_jd_excerpt(ctx),
        )
        repair_reason = _classify_repair_reason(errors)
        if errors and repair_reason in _RECOVERABLE_REPAIR_REASONS:
            repair_prompt = _repair_prompt(base_prompt=prompt, raw_payload=raw_doc, errors=errors)
            repair_payload, repair_attempt = _invoke_codex_json_traced(
                prompt=repair_prompt,
                model=llm_attempt_model,
                job_id=f"{_job_id(ctx)}:pain_point_intelligence:repair",
                tracer=ctx.tracer,
                stage_name=ctx.stage_name or "pain_point_intelligence",
                substage="schema_repair",
                codex_cwd=ctx.config.codex_workdir,
                reasoning_effort=ctx.config.reasoning_effort,
            )
            attempts.append(repair_attempt)
            repaired_raw = _extract_subpayload(repair_payload, "pain_point_intelligence") if isinstance(repair_payload, dict) else None
            if isinstance(repaired_raw, dict):
                normalized = normalize_pain_point_intelligence_payload(repaired_raw, jd_excerpt=_jd_excerpt(ctx))
                normalized.update(
                    {
                        "job_id": _job_id(ctx),
                        "level2_job_id": _level2_job_id(ctx),
                        "input_snapshot_id": ctx.input_snapshot_id,
                        "pain_input_hash": input_hash,
                        "prompt_version": PROMPT_VERSION,
                        "prompt_metadata": _prompt_metadata(ctx).model_dump(),
                        "provider_used": ctx.config.provider,
                        "model_used": llm_attempt_model,
                        "transport_used": ctx.config.transport or "none",
                        "cache_refs": {"pain_input_hash": input_hash},
                        "timing": {"generated_at": _now_iso()},
                        "usage": {"provider": ctx.config.provider, "model": llm_attempt_model, "attempts": attempts},
                        "trace_ref": {"trace_id": ctx.tracer.trace_id, "trace_url": ctx.tracer.trace_url},
                    }
                )
                if normalized.get("debug_context"):
                    retry_reasons = list((normalized["debug_context"] or {}).get("retry_reasons") or [])
                    retry_reasons.append(repair_reason)
                    normalized["debug_context"]["retry_reasons"] = retry_reasons
                    normalized["debug_context"]["evidence_bag_counts"] = {key: len(value) for key, value in evidence_bag.items()}
                    normalized["debug_context"]["supplemental_web_queries"] = supplemental_queries
                doc = _stabilize_doc(PainPointIntelligenceDoc.model_validate(normalized))
                errors = _validate_doc(doc, inputs={"pre_enrichment": {"outputs": outputs}}, jd_excerpt=_jd_excerpt(ctx))

        research_status = str(research.get("status") or "unresolved")
        if not errors:
            if research_status in {"partial", "unresolved", "no_research"}:
                doc.status = "partial"
                doc.source_scope = "jd_only"
                doc.fail_open_reason = "thin_research"
                doc.unresolved_questions = list(dict.fromkeys([*doc.unresolved_questions, "Research evidence was thin; output downgraded to jd_only."]))
            elif supplemental_queries:
                doc.source_scope = "supplemental_web"
            else:
                doc.source_scope = "jd_plus_research"
        else:
            doc = _deterministic_fail_open_doc(
                ctx=ctx,
                research=research,
                evidence_bag=evidence_bag,
                source_registry=source_registry,
                input_hash=input_hash,
                fail_open_reason="schema_repair_exhausted",
            )
            _trace_event(
                ctx,
                "scout.preenrich.pain_point_intelligence.fail_open",
                {"fail_open_reason": "schema_repair_exhausted", "pain_input_hash": input_hash, "validator_errors": errors[:6]},
            )

        _end_substage(
            ctx,
            post_span,
            {
                "status": doc.status,
                "source_scope": doc.source_scope,
                "pains_count": len(doc.pain_points),
                "proof_map_size": len(doc.proof_map),
                "unresolved_questions_count": len(doc.unresolved_questions),
                "fail_open_reason": doc.fail_open_reason,
            },
        )

        if doc.fail_open_reason:
            _trace_event(
                ctx,
                "scout.preenrich.pain_point_intelligence.fail_open",
                {"fail_open_reason": doc.fail_open_reason, "pain_input_hash": input_hash},
            )

        return self._result_from_artifact(ctx, doc)

    def _compat_output(self, artifact: PainPointIntelligenceDoc) -> dict[str, Any]:
        if not pain_point_intelligence_compat_projection_enabled():
            return {}
        return {
            "pain_points": [item.statement for item in artifact.pain_points],
            "strategic_needs": [item.statement for item in artifact.strategic_needs],
            "risks_if_unfilled": [item.statement for item in artifact.risks_if_unfilled],
            "success_metrics": [item.statement for item in artifact.success_metrics],
        }

    def _result_from_artifact(self, ctx: StageContext, artifact: PainPointIntelligenceDoc) -> StageResult:
        compact = build_pain_point_intelligence_compact(artifact)
        stage_output = artifact.model_dump()
        stage_output["trace_ref"] = {"trace_id": ctx.tracer.trace_id, "trace_url": ctx.tracer.trace_url}
        stage_output["compact"] = compact
        return StageResult(
            output=self._compat_output(artifact),
            stage_output=stage_output,
            artifact_writes=[
                ArtifactWrite(
                    collection="pain_point_intelligence",
                    unique_filter={
                        "job_id": artifact.job_id,
                        "input_snapshot_id": artifact.input_snapshot_id,
                        "prompt_version": artifact.prompt_version,
                    },
                    document=stage_output,
                    ref_name="pain_point_intelligence",
                )
            ],
            provider_used=artifact.provider_used,
            model_used=artifact.model_used,
            prompt_version=artifact.prompt_version,
        )
