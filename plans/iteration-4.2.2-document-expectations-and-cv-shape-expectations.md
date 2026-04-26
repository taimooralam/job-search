# Iteration 4.2.2 Plan: Document Expectations and CV Shape Expectations

## 1. Objective

Produce two peer, candidate-agnostic subdocuments of `presentation_contract`:

1. `document_expectations` — what kind of document this job wants in the
   abstract: document goal, audience variants, proof order, anti-patterns,
   and tone/density/keyword-balance posture. This is the "document thesis"
   layer.
2. `cv_shape_expectations` — the concrete structural shape that follows from
   the thesis: section order, header shape, section emphasis / compression /
   omission, standard ATS envelope, counts, and AI-section decision policy.

Both are derived from enriched job understanding and evaluator surface
signals. Neither describes candidate evidence and neither generates prose.
The later CV skeleton and candidate-aware generation stages consume both.

The prior revision folded `cv_shape` as a nested object under
`document_expectations`. This revision splits them into two peer artifacts
because they have different audiences (thesis vs structural) and benefit
from independent validation, independent debuggability, and independent
eval signal. They remain co-produced in one `presentation_contract` run.

### 1.1 What this stage must answer

- What is the primary document goal (architecture-first, delivery-first,
  leadership-first, AI-first, platform-first, transformation-first, or a
  defined mix)?
- What does each evaluator lens want the document to do, in abstract
  terms?
- What order of proof categories should the document follow?
- What anti-patterns must the document avoid (e.g. tool-list CV, hype
  headers for rigor-first evaluators)?
- What should the concrete CV skeleton look like: section order, header
  density, section length targets, AI section policy, ATS posture,
  seniority signal strength, evidence density?
- What tone, density, and keyword-balance posture should the skeleton
  assume before any candidate evidence enters?

### 1.2 What this stage must NOT answer

- Who is evaluating (owned by 4.2.1 `stakeholder_surface`).
- What proof targets the evaluators actually require (owned by 4.2.3
  `pain_point_intelligence`).
- How the ideal candidate should be framed on paper (owned by 4.2.4
  `ideal_candidate_presentation_model`).
- How to weight experience dimensions (owned by 4.2.5
  `experience_dimension_weights`).
- What cannot be claimed without direct candidate evidence (owned by
  4.2.6 `truth_constrained_emphasis_rules`).
- Final header copy, summary copy, bullet copy, or any CV prose. Final
  copy generation remains governed by
  `docs/current/cv-generation-guide.md` and is out of scope for 4.2.
- Candidate match strategy or evidence retrieval.

### 1.3 Why this stage exists inside 4.2.2 and not another stage

`jd_facts`, `classification`, `research_enrichment`, and `job_inference`
answer "what is this job?". `stakeholder_surface` answers "who is
evaluating?". `pain_point_intelligence` answers "what proof do they need?".
None of them answer "what shape should the document take?". 4.2.2 owns that
question. It is co-produced in `presentation_contract` with 4.2.4/4.2.5/
4.2.6 so the four share one evidence frame, one invalidation key, and one
cross-validation pass (umbrella §5.3).

The current blueprint path has high-level writing guidance in
`cv_guidelines`, but it does not emit a structured document-thesis /
document-shape contract. 4.2.2 makes that contract concrete and consumable.

## 2. Stage Boundary and Peer Relationships

This stage is **co-produced** inside the `presentation_contract` stage with
4.2.4, 4.2.5, and 4.2.6. It is not a standalone DAG node.

Boundary contracts with peer subdocuments:

- **`stakeholder_surface` (4.2.1)** — evaluator lenses live there. 4.2.2
  consumes them to derive audience variants. 4.2.2 never attributes
  preferences to specific named real stakeholders; it reasons in terms of
  evaluator role. 4.2.2 never emits evaluator names, URLs, or identities.
- **`pain_point_intelligence` (4.2.3)** — the `proof_map` and proof
  categories live there. 4.2.2 maps those categories into `proof_order[]`
  and into `section_emphasis[]` priorities. 4.2.2 never invents new proof
  categories outside the canonical enum.
- **`ideal_candidate_presentation_model` (4.2.4)** — candidate framing
  (`visible_identity`, `acceptable_titles`, `proof_ladder`, `tone_profile`)
  lives there. 4.2.2 may read same-run 4.2.4 output but is not the source
  of those fields. 4.2.2 owns `title_strategy` as a policy enum; 4.2.4
  owns the list of acceptable titles and the candidate framing.
  `cv_shape_expectations.title_strategy` must equal
  `ideal_candidate_presentation_model.title_strategy` after
  cross-validation.
- **`experience_dimension_weights` (4.2.5)** — numeric dimension weights
  live there. 4.2.2 does not emit weights. 4.2.2 may emit section-level
  emphasis tags (`architecture`, `delivery`, `leadership`, `ai`,
  `platform`) and rely on 4.2.5 to set the numeric distribution.
- **`truth_constrained_emphasis_rules` (4.2.6)** — anti-claim policy rules
  live there. 4.2.2's `anti_patterns[]` is document-shape advice (e.g.
  "no tool-list CV", "no hype header"), not claim-level forbidden patterns.
  4.2.6 converts 4.2.2 shape rules into enforceable claim policies where
  needed. 4.2.2 never authors `Rule[]` records in 4.2.6's schema.
- **Final `presentation_contract`** — the four subdocuments co-persist in
  one `PresentationContractDoc`. 4.2.2 is two of those four subdocuments.
- **Final copy generation (out of 4.2)** — consumes 4.2.2 as input;
  4.2.2 never consumes it.

Cross-subdocument invariants (enforced by deterministic validator in
`presentation_contract`):

- `cv_shape_expectations.title_strategy` ==
  `ideal_candidate_presentation_model.title_strategy`
- `cv_shape_expectations.ai_section_policy` is consistent with
  `classification.ai_taxonomy.intensity` (mapping in §7.4)
- `cv_shape_expectations.section_order[]` ⊆ canonical section id enum
- `document_expectations.proof_order[]` ⊆ canonical proof-category enum
  declared by 4.2.3
- `document_expectations.audience_variants` ⊆
  `stakeholder_surface.evaluator_coverage_target`
- `cv_shape_expectations.section_emphasis[].category` ⊆ canonical proof-
  category enum; keys consistent with dimension enum where applicable
- failure of any invariant fails the whole `presentation_contract` run
  and falls back to role-family defaults per umbrella §8.2

## 3. Required and Optional Inputs

### 3.1 Required

- `jd_facts.merged_view`
  - title, normalized title, keywords, qualifications, nice_to_haves,
    expectations, identity_signals, weighting_profiles,
    skill_dimension_profile, team_context
- `classification`
  - `primary_role_category`, `secondary_role_categories`, seniority,
    `tone_family`, `ai_taxonomy.intensity`
- `research_enrichment`
  - `company_profile` (status, signals, identity confidence)
  - `role_profile` (mandate, business impact, evaluation signals)
  - `application_profile` (ATS vendor family, apply channel)
- `stakeholder_surface`
  - `evaluator_coverage_target[]`
  - per-role `cv_preference_surface` projections
  - per-role `preferred_signal_order[]`, `preferred_evidence_types[]`
