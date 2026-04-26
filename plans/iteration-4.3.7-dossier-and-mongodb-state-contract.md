# Iteration 4.3.7 Plan: Dossier and MongoDB `level-2` State Contract

## 1. Executive Summary

4.3.7 is the **state and consumer contract** for the candidate-aware
4.3 lane. It is the plan that keeps the dossier, MongoDB `level-2`,
the publisher (4.3.6), the dashboards, the per-job detail APIs, and
every legacy reader talking about the same job in the same vocabulary
— before, during, and after rollout.

Concretely, 4.3.7 owns four surfaces:

1. The **canonical `cv_assembly.*` schema on `level-2`** — what is
   canonical, what is projected, and what must never move.
2. The **`cv_assembly.dossier_state` subdoc** — section-by-section
   dossier health, evidence-map provenance, and the explicit fallback
   path through `best_effort_dossier.py`.
3. The **compatibility projection module** —
   `src/cv_assembly/compat/projection.py::project_cv_assembly_to_level2`,
   the *only* writer of legacy `level-2` root publisher fields when
   the 4.3 lane is on, called by 4.3.6's finalizer in the same
   atomic update that performs the `published` CAS.
4. The **dossier section validator** —
   `src/cv_assembly/validators/dossier_validator.py::validate_dossier`,
   a deterministic, no-LLM, one-pass repair surface that 4.3.7 owns
   and that 4.3.6's render path must call before persisting
   `dossier_state.body_*`.

Everything else flows from those four surfaces: the `status_breakdown`
rollup, the lifecycle categories the dashboards use, the per-job
detail view, the new compound indexes, the migration plan for the
discriminator that distinguishes legacy and 4.3 jobs, and the Langfuse
metadata that operators read to debug a partial publish.

