# Iteration 4.3.3 Plan: CV Pattern Selection And Evidence Mapping

## 1. Executive Summary

Once the header blueprint (4.3.2) freezes identity and exposes its
bounded candidate pools, the next question is structural: *which three
CV patterns best fit this job, and for each, which master-CV roles,
projects, achievements, and variants should the candidate lead with?*
Today Layer 6 V2 has a single implicit pattern — use all roles, generate
bullets per role, stitch, grade, improve — and the 4.2
`presentation_contract` describes document shape but not which patterns
to instantiate.

Iteration 4.3.3 is the explicit, candidate-aware reasoning stage that
picks **exactly three** ideal CV patterns implied by the
`presentation_contract`, the 4.3.1 master-CV blueprint, and the 4.3.2
header blueprint, and binds each pattern to a concrete, evidence-
grounded `evidence_map` that the 4.3.4 multi-draft assembly consumes
verbatim. The stage is structure-first: for each pattern it emits why
the pattern fits the job, which roles and projects lead, which
achievements and variants anchor each section, which header pool
fragments are picked, and what dimension weighting the pattern uses.

4.3.3 is a **picker**, not a pool maker. It selects, ranks, swaps, and
clamps — but it never grows an upstream pool, never invents evidence,
and never moves the title or AI/leadership bands beyond what 4.3.2 and
master-CV permit.

After 4.3.3, three diverse, defensible, evidence-bound patterns exist
— not three variations of the same assembly, and not three
hallucinations. Every pattern's evidence map is provable against
master-CV, every pool pick is provable against 4.3.2, and every
weighting override is provable against 4.2.5.

Operational discipline is inherited from 4.3 umbrella:

- **Mongo is the control plane.** `work_items`,
  `cv_assembly.stage_states`, `cv_assembly_stage_runs`, and
  `cv_assembly_job_runs` drive execution.
- **Langfuse is the observability sink.** Stage span
  `scout.cv.pattern_selection` with substep spans (§17) carries
  metadata-first payloads. Full evidence-map bodies stay in Mongo.
- **VPS validation** (§18) runs the stage end-to-end on a real
  `cv_ready` `level-2` job before default-on rollout.

## 2. Mission

Produce exactly three candidate-aware CV patterns per job, each
anchored to a concrete master-CV evidence map and to picks from the
fixed 4.3.2 header pools, with explicit rationales rooted in the job's
presentation contract and stakeholder surface, so the three downstream
drafts exercise meaningfully different framings while staying
truthful, identity-stable, and within frozen pool bounds.

## 3. Objectives

- **O1.** Produce a typed, enum-bounded `PatternSelectionDoc` with
  exactly three patterns per job, each carrying a deterministic
  `pattern_signature`, an `evidence_map`, and per-pattern picks from
  the 4.3.2 header blueprint pools.
- **O2.** Define and enforce a **pool-consumption contract** with
  4.3.2 (§10) so 4.3.3 may pick from but never grow upstream pools,
  and so picks always honor `viability_bands.minimum_viable_truthful_header`
  must-include floors and `viability_bands.strong_competitive_header`
  ceilings.
- **O3.** Run a **deterministic preflight** (§11) that builds the
  candidate evidence pool from master-CV achievements and ranks them
  by an executable salience formula seeded from 4.2.3 `proof_map[]`,
  4.2.5 `overall_weights`, 4.3.2 viability bands, and 4.3.1
  achievement metadata bands. The LLM picks and rationalizes from
  this pool; it never searches master-CV free-form.
- **O4.** Ship a **byte-deterministic** `pattern_signature` rule
  (§12) so two patterns with the same lead role, goal override,
  weights, and achievement set always produce the same hash — and so
  pattern de-duplication is provably stable.
- **O5.** Ship a shared **`pattern_validator`** library (§13) with
  modes `selection` and `draft_consumption`, allowed deterministic
  repair actions (`drop_pattern`, `swap_to_default`, `clamp_band`,
  `prune_to_pool`, `clamp_weight_override`), one-pass bound, no LLM
  in repair, byte-deterministic guarantees, asserted by eval.
