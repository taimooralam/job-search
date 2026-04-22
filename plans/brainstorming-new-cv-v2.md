# Stage 1 Brainstorm — Job Blueprint (JD + Public Research → Master Object)

Author: Principal architect revision.
Date: 2026-04-19
Status: Stage 1 design. Stages 2 (candidate modeling) and 3 (match + generation) are explicitly out of scope and tracked separately.
Constraint: VPS pipeline, Codex/OpenAI-accessible models only. Web research is a capability flag.

## 1. Purpose & Non-Goals

**Purpose.** For each job, produce **one MongoDB master object** — `job_blueprint` — that an expert recruiter would build by studying only the JD and public information about the company/role, before ever meeting the candidate. The blueprint captures:

- what the role actually is (facts)
- what the role almost certainly implies (inferences)
- what the hiring side probably wants but didn't say (hypotheses, isolated)
- how the job is likely applied to in practice (application surface: job URL, direct application URL if resolvable, portal family, friction signals)
- what the *ideal* CV would look like for this role — title, identity, bullets themes, ATS keywords, skills, challenges, visa/comp framing — **as guidelines**, not as written prose
- what a generic cover letter and audience-specific cover letters should emphasize — **as expectations only**, not as written prose

**In scope.**
- JD text, pre-enrichment outputs already in MongoDB, optional company URL/careers page.
- Public internet research (gated by capability flag, company-identity resolvability, and budget/depth constraints).
- Deterministic extraction, LLM inference, LLM hypothesis extraction, LLM-synthesised CV guidelines.

**Out of scope (explicitly).**
- The candidate's master CV, evidence store, lantern skills, past annotations.
- Any matching between JD and the candidate.
- Any bullet, headline, or section writing.
- Any grounding against candidate history (there is no candidate side at this stage).
- ATS *output* formatting — Stage 1 produces ATS *guidance* only.

The blueprint is recruiter-perspective only. It is the same artifact whether the candidate is Taimoor or anyone else.

## 2. Runtime Assumptions

- Codex CLI with ChatGPT-plan auth is the production surface today. Not the OpenAI API. Do not assume Responses API, `web_search` tool, Batch API, structured outputs by schema, or prompt-caching metrics.
- OpenAI API may be added later. Model routing is a config mapping, not hardcoded SKUs.
- Web research availability is a capability flag, not a default:
  - `WEB_RESEARCH_ENABLED` (bool)
  - `RESEARCH_BUDGET_USD` (per-run ceiling)
  - `RESEARCH_DEPTH` (`none | shallow | deep`)
- If web research is unavailable, S4 is skipped silently; no claim may depend on it.

## 3. Input Contracts

Stage 1 reads only:

- `jobs.<collection>` MongoDB document: raw JD text, company fields, pre-enrichment outputs, tier if already assigned.
- Existing URL fields if present: `jobUrl`, `job_url`, `application_url`.
- Optional: recruiter message text, company URL, careers page URL.
- Public internet (via S4, gated).

Stage 1 does **not** read:

- `master-cv.md`
- `lantern_skills.json`
- Any candidate artifact
- Any prior CV run

Stage 1 writes only into its own collections (§6). No upstream mutation.

## 4. Confidence Model & Structural Separation

Labels alone are decoration. An LLM given a `hypotheses` block will absorb it regardless of any `allowed_in_cv: false` flag. The safeguard must be **structural, not annotative**.

### 4.1 Three separate documents

| Document | Holds | Confidence levels | Consumers (now and in future stages) |
|---|---|---|---|
| `jd_facts` | deterministic facts from JD text | fact | everything downstream |
| `job_inference` | high- and medium-confidence inferences with evidence spans | high, medium | everything downstream |
| `job_hypotheses` | speculative, unverifiable signals (hiring-manager profile, recruiter profile, hidden expectations) | low | future S-rerank selection only; **never** a generation prompt |

Generation prompts (Stage 3, future) will be assembled from a whitelist that contains `jd_facts` and `job_inference` but **not** `job_hypotheses`. At Stage 1 there are no generation prompts, so the isolation is pre-emptive discipline for later.

### 4.2 Hypotheses feed selection, not wording

In Stages 2/3, hypotheses can influence **which** of the candidate's real achievements to surface (weighting signal for a reranker). They cannot influence **the prose** of any headline, profile, bullet, tagline, or skills entry. Stage 1 simply produces and stores them with source reasoning.

### 4.3 Per-field structure

Inside `job_inference`:
```
{ field, value, confidence: high|medium, evidence_spans[{source, locator, quote}] }
```

Inside `job_hypotheses`:
```
{ field, value, confidence: low, reasoning, source_hints[] }
```

No `allowed_in_cv` flag anywhere — isolation is the enforcement.

## 5. Pipeline Stages

Each stage: idempotent, content-hash keyed, independently retryable.

### S0 — Capability Gate (Python, no LLM)
Resolves budget, research flags, company-identity inputs, and run config.

### S1 — Deterministic-First JD Normalize, LLM-as-Judge Second

