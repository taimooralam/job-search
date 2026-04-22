# Iteration 4.1.3 Plan: Unified Company, Role, Application, and Stakeholder Intelligence

## 1. Executive Summary

Iteration 4.1.3 upgrades the current `research_enrichment` stage from a thin company-summary wrapper into the canonical external-intelligence artifact for the 4.1 DAG. The target is one collection-backed `research_enrichment` document per job that unifies:

- company research richer than runner-era `company_research`
- role research richer than runner-era `role_research`
- application resolution richer than current `application_surface`
- public-professional stakeholder discovery
- evidence-grounded initial outreach guidance for each discovered stakeholder

This is not a control-plane rewrite. The stage-level DAG, independent workers, sweepers, retries, `cv_ready`, single-job-document UI read pattern, snapshot mirror, and compatibility projections from Iterations 4 and 4.1 remain in place.

The correct 4.1.3 shape is:

- keep `application_surface` as a separate execution stage for retry/isolation
- make `research_enrichment` depend on `application_surface` and absorb its results into a canonical `application_profile`
- move runner-grade company and role intelligence into `research_enrichment`
- keep `job_inference` as a synthesis layer, not the owner of web-grounded role research
- treat stakeholder discovery and outreach guidance as optional, source-attributed, privacy-bounded subdocuments that never block the lane when evidence is weak

Short-term, `level-2.company_research`, `level-2.role_research`, and `application_url` remain compatibility projections. Long-term, `research_enrichment` becomes the source of truth for all external/public job intelligence.

## 2. Objective and Non-Goals

### Objective

Design Iteration 4.1.3 so the preenrich lane produces a unified `research_enrichment` artifact with:

- externally grounded company intelligence
- externally grounded role intelligence
- externally grounded application intelligence
- stakeholder identity candidates with evidence and confidence
- evidence-grounded initial outreach guidance that is useful without being manipulative, speculative, or privacy-invasive

### Non-Goals

Iteration 4.1.3 does not:

- redesign the stage-DAG control plane from Iteration 4
- collapse all research into one monolithic worker call
- replace `jd_facts`, `classification`, or `job_inference`
- make people research mandatory for `cv_ready`
- scrape private data, personal contact details, or protected-trait signals
- generate fully personalized outbound copy in preenrich
- move the frontend to direct multi-collection joins

## 3. Inherited Constraints From Iterations 1–4.1.1

### Iteration 1

- Avoid blackholes. Every new boundary must have a real downstream consumer and observable run state.
- Do not add “nice to have” intelligence that nothing actually reads.

### Iteration 2

- Preserve honest state transitions.
- Preserve rollout flags and rollback paths.
- Do not silently diverge from the reference implementation while claiming parity.

### Iteration 3

- `level-2` remains the live preenrich handoff boundary.
- Mongo remains the operational source of truth.
- Debug/operator surfaces must remain projection-friendly and readable from the job document.

### Iteration 4

- Keep the stage-level DAG, independent workers, retries, sweepers, and `cv_ready`.
- Do not reintroduce a monolithic preenrich worker.

### Iteration 4.1

- Not a clean-slate rewrite.
- Collection-backed artifacts plus `level-2` snapshot mirror remain the architectural pattern.
- Compatibility projections are mandatory while downstream consumers still read legacy fields.

### Iteration 4.1.1

- No-loss contracts matter more than prompt cleverness.
- Shadow vs live-write separation matters.
- Benchmarks and rollout gates must exist before cutover.

## 4. Current-State Review

### 4.1 Current `research_enrichment` Is a Thin Wrapper

Current code in `src/preenrich/stages/research_enrichment.py` does not perform real research. It:

- reads company name and maybe `company_url`
- exits `unresolved` if company identity is weak
- exits `no_research` if `WEB_RESEARCH_ENABLED=false`
- mostly mirrors preexisting `job.company_research` into a `CompanyProfile`
- writes an artifact with almost no `sources`, `evidence`, or role/application/stakeholder content

This is a blackhole: a stage with a rich name but thin behavior.

### 4.2 Current `application_surface` Is Structurally Right but Operationally Thin

`src/preenrich/stages/application_surface.py` already isolates deterministic URL normalization and portal-family detection. That is good control-plane design. But it is still thin:

- no redirect-chain verification
- no stale/closed detection
- no form or ATS fetch verification
- no duplicate-posting normalization beyond basic URL handling
- no explicit relationship to company or stakeholder discovery

### 4.3 Current `job_inference` Is Not Runner-Grade Role Research

`src/preenrich/stages/job_inference.py` is a synthesis layer, not a web-grounded role-research owner. It currently derives:

- semantic role model
- success themes
- screening themes
- candidate archetypes

from `jd_facts`, `classification`, and thin research inputs. That is useful, but it is not a substitute for runner-grade role research.

### 4.4 Current Snapshot/Compat Projection Is Still Thin

`src/preenrich/stages/blueprint_assembly.py` currently projects:

- top-level `application_url`
- thin `company_research`
- thin `role_research`
- pain-point related compatibility fields

This preserves old readers, but it does not carry a modern research contract.

### 4.5 Stronger Legacy Surfaces Already Exist

The repo already contains richer building blocks:

- `src/layer3/company_researcher.py`
- `src/layer3/role_researcher.py`
- `src/services/company_research_service.py`
- `src/common/claude_web_research.py`
- `src/services/form_scraper_service.py`
- `n8n/skills/url-resolver/scripts/resolver.py`
- `src/layer5/people_mapper.py`
- `src/services/outreach_service.py`

These prove 4.1.3 is not speculative. The gap is not absence of ideas. The gap is lack of a unified artifact and controlled integration into the 4.1 DAG.

### 4.6 Current Downstream Consumers Already Exist

There are real consumers for richer research:

- job detail UI sections in `frontend/templates/job_detail.html`
- blueprint snapshot readers
- contact discovery / contact display in the job detail page
- outreach generation in `src/services/outreach_service.py`
- future `job_inference` and `cv_guidelines` consumers

This satisfies the Iteration 1 “no blackholes” requirement.

## 5. Gap Analysis vs Runner Company Research / Role Research / Application Resolution

| Area | Runner / Existing Capability | Current 4.1 Gap | 4.1.3 Requirement |
| --- | --- | --- | --- |
| Company research | `company_researcher` has richer summaries, signals, source-aware logic | thin mirror only | canonical `company_profile` with evidence, sources, confidence, caching |
| Role research | `role_researcher` does web-grounded summary/impact/why-now | thin inference-derived role summary | canonical `role_profile` grounded in JD + public web research |
| Application resolution | `url-resolver` and `form_scraper_service` are richer | deterministic URL normalize only | canonical `application_profile` with resolution, portal, friction, stale detection |
| People intelligence | `people_mapper` and outreach flows exist outside 4.1 | no canonical preenrich artifact | canonical `stakeholder_intelligence` with evidence and confidence |
| Outreach guidance | outreach service generates messages later | no preenrich guidance substrate | evidence-grounded outreach guidance, not speculative personalization |
| Source attribution | legacy company/role research has stronger sourcing patterns | current 4.1 artifact nearly empty | mandatory source trail per subdocument |
| Transport realism | Claude web research and Firecrawl exist; Codex CLI now exposes `--search` | no unified transport abstraction | explicit provider/transport contract with fallback paths |

## 6. Scope Ruling

### 6.1 Canonical Artifact Decision

Iteration 4.1.3 should keep **one canonical `research_enrichment` artifact**.

### 6.2 Execution-Stage Decision

`application_surface` should **remain a separate execution stage**.

Reason:

- URL/application resolution has different retry/failure behavior than company/role/stakeholder research.
- deterministic normalization, redirect probing, and form/ATS inspection are operationally distinct.
- forcing everything into one stage creates a monolithic retry blackhole and worsens rate-limit behavior.

But `research_enrichment` should **absorb `application_surface` as a canonical subdocument** by reading the `application_surface` artifact and building `application_profile` inside `research_enrichment`.

That means:

- one canonical source of truth for downstream consumers
- separate execution isolation for operational safety

### 6.3 Role-Research Ownership Decision

Runner-grade role-research reasoning should live **mostly in `research_enrichment`**, not `job_inference`.

`job_inference` should continue to own semantic synthesis for CV generation and screening logic.

`research_enrichment` should own:

- public-company context
- public-role context
- interview/evaluation themes sourced from public evidence or strong JD/company signals
- role urgency / why-now / business context sourced from external evidence

`job_inference` should consume that artifact and produce candidate-facing synthesis, not invent it from thin inputs.

### 6.4 Stakeholder Scope Decision

Stakeholder discovery and stakeholder outreach guidance belong in `research_enrichment`, but they are:

- optional
- evidence-gated
- confidence-scored
- unresolved-by-default when evidence is thin

They do not justify a separate top-level DAG stage in 4.1.3.

## 7. Target Architecture

### 7.1 Canonical 4.1.3 Shape

Recommended architecture:

1. `application_surface`
   - deterministic-first resolution stage
   - enriches application candidates, portal family, friction, stale/duplicate hints
   - writes its own artifact

2. `research_enrichment`
   - depends on `jd_facts`, `classification`, and `application_surface`
   - resolves company identity
   - performs external company research
   - performs external role research
   - merges application-stage results into `application_profile`
   - performs stakeholder discovery
   - performs stakeholder profile synthesis
   - generates evidence-grounded initial outreach guidance
   - writes one canonical collection-backed artifact

3. `job_inference`
   - consumes the richer `research_enrichment`
   - no longer owns runner-grade role research by proxy

4. `blueprint_assembly`
   - mirrors compact research views into snapshot and compatibility projections
   - does not re-research or infer missing external facts

### 7.2 Internal Research Substeps

Inside `research_enrichment`, implement internal substeps rather than new DAG stages:

1. company identity resolution
2. company profile acquisition
3. role profile acquisition
4. application profile merge
5. stakeholder candidate discovery
6. stakeholder evidence consolidation
7. outreach-guidance synthesis

Each substep must persist traceable status and confidence, even if the final stage completes with partial/unresolved subdocuments.

## 8. Canonical Artifact Schema

Recommended top-level shape for collection `research_enrichment`:

```json
{
  "_id": "...",
  "job_id": "...",
  "jd_facts_id": "...",
  "classification_id": "...",
  "application_surface_id": "...",
  "input_snapshot_id": "...",
  "research_version": "research_enrichment.v4.1.3",
  "prompt_version": "v1",
  "provider_used": "codex|claude|hybrid",
  "model_used": "gpt-5.4-mini|...",
  "transport_used": "codex_web_search|claude_web_tools|firecrawl_hybrid|none",
  "status": "completed|partial|unresolved|no_research|failed_terminal",
  "capability_flags": {},
  "company_profile": {},
  "role_profile": {},
  "application_profile": {},
  "stakeholder_intelligence": [],
  "sources": [],
  "evidence": [],
  "confidence": {},
  "notes": [],
  "unresolved_questions": [],
  "cache_refs": {},
  "timing": {},
  "usage": {}
}
```

<!-- Review note 2026-04-20: Final persisted artifact fields in §8 and prompt outputs in §22 must stay aligned. Phase-scoped prompt payloads may be partial, but they must merge into these canonical names without renaming or lossy projection. -->

Prompt-library alignment rule:

- Prompts in §22 may emit **phase-scoped partial payloads** keyed by `stakeholder_ref`, `candidate_rank`, or another explicit merge key.
- Partial payloads may omit fields outside that phase’s scope.
- Partial payloads may **not** rename canonical persisted fields defined in §8.
- Any intermediate-only helper field must be explicitly labeled intermediate-only and stripped before persistence.

<!-- Review rubric B6/B7: PASS after contract alignment. `company_profile`, `role_profile`, `application_profile`, and compact stakeholder summary all have reachable consumers through `blueprint_assembly` compat/snapshot projections, `job_inference`, job-detail UI, and outreach handoff. Any richer nested detail beyond those readers must stay collection-only to avoid blackholes. -->

### 8.1 `company_profile`

At minimum:

- `summary`
- `url`
- `signals`
- `canonical_name`
- `canonical_domain`
- `canonical_url`
- `identity_confidence`
- `identity_basis`
- `company_type`
- `mission_summary`
- `product_summary`
- `business_model`
- `customers_and_market`
- `scale_signals`
- `funding_signals`
- `ai_data_platform_maturity`
- `team_org_signals`
- `recent_signals`
- `role_relevant_signals`
- `sources`
- `evidence`
- `confidence`
- `status`

Required compatibility note:

- `summary`, `url`, and `signals` remain required compat-facing aliases because current blueprint snapshot and `level-2.company_research` readers still expect that shape.
- `summary` is the compact display/operator summary.
- `url` is the compat alias of `canonical_url`.
- `signals` is the compact display/operator signal list; richer signal structures may also exist elsewhere in the subdocument.

### 8.2 `role_profile`

At minimum:

- `role_summary`
- `mandate`
- `business_impact`
- `why_now`
- `success_metrics`
- `collaboration_map`
- `reporting_line`
- `org_placement`
- `interview_themes`
- `evaluation_signals`
- `risk_landscape`
- `company_context_alignment`
- `sources`
- `evidence`
- `confidence`
- `status`

<!-- Review rubric B8: PASS after adding `last_verified_at`, `final_http_status`, `resolution_note`, `ui_actionability`, and `status`. Without those fields the plan could not honestly support apply-button confidence or stale/closed UI warnings. -->

### 8.3 `application_profile`

At minimum:

- `job_url`
- `canonical_application_url`
- `redirect_chain`
- `last_verified_at`
- `final_http_status`
- `resolution_method`
- `resolution_confidence`
- `resolution_status`
- `resolution_note`
- `ui_actionability`
- `portal_family`
- `ats_vendor`
- `is_direct_apply`
- `account_creation_likely`
- `multi_step_likely`
- `form_fetch_status`
- `stale_signal`
- `closed_signal`
- `duplicate_signal`
- `geo_normalization`
- `apply_instructions`
- `apply_caveats`
- `sources`
- `evidence`
- `confidence`
- `status`

<!-- Review rubric B9: PASS with constraints. The stakeholder shape is useful for outreach and review, but it stays within public-professional, source-attributed, confidence-scored bounds and excludes private contact fields. -->

### 8.4 `stakeholder_intelligence`

Each stakeholder record:

- `stakeholder_type`
  - `recruiter`
  - `hiring_manager`
  - `executive_sponsor`
  - `peer_technical`
  - `unknown`
- `identity_confidence`
- `identity_status`
- `identity_basis`
- `matched_signal_classes`
- `candidate_rank`
- `name`
- `current_title`
- `current_company`
- `profile_url`
- `source_trail`
- `function`
- `seniority`
- `relationship_to_role`
- `likely_influence`
- `public_professional_background`
- `public_communication_signals`
- `working_style_signals`
- `likely_priorities`
- `initial_outreach_guidance`
- `avoid_points`
- `evidence_basis`
- `confidence`
- `unresolved_markers`

### 8.5 `initial_outreach_guidance`

Each stakeholder record must include:

- `what_they_likely_care_about`
  - 3–7 bullets
  - job-relevant only
  - each bullet tied to public evidence, JD evidence, company context, or role context
- `initial_cold_interaction_guidance`
  - 3–7 bullets
  - tailored by stakeholder type
  - includes best opening angle, value signal, credibility markers, what not to waste time on, and appropriate CTA
- `avoid_in_initial_contact`
  - 2–5 bullets
- `confidence_and_basis`
  - explicit score
  - evidence summary
  - unresolved/uncertain items

Normalization rule for the final artifact:

- `likely_priorities` is the canonical top-level alias of `initial_outreach_guidance.what_they_likely_care_about`.
- `avoid_points` is the canonical top-level alias of `initial_outreach_guidance.avoid_in_initial_contact`.
- `evidence_basis` is the top-level compact summary derived from `initial_outreach_guidance.confidence_and_basis`.
- `confidence` is the persisted top-level confidence object for the stakeholder record.

## 9. Stage / DAG / Gating Decision

<!-- Review rubric A1/A2/A3: A1 PASS — preserves 4.1 control-plane invariants (stage DAG, collection-backed artifacts, compact snapshot, compat projections). A2 PASS — no circular dependency introduced; `job_inference` remains downstream of `research_enrichment`. A3 WEAK-but-accepted — keeping `application_surface` separate is the right short-term call because current DAG, `job_inference`, and UI compat still read it directly, even though long-term canonical ownership moves to `research_enrichment.application_profile`. -->

### 9.1 DAG Recommendation

Change the blueprint DAG so:

- `application_surface` prerequisites remain `("jd_facts",)`
- `research_enrichment` prerequisites become `("jd_facts", "classification", "application_surface")`
- `job_inference` prerequisites become `("jd_facts", "classification", "research_enrichment")`

This is a DAG adjustment, not a control-plane rewrite.

### 9.2 Why This DAG Change Is Correct

- `classification` helps scope role/company research and search queries.
- `application_surface` should complete first so `research_enrichment` can own the unified `application_profile`.
- `job_inference` should consume the canonical research artifact rather than parallel thin artifacts.

### 9.3 `required_for_cv_ready`

`research_enrichment` remains `required_for_cv_ready`, but required means the stage must complete with an honest terminal status, not that every subdocument must be fully populated.

Subdocument gating:

- `company_profile`
  - required when company identity is resolvable
  - may be `status="unresolved"` when identity is weak
- `role_profile`
  - required if JD facts are sufficient to identify role family
  - may be partial/unresolved if external evidence is weak
- `application_profile`
  - required as a subdocument
  - may be `unresolved` or `partial` without blocking the stage
- `stakeholder_intelligence`
  - optional, non-gating
  - unresolved/empty is acceptable
- `initial_outreach_guidance`
  - optional and only emitted when stakeholder identity reaches threshold

### 9.4 Failure Policy

Do not fail the whole stage for:

- missing stakeholder identities
- weak people evidence
- weak role-context signals
- lack of live web search on a given run

Do fail terminally for:

- schema corruption
- invalid transport output after bounded retries
- incompatible feature-flag configuration

## 10. Websearch and Webfetch Transport Strategy

### 10.1 Current Repo Reality

The repo already has:

- `src/common/claude_web_research.py`
  - real Claude web-research wrapper
- `src/services/form_scraper_service.py`
  - Firecrawl-backed search/fetch/form extraction
- `n8n/skills/url-resolver/scripts/resolver.py`
  - Codex/OpenClaw agent with `web_fetch` plus Firecrawl fallback

Additionally, the current Codex CLI exposes `--search`. A live probe on 2026-04-20 successfully executed a native `web_search` tool call through:

- `codex --search exec ...`

That means Codex web search is operationally plausible on VPS. But the repo does **not** yet have a first-class Python transport wrapper around Codex CLI web search for stage workers.

### 10.2 Recommended Transport Contract

Introduce a transport abstraction for 4.1.3 planning:

- `codex_web_search`
  - primary on VPS when Codex CLI auth/config is present
- `claude_web_tools`
  - fallback when Claude web tools are available
- `firecrawl_hybrid`
  - deterministic fallback for fetch-heavy application resolution and form inspection
- `none`
  - explicit degraded mode

### 10.3 Recommended Operational Routing

Short-term recommended routing:

1. `application_surface`
   - deterministic URL normalization
   - Codex/OpenClaw `web_fetch` or Firecrawl search/fetch for application verification
2. `research_enrichment`
   - Codex CLI `--search` on VPS as the preferred search transport
   - Claude web tools as fallback if Codex transport is unavailable
   - Firecrawl only where fetch/HTML/form inspection is superior to search synthesis

### 10.4 Fallback Behavior

If live web research is unavailable:

- complete the stage with `status="partial"` or `status="no_research"`
- preserve deterministic application resolution if available
- populate unresolved questions instead of hallucinating
- never silently fabricate company, role, or stakeholder details

<!-- Review rubric C10/C12: C10 PASS after §10.5 and §18.4 were made consistent. C12 PASS with explicit degradation ordering only if low-confidence and transport-unavailable cases end in `partial`/`unresolved`, not fake parity claims. -->

### 10.5 Recommended Feature Flags

At minimum add:

- `PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED`
- `PREENRICH_RESEARCH_SHADOW_MODE_ENABLED`
- `PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED`
- `PREENRICH_RESEARCH_UI_SNAPSHOT_EXPANDED_ENABLED`
- `PREENRICH_RESEARCH_PROVIDER`
- `PREENRICH_RESEARCH_TRANSPORT`
- `PREENRICH_RESEARCH_FALLBACK_PROVIDER`
- `PREENRICH_RESEARCH_FALLBACK_TRANSPORT`
- `PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS`
- `PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE`
- `PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION`
- `PREENRICH_RESEARCH_MAX_WEB_QUERIES`
- `PREENRICH_RESEARCH_MAX_FETCHES`
- `PREENRICH_RESEARCH_COMPANY_CACHE_TTL_HOURS`
- `PREENRICH_RESEARCH_APPLICATION_CACHE_TTL_HOURS`
- `PREENRICH_RESEARCH_STAKEHOLDER_CACHE_TTL_HOURS`

Validation rules:

- shadow mode requires V2 enabled
- live compat write requires V2 enabled
- expanded UI snapshot requires V2 enabled
- outreach guidance requires stakeholders enabled
- require-source-attribution may not be disabled in live compat mode

## 11. Stakeholder Discovery and Evidence Rules

### 11.1 Identity Ladder

Discover stakeholders only via this evidence ladder:

1. explicit JD/person mentions
2. explicit company/job/application URLs
3. ATS/application page metadata
4. company team/about/leadership pages
5. public professional profiles that match company + function + role context

No stakeholder should be emitted as “resolved” on a single fuzzy title match.

### 11.2 Confidence Bands

Each stakeholder candidate must be classified as:

- `high`
- `medium`
- `low`
- `unresolved`

High confidence requires converging evidence from more than one signal class or a single strong direct signal.

### 11.3 Anti-Hallucination Rules

- never merge two ambiguous public profiles into one person
- never guess personal email or private contact routes
- never fabricate department, scope, or decision influence
- when uncertain, keep multiple candidates or emit unresolved
- require source trail on every stakeholder record

### 11.4 Stakeholder Types

Supported types:

- recruiter
- hiring_manager
- executive_sponsor
- peer_technical
- unknown

### 11.5 Snapshot Policy

Do not mirror full stakeholder records into the default snapshot. Mirror only compact summaries and artifact refs. Full stakeholder intelligence should remain collection-backed to avoid snapshot bloat and privacy drift.

## 12. Stakeholder Outreach Guidance Rules

### 12.1 Purpose

The goal is not to generate manipulative copy. The goal is to produce evidence-grounded guidance that later outreach workflows can use safely.

### 12.2 Required Rules

Guidance must:

- never pretend to know private motives or inner psychology
- never fabricate familiarity
- never use sensitive personal data
- never infer protected traits
- never state “they care about X” without role/JD/public evidence
- use uncertainty language when evidence is weak
- stay job-relevant and outreach-relevant

### 12.3 Guidance Inputs

Only use:

- the JD
- company context
- role context
- stakeholder public-professional profile/signals
- explicit source attribution
- confidence scoring

### 12.4 Guidance Contract

For each stakeholder:

- `what_they_likely_care_about`
  - 3–7 evidence-backed bullets
- `initial_cold_interaction_guidance`
  - 3–7 bullets
  - must include opening angle, value signal, credibility markers, what not to waste time on, appropriate CTA
  - must be tailored by stakeholder type
- `avoid_in_initial_contact`
  - 2–5 bullets
- `confidence_and_basis`
  - score, evidence, uncertainty

### 12.5 Tailoring by Stakeholder Type

- recruiter
  - prioritize role-match clarity, logistics, fit, signal efficiency
- hiring_manager
  - prioritize mandate understanding, execution value, relevant ownership
- executive_sponsor
  - prioritize business impact, leverage, organization-level outcomes
- peer_technical
  - prioritize technical credibility, collaboration, problem fit

## 13. Privacy, Safety, and Compliance Guardrails

Hard bans:

- protected-trait inference
- political or religious inference
- family/home/private-life details
- mental-health or personality claims
- private contact scraping
- speculative psychologizing
- covert influence tactics

Allowed:

- public-professional role/title/background
- public speaking/writing/working-style signals when directly sourced
- job-relevant hiring-priority inferences when evidence-backed

Logs and artifacts must avoid storing unnecessary personal data. Snapshot mirrors must be compact.

## 14. Data Model, Indexes, Caching, and Invalidation

### 14.1 Canonical Collection

Primary collection:

- `research_enrichment`

Recommended unique key:

- `job_id`
- `input_snapshot_id`
- `research_version`

Recommended supporting indexes:

- `(job_id, created_at desc)`
- `(jd_facts_id, classification_id, application_surface_id)`
- `(status, updated_at)`
- `(company_profile.canonical_domain, status)`

<!-- Review rubric C11: PASS after cache-scope hardening. Company cache is now explicitly company-global only; role-scoped, application-scoped, stakeholder-scoped, and outreach-scoped conclusions may not leak across postings. -->

### 14.2 Shared Cache Collections

To avoid duplicated research across jobs from the same company:

- `research_company_cache`
  - key: `canonical_domain + transport_version + prompt_version`
- `research_application_cache`
  - key: `normalized_job_url or canonical_application_url + transport_version + prompt_version`
- `research_stakeholder_cache`
  - key: `canonical_domain + profile_url + transport_version + prompt_version`

Do not make caches the source of truth. They are accelerators only.

<!-- Review note 2026-04-20: company-level cache scope must stay company-global. Role-scoped and stakeholder-scoped conclusions may not be written into a shared company cache or they will leak across postings. -->

Cache-scope rule:

- `research_company_cache` may store only company-global facts:
  - canonical identity
  - mission/product summary
  - business model
  - scale/funding/org signals
  - public AI/data/platform signals
- `role_relevant_signals`, `role_profile`, stakeholder records, and outreach guidance are **never** written into the shared company cache.
- `role_profile` remains job-scoped and must always be recomputed against the current JD checksum even when company cache hits.

### 14.3 Invalidation

Invalidate `research_enrichment` on:

- JD checksum change
- company checksum change
- taxonomy version change when role classification materially shifts
- transport/prompt version change
- application URL candidate set change

Additional scope rules:

- `role_profile` invalidates on JD checksum change even if `research_company_cache` remains fresh.
- stakeholder guidance invalidates on any change to stakeholder identity resolution, role profile, or company profile.

Invalidate shared caches on:

- TTL expiry
- transport version change
- prompt version change
- explicit company identity correction

### 14.4 Suggested TTLs

- company cache: 7 days
- application cache: 24–72 hours
- stakeholder cache: 3 days

## 15. Compatibility Projections and Snapshot Strategy

<!-- Review rubric A5: PASS after explicit V2-off rule. If research V2 is disabled, existing 4.1 projections remain authoritative instead of leaving legacy readers in a half-disabled state. -->

### 15.1 Short-Term Compatibility

Keep these top-level compatibility projections:

- `application_url`
- `company_research`
- `role_research`

But generate them from the new canonical artifact.

V2-off rule:

- If `PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=false`, the existing 4.1 `application_surface`, current top-level `application_url`, and existing `company_research` / `role_research` projection behavior remain authoritative.
- V2 flags must not partially disable those legacy readers without an explicit replacement path.

<!-- Review rubric A4: PASS after compact allow-listing. The snapshot stays compact by mirroring summaries, compact signals, and stakeholder counts/refs only; full source/evidence/outreach payloads remain out of snapshot. -->

### 15.2 Snapshot Mirror

Mirror compact research views into `pre_enrichment.job_blueprint_snapshot`:

- `research.company_profile.summary`
- `research.company_profile.signals`
- `research.role_profile.summary`
- `research.role_profile.why_now`
- `research.role_profile.success_metrics`
- `research.application_profile.portal_family`
- `research.application_profile.canonical_application_url`
- compact stakeholder summary only
  - count by type
  - top high-confidence names/titles
  - artifact refs

Do not mirror:

- full source trails
- full stakeholder evidence blocks
- full outreach-guidance bullet sets

### 15.3 Long-Term Source of Truth

Long-term:

- `research_enrichment` becomes the only external-intelligence owner
- `company_research` and `role_research` top-level fields become thin projections and later removable
- outreach/contact workflows read the collection-backed stakeholder intelligence directly or via targeted service projections

## 16. Prompt / Model Routing / Provider Strategy

### 16.1 Provider Strategy

Default provider strategy:

- company + role + stakeholder synthesis: Codex on VPS with `--search`
- fallback: Claude web tools
- fetch-heavy application verification: Firecrawl / resolver hybrid

### 16.2 Model Routing

Keep costs bounded:

- deterministic resolution and normalization first
- `gpt-5.4-mini` default for bounded research synthesis passes
- escalate to `gpt-5.4` only when:
  - evidence reconciliation fails
  - stakeholder ambiguity remains high after bounded search
  - schema validation repeatedly fails

Where Claude fallback is used:

- `claude-haiku` for lightweight fetch summarization
- `claude-sonnet` for richer evidence synthesis

### 16.3 Prompt Decomposition

Recommended prompts:

- `P-research-company`
- `P-research-role`
- `P-research-application-merge`
- `P-stakeholder-discovery`
- `P-stakeholder-profile`
- `P-stakeholder-outreach-guidance`

Each must be:

- JSON-only
- schema-first
- source-attributed
- confidence-scored
- explicit about abstaining when evidence is weak

## 17. Benchmark and Acceptance Criteria

### 17.1 Harness

Add a benchmark harness for 4.1.3. The plan should expect a future script such as:

- `scripts/benchmark_research_enrichment_4_1_3.py`

<!-- Review rubric E22/E23: E22 PASS after threshold-to-output alignment was tightened in §17.4 and §22.5. E23 WEAK — the listed corpora are acceptable minimum gates, but not a long-term steady-state sign-off corpus if reviewer disagreement stays noisy. -->

### 17.2 Benchmark Sets

Minimum curated sets:

- 20-job company/role benchmark set with runner-era research for comparison
- 15-job application-resolution benchmark set across ATS/direct-apply/stale/duplicate cases
- 10-job stakeholder discovery benchmark set with manual review
- 10-job outreach-guidance review set, starting with 1 seed gold job and expanding deliberately

### 17.3 Better-Than-Runner Criteria

Better-than-runner means:

- company profile contains at least the runner summary/signals plus source attribution and fresher public signals
- role profile contains at least the runner summary/business-impact/why-now plus evidence, interview themes, and risk landscape
- application resolution beats current `application_surface` on canonical URL accuracy and stale detection

### 17.4 Blocking Thresholds

Recommended thresholds before live write:

- company-profile factuality: >= 0.95 reviewed factual accuracy
- role-profile factuality: >= 0.90 reviewed factual accuracy
- application canonical URL exact match: >= 0.90
- portal-family accuracy: >= 0.95
- stakeholder identification precision at medium/high confidence: >= 0.85
- non-unknown company and role claims with source_ids attached: >= 0.95
- non-unknown outreach-guidance bullets with explicit evidence basis attached: >= 0.95
- outreach-guidance speculative/privacy violations: 0 tolerated
- unresolved-handling correctness on low-evidence cases: >= 0.90
- downstream usefulness reviewer score for `job_inference`, job-detail UI, and outreach handoff: >= 0.80

### 17.5 Outreach-Guidance Evaluation

Require reviewer scoring for:

- precision of stakeholder identification
- factual grounding of `what_they_likely_care_about`
- usefulness of `initial_cold_interaction_guidance`
- absence of speculative or privacy-invasive claims
- whether guidance is actionable without sounding fabricated

## 18. Rollout, Shadow Mode, Canary, and Rollback

### 18.1 Shadow Mode

First ship 4.1.3 in shadow mode:

- write `research_enrichment` v2 artifact
- keep legacy compatibility projections live
- do not widen UI snapshot by default
- compare against runner/company/role/application baselines offline

### 18.2 Canary

Rollout phases:

1. one-job canary
2. 10-job shadow corpus
3. benchmark sign-off
4. 10% live compat projection
5. 100% live compat projection

### 18.3 Rollback

Rollback must allow:

- disabling live compat projection
- keeping artifact writes for debugging
- falling back to old thin projections without breaking `cv_ready`

### 18.4 Required Flags

At minimum:

- `PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED`
- `PREENRICH_RESEARCH_SHADOW_MODE_ENABLED`
- `PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED`
- `PREENRICH_RESEARCH_UI_SNAPSHOT_EXPANDED_ENABLED`
- `PREENRICH_RESEARCH_PROVIDER`
- `PREENRICH_RESEARCH_TRANSPORT`
- `PREENRICH_RESEARCH_FALLBACK_PROVIDER`
- `PREENRICH_RESEARCH_FALLBACK_TRANSPORT`
- `PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS`
- `PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE`
- `PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION`
- `PREENRICH_RESEARCH_MAX_WEB_QUERIES`
- `PREENRICH_RESEARCH_MAX_FETCHES`
- `PREENRICH_RESEARCH_COMPANY_CACHE_TTL_HOURS`
- `PREENRICH_RESEARCH_APPLICATION_CACHE_TTL_HOURS`
- `PREENRICH_RESEARCH_STAKEHOLDER_CACHE_TTL_HOURS`

## 19. Test Plan

### 19.1 Unit Tests

Add tests for:

- research artifact schema validation
- company identity resolution and confidence scoring
- application profile merge from `application_surface`
- stakeholder candidate confidence and unresolved handling
- outreach-guidance safety rules
- snapshot compactness and allow-listing

### 19.2 Integration Tests

Add tests for:

- DAG prereq changes
- `cv_ready` behavior with partial/unresolved stakeholder subdocs
- compat projection correctness
- cache hit/miss and invalidation behavior
- transport fallback behavior when live web research is unavailable

### 19.3 Benchmark Tests

Add harness tests for:

- benchmark corpus loading
- no-write benchmark mode
- reviewed-score aggregation
- blocking-threshold enforcement

### 19.4 UI / Consumer Tests

Add tests for:

- snapshot-first rendering of compact research views
- no oversized snapshot payload
- stakeholder summary presence without leaking full private-detail blocks
- outreach consumers reading artifact-backed stakeholder data safely

<!-- Review rubric F24/F25: F24 PASS — Questions 4 and 5 are correctly treated as pre-Phase-1 blockers; Questions 1–3 can wait. F25 PASS — only limited safe parallelism exists once §8 schema and §22 prompt contracts are frozen. -->

## 20. Open Questions

Questions to close before implementation:

1. Should `application_surface` artifact remain separately readable by operators, or only as a subordinate artifact once 4.1.3 lands?
2. Should stakeholder summaries be visible on the default job detail page, or only in a dedicated expandable section?
3. Should outreach-guidance fields live only in `research_enrichment`, or also be mirrored into `outreach_packages` later as derived data?
4. Which provider should be the default on VPS at launch: Codex CLI `--search` or Claude web tools?
5. Is `people_mapper` migrated into the new artifact boundary or retired behind it?

Must-answer before Phase 1 starts:

- Question 4
- Question 5

May wait until later phases:

- Questions 1–3

## 21. Implementation Phases

### Phase 1: Contract and Transport

- finalize artifact schema
- define transport abstraction
- add flags, models, and collection/index definitions

### Phase 2: Application and Company/Role Parity

- strengthen `application_surface`
- build `research_enrichment.company_profile`
- build `research_enrichment.role_profile`
- wire compact compat projections

### Phase 3: Stakeholder Intelligence

- add stakeholder discovery
- add stakeholder evidence rules
- add confidence and unresolved handling

### Phase 4: Outreach Guidance

- add evidence-grounded guidance blocks
- add privacy/speculation guardrails
- add benchmark review rubric

### Phase 5: Shadow, Benchmark, Cutover

- run shadow corpus
- score against runner/current baselines
- fix regressions
- enable live compat projection

Safe parallelism:

- benchmark harness scaffolding can begin in parallel with Phase 2 once the §8 schema and §22 prompt contracts are frozen
- Phase 3 stakeholder discovery can begin in parallel with late Phase 2 only after company/role/application schemas are stable
- Phase 4 outreach-guidance work must wait for stakeholder merge keys and confidence rules to be frozen

## 22. Prompt Library for Phases 1–4

This section specifies the canonical prompt contracts for every LLM-facing step introduced in Iteration 4.1.3. All prompts are upgrades of the runner-era prompts (`COMPANY_RESEARCH_SYSTEM_PROMPT`, `ROLE_RESEARCH_SYSTEM_PROMPT`, `PEOPLE_RESEARCH_SYSTEM_PROMPT`, `SYSTEM_PROMPT_CLASSIFICATION`, `SYSTEM_PROMPT_OUTREACH`, url-resolver agent prompt, form-extraction prompt) that currently live in `src/common/claude_web_research.py`, `src/layer5/people_mapper.py`, `src/services/outreach_service.py`, `src/services/form_scraper_service.py`, and `n8n/skills/url-resolver/scripts/resolver.py`.

Every prompt below is richer than the status quo along four dimensions:

- schema-first structured output with per-field confidence
- explicit source-attribution contract (each claim maps to a source id)
- explicit abstain-on-weak-evidence contract (unresolved beats hallucinated)
- explicit privacy/safety guardrails (no protected traits, no private contact data)

All prompts assume JSON-only output, no markdown fences, no commentary, and deterministic field order. They follow the existing `_json_only_contract()` discipline in `src/preenrich/blueprint_prompts.py`.

### 22.0 Shared Prompt Contract (applies to every prompt below)

Every prompt in this library MUST include the following shared header, referenced as `SHARED_CONTRACT_HEADER`:

```
You are a preenrich research worker for Iteration 4.1.3.

Hard output rules:
- Return ONLY valid JSON. No markdown, no code fences, no commentary.
- Use the literal string "unknown" only for schema fields that explicitly allow unknown string values. Do not invent placeholder values for enums, URLs, dates, or identifiers.
- Empty lists MUST be [].
- Every factual claim MUST cite at least one entry from the `sources` array by `source_id`.
- Every persisted subdocument MUST include a `confidence` object: {score: 0.0–1.0, band: "high"|"medium"|"low"|"unresolved", basis: string}.
- If the evidence is insufficient for a claim, emit status="unresolved" for that subdocument and move on.
- NEVER invent people, URLs, dates, titles, or quotes. NEVER merge two ambiguous profiles.
- NEVER infer protected traits (age, gender, race, religion, politics, health, family status).
- NEVER scrape or guess personal contact details (personal email, phone, home address).

Source discipline:
- Every source you consult MUST be added to the `sources` array with a unique `source_id` (e.g., "s1", "s2").
- Each source entry: {source_id, url, source_type, fetched_at, trust_tier: "primary"|"secondary"|"tertiary"}.
- Primary = company-owned official page, ATS page, job posting page.
- Secondary = LinkedIn, Crunchbase, reputable press, official filings.
- Tertiary = aggregators, blog posts, forums.

Evidence discipline:
- Every persisted subdocument MUST include an `evidence` array of {claim, source_ids[], excerpt?} tuples.
- An excerpt, when present, MUST be ≤ 240 chars quoted directly from the source.
- If you did not directly observe quote text, omit `excerpt` rather than fabricating a paraphrase as a quote.
- Do NOT emit excerpts for stakeholder personal posts unless they are clearly job-relevant.

Verification discipline:
- A URL may be returned only if it was directly fetched, observed in fetched content, or observed in a trusted search result payload.
- Probe templates and constructed ATS candidates are discovery aids only. They are NOT valid outputs unless subsequently verified.
- Domains may not be guessed from company slugs alone.
- Dates MUST be directly observed. If not directly observed, emit "unknown".

Confidence calibration:
- high  (>=0.80): two+ converging primary/secondary sources OR one unambiguous primary source.
- medium (0.50–0.79): one secondary source OR converging tertiary sources.
- low    (0.20–0.49): single tertiary source OR inferential from strong priors.
- unresolved (<0.20): stop — emit status="unresolved" for that subdocument.

Abstain rules (MANDATORY):
- If you cannot resolve company identity with at least medium confidence, emit `company_profile.status="unresolved"` and skip downstream claims that depend on company identity.
- If role family cannot be identified from JD + classification, emit `role_profile.status="partial"` with only the fields you CAN ground.
- If no stakeholder candidate clears medium confidence, emit `stakeholder_intelligence=[]` with a note explaining why.

Safety guardrails (MANDATORY):
- No protected-trait inference, no psychologizing, no speculation about private motives.
- No political/religious/family-life signals unless the person has publicly posted on the topic in a clearly professional context AND it is directly job-relevant.
- No covert-influence or manipulation tactics in outreach guidance.
- No private contact routes. Restrict guidance to public-professional channels only.
```

All prompts below assume this header is prepended. For brevity, the rest of this document references it as `{SHARED_CONTRACT_HEADER}`.

### 22.1 Phase 1 — Contract and Transport

Phase 1 is schema/plumbing; it introduces no new user-facing LLM prompts. It DOES, however, define the **transport preamble** that every provider wrapper must emit before calling the downstream prompt.

<!-- Review rubric D13–D21 for `P-transport-preamble`: D13 WEAK — this is richer than current wrappers on budget/source discipline, but it is not itself a semantic research prompt. D14 PASS. D15 PASS. D16 PASS after verified-source rules. D17 PASS. D18 N/A. D19 PASS. D20 PASS. D21 PASS once §22.5 records prompt file path + git SHA + transport tuple. -->

#### 22.1.1 `P-transport-preamble`

Purpose: a one-shot wrapper injected by the transport layer (codex_web_search, claude_web_tools, firecrawl_hybrid) before the real prompt, so the model knows which tools it can use and how to attribute sources.

```
{SHARED_CONTRACT_HEADER}

Transport: {transport_used}
Budget:
- max_web_queries: {PREENRICH_RESEARCH_MAX_WEB_QUERIES}
- max_fetches:     {PREENRICH_RESEARCH_MAX_FETCHES}
- max_tool_turns:  {max_tool_turns}

Tool-use rules:
- Prefer primary sources (company-owned pages, ATS pages) over aggregators.
- After each successful fetch, record the fetched URL and a 1-sentence relevance tag.
- Stop fetching once you have enough to emit a schema-valid artifact with high or medium confidence.
- If you exhaust the budget without reaching medium confidence, emit status="partial" with what you have.
- Never fetch private pages, logged-in views, or pages behind paywalls you cannot read.

Return only the downstream artifact JSON for this step. Do NOT echo this preamble.
```

Flags controlling this preamble: `PREENRICH_RESEARCH_TRANSPORT`, `PREENRICH_RESEARCH_MAX_WEB_QUERIES`, `PREENRICH_RESEARCH_MAX_FETCHES`, `PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION`.

### 22.2 Phase 2 — Application and Company/Role Parity

Phase 2 introduces four prompts. All are richer than their runner predecessors along the source/evidence/confidence dimensions.

<!-- Review rubric D13–D21 for `P-application-surface`: D13 PASS versus `n8n/skills/url-resolver/scripts/resolver.py:61-93` on schema, attribution, confidence, abstention, and stale/duplicate handling. D14 PASS. D15 PASS. D16 PASS after verified-only URL output and anti-cross-company rule. D17 PASS. D18 N/A. D19 PASS. D20 PASS. D21 PASS. -->

#### 22.2.1 `P-application-surface` (upgrade of `n8n/skills/url-resolver/scripts/resolver.py:build_prompt`)

Purpose: deterministic-first application URL resolution, redirect probing, ATS vendor detection, stale/closed/duplicate detection.

```
{SHARED_CONTRACT_HEADER}
{SHARED_TRANSPORT_PREAMBLE}

You are resolving the authoritative application URL and portal metadata for a specific job posting.

Inputs:
- title: {title}
- company: {company}
- location: {location}
- known_job_url: {job_url}
- ats_domain_allowlist: {ats_domains}
- blocked_domains: {blocked_domains}

Resolution strategy (execute in order, stop at first high-confidence hit):
1. Dereference the known_job_url and record the full redirect chain, final HTTP status, and verification timestamp.
2. If the final URL is on an ATS (greenhouse, lever, workday, ashby, smartrecruiters, icims, bamboohr, workable, teamtailor, recruitee, breezy, jobvite, taleo, successfactors), record `ats_vendor` and `portal_family`.
3. If no ATS detected, probe these canonical ATS API/URL patterns for the company slug `{company_slug}`:
   - boards-api.greenhouse.io/v1/boards/{company_slug}/jobs
   - jobs.lever.co/{company_slug}
   - {company_slug}.wd1.myworkdayjobs.com, wd3, wd5
   - jobs.ashbyhq.com/{company_slug}
   - {company_slug}.bamboohr.com/careers
   - apply.workable.com/{company_slug}
4. Treat those probe URLs as candidates only. A probe URL may be emitted only if a fetch or trusted result confirms the posting actually exists.
5. If none work, fetch the company careers page and look for the exact role title.
6. If the only candidate is a third-party aggregator, keep it in `redirect_chain`/`duplicate_signal` but do not promote it to `canonical_application_url` unless no first-party or ATS path can be verified.
7. For each candidate URL, classify: is_direct_apply, account_creation_likely, multi_step_likely.
8. Inspect the page for stale/closed signals ("position filled", "no longer accepting", 404, 410, HTTP redirect to /careers root).
9. If the posting appears on two URLs from different portals, record the canonical (primary employer > ATS vendor > aggregator) and list duplicates.
10. Do NOT invent URLs. If confidence < medium, emit resolution_status="unresolved".

Geo normalization:
- Normalize `location` to {country, region, city, remote_policy}. If the posting advertises multiple geos, keep all.

Output schema (JSON only):
{
  "job_url": "{job_url}",
  "canonical_application_url": "<url or 'unknown'>",
  "redirect_chain": [<url>, ...],
  "last_verified_at": "<ISO8601 timestamp>",
  "final_http_status": 200|301|302|404|410|"unknown",
  "resolution_method": "direct_ats|ats_probe|careers_page|search|unresolved",
  "resolution_status": "resolved|partial|unresolved",
  "resolution_note": "<short operator-facing note or 'unknown'>",
  "ui_actionability": "ready|caution|blocked|unknown",
  "portal_family": "greenhouse|lever|workday|ashby|smartrecruiters|icims|bamboohr|workable|teamtailor|recruitee|breezy|jobvite|taleo|successfactors|direct|unknown",
  "ats_vendor": "<vendor or 'unknown'>",
  "is_direct_apply": true|false|"unknown",
  "account_creation_likely": true|false|"unknown",
  "multi_step_likely": true|false|"unknown",
  "form_fetch_status": "fetched|blocked|not_attempted",
  "stale_signal": "active|likely_stale|closed|unknown",
  "closed_signal": "open|closed|unknown",
  "duplicate_signal": {"canonical": "<url>", "duplicates": [<url>, ...]},
  "geo_normalization": {"country": "<iso2>", "region": "<str>", "city": "<str>", "remote_policy": "remote|hybrid|onsite|unknown"},
  "apply_instructions": "<short operator-facing note or 'unknown'>",
  "apply_caveats": [<str>, ...],
  "sources": [...],
  "evidence": [...],
  "confidence": {"score": 0.0, "band": "...", "basis": "..."},
  "status": "completed|partial|unresolved"
}

Never return a URL from a different company. If uncertain, return "unknown".
```

Why this is richer than runner: runner prompt returned only `{application_url, confidence, source}` with no redirect chain, no portal family, no stale detection, no duplicate handling, no geo normalization.

<!-- Review rubric D13–D21 for `P-research-company`: D13 PASS versus `src/common/claude_web_research.py:94-139` on canonical identity, per-subfield evidence/confidence, abstention, and safety. D14 PASS after compat-facing `summary` / `url` / `signals` were restored. D15 PASS. D16 PASS after guessed-domain prohibition. D17 PASS. D18 N/A. D19 WEAK unless caller enforces the inline search-result packing caps. D20 PASS. D21 PASS. -->

#### 22.2.2 `P-research-company` (upgrade of `COMPANY_RESEARCH_SYSTEM_PROMPT`)

Purpose: externally grounded company intelligence with source-per-claim attribution and per-field confidence.

```
{SHARED_CONTRACT_HEADER}
{SHARED_TRANSPORT_PREAMBLE}

You are building a canonical `company_profile` subdocument for a specific employer.

Inputs:
- company_name: {company}
- company_name_variations: {name_variations}
- known_company_url: {company_url}
- candidate_domain_hints: {candidate_domains}
- jd_excerpt: {jd_excerpt_2000c}
- classification: {role_category}, {seniority_level}
- application_profile: {application_profile_compact}

Input packing constraints:
- jd_excerpt is capped at 2,000 chars.
- application_profile_compact must be <= 1,000 chars.
- Search-result snippets passed inline must be <= 6 snippets total and <= 240 chars each.

Identity resolution (do FIRST, never skip):
- Resolve canonical domain, canonical name, canonical URL. Use application_profile.portal_family as a tiebreaker if present.
- If you cannot converge on a single entity with medium+ confidence (e.g., two companies share the name, or the company is a microsite of a larger org), emit `identity_confidence.band="unresolved"` and STOP — do NOT fabricate signals.
- `canonical_domain` and `canonical_url` must come from verified sources. Do not guess them from a company slug.

Search strategy (budget-bounded, prefer primary sources):
1. Official site: "{company}" (about OR careers OR company OR leadership) site:{canonical_domain}
2. LinkedIn: site:linkedin.com/company "{company}"
3. Crunchbase / Pitchbook-equivalent: site:crunchbase.com "{company}"
4. Recent news (last 18 months): "{company}" (funding OR acquisition OR partnership OR leadership OR layoff OR IPO) after:{cutoff_date}
5. Product/technical context: "{company}" (engineering blog OR tech stack OR open source OR AI OR platform)
6. Agency detection: "{company}" (staffing OR recruitment OR "on behalf of" OR "our client")
7. Scale: employee count, geographic footprint, customer logos, revenue signals.
8. AI/data maturity: ML teams, data platform choice, model usage, MLOps posture.

Anti-hallucination rules (in addition to shared contract):
- Every signal MUST have type ∈ {funding, acquisition, leadership_change, product_launch, partnership, growth, layoff, regulatory, ai_initiative, customer_win, other}.
- Every signal MUST have a `source_ids` array citing at least one entry in `sources`.
- Do NOT repeat a signal across types; pick the most specific one.
- If the company is a recruitment agency, emit `company_type="recruitment_agency"` and skip product/market sections with a note.

Output schema (JSON only):
{
  "summary": "<compact operator-facing summary grounded in sources>",
  "url": "<canonical url or 'unknown'>",
  "signals": [<compact signal objects for compat/display>, ...],
  "canonical_name": "<str>",
  "canonical_domain": "<str>",
  "canonical_url": "<str>",
  "identity_confidence": {"score": 0.0, "band": "...", "basis": "..."},
  "identity_basis": "<which sources converged>",
  "company_type": "employer|recruitment_agency|unknown",
  "mission_summary": "<2–3 sentences grounded in sources, or 'unknown'>",
  "product_summary":  "<2–3 sentences grounded in sources, or 'unknown'>",
  "business_model": "b2b_saas|b2c|marketplace|enterprise_services|agency|public_sector|nonprofit|other|unknown",
  "customers_and_market": {"segments": [<str>, ...], "named_customers": [<str>, ...], "geo": [<str>, ...]},
  "scale_signals": {"employee_band": "1-50|51-200|201-1k|1k-10k|10k+|unknown", "revenue_band": "<str or unknown>", "offices": [<str>, ...]},
  "funding_signals": [{"round": "seed|series_a|...|ipo|public", "amount": "<str>", "date": "YYYY-MM", "investors": [<str>, ...], "source_ids": [...]}, ...],
  "ai_data_platform_maturity": {"posture": "ai_native|ai_adopter|ai_curious|not_ai|unknown", "platform_hints": [<str>, ...], "model_usage_hints": [<str>, ...], "source_ids": [...]},
  "team_org_signals": {"eng_org_shape": "<str or unknown>", "notable_leaders": [{"name":"...", "title":"...", "source_ids":[...]}], "open_roles_near": "<str or unknown>"},
  "recent_signals": [<CompanySignal>, ...],
  "role_relevant_signals": [<CompanySignal subset explicitly tied to the open role>, ...],
  "sources": [...],
  "evidence": [...],
  "confidence": {"score": 0.0, "band": "...", "basis": "..."},
  "status": "completed|partial|unresolved"
}
```

Why this is richer than runner: runner version produced `{summary, signals[], url, company_type}` only. The 4.1.3 version adds canonical identity, business model, customers, scale/funding breakdown, AI/data maturity, org signals, role-relevant signal filtering, and per-subfield source attribution.

<!-- Review rubric D13–D21 for `P-research-role`: D13 PASS versus `src/common/claude_web_research.py:190-225` on richer schema, attribution, confidence, and abstention. D14 PASS. D15 PASS. D16 WEAK residual hallucination risk remains around `reporting_line` / `org_placement`, so `unknown` must remain the default absent explicit public evidence. D17 PASS. D18 N/A. D19 PASS with the stated packing caps. D20 PASS. D21 PASS. -->

#### 22.2.3 `P-research-role` (upgrade of `ROLE_RESEARCH_SYSTEM_PROMPT`)

Purpose: externally grounded role intelligence (mandate, why-now, success metrics, collaboration map, risk landscape).

```
{SHARED_CONTRACT_HEADER}
{SHARED_TRANSPORT_PREAMBLE}

You are building a canonical `role_profile` subdocument for a specific open role at a specific company.

Inputs:
- title: {title}
- company: {company}
- jd_text: {jd_full_or_3000c}
- jd_facts: {jd_facts_compact}
- classification: {role_category}, {seniority_level}, {function_area}
- company_profile: {company_profile_compact}
- application_profile: {application_profile_compact}

Input packing constraints:
- jd_text is capped at 3,000 chars with section-aware packing.
- company_profile_compact must be <= 1,200 chars.
- application_profile_compact must be <= 800 chars.

Search strategy (budget-bounded):
1. Team/department: site:linkedin.com/company "{company}" {function_area}
2. Recent hires into equivalent title: "{company}" ("{title}" OR "{title_variant}") "joined as" site:linkedin.com/in
3. Technical context (if tech role): "{company}" (engineering blog OR tech stack OR architecture OR AI platform)
4. Leadership context: previous person in this seat, current reporting line
5. Why-now signals: cross-reference company_profile.recent_signals (funding, product launch, reorg, AI push, geographic expansion)
6. Interview-loop signals: public interview pages, engineering blog posts, public candidate experience posts. Anonymous forums may be used only as tertiary corroboration and never as the sole basis for a claim.
7. Risk landscape: recent layoffs at the company, closed rounds, regulatory actions, public negative signals

Mandate inference rules:
- Build `mandate` from JD + company_profile.recent_signals. Every mandate bullet MUST cite either (a) a JD line via evidence excerpt, or (b) a company signal by source_id.
- `why_now` MUST reference at least one company signal, one JD urgency cue, or an explicit statement from a public source — never fabricated.
- `success_metrics` MUST be tied to JD bullets or public role descriptions at peer companies — mark inference explicitly in `basis`.
- `collaboration_map` lists functions/teams the role will work with, inferred from JD or company org signals.
- `reporting_line` is unknown unless JD or a public source states it.
- `risk_landscape` is optional but should flag role-level risks (new function, shrinking team, post-layoff backfill) when evidence exists.

Abstain rules:
- If company_profile.status is "unresolved", emit role_profile.status="partial" and populate only JD-derived fields.
- If JD is too thin to identify role family, emit role_profile.status="unresolved".

Output schema (JSON only):
{
  "role_summary": "<2–3 sentences: ownership, scope, team size if known>",
  "mandate": [<bullet, each citing source_ids>, ...],
  "business_impact": [<3–5 bullets tied to JD or company signals>],
  "why_now": "<1–2 sentences citing ≥1 company signal>",
  "success_metrics": [<3–5 measurable outcomes, each with basis>],
  "collaboration_map": [{"function": "...", "seniority": "...", "interaction_mode": "dotted|solid|peer|unknown"}, ...],
  "reporting_line": {"manager_title": "<str or unknown>", "skip_level_title": "<str or unknown>", "source_ids": [...]},
  "org_placement": {"function_area": "...", "sub_org": "<str or unknown>", "team_size_band": "1-5|6-15|16-50|50+|unknown"},
  "interview_themes": [<4–7 likely interview themes with basis>],
  "evaluation_signals": [<what the company will test for, with basis>],
  "risk_landscape": [<role-level risks with source_ids or "none_detected">],
  "company_context_alignment": "<1–2 sentences tying the role to company_profile>",
  "sources": [...],
  "evidence": [...],
  "confidence": {"score": 0.0, "band": "...", "basis": "..."},
  "status": "completed|partial|unresolved"
}
```

Why this is richer than runner: runner version produced `{summary, business_impact[3–5], why_now}`. The 4.1.3 version adds mandate, success_metrics, collaboration_map, reporting_line, org_placement, interview_themes, evaluation_signals, risk_landscape, and alignment to company_profile — each source-attributed.

<!-- Review rubric D13–D21 for `P-research-application-merge`: D13 PASS as a safer, schema-bound reconciliation step that the runner stack did not have. D14 PASS. D15 PASS. D16 PASS so long as it never refetches and only reconciles verified inputs. D17 PASS. D18 N/A. D19 PASS. D20 PASS. D21 PASS. -->

#### 22.2.4 `P-research-application-merge`

Purpose: deterministic consolidator that MERGES the `application_surface` artifact into `research_enrichment.application_profile`. Mostly non-LLM, but when reconciliation is ambiguous the LLM is asked to choose.

```
{SHARED_CONTRACT_HEADER}

You are reconciling the application_surface artifact with any existing application_url hints on the job document.

Inputs:
- application_surface_artifact: {application_surface_compact}
- job_document_hints: {job_doc_application_hints}
- company_profile.canonical_domain: {canonical_domain}

Rules:
- Prefer application_surface.canonical_application_url over job_document_hints unless application_surface.resolution_status="unresolved" AND job_document_hints.url is on the canonical_domain.
- Keep the full redirect_chain from application_surface.
- If canonical_application_url is on an ATS that is NOT typically used by the canonical_domain, flag `portal_family_mismatch=true` and lower confidence to "low".
- If `stale_signal="likely_stale"` or `closed_signal="closed"`, merge with resolution_status="partial" and emit an apply_caveat explaining the staleness.

Output: the same schema as §8.3 `application_profile`, with sources/evidence/confidence populated. Do NOT refetch the web — this is a merge, not a research pass.
```

### 22.3 Phase 3 — Stakeholder Intelligence

Phase 3 introduces two prompts, both stricter than `PEOPLE_RESEARCH_SYSTEM_PROMPT` / `SYSTEM_PROMPT_CLASSIFICATION`.

<!-- Review rubric D13–D21 for `P-stakeholder-discovery`: D13 PASS versus `src/common/claude_web_research.py:141-188` and `src/layer5/people_mapper.py:319-385` on structure, confidence, abstention, and anti-merge rules. D14 PASS. D15 PASS after `matched_signal_classes` and ladder-gated confidence rules were made validator-enforceable. D16 PASS with explicit no-constructed-URL / no-cross-person-merge rules. D17 PASS. D18 N/A. D19 PASS. D20 PASS. D21 PASS. -->

#### 22.3.1 `P-stakeholder-discovery` (upgrade of `PEOPLE_RESEARCH_SYSTEM_PROMPT`)

Purpose: discover candidate stakeholders using the Identity Ladder (§11.1), classify by type, score confidence, and emit unresolved when evidence is thin.

```
{SHARED_CONTRACT_HEADER}
{SHARED_TRANSPORT_PREAMBLE}

You are discovering public-professional stakeholder candidates for a specific open role.

Inputs:
- title: {title}
- company: {company}
- company_profile: {company_profile_compact}
- role_profile: {role_profile_compact}
- application_profile: {application_profile_compact}
- jd_excerpt: {jd_excerpt_1500c}

Identity Ladder (you MUST follow this order — no shortcuts):
1. Explicit JD/person mentions (hiring manager named in JD).
2. Explicit company/job/application URLs (recruiter contact on the ATS page).
3. ATS/application page metadata (posting owner, "hiring manager:" field, referral contact).
4. Company team/about/leadership pages (public leadership list).
5. Public LinkedIn profiles that match company + function + role context. Require ≥2 converging signals (current company + function OR current company + seniority + region).

Validator-enforceable confidence rules:
- `medium` or `high` identity confidence requires either:
  - one direct signal class: `jd_named_person`, `ats_named_person`, or `official_team_page_named_person`, or
  - at least two distinct `matched_signal_classes`.
- `matched_signal_classes` must be chosen from:
  - `jd_named_person`
  - `job_or_application_url`
  - `ats_named_person`
  - `official_team_page_named_person`
  - `public_profile_company_match`
  - `public_profile_function_match`
  - `public_profile_seniority_match`
  - `public_profile_region_match`

Stakeholder types (emit one per record):
- recruiter — in-house TA, internal recruiter, TA coordinator, staffing partner.
- hiring_manager — the direct manager for the role, inferred from JD reporting language + LinkedIn title match.
- executive_sponsor — VP/C-suite one level above the hiring_manager, relevant only if the role is VP+ or if JD names them.
- peer_technical — likely future peer at comparable seniority in the same function.
- unknown — evidence exists but role-mapping cannot be pinned down.

Anti-hallucination rules (in addition to shared contract):
- NEVER construct LinkedIn URLs. Only emit URLs that appear in search results you actually saw.
- NEVER merge two ambiguous candidates into one — if two candidates both match, emit BOTH with lower confidence and leave resolution to downstream review.
- NEVER promote a stakeholder to `high` confidence on a single fuzzy title match.
- If no candidate clears `medium`, emit stakeholder_intelligence=[] with an `unresolved_markers` note explaining why (e.g., "company has <50 employees listed on LinkedIn, no public team page").
- Never emit personal email, phone, or home-region details. profile_url must be a public professional profile.

Ranking rules:
- Rank candidates by: (a) relevance to the open role, (b) identity_confidence, (c) likely_influence on the hire.
- Emit up to 3 recruiter, 2 hiring_manager, 2 executive_sponsor, 3 peer_technical candidates. No more.

Output schema (JSON only, list):
[
  {
    "stakeholder_type": "recruiter|hiring_manager|executive_sponsor|peer_technical|unknown",
    "identity_status": "resolved|ambiguous|unresolved",
    "identity_confidence": {"score": 0.0, "band": "...", "basis": "..."},
    "identity_basis": "<short explanation of why this candidate is in play>",
    "matched_signal_classes": [<enum>, ...],
    "candidate_rank": 1,
    "name": "<str or 'unknown'>",
    "current_title": "<str or 'unknown'>",
    "current_company": "<str>",
    "profile_url": "<url or 'unknown'>",
    "source_trail": [<source_id>, ...],
    "function": "engineering|product|data|ml|recruiting|operations|finance|executive|unknown",
    "seniority": "individual|lead|manager|director|vp|cxo|unknown",
    "relationship_to_role": "direct_manager|skip_manager|peer|recruiter|sponsor|unknown",
    "likely_influence": "decision_maker|strong_input|veto|informational|unknown",
    "unresolved_markers": [<str>, ...],
    "sources": [...],
    "evidence": [...],
    "confidence": {"score": 0.0, "band": "...", "basis": "..."}
  },
  ...
]
```

Why this is richer than runner: runner version produced `{primary_contacts[], secondary_contacts[]}` with minimal `{name, role, why_relevant, linkedin_url, email}`. The 4.1.3 version adds identity_status, identity_confidence, source_trail, function/seniority/relationship/influence, and enforces the Identity Ladder and anti-merge rules.

<!-- Review rubric D13–D21 for `P-stakeholder-profile`: D13 PASS versus runner people research because it adds grounded public-professional background, working-style signals, and explicit evidence basis. D14 PASS. D15 PASS. D16 WEAK if callers overfeed public-post context; the excerpt caps must stay enforced. D17 PASS. D18 N/A. D19 PASS with the stated input caps. D20 PASS. D21 PASS. -->

#### 22.3.2 `P-stakeholder-profile`

Purpose: synthesize a public-professional profile for each resolved stakeholder — background, working-style signals, likely priorities — strictly from their public posts/bio and the JD/company context.

```
{SHARED_CONTRACT_HEADER}
{SHARED_TRANSPORT_PREAMBLE}

You are synthesizing a public-professional profile for ONE stakeholder. Emit ONLY evidence-grounded signals.

Inputs:
- stakeholder_record: {stakeholder_record_from_P_stakeholder_discovery}
- role_profile: {role_profile_compact}
- company_profile: {company_profile_compact}
- public_posts_fetched: {list_of_source_ids_for_their_posts}

Input packing constraints:
- public_posts_fetched may include at most 5 post/article excerpts.
- Each excerpt must be <= 240 chars.
- Combined public-post payload must stay <= 1,200 chars.

Rules:
- ONLY summarize what they have publicly said or published in a professional capacity.
- NEVER speculate about private motives, personality, inner state, or protected traits.
- working_style_signals must be derived from public posts, talks, or articles — not from job title alone.
- likely_priorities must cite at least one source_id per bullet.
- If public_posts_fetched is empty or all tertiary, mark all inferred fields with band="low" and add an `unresolved_markers` note.

Output schema (JSON only):
{
  "stakeholder_ref": "<name or candidate_rank>",
  "public_professional_background": {
    "career_arc": "<2–3 sentences summarizing career>",
    "notable_prior_companies": [<str>, ...],
    "specializations": [<str>, ...],
    "source_ids": [...]
  },
  "public_communication_signals": {
    "topics_they_post_about": [<str>, ...],
    "tone": "direct|reflective|promotional|teaching|unknown",
    "cadence": "frequent|occasional|rare|unknown",
    "source_ids": [...]
  },
  "working_style_signals": [<bullet, each with source_ids>, ...],
  "likely_priorities": [<3–7 bullets, each with source_ids AND tied to JD/role/company context>],
  "relationship_to_role": "<1 sentence>",
  "evidence_basis": "<summary of what the signals are grounded in>",
  "unresolved_markers": [<str>, ...],
  "sources": [...],
  "evidence": [...],
  "confidence": {"score": 0.0, "band": "...", "basis": "..."}
}
```

### 22.4 Phase 4 — Outreach Guidance

Phase 4 introduces one prompt — richer, safer, and narrower than `SYSTEM_PROMPT_OUTREACH` and the `outreach_service.py` persona prompts.

<!-- Review rubric D13–D21 for `P-stakeholder-outreach-guidance`: D13 PASS versus `src/layer5/people_mapper.py:387-501` and `src/services/outreach_service.py:49-184` because it produces guidance instead of fabricated copy, with per-bullet evidence/confidence and explicit abstention. D14 PASS after the output was aligned to §8 top-level aliases. D15 PASS because low/unresolved identity now blocks guidance emission. D16 PASS after fake familiarity, guessed motives, and private-channel tactics were banned. D17 PASS. D18 PASS — the tailoring matrix is concrete enough for a downstream writer. D19 PASS. D20 PASS with enum-like `basis` / `dimension` fields. D21 PASS. -->

#### 22.4.1 `P-stakeholder-outreach-guidance` (upgrade of `SYSTEM_PROMPT_OUTREACH` + `CONNECTION_SYSTEM_PROMPT_PERSONA` + `INMAIL_SYSTEM_PROMPT_PERSONA`)

Purpose: emit evidence-grounded guidance blocks (NOT full copy) that downstream outreach workflows can safely use. Iteration 4.1.3 produces GUIDANCE, not messages.

```
{SHARED_CONTRACT_HEADER}

You are producing evidence-grounded outreach GUIDANCE for ONE stakeholder. You are NOT writing the outreach message itself — a downstream worker will do that. Your job is to give that worker a safe, grounded, stakeholder-type-appropriate briefing.

Inputs:
- stakeholder_record: {stakeholder_record}
- stakeholder_profile: {stakeholder_profile}
- role_profile: {role_profile_compact}
- company_profile: {company_profile_compact}
- jd_facts: {jd_facts_compact}

Tailoring matrix (select by stakeholder_type):
- recruiter: role-match clarity, logistics, fit, signal efficiency, ATS-keyword density.
- hiring_manager: mandate understanding, execution value, relevant ownership, peer-level technical fluency.
- executive_sponsor: business impact, leverage, org-level outcomes; extreme brevity.
- peer_technical: technical credibility, collaboration, problem fit; low-friction opener.

Guidance rules (MANDATORY):
- Each bullet in `what_they_likely_care_about` MUST cite ≥1 source_id OR ≥1 JD/role/company evidence reference.
- `initial_cold_interaction_guidance` bullets MUST be tailored to the stakeholder_type above — a recruiter bullet is NOT interchangeable with a hiring_manager bullet.
- `avoid_in_initial_contact` bullets MUST be specific to this stakeholder/company/role — generic advice ("avoid jargon") is a fail.
- NEVER speculate about inner psychology. NEVER claim to know their motivations. Use uncertainty language ("likely", "based on public posts") whenever a claim is inferred.
- NEVER suggest covert-influence tactics, fake familiarity, manufactured urgency, or flattery not grounded in their actual public work.
- NEVER reference protected traits, politics, religion, family status, or health.
- NEVER recommend outreach via private channels (personal email, DMs to personal accounts, phone).
- If stakeholder.identity_confidence.band="unresolved" or "low", emit status="unresolved" and skip all guidance bullets — do NOT produce guidance on a stakeholder you cannot place.

Abstain rules:
- If you cannot tie at least 2 `what_they_likely_care_about` bullets to evidence, emit status="partial" with only the bullets you CAN ground.

Output schema (JSON only):
{
  "stakeholder_ref": "<name or candidate_rank>",
  "stakeholder_type": "recruiter|hiring_manager|executive_sponsor|peer_technical|unknown",
  "likely_priorities": [
    {"bullet": "<str>", "basis": "jd|role|company|public_posts|multi", "source_ids": [...]},
    ... (3–7 items)
  ],
  "initial_outreach_guidance": {
    "what_they_likely_care_about": [
      {"bullet": "<str>", "basis": "jd|role|company|public_posts|multi", "source_ids": [...]},
      ... (3–7 items)
    ],
    "initial_cold_interaction_guidance": [
      {"bullet": "<str>", "dimension": "opening_angle|value_signal|credibility_marker|what_to_skip|cta|logistics", "source_ids": [...]},
      ... (3–7 items)
    ],
    "avoid_in_initial_contact": [
      {"bullet": "<str>", "reason": "<short why>", "source_ids": [...]},
      ... (2–5 items)
    ],
    "confidence_and_basis": {
      "score": 0.0,
      "band": "high|medium|low|unresolved",
      "evidence_summary": "<1 sentence>",
      "unresolved_items": [<str>, ...]
    }
  },
  "avoid_points": [
    {"bullet": "<str>", "reason": "<short why>", "source_ids": [...]},
    ... (2–5 items)
  ],
  "evidence_basis": "<1 sentence summary of what the guidance is grounded in>",
  "confidence": {
    "score": 0.0,
    "band": "high|medium|low|unresolved",
    "evidence_summary": "<1 sentence>",
    "unresolved_items": [<str>, ...]
  },
  "status": "completed|partial|unresolved"
}
```

Why this is richer and SAFER than runner: runner outreach prompts produced full `linkedin_connection_message`, `linkedin_inmail`, `email_body` in a single pass — concatenating discovery, synthesis, and copy. The 4.1.3 version (a) separates guidance from copy, (b) requires per-bullet source attribution, (c) aligns the output to stable artifact fields, (d) adds an explicit tailoring matrix, (e) forbids speculation about inner psychology, (f) forbids covert-influence tactics, and (g) requires abstention on low-confidence stakeholders.

### 22.5 Prompt Versioning and Benchmarking

Every prompt above is pinned by `prompt_version` on the artifact:

- `P-transport-preamble@v1`
- `P-application-surface@v1`
- `P-research-company@v1`
- `P-research-role@v1`
- `P-research-application-merge@v1`
- `P-stakeholder-discovery@v1`
- `P-stakeholder-profile@v1`
- `P-stakeholder-outreach-guidance@v1`

Any prompt change bumps the minor version and invalidates the relevant cache (§14.3). Benchmark harness `scripts/benchmark_research_enrichment_4_1_3.py` must pin the prompt_version per run and record it in the benchmark output so runs are comparable over time.

Benchmark metadata must also record:

- prompt_id
- prompt file path
- git SHA of the prompt-library source at run time
- transport tuple (`provider`, `model`, `transport_used`)

Acceptance criteria for promoting a prompt from shadow to live (§17.4) apply per prompt:

- `P-research-company@v1`: company-profile factuality ≥ 0.95, zero protected-trait violations.
- `P-research-role@v1`: role-profile factuality ≥ 0.90, why-now cites ≥1 company signal in ≥ 0.85 of cases.
- `P-application-surface@v1` + `P-research-application-merge@v1`: canonical URL exact-match ≥ 0.90, portal-family accuracy ≥ 0.95.
- `P-stakeholder-discovery@v1`: precision at medium/high confidence ≥ 0.85, zero cross-person merges.
- `P-stakeholder-profile@v1`: zero protected-trait or private-life violations in reviewer audit.
- `P-stakeholder-outreach-guidance@v1`: zero speculative/privacy violations, ≥ 0.85 reviewer-judged actionability.

## Final Recommended Iteration 4.1.3 Plan

Iteration 4.1.3 should preserve the 4.x/4.1 control plane, keep `application_surface` as a separate execution stage, and upgrade `research_enrichment` into the canonical external-intelligence artifact. It should absorb application intelligence as a subdocument, own runner-grade company and role research, add evidence-gated stakeholder intelligence, and add evidence-grounded outreach guidance that is explicitly job-relevant, confidence-scored, and privacy-bounded.

This is the correct continuation of Iterations 1 through 4.1.1 because it closes the current thin-wrapper blackholes without reintroducing a monolith, preserves `level-2` compatibility, uses collection-backed source-of-truth artifacts plus compact snapshot projections, and creates a rollout path where richer research can be benchmarked, shadowed, and cut over safely.

## Deferred Notes

- Consider adding an explicit `interview_process_confidence` field under `role_profile` once there is a real downstream UI or coaching consumer for it. Current wording can stay compact to avoid overcommitting to anonymous-source material.
- Consider expanding the stakeholder/outreach gold set beyond 10 jobs before 100% rollout if reviewer agreement is noisy. Suggested wording: "10 jobs is the minimum shadow gate, not the long-term steady-state benchmark corpus."
- Consider adding an operator-only debug projection for `matched_signal_classes` if the default job detail page proves too dense. Keep it out of the default snapshot unless review workflows need it.

## 23. Review Log

- date: 2026-04-20
- reviewer: codex gpt-5
- commit_sha_of_plan_before: 93a2a17e68a74eaa1e9a2a610e08a0407134db54
- summary: Reviewed the 4.1.3 plan against live stage code, runner-era prompts, and current UI/consumer surfaces. Fixed the main contract drift between §8, §15, and §22; tightened prompt-library safety and validator-enforceable abstention rules; and made flag, cache, and V2-off compatibility behavior explicit.
- blocker_findings:
  - company/application/stakeholder field drift between §8, §15.2, and §22 prompt outputs
  - V2-off compatibility behavior was unspecified
  - prompt library allowed unverified constructed URLs and non-consumer channel fields
- major_findings:
  - cache scope could leak role-specific conclusions across jobs at the same company
  - §10.5 and §18.4 flags were inconsistent
  - §17 thresholds did not include source-coverage/downstream-usefulness gates
  - stakeholder confidence rules were not validator-enforceable
