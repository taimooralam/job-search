# Iteration 4.2.5 Plan: Experience Dimension Weights and Salience

## 1. Executive Summary

`experience_dimension_weights` is **one subdocument co-produced inside the
`presentation_contract` stage** (alongside 4.2.2 `document_expectations` and
`cv_shape_expectations`, 4.2.4 `ideal_candidate_presentation_model`, and 4.2.6
`truth_constrained_emphasis_rules`). It is not a standalone preenrich stage,
does not register a `StageDefinition`, does not own a DAG node, does not claim
a work-item lease, and does not own an independent cache key.

Its job: produce a typed, enum-bounded, sum-to-100 weighting of which
**experience dimensions** this role and evaluator surface want a CV to
front-load, hold level, or keep secondary — plus per-evaluator variants, a
minimum-visible-dimensions floor, and overuse-risk flags. The artifact is
strictly **candidate-agnostic**: it describes preferred document visibility
derived from role truth and evaluator surface, never candidate truth.

Operational discipline is inherited from the rest of 4.2:

- **Mongo is the control plane.** `work_items`,
  `preenrich_stage_runs`, `preenrich_job_runs`, and
  `pre_enrichment.stage_states.presentation_contract` drive execution. 4.2.5
  adds no new control surface.
- **Langfuse is the observability sink.** The subdocument emits under the
  `scout.preenrich.presentation_contract.dimension_weights` substage span
  with metadata-first payloads; full weight maps and rationale live in
  Mongo `debug_context` and the persisted artifact, not in span bodies.
- **VPS validation** runs the `presentation_contract` stage end-to-end on a
  real level-2 job and inspects the 4.2.5 subdocument. There is no fake
  standalone `preenrich.experience_dimension_weights` stage to validate.

This subdocument closes a real gap: today, dimension salience is implicit in
`classification.primary_role_category`, `jd_facts.weighting_profiles`, the
grading rubric, and free-text `cv_guidelines`. That implicit-ness is the
source of the "generically good" CV problem. 4.2.5 makes experience shape
explicit, auditable, and stakeholder-variable so every downstream emphasis
decision can justify itself against a weighted contract.

## 2. Mission

Turn the question "which experience dimensions should this CV put forward,
hold level, and keep secondary for this role and these evaluators?" into a
structured, enum-bounded, sum-to-100 contract with stakeholder variants, a
visibility floor, and overuse risks — candidate-agnostic, evidence-grounded,
and consistent with its three peer subdocuments.

## 3. Objectives

- **O1.** Produce a typed, enum-constrained `experience_dimension_weights`
  subdocument inside every successful `presentation_contract` run.
- **O2.** Keep every weight grounded in `jd_facts`, `classification`,
  `research_enrichment`, `stakeholder_surface`, and `pain_point_intelligence`
  evidence; fall back to role-family priors only via an explicit
  `defaults_applied[]` record.
- **O3.** Enforce the deterministic invariants that make the artifact safe to
  consume downstream: sum-to-100, canonical-enum only, non-negative integers,
  stakeholder-variant gating by evaluator coverage target, and AI /
  architecture / leadership caps tied to upstream evidence.
- **O4.** Keep the artifact internally coherent with its peer subdocuments
  (4.2.2 section emphasis, 4.2.4 must/should/de-emphasize signals and proof
  ladder, 4.2.6 truth-constrained rules) at a single deterministic
  validator gate inside `presentation_contract`.
- **O5.** Fail open to role-family + taxonomy priors with capped confidence
  and explicit `unresolved_markers[]` when upstream is thin; never fail the
  parent `presentation_contract` run solely because 4.2.5 had to default.
- **O6.** Emit a Langfuse substage (`scout.preenrich.presentation_contract.
  dimension_weights`) that lets an operator diagnose weight-map drift,
  invariant violations, AI-cap suppression, stakeholder-variant suppression,
  and schema-repair retries in under two minutes from Mongo → trace.
- **O7.** Be validated on the VPS through the `presentation_contract` stage
  on a real `level-2` job with full upstream prerequisites before default-on
  rollout.

## 4. Goals

- **G1.** Single subdocument, single schema, single deterministic validator.
  No new collection, no new DAG node, no new work-item lifecycle, no new
  cache key beyond the parent `presentation_contract` stage.
- **G2.** Canonical `ExperienceDimension` enum owned by 4.2.5 and imported by
  4.2.2, 4.2.4, and 4.2.6 without redefinition. `dimension_enum_version`
  field on every emitted artifact for forward-compatibility.
- **G3.** A compact snapshot projection inside
  `job_blueprint_snapshot.presentation_contract_compact.dimension_weights`:
  top weights, counts, `status`, `confidence.band`, `trace_ref`. Never full
  weight maps or rationale bodies.
- **G4.** Zero fabricated dimension labels, zero variants emitted for
  evaluator personas not in `stakeholder_surface.evaluator_coverage_target`,
  zero AI/architecture/leadership caps breached.
- **G5.** Feature-flag gating via the parent stage flag
  (`presentation_contract_enabled()`) plus an optional sub-flag
  (`presentation_contract_dimension_weights_enabled()`) that controls the
  LLM synthesis path; the deterministic role-family-default fallback is
  always available.
- **G6.** Safe cohabitation with 4.2.2's merged prompt mode
  (`P-document-and-cv-shape@v1`): when the merged prompt runs, 4.2.5 still
  emits a distinct parse-time subdocument with its own span and validator.

## 5. Success Criteria

The subdocument is successful when, for a representative 30-job corpus
(mixed IC / EM / Director / Head, mixed research quality, mixed
ai_intensity, mixed ATS):

- **SC1.** 100% of `presentation_contract` runs produce a validated
  `experience_dimension_weights` with
  `status ∈ {completed, partial, inferred_only, unresolved}`. None terminal
  because of 4.2.5 schema issues alone.
- **SC2.** Reviewer-rated emphasis-coherence ≥ 4.0 / 5 median (rubric §18.9)
  measured against the role mandate and stakeholder surface.
- **SC3.** 100% of emitted weight maps satisfy sum-to-100, canonical-enum-
  only, and non-negative-integer invariants post-validator.
- **SC4.** `stakeholder_variant_weights` keys are always a subset of
  `stakeholder_surface.evaluator_coverage_target`; gating violations are 0.
- **SC5.** AI cap holds 100%: `overall_weights.ai_ml_depth` is bounded by
  the ai-intensity cap table (§12.4); spot-check corpus has 0 violations.
- **SC6.** Architecture / leadership caps hold: `architecture_system_design`
  and `leadership_enablement` top the distribution only when corresponding
  JD / role / evaluator evidence exists (§12.5); spot-check has 0
  violations.
- **SC7.** Cross-subdocument consistency 100%: weights do not contradict
  `document_expectations.section_emphasis`, `ideal_candidate_presentation_model.
  must_signal[]` / `should_signal[]`, or `truth_constrained_emphasis_rules.
  cap_dimension_weight` rules.
- **SC8.** For `stakeholder_surface.status ∈ {inferred_only, no_research,
  unresolved}` or `research_enrichment.status ∈ {partial, unresolved}`,
  `confidence.band ≤ medium` and at least one `unresolved_marker` is set.
- **SC9.** Langfuse substage `scout.preenrich.presentation_contract.
  dimension_weights` is emitted on every run with full §17.4 metadata, one
  click from the level-2 UI.
- **SC10.** VPS smoke (§19) completes on a real job with artifacts captured
  under `reports/presentation-contract/<job_id>/dimension_weights/`.

## 6. Non-Goals

- Final CV prose, section copy, header lines, summaries, bullets, ordering
  commitments. 4.2.5 describes weight, not layout.
- Candidate evidence retrieval, master-CV matching, STAR selection,
  achievement ranking. Those belong to 4.3.x.
- Claims about the *candidate's* strengths; 4.2.5 is purely about document
  preference, not candidate truth.
- Ownership of `DocumentSectionIdEnum` (4.2.2), `ProofTypeEnum` (4.2.3),
  `StakeholderTypeEnum` (4.2.1), the `Rule` schema (4.2.6), or the
  `acceptable_titles[]` / `proof_ladder[]` content (4.2.4). 4.2.5 imports
  and cross-validates; it does not redefine.
- A standalone preenrich stage, a distinct DAG node, an independent work
  item, an independent lease, or an independent cache key.
- A new preenrich trace or top-level span. 4.2.5 lives under
  `scout.preenrich.presentation_contract` as a substage.
- Private stakeholder motives, clinical / psychological profiling,
  protected-trait inference.

## 7. Why This Artifact Exists

The system already infers dimension salience implicitly through:

- `classification.primary_role_category` (role family → priors).
- `jd_facts.extraction.competency_weights` and
  `jd_facts.weighting_profiles.expectation_weights` (delivery /
  communication / leadership / collaboration / strategic_scope).
- CV grading rubric in `src/layer6_v2/prompts/grading_rubric.py`.
- Free-text hiring-manager guidance in
  `docs/current/cv-generation-guide.md` §6.
- `docs/current/achievement-review-tracker.yaml` review-tracker axes.

None of those emit a typed per-dimension weighting contract with
stakeholder variants, overuse risks, a minimum-visible floor, and
deterministic cross-checks. The missing contract is the root cause of two
recurring failure modes in generated CVs:

