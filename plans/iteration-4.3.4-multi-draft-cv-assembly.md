# Iteration 4.3.4 Plan: Multi-Draft CV Assembly

## 1. Executive Summary

With the header blueprint (4.3.2) freezing identity and the pattern
selection (4.3.3) freezing structure, evidence picks, and per-pattern
header picks, 4.3.4 is the candidate-aware stage where the three CV
drafts are actually written. Each draft is a pattern-scoped invocation
of the existing Layer 6 V2 pipeline — loader → variant selection →
per-role generation → stitching → blueprint-first header prose → ATS
validation — followed by two deterministic gates (the shared 4.3.2
header validator and a new evidence-lineage validator) before persist.
The three drafts run in parallel as separate `cv.draft_assembly` work
items, one per `pattern_id`.

4.3.4 does not rewrite Layer 6 V2 and does not own a parallel control
plane. It composes on top of Layer 6 V2 through three narrow adapter
seams declared in the source plan and consumed verbatim from 4.3.3:

- a `PatternContext` parameter that threads pattern-scoped inputs
  through the orchestrator;
- a deterministic `PatternContext → PatternBias` adapter (§10) that
  drives `VariantSelector` scoring without rewriting it;
- a blueprint-first mode on `HeaderGenerator` (defined in 4.3.2 and
  consumed here).

The output of this stage is **not yet a winner**. It is up to three
persisted `DraftDoc`s — each one already lineage-checked against
master-CV evidence and already header-validated against the 4.3.2
shared validator — that the grader/synthesis stage (4.3.5) audits and
merges. 4.3.4 is the seam where free-form Layer 6 V2 prose stops being
free-form: every realized claim must be traceable to 4.3.3 picks and
master-CV bands, and every numeric token must be either a master-CV
copy or a whitelisted band rendering.

Operational discipline is inherited from the 4.3 umbrella:

- **Mongo is the control plane.** `work_items`,
  `cv_assembly.stage_states`, `cv_assembly_stage_runs`, and
  `cv_assembly_job_runs` drive execution. There is no shadow runner.
- **Langfuse is the observability sink.** Stage span
  `scout.cv_assembly.draft_assembly` with bounded per-draft subspans
  (§18) carries metadata-first payloads. Full draft bodies stay in
  Mongo.
- **VPS validation** (§21) runs the stage end-to-end on a real
  `cv_assembling` `level-2` job before default-on rollout.

## 2. Mission

Produce up to three candidate-aware CV drafts per job — one per
selected pattern — through the existing Layer 6 V2 pipeline, with
pattern-scoped inputs that keep all prose bound to master-CV truth,
no cross-draft identity drift, no fabricated metrics, and a per-draft
deterministic lineage trail that the grader (4.3.5) can audit
byte-deterministically.

## 3. Objectives

- **O1.** Define a `cv.draft_assembly` stage that consumes the persisted
  `cv_assembly.pattern_selection` verbatim (no re-derivation), fans
  out one work item per `pattern_id` (1–3), and writes one
  `DraftDoc` per pattern under `cv_assembly.drafts[]`.
- **O2.** Ship a `PatternContext` adapter (§10.1) that wraps every
  pattern-scoped input Layer 6 V2 needs — `PatternDoc` (verbatim),
  `HeaderBlueprintDoc`, `PresentationContractDoc`, `CandidateData`
  (master-CV loader v2), tracer, checksums — and threads it through
  the orchestrator without changing legacy single-pass behavior.
- **O3.** Ship a deterministic `PatternContext → PatternBias` adapter
  (§10.2) that projects `dimension_weights_override`,
  per-role/per-achievement allowlists, and forbidden-category
  derivations into `VariantSelector`-readable form, with a fixed
  formula and tie-break rules (no LLM in the projection).
- **O4.** Define the per-bullet `DraftDoc` schema (§9) so each bullet
  carries `(role_id, achievement_id, variant_id?, proof_category,
  dimension, bands, source_fragment_ref)`, and so each draft persists
  the Layer 6 V2 sub-outputs (QA, ATS, tailoring, keyword placement,
  self-grade, improver) for downstream audit — but never as the
  authoritative grade.
- **O5.** Ship a shared `evidence_lineage_validator` library (§12)
  with explicit module path, signature, report shape, allowed
  deterministic repair actions, one-pass bound, no-LLM-in-repair
  rule, and byte-determinism guarantees asserted by eval. Modes:
  `"draft"` (used here, before persist) and `"synthesis"` (used by
  4.3.5).
- **O6.** Ship an explicit header-validator consumption contract
  (§13): every draft header struct must call `validate_header(...,
  mode="draft", pattern=current_pattern)` from
  `src/cv_assembly/validators/header_validator.py` (4.3.2 §11.2)
  before persist; failures are repaired through the validator's
  deterministic repair surface or the draft is marked `failed`.
- **O7.** Ship a deterministic number-resolution policy (§11) for
  bullet text: regex tokenization, recognized units, source-of-truth
  hierarchy (master-CV source fragment → structured metric field →
  whitelisted metric-band rendering → strip), failure mode when no
  source exists, and interaction with 4.2.6 truth rules.
- **O8.** Define explicit fail-open / fail-closed rules (§15) bounded
  to two-draft degraded mode (when only two patterns are valid),
  one-draft `cv_assembly.status=degraded` minima, and zero-draft
  `cv_assembly.status=failed` deadletter — never best-effort
  publishing.
- **O9.** Define explicit downstream-consumer contracts (§17) so
  4.3.5 reads a fixed surface from 4.3.4 and 4.3.6 reads only what
  4.3.5 promotes — 4.3.6 must not read 4.3.4 directly.
- **O10.** Emit Langfuse traces (§18) under a single canonical stage
  span with bounded per-draft subspans, required metadata, forbidden
  content list, and operator debug checklist; trace refs flow into
  Mongo so an operator reaches the trace from `level-2` in one
  click.
- **O11.** Validate end-to-end on the VPS (§21) on a real
  `cv_assembling` job, with stage-only fast path and prerequisite
  verification, before default-on rollout.

## 4. Success Criteria

4.3.4 is done when, for a representative 15-case eval corpus (§20.6)
and a 50-job staging soak:

- **SC1.** Every `cv_assembling` job with `pattern_selection.status ∈
  {completed, partial}` and ≥ 2 valid patterns produces between two
  and three `DraftDoc`s with distinct `pattern_id`s. Three valid
  patterns ⇒ three drafts; exactly two valid patterns ⇒ two drafts
  and `cv_assembly.status=degraded`.
- **SC2.** Every persisted `DraftDoc` has `evidence_lineage_validator`
  status `pass` or `repair_attempted` (never `failed` at persist —
  failed drafts are not persisted with `cv_text`; they carry a
  `failure_record` for audit).
- **SC3.** Every persisted `DraftDoc` has a `header_validator` (4.3.2
  shared) status `pass` or `repair_attempted` against the pattern's
  picks.
- **SC4.** No persisted bullet, header element, summary line, key
  achievement, AI highlight, competency, or skill references an
  achievement, variant, project, or skill outside the pattern's
  `evidence_map` (asserted by §12 validator, byte-deterministic).
- **SC5.** No persisted bullet text contains a numeric token that
  fails the §11 number-resolution policy.
- **SC6.** No persisted draft contains a title outside
  `acceptable_titles`, an AI-band claim above
  `classification.ai_taxonomy.intensity`, or a leadership claim above
  the cited role's `seniority.managerial_level`.
- **SC7.** A failed draft never poisons a sibling draft: when
  pattern_2 fails, pattern_1 and pattern_3 (if valid) still
  complete and persist.
- **SC8.** When fewer than two drafts succeed, the job goes to
  `cv_assembly.status=failed` with a structured failure record per
  pattern; `cv.grade_select_synthesize` is **not** enqueued.
- **SC9.** Every `DraftDoc.pattern_signature` matches its source
  `PatternDoc.pattern_signature` (4.3.3 §12) verbatim.
- **SC10.** Langfuse stage span `scout.cv_assembly.draft_assembly` is
  emitted with §18.4 metadata; one click from the level-2 UI.
- **SC11.** The eval corpus passes 100% structural invariants and
  reviewer usefulness ≥ 0.75 per draft.
- **SC12.** VPS smoke (§21) completes on a real job with artifacts
  captured under `reports/draft-assembly/<job_id>/`.

## 5. Non-Goals

- Re-authoring the per-role generator, the stitcher, the grader, or
  the improver. Those Layer 6 V2 modules are preserved.
- Selecting *the* winning draft. Selection and synthesis are 4.3.5.
- Producing the synthesized best-version. That is 4.3.5.
- Generating cover letters in this stage (resolved in §22 — cover
  letters are produced for the winner only, in 4.3.5, after
  synthesis).
- Publishing or rendering. That is 4.3.6.
- Re-deriving `chosen_title`, `chosen_title_strategy`,
  `identity_tags[]`, `not_identity[]`, `forbidden_phrases[]`,
  `viability_bands.*`, or any 4.3.2-frozen field.
- Re-deriving any 4.3.3 pick: `header_picks`, `evidence_map.*`,
  `dimension_weights_override`, `proof_order_override[]`,
  `primary_document_goal_override`, `section_emphasis[]`. 4.3.4 is a
  **realizer**, not a picker.
- Growing pools, expanding allowlists, or adding achievements outside
  the pattern's `evidence_map`.
- Owning a parallel control plane, a hidden lineage judge, or a
  sidecar synthesis stage.
- Free-form web search, research transports, or cross-job reasoning.

## 6. Why This Stage Exists

4.3.2 froze identity and exposed bounded pools. 4.3.3 turned those
pools into three disciplined picks per job, with deterministic
evidence maps. 4.3.4 turns each pick into prose — without losing the
discipline upstream stages established. Without 4.3.4 as a candidate-
aware stage:

1. **Three parallel drafts must share one identity.** A free-form
   Layer 6 V2 invocation per pattern would re-derive identity per
   draft and risk title drift, tagline drift, and cross-draft
   incoherence for the same candidate on the same job. The
   `PatternContext` adapter and the 4.3.2 blueprint-first header mode
   prevent this.
2. **Pattern-scoped inputs must reach `VariantSelector` before
   stitching.** Today, `VariantSelector` reasons about JD + master-CV
   only. The 4.3 patterns add intentional emphasis (dimension
   weighting, allowlists, forbidden categories) that must enter the
   selection stage **before** scoring. Retrofitting after stitching
   produces "generically good" drafts instead of intentionally
   shaped ones.
3. **Evidence lineage must be deterministic.** A single Layer 6 V2
   draft today emits `cv_text` with no explicit map from each bullet
   back to a `(role_id, achievement_id, variant_id)` tuple. The
   grader and synthesis steps require that map. 4.3.4 emits it
   verbatim, and the §12 validator asserts it.
4. **Failed drafts must not poison siblings.** Putting each pattern
   in its own work item lets a transient LLM failure on draft 2
   leave drafts 1 and 3 intact, and lets the §12 validator reject
   draft 2 surgically without rolling back the job.
5. **Number resolution must be deterministic.** Layer 6 V2's free-
   form prose is the most common surface for fabricated metrics
   (e.g., "drove 40% YoY growth" with no source). 4.3.4 is the seam
   where every numeric token must be tied to a master-CV source or a
   whitelisted band rendering — enforced by §11 + §12.

The 4.3.4 stage exists so the truth boundary established by 4.3.1 →
4.3.2 → 4.3.3 survives prose realization.

## 7. Stage Boundary

### 7.1 DAG position

```
cv.pattern_selection
       └── fan-out: 1..3 cv.draft_assembly work items, one per pattern_id
              ├── pattern_1 → DraftDoc with draft_id="draft_pattern_1"
              ├── pattern_2 → DraftDoc with draft_id="draft_pattern_2"
              └── pattern_3 → DraftDoc with draft_id="draft_pattern_3"
       └── barrier: cv.grade_select_synthesize (4.3.5) consumes drafts[]
```

`cv.draft_assembly` is **not** a barrier itself; the barrier is at
4.3.5. Each `cv.draft_assembly` work item runs independently. 4.3.5
claims when all enqueued draft work items are in a terminal state
(completed | partial | failed) and ≥ 2 are non-failed; otherwise the
job goes to `cv_assembly.status=failed` per §15.3.

### 7.2 Inputs

Per draft, at claim time (read from `level-2`, all pinned to
`input_snapshot_id` from the work-item payload):

- `cv_assembly.header_blueprint` (full `HeaderBlueprintDoc`, 4.3.2) —
  shared across all drafts of the same job.
- `cv_assembly.pattern_selection.patterns[pattern_id]` — the single
  `PatternDoc` for this draft, including `header_picks`,
  `evidence_map.*`, `dimension_weights_override`,
  `proof_order_override[]`, `primary_document_goal_override`,
  `section_emphasis[]`, `audience_tilt`, `risks[]`, `pattern_label`,
  `pattern_signature`, `pattern_status`.
- `pre_enrichment.presentation_contract.*` (all five subdocuments;
  read-only; no re-derivation):
  - `document_expectations` (4.2.2),
  - `cv_shape_expectations` (4.2.2 — `counts`, `header_shape`,
    `ats_envelope`, `ai_section_policy`),
  - `ideal_candidate_presentation_model` (4.2.4 — `tone_profile`,
    `risk_flags`),
  - `experience_dimension_weights` (4.2.5 — `overall_weights` prior;
    pattern override authoritative for emphasis),
  - `truth_constrained_emphasis_rules` (4.2.6 —
    `forbidden_claim_patterns[]`, `omit_rules[]`, `downgrade_rules[]`,
    `section_rules.*`).
- `pre_enrichment.classification` (4.1.2) — `primary_role_category`,
  `seniority`, `tone_family`, `ai_taxonomy.intensity` band cap.
- `pre_enrichment.jd_facts` (4.1.1) — `top_keywords` for ATS keyword
  placement only; no re-derivation of strategy or proof.
- `pre_enrichment.stakeholder_surface` (4.2.1) — `evaluator_coverage_target`
  for `audience_tilt` projection; advisory.
- `pre_enrichment.pain_point_intelligence` (4.2.3) — read-only;
  consumed by Layer 6 V2 prompts as topical vocabulary.
- `pre_enrichment.research_enrichment.role_profile` — opportunistic;
  may be absent.
- Master-CV via loader v2 (4.3.1) — full `RoleData[]`,
  `RoleMetadata`, `ProjectMetadata`, taxonomies, `candidate_facts`,
  pinned to `master_cv_checksum`.

The work-item payload carries:

```text
payload {
  input_snapshot_id,                       # same across all drafts of this job
  master_cv_checksum,
  presentation_contract_checksum,
  header_blueprint_checksum,
  pattern_selection_checksum,
  jd_checksum,
  pattern_id,                              # 1, 2, or 3
  pattern_signature,                       # back-ref to PatternDoc.pattern_signature
  attempt_token,
  correlation_id,
  level2_id
}
```

`input_snapshot_id` is composed per the 4.3 umbrella (sha256 over
checksums + `PROMPT_VERSION` + `DRAFT_SCHEMA_VERSION`).

### 7.3 Output

Per draft, on success:

- `cv_assembly.drafts[<index>]` — one `DraftDoc` (§9), where
  `<index> = pattern_id - 1` so list slots are stable.
- `cv_assembly.stage_states.cv.draft_assembly.<pattern_id>` —
  `status`, `attempt_count`, `lease_owner` cleared, `trace_id`,
  `trace_url`, `validator_report.status`,
  `header_validator_report.status`.

Per job (rolled up after the last draft work item completes; computed
by the 4.3 sweeper, not by 4.3.4 itself):

- `cv_assembly.draft_assembly_summary` — `{drafts_persisted_count,
  drafts_failed_count, degraded_mode: bool, status:
  completed|partial|degraded|failed, trace_refs[]}`. The job-level
  rollup is the 4.3.5 claim signal; 4.3.4 does not emit it directly.

### 7.4 Work-item details

