# Iteration 4.2.6 Plan: Truth-Constrained Emphasis Rules

## 1. Executive Summary

`truth_constrained_emphasis_rules` is **one subdocument co-produced inside the
`presentation_contract` stage** (alongside 4.2.2 `document_expectations` /
`cv_shape_expectations`, 4.2.4 `ideal_candidate_presentation_model`, and 4.2.5
`experience_dimension_weights`). It is not a standalone preenrich stage, does
not register a `StageDefinition`, does not own a DAG node, does not enqueue a
`work_items` row, does not hold a worker lease, and does not own an
independent cache key.

Its job: emit a typed, enum-bounded **policy artifact** that tells later
candidate-aware CV generation what may be emphasized, what must be softened,
what must be omitted, and what must not be claimed at all without direct
candidate evidence. The artifact is strictly **candidate-agnostic**: it
defines guardrails over how the four other subdocuments' framing may be
expressed; it never asserts candidate truth, never names a candidate, never
emits CV prose, and never authorizes claims that are unsupported by
`pain_point_intelligence` evidence, `stakeholder_surface` reject signals,
`classification.ai_taxonomy.intensity`, or the JD itself.

It is the formalization layer for the qualitative risk surface 4.2.4 produces
(`risk_flags[]`, `de_emphasize[]`) and the cap surface 4.2.5 produces
(`overuse_risks[]`, intensity / evidence-band caps). Without it, downstream
generation has structure (4.2.2), identity (4.2.4), and weights (4.2.5) but
no enforceable claim-level policy. With it, every candidate-aware decision
in 4.3.x has a deterministic, auditable rule set to validate against.

Operational discipline is inherited from the rest of 4.2:

- **Mongo is the control plane.** `work_items`, `preenrich_stage_runs`,
  `preenrich_job_runs`, and
  `pre_enrichment.stage_states.presentation_contract` drive execution.
  4.2.6 adds no new control surface.
- **Langfuse is the observability sink.** The subdocument emits under the
  `scout.preenrich.presentation_contract.emphasis_rules` substage span with
  metadata-first payloads; full rule bodies live in Mongo `debug_context` and
  the persisted artifact, never in span bodies.
- **VPS validation** runs the `presentation_contract` stage end-to-end on a
  real `level-2` job and inspects the 4.2.6 subdocument. There is no fake
  standalone `preenrich.truth_constrained_emphasis_rules` stage.

## 2. Mission

Turn the question "what must this CV refuse to claim, soften, or omit
absent direct candidate evidence?" into a structured, enum-bounded,
deterministically validated rule set — candidate-agnostic, evaluator-aware,
and internally consistent with the other three `presentation_contract`
subdocuments — so every later generation step can both cite and be
verified against a single source of truth for emphasis policy.

## 3. Objectives

- **O1.** Produce a typed, enum-constrained
  `truth_constrained_emphasis_rules` subdocument inside every successful
  `presentation_contract` run.
- **O2.** Cover the mandatory claim-policy topic families
  (title inflation, AI claims, leadership scope, architecture claims,
  domain expertise, stakeholder-management claims, metrics / scale claims,
  credibility-ladder degradation) with at least one rule per family, each
  carrying stable `rule_id` and resolvable `evidence_refs[]`.
- **O3.** Enforce deterministic cross-subdocument invariants between
  4.2.6 and its peers (4.2.2 `proof_order` / `ai_section_policy` /
  `title_strategy` / canonical section ids; 4.2.4 `must_signal[]` /
  `should_signal[]` / `de_emphasize[]` / `acceptable_titles[]`;
  4.2.5 `ExperienceDimension` enum and dimension caps) at the single
  `presentation_contract` cross-validator gate.
- **O4.** Fail open to role-family + taxonomy priors with capped confidence
  and explicit `unresolved_markers[]` when upstream is thin; never fail the
  parent `presentation_contract` run solely because 4.2.6 had to default.
- **O5.** Fail closed on any rule that authorizes title inflation,
  unsupported AI depth, unsupported leadership scope, fabricated metrics,
  fabricated company events, or candidate-leakage; the deterministic
  post-pass is the single source of truth for enforcement.
- **O6.** Emit a Langfuse substage
  (`scout.preenrich.presentation_contract.emphasis_rules`) that lets an
  operator diagnose rule-set coverage gaps, conflict-resolution outcomes,
  schema-repair retries, and fail-open reasons in under two minutes from
  Mongo → trace.
- **O7.** Be validated on the VPS through the `presentation_contract` stage
  on a real `level-2` job with full upstream prerequisites before
  default-on rollout.

## 4. Goals

- **G1.** Single subdocument, single schema, single deterministic validator.
  No new collection, no new DAG node, no new work-item lifecycle, no new
  cache key beyond the parent `presentation_contract` stage, no new
  control plane.
- **G2.** Canonical `RuleTypeEnum` and `AppliesToScopeEnum` owned by 4.2.6,
  consumed but not redefined by other plans. Every other enum referenced by
  rules (`DocumentSectionIdEnum`, `ProofTypeEnum`, `ExperienceDimension`,
  `TitleStrategyEnum`, `AudienceVariantKey`) is **imported** from its
  owning peer plan. `rule_topic_family` enum (§10.6) is owned here and used
  to enforce mandatory coverage.
- **G3.** Compact snapshot projection inside
  `job_blueprint_snapshot.presentation_contract_compact.emphasis_rules`:
  counts, booleans, confidence band, parent `trace_ref`. Never full rule
  bodies, never `forbidden_claim_patterns[].example` strings.
- **G4.** Zero rules that authorize the behaviors 4.2.6 is meant to forbid;
  zero candidate leakage; zero `applies_to` references outside canonical
  enums; stable `rule_id` values across runs for the same input snapshot.
- **G5.** Feature-flag gating via the parent stage flag
  (`presentation_contract_enabled()`) plus an optional sub-flag
  (`presentation_contract_emphasis_rules_enabled()`) that controls the
  LLM synthesis path; the deterministic role-family-default fallback is
  always available and produces a valid minimum artifact.
- **G6.** Safe cohabitation with 4.2.2's merged-prompt mode
  (`P-document-and-cv-shape@v1`, eventually
  `P-document-ideal-shape-weights-rules@v1`): when the merged prompt runs,
  4.2.6 still emits a distinct parse-time subdocument with its own span,
  validator, and cross-validator pass.

## 5. Success Criteria

The subdocument is successful when, for a representative 30-job corpus
(mixed IC / EM / Director / Head, mixed research quality, mixed
ai_intensity, mixed ATS):

- **SC1.** 100% of `presentation_contract` runs produce a validated
  `truth_constrained_emphasis_rules` with
  `status ∈ {completed, partial, inferred_only, unresolved}`. None terminal
  due to 4.2.6 schema issues alone.
- **SC2.** Reviewer-rated rule usefulness ≥ 4.0 / 5 median (rubric §18.13).
- **SC3.** 100% of emitted rules satisfy: `rule_type ∈ RuleTypeEnum`,
  `applies_to ∈ AppliesToScopeEnum`, `rule_id` unique, `evidence_refs[]`
  non-empty, `confidence` populated.
- **SC4.** 100% of runs cover the mandatory `rule_topic_family[]` set
  (§10.6). Coverage gaps trigger `defaults_applied[]` and `status = partial`,
  never silent omission.
- **SC5.** 0 rules authorize title inflation past
  `cv_shape_expectations.title_strategy` /
  `ideal_candidate_presentation_model.acceptable_titles[]`.
- **SC6.** 0 rules authorize AI depth claims when
  `classification.ai_taxonomy.intensity ∈ {none, adjacent}`.
- **SC7.** 0 rules authorize leadership-depth claims when
  `classification.seniority ∈ {junior, mid, senior_ic}` and
  `jd_facts.team_context.direct_reports ≤ 0`.
- **SC8.** 0 `cap_dimension_weight` rules reference a dimension outside
  4.2.5's `ExperienceDimension` enum; 100% are honored by 4.2.5
  `overall_weights` (cross-validator I-CAP).
- **SC9.** For `stakeholder_surface.status ∈ {inferred_only, no_research,
  unresolved}` or `pain_point_intelligence.status ∈ {partial, unresolved}`,
  `confidence.band ≤ medium` and at least one `unresolved_marker` is set.
- **SC10.** Langfuse substage
  `scout.preenrich.presentation_contract.emphasis_rules` is emitted on every
  run with full §15.4 metadata, one click from the level-2 UI.
- **SC11.** VPS smoke (§17) completes on a real job with artifacts captured
  under `reports/presentation-contract/<job_id>/emphasis_rules/`.

## 6. Non-Goals

- Final CV prose, header text, summary copy, bullets, ordering commitments.
  4.2.6 emits policy, never copy.
- Candidate evidence retrieval, master-CV matching, STAR selection,
  achievement ranking. Those belong to 4.3.x.
- Claims about the *candidate's* strengths or weaknesses; 4.2.6 is purely
  about claim-policy guardrails.
- Ownership of `DocumentSectionIdEnum` (4.2.2), `ProofTypeEnum` (4.2.3),
  `ExperienceDimension` (4.2.5), `TitleStrategyEnum` (4.2.2),
  `AudienceVariantKey` (4.2.4). 4.2.6 imports and references; it never
  redefines.
- Ownership of `risk_flags[]` and `de_emphasize[]` *content* (4.2.4); 4.2.6
  formalizes those into enforceable rules but never authors 4.2.4's
  `RiskFlag[]` records.
- Ownership of dimension *weights* (4.2.5); 4.2.6 may emit
  `cap_dimension_weight` rules that bind a dimension above by enforceable
  policy, but never sets the actual weight value.
- A standalone preenrich stage, a distinct DAG node, an independent work
  item, an independent lease, an independent cache key, or its own
  top-level Langfuse trace.
- Private stakeholder motives, clinical / psychological profiling,
  protected-trait inference, manipulation tactics.
- Replacing the high-level `cv-generation-guide.md` ATS / role-family
  guidance; 4.2.6 is the structured machine-readable counterpart, not a
  doc rewrite.

## 7. Why This Artifact Exists

The system already encodes anti-hallucination posture in:

- `cv-generation-guide.md` (role guidance, ATS rules, anti-patterns).
- `outreach-detection-principles.md` (signal grounding rules).
- `grading_rubric.py` (CV grader heuristics).
- 4.2.2's `anti_patterns[]` (document-shape patterns like
  `tool_list_cv`).
- 4.2.4's `risk_flags[]` (qualitative risk surface).
- 4.2.5's `overuse_risks[]` and AI / architecture / leadership cap tables.

But none of these is a **machine-enforceable, candidate-agnostic claim
policy**. They are heuristics, advisory tags, or numeric caps. They cannot
be cited or refused against by a downstream generator the way a typed
`Rule` record can.

4.2.6 closes this gap. It produces:

- a typed `Rule[]` set with stable `rule_id`s,
- bounded `rule_type` and `applies_to` enums,
- evidence-bound rationale every downstream consumer can audit,
- topic-coverage guarantees (every risky topic family has at least one
  rule),
- a deterministic post-pass that refuses contradictions with the other
  three subdocuments.

It must live inside `presentation_contract` rather than as a standalone
stage because:

- it shares the same five upstream inputs as 4.2.2 / 4.2.4 / 4.2.5;
- it shares one evidence frame, one snapshot, and one cache key with those
  peers;
- it needs a single cross-validation gate against 4.2.2 `proof_order` /
  `ai_section_policy` / `title_strategy`, 4.2.4 `must_signal[]` /
  `should_signal[]` / `de_emphasize[]` / `acceptable_titles[]`, and 4.2.5
  `ExperienceDimension` weights;
- splitting it would invite prompt drift, contradictory rule sets, and
  extra cost for zero observational gain, since it performs no fetches
  and owns no identity-safety surface;
- failure containment: a 4.2.6 schema fault should not deadletter the job;
  it should fall back to role-family rule defaults inside the same parent
  stage.

## 8. Subdocument Boundary

### 8.1 Placement

Co-produced inside the `presentation_contract` stage. The parent stage is
placed in the DAG as:

```
jd_facts -> classification -> application_surface -> research_enrichment
   -> stakeholder_surface -> pain_point_intelligence -> presentation_contract
```

4.2.6 does not register a `StageDefinition`. It does not appear in
`_blueprint_registry()`. It does not enqueue a `work_items` row, does not
claim a lease, does not run its own retry loop at the worker level. The
parent `presentation_contract` stage owns all of those.

### 8.2 Relationship to peer subdocuments

- **`document_expectations` (4.2.2).** 4.2.6 reads `proof_order[]`,
  `anti_patterns[]`, `tone_posture`, and `density_posture` as upstream
  peers. `forbidden_claim_patterns[]` MUST NOT contradict
  `document_expectations.proof_order[]` (e.g. forbidding `metric` evidence
  when `metric` is the top proof category). Rules MUST NOT undo the
  document's primary thesis (e.g. `forbid_without_direct_proof` over an
  entire dominant proof category without a fallback path).
- **`cv_shape_expectations` (4.2.2).** `applies_to` in `section_rules[]` is
  drawn from `cv_shape_expectations.section_order[]` ⊆
  `DocumentSectionIdEnum`. Title-related rules MUST be consistent with
  `cv_shape_expectations.title_strategy`. AI-section rules MUST be
  consistent with `cv_shape_expectations.ai_section_policy`. The 4.2.6
  rule for `omit_ai_highlights_if_policy_discouraged` is a reflection,
  not a re-decision, of 4.2.2's policy.