4.3.7 is not a work-item stage. No new lane, no new task type, no new
collection. `level-2` remains authoritative. `pre_enrichment.*` is
never mutated by 4.3. The projection module is a pure function. The
validator is deterministic. Both are consumed by stages owned by
other plans (4.3.4 lineage, 4.3.5 synthesis, 4.3.6 publish, 4.3.7
dossier-section repair invoked by 4.3.6's render path).

This revision closes every `missing.md` gap for 4.3.7: hard
prerequisites, projection module API, dossier validator API, frontend
backward-compat semantics, index migration plan, formalized
partial-completion rollup, downstream-consumer contracts, expanded
observability, VPS validation, and a triaged open-question table.

## 2. Mission

Make every MongoDB reader, every dashboard, every projection, and the
dossier itself coherent with the 4.3 candidate-aware lane — through a
single canonical subtree on `level-2.cv_assembly.*`, a pure
compatibility projection that never fabricates state for legacy
readers, a deterministic dossier section validator that bounds the
fallback path, and a formalized partial-completion rollup that
distinguishes degraded outcomes from failures so an operator can
diagnose any half-published job in one read.

## 3. Objectives

O1. Lock the **canonical `cv_assembly.*` schema** on `level-2`,
    including `dossier_state`, `status`, `status_breakdown`, the
    `legacy` discriminator, and the hard rule that
    `pre_enrichment.*` is never mutated by 4.3 (§8).
O2. Specify a **Hard Prerequisites** section binding 4.3.7-owned
    operations (dossier validation, dossier-state writes, projection
    writes, rollup computation) to the upstream `cv_assembly.*` state
    they require, including the synthesis-degraded vs winner-grade
    threshold rule (§9).
O3. Extend `DossierGenerator` to consume the 4.3 evidence map when
    available, and to degrade per-section through `best_effort_dossier`
    when the evidence-lineage validator rejects a section (§10).
O4. Ship `validate_dossier()` — a deterministic, no-LLM, one-pass,
    section-level dossier validator with a precise report shape and a
    bounded set of repair actions (§11).
O5. Ship `project_cv_assembly_to_level2()` — a pure, deterministic,
    idempotent compatibility projection with an enumerated return
    shape, no Mongo side-effects, and a single canonical caller-list
    (§12).
O6. Specify the **frontend backward-compat semantics** during rollout:
    explicit `cv_assembly.legacy=true` discriminator, default
    "show non-legacy only" with operator toggle, and per-job detail
    view contract (§13).
O7. Ship the **index / migration plan** for new compound indexes on
    `level-2.cv_assembly.*`, with rolling-build strategy on the live
    Atlas replica set (§14).
O8. Formalize **partial-completion rollup** as a deterministic table
    over child statuses, with worked examples for `cv_assembling`,
    `cv_assembled`, `publishing`, `published`, `delivered` (§15).
O9. State **downstream consumer contracts** explicitly so 4.3.6,
    dashboards, per-job detail APIs, dossier exporters, and audit
    tooling all share the same canonical / fallback / forbidden
    surfaces (§19).
O10. Specify the **observability contract** for 4.3.7-owned reads and
     writes — which existing stage spans own them, what subspans/events
     are required, and what is forbidden in Langfuse vs allowed in
     `debug_context` (§21).
O11. Ship the eval corpus under
     `data/eval/validation/cv_assembly_4_3_7_state/`, including
     projection determinism, validator determinism, mixed-mode
     reader, and rollup-table cases (§22).
O12. Validate end-to-end on the VPS against a real eligible job per
     §23 before flipping `CV_ASSEMBLY_DOSSIER_V2_ENABLED=true`.
O13. Preserve disclosure coherence across canonical and projected
     state: public legacy fields and per-job detail views must never
     expose metadata that 4.3.1/4.3.2 marked non-public or
     region-specific-only (§8, §12, §19).

## 4. Success Criteria

4.3.7 is done when, in production, all of the following hold:

SC1. Every `cv_assembled`+ job either carries a populated
     `cv_assembly.dossier_state` with `source ∈ {evidence_map,
     best_effort_fallback, partial, missing}`, or is explicitly
     marked `cv_assembly.legacy=true`.
SC2. Every legacy `level-2` root publisher field listed in 4.3.6
     §10.1 (`cv_text`, `cv_path`, `cv_reasoning`, `generated_dossier`,
     `cover_letter`, `fit_score`, `fit_rationale`,
     `selected_star_ids`, `drive_folder_url`, `sheet_row_id`,
     `gdrive_uploaded_at`, `dossier_gdrive_uploaded_at`,
     `total_cost_usd`, `token_usage`, `pipeline_runs`, `status`,
     `pipeline_run_at`, the four pain-projection arrays,
     `company_summary`, `extracted_jd`, `primary_contacts`,
     `secondary_contacts`) is populated by
     `project_cv_assembly_to_level2()` and survives byte-equality
     against the eval corpus across releases.
SC3. The compatibility projection is **pure** (no Mongo writes
     inside the function), **idempotent** (re-applying produces the
     same dict), and **null-preserving** (missing canonical state
     never overwrites a present legacy field with `None`); asserted
     by §22 unit tests and the regression gate in §22.7.
SC4. `validate_dossier()` is byte-deterministic for fixed
     `(dossier_state_doc, blueprint, winner_draft, master_cv)`;
     asserted by `tests/unit/cv_assembly/test_dossier_validator_
     determinism.py` (§22.1).
SC5. `cv_assembly.status` and `status_breakdown` are computed from
     the deterministic rollup table in §15 — *not* from ad-hoc per-
     reader logic; asserted by the rollup eval cases.
SC6. The frontend renders mixed legacy and 4.3 jobs without flicker:
     legacy jobs (`cv_assembly.legacy=true` or `cv_assembly` absent)
     route to the legacy dashboard cards; 4.3 jobs route to the new
     cards; default toggle hides legacy jobs from 4.3 counters.
SC7. New compound indexes are present on the live replica set, were
     built in background mode, and queries used by §13.1 dashboards
     resolve without `COLLSCAN`; asserted by §14.4 index-adoption
     check.
SC8. A degraded dossier (one or more sections at `status=degraded`
     with explicit fallback) is distinguishable in the operator UI
     from a failed CV; asserted by §22 fault-case rendering tests.
SC9. VPS smoke pass (§23) completed on a real eligible job with
     artifacts captured under `reports/cv-assembly-state/<job_id>/`.
SC10. Langfuse traces for any `cv_assembled` job include the
      4.3.7-owned subspans (`...dossier_validate`,
      `...projection_write`, `...rollup_compute`) under their parent
      stage spans; asserted by §22 trace-emission tests.
SC11. Per-job detail APIs and compatibility projections never leak
      candidate metadata that is redacted by 4.3.1
      `candidate_facts.display_policy` or 4.3.2
      `header_surface_policy`; asserted by §22 mixed-mode reader
      tests.

## 5. Non-Goals

- **Moving `level-2` authority elsewhere.** `level-2` remains the
  authoritative document for both preenrich and 4.3 state.
- **Introducing a new Mongo collection for candidate-aware outputs.**
  v1 keeps `cv_assembly.*` inline. A separate collection is a
  follow-up only if the document approaches 1MB; current expected
  size is < 200KB per job.
- **Replacing `DossierGenerator`'s 10-section template.**
  Pain→Proof→Plan / Job Summary / Pain Points / Role Research /
  STAR / Company / Fit / People & Outreach / Cover Letter /
  Metadata is preserved.
- **Removing the `best_effort_dossier.py` fallback.** It remains as
  the per-section degraded path under §10.2.
- **Generating dossier prose inside 4.3.7.** Dossier rendering and
  upload are 4.3.6's job; 4.3.7 owns the body bytes
  (`dossier_state.body_*`) and the validator that gates them.
- **Mutating `pre_enrichment.*`.** 4.3.7 reads only.
- **Adding a separate control plane.** Mongo + work_items + stage-
  run records remain the operational control plane; Langfuse remains
  the observability sink, not the orchestration plane.
- **Backfilling historical pre-4.3 jobs.** Legacy jobs keep their
  legacy fields and never grow a `cv_assembly.*` subtree; the
  `cv_assembly.legacy=true` discriminator is added by
  `scripts/mark_legacy_cv_ready.py` so dashboards can filter them.
- **Changing the Google Sheets schema.** That is 4.3.6 §15.
- **Replacing the publisher.** 4.3.6 still runs render and upload;
  4.3.7 only defines the bytes the publisher consumes and the
  legacy fields the finalizer projects.

## 6. Why This Artifact Exists

Three forces create this plan:

1. **Document growth.** The 4.3 lane adds drafts, grades, synthesis,
   per-surface publish state, and dossier state to `level-2`.
   Without a clean canonical subtree (`cv_assembly.*`), these
   additions pollute the top level and collide with legacy publisher
   fields. Without an explicit projection module, every reader has
   to know which fields are canonical and which are derived.
2. **Dossier drift.** Today the dossier can be produced from
   `DossierGenerator` (full path) or `best_effort_dossier.py`
   (fallback). After 4.3, the dossier must reflect the **same**
   evidence that produced the winning CV — not an independent
   re-derivation. Without 4.3.7, the published CV and the published
   dossier could tell different stories. The validator-driven
   per-section degradation closes that gap.
3. **Partial-completion visibility.** Multi-surface publish (CV
   render, dossier render, Drive CV, Drive dossier, Sheets) has
   per-surface states. A dashboard that collapses "published=true"
   hides a failing Sheets write or a degraded dossier. Without a
   formalized rollup, every dashboard re-invents partial-completion
   semantics, and operators see contradictory states across surfaces.

A fourth concern is *consumer coherence*. 4.3.6 needs to know what
projection rule to apply atomically with the `published` CAS.
Dashboards need to know which jobs are 4.3-shaped. Per-job APIs need
to know what the canonical fields are vs the projected ones. The
debug tooling needs a dossier validator report it can render. Every
one of those consumers calls into surfaces 4.3.7 owns.

## 7. Boundary and Ownership

### 7.1 4.3.7 is not a work-item stage

There is no `cv.dossier_state` task type, no `publish.projection_write`
task type, and no new lane. 4.3.7 defines:

- A **schema** on `level-2.cv_assembly.*` (§8).
- A **pure function** (the projection module, §12) called from the
  4.3.6 finalizer.
- A **deterministic validator** (the dossier section validator, §11)
  called from the 4.3.6 dossier-render preflight and from any
  re-validation path.
- A **deterministic rollup function** (§15) called by readers that
  need `cv_assembly.status` / `status_breakdown` derived state.
- An extended `DossierGenerator` invocation contract (§10) consumed
  by 4.3.6's `publish.render.dossier` task.

Execution of dossier rendering and upload still occurs through 4.3.6.
4.3.7 defines the contract those consumers must honor.

### 7.2 Ownership chain (single source of truth)

| Concern | Owned by | Defined in |
|---------|----------|------------|
| Canonical `cv_assembly.*` subtree on `level-2` | 4.3.7 | §8 |
| Dossier evidence map → dossier body bytes | 4.3.7 | §10, §11 |
| Dossier section validator | 4.3.7 | §11 |
| Compatibility projection rule (`cv_assembly.*` → legacy `level-2` root) | 4.3.7 | §12 |
| `cv_assembly.status` / `status_breakdown` rollup | 4.3.7 | §15 |
| `cv_assembly.legacy` discriminator | 4.3.7 | §8.5 |
| Compatibility projection **write** (atomic with `published` CAS) | 4.3.6 | 4.3.6 §10.2 |
| Dossier render artifact and upload outcome | 4.3.6 | 4.3.6 §11 |
| `cv_assembly.dossier_state.body_*` bytes | 4.3.7 | §10 |
| `cv_assembly.synthesis.*` / `cv_assembly.winner.*` | 4.3.5 | 4.3.5 §9 |
| `cv_assembly.publish_state.*` | 4.3.6 | 4.3.6 §11 |
| `cv_assembly.header_blueprint.*` | 4.3.2 | 4.3.2 §9 |
| `cv_assembly.pattern_selection.*` | 4.3.3 | 4.3.3 §9 |
| `cv_assembly.drafts[]` | 4.3.4 | 4.3.4 §9 |
| `cv_assembly.grades[]` | 4.3.5 | 4.3.5 §9 |
| `pre_enrichment.*` | 4.x preenrich | 4.x |

Implications:

- 4.3.7 may not write `cv_assembly.synthesis.*`,
  `cv_assembly.winner.*`, `cv_assembly.publish_state.*`,
  `cv_assembly.drafts[]`, or `cv_assembly.grades[]`.
- 4.3.7 may write `cv_assembly.dossier_state.body_*`,
  `cv_assembly.dossier_state.sections[]`,
  `cv_assembly.dossier_state.validator_report`,
  `cv_assembly.status`, `cv_assembly.status_breakdown`, and
  `cv_assembly.legacy` — but only via the contracts in §10–§15.
- 4.3.7 never mutates `pre_enrichment.*`, full stop.
- The compatibility projection write is *invoked from* 4.3.6's
  finalizer, but the projection *rule* is owned by 4.3.7. If 4.3.7
  changes the rule, 4.3.6 picks it up automatically by re-importing
  the module.

## 8. Canonical `cv_assembly.*` Schema On `level-2`

### 8.1 Subtree shape and ownership rules

The umbrella plan §8.5 declares the top-level shape; this plan fills
in 4.3.7's specific subdocs and their relationship to peers.

```text
level-2.cv_assembly {
  schema_version,                      # "4.3.7.1" — bumped here
  input_snapshot_id,                   # 4.3.4-set; 4.3.7 reads only
  master_cv_checksum,                  # set by header_blueprint stage; 4.3.7 reads only
  presentation_contract_checksum,      # same
  legacy: bool,                        # 4.3.7-owned (§8.5)

  header_blueprint { ... },            # 4.3.2-owned
  pattern_selection { ... },           # 4.3.3-owned
  drafts [ { ... } x3 ],               # 4.3.4-owned
  grades [ { ... } x3 ],               # 4.3.5-owned
  winner { ... },                      # 4.3.5-owned
  synthesis { ... },                   # 4.3.5-owned

  publish_state { ... },               # 4.3.6-owned
  dossier_state { ... },               # 4.3.7-owned (§8.2)

  status,                              # 4.3.7-owned rollup (§8.4)
  status_breakdown { ... },            # 4.3.7-owned rollup (§8.4)

  assembled_at,                        # 4.3.5 CAS
  published_at,                        # 4.3.6 CAS
  delivered_at,                        # 4.3.6 CAS

  total_cost_usd,                      # 4.3.8-rolled (read-only here)
  timing_breakdown { ... }             # 4.3.8-owned
}
```

Three rules govern the subtree:

1. **`cv_assembly.*` is canonical for 4.3 state.** No 4.3 outcome
   may be sourced from anywhere else.
2. **`pre_enrichment.*` is read-only for 4.3.** Every 4.3 stage,
   including 4.3.7's projection and validator, may *read*
   `pre_enrichment.*` but may never write it.
3. **Legacy `level-2` root publisher fields are derived, not
   canonical, when `cv_assembly_source=True`.** They are written by
   the 4.3.6 finalizer via the projection module (§12). They are
   read by legacy consumers but must never be the source of truth
   when canonical `cv_assembly.*` exists.
4. **Disclosure policy survives projection.** Compatibility
   projection may flatten canonical 4.3 state into legacy fields, but
   it may not broaden the disclosure envelope. Any field redacted by
   4.3.1/4.3.2 remains redacted in legacy roots, dashboards, and
   per-job detail APIs.

### 8.2 `cv_assembly.dossier_state`

```text
DossierStateDoc {
  schema_version: "4.3.7.dossier.v1",
  source: enum,                             # see §8.2.1
  template_version: str,                    # e.g. "dossier_v1.1" (DossierGenerator template)
  evidence_map_ref {                        # populated when source ∈ {evidence_map, partial}
    winner_draft_id: str,                   # mirrors cv_assembly.winner.draft_id
    synthesis_hash: str,                    # mirrors cv_assembly.synthesis.synthesis_hash
    pattern_id: str,
    pattern_label: str,
    bullet_lineage_count: int
  } | null,
  fallback_reason: str | null,              # populated when source != evidence_map; <= 240 chars
  body_markdown: str,                       # rendered markdown body (canonical text form)
  body_html: str,                           # rendered HTML for pdf-service /render-pdf
  body_sha256: str,                         # sha256 over canonical UTF-8 body_html bytes
  body_size_bytes: int,
  sections: [                               # explicit section-by-section health
    DossierSectionDoc, ...                  # one entry per section enum (§8.3); never absent
  ],
  validator_report: DossierValidatorReport, # see §11.2; always populated post-validate
  langfuse_trace_ref: TraceRef | null,
  generated_at: datetime,
  generated_by_template_sha: str,           # sha of DossierGenerator template module
  debug_context: DossierStateDebug          # never mirrored to Langfuse, never in projection
}

DossierSectionDoc {
  section_id: SectionEnum,                  # see §8.3
  status: enum,                             # ok | degraded | missing | omitted
  source: enum,                             # evidence_map | best_effort_fallback | absent
  body_markdown: str | null,                # per-section markdown; null when status=missing/omitted
  body_html: str | null,
  evidence_refs: [EvidenceRef, ...],        # master-CV refs + presentation_contract refs
  reason: str | null,                       # when degraded/missing/omitted; <= 240 chars
  validator_action: enum | null,            # which §11.3 action produced this state
  validator_violations: [str, ...]          # rule_ids that fired (subset of validator_report.violations)
}

DossierStateDebug {
  inputs_snapshot_summary { ... },
  validator_pass_summary { ... },
  fallback_invocations: [
    { section_id, reason, replaced_with: enum }
  ],
  template_invocation_summary { ... },
  rollup_inputs_at_compute_time { ... }
}
```

#### 8.2.1 `dossier_state.source` enum

Authoritative enum (4.3.6 reads it; the publisher's
`PublishInput.dossier_source` field per 4.3.6 §9.1 references this
enum verbatim):

| Value | Meaning |
|-------|---------|
| `evidence_map` | All sections sourced from the 4.3 evidence map; validator clean. |
| `best_effort_fallback` | Whole dossier produced via `best_effort_dossier.py`. Used when `cv_assembly.*` is absent (legacy job rendered through the 4.3.6 path) or when `CV_ASSEMBLY_DOSSIER_V2_ENABLED=false`. |
| `partial` | Mixed: some sections from `evidence_map`, others fell back per §10.2 / §11.3. |
| `missing` | Dossier body is absent entirely (degraded path); `body_html=null`, `body_sha256=null`, `body_size_bytes=0`. Publisher renders nothing; `publish_state.render.dossier.status=degraded` per 4.3.6 §13.2. |

### 8.3 Dossier section enum

Mirrors the existing `DossierGenerator` template (`src/layer7/
dossier_generator.py`). No new sections, no reordering.

```text
SectionEnum = Literal[
  "pain_proof_plan",        # 1. Pain → Proof → Plan
  "job_summary",            # 2. Job Summary & Requirements
  "pain_points",            # 3. Pain Point Analysis
  "role_research",          # 4. Role Research
  "star_achievements",      # 5. Selected STAR Achievements
  "company",                # 6. Company Overview
  "fit_analysis",           # 7. Fit Analysis
  "people_and_outreach",    # 8. People & Outreach
  "cover_letter",           # 9. Cover Letter
  "metadata"                # 10. Metadata & Application Form Fields
]
```

`dossier_state.sections[]` always contains exactly 10 entries. A
section that is intentionally not produced has `status=omitted`,
`body_markdown=null`, `reason="omitted_by_template_policy"` — never
absent.

### 8.4 `cv_assembly.status` and `status_breakdown`

```text
cv_assembly.status: enum
  = "pending"        # before 4.3 lane begins
  | "in_progress"    # at least one task running, none completed
  | "completed"      # all required surfaces done; dossier source ∈ {evidence_map}
  | "degraded"       # all required surfaces done; some surface degraded
  | "partial"        # stable state with known gaps (e.g. dossier degraded; legitimate)
  | "failed"         # required surface terminally failed (CV deadletter, lane terminal failure)

cv_assembly.status_breakdown {
  drafts_completed: int,                    # 0..3
  drafts_failed: int,
  winner_present: bool,
  synthesis_present: bool,
  synthesis_degraded: bool,                 # synthesis.degraded
  synthesis_validator_status: enum | null,  # pass | repair_attempted | failed | null
  publish_cv_status: enum,                  # pending|in_progress|done|degraded|failed
  publish_dossier_status: enum,             # pending|in_progress|done|degraded|failed|missing
  publish_drive_cv_status: enum,
  publish_drive_dossier_status: enum,
  publish_sheets_status: enum,              # includes "skipped"
  dossier_source: enum,                     # mirrors dossier_state.source (§8.2.1)
  dossier_section_count: int,               # always 10 by §8.3
  dossier_degraded_section_count: int,
  dossier_missing_section_count: int
}
```

This rollup is the single field an operator UI sorts/filters by.
The exact mapping from sub-states to `cv_assembly.status` is the
deterministic table in §15.

### 8.5 `cv_assembly.legacy` discriminator

`cv_assembly.legacy: bool` is a top-level boolean on the
`cv_assembly` subtree.

| Value | Meaning |
|-------|---------|
| `true` | This `level-2` job pre-dates 4.3 (or 4.3 was disabled when it ran). Dashboards should treat it as a legacy job; only legacy publisher fields apply. |
| `false` | Job was processed by the 4.3 lane. Canonical `cv_assembly.*` exists. |
| absent | Same as `legacy=true` for reader purposes (legacy assumption). New 4.3 writes always set `legacy=false`. |

The discriminator is set by:

- The 4.3 lane's first stage (`cv.header_blueprint`) on first
  write — sets `legacy=false`.
- `scripts/mark_legacy_cv_ready.py` — backfill tool for historical
  jobs; sets `legacy=true` and creates a minimal
  `cv_assembly={legacy:true, schema_version:"4.3.7.1"}` stub if
  `cv_assembly` is absent.

The discriminator is the single field a dashboard reads to decide
which rendering path to use (§13.3).

## 9. Hard Prerequisites

4.3.7-owned operations are not work items, but they are invoked from
work items in other plans. Each invocation has prereqs.

### 9.1 Prereqs for the dossier validator + dossier-state write
(invoked from `publish.render.dossier` per 4.3.6 §13.2)

| Prereq | Check | Blocking | Degradable | On unmet |
|--------|-------|----------|------------|----------|
| `cv_assembly.synthesis.synthesis_hash` present | level-2 read | yes | no | dossier source = `best_effort_fallback`; emit `dossier_prereq_synthesis_missing` event |
| `cv_assembly.synthesis.validator_report.status ∈ {pass, repair_attempted}` | level-2 read | yes for `evidence_map` source | yes — degrade to `best_effort_fallback` when `failed` | dossier source = `best_effort_fallback`; section bodies sourced from `best_effort_dossier`; `fallback_reason="synthesis_validator_failed"` |
| `cv_assembly.synthesis.degraded != true` **OR** `cv_assembly.winner.grade.composite_score >= DOSSIER_EVIDENCE_MAP_MIN_COMPOSITE` (default `0.55`) | level-2 read | yes for `evidence_map` source | yes — degrade to `partial` (use evidence map for sections that pass validator; fall back per-section for the rest) | dossier source = `partial` if any section validates; `best_effort_fallback` otherwise; `fallback_reason="winner_below_threshold"` |
| `cv_assembly.winner.draft_id` present and resolvable in `cv_assembly.drafts[]` | level-2 read | yes for `evidence_map` source | no | reject; degrade to `best_effort_fallback` |
| `cv_assembly.synthesis.evidence_lineage.bullet_lineage[*]` resolvable in master-CV (achievement_id ∈ master-CV) | level-2 read + master-CV loader | per-section blocking only | yes — section degrades to `best_effort_fallback` for that section | per §10.2 / §11.3 |
| `cv_assembly.header_blueprint.identity.chosen_title` present | level-2 read | no | n/a | dossier metadata section uses `level-2.title` directly with note in `debug_context` |
| `pre_enrichment.outputs.pain_point_intelligence` present | level-2 read | no | yes — `pain_points` section degrades | per §10.2 |
| `pre_enrichment.outputs.research_enrichment.{company_profile, role_profile}` present | level-2 read | no | yes — `company` / `role_research` sections degrade | per §10.2 |
| `pre_enrichment.outputs.stakeholder_surface.primary_contacts` (or `secondary_contacts`) present | level-2 read | no | yes — `people_and_outreach` section degrades | per §10.2 |
| `CV_ASSEMBLY_DOSSIER_V2_ENABLED=true` | env / config | yes for `evidence_map` source | yes — when false, force `source=best_effort_fallback` | route through legacy `DossierGenerator` + `best_effort_dossier` exclusively |
| Master-CV loader healthy | call site | yes | no | reject; `dossier_state.source=missing` if no fallback possible; emit alert |

### 9.2 Prereqs for the compatibility projection
(invoked from `publish.finalize` per 4.3.6 §10.2 in the same atomic
update as the `published` CAS)

| Prereq | Check | Blocking | Degradable | On unmet |
|--------|-------|----------|------------|----------|
| `cv_assembly.synthesis.final_cv_text` present | level-2 read | yes for `cv_text` projection | no | projection skips `cv_text`; finalizer fails CAS preconditions per 4.3.6 §10.2 |
| `cv_assembly.publish_state.render.cv.{artifact_local_path, artifact_sha256}` populated | level-2 read | yes for `cv_path` projection | no | finalizer CAS does not match (4.3.6 §10.2 filter requires `render.cv.status="done"`) |
| `cv_assembly.publish_state.upload.drive.cv.uploaded_at` present | level-2 read | yes for `gdrive_uploaded_at` projection | no | finalizer CAS does not match |
| `cv_assembly.dossier_state.body_markdown` present | level-2 read | for `generated_dossier` projection only | yes — when absent, projection passes through (null-preserving) | legacy `generated_dossier` keeps prior value or remains null |
| `cv_assembly.publish_state.upload.drive.dossier.uploaded_at` present | level-2 read | for `dossier_gdrive_uploaded_at` projection only | yes — null-preserving | legacy field unchanged when degraded |
| `cv_assembly.publish_state.upload.sheets.row_id` present | level-2 read | for `sheet_row_id` projection only | yes — null-preserving | legacy field unchanged when sheets skipped |
| `cv_assembly.winner.grade.composite_score` present | level-2 read | yes for `fit_score` projection | no | finalizer CAS does not match |
| `pre_enrichment.outputs.{stakeholder_surface, pain_point_intelligence, research_enrichment, jd_facts}` present | level-2 read | per-field | yes — null-preserving for each absent source | each missing source projects `null` and `$set` skips it |
| `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED=true` | env / config | yes (default true) | yes — when false, finalizer skips projection write but still performs CAS (emergency rollback only) | finalizer alerts; legacy fields untouched |

The projection module itself never blocks — it returns a partial dict
when sources are absent (§12.4). 4.3.6's finalizer CAS is what blocks
or proceeds; it is the consumer that decides whether to write the
projection.

### 9.3 Prereqs for the rollup function

| Prereq | Check | Blocking | Degradable | On unmet |
|--------|-------|----------|------------|----------|
| `cv_assembly` subtree present | level-2 read | yes | no | rollup returns `{status:"pending"}` and skips `status_breakdown` |
| At least one of `drafts`, `grades`, `winner`, `synthesis`, `publish_state`, `dossier_state` present | level-2 read | no | yes | rollup returns `{status:"in_progress"}` with whatever child statuses are derivable |

The rollup function is *defensive* — it never raises on partial state;
absent fields contribute `null` to `status_breakdown` and are scored
as missing in the §15 table.

### 9.4 Hard-prereq summary for 4.3.7 vs umbrella `missing.md` table

The umbrella table in `docs/current/missing.md:6495` lists 4.3.7 as
*"publish_state populated, Yes — projection writes available fields
only"*. The above sections refine that statement: the projection is
*always callable* (pure, partial-tolerant), the *finalizer CAS* is
what blocks publication, and the dossier validator has its own
prereqs that may degrade per-section without blocking publish.

## 10. Extended `DossierGenerator`

### 10.1 Input modes

```python
DossierGenerator.generate(
    job_state: JobState,
    *,
    cv_assembly_evidence: CvAssemblyEvidence | None = None,
    blueprint: HeaderBlueprintDoc | None = None,
    winner_draft: DraftDoc | None = None,
    master_cv: CandidateData | None = None,
    tracer: CvAssemblyTracingSession | None = None,
) -> DossierStateDoc
```

When `cv_assembly_evidence` is provided (4.3 path):

- `pain_proof_plan` from `pain_point_intelligence` (unchanged
  template; new evidence refs).
- `pain_points` from `pain_point_intelligence` (unchanged).
- `role_research` from `research_enrichment.role_profile`.
- `company` from `research_enrichment.company_profile`.
- `people_and_outreach` from `stakeholder_surface.primary_contacts`
  / `secondary_contacts`.
- `star_achievements` from
  `cv_assembly.synthesis.evidence_lineage.bullet_lineage[]` projected
  to STAR shape; section's `evidence_refs[]` cite achievement ids in
  master-CV.
- `fit_analysis` from the **winner** `GradeDoc.dimensions[*].rationale`
  — this is the key change. Today `fit_rationale` is Layer 6 V2's
  self-rationale; with 4.3, it is the authoritative grader's
  rationale, bounded to 300 chars per dimension.
- `cover_letter` from `synthesis.cover_letter` when present;
  otherwise from `winner.draft.cover_letter`; otherwise the section
  is `omitted` with `reason="cover_letter_unavailable"`.
- `metadata` includes `winner_draft_id`, `synthesis_hash` (full),
  `pattern_id`, `pattern_label`, `bullet_lineage_count`, and the
  first 8 chars of `master_cv_checksum` — operator audit surface.
- `job_summary` from the existing JD-facts surface (unchanged).

When `cv_assembly_evidence` is `None` (legacy / flag-off path):

- Falls back to today's `DossierGenerator` behavior verbatim;
  emits `DossierStateDoc` with `source=best_effort_fallback`,
  `evidence_map_ref=null`,
  `fallback_reason="cv_assembly_evidence_absent"`. All 10 sections
  are still populated (or marked `omitted`), so the §11 validator
  has a uniform input shape.

### 10.2 Section-by-section degradation rules

Degradation is **deterministic, per-section, one pass**. The
validator (§11) drives degradation; this section enumerates the
permitted outcomes per section.

| Section | Source priority (deterministic) | Degraded action when source priority fails |
|---------|----------------------------------|---------------------------------------------|
| `pain_proof_plan` | (1) cv_assembly evidence map; (2) pain_point_intelligence; (3) `best_effort_dossier._generate_persona_section` | `omitted` if no source; `reason="no_pain_signal"` |
| `job_summary` | (1) jd_facts; (2) raw JD via `best_effort_dossier._generate_raw_jd_section` | `omitted` if no JD; `reason="no_jd"` |
| `pain_points` | (1) pain_point_intelligence; (2) `best_effort_dossier._generate_analysis_section` | `omitted`; `reason="no_pain_intelligence"` |
| `role_research` | (1) research_enrichment.role_profile; (2) JD-derived stub | `omitted`; `reason="no_role_research"` |
| `star_achievements` | (1) evidence_lineage.bullet_lineage; (2) winner_draft achievement spans (no synthesis); (3) master-CV top achievements (degraded — no jd_facts) | `degraded` with `source=best_effort_fallback` if (3) fires; `omitted` only if master-CV is empty |
| `company` | (1) research_enrichment.company_profile; (2) `best_effort_dossier._generate_company_section` | `omitted`; `reason="no_company_research"` |
| `fit_analysis` | (1) winner.grade.dimensions; (2) Layer-6-V2 self-rationale fallback (legacy fit_rationale) | `degraded` if (2) fires; `omitted` if both absent |
| `people_and_outreach` | (1) stakeholder_surface.{primary,secondary}_contacts; (2) `best_effort_dossier._generate_contacts_section` | `omitted`; `reason="no_contacts"` |
| `cover_letter` | (1) synthesis.cover_letter; (2) winner.draft.cover_letter | `omitted`; `reason="cover_letter_unavailable"` |
| `metadata` | always sourced; never degrades | n/a — uses whatever fields are present; missing fields write `null` |

A section that uses source priority ≥ 2 is recorded with
`status="degraded"`, `source="best_effort_fallback"`,
`validator_action ∈ {fall_back_to_best_effort_section, omit_section}`,
and the `reason` populated. The dossier's overall `source` is then
`partial` if at least one section is `evidence_map` and at least one
is `best_effort_fallback`; `evidence_map` if all non-`omitted`
sections are `evidence_map`; `best_effort_fallback` if all
non-`omitted` sections are fallback; `missing` if every section is
`omitted` (in which case `body_html=null`).

### 10.3 `best_effort_dossier` path preserved

`runner_service/utils/best_effort_dossier.py` is unchanged. It
remains:

- the canonical legacy path when `cv_assembly` is absent
  (`source=best_effort_fallback`);
- the per-section fallback target under §10.2;
- the path used when `CV_ASSEMBLY_DOSSIER_V2_ENABLED=false`.

The 6-section lite dossier it produces today is mapped onto the
10-section `dossier_state.sections[]` with `omitted` entries for
sections it does not produce.

## 11. Dossier Section Validator API

Mirrors the 4.3.2 §11.2 validator template; deterministic, no LLM,
single-pass repair, byte-determinism guaranteed.

### 11.1 Module and signature

Module: `src/cv_assembly/validators/dossier_validator.py`.

Public surface (Python pseudo-signature):

```python
def validate_dossier(
    dossier_state_doc: DossierStateDoc,
    blueprint: HeaderBlueprintDoc,
    winner_draft: DraftDoc,
    master_cv: CandidateData,
    *,
    presentation_contract: PresentationContractDoc | None = None,
    pain_intelligence: PainPointIntelligenceDoc | None = None,
    research_enrichment: ResearchEnrichmentDoc | None = None,
    stakeholder_surface: StakeholderSurfaceDoc | None = None,
    tracer: CvAssemblyTracingSession | None = None,
) -> DossierValidatorReport
```

Invocation contract:

- Called by `publish.render.dossier` (4.3.6 §13.2) immediately
  before the body is rendered, against the in-memory
  `DossierStateDoc` produced by `DossierGenerator.generate()`.
- May also be called from a debug/admin re-validation path against
  the persisted `dossier_state` for an existing job. Output must be
  byte-identical to the original validation given identical inputs.
- The validator never raises on input absence — missing optional
  inputs (`presentation_contract=None` etc.) reduce the set of
  invariants checked; the report records which checks were skipped.

### 11.2 Report shape

```text
DossierValidatorReport {
  status: enum,                              # pass | repair_attempted | failed
  determinism_hash: str,                     # sha256 over canonical serialization of report — used for byte-equality assertions
  sections: [
    {
      section_id: SectionEnum,
      status: enum,                          # ok | degraded | missing | omitted
      violations: [
        {
          rule_id: str,                      # stable slug, e.g. "star_lineage_unresolved"
          severity: enum,                    # blocking | repairable | warning
          detail: str                        # <= 240 chars
        }, ...
      ],
      repair_action: enum | null,            # see §11.3; null if no repair needed
      action_reason: str | null              # <= 240 chars
    },
    ... (always 10 entries, mirrors §8.3)
  ],
  violations_summary: {
    total: int,
    blocking_count: int,
    repairable_count: int,
    warning_count: int
  },
  repairs_applied: [
    {
      section_id: SectionEnum,
      action: enum,                          # see §11.3
      before_hash: str,                      # sha256 over before-section body
      after_hash: str
    }, ...
  ],
  checks_skipped: [str, ...],                # rule_ids skipped because optional inputs absent
  duration_ms: int
}
```

### 11.3 Allowed deterministic actions

Repair is **deterministic**, **bounded to one pass**, **never calls
an LLM**, and never adds content outside the inputs already present
on the validator surface (master-CV, blueprint, winner draft,
preenrich subdocs).

| Action | Effect | Allowed when |
|--------|--------|--------------|
| `fall_back_to_best_effort_section` | Replace the offending section's body with the result of `best_effort_dossier`'s analogous helper (§10.2 source priority 2/3); set section `status=degraded`, `source=best_effort_fallback`. | Section's evidence-map sourced body fails a `repairable` rule (e.g. `star_lineage_unresolved`, `fit_rationale_too_long`, `company_summary_empty`). |
| `omit_section` | Drop the section: `status=omitted`, body fields null, `reason` populated. | Section's evidence map *and* fallback both fail (e.g. `cover_letter_unavailable`). |
| `clamp_field_length` | Truncate over-long fields to enforced bounds (e.g. clamp `fit_rationale` per dimension to 300 chars). | Field-length rule violations only; never used for content rules. |
| `dedupe_evidence_refs` | Remove duplicate evidence_refs (sha-stable order preserved). | Validator detects duplicates from the per-section refs list. |

Repair never:

- generates new prose;
- introduces master-CV refs not already in `winner_draft.evidence_refs[]`,
  `synthesis.evidence_lineage[]`, or `blueprint.evidence[]`;
- modifies `evidence_map_ref` (provenance);
- regenerates via LLM;
- calls back into `DossierGenerator.generate()`.

After a single repair pass, the validator re-runs invariant checks
on the post-repair `DossierStateDoc`. Remaining `severity=blocking`
violations → `status=failed` (the per-section status becomes
`omitted`; if every section omits, dossier `source=missing`).
Remaining `severity=repairable` violations after one pass →
`status=failed` for that section (same per-section omission).
`severity=warning` violations are retained in the report but do not
fail the section.

### 11.4 Determinism guarantee

For fixed `(dossier_state_doc, blueprint, winner_draft, master_cv,
presentation_contract, pain_intelligence, research_enrichment,
stakeholder_surface)`, `validate_dossier()` returns a
`DossierValidatorReport` whose `determinism_hash` is byte-identical
across runs.

This is asserted by:

- `tests/unit/cv_assembly/test_dossier_validator_determinism.py` —
  fixed-input → fixed-`determinism_hash` test on a curated 8-case
  fixture.
- The §22 eval corpus byte-equality regression gate.

## 12. Compatibility Projection Module API

### 12.1 Module and signature

Module: `src/cv_assembly/compat/projection.py`.

Public surface (Python pseudo-signature):

```python
def project_cv_assembly_to_level2(
    level2_doc: dict,
    *,
    include_null_projections: bool = False,
    tracer: CvAssemblyTracingSession | None = None,
) -> dict:
    """
    Compute the legacy-field projection for the 4.3 lane.

    Pure function. No Mongo writes, no IO, no time-dependent values.

    Returns a dict suitable for use as the `$set` payload in the
    4.3.6 finalizer CAS. The dict contains *only* legacy-root field
    keys (e.g. "cv_text", "fit_score", "drive_folder_url"); it never
    contains keys under the `cv_assembly.*` subtree.

    When `include_null_projections=False` (default), keys whose
    canonical source is absent are omitted from the returned dict
    (null-preserving rule). When True, those keys are included with
    value None — useful for callers that want to detect missing
    canonical sources explicitly (debug tooling, eval harness).
    """
```

The function never raises. On a malformed `level2_doc` (e.g. invalid
schema), the function returns an empty dict and emits a
`projection_input_invalid` event to the tracer if provided. It does
not mutate `level2_doc`.

### 12.2 Return shape (full enumerated)

The dict's keys are exactly the legacy fields enumerated in 4.3.6
§10.1, and *only* those keys. For convenience and to lock the
contract here, the canonical key list is:

```text
PROJECTION_KEYS = [
  "cv_text",
  "cv_path",
  "cv_reasoning",
  "cover_letter",
  "generated_dossier",
  "fit_score",
  "fit_rationale",
  "selected_star_ids",
  "primary_contacts",
  "secondary_contacts",
  "pain_points",
  "strategic_needs",
  "risks_if_unfilled",
  "success_metrics",
  "company_summary",
  "extracted_jd",
  "drive_folder_url",
  "sheet_row_id",
  "gdrive_uploaded_at",
  "dossier_gdrive_uploaded_at",
  "total_cost_usd",
  "token_usage",
  "status",
  "pipeline_run_at",
]
```

`pipeline_runs[]` is **not** in the return dict — it is a `$push`
operation, computed by the caller (4.3.6 finalizer) from
`PublishInput.run_id` + `PublishInput.processing_tier` per 4.3.6
§10.1. The projection module exports a sibling helper for the
caller's convenience:

```python
def build_pipeline_run_entry(level2_doc: dict, *, run_id: str, tier: str) -> dict:
    """Returns the dict to $push onto pipeline_runs[]."""
```

The projection module is the only canonical source of the
`PROJECTION_KEYS` list. Any other code that enumerates legacy
publisher fields must `from src.cv_assembly.compat.projection import
PROJECTION_KEYS`.

### 12.3 Idempotence and purity contract

| Property | Guarantee | How asserted |
|----------|-----------|--------------|
| **Pure** | No Mongo IO, no HTTP, no clock reads, no env reads inside the function body. | `tests/unit/cv_assembly/test_projection_purity.py` — patches `time.time`, `datetime.utcnow`, and Mongo client to `None`; asserts function still runs. |
| **Deterministic** | Same `level2_doc` → byte-identical return dict across runs (key order irrelevant; values identical). | Unit test compares dict.items() sorted. |
| **Idempotent** | `project(level2_doc) == project({**level2_doc, **project(level2_doc)})` — re-projecting a doc that already has projection applied yields the same result. | Unit test. |
| **Null-preserving** | If a canonical source is `None` or absent, the corresponding key is omitted from the return dict (default mode). The caller's `$set` skips missing keys, leaving the existing legacy field value intact. | Unit test on a doc with mixed legacy + canonical state. |
| **Subtree-isolated** | Return dict contains only keys in `PROJECTION_KEYS`; never contains `cv_assembly.*` keys. | Unit test asserts `set(result.keys()) ⊆ set(PROJECTION_KEYS)`. |
| **Schema-stable** | Adding a new `PROJECTION_KEYS` entry is a minor version bump; removing one is a major bump. | Schema-version constant `PROJECTION_SCHEMA_VERSION` in the module; eval gate. |

### 12.4 Error behavior on partial state

The projection module never raises. Partial-state behaviors:

| Canonical source | Projection behavior |
|------------------|---------------------|
| `cv_assembly.synthesis.final_cv_text` absent | `cv_text` omitted from return dict; null-preserving. |
| `cv_assembly.dossier_state.body_markdown` absent / null | `generated_dossier` omitted; null-preserving. |
| `cv_assembly.publish_state.upload.drive.dossier.uploaded_at` absent | `dossier_gdrive_uploaded_at` omitted. |
| `cv_assembly.publish_state.upload.sheets.row_id` absent (sheets skipped) | `sheet_row_id` omitted. |
| `cv_assembly.winner.grade.composite_score` absent | `fit_score` and `fit_rationale` both omitted. |
| `pre_enrichment.outputs.stakeholder_surface` absent | `primary_contacts` and `secondary_contacts` both omitted. |
| `cv_assembly` subtree absent entirely | Empty dict returned (legacy job; finalizer should not even be invoked, but the module is defensive). |
| `cv_assembly.legacy=true` | Empty dict returned (legacy jobs do not project). |

### 12.5 Caller list and replay safety

Permitted callers:

| Caller | Purpose | Replay behavior |
|--------|---------|-----------------|
| `src/cv_assembly/sweepers.py::published_finalizer_cas` | Atomic projection write inside the `published` CAS (4.3.6 §10.2). | Idempotent: re-running the finalizer recomputes the projection from current `cv_assembly.*`; CAS filter prevents double-write of `published_at`. |
| `src/cv_assembly/sweepers.py::delivered_finalizer_cas` | Re-projection on `delivered` re-entry (rare; `gdrive_uploaded_at` already set by `published` projection per 4.3.6 §16.2). | Idempotent. |
| `frontend/repositories/discovery_repository.py::cv_assembly_job_detail` | Read-only debug surface — calls projection with `include_null_projections=True` to render a "what would the projection write" diff for operator UI. | Pure; no writes. |
| `scripts/cv_assembly_replay_projection.py` | Operator tool to recompute and overwrite the projection for a single job (e.g. after a projection schema bump). Writes only when `--commit` is passed; default is dry-run with diff. | Idempotent for unchanged inputs; `--commit` is a manual write. |
| `data/eval/validation/cv_assembly_4_3_7_state/` benchmark harness | Byte-equality eval. | Pure. |

Forbidden callers:

- `src/layer7/output_publisher.py` — must use `PublishInput` per
  4.3.6 §9 and let the finalizer call the projection. The publisher
  must not call the projection module directly.
- Any preenrich stage. The projection runs *after* `cv_assembled`;
  preenrich never invokes it.
- Any `pre_enrichment.*` stage outbox.

Replay safety is a function of (a) projection determinism (§12.3),
(b) finalizer CAS idempotence (4.3.6 §10.2), and (c) the
null-preserving rule (legacy fields are not destroyed by replays
against partial canonical state).

## 13. Frontend / Operator UI Semantics

### 13.1 Lifecycle categories

Dashboards group by lifecycle. 4.3.7 extends the legacy bucketing:

| Category label | Lifecycle values |
|----------------|------------------|
| Preenriching | `selected`, `preenriching`, legacy `ready`, `ready_for_cv`, `queued`, `running` |
| Awaiting CV assembly | `cv_ready` |
| Assembling CV | `cv_assembling` |
| Ready to publish | `cv_assembled` |
| Publishing | `publishing` |
| Published | `published` |
| Delivered | `delivered` |
| Terminal failure | `failed`, `deadletter` |

Legacy dashboards that bucketed every post-preenrich state as "ready
for applying" continue to render the legacy bucket for legacy jobs
(per the discriminator §13.3); 4.3 jobs use the new buckets.

### 13.2 Status-color semantics

- `cv_assembling`, `publishing` → yellow (in progress).
- `cv_assembled`, `published`, `delivered` → green (increasing
  completeness; `delivered` is strongest signal).
- `cv_assembly.status="degraded"` rollups → amber tint within green
  (job reached a green lifecycle but has a degraded outcome; per-
  surface badges surface details).
- `cv_assembly.status="partial"` rollups → amber (job reached a
  stable state with known gaps, e.g. only 2 of 3 drafts succeeded).
- `failed`, `deadletter` → red.

### 13.3 Legacy / non-legacy discriminator and default toggle

The frontend uses `cv_assembly.legacy` as the *single* discriminator
for which rendering path to use:

| Discriminator value | Rendering path | Reason |
|---------------------|----------------|--------|
| `cv_assembly.legacy = true` (or `cv_assembly` absent) | Legacy dashboard cards. Reads only legacy `level-2` root fields. | Pre-4.3 jobs; `cv_assembly.*` either absent or stub. |
| `cv_assembly.legacy = false` AND `cv_assembly.dossier_state.source != "missing"` | 4.3 dashboard cards. Reads `cv_assembly.*` canonical surfaces. | Healthy 4.3 path. |
| `cv_assembly.legacy = false` AND `cv_assembly.dossier_state.source = "missing"` | 4.3 dashboard cards with explicit "dossier missing" badge. | 4.3 path with degraded dossier; do not switch to legacy reads. |

Default behaviors:

- The dashboard's default filter is `cv_assembly.legacy=false`
  ("show only 4.3 jobs"). Operators can flip a single toggle
  `Show legacy jobs` to include all jobs.
- Per-job detail views read `cv_assembly.legacy` once at page load
  and route deterministically; mid-render mode-flipping is
  forbidden (avoids flicker between legacy and 4.3 layouts).
- When mixed (toggle on), the dashboard groups legacy jobs and 4.3
  jobs into separate sections; never interleaves them in one ranked
  list.
- The 4.3 lifecycle counters (`cv_assembling`, `cv_assembled`,
  `publishing`, `published`, `delivered`) only count
  `cv_assembly.legacy=false` jobs by default; the toggle is what
  brings legacy jobs into the counters (with a visible `(incl
  legacy: N)` annotation).

The frontend may become "4.3-first" — i.e. flip the default toggle
to "show all" and remove the legacy/4.3 separation — only after the
last legacy job has been migrated, archived, or aged out. v1 keeps
them visibly separated.

### 13.4 Per-job detail view

For `cv_assembly.legacy=false` jobs, the per-job detail view must:

- show the three draft grade `composite_score` values side by side,
  labeled by `pattern_label`;
- show `winner_draft_id` and the synthesis improvement delta
  (`synthesis.composite_score - winner.grade.composite_score`);
- show per-surface publish state from `cv_assembly.publish_state`:
  CV render, dossier render, Drive CV, Drive dossier, Sheets;
- show `cv_assembly.dossier_state.source` and a per-section
  status badge grid (10 sections, one badge each);
- link to the `trace_ref` for every stage in `cv_assembly.stage_runs`
  (one click → Langfuse);
- expose the projection diff (`include_null_projections=True`) as a
  collapsible "what the finalizer wrote to the legacy fields"
  panel.

Implementation targets in the frontend:

- `frontend/repositories/discovery_repository.py`
  - extend `get_pipeline_heartbeat()` to surface a 4.3 card:
    primary = `published` in 24h, secondary = active
    `cv_assembling` + `publishing`, alert on `degraded > threshold`.
    Heartbeat respects the `cv_assembly.legacy=false` filter.
  - new `cv_assembly_job_detail(level2_id) -> dict` returning the
    full `cv_assembly.*` subtree plus the projection-diff dict
    described above (called with
    `include_null_projections=True`).
- `frontend/intel_dashboard.py`
  - new route `/discovery/cv-assembly` with stage backlog cards for
    `cv.*` and `publish.*` task types; default filter
    `cv_assembly.legacy=false`.
  - new route `/discovery/cv-assembly/<level2_id>` with per-job
    detail per §13.4.
  - extend `/discovery/results` filters to include the new
    lifecycles and the legacy toggle.
- `frontend/templates/`
  - new partials for the three-draft side-by-side, the per-surface
    publish grid, the 10-section dossier badge grid, and the
    projection diff panel.

## 14. Index / Migration Plan

### 14.1 New indexes (declared)

Two compound indexes on `level-2` and one on `pdf_service_health_state`
(the latter declared in 4.3.6 but listed here for completeness of
the migration script):

```text
db["level-2"].create_index(
  [
    ("cv_assembly.legacy", 1),
    ("cv_assembly.status", 1),
    ("cv_assembly.status_breakdown.publish_cv_status", 1),
  ],
  name="cv_assembly_legacy_status_publish_cv_v1",
  background=True,
)

db["level-2"].create_index(
  [
    ("cv_assembly.legacy", 1),
    ("lifecycle", 1),
    ("cv_assembly.published_at", -1),
  ],
  name="cv_assembly_legacy_lifecycle_published_at_v1",
  background=True,
)
```

The first powers the `/discovery/cv-assembly` dashboard's status
breakdown queries; the second powers the "recent published"
heartbeat card.

`cv_assembly.legacy` is the leading key in both because the default
dashboard filter is `legacy=false`; this lets the index serve queries
that filter on the discriminator without scanning legacy jobs.

### 14.2 Rolling-build strategy

The Atlas replica set is a 3-node deployment; index builds must be
non-blocking. Strategy:

1. **Schema preflight.** Ship the
   `cv_assembly.legacy` write-path code first (so new jobs populate
   the field) but leave indexes unbuilt. Verify
   `cv_assembly.legacy` is present on all jobs created after the
   shipped commit.
2. **Discriminator backfill.** Run
   `scripts/mark_legacy_cv_ready.py` against the historical job set
   to set `cv_assembly.legacy=true`. The script is batched
   (`--batch-size 100`, `--sleep-ms 200`) and idempotent (skips
   docs that already have `cv_assembly.legacy` set). Verify post-
   backfill: every `level-2` doc has `cv_assembly.legacy ∈ {true,
   false}`.
3. **Rolling background build.** Use Atlas's rolling index build (or
   `db.runCommand({createIndexes, indexes:[…], commitQuorum:0})`
   with `background:true`). Builds run on each replica in turn; no
   write block on the primary.
