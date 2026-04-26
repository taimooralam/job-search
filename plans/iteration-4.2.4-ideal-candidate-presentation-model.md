# Iteration 4.2.4 Plan: Ideal Candidate Presentation Model

## 1. Executive Summary

`ideal_candidate_presentation_model` is **one subdocument co-produced inside
the `presentation_contract` stage** (alongside 4.2.2 `document_expectations`
and `cv_shape_expectations`, 4.2.5 `experience_dimension_weights`, and 4.2.6
`truth_constrained_emphasis_rules`). It is not a standalone preenrich stage,
does not own a DAG node, and does not own an independent work-item lifecycle.

This subdocument extends the role-truth view produced in
`jd_facts.extraction.ideal_candidate_profile` (the `IdealCandidateProfileModel`
in `src/layer1_4/claude_jd_extractor.py`) into a **presentation-truth** view:
how the ideal candidate for this specific evaluator surface should be **framed
on paper**, in a way that is candidate-agnostic, internally consistent with its
peer subdocuments, and safe against identity inflation.

The subdocument is purely candidate-agnostic. It defines visible identity,
acceptable titles, title strategy, must/should/de-emphasize signals, the proof
ladder, tone profile, credibility markers, risk flags, and per-evaluator
audience variants. It does not describe candidate evidence, does not emit CV
prose, and does not bind final copy choices.

Operational discipline is inherited from the rest of 4.2:

- **Mongo is the control plane.** `work_items`, `preenrich_stage_runs`,
  `preenrich_job_runs`, and `pre_enrichment.stage_states.presentation_contract`
  drive execution. 4.2.4 does not add a new control surface.
- **Langfuse is the observability sink.** The subdocument emits under the
  `scout.preenrich.presentation_contract.ideal_candidate` substage span with
  metadata-first payloads; full bodies live in Mongo `debug_context`.
- **VPS validation** happens through the `presentation_contract` stage, not
  through a fictitious standalone `preenrich.ideal_candidate_presentation_model`
  stage.

## 2. Mission

Turn "who should this CV look like?" into a structured, evaluator-aware,
evidence-referenced, candidate-agnostic contract that the later candidate-aware
CV generation path can consume without re-deriving identity framing from raw
research.

## 3. Objectives

- **O1.** Produce a typed, enum-constrained `ideal_candidate_presentation_model`
  subdocument inside every successful `presentation_contract` run.
- **O2.** Keep every field grounded in `jd_facts`, `classification`,
  `research_enrichment`, `stakeholder_surface`, or `pain_point_intelligence`
  evidence; reject inflation beyond role evidence.
- **O3.** Enforce cross-subdocument invariants with the three peer subdocuments
  (`title_strategy`, proof ladder, signal tags, audience variants, dimension
  consistency) at a single deterministic validator gate.
- **O4.** Fail open to role-family priors with lower confidence and explicit
  `unresolved_markers[]` when upstream is thin; never fail the parent stage
  solely because 4.2.4 had to default.
- **O5.** Emit a Langfuse substage that lets an operator diagnose title
  strategy drift, proof-ladder enum drift, audience-variant leakage, and
  schema-repair retries in under two minutes from Mongo → trace.
- **O6.** Be validated on the VPS through the `presentation_contract` stage on
  a real level-2 job with full upstream prerequisites before default-on
  rollout.

## 4. Goals

- **G1.** Single subdocument, single schema, single validator. No new
  control plane, no new collection.
- **G2.** Canonical `title_strategy`, `proof_ladder`, `signal_tag`, `tone_axis`,
  `audience_variant_key`, and `risk_flag` enums, shared with peer subdocuments
  where they already own a canonical enum (proof categories come from 4.2.3;
  section ids from 4.2.2; dimensions from 4.2.5).
- **G3.** A compact snapshot projection inside
  `job_blueprint_snapshot.presentation_contract_compact.ideal_candidate`:
  counts, booleans, confidence band, trace ref. Never full bodies.
- **G4.** No fabricated identity: every `acceptable_title`, `must_signal`,
  `credibility_marker` is evidence-bound or defaulted from the declared role
  family with `defaults_applied[]` recorded.
- **G5.** Single stage-local feature flag
  (`presentation_contract_ideal_candidate_enabled()`) gating the LLM path; the
  deterministic fallback is always available.
- **G6.** Safe cohabitation with 4.2.2: when the merged prompt
  (`P-document-and-cv-shape@v1` — see §9.3 in 4.2.2) is on, 4.2.4 synthesis
  remains a distinct parse-time subdocument with its own span and validator.

## 5. Success Criteria

The subdocument is successful when, for a representative 30-job corpus (mixed
IC / EM / Director / Head, mixed research quality, mixed ATS):

- **SC1.** 100% of `presentation_contract` runs produce a validated
  `ideal_candidate_presentation_model` with `status ∈ {completed, partial,
  inferred_only, unresolved}`. None terminal due to 4.2.4 schema issues alone.
- **SC2.** Reviewer-rated identity-clarity ≥ 4.0 / 5 median (rubric §14.8).
- **SC3.** 0 candidate-leakage events (first-person, candidate companies,
  candidate tenures) across the corpus.
- **SC4.** `title_strategy` matches `cv_shape_expectations.title_strategy`
  on 100% of runs after the cross-validator pass.
- **SC5.** `proof_ladder[]` uses only canonical proof categories from 4.2.3
  on 100% of runs.
- **SC6.** `audience_variants` keys are always a subset of
  `stakeholder_surface.evaluator_coverage_target`.
- **SC7.** For `stakeholder_surface.status ∈ {inferred_only, no_research,
  unresolved}`, `confidence.band ≤ medium` and at least one
  `unresolved_marker` is set; no fabricated real-stakeholder preference is
  emitted.
- **SC8.** Langfuse substage `scout.preenrich.presentation_contract.ideal_candidate`
  is emitted on every run with full §11 metadata, one click from the level-2 UI.
- **SC9.** VPS smoke (§13) completes on a real job with artifacts under
  `reports/presentation-contract/<job_id>/ideal_candidate/`.

## 6. Non-Goals

- Final CV prose, title copy, header text, summary sentences, bullets.
  Final copy generation remains governed by `docs/current/cv-generation-guide.md`.
- Candidate evidence retrieval, master-CV read-through, STAR selection.
  These belong to 4.3.x.
- Candidate identity, candidate tenures, candidate companies, candidate
  achievements. This subdocument is candidate-agnostic.
- Ownership of `DocumentSectionIdEnum` (owned by 4.2.2), `ProofTypeEnum`
  (owned by 4.2.3), or `ExperienceDimension` enum (owned by 4.2.5). 4.2.4
  imports, it does not redefine.
- Private stakeholder motives, clinical/psychological profiling, protected-
  trait inference.
- A standalone preenrich stage, a distinct DAG node, or an independent work-
  item lifecycle for this subdocument.
- A new cache key scoped only to this subdocument. The parent
  `presentation_contract` cache key governs invalidation.

## 7. Why This Artifact Exists

`jd_facts.extraction.ideal_candidate_profile`
(`IdealCandidateProfileModel` in `src/layer1_4/claude_jd_extractor.py`)
already captures `identity_statement`, `archetype` (from `CandidateArchetype`),
`key_traits`, `experience_profile`, and `culture_signals`. That is role-truth
only. It answers "what kind of person solves this role?" It does not answer:

- Which parts of that identity should be **front-loaded** on the CV versus
  held back because they will be assumed or irrelevant for this evaluator?
- What title framing is **safe** given the JD title, the classification, the
  company identity, and the role family?
- What credibility ladder should the document follow, and which credibility
  markers are non-negotiable for this evaluator?
- Where the CV risks **over-claiming** (e.g. "AI expertise" claimed when the
  role is AI-adjacent) or **under-claiming** (e.g. leadership framing when the
  team-context signal is high).
- How the same role should be framed differently to a recruiter vs. a
  hiring manager vs. a peer technical reviewer.

4.2.4 answers those questions as structured, enum-bound policy, not prose.
It is the bridge between role-truth and CV-skeleton-truth, and it is
specifically evaluator-aware via `stakeholder_surface`.

Why this must be a subdocument inside `presentation_contract`, not a separate
stage:

- It shares the same five upstream inputs as 4.2.2 / 4.2.5 / 4.2.6.
- It shares one evidence frame and one invalidation key with them.
- It needs a single cross-validation gate against its peers
  (`title_strategy`, proof-ladder enum, dimension mentions, audience variants).
- Splitting it out would drive prompt drift and contradictory defaults with no
  benefit, since it performs no fetches and owns no identity-safety surface.

## 8. Subdocument Boundary

### 8.1 Placement

Co-produced inside the `presentation_contract` stage, which is itself placed
in the DAG as:

```
jd_facts -> classification -> application_surface -> research_enrichment
   -> stakeholder_surface -> pain_point_intelligence -> presentation_contract
```

4.2.4 does not register a `StageDefinition`. It is not in
`_blueprint_registry()`. It does not enqueue a work item. It does not hold a
lease. The parent `presentation_contract` stage owns all of those.

### 8.2 Relationship to peer subdocuments

- **`document_expectations` (4.2.2).** 4.2.4 reads `primary_document_goal`,
  `proof_order[]`, `audience_variants` (roles in scope), `tone_posture`, and
  `density_posture` as upstream peers when the merged or split prompt has
  already produced them. It never overrides them. `must_signal[]` and
  `de_emphasize[]` must not contradict `proof_order[]`. `tone_profile` must be
  consistent with `tone_posture.primary_tone` (mapping in §10.5).
- **`cv_shape_expectations` (4.2.2).** 4.2.4 owns `acceptable_titles[]` and
  the *content* of `title_strategy`; 4.2.2 owns the enum value
  `cv_shape_expectations.title_strategy` as a policy decision. The cross-
  validator enforces
  `ideal_candidate_presentation_model.title_strategy ==
  cv_shape_expectations.title_strategy` (4.2.2 §4.7).
