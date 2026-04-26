# Iteration 4.3 Plan: Candidate Evidence, Multi-Draft Assembly, Grading, and Publishing

Author: Codex planning pass on 2026-04-23
Parent plans:
- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`
- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`

Status: new umbrella plan; adds the candidate-aware lane after `cv_ready`.

---

## 1. Executive Summary

Iteration 4 made preenrichment a stage-level Mongo DAG that terminates at
`lifecycle="cv_ready"`. Iteration 4.2 added the pre-candidate
`presentation_contract` on top of that — evaluator lenses, pain/proof mapping,
dimension weights, and truth-constrained emphasis rules — so the job side of
the pipeline now speaks one coherent language.

Iteration 4.3 is the next slice after `cv_ready`. It turns the
candidate-agnostic `presentation_contract` into real, candidate-aware CV
drafts, grades them, synthesizes the best version, and publishes the result
through the existing Layer 7 output publisher, the Playwright PDF service,
n8n, Google Drive, Google Sheets, and the dossier path.

Crucially, 4.3 also upgrades the **master-CV blueprint** itself: the role
records, project records, and taxonomies that feed candidate-aware generation
become much richer, more explicitly metadata-bearing, and fully provenance-
tagged. Without that substrate upgrade, the candidate-aware stages cannot stay
grounded in truth.

4.3 is not a redesign of Layer 6 V2 or Layer 7. It is an additive lane that
wraps them with a candidate-aware orchestration layer and a new set of
pre-generation artifacts (header blueprint, evidence map, pattern selection)
and post-generation artifacts (multi-draft set, grade set, best-version
synthesis). The canonical rendering path remains the Playwright-backed
pdf-service; the canonical delivery path remains Layer 7 + n8n + Drive/Sheets.

By the end of iteration 4.3, the primary downstream path must be:

```text
level-2.lifecycle=cv_ready
  -> work_items(cv.header_blueprint)
  -> work_items(cv.pattern_selection)
  -> work_items(cv.draft_assembly)      x 3 drafts, fanned out
  -> work_items(cv.grade_select_synthesize)
  -> level-2.lifecycle=cv_assembled
  -> work_items(publish.render)
  -> work_items(publish.upload.drive)
  -> work_items(publish.upload.sheets)
  -> level-2.lifecycle=published
  -> level-2.lifecycle=delivered        (optional, n8n ACK)
```

## 2. Mission

Turn every `cv_ready` job into a truthful, evaluator-aware, high-quality CV
that was chosen from a grounded three-draft competition and published through
the existing Layer 7 / PDF / Drive / Sheets / n8n path, with full master-CV
provenance, first-class Langfuse tracing, and a dossier that reflects the
same facts that went into the CV.

## 3. Objectives

1. Upgrade the master-CV blueprint so every role, project, and taxonomy is
   rich enough to drive candidate-aware generation without loss of truth or
   provenance (4.3.1).
2. Produce a structured, pre-prose header blueprint for every job, grounded
   only in master-CV evidence and the 4.2 `presentation_contract` (4.3.2).
3. Select the top three ideal CV patterns implied by the presentation
   contract and bind each pattern to a concrete master-CV evidence map
   (4.3.3).
4. Assemble three candidate-aware CV drafts — one per pattern — through the
   existing Layer 6 V2 pipeline, with pattern-scoped inputs that keep
   generation grounded in master-CV truth (4.3.4).
5. Grade the three drafts using a deterministic rubric plus a grading LLM
   (`gpt-5.4-mini` default), pick the best, and synthesize an improved
   best-version by selectively promoting strong fragments from the other two
   drafts without violating evidence boundaries (4.3.5).
6. Render, upload, and publish the winning CV through the existing Layer 7
   output publisher, Playwright-backed PDF service, n8n webhook, Google
   Drive, and Google Sheets, with the dossier refreshed from the same
   candidate-aware evidence map (4.3.6).
7. Update the dossier and MongoDB `level-2` state contract so the new
   candidate-aware outputs are stored gracefully, with compatibility
   projections for existing readers and honest partial-completion semantics
   (4.3.7).
8. Treat Langfuse tracing and eval/benchmark corpora as first-class concerns
   across the whole family, not afterthoughts (4.3.8).

## 4. Success Criteria

Iteration 4.3 is done when all of the following are true in production:

### 4.1 Functional

- Every `cv_ready` job passes through the 4.3 lane and either reaches
  `published` or a well-defined failure/deadletter state with operator-
  visible diagnosis.
- Every produced CV cites its master-CV evidence back to specific role ids,
  project ids, achievement ids, and (where applicable) achievement variant
  ids.
- No CV or dossier contains fabricated titles, fabricated metrics, AI-depth
  claims exceeding `classification.ai_taxonomy.intensity`, or leadership
  scope claims exceeding master-CV evidence.
- The 4.3 lane works end-to-end for three prototypical role families
  (applied-AI engineering, engineering leadership, platform/architect) on
  the curated eval set.