- "**Generically good**": every axis looks reasonable, nothing leads — so
  nothing proves role fit.
- "**Fashionable overshoot**": AI or leadership dimensions inflate because
  the JD uses the keyword, even when the role is adjacent or the
  stakeholder surface rejects it.

4.2.5 makes shape explicit, auditable, and stakeholder-variable so
downstream emphasis decisions can cite it and downstream guardrails (4.2.6,
later 4.3.x) can constrain against it.

It must live inside `presentation_contract` rather than as a standalone
stage because:

- it shares the same five upstream inputs as 4.2.2 / 4.2.4 / 4.2.6;
- it shares one evidence frame and one cache key with those peers;
- it needs single-gate cross-validation against 4.2.2 section emphasis,
  4.2.4 must/should signals, and 4.2.6 `cap_dimension_weight` rules;
- splitting it would invite prompt drift, contradictory defaults, and
  extra cost for zero observational gain, since it performs no fetches
  and owns no identity-safety surface.

## 8. Subdocument Boundary

### 8.1 Placement

Co-produced inside the `presentation_contract` stage. The parent stage is
placed in the DAG as:

```
jd_facts -> classification -> application_surface -> research_enrichment
   -> stakeholder_surface -> pain_point_intelligence -> presentation_contract
```

4.2.5 does not register a `StageDefinition`. It does not appear in
`_blueprint_registry()`. It does not enqueue a work item. It does not hold
a lease. The parent `presentation_contract` stage owns all of those. The
only artifact 4.2.5 owns is its own subdocument inside the parent
`PresentationContractDoc`, plus the canonical `ExperienceDimension` enum.

### 8.2 Relationship to peer subdocuments

- **`document_expectations` (4.2.2).** 4.2.5 reads
  `primary_document_goal`, `proof_order[]`, `density_posture`, and
  `tone_posture` when same-run. Weights must not contradict
  `document_expectations.section_emphasis` (architecture-first goal should
  not produce `architecture_system_design ≤ 10`). The cross-validator
  asserts consistency between `section_emphasis[].focus_categories` and
  the high-weighted dimensions.
- **`cv_shape_expectations` (4.2.2).** 4.2.5 never owns section counts or
  section order. It may indirectly shape them through weights, but does not
  emit section-shape fields. `ai_section_policy` in 4.2.2 constrains 4.2.5
  indirectly via the AI cap table (§12.4).
- **`ideal_candidate_presentation_model` (4.2.4).** 4.2.4 owns
  `must_signal[]`, `should_signal[]`, `de_emphasize[]`, and the
  `proof_ladder[]`. When those signals name a dimension-scoped concept,
  the dimension reference *must* match a value in 4.2.5's
  `ExperienceDimension` enum. Weights must be consistent with:
  - `must_signal[]` dimensions → non-zero weight, typically ≥ 10.
  - `de_emphasize[]` dimensions → weight ≤ 5 unless role evidence
    forces it higher (then flagged as `overuse_risk`).
  - `proof_ladder[]` top rungs → corresponding dimensions non-trivial
    in `overall_weights`.
  The cross-validator enforces coherence; contradictions fail the parent
  run and fall back to role-family defaults.
- **`truth_constrained_emphasis_rules` (4.2.6).** 4.2.6 may emit
  `cap_dimension_weight` rules. 4.2.5 must honor those caps; if a LLM-
  emitted weight exceeds a cap, the deterministic post-pass clamps it and
  records a `normalization_events[]` entry. 4.2.5 never authors `Rule[]`
  records in 4.2.6's schema.
- **Final `presentation_contract`.** All four subdocuments co-persist in
  one `PresentationContractDoc`. 4.2.5 is one of those four. Cross-
  subdocument invariants (§13.2) are validated in a single deterministic
  gate before persistence.

### 8.3 Relationship to `jd_facts.weighting_profiles`

`jd_facts.extraction.weighting_profiles.expectation_weights` already
sums to 100 over a *different* axis (delivery / communication /
leadership / collaboration / strategic_scope). That axis is about
behavioral expectations, not document emphasis. 4.2.5's
`ExperienceDimension` enum is richer (12 dimensions) and about
document visibility. The two axes are related but not identical.
4.2.5 reads `expectation_weights` as a prior and may map it into
deterministic preflight biases (§9.3); it never overwrites it and
never claims to be the same artifact.

## 9. Inputs

### 9.1 Required (from `pre_enrichment.outputs`)

- `jd_facts.merged_view` — especially
  `extraction.competency_weights`, `weighting_profiles`,
  `skill_dimension_profile`, `team_context`, `top_keywords`,
  `qualifications`, `responsibilities`, `identity_signals`.
- `classification` — `primary_role_category`, `seniority`,
  `tone_family`, `ai_taxonomy.intensity`, `ai_taxonomy.modalities`.
- `research_enrichment.role_profile` — `mandate`, `business_impact`,
  `success_metrics[]`, `evaluation_signals[]`, `risk_landscape[]`.
- `research_enrichment.company_profile` — `scale_signals[]`,
  `ai_data_platform_maturity`, `identity_confidence.band`.
- `stakeholder_surface` — `evaluator_coverage_target[]`, per-role
  `cv_preference_surface`, `preferred_signal_order[]`,
  `preferred_evidence_types[]`, `likely_reject_signals[]`, `status`.
- `pain_point_intelligence` — `proof_map[].preferred_proof_type`,
  `pain_points[].likely_proof_targets[]`, `bad_proof_patterns[]`,
  `status`.

### 9.2 Opportunistic (same-run peers; never hard prerequisites)

- `document_expectations` / `cv_shape_expectations` (4.2.2) when
  synthesized earlier in the same `presentation_contract` run — used for
  cross-consistency and section-emphasis alignment.
- `ideal_candidate_presentation_model` (4.2.4) — used for
  `must_signal[]` / `should_signal[]` dimension coherence.
- `job_inference.semantic_role_model` when present — used as a weak
  secondary prior only.
- rubric priors from `src/layer6_v2/prompts/grading_rubric.py` and
  `docs/current/cv-generation-guide.md`.

### 9.3 Deterministic preflight helpers (built before the LLM call)

Constructed by the parent `presentation_contract` preflight pass and
projected into 4.2.5's prompt payload:

- `role_family_weight_priors` — `{dimension: int}` default map indexed
  by `classification.primary_role_category` and `seniority`. Seeds
  from the role guidance in `docs/current/cv-generation-guide.md` §6,
  the grading rubric axes, and the achievement-review tracker. This
  map is the deterministic fail-open target.
- `evaluator_dimension_pressure` — compressed per-role projection of
  `stakeholder_surface.preferred_signal_order[]` and
  `preferred_evidence_types[]` onto the `ExperienceDimension` enum.
  Used as a strong prior for `stakeholder_variant_weights`.
- `ai_intensity_cap` — the cap on `ai_ml_depth` derived from
  `classification.ai_taxonomy.intensity` per §12.4.
- `architecture_evidence_band` — enum `{none, partial, strong}` derived
  from JD scope, `research_enrichment.role_profile.mandate`, and
  `scale_signals[]`. Gates whether `architecture_system_design` may
  dominate.
- `leadership_evidence_band` — enum `{none, partial, strong}` derived
  from `classification.seniority`, `jd_facts.team_context`, and
  `stakeholder_surface` evaluator composition. Gates whether
  `leadership_enablement` may dominate.
- `proof_category_dimension_map` — mapping of
  `pain_point_intelligence.proof_map[].preferred_proof_type` onto
  dimensions (e.g. `metric → business_impact`, `architecture →
  architecture_system_design`, `reliability → quality_risk_reliability`,
  `ai → ai_ml_depth`, `leadership → leadership_enablement`,
  `stakeholder → stakeholder_communication`).

The preflight pass never fails the stage. When an input is missing it
degrades to role-family priors and records that in
`defaults_applied[]`.

### 9.4 Input hashing (parent cache key)

4.2.5 has **no independent cache key**. Cache invalidation is the parent
stage's `presentation_contract_input_hash`, which already incorporates:

- `jd_facts.merged_view`
- `classification` (including `ai_taxonomy`)
- `research_enrichment.research_input_hash`, `status`
- `stakeholder_surface.coverage_digest`
- `pain_point_intelligence.pain_input_hash`
- `PROMPT_VERSION` for 4.2.5's prompt
- `DIMENSION_ENUM_VERSION`

Drift in any of those busts the parent cache and re-synthesizes all four
subdocuments together. This is intentional: the four are co-validated
and must stay in lock-step.

## 10. Canonical Dimensions

### 10.1 Enum and ownership

`ExperienceDimension` is owned by 4.2.5 and consumed by 4.2.2 (as
`focus_category` where dimension-scoped), 4.2.4 (as the dimension
reference in `must_signal[]` / `should_signal[]`), and 4.2.6 (as
`applies_to` for `cap_dimension_weight` rules). No other plan may
redefine this enum.

```
ExperienceDimension:
  hands_on_implementation
  architecture_system_design
  leadership_enablement
  tools_technology_stack
  methodology_operating_model
  business_impact
  stakeholder_communication
  ai_ml_depth
  domain_context
  quality_risk_reliability
  delivery_execution_pace
  platform_scaling_change
```

### 10.2 Dimension semantics