- **`pain_point_intelligence` (4.2.3).** 4.2.4 imports `ProofTypeEnum` for the
  proof-ladder categorization. Every `proof_ladder[]` entry MUST use a value
  from 4.2.3's enum; no new proof categories are introduced here.
  `credibility_markers[]` should map to observable shapes of proof expressed
  by `pain_point_intelligence.proof_map[].preferred_evidence_shape` (free-text
  but restricted to evaluator-derived concrete signals).
- **`experience_dimension_weights` (4.2.5).** 4.2.4 does not emit numeric
  dimension weights. When `must_signal[]` or `should_signal[]` name a
  dimension-scoped concept (e.g. "AI/ML depth"), the dimension reference must
  match a value in 4.2.5's `ExperienceDimension` enum. 4.2.5 sets the numeric
  weight; 4.2.4 sets the qualitative visibility signal.
- **`truth_constrained_emphasis_rules` (4.2.6).** 4.2.6 converts 4.2.4's
  `risk_flags[]` and `de_emphasize[]` into enforceable Rule records. 4.2.4
  never authors `Rule[]` entries; it produces the qualitative risk surface
  that 4.2.6 formalizes.

### 8.3 Relationship to upstream `IdealCandidateProfileModel`

`jd_facts.extraction.ideal_candidate_profile` is the **role-truth seed**.
4.2.4 may:

- extend `archetype` into `visible_identity` (one short phrase, ≤ 120 chars).
- extend `key_traits[]` into `must_signal[]` / `should_signal[]` with explicit
  evaluator justification.
- extend `culture_signals[]` into `tone_profile` and `credibility_markers[]`.

4.2.4 must not:

- reject `archetype` without explicit evidence from `stakeholder_surface` or
  `research_enrichment`.
- inflate `experience_profile` (e.g. upgrade "Senior" to "Principal").
- contradict `classification.ai_taxonomy.intensity` when deriving AI
  credibility markers.

## 9. Inputs

### 9.1 Required (from upstream `pre_enrichment.outputs`)

- `jd_facts.merged_view` — particularly `ideal_candidate_profile`,
  `identity_signals`, `expectations`, `skill_dimension_profile`,
  `team_context`, `weighting_profiles`, `top_keywords`, `title`,
  `normalized_title`, `seniority_level`.
- `classification` — `primary_role_category`, `seniority`, `tone_family`,
  `ai_taxonomy.intensity`, `ai_taxonomy.modalities`.
- `research_enrichment.company_profile` — `canonical_name`, `industry`,
  `stage`, `identity_confidence.band`, `scale_signals[]`,
  `ai_data_platform_maturity`.
- `research_enrichment.role_profile` — `mandate`, `business_impact`,
  `evaluation_signals[]`, `success_metrics[]`, `risk_landscape[]`.
- `stakeholder_surface` — `evaluator_coverage_target[]`, per-role
  `cv_preference_surface`, `preferred_signal_order[]`, `preferred_evidence_types[]`,
  `likely_reject_signals[]`, `status`.
- `pain_point_intelligence` — `proof_map[]`, `pain_points[].likely_proof_targets[]`,
  `bad_proof_patterns[]`, `status`.

### 9.2 Opportunistic (same-run peers allowed; never hard prerequisites)

- `document_expectations` (4.2.2) when produced earlier in the same
  `presentation_contract` run.
- `cv_shape_expectations` (4.2.2) when produced earlier in the same run
  (for `title_strategy` alignment).
- `job_inference.semantic_role_model` (compat prior).

The parent stage enforces temporal ordering: when split prompts are used,
document-expectations → cv-shape-expectations → ideal-candidate → dimension-
weights → emphasis-rules. When the merged prompt is used, the parse-time
split hydrates all four subdocuments with the same peer references.

### 9.3 Deterministic preflight helpers (extending 4.2.2 §3.3)

- **`role_family_identity_priors`** — per-role-family defaults for
  `visible_identity_stub`, `tone_profile`, `credibility_markers[]`, and
  `proof_ladder[]`. Seed from `docs/current/cv-generation-guide.md` role
  guidance plus `grading_rubric.py` dimension priors.
- **`acceptable_title_candidates[]`** — generated deterministically from:
  - `jd_facts.merged_view.title`
  - `jd_facts.merged_view.normalized_title`
  - `classification.primary_role_category` role-family synonyms (bounded list)
  - `jd_facts.identity_signals.title_safety_band` if present
  Capped at 4 candidates. The LLM may drop or reorder but not invent new
  candidates outside this bounded set unless a stakeholder preference signal
  in `stakeholder_surface` explicitly authorizes one.
- **`signal_priors_by_role_family`** — `{ must_signal[], should_signal[],
  de_emphasize[] }` role-family defaults, used when stakeholder signals are
  thin.
- **`tone_profile_priors`** — per-role-family tone axis intensities used as
  starting values for LLM synthesis or as fallback when the LLM cannot commit.
- **`audience_variant_candidates`** — intersection of
  `stakeholder_surface.evaluator_coverage_target` and the canonical
  `AudienceVariantKey` enum (§10.5).

All preflight helpers are deterministic, idempotent, and recorded under
`debug_context.input_summary`. Preflight never fails the subdocument.

### 9.4 Invalidation / cache

4.2.4 does NOT own its own cache key. It inherits the parent
`presentation_contract` input hash (built from `jd_facts`, `classification`,
`research_enrichment.research_input_hash`,
`stakeholder_surface.coverage_digest`,
`pain_point_intelligence.pain_input_hash`, and all relevant `PROMPT_VERSION`s
for the parent stage). Any drift in any of those busts the parent cache and
re-runs all subdocuments, including 4.2.4. This is intentional: splitting the
cache would allow drift between peer subdocuments.

## 10. Output Shape

### 10.1 Pydantic model

`IdealCandidatePresentationModelDoc` in `src/preenrich/blueprint_models.py`,
nested under `PresentationContractDoc.ideal_candidate_presentation_model`
(analogous to the existing `document_expectations` / `cv_shape_expectations`
slots).

```text
IdealCandidatePresentationModelDoc {
  status,                           # "completed" | "partial" | "inferred_only"
                                    # | "unresolved" | "failed_terminal"
  visible_identity,                 # <= 120 chars, candidate-agnostic
  acceptable_titles[],              # 1..4 items, drawn from preflight candidates
  title_strategy,                   # TitleStrategyEnum (mirrors 4.2.2)
  must_signal[],                    # 2..6 SignalTag entries
  should_signal[],                  # 0..6 SignalTag entries
  de_emphasize[],                   # 0..6 SignalTag entries
  proof_ladder[],                   # ordered 3..6 ProofLadderStep entries
  tone_profile {
    operator,                       # float [0.0, 1.0]
    architect,                      # float [0.0, 1.0]
    builder,                        # float [0.0, 1.0]
    leader,                         # float [0.0, 1.0]
    transformation,                 # float [0.0, 1.0]
    platform,                       # float [0.0, 1.0]
    execution                       # float [0.0, 1.0]
  },
  framing_rules[],                  # 0..8 short candidate-agnostic rule strings
  credibility_markers[],            # 2..6 CredibilityMarker entries
  risk_flags[],                     # 0..6 RiskFlag entries
  audience_variants {               # 0..4 entries, keys from AudienceVariantKey
    recruiter         : AudienceVariant | null,
    hiring_manager    : AudienceVariant | null,
    executive_sponsor : AudienceVariant | null,
    peer_reviewer     : AudienceVariant | null,
  },
  unresolved_markers[],             # free-text, bounded 12 entries
  rationale,                        # 1-3 short paragraphs, bounded 800 chars
  debug_context: IdealCandidateDebug,
  confidence: ConfidenceDoc,
  evidence: list[EvidenceEntry],
}
```

### 10.2 SignalTag

```text
SignalTag {
  tag,                              # slug, lower_snake_case, <= 48 chars
  category,                         # SignalCategoryEnum (§10.5)
  proof_type,                       # ProofTypeEnum (§10.5) or null
  rationale,                        # <= 160 chars, candidate-agnostic
  evidence_refs[],                  # artifact:<path> or source:<id>
}
```

### 10.3 ProofLadderStep

```text
ProofLadderStep {
  step_index,                       # 0..5
  category,                         # ProofLadderCategoryEnum (§10.5)
  proof_type,                       # ProofTypeEnum (§10.5)
  intent,                           # <= 160 chars, candidate-agnostic
}
```

### 10.4 CredibilityMarker, RiskFlag, AudienceVariant

```text
CredibilityMarker {
  marker_id,                        # slug
  marker_type,                      # CredibilityMarkerTypeEnum (§10.5)
  description,                      # <= 160 chars, candidate-agnostic
  evidence_refs[],                  # artifact:<path> or source:<id>
}

RiskFlag {
  flag_id,                          # slug
  flag_type,                        # RiskFlagTypeEnum (§10.5)
  description,                      # <= 200 chars
  mitigation_hint,                  # <= 200 chars, candidate-agnostic
}

AudienceVariant {
  tilt[],                           # 2..6 short bias tags, candidate-agnostic
  must_see[],                       # 2..6 SignalTag.tag values (subset of parent)
  avoid[],                          # 0..4 SignalTag.tag values (subset of parent)
  rationale,                        # <= 200 chars
}
```

### 10.5 Canonical enums (owned by 4.2.4 unless noted)

