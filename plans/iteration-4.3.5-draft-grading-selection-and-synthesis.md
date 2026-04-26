# Iteration 4.3.5 Plan: Draft Grading, Selection, and Best-Version Synthesis

## 1. Executive Summary

By the time 4.3.4 finishes, the job carries up to three lineage-checked,
header-validated `DraftDoc`s on `cv_assembly.drafts[]`. Each draft is
already pinned to its source `PatternDoc` and has passed the shared
header validator (4.3.2 §11.2) and the shared evidence-lineage
validator (4.3.4 §12) in `mode="draft"`. 4.3.5 is the candidate-aware
stage that turns those drafts into one published surface: it grades
each draft under a shared deterministic-first rubric harness, picks
the winner, and produces a **synthesis** — an improved best-version
of the winning draft assembled by surgically promoting fragments from
the other drafts under a closed enum of merge rules, every promotion
re-checked by the shared validators in `mode="synthesis"` before
persistence.

The grader is not the Layer 6 V2 self-grader. The Layer 6 V2 self-grade
on each `DraftDoc.layer6_v2_outputs.layer6_grade_result` remains
advisory; the authoritative grade is produced here by a shared harness
that every draft sees identically. The default grading model is
`gpt-5.4-mini` per the 4.3 umbrella; the rubric-first deterministic
pass dominates the score, and the LLM is invoked only for the
hiring-manager persuasiveness dimension and (optionally) for pairwise
disambiguation of ε-tied drafts.

Synthesis is **not** a free LLM rewrite. It is a versioned, byte-
deterministic, rule-driven merge with a closed `SynthesisRule` enum,
explicit per-rule preconditions, deterministic ordering, one-pass
rollback semantics, and validator consumption before persist. The
merge surface is bounded so "best-looking but less truthful" content
cannot win at the prose level: the same rubric that selected the
winner re-scores the merged output, and the union of the source
patterns' `evidence_map`s — never the master-CV alone — bounds what
fragments may cross from a non-winning draft into the synthesis.

Operational discipline is inherited from the 4.3 umbrella:

- **Mongo is the control plane.** `work_items`,
  `cv_assembly.stage_states.cv.grade_select_synthesize`,
  `cv_assembly_stage_runs`, and `cv_assembly_job_runs` drive
  execution. There is no shadow grader and no hidden human-review
  gate.
- **Langfuse is the observability sink.** A canonical stage span
  `scout.cv_assembly.grading_synthesis` carries metadata-first
  payloads with bounded subspans (§17). Full grade rationales and
  full synthesis bodies stay in Mongo.
- **Deterministic validators backstop LLM behavior.** The 4.3.4
  evidence-lineage validator and the 4.3.2 header validator are both
  invoked in `mode="synthesis"` before any synthesis output is
  persisted; their reports flow downstream verbatim.
- **VPS validation** (§19) runs the stage end-to-end on a real
  `cv_assembled`-bound job with all three drafts persisted before
  default-on rollout.

## 2. Mission

Grade up to three candidate-aware CV drafts under a shared
deterministic-first rubric; pick the winner deterministically; and
emit a versioned, byte-reproducible synthesis that promotes the
strongest fragments from the non-winning drafts under a closed
enum of merge rules — without inventing claims, expanding evidence
pools, drifting identity, or bypassing the truth-constrained
emphasis rules — so the published CV is at least as good as the
winner alone and demonstrably better when cross-draft promotion
adds verified lift.

## 3. Objectives

- **O1.** Define a `cv.grade_select_synthesize` stage that runs as
  a single barrier work item once all enqueued `cv.draft_assembly`
  work items are terminal AND ≥ 2 are non-failed. The stage
  produces one `GradeDoc` per persisted draft, exactly one
  `winner` reference, and one `SynthesisDoc` (possibly degraded).
- **O2.** Ship a shared **grading harness** with three modes
  (`rubric`, `pairwise`, `hybrid`) governed by
  `CV_ASSEMBLY_GRADER_MODE`. The deterministic rubric pass is
  authoritative on three dimensions (Truth, Pattern Fidelity,
  Coverage); the LLM scores one dimension (Hiring-Manager
  Persuasiveness); pairwise mode is bounded to ε-tied resolution
  and is otherwise off.
- **O3.** Externalise rubric weights as a versioned config
  (`data/eval/cv_assembly/rubric_weights.json`) with role-family
  overrides, summing-to-100 invariant, and a regression gate on
  any change.
- **O4.** Externalise ε thresholds (`ε_tied`, `ε_replace`,
  `ε_improve`) as a versioned config
  (`data/eval/cv_assembly/synthesis_thresholds.json`) with a
  documented eval-corpus calibration method and per-role-family
  overrides.
- **O5.** Define and ship a closed `SynthesisRule` enum with
  per-rule preconditions, action, applies-to sections, fill-only-
  vs-replace flag, deterministic ordering, rollback trigger, and
  lineage / truth constraints (§10).
- **O6.** Ship `merge_algorithm_version` semantics with semver,
  bump rules, replay compatibility, and byte-determinism scope
  (§10.7).
- **O7.** Define an explicit **validator consumption contract**:
  synthesis must invoke `validate_lineage(..., mode="synthesis",
  pattern=None)` and `validate_header(..., mode="synthesis",
  pattern=None)` before persist, and consume their reports
  verbatim into the persisted `SynthesisDoc` (§11).
- **O8.** Define explicit **downstream-consumer contracts** for
  4.3.6 and 4.3.7 so the publisher and dossier read a single,
  fixed surface from 4.3.5 and never reach into `drafts[]` for
  publishing decisions (§13).
- **O9.** Define explicit fail-open / fail-closed rules bounded
  to deterministic-only mode when the grader model is unavailable,
  two-draft synthesis when only two drafts persist, and synthesis
  rollback when no improvement clears `ε_improve` (§14).
- **O10.** Emit Langfuse traces under `scout.cv_assembly.
  grading_synthesis` with bounded subspans, required metadata,
  forbidden content list, and operator debug checklist (§17);
  trace refs flow into Mongo so an operator reaches the trace from
  `level-2` in one click.
- **O11.** Validate end-to-end on the VPS (§19) on a real
  `cv_assembling` job with three persisted drafts, with
  prerequisite verification, before default-on rollout.

## 4. Success Criteria

4.3.5 is done when, for the §18.13 15-case eval corpus and a
50-job staging soak:

- **SC1.** Every `cv_assembling` job with `draft_assembly_summary
  .drafts_persisted_count ≥ 2` produces one `GradeDoc` per
  persisted draft, exactly one `cv_assembly.winner`, and one
  `cv_assembly.synthesis` with `degraded ∈ {true, false}`.
- **SC2.** For fixed
  `(input_snapshot_id, master_cv_checksum,
  presentation_contract_checksum, header_blueprint_checksum,
  pattern_selection_checksum, jd_checksum,
  RUBRIC_WEIGHTS_VERSION, SYNTHESIS_THRESHOLDS_VERSION,
  merge_algorithm_version, drafts payload)`, the deterministic
  rubric scores, the winner selection, and `SynthesisDoc.
  final_cv_struct` are byte-identical across runs.
- **SC3.** Every persisted `SynthesisDoc` has `validator_report
  .status ∈ {pass, repair_attempted}` and `header_validator_report
  .status ∈ {pass, repair_attempted}` — never `failed`.
- **SC4.** No `SynthesisDoc.promoted_fragments[]` entry references
  an `(role_id, achievement_id, variant_id)` tuple outside the
  union of source patterns' `evidence_map`s; no header pool
  reference outside the blueprint pools.
- **SC5.** No `SynthesisDoc.final_cv_struct.header.title_string`
  differs from `header_blueprint.identity.chosen_title`.
- **SC6.** No `SynthesisDoc.final_cv_struct` numeric token fails
  the 4.3.4 §11 number-resolution policy (re-checked by the
  lineage validator in `mode="synthesis"`).
- **SC7.** When `synthesis.degraded == false`,
  `synthesis.composite_score ≥ winner.composite_score +
  ε_improve` (rounded to 4 decimal places).
- **SC8.** When the deterministic rubric top-K (K = persisted
  draft count) is within `ε_tied` and `CV_ASSEMBLY_GRADER_MODE ∈
  {pairwise, hybrid}`, the pairwise grader is invoked and its
  preference order is captured deterministically; in
  `mode=rubric`, ties are broken by §11.4 deterministic ladder.
- **SC9.** When the LLM grader and the pairwise grader are both
  unavailable AND deterministic rubric scores are within
  `ε_tied`, the stage emits `cv_assembly.status=degraded` with
  `winner_selection_method=deterministic_only_tiebreak` and the
  fixed §14 ladder picks the winner. No random tie-break.
- **SC10.** A draft whose `evidence_lineage_validator_report
  .status=failed` (i.e., a draft that failed at 4.3.4 persist) is
  filtered out of grading; failed drafts are surfaced in the
  dossier (4.3.7) but never selected as winner and never used as
  a synthesis source.
- **SC11.** `SynthesisDoc.cover_letter` is generated exactly once
  per job, on the synthesis output (per 4.3.4 §22 resolution).
- **SC12.** Langfuse stage span `scout.cv_assembly.
  grading_synthesis` is emitted with §17 metadata; one click from
  the level-2 UI reaches the synthesis trace, the rubric-pass
  subspan, the pairwise subspan (when fired), and both validator
  subspans.
- **SC13.** VPS smoke (§19) completes on a real job with
  artifacts captured under
  `reports/grading-synthesis/<job_id>/`.
- **SC14.** The eval corpus passes 100% structural invariants and
  reviewer usefulness ≥ 0.85 on the winner, ≥ 0.80 on the
  synthesis.

## 5. Non-Goals

- Re-running Layer 6 V2 role generation, the stitcher, or any
  4.3.4 prose pipeline. The drafts are final prose from 4.3.4;
  4.3.5 grades and merges only.
- Inventing achievement content. Synthesis merges existing
  fragments; it never authors a new bullet, summary line, key
  achievement, AI highlight, competency, or header element.
- Generating draft prose. There is no LLM rewrite of the body.
  An optional polish pass (§10.6) is gated off in v1 and bounded
  to surface-level grammar/punctuation when (and only when) it
  is enabled.
- Re-running the 4.3.4 number-resolution policy on persisted
  bullet text. Promoted fragments inherit their source bullet's
  `number_resolution_log[]`; the lineage validator in
  `mode="synthesis"` re-validates if the fragment is merged.
- Replacing the Layer 6 V2 self-grader. The self-grade stays on
  `DraftDoc.layer6_v2_outputs.layer6_grade_result` as advisory
  signal; it does not enter the rubric composite.
- Selecting a non-winner draft for publication. No human-pick
  override; that surface belongs to the future CV Editor (4.4).
- Owning a parallel control plane, a hidden judge service, a
  shadow grader, or a sidecar review surface.
- Free-form web search, research transports, or cross-job
  reasoning.
- A/B testing grading models online. Model benchmarking lives in
  4.3.8's eval corpus.
- Publishing or rendering. That is 4.3.6.
- Mutating any 4.3.4 `DraftDoc`. Drafts are immutable inputs to
  this stage.

## 6. Why This Stage Exists

4.3.4 produces three lineage-checked drafts. Without 4.3.5 as a
disciplined candidate-aware stage:

1. **There is no principled winner.** Picking "the first draft
   that passes the validator" or "the highest Layer 6 V2 self-
   grade" is non-comparable across drafts: each self-grade is
   conditioned on the prompt that produced it, biased toward its
   own pattern, and was never normalized across drafts of the
   same job. A shared rubric harness applied identically to
   every draft is the only comparable ranking surface.
2. **Truth must be load-bearing in selection.** Three drafts can
   converge on similar persuasiveness while differing materially
   in evidence-lineage cleanliness. Without weighting truth
   highest in the composite — and without including the lineage
   validator's `repair_attempted`/`pass` status as direct rubric
   input — the system can pick a stylistically polished draft
   over a more truthful one. The 30% Truth weight (§9.1) plus
   the deterministic-first rubric ensures truth dominates.
3. **The losing drafts contain real lift.** In practice one
   draft has the strongest header, another has the strongest
   mid-career bullet, and a third has the strongest key-
   achievements section. A bounded, evidence-respecting merge
   captures that lift without LLM rewriting. The closed
   `SynthesisRule` enum (§10.3) plus `merge_algorithm_version`
   (§10.7) plus the validator consumption contract (§11) make
   the merge auditable, reversible, and byte-deterministic.