### 4.2 Architectural

- Layer 6 V2 per-role generation, stitching, grading, and improvement
  surfaces are preserved — 4.3 composes on top of them instead of replacing
  them.
- Layer 7 output publisher, `gdrive_upload_service`, pdf-service, and n8n
  webhook remain the canonical delivery path.
- `level-2` remains authoritative. All new candidate-aware outputs live
  under a new `cv_assembly.*` namespace and (for publishing) the existing
  `level-2` publisher fields, with explicit compatibility projections for
  any reader that still expects the legacy shape.
- Preenrich state on `level-2.pre_enrichment.*` is never mutated by 4.3
  stages. 4.3 only appends.

### 4.3 Observability

- Every 4.3 stage emits Langfuse traces under the canonical
  `scout.cv.*` / `scout.publish.*` namespaces with `job:<level2_id>`
  session pinning.
- Per-draft, per-grade, per-synthesis decisions are inspectable in Langfuse
  and in Mongo `debug_context`, with trace refs carried on every stage run
  record.
- A single operator can debug any one job from `cv_ready` to `published`
  end-to-end, across master-CV evidence, pattern selection, three drafts,
  grade rationales, synthesis choice, render failures, upload outcomes, and
  dossier persistence — without touching the LLM providers directly.

### 4.4 Safety / anti-hallucination

- A deterministic evidence validator runs before every Mongo persist for
  CV text, header blueprint, pattern evidence map, and dossier body.
- No candidate-aware stage may write a claim that cannot be traced to a
  master-CV entry or an explicitly-whitelisted derived statement.
- Truth constraints from `truth_constrained_emphasis_rules` are enforced
  deterministically, not only asked of the LLM.

### 4.5 Eval / benchmark

- A frozen eval corpus under `data/eval/validation/cv_assembly_4_3_*/`
  exists and regresses cleanly between runs.
- Regression gates block rollout when grading rubric scores drop, when
  evidence-leakage incidents rise, or when any required stage stops
  emitting trace refs.

## 5. Non-Goals

Iteration 4.3 explicitly does not:

- Redesign the Layer 6 V2 per-role generator, variant selector, stitcher,
  grader, or improver. 4.3 composes on top; those files change only where
  adapter seams are genuinely needed.
- Redesign the Layer 7 output publisher, `gdrive_upload_service`, or
  pdf-service. 4.3 changes them only to accept the new multi-draft input
  and to emit additional trace metadata.
- Replace `level-2` or move authoritative state elsewhere.
- Replace the Playwright/Chromium path. The pdf-service on the VPS remains
  the canonical renderer.
- Replace n8n for Drive/Sheets uploads. The same webhook contract is used.
- Invent new evaluator intelligence — all of that remains in 4.2
  `stakeholder_surface` and `presentation_contract`.
- Add a separate application-tracking collection. Publisher state remains
  on `level-2`.
- Generate public data about third-party people. All candidate framing
  uses master-CV only.
- Extend the CV Editor UI (a separate follow-up once 4.3 is stable).

Deferred to iteration 4.4+:

- Interview-prep regeneration keyed off the 4.3 evidence map.
- CV Editor surface that lets a human edit the winning draft before
  publish.
- Multi-candidate (non-Taimoor) support in the master-CV loader.
- A/B experimentation across grading models.

## 6. Why This Iteration Exists

The current path after `cv_ready` today is:

- a single Layer 6 V2 generation pass;
- a single grade and single-pass improvement;
- a publisher that ships whatever Layer 6 V2 produced;
- a dossier that was produced in parallel, sometimes from the
  best-effort fallback;
- and master-CV data that is good but under-described for the kind of
  evaluator-aware, pattern-driven presentation the 4.2 contract now
  demands.

That is under-powered in three specific ways that 4.3 addresses:

1. **One draft is not enough.** The best CV for an architecture-heavy AI
   job is not the best CV for an engineering-leadership job, even from the
   same candidate. The `presentation_contract` now carries enough signal to
   pick a pattern, but the system still only generates one draft. 4.3 runs
   three pattern-anchored drafts and picks the best.
2. **Master-CV is too thin to drive evaluator-aware generation safely.**
   Roles and projects currently encode skills and achievements, but not
   scope, seniority signals, stakeholder exposure, domain depth, operating
   model, credibility markers, or evidence confidence. Without those
   metadata, candidate-aware generation either hallucinates or strips
   everything down to the lowest-common-denominator skill list.
3. **Header and evidence wiring is implicit.** Today the
   `HeaderGenerator` derives the profile/tagline/key-achievements from the
   stitched CV after generation. That is too late — the evaluator-aware
   header identity should be decided before prose, from an explicit
   blueprint bound to master-CV evidence. 4.3 introduces that blueprint.

## 7. Stage Boundary And Ownership

### 7.1 What stays in preenrich (`pre_enrichment.*`)

Everything upstream of `cv_ready`:

- `jd_facts`, `classification`, `application_surface`, `research_enrichment`
- `stakeholder_surface`, `pain_point_intelligence`, `presentation_contract`
- `job_inference`, `cv_guidelines`, `blueprint_assembly`

Iteration 4.3 does not mutate any of these fields. It reads them only.

### 7.2 What 4.3 owns (`cv_assembly.*` on `level-2`)

All new candidate-aware artifacts live under `level-2.cv_assembly.*`:

- `cv_assembly.header_blueprint` (4.3.2)
- `cv_assembly.pattern_selection` (4.3.3)
- `cv_assembly.drafts[]` (4.3.4, exactly three entries)
- `cv_assembly.grades[]` (4.3.5)
- `cv_assembly.winner` (4.3.5, ref to winning draft)
- `cv_assembly.synthesis` (4.3.5, best-version)
- `cv_assembly.publish_state` (4.3.6, per-surface publish outcomes)
- `cv_assembly.dossier_state` (4.3.7, dossier linkage)

### 7.3 What 4.3 extends, not replaces

- `src/layer6_v2/orchestrator.py` — gains a **pattern-scoped mode**: when
  invoked with a `PatternContext` (pattern id, evidence map, scoped header
  blueprint, scoped presentation slice), it runs a single draft under
  that context. Without a `PatternContext`, it runs as today.
- `src/layer6_v2/header_generator.py` — gains a **blueprint-first mode**:
  if a `HeaderBlueprint` is supplied, the generator emits prose aligned to
  the blueprint instead of re-deriving it from the stitched CV.
- `src/layer6_v2/variant_selector.py` — gains a **pattern bias** input so
  variant selection can favor achievement variants whose metadata matches
  the current pattern's dimension weights and proof categories.
- `src/layer7/output_publisher.py` — gains a **best-version input**: it
  accepts the winning synthesis, not whatever was last written to disk,
  and emits the publish state to `cv_assembly.publish_state`.
- `src/layer7/dossier_generator.py` — gains a **candidate-evidence mode**:
  when a `pattern_selection` and `winner` are available, the dossier uses
  the same evidence ids instead of re-deriving them.

### 7.4 What 4.3 updates in master-CV

4.3.1 extends the master-CV schema to include new role metadata, new project
metadata, and new taxonomy files. The existing `data/master-cv/roles/*.md`
and `data/master-cv/projects/*.md` remain authoritative for prose content;
a parallel metadata layer (either alongside the markdown or as `*.meta.json`
sidecars — decided in 4.3.1) adds the new fields. The loader
(`src/layer6_v2/cv_loader.py`, `src/common/master_cv_store.py`) is extended
to read both and expose the new fields.

## 8. Target Architecture

### 8.1 Lane

4.3 introduces the `cv_assembly` lane in `work_items` (new
`lane="cv_assembly"` value), plus the `publish` lane:

- `cv_assembly` lane task types:
  - `cv.header_blueprint`
  - `cv.pattern_selection`
  - `cv.draft_assembly`   (fanned out three times per job)
  - `cv.grade_select_synthesize`
- `publish` lane task types:
  - `publish.render.cv`
  - `publish.render.dossier`
  - `publish.upload.drive`
  - `publish.upload.sheets`

Both lanes reuse the iteration-4 stage registry, work-item schema, lease
semantics, idempotency key format, retry/backoff, dead-worker sweeper,
snapshot-invalidation rule, and stage-outbox pattern verbatim. The only
change is the set of task types and the downstream DAG edges.

### 8.2 DAG edges

```text
cv_ready
  -> cv.header_blueprint
  -> cv.pattern_selection
  -> cv.draft_assembly (pattern_id=1)
     cv.draft_assembly (pattern_id=2)
     cv.draft_assembly (pattern_id=3)                [fan-out]
  -> cv.grade_select_synthesize                      [fan-in barrier]
  -> cv_assembled
  -> publish.render.cv
     publish.render.dossier                          [fan-out]
  -> publish.upload.drive                            [fan-in on renders]
  -> publish.upload.sheets
  -> published
  -> delivered (optional, on n8n ACK)
```

Fan-out rules:

- `cv.pattern_selection` emits exactly three `cv.draft_assembly` children,
  one per selected pattern id (indices 0, 1, 2). Idempotency key includes
  the pattern id so re-enqueues collapse.
- `cv.grade_select_synthesize` is a barrier: it only claims when all three
  draft-assembly work items are `status=done` on the current
  `input_snapshot_id`.
- `publish.render.cv` and `publish.render.dossier` fan out from
  `cv_assembled`.
- `publish.upload.drive` is a barrier on both renders.

### 8.3 Control plane

Same as iteration 4:

- Mongo = truth for stage state, leases, retries, dependencies.
- `systemd` host workers = execution.
- Langfuse = observability sink.
- pdf-service = rendering boundary (dedicated HTTP service with Playwright/
  Chromium on the VPS).