Short definitions (kept here so the prompt and tests share one source of
truth):

- `hands_on_implementation` — day-in-day-out production-grade build,
  debug, ship depth.
- `architecture_system_design` — whole-system responsibility, tradeoff
  judgment, design authority.
- `leadership_enablement` — direct and indirect people leverage: hiring,
  coaching, setting direction, raising bar.
- `tools_technology_stack` — specific technology fluency, modern stack
  currency, tool ecosystem depth.
- `methodology_operating_model` — delivery model, team operating system,
  engineering practice discipline.
- `business_impact` — outcomes in business units, revenue, retention,
  cost, margin.
- `stakeholder_communication` — cross-functional clarity, executive
  partnership, narrative craft.
- `ai_ml_depth` — AI / ML system design, model ops, evaluation, training
  / RAG / inference platform depth.
- `domain_context` — vertical fluency (fintech, health, platform, etc.).
- `quality_risk_reliability` — quality bar, reliability, security,
  compliance, incident response.
- `delivery_execution_pace` — shipped volume and cadence; throughput.
- `platform_scaling_change` — platform leverage, scaling from N to 10N,
  org-wide change leverage.

### 10.3 Enum versioning / promotion policy

- `dimension_enum_version` is persisted on every emitted artifact and on
  the Langfuse substage span metadata.
- New dimensions must be added via a versioned bump in
  `src/preenrich/blueprint_models.py`, a prompt version bump, and a
  migration note. Prompt freedom to invent new dimensions is explicitly
  forbidden and caught by the deterministic post-pass.
- Removals are not supported on a live enum. Deprecated dimensions must
  be mapped to a successor via a one-release compat window.

## 11. Output Shape

### 11.1 Top-level Pydantic model

```
ExperienceDimensionWeightsDoc {
  status,                       # "completed" | "partial" | "inferred_only" | "unresolved"
  source_scope,                 # "jd_only" | "jd_plus_research" | "jd_plus_research_plus_stakeholder"
  dimension_enum_version,       # "v1"
  prompt_version,               # e.g. "P-experience-dimension-weights@v1"
  prompt_metadata: PromptMetadata,
  overall_weights,              # dict[ExperienceDimension, int]; sums to 100
  stakeholder_variant_weights,  # dict[StakeholderType, dict | None]; each non-null sums to 100
  minimum_visible_dimensions,   # list[ExperienceDimension]; subset of enum
  overuse_risks,                # list[OveruseRisk]; see 11.4
  rationale,                    # 1-3 short paragraphs
  unresolved_markers,           # list[str]
  defaults_applied,             # list[str]  (role-family prior ids)
  normalization_events,         # list[NormalizationEvent]  (see 11.5)
  confidence: ConfidenceDoc,
  evidence,                     # list[EvidenceEntry]
  notes,                        # list[str]  (short implementation-visible notes)
  debug_context: ExperienceDimensionWeightsDebug
}
```

The parent `PresentationContractDoc` persists this subdocument at
`presentation_contract.experience_dimension_weights`.

### 11.2 Weight map shape and rules

`overall_weights` and each non-null entry in `stakeholder_variant_weights`
are maps `ExperienceDimension → int`. Rules enforced by the
deterministic post-pass:

- every key is a canonical `ExperienceDimension` value;
- every value is a non-negative integer;
- map sums to exactly 100 (no silent rescale; fails gate if off);
- zeros are allowed and must still be present when the dimension is
  referenced by `minimum_visible_dimensions[]` or `overuse_risks[]`;
- float values, negative values, and non-canonical keys are rejected
  at ingress (schema-repair retry eligible).

### 11.3 Variant map shape and gating

`stakeholder_variant_weights` is always a full dict with the four
canonical keys so consumers can count coverage deterministically:

```
stakeholder_variant_weights:
  recruiter         : dict | null
  hiring_manager    : dict | null
  executive_sponsor : dict | null
  peer_reviewer     : dict | null
```

Gating rules:

- a variant is emitted (non-null) only if its persona type appears in
  `stakeholder_surface.evaluator_coverage_target[]`;
- a variant emitted for a persona not in the coverage target is rejected
  at ingress and the offender is nulled with a `normalization_events[]`
  entry;
- each non-null variant must sum to 100 independently;
- divergence from `overall_weights` is allowed only with explicit
  stakeholder evidence (`evaluator_dimension_pressure` preflight or
  `stakeholder_surface.preferred_signal_order[]`); unjustified divergence
  is flagged by the validator and softened back toward
  `overall_weights`.

### 11.4 Minimum-visible and overuse-risks rules

```
minimum_visible_dimensions: list[ExperienceDimension]
```

- subset of the canonical enum;
- dimensions listed must be present in `overall_weights` (possibly with
  weight 0 — the consumer is obliged to surface them somewhere in the
  document even if not top-weighted);
- cap at 5 entries.

```
overuse_risks: list[OveruseRisk]
OveruseRisk {
  dimension,                 # ExperienceDimension
  reason,                    # enum: weak_evidence | stakeholder_reject |
                             #       role_adjacent | seniority_mismatch |
                             #       keyword_inflation | saturation
  threshold,                 # int weight above which the risk fires
  mitigation                 # short string: softened_form | omit | proof_first
}
```

- dimension must be canonical;
- 4.2.5 flags; 4.2.6 formalizes enforceable `Rule[]` records; the
  cross-validator refuses contradictions.

### 11.5 `debug_context` block

```
ExperienceDimensionWeightsDebug {
  input_summary {
    role_family,
    seniority,
    ai_intensity,
    evaluator_roles_in_scope[],
    proof_category_frequencies: dict[ProofType, int],
    top_keywords_top10[],
    research_status,
    stakeholder_surface_status,
    pain_point_intelligence_status
  },
  role_family_weight_priors,         # full prior map
  evaluator_dimension_pressure,      # full per-role map
  ai_intensity_cap,
  architecture_evidence_band,
  leadership_evidence_band,
  defaults_applied[],
  normalization_events[]             # NormalizationEvent { kind, from, to, reason }
  richer_output_retained[],
  rejected_output[],
  retry_events[]
}
```

Debug is collection-backed only, never in the compact snapshot. Size
capped at 16KB per subdocument. No candidate PII, no full `sources[]`
body, no full LLM prompt text.

## 12. Synthesis Strategy

### 12.1 Split vs merged prompt modes

Default is split: a dedicated prompt
`P-experience-dimension-weights@v1` (`build_p_experience_dimension_weights`)
runs after 4.2.2 and 4.2.4 inside the same `presentation_contract` call,
because the prompt benefits from same-run `document_expectations`,
`cv_shape_expectations`, and `ideal_candidate_presentation_model` as
peer inputs.

Merged mode: when 4.2.2's benchmark gate passes and
`P-document-and-cv-shape@v1` becomes default, 4.2.5 still emits a
distinct parse-time subdocument and a distinct Langfuse substage.
Parsing extracts `experience_dimension_weights` from the merged
response and runs the 4.2.5 validator independently; span-name
stability is a requirement so telemetry comparisons work across modes.

### 12.2 Model routing, fallbacks, repair retry

- Primary: `gpt-5.4` via default provider.
- Baseline / fallback: `gpt-5.4-mini` (shadow and fallback).
- Transport: `_call_llm_with_fallback` in the parent stage.
- `max_web_queries = 0` always: 4.2.5 never fetches the web.
- Exactly one schema-repair retry allowed, only for recoverable
  defects (see §13). The retry prompt passes the validator diff and
  the original output, not the full payload.

### 12.3 Role-family default table (fail-open)

When `status` drops to `inferred_only`, 4.2.5 emits role-family priors
from a fixed table. Seed (to be refined during bench):

| primary_role_category | top-3 dimensions (weights) | notes |
| --- | --- | --- |
| `applied_ai_engineering` | ai_ml_depth:22, hands_on_implementation:20, architecture_system_design:15 | caps enforced |
| `ai_platform_engineering` | platform_scaling_change:20, ai_ml_depth:18, architecture_system_design:18 | |
| `ml_research` | ai_ml_depth:30, domain_context:15, quality_risk_reliability:10 | AI cap exempt iff `ai_intensity=core` |
| `staff_software_engineering` | architecture_system_design:22, hands_on_implementation:18, quality_risk_reliability:12 | |
| `engineering_management` | leadership_enablement:22, delivery_execution_pace:15, business_impact:15 | requires leadership_evidence_band ≥ partial |
| `director_plus` | leadership_enablement:22, business_impact:18, stakeholder_communication:15 | requires leadership_evidence_band = strong |
| `data_engineering` | platform_scaling_change:18, hands_on_implementation:18, quality_risk_reliability:15 | |
| `infra_platform` | platform_scaling_change:20, quality_risk_reliability:18, architecture_system_design:18 | |
| `security_engineering` | quality_risk_reliability:25, architecture_system_design:15, hands_on_implementation:15 | |
| fallback (`balanced`) | hands_on_implementation:18, architecture_system_design:15, business_impact:15 | |

Tail distribution rounds up to 100 per a deterministic fill rule that
prefers `tools_technology_stack`, `methodology_operating_model`,
`domain_context`.

### 12.4 AI-intensity × `ai_ml_depth` cap table

| ai_taxonomy.intensity | overall_weights.ai_ml_depth max |
| --- | --- |
| `core` | 40 |
| `significant` | 28 |
| `adjacent` | 15 |
| `none` | 5 |
| `unknown` | 10 |