- **O6.** Define an explicit **downstream-consumer contract** (§14)
  for 4.3.4 (and 4.3.5's synthesis) so consumers know which pattern
  fields are authoritative and which are advisory.
- **O7.** Define **fail-open** rules (§15) bounded to swapping a
  pattern for a role-family conservative default and degrading
  confidence; **fail-closed** rules (§15) bounded to evidence
  resolution failures, identity drift, AI/leadership-band climbing,
  and pool-violation patterns.
- **O8.** Emit Langfuse traces (§17) that let an operator diagnose
  pool insufficiency, default swaps, validator repairs, diversity
  failures, and degraded patterns in under two minutes from Mongo
  → trace.
- **O9.** Validate end-to-end on the VPS (§18) on a real `cv_ready`
  job before default-on rollout.

## 4. Success Criteria

4.3.3 is done when, for a representative 20-case eval corpus
(§16) and a 50-job staging soak:

- **SC1.** Every `cv_assembled_candidate`-eligible job has exactly
  three entries in `cv_assembly.pattern_selection.patterns[]`, each
  with a distinct `pattern_signature` and a distinct `lead_role_id`
  OR distinct `primary_document_goal_override`.
- **SC2.** Every pattern's `evidence_map` resolves 100% against the
  master-CV snapshot pinned into the work-item payload; zero
  unresolved citations.
- **SC3.** Every pattern's pool picks satisfy the §10 pool-
  consumption contract: `viability_bands.minimum_viable_truthful_header`
  IDs are present; `viability_bands.strong_competitive_header` IDs are
  not exceeded; no pick lies outside its source pool.
- **SC4.** Every pattern's `dimension_weights_override` keys are a
  subset of the canonical 4.2.5 `ExperienceDimension` enum, sums to
  100, and stays within ±30 percentage points of 4.2.5
  `overall_weights` per dimension (recommendation; calibrated by
  bench, see §15).
- **SC5.** Every pattern's `proof_order_override[]` is a permutation
  or subset of the canonical 4.2.3 `ProofTypeEnum`, and every
  `primary_document_goal_override` is in the canonical 4.2.2 goal
  enum.
- **SC6.** `pattern_signature` is byte-deterministic across two
  consecutive runs over identical inputs; eval-asserted (§16.4).
- **SC7.** The deterministic diversity check passes: at least one of
  (Jaccard distance ≥ 0.35 on `evidence_map.key_achievements.slots`),
  (distinct `lead_role_id`), (distinct `primary_document_goal_override`)
  holds for every pattern pair; or the third pattern is a
  conservative role-family default with `confidence.band ≤ medium`
  and `status=partial`.
- **SC8.** 4.3.4 consumes the persisted patterns verbatim with no
  re-derivation of evidence allowlists, header picks, or dimension
  overrides; every Layer 6 V2 invocation in 4.3.4 carries
  `pattern_id` and reads its pattern's `evidence_map` only.
- **SC9.** Langfuse stage span `scout.cv.pattern_selection` is
  emitted with the §17.4 metadata; one click from the level-2 UI.
- **SC10.** VPS smoke (§18) completes on a real `cv_ready` job with
  artifacts captured under `reports/pattern-selection/<job_id>/`.

## 5. Non-Goals

- Generating CV prose (header, summary, bullets, key achievements,
  competencies). Prose belongs to 4.3.4.
- Picking *the* best pattern. Selection of the winner is 4.3.5's job;
  4.3.3 only proposes three.
- Re-doing identity choice. The blueprint freezes
  `chosen_title`, `chosen_title_strategy`, `identity_tags[]`,
  `not_identity[]`, AI-band caps, leadership-band caps, and the
  `hero_proof_fragments[]` pool. Patterns reshape proof and emphasis,
  not identity.
- Inventing new dimension labels beyond the canonical 4.2.5 enum, or
  new `pattern_label` values beyond the §9.1 enum, or new proof
  categories beyond 4.2.3 `ProofTypeEnum`.
- Calling out to external data, web search, or research transports.
- Doing candidate-wide pattern discovery across multiple jobs (single-
  job scope, single `level2_id`).
- Owning a parallel control plane, a hidden selector service, or a
  "judge later" deferral mechanism.
- Growing any 4.3.2 pool retroactively.
- Authoring Layer 6 V2 prompt or stitcher behavior; 4.3.3 only emits
  the contract that 4.3.4 enforces inside Layer 6 V2.

## 6. Why This Stage Exists

Today the pipeline has one implicit pattern per job. That is
inadequate because:

- different evaluator lenses on the same job want different emphasis
  (a CTO wants system-architecture front-loaded; a hiring EM wants
  delivery execution front-loaded; a peer-IC reviewer wants hands-on
  implementation detail);
- for the same candidate, multiple legitimate patterns exist —
  architecture-first, delivery-first, leadership-first, AI-first,
  platform-first — each emphasizing different roles and different
  achievement variants;
- without a pattern spine, a single draft tries to satisfy every
  audience, ending up "generically good" instead of intentionally
  shaped;
- without evidence binding at the pattern level, later draft prose
  drifts because there is no structured memory of *why* a particular
  achievement made the cut.

4.3.2 froze identity and exposed bounded pools. 4.3.3 turns those
pools into three disciplined picks with structured evidence. It is the
reasoning seam where "what story does this candidate tell here" gets
three defensible answers, each with structured evidence — and where
4.3.4 obtains the deterministic instructions that prevent free-form
re-derivation inside Layer 6 V2.

## 7. Stage Boundary

### 7.1 DAG position

```
cv_ready -> cv.header_blueprint -> cv.pattern_selection
        -> fan-out to 3 cv.draft_assembly work items (per pattern_id)
        -> cv.grade_select_synthesize -> cv.publish -> cv.dossier
```

`cv.pattern_selection` runs as a single work item per `level2_id` and
is a barrier between `cv.header_blueprint` and the 4.3.4 fan-out: all
three downstream draft work items receive the same persisted
`PatternSelectionDoc`.

### 7.2 Inputs

Required upstream (all read from `level-2`):

- `cv_assembly.header_blueprint` — full `HeaderBlueprintDoc` (4.3.2).
- `pre_enrichment.presentation_contract.document_expectations` (4.2.2)
  — `primary_document_goal`, `proof_order[]`, `density_posture`,
  canonical section enum.
- `pre_enrichment.presentation_contract.cv_shape_expectations` (4.2.2)
  — `section_order[]`, `counts`, `header_shape`, `ats_envelope`,
  `ai_section_policy`.
- `pre_enrichment.presentation_contract.ideal_candidate_presentation_model`
  (4.2.4) — `visible_identity`, `acceptable_titles[]`, `tone_profile`,
  `must_signal[]`, `should_signal[]`, `de_emphasize[]`, `proof_ladder[]`,
  `risk_flags[]`.
- `pre_enrichment.presentation_contract.experience_dimension_weights`
  (4.2.5) — `overall_weights`, `stakeholder_variant_weights`,
  `minimum_visible_dimensions`, `overuse_risks`.
- `pre_enrichment.presentation_contract.truth_constrained_emphasis_rules`
  (4.2.6) — relevant `Rule[]` records (`forbidden_claim_patterns`,
  `cap_dimension_weight`, `soften_form`).
- `pre_enrichment.pain_point_intelligence` (4.2.3) — `pain_points[]`,
  `proof_map[]`, `bad_proof_patterns[]`, `search_terms[]`.
- `pre_enrichment.stakeholder_surface` (4.2.1) —
  `evaluator_coverage_target[]`, per-role `cv_preference_surface`.
- `pre_enrichment.classification` (4.1.2) — `primary_role_category`,
  `seniority`, `tone_family`, `ai_taxonomy`.
- `pre_enrichment.jd_facts` (4.1.1) — `top_keywords`, `responsibilities`,
  `qualifications`, `team_context` (read-only; no re-derivation).
- Master-CV via loader (4.3.1 v2 shape) — full `RoleData`,
  `RoleMetadata`, `ProjectMetadata`, taxonomies, `candidate_facts`,
  pinned to a `master_cv_checksum`.

Opportunistic (advisory, may be absent):

- `pre_enrichment.research_enrichment.role_profile` — `mandate`,
  `business_impact`, `success_metrics[]` (used as ranking priors only).
- `pre_enrichment.job_inference.semantic_role_model` — secondary prior
  for role-family pattern affinity.

### 7.3 Output

`cv_assembly.pattern_selection`: a `PatternSelectionDoc` persisted on
`level-2` under the `cv_assembly` subtree. See §9.

### 7.4 Work-item details

- `task_type = cv.pattern_selection`, `lane = cv_assembly`.
- `idempotency_key = cv.pattern_selection:<level2_id>:<input_snapshot_id>`
  where
  `input_snapshot_id = sha256(master_cv_checksum || header_blueprint_checksum
  || presentation_contract_checksum || jd_checksum || PROMPT_VERSION
  || PATTERN_SCHEMA_VERSION)`.
- `max_attempts = 3` with shared `RETRY_BACKOFF_SECONDS` from 4.3
  umbrella.
- `required_for_cv_assembled = true`. Failure deadletters the job per
  4.3 umbrella semantics — but a `status=partial` (one or two patterns
  swapped to conservative defaults) is allowed and not failure.
- Prerequisite check at claim: see §8 below.

### 7.5 Stage owner

Owned by the cv_assembly worker (`src/cv_assembly/stages/pattern_selection.py`).
Co-owned with 4.3.2 only at the validator-API level (§13.6 — the
shared validator pattern); no other ownership crossover.

## 8. Hard Prerequisites

The following must be true before `cv.pattern_selection` is allowed
to claim a job. These are checked deterministically at claim time and
recorded in `debug_context.preflight_check[]`.

### 8.1 Hard-blocking prerequisites

If any of these fail, the stage is **not enqueued** for the job; the
work-item layer marks `level-2.cv_assembly.stage_states.cv.pattern_selection`
with `status=blocked` and `blocked_reason`.

- `level-2.lifecycle == "cv_ready"` (or any later cv_assembly
  lifecycle that still implies this stage has work).
- `level-2.cv_assembly.header_blueprint.status in {completed, partial}`.
  `degraded` and `failed` are blockers — 4.3.2 must re-run first.
- `cv_assembly.header_blueprint` carries non-empty:
  - `identity.chosen_title`,
  - `identity.title_candidates[]` (≥ 1 entry),
  - `identity.visible_identity_candidates[]` (≥ 1 entry),
  - `tagline_ingredients.lead_phrase_candidates[]` (≥ 1 entry),
  - `hero_proof_fragments[]` (≥ 1 entry),
  - `viability_bands.minimum_viable_truthful_header.*_ids[]`
    populated.
- `MASTER_CV_BLUEPRINT_V2_ENABLED=true` and the master-CV loader
  succeeds with v2 schema (4.3.1) — `RoleMetadata.acceptable_titles`,
  `RoleMetadata.achievements[].scope_band`,
  `RoleMetadata.achievements[].metric_band`,
  `RoleMetadata.achievements[].ai_relevance_band`, and
  `RoleMetadata.achievements[].dimensions[]` are all populated for
  every role used by the job's role family.
- Canonical enums resolvable at import:
  `ProofType` (4.2.3), `ExperienceDimension` (4.2.5),
  `PrimaryDocumentGoal` (4.2.2), `DocumentSectionId` (4.2.2). If any
  enum import fails, the stage is blocked.

### 8.2 Degraded-allowed prerequisites

If any of these fail, the stage runs but emits `status in {partial,
degraded}` per the rules below. None of these alone is a blocker; the
combination is bounded by §8.4.

| Prerequisite | Degradation rule |
|---|---|
| `pre_enrichment.presentation_contract.experience_dimension_weights` missing or `status=unresolved` | Use 4.2.5 role-family default table (4.2.5 §12.3) as the prior; cap `confidence.band` at `medium`; record `defaults_applied=["dimension_weights:role_family"]`. |
| `pre_enrichment.presentation_contract.ideal_candidate_presentation_model` missing or `status=unresolved` | Use 4.3.1 `role_metadata.identity_summary.primary_identity_tags` as the visible-identity seed; cap confidence at `medium`. |
| `pre_enrichment.presentation_contract.truth_constrained_emphasis_rules` missing | Apply only the deterministic safety rules (§19); skip rule-projected forbidden categories. Cap confidence at `medium`. |
| `pre_enrichment.pain_point_intelligence` missing or `status=unresolved` | Salience formula drops the `proof_match` factor; cap confidence at `medium`. |
| `pre_enrichment.stakeholder_surface.status in {inferred_only, no_research}` | `stakeholder_variant_weights` from 4.2.5 are not used to bias dimension overrides; default to `overall_weights` only. |
| `pre_enrichment.research_enrichment.status in {partial, unresolved}` | Skip research-prior re-ranking; salience formula uses jd_facts + master-CV bands only. |
| `cv_assembly.header_blueprint.status == partial` | Patterns inherit `partial` status; record in `debug_context.upstream_partial=true`. |

### 8.3 Per-pattern degradation

A single pattern may fail diversity, fail evidence resolution after
one repair pass, or exhaust its pool — the **pattern** is swapped for
the conservative role-family default (§15.1) with
`pattern_status=swapped_default` and `confidence.band=medium`, while
the other two patterns may still complete normally. The stage's
overall `status` is `partial` whenever ≥ 1 pattern is swapped.

### 8.4 Bound on degradation

If two of three patterns are swapped to defaults, the stage emits
`status=degraded` (not `partial`) and the job's `cv_assembly.status`
becomes `degraded`. If all three are swapped to defaults, the stage
emits `status=failed` and the job deadletters per §15.2 — the
diversity invariant has effectively collapsed and 4.3.4 cannot
produce three meaningfully different drafts.

### 8.5 Operating-mode declaration

Per 4.3.2 §15.0, the degraded path is permitted but is **never** the
operating mode. Production runs must complete with `status=completed`
on ≥ 90% of `cv_ready` jobs (gate in §16.4).

## 9. Output Shape / Schema Direction

### 9.1 Top-level Pydantic model

```text
PatternSelectionDoc {
  schema_version,                          # PATTERN_SCHEMA_VERSION
  prompt_version,                          # "P-pattern-selection@vX"
  prompt_metadata: PromptMetadata,
  input_snapshot_id,
  master_cv_checksum,
  presentation_contract_checksum,
  header_blueprint_checksum,
  jd_checksum,
  status,                                  # completed | partial | degraded | failed
  source_scope,                            # full | jd_plus_research | jd_only_fallback
  patterns[] {                             # length == 3 unless status=failed
    pattern_id,                            # stable: "pattern_1" | "pattern_2" | "pattern_3"
    pattern_signature,                     # deterministic hash per §12
    pattern_label,                         # bounded enum, see §9.2
    pattern_status,                        # llm_picked | swapped_default | clamped | dropped
    fit_rationale,                         # <= 320 chars; cites presentation_contract ids
    lead_role_id,                          # master-CV role id that anchors the pattern
    supporting_role_ids[],                 # ordered subset of master-CV roles
    lead_project_ids[],                    # 0-3 master-CV project ids
    primary_document_goal_override,        # canonical 4.2.2 goal enum
    proof_order_override[],                # permutation OR subset of canonical 4.2.3 ProofType enum
    dimension_weights_override {           # dict[ExperienceDimension, int]; sums to 100
      <dimension>: int
    },
    section_emphasis[] {                   # consumed verbatim by 4.3.4
      section_id,                          # canonical 4.2.2 section enum
      emphasis,                            # enum: lead | strong | moderate | minimal
      focus_categories[],                  # canonical 4.2.3 ProofType
      length_bias,                         # enum: short | standard | expansive
      ordering_bias                        # enum: top | middle | bottom
    },
    header_picks {                         # per-pattern picks from 4.3.2 pools (§10.3)
      visible_identity_candidate_id,       # exactly one; from header_blueprint.identity.visible_identity_candidates[]
      lead_phrase_candidate_id,            # exactly one; from header_blueprint.tagline_ingredients.lead_phrase_candidates[]
      title_candidate_id,                  # exactly one from header_blueprint.identity.title_candidates[]
                                           # MUST resolve to the same string as header_blueprint.identity.chosen_title
                                           # (chosen_title is frozen by 4.3.2; this is a back-ref for audit only)
    },
    evidence_map {
      header {
        hero_proof_fragment_ids[],         # subset of header_blueprint.hero_proof_fragments[].fragment_id
        credibility_marker_ids[],          # subset of header_blueprint.credibility_markers[].marker_id
        differentiator_ids[],              # subset of header_blueprint.differentiators[].differentiator_id
        proof_anchor_ids[],                # subset of header_blueprint.tagline_ingredients.proof_anchor_pool[]
        differentiator_anchor_ids[]        # subset of header_blueprint.tagline_ingredients.differentiator_anchor_pool[]
      },
      summary {
        lead_achievement_refs[] {
          role_id, achievement_id, variant_id?
        }                                  # 0..3 refs; constrained by counts (4.2.2)
      },
      key_achievements {
        slots[] {                          # 0..N; N from cv_shape_expectations.counts.key_achievements
          role_id, achievement_id, variant_id?,
          proof_category,                  # canonical 4.2.3 ProofType
          dimension,                       # canonical 4.2.5 ExperienceDimension
          scope_band,                      # canonical 4.3.1 enum
          metric_band,                     # canonical 4.3.1 enum
          ai_relevance_band                # canonical 4.3.1 enum
        }
      },
      core_competencies {
        skill_ids[],                       # refs into role_skills_taxonomy
        evidence_for_skill: {              # map skill_id -> achievement_refs[]
          <skill_id>: [{role_id, achievement_id, variant_id?}]
        }
      },
      ai_highlights {
        enabled,                           # bool; honors cv_shape_expectations.ai_section_policy
        anchor_refs[]                      # achievement_refs with ai_relevance_band >= significant
      },
      experience {
        role_order[],                      # ordered role_ids; subset of master-CV roles
        per_role: {                        # map role_id -> RoleEmphasisDoc
          <role_id>: {
            emphasis,                      # enum: lead | strong | moderate | minimal
            achievement_refs[] {
              achievement_id, variant_id?, proof_category, dimension
            }
          }
        }
      },
      projects {
        enabled,
        project_order[]                    # ordered master-CV project_ids
      },
      education      { enabled, refs[] },  # refs into candidate_facts.education
      certifications { enabled, refs[] },
      publications   { enabled, refs[] },
      awards         { enabled, refs[] }
    },
    audience_tilt {                        # per-evaluator emphasis hint within the pattern
      recruiter:          {tilt[]} | null,
      hiring_manager:     {tilt[]} | null,
      executive_sponsor:  {tilt[]} | null,
      peer_reviewer:      {tilt[]} | null
    },
    risks[],                               # cites 4.2.4 risk_flags[] + 4.2.6 rule_ids
    confidence: ConfidenceDoc,
    evidence[]                             # EvidenceEntry refs to presentation_contract + master-CV
  },
  diversity_report: PatternDiversityReport,
  pool_consumption_report: PoolConsumptionReport,
  validator_report: PatternValidatorReport,
  unresolved_questions[],
  defaults_applied[],
  normalization_events[],
  debug_context: PatternSelectionDebug,
  confidence: ConfidenceDoc
}
```

### 9.2 `pattern_label` enum

Bounded label set; consumed by 4.3.4 to project pattern intent into
Layer 6 V2 prompt anchors. New labels MUST be added by enum bump in
`src/cv_assembly/models.py` and a prompt version bump.

```
architecture_led
delivery_led
leadership_led
ai_led
platform_led
transformation_led
operator_led
hybrid_architecture_ai
hybrid_delivery_leadership
hybrid_platform_ai
default_role_family            # used only by pattern_status=swapped_default patterns
```

No free-form labels. If the LLM returns a non-enum label, the
deterministic post-pass coerces it to the closest enum entry by token
similarity (recorded in `normalization_events[]`); if no entry is
within similarity threshold 0.5, the pattern is dropped and replaced
with the role-family default per §15.1.

### 9.3 `PatternDiversityReport`

```text
PatternDiversityReport {
  pattern_pair_jaccard[] {                # achievement-id Jaccard distance
    pair: ["pattern_1","pattern_2"|"pattern_1","pattern_3"|"pattern_2","pattern_3"],
    distance: float                       # 1 - Jaccard similarity over key_achievements.slots achievement_ids
  },
  experience_pair_jaccard[] {             # same, over experience.per_role.*.achievement_refs
    pair, distance
  },
  lead_role_uniqueness: bool,
  goal_uniqueness: bool,
  diversity_threshold: float,             # 0.35 default; see §11.4
  diversity_status: "ok" | "tight" | "default_swap_required"
}
```

### 9.4 `PoolConsumptionReport`

```text
PoolConsumptionReport {
  per_pattern[] {
    pattern_id,
    title_candidate_pool_size,
    visible_identity_pool_size,
    lead_phrase_pool_size,
    hero_proof_fragment_pool_size,
    proof_anchor_pool_size,
    differentiator_anchor_pool_size,
    must_include_floor_satisfied: bool,   # viability_bands.minimum_viable_truthful_header
    upper_bound_satisfied: bool,          # viability_bands.strong_competitive_header
    pool_insufficiency_kinds[]            # subset of {hero_proof, credibility, differentiator,
                                          #            visible_identity, lead_phrase, title}
  },
  any_default_swap: bool,
  any_pool_growth_attempted: bool,        # MUST be false (§10)
}
```

### 9.5 `PatternSelectionDebug`

```text
PatternSelectionDebug {
  preflight_check[] {                     # one per §8 condition
    name, status, detail
  },
  preflight_pool {
    candidate_evidence_pool_size,
    selected_achievement_count,
    rejected_achievement_count,
    salience_quantiles                    # {q25, q50, q75, max}
  },
  defaults_applied[],
  normalization_events[] {kind, from, to, reason},
  richer_output_retained[],
  rejected_output[],
  retry_events[],
  validator_trace[],
  diversity_computation_trace[],
  llm_request_ids[],
  cache_hit: bool,
  cache_key                               # input_snapshot_id by default
}
```

Debug is collection-backed only, never mirrored to compact projection.
Capped at 32 KB.

## 10. Pool Consumption Contract With 4.3.2

This contract is **load-bearing** and is enforced by the deterministic
pattern validator (§13). 4.3.3 is a **picker** stage; 4.3.2 owns the
pools.

### 10.1 Source-of-truth chain (titles, identity, proof)

Per 4.3.2 §7.5, the SoT chain is:

| Concern | Owned by | Read by 4.3.3 from |
|---|---|---|
| `chosen_title` (frozen) | 4.3.2 | `header_blueprint.identity.chosen_title` |
| `chosen_title_strategy` (frozen) | 4.3.2 | `header_blueprint.identity.chosen_title_strategy` |
| `title_candidates[]` (ranked) | 4.3.2 | `header_blueprint.identity.title_candidates[]` |
| `visible_identity_candidates[]` (pool) | 4.3.2 | `header_blueprint.identity.visible_identity_candidates[]` |
| `lead_phrase_candidates[]` (pool) | 4.3.2 | `header_blueprint.tagline_ingredients.lead_phrase_candidates[]` |
| `hero_proof_fragments[]` (pool) | 4.3.2 | `header_blueprint.hero_proof_fragments[]` |
| `proof_anchor_pool[]` (pool) | 4.3.2 | `header_blueprint.tagline_ingredients.proof_anchor_pool[]` |
| `differentiator_anchor_pool[]` (pool) | 4.3.2 | `header_blueprint.tagline_ingredients.differentiator_anchor_pool[]` |
| `credibility_markers[]` (pool) | 4.3.2 | `header_blueprint.credibility_markers[]` |
| `differentiators[]` (pool) | 4.3.2 | `header_blueprint.differentiators[]` |
| `viability_bands.*` (must-include / upper-bound) | 4.3.2 | `header_blueprint.viability_bands` |

4.3.3 may **never**:

- override `chosen_title`,
- override `chosen_title_strategy`,
- substitute outside `title_candidates[]`,
- compose new `visible_identity` strings,
- compose new `lead_phrase` strings,
- introduce a `hero_proof_fragment` not in the pool,
- introduce a `credibility_marker` not in the pool,
- introduce a `differentiator` not in the pool,
- attempt to grow any pool retroactively (the validator rejects this
  with `pool_growth_attempted`; the work item retries once with the
  fresh pool, then deadletters — pool growth is a contract violation,
  not a recoverable defect).

### 10.2 Pool vs pick semantics

For each pool listed in §10.1, 4.3.3 picks **subsets** per pattern:

- `visible_identity_candidate_id`: **exactly one** per pattern.
- `lead_phrase_candidate_id`: **exactly one** per pattern.
- `title_candidate_id`: **exactly one** per pattern; MUST resolve to
  the same string as `header_blueprint.identity.chosen_title`. (See
  §10.5 for the per-pattern title-pick rule.)
- `hero_proof_fragment_ids[]`: 1..N subset; N bounded above by
  `viability_bands.strong_competitive_header.hero_proof_fragment_ids[]`
  size.
- `credibility_marker_ids[]`: 0..N subset; N bounded above by
  `viability_bands.strong_competitive_header.credibility_marker_ids[]`
  size.
- `differentiator_ids[]`: 0..N subset; bounded above similarly.
- `proof_anchor_ids[]` and `differentiator_anchor_ids[]`: 0..N subsets.

### 10.3 Per-pattern header picks

Every pattern carries a `header_picks` block (§9.1) that records the
exact picks. The set of `header_picks` across the three patterns
needs not be disjoint — two patterns may pick the same
`visible_identity_candidate_id` if their `evidence_map` differs
sufficiently to satisfy the diversity invariant (§11.4). However, if
two patterns share the same pick set across `(visible_identity,
lead_phrase, hero_proof_fragment_ids[])`, they are presumed
non-diverse and the diversity check applies.

### 10.4 Must-include and upper-bound rules

Every pattern's `evidence_map.header` MUST include:

- every `hero_proof_fragment_id` listed in
  `header_blueprint.viability_bands.minimum_viable_truthful_header.hero_proof_fragment_ids[]`,
- every `credibility_marker_id` listed in
  `header_blueprint.viability_bands.minimum_viable_truthful_header.credibility_marker_ids[]`,
- the `visible_identity_candidate_id` listed in
  `header_blueprint.viability_bands.minimum_viable_truthful_header.visible_identity_candidate_id`
  is **the conservative default** — patterns are not required to pick
  it specifically, but if a pattern picks something else, the validator
  checks that the pick is also in
  `viability_bands.strong_competitive_header.visible_identity_candidate_ids[]`.

Every pattern's `evidence_map.header` MUST NOT exceed:

- the union of
  `header_blueprint.viability_bands.strong_competitive_header.hero_proof_fragment_ids[]`
  for `hero_proof_fragment_ids`,
- analogous upper-bound id sets for `credibility_marker_ids[]` and
  `differentiator_ids[]`.

Picks outside the upper-bound id sets are pool violations and
trigger validator action `prune_to_pool` (§13.4).

### 10.5 Per-pattern title-pick rule

`chosen_title` is frozen by 4.3.2 (the picked title is the same
across all three patterns). However, `title_candidates[]` is exposed
so a pattern may justify why it would have chosen the same title or a
near-rank substitute within the same `chosen_title_strategy` band, in
its `fit_rationale`. The `header_picks.title_candidate_id` field
records which `title_candidates[]` entry the pattern *would* pick if
it could; the validator asserts this resolves to the same string as
`chosen_title`. This preserves cross-draft title stability while
allowing pattern-specific rationale.

### 10.6 Pool insufficiency rule

If, **for a specific pattern**, no valid pick set satisfies all of:

- the must-include floor (§10.4),
- the upper-bound (§10.4),
- the diversity invariant relative to already-finalized patterns
  (§11.4),
- the pattern's intended emphasis (lead role compatibility, dimension
  weighting compatibility),