```
TitleStrategyEnum          # MIRRORED from 4.2.2 CvShapeExpectationsDoc
  exact_match | closest_truthful | functional_label | unresolved

AudienceVariantKey         # OWNED by 4.2.4
  recruiter | hiring_manager | executive_sponsor | peer_reviewer
  # must be subset of stakeholder_surface.evaluator_coverage_target

SignalCategoryEnum         # OWNED by 4.2.4
  identity | capability | scope | domain | credibility | outcome
  | leadership | ai | platform | delivery | risk

ProofLadderCategoryEnum    # OWNED by 4.2.4
  identity | capability | proof | business_outcome | credibility

ProofTypeEnum              # IMPORTED from 4.2.3 (owned by pain_point_intelligence)
  metric | architecture | leadership | domain | reliability
  | ai | stakeholder | process | compliance | scale

CredibilityMarkerTypeEnum  # OWNED by 4.2.4
  named_production_system | named_scale_marker | named_stakeholder_scope
  | named_domain_credential | named_cost_or_revenue_impact
  | named_regulatory_footprint | named_platform_ownership
  | named_team_ownership

RiskFlagTypeEnum           # OWNED by 4.2.4
  title_inflation | ai_overclaim | leadership_overclaim
  | architecture_overclaim | domain_overclaim | scale_overclaim
  | under_claim_of_scope | missing_credibility_marker
  | audience_variant_mismatch

DocumentSectionIdEnum      # IMPORTED from 4.2.2; never referenced inside
                           # framing tag strings (enforced in §12)

ExperienceDimension        # IMPORTED from 4.2.5; used only in evidence_refs
                           # and dimension-scoped signal tags
```

### 10.6 `evidence_refs[]` format

Pinned to the same format as 4.2.3:

- `source:<source_id>` where `source_id` exists in the parent
  `presentation_contract` run's composite source list (union of research and
  JD-derived sources).
- `artifact:<dotted-path>` rooted at
  `pre_enrichment.outputs.<stage>.<field>[...]`.

Mixed or free-form strings are rejected by the post-pass.

### 10.7 `debug_context`

```text
IdealCandidateDebug {
  input_summary {
    role_family,
    seniority,
    ai_intensity,
    tone_family,
    title,
    normalized_title,
    evaluator_roles_in_scope[],
    acceptable_title_candidates[],
    research_status,
    stakeholder_surface_status,
    pain_point_status,
    peer_title_strategy,              # read from cv_shape_expectations if present
  },
  defaults_applied[],                 # role-family-prior ids applied
  normalization_events[],             # alias mapping, coercion, clamp events
  richer_output_retained[],           # richer-than-schema fields kept for §11.3
  rejected_output[],                  # {path, reason}; candidate leakage etc.
  retry_events[],                     # {repair_reason, repair_attempt}
  cross_validator_diffs[],            # violated invariants before final resolution
}
```

Debug block is collection-backed only, 16 KB cap, never in snapshot.

## 11. Richer-Output Normalization

Inherits 4.2.2 §5 verbatim and restates the 4.2.4-specific nuances:

### 11.1 Alias and coercion map

- `visible_summary` → `visible_identity`
- `titles` | `title_options` | `title_candidates` → `acceptable_titles`
- `tone` | `tone_axis` | `axis_weights` → `tone_profile`
- `evaluator_variants` → `audience_variants`
- `risks` | `risk_notes` → `risk_flags`
- `framing` | `positioning_notes` → `framing_rules`
- `proof_chain` | `ladder` → `proof_ladder`
- signal-tag strings delivered as flat strings ("architecture_depth") → map to
  `{tag: "architecture_depth", category: "capability", proof_type: "architecture"}`
  via a deterministic enricher that fills missing fields from the preflight
  prior, not from the LLM.
- tone axis as list-of-pairs or as map → canonical map.
- `audience_variants` as list-of-dicts keyed by `role` → canonical map keyed
  by `AudienceVariantKey`.

### 11.2 Strict-on-truth rejections

- Any `audience_variant` key not in
  `stakeholder_surface.evaluator_coverage_target` → rejected at ingress.
- Any `title` outside `preflight.acceptable_title_candidates` AND not
  corresponding to a stakeholder-authorized alias → rejected.
- Any `proof_type` outside `ProofTypeEnum` → rejected.
- Any `proof_ladder[].category` outside `ProofLadderCategoryEnum` → rejected.
- Any `must_signal[].tag`, `should_signal[].tag`, or `de_emphasize[].tag`
  whose value matches a `DocumentSectionIdEnum` member → rejected (§12.1).
- Any `credibility_marker_type` outside `CredibilityMarkerTypeEnum` →
  rejected.
- Any `risk_flag_type` outside `RiskFlagTypeEnum` → rejected.
- Any tone axis value outside `[0.0, 1.0]` after coercion → clamped; event
  logged to `normalization_events[]`.
- Any first-person pronoun (`I`, `my`, `we`, `our`) in any string field →
  rejected; field omitted; `debug_context.rejected_output[]` entry recorded;
  status downgraded to `partial`.
- Any inflated title (e.g. JD "Lead" → LLM "VP") with no
  stakeholder-authorized justification → rejected; `defaults_applied` used.
- Any AI depth claim with `classification.ai_taxonomy.intensity ∈ {none,
  adjacent}` → rejected.

### 11.3 Richer-output retention

Unknown-but-grounded fields (e.g. extra per-variant narrative, extra tone-axis
dimensions, stakeholder-specific proof-ladder hints) are preserved under
`debug_context.richer_output_retained[]` as `{key, value, note}` entries and
flagged for schema-evolution review once the rate exceeds 30% over a 100-job
benchmark (same rule as 4.2.2 §5.5).

## 12. Safety / Anti-Hallucination Rules

### 12.1 Candidate-leakage detection (hard fail-closed)

- reject first-person pronouns anywhere
- reject proper nouns that are not the hiring company's canonical name,
  canonical domain, or a canonical framework name
- reject tokens matching `candidate_*` or `my_*`
- reject exact numeric achievements (e.g. `40% YoY`) unless the token
  appears verbatim in the JD
- reject framing rule strings that reference a specific employer or
  certification body

### 12.2 Identity-inflation fail-closed rules

- no `acceptable_title` whose level-token (`VP`, `Head`, `Director`,
  `Principal`, `Staff`, `Lead`, `Senior`, `Manager`) exceeds the JD title
  level-token unless `stakeholder_surface` contains an explicit
  `cv_preference_surface.title_safety_override`.
- no "strategic visionary", "rockstar", "ninja", "guru", "10x" tokens in
  any string field.
- no AI depth claim in `must_signal[]` / `should_signal[]` /
  `credibility_markers[]` when `classification.ai_taxonomy.intensity ∈ {none,
  adjacent}`.
- no leadership depth claim in `must_signal[]` / `credibility_markers[]`
  when `classification.seniority ∈ {junior, mid, senior_ic}` and
  `jd_facts.team_context.direct_reports ≤ 0`.
- no domain credential claim without a matching signal in
  `research_enrichment.company_profile.signals[]` or
  `role_profile.evaluation_signals[]`.

### 12.3 Audience-variant boundary

- variant keys ⊆ `stakeholder_surface.evaluator_coverage_target`
- variant `must_see[]` / `avoid[]` values ⊆ parent `must_signal[].tag` ∪
  `should_signal[].tag` ∪ `de_emphasize[].tag`
- if `stakeholder_surface.status ∈ {inferred_only, no_research, unresolved}`,
  only `recruiter` and `hiring_manager` variants may be populated, and
  `confidence.band ≤ medium`

### 12.4 Confidence caps

- when `research_enrichment.status ∈ {partial, unresolved}` AND
  `stakeholder_surface.status ∈ {inferred_only, no_research, unresolved}`:
  `confidence.band ≤ medium`, `confidence.score ≤ 0.69`
- when both upstreams are `completed` but `pain_point_intelligence.status ==
  unresolved`: `confidence.band ≤ medium`
- when defaults applied on any of `acceptable_titles`, `proof_ladder`,
  `tone_profile`, or `audience_variants`: `confidence.band ≤ medium`

## 13. Cross-Subdocument Invariants (deterministic validator)

All invariants are enforced by the shared `presentation_contract`
cross-validator pass described in 4.2.2 §4.7. Any failure fails the entire
`presentation_contract` run and falls back to role-family defaults per
umbrella §8.2.

- **I1.** `ideal_candidate_presentation_model.title_strategy ==
  cv_shape_expectations.title_strategy`.
- **I2.** `ideal_candidate_presentation_model.acceptable_titles[]` is bounded
  by `preflight.acceptable_title_candidates` (or a stakeholder-authorized
  alias) and does not exceed the JD title level-token (§12.2).
- **I3.** every `proof_ladder[].proof_type` and every `SignalTag.proof_type`
  ∈ `ProofTypeEnum` (owned by 4.2.3).
- **I4.** every `SignalTag.category` ∈ `SignalCategoryEnum`; every
  `proof_ladder[].category` ∈ `ProofLadderCategoryEnum`.
- **I5.** `must_signal[]` and `should_signal[]` do not contradict
  `document_expectations.proof_order[]` — every proof_type that appears in
  `must_signal[]` must also appear in `document_expectations.proof_order[]`.
- **I6.** `de_emphasize[]` does not contain any tag whose `proof_type`
  appears in `document_expectations.proof_order[0:2]` (top-two proof
  categories cannot be simultaneously de-emphasized).
- **I7.** `tone_profile` directional vector is consistent with
  `document_expectations.tone_posture.primary_tone`:
  - `evidence_first` → `operator + architect ≥ 0.6`
  - `operator_first` → `operator ≥ 0.6`
  - `architect_first` → `architect ≥ 0.6`
  - `leader_first` → `leader ≥ 0.6`
  - `balanced` → no axis dominates (max axis ≤ 0.8)
- **I8.** `audience_variants` keys ⊆
  `stakeholder_surface.evaluator_coverage_target`.
- **I9.** dimension-scoped signal tags reference only values from 4.2.5's
  `ExperienceDimension` enum.