4. **Adoption check.** Once both indexes are present in
   `db["level-2"].listIndexes()`, run the §14.4 adoption script.
5. **Flip dashboard default.** Only after adoption is confirmed do
   we enable `CV_ASSEMBLY_DASHBOARD_V2_ENABLED=true` and let the new
   queries run against the indexes.

### 14.3 Deployment ordering and rollback

Deployment ordering:

1. Backfill `cv_assembly.legacy` on historical jobs.
2. Ship code that writes `cv_assembly.legacy=false` on every new
   4.3 job.
3. Build new indexes via rolling background build.
4. Verify adoption.
5. Flip frontend feature flag.

Rollback (in reverse):

1. Flip `CV_ASSEMBLY_DASHBOARD_V2_ENABLED=false` — frontend reverts
   to legacy queries that don't depend on the new indexes.
2. (Optional) Drop new indexes via
   `db["level-2"].drop_index("cv_assembly_legacy_status_publish_cv_v1")`
   and the second index. Indexes are cheap to retain; only drop if
   space is genuinely a concern. v1 keeps them.
3. The `cv_assembly.legacy` field is left in place on all docs; it
   is harmless when unread.

### 14.4 Adoption verification

Script: `scripts/cv_assembly_index_adoption_check.py`. Runs:

- `db["level-2"].listIndexes()` — both new indexes present.
- For each new dashboard query, runs `explain("executionStats")`
  and asserts `IXSCAN` (not `COLLSCAN`) and that the new index is
  the chosen plan.