- `pain_point_intelligence`
  - `proof_map[]` (pain → proof category)
  - `bad_proof_patterns[]`

### 3.2 Opportunistic (allowed, not required)

- `job_inference.semantic_role_model`
- same-run peer `ideal_candidate_presentation_model` (when produced in the
  same `presentation_contract` call)
- current `cv_guidelines` (for prior-art signal only; not authoritative)
- rubric priors from `docs/current/cv-generation-guide.md` and
  `src/layer6_v2/prompts/grading_rubric.py`

### 3.3 Deterministic preflight helpers (built before any LLM call)

- `role_thesis_priors`: role-family-indexed defaults for goal, section
  order, ai policy, ATS pressure (seed from existing `cv-generation-guide.md`
  §6 role guidance).
- `evaluator_axis_summary`: a compressed per-role bag of
  `{role, top_review_objectives[], top_preferred_evidence_types[],
  reject_signals[], ai_section_preference}` projected from
  `stakeholder_surface`.
- `proof_order_candidates`: ordered list of proof categories derived from
  `pain_point_intelligence.proof_map` weighted by frequency and severity,
  used as a strong prior in the prompt.
- `ats_envelope_profile`: derived from
  `research_enrichment.application_profile.ats_vendor_family` and
  `classification.primary_role_category` (known-ATS rules: keyword-heavy
  posture when ATS vendor implies aggressive parsing; standard otherwise).

Preflight never fails the stage. It degrades to role-family priors when
upstream signals are thin and records that degradation in a `notes[]`
entry.

## 4. Output Artifact Contract

`presentation_contract` persists both subdocuments side-by-side. Each has
its own schema, its own validators, and its own debug block.

### 4.1 `document_expectations`

```text
document_expectations {
  primary_document_goal,                # enum; see §4.3
  secondary_document_goals[],           # 0-2 enum values
  audience_variants {                   # one entry per evaluator role in scope
    <evaluator_role>: {
      tilt[],                           # 2-6 short bias tags
      must_see[],                       # 2-6 abstract signal categories
      risky_signals[],                  # 0-5 abstract anti-signals
      rationale                         # <=240 chars
    }
  },
  proof_order[],                        # ordered canonical proof-category ids
  anti_patterns[],                      # 2-6 shape anti-pattern ids, see §4.5
  tone_posture {
    primary_tone,                       # enum: evidence_first | operator_first | architect_first | leader_first | balanced
    hype_tolerance,                     # enum: low | medium | high
    narrative_tolerance,                # enum: low | medium | high
    formality                           # enum: informal | neutral | formal
  },
  density_posture {
    overall_density,                    # enum: low | medium | high
    header_density,                     # enum: compact | balanced | proof_dense
    section_density_bias[],             # list of {section_id, bias: low|medium|high}
  },
  keyword_balance {
    target_keyword_pressure,            # enum: low | medium | high | extreme
    ats_mirroring_bias,                 # enum: conservative | balanced | aggressive
    semantic_expansion_bias             # enum: narrow | balanced | broad
  },
  unresolved_markers[],                 # strings describing what could not be resolved
  rationale,                            # 1-3 short paragraphs
  debug_context: DocumentExpectationsDebug,  # §4.6
  confidence: ConfidenceDoc,
  evidence[]                            # EvidenceEntry refs to upstream artifacts
}
```

### 4.2 `cv_shape_expectations`

```text
cv_shape_expectations {
  title_strategy,                       # enum: exact_match | closest_truthful | functional_label | unresolved
  header_shape {
    density,                            # enum: compact | balanced | proof_dense  (mirrors document_expectations.density_posture.header_density)
    include_elements[],                 # subset of: ["name", "current_or_target_title", "tagline", "location", "links", "proof_line", "differentiator_line"]
    proof_line_policy,                  # enum: required | optional | omit
    differentiator_line_policy          # enum: required | optional | omit
  },
  section_order[],                      # ordered canonical section ids
  section_emphasis[] {                  # 1 entry per section id that needs emphasis guidance
    section_id,
    emphasis,                           # enum: highlight | balanced | secondary | compress | omit
    focus_categories[],                 # proof-category enum ids this section should lean into
    length_bias,                        # enum: short | medium | long
    ordering_bias,                      # enum: outcome_first | scope_first | tech_first | narrative_first
    rationale                           # <=240 chars
  },
  ai_section_policy,                    # enum: required | optional | discouraged | embedded_only
  counts {
    key_achievements_min,               # int, 0-10
    key_achievements_max,               # int, 0-10
    core_competencies_min,              # int, 0-14
    core_competencies_max,              # int, 0-14
    summary_sentences_min,              # int, 0-8
    summary_sentences_max               # int, 0-8
  },
  ats_envelope {
    pressure,                           # enum: standard | high | extreme
    format_rules[],                     # short rule ids, e.g. "single_column", "no_tables_in_experience"
    keyword_placement_bias              # enum: top_heavy | balanced | bottom_heavy
  },
  evidence_density,                     # enum: low | medium | high
  seniority_signal_strength,            # enum: low | medium | high
  compression_rules[],                  # ordered list of rule ids when CV must be shortened; see §4.8
  omission_rules[],                     # sections/fields that may be omitted when irrelevant; see §4.8
  unresolved_markers[],
  rationale,
  debug_context: CvShapeExpectationsDebug,  # §4.6
  confidence: ConfidenceDoc,
  evidence[]
}
```

### 4.3 Canonical `primary_document_goal` enum

```
architecture_first
delivery_first
leadership_first
ai_first
platform_first
transformation_first
balanced
unresolved
```

### 4.4 Canonical section id enum (used by `section_order[]` and
`section_emphasis[].section_id`)

```
header
summary
key_achievements
core_competencies
ai_highlights
experience
education
certifications
projects
publications
awards
```

New section ids may not be introduced by the prompt. They must be added to
the enum in `blueprint_models.py` and bumped in the prompt version.

### 4.5 Canonical anti-pattern id enum

```
tool_list_cv
hype_header
metrics_without_scope
scope_without_metrics
titles_without_proof
ai_claims_without_evidence
buzzword_stacking
narrative_only_summary
skill_cloud_without_ordering
generic_mission_restatement
```

Anti-pattern ids are document-shape patterns (what the CV shape should not
look like). Claim-level forbidden patterns belong to 4.2.6.

### 4.6 Debug context

Every run must preserve a debug block inside each subdocument (not mirrored
into the compact snapshot). Purpose: make failures, partial outputs, and
drift diagnosable without re-running the LLM.

```text
DocumentExpectationsDebug {
  input_summary {                        # bounded projection of what the prompt saw
    role_family,
    seniority,
    ai_intensity,
    evaluator_roles_in_scope[],
    proof_category_frequencies {<cat>: int},
    top_keywords_top10[],
    company_identity_band,
    research_status,
    stakeholder_surface_status
  },
  defaults_applied[],                    # ids of role-family priors applied (e.g. "role_family_delivery_first_default")
  normalization_events[],                # what the ingress normalizer changed (§5)
  richer_output_retained[],              # keys kept from richer-than-schema LLM output
  rejected_output[],                     # {path, reason} entries rejected at ingress
  retry_events[]                         # schema-repair retries, if any
}
CvShapeExpectationsDebug { ... same shape, populated for this subdocument ... }
```

The debug block is collection-backed only (never in snapshot). It is
stripped from public-facing projections. Size is capped at 16KB per
subdocument.

### 4.7 Cross-subdocument consistency (asserted in validator)

- `cv_shape_expectations.header_shape.density` ==
  `document_expectations.density_posture.header_density`
- `cv_shape_expectations.ai_section_policy` is consistent with
  `classification.ai_taxonomy.intensity` per table in §7.4
- every `section_id` in `cv_shape_expectations.section_order` and
  `section_emphasis` appears in the canonical section enum
- every proof category referenced in
  `document_expectations.proof_order` and
  `cv_shape_expectations.section_emphasis[].focus_categories` appears in
  the canonical proof-category enum
- every `evaluator_role` key in `document_expectations.audience_variants`
  appears in `stakeholder_surface.evaluator_coverage_target`
- `counts.*_min <= counts.*_max` for every min/max pair

### 4.8 Compression and omission rules

`compression_rules[]` and `omission_rules[]` are ordered lists of rule ids.
Canonical rule ids include:

```
compress_core_competencies_first
compress_certifications_second
compress_projects_third
omit_publications_if_unused_in_role_family
omit_awards_if_unused_in_role_family
omit_ai_highlights_if_policy_discouraged
omit_projects_if_experience_is_dominant
```

Additional rule ids must be added to the enum, not invented by the prompt.

## 5. Richer-Output Normalization Strategy

This stage inherits the 4.1.3.1 principle: **validation is loose on shape
and strict on truth.** Richer prompt output is expected because the models
at current routing will naturally produce evidence-bearing structure,
rationale, and richer section-level guidance than the canonical contract
strictly requires. Flattening such richer output is explicitly rejected.

### 5.1 Ingress rules

At ingress (before Pydantic validation), a normalizer must:

- accept aliases and map them to canonical field names (e.g. `goal` →
  `primary_document_goal`, `shape.sections` → `section_order`,
  `ai_policy` → `ai_section_policy`, `order` → `section_order`)
- coerce scalar/list/dict drift into canonical shape (e.g.
  `section_emphasis` delivered as a map → list of entries)
- absorb unknown-but-grounded wrappers into `debug_context.
  richer_output_retained[]` rather than discarding them
- lower-case enum values before enum check
- coerce `null` to canonical absence (omit) for optional fields
- normalize `confidence` to the canonical `{score, band, basis}` shape

### 5.2 Strict-on-truth rules (fail closed at ingress)

- reject any `section_id` outside the canonical enum
- reject any proof category outside the canonical enum
- reject any anti-pattern id outside the canonical enum
- reject any `ai_section_policy` value that contradicts
  `classification.ai_taxonomy.intensity` (table in §7.4)
- reject any `audience_variants` key not in
  `stakeholder_surface.evaluator_coverage_target`
- reject any field that looks candidate-specific (see §5.4)

### 5.3 Richer-output retention

When the LLM emits fields not in the canonical schema but semantically
useful (e.g. extra per-evaluator narrative, per-section tone notes), the
normalizer must:

- try to map the extra field to a canonical field (e.g. a per-evaluator
  `communication_style_tag` → audience_variants[role].tilt)
- if no canonical mapping exists, preserve the field under
  `debug_context.richer_output_retained[]` as a `{key, value, note}`
  entry and record a `notes[]` line so schema evolution can be
  prioritized
- never silently drop richer content; every discarded field must appear
  in `debug_context.rejected_output[]` with a reason

### 5.4 Candidate-leakage detection

A deterministic post-check rejects outputs that contain any of:

- first-person pronouns (`I`, `my`, `we`, `our`) in any string field
- specific company names from the candidate's likely history (none are
  known to this stage, so any proper noun that is not the hiring company
  or a reference framework name is suspect and is flagged into debug)
- tokens matching exact JD candidate names / URLs
- exact numbers that look like achievements (e.g. "40% YoY") unless the
  token appears verbatim in the JD

Leakage triggers `status = partial` with the offending field omitted and
the event logged to `debug_context.rejected_output[]`.

### 5.5 Schema evolution policy

When the same richer field appears in at least 30% of runs over a 100-job
benchmark with clear utility, it is promoted to the canonical schema in a
follow-up plan (not in 4.2.2). Until then it lives in
`debug_context.richer_output_retained[]`.

## 6. Fail-Open / Fail-Closed and Partial Completion

### 6.1 Fail open (preferred over empty output)

- When `stakeholder_surface` is `inferred_only`: emit audience_variants for
  inferred personas only, with `confidence.band <= medium`.
- When `stakeholder_surface` status is `no_research` or `unresolved`:
  emit audience_variants for `recruiter` and `hiring_manager` only (the
  always-in-scope pair), using role-family priors and
  `classification.tone_family`; record `defaults_applied[]`.
- When `pain_point_intelligence` proof_map is thin (<3 entries): derive
  `proof_order[]` from role-family priors with lower confidence and
  populate `rationale`.
- When `research_enrichment.role_profile` is partial: derive
  `primary_document_goal` from `classification.primary_role_category` and
  `seniority`; record the defaulted choice in `rationale`.
- When the ATS vendor family is unknown: default
  `ats_envelope.pressure = standard` and
  `ats_mirroring_bias = balanced`.

Fail-open never produces empty output. The minimum acceptable artifact has:

- `primary_document_goal` populated (possibly `balanced` or `unresolved`)
- `section_order[]` populated with a role-family default order
- `ai_section_policy` populated (possibly `embedded_only` or `discouraged`)
- `audience_variants[recruiter]` and `audience_variants[hiring_manager]`
  populated
- `proof_order[]` populated from priors when pain_point_intelligence is
  thin
- `counts{}` populated with conservative defaults

### 6.2 Fail closed (hard reject, drop offending record)

- candidate-specific assertions anywhere in the output
- section ids outside the canonical enum
- proof categories outside the canonical enum
- anti-pattern ids outside the canonical enum
- `ai_section_policy = required` when
  `classification.ai_taxonomy.intensity in {none, adjacent}`
- `title_strategy = exact_match` when JD title is ambiguous per
  `jd_facts.identity_signals`
- `audience_variants` keys not present in
  `stakeholder_surface.evaluator_coverage_target`
- outputs containing CV prose (headers, summaries, bullets) — rejected
  wholesale per §5.4 and §9

Fail-closed always wins. A coverage gap does not justify lowering policy
standards; emit a conservative default instead.

### 6.3 Partial completion

The artifact carries a per-subdocument status:

```
status in {
  "completed",
  "partial",            # fail-open path was used for one or more fields
  "inferred_only",      # emitted entirely from priors because upstream signals were sparse
  "unresolved",         # minimum artifact could not be assembled meaningfully
  "failed_terminal"     # safety violation; subdocument not persisted
}
```

If either subdocument fails schema validation after one repair retry, the
entire `presentation_contract` run fails and falls back to role-family
defaults per umbrella §8.2.

## 7. Model, Execution, and Routing

### 7.1 Sub-runs inside `presentation_contract` relevant to 4.2.2

1. Deterministic preflight (§3.3).
2. **`P-document-expectations@v1`** (LLM).
3. **`P-cv-shape-expectations@v1`** (LLM).
4. Deterministic assembly and cross-subdocument validation across all
   four subdocuments (4.2.2 + 4.2.4 + 4.2.5 + 4.2.6).

Option (bench-gated): merge (2) and (3) into
**`P-document-and-cv-shape@v1`** when benchmarks show consistent
cross-field agreement; keep split by default until that bench gate passes.

### 7.2 Primary model

- Primary: `gpt-5.4`.
- Baseline for benchmark and regression: `gpt-5.4-mini`.
- No escalation on this subdocument family; one schema-repair retry with
  strict-schema-only instruction.
- No web search on the normal path; synthesis only over upstream artifacts.

### 7.3 Deterministic post-processing

The validator must enforce:

- enum membership for section ids, proof categories, anti-patterns,
  goals, policies
- `counts{}` inequalities (min <= max, within declared ranges)
- cross-subdocument invariants (§4.7)
- candidate-leakage checks (§5.4)
- richer-output retention (§5.3)
- confidence band coherence: if `stakeholder_surface.status in
  {inferred_only, no_research}`, cap `document_expectations.confidence.band
  <= medium`

### 7.4 `ai_section_policy` × `ai_taxonomy.intensity` matrix

```
intensity = core           -> ai_section_policy in {required, optional}
intensity = significant    -> ai_section_policy in {required, optional, embedded_only}
intensity = adjacent       -> ai_section_policy in {optional, embedded_only}
intensity = none           -> ai_section_policy in {embedded_only, discouraged}
```

Any value outside these sets is rejected.

## 8. Prompt Suite (implementation-grade)

Both prompts inherit `SHARED_CONTRACT_HEADER` from
`src/preenrich/blueprint_prompts.py`. That header already forbids CV prose,
fabrication, protected-trait inference, and private data. These prompts
add 4.2.2-specific constraints on top.

### 8.1 `P-document-expectations@v1`

**Purpose.** Emit the document-thesis artifact. No prose. No candidate
evidence. Structured output only, grounded in upstream artifacts.

**When to run.** After `jd_facts`, `classification`,
`research_enrichment`, `stakeholder_surface`, `pain_point_intelligence`
have all completed (at least partially) for this job. One call per run.

**Added instruction lines (on top of `SHARED_CONTRACT_HEADER`).**

- You do not know the candidate. Never reference a specific candidate,
  employer, year, or achievement. No first-person language.
- Produce structure, not prose. Never emit header copy, summary copy, or
  bullet text.
- Use only canonical enums (provided in payload) for
  `primary_document_goal`, `proof_order[]`, `anti_patterns[]`,
  `audience_variants` keys, tone posture values, density posture values,
  keyword balance values.
- `audience_variants` keys MUST be a subset of
  `evaluator_coverage_target` provided in the payload.
- `proof_order[]` MUST be drawn from the canonical proof-category enum in
  the payload and SHOULD be ordered to maximize upstream proof_map
  frequency and severity.
- Evidence-cite upstream artifacts in `evidence[]` by id
  (e.g. `stakeholder_surface.hiring_manager.cv_preference_surface`).
- Unresolved is a valid first-class answer. When evidence is insufficient
  for a field, emit the sentinel value defined in the output shape and
  explain why in `unresolved_markers[]` and `rationale`.
- Prefer richer output: when you have more audience-variant tilt tags,
  more density-bias entries, or more anti-patterns to justify, include
  them; the normalizer will retain them.
- Never attribute preferences to specific named real stakeholders; always
  reason in evaluator-role terms.
- Never emit CV section ids inside any field that should describe
  abstract categories (e.g. tilt tags must not be `summary`).

**Input payload shape.**

```json
{
  "job_id": "...",
  "role_brief": {
    "normalized_title": "Senior Applied AI Engineer",
    "role_family": "applied_ai_engineering",
    "seniority": "senior",
    "tone_family": "operator_architect",
    "ai_intensity": "significant"
  },
  "company_brief": {
    "identity_band": "high",
    "industry": "ai_platform",
    "stage": "growth"
  },
  "research_status": {
    "company_profile_status": "completed",
    "role_profile_status": "partial",
    "application_profile_status": "completed"
  },
  "stakeholder_axis": [
    {
      "role": "recruiter",
      "status": "real",
      "preferred_signal_order": ["credibility", "fit", "impact"],
      "preferred_evidence_types": ["named_systems", "scale_markers"],
      "risky_signals": ["hype", "buzzwords"],
      "ai_section_preference": "dedicated_if_core"
    },
    {
      "role": "hiring_manager",
      "status": "real",
      "preferred_signal_order": ["hands-on implementation", "architecture judgment", "production impact"],
      "preferred_evidence_types": ["named_systems", "scale_markers", "metrics", "ownership_scope"],
      "risky_signals": ["narrative-only", "tool-list"],
      "ai_section_preference": "dedicated_if_core"
    },
    {
      "role": "peer_technical",
      "status": "inferred",
      "preferred_signal_order": ["hands-on implementation", "system_design", "production_impact"],
      "preferred_evidence_types": ["named_systems", "decision_tradeoffs"],
      "risky_signals": ["tool-list"],
      "ai_section_preference": "dedicated_if_core"
    }
  ],
  "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
  "proof_category_frequencies": {
    "architecture": 5,
    "metric": 4,
    "ai": 4,
    "reliability": 2,
    "leadership": 1,
    "domain": 1
  },
  "bad_proof_patterns": ["generic_ai_claim_without_system", "tool_list_without_ownership"],
  "enums": {
    "primary_document_goal": ["architecture_first", "delivery_first", "leadership_first", "ai_first", "platform_first", "transformation_first", "balanced", "unresolved"],
    "proof_category": ["metric", "architecture", "leadership", "domain", "reliability", "ai", "stakeholder"],
    "anti_pattern": ["tool_list_cv", "hype_header", "metrics_without_scope", "scope_without_metrics", "titles_without_proof", "ai_claims_without_evidence", "buzzword_stacking", "narrative_only_summary", "skill_cloud_without_ordering", "generic_mission_restatement"],
    "primary_tone": ["evidence_first", "operator_first", "architect_first", "leader_first", "balanced"],
    "hype_tolerance": ["low", "medium", "high"],
    "narrative_tolerance": ["low", "medium", "high"],
    "formality": ["informal", "neutral", "formal"],
    "density": ["low", "medium", "high"],
    "header_density": ["compact", "balanced", "proof_dense"],
    "keyword_pressure": ["low", "medium", "high", "extreme"],
    "ats_mirroring_bias": ["conservative", "balanced", "aggressive"],
    "semantic_expansion_bias": ["narrow", "balanced", "broad"]
  }
}
```

**Required output shape.**