- **I10.** `credibility_markers[]` cardinality is consistent with
  `document_expectations.density_posture.overall_density`:
  - `density=high` → ≥ 3 markers
  - `density=medium` → ≥ 2 markers
  - `density=low` → ≥ 2 markers (unchanged, safety floor)
- **I11.** `risk_flags[]` must include at least one
  `title_inflation` entry when `classification.seniority` differs from
  `jd_facts.seniority_level` by more than one step.
- **I12.** no tag string is a `DocumentSectionIdEnum` value (§11.2).

Violation escalates to a single schema-repair retry through the parent stage's
existing repair path, then falls back to `_default_ideal_candidate_presentation_model`
(§15) marked `defaults_applied[]`.

## 14. Fail-Open / Fail-Closed Rules

### 14.1 Fail open (preferred over empty)

- `stakeholder_surface.status = inferred_only` → `audience_variants`
  restricted to inferred personas only; `confidence.band ≤ medium`;
  `unresolved_markers[] += ["stakeholder_surface_inferred_only"]`.
- `stakeholder_surface.status ∈ {no_research, unresolved}` → audience
  variants restricted to `{recruiter, hiring_manager}` only; role-family
  priors applied; `defaults_applied[] += [...]`.
- `pain_point_intelligence.proof_map[]` thin (<3 entries) → `proof_ladder[]`
  defaults from role-family priors with lower confidence;
  `unresolved_markers[] += ["thin_proof_map"]`.
- `research_enrichment.role_profile.status = partial` → `credibility_markers[]`
  derive from `classification` and `jd_facts` priors;
  `unresolved_markers[] += ["partial_role_profile"]`.
- schema-repair exhausted → keep LLM's first parseable output, downgrade
  `status = partial`, record `fail_open_reason = "schema_repair_exhausted"`.
- LLM terminal failure → `_default_ideal_candidate_presentation_model` fallback
  with `status = unresolved` and `fail_open_reason = "llm_terminal_failure"`.

### 14.2 Fail closed (hard reject; drop offending field)

- any candidate-specific assertion (§12.1)
- any title inflation beyond role evidence (§12.2)
- any AI claim beyond `ai_taxonomy.intensity` (§12.2)
- any `audience_variant` key outside `evaluator_coverage_target`
- any tag string equal to a `DocumentSectionIdEnum` value
- any proof_type outside `ProofTypeEnum`
- any tone-axis value outside `[0.0, 1.0]` after clamp (terminal only if
  clamp itself cannot resolve)

Minimum viable artifact under fail-open (never empty):

- `visible_identity` populated (role-family default acceptable)
- `acceptable_titles[]` populated with at least the JD title
- `title_strategy` populated (`closest_truthful` default)
- `must_signal[]` with ≥ 2 entries
- `proof_ladder[]` with ≥ 3 entries
- `tone_profile` populated with role-family priors
- `audience_variants[recruiter]` and `audience_variants[hiring_manager]`
  populated

### 14.3 Partial completion statuses

```
status in {
  "completed",
  "partial",            # fail-open path used for one or more fields
  "inferred_only",      # entire subdocument emitted from role-family priors
  "unresolved",         # minimum artifact could not be assembled
  "failed_terminal"     # safety violation; subdocument not persisted,
                        # parent stage falls back to role-family defaults
}
```

## 15. Synthesis Strategy (inside `presentation_contract`)

### 15.1 Ordering inside the parent stage

The parent stage runs, in order:

1. Parent preflight (`_role_thesis_priors`, `_evaluator_axis_summary`,
   `_proof_order_candidates`, `_ats_envelope_profile`) — already implemented.
2. **New 4.2.4 preflight extension** (`_ideal_candidate_priors`, §9.3).
3. If `presentation_contract_merged_prompt_enabled()` → one merged
   LLM call (`P-document-ideal-shape-weights-rules@v1`, future) that
   returns all four subdocuments; 4.2.4 hydrates from the
   `ideal_candidate_presentation_model` key.
4. Else (split prompt mode, default) — in sequence:
   - `P-document-expectations@v1`
   - `P-cv-shape-expectations@v1`
   - **`P-ideal-candidate@v1`** — 4.2.4, reads peer outputs (1..3 above) as
     same-run peers
   - 4.2.5 and 4.2.6 prompts as they ship
5. Deterministic normalizer + validator for each subdocument.
6. Cross-subdocument validator (§13).
7. Persistence (collection-backed) + snapshot projection + Langfuse
   finalization.

### 15.2 `P-ideal-candidate@v1` prompt