- Asserts `nReturned / totalDocsExamined > 0.5` for the
  legacy-filtered queries (sanity that the discriminator is
  filtering effectively).
- Exits with code 0 on success, 1 on any check failure.

The §23 VPS validation runs this script before declaring §23.13
acceptance.

## 15. Partial-Completion Rollup Table

### 15.1 Deterministic rollup function

Module: `src/cv_assembly/compat/rollup.py`.

```python
def compute_status_rollup(level2_doc: dict) -> tuple[str, dict]:
    """
    Returns (cv_assembly.status, status_breakdown) computed
    deterministically from the cv_assembly subtree.

    Pure function. Same shape contract as projection module: never
    raises; missing inputs contribute null to status_breakdown.
    """
```

Called by:

- `frontend/repositories/discovery_repository.py` on every per-job
  detail read.
- 4.3.4 / 4.3.5 / 4.3.6 finalizers may invoke it to persist
  `cv_assembly.status` and `status_breakdown` for fast dashboard
  reads (cheap, deterministic, ok to overwrite).
- The §22 eval harness for byte-equality checks.

The function emits no events, makes no Mongo writes, and never calls
LLMs.

### 15.2 Rollup table

Inputs (per job):

- `D`: `len([d for d in cv_assembly.drafts if d.status=="completed"])` (0–3)
- `Df`: `len([d for d in cv_assembly.drafts if d.status=="failed"])`
- `W`: `cv_assembly.winner` is present
- `S`: `cv_assembly.synthesis` is present
- `Sd`: `cv_assembly.synthesis.degraded` is true
- `Sv`: `cv_assembly.synthesis.validator_report.status`
  (`pass | repair_attempted | failed | null`)
