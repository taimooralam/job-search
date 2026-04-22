"""Prompt builders for iteration-4.1 blueprint stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.layer1_4.prompts import JD_EXTRACTION_SYSTEM_PROMPT
from src.preenrich.blueprint_config import current_git_sha, load_job_taxonomy, taxonomy_version

PROMPT_LIBRARY_PATH = str(Path(__file__).resolve())

PROMPT_VERSIONS = {
    "transport_preamble": "P-transport-preamble@v1",
    "application_surface": "P-application-surface@v1.1",
    "research_company": "P-research-company@v1.1",
    "research_role": "P-research-role@v1.1",
    "research_application_merge": "P-research-application-merge@v1.1",
    "stakeholder_discovery": "P-stakeholder-discovery@v1.1",
    "stakeholder_profile": "P-stakeholder-profile@v1.1",
    "stakeholder_outreach_guidance": "P-stakeholder-outreach-guidance@v1.1",
    "stakeholder_surface_discovery": "P-stakeholder-discovery@v2",
    "stakeholder_surface_profile": "P-stakeholder-profile@v2",
    "inferred_stakeholder_personas": "P-inferred-stakeholder-personas@v1",
}


def _reject_hypotheses_payload(prompt_name: str, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, sort_keys=True, default=str).lower()
    if "job_hypotheses" in serialized:
        raise ValueError(f"{prompt_name} prompt payload must not reference job_hypotheses")


def _json_only_contract(name: str, schema_keys: list[str]) -> str:
    return (
        f"You are {name}. Return ONLY valid JSON. "
        "No prose. No markdown fences. No commentary. "
        f"Required top-level keys: {', '.join(schema_keys)}."
    )


SHARED_CONTRACT_HEADER = """You are a preenrich research worker for Iteration 4.1.3.

Hard output rules:
- Return ONLY valid JSON. No markdown, no code fences, no commentary.
- Use the literal string "unknown" only for schema fields that explicitly allow unknown string values. Do not invent placeholder values for enums, URLs, dates, or identifiers.
- Empty lists MUST be [].
- Every factual claim MUST cite at least one entry from the `sources` array by `source_id`.
- Every persisted subdocument MUST include a `confidence` object: {score: 0.0-1.0, band: "high"|"medium"|"low"|"unresolved", basis: string}.
- If the evidence is insufficient for a claim, emit status="unresolved" for that subdocument and move on.
- NEVER invent people, URLs, dates, titles, or quotes. NEVER merge two ambiguous profiles.
- NEVER infer protected traits (age, gender, race, religion, politics, health, family status).
- NEVER scrape or guess personal contact details (personal email, phone, home address).

Source discipline:
- Every source you consult MUST be added to the `sources` array with a unique `source_id`.
- Each source entry: {source_id, url, source_type, fetched_at, trust_tier}.
- Primary = company-owned official page, ATS page, job posting page.
- Secondary = LinkedIn, Crunchbase, reputable press, official filings.
- Tertiary = aggregators, blog posts, forums.

Evidence discipline:
- Every persisted subdocument MUST include an `evidence` array of {claim, source_ids[], excerpt?} tuples.
- An excerpt, when present, MUST be <= 240 chars quoted directly from the source.
- If you did not directly observe quote text, omit `excerpt` rather than fabricating a paraphrase as a quote.

Verification discipline:
- A URL may be returned only if it was directly fetched, observed in fetched content, or observed in a trusted search result payload.
- Probe templates and constructed ATS candidates are discovery aids only. They are NOT valid outputs unless subsequently verified.
- Domains may not be guessed from company slugs alone.
- Dates MUST be directly observed. If not directly observed, emit "unknown".

Confidence calibration:
- high  (>=0.80): two+ converging primary/secondary sources OR one unambiguous primary source.
- medium (0.50-0.79): one secondary source OR converging tertiary sources.
- low    (0.20-0.49): single tertiary source OR inferential from strong priors.
- unresolved (<0.20): stop and emit status="unresolved" for that subdocument.

Abstain rules:
- If you cannot resolve company identity with at least medium confidence, emit company_profile.status="unresolved" and skip downstream claims that depend on company identity.
- If role family cannot be identified from JD + classification, emit role_profile.status="partial" with only the fields you can ground.
- If no stakeholder candidate clears medium confidence, emit stakeholder_intelligence=[] with a note explaining why.