Builder: `build_p_ideal_candidate` in `src/preenrich/blueprint_prompts.py`,
following the same structure as `build_p_document_expectations` (prefix with
`SHARED_CONTRACT_HEADER`, append `_json_only_contract(PROMPT_VERSIONS[
"ideal_candidate"], ["ideal_candidate_presentation_model"])`).

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
  "stakeholder_axis": [ /* evaluator_axis_summary, §3.3 of 4.2.2 */ ],
  "evaluator_coverage_target": [ ... ],
  "proof_category_frequencies": { ... },
  "peer_document_expectations": { /* verbatim DocumentExpectationsDoc */ },
  "peer_cv_shape_expectations": { /* verbatim CvShapeExpectationsDoc */ },
  "pain_proof_map_summary": [ { "pain_id": ..., "preferred_proof_type": ...,
                                "preferred_evidence_shape": "..." }, ... ],
  "ideal_candidate_profile_seed": { /* verbatim IdealCandidateProfileModel
                                       from jd_facts.extraction */ },
  "preflight": {
    "acceptable_title_candidates": [ ... ],
    "role_family_identity_priors": { ... },
    "signal_priors_by_role_family": { ... },
    "tone_profile_priors": { ... },
    "audience_variant_candidates": [ ... ]
  },
  "enums": {
    "title_strategy": [...],
    "audience_variant_key": [...],
    "signal_category": [...],
    "proof_ladder_category": [...],
    "proof_type": [...],
    "credibility_marker_type": [...],
    "risk_flag_type": [...],
    "experience_dimension": [...]
  }
}
```

Instruction additions (appended to `SHARED_CONTRACT_HEADER`):

- You do not know the candidate. Never reference a specific candidate,
  employer, tenure, or achievement. No first-person language.
- Describe how the **ideal** candidate should be **framed on paper**, not
  what any particular candidate actually has.
- Title inflation beyond the JD title level is forbidden. `acceptable_titles`
  must be drawn only from `preflight.acceptable_title_candidates` unless a
  stakeholder signal explicitly authorizes an alias.
- `title_strategy` MUST equal `peer_cv_shape_expectations.title_strategy`.
- Use only canonical enums (provided in payload).
- `audience_variants` keys MUST be a subset of
  `evaluator_coverage_target` and MUST NOT include inferred-only roles
  when `stakeholder_status != completed` — restrict to `recruiter` and
  `hiring_manager` in that case.
- `must_signal[]` / `should_signal[]` proof types MUST be a subset of
  `peer_document_expectations.proof_order[]`.
- `de_emphasize[]` MUST NOT target the top-two proof categories from
  `peer_document_expectations.proof_order[]`.
- `tone_profile` values are intensities in `[0.0, 1.0]`; they do not need to
  sum. Consistency with `peer_document_expectations.tone_posture.primary_tone`
  is required (table in payload).
- `credibility_markers[]` must be evaluator-derived concrete signals (e.g.
  "named production system serving real traffic", "named stakeholder scope
  across functions"). Generic phrases ("strong communicator", "team player",
  "rockstar", "ninja", "guru") are forbidden.
- No AI depth claim when `ai_intensity ∈ {none, adjacent}`.
- No CV prose. No headers. No bullets. No summaries.
- Unresolved is a valid first-class answer for individual fields; populate
  `unresolved_markers[]` and `rationale`.
- Every major decision must carry at least one evidence ref in
  `evidence[]`, cited by `source:<id>` or `artifact:<dotted-path>`.

### 15.3 Schema-repair retry contract

Exactly one repair retry, consistent with the existing parent-stage mechanism
(`_repair_prompt` in `presentation_contract.py`). Permitted repair reasons:

- `missing_evidence_ref`
- `enum_drift_title_strategy` | `enum_drift_proof_type` |
  `enum_drift_signal_category` | `enum_drift_risk_flag`
- `audience_variant_out_of_scope`
- `title_inflation`
- `section_id_leaked_into_tag`
- `tone_axis_out_of_range`

Repair prompt is the same LLM call with: the original prompt + the diff +
a normative sentence describing the violation + "Return valid JSON only; do
not add candidate-specific details; use only canonical enums."

### 15.4 Deterministic fallback (`_default_ideal_candidate_presentation_model`)

Implemented next to `_default_document_expectations` in
`src/preenrich/stages/presentation_contract.py`. Builds from:

- `preflight.role_family_identity_priors`
- `preflight.acceptable_title_candidates` (keeps only the JD title when
  uncertain)
- `preflight.signal_priors_by_role_family`
- `preflight.tone_profile_priors`
- a minimum audience-variant pair (recruiter + hiring_manager) populated from
  role-family defaults
- `proof_ladder[]` defaulted from 4.2.3's proof-category frequencies
- `credibility_markers[]` defaulted from role-family markers

Fallback marks `status = inferred_only`, `confidence.band ≤ medium`,
`defaults_applied[] = ["role_family_ideal_candidate_default"]`, and
`unresolved_markers[] = ["fail_open_role_family_ideal_candidate_defaults"]`.

## 16. Operational Catalogue

This section is explicitly **subdocument-scoped**, not stage-scoped.

### 16.1 Ownership

- **Owning stage:** `presentation_contract` (registered in
  `src/preenrich/stage_registry.py`, task type
  `preenrich.presentation_contract`, already wired).
- **Owning subdocument:** `ideal_candidate_presentation_model` (new), slot
  inside `PresentationContractDoc`.
- **Owning model:** `IdealCandidatePresentationModelDoc` in
  `src/preenrich/blueprint_models.py` (new).
- **Owning prompt:** `P-ideal-candidate@v1` registered in
  `PROMPT_VERSIONS["ideal_candidate"]` and built by `build_p_ideal_candidate`.
- **Owning validator:** `normalize_ideal_candidate_payload` +
  `_validate_ideal_candidate` in
  `src/preenrich/stages/presentation_contract.py`.
- **Owning fallback:** `_default_ideal_candidate_presentation_model` in the
  same stage file.

### 16.2 Prerequisite artifacts

Before the parent `presentation_contract` stage may synthesize this
subdocument, the run must have:

- `pre_enrichment.outputs.jd_facts` with status ∈ {completed, partial}
- `pre_enrichment.outputs.classification` completed
- `pre_enrichment.outputs.research_enrichment` with status ∈ {completed,
  partial, unresolved}
- `pre_enrichment.outputs.stakeholder_surface` with status ∈ {completed,
  inferred_only, no_research, unresolved}
- `pre_enrichment.outputs.pain_point_intelligence` with status ∈ {completed,
  partial, unresolved}

Hard-fail of any prerequisite is surfaced by the parent stage, not by 4.2.4.

### 16.3 Persistence map

| What                                      | Location                                                                                                             |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Full `PresentationContractDoc` including 4.2.4 | `presentation_contract` collection, unique filter `(job_id, input_snapshot_id)`                                       |
| Stage output ref                          | `level-2.pre_enrichment.outputs.presentation_contract`                                                               |
| Stage state                               | `level-2.pre_enrichment.stage_states.presentation_contract`                                                          |
| Compact snapshot projection               | `level-2.pre_enrichment.job_blueprint_snapshot.presentation_contract_compact.ideal_candidate`                        |
| Work item                                 | `work_items` collection, `task_type="preenrich.presentation_contract"` (shared with peers)                           |
| Run audit                                 | `preenrich_stage_runs` (shared with peers; one row per parent stage run; includes `trace_id` / `trace_url`)          |
| Job aggregate                             | `preenrich_job_runs.stage_status_map.presentation_contract`                                                          |
| Alerts                                    | `preenrich_alerts` (on parent-stage deadletter only; never on subdocument fail-open)                                 |

There is **no** separate `ideal_candidate_presentation_model` collection and
**no** separate `work_items` row.

### 16.4 Compact snapshot projection

Projected by `blueprint_assembly` into
`JobBlueprintSnapshot.presentation_contract_compact.ideal_candidate`:

```json
{
  "status": "...",
  "confidence_band": "...",
  "title_strategy": "...",
  "acceptable_titles_count": 2,
  "must_signal_count": 4,
  "should_signal_count": 3,
  "de_emphasize_count": 2,
  "proof_ladder_length": 4,
  "audience_variant_count": 3,
  "credibility_marker_count": 3,
  "risk_flag_count": 2,
  "defaults_applied_count": 0,
  "normalization_events_count": 1,
  "unresolved_markers_count": 0,
  "trace_ref": { "trace_id": "...", "trace_url": "..." }
}
```

No signal tag bodies, no framing rule strings, no rationale, no debug block.

### 16.5 Subdocument status vs parent status

Parent `PresentationContractDoc.status` resolution (already implemented) uses
the union of its subdocument statuses:

- any `failed_terminal` → parent `failed_terminal`
- any `partial` or `inferred_only` → parent `partial`
- any `unresolved` (and no `partial`/`inferred_only`) → parent `unresolved`
- all `completed` → parent `completed`

4.2.4's own `status` therefore directly feeds the parent's escalation
threshold. A `failed_terminal` in 4.2.4 causes the parent stage to fall back
to role-family defaults across ALL subdocuments (umbrella §8.2); it does not
deadletter the job, because `job_fail_policy="fail_open"` at the stage level.

### 16.6 Retry / repair semantics

- Parent stage `max_attempts = 3` (shared with 4.2.2).
- 4.2.4 adds a single schema-repair retry via the same
  `_repair_prompt` mechanism as 4.2.2 / 4.2.3. Repair attempts ≥ 2 are not
  permitted.
- On repair exhaustion: fail-open to `_default_ideal_candidate_presentation_model`
  with `status = inferred_only` and `defaults_applied[]` populated.
- On candidate-leakage trigger: offending field omitted, `status = partial`.
- On cross-validator invariant violation that cannot be repaired: parent
  stage re-runs all subdocuments with role-family defaults (umbrella
  fallback); 4.2.4 is marked `failed_terminal`.

### 16.7 Cache behavior

4.2.4 does **not** own a cache key. Inherits the parent
`presentation_contract` cache key, which includes
`PROMPT_VERSIONS["ideal_candidate"]`. Bumping `PROMPT_VERSIONS["ideal_candidate"]`
invalidates cached parent artifacts. No standalone `ideal_candidate_cache`
collection.

### 16.8 Heartbeat and operator expectations

- Parent stage heartbeat every `PREENRICH_STAGE_HEARTBEAT_SECONDS` (default
  60 s) via `StageWorker._heartbeat_loop`.
- The 4.2.4 LLM call must not hold CPU > 30 s between yield points
  (preflight, prompt build, LLM call, post-pass). The worker heartbeat
  renews the lease.
- Launcher-side operator heartbeat (§18) every 15–30 s during VPS runs,
  streaming Codex PID / stdout / stderr.
- Silence > 90 s is a stuck-run flag.

### 16.9 Feature flags affecting 4.2.4

- `presentation_contract_enabled()` — master for the parent stage; off
  disables all subdocuments.
- `presentation_contract_ideal_candidate_enabled()` — gates the LLM call
  for 4.2.4. When off, the parent stage always uses
  `_default_ideal_candidate_presentation_model`. Default: off at ship;
  default-on after SC gate.
- `presentation_contract_merged_prompt_enabled()` — when on, 4.2.4 hydrates
  from the merged prompt's `ideal_candidate_presentation_model` key. When
  off (default), the split `P-ideal-candidate@v1` path is used.
- `presentation_contract_compat_projection_enabled()` — keeps legacy
  downstream consumers working during rollout; does not affect 4.2.4
  synthesis.

### 16.10 Downstream consumers of `ideal_candidate_presentation_model`

- `presentation_contract` cross-validator (intra-stage consumer)
- 4.2.5 `experience_dimension_weights` (uses tone profile + signals as
  priors)
- 4.2.6 `truth_constrained_emphasis_rules` (turns `risk_flags[]` +
  `de_emphasize[]` into enforceable `Rule[]`)
- `blueprint_assembly.snapshot` (compact projection, §16.4)
- 4.3.x candidate-aware CV generation (consumes `visible_identity`,
  `acceptable_titles`, `title_strategy`, `proof_ladder`, `tone_profile`,
  `credibility_markers`, `audience_variants`)
- reviewer UI ("what the ideal candidate should look like on paper" panel)

### 16.11 Rollback

- toggle `presentation_contract_ideal_candidate_enabled()` to `false`:
  parent stage synthesizes the subdocument deterministically from role-
  family priors only.
- toggle `presentation_contract_enabled()` to `false`: downstream consumers
  fall back to legacy `cv_guidelines`; existing `presentation_contract`
  collection documents remain inert.
- no schema migration on rollback; no data loss.

### 16.12 Why no separate cache keys / trace refs

A separate cache key would let 4.2.4 drift from its peers when an upstream
artifact changes. A separate trace ref would fragment the one-click-from-
Mongo-to-Langfuse operator path. Both are actively undesirable.

## 17. Langfuse Tracing Contract

Inherits the 4.2 umbrella contract (§8.8) and the `presentation_contract`
stage-level contract in 4.2.2 §9.5. This section is normative for the
subdocument span.

### 17.1 Canonical parent and child spans

- trace: `scout.preenrich.run` (unchanged)
- job span: `scout.preenrich.job` (unchanged)
- parent stage span: `scout.preenrich.presentation_contract`
- preflight span: `scout.preenrich.presentation_contract.preflight`
  (shared; 4.2.4 contributes `role_family_identity_priors`,
  `acceptable_title_candidates`, `signal_priors_by_role_family`,
  `tone_profile_priors`, `audience_variant_candidates` to its output
  metadata)
- **4.2.4 substage span:** `scout.preenrich.presentation_contract.ideal_candidate`

Optional child spans under the ideal_candidate substage:

- `scout.preenrich.presentation_contract.ideal_candidate.prompt_build`
- `scout.preenrich.presentation_contract.ideal_candidate.llm_call.primary`
  (+ `.llm_call.fallback` if the parent's fallback transport fires)
- `scout.preenrich.presentation_contract.ideal_candidate.post_pass`
- `scout.preenrich.presentation_contract.ideal_candidate.schema_repair`
  (only when §15.3 fires)
- `scout.preenrich.presentation_contract.ideal_candidate.cross_validate`
  (shared cross-validator pass; contribution span)

No per-signal-tag, per-marker, per-variant spans. Cardinality is expressed
as metadata, never in span names. Repair attempts bounded at 1, hence
bounded spans.

### 17.2 Events

- `scout.preenrich.presentation_contract.ideal_candidate.fail_open`
- `scout.preenrich.presentation_contract.consistency.ideal_candidate`
  (emitted by the cross-validator when it suppresses / downgrades /
  overrides a field; metadata includes `conflict_source`,
  `conflict_target`, `resolution ∈ {suppressed, downgraded,
  overridden_by_defaults, retained}`)

Cache events are owned by the parent span
(`scout.preenrich.presentation_contract.cache.hit|miss`). 4.2.4 does not
emit its own cache events.

### 17.3 Required canonical metadata (every span and event)

Identical to the 4.2 umbrella canonical payload:

`job_id`, `level2_job_id`, `correlation_id`, `langfuse_session_id`,
`run_id`, `worker_id`, `task_type`, `stage_name`, `attempt_count`,
`attempt_token`, `input_snapshot_id`, `jd_checksum`, `lifecycle_before`,
`lifecycle_after`, `work_item_id`.

### 17.4 Stage-specific metadata on the ideal_candidate substage span

On end:

- `status ∈ {completed, partial, inferred_only, unresolved,
  failed_terminal}`
- `title_strategy` (canonical enum value)
- `acceptable_titles_count`
- `must_signal_count`, `should_signal_count`, `de_emphasize_count`
- `proof_ladder_length`
- `audience_variant_count` (non-null entries only)
- `credibility_marker_count`
- `risk_flag_count`
- `tone_profile_axis_max` (float, max intensity across all axes)
- `tone_profile_primary_axis` (axis name with max intensity)
- `defaults_applied_count`
- `normalization_events_count`
- `rejected_output_count`
- `cross_validator_violations_count`
- `confidence.band`, `confidence.score`
- `prompt_version` = `PROMPT_VERSIONS["ideal_candidate"]`
- `prompt_git_sha`
- `llm_call_schema_valid: bool`
- `fail_open_reason` when status ∈ {partial, inferred_only, unresolved,
  failed_terminal}: one of
  - `thin_stakeholder_surface`
  - `thin_proof_map`
  - `partial_role_profile`
  - `schema_repair_exhausted`
  - `llm_terminal_failure`
  - `cross_invariant_violation`
  - `candidate_leakage_detected`
  - `title_inflation_detected`
  - `defaults_only`

Boolean alert helpers (used by monitoring):

- `title_strategy_matches_peer_cv_shape: bool`
- `proof_ladder_enum_valid: bool`
- `audience_variants_in_scope: bool`
- `candidate_leakage_detected: bool` (equivalent to
  `rejected_output_count > 0 for candidate_leakage` — surfaced separately so
  alerts don't have to parse bodies)

### 17.5 Outcome classifications

`llm_call.*` spans carry the same transport outcome classification as the
rest of the preenrich stage family: `success | unsupported_transport |
error_missing_binary | error_timeout | error_subprocess | error_no_json |
error_schema | error_exception`. `schema_valid: bool` is always set.

### 17.6 Retry / repair metadata

`schema_repair` child span metadata:

- `repair_reason ∈ {missing_evidence_ref, enum_drift_title_strategy,
  enum_drift_proof_type, enum_drift_signal_category, enum_drift_risk_flag,
  audience_variant_out_of_scope, title_inflation,
  section_id_leaked_into_tag, tone_axis_out_of_range}`
- `repair_attempt` (1)
- `repaired_fields: list[str]`
- `pre_repair_schema_valid: bool`
- `post_repair_schema_valid: bool`

### 17.7 Cross-validator metadata

`cross_validate` contribution span metadata (authored by the parent stage
on behalf of 4.2.4):

- `invariants_checked_count`
- `invariants_violated_count`
- per-invariant ids when violated (e.g. `I1`, `I3`, `I7`)
- `resolution ∈ {passed, downgraded, suppressed, overridden_by_defaults,
  parent_fallback}`

### 17.8 Trace refs into Mongo run records

- `preenrich_stage_runs[trace_id, trace_url]` — parent stage row; 4.2.4
  does not write its own row.
- `preenrich_job_runs[stage_status_map.presentation_contract]` — aggregate
  job-level; 4.2.4 contributes through the parent.
- `pre_enrichment.stage_states.presentation_contract.trace_id/url` — parent
  state; reached via the level-2 UI.
- `pre_enrichment.outputs.presentation_contract.trace_ref` — projection
  only.
- `JobBlueprintSnapshot.presentation_contract_compact.ideal_candidate.
  trace_ref` — compact snapshot reference; points back to the parent trace.

An operator opening a level-2 job in the UI reaches the Langfuse parent
trace in one click and the `ideal_candidate` substage in one more click.

### 17.9 Forbidden in Langfuse

- full signal-tag bodies, full framing rule strings, full rationale
  paragraphs
- full credibility marker descriptions, full risk flag descriptions
- full `debug_context` payloads
- raw LLM prompt / response bodies unless `_sanitize_langfuse_payload` is
  applied and `LANGFUSE_CAPTURE_FULL_PROMPTS=true`
- first-person pronouns, candidate names, candidate URLs

### 17.10 What may live only in `debug_context`

- raw LLM response (pre-normalization) per prompt call
- normalization diffs
- rejected-output path + reason pairs
- cross-validator per-invariant diffs
- defaults-applied ids with per-field provenance

### 17.11 Cardinality and naming

- 4.2.4's substage span name is fixed: `...presentation_contract.ideal_candidate`.
- Optional child spans under it are a small closed set (§17.1).
- Repair attempts bounded at 1.
- No per-signal-tag, per-marker, per-variant spans.
- Counts are emitted as metadata fields only.

### 17.12 Operator debug checklist (normative)

An operator must be able to diagnose each of these from Mongo → trace in
under two minutes:

- slow subdocument synthesis —
  `ideal_candidate.llm_call.primary.duration_ms`
- malformed LLM output — `ideal_candidate.schema_repair.repair_reason`
- title-strategy drift — `title_strategy_matches_peer_cv_shape = false`
- candidate leakage — `candidate_leakage_detected = true`
- audience-variant out-of-scope — `audience_variants_in_scope = false`
- defaulted-only run — `status = inferred_only` AND
  `defaults_applied_count > 0`
- cross-invariant failure — `consistency.ideal_candidate` event with
  `resolution = parent_fallback`

## 18. Tests and Evals

Tests live under `tests/unit/preenrich/` mirroring 4.2.2 conventions.

### 18.1 Schema / unit tests

`tests/unit/preenrich/test_ideal_candidate_schema.py`:

- `IdealCandidatePresentationModelDoc` accepts canonical output (fixture
  based on §10.1).
- `extra="forbid"` rejects unknown top-level keys.
- enum rejection for each of: `title_strategy`, `signal_category`,
  `proof_ladder_category`, `proof_type`, `credibility_marker_type`,
  `risk_flag_type`, `audience_variant_key`.
- tone-axis clamp: values outside `[0.0, 1.0]` clamped; event logged.
- `acceptable_titles[]` length bounded to 1..4.
- `must_signal[]` length bounded to 2..6.
- `proof_ladder[]` length bounded to 3..6.
- confidence band clamp when stakeholder status ∈ {inferred_only,
  no_research, unresolved}.

### 18.2 Normalizer tests

`tests/unit/preenrich/test_ideal_candidate_ingress.py`:

- alias map (`titles` → `acceptable_titles`, `tone` → `tone_profile`,
  `evaluator_variants` → `audience_variants`, `proof_chain` →
  `proof_ladder`) mapped correctly.
- signal-tag string coerced to structured `SignalTag` with
  deterministic category/proof_type enrichment.
- audience-variant key map-vs-list coercion.
- unknown-but-grounded fields retained in
  `debug_context.richer_output_retained[]`.
- candidate-leakage detector catches first-person, candidate companies,
  candidate tenure tokens.
- section-id leakage into tag strings (`tag="summary"`) rejected.

### 18.3 Invariant tests (cross-subdocument)

`tests/unit/preenrich/test_ideal_candidate_invariants.py`:

- I1 (`title_strategy` match with 4.2.2): violation triggers cross-
  validator event.
- I2 (`acceptable_titles` bounded by preflight candidates): violation
  triggers repair → defaults.
- I3/I4 (enum validity): triggers repair.
- I5 (`must_signal.proof_type ⊆ document_expectations.proof_order`):
  triggers repair.
- I6 (`de_emphasize` does not target top-two proof order): rejected.
- I7 (`tone_profile` vs `tone_posture.primary_tone`): violation triggers
  clamp or default.
- I8 (`audience_variants` keys ⊆ `evaluator_coverage_target`): rejected.
- I9 (dimension-scoped tags reference `ExperienceDimension`): rejected.
- I10 (`credibility_markers` cardinality floor).
- I11 (title inflation risk flag required).
- I12 (no tag equals a section id).

Each invariant has at least one positive test and one negative test.

### 18.4 Title-safety tests

- JD title "Lead Engineer" → `acceptable_titles[]` must not contain
  "Principal" or "VP".
- JD title "Senior Engineer" + `stakeholder_surface.title_safety_override =
  staff_acceptable` → "Staff Engineer" may appear.
- `title_strategy = exact_match` when JD title is ambiguous per
  `jd_facts.identity_signals` → rejected; falls back to `closest_truthful`.

### 18.5 Proof-ladder enum tests

- every `proof_ladder[].proof_type` in `ProofTypeEnum` (imported from
  4.2.3).
- new proof types NOT defined in 4.2.3 are rejected with
  `enum_drift_proof_type`.

### 18.6 Candidate-leakage rejection tests

- first-person pronouns in any string field → rejected, `partial`.
- candidate-company proper noun (mocked) in `framing_rules[]` → rejected.
- exact numeric achievement ("40% YoY") not in JD → rejected.
- "rockstar" / "ninja" / "guru" / "10x" tokens → rejected.

### 18.7 Audience-variant consistency tests

- `stakeholder_surface.status = inferred_only` → only `recruiter` and
  `hiring_manager` variants populated; `confidence.band ≤ medium`.
- `evaluator_coverage_target = ["recruiter", "hiring_manager",
  "executive_sponsor"]` → `peer_reviewer` variant absent.
- `audience_variants.hiring_manager.must_see[]` ⊆ parent `must_signal ∪
  should_signal ∪ de_emphasize`.

### 18.8 Partial-research fail-open tests

- `research_enrichment.status = partial` → `credibility_markers[]` from
  role-family defaults; `defaults_applied[]` populated;
  `unresolved_markers[] += ["partial_role_profile"]`; `status = partial`.
- `stakeholder_surface.status = no_research` → audience_variants limited
  to recruiter + hiring_manager, confidence capped.
- `pain_point_intelligence.proof_map[]` empty → `proof_ladder[]` from
  role-family priors; `status = partial` or `inferred_only`.

### 18.9 Trace emission tests

Using a `FakeTracer`:

- `scout.preenrich.presentation_contract.ideal_candidate` span emitted
  exactly once per run with required §17.4 metadata keys.
- `ideal_candidate.schema_repair` span emitted iff repair fired.
- `consistency.ideal_candidate` event emitted when the cross-validator
  suppresses / downgrades / overrides.
- no forbidden keys (full bodies, first-person strings) leak into span
  metadata (grep assertion on serialized payload).

### 18.10 Snapshot projection tests

- compact snapshot contains all §16.4 keys and no full bodies.
- snapshot `trace_ref` matches the parent stage's `trace_id` / `trace_url`.

### 18.11 Same-run `presentation_contract` compatibility tests

- happy path: all upstreams completed → parent stage emits 4.2.2, 4.2.4
  (and 4.2.5/4.2.6 when shipped) with `status = completed` and all
  invariants pass.
- 4.2.4 terminal subdocument failure → parent stage falls back all four
  subdocuments to role-family defaults; `PresentationContractDoc.status =
  partial`.
- merged-prompt mode: parse-time split hydrates the 4.2.4 subdocument
  correctly; span `ideal_candidate` is still emitted per §17.1.

### 18.12 Regression corpus

- 30 curated level-2 jobs under `tests/data/ideal_candidate/corpus/`
  (10 IC, 10 EM/Director, 10 Head/VP; mixed ATS vendor; mixed research
  completeness).
- golden outputs under `tests/data/ideal_candidate/golden/` with tolerance
  for ordering and signal-tag string Jaccard ≥ 0.9.
- CI mode: mocked LLM returning recorded response; diff non-deterministic
  fields separately.

### 18.13 Reviewer rubric (evals)

Scored per job, recorded under `reports/ideal_candidate_eval/`:

- **identity-clarity (1–5):** 5 = "a reader could unambiguously describe
  how this person should look on paper from these fields alone"; 1 =
  "generic".
- **title-safety (1–5):** 5 = "no plausible reviewer would flag these
  titles as inflated"; 1 = "overt inflation".
- **signal specificity (1–5):** 5 = "`must_signal[]` is concrete,
  evaluator-justified, and hard to substitute"; 1 = "buzzword soup".
- **credibility concreteness (1–5):** 5 = "named and observable";
  1 = "generic communicator / team player".
- **audience variant usefulness (1–5):** 5 = "the recruiter / hiring
  manager / peer framings diverge meaningfully where evidence supports";
  1 = "identical across variants".
- **anti-hallucination posture (1–5):** 5 = "no overclaim, no candidate
  leakage"; 1 = "multiple inflation / leakage events".
- **JD-only graceful degradation:** for research-thin jobs, median
  identity-clarity ≥ 3.5 with `fail_open_reason = thin_stakeholder_surface`
  or `partial_role_profile`.

### 18.14 Live smoke tests

- `scripts/smoke_ideal_candidate_subdocument.py` — loads `.env` from
  Python, fetches one job by `_id`, runs the parent
  `PresentationContractStage` locally against live Codex/LLM with
  `presentation_contract_ideal_candidate_enabled()=true`, validates the
  4.2.4 subdocument, prints heartbeat every 15 s.

## 19. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This plan validates 4.2.4 through the real `presentation_contract`
stage on VPS. It does NOT invent a standalone
`preenrich.ideal_candidate_presentation_model` stage.

### 19.1 Local prerequisite tests before touching VPS

- `pytest tests/unit/preenrich -n auto -k "ideal_candidate"` clean.
- `pytest tests/unit/preenrich/test_presentation_contract_stage.py -x`
  clean (parent stage contract).
- `python -u -m scripts.preenrich_dry_run --stage presentation_contract
  --job <level2_id> --mock-llm` clean.
- compact snapshot projection test green.
- Langfuse sanitizer test green.

### 19.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path.
- `grep -n "ideal_candidate" /root/scout-cron/src/preenrich/blueprint_models.py`
  to confirm `IdealCandidatePresentationModelDoc` is present.
- `grep -n "ideal_candidate"
  /root/scout-cron/src/preenrich/stages/presentation_contract.py`
  to confirm the synthesis path is wired.
- `grep -n "ideal_candidate" /root/scout-cron/src/preenrich/blueprint_prompts.py`
  to confirm `build_p_ideal_candidate` and
  `PROMPT_VERSIONS["ideal_candidate"]` are present.
- `grep -n "presentation_contract_ideal_candidate_enabled"
  /root/scout-cron/src/preenrich/blueprint_config.py` to confirm the flag.
- `.venv` resolves the deployed Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`.
- deployment is file-synced, not git-pulled — check sync markers, do not
  `git status`.

