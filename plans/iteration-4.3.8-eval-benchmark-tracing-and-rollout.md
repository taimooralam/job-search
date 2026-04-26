# Iteration 4.3.8 Plan: Eval Corpora, Benchmark Harnesses, Langfuse Tracing, And Cross-Family Rollout

## 1. Executive Summary

4.3 ships six candidate-aware and publish stages plus an upgraded master-CV
blueprint. Each stage owns its own schema, validators, and benchmark
corpus inside its plan. What no stage owns, and what 4.3.8 owns, is the
**family-level contract** that makes those stages safely composable in
production:

- one canonical Langfuse trace taxonomy (`scout.cv.*`, `scout.publish.*`)
  with explicit metadata, payload, and session-lifetime rules;
- one canonical eval corpus layout under
  `data/eval/validation/cv_assembly_4_3_*/` and one frozen end-to-end
  corpus owned by this plan;
- one end-to-end harness with a typed input/output contract and
  bounded tolerance bands;
- one cross-stage cost aggregation rule that produces
  `cv_assembly.total_cost_usd` and feeds the per-job and per-hour
  cost breakers;
- one rollout state machine with explicit states, transitions, an
  on-disk artifact, and a single rollout-gate script with a typed
  exit-code and JSON output contract;
- one operator runbook with named owners, escalation paths, and
  recovery-time targets for every 4.3 failure mode.

4.3.8 does **not** produce candidate content. It does not own per-stage
schemas, prompts, or stage-local validators. Each 4.3 stage retains its
schema and test ownership; 4.3.8 owns the cross-cutting gates, harnesses,
tracing conventions, cost aggregation, and rollout machinery that bind
those stages into a shippable family.

Without this plan, the family ships one stage at a time with ad-hoc trace
names, ad-hoc gate semantics, ad-hoc rollout flips, and an operator
runbook that is troubleshooting prose rather than a contract — exactly
the failure mode that motivates per-stage queues and coherent
observability in the first place.

## 2. Mission

Make Langfuse tracing, eval corpora, cross-stage cost aggregation, and
rollout gating **first-class family-level contracts** for iteration 4.3:
one canonical trace namespace; one eval directory layout; one regression
gate script; one rollout state machine; one cost rollup rule; one
runbook with owners — all enforced by code, not by convention.

## 3. Objectives

1. Own the canonical Langfuse trace taxonomy and session-lifetime rule
   for `scout.cv.*` and `scout.publish.*`, extending iteration-4 §9.
2. Own the canonical eval corpus directory layout and the cross-family
   regression-gate semantics.
3. Own the end-to-end harness input/output contract (`cv_ready` slice →
   `published` slice) with explicit tolerance bands and frozen fixture
   layout.
4. Own the cross-stage cost aggregation rule, including the formula for
   `cv_assembly.total_cost_usd`, its write site, and its interaction
   with per-job and per-hour breakers.
5. Own the rollout state machine, including canonical states,
   transition triggers, rollback semantics, and the on-disk
   `current_rollout_state.json` artifact.
6. Own `scripts/gate_cv_assembly_rollout.py` — its CLI, exit codes,
   JSON output schema, and mutation policy (report-only).
7. Own the production-readiness gates for the 4.3 family as a whole.
8. Own the operator runbook additions for 4.3 failure scenarios, with
   per-scenario `owner_role`, `escalation_path`, and
   `acceptable_recovery_time`.

## 4. Success Criteria

4.3.8 is done when:

- every 4.3 stage writes `trace_ref` into its Mongo state and uses the
  canonical taxonomy, validated by a startup health probe;
- every per-stage eval corpus is frozen with a known baseline; the
  end-to-end corpus is frozen and committed; both are exercised by
  `scripts/gate_cv_assembly_rollout.py`;
- the rollout state machine is the single source of truth for
  `current_rollout_state`, and rollout cannot advance unless the gate
  script returns `overall=pass`;
- `cv_assembly.total_cost_usd` is written deterministically per the
  formula in §13 and is the input to the per-job and per-hour cost
  breakers;
- operators can debug a single job from `cv_ready` through `delivered`
  in Langfuse using one stable session id and reach the correct
  runbook entry for any failure mode in under two minutes;
- every runbook scenario in §17 has `owner_role`, `escalation_path`,
  `acceptable_recovery_time` populated.

## 5. Non-Goals

- Designing or replacing Langfuse, `PreenrichTracingSession`, or the
  scout project Langfuse layout.