```json
{
  "document_expectations": {
    "primary_document_goal": "architecture_first",
    "secondary_document_goals": ["ai_first"],
    "audience_variants": {
      "recruiter": {
        "tilt": ["credibility-first", "low-hype", "named-systems-visible"],
        "must_see": ["production_ai_scope", "named_production_systems", "scale_markers"],
        "risky_signals": ["buzzword_stacking", "generic_mission_restatement"],
        "rationale": "Technical recruiter screens for credibility and role-fit signals; public posts prefer evidence over narrative."
      },
      "hiring_manager": {
        "tilt": ["execution-first", "architecture-aware", "low-hype"],
        "must_see": ["hands_on_implementation", "architecture_judgment", "named_production_systems", "ownership_scope"],
        "risky_signals": ["narrative_only_summary", "tool_list_cv"],
        "rationale": "Hiring manager mandate is production AI delivery; rigor-first decision style implied by public signals."
      },
      "peer_technical": {
        "tilt": ["hands-on", "system-design-visible", "evidence-first"],
        "must_see": ["named_production_systems", "decision_tradeoffs", "production_impact"],
        "risky_signals": ["tool_list_cv", "ai_claims_without_evidence"],
        "rationale": "Peer-IC lens prefers hands-on implementation depth and architecture judgment over narrative framing."
      }
    },
    "proof_order": ["architecture", "ai", "metric", "reliability", "leadership", "domain", "stakeholder"],
    "anti_patterns": ["tool_list_cv", "hype_header", "ai_claims_without_evidence", "narrative_only_summary"],
    "tone_posture": {
      "primary_tone": "operator_first",
      "hype_tolerance": "low",
      "narrative_tolerance": "low",
      "formality": "neutral"
    },
    "density_posture": {
      "overall_density": "high",
      "header_density": "proof_dense",
      "section_density_bias": [
        {"section_id": "summary", "bias": "medium"},
        {"section_id": "experience", "bias": "high"},
        {"section_id": "key_achievements", "bias": "high"},
        {"section_id": "core_competencies", "bias": "medium"}
      ]
    },
    "keyword_balance": {
      "target_keyword_pressure": "high",
      "ats_mirroring_bias": "balanced",
      "semantic_expansion_bias": "narrow"
    },
    "unresolved_markers": [],
    "rationale": "Architecture-first goal: JD mandates production AI systems with named scope; hiring manager prefers rigor-first evidence; peer-IC lens reinforces system-design visibility; recruiter lens demands named-system credibility. AI-first as secondary because ai_intensity=significant.",
    "confidence": {"score": 0.82, "band": "high", "basis": "Converging signals across JD, role mandate, and stakeholder surface."},
    "evidence": [
      {"claim": "Hiring manager prefers rigor-first with named-system evidence.", "source_ids": ["stakeholder_surface.hiring_manager.cv_preference_surface"]},
      {"claim": "Role mandate emphasizes production AI systems with named scope.", "source_ids": ["research_enrichment.role_profile.mandate"]}
    ]
  }
}
```

**Abstention shape.** When evidence is too thin to choose a goal:

```json
{
  "document_expectations": {
    "primary_document_goal": "balanced",
    "secondary_document_goals": [],
    "audience_variants": {
      "recruiter": {"tilt": ["credibility-first"], "must_see": ["role_fit_signals"], "risky_signals": [], "rationale": "Role-family default."},
      "hiring_manager": {"tilt": ["evidence-first"], "must_see": ["production_evidence"], "risky_signals": [], "rationale": "Role-family default."}
    },
    "proof_order": ["metric", "architecture", "leadership", "domain"],
    "anti_patterns": ["tool_list_cv", "hype_header"],
    "tone_posture": {"primary_tone": "balanced", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
    "density_posture": {"overall_density": "medium", "header_density": "balanced", "section_density_bias": []},
    "keyword_balance": {"target_keyword_pressure": "medium", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
    "unresolved_markers": ["stakeholder_surface_inferred_only", "role_profile_partial"],
    "rationale": "Insufficient upstream evidence to pick a specific goal; emitting role-family balanced defaults with evaluator pair.",
    "confidence": {"score": 0.42, "band": "low", "basis": "Role-family priors applied."},
    "evidence": [{"claim": "Falling back to role-family defaults.", "source_ids": ["classification.primary_role_category"]}]
  }
}
```

**Richness expectations.**

- `audience_variants` populated for every role in
  `evaluator_coverage_target` (omit only when status in
  `{unresolved, no_research}` and the always-in-scope pair is the only
  feasible emission).
- `tilt[]` 2–6 entries per variant.
- `must_see[]` 2–6 entries per variant.
- `proof_order[]` 4–7 entries.
- `anti_patterns[]` 2–6 entries.
- `section_density_bias[]` covers at least `summary`, `experience`,
  `key_achievements`, `core_competencies`.
- `evidence[]` cites at least 3 upstream-artifact refs when confidence
  band is medium or higher.

### 8.2 `P-cv-shape-expectations@v1`

**Purpose.** Given the document thesis from
`P-document-expectations@v1` (read as same-run input) plus upstream
artifacts, emit the concrete structural shape. No prose.

**When to run.** Immediately after `P-document-expectations@v1` in the
same `presentation_contract` run. One call.

**Added instruction lines.**

- You do not know the candidate. No first-person language. No prose.
- Section ids MUST be drawn only from the canonical section enum provided
  in the payload.
- `section_order[]` MUST begin with `header` and MUST include at least
  `summary` (or justify omission via `omission_rules[]`), `experience`,
  and `education`.
- `ai_section_policy` MUST satisfy the intensity matrix in the payload.
- `title_strategy` MUST be consistent with peer
  `ideal_candidate_presentation_model.title_strategy` when that peer is
  provided in the payload.
- `counts.*_min <= counts.*_max` for every pair.
- `section_emphasis[]` entries MUST reference only section ids present
  in `section_order[]`.
- Use only canonical enums.
- Prefer richer output (more `section_emphasis[]` detail, more focused
  `compression_rules[]`); the normalizer retains richer content.
- Unresolved is a valid first-class answer for individual fields;
  rationalize in `unresolved_markers[]` and `rationale`.

**Input payload shape.**