Two passes. Regex alone loses information when facts are buried in prose. LLM alone hallucinates. The combination: deterministic runs first for high-precision capture, then the LLM reviews the raw JD against the deterministic output to add what was missed and flag likely errors — but cannot silently overwrite.

#### S1a — Deterministic extraction (Python, no LLM)
Regex + lexicon → `jd_facts.deterministic`. High precision, potentially low recall. Every extracted field carries a `locator` (character span in raw JD) so downstream stages can verify provenance.

Extracts: company, title_raw + title_normalized, seniority, location, remote policy, visa statement, salary range, must-haves, nice-to-haves, explicit hard/soft skills, explicit AI skills, explicit architecture signals, explicit challenge statements, years required, acronym table, keyword inventory, reporting line, existing `jobUrl` / `application_url`.

Also builds `jd_guidance_inputs` from explicit JD language:

- `hard_skills_guidance_input`
- `soft_skills_guidance_input`
- `ai_skills_guidance_input`
- `architecture_guidance_input`
- `challenges_guidance_input`

These are still JD-side extracts, not synthesized guidance. S5 refines them into recruiter-facing guidance objects.

#### S1b — LLM-as-Judge fill and flag
Input: raw JD + `jd_facts.deterministic`. Output: structured diff with three lists:

```
additions[]:   { field, value, evidence_span{start,end,quote}, confidence }
flags[]:       { field, deterministic_value, proposed_value,
                 severity: info|warn|blocking, reasoning, evidence_span, confidence }
confirmations: { field: bool }   # LLM confirms deterministic value is correct
```

Rules for merging into final `jd_facts`:

1. **Deterministic wins ties.** If regex extracted a value with a locator, the LLM cannot overwrite it. A disagreement becomes a `flag`, not a replacement.
2. **Additions are allowed** only if `confidence ≥ high`, `evidence_span` is present and non-empty, and the `field` is not already populated in deterministic output. If the LLM proposes a different value for a deterministic field, it becomes a `flag`, never an addition.
3. **No span, no addition.** An LLM addition without a character span in the raw JD is rejected.
4. **Flags are surfaced, not applied.** `flags[]` is persisted for human review and can block downstream stages only if `severity: blocking` — e.g., LLM says the deterministic title is flat-out wrong with a quoted span. Blocking flags mark the run as `needs_review`, do not auto-apply.
5. **Confirmations reduce ambiguity_score downstream**, nothing more.

Final `jd_facts` shape:
```
deterministic:   { ... regex extracts with locators }
llm_additions:   [ { field, value, evidence_span, confidence } ]
llm_flags:       [ { field, deterministic_value, proposed_value,
                     severity, evidence_span, reasoning } ]
merged_view:     { ... deterministic + accepted additions, read by S2+ }
provenance:      { per-field source: "deterministic" | "llm_addition" }
```

Downstream stages read `merged_view` by default. The `llm_flags` list is visible in observability and can be surfaced in a review UI. This keeps the "deterministic is authoritative" guarantee while closing the recall gap that pure regex leaves open.

Cost: one LLM call per job, structured output, typically <1k tokens in, <500 out.

### S2 — Classification
One structured call: `{primary_role_category, secondary_role_categories[], search_profiles[], selector_profiles[], tone_family, taxonomy_version, ambiguity_score}`. Classification is driven by one canonical taxonomy file shared across Stage 1 and the selector/search skills. This stage classifies the role only; company research still happens later in S4.

### S2a — Canonical Job Taxonomy (Single Source Of Truth)

Stage 1 must stop inventing yet another role taxonomy. `P-classify` should read from one canonical source-of-truth artifact: `data/job_archetypes.yaml`. The same file should define the labels used by Stage 1, selector/search skills, and any downstream evaluation or reporting.

This taxonomy should unify the currently scattered vocabularies:

- from `top-jobs`: `tech-lead`, `architect`, `staff-principal`, `head-director`, `engineering-manager`
- from `scout-jobs`: `ai`, `engineering`, `leadership`, `architect`
- from JD extraction / preenrich: `engineering_manager`, `staff_principal_engineer`, `director_of_engineering`, `head_of_engineering`, `vp_engineering`, `cto`, `tech_lead`, `senior_engineer`
- from existing evaluation/tone logic: `executive`, `architect`, `hands_on`, `player_coach`
- from ideal-candidate archetypes: `technical_architect`, `people_leader`, `execution_driver`, `strategic_visionary`, `domain_expert`, `builder_founder`, `process_champion`, `hybrid_technical_leader`

`apply-jobs` does **not** contribute role archetypes. Its relevant taxonomy is separate: application `portal_family` derived from job/apply URLs and playbooks. Keep that as a parallel taxonomy, not mixed into role identity.

`P-classify` should become the single classifier that outputs the canonical labels, and all downstream consumers should map from this source-of-truth file rather than maintaining separate regex families.

### S2b — Canonical Taxonomy Shape

The canonical taxonomy should be multi-axis, not a single overloaded label:

- `primary_role_category` (exactly one):
  - `senior_engineer`
  - `tech_lead`
  - `staff_principal_engineer`
  - `engineering_manager`
  - `director_of_engineering`
  - `head_of_engineering`
  - `vp_engineering`
  - `cto`