- `PCV`: `cv_assembly.publish_state.render.cv.status`
- `PD`: `cv_assembly.publish_state.render.dossier.status`
- `UCV`: `cv_assembly.publish_state.upload.drive.cv.status`
- `UD`: `cv_assembly.publish_state.upload.drive.dossier.status`
- `US`: `cv_assembly.publish_state.upload.sheets.status`
- `Pat`: `cv_assembly.published_at` is set
- `Dat`: `cv_assembly.delivered_at` is set
- `DS`: `cv_assembly.dossier_state.source`

Status decision (first match wins):

| Condition | `cv_assembly.status` |
|-----------|----------------------|
| Lane has not started: `cv_assembly` absent or only `header_blueprint` present and no work-item activity | `pending` |
| `Df ≥ 3` OR `Sv == "failed"` AND no winner OR `PCV == "failed"` AND attempt budget exhausted | `failed` |
| `Pat` set AND `Dat` set AND `UCV == "done"` AND `UD == "done"` AND `US ∈ {"done","skipped"}` AND `DS == "evidence_map"` | `completed` |
| `Pat` set AND `Dat` set AND (`UD == "degraded"` OR `US == "skipped"` OR `DS ∈ {"partial","best_effort_fallback"}`) | `degraded` |
| `Pat` set AND `Dat` not set (delivered lag) | `degraded` |
| `Pat` set AND any of `(UD,UCV,US)` still `pending`/`in_progress` | `in_progress` |
| `Pat` not set AND any of `(PCV,PD,UCV,UD,US)` is `in_progress` OR `pending` | `in_progress` |
| `Pat` not set AND `S` present AND `(D ≥ 2)` AND (no publish_state activity yet) | `partial` (cv_assembled, not yet publishing) |
| `Pat` not set AND `D < 3` AND `Df > 0` (degraded draft set) | `partial` |
| Otherwise | `in_progress` |

`status_breakdown` is filled directly from the inputs above per §8.4.

### 15.3 Worked examples

| Lifecycle | D | Df | W | S | Sd | Sv | PCV | PD | UCV | UD | US | Pat | Dat | DS | → status |
|-----------|---|----|---|---|----|----|-----|-----|-----|----|----|----|------|----|---------|
| `cv_assembling` (just started) | 1 | 0 | F | F | – | null | pending | pending | pending | pending | pending | F | F | – | `in_progress` |
| `cv_assembled` (winner picked) | 3 | 0 | T | T | F | pass | pending | pending | pending | pending | pending | F | F | – | `partial` |
| `cv_assembled` (synthesis degraded but valid) | 3 | 0 | T | T | T | pass | pending | pending | pending | pending | pending | F | F | – | `partial` |
| `publishing` (CV rendered, dossier in flight) | 3 | 0 | T | T | F | pass | done | in_progress | pending | pending | pending | F | F | – | `in_progress` |
| `published` (full healthy) | 3 | 0 | T | T | F | pass | done | done | done | done | done | T | T | evidence_map | `completed` |
| `published` (dossier degraded, sheets skipped) | 3 | 0 | T | T | F | pass | done | degraded | done | degraded | skipped | T | T | partial | `degraded` |
| `published` (delivered lag) | 3 | 0 | T | T | F | pass | done | done | done | done | done | T | F | evidence_map | `degraded` |
| `published` (best-effort dossier — legacy-style content even on 4.3 lane) | 3 | 0 | T | T | F | pass | done | done | done | done | done | T | T | best_effort_fallback | `degraded` |
| `delivered` (every healthy surface) | 3 | 0 | T | T | F | pass | done | done | done | done | done | T | T | evidence_map | `completed` |
| `failed` (all drafts failed) | 0 | 3 | F | F | – | null | – | – | – | – | – | F | F | – | `failed` |
| `failed` (synthesis validator failed and no recoverable winner) | 3 | 0 | T | T | F | failed | – | – | – | – | – | F | F | – | `failed` |
| `failed` (CV render deadletter) | 3 | 0 | T | T | F | pass | failed | – | – | – | – | F | F | – | `failed` |

Edge-state rules:

- **Dossier degraded while CV publish succeeded**: `status=degraded`,
  not `failed`. Per-surface badges show the degradation.
- **Compatibility projection succeeded but render artifact missing**:
  cannot happen — finalizer CAS requires `render.cv.status="done"`
  and `artifact_sha256` to exist (4.3.6 §10.2 filter). If
  `artifact_local_path` is later deleted by cleanup, the publish
  state still records the sha; consumers must use Drive as
  canonical for the artifact (4.3.6 §18.1).
- **`delivered` lags `published`**: `status=degraded` until
  `Dat` is set or 4.3.6 §16.3 `delivered_lag` alert fires; operators
  may manually trigger `delivered` re-entry per 4.3.6 §16.2.

## 16. Cross-Artifact Invariants

INV1. **`cv_assembly.*` is canonical** for 4.3 state; legacy `level-2`
  root fields are derived via the projection module (§12).
INV2. **`pre_enrichment.*` is never mutated by 4.3**, including by
  4.3.7's projection and validator. Confirmed by §22 unit tests
  asserting projection input → projection output never includes
  `pre_enrichment.*` keys.
INV3. **`cv_assembly.dossier_state.evidence_map_ref.synthesis_hash`
  equals `cv_assembly.synthesis.synthesis_hash`** when
  `dossier_state.source ∈ {evidence_map, partial}`.
INV4. **`cv_assembly.dossier_state.evidence_map_ref.winner_draft_id`
  equals `cv_assembly.winner.draft_id`** under the same condition.
INV5. **The compatibility projection never fabricates values absent
  in canonical state**. If a canonical source is absent, the
  projected key is omitted (null-preserving). Legacy fields are
  never overwritten with `None`.
INV6. **Compatibility projection fields on `level-2` root equal the
  projection of `cv_assembly.*` at the time of publish**, asserted
  by re-running the projection against the post-publish doc and
  comparing to the legacy fields actually present.
INV7. **`cv_assembly.status_breakdown.dossier_source ==
  cv_assembly.dossier_state.source`** always.
INV8. **`status_breakdown` deterministically rolls up from child
  statuses** per §15. No reader may compute a different rollup.
INV9. **`cv_assembly.delivered_at` is null when
  `cv_assembly.published_at` is null** (inherited from 4.3.6 INV8;
  4.3.7 dashboards rely on it for the "delivered" badge).
INV10. **`cv_assembly.dossier_state.body_sha256` equals the sha256
  of UTF-8 bytes of `body_html`** (the bytes 4.3.6 sends to
  pdf-service `/render-pdf`).
INV11. **`cv_assembly.dossier_state.sections[]` contains exactly 10
  entries**, one per `SectionEnum` value (§8.3); ordering matches the
  enum's declaration order; missing/omitted sections are still
  present with explicit `status=missing|omitted`.
INV12. **`cv_assembly.legacy=true` jobs do not project**: the
  projection module returns an empty dict; legacy readers continue
  to see whatever legacy fields were already present.
INV13. **Validator-reported `status=failed` on a section forces
  `dossier_state.sections[i].status=omitted`** post-repair — the
  body bytes for that section are never persisted.
INV14. **Dossier fallback is always clearly marked**: any section
  with `source=best_effort_fallback` carries
  `status=degraded|missing|omitted` (never `ok`); any whole-dossier
  fallback (`dossier_state.source=best_effort_fallback`) populates
  `fallback_reason`.
INV15. **The `legacy` discriminator is monotonic**: once
  `cv_assembly.legacy=false` is set, no code path may flip it back
  to `true`. (Only `mark_legacy_cv_ready.py` writes `true`, and only
  on docs where `legacy` is absent.)

Failure of any invariant is a §22 regression-gate condition.

## 17. Fail-Open / Fail-Closed Matrix

| Condition | Behavior | Lifecycle outcome |
|-----------|----------|-------------------|
| `cv_assembly.*` absent on a legacy job | Dashboards render legacy bucket; projection returns `{}` | unchanged; legacy job behavior preserved |
| `cv_assembly.legacy=true` on a job | Dashboards render legacy bucket; projection returns `{}` | unchanged |
| Synthesis present, validator status `failed` | Dossier source falls back to `best_effort_fallback`; CV publish blocked by 4.3.6 prereq INV1 | stays `cv_assembled`; alerts via 4.3.6 |
| Synthesis present, `degraded=true`, `winner.composite >= threshold` | Dossier source = `evidence_map` (acceptable per §9.1); `status_breakdown.synthesis_degraded=true` | proceeds normally |
| Synthesis present, `degraded=true`, `winner.composite < threshold` | Dossier source = `partial` (per-section fallback) or `best_effort_fallback` (whole-dossier) per §9.1 | proceeds; `status=degraded` |
| One dossier section fails validator (repairable) | Section degrades to `best_effort_fallback`; `dossier_state.source=partial` | proceeds; `status=degraded` |
| All dossier sections fail validator | `dossier_state.source=missing`; body null; 4.3.6 dossier render skipped | proceeds (dossier degradable per 4.3.6); `status=degraded` |
| Compat projection schema mismatch (canonical field added but consumers expect old shape) | Projection schema-version bump emits `projection_schema_version_drift` event; finalizer continues with new shape | proceeds; alert |
| Reader queries `cv_assembly.status` before any 4.3 stage runs | Rollup returns `{status:"pending", status_breakdown:{}}` defensively | unchanged |
| Index not yet adopted but query runs | Query falls back to COLLSCAN (slow but correct); §14.4 adoption check fires alert | proceeds |
| `mark_legacy_cv_ready.py` rerun | Idempotent; skips already-marked docs | unchanged |
| Compatibility projection detects internal inconsistency (e.g. `synthesis.final_cv_text` empty string vs absent) | Treated as absent (null-preserving rule) | proceeds |
| Mid-flight crash during atomic projection write | Mongo guarantees single-document atomicity (4.3.6 §10.2); on retry, projection recomputes deterministically and CAS lands or already-set | proceeds |

Fail-closed (deadletter, lifecycle stays `cv_assembled` or `failed`):

- **Validator determinism violation**: `validate_dossier()` returns
  different reports on identical inputs across runs in the eval
  corpus → block rollout.
- **Projection purity violation**: `project_cv_assembly_to_level2()`
  performs a Mongo write or reads from clock/env → block rollout.
- **`pre_enrichment.*` mutation**: any 4.3.7-owned code mutates
  `pre_enrichment.*` → block rollout.