### 19.3 Target job selection

- pick a real level-2 job with `pre_enrichment.outputs` for all of
  `jd_facts`, `classification`, `research_enrichment`, `stakeholder_surface`,
  `pain_point_intelligence` at `status ∈ {completed, partial}` as
  appropriate.
- prefer a mid-seniority IC or EM role with resolved company identity
  (`research_enrichment.status = completed`) and a real stakeholder
  (`stakeholder_surface.status = completed`) for the main smoke.
- record `_id`, `jd_checksum`, `input_snapshot_id`, `research_input_hash`,
  `pain_input_hash`.
- pick a second job with `stakeholder_surface.status = inferred_only` or
  `research_enrichment.status = partial` to exercise fail-open.

### 19.4 Upstream artifact recovery

If `stage_states` show stale entries:

1. verify `pre_enrichment.outputs.{jd_facts, classification,
   research_enrichment, stakeholder_surface, pain_point_intelligence}`
   exist.
2. recompute the current `input_snapshot_id`:
   `/root/scout-cron/.venv/bin/python -u scripts/recompute_snapshot_id.py
   --job <_id>`.
3. only if necessary, re-enqueue prerequisites via
   `scripts/enqueue_stage.py` — never touch `work_items` directly.

### 19.5 Single-stage run path (fast path)