Safety guardrails:
- No protected-trait inference, no psychologizing, no speculation about private motives.
- No covert-influence or manipulation tactics in outreach guidance.
- No private contact routes. Restrict guidance to public-professional channels only."""


def prompt_metadata(prompt_key: str, *, provider: str, model: str | None, transport_used: str) -> dict[str, str | None]:
    prompt_version = PROMPT_VERSIONS[prompt_key]
    return {
        "prompt_id": prompt_key,
        "prompt_version": prompt_version,
        "prompt_file_path": PROMPT_LIBRARY_PATH,
        "git_sha": current_git_sha(),
        "provider": provider,
        "model": model,
        "transport_used": transport_used,
    }


def build_p_transport_preamble(*, transport_used: str, max_web_queries: int, max_fetches: int, max_tool_turns: int) -> str:
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            f"Transport: {transport_used}",
            "Budget:",
            f"- max_web_queries: {max_web_queries}",
            f"- max_fetches: {max_fetches}",
            f"- max_tool_turns: {max_tool_turns}",
            "Tool-use rules:",
            "- Prefer primary sources over aggregators.",
            "- After each successful fetch, record the fetched URL and a one-sentence relevance tag.",
            "- Stop fetching once you have enough to emit a schema-valid artifact with high or medium confidence.",
            "- If you exhaust the budget without reaching medium confidence, emit status=\"partial\" with what you have.",
            "- Never fetch private pages, logged-in views, or pages behind unreadable paywalls.",
            "- Do not inspect local repository files, local tests, or local prompt code. Treat local workspace context as irrelevant unless the payload explicitly contains it.",
            "- Do not use shell commands for schema discovery, file discovery, or repo inspection. Use web tools only when transport is web-enabled.",
            "- Do not narrate planning, schema deliberation, or tool strategy. Spend the budget on evidence gathering, then emit JSON immediately.",
            "Return only the downstream artifact JSON for this step. Do not echo this preamble.",
        ]
    )


def _minimal_research_company_example() -> str:
    example = {
        "summary": "Acme is an enterprise workflow software company.",
        "url": "https://acme.example.com/",
        "signals": [{"type": "growth", "description": "Hiring across platform engineering.", "source_ids": ["src_company_home"]}],
        "canonical_name": "Acme",
        "canonical_domain": "acme.example.com",
        "canonical_url": "https://acme.example.com/",
        "identity_confidence": {"score": 0.9, "band": "high", "basis": "Official company website."},
        "identity_basis": "Official company website.",
        "identity_detail": {"status": "complete", "text": "Company identity verified on the official site."},
        "company_type": "employer",
        "mission_summary": "Acme helps operations teams automate workflows.",
        "mission_detail": {"status": "partial", "text": "Mission inferred from official product copy."},
        "product_summary": "Workflow automation software for enterprise operations.",
        "product_detail": {"status": "partial", "text": "Official product description."},
        "business_model": "B2B software.",
        "business_model_detail": {"status": "partial", "text": "Enterprise software sold to business customers."},
        "customers_and_market": {"status": "partial", "items": ["Enterprise operations teams"]},
        "scale_signals": {"status": "partial", "items": ["Official careers page present"]},
        "funding_signals": [],
        "ai_data_platform_maturity": {"status": "unresolved", "summary": "Not evidenced in fetched sources."},
        "team_org_signals": {"status": "partial", "items": ["Platform engineering hiring observed"]},
        "recent_signals": [],
        "role_relevant_signals": [{"type": "other", "description": "Hiring platform engineers.", "source_ids": ["src_company_home"]}],
        "signals_rich": [{"type": "growth", "description": "Hiring across platform engineering.", "source_ids": ["src_company_home"]}],
        "recent_signals_rich": [],
        "role_relevant_signals_rich": [{"type": "other", "description": "Hiring platform engineers.", "source_ids": ["src_company_home"]}],
        "sources": [{"source_id": "src_company_home", "url": "https://acme.example.com/", "source_type": "official_company_site", "fetched_at": "2026-04-21", "trust_tier": "primary"}],
        "evidence": [{"claim": "Acme operates the official domain acme.example.com.", "source_ids": ["src_company_home"]}],
        "confidence": {"score": 0.84, "band": "high", "basis": "Company identity and core business are supported by primary sources."},
        "status": "partial",
    }
    return json.dumps(example, indent=2)


def _minimal_research_role_example() -> str:
    example = {
        "role_summary": "Staff-level platform role focused on delivery and architecture.",
        "summary": "Staff-level platform role focused on delivery and architecture.",
        "summary_detail": {"status": "complete", "text": "Role scope grounded in the JD."},
        "role_summary_detail": {"status": "complete", "text": "Role scope grounded in the JD."},
        "mandate": ["Own platform architecture", "Lead delivery"],
        "business_impact": ["Improve reliability", "Increase delivery velocity"],
        "why_now": "The organization is scaling platform delivery.",
        "why_now_detail": {"status": "partial", "text": "Why-now rationale is inferred from the JD and company context."},
        "success_metrics": ["Reduce incidents", "Improve deploy velocity"],
        "collaboration_map": [{"status": "partial", "partners": ["Product", "Security"]}],
        "reporting_line": {},
        "org_placement": {},
        "interview_themes": ["Architecture", "Delivery", "Stakeholder management"],
        "evaluation_signals": ["System design depth", "Execution signal"],
        "risk_landscape": ["Reliability risk", "Governance risk"],
        "company_context_alignment": "The role supports platform scale and delivery quality.",
        "company_context_alignment_detail": {"status": "partial", "text": "Alignment is grounded in the JD plus company context."},
        "sources": [{"source_id": "src_jd", "url": None, "source_type": "job_document", "fetched_at": "2026-04-21", "trust_tier": "primary"}],
        "evidence": [{"claim": "The JD emphasizes platform architecture and delivery ownership.", "source_ids": ["src_jd"]}],
        "confidence": {"score": 0.8, "band": "high", "basis": "Role scope is strongly supported by the JD."},
        "status": "partial",
    }
    return json.dumps(example, indent=2)


def _minimal_research_application_merge_example() -> str:
    example = {
        "application_profile": {
            "status": "partial",
            "job_url": "https://linkedin.com/jobs/view/123",
            "canonical_application_url": None,
            "resolution_method": "web_search",
            "resolution_status": "unresolved",
            "resolution_note": "No authoritative employer-owned or ATS-owned application URL was directly observed.",
            "ui_actionability": "blocked",
            "portal_family": "unknown",
            "form_fetch_status": "not_attempted",
            "apply_caveats": ["Canonical application URL remains unresolved."],
            "sources": [{"source_id": "src_job_url", "url": "https://linkedin.com/jobs/view/123", "source_type": "input", "fetched_at": "2026-04-21", "trust_tier": "secondary"}],
            "evidence": [{"claim": "The provided job URL is a LinkedIn job view link.", "source_ids": ["src_job_url"]}],
            "confidence": {"score": 0.2, "band": "unresolved", "basis": "No authoritative employer or ATS URL was directly observed."}
        }
    }
    return json.dumps(example, indent=2)


def _minimal_stakeholder_evaluation_profile_example() -> str:
    example = {
        "stakeholder_ref": "candidate_rank:1",
        "stakeholder_type": "hiring_manager",
        "role_in_process": "mandate_fit_and_delivery_risk_screen",
        "public_professional_decision_style": {
            "evidence_preference": "metrics_and_systems",
            "risk_posture": "quality_first",
            "speed_vs_rigor": "rigor_first",
            "communication_style": "concise_substantive",
            "authority_orientation": "credibility_over_title",
            "technical_vs_business_bias": "technical_first",
        },
        "cv_preference_surface": {
            "review_objectives": ["Verify shipped systems", "Verify ownership scope"],
            "preferred_signal_order": ["hands_on_implementation", "architecture_judgment", "production_impact"],
            "preferred_evidence_types": ["named_systems", "metrics", "ownership_scope"],
            "preferred_header_bias": ["credibility_first", "low_hype"],
            "title_match_preference": "moderate",
            "keyword_bias": "medium",
            "ai_section_preference": "dedicated_if_core",
            "preferred_tone": ["clear", "evidence_first"],
            "evidence_basis": "Public professional signals and role context.",
            "confidence": {"score": 0.71, "band": "medium", "basis": "Public professional signals support evaluator inference."},
        },
        "likely_priorities": [{"bullet": "Proof of shipped production systems.", "basis": "role mandate", "source_ids": ["src_manager_profile"]}],
        "likely_reject_signals": [{"bullet": "Generic AI claims with no ownership signal.", "reason": "quality_screen", "source_ids": ["src_manager_profile"]}],
        "unresolved_markers": [],
        "sources": [{"source_id": "src_manager_profile", "url": "https://example.com/team", "source_type": "company_site", "fetched_at": "2026-04-21", "trust_tier": "primary"}],
        "evidence": [{"claim": "The stakeholder is positioned as engineering leadership.", "source_ids": ["src_manager_profile"]}],
        "confidence": {"score": 0.71, "band": "medium", "basis": "Public professional signals support evaluator inference."},
    }
    return json.dumps(example, indent=2)


def _minimal_inferred_persona_example() -> str:
    example = {
        "inferred_stakeholder_personas": [
            {
                "persona_id": "persona_hiring_manager_1",
                "persona_type": "hiring_manager",
                "role_in_process": "mandate_fit_and_delivery_risk_screen",
                "emitted_because": "coverage_gap_despite_real",
                "trigger_basis": ["technical_ic_role", "hiring_manager_coverage_gap"],
                "coverage_gap": "hiring_manager",
                "public_professional_decision_style": {
                    "evidence_preference": "metrics_and_systems",
                    "risk_posture": "quality_first",
                    "speed_vs_rigor": "balanced",
                    "communication_style": "concise_substantive",
                    "authority_orientation": "credibility_over_title",
                    "technical_vs_business_bias": "technical_first",
                },
                "cv_preference_surface": {
                    "review_objectives": ["Verify hands-on credibility", "Verify production impact"],
                    "preferred_signal_order": ["hands_on_implementation", "production_impact"],
                    "preferred_evidence_types": ["named_systems", "metrics"],
                    "preferred_header_bias": ["execution_first", "low_hype"],
                    "title_match_preference": "moderate",
                    "keyword_bias": "medium",
                    "ai_section_preference": "dedicated_if_core",
                    "preferred_tone": ["clear", "evidence_first"],
                    "evidence_basis": "Inferred from role class and company context.",
                    "confidence": {"score": 0.64, "band": "medium", "basis": "Role-conditioned inferred evaluator persona."},
                },
                "likely_priorities": [{"bullet": "Proof of shipped systems.", "basis": "role class", "source_ids": []}],
                "likely_reject_signals": [{"bullet": "Tool-list CV with weak ownership evidence.", "reason": "role_class_pattern", "source_ids": []}],
                "unresolved_markers": ["No real hiring manager identity resolved."],
                "evidence_basis": "This is inferred from role class, JD, and company context.",
                "sources": [],
                "evidence": [],
                "confidence": {"score": 0.64, "band": "medium", "basis": "Role-conditioned inferred evaluator persona."},
            }
        ],
        "unresolved_markers": [],
        "notes": [],
    }
    return json.dumps(example, indent=2)


def _taxonomy_prompt_context(taxonomy: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = taxonomy or load_job_taxonomy()
    role_nodes = payload.get("primary_role_categories") or {}
    archetype_nodes = payload.get("ideal_candidate_archetypes") or {}
    return {
        "taxonomy_version": str(payload.get("version") or taxonomy_version()),
        "role_categories": {
            slug: {
                "summary": node.get("summary"),
                "likely_archetypes": list((node.get("maps_from") or {}).get("ideal_candidate_archetypes", [])),
            }
            for slug, node in role_nodes.items()
        },
        "ideal_candidate_archetypes": {
            slug: {"description": node.get("description")}
            for slug, node in archetype_nodes.items()
        },
    }


def build_p_jd_judge(*, description: str, deterministic: dict[str, Any]) -> str:
    payload = {"description": description[:8000], "deterministic": deterministic}
    return "\n".join(
        [
            _json_only_contract("P-jd-judge", ["additions", "flags", "confirmations"]),
            "Review the raw job description against the deterministic extraction.",
            "Deterministic fields cannot be silently overwritten.",
            "Output additions only when they include evidence spans.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_jd_extract(
    *,
    title: str,
    company: str,
    deterministic_hints: dict[str, Any],
    structured_sections: dict[str, Any],
    raw_jd_excerpt: str,
    taxonomy_context: dict[str, Any] | None = None,
) -> str:
    taxonomy_payload = _taxonomy_prompt_context(taxonomy_context)
    role_categories = list((taxonomy_payload.get("role_categories") or {}).keys())
    archetypes = list((taxonomy_payload.get("ideal_candidate_archetypes") or {}).keys())
    payload = {
        "title": title,
        "company": company,
        "taxonomy_version": taxonomy_payload["taxonomy_version"],
        "taxonomy_context": taxonomy_payload,
        "deterministic_hints": deterministic_hints,
        "structured_sections": structured_sections,
        "raw_jd_excerpt": raw_jd_excerpt,
        "required_output_keys": [
            "title",
            "company",
            "location",
            "remote_policy",
            "role_category",
            "seniority_level",
            "competency_weights",
            "responsibilities",
            "qualifications",
            "nice_to_haves",
            "technical_skills",
            "soft_skills",
            "implied_pain_points",
            "success_metrics",
            "top_keywords",
            "years_experience_required",
            "education_requirements",
            "ideal_candidate_profile",
            "salary_range",
            "application_url",
            "remote_location_detail",
            "expectations",
            "identity_signals",
            "skill_dimension_profile",
            "team_context",
            "weighting_profiles",
            "operating_signals",
            "ambiguity_signals",
            "language_requirements",
            "company_description",
            "role_description",
            "residual_context",
            "analysis_metadata",
        ],
    }
    _reject_hypotheses_payload("P-jd-extract", payload)
    return "\n".join(
        [
            _json_only_contract(
                "P-jd-extract",
                [
                    "title",
                    "company",
                    "location",
                    "remote_policy",
                    "role_category",
                    "seniority_level",
                    "competency_weights",
                    "responsibilities",
                    "qualifications",
                    "nice_to_haves",
                    "technical_skills",
                    "soft_skills",
                    "implied_pain_points",
                    "success_metrics",
                    "top_keywords",
                    "industry_background",
                    "years_experience_required",
                    "education_requirements",
                    "ideal_candidate_profile",
                    "salary_range",
                    "application_url",
                    "remote_location_detail",
                    "expectations",
                    "identity_signals",
                    "skill_dimension_profile",
                    "team_context",
                    "weighting_profiles",
                    "operating_signals",
                    "ambiguity_signals",
                    "language_requirements",
                    "company_description",
                    "role_description",
                    "residual_context",
                    "analysis_metadata",
                ],
            ),
            "Use the runner-era extraction contract as the quality baseline, then add the richer 4.1.1 contract as first-class output.",
            "Prefer the structured sections first, then use the raw JD excerpt to recover missing context.",
            "Do not silently drop tail-section evidence. Preserve ATS-critical terminology and the exact role-category and archetype labels from the supplied taxonomy context.",
            "Deterministic hints are anchors, not optional output fields. If they disagree with the JD, keep the anchored field values recoverable and preserve ambiguity in ambiguity_signals.",
            "Extraction workflow: 1. Anchor explicit title/company/location/URL/salary facts from deterministic hints and JD text. 2. Extract responsibilities, qualifications, preferred qualifications, keywords, and role taxonomy from structured sections plus raw JD. 3. Populate the main rich-contract fields only when grounded in the JD. 4. Return compact analysis_metadata with no hidden reasoning.",
            "You must extract application_url, salary_range, and language_requirements from the JD text whenever they are present.",
            "company_description, role_description, and residual_context must stay grounded in JD text only.",
            "weighting_profiles.expectation_weights must sum to 100 when present.",
            "weighting_profiles.operating_style_weights must sum to 100 when present.",
            "Role-category disambiguation: titles containing 'leader' or 'lead' are not enough on their own. If the JD emphasizes leading teams, mentoring, and setting technical direction without executive/org-of-org scope, prefer engineering_manager over tech_lead. Reserve tech_lead for clearly hands-on player-coach roles centered on a small stream or technical track.",
            "Responsibilities quality bar: return 5-10 concrete action-object bullets grounded in the JD. Preserve the business or technical object of the action, such as production ML delivery, LLM/NLP use cases, cross-border payments, platform integration, or team leadership. Do not paraphrase into generic leadership slogans.",
            "Qualifications quality bar: separate required qualifications from nice_to_haves. Keep qualifications anchored to explicit requirements or strongly implied must-haves. Do not move preferred or bonus items into qualifications.",
            "Success-metrics quality bar: extract or synthesize grounded outcome statements from the JD's mission, delivery expectations, and business context. Prefer production outcomes, adoption outcomes, integration outcomes, scale outcomes, and organizational outcomes over generic statements like 'do well' or 'communicate effectively'.",
            "Keyword quality bar: top_keywords must be ranked ATS terms. Prefer exact JD wording and exact role/domain/tool phrases. Include literal title variants, domain terms, and production/architecture terms when present. Avoid invented synonyms that are not grounded in the JD.",
            "For this iteration, implied_pain_points is intentionally deferred. Return implied_pain_points as an empty array unless the plan is changed later.",
            "Strict nested-shape rules: remote_location_detail, expectations, identity_signals, skill_dimension_profile, team_context, weighting_profiles, language_requirements, and analysis_metadata MUST be JSON objects, never strings or arrays.",
            "Anti-pattern bans: do not return remote_location_detail as a sentence, do not return expectations as a flat list, do not return team_context as a sentence, do not return language_requirements as a list, and do not return residual_context as an array.",
            "weighting_profiles.expectation_weights must use exactly these keys: delivery, communication, leadership, collaboration, strategic_scope.",
            "weighting_profiles.operating_style_weights must use exactly these keys: autonomy, ambiguity, pace, process_rigor, stakeholder_exposure.",
            "Example valid shapes: remote_location_detail={\"remote_anywhere\": false, \"remote_regions\": [\"EU\"], \"timezone_expectations\": [], \"travel_expectation\": null, \"onsite_expectation\": null, \"location_constraints\": [\"Spain only\"], \"relocation_support\": null, \"primary_locations\": [\"Spain\"], \"secondary_locations\": [], \"geo_scope\": \"country\", \"work_authorization_notes\": null}.",
            "Example valid expectations shape: expectations={\"explicit_outcomes\": [\"Ship ML features to production\"], \"delivery_expectations\": [\"Own roadmap execution\"], \"leadership_expectations\": [\"Mentor engineers\"], \"communication_expectations\": [\"Communicate clearly in English\"], \"collaboration_expectations\": [\"Work with product\"], \"first_90_day_expectations\": []}.",
            "Example valid team_context shape: team_context={\"team_size\": null, \"reporting_to\": null, \"org_scope\": \"AI engineering\", \"management_scope\": \"player-coach\"}.",
            "Example valid language_requirements shape: language_requirements={\"required_languages\": [\"English\"], \"preferred_languages\": [], \"fluency_expectations\": [\"Strong communication in English\"], \"language_notes\": null}.",
            "Example valid residual_context shape: residual_context=\"Global fintech role. Multiple hires. 3-stage interview process.\" or null.",
            JD_EXTRACTION_SYSTEM_PROMPT,
            f"taxonomy_version={taxonomy_payload['taxonomy_version']}",
            f"allowed_role_categories={', '.join(role_categories)}",
            f"allowed_candidate_archetypes={', '.join(archetypes)}",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_classify(
    *,
    jd_facts: dict[str, Any],
    taxonomy: dict[str, Any] | None = None,
    pre_score: list[dict[str, Any]] | None = None,
    section_context: dict[str, Any] | None = None,
) -> str:
    taxonomy_payload = taxonomy or load_job_taxonomy()
    payload = {
        "taxonomy_version": str(taxonomy_payload.get("version") or taxonomy_version()),
        "jd_facts": jd_facts,
        "pre_score": pre_score or [],
        "section_context": section_context or {},
        "taxonomy": {
            "primary_role_categories": (taxonomy_payload.get("primary_role_categories") or {}),
            "disambiguation_rules": taxonomy_payload.get("disambiguation_rules") or [],
            "ai_taxonomy": taxonomy_payload.get("ai_taxonomy") or {},
        },
    }
    _reject_hypotheses_payload("P-classify", payload)
    return "\n".join(
        [
            _json_only_contract(
                "P-classify",
                [
                    "primary_role_category",
                    "secondary_role_categories",
                    "search_profiles",
                    "selector_profiles",
                    "tone_family",
                    "confidence",
                    "ambiguity_score",
                    "reason_codes",
                    "evidence",
                    "jd_facts_agreement",
                    "pre_score",
                    "decision_path",
                    "ai_taxonomy",
                    "ai_relevance",
                ],
            ),
            "Classify the role using the supplied canonical taxonomy only.",
            "Use the deterministic pre-score summary as the starting point. Override it only when the JD evidence clearly supports a different category.",
            "This prompt is for ambiguous or disagreement cases only. Do not invent new role categories, archetypes, search profiles, selector profiles, tone families, AI specializations, or scope tags.",
            "Forbidden inputs: job_hypotheses and research_enrichment. Use jd_facts and section-aware JD excerpts only.",
            "Return JSON only. No markdown. No commentary. No hidden chain-of-thought.",
            "ai_taxonomy must include: is_ai_job, primary_specialization, secondary_specializations, intensity, scope_tags, legacy_ai_categories, rationale.",
            "confidence may be either a compact band string (high|medium|low) or a numeric 0.0-1.0 score if you need finer calibration.",
            "evidence must stay compact and cite only title/responsibility/qualification/keyword/archetype evidence present in the payload.",
            "Preferred evidence keys are title_matches, responsibility_matches, qualification_matches, keyword_matches, archetype_matches. If you emit title/responsibilities/qualifications/keywords/archetype aliases, they will be normalized.",
            "jd_facts_agreement should preferably be {agrees, jd_facts_role_category?, reason?}. If you emit structured booleans like overall/title/role_category/seniority_level, they must all refer only to agreement with jd_facts evidence.",
            "decision_path may be a single concise string or a short ordered list of decision steps.",
            f"taxonomy_version={payload['taxonomy_version']}",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_research(*, jd_facts: dict[str, Any], identity: dict[str, Any]) -> str:
    payload = {"jd_facts": jd_facts, "identity": identity}
    return "\n".join(
        [
            _json_only_contract("P-research", ["status", "company_profile", "sources", "notes"]),
            "Synthesize public company and role research using the supplied evidence only.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_application_url(*, candidates: list[str], job_identity: dict[str, Any]) -> str:
    payload = {"candidates": candidates, "job_identity": job_identity}
    return "\n".join(
        [
            _json_only_contract("P-application-url", ["application_url", "status", "reason"]),
            "Choose the best direct apply URL from ambiguous candidates.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_application_surface(
    *,
    title: str,
    company: str,
    location: str | None,
    job_url: str | None,
    ats_domains: list[str],
    blocked_domains: list[str],
    transport_preamble: str,
) -> str:
    payload = {
        "title": title,
        "company": company,
        "location": location,
        "job_url": job_url,
        "ats_domain_allowlist": ats_domains,
        "blocked_domains": blocked_domains,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(
                PROMPT_VERSIONS["application_surface"],
                [
                    "job_url",
                    "canonical_application_url",
                    "redirect_chain",
                    "last_verified_at",
                    "final_http_status",
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
                    "duplicate_signal",
                    "geo_normalization",
                    "apply_instructions",
                    "apply_caveats",
                    "sources",
                    "evidence",
                    "confidence",
                    "status",
                ],
            ),
            "You are resolving the authoritative application URL and portal metadata for a specific job posting.",
            "Do not invent URLs, dates, or redirects. Never emit a URL for a different company. Constructed ATS probe URLs are candidates only until verified.",
            "Preserve useful partial outcomes. If the exact job-specific deep link is unavailable but a verified employer jobs portal is directly observed, emit status=\"partial\" and keep that employer portal URL.",
            "Shape rules: `ui_actionability` must be one of ready/caution/blocked/unknown. `form_fetch_status` must be one of fetched/blocked/not_attempted. `apply_instructions` may be either a string or a short list of strings.",
            "If the result is unresolved, it must still preserve observed evidence, candidate URLs, portal hints, and the reason the URL could not be verified.",
            "Search discipline: start with official-employer discovery queries using the exact company name plus jobs/careers/apply terms, then exact title + company queries. Prefer company-owned and ATS-owned results before any third-party job boards.",
            "Do not spend more than one query on tertiary job boards unless they expose a directly observed employer or ATS destination. If only tertiary mirrors are found, keep the result unresolved-but-useful rather than treating them as canonical.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_research_company(
    *,
    company: str,
    name_variations: list[str],
    company_url: str | None,
    candidate_domains: list[str],
    jd_excerpt: str,
    classification: dict[str, Any],
    application_profile: dict[str, Any],
    transport_preamble: str,
) -> str:
    payload = {
        "company_name": company,
        "company_name_variations": name_variations,
        "known_company_url": company_url,
        "candidate_domain_hints": candidate_domains,
        "jd_excerpt": jd_excerpt[:2000],
        "classification": classification,
        "application_profile": application_profile,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(
                PROMPT_VERSIONS["research_company"],
                [
                    "summary",
                    "url",
                    "signals",
                    "canonical_name",
                    "canonical_domain",
                    "canonical_url",
                    "identity_confidence",
                    "identity_basis",
                    "identity_detail",
                    "company_type",
                    "mission_summary",
                    "mission_detail",
                    "product_summary",
                    "product_detail",
                    "business_model",
                    "business_model_detail",
                    "customers_and_market",
                    "scale_signals",
                    "funding_signals",
                    "ai_data_platform_maturity",
                    "team_org_signals",
                    "recent_signals",
                    "role_relevant_signals",
                    "signals_rich",
                    "recent_signals_rich",
                    "role_relevant_signals_rich",
                    "sources",
                    "evidence",
                    "confidence",
                    "status",
                ],
            ),
            "Resolve canonical company identity before emitting company signals. Do not guess domains or URLs from slugs alone.",
            "Richer grounded output is preferred. If a field naturally comes back as an evidence-bearing object, include both the compact alias and the richer *_detail or *_rich companion field.",
            "Do not inspect local files, prompts, tests, or use shell commands to discover the schema. Use only the payload above and allowed web research.",
            "Use this minimal shape as a guide and emit JSON directly with no planning chatter:",
            _minimal_research_company_example(),
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_research_role(
    *,
    title: str,
    company: str,
    jd_text: str,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    company_profile: dict[str, Any],
    application_profile: dict[str, Any],
    transport_preamble: str,
) -> str:
    payload = {
        "title": title,
        "company": company,
        "jd_text": jd_text[:3000],
        "jd_facts": jd_facts,
        "classification": classification,
        "company_profile": company_profile,
        "application_profile": application_profile,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(
                PROMPT_VERSIONS["research_role"],
                [
                    "role_summary",
                    "summary",
                    "summary_detail",
                    "role_summary_detail",
                    "mandate",
                    "business_impact",
                    "why_now",
                    "why_now_detail",
                    "success_metrics",
                    "collaboration_map",
                    "reporting_line",
                    "org_placement",
                    "interview_themes",
                    "evaluation_signals",
                    "risk_landscape",
                    "company_context_alignment",
                    "company_context_alignment_detail",
                    "sources",
                    "evidence",
                    "confidence",
                    "status",
                ],
            ),
            "Build role intelligence from the JD plus verified public company context. Reporting lines and org placement must stay unknown unless explicitly evidenced.",
            "If summary-style fields naturally resolve to structured evidence-bearing objects, emit both the compact text alias and the *_detail companion field.",
            "Do not inspect local files, prompts, tests, or use shell commands to discover the schema. Use only the payload above and allowed web research.",
            "Use this minimal shape as a guide and emit JSON directly with no planning chatter:",
            _minimal_research_role_example(),
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_research_application_merge(
    *,
    application_surface_artifact: dict[str, Any],
    job_document_hints: dict[str, Any],
    canonical_domain: str | None,
) -> str:
    payload = {
        "application_surface_artifact": application_surface_artifact,
        "job_document_hints": job_document_hints,
        "company_profile": {"canonical_domain": canonical_domain},
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            _json_only_contract(PROMPT_VERSIONS["research_application_merge"], ["application_profile"]),
            "This is a merge step, not a refetch step. Reconcile verified inputs only. Do not invent new URLs or dates.",
            "If useful merge context needs to be preserved, place it under additional top-level debug/context blocks rather than dropping it. The persisted canonical application_profile must remain directly usable on its own.",
            "Do not inspect local files, prompts, tests, or use shell commands to discover the schema. Use only the inputs above and emit JSON directly with no planning chatter.",
            "Use this minimal shape as a guide:",
            _minimal_research_application_merge_example(),
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_stakeholder_discovery(
    *,
    title: str,
    company: str,
    company_profile: dict[str, Any],
    role_profile: dict[str, Any],
    application_profile: dict[str, Any],
    jd_excerpt: str,
    transport_preamble: str,
) -> str:
    payload = {
        "title": title,
        "company": company,
        "company_profile": company_profile,
        "role_profile": role_profile,
        "application_profile": application_profile,
        "jd_excerpt": jd_excerpt[:1500],
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(PROMPT_VERSIONS["stakeholder_discovery"], ["stakeholder_intelligence"]),
            "Discover stakeholders using the identity ladder only. No constructed LinkedIn URLs. Never merge ambiguous people into one record.",
            "Field aliases are allowed when semantically equivalent: title/current_title, company/current_company, relationship/relationship_to_role.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_stakeholder_profile(
    *,
    stakeholder_record: dict[str, Any],
    role_profile: dict[str, Any],
    company_profile: dict[str, Any],
    public_posts_fetched: list[dict[str, Any]],
    transport_preamble: str,
) -> str:
    payload = {
        "stakeholder_record": stakeholder_record,
        "role_profile": role_profile,
        "company_profile": company_profile,
        "public_posts_fetched": public_posts_fetched[:5],
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(
                PROMPT_VERSIONS["stakeholder_profile"],
                [
                    "stakeholder_ref",
                    "public_professional_background",
                    "public_communication_signals",
                    "working_style_signals",
                    "likely_priorities",
                    "relationship_to_role",
                    "evidence_basis",
                    "unresolved_markers",
                    "sources",
                    "evidence",
                    "confidence",
                ],
            ),
            "Only summarize public professional signals. No speculative psychology, no private motives, no protected-trait inference.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_stakeholder_outreach_guidance(
    *,
    stakeholder_record: dict[str, Any],
    stakeholder_profile: dict[str, Any],
    role_profile: dict[str, Any],
    company_profile: dict[str, Any],
    jd_facts: dict[str, Any],
) -> str:
    payload = {
        "stakeholder_record": stakeholder_record,
        "stakeholder_profile": stakeholder_profile,
        "role_profile": role_profile,
        "company_profile": company_profile,
        "jd_facts": jd_facts,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            _json_only_contract(
                PROMPT_VERSIONS["stakeholder_outreach_guidance"],
                [
                    "stakeholder_ref",
                    "stakeholder_type",
                    "likely_priorities",
                    "initial_outreach_guidance",
                    "avoid_points",
                    "evidence_basis",
                    "confidence",
                    "status",
                ],
            ),
            "Produce guidance only, not outreach copy. Guidance must be evidence-grounded, stakeholder-type-specific, and non-manipulative.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_stakeholder_discovery_v2(
    *,
    canonical_company_identity: dict[str, Any],
    target_role_brief: dict[str, Any],
    evaluator_coverage_target: list[str],
    seed_stakeholders: list[dict[str, Any]],
    company_profile_excerpt: dict[str, Any],
    role_profile_excerpt: dict[str, Any],
    application_profile_excerpt: dict[str, Any],
    jd_excerpt: str,
    search_constraints: dict[str, Any],
    transport_preamble: str,
    job_id: str,
) -> str:
    payload = {
        "job_id": job_id,
        "target_role_brief": target_role_brief,
        "canonical_company_identity": canonical_company_identity,
        "evaluator_coverage_target": evaluator_coverage_target,
        "seed_stakeholders": seed_stakeholders,
        "company_profile_excerpt": company_profile_excerpt,
        "role_profile_excerpt": role_profile_excerpt,
        "application_profile_excerpt": application_profile_excerpt,
        "jd_excerpt": jd_excerpt[:1800],
        "search_constraints": search_constraints,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(
                PROMPT_VERSIONS["stakeholder_surface_discovery"],
                ["stakeholder_intelligence", "search_journal", "unresolved_markers", "notes"],
            ),
            "Resolve real public-professional stakeholders using the identity ladder only. Truth beats coverage.",
            "Do not construct LinkedIn URLs or infer names from URL slugs. Do not merge ambiguous profiles.",
            "A real stakeholder must match canonical company identity and role/function context simultaneously.",
            "Medium/high identity confidence requires a direct signal class or two distinct converging matched_signal_classes.",
            "Low-confidence or ambiguous candidates belong in search_journal, not stakeholder_intelligence.",
            "search_journal.outcome must be exactly one of: hit, miss, ambiguous, rejected_fabrication.",
            "If a search found relevant company pages but no named people, use outcome=\"miss\" and explain that in notes instead of inventing a new outcome value.",
            "The output stakeholder_intelligence records must stay discovery-only. Do not emit evaluator personas here.",
            "Use this minimal shape as a guide and emit JSON directly:",
            json.dumps(
                {
                    "stakeholder_intelligence": [
                        {
                            "stakeholder_type": "recruiter",
                            "identity_status": "resolved",
                            "identity_confidence": {"score": 0.83, "band": "high", "basis": "Official company site plus public profile."},
                            "identity_basis": "Official team page and public professional profile.",
                            "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                            "candidate_rank": 1,
                            "name": "Jane Doe",
                            "current_title": "Senior Technical Recruiter",
                            "current_company": "Example AI",
                            "profile_url": "https://www.linkedin.com/in/jane-doe-example",
                            "source_trail": ["src_team_page", "src_profile"],
                            "function": "recruiting",
                            "seniority": "senior",
                            "relationship_to_role": "recruiter",
                            "likely_influence": "screening_and_process_control",
                            "evidence_basis": "Identity only at discovery stage.",
                            "confidence": {"score": 0.83, "band": "high", "basis": "Identity resolution only."},
                            "unresolved_markers": [],
                            "sources": [{"source_id": "src_team_page", "url": "https://example.ai/team", "source_type": "company_site", "fetched_at": "2026-04-21", "trust_tier": "primary"}],
                            "evidence": [{"claim": "Jane Doe is listed as a recruiter.", "source_ids": ["src_team_page"]}],
                        }
                    ],
                    "search_journal": [{"step": "discovery", "query": "site:example.ai recruiter", "intent": "find_recruiter", "source_type": "company_site", "outcome": "hit", "source_ids": ["src_team_page"], "notes": ""}],
                    "unresolved_markers": [],
                    "notes": [],
                },
                indent=2,
            ),
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_stakeholder_profile_v2(
    *,
    stakeholder_record: dict[str, Any],
    target_role_brief: dict[str, Any],
    company_profile_excerpt: dict[str, Any],
    role_profile_excerpt: dict[str, Any],
    application_profile_excerpt: dict[str, Any],
    jd_excerpt: str,
    public_posts_fetched: list[dict[str, Any]],
    coverage_context: dict[str, Any],
    transport_preamble: str,
) -> str:
    payload = {
        "stakeholder_record": stakeholder_record,
        "target_role_brief": target_role_brief,
        "company_profile_excerpt": company_profile_excerpt,
        "role_profile_excerpt": role_profile_excerpt,
        "application_profile_excerpt": application_profile_excerpt,
        "jd_excerpt": jd_excerpt[:1400],
        "public_posts_fetched": public_posts_fetched[:5],
        "coverage_context": coverage_context,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            transport_preamble,
            _json_only_contract(
                PROMPT_VERSIONS["stakeholder_surface_profile"],
                [
                    "stakeholder_ref",
                    "stakeholder_type",
                    "role_in_process",
                    "public_professional_decision_style",
                    "cv_preference_surface",
                    "likely_priorities",
                    "likely_reject_signals",
                    "unresolved_markers",
                    "sources",
                    "evidence",
                    "confidence",
                ],
            ),
            "Summarize only public-professional evidence and evaluator-style inference for this already-resolved stakeholder.",
            "Do not emit exact title text, exact header text, exact summary text, or CV section ids. preferred_signal_order must use abstract signal categories only.",
            "Mark fields unresolved rather than forcing a view when evidence is weak.",
            "Do not inspect local files, prompts, tests, or use shell commands. Use only the payload above and allowed web research.",
            "Use this minimal shape as a guide and emit JSON directly:",
            _minimal_stakeholder_evaluation_profile_example(),
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_inferred_stakeholder_personas_v1(
    *,
    target_role_brief: dict[str, Any],
    canonical_company_identity: dict[str, Any],
    company_profile_excerpt: dict[str, Any],
    role_profile_excerpt: dict[str, Any],
    application_profile_excerpt: dict[str, Any],
    classification_excerpt: dict[str, Any],
    jd_excerpt: str,
    real_stakeholder_summaries: list[dict[str, Any]],
    evaluator_coverage_target: list[str],
    missing_coverage_types: list[str],
    emission_mode: str,
) -> str:
    payload = {
        "target_role_brief": target_role_brief,
        "canonical_company_identity": canonical_company_identity,
        "company_profile_excerpt": company_profile_excerpt,
        "role_profile_excerpt": role_profile_excerpt,
        "application_profile_excerpt": application_profile_excerpt,
        "classification_excerpt": classification_excerpt,
        "jd_excerpt": jd_excerpt[:1400],
        "real_stakeholder_summaries": real_stakeholder_summaries,
        "evaluator_coverage_target": evaluator_coverage_target,
        "missing_coverage_types": missing_coverage_types,
        "emission_mode": emission_mode,
    }
    return "\n".join(
        [
            SHARED_CONTRACT_HEADER,
            _json_only_contract(
                PROMPT_VERSIONS["inferred_stakeholder_personas"],
                ["inferred_stakeholder_personas", "unresolved_markers", "notes"],
            ),
            "Emit personas, not people. Never emit a name, profile_url, current_title, or current_company.",
            'Every persona evidence_basis MUST contain the literal word "inferred".',
            "Do not model private motives, protected traits, or personal psychology.",
            "Persona confidence may not exceed medium.",
            "cv_preference_surface remains evaluator signal, not CV instruction. Do not emit CV section ids or exact copy.",
            "Use this minimal shape as a guide and emit JSON directly:",
            _minimal_inferred_persona_example(),
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_role_model(
    *,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research_enrichment: dict[str, Any],
    application_surface: dict[str, Any],
) -> str:
    payload = {
        "jd_facts": jd_facts,
        "classification": classification,
        "research_enrichment": research_enrichment,
        "application_surface": application_surface,
    }
    return "\n".join(
        [
            _json_only_contract(
                "P-role-model",
                ["semantic_role_model", "company_model", "qualifications", "inferences"],
            ),
            "Produce evidence-backed role and company inferences. Do not invent hypotheses.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_hypotheses(
    *,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research_enrichment: dict[str, Any],
    application_surface: dict[str, Any],
) -> str:
    payload = {
        "jd_facts": jd_facts,
        "classification": classification,
        "research_enrichment": research_enrichment,
        "application_surface": application_surface,
    }
    return "\n".join(
        [
            _json_only_contract("P-hypotheses", ["hypotheses"]),
            "Produce speculative low-confidence hypotheses only. These are never used for prose generation.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_cv_guidelines(
    *,
    jd_facts: dict[str, Any],
    job_inference: dict[str, Any],
    research_enrichment: dict[str, Any],
) -> str:
    payload = {
        "jd_facts": jd_facts,
        "job_inference": job_inference,
        "research_enrichment": research_enrichment,
    }
    _reject_hypotheses_payload("P-cv-guidelines", payload)
    return "\n".join(
        [
            _json_only_contract(
                "P-cv-guidelines",
                [
                    "title_guidance",
                    "identity_guidance",
                    "bullet_theme_guidance",
                    "ats_keyword_guidance",
                    "cover_letter_expectations",
                ],
            ),
            "Produce guidance only. No prose CV output. Every block must include evidence_refs.",
            json.dumps(payload, indent=2, default=str),
        ]
    )