- `secondary_role_categories[]` (zero or more, same enum):
  - used for hybrids like a hands-on EM leaning toward `tech_lead`
- `search_profiles[]` from scout search vocabulary:
  - `ai_core`
  - `ai_leadership`
  - `ai_senior_ic`
  - `ai_architect`
- `selector_profiles[]` from top-jobs vocabulary:
  - `tech-lead`
  - `architect`
  - `staff-principal`
  - `head-director`
  - `engineering-manager`
- `tone_family` (exactly one):
  - `hands_on`
  - `player_coach`
  - `architect`
  - `executive`
- `ideal_candidate_archetype` remains a separate downstream field:
  - `technical_architect`
  - `people_leader`
  - `execution_driver`
  - `strategic_visionary`
  - `domain_expert`
  - `builder_founder`
  - `process_champion`
  - `hybrid_technical_leader`
- `portal_family` is a separate application-surface taxonomy, not a role taxonomy:
  - `greenhouse`
  - `lever`
  - `workday`
  - `smartrecruiters`
  - `ashby`
  - `bamboohr`
  - `linkedin_easy_apply`
  - `indeed`
  - `join`
  - `personio`
  - `recruitee`
  - `breezy`
  - `teamtailor`
  - `workable`
  - `applytojob`
  - `custom_unknown`

Design rule: `primary_role_category` answers "what job is this?", `tone_family` answers "what communication posture fits this role?", `search_profiles[]` and `selector_profiles[]` preserve compatibility with existing search/ranking systems, and `portal_family` answers "how is this role applied to?" Mixing these axes is what created the current taxonomy drift.

### S3 — Semantic Role Model → `job_inference`
Produces the semantic understanding of the role and company. Inferences only, each with evidence spans. Dimensions produced:

**Company dimensions**
- industry, sub-industry
- mission, product/service surface, customer types
- business model and revenue motion if public
- funding / company trajectory if public
- company stage, scale, operating model
- product complexity proxy
- regulated-domain pressure (public sources only)
- AI adoption maturity signals (from JD + careers page)
- architecture maturity signals
- public engineering culture signals
- public tech-stack signals
- recent news signals relevant to the role
- public hiring-process signals if available

**Role dimensions**
- role mandate
- expected success metrics
- expected architecture depth
- expected AI depth
- expected business partnership level
- expected delivery maturity
- ideal candidate archetype
- likely screening themes
- likely stakeholder surface
- reporting and scope inferences
- communication surface expectations (exec-facing, recruiter-facing, peer-facing, cross-functional)
- likely document asks beyond CV (generic cover letter, hiring-manager note, recruiter note, peer-colleague note)

**Qualifications**
- consolidated must-have list (fact-source → merged with inferred must-haves)
- consolidated nice-to-have list
- implicit qualifications (inferred, confidence-scored)

**Skills**
- technical skills (explicit + inferred, separated)
- soft skills (explicit + inferred)
- AI skills (depth-tiered: applied, architect, research)
- architecture skills (depth-tiered: service, platform, enterprise)
- leadership scope and type
- guidance-seed expansion for hard, soft, AI, architecture, and challenge dimensions

**Domain knowledge**
- industry knowledge likely required
- domain-specific regulations or frameworks

**Keywords**
- ATS must-include keywords (derived from JD, not speculative)
- ATS should-include keywords (related terminology)
- acronym policy (expansion pairs)

**Application surface**
- existing job URL
- direct application URL if resolvable
- portal family (Greenhouse, Lever, Workday, Ashby, SmartRecruiters, LinkedIn Easy Apply, etc.)
- whether the current URL is already the direct apply URL
- application friction signals (login wall likely, multi-step form likely, direct-apply vs redirect)
- posting freshness / closure risk if public signals exist

All fields carry confidence and evidence spans. No speculation lives here.

### S3a — Dimension Audit

The current dimensions are mostly right, but they need to be split by value density:

- **High-yield and must keep**: company model, role mandate, qualifications, explicit/inferred skills, ATS keywords, architecture depth, AI depth, success metrics, application surface
- **High-yield and currently under-specified**: mission/product surface, customer types, business model, funding/trajectory, public engineering culture, public tech stack, document expectations, portal family, application URL availability, challenge statements, communication surface, hiring-process signals
- **Medium-yield and keep only when evidenced**: domain regulations, stakeholder map, public leadership messaging, recent news likely to affect role urgency
- **Low-yield and keep isolated only as hypotheses**: psych profiles, subtle expectations, political complexity, stretch zones, danger zones

The objective is not to maximize the number of dimensions. It is to maximize job signal density with fields that are evidencable, reusable, and likely to change downstream CV decisions.

### S3b — Hypothesis Extraction → `job_hypotheses`
Separate prompt, separate output document. Prompt explicitly instructs: "these will be stored as speculation only; do not invent facts." Dimensions:

- nuanced pain points not stated explicitly
- subtle expectations not visible in the JD
- hidden opportunities the role implies
- hiring-manager psychological profile (if and only if public signals exist, e.g., named hiring manager with a public interview or blog)
- recruiter psychological profile and history (if named and if public profile is linked)
- risk sensitivities
- org political complexity signals
- team growth stage signals
- stretch zones vs danger zones for framing