## 18. Safety / Anti-Hallucination

- **Dossier prose is constrained to the evidence map** when
  `dossier_state.source=evidence_map`. No novel claims may enter via
  dossier prose; the validator (§11) enforces `evidence_refs[]`
  resolution against master-CV.
- **Fit analysis copy comes from grader rationale strings**, which
  are bounded to 300 chars per dimension and grounded in rubric
  dimensions (4.3.5 §9). The validator clamps over-long values
  deterministically (§11.3 `clamp_field_length`).
- **`best_effort_dossier` fallback never pulls from fabricated
  content**. It uses existing JD + company + contacts + master-CV
  highlights only; the validator still asserts
  `evidence_refs[]` resolve.
- **Metadata section** includes `winner_draft_id`, `synthesis_hash`,
  `pattern_id`, `pattern_label`, `bullet_lineage_count`, and the
  first 8 chars of `master_cv_checksum`, so an operator reading the
  dossier can audit exactly which drafts and evidence produced it.
- **The projection module never invents legacy values**. If the
  canonical source is absent, the projected key is omitted (INV5);
  the legacy field is left as-is.
- **The validator never invokes an LLM**. `repair` is bounded to the
  four deterministic actions in §11.3.
- **No protected-trait inferences anywhere** in the dossier or the
  projection.
- **No third-party PII** beyond what `stakeholder_surface` already
  produced (which has its own anti-PII guardrails).

## 19. Downstream Consumer Contracts

Each consumer of 4.3.7-owned surfaces declares what it may rely on
and what it must not infer.

### 19.1 4.3.6 publisher (`publish.render.dossier`, `publish.finalize`)

**May rely on**:

- `cv_assembly.dossier_state.body_html` (and `body_sha256`,
  `body_size_bytes`) populated when
  `dossier_state.source ∈ {evidence_map, best_effort_fallback,
  partial}`.
- `cv_assembly.dossier_state.source` carrying one of the four
  values in §8.2.1.
- `cv_assembly.dossier_state.validator_report.status ∈ {pass,
  repair_attempted}` when `source != missing`.
- `project_cv_assembly_to_level2()` returning a dict of legacy keys
  ⊆ `PROJECTION_KEYS` and never raising.
- Idempotent re-invocation of the projection on retry yielding the
  same dict.

**Must not infer**:

- That `dossier_state.body_*` exists when `source = "missing"`.
- That `dossier_state.sections[i].body_*` exists when section
  `status ∈ {missing, omitted}`.
- That `evidence_map_ref` is populated when `source =
  "best_effort_fallback"`.
- That the projection writes any keys outside `PROJECTION_KEYS`.

### 19.2 Frontend dashboards / operator UI

**May rely on**:

- `cv_assembly.legacy` as the single discriminator (§13.3).
- `cv_assembly.status` and `status_breakdown` computed via the
  rollup function (§15).
- The 10-section structure in `dossier_state.sections[]` for the
  badge grid.
- All legacy `level-2` root fields populated at `published` per the
  projection (§12).
- `cv_assembly.published_at` and `cv_assembly.delivered_at` for the
  green-state badges.

**Must not infer**:

- Pre-`published` populated values for any 4.3.6-owned legacy field
  (those are written atomically with the `published` CAS).
- That `dossier_state.body_html` is valid HTML for direct render in
  the UI; the dashboard renders the markdown form
  (`body_markdown`) for in-UI display, not the HTML form.
- That `cv_assembly.status` is current — it is computed by the
  rollup, not persisted continuously; readers may invoke
  `compute_status_rollup()` for fresh state, or trust the persisted
  value with a small staleness window (the §22 corpus locks the
  staleness behavior).
- That `delivered_at` will be eventually set; lag may exceed the
  4.3.6 budget without manual intervention.

### 19.3 Per-job detail APIs (`cv_assembly_job_detail`)

**May rely on**:

- Calling `project_cv_assembly_to_level2(level2_doc,
  include_null_projections=True)` for the projection-diff panel.
- The full `cv_assembly.*` subtree being returned (the API does not
  redact).
- `compute_status_rollup()` being safe to call defensively.

**Must not infer**:

- That `debug_context` fields are stable across releases (they are
  documented in the schema versioning but may shift; UI should
  render best-effort).
- That `langfuse_trace_ref` URL is reachable (Langfuse retention
  applies; the UI shows the URL but does not depend on a live
  fetch).

### 19.4 Legacy readers / batch pipeline

**May rely on**:

- `OutputPublisher.publish()` callable signature unchanged when
  `cv_assembly_source=False` (4.3.6 §9.4 rollback path).
- `gdrive_upload_service.*` callable signatures unchanged for
  editor-driven manual uploads outside the 4.3 lane.
- Legacy `level-2` root publisher fields populated at `published`.
- Legacy jobs with `cv_assembly.legacy=true` continue to render in
  the legacy dashboard cards.

**Must not infer**:

- That the 4.3 lane writes `gdrive_uploaded_at` *before*
  `published_at`. In the 4.3 lane, both fields are written in the
  same finalizer update (4.3.6 §10.2).
- That `cv_assembly.*` is absent on a job without `legacy=true` —
  some jobs are 4.3 jobs in mid-progress.

### 19.5 Dossier exporters and audit/debug tooling

**May rely on**:

- `cv_assembly.dossier_state.body_markdown` as the canonical text
  form for export.
- `cv_assembly.dossier_state.sections[]` for per-section export.
- `cv_assembly.dossier_state.validator_report` for per-section
  health and repair history.
- `cv_assembly.dossier_state.evidence_map_ref` for provenance.

**Must not infer**:

- That the dossier markdown can be parsed back to a structured
  doc; it is rendered output, not a structured representation. The
  structured representation is `dossier_state.sections[]`.
- That `validator_report.repairs_applied[]` is exhaustive of all
  per-section adjustments — only repair actions are listed; pure
  source-priority falls (§10.2) are recorded via `section.source`
  and `section.reason`, not `repairs_applied`.

## 20. Operational Catalogue

4.3.7 has no work-item stage of its own; this catalogue declares the
operational surfaces 4.3.7 *contributes to* and the existing stages
that perform the writes.

| Item | Value |
|------|-------|
| Owning subsystem(s) | `src/cv_assembly/compat/projection.py`, `src/cv_assembly/compat/rollup.py`, `src/cv_assembly/validators/dossier_validator.py`, `src/layer7/dossier_generator.py` (extended), `runner_service/utils/best_effort_dossier.py` (preserved) |
| Prerequisite artifacts | `cv_assembly.synthesis`, `cv_assembly.winner`, `cv_assembly.header_blueprint`, `pre_enrichment.outputs.*` (passthrough sources for projection), master-CV (for validator) |
| Persisted Mongo locations | `level-2.cv_assembly.dossier_state.*`, `level-2.cv_assembly.status`, `level-2.cv_assembly.status_breakdown.*`, `level-2.cv_assembly.legacy`, plus the legacy `level-2` root fields written by 4.3.6 finalizer using §12 |
| Stage-run records | None of its own. The dossier validator's substage span lives under `scout.cv_assembly.publish.render_dossier` (4.3.6 §22.1). The projection write event lives under `scout.cv_assembly.publish.projection_write` (4.3.6 §22.1). |
| Which existing stage(s) perform the writes | `publish.render.dossier` (4.3.6) writes `dossier_state.*`. `publish.finalize` (4.3.6) writes the projection keys to `level-2` root in the same atomic update as the `published` CAS. The rollup function may be invoked from any stage that needs `status` / `status_breakdown` updated. |
| Work-item lane | None (contract plan). |
| Task types | None of its own. |
| Retry / repair | The dossier validator is invoked once per dossier render; one in-validator repair pass (§11.3) is bounded. The projection module is pure and re-invoked on every retry of the finalizer. |
| Heartbeat / operator expectations | Heartbeat behavior is owned by 4.3.6. The dossier validator's per-call duration must stay under `DOSSIER_VALIDATOR_BUDGET_MS` (default 5000 ms); over-budget logs a warning. |
| Feature flags | `CV_ASSEMBLY_DOSSIER_V2_ENABLED`, `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED`, `CV_ASSEMBLY_DASHBOARD_V2_ENABLED`, `CV_ASSEMBLY_FRONTEND_STRICT_LEGACY`, `CV_ASSEMBLY_LEGACY_DISCRIMINATOR_REQUIRED` (default `true` — refuse to render `cv_assembly` jobs in 4.3 dashboards if `legacy` is absent) |
| Operator-visible success signals | `cv_assembly.status ∈ {completed, in_progress}`, `dossier_state.source = evidence_map`, `validator_report.status = pass`, projection diff non-empty in per-job detail view |
| Operator-visible failure signals | `cv_assembly.status = failed`, `dossier_state.source = missing`, `validator_report.status = failed`, `dossier_state.sections[*].status = omitted` count high, projection_schema_version_drift event |
| Downstream consumers | 4.3.6 publisher (projection + dossier body), frontend dashboards (rollup + discriminator), per-job detail API, dossier exporter, audit/debug tooling, batch pipeline (legacy projection consumers) |
| Rollback strategy | Flag-flip `CV_ASSEMBLY_DOSSIER_V2_ENABLED=false` routes dossier to legacy `DossierGenerator` + `best_effort_dossier`; flag-flip `CV_ASSEMBLY_DASHBOARD_V2_ENABLED=false` reverts UI; flag-flip `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED=false` is the emergency switch (finalizer skips projection write while still completing CAS). `cv_assembly.*` subtrees retained on rollback for audit. |
| Why 4.3.7 is not its own work-item type | The schema, projection, validator, and rollup are all consumed by other stages' work items at well-defined seams (dossier render preflight, publish finalizer, dashboard read). Wrapping any of them in a separate work item would add latency without adding control. The contract plan is the source of truth; the consumers do the work. |

## 21. Langfuse Tracing / Observability Contract

4.3.7 is a contract plan, so its tracing surface is *contributory*:
4.3.7-owned subspans and events sit *under* parent stage spans owned
by 4.3.4 / 4.3.5 / 4.3.6 / 4.3.8, and use those plans' canonical
namespaces.

### 21.1 Subspan and event ownership

| 4.3.7-owned operation | Parent stage span | Subspan / event name | Owner |
|------------------------|-------------------|----------------------|-------|
| Dossier validation | `scout.cv_assembly.publish.render_dossier` (4.3.6 §22.1) | `scout.cv_assembly.publish.render_dossier.validate` | 4.3.7 (this plan) |
| Per-section fallback decision | same | event `scout.cv_assembly.publish.render_dossier.section_fallback` | 4.3.7 |
| Whole-dossier fallback decision | same | event `scout.cv_assembly.publish.render_dossier.dossier_fallback` | 4.3.7 |
| Projection module invocation | `scout.cv_assembly.publish.projection_write` (4.3.6 §22.1) | subspan `scout.cv_assembly.publish.projection_write.compute` | 4.3.7 |
| Rollup compute (when persisted) | `scout.cv_assembly.publish.finalizer` (4.3.6 §22.1) OR caller's parent span | event `scout.cv_assembly.publish.rollup_computed` | 4.3.7 |
| Frontend / debug projection-diff read | `scout.frontend.cv_assembly.detail` (frontend stage) | event `scout.frontend.cv_assembly.detail.projection_diff_emitted` | 4.3.7 (consumed by frontend) |

Session pinning inherited from 4.3.6 / 4.3.8: `langfuse_session_id =
job:<level2_id>`.

### 21.2 Required metadata per span/event

Every 4.3.7 span/event carries the canonical 4.3.6 metadata
(`level2_id`, `job_id`, `work_item_id`, `attempt_count`,
`idempotency_key`, `lane`, `task_type`, `input_snapshot_id`) plus the
4.3.7-specific metadata below.

| Span/event | Additional metadata |
|------------|---------------------|
| `render_dossier.validate` | `validator_status`, `validator_determinism_hash`, `dossier_section_count` (always 10), `dossier_degraded_section_count`, `dossier_missing_section_count`, `dossier_omitted_section_count`, `repairs_applied_count`, `validator_duration_ms`, `checks_skipped_count` |
| `render_dossier.section_fallback` | `section_id`, `from_source` (`evidence_map`), `to_source` (`best_effort_fallback`), `reason` (≤ 240 chars), `validator_violations` (rule_id list, ≤ 5) |
| `render_dossier.dossier_fallback` | `from_source`, `to_source`, `reason`, `degraded_section_count`, `missing_section_count` |
| `projection_write.compute` | `projection_status` (`ok` \| `empty` \| `partial`), `legacy_fields_written_count`, `legacy_fields_skipped_count`, `projection_schema_version`, `legacy_mode` (`true` if `cv_assembly.legacy=true`, in which case projection returns `{}`) |
| `rollup_computed` | `status_rollup`, `publish_state_status` (composite), `dossier_source`, `legacy_mode`, `compute_duration_ms` |
| `detail.projection_diff_emitted` | `differing_field_count`, `legacy_only_field_count` (fields present on root but absent from projection — should be 0 for healthy jobs), `projection_only_field_count` |

### 21.3 Mongo `trace_ref` surfaces

| Mongo location | Source span |
|----------------|-------------|
| `cv_assembly.dossier_state.langfuse_trace_ref` | `render_dossier.validate` span id |
| `cv_assembly.publish_state.render.dossier.trace_ref` | already declared by 4.3.6 §22.5 |
| `cv_assembly.publish_state.summary.projection_trace_ref` (new in 4.3.7) | `projection_write.compute` span id; persisted by the 4.3.6 finalizer for operator one-click navigation |
| `cv_assembly.status_breakdown.last_rollup_trace_ref` (new in 4.3.7, optional) | `rollup_computed` event id; persisted only when the rollup is invoked from a finalizer (not from frontend reads) |