Preferred. A wrapper script in
`/tmp/run_presentation_contract_<job>.py`:

- loads `.env` in Python with explicit path:
  `from dotenv import load_dotenv; load_dotenv("/root/scout-cron/.env")`.
- reads `MONGODB_URI`.
- builds `StageContext` via `build_stage_context_for_job`.
- forces `presentation_contract_ideal_candidate_enabled()=True` via env
  override for the scope of the run.
- runs `PresentationContractStage().run(ctx)` directly.
- prints a heartbeat line every 15 s during the LLM call chain:
  wall clock, elapsed, last substage, Codex PID, Codex stdout/stderr tail.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_presentation_contract_<job>.py \
  > /tmp/presentation_contract_<job>.log 2>&1 &
```

### 19.6 Full-chain path (fallback)

Only when `StageContext` construction drifts:

- enqueue `work_items` for the full prerequisite chain.
- start `preenrich_worker_runner.py` with
  `PREENRICH_STAGE_ALLOWLIST="presentation_contract"` (plus any missing
  prerequisite stages as the DAG requires).
- same `.venv` / `python -u` / Python-side `.env` / `MONGODB_URI`
  discipline.
- same operator heartbeat.

### 19.7 Required launcher behavior

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

### 19.8 Heartbeat requirements

- stage-level heartbeat every 15–30 s from the wrapper.
- lease heartbeat every 60 s by the worker.
- Codex PID / stdout / stderr tail on every heartbeat when the LLM is
  live.
- silence > 90 s is a stuck-run flag.

### 19.9 Expected Mongo writes

On success:

- `presentation_contract` collection: new doc keyed by
  `(job_id, input_snapshot_id)` containing a populated
  `ideal_candidate_presentation_model` slot.
- `level-2.pre_enrichment.outputs.presentation_contract.ideal_candidate_presentation_model`
  populated (projection).
- `level-2.pre_enrichment.stage_states.presentation_contract.status =
  completed`, `trace_id`, `trace_url` set.
- `preenrich_stage_runs`: one row for the parent stage with
  `status=completed`, `trace_id`, `trace_url`, `provider_used`,
  `model_used`, `prompt_version` (parent), `tokens_input`,
  `tokens_output`, `cost_usd`.
- `preenrich_job_runs`: aggregate updated; `stage_status_map.presentation_contract
  = completed`.
- `work_items`: this row `status=completed`.
- `JobBlueprintSnapshot.presentation_contract_compact.ideal_candidate`:
  populated per §16.4.

### 19.10 Expected Langfuse traces

In the same trace (`scout.preenrich.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- `scout.preenrich.presentation_contract` stage span with full peer
  metadata.
- `scout.preenrich.presentation_contract.preflight`.
- `scout.preenrich.presentation_contract.ideal_candidate` substage span
  with full §17.4 metadata.
- optional children:
  `ideal_candidate.prompt_build`, `ideal_candidate.llm_call.primary`,
  `ideal_candidate.post_pass`, `ideal_candidate.schema_repair` (iff
  repair fired), `ideal_candidate.cross_validate`.
- `consistency.ideal_candidate` event (iff cross-validator acted).
- canonical lifecycle events (`claim`, `enqueue_next`).

### 19.11 Expected `preenrich_stage_runs` / `preenrich_job_runs`

- `stage_runs` row (parent) has `trace_id`, `trace_url`, and
  `fail_open_reason` iff non-completed.
- `job_runs` aggregate has updated
  `stage_status_map.presentation_contract`.

### 19.12 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/presentation_contract_<job>.log`.
- `ps -p <codex_pid> -o pid,etime,stat,cmd`.
- check `/tmp/codex-work-presentation-contract-<job>/stdout.log` touch
  ctime.
- inspect Mongo stage state:
  `level-2.pre_enrichment.stage_states.presentation_contract.lease_expires_at`.