Each field carries `reasoning` and `source_hints`. If no public source supports the speculation, it is marked `source_hints: []` and flagged `ungrounded: true`. These are retained for inspection, never promoted.

### S4 — Optional Research Enrichment
Always runs when `WEB_RESEARCH_ENABLED`. This is not a research-worthiness gate. It is, however, a correctness-gated stage: S4 first resolves whether the target company can be identified confidently enough to research without contaminating the blueprint. If `WEB_RESEARCH_ENABLED=false`, S4 is skipped silently and no claim in the blueprint may depend on research.

Targets:

- company profile: mission, products/services, customer types, funding/trajectory, recent announcements
- engineering stack and engineering culture signals
- public signals for hiring manager and recruiter if named
- salary benchmark signals and public interview-process signals when available
- industry/domain context

If company identity is unresolved, S4 persists `status=skipped_unresolved_identity` and fetches nothing. If identity is resolved, it produces `research_notes` with sources `[{source_id, url, fetched_at, hash, quote}]`. Rule: **no URL, no claim**. S3 and S3b may be re-run with research context to upgrade inferences and ground hypotheses.

### S4b — Application URL & Portal Resolution

Stage 1 should also resolve the application surface when possible, following the status quo already present in `n8n/skills/url-resolver/` and `.claude/skills/apply-jobs/`.

Current repo behavior already establishes the pattern:

- read existing `jobUrl` / `application_url` if present
- resolve a direct `application_url` when missing
- identify `portal_family` from URL/domain patterns and portal playbooks
- track resolution confidence and source

Stage 1 should not mutate the source job document. It should write the resolved result into its own artifact model and expose it through `job_blueprint`.

Execution order should stay deterministic-first:

1. normalize existing `jobUrl`, `job_url`, and `application_url`
2. match known ATS / portal domains deterministically
3. if only a listing URL exists, attempt direct application URL resolution
4. use the LLM only to choose among competing candidate URLs or extract the best direct-apply URL from fetched search results
5. persist the result with provenance and confidence

Expected outputs:

- `application_url` if resolvable
- `portal_family`
- `is_direct_apply`
- `resolution_confidence`
- `resolution_source`
- `portal_detection_source`
- `login_required_likely`
- `multi_step_likely`
- `closed_signal_if_any`

This is valuable because application friction, portal family, and direct apply surface materially affect downstream outreach, application planning, and cover-letter expectations.

### S5 — CV Guidelines Synthesis → `cv_guidelines`
This is the "expert recruiter's checklist for the ideal CV" — principle-based guidance only, no prose, no candidate reference. Inputs: `jd_facts`, `job_inference`, optional `research_notes`. It does **not** read `job_hypotheses` in any form.

Outputs, all as structured guidelines:

**Title guidance**
- ideal title (single string)
- acceptable title range (list)
- titles to avoid (list, with rationale)

**Identity statement & tagline guidance**
- identity thesis: what the hiring side wants to hear in one sentence
- tagline themes (list of angles, not written taglines)
- proof-ladder structure (what progression of claims would be persuasive)

**Bullet guidance**
- bullet themes per expected role archetype
- preferred outcome patterns (scale, reliability, platformization, cost, speed, AI adoption, stakeholder alignment)
- anti-patterns (task lists, responsibilities, buzzwords without outcomes)

**ATS keyword guidance**
- must-include keywords (verbatim from JD)
- should-include keywords (synonyms, related terms)
- acronym policy (first-use expansion pairs)
- section-heading conventions expected by ATS stacks common in this industry

**Hard skills guidance**
- required tools and platforms
- preferred technologies
- depth expected per tool

**Soft skills guidance**
- leadership and collaboration signals the hiring side values
- communication patterns expected (e.g., exec-facing vs IC-facing)

**AI skills guidance**
- AI depth tier expected (applied / architect / research)
- AI domains expected (LLM systems, retrieval, evals, agents, MLOps, etc.)
- AI topics to avoid (hype terms unsupported by JD)

**Architecture skills guidance**
- architecture depth tier (service / platform / enterprise)
- architecture patterns expected (e.g., event-driven, multi-tenant, data-mesh)
- architecture anti-patterns to avoid claiming

**Challenges-solved guidance**
- technical challenges the hiring side would want to see demonstrated
- business challenges the hiring side would want to see demonstrated
- domain challenges specific to the industry

**Cover letter expectations**
- generic cover-letter expectations
- hiring-manager cover-letter expectations
- recruiter cover-letter expectations
- peer-colleague / team-intro note expectations

These remain expectation objects only: opening angle, tone, proof order, what to emphasize, what to avoid, and CTA style. No prose is generated at Stage 1.

**Visa / location guidance**
- whether to mention visa status
- whether to mention location or remote preference
- recommended framing

**Compensation positioning guidance**
- salary band inferred from JD, location, industry, seniority (with sources if S4 ran)
- whether the candidate should mention comp at CV stage (almost always no, but captured for downstream use)