```json
{
  "job_id": "...",
  "role_brief": { /* as §8.1 */ },
  "document_expectations": { /* verbatim output of §8.1 */ },
  "peer_ideal_candidate_presentation_model": { /* optional; when co-produced in same run */
    "title_strategy": "closest_truthful",
    "acceptable_titles": ["Senior Applied AI Engineer", "Applied AI Engineer"],
    "proof_ladder": ["identity", "capability", "proof", "business_outcome"]
  },
  "ai_intensity_matrix": {
    "core":        ["required", "optional"],
    "significant": ["required", "optional", "embedded_only"],
    "adjacent":    ["optional", "embedded_only"],
    "none":        ["embedded_only", "discouraged"]
  },
  "ats_envelope_profile": {
    "ats_vendor_family": "greenhouse",
    "parsing_posture": "standard"
  },
  "enums": {
    "section_id": ["header", "summary", "key_achievements", "core_competencies", "ai_highlights", "experience", "education", "certifications", "projects", "publications", "awards"],
    "title_strategy": ["exact_match", "closest_truthful", "functional_label", "unresolved"],
    "ai_section_policy": ["required", "optional", "discouraged", "embedded_only"],
    "emphasis": ["highlight", "balanced", "secondary", "compress", "omit"],
    "length_bias": ["short", "medium", "long"],
    "ordering_bias": ["outcome_first", "scope_first", "tech_first", "narrative_first"],
    "focus_category": ["metric", "architecture", "leadership", "domain", "reliability", "ai", "stakeholder"],
    "header_density": ["compact", "balanced", "proof_dense"],
    "header_element": ["name", "current_or_target_title", "tagline", "location", "links", "proof_line", "differentiator_line"],
    "proof_line_policy": ["required", "optional", "omit"],
    "ats_pressure": ["standard", "high", "extreme"],
    "format_rule": ["single_column", "no_tables_in_experience", "no_graphics", "ascii_safe", "plain_bullets"],
    "keyword_placement_bias": ["top_heavy", "balanced", "bottom_heavy"],
    "evidence_density": ["low", "medium", "high"],
    "seniority_signal_strength": ["low", "medium", "high"],
    "compression_rule": ["compress_core_competencies_first", "compress_certifications_second", "compress_projects_third"],
    "omission_rule": ["omit_publications_if_unused_in_role_family", "omit_awards_if_unused_in_role_family", "omit_ai_highlights_if_policy_discouraged", "omit_projects_if_experience_is_dominant"]
  },
  "bounds": {
    "key_achievements": {"min": 0, "max": 10},
    "core_competencies": {"min": 0, "max": 14},
    "summary_sentences": {"min": 0, "max": 8}
  }
}
```

**Required output shape.**

```json
{
  "cv_shape_expectations": {
    "title_strategy": "closest_truthful",
    "header_shape": {
      "density": "proof_dense",
      "include_elements": ["name", "current_or_target_title", "tagline", "location", "links", "proof_line"],
      "proof_line_policy": "required",
      "differentiator_line_policy": "optional"
    },
    "section_order": ["header", "summary", "key_achievements", "core_competencies", "ai_highlights", "experience", "education", "certifications", "projects"],
    "section_emphasis": [
      {"section_id": "summary", "emphasis": "balanced", "focus_categories": ["architecture", "ai", "metric"], "length_bias": "short", "ordering_bias": "outcome_first", "rationale": "Short evidence-first summary aligned to architecture-first thesis."},
      {"section_id": "key_achievements", "emphasis": "highlight", "focus_categories": ["architecture", "ai", "metric", "reliability"], "length_bias": "medium", "ordering_bias": "outcome_first", "rationale": "Front-load named production systems and scale markers."},
      {"section_id": "core_competencies", "emphasis": "secondary", "focus_categories": ["architecture", "ai"], "length_bias": "short", "ordering_bias": "tech_first", "rationale": "Competencies are secondary; architecture/AI stacks only."},
      {"section_id": "ai_highlights", "emphasis": "highlight", "focus_categories": ["ai", "architecture"], "length_bias": "medium", "ordering_bias": "outcome_first", "rationale": "ai_intensity=significant supports a dedicated section."},
      {"section_id": "experience", "emphasis": "highlight", "focus_categories": ["architecture", "ai", "metric", "leadership"], "length_bias": "long", "ordering_bias": "outcome_first", "rationale": "Experience carries the architecture-first proof ladder."},
      {"section_id": "projects", "emphasis": "compress", "focus_categories": ["ai", "architecture"], "length_bias": "short", "ordering_bias": "tech_first", "rationale": "Supporting only if experience is sparse."}
    ],
    "ai_section_policy": "required",
    "counts": {
      "key_achievements_min": 3,
      "key_achievements_max": 5,
      "core_competencies_min": 6,
      "core_competencies_max": 10,
      "summary_sentences_min": 2,
      "summary_sentences_max": 4
    },
    "ats_envelope": {
      "pressure": "standard",
      "format_rules": ["single_column", "no_tables_in_experience", "no_graphics", "ascii_safe", "plain_bullets"],
      "keyword_placement_bias": "top_heavy"
    },
    "evidence_density": "high",
    "seniority_signal_strength": "high",
    "compression_rules": ["compress_core_competencies_first", "compress_certifications_second", "compress_projects_third"],
    "omission_rules": ["omit_publications_if_unused_in_role_family", "omit_awards_if_unused_in_role_family"],
    "unresolved_markers": [],
    "rationale": "Concrete shape follows the architecture-first thesis: proof-dense header, key_achievements highlighted, dedicated ai_highlights for ai_intensity=significant, experience carrying the long-form proof ladder.",
    "confidence": {"score": 0.82, "band": "high", "basis": "Matches thesis and intensity matrix; ATS envelope standard for greenhouse."},
    "evidence": [
      {"claim": "Architecture-first thesis requires key_achievements highlighted.", "source_ids": ["document_expectations.primary_document_goal", "document_expectations.density_posture.header_density"]},
      {"claim": "ai_section_policy=required satisfied by intensity=significant.", "source_ids": ["classification.ai_taxonomy.intensity"]}
    ]
  }
}
```

**Abstention shape.** When evidence is too thin to commit to a concrete
shape: emit a role-family default section_order (`header -> summary ->
key_achievements -> core_competencies -> experience -> education`),
`ai_section_policy = embedded_only` (or `discouraged` for intensity=none),
`title_strategy = closest_truthful`, conservative counts, and populate
`unresolved_markers[]`.

**Richness expectations.**

- `section_order[]` covers all sections the shape wants visible and
  references only canonical ids.
- `section_emphasis[]` covers at least `summary`, `key_achievements`,
  `experience`, and either `core_competencies` or `ai_highlights`.
- `ats_envelope.format_rules[]` 3–6 entries.
- `evidence[]` cites 2+ upstream refs for medium+ confidence.

### 8.3 Optional merged prompt `P-document-and-cv-shape@v1`

Same constraints as §8.1 and §8.2 combined. Output top-level keys:
`document_expectations`, `cv_shape_expectations`. Cross-subdocument
consistency (§4.7) becomes a within-prompt invariant that the prompt must
enforce; the deterministic validator still re-enforces it at ingress.

**When to switch.** Only after a 50-job bench shows the merged prompt
matches the split prompt on every cross-subdocument invariant, with equal
or higher reviewer usefulness, and with at least 15% lower cost.

## 9. Debuggability and Observability

### 9.1 What must be inspectable after each run

- both subdocuments with full `debug_context`
- the preflight `role_thesis_priors`, `evaluator_axis_summary`,
  `proof_order_candidates`, and `ats_envelope_profile` snapshots
- the raw LLM output (pre-normalization) for each prompt
- the normalization diff (`normalization_events[]` and
  `rejected_output[]`)
- schema-repair retry events and reasons
- timing and usage per prompt

Storage: collection-backed in the same document as `presentation_contract`,
under `presentation_contract.debug.document_expectations` and
`presentation_contract.debug.cv_shape_expectations`. Snapshot mirrors only
`{status, confidence.band, confidence.score, primary_document_goal,
section_order_length, ai_section_policy}`.

### 9.2 Heartbeat and logging

Follows `AGENTS.md` "Long-Running Debug Sessions" and
`docs/current/operational-development-manual.md`:

- stage heartbeat every N seconds
- inner Codex PID and last output age logged during each prompt call
- explicit env-loaded `.env` (never `source .env`)
- `python -u` for any debug driver
- default to isolated temp cwd for this stage (no repo context needed)