New `systemd` units (one per task type, same template):

- `scout-cv-assembly-worker@header_blueprint.service`
- `scout-cv-assembly-worker@pattern_selection.service`
- `scout-cv-assembly-worker@draft_assembly.service` (scaled to 3)
- `scout-cv-assembly-worker@grade_select_synthesize.service`
- `scout-publish-worker@render_cv.service`
- `scout-publish-worker@render_dossier.service`
- `scout-publish-worker@upload_drive.service`
- `scout-publish-worker@upload_sheets.service`

### 8.4 Lifecycle extension

Extends iteration-4 lifecycle:

- `selected` → `preenriching` → `cv_ready`
  → `cv_assembling` → `cv_assembled`
  → `publishing` → `published`
  → `delivered` (optional)
- plus `failed` / `deadletter` as today.

Terminal boundary rules:

- `cv_assembled` = winner chosen, synthesis persisted, renders not yet
  done. Safe to pause publishing while keeping the winning CV available.
- `published` = both renders uploaded to Drive and Sheets row logged.
- `delivered` = n8n has acknowledged, `gdrive_uploaded_at` set. Optional;
  the absence of `delivered` does not block anything.

Each transition is a CAS on `lifecycle` plus `cv_assembly.<phase>_at`,
identical pattern to iteration-4 `cv_ready_at`.

### 8.5 Canonical `cv_assembly.*` on `level-2`

```text
cv_assembly {
  schema_version,
  input_snapshot_id,                  # sha256(jd_checksum || master_cv_checksum || pc_checksum)
  master_cv_checksum,                 # checksum over master-CV inputs the drafts saw
  presentation_contract_checksum,     # checksum over presentation_contract
  stage_states { <task>: { ... } },   # mirrors pre_enrichment.stage_states shape
  header_blueprint { ... },           # 4.3.2
  pattern_selection { ... },          # 4.3.3
  drafts [ { ... } x3 ],              # 4.3.4
  grades [ { ... } x3 ],              # 4.3.5
  winner { draft_id, score, rationale_ref },
  synthesis { ... },                  # 4.3.5 best-version
  publish_state { ... },              # 4.3.6
  dossier_state { ... },              # 4.3.7
  assembled_at,                       # CAS guarded
  published_at,                       # CAS guarded
  delivered_at                        # CAS guarded (optional)
}
```

### 8.6 Compatibility projections

Existing readers of `level-2` publisher fields
(`cv_text`, `cv_path`, `cv_reasoning`, `cover_letter`, `generated_dossier`,
`drive_folder_url`, `sheet_row_id`, `gdrive_uploaded_at`,
`dossier_gdrive_uploaded_at`) continue to work unchanged. On successful
publish, `output_publisher.publish()` still writes these fields as a
compatibility projection of `cv_assembly.winner` + `cv_assembly.synthesis` +
`cv_assembly.publish_state`. 4.3.7 enumerates the projection map.

## 9. Canonical Invariants Across 4.3

These are load-bearing rules the subplans all inherit:

### 9.1 Truth-first invariants

- Every candidate-aware string output must be traceable to a
  `master_cv_ref` or an explicit `derived_marker` that names the derivation
  rule. Prose without refs is rejected deterministically before persist.
- Every structured claim in `header_blueprint` and `pattern_selection.
  evidence_map` must carry `(role_id | project_id, achievement_id?,
  variant_id?, source_fragment_ref?)`.
- A deterministic evidence validator runs before persist in every
  candidate-aware stage (4.3.2, 4.3.3, 4.3.4, 4.3.5).
- Title selection is bounded by
  `ideal_candidate_presentation_model.acceptable_titles` plus
  `document_expectations.title_strategy`. No other titles are permitted.
- AI depth claims are bounded by
  `classification.ai_taxonomy.intensity`.
- Leadership scope claims are bounded by role-metadata scope markers
  (team size, direct reports, budget, cross-org reach) introduced in 4.3.1.
- Public CV metadata is bounded by `candidate_facts.display_policy`
  introduced in 4.3.1. A fact may be true in the store and still be forbidden
  from the default public CV surface.
- A skill may appear in `core_competencies` only when the 4.3.1 skill
  evidence map authorizes the `core_competency` surface. This is a hard
  downstream contract, not a stylistic preference.
- A role or project proof fragment may appear in the header or summary only
  when 4.3.1 marks it safe for `header_proof` or `summary_safe`. Otherwise it
  stays in detailed experience only.

### 9.2 Separation of concerns

- `header_blueprint` emits blueprint structure, not prose.
- `pattern_selection` emits pattern rationale and evidence map, not prose.
- `draft_assembly` emits one CV per pattern — this is the only stage that
  emits prose.
- `grade_select_synthesize` emits grades, winner, and a synthesized best
  version (which is again prose).
- `publish.*` emits no prose — only rendering and upload actions.

### 9.3 Fail-open / fail-closed

Fail open:

- When `presentation_contract` is partial or unresolved, 4.3 stages
  degrade to role-family defaults sourced from
  `classification.primary_role_category` and record the fallback in
  `debug_context`.
- When one draft fails assembly, the winner is chosen from the remaining
  drafts and a deterministic repair retry is attempted once.
- When n8n upload fails transiently, retries follow iteration-4 backoff;
  publishing remains `in_progress` until exhaustion.

Fail closed:

- When all three drafts fail the deterministic evidence validator, the
  job goes to `failed`, not `published`. No fabricated CV is ever
  published.
- When the pdf-service is unavailable past retry budget, the job goes
  to `failed`. There is no local HTML fallback for delivery.
- When dossier body fails the evidence validator, the CV can still
  publish; the dossier enters a `degraded` state under
  `cv_assembly.dossier_state`.

### 9.4 Master-CV immutability per run

Every 4.3 stage snapshots `master_cv_checksum` into its work-item payload
at claim time. Mid-flight master-CV edits invalidate in-flight work via
the iteration-4 snapshot-invalidation mechanism (4.3.1 §7.3), identical in
shape to JD snapshot invalidation.

### 9.5 Langfuse tracing contract (summary)

Every 4.3 stage:

- pins `langfuse_session_id = job:<level2_object_id>` verbatim;
- uses the canonical `scout.cv.*` / `scout.publish.*` namespace;
- reuses `PreenrichTracingSession` via a new `CvAssemblyTracingSession`
  and `PublishTracingSession` wrapper (same seam, same metadata builder);
- emits metadata-first payloads (counts, refs, confidence bands) and
  never ships full CV prose into Langfuse;
- writes `trace_id` and `trace_url` into `cv_assembly.stage_states.<task>.
  trace_ref` so operators can jump from Mongo UI into Langfuse.

Full contract in 4.3.8.

## 10. Why This Decomposition

Eight subplans; one concern per subplan; orthogonal failure modes.

This plan set also inherits the manual editorial method in
`reports/4.3-manual-master-cv-review-methodology.md`, which translates the
eval corpus plus the 4.2 implementation into:

- persona-family priors,
- header/disclosure policy,
- competency-surface authorization,
- ATS-safe structure,
- and the manual 4.3.1 review order.

### 10.1 Why master-CV blueprint is its own plan (4.3.1)

The substrate is doing double duty: it is both the evidence base for
candidate-aware generation and the schema everyone upstream (CV Editor,
dossier, Sheets log) reads from. Evolving it deserves a dedicated plan with
its own migration and backfill strategy.

### 10.2 Why header blueprint is its own plan (4.3.2)

Headers are identity. Getting identity wrong is a bigger failure mode than
any other single section. The blueprint captures identity before prose, so
three later drafts share one truthful identity rather than each inventing
their own.

### 10.3 Why pattern selection is its own plan (4.3.3)

Picking the top-3 patterns and binding them to concrete evidence is a
reasoning task with its own schema, cost profile, and eval needs. Folding
it into draft assembly would make pattern choice invisible to the operator
and uncheckable by eval.

### 10.4 Why draft assembly is its own plan (4.3.4)

Draft assembly is the one stage that runs Layer 6 V2 — three times, in
parallel, with pattern-scoped inputs. It has its own parallelism,
resource, and repair semantics that do not belong in a grading document.

### 10.5 Why grading + synthesis is one plan (4.3.5)

Grading, selection, and synthesis share the same rubric, the same eval
frame, and the same anti-hallucination guardrails. Splitting them would
let synthesis drift from the very rubric that picked the winner.

### 10.6 Why publisher + renderer + remote is one plan (4.3.6)

The whole delivery path (render → Drive → Sheets → n8n ACK) is a single
failure domain. Splitting renderer and uploader across plans would hide
the dependency between them and duplicate rollout concerns.

### 10.7 Why dossier + Mongo state is its own plan (4.3.7)

Dossier is a parallel output with the same evidence base and different
rendering requirements. Mongo `level-2` updates touch every consumer
(frontend, operator UI, application tracking). Both deserve a single
plan to hold the compatibility and backfill contract.

### 10.8 Why evals + tracing + rollout is its own plan (4.3.8)

Without dedicated corpora and a disciplined rollout, 4.3 silently
regresses. A shared plan owns corpus structure, regression gates, and the
canary staircase across the entire family so the sub-plans do not each
re-invent it.

## 11. Primary Source Surfaces

Upstream (read-only for 4.3):

- `src/preenrich/stage_registry.py`, `src/preenrich/stage_worker.py`,
  `src/preenrich/sweepers.py`, `src/preenrich/dag.py`
- `src/preenrich/blueprint_models.py`, `src/preenrich/blueprint_prompts.py`
- `src/preenrich/stages/jd_facts.py`, `classification.py`,
  `research_enrichment.py`, `stakeholder_surface.py`,
  `pain_point_intelligence.py`, `presentation_contract.py`,
  `blueprint_assembly.py`