Every guideline carries: `rationale`, `confidence`, `evidence_ids[]` pointing back to `jd_facts` / `job_inference` / `research_notes`. `evidence_ids[]` are canonical identifiers, not free text: field paths for `jd_facts`, item IDs for `job_inference.inferences[]`, and `source_id` values for `research_notes`. No guideline is emitted without ≥1 evidence reference.

### S6 — Master Object Assembly → `job_blueprint` (Python, no LLM)
Assembles the master object by reference + denormalized snapshot. See §6. Deterministic.

## 6. MongoDB Master Object

Underlying documents remain separate (for caching, invalidation, partial rerun). The **master object** is one logical document per job that aggregates them.

### 6.1 `jd_facts`
Two-pass result of S1a (deterministic) + S1b (LLM-as-judge).
```
_id, job_id, jd_text_hash, extracted_at,
extractor_version, judge_model_id, judge_prompt_version,
deterministic {
  company, title_raw, title_normalized, seniority,
  location_raw, location_normalized, remote_policy,
  visa_statement, salary_range {min,max,currency,confidence},
  must_haves[], nice_to_haves[], years_required,
  explicit_hard_skills[], explicit_soft_skills[],
  explicit_ai_skills[], explicit_architecture_signals[],
  explicit_challenges { technical[], business[], domain[] },
  job_url?, existing_application_url?,
  jd_guidance_inputs {
    hard_skills_guidance_input[],
    soft_skills_guidance_input[],
    ai_skills_guidance_input[],
    architecture_guidance_input[],
    challenges_guidance_input { technical[], business[], domain[] }
  },
  acronym_table[{short,long}], keyword_inventory[],
  reporting_line?, raw_word_count,
  locators { <field>: {start,end} }
},
llm_additions[] { field, value, evidence_span{start,end,quote}, confidence },
llm_flags[]     { field, deterministic_value, proposed_value,
                  severity: info|warn|blocking, evidence_span, reasoning },
merged_view { ... as deterministic + accepted additions ... },
provenance  { <field>: "deterministic" | "llm_addition" },
status: ok | needs_review
```

### 6.2 `job_inference`
```
_id, jd_facts_id, research_enrichment_id?, ambiguity_score, taxonomy_version,
primary_role_category,
secondary_role_categories[],
search_profiles[],
selector_profiles[],
tone_family,
semantic_role_model { mandate, success_metrics[],
  expected_architecture_depth, expected_ai_depth,
  expected_business_partnership_level, expected_delivery_maturity,
  ideal_candidate_archetype, likely_screening_themes[],
  likely_stakeholder_surface[], communication_surface_expectations[], document_expectations[] },
company_model { industry, sub_industry, stage, scale, operating_model,
  mission?, product_surface[], customer_types[], business_model?,
  funding_stage?, recent_news_signals[],
  product_complexity, regulated_domain_pressure,
  ai_adoption_maturity, architecture_maturity,
  engineering_culture_signals[], public_tech_stack_signals[],
  hiring_process_public_signals[] },
qualifications { must_haves_merged[], nice_to_haves_merged[], implicit[] },
skills { hard[], soft[], ai_depth, architecture_depth, leadership_scope,
  guidance_seed_hard[], guidance_seed_soft[], guidance_seed_ai[],
  guidance_seed_architecture[], guidance_seed_challenges[] },
domain_knowledge { industries[], regulations[] },
keywords { must_include[], should_include[], acronym_policy },
application_surface { job_url?, application_url?, portal_family?, is_direct_apply?, confidence?,
  source?, portal_detection_source?, login_required_likely?, multi_step_likely?, closed_signal? },
inferences[] { inference_id, field, value, confidence, evidence_spans[] },
token_usage, model_id, prompt_version, created_at
```

### 6.3 `job_hypotheses` (structurally isolated)
```
_id, jd_facts_id, research_enrichment_id?, taxonomy_version,
hypotheses[] { field, value, confidence: low, reasoning, source_hints[], ungrounded: bool },
  # fields include: nuanced_pain_points, subtle_expectations,
  # hidden_opportunities, hiring_manager_profile, recruiter_profile,
  # risk_sensitivities, political_complexity, team_growth_stage,
  # stretch_zones, danger_zones
token_usage, model_id, prompt_version, created_at
```

### 6.4 `research_enrichment` (optional)
```
_id, jd_facts_id, enabled, status: ok | skipped_disabled | skipped_unresolved_identity | failed_budget,
research_depth, research_input_hash, prompt_version,
target_identity { company_name_normalized?, company_url?, confidence },
company_profile { mission?, product_surface[], customer_types[], business_model?,
  funding_stage?, recent_news_signals[], engineering_culture_signals[],
  public_tech_stack_signals[], hiring_process_public_signals[] },
sources[] { source_id, url, fetched_at, hash, title, quote },
notes[] { note_id, topic, summary, source_ids[] },
application_surface { job_url?, application_url?, portal_family?, is_direct_apply?, confidence?,
  source?, portal_detection_source?, login_required_likely?, multi_step_likely?, closed_signal? },
cost_usd, model_id, created_at
```