then the pattern is **swapped for the conservative role-family default**
per §15.1. `pattern_status=swapped_default`, `confidence.band` is
capped at `medium`, the swap is recorded in
`pool_consumption_report.per_pattern[].pool_insufficiency_kinds[]` and
in `defaults_applied[]`, and stage `status` becomes `partial`.

Pool insufficiency is **per-pattern**, not stage-global. One pattern's
insufficiency does not invalidate the other two. Insufficiency for
all three patterns triggers `status=failed` per §8.4.

### 10.7 No retroactive pool growth

If pool insufficiency is **stage-global** (the pool itself is too thin
for any meaningful pattern to use it — for example, the
`hero_proof_fragments[]` pool has 1 entry and three patterns each need
≥ 2), 4.3.3 does not grow the pool. The job's
`cv_assembly.header_blueprint` must re-run with broader extraction
parameters (a 4.3.2 concern, not a 4.3.3 concern). The validator
records `pool_growth_attempted=false`, the stage swaps to defaults
where possible, and the job is escalated to operator triage if §8.4
fires.

### 10.8 Persistence under per-pattern degradation

When one pattern degrades (`pattern_status in {swapped_default,
clamped}`) and another does not, both are persisted to
`patterns[]`. The persisted doc carries:

- `pattern_status` per pattern,
- `defaults_applied[]` at the stage level (which patterns were swapped
  and why),
- `confidence.band` per pattern (cap rule applies per pattern, not
  globally),
- `status` at the stage level following §8.5.

4.3.4 reads each pattern's `pattern_status` and may apply per-pattern
strictness — a swapped-default pattern uses a more conservative
truthfulness regime in Layer 6 V2 (no architecture/leadership
inflation, narrower variant set).

### 10.9 What 4.3.4 may consume; what it may not invent later

4.3.4 may consume verbatim:

- the pattern's `header_picks.{visible_identity_candidate_id,
  lead_phrase_candidate_id, title_candidate_id}`,
- the pattern's `evidence_map.*` (header picks, summary refs,
  key_achievements slots, core_competencies skill_ids,
  ai_highlights anchors, experience role_order and per_role
  refs, projects/education/certifications/publications/awards refs),
- the pattern's `dimension_weights_override`,
- the pattern's `proof_order_override[]`,
- the pattern's `primary_document_goal_override`,
- the pattern's `section_emphasis[]`,
- the pattern's `audience_tilt`,
- the pattern's `risks[]` (advisory; 4.3.4 may translate into
  Layer 6 V2 forbidden-category projection per 4.3.4 §8).

4.3.4 may **not**:

- introduce a `visible_identity` string outside the pattern's pick,
- introduce a `lead_phrase` string outside the pattern's pick,
- introduce a `hero_proof_fragment` outside the pattern's
  `evidence_map.header.hero_proof_fragment_ids[]`,
- introduce an achievement outside the pattern's
  `evidence_map.experience.per_role.*.achievement_refs[]` ∪
  `evidence_map.key_achievements.slots[]` ∪
  `evidence_map.summary.lead_achievement_refs[]`,
- introduce a skill outside the pattern's
  `evidence_map.core_competencies.skill_ids[]`,
- override `dimension_weights_override`,
- override `primary_document_goal_override`,
- override `proof_order_override[]`.

Violations are caught by the 4.3.4 `evidence_lineage_validator` at
persist (4.3.4 §9.2).

## 11. Deterministic Preflight And Salience Ranking

The LLM in this stage is asked to **pick and rationalize from a
bounded, ranked candidate pool**, not to search master-CV
free-form. The preflight is the seam that keeps that promise.

### 11.1 Candidate evidence pool construction

Built deterministically from master-CV (4.3.1) before any LLM call:

For each role in `RoleData[]`:

1. Enumerate `role.metadata.achievements[]`.
2. For each achievement, enumerate its `variants[]`. The candidate
   pool contains one entry per `(role_id, achievement_id, variant_id?)`
   tuple. When `variants[]` is empty, the entry uses `variant_id=null`.
3. Attach the achievement metadata: `proof_categories[]`,
   `dimensions[]`, `credibility_markers[]`, `scope_band`,
   `metric_band`, `ai_relevance_band`, `confidence`.

The pool is capped at 256 entries per stage run. If the master-CV
exceeds this, entries are truncated by salience score (§11.3) after
ranking — never by random sampling. The rejected count is recorded in
`debug_context.preflight_pool.rejected_achievement_count`.

### 11.2 Enum-to-numeric mapping table

Used by the salience score; bytes-stable across runs.

```
metric_band:        none=0, small=1, medium=2, large=3, flagship=4
scope_band:         individual=0, squad=1, team=2, cross_team=3, org=4, company=5
ai_relevance_band:  none=0, adjacent=1, significant=2, core=3
confidence_band:    none=0, low=1, medium=2, high=3
emphasis:           minimal=1, moderate=2, strong=3, lead=4
proof_match:        none=0, partial=1, exact=2     # see §11.3 for derivation
```

### 11.3 Salience score formula

For each candidate `c = (role_id, achievement_id, variant_id?)`, with
metadata `M(c)`:

```
dimension_weight(c)   = max over d in M(c).dimensions of
                          experience_dimension_weights.overall_weights[d]
                        (default 0 if c has no canonical dimensions)
proof_match(c)        = exact   if any pp in pain_point_intelligence.proof_map[]
                                 has preferred_proof_type in M(c).proof_categories
                                 AND any term in pain_point_intelligence.search_terms[].term
                                 appears in role.markdown source for c
                       partial  if only the proof_type matches
                       none     otherwise
proof_match_weight(c) = ordinal(proof_match(c))            # 0,1,2

salience(c) = (
    dimension_weight(c)            # 0..100
  * (1 + ordinal(M(c).scope_band)) # 1..6
  * (1 + ordinal(M(c).metric_band))# 1..5
  * (1 + ordinal(M(c).ai_relevance_band)) # 1..4 (only when relevant — see normalization)
  * (1 + proof_match_weight(c))    # 1..3
)

# Normalization
- divide by max(salience(*)) over the pool; salience_norm in [0, 1]
- when classification.ai_taxonomy.intensity in {none, unknown}, the
  ai_relevance_band factor is replaced by 1 (does not bias score)
- when pain_point_intelligence is absent, proof_match_weight = 0 for
  all candidates (factor becomes 1)