Violations are clamped by the post-pass; a `normalization_events[]`
entry `{ kind: "ai_cap", from: <n>, to: <cap>, reason: "ai_intensity_<x>" }`
is recorded. `confidence.band` is lowered one step when clamping
fires.

### 12.5 Seniority × leadership cap table

| seniority | `leadership_enablement` max when leadership_evidence_band |
| --- | --- |
|  | `none` / `partial` / `strong` |
| `junior` | 5 / 8 / 10 |
| `mid` | 8 / 12 / 15 |
| `senior` | 10 / 18 / 25 |
| `staff_plus` | 15 / 25 / 35 |
| `manager` | 15 / 25 / 35 |
| `director_plus` | 15 / 30 / 45 |

Analogous architecture cap: `architecture_system_design` is clamped by
`architecture_evidence_band` × role family (table committed in the
validator module; seed values — `none:15`, `partial:25`, `strong:40`
for architecture-leaning roles; subtract 10 for non-architecture-leaning
roles).

### 12.6 Prompt constraints

`P-experience-dimension-weights@v1` inherits `SHARED_CONTRACT_HEADER`
and adds:

- You do not know the candidate. No first-person language. No prose.
- Use only the canonical `ExperienceDimension` enum. You may not invent
  new dimension names.
- Every `overall_weights` and non-null `stakeholder_variant_weights`
  entry MUST sum to exactly 100. Integer values only. No floats, no
  negatives.
- `stakeholder_variant_weights` entries MUST be a subset of
  `evaluator_coverage_target` provided in the payload. Unlisted personas
  MUST be `null`.
- `ai_ml_depth` MUST not exceed the AI cap provided in the payload.
- `architecture_system_design` MUST not dominate without corresponding
  architecture evidence band.
- `leadership_enablement` MUST not dominate without corresponding
  leadership evidence band.
- Weights MUST be coherent with `must_signal[]` and `should_signal[]`
  from `ideal_candidate_presentation_model`.
- Weights MUST NOT contradict `section_emphasis[]` from
  `cv_shape_expectations`.
- Weights MUST NOT exceed any `cap_dimension_weight` rule from
  `truth_constrained_emphasis_rules`.
- Unresolved is a valid first-class answer. Prefer
  `unresolved_markers[]` and conservative defaults over invented weight.
- Explain trade-offs in `rationale`, not just top scores. Reference
  upstream artifacts in `evidence[]` using
  `source:<source_id>` or `artifact:<dotted-path>`.
- Never attribute preferences to named real stakeholders; reason in
  evaluator-role terms only.

## 13. Deterministic Post-Pass and Validation

The post-pass runs inside `presentation_contract` after the prompt
returns and before the parent artifact is persisted. It is a gate, not a
repair step, except where §12.2 explicitly permits one retry.

### 13.1 Shape rules (hard fail unless repair-eligible)

- every key in every weight map is in the `ExperienceDimension` enum;
- every value is a non-negative integer;
- `overall_weights` sum == 100;
- each non-null `stakeholder_variant_weights[...]` sum == 100;
- `stakeholder_variant_weights` keys ⊆ `evaluator_coverage_target`;
- `minimum_visible_dimensions` ⊆ enum, size ≤ 5;
- `overuse_risks[].dimension` ⊆ enum;
- `dimension_enum_version` matches the registered current version.

Repair-eligible defects (§12.2): `enum_drift`, `non_integer_value`,
`sum_off_by_one`, `orphan_variant_key`, `unknown_overuse_dimension`.
Non-recoverable: `candidate_leakage`, `fabricated_dimension`,
`fail_closed_cap_breach` after one clamp attempt.

### 13.2 Cross-subdocument invariants

Enforced at the single `presentation_contract` cross-validator gate:

1. **sum-to-100**: `overall_weights` and every non-null
   `stakeholder_variant_weights[*]`.
2. **canonical enum only**: all keys and enum refs use the registered
   `ExperienceDimension`.
3. **non-negative integers**: type-validated at ingress.
4. **stakeholder variants gated**: variant keys ⊆
   `stakeholder_surface.evaluator_coverage_target`.
5. **minimum-visible subset**: `minimum_visible_dimensions[] ⊆` enum.
6. **overuse-risks canonical**: `overuse_risks[].dimension ⊆` enum and
   does not conflict with a top-weighted dimension lacking mitigation.
7. **AI cap**: `overall_weights.ai_ml_depth ≤` the §12.4 cap for
   `classification.ai_taxonomy.intensity`.
8. **Architecture evidence cap**: `architecture_system_design` does not
   dominate without `architecture_evidence_band ∈ {partial, strong}`
   (per §12.5).
9. **Leadership evidence cap**: `leadership_enablement` does not
   dominate without `leadership_evidence_band ∈ {partial, strong}` and
   appropriate seniority (§12.5).
10. **Section-emphasis coherence**: `overall_weights` high-weighted
    dimensions do not contradict
    `cv_shape_expectations.section_emphasis[].focus_categories` for
    `key_achievements`, `experience`, and `ai_highlights`.
11. **Ideal-candidate coherence**: for every
    `ideal_candidate_presentation_model.must_signal[]` tagged with a
    canonical dimension, that dimension's weight in `overall_weights`
    is ≥ 10 (or an `unresolved_marker` justifies the exception); for
    every `de_emphasize[]` dimension, weight ≤ 5 unless flagged as an
    `overuse_risk`.
12. **Proof-ladder coherence**: the top rungs of
    `ideal_candidate_presentation_model.proof_ladder[]` map to non-
    trivial weights in `overall_weights` via
    `proof_category_dimension_map` (§9.3).
13. **Truth-constraint coherence**: no `overall_weights[d]` exceeds any
    `truth_constrained_emphasis_rules.cap_dimension_weight` with
    `applies_to == d`.
14. **Confidence coherence**: when `stakeholder_surface.status ∈
    {inferred_only, no_research, unresolved}` or
    `research_enrichment.status ∈ {partial, unresolved}`,
    `confidence.band ≤ medium`.
15. **Fail-open discipline**: `defaults_applied[]` is non-empty whenever
    `status ∈ {partial, inferred_only}`.

Failure of any invariant after the one-retry repair budget fails the
entire `presentation_contract` run and falls back to role-family
defaults per umbrella §8.2.

### 13.3 Anti-hallucination rules

- no invented dimension names (post-pass rejects unknown keys);
- no variants for unseen personas (post-pass nulls and logs);
- no fabricated company events or metrics referenced in `rationale`
  beyond what evidence refs resolve;
- no first-person language in any string field (candidate-leakage
  detector, inherited from 4.2.2 §5.4);
- no claim that a real named stakeholder "wants" X; only evaluator-role
  framing.

## 14. Fail-Open / Fail-Closed

**Fail open:**

- `stakeholder_surface.status ∈ {inferred_only, no_research, unresolved}`
  → emit `overall_weights` and the two always-in-scope variants
  (`recruiter`, `hiring_manager`) from the role-family default table,
  cap `confidence.band ≤ medium`, populate
  `unresolved_markers[]`.
- `pain_point_intelligence.status ∈ {partial, unresolved}` → skip the
  proof-category-driven nudge but keep role-family priors;
  `confidence.band ≤ medium`; record `defaults_applied[]`.
- `research_enrichment.role_profile.status = partial` → rely on
  `classification.primary_role_category` priors; record in
  `rationale` which defaults were applied.
- LLM emits invalid sums → one schema-repair retry; if still invalid,
  fall back to role-family default table and emit `status = partial`
  with `fail_open_reason = "schema_repair_exhausted"`.

**Fail closed:**

- unknown dimension keys (after one repair retry);
- negative or float weights;
- variants for personas not in `evaluator_coverage_target`;
- AI cap breach after clamp;
- contradictions with 4.2.6 `cap_dimension_weight` rules;
- cross-subdocument invariant violations (§13.2) after clamp;
- candidate-leakage (first-person, candidate names, candidate metrics);
- fabricated dimension labels or fabricated stakeholder persona keys.

Fail-closed always wins. A coverage gap never justifies lowering policy
standards.

Minimum acceptable `status = inferred_only` artifact:

- `overall_weights` populated (role-family default, sum 100);
- `stakeholder_variant_weights.recruiter` and `.hiring_manager`
  populated (always-in-scope pair);
- `minimum_visible_dimensions[]` at least one entry;
- `defaults_applied[]` non-empty;
- `confidence.band ≤ medium`;
- at least one `unresolved_marker`.

## 15. Safety / Anti-Hallucination Rules

Inherited from 4.2 umbrella §8.5 and restated as hard implementation
rules:

- every non-default weighting choice carries `evidence[]` refs that
  resolve to `source:<id>` (in `pain_point_intelligence.sources[]` or
  `research_enrichment.sources[]`) or `artifact:<dotted-path>` rooted at
  `pre_enrichment.outputs.*`.
- prompt must instruct: "Unresolved is a valid answer. Prefer
  `unresolved_markers[]` over guessed weights."
- prompt must instruct: "Do not invent dimensions, variants, or
  evaluator personas outside the enums and coverage target provided."
- prompt must instruct: "Do not assume the candidate has strengths in
  any dimension. Weights describe document preference, not candidate
  truth."