- `src/pipeline/tracing.py` (`PreenrichTracingSession`)

Candidate-aware surfaces (read/extend for 4.3):

- `src/layer6_v2/orchestrator.py`, `role_generator.py`,
  `variant_selector.py`, `variant_parser.py`, `stitcher.py`,
  `header_generator.py`, `grader.py`, `improver.py`, `cv_loader.py`,
  `types.py`
- `src/layer6_v2/prompts/role_generation.py`, `header_generation.py`,
  `grading_rubric.py`, `shared.py`
- `src/common/master_cv_store.py`
- `src/common/unified_llm.py`, `src/common/llm_config.py`

Publisher / delivery surfaces (read/extend for 4.3):

- `src/layer7/output_publisher.py`, `src/layer7/dossier_generator.py`
- `runner_service/utils/best_effort_dossier.py`
- `src/services/gdrive_upload_service.py`
- `src/services/batch_pipeline_service.py`
- `pdf_service/app.py`, `Dockerfile.pdf-service`,
  `docker-compose.local.yml`, `docker-compose.ingest.yml`
- `n8n/cron/`, `n8n/workflows/`
- `runner_service/routes/operations.py`

Data surfaces:

- `data/master-cv/roles/`, `data/master-cv/projects/`,
  `data/master-cv/role_metadata.json`,
  `data/master-cv/role_skills_taxonomy.json`
- `data/eval/validation/` (existing), plus new
  `data/eval/validation/cv_assembly_4_3_*/`
- `evals/stakeholder_surface_4_2_1/` (reference shape)

Documentation surfaces:

- `docs/current/cv-generation-guide.md`
- `docs/current/architecture.md`
- `docs/current/jd-annotation-system.md`
- `docs/current/operational-development-manual.md`

## 12. Rollout And Migration

### 12.1 Rollout order

1. Ship 4.3.1 master-CV blueprint schema, loader extension, and backfill
   scripts. Ship behind `MASTER_CV_BLUEPRINT_V2_ENABLED=false` by default.
   Run backfill dry-run, then real run.
2. Ship 4.3.2 header blueprint stage, fully behind
   `CV_ASSEMBLY_HEADER_BLUEPRINT_ENABLED`. No downstream consumption yet.
   Bench it on the eval corpus.
3. Ship 4.3.3 pattern selection stage, behind
   `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED`. No downstream consumption
   yet. Bench.
4. Ship 4.3.4 draft assembly stage behind
   `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED`, shadow-mode: produce drafts but
   do not overwrite the existing single-pass Layer 6 V2 result. Compare
   outputs on canary jobs.
5. Ship 4.3.5 grading + synthesis behind
   `CV_ASSEMBLY_GRADE_SELECT_ENABLED`, shadow-mode: produce winner but
   do not publish. Compare winner against current single-pass output
   quality.
6. Ship 4.3.6 publisher/renderer adapter behind
   `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED`. Single-job canary, then 5%, then
   25%, then 100% over at least 72h soak.
7. Ship 4.3.7 dossier/Mongo state updates in parallel with step 6 —
   they are additive-only and backward-compatible.
8. Flip `CV_ASSEMBLY_DEFAULT_ON=true` after full-soak gates pass.
9. Deprecate the legacy single-pass path from the active route; keep the
   code under a feature flag for one stable release.

### 12.2 Required flags

| Flag | Default | Post-cutover | Notes |
|------|---------|--------------|-------|
| `MASTER_CV_BLUEPRINT_V2_ENABLED` | false | true | Gates 4.3.1 loader path |
| `CV_ASSEMBLY_HEADER_BLUEPRINT_ENABLED` | false | true | Gates 4.3.2 |
| `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED` | false | true | Gates 4.3.3 |
| `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED` | false | true | Gates 4.3.4 |
| `CV_ASSEMBLY_GRADE_SELECT_ENABLED` | false | true | Gates 4.3.5 |
| `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED` | false | true | Gates 4.3.6 |
| `CV_ASSEMBLY_DOSSIER_V2_ENABLED` | false | true | Gates 4.3.7 dossier extension |
| `CV_ASSEMBLY_DEFAULT_ON` | false | true | Master switch |
| `CV_ASSEMBLY_CANARY_ALLOWLIST` | "" | "" | CSV of level-2 ids |
| `CV_ASSEMBLY_CANARY_PCT` | 0 | 100 | |
| `CV_ASSEMBLY_SHADOW_MODE` | true | false | Assembles but does not publish |
| `CV_ASSEMBLY_GRADER_MODEL` | `gpt-5.4-mini` | `gpt-5.4-mini` | Overrideable |
| `CV_ASSEMBLY_SYNTHESIS_MODEL` | `gpt-5.4` | `gpt-5.4` | |
| `PUBLISH_PLAYWRIGHT_TIMEOUT_SECONDS` | 90 | 90 | Per render |
| `PUBLISH_N8N_UPLOAD_MAX_ATTEMPTS` | 5 | 5 | |
| `LANGFUSE_CV_ASSEMBLY_TRACING_ENABLED` | false | true | |