```

### 11.4 Tie-break and ordering rules

Ranking uses `salience_norm` descending. Ties are broken in this
fixed order:

1. higher `confidence.band` ordinal,
2. higher `metric_band` ordinal,
3. higher `scope_band` ordinal,
4. lexicographic ascending `(role_id, achievement_id, variant_id ?? "")`.

This produces a fully deterministic ordering for byte-equal inputs.
The ordering is recorded in `debug_context.preflight_pool` for replay.

### 11.5 When the preflight rejects a candidate

Hard rejections (candidate excluded from the pool entirely):

- `M(c).confidence.band == none`,
- `c` cites a `variant_id` that does not resolve in master-CV,
- `M(c)` is missing required metadata bands (one of `scope_band`,
  `metric_band`, `ai_relevance_band`),
- `M(c).proof_categories` empty AND `M(c).dimensions` empty,
- `c.role_id` is in `presentation_contract.truth_constrained_emphasis_rules`
  forbidden role list (rare; only when a role's
  `RoleMetadata.identity_summary.primary_identity_tags[]` is in
  `not_identity[]` for the job — recorded as a rejection event).

Soft rejections (kept in the pool but flagged in debug):

- `M(c).ai_relevance_band > classification.ai_taxonomy.intensity` —
  candidate is still pickable but the validator will reject it from
  any pattern's `ai_highlights.anchor_refs[]` (per safety rule §19).
- `M(c).scope_band == individual` AND the pattern label is
  `leadership_led` — the candidate is pickable for `experience` but
  not for `key_achievements` of that pattern.

### 11.6 Consumption of 4.2.3 `proof_map` and `search_terms[]`

Per 4.2.3 §14.11 downstream-consumer contract:

- `proof_map[].preferred_proof_type` is the seed for the
  `proof_match_weight` factor (§11.3). Each pattern's
  `evidence_map.experience.per_role.*.achievement_refs[].proof_category`
  must be in the union of `proof_map[].preferred_proof_type` ∪ the
  achievement's own `proof_categories[]` ∪ `proof_order[]` from 4.2.2.
- `proof_map[].bad_proof_patterns[]` are projected onto a
  `forbidden_proof_categories[]` derived list at preflight time and
  passed to the LLM as a hard constraint. Any pattern emitting an
  `evidence_map.*.proof_category` in this list is rejected by the
  validator and triggers `clamp_band` or `drop_pattern` (§13.4).
- `search_terms[]` are used as a token-overlap signal in `proof_match`
  derivation (§11.3) and are passed into the LLM as a "topical
  vocabulary" hint, not as a hard constraint. The LLM may not
  copy-paste search terms into the rationale or evidence_map.

### 11.7 Consumption of 4.2.5 `overall_weights`

Per 4.2.5 §10.1, `ExperienceDimension` is owned by 4.2.5. 4.3.3
seeds `dimension_weights_override` from `overall_weights` per
pattern:

- For pattern label `architecture_led`, bias toward
  `architecture_system_design` and `platform_scaling_change` by
  +10 percentage points each (subject to per-pattern sum-to-100).
- For pattern label `delivery_led`, bias toward
  `delivery_execution_pace` and `business_impact` by +10 each.
- For pattern label `leadership_led`, bias toward
  `leadership_enablement` and `stakeholder_communication` by +10
  each. Subject to 4.2.5 §12.5 leadership cap by `seniority` ×
  `leadership_evidence_band`.
- For pattern label `ai_led`, bias toward `ai_ml_depth` and
  `architecture_system_design` by +10 each. Subject to 4.2.5
  §12.4 AI cap.
- For pattern label `platform_led`, bias toward
  `platform_scaling_change` and `quality_risk_reliability` by +10
  each.
- For pattern label `transformation_led`, bias toward
  `business_impact` and `methodology_operating_model` by +10 each.
- For pattern label `operator_led`, bias toward
  `delivery_execution_pace` and `methodology_operating_model` by +10
  each.
- For pattern labels prefixed `hybrid_*`, split the +10 across the
  two named dimensions (+5 each).

After bias, the override map is renormalized to sum to 100 by
proportional scaling of all non-biased dimensions. Per-dimension
deviation from `overall_weights` is bounded above by **±30
percentage points** (recommendation, calibrated by bench). Excess
deviation is clamped (`clamp_weight_override` action; §13.4).

### 11.8 Eval-derived persona-family priors

The pattern selector must not treat the category label as the persona.
It must treat the category as a market lane and seed patterns from the
eval-backed lane priors summarized in
`reports/4.3-manual-master-cv-review-methodology.md`.

Required priors by lane:

- `ai_architect_*`
  - at least two of the three patterns must come from
    `{architecture_led, platform_led, delivery_led}`;
  - `leadership_led` is allowed only as a bounded player-coach variant.
- `head_of_ai_*`
  - at least one pattern must be `architecture_led`;
  - no pattern may assume literal executive identity unless 4.3.1 title
    allowlists and role scope support it.
- `staff_ai_engineer_*`
  - prioritize `{platform_led, ai_led, architecture_led}`;
  - any leadership tilt must remain senior-IC/player-coach.
- `senior_ai_engineer_eea`
  - prioritize `{ai_led, platform_led, delivery_led}`;
  - avoid over-architected or management-heavy pattern picks.
- `tech_lead_ai_eea`
  - prioritize `{delivery_led, platform_led, leadership_led}`;
  - `leadership_led` here means mentoring/design-review/player-coach, not
    org-chart management.
- `ai_eng_manager_eea`
  - prioritize `{delivery_led, leadership_led, architecture_led}`;
  - must remain player-coach unless direct manager evidence is explicit.

These priors are load-bearing because the eval corpus showed that
`head_of_ai_*` is usually an architect-first adjacency, not a true executive
persona, and that most "management" fit comes from player-coach delivery
evidence rather than org ownership.

### 11.9 Consumption of 4.3.2 viability bands

The viability bands (§10.4) constrain pool picks. They also seed
the LLM prompt as MUST-include / MUST-NOT-exceed instructions — the
deterministic post-pass enforces them after the LLM call.

### 11.10 Surface-authorization consumption

Pattern selection must consume 4.3.1 surface authorizations:

- a skill may not be placed in
  `evidence_map.core_competencies.skill_ids[]` unless
  `skill_surface_authorization[skill_id]` contains `core_competency`;
- a header hero proof fragment may not cite an achievement whose
  `allowed_surfaces[]` omits `header_proof`;
- a summary lead achievement may not cite an achievement whose
  `allowed_surfaces[]` omits `summary_safe`.

This prevents the exact eval failure mode where competencies or header
signals become more ambitious than the underlying experience.

## 12. `pattern_signature` Determinism Rule

`pattern_signature` is a byte-deterministic hash. It is used for
de-duplication, eval-corpus snapshot comparisons, and 4.3.5 cache
keys. Determinism is a hard invariant (asserted by §16.4).

### 12.1 Canonical input object

```python
def canonical_pattern_input(pattern: PatternDoc) -> dict:
    return {
        "lead_role_id": pattern.lead_role_id,
        "supporting_role_ids": sorted(pattern.supporting_role_ids),
        "lead_project_ids": sorted(pattern.lead_project_ids),
        "primary_document_goal_override": pattern.primary_document_goal_override,
        "proof_order_override": list(pattern.proof_order_override),  # order preserved
        "dimension_weights_override": {
            d: int(w)                                                # non-negative ints only
            for d, w in sorted(pattern.dimension_weights_override.items())
        },
        "header_picks": {
            "visible_identity_candidate_id": pattern.header_picks.visible_identity_candidate_id,
            "lead_phrase_candidate_id": pattern.header_picks.lead_phrase_candidate_id,
            "title_candidate_id": pattern.header_picks.title_candidate_id,
        },
        "evidence_map_achievement_ids": sorted(  # canonical achievement-set fingerprint
            f"{ref.role_id}:{ref.achievement_id}:{ref.variant_id or ''}"
            for ref in (
                *pattern.evidence_map.summary.lead_achievement_refs,
                *pattern.evidence_map.key_achievements.slots,
                *(
                    ref
                    for role in pattern.evidence_map.experience.per_role.values()
                    for ref in role.achievement_refs
                ),
            )
        ),
        "evidence_map_header_ids": {
            "hero_proof_fragment_ids": sorted(pattern.evidence_map.header.hero_proof_fragment_ids),
            "credibility_marker_ids": sorted(pattern.evidence_map.header.credibility_marker_ids),
            "differentiator_ids": sorted(pattern.evidence_map.header.differentiator_ids),
        },
        "schema_version": PATTERN_SCHEMA_VERSION,
    }
```

### 12.2 Serialization rule

```python
import hashlib, json

def pattern_signature(pattern: PatternDoc) -> str:
    payload = canonical_pattern_input(pattern)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

`json.dumps(..., sort_keys=True, separators=(",", ":"))` is the
canonical Python form. `ensure_ascii=True` is required (no Unicode
escapes in the canonical form). `allow_nan=False` rejects NaN /
Inf — they must never appear in the canonical input.

### 12.3 Storage field

`pattern_signature` is persisted on `PatternDoc.pattern_signature` as
a string (`"sha256:" + 64 hex chars`). It is also surfaced on
Langfuse stage events (`scout.cv.pattern_selection.pattern_emitted`)
and on 4.3.4 `DraftDoc.pattern_signature` (back-ref).

### 12.4 Replay guarantee

For the same `(input_snapshot_id, prompt_version, schema_version)`,
re-running the stage MUST produce the same set of three
`pattern_signature`s in the same order. Asserted by
`tests/unit/cv_assembly/test_pattern_signature_determinism.py`
(§16.4).

### 12.5 What changes the signature; what does not

Changes signature:

- any change to `lead_role_id`, `supporting_role_ids`,
  `lead_project_ids`, `primary_document_goal_override`,
  `proof_order_override`, `dimension_weights_override`,
- any change to the canonical achievement-id fingerprint (added or
  removed achievement, variant, or per-role membership),
- any change to header picks
  (`visible_identity_candidate_id`, `lead_phrase_candidate_id`,
  `title_candidate_id`),
- any change to header-id picks (`hero_proof_fragment_ids`,
  `credibility_marker_ids`, `differentiator_ids`),
- a `PATTERN_SCHEMA_VERSION` bump.

Does NOT change signature:

- `fit_rationale` text changes,
- `confidence.band` changes,
- `pattern_status` changes (a swapped-default pattern with the same
  achievement set as a previous swapped-default has the same
  signature — diversity check operates on signature uniqueness so
  this is correctly caught),
- `audience_tilt` changes,
- `risks[]` text changes,
- `evidence[]` provenance ordering (sorted before hashing),
- `debug_context` content,
- `proof_anchor_ids[]` and `differentiator_anchor_ids[]` (these are
  advisory tagline ingredients, not load-bearing for diversity).

The split between "changes signature" and "does not" is bounded by
the rule **load-bearing for diversity and 4.3.4 consumption changes
the signature; advisory and provenance fields do not.**

## 13. Pattern Validator API

Module: `src/cv_assembly/validators/pattern_validator.py`. The
validator is a **shared library**, used by 4.3.3 (selection) and
4.3.4 (consumption sanity check). Its determinism is load-bearing.

### 13.1 Module and signature

```python
# src/cv_assembly/validators/pattern_validator.py

PatternValidatorMode = Literal["selection", "draft_consumption"]

def validate_patterns(
    pattern_doc: PatternSelectionDoc,
    header_blueprint: HeaderBlueprintDoc,
    master_cv: CandidateData,
    presentation_contract: PresentationContractDoc,
    *,
    mode: PatternValidatorMode,
    tracer: Optional[CvAssemblyTracingSession] = None,
) -> PatternValidatorReport
```

Mode semantics:

- `"selection"`: validates the pattern doc the LLM produced (or the
  doc after deterministic-default swap). Allowed to apply repair
  actions (§13.4). Used inside 4.3.3 before persist.
- `"draft_consumption"`: validates that the pattern as persisted is
  internally consistent and that the assumptions 4.3.4 will make are
  true (e.g., evidence_map references resolve in the pinned master-CV
  snapshot). Repair is **not** allowed in this mode — failures bubble
  to 4.3.4 as a hard error and the draft work item deadletters.

### 13.2 Report shape

```text
PatternValidatorReport {
  status,                                  # pass | repair_attempted | failed
  determinism_hash,                        # sha256 of canonical report payload (§13.5)
  per_pattern[] {
    pattern_id,
    pattern_signature,                     # back-ref
    pattern_status,                        # input from pattern_doc, copied here
    violations[] {
      rule_id,                             # stable slug, see §13.3
      severity,                            # blocking | repairable | warning
      location {
        section,                           # header | summary | key_achievements | core_competencies |
                                           # ai_highlights | experience | projects | education |
                                           # certifications | publications | awards | weights | goals |
                                           # proof_order | header_picks
        slot_index?,
        role_id?,
        achievement_id?,
        skill_id?
      },
      detail,                              # <= 240 chars
      suggested_action                     # enum, see §13.4
    },
    repairs_applied[] {
      rule_id,
      action,                              # enum, see §13.4
      before_signature,
      after_signature,
      detail
    },
    repaired_pattern: PatternDoc | null    # populated when any repair fired
  },
  diversity_violations[] {
    pair: ["pattern_X","pattern_Y"],
    metric,                                # achievement_jaccard | experience_jaccard | signature_collision
    value,
    threshold,
    suggested_action                       # swap_to_default | drop_pattern
  },
  pool_violations[] {
    pattern_id,
    kind,                                  # outside_pool | floor_unmet | upper_bound_exceeded |
                                           # pool_growth_attempted
    pool,                                  # hero_proof | credibility | differentiator |
                                           # visible_identity | lead_phrase | title |
                                           # proof_anchor | differentiator_anchor
    detail
  }
}
```

### 13.3 Violation rule_id catalogue

Stable slugs; new slugs require a model-bump and a doc update.

```
title_outside_chosen          # header_picks.title_candidate_id resolves to a string != chosen_title
title_outside_pool            # title_candidate_id not in title_candidates[]
visible_identity_outside_pool
lead_phrase_outside_pool
hero_proof_outside_pool
credibility_outside_pool
differentiator_outside_pool
proof_anchor_outside_pool
floor_hero_proof_unmet
floor_credibility_unmet
upper_bound_hero_proof_exceeded
upper_bound_credibility_exceeded
upper_bound_differentiator_exceeded
pool_growth_attempted

evidence_unresolved           # achievement_id, variant_id, role_id, project_id, skill_id unresolved
ai_band_climbing              # ai_highlights anchor with band > classification.ai_taxonomy.intensity
leadership_band_climbing      # leadership_led pattern with lead_role.seniority.managerial_level=ic
scope_climbing                # pattern emphasis exceeds underlying achievement's scope_band
forbidden_proof_category      # evidence_map.*.proof_category in forbidden_proof_categories[]
forbidden_claim_pattern       # truth_constrained_emphasis_rules forbidden_claim_patterns
identity_drift                # picks visible_identity inconsistent with identity_tags[]
not_identity_violated         # picks intersect with not_identity[]

dimension_weights_off_canonical_enum
dimension_weights_sum_not_100
dimension_weights_negative
dimension_weights_outside_band  # > overall_weights ± 30 pp
dimension_weights_cap_exceeded  # exceeds 4.2.6 cap_dimension_weight rule

primary_document_goal_off_canonical_enum
proof_order_off_canonical_enum
section_emphasis_section_off_canonical_enum
section_emphasis_focus_categories_off_canonical_enum

pattern_label_off_enum
pattern_signature_collision
pattern_signature_nondeterministic
diversity_floor_violation

key_achievements_count_exceeds_shape
core_competencies_skill_outside_taxonomy
ai_highlights_enabled_with_no_anchors
ai_highlights_anchor_band_too_low

audience_tilt_key_outside_evaluator_coverage
risks_rule_id_unresolved
```

### 13.4 Allowed deterministic repair actions