- prompt must instruct: "Do not infer private motives, protected
  traits, or clinical psychology."
- the deterministic post-pass is the single source of truth for
  enforcement.

## 16. Operational Catalogue

4.2.5 adds no stage, no work item, no lease, no collection. Its
operational surface is entirely embedded in `presentation_contract`.
Everything below is written against that constraint.

### 16.1 Owning stage

- Owning stage: `presentation_contract` (see 4.2.2 §12).
- Owning subdocument: `experience_dimension_weights`.
- Registered in `_blueprint_registry()` only as part of the parent
  stage. 4.2.5 contributes no `StageDefinition` of its own.

### 16.2 Prerequisite artifacts

`presentation_contract` must not synthesize 4.2.5 unless every required
input in §9.1 is present and its `status` is at least `partial`. When
upstream is missing, the parent stage still runs, and 4.2.5 either
produces `status = inferred_only` or downgrades the whole subdocument to
`unresolved` — it never fails the parent run.

### 16.3 Mongo persistence map

| What | Location |
| --- | --- |
| Subdocument body | `level-2.pre_enrichment.outputs.presentation_contract.experience_dimension_weights` |
| Parent collection mirror (if applicable) | `presentation_contract` collection, inside the `PresentationContractDoc` body |
| Parent stage state | `level-2.pre_enrichment.stage_states.presentation_contract` |
| Compact snapshot | `level-2.pre_enrichment.job_blueprint_snapshot.presentation_contract_compact.dimension_weights` |
| Work item | **no 4.2.5-specific item**; parent `work_items` row with `task_type="preenrich.presentation_contract"` |
| Run audit | `preenrich_stage_runs` (one row per parent stage run; carries 4.2.5 substage metadata) and `preenrich_job_runs` (aggregate) |
| Debug | inside the subdocument under `experience_dimension_weights.debug_context`, size-capped |
| Alerts | `preenrich_alerts` (parent-stage deadletter only; 4.2.5 never alerts independently) |

Compact snapshot projection shape (computed by `blueprint_assembly`):

```
presentation_contract_compact.dimension_weights {
  status,
  confidence_band,
  dimension_enum_version,
  overall_top3: [ {dimension, weight}, ... ],
  overall_weight_sum,
  non_zero_dimension_count,
  stakeholder_variant_count,
  minimum_visible_dimensions_count,
  overuse_risks_count,
  ai_ml_depth_weight,
  architecture_weight,
  leadership_weight,
  business_impact_weight,
  defaults_applied_count,
  normalization_events_count,
  trace_ref: { trace_id, trace_url },
  artifact_ref: { collection: "presentation_contract", _id, subpath: "experience_dimension_weights" }
}
```

No full weight maps, no rationale bodies in the snapshot.

### 16.4 Subdocument status semantics

`experience_dimension_weights.status`:

- `completed` — full synthesis, all invariants passed, confidence not
  capped.
- `partial` — one or more fields defaulted (e.g.
  `stakeholder_variant_weights.peer_reviewer = null` because coverage
  target excluded it), confidence ≤ medium.
- `inferred_only` — body generated from role-family priors because
  upstream signals are sparse; `defaults_applied[]` populated.
- `unresolved` — minimum artifact could not be assembled; parent run
  still succeeds with this subdocument as `unresolved` if and only if
  other subdocuments succeed and the parent allows degraded persistence
  per umbrella §8.2.

The parent stage does **not** deadletter on 4.2.5 alone. Parent-stage
deadletter still owns retry semantics.

### 16.5 Retry / repair behavior at subdocument level

- Exactly **one** in-stage schema-repair retry specific to 4.2.5 for
  the defect set in §13.1.
- The retry is tracked on the
  `scout.preenrich.presentation_contract.dimension_weights.schema_repair`
  substep span.
- If the retry still fails, the parent falls back to the role-family
  default table (not a deadletter). `status = partial`,
  `fail_open_reason = "schema_repair_exhausted"`, and
  `defaults_applied[]` records the prior id.
- Parent-stage `max_attempts = 3` retries govern worker-level retries
  (network errors, transient provider failures). 4.2.5 does not add
  its own worker retry budget.

### 16.6 Cache behavior

- 4.2.5 inherits `presentation_contract_input_hash` (§9.4). No
  separate cache key.
- On cache hit, the parent stage skips the LLM call for all four
  subdocuments together and re-projects the cached doc.
- Cache bust triggers: any input in §9.4, any prompt version bump,
  any `DIMENSION_ENUM_VERSION` bump.
- Cache hit/miss is emitted only at the parent level
  (`scout.preenrich.presentation_contract.cache.hit|miss`), not per
  subdocument.

### 16.7 Heartbeat expectations

- Parent stage heartbeat (`PREENRICH_STAGE_HEARTBEAT_SECONDS`, default
  60s) applies. 4.2.5 does not add its own heartbeat.
- The dimension_weights substep must not hold CPU > 10s between yield
  points (prompt build, LLM call, post-pass). This is a small LLM call
  with a deterministic post-pass; longer is a signal of preflight
  over-expansion or runaway repair.
- Launcher-side operator heartbeat (15–30s) is owned by the parent
  stage launcher (§19.8); 4.2.5 surfaces its substep in the heartbeat
  output with `last_substep`.

### 16.8 Feature flags

- **`presentation_contract_enabled()`** — master flag for the parent
  stage. Off ⇒ 4.2.5 is not synthesized; `blueprint_assembly` continues
  its legacy compat.
- **`presentation_contract_dimension_weights_enabled()`** — optional
  sub-flag for the LLM synthesis path. When off, the parent stage
  still emits a 4.2.5 subdocument but uses only the role-family
  default table (fully deterministic, no LLM call). Default: off for
  the rollout window; on when 4.2.5 is bench-gated.
- **`presentation_contract_merged_prompt_enabled()`** — owned by 4.2.2;
  affects whether 4.2.5 is synthesized in merged or split mode. Span
  names are stable across modes (§12.1).

### 16.9 Downstream consumers

- **`blueprint_assembly`** — compact snapshot projection (§16.3).
- **`cv_guidelines`** migration — once migrated, reads
  `experience_dimension_weights.overall_weights` for dimension priors.
- **4.3.x CV skeleton and candidate-aware generation** — reads
  `overall_weights`, `stakeholder_variant_weights`,
  `minimum_visible_dimensions[]`, and `overuse_risks[]` for
  front-loading, section emphasis, and achievement selection.
- **Reviewer UI** — renders top-weighted dimensions and variant
  divergence per stakeholder for "what this CV should emphasize".

### 16.10 Rollback strategy

- Toggle `presentation_contract_dimension_weights_enabled()` off ⇒
  parent stage still emits the subdocument from the role-family
  default table; no data migration.
- Toggle `presentation_contract_enabled()` off ⇒ 4.2.5 subdocument is
  not produced at all; downstream consumers fall back to implicit
  salience.
- No schema migration on rollback. Existing persisted subdocuments
  remain valid and inert until re-run.

### 16.11 Why no separate cache keys or trace refs beyond the parent

- the four subdocuments share one evidence frame and one invalidation
  key; splitting caches would let them drift;
- the parent stage already owns artifact persistence and
  `preenrich_stage_runs`; adding a 4.2.5-specific trace ref would
  duplicate without operator benefit;
- telemetry for 4.2.5 is expressed through substage spans under the
  single parent trace, giving operators one click from Mongo → parent
  trace → 4.2.5 substage.

## 17. Langfuse Tracing Contract

Inherits 4.2 umbrella §8.8 verbatim and
`presentation_contract` stage-level rules in 4.2.2 §9.5. The section
below is normative for 4.2.5 only.

### 17.1 Parent span and subspan taxonomy

- parent stage span: `scout.preenrich.presentation_contract` (owned by
  4.2.2 §9.5).
- 4.2.5 subspan: `scout.preenrich.presentation_contract.dimension_weights`.
- optional child spans beneath the 4.2.5 subspan, emitted only when
  they meaningfully time work:
  - `.prompt_build`
  - `.llm_call` — primary and fallback named
    `.llm_call.primary` / `.llm_call.fallback`.
  - `.post_pass`
  - `.schema_repair` — only when the repair retry fires (§13.1).
  - `.cross_validate` — only when 4.2.5's post-pass feeds the
    cross-subdocument validator and meaningfully times the
    invariant batch.

No per-dimension, per-variant, or per-overuse-risk spans. Cardinality
is expressed through metadata counts, never through span names.

### 17.2 Events

- `scout.preenrich.presentation_contract.consistency.dimension_weights`
  — emitted when the deterministic post-pass clamps a weight, nulls an
  ungated variant, or suppresses a rule to satisfy an invariant.
  Metadata: `kind`, `from`, `to`, `reason`, `affected_dimension`.
- `scout.preenrich.presentation_contract.fail_open` — emitted with
  `source_subdocument = "dimension_weights"` when 4.2.5 downgrades to
  `partial` / `inferred_only` / `unresolved`.

Canonical lifecycle events (`claim`, `enqueue_next`, `retry`,
`deadletter`, `release_lease`, `snapshot_invalidation`) stay at the
parent stage and are not re-emitted.

### 17.3 Required metadata (inherited)

Every span and event carries the canonical payload from
`PreenrichTracingSession.payload_builder`:

`job_id`, `level2_job_id`, `correlation_id`, `langfuse_session_id`,
`run_id`, `worker_id`, `task_type`, `stage_name`, `attempt_count`,
`attempt_token`, `input_snapshot_id`, `jd_checksum`, `lifecycle_before`,
`lifecycle_after`, `work_item_id`.

### 17.4 Stage-specific metadata (on the 4.2.5 subspan end)

- `status` — `completed | partial | inferred_only | unresolved | failed`.
- `source_scope` — `jd_only | jd_plus_research |
  jd_plus_research_plus_stakeholder`.
- `dimension_enum_version`.
- **weight-map health:**
  - `overall_weight_sum` (expected 100; surfaced for alerting when off).
  - `non_zero_dimension_count`.
  - `minimum_visible_dimensions_count`.
  - `overuse_risks_count`.
- **per-key highlights (for alerting):**
  - `ai_ml_depth_weight`
  - `architecture_weight` (i.e. `architecture_system_design`)
  - `leadership_weight` (i.e. `leadership_enablement`)
  - `business_impact_weight`
  - `hands_on_implementation_weight`
  - `platform_scaling_change_weight`
- **variant coverage:**
  - `stakeholder_variant_count` — count of non-null variants.
  - `variant_weight_sums_valid` — boolean; false if any non-null
    variant sum != 100.
  - `variants_emitted` — list subset of
    `{recruiter, hiring_manager, executive_sponsor, peer_reviewer}`.
- **cap outcomes:**
  - `ai_cap_applied` — boolean.
  - `ai_cap_value` — int cap that was applied.
  - `architecture_cap_applied` — boolean.
  - `leadership_cap_applied` — boolean.
- **normalization:**
  - `normalization_events_count`.
  - `defaults_applied_count`.
- **confidence:**
  - `confidence.score`.
  - `confidence.band`.
- **upstream availability:**
  - `jd_facts_available`, `classification_available`,
    `research_enrichment_available`, `stakeholder_surface_available`,
    `pain_point_intelligence_available`.
- **cross-validator outcome:**
  - `cross_subdoc_invariants_passed` — boolean.
  - `cross_subdoc_invariants_failed_list` — short list of failed
    invariant ids (§13.2).

Forbidden in span metadata: the full `overall_weights` map, the full
variant maps, rationale bodies, evidence bodies, full `debug_context`.
Those live only in Mongo.

### 17.5 Outcome classifications

`llm_call.*` spans carry the iteration-4 transport outcome classification
(`success | unsupported_transport | error_missing_binary | error_timeout
| error_subprocess | error_no_json | error_schema | error_exception`) and
`schema_valid: bool`.

### 17.6 Retry / repair metadata (on `.schema_repair` subspan)

- `repair_reason ∈ {enum_drift, non_integer_value, sum_off_by_one,
  orphan_variant_key, unknown_overuse_dimension}`.
- `repair_attempt` — always 1.
- `repaired_fields` — list of JSON paths repaired.
- `pre_repair_schema_valid: bool`, `post_repair_schema_valid: bool`.

Retry events use the canonical `scout.preenrich.retry` at the parent
level with `stage_name="presentation_contract"`; 4.2.5 does not retry
independently at the worker level.

### 17.7 Fail-open reason metadata

On the 4.2.5 subspan and on any
`scout.preenrich.presentation_contract.fail_open` event sourced from
4.2.5, exactly one of:

```
jd_only_fallback | thin_research | thin_stakeholder |
thin_pain_point_intelligence | schema_repair_exhausted |
cap_breach_clamped | cross_invariant_suppressed |
llm_terminal_failure
```

### 17.8 Trace refs into Mongo and parent artifact refs

- the parent stage's `trace_id` / `trace_url` flow into
  `preenrich_stage_runs`, `preenrich_job_runs`,
  `pre_enrichment.stage_states.presentation_contract`, and the parent
  artifact's `trace_ref`.
- 4.2.5 does **not** expose its own top-level `trace_ref`; the snapshot
  projection reuses the parent `trace_ref`. The subspan is reachable
  from the parent trace via standard Langfuse navigation.

### 17.9 Forbidden in Langfuse

- full weight maps (any of `overall_weights`,
  `stakeholder_variant_weights[*]`);
- full `rationale` body;
- full `evidence[]` bodies;
- full `debug_context`;
- raw LLM prompts except through `_sanitize_langfuse_payload` with
  `LANGFUSE_CAPTURE_FULL_PROMPTS=true`;
- any field matching `*prompt*` without sanitisation;
- any field exceeding 160 chars without the sanitizer.

### 17.10 What may live only in `debug_context`

- full `role_family_weight_priors`, `evaluator_dimension_pressure`,
  `proof_category_dimension_map`;
- full `normalization_events[]`;
- full LLM request ids and repair prompts;
- full pre-repair and post-repair outputs;
- rejected-output entries with reasons.

### 17.11 Cardinality and naming

- substep span names are a bounded set (§17.1);
- per-dimension details only via metadata counts and a few highlighted
  scalar weights (§17.4);
- repair attempts bounded at 1 → bounded span count;
- variants bounded at 4 → bounded span count.

### 17.12 Operator debug checklist (normative)

From Mongo → Langfuse, an operator must be able to diagnose in under
two minutes:

- sum-to-100 drift — inspect `overall_weight_sum` on the
  `dimension_weights` subspan.
- AI overuse — inspect `ai_ml_depth_weight`, `ai_cap_applied`,
  `ai_cap_value`.
- architecture overreach — inspect `architecture_cap_applied` and
  `architecture_evidence_band` (from parent preflight span metadata).
- leadership overreach — inspect `leadership_cap_applied` and
  `leadership_evidence_band`.
- variant gating issues — inspect `variants_emitted` vs
  `stakeholder_surface.evaluator_coverage_target`.
- schema repair usage — presence of the `.schema_repair` subspan and
  its `repair_reason`.
- fail-open — presence of the `.fail_open` event and its `fail_open_reason`.
- cross-validator suppression — presence of
  `.consistency.dimension_weights` events with `reason` and
  `affected_dimension`.

## 18. Tests and Evals

### 18.1 Unit tests — schema and normalizer

`tests/unit/preenrich/test_experience_dimension_weights_schema.py`:

- `ExperienceDimensionWeightsDoc` accepts canonical output.
- `extra="forbid"` rejects unknown top-level keys.
- unknown dimension keys rejected in `overall_weights` and variant
  maps.
- negative and float weights rejected.
- `stakeholder_variant_weights` non-null entry keys outside enum
  rejected.
- missing `dimension_enum_version` rejected.

`tests/unit/preenrich/test_experience_dimension_weights_normalizer.py`:

- aliases (`overall`, `weights`) → `overall_weights`.
- scalar→dict or list→dict drift normalized.
- richer output (extra per-dimension `rationale_line`) retained in
  `debug_context.richer_output_retained[]`.
- float-looking integers (`25.0`) coerced to 25; `25.5` rejected.
- candidate-leakage detector catches first-person in `rationale`.

### 18.2 Deterministic validator / invariants

Table-driven across §13.2:

- sum-to-100 (exact, off-by-one, off-by-more).
- canonical-enum-only (`overall_weights`, variants,
  `minimum_visible_dimensions[]`, `overuse_risks[]`).
- non-negative integers.
- stakeholder-variant gating (keys ⊆ coverage target).
- overuse-risk dimension validity.
- cross-subdoc coherence (mocked peer subdocuments).
- confidence-band clamp under thin stakeholder / research statuses.

### 18.3 Role-family-default fail-open

- every entry in the §12.3 role-family table produces a valid sum-to-100
  `overall_weights`.
- tail fill rule is deterministic; same inputs → same output.
- `defaults_applied[]` populated; `status = inferred_only`;
  `confidence.band ≤ medium`.

### 18.4 Cross-subdocument consistency

- contradiction with `cv_shape_expectations.section_emphasis[]` is
  detected and either corrected or suppressed with a
  `consistency.dimension_weights` event.
- contradiction with
  `ideal_candidate_presentation_model.must_signal[]` dimensions is
  detected (must_signal dimension with weight < 10 flagged unless
  `unresolved_marker` justifies it).
- `truth_constrained_emphasis_rules.cap_dimension_weight` beats a LLM-
  emitted higher weight; post-clamp weight respects the cap.
- merged-prompt mode still produces a distinct 4.2.5 subdocument with
  its own span and validator pass.

### 18.5 AI-intensity, architecture, leadership caps

- AI cap (§12.4): each intensity value, LLM emits over-cap weight →
  clamped; metadata `ai_cap_applied=True`, `ai_cap_value=<cap>`.
- architecture cap (§12.5): `architecture_evidence_band=none` →
  `architecture_system_design` clamped at low cap.
- leadership cap (§12.5): `seniority=junior` ×
  `leadership_evidence_band=none` → `leadership_enablement` clamped ≤ 5.

### 18.6 Stakeholder-variant gating

- variants for personas not in `evaluator_coverage_target` get nulled
  at ingress with a `normalization_events[]` entry; metadata reflects
  the actual `variants_emitted` set.
- all four variants emitted when `evaluator_coverage_target` covers
  all four; each sums to 100 independently.
- divergence from `overall_weights` without stakeholder evidence is
  softened toward `overall_weights` and logged.