- **`ideal_candidate_presentation_model` (4.2.4).** Title-related rules
  MUST be consistent with
  `ideal_candidate_presentation_model.title_strategy` and
  `acceptable_titles[]`. Rules MUST NOT contradict 4.2.4's
  `must_signal[]` or `should_signal[]` (e.g. `omit_if_weak` over a
  `must_signal[]` proof type is forbidden unless an
  `unresolved_marker` justifies it). 4.2.6 may formalize 4.2.4's
  `de_emphasize[]` and `risk_flags[]` into enforceable `Rule[]` records.
- **`experience_dimension_weights` (4.2.5).** `cap_dimension_weight` rules
  MUST reference only canonical `ExperienceDimension` enum values.
  4.2.6 may emit caps that bind 4.2.5's `overall_weights[d]` from above;
  the cross-validator (4.2.5 §13.2 invariant 13) clamps any LLM-emitted
  weight that exceeds these caps.
- **Final `presentation_contract`.** All four subdocuments co-persist in
  one `PresentationContractDoc`. 4.2.6 is one of those four. Cross-
  subdocument invariants (§13) are validated in a single deterministic
  gate before persistence.

### 8.3 Relationship to upstream `IdealCandidateProfileModel` and grading rubric

`jd_facts.extraction.ideal_candidate_profile` and
`src/layer6_v2/prompts/grading_rubric.py` are read-only priors. 4.2.6 may
seed `forbidden_claim_patterns[]` from rubric anti-patterns (e.g.
"buzzword stacking", "metric without scope") and may seed
`credibility_ladder_rules[]` from the rubric's evaluator-truth heuristics.
4.2.6 must not author candidate-specific claims by reading these priors.

## 9. Inputs

### 9.1 Required (from `pre_enrichment.outputs`)

- `jd_facts.merged_view` — particularly `title`, `normalized_title`,
  `seniority_level`, `top_keywords`, `responsibilities`, `qualifications`,
  `expectations`, `identity_signals`, `team_context`,
  `weighting_profiles`, `skill_dimension_profile`, `ideal_candidate_profile`.
- `classification` — `primary_role_category`, `secondary_role_categories`,
  `seniority`, `tone_family`, `ai_taxonomy.intensity`,
  `ai_taxonomy.modalities`.
- `research_enrichment.role_profile` — `mandate`, `business_impact`,
  `evaluation_signals[]`, `risk_landscape[]`, `interview_themes[]`.
- `research_enrichment.company_profile` — `signals[]`,
  `scale_signals[]`, `ai_data_platform_maturity`,
  `identity_confidence.band`.
- `stakeholder_surface` — `evaluator_coverage_target[]`, per-role
  `cv_preference_surface`, `likely_reject_signals[]`, `status`.
- `pain_point_intelligence` — `proof_map[]`, `bad_proof_patterns[]`,
  `pain_points[].likely_proof_targets[]`, `status`.

### 9.2 Opportunistic (same-run peers; never hard prerequisites)

- `document_expectations` (4.2.2) — for `proof_order[]`, `anti_patterns[]`,
  `tone_posture`, `density_posture`. Used for cross-consistency.
- `cv_shape_expectations` (4.2.2) — for `section_order[]`,
  `title_strategy`, `ai_section_policy`, `section_emphasis[]`,
  `compression_rules[]`, `omission_rules[]`. Used to align
  `section_rules[]` and title-related rules.
- `ideal_candidate_presentation_model` (4.2.4) — for `title_strategy`,
  `acceptable_titles[]`, `must_signal[]`, `should_signal[]`,
  `de_emphasize[]`, `risk_flags[]`, `proof_ladder[]`,
  `audience_variants{}`. Used to formalize qualitative risk surface.
- `experience_dimension_weights` (4.2.5) — for `overall_weights{}`,
  `overuse_risks[]`, `ai_intensity_cap`, `architecture_evidence_band`,
  `leadership_evidence_band`. Used to align
  `cap_dimension_weight` rules.

The parent stage enforces temporal ordering. Default split-prompt mode:
`document_expectations` → `cv_shape_expectations` → `ideal_candidate` →
`dimension_weights` → **`emphasis_rules`** → cross-validator. In merged-
prompt mode, the parse-time split hydrates all four subdocuments from the
single LLM response with the same peer references.

### 9.3 Deterministic preflight helpers (extending 4.2.2 / 4.2.4 / 4.2.5)

Constructed by the parent `presentation_contract` preflight pass and
projected into 4.2.6's prompt payload:

- **`role_family_emphasis_rule_priors`** — per-role-family default `Rule[]`
  set covering the mandatory topic families (§10.6). Seeds from
  `cv-generation-guide.md` §6 role guidance, `grading_rubric.py`
  anti-patterns, and the existing 4.2.2 `anti_patterns[]` list. This map
  is the deterministic fail-open target.
- **`title_safety_envelope`** — derived from `jd_facts.title`,
  `jd_facts.identity_signals.title_safety_band`,
  `cv_shape_expectations.title_strategy`,
  `ideal_candidate_presentation_model.acceptable_titles[]` (when
  available). Bounds title-related rules.
- **`ai_claim_envelope`** — derived from
  `classification.ai_taxonomy.intensity`,
  `cv_shape_expectations.ai_section_policy`, and 4.2.5's
  `ai_intensity_cap`. Bounds AI-related rules; emits a default
  `forbid_without_direct_proof` rule when intensity ∈ {none, adjacent}.
- **`leadership_claim_envelope`** — derived from
  `classification.seniority`, `jd_facts.team_context.direct_reports`,
  4.2.5's `leadership_evidence_band`. Bounds leadership-related rules.
- **`architecture_claim_envelope`** — derived from
  `research_enrichment.role_profile.mandate`,
  `company_profile.scale_signals[]`, and 4.2.5's
  `architecture_evidence_band`. Bounds architecture-related rules.
- **`forbidden_claim_pattern_priors`** — curated stop-list seeded from
  `grading_rubric.py` and existing CV anti-patterns ("rockstar",
  "ninja", "guru", "10x", "thought leader", "passionate about",
  "team player", "strategic visionary"). Used as a baseline; LLM may
  extend, never replace.
- **`credibility_ladder_priors`** — per-role-family fallback ladder
  expressing how proof should degrade gracefully when evidence is thin
  (e.g. `metric → scope → architecture → tooling` for engineering roles;
  `outcome → org → influence → narrative` for leadership roles).

All preflight helpers are deterministic, idempotent, and recorded under
`debug_context.input_summary`. Preflight never fails the subdocument.

### 9.4 Invalidation / cache

4.2.6 has **no independent cache key**. Cache invalidation is the parent
stage's `presentation_contract_input_hash`, which incorporates:

- `jd_facts.merged_view`,
- `classification` (including `ai_taxonomy`),
- `research_enrichment.research_input_hash`, `status`,
- `stakeholder_surface.coverage_digest`,
- `pain_point_intelligence.pain_input_hash`,
- `PROMPT_VERSIONS["emphasis_rules"]`,
- `RULE_TYPE_ENUM_VERSION`,
- `APPLIES_TO_ENUM_VERSION`.

Drift in any of those busts the parent cache and re-synthesizes all four
subdocuments together. This is intentional: the four are co-validated
and must stay in lock-step.

## 10. Output Shape

### 10.1 Top-level Pydantic model

`TruthConstrainedEmphasisRulesDoc` in `src/preenrich/blueprint_models.py`,
nested under `PresentationContractDoc.truth_constrained_emphasis_rules`
(analogous to existing `document_expectations` / `cv_shape_expectations`
slots).

```text
TruthConstrainedEmphasisRulesDoc {
  status,                            # "completed" | "partial" | "inferred_only"
                                     # | "unresolved" | "failed_terminal"
  source_scope,                      # "jd_only" | "jd_plus_research"
                                     # | "jd_plus_research_plus_stakeholder"
  rule_type_enum_version,            # "v1"
  applies_to_enum_version,           # "v1"
  prompt_version,                    # "P-emphasis-rules@v1"
  prompt_metadata: PromptMetadata,
  global_rules: list[Rule],          # 0..12; cross-section policy
  section_rules: dict[              # one bucket per canonical section id
    DocumentSectionIdEnum,           # in scope (header, summary, etc.)
    list[Rule]                       # 0..6 per section
  ],
  allowed_if_evidenced: list[Rule],  # 0..12
  downgrade_rules: list[Rule],       # 0..12
  omit_rules: list[Rule],            # 0..12
  forbidden_claim_patterns: list[ForbiddenClaimPattern],  # 2..16
  credibility_ladder_rules: list[CredibilityLadderRule],  # 1..6
  topic_coverage: list[TopicCoverageEntry],   # one per RuleTopicFamily
  rationale,                         # 1-3 short paragraphs, <= 800 chars
  unresolved_markers: list[str],     # bounded 12 entries
  defaults_applied: list[str],       # role-family-prior ids applied
  normalization_events: list[NormalizationEvent],
  confidence: ConfidenceDoc,
  evidence: list[EvidenceEntry],
  notes: list[str],                  # short implementation-visible notes
  debug_context: TruthConstrainedEmphasisRulesDebug,
}
```

### 10.2 `Rule` shape

```text
Rule {
  rule_id,                           # stable slug, lower_snake_case, <= 64 chars
                                     # format: "tcer_<topic>_<applies_to>_<hash6>"
  rule_type,                         # RuleTypeEnum (§10.5)
  topic_family,                      # RuleTopicFamily (§10.6)
  applies_to,                        # AppliesToScope (§10.7); resolved id string
  applies_to_kind,                   # AppliesToKindEnum (§10.7): section | proof
                                     # | dimension | global | audience_variant
  condition,                         # <= 240 chars, evaluator-truth condition
  action,                            # <= 240 chars, what later generation must do
  basis,                             # <= 200 chars, short rationale
  source_refs: list[str],            # artifact:<dotted-path> or source:<id>
  precedence,                        # int 0-100; higher overrides lower on conflict
  confidence: ConfidenceDoc,
}
```

`rule_id` is stable: derived deterministically from
`(topic_family, applies_to_kind, applies_to, hash6(canonical_condition))`.
The post-pass enforces stability across runs of the same input snapshot.

### 10.3 `ForbiddenClaimPattern` shape

```text
ForbiddenClaimPattern {
  pattern_id,                        # stable slug, <= 64 chars
  pattern,                           # case-insensitive substring or simple regex
                                     # (regex restricted to char classes + quantifiers,
                                     # no lookarounds, no backrefs)
  pattern_kind,                      # "substring" | "regex_safe"
  reason,                            # <= 200 chars; *not* the matched example
  example,                           # <= 160 chars; debug-only,
                                     # NEVER persisted to Langfuse
  evidence_refs: list[str],
  confidence: ConfidenceDoc,
}
```

`pattern` and `example` live in Mongo; only `pattern_id`, `pattern_kind`,
and counts surface in Langfuse (§15.10).

### 10.4 `CredibilityLadderRule`, `TopicCoverageEntry`, `NormalizationEvent`

```text
CredibilityLadderRule {
  ladder_id,                         # stable slug
  applies_to_audience,               # AudienceVariantKey | "all"
  ladder: list[ProofType],           # ordered, 2..5; uses 4.2.3 enum
  fallback_rule_id,                  # rule_id to invoke when top of ladder is unsupported
  rationale,                         # <= 200 chars
  evidence_refs: list[str],
  confidence: ConfidenceDoc,
}

TopicCoverageEntry {
  topic_family,                      # RuleTopicFamily (§10.6)
  rule_count,                        # int >= 1 for mandatory families
  source,                            # "llm" | "default" | "merged"
}

NormalizationEvent {
  kind,                              # alias_mapped | enum_clamp | candidate_leakage
                                     # | conflict_suppressed | conflict_downgraded
                                     # | conflict_retained | duplicate_collapsed
                                     # | precedence_assigned | id_renormalized
  path,                              # JSON path
  from,                              # raw value (bounded 160 chars)
  to,                                # canonical value (bounded 160 chars)
  reason,                            # short string
}
```

### 10.5 Canonical `RuleTypeEnum` (owned by 4.2.6)

```
allowed_if_evidenced            # claim permitted only if candidate evidence supports it
prefer_softened_form            # claim permitted but must use conservative phrasing
omit_if_weak                    # claim must be omitted when evidence is weak
forbid_without_direct_proof     # claim is forbidden absent direct evidence
never_infer_from_job_only       # claim cannot be constructed from JD inference alone
cap_dimension_weight            # deterministic upper bound on dimension weight
require_credibility_marker      # section must include >= 1 credibility marker
require_proof_for_emphasis      # section emphasis tier requires named proof
suppress_audience_variant_signal # specific audience variant must not surface signal
```

`rule_type_enum_version` bumps on any addition; the deterministic
post-pass refuses unknown values.

### 10.6 Canonical `RuleTopicFamily` (owned by 4.2.6)

Mandatory topic families (every successful run must carry ≥ 1 rule each):

```
title_inflation
ai_claims
leadership_scope
architecture_claims
domain_expertise
stakeholder_management_claims
metrics_scale_claims
credibility_ladder_degradation
```

Optional topic families:

```
tooling_inflation
process_methodology_claims
compliance_regulatory_claims
keyword_stuffing
narrative_overreach
audience_variant_specific_softening
```

Coverage gaps for mandatory families MUST be filled from
`role_family_emphasis_rule_priors` (§9.3) with `defaults_applied[]`
populated and `status = partial` (never silent omission).

### 10.7 `AppliesToScope` and `AppliesToKindEnum`

```
AppliesToKindEnum:
  section          # value is a DocumentSectionIdEnum (4.2.2)
  proof            # value is a ProofType (4.2.3)
  dimension        # value is an ExperienceDimension (4.2.5)
  audience_variant # value is an AudienceVariantKey (4.2.4)
  global           # value is the literal string "global"
```

`applies_to` is the resolved id string drawn from the appropriate enum.
The post-pass refuses any (kind, value) pair where value is not in the
enum corresponding to kind.

### 10.8 `evidence_refs[]` format

Pinned to the same format as 4.2.3 / 4.2.4:

- `source:<source_id>` — `source_id` exists in the parent
  `presentation_contract` run's composite source list (union of research
  and JD-derived sources).
- `artifact:<dotted-path>` — rooted at
  `pre_enrichment.outputs.<stage>.<field>[...]`.

Mixed or free-form strings are rejected by the post-pass. Every rule must
carry ≥ 1 `evidence_refs[]` entry. Default rules sourced from
`role_family_emphasis_rule_priors` carry an
`artifact:role_family_emphasis_rule_priors.<topic>` ref so provenance is
explicit.

### 10.9 `debug_context`

```text
TruthConstrainedEmphasisRulesDebug {
  input_summary {
    role_family,
    seniority,
    ai_intensity,
    tone_family,
    title,
    normalized_title,
    evaluator_roles_in_scope[],
    proof_category_frequencies: dict[ProofType, int],
    research_status,
    stakeholder_surface_status,
    pain_point_status,
    peer_title_strategy,           # from cv_shape_expectations if present
    peer_proof_order[],
    peer_must_signal_proof_types[],
    peer_de_emphasize_dimensions[],
    peer_overall_weights_top3,
    peer_ai_intensity_cap,
  },
  envelopes {
    title_safety_envelope,
    ai_claim_envelope,
    leadership_claim_envelope,
    architecture_claim_envelope,
  },
  defaults_applied[],              # role-family-prior ids applied
  normalization_events[],          # full NormalizationEvent[] (capped)
  richer_output_retained[],        # richer-than-schema fields kept for §11.3
  rejected_output[],               # {path, reason}; candidate leakage etc.
  retry_events[],                  # {repair_reason, repair_attempt}
  cross_validator_diffs[],         # violated invariants before resolution
  conflict_resolution_log[],       # per-conflict {source, target, resolution}
  forbidden_claim_pattern_examples[],  # full ForbiddenClaimPattern.example
                                       # strings (bounded; debug-only)
}
```

Debug block is collection-backed only, 16 KB cap, never in snapshot.

## 11. Richer-Output Normalization

Inherits 4.2.2 §5 verbatim and restates the 4.2.6-specific nuances.

### 11.1 Alias and coercion map

- `rules` | `rule_set` → `global_rules[]` (when entries lack
  `applies_to`); else split by `applies_to_kind`.
- `mandatory_rules` → typed split: `forbid_without_direct_proof` /
  `omit_if_weak` entries land in `omit_rules[]`; others in `global_rules[]`.
- `conditional_rules` → `allowed_if_evidenced[]`.
- `softeners` | `downgrades` → `downgrade_rules[]`.
- `forbidden_patterns` | `forbidden_phrases` → `forbidden_claim_patterns[]`.
- `credibility_chain` | `proof_chain` → `credibility_ladder_rules[]`.
- `applies_to: "section:summary"` and similar string-prefixed forms →
  `{applies_to_kind: "section", applies_to: "summary"}`.
- bare `applies_to: "summary"` (string only) → enum-resolved by trying
  section enum first, then proof enum, then dimension enum, then audience
  variant; ambiguity logged and rejected.
- `rule_id` missing → deterministic regenerated from
  `(topic_family, applies_to_kind, applies_to, hash6(condition))`.

### 11.2 Strict-on-truth rejections

- Any `rule_type` outside `RuleTypeEnum` → rejected at ingress.
- Any `topic_family` outside `RuleTopicFamily` → rejected.
- Any `applies_to_kind` outside `AppliesToKindEnum` → rejected.
- Any (`applies_to_kind`, `applies_to`) pair where `applies_to` is not in
  the enum corresponding to kind → rejected.
- Any `cap_dimension_weight` rule whose `applies_to` is not in
  `ExperienceDimension` → rejected.
- Any title-related rule whose `condition`/`action` text references a
  title outside `acceptable_title_candidates` (preflight) → rejected.
- Any AI-claim rule that *authorizes* AI depth when
  `classification.ai_taxonomy.intensity ∈ {none, adjacent}` → rejected.
- Any leadership-claim rule that authorizes leadership scope claims when
  `classification.seniority ∈ {junior, mid, senior_ic}` and
  `jd_facts.team_context.direct_reports ≤ 0` → rejected.
- Any `forbidden_claim_patterns[].pattern` using regex constructs outside
  the `regex_safe` whitelist (char classes, quantifiers; no lookarounds,
  backrefs, or alternation > 4 branches) → rejected.
- Any first-person pronoun in any string field → rejected.
- Any `applies_to_kind = global` whose `applies_to ≠ "global"` → rejected.

### 11.3 Richer-output retention

Unknown-but-grounded fields (e.g. extra per-rule severity, suggested
mitigation copy, per-section narrative notes) are preserved under
`debug_context.richer_output_retained[]` as `{key, value, note}` entries
and flagged for schema-evolution review once the rate exceeds 30% over a
100-job benchmark (same rule as 4.2.2 §5.5).

### 11.4 Duplicate / conflict collapse

When the LLM emits two rules with identical
`(topic_family, applies_to_kind, applies_to, condition_canonical)`, the
normalizer collapses them into one rule whose `precedence` is the max of
the two and whose `evidence_refs[]` is the union. A
`normalization_events[]` entry `{kind: "duplicate_collapsed", ...}` is
recorded.

When two rules conflict (e.g. `allowed_if_evidenced` vs
`forbid_without_direct_proof` on the same `applies_to`), conflict
resolution follows precedence: higher `precedence` wins; on ties,
fail-closed wins (the more restrictive `rule_type` is retained). The
loser is suppressed and a `conflict_resolution_log[]` entry is recorded.

## 12. Safety / Anti-Hallucination Rules

### 12.1 Candidate-leakage detection (hard fail-closed)

- reject first-person pronouns anywhere (`I`, `my`, `we`, `our`)
- reject proper nouns that are not the hiring company's canonical name,
  canonical domain, or a canonical framework name (e.g. "Kubernetes",
  "PyTorch")
- reject tokens matching `candidate_*` or `my_*`
- reject exact numeric achievements (e.g. `40% YoY`) unless the token
  appears verbatim in the JD
- reject rule strings that reference a specific employer or
  certification body other than the hiring company

### 12.2 Authorization-inflation fail-closed rules

- no rule whose `action` authorizes title inflation past the JD title
  level-token (`VP`, `Head`, `Director`, `Principal`, `Staff`, `Lead`,
  `Senior`, `Manager`) unless 4.2.4's `acceptable_titles[]` includes the
  inflated title and `stakeholder_surface` carries an explicit
  `cv_preference_surface.title_safety_override`.
- no rule whose `action` authorizes AI depth claims when
  `classification.ai_taxonomy.intensity ∈ {none, adjacent}`. The rule set
  MUST instead include a `forbid_without_direct_proof` rule scoped to
  `applies_to_kind=section` over `ai_highlights` (when present) and
  `summary`.
- no rule whose `action` authorizes leadership scope claims when
  `classification.seniority ∈ {junior, mid, senior_ic}` and
  `jd_facts.team_context.direct_reports ≤ 0`. The rule set MUST instead
  include a `forbid_without_direct_proof` rule on
  `dimension:leadership_enablement`.
- no rule whose `action` authorizes architecture-system-design framing
  when `architecture_evidence_band = none` (per 4.2.5 preflight).
- no rule whose `action` authorizes fabricated metrics. The rule set
  MUST include a `forbid_without_direct_proof` rule on
  `proof:metric` and a `require_proof_for_emphasis` rule on
  `section:key_achievements`.
- no rule whose `action` treats inferred stakeholder preference as
  candidate strength.

### 12.3 Audience-variant boundary

- `suppress_audience_variant_signal` rules' `applies_to` must be in
  `stakeholder_surface.evaluator_coverage_target`.
- when `stakeholder_surface.status ∈ {inferred_only, no_research,
  unresolved}`, only `recruiter` and `hiring_manager` audience variants
  may be referenced; `confidence.band ≤ medium`.

### 12.4 Confidence caps

- when `research_enrichment.status ∈ {partial, unresolved}` AND
  `stakeholder_surface.status ∈ {inferred_only, no_research, unresolved}`:
  `confidence.band ≤ medium`, `confidence.score ≤ 0.69`.
- when both upstreams are `completed` but
  `pain_point_intelligence.status == unresolved`:
  `confidence.band ≤ medium`.
- when defaults applied on any mandatory `rule_topic_family`:
  `confidence.band ≤ medium`.

## 13. Cross-Subdocument Invariants (deterministic validator)

All invariants are enforced by the shared `presentation_contract`
cross-validator pass described in 4.2.2 §4.7 / 4.2.4 §13 / 4.2.5 §13.2.
Any failure that cannot be repaired or clamped fails the entire
`presentation_contract` run and falls back to role-family defaults per
umbrella §8.2.

- **I-ER1.** every `applies_to` references a valid id in the enum that
  matches its `applies_to_kind`.
- **I-ER2.** title-related rules (`topic_family = title_inflation`) are
  consistent with `cv_shape_expectations.title_strategy` AND
  `ideal_candidate_presentation_model.title_strategy` AND
  `ideal_candidate_presentation_model.acceptable_titles[]`.
- **I-ER3.** AI-related rules (`topic_family = ai_claims`) are consistent
  with `cv_shape_expectations.ai_section_policy`,
  `classification.ai_taxonomy.intensity`, and 4.2.5's
  `overall_weights.ai_ml_depth` (the rule MUST permit at least the
  weight 4.2.5 emitted, and MUST cap at the §12.4 4.2.5 AI-cap value).
- **I-ER4.** `cap_dimension_weight` rules' `applies_to` ⊆
  `ExperienceDimension`; the cap value MUST be ≥ 0 AND MUST be ≥ the
  weight 4.2.5 emitted for that dimension *unless* 4.2.5 also flagged it
  as an `overuse_risk` (in which case 4.2.5's emitted weight is clamped
  by the rule).
- **I-ER5.** `forbidden_claim_patterns[]` MUST NOT contradict
  `document_expectations.proof_order[0:2]` — no forbidden pattern may
  uniformly suppress evidence in either of the top two proof categories
  (e.g. cannot forbid all `metric` mentions when `metric` is top).
- **I-ER6.** rules MUST NOT contradict
  `ideal_candidate_presentation_model.must_signal[]` — no
  `omit_if_weak` / `forbid_without_direct_proof` rule may apply to a
  proof type that is in `must_signal[].proof_type` unless an
  `unresolved_marker` justifies it.
- **I-ER7.** rules MUST NOT contradict
  `ideal_candidate_presentation_model.should_signal[]` — no
  `omit_if_weak` rule may apply to a `should_signal[]` proof type without
  an `allowed_if_evidenced` companion.
- **I-ER8.** `de_emphasize[]` from 4.2.4 MUST be reflected in 4.2.6 — for
  every `de_emphasize[]` entry, 4.2.6 MUST emit ≥ 1 rule of type
  `prefer_softened_form` or `omit_if_weak` whose `applies_to` matches.
- **I-ER9.** every mandatory `RuleTopicFamily` (§10.6) has ≥ 1 rule.
  Coverage gaps are filled from `role_family_emphasis_rule_priors` and
  recorded in `defaults_applied[]`.
- **I-ER10.** `rule_id` values are unique within the subdocument and
  stable across runs of the same input snapshot (§10.2).
- **I-ER11.** `section_rules` keys ⊆ `cv_shape_expectations.section_order`
  ⊆ `DocumentSectionIdEnum`.
- **I-ER12.** every `Rule.confidence.band ≤ subdocument.confidence.band`
  (no rule may claim higher confidence than the artifact as a whole).
- **I-ER13.** `credibility_ladder_rules[].ladder` uses only
  `ProofType` enum values; `applies_to_audience ∈ AudienceVariantKey ∪
  {"all"}`; `fallback_rule_id` resolves to a rule in the same artifact.
- **I-ER14.** `forbidden_claim_patterns[].pattern_kind = regex_safe`
  passes the bounded-regex check (no lookarounds, no backrefs,
  alternation ≤ 4 branches).

Violation escalates to a single schema-repair retry through the parent
stage's existing `_repair_prompt` mechanism. On exhaustion, fall back to
`_default_truth_constrained_emphasis_rules` (§15.4) marked
`defaults_applied[]`. Catastrophic failure (e.g. unrepairable
candidate-leakage in defaults) marks 4.2.6 `failed_terminal` and the
parent stage falls back to role-family defaults across all four
subdocuments per umbrella §8.2.