4. **Synthesis must be reversible.** A merge that introduces a
   lineage violation must roll back surgically, leaving the
   winner draft as the published baseline. Without a closed
   rule enum and one-pass rollback semantics, "the merge made
   it worse" becomes impossible to detect or undo. The `degraded
   = true` discipline (§10.5) makes synthesis an additive,
   never-destructive surface.
5. **Publishing must consume one surface.** 4.3.6 must not
   reason about three drafts, three grades, and a synthesis at
   render time. 4.3.5 collapses the 3-draft surface into one
   `winner` + one `synthesis` so the publisher is agnostic to
   which pattern won.

The 4.3.5 stage exists so the truth boundary that 4.3.1 → 4.3.2 →
4.3.3 → 4.3.4 established survives competitive selection and
cross-draft enhancement.

## 7. Stage Boundary

### 7.1 DAG position

```
cv.draft_assembly (pattern_1) -+
cv.draft_assembly (pattern_2) -+--> cv.grade_select_synthesize --> cv_assembled
cv.draft_assembly (pattern_3) -+
```

`cv.grade_select_synthesize` is a **single barrier work item per
job**. It claims when:

- all enqueued `cv.draft_assembly` work items are in a terminal
  `DraftDoc.status` (`completed | partial | degraded | failed`),
  AND
- ≥ 2 of those drafts are not `failed` (per the 4.3.4 §8.4
  ladder).

Fewer than two non-failed drafts ⇒ the stage is not enqueued; the
job rolls up to `cv_assembly.status=failed` per 4.3.4 §15.4. There
is no fabricated single-draft "best-effort" winner.

### 7.2 Inputs

At claim time (read from `level-2`, all pinned to
`input_snapshot_id` from the work-item payload):

- `cv_assembly.drafts[]` — the persisted `DraftDoc`s (1–3, after
  failed-draft filtering ≥ 2).
- `cv_assembly.draft_assembly_summary` — the 4.3.4 rollup, used
  to confirm prerequisites at claim and to detect mutations
  between the 4.3.4 finalizer and 4.3.5 claim.
- `cv_assembly.header_blueprint` — full `HeaderBlueprintDoc`
  (4.3.2). Used as the synthesis-mode header validator anchor
  and as the source of truth for header pool membership in
  cross-draft promotion.
- `cv_assembly.pattern_selection.patterns[]` — full pattern
  records (4.3.3) for every persisted-draft pattern. Used to
  build the `union_evidence_map` (§9.4) and to gate cross-pattern
  fragment promotion via the pattern-compatibility table
  (§10.3).
- `pre_enrichment.presentation_contract.*` (all five
  subdocuments; read-only; no re-derivation) — used as rubric
  inputs (`document_expectations` for goal-fit weighting,
  `cv_shape_expectations.counts` for coverage scoring,
  `ideal_candidate_presentation_model.must_signal[]` for
  coverage scoring, `truth_constrained_emphasis_rules` for
  synthesis-time forbidden-claim enforcement,
  `experience_dimension_weights` as advisory weighting prior).
- `pre_enrichment.classification` — `primary_role_category`,
  `seniority`, `tone_family`, `ai_taxonomy.intensity`. Used for
  per-role-family rubric weight overrides (§9.1) and for the
  AI-band cap (already enforced upstream; surfaced here as
  rubric input).
- `pre_enrichment.stakeholder_surface` —
  `evaluator_coverage_target` for the LLM persuasiveness lens
  conditioning (§9.4). Advisory.
- `pre_enrichment.pain_point_intelligence.proof_map` — read-only
  rubric input for Coverage scoring (§9.3).
- Master-CV via loader v2 (4.3.1) — pinned to
  `master_cv_checksum`. Used by the lineage validator in
  `mode="synthesis"` to resolve refs; not re-read for any
  prose-level decision.

The work-item payload carries:

```text
payload {
  input_snapshot_id,
  master_cv_checksum,
  presentation_contract_checksum,
  header_blueprint_checksum,
  pattern_selection_checksum,
  jd_checksum,
  draft_assembly_summary_checksum,        # back-ref to 4.3.4 rollup at claim
  rubric_weights_version,
  synthesis_thresholds_version,
  merge_algorithm_version,
  attempt_token,
  correlation_id,
  level2_id
}
```

`input_snapshot_id` is composed per the 4.3 umbrella with the
addition of `RUBRIC_WEIGHTS_VERSION`,
`SYNTHESIS_THRESHOLDS_VERSION`, and `merge_algorithm_version` so
any change to those configs invalidates cached grade/synthesis
results.

### 7.3 Outputs

On success:

- `cv_assembly.grades[]` — one `GradeDoc` (§9.2) per persisted,
  non-failed draft. Failed drafts are not graded.
- `cv_assembly.winner` — `{draft_id, pattern_id, pattern_label,
  composite_score, ranking_tier: "winner",
  selection_method, rationale_ref, trace_ref}`.
- `cv_assembly.synthesis` — one `SynthesisDoc` (§9.3) carrying
  the merged best-version CV text and structured payload, the
  union evidence-map ref, the merge plan, the validator reports,
  and the cover letter.
- `cv_assembly.assembled_at` — CAS-guarded timestamp on success.
- `cv_assembly.status` rolled up by the 4.3 sweeper: `completed`
  when grading + synthesis both clean; `partial` when synthesis
  ran with rollbacks but cleared `ε_improve`; `degraded` when
  synthesis is `degraded=true` (no improvement) OR
  `winner_selection_method=deterministic_only_tiebreak`;
  `failed` only on the closed list in §14.4.
- `lifecycle = cv_assembled` on success.

### 7.4 Work-item details

- `task_type = cv.grade_select_synthesize`, `lane = cv_assembly`.
- `idempotency_key =
  cv.grade_select_synthesize:<level2_id>:<input_snapshot_id>`.
  Note: idempotency does **not** include
  `merge_algorithm_version`; bumping the version is a separate
  invalidation surface (§10.7).
- `max_attempts = 3` with the 4.3-umbrella
  `RETRY_BACKOFF_SECONDS`.
- `required_for_cv_assembled = true` (terminal barrier).
- Prerequisite checks at claim (§8) — recorded in
  `debug_context.preflight_check[]`.

### 7.5 Stage owner

Owned by the cv_assembly worker
(`src/cv_assembly/stages/grade_select_synthesize.py`). Co-owned
only at the shared-library level: 4.3.2 (`validate_header`) and
4.3.4 (`validate_lineage`) are consumed verbatim; 4.3.4
`PatternDoc`, 4.3.4 `DraftDoc`, 4.3.2 `HeaderBlueprintDoc` are
read verbatim, never extended in flight.

## 8. Hard Prerequisites

The following must be true before `cv.grade_select_synthesize`
is allowed to claim a job. These are checked deterministically
at claim time and recorded in `debug_context.preflight_check[]`.

### 8.1 Hard-blocking prerequisites (job-wide)

If any of these fail, the stage is **not enqueued** and the
work-item layer marks
`level-2.cv_assembly.stage_states.cv.grade_select_synthesize`
with `status=blocked` and `blocked_reason`.

- `level-2.lifecycle == "cv_assembling"`.
- `cv_assembly.draft_assembly_summary.status ∈
  {completed, partial, degraded}` AND
  `drafts_persisted_count ≥ 2` AND
  `(drafts_persisted_count - drafts_failed_count) ≥ 2`. The 4.3.4
  rollup is the single signal here; this stage does **not** count
  drafts in `cv_assembly.drafts[]` independently.
- For every `draft ∈ cv_assembly.drafts[]` with
  `status ∈ {completed, partial, degraded}`:
  `draft.validator_report.status ∈ {pass, repair_attempted}` AND
  `draft.header_validator_report.status ∈
  {pass, repair_attempted}` AND
  `draft.pattern_signature == cv_assembly.pattern_selection
  .patterns[draft.pattern_id - 1].pattern_signature`.
  Drafts whose lineage or header validator status is `failed`
  cannot exist (4.3.4 §13.3 and §15.3 prevent persistence in
  that case); a drift here is a hard blocker — operator triage,
  no auto-repair.
- `cv_assembly.header_blueprint.status ∈ {completed, partial}`.
  `degraded` and `failed` are blockers; if the blueprint somehow
  arrived `failed` after 4.3.4 succeeded, the job deadletters
  for operator triage.
- `cv_assembly.pattern_selection.status ∈
  {completed, partial}` AND for every persisted draft, its
  source `PatternDoc.pattern_status != failed`.
- All five `pre_enrichment.presentation_contract.*` subdocuments
  resolvable with their pinned checksum.
- Master-CV loader v2 succeeds against the pinned
  `master_cv_checksum`.
- `RUBRIC_WEIGHTS_VERSION` and `SYNTHESIS_THRESHOLDS_VERSION`
  resolve to a checked-in config row (§9.1, §10.4) in the
  deployed repo and on disk.
- `merge_algorithm_version` resolves to a registered version in
  `src/cv_assembly/grading/synthesis_versions.py` (§10.7).
- Canonical enums resolvable at import: `SynthesisRule` (§10.3),
  `RankingTier`, `WinnerSelectionMethod`, `GraderMode`. Import
  failure is a blocker.
- `CV_ASSEMBLY_GRADE_SELECT_SYNTHESIZE_ENABLED=true` AND
  `CV_ASSEMBLY_SYNTHESIS_ENABLED=true` (when `false`, grading
  runs and persists `winner`, but `synthesis` is skipped and
  `cv_assembly.synthesis` is populated with `degraded=true`,
  `degradation_reason=synthesis_disabled`,
  `final_cv_struct = winner.cv_struct`,
  `final_cv_text = winner.cv_text` — see §22).

### 8.2 Degraded-allowed prerequisites

These do not block the stage but downgrade the run.

| Prerequisite | Degradation rule |
|---|---|
| Grader model (`gpt-5.4-mini` and `gpt-5.4` fallback) unreachable per `unified_llm.py` health probe | `deterministic_only_mode = true`; `hiring_manager_persuasiveness.score = 0.0`, `abstention=true`, `model_used=null`. Composite recomputed with deterministic-only weights normalized to 100 (the 30% persuasiveness weight is redistributed pro-rata to Truth, Pattern Fidelity, and Coverage). When deterministic spread is within `ε_tied`, the deterministic ladder (§11.4) breaks the tie and `cv_assembly.status=degraded` with `winner_selection_method=deterministic_only_tiebreak`. |
| Pairwise grader unreachable when `CV_ASSEMBLY_GRADER_MODE ∈ {pairwise, hybrid}` AND deterministic spread is within `ε_tied` | Fall through to the deterministic ladder (§11.4); record `pairwise_invoked=false`, `pairwise_unreachable=true`; `winner_selection_method=deterministic_only_tiebreak`; `cv_assembly.status=degraded`. |
| `cv_assembly.draft_assembly_summary.degraded_mode == true` (only two drafts persisted at 4.3.4) | Grade two drafts; synthesize from the single non-winner. Synthesis still proceeds; `cv_assembly.status=degraded` is inherited from 4.3.4 if 4.3.5 itself is otherwise clean; if 4.3.5 introduces additional degradation (e.g., `synthesis.degraded=true`) the rollup remains `degraded`. |
| One persisted draft is `cv_assembly.drafts[i].status=partial` (validator repair fired) | Grading proceeds; `validator_report.status=repair_attempted` reduces the Truth dimension score per §9.1 calibration, but does not exclude the draft from grading or from being the winner. |
| `pain_point_intelligence.status ∈ {partial, unresolved}` | Coverage scoring (§9.3) reweights toward `cv_shape_expectations` and `must_signal[]`; pain-point coverage component contributes 0 with `coverage_unresolved_marker=true`. |
| `stakeholder_surface.status ∈ {inferred_only, no_research}` | LLM persuasiveness lens conditioning uses `recruiter` + `hiring_manager` evaluators only; `evaluator_coverage_used` is recorded in `GradeDoc.dimensions.hiring_manager_persuasiveness.evaluator_coverage_used[]`. |

### 8.3 Operating-mode declaration

Per the 4.3.2 / 4.3.3 / 4.3.4 §15.0 / §8.5 pattern, every degraded
path is permitted but is **never** the operating mode. Production
runs must complete with `cv_assembly.status ∈ {completed,
partial}` on ≥ 90% of `cv_assembled`-bound jobs (gate in §18.14).
`degraded` and the deterministic-only tiebreak ladder are
fail-open paths, not goals.

### 8.4 What is **not** a prerequisite

- A specific Layer 6 V2 self-grade outcome on any draft.
  `layer6_v2_outputs.layer6_grade_result` is advisory and may be
  absent (when the self-grader was unhealthy upstream).
- A successful third draft. Two persisted drafts is sufficient.
- `pain_point_intelligence` non-emptiness. Sparse pain-point
  data downgrades Coverage but does not block.
- A specific `pattern_label` distribution across the persisted
  drafts. The pattern-compatibility table (§10.3) handles
  cross-pattern fills regardless of which patterns survived.

## 9. Output Shape / Schema Direction

### 9.1 Rubric weights — `RubricWeightsConfig`

Stored at `data/eval/cv_assembly/rubric_weights.json`; loaded at
import time; pinned by `RUBRIC_WEIGHTS_VERSION` (semver).

```text
RubricWeightsConfig {
  version,                                # e.g. "1.0.0"
  default_weights {
    truth_evidence_grounding: 30,
    pattern_fidelity: 20,
    presentation_contract_coverage: 20,
    hiring_manager_persuasiveness: 30
  },
  role_family_overrides {                 # optional per primary_role_category
    "leadership_led":   { truth_evidence_grounding: 30, pattern_fidelity: 15,
                           presentation_contract_coverage: 25,
                           hiring_manager_persuasiveness: 30 },
    "ai_led":           { truth_evidence_grounding: 35, pattern_fidelity: 20,
                           presentation_contract_coverage: 15,
                           hiring_manager_persuasiveness: 30 },
    ...
  },
  deterministic_only_redistribution: pro_rata,   # how the 30% LLM weight is
                                                 # redistributed when
                                                 # deterministic_only_mode=true
  invariants {
    weights_sum_to_100: true,
    every_dimension_present: true,
    integer_weights_only: true,
    role_family_overrides_subset_of_pattern_label_enum: true   # cross-check
                                                                # against 4.3.3 §9.2
  }
}
```

Invariants are checked at config load. Any violation → import-
time error; the stage refuses to register. Changes to the config
require:

- a `RUBRIC_WEIGHTS_VERSION` semver bump,
- a regression-gate run on the §18.13 corpus (§18.15 gate),
- a docs entry in `docs/current/architecture.md` "Iteration
  4.3.5 Grading" subsection.

The role-family override key is `pattern_label` from the
**winner's** pattern (per draft) when scoring that draft's
composite, **not** the job's `classification.primary_role_category`
— the rubric must reward each draft against its own pattern's
posture so an `architecture_led` draft is not penalized for
sparse leadership coverage. When the override key is missing,
the default weights apply.

### 9.2 `GradeDoc`

```text
GradeDoc {
  draft_id,
  pattern_id,
  pattern_label,                           # for role-family weight lookup
  pattern_signature,                       # back-ref to PatternDoc
  schema_version,                          # GRADE_SCHEMA_VERSION
  rubric_weights_version,
  weights_used {
    truth_evidence_grounding,
    pattern_fidelity,
    presentation_contract_coverage,
    hiring_manager_persuasiveness
  },
  deterministic_only_mode: bool,           # true if LLM dimension was redistributed
  dimensions {
    truth_evidence_grounding {
      score,                               # 0..1
      sub_components {
        lineage_validator_status,          # pass | repair_attempted
        lineage_repair_count,
        lineage_warning_count,
        header_validator_status,
        header_repair_count,
        number_resolution_unsourced_count,
        forbidden_phrase_match_count,
        forbidden_proof_category_count
      },
      violations[],                        # refs to validator report entries
      trace_ref
    },
    pattern_fidelity {
      score,
      sub_components {
        pattern_signature_match: bool,
        achievements_in_evidence_map_count,
        achievements_outside_evidence_map_count,
        skills_in_evidence_map_count,
        skills_stripped_count,
        section_emphasis_alignment_score,
        proof_order_alignment_score
      },
      additions_outside_map[],
      omissions_from_map[]
    },
    presentation_contract_coverage {
      score,
      sub_components {
        proof_order_coverage,              # fraction of pattern.proof_order_override
                                           # categories realized
        must_signal_coverage,              # fraction of
                                           # ideal_candidate_presentation_model
                                           # .must_signal[] addressed
        dimension_weight_alignment,        # KL divergence to pattern's
                                           # dimension_weights_override
        pain_point_coverage,               # fraction of
                                           # pain_point_intelligence.proof_map
                                           # categories addressed
        section_count_compliance,          # cv_shape_expectations.counts
        ats_keyword_density                # jd_facts.top_keywords coverage
      },
      covered_proof_categories[],
      missing_proof_categories[]
    },
    hiring_manager_persuasiveness {
      score,                               # 0..1
      rationale,                           # <= 300 chars
      model_used,                          # null when deterministic_only_mode
      abstention: bool,
      evaluator_coverage_used[],
      tokens_input,
      tokens_output,
      cost_usd
    }
  },
  composite_score,                         # weighted sum, rounded to 4 dp
  composite_score_rank,                    # 1..K within this job
  ranking_tier,                            # winner | runner_up | third
  used_in_synthesis: bool,
  rubric_pass_signature,                   # sha256 over canonical rubric inputs
  trace_ref,
  debug_context: GradeDebug
}
```

### 9.2.1 `GradeDebug`

```text
GradeDebug {
  preflight_check[] {name, status, detail},
  deterministic_input_summary {
    bullets_total,
    bullets_with_master_cv_exact,
    bullets_with_structured_metric,
    bullets_with_metric_band,
    skills_total,
    keys_total,
    forbidden_phrase_substring_hits[]
  },
  llm_persuasiveness_full_trace {
    prompt_signature,
    request_id,
    raw_response,                          # bounded; full body kept here only
    parse_outcome,                         # ok | repaired | failed
    repair_actions[]
  },
  pairwise_full_trace?,                    # populated only when pairwise fired
  composition_steps[] {step_name, score_delta},
  retry_events[]
}
```

Capped at 32 KB; collection-backed only; not mirrored to compact
projection.

### 9.3 `SynthesisDoc`

```text
SynthesisDoc {
  base_draft_id,                           # winner draft id
  schema_version,                          # SYNTHESIS_SCHEMA_VERSION
  merge_algorithm_version,
  synthesis_thresholds_version,
  rubric_weights_version,
  status,                                  # completed | partial | degraded | failed
  degraded: bool,                          # true when no improvement OR rollback
  degradation_reason?,                     # enum, see §10.5
  promoted_fragments[] {
    promotion_id,                          # stable: sha256(rule_id || source_draft_id ||
                                           #                section_id || slot_index)[:16]
    rule_id,                               # SynthesisRule enum, §10.3
    source_draft_id,
    source_pattern_id,
    source_pattern_label,
    fragment_type,                         # header_line | tagline | summary_sentence |
                                           # key_achievement | bullet | competency |
                                           # ai_highlight | differentiator
    section_id,                            # canonical 4.2.2 enum
    slot_ref {
      section,
      slot_index?,
      role_id?,
      bullet_index?
    },
    base_signature,                        # sha256 over the base draft's replaced
                                           # fragment bytes (null when fill_only)
    promoted_signature,                    # sha256 over the promoted fragment bytes
    promoted_text_preview,                 # <= 240 chars, truncated
    source_lineage_ref {                   # back-ref into source draft's lineage
      role_id?, achievement_id, variant_id?,
      proof_category, dimension,
      scope_band, metric_band, ai_relevance_band,
      source_fragment_ref
    },
    score_delta {                          # per-dimension; positive = promotion improves
      truth_evidence_grounding,
      pattern_fidelity,
      presentation_contract_coverage,
      hiring_manager_persuasiveness
    },
    rule_outcome,                          # applied | rolled_back
    rollback_reason?                       # enum, see §10.5.4
  },
  rolled_back_attempts[] {                 # one entry per rule application that failed
                                           # validators after merge
    rule_id, source_draft_id, section_id, slot_ref,
    rollback_reason, validator_violations_summary
  },
  final_cv_text,                           # canonical markdown; null only when synthesis
                                           # is wholly degraded to winner verbatim
  final_cv_struct {                        # same shape as DraftDoc.cv_struct
    header { headline, tagline, key_achievements[], core_competencies[] },
    summary,
    ai_highlights[]?,
    experience [...],
    education[], certifications[], projects[]?, publications[]?, awards[]?
  },
  evidence_lineage {                       # same shape as DraftDoc.evidence_lineage,
                                           # composed across promoted + base fragments
    header { ... },
    summary { ... },
    bullet_lineage[],
    derived_markers[]
  },
  union_evidence_map_ref {                 # back-ref into the SynthesisContext union
    pattern_ids_unioned[],
    union_signature                        # sha256 over canonical union
  },
  validator_report: EvidenceLineageValidatorReport,    # mode="synthesis"
  header_validator_report: HeaderValidatorReport,      # mode="synthesis"
  composite_score,                         # synthesis re-graded under same rubric harness
  composite_score_delta_vs_winner,         # composite_score - winner.composite_score
  cover_letter {                           # generated once; see §10.6
    text,
    cover_letter_prompt_version,
    model_used,
    tokens_input, tokens_output,
    generation_trace_ref,
    validator_status                       # pass | failed
  } | null,
  langfuse_trace_ref { trace_id, trace_url, parent_stage_trace_id, span_id },
  debug_context: SynthesisDebug
}
```

### 9.3.1 `SynthesisDebug`

```text
SynthesisDebug {
  union_evidence_map_full[],               # full union, capped at 32 KB
  promotion_attempts_full[],               # every fragment considered, scored, decided
  rule_application_order[],                # deterministic order trace
  validator_full_trace_pre_repair[],
  validator_full_trace_post_repair[],
  header_validator_full_trace[],
  rollback_full_trace[],
  reasoning_summary,                       # <= 1200 chars; summary for compat projection
  retry_events[]
}
```

Capped at 64 KB; collection-backed only; not mirrored to compact
projection. `reasoning_summary` is consumed by the 4.3.6 §10
compatibility projection (`cv_reasoning` field).

### 9.4 `SynthesisContext`

Built deterministically at the start of the work item; pure
function over inputs; no LLM in this construction. Asserted by
§18.5 unit tests.

```python
@dataclass(frozen=True)
class SynthesisContext:
    persisted_drafts: tuple[DraftDoc, ...]               # filtered: status != failed
    winner_draft_id: str                                 # set after grading + selection
    runner_up_draft_ids: tuple[str, ...]                 # ranked descending by composite
    union_evidence_map: UnionEvidenceMap                 # see below
    union_pattern_ids: frozenset[int]
    pattern_compat_table: PatternCompatTable             # §10.3
    header_blueprint: HeaderBlueprintDoc
    presentation_contract: PresentationContractDoc
    classification: ClassificationDoc
    pain_point_intelligence: Optional[PainPointIntelligenceDoc]
    stakeholder_surface: Optional[StakeholderSurfaceDoc]
    candidate_data: CandidateData
    rubric_weights: RubricWeightsConfig
    synthesis_thresholds: SynthesisThresholdsConfig
    merge_algorithm_version: str
    grader_mode: Literal["rubric", "pairwise", "hybrid"]
    deterministic_only_mode: bool
    input_snapshot_id: str
    tracer: CvAssemblyTracingSession