### 9.3 Failure diagnosis playbook (baked into the plan)

When a run produces `status = partial` or `unresolved`:

1. Read `debug_context.normalization_events[]` to see whether the LLM
   output was richer than the schema and got retained or rejected.
2. Read `debug_context.rejected_output[]` to see which fields were
   dropped and why (enum mismatch, candidate leakage, shape drift).
3. Read `debug_context.defaults_applied[]` to see which role-family
   priors the stage fell back to.
4. Read the raw LLM output to judge whether the prompt or the
   normalizer is the source of drift.
5. If a specific richer shape keeps appearing, open a schema-evolution
   issue under §5.5.

### 9.4 What must never leak to logs

- candidate PII (none should appear at this stage)
- raw stakeholder names or profile URLs beyond
  `stakeholder_surface.real_stakeholders[].stakeholder_ref`
- `evidence.excerpt` content beyond 240 chars

### 9.5 Langfuse tracing

Inherits the 4.2 umbrella contract (see
`plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
§8.8). Mongo `debug_context` is the source of truth for raw LLM output and
normalization diffs; Langfuse mirrors shape and boundaries, not payloads.

**Canonical spans for `presentation_contract`.** The `presentation_contract`
stage co-produces four subdocuments (4.2.2, 4.2.4, 4.2.5, 4.2.6). Each
subdocument synthesis pass is a substage span:

- `scout.preenrich.presentation_contract` — stage body span.
- `scout.preenrich.presentation_contract.preflight` — role-thesis /
  evaluator-axis / proof-order / ATS-envelope preflight.
- `scout.preenrich.presentation_contract.document_expectations`
- `scout.preenrich.presentation_contract.cv_shape_expectations`
- `scout.preenrich.presentation_contract.ideal_candidate` (4.2.4)
- `scout.preenrich.presentation_contract.dimension_weights` (4.2.5)
- `scout.preenrich.presentation_contract.emphasis_rules` (4.2.6)
- `scout.preenrich.presentation_contract.normalization` — per-subdocument
  normalization pass when it meaningfully transforms or rejects LLM output.
- `scout.preenrich.presentation_contract.schema_repair` — schema-repair
  retries; outcome metadata includes `repair_reason` and `repair_attempt`.

**Required subdocument-span metadata.**

- `primary_document_goal`, `section_order_length`, `ai_section_policy`,
  `status`, `confidence.band`, `confidence.score`.
- Normalization counts: `normalization_events_count`,
  `rejected_output_count`, `defaults_applied_count`. Full bodies stay in
  Mongo `debug_context`, not in Langfuse.

**Merged vs split prompt mode.** When benchmarking the single-merged prompt
variant (see §8.*), the stage still emits one span per logical subdocument
by splitting the merged response at parse time. Span-name stability across
prompt modes is required so telemetry comparisons are valid.

**What never goes into span payloads.** Raw LLM output, full `ai_section`
candidates, full bullets or tagline text, and the full `debug_context`.
Previews are capped at 160 chars and only emitted through
`_sanitize_langfuse_payload`.

## 10. Test Strategy (aligned with AGENTS.md)

Follows the current local dev cycle:

- use `.venv` and `python -u`
- load `.env` from Python with an explicit path (no `source .env`)
- isolate tests (`tests/unit/preenrich/...`); mock LLM transport; do
  not hit MongoDB; do not run integration/bulk tests
- run with `pytest tests/unit/preenrich -n auto` for speed; targeted
  tests during iteration (e.g. `pytest
  tests/unit/preenrich/test_document_expectations.py -x`)
- keep individual test commands under the **7-minute ceiling** called out
  for heavy test commands; split if a slice exceeds budget

### 10.1 Unit tests (schema and validators)

`tests/unit/preenrich/test_document_expectations_schema.py`:

- `DocumentExpectationsDoc` accepts canonical output from §8.1
- `extra="forbid"` rejects unknown top-level keys
- section-id-in-wrong-field rejection (e.g. `tilt` containing `summary`)
- enum rejection for all enums (goal, proof category, anti-pattern, tone,
  density, keyword balance)
- `audience_variants` keys must appear in
  `evaluator_coverage_target` (validator fed a mock coverage target)
- confidence band clamp when upstream status is `inferred_only`

`tests/unit/preenrich/test_cv_shape_expectations_schema.py`:

- `CvShapeExpectationsDoc` accepts canonical output from §8.2
- section-id enum enforcement for `section_order[]` and
  `section_emphasis[]`
- `section_emphasis[].section_id` subset of `section_order[]`
- `ai_section_policy` × `ai_taxonomy.intensity` matrix (§7.4) rejection
- counts min/max invariants
- cross-subdoc `header_shape.density` ==
  `document_expectations.density_posture.header_density`

### 10.2 Normalizer tests

`tests/unit/preenrich/test_presentation_contract_ingress.py`:

- aliases (`goal` → `primary_document_goal`, `order` →
  `section_order`) are mapped
- scalar/list/dict drift coerced
- unknown-but-grounded wrappers retained in
  `debug_context.richer_output_retained[]`
- candidate-leakage detector catches first-person strings
- section-id and proof-category outside enum rejected at ingress
- richer output (extra per-evaluator narrative) retained, not discarded

### 10.3 Stage-level tests

`tests/unit/preenrich/test_presentation_contract_stage.py`:

- happy path: real stakeholders + rich research → `status = completed`,
  both subdocuments populated, all cross-invariants pass
- fail-open A: `stakeholder_surface.status = inferred_only` →
  `status = partial`, audience_variants restricted to inferred roles,
  `confidence.band <= medium`
- fail-open B: `pain_point_intelligence.proof_map` empty →
  `proof_order[]` defaults from role-family priors,
  `defaults_applied[]` populated
- fail-open C: `research_enrichment.role_profile.status = partial` →
  `primary_document_goal` derived from `classification` priors
- fail-closed A: LLM returns `ai_section_policy = required` with
  `ai_intensity = none` → rejected, one repair retry, then role-family
  default
- fail-closed B: LLM returns a section id outside enum → rejected with
  debug entry, repair retry, falls back to role-family shape if retry
  also fails
- fail-closed C: LLM emits candidate-specific assertion → offending
  field omitted; `status = partial`

### 10.4 Bench harness (local)

`scripts/benchmark_presentation_contract_4_2_2.py` (future implementation
task). Runs the two prompts across a curated 20-job set, writes the
subdocuments, and asserts:

- per-job cross-invariants pass
- reviewer-usefulness score (manual review sheet per job) for thesis
  goal clarity, audience variant actionability, section-order match,
  ai policy correctness
- normalization retention rate (expect >= 30% of runs to retain at least
  one richer field in `richer_output_retained[]`)
- cost per run per model
- regressions vs `gpt-5.4-mini` baseline

## 11. Eval Requirements

Eval cases live under `evals/presentation_contract_4_2_2/`. Structure
mirrors existing eval directories.

### 11.1 Eval cases (minimum 20 jobs across role families)

- architecture-first AI role with resolved stakeholders
- delivery-first engineering role with inferred-only stakeholders
- leadership-first role (head / director) with strategic research
- AI-first applied-ML role with intensity=core
- platform-first infra role with intensity=adjacent
- transformation-first greenfield role
- ambiguous role where goal should come out as `balanced`
- no-research job (`research_enrichment.status = no_research`)
- thin pain_map job (default to role-family priors)
- conflicting stakeholder preferences (recruiter hype vs hiring-manager
  rigor) — thesis should resolve per priority rules in §5.4 / §8.1
- low ai_intensity with JD keyword spam — thesis must not emit
  ai_first goal
- strict ATS vendor (e.g. Workday) with `pressure=high`

### 11.2 What to measure

- cross-invariant pass rate (must be 100%; any failure is a blocker)
- reviewer usefulness score for each subdocument (target >= 0.80)
- candidate-leakage rate (target = 0)
- `primary_document_goal` accuracy vs reviewer label (target >= 0.85)
- `section_order[]` accuracy vs reviewer label for top 3 slots
  (target >= 0.90)
- `ai_section_policy` intensity-matrix compliance (target = 1.00)
- richer-output retention rate (report; no hard threshold; used to
  gate schema evolution per §5.5)
- abstention appropriateness (target >= 0.90 — abstain only when
  evidence is legitimately thin)

### 11.3 Regression eval

Re-run the frozen eval set after:

- every prompt version bump
- every schema change
- every routing/model change
- every normalizer change

A regression is any drop >5 points on reviewer usefulness, any new
cross-invariant failure, or any increase in candidate-leakage rate.

## 12. Test / Live Production Rollout

### 12.1 Flagging and gating

- Capability flag: `preenrich.presentation_contract.enabled`
  (default off).
- Sub-flags:
  - `preenrich.presentation_contract.document_expectations.enabled`
  - `preenrich.presentation_contract.cv_shape_expectations.enabled`
  - `preenrich.presentation_contract.merged_prompt.enabled`
    (default off; enabled only after §8.3 bench gate passes)
- Registration: once the stage is registered in
  `src/preenrich/stage_registry.py`, downstream consumers (`cv_guidelines`,
  `blueprint_assembly`) must treat it as opportunistic until the flag is
  default-on.

### 12.2 Rollout order

1. Ship schemas, normalizer, and prompt builders behind the stage flag.
2. Unit and stage tests green.
3. Shadow-run `P-document-expectations@v1` on the curated 20-job eval
   set; review usefulness scores.
4. Shadow-run `P-cv-shape-expectations@v1` next; review cross-invariants.
5. Ship to 50-job canary with flag on for those jobs only; manual review
   every 10th run.
6. Default-on after:
   - cross-invariant pass rate = 100%
   - reviewer usefulness >= 0.80 on both subdocuments
   - candidate-leakage rate = 0
   - cost per job within agreed budget
7. Begin downstream consumer migration (`cv_guidelines` reads
   `presentation_contract` instead of re-deriving).

### 12.3 Rollback

Flag off instantly disables the stage; downstream consumers revert to
current `cv_guidelines`. No data migration needed because
`presentation_contract` is an additive artifact.

### 12.4 Production readiness checklist

- [ ] schemas and validators in `blueprint_models.py`, with unit tests
- [ ] ingress normalizer with tests
- [ ] two prompt builders in `blueprint_prompts.py`, with versions in
      `PROMPT_VERSIONS`
- [ ] stage implementation in
      `src/preenrich/stages/presentation_contract.py`
- [ ] registration in `stage_registry.py` and DAG wiring in `dag.py`
- [ ] compact snapshot projection in
      `src/preenrich/stages/blueprint_assembly.py`
- [ ] debug_context persisted, snapshot-excluded, size-capped
- [ ] eval directory scaffolded under
      `evals/presentation_contract_4_2_2/`
- [ ] bench script `scripts/benchmark_presentation_contract_4_2_2.py`
- [ ] docs updated: `missing.md`, `architecture.md`, decision doc under
      `docs/current/decisions/` for model routing choice

## 13. Primary Source Surfaces

- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `plans/research-enrichment-4.1.3.1-live-codex-hard-cutover-and-schema-alignment.md`
- `plans/brainstorming-new-cv-v2.md`
- `src/preenrich/blueprint_models.py`
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/stage_registry.py`
- `src/preenrich/stages/blueprint_assembly.py`
- `src/layer6_v2/prompts/grading_rubric.py`
- `docs/current/cv-generation-guide.md`
- `docs/current/operational-development-manual.md`
- `AGENTS.md`

Implementation surfaces (to be created/extended during follow-up
implementation plan, not in this plan):

- `src/preenrich/stages/presentation_contract.py` (new)
- `DocumentExpectationsDoc`, `CvShapeExpectationsDoc`, supporting sub-
  models, enums, and validators in `src/preenrich/blueprint_models.py`
- `build_p_document_expectations`, `build_p_cv_shape_expectations`, and
  optional `build_p_document_and_cv_shape` in
  `src/preenrich/blueprint_prompts.py`
- prompt versions registered under `PROMPT_VERSIONS`:
  `document_expectations: "P-document-expectations@v1"`,
  `cv_shape_expectations: "P-cv-shape-expectations@v1"`,
  `document_and_cv_shape: "P-document-and-cv-shape@v1"`
- compact snapshot projection in
  `src/preenrich/stages/blueprint_assembly.py`

## 14. Resolved Decisions and Open Questions

### 14.1 Resolved in this revision

- `document_expectations` and `cv_shape_expectations` are two peer
  subdocuments, not one nested object. Both co-produced in
  `presentation_contract`. (§1, §4)
- `title_strategy` belongs to `cv_shape_expectations` as policy enum;
  the list of acceptable titles belongs to 4.2.4. Cross-invariant keeps
  them consistent. (§2, §4.7)
- Anti-pattern ids in 4.2.2 are document-shape-level; claim-level
  forbidden patterns remain in 4.2.6. (§4.5)
- Debug block is mandatory per subdocument and snapshot-excluded. (§4.6,
  §9)
- Richer-output retention is the default, following 4.1.3.1. (§5)
- Primary model: `gpt-5.4`; baseline: `gpt-5.4-mini`; no web search; one
  schema-repair retry. (§7)
- Two-prompt split by default; merged prompt is a bench-gated option.
  (§7.1, §8.3)
- Minimum viable artifact rules under fail-open. (§6.1)
- Candidate-leakage detector is deterministic and runs post-LLM. (§5.4)

### 14.2 Open questions (carry to follow-up plans, not implemented here)

- When should `cv_guidelines` formally migrate to read
  `presentation_contract` instead of re-deriving? (Needs its own plan.)
- When should richer-output fields promote into canonical schema per
  §5.5? (Governed by a schema-evolution follow-up after 100-job bench.)
- Should `section_order[]` encode section groups (`[header] [summary]
  [proof_block] [experience] [education]`) instead of flat ids? Defer
  until a concrete consumer needs grouping.
- Should the optional merged prompt §8.3 become the default? Defer to
  bench outcome.
- Should `keyword_balance.ats_mirroring_bias` integrate with a
  dedicated ATS keyword-lookup layer? Out of scope for 4.2.2;
  revisit during final CV generation planning.