Repair is **deterministic**, **bounded to one pass**, **never calls
an LLM**, and **never invents content outside the blueprint pools or
master-CV evidence**. Allowed actions:

- `prune_to_pool` — drop one or more ids from a pool-sourced list
  that were not in the source pool. Renumber slot indices; preserve
  original order. Applies to `hero_proof_outside_pool`,
  `credibility_outside_pool`, `differentiator_outside_pool`,
  `proof_anchor_outside_pool`.
- `clamp_band` — clamp an `ai_relevance_band` or
  `leadership` claim down to the maximum allowed by upstream
  (`classification.ai_taxonomy.intensity` or
  `seniority.managerial_level`). Recorded with before/after values.
  Applies to `ai_band_climbing`, `leadership_band_climbing`,
  `scope_climbing`.
- `clamp_weight_override` — clamp a `dimension_weights_override`
  entry that exceeds the ±30 pp band, then renormalize the rest to
  sum to 100 by proportional scaling. Applies to
  `dimension_weights_outside_band`, `dimension_weights_sum_not_100`
  (when off by ≤ 5), `dimension_weights_cap_exceeded`.
- `swap_to_default` — replace a pattern entirely with the role-family
  conservative default per §15.1. The pattern's `pattern_status`
  becomes `swapped_default`, `confidence.band` is capped at `medium`,
  the swap is recorded in `defaults_applied[]`. Applies to
  `pool_growth_attempted` (after one re-pick attempt fails),
  `evidence_unresolved` (when ≥ 2 unresolved cites in one pattern),
  `diversity_floor_violation` (when the third pattern is non-diverse
  with the first two).
- `drop_pattern` — remove a pattern from `patterns[]`. Triggers
  immediate replacement with the role-family default — `drop_pattern`
  alone is never the final action; it always pairs with
  `swap_to_default`. Applies to `pattern_signature_collision` (the
  later-indexed pattern is dropped and swapped).

Repair never:

- generates new prose,
- introduces a master-CV ref not already in the candidate evidence
  pool (§11.1),
- introduces a header pool member that 4.3.2 did not emit,
- changes `chosen_title`, `chosen_title_strategy`, `identity_tags[]`,
  `not_identity[]`, or any 4.3.2-frozen field,
- regenerates via LLM,
- alters `pattern_signature` semantics (signature is recomputed after
  repair).

After one pass, the validator re-runs the gate on the repaired
pattern doc. Remaining `severity=blocking` violations →
`status=failed`. Remaining `severity=repairable` violations after
one pass → `status=failed`. `severity=warning` violations are
retained but do not fail the run.

### 13.5 Determinism guarantees

For fixed `(pattern_doc, header_blueprint, master_cv,
presentation_contract, mode)`, `validate_patterns()` returns
byte-identical `PatternValidatorReport` instances across runs.

- `determinism_hash` is `sha256:` over the canonical JSON form of the
  report (excluding itself), with the same canonicalization rule as
  §12.2.
- Asserted by
  `tests/unit/cv_assembly/test_pattern_validator_determinism.py`
  (§16.4) with two runs over the same inputs.
- No clock reads, no random seeds, no environment reads, no Mongo
  reads. Pure function over inputs.

### 13.6 Test fixture expectations

Per `tests/unit/cv_assembly/test_pattern_validator.py`:

- one fixture per `rule_id` in §13.3 — a synthesized minimal
  `PatternSelectionDoc` that violates only that rule, with the
  expected `severity` and `suggested_action`.
- one repair fixture per `action` in §13.4 — pre/post pattern docs and
  expected `repairs_applied[]` entry.
- one diversity fixture (three patterns with collapsed signatures →
  `swap_to_default` on pattern_3).
- one pool-growth fixture (a pattern picks a `hero_proof_fragment_id`
  not in the pool → `pool_growth_attempted` with severity=blocking).
- one mode-difference fixture: same defect, `selection` mode triggers
  repair, `draft_consumption` mode reports `failed`.

## 14. Downstream Consumer Contracts

### 14.1 4.3.4 Multi-Draft CV Assembly

For each of the three drafts (one per `pattern_id`), 4.3.4 reads the
following from `cv_assembly.pattern_selection.patterns[<pattern_id>]`:

| Field | Used for | Override allowed? |
|---|---|---|
| `header_picks.visible_identity_candidate_id` | header prose composition (Layer 6 V2 blueprint-first) | no |
| `header_picks.lead_phrase_candidate_id` | header prose composition | no |
| `header_picks.title_candidate_id` | back-ref check; final title is `chosen_title` | no |
| `evidence_map.header.hero_proof_fragment_ids[]` | key_achievements + tagline ingredient picks | no |
| `evidence_map.header.credibility_marker_ids[]` | competency / header marker picks | no |
| `evidence_map.summary.lead_achievement_refs[]` | summary prose lead bullets | no |
| `evidence_map.key_achievements.slots[]` | KA section prose; one bullet per slot | no |
| `evidence_map.core_competencies.skill_ids[]` | skills section content (skills outside list are stripped) | no |
| `evidence_map.core_competencies.evidence_for_skill` | grader provenance only | advisory |
| `evidence_map.ai_highlights.enabled` | whether to render AI highlights section | no |
| `evidence_map.ai_highlights.anchor_refs[]` | AI highlights bullet picks | no |
| `evidence_map.experience.role_order[]` | order roles appear | no |
| `evidence_map.experience.per_role.<id>.emphasis` | per-role bullet count + verbosity | no |
| `evidence_map.experience.per_role.<id>.achievement_refs[]` | bullet picks (achievements outside list are filtered before LLM prompting) | no |
| `evidence_map.projects.enabled` and `project_order[]` | projects section | no |
| `evidence_map.education / certifications / publications / awards.{enabled, refs}` | flat refs into candidate_facts | no |
| `dimension_weights_override` | `VariantSelector` `pattern_bias` multipliers (4.3.4 §8) | no |
| `proof_order_override[]` | `VariantSelector` proof category ordering | no |
| `primary_document_goal_override` | Layer 6 V2 prompt anchor | no |
| `section_emphasis[]` | section-by-section emphasis projection | no |
| `audience_tilt` | per-evaluator emphasis hint inside Layer 6 V2 | advisory |
| `risks[]` | Layer 6 V2 forbidden-category projection | advisory (compose with 4.2.6) |
| `pattern_label` | Langfuse stage span metadata; prompt anchor | no |
| `pattern_signature` | `DraftDoc.pattern_signature` back-ref; cache key | no |
| `pattern_status` | per-draft strictness regime (swapped_default → conservative) | no |
| `confidence.band` | downstream advisory | advisory |

4.3.4's `evidence_lineage_validator` (4.3.4 §9.2) re-asserts that
every persisted bullet, header element, and competency in the draft
references something in the pattern's `evidence_map`. Patterns are
the single allowlist; drafts are not allowed to pick outside.

### 14.2 4.3.5 Draft Grading, Selection, and Synthesis

For the synthesis step, 4.3.5 reads `patterns[]` from
`cv_assembly.pattern_selection` to:

- Determine cross-pattern affinity for fragment promotion (a
  fragment from pattern_2 may be promoted into the winner from
  pattern_1 only when both patterns include the same achievement_id
  in their respective `evidence_map`s).
- Identify which pattern slots are unfilled in the winner and may
  receive promotion.
- Compute `merge_algorithm_version`-aware diffs for the dossier.
- Read `pattern_label` to gate cross-pattern compatibility (per the
  4.3.5 cross-pattern compatibility table).

4.3.5 may NOT:

- introduce evidence outside the union of the three patterns'
  `evidence_map`s,
- re-derive `dimension_weights_override` or
  `primary_document_goal_override`,
- modify `header_picks` of the winning draft (those are frozen by
  4.3.4 from the pattern).

### 14.3 Persistence as the contract

The persisted `cv_assembly.pattern_selection` document is the single
source of truth for downstream consumers. There is no parallel
"selector service" that 4.3.4 / 4.3.5 may consult. If a downstream
needs information not in the persisted doc, the doc must be extended
(with a `PATTERN_SCHEMA_VERSION` bump and a 4.3.3 prompt-version
bump), not derived ad-hoc by the consumer.

## 15. Fail-Open / Fail-Closed

### 15.1 Fail-open: conservative role-family default pattern

The conservative role-family default is a deterministic fallback
pattern composed from:

- `lead_role_id = master_cv.most_recent_relevant_role_for(
    classification.primary_role_category)` (deterministic by
  `RoleData[].period.start_iso` descending, then by alphabetical
  `role_id`),
- `supporting_role_ids = next 2 roles by the same ordering`,
- `lead_project_ids = []`,
- `primary_document_goal_override = balanced` (canonical 4.2.2 enum),
- `proof_order_override[] = canonical 4.2.3 ProofType ordering`
  (no override),
- `dimension_weights_override = role_family_weight_priors` from
  4.2.5 §12.3 default table for the job's role family,
- `header_picks` sourced from
  `viability_bands.minimum_viable_truthful_header.*_ids` plus the
  default `visible_identity_candidate_id` and
  `lead_phrase_candidate_id`,
- `evidence_map` populated by selecting the top-K candidates from the
  preflight pool (§11) where K is from
  `cv_shape_expectations.counts.key_achievements`, with section
  emphasis driven by the role-family default in 4.2.2,
- `pattern_label = default_role_family`,
- `pattern_status = swapped_default`,
- `confidence.band = medium` (capped),
- `fit_rationale = "Conservative role-family default; pool insufficient
  for distinctive pattern emphasis."`.

### 15.2 Fail-open rules

- When `header_blueprint.status == partial`, patterns inherit
  `partial` status; record `upstream_partial=true` in
  `debug_context`.
- When ≥ 1 pattern fails diversity, evidence resolution after one
  repair pass, or pool insufficiency for its intended emphasis, the
  pattern is **swapped for the conservative default** per §15.1.
  Stage `status = partial`.
- When master-CV coverage is shallow for a pattern (e.g., insufficient
  `ai_relevance_band ≥ significant` evidence for an `ai_led`
  pattern), the LLM is asked to choose a different label from the
  enum first; if the next-choice label also lacks evidence, the
  pattern swaps to default.
- When `pre_enrichment.pain_point_intelligence.status in {partial,
  unresolved}`, salience scoring drops the proof-match factor;
  confidence is capped at `medium`.
- When two patterns are swapped, stage `status = degraded`.

### 15.3 Fail-closed rules

- All three patterns swapped to defaults → stage `status = failed`,
  job deadletters per 4.3 umbrella.
- Any `evidence_map` citation that does not resolve in master-CV
  AND repair (`drop_pattern + swap_to_default`) cannot heal it →
  stage `failed`.
- Any `dimension_weights_override` that cannot be clamped to sum-to-100
  (e.g., negative entries that would not normalize) → stage `failed`.
- Any `pattern_label` outside the §9.2 enum AND no closest-by-similarity
  match within 0.5 → pattern dropped, swapped to default; if all three
  fail this, stage `failed`.
- Any two patterns with identical `pattern_signature` after repair →
  stage `failed`.
- Any `ai_led` pattern with overall achievement-set
  `ai_relevance_band` < `significant` AND repair (clamp +
  swap_to_default) cannot heal → pattern swapped to default.
- Any `pool_growth_attempted` violation (the LLM emitted a
  `hero_proof_fragment_id` not in the pool) → `prune_to_pool`
  repair; if the pattern is left empty after pruning → swap to
  default.
- Title outside `header_blueprint.identity.chosen_title` → reject
  immediately; this is identity drift, not pool insufficiency. Repair
  not allowed; stage `failed`.

## 16. Tests And Evals

### 16.1 Unit tests (`tests/unit/cv_assembly/`)

- `test_preflight_pool_construction.py` — given a fixture master-CV,
  expected pool composition, including rejection cases.
- `test_salience_score.py` — table-driven over §11.3 inputs; expected
  `salience_norm` values; tie-break rules in §11.4.
- `test_pattern_signature_determinism.py` — same input → same
  signature, twice; ordering of inputs does not change signature.
- `test_pattern_validator.py` — one case per `rule_id` in §13.3
  (see §13.6).
- `test_pattern_validator_determinism.py` — two runs over identical
  inputs produce byte-identical `PatternValidatorReport`.
- `test_diversity_check.py` — Jaccard distance computation over
  achievement id sets; threshold default 0.35; edge cases (empty
  sets, identical sets, near-identical sets).
- `test_default_swap.py` — pool insufficiency triggers default swap;
  conservative default has the §15.1 shape; `confidence.band ≤ medium`.
- `test_pool_consumption.py` — picks within pool pass; picks outside
  fail; floor-unmet fails; upper-bound-exceeded fails.
- `test_dimension_weights_override.py` — sum-to-100 invariant; ±30 pp
  band; cap from 4.2.6 honored; negative values rejected.

### 16.2 Stage contract tests

- `StageDefinition` lookup returns the registered instance under
  `cv.pattern_selection`; `prerequisites = ("cv.header_blueprint",)`;
  `produces_fields = ("cv_assembly.pattern_selection",)`;
  `task_type == "cv.pattern_selection"`; `lane == "cv_assembly"`;
  `required_for_cv_assembled == True`.
- Idempotency-key composition matches §7.4.

### 16.3 Pool-consumption invariant tests

For every persisted `PatternSelectionDoc` in the eval corpus
(§16.6):

- every `header_picks.{visible_identity, lead_phrase, title}_id`
  resolves in the corresponding `header_blueprint` pool,
- every `evidence_map.header.*_ids[]` is a subset of the
  corresponding pool,
- the union of must-include floor ids ⊆ every pattern's evidence_map
  header ids,