```

```text
UnionEvidenceMap {
  achievements: frozenset[(role_id, achievement_id, variant_id|None)],
  skills: frozenset[skill_id],
  header_pool {
    visible_identity_candidate_ids: frozenset[str],
    lead_phrase_candidate_ids: frozenset[str],
    title_candidate_ids: frozenset[str],
    hero_proof_fragment_ids: frozenset[str],
    credibility_marker_ids: frozenset[str],
    differentiator_ids: frozenset[str]
  },
  per_pattern_evidence_maps: dict[pattern_id, PatternEvidenceMap],
  union_signature                          # sha256(canonical_json(union))
}
```

The union is the **superset** of every persisted draft's source
pattern's evidence map; it is **not** the union of master-CV
evidence at large. The lineage validator in `mode="synthesis"`
asserts pool membership against the blueprint as a whole and
achievement membership against `union.achievements`. This is
exactly the cross-pattern promotion surface 4.3.5 needs.

### 9.5 Schema versioning

- `GRADE_SCHEMA_VERSION` and `SYNTHESIS_SCHEMA_VERSION` live in
  `src/cv_assembly/models.py`. Bumps on any change to:
  `dimensions` schema, `promoted_fragments[]` schema,
  `validator_report` schema (other than additive fields),
  `evidence_lineage` schema. Bumps invalidate
  `input_snapshot_id` and require re-running.
- `RUBRIC_WEIGHTS_VERSION` and `SYNTHESIS_THRESHOLDS_VERSION` are
  config-file-resident and are part of `input_snapshot_id`.
- `merge_algorithm_version` is **not** part of
  `input_snapshot_id` (deliberately — see §10.7); a bump is a
  separate cache-invalidation surface.

## 10. Synthesis Algorithm and Rule Enum

Synthesis is rule-driven, byte-deterministic, validator-checked,
and reversible. There is no LLM rewrite of the body. The
`SynthesisRule` enum is closed; new rules require an enum bump
and a `merge_algorithm_version` bump.

### 10.1 High-level algorithm

1. **Build `SynthesisContext`** (§9.4). Pure; no I/O.
2. **Score drafts** under the grading harness (§11). Determine
   `winner_draft_id`, `runner_up_draft_ids`, and per-draft
   per-fragment dimension scores. The fragment scores are reused
   in step 4.
3. **Build the candidate-fragment ladder.** For every non-winner
   draft and every fragment-bearing slot in its `cv_struct`,
   compute a candidate `(rule_id, source_draft_id, section_id,
   slot_ref, base_signature?, promoted_signature, score_delta)`
   tuple per §10.3. Reject candidates that fail their rule's
   preconditions deterministically.
4. **Order candidates deterministically.** The order is fixed:
   1. by `rule_id` ordinal (ascending; §10.3 enum order),
   2. by `section_id` ordinal (4.2.2 canonical enum order),
   3. by `slot_ref.slot_index` ascending (then `role_id`
      ascending, then `bullet_index` ascending),
   4. by `source_draft_id` ascending,
   5. by `score_delta.truth_evidence_grounding` descending,
   6. by `promoted_signature` ascending (lexicographic).
5. **Apply candidates one-by-one, stopping on rollback.** For
   each candidate, attempt the merge, then run the lineage
   validator in `mode="synthesis"` (§11). If the validator
   reports a new violation that the rule's deterministic repair
   cannot heal in one pass, **roll back the candidate** and
   record a `rolled_back_attempts[]` entry. Continue with the
   next candidate.
6. **Run the header validator** in `mode="synthesis"` against
   the merged header struct. Header repair under §11 may
   substitute from blueprint pools deterministically; if any
   `severity=blocking` violation remains after one pass, roll
   back the most recent header-affecting promotion(s) until the
   header validator clears.
7. **Re-grade the merged output** under the same rubric harness
   used in step 2. Compute `synthesis.composite_score` and
   `composite_score_delta_vs_winner`.
8. **Improvement gate.** If `composite_score_delta_vs_winner <
   ε_improve`, set `degraded=true`,
   `degradation_reason=no_improvement`, restore
   `final_cv_struct = winner.cv_struct`,
   `final_cv_text = winner.cv_text`, and persist with the
   rolled-back synthesis attempts captured in
   `rolled_back_attempts[]`.
9. **Generate the cover letter** (§10.6) from the merged output
   (or the winner if degraded).
10. **Persist** the `GradeDoc[]`, the winner reference, and the
    `SynthesisDoc` in a single Mongo transaction (§16).

The whole pipeline is deterministic: for fixed inputs, the
rolled-back attempts, the applied promotions, the final
`cv_struct`, `cv_text`, and `composite_score` are byte-identical
across runs (cover-letter generation and the LLM persuasiveness
score are the only LLM-dependent surfaces; both are excluded
from byte-determinism but are bounded to ±0.05 tolerance per
SC2 / §18.14).

### 10.2 Fragment eligibility (preconditions, every rule)

Before any rule's per-rule preconditions, every candidate must
satisfy the **base eligibility** filter:

- The fragment's `(role_id, achievement_id, variant_id)`
  resolves in `union_evidence_map.achievements`.
- The fragment's `proof_category` is **not** in the **winner
  pattern's** `forbidden_proof_categories` (composed per 4.3.4
  §10.2.4 against the **winner's** pattern, not the source
  draft's pattern — synthesis lives under the winner's
  emphasis posture).
- The fragment's text contains no substring in
  `winner_pattern_bias.forbidden_phrases` (composed per 4.3.4
  §10.2.5).
- The fragment satisfies the 4.2.6 truth-constrained emphasis
  rules under the winner pattern — `omit_rules[]` and
  `downgrade_rules[]` are honored at merge time per the §11
  validator (4.2.6 ownership; consumed verbatim).
- The fragment's `ai_relevance_band` ≤
  `classification.ai_taxonomy.intensity`.
- For experience bullets: the fragment's `role_id` is present in
  `winner.cv_struct.experience[].role_id` (the winner draft's
  rendered role list). Synthesis does **not** add roles that
  the winner did not render; promoting a bullet into a role the
  winner did not include would change the experience surface
  beyond bullet-level promotion and is forbidden.

A candidate failing base eligibility is filtered out before
ordering. It does not enter `rolled_back_attempts[]` (only
post-merge rollbacks do).

### 10.3 The `SynthesisRule` enum

The enum is closed. Every rule has a stable `rule_id`,
preconditions in addition to base eligibility (§10.2), an
action, an `applies_to` set of `section_id`s, a fill-only-vs-
replace flag, a deterministic ordering hint (the rule ordinal
in this section), and a rollback trigger.

#### 10.3.1 `R001_higher_score_same_achievement_promotion`

- **Applies to:** `summary | key_achievements | experience |
  ai_highlights`. Bullet-level and slot-level fragments.
- **Preconditions (rule-specific):**
  - The candidate fragment's `achievement_id` (and `variant_id`
    if specified) **equals** the base fragment's
    `achievement_id` (and `variant_id`) at the same `slot_ref`.
  - `score_delta.truth_evidence_grounding ≥ 0` AND
    `score_delta.hiring_manager_persuasiveness ≥ ε_replace`,
    OR
    `score_delta.truth_evidence_grounding ≥ ε_replace` AND
    `score_delta.hiring_manager_persuasiveness ≥ 0`.
    (Truth and persuasiveness are the two replacement-gating
    dimensions; pattern fidelity and coverage are tie-breakers
    and may not be the sole drivers of replacement.)
  - The candidate fragment's `metric_band`, `scope_band`, and
    `ai_relevance_band` are each **≤** the base fragment's
    bands (no band climbing via promotion).
- **Mode:** replace.
- **Action:** swap the base fragment's text/struct for the
  promoted fragment's text/struct at `slot_ref`. Lineage entry
  for the slot is replaced with the promoted fragment's lineage.
- **Rollback trigger:** any post-merge lineage violation,
  header violation (header surfaces only), or 4.2.6 forbidden-
  claim match introduced by the swap.

#### 10.3.2 `R002_fill_empty_slot`

- **Applies to:** `summary | key_achievements | core_competencies
  | ai_highlights`. Specifically: slots where the winner draft
  rendered no content (e.g., `key_achievements[3]` is absent or
  empty, `ai_highlights[]` is empty but
  `pattern.evidence_map.ai_highlights.enabled=true`).
- **Preconditions (rule-specific):**
  - The base draft's slot at `slot_ref` is empty/null/missing.
  - The fragment's `(role_id, achievement_id, variant_id)` is
    in the **winner's** `pattern.evidence_map` (this is a
    same-pattern fill; cross-pattern fill uses R003).
  - Filling does not exceed `cv_shape_expectations.counts`
    upper bound for the section.
- **Mode:** fill-only.
- **Action:** insert the promoted fragment at `slot_ref`. New
  lineage entry composed from the promoted fragment's lineage.
- **Rollback trigger:** any post-merge lineage violation,
  count-overflow violation, or header violation.

#### 10.3.3 `R003_higher_score_cross_pattern_section_fill`

- **Applies to:** `summary | key_achievements |
  core_competencies | ai_highlights`. Fill-only, **never**
  replace, in v1.
- **Preconditions (rule-specific):**
  - The base draft's slot at `slot_ref` is empty/null/missing
    (same as R002).
  - The fragment's `(role_id, achievement_id, variant_id)` is
    in `union_evidence_map.achievements` but **not** in the
    winner pattern's `evidence_map` (i.e., it is from a
    runner-up's pattern — the cross-pattern surface).
  - `pattern_compat_table[winner.pattern_label][source.pattern_label]
    == "compat"` per §10.3.7. Incompatible pairs are filtered
    out.
  - For `key_achievements`: the fragment's `proof_category` is
    in `winner.pattern.proof_order_override[]` (the winner
    pattern's emphasis still gates which proof categories may
    surface).
  - For `core_competencies`: the fragment's `skill_id` is in
    `winner.pattern.evidence_map.core_competencies.skill_ids[]`
    OR the union of all persisted patterns' skill pools — and
    the §11 lineage validator in `mode="synthesis"` accepts
    skills from the union (4.3.4 §12.1 mode semantics).
- **Mode:** fill-only.
- **Action:** insert the promoted fragment at `slot_ref`.
- **Rollback trigger:** any post-merge lineage violation,
  pattern-compat violation surfacing post-merge, or count
  overflow.

#### 10.3.4 `R004_conservative_softening_per_4_2_6`

- **Applies to:** `summary | key_achievements | experience`.
- **Preconditions (rule-specific):**
  - The base fragment matches a 4.2.6 `downgrade_rules[]`
    pattern that surfaces only after merge time (e.g., a fill
    by R002 introduced wording that the downgrade rule would
    soften in the winner's emphasis posture).
  - A registered metric-band phrase per 4.3.4 §11.4 exists for
    the softer band.
- **Mode:** rewrite-in-place (deterministic phrase
  substitution).
- **Action:** replace the offending phrase with the next-
  conservative phrase from the rule's `action` field. This
  rule **only fires as a deterministic repair** during step 5
  rollback handling — it is not invoked as an independent
  promotion candidate. It is enumerated here so the closed
  rule set covers every observable promotion outcome.
- **Rollback trigger:** if softening introduces a header
  violation or a count overflow, the **original promotion
  that triggered softening** is rolled back instead.

#### 10.3.5 `R005_header_pool_substitution`

- **Applies to:** `header.headline | header.tagline`. Limited
  to header-pool members.
- **Preconditions (rule-specific):**
  - The base draft uses
    `header_picks.{visible_identity_candidate_id |
    lead_phrase_candidate_id |
    title_candidate_id | hero_proof_fragment_id_*}` from the
    blueprint pools.
  - A non-winner draft uses a different pool member at the same
    surface, with a higher Truth+Persuasiveness composite
    delta ≥ `ε_replace` AND the alternative pool member is
    permitted by `viability_bands.strong_competitive_header`.
  - **`title_candidate_id` substitution is forbidden** —
    `chosen_title` is frozen per 4.3.2 §11.1.1 and 4.3.4 §I2.
    R005 may not change the title.
- **Mode:** replace (within blueprint pools only).
- **Action:** substitute the realized prose's pool member with
  the promoted member; the 4.3.2 header validator's
  `substitute_from_pool` repair surface (4.3.2 §11.2.3) is
  reused at synthesis time when the realized prose was
  paraphrased.
- **Rollback trigger:** any post-merge header validator
  violation that the deterministic substitute_from_pool repair
  cannot heal in one pass.

#### 10.3.6 `R006_differentiator_promotion`

- **Applies to:** `header.tagline | summary`. Strictly
  fill-only on a registered `differentiator_id`.
- **Preconditions (rule-specific):**
  - The base draft's tagline / summary does not surface this
    `differentiator_id`.
  - The differentiator is in `union_evidence_map
    .header_pool.differentiator_ids` AND in the winner's
    pattern's permitted differentiators per 4.3.2
    `viability_bands.strong_competitive_header.differentiator_ids[]`.
- **Mode:** fill-only (insert into a fixed-grammar slot in
  tagline/summary; the slot is composed deterministically per
  4.3.2 §11.1.3 grammar rules).
- **Action:** insert the differentiator phrase at the
  deterministic slot.
- **Rollback trigger:** any header validator violation,
  forbidden-phrase match, or grammar-integrity failure.

#### 10.3.7 `pattern_compat_table` (R003 gate)

A small, hand-curated compatibility matrix over
`PatternLabel × PatternLabel`. The intent is to allow cross-
pattern fills only when the source pattern's emphasis is
non-conflicting with the winner's. The table is shipped as
`src/cv_assembly/grading/pattern_compat.py`:

```text
                    architecture_led | delivery_led | leadership_led | ai_led | platform_led | transformation_led | operator_led | hybrid_*
architecture_led    self              | compat       | compat         | compat | compat       | compat             | -            | compat
delivery_led        compat            | self         | compat         | -      | compat       | compat             | compat       | compat
leadership_led      compat            | compat       | self           | -      | -            | compat             | compat       | compat
ai_led              compat            | -            | -              | self   | compat       | -                  | -            | compat
platform_led        compat            | compat       | -              | compat | self         | -                  | -            | compat
transformation_led  compat            | compat       | compat         | -      | -            | self               | compat       | compat
operator_led        -                 | compat       | compat         | -      | -            | compat             | self         | compat
hybrid_*            compat            | compat       | compat         | compat | compat       | compat             | compat       | self
default_role_family  compat (target)  | compat       | compat         | compat | compat       | compat             | compat       | compat
```

`compat`: cross-pattern fills permitted under R003.
`self`: same pattern; uses R002 not R003.
`-`: forbidden cross-pattern fill (e.g., promoting
`leadership_led` content into an `ai_led` winner, or vice versa,
in v1 — these emphases are in tension and the closed promotion
surface forbids the mix).

The table is **declared in code, not config** — changes require a
PR review and a `merge_algorithm_version` bump (§10.7). It is
shipped versioned in
`src/cv_assembly/grading/pattern_compat.py::PATTERN_COMPAT_TABLE`.

### 10.4 ε thresholds — `SynthesisThresholdsConfig`

Stored at `data/eval/cv_assembly/synthesis_thresholds.json`;
loaded at import time; pinned by
`SYNTHESIS_THRESHOLDS_VERSION` (semver).

```text
SynthesisThresholdsConfig {
  version,                                 # e.g. "1.0.0"
  defaults {
    epsilon_tied: 0.05,                    # composite-score band that triggers
                                           # pairwise grading (when enabled) or
                                           # the deterministic ladder
    epsilon_replace: 0.07,                 # per-dimension delta required for
                                           # R001 / R005 replacement
    epsilon_improve: 0.02                  # composite-score delta required for
                                           # synthesis to be non-degraded
  },
  role_family_overrides {                  # per pattern_label of the WINNER
    "leadership_led":   { epsilon_tied: 0.04, epsilon_replace: 0.08, epsilon_improve: 0.02 },
    "ai_led":           { epsilon_tied: 0.05, epsilon_replace: 0.06, epsilon_improve: 0.025 },
    ...
  },
  invariants {
    epsilons_in_range: { epsilon_tied: [0.0, 0.2],
                         epsilon_replace: [0.0, 0.3],
                         epsilon_improve: [0.0, 0.1] },
    epsilon_improve_le_epsilon_replace: true,    # consistency
    every_role_family_complete: true             # no partial overrides
  },
  calibration_method {                     # documented; not executed at runtime
    corpus: "data/eval/validation/cv_assembly_4_3_5_grade_synth/",
    cadence: "per release",
    procedure: "per role family compute reviewer-usefulness vs synthesis-frequency curves;
                pick the epsilon that maximizes reviewer-usefulness subject to
                synthesis_rollback_rate < 0.30 over the 20+ case corpus",
    decision_owner: "pipeline_owner",
    last_calibrated_at, last_calibrated_run_id
  }
}
```

Threshold changes follow the same workflow as rubric weights:
semver bump, regression-gate run, docs entry. The
`role_family_overrides` use the **winner's** `pattern_label`
(consistent with §9.1 weight overrides).

### 10.5 Rollback semantics

Rollback is **per-promotion**, **one-pass per promotion**, and
**deterministic**. There is no LLM in rollback.

#### 10.5.1 What triggers rollback

- A new lineage validator violation introduced post-merge that
  the validator's deterministic repair surface (4.3.4 §12.4)
  cannot heal in one pass.
- A new header validator violation introduced post-merge that
  the header validator's deterministic repair surface (4.3.2
  §11.2.3) cannot heal in one pass.
- A new 4.2.6 forbidden-claim match introduced post-merge.
- A `cv_shape_expectations.counts` overflow introduced
  post-merge.
- Any grammar-integrity failure post-`R005_header_pool_substitution`
  or `R006_differentiator_promotion`.

#### 10.5.2 What rollback does

- Restore the slot to its pre-promotion state byte-exactly
  (using `base_signature` from the candidate tuple).
- Restore the corresponding lineage entry.
- Re-run only the validator that reported the violation, scoped
  to the affected slot, to confirm the rollback healed the
  violation.
- Record a `rolled_back_attempts[]` entry with the rollback
  reason and the validator violations that triggered it.

#### 10.5.3 What rollback never does

- Apply a different rule to the same slot to "rescue" the
  intent.
- Generate new prose to mediate.
- Re-order earlier promotions.
- Modify `chosen_title` or any 4.3.2-frozen field.

#### 10.5.4 `rollback_reason` enum

```text
lineage_violation_unrepairable
header_validation_unrepairable
forbidden_claim_post_merge
count_overflow_post_merge
grammar_integrity_post_merge
pattern_compat_drift_post_merge
softening_introduces_blocking_repair
```

#### 10.5.5 `degradation_reason` enum (top-level synthesis)

```text
no_improvement                              # composite delta < epsilon_improve
all_promotions_rolled_back                  # nothing applied
synthesis_disabled                          # CV_ASSEMBLY_SYNTHESIS_ENABLED=false
deterministic_only_mode                     # grader unavailable; synthesis still
                                            # ran but rubric pass is degraded
