"""Iteration-4.2.1 stakeholder_surface stage."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Iterable, List

from src.preenrich.blueprint_config import (
    current_git_sha,
    research_transport,
    stakeholder_surface_real_discovery_enabled,
    stakeholder_surface_require_source_attribution,
    web_research_enabled,
)
from src.preenrich.blueprint_models import (
    ApplicationProfile,
    CompanyProfile,
    ConfidenceDoc,
    CVPreferenceSurface,
    EvaluatorCoverageEntry,
    EvidenceEntry,
    GuidanceAvoidBullet,
    GuidanceBullet,
    InferredStakeholderPersona,
    PromptMetadata,
    PublicProfessionalDecisionStyle,
    RoleProfile,
    SearchJournalEntry,
    SourceEntry,
    StakeholderEvaluationProfile,
    StakeholderRecord,
    StakeholderSurfaceDoc,
    normalize_company_profile_payload,
    normalize_application_surface_payload,
    normalize_cv_preference_surface_payload,
    normalize_inferred_stakeholder_persona_payload,
    normalize_public_professional_decision_style_payload,
    normalize_role_profile_payload,
    normalize_search_journal_entry_payload,
    normalize_stakeholder_evaluation_profile_payload,
    normalize_stakeholder_record_payload,
)
from src.preenrich.blueprint_prompts import (
    PROMPT_VERSIONS,
    build_p_inferred_stakeholder_personas_v1,
    build_p_stakeholder_discovery_v2,
    build_p_stakeholder_profile_v2,
    build_p_transport_preamble,
)
from src.preenrich.research_transport import CodexResearchTransport, ResearchTransportResult
from src.preenrich.stages.blueprint_common import canonical_domain_from_url, company_slug
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

logger = logging.getLogger(__name__)
PROMPT_VERSION = "stakeholder_surface@v4.2.1"
SURFACE_VERSION = "stakeholder_surface.v4.2.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _band_from_score(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.2:
        return "low"
    return "unresolved"


def _jd_excerpt(ctx: StageContext, *, limit: int = 2000) -> str:
    description = str(ctx.job_doc.get("description") or "").strip()
    if description:
        return description[:limit]
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    fragments = [
        str(jd_facts.get("title") or "").strip(),
        "\n".join(list(jd_facts.get("responsibilities") or [])[:6]),
        "\n".join(list(jd_facts.get("qualifications") or [])[:6]),
    ]
    return "\n".join(item for item in fragments if item)[:limit]


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


def _dedupe_sources(*groups: Iterable[SourceEntry | dict[str, Any]]) -> list[SourceEntry]:
    deduped: dict[str, SourceEntry] = {}
    for group in groups:
        for item in group or []:
            try:
                source = item if isinstance(item, SourceEntry) else SourceEntry.model_validate(item)
            except Exception:
                continue
            deduped[source.source_id] = source
    return list(deduped.values())


def _dedupe_evidence(*groups: Iterable[EvidenceEntry | dict[str, Any]]) -> list[EvidenceEntry]:
    deduped: dict[tuple[str, tuple[str, ...]], EvidenceEntry] = {}
    for group in groups:
        for item in group or []:
            try:
                entry = item if isinstance(item, EvidenceEntry) else EvidenceEntry.model_validate(item)
            except Exception:
                continue
            deduped[(entry.claim, tuple(entry.source_ids))] = entry
    return list(deduped.values())


def _prompt_metadata(*, prompt_id: str, ctx: StageContext) -> PromptMetadata:
    return PromptMetadata(
        prompt_id=prompt_id,
        prompt_version=PROMPT_VERSIONS[prompt_id],
        prompt_file_path=str(__file__).replace("stages/stakeholder_surface.py", "blueprint_prompts.py"),
        git_sha=current_git_sha(),
        provider=ctx.config.provider or "codex",
        model=ctx.config.primary_model,
        transport_used=ctx.config.transport or research_transport(),
        fallback_provider=ctx.config.fallback_provider,
        fallback_transport=ctx.config.fallback_transport,
    )


def _canonical_company_aliases(company_profile: CompanyProfile, job_doc: dict[str, Any]) -> list[str]:
    aliases = {
        str(job_doc.get("company") or "").strip(),
        str(company_profile.canonical_name or "").strip(),
    }
    aliases |= {
        alias.replace(" Ltd", "").replace(" Limited", "").strip()
        for alias in list(aliases)
        if alias
    }
    return [alias for alias in aliases if alias]


def _company_matches(candidate_company: str | None, aliases: list[str]) -> bool:
    if not candidate_company:
        return True
    candidate = candidate_company.strip().lower()
    alias_set = {alias.strip().lower() for alias in aliases if alias}
    return not alias_set or candidate in alias_set


def _looks_constructed_profile_url(name: str | None, profile_url: str | None) -> bool:
    if not name or not profile_url:
        return False
    lowered = profile_url.lower()
    if "linkedin.com/in/" not in lowered:
        return False
    slug = lowered.rstrip("/").rsplit("/", 1)[-1]
    expected = name.strip().lower().replace(" ", "-")
    return slug == expected


def _target_role_brief(ctx: StageContext, role_profile: RoleProfile) -> dict[str, Any]:
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    classification = outputs.get("classification") or {}
    return {
        "normalized_title": str(jd_facts.get("title") or ctx.job_doc.get("title") or "").strip() or "unknown",
        "role_family": str(classification.get("primary_role_category") or "unknown"),
        "function": str((role_profile.org_placement or {}).get("function_area") or "unknown"),
        "department": str((role_profile.org_placement or {}).get("sub_org") or "unknown"),
        "seniority": str(jd_facts.get("seniority_level") or "unknown"),
    }


def _evaluator_coverage_target(ctx: StageContext, role_profile: RoleProfile) -> list[str]:
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    classification = outputs.get("classification") or {}
    ai_taxonomy = classification.get("ai_taxonomy") or {}
    intensity = str(ai_taxonomy.get("intensity") or "unknown")
    seniority = str(jd_facts.get("seniority_level") or "unknown")
    target = ["recruiter", "hiring_manager"]
    technical_categories = {"staff_principal_engineer", "senior_engineer", "tech_lead", "ai_architect", "applied_scientist"}
    if intensity in {"significant", "core"} or str(classification.get("primary_role_category") or "") in technical_categories:
        target.append("peer_technical")
    if seniority in {"staff", "principal", "manager", "senior_manager", "director"}:
        target.append("skip_level_leader")
    collaboration_map = role_profile.collaboration_map or []
    jd_text = _jd_excerpt(ctx, limit=1500).lower()
    if collaboration_map or any(token in jd_text for token in ("product", "security", "design", "data team", "cross-functional")):
        target.append("cross_functional_partner")
    if seniority in {"director", "head", "vp", "c_level"} or any(token in jd_text for token in ("transform", "strategy", "greenfield", "first ai")):
        target.append("executive_sponsor")
    return list(dict.fromkeys(target))


def _coverage_confidence(*, status: str, count: int = 0, basis: str) -> ConfidenceDoc:
    score = 0.82 if status == "real" else 0.62 if status == "inferred" else 0.15
    if count > 1 and status == "real":
        score = 0.9
    return ConfidenceDoc(score=score, band=_band_from_score(score), basis=basis)


def _search_constraints(ctx: StageContext) -> dict[str, Any]:
    return {
        "public_professional_only": True,
        "max_queries": ctx.config.max_web_queries,
        "max_fetches": ctx.config.max_fetches,
    }


def _company_profile_excerpt(profile: CompanyProfile) -> dict[str, Any]:
    return {
        "summary": profile.summary,
        "canonical_name": profile.canonical_name,
        "canonical_domain": profile.canonical_domain,
        "canonical_url": profile.canonical_url,
        "company_type": profile.company_type,
        "role_relevant_signals": [item.model_dump() for item in profile.role_relevant_signals[:4]],
        "confidence": profile.confidence.model_dump(),
        "status": profile.status,
    }


def _role_profile_excerpt(profile: RoleProfile) -> dict[str, Any]:
    return {
        "summary": profile.summary or profile.role_summary,
        "mandate": list(profile.mandate or [])[:5],
        "business_impact": list(profile.business_impact or [])[:4],
        "why_now": profile.why_now,
        "org_placement": dict(profile.org_placement or {}),
        "collaboration_map": list(profile.collaboration_map or [])[:4],
        "confidence": profile.confidence.model_dump(),
        "status": profile.status,
    }


def _application_profile_excerpt(profile: ApplicationProfile) -> dict[str, Any]:
    return {
        "canonical_application_url": profile.canonical_application_url,
        "portal_family": profile.portal_family,
        "ats_vendor": profile.ats_vendor,
        "ui_actionability": profile.ui_actionability,
        "resolution_status": profile.resolution_status,
        "confidence": profile.confidence.model_dump(),
        "status": profile.status,
    }


def _validate_discovery_payload(
    payload: dict[str, Any],
    *,
    company_aliases: list[str],
    require_source_attribution: bool,
) -> dict[str, Any]:
    raw_records = payload.get("stakeholder_intelligence") or []
    if not isinstance(raw_records, list):
        raise ValueError("stakeholder_intelligence must be a list")
    records: list[StakeholderRecord] = []
    for raw in raw_records:
        normalized = normalize_stakeholder_record_payload(raw if isinstance(raw, dict) else {})
        if _looks_constructed_profile_url(normalized.get("name"), normalized.get("profile_url")):
            raise ValueError("constructed stakeholder profile URL rejected")
        if not _company_matches(normalized.get("current_company"), company_aliases):
            raise ValueError("cross-company stakeholder candidate rejected")
        if require_source_attribution and not normalized.get("sources"):
            raise ValueError("stakeholder discovery requires sources[] on persisted real records")
        if require_source_attribution and not normalized.get("matched_signal_classes"):
            raise ValueError("stakeholder discovery requires matched_signal_classes on persisted real records")
        records.append(StakeholderRecord.model_validate(normalized))
    search_journal = [
        SearchJournalEntry.model_validate(normalize_search_journal_entry_payload(item))
        for item in (payload.get("search_journal") or [])
        if isinstance(item, dict)
    ]
    return {
        "stakeholder_intelligence": records,
        "search_journal": search_journal,
        "unresolved_markers": list(payload.get("unresolved_markers") or []),
        "notes": list(payload.get("notes") or []),
    }


def _valid_seed_records(seed_payloads: list[dict[str, Any]], *, company_aliases: list[str]) -> tuple[list[StakeholderRecord], list[str]]:
    records: list[StakeholderRecord] = []
    notes: list[str] = []
    for raw in seed_payloads:
        try:
            normalized = normalize_stakeholder_record_payload(raw)
            if normalized.get("identity_confidence", {}).get("band") not in {"medium", "high"}:
                continue
            if _looks_constructed_profile_url(normalized.get("name"), normalized.get("profile_url")):
                notes.append("Rejected seed stakeholder with constructed profile URL.")
                continue
            if not _company_matches(normalized.get("current_company"), company_aliases):
                notes.append("Rejected seed stakeholder due to cross-company mismatch.")
                continue
            records.append(StakeholderRecord.model_validate(normalized))
        except Exception as exc:
            notes.append(f"Rejected seed stakeholder during normalization: {exc}")
    return records, notes


def _merge_real_records(live_records: list[StakeholderRecord], seed_records: list[StakeholderRecord]) -> list[StakeholderRecord]:
    merged: dict[str, StakeholderRecord] = {}
    for record in [*live_records, *seed_records]:
        key = record.profile_url or f"{record.name}|{record.current_title}|{record.stakeholder_type}"
        existing = merged.get(key)
        if existing is None or record.identity_confidence.score > existing.identity_confidence.score:
            merged[key] = record
    ordered = sorted(
        merged.values(),
        key=lambda item: (item.identity_confidence.score, item.candidate_rank or 999),
        reverse=True,
    )
    return ordered


def _role_in_process(role: str) -> str:
    mapping = {
        "recruiter": "screening_and_process_control",
        "hiring_manager": "mandate_fit_and_delivery_risk_screen",
        "skip_level_leader": "organizational_scope_and_risk_review",
        "peer_technical": "technical_depth_and_execution_screen",
        "cross_functional_partner": "collaboration_and_delivery_interface_review",
        "executive_sponsor": "strategic_case_and_leadership_signal_review",
    }
    return mapping.get(role, "evaluator_screen")


def _build_identity_only_profile(record: StakeholderRecord) -> StakeholderEvaluationProfile:
    return StakeholderEvaluationProfile(
        stakeholder_ref=f"candidate_rank:{record.candidate_rank}" if record.candidate_rank is not None else f"profile:{company_slug(record.name or record.current_title or 'unknown')}",
        stakeholder_record_snapshot=record,
        stakeholder_type=record.stakeholder_type if record.stakeholder_type != "unknown" else "hiring_manager",
        role_in_process=_role_in_process(record.stakeholder_type if record.stakeholder_type != "unknown" else "hiring_manager"),
        likely_priorities=list(record.likely_priorities or []),
        likely_reject_signals=list(record.avoid_points or []),
        unresolved_markers=list(record.unresolved_markers or []),
        sources=list(record.sources or []),
        evidence=list(record.evidence or []),
        confidence=record.confidence,
        status="identity_only",
    )


def _merge_profile_payload(record: StakeholderRecord, payload: dict[str, Any] | None) -> StakeholderEvaluationProfile:
    base = _build_identity_only_profile(record)
    if not isinstance(payload, dict):
        return base
    normalized = normalize_stakeholder_evaluation_profile_payload(payload)
    style = normalized.get("public_professional_decision_style")
    cv_surface = normalized.get("cv_preference_surface")
    sources = _dedupe_sources(base.sources, normalized.get("sources") or [])
    evidence = _dedupe_evidence(base.evidence, normalized.get("evidence") or [])
    profile = StakeholderEvaluationProfile(
        stakeholder_ref=normalized.get("stakeholder_ref") or base.stakeholder_ref,
        stakeholder_record_snapshot=record,
        stakeholder_type=normalized.get("stakeholder_type") or base.stakeholder_type,
        role_in_process=normalized.get("role_in_process") or base.role_in_process,
        public_professional_decision_style=(
            PublicProfessionalDecisionStyle.model_validate(style) if isinstance(style, dict) else None
        ),
        cv_preference_surface=CVPreferenceSurface.model_validate(cv_surface) if isinstance(cv_surface, dict) else None,
        likely_priorities=[GuidanceBullet.model_validate(item) for item in (payload.get("likely_priorities") or [])],
        likely_reject_signals=[GuidanceAvoidBullet.model_validate(item) for item in (payload.get("likely_reject_signals") or [])],
        unresolved_markers=list(normalized.get("unresolved_markers") or []),
        sources=sources,
        evidence=evidence,
        confidence=ConfidenceDoc.model_validate(normalized.get("confidence") or base.confidence.model_dump()),
        status=normalized.get("status") or ("completed" if style and cv_surface else "partial"),
    )
    if not profile.public_professional_decision_style and not profile.cv_preference_surface:
        profile.status = "identity_only"
    elif not profile.public_professional_decision_style or not profile.cv_preference_surface:
        profile.status = "partial"
    else:
        profile.status = "completed"
    return profile


def _validate_personas_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_personas = payload.get("inferred_stakeholder_personas") or []
    if not isinstance(raw_personas, list):
        raise ValueError("inferred_stakeholder_personas must be a list")
    personas = [
        InferredStakeholderPersona.model_validate(normalize_inferred_stakeholder_persona_payload(item))
        for item in raw_personas
        if isinstance(item, dict)
    ]
    return {
        "inferred_stakeholder_personas": personas,
        "unresolved_markers": list(payload.get("unresolved_markers") or []),
        "notes": list(payload.get("notes") or []),
    }


def _deterministic_persona(
    *,
    role: str,
    emission_mode: str,
    target_role_brief: dict[str, Any],
    company_profile: CompanyProfile,
    role_profile: RoleProfile,
    no_research_mode: bool,
) -> InferredStakeholderPersona:
    score = 0.36 if no_research_mode else 0.62
    style = PublicProfessionalDecisionStyle(
        evidence_preference="metrics_and_systems" if role in {"hiring_manager", "peer_technical", "skip_level_leader"} else "scope_and_ownership",
        risk_posture="quality_first" if role in {"hiring_manager", "peer_technical"} else "balanced",
        speed_vs_rigor="balanced",
        communication_style="concise_substantive",
        authority_orientation="credibility_over_title",
        technical_vs_business_bias="technical_first" if role in {"peer_technical", "hiring_manager"} else "balanced",
    )
    cv_surface = CVPreferenceSurface(
        review_objectives=[
            "Verify role-relevant credibility",
            "Verify scope and ownership",
        ],
        preferred_signal_order=["hands_on_implementation", "ownership_scope", "production_impact"],
        preferred_evidence_types=["named_systems", "metrics", "ownership_scope"],
        preferred_header_bias=["credibility_first", "low_hype"],
        title_match_preference="moderate",
        keyword_bias="medium",
        ai_section_preference="dedicated_if_core",
        preferred_tone=["clear", "evidence_first"],
        evidence_basis="inferred from role class, JD, and company context",
        confidence=ConfidenceDoc(score=min(score, 0.79), band="medium" if score >= 0.5 else "low", basis="Deterministic inferred evaluator persona."),
    )
    return InferredStakeholderPersona(
        persona_id=f"persona_{role}_{company_slug(target_role_brief.get('role_family') or 'role')}",
        persona_type=role,
        role_in_process=_role_in_process(role),
        emitted_because=emission_mode if emission_mode in {"no_real_candidate", "real_search_disabled", "real_ambiguous", "coverage_gap_despite_real"} else "coverage_gap_despite_real",
        trigger_basis=[
            str(target_role_brief.get("role_family") or "unknown_role_family"),
            f"{role}_coverage_gap",
        ],
        coverage_gap=role,
        public_professional_decision_style=style,
        cv_preference_surface=cv_surface,
        likely_priorities=[
            GuidanceBullet(bullet="Evidence of role-relevant delivery and ownership.", basis="inferred", source_ids=[]),
            GuidanceBullet(bullet="Clear proof of shipped outcomes tied to the mandate.", basis="inferred", source_ids=[]),
        ],
        likely_reject_signals=[
            GuidanceAvoidBullet(bullet="Generic claims without grounded ownership evidence.", reason="inferred", source_ids=[]),
            GuidanceAvoidBullet(bullet="Inflated title or hype without delivery proof.", reason="inferred", source_ids=[]),
        ],
        unresolved_markers=[f"No real {role} identity resolved."],
        evidence_basis="This persona is inferred from role class, JD, and company context.",
        sources=[*company_profile.sources[:1], *role_profile.sources[:1]],
        evidence=[EvidenceEntry(claim="Persona is inferred from JD and role/company context.", source_ids=[], basis="inferred")],
        confidence=ConfidenceDoc(score=score, band="medium" if score >= 0.5 else "low", basis="Deterministic inferred evaluator persona."),
    )


def _coverage_entries(
    target_roles: list[str],
    real_profiles: list[StakeholderEvaluationProfile],
    personas: list[InferredStakeholderPersona],
) -> list[EvaluatorCoverageEntry]:
    entries: list[EvaluatorCoverageEntry] = []
    for role in target_roles:
        stakeholder_refs = [item.stakeholder_ref for item in real_profiles if item.stakeholder_type == role and item.stakeholder_record_snapshot.identity_confidence.band in {"medium", "high"}]
        persona_refs = [item.persona_id for item in personas if item.coverage_gap == role]
        if stakeholder_refs:
            entries.append(
                EvaluatorCoverageEntry(
                    role=role,
                    required=True,
                    status="real",
                    stakeholder_refs=stakeholder_refs,
                    coverage_confidence=_coverage_confidence(status="real", count=len(stakeholder_refs), basis=f"Real stakeholder coverage present for {role}."),
                )
            )
        elif persona_refs:
            entries.append(
                EvaluatorCoverageEntry(
                    role=role,
                    required=True,
                    status="inferred",
                    persona_refs=persona_refs,
                    coverage_confidence=_coverage_confidence(status="inferred", count=len(persona_refs), basis=f"Inferred persona coverage filled {role}."),
                )
            )
        else:
            entries.append(
                EvaluatorCoverageEntry(
                    role=role,
                    required=True,
                    status="uncovered",
                    coverage_confidence=_coverage_confidence(status="uncovered", basis=f"No real or inferred coverage for {role}."),
                )
            )
    return entries


def _overall_status(
    *,
    real_discovery_enabled: bool,
    upstream_no_research: bool,
    real_profiles: list[StakeholderEvaluationProfile],
    personas: list[InferredStakeholderPersona],
    coverage: list[EvaluatorCoverageEntry],
) -> str:
    if not coverage and not personas and not real_profiles:
        return "unresolved"
    if upstream_no_research and personas:
        return "no_research"
    if not real_discovery_enabled and personas:
        return "inferred_only"
    if real_profiles and any(item.status != "completed" for item in real_profiles):
        return "partial"
    if any(item.status == "uncovered" for item in coverage):
        return "partial"
    if not real_profiles and personas:
        return "inferred_only"
    return "completed"


class StakeholderSurfaceStage:
    name: str = "stakeholder_surface"
    dependencies: List[str] = ["jd_facts", "classification", "application_surface", "research_enrichment"]

    def run(self, ctx: StageContext) -> StageResult:
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        research = outputs.get("research_enrichment") or {}
        jd_facts = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
        classification = outputs.get("classification") or {}
        application_payload = research.get("application_profile") or outputs.get("application_surface") or {}
        company_profile = CompanyProfile.model_validate(normalize_company_profile_payload(research.get("company_profile") or {}))
        role_profile = RoleProfile.model_validate(normalize_role_profile_payload(research.get("role_profile") or {}))
        application_profile = ApplicationProfile.model_validate(normalize_application_surface_payload(application_payload or {"status": "unresolved"}))
        seed_payloads = [dict(item) for item in (research.get("stakeholder_intelligence") or []) if isinstance(item, dict)]
        company_aliases = _canonical_company_aliases(company_profile, ctx.job_doc)
        canonical_company_identity = {
            "canonical_name": company_profile.canonical_name,
            "canonical_domain": company_profile.canonical_domain,
            "aliases": company_aliases,
            "official_urls": [item for item in {company_profile.canonical_url, company_profile.url} if item],
            "identity_confidence": company_profile.identity_confidence.model_dump(),
        }
        target_role_brief = _target_role_brief(ctx, role_profile)
        coverage_target = _evaluator_coverage_target(ctx, role_profile)
        upstream_no_research = str(research.get("status") or "") == "no_research"
        transport = CodexResearchTransport(ctx.config)
        real_discovery_enabled = (
            stakeholder_surface_real_discovery_enabled()
            and web_research_enabled()
            and transport.is_live_configured()
            and company_profile.identity_confidence.band in {"medium", "high"}
            and not upstream_no_research
        )
        capability_flags = {
            "web_search": transport.is_live_configured() and web_research_enabled(),
            "real_discovery_enabled": real_discovery_enabled,
            "upstream_no_research": upstream_no_research,
            "require_source_attribution": stakeholder_surface_require_source_attribution(),
        }
        prompt_metadata = {
            "discovery": _prompt_metadata(prompt_id="stakeholder_surface_discovery", ctx=ctx),
            "profile": _prompt_metadata(prompt_id="stakeholder_surface_profile", ctx=ctx),
            "personas": _prompt_metadata(prompt_id="inferred_stakeholder_personas", ctx=ctx),
        }
        search_journal: list[SearchJournalEntry] = [
            SearchJournalEntry(
                step="preflight",
                intent="deterministic_preflight",
                outcome="hit",
                notes=f"real_discovery_enabled={real_discovery_enabled}; company_identity_band={company_profile.identity_confidence.band}; coverage_target={','.join(coverage_target)}",
            )
        ]
        notes: list[str] = []
        unresolved_questions: list[str] = []

        live_records: list[StakeholderRecord] = []
        if real_discovery_enabled:
            discovery_prompt = build_p_stakeholder_discovery_v2(
                canonical_company_identity=canonical_company_identity,
                target_role_brief=target_role_brief,
                evaluator_coverage_target=coverage_target,
                seed_stakeholders=seed_payloads[:5],
                company_profile_excerpt=_company_profile_excerpt(company_profile),
                role_profile_excerpt=_role_profile_excerpt(role_profile),
                application_profile_excerpt=_application_profile_excerpt(application_profile),
                jd_excerpt=_jd_excerpt(ctx),
                search_constraints=_search_constraints(ctx),
                transport_preamble=_transport_preamble(ctx, transport),
                job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "stakeholder-surface"),
            )
            result = transport.invoke_json(
                prompt=discovery_prompt,
                job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "stakeholder-surface-discovery"),
                validator=lambda payload: _validate_discovery_payload(
                    payload,
                    company_aliases=company_aliases,
                    require_source_attribution=stakeholder_surface_require_source_attribution(),
                ),
            )
            logger.info(
                "stakeholder_surface discovery result: success=%s error=%s payload_keys=%s",
                result.success,
                result.error,
                _payload_keys(result.payload),
            )
            if result.success and isinstance(result.payload, dict):
                live_records = list(result.payload.get("stakeholder_intelligence") or [])
                search_journal.extend(result.payload.get("search_journal") or [])
                unresolved_questions.extend(list(result.payload.get("unresolved_markers") or []))
                notes.extend(list(result.payload.get("notes") or []))
            else:
                unresolved_questions.append(f"Real stakeholder discovery failed: {result.error or 'unknown error'}")
                search_journal.append(
                    SearchJournalEntry(
                        step="discovery",
                        intent="real_stakeholder_identity_resolution",
                        outcome="ambiguous",
                        notes=result.error or "discovery_failed",
                    )
                )
        else:
            notes.append("Real stakeholder discovery skipped; stage will fail open to inferred personas.")

        if real_discovery_enabled:
            seed_records, seed_notes = _valid_seed_records(seed_payloads, company_aliases=company_aliases)
            notes.extend(seed_notes)
            real_records = _merge_real_records(live_records, seed_records)
            if seed_records:
                capability_flags["seed_records_considered"] = len(seed_records)
        else:
            real_records = []

        real_profiles: list[StakeholderEvaluationProfile] = []
        for record in real_records:
            if record.identity_confidence.band not in {"medium", "high"}:
                continue
            profile_prompt = build_p_stakeholder_profile_v2(
                stakeholder_record=record.model_dump(),
                target_role_brief=target_role_brief,
                company_profile_excerpt=_company_profile_excerpt(company_profile),
                role_profile_excerpt=_role_profile_excerpt(role_profile),
                application_profile_excerpt=_application_profile_excerpt(application_profile),
                jd_excerpt=_jd_excerpt(ctx),
                public_posts_fetched=[],
                coverage_context={
                    "evaluator_coverage_target": coverage_target,
                    "real_types_already_found": [item.stakeholder_type for item in real_profiles],
                },
                transport_preamble=_transport_preamble(ctx, transport),
            )
            payload: dict[str, Any] | None = None
            if real_discovery_enabled:
                profile_result = transport.invoke_json(
                    prompt=profile_prompt,
                    job_id=f"{ctx.job_doc.get('_id')}:stakeholder-profile:{record.candidate_rank or 0}",
                )
                logger.info(
                    "stakeholder_surface profile result: candidate_rank=%s success=%s error=%s payload_keys=%s",
                    record.candidate_rank,
                    profile_result.success,
                    profile_result.error,
                    _payload_keys(profile_result.payload),
                )
                if profile_result.success and isinstance(profile_result.payload, dict):
                    payload = profile_result.payload
                else:
                    notes.append(f"Profile enrichment fell back to identity-only for candidate_rank={record.candidate_rank}: {profile_result.error or 'unknown error'}")
            real_profiles.append(_merge_profile_payload(record, payload))

        filled_roles = {item.stakeholder_type for item in real_profiles if item.stakeholder_record_snapshot.identity_confidence.band in {"medium", "high"}}
        missing_roles = [role for role in coverage_target if role not in filled_roles]
        personas: list[InferredStakeholderPersona] = []
        persona_notes: list[str] = []
        if missing_roles:
            emission_mode = (
                "no_research"
                if upstream_no_research
                else "real_search_disabled"
                if not real_discovery_enabled
                else "coverage_gap_despite_real"
                if real_profiles
                else "no_real_candidate"
            )
            personas_prompt = build_p_inferred_stakeholder_personas_v1(
                target_role_brief=target_role_brief,
                canonical_company_identity=canonical_company_identity,
                company_profile_excerpt=_company_profile_excerpt(company_profile),
                role_profile_excerpt=_role_profile_excerpt(role_profile),
                application_profile_excerpt=_application_profile_excerpt(application_profile),
                classification_excerpt={
                    "primary_role_category": classification.get("primary_role_category"),
                    "ai_taxonomy": classification.get("ai_taxonomy") or {},
                },
                jd_excerpt=_jd_excerpt(ctx),
                real_stakeholder_summaries=[
                    {
                        "stakeholder_type": item.stakeholder_type,
                        "identity_status": item.stakeholder_record_snapshot.identity_status,
                    }
                    for item in real_profiles
                ],
                evaluator_coverage_target=coverage_target,
                missing_coverage_types=missing_roles,
                emission_mode=emission_mode,
            )
            persona_result = transport.invoke_json(
                prompt=personas_prompt,
                job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "stakeholder-personas"),
                validator=_validate_personas_payload,
            )
            logger.info(
                "stakeholder_surface personas result: success=%s error=%s payload_keys=%s",
                persona_result.success,
                persona_result.error,
                _payload_keys(persona_result.payload),
            )
            if persona_result.success and isinstance(persona_result.payload, dict):
                personas = list(persona_result.payload.get("inferred_stakeholder_personas") or [])
                unresolved_questions.extend(list(persona_result.payload.get("unresolved_markers") or []))
                persona_notes.extend(list(persona_result.payload.get("notes") or []))
            covered_persona_roles = {item.coverage_gap for item in personas}
            fallback_roles = [role for role in missing_roles if role not in covered_persona_roles]
            if not personas or fallback_roles:
                capability_flags["deterministic_persona_fallback"] = True
                personas.extend(
                    _deterministic_persona(
                        role=role,
                        emission_mode=emission_mode,
                        target_role_brief=target_role_brief,
                        company_profile=company_profile,
                        role_profile=role_profile,
                        no_research_mode=upstream_no_research,
                    )
                    for role in fallback_roles if role
                )
                if not covered_persona_roles:
                    persona_notes.append("Persona synthesis fell back to deterministic personas.")
                elif fallback_roles:
                    persona_notes.append(
                        "Persona synthesis was incomplete; deterministic personas filled remaining evaluator coverage gaps."
                    )
        notes.extend(persona_notes)

        coverage = _coverage_entries(coverage_target, real_profiles, personas)
        status = _overall_status(
            real_discovery_enabled=real_discovery_enabled,
            upstream_no_research=upstream_no_research,
            real_profiles=real_profiles,
            personas=personas,
            coverage=coverage,
        )
        sources = _dedupe_sources(
            *[item.sources for item in real_profiles],
            *[item.sources for item in personas],
        )
        evidence = _dedupe_evidence(
            *[item.evidence for item in real_profiles],
            *[item.evidence for item in personas],
        )
        score = 0.0
        if coverage:
            score = sum(item.coverage_confidence.score for item in coverage) / len(coverage)
        if real_profiles:
            score = max(score, sum(item.confidence.score for item in real_profiles) / len(real_profiles))
        overall_confidence = ConfidenceDoc(
            score=score,
            band=_band_from_score(score),
            basis="Aggregate confidence across evaluator coverage, real stakeholder profiles, and inferred personas.",
            unresolved_items=list(dict.fromkeys(unresolved_questions)),
        )
        artifact = StakeholderSurfaceDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            research_enrichment_id="__ref__:research_enrichment.id",
            input_snapshot_id=ctx.input_snapshot_id,
            prompt_versions={
                "discovery": PROMPT_VERSIONS["stakeholder_surface_discovery"],
                "profile": PROMPT_VERSIONS["stakeholder_surface_profile"],
                "personas": PROMPT_VERSIONS["inferred_stakeholder_personas"],
            },
            prompt_metadata=prompt_metadata,
            status=status,
            capability_flags=capability_flags,
            evaluator_coverage_target=coverage_target,
            evaluator_coverage=coverage,
            real_stakeholders=real_profiles,
            inferred_stakeholder_personas=personas,
            search_journal=search_journal,
            sources=sources,
            evidence=evidence,
            confidence=overall_confidence,
            unresolved_questions=list(dict.fromkeys(unresolved_questions)),
            notes=[
                "stakeholder_surface is the canonical evaluator-first stakeholder artifact for 4.2.1.",
                "Real stakeholder identity resolution remains disjoint from inferred persona synthesis.",
                *notes,
            ],
            timing={"generated_at": _now_iso()},
            usage={"provider": ctx.config.provider, "model": ctx.config.primary_model},
        )

        return StageResult(
            stage_output=artifact.model_dump(),
            artifact_writes=[
                ArtifactWrite(
                    collection="stakeholder_surface",
                    unique_filter={
                        "job_id": artifact.job_id,
                        "input_snapshot_id": artifact.input_snapshot_id,
                        "research_enrichment_id": artifact.research_enrichment_id,
                    },
                    document=artifact.model_dump(),
                    ref_name="stakeholder_surface",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )
