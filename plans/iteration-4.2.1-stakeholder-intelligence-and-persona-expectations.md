# Iteration 4.2.1 Plan: Stakeholder Intelligence and Persona Expectations

## 1. Objective

Produce a canonical `stakeholder_surface` artifact that resolves the evaluator
side of a single hiring process with two independent, clearly-labeled layers:

1. **Real public-professional stakeholders** when and only when safe public
   evidence supports them.
2. **Explicit inferred stakeholder personas** when real people cannot be safely
   resolved, or when the set of resolved real people does not cover the
   evaluator roles that matter for the role class.

For every stakeholder or persona in scope, emit evaluator-grounded
**CV preference signals** (what this evaluator is likely to optimize for,
what proof style they likely trust, what would likely hurt in their screen)
that `presentation_contract` (4.2.2, 4.2.4, 4.2.5, 4.2.6) consumes.

### 1.1 In scope

- public-professional identity resolution under the 4.1.3 identity ladder
- public-professional decision-style inference per resolved stakeholder
- inferred persona synthesis for uncovered evaluator roles
- evaluator-conditioned CV preference signals (not CV prose)
- explicit coverage accounting: which evaluator roles are real, which are
  inferred, which remain uncovered

### 1.2 Out of scope (belongs elsewhere)

- final CV title, header copy, summary copy, section order, bullet copy
  (see `presentation_contract` / 4.2.2 / 4.2.4)
- pain, proof map, search_terms (see `pain_point_intelligence` / 4.2.3)
- outreach message generation (covered by existing 4.1.3
  `InitialOutreachGuidance` on `StakeholderRecord`; this stage does not
  rewrite that structure)
- candidate evidence matching, STAR selection, master-CV mapping
- private contact routes, clinical profiling, protected-trait inference

### 1.3 Why this stage exists as a sibling to `research_enrichment`

`research_enrichment.stakeholder_intelligence` is the compact seed list used
by 4.1.3 outreach guidance and existing runner consumers. It is a
**discovery-first** artifact with tight prompt budget.

`stakeholder_surface` is the **evaluator-first** canonical layer. It upgrades
the seed list into a richer evaluator model without destabilizing the 4.1.3
contract, and without giving the research stage a second, conflicting job.

## 2. Design Principles

1. **Truth over coverage.** Unresolved is a valid first-class answer.
2. **Identity resolution and persona inference are separate sub-runs.**
   They have different failure modes and different safety envelopes.
3. **Inferred personas never merge into real stakeholder identity.**
   `real_stakeholders[]` and `inferred_stakeholder_personas[]` are disjoint
   by construction. No field on a real record is ever populated by persona
   inference, and no persona is ever stamped with a real name or profile URL.
4. **Public-professional signals only.** No private life, no protected traits,
   no clinical psychology, no manipulative framing, no personal motives.
5. **Evaluator signals, not final document instructions.** This stage emits
   preferences and likely reject signals. `presentation_contract` decides
   section order, title copy, header copy.
6. **Rich artifact, compact snapshot.** Full evidence stays collection-backed;
   the compact projection in `blueprint_assembly.snapshot` only mirrors
   counts, key refs, and short confidence summaries.
7. **Fail open to inferred personas. Fail closed on fabrication and privacy
   drift.** See §9.

## 3. Hard Safety Constraints

Never:

- fabricate names, titles, employers, profile URLs, or LinkedIn slugs
- construct a profile URL from a name and company (e.g. `/in/first-last-slug`)
- infer personal email, phone, home address, or any non-public channel
- infer age, gender, race, religion, politics, health, family status, or
  any other protected trait
- infer private motives, personal psychology, or clinical style
- claim a specific person is the hiring manager without direct evidence
- merge two ambiguous profiles into one person
- carry an identity across companies on name collision alone

Always:

- keep ambiguity explicit via `unresolved_markers` and status fields
- require medium/high identity confidence for a real-person record to persist
- demote weak identities into inferred personas or search-journal notes
- attach `sources[]` and `evidence[]` to every real-person claim

## 4. Stage Placement

Recommended DAG slice (mirrors 4.2 umbrella §6):

```
jd_facts -> classification -> application_surface -> research_enrichment
   -> stakeholder_surface -> pain_point_intelligence -> presentation_contract
```

`stage_registry` wiring:

- `prerequisites = ("jd_facts", "classification", "application_surface", "research_enrichment")`
- `produces_fields = ("stakeholder_surface",)`
- opportunistic readers: `job_inference.semantic_role_model` when available

### 4.1 Relationship to `research_enrichment.stakeholder_intelligence`

- `research_enrichment.stakeholder_intelligence: list[StakeholderRecord]`
  remains the **compact seed list** and remains the input to 4.1.3 outreach
  guidance.
- `stakeholder_surface` **never mutates** the seed list. It reads it, may
  upgrade / dedupe / demote records into its own `real_stakeholders[]`, and
  records the mapping back to the seed via `stakeholder_ref`.
- Both artifacts coexist on the job document. 4.1.3 consumers are unaffected
  by 4.2.1 shipping.

## 5. Canonical Inputs

### 5.1 Required

- `jd_facts.merged_view`
  - title, company, keywords, qualifications, nice_to_haves, expectations,
    identity_signals, weighting_profiles, skill_dimension_profile
- `classification`
  - `primary_role_category`, `secondary_role_categories`, seniority (from
    `jd_facts`), `tone_family`, `ai_taxonomy`
- `application_surface`
  - canonical application URL, ATS vendor, portal family, direct-apply
    signals, `ui_actionability`
- `research_enrichment.company_profile`
- `research_enrichment.role_profile`