runner_up_drafts_unavailable                # only one persisted draft (rare;
                                            # would also trigger SC10 filtering
                                            # if the second draft was failed)
```

A `degraded=true` synthesis is not a failure: the winner is
persisted as the published surface (`final_cv_struct =
winner.cv_struct`, `final_cv_text = winner.cv_text`), the
grading and validator artifacts are persisted, and the dossier
(4.3.7) annotates the degradation. Operators see this as amber,
not red.

### 10.6 Cover letter

Cover-letter generation is **owned by 4.3.5** for the synthesis
output (per the 4.3.4 §22 resolution: cover letters are
generated only for the winner's surface, not per draft, and
they are generated post-synthesis).

- Generated from the merged output (`final_cv_struct +
  header_blueprint + classification.tone_family +
  stakeholder_surface.evaluator_coverage_target +
  jd_facts.normalized_title`) when the synthesis is non-degraded
  OR when synthesis is degraded but the winner is well-formed.
- Skipped when the stage is in `deterministic_only_mode` AND the
  cover-letter LLM is unavailable; `cover_letter=null` in that
  case; the publisher (4.3.6) handles `null` by surfacing a
  warning in the publish state, not by failing.
- The cover-letter prompt lives in
  `src/layer6_v2/cover_letter_generator.py` (preserved from
  Layer 6 V2). 4.3.5 invokes it once with the merged inputs.
- `cover_letter.validator_status` reflects a deterministic
  forbidden-phrase scan and a numeric-token scan against the
  master-CV evidence. Cover-letter validation is forgiving by
  comparison to the CV body validator: `validator_status=failed`
  → `cover_letter=null` and a warning event, but synthesis
  itself is not rolled back.

### 10.7 `merge_algorithm_version` semantics

Semver: `MAJOR.MINOR.PATCH`, e.g., `1.0.0`.

#### 10.7.1 When to bump

- **MAJOR** (e.g., `1.0.0` → `2.0.0`): any change to the
  `SynthesisRule` enum (rule add/remove/rename), any change to
  `pattern_compat_table` semantics, any change to the
  rollback-decision policy, any change to the deterministic
  ordering in §10.1 step 4. Replays of pre-bump jobs become
  non-byte-comparable across the bump.
- **MINOR** (`1.0.0` → `1.1.0`): non-breaking additions —
  adding a new tracked sub-component to `score_delta`, adding a
  new metadata field to `promoted_fragments[]`, broadening
  `pattern_compat_table` from `-` to `compat` for new pairs
  (replays produce ≥-superset of prior promotions but are not
  byte-equal).
- **PATCH** (`1.0.0` → `1.0.1`): cosmetic / tracing only —
  span name additions, metadata field renames in debug context,
  log-format changes. Replay byte-equality preserved.

#### 10.7.2 Replay compatibility

- The `SynthesisDoc` persists `merge_algorithm_version`. A
  replay of a job is the canonical re-run path: bump-time
  drift is **expected** and is captured by re-running 4.3.5
  on the same `input_snapshot_id` with the new version.
- The eval corpus (§18.13) freezes
  `merge_algorithm_version=1.0.0` for v1; bumps require
  recomputing expected outputs and gating regression as a
  separate explicit step.
- Byte-determinism scope: for fixed
  `(input_snapshot_id, merge_algorithm_version,
  RUBRIC_WEIGHTS_VERSION, SYNTHESIS_THRESHOLDS_VERSION,
  drafts payload)`, `final_cv_struct` and the deterministic
  rubric scores are byte-identical. Across version bumps,
  byte-equality is not guaranteed; reviewer-usefulness
  parity is the comparable surface and is gated at §18.15.

#### 10.7.3 Where the version is registered

`src/cv_assembly/grading/synthesis_versions.py`:

```python
MERGE_ALGORITHM_VERSIONS = {
    "1.0.0": MergeAlgorithmSpec(
        rule_enum=SYNTHESIS_RULE_ENUM_V1,
        ordering_fn=order_candidates_v1,
        rollback_policy=ROLLBACK_POLICY_V1,
        pattern_compat=PATTERN_COMPAT_TABLE_V1,
        first_seen_at="2026-04-25",
    ),
    # future versions added here; never mutated.
}
ACTIVE_MERGE_ALGORITHM_VERSION = "1.0.0"
```

The active version is shipped as code and pinned per release.
The active version is read by the stage at startup and is **not**
config-overridable in production (only test harnesses may
override via dependency injection).

## 11. Grading Harness Contract

The grading harness is a shared library consumed by 4.3.5 (rubric
mode), the §18 unit tests (corpus replays), and the §18.13 eval
harness. Its determinism is load-bearing.

### 11.1 Module and signature

Modules:

- `src/cv_assembly/grading/rubric_deterministic.py` — the three
  deterministic dimensions.
- `src/cv_assembly/grading/persuasiveness_llm.py` — the LLM
  persuasiveness scorer.
- `src/cv_assembly/grading/pairwise_grader.py` — the pairwise
  grader (gated).
- `src/cv_assembly/grading/composite.py` — the weighted-sum
  composer and tie-detector.

Public surface:

```python
def grade_drafts(
    drafts: tuple[DraftDoc, ...],
    *,
    blueprint: HeaderBlueprintDoc,
    patterns: dict[int, PatternDoc],
    presentation_contract: PresentationContractDoc,
    classification: ClassificationDoc,
    stakeholder_surface: Optional[StakeholderSurfaceDoc],
    pain_point_intelligence: Optional[PainPointIntelligenceDoc],
    candidate_data: CandidateData,
    rubric_weights: RubricWeightsConfig,
    grader_mode: Literal["rubric", "pairwise", "hybrid"],
    deterministic_only_mode: bool,
    epsilon_tied: float,
    tracer: CvAssemblyTracingSession,
) -> GradingResult: ...
```

`GradingResult` carries `grades: tuple[GradeDoc, ...]`,
`winner_draft_id`, `winner_selection_method ∈
{rubric_dominant | pairwise | deterministic_only_tiebreak}`,
`tied_at_epsilon: bool`, `pairwise_invoked: bool`,
`pairwise_outcome` (when invoked), and `trace_ref`.

### 11.2 Deterministic rubric pass (mode-agnostic; always runs first)

Three deterministic scorers, each pure (no I/O):

#### 11.2.1 Truth / Evidence Grounding (default 30%)

Score in `[0.0, 1.0]`:

```
base = 1.00
if validator_report.status == "repair_attempted":
    base -= 0.10                                # one-time penalty per repair pass
base -= 0.05 * lineage_repair_count             # per-action penalty, capped
base -= 0.02 * lineage_warning_count            # per-warning penalty, capped
base -= 0.10 * (header_validator_report.status == "repair_attempted")
base -= 0.05 * header_repair_count              # capped
base -= 0.20 * (number_resolution_unsourced_count > 0)
base -= 0.05 * forbidden_phrase_match_count     # warning-tier post-validator
base -= 0.05 * forbidden_proof_category_count   # warning-tier post-validator
truth_score = max(0.0, base)
```

Caps: each per-action penalty capped at 0.30 cumulative; the
score floor is 0.00 and ceiling is 1.00. The exact penalty
coefficients are versioned alongside `RUBRIC_WEIGHTS_VERSION`
(stored in `rubric_weights.json` under
`truth_penalty_coefficients`).

The validator outputs are read directly from
`DraftDoc.validator_report` and
`DraftDoc.header_validator_report`; this scorer does **not**
re-run the validators (the validators are pure and were already
run at 4.3.4 persist time). The rubric pass is therefore I/O-
free and pure.

#### 11.2.2 Pattern Fidelity (default 20%)

Score in `[0.0, 1.0]`:

```
match_signature      = 1.0 if DraftDoc.pattern_signature ==
                          PatternDoc.pattern_signature else 0.0
ach_in_map_ratio     = achievements_in_evidence_map_count /
                       max(achievements_total, 1)
ach_outside_penalty  = 0.10 * (achievements_outside_evidence_map_count > 0)
                       # > 0 should be impossible at this stage
                       # (4.3.4 §12 enforces) — reserved for drift detection
skills_in_map_ratio  = skills_in_evidence_map_count /
                       max(skills_total, 1)
section_emphasis     = score_section_emphasis_alignment(draft, pattern)
                       # ∈ [0,1]; deterministic comparison of bullet counts
                       # per section_id vs pattern.section_emphasis[].length_bias
proof_order          = score_proof_order_alignment(draft, pattern)
                       # ∈ [0,1]; deterministic comparison of section ordering
                       # vs pattern.proof_order_override[]
fidelity_score = (match_signature * 0.25 +
                  ach_in_map_ratio * 0.30 +
                  skills_in_map_ratio * 0.15 +
                  section_emphasis * 0.15 +
                  proof_order * 0.15) - ach_outside_penalty
fidelity_score = max(0.0, min(1.0, fidelity_score))
```

The internal sub-component weights `(0.25 / 0.30 / 0.15 / 0.15
/ 0.15)` are versioned in `rubric_weights.json` under
`pattern_fidelity_subweights`.

#### 11.2.3 Presentation-Contract Coverage (default 20%)

Score in `[0.0, 1.0]`:

```
proof_order_cov      = |realized_proof_categories ∩
                        pattern.proof_order_override| /
                       max(|pattern.proof_order_override|, 1)
must_signal_cov      = |bullets_addressing_must_signal| /
                       max(|ideal_candidate_presentation_model.must_signal|, 1)
dim_alignment        = 1.0 - normalized_kl(realized_dim_distribution,
                                            pattern.dimension_weights_override)
                       # ∈ [0,1]; KL divergence is normalized to a bounded scale
pain_point_cov       = |proof_categories_addressing_pain_map| /
                       max(|pain_point_intelligence.proof_map.categories|, 1)
                       # 0 with coverage_unresolved_marker=true when proof_map sparse
section_count_comp   = 1.0 - normalized_count_overflow(draft, cv_shape_expectations.counts)
ats_keyword_density  = jd_keyword_match_count / max(jd_keyword_target, 1)

coverage_score = (proof_order_cov * 0.25 +
                  must_signal_cov * 0.20 +
                  dim_alignment * 0.15 +
                  pain_point_cov * 0.15 +
                  section_count_comp * 0.10 +
                  ats_keyword_density * 0.15)
coverage_score = max(0.0, min(1.0, coverage_score))
```

Sub-weights versioned. When `pain_point_intelligence` is
unresolved, the `pain_point_cov` sub-weight (0.15) is
redistributed pro-rata to the other sub-components and
`coverage_unresolved_marker=true` is recorded.

### 11.2.4 Editorial-surface compliance penalties

The deterministic rubric must also penalize high-visibility editorial drift
that the eval corpus showed to be conversion-harming:

- unsupported competency inflation;
- sensitive metadata leakage;
- ATS-hostile structure that survived 4.3.4;
- persona/title drift into executive framing.

These are modeled as post-score penalties derived from 4.3.9 validator
reports and deterministic document inspection:

```
editorial_penalty =
    0.05 * unsupported_competency_count
  + 0.10 * (sensitive_metadata_violation_count > 0)
  + 0.05 * ats_surface_violation_count
  + 0.05 * persona_title_drift_count

