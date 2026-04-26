"""Iteration-4.1.3 application_surface stage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from src.preenrich.blueprint_config import web_research_enabled
from src.preenrich.blueprint_models import (
    ApplicationSurfaceDoc,
    ConfidenceDoc,
    EvidenceEntry,
    SourceEntry,
    normalize_application_surface_payload,
)
from src.preenrich.blueprint_prompts import build_p_application_surface, build_p_transport_preamble
from src.preenrich.research_transport import CodexResearchTransport
from src.preenrich.stages.blueprint_common import (
    AGGREGATOR_HOST_TOKENS,
    canonical_domain_from_url,
    company_slug,
    detect_ats_vendor,
    detect_portal_family,
    detect_remote_policy,
    is_aggregator_url,
    normalize_url,
    url_matches_company,
)
from src.preenrich.types import StageContext, StageResult

PROMPT_VERSION = "P-application-surface@v1.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _candidate_urls(ctx: StageContext) -> list[str]:
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    raw_candidates = [
        ctx.job_doc.get("application_url"),
        ctx.job_doc.get("jobUrl"),
        ctx.job_doc.get("job_url"),
        ctx.job_doc.get("url"),
        jd_facts.get("application_url"),
    ]
    normalized = [normalize_url(item) for item in raw_candidates if item]
    return [item for item in dict.fromkeys(normalized) if item]


def _location_payload(ctx: StageContext) -> dict[str, Any]:
    location = str(ctx.job_doc.get("location") or "").strip()
    description = str(ctx.job_doc.get("description") or "")
    parts = [part.strip() for part in location.split(",") if part.strip()]
    return {
        "country": parts[-1][:2].upper() if parts else "unknown",
        "region": parts[-2] if len(parts) >= 2 else (parts[0] if parts else "unknown"),
        "city": parts[0] if parts else "unknown",
        "remote_policy": detect_remote_policy(description, location),
    }


def _closed_signal(ctx: StageContext, candidates: list[str]) -> tuple[str, str, list[str]]:
    description = str(ctx.job_doc.get("description") or "").lower()
    notes: list[str] = []
    if any(token in description for token in ("no longer accepting", "position filled", "closed", "role has been filled")):
        notes.append("Job description contains closed or stale language.")
        return "closed", "closed", notes
    if candidates and all(is_aggregator_url(url) for url in candidates):
        notes.append("Only aggregator candidates observed; canonical application path remains unverified.")
        return "likely_stale", "unknown", notes
    return "active", "open", notes


def _dedupe_text(items: list[str]) -> list[str]:
    return [item for item in dict.fromkeys(item.strip() for item in items if item and item.strip())]


def _dedupe_sources(*source_groups: list[SourceEntry]) -> list[SourceEntry]:
    deduped: dict[str, SourceEntry] = {}
    for group in source_groups:
        for item in group or []:
            try:
                source = item if isinstance(item, SourceEntry) else SourceEntry.model_validate(item)
            except Exception:
                continue
            deduped[source.source_id] = source
    return list(deduped.values())


def _dedupe_evidence(*evidence_groups: list[EvidenceEntry]) -> list[EvidenceEntry]:
    deduped: dict[tuple[str, tuple[str, ...]], EvidenceEntry] = {}
    for group in evidence_groups:
        for item in group or []:
            try:
                evidence = item if isinstance(item, EvidenceEntry) else EvidenceEntry.model_validate(item)
            except Exception:
                continue
            deduped[(evidence.claim, tuple(evidence.source_ids))] = evidence
    return list(deduped.values())


def _deterministic_surface(ctx: StageContext) -> ApplicationSurfaceDoc:
    candidates = _candidate_urls(ctx)
    now_iso = _now_iso()
    company = str(ctx.job_doc.get("company") or "").strip()
    company_domain = canonical_domain_from_url(
        ctx.job_doc.get("company_url") or (ctx.job_doc.get("company_research") or {}).get("url")
    )
    safe_candidates = [url for url in candidates if url_matches_company(url, company, company_domain)]
    non_aggregators = [url for url in safe_candidates if not is_aggregator_url(url)]
    canonical_candidate = non_aggregators[0] if non_aggregators else None
    if not canonical_candidate and len(safe_candidates) == 1 and not is_aggregator_url(safe_candidates[0]):
        canonical_candidate = safe_candidates[0]

    portal_target = canonical_candidate or (safe_candidates[0] if safe_candidates else (candidates[0] if candidates else None))
    portal_family = detect_portal_family(portal_target) or "unknown"
    ats_vendor = detect_ats_vendor(portal_target)
    stale_signal, closed_signal, detection_notes = _closed_signal(ctx, candidates)

    multi_step_likely = portal_family in {"greenhouse", "lever", "workday", "ashby", "smartrecruiters", "icims"}
    account_creation_likely = portal_family in {"workday", "bamboohr", "successfactors"}
    is_direct_apply = bool(canonical_candidate and not is_aggregator_url(canonical_candidate))
    friction_signals: list[str] = []
    if multi_step_likely:
        friction_signals.append("multi_step_likely")
    if account_creation_likely:
        friction_signals.append("account_creation_likely")
    if stale_signal in {"likely_stale", "closed"}:
        friction_signals.append("stale_or_closed")

    if canonical_candidate and stale_signal == "active":
        resolution_status = "resolved"
        status = "resolved"
        ui_actionability = "ready"
        confidence = ConfidenceDoc(score=0.86, band="high", basis="Observed non-aggregator application URL matched company or ATS family.")
        resolution_method = "direct_ats" if portal_family not in {"unknown", "custom_unknown"} else "direct_observed"
        resolution_note = "Resolved from observed job/application URL without cross-company drift."
    elif safe_candidates:
        resolution_status = "partial"
        status = "partial"
        ui_actionability = "caution"
        confidence = ConfidenceDoc(score=0.58, band="medium", basis="Observed candidates are company-safe but canonical verification is incomplete.")
        resolution_method = "observed_candidates"
        resolution_note = "Company-safe candidates found, but canonical application URL remains unverified."
    elif len(candidates) > 1:
        resolution_status = "ambiguous"
        status = "ambiguous"
        ui_actionability = "caution"
        confidence = ConfidenceDoc(score=0.32, band="low", basis="Multiple observed candidates with no company-safe canonical winner.")
        resolution_method = "unresolved"
        resolution_note = "Observed multiple candidate URLs without a safe canonical winner."
    else:
        resolution_status = "unresolved"
        status = "unresolved"
        ui_actionability = "unknown"
        confidence = ConfidenceDoc(score=0.0, band="unresolved", basis="No verified company-safe application URL was observed.")
        resolution_method = "unresolved"
        resolution_note = "No application URL candidates were verified."

    if stale_signal == "closed":
        status = "partial" if canonical_candidate else "unresolved"
        resolution_status = "partial" if canonical_candidate else "unresolved"
        ui_actionability = "blocked"
        resolution_note = "Posting appears closed or stale based on observed content."

    source = SourceEntry(
        source_id="s_job_doc",
        url=candidates[0] if candidates else normalize_url(ctx.job_doc.get("jobUrl") or ctx.job_doc.get("url")),
        source_type="job_document",
        fetched_at=now_iso,
        trust_tier="primary",
        relevance="Observed job-supplied application candidates.",
        domain=canonical_domain_from_url(candidates[0]) if candidates else None,
    )
    evidence = [
        EvidenceEntry(
            claim="Application URL candidates were derived from the job document and jd_facts extraction.",
            source_ids=[source.source_id],
            basis="deterministic_input",
        )
    ]
    duplicate_urls = [url for url in candidates if url != canonical_candidate]
    if canonical_candidate and duplicate_urls:
        evidence.append(
            EvidenceEntry(
                claim="Multiple candidate application URLs were observed; canonical URL was chosen using company-safe preference ordering.",
                source_ids=[source.source_id],
                basis="deterministic_candidate_rank",
            )
        )

    return ApplicationSurfaceDoc(
        status=status,
        job_url=candidates[0] if candidates else None,
        application_url=canonical_candidate or ctx.job_doc.get("application_url"),
        canonical_application_url=canonical_candidate,
        redirect_chain=[candidates[0]] if candidates else [],
        last_verified_at=now_iso if candidates else None,
        final_http_status="unknown",
        resolution_method=resolution_method,
        resolution_confidence=confidence,
        resolution_status=resolution_status,
        resolution_note=resolution_note,
        ui_actionability=ui_actionability,
        portal_family=portal_family,
        ats_vendor=ats_vendor,
        is_direct_apply=is_direct_apply if candidates else None,
        account_creation_likely=account_creation_likely if candidates else None,
        multi_step_likely=multi_step_likely if candidates else None,
        form_fetch_status="not_attempted",
        stale_signal=stale_signal,
        closed_signal=closed_signal,
        duplicate_signal={"canonical": canonical_candidate, "duplicates": duplicate_urls},
        geo_normalization=_location_payload(ctx),
        apply_instructions="Use the canonical application URL when available." if canonical_candidate else None,
        apply_caveats=detection_notes + ([] if canonical_candidate else ["Canonical application URL remains unresolved."]),
        sources=[source],
        evidence=evidence,
        confidence=confidence,
        candidates=candidates,
        friction_signals=friction_signals,
        notes=detection_notes + ([f"company_slug={company_slug(company)}"] if company else []),
    )


def _should_attempt_live(surface: ApplicationSurfaceDoc) -> bool:
    if surface.resolution_status in {"unresolved", "ambiguous"}:
        return True
    return not bool(surface.canonical_application_url)


def _validate_live_surface(surface: ApplicationSurfaceDoc, company: str, company_domain: str | None) -> ApplicationSurfaceDoc:
    candidate = normalize_url(surface.canonical_application_url or surface.application_url)
    if candidate and not url_matches_company(candidate, company, company_domain):
        surface.canonical_application_url = None
        surface.application_url = None
        surface.status = "unresolved"
        surface.resolution_status = "unresolved"
        surface.ui_actionability = "blocked"
        surface.resolution_note = "Live research returned a cross-company candidate URL and it was rejected."
        surface.confidence = ConfidenceDoc(
            score=0.0,
            band="unresolved",
            basis="Returned application URL did not match the company domain or a known ATS family.",
        )
        surface.apply_caveats = _dedupe_text(list(surface.apply_caveats) + ["Rejected a cross-company application URL candidate."])
        surface.debug_context["rejected_candidate_url"] = candidate
        return surface
    if candidate and not surface.portal_family:
        surface.portal_family = detect_portal_family(candidate) or "custom_unknown"
    if candidate and not surface.ats_vendor:
        surface.ats_vendor = detect_ats_vendor(candidate)
    if candidate and surface.resolution_status == "unresolved":
        surface.resolution_status = "partial"
    if candidate and surface.status == "unresolved":
        surface.status = "partial"
    if candidate and surface.ui_actionability == "unknown":
        surface.ui_actionability = "caution"
    if candidate and surface.final_http_status in {None, "unknown"}:
        surface.final_http_status = 200
    if candidate and not surface.resolution_note:
        surface.resolution_note = "Verified employer or ATS application entrypoint found, but an exact job-specific deep link was not directly observed."
    return surface


def _merge_surface(base: ApplicationSurfaceDoc, live: ApplicationSurfaceDoc, company: str, company_domain: str | None) -> ApplicationSurfaceDoc:
    live = _validate_live_surface(live, company, company_domain)
    merged = base.model_copy(deep=True)
    if live.job_url:
        merged.job_url = live.job_url
    if live.canonical_application_url:
        merged.canonical_application_url = live.canonical_application_url
        merged.application_url = live.canonical_application_url
    if live.redirect_chain:
        merged.redirect_chain = _dedupe_text(list(base.redirect_chain) + list(live.redirect_chain))
    if live.last_verified_at:
        merged.last_verified_at = live.last_verified_at
    if live.final_http_status not in {None, "unknown"}:
        merged.final_http_status = live.final_http_status
    for field_name in (
        "resolution_method",
        "resolution_status",
        "resolution_note",
        "ui_actionability",
        "portal_family",
        "ats_vendor",
        "is_direct_apply",
        "account_creation_likely",
        "multi_step_likely",
        "form_fetch_status",
        "stale_signal",
        "closed_signal",
        "apply_instructions",
        "status",
    ):
        value = getattr(live, field_name)
        if value is not None and value != "" and value != [] and value != {}:
            setattr(merged, field_name, value)
    merged.apply_instruction_lines = _dedupe_text(list(base.apply_instruction_lines) + list(live.apply_instruction_lines))
    merged.duplicate_signal = live.duplicate_signal or base.duplicate_signal
    merged.geo_normalization = live.geo_normalization or base.geo_normalization
    merged.apply_caveats = _dedupe_text(list(base.apply_caveats) + list(live.apply_caveats))
    merged.sources = _dedupe_sources(base.sources, live.sources)
    merged.evidence = _dedupe_evidence(base.evidence, live.evidence)
    merged.confidence = live.confidence if live.confidence.band != "unresolved" else base.confidence
    merged.candidates = _dedupe_text(list(base.candidates) + list(live.candidates))
    merged.friction_signals = _dedupe_text(list(base.friction_signals) + list(live.friction_signals))
    merged.notes = _dedupe_text(list(base.notes) + list(live.notes))
    merged.debug_context = {**base.debug_context, **live.debug_context}
    if merged.canonical_application_url and merged.status == "unresolved":
        merged.status = "partial"
    if merged.canonical_application_url and merged.resolution_status == "unresolved":
        merged.resolution_status = "partial"
    if merged.canonical_application_url and not merged.resolution_note:
        merged.resolution_note = "Verified employer or ATS application entrypoint preserved as a partial result."
    return merged


class ApplicationSurfaceStage:
    name: str = "application_surface"
    dependencies: List[str] = ["jd_facts"]

    def run(self, ctx: StageContext) -> StageResult:
        application_surface = _deterministic_surface(ctx)
        provider_used = "none"
        model_used = None
        company = str(ctx.job_doc.get("company") or "").strip()
        company_domain = canonical_domain_from_url(
            ctx.job_doc.get("company_url") or (ctx.job_doc.get("company_research") or {}).get("url")
        )
        if web_research_enabled() and _should_attempt_live(application_surface):
            transport = CodexResearchTransport(ctx.config)
            if transport.is_live_configured():
                prompt = build_p_application_surface(
                    title=str(ctx.job_doc.get("title") or "").strip(),
                    company=company,
                    location=str(ctx.job_doc.get("location") or "").strip() or None,
                    job_url=application_surface.job_url,
                    ats_domains=[item for item in {company_domain} if item],
                    blocked_domains=list(AGGREGATOR_HOST_TOKENS),
                    transport_preamble=build_p_transport_preamble(
                        transport_used=transport.transport,
                        max_web_queries=ctx.config.max_web_queries,
                        max_fetches=ctx.config.max_fetches,
                        max_tool_turns=max(ctx.config.max_web_queries + ctx.config.max_fetches, 4),
                    ),
                )
                result = transport.invoke_json(
                    prompt=prompt,
                    job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "application-surface"),
                    validator=lambda payload: ApplicationSurfaceDoc.model_validate(normalize_application_surface_payload(payload)),
                    tracer=ctx.tracer,
                    stage_name=ctx.stage_name or "application_surface",
                    substage="live_lookup",
                )
                provider_used = result.provider_used
                model_used = result.model_used
                if result.success:
                    live_surface = result.payload if isinstance(result.payload, ApplicationSurfaceDoc) else ApplicationSurfaceDoc.model_validate(normalize_application_surface_payload(result.payload))
                    application_surface = _merge_surface(application_surface, live_surface, company, company_domain)
                else:
                    application_surface.notes = _dedupe_text(list(application_surface.notes) + [f"Live codex application research failed: {result.error or 'unknown error'}"])
                    application_surface.apply_caveats = _dedupe_text(list(application_surface.apply_caveats) + ["Canonical application URL remains unresolved because live Codex research did not return a valid verified URL."])
            else:
                application_surface.notes = _dedupe_text(list(application_surface.notes) + ["Live codex application research skipped because no codex research transport is configured."])

        output = {"application_url": application_surface.application_url or ctx.job_doc.get("application_url")}
        return StageResult(
            output=output,
            stage_output=application_surface.model_dump(),
            provider_used=provider_used,
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
        )