- no pattern exceeds the upper-bound id sets,
- `pool_growth_attempted == false` in the validator report.

### 16.4 Determinism tests (load-bearing for SC6)

- `test_pattern_signature_determinism.py` (above).
- `test_pattern_validator_determinism.py` (above).
- `test_full_stage_determinism.py` — two runs of the full stage
  against the same input snapshot with a recorded LLM response (mock
  transport) produce byte-identical `PatternSelectionDoc`s except
  for `timing.*` fields, which are compared with tolerance.
- `test_canonical_serialization.py` — `canonical_pattern_input()`
  produces the same JSON for two equivalent dicts with different
  key orders.

### 16.5 Trace emission tests

Using a `FakeTracer`:

- stage span emitted with §17.4 metadata keys;
- substep spans `preflight`, `pool_read`, `salience_rank`,
  `prompt_build`, `llm_call`, `schema_repair` (when fired),
  `validator`, `persist` emitted in correct nesting;
- events `pattern_emitted` (3 per run), `degraded_to_default` (when
  fired), `pattern_dropped` (when fired), `validator_repair_applied`
  (when fired) emitted with required metadata;
- no forbidden keys leak (grep assertion on serialized payload —
  no full `evidence_map` body, no full `fit_rationale` beyond 240
  chars, no full debug body in span metadata).

### 16.6 Regression corpus

`data/eval/validation/cv_assembly_4_3_3_pattern_selection/`:

- `cases/<job_id>/input/` — frozen `level-2` slice with all 4.2
  subdocuments and the 4.3.2 `header_blueprint`, plus a frozen
  `data/master-cv/` snapshot.
- `cases/<job_id>/expected/patterns.json` — expected pattern set
  (with allowed bounded variance: any string preview, ordering
  within tied salience).
- `cases/<job_id>/expected/diversity_report.json` — expected
  diversity report.
- `cases/<job_id>/expected/pool_consumption_report.json` — expected
  pool consumption report.
- `cases/<job_id>/expected/validator_report.json` — expected
  validator report (byte-equal asserted).
- `cases/<job_id>/ground_truth.md` — reviewer rationale.

Minimum 20 cases; ≥ 3 per role family
(`applied_ai_engineering`, `ai_platform_engineering`, `ml_research`,
`staff_software_engineering`, `engineering_management`,
`director_plus`); plus adversarial cases (thin pool — only one
viable pattern; AI-heavy JD with insufficient AI bands; leadership
JD with insufficient scope bands; identical evidence across roles
that would collapse to non-diverse signatures).

### 16.7 Validator API tests

- `validate_patterns(..., mode="selection")` allows repair and
  produces `repairs_applied[]`.
- `validate_patterns(..., mode="draft_consumption")` does not allow
  repair and produces `status=failed` for any `severity=blocking`
  violation.
- Mode-difference fixture in §13.6.
- Validator does not call any I/O — pure function (asserted by
  patching socket/Mongo/Open and ensuring no calls during validator
  invocation).

### 16.8 Repair-action tests

One per action in §13.4; pre-repair and post-repair pattern docs
captured; `repairs_applied[]` shape matches §13.2.

### 16.9 Diversity-threshold tests

- 3 patterns with pairwise Jaccard 0.5 → `diversity_status=ok`.
- 3 patterns with one pair at 0.2 → `diversity_status=tight`,
  default-swap considered if no other diversity criterion (lead role
  / goal) holds.
- 3 patterns with 2 pairs at 0.2 → `diversity_status=default_swap_required`
  on pattern_3.

### 16.10 Degraded-path tests

- Header blueprint `status=partial` → pattern selection inherits
  partial.
- Pain-point-intelligence `status=unresolved` → salience drops
  proof_match factor; stage emits with `confidence.band ≤ medium`.
- Two patterns swapped → `status=degraded`.
- Three patterns swapped → `status=failed`.

### 16.11 Snapshot / persistence tests

- Persisted `cv_assembly.pattern_selection` matches the schema in §9.
- Compact projection (if any) does not include full `evidence_map`
  bodies or `fit_rationale` bodies; only counts and ids.
- `cv_assembly.stage_states.cv.pattern_selection.trace_ref` is
  populated.
- `cv_assembly_stage_runs` has a row with `trace_id`, `trace_url`,
  `prompt_version`, tokens, cost.

### 16.12 Downstream compatibility tests with 4.3.4

- Given a fixture `PatternSelectionDoc`, the 4.3.4 `PatternContext`
  builder constructs without `KeyError` on any required field.
- `VariantSelector(pattern_bias=...)` accepts the
  `dimension_weights_override` and produces a deterministic ordering
  (assertions on multiplied scores).
- The 4.3.4 `evidence_lineage_validator` rejects a draft that
  references an achievement_id outside the pattern's `evidence_map`.
- `DraftDoc.pattern_signature` matches the source pattern's signature.

### 16.13 Live smoke tests

- `scripts/smoke_pattern_selection.py` — loads `.env` from Python,
  fetches one job by `_id`, runs the stage locally against live
  Codex/LLM, validates output, prints heartbeat every 15 s.

### 16.14 Eval metrics

Reviewer rubric, recorded in `reports/`:

- **Diversity threshold compliance** (target = 1.00; SC7).
- **Evidence resolution rate** (target = 1.00; SC2).
- **Pool consumption compliance** (target = 1.00; SC3).
- **Pattern label enum compliance** (target = 1.00).
- **Reviewer usefulness** (target ≥ 0.80) — reviewer scores each
  pattern on (1) "would a real evaluator find this framing
  defensible?", (2) "would the three patterns produce meaningfully
  different drafts?", (3) "are the pattern picks justified by the
  cited evidence?".
- **Fit rationale grounding** (target ≥ 0.90) — fit rationales cite
  ≥ 2 presentation_contract ids and ≥ 1 master-CV id.
- **Determinism rate** (target = 1.00; SC6) — two consecutive runs
  produce identical signatures and identical validator reports.
- **Default-swap rate** (target ≤ 10% in production; tracked).
- **Stage latency p95** (report only; target < 30 s on canary
  model).

### 16.15 Regression gate

Block rollout if:

- diversity compliance regresses,
- any evidence citation fails to resolve,
- reviewer usefulness drops > 5 points,
- two patterns collapse to identical signatures in ≥ 5% of cases,
- determinism rate < 1.00,
- default-swap rate > 25% in canary.

## 17. Langfuse Tracing Contract

Inherits 4.3 umbrella verbatim. Stage-specific rules below are
normative.

### 17.1 Canonical trace, stage span, substep spans

- Trace: `scout.cv.run` (4.3 umbrella).
- Job span: `scout.cv.job` with `langfuse_session_id=job:<level2_id>`.
- Stage span: `scout.cv.pattern_selection`.
- Substep spans (only those that meaningfully time work):
  - `scout.cv.pattern_selection.preflight` — §8 prereq checks.
  - `scout.cv.pattern_selection.pool_read` — read 4.3.2 pools and
    project into prompt payload.
  - `scout.cv.pattern_selection.salience_rank` — §11.3 deterministic
    rank.
  - `scout.cv.pattern_selection.prompt_build`.
  - `scout.cv.pattern_selection.llm_call.primary` (+ `.fallback` if
    fallback fired).
  - `scout.cv.pattern_selection.schema_repair` (only when fires).
  - `scout.cv.pattern_selection.validator` — §13 invocation.
  - `scout.cv.pattern_selection.persist`.

No per-pattern child spans. Cardinality is bounded by the §9
schema (3 patterns); per-pattern detail goes into events and
metadata, never spans.

### 17.2 Events

- `scout.cv.pattern_selection.cache.hit` / `.cache.miss`.
- `scout.cv.pattern_selection.pattern_emitted` — one per pattern
  with metadata `{pattern_id, pattern_label, pattern_signature,
  lead_role_id, ai_relevance_band_max, confidence.band,
  pattern_status}`.
- `scout.cv.pattern_selection.degraded_to_default` — when a pattern
  is swapped to the role-family default; metadata
  `{pattern_id, reason, pool_insufficiency_kinds}`.
- `scout.cv.pattern_selection.pattern_dropped` — when
  `drop_pattern` action fires; metadata `{pattern_id, rule_id}`.
- `scout.cv.pattern_selection.validator_repair_applied` — one per
  action; metadata `{pattern_id, rule_id, action,
  before_signature, after_signature}`.
- `scout.cv.pattern_selection.diversity_report` — Jaccard distances
  and uniqueness booleans.
- `scout.cv.pattern_selection.fail_open` — with `fail_open_reason`.
- `scout.cv.pattern_selection.rejection` — on terminal invariant
  violation; metadata `{rule_id, severity}`.
- Lifecycle events (`claim`, `enqueue_next`, `retry`,
  `deadletter`, `release_lease`) are 4.3 umbrella, not redefined.

### 17.3 Required metadata on every span/event

`job_id`, `level2_id`, `correlation_id`, `langfuse_session_id`,
`run_id`, `worker_id`, `task_type`, `stage_name`, `attempt_count`,
`attempt_token`, `input_snapshot_id`,
`master_cv_checksum`, `presentation_contract_checksum`,
`header_blueprint_checksum`, `jd_checksum`,
`lifecycle_before`, `lifecycle_after`, `work_item_id`.

### 17.4 Stage-specific metadata (stage span, on end)

- `status` ∈ `{completed, partial, degraded, failed}`,
- `source_scope` ∈ `{full, jd_plus_research, jd_only_fallback}`,
- `pattern_count_requested` (always 3),
- `pattern_count_persisted`,
- `degraded_pattern_count`,
- `default_swap_count`,
- `pool_insufficiency_count`,
- `header_pool_sizes` — `{title: int, visible_identity: int,
  lead_phrase: int, hero_proof: int, credibility: int,
  differentiator: int, proof_anchor: int, differentiator_anchor: int}`,
- `candidate_achievement_pool_size`,
- `selected_achievement_count`,
- `diversity_threshold` (default 0.35),
- `mean_jaccard`,
- `min_jaccard`,
- `signature_count` (always 3 unless degraded),
- `validator_status` ∈ `{pass, repair_attempted, failed}`,
- `validator_repairs_applied_count`,
- `confidence.band`,
- `prompt_version`, `prompt_git_sha`,
- `cache_hit: bool`,
- `fail_open_reason` when `status ∈ {partial, degraded}`: one of
  `pool_insufficiency`, `evidence_thin`, `pain_intel_unavailable`,
  `header_blueprint_partial`, `presentation_contract_partial`,
  `schema_repair_exhausted`, `llm_terminal_failure`.

### 17.5 LLM call outcome classifications

`llm_call.*` spans carry the iteration-4 transport outcome
classification: `success | unsupported_transport |
error_missing_binary | error_timeout | error_subprocess |
error_no_json | error_schema | error_exception`.
`schema_valid: bool` is always set.

### 17.6 Mongo trace refs

The stage's `trace_id` and `trace_url` flow into:

- `cv_assembly_stage_runs` — for this row,
- `cv_assembly_job_runs` — aggregate job-level,
- `cv_assembly.stage_states.cv.pattern_selection.trace_id/url`,
- `cv_assembly.pattern_selection.trace_ref` (projection).

An operator opening a single level-2 job in the UI reaches the
Langfuse trace in one click.

### 17.7 Forbidden in Langfuse

- full `evidence_map` body,
- full `fit_rationale` text beyond a 240-char preview per pattern,
- full `pool_consumption_report.per_pattern[].*` bodies,
- full `validator_report.per_pattern[].violations[].detail` bodies
  beyond a 240-char preview,
- full `debug_context` body,
- raw LLM prompts unless `_sanitize_langfuse_payload` is applied
  and `LANGFUSE_CAPTURE_FULL_PROMPTS=true`.

Previews capped at 240 chars via `_sanitize_langfuse_payload`.

### 17.8 What may live only in `debug_context`

- raw candidate-evidence-pool entries,
- full salience-score table,
- full LLM request ids and raw repair prompts,
- full validator-trace per-pattern,
- per-pattern diversity-computation trace,
- defaults applied with full descriptive strings.

### 17.9 Cardinality and naming safety

- substep span names are a fixed, small set (§17.1),
- per-pattern detail is metadata + events, never spans,
- repair attempts bounded at 1 → bounded `schema_repair` and
  `validator_repair_applied` cardinality,
- LLM fallback bounded → ≤ 2 `llm_call.*` spans.

### 17.10 Operator debug checklist (normative)

An operator must be able to diagnose each of these from Mongo →
trace in < 2 minutes:

- slow stage execution → inspect `llm_call.primary.duration_ms` and
  `salience_rank.duration_ms`.
- pool insufficiency → look at `degraded_to_default` events and
  `pool_insufficiency_count` metadata.
- diversity collapse → `diversity_report` event with `min_jaccard`.
- validator repair → `validator_repair_applied` event with
  `rule_id` and `action`.
- evidence resolution failure → `rejection` event with
  `rule_id=evidence_unresolved`.
- schema-repair retry usage → `schema_repair` span count.
- downstream incompatibility → 4.3.4 `draft_assembly` span with
  `pattern_id` mismatch or `evidence_lineage_validator` rejection.

## 18. VPS End-To-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This section is the live-run chain.

### 18.1 Local prerequisite tests before touching VPS

- `pytest -k "pattern_selection"` clean.
- `pytest tests/unit/cv_assembly/test_pattern_signature_determinism.py
  tests/unit/cv_assembly/test_pattern_validator_determinism.py` clean.
- `python -m scripts.cv_assembly_dry_run --stage pattern_selection
  --job <level2_id> --mock-llm` clean.