- Owning per-stage schemas, prompts, or stage-local validators (each
  stage's plan owns those).
- Generating eval cases (each subplan owns its own cases; 4.3.8 owns
  the layout, the gates, and the end-to-end cases only).
- Building a benchmark comparison dashboard beyond what
  `scripts/gate_cv_assembly_rollout.py` produces as JSON output and
  what Langfuse already exposes.
- Automating canary expansion (manual flips remain the default, with
  optional report-only gate-checks).
- Inventing a new control plane: Mongo work_items / stage_states /
  lifecycle remain the orchestration plane. Langfuse remains the
  observability sink. The rollout-state artifact is configuration,
  not orchestration.

## 6. Why This Artifact Exists

Iteration 4 already established a strong tracing taxonomy and rollout
discipline for the preenrich lane. The 4.3 candidate-aware lane spans
three concerns — assembly, grading, publishing — and three Mongo
subtrees (`cv_assembly.*`, `level-2` legacy projections, `dossier_state`)
each with its own failure surface and per-stage queue. Without a
family-level plan, three structural problems recur:

1. **Trace-name drift.** Every per-stage subplan correctly defines
   local span names; only a shared plan can enforce that the names
   stay disjoint, that metadata fields stay consistent, and that
   trace_ref propagation works end-to-end across `scout.cv.*` → 
   `scout.publish.*`.
2. **Gate-shape drift.** Every per-stage subplan defines its own
   benchmark gate; only a shared plan can enforce that gates compose
   into a single `pass`/`fail` with a typed JSON output, and that
   rollout cannot advance unless every gate is green.
3. **Rollout-flag drift.** The umbrella defines flags; per-stage plans
   define their behavior; only a shared plan can enforce flag mutual-
   exclusion (e.g., `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED` cannot be
   true unless `CV_ASSEMBLY_GRADE_SELECT_ENABLED` is true) and define
   the rollback semantics.
4. **Cost-aggregation drift.** Per-stage plans capture per-stage cost;
   only a shared plan can define the rollup formula, where it lands
   in Mongo, and how it interacts with breakers.
5. **Runbook-ownership drift.** Per-stage plans describe per-stage
   failure modes; only a shared plan can name the on-call owner,
   escalation path, and acceptable recovery time consistently.

4.3.8 closes those gaps without redefining anything a stage owns. It
is the umbrella's compliance layer.

## 7. Hard Prerequisites

The following must be true in production before 4.3.8 rollout-gating is
active and the gate script is treated as load-bearing for flag flips.
Any unmet prerequisite means rollout-gating runs in **observe-only
mode** (gate script may execute and report, but its `overall` value is
advisory, not blocking).

### 7.1 Stage prerequisites

- **MASTER_CV_BLUEPRINT_V2_ENABLED=true** (4.3.1) — `role_metadata`,
  `acceptable_titles`, `identity_taxonomy`, and
  `credibility_marker_taxonomy` are loadable in production.
- **Per-stage benchmark suites green for 4.3.2–4.3.7** — every stage's
  benchmark harness exits 0 against its frozen corpus *under the same
  model versions and prompt versions that production uses*. "Green"
  means: invariants pass, regression metrics within tolerance, and
  the harness writes a `baseline_report.json` accepted by the stage
  owner (commit reference recorded).
- **Each 4.3 stage has a registered health probe** — declared in
  `src/cv_assembly/health_probe.py` (this plan owns the registry).
  The probe runs at worker startup; if a registered stage's probe
  fails, the worker template refuses to start. 4.3.8's own probe
  asserts the rollout-state artifact is parseable, the gate script
  is importable, and the cost aggregation function resolves.

### 7.2 Tracing prerequisites

- **`PreenrichTracingSession` available and configured** (`src/pipeline/
  tracing.py`).
- **Langfuse retention policy is verified** per iteration-4 §10:
  scout-project retention is at least 30 days for traces; 7 days for
  raw events. This is a manual confirmation step recorded in the
  runbook (§17.1) before any rollout state advances past `shadow`.
- **`LANGFUSE_CV_ASSEMBLY_TRACING_ENABLED=true`** in the worker
  environment, with credentials resolvable.

### 7.3 Cost-tracking prerequisites

- **Per-stage cost is being persisted** by every 4.3 stage. The
  `cv_assembly.<stage>.cost_usd` (or equivalent — see the per-stage
  plan) field must be populated with a non-null float for every
  successful stage run before the breakers in §13 are wired in.
- **`cv_assembly_stage_runs` collection exists** with a `cost_usd`
  field per run, used by the per-hour breaker (§13.4).

### 7.4 Rollout prerequisites

- **All 4.3 feature flags exist in `src/cv_assembly/config_flags.py`**
  with the defaults specified in the umbrella's flag table; missing
  flags fail closed (treated as `false`).
- **`current_rollout_state.json` artifact exists** under
  `infra/rollout/cv_assembly/current_rollout_state.json` (see §14)
  with at least `state="shadow"` and `started_at`.

### 7.5 Hard-blocking vs observe-only

| Prerequisite class | Unmet → rollout state | Unmet → gate script |
|--------------------|-----------------------|---------------------|
| MASTER_CV_BLUEPRINT_V2_ENABLED | rollout cannot leave `shadow` | exits 1 (gate fail) |
| Per-stage benchmark suite green | cannot advance past current state | exits 1 |
| Health probe registration | worker refuses to start | n/a (worker not running) |
| Langfuse retention verified | cannot advance past `canary_5` | exits 1 (gate fail) |
| Cost field population | cannot advance past `canary_25` | exits 1 (cost gate) |
| `current_rollout_state.json` parseable | rollout treated as `shadow` | exits 2 (infra) |

There is **no observe-only path** for missing flags or a missing
state artifact: those fail closed, since they are config errors, not
rollout questions.

## 8. Langfuse Tracing Foundation

### 8.1 Sink vs orchestration

Inherited verbatim from iteration-4 §9: Langfuse is the observability
sink. Mongo `work_items`, `cv_assembly_stage_runs`, `level-2.cv_assembly.
stage_states` and `level-2.lifecycle` are the orchestration plane. 4.3.8
adds **no** orchestration to Langfuse. No stage transition is decided
from Langfuse data.

### 8.2 Canonical namespaces

Reserves and freezes the following 4.3 namespaces (extends iteration-4
§9.4 placeholders):

```
scout.cv.master_cv_load
scout.cv.master_cv_backfill
scout.cv.header_blueprint
scout.cv.header_blueprint.preflight
scout.cv.header_blueprint.compose
scout.cv.header_blueprint.validate
scout.cv.pattern_selection
scout.cv.pattern_selection.preflight
scout.cv.pattern_selection.compose
scout.cv.pattern_selection.diversity_check
scout.cv.pattern_selection.validate
scout.cv.draft_assembly
scout.cv.draft_assembly.pattern_projection
scout.cv.draft_assembly.variant_selection
scout.cv.draft_assembly.role_generation
scout.cv.draft_assembly.stitching
scout.cv.draft_assembly.header_prose
scout.cv.draft_assembly.ats_validation
scout.cv.draft_assembly.evidence_lineage
scout.cv.grade_select_synthesize
scout.cv.grade_select_synthesize.rubric_deterministic
scout.cv.grade_select_synthesize.llm_tiebreaker
scout.cv.grade_select_synthesize.selection
scout.cv.grade_select_synthesize.synthesis
scout.cv.grade_select_synthesize.validate
scout.cv.finalize_cv_assembled
scout.publish.render.cv
scout.publish.render.dossier
scout.publish.render.dossier.generate
scout.publish.upload.drive.cv
scout.publish.upload.drive.dossier
scout.publish.upload.sheets
scout.publish.finalize_published
scout.publish.finalize_delivered
scout.publish.projection_written
scout.publish.partial
scout.publish.retry
scout.publish.deadletter
```

A startup contract test asserts the registry of canonical names equals
this list. Adding a name requires a plan amendment; renaming requires a
plan amendment plus a migration entry.

### 8.3 Required correlation metadata

Every span and event must carry these fields (extends iteration-4 §9.3):

- **Universal:** `job_id`, `level2_job_id`, `correlation_id`,
  `langfuse_session_id` (see §9), `run_id`, `worker_id`,
  `task_type`, `stage_name`, `attempt_count`, `attempt_token`,
  `input_snapshot_id`, `work_item_id`, `lifecycle_before`,
  `lifecycle_after`.
- **4.3-family-specific:** `master_cv_checksum`,
  `presentation_contract_checksum`, `header_blueprint_checksum?`,
  `pattern_selection_checksum?`, `pattern_id?`, `pattern_signature?`,
  `winner_draft_id?`, `synthesis_hash?`, `artifact_sha256?`,
  `cv_assembly_total_cost_usd_running?`.
- **Transport spans (pdf-service, n8n, sheets):** `provider`,
  `transport`, `endpoint`, `duration_ms`, `http_status?`, `success`,
  `outcome`.

A unit test under `tests/unit/cv_assembly/test_tracing_metadata_
completeness.py` (4.3.8 owns it) iterates the canonical-name list and
asserts that the corresponding helper produces every required field.

### 8.4 Span vs event discipline

**Spans** are reserved for timed work:

- stage body;
- LLM calls inside stages;
- pdf-service HTTP calls;
- n8n webhook calls;
- Sheets logging calls;
- deterministic validators of non-trivial cost (header validator,
  evidence-lineage validator, dossier validator).

**Events** are point-in-time transitions:

- `claim`, `enqueue_next`, `finalize_cv_assembled`,
  `finalize_published`, `finalize_delivered`, `retry`, `deadletter`,
  `release_lease`, `snapshot_invalidation`, `cost_breaker_tripped`,
  `rollout_state_observed` (see §14).

**Forbidden span names:** any name with unbounded cardinality —
per-bullet, per-role-id, per-achievement-id, per-pattern-bullet,
per-section. Cardinality is metadata, never structure.

### 8.5 Payload discipline (numeric)

Inherited from 4.2 §8.8 with explicit numeric caps:

- string previews: ≤ **160** characters; longer strings are truncated
  with `…` suffix;
- list previews: ≤ **8** entries; longer lists are summarized as
  `{count, first_id, last_id}`;
- counts and band enums are always allowed at full fidelity;
- checksums and refs are always allowed at full fidelity;
- prompts are captured only via `_sanitize_langfuse_payload` and only
  when `LANGFUSE_CV_ASSEMBLY_CAPTURE_FULL_PROMPTS=true` (default
  `false`).

**Forbidden payload content:** full CV prose, full draft bodies, full
synthesis bodies, full debug JSON, full evidence_maps, full master-CV
markdown, full JD bodies, full role markdown, raw LLM request bodies
absent the sanitizer.

### 8.6 Shared seam

- `src/cv_assembly/tracing.py` (new) — `CvAssemblyTracingSession` and
  `PublishTracingSession`, both wrapping `PreenrichTracingSession`
  with 4.3-namespace defaults and the §9 session pinning.
- Sweeper-side emissions: `emit_cv_assembly_sweeper_event()` and
  `emit_publish_sweeper_event()` with canonical session pinning.
- A linter test (`tests/unit/cv_assembly/test_no_raw_langfuse_client.
  py`) asserts no module under `src/cv_assembly/` constructs a raw
  `langfuse.Langfuse(...)` client. Tracing only flows through the
  shared seam.

### 8.7 Trace-ref propagation

Every stage persists `trace_id` and `trace_url` to:

- `level-2.cv_assembly.stage_states.<task>.trace_ref`;
- `cv_assembly_stage_runs.<row>.trace_ref`;
- (publisher only) `level-2.cv_assembly.publish_state.<surface>.
  trace_ref`.

The frontend per-job detail view links directly to the Langfuse trace
URL. The trace-ref shape is `{trace_id: str, trace_url: str}`. Stages
that emit no trace (because tracing was disabled at runtime) still
write `{trace_id: null, trace_url: null}` to keep the field present
and queryable.

### 8.8 Retention and lookup assumptions

Operators may rely on:

- Langfuse retains traces for **at least 30 days**;
- Langfuse retains events for **at least 7 days**;
- a session id (§9) is queryable as a single timeline that joins
  every `scout.cv.*` and `scout.publish.*` span for the same job
  across retries and re-runs;
- Mongo `cv_assembly_stage_runs` is the canonical source for
  cost/duration/outcome aggregation **older than the Langfuse
  retention window**.

Operators may not rely on Langfuse for any decision affecting stage
progression or for any data older than 30 days.

### 8.9 What may live only in Mongo

- raw evidence-bag contents and per-pattern projections;
- full LLM request / response bodies (in `<stage>_runs.debug` only,
  bounded by §8.5 caps for any field that mirrors to Langfuse);
- per-bullet draft outputs;
- full validator violation details beyond rule_id / severity / detail
  preview;
- cost ledger rows.

## 9. Langfuse Session Lifetime Rule

A single, stable Langfuse session id binds every 4.3 span and event
for the same job into one operator-readable timeline.

### 9.1 Canonical format

```
session_id = f"job:{level2_job_id}"
```

`level2_job_id` is the canonical level-2 ObjectId hex string. There is
exactly one session per `level2_job_id`. There is no per-attempt or
per-run session.

### 9.2 Stability across retries

Within a single `cv_ready` cycle, every retry of every 4.3 stage
**reuses** `session_id`. Retries append spans to the same session;
they do not start a new session. The `attempt_count` and
`attempt_token` metadata fields disambiguate within the session.

### 9.3 Stability across re-runs

The same session id is reused when the same `level2_job_id` re-enters
`cv_ready` after:

- snapshot invalidation (`input_snapshot_id` changes);
- a manual re-enqueue (`scripts/enqueue_stage.py`);
- a lifecycle revert (`cv_assembled` → `cv_ready`, e.g., for a forced
  re-grade).

Re-runs are disambiguated by:

- the canonical lifecycle event `snapshot_invalidation` emitted at
  the boundary;
- the per-span `input_snapshot_id` metadata field;
- the per-span `cv_assembly_run_seq` metadata field (1-indexed,
  monotonic per `level2_job_id`, written from
  `cv_assembly.run_seq` in Mongo — see §13.6).

Operators reading a session in Langfuse see one continuous timeline
with explicit re-run boundaries marked by `snapshot_invalidation`
events and a step in `cv_assembly_run_seq`.

### 9.4 Forbidden session strategies

- session id must not include `input_snapshot_id` — that breaks the
  cross-run timeline guarantee;
- session id must not include `attempt_token` — that breaks the
  cross-retry timeline guarantee;
- session id must not include `correlation_id` — multiple correlated
  jobs may share a correlation id by design;
- session id must not be dropped or rotated when retention pressure
  is suspected.

### 9.5 Tests

`tests/unit/cv_assembly/test_session_lifetime.py` (4.3.8 owns it)
asserts:

- `build_cv_assembly_session_id(level2_id)` returns
  `f"job:{level2_id}"`;
- two distinct retries of the same stage emit the same session id;
- a re-run after `snapshot_invalidation` emits the same session id
  with `cv_assembly_run_seq` incremented by 1.

## 10. Eval Corpus Foundation

### 10.1 Directory layout

```
data/eval/validation/
  cv_assembly_4_3_1_master_cv/
  cv_assembly_4_3_2_header_blueprint/
  cv_assembly_4_3_3_pattern_selection/
  cv_assembly_4_3_4_multi_draft/
  cv_assembly_4_3_5_grade_synth/
  cv_assembly_4_3_6_publish/
  cv_assembly_4_3_7_state/
  cv_assembly_4_3_8_end_to_end/        ← NEW (4.3.8-owned)
```

Per-stage corpus shape (every stage adopts the same skeleton; details
are the stage's plan):

```
<stage_corpus>/
  cases/
    <case_id>/
      input/                  # frozen inputs (level-2 slice + master-CV snapshot)
      expected/               # frozen expected outputs
      reviewer_sheet.md       # reviewer rubric
      notes.md
  fixtures/                   # stub transport responses
  fault_cases/                # failure injections
  baseline_report.json        # last accepted run report
  README.md
```

### 10.2 End-to-end corpus (4.3.8-owned)

`cv_assembly_4_3_8_end_to_end/` holds full-pipeline cases — frozen
`cv_ready` `level-2` slice in, expected `published` `level-2` slice
plus `cv_assembly.*` populated plus compatibility projection applied
out. The corpus minimum is **8 cases**:

- architecture-first AI (Principal/Staff seniority);
- engineering leadership (EM → Senior EM);
- platform/infra (Staff/Principal);
- head-of-engineering (Director / Head);
- AI product + platform hybrid;
- two adversarial cases (JD with AI hype + candidate with low AI
  intensity; JD with extreme leadership scope + candidate with modest
  scope);
- two fault cases (pdf-service flaky; n8n webhook timeout).

The end-to-end harness contract for these cases is in §11.

### 10.3 Eval dimensions per stage (summary)

| Stage | Key metrics (owned by stage plan; 4.3.8 references) |
|-------|------------------------------------------------------|
| 4.3.1 | Schema validity, invariant pass rate, backfill idempotence |
| 4.3.2 | Header invariants, title allowlist, viability bands, metadata-policy compliance, reviewer usefulness, AI-claim drift |
| 4.3.3 | Diversity thresholds, evidence resolution, pattern labels, persona-lane compliance, reviewer usefulness |
| 4.3.4 | Lineage validator pass rate, structural invariants, title/AI compliance, ATS-surface compliance, reviewer usefulness |
| 4.3.5 | Rubric reproducibility, winner agreement, truth dominance, unsupported-competency rate, synthesis improvement |
| 4.3.6 | Publish-state shape, projection correctness, render-variant compliance, retry/deadletter behavior |
| 4.3.7 | Projection byte equality, dossier_state shape, dashboard rollups, disclosure-preservation correctness |
| 4.3.8 | End-to-end lifecycle correctness, Langfuse trace integrity, cost per job, rollout-state machine correctness |

### 10.4 Cross-family regression gates

Rollout is blocked if **any** of the following regress against the
frozen corpora:

- evidence-lineage validator pass rate (4.3.4 + 4.3.5) drops below
  the previous accepted baseline (recorded in the corresponding
  `baseline_report.json`);
- title-allowlist compliance falls below 1.00 in any case;
- metadata/disclosure policy compliance falls below 1.00 in any case;
- AI-claim drift appears in any case;
- unsupported competency inflation appears in any case's final
  `core_competencies` or header proof surfaces;
- deterministic rubric reproducibility (4.3.5) drops below 1.00;
- compatibility projection (4.3.7) loses any legacy field on any
  case;
- Langfuse trace integrity: any stage fails to emit a `trace_ref`
  on completion (`trace_ref={null,null}` is acceptable when tracing
  is disabled, but the field must be present);
- per-job cost exceeds `CV_ASSEMBLY_MAX_COST_USD` on any non-fault
  case.

These gates are enforced by `scripts/gate_cv_assembly_rollout.py`
(§15). Per-stage gate semantics remain owned by per-stage plans;
4.3.8 owns the composition rule and the umbrella gate.

## 11. End-to-End Harness Contract

`scripts/benchmark_cv_assembly_end_to_end.py` (new, 4.3.8-owned) runs
the end-to-end corpus and emits a comparison report. The harness is
deterministic across runs *modulo the explicit tolerance bands below*.

### 11.1 Frozen input fields

Each case under `cv_assembly_4_3_8_end_to_end/cases/<case_id>/input/`
contains:

- `level2_slice.json` — a frozen `level-2` document at lifecycle
  `cv_ready` with these fields snapshot-frozen and asserted byte-equal
  on load:
  - `_id`, `slug`, `lifecycle="cv_ready"`,
    `pre_enrichment.outputs.jd_facts`,
    `pre_enrichment.outputs.classification`,
    `pre_enrichment.outputs.research_enrichment`,
    `pre_enrichment.outputs.stakeholder_surface`,
    `pre_enrichment.outputs.pain_point_intelligence`,
    `pre_enrichment.outputs.presentation_contract`,
    `pre_enrichment.job_blueprint_snapshot` (the compact
    projection; for completeness),
    all four `presentation_contract` subdocuments,
    `master_cv_checksum`, `presentation_contract_checksum`,
    `jd_checksum`;
- `master_cv_snapshot/` — a directory of frozen master-CV markdown +
  `role_metadata.json` exactly as 4.3.1 loader would resolve them,
  pinned by `master_cv_checksum`;
- `transport_fixtures.json` — recorded responses for any
  pdf-service / n8n / Sheets / Drive call the case will make;
  fault cases use this to inject flakes;
- `case_meta.json` — `{case_id, role_family, seniority, intent,
  expected_status, expected_lifecycle}`.

The harness fails closed if any frozen-input checksum drifts. No live
fetches.

### 11.2 Asserted output fields

For each case, the harness produces an `actual/` directory and
compares to `expected/`:

- `level2_after.json` — the `level-2` document at the case's
  expected terminal lifecycle (`published` or `delivered` or
  `cv_ready` with `cv_assembly.status="failed"` for fault cases);
- `cv_assembly_subtree.json` — the `level-2.cv_assembly` subtree;
- `cv_assembly_stage_runs.json` — list of stage-run rows produced;
- `langfuse_trace_summary.json` — list of `(span_name,
  required_metadata_fields_present, trace_ref_emitted)` with no
  payload bodies;
- `cost_summary.json` — `{total_cost_usd, per_stage_cost_usd[],
  breaker_status}`;
- `rollout_observations.json` — `{state_observed, transitions_seen}`
  (always `{shadow, []}` in harness mode; see §14.7).

### 11.3 Tolerance bands per field type

| Field class | Tolerance | Examples |
|-------------|-----------|----------|
| Identifiers | byte-exact | `_id`, `master_cv_checksum`, `jd_checksum`, `pattern_id`, `winner_draft_id`, `synthesis_hash`, `artifact_sha256` |
| Enums | byte-exact | `lifecycle`, `cv_assembly.status`, `chosen_title_strategy`, `pattern_label`, `confidence.band` |
| Counts and ordinals | byte-exact | `drafts.length == 3`, `patterns.length`, `metric_band` ordinal |
| Cost (per stage) | ±5% of expected (LLM provider variance) | `cv_assembly.drafts[*].cost_usd` |
| Cost (per job total) | ±5% of expected, AND ≤ `CV_ASSEMBLY_MAX_COST_USD` | `cv_assembly.total_cost_usd` |
| Duration | log-only (not asserted) | `duration_ms` |
| Score (LLM-judged) | ±0.05 of expected | `grades[*].composite`, reviewer-rated synthesis improvement |
| Score (deterministic rubric) | byte-exact | `grades[*].deterministic_subscore` |
| Prose strings (titles, taglines) | structural (length within ±10%, allowlist compliance, no forbidden phrases) | `header.tagline`, `header.profile` |
| Prose strings (bullets, summary) | structural + lineage (every claim resolves to a master-CV ref) | `experience[*].bullets[*]`, `summary` |
| Prose strings (chosen_title) | byte-exact (4.3.2 §11.1.1 is byte-deterministic) | `header.chosen_title` |
| Compatibility projection fields | byte-exact (4.3.7 §6 declares projection identity) | legacy `summary`, `key_achievements[*].text`, etc. |

### 11.4 Degraded-but-acceptable outcomes

A case may be tagged `expected_status="degraded"` in
`case_meta.json`. The harness then asserts:

- `cv_assembly.status="degraded"` AND
- `cv_assembly.synthesis.degraded=true` (or analogous per-stage
  marker) AND
- the per-stage validator report status ∈ `{pass, repair_attempted}`,
  not `failed` AND
- the case's terminal lifecycle matches its expected value AND
- compatibility projection fields are present, even if their content
  is the safer/conservative alternative.

Fault cases (pdf-service flaky, n8n timeout) are tagged
`expected_status="published_after_retry"` and additionally assert
exactly one retry event in the expected stage's trace summary.

### 11.5 Fixture and artifact storage

- frozen inputs live under git in
  `data/eval/validation/cv_assembly_4_3_8_end_to_end/cases/<case_id>/
  input/`;
- expected outputs live under git under `expected/`;
- the harness writes per-run artifacts under
  `reports/cv-assembly-end-to-end/<run_id>/<case_id>/` (gitignored);
- a comparison report `reports/cv-assembly-end-to-end/<run_id>/
  comparison.json` aggregates all cases.

### 11.6 Comparison report shape

```
{
  "run_id": "<utc_iso8601>-<short_sha>",
  "harness_version": "v1",
  "expected_baseline": "<commit_sha>",
  "cases": [
    {
      "case_id": "...",
      "status": "pass" | "fail" | "degraded_pass" | "skipped",
      "violations": [
        {"field": "...", "kind": "byte_diff" | "score_drift" | "lineage_unresolved" | "structural", "detail": "<= 240 chars"}
      ],
      "cost_usd_actual": 1.23,
      "cost_usd_expected": 1.20,
      "duration_ms_actual": 312000
    }
  ],
  "overall": "pass" | "fail",
  "ts": "<utc_iso8601>"
}
```

`scripts/gate_cv_assembly_rollout.py` (§15) consumes this report.

### 11.7 Cross-version comparability

Frozen inputs are versioned by case directory; the corpus is
versioned by the `case_meta.json` `corpus_version` field. When a plan
amendment changes the corpus shape (e.g., adds a required output
field), the harness records `harness_version` in the report and
emits a `corpus_migration` entry in `data/eval/validation/cv_assembly_
4_3_8_end_to_end/CHANGELOG.md`. Old `baseline_report.json` files
remain comparable for fields that did not change, with the harness
flagging fields that are unavailable in the older baseline as
`"skipped_for_baseline_version"`.

## 12. Cost And Latency Benchmark Contract

### 12.1 Per-stage cost expectation bands

Per-stage cost per job, based on model routing in the umbrella:

| Stage | Primary model | Expected cost/job band | Soft budget USD |
|-------|---------------|------------------------|-----------------|
| 4.3.1 loader | n/a | n/a | 0.00 |
| 4.3.2 header blueprint | gpt-5.4 | low | 0.15 |
| 4.3.3 pattern selection | gpt-5.4 | medium | 0.25 |
| 4.3.4 draft assembly (×3) | tier-based | high (3× Layer 6 V2) | 1.50 |
| 4.3.5 grade + synthesis | gpt-5.4-mini grader + algorithmic synthesis | medium | 0.30 |
| 4.3.6 publish | n/a (LLM-free) | negligible | 0.05 |
| 4.3.7 projection | n/a | negligible | 0.00 |
| 4.3.8 (this plan) | n/a | n/a | 0.00 |

Soft budgets are advisory inputs to per-stage tier-downgrade logic in
`unified_llm.py`; they are not enforced by 4.3.8 directly. The hard
ceiling is `CV_ASSEMBLY_MAX_COST_USD` (default **2.50**) and is
enforced by the cost breaker (§13).

### 12.2 Latency targets (p95)

- 4.3.2: < 20s
- 4.3.3: < 30s
- 4.3.4: < 180s per draft (3 drafts in parallel ⇒ wall ~180s)
- 4.3.5: < 60s
- 4.3.6: < 120s for full publish
- End-to-end `cv_ready → published`: wall p95 < 8 minutes.

Latency is reported by the harness (§11) but is not a hard rollout
gate at v1 (rollout gates on cost, correctness, and observability;
latency is observed and reviewed manually).

## 13. Cross-Stage Cost Aggregation Rule

### 13.1 Formula

`cv_assembly.total_cost_usd` is computed deterministically as:

```
total_cost_usd =
    Σ cv_assembly.drafts[*].cost_usd
  + Σ cv_assembly.grades[*].cost_usd
  + cv_assembly.synthesis.cost_usd
  + cv_assembly.publish_state.summary.total_cost_usd      # 4.3.6 §497 (sum of render+upload)
```

Components that are missing because their stage has not yet run
contribute `0.0`. Components that are missing because their stage
**failed terminally** contribute the partial cost recorded in
`cv_assembly_stage_runs` rather than `0.0`. The aggregator never
fabricates a missing cost.

If a stage completed successfully but `cost_usd` is null (e.g., due to
a transient cost-tracker miss), the aggregator records the partial
total and adds `cost_aggregation_warnings[]` entry
`{stage_name, reason="cost_field_missing"}`. The job is **not**
failed for this; the per-job breaker treats `null` as `0.0`.

### 13.2 Write site

Owned by the publisher's `finalize_published` finalizer (4.3.6) on
the same `findOneAndUpdate` that flips `lifecycle="published"`:

```
{
  "$set": {
    "cv_assembly.total_cost_usd": <float>,
    "cv_assembly.cost_aggregation_warnings": [...],
    "lifecycle": "published",
    ...
  }
}
```

This is atomic with publish: a job in `lifecycle="published"` always
has `cv_assembly.total_cost_usd` set. A job that never reaches
`published` (failed, deadlettered) gets a best-effort
`total_cost_usd` written by the failure-finalizer in 4.3.6.

### 13.3 Write timing (re-runs)

On re-run after `snapshot_invalidation`:

- `cv_assembly.total_cost_usd` is **overwritten** with the latest
  run's aggregate;
- the previous value is preserved in `cv_assembly.cost_history[]`
  with `{run_seq, total_cost_usd, ts}`;
- the per-hour breaker (§13.4) consumes `cv_assembly_stage_runs`
  rows directly, so re-run cost is counted against the per-hour
  ceiling regardless of overwrite.

### 13.4 Interaction with breakers

- **Per-job breaker** (`CV_ASSEMBLY_MAX_COST_USD`, default 2.50):
  enforced at the start of every cost-bearing stage. The stage reads
  the running aggregate from the in-progress `cv_assembly` subtree
  (whatever has been written so far) and refuses to claim its work
  item if the running total + the stage's expected band (§12.1)
  would exceed the ceiling. On overrun mid-stage, the stage emits
  `cost_breaker_tripped` event, fails its own work item, and the
  4.3 lane fails the job (`cv_assembly.status="failed"`,
  `fail_reason="cost_breaker"`).
- **Per-hour breaker** (`CV_ASSEMBLY_MAX_COST_USD_PER_HOUR`,
  default 15.00): enforced by the worker scheduler. The worker
  queries `sum(cv_assembly_stage_runs.cost_usd)` over the last 60
  minutes for `task_type LIKE 'cv.%' OR 'publish.%'`. When the sum
  exceeds the ceiling, the worker pauses new claims, emits
  `cost_breaker_tripped` event, and an operator alert is fired (see
  §17 scenario "Cost breaker triggered"). The pause auto-recovers
  after 15 minutes if the rolling sum drops back below the ceiling.
- **Per-hour deadletter ceiling**
  (`CV_ASSEMBLY_MAX_DEADLETTER_PER_HOUR`, default 5): independent
  of cost; pauses worker claims when exceeded; same auto-recovery.

### 13.5 Missing per-stage cost

If a stage completes successfully but `cost_usd` is null:

- the aggregator records a warning (§13.1);
- the per-job breaker treats it as `0.0`;
- the per-hour breaker excludes the row;
- the harness (§11) flags the case as `degraded_pass` if
  `cost_aggregation_warnings[]` is non-empty;
- the gate script (§15) downgrades `cost` gate to `warn` (not
  `fail`) if a single case has the warning, but escalates to
  `fail` if more than 10% of cases in a run have it.

### 13.6 Run-sequence numbering

`cv_assembly.run_seq` is a monotonic 1-indexed integer per
`level2_id` written by the publisher's finalizer. It is incremented
when a re-run completes (i.e., at the time `cv_assembly.cost_history[]`
gets a new entry). It is the source for the
`cv_assembly_run_seq` metadata field in §9.3.

## 14. Rollout State Machine

### 14.1 Canonical states

| State | Volume | Default flag posture |
|-------|--------|----------------------|
| `shadow` | 0 jobs publish via 4.3 lane; drafts produced and persisted only | `CV_ASSEMBLY_SHADOW_MODE=true`, `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=false` |
| `canary_1` | 1 specific job (manual allowlist) publishes via 4.3 lane | `CV_ASSEMBLY_CANARY_ALLOWLIST="<level2_id>"`, `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=true` for allowlisted only |
| `canary_5` | up to 5 jobs from allowlist | `CV_ASSEMBLY_CANARY_ALLOWLIST` size 5 |
| `canary_25` | up to 25 jobs from allowlist (or 25% if percent-based) | allowlist or `CV_ASSEMBLY_CANARY_PCT=25` |
| `soak` | 100% but observed for ≥ 72h with continuous gate-greens | `CV_ASSEMBLY_CANARY_PCT=100`, `CV_ASSEMBLY_DEFAULT_ON=false` (gate not yet flipped) |
| `default_on` | 100% by default | `CV_ASSEMBLY_DEFAULT_ON=true` |

### 14.2 State machine

```
shadow ──(T1)──▶ canary_1 ──(T2)──▶ canary_5 ──(T3)──▶ canary_25 ──(T4)──▶ soak ──(T5)──▶ default_on
   ▲                │                  │                  │                 │
   │                │                  │                  │                 │
   └────(R*)────────┴──────────────────┴──────────────────┴─────────────────┘
                              rollback to shadow
```

### 14.3 Transition triggers

| Transition | Required gates green | Required observation window | Manual or automatic |
|------------|----------------------|------------------------------|---------------------|
| T1: shadow → canary_1 | per-stage benchmarks; harness (§11); flag mutual-exclusion probe | ≥ 24h in shadow with zero gate failures | manual |
| T2: canary_1 → canary_5 | T1 gates + canary_1 produced ≥ 1 successful end-to-end | ≥ 24h in canary_1 | manual |
| T3: canary_5 → canary_25 | T2 gates + canary_5 cost p95 within band; zero deadletter | ≥ 48h in canary_5 | manual |
| T4: canary_25 → soak | T3 gates + canary_25 published count ≥ 10; reviewer sample ≥ 5 with score ≥ 4.0 | ≥ 48h in canary_25 | manual |
| T5: soak → default_on | T4 gates + 72h soak with zero gate failures | ≥ 72h in soak | manual |
| R*: any → shadow | gate failure (cost breaker repeatedly tripped, or any blocking gate fails 3 consecutive runs) | none | **automatic** when configured, manual otherwise |

The rollback transition R* is **automatic** when
`CV_ASSEMBLY_AUTO_ROLLBACK=true` and the gate script runs in
hourly cron (`scripts/gate_cv_assembly_rollout.py --auto-rollback`).
Otherwise R* is manual and triggered by the operator runbook
(§17.7).

Forward transitions (T1–T5) are **always manual**. The gate script
**never** advances state automatically — that is a hard cross-artifact
invariant (§19) and a fail-closed rule (§20).

### 14.4 Canonical rollout-state artifact

```
infra/rollout/cv_assembly/current_rollout_state.json
```

Schema:

```json
{
  "state": "shadow" | "canary_1" | "canary_5" | "canary_25" | "soak" | "default_on",
  "started_at": "<utc_iso8601>",
  "previous_state": null | "<state>",
  "flag_snapshot": {
    "MASTER_CV_BLUEPRINT_V2_ENABLED": true,
    "CV_ASSEMBLY_HEADER_BLUEPRINT_ENABLED": true,
    "CV_ASSEMBLY_PATTERN_SELECTION_ENABLED": true,
    "CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED": true,
    "CV_ASSEMBLY_GRADE_SELECT_ENABLED": true,
    "CV_ASSEMBLY_PUBLISH_WINNER_ENABLED": true,
    "CV_ASSEMBLY_DOSSIER_V2_ENABLED": true,
    "CV_ASSEMBLY_DEFAULT_ON": false,
    "CV_ASSEMBLY_SHADOW_MODE": false,
    "CV_ASSEMBLY_CANARY_ALLOWLIST": "...",
    "CV_ASSEMBLY_CANARY_PCT": 25
  },
  "advanced_by": "<github_user>",
  "advance_reason": "<= 240 chars",
  "gate_report_ref": "reports/cv-assembly-end-to-end/<run_id>/comparison.json",
  "schema_version": "v1"
}
```

This file is the single source of truth for the rollout state. It is
checked into git on transition; PR describes the transition reason and
links to the gate report. Workers read it on startup; any mismatch
between the artifact's `flag_snapshot` and the live worker environment
fails the health probe.

### 14.5 Who is allowed to advance

Forward transitions:

- require a PR modifying `current_rollout_state.json`;
- require approval from the family owner role (`pipeline_owner`,
  see §17);
- require a green gate script run referenced by `gate_report_ref`.

Rollback transitions:

- on automatic rollback, the gate script writes a new artifact with
  `state="shadow"`, `previous_state="<prior>"`,
  `advanced_by="auto-rollback-script"`, and an audit row in
  `cv_assembly_rollout_events` (Mongo);
- on manual rollback, the operator commits the artifact change and
  references the runbook scenario.

### 14.6 Partial-application semantics

If a transition partially applies (artifact updated but worker env
not yet reloaded):

- workers continue to use their loaded snapshot until they restart;
- the next worker startup health probe detects the artifact/env
  mismatch and refuses to start;
- operator must roll the workers (`systemctl restart scout-cv-
  assembly-worker@*.service`) for the transition to take effect;
- the transition is considered **complete** only when every worker's
  loaded snapshot matches the artifact, asserted by the
  `cv_assembly.flag_snapshot_observed` event (§14.7).

### 14.7 Rollout observation events

A `rollout_state_observed` event is emitted by every worker on
startup with metadata `{state, flag_snapshot, observed_at}`. The
operator dashboard (frontend) aggregates these events and surfaces
"workers in state X" counts. The end-to-end harness (§11) emits
exactly one synthetic `rollout_state_observed` event with
`state="shadow"` so harness runs never appear as production traffic.

## 15. Rollout Gate Script Contract

### 15.1 Canonical path and CLI

Module: `scripts/gate_cv_assembly_rollout.py`.

```
python -u scripts/gate_cv_assembly_rollout.py
  [--corpus-root data/eval/validation]
  [--end-to-end-report reports/cv-assembly-end-to-end/<run_id>/comparison.json]
  [--cost-window-minutes 60]
  [--report-out reports/rollout-gate/<run_id>.json]
  [--auto-rollback]
  [--observe-only]
```

`--auto-rollback` only takes effect when
`CV_ASSEMBLY_AUTO_ROLLBACK=true` is also set in the environment;
omitting either renders the flag report-only.

`--observe-only` forces report-only mode regardless of any other
input. This is the mode used during the §7.5 hard-prerequisite
ramp-up.

### 15.2 Exit codes

| Exit code | Meaning |
|-----------|---------|
| 0 | All gates pass (`overall=pass`) |
| 1 | At least one gate fails (`overall=fail`) |
| 2 | Infrastructure error (corpus unreadable, Mongo unreachable, gate script bug) |

The script never exits with any other code. Wrappers (cron, CI)
treat:

- 0 → continue;
- 1 → block forward transition; if `--auto-rollback`, perform
  rollback (§14.5);
- 2 → page the runbook owner (§17.6); do **not** auto-rollback on
  exit 2 (cause is unknown; rolling back a healthy state on a
  spurious infra error is worse than waiting for a human).

### 15.3 JSON output schema

```json
{
  "schema_version": "v1",
  "ts": "<utc_iso8601>",
  "run_id": "<utc_iso8601>-<short_sha>",
  "current_state": "shadow" | "canary_1" | ... | "default_on",
  "gates": [
    {
      "name": "per_stage_4_3_2_invariants",
      "status": "pass" | "fail" | "warn" | "skipped",
      "detail": "<= 240 chars",
      "stage_ref": "4.3.2",
      "report_ref": "reports/.../baseline_report.json"
    },
    {
      "name": "end_to_end_harness",
      "status": "pass" | "fail" | "warn",
      "detail": "<= 240 chars",
      "report_ref": "reports/cv-assembly-end-to-end/<run_id>/comparison.json"
    },
    {
      "name": "cost_per_job_ceiling",
      "status": "pass" | "fail" | "warn",
      "detail": "max=2.42 USD; ceiling=2.50 USD"
    },
    {
      "name": "cost_per_hour_ceiling",
      "status": "pass" | "fail",
      "detail": "rolling=11.20 USD; ceiling=15.00 USD"
    },
    {
      "name": "trace_ref_propagation",
      "status": "pass" | "fail",
      "detail": "<= 240 chars"
    },
    {
      "name": "flag_mutual_exclusion",
      "status": "pass" | "fail",
      "detail": "<= 240 chars"
    },
    {
      "name": "rollout_state_artifact_parseable",
      "status": "pass" | "fail",
      "detail": "<= 240 chars"
    },
    {
      "name": "session_id_stability",
      "status": "pass" | "fail",
      "detail": "<= 240 chars"
    }
  ],
  "stage_summaries": {
    "4.3.2": {"corpus_pass_rate": 1.0, "cost_usd_p95": 0.12},
    "4.3.3": {...},
    "4.3.4": {...},
    "4.3.5": {...},
    "4.3.6": {...},
    "4.3.7": {...}
  },
  "overall": "pass" | "fail",
  "rollback_advised": false | true,
  "advised_action": "advance" | "hold" | "rollback" | "page_owner"
}
```

### 15.4 Mutation policy

The gate script is **report-only** in its happy path. It writes:

- `reports/rollout-gate/<run_id>.json` (the JSON above);
- `cv_assembly_rollout_events` row with `event_type="gate_run"`.

It does **not** mutate feature flags. It does **not** edit
`current_rollout_state.json` for forward transitions.

The single exception: `--auto-rollback` AND
`CV_ASSEMBLY_AUTO_ROLLBACK=true` AND `overall=fail` AND
`current_state ∈ {canary_1, canary_5, canary_25, soak, default_on}`
together permit the script to write a new
`current_rollout_state.json` with `state="shadow"`,
`advanced_by="auto-rollback-script"`, plus a
`cv_assembly_rollout_events` row with
`event_type="auto_rollback"`. Even in this case, feature flags are
**not** mutated; flag flips are the operator's job (the artifact is
configuration, not orchestration).

### 15.5 Replay and idempotence

The gate script is idempotent for a given `(corpus state, mongo
snapshot, ts)`. Re-running it on the same inputs produces a
byte-equal report (modulo the `ts` and `run_id` fields). This is
asserted by `tests/unit/cv_assembly/test_gate_script_idempotence.py`.

### 15.6 Consumers

The gate script's JSON output is consumed by:

- the rollout PR template (operator pastes `overall` and gate
  summary into the PR body);
- the cron wrapper (`infra/cron/cv-assembly-rollout-gate.cron`)
  which runs hourly when configured;
- the operator dashboard reader (
  `frontend/repositories/discovery_repository.py` adds a method
  `latest_rollout_gate_report()` that surfaces the most recent
  report);
- the auto-rollback path (§15.4).

## 16. Production-Readiness Gates

The 4.3 family is production-ready (eligible for `default_on`) only
when **all** of the following are true.

### 16.1 Functional gates

- end-to-end: a `cv_ready` canary job reaches `published` with
  winner + synthesis + projection + dossier;
- diversity: the three drafts for each canary job pass the 4.3.3
  diversity invariant;
- truth: the evidence-lineage validator passes on every published
  synthesis;
- fault tolerance: a fault-injected pdf-service flake produces correct
  retry, then either recovery or clean terminal failure;
- compatibility: the legacy projection fields on `level-2` exactly
  match the synthesis projection; no legacy field lost.

### 16.2 Operational gates

- per-stage units are independently scaleable;
- per-stage backlogs are visible in the frontend dashboard (4.3.7);
- per-surface publish states are separately retriable;
- pdf-service `/health` gating works; an induced failure prevents
  claim; recovery restarts claims automatically;
- per-job cost ≤ `CV_ASSEMBLY_MAX_COST_USD` for every published job;
- per-hour cost ≤ `CV_ASSEMBLY_MAX_COST_USD_PER_HOUR` for every
  rolling 60-minute window during canary;
- per-hour deadletter ≤ `CV_ASSEMBLY_MAX_DEADLETTER_PER_HOUR`.

### 16.3 Observability gates

- every stage emits Langfuse traces in the canonical namespace
  (§8.2);
- per-job stage timeline is visible end-to-end in Langfuse, joined
  by `langfuse_session_id=job:<level2_id>` (§9);
- Langfuse retention policy (iteration-4 §10) holds and is verified;
- `cv_assembly.timing_breakdown` is populated for every published
  job (see §25 Q1 resolution).

### 16.4 Infrastructure gates

- `infra/systemd/scout-cv-assembly-worker@.service` and
  `scout-publish-worker@.service` are installed and documented;
- `infra/scripts/verify-cv-assembly-cutover.sh` and
  `verify-publish-cutover.sh` exist and pass;
- pdf-service container is tagged, pinned, and health-gated in
  compose.

### 16.5 Test gates

- per-stage benchmark suites pass;
- end-to-end benchmark suite passes (§11);
- fault-case suite passes (pdf-service down, n8n timeout, Sheets
  500, draft exhaustion);
- compatibility projection round-trip test passes;
- Langfuse trace-ref round-trip test passes;
- idempotency tests for every 4.3 work-item type;
- gate-script tests pass (§23);
- session-lifetime tests pass (§9.5);
- cost-aggregation tests pass (§23).

### 16.6 Documentation gates

- `docs/current/architecture.md` updated with the 4.3 lane;
- `docs/current/cv-generation-guide.md` updated to reference 4.3.2
  header blueprint + 4.3.5 grader rubric + 4.3.7 projection map;
- `docs/current/missing.md` session entries per AGENTS.md rules;
- `docs/current/operational-development-manual.md` updated with the
  4.3 runbook (§17).

### 16.7 Flag mutual-exclusion gates

Enforced by `src/cv_assembly/health_probe.py` at worker startup; the
worker template refuses to start if any invariant fails:

- `CV_ASSEMBLY_DEFAULT_ON=true` requires every 4.3 sub-flag true;
- `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=true` requires
  `CV_ASSEMBLY_GRADE_SELECT_ENABLED=true`;
- `CV_ASSEMBLY_GRADE_SELECT_ENABLED=true` requires
  `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED=true`;
- `CV_ASSEMBLY_DRAFT_ASSEMBLY_ENABLED=true` requires
  `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED=true`;
- `CV_ASSEMBLY_PATTERN_SELECTION_ENABLED=true` requires
  `CV_ASSEMBLY_HEADER_BLUEPRINT_ENABLED=true`;
- `CV_ASSEMBLY_HEADER_BLUEPRINT_ENABLED=true` requires
  `MASTER_CV_BLUEPRINT_V2_ENABLED=true`;
- `CV_ASSEMBLY_SHADOW_MODE=true` AND
  `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=true` is forbidden (shadow
  mode suppresses publisher compatibility writes).

## 17. Operator Runbook Additions

Every scenario carries an explicit `owner_role`, `escalation_path`,
and `acceptable_recovery_time`. Owner roles are aliases that map to
real on-call rotations in
`docs/current/operational-development-manual.md`:

| Owner role | Maps to |
|------------|---------|
| `oncall_eng` | first-line on-call engineer for scout pipeline |
| `oncall_data` | first-line on-call for data integrity |
| `pipeline_owner` | family owner for 4.3 (single human) |
| `tech_lead` | escalation owner above pipeline_owner |

`escalation_path` is a sequence of `(time_threshold, owner)` pairs.
Beyond the last threshold the owner stays the last named role.

### 17.1 Scenario: "All three drafts failed"

- **owner_role:** `oncall_eng`
- **escalation_path:** `<10min: oncall_eng → <30min: pipeline_owner
  → <2h: tech_lead`
- **acceptable_recovery_time:** 2 hours
- **manual or scripted:** manual diagnosis; no scripted auto-repair
- **symptom:** `cv_assembly.status="failed"`, `lifecycle="failed"`,
  every `DraftDoc.status="failed"`
- **playbook:**
  1. open `scout.cv.draft_assembly` traces for each draft; inspect
     `violations[]`;
  2. if violations converge on a master-CV issue (taxonomy miss,
     unresolved credibility marker), open the master-CV sidecar; fix
     and re-commit; re-enqueue root via
     `scripts/enqueue_stage.py --stage cv.header_blueprint --job <id>`;
  3. if violations indicate the pattern selector produced patterns
     with thin evidence, inspect
     `scout.cv.pattern_selection.diversity_report` and
     `cv_assembly.pattern_selection.patterns[*].confidence.band`;
     consider widening allowlist via
     `role_metadata.acceptable_titles`.

### 17.2 Scenario: "Synthesis degraded"

- **owner_role:** `oncall_eng`
- **escalation_path:** `<30min: oncall_eng → <2h: pipeline_owner`
- **acceptable_recovery_time:** designed behavior; no recovery
- **manual or scripted:** scripted (analysis only)
- **symptom:** `cv_assembly.synthesis.degraded=true` with
  `reason="no_improvement"`; CV publishes as-is
- **playbook:** none required; this is designed behavior. For
  recurring cases, run `scripts/review_synthesis_rollbacks.py`
  (4.3.5) and review rubric weights with `pipeline_owner`.

### 17.3 Scenario: "pdf-service unhealthy"

- **owner_role:** `oncall_eng`
- **escalation_path:** `<10min: oncall_eng → <30min: pipeline_owner`
- **acceptable_recovery_time:** 30 minutes
- **manual or scripted:** manual (SSH + restart)
- **symptom:**
  `scout.publish.render.cv.unhealthy_pdf_service` events rising;
  `cv_assembly.publish_state.render.cv.status=pending` backlog
  growing
- **playbook:**
  1. SSH to the VPS, check `systemctl status scout-pdf-service`;
  2. check Playwright install
     (`playwright install chromium --dry-run`);
  3. restart container:
     `systemctl restart scout-pdf-service.service`;
  4. confirm `curl -s $PDF_SERVICE_URL/health` returns
     `playwright_ready=true`;
  5. publish workers automatically resume on the next claim cycle.

### 17.4 Scenario: "n8n webhook timeouts"

- **owner_role:** `oncall_eng`
- **escalation_path:** `<10min: oncall_eng → <60min: pipeline_owner`
- **acceptable_recovery_time:** 1 hour
- **manual or scripted:** manual
- **symptom:** `scout.publish.upload.drive.webhook_timeout` event
  cluster
- **playbook:**
  1. verify n8n host reachable and cron workflows running;
  2. inspect n8n workflow logs for the cv-upload webhook;
  3. if persistent, pause
     `scout-publish-worker@upload_drive.service` until n8n is
     stable; existing work items will retry on resume.

### 17.5 Scenario: "Sheets row missing"

- **owner_role:** `oncall_data`
- **escalation_path:** `<2h: oncall_data → <24h: pipeline_owner`
- **acceptable_recovery_time:** 24 hours (CV publish is unaffected)
- **manual or scripted:** scripted (re-enqueue is idempotent)
- **symptom:** `cv_assembly.publish_state.upload.sheets.status=
  failed` after retry exhaustion; CV still published
- **playbook:**
  1. inspect Sheets API quota and service-account token expiry;
  2. re-enqueue `publish.upload.sheets` work item via
     `scripts/enqueue_stage.py --stage publish.upload.sheets
     --job <id>` (idempotent by `idempotency_key`);
  3. if systemic, page `pipeline_owner`; CV publish is unaffected.

### 17.6 Scenario: "Rollout gate script failure (exit 2)"

- **owner_role:** `pipeline_owner`
- **escalation_path:** `<30min: pipeline_owner → <2h: tech_lead`
- **acceptable_recovery_time:** 2 hours
- **manual or scripted:** manual (do not auto-rollback on exit 2)
- **symptom:** gate script exits 2; cron alert fires; no rollout
  artifact mutation
- **playbook:**
  1. read latest report under `reports/rollout-gate/`;
  2. tail script log for stack trace;
  3. classify: corpus drift, Mongo connectivity, Langfuse client
     bug, or harness regression;
  4. fix root cause; do **not** auto-rollback to `shadow` on a bare
     exit 2 — investigate first;
  5. re-run gate script manually with `--observe-only` to confirm
     fix.

### 17.7 Scenario: "Cost breaker triggered"

- **owner_role:** `pipeline_owner`
- **escalation_path:** `<30min: pipeline_owner → <2h: tech_lead`
- **acceptable_recovery_time:** 1 hour for per-hour breaker; same-day
  for per-job
- **manual or scripted:** scripted (auto-pause + auto-resume on
  per-hour); manual investigation always
- **symptom:** `cost_breaker_tripped` event; worker pauses new claims;
  alert fires
- **playbook:**
  1. inspect last hour's
     `cv_assembly_stage_runs` rows: top costs, models used, retries;
  2. if a single job blew the per-job ceiling, fail that job, mark
     `fail_reason="cost_breaker"`, and review its inputs (oversized
     master-CV section, runaway pattern, etc.);
  3. if the per-hour ceiling is tripping due to legitimate volume,
     raise `CV_ASSEMBLY_MAX_COST_USD_PER_HOUR` via PR with rationale;
  4. if cost is climbing without volume, consider rolling back via
     §17.8 (rollout gate failure path).

### 17.8 Scenario: "Auto-rollback fired"

- **owner_role:** `pipeline_owner`
- **escalation_path:** `<10min: pipeline_owner → <30min: tech_lead`
- **acceptable_recovery_time:** investigate within 1 hour;
  re-advance only after fix
- **manual or scripted:** scripted (the rollback itself); manual
  (investigation and re-advance)
- **symptom:** `current_rollout_state.json` has been overwritten to
  `state="shadow"` with `advanced_by="auto-rollback-script"`; alert
  fires
- **playbook:**
  1. read the gate report referenced in the new artifact's
     `gate_report_ref`;
  2. identify which gate failed; cross-reference per-stage runbook
     entry above;
  3. fix root cause; re-run gate script; re-advance manually via
     PR (no auto-advance ever, §14.3);
  4. confirm operator dashboard reflects new state.

### 17.9 Cross-scenario constants

- every runbook scenario includes a "verify worker state" step:
  confirm `current_rollout_state.json` matches live workers via the
  `rollout_state_observed` event aggregation;
- alerts are dispatched via the existing scout pipeline alerting
  channel (slack/email per `operational-development-manual.md`);
- post-incident: every scenario triggers a session entry in
  `docs/current/missing.md` per AGENTS.md rules.

## 18. Migration And Historical Data Policy

- pre-4.3 jobs are not migrated. Historical `level-2` documents
  retain their legacy publisher fields;
- `scripts/mark_legacy_cv_ready.py` (4.3.7) tags historical jobs
  with `cv_assembly.legacy=true` so dashboards can filter them out
  of 4.3 counters; the frontend defaults to "show only non-legacy"
  with a toggle;
- no deletion of Mongo state on rollback; all `cv_assembly.*`
  subtrees remain for audit;
- the rollout-state artifact's git history is the audit log for
  forward and rollback transitions.

## 19. Cross-Artifact Invariants

The following invariants bind 4.3.8's contracts to the rest of the
4.3 family:

- 4.3.8 never overrides stage-local truth rules; per-stage validators
  (header validator, pattern validator, evidence-lineage validator,
  dossier validator) remain owned by the per-stage plans;
- rollout cannot advance to the next state when any blocking gate
  fails (§14.3 + §15.4);
- the rollout-gate script never advances rollout state automatically;
  only rollback may be automatic (§14.3, §15.4);
- the tracing contract (§8) is consistent across every 4.3 stage;
  per-stage plans may add stage-specific spans/events but may not
  rename canonical names or weaken metadata caps;
- the end-to-end harness (§11) operates only on frozen inputs;
  any case that requires a live fetch is a corpus error, not a
  harness limitation;
- per-stage plans remain the source of per-stage schema truth; 4.3.8
  reads but never edits per-stage schemas;
- cost aggregation (§13) never invents missing per-stage cost; null
  is recorded as warning, never silently substituted;
- runbook scenarios (§17) map to actual stage/status surfaces:
  every `symptom` field references a real Mongo path or a real
  Langfuse span/event;
- rollout state must reflect flag reality; the worker startup health
  probe (§16.7 + §14.6) refuses to start if the artifact's
  `flag_snapshot` and the live env disagree;
- session id (§9) is stable per `level2_id` across retries and
  re-runs; it is never rotated even under retention pressure.

## 20. Fail-Open / Fail-Closed

### 20.1 Fail-open paths

- gate script in `--observe-only` mode reports but never blocks;
- gate script in any mode emits a JSON report even on internal
  failure (exit 2); the report records the error and is still
  consumable;
- the harness skips a case (records `status="skipped"`) when its
  frozen-input checksum drifts; this is a warning, not a failure,
  unless more than 10% of cases are skipped — at which point the
  `end_to_end_harness` gate fails;
- `cv_assembly.total_cost_usd` records `cost_aggregation_warnings[]`
  when a per-stage cost is null but the stage completed successfully
  (§13.5);
- the per-hour cost breaker auto-recovers after 15 minutes when the
  rolling sum drops below the ceiling.

### 20.2 Fail-closed paths

- worker startup fails closed when the rollout-state artifact is
  unparseable, missing, or its `flag_snapshot` disagrees with the
  live env;
- worker startup fails closed when any registered health probe fails;
- `CV_ASSEMBLY_DEFAULT_ON=true` requires every sub-flag true (§16.7);
- gate script fails closed (exit 1) when any blocking gate fails;
- the per-job cost breaker fails closed: a job that exceeds
  `CV_ASSEMBLY_MAX_COST_USD` is failed, not silently truncated;
- forward rollout transitions are always manual; no automatic
  advancement is permitted regardless of gate-greenness streak.

## 21. Operational Catalogue

Because 4.3.8 is a family-level contract rather than a content stage,
this catalogue is implementation-facing and cross-stage.

### 21.1 Owning subsystems

- `src/cv_assembly/tracing.py` — tracing seam;
- `src/cv_assembly/health_probe.py` — startup invariant probe;
- `src/cv_assembly/cost_breaker.py` — per-job and per-hour breakers;
- `src/cv_assembly/cost_aggregation.py` (new) — total-cost formula
  (§13);
- `scripts/gate_cv_assembly_rollout.py` — rollout gate;
- `scripts/benchmark_cv_assembly_end_to_end.py` — harness runner;
- `scripts/review_synthesis_rollbacks.py` — analysis tool (4.3.5
  ownership; 4.3.8 references in runbook);
- `infra/rollout/cv_assembly/current_rollout_state.json` — rollout
  state artifact;
- `infra/scripts/verify-cv-assembly-cutover.sh` — cross-family
  cutover verifier.

### 21.2 Prerequisite suites and harnesses

- per-stage benchmark suites (4.3.1–4.3.7) — owned by each stage;
- end-to-end harness (§11) — owned by 4.3.8;
- gate-script tests, session-lifetime tests, cost-aggregation tests,
  rollout-state-machine tests — owned by 4.3.8 (§23).

### 21.3 Persisted artifacts and files

| Artifact | Path | Owner |
|---------|------|-------|
| End-to-end corpus | `data/eval/validation/cv_assembly_4_3_8_end_to_end/` | 4.3.8 |
| Rollout-state file | `infra/rollout/cv_assembly/current_rollout_state.json` | 4.3.8 |
| Gate-script reports | `reports/rollout-gate/<run_id>.json` | 4.3.8 (gitignored except per-PR) |
| Harness reports | `reports/cv-assembly-end-to-end/<run_id>/` | 4.3.8 (gitignored except per-PR) |
| Runbook updates | `docs/current/operational-development-manual.md` | 4.3.8 |
| Architecture updates | `docs/current/architecture.md` | 4.3.8 |
| CHANGELOG (corpus) | `data/eval/validation/cv_assembly_4_3_8_end_to_end/CHANGELOG.md` | 4.3.8 |

### 21.4 Stage-run / job-run records touched or read

- 4.3.8 **reads** `cv_assembly_stage_runs` for cost aggregation
  (§13) and per-hour breaker (§13.4); never writes;
- 4.3.8 **reads** `cv_assembly_job_runs` (if introduced by 4.3.7) for
  dashboard rollups; never writes;
- 4.3.8 **writes** `cv_assembly_rollout_events` rows for
  `gate_run`, `auto_rollback`, `rollout_state_observed_aggregate`.

### 21.5 Health-probe registry ownership

`src/cv_assembly/health_probe.py` exposes:

```python
def register_health_probe(name: str, probe: Callable[[], ProbeResult]) -> None: ...
def run_all_health_probes() -> list[ProbeResult]: ...
```

Every 4.3 stage registers its own probe at module-import time; 4.3.8
owns the registry but not the per-stage probe bodies. The worker
startup runs all probes; any `ProbeResult.status="fail"` aborts
startup.

### 21.6 Rollout-state artifact ownership

The artifact at `infra/rollout/cv_assembly/current_rollout_state.json`
is owned by 4.3.8. Every other plan reads it for context but does
not write it. The gate script is the only auto-writer (rollback
only, §15.4).

### 21.7 Retry / repair behavior

4.3.8 introduces no new retries. Per-stage retries follow per-stage
plans. Gate-script and harness failures do not retry; they emit a
report and exit per §15.2.

### 21.8 Operator-visible success/failure signals

- `current_rollout_state.json` `state` field;
- `reports/rollout-gate/<run_id>.json` `overall` and `gates[]`;
- `cv_assembly_rollout_events` collection;
- frontend dashboard "rollout state" widget (consumes
  `latest_rollout_gate_report()`);
- Langfuse session per job (§9).

### 21.9 Feature flags owned

| Flag | Purpose | Default |
|------|---------|---------|
| `CV_ASSEMBLY_AUTO_ROLLBACK` | enables auto-rollback on gate fail | false |
| `CV_ASSEMBLY_MAX_COST_USD` | per-job cost ceiling | 2.50 |
| `CV_ASSEMBLY_MAX_COST_USD_PER_HOUR` | per-hour cost ceiling | 15.00 |
| `CV_ASSEMBLY_MAX_DEADLETTER_PER_HOUR` | per-hour deadletter ceiling | 5 |
| `LANGFUSE_CV_ASSEMBLY_TRACING_ENABLED` | tracing seam on/off | false |
| `LANGFUSE_CV_ASSEMBLY_CAPTURE_FULL_PROMPTS` | prompt-capture toggle | false |

Other flags are owned by the umbrella or per-stage plans; 4.3.8
references them in §14 and §16.7 but does not own them.

### 21.10 Rollback strategy

Family-level rollback is a state transition to `shadow` (§14.3 R*).
Persisted Mongo state is not deleted. Trace data is not deleted.
Operator playbook §17.8 describes the human side.

### 21.11 Why 4.3.8 is not a content-producing stage

4.3.8 produces no candidate-facing artifact. It produces:

- contracts (tracing, harness, cost, rollout, runbook);
- gates (gate script, regression gates);
- machinery (state machine, cost breakers, health-probe registry).

It is the family's compliance layer. Per-stage plans remain the
source of truth for the content side.

## 22. Downstream-Consumer Contracts

### 22.1 What consumers may rely on from 4.3.8

- **`scripts/gate_cv_assembly_rollout.py`** consumers may rely on:
  - the JSON output schema (§15.3) being stable across patch
    releases (`schema_version` bumps on breaking changes);
  - exit codes 0/1/2 being the only possible exits (§15.2);
  - report-only behavior in the absence of `--auto-rollback` AND
    `CV_ASSEMBLY_AUTO_ROLLBACK=true` (§15.4);
  - idempotence on `(corpus state, mongo snapshot, ts)` (§15.5).
- **Dashboards** (frontend `latest_rollout_gate_report()`,
  `intel_dashboard.py`) may rely on:
  - `reports/rollout-gate/<run_id>.json` files being durable until
    the next successful run;
  - `current_rollout_state.json` schema (§14.4) being stable;
  - `rollout_state_observed` events being emitted on every worker
    startup;
  - `cv_assembly.timing_breakdown` being populated on every
    published job (§25 Q1).
- **Operator tooling** (`scripts/enqueue_stage.py`,
  `scripts/mark_legacy_cv_ready.py`) may rely on:
  - the runbook scenario list (§17) being authoritative;
  - the `cv_assembly_rollout_events` collection schema being stable.
- **CI / release automation** may rely on:
  - the gate script being safe to run in dry mode (`--observe-only`)
    against any environment;
  - the harness fixture layout (§11.5) being deterministic across
    runs.
- **Per-stage plans inheriting tracing conventions** may rely on:
  - the canonical name list (§8.2) being authoritative;
  - the metadata field set (§8.3) being a superset of what each
    span produces;
  - the session-id rule (§9) holding for any new stage they add.
- **Benchmark comparison scripts** may rely on:
  - `baseline_report.json` shape per stage being stable for the
    fields the cross-family gate consumes (`pass_rate`,
    `cost_usd_p95`, `metric_*`);
  - the `comparison.json` shape (§11.6) being stable.

### 22.2 What consumers must not assume

- Langfuse is **not** queryable for orchestration decisions;
- the rollout-state artifact is **not** the right place to encode
  per-job state — it is family-level configuration;
- `cv_assembly.total_cost_usd` is **not** stable mid-run; only the
  final value (written by `finalize_published`) is observable;
- the gate script does **not** mutate flags; do not chain it as a
  flag-flip mechanism;
- the harness output is **not** a substitute for production
  monitoring; it covers only the frozen corpus.

## 23. Tests And Evals

### 23.1 Gate-script tests

`tests/unit/cv_assembly/test_gate_script.py`:

- exit code 0 on a green corpus + green Mongo snapshot;
- exit code 1 on a corpus regression injected into a single case;
- exit code 1 on a per-job cost overage injected into Mongo;
- exit code 1 on a per-hour cost overage injected into
  `cv_assembly_stage_runs`;
- exit code 1 on a missing trace_ref injected into Mongo;
- exit code 2 on Mongo unreachable;
- exit code 2 on corpus directory missing;
- `--observe-only` always returns exit code 0 regardless of gate
  results;
- `--auto-rollback` without `CV_ASSEMBLY_AUTO_ROLLBACK=true` leaves
  the rollout artifact unchanged;
- `--auto-rollback` with the env flag rewrites the artifact to
  `state="shadow"` on `overall=fail` from a non-shadow state.

### 23.2 JSON-output contract tests

`tests/unit/cv_assembly/test_gate_script_json_contract.py`:

- the JSON output validates against the schema in §15.3;
- `schema_version` is `"v1"`;
- each `gates[*].name` ∈ a fixed canonical set;
- `overall ∈ {pass, fail}` (never anything else);
- `advised_action ∈ {advance, hold, rollback, page_owner}`.

### 23.3 Rollout state-machine tests

`tests/unit/cv_assembly/test_rollout_state_machine.py`:

- valid transitions T1–T5 are accepted in order with required gates;
- invalid forward transitions (e.g., shadow → canary_5) are
  rejected;
- rollback R* from any non-shadow state writes
  `state="shadow"`, `previous_state=<prior>`,
  `advanced_by="auto-rollback-script"`;
- a forward transition signed by `auto-rollback-script` is rejected
  (forward is always manual, §14.3);
- partial-application detection: artifact updated but env
  unchanged → health probe fail.

### 23.4 Cost-aggregation tests

`tests/unit/cv_assembly/test_cost_aggregation.py`:

- formula in §13.1 holds against fixture stage outputs;
- missing per-stage cost records a warning, not a fabrication;
- the aggregator never writes mid-run; only `finalize_published`
  writes;
- re-run preserves prior totals in `cv_assembly.cost_history[]`;
- per-job breaker rejects a stage claim when the running total +
  expected band would exceed `CV_ASSEMBLY_MAX_COST_USD`;
- per-hour breaker pauses claims when the rolling 60-minute sum
  exceeds `CV_ASSEMBLY_MAX_COST_USD_PER_HOUR`.

### 23.5 Langfuse session-id tests

See §9.5.

### 23.6 Benchmark-harness contract tests

`tests/unit/cv_assembly/test_end_to_end_harness_contract.py`:

- frozen-input checksum drift fails closed (or skips, with the
  10%-cutoff rule);
- tolerance bands are honored field-by-field per §11.3;
- comparison report shape matches §11.6;
- `corpus_version` mismatch produces `skipped_for_baseline_version`
  entries (§11.7).

### 23.7 Frozen-fixture reproducibility tests

`tests/unit/cv_assembly/test_frozen_fixture_reproducibility.py`:

- running the harness twice on the same case produces byte-equal
  results modulo the tolerance bands;
- `chosen_title`, `pattern_id`, `synthesis_hash`,
  `artifact_sha256`, and compatibility-projection fields are
  byte-equal across runs.

### 23.8 Operator-runbook mapping tests

`tests/unit/cv_assembly/test_runbook_mapping.py`:

- every scenario in §17 has `owner_role`, `escalation_path`,
  `acceptable_recovery_time`, and `manual_or_scripted` populated;
- every `symptom` reference resolves to a real Mongo path or a real
  Langfuse span/event in the canonical list (§8.2);
- every playbook step references a real script under `scripts/` or
  `infra/scripts/` if it claims to.

### 23.9 Trace-metadata-completeness tests

`tests/unit/cv_assembly/test_tracing_metadata_completeness.py` (also
referenced in §8.3): every canonical span name produces every
required metadata field.

### 23.10 Regression corpus design

The regression corpus (under
`data/eval/validation/cv_assembly_4_3_8_end_to_end/`) follows the
shape in §10.1 and §10.2. Cases are added by PR; each case carries a
reviewer-rated `acceptance.md`. The corpus is versioned by
`corpus_version` in `case_meta.json`.

### 23.11 Live smoke tests

`scripts/smoke_cv_assembly_end_to_end.py` (4.3.8-owned wrapper):
loads `.env` from Python, fetches one `cv_ready` job by `_id`, runs
the full lane locally against live LLM + transports, validates
outputs against an expected shape (not byte-exact — live LLM), and
prints heartbeats every 15 s.

### 23.12 VPS validation tests

See §24.

## 24. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This section is the live-run chain for 4.3.8's gate script,
harness, cost aggregation, session id, and rollout state artifact.

### 24.1 Local prerequisite tests before touching VPS

- `pytest -k "cv_assembly and not slow"` clean;
- `pytest tests/unit/cv_assembly/test_gate_script*.py` clean;
- `pytest tests/unit/cv_assembly/test_rollout_state_machine.py`
  clean;
- `pytest tests/unit/cv_assembly/test_cost_aggregation.py` clean;
- `pytest tests/unit/cv_assembly/test_session_lifetime.py` clean;
- `python -u scripts/gate_cv_assembly_rollout.py --observe-only
  --report-out reports/rollout-gate/local-dry-run.json` exits 0 with
  a parseable report.

### 24.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path;
- verify deployed
  `infra/rollout/cv_assembly/current_rollout_state.json` exists and
  parses;
- verify `scripts/gate_cv_assembly_rollout.py` resolves on
  `/root/scout-cron/.venv/bin/python`;
- verify per-stage corpora exist under
  `/root/scout-cron/data/eval/validation/cv_assembly_4_3_*/`;
- verify systemd templates
  `scout-cv-assembly-worker@.service` and
  `scout-publish-worker@.service` are installed;
- deployment is file-synced, not git-pulled — read file markers,
  do not `git status`.

### 24.3 Verify benchmark corpora and scripts

- end-to-end corpus has at least the 8 cases in §10.2;
- per-stage corpora are pinned via `baseline_report.json` to known
  commit refs;
- harness script `scripts/benchmark_cv_assembly_end_to_end.py`
  imports cleanly under the repo `.venv`.

### 24.4 Choose canary job set

For canary_1: pick exactly one real `level-2` job at
`lifecycle="cv_ready"` with rich research and clear role family
(prefer EM-mid-seniority or AI Staff-IC). Record `_id`, slug,
`master_cv_checksum`, `presentation_contract_checksum`. Add to
`CV_ASSEMBLY_CANARY_ALLOWLIST`. Do not include any job whose
`pre_enrichment.status` is `partial` or `unresolved`.

For canary_5 / canary_25: select a mix of role families per §10.2 to
cover the corpus distribution.

### 24.5 Validate trace/session behavior on VPS

After the canary job processes:

- open Langfuse, search session `job:<level2_id>`;
- assert one timeline includes every `scout.cv.*` and
  `scout.publish.*` span;
- assert `langfuse_session_id` metadata matches `job:<level2_id>` on
  every span;
- assert `trace_ref` is populated on every
  `cv_assembly.stage_states.*` row in Mongo;
- on a forced re-run (snapshot invalidation), assert the session id
  is unchanged and `cv_assembly_run_seq` incremented by 1.

### 24.6 Validate gate script behavior on VPS

```
nohup /root/scout-cron/.venv/bin/python -u \
  /root/scout-cron/scripts/gate_cv_assembly_rollout.py \
    --report-out /tmp/rollout-gate-vps-$(date -u +%Y%m%dT%H%M%SZ).json \
  > /tmp/rollout-gate.log 2>&1 &
```

- log emits heartbeats every 15–30s;
- exit 0 expected on a healthy environment;
- inspect output JSON: `gates[*].status`, `overall`,
  `advised_action`, `current_state`;
- repeat with `--observe-only` to confirm report-only behavior;
- repeat with `--auto-rollback` (without
  `CV_ASSEMBLY_AUTO_ROLLBACK=true`) to confirm artifact unchanged.

### 24.7 Validate cost aggregation on VPS

After the canary job publishes:

- read `level-2.cv_assembly.total_cost_usd`;
- recompute manually from
  `cv_assembly_stage_runs` rows (§13.1);
- assert equality within `cost_aggregation_warnings[]` boundaries;
- inspect
  `cv_assembly.cost_aggregation_warnings` if present;
- run `scripts/gate_cv_assembly_rollout.py --report-out ...` and
  confirm `cost_per_job_ceiling` gate is `pass` for the canary job.

### 24.8 Validate rollout-state artifact behavior on VPS

- read `infra/rollout/cv_assembly/current_rollout_state.json`;
- compare `flag_snapshot` against the live worker env via
  `systemctl show scout-cv-assembly-worker@cv-header-blueprint
  -p Environment`;
- confirm match; if mismatch, the worker startup health probe
  should already be failing.

### 24.9 Required launcher behavior

Every VPS launcher (gate script, harness, smoke) must:

- activate `.venv`
  (`source /root/scout-cron/.venv/bin/activate` or absolute path
  to `/root/scout-cron/.venv/bin/python`);
- use `python -u` for unbuffered output;
- load `.env` from Python:
  `from dotenv import load_dotenv;
   load_dotenv("/root/scout-cron/.env")`;
- read `MONGODB_URI` (not `MONGO_URI`);
- emit operator heartbeat every 15–30 s with: wall clock, elapsed,
  current substep, and (when relevant) monitored subprocess PID +
  stdout/stderr tail (first 128 chars);
- run with cwd in an isolated `/tmp/cv-assembly-<run_id>/` unless
  the script explicitly requires repo cwd.

### 24.10 Expected Mongo writes

On a successful VPS canary run:

- `level-2.cv_assembly.*` populated through `synthesis`,
  `publish_state`, `dossier_state`;
- `level-2.lifecycle="published"`;
- `level-2.cv_assembly.total_cost_usd` populated;
- `level-2.cv_assembly.timing_breakdown` populated (§25 Q1);
- `cv_assembly_stage_runs` rows written for every stage;
- `cv_assembly_rollout_events` row written by gate script run.

### 24.11 Expected Langfuse traces

Per §24.5 plus:

- one `rollout_state_observed` event per worker startup;
- one `gate_run` audit event from the gate-script wrapper if it
  emits Langfuse audit events (optional in v1).

### 24.12 Acceptance criteria

- log ends with
  `CV_ASSEMBLY_END_TO_END_RUN_OK job=<id> status=published trace=<url>`;
- Mongo writes match §24.10;
- Langfuse trace matches §24.11;
- gate-script run on VPS exits 0 (or `--observe-only` exits 0 with
  matching `overall`);
- the rollout artifact matches the live worker env;
- the runbook entry §17.6 was *not* triggered (no exit 2).

### 24.13 Artifact / log / report capture

Create `reports/cv-assembly-end-to-end/<run_id>/` containing:

- `run.log` — full stdout/stderr of the launcher;
- `level2_after.json` — final level-2 doc;
- `cv_assembly_subtree.json` — final subtree;
- `trace_url.txt` — Langfuse session URL;
- `gate_report.json` — gate script output;
- `mongo_writes.md` — human summary of §24.10 checks;
- `acceptance.md` — pass/fail list for §24.12.

## 25. Open-Questions Triage

| Question | Triage | Resolution-or-recommendation |
|----------|--------|------------------------------|
| Should the family expose `cv_assembly.timing_breakdown.{stage_name: {duration_ms, started_at, completed_at}}` so dashboards can chart per-stage latency without a Langfuse round-trip? | **Must resolve** | **Resolved — yes.** Cost is minimal; the field is written by each stage's finalizer alongside its existing `cv_assembly.<stage>` subtree. Required for the observability gate (§16.3) and the harness comparison report (§11.6). Schema: `{stage_name: {duration_ms: int, started_at: iso8601, completed_at: iso8601}}`. |
| Should we persist per-stage cost breakdown on `level-2` (in addition to per-stage cost on `cv_assembly_stage_runs` rows)? | Safe to defer | v1 aggregates cost into `cv_assembly.total_cost_usd` (§13) and leaves per-stage cost in Langfuse metadata + `cv_assembly_stage_runs`. Revisit if the dashboard needs per-stage cost rollups by job without joining the runs collection. |
| Should canary expansion be automated by a scheduled task watching gates? | Safe to defer | v1 keeps forward transitions manual (§14.3). Manual flips give clearer audit and a stronger consent boundary on cost overruns. Auto-rollback (§14.3 R*) handles the hot-fix direction; auto-advance does not. Revisit only if the manual cadence becomes a bottleneck during soak. |
| Should we adopt a separate Langfuse project for 4.3 to isolate retention pressure? | Safe to defer | v1 reuses the scout project. Session-id stability (§9) makes the separate-project case weaker; storage pressure metrics from canary will indicate whether to revisit. |
| Should the harness compare reviewer-usefulness scores across runs as a hard gate? | Safe to defer | v1 reports reviewer-usefulness in per-stage corpora only; the end-to-end harness reports structural correctness + cost. Reviewer-usefulness as a hard cross-family gate awaits a calibrated reviewer pool. |
| Should `cv_assembly.cost_history[]` cap at N entries, or grow indefinitely? | Safe to defer | v1: grow indefinitely (re-runs are rare; the field is small). Add cap if document size approaches the per-job 200KB envelope (per 4.3.7 size analysis). |
| Should the rollout-state artifact carry per-job allowlist directly, or only reference the env-var-driven allowlist? | Safe to defer | v1: artifact records the env-var snapshot at advance time (§14.4 `flag_snapshot.CV_ASSEMBLY_CANARY_ALLOWLIST`). The env var remains the operational source. Inlining the allowlist in the artifact requires a CI-side diff workflow that is out of scope. |

## 26. Primary Source Surfaces

- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`
- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.3-candidate-evidence-assembly-grading-and-publishing.md`
- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`
- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
- `plans/iteration-4.3.3-cv-pattern-selection-and-evidence-mapping.md`
- `plans/iteration-4.3.4-multi-draft-cv-assembly.md`
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.3.6-publisher-renderer-and-remote-delivery-integration.md`
- `plans/iteration-4.3.7-dossier-and-mongodb-state-contract.md`
- `src/pipeline/tracing.py` (`PreenrichTracingSession`,
  `_sanitize_langfuse_payload`, `build_session_id_for_job`)
- `src/cv_assembly/tracing.py` (new — this plan)
- `src/cv_assembly/health_probe.py` (new — this plan)
- `src/cv_assembly/cost_breaker.py` (new — this plan)
- `src/cv_assembly/cost_aggregation.py` (new — this plan)
- `src/cv_assembly/compat/projection.py` (4.3.7)
- `frontend/repositories/discovery_repository.py`
- `frontend/intel_dashboard.py`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md`
- `docs/current/missing.md`

## 27. Implementation Targets

### 27.1 New modules

- `src/cv_assembly/tracing.py` — `CvAssemblyTracingSession`,
  `PublishTracingSession`, sweeper-event emitters,
  `build_cv_assembly_session_id(level2_id)`.
- `src/cv_assembly/cost_breaker.py` — per-job and per-hour cost
  breakers; per-hour deadletter ceiling.
- `src/cv_assembly/cost_aggregation.py` — `compute_total_cost_usd
  (cv_assembly_subtree) -> (float, list[dict])` returning
  `(total, warnings)`; `record_cost_history(...)`.
- `src/cv_assembly/health_probe.py` — startup invariant probe,
  flag mutual-exclusion checker, rollout-artifact parser,
  registry surface.
- `src/cv_assembly/rollout_state.py` — `read_current_rollout_state
  () -> RolloutStateDoc`; `validate_transition(prev, next, gate_
  report)`; `write_rollback(prev_state, gate_report_ref)`.

### 27.2 New scripts

- `scripts/gate_cv_assembly_rollout.py` — single CI gate; CLI per
  §15.1; JSON output per §15.3.
- `scripts/benchmark_cv_assembly_end_to_end.py` — end-to-end
  harness runner; comparison report per §11.6.
- `scripts/smoke_cv_assembly_end_to_end.py` — VPS-friendly live
  smoke wrapper.
- `scripts/review_synthesis_rollbacks.py` — analysis tool
  (referenced by 4.3.5; lives here for cross-family runbook
  access).

### 27.3 New corpora and artifacts

- `data/eval/validation/cv_assembly_4_3_8_end_to_end/` —
  end-to-end corpus per §10.2 with at least 8 cases.
- `data/eval/validation/cv_assembly_4_3_8_end_to_end/CHANGELOG.md`
  — corpus-version migration log.
- `infra/rollout/cv_assembly/current_rollout_state.json` —
  rollout-state artifact per §14.4 (initial state `shadow`).
- `infra/cron/cv-assembly-rollout-gate.cron` — hourly gate-script
  cron (optional, off by default).

### 27.4 Infrastructure

- `infra/scripts/verify-cv-assembly-cutover.sh` — cross-family
  cutover verifier.
- `infra/scripts/verify-publish-cutover.sh` — publisher-specific
  cutover verifier (4.3.6 reference; 4.3.8 ensures it is wired
  into the umbrella).
- `infra/systemd/scout-cv-assembly-worker@.service` and
  `scout-publish-worker@.service` — installed and documented.

### 27.5 Tests

- `tests/unit/cv_assembly/test_gate_script.py`
- `tests/unit/cv_assembly/test_gate_script_json_contract.py`
- `tests/unit/cv_assembly/test_gate_script_idempotence.py`
- `tests/unit/cv_assembly/test_rollout_state_machine.py`
- `tests/unit/cv_assembly/test_cost_aggregation.py`
- `tests/unit/cv_assembly/test_session_lifetime.py`
- `tests/unit/cv_assembly/test_end_to_end_harness_contract.py`
- `tests/unit/cv_assembly/test_frozen_fixture_reproducibility.py`
- `tests/unit/cv_assembly/test_runbook_mapping.py`
- `tests/unit/cv_assembly/test_tracing_metadata_completeness.py`
- `tests/unit/cv_assembly/test_no_raw_langfuse_client.py`

### 27.6 Documentation

- `docs/current/architecture.md` — 4.3 lane section, including
  rollout state machine and cost aggregation rule.
- `docs/current/cv-generation-guide.md` — references to 4.3.2
  header blueprint, 4.3.5 grader rubric, 4.3.7 projection map.
- `docs/current/operational-development-manual.md` — runbook
  scenarios per §17, owner-role mappings, escalation paths.
- `docs/current/missing.md` — migration log entries per AGENTS.md.

## 28. Definition Of Done

Iteration 4.3.8 is done when:

- the canonical Langfuse taxonomy (§8.2) is stable across the
  family and asserted by `test_tracing_metadata_completeness`;
- the session-id rule (§9) is asserted by
  `test_session_lifetime`;
- every per-stage corpus is frozen with a `baseline_report.json`,
  and the end-to-end corpus has its 8 cases committed;
- `scripts/gate_cv_assembly_rollout.py` is implemented per §15
  (CLI, exit codes, JSON output, mutation policy) and asserted by
  its tests;
- the rollout state machine (§14) is implemented, with a parseable
  `current_rollout_state.json` and a passing
  `test_rollout_state_machine`;
- `cv_assembly.total_cost_usd` is written by `finalize_published`
  per §13 and asserted by `test_cost_aggregation`;
- per-job and per-hour cost breakers are wired in and asserted by
  `test_cost_aggregation`;
- the operator runbook (§17) covers every 4.3 failure mode with
  `owner_role`, `escalation_path`, and `acceptable_recovery_time`,
  and `test_runbook_mapping` passes;
- the production-readiness gates (§16) all pass on a real VPS
  canary;
- the family can be advanced to `default_on` after a 72h soak
  with zero gate failures and zero compatibility regressions.

That is the correct production-ready boundary for iteration 4.3 as
a whole.