editorial_penalty = min(editorial_penalty, 0.30)
coverage_score = max(0.0, min(1.0, coverage_score - editorial_penalty))
```

Definitions:

- `unsupported_competency_count`
  - skills present in `core_competencies` or header proof surfaces without
    4.3.1 authorization or without supporting experience evidence.
- `sensitive_metadata_violation_count`
  - public CV fields emitted outside `candidate_facts.display_policy` or
    `header_surface_policy`.
- `ats_surface_violation_count`
  - nonstandard section headers, layout-hostile constructs, or parser-hostile
    structural artifacts still visible in the final doc.
- `persona_title_drift_count`
  - cases where the visible identity behaves like a different lane than the
    eval-backed lane or exceeds the 4.3.1 title envelope.

### 11.3 LLM Persuasiveness pass (default 30%)

The LLM is invoked **once per draft** with a prompt that:

- includes the full `cv_text` (bounded; ≤ 16K tokens; 4.3.4
  bullet caps keep this safe in practice),
- includes `header_blueprint.identity` (titles, taglines pool),
- includes `presentation_contract.ideal_candidate_presentation_model
  .must_signal[]` and `tone_profile`,
- includes `stakeholder_surface.evaluator_coverage_target` for
  the hiring-manager-lens conditioning,
- includes the deterministic rubric scores for the same draft
  as a calibration anchor,
- forbids the LLM from changing the score of any other
  dimension,
- forbids the LLM from emitting prose suggestions or rewrites,
- requires JSON output: `{score: 0.0..1.0, rationale: <=300
  chars, evaluator_coverage_used: [str], abstention: bool}`.

Model: `gpt-5.4-mini` primary; `gpt-5.4` fallback when the mini
returns `abstention=true` or `confidence_band=low`. `temperature
= 0` (sampling-deterministic-as-far-as-the-provider-allows;
nondeterminism is bounded by the SC2 ±0.05 tolerance).

When `deterministic_only_mode = true`, the LLM is not invoked;
`hiring_manager_persuasiveness.score = 0.0`,
`abstention = true`, the 30% weight is redistributed pro-rata
to the other three dimensions.

### 11.4 Composite and tie detection

```
composite[i] = sum_d(weight[d] * dimension_score[i][d]) / 100
ranks       = argsort(composite, descending)
top_score   = composite[ranks[0]]
spread      = top_score - composite[ranks[1]]
tied        = spread < epsilon_tied
```

If `tied` AND `grader_mode ∈ {pairwise, hybrid}` AND the
pairwise grader is reachable: invoke pairwise (§11.5).
Otherwise: deterministic-ladder tiebreak (§11.4.1).

#### 11.4.1 Deterministic-ladder tiebreak

Applied when `tied=true` and (a) `grader_mode=rubric`, OR (b)
the pairwise grader is unreachable, OR (c)
`deterministic_only_mode=true`. The ladder breaks ties in this
fixed order:

1. Higher `truth_evidence_grounding.score`.
2. Higher `pattern_fidelity.score`.
3. Lower `lineage_repair_count`.
4. Lower `header_repair_count`.
5. Lower `pattern_id` (ascending). Patterns are 1, 2, 3 in
   `pattern_selection.patterns[]` order; this is the final
   tie-break and is itself deterministic per 4.3.3.

The picked draft becomes the winner; `winner_selection_method =
deterministic_only_tiebreak` when this ladder fired (regardless
of whether the LLM persuasiveness dimension contributed),
`cv_assembly.status=degraded` when the ladder fired due to (b)
or (c).

When the ladder fires due to (a) (`grader_mode=rubric` is the
operating mode and was deliberately chosen), the rollup remains
`completed` — rubric mode without pairwise is a legitimate
production posture, just one with stronger reliance on the
deterministic ladder. In that case `winner_selection_method =
deterministic_only_tiebreak` is recorded but is not in itself a
degradation signal; only paired with `deterministic_only_mode =
true` does it become `cv_assembly.status=degraded`.

### 11.5 Pairwise mode contract

Pairwise mode is **bounded to ε-tied resolution**. It is not a
parallel ranking surface in v1; it does not replace the rubric.

#### 11.5.1 When pairwise fires

- `grader_mode == "pairwise"`: pairwise fires unconditionally
  after the rubric pass, regardless of `tied`. The rubric
  scores are still computed and persisted; pairwise is
  authoritative for winner selection.
- `grader_mode == "hybrid"` (recommended after eval bench):
  pairwise fires only when `tied == true`. Rubric is
  authoritative when `tied == false`.
- `grader_mode == "rubric"` (default): pairwise never fires.

#### 11.5.2 Input shape

Whole-document pairwise comparisons (no section-level pairwise
in v1). For K persisted drafts, the grader runs at most
`K * (K - 1) / 2` pair comparisons (max 3 for K=3, 1 for K=2).

Per-pair input:

```text
{
  draft_a: {
    draft_id, pattern_label,
    cv_text,                                 # full
    header_picks_used,
    deterministic_rubric_scores
  },
  draft_b: { ... },                          # symmetric
  shared_context: {
    chosen_title,
    visible_identity_pool: [<3-5 candidates>],
    must_signal: [...],                      # ideal_candidate_presentation_model
    tone_profile,
    evaluator_coverage_target,
    pain_point_categories: [...]             # bounded summary, not full proof_map
  },
  rubric_anchor: {
    epsilon_tied, weights_used               # transparency only
  }
}
```

Order per pair is deterministic: `(min(draft_id_a, draft_id_b),
max(...))` lexicographic; `draft_a` is always the lower.

#### 11.5.3 Output shape

```text
PairwiseGradeOutput {
  pair: {draft_a, draft_b},
  preferred,                                 # "draft_a" | "draft_b" | "tied"
  margin,                                    # "decisive" | "slight" | "tied"
  rationale,                                 # <= 300 chars
  evaluator_lens_applied,                    # which evaluator the LLM weighted
  abstention: bool
}
```

The aggregate `PairwiseAggregateOutcome`:

```text
PairwiseAggregateOutcome {
  pairs: tuple[PairwiseGradeOutput, ...],
  preference_matrix,                         # K x K matrix of "win/tie/loss"
  borda_scores,                              # K-vector; deterministic transformation
  winner_draft_id,                           # by Borda + deterministic tie-break
  fully_tied: bool
}
```

#### 11.5.4 Tie handling (deterministic)

If `fully_tied = true` (no pair returns a clean preference, or
Borda scores are all equal), fall through to the
deterministic-ladder tiebreak (§11.4.1). Pairwise never returns
a random pick.

#### 11.5.5 Reproducibility

- Cache key: `(input_snapshot_id, K, sorted(draft_ids),
  rubric_weights_version, grader_mode,
  pairwise_prompt_version, pairwise_model)`.
- Cache stored in `cv_assembly.grades` collection alongside
  `GradeDoc`s; hit ⇒ skip the LLM invocation, project cached
  output deterministically.
- Bust on any change to `pairwise_prompt_version`,
  `pairwise_model`, or any input checksum.
- LLM `temperature=0`. ±0.05 tolerance on `borda_scores` is
  permitted across consecutive runs (provider nondeterminism);
  the deterministic tie-break disambiguates.

#### 11.5.6 Authority

- In `grader_mode="pairwise"`: pairwise winner is authoritative.
  Rubric scores are persisted but not used for selection;
  `winner_selection_method = pairwise`.
- In `grader_mode="hybrid"`: pairwise winner is authoritative
  **only when** the rubric pass returned `tied=true`;
  `winner_selection_method = pairwise`. When `tied=false`,
  pairwise is not invoked and rubric is authoritative;
  `winner_selection_method = rubric_dominant`.

### 11.6 Optional LLM polish (§22 — gated off in v1)

`CV_ASSEMBLY_SYNTHESIS_POLISH_ENABLED=false` in v1. When (and
only when) enabled, a single deterministic polish pass runs
after step 6 and before step 7 in §10.1, scoped to surface-level
grammar/punctuation/conjunction-choice on the merged output,
under a bounded prompt that is forbidden from touching facts,
numbers, titles, identity, or any tokens flagged by
`number_resolution_log[]`. The post-polish lineage validator
runs once more; any new violation discards the polish. The
polish is **not** a synthesis rule — it does not enter
`promoted_fragments[]`; it is recorded in
`SynthesisDebug.polish_full_trace` only.

## 12. Validator Consumption Contract

4.3.5 does not own either validator. It **consumes** the shared
validators declared in 4.3.4 §12 (`validate_lineage`) and 4.3.2
§11.2 (`validate_header`) in `mode="synthesis"`.

### 12.1 Required calls

For the synthesis output, before persist, in this fixed order:

1. After every per-promotion merge in step 5 (§10.1):
   `validate_lineage(synthesis_draft_in_progress, blueprint,
   pattern=None, master_cv, mode="synthesis", tracer)` —
   scoped to the affected sections; rollback decisions consume
   this report.
2. After all promotions are applied (or rolled back) and before
   step 7 (§10.1):
   `validate_header(synthesis_draft.cv_struct.header,
   blueprint, master_cv, mode="synthesis", pattern=None,
   tracer)` — runs the full header validator pass.
3. After header validation completes (and any header repair
   applies) and before step 7:
   `validate_lineage(synthesis_draft, blueprint, pattern=None,
   master_cv, mode="synthesis", tracer)` — final full-pass
   lineage validation; this is the report persisted on
   `SynthesisDoc.validator_report`.

The header validator output (`HeaderValidatorReport`) is
persisted on `SynthesisDoc.header_validator_report` verbatim.
The final lineage validator output
(`EvidenceLineageValidatorReport`) is persisted on
`SynthesisDoc.validator_report` verbatim.

### 12.2 Validator failure handling

- `pass`: proceed.
- `repair_attempted` (one or more deterministic repair actions
  fired and healed all `severity=blocking` violations):
  proceed; `SynthesisDoc.status = partial` IF this is the only
  degradation signal, else inherit the more severe status;
  `degraded` is **not** set by `repair_attempted` alone.
- `failed` after one pass: roll back the most recent promotion
  that introduced the violation, retry validators once, then:
  - if `pass | repair_attempted`: proceed.
  - if `failed` again: roll back the next-most-recent
    promotion and retry.
  - if all promotions are rolled back and `failed` remains:
    `SynthesisDoc.degraded = true`,
    `degradation_reason = all_promotions_rolled_back`,
    `final_cv_struct = winner.cv_struct`,
    `final_cv_text = winner.cv_text`. The validator reports on
    the winner-only output remain `pass` (the winner already
    passed the validators at 4.3.4 persist time; running them
    on the winner again in `mode="synthesis"` is a sanity
    check).

A `failed` validator status on the **winner-only** output is
impossible by construction (4.3.4 §13.3 / §15.3 prevent
persistence of failed-validator drafts); a drift here is a
hard blocker — operator triage, no auto-repair.

### 12.3 Allowed deterministic repair actions

Inherited verbatim from 4.3.4 §12.4 and 4.3.2 §11.2.3.
Synthesis adds **no new** repair actions. Synthesis's role is
strictly to apply or roll back a closed set of promotion rules;
the validators' repair surfaces are the only deterministic
mediation between merged content and persistence.

### 12.4 What gets persisted

`SynthesisDoc.validator_report` and
`SynthesisDoc.header_validator_report` carry the **final-pass**
reports. Per-promotion reports are recorded in
`SynthesisDebug.validator_full_trace_pre_repair[]`; the
pre/post-repair distinction is preserved for postmortem.

### 12.5 Validator ordering rationale

Header validator runs **after** all per-promotion lineage
validations and **before** the final lineage pass. Rationale:

- Header repairs (`substitute_from_pool`,
  `clamp_band`) may swap a `chosen_title` candidate within the
  blueprint pools (4.3.2 §11.2.3); running header before final
  lineage means the final lineage pass sees the realized
  header.
- Per-promotion lineage runs scoped to affected sections, so
  early failures roll back surgically without re-validating
  the whole document; the final pass catches whole-document
  invariants (e.g., section count compliance) that per-
  promotion passes do not assess.

### 12.6 Mode semantics under synthesis

- `validate_lineage(..., mode="synthesis", pattern=None)`
  asserts pool membership against the blueprint and achievement
  membership against `union_evidence_map.achievements`. This is
  the surface that allows cross-pattern promotion; it is also
  the surface that prevents promoting an achievement the union
  does not include (i.e., one that no persisted draft's
  pattern picked).
- `validate_header(..., mode="synthesis", pattern=None)`
  asserts pool membership against the blueprint as a whole;
  it does not require any single pattern's `header_picks` to
  be present in the realized prose (because R005 may have
  swapped a pool member).

## 13. Cross-Artifact Invariants

Restated as hard implementation rules; enforced by §12 and the
synthesis algorithm (§10).

- **I1.** `winner.draft_id ∈ {d.draft_id for d in
  cv_assembly.drafts[] if d.status != "failed"}`.
- **I2.** Exactly one `GradeDoc` has `ranking_tier = "winner"`;
  all others have `ranking_tier ∈ {runner_up, third}`.
- **I3.** `synthesis.final_cv_struct.header.title_string ==
  header_blueprint.identity.chosen_title` (frozen across
  every draft and the synthesis; 4.3.2 §I, 4.3.4 §I2).
- **I4.** Every `synthesis.promoted_fragments[].source_lineage_ref
  .achievement_id` ∈ `union_evidence_map.achievements`.
- **I5.** Every `synthesis.promoted_fragments[].rule_id` ∈
  `SynthesisRule` enum (§10.3).
- **I6.** No `synthesis.promoted_fragments[].rule_id ∈
  {R001, R005}` (the replace-mode rules) when
  `cv_assembly.draft_assembly_summary.degraded_mode == true`
  AND only one runner-up draft exists — replacement requires
  a meaningful comparison surface; when only one runner-up
  exists, R002 / R003 / R006 (fill-only rules) are still
  valid, but replacement is disabled (recorded as
  `degraded_mode_replacement_disabled=true`).
- **I7.** `synthesis.composite_score - winner.composite_score ≥
  ε_improve` when `synthesis.degraded == false`.
- **I8.** `synthesis.validator_report.status ∈ {pass,
  repair_attempted}`. Never `failed`.
- **I9.** `synthesis.header_validator_report.status ∈ {pass,
  repair_attempted}`. Never `failed`.
- **I10.** Every `GradeDoc.composite_score` is computed under
  the **same** `RUBRIC_WEIGHTS_VERSION`,
  `rubric_weights.weights_used`, and `pattern_label` resolution
  rule; cross-draft composite differences come from dimension
  scores alone, not from weight drift.
- **I11.** `synthesis.evidence_lineage` is consistent with
  `synthesis.final_cv_struct`: every realized claim resolves
  to a `bullet_lineage[]` entry; every header pool reference
  used in realized prose resolves to a header pool member; no
  derived marker is emitted without a registered `rule_id`
  (4.3.4 §16 derived-markers registry).
- **I12.** `synthesis.cover_letter`, when non-null, has
  `validator_status=pass`; failed cover letters set
  `cover_letter=null` and a warning event but do not fail
  synthesis.
- **I13.** `synthesis.union_evidence_map_ref.union_signature`
  matches the recomputed union_signature over the persisted
  drafts at the time of synthesis. Drift here indicates
  external mutation between claim and persist; the stage
  fails-closed (operator triage).
- **I14.** `synthesis.merge_algorithm_version ==
  ACTIVE_MERGE_ALGORITHM_VERSION`. Mismatch is impossible by
  construction; an integrity check at persist asserts it.
- **I15.** Failed drafts are never selected as winner and never
  used as a synthesis source (SC10).
- **I16.** No `synthesis.promoted_fragments[]` introduces a
  credibility marker not already present in at least one
  persisted draft's `evidence_lineage.derived_markers[]` or
  `cv_struct.header.credibility_markers[]`.
- **I17.** No `synthesis.promoted_fragments[]` introduces a
  numeric token whose `unit_class` differs from the base
  fragment's unit_class at the same `slot_ref` (R001 and R005
  preserve unit class to keep grammar integrity stable).
- **I18.** When `winner_selection_method = pairwise`, the
  pairwise output's `winner_draft_id` matches
  `cv_assembly.winner.draft_id`. When
  `winner_selection_method = rubric_dominant`, the rubric
  composite ranking matches. When
  `winner_selection_method = deterministic_only_tiebreak`, the
  §11.4.1 ladder matches.
- **I19.** No selected winner or synthesis output may contain a
  `core_competency` skill lacking 4.3.1 competency-surface
  authorization.
- **I20.** No selected winner or synthesis output may expose
  header/public metadata outside `candidate_facts.display_policy`
  and 4.3.2 `header_surface_policy`.
- **I21.** A draft that violates ATS-safe structural rules may not
  outrank a structurally compliant draft on the strength of
  persuasiveness alone; the deterministic penalties in §11.2.4 must
  dominate.

If any invariant fails after one deterministic repair pass,
synthesis is rolled back per §10.5 or §14.

## 14. Fail-Open / Fail-Closed

### 14.1 Fail-open (per stage)

- **Grader model unavailable** → `deterministic_only_mode=true`;
  composite recomputed with redistributed weights;
  `cv_assembly.status=degraded` only when the deterministic
  spread is within `epsilon_tied` (§8.2 / §11.4.1). Otherwise
  the rollup is `completed` or `partial` based on the rest of
  the run.
- **Pairwise grader unavailable** when `grader_mode ∈ {pairwise,
  hybrid}` AND `tied=true` → fall through to the deterministic
  ladder; `pairwise_unreachable=true`;
  `cv_assembly.status=degraded`.
- **Synthesis produces no improvement** (composite delta <
  `epsilon_improve`) → `degraded=true`,
  `degradation_reason=no_improvement`. Winner is published as
  `final_cv_struct=winner.cv_struct`. Not a failure.
- **All promotions rolled back** → `degraded=true`,
  `degradation_reason=all_promotions_rolled_back`. Winner is
  published as final. Not a failure.
- **Cover-letter generation fails or LLM unavailable** →
  `cover_letter=null`, `cover_letter_warning` event. Not a
  failure of synthesis.
- **One persisted draft is `partial`** (4.3.4 validator repair
  fired) → graded with truth penalty; eligible to win.

### 14.2 Fail-open (per job)

- **Two-draft mode** (4.3.4 `degraded_mode=true`) — grade two
  drafts; synthesize from one runner-up; `cv_assembly.status
  =degraded` is inherited from 4.3.4 if no other degradation
  signal fires here.

### 14.3 Fail-closed (per stage)

- **Header validator failed on synthesis** after rollback of all
  header-affecting promotions (§12.2) → impossible if the
  winner already passed; if drift detected, stage fails
  terminally; operator triage.
- **Lineage validator failed on synthesis** after rollback of
  all promotions → impossible by construction (the
  winner-only output already passed at 4.3.4 persist); if
  observed, stage fails terminally; operator triage.
- **Pattern-signature drift** between draft and persisted
  `PatternDoc` (§13 I13) → stage fails terminally; operator
  triage.
- **`merge_algorithm_version` mismatch** between active code and
  config → stage refuses to register; operator alert.
- **Schema version mismatch on `DraftDoc` or `HeaderBlueprintDoc`**
  → stage fails terminally; operator triage.

### 14.4 Fail-closed (per job)

- **Fewer than two non-failed drafts at claim time** → stage is
  not enqueued; `cv_assembly.status=failed` per 4.3.4 rollup.
  No best-effort single-draft "winner".
- **Pattern selection record disappeared between claim and
  persist** (rare; indicates external mutation) → stage fails
  terminally; deadletter.
- **Mongo write failure during persist** → retry per
  `max_attempts=3`; on exhaustion, deadletter.

### 14.5 What is **not** fail-open

- Promoting a fragment whose `(role_id, achievement_id,
  variant_id)` is not in the union — no fabricated lineage
  satisfies any rule.
- Inventing a tagline or summary to bridge a rolled-back
  promotion's prose.
- Substituting a different `chosen_title` to satisfy a runner-up
  pattern's framing — title is frozen.
- Selecting a non-winning draft as the published surface — no
  human-pick override (deferred to 4.4 CV Editor).
- Skipping the validator passes to "publish faster". Validators
  are pure and fast; skipping them is forbidden in every mode
  including `deterministic_only_mode`.
- Inferring a metric to support a promoted fragment that lost
  its number under 4.3.4 §11. Promoted fragments inherit their
  source's `number_resolution_log[]` exactly.

## 15. Safety / Anti-Hallucination

Inherits the cross-family anti-hallucination invariants (4.3
umbrella §9). The §12 validator consumption is the load-bearing
enforcement surface; §10.2–§10.3 are the load-bearing
enforcement on rule application. Specific rules restated:

- Rubric dimension 1 (Truth) is weighted 30% by default; the
  weight is configurable but cannot drop below 25% (config-load
  invariant).
- Synthesis rules are constraint-based, not prompt-based; no
  free LLM rewrite can occur on facts. The optional polish pass
  (§11.6) is gated off in v1.
- Cross-draft promotion never introduces a new entity (system,
  customer, product, framework) — the source fragment must
  already cite that entity.
- Numbers may only be promoted when the `achievement_id` is the
  same (R001) or when the slot is unfilled (R002, R003) and
  the fragment's `number_resolution_log[]` outcome is
  `passed_*` or `repaired_softened_to_band` (never
  `failed_unsourced`).
- Cross-pattern promotion (R003, R005, R006) is bounded by the
  pattern-compatibility table (§10.3.7); incompatible pairs
  are filtered before ordering.
- Identity is frozen: `chosen_title`, `chosen_title_strategy`,
  `identity_tags[]`, `not_identity[]`, `forbidden_phrases[]`,
  AI band caps, and leadership band caps from the blueprint
  are never modified by synthesis.
- 4.2.6 truth-constrained emphasis rules are enforced
  deterministically via the validator; `omit_rules[]` and
  `downgrade_rules[]` are honored at merge time per the §11
  validator consumption contract.
- No protected-trait inference, clinical profiling, or private
  stakeholder motives. Carried from the 4.3 umbrella.
- No web search, no cross-job reasoning, no candidate-wide
  claims not pinned to the master-CV snapshot.
- Cover-letter generation reuses the Layer 6 V2 cover-letter
  prompt (preserved); the cover letter is a derived surface
  bounded by the synthesis's `cv_struct` plus blueprint plus
  pre-enrich state.

## 16. Operational Catalogue

### 16.1 Stage owner

Owned by the cv_assembly worker.
Module: `src/cv_assembly/stages/grade_select_synthesize.py`.
Stage definition: `src/cv_assembly/stage_registry.py`.
Co-owners (shared library only): 4.3.2 (`validate_header`),
4.3.4 (`validate_lineage`), Layer 6 V2
(`cover_letter_generator.py`).

### 16.2 Prerequisite artifacts

- `cv_assembly.drafts[]` (4.3.4) — hard prerequisite (§8.1).
- `cv_assembly.draft_assembly_summary` (4.3.4) — hard
  prerequisite.
- `cv_assembly.header_blueprint` (4.3.2) — hard prerequisite.
- `cv_assembly.pattern_selection` (4.3.3) — hard prerequisite.
- `pre_enrichment.presentation_contract.*` — hard prerequisite
  for the first two; degraded-allowed for the last three (§8.2).
- `pre_enrichment.{classification, jd_facts,
  stakeholder_surface, pain_point_intelligence}` — read-only;
  degraded-allowed for the last two.
- Master-CV via loader v2 — hard prerequisite.
- `data/eval/cv_assembly/rubric_weights.json` — hard
  prerequisite at import.
- `data/eval/cv_assembly/synthesis_thresholds.json` — hard
  prerequisite at import.

### 16.3 Persisted Mongo locations

| What | Location |
|---|---|
| Full grade artifact (per draft) | `cv_assembly.grades` collection (or subdocument), unique filter `(level2_id, input_snapshot_id, draft_id, rubric_weights_version)` |
| Grade slot in level-2 | `level-2.cv_assembly.grades[<draft_pattern_id - 1>]` |
| Winner | `level-2.cv_assembly.winner` |
| Synthesis | `level-2.cv_assembly.synthesis` (full doc; compact projection inline) |
| Stage state | `level-2.cv_assembly.stage_states.cv.grade_select_synthesize` |
| Job lifecycle | `level-2.lifecycle = "cv_assembled"` (CAS) |
| Stage run audit | `cv_assembly_stage_runs` (one row) |
| Job run aggregate | `cv_assembly_job_runs` |
| Work item | `work_items`, `task_type=cv.grade_select_synthesize` (one) |
| Alerts | `cv_assembly_alerts` (on deadletter only, rate-limited) |
| Pairwise cache | `cv_assembly.grades` collection, sub-document per cache key |

### 16.4 Stage-run records touched

`cv_assembly_stage_runs` row with: `status`, `trace_id`,
`trace_url`, `provider_used`, `model_used`,
`pairwise_model_used`, `prompt_version`,
`pairwise_prompt_version`, `tokens_input`, `tokens_output`,
`cost_usd`, `winner_draft_id`, `winner_pattern_label`,
`winner_selection_method`, `synthesis_degraded`,
`synthesis_degradation_reason`, `synthesis_promoted_count`,
`synthesis_rolled_back_count`, `validator_status`,
`header_validator_status`, `cover_letter_status`,
`upstream_draft_assembly_summary_status`, `fail_open_reason`
(when present).

### 16.5 Work-item semantics

- Enqueued by the 4.3 sweeper when
  `cv_assembly.draft_assembly_summary.status ∈ {completed,
  partial, degraded}` AND `drafts_persisted_count ≥ 2`.
- Payload per §7.4.
- Claimed atomically via `StageWorker.claim` with lease.
- On success, the work item writes `GradeDoc[]`, `winner`,
  `SynthesisDoc`, and updates
  `cv_assembly.stage_states.cv.grade_select_synthesize`. The
  4.3 sweeper finalizes `lifecycle=cv_assembled` via the
  `cv_assembled` finalizer CAS (4.3.6 §8 inverse — same
  pattern, applied here).
- On failure (terminal), the work item writes `failure_record`
  on `cv_assembly.stage_states.cv.grade_select_synthesize`;
  the job rolls up to `cv_assembly.status=failed`.

### 16.6 Cache semantics

- Cache key: `(level2_id, input_snapshot_id,
  GRADE_SCHEMA_VERSION, SYNTHESIS_SCHEMA_VERSION,
  RUBRIC_WEIGHTS_VERSION, SYNTHESIS_THRESHOLDS_VERSION,
  ACTIVE_MERGE_ALGORITHM_VERSION, prompt_version,
  pairwise_prompt_version)`.
- Cache stored in `cv_assembly.grades` and
  `cv_assembly.synthesis` documents; hit ⇒ skip LLM
  invocations, project cached docs into a new
  `attempt_token`-keyed write, re-run validators (validators
  are pure and free).
- Bust on any change to a cache-key component or any draft
  payload.
- Emits `scout.cv_assembly.grading_synthesis.cache.{hit,miss}`
  events.

### 16.7 Retry / repair behavior

- `max_attempts = 3` at the work-item level.
- One in-stage validator repair pass per validator invocation
  (inherited from 4.3.2 / 4.3.4).
- One LLM transport retry on recoverable failure
  (`error_timeout`, `error_subprocess`, `error_no_json`,
  `error_schema`) per persuasiveness call and per pairwise
  pair.
- `job_fail_policy=fail_closed` only when the closed list
  in §14.3 / §14.4 fires.

### 16.8 Heartbeat expectations

- Stage heartbeat every 60 s by the worker
  (`CV_ASSEMBLY_STAGE_HEARTBEAT_SECONDS=60`).
- The stage must yield CPU between phases
  (`rubric_first`, `pairwise`, `winner_select`, `merge`,
  `header_validate`, `lineage_validate`, `cover_letter`,
  `persist`).
- Launcher-side wrapper (§19) emits operator heartbeat every
  15-30 s with last substep, last validator phase, last
  rule application, Codex/LLM PID and stdout/stderr tail.
- Silence > 90 s = stuck-run flag.

### 16.9 Feature flags

- `CV_ASSEMBLY_GRADE_SELECT_SYNTHESIZE_ENABLED` — master flag
  for the stage. Off: stage not registered; 4.3.5 not
  invoked; the 4.3 sweeper does not enqueue this work item;
  legacy publishing path takes whichever single draft 4.3.4
  produced (debug-only).
- `CV_ASSEMBLY_SYNTHESIS_ENABLED` — gates the synthesis step
  only. Off: grading + winner selection still run;
  `cv_assembly.synthesis` is populated with `degraded=true`,
  `degradation_reason=synthesis_disabled`, `final_cv_struct
  = winner.cv_struct`, `final_cv_text = winner.cv_text`. Used
  in shadow mode and for rollback.
- `CV_ASSEMBLY_GRADER_MODE` — `rubric | pairwise | hybrid`.
  Default: `rubric` in v1; recommended `hybrid` after eval
  bench passes (§22 triage).
- `CV_ASSEMBLY_GRADER_TIEBREAKER_ENABLED` — kept for backward
  compatibility with the original plan; effectively
  `mode=hybrid`. Default: `false` in v1.
- `CV_ASSEMBLY_SYNTHESIS_POLISH_ENABLED` — gates the optional
  polish pass (§11.6). Default: `false`.
- `CV_ASSEMBLY_GRADER_DETERMINISTIC_ONLY` — forces
  `deterministic_only_mode=true` regardless of LLM
  availability. Used in eval and in some integration tests.
  Default: `false`.

### 16.10 Operator-visible success / failure signals

- `level-2.cv_assembly.stage_states.cv.grade_select_synthesize.status` —
  `pending | leased | completed | failed | deadletter`.
- `level-2.cv_assembly.winner` — populated on success.
- `level-2.cv_assembly.synthesis.degraded` — `true | false`.
- `level-2.cv_assembly.synthesis.degradation_reason` — set when
  degraded.
- `level-2.cv_assembly.status` — `completed | partial |
  degraded | failed`.
- `cv_assembly_stage_runs` row with `trace_id`, `trace_url`,
  `winner_selection_method`, `fail_open_reason`.
- `cv_assembly_alerts` row only on deadletter or repeated
  `deterministic_only_mode` events across consecutive jobs.

### 16.11 Downstream consumers

- `cv.publish.render.cv` (4.3.6) — reads
  `cv_assembly.synthesis.final_cv_struct` and
  `cv_assembly.synthesis.final_cv_text`; reads
  `cv_assembly.synthesis.cover_letter` when present; reads
  `cv_assembly.winner.draft_id` and
  `cv_assembly.synthesis.body_sha256`-equivalents (computed at
  publish time, not by 4.3.5) for idempotency.
- `cv.publish.render.dossier` (4.3.6 + 4.3.7) — reads
  `cv_assembly.synthesis.evidence_lineage`,
  `cv_assembly.winner.draft_id`,
  `cv_assembly.synthesis.composite_score`, the winner
  `GradeDoc.dimensions.*` rationales, and (for partial-section
  fallback) the persisted `drafts[]` for read-only display.
- `cv_assembly.compat.projection` (4.3.7) — reads
  `synthesis.composite_score`,
  `synthesis.debug_context.reasoning_summary`, and the winner
  `GradeDoc` rationale per the 4.3.6 §10 projection map.

### 16.12 Rollback strategy

- Toggle `CV_ASSEMBLY_SYNTHESIS_ENABLED=false` → grading +
  winner still run; synthesis is degraded to winner-verbatim;
  the publisher (4.3.6) sees a synthesis with
  `degraded=true, degradation_reason=synthesis_disabled` and
  publishes the winner.
- Toggle `CV_ASSEMBLY_GRADE_SELECT_SYNTHESIZE_ENABLED=false`
  → 4.3.5 not invoked; legacy single-pass Layer 6 V2 path
  takes over (debug-only); no `cv_assembled` lifecycle
  transition occurs through the 4.3 lane.
- Existing `cv_assembly.grades`, `cv_assembly.winner`, and
  `cv_assembly.synthesis` documents remain for audit; no
  deletion.
- No schema migration on rollback; the schemas are purely
  additive.

## 17. Langfuse Tracing Contract

Inherits 4.3 umbrella verbatim. Stage-specific rules below are
normative.

### 17.1 Canonical trace, stage span, subspans

- Trace: `scout.cv.run` (4.3 umbrella).
- Job span: `scout.cv.job` with
  `langfuse_session_id=job:<level2_id>`.
- Stage span: `scout.cv_assembly.grading_synthesis` — emitted
  by the cv_assembly worker for the single 4.3.5 work item.

### 17.2 Substep spans

```
scout.cv_assembly.grading_synthesis                # stage span
  ├── .preflight                                   # prereq checks; SynthesisContext build
  ├── .rubric_first                                # deterministic rubric pass over all drafts
  ├── .persuasiveness_llm                          # per-draft LLM persuasiveness call
  ├── .pairwise                                    # only when fired
  │     ├── .pair.<a>_vs_<b>                       # one per pair
  │     └── .aggregate
  ├── .winner_select                               # composite + tie + selection
  ├── .merge                                       # promotion-ladder application
  │     └── .rule.<rule_id>                        # one per rule application (capped)
  ├── .header_validate                             # validate_header(mode="synthesis")
  ├── .lineage_validate                            # validate_lineage(mode="synthesis") final
  ├── .repair                                      # any deterministic repair in either validator
  ├── .cover_letter                                # cover-letter LLM call
  └── .persist                                     # Mongo write (transactional)