- Langfuse sanitizer test green.

### 18.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path;
- verify the deployed `stage_registry.py` contains
  `cv.pattern_selection` and the flag is on:
  `grep -n "cv.pattern_selection" /root/scout-cron/src/cv_assembly/stage_registry.py`,
  `grep -n "CV_ASSEMBLY_PATTERN_SELECTION_ENABLED"
  /root/scout-cron/src/cv_assembly/config_flags.py`;
- verify `validators/pattern_validator.py` exists and exposes
  `validate_patterns`;
- verify `prompts/pattern_selection.py` contains
  `build_p_pattern_selection`;
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`;
- deployment is file-synced; do not `git status`.

### 18.3 Target job selection

- Pick a real `cv_ready` `level-2` job with:
  - `pre_enrichment.outputs.{jd_facts, classification,
    research_enrichment, stakeholder_surface,
    pain_point_intelligence, presentation_contract}` all at
    `status ∈ {completed, partial}`,
  - `cv_assembly.header_blueprint.status ∈ {completed, partial}`,
  - master-CV loader v2 returns no schema errors.
- Prefer a mid-seniority IC or EM role with rich research and a
  populated header blueprint.
- Record `_id`, `jd_checksum`, `header_blueprint_checksum`, and
  current `input_snapshot_id`.
- Optionally pick a second job with thin pools (header blueprint
  `status=partial`) to exercise §15 fail-open.

### 18.4 Upstream artifact verification

Before launching:

- verify `cv_assembly.header_blueprint` is non-empty for the chosen
  job;
- verify pools are non-empty:
  - `identity.title_candidates`, `visible_identity_candidates`,
  - `tagline_ingredients.lead_phrase_candidates`,
    `proof_anchor_pool`, `differentiator_anchor_pool`,
  - `hero_proof_fragments`, `credibility_markers`,
  - `viability_bands.minimum_viable_truthful_header.*`;
- verify all four `presentation_contract` subdocuments are persisted:
  `document_expectations`, `cv_shape_expectations`,
  `ideal_candidate_presentation_model`,
  `experience_dimension_weights`,
  `truth_constrained_emphasis_rules`.

If any verification fails, recompute via
`scripts/recompute_snapshot_id.py --job <_id>` and re-enqueue
`cv.header_blueprint` via `scripts/enqueue_stage.py` rather than
touching `work_items` directly.

### 18.5 Single-stage run path (fast path)

Preferred. A wrapper in `/tmp/run_pattern_selection_<job>.py`:

- `from dotenv import load_dotenv; load_dotenv("/root/scout-cron/.env")`,
- reads `MONGODB_URI`,
- builds `StageContext` via the worker-compatible factory
  (`build_cv_assembly_stage_context_for_job`),
- runs `PatternSelectionStage().run(ctx)` directly,
- prints a heartbeat line every 15 s during LLM work with: wall
  clock, elapsed, last substep, last validator phase, Codex PID if
  any, Codex stdout/stderr tail.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_pattern_selection_<job>.py \
  > /tmp/pattern_selection_<job>.log 2>&1 &
```

### 18.6 Full-chain path (fallback)

If the fast path is blocked by `StageContext` construction drift:

- enqueue `work_items` for `cv.pattern_selection` only,
- start the cv_assembly worker with
  `CV_ASSEMBLY_STAGE_ALLOWLIST="cv.pattern_selection"`,
- same `.venv`, `python -u`, Python-side `.env`, `MONGODB_URI`
  discipline,
- same operator heartbeat.

### 18.7 Required launcher behavior

- `.venv` activated (absolute path to `.venv/bin/python`),
- `python -u` unbuffered,
- `.env` loaded from Python, not `source .env`,
- `MONGODB_URI` present,
- inner Codex PID and first 128 chars of stdout / stderr logged on
  every heartbeat,
- isolated workdir `/tmp/cv-pattern-selection-<job>/` for any inner
  Codex subprocess (the stage itself does no codex calls; included
  for parity if future repair retries require codex).

### 18.8 Heartbeat requirements

- stage-level heartbeat every 15-30 s from the wrapper;
- lease heartbeat every 60 s by the worker;
- silence > 90 s = stuck-run flag.

### 18.9 Expected Mongo writes

On success:

- `cv_assembly.pattern_selection` collection (or subdocument):
  one doc keyed by `(level2_id, input_snapshot_id, prompt_version)`;
- `level-2.cv_assembly.pattern_selection`:
  populated with the persisted `PatternSelectionDoc`;
- `level-2.cv_assembly.stage_states.cv.pattern_selection`:
  `status=completed | partial | degraded`,
  `attempt_count`, `lease_owner` cleared,
  `trace_id`, `trace_url` set,
  `validator_report.status`,
  `pool_consumption_report.any_default_swap`;
- `cv_assembly_stage_runs`: one row with `status`, `trace_id`,
  `trace_url`, `provider_used`, `model_used`, `prompt_version`,
  `tokens_input`, `tokens_output`, `cost_usd`;
- `cv_assembly_job_runs`: aggregate updated;
- `work_items`: this row `status=completed`;
- on success and stage `required_for_cv_assembled`, three
  `cv.draft_assembly` work items enqueued (one per `pattern_id`).

### 18.10 Expected Langfuse traces

In the same trace (`scout.cv.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- `scout.cv.pattern_selection` stage span with §17.4 metadata,
- `scout.cv.pattern_selection.preflight`,
- `scout.cv.pattern_selection.pool_read`,
- `scout.cv.pattern_selection.salience_rank`,
- `scout.cv.pattern_selection.prompt_build`,
- `scout.cv.pattern_selection.llm_call.primary`
  (+ `.fallback` if fired),
- `scout.cv.pattern_selection.validator`,
- `scout.cv.pattern_selection.persist`,
- 3 `pattern_emitted` events (or fewer if degraded),
- 1 `diversity_report` event,
- canonical lifecycle events.

### 18.11 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/pattern_selection_<job>.log`,
- inspect launcher PID,
- inspect Mongo:
  `level-2.cv_assembly.stage_states.cv.pattern_selection.lease_expires_at`,
- if lease is expiring and no progress, kill the launcher; wait for
  the prior PID to be confirmed gone before restarting.

Silence is not progress.

### 18.12 Acceptance criteria

- log ends with
  `PATTERN_SELECTION_RUN_OK job=<id> status=<status> trace=<url>`;
- Mongo writes match §18.9;
- Langfuse trace matches §18.10;
- stage output validates against `PatternSelectionDoc` schema (§9);
- spot-check: 3 distinct `pattern_signature`s, every `evidence_map`
  citation resolves in master-CV, every header pick is in the
  4.3.2 pool, no pool growth attempted, validator status
  `pass | repair_attempted`;
- fail-open run (thin-pool job) returns `status=partial` with
  `fail_open_reason in {pool_insufficiency, evidence_thin}`, not
  deadletter.

### 18.13 Artifact / log / report capture

Create `reports/pattern-selection/<job_id>/` containing:

- `run.log` — full stdout/stderr,
- `stage_output.json` — the emitted `PatternSelectionDoc`,
- `validator_report.json` — the validator output,
- `diversity_report.json`,
- `pool_consumption_report.json`,
- `trace_url.txt` — Langfuse URL,
- `stage_runs_row.json` — `cv_assembly_stage_runs` row dump,
- `mongo_writes.md` — human summary of §18.9 checks,
- `acceptance.md` — pass/fail list for §18.12.

## 19. Safety / Anti-Hallucination

Restated as hard implementation rules; enforced by the deterministic
post-pass and by `pattern_validator` (§13).

- **No citation without an evidence ref.** Every achievement / variant
  ref is resolved against master-CV at persist time; an unresolved
  citation triggers `evidence_unresolved` (severity blocking).
- **No title rewriting.** Patterns cannot override `chosen_title` or
  `chosen_title_strategy`. Identity is frozen by 4.3.2.
- **No AI climbing.** A pattern cannot boost `ai_relevance_band`
  beyond the underlying achievement's band, and cannot enable
  `ai_highlights` whose anchors do not have
  `ai_relevance_band ≥ significant`.
- **No scope climbing.** `lead_role_id` must have metadata bands
  consistent with the pattern's emphasis (e.g., a `leadership_led`
  pattern cannot choose a role whose
  `seniority.managerial_level == ic`).
- **No invented projects.** Every `project_id` resolves in
  `data/master-cv/projects/`.
- **No pool growth.** `hero_proof_fragment_ids[]`,
  `credibility_marker_ids[]`, and `differentiator_ids[]` are subsets
  of 4.3.2 pools. Violations are repaired via `prune_to_pool`; if
  pruning empties the pattern, it swaps to default.
- **No identity inflation.** `visible_identity` and `lead_phrase`
  picks are bounded to 4.3.2 pools; composing new strings is forbidden.
- **No cross-candidate claims.** Patterns reason exclusively over the
  single candidate's pinned master-CV snapshot.
- **No evidence outside the canonical pools.** `evidence_map.*` ids
  must resolve in master-CV (achievements, variants, skills,
  projects) or in 4.3.2 pools (hero_proof, credibility,
  differentiator).
- **No protected-trait inference, no clinical profiling, no private
  stakeholder motives.**
- **No metric invention.** The salience formula and the validator
  refer only to `metric_band` ordinals; free-form metrics in
  `fit_rationale` or `evidence[]` text are rejected by a regex check
  on numeric tokens (digits + `%`, `x`, `M`, `k`, `B`) — only allowed
  when copied verbatim from the cited achievement source fragment.

The deterministic post-pass and `pattern_validator` are the single
sources of truth for enforcement; the LLM prompt instructs but does
not adjudicate.

## 20. Cross-Artifact Invariants

- `patterns.length == 3` unless `status == failed`.
- Every pattern's `header_picks.title_candidate_id` resolves to the
  same string as `header_blueprint.identity.chosen_title`.
- Every pattern cites at least one role from master-CV as
  `lead_role_id`.
- Every pattern's `section_emphasis[]` keys are a subset of the
  canonical 4.2.2 section enum (`DocumentSectionId`), and a superset
  of the sections declared in
  `cv_shape_expectations.section_order[]`.
- Every `evidence_map` key resolves in master-CV (role id, project
  id, achievement id, variant id, skill id).
- Every `dimension_weights_override` keys ⊆ canonical 4.2.5
  `ExperienceDimension` enum; values are non-negative integers
  summing to 100.
- Every `dimension_weights_override` entry is within ±30 percentage
  points of `presentation_contract.experience_dimension_weights.overall_weights`
  for that dimension (recommendation; calibrated by §16.14
  `default_swap_rate`).
- Every `dimension_weights_override` entry honors the
  `truth_constrained_emphasis_rules.cap_dimension_weight` rules from
  4.2.6 — clamped via `clamp_weight_override` if exceeded.
- Every `proof_order_override[]` entry ∈ canonical 4.2.3
  `ProofType` enum; the override is a permutation OR a strict
  subset (subset is allowed when the pattern intentionally drops a
  proof category for emphasis reasons).
- Every `primary_document_goal_override` ∈ canonical 4.2.2
  `PrimaryDocumentGoal` enum.
- Title choices remain within 4.3.1 allowlist
  (`role_metadata.acceptable_titles`) and within 4.2.4
  `acceptable_titles[]` filter — both already validated upstream by
  4.3.2; no re-derivation here.
- Selected evidence satisfies 4.2.6 truth constraints: no
  `forbidden_claim_pattern`, no `cap_dimension_weight` violation, no
  rule whose `applies_to` matches a pattern emphasis.
- Pattern diversity does not break header viability bands: even when
  patterns are diverse, every pattern still includes the
  `minimum_viable_truthful_header` floor.
- Degraded / default patterns are still truthful and validator-clean
  — `swapped_default` is not a fail-open for evidence resolution; it
  is a fail-open only for emphasis distinctiveness.
- `pattern_signature` is unique across the three patterns. Collisions
  trigger `pattern_signature_collision` and `swap_to_default` on the
  later-indexed pattern.
- `audience_tilt` keys ⊆
  `stakeholder_surface.evaluator_coverage_target[]`. Keys outside
  the coverage target are nulled with a `normalization_events[]`
  entry.

If any invariant fails after one deterministic repair retry, the
stage runs §15 (fail-open swap) or fails closed (per §15.3).

## 21. Operational Catalogue

### 21.1 Stage owner

Owned by the cv_assembly worker.
Module: `src/cv_assembly/stages/pattern_selection.py`.
Stage definition: `src/cv_assembly/stage_registry.py`.

### 21.2 Prerequisite artifacts

- `cv_assembly.header_blueprint` (4.3.2) — hard prerequisite (§8).
- `pre_enrichment.presentation_contract.{document_expectations,
  cv_shape_expectations, ideal_candidate_presentation_model,
  experience_dimension_weights, truth_constrained_emphasis_rules}` —
  hard prerequisite (degraded-allowed for the last three per §8.2).
- `pre_enrichment.pain_point_intelligence` — degraded-allowed (§8.2).
- `pre_enrichment.{classification, jd_facts, stakeholder_surface,
  research_enrichment}` — read-only.
- Master-CV via loader v2 (4.3.1) — hard prerequisite.

### 21.3 Persisted Mongo locations

| What | Location |
|---|---|
| Full artifact | `cv_assembly.pattern_selection` collection (or subdocument), unique filter `(level2_id, input_snapshot_id, prompt_version)` |
| Stage output ref | `level-2.cv_assembly.pattern_selection` |
| Stage state | `level-2.cv_assembly.stage_states.cv.pattern_selection` |
| Stage run audit | `cv_assembly_stage_runs` |
| Job run aggregate | `cv_assembly_job_runs` |
| Work item | `work_items`, `task_type=cv.pattern_selection` |
| Alerts | `cv_assembly_alerts` (on deadletter only, rate-limited) |