## 14. Fail-Open / Fail-Closed Rules

### 14.1 Fail open (preferred over empty)

- `stakeholder_surface.status ∈ {inferred_only, no_research, unresolved}`
  → omit audience-variant-scoped rules; restrict to
  `{recruiter, hiring_manager}` if any; cap `confidence.band ≤ medium`;
  populate `unresolved_markers[]`.
- `pain_point_intelligence.proof_map[]` thin (< 3 entries) →
  `forbidden_claim_patterns[]` and `credibility_ladder_rules[]` default
  from role-family priors; `defaults_applied[]` populated;
  `unresolved_markers[] += ["thin_proof_map"]`.
- `research_enrichment.role_profile.status = partial` → architecture /
  domain rules default from `classification` and `jd_facts` priors;
  `unresolved_markers[] += ["partial_role_profile"]`.
- coverage gap on a mandatory `RuleTopicFamily` → fill from
  `role_family_emphasis_rule_priors`; `defaults_applied[] += [...]`;
  `status = partial`.
- schema-repair exhausted → keep LLM's first parseable output; downgrade
  `status = partial`; record `fail_open_reason = "schema_repair_exhausted"`.
- LLM terminal failure → `_default_truth_constrained_emphasis_rules`
  fallback with `status = inferred_only` and
  `fail_open_reason = "llm_terminal_failure"`.
- cross-validator soft conflict (e.g. an `omit_if_weak` rule conflicts
  with a `must_signal[]` proof type but an `unresolved_marker` justifies
  it) → suppress the offending rule; record in
  `conflict_resolution_log[]`; `status = partial`.

### 14.2 Fail closed (hard reject; drop offending field)

- candidate-specific assertion (§12.1)
- title inflation past 4.2.4 `acceptable_titles[]` (§12.2)
- AI / leadership / architecture authorization beyond evidence band (§12.2)
- fabricated-metric authorization (§12.2)
- inferred-stakeholder-preference framed as candidate strength (§12.2)
- `applies_to` outside the corresponding enum (§13 I-ER1, I-ER4, I-ER11)
- duplicate `rule_id` after one repair attempt (§13 I-ER10)
- regex outside the `regex_safe` whitelist (§13 I-ER14)
- defaults-only rule set that itself violates a hard fail-closed rule
  (catastrophic; subdocument marked `failed_terminal`, parent falls back)

### 14.3 Minimum viable artifact under fail-open (never empty)

- ≥ 1 rule per mandatory `RuleTopicFamily` (§10.6); defaulted from
  `role_family_emphasis_rule_priors` when the LLM did not produce one.
- `forbidden_claim_patterns[]` ≥ 2 entries (default seed from
  `forbidden_claim_pattern_priors`).
- `credibility_ladder_rules[]` ≥ 1 entry (default from
  `credibility_ladder_priors`).
- `topic_coverage[]` populated for every `RuleTopicFamily` (mandatory and
  optional) with `rule_count` and `source`.
- `confidence.band ≤ medium` whenever any default was applied.
- ≥ 1 `unresolved_marker` whenever `status ∈ {partial, inferred_only,
  unresolved}`.

### 14.4 Partial completion statuses

```
status in {
  "completed",
  "partial",            # fail-open path used for one or more fields
  "inferred_only",      # entire subdocument emitted from role-family priors
  "unresolved",         # minimum artifact could not be assembled meaningfully
  "failed_terminal"     # safety violation; subdocument not persisted; parent falls back
}
```

## 15. Synthesis Strategy (inside `presentation_contract`)

### 15.1 Ordering inside the parent stage

The parent stage runs, in order:

1. Parent preflight (`_role_thesis_priors`, `_evaluator_axis_summary`,
   `_proof_order_candidates`, `_ats_envelope_profile`).
2. 4.2.4 preflight extension (`_ideal_candidate_priors`).
3. 4.2.5 preflight extension (`_dimension_weight_priors`).
4. **New 4.2.6 preflight extension** (`_emphasis_rule_priors`, §9.3).
5. If `presentation_contract_merged_prompt_enabled()` → one merged LLM
   call (`P-document-ideal-shape-weights-rules@v1`, future) returning
   all four subdocuments; 4.2.6 hydrates from the
   `truth_constrained_emphasis_rules` key.
6. Else (split prompt mode, default), in sequence:
   - `P-document-expectations@v1`
   - `P-cv-shape-expectations@v1`
   - `P-ideal-candidate@v1`
   - `P-experience-dimension-weights@v1`
   - **`P-emphasis-rules@v1`** — 4.2.6, reads peer outputs (1..5 above) as
     same-run peers
7. Deterministic normalizer + validator for each subdocument.
8. Cross-subdocument validator (§13).
9. Persistence (collection-backed) + snapshot projection + Langfuse
   finalization.

### 15.2 `P-emphasis-rules@v1` prompt

Builder: `build_p_emphasis_rules` in `src/preenrich/blueprint_prompts.py`,
following the same structure as `build_p_document_expectations` (prefix
with `SHARED_CONTRACT_HEADER`, append
`_json_only_contract(PROMPT_VERSIONS["emphasis_rules"],
["truth_constrained_emphasis_rules"])`).

Inputs packed into the prompt:

```json
{
  "job_id": "...",
  "role_brief": { "normalized_title": "...", "role_family": "...",
                  "seniority": "...", "tone_family": "...",
                  "ai_intensity": "..." },
  "company_brief": { "identity_band": "...", "industry": "...",
                     "stage": "..." },
  "research_status": { "company_profile_status": "...",
                       "role_profile_status": "...",
                       "application_profile_status": "..." },
  "stakeholder_axis": [ /* evaluator_axis_summary */ ],
  "evaluator_coverage_target": [ ... ],
  "peer_document_expectations": { /* verbatim DocumentExpectationsDoc */ },
  "peer_cv_shape_expectations": { /* verbatim CvShapeExpectationsDoc */ },
  "peer_ideal_candidate_presentation_model": { /* verbatim 4.2.4 doc */ },
  "peer_experience_dimension_weights": { /* verbatim 4.2.5 doc */ },
  "pain_proof_summary": [ { "pain_id": ..., "preferred_proof_type": ...,
                            "preferred_evidence_shape": "..." }, ... ],
  "bad_proof_patterns": [ ... ],
  "preflight": {
    "role_family_emphasis_rule_priors": { ... },
    "title_safety_envelope": { ... },
    "ai_claim_envelope": { ... },
    "leadership_claim_envelope": { ... },
    "architecture_claim_envelope": { ... },
    "forbidden_claim_pattern_priors": [ ... ],
    "credibility_ladder_priors": [ ... ]
  },
  "enums": {
    "rule_type": [...],
    "topic_family": [...],
    "applies_to_kind": [...],
    "section_id": [...],            // from 4.2.2 enum
    "proof_type": [...],            // from 4.2.3 enum
    "experience_dimension": [...],  // from 4.2.5 enum
    "audience_variant_key": [...],  // from 4.2.4 enum
    "title_strategy": [...]         // from 4.2.2 enum
  }
}
```

Instruction additions (appended to `SHARED_CONTRACT_HEADER`):

- You do not know the candidate. Never reference a specific candidate,
  employer, tenure, or achievement. No first-person language.
- Produce policy, not prose. Every rule must be actionable by a later
  generator or by a deterministic enforcer.
- Use only canonical enums (provided in payload) for every enumerated
  field.
- Rules are conditional on candidate evidence state. The rule MUST say
  what to do when evidence is present versus absent; conservative
  emphasis is the default for unresolved evidence.
- `cap_dimension_weight` rules' `applies_to` MUST be in
  `experience_dimension`. The cap value MUST be ≥ the value 4.2.5
  emitted for that dimension UNLESS 4.2.5 also flagged it as an
  `overuse_risk`; in that case the cap MAY be lower.
- Title-related rules MUST be consistent with
  `peer_cv_shape_expectations.title_strategy` AND
  `peer_ideal_candidate_presentation_model.title_strategy` AND
  `acceptable_titles[]`.
- AI-related rules MUST be consistent with
  `peer_cv_shape_expectations.ai_section_policy` AND
  `ai_intensity`. When `ai_intensity ∈ {none, adjacent}`, you MUST
  emit a `forbid_without_direct_proof` rule on `proof:ai`.
- Leadership-related rules MUST honor the
  `leadership_claim_envelope`. When `direct_reports = 0` and
  `seniority ∈ {junior, mid, senior_ic}`, you MUST emit a
  `forbid_without_direct_proof` rule on
  `dimension:leadership_enablement`.
- `forbidden_claim_patterns[]` MUST NOT uniformly suppress the top two
  proof categories from `peer_document_expectations.proof_order[]`.
- For every `peer_ideal_candidate_presentation_model.de_emphasize[]`
  entry, emit ≥ 1 `prefer_softened_form` or `omit_if_weak` rule.
- Every mandatory `topic_family` MUST have ≥ 1 rule. If you cannot
  ground a topic, copy the matching prior from
  `preflight.role_family_emphasis_rule_priors` and tag it
  `topic_coverage[*].source = "default"`.
- Every rule MUST carry ≥ 1 `evidence_refs[]` entry resolvable as
  `source:<id>` or `artifact:<dotted-path>`.
- `rule_id` MUST be a stable slug. If you do not provide one, the
  normalizer will derive it deterministically from
  `(topic_family, applies_to_kind, applies_to, hash6(condition))`.
- Unresolved is a valid first-class answer for individual rules;
  populate `unresolved_markers[]` and `rationale`.
- `forbidden_claim_patterns[].pattern` MUST be either a substring or a
  bounded regex (no lookarounds, no backrefs, alternation ≤ 4
  branches).
- No CV prose. No headers. No bullets. No summaries.

### 15.3 Schema-repair retry contract

Exactly one repair retry, consistent with the parent-stage
`_repair_prompt` mechanism. Permitted repair reasons:

- `missing_evidence_ref`
- `enum_drift_rule_type` | `enum_drift_topic_family` |
  `enum_drift_applies_to_kind` | `enum_drift_applies_to`
- `applies_to_kind_value_mismatch`
- `cap_dimension_weight_unknown_dimension`
- `title_inflation_authorization`
- `ai_authorization_above_intensity`
- `leadership_authorization_above_envelope`
- `forbidden_pattern_contradicts_proof_order`
- `must_signal_contradicted`
- `duplicate_rule_id`
- `regex_outside_safe_subset`
- `mandatory_topic_coverage_missing`
- `section_rule_unknown_section_id`
- `audience_variant_out_of_scope`

Repair prompt is the same LLM call with the original prompt + the diff +
a normative sentence describing the violation + "Return valid JSON only;
do not add candidate-specific details; use only canonical enums; honor
all envelopes; preserve mandatory topic coverage." If the retry still
fails, fall back to `_default_truth_constrained_emphasis_rules`.

### 15.4 Deterministic fallback (`_default_truth_constrained_emphasis_rules`)

Implemented next to `_default_document_expectations` in
`src/preenrich/stages/presentation_contract.py`. Builds from:

- `preflight.role_family_emphasis_rule_priors` (mandatory topic-family
  rules)
- `preflight.title_safety_envelope` (title-inflation rule)
- `preflight.ai_claim_envelope` (AI-claim rule, defaulted to
  `forbid_without_direct_proof` when `ai_intensity ∈ {none, adjacent}`)
- `preflight.leadership_claim_envelope` (leadership rule, defaulted to
  `forbid_without_direct_proof` when scope evidence absent)
- `preflight.architecture_claim_envelope` (architecture rule)
- `preflight.forbidden_claim_pattern_priors`
- `preflight.credibility_ladder_priors`
- `peer_experience_dimension_weights.overuse_risks[]` → matching
  `cap_dimension_weight` rules with `precedence = 80`
- `peer_ideal_candidate_presentation_model.de_emphasize[]` → matching
  `prefer_softened_form` rules with `precedence = 60`

Fallback marks `status = inferred_only`,
`confidence.band ≤ medium`,
`defaults_applied[] = ["role_family_emphasis_rules_default"]`,
`unresolved_markers[] = ["fail_open_role_family_emphasis_rules_defaults"]`.

The fallback itself is unit-tested to satisfy every fail-closed rule in
§12. If the fallback ever fails its own validation, the subdocument is
marked `failed_terminal` and the parent stage falls back across all four
subdocuments.

## 16. Operational Catalogue

This section is explicitly **subdocument-scoped**, not stage-scoped.

### 16.1 Ownership

- **Owning stage:** `presentation_contract` (registered in
  `src/preenrich/stage_registry.py`, task type
  `preenrich.presentation_contract`, already wired).
- **Owning subdocument:** `truth_constrained_emphasis_rules` (new), slot
  inside `PresentationContractDoc`.
- **Owning model:** `TruthConstrainedEmphasisRulesDoc`, `Rule`,
  `ForbiddenClaimPattern`, `CredibilityLadderRule`,
  `TopicCoverageEntry`, `NormalizationEvent`,
  `TruthConstrainedEmphasisRulesDebug` in
  `src/preenrich/blueprint_models.py` (new).
- **Owning enums:** `RuleTypeEnum`, `RuleTopicFamily`,
  `AppliesToKindEnum` in `src/preenrich/blueprint_models.py` (new).
  Imports: `DocumentSectionIdEnum` (4.2.2), `ProofType` (4.2.3),
  `ExperienceDimension` (4.2.5), `AudienceVariantKey` (4.2.4),
  `TitleStrategyEnum` (4.2.2).
- **Owning prompt:** `P-emphasis-rules@v1` registered in
  `PROMPT_VERSIONS["emphasis_rules"]` and built by
  `build_p_emphasis_rules`.
- **Owning normalizer:**
  `normalize_truth_constrained_emphasis_rules_payload` in
  `blueprint_models.py`.
- **Owning validator + fallback:**
  `_validate_truth_constrained_emphasis_rules`,
  `_default_truth_constrained_emphasis_rules`,
  `_emphasis_rule_priors` in
  `src/preenrich/stages/presentation_contract.py`.

### 16.2 Prerequisite artifacts

Before the parent `presentation_contract` stage may synthesize this
subdocument, the run must have:

- `pre_enrichment.outputs.jd_facts` with status ∈ {completed, partial}
- `pre_enrichment.outputs.classification` completed
- `pre_enrichment.outputs.research_enrichment` with status ∈ {completed,
  partial, unresolved}
- `pre_enrichment.outputs.stakeholder_surface` with status ∈ {completed,
  inferred_only, no_research, unresolved}
- `pre_enrichment.outputs.pain_point_intelligence` with status ∈
  {completed, partial, unresolved}

Hard-fail of any prerequisite is surfaced by the parent stage, not by
4.2.6.

### 16.3 Persistence map

| What                                          | Location                                                                                                     |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Full `PresentationContractDoc` including 4.2.6 | `presentation_contract` collection, unique filter `(job_id, input_snapshot_id)`                              |
| Stage output ref                              | `level-2.pre_enrichment.outputs.presentation_contract.truth_constrained_emphasis_rules`                       |
| Stage state                                   | `level-2.pre_enrichment.stage_states.presentation_contract`                                                  |
| Compact snapshot projection                   | `level-2.pre_enrichment.job_blueprint_snapshot.presentation_contract_compact.emphasis_rules`                  |
| Work item                                     | `work_items` collection, `task_type="preenrich.presentation_contract"` (shared with peers)                    |
| Run audit                                     | `preenrich_stage_runs` (shared with peers; one row per parent stage run; carries 4.2.6 substage metadata)    |
| Job aggregate                                 | `preenrich_job_runs.stage_status_map.presentation_contract`                                                  |
| Debug                                         | inside the subdocument under `truth_constrained_emphasis_rules.debug_context`, size-capped at 16 KB          |
| Alerts                                        | `preenrich_alerts` (parent-stage deadletter only; 4.2.6 never alerts independently)                          |

There is **no** separate `truth_constrained_emphasis_rules` collection,
**no** separate `work_items` row, **no** separate `preenrich_stage_runs`
row, and **no** separate `preenrich_alerts` row.

### 16.4 Compact snapshot projection

Projected by `blueprint_assembly` into
`JobBlueprintSnapshot.presentation_contract_compact.emphasis_rules`:

```json
{
  "status": "...",
  "confidence_band": "...",
  "rule_type_enum_version": "v1",
  "applies_to_enum_version": "v1",
  "global_rules_count": 4,
  "section_rule_count": 7,
  "section_rule_coverage_section_ids": ["summary", "key_achievements",
                                        "ai_highlights", "experience"],
  "allowed_if_evidenced_count": 3,
  "downgrade_rules_count": 2,
  "omit_rules_count": 2,
  "forbidden_claim_patterns_count": 6,
  "credibility_ladder_rules_count": 2,
  "topic_coverage": {
    "title_inflation": 1,
    "ai_claims": 2,
    "leadership_scope": 1,
    "architecture_claims": 1,
    "domain_expertise": 1,
    "stakeholder_management_claims": 1,
    "metrics_scale_claims": 2,
    "credibility_ladder_degradation": 1
  },
  "title_strategy_conflict_count": 0,
  "ai_section_policy_conflict_count": 0,
  "dimension_weight_conflict_count": 0,
  "must_signal_contradiction_count": 0,
  "defaults_applied_count": 1,
  "normalization_events_count": 2,
  "unresolved_markers_count": 0,
  "trace_ref": { "trace_id": "...", "trace_url": "..." }
}
```

No rule bodies, no `forbidden_claim_patterns[].example` strings, no
rationale, no debug block.

### 16.5 Subdocument status semantics inside parent

Parent `PresentationContractDoc.status` resolution uses the union of its
subdocument statuses (consistent with 4.2.4 §16.5):

- any `failed_terminal` → parent `failed_terminal`
- any `partial` or `inferred_only` → parent `partial`
- any `unresolved` (no `partial`/`inferred_only`) → parent `unresolved`
- all `completed` → parent `completed`

A `failed_terminal` in 4.2.6 causes the parent stage to fall back to
role-family defaults across ALL subdocuments (umbrella §8.2); it does
not deadletter the job, because `job_fail_policy="fail_open"` at the
stage level.

### 16.6 Retry / repair semantics at subdocument vs stage level

- Parent stage `max_attempts = 3` (shared with all four subdocuments).
- 4.2.6 adds a single schema-repair retry via the same `_repair_prompt`
  mechanism as 4.2.2 / 4.2.3 / 4.2.4 / 4.2.5. Repair attempts ≥ 2 are not
  permitted.
- On repair exhaustion: fall back to
  `_default_truth_constrained_emphasis_rules` with
  `status = inferred_only` and `defaults_applied[]` populated.
- On candidate-leakage trigger: offending rule omitted; `status =
  partial`; `normalization_events[]` records the rejection.
- On cross-validator invariant violation that cannot be repaired: parent
  stage re-runs all four subdocuments with role-family defaults; 4.2.6 is
  marked `failed_terminal`.

### 16.7 Cache behavior

4.2.6 does **not** own a cache key. Inherits the parent
`presentation_contract_input_hash`, which includes
`PROMPT_VERSIONS["emphasis_rules"]`, `RULE_TYPE_ENUM_VERSION`, and
`APPLIES_TO_ENUM_VERSION`. Bumping any of these invalidates cached
parent artifacts. No standalone `emphasis_rules_cache` collection.

### 16.8 Heartbeat and operator expectations

- Parent stage heartbeat every `PREENRICH_STAGE_HEARTBEAT_SECONDS`
  (default 60 s) via `StageWorker._heartbeat_loop`.
- The 4.2.6 LLM call must not hold CPU > 30 s between yield points
  (preflight, prompt build, LLM call, post-pass, cross-validator). The
  worker heartbeat renews the lease.
- Launcher-side operator heartbeat (§17.8) every 15–30 s during VPS
  runs, with `last_substep` reflecting `emphasis_rules` when the
  subdocument is being synthesized.
- Silence > 90 s is a stuck-run flag.

### 16.9 Feature flags affecting 4.2.6

- `presentation_contract_enabled()` — master flag for the parent stage;
  off ⇒ 4.2.6 is not synthesized.
- `presentation_contract_emphasis_rules_enabled()` — gates the LLM
  synthesis path for 4.2.6. When off, the parent stage always uses
  `_default_truth_constrained_emphasis_rules`. Default: off at ship;
  default-on after SC gate.
- `presentation_contract_merged_prompt_enabled()` — when on, 4.2.6
  hydrates from the merged prompt's
  `truth_constrained_emphasis_rules` key. When off (default), the split
  `P-emphasis-rules@v1` path is used.
- `presentation_contract_compat_projection_enabled()` — keeps legacy
  downstream consumers working during rollout; does not affect 4.2.6
  synthesis.

### 16.10 Downstream consumers of `truth_constrained_emphasis_rules`

- `presentation_contract` cross-validator (intra-stage; enforces I-ER1
  through I-ER14)
- `experience_dimension_weights` (4.2.5; honors
  `cap_dimension_weight` rules at clamp time)
- `blueprint_assembly.snapshot` (compact projection, §16.4)
- 4.3.x candidate-aware CV generation (consumes every rule type as
  enforceable policy; the generator must cite the `rule_id` it complied
  with for each emphasis decision)
- 4.3.x repair / verifier loops (re-run rules against candidate-aware
  output)
- reviewer UI ("what this CV must not claim" panel)
- optional outreach guidance refresh (consumes
  `forbidden_claim_patterns[]` to gate generated outreach copy)

### 16.11 Rollback strategy

- toggle `presentation_contract_emphasis_rules_enabled()` to `false`:
  parent stage synthesizes the subdocument deterministically from
  `_default_truth_constrained_emphasis_rules`; no data loss.
- toggle `presentation_contract_enabled()` to `false`: downstream
  consumers fall back to legacy `cv_guidelines`; existing
  `presentation_contract` collection documents remain inert.
- no schema migration on rollback.

### 16.12 Why no separate cache keys / trace refs beyond the parent

A separate cache key would let 4.2.6 drift from 4.2.2 / 4.2.4 / 4.2.5
when an upstream artifact changes — and cross-subdocument invariants
are precisely what 4.2.6 exists to enforce. A separate trace ref would
fragment the one-click-from-Mongo-to-Langfuse operator path. Both are
actively undesirable.

## 17. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This plan validates 4.2.6 through the real
`presentation_contract` stage on VPS. It does **NOT** invent a
standalone `preenrich.truth_constrained_emphasis_rules` stage.

### 17.1 Local prerequisite tests before touching VPS

- `pytest tests/unit/preenrich -n auto -k "emphasis_rules"` clean.
- `pytest tests/unit/preenrich/test_presentation_contract_stage.py -x`
  clean (parent stage contract, including 4.2.6 wiring).
- `python -u -m scripts.preenrich_dry_run --stage presentation_contract
  --job <level2_id> --mock-llm` clean and the dry-run produces the 4.2.6
  subdocument.
- compact snapshot projection test green (§18.10).
- Langfuse sanitizer test green (no full rule bodies, no forbidden
  pattern examples in payload).

### 17.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path.
- `grep -n "truth_constrained_emphasis_rules"
  /root/scout-cron/src/preenrich/blueprint_models.py` to confirm
  `TruthConstrainedEmphasisRulesDoc` and supporting models present.
- `grep -n "emphasis_rules"
  /root/scout-cron/src/preenrich/stages/presentation_contract.py` to
  confirm the synthesis path, the validator, and the fallback are wired.
- `grep -n "emphasis_rules"
  /root/scout-cron/src/preenrich/blueprint_prompts.py` to confirm
  `build_p_emphasis_rules` and `PROMPT_VERSIONS["emphasis_rules"]`.
- `grep -n "presentation_contract_emphasis_rules_enabled"
  /root/scout-cron/src/preenrich/blueprint_config.py` to confirm the
  flag exists and matches the intended rollout posture.
- `.venv` resolves the deployed Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`.
- deployment is file-synced, not git-pulled — read sync markers; do not
  `git status`.

### 17.3 Target job selection

- pick a real `level-2` job with `pre_enrichment.outputs` for all of
  `jd_facts`, `classification`, `research_enrichment`,
  `stakeholder_surface`, `pain_point_intelligence` at `status ∈
  {completed, partial}` as appropriate.
- prefer a mid-seniority IC or EM role with resolved company identity
  (`research_enrichment.status = completed`) and a real stakeholder
  (`stakeholder_surface.status = completed`) for the main smoke.
- record `_id`, `jd_checksum`, `input_snapshot_id`,
  `research_input_hash`, `pain_input_hash`.
- pick a second job with `stakeholder_surface.status = inferred_only` or
  `research_enrichment.status = partial` to exercise fail-open.
- pick a third job with
  `classification.ai_taxonomy.intensity ∈ {adjacent, none}` and JD
  keyword-inflated AI language to exercise the AI-claim envelope and
  the forbidden-AI rule.
- pick a fourth job with `classification.seniority ∈ {junior, mid,
  senior_ic}` and `jd_facts.team_context.direct_reports = 0` plus JD
  leadership language to exercise the leadership envelope.

### 17.4 Upstream artifact recovery

If `stage_states` show stale entries:

1. verify `pre_enrichment.outputs.{jd_facts, classification,
   research_enrichment, stakeholder_surface, pain_point_intelligence}`
   exist.
2. recompute the current `input_snapshot_id` deterministically:
   `/root/scout-cron/.venv/bin/python -u
   scripts/recompute_snapshot_id.py --job <_id>`.
3. only if necessary, re-enqueue prerequisites via
   `scripts/enqueue_stage.py` — never touch `work_items` directly.

### 17.5 Single-stage run path (fast path)

Preferred. A wrapper script
`/tmp/run_presentation_contract_<job>.py`:

- loads `.env` in Python with explicit path:
  `from dotenv import load_dotenv;
   load_dotenv("/root/scout-cron/.env")`.
- reads `MONGODB_URI`.
- builds `StageContext` via `build_stage_context_for_job`.
- forces `presentation_contract_emphasis_rules_enabled()=True` via env
  override for the scope of the run.
- runs `PresentationContractStage().run(ctx)` directly.
- prints a heartbeat every 15 s during the LLM call chain showing wall
  clock, elapsed, last substep
  (`preflight | document_expectations | cv_shape_expectations |
   ideal_candidate | dimension_weights | emphasis_rules | cross_validate
   | persist`), Codex PID, Codex stdout/stderr tail.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_presentation_contract_<job>.py \
  > /tmp/presentation_contract_<job>.log 2>&1 &
```

### 17.6 Full-chain path (fallback)

Only when `StageContext` construction drifts:

- enqueue `work_items` for the full prerequisite chain.
- start `preenrich_worker_runner.py` with
  `PREENRICH_STAGE_ALLOWLIST="presentation_contract"`.
- same `.venv` / `python -u` / Python-side `.env` / `MONGODB_URI`
  discipline.
- same operator heartbeat.

### 17.7 Required launcher behavior

- `.venv` activated (`source /root/scout-cron/.venv/bin/activate` OR
  absolute path to `.venv/bin/python`).
- `python -u` unbuffered.
- `.env` loaded from Python, not `source .env`.
- `MONGODB_URI` present.
- Codex subprocess cwd defaults to an isolated
  `/tmp/codex-work-presentation-contract-<job>/` unless repo context is
  explicitly required (debug only,
  `PREENRICH_CODEX_WORKDIR_PRESENTATION_CONTRACT=...`, never default).
- inner Codex PID and first 128 chars of stdout / stderr logged on every
  heartbeat.

### 17.8 Heartbeat requirements

- launcher operator heartbeat every 15–30 s, showing: `last_substep`,
  elapsed since last substep change, Codex PID if any, last stage span
  duration.
- lease heartbeat every 60 s by the parent worker
  (`PREENRICH_STAGE_HEARTBEAT_SECONDS`).
- silence > 90 s between heartbeats is a stuck-run flag.

### 17.9 Expected Mongo writes

On success:

- `presentation_contract` collection: new doc keyed by
  `(job_id, input_snapshot_id)` containing a populated
  `truth_constrained_emphasis_rules` slot.
- `level-2.pre_enrichment.outputs.presentation_contract.truth_constrained_emphasis_rules`
  populated (projection).
- `level-2.pre_enrichment.stage_states.presentation_contract.status =
  completed`, `trace_id`, `trace_url` set.
- `preenrich_stage_runs`: one row for the parent stage with
  `status=completed`, `trace_id`, `trace_url`, `provider_used`,
  `model_used`, `prompt_version` (parent), `tokens_input`,
  `tokens_output`, `cost_usd`. Substage metadata records 4.2.6 substage
  summary (`status`, `confidence_band`, `global_rules_count`,
  `forbidden_claim_patterns_count`, `defaults_applied_count`).
- `preenrich_job_runs`: aggregate updated;
  `stage_status_map.presentation_contract = completed`.
- `work_items`: this row `status=completed`.
- `JobBlueprintSnapshot.presentation_contract_compact.emphasis_rules`:
  populated per §16.4.

### 17.10 Expected Langfuse traces