### 18.7 Trace emission

Using a `FakeTracer`:

- the `scout.preenrich.presentation_contract.dimension_weights`
  subspan is emitted on every successful parent run.
- `prompt_build`, `llm_call.primary`, `post_pass` spans emitted on the
  happy path.
- `schema_repair` subspan emitted exactly when the validator fired a
  recoverable defect and the repair retry ran.
- `consistency.dimension_weights` event emitted when a cap or cross-
  invariant clamp fires.
- forbidden keys (full weight maps, rationale body) do not appear in
  any span payload (grep assertion on serialized payload).

### 18.8 Snapshot projection

- `blueprint_assembly` produces the full compact projection shape in
  §16.3 — no extra keys, no missing keys.
- snapshot never contains full weight maps or rationale.
- `trace_ref` matches the parent stage's `trace_id` / `trace_url`.

### 18.9 Regression corpus and reviewer rubric

- 30 curated `level-2` jobs under
  `tests/data/dimension_weights/corpus/` (10 IC, 10 EM / Director,
  10 Head / VP).
- golden outputs in `tests/data/dimension_weights/golden/` with
  per-field tolerance: weights exact, `rationale` fuzz-match via
  length and keyword set, `confidence.band` stable.
- reviewer rubric:
  - emphasis coherence (1–5): alignment with role mandate,
    evaluator surface, and must/should signals.
  - AI-cap correctness (1–5): does the emitted `ai_ml_depth_weight`
    match the intensity?
  - variant usefulness (1–5): do variants meaningfully diverge when
    evidence supports it?
  - overuse-risk usefulness (1–5): do flagged risks catch real
    overshoot cases?
- regression CI: mocked LLM returns recorded response; compare to
  golden; diff non-deterministic fields separately.

### 18.10 Live smoke

- `scripts/smoke_experience_dimension_weights.py` — loads `.env` from
  Python, runs only the parent `presentation_contract` stage (not a
  fake standalone 4.2.5 stage) against either one real `level-2` job
  by `_id` or a checked-in fixture via `--fixture`, asserts 4.2.5
  subdocument validity, and prints compact projection summary with
  heartbeat every 15s.

## 19. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. Validation runs through the `presentation_contract` stage on
VPS; there is no standalone 4.2.5 stage to run.

### 19.1 Local prerequisite tests before touching VPS

- `pytest -k "experience_dimension_weights"` clean.
- `pytest -k "presentation_contract"` clean (dimension_weights
  cross-validator covered here).
- `python -m scripts.preenrich_dry_run --stage presentation_contract
  --job <level2_id> --mock-llm` clean and the dry-run produces the
  4.2.5 subdocument.
- Langfuse sanitizer test green (no full weight maps in payload).
- compact snapshot test green (§18.8).

### 19.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path.
- verify the deployed `stage_registry.py` registers
  `presentation_contract` and the flag is on:
  `grep -n "presentation_contract" /root/scout-cron/src/preenrich/stage_registry.py`.
- verify `blueprint_prompts.py` contains
  `build_p_experience_dimension_weights` (or the merged builder when
  in merged mode).
- verify `blueprint_models.py` contains `ExperienceDimension`,
  `ExperienceDimensionWeightsDoc`, and
  `normalize_experience_dimension_weights_payload`.
- verify `presentation_contract_dimension_weights_enabled` exists in
  `config_flags.py` and matches the intended rollout posture.
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`.
- deployment is file-synced, not git-pulled — read sync markers; do
  not `git status`.

### 19.3 Target job selection

- pick a real `level-2` job with
  `pre_enrichment.outputs.jd_facts`, `classification`,
  `research_enrichment`, `stakeholder_surface`, and
  `pain_point_intelligence` all at `status="completed"`.
- prefer IC or EM mid-seniority with rich research and non-trivial
  stakeholder coverage (≥ 3 evaluator roles in coverage target).
- record `_id`, `jd_checksum`, and `input_snapshot_id`.
- choose a second job with
  `stakeholder_surface.status="inferred_only"` or
  `research_enrichment.status="partial"` to exercise fail-open.
- choose a third job with `classification.ai_taxonomy.intensity ∈
  {adjacent, none}` and JD keyword-inflated AI language to exercise
  the AI cap.
- if no real `level-2` document satisfies the third case, run the same
  validation against
  `data/presentation_contract_fixtures/low_ai_adjacent_full_upstream.json`
  via `scripts/smoke_experience_dimension_weights.py --fixture ...` or
  `scripts/vps_run_presentation_contract.py --fixture ...` with
  `--persist` left off.

### 19.4 Upstream artifact recovery

If `stage_states` show stale entries for the parent or prerequisites:

1. verify `pre_enrichment.outputs.{jd_facts, classification,
   research_enrichment, stakeholder_surface, pain_point_intelligence}`
   exist and `status != "unresolved"` where possible.
2. recompute the current `input_snapshot_id` deterministically
   (`python -u scripts/recompute_snapshot_id.py --job <_id>`).
3. re-enqueue missing prerequisites via
   `scripts/enqueue_stage.py`; never touch `work_items` directly.

### 19.5 Single-stage run path (fast path)

Preferred. A wrapper script `/tmp/run_presentation_contract_<job>.py`:

- loads `.env` in Python with explicit path:
  `from dotenv import load_dotenv; load_dotenv("/root/scout-cron/.env")`.
- reads `MONGODB_URI`.
- builds `StageContext` via `build_stage_context_for_job`.
- runs `PresentationContractStage().run(ctx)` directly.
- prints a heartbeat every 15s during LLM work: wall clock, elapsed,
  last substep (`preflight`, `document_expectations`,
  `cv_shape_expectations`, `ideal_candidate`, `dimension_weights`,
  `emphasis_rules`, `cross_validate`, `persist`), Codex PID if any,
  Codex stdout/stderr tail.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_presentation_contract_<job>.py \
  > /tmp/presentation_contract_<job>.log 2>&1 &
```

### 19.6 Full-chain path (fallback)

If the fast path is blocked by `StageContext` construction drift:

- enqueue `work_items` for the full prerequisite chain down to
  `presentation_contract`.
- start `preenrich_worker_runner.py` with
  `PREENRICH_STAGE_ALLOWLIST="presentation_contract"`.
- same `.venv`, `python -u`, Python-side `.env`, `MONGODB_URI`
  discipline.
- same operator heartbeat.

### 19.7 Required launcher behavior

- `.venv` activated (`source /root/scout-cron/.venv/bin/activate`
  OR absolute path to `.venv/bin/python`).
- `python -u` unbuffered.
- `.env` loaded from Python, not `source .env`.
- `MONGODB_URI` present.
- Codex subprocess cwd defaults to isolated
  `/tmp/codex-work-<job>/` unless repo context is explicitly required
  (`PREENRICH_CODEX_WORKDIR_PRESENTATION_CONTRACT` — only for
  debugging, never default).
- inner Codex PID and first 128 chars of stdout / stderr logged on
  every heartbeat.

### 19.8 Heartbeat requirements

- launcher operator heartbeat every 15–30s, showing:
  `last_substep`, elapsed since last substep change, Codex PID if
  any, last stage span duration.
- lease heartbeat every 60s by the parent worker
  (`PREENRICH_STAGE_HEARTBEAT_SECONDS`).
- silence > 90s between heartbeats is a stuck-run flag.

### 19.9 Expected Mongo writes

On success:

- `level-2.pre_enrichment.outputs.presentation_contract.experience_dimension_weights`
  populated with a valid `ExperienceDimensionWeightsDoc`.
- `level-2.pre_enrichment.stage_states.presentation_contract`:
  `status=completed`, `attempt_count`, `lease_owner` cleared,
  `trace_id`, `trace_url` set.
- `level-2.pre_enrichment.job_blueprint_snapshot.presentation_contract_compact.dimension_weights`
  matches §16.3 shape.
- `presentation_contract` collection (if enabled) has the new
  `PresentationContractDoc` containing the 4.2.5 subdocument.
- `preenrich_stage_runs`: one row per parent run with `trace_id`,
  `trace_url`, `provider_used`, `model_used`, `prompt_version`
  (parent), `tokens_input`, `tokens_output`, `cost_usd`, and
  substage metadata referencing `dimension_weights`.
- `preenrich_job_runs`: aggregate updated.
- `work_items`: parent row `status=completed`; next-stage enqueue
  fires if applicable.

### 19.10 Expected Langfuse traces