### 6.5 `cv_guidelines`
```
_id, jd_facts_id, job_inference_id, research_enrichment_id?,
title_guidance { ideal, acceptable_range[], avoid[], rationale, confidence, evidence_ids[] },
identity_guidance { thesis, tagline_themes[], proof_ladder[], rationale, confidence, evidence_ids[] },
bullet_guidance { themes_by_archetype[], outcome_patterns[], anti_patterns[], rationale, confidence, evidence_ids[] },
ats_keyword_guidance { must_include[], should_include[], acronym_policy, heading_conventions[], rationale, confidence, evidence_ids[] },
hard_skills_guidance { required[], preferred[], depth_expectations, rationale, confidence, evidence_ids[] },
soft_skills_guidance { leadership_signals[], collaboration_signals[], communication_patterns, rationale, confidence, evidence_ids[] },
ai_skills_guidance { depth_tier, domains[], avoid_topics[], rationale, confidence, evidence_ids[] },
architecture_guidance { depth_tier, patterns[], anti_patterns[], rationale, confidence, evidence_ids[] },
challenges_guidance { technical[], business[], domain[], rationale, confidence, evidence_ids[] },
cover_letter_guidance {
  generic_expectations { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style, rationale, confidence, evidence_ids[] },
  hiring_manager_expectations { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style, rationale, confidence, evidence_ids[] },
  recruiter_expectations { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style, rationale, confidence, evidence_ids[] },
  peer_colleague_expectations { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style, rationale, confidence, evidence_ids[] }
},
visa_location_guidance { mention_visa, mention_location, framing, rationale, confidence, evidence_ids[] },
compensation_guidance { inferred_band, mention_at_cv_stage: false, rationale, confidence, evidence_ids[] },
confidence_summary, token_usage, model_id, prompt_version, created_at
```

### 6.6 `job_blueprint` — the Master Object
One logical document per `(job_id, blueprint_version)`. References the five above and denormalizes the fields you actually read most often.
```
_id, job_id, blueprint_version, created_at,
refs {
  jd_facts_id, job_inference_id, job_hypotheses_id,
  research_enrichment_id?, cv_guidelines_id
},
snapshot {
  company { name, industry, mission?, stage, ai_adoption_maturity, architecture_maturity },
  role { title_normalized, seniority, primary_role_category, secondary_role_categories[],
         search_profiles[], selector_profiles[], tone_family, mandate, remote_policy,
         visa_statement, location_normalized, salary_range },
  qualifications { must_haves[], nice_to_haves[], implicit[] },
  skills { hard[], soft[], ai_depth, architecture_depth, leadership_scope },
  keywords { must_include[], should_include[], acronym_policy },
  application_surface { job_url?, application_url?, portal_family?, is_direct_apply?, login_required_likely?, multi_step_likely? },
  cv_guidelines { title, identity_thesis, tagline_themes[], bullet_themes[],
                  challenges_expected[], ats_must_include[],
                  cover_letter_expectations {
                    generic { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style },
                    hiring_manager { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style },
                    recruiter { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style },
                    peer_colleague { opening_angle, emphasize[], proof_order[], avoid[], tone, cta_style }
                  } }
},
hypotheses_ref_only: true,     # reminder that hypotheses are NOT in snapshot
confidence_summary, cost_summary, stage_status
```

**Why aggregate + reference**: aggregate for the "one master object" ergonomic, references for invalidation (if JD changes only `jd_facts` invalidates; everything downstream cascades via content hash).

**Persisted vs ephemeral.** Persisted: all six above. Ephemeral (Langfuse only, 30d): raw LLM completions, retry scratchpads, prompt-assembly diagnostics.

**Required indexes.**
- `jd_facts`: unique on `(job_id, jd_text_hash, extractor_version, judge_prompt_version)`
- `job_inference`: unique on `(jd_facts_id, research_enrichment_id, prompt_version, taxonomy_version)`
- `job_hypotheses`: unique on `(jd_facts_id, research_enrichment_id, prompt_version, taxonomy_version)`
- `research_enrichment`: unique on `(jd_facts_id, research_input_hash, prompt_version)`
- `cv_guidelines`: unique on `(jd_facts_id, job_inference_id, research_enrichment_id, prompt_version)`
- `job_blueprint`: unique on `(job_id, blueprint_version)`
- Add non-unique indexes on every `*_id` reference field used by assemblers and review UIs.

## 7. Prompt Catalog

| Prompt | Input | Output (structured) |
|---|---|---|
| P-jd-judge | raw JD + jd_facts.deterministic | `{additions[], flags[], confirmations}` |
| P-classify | jd_facts.merged_view + canonical job taxonomy | `{primary_role_category, secondary_role_categories[], search_profiles[], selector_profiles[], tone_family, taxonomy_version, ambiguity_score}` |
| P-role-model | jd_facts + classify (+ research if available) | `job_inference` body |
| P-hypotheses | jd_facts + classify (+ research if available) | `job_hypotheses` body |
| P-research | jd_facts + company tokens | `research_enrichment` body |
| P-application-url | existing URLs + company identity + portal taxonomy | `application_surface { application_url, portal_family, is_direct_apply, confidence, source, portal_detection_source, login_required_likely, multi_step_likely, closed_signal_if_any }` |
| P-cv-guidelines | jd_facts + job_inference + research_notes? | `cv_guidelines` body |