### 21.4 Stage-run records touched

`cv_assembly_stage_runs` row with: `status`, `trace_id`, `trace_url`,
`provider_used`, `model_used`, `prompt_version`, `tokens_input`,
`tokens_output`, `cost_usd`, `validator_status`,
`degraded_pattern_count`, `default_swap_count`,
`pool_insufficiency_count`, `fail_open_reason` (when present).

### 21.5 Work-item semantics

- enqueued by the DAG sweeper when
  `cv_assembly.header_blueprint.status ∈ {completed, partial}` and
  `input_snapshot_id` matches the current job snapshot;
- payload carries `input_snapshot_id`, `attempt_token`,
  `correlation_id`, `master_cv_checksum`,
  `header_blueprint_checksum`, `presentation_contract_checksum`,
  `jd_checksum`, `level2_id`;
- claimed atomically via `StageWorker.claim` with lease;
- on success, Phase A writes `cv_assembly.pattern_selection` and
  pushes three `cv.draft_assembly` work items (one per pattern id)
  onto `pending_next_stages`; Phase B drains the fan-out.

### 21.6 Cache semantics

- cache key: `input_snapshot_id` (composed per §7.4);
- cache stored in the `cv_assembly.pattern_selection` collection
  itself, filtered by `(level2_id, input_snapshot_id)`;
- hit ⇒ skip LLM, project cached doc into a new
  `attempt_token`-keyed write,
- miss ⇒ full pipeline,
- bust on any change to: `master_cv_checksum`,
  `header_blueprint_checksum`, `presentation_contract_checksum`,
  `jd_checksum`, `PROMPT_VERSION`, `PATTERN_SCHEMA_VERSION`,
- emits `scout.cv.pattern_selection.cache.hit|miss` events with
  metadata `{cache_key, hit_reason, ttl_remaining_s,
  upstream_blueprint_status}`.

### 21.7 Retry / repair behavior

- `max_attempts = 3` at the work-item level;
- one in-stage schema-repair retry permitted (§15.2; only for
  recoverable defects: pool-violation, dimension-weights-off,
  forbidden-category, evidence-unresolved on ≤ 1 ref per pattern);
- one in-stage validator repair pass per pattern (§13.4);
- `job_fail_policy=fail_closed` per 4.3 umbrella when stage
  `status=failed`;
- `job_fail_policy=fail_open` (downstream proceeds with degraded
  pattern set) when stage `status ∈ {partial, degraded}`.

### 21.8 Heartbeat expectations

- stage heartbeat every 60 s by the worker
  (`CV_ASSEMBLY_STAGE_HEARTBEAT_SECONDS=60`);
- the stage must not hold CPU for more than 30 s between yield
  points (preflight, salience-rank, LLM call, validator);
- launcher-side wrapper (§18) emits operator heartbeat every
  15-30 s.

### 21.9 Feature flags

- `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED` — master flag for the
  stage. Off: stage not registered; 4.3.4 `cv.draft_assembly` does
  not run.
- `CV_ASSEMBLY_PATTERN_CONSUMED_BY_DRAFTS` — gates whether 4.3.4
  reads `cv_assembly.pattern_selection`. Off: 4.3.4 falls back to a
  single-pattern Layer 6 V2 run (one draft only).
- `CV_ASSEMBLY_PATTERN_SELECTION_DETERMINISTIC_ONLY` — debug-only;
  forces all three patterns to `swapped_default` per role family.
  Used during initial canary to verify the deterministic pipeline
  without the LLM.

### 21.10 Operator-visible success / failure signals

- `level-2.cv_assembly.stage_states.cv.pattern_selection.status` —
  `pending | leased | completed | failed | deadletter`;
- `level-2.cv_assembly.pattern_selection.status` —
  `completed | partial | degraded | failed`;
- `cv_assembly_stage_runs` row with `trace_id`, `trace_url`,
  `fail_open_reason` (when present);
- `cv_assembly_alerts` row only on deadletter.

### 21.11 Downstream consumers

- `cv.draft_assembly` (4.3.4) — fan-out, one per pattern id (§14.1).
- `cv.grade_select_synthesize` (4.3.5) — reads patterns for synthesis
  cross-pattern affinity (§14.2).
- `cv.dossier` (4.3.7) — reads `pattern_label` and
  `pattern_signature` for dossier UI; reads `fit_rationale` for the
  per-pattern explanation card.

### 21.12 Rollback strategy

- Toggle `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED=false`; downstream
  4.3.4 falls back to single-pattern Layer 6 V2 run via
  `CV_ASSEMBLY_PATTERN_CONSUMED_BY_DRAFTS=false`;
- existing `cv_assembly.pattern_selection` documents remain for
  audit; no deletion;
- no schema migration on rollback.

## 22. Open-Questions Triage

| Question | Triage | Resolution-or-recommendation |
|---|---|---|
| What is the deterministic `pattern_signature` rule? | must-resolve | **(resolved)** §12 — `sha256:` + `hashlib.sha256(json.dumps(canonical_input, sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()`. Canonical input enumerated; replay guarantee asserted by §16.4 tests. |
| What is the salience-score formula? | must-resolve | **(resolved)** §11.3 — `dimension_weight × (1 + ordinal(scope_band)) × (1 + ordinal(metric_band)) × (1 + ordinal(ai_relevance_band)) × (1 + proof_match_weight)`, normalized to [0,1] by max. AI factor neutralized when `ai_intensity ∈ {none, unknown}`. Tie-break in §11.4. |
| What is the `pattern_validator` API? | must-resolve | **(resolved)** §13 — `validate_patterns(pattern_doc, header_blueprint, master_cv, presentation_contract, *, mode={"selection","draft_consumption"}, tracer)`, `PatternValidatorReport` shape, allowed actions `{prune_to_pool, clamp_band, clamp_weight_override, swap_to_default, drop_pattern}`, one-pass bound, no LLM in repair, byte-determinism guaranteed. |
| What is the pool-consumption contract with 4.3.2? | must-resolve | **(resolved)** §10 — pool vs pick semantics; must-include floor and upper-bound rules; per-pattern title pick rule; pool insufficiency triggers per-pattern swap to default; no retroactive growth. |
| What hard prerequisites must be satisfied before 4.3.3 enables? | must-resolve | **(resolved)** §8.1 — `cv.header_blueprint.status ∈ {completed, partial}`; non-empty pools and viability bands; `MASTER_CV_BLUEPRINT_V2_ENABLED=true`; canonical enums resolvable. Degraded path bounded by §8.4. |
| What is the canonical owner of the `ExperienceDimension` enum used by `dimension_weights_override`? | must-resolve | **(resolved)** §11.7 + §20 — 4.2.5 owns `ExperienceDimension`; 4.3.3 imports it; deviation from `overall_weights` bounded ±30 pp; cap rules from 4.2.6 honored. |
| What is the canonical owner of the `ProofType` enum used by `proof_order_override[]`? | must-resolve | **(resolved)** §11.6 + §20 — 4.2.3 owns `ProofType`; 4.3.3 imports it; `proof_order_override[]` is a permutation or subset, never extension. |
| What is the canonical owner of the `PrimaryDocumentGoal` enum used by `primary_document_goal_override`? | must-resolve | **(resolved)** §20 — 4.2.2 owns `PrimaryDocumentGoal`; values listed in 4.2.2 §4.3. |
| Should the diversity Jaccard threshold (default 0.35) vary per role family? | safe-to-defer | v1: global 0.35. Recommend per-role-family calibration in 4.3.8 once eval corpus produces enough signal — narrow careers (e.g., 100% AI engineering) likely benefit from a lower threshold (0.25) since their achievement sets overlap heavily by construction. Make the default override-capable in `data/eval/cv_assembly/diversity_thresholds.json`. |
| Should `pattern_label` be enum-bounded or registry-extensible? | safe-to-defer | v1: literal enum in `models.py` per §9.2. Enum bumps require a prompt-version bump. Move to a registry only after eval shows three or more legitimate labels missing from the enum across multiple role families. |
| Should we support **two** patterns for narrow careers? | safe-to-defer | v1: keep three; allow third to be `default_role_family` per §15.1. Revisit after bench if the swap-rate consistently exceeds 25% for narrow-career corpora. |
| Should pattern choice influence the choice of grading model in 4.3.5? | safe-to-defer | v1: no — grading uses one rubric. Revisit only if patterns show systematic grade bias. |
| Should the evidence pool include cross-role composites (e.g., a pattern arguing about consistent cross-role themes)? | safe-to-defer | v1: composites attach via `lead_project_ids[]`. Richer composite modeling deferred to 4.3.8 corpus-driven proposal. |
| Should the diversity threshold be learned from reviewer-scored eval data rather than hard-coded? | safe-to-defer | v1: hard-coded at 0.35; configurable in `data/eval/cv_assembly/diversity_thresholds.json`; revisit when corpus reaches 50+ scored cases. |
| Is the ±30 pp `dimension_weights_override` deviation band the right number? | safe-to-defer | v1: 30 pp recommendation, calibrated by `default_swap_rate` metric in §16.14. Tighten if drift is observed (e.g., pattern label `architecture_led` consistently produces deviations > 30 pp); loosen if it forces excess default swaps. |
| Should the stakeholder_variant_weights from 4.2.5 bias `audience_tilt` per pattern? | safe-to-defer | v1: yes — `audience_tilt` per pattern is seeded from `stakeholder_variant_weights` for the matching evaluator key, but only as a soft bias; the hard authority is `dimension_weights_override` at the overall level. |
| Should signature-collision repair re-roll the LLM rather than swap to default? | safe-to-defer | v1: swap to default. LLM re-roll is non-deterministic and breaks SC6. Reconsider only if the swap rate for collision is the dominant cause of partial status. |

## 23. Primary Source Surfaces

- `plans/iteration-4.3-candidate-evidence-assembly-grading-and-publishing.md`
- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`
- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
- `plans/iteration-4.3.4-multi-draft-cv-assembly.md`
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `docs/current/missing.md`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md`
- `src/layer6_v2/variant_selector.py` (for scoring prior art)
- `src/layer6_v2/types.py`
- `src/preenrich/blueprint_models.py` (canonical enums)
- `src/cv_assembly/validators/header_validator.py` (validator-pattern
  template per 4.3.2 §11.2)

## 24. Implementation Targets

- `src/cv_assembly/stages/pattern_selection.py` (new) — work-item
  worker entrypoint; runs preflight, salience rank, LLM call,
  validator, persist.
- `src/cv_assembly/prompts/pattern_selection.py` (new) — prompt
  builder `build_p_pattern_selection`; constraints reflect §10, §11,
  §19, §20.
- `src/cv_assembly/models.py` — add `PatternSelectionDoc`,
  `PatternDoc`, `EvidenceMapDoc`, `HeaderPicksDoc`,
  `SectionEmphasisDoc`, `RoleEmphasisDoc`, `AudienceTiltDoc`,
  `PatternDiversityReport`, `PoolConsumptionReport`,
  `PatternValidatorReport`, `PatternSelectionDebug`,
  `PatternLabel` enum, `PatternStatus` enum, `PatternValidatorMode`
  literal, `PATTERN_SCHEMA_VERSION` constant.
- `src/cv_assembly/validators/pattern_validator.py` (new) — §13
  validator API, fixtures under `tests/unit/cv_assembly/`.
- `src/cv_assembly/preflight/pattern_preflight.py` (new) — §11
  candidate-pool construction, salience formula, tie-break rules,
  enum-to-numeric mapping table.
- `src/cv_assembly/defaults/role_family_default_pattern.py` (new) —
  §15.1 conservative-default composer.
- `src/cv_assembly/stage_registry.py` — register
  `cv.pattern_selection`, prereq `cv.header_blueprint`,
  `required_for_cv_assembled=True`, `lane=cv_assembly`,
  `max_attempts=3`.
- `src/cv_assembly/dag.py` — edge `cv.header_blueprint →
  cv.pattern_selection`; fan-out edge `cv.pattern_selection →
  cv.draft_assembly` (3 work items).
- `src/cv_assembly/config_flags.py` —
  `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED`,
  `CV_ASSEMBLY_PATTERN_CONSUMED_BY_DRAFTS`,
  `CV_ASSEMBLY_PATTERN_SELECTION_DETERMINISTIC_ONLY`.
- `src/cv_assembly/tracing.py` — register stage span and substep
  spans (§17), enforce `_sanitize_langfuse_payload` on previews.
- `scripts/benchmark_pattern_selection_4_3_3.py` (new) — eval
  harness over §16.6 corpus.
- `scripts/smoke_pattern_selection.py` (new) — single-job live
  smoke per §16.13.
- `scripts/vps_run_pattern_selection.py` (new) — VPS wrapper
  template per §18.5.
- `data/eval/validation/cv_assembly_4_3_3_pattern_selection/` (new)
  — 20-case corpus per §16.6.
- `data/eval/cv_assembly/diversity_thresholds.json` (new) —
  override map (default `{global: 0.35}`).
- `tests/unit/cv_assembly/` — test files per §16.1, §16.4, §16.7,
  §16.8, §16.9, §16.10, §16.11, §16.12.
- `docs/current/architecture.md` — add §"Iteration 4.3.3 Pattern
  Selection".
- `docs/current/missing.md` — strike out the §6330–6338 4.3.3 gap
  entries and reference this plan as the resolution.