```

Cardinality bounded: `.rule.*` is capped at 50 per stage span
(any excess collapsed into a single
`scout.cv_assembly.grading_synthesis.rule.overflow` event with
`excess_count`). `.pair.*` is bounded at K(K-1)/2 ≤ 3.

### 17.3 Events

- `scout.cv_assembly.grading_synthesis.insufficient_drafts` —
  fires when the stage somehow claims with < 2 non-failed
  drafts (should never happen given §8.1 prereqs; recorded
  for drift detection).
- `scout.cv_assembly.grading_synthesis.deterministic_only_mode`
  — fires when grader unavailable and the deterministic
  fallback engages.
- `scout.cv_assembly.grading_synthesis.pairwise_invoked` —
  fires when pairwise mode actually runs; metadata
  `{tied_at_epsilon, K, grader_mode}`.
- `scout.cv_assembly.grading_synthesis.pairwise_unreachable` —
  fires when pairwise mode would fire but the model is
  unreachable.
- `scout.cv_assembly.grading_synthesis.winner_selected` — one
  per job; metadata `{winner_draft_id, winner_pattern_label,
  winner_selection_method, composite_score, spread_at_top}`.
- `scout.cv_assembly.grading_synthesis.synthesis_rule_applied` —
  one per applied promotion; metadata `{rule_id,
  source_draft_id, source_pattern_label, section_id,
  slot_index?, score_delta_truth, score_delta_persuasiveness}`.
- `scout.cv_assembly.grading_synthesis.synthesis_rule_rolled_back`
  — one per rollback; metadata `{rule_id, source_draft_id,
  section_id, rollback_reason, validator_violations_count}`.
- `scout.cv_assembly.grading_synthesis.validator_repair_applied`
  — one per validator repair action during synthesis;
  metadata `{validator: lineage|header, rule_id, action,
  before_signature, after_signature}`.
- `scout.cv_assembly.grading_synthesis.validator_failure` —
  fires on any `validator_report.status=failed` event during
  synthesis (drift detection; should not fire if winner was
  validated at 4.3.4).
- `scout.cv_assembly.grading_synthesis.degraded_synthesis` —
  fires when `synthesis.degraded=true`; metadata
  `{degradation_reason, composite_score_delta_vs_winner,
  promoted_count, rolled_back_count}`.
- `scout.cv_assembly.grading_synthesis.cover_letter_warning` —
  fires when cover-letter generation fails or returns
  `validator_status=failed`; metadata `{reason}`.
- `scout.cv_assembly.grading_synthesis.cache.hit` /
  `.cache.miss`.
- Lifecycle events (`claim`, `enqueue_next`, `retry`,
  `deadletter`, `release_lease`) per 4.3 umbrella.

### 17.4 Required metadata on every span / event

`job_id`, `level2_id`, `correlation_id`,
`langfuse_session_id`, `run_id`, `worker_id`, `task_type`,
`stage_name`, `attempt_count`, `attempt_token`,
`input_snapshot_id`, `master_cv_checksum`,
`presentation_contract_checksum`, `header_blueprint_checksum`,
`pattern_selection_checksum`, `jd_checksum`,
`draft_assembly_summary_checksum`, `rubric_weights_version`,
`synthesis_thresholds_version`, `merge_algorithm_version`,
`lifecycle_before`, `lifecycle_after`, `work_item_id`.

### 17.5 Stage-specific metadata on the stage span (on end)

- `status` ∈ `{completed, partial, degraded, failed}`,
- `draft_count_input`,                                # drafts at claim
- `draft_count_graded`,                               # drafts that received a GradeDoc
- `draft_count_failed_filtered`,                      # drafts excluded as failed
- `winner_draft_id`,
- `winner_pattern_id`,
- `winner_pattern_label`,
- `winner_composite_score`,
- `winner_selection_method`,
- `pairwise_mode_enabled` (bool),
- `pairwise_invoked` (bool),
- `pairwise_unreachable` (bool),
- `deterministic_only_mode` (bool),
- `tied_at_epsilon` (bool),
- `composite_spread_top1_top2`,
- `epsilon_tied`,
- `epsilon_replace`,
- `epsilon_improve`,
- `synthesis_promoted_count`,
- `synthesis_rolled_back_count`,
- `synthesis_rule_application_count` (synonymous with
  `synthesis_promoted_count + synthesis_rolled_back_count`),
- `synthesis_degraded` (bool),
- `synthesis_degradation_reason?`,
- `synthesis_composite_score?`,
- `synthesis_composite_delta_vs_winner?`,
- `lineage_validator_status`,
- `header_validator_status`,
- `cover_letter_status`,
- `model_primary`,
- `pairwise_model?`,
- `tokens_input`, `tokens_output`, `cost_usd`,
- `prompt_version`, `pairwise_prompt_version`, `prompt_git_sha`,
- `cache_hit` (bool),
- `trace_ref` — back-pointer to Mongo
  `cv_assembly_stage_runs` row.

### 17.6 What flows into Mongo trace refs

- `cv_assembly_stage_runs` — one row,
- `cv_assembly_job_runs` — aggregate updated,
- `cv_assembly.stage_states.cv.grade_select_synthesize.{trace_id,
  trace_url}`,
- `GradeDoc.trace_ref` — per-draft span ref,
- `SynthesisDoc.langfuse_trace_ref` — synthesis span ref.

An operator opening a `level-2` job in the UI reaches the
grading trace, the synthesis trace, and each promotion's
`synthesis_rule_applied` event in one click.

### 17.7 Forbidden in Langfuse

- full `cv_text` body (drafts or synthesis),
- full `cv_struct` body,
- full bullet text beyond a 240-char preview,
- full `evidence_lineage` body,
- full `validator_report.repaired_struct` body,
- full `debug_context` body (`GradeDebug`, `SynthesisDebug`),
- full pairwise rationales beyond 300 chars (the rationale
  field itself is bounded; the LLM raw response is not in
  spans, only in `GradeDebug.llm_persuasiveness_full_trace`),
- raw cover-letter text beyond a 240-char preview,
- raw LLM prompts unless `_sanitize_langfuse_payload` is
  applied AND `LANGFUSE_CAPTURE_FULL_PROMPTS=true`.

Previews capped at 240 chars via `_sanitize_langfuse_payload`.
Numeric counters and small enums are not capped.

### 17.8 What may live only in `debug_context` (Mongo)

- raw LLM persuasiveness response per draft,
- raw pairwise responses per pair,
- full per-promotion attempt log,
- full validator pre/post-repair traces,
- full union evidence map,
- full polish pass trace (when enabled),
- full cover-letter generation trace,
- LLM request ids and full repair prompts.

### 17.9 Cardinality and naming safety

- Substep span names are a fixed, small set (§17.2).
- `.rule.*` cardinality bounded; overflow event collapses
  excess.
- `.pair.*` cardinality bounded by K(K-1)/2.
- `synthesis_rule_applied` and `synthesis_rule_rolled_back`
  events bounded similarly; overflow collapsed.
- LLM fallback bounded → ≤ 2 `persuasiveness_llm.*` spans per
  draft and ≤ 2 `pairwise.pair.*` per pair.

### 17.10 Operator debug checklist (normative)

An operator must be able to diagnose each of these from
`level-2` → trace in < 2 minutes:

- winner unexpected → `winner_selected` event with metadata,
  cross-checked against the per-draft `composite_score` and
  the `composite_spread_top1_top2`.
- pairwise should have fired but didn't → check
  `pairwise_invoked`, `pairwise_unreachable`, and
  `tied_at_epsilon` metadata.
- synthesis stuck on rollbacks → count
  `synthesis_rule_rolled_back` events vs
  `synthesis_rule_applied`; correlate with
  `validator_failure` events and `rollback_reason` metadata.
- synthesis no improvement → `degraded_synthesis` event with
  `degradation_reason=no_improvement` and
  `composite_score_delta_vs_winner < epsilon_improve`.
- deterministic-only mode → `deterministic_only_mode` event
  on the stage span.
- cover-letter missing → `cover_letter_warning` event.
- cache-hit unexpected → `.cache.hit` event with the cache key.
- stuck stage → no heartbeat after lease expiry; correlate
  via `worker_id` and `attempt_token`.

## 18. Tests And Evals

### 18.1 Unit tests (`tests/unit/cv_assembly/`)

- `test_synthesis_context_builder.py` — verifies `SynthesisContext`
  is constructible from realistic upstream artifacts; freeze
  semantics; pure (no I/O) under socket / Mongo patches.
- `test_union_evidence_map.py` — table-driven over §9.4 union
  composition; signature byte-stability across two runs;
  union ⊇ winner pattern ⊇ runner-up patterns when
  achievement sets overlap.
- `test_rubric_deterministic.py` — table-driven over §11.2
  formulas (truth, fidelity, coverage); penalty caps; sub-
  weights from `rubric_weights.json`; redistribution under
  `deterministic_only_mode`.
- `test_rubric_weights_config.py` — config loader; invariants
  (sum to 100, integer weights, all dimensions present);
  role-family override resolution; rejection of malformed
  configs.
- `test_persuasiveness_llm_contract.py` — prompt shape; output
  parsing; abstention handling; ±0.05 tolerance assertion
  across two runs.
- `test_pairwise_grader.py` — input shape; output parsing;
  per-pair determinism (lexicographic ordering); aggregate
  Borda computation; tied-aggregate fallback to deterministic
  ladder; reproducibility cache key.
- `test_composite_and_tie.py` — tie detection at ε; fold-
  through to deterministic ladder; ladder ordering correctness.
- `test_synthesis_rule_enum.py` — one fixture per `rule_id` in
  §10.3 — pre-merge state, post-merge state, expected
  `rolled_back_attempts[]` if applicable, expected
  `promoted_fragments[]` entry.
- `test_synthesis_ordering.py` — fixtures asserting §10.1 step
  4 ordering is deterministic and stable under candidate
  permutation.
- `test_synthesis_rollback.py` — fixtures per `rollback_reason`
  enum; one-pass validator semantics; rollback never re-runs
  earlier promotions.
- `test_merge_algorithm_versioning.py` — version registry;
  bump rules; replay byte-equality at fixed version.
- `test_synthesis_thresholds_config.py` — config loader;
  invariants; role-family override resolution.
- `test_pattern_compat_table.py` — table consistency (no
  asymmetric `compat` entries unless intentional); `default_role_family`
  always `compat`.
- `test_validator_consumption.py` — synthesis calls
  `validate_lineage(mode="synthesis", pattern=None)` and
  `validate_header(mode="synthesis", pattern=None)` in the
  correct order; ordering of header validator vs final
  lineage validator (§12.5).
- `test_no_io.py` — `grade_drafts()` and the synthesis core
  invocation under `socket`, `pymongo`, `open`, `requests`
  patched to raise; assertion: completes without touching any
  of them (LLM transports are mocked; the only network is
  the LLM transport).
- `test_failed_draft_filtering.py` — failed drafts excluded
  from grading and synthesis source set; SC10 enforcement.
- `test_two_draft_mode.py` — degraded inputs with two drafts;
  SC1 / I6 enforcement; replacement disabled.

### 18.2 Stage contract tests

- `StageDefinition` lookup returns the registered instance
  under `cv.grade_select_synthesize`; `prerequisites =
  ("cv.draft_assembly",)` (barrier on all enqueued instances);
  `produces_fields = ("cv_assembly.grades", "cv_assembly.winner",
  "cv_assembly.synthesis", "cv_assembly.assembled_at",
  "lifecycle:cv_assembled")`; `task_type ==
  "cv.grade_select_synthesize"`; `lane == "cv_assembly"`;
  `required_for_cv_assembled` is set.
- Idempotency-key composition matches §7.4.
- Cache-key composition matches §16.6.

### 18.3 Grading contract tests

- Construction from realistic upstream artifacts.
- `weights_used` resolution (default vs role-family override)
  matches `pattern_label` of the **winner**.
- Composite score determinism across two runs at fixed inputs.
- Rubric scores match `rubric_weights.json` checked-in values
  on the §18.13 fixtures.

### 18.4 Pairwise contract tests

- Pair input order is lexicographic by `draft_id`.
- Pair output is parsed and validated; abstention propagates
  to the aggregate.
- Aggregate Borda matches the deterministic transformation
  rule.
- Tied aggregate falls through to §11.4.1 ladder.
- Cache hit/miss semantics under §16.6.

### 18.5 Synthesis algorithm tests

- Per-rule fixture per §10.3 enum.
- Per-rollback fixture per `rollback_reason`.
- Determinism: two runs produce byte-identical
  `final_cv_struct`, `promoted_fragments[]`,
  `rolled_back_attempts[]` at fixed
  `merge_algorithm_version`, `RUBRIC_WEIGHTS_VERSION`,
  `SYNTHESIS_THRESHOLDS_VERSION`, drafts payload.
- Improvement gate: synthesis with
  `composite_delta < epsilon_improve` rolls back to winner.
- Cross-pattern compat: R003 with incompatible `pattern_label`
  pair is filtered before ordering.
- I6 (replacement disabled in two-draft mode).
- I17 (unit-class preservation under R001 / R005).

### 18.6 Validator-consumption tests

- Calls happen in the correct order (§12.1).
- `mode="synthesis"` accepts cross-pattern bullets.
- `failed` validator status leads to rollback; if all
  rolled-back, synthesis degrades to winner-verbatim.
- `repair_attempted` propagates correctly into the persisted
  reports.

### 18.7 Degraded-path tests

- Grader unavailable → `deterministic_only_mode=true`;
  composite recomputed; ladder fires on tie.
- Pairwise grader unavailable when `mode=hybrid` and tied →
  ladder fires; `pairwise_unreachable=true` recorded.
- Synthesis disabled flag → `synthesis.degraded=true`,
  `degradation_reason=synthesis_disabled`.
- Two-draft mode at claim → grading + synthesis still run.

### 18.8 Trace emission tests

Using a `FakeTracer`:

- stage span emitted with §17.4 + §17.5 metadata keys;
- substep spans (§17.2) emitted in correct nesting;
- events from §17.3 emitted with required metadata;
- forbidden keys do not leak (grep assertion on serialized
  payload — no full `cv_text`, no full `cv_struct`, no full
  `evidence_lineage`, no full debug body, no full LLM
  responses).

### 18.9 Persistence tests

- Persisted `GradeDoc[]`, `winner`, `SynthesisDoc` match the
  §9 schemas.
- Compact projection retains only counts and previews (not
  full `evidence_lineage`).
- `cv_assembly.stage_states.cv.grade_select_synthesize.trace_ref`
  is populated.
- `cv_assembly_stage_runs` has one row with §16.4 fields.
- Persistence is transactional: partial state never persists.

### 18.10 Downstream compatibility tests with 4.3.6

- Given a fixture `SynthesisDoc`, the 4.3.6 publisher's
  rendering input constructs without `KeyError` on any
  required field.
- Compatibility projection (4.3.7 §10) consumes
  `winner.composite_score`, `winner.dimensions.*` rationales,
  and `synthesis.debug_context.reasoning_summary` without
  drift.

### 18.11 Downstream compatibility tests with 4.3.7

- `DossierGenerator` consumes
  `synthesis.evidence_lineage.bullet_lineage[]`, the winner
  `GradeDoc.dimensions.*` rationales, and
  `synthesis.cover_letter` (when present) without drift.
- Section-by-section health flags reflect rolled-back
  synthesis attempts when relevant.

### 18.12 Determinism tests

- Two consecutive runs over identical inputs produce byte-
  identical `final_cv_struct`, `promoted_fragments[]`,
  `rolled_back_attempts[]`, and deterministic rubric scores.
- LLM-dependent surfaces (persuasiveness score, pairwise
  preferences, cover-letter text) are bounded by the SC2
  ±0.05 tolerance.
- `rubric_pass_signature` and `union_evidence_map_ref
  .union_signature` are byte-stable across runs.

### 18.13 Regression corpus

`data/eval/validation/cv_assembly_4_3_5_grade_synth/`:

- `cases/<job_id>/input/` — three persisted `DraftDoc`s,
  the `HeaderBlueprintDoc`, the `PatternSelectionDoc` (3
  patterns), all five `presentation_contract` subdocuments,
  classification, jd_facts, stakeholder_surface,
  pain_point_intelligence, master-CV snapshot.
- `cases/<job_id>/expected/grades.json` — expected per-
  dimension deterministic scores per draft (byte-equal asserted
  on the deterministic dimensions; ±0.05 tolerance on
  persuasiveness).
- `cases/<job_id>/expected/winner.json` — expected winner id
  and `winner_selection_method`.
- `cases/<job_id>/expected/synthesis.json` — expected
  `final_cv_struct`, `promoted_fragments[]`, and
  `rolled_back_attempts[]` (byte-equal at fixed
  `merge_algorithm_version=1.0.0`).
- `cases/<job_id>/expected/validator_report.json` — expected
  `EvidenceLineageValidatorReport` for the synthesis
  (byte-equal on `determinism_hash`).
- `cases/<job_id>/expected/header_validator_report.json` —
  expected `HeaderValidatorReport` for the synthesis.
- `cases/<job_id>/expected/cover_letter_summary.json` —
  expected counts (length, validator_status; full text not
  asserted byte-equal due to LLM nondeterminism).
- `cases/<job_id>/reviewer_sheet.md` — reviewer-facing
  acceptance sheet.

Minimum 20 cases, mirroring the 4.3.4 §20.13 distribution
plus 4.3.5-specific adversarial cases:

- three drafts with clear rubric separation (no tie);
- three drafts with ε-tie requiring pairwise (when
  `mode=hybrid`);
- three drafts where synthesis adds measurable lift on
  multiple sections (R001 + R002 + R003 in combination);
- three drafts where synthesis lifts only one section but
  passes `epsilon_improve`;
- three drafts where synthesis degrades and rolls back
  (`degradation_reason=no_improvement`);
- two-draft mode (`degraded_mode=true`) with R001 disabled
  per I6;
- adversarial: high-persuasiveness / low-truth draft (must
  lose on Truth weight; SC10 surface);
- adversarial: cross-pattern incompatible pair (R003 must be
  filtered);
- adversarial: synthesis would introduce a forbidden phrase
  via R001 (rollback expected);
- adversarial: synthesis would overflow `cv_shape_expectations
  .counts` via R002 (rollback expected);
- adversarial: synthesis would exceed AI band via R001 with
  paraphrased band claim (rollback expected; band climbing
  forbidden by §10.3.1 preconditions, drift detection here);
- one case with `pain_point_intelligence.status=unresolved`
  forcing Coverage redistribution;
- one case with `stakeholder_surface.status=inferred_only`
  forcing reduced evaluator coverage;
- one case with one persisted draft `partial`
  (`repair_attempted` upstream).

### 18.14 Eval metrics

Reviewer rubric, recorded in `reports/`:

- **Deterministic rubric reproducibility** (target = 1.00
  byte-level on deterministic dimensions) — SC2.
- **Composite score reproducibility** (target ≥ 0.99 within
  ±0.05 across two runs; LLM tolerance) — SC2.
- **Winner selection agreement with reviewer label** (target
  ≥ 0.90).
- **Synthesis improvement rate** (report; no hard target;
  used to tune `epsilon_improve`).
- **Synthesis rollback rate** (report; monitor; gate at <
  0.30 over 20+ cases per §10.4 calibration spec).
- **Truth weight dominance test** (adversarial case: target =
  1.00 — high-persuasiveness / low-truth must not win).
- **Pattern-compat correctness** (target = 1.00 — no
  forbidden cross-pattern fills appear).
- **Cover-letter validator pass rate** (target ≥ 0.95).
- **Reviewer usefulness on winner** (target ≥ 0.85) — SC14.
- **Reviewer usefulness on synthesis** (target ≥ 0.80) —
  SC14.
- **Determinism rate** (target = 1.00 byte-equal at fixed
  versions) — SC2.
- **Stage latency p95** (report only; target < 60 s on canary
  model with `mode=hybrid`).

### 18.15 Regression gates

Block rollout if:

- deterministic reproducibility regresses (drops below 1.00),
- truth weight dominance test fails on the adversarial case,
- winner selection agreement drops more than 5 points,
- synthesis rollback rate exceeds 30% across the corpus
  (indicates the merge algorithm is too aggressive),
- pattern-compat correctness < 1.00,
- cover-letter validator pass rate drops more than 5 points,
- determinism rate < 1.00,
- reviewer usefulness drops more than 5 points (winner or
  synthesis),
- any change to `rubric_weights.json` or
  `synthesis_thresholds.json` lands without a corresponding
  semver bump and a green corpus run.

### 18.16 Live smoke tests

- `scripts/smoke_grade_synthesis.py` — loads `.env` from
  Python, fetches one job by `_id` with three persisted
  drafts, runs the stage locally against live LLM, validates
  outputs, prints heartbeat every 15 s.

## 19. VPS End-To-End Validation Plan

Full discipline from
`docs/current/operational-development-manual.md` applies. This
section is the live-run chain.

### 19.1 Local prerequisite tests before touching VPS

- `pytest -k "grade_select_synthesize"` clean.
- `pytest tests/unit/cv_assembly/test_synthesis_rule_enum.py
  tests/unit/cv_assembly/test_synthesis_ordering.py
  tests/unit/cv_assembly/test_synthesis_rollback.py
  tests/unit/cv_assembly/test_validator_consumption.py
  tests/unit/cv_assembly/test_merge_algorithm_versioning.py`
  clean.
- `python -m scripts.cv_assembly_dry_run --stage
  grade_select_synthesize --job <level2_id> --mock-llm` clean.
- Langfuse sanitizer test green.
- 4.3.2 `validate_header` test suite green.
- 4.3.4 `validate_lineage` test suite green.
- 4.3.4 §20 test suite green (we depend on persisted drafts).
- `rubric_weights.json` and `synthesis_thresholds.json`
  parse cleanly with the active versions.

### 19.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path;
- verify the deployed `stage_registry.py` contains
  `cv.grade_select_synthesize`:
  `grep -n "cv.grade_select_synthesize"
  /root/scout-cron/src/cv_assembly/stage_registry.py`;
  `grep -n "CV_ASSEMBLY_GRADE_SELECT_SYNTHESIZE_ENABLED"
  /root/scout-cron/src/cv_assembly/config_flags.py`;
- verify
  `/root/scout-cron/src/cv_assembly/grading/synthesis_versions.py`
  exposes `ACTIVE_MERGE_ALGORITHM_VERSION` and that it
  matches the local active version;
- verify
  `/root/scout-cron/src/cv_assembly/grading/pattern_compat.py`
  exposes `PATTERN_COMPAT_TABLE`;
- verify
  `/root/scout-cron/data/eval/cv_assembly/rubric_weights.json`
  and `synthesis_thresholds.json` exist and parse;
- verify
  `/root/scout-cron/src/cv_assembly/validators/evidence_lineage_validator.py`
  exposes `validate_lineage` (4.3.4); same for
  `header_validator.py` (4.3.2);
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys;
  print(sys.executable)"`;