- `task_type = cv.draft_assembly`, `lane = cv_assembly`.
- `idempotency_key =
  cv.draft_assembly:<level2_id>:<input_snapshot_id>:<pattern_id>`.
- `max_attempts = 3` with the 4.3-umbrella `RETRY_BACKOFF_SECONDS`.
- `required_for_cv_assembled = true` *at the job-rollup level*: at
  least two drafts must complete; the 4.3.5 barrier asserts this.
- Prerequisite check at claim (deterministic, recorded in
  `debug_context.preflight_check[]` — see §8):
  - `cv_assembly.pattern_selection.status ∈ {completed, partial}`,
  - `pattern_selection.patterns[pattern_id].pattern_status !=
    failed`,
  - `cv_assembly.header_blueprint.status ∈ {completed, partial}`,
  - master-CV loader v2 succeeds,
  - Layer 6 V2 self-grader healthy (probe in §8.2).

### 7.5 Stage owner

Owned by the cv_assembly worker
(`src/cv_assembly/stages/draft_assembly.py`). Co-owned with 4.3.2
only at the validator-API level (4.3.2 `validate_header` is consumed
verbatim) and with 4.3.3 only at the persisted-pattern API level
(`PatternDoc` is consumed verbatim, never extended in flight).

## 8. Hard Prerequisites

The following must be true before `cv.draft_assembly` is allowed to
claim a job. These are checked deterministically at claim time and
recorded in `debug_context.preflight_check[]`. Per-draft prereqs
also exist (§8.3) and are checked per work item.

### 8.1 Hard-blocking prerequisites (job-wide)

If any of these fail, `cv.draft_assembly` work items are **not
enqueued**; the work-item layer marks
`level-2.cv_assembly.stage_states.cv.draft_assembly.<n>` with
`status=blocked` and `blocked_reason`.

- `level-2.lifecycle == "cv_assembling"` (4.3 lifecycle for the draft
  fan-out window).
- `cv_assembly.pattern_selection.status ∈ {completed, partial}`
  (`degraded` is a blocker — 4.3.3 must re-run; `failed` is a hard
  blocker — the job deadletters per 4.3 umbrella).
- `cv_assembly.header_blueprint.status ∈ {completed, partial}`. A
  `partial` blueprint is allowed; `degraded` and `failed` are
  blockers.
- `cv_assembly.pattern_selection.patterns[]` contains at least
  **two** entries with `pattern_status ∈ {llm_picked,
  swapped_default, clamped}` (i.e., at least two valid patterns —
  see §8.4 degraded path). Fewer than two valid patterns means there
  is no diverse fan-out to run; the job is escalated to operator
  triage and the lifecycle stays at `cv_assembling`.
- `MASTER_CV_BLUEPRINT_V2_ENABLED=true` and the master-CV loader v2
  succeeds against the pinned `master_cv_checksum` — every role used
  by the job's role family loads with `RoleMetadata.achievements[]`
  populated for `scope_band`, `metric_band`, `ai_relevance_band`,
  `dimensions[]`, `proof_categories[]`, `source_fragment_ref`.
- Canonical enums resolvable at import: `ProofType` (4.2.3),
  `ExperienceDimension` (4.2.5), `PrimaryDocumentGoal` (4.2.2),
  `DocumentSectionId` (4.2.2), `PatternLabel` (4.3.3 §9.2). Import
  failure is a blocker.
- `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED=true` AND
  `CV_ASSEMBLY_PATTERN_CONSUMED_BY_DRAFTS=true` (4.3.3 flag) — when
  the latter is `false`, the legacy single-pattern Layer 6 V2 path
  runs instead, and 4.3.4 is not invoked.

### 8.2 Degraded-allowed prerequisites (job-wide)

If any of these fail, the stage runs but emits per-draft
`status=partial` per the rules below. None alone is a blocker; the
combination is bounded by §8.4.

| Prerequisite | Degradation rule |
|---|---|
| `cv_assembly.header_blueprint.status == partial` | Drafts inherit the partial blueprint; record `upstream_partial=true` in `debug_context`. Header validator still required to pass in `mode="draft"` against the pattern's pick. |
| `cv_assembly.pattern_selection.status == partial` (≥ 1 pattern `swapped_default`) | The swapped-default pattern's draft uses a stricter truthfulness regime: `VariantSelector.pattern_bias.scope_band_cap` clamped down by one ordinal, `dimension_weights_override` follows the role-family default exactly, `forbidden_proof_categories` projection is the full union from 4.2.6. Recorded in `DraftAssemblyDebug.upstream_pattern_status_per_draft[]`. |
| `pre_enrichment.research_enrichment.status ∈ {partial, unresolved}` | Skip research-prior re-ranking inside Layer 6 V2; rely on JD facts + master-CV bands only. Confidence cap at `medium`. |
| `pre_enrichment.pain_point_intelligence.status ∈ {partial, unresolved}` | Pain-point topical vocabulary not used in Layer 6 V2 prompts; ATS keyword placement uses `jd_facts.top_keywords[]` only. |
| Layer 6 V2 self-grader probe (`POST /probe` to the model gateway, or in-process grader instantiation) returns unhealthy | Self-grader output is omitted from `DraftDoc.layer6_v2_outputs.layer6_grade_result` (advisory only — never authoritative); recorded as `defaults_applied=["layer6_self_grader:unavailable"]`. **Not a blocker** — the authoritative grade comes from 4.3.5. |
| Codex CLI primary unavailable | LangChain fallback engaged per `unified_llm.py`; recorded in `generation_trace.model_fallback_used=true`. |

### 8.3 Per-draft prerequisites (work-item-level)

Checked when a specific `cv.draft_assembly` work item claims:

- `pattern_selection.patterns[pattern_id].pattern_status != failed`
  (a `failed` pattern would not have been enqueued; this is a sanity
  check at claim time in case the upstream record changed under us).