### 5.2 Opportunistic

- `research_enrichment.stakeholder_intelligence[]` (seed list)
- `job_inference.semantic_role_model`
- company domain, aliases, official URLs from `company_profile`

### 5.3 Deterministic preflight helpers (built before any LLM call)

- `canonical_company_identity` = `{ canonical_name, canonical_domain,
  aliases[], official_urls[], identity_confidence }` from `company_profile`
- `target_role_brief` = `{ normalized_title, role_family, function,
  department, seniority }` from `jd_facts` + `classification`
- `evaluator_coverage_target[]` = the set of evaluator roles that must be
  represented (real or inferred) for this job; see §6

## 6. Evaluator Coverage Target

### 6.1 Evaluator role enum (canonical)

```
recruiter
hiring_manager
skip_level_leader           # manager's manager, exec sponsor for IC roles
peer_technical              # IC on the target team
cross_functional_partner    # PM, design, data, infra depending on role
executive_sponsor           # exec owner for leadership or strategic roles
```

This enum is shared with `StakeholderRecord.stakeholder_type` by widening:
4.1.3 currently allows `recruiter | hiring_manager | executive_sponsor |
peer_technical | unknown`. 4.2.1 adds `skip_level_leader` and
`cross_functional_partner`. Schema drift is justified: both are evaluator
roles that materially shape CV preference, and neither fits the existing
four cleanly. See §12 for the migration note.

### 6.2 Coverage rules (deterministic, not LLM)

- `recruiter` and `hiring_manager` are **always** in scope.
- `peer_technical` is in scope when:
  - role is IC or hybrid IC/management, and
  - `classification.ai_taxonomy.intensity in {significant, core}` OR
    role family implies hands-on technical evaluation.
- `skip_level_leader` is in scope when:
  - seniority is `staff`, `principal`, `manager`, `senior_manager`, or
    `director` AND an explicit skip-level is plausible (company size, org
    placement from `role_profile.org_placement` when present).
- `cross_functional_partner` is in scope when:
  - JD mentions explicit cross-functional partners, OR
  - `research_enrichment.role_profile.collaboration_map` implies one.
- `executive_sponsor` is in scope when:
  - seniority in `{director, head, vp, c_level}`, OR
  - role is strategic/transformational (first-AI, first-platform, new
    function, greenfield).

### 6.3 Coverage scoring

Emit one row per evaluator role in scope:

```
evaluator_coverage[] {
  role,                  # one of the enum
  required,              # bool (always true if role is in scope)
  status,                # "real" | "inferred" | "uncovered"
  stakeholder_refs[],    # candidate_ranks of real_stakeholders filling this role
  persona_refs[],        # persona_ids of inferred personas filling this role
  coverage_confidence    # ConfidenceDoc
}
```

Rules:

- a real record only fills a coverage slot if its `identity_confidence.band`
  is `medium` or `high` **and** its `stakeholder_type` matches the role.
- an inferred persona fills a coverage slot only if `real` did not.
- if neither filled, status is `uncovered` and a persona MUST be emitted
  unless the entire stage is operating in `inferred_only` mode and the role
  is explicitly skipped with a reason.

## 7. Output Contract

### 7.1 Top-level `stakeholder_surface`

```
StakeholderSurfaceDoc {
  job_id,
  level2_job_id,
  research_enrichment_id,
  prompt_versions { discovery, profile, personas },
  prompt_metadata { discovery?, profile?, personas? },   # PromptMetadata per run
  status,                                                # see §7.4
  capability_flags { web_search, real_discovery_enabled },
  evaluator_coverage_target[],                           # just the enum strings
  evaluator_coverage[],                                  # per §6.3
  real_stakeholders: list[StakeholderEvaluationProfile], # §7.2
  inferred_stakeholder_personas: list[InferredStakeholderPersona], # §7.3
  search_journal: list[SearchJournalEntry],              # §7.5, debug only
  sources: list[SourceEntry],                            # reuses blueprint model
  evidence: list[EvidenceEntry],                         # reuses blueprint model
  confidence: ConfidenceDoc,                             # stage-level
  unresolved_questions: list[str],
  notes: list[str],
  timing: dict,
  usage: dict,
  cache_refs: dict
}
```

All new models use `model_config = ConfigDict(extra="forbid")` to match the
rest of `blueprint_models.py`.

### 7.2 `StakeholderEvaluationProfile` (real stakeholders)

Option A from the previous revision remains correct and is now locked in:
`StakeholderRecord` stays unchanged (it has `extra="forbid"` and a
`sync_alias_fields` validator whose two-signal rule must not regress), and a
sibling model references it.

```
StakeholderEvaluationProfile {
  stakeholder_ref,                  # "candidate_rank:<int>" from the corresponding StakeholderRecord in stakeholder_intelligence, or a stable local id if minted here
  stakeholder_record_snapshot,      # StakeholderRecord (immutable copy at resolution time)
  stakeholder_type,                 # canonical evaluator role enum (§6.1)
  role_in_process,                  # short phrase: screener, mandate-fit, delivery-risk, technical-depth, etc.
  public_professional_decision_style {
    evidence_preference,            # enum: metrics_and_systems | scope_and_ownership | narrative_and_impact | unresolved
    risk_posture,                   # enum: quality_first | speed_first | balanced | unresolved
    speed_vs_rigor,                 # enum: speed_first | balanced | rigor_first | unresolved
    communication_style,            # enum: concise_substantive | narrative | formal | hype_averse | unresolved
    authority_orientation,          # enum: credibility_over_title | title_sensitive | unresolved
    technical_vs_business_bias      # enum: technical_first | balanced | business_first | unresolved
  },
  cv_preference_surface {
    review_objectives[],            # 3-7 evaluator goals (string bullets)
    preferred_signal_order[],       # ordered abstract signal categories, NOT section ids (e.g. "hands-on implementation" not "experience")
    preferred_evidence_types[],     # enum bag: named_systems, scale_markers, metrics, ownership_scope, decision_tradeoffs, team_outcomes, product_outcomes
    preferred_header_bias[],        # short bias tags (e.g. "credibility-first", "low-hype")
    title_match_preference,         # enum: strict | moderate | lenient | unresolved
    keyword_bias,                   # enum: high | medium | low | unresolved
    ai_section_preference,          # enum: dedicated_if_core | embedded_only | discouraged | unresolved
    preferred_tone[],               # short tone tags
    evidence_basis,                 # string, cites public signal or upstream artifact
    confidence: ConfidenceDoc
  },
  likely_priorities: list[GuidanceBullet],         # reuses existing model
  likely_reject_signals: list[GuidanceAvoidBullet],# reuses existing model
  unresolved_markers[],
  sources[],                        # SourceEntry
  evidence[],                       # EvidenceEntry
  confidence: ConfidenceDoc         # covers decision-style + cv_preference inference
}
```

Constraints to prevent CV-instruction drift:

- `preferred_signal_order[]` MUST be abstract signal categories, not CV
  section ids. The canonical section id vocabulary lives in `presentation_
  contract.document_expectations`. Any token matching `^(title|header|
  summary|key_achievements|core_competencies|ai_highlights|experience|
  education)$` is rejected by validator.
- `cv_preference_surface` MUST NOT contain exact title text, exact header
  copy, exact summary copy, or a full section order. Those are owned by
  4.2.2/4.2.4.

### 7.3 `InferredStakeholderPersona`

```
InferredStakeholderPersona {
  persona_id,                       # stable local id: "persona_<role>_<n>"
  persona_type,                     # evaluator role enum (§6.1)
  role_in_process,
  emitted_because,                  # enum: no_real_candidate | real_search_disabled | real_ambiguous | coverage_gap_despite_real
  trigger_basis[],                  # short factual triggers (role class, seniority, ai intensity, gap type)
  coverage_gap,                     # the evaluator role this persona covers
  public_professional_decision_style { ... as §7.2 ... },
  cv_preference_surface { ... as §7.2 ... },
  likely_priorities: list[GuidanceBullet],
  likely_reject_signals: list[GuidanceAvoidBullet],
  unresolved_markers[],
  evidence_basis,                   # MUST explicitly say the persona is inferred from role/company/JD context
  sources[],                        # usually upstream-artifact refs (e.g. "jd_facts", "role_profile") rather than web URLs
  evidence[],
  confidence: ConfidenceDoc         # band is clamped at most "medium"; see §8.4
}
```

Hard rules enforced by validators:

- `name`, `profile_url`, `current_title`, and `current_company` fields MUST
  NOT exist on this model (not declared; `extra="forbid"` rejects them).
- `confidence.band` is coerced to `medium` when higher; `unresolved` and
  `low` are allowed unchanged.
- `evidence_basis` must contain the literal substring `inferred` (guarded
  by a validator to prevent later prompt drift from presenting personas as
  real).

### 7.4 Artifact status

```
status in {
  "completed",         # real discovery ran, coverage filled (real or inferred), no terminal error
  "partial",           # real discovery ran but profile enrichment partially failed; at least one evaluator slot is present
  "inferred_only",     # real discovery skipped (e.g. company unresolved) or produced nothing medium/high
  "unresolved",        # not enough upstream context to even emit inferred personas meaningfully
  "no_research",       # research_enrichment was no_research; inferred personas are emitted from JD+classification only with lower confidence
  "failed_terminal"    # hard safety violation or repeated schema failure; artifact is not persisted beyond a failure record
}
```

### 7.5 `SearchJournalEntry`

```
SearchJournalEntry {
  step,               # "preflight" | "discovery" | "profile" | "personas"
  query,              # redacted query string; no PII
  intent,             # short phrase
  source_type,        # "company_site" | "ats_page" | "public_profile" | "press" | ...
  outcome,            # "hit" | "miss" | "ambiguous" | "rejected_fabrication"
  source_ids[],       # linked to sources[]
  notes
}
```

Search journal is artifact-only. It is **not** mirrored into the compact
snapshot.

## 8. Execution Model

### 8.1 Sub-runs (in order)

1. **Deterministic preflight.** No LLM call. Build
   `canonical_company_identity`, `target_role_brief`,
   `evaluator_coverage_target`. Decide whether real discovery is enabled.
2. **`P-stakeholder-discovery@v2`** (identity-critical).
3. **`P-stakeholder-profile@v2`** (one call per resolved stakeholder; may be
   batched if the model supports it, but output remains one record per
   stakeholder).
4. **`P-inferred-stakeholder-personas@v1`** (one call; emits all missing
   coverage slots).
5. **Deterministic assembly.** Merge into `StakeholderSurfaceDoc`; compute
   `evaluator_coverage[]`; run cross-model validators; decide `status`.

### 8.2 Boundaries

Keep separate:

- discovery (identity-critical, anti-fabrication, web-facing)
- profile enrichment (evidence interpretation over already-resolved people)
- inferred persona synthesis (intentionally non-identity work)

Combine inside profile enrichment:

- public-professional background summary, decision-style inference, and
  `cv_preference_surface` extraction for one person, in one call, over the
  same evidence.

Do not combine:

- discovery with profile enrichment (identity confidence must not be
  adjusted by evidence interpretation)
- profile enrichment with persona synthesis (personas must never inherit
  real-person identity signal)

### 8.3 Preflight gates

- If `company_profile.identity_confidence.band` is `low` or `unresolved`:
  skip real discovery. Set `capability_flags.real_discovery_enabled=false`.
  Proceed to persona synthesis only.
- If web-research capability is disabled by config: skip real discovery.
- If `research_enrichment.status` is `no_research`: run persona synthesis
  from `jd_facts` + `classification` only. Clamp persona confidence bands
  at most `low` unless the role class is extremely standard.

### 8.4 Partial-completion rules

- Discovery succeeds but profile enrichment fails for a given stakeholder:
  keep the real record in `real_stakeholders[]` with
  `public_professional_decision_style` and `cv_preference_surface` absent;
  status becomes `partial`.
- Discovery fails entirely: `status = inferred_only`.
- Persona synthesis fails schema validation: retry once with schema repair.
  If it still fails, emit zero personas and set `status = partial` with a
  note.
- Any fabrication detection (§9.2) triggers `status = failed_terminal` for
  that sub-run; the offending records are dropped; other sub-runs may still
  complete.

## 9. Fail-Open / Fail-Closed Rules

### 9.1 Fail open (preferred over weak real claims)

Fail open to inferred personas when:

- company identity is resolved enough to reason about role context but no
  real stakeholder clears medium confidence
- real discovery is disabled or unavailable
- a real stakeholder of one type was found but another required type is
  uncovered (coverage gap)

### 9.2 Fail closed (hard reject)

Reject and drop the offending record entirely when:

- a candidate record has a constructed profile URL (heuristic: slug derived
  from `name.lower().replace(" ", "-")` with no verification source)
- a candidate's company does not match `canonical_company_identity` within
  alias tolerance (cross-company collision)
- the record lacks `sources[]` or has zero entries in
  `matched_signal_classes`
- the record claims any protected-trait, clinical, or private-motive
  content
- a persona record contains `name`, `profile_url`, `current_title`, or
  `current_company` fields

### 9.3 Precedence

Fail-closed always wins. A coverage gap does not justify lowering identity
standards; emit an inferred persona instead.

## 10. Web Search Strategy

Reuses the 4.1.3 identity ladder. This stage does not invent a new ladder;
it reuses queries and source-trust tiers from `research_enrichment`.

### 10.1 Allowed query families

- `site:<canonical_domain> (team OR leadership OR about) "<department_or_function>"`
- `site:<canonical_domain> careers "<role_family>"`
- `site:linkedin.com/in "<canonical_name>" "<function>"`
- `site:linkedin.com/in "<canonical_name>" recruiter`
- `site:<canonical_domain> ("talent acquisition" OR recruiter OR "engineering manager" OR "head of <function>")`

### 10.2 Stop conditions

Stop when any becomes true:

- 1-2 medium/high candidates exist for the needed evaluator type
- `search_constraints.max_queries` or `max_fetches` exhausted
- evidence remains ambiguous after bounded search

### 10.3 Disallowed

- logged-in-only / paywalled sources
- constructed profile URLs
- cached summaries with no visible public source trail
- cross-company pages relying on name collision
- social chatter that is not professionally relevant

## 11. Model Routing and Escalation

### 11.1 Primary routing

- `P-stakeholder-discovery@v2`: primary `gpt-5.2` (extraction discipline,
  low narrative drift).
- `P-stakeholder-profile@v2`: primary `gpt-5.4` (richer synthesis over
  evidence).
- `P-inferred-stakeholder-personas@v1`: primary `gpt-5.4` (evaluator
  modeling).

### 11.2 Escalation

At most per sub-run:

- 1 primary run
- 1 escalation run (`gpt-5.2 -> gpt-5.4` for discovery only; others do not
  escalate by model)
- 1 schema repair retry (same model, payload echoed back with strict
  schema-only instruction)

Escalate discovery only when company identity is solid AND the first pass
returned only ambiguous / low-confidence candidates AND the role is
high-value by `classification.primary_role_category`.

### 11.3 Benchmark gating

Final model choices are gated by benchmarks per sub-run following the
pattern of `docs/current/decisions/2026-04-21-jd-facts-model-selection.md`.
Defaults above are initial picks, not frozen.

## 12. Schema Impact on `blueprint_models.py`

Minimize drift:

- **Add** `StakeholderEvaluationProfile`, `InferredStakeholderPersona`,
  `EvaluatorCoverageEntry`, `SearchJournalEntry`, `StakeholderSurfaceDoc`.
- **Widen** `StakeholderRecord.stakeholder_type` and a new
  `EvaluatorRole` Literal to include `skip_level_leader` and
  `cross_functional_partner`. This is the one justified drift. Migration:
  existing rows default to `unknown` on read; 4.1.3 outreach guidance
  handles `unknown` without crashing (verify in a stage test).
- **Do not modify** `StakeholderRecord` fields or its `sync_alias_fields`
  validator. The two-signal rule on medium/high stays authoritative.
- **Do not modify** `ResearchEnrichmentDoc`. `stakeholder_surface` is
  referenced from the parent job document, not nested in research.

All new models use `ConfigDict(extra="forbid")` and reuse `ConfidenceDoc`,
`SourceEntry`, `EvidenceEntry`, `GuidanceBullet`, `GuidanceAvoidBullet`,
`PromptMetadata`.

## 13. Prompt Suite

All prompts inherit `SHARED_CONTRACT_HEADER` from
`src/preenrich/blueprint_prompts.py`. The 4.1.3 header already forbids
invented people, URLs, dates, quotes, protected-trait inference, private
contact inference, and ambiguous-profile merging. The 4.2.1 prompts add
stage-specific constraints on top of that header; they do not restate it.

Every prompt:

- is JSON-only, no markdown, no commentary
- declares the exact top-level output keys it expects
- defines an abstention shape (how to emit "unresolved" cleanly)
- has no free-text escape hatch outside `notes[]` and `unresolved_markers[]`

### 13.1 `P-stakeholder-discovery@v2`

**Purpose.** Resolve real public-professional stakeholders using the
identity ladder only. Emit `StakeholderRecord`-shaped records suitable for
consumption by `P-stakeholder-profile@v2`.

**When to run.**

- after `research_enrichment`
- only when `canonical_company_identity.identity_confidence.band` is
  `medium` or `high`
- only when `capability_flags.real_discovery_enabled` is true

**Added instruction lines (on top of `SHARED_CONTRACT_HEADER`).**

- Truth beats coverage. Unresolved is valid and preferred over weak claims.
- Do not construct LinkedIn URLs or infer names from URL slugs.
- Do not merge two ambiguous profiles into one person.
- A real stakeholder must match company identity AND (function OR role
  context) simultaneously.
- Medium/high identity confidence requires a direct signal class
  (`jd_named_person`, `ats_named_person`, `official_team_page_named_person`)
  OR two distinct converging `matched_signal_classes`.
- Target evaluator coverage given; prefer filling uncovered types over
  duplicating covered ones.
- Low/ambiguous candidates belong in `search_journal` notes, not in
  `stakeholder_intelligence`.

**Input bundle.**

```json
{
  "job_id": "...",
  "target_role_brief": {
    "normalized_title": "Senior Applied AI Engineer",
    "role_family": "applied_ai_engineering",
    "function": "engineering",
    "department": "ai_platform",
    "seniority": "senior"
  },
  "canonical_company_identity": {
    "canonical_name": "Example AI",
    "canonical_domain": "example.ai",
    "aliases": ["ExampleAI"],
    "official_urls": ["https://example.ai"],
    "identity_confidence": {"score": 0.88, "band": "high", "basis": "..."}
  },
  "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
  "seed_stakeholders": [],                  // compact refs from research_enrichment.stakeholder_intelligence (no mutation)
  "company_profile_excerpt": {},            // bounded projection
  "role_profile_excerpt": {},
  "application_profile_excerpt": {},
  "jd_excerpt": "trimmed JD text (bounded)",
  "search_constraints": {
    "public_professional_only": true,
    "max_queries": 6,
    "max_fetches": 8
  }
}
```

**Required output shape.**

```json
{
  "stakeholder_intelligence": [
    {
      "stakeholder_type": "recruiter",
      "identity_status": "resolved",
      "identity_confidence": {"score": 0.83, "band": "high", "basis": "..."},
      "identity_basis": "...",
      "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
      "candidate_rank": 1,
      "name": "Jane Doe",
      "current_title": "Senior Technical Recruiter",
      "current_company": "Example AI",
      "profile_url": "https://www.linkedin.com/in/jane-doe-example",
      "source_trail": ["s_company_careers_team", "s_public_profile_1"],
      "function": "recruiting",
      "seniority": "senior",
      "relationship_to_role": "recruiter",
      "likely_influence": "screening_and_process_control",
      "evidence_basis": "Identity only at discovery stage.",
      "confidence": {"score": 0.83, "band": "high", "basis": "..."},
      "unresolved_markers": [],
      "sources": [{"source_id": "s_company_careers_team", "url": "https://example.ai/careers/team", "source_type": "company_site", "trust_tier": "primary"}],
      "evidence": [{"claim": "Jane Doe listed as technical recruiter.", "source_ids": ["s_company_careers_team"]}]
    }
  ],
  "search_journal": [{"step": "discovery", "query": "site:example.ai team recruiter", "intent": "find_recruiter", "source_type": "company_site", "outcome": "hit", "source_ids": ["s_company_careers_team"], "notes": ""}],
  "unresolved_markers": [],
  "notes": []
}
```

**Abstention shape.** If no candidate clears medium confidence for any
requested type:

```json
{"stakeholder_intelligence": [], "search_journal": [...], "unresolved_markers": ["no_medium_high_candidates"], "notes": ["company identity resolved but no medium/high real stakeholder found"]}
```

### 13.2 `P-stakeholder-profile@v2`

**Purpose.** For a single medium/high real stakeholder, emit
`StakeholderEvaluationProfile` fields (decision style, CV preference
surface, likely priorities, likely reject signals).

**When to run.** Only for medium/high resolved stakeholders from discovery.
One call per stakeholder.

**Added instruction lines.**

- Summarize only public-professional signals and role-relevant inference.
- Distinguish what is directly evidenced from what is inferred from public
  professional context.
- `cv_preference_surface` is evaluator signal, not CV instruction. Do not
  emit exact section order, exact title text, exact header text, exact
  summary text, or canonical CV section ids.
- `preferred_signal_order[]` items must be abstract signal categories
  (e.g. "hands-on implementation", "architecture judgment", "business
  impact"), not section ids.
- Mark unresolved rather than forcing a view when evidence is weak.

**Input bundle.**

```json
{
  "stakeholder_record": { /* StakeholderRecord from discovery */ },
  "target_role_brief": { /* as §13.1 */ },
  "company_profile_excerpt": {},
  "role_profile_excerpt": {},
  "application_profile_excerpt": {},
  "jd_excerpt": "trimmed JD text",
  "public_posts_fetched": [
    {"url": "https://example.ai/blog/post-1", "title": "...", "excerpt": "<=240 chars"}
  ],
  "coverage_context": {
    "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
    "real_types_already_found": ["recruiter", "hiring_manager"]
  }
}
```

**Required output shape.**

```json
{
  "stakeholder_ref": "candidate_rank:1",
  "stakeholder_type": "hiring_manager",
  "role_in_process": "mandate_fit_and_delivery_risk_screen",
  "public_professional_decision_style": {
    "evidence_preference": "metrics_and_systems",
    "risk_posture": "quality_first",
    "speed_vs_rigor": "rigor_first",
    "communication_style": "concise_substantive",
    "authority_orientation": "credibility_over_title",
    "technical_vs_business_bias": "technical_first"
  },
  "cv_preference_surface": {
    "review_objectives": ["verify hands-on credibility", "verify system design maturity", "verify production impact"],
    "preferred_signal_order": ["hands-on implementation", "architecture judgment", "production impact", "team enablement"],
    "preferred_evidence_types": ["named_systems", "scale_markers", "metrics", "ownership_scope"],
    "preferred_header_bias": ["execution-first", "architecture-aware", "low-hype"],
    "title_match_preference": "moderate",
    "keyword_bias": "medium",
    "ai_section_preference": "dedicated_if_core",
    "preferred_tone": ["clear", "evidence-first", "non-inflated"],
    "evidence_basis": "Public engineering leadership signals plus role/JD context.",
    "confidence": {"score": 0.74, "band": "medium", "basis": "..."}
  },
  "likely_priorities": [{"bullet": "Strong examples of production AI implementation with clear ownership.", "basis": "role mandate + public posts", "source_ids": ["s_public_post_1"]}],
  "likely_reject_signals": [{"bullet": "Generic AI claims with no production evidence.", "reason": "public posts emphasize rigor", "source_ids": ["s_public_post_1"]}],
  "unresolved_markers": ["No direct evidence of exact team ownership."],
  "sources": [ /* SourceEntry[] */ ],
  "evidence": [ /* EvidenceEntry[] */ ],
  "confidence": {"score": 0.74, "band": "medium", "basis": "..."}
}
```

**Abstention shape.** When evidence is too thin for a given field, emit
the literal value `"unresolved"` for enum fields and an empty list for list
fields, with an explanatory entry in `unresolved_markers[]`.

### 13.3 `P-inferred-stakeholder-personas@v1`

**Purpose.** Emit explicit, labeled evaluator personas for every
uncovered role in `evaluator_coverage_target` where neither real discovery
nor profile enrichment produced a matching record.

**When to run.** After discovery and profile enrichment complete (or were
skipped). One call emits all missing slots.

**Added instruction lines.**

- Emit personas, not people. Never emit a name, profile URL, exact title,
  or employer.
- Label every persona as inferred. `evidence_basis` MUST contain the literal
  word "inferred".
- Use role, company, application, and discovered-stakeholder context to
  shape the evaluator lens.
- Do not model private motives, protected traits, or personal psychology.
- `confidence.band` may not exceed `medium`.
- `cv_preference_surface` constraints from §13.2 apply identically here.

**Input bundle.**

```json
{
  "target_role_brief": { /* as §13.1 */ },
  "canonical_company_identity": { /* as §13.1 */ },
  "company_profile_excerpt": {},
  "role_profile_excerpt": {},
  "application_profile_excerpt": {},
  "classification_excerpt": {"primary_role_category": "...", "ai_taxonomy": {"intensity": "significant"}},
  "jd_excerpt": "trimmed JD text",
  "real_stakeholder_summaries": [{"stakeholder_type": "recruiter", "identity_status": "resolved"}],
  "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
  "missing_coverage_types": ["hiring_manager", "peer_technical"],
  "emission_mode": "coverage_gap"   // or "real_search_disabled" | "real_ambiguous" | "no_research"
}
```

**Required output shape.**

```json
{
  "inferred_stakeholder_personas": [
    {
      "persona_id": "persona_hiring_manager_1",
      "persona_type": "hiring_manager",
      "role_in_process": "mandate_fit_and_delivery_risk_screen",
      "emitted_because": "coverage_gap_despite_real",
      "trigger_basis": ["technical IC role", "production AI mandate", "hiring_manager coverage gap"],
      "coverage_gap": "hiring_manager",
      "public_professional_decision_style": { /* as §13.2 */ },
      "cv_preference_surface": { /* as §13.2 */ },
      "likely_priorities": [{"bullet": "Proof of shipped systems.", "basis": "role class + JD mandate", "source_ids": []}],
      "likely_reject_signals": [{"bullet": "Tool-list CV with weak ownership evidence.", "reason": "role class pattern", "source_ids": []}],
      "unresolved_markers": ["No real hiring-manager identity resolved."],
      "evidence_basis": "Inferred from role class, JD, company context, and uncovered evaluator type.",
      "sources": [],
      "evidence": [],
      "confidence": {"score": 0.68, "band": "medium", "basis": "Role-conditioned inferred evaluator persona."}
    }
  ],
  "unresolved_markers": [],
  "notes": []
}
```

**Abstention shape.** If a coverage slot cannot be reasoned about even at
the persona level (e.g. `status = no_research` and role class is atypical),
omit the slot from the output and note it in `unresolved_markers[]` with
reason.

## 14. Richness Expectations

For every `StakeholderEvaluationProfile` with `confidence.band` in
`{medium, high}`:

- at least 2 distinct `matched_signal_classes` on the underlying record
- at least 2 `sources[]` and 2 `evidence[]` entries on the profile
- 3-7 `cv_preference_surface.review_objectives` or
  `preferred_signal_order` items combined
- 3-6 `likely_priorities[]` bullets
- at least 2 `likely_reject_signals[]` bullets

For every `InferredStakeholderPersona`:

- at least 3 evaluator preference signals across `decision_style` fields
  that are not `unresolved`
- at least 2 `likely_reject_signals[]` bullets
- explicit `emitted_because` and `coverage_gap`
- explicit `trigger_basis[]` with at least 2 entries

Weak evidence lowers richness rather than triggering invention.

## 15. Snapshot, Storage, and Cache Policy

### 15.1 Compact snapshot projection

`blueprint_assembly.snapshot` mirrors only:

- `stakeholder_surface.status`
- counts per evaluator role: `{role, real_count, inferred_count}`
- a list of `{role, status}` entries (1 per evaluator role in scope)
- stage-level `confidence.band` and `confidence.score`
- `stakeholder_surface` artifact ref

Full `real_stakeholders[]`, `inferred_stakeholder_personas[]`,
`search_journal[]`, `sources[]`, and `evidence[]` stay collection-backed.

### 15.2 Cache policy

- real discovery cache: short TTL, scoped by `(canonical_domain,
  target_role_brief.role_family, target_role_brief.seniority)`. Not scoped
  on company alone.
- profile enrichment cache: same scope plus `stakeholder_ref`.
- inferred persona cache: recompute cheaply per job; do not cache
  aggressively because role-class context shifts persona shape.

## 15.5 Langfuse tracing

Inherits the 4.2 umbrella tracing contract (see
`plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
§8.8) verbatim. Stage-specific rules follow.

**Canonical spans for `stakeholder_surface`.**

- `scout.preenrich.stakeholder_surface` — the stage body span. Output
  metadata must include `real_discovery_enabled`, `real_candidates_found`,
  `real_profiles_completed`, `inferred_personas_emitted`, `coverage_gaps`,
  `overall_status`, `confidence_band`, `upstream_no_research`.
- `scout.preenrich.stakeholder_surface.research.discovery` — the live
  identity-ladder Codex call. Provider/model/transport/duration/outcome and
  `schema_valid` are required. Candidate counts go in metadata;
  per-candidate span names are forbidden.
- `scout.preenrich.stakeholder_surface.research.profile` — per-candidate
  profile enrichment calls. `candidate_rank` is a metadata field, never part
  of the span name. Operators distinguish candidates via metadata filtering.
- `scout.preenrich.stakeholder_surface.research.personas` — the inferred
  persona emission call when real coverage is incomplete.

**Metadata contract extensions (stage-local).**

- `real_discovery_enabled`, `coverage_target`, `filled_roles`,
  `missing_roles`, `upstream_no_research`, `identity_ladder_version`,
  `require_source_attribution`.
- For discovery: `candidate_count`, `search_journal_entries_count`,
  `identity_confidence_band_distribution`.
- For profile calls: `candidate_rank`, `identity_confidence_band`,
  `public_posts_fetched_count`, `fail_open_to_identity_only`.

**Cache boundaries.** Company-scoped and role-scoped cache reads/writes
(`stakeholder_identity_cache`, `stakeholder_profile_cache`) are traced as
events, not spans: `scout.preenrich.stakeholder_surface.cache.hit` and
`scout.preenrich.stakeholder_surface.cache.miss` with `cache_key`,
`cache_layer`, and `transport_version` in metadata.

**Fail-open transitions.** The stage-span output must record when the stage
fails open to inferred personas (`fail_open_reason`: one of
`discovery_disabled`, `identity_below_threshold`, `discovery_failed`,
`upstream_no_research`). This is the single most useful piece of telemetry
for operators debugging weak stakeholder output.

**Parallelism.** If discovery and profile calls are parallelized, spans are
ended in-thread before the orchestrator ends the stage span. Shared
`ctx.tracer` usage across threads is expected.

## 16. Tests and Evals

### 16.1 Unit tests (`tests/unit/preenrich/`)

- `StakeholderEvaluationProfile` schema validation (extra=forbid, section-
  id rejection in `preferred_signal_order`, required fields)
- `InferredStakeholderPersona` schema validation (no name/profile_url/
  current_title/current_company fields accepted; `evidence_basis` must
  contain "inferred"; `confidence.band` clamped to `medium`)
- `EvaluatorCoverageEntry` validation (`status` transitions, refs are
  disjoint with persona_refs)
- `StakeholderRecord` widened `stakeholder_type` accepts new values and
  keeps the `sync_alias_fields` two-signal rule intact
- constructed-URL rejector (heuristic: slug-from-name detector)
- cross-company mismatch rejector
- persona confidence band clamp
- coverage-target heuristic (role-class, seniority, ai-intensity rules)

### 16.2 Stage tests (`tests/unit/preenrich/test_stakeholder_surface.py`)

- company unresolved -> `status = inferred_only`, personas emitted
- discovery succeeds, profile partial -> `status = partial`, record kept
  with absent decision-style
- discovery finds recruiter only, hiring_manager coverage gap -> inferred
  hiring_manager persona emitted, coverage entry shows `status=inferred`
- ambiguous cross-company profile match -> rejected, search journal notes
  `outcome=rejected_fabrication`
- constructed LinkedIn URL -> rejected
- public-professional-only constraint preserved (prompt integration test
  with fixtures containing protected-trait content -> output drops those
  tokens and adds a note)
- `no_research` upstream -> personas emitted from jd_facts+classification
  with confidence clamped to `low`
- seed list from `research_enrichment.stakeholder_intelligence` is read,
  not mutated (asserted by snapshot comparison)

### 16.3 Benchmark gates (curated jobs, reviewed)

Must pass before default-on rollout:

- medium/high real stakeholder precision: `>= 0.85`
- fabricated real stakeholder rate: `= 0`
- fabricated profile URL rate: `= 0`
- private-channel suggestion rate: `= 0`
- protected-trait inference rate: `= 0`
- reviewer usefulness for `cv_preference_surface` on real records: `>= 0.85`
- reviewer usefulness for inferred personas: `>= 0.80`
- coverage fill rate (real + inferred) across evaluator_coverage_target:
  `>= 0.95`
- real stakeholder recall (medium/high) when company identity is high-
  confidence: `>= 0.60` (lower bar than precision; we accept missing a
  real person more readily than inventing one)

Kill-switch: if any of the zero-rate safety gates is breached in
production on a reviewed sample of 50 jobs, disable real discovery via
capability flag and run personas-only until the breach is rooted out.

### 16.4 Review rubric

Reviewers judge:

- factual correctness of real identity (company + function + role fit)
- usefulness of evaluator lens per record
- usefulness of `cv_preference_surface` signals for downstream synthesis
- honesty of uncertainty handling
- absence of privacy / manipulative / protected-trait content
- disjointness of real vs inferred layers (zero leakage in names or URLs)

## 17. Implementation Order

1. Extend `src/preenrich/blueprint_models.py` with
   `StakeholderEvaluationProfile`, `InferredStakeholderPersona`,
   `EvaluatorCoverageEntry`, `SearchJournalEntry`,
   `StakeholderSurfaceDoc`; widen `stakeholder_type` enum; add validators
   for constructed URL, cross-company, persona-band clamp, section-id
   rejection, and the "inferred" literal check.
2. Add prompt builders in `src/preenrich/blueprint_prompts.py`:
   `build_stakeholder_discovery_v2`, `build_stakeholder_profile_v2`,
   `build_inferred_stakeholder_personas_v1`. Register versions in
   `PROMPT_VERSIONS`.
3. Implement `src/preenrich/stages/stakeholder_surface.py` (preflight,
   three sub-runs, assembly, status decision).
4. Register stage in `src/preenrich/stage_registry.py` with the
   prerequisites above; wire DAG in `src/preenrich/dag.py`.
5. Extend `src/preenrich/stages/blueprint_assembly.py` with the compact
   snapshot projection from §15.1.
6. Unit and stage tests per §16.
7. Capability flag `preenrich.stakeholder_surface.enabled` (default off).
   Benchmark on curated jobs. Flip default-on only after §16.3 gates pass.

## 18. Rollout and Rollback

### 18.1 Rollout

1. Ship behind capability flag; disabled by default.
2. Shadow-run on a curated 50-job benchmark set; compare against reviewer
   judgments and the current seed-list outputs.
3. Enable for a 100-job canary on production jobs; monitor zero-rate
   safety gates daily.
4. Default-on after 1 week with clean safety gates.
5. Begin migration planning for downstream consumers per §18.3.

### 18.2 Rollback

- Capability flag off instantly disables the stage; downstream (`pain_
  point_intelligence`, `presentation_contract`) must treat an absent
  `stakeholder_surface` as an opportunistic input, not a hard prerequisite
  (confirmed in 4.2 umbrella §6 for stakeholder_surface as an opportunistic
  input to pain_point_intelligence, but a required prerequisite for
  presentation_contract; if flag is off, presentation_contract must fall
  back to role-family defaults per 4.2 §8.2 fail-open rules).

### 18.3 Consumer migration

- 4.2.2 / 4.2.4 / 4.2.5 / 4.2.6 are the primary new consumers. They
  already specify `stakeholder_surface` as a required input.
- 4.1.3 outreach guidance continues to read `research_enrichment.
  stakeholder_intelligence`. Migration to `stakeholder_surface.real_
  stakeholders[]` is out of scope for 4.2.1 and requires its own plan.

## 19. Resolved Decisions and Remaining Open Questions

Resolved in this revision:

- `research_enrichment.stakeholder_intelligence` remains the compact seed
  list. `stakeholder_surface` is the canonical evaluator layer. Both
  coexist. (§4.1)
- Evaluator-conditioned CV preference lives on a sibling
  `StakeholderEvaluationProfile`, not on `StakeholderRecord`. (§7.2)
- Inferred personas fill uncovered evaluator-role gaps even when one real
  stakeholder of a different type exists. Goal is evaluator-lens coverage,
  not headcount. (§6.2)
- Evaluator role enum is widened with `skip_level_leader` and
  `cross_functional_partner`; `StakeholderRecord.stakeholder_type` is
  widened in lockstep. (§6.1, §12)
- `preferred_signal_order[]` uses abstract signal categories, not CV
  section ids; section ids are owned by `presentation_contract.document_
  expectations`. (§7.2)
- Persona `confidence.band` is clamped at `medium` maximum. (§7.3)

Still open (carry to follow-up):

- Should 4.1.3 outreach guidance migrate to read `stakeholder_surface.
  real_stakeholders[]`? Default: no, until a dedicated migration plan.
- Should `executive_sponsor` and `skip_level_leader` merge? Keeping them
  distinct for now because evaluator priorities differ (strategic vs
  delivery-risk).
- How much of `public_posts_fetched` should be cached vs re-fetched per
  run? Default: cache by `(domain, profile_url)` for 7 days, invalidate
  on research_enrichment rehydration.