- deployment is file-synced; do not `git status`.

### 19.3 Target job selection

- Pick a real `cv_assembling` `level-2` job with:
  - `cv_assembly.draft_assembly_summary.status ∈
    {completed, partial, degraded}`,
  - `cv_assembly.draft_assembly_summary.drafts_persisted_count
    ≥ 2`,
  - all upstream `cv_assembly.*` artifacts present (header
    blueprint, pattern selection),
  - all five `presentation_contract` subdocuments present,
  - master-CV v2 inputs load cleanly.
- Prefer a mid-seniority IC or EM role with three persisted
  drafts and a meaningful score spread (so synthesis has
  fragments to consider).
- Record `_id`, `jd_checksum`,
  `draft_assembly_summary_checksum`, current
  `input_snapshot_id`.
- Optionally pick a second job with two persisted drafts to
  exercise the §8.4 / I6 two-draft path.

### 19.4 Upstream artifact verification

Before launching:

- verify `cv_assembly.drafts[]` has ≥ 2 entries with
  `status != "failed"` and clean validator reports;
- verify `cv_assembly.header_blueprint` is non-empty with
  pools and viability bands populated;
- verify `cv_assembly.pattern_selection.patterns[]` has
  entries for every persisted-draft `pattern_id`;
- verify `presentation_contract` subdocuments persisted;
- verify master-CV v2 loader returns no schema errors:
  `python -m src.cv_assembly.cli check_master_cv_v2
  --candidate $CANDIDATE_ID`;
- verify Langfuse session reachable.

If any verification fails, choose a different job — do not
mutate `work_items` or `level-2.cv_assembly.*` directly to
make verification pass. Re-run upstream stages via the
proper enqueue path:

- `scripts/recompute_snapshot_id.py --job <_id>`,
- `scripts/enqueue_stage.py --stage cv.draft_assembly --job
  <_id> --pattern_id {1,2,3}` (re-runs 4.3.4).

### 19.5 Single-stage run path (fast path) — preferred

A wrapper in `/tmp/run_grade_synthesis_<job>.py`:

- `from dotenv import load_dotenv;
  load_dotenv("/root/scout-cron/.env")`,