Prompt prefix order: system rules → schema → few-shot → variable inputs last. Structured output enforced; on invalid parse: one retry, then fail stage.

## 8. Model Choice

Stage 1 should now expose explicit Codex CLI model choices per step, even if the runtime keeps them configurable in one mapping file.

Current recommended Codex CLI mapping:

| Stage / Prompt | Model |
|---|---|
| S1a, S6 | none (Python) |
| S1b / P-jd-judge | `gpt-5.4-mini` |
| S2 / P-classify | `gpt-5.4-mini` |
| S3 / P-role-model | `gpt-5.4` |
| S3b / P-hypotheses | `gpt-5.4-mini` |
| S4 / P-research | `gpt-5.4-mini` |
| S4b / P-application-url | `gpt-5.4-mini` |
| S5 / P-cv-guidelines | `gpt-5.4` |

Why this split:

- `P-jd-judge` and `P-classify` are structured, bounded, and cheaper on `gpt-5.4-mini`.
- `P-role-model` and `P-cv-guidelines` are the highest-value synthesis steps and benefit most from `gpt-5.4`.
- `P-hypotheses`, `P-research`, and `P-application-url` need reasoning over fetched/search-derived context, but not the highest-cost synthesis path.

Operational rule:

- keep the model IDs in config, not hardcoded in the implementation
- if the VPS runtime only exposes one production-safe Codex CLI model, collapse all LLM steps to `gpt-5.4` and keep the stage boundaries unchanged

## 9. Deterministic Linters (Stage 1 scope only)

Stage 1 produces guidance, not CV text, so ATS *formatting* linters do not apply here. What does apply:

- `jd_facts` extractor correctness: unit tests on known JDs.
- `keyword_inventory` dedup and stopword filtering.
- Acronym table sanity: no self-referential entries.
- `cv_guidelines` schema validation: every guideline has `evidence_ids[]` length ≥1.
- `job_hypotheses` guard: no hypothesis field accidentally promoted into `job_inference`. Enforced by prompt isolation + schema validator that rejects low-confidence items written to `job_inference`.

## 10. Caching, Idempotency, Reuse Keys

- `jd_facts.deterministic`: invalidate on JD text hash change.
- `jd_facts` (merged): invalidate on `(jd_text_hash, extractor_version, judge_prompt_version)` change.
- `job_inference`: invalidate on `(jd_facts_id, research_enrichment_id?, prompt_version, taxonomy_version)` change.
- `job_hypotheses`: invalidate on `(jd_facts_id, research_enrichment_id?, prompt_version, taxonomy_version)` change.
- `research_enrichment`: invalidate on `(jd_facts_id, research_depth, prompt_version)` change.
- `cv_guidelines`: invalidate on `(job_inference_id, research_enrichment_id?, prompt_version)` change.
- `job_blueprint`: rebuilt cheaply from references whenever any sub-document changes.
- `P-classify` also invalidates on canonical taxonomy file version/hash changes.

Prompt prefixes kept stable across jobs for whatever cache benefit the runtime exposes.

## 11. Observability

- Langfuse span per stage, per LLM call: stage, input hash, model_id, prompt_version, tokens, cost, latency, output validity.
- Mongo persists durable artifacts only.
- Per-run summary: stages executed/skipped, cost, blueprint completeness score.

`blueprint_completeness_score` is deterministic: required documents present (`jd_facts`, `job_inference`, `cv_guidelines`) + zero unresolved blocking flags + `cv_guidelines` evidence coverage pass. `job_hypotheses` and `research_enrichment` do not gate completeness.

## 12. Eval Strategy (What "Good Blueprint" Means Without Candidate Ground Truth)

Stage 1 has no interview-outcome signal yet. Useful proxies:

- **Expert rubric**: 20 held-out jobs scored by a human recruiter against: correctness of facts, reasonableness of inferences, defensibility of hypotheses, usefulness of CV guidelines for an archetypal candidate.
- **Cross-run stability**: run Stage 1 twice on the same JD; target high agreement on facts, moderate on inferences, documented drift on hypotheses.
- **Coverage check**: percentage of JD must-have clauses represented in `job_inference.qualifications`.
- **Evidence-span density**: average evidence_ids per `cv_guidelines` field. Below threshold → reject.

## 13. Rollout Plan

- **Phase 0**: freeze the six schemas; Pydantic models; Mongo indexes.
- **Phase 0.5**: adopt `data/job_archetypes.yaml` as the canonical taxonomy source-of-truth and map existing profile/category enums to it.
- **Phase 1**: S0, S1, S6 (all deterministic) shipped behind feature flag.
- **Phase 2**: S2, S3 minimal vertical slice producing `job_inference`.
- **Phase 3**: S3b hypothesis extraction in separate collection, isolation verified by tests.
- **Phase 4**: S4 research + S4b application URL / portal resolution.
- **Phase 5**: S5 CV guidelines synthesis including cover-letter expectation guidance.
- **Phase 6**: evals, prompt versioning, cost tracking.