- if lease is expiring and no progress, kill the launcher; do not restart
  until the prior PID is confirmed gone. Silence is not progress.

### 19.13 Acceptance criteria

- log ends with
  `PRESENTATION_CONTRACT_RUN_OK job=<id> status=<status>
  ideal_candidate=<status> trace=<url>`.
- Mongo writes match §19.9.
- Langfuse trace matches §19.10, including the `ideal_candidate` substage
  metadata (§17.4).
- `IdealCandidatePresentationModelDoc` validates for the persisted doc.
- spot-check: no candidate leakage; `title_strategy` matches
  `cv_shape_expectations.title_strategy`; `proof_ladder[]` enum-clean;
  `audience_variants` ⊆ `evaluator_coverage_target`.
- fail-open run (research-thin or stakeholder-thin) returns
  `status=partial` or `inferred_only` with an appropriate
  `fail_open_reason`; parent stage does not deadletter.

### 19.14 Artifact / log / report capture

Create `reports/presentation-contract/<job_id>/ideal_candidate/`
containing:

- `run.log` — full stdout/stderr.
- `subdocument_output.json` — the emitted
  `IdealCandidatePresentationModelDoc`.
- `parent_stage_output.json` — the full `PresentationContractDoc`.
- `trace_url.txt` — Langfuse URL.
- `stage_runs_row.json` — `preenrich_stage_runs` row for the parent
  stage.
- `mongo_writes.md` — human summary of §19.9 checks.
- `acceptance.md` — pass/fail list for §19.13.

## 20. Rollout, Feature Flags, Migration

### 20.1 Rollout order

1. Ship `IdealCandidatePresentationModelDoc`, the normalizer, the prompt
   builder, the fallback, the cross-validator extensions, and the snapshot
   projection behind `presentation_contract_ideal_candidate_enabled()` =
   **off**. Deterministic fallback synthesizes the subdocument so downstream
   consumers can rely on presence.
2. Unit + invariant + normalizer + snapshot tests green (§18.1–18.11).
3. Flip the flag on for a curated 30-job corpus in staging; collect eval
   metrics (§18.13). Gate default-on on SC1–SC7.
4. Default-on in production behind
   `presentation_contract_ideal_candidate_enabled() = true`; keep
   `presentation_contract_compat_projection_enabled()` on so legacy
   downstream consumers are unaffected.
5. Flip `presentation_contract_compat_projection_enabled()` off only after
   4.3.x downstream consumers have migrated.

### 20.2 Migration path

- no backfill of historical jobs at ship; the subdocument fills lazily on
  the next `presentation_contract` run for each job.
- jobs without `ideal_candidate_presentation_model` continue to read from
  legacy `cv_guidelines` via compat projection until 4.3.x migrates.
- `blueprint_assembly` always reads
  `pre_enrichment.outputs.presentation_contract.ideal_candidate_presentation_model`
  first; falls back to legacy synthesis only when the slot is absent.

### 20.3 Rollback

- toggle `presentation_contract_ideal_candidate_enabled()` = false;
  deterministic fallback takes over immediately; no data loss.
- toggle `presentation_contract_enabled()` = false to disable the whole
  parent stage; downstream reverts to `cv_guidelines`.
- no schema migration on rollback.

### 20.4 Production readiness checklist

- [ ] `IdealCandidatePresentationModelDoc` and sub-models + enums in
      `blueprint_models.py` with unit tests
- [ ] `normalize_ideal_candidate_payload` at module scope + tests
- [ ] `build_p_ideal_candidate` + `PROMPT_VERSIONS["ideal_candidate"]`
- [ ] `_ideal_candidate_priors`, `_default_ideal_candidate_presentation_model`,
      `_validate_ideal_candidate` in
      `src/preenrich/stages/presentation_contract.py`
- [ ] `PresentationContractStage.run` wires the split and merged paths;
      `PresentationContractDoc` carries the new slot
- [ ] compact snapshot projection in
      `src/preenrich/stages/blueprint_assembly.py`
      (`presentation_contract_compact.ideal_candidate`)
- [ ] cross-validator invariants I1–I12 enforced (shared with 4.2.2)
- [ ] debug_context persisted, snapshot-excluded, size-capped at 16 KB
- [ ] Langfuse substage emission via `ctx.tracer.start_substage_span(...,
      "ideal_candidate", ...)` and canonical metadata
- [ ] eval directory scaffolded under `evals/ideal_candidate_4_2_4/`
- [ ] VPS smoke script `scripts/smoke_ideal_candidate_subdocument.py`
- [ ] docs updated: `architecture.md`, `missing.md`,
      optional decision doc under `docs/current/decisions/`

## 21. Open Questions

- **Q1.** Should `credibility_markers[]` be promoted to a shared sub-model
  with 4.2.3's `proof_map[].preferred_evidence_shape`? Recommend: no at
  ship; revisit after 100-job bench.
- **Q2.** Should `tone_profile` sum-constraint be added (e.g. sum ≤ 4.0)?
  Recommend: no, intensities are not distributions; cap axis max at 1.0
  and let total float.
- **Q3.** Should `acceptable_titles[]` carry a `title_safety_score` per
  entry? Defer until 4.3.2 `HeaderIdentity` needs it.
- **Q4.** Should 4.2.4 be allowed to author `allowed_if_evidenced` Rule
  entries directly (shortcutting 4.2.6)? Recommend: no; keeps peer
  boundaries clean.
- **Q5.** Should `audience_variants[<role>].must_see[]` reference
  `DocumentSectionIdEnum` values instead of `SignalTag.tag`? Recommend:
  no at ship; section-level placement belongs to 4.2.2.
- **Q6.** Should `visible_identity` carry a canonical archetype enum
  (mirroring `CandidateArchetype`)? Recommend: preserve free-text with
  bounded length for now; revisit if reviewer usefulness plateaus.

## 22. Primary Source Surfaces

- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `plans/brainstorming-new-cv-v2.md`
- `src/preenrich/stages/presentation_contract.py`
- `src/preenrich/stages/jd_facts.py`
- `src/preenrich/stages/pain_point_intelligence.py`
- `src/preenrich/stages/stakeholder_surface.py`
- `src/preenrich/blueprint_models.py` (`ConfidenceDoc`, `EvidenceEntry`,
  `PromptMetadata`, `PresentationContractDoc`, `DocumentExpectationsDoc`,
  `CvShapeExpectationsDoc`, normalizers)
- `src/preenrich/blueprint_prompts.py` (`PROMPT_VERSIONS`, existing
  `build_p_document_expectations`, `build_p_cv_shape_expectations`,
  `build_p_document_and_cv_shape`)
- `src/preenrich/blueprint_config.py` (feature flags)
- `src/preenrich/stage_registry.py`
- `src/preenrich/stage_worker.py`
- `src/pipeline/tracing.py`
- `src/layer1_4/claude_jd_extractor.py` (`IdealCandidateProfileModel`,
  `CandidateArchetype`)
- `src/layer6_v2/prompts/grading_rubric.py`
- `docs/current/cv-generation-guide.md`
- `docs/current/operational-development-manual.md`
- `docs/current/architecture.md`
- `AGENTS.md`

## 23. Implementation Targets

- new `IdealCandidatePresentationModelDoc`, `SignalTag`, `ProofLadderStep`,
  `CredibilityMarker`, `RiskFlag`, `AudienceVariant`,
  `IdealCandidateDebug` sub-models in `src/preenrich/blueprint_models.py`.
- new `AudienceVariantKey`, `SignalCategoryEnum`, `ProofLadderCategoryEnum`,
  `CredibilityMarkerTypeEnum`, `RiskFlagTypeEnum` enums in
  `src/preenrich/blueprint_models.py`.
- import `ProofTypeEnum` from `pain_point_intelligence` enums module;
  import `DocumentSectionIdEnum` and `TitleStrategyEnum` from
  `CvShapeExpectationsDoc` context; import `ExperienceDimension` when
  4.2.5 ships.
- extend `PresentationContractDoc` with
  `ideal_candidate_presentation_model: IdealCandidatePresentationModelDoc |
  None` field (consistent with the 4.2.2-first guarded pattern).
- new `normalize_ideal_candidate_payload` in
  `src/preenrich/blueprint_models.py` alongside existing normalizers.
- new `build_p_ideal_candidate` in
  `src/preenrich/blueprint_prompts.py` with `PROMPT_VERSIONS["ideal_candidate"]
  = "P-ideal-candidate@v1"`.
- new `_ideal_candidate_priors`, `_default_ideal_candidate_presentation_model`,
  `_validate_ideal_candidate` in
  `src/preenrich/stages/presentation_contract.py`.
- extend `PresentationContractStage.run` to synthesize 4.2.4 after
  `cv_shape_expectations` in split-prompt mode and to parse the merged
  prompt payload in merged-prompt mode; emit the substage span
  (`scout.preenrich.presentation_contract.ideal_candidate`) with §17.4
  metadata.
- new feature flag
  `presentation_contract_ideal_candidate_enabled()` in
  `src/preenrich/blueprint_config.py`.
- extend the cross-validator pass to enforce invariants I1–I12.
- update `src/preenrich/stages/blueprint_assembly.py` to project
  `JobBlueprintSnapshot.presentation_contract_compact.ideal_candidate`.
- new tests under `tests/unit/preenrich/test_ideal_candidate_schema.py`,
  `test_ideal_candidate_ingress.py`, `test_ideal_candidate_invariants.py`,
  and `tests/data/ideal_candidate/`.
- new `scripts/smoke_ideal_candidate_subdocument.py` (local).
- new `scripts/vps_run_presentation_contract.py` (VPS wrapper template;
  shared with 4.2.2).
- update `docs/current/architecture.md` "Iteration 4.2.4" section.
- update `docs/current/missing.md`.
