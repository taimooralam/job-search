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
            "Return only the downstream artifact JSON for this step. Do not echo this preamble.",
        ]
    )


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