- reads `MONGODB_URI`,
- builds `StageContext` via the worker-compatible factory
  (`build_cv_assembly_stage_context_for_job`),
- runs `GradeSelectSynthesizeStage().run(ctx)` directly,
- prints a heartbeat line every 15 s during LLM work with:
  wall clock, elapsed, last substep (`preflight`,
  `rubric_first`, `persuasiveness_llm`, `pairwise`,
  `winner_select`, `merge`, `header_validate`,
  `lineage_validate`, `repair`, `cover_letter`, `persist`),
  Codex/LLM PID, last LLM stdout/stderr tail.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_grade_synthesis_<job>.py \
  > /tmp/grade_synthesis_<job>.log 2>&1 &
```

### 19.6 Full-chain path (fallback)

If the fast path is blocked by `StageContext` construction
drift or if you need to validate the fan-in behavior end-to-
end:

- enqueue the `cv.grade_select_synthesize` work item via
  `scripts/enqueue_stage.py --stage cv.grade_select_synthesize
  --job <_id>`,
- start the cv_assembly worker with
  `CV_ASSEMBLY_STAGE_ALLOWLIST="cv.grade_select_synthesize"`,
- same `.venv`, `python -u`, Python-side `.env`, `MONGODB_URI`
  discipline,
- same operator heartbeat from the worker's structured
  logger.

When a 4.3.4 + 4.3.5 chain run is needed (e.g., after
regenerating drafts):

- enqueue three `cv.draft_assembly` work items first with
  `--block-until-complete`,
- then enqueue the single `cv.grade_select_synthesize` work
  item.

### 19.7 Required launcher behavior

- `.venv` activated (absolute path to `.venv/bin/python`),
- `python -u` unbuffered,
- `.env` loaded from Python, not `source .env`,
- `MONGODB_URI` present,
- inner LLM PID and first 128 chars of stdout / stderr logged
  on every heartbeat,
- isolated workdir
  `/tmp/cv-grade-synthesis-<job>/` for any inner LLM
  subprocess (per operational manual §"Failure 9").

### 19.8 Heartbeat requirements

- stage-level heartbeat every 15-30 s from the wrapper;
- lease heartbeat every 60 s by the worker;
- silence > 90 s = stuck-run flag.

### 19.9 Expected Mongo writes

On success:

- `cv_assembly.grades` collection: one doc per persisted
  draft, keyed by `(level2_id, input_snapshot_id, draft_id,
  rubric_weights_version)`;
- `level-2.cv_assembly.grades[]` populated;
- `level-2.cv_assembly.winner` populated;
- `level-2.cv_assembly.synthesis` populated (full doc inline,
  per §16.3);
- `level-2.cv_assembly.assembled_at` set;
- `level-2.lifecycle = "cv_assembled"`;
- `level-2.cv_assembly.stage_states.cv.grade_select_synthesize`
  → `status=completed | partial | degraded`,
  `attempt_count`, `lease_owner` cleared, `trace_id`,
  `trace_url`, `validator_report.status`,
  `header_validator_report.status`,
  `winner_selection_method`,
  `synthesis_degraded`, `synthesis_degradation_reason?`,
  `cover_letter_status`;
- `cv_assembly_stage_runs`: one row per §16.4;
- `work_items`: this row `status=completed`.

Subsequent: 4.3 sweeper enqueues `cv.publish.render.cv` and
`cv.publish.render.dossier` per 4.3.6 §7.1.

### 19.10 Expected Langfuse traces

In the same trace (`scout.cv.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- one `scout.cv_assembly.grading_synthesis` stage span with
  §17.4 / §17.5 metadata,
- substep spans listed in §17.2 (only those that fired),
- events from §17.3 (only those that fired),
- canonical lifecycle events from the 4.3 umbrella.

A correctly-running job produces:

- 1 `winner_selected` event,
- N `synthesis_rule_applied` events (N small; 0–10 typical),
- M `synthesis_rule_rolled_back` events (M small; ≤ N),
- 0 `validator_failure` events,
- 0–1 `degraded_synthesis` event,
- 0 `pairwise_unreachable` event.

### 19.11 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/grade_synthesis_<job>.log`,
- inspect launcher PID,
- inspect Mongo:
  `level-2.cv_assembly.stage_states.cv.grade_select_synthesize.lease_expires_at`,
- if lease is expiring and no progress, kill the launcher;
  wait for the prior PID to be confirmed gone before
  restarting.

Silence is not progress.

### 19.12 Acceptance criteria

- log ends with `GRADE_SYNTHESIS_RUN_OK job=<id>
  winner=<draft_id> synthesis_degraded=<bool>
  trace=<url>`;
- Mongo writes match §19.9;
- Langfuse traces match §19.10;
- `SynthesisDoc.validator_report.status ∈ {pass,
  repair_attempted}`;
- `SynthesisDoc.header_validator_report.status ∈ {pass,
  repair_attempted}`;
- `synthesis.composite_score - winner.composite_score ≥
  ε_improve` when `synthesis.degraded == false`;
- `synthesis.final_cv_struct.header.title_string ==
  header_blueprint.identity.chosen_title` exactly;
- spot-check: every `synthesis.promoted_fragments[]` entry's
  `source_lineage_ref` resolves in the corresponding source
  draft's `evidence_lineage`; every `rule_id` is in the
  enum; every `rolled_back_attempts[]` entry has a
  `rollback_reason`;
- `synthesis.cover_letter` is non-null with
  `validator_status=pass` (or null with a recorded
  `cover_letter_warning` event);
- two-draft run (when applicable) returns
  `synthesis.degraded ∈ {true, false}` with R001/R005
  disabled per I6.

### 19.13 Artifact / log / report capture

Create `reports/grading-synthesis/<job_id>/` containing:

- `run.log` — full stdout/stderr,
- `grades.json` — emitted `GradeDoc[]`,
- `winner.json` — emitted winner,
- `synthesis.json` — emitted `SynthesisDoc` (compact
  projection),
- `synthesis_full.json` — full `SynthesisDoc` including
  `debug_context`,
- `validator_report.json` — synthesis lineage validator
  output,
- `header_validator_report.json` — synthesis header
  validator output,
- `cover_letter.txt` — cover-letter text (when present),
- `trace_url.txt` — Langfuse URL,
- `stage_run.json` — `cv_assembly_stage_runs` row,
- `mongo_writes.md` — human summary of §19.9 checks,
- `acceptance.md` — pass/fail list for §19.12.

## 20. Open-Questions Triage

| Question | Triage | Resolution-or-recommendation |
|---|---|---|
| Should synthesis accept **cross-pattern** section replacements (not just unfilled-slot fills)? | must-resolve | **(resolved)** §10.3.3 + §10.3.7 — v1: cross-pattern **fills** (R003) are permitted only on unfilled slots and only when the pattern-compat table marks the pair `compat`. Cross-pattern **replacements** are forbidden in v1. Same-pattern replacements (R001) and same-pattern header-pool substitutions (R005) cover the replace surface. The pattern-compat table is declared in code (`pattern_compat.py`); changes require a `merge_algorithm_version` bump. Revisit cross-pattern replacement only if eval shows recurring R001/R002 misses where a runner-up's clearly-better fragment lives in an incompatible pattern. |
| Should synthesis try a **multi-round** merge (apply R001/R002/R003 across multiple rounds)? | safe-to-defer | v1: single-round, deterministic order (§10.1 step 4). Multi-round adds order-dependency complications (an early R002 fill changes whether a later R001 replacement makes sense) and complicates determinism. Revisit only if eval shows recurring cases where one round's promotions block the next round's eligibility (for example, an R002 fill that surfaces a dimension imbalance which a second-round R001 would correct). |
| Should rubric weights be per-role-family (not global)? | must-resolve | **(resolved)** §9.1 — yes; weights are versioned in `data/eval/cv_assembly/rubric_weights.json` with `default_weights` plus `role_family_overrides` keyed by the **winner's** `pattern_label`. This rewards each draft against its own pattern's posture. Schema bump on any change. The default weights are 30/20/20/30 (Truth/Pattern Fidelity/Coverage/Persuasiveness) and individual overrides clamp Truth to ≥ 25%. |
| Should `epsilon_tied`, `epsilon_replace`, `epsilon_improve` be per-role-family? | must-resolve | **(resolved)** §10.4 — yes; thresholds are versioned in `data/eval/cv_assembly/synthesis_thresholds.json` with `defaults` plus `role_family_overrides` keyed by the **winner's** `pattern_label`. Calibration method is documented in the config (corpus + cadence + decision owner). |
| Should the LLM tie-breaker / pairwise grader see `pattern_label` and `pattern_signature`? | safe-to-defer | **(resolved)** §11.5.2 — yes, `pattern_label` is included in the per-pair input as transparency context. `pattern_signature` is not included (it is a content-addressed hash of pattern internals — useful for the determinism contract, not for the LLM's reasoning). Experiments may ablate via a flagged variant prompt. |
| Should the grader also consume cover letter / dossier drafts? | safe-to-defer | v1: CV only. Cover letters are generated **after** synthesis (§10.6), never per draft, so the grader has nothing to grade on the cover-letter surface. Dossiers are produced from the synthesis output (4.3.7), not from drafts, so they do not enter grading. Revisit if reviewer feedback shows the winner-CV is consistently mis-aligned with the resulting cover-letter quality. |
| Should the optional polish pass (§11.6) be enabled in v1? | safe-to-defer | v1: `CV_ASSEMBLY_SYNTHESIS_POLISH_ENABLED=false`. The polish pass is gated off until the eval corpus shows a meaningful reviewer-usefulness lift from grammar/punctuation polish that the deterministic merge does not capture. When enabled, the polish prompt is bounded and the post-polish lineage validator re-runs (§11.6); any new violation discards the polish. |
| Should winners from `swapped_default` patterns be allowed to win? | safe-to-defer | **(resolved)** §11.4 + §13 I15 — yes; `swapped_default` patterns are eligible to win if they score highest. The 4.3.4 `swapped_default` truthfulness regime (4.3.4 §I13) is already applied at draft time, so the resulting `DraftDoc` is already conservative-by-construction. The rubric Truth dimension surfaces this conservatism as fewer repairs and zero band climbs, which is rewarded; no special swap-aware grader logic is needed. |
| Should a non-winning draft be selectable by an operator post-synthesis? | safe-to-defer | v1: no human-pick override. The CV Editor (4.4) owns this surface. 4.3.5 emits a single deterministic winner + synthesis; 4.4 is where an operator may override. |
| Should synthesis re-run 4.3.4 §11 number-resolution on promoted bullet text? | safe-to-defer | v1: no. Promoted fragments inherit their source bullet's `number_resolution_log[]` exactly; the `mode="synthesis"` lineage validator re-checks numeric tokens against the source pattern's evidence map but does not re-tokenize. Revisit if eval shows promoted bullets drift their numeric source decisions when surrounding context changes (unlikely; numeric tokens are bullet-local). |

## 21. Primary Source Surfaces

- `plans/iteration-4.3-candidate-evidence-assembly-grading-and-publishing.md`
- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`
- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
- `plans/iteration-4.3.3-cv-pattern-selection-and-evidence-mapping.md`
- `plans/iteration-4.3.4-multi-draft-cv-assembly.md`
- `plans/iteration-4.3.6-publisher-renderer-and-remote-delivery-integration.md`
- `plans/iteration-4.3.7-dossier-and-mongodb-state-contract.md`
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `docs/current/missing.md`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md` (Part 4 — Scoring; Part 5 — Quality Gates)
- `src/layer6_v2/grader.py`
- `src/layer6_v2/improver.py`
- `src/layer6_v2/cover_letter_generator.py`
- `src/layer6_v2/prompts/grading_rubric.py`
- `src/layer6_v2/cv_loader.py`
- `src/cv_assembly/validators/header_validator.py` (4.3.2 — consumed)
- `src/cv_assembly/validators/evidence_lineage_validator.py` (4.3.4 — consumed)
- `src/cv_assembly/models.py`
- `src/cv_assembly/stage_registry.py`
- `src/cv_assembly/sweepers.py`
- `src/cv_assembly/tracing.py`
- `src/common/unified_llm.py`
- `src/common/llm_config.py`
- `src/preenrich/blueprint_models.py` (canonical enums)

## 22. Implementation Targets

- `src/cv_assembly/stages/grade_select_synthesize.py` (new) —
  work-item entrypoint; runs prereq, builds
  `SynthesisContext`, runs grading harness, selects winner,
  drives synthesis, runs validators, generates cover letter,
  persists. One entrypoint:
  `GradeSelectSynthesizeStage.run(ctx) -> StageOutput`.
- `src/cv_assembly/grading/__init__.py` (new).
- `src/cv_assembly/grading/rubric_deterministic.py` (new) —
  §11.2 truth/fidelity/coverage scorers. Pure; no I/O.
- `src/cv_assembly/grading/persuasiveness_llm.py` (new) —
  §11.3 LLM persuasiveness scorer; abstention handling;
  fallback escalation.
- `src/cv_assembly/grading/pairwise_grader.py` (new) —
  §11.5 pairwise grader; pair ordering; aggregate Borda;
  cache integration.
- `src/cv_assembly/grading/composite.py` (new) — weighted-
  sum composer; tie detector; deterministic ladder.
- `src/cv_assembly/grading/rubric_weights.py` (new) — config
  loader; invariants; role-family override resolution.
- `src/cv_assembly/grading/synthesis.py` (new) — synthesis
  driver; orchestrates §10.1.
- `src/cv_assembly/grading/synthesis_rules.py` (new) —
  `SynthesisRule` enum; per-rule precondition checkers; per-
  rule appliers. Pure; no I/O.
- `src/cv_assembly/grading/synthesis_versions.py` (new) —
  `MERGE_ALGORITHM_VERSIONS` registry;
  `ACTIVE_MERGE_ALGORITHM_VERSION`.
- `src/cv_assembly/grading/synthesis_thresholds.py` (new) —
  config loader; invariants; role-family override.
- `src/cv_assembly/grading/synthesis_context.py` (new) —
  `SynthesisContext` dataclass;
  `build_synthesis_context()` pure function; union evidence
  map composition with byte-stable signature.
- `src/cv_assembly/grading/pattern_compat.py` (new) —
  `PATTERN_COMPAT_TABLE_V1`; lookup helper.
- `src/cv_assembly/prompts/grading_persuasiveness.py` (new) —
  LLM persuasiveness prompt template.
- `src/cv_assembly/prompts/grading_pairwise.py` (new) —
  pairwise prompt template.
- `src/cv_assembly/models.py` — add `GradeDoc`,
  `GradeDimensionDoc`, `GradeDebug`, `SynthesisDoc`,
  `SynthesisDebug`, `PromotedFragmentDoc`,
  `RolledBackAttemptDoc`, `UnionEvidenceMap`,
  `RubricWeightsConfig`, `SynthesisThresholdsConfig`,
  `SynthesisRule` enum, `RankingTier` enum,
  `WinnerSelectionMethod` enum, `GraderMode` enum,
  `RollbackReason` enum, `DegradationReason` enum,
  `GRADE_SCHEMA_VERSION`, `SYNTHESIS_SCHEMA_VERSION`
  constants.
- `src/cv_assembly/stage_registry.py` — register
  `cv.grade_select_synthesize`; barrier rule on all enqueued
  `cv.draft_assembly` work items;
  `required_for_cv_assembled = true`.
- `src/cv_assembly/dag.py` — barrier edge `cv.draft_assembly →
  cv.grade_select_synthesize`; outbound edge to
  `cv.publish.render.*` (4.3.6).
- `src/cv_assembly/sweepers.py` — `cv_assembled` finalizer
  CAS; 4.3.6 enqueue trigger when `cv_assembled` set.
- `src/cv_assembly/tracing.py` — register stage span and
  substep spans (§17), enforce `_sanitize_langfuse_payload`
  on previews, cap `synthesis_rule_applied` /
  `synthesis_rule_rolled_back` events at 50 with overflow
  event.
- `src/cv_assembly/config_flags.py` —
  `CV_ASSEMBLY_GRADE_SELECT_SYNTHESIZE_ENABLED`,
  `CV_ASSEMBLY_SYNTHESIS_ENABLED`,
  `CV_ASSEMBLY_GRADER_MODE`,
  `CV_ASSEMBLY_GRADER_TIEBREAKER_ENABLED`,
  `CV_ASSEMBLY_SYNTHESIS_POLISH_ENABLED`,
  `CV_ASSEMBLY_GRADER_DETERMINISTIC_ONLY`.
- `data/eval/cv_assembly/rubric_weights.json` (new) —
  default + role-family overrides; sub-component weights;
  `truth_penalty_coefficients`.
- `data/eval/cv_assembly/synthesis_thresholds.json` (new) —
  default + role-family overrides; calibration method
  documentation.
- `scripts/benchmark_grade_synthesis_4_3_5.py` (new) — eval
  harness over §18.13 corpus.
- `scripts/smoke_grade_synthesis.py` (new) — single-job live
  smoke per §18.16.
- `scripts/vps_run_grade_synthesis.py` (new) — VPS wrapper
  template per §19.5.
- `data/eval/validation/cv_assembly_4_3_5_grade_synth/` (new)
  — 20-case corpus per §18.13.
- `tests/unit/cv_assembly/` — test files per §18.1, §18.4–
  §18.12.
- `docs/current/architecture.md` — add §"Iteration 4.3.5
  Grading And Synthesis" subsection covering the canonical
  span, the rubric weights config, the synthesis thresholds
  config, the `merge_algorithm_version` registry, and the
  pattern-compatibility table.
- `docs/current/missing.md` — strike out the §6350–6359
  4.3.5 gap entries and reference this plan as the
  resolution.
- `docs/current/cv-generation-guide.md` (Part 4) — reference
  the rubric weights config as the canonical scoring
  surface.