Mutual-exclusion invariant:

- `CV_ASSEMBLY_DEFAULT_ON=true` requires every sub-flag to be true.
- `CV_ASSEMBLY_SHADOW_MODE=true` prevents `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED`
  from having any effect on real publishing.

### 12.3 Backfill

- 4.3.1 master-CV backfill: a dry-run-first script that derives the new
  metadata fields from existing markdown content where unambiguous,
  flags ambiguous fields for manual review, and emits a report.
  **Never** fabricates missing scope, metrics, or seniority markers.
- No backfill for historical jobs. 4.3 applies to `cv_ready` jobs going
  forward. Historical jobs keep their single-pass CV and dossier.

### 12.4 Rollback

- Flag-flip disables the 4.3 lane; the legacy single-pass path re-engages
  under `CV_ASSEMBLY_DEFAULT_ON=false`.
- `scripts/rollback-cv-assembly.py` cancels in-flight 4.3 work items,
  leaves `cv_assembly.*` fields intact for audit, and restores
  `output_publisher.publish()` to single-pass input on affected jobs.
- No data deletion.

## 13. Edge Cases And Failure Modes

| Case | Owning mechanism | Plan |
|------|------------------|------|
| All three drafts fail evidence validator | deterministic rejection → `cv_assembly.status=failed` | 4.3.4, 4.3.5 |
| One draft fails, other two pass | winner chosen from remaining; audit entry logged | 4.3.5 |
| Draft contains title outside `acceptable_titles` | rejected at validator; repair retry once; else fail | 4.3.2, 4.3.4 |
| Pattern selection returns <3 patterns | fail-open to top-1 or top-2; mark `status=partial`; eval flag | 4.3.3 |
| Master-CV edited mid-flight | snapshot invalidation cancels in-flight work; re-enqueue root | 4.3.1 |
| pdf-service down, transient | retry with backoff; stays `publishing`; fail after budget | 4.3.6 |
| pdf-service down, persistent | `failed` terminal; operator alert; no local fallback for publish path | 4.3.6 |
| n8n webhook 500s | retry with idempotency key; deadletter after budget | 4.3.6 |
| n8n ACK missing (no `gdrive_uploaded_at`) | `published` set; `delivered` unset; operator visible | 4.3.6 |
| Dossier body fails evidence validator | dossier → `degraded`; CV still publishes | 4.3.7 |
| Grading model unavailable | fall back to rubric-only deterministic scoring; mark winner `degraded_grade` | 4.3.5 |
| Synthesis violates evidence | reject synthesis; winner draft persists as final | 4.3.5 |
| Two `cv.grade_select_synthesize` workers race | CAS on `cv_assembled_at` (not exists) | 4.3.5, 8.4 |
| Partial publish (CV on Drive, Sheets failed) | publish state records per-surface status; operator retries sheets lane | 4.3.6 |

## 14. Open Questions

- Should `cv_assembly.*` be a separate Mongo collection instead of an
  embedded subtree? Current recommendation: keep on `level-2` for
  operator ergonomics; revisit if document size crosses 1MB.
- Should grading be pairwise, rubric-only, or hybrid? 4.3.5 recommends
  hybrid (rubric-first deterministic + LLM tie-breaker), to be
  benchmarked.
- Should synthesis be a separate LLM call or a constrained merge of
  winner + accepted fragments? 4.3.5 recommends constrained merge in v1;
  separate call only if the merge loses too much.
- Should `delivered` be a hard lifecycle terminal or stay optional?
  Recommendation: optional in v1; revisit once n8n ACK reliability is
  measured.
- Should the 4.3 lane run on the same `systemd` units as preenrich
  (shared allowlists) or on separate units? Recommendation: separate
  units per task type, matching iteration-4 pattern.
- Should the CV Editor UI surface the three drafts for human selection?
  Deferred to 4.4.
- Should `n8n` move from webhook-push to Drive push-via-service-account?
  Out of scope for 4.3 (explicit non-goal).

## 15. File Plan Index

Umbrella implemented by:

- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`
- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
- `plans/iteration-4.3.3-cv-pattern-selection-and-evidence-mapping.md`
- `plans/iteration-4.3.4-multi-draft-cv-assembly.md`
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.3.6-publisher-renderer-and-remote-delivery-integration.md`
- `plans/iteration-4.3.7-dossier-and-mongodb-state-contract.md`
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md`

## 16. Implementation Targets (expected files)

### 16.1 Preenrich-stage work (none — 4.3 runs after preenrich)

No files in `src/preenrich/stages/` are modified by 4.3. The DAG edge
from `cv_ready` to `cv.header_blueprint` is attached in a new stage
registry module (see 16.2).

### 16.2 New shared seam

- `src/cv_assembly/` (new package)
  - `stage_registry.py` — registers the `cv_assembly.*` and `publish.*`
    task types; mirrors `src/preenrich/stage_registry.py` shape.
  - `stage_worker.py` — stage worker entrypoint with task-type allowlist.
  - `dag.py` — DAG edges from `cv_ready` to `published`.
  - `sweepers.py` — `cv_assembled` finalizer, `published` finalizer,
    stage-outbox sweeper (mirrors preenrich sweepers).
  - `models.py` — `HeaderBlueprintDoc`, `PatternSelectionDoc`,
    `DraftDoc`, `GradeDoc`, `SynthesisDoc`, `PublishStateDoc`,
    `DossierStateDoc`.
  - `prompts/` — pattern_selection, header_blueprint, synthesis prompts.
  - `validators/` — deterministic evidence validator, title validator,
    claim validator.
  - `tracing.py` — `CvAssemblyTracingSession`, `PublishTracingSession`
    wrappers around `PreenrichTracingSession`.

### 16.3 Layer 6 V2 adapter work

- `src/layer6_v2/pattern_context.py` (new) — `PatternContext` dataclass.
- `src/layer6_v2/orchestrator.py` — accepts `PatternContext`; exposes a
  `generate_for_pattern(pattern_context)` wrapper that threads the
  pattern into role/header/grader/improver.
- `src/layer6_v2/header_generator.py` — accepts a `HeaderBlueprint`;
  becomes blueprint-driven when one is supplied.
- `src/layer6_v2/variant_selector.py` — accepts a `pattern_bias`
  argument.
- `src/layer6_v2/cv_loader.py` and `src/common/master_cv_store.py` —
  read the new metadata fields and project them into `RoleData` /
  `CandidateData`.

### 16.4 Layer 7 adapter work

- `src/layer7/output_publisher.py` — accepts `cv_assembly.winner` +
  `cv_assembly.synthesis`; emits to `cv_assembly.publish_state`;
  preserves compatibility projection to legacy `level-2` fields.
- `src/layer7/dossier_generator.py` — gains candidate-evidence mode.
- `src/services/gdrive_upload_service.py` — emits per-surface publish
  state and trace refs.
- `pdf_service/app.py` — no protocol changes; adds observability
  headers (`X-Job-Id`, `X-Trace-Id`) and stricter timeouts.
- `src/services/batch_pipeline_service.py` — routes through the 4.3
  lane when `CV_ASSEMBLY_DEFAULT_ON=true`.

### 16.5 Data / config

- `data/master-cv/role_metadata.json` — extended (4.3.1).
- `data/master-cv/role_skills_taxonomy.json` — extended (4.3.1).
- New taxonomies under `data/master-cv/taxonomies/`:
  `identity_taxonomy.json`, `leadership_taxonomy.json`,
  `industry_taxonomy.json`, `domain_taxonomy.json`,
  `operating_model_taxonomy.json`, `credibility_marker_taxonomy.json`.
- Per-role metadata sidecars: `data/master-cv/roles/<id>.meta.json`.
- Per-project metadata sidecars: `data/master-cv/projects/<id>.meta.json`.

### 16.6 Infra

- `infra/systemd/scout-cv-assembly-worker@.service` (new template).
- `infra/systemd/scout-publish-worker@.service` (new template).
- `infra/scripts/verify-cv-assembly-cutover.sh` (new).
- `infra/scripts/backfill-master-cv-blueprint.py` (new, dry-run first).
- `infra/scripts/rollback-cv-assembly.py` (new).

### 16.7 Evals

- `data/eval/validation/cv_assembly_4_3_1_master_cv/`
- `data/eval/validation/cv_assembly_4_3_2_header_blueprint/`
- `data/eval/validation/cv_assembly_4_3_3_pattern_selection/`
- `data/eval/validation/cv_assembly_4_3_4_multi_draft/`
- `data/eval/validation/cv_assembly_4_3_5_grade_synth/`
- `data/eval/validation/cv_assembly_4_3_6_publish/`

## 17. Definition Of Done

Iteration 4.3 is done when:

- every `cv_ready` job produces three candidate-aware drafts grounded in
  master-CV evidence, is graded, synthesized into a best-version, and
  reliably reaches `published` or a well-defined terminal failure state;
- the master-CV blueprint is explicit and rich enough to drive
  evaluator-aware generation without hallucination;
- every 4.3 stage and every render/upload boundary is observable in
  Langfuse via the canonical `scout.cv.*` / `scout.publish.*` namespaces;
- compatibility projections keep all existing readers of `level-2`
  publisher fields working;
- the dossier reflects the same evidence map that drove the winning CV;
- the eval corpora regress cleanly between runs and gate rollout;
- and the architecture is ready for the CV Editor surface and for further
  candidate-aware stages (interview prep, outreach tuning) to be added
  later without another orchestration redesign.

That is the correct production-ready boundary for iteration 4.3.