In the same trace (`scout.preenrich.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- `scout.preenrich.presentation_contract` stage span with full peer
  metadata.
- `scout.preenrich.presentation_contract.preflight`.
- `scout.preenrich.presentation_contract.document_expectations`.
- `scout.preenrich.presentation_contract.cv_shape_expectations`.
- `scout.preenrich.presentation_contract.ideal_candidate`.
- `scout.preenrich.presentation_contract.dimension_weights`.
- **`scout.preenrich.presentation_contract.emphasis_rules` substage span
  with full §15.4 metadata.**
- optional 4.2.6 children:
  `emphasis_rules.prompt_build`,
  `emphasis_rules.llm_call.primary` (+ `.fallback` if it fired),
  `emphasis_rules.post_pass`,
  `emphasis_rules.schema_repair` (iff repair fired),
  `emphasis_rules.rule_conflict_resolution` (iff the normalizer
  collapsed conflicts),
  `emphasis_rules.cross_validate`.
- `scout.preenrich.presentation_contract.consistency.emphasis_rules`
  events (one per cross-validator suppression / downgrade / retain).
- canonical lifecycle events (`claim`, `enqueue_next`).
- one `cache.hit` or `cache.miss` event at the parent level.

### 17.11 Expected `preenrich_stage_runs` / `preenrich_job_runs`

- `stage_runs` row (parent) has `trace_id`, `trace_url`, and
  `fail_open_reason` iff non-completed at the parent level.
- `job_runs` aggregate has updated
  `stage_status_map.presentation_contract`.
- Substage metadata on the `stage_runs` row records the 4.2.6 subspan
  summary (status, confidence band, key counts) without full bodies.

### 17.12 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/presentation_contract_<job>.log`.
- `ps -p <codex_pid> -o pid,etime,stat,cmd`.
- check `/tmp/codex-work-presentation-contract-<job>/stdout.log` touch
  ctime.
- inspect Mongo stage state:
  `level-2.pre_enrichment.stage_states.presentation_contract.lease_expires_at`.
- if lease is expiring and no progress, kill the launcher; do not restart
  until the prior PID is confirmed gone. Silence is not progress.

### 17.13 Acceptance criteria

- log ends with
  `PRESENTATION_CONTRACT_RUN_OK job=<id> status=<status>
  emphasis_rules=<status> trace=<url>`.
- Mongo writes match §17.9.
- Langfuse trace matches §17.10, including the `emphasis_rules` substage
  metadata (§15.4).
- `TruthConstrainedEmphasisRulesDoc` validates for the persisted doc.
- spot-check:
  - mandatory `RuleTopicFamily` coverage = 100% (§10.6);
  - 0 rules authorize title inflation past 4.2.4 `acceptable_titles[]`;
  - 0 rules authorize AI depth claims when intensity ∈ {none, adjacent};
  - 0 rules authorize leadership scope claims when seniority and
    `direct_reports` envelope forbid them;
  - 0 `cap_dimension_weight` rules reference an unknown dimension;
  - 100% of rules carry resolvable `evidence_refs[]`;
  - `forbidden_claim_patterns[]` ≥ 2 entries; no pattern uniformly
    suppresses the top two `proof_order[]` categories;
  - `credibility_ladder_rules[]` ≥ 1 entry;
  - `rule_id` values are unique and re-derive identically on re-run
    against the same input snapshot;
  - `title_strategy_conflict_count = 0`,
    `ai_section_policy_conflict_count = 0`,
    `dimension_weight_conflict_count = 0`,
    `must_signal_contradiction_count = 0`.
- fail-open run (research-thin, stakeholder-thin, AI-inflated) returns
  `status=partial` or `inferred_only` with `defaults_applied[]`
  populated and an explicit `fail_open_reason`; parent stage does not
  deadletter.

### 17.14 Artifact / log / report capture

Create `reports/presentation-contract/<job_id>/emphasis_rules/`
containing:

- `run.log` — full stdout/stderr.
- `subdocument.json` — the emitted
  `TruthConstrainedEmphasisRulesDoc`.
- `parent_stage_output.json` — the full `PresentationContractDoc`.
- `trace_url.txt` — Langfuse URL.
- `stage_runs_row.json` — `preenrich_stage_runs` row for the parent
  stage.
- `mongo_writes.md` — human summary of §17.9 checks.
- `acceptance.md` — pass/fail list for §17.13.

## 15.5 Langfuse Tracing Contract (continued — see §15)

> NOTE: tracing detail lives in §15.4 below. The tracing-contract section
> is numbered §15 in this plan to keep peer parity with 4.2.4 §17 / 4.2.5
> §17. Both numbering conventions are accepted; Langfuse readers should
> treat §15.4 as the source of truth for stage-specific metadata.

## 18. Tests and Evals

Tests live under `tests/unit/preenrich/` mirroring 4.2.4 / 4.2.5
conventions. Follows AGENTS.md test discipline: `.venv`, `python -u`,
explicit `.env` loading, mocked LLM, no MongoDB, no integration tests.

### 18.1 Schema / unit tests

`tests/unit/preenrich/test_emphasis_rules_schema.py`:

- `TruthConstrainedEmphasisRulesDoc` accepts canonical output (fixture
  based on §10.1).
- `extra="forbid"` rejects unknown top-level keys.
- enum rejection for each of: `RuleTypeEnum`, `RuleTopicFamily`,
  `AppliesToKindEnum`, `TitleStrategyEnum`, imported
  `DocumentSectionIdEnum` / `ProofType` / `ExperienceDimension` /
  `AudienceVariantKey`.
- `Rule.applies_to_kind` × `Rule.applies_to` value-mismatch rejection
  (e.g. kind=section with applies_to="ai_ml_depth").
- `cap_dimension_weight` rule with `applies_to_kind != dimension`
  rejected.
- `Rule.precedence` outside `[0, 100]` rejected.
- `forbidden_claim_patterns[].pattern` outside `regex_safe` rejected.
- `Rule.confidence.band > subdocument.confidence.band` rejected.
- `rule_id` non-unique rejected.

### 18.2 Normalizer tests

`tests/unit/preenrich/test_emphasis_rules_ingress.py`:

- alias map (`rules` → `global_rules`,
  `mandatory_rules` → typed split,
  `softeners` → `downgrade_rules`,
  `forbidden_phrases` → `forbidden_claim_patterns`,
  `proof_chain` → `credibility_ladder_rules`) mapped correctly.
- `applies_to: "section:summary"` string-prefix coerced to
  `{applies_to_kind: "section", applies_to: "summary"}`.
- bare-string `applies_to` ambiguity logged and rejected.
- duplicate-rule collapse (same topic+kind+applies_to+condition) merges
  with max precedence and union of `evidence_refs[]`; logs
  `normalization_events[]`.
- conflict resolution by precedence (`allowed_if_evidenced` precedence=20
  vs `forbid_without_direct_proof` precedence=80 on same `applies_to` →
  forbid wins; loser logged).
- on precedence tie, fail-closed wins (more restrictive rule_type).
- `rule_id` derivation deterministic across run order.
- candidate-leakage detector catches first-person, candidate company
  proper noun, candidate tenure tokens, exact numeric achievement not
  in JD.
- richer-output retention (extra per-rule severity, suggested mitigation
  copy) goes to `debug_context.richer_output_retained[]`.

### 18.3 Invariant tests (cross-subdocument)

`tests/unit/preenrich/test_emphasis_rules_invariants.py`:

- I-ER1 (`applies_to` ⊆ kind enum): triggers repair.
- I-ER2 (title-strategy match across 4.2.2 + 4.2.4 + 4.2.6): violation
  triggers repair → defaults.
- I-ER3 (AI-claim consistency with intensity + 4.2.5 ai_ml_depth): per
  intensity value — `core / significant / adjacent / none / unknown`.
- I-ER4 (`cap_dimension_weight` honors 4.2.5; cap ≥ 4.2.5 weight unless
  flagged as overuse): both passing and conflicting cases.
- I-ER5 (forbidden_claim_patterns vs proof_order top-two): violation
  rejected.
- I-ER6 (`omit_if_weak` over `must_signal[]` proof type without
  `unresolved_marker`): rejected.
- I-ER7 (`omit_if_weak` over `should_signal[]` without
  `allowed_if_evidenced` companion): rejected.
- I-ER8 (every `de_emphasize[]` reflected in 4.2.6 by ≥ 1 rule): missing
  reflection triggers default fill.
- I-ER9 (mandatory topic-family coverage): missing topics auto-filled
  from priors with `defaults_applied[]`.
- I-ER10 (`rule_id` unique + stable across runs): negative test for
  collision; positive test for stability across re-run.
- I-ER11 (`section_rules` keys ⊆ `cv_shape_expectations.section_order`):
  rejected; offending section dropped.
- I-ER12 (rule confidence ≤ subdoc confidence): rule clamped.
- I-ER13 (credibility_ladder enum + audience_variant + fallback
  resolution): negative test for orphan fallback.
- I-ER14 (regex_safe whitelist): negative test for `(?=...)`,
  backreferences, alternation > 4 branches.

Each invariant has at least one positive and one negative test.

### 18.4 Title-inflation prevention tests

- JD title "Lead Engineer" + 4.2.4 `acceptable_titles=["Senior
  Engineer", "Lead Engineer"]` → no rule may authorize "Principal" or
  "VP".
- 4.2.4 `acceptable_titles=["Staff Engineer"]` with stakeholder
  override → rule MAY authorize "Staff" framing.
- title rule with `action` text containing "VP" when JD title is
  "Senior" → rejected.

### 18.5 AI-claim gating tests

- `ai_intensity = none` + JD keyword "AI / ML" → rule set MUST include
  `forbid_without_direct_proof` on `proof:ai`; any rule authorizing AI
  depth → rejected; covers `ai_section_policy = discouraged`.
- `ai_intensity = adjacent` → rule set MUST include
  `omit_if_weak` on `dimension:ai_ml_depth`.
- `ai_intensity = significant / core` + JD evidence → rule set MUST
  include `allowed_if_evidenced` on `proof:ai` with credibility-marker
  requirement.

### 18.6 Leadership-scope gating tests

- `seniority = mid` + `direct_reports = 0` → rule set MUST include
  `forbid_without_direct_proof` on
  `dimension:leadership_enablement`.
- `seniority = manager` + `direct_reports >= 1` → rule set MAY include
  `allowed_if_evidenced` on `dimension:leadership_enablement` with
  named-team-ownership credibility marker.
- `seniority = director_plus` + `team_context.scope_band = high` →
  rule set MUST include `require_credibility_marker` on
  `section:summary`.

### 18.7 Metric / scale anti-fabrication tests

- rule set MUST include `forbid_without_direct_proof` on `proof:metric`.
- rule set MUST include `require_proof_for_emphasis` on
  `section:key_achievements`.
- LLM-emitted rule with `action` text "use estimated 30% improvement" →
  rejected (numeric not in JD).
- `forbidden_claim_patterns[]` MUST include patterns for "industry
  leader", "best in class", "10x", "transformed" without scope.

### 18.8 Partial-research fail-open tests

- `research_enrichment.status = partial` → architecture / domain rules
  default from priors; `defaults_applied[]` populated;
  `unresolved_markers[] += ["partial_role_profile"]`;
  `status = partial`.
- `stakeholder_surface.status = no_research` → audience-variant-scoped
  rules limited to recruiter + hiring_manager;
  `confidence.band ≤ medium`.
- `pain_point_intelligence.proof_map[]` empty →
  `forbidden_claim_patterns[]` and `credibility_ladder_rules[]` from
  role-family priors; `status = partial` or `inferred_only`.

### 18.9 Trace emission tests

Using a `FakeTracer`:

- `scout.preenrich.presentation_contract.emphasis_rules` span emitted
  exactly once per parent run with required §15.4 metadata keys.
- `emphasis_rules.schema_repair` span emitted iff repair fired.
- `emphasis_rules.rule_conflict_resolution` span emitted iff the
  normalizer collapsed conflicts.
- `consistency.emphasis_rules` event emitted when the cross-validator
  suppresses / downgrades / retains; metadata includes `conflict_source`,
  `rule_id`, `resolution`.
- forbidden keys (full rule bodies, full
  `forbidden_claim_patterns[].example`, raw evaluator-facing
  justification) do not appear in any span payload (grep assertion on
  serialized payload).

### 18.10 Snapshot projection tests

- compact snapshot contains all §16.4 keys and no full bodies.
- snapshot `trace_ref` matches the parent stage's `trace_id` /
  `trace_url`.
- `topic_coverage{}` map is populated for every mandatory family.
- conflict counts (`title_strategy_conflict_count`,
  `ai_section_policy_conflict_count`,
  `dimension_weight_conflict_count`,
  `must_signal_contradiction_count`) are integers, default zero.

### 18.11 Same-run `presentation_contract` compatibility tests

- happy path: all upstreams completed → parent stage emits all four
  subdocuments with `status = completed` and all invariants pass.
- 4.2.6 terminal subdocument failure (catastrophic fallback failure) →
  parent stage falls back all four subdocuments to role-family defaults;
  `PresentationContractDoc.status = partial`.
- merged-prompt mode: parse-time split hydrates the 4.2.6 subdocument
  correctly; span `emphasis_rules` is still emitted per §15.1.
- conflict propagation: a `cap_dimension_weight` rule with cap = 12 on
  `ai_ml_depth` clamps a 4.2.5-emitted weight of 18; 4.2.5 records
  `normalization_events[].kind = "cap_clamped"` referencing the
  4.2.6 `rule_id`.

### 18.12 Regression corpus

- 30 curated `level-2` jobs under
  `tests/data/emphasis_rules/corpus/` (10 IC, 10 EM/Director,
  10 Head/VP; mixed ATS vendor; mixed research completeness; mixed
  ai_intensity).
- golden outputs under `tests/data/emphasis_rules/golden/` with
  tolerance for ordering and rule-string Jaccard ≥ 0.9 on `condition`
  and `action`; `rule_id` exact match (stability check).
- CI mode: mocked LLM returning recorded response; diff
  non-deterministic fields separately.

### 18.13 Reviewer rubric (evals)

Scored per job, recorded under `reports/emphasis_rules_eval/`:

- **rule usefulness (1–5):** 5 = "every rule meaningfully reduces a
  plausible hallucination"; 1 = "boilerplate".
- **anti-hallucination strength (1–5):** 5 = "no plausible reviewer
  could find an inflation path the rules miss"; 1 = "rules ignore
  obvious risks".
- **specificity (1–5):** 5 = "rule conditions and actions are concrete
  enough to drive deterministic enforcement"; 1 = "vague guidance".
- **internal consistency (1–5):** 5 = "no contradictions with 4.2.2 /
  4.2.4 / 4.2.5"; 1 = "multiple visible contradictions".
- **coverage (1–5):** 5 = "all mandatory topic families covered with
  evidence"; 1 = "multiple gaps filled by defaults".
- **fail-open posture (1–5):** 5 = "fail-open path produces a usable
  rule set"; 1 = "fail-open returns near-empty".
- **JD-only graceful degradation:** for research-thin jobs, median rule
  usefulness ≥ 3.5 with `fail_open_reason` populated.

### 18.14 Live smoke tests

- `scripts/smoke_emphasis_rules_subdocument.py` — loads `.env` from
  Python, fetches one job by `_id`, runs the parent
  `PresentationContractStage` locally against live Codex/LLM with
  `presentation_contract_emphasis_rules_enabled()=true`, validates the
  4.2.6 subdocument, prints heartbeat every 15 s with `last_substep` and
  Codex PID.

## 19. Rollout, Feature Flags, Migration

### 19.1 Rollout order

1. Ship `TruthConstrainedEmphasisRulesDoc`, the normalizer, the prompt
   builder, the fallback, the cross-validator extensions, and the
   snapshot projection behind
   `presentation_contract_emphasis_rules_enabled() = false`.
   Deterministic fallback synthesizes the subdocument so downstream
   consumers can rely on presence.
2. Unit + invariant + normalizer + snapshot tests green
   (§18.1–18.11).
3. Flip the flag on for a curated 30-job corpus in staging; collect
   eval metrics (§18.13). Gate default-on on SC1–SC9.
4. Default-on in production behind
   `presentation_contract_emphasis_rules_enabled() = true`; keep
   `presentation_contract_compat_projection_enabled()` on so legacy
   downstream consumers are unaffected during the rollout window.
5. Flip `presentation_contract_compat_projection_enabled()` off only
   after 4.3.x downstream consumers have migrated to read 4.2.6 as the
   source of truth for emphasis policy.

### 19.2 Migration path

- no backfill of historical jobs at ship; the subdocument fills lazily
  on the next `presentation_contract` run for each job.
- jobs without `truth_constrained_emphasis_rules` continue to read from
  legacy `cv_guidelines` via compat projection until 4.3.x migrates.
- `blueprint_assembly` always reads
  `pre_enrichment.outputs.presentation_contract.truth_constrained_emphasis_rules`
  first; falls back to legacy synthesis only when the slot is absent.

### 19.3 Rollback

- toggle `presentation_contract_emphasis_rules_enabled() = false`:
  deterministic fallback takes over immediately; no data loss.
- toggle `presentation_contract_enabled() = false`: downstream reverts
  to `cv_guidelines`; existing `presentation_contract` collection
  documents remain inert.
- no schema migration on rollback.

### 19.4 Production readiness checklist

- [ ] `TruthConstrainedEmphasisRulesDoc`, `Rule`,
      `ForbiddenClaimPattern`, `CredibilityLadderRule`,
      `TopicCoverageEntry`, `NormalizationEvent`,
      `TruthConstrainedEmphasisRulesDebug` in
      `blueprint_models.py` with unit tests
- [ ] `RuleTypeEnum`, `RuleTopicFamily`, `AppliesToKindEnum` in
      `blueprint_models.py`; imports for
      `DocumentSectionIdEnum` / `ProofType` / `ExperienceDimension` /
      `AudienceVariantKey` / `TitleStrategyEnum`
- [ ] `normalize_truth_constrained_emphasis_rules_payload` at module
      scope + tests (alias map, kind+value coercion, conflict resolution,
      duplicate collapse, leakage detection)
- [ ] `build_p_emphasis_rules` +
      `PROMPT_VERSIONS["emphasis_rules"] = "P-emphasis-rules@v1"` +
      `RULE_TYPE_ENUM_VERSION` + `APPLIES_TO_ENUM_VERSION`
- [ ] `_emphasis_rule_priors`,
      `_default_truth_constrained_emphasis_rules`,
      `_validate_truth_constrained_emphasis_rules` in
      `src/preenrich/stages/presentation_contract.py`
- [ ] `PresentationContractStage.run` wires the split and merged paths;
      `PresentationContractDoc` carries the new slot
- [ ] cross-validator extensions enforce I-ER1–I-ER14 (shared with 4.2.2
      / 4.2.4 / 4.2.5)
- [ ] compact snapshot projection in
      `src/preenrich/stages/blueprint_assembly.py`
      (`presentation_contract_compact.emphasis_rules`)
- [ ] debug_context persisted, snapshot-excluded, size-capped at 16 KB
- [ ] Langfuse substage emission via
      `ctx.tracer.start_substage_span(..., "emphasis_rules", ...)` with
      §15.4 metadata
- [ ] eval directory scaffolded under `evals/emphasis_rules_4_2_6/`
- [ ] VPS smoke script `scripts/smoke_emphasis_rules_subdocument.py`
- [ ] feature flag `presentation_contract_emphasis_rules_enabled()` in
      `src/preenrich/blueprint_config.py`
- [ ] docs updated: `architecture.md`, `missing.md`, optional decision
      doc under `docs/current/decisions/`

## 20. Open Questions

- **Q1.** Should `cap_dimension_weight` rules carry an explicit numeric
  cap or only a category (`hard_cap | soft_cap | informational`)?
  Recommend: keep numeric, because 4.2.5 needs the value to clamp.
- **Q2.** Should `Rule.precedence` be auto-assigned from `rule_type`
  (e.g. `forbid_without_direct_proof = 80`,
  `prefer_softened_form = 50`, `allowed_if_evidenced = 20`) and rejected
  when the LLM diverges? Recommend: auto-assign as default;
  `normalization_events[]` records when LLM-supplied diverged.
- **Q3.** Should `forbidden_claim_patterns[]` support categorized
  severities (`hard | soft | warn`) alongside `pattern_kind`?
  Recommend: defer; one severity (hard) is enough at ship.
- **Q4.** Should `audience_variants` be allowed as a `applies_to_kind`
  for arbitrary rules, or only for `suppress_audience_variant_signal`?
  Recommend: only for the suppress rule type at ship; revisit after a
  100-job bench.
- **Q5.** Should 4.2.6 author its own `risk_flags[]` schema independent
  of 4.2.4? Recommend: no; 4.2.4 stays the qualitative surface, 4.2.6
  formalizes.
- **Q6.** Should the merged prompt
  `P-document-ideal-shape-weights-rules@v1` ship together with
  `P-emphasis-rules@v1`, or stay split until a bench gate passes?
  Recommend: ship split first; merged is bench-gated per 4.2.2 §8.3.
- **Q7.** Should `topic_coverage[]` be exposed in the snapshot as a
  detailed map (per family) or just a count? Recommend: keep the
  per-family map (§16.4) — operators need to alert on coverage gaps.

## 21. Primary Source Surfaces

- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/brainstorming-new-cv-v2.md`
- `src/preenrich/stages/presentation_contract.py`
- `src/preenrich/stages/jd_facts.py`
- `src/preenrich/stages/research_enrichment.py`
- `src/preenrich/stages/pain_point_intelligence.py`
- `src/preenrich/stages/stakeholder_surface.py`
- `src/preenrich/blueprint_models.py` (`ConfidenceDoc`, `EvidenceEntry`,
  `PromptMetadata`, `PresentationContractDoc`, `DocumentExpectationsDoc`,
  `CvShapeExpectationsDoc`, normalizers, enum sets
  `_PROOF_CATEGORIES` / `_PRESENTATION_SECTION_IDS` /
  `_DOCUMENT_GOALS` / `_ANTI_PATTERN_IDS`)
- `src/preenrich/blueprint_prompts.py` (`PROMPT_VERSIONS`,
  `SHARED_CONTRACT_HEADER`, `_json_only_contract`,
  existing `build_p_document_expectations` /
  `build_p_cv_shape_expectations` / `build_p_document_and_cv_shape`)
- `src/preenrich/blueprint_config.py` (feature flags;
  `presentation_contract_enabled`,
  `presentation_contract_document_expectations_enabled`,
  `presentation_contract_cv_shape_expectations_enabled`,
  `presentation_contract_merged_prompt_enabled`)
- `src/preenrich/stage_registry.py`
- `src/preenrich/stage_worker.py`
- `src/pipeline/tracing.py` (`PreenrichTracingSession`,
  `start_substage_span`, `_sanitize_langfuse_payload`)
- `src/layer1_4/claude_jd_extractor.py`
  (`IdealCandidateProfileModel`, `CandidateArchetype`)
- `src/layer6_v2/prompts/grading_rubric.py`
- `docs/current/cv-generation-guide.md`
- `docs/current/outreach-detection-principles.md`
- `docs/current/operational-development-manual.md`
- `docs/current/architecture.md`
- `AGENTS.md`

## 22. Implementation Targets

- new `TruthConstrainedEmphasisRulesDoc`, `Rule`,
  `ForbiddenClaimPattern`, `CredibilityLadderRule`,
  `TopicCoverageEntry`, `NormalizationEvent`,
  `TruthConstrainedEmphasisRulesDebug` sub-models in
  `src/preenrich/blueprint_models.py`.
- new `RuleTypeEnum`, `RuleTopicFamily`, `AppliesToKindEnum`,
  `RULE_TYPE_ENUM_VERSION`, `APPLIES_TO_ENUM_VERSION` in
  `src/preenrich/blueprint_models.py`.
- import `DocumentSectionIdEnum` / `_PRESENTATION_SECTION_IDS` (4.2.2),
  `ProofType` / `_PROOF_CATEGORIES` (4.2.3),
  `ExperienceDimension` (4.2.5),
  `AudienceVariantKey` (4.2.4),
  `TitleStrategyEnum` (4.2.2).
- extend `PresentationContractDoc` with
  `truth_constrained_emphasis_rules: TruthConstrainedEmphasisRulesDoc |
  None` field, consistent with the 4.2.2-first guarded pattern.
- new `normalize_truth_constrained_emphasis_rules_payload` in
  `src/preenrich/blueprint_models.py` alongside existing normalizers
  (alias map, kind+value coercion, conflict resolution by precedence,
  duplicate collapse, candidate-leakage detection,
  `regex_safe` validation).
- new `build_p_emphasis_rules` in
  `src/preenrich/blueprint_prompts.py` with
  `PROMPT_VERSIONS["emphasis_rules"] = "P-emphasis-rules@v1"`.
- new `_emphasis_rule_priors`,
  `_default_truth_constrained_emphasis_rules`,
  `_validate_truth_constrained_emphasis_rules` in
  `src/preenrich/stages/presentation_contract.py`.
- extend `PresentationContractStage.run` to synthesize 4.2.6 after
  4.2.5 in split-prompt mode and to parse the merged-prompt payload in
  merged-prompt mode; emit the substage span
  (`scout.preenrich.presentation_contract.emphasis_rules`) with §15.4
  metadata.
- new feature flag
  `presentation_contract_emphasis_rules_enabled()` in
  `src/preenrich/blueprint_config.py`.
- extend the cross-validator pass in
  `PresentationContractDoc.validate_cross_subdocument_invariants` (and
  the surrounding stage glue) to enforce I-ER1–I-ER14.
- update `src/preenrich/stages/blueprint_assembly.py` to project
  `JobBlueprintSnapshot.presentation_contract_compact.emphasis_rules`
  per §16.4.
- new tests under `tests/unit/preenrich/test_emphasis_rules_schema.py`,
  `test_emphasis_rules_ingress.py`,
  `test_emphasis_rules_invariants.py`,
  `test_emphasis_rules_caps.py`,
  `test_emphasis_rules_fail_open.py`,
  `test_emphasis_rules_trace_emission.py`,
  `test_emphasis_rules_snapshot_projection.py`,
  and `tests/data/emphasis_rules/corpus/` + `golden/`.
- new `scripts/smoke_emphasis_rules_subdocument.py` (local).
- `scripts/vps_run_presentation_contract.py` (shared with 4.2.4 / 4.2.5
  VPS wrappers) extended to surface 4.2.6 substep summary in heartbeat
  output.
- update `docs/current/architecture.md` "Iteration 4.2.6" section.
- update `docs/current/missing.md`.

---

## 15. Langfuse Tracing Contract

Inherits the 4.2 umbrella contract
(`plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
§8.8) and the `presentation_contract` stage-level contract in 4.2.2 §9.5.
This section is normative for 4.2.6's substage span. Verbose tracing
means **richer metadata and better operator debuggability**, not full
rule bodies dumped into Langfuse.

