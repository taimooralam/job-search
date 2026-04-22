"""Iteration-4.1.3 research_enrichment stage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
from typing import Any, Callable, List, TypeVar

from pydantic import BaseModel

from src.preenrich.blueprint_config import (
    current_git_sha,
    research_enable_outreach_guidance,
    research_enable_stakeholders,
    research_enrichment_v2_enabled,
    research_fallback_provider,
    research_fallback_transport,
    research_live_compat_write_enabled,
    research_prompt_file_path,
    research_provider,
    research_require_source_attribution,
    research_shadow_mode_enabled,
    research_transport,
    research_ui_snapshot_expanded_enabled,
    web_research_enabled,
)
from src.preenrich.blueprint_prompts import (
    build_p_research_application_merge,
    build_p_research_company,
    build_p_research_role,
    build_p_stakeholder_discovery,
    build_p_stakeholder_outreach_guidance,
    build_p_stakeholder_profile,
    build_p_transport_preamble,
)
from src.preenrich.blueprint_models import (
    ApplicationProfile,
    ApplicationSurfaceDoc,
    CompanyProfile,
    ConfidenceDoc,
    EvidenceEntry,
    GuidanceActionBullet,
    GuidanceAvoidBullet,
    GuidanceBullet,
    InitialOutreachGuidance,
    PromptMetadata,
    ResearchEnrichmentDoc,
    RoleProfile,
    SourceEntry,
    StakeholderRecord,
    normalize_application_surface_payload,
    normalize_company_profile_payload,
    normalize_role_profile_payload,
    normalize_stakeholder_record_payload,
)
from src.preenrich.research_transport import CodexResearchTransport
from src.preenrich.stages.blueprint_common import canonical_domain_from_url, company_slug, normalize_url
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "research_enrichment_bundle@v4.1.3.1"
RESEARCH_VERSION = "research_enrichment.v4.1.3.1"
logger = logging.getLogger(__name__)
TProfile = TypeVar("TProfile", bound=BaseModel)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dedupe_sources(*source_groups: list[dict[str, Any]]) -> list[SourceEntry]:
    deduped: dict[str, SourceEntry] = {}
    for group in source_groups:
        for item in group or []:
            try:
                source = item if isinstance(item, SourceEntry) else SourceEntry.model_validate(item)
            except Exception:
                continue
            deduped[source.source_id] = source
    return list(deduped.values())


def _dedupe_evidence(*evidence_groups: list[dict[str, Any]]) -> list[EvidenceEntry]:
    deduped: dict[tuple[str, tuple[str, ...]], EvidenceEntry] = {}
    for group in evidence_groups:
        for item in group or []:
            try:
                entry = item if isinstance(item, EvidenceEntry) else EvidenceEntry.model_validate(item)
            except Exception:
                continue
            key = (entry.claim, tuple(entry.source_ids))
            deduped[key] = entry
    return list(deduped.values())


def _band_from_score(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.2:
        return "low"
    return "unresolved"


def _prompt_metadata(ctx: StageContext) -> PromptMetadata:
    return PromptMetadata(
        prompt_id="research_enrichment_bundle",
        prompt_version=PROMPT_VERSION,
        prompt_file_path=research_prompt_file_path(),
        git_sha=current_git_sha(),
        provider=ctx.config.provider or research_provider(),
        model=ctx.config.primary_model,
        transport_used=ctx.config.transport or research_transport(),
        fallback_provider=ctx.config.fallback_provider or research_fallback_provider(),
        fallback_transport=ctx.config.fallback_transport or research_fallback_transport(),
    )


def _company_profile(ctx: StageContext, application_profile: ApplicationProfile) -> CompanyProfile:
    legacy = ctx.job_doc.get("company_research") or {}
    company_name = str(ctx.job_doc.get("company") or "").strip() or None
    company_url = normalize_url(
        ctx.job_doc.get("company_url") or legacy.get("url") or application_profile.canonical_application_url
    )
    canonical_domain = canonical_domain_from_url(company_url)
    now_iso = _now_iso()
    source = SourceEntry(
        source_id="s_company_legacy" if legacy else "s_company_job_doc",
        url=company_url,
        source_type="legacy_company_research" if legacy else "job_document",
        fetched_at=now_iso,
        trust_tier="primary" if company_url else "secondary",
        domain=canonical_domain,
        relevance="Canonical company identity and compat company research summary.",
    )
    signals = legacy.get("signals") or []
    summary = legacy.get("summary")
    identity_score = 0.82 if canonical_domain or company_url else 0.34 if company_name else 0.0
    identity_confidence = ConfidenceDoc(
        score=identity_score,
        band=_band_from_score(identity_score),
        basis="Company identity derived from job document and legacy company research compatibility fields.",
    )
    evidence = []
    if summary:
        evidence.append(
            EvidenceEntry(
                claim="Company summary is grounded in the existing company_research compatibility field.",
                source_ids=[source.source_id],
                basis="legacy_company_research",
            )
        )
    status = "completed" if summary or company_url else ("partial" if company_name else "unresolved")
    return CompanyProfile(
        summary=summary or (f"Public company context is limited for {company_name}." if company_name else None),
        url=company_url,
        signals=signals,
        canonical_name=company_name,
        canonical_domain=canonical_domain,
        canonical_url=company_url,
        identity_confidence=identity_confidence,
        identity_basis="job.company + company_research.url + application profile",
        company_type=legacy.get("company_type") or "unknown",
        mission_summary=legacy.get("summary"),
        product_summary=None if legacy.get("company_type") == "recruitment_agency" else legacy.get("summary"),
        business_model="agency" if legacy.get("company_type") == "recruitment_agency" else "unknown",
        recent_signals=signals,
        role_relevant_signals=signals[:3],
        sources=[source],
        evidence=evidence,
        confidence=identity_confidence,
        status=status,
    )


def _role_profile(ctx: StageContext, company_profile: CompanyProfile) -> RoleProfile:
    legacy = ctx.job_doc.get("role_research") or {}
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    classification = outputs.get("classification") or {}
    title = str(jd_facts.get("title") or ctx.job_doc.get("title") or "").strip()
    summary = legacy.get("summary") or (f"{title} role with public context pending." if title else None)
    why_now = legacy.get("why_now") or (
        "Hiring urgency appears tied to the role mandate described in the JD."
        if title and company_profile.status != "unresolved"
        else None
    )
    success_metrics = list(legacy.get("business_impact") or jd_facts.get("success_metrics") or [])[:5]
    interview_themes = list(jd_facts.get("top_keywords") or [])[:5]
    source = SourceEntry(
        source_id="s_role_legacy" if legacy else "s_role_jd",
        url=company_profile.canonical_url,
        source_type="legacy_role_research" if legacy else "jd_facts",
        fetched_at=_now_iso(),
        trust_tier="secondary" if legacy else "primary",
        domain=company_profile.canonical_domain,
        relevance="Role summary, why-now context, and JD-derived success metrics.",
    )
    score = 0.78 if legacy else 0.56 if title else 0.0
    confidence = ConfidenceDoc(
        score=score,
        band=_band_from_score(score),
        basis="Role profile merged from legacy role research plus JD/classification signals.",
    )
    evidence = [
        EvidenceEntry(
            claim="Role profile is based on the existing role_research projection and current jd_facts payload.",
            source_ids=[source.source_id],
            basis="legacy_role_research+jd_facts",
        )
    ]
    status = "completed" if legacy else ("partial" if title else "unresolved")
    return RoleProfile(
        summary=summary,
        role_summary=summary,
        mandate=list(jd_facts.get("responsibilities") or [])[:5],
        business_impact=list(legacy.get("business_impact") or jd_facts.get("success_metrics") or [])[:5],
        why_now=why_now,
        success_metrics=success_metrics,
        collaboration_map=[],
        reporting_line={
            "manager_title": "unknown",
            "skip_level_title": "unknown",
            "source_ids": [source.source_id],
        },
        org_placement={
            "function_area": classification.get("primary_role_category") or "unknown",
            "sub_org": "unknown",
            "team_size_band": "unknown",
        },
        interview_themes=interview_themes,
        evaluation_signals=interview_themes[:4],
        risk_landscape=[],
        company_context_alignment=company_profile.summary,
        sources=[source],
        evidence=evidence,
        confidence=confidence,
        status=status,
    )


def _application_profile(ctx: StageContext, company_profile: CompanyProfile) -> ApplicationProfile:
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    app_surface_payload = outputs.get("application_surface") or {}
    surface = ApplicationSurfaceDoc.model_validate(normalize_application_surface_payload(app_surface_payload or {"status": "unresolved"}))
    application = ApplicationProfile.model_validate(surface.model_dump())
    if application.application_url and company_profile.canonical_domain:
        host = canonical_domain_from_url(application.application_url)
        if host and company_profile.canonical_domain not in host and application.portal_family in {"unknown", "custom_unknown", None}:
            application.canonical_application_url = None
            application.application_url = None
            application.resolution_status = "unresolved"
            application.status = "unresolved"
            application.ui_actionability = "blocked"
            application.apply_caveats.append("Rejected a cross-company application URL candidate.")
            application.confidence = ConfidenceDoc(
                score=0.0,
                band="unresolved",
                basis="Application candidate host did not match the canonical company domain or a known ATS family.",
            )
    return application


def _seed_company_profile(ctx: StageContext, application_profile: ApplicationProfile) -> CompanyProfile:
    company_name = str(ctx.job_doc.get("company") or "").strip() or None
    company_url = normalize_url(ctx.job_doc.get("company_url"))
    canonical_domain = canonical_domain_from_url(company_url) or canonical_domain_from_url(application_profile.canonical_application_url)
    source = SourceEntry(
        source_id="s_company_job_doc_v2",
        url=company_url,
        source_type="job_document",
        fetched_at=_now_iso(),
        trust_tier="primary" if company_url else "secondary",
        domain=canonical_domain,
        relevance="Job-supplied company identity hint for live Codex research.",
    )
    score = 0.55 if company_url else 0.32 if company_name else 0.0
    confidence = ConfidenceDoc(
        score=score,
        band=_band_from_score(score),
        basis="Seed company identity came from the job document and application surface only.",
    )
    evidence = []
    if company_name:
        evidence.append(
            EvidenceEntry(
                claim="Company identity seed was taken from the job document.",
                source_ids=[source.source_id],
                basis="job_document",
            )
        )
    return CompanyProfile(
        summary=f"Public company context for {company_name} is pending live verification." if company_name else None,
        canonical_name=company_name,
        canonical_domain=canonical_domain,
        canonical_url=company_url,
        url=company_url,
        identity_confidence=confidence,
        identity_basis="job.company + job.company_url + application_profile",
        sources=[source],
        evidence=evidence,
        confidence=confidence,
        status="partial" if company_name else "unresolved",
    )


def _seed_role_profile(ctx: StageContext, company_profile: CompanyProfile) -> RoleProfile:
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    classification = outputs.get("classification") or {}
    title = str(jd_facts.get("title") or ctx.job_doc.get("title") or "").strip()
    source = SourceEntry(
        source_id="s_role_seed_v2",
        url=company_profile.canonical_url or company_profile.url,
        source_type="jd_facts",
        fetched_at=_now_iso(),
        trust_tier="primary",
        domain=company_profile.canonical_domain,
        relevance="JD and classification seeds for live Codex role research.",
    )
    confidence = ConfidenceDoc(
        score=0.5 if title else 0.0,
        band=_band_from_score(0.5 if title else 0.0),
        basis="Seed role profile came from jd_facts and classification only.",
    )
    return RoleProfile(
        summary=f"{title} role with public validation pending." if title else None,
        mandate=list(jd_facts.get("responsibilities") or [])[:5],
        success_metrics=list(jd_facts.get("success_metrics") or [])[:5],
        interview_themes=list(jd_facts.get("top_keywords") or [])[:5],
        org_placement={"function_area": classification.get("primary_role_category") or "unknown"},
        sources=[source],
        evidence=[
            EvidenceEntry(
                claim="Seed role profile was derived from jd_facts and classification.",
                source_ids=[source.source_id],
                basis="jd_facts+classification",
            )
        ] if title else [],
        confidence=confidence,
        status="partial" if title else "unresolved",
    )


def _jd_excerpt(ctx: StageContext, *, limit: int = 3000) -> str:
    description = str(ctx.job_doc.get("description") or "").strip()
    if description:
        return description[:limit]
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    fragments = [
        str(jd_facts.get("title") or "").strip(),
        "\n".join(list(jd_facts.get("responsibilities") or [])[:6]),
        "\n".join(list(jd_facts.get("qualifications") or [])[:6]),
        "\n".join(list(jd_facts.get("top_keywords") or [])[:10]),
    ]
    return "\n".join(fragment for fragment in fragments if fragment)[:limit]


def _transport_preamble(ctx: StageContext, transport: CodexResearchTransport) -> str:
    return build_p_transport_preamble(
        transport_used=transport.transport,
        max_web_queries=ctx.config.max_web_queries,
        max_fetches=ctx.config.max_fetches,
        max_tool_turns=max(ctx.config.max_web_queries + ctx.config.max_fetches, 4),
    )


def _payload_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(payload.keys())
    return []


def _attempt_fail_open_profile(
    *,
    payload: Any,
    normalizer: Callable[[dict[str, Any] | None], dict[str, Any]],
    model_cls: type[TProfile],
    fallback_status: str = "partial",
) -> TProfile | None:
    if isinstance(payload, model_cls):
        return payload
    if not isinstance(payload, dict):
        return None
    normalized = normalizer(payload)
    if not normalized.get("status"):
        normalized["status"] = fallback_status
    elif str(normalized.get("status")).strip().lower() == "completed" and not normalized.get("summary"):
        normalized["status"] = fallback_status
    return model_cls.model_validate(normalized)


def _live_company_profile(
    ctx: StageContext,
    transport: CodexResearchTransport,
    application_profile: ApplicationProfile,
) -> tuple[CompanyProfile, list[str]]:
    seed = _seed_company_profile(ctx, application_profile)
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    classification = outputs.get("classification") or {}
    company = seed.canonical_name or str(ctx.job_doc.get("company") or "").strip()
    prompt = build_p_research_company(
        company=company,
        name_variations=[item for item in {company, company.replace(" Ltd", "").replace(" LLC", ""), company.replace(" Limited", "")} if item],
        company_url=seed.canonical_url,
        candidate_domains=[item for item in {seed.canonical_domain, canonical_domain_from_url(application_profile.canonical_application_url)} if item],
        jd_excerpt=_jd_excerpt(ctx, limit=2000),
        classification=classification,
        application_profile=application_profile.model_dump(),
        transport_preamble=_transport_preamble(ctx, transport),
    )
    result = transport.invoke_json(
        prompt=prompt,
        job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "research-company"),
        validator=lambda payload: CompanyProfile.model_validate(normalize_company_profile_payload(payload)),
    )
    logger.info(
        "research_enrichment company transport result: success=%s error=%s payload_type=%s payload_keys=%s",
        result.success,
        result.error,
        type(result.payload).__name__ if result.payload is not None else None,
        _payload_keys(result.payload),
    )
    if not result.success:
        if isinstance(result.payload, dict):
            try:
                profile = _attempt_fail_open_profile(
                    payload=result.payload,
                    normalizer=normalize_company_profile_payload,
                    model_cls=CompanyProfile,
                )
                if profile is not None:
                    logger.warning(
                        "research_enrichment company fail-open accepted live payload after schema drift: status=%s canonical_name=%s canonical_domain=%s",
                        profile.status,
                        profile.canonical_name,
                        profile.canonical_domain,
                    )
                    return profile, [f"Live Codex company research recovered via fail-open normalization after schema drift: {result.error or 'unknown error'}"]
            except Exception:
                logger.exception("research_enrichment company fail-open normalization failed")
        logger.warning(
            "research_enrichment company fallback to seed: reason=%s seed_status=%s seed_canonical_name=%s",
            result.error or "unknown error",
            seed.status,
            seed.canonical_name,
        )
        return seed, [f"Live Codex company research failed: {result.error or 'unknown error'}"]
    try:
        profile = result.payload if isinstance(result.payload, CompanyProfile) else CompanyProfile.model_validate(normalize_company_profile_payload(result.payload))
    except Exception as exc:
        logger.exception("research_enrichment company validation fallback to seed")
        return seed, [f"Live Codex company research validation failed: {exc}"]
    if not profile.status:
        profile.status = "completed" if profile.summary else "partial"
    logger.info(
        "research_enrichment company accepted live profile: status=%s canonical_name=%s canonical_domain=%s sources=%d evidence=%d signals=%d signals_rich=%d",
        profile.status,
        profile.canonical_name,
        profile.canonical_domain,
        len(profile.sources or []),
        len(profile.evidence or []),
        len(profile.signals or []),
        len(profile.signals_rich or []),
    )
    return profile, []


def _live_role_profile(
    ctx: StageContext,
    transport: CodexResearchTransport,
    company_profile: CompanyProfile,
    application_profile: ApplicationProfile,
) -> tuple[RoleProfile, list[str]]:
    seed = _seed_role_profile(ctx, company_profile)
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    prompt = build_p_research_role(
        title=str(ctx.job_doc.get("title") or "").strip(),
        company=str(ctx.job_doc.get("company") or "").strip(),
        jd_text=_jd_excerpt(ctx),
        jd_facts=((outputs.get("jd_facts") or {}).get("merged_view") or {}),
        classification=outputs.get("classification") or {},
        company_profile=company_profile.model_dump(),
        application_profile=application_profile.model_dump(),
        transport_preamble=_transport_preamble(ctx, transport),
    )
    result = transport.invoke_json(
        prompt=prompt,
        job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "research-role"),
        validator=lambda payload: RoleProfile.model_validate(normalize_role_profile_payload(payload)),
    )
    logger.info(
        "research_enrichment role transport result: success=%s error=%s payload_type=%s payload_keys=%s",
        result.success,
        result.error,
        type(result.payload).__name__ if result.payload is not None else None,
        _payload_keys(result.payload),
    )
    if not result.success:
        if isinstance(result.payload, dict):
            try:
                profile = _attempt_fail_open_profile(
                    payload=result.payload,
                    normalizer=normalize_role_profile_payload,
                    model_cls=RoleProfile,
                )
                if profile is not None:
                    logger.warning(
                        "research_enrichment role fail-open accepted live payload after schema drift: status=%s summary=%s",
                        profile.status,
                        profile.summary,
                    )
                    return profile, [f"Live Codex role research recovered via fail-open normalization after schema drift: {result.error or 'unknown error'}"]
            except Exception:
                logger.exception("research_enrichment role fail-open normalization failed")
        logger.warning(
            "research_enrichment role fallback to seed: reason=%s seed_status=%s seed_summary=%s",
            result.error or "unknown error",
            seed.status,
            seed.summary,
        )
        return seed, [f"Live Codex role research failed: {result.error or 'unknown error'}"]
    try:
        profile = result.payload if isinstance(result.payload, RoleProfile) else RoleProfile.model_validate(normalize_role_profile_payload(result.payload))
    except Exception as exc:
        logger.exception("research_enrichment role validation fallback to seed")
        return seed, [f"Live Codex role research validation failed: {exc}"]
    if not profile.status:
        profile.status = "completed" if profile.summary else "partial"
    logger.info(
        "research_enrichment role accepted live profile: status=%s summary=%s sources=%d evidence=%d mandate=%d success_metrics=%d collaboration_map=%d",
        profile.status,
        profile.summary,
        len(profile.sources or []),
        len(profile.evidence or []),
        len(profile.mandate or []),
        len(profile.success_metrics or []),
        len(profile.collaboration_map or []),
    )
    return profile, []


def _merge_application_profile_live(
    ctx: StageContext,
    transport: CodexResearchTransport,
    company_profile: CompanyProfile,
    base_application_profile: ApplicationProfile,
) -> tuple[ApplicationProfile, list[str]]:
    prompt = build_p_research_application_merge(
        application_surface_artifact=base_application_profile.model_dump(),
        job_document_hints={
            "job_url": ctx.job_doc.get("jobUrl") or ctx.job_doc.get("url"),
            "application_url": ctx.job_doc.get("application_url"),
            "company": ctx.job_doc.get("company"),
            "title": ctx.job_doc.get("title"),
        },
        canonical_domain=company_profile.canonical_domain,
    )
    result = transport.invoke_json(
        prompt=prompt,
        job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "research-application-merge"),
        validator=lambda payload: ApplicationProfile.model_validate(normalize_application_surface_payload(payload)),
    )
    logger.info(
        "research_enrichment application merge transport result: success=%s error=%s payload_type=%s payload_keys=%s",
        result.success,
        result.error,
        type(result.payload).__name__ if result.payload is not None else None,
        _payload_keys(result.payload),
    )
    if not result.success:
        if isinstance(result.payload, dict):
            try:
                profile = _attempt_fail_open_profile(
                    payload=result.payload,
                    normalizer=normalize_application_surface_payload,
                    model_cls=ApplicationProfile,
                )
                if profile is not None:
                    logger.warning(
                        "research_enrichment application merge fail-open accepted live payload after schema drift: status=%s resolution_status=%s canonical_application_url=%s",
                        profile.status,
                        profile.resolution_status,
                        profile.canonical_application_url,
                    )
                    return profile, [f"Codex application merge recovered via fail-open normalization after schema drift: {result.error or 'unknown error'}"]
            except Exception:
                logger.exception("research_enrichment application merge fail-open normalization failed")
        logger.warning(
            "research_enrichment application merge fallback to base: reason=%s base_status=%s base_resolution_status=%s",
            result.error or "unknown error",
            base_application_profile.status,
            base_application_profile.resolution_status,
        )
        return base_application_profile, [f"Codex application merge failed: {result.error or 'unknown error'}"]
    try:
        profile = result.payload if isinstance(result.payload, ApplicationProfile) else ApplicationProfile.model_validate(normalize_application_surface_payload(result.payload))
    except Exception as exc:
        logger.exception("research_enrichment application merge validation fallback to base")
        return base_application_profile, [f"Codex application merge validation failed: {exc}"]
    if profile.canonical_application_url:
        host = canonical_domain_from_url(profile.canonical_application_url)
        if host and company_profile.canonical_domain and company_profile.canonical_domain not in host and profile.portal_family in {"unknown", "custom_unknown", None}:
            logger.warning(
                "research_enrichment application merge rejected cross-company URL: candidate=%s canonical_domain=%s",
                profile.canonical_application_url,
                company_profile.canonical_domain,
            )
            return base_application_profile, ["Codex application merge proposed a cross-company URL and it was rejected."]
    if not profile.sources:
        profile.sources = list(base_application_profile.sources)
    if not profile.evidence:
        profile.evidence = list(base_application_profile.evidence)
    if profile.confidence.band == "unresolved":
        profile.confidence = base_application_profile.confidence
    logger.info(
        "research_enrichment application merge accepted live profile: status=%s resolution_status=%s canonical_application_url=%s sources=%d evidence=%d",
        profile.status,
        profile.resolution_status,
        profile.canonical_application_url,
        len(profile.sources or []),
        len(profile.evidence or []),
    )
    return profile, []


def _validate_stakeholder_payload(payload: dict[str, Any]) -> list[StakeholderRecord]:
    raw_records = payload.get("stakeholder_intelligence") or []
    if not isinstance(raw_records, list):
        raise ValueError("stakeholder_intelligence must be a list")
    return [StakeholderRecord.model_validate(normalize_stakeholder_record_payload(item)) for item in raw_records]


def _live_stakeholder_records(
    ctx: StageContext,
    transport: CodexResearchTransport,
    company_profile: CompanyProfile,
    role_profile: RoleProfile,
    application_profile: ApplicationProfile,
) -> tuple[list[StakeholderRecord], list[str]]:
    if not research_enable_stakeholders():
        return [], []
    prompt = build_p_stakeholder_discovery(
        title=str(ctx.job_doc.get("title") or "").strip(),
        company=str(ctx.job_doc.get("company") or "").strip(),
        company_profile=company_profile.model_dump(),
        role_profile=role_profile.model_dump(),
        application_profile=application_profile.model_dump(),
        jd_excerpt=_jd_excerpt(ctx, limit=1500),
        transport_preamble=_transport_preamble(ctx, transport),
    )
    result = transport.invoke_json(
        prompt=prompt,
        job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "research-stakeholders"),
        validator=_validate_stakeholder_payload,
    )
    if not result.success:
        return [], [f"Live Codex stakeholder discovery failed: {result.error or 'unknown error'}"]
    records = list(result.payload or [])
    if not records:
        return [], ["No stakeholder candidate cleared the 4.1.3 identity ladder."]
    return records, []


def _enrich_stakeholder_records(
    ctx: StageContext,
    transport: CodexResearchTransport,
    stakeholders: list[StakeholderRecord],
    company_profile: CompanyProfile,
    role_profile: RoleProfile,
    application_profile: ApplicationProfile,
) -> tuple[list[StakeholderRecord], list[str]]:
    if not stakeholders:
        return [], []
    enriched: list[StakeholderRecord] = []
    notes: list[str] = []
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    for stakeholder in stakeholders:
        record = stakeholder.model_copy(deep=True)
        if record.identity_confidence.band not in {"medium", "high"}:
            record.initial_outreach_guidance = None
            enriched.append(record)
            continue
        profile_prompt = build_p_stakeholder_profile(
            stakeholder_record=record.model_dump(),
            role_profile=role_profile.model_dump(),
            company_profile=company_profile.model_dump(),
            public_posts_fetched=[],
            transport_preamble=_transport_preamble(ctx, transport),
        )
        profile_result = transport.invoke_json(
            prompt=profile_prompt,
            job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "research-stakeholder-profile"),
        )
        if profile_result.success and isinstance(profile_result.payload, dict):
            payload = normalize_stakeholder_record_payload(profile_result.payload)
            record.public_professional_background = payload.get("public_professional_background") or record.public_professional_background
            record.public_communication_signals = payload.get("public_communication_signals") or record.public_communication_signals
            record.working_style_signals = payload.get("working_style_signals") or record.working_style_signals
            if payload.get("likely_priorities"):
                record.likely_priorities = [GuidanceBullet.model_validate(item) for item in payload.get("likely_priorities") or []]
            if payload.get("relationship_to_role"):
                record.relationship_to_role = payload.get("relationship_to_role")
            if payload.get("evidence_basis"):
                record.evidence_basis = payload.get("evidence_basis")
            if payload.get("confidence"):
                record.confidence = ConfidenceDoc.model_validate(payload.get("confidence"))
            record.unresolved_markers = list(payload.get("unresolved_markers") or record.unresolved_markers)
            record.sources = _dedupe_sources(record.sources, payload.get("sources") or [])
            record.evidence = _dedupe_evidence(record.evidence, payload.get("evidence") or [])
        else:
            notes.append(f"Stakeholder profile enrichment failed for rank={record.candidate_rank}: {profile_result.error or 'unknown error'}")

        if research_enable_outreach_guidance():
            guidance_prompt = build_p_stakeholder_outreach_guidance(
                stakeholder_record=record.model_dump(),
                stakeholder_profile=record.model_dump(),
                role_profile=role_profile.model_dump(),
                company_profile=company_profile.model_dump(),
                jd_facts=jd_facts,
            )
            guidance_result = transport.invoke_json(
                prompt=guidance_prompt,
                job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "research-stakeholder-guidance"),
            )
            if guidance_result.success and isinstance(guidance_result.payload, dict):
                payload = normalize_stakeholder_record_payload(guidance_result.payload)
                guidance_payload = payload.get("initial_outreach_guidance") or {}
                if guidance_payload:
                    record.initial_outreach_guidance = InitialOutreachGuidance.model_validate(guidance_payload)
                if payload.get("likely_priorities"):
                    record.likely_priorities = [GuidanceBullet.model_validate(item) for item in payload.get("likely_priorities") or []]
                if payload.get("avoid_points"):
                    record.avoid_points = [GuidanceAvoidBullet.model_validate(item) for item in payload.get("avoid_points") or []]
                if payload.get("evidence_basis"):
                    record.evidence_basis = payload.get("evidence_basis")
                if payload.get("confidence"):
                    record.confidence = ConfidenceDoc.model_validate(payload.get("confidence"))
            else:
                notes.append(f"Stakeholder outreach guidance failed for rank={record.candidate_rank}: {guidance_result.error or 'unknown error'}")
                record.initial_outreach_guidance = None
        enriched.append(StakeholderRecord.model_validate(record.model_dump()))
    return enriched, notes


def _stakeholder_type(title: str) -> str:
    lowered = title.lower()
    if any(token in lowered for token in ("recruiter", "talent acquisition", "talent partner", "sourcer")):
        return "recruiter"
    if any(token in lowered for token in ("vp", "chief", "cxo", "cto", "head of")):
        return "executive_sponsor"
    if "manager" in lowered or "director" in lowered:
        return "hiring_manager"
    if title:
        return "peer_technical"
    return "unknown"


def _stakeholder_records(ctx: StageContext, company_profile: CompanyProfile, role_profile: RoleProfile) -> tuple[list[StakeholderRecord], list[str]]:
    if not research_enable_stakeholders():
        return [], []

    contacts = []
    contacts.extend(list(ctx.job_doc.get("primary_contacts") or []))
    contacts.extend(list(ctx.job_doc.get("secondary_contacts") or []))
    stakeholders: list[StakeholderRecord] = []
    unresolved: list[str] = []
    if not contacts:
        unresolved.append("No existing public-professional contact candidates were available to map into stakeholder_intelligence.")
        return [], unresolved

    for index, contact in enumerate(contacts, start=1):
        if not isinstance(contact, dict):
            continue
        name = str(contact.get("name") or "").strip() or None
        title = str(contact.get("role") or contact.get("title") or "").strip()
        profile_url = normalize_url(contact.get("linkedin_url") or contact.get("profile_url"))
        matched_signal_classes = []
        if company_profile.canonical_name and str(contact.get("company") or company_profile.canonical_name).strip():
            matched_signal_classes.append("public_profile_company_match")
        if title:
            matched_signal_classes.append("public_profile_function_match")
        if profile_url:
            matched_signal_classes.append("job_or_application_url")
        score = 0.62 if len(set(matched_signal_classes)) >= 2 and name and title else 0.35 if name else 0.0
        band = _band_from_score(score)
        confidence = ConfidenceDoc(
            score=score,
            band=band,
            basis="Stakeholder candidate mapped from existing public contact projections without private contact enrichment.",
        )
        source_id = f"s_stakeholder_{index}"
        source = SourceEntry(
            source_id=source_id,
            url=profile_url,
            source_type="public_professional_profile" if profile_url else "legacy_contact_projection",
            fetched_at=_now_iso(),
            trust_tier="secondary" if profile_url else "tertiary",
            relevance="Existing public-professional contact candidate carried into research_enrichment.",
        )
        stakeholder_type = _stakeholder_type(title)
        guidance = None
        if research_enable_outreach_guidance() and band in {"medium", "high"}:
            priorities = [
                GuidanceBullet(
                    bullet=(str(contact.get("why_relevant") or "").strip() or "Role-fit clarity and practical execution signal.")[:180],
                    basis="public_posts" if profile_url else "multi",
                    source_ids=[source_id],
                )
            ]
            priorities.extend(
                GuidanceBullet(bullet=item, basis="role", source_ids=[source_id])
                for item in role_profile.business_impact[:2]
            )
            guidance = InitialOutreachGuidance(
                what_they_likely_care_about=priorities[:3],
                initial_cold_interaction_guidance=[
                    GuidanceActionBullet(
                        bullet="Open with role-relevant evidence and keep the ask lightweight.",
                        dimension="opening_angle",
                        source_ids=[source_id],
                    ),
                    GuidanceActionBullet(
                        bullet="Use one concrete execution signal tied to the mandate instead of generic enthusiasm.",
                        dimension="value_signal",
                        source_ids=[source_id],
                    ),
                ],
                avoid_in_initial_contact=[
                    GuidanceAvoidBullet(
                        bullet="Do not claim familiarity beyond public-professional context.",
                        reason="anti_speculation",
                        source_ids=[source_id],
                    )
                ],
                confidence_and_basis=confidence,
            )
        record = StakeholderRecord(
            stakeholder_type=stakeholder_type,
            identity_status="resolved" if band in {"medium", "high"} else "ambiguous" if name else "unresolved",
            identity_confidence=confidence,
            identity_basis=str(contact.get("why_relevant") or "Mapped from public-professional contact projection."),
            matched_signal_classes=matched_signal_classes,
            candidate_rank=index,
            name=name,
            current_title=title or None,
            current_company=str(contact.get("company") or company_profile.canonical_name or "").strip() or company_profile.canonical_name,
            profile_url=profile_url,
            source_trail=[source_id],
            function="recruiting" if stakeholder_type == "recruiter" else "engineering",
            seniority="manager" if "manager" in title.lower() else "unknown",
            relationship_to_role="recruiter" if stakeholder_type == "recruiter" else "unknown",
            likely_influence="strong_input" if band in {"medium", "high"} else "informational",
            public_professional_background={"career_arc": str(contact.get("why_relevant") or "")[:240], "source_ids": [source_id]},
            public_communication_signals={"topics_they_post_about": [], "tone": "unknown", "cadence": "unknown", "source_ids": [source_id]},
            working_style_signals=[],
            initial_outreach_guidance=guidance,
            unresolved_markers=[] if band in {"medium", "high"} else ["identity_below_threshold"],
            sources=[source],
            evidence=[
                EvidenceEntry(
                    claim="Stakeholder candidate was mapped from an existing public-professional contact projection.",
                    source_ids=[source_id],
                    basis="legacy_contact_projection",
                )
            ],
            confidence=guidance.confidence_and_basis if guidance else confidence,
        )
        stakeholders.append(record)
    qualified = [record for record in stakeholders if record.identity_confidence.band in {"medium", "high"}]
    if not qualified:
        unresolved.append("No stakeholder candidate cleared medium confidence under the identity ladder rules.")
        return [], unresolved
    return stakeholders, unresolved


class ResearchEnrichmentStage:
    name: str = "research_enrichment"
    dependencies: List[str] = ["jd_facts", "classification", "application_surface"]

    def run(self, ctx: StageContext) -> StageResult:
        v2_enabled = research_enrichment_v2_enabled()
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        application_profile = _application_profile(ctx, CompanyProfile())

        if not v2_enabled:
            company_profile = _company_profile(ctx, application_profile)
            legacy_company = ctx.job_doc.get("company_research") or {}
            legacy_authoritative_status = "completed" if legacy_company else ("no_research" if not web_research_enabled() else company_profile.status)
            artifact = ResearchEnrichmentDoc(
                job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
                level2_job_id=str(ctx.job_doc.get("_id")),
                jd_facts_id="__ref__:jd_facts.id",
                classification_id="__ref__:classification.id",
                application_surface_id="__ref__:application_surface.id",
                input_snapshot_id=ctx.input_snapshot_id,
                research_input_hash=f"{ctx.input_snapshot_id}:legacy:{PROMPT_VERSION}",
                prompt_version=PROMPT_VERSION,
                prompt_metadata=_prompt_metadata(ctx),
                provider_used=ctx.config.provider,
                model_used=ctx.config.primary_model,
                transport_used=ctx.config.transport or research_transport(),
                status=legacy_authoritative_status,
                capability_flags={
                    "research_v2_enabled": False,
                    "research_shadow_mode_enabled": research_shadow_mode_enabled(),
                    "research_live_compat_write_enabled": research_live_compat_write_enabled(),
                    "research_ui_snapshot_expanded_enabled": research_ui_snapshot_expanded_enabled(),
                    "research_require_source_attribution": research_require_source_attribution(),
                    "web_research_enabled": web_research_enabled(),
                },
                company_profile=company_profile,
                role_profile=RoleProfile(),
                application_profile=application_profile,
                sources=company_profile.sources,
                evidence=company_profile.evidence,
                confidence=company_profile.confidence,
                notes=["Research V2 disabled; legacy 4.1 projections remain authoritative."],
                unresolved_questions=[],
            )
            return StageResult(
                stage_output=artifact.model_dump(),
                artifact_writes=[
                    ArtifactWrite(
                        collection="research_enrichment",
                        unique_filter={
                            "job_id": artifact.job_id,
                            "input_snapshot_id": artifact.input_snapshot_id,
                            "research_version": artifact.research_version,
                        },
                        document=artifact.model_dump(),
                        ref_name="research_enrichment",
                    )
                ],
                provider_used=ctx.config.provider,
                model_used=ctx.config.primary_model,
                prompt_version=PROMPT_VERSION,
            )

        transport = CodexResearchTransport(ctx.config)
        live_notes: list[str] = []
        company_profile = _seed_company_profile(ctx, application_profile)
        role_profile = _seed_role_profile(ctx, company_profile)
        if web_research_enabled() and transport.is_live_configured():
            seed_company_profile = company_profile
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="research_enrichment") as executor:
                company_future = executor.submit(_live_company_profile, ctx, transport, application_profile)
                role_future = executor.submit(
                    _live_role_profile,
                    ctx,
                    transport,
                    seed_company_profile,
                    application_profile,
                )
                company_profile, company_notes = company_future.result()
                role_profile, role_notes = role_future.result()
            logger.info(
                "research_enrichment parallel live subpasses complete: company_status=%s company_domain=%s role_status=%s role_summary=%s company_notes=%s role_notes=%s",
                company_profile.status,
                company_profile.canonical_domain,
                role_profile.status,
                role_profile.summary,
                company_notes,
                role_notes,
            )
            live_notes.extend(company_notes)
            application_profile = _application_profile(ctx, company_profile)
            application_profile, application_notes = _merge_application_profile_live(
                ctx,
                transport,
                company_profile,
                application_profile,
            )
            logger.info(
                "research_enrichment post-merge assembly state: company_status=%s role_status=%s application_status=%s application_resolution_status=%s application_notes=%s",
                company_profile.status,
                role_profile.status,
                application_profile.status,
                application_profile.resolution_status,
                application_notes,
            )
            live_notes.extend(application_notes)
            live_notes.extend(role_notes)
            stakeholders, stakeholder_notes = _live_stakeholder_records(
                ctx,
                transport,
                company_profile,
                role_profile,
                application_profile,
            )
            live_notes.extend(stakeholder_notes)
            stakeholders, enrichment_notes = _enrich_stakeholder_records(
                ctx,
                transport,
                stakeholders,
                company_profile,
                role_profile,
                application_profile,
            )
            live_notes.extend(enrichment_notes)
        else:
            stakeholders = []
            stakeholder_notes = []

        capability_flags = {
            "research_v2_enabled": True,
            "research_shadow_mode_enabled": research_shadow_mode_enabled(),
            "research_live_compat_write_enabled": research_live_compat_write_enabled(),
            "research_ui_snapshot_expanded_enabled": research_ui_snapshot_expanded_enabled(),
            "research_enable_stakeholders": research_enable_stakeholders(),
            "research_enable_outreach_guidance": research_enable_outreach_guidance(),
            "research_require_source_attribution": research_require_source_attribution(),
            "web_research_enabled": web_research_enabled(),
            "transport_configured": transport.is_live_configured(),
            "codex_only_transport": transport.is_live_configured(),
        }

        unresolved_questions: list[str] = []
        if company_profile.status == "unresolved":
            unresolved_questions.append("Canonical company identity remains unresolved.")
        if role_profile.status == "unresolved":
            unresolved_questions.append("Role profile remained unresolved beyond JD-derived fields.")
        if application_profile.resolution_status not in {"resolved", "partial"}:
            unresolved_questions.append("Canonical application URL remains unresolved.")
        unresolved_questions.extend(stakeholder_notes)
        unresolved_questions.extend(live_notes)
        if not capability_flags["transport_configured"] or not web_research_enabled():
            unresolved_questions.append("Live web transport unavailable; artifact was built from deterministic seeds and application-surface inputs only.")

        company_role_statuses = {company_profile.status, role_profile.status}
        gating_statuses = {company_profile.status, role_profile.status, application_profile.status}
        if "unresolved" in company_role_statuses:
            overall_status = "unresolved"
        elif application_profile.status == "unresolved":
            overall_status = "partial"
        elif "partial" in gating_statuses:
            overall_status = "partial"
        elif not web_research_enabled():
            overall_status = "no_research"
        else:
            overall_status = "completed"

        score = (
            company_profile.confidence.score
            + role_profile.confidence.score
            + application_profile.confidence.score
        ) / 3.0
        overall_confidence = ConfidenceDoc(
            score=score,
            band=_band_from_score(score),
            basis="Aggregate confidence across company, role, and application subdocuments.",
            unresolved_items=unresolved_questions,
        )
        company_domain = company_profile.canonical_domain or canonical_domain_from_url(company_profile.canonical_url)
        transport_version = f"{ctx.config.provider}:{ctx.config.primary_model}:{ctx.config.transport or research_transport()}"
        company_cache_key = f"{company_domain or company_slug(company_profile.canonical_name)}|{transport_version}|{PROMPT_VERSION}"
        application_cache_key = (
            f"{application_profile.canonical_application_url or application_profile.job_url or 'unknown'}|{transport_version}|{PROMPT_VERSION}"
        )
        cache_refs = {
            "company_cache_key": company_cache_key,
            "application_cache_key": application_cache_key,
            "stakeholder_cache_keys": [
                f"{company_domain or company_slug(company_profile.canonical_name)}|{record.profile_url or record.name or record.candidate_rank}|{transport_version}|{PROMPT_VERSION}"
                for record in stakeholders
            ],
        }

        sources = _dedupe_sources(
            company_profile.sources,
            role_profile.sources,
            application_profile.sources,
            *[record.sources for record in stakeholders],
        )
        evidence = _dedupe_evidence(
            company_profile.evidence,
            role_profile.evidence,
            application_profile.evidence,
            *[record.evidence for record in stakeholders],
        )
        artifact = ResearchEnrichmentDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_facts_id="__ref__:jd_facts.id",
            classification_id="__ref__:classification.id",
            application_surface_id="__ref__:application_surface.id",
            input_snapshot_id=ctx.input_snapshot_id,
            research_version=RESEARCH_VERSION,
            research_input_hash=f"{ctx.input_snapshot_id}:{transport_version}:{PROMPT_VERSION}",
            prompt_version=PROMPT_VERSION,
            prompt_metadata=_prompt_metadata(ctx),
            provider_used=ctx.config.provider or research_provider(),
            model_used=ctx.config.primary_model,
            transport_used=ctx.config.transport or research_transport(),
            status=overall_status,
            capability_flags=capability_flags,
            company_profile=company_profile,
            role_profile=role_profile,
            application_profile=application_profile,
            stakeholder_intelligence=stakeholders,
            sources=sources,
            evidence=evidence,
            confidence=overall_confidence,
            notes=[
                "research_enrichment is the canonical external-intelligence artifact for 4.1.3.",
                "application_surface remains a separate execution stage and is merged into application_profile.",
                "Live company, role, and stakeholder research is Codex-only in the V2 path.",
            ],
            unresolved_questions=unresolved_questions,
            cache_refs=cache_refs,
            timing={"generated_at": _now_iso()},
            usage={"provider": ctx.config.provider, "model": ctx.config.primary_model},
        )

        artifact_writes = [
            ArtifactWrite(
                collection="research_enrichment",
                unique_filter={
                    "job_id": artifact.job_id,
                    "input_snapshot_id": artifact.input_snapshot_id,
                    "research_version": artifact.research_version,
                },
                document=artifact.model_dump(),
                ref_name="research_enrichment",
            ),
            ArtifactWrite(
                collection="research_company_cache",
                unique_filter={"cache_key": company_cache_key},
                document={
                    "cache_key": company_cache_key,
                    "canonical_domain": company_profile.canonical_domain,
                    "transport_version": transport_version,
                    "prompt_version": PROMPT_VERSION,
                    "cached_at": _now_iso(),
                    "company_profile": company_profile.model_dump(
                        include={
                            "summary",
                            "url",
                            "signals",
                            "canonical_name",
                            "canonical_domain",
                            "canonical_url",
                            "identity_confidence",
                            "identity_basis",
                            "company_type",
                            "mission_summary",
                            "product_summary",
                            "business_model",
                            "customers_and_market",
                            "scale_signals",
                            "funding_signals",
                            "ai_data_platform_maturity",
                            "team_org_signals",
                            "recent_signals",
                            "sources",
                            "evidence",
                            "confidence",
                            "status",
                        }
                    ),
                },
                ref_name="research_company_cache",
            ),
            ArtifactWrite(
                collection="research_application_cache",
                unique_filter={"cache_key": application_cache_key},
                document={
                    "cache_key": application_cache_key,
                    "normalized_job_url": application_profile.job_url,
                    "canonical_application_url": application_profile.canonical_application_url,
                    "transport_version": transport_version,
                    "prompt_version": PROMPT_VERSION,
                    "cached_at": _now_iso(),
                    "application_profile": application_profile.model_dump(),
                },
                ref_name="research_application_cache",
            ),
        ]
        for record, cache_key in zip(stakeholders, cache_refs["stakeholder_cache_keys"]):
            artifact_writes.append(
                ArtifactWrite(
                    collection="research_stakeholder_cache",
                    unique_filter={"cache_key": cache_key},
                    document={
                        "cache_key": cache_key,
                        "canonical_domain": company_domain,
                        "profile_url": record.profile_url,
                        "transport_version": transport_version,
                        "prompt_version": PROMPT_VERSION,
                        "cached_at": _now_iso(),
                        "stakeholder": record.model_dump(),
                    },
                    ref_name=f"research_stakeholder_cache_{record.candidate_rank}",
                )
            )

        return StageResult(
            stage_output=artifact.model_dump(),
            artifact_writes=artifact_writes,
            provider_used=artifact.provider_used,
            model_used=artifact.model_used,
            prompt_version=PROMPT_VERSION,
        )