### 21.4 Forbidden in Langfuse / allowed in `debug_context`

Forbidden in Langfuse payloads (any span or event):

- Full dossier markdown body, full HTML body, full PDF bytes.
- Full validator report bodies (only `determinism_hash`, counts,
  status enums).
- Full projection dict (only counts, status enums, schema version).
- Full `level2_doc` (only id refs).
- Full `cv_assembly.synthesis.*` content.
- Master-CV content.

Allowed only in Mongo `debug_context`:

- Full validator report (`DossierStateDoc.validator_report` is the
  authoritative artifact; Langfuse only carries
  `determinism_hash`).
- Per-section before/after body sha pairs from
  `validator_report.repairs_applied[]`.
- The `defaults_applied[]` and `normalization_events[]` fields in
  `DossierStateDebug`.
- The full projection diff in `cv_assembly.publish_state.summary.
  projection_diff_debug` (operator audit; never mirrored).

### 21.5 Cardinality / naming safety

- Span/event names are static strings.
- `section_id` is a bounded enum (10 values).
- `rule_id` is a bounded enum derived from the validator's static
  rule registry (≤ 30 entries expected).
- `determinism_hash`, `synthesis_hash`, `body_sha256` are bounded to
  ≤ 64 chars before recording.
- Lists in metadata are capped at 5 entries; longer lists set a
  `*_truncated=true` flag.

### 21.6 Operator debugging goals

A single operator must be able to, from one Langfuse trace + one
Mongo per-job detail view:

- determine why a dossier landed at `source=partial` (which sections
  fell back, why);
- see which legacy fields were written by the projection on this
  job;
- see the `status_rollup` value and the inputs that produced it;
- jump from any `*.trace_ref` in Mongo to the corresponding
  Langfuse span in one click.

## 22. Tests and Evals

### 22.1 Unit tests

- `tests/unit/cv_assembly/test_dossier_state_schema.py` — TypedDict
  validation; section_count == 10; enum exhaustiveness.
- `tests/unit/cv_assembly/test_dossier_validator_determinism.py` —
  fixed-input → fixed-`determinism_hash` over an 8-case fixture
  spanning healthy, degraded-per-section, all-degraded, and
  all-missing scenarios.
- `tests/unit/cv_assembly/test_dossier_validator_repair_actions.py`
  — each of the four §11.3 actions exercised; repair never invokes
  LLM; one-pass bound asserted.
- `tests/unit/cv_assembly/test_projection_module.py` — field-by-field
  projection per 4.3.6 §10.1 / §12.2; null-preserving rule;
  schema-version constant.
- `tests/unit/cv_assembly/test_projection_purity.py` — function
  runs with patched `time`, `datetime`, and Mongo client = None;
  no IO, no clock reads.
- `tests/unit/cv_assembly/test_projection_idempotence.py` —
  `project(level2_doc) == project({**level2_doc,
  **project(level2_doc)})` over the corpus.
- `tests/unit/cv_assembly/test_rollup_table.py` — every row of the
  §15.2 table asserted.
- `tests/unit/cv_assembly/test_legacy_discriminator.py` — discriminator
  monotonic; default toggle behavior; mark_legacy idempotent.
- `tests/unit/cv_assembly/test_dossier_section_enum.py` — enum
  ordering matches `DossierGenerator` template; no drift.
- `tests/unit/cv_assembly/test_invariants.py` — INV1–INV15 each
  exercised on a synthetic doc.

### 22.2 Integration tests

- `tests/integration/cv_assembly/test_dossier_render_end_to_end.py`
  — `cv_assembled` → dossier validator → degraded-section repair →
  4.3.6 dossier render → publish_state populated. Uses fixture
  pdf-service.
- `tests/integration/cv_assembly/test_projection_finalizer_atomic.py`
  — runs 4.3.6 finalizer with the projection module; asserts the
  legacy fields and `published_at` appear in the same
  `findOneAndUpdate`; fault-injects a kill mid-update; on retry,
  state is consistent.
- `tests/integration/cv_assembly/test_mixed_legacy_reader.py` —
  10 legacy + 10 4.3 jobs; dashboard render returns both; default
  toggle hides legacy; manual toggle shows both grouped separately;
  no flicker (test renders twice and compares HTML byte-equal).

### 22.3 Index-migration safety tests

- `tests/integration/cv_assembly/test_index_rolling_build.py` —
  against an ephemeral local Mongo replica set, simulates the §14.2
  rolling-build sequence; asserts no write blocks during build;
  asserts `explain()` chooses the new index post-build.
- `tests/integration/cv_assembly/test_mark_legacy_backfill.py` —
  runs `scripts/mark_legacy_cv_ready.py` against a synthetic 1k-doc
  corpus; asserts batched, idempotent, no overwrite of pre-existing
  `legacy` values.

### 22.4 Fault-injection cases (under
`data/eval/validation/cv_assembly_4_3_7_state/fault_cases/`)

- Synthesis validator status = `failed` → dossier source =
  `best_effort_fallback`; per-section bodies sourced from
  `best_effort_dossier`.
- `winner.composite_score < threshold` AND `synthesis.degraded=true`
  → dossier source = `partial` (per-section fallback for
  evidence-map sections that fail validator) or
  `best_effort_fallback` (whole-dossier).
- `bullet_lineage[]` contains an unresolved achievement_id → that
  section degrades, others remain `evidence_map`.
- `pre_enrichment.outputs.research_enrichment.company_profile`
  absent → `company` section degrades.
- `cv_assembly.dossier_state.body_html` empty after validator →
  `source=missing`; 4.3.6 dossier render skipped per 4.3.6 §13.2.
- Compatibility projection schema bump: a new key added to
  `PROJECTION_KEYS` → eval emits drift warning; finalizer continues.
- `cv_assembly.legacy=true` on a partially-published job →
  projection returns `{}`, finalizer warning event, no legacy
  fields written.
- Mid-flight crash during projection write → re-run yields
  byte-identical projection; CAS lands or already-set per 4.3.6.

### 22.5 Eval corpus structure

```
data/eval/validation/cv_assembly_4_3_7_state/
├── cases/<job_id>/
│   ├── input/
│   │   ├── level2.json                  # frozen at cv_assembled (or post-publish)
│   │   ├── synthesis.json
│   │   ├── winner.json
│   │   ├── header_blueprint.json
│   │   └── master_cv_snapshot.json
│   ├── expected/
│   │   ├── dossier_state.json           # full DossierStateDoc
│   │   ├── validator_report.json        # full DossierValidatorReport
│   │   ├── projection.json              # exact projection dict (sorted keys)
│   │   ├── status_rollup.json           # {status, status_breakdown}
│   │   └── frontend_render.html         # for mixed-mode reader test
│   └── ground_truth.md
├── fixtures/
│   ├── master_cv_variants/
│   ├── presentation_contracts/
│   └── pre_enrichment_subdocs/
└── fault_cases/
```

Target: minimum 20 cases spanning role families (architecture-first
AI, delivery-first engineering, EM/Sr EM, AI-first applied ML,
platform/infra, transformation, leadership, ambiguous balanced) plus
≥ 12 fault cases per §22.4.

### 22.6 Harness

`scripts/benchmark_state_contract_4_3_7.py`:

- Runs the projection module against each case → byte-equality
  against `expected/projection.json`.
- Runs the dossier validator → byte-equality on `determinism_hash`
  and structural equality on `validator_report.json`.
- Runs the rollup function → byte-equality on `status_rollup.json`.
- Runs frontend template rendering for each lifecycle in a headless
  smoke test → byte-equality on `frontend_render.html`.
- Runs the §14.4 index-adoption check (when invoked with
  `--include-index-checks`).

### 22.7 Regression metrics and gates

| Metric | Target | Gate fires when |
|--------|--------|-----------------|
| Projection byte-equality | 1.00 | any case differs |
| Dossier_state shape compliance | 1.00 | any structural drift |
| Validator determinism_hash equality | 1.00 | any case differs across runs |
| Rollup table correctness | 1.00 | any case differs |
| Frontend smoke pass rate | 1.00 | any new lifecycle regresses |
| Mixed-mode reader byte-equality | 1.00 | flicker or layout drift |
| Legacy-field drift | 0 | any field lost or renamed across releases |
| Projection purity test pass | 1.00 | function performs IO or reads clock |
| Index-adoption check (VPS) | exit 0 | any new dashboard query falls back to COLLSCAN |
| `pre_enrichment.*` mutation by 4.3.7 code | 0 | any 4.3.7 path writes to `pre_enrichment.*` |

Block rollout if any gate fails.

## 23. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This is the live-run chain for 4.3.7.

### 23.1 Local prerequisite tests before touching VPS

- `pytest -k "cv_assembly and (dossier or projection or rollup or
  legacy or invariants)"` clean.
- `python -m scripts.benchmark_state_contract_4_3_7 --offline` clean
  (uses fixture transports).
- Projection purity test green.
- Validator determinism test green.
- Rollup table test green.

### 23.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the deployed path (file-synced).
- verify the new modules are present:
  - `src/cv_assembly/compat/projection.py`
  - `src/cv_assembly/compat/rollup.py`
  - `src/cv_assembly/validators/dossier_validator.py`
  - `src/layer7/dossier_generator.py` updated to accept
    `cv_assembly_evidence`.
- verify file-content equality against the local build via sha256
  on each module.
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`.
- verify `MONGODB_URI` env present.

### 23.3 Target job selection

- pick a real `level-2` job with:
  - `cv_assembly.synthesis.validator_report.status ∈
    {pass, repair_attempted}`,
  - `cv_assembly.winner.draft_id` and `cv_assembly.winner.grade.
    composite_score` present,
  - `cv_assembly.publish_state.render.cv.status="done"` (i.e.
    publish path has completed render at least),
  - `cv_assembly.dossier_state.source` resolvable to one of the
    four enum values,
  - `cv_assembly.legacy=false`.
- record `_id`, `synthesis_hash`, `winner_draft_id`,
  `input_snapshot_id`, `dossier_state.source`.
- prefer a job at lifecycle `published` for the projection-replay
  fast path (§23.5); a job at `cv_assembled` for the full-chain
  fallback (§23.6).

### 23.4 Upstream artifact recovery

If `cv_assembly.dossier_state` already has a partial state from a
prior aborted run:

- inspect `dossier_state.{source, sections, validator_report.status}`.
- if `validator_report.status="failed"` and operator wants to
  retry, clear the report and re-enqueue
  `publish.render.dossier`; the validator will re-run.
- if `dossier_state.source="missing"` and the publisher has already
  marked dossier render `degraded`, accept the published outcome;
  no recovery needed.

### 23.5 Single-stage run path (4.3.7 fast path)

Preferred when only 4.3.7-owned logic needs validation. A wrapper
script `/tmp/run_state_contract_<job>.py`:

- loads `.env` in Python: `from dotenv import load_dotenv;
  load_dotenv("/root/scout-cron/.env")`.
- reads `MONGODB_URI`.
- builds a minimal context for 4.3.7 ops (no full StageContext
  needed since no work item is being claimed):
  1. fetch `level2_doc` from Mongo by `_id`.
  2. invoke `validate_dossier(...)` against current
     `dossier_state` — assert `determinism_hash` matches the prior
     persisted value (stored in `dossier_state.validator_report.
     determinism_hash`).
  3. invoke `project_cv_assembly_to_level2(level2_doc,
     include_null_projections=True)` — diff against current
     legacy fields on root; print diff.
  4. invoke `compute_status_rollup(level2_doc)` — assert
     equals current `cv_assembly.status` /
     `cv_assembly.status_breakdown` (within staleness tolerance).
  5. write `reports/cv-assembly-state/<_id>/{validator_check.json,
     projection_diff.json, rollup_check.json}`.
- prints heartbeat every 15 s with: wall clock, elapsed, last
  substep, last Mongo response time.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u /tmp/run_state_contract_<job>.py \
  > /tmp/state_contract_<job>.log 2>&1 &
```

### 23.6 Full-chain path (4.3.6 + 4.3.7 together)

When 4.3.6 has not yet rendered the dossier or finalized publish:

- enqueue `publish.render.dossier` work item; it will invoke
  `validate_dossier()` and write `dossier_state.*`.
- after dossier render completes, enqueue `publish.finalize`; it
  will invoke `project_cv_assembly_to_level2()` and write the
  legacy fields atomically with the `published` CAS.
- start the publish worker per 4.3.6 §24.6.
- same `.venv`, `python -u`, Python-side `.env`, `MONGODB_URI`,
  heartbeat discipline.

### 23.7 Required launcher behavior

- `.venv` resolved (absolute path to `.venv/bin/python`).
- `python -u` unbuffered.
- `.env` loaded from Python.
- `MONGODB_URI` present.
- subprocess cwd defaults to `/tmp/state-contract-work-<job>/`
  unless repo context is required.
- inner subprocess stdout/stderr/PID logged on each heartbeat.

### 23.8 Heartbeat requirements

- stage-level heartbeat every 15 s from the wrapper.
- silence > 90 s between heartbeats is a stuck-run flag.
- the validator and projection are pure functions and should
  complete in < 5 s combined per job; over-budget logs a warning.

### 23.9 Expected Mongo writes

Fast path (§23.5) makes **no Mongo writes** by default — it is a
read-and-diff path. With `--commit`:

- `level-2.cv_assembly.dossier_state.validator_report` may be
  refreshed if the determinism_hash differs from the persisted
  value (rare; usually means input drift or a code change).
- `level-2.cv_assembly.status` and `status_breakdown` may be
  refreshed if the rollup differs from the persisted value.

Full chain (§23.6) writes per 4.3.6 §24.9, with the addition that
the legacy projection fields are now produced by §12 (sourced from
`cv_assembly.*`).

### 23.10 Expected Langfuse traces

In session `job:<level2_id>`:

- For full chain: `scout.cv_assembly.publish.render_dossier`
  parent span containing `.validate` subspan; one or more
  `.section_fallback` events per degraded section;
  `scout.cv_assembly.publish.projection_write` parent span
  containing `.compute` subspan; `rollup_computed` event under
  `.finalizer`.
- For fast path: a one-off trace under
  `scout.cv_assembly.tooling.state_contract_replay` (new namespace)
  with the four substeps as events.

### 23.11 Expected stage-run / job-run records

- Fast path: no stage_runs row written by default; with `--commit`,
  one row in a new `cv_assembly_tool_runs` collection (out of
  scope for the canonical pipeline).
- Full chain: per 4.3.6 §24.11.

### 23.12 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/state_contract_<job>.log`.
- inspect Mongo for the job's current state:
  `mongosh ... --eval 'db["level-2"].findOne({_id: ObjectId("...")},
   {cv_assembly: 1})'`.
- inspect any held lease (full chain only).
- if the prior PID is still alive, kill it; do not restart until
  it is gone.

Silence is not progress.

### 23.13 Acceptance criteria

- log ends with `STATE_CONTRACT_RUN_OK job=<id> validator=<status>
  projection_diff_count=<N> rollup_status=<status>
  trace=<url|n/a>`.
- For full chain: Mongo writes match §23.9; Langfuse trace matches
  §23.10; legacy fields populated per 4.3.6 §10.1.
- Re-running the launcher on the same `_id` is byte-equal in fast
  path (validator hash, projection diff, rollup all unchanged).
- §14.4 index-adoption check passes.

### 23.14 Artifact / log / report capture

Create `reports/cv-assembly-state/<job_id>/`:

- `run.log` — full stdout/stderr.
- `validator_check.json` — current vs persisted
  `determinism_hash`, `validator_report` summary.
- `projection_diff.json` — current legacy-root fields vs projection
  output (with `include_null_projections=True`).
- `rollup_check.json` — current vs computed `status` /
  `status_breakdown`.
- `dossier_state.json` — full current `dossier_state` dump.
- `trace_url.txt` — Langfuse parent URL (if any).
- `mongo_writes.md` — human summary of any writes (or "none" for
  read-only fast path).
- `acceptance.md` — §23.13 pass/fail.

## 24. Rollout / Migration / Compatibility

### 24.1 Rollout order

1. Ship `cv_assembly.*` TypedDicts (including `dossier_state`,
   `legacy`, `status`, `status_breakdown`), the projection module,
   the rollup module, the dossier validator, and the extended
   `DossierGenerator`. No prod writes yet.
2. Bench against §22 corpus until all gates green.
3. Backfill `cv_assembly.legacy` on historical jobs via
   `scripts/mark_legacy_cv_ready.py`.
4. Build new compound indexes via rolling background build (§14.2).
5. Run §14.4 adoption check; verify all three new dashboard
   queries hit IXSCAN.
6. Ship the frontend dashboard extensions in shadow mode (read-only
   preview of `cv_assembly.*` if present); default toggle hides
   legacy-flagged jobs.
7. Enable 4.3.4 + 4.3.5 + 4.3.6 + 4.3.7 in canary; new jobs
   populate `cv_assembly.dossier_state` via the validator;
   projection writes legacy fields atomically with the `published`
   CAS.
8. Verify compatibility across frontend + operator UI + batch
   pipeline on canary (1 job, 5 jobs, 25 jobs, 100% with 72h soak
   between steps).
9. Flip `CV_ASSEMBLY_DOSSIER_V2_ENABLED=true` for every new
   `cv_assembled` job.
10. Flip `CV_ASSEMBLY_DASHBOARD_V2_ENABLED=true` and update the
    default dashboard groupings to first-class 4.3 lifecycle
    categories.

### 24.2 Required flags

| Flag | Default | Post-cutover | Notes |
|------|---------|--------------|-------|
| `CV_ASSEMBLY_DOSSIER_V2_ENABLED` | false | true | Gates evidence-map dossier path |
| `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED` | true | true | Atomic projection in 4.3.6 finalize |
| `CV_ASSEMBLY_DASHBOARD_V2_ENABLED` | false | true | Frontend uses new groupings |
| `CV_ASSEMBLY_FRONTEND_STRICT_LEGACY` | false | false | If true, forces legacy rendering regardless of new state |
| `CV_ASSEMBLY_LEGACY_DISCRIMINATOR_REQUIRED` | false | true | Refuse to render `cv_assembly` jobs in 4.3 dashboards if `legacy` field is absent |
| `DOSSIER_VALIDATOR_BUDGET_MS` | 5000 | 5000 | Per-call duration warning threshold |
| `DOSSIER_EVIDENCE_MAP_MIN_COMPOSITE` | 0.55 | 0.55 | Threshold for `evidence_map` source when `synthesis.degraded=true` |
| `LANGFUSE_CV_ASSEMBLY_STATE_TRACING_ENABLED` | false | true | Enables 4.3.7-owned subspans/events |

### 24.3 Backfill

- No historical mutation of `cv_assembly.*` content. Pre-4.3 jobs
  keep their legacy fields and do not grow a `cv_assembly.*`
  subtree beyond the discriminator stub.
- `scripts/mark_legacy_cv_ready.py` adds
  `cv_assembly={legacy:true, schema_version:"4.3.7.1"}` on
  historical jobs so dashboards can filter them out of 4.3
  counters. The script is idempotent and batched.
- Once `cv_assembly.legacy` is present on every doc, the §14
  indexes can be built; until then, the index would have an
  unbounded null-leading-key scan.

### 24.4 Rollback

- Flag-flip `CV_ASSEMBLY_DOSSIER_V2_ENABLED=false` routes dossier
  back to `DossierGenerator` legacy path (and
  `best_effort_dossier.py` as the fallback).
- Flag-flip `CV_ASSEMBLY_DASHBOARD_V2_ENABLED=false` reverts UI.
- Flag-flip `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED=false` is the
  emergency switch; finalizer skips projection write while still
  completing the `published` CAS. Alert fires.
- `cv_assembly.*` subtrees are preserved on rollback for audit.
- New compound indexes can remain in place; they are cheap. Drop
  only if space is genuinely a concern.
- The `cv_assembly.legacy` field is left in place on all docs; it
  is harmless when unread.

## 25. Open-Questions Triage

| Question | Triage | Resolution / recommendation |
|----------|--------|-----------------------------|
| Should `cv_assembly.*` move to a separate `cv_assembly` collection if document size approaches 1MB? | safe-to-defer | Keep inline for v1. Current expected size is < 200KB per job (3 drafts × ~30KB + grades + synthesis + publish_state + dossier_state ≈ 150KB). Revisit only if `db["level-2"].stats({scale:1024})` shows avgObjSize crossing 600KB or any single doc exceeds 1MB. The collection split would require a second projection module and a new index migration; not worth it until we measure pressure. |
| Should the dossier template version be bumped to v2 for 4.3? | safe-to-defer | Keep `template_version="dossier_v1.1"` with metadata additions (`pattern_label`, synthesis improvement delta) only. A v2 template is a separate editorial task; the current 10-section structure is correct and operator-validated. Revisit if §22 reviewer-usefulness scores drop. |
| Should operator UI allow manual pick of a non-winner draft for publishing? | safe-to-defer | Deferred to 4.4 CV Editor. The 4.3.7 contract supports it (the per-job detail view exposes all three drafts), but the publisher path assumes `winner.draft_id` is the source. Adding an editor-driven override means a new task type (`publish.republish_with_alternate_winner`) and is out of 4.3.7 scope. |
| Should the projection module also project a public-safe subset for external dashboards? | safe-to-defer | No external dashboards exist today. When they do, add `project_cv_assembly_to_public(level2_doc) -> dict` as a sibling function with a separate `PUBLIC_PROJECTION_KEYS` constant. |
| Should `cv_assembly.status` and `status_breakdown` be persisted continuously or computed on read? | resolved (must-resolve) | Both — finalizers persist after their CAS completes (cheap); readers may also call `compute_status_rollup()` defensively to refresh stale state. Persisted state is a snapshot of the last finalizer; readers that need real-time accuracy compute fresh. |
| Should the dossier validator share its rule registry with the 4.3.4 evidence-lineage validator? | resolved (must-resolve) | Partially — both reference the same master-CV resolver and the same `evidence_refs[]` shape. The dossier validator's *rule_ids* are a superset (sections-aware) and live in `dossier_validator.py`'s registry. Sharing the resolver but not the registry keeps section-specific rules locally inspectable. |
| Should `cv_assembly.legacy` be a string instead of a boolean (e.g. `"v0_legacy"`, `"v1_4_3"`, `"v2_future"`)? | resolved (safe-to-defer) | Boolean for v1. A string-valued discriminator is cleaner if we get a v2 lane, but boolean serves today's only distinction. Migration to string is a separate index change if it ever happens. |
| Should the rollup table be data-driven (config file) or code? | resolved (safe-to-defer) | Code in `rollup.py` — the table has a small, fixed shape and is exercised by the §22 unit tests. A config file adds a layer without simplifying anything; revisit only if rollup rules diverge per role family (no current evidence they should). |

## 26. Primary Source Surfaces

- `src/layer7/dossier_generator.py` (extended per §10)
- `src/layer7/output_publisher.py` (consumes projection per 4.3.6 §10.2)
- `runner_service/utils/best_effort_dossier.py` (preserved)
- `src/common/repositories/atlas_repository.py` (new indexes per §14)
- `frontend/repositories/discovery_repository.py` (heartbeat + per-job detail)
- `frontend/intel_dashboard.py` (new routes + filters)
- `frontend/templates/` (new partials per §13.4)
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.3.6-publisher-renderer-and-remote-delivery-integration.md`
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md`
- `plans/iteration-4.3-candidate-evidence-assembly-grading-and-publishing.md`
- `docs/current/missing.md`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md`

## 27. Implementation Targets

- `src/cv_assembly/models.py` — add `DossierStateDoc`,
  `DossierSectionDoc`, `DossierValidatorReport`,
  `DossierStateDebug`, `CvAssemblyStatusBreakdownDoc`,
  `SectionEnum`, `DossierSourceEnum`, `CvAssemblyStatusEnum`.
- `src/cv_assembly/compat/projection.py` (new) —
  `project_cv_assembly_to_level2(level2_doc, *,
  include_null_projections=False, tracer=None) -> dict`,
  `build_pipeline_run_entry(...) -> dict`,
  `PROJECTION_KEYS` constant, `PROJECTION_SCHEMA_VERSION` constant.
- `src/cv_assembly/compat/rollup.py` (new) —
  `compute_status_rollup(level2_doc) -> tuple[str, dict]`.
- `src/cv_assembly/compat/typeddicts.py` (new) — MongoDB TypedDicts
  for `cv_assembly.*` subtree (re-exports `models.py` types in a
  Mongo-friendly shape).
- `src/cv_assembly/validators/dossier_validator.py` (new) —
  `validate_dossier(...)` per §11, with internal rule registry,
  determinism harness, and §11.3 repair actions.
- `src/layer7/dossier_generator.py` — accept `cv_assembly_evidence`
  input; per-section degradation per §10.2; emit
  `DossierStateDoc`.
- `src/common/repositories/atlas_repository.py` — register two new
  indexes per §14.1.
- `frontend/repositories/discovery_repository.py` — new
  `cv_assembly_job_detail()`, heartbeat 4.3 card,
  legacy-discriminator filter.
- `frontend/intel_dashboard.py` — new routes
  `/discovery/cv-assembly`, `/discovery/cv-assembly/<level2_id>`;
  extend `/discovery/results` with new lifecycles and legacy
  toggle.
- `frontend/templates/` — three-draft side-by-side, per-surface
  publish grid, 10-section dossier badge grid, projection diff
  panel.
- `scripts/benchmark_state_contract_4_3_7.py` (new) — §22.6 harness.
- `scripts/mark_legacy_cv_ready.py` (new) — §24.3 backfill;
  batched, idempotent.
- `scripts/cv_assembly_index_adoption_check.py` (new) — §14.4.
- `scripts/cv_assembly_replay_projection.py` (new) — §12.5
  operator tool; dry-run by default, `--commit` to write.
- `data/eval/validation/cv_assembly_4_3_7_state/` (new) — corpus
  per §22.5.
- `tests/unit/cv_assembly/test_dossier_validator_determinism.py`
  (new), `test_projection_module.py` (new), `test_projection_purity.py`
  (new), `test_projection_idempotence.py` (new), `test_rollup_table.py`
  (new), `test_legacy_discriminator.py` (new),
  `test_dossier_state_schema.py` (new), `test_invariants.py` (new).
- `tests/integration/cv_assembly/test_dossier_render_end_to_end.py`
  (new), `test_projection_finalizer_atomic.py` (new),
  `test_mixed_legacy_reader.py` (new),
  `test_index_rolling_build.py` (new),
  `test_mark_legacy_backfill.py` (new).
- `docs/current/architecture.md` — document the `cv_assembly.*`
  subtree canonically (point at this plan).
- `docs/current/cv-generation-guide.md` — reference the projection
  map (point at §12).