### 15.1 Canonical parent and child spans

- trace: `scout.preenrich.run` (unchanged)
- job span: `scout.preenrich.job` (unchanged)
- parent stage span: `scout.preenrich.presentation_contract`
- preflight span: `scout.preenrich.presentation_contract.preflight`
  (shared; 4.2.6 contributes `role_family_emphasis_rule_priors`,
  `title_safety_envelope`, `ai_claim_envelope`,
  `leadership_claim_envelope`, `architecture_claim_envelope`,
  `forbidden_claim_pattern_priors`, `credibility_ladder_priors` to its
  metadata)
- **4.2.6 substage span:**
  `scout.preenrich.presentation_contract.emphasis_rules`

Optional child spans under the `emphasis_rules` substage:

- `.prompt_build`
- `.llm_call.primary` (+ `.llm_call.fallback` if the parent's fallback
  transport fires)
- `.post_pass`
- `.schema_repair` (only when §15.3 fires)
- `.rule_conflict_resolution` (only when the normalizer collapses
  conflicts or duplicates)
- `.cross_validate` (shared cross-validator pass; contribution span)

No per-rule, per-pattern, or per-ladder spans. Cardinality is expressed
through metadata counts, never through span names. Repair attempts
bounded at 1.

### 15.2 Events

- `scout.preenrich.presentation_contract.emphasis_rules.fail_open`
- `scout.preenrich.presentation_contract.consistency.emphasis_rules`
  emitted by the cross-validator when it suppresses, downgrades, or
  retains a rule due to conflict with `dimension_weights`,
  `document_expectations`, `cv_shape_expectations`, or
  `ideal_candidate_presentation_model`. Metadata: `conflict_source` ∈
  `{document_expectations, cv_shape_expectations, ideal_candidate,
  dimension_weights}`, `rule_id`, `topic_family`, `applies_to_kind`,
  `applies_to`, `resolution ∈ {suppressed, downgraded, retained,
  overridden_by_defaults}`.

Cache events are owned by the parent span
(`scout.preenrich.presentation_contract.cache.hit|miss`). 4.2.6 does not
emit its own cache events.

### 15.3 Required canonical metadata (every span and event)

Identical to the 4.2 umbrella canonical payload from
`PreenrichTracingSession.payload_builder`:

`job_id`, `level2_job_id`, `correlation_id`, `langfuse_session_id`,
`run_id`, `worker_id`, `task_type`, `stage_name`, `attempt_count`,
`attempt_token`, `input_snapshot_id`, `jd_checksum`, `lifecycle_before`,
`lifecycle_after`, `work_item_id`.

### 15.4 Stage-specific metadata on the `emphasis_rules` substage span

On end:

- `status ∈ {completed, partial, inferred_only, unresolved,
  failed_terminal}`
- `source_scope` ∈ `{jd_only, jd_plus_research,
  jd_plus_research_plus_stakeholder}`
- `rule_type_enum_version`, `applies_to_enum_version`,
  `prompt_version`, `prompt_git_sha`
- **rule-set health:**
  - `global_rules_count`
  - `section_rule_count` (sum across all section buckets)
  - `section_rule_coverage_section_ids` (list)
  - `allowed_if_evidenced_count`
  - `downgrade_rules_count`
  - `omit_rules_count`
  - `forbidden_claim_patterns_count`
  - `credibility_ladder_rules_count`
- **topic coverage:**
  - `rule_topic_coverage_count` (count of mandatory families covered)
  - `mandatory_topic_families_missing` (list; empty on `completed`)
- **conflict outcomes:**
  - `title_strategy_conflict_count`
  - `ai_section_policy_conflict_count`
  - `dimension_weight_conflict_count`
  - `must_signal_contradiction_count`
  - `de_emphasize_reflection_missing_count`
- **normalization:**
  - `normalization_events_count`
  - `defaults_applied_count`
  - `rejected_output_count`
  - `cross_validator_violations_count`
  - `duplicate_rules_collapsed_count`
- **confidence:**
  - `confidence.band`, `confidence.score`
- **upstream availability:**
  - `jd_facts_available`, `classification_available`,
    `research_enrichment_available`, `stakeholder_surface_available`,
    `pain_point_intelligence_available`,
    `peer_document_expectations_available`,
    `peer_cv_shape_expectations_available`,
    `peer_ideal_candidate_available`,
    `peer_dimension_weights_available`
- `llm_call_schema_valid: bool`
- `fail_open_reason` when `status ∈ {partial, inferred_only,
  unresolved, failed_terminal}`: exactly one of
  - `jd_only_fallback`
  - `thin_research`
  - `thin_stakeholder`
  - `thin_pain_point_intelligence`
  - `mandatory_topic_coverage_default_filled`
  - `schema_repair_exhausted`
  - `cross_invariant_suppressed`
  - `title_inflation_detected`
  - `ai_authorization_above_intensity`
  - `leadership_authorization_above_envelope`
  - `candidate_leakage_detected`
  - `llm_terminal_failure`
  - `defaults_only`

Boolean alert helpers (used by monitoring; surfaced separately so
alerts don't have to parse bodies):

- `title_strategy_matches_peer: bool`
  (true iff 4.2.6 title rules consistent with 4.2.2 + 4.2.4)
- `ai_section_policy_consistent: bool`
- `dimension_caps_honored: bool`
- `mandatory_topic_coverage_complete: bool`
- `candidate_leakage_detected: bool`
- `forbidden_pattern_proof_order_safe: bool`
  (true iff no forbidden pattern uniformly suppresses top-two
  `proof_order[]` categories)

### 15.5 Outcome classifications

`llm_call.*` spans carry the iteration-4 transport outcome
classification: `success | unsupported_transport |
error_missing_binary | error_timeout | error_subprocess | error_no_json
| error_schema | error_exception`. `schema_valid: bool` is always set.

### 15.6 Retry / repair metadata

`schema_repair` child span metadata:

- `repair_reason` (one of the values listed in §15.3 repair contract)
- `repair_attempt` (always 1)
- `repaired_fields: list[str]`
- `pre_repair_schema_valid: bool`
- `post_repair_schema_valid: bool`

Retry events use the canonical `scout.preenrich.retry` at the parent
level with `stage_name="presentation_contract"`; 4.2.6 does not retry
independently at the worker level.

### 15.7 Cross-validator metadata

`cross_validate` contribution span metadata (authored by the parent
stage on behalf of 4.2.6):

- `invariants_checked_count`
- `invariants_violated_count`
- per-invariant ids when violated (e.g. `I-ER2`, `I-ER4`, `I-ER8`)
- `resolution ∈ {passed, downgraded, suppressed, overridden_by_defaults,
  parent_fallback}`

### 15.8 Trace refs into Mongo run records and parent artifact refs

- `preenrich_stage_runs[trace_id, trace_url]` — parent stage row;
  4.2.6 does not write its own row.
- `preenrich_job_runs[stage_status_map.presentation_contract]` —
  aggregate job-level; 4.2.6 contributes through the parent.
- `pre_enrichment.stage_states.presentation_contract.trace_id/url` —
  parent state; reached via the level-2 UI.
- `pre_enrichment.outputs.presentation_contract.trace_ref` —
  projection only.
- `JobBlueprintSnapshot.presentation_contract_compact.emphasis_rules.
  trace_ref` — compact snapshot reference; points back to the parent
  trace.

An operator opening a level-2 job in the UI reaches the Langfuse parent
trace in one click and the `emphasis_rules` substage in one more click.

### 15.9 Forbidden in Langfuse

- full `Rule.condition` / `Rule.action` / `Rule.basis` text
- full `forbidden_claim_patterns[].pattern` strings
  (counts and `pattern_id` are sufficient for telemetry)
- full `forbidden_claim_patterns[].example` strings (debug-only)
- full `credibility_ladder_rules[]` bodies
- full `rationale` paragraphs
- full `evidence[]` bodies
- full `debug_context` payloads
- raw LLM prompts unless `_sanitize_langfuse_payload` is applied and
  `LANGFUSE_CAPTURE_FULL_PROMPTS=true`
- first-person pronouns, candidate names, candidate URLs

Previews capped at 160 chars via `_sanitize_langfuse_payload`.

### 15.10 What may live only in `debug_context`

- raw LLM response (pre-normalization)
- normalization diffs (full `NormalizationEvent[]`)
- rejected-output path + reason pairs
- cross-validator per-invariant diffs
- defaults-applied ids with per-field provenance
- `forbidden_claim_pattern_examples[]` full strings
- conflict-resolution log per (`source`, `target`, `resolution`,
  `rule_id`)
- preflight envelopes (`title_safety_envelope`, `ai_claim_envelope`,
  `leadership_claim_envelope`, `architecture_claim_envelope`)

### 15.11 Cardinality and naming

- 4.2.6's substage span name is fixed:
  `...presentation_contract.emphasis_rules`.
- Optional child spans under it are a small closed set (§15.1).
- Repair attempts bounded at 1.
- No per-rule / per-pattern / per-ladder spans.
- Counts are emitted as metadata fields only.
- Mandatory topic families form a fixed enum (§10.6); coverage is
  expressed as a list and a count, not as per-family spans.

### 15.12 Operator debug checklist (normative)

An operator must be able to diagnose each of these from Mongo → trace in
under two minutes:

- slow subdocument synthesis —
  `emphasis_rules.llm_call.primary.duration_ms`.
- malformed LLM output — `emphasis_rules.schema_repair.repair_reason`.
- title-strategy drift — `title_strategy_matches_peer = false` AND
  `title_strategy_conflict_count > 0`.
- AI authorization above intensity —
  `ai_section_policy_consistent = false` OR
  `fail_open_reason = ai_authorization_above_intensity`.
- leadership authorization above envelope —
  `fail_open_reason = leadership_authorization_above_envelope`.
- dimension cap drift — `dimension_caps_honored = false` AND
  `dimension_weight_conflict_count > 0`.
- mandatory coverage gap —
  `mandatory_topic_coverage_complete = false` AND
  `mandatory_topic_families_missing` is non-empty (with
  `defaults_applied_count > 0`).
- candidate leakage — `candidate_leakage_detected = true`.
- forbidden-pattern over-reach —
  `forbidden_pattern_proof_order_safe = false`.
- defaulted-only run — `status = inferred_only` AND
  `defaults_applied_count > 0`.
- cross-invariant suppression — `consistency.emphasis_rules` event with
  `resolution ∈ {suppressed, overridden_by_defaults, parent_fallback}`.