Each phase ships with eval deltas.

## 14. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Hypotheses leak into later generation prompts | Separate document; no generation-stage whitelist includes it; automated test asserts no prompt template imports `job_hypotheses`. |
| LLM drifts into candidate-specific guidance | Prompt framing: "You do not know the candidate. Produce guidelines for an ideal candidate only." Schema rejects any field referencing a candidate. |
| Research cost explosion | Per-run USD budget (`RESEARCH_BUDGET_USD`) and bounded `RESEARCH_DEPTH`. S4 aborts cleanly when the budget is hit. |
| Hallucinated evidence_ids in `cv_guidelines` | S6 assembler validates that every `evidence_ids[]` resolves to a real span in `jd_facts`/`job_inference`/`research_enrichment`. |
| Model SKU drift | Stage-to-model mapping lives in one config surface; update there, not in prompt code. |
| Codex CLI lacks structured outputs | Template-regex validator + single retry; fail stage on second invalid. |
| Over-stored Mongo blobs | Raw completions to Langfuse only. |

## 15. Roadmap

**Stage 1 (this plan).** JD + public research → `job_blueprint` master object. No candidate input.

**Stage 2 (future plan).** Candidate modeling: `candidate_evidence_store`, `candidate_profile`, evidence ingestion pipeline, edit loop. Also runs independently of any specific job.

**Stage 3 (future plan).** Match + generation: consumes `job_blueprint` + `candidate_evidence_store`. Produces match strategy, section drafts, grounding verifier, repair loop, final CV. Stage 3 is the only place `job_hypotheses` could affect selection, never wording; structural isolation stays.

## 16. What Was Removed From The Previous Draft And Why

- `candidate_evidence_store` — candidate input, out of scope for Stage 1.
- `candidate_match_strategy` — two-sided, requires candidate. Deferred to Stage 3.
- `cv_generation_run` — produces CV prose. Deferred to Stage 3.
- S5 evidence selection, S7 section generation, S9 grounding verifier, S10 repair, S11 final assembly — all candidate-dependent.
- The §16 "What Hiring Managers Want To See" writing tips were moved to `docs/current/cv-generation-guide.md` as an appendix.
- Astrology dimensions (political complexity, team growth stage, stretch zones, etc.) are retained **only** inside `job_hypotheses`, with explicit `ungrounded: true` when no public source supports them. They are structurally isolated and do not reach generation prompts when Stage 3 is built.

## 17. Direct Answers To The Original Questions

1. **Only steps needed?** Stage 1 = S0, S1a, S1b, S2, S3, S3b, S4, S4b, S5, S6. Research runs whenever `WEB_RESEARCH_ENABLED=true`, with budget/depth limits and a correctness guard that skips unsafe external fetches when company identity cannot be resolved safely. Everything else runs on every job.
2. **Best quality while minimizing cost?** Cost is controlled structurally first, but the plan now exposes explicit Codex CLI model choices: `gpt-5.4-mini` for judge/classify/research/url-resolution and `gpt-5.4` for high-value synthesis (`P-role-model`, `P-cv-guidelines`).
3. **Full semantic model of role and company?** Covered by S3 (`job_inference`), with company + product/mission + role + qualifications + skills + keywords + domain knowledge + application surface + document expectations all structured. Speculative dimensions (pain points, subtle expectations, hiring-manager profile, recruiter profile, opportunities) live in `job_hypotheses`, isolated.
4. **Is regex structuring needed?** Yes, as the source of truth for `jd_facts`. It is cheaper and more reliable than an LLM for title/seniority/location/comp/visa/must-haves/acronyms/keywords/years.
5. **Principle-based guidelines for what the hiring manager wants to see?** Covered by S5 `cv_guidelines` covering title, bullets, identity, ATS, hard/soft/AI/architecture skills, challenges, cover-letter expectations, visa, location, salary. Every guideline carries evidence references; no guideline without ≥1 evidence ID.
6. **One skill or many?** One orchestration skill externally; multiple internal stage modules with one canonical taxonomy source-of-truth. No monolithic prompt, not even as fallback.
7. **One prompt or many?** Seven typed prompts (P-jd-judge, P-classify, P-role-model, P-hypotheses, P-research, P-application-url, P-cv-guidelines). Never one giant prompt.
8. **Model routing under Codex/OpenAI-only?** Explicit per-step Codex CLI models are now part of the plan: `gpt-5.4-mini` for bounded structured steps and `gpt-5.4` for the deepest synthesis steps.
9. **ATS strategy strict enough?** ATS *guidance* at Stage 1 (must/should keywords, acronym policy, heading conventions). ATS *enforcement* (format linters, forbidden-claim regex, keyword-coverage gates) belongs in Stage 3, which writes the CV text.
10. **Realistic for a VPS skill pipeline?** Yes — Stage 1 has no candidate dependencies, no retrieval, no repair loop. It is seven prompts + three deterministic stages, all independently cacheable, and it now absorbs the existing application URL resolution pattern without mutating upstream job docs.