- `pattern_selection.patterns[pattern_id].evidence_map.*` references
  resolve in the pinned master-CV (sample-checked at claim — the
  full check is the §12 validator's job at persist).
- `pattern_selection.patterns[pattern_id].header_picks.{visible_identity_candidate_id,
  lead_phrase_candidate_id, title_candidate_id}` resolve in the
  pinned `header_blueprint` pools.

A per-draft prereq failure is **not** a blocker for the job — the
work item fails (`DraftDoc.status=failed`, no `cv_text`) and the
remaining drafts proceed independently, subject to §8.4.

### 8.4 Degraded path (two-draft mode)

The diversity invariant from 4.3.3 requires at least two patterns to
proceed. The accepted ladder:

| Valid pattern count at claim | 4.3.4 fan-out | Per-job rollup status |
|---|---|---|
| 3 | 3 work items, one per pattern_id | `completed` (if all three persist with validator pass) or `partial` (if any persist with `repair_attempted`) |
| 2 | 2 work items, one per surviving pattern_id | `degraded` (4.3.5 still proceeds with two drafts) |
| 1 | 0 work items enqueued; job returns to `cv_assembling` for operator triage | `cv_assembly.status=failed_terminal_pending_operator` |
| 0 | 0 work items; deadletter | `cv_assembly.status=failed` |

When two drafts run and one fails permanently, the job rolls up to
`cv_assembly.status=failed` (only one usable draft is below the 4.3.5
minimum). When two drafts run and both succeed, the job rolls up to
`cv_assembly.status=degraded` and 4.3.5 grades two drafts.

### 8.5 Operating-mode declaration

Per the 4.3.2 / 4.3.3 §15.0 pattern, the degraded path is permitted
but is **never** the operating mode. Production runs must complete
with per-job `cv_assembly.draft_assembly_summary.status=completed`
on ≥ 90% of `cv_assembling` jobs (gate in §20.14). Two-draft
degraded mode is a fail-open **path**, not a goal.

## 9. Output Shape / Schema Direction

### 9.1 Top-level Pydantic model: `DraftDoc`

```text
DraftDoc {
  draft_id,                                  # stable: "draft_pattern_<n>"
  pattern_id,                                # 1, 2, or 3
  pattern_signature,                         # back-ref to PatternDoc.pattern_signature
  schema_version,                            # DRAFT_SCHEMA_VERSION
  prompt_version,                            # "P-draft-assembly@vX"
  prompt_metadata: PromptMetadata,
  input_snapshot_id,
  master_cv_checksum,
  presentation_contract_checksum,
  header_blueprint_checksum,
  pattern_selection_checksum,
  jd_checksum,
  status,                                    # completed | partial | degraded | failed
  upstream_pattern_status,                   # copy of source PatternDoc.pattern_status

  cv_text,                                   # final markdown (null when status=failed)
  cv_struct {                                # structured breakdown (null when status=failed)
    header: {
      headline,
      tagline,
      key_achievements[],                    # bounded by cv_shape_expectations.counts
      core_competencies[]                    # subset of pattern.evidence_map.core_competencies.skill_ids[]
    },
    summary,                                 # prose composed from pattern.evidence_map.summary refs
    ai_highlights[]?,                        # nullable; honors pattern.evidence_map.ai_highlights.enabled
    experience: [
      {
        role_id,                             # ∈ pattern.evidence_map.experience.role_order[]
        company, title, location, period,
        bullets[] {
          text,
          aris { action, result, impact_signal },
          source {
            achievement_id,
            variant_id?,
            proof_category,                  # canonical 4.2.3 enum
            dimension,                       # canonical 4.2.5 enum
            scope_band, metric_band, ai_relevance_band,
            credibility_marker_ids[],
            keyword_used?,                   # ATS keyword if injected
            pain_point_addressed?,           # ref into pain_point_intelligence
            annotation_influenced: bool,
            annotation_ids[],
            reframe_applied: bool,
            source_fragment_ref              # provenance to role markdown
          },
          number_resolution_log[]            # one entry per numeric token; see §11.5
        }
      }
    ],
    education[],
    certifications[],
    projects[]?,
    publications[]?,
    awards[]?
  },

  evidence_lineage {
    header {
      visible_identity_candidate_id_used,    # back-ref to pattern.header_picks
      lead_phrase_candidate_id_used,
      title_candidate_id_used,
      title_string_used,                     # MUST equal header_blueprint.identity.chosen_title
      hero_proof_fragment_ids_used[],
      credibility_marker_ids_used[],
      differentiator_ids_used[]
    },
    summary {
      lead_achievement_refs_used[]
    },
    bullet_lineage [                         # one entry per bullet across all sections
      {
        section_id,                          # canonical 4.2.2 section enum
        slot_index,
        role_id?,                            # nullable for non-experience sections
        achievement_id,
        variant_id?,
        proof_category,
        dimension,
        scope_band, metric_band, ai_relevance_band,
        source_fragment_ref,
        derived: bool,                       # true only for whitelisted derived markers (see below)
        derived_rule_id?                     # required when derived=true
      }
    ],
    derived_markers[] {                      # whitelisted derived statements only
      rule_id,                               # ∈ allowed-derived-marker registry
      composition_inputs[],                  # ids of master-CV fragments composed
      surface,                               # where it appears: tagline | summary | header_line
      text_snippet                           # <= 160 chars
    }
  },

  layer6_v2_outputs {                        # advisory only — NEVER authoritative
    qa_result,                               # hallucination QA from layer6_v2.role_qa
    ats_validation,                          # layer6_v2.ats_checker output
    tailoring_result,                        # layer6_v2.cv_tailorer output
    keyword_placement_validation,            # layer6_v2.keyword_placement output
    reframe_validation,
    layer6_grade_result,                     # layer6_v2.grader self-grade — advisory
    layer6_improvement_result                # layer6_v2.improver — advisory
  },

  generation_trace {
    model_primary,                           # e.g. "claude-opus-4-5" via UnifiedLLM
    model_fallback_used: bool,
    model_fallback_reason?,                  # transport_outcome enum
    tokens_input, tokens_output,
    cost_usd,
    variant_selection_trace {                # bounded counts only — full bodies in debug_context
      variants_considered_count,
      variants_selected_count,
      variants_dropped_by_pattern_bias_count,
      variants_dropped_by_truth_rule_count,
      variants_dropped_by_allowlist_count
    },
    role_generation_attempts {<role_id>: int},
    stitching_dedup_decisions_count,
    repair_count,                            # validator repairs applied
    number_stripped_count                    # bullets where a number was stripped per §11
  },

  validator_report: EvidenceLineageValidatorReport,    # §12
  header_validator_report: HeaderValidatorReport,      # 4.3.2 §11.2 in mode="draft"

  langfuse_trace_ref {
    trace_id, trace_url, parent_stage_trace_id, span_id
  },
  debug_context: DraftAssemblyDebug,
  failure_record?: DraftFailureRecord        # populated only when status=failed
}
```

### 9.2 `DraftAssemblyDebug`

```text
DraftAssemblyDebug {
  preflight_check[] {name, status, detail},
  upstream_pattern_status,
  upstream_blueprint_status,
  pattern_bias_projection {                  # full §10.2 derivation, byte-deterministic
    dimension_multipliers {<dim>: float},
    achievement_allowlist[],
    forbidden_proof_categories[],
    forbidden_phrases[],
    visible_identity_string,
    lead_phrase_string,
    title_string,
    hero_proof_fragment_strings[],           # resolved at adapter time
    credibility_marker_strings[],
    differentiator_strings[]
  },
  variant_selection_full_trace[],            # not in compact projection
  role_generation_full_trace[],
  stitching_full_trace[],
  header_prose_trace,
  number_resolution_full_trace[],            # full §11 token-by-token log
  validator_full_trace[],
  header_validator_full_trace[],
  retry_events[],
  llm_request_ids[],
  cache_hit: bool
}
```

Capped at 64 KB; collection-backed only; not mirrored to compact
projection.

### 9.3 `DraftFailureRecord`

```text
DraftFailureRecord {
  failure_kind,                              # transport | schema | validator | header_validator |
                                             # number_resolution | timeout | exhausted_retries
  rule_id?,                                  # validator rule_id when failure_kind=validator
  detail,                                    # <= 320 chars
  attempt_count,
  last_transport_outcome,                    # iteration-4 enum
  occurred_at
}
```

A failed draft persists with `cv_text=null`, `cv_struct=null`,
`evidence_lineage=null`, `failure_record` populated. Debug remains
populated for postmortem.

### 9.4 Schema versioning

`DRAFT_SCHEMA_VERSION` lives in `src/cv_assembly/models.py`. Bumps on
any change to: bullet `source` schema, `evidence_lineage` schema,
`number_resolution_log` schema, `validator_report` schema (other
than additive fields). Bumps invalidate `input_snapshot_id` and
require re-running.

## 10. PatternContext Adapter and PatternBias Composition

### 10.1 `PatternContext`

The single object that converts Layer 6 V2 from JD-only reasoning to
pattern-scoped reasoning. Built deterministically from upstream
artifacts at the start of each work item; no LLM in this construction.

```python
@dataclass(frozen=True)
class PatternContext:
    pattern_id: int
    pattern_doc: PatternDoc                  # verbatim from pattern_selection
    header_blueprint: HeaderBlueprintDoc     # shared across drafts
    presentation_contract: PresentationContractDoc
    candidate_data: CandidateData            # full master-CV loader output, v2
    classification: ClassificationDoc
    jd_facts: JdFactsDoc
    stakeholder_surface: Optional[StakeholderSurfaceDoc]
    pain_point_intelligence: Optional[PainPointIntelligenceDoc]
    pattern_bias: PatternBias                # derived per §10.2
    master_cv_checksum: str
    presentation_contract_checksum: str
    header_blueprint_checksum: str
    pattern_selection_checksum: str
    jd_checksum: str
    input_snapshot_id: str
    tracer: CvAssemblyTracingSession
```

`PatternContext` is **frozen** at adapter time. Layer 6 V2 may not
mutate it. Any decision Layer 6 V2 makes at LLM time (e.g., variant
ordering ties, prose phrasing) is constrained by but does not modify
`PatternContext`.

### 10.2 `PatternBias` deterministic composition

`PatternBias` is the projection of `PatternDoc` into a Layer 6 V2-
readable shape. Composition is **deterministic** (no LLM); for
identical `(PatternDoc, HeaderBlueprintDoc, PresentationContractDoc,
CandidateData)` inputs, the output is byte-identical across runs.
Asserted by §20.4 determinism tests.

```python
@dataclass(frozen=True)
class PatternBias:
    # ----- Dimension multipliers (used by VariantSelector scoring) -----
    dimension_multipliers: dict[ExperienceDimension, float]
    # ----- Hard allowlists (used by VariantSelector pre-filter) -------
    achievement_allowlist: frozenset[tuple[str, str, Optional[str]]]
        # set of (role_id, achievement_id, variant_id) tuples
    skill_allowlist: frozenset[str]          # core competency skill_ids
    role_emphasis: dict[str, RoleEmphasisLevel]
        # role_id -> {minimal, moderate, strong, lead}
    # ----- Hard denylists --------------------------------------------
    forbidden_proof_categories: frozenset[ProofType]
    forbidden_phrases: frozenset[str]        # forbidden_phrases from blueprint + 4.2.6 forbidden_claim_patterns substrings
    # ----- Frozen-string picks (resolved at adapter time) ------------
    title_string: str                        # equals header_blueprint.identity.chosen_title
    visible_identity_string: str             # resolved candidate from pool
    lead_phrase_string: str                  # resolved candidate from pool
    hero_proof_fragment_strings: list[str]   # resolved per pattern picks; order = picks order
    credibility_marker_strings: list[str]
    differentiator_strings: list[str]
    # ----- Section emphasis projection -------------------------------
    section_emphasis_map: dict[DocumentSectionId, SectionEmphasis]
    proof_order: list[ProofType]             # equals pattern.proof_order_override
    primary_document_goal: PrimaryDocumentGoal
    # ----- Audience tilt advisory ------------------------------------
    audience_tilt: dict[EvaluatorKey, AudienceTilt]
    # ----- Provenance for debug --------------------------------------
    derivation_trace: list[BiasDerivationStep]
```

Composition rule (called once per draft, before any LLM call):

#### 10.2.1 Dimension multipliers

For each canonical dimension `d ∈ ExperienceDimension`:

```
prior(d)      = presentation_contract.experience_dimension_weights.overall_weights[d]
override(d)   = pattern_doc.dimension_weights_override.get(d, prior(d))
multiplier(d) = override(d) / max(prior(d), 1)         # avoid div-by-zero
```

Multipliers are clamped to `[0.25, 4.0]`. The clamp matters for
narrow careers where `prior(d)` is tiny and `override(d)` is large
or vice versa — the clamp keeps `VariantSelector` scoring numerically
stable. A clamp event is recorded in `derivation_trace[]`.

#### 10.2.2 Achievement allowlist

```
A_summary  = pattern.evidence_map.summary.lead_achievement_refs[]
A_ka       = pattern.evidence_map.key_achievements.slots[]
A_exp      = ⋃ over r in pattern.evidence_map.experience.per_role.values()
                 of r.achievement_refs[]
A_ai       = pattern.evidence_map.ai_highlights.anchor_refs[]
              (if pattern.evidence_map.ai_highlights.enabled)

achievement_allowlist =
   set( (ref.role_id, ref.achievement_id, ref.variant_id)
        for ref in (A_summary ∪ A_ka ∪ A_exp ∪ A_ai) )
```

`VariantSelector` filters its candidate pool against
`achievement_allowlist` **before** scoring. Achievements outside the
allowlist are dropped and never reach the LLM prompt. Variant_id is
matched permissively: if the allowlist tuple has `variant_id=None`,
any variant of that achievement is allowed; otherwise the variant
must match exactly.

#### 10.2.3 Skill allowlist and role emphasis

```
skill_allowlist = frozenset(pattern.evidence_map.core_competencies.skill_ids)
role_emphasis   = { role_id: per_role.emphasis
                    for role_id, per_role in
                    pattern.evidence_map.experience.per_role.items() }
```

Roles outside `pattern.evidence_map.experience.role_order[]` are not
rendered. Roles in `role_order[]` but with `emphasis=minimal` get the
shortest variant the §10.2.1 allowlist permits.

#### 10.2.4 Forbidden proof categories

```
forbidden_from_4_2_6 =
    { rule.applies_to.proof_category_id
      for rule in presentation_contract.truth_constrained_emphasis_rules
                   .forbidden_claim_patterns
      if rule.applies_to_kind == "proof"
        and pattern.pattern_label in rule.applies_to.pattern_label_filter | {ANY}
    }

forbidden_from_pattern =
    { c for c in ProofType
      if c not in pattern.proof_order_override }   # only when proof_order_override is a strict subset

forbidden_proof_categories = forbidden_from_4_2_6 ∪ forbidden_from_pattern
```

When `proof_order_override` is a **permutation** (not a strict
subset) of `ProofType`, `forbidden_from_pattern` is empty and only
4.2.6 rules contribute.

#### 10.2.5 Forbidden phrases

```
forbidden_phrases =
    set(header_blueprint.tagline_ingredients.forbidden_phrases)
  ∪ set(rule.pattern
        for rule in presentation_contract.truth_constrained_emphasis_rules
                     .forbidden_claim_patterns
        if rule.pattern_kind == "substring")
```

Substring `forbidden_phrases` are matched case-insensitively at
validator time and during keyword placement; `regex_safe` rules from
4.2.6 are kept on the validator side (they need regex compilation —
not appropriate for the bias adapter, which is a pure data shape).

#### 10.2.6 Frozen-string picks

```
title_string             = header_blueprint.identity.chosen_title
visible_identity_string  = lookup_candidate(
    header_blueprint.identity.visible_identity_candidates,
    pattern.header_picks.visible_identity_candidate_id
).string
lead_phrase_string       = lookup_candidate(
    header_blueprint.tagline_ingredients.lead_phrase_candidates,
    pattern.header_picks.lead_phrase_candidate_id
).string

hero_proof_fragment_strings = [
    resolve_fragment(header_blueprint.hero_proof_fragments, fid).text_snippet
    for fid in pattern.evidence_map.header.hero_proof_fragment_ids
]
credibility_marker_strings = [...]   # analogous
differentiator_strings     = [...]   # analogous
```

Frozen strings are passed verbatim into Layer 6 V2 prompts. Layer 6
V2 may not paraphrase them; the validator asserts exact substring
appearance in the realized prose for `title_string`,
`visible_identity_string`, and `lead_phrase_string`.

#### 10.2.7 Section emphasis projection

```
section_emphasis_map = {
    se.section_id: SectionEmphasis(
        emphasis=se.emphasis,
        focus_categories=tuple(se.focus_categories),
        length_bias=se.length_bias,
        ordering_bias=se.ordering_bias,
    )
    for se in pattern.section_emphasis
}
```

Layer 6 V2 stitcher uses `length_bias` and `ordering_bias` to
shape per-section bullet counts and ordering. The numeric mapping
from `length_bias ∈ {short, standard, expansive}` to bullet counts
honors `cv_shape_expectations.counts` minimum and maximum bounds; ties
break toward `cv_shape_expectations.counts.default`.

#### 10.2.7A ATS-safe section budgets and bullet-shape contract

4.3.4 is the only prose-emitting assembly stage, so it owns the last
deterministic guardrail before grader penalties appear.

Section budgets:

- header
  - single-column logical order only;
  - no sidebars, tables, or off-body metadata constructs in the intermediate
    markdown/TipTap structure.
- summary
  - 2 to 4 sentences;
  - sentence 1 must state identity;
  - sentence 2 or 3 must carry proof, not aspiration.
- key achievements
  - 4 to 6 bullets;
  - only evidence-map-approved flagship proofs.
- core competencies
  - 8 to 12 terms, maximum 14;
  - grouped plain-text keywords only;
  - no unsupported skills; no proficiency bars.
- experience
  - current role 5 to 6 bullets;
  - previous major role 3 to 5 bullets;
  - older roles 1 to 3 bullets.
- selected projects
  - include only when the pattern or `ai_section_policy` makes them useful;
  - do not duplicate experience bullets verbatim.

Bullet-shape contract:

- every high-visibility bullet must include action + scope/system + outcome;
- responsibility-only bullets are forbidden in `key_achievements`;
- tool-list bullets are forbidden everywhere except tightly scoped
  competency lines;
- leadership bullets must still show what changed technically or
  operationally;
- summary and key-achievement bullets must prefer achievements whose
  4.3.1 `allowed_surfaces[]` permit those surfaces.

The assembly stage must also honor the current repo ATS envelope:

- standard section headers only;
- no tables/columns/text boxes in any renderable structure;
- top-third keyword density concentrated in title, summary, key
  achievements, and recent experience;
- umbrella formatting for multi-role tenure at one employer.

#### 10.2.8 Tie-break rules (deterministic)

When two candidate variants score identically under
`VariantSelector.score(variant) × multiplier(dimension)`, ties break
in this fixed order:

1. higher `RoleMetadata.achievements[].confidence.band` ordinal,
2. higher `metric_band` ordinal,
3. higher `scope_band` ordinal,
4. lexicographic `(role_id, achievement_id, variant_id ?? "")`.

This is the same tie-break ladder as 4.3.3 §11.4, intentionally —
4.3.4 must not introduce a new ordering policy.

#### 10.2.9 What is frozen at adapter time vs what the LLM may choose

Frozen at adapter time (no LLM influence):

- `dimension_multipliers`, `achievement_allowlist`, `skill_allowlist`,
  `role_emphasis`, `forbidden_proof_categories`,
  `forbidden_phrases`, `title_string`, `visible_identity_string`,
  `lead_phrase_string`, `hero_proof_fragment_strings`,
  `credibility_marker_strings`, `differentiator_strings`,
  `proof_order`, `primary_document_goal`,
  `section_emphasis_map.{emphasis, length_bias, ordering_bias}`.

LLM may choose, within the frozen guardrails:

- per-bullet wording (subject to §11 + §12),
- variant tie-break only when the deterministic ladder is genuinely
  tied (recorded in `variant_selection_trace`),
- summary prose composition over `lead_achievement_refs[]`,
- AI highlights phrasing over `anchor_refs[]`,
- core competencies surface ordering (skills set is fixed; order may
  reflect ATS priority).

LLM may **not** choose:

- which achievements appear,
- which roles appear or in what order,
- which skills are present,
- which header strings are used,
- whether AI highlights renders (governed by
  `pattern.evidence_map.ai_highlights.enabled` and
  `cv_shape_expectations.ai_section_policy`).

### 10.3 Adapter implementation surface

```python
# src/cv_assembly/pattern_context.py
def build_pattern_context(
    *,
    pattern_id: int,
    pattern_selection: PatternSelectionDoc,
    header_blueprint: HeaderBlueprintDoc,
    presentation_contract: PresentationContractDoc,
    candidate_data: CandidateData,
    classification: ClassificationDoc,
    jd_facts: JdFactsDoc,
    stakeholder_surface: Optional[StakeholderSurfaceDoc],
    pain_point_intelligence: Optional[PainPointIntelligenceDoc],
    checksums: ChecksumBundle,
    input_snapshot_id: str,
    tracer: CvAssemblyTracingSession,
) -> PatternContext: ...

def derive_pattern_bias(
    pattern: PatternDoc,
    header_blueprint: HeaderBlueprintDoc,
    presentation_contract: PresentationContractDoc,
    candidate_data: CandidateData,
) -> PatternBias: ...
```

Both functions are pure (no I/O, no clock, no random seeds, no
environment reads). Asserted by §20.1 unit tests.

## 11. Number-Resolution Policy

Free-form numeric tokens are the dominant fabrication risk in CV
prose. 4.3.4 enforces a deterministic number-resolution policy on
every realized bullet text, summary line, key achievement, and AI
highlight. The §12 validator runs the policy at persist time; the
adapter exposes the policy to Layer 6 V2 prompts as a constraint.

### 11.1 Numeric token extraction

A "numeric token" is matched by the following regex (compiled once;
case-insensitive on units):

```python
NUMERIC_TOKEN_RE = re.compile(
    r"""
    (?<![\w])                       # word boundary on the left
    (?P<sign>[+\-]?)
    (?P<int>\d{1,3}(?:[, ]\d{3})*|\d+)
    (?:\.(?P<frac>\d+))?
    (?:\s?
        (?P<unit>
            %                            # percent
          | x                            # multiplier ("3x")
          | k|K|m|M|b|B                  # magnitude suffixes
          | bps                          # basis points
          | (?:hr|hrs|h)                 # hours
          | (?:min|mins|m)               # minutes
          | (?:sec|secs|s)               # seconds
          | (?:ms|µs|us|ns)              # sub-second
          | (?:day|days|d)
          | (?:week|weeks|wk)
          | (?:month|months|mo)
          | (?:year|years|yr)
          | (?:qps|rps|tps|pps)          # rates
          | (?:gb|tb|pb|mb|kb)           # data sizes
        )?
    )
    (?![\w])                       # word boundary on the right
    """,
    re.VERBOSE | re.IGNORECASE,
)
```

The validator runs this regex against every realized
text-bearing field. Each match becomes a `NumericTokenObservation`:

```text
NumericTokenObservation {
  bullet_index?, section_id, slot_index,
  matched_text,                    # e.g., "40%"
  normalized_value,                # canonical scalar; "40%" -> 0.40, "3x" -> 3.0, "15M" -> 15_000_000
  unit_class,                      # enum: percent | multiplier | magnitude | rate | duration | size | bare
  source_decision                  # one of §11.3 outcomes
}
```

### 11.2 Source-of-truth hierarchy

For each `NumericTokenObservation`, the validator walks the following
hierarchy in order. The first hit wins; remainder are not consulted.

1. **Exact master-CV source fragment.** The bullet's
   `source.source_fragment_ref` resolves to a span in the role
   markdown. If `matched_text` (or its `normalized_value` rendered
   in any equivalent surface form — see §11.6) appears verbatim in
   the source span, the observation is `source_decision=master_cv_exact`.
2. **Structured metric field on achievement metadata.** The
   bullet's `source.achievement_id` resolves to a `RoleMetadata
   .achievements[]` entry. If `normalized_value` matches one of:
   - `achievement.scope.headcount_total`,
   - `achievement.scope.direct_reports_total`,
   - `achievement.scope.indirect_reports_total`,
   - `achievement.scope.budget_usd_per_year`,
   - `achievement.metric_band` rendered through the §11.4 band
     table,
   then the observation is `source_decision=structured_metric`.
3. **Whitelisted metric-band rendering.** When the bullet's metadata
   declares `metric_band` and the matched token is a phrase
   explicitly produced by the §11.4 band-rendering table for that
   band, the observation is `source_decision=metric_band_rendering`.
   This is how phrases like "in the millions" or "double-digit
   growth" are validated when no exact number exists.
4. **Strip / soften.** If hierarchy 1–3 produces no match, the
   token has no source. The validator action depends on §11.5 below.

### 11.3 Source-decision outcomes

| `source_decision` | Validator outcome | Persisted `NumericTokenObservation.outcome` |
|---|---|---|
| `master_cv_exact` | Pass; persist as-is | `passed_master_cv_exact` |
| `structured_metric` | Pass; persist as-is | `passed_structured_metric` |
| `metric_band_rendering` | Pass; persist as-is | `passed_metric_band_rendering` |
| (no match) AND token is **strippable** under §11.5 | Repair via `clamp_band` or `surgical_remove_bullet`; persist with `repair_applied` | `repaired_stripped` or `repaired_softened_to_band` |
| (no match) AND token is **not strippable** | Fail the bullet; if all bullets in a section fail → fail the section; if one section is critical (header, summary) → fail the draft | `failed_unsourced` |

### 11.4 Metric-band rendering table

Authoritative phrases per `metric_band`. Layer 6 V2 prompt is told to
prefer these renderings when a bullet has `metric_band` populated but
no exact number; the validator accepts only these phrases.

```text
metric_band = none      → no numeric phrase permitted; numeric token outside source = failed
metric_band = small     → "modest", "early", "small-scale" (no digits)
                          OR digit token if and only if it appears in source fragment
metric_band = medium    → "meaningful", "double-digit", "team-sized"
                          OR digit token from source fragment
metric_band = large     → "substantial", "high-double-digit", "org-wide"
                          OR digit token from source fragment
metric_band = flagship  → "company-defining", "flagship", "industry-scale"
                          OR digit token from source fragment
```

The phrase lists are concrete strings registered in
`src/cv_assembly/policies/number_resolution.py::METRIC_BAND_PHRASES`.
Only registered phrases pass the validator. New phrases require a
schema bump.

### 11.5 Strip vs soften decision

When hierarchy 1–3 fails, the validator runs the following decision:

1. **Strip the numeric token only** (preserve the rest of the
   bullet) when:
   - the bullet has at least one other realized claim (verb +
     object + impact_signal that is not the numeric token),
   - and the numeric token is **not** a key impact signal — i.e.,
     it does not appear in `aris.result` or `aris.impact_signal`.

   Action: `surgical_remove_bullet` is **not** invoked; the
   validator applies a surgical token strip and re-parses the
   bullet. Recorded as `repaired_stripped`.

2. **Soften to a banded statement** when:
   - the achievement has `metric_band ∈ {medium, large, flagship}`,
   - the numeric token's `unit_class` is `percent | magnitude |
     multiplier`,
   - and a registered phrase from §11.4 exists for that band.

   Action: replace the numeric token with a deterministic phrase
   selection (lowest-conservatism phrase from the band's whitelist
   that fits the surrounding grammar — selection is a fixed function
   of `(band, unit_class, surrounding tokens)`). Recorded as
   `repaired_softened_to_band`.

3. **Drop the bullet** when:
   - the numeric token is the bullet's sole impact signal AND
   - softening per (2) is not possible.

   Action: `surgical_remove_bullet` (one of §12.4's allowed repair
   actions). Recorded as `failed_unsourced` against the original
   bullet, plus a repair entry for the removal. The bullet is
   removed from `cv_struct.experience[].bullets[]` and
   `cv_text` is regenerated from the remaining bullets.

4. **Fail the draft** when:
   - the numeric token appears in `header.tagline`,
     `header.headline`, or `summary` — these surfaces have no
     "remove the bullet" option AND cannot be silently stripped
     without breaking grammar in a way the deterministic repair
     surface can guarantee.

   Action: validator `status=failed`; draft persists with
   `status=failed`, `failure_record.failure_kind=number_resolution`.

### 11.6 Surface-form equivalence

Numeric equivalence handles cosmetic variation deterministically:

- `40%` ≡ `40 percent` ≡ `0.40` (when comparing to a structured field).
- `15M` ≡ `15 million` ≡ `15,000,000` ≡ `15000000`.
- `3x` ≡ `3-fold` ≡ `threefold`.
- thousands separators `,` and ` ` (non-breaking space) are
  equivalent to no separator.
- locale-specific decimal separators (`.` vs `,`) are not currently
  supported; ATS envelope guarantees ASCII-decimal output. Tracked as
  a §22 deferred follow-up.

Equivalence is computed by normalizing both sides of the comparison
to a canonical scalar (`Decimal`) and a unit class.

### 11.7 Interaction with 4.2.6 truth-constrained emphasis rules

- `forbidden_claim_patterns[]` from 4.2.6 are checked **after** the
  number-resolution pass — a phrase that resolves to a band
  rendering may still be forbidden by 4.2.6 (e.g., "company-defining"
  forbidden for an early-stage achievement). When that happens, the
  bullet is stripped/softened by the next-conservative phrase or
  dropped per §11.5.
- `omit_rules[]` from 4.2.6 may pre-empt §11 entirely — a section
  flagged for omission is skipped before number resolution runs.
- `downgrade_rules[]` from 4.2.6 inform softening: the
  next-conservative phrase respects any `downgrade_rules[]` that
  applies to the achievement's `proof_category` or `dimension`.

### 11.8 Logging

Every observation is recorded in
`DraftDoc.cv_struct.experience[].bullets[].number_resolution_log[]`:

```text
NumberResolutionLogEntry {
  matched_text,
  normalized_value,
  unit_class,
  source_decision,                 # §11.3 enum
  outcome,                         # §11.3 enum
  source_fragment_offset?,         # when master_cv_exact
  metric_band_phrase_id?,          # when metric_band_rendering
  repair_action?                   # surgical_strip | soften_to_band | remove_bullet
}
```

The full log goes to debug; the compact projection retains only
counts (`number_stripped_count`, `number_softened_count`,
`number_unsourced_count`).

## 12. Evidence-Lineage Validator API

The evidence-lineage validator is a **shared library** consumed by
4.3.4 (in `mode="draft"`) and 4.3.5 (in `mode="synthesis"`). Its
determinism is load-bearing.

### 12.1 Module and signature

Module: `src/cv_assembly/validators/evidence_lineage_validator.py`.

```python
from typing import Literal, Optional
from src.cv_assembly.models import (
    DraftDoc, HeaderBlueprintDoc, PatternDoc,
    EvidenceLineageValidatorReport,
)
from src.layer6_v2.cv_loader import CandidateData
from src.cv_assembly.tracing import CvAssemblyTracingSession

EvidenceLineageValidatorMode = Literal["draft", "synthesis"]

def validate_lineage(
    draft_doc: DraftDoc,
    blueprint: HeaderBlueprintDoc,
    pattern: Optional[PatternDoc],          # required in mode="draft";
                                            # None permitted in mode="synthesis"
    master_cv: CandidateData,
    *,
    mode: EvidenceLineageValidatorMode,
    tracer: Optional[CvAssemblyTracingSession] = None,
) -> EvidenceLineageValidatorReport: ...
```

Mode semantics:

- `"draft"`: validates a single 4.3.4 draft against its source
  pattern. `pattern` is **required**. The validator asserts that
  every header element, summary line, key achievement, AI highlight,
  competency, bullet, and project ref in `draft_doc.cv_struct`
  resolves to an entry in `pattern.evidence_map` (header pool entry,
  achievement_ref, skill_id, etc.). Allowed to apply repair actions
  (§12.4).
- `"synthesis"`: validates a 4.3.5 synthesis output against the
  blueprint and the union of all source patterns'
  `evidence_map`s. `pattern=None` is permitted because synthesis
  may have promoted fragments across patterns; the validator
  asserts pool membership against the blueprint as a whole and
  achievement membership against the union of patterns from the
  job's `cv_assembly.pattern_selection.patterns[]`. 4.3.5 supplies
  the union via `synthesis_context.union_evidence_map` (4.3.5 §9.4).

### 12.2 Report shape

```text
EvidenceLineageValidatorReport {
  status,                                  # pass | repair_attempted | failed
  determinism_hash,                        # sha256 of canonical report payload (§12.5)
  schema_version,                          # VALIDATOR_REPORT_SCHEMA_VERSION
  mode,                                    # "draft" | "synthesis"
  violations[] {
    rule_id,                               # stable slug, see §12.3
    severity,                              # blocking | repairable | warning
    location {
      section,                             # canonical 4.2.2 section enum:
                                           # header | summary | key_achievements |
                                           # core_competencies | ai_highlights |
                                           # experience | projects | education |
                                           # certifications | publications | awards
      slot_index?,
      role_id?,
      achievement_id?,
      bullet_index?,
      skill_id?,
      numeric_token?                       # when rule_id is in number-resolution family
    },
    detail,                                # <= 240 chars
    suggested_action                       # enum, see §12.4
  },
  repairs_applied[] {
    rule_id,
    action,                                # enum, see §12.4
    location {...},
    before_signature,                      # sha256 over the affected fragment
    after_signature,
    detail
  },
  repaired_draft: DraftDoc | null,         # populated when any repair fired
  numeric_token_observations[],            # full §11 token-by-token log; bounded
  counts {                                 # for telemetry
    bullets_total,
    bullets_passed,
    bullets_stripped,
    bullets_dropped,
    numeric_tokens_total,
    numeric_tokens_master_cv_exact,
    numeric_tokens_structured_metric,
    numeric_tokens_metric_band_rendering,
    numeric_tokens_unsourced,
    skills_outside_pool_stripped,
    forbidden_categories_dropped
  }
}
```

### 12.3 Violation rule_id catalogue

Stable slugs; new slugs require a `VALIDATOR_REPORT_SCHEMA_VERSION`
bump and a doc update.

```
# --- evidence resolution -----------------------------------------------
bullet_achievement_id_unresolved          # achievement_id not in master-CV
bullet_variant_id_unresolved              # variant_id not in resolved achievement
bullet_role_id_unresolved
bullet_outside_pattern_evidence_map       # achievement not picked by this pattern
bullet_skill_outside_pattern_pool         # competency outside pattern.skill_ids[]
project_ref_unresolved
project_ref_outside_pattern_evidence_map
education_ref_unresolved
certification_ref_unresolved
header_visible_identity_string_mismatch   # realized prose does not contain the picked string
header_lead_phrase_string_mismatch
header_title_string_mismatch              # MUST equal blueprint.identity.chosen_title
header_hero_proof_id_outside_pattern      # picked id not in pattern.evidence_map.header.hero_proof_fragment_ids[]
header_credibility_id_outside_pattern
header_differentiator_id_outside_pattern
key_achievement_outside_pattern_slot

# --- band climbing ----------------------------------------------------
ai_band_claim_above_classification        # claim ai depth > classification.ai_taxonomy.intensity
leadership_claim_above_role_seniority     # "led", "managed", "owned a team" outside seniority allowance
scope_claim_above_role_scope              # "team of 20" not in scope.headcount_total
metric_claim_above_metric_band            # numeric token above achievement's metric_band

# --- forbidden categories / phrases -----------------------------------
forbidden_proof_category_used             # bullet's proof_category in forbidden_proof_categories[]
forbidden_phrase_used                     # exact substring from forbidden_phrases set
forbidden_claim_pattern_matched           # 4.2.6 regex_safe match
not_identity_violated                     # tag from blueprint.identity.not_identity[] used as identity

# --- number resolution (§11) -----------------------------------------
numeric_token_unsourced                   # no master-cv / structured / band match
numeric_token_above_band                  # numeric exceeds metric_band rendering
numeric_token_in_header_critical_surface  # unsourced number in headline/tagline/summary

# --- realized-prose drift -------------------------------------------
header_critical_surface_missing_picked_string  # blueprint pick not realized
key_achievement_count_exceeds_shape       # too many KA bullets vs cv_shape_expectations.counts
core_competency_count_exceeds_shape
ai_highlights_enabled_with_no_anchor      # section rendered but no anchor_refs satisfied
ai_highlights_disabled_but_rendered

# --- derived markers ------------------------------------------------
derived_marker_unregistered               # rule_id not in the allowed-derived-markers registry
derived_marker_inputs_unresolved          # composition_inputs ids do not resolve

# --- determinism guards (sanity) ------------------------------------
schema_version_mismatch
pattern_signature_mismatch                # DraftDoc.pattern_signature != PatternDoc.pattern_signature
```

### 12.4 Allowed deterministic repair actions

Repair is **deterministic**, **bounded to one pass per draft**,
**never calls an LLM**, and **never adds content outside the
pattern's evidence_map or master-CV evidence**.

| Action | Applies to | Effect |
|---|---|---|
| `surgical_remove_bullet` | `bullet_outside_pattern_evidence_map`, `bullet_achievement_id_unresolved`, `bullet_variant_id_unresolved`, `numeric_token_unsourced` (when bullet is non-strippable per §11.5), `forbidden_proof_category_used` (when softening fails), `forbidden_phrase_used` | Drop the bullet from `cv_struct.experience[].bullets[]`; renumber slots; preserve order; regenerate `cv_text` from remaining bullets. |
| `soften_per_emphasis_rule` | `forbidden_claim_pattern_matched`, `metric_claim_above_metric_band`, `scope_claim_above_role_scope`, `leadership_claim_above_role_seniority`, `numeric_token_above_band` | Apply the relevant 4.2.6 `downgrade_rules[]` action verbatim — replace the offending fragment with the next-conservative phrase from the rule's `action` field. Recorded with `before_signature` / `after_signature`. |
| `collapse_section` | `key_achievement_count_exceeds_shape`, `core_competency_count_exceeds_shape`, `ai_highlights_enabled_with_no_anchor`, `ai_highlights_disabled_but_rendered` | Drop the section's overflow slots (deterministic ordering by slot_index ascending) or drop the section entirely; re-render `cv_text`. |
| `clamp_band` | `ai_band_claim_above_classification`, `leadership_claim_above_role_seniority` (when softening per `downgrade_rules` is not configured), `metric_claim_above_metric_band` (when softening fails) | Reduce the numeric/ordinal claim to the maximum allowed by upstream (`classification.ai_taxonomy.intensity`, `seniority.managerial_level`, `metric_band`). For prose, replaces the claim phrase with the §11.4 phrase one band lower. |
| `strip_skill_outside_pool` | `bullet_skill_outside_pattern_pool` | Remove the skill from `cv_struct.header.core_competencies[]`; re-render `cv_text`. Bullets that cite the stripped skill via `keyword_used` lose only the keyword annotation, not the bullet. |
| `strip_numeric_token` | `numeric_token_unsourced` (when bullet is strippable per §11.5) | Replace the numeric token with the surrounding-grammar-aware phrase per §11.5(1). The bullet text is re-tokenized; sentence integrity is checked deterministically (presence of subject + verb after strip); if integrity fails, the action escalates to `surgical_remove_bullet`. |
| `substitute_picked_string` | `header_visible_identity_string_mismatch`, `header_lead_phrase_string_mismatch` | Replace the realized prose's identity/lead-phrase fragment with the exact picked string from the blueprint pool. Used when Layer 6 V2 paraphrased a frozen pick. The bullet's grammar around the substitution is checked deterministically. |

Repair never:

- generates new prose,
- introduces a master-CV ref not already in the pattern's
  `evidence_map` (in `mode="draft"`) or the union (in
  `mode="synthesis"`),
- introduces a header pool member outside the blueprint,
- changes `chosen_title` or `chosen_title_strategy`,
- regenerates via LLM,
- bumps section emphasis or dimension multipliers.

After one pass, the validator re-runs the gate on `repaired_draft`.
Remaining `severity=blocking` violations → `status=failed`.
Remaining `severity=repairable` violations after one pass →
`status=failed`. `severity=warning` violations are retained but do
not fail the run.

### 12.5 Determinism guarantees

For fixed `(draft_doc, blueprint, pattern, master_cv, mode)`,
`validate_lineage()` returns byte-identical
`EvidenceLineageValidatorReport` instances across runs.

- `determinism_hash` is `sha256:` over the canonical JSON form of
  the report (excluding `determinism_hash` itself), with the same
  canonicalization rule as 4.3.3 §12.2:
  `json.dumps(payload, sort_keys=True, separators=(",", ":"),
  ensure_ascii=True, allow_nan=False)`.
- Asserted by
  `tests/unit/cv_assembly/test_evidence_lineage_validator_determinism.py`
  with two runs over the same inputs.
- No clock reads, no random seeds, no environment reads, no Mongo
  reads, no network. Pure function over inputs.

### 12.6 Test fixture expectations

Per `tests/unit/cv_assembly/test_evidence_lineage_validator.py`:

- one fixture per `rule_id` in §12.3 — a synthesized minimal
  `DraftDoc` that violates only that rule, with the expected
  `severity` and `suggested_action`.
- one repair fixture per `action` in §12.4 — pre/post draft docs and
  expected `repairs_applied[]` entry.
- one number-resolution fixture per `source_decision` outcome.
- one mode-difference fixture: same defect in `mode="draft"` and
  `mode="synthesis"`, asserting that `mode="synthesis"` accepts a
  bullet whose achievement is in the union but not in any single
  pattern (this is exactly the cross-pattern promotion 4.3.5
  performs).
- one no-IO fixture: `validate_lineage` invocation with `socket`,
  `pymongo`, `open`, and `requests` patched to raise; the validator
  must complete without touching any of them.

## 13. Header Validator Consumption Contract

4.3.4 does **not** own the header validator. 4.3.4 **consumes** the
shared validator declared in 4.3.2 §11.2.

### 13.1 Required call

For each draft, before persist, after the §12 lineage validator's
first pass and before its repair re-check (the order matters — see
§13.4):

```python
header_report = validate_header(
    header_struct=draft.cv_struct.header,
    blueprint=header_blueprint,
    master_cv=candidate_data,
    mode="draft",
    pattern=current_pattern_doc,             # required in mode="draft"
    tracer=tracer,
)
```

The call is mandatory — drafts may not be persisted without a
`header_validator_report`.

### 13.2 Input shape

`HeaderStruct` is the canonical struct surface defined by 4.3.2 §11.2.1:
`{headline, tagline, key_achievements[], core_competencies[]}`.
4.3.4 builds it from `draft.cv_struct.header` directly; the fields
have one-to-one correspondence.

### 13.3 Validator failure handling

`HeaderValidatorReport.status` outcomes:

- `pass` → proceed to lineage validator.
- `repair_attempted` → proceed using `repaired_struct`; the repair
  is recorded in `DraftDoc.header_validator_report.repair_actions[]`.
- `failed` → the draft cannot be persisted with a valid header.
  Outcome:
  - if the failing rule is `severity=blocking` (per 4.3.2 §11.2.3
    semantics) → draft `status=failed`,
    `failure_record.failure_kind=header_validator`,
    `rule_id=<the failing rule>`.
  - if the failing rule is `severity=repairable` and one pass did
    not heal it → same as blocking: draft `status=failed`.

A failed header validator is **never** repaired by 4.3.4
independently of the 4.3.2 validator's repair surface. 4.3.4 may not
add a repair action that 4.3.2 §11.2.3 does not list.

### 13.4 Ordering of header validator vs lineage validator

Order: header validator **first**, lineage validator **second**.

Rationale:

- The header validator may perform `substitute_from_pool` repairs
  that swap a `chosen_title` candidate (within
  `title_candidates[]`) — this can change which bullets are
  consistent with the realized header prose. Running it first means
  the lineage validator sees the final realized header.
- The lineage validator's `surgical_remove_bullet` actions never
  affect the header surface — header repair concerns are bounded
  to the 4.3.2 validator.
- Both validators are deterministic and pure; running them
  sequentially preserves byte-determinism.

The header validator's `repaired_struct` (when present) replaces
`draft.cv_struct.header` before the lineage validator runs.

### 13.5 Failure propagation to 4.3.5

`DraftDoc.header_validator_report` is persisted in full (status,
violations, repair actions, repaired_struct hashes). 4.3.5 reads:

- `status` — feeds the rubric Truth/Evidence dimension (a draft
  with `repair_attempted` is penalized vs a clean `pass`).
- `repair_actions[]` count — feeds the rubric Pattern Fidelity
  dimension.
- `violations[]` with `severity=warning` — surfaced in the dossier
  for operator audit, but does not fail the draft.

A `failed` header_validator_report on any persisted draft is
impossible by §13.3 (the draft would be `status=failed` and not
contribute prose to 4.3.5).

## 14. Cross-Artifact Invariants

Restated as hard implementation rules; enforced by §12 and §13.

- **I1.** `DraftDoc.pattern_signature == PatternDoc.pattern_signature`
  for the same `pattern_id` (4.3.3 §12 byte-determinism).
- **I2.** `DraftDoc.cv_struct.header.title_string ==
  HeaderBlueprintDoc.identity.chosen_title` (frozen across all
  drafts of a job).
- **I3.** Every realized claim (bullet text, summary line, key
  achievement, AI highlight) cites a `(role_id, achievement_id,
  variant_id?)` tuple in `pattern.evidence_map.experience.per_role.*
  ∪ pattern.evidence_map.summary.lead_achievement_refs ∪ pattern.
  evidence_map.key_achievements.slots ∪ pattern.evidence_map.
  ai_highlights.anchor_refs`.
- **I4.** Every skill in `cv_struct.header.core_competencies[]` ∈
  `pattern.evidence_map.core_competencies.skill_ids[]`.
- **I5.** Every header pool reference (hero_proof, credibility,
  differentiator) used in realized prose ∈ the corresponding
  `pattern.evidence_map.header.*_ids[]`.
- **I6.** No realized claim's `proof_category` ∈
  `forbidden_proof_categories` (composed per §10.2.4).
- **I7.** No realized prose contains a substring from
  `forbidden_phrases` (composed per §10.2.5) or matches a
  `forbidden_claim_patterns[].pattern` (4.2.6).
- **I8.** Every numeric token in realized prose has a
  `source_decision ∈ {master_cv_exact, structured_metric,
  metric_band_rendering}` OR the token has been deterministically
  stripped/softened/dropped per §11.
- **I9.** `ai_relevance_band` claimed in any realized claim ≤
  `classification.ai_taxonomy.intensity`. AI highlights section
  rendered iff `pattern.evidence_map.ai_highlights.enabled` AND at
  least one anchor has `ai_relevance_band ≥ significant`.
- **I10.** `seniority.managerial_level` cited indirectly by any
  leadership phrase ≤ `lead_role.seniority.managerial_level`.
- **I11.** `dimension_weights_override` from `pattern_doc` is the
  authoritative emphasis input for `VariantSelector` — Layer 6 V2
  may not override it from JD facts or self-grader feedback.
- **I12.** `proof_order_override[]` from `pattern_doc` is the
  authoritative `VariantSelector` proof-category ordering.
- **I13.** Pattern-source semantics: a draft from a `swapped_default`
  pattern uses the conservative truthfulness regime (§8.2): no
  `repair_action=clamp_band` permitted (the draft fails outright if
  it needs band climbing repair) and `metric_band_rendering`
  defaults to the lowest-conservatism phrase.
- **I14.** Failed drafts do not poison siblings: a draft work item
  failure is bounded to its `pattern_id`'s slot in
  `cv_assembly.drafts[]`. The other drafts continue independently.
- **I15.** Degraded stage output is consumable by 4.3.5: when only
  two drafts persist, both must satisfy I1–I13; 4.3.5 grades and
  may synthesize cross-draft as if there were three.

If any invariant fails after one deterministic repair pass, the
draft is `status=failed`. Inv I14 is structural (work-item isolation)
and is enforced by the `cv_assembly` worker, not by the validator.

## 15. Fail-Open / Fail-Closed

### 15.1 Fail-open (per draft)

- **Single retry on recoverable Layer 6 V2 failure.** Transport
  outcomes `error_timeout`, `error_subprocess`, `error_no_json`,
  `error_schema` per the iteration-4 transport-outcome enum allow
  one retry with cache-busted prompt; on second failure, the work
  item retries per `max_attempts = 3`. After `max_attempts`,
  `status=failed`, `failure_record.failure_kind=transport`.
- **One in-stage validator repair pass.** §12.4 actions fire once
  per draft. `status=partial` when repairs healed any violations;
  `status=completed` when zero repairs fired.
- **Number softening** instead of strip/drop when §11.5(2) applies.
  Recorded as `repaired_softened_to_band`.
- **Layer 6 V2 self-grader unavailable** → `layer6_grade_result` and
  `layer6_improvement_result` omitted; draft proceeds.
- **AI highlights collapsed** when the pattern enabled them but no
  anchor satisfies `ai_relevance_band ≥ significant` after band
  enforcement → §12.4 `collapse_section`; `status=partial`.

### 15.2 Fail-open (per job, two-draft mode)

Per §8.4: when only two patterns are valid at claim time, run two
work items. When one of two work items fails permanently, the job
goes to `cv_assembly.status=failed` (only one persisted draft is
below the 4.3.5 minimum). When two of three work items fail
permanently, the same applies.

### 15.3 Fail-closed (per draft)

- **Header validator failure** (§13.3) → `status=failed`,
  `failure_record.failure_kind=header_validator`. No fabricated
  header repair.
- **Title outside `acceptable_titles` after substitute_from_pool
  attempt** → `status=failed`. Title drift is identity drift, not a
  pool defect.
- **Numeric token in `headline | tagline | summary` with no source**
  → `status=failed` (§11.5(4)). Header surfaces have no fallback.
- **Pattern signature mismatch** (`DraftDoc.pattern_signature !=
  PatternDoc.pattern_signature`) → `status=failed`. This indicates
  upstream-record drift; repair is impossible at this stage.
- **Schema version mismatch on persisted `pattern_doc`** →
  `status=failed`. Operator triage; no auto-repair.

### 15.4 Fail-closed (per job)

- **Zero successful drafts** → `cv_assembly.status=failed`, job
  deadletters per 4.3 umbrella. No best-effort publishing.
- **Pattern selection record disappeared between claim and persist**
  (rare; indicates external mutation) → all in-flight drafts fail;
  `cv_assembly.status=failed`.

### 15.5 What is **not** fail-open

- Inventing a metric to satisfy `metric_band_rendering` when the
  band table has no phrase for that combination — the validator
  fails the bullet.
- Substituting a different `chosen_title` to satisfy a pattern's
  preferred framing — title is frozen.
- Inventing an achievement to fill an empty `key_achievements` slot.
- Promoting a fragment from a sibling draft into the current draft.
  Cross-draft promotion is exclusively 4.3.5's surface.

## 16. Safety / Anti-Hallucination

Inherits the cross-family anti-hallucination invariants (4.3 umbrella
§9). The §12 validator is the load-bearing enforcement surface; §11
is the load-bearing enforcement on numeric tokens. Specific rules
restated:

- **No bullet introduces an entity** (system, customer, framework,
  product) not in the achievement source fragment or the
  `credibility_marker_taxonomy`.
- **No causal claims** ("which drove X", "resulting in Y") unless X
  or Y appears in the achievement evidence.
- **Summary prose** is constrained to compositions of
  `visible_identity_string`, `identity_tags[]` from blueprint, and
  whitelisted phrases from `header_blueprint.tagline_ingredients`
  pool. New compositions require a `derived_marker` registry entry.
- **Key achievements** are constrained to
  `pattern.evidence_map.key_achievements.slots[]`. The LLM may not
  add achievements outside that list; achievements outside it are
  filtered before LLM prompting.
- **Core competencies** are constrained to
  `pattern.evidence_map.core_competencies.skill_ids[]`; skills
  outside the list are stripped via §12.4 `strip_skill_outside_pool`.
- **No protected-trait inference, clinical profiling, private
  stakeholder motives.** Carried from 4.3 umbrella.
- **No web search, no cross-job reasoning, no candidate-wide claims
  not pinned to the master-CV snapshot.**
- **No metric invention.** Numbers in prose pass §11 or are
  removed/softened.
- **Derived markers** are an explicit, audited surface — every
  `derived_marker` in `cv_struct` carries a registered `rule_id`
  whose composition rule references master-CV fragments only. The
  registry lives at
  `src/cv_assembly/derived_markers/registry.py`. New rules require
  PR review and a schema bump.

## 17. Downstream Consumer Contracts

### 17.1 4.3.5 (Draft Grading, Selection, and Synthesis)

4.3.5 reads from `cv_assembly.drafts[]`:

| Field | Used for | Override allowed? |
|---|---|---|
| `cv_struct.*` | Rubric scoring (truth, pattern fidelity, coverage); cross-draft fragment promotion | no |
| `evidence_lineage.*` | Lineage check for synthesis (`mode="synthesis"`); cross-draft union | no |
| `validator_report.status` | Truth/Evidence rubric (clean pass = full credit; repair_attempted = partial credit) | no |
| `validator_report.violations[]` (severity=warning) | Truth/Evidence rubric tie-break | no |
| `header_validator_report.status` | Truth/Evidence rubric for header-bound claims | no |
| `header_validator_report.repair_actions[]` count | Pattern Fidelity rubric | no |
| `pattern_id`, `pattern_signature`, `upstream_pattern_status` | Pattern Fidelity rubric; cross-pattern compatibility table for synthesis (4.3.5 §9.3) | no |
| `layer6_v2_outputs.layer6_grade_result` | **Advisory only** — never authoritative; surfaced in dossier | advisory |
| `generation_trace.cost_usd`, `tokens_input`, `tokens_output` | Cost telemetry roll-up (4.3.8 cost breaker) | no |
| `debug_context.pattern_bias_projection` | 4.3.5 reviewer audit; not used in grading | advisory |
| `failure_record` (when present) | 4.3.5 ignores failed drafts; surfaces in dossier for operator | no |

4.3.5 may **not**:

- introduce evidence outside the union of the persisted drafts'
  patterns' `evidence_map`s,
- modify `header_picks` of any draft (4.3.4 freezes them),
- re-run §11 on persisted bullet text — promotion is fragment-level,
  and the lineage validator in `mode="synthesis"` re-runs if the
  fragment is merged.

### 17.2 4.3.5 synthesis input contract

When 4.3.5 builds `synthesis_context` (4.3.5 §9.3), it composes:

- `union_evidence_map = ⋃ pattern.evidence_map for pattern in
  pattern_selection.patterns where pattern_id ∈ persisted drafts`,
- `validator_inputs = {draft_id, validator_report, header_validator_report}
  for each persisted draft`,
- `cost_envelope = sum of generation_trace.cost_usd` (advisory).

The synthesis context's `union_evidence_map` is what
`validate_lineage(..., mode="synthesis", pattern=None)` is asserted
against.

### 17.3 4.3.6 (Publisher and Renderer)

4.3.6 **does not** read from `cv_assembly.drafts[]` directly. 4.3.6
reads from `cv_assembly.synthesis` (the 4.3.5 output) only. This is a
hard contract: the publisher must be agnostic to which pattern won
or which fragments were promoted; it sees a single synthesis output.

If 4.3.6 needs a debug surface (e.g., showing the user the three
candidate drafts in the dossier), it goes through 4.3.7 (dossier and
state contract), which **may** read `cv_assembly.drafts[]` for
read-only display — never for rendering the published CV.

### 17.4 Persistence as the contract

The persisted `cv_assembly.drafts[]` document is the single source of
truth for downstream consumers. There is no parallel "draft service"
that 4.3.5 / 4.3.6 may consult. If a downstream needs information not
in the persisted doc, the doc must be extended (with a
`DRAFT_SCHEMA_VERSION` bump and a 4.3.4 prompt-version bump), not
derived ad-hoc by the consumer.

## 18. Langfuse Tracing Contract

Inherits 4.3 umbrella verbatim. Stage-specific rules below are
normative.

### 18.1 Canonical trace, stage span, per-draft subspans

- Trace: `scout.cv.run` (4.3 umbrella).
- Job span: `scout.cv.job` with `langfuse_session_id=job:<level2_id>`.
- Stage span: `scout.cv_assembly.draft_assembly` — emitted by the
  `cv_assembly` worker for each work item. The stage span carries
  `pattern_id` so the three drafts appear as three sibling spans
  under the same job span.
- Per-draft subspan suffix: `.pattern_<n>` (e.g.,
  `scout.cv_assembly.draft_assembly.pattern_2`) — used by per-draft
  events and metadata.

### 18.2 Substep spans

Only those that meaningfully time work; cardinality bounded.

```
scout.cv_assembly.draft_assembly                    # stage span (per work item)
  ├── .context_build                                # PatternContext + PatternBias derivation
  ├── .prompt_build                                 # Layer 6 V2 prompt assembly with bias projection
  ├── .llm_call.primary                             # UnifiedLLM primary call
  ├── .llm_call.fallback                            # only when fallback fires
  ├── .variant_selection                            # VariantSelector with pattern_bias
  ├── .role_generation                              # per-role generation; metadata-only, no per-role span
  ├── .stitching                                    # stitcher
  ├── .header_prose                                 # blueprint-first HeaderGenerator
  ├── .ats_validation                               # layer6_v2.ats_checker
  ├── .header_validate                              # 4.3.2 validate_header(mode="draft")
  ├── .lineage_validate                             # §12 validate_lineage(mode="draft")
  ├── .repair                                       # only when at least one repair fires
  ├── .self_grade                                   # layer6_v2.grader; advisory; collapsed when unhealthy
  └── .persist                                      # Mongo write + pattern_signature back-ref
```

No per-role child spans. Cardinality is bounded by the §9 schema.
Per-role detail goes into events and metadata.

### 18.3 Events

- `scout.cv_assembly.draft_assembly.cache.hit` /
  `.cache.miss`.
- `scout.cv_assembly.draft_assembly.draft_skipped` — emitted when a
  per-draft prereq fails (§8.3); metadata `{pattern_id, reason}`.
- `scout.cv_assembly.draft_assembly.degraded_to_two_draft_mode` —
  emitted **once per job** by the first work item to detect §8.4
  two-draft mode. Metadata `{valid_pattern_count, degraded_pattern_ids}`.
- `scout.cv_assembly.draft_assembly.variant_filtered` — counts of
  variants dropped by `pattern_bias.achievement_allowlist`,
  `forbidden_proof_categories`, and 4.2.6 truth rules. Emitted once
  per draft, with `{dropped_by_allowlist, dropped_by_forbidden_category,
  dropped_by_truth_rule, dropped_by_dimension_clamp}`.
- `scout.cv_assembly.draft_assembly.validator_repair_applied` — one
  per repair action; metadata `{pattern_id, rule_id, action,
  before_signature, after_signature}`.
- `scout.cv_assembly.draft_assembly.number_stripped` — one per
  numeric token whose `outcome ∈ {repaired_stripped,
  repaired_softened_to_band}`. Metadata `{pattern_id, section,
  slot_index, unit_class, outcome, metric_band_phrase_id?}`. Cardinality
  bounded by `number_stripped_count`; capped at 50 per draft.
- `scout.cv_assembly.draft_assembly.lineage_failure` — emitted when
  `validator_report.status=failed`. Metadata `{pattern_id, rule_id,
  severity}`.
- `scout.cv_assembly.draft_assembly.header_failure` — emitted when
  `header_validator_report.status=failed`. Metadata `{pattern_id,
  rule_id, severity}`.
- `scout.cv_assembly.draft_assembly.draft_persisted` — one per draft
  on success; metadata `{pattern_id, pattern_signature, status,
  repair_count, number_stripped_count, validator_status,
  header_validator_status}`.
- Lifecycle events (`claim`, `enqueue_next`, `retry`, `deadletter`,
  `release_lease`) are 4.3 umbrella.

### 18.4 Required metadata on every span / event

`job_id`, `level2_id`, `correlation_id`, `langfuse_session_id`,
`run_id`, `worker_id`, `task_type`, `stage_name`, `attempt_count`,
`attempt_token`, `input_snapshot_id`, `master_cv_checksum`,
`presentation_contract_checksum`, `header_blueprint_checksum`,
`pattern_selection_checksum`, `jd_checksum`, `pattern_id`,
`pattern_signature`, `lifecycle_before`, `lifecycle_after`,
`work_item_id`.

### 18.5 Stage-specific metadata on the stage span (on end)

- `status` ∈ `{completed, partial, degraded, failed}`,
- `pattern_count_requested` (job-wide; redundant on per-draft span,
  but useful for filtering),
- `pattern_count_started` (per job),
- `pattern_count_persisted` (per job),
- `draft_count_success` (per job; rolled up by sweeper after all
  drafts complete; emitted on the last work item to finish),
- `draft_count_failed` (per job; same emission rule),
- `degraded_mode: bool` — true when valid_pattern_count == 2,
- `header_validator_failures` (per draft on the per-draft span;
  rolled up at job span by sweeper),
- `lineage_validator_failures`,
- `repair_count` (sum across both validators),
- `number_stripped_count`,
- `number_softened_count`,
- `number_unsourced_count`,
- `self_grade_model` (when self-grader ran),
- `model_primary`, `model_fallback_used`,
- `tokens_input`, `tokens_output`, `cost_usd`,
- `validator_status`, `header_validator_status`,
- `confidence_band` (composite of validator outcomes; advisory),
- `prompt_version`, `prompt_git_sha`,
- `cache_hit: bool`,
- `trace_ref` — back-pointer to Mongo `cv_assembly_stage_runs` row
  for this draft.

### 18.6 What flows into Mongo trace refs

The stage's `trace_id` and `trace_url` flow into:

- `cv_assembly_stage_runs` — one row per draft work item,
- `cv_assembly_job_runs` — aggregate job-level (rolled up by 4.3.5
  barrier or by the sweeper when the last draft completes),
- `cv_assembly.stage_states.cv.draft_assembly.<pattern_id>.{trace_id,
  trace_url}`,
- `DraftDoc.langfuse_trace_ref.{trace_id, trace_url, parent_stage_trace_id,
  span_id}`.

An operator opening a single `level-2` job in the UI reaches each
draft's Langfuse trace in one click.

### 18.7 Forbidden in Langfuse

- full `cv_text` body,
- full `cv_struct` body,
- full bullet text beyond a 240-char preview per bullet (only on
  events where strictly necessary, e.g., `validator_repair_applied`
  detail field),
- full `evidence_lineage` body,
- full `header_validator_report.repaired_struct` body,
- full `debug_context` body,
- full `pattern_bias_projection.derivation_trace[]` body,
- full `number_resolution_log[]` body,
- raw LLM prompts unless `_sanitize_langfuse_payload` is applied
  AND `LANGFUSE_CAPTURE_FULL_PROMPTS=true`.

Previews capped at 240 chars via `_sanitize_langfuse_payload`. Numeric
counters (`number_stripped_count`, etc.) are not capped; they are
small integers.

### 18.8 What may live only in `debug_context` (Mongo)

- raw variant-selection trace (per-variant scores),
- raw role-generation trace (per-role attempts, retries),
- raw stitching dedup trace,
- raw number-resolution log (token by token),
- full validator-trace per-rule,
- full header-validator-trace per-rule,
- full LLM request ids and full repair prompts.

### 18.9 Cardinality and naming safety

- Substep span names are a fixed, small set (§18.2).
- Per-draft detail is metadata + events; no nested per-role spans.
- Repair actions bounded at one pass per draft → bounded
  `validator_repair_applied` cardinality.
- LLM fallback bounded → ≤ 2 `llm_call.*` spans per draft.
- `number_stripped` events capped at 50 per draft (excess collapsed
  into a single `number_stripped_overflow` event with
  `excess_count`).

### 18.10 Operator debug checklist (normative)

An operator must be able to diagnose each of these from `level-2` →
trace in < 2 minutes:

- slow draft execution → inspect
  `llm_call.primary.duration_ms` and `stitching.duration_ms`.
- header drift → `header_failure` event with `rule_id` and
  `repair_count`.
- lineage drift → `lineage_failure` event with `rule_id`.
- number issues → `number_stripped` event count vs
  `number_resolution_log.numeric_tokens_unsourced`.
- AI band climbing → `validator_repair_applied` events with
  `rule_id=ai_band_claim_above_classification`.
- pattern allowlist mismatch → `variant_filtered` event with
  `dropped_by_allowlist > expected`.
- two-draft mode → `degraded_to_two_draft_mode` event on the job
  span.
- model fallback → `llm_call.fallback` span present;
  `model_fallback_used=true` metadata.
- stuck draft → no heartbeat after lease expiry; correlate via
  `worker_id` and `attempt_token`.

## 19. Operational Catalogue

### 19.1 Stage owner

Owned by the cv_assembly worker.
Module: `src/cv_assembly/stages/draft_assembly.py`.
Stage definition: `src/cv_assembly/stage_registry.py`.
Co-owner: 4.3.2 (header validator) and 4.3.3 (pattern doc) at the
shared-library level only — no cross-stage code in `draft_assembly.py`.

### 19.2 Prerequisite artifacts

- `cv_assembly.pattern_selection` (4.3.3) — hard prerequisite (§8.1).
- `cv_assembly.header_blueprint` (4.3.2) — hard prerequisite (§8.1).
- `pre_enrichment.presentation_contract.{document_expectations,
  cv_shape_expectations, ideal_candidate_presentation_model,
  experience_dimension_weights, truth_constrained_emphasis_rules}` —
  hard prerequisite for the first two; degraded-allowed for the last
  three (§8.2).
- `pre_enrichment.{classification, jd_facts, stakeholder_surface,
  pain_point_intelligence, research_enrichment}` — read-only;
  degraded-allowed for the last three (§8.2).
- Master-CV via loader v2 (4.3.1) — hard prerequisite.

### 19.3 Persisted Mongo locations

| What | Location |
|---|---|
| Full draft artifact | `cv_assembly.drafts` collection (or subdocument), unique filter `(level2_id, input_snapshot_id, pattern_id, prompt_version)` |
| Draft slot in level-2 | `level-2.cv_assembly.drafts[<pattern_id - 1>]` |
| Per-draft stage state | `level-2.cv_assembly.stage_states.cv.draft_assembly.<pattern_id>` |
| Job-level rollup | `level-2.cv_assembly.draft_assembly_summary` |
| Stage run audit | `cv_assembly_stage_runs` (one row per draft work item) |
| Job run aggregate | `cv_assembly_job_runs` |
| Work item | `work_items`, `task_type=cv.draft_assembly`, one per pattern_id |
| Alerts | `cv_assembly_alerts` (on deadletter only, rate-limited) |

### 19.4 Stage-run records touched

`cv_assembly_stage_runs` row per draft with: `status`, `trace_id`,
`trace_url`, `provider_used`, `model_used`, `prompt_version`,
`tokens_input`, `tokens_output`, `cost_usd`, `validator_status`,
`header_validator_status`, `repair_count`, `number_stripped_count`,
`upstream_pattern_status`, `fail_open_reason` (when present).

### 19.5 Work-item semantics

- enqueued by the DAG sweeper when
  `cv_assembly.pattern_selection.status ∈ {completed, partial}`
  and the per-pattern `pattern_status != failed`;
- payload per §7.4;
- claimed atomically via `StageWorker.claim` with lease;
- on success, the work item writes its `DraftDoc` to
  `cv_assembly.drafts[]` and updates
  `cv_assembly.stage_states.cv.draft_assembly.<pattern_id>`. The
  4.3.5 barrier polls all enqueued draft work items; once all are
  terminal AND ≥ 2 are non-failed, 4.3.5 is enqueued.

### 19.6 Fan-out behavior

- One work item per `pattern_id` (1, 2, or 3 depending on §8.4).
- Work items are independent; they may run concurrently up to the
  worker's `MAX_PARALLEL_DRAFT_ASSEMBLIES` env cap (default 2 on
  the canary VPS, 3 in production).
- Failed sibling does not halt the fan-out (§14 I14).

### 19.7 Cache semantics

- Cache key: `(level2_id, input_snapshot_id, pattern_id,
  prompt_version, DRAFT_SCHEMA_VERSION)`.
- Cache stored in `cv_assembly.drafts` collection itself; hit ⇒ skip
  Layer 6 V2 invocation, project cached doc into a new
  `attempt_token`-keyed write, re-run validators (validators are
  free; fresh runs every time).
- Bust on any change to: `master_cv_checksum`,
  `header_blueprint_checksum`, `pattern_selection_checksum`,
  `presentation_contract_checksum`, `jd_checksum`, `PROMPT_VERSION`,
  `DRAFT_SCHEMA_VERSION`, `VALIDATOR_REPORT_SCHEMA_VERSION`.
- Emits `scout.cv_assembly.draft_assembly.cache.{hit,miss}` events
  with metadata `{cache_key, hit_reason, ttl_remaining_s,
  upstream_pattern_status, upstream_blueprint_status}`.

### 19.8 Retry / repair behavior

- `max_attempts = 3` at the work-item level.
- One in-stage validator repair pass per draft (§12.4).
- One in-stage header validator repair pass per draft (4.3.2 §11.2.3).
- One LLM transport retry on recoverable failure
  (`error_timeout`, `error_subprocess`, `error_no_json`,
  `error_schema`).
- `job_fail_policy=fail_closed` per 4.3 umbrella when ≥ 2 drafts
  fail.
- `job_fail_policy=fail_open` (4.3.5 proceeds with the surviving
  drafts) when status `partial` or `degraded`.

### 19.9 Heartbeat expectations

- Stage heartbeat every 60 s by the worker
  (`CV_ASSEMBLY_STAGE_HEARTBEAT_SECONDS=60`).
- The stage must yield CPU between Layer 6 V2 phases (preflight,
  variant selection, role generation, stitching, header prose,
  validators, persist).
- Launcher-side wrapper (§21) emits operator heartbeat every
  15-30 s, including last substep, last validator phase, Codex
  PID and stdout/stderr tail when relevant.
- Silence > 90 s = stuck-run flag.

### 19.10 Feature flags

- `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED` — master flag for the stage.
  Off: stage not registered; 4.3.5 not invoked; legacy single-pass
  Layer 6 V2 path runs against the most recent persisted pattern
  (debug-only).
- `CV_ASSEMBLY_PATTERN_CONSUMED_BY_DRAFTS` — gates whether 4.3.4
  reads `cv_assembly.pattern_selection`. Off: 4.3.4 falls back to a
  single Layer 6 V2 invocation per job (one draft only);
  fan-out skipped; 4.3.5 may grade one draft only.
- `CV_ASSEMBLY_DRAFT_NUMBER_RESOLUTION_STRICT` — when `true`,
  `numeric_token_unsourced` always fails the bullet (no soften).
  Default: `false` (soften via §11.5(2) when permissible). Used in
  shadow mode to surface the worst case.
- `CV_ASSEMBLY_DRAFT_LAYER6_SELF_GRADER_ENABLED` — controls whether
  the Layer 6 V2 self-grader runs. Default: `true`. When `false`,
  `layer6_grade_result` is omitted and §18.5 metadata reflects this.
- `MAX_PARALLEL_DRAFT_ASSEMBLIES` — env cap on per-worker concurrency.

### 19.11 Operator-visible success / failure signals

- `level-2.cv_assembly.stage_states.cv.draft_assembly.<n>.status` —
  `pending | leased | completed | failed | deadletter` per draft.
- `level-2.cv_assembly.drafts[n].status` —
  `completed | partial | degraded | failed`.
- `level-2.cv_assembly.draft_assembly_summary.status` (job-wide
  rollup) — `completed | partial | degraded | failed`.
- `cv_assembly_stage_runs` row with `trace_id`, `trace_url`,
  `fail_open_reason` (when present).
- `cv_assembly_alerts` row only on deadletter or two-draft mode
  triggered repeatedly across consecutive jobs.

### 19.12 Downstream consumers

- `cv.grade_select_synthesize` (4.3.5) — claim-time barrier on all
  enqueued draft work items (§17.1).
- `cv.dossier` (4.3.7) — read-only display of `drafts[]` for
  operator audit (§17.3); not used in publishing.
- `cv.publish` (4.3.6) — does **not** consume `drafts[]` directly;
  reads `cv_assembly.synthesis` only.

### 19.13 Rollback strategy

- Toggle `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED=false` → legacy
  single-pass Layer 6 V2 runs against the most recent pattern
  (debug-only); 4.3.5 not invoked; 4.3.6 publishes the legacy
  output.
- Existing `cv_assembly.drafts` documents remain for audit; no
  deletion.
- No schema migration on rollback; `DraftDoc` schema is purely
  additive.

## 20. Tests And Evals

### 20.1 Unit tests (`tests/unit/cv_assembly/`)

- `test_pattern_context_adapter.py` — verifies §10.1 PatternContext
  is constructible from realistic upstream artifacts; freeze
  semantics (immutability); pure (no I/O) under socket / Mongo
  patches.
- `test_pattern_bias_composition.py` — table-driven over §10.2.1
  formula (multiplier inputs/outputs); §10.2.2 allowlist union;
  §10.2.4 forbidden-category derivation; §10.2.5 forbidden phrases;
  §10.2.6 frozen-string lookup; §10.2.8 tie-break order.
- `test_pattern_bias_determinism.py` — two runs over the same
  inputs produce byte-identical `PatternBias` (excluding
  `derivation_trace[]` which is structurally bounded).
- `test_evidence_lineage_validator.py` — one fixture per `rule_id`
  in §12.3; expected `severity` and `suggested_action` per fixture
  (mirrors 4.3.3 §13.6 / 4.3.2 §11.2.6 template).
- `test_evidence_lineage_validator_determinism.py` — two runs over
  the same inputs produce byte-identical
  `EvidenceLineageValidatorReport`; `determinism_hash` matches.
- `test_evidence_lineage_validator_no_io.py` — `validate_lineage()`
  invocation with `socket`, `pymongo`, `open`, and `requests`
  patched to raise; assertion: validator completes without touching
  any of them.
- `test_number_resolution_extraction.py` — table-driven over
  `NUMERIC_TOKEN_RE` (units, separators, suffixes, surface-form
  equivalence per §11.6).
- `test_number_resolution_hierarchy.py` — fixtures for each
  `source_decision` outcome (master_cv_exact, structured_metric,
  metric_band_rendering, unsourced).
- `test_number_resolution_strip_vs_soften.py` — §11.5 decision
  table with grammar-integrity checks after surgical strip.
- `test_metric_band_phrase_table.py` — registered phrases match
  §11.4 canonical table; new phrase additions require schema bump.
- `test_header_validator_consumption.py` — 4.3.4 calls
  `validate_header(mode="draft", pattern=...)` with the correct
  inputs; orders header validator before lineage validator (§13.4).
- `test_failed_draft_isolation.py` — one work item failure does not
  affect sibling work items (§14 I14); Mongo writes per draft are
  independent.

### 20.2 Stage contract tests

- `StageDefinition` lookup returns the registered instance under
  `cv.draft_assembly`; `prerequisites = ("cv.pattern_selection",)`;
  `produces_fields = ("cv_assembly.drafts",)`;
  `task_type == "cv.draft_assembly"`; `lane == "cv_assembly"`;
  `required_for_cv_assembled` is set such that the 4.3.5 barrier
  fires correctly under §8.4 valid-pattern-count permutations.
- Idempotency-key composition matches §7.4.

### 20.3 PatternContext adapter tests

- Construction from realistic upstream artifacts (full preenrich +
  master-CV v2 + pattern_selection + header_blueprint).
- Freeze semantics — `PatternContext` is `@dataclass(frozen=True)`;
  mutation attempt raises.
- Field one-to-one mapping to upstream sources; checksums match
  source artifacts.

### 20.4 PatternBias formula tests

- `dimension_multipliers` formula (§10.2.1) including clamp at
  `[0.25, 4.0]` boundaries.
- `achievement_allowlist` union over all `evidence_map.*` sources
  (§10.2.2); permissive variant matching when allowlist tuple has
  `variant_id=None`.
- `forbidden_proof_categories` derivation (§10.2.4) under
  permutation vs strict-subset `proof_order_override`.
- `forbidden_phrases` substring set (§10.2.5).
- Frozen-string resolution (§10.2.6).
- Tie-break order (§10.2.8) matches 4.3.3 §11.4.

### 20.5 Evidence-lineage validator tests

- Per-rule_id fixture per §12.3.
- Per-action fixture per §12.4.
- Mode-difference fixture: same defect; `mode="draft"` triggers
  repair; `mode="synthesis"` accepts cross-pattern bullets.
- Number-resolution integration with the validator (numeric tokens
  drive `numeric_token_*` rule_ids; correct rule_id per §11.3
  outcome).
- `determinism_hash` byte-stability across two runs.

### 20.6 Header-validator integration tests

- 4.3.4 calls `validate_header(mode="draft", pattern=...)` with
  exact inputs.
- Header validator runs before lineage validator (§13.4).
- Header validator failure → draft `status=failed` (§13.3).

### 20.7 Number-resolution tests

- Token extraction regex coverage (units, separators, magnitudes).
- Surface-form equivalence (§11.6) — `40%` ≡ `40 percent` etc.
- Hierarchy walk (§11.2) — first hit wins.
- Strip vs soften decision (§11.5).
- Header-critical surface fail-closed when no source.
- Interaction with 4.2.6 (downgrade rules drive softening; forbidden
  patterns block band rendering).

### 20.8 Degraded two-draft path tests

- Pattern_3 invalid at claim → only 2 work items enqueued; both
  succeed → `cv_assembly.draft_assembly_summary.status=degraded`.
- Pattern_3 invalid + pattern_2 fails → 1 success only →
  `cv_assembly.status=failed`.

### 20.9 One-draft failure semantics tests

- pattern_2 fails after retries; pattern_1 and pattern_3 succeed →
  `drafts_persisted_count=2`, `drafts_failed_count=1`,
  `summary.status=partial` or `degraded` (per §8.4 ladder).
- failed draft persists with `cv_text=null` and
  `failure_record` populated.

### 20.10 Trace emission tests

Using a `FakeTracer`:

- stage span emitted with §18.4 + §18.5 metadata keys;
- substep spans (§18.2) emitted in correct nesting;
- events `cache.{hit,miss}`, `draft_skipped`, `degraded_to_two_draft_mode`,
  `variant_filtered`, `validator_repair_applied`, `number_stripped`,
  `lineage_failure`, `header_failure`, `draft_persisted` emitted
  with required metadata;
- forbidden keys do not leak (grep assertion on serialized payload —
  no full `cv_text`, no full `cv_struct`, no full `evidence_lineage`,
  no full debug body).

### 20.11 Persistence tests

- Persisted `DraftDoc` matches the §9 schema.
- Compact projection retains only counts (not full
  `evidence_lineage`).
- `cv_assembly.stage_states.cv.draft_assembly.<n>.trace_ref` is
  populated.
- `cv_assembly_stage_runs` has one row per draft with `trace_id`,
  `trace_url`, `prompt_version`, tokens, cost.

### 20.12 Downstream compatibility tests with 4.3.5

- Given a fixture `DraftDoc`, the 4.3.5 grader's rubric inputs
  construct without `KeyError` on any required field.
- `validate_lineage(..., mode="synthesis", pattern=None)` accepts a
  fragment whose achievement is in the union of two patterns'
  `evidence_map`s but absent from any single one.
- `DraftDoc.pattern_signature` matches its source pattern's
  signature (§14 I1).

### 20.13 Regression corpus

`data/eval/validation/cv_assembly_4_3_4_multi_draft/`:

- `cases/<job_id>/input/` — full preenriched `level-2` slice + 4.3.2
  `header_blueprint` + 4.3.3 `pattern_selection` (3 patterns) +
  master-CV snapshot.
- `cases/<job_id>/expected/draft_shapes.json` — expected structural
  invariants per draft (section coverage, role coverage, bullet
  counts per role bounded by `cv_shape_expectations.counts`,
  ai_highlights eligibility).
- `cases/<job_id>/expected/validator_reports.json` — expected
  `EvidenceLineageValidatorReport` per draft (byte-equal asserted
  on `determinism_hash`).
- `cases/<job_id>/expected/header_validator_reports.json` —
  expected `HeaderValidatorReport` per draft.
- `cases/<job_id>/expected/number_resolution_summary.json` —
  expected count of `master_cv_exact`, `structured_metric`,
  `metric_band_rendering`, `repaired_stripped`,
  `repaired_softened_to_band`, `failed_unsourced` per draft.
- `cases/<job_id>/reviewer_sheet.md` — reviewer-facing acceptance
  sheet.

Minimum 15 cases (≥ 3 per major role family); plus adversarial
cases:

- thin evidence (forces aggressive softening),
- AI-heavy JD with `ai_taxonomy.intensity=adjacent` (forces band
  clamps),
- leadership JD with `seniority.managerial_level=ic` cited role
  (forces leadership-claim repair),
- architecture JD with shallow platform evidence,
- numeric-heavy JD where master-CV has bands but no exact figures
  (forces band rendering),
- 4.2.6-rich case with multiple `forbidden_claim_patterns[]` that
  intersect with patterns' picks (forces `soften_per_emphasis_rule`).

### 20.14 Eval metrics

Reviewer rubric, recorded in `reports/`:

- **Evidence-lineage validator pass rate** (target ≥ 0.98 across
  corpus; 100% after repair) — SC2.
- **Header validator pass rate** — SC3.
- **Structural invariant pass rate** (target = 1.00) — SC1, SC4.
- **Cross-draft diversity preservation** (target ≥ 0.85; pattern
  intent survives prose realization) — measured by Jaccard on
  bullet `(role_id, achievement_id, variant_id)` sets across drafts
  of the same job.
- **Title allowlist compliance** (target = 1.00) — SC6.
- **AI-band compliance** (target = 1.00) — SC6.
- **Number-resolution pass rate** (target ≥ 0.99 — `failed_unsourced`
  count per draft ≤ 1).
- **Reviewer usefulness** (target ≥ 0.75 per draft; higher for
  winner) — SC11.
- **Two-draft degraded mode rate** (target ≤ 5% in production;
  tracked).
- **Determinism rate** (target = 1.00) — two consecutive runs over
  identical inputs produce byte-identical `validator_report`s and
  byte-identical `evidence_lineage` (cv_text variation tolerated
  only on advisory `layer6_v2_outputs.layer6_grade_result`).
- **Stage latency p95 per draft** (report only; target < 90 s on
  canary model).

### 20.15 Regression gates

Block rollout if:

- evidence-lineage validator pass rate regresses,
- diversity preservation drops below 0.70,
- title or AI compliance failure appears in any case,
- number-resolution pass rate drops below 0.95,
- reviewer usefulness drops by more than 5 points,
- determinism rate < 1.00,
- two-draft degraded mode rate exceeds 15% in canary.

### 20.16 Live smoke tests

- `scripts/smoke_draft_assembly.py` — loads `.env` from Python,
  fetches one job by `_id`, runs three drafts locally against live
  Codex/LLM, validates outputs, prints heartbeat every 15 s.

## 21. VPS End-To-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This section is the live-run chain.

### 21.1 Local prerequisite tests before touching VPS

- `pytest -k "draft_assembly"` clean.
- `pytest tests/unit/cv_assembly/test_evidence_lineage_validator_determinism.py
  tests/unit/cv_assembly/test_pattern_bias_determinism.py
  tests/unit/cv_assembly/test_number_resolution_extraction.py` clean.
- `python -m scripts.cv_assembly_dry_run --stage draft_assembly
  --job <level2_id> --pattern_id 1 --mock-llm` clean.
- Langfuse sanitizer test green.
- 4.3.2 `validate_header` test suite green (4.3.4 consumes it).
- 4.3.3 pattern_selection eval corpus green (4.3.4 needs valid
  patterns).

### 21.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path;
- verify the deployed `stage_registry.py` contains
  `cv.draft_assembly`:
  `grep -n "cv.draft_assembly" /root/scout-cron/src/cv_assembly/stage_registry.py`,
  `grep -n "CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED"
  /root/scout-cron/src/cv_assembly/config_flags.py`;
- verify
  `/root/scout-cron/src/cv_assembly/validators/evidence_lineage_validator.py`
  exists and exposes `validate_lineage`;
- verify
  `/root/scout-cron/src/cv_assembly/validators/header_validator.py`
  exists (4.3.2) and exposes `validate_header`;
- verify `pattern_context.py` exists and exports
  `build_pattern_context` and `derive_pattern_bias`;
- verify `policies/number_resolution.py` registers
  `METRIC_BAND_PHRASES`;
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`;
- deployment is file-synced; do not `git status`.

### 21.3 Target job selection

- Pick a real `cv_assembling` `level-2` job with:
  - `cv_assembly.pattern_selection.status ∈ {completed, partial}`
    AND `patterns[]` length ≥ 2 with valid statuses,
  - `cv_assembly.header_blueprint.status ∈ {completed, partial}`,
  - all five `presentation_contract` subdocuments present,
  - `master-CV` v2 inputs load cleanly.
- Prefer a mid-seniority IC or EM role with rich research, populated
  pools, and three valid patterns.
- Record `_id`, `jd_checksum`, `pattern_selection_checksum`,
  `header_blueprint_checksum`, current `input_snapshot_id`.
- Optionally pick a second job with two valid patterns to exercise
  §8.4 degraded path.

### 21.4 Upstream artifact verification

Before launching:

- verify `cv_assembly.pattern_selection.patterns[]` has ≥ 2 entries
  with `pattern_status != failed`;
- verify `cv_assembly.header_blueprint` is non-empty with all
  pools and viability bands populated;
- verify `presentation_contract` subdocuments persisted;
- verify master-CV v2 loader returns no schema errors:
  `python -m src.cv_assembly.cli check_master_cv_v2 --candidate
  $CANDIDATE_ID`.

If any verification fails, choose a different job — do not
mutate `work_items` or `level-2.cv_assembly.*` directly to make
verification pass. Re-run upstream stages via the proper enqueue
path:

- `scripts/recompute_snapshot_id.py --job <_id>` then
- `scripts/enqueue_stage.py --stage cv.pattern_selection --job <_id>`
  (re-runs 4.3.3) or
- `scripts/enqueue_stage.py --stage cv.header_blueprint --job <_id>`
  (re-runs 4.3.2).

### 21.5 Single-stage run path (fast path) — preferred

Preferred for diagnosing 4.3.4 in isolation. A wrapper in
`/tmp/run_draft_assembly_<job>_<pattern_id>.py`:

- `from dotenv import load_dotenv; load_dotenv("/root/scout-cron/.env")`,
- reads `MONGODB_URI`,
- builds `StageContext` via the worker-compatible factory
  (`build_cv_assembly_stage_context_for_job`),
- runs `DraftAssemblyStage().run(ctx, pattern_id=<n>)` directly,
- prints a heartbeat line every 15 s during LLM work with: wall
  clock, elapsed, last substep (`context_build`, `prompt_build`,
  `llm_call.primary`, `variant_selection`, `role_generation`,
  `stitching`, `header_prose`, `header_validate`, `lineage_validate`,
  `repair`, `persist`), Codex PID, Codex stdout/stderr tail.

Launch (one terminal per pattern when running all three sequentially
for diagnostic clarity; or parallel if confidence is high):

```
nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_draft_assembly_<job>_1.py \
  > /tmp/draft_assembly_<job>_1.log 2>&1 &

nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_draft_assembly_<job>_2.py \
  > /tmp/draft_assembly_<job>_2.log 2>&1 &

nohup /root/scout-cron/.venv/bin/python -u \
  /tmp/run_draft_assembly_<job>_3.py \
  > /tmp/draft_assembly_<job>_3.log 2>&1 &
```

### 21.6 Full-chain path (fallback)

If the fast path is blocked by `StageContext` construction drift or
if you need to validate the fan-out behavior end-to-end:

- enqueue three `work_items` for `cv.draft_assembly` (one per
  pattern_id) via `scripts/enqueue_stage.py --stage cv.draft_assembly
  --job <_id> --pattern_id {1,2,3}`,
- start the cv_assembly worker with
  `CV_ASSEMBLY_STAGE_ALLOWLIST="cv.draft_assembly"`
  and `MAX_PARALLEL_DRAFT_ASSEMBLIES=3`,
- same `.venv`, `python -u`, Python-side `.env`, `MONGODB_URI`
  discipline,
- same operator heartbeat from the worker's structured logger.

When a 4.3.3 + 4.3.4 chain run is needed (e.g., after pattern
selection re-run):

- enqueue `cv.pattern_selection` first with `--block-until-complete`,
- then enqueue the three `cv.draft_assembly` work items.

### 21.7 Required launcher behavior

- `.venv` activated (absolute path to `.venv/bin/python`),
- `python -u` unbuffered,
- `.env` loaded from Python, not `source .env`,
- `MONGODB_URI` present,
- inner Codex PID and first 128 chars of stdout / stderr logged on
  every heartbeat,
- isolated workdir
  `/tmp/cv-draft-assembly-<job>-<pattern_id>/` for any inner Codex
  subprocess (per operational manual §"Failure 9"; the stage uses
  Codex inside Layer 6 V2 calls).

### 21.8 Heartbeat requirements

- stage-level heartbeat every 15-30 s from the wrapper;
- lease heartbeat every 60 s by the worker;
- silence > 90 s = stuck-run flag.

### 21.9 Expected Mongo writes

On success per draft:

- `cv_assembly.drafts` collection: one doc keyed by
  `(level2_id, input_snapshot_id, pattern_id, prompt_version)`;
- `level-2.cv_assembly.drafts[<pattern_id - 1>]`: populated with the
  persisted `DraftDoc` (or compact projection per §19.3);
- `level-2.cv_assembly.stage_states.cv.draft_assembly.<pattern_id>`:
  `status=completed | partial | degraded`,
  `attempt_count`, `lease_owner` cleared,
  `trace_id`, `trace_url`,
  `validator_report.status`,
  `header_validator_report.status`;
- `cv_assembly_stage_runs`: one row per draft with `status`,
  `trace_id`, `trace_url`, `provider_used`, `model_used`,
  `prompt_version`, tokens, cost, validator counts;
- `work_items`: this row `status=completed`.

After the last draft completes, the sweeper rolls up:

- `level-2.cv_assembly.draft_assembly_summary` —
  `{drafts_persisted_count, drafts_failed_count, degraded_mode,
  status, trace_refs[]}`;
- `cv_assembly_job_runs`: aggregate updated;
- on rollup `status ∈ {completed, partial, degraded}` with
  `drafts_persisted_count ≥ 2`, one
  `cv.grade_select_synthesize` work item enqueued.

### 21.10 Expected Langfuse traces

In the same trace (`scout.cv.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- One `scout.cv_assembly.draft_assembly` stage span per draft work
  item (so up to 3 sibling stage spans), each with §18.4 / §18.5
  metadata.
- Per stage span, the substep spans listed in §18.2 (only those
  that fired).
- Per stage span, events from §18.3 (only those that fired).
- Canonical lifecycle events from the 4.3 umbrella.

A correctly-running job produces:

- 3 `draft_persisted` events (or 2 in degraded mode),
- 0 `lineage_failure` / `header_failure` events,
- 1 `degraded_to_two_draft_mode` event when applicable,
- N `validator_repair_applied` events (N small; healthy
  distribution).

### 21.11 Stuck-run operator checks

If no heartbeat for > 90 s for any pattern_id:

- tail `/tmp/draft_assembly_<job>_<pattern_id>.log`,
- inspect launcher PID,
- inspect Mongo:
  `level-2.cv_assembly.stage_states.cv.draft_assembly.<pattern_id>.lease_expires_at`,
- if lease is expiring and no progress, kill the launcher; wait for
  the prior PID to be confirmed gone before restarting.

Silence is not progress. When one pattern is stuck and others are
progressing, restart only the stuck pattern's launcher.

### 21.12 Acceptance criteria

- log per pattern ends with
  `DRAFT_ASSEMBLY_RUN_OK job=<id> pattern=<n> status=<status>
  trace=<url>`;
- Mongo writes match §21.9 for each persisted draft;
- Langfuse traces match §21.10;
- per-draft output validates against `DraftDoc` schema (§9);
- spot-check: every realized bullet's `source.achievement_id`
  resolves in master-CV; every realized header pool reference
  resolves in `header_blueprint`; every numeric token in
  `cv_struct.experience[].bullets[].number_resolution_log`
  has `outcome ∈ {passed_*, repaired_stripped,
  repaired_softened_to_band}`; `cv_struct.header.title_string ==
  header_blueprint.identity.chosen_title` exactly;
- two-draft mode run (when applicable) returns
  `summary.status=degraded` with
  `degraded_mode=true` and 2 persisted drafts;
- failed-draft run (when applicable) returns the failed draft as
  `status=failed` with `failure_record` populated, and sibling
  drafts unaffected.

### 21.13 Artifact / log / report capture

Create `reports/draft-assembly/<job_id>/` containing:

- `run_pattern_<n>.log` — full stdout/stderr per pattern,
- `draft_pattern_<n>.json` — emitted `DraftDoc`,
- `validator_report_pattern_<n>.json` — `EvidenceLineageValidatorReport`,
- `header_validator_report_pattern_<n>.json` — 4.3.2 validator output,
- `number_resolution_log_pattern_<n>.json` —
  `cv_struct.experience[].bullets[].number_resolution_log[]`
  collated for review,
- `trace_url_pattern_<n>.txt` — Langfuse URL,
- `stage_runs_pattern_<n>.json` — `cv_assembly_stage_runs` row,
- `summary.json` — `cv_assembly.draft_assembly_summary`,
- `mongo_writes.md` — human summary of §21.9 checks,
- `acceptance.md` — pass/fail list for §21.12.

## 22. Open-Questions Triage

Items resolved in this revision are marked **(resolved)** with the
section that implements the resolution. Deferred items remain v1
recommendations subject to re-bench.

| Question | Triage | Resolution-or-recommendation |
|---|---|---|
| Should cover letters be generated per draft or only for the winner? | must-resolve | **(resolved)** — Cover letters are generated **only for the winner**, in 4.3.5 after synthesis. Rationale: per-draft cover letters at v1 cost ≈ 3× the LLM spend without evidence of grade impact, and risk identity drift across letters. The cover-letter prompt is owned by `src/layer6_v2/cover_letter_generator.py` (preserved). 4.3.5 invokes it once with `synthesis.final_cv_struct + header_blueprint` as inputs. Revisit only if 4.3.8 eval shows per-draft letters meaningfully shift winner selection (unlikely given 4.3.5 grades the CV, not the letter). |
| Should the cost cap be per-draft or per-job? | must-resolve | **(resolved)** — **Per-job ceiling** applied through the 4.3.8 cost breaker (`CV_ASSEMBLY_PER_JOB_COST_USD_CEILING`), with a **per-draft soft budget** (`CV_ASSEMBLY_PER_DRAFT_COST_USD_SOFT`) that triggers `unified_llm.py` tier downgrade to baseline model on the next phase boundary inside that draft. Per-draft hard caps would create cross-draft asymmetry (one draft runs cheap-only, others run primary) and break diversity invariants from 4.3.3. Per-job ceiling is enforced before claiming the next draft work item; if cumulative cost exceeds the ceiling, remaining work items are marked `failed` with `failure_kind=cost_breaker`. |
| Should all three drafts share a single prompt cache to save cost? | safe-to-defer | v1: **cold per draft** for diversity. Each draft sees a fresh prompt with its `pattern_id`-specific bias projection; warm caching across drafts could allow one pattern's bias to leak into another's first-token logits in a way that's hard to reason about. Post-rollout optimization: revisit after cost telemetry shows >20% of total CV-assembly cost is in repeated prompt prefixes. If so, cache the **invariant prefix** (`master_cv` summaries, presentation contract) only, keyed on `master_cv_checksum + presentation_contract_checksum`; never cache pattern-specific suffixes. |
| Should the Layer 6 V2 self-grader run per draft or be skipped? | safe-to-defer | v1: **runs per draft** when healthy; recorded as advisory only. The self-grade is sometimes useful for operator audit ("why did Layer 6 V2 think draft 2 was strong?"). When the self-grader is unhealthy, draft proceeds without it. After 4.3.5 demonstrates the rubric is dominant, consider toggling self-grader off in production via `CV_ASSEMBLY_DRAFT_LAYER6_SELF_GRADER_ENABLED=false` to save cost. |
| Should `stitcher.py` dedup honor pattern's dimension weight overrides? | safe-to-defer | v1: **dedup global**. Today the stitcher deduplicates achievements globally across role bullets to avoid the same impact appearing twice. Pattern-aware dedup (e.g., a `leadership_led` pattern preferring leadership-bullet collisions to architecture-bullet collisions) is appealing but adds a second emphasis surface that competes with `pattern_bias.dimension_multipliers`. Keep dedup global; revisit only if 4.3.5 grader reports dedup as a confound (e.g., two drafts producing systematically near-identical bullet sets). |
| Should the `derived_markers` registry be per-job or candidate-global? | safe-to-defer | v1: **candidate-global**. Derived markers compose master-CV fragments; the composition rules are functions of master-CV shape, not JD shape. Adding job-specific derived markers would couple 4.3.4 to JD reasoning in a way that 4.3.3 already owns. Revisit if the eval corpus shows recurring per-job composition needs that don't fit existing rules. |
| Should `number_resolution_log` be collapsed in the compact projection? | safe-to-defer | v1: **counts only in compact projection** (`number_stripped_count`, `number_softened_count`, `number_unsourced_count`). Full token-by-token log lives in `debug_context`. Revisit if dossier UX shows reviewers need per-token detail for audit. |
| Is the metric_band rendering whitelist (§11.4) too restrictive? | safe-to-defer | v1: **5 bands × ~3 phrases = 15 registered phrases**. Restrictive on purpose: every phrase has been reviewed for truth-band alignment. If the eval corpus shows excessive softening to the same phrase (e.g., "substantial" appearing in 80% of drafts), broaden the table by adding 2–3 additional phrases per band, each with explicit ladder ordering. Schema bump required. |

## 23. Primary Source Surfaces

- `plans/iteration-4.3-candidate-evidence-assembly-grading-and-publishing.md`
- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`
- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
- `plans/iteration-4.3.3-cv-pattern-selection-and-evidence-mapping.md`
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `docs/current/missing.md`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md` (Part 5, Part 6)
- `src/layer6_v2/orchestrator.py`
- `src/layer6_v2/role_generator.py`
- `src/layer6_v2/variant_selector.py`
- `src/layer6_v2/variant_parser.py`
- `src/layer6_v2/stitcher.py`
- `src/layer6_v2/header_generator.py`
- `src/layer6_v2/grader.py`
- `src/layer6_v2/improver.py`
- `src/layer6_v2/cv_loader.py`
- `src/layer6_v2/types.py`
- `src/layer6_v2/role_qa.py`
- `src/layer6_v2/ats_checker.py`
- `src/layer6_v2/cv_tailorer.py`
- `src/layer6_v2/keyword_placement.py`
- `src/layer6_v2/cover_letter_generator.py`
- `src/common/unified_llm.py`
- `src/common/llm_config.py`
- `src/preenrich/blueprint_models.py` (canonical enums)
- `src/cv_assembly/validators/header_validator.py` (4.3.2 — consumed
  here)
- `src/cv_assembly/validators/pattern_validator.py` (4.3.3 — pattern
  consumption sanity check available in `mode="draft_consumption"`)

## 24. Implementation Targets

- `src/cv_assembly/stages/draft_assembly.py` (new) — work-item
  worker entrypoint; builds `PatternContext`, calls Layer 6 V2,
  runs both validators, persists `DraftDoc`. One entrypoint
  function `DraftAssemblyStage.run(ctx, pattern_id) -> DraftDoc`.
- `src/cv_assembly/pattern_context.py` (new) — `PatternContext`
  dataclass, `build_pattern_context()`, `derive_pattern_bias()`,
  `PatternBias` dataclass. Pure functions; no I/O.
- `src/cv_assembly/policies/number_resolution.py` (new) —
  `NUMERIC_TOKEN_RE`, `METRIC_BAND_PHRASES`,
  `resolve_numeric_token(token, bullet, master_cv) -> NumericTokenObservation`,
  `decide_strip_or_soften(observation, bullet) -> RepairDecision`.
  Pure functions.
- `src/cv_assembly/validators/evidence_lineage_validator.py` (new) —
  §12 `validate_lineage()` entrypoint plus per-rule check functions.
  Pure; no I/O.
- `src/cv_assembly/derived_markers/registry.py` (new) — registered
  derived-marker rules with composition signatures.
- `src/cv_assembly/models.py` — add `DraftDoc`, `EvidenceLineageDoc`,
  `EvidenceLineageValidatorReport`, `DraftAssemblyDebug`,
  `DraftFailureRecord`, `NumericTokenObservation`,
  `NumberResolutionLogEntry`, `PatternBias`, `PatternContext`
  (TYPE_CHECKING re-export), `DRAFT_SCHEMA_VERSION`,
  `VALIDATOR_REPORT_SCHEMA_VERSION` constants.
- `src/cv_assembly/stage_registry.py` — register
  `cv.draft_assembly`; prereq `cv.pattern_selection`;
  `lane=cv_assembly`; `max_attempts=3`; barrier rule for 4.3.5
  expressed as "claim when all three (or two) draft work items
  are terminal AND ≥ 2 are non-failed".
- `src/cv_assembly/dag.py` — fan-out edge `cv.pattern_selection →
  cv.draft_assembly` (1..3 work items per `pattern_id`); barrier
  edge `cv.draft_assembly → cv.grade_select_synthesize`.
- `src/cv_assembly/config_flags.py` —
  `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED`,
  `CV_ASSEMBLY_DRAFT_NUMBER_RESOLUTION_STRICT`,
  `CV_ASSEMBLY_DRAFT_LAYER6_SELF_GRADER_ENABLED`,
  `MAX_PARALLEL_DRAFT_ASSEMBLIES`,
  `CV_ASSEMBLY_PER_JOB_COST_USD_CEILING` (read here; enforced
  cross-stage by 4.3.8),
  `CV_ASSEMBLY_PER_DRAFT_COST_USD_SOFT`.
- `src/cv_assembly/tracing.py` — register stage span and substep
  spans (§18), enforce `_sanitize_langfuse_payload` on previews,
  cap `number_stripped` events at 50 with overflow event.
- `src/cv_assembly/sweepers.py` — `draft_assembly_summary` rollup
  computation; 4.3.5 enqueue trigger when ≥ 2 drafts persisted.
- `src/layer6_v2/orchestrator.py` — accept
  `pattern_context: Optional[PatternContext]`; when supplied,
  thread it through `_generate_all_role_bullets()` and
  `_run_header_phase()` without changing legacy behavior. The
  orchestrator's existing single-pass mode is preserved as the
  fallback when `pattern_context is None`.
- `src/layer6_v2/variant_selector.py` — accept
  `pattern_bias: Optional[PatternBias]`; when supplied,
  deterministically multiply scores by `pattern_bias.dimension_multipliers`,
  filter by `achievement_allowlist`, drop variants whose
  `proof_categories ∩ forbidden_proof_categories` is non-empty,
  apply tie-break per §10.2.8.
- `src/layer6_v2/stitcher.py` — extend `StitchedCV` with per-bullet
  `source` metadata: `(role_id, achievement_id, variant_id?,
  proof_category, dimension, scope_band, metric_band,
  ai_relevance_band, source_fragment_ref)`. Existing dedup unchanged
  (per §22).
- `src/layer6_v2/header_generator.py` — blueprint-first path from
  4.3.2 (§7.5 stage owns this; 4.3.4 only consumes).
- `src/layer6_v2/role_generator.py` — read `pattern_context.pattern_bias`
  for per-role emphasis hints; do not introduce new picks; bullets
  outside the allowlist are filtered before LLM prompting.
- `scripts/benchmark_multi_draft_4_3_4.py` (new) — eval harness over
  §20.13 corpus.
- `scripts/smoke_draft_assembly.py` (new) — single-job live smoke
  per §20.16.
- `scripts/vps_run_draft_assembly.py` (new) — VPS wrapper template
  per §21.5.
- `data/eval/validation/cv_assembly_4_3_4_multi_draft/` (new) —
  15-case corpus per §20.13.
- `tests/unit/cv_assembly/` — test files per §20.1, §20.4, §20.5,
  §20.6, §20.7, §20.10, §20.11, §20.12.
- `docs/current/architecture.md` — add §"Iteration 4.3.4 Draft
  Assembly".
- `docs/current/missing.md` — strike out the §6340–6348 4.3.4 gap
  entries and reference this plan as the resolution.