In the same trace (`scout.preenrich.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- `scout.preenrich.presentation_contract` stage span with canonical
  metadata.
- substep spans including
  `scout.preenrich.presentation_contract.preflight`,
  `...document_expectations`, `...cv_shape_expectations`,
  `...ideal_candidate`, **`...dimension_weights`**, `...emphasis_rules`,
  `...normalization`, `...cross_validate`, `...artifact_persist`.
- 4.2.5 subspan with full §17.4 metadata.
- optional `...dimension_weights.schema_repair` and
  `...consistency.dimension_weights` when applicable.
- one `cache.hit` or `cache.miss` event at the parent level.

### 19.11 Expected `preenrich_stage_runs` / `preenrich_job_runs`

- `stage_runs` row has `trace_id`, `trace_url`, `fail_open_reason` iff
  non-completed at the parent level.
- `job_runs` aggregate has updated
  `stage_status_map.presentation_contract`.
- Substage metadata on the `stage_runs` row records the 4.2.5 subspan
  summary (`status`, `confidence.band`, key weight highlights) without
  full bodies.

### 19.12 Stuck-run operator checks

If no heartbeat > 90s:

- tail `/tmp/presentation_contract_<job>.log`.
- inspect Codex PID:
  `ps -p <pid> -o pid,etime,stat,cmd`.
- inspect last output age of
  `/tmp/codex-work-<job>/stdout.log`.
- inspect Mongo stage_state:
  `level-2.pre_enrichment.stage_states.presentation_contract.lease_expires_at`.
- if lease is expiring and no progress, kill the launcher; do not
  restart until the prior PID is confirmed gone.

Silence is not progress.

### 19.13 Acceptance criteria

- launcher log ends with
  `PRESENTATION_CONTRACT_RUN_OK job=<id> status=<status> trace=<url>`.
- Mongo writes match §19.9.
- Langfuse trace matches §19.10, including the 4.2.5 subspan with
  §17.4 metadata.
- 4.2.5 subdocument validates against `ExperienceDimensionWeightsDoc`.
- spot-check:
  - `overall_weights` sums to 100 and uses only canonical dimensions;
  - each non-null variant sums to 100;
  - `variants_emitted ⊆ stakeholder_surface.evaluator_coverage_target`;
  - `ai_ml_depth_weight ≤ §12.4 cap for the job's intensity`;
  - `architecture_system_design` and `leadership_enablement` respect
    §12.5 caps;
  - `must_signal[]` dimensions are ≥ 10 in `overall_weights` (or a
    justified `unresolved_marker` exists).
- fail-open run (research-thin or stakeholder-thin) returns
  `status=partial` or `inferred_only` with a populated
  `defaults_applied[]` and an explicit `fail_open_reason`.

### 19.14 Artifact / log / report capture

Create `reports/presentation-contract/<job_id>/dimension_weights/`
containing:

- `run.log` — full stdout/stderr for the parent run.
- `subdocument.json` — the emitted 4.2.5 subdocument.
- `snapshot_projection.json` — the compact projection dump.
- `trace_url.txt` — Langfuse URL for the parent stage.
- `stage_runs_row.json` — `preenrich_stage_runs` row dump with
  substage summary.
- `mongo_writes.md` — human summary of §19.9 checks.
- `acceptance.md` — pass/fail list for §19.13.

## 20. Rollout, Feature Flags, Migration

### 20.1 Rollout order

1. Ship `ExperienceDimension` enum,
   `ExperienceDimensionWeightsDoc` schema, normalizer, deterministic
   default table, and validator behind
   `presentation_contract_dimension_weights_enabled()` off — parent
   stage emits the deterministic subdocument (no LLM call) in this
   phase. Unit + validator + snapshot tests green.
2. Flip `presentation_contract_dimension_weights_enabled()` on for a
   curated 30-job corpus in staging; collect reviewer metrics
   (§18.9); gate default-on on SC1–SC7.
3. Default-on in production behind `presentation_contract_enabled()`;
   monitor Langfuse for cap-clamp rate, fail-open rate, confidence
   band distribution.
4. Consider merged-prompt mode (owned by 4.2.2) only after 4.2.5 split
   mode is stable and benchmarks prove merged parity across §17.4
   metrics.

### 20.2 Migration

- no backfill of historical jobs at ship; 4.2.5 runs lazily on the
  next parent pipeline touch.
- snapshot projection is additive; existing snapshots continue to
  validate.
- `cv_guidelines` migration to read 4.2.5 is a separate follow-up
  plan.

### 20.3 Rollback

- Flip `presentation_contract_dimension_weights_enabled()` off ⇒ LLM
  path disabled; parent stage emits deterministic defaults.
- Flip `presentation_contract_enabled()` off ⇒ entire stage disabled;
  no 4.2.5 subdocument produced; downstream falls back to implicit
  salience.
- No data migration either way.

## 21. Open Questions

- **Q1.** Should `ExperienceDimension` expose a public alias for a
  simplified 6-axis view when the evaluator surface is narrow
  (recruiter-only)? Recommend no — collapse happens at
  consumer time, not artifact time.
- **Q2.** Should `overuse_risks[].reason` enum include
  `ats_keyword_inflation` as a distinct value? Recommend yes;
  ATS-heavy JDs are common and the distinction is operator-useful.
- **Q3.** Should `stakeholder_variant_weights[executive_sponsor]`
  produce a minimum-divergence hint from `overall_weights` when it
  is emitted but evidence is thin? Defer until variant eval corpus
  grows.
- **Q4.** Should confidence-band computation incorporate normalization
  count as a negative factor? Defer to a scoring follow-up; for now
  clamp confidence only when caps or repair fire.
- **Q5.** Should `dimension_enum_version` bumps trigger automatic
  parent cache bust? Recommend yes; wire it into
  `presentation_contract_input_hash` (§9.4).
- **Q6.** Should the `proof_category_dimension_map` (§9.3) be
  exposed as a top-level constant for 4.3.x consumers, or kept
  internal to `presentation_contract`? Lean internal until a
  second consumer needs it.

## 22. Primary Source Surfaces

- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md`
- `docs/current/achievement-review-tracker.yaml`
- `src/preenrich/stages/presentation_contract.py`
- `src/preenrich/blueprint_models.py`
  (`CompetencyWeightsModel`, `WeightingProfiles`,
  `ExpectationWeights`, existing sum-to-100 validators)
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/stage_registry.py`
- `src/preenrich/blueprint_config.py`
- `src/pipeline/tracing.py`
- `src/layer6_v2/prompts/grading_rubric.py`
- `plans/brainstorming-new-cv-v2.md`

## 23. Implementation Targets

- **`src/preenrich/blueprint_models.py`**
  - new `ExperienceDimension` enum (canonical list §10.1).
  - new `ExperienceDimensionWeightsDoc` model with sum-to-100
    validators modeled on `ExpectationWeights` / `OperatingStyleWeights`.
  - new `OveruseRisk`, `OveruseRiskReason`, `NormalizationEvent`,
    `ExperienceDimensionWeightsDebug` sub-models.
  - `normalize_experience_dimension_weights_payload()` ingress
    normalizer paralleling
    `normalize_document_expectations_payload`.
  - `DIMENSION_ENUM_VERSION` constant and `dimension_enum_version`
    field wiring.
- **`src/preenrich/blueprint_prompts.py`**
  - `build_p_experience_dimension_weights()` prompt builder.
  - `PROMPT_VERSIONS["experience_dimension_weights"] =
    "P-experience-dimension-weights@v1"`.
  - merged-prompt variant integration so
    `build_p_document_and_cv_shape()` (or its successor) also emits
    `experience_dimension_weights` in the same response.
- **`src/preenrich/stages/presentation_contract.py`**
  - preflight helpers: `role_family_weight_priors`,
    `evaluator_dimension_pressure`, `ai_intensity_cap`,
    `architecture_evidence_band`, `leadership_evidence_band`,
    `proof_category_dimension_map`.
  - synthesis call for `dimension_weights` in split mode; parse-time
    extraction in merged mode.
  - deterministic post-pass: sum-to-100, cap clamps, variant gating.
  - cross-subdocument validator extension (§13.2).
  - Langfuse substage emission:
    `scout.preenrich.presentation_contract.dimension_weights` with
    §17.4 metadata, plus child spans and consistency events.
  - role-family default table helper for fail-open (§12.3).
- **`src/preenrich/blueprint_config.py`**
  - `presentation_contract_dimension_weights_enabled()` sub-flag.
- **`src/preenrich/stages/blueprint_assembly.py`**
  - `presentation_contract_compact.dimension_weights` projection
    (§16.3).
- **Tests**
  - `tests/unit/preenrich/test_experience_dimension_weights_schema.py`
  - `tests/unit/preenrich/test_experience_dimension_weights_normalizer.py`
  - `tests/unit/preenrich/test_experience_dimension_weights_validator.py`
  - `tests/unit/preenrich/test_presentation_contract_dimension_weights_integration.py`
  - `tests/unit/preenrich/test_presentation_contract_dimension_weights_trace.py`
  - `tests/unit/preenrich/test_blueprint_assembly_dimension_weights_snapshot.py`
  - `tests/data/dimension_weights/corpus/` and
    `tests/data/dimension_weights/golden/` fixtures.
- **Scripts**
  - `scripts/smoke_experience_dimension_weights.py` (local smoke via
    the parent stage).
  - `scripts/vps_run_presentation_contract.py` wrapper template with
    heartbeat and artifact capture under
    `reports/presentation-contract/<job_id>/dimension_weights/`.
- **Validation fixtures**
  - `scripts/presentation_contract_validation_io.py` shared
    fixture-loading helper for local and VPS validation runs.
  - `data/presentation_contract_fixtures/low_ai_adjacent_full_upstream.json`
    for the low/adjacent-AI scenario when Mongo lacks a suitable
    upstream-complete job.
- **Docs**
  - `docs/current/architecture.md` "Iteration 4.2.5" section update.
  - `docs/current/missing.md` gap update.
  - optional `docs/current/decisions/2026-04-XX-dimension-enum-ownership.md`
    capturing the ownership and versioning policy in §10.
