# Iteration 4 Plan: Stage-Level Preenrich DAG To `cv_ready` And Infra Consolidation

Author: Codex planning pass on 2026-04-19  
Parent plans:
- `plans/runnerless-vps-mongo-skill-pipeline.md`
- `plans/iteration-3-mongo-native-selector-family.md`
- `plans/scout-pre-enrichment-skills-plan.md`

Status: supersedes the earlier iteration-4 draft that bundled CV/review/publish into the same slice

## 0. Objective

Iteration 4 changes the preenrich lane from a single lease-owned job worker into a true stage-level queued DAG with independent control per stage, and stops the production boundary at `cv_ready`.

By the end of iteration 4, the primary downstream path must be:

```text
native search
  -> native scrape
  -> native selector family
  -> level-2.lifecycle=selected
  -> work_items(preenrich.jd_structure)
  -> work_items(preenrich.jd_extraction)
  -> work_items(preenrich.ai_classification)
  -> work_items(preenrich.pain_points)
  -> work_items(preenrich.annotations)
  -> work_items(preenrich.persona)
  -> work_items(preenrich.company_research)
  -> work_items(preenrich.role_research)
  -> level-2.lifecycle=cv_ready
```

This iteration is the first fully queue-controlled downstream lane and the foundation for adding more preenrich stages later without another orchestration rewrite.

## 0.1 What Changed From The Previous Draft

The previous draft optimized for the fastest path to full downstream runnerless execution by keeping preenrich as one lane and moving CV/review/publish in the same iteration.

This revised plan matches the clarified priority instead:

- maximum stage-level queue control now
- deploy the new preenrich DAG in production this iteration
- make the terminal state of the iteration `cv_ready`
- defer native CV generation, native review, and native publish to later iterations
- design preenrich so additional stages can be added safely later

That is a different iteration shape and this file should be treated as the new source of truth.

## 0.2 Production Boundary For Iteration 4

Iteration 4 is complete only when this boundary is true in production:

- no selected job requires the old monolithic preenrich worker loop to reach preenrich completion
- each preenrich stage is represented by its own Mongo work item type
- each preenrich stage can be paused, resumed, scaled, and observed independently
- the terminal lifecycle written by the native preenrich DAG is `cv_ready`
- no Redis outbox or runner handoff exists in the active post-selector path
- operators can determine which exact stage a job is blocked in
- Langfuse shows stage-by-stage traces with a stable naming scheme

This iteration is not done just because the stages run. It is done only when the stage-queue model is the authoritative production path.

---

## 1. Scope

### In Scope

- replace the current one-worker preenrich orchestration boundary with stage-level Mongo work items
- keep all 8 existing preenrich stages as independent queue-owned stages
- define the stage DAG, dependency rules, idempotency keys, and retry rules
- add stage-level worker deployment on the VPS via `systemd`
- transition preenrich completion to `lifecycle="cv_ready"`
- add operator UI and Langfuse visibility for every preenrich stage
- add the infra repo structure required to support Docker infra and host workers cleanly
- define retention and cleanup policy for Langfuse on a single VPS

### Explicitly Out Of Scope

- native CV generation worker
- native CV review worker
- native publish worker
- redesigning the content logic of the existing 8 stages
- changing selector ownership or pre-selector lanes
- replacing `level-2`

### Deferred To Iteration 5+

- `cv.generate`
- `cv.review`
- `publish.upload`
- any new preenrich stages beyond the initial 8, though iteration 4 must make them easy to add

---

## 2. Current-State Reality And Risks

## 2.1 Current Preenrich Implementation

Today:

- `src/preenrich/lease.py` claims entire jobs from `level-2` by lifecycle
- `src/preenrich/worker.py` runs the whole stage sequence inside one claim
- `src/preenrich/dispatcher.py` persists per-stage outputs, but orchestration is still intra-process
- success currently lands in `lifecycle="ready"`
- `src/preenrich/outbox.py` still reflects the abandoned Redis + runner model

This means the current code has stage persistence, but not stage-level queue control.

## 2.2 Why The Current Model Is Not Good Enough

The current model is too coarse for the desired future:

- you cannot independently pause `company_research` while leaving earlier stages active
- you cannot scale `pain_points` separately from `jd_extraction`
- you cannot insert a new stage between existing stages cleanly without editing a monolithic sequence
- you cannot see stage queue depth directly in Mongo
- you cannot deadletter one stage independently while preserving downstream clarity

## 2.3 Key Migration Hazards

The stage-level rewrite introduces new risks that the plan must address explicitly:

- duplicate next-stage enqueue after a stage succeeds
- two workers claiming the same stage work item
- stale stage outputs surviving a changed JD snapshot
- partial DAG progress when a later stage fails
- inconsistent terminal lifecycle when all stages are complete but `cv_ready` is not written
- mixed historical states: `selected`, `preenriching`, `ready`, `ready_for_cv`, `queued`, `running`, `stale`, `failed`, and new `cv_ready`
- lingering old preenrich worker or outbox still processing in parallel with the new stage DAG
- stranded docs in `lifecycle in {ready,queued,running}` when the Redis outbox is disabled mid-flight
- worker or process crash after stage output persist but before downstream enqueue (partial step two-phase)
- stage lease held by dead worker, no sweeper, backlog stalls silently
- stage-level prerequisite violated by manual insert / retry after snapshot change
- two concurrent last-stage completions both fighting over `cv_ready` finalization

## 2.4 Divergences From Prior Plans That Must Be Reconciled

The following concrete divergences exist between the parent plans and the live code. Iteration 4 must reconcile them explicitly, not implicitly:

| Topic | Parent runnerless plan | scout-preenrich plan | Current code | Iteration 4 decision |
|-------|------------------------|----------------------|--------------|----------------------|
| Authoritative collection | `jobs` | `level-2` | `level-2` | **`level-2` remains authoritative for iteration 4.** Migration to `jobs` is out of scope. |
| Preenrich lease surface | per-stage `work_items` lease | level-2 doc lease (`lease_owner`, `lease_expires_at` on level-2) | level-2 doc lease | **Per-stage `work_items` lease.** The level-2 doc lease is retired. `lifecycle="preenriching"` is derived state, not a lease. |
| Stage terminal failure state | `deadletter` | `failed_terminal` | `failed_terminal` | Canonical new value is `deadletter`. `failed_terminal` is accepted as a read-time alias until migration completes. |
| Terminal success lifecycle | `cv_ready` | `ready` | `ready` (then `queued` via Redis outbox) | **`cv_ready`** is the only new writer value. `ready`, `queued`, `running`, `ready_for_cv` are read-compat only. |
| `attempt_token` composition | not defined | `sha256(job_id\|stage\|jd_checksum\|prompt_version\|attempt_number)` (excludes provider/model) | matches scout-preenrich | Preserved verbatim. Provider/model must not enter the token. |
| Handoff from selector | `work_items(preenrich.*)` | level-2 lifecycle poll | level-2 lifecycle poll (`lifecycle="selected"` + `selected_at`) | Selector write stays as-is. A separate root-enqueuer reads `selected` + `orchestration!="dag"` and inserts the root `work_items(preenrich.jd_structure)`. |
| Selector handoff flag | n/a | n/a | `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle` | Unchanged. Iteration 4 does not fork this flag. |

---

## 3. Target Architecture

## 3.1 Control Plane

For iteration 4:

- Mongo = truth for stage state, leases, retries, dependencies, and queue control
- host-side `systemd` workers = execution
- Langfuse = tracing only
- Docker = infra only, not stage execution

## 3.2 Orchestration Rule

Preenrich is no longer orchestrated by one worker deciding the next in-memory stage.

Instead:

1. selector writes `level-2.lifecycle="selected"`
2. a scheduler or enqueue hook creates the root stage work item
3. each stage worker claims exactly one stage task
4. the stage writes its durable output and stage completion record atomically
5. the orchestration layer enqueues eligible downstream stages exactly once
6. when the DAG’s required terminal conditions are met, the job becomes `cv_ready`

## 3.3 Worker Model

Iteration 4 should use one codebase with stage allowlists, but stage-specific deploy control.

Recommended deploy pattern:

- `scout-preenrich-worker@jd_structure.service`
- `scout-preenrich-worker@jd_extraction.service`
- `scout-preenrich-worker@ai_classification.service`
- `scout-preenrich-worker@pain_points.service`
- `scout-preenrich-worker@annotations.service`
- `scout-preenrich-worker@persona.service`
- `scout-preenrich-worker@company_research.service`
- `scout-preenrich-worker@role_research.service`

Each instance runs the same Python entrypoint with:

- `PREENRICH_STAGE_ALLOWLIST=<stage_name>`
- common Mongo/trace config
- independent resource limits (`MemoryMax`, `CPUQuota`, `Restart=on-failure`, `RestartSec=5`, `LimitNOFILE=4096`)
- `ExecStopPost` hook that releases held leases (best effort)

This gives you maximum operational control without duplicating worker code.

## 3.4 Auxiliary Host Processes

In addition to the 8 stage workers, iteration 4 introduces these small host processes (same venv, small footprint):

- `preenrich-root-enqueuer.service` (+ `.timer`, every 30s) — implements §6.1
- `preenrich-next-stage-sweeper.service` (+ `.timer`, every 30s) — implements §6.2 Phase B for any `pending_next_stages` entries missed by inline enqueue
- `preenrich-stage-sweeper.service` (+ `.timer`, every 60s) — implements §4.4.3 dead-worker recovery
- `preenrich-cv-ready-sweeper.service` (+ `.timer`, every 60s) — implements §6.5 sweeper finalizer
- `preenrich-snapshot-invalidator.service` (on-demand or + `.timer` every 5 min) — implements §6.6 on docs whose `jd_checksum` drifted
- `preenrich-stranded-outbox-drainer.service` (one-shot) — implements §12.5 migration

All sweepers must be safe to run concurrently with workers. All sweepers must be safe to run 0× (workers handle the happy path inline) and N× (idempotent CAS writes).

---

## 4. Canonical Lifecycle And State Contract

## 4.1 Lifecycle Contract

Iteration 4 standardizes the downstream lifecycle states as:

- `selected`
- `preenriching`
- `cv_ready`
- `failed`
- `deadletter`

During this iteration, `preenriching` means:

- at least one stage is queued, leased, or running
- the job has not yet satisfied the terminal DAG completion rule

`cv_ready` means:

- all required stage outputs for the current DAG version are complete
- no required stage is pending, leased, retry_pending, failed, or deadletter
- the job is ready for a later `cv.generate` lane

## 4.2 Compatibility Rule For Historical States

During migration, the system must tolerate every historical value currently observed on `level-2.lifecycle`:

- `selected`
- `preenriching`
- `ready`
- `ready_for_cv` (present in readers like `ACTIVE_LIFECYCLES`; possibly never written by current code but must be treated as a no-op downstream state)
- `queued`
- `running`
- `stale`
- `failed`

Rules:

- new writers must write `cv_ready` only
- the legacy `outbox.py` writer that flips `ready → queued` is disabled before any DAG writer emits `cv_ready` into production
- historical `ready`, `ready_for_cv`, `queued`, `running` docs must be backfilled before the old monolithic worker is stopped — see §12.5 backfill procedure
- dashboards must show these transient historical states under a dedicated "legacy" bucket, not under `preenriching`, so operators see the real distribution

## 4.2.1 State Machine (Canonical)

```text
            (selector)
                |
                v
            selected  -- orchestration="dag" --------+
                |                                    |
   [root-enqueuer inserts preenrich.jd_structure]    |
                |                                    |
                v                                    |
           preenriching  <--- any stage active       |
                |                                    |
   (all required stages completed for current
    input_snapshot_id, none leased/pending/failed)   |
                |                                    |
                v                                    |
             cv_ready                                |
                                                     |
   any stage deadlettered + job_fail_policy=hard --> failed
   exhausted retries on unrecoverable class --------> deadletter
   snapshot change during flight --------> stale work cancelled, root re-enqueue
```

## 4.3 Required State Surfaces On `level-2`

Each preenriched job must expose:

- `lifecycle`
- `selected_at`
- `pre_enrichment.schema_version`
- `pre_enrichment.dag_version`
- `pre_enrichment.input_snapshot_id`
- `pre_enrichment.jd_checksum`
- `pre_enrichment.company_checksum`
- `pre_enrichment.stage_states`
- `pre_enrichment.cv_ready_at` (set exactly once — CAS guarded)
- `pre_enrichment.last_error`
- `pre_enrichment.deadletter_reason`
- `pre_enrichment.orchestration` (discriminator: `"dag"` or `"legacy"`; read by both legacy and new claim paths)
- `pre_enrichment.pending_next_stages` (stage-outbox buffer for atomic enqueue, see §6.2)
- `observability.langfuse_session_id` (format: `job:<level2_object_id>`)

The legacy per-job lease fields (`lease_owner`, `lease_expires_at`, `lease_heartbeat_at`) on the level-2 doc are retired for the DAG path. They may remain on historical docs but must not be read or written by the DAG codepaths.

Canonical `stage_states.<stage>` shape:

```json
{
  "jd_structure": {
    "status": "pending|leased|completed|retry_pending|failed|deadletter|cancelled|skipped",
    "attempt_count": 1,
    "lease_owner": "worker-id",
    "lease_expires_at": "ISODate",
    "started_at": "ISODate",
    "completed_at": "ISODate",
    "input_snapshot_id": "sha256:...",
    "attempt_token": "sha256(...)",
    "jd_checksum_at_completion": "sha256:...",
    "provider": "claude|codex|...",
    "model": "...",
    "prompt_version": "v3",
    "output_ref": { "path": "pre_enrichment.jd_structure.output" },
    "last_error": { "class": "...", "message": "...", "at": "ISODate" },
    "work_item_id": "ObjectId",
    "tokens_input": 0,
    "tokens_output": 0,
    "cost_usd": 0.0
  }
}
```

Enum reconciliation rule:

- New writers use `deadletter` (never `failed_terminal`).
- Readers and dashboards must treat pre-existing `failed_terminal` as equivalent to `deadletter` until the backfill (§12.5) clears it.
- `cancelled` is reserved for snapshot-invalidation (§6.6).
- `skipped` is reserved for stages that a future registry may mark non-applicable by role.

`attempt_token` composition is fixed: `sha256(job_id|stage|jd_checksum|prompt_version|attempt_number)`. Provider and model must not enter the token (this is a hard rule inherited from scout-preenrich to prevent Claude/Codex fallback from duplicating writes).

## 4.4 Required Queue Surfaces

Recommended `work_items.task_type` values:

- `preenrich.jd_structure`
- `preenrich.jd_extraction`
- `preenrich.ai_classification`
- `preenrich.pain_points`
- `preenrich.annotations`
- `preenrich.persona`
- `preenrich.company_research`
- `preenrich.role_research`

Each work item must include:

- `task_type`
- `lane="preenrich"`
- `subject_type="job"`
- `subject_id` (string form of the level-2 ObjectId)
- `status` (`pending|leased|done|failed|deadletter|cancelled`, plus logical `retry_pending` represented as `pending` with future `available_at`)
- `available_at`
- `priority`
- `lease_owner`
- `lease_expires_at`
- `attempt_count`
- `max_attempts`
- `idempotency_key`
- `correlation_id` (= `langfuse_session_id` = `job:<level2_id>`)
- `payload` (must contain `input_snapshot_id`, `jd_checksum`, `company_checksum`, `dag_version`, `stage_name`)
- `result_ref`
- `created_at`
- `updated_at`

### 4.4.1 Idempotency key format (pinned)

```
preenrich.<stage>:<level2_id>:<input_snapshot_id>
```

Single unique index on `work_items.idempotency_key`. Duplicate insert attempts (root-enqueue retry, snapshot-change re-enqueue, sweeper re-enqueue) are suppressed cleanly by `E11000`. If the snapshot changes mid-flight, the new stage work item has a different `idempotency_key` and does not collide.

### 4.4.2 Per-stage `max_attempts` defaults

| Stage | max_attempts | Rationale |
|-------|--------------|-----------|
| jd_structure | 3 | Deterministic LLM parse |
| jd_extraction | 3 | Deterministic LLM parse |
| ai_classification | 3 | Small Haiku call |
| pain_points | 3 | LLM reasoning |
| annotations | 3 | LLM reasoning |
| persona | 3 | LLM reasoning |
| company_research | 5 | Web/search transient failures |
| role_research | 5 | Web/search transient failures |

Retry backoff (per attempt): `30s, 2min, 10min, 30min, 60min`, clamped to `max_attempts`. Terminal after exhaustion = `deadletter`.

### 4.4.3 Stage lease + heartbeat rules

- Default lease: `PREENRICH_STAGE_LEASE_SECONDS=600` (10 minutes)
- Heartbeat cadence: `PREENRICH_STAGE_HEARTBEAT_SECONDS=60`
- Heartbeat renews `work_items.lease_expires_at` AND `level-2.pre_enrichment.stage_states.<stage>.lease_expires_at`
- Dead-worker sweeper (`preenrich-stage-sweeper.timer`, every 60s) finds `status="leased" AND lease_expires_at < now`, flips back to `status="pending"`, increments `attempt_count`, pushes `available_at` by backoff, clears `lease_owner` on both surfaces.

## 4.5 Required Indexes

Iteration 4 is not production-ready without the indexes for the hot paths it introduces.

Required indexes:

- `level-2 { lifecycle: 1, "pre_enrichment.orchestration": 1, selected_at: 1 }` (root-enqueue scan)
- `level-2 { "pre_enrichment.cv_ready_at": 1 }`
- `level-2 { "pre_enrichment.input_snapshot_id": 1 }`
- `level-2 { "pre_enrichment.pending_next_stages.idempotency_key": 1 }` (stage-outbox sweeper)
- `work_items { status: 1, task_type: 1, available_at: 1, priority: -1 }` (claim)
- `work_items { lane: 1, status: 1, lease_expires_at: 1 }` (dead-worker sweeper)
- `work_items { idempotency_key: 1 }` — **unique**
- `work_items { subject_id: 1, task_type: 1, status: 1 }`
- `work_items { status: 1, updated_at: 1 }` partial TTL for `status in {done, deadletter, cancelled}` with `expireAfterSeconds = 30 days` (growth guardrail)
- `preenrich_stage_runs { started_at: 1, status: 1 }`
- `preenrich_stage_runs { job_id: 1, stage: 1, started_at: -1 }`
- `preenrich_job_runs { started_at: 1, status: 1 }`

All indexes ship in the same slice as the code that reads them. Missing indexes block rollout gates in §14.

---

## 5. Stage DAG Contract

## 5.1 Initial Stage Set

The initial queue-owned stages are the current 8:

1. `jd_structure`
2. `jd_extraction`
3. `ai_classification`
4. `pain_points`
5. `annotations`
6. `persona`
7. `company_research`
8. `role_research`

Reserved future stages (registry-ready, not shipped in iteration 4):

- `fit_signal` (from scout-preenrich-skills-plan)
- `competency_eval` (see `data/master-cv/projects/lantern_skills.json` integration)

## 5.2 DAG Rule

Iteration 4 should preserve the current effective topological order first, then allow future insertion of more stages without rewriting orchestration.

Represent each stage with registry metadata:

- `name`
- `task_type`
- `prerequisites`
- `produces_fields`
- `required_for_cv_ready`
- `max_attempts`
- `default_priority`

## 5.3 Recommended Initial Dependency Graph

Risk-averse starting graph:

- `jd_structure` -> `jd_extraction`
- `jd_extraction` -> `ai_classification`
- `ai_classification` -> `pain_points`
- `pain_points` -> `annotations`
- `annotations` -> `persona`
- `persona` -> `company_research`
- `company_research` -> `role_research`

This preserves current behavior first.

Important:

- use a DAG registry even if the first live graph is mostly linear
- do not hardcode the sequence only in worker code
- future stages must be addable by registry change plus implementation, not by rewriting the whole orchestrator

## 5.4 Future-Stage Extensibility Rule

To add a future stage later, the architecture must support:

- adding a registry entry
- defining prerequisites
- defining whether it gates `cv_ready`
- defining worker allowlist deployment
- defining UI visibility and Langfuse step names

No iteration-4 design choice should make that harder.

---

## 6. Orchestration And Idempotency Rules

## 6.0 Dual-Path Ownership Guard

The legacy `src/preenrich/lease.py::claim_one` currently claims any `level-2` doc with `lifecycle in {selected, stale}`. The new DAG root-enqueuer reads the same set. Without a discriminator, both paths will race on every newly selected doc.

Ownership marker: `level-2.pre_enrichment.orchestration`.

- Root-enqueuer CAS: `{lifecycle:"selected", "pre_enrichment.orchestration": {$in: [null, "legacy"]}} → $set {"pre_enrichment.orchestration":"dag", lifecycle:"preenriching", ...}` gated by `PREENRICH_STAGE_DAG_ENABLED=true`.
- Legacy `claim_one` must be patched to filter `"pre_enrichment.orchestration": {$ne: "dag"}` *as long as it runs* (i.e. during cutover). After the legacy path is disabled, the marker remains as an audit field.
- Exactly one orchestration path owns any given snapshot. Rollback re-tags `orchestration="legacy"` only on docs that have not yet produced DAG stage completions.

## 6.1 Root Enqueue Rule

Triggered by a dedicated `preenrich-root-enqueuer.timer` (every 30s) — not by the selector worker. Rationale: keeps the selector blast-radius unchanged and lets root enqueue be paused independently.

Procedure (per candidate level-2 doc):

1. CAS ownership to `"dag"` (see §6.0). Skip if already owned.
2. Compute `input_snapshot_id = sha256(jd_checksum || company_checksum || dag_version)`.
3. `$set`:
   - `lifecycle="preenriching"`
   - `pre_enrichment.schema_version`, `pre_enrichment.dag_version`
   - `pre_enrichment.input_snapshot_id`, `pre_enrichment.jd_checksum`, `pre_enrichment.company_checksum`
   - `observability.langfuse_session_id = "job:<level2_id>"`
   - initialize `stage_states.jd_structure.status="pending"` and every other registered stage to `status="pending"`
4. Insert `work_items(preenrich.jd_structure)` with `idempotency_key=preenrich.jd_structure:<id>:<snapshot>`. `E11000` is a no-op success.
5. Emit Langfuse span `scout.preenrich.enqueue_root`.

Idempotent by construction: the CAS and the unique `idempotency_key` guarantee at-most-once effective behavior across retries.

## 6.2 Stage Completion Protocol (Atomic Two-Surface Update)

**Problem.** A stage must (a) write its output + stage_states on level-2, and (b) insert one or more downstream `work_items`. These are two collections. Without a named mechanism this is the largest correctness risk.

**Mechanism: stage-outbox pattern, single-writer.**

Phase A — single level-2 update, one Mongo write, deterministic:

```text
findOneAndUpdate(
  { _id: level2_id,
    "pre_enrichment.stage_states.<stage>.lease_owner": worker_id,
    "pre_enrichment.stage_states.<stage>.attempt_token": { $ne: token } },
  { $set: {
      "pre_enrichment.<stage>.output": <output>,
      "pre_enrichment.stage_states.<stage>.status": "completed",
      "pre_enrichment.stage_states.<stage>.completed_at": now,
      "pre_enrichment.stage_states.<stage>.attempt_token": token,
      "pre_enrichment.stage_states.<stage>.jd_checksum_at_completion": jd_checksum,
      "pre_enrichment.stage_states.<stage>.input_snapshot_id": snapshot },
    $push: {
      "pre_enrichment.pending_next_stages": { $each: [
        { idempotency_key: "preenrich.<next>:<id>:<snapshot>",
          task_type: "preenrich.<next>",
          payload: {...},
          enqueued_at: null } ] } } }
)
```

Phase B — a small, idempotent `enqueue-next-stages` sweeper (can be inline call after Phase A AND a separate timer):

- scans `level-2` docs with any entry in `pending_next_stages` where `enqueued_at==null`
- for each, attempts `work_items.insert_one` (unique key suppresses duplicates)
- on success or `E11000`, `$set pending_next_stages.$.enqueued_at=now`

Consequences:

- Crash between A and B: next run of the sweeper completes the enqueue. No lost downstream.
- Crash after partial B: `E11000` on retry. No duplicate downstream.
- Two workers cannot pass Phase A concurrently because the `lease_owner` + `attempt_token` filter is mutually exclusive.

Phase A and B both run under the Langfuse span `scout.preenrich.enqueue_next`.

## 6.3 Stage Retry Rule

Retryable failures:

- worker sets `stage_states.<stage>.status="pending"` (logical `retry_pending`) with `attempt_count+=1`, pushed `available_at`, `last_error` captured
- work item is not deleted — `status="pending"` with future `available_at`
- the stage's `attempt_token` is *not* rotated until a new real attempt starts (prevents duplicate completion writes)

Terminal failures (class unrecoverable OR `attempt_count >= max_attempts`):

- `stage_states.<stage>.status="deadletter"`, `work_items.status="deadletter"`, `last_error` populated, `deadletter_reason` propagated to level-2
- if the stage has `required_for_cv_ready=true`, job lifecycle transitions to `failed` (soft) or `deadletter` (hard) per `job_fail_policy` in the registry (default: `failed`)

## 6.4 Snapshot / Checksum Rule

Every stage work item `payload` carries `input_snapshot_id`, `jd_checksum`, `company_checksum`. On claim, the worker must re-compute the current snapshot from level-2 and compare:

- mismatch → worker marks work item `status="cancelled"`, releases lease, logs `scout.preenrich.retry` with reason `snapshot_changed`. Does not run the stage.

## 6.5 `cv_ready` Finalization Rule

Finalization is attempted in two places to eliminate the last-stage race:

- **Inline.** After §6.2 Phase A on any required stage, the worker calls the finalizer.
- **Sweeper.** `preenrich-cv-ready-sweeper.timer` runs every 60s, scans `lifecycle="preenriching"` docs with no pending stage work, and calls the finalizer.

Finalizer CAS:

```text
findOneAndUpdate(
  { _id, lifecycle: "preenriching",
    "pre_enrichment.cv_ready_at": { $exists: false },
    "pre_enrichment.input_snapshot_id": current_snapshot,
    <for each required stage>
       "pre_enrichment.stage_states.<stage>.status": "completed",
       "pre_enrichment.stage_states.<stage>.input_snapshot_id": current_snapshot,
    "pre_enrichment.pending_next_stages": { $not: { $elemMatch: { enqueued_at: null } } } },
  { $set: { lifecycle: "cv_ready", "pre_enrichment.cv_ready_at": now } }
)
```

- Unique write by construction (`cv_ready_at` must not exist).
- Safe against duplicate sweeper calls.
- Langfuse span: `scout.preenrich.finalize_cv_ready`.

## 6.6 Snapshot Invalidation Algorithm

Triggered when any upstream path detects a JD or company change on a `preenriching` doc:

1. Compute `new_snapshot_id`.
2. On level-2: `$set pre_enrichment.input_snapshot_id=new; pre_enrichment.jd_checksum=new; reset any stage_states.<stage> whose input_snapshot_id != new to status="cancelled"` (preserve completed outputs as `output_ref` but drop status).
3. On work_items: `updateMany({subject_id, lane:"preenrich", "payload.input_snapshot_id": {$ne: new}, status: {$in: ["pending","leased"]}}, $set {status:"cancelled", cancelled_reason:"snapshot_changed"})`.
4. Re-run root-enqueue step §6.1 (new idempotency keys by construction).

Runs under span `scout.preenrich.retry` with `reason=snapshot_changed`. Rate-limited per job (`PREENRICH_SNAPSHOT_REVALIDATE_WINDOW_SECONDS=120`) to avoid flapping.

## 6.7 Prerequisite Enforcement At Claim

On work item claim, before executing the stage body, the worker MUST assert:

- every prerequisite in the registry for this stage has `stage_states.<prereq>.status=="completed"`
- every prerequisite's `input_snapshot_id` equals the current snapshot
- the payload's `input_snapshot_id` equals the current level-2 snapshot

Failure path: release lease, push `available_at` by the retry backoff, emit `scout.preenrich.retry` with `reason=prerequisite_not_ready`. Do not execute the stage body. This prevents out-of-order execution from manual inserts or sweeper races.

## 6.8 Idempotency + attempt_token Rules

- `work_items.idempotency_key` format: see §4.4.1.
- `stage_states.<stage>.attempt_token` format: `sha256(job_id|stage|jd_checksum|prompt_version|attempt_number)` — provider/model NOT included. Completion `$set` is guarded by `attempt_token != $current_token` to prevent fallback-provider double-write.
- Root-enqueue is guarded by the `pre_enrichment.orchestration` CAS.
- cv_ready is guarded by the `cv_ready_at not exists` CAS.

---

## 7. Worker Deployment Model

## 7.1 Systemd Units

Iteration 4 should deploy one template unit and instantiate it per stage.

Suggested unit naming:

- `infra/systemd/scout-preenrich-worker@.service`

Suggested instance names:

- `scout-preenrich-worker@jd_structure.service`
- `scout-preenrich-worker@jd_extraction.service`
- `scout-preenrich-worker@ai_classification.service`
- `scout-preenrich-worker@pain_points.service`
- `scout-preenrich-worker@annotations.service`
- `scout-preenrich-worker@persona.service`
- `scout-preenrich-worker@company_research.service`
- `scout-preenrich-worker@role_research.service`

## 7.2 Scaling Rules

Stage-level queue control means you can scale stages independently.

Recommended initial production scale:

- one instance per stage
- only increase workers on the actual bottleneck stage after queue depth is observed

Do not over-scale all stages uniformly on a single VPS.

## 7.3 Pause And Resume Rules

The design must allow:

- stopping `company_research` without stopping `jd_extraction`
- draining one stage backlog while pausing another
- rolling a single stage forward or back

That is one of the main reasons for the stage-level model.

## 7.4 Notification Consolidation

The current `src/preenrich/worker.py` emits Telegram tick summaries. Running 8 independent stage workers must NOT 8× the notification volume.

Rule:

- Stage workers emit structured logs only (no Telegram)
- A single `preenrich-heartbeat.service` (timer every 10 min) aggregates queue depth, completions, deadletters across all stages and emits one Telegram message
- Deadletter transitions emit a Telegram alert from the stage worker itself (capped at `PREENRICH_ALERT_MAX_PER_HOUR=10` via an in-memory token bucket or Mongo counter)

---

## 8. Operator UI Requirements

Iteration 4 is not production-ready without first-class stage observability.

Required dashboard surfaces:

- stage backlog cards:
  - pending
  - leased
  - retry_pending
  - failed
  - deadletter
- per-stage throughput in the last 24 hours
- per-stage median and p95 runtime
- per-job stage matrix showing all 8 stages
- filter for:
  - selected
  - preenriching
  - cv_ready
  - failed
  - deadletter
- details panel with:
  - input snapshot id
  - current stage statuses
  - last error
  - linked work items
  - Langfuse trace/session ids

Semantic honesty rules:

- `preenriching` does not mean "almost done"
- `completed` for one stage does not imply `cv_ready`
- `cv_ready` means the full required DAG is complete for the current snapshot only
- dashboard must clearly separate *logical* stage status (`pending|leased|completed|retry_pending|failed|deadletter|cancelled`) from *lifecycle* status on the job

## 8.1 Concrete Implementation Targets

The following files must change (or be created) to satisfy §8. This is the deployment surface for the dashboard work:

- `frontend/repositories/discovery_repository.py`
  - new `preenrich_stage_snapshot()` returning per-stage counts from `work_items` (status×task_type matrix) and per-stage runtime percentiles from `preenrich_stage_runs`
  - new `preenrich_job_stage_matrix(level2_id)` returning the 8-stage matrix for one job
  - extend existing `pipeline_heartbeat` to add Iteration 4 card
- `frontend/intel_dashboard.py`
  - new route `/discovery/preenrich` — stage backlog cards, throughput, p50/p95
  - new route `/discovery/preenrich/<level2_id>` — stage matrix detail
  - extend `/discovery/results` lifecycle filter to include `preenriching`, `cv_ready`, `failed`, `deadletter`
  - extend `_parse_discovery_filters` with `stage_status` and `stage_name` filters
- `frontend/templates/` — new partials for the stage matrix and stage card grid

## 8.2 Heartbeat Card

Extend `get_pipeline_heartbeat()` with a fourth card "Iteration 4 preenrich DAG" showing:

- primary: `cv_ready` produced in last 24h
- secondary: total stage tasks in `pending + leased`, deadletter count
- state color: green if all 8 stages have `pending<50` and `deadletter==0`; yellow if any stage has `pending∈[50,200]` or `deadletter∈[1,5]`; red otherwise
- reason string: the specific stage driving yellow/red

---

## 9. Langfuse Logging And Trace Framework

## 9.1 Naming Rules

Keep the existing `scout.` prefix and make step names stable across queue, logs, and UI.

Naming convention:

- root run trace: `scout.<lane>.run`
- job/stage span: `scout.<lane>.job`
- stage execution span: `scout.<lane>.<stage_name>`
- orchestration span: `scout.<lane>.<orchestration_step>`

## 9.2 Canonical Preenrich Step Names

- `scout.preenrich.run`
- `scout.preenrich.job`
- `scout.preenrich.enqueue_root`
- `scout.preenrich.claim`
- `scout.preenrich.jd_structure`
- `scout.preenrich.jd_extraction`
- `scout.preenrich.ai_classification`
- `scout.preenrich.pain_points`
- `scout.preenrich.annotations`
- `scout.preenrich.persona`
- `scout.preenrich.company_research`
- `scout.preenrich.role_research`
- `scout.preenrich.enqueue_next`
- `scout.preenrich.finalize_cv_ready`
- `scout.preenrich.retry`
- `scout.preenrich.deadletter`

## 9.3 Required Correlation Fields

Each trace/span must carry:

- `job_id`
- `level2_job_id`
- `correlation_id` (= `langfuse_session_id`)
- `langfuse_session_id` — **format pinned: `job:<level2_object_id>`** so all lanes (search, scrape, selector, preenrich, future cv.*) aggregate into one session per job
- `run_id`
- `worker_id` (`hostname-pid-uuid`, same convention as `lease.py`)
- `task_type`
- `stage_name`
- `attempt_count`
- `attempt_token`
- `input_snapshot_id`
- `jd_checksum`
- `lifecycle_before`
- `lifecycle_after`
- `work_item_id`

## 9.4 Overall Pipeline Taxonomy

Iteration 4 must also define the stable top-level step names for the whole pipeline so later iterations extend, not rename, them:

- `scout.search.*`
- `scout.scrape.*`
- `scout.selector.*`
- `scout.preenrich.*`
- reserved for later:
  - `scout.cv.generate.*`
  - `scout.cv.review.*`
  - `scout.publish.*`

## 9.5 Payload Discipline

To keep Langfuse volume under control:

- default to metadata, previews, checksums, and counts
- do not attach full raw JD or full stage outputs to every span
- attach full prompts only for the stage calls where prompt debugging matters materially

---

## 10. Langfuse Retention, TTL, And Storage Policy

## 10.0 Pre-Cutover Verification Step

Before relying on any built-in Langfuse retention setting, iteration 4 must execute:

1. Log into the deployed Langfuse admin UI and confirm that Project Data Retention is enabled on the deployed edition.
2. If it is NOT available on the self-hosted edition in use, fall back to §10.3 BEFORE enabling preenrich tracing in production.
3. Document the observed edition and retention capability in `docs/current/architecture.md`.

## 10.1 Official Constraints

Official Langfuse docs currently indicate:

- event data is retained indefinitely by default
- project-level retention accepts a minimum of 3 days
- data retention is documented as a self-hosted feature and also listed under Enterprise feature overview
- Docker Compose is suitable for low-scale deployments only

Sources:

- `https://langfuse.com/docs/administration/data-retention`
- `https://langfuse.com/docs/deployment/feature-overview`
- `https://langfuse.com/self-hosting`
- `https://langfuse.com/docs/administration/data-deletion`

## 10.2 Recommended TTL For This VPS

Reasonable starting policy:

- dev Langfuse project: 7 days
- canary/staging project: 14 days
- production scout project: 30 days

This is long enough to:

- debug multi-day regressions
- inspect stage retry trends
- compare queue bottlenecks over time

without letting a single-VPS container grow without bound.

## 10.3 If Built-In Retention Is Not Available In The Deployed Edition

Fallback policy:

1. isolate the scout pipeline into its own Langfuse project
2. disable unnecessary media capture
3. run a nightly cleanup job using supported deletion flows for traces older than 30 days
4. keep long-lived audit signals in Mongo:
   - stage run summaries
   - deadletter reasons
   - work-item stats
   - linked artifact refs

Do not make ad hoc direct database pruning the default plan.

## 10.4 Storage Guardrails

Iteration 4 infra must add:

- weekly Langfuse storage report
- alert when Langfuse data volume crosses 70% of allocated storage budget
- operator runbook for cleanup

---

## 11. Infra Folder Consolidation Plan

## 11.1 Target Structure

Iteration 4 should introduce:

```text
infra/
  compose/
    langfuse/
      docker-compose.yml
      .env.example
    n8n/
      docker-compose.yml
      .env.example
    legacy/
      runner/
        docker-compose.yml
  docker/
    pdf-service/
      Dockerfile
    job-ingest/
      Dockerfile
      entrypoint.sh
      crontab
    openclaw/
      Dockerfile
      openclaw-init.sh
  systemd/
    scout-preenrich-worker@.service
  env/
    scout-workers.env.example
    langfuse.env.example
    n8n.env.example
  scripts/
    deploy-langfuse.sh
    deploy-n8n.sh
    verify-preenrich-cutover.sh
    rollback-preenrich-dag.py
    backfill-preenrich-states.py
  n8n/
    cron/
    workflows/
    prompts/
```

## 11.2 Skill Code Separation Rule

Host-executed skill code is not infra.

Risk-averse path:

1. move pure deploy assets into `infra/` first
2. keep business logic paths stable during the stage-DAG cutover
3. move `n8n/skills/` code later only if path churn will not interfere with the functional rollout

Do not combine the first live stage-DAG cutover with a deep app-code move.

## 11.3 Legacy Asset Rule

Legacy runner assets should be moved out of the repo root and marked deprecated:

- root `docker-compose.runner*.yml` -> `infra/compose/legacy/runner/`
- root `Dockerfile.runner` -> `infra/docker/legacy/runner/` or archive path

They should not look active once the runnerless direction is the repo truth.

`src/preenrich/outbox.py` (Redis-based) is kept in-tree but wrapped with a hard guard that raises if imported while `PREENRICH_DISABLE_REDIS_OUTBOX=true`. After one stable release past cutover, the file moves to `src/legacy/preenrich_outbox.py` and is removed from import paths.

## 11.4 `verify-preenrich-cutover.sh` Contract

Single script that must return non-zero on any failure. It must check:

1. All 8 stage systemd units are `active`.
2. All 5 sweeper timers are `active`.
3. `work_items` has the unique index on `idempotency_key`.
4. All required indexes from §4.5 exist (queried via `listIndexes`).
5. No doc has `pre_enrichment.orchestration="dag"` while a legacy lease (`lease_owner`, `lease_expires_at`) is held by a non-DAG worker.
6. No duplicate `work_items.idempotency_key` exists.
7. No `lifecycle in {ready, queued, running}` docs remain after the outbox drain.
8. Langfuse host is reachable and project retention setting matches §10 plan.
9. At least one successful `cv_ready` has been written in the last 24h (post-canary).

Runs on the VPS via `ssh root@72.61.92.76 /root/scout-cron/infra/scripts/verify-preenrich-cutover.sh`.

---

## 12. Rollout, Canary, And Rollback

## 12.1 Rollout Order

1. ship stage registry, queue schema, and **all indexes including `work_items.idempotency_key` unique**
2. ship stage-level workers, sweepers, and ownership marker logic behind flags
3. deploy dashboard changes (can go in before flags flip — reads are backward-compatible)
4. run backfill script on historical preenrich states (§12.5)
5. drain and disable Redis outbox (§12.6)
6. flip `PREENRICH_STAGE_DAG_ENABLED=true` for a single-job canary (select by `_id` allowlist env var)
7. verify stage progression to `cv_ready` on canary; verify no duplicate work_items; verify Langfuse trace integrity
8. widen canary slice to 5%, then 25%, then 100% over at least 72h soak
9. disable old monolithic preenrich path (`PREENRICH_LEGACY_SEQUENCE_ENABLED=false`)
10. archive legacy runner compose files and Redis outbox code (§11.3)

## 12.2 Required Rollout Flags

Minimum flags and their prod-safe defaults:

| Flag | Default (pre-cutover) | Post-cutover | Notes |
|------|-----------------------|--------------|-------|
| `PREENRICH_STAGE_DAG_ENABLED` | `false` | `true` | Master switch for root-enqueuer + stage workers |
| `PREENRICH_DAG_CANARY_ALLOWLIST` | `""` | `""` (unused) | CSV of level-2 ids for single-job canary |
| `PREENRICH_DAG_CANARY_PCT` | `0` | `100` | 0–100, gates root-enqueuer probability |
| `PREENRICH_LEGACY_SEQUENCE_ENABLED` | `true` | `false` | Master switch for old monolithic worker |
| `PREENRICH_WRITE_CV_READY` | `false` | `true` | Finalizer is a no-op until this is true; paired with DAG |
| `PREENRICH_ACCEPT_READY_COMPAT` | `true` | `true` | Readers treat `ready`/`ready_for_cv`/`queued` as legacy |
| `PREENRICH_DISABLE_REDIS_OUTBOX` | `false` | `true` | Disables `outbox.py` producer + consumer |
| `PREENRICH_STAGE_ALLOWLIST` | `""` | per-unit | Set per systemd instance |
| `PREENRICH_STAGE_LEASE_SECONDS` | `600` | `600` | §4.4.3 |
| `PREENRICH_STAGE_HEARTBEAT_SECONDS` | `60` | `60` | §4.4.3 |
| `PREENRICH_SNAPSHOT_REVALIDATE_WINDOW_SECONDS` | `120` | `120` | §6.6 anti-flap |
| `PREENRICH_ALERT_MAX_PER_HOUR` | `10` | `10` | Caps per-stage deadletter Telegram alerts; aggregated heartbeat remains separate |
| `LANGFUSE_PREENRICH_TRACING_ENABLED` | `false` | `true` | Gated until §10.0 verification completes |
| `LANGFUSE_CAPTURE_FULL_PROMPTS` | `false` | `false` | Per §9.5, opt-in per stage |

Mutual-exclusion invariant (checked at startup by a small health probe):

- `PREENRICH_STAGE_DAG_ENABLED=true AND PREENRICH_LEGACY_SEQUENCE_ENABLED=true` is only allowed when `PREENRICH_DAG_CANARY_PCT < 100`. In 100% DAG mode, legacy must be off.
- `PREENRICH_DISABLE_REDIS_OUTBOX=true` must not be set while `PREENRICH_LEGACY_SEQUENCE_ENABLED=true`.

Rules:

- defaults must be safe
- legacy and DAG paths must not both own the same job silently (enforced by §6.0 ownership marker)
- rollout must be reversible without code edits

## 12.3 Ownership Rule During Cutover

For any given job snapshot, exactly one orchestration path may own preenrich:

- legacy monolithic sequence
- or stage-DAG path

Never both.

Use an explicit ownership marker or enqueue guard to prevent double-processing.

## 12.4 Rollback Rules

Rollback must support:

- stopping all stage workers
- re-enabling the legacy sequence path if necessary
- preserving already completed stage outputs
- avoiding duplicate root or next-stage enqueues

Rollback must not require deleting Mongo state.

Explicit rollback procedure:

1. `PREENRICH_STAGE_DAG_ENABLED=false` (stops root enqueuer).
2. `systemctl stop scout-preenrich-worker@*.service preenrich-*-sweeper.timer`.
3. Run `scripts/rollback-preenrich-dag.py` which:
   - flips `orchestration="dag"` → `"legacy"` ONLY on docs whose `stage_states.*.status` shows no completed stages (i.e. DAG has not yet produced durable work)
   - leaves `orchestration="dag"` on docs that have completed stages — they will complete through the sweeper tail after it is restarted
   - cancels `work_items(preenrich.*)` in `status=pending` for the rollback set
4. `PREENRICH_LEGACY_SEQUENCE_ENABLED=true`, restart `preenrich-worker.service` (legacy).
5. `PREENRICH_DISABLE_REDIS_OUTBOX=false` if Redis path was disabled.

## 12.5 Historical-State Backfill Script (`scripts/backfill-preenrich-states.py`)

Runs once before or during canary; idempotent; dry-run by default.

Actions (all scoped to `level-2`):

| From | To | Rule |
|------|----|------|
| `lifecycle="ready"` with all 8 stages completed | `lifecycle="cv_ready"`, set `pre_enrichment.cv_ready_at=max(stages.completed_at)` | Legacy success carried forward |
| `lifecycle="ready"` without full stage completeness | leave as-is; log as "legacy partial ready" | Should not occur; inspect manually |
| `lifecycle="ready_for_cv"` | `lifecycle="cv_ready"`, same `cv_ready_at` rule | Read-compat historical state |
| `lifecycle="queued"` (Redis outbox) | stage sweeper drains via §12.6 then finalizes | Do not touch lifecycle directly here |
| `lifecycle="running"` with stale `lease_expires_at` | `lifecycle="stale"` | Let new root-enqueuer restart |
| `stage_states.*.status="failed_terminal"` | `stage_states.*.status="deadletter"` | Enum alignment |
| Any `lifecycle="preenriching"` with no `pre_enrichment.orchestration` | `orchestration="legacy"` | Preserves legacy ownership for in-flight pre-cutover docs |
| Bootstrap `stage_states` missing | derive from `pre_enrichment.stages.<name>` where present (mapping `completed→completed`, `failed→failed`, `failed_terminal→deadletter`, `in_progress→pending` after lease expiry) | Gives new dashboard a truthful view |

Output: summary report at `reports/backfill-preenrich-<ts>.json` with counts per transition. Must pass a dry-run before real run.

## 12.6 Stranded Redis Outbox Drain (`preenrich-stranded-outbox-drainer.service`)

Runs once before flipping `PREENRICH_DISABLE_REDIS_OUTBOX=true` for keeps.

Procedure:

1. Stop producer (`enqueue_ready` tick): flip internal flag that makes `enqueue_ready` a no-op.
2. Drain Redis stream `preenrich:enqueue_outbox` until backlog is zero OR `drain_deadline` (30 min).
3. For each level-2 doc still in `lifecycle in {ready, queued, running}` with no remaining Redis work:
   - if all stages complete: set `lifecycle="cv_ready"` (via backfill finalizer)
   - else: set `lifecycle="stale"` and let the new DAG root-enqueuer pick it up (it will when canary widens)
4. Stop consumer (`outbox_consumer_tick`).
5. Only now set `PREENRICH_DISABLE_REDIS_OUTBOX=true` permanently.
6. Redis deadletter stream `preenrich:deadletter` is archived to disk, not deleted.

Without this procedure, flipping the flag creates stranded docs (critical risk #6).

---

## 13. Edge Cases And Failure Modes

Iteration 4 must explicitly handle each of these, with the owning mechanism named:

| Case | Owning mechanism | Section |
|------|------------------|---------|
| Worker crash after stage output persist, before downstream enqueue | stage-outbox Phase B sweeper | §6.2 |
| Worker crash after downstream enqueue, before work_item status update | `E11000` on re-insert + unique `idempotency_key` | §4.4.1 |
| Two workers racing on the same stage task | `findOneAndUpdate` on `status=pending` claim + `lease_owner` guard on completion | §6.2 |
| Stale stage task after snapshot change | snapshot-invalidator + claim-time snapshot check | §6.4, §6.6 |
| Same stage repeatedly retrying while downstream already exists | unique `idempotency_key` suppresses duplicates | §4.4.1 |
| Missing prerequisite output despite status `completed` | prerequisite enforcement at claim (also checks `input_snapshot_id` match) | §6.7 |
| Manual Mongo edits while stages in flight | snapshot change triggers §6.6; prerequisite check blocks stale execution | §6.6, §6.7 |
| Deadletter in one stage while downstream pending | job `failed` policy per registry; downstream work items `cancelled` | §6.3 |
| Historical docs in `ready`/`ready_for_cv`/`queued`/`running` | backfill script §12.5 + outbox drain §12.6 | §12.5, §12.6 |
| Lingering old worker or outbox | ownership marker §6.0 + flag mutual exclusion §12.2 | §6.0, §12.2 |
| Dead worker holding lease | stage sweeper flips leased→pending on expiry | §4.4.3 |
| Two concurrent last-stage completions racing on `cv_ready` | `cv_ready_at not exists` CAS in finalizer | §6.5 |
| Clock skew on VPS affecting lease comparisons | always use Mongo server time (`$$NOW`) in filters, not client-computed `now` | §6 throughout |
| Partial index build during rollout | indexes ship BEFORE code that reads them; gated by startup probe | §4.5 |

Every stage must define in the registry:

- retryable failure classes (network timeout, 5xx, JSON parse flake, rate limit)
- terminal failure classes (auth failure, schema violation, parse guardrail)
- `max_attempts`
- deadletter semantics
- `required_for_cv_ready` boolean
- `job_fail_policy` on deadletter (`fail|deadletter|continue`)
- operator-visible `last_error` redaction rules

---

## 14. Production-Readiness Gates

Iteration 4 is production-ready only when all of the following are true.

### Functional gates

- a selected job enters the stage DAG through `preenrich.jd_structure`
- all required stages progress through work items, not only in-process sequencing
- a completed job reaches `cv_ready`
- no active production path writes `ready` or `ready_for_cv`
- the old Redis/runner outbox is disabled from the active path

### Operational gates

- each stage can be paused and resumed independently
- each stage backlog is visible in the dashboard
- each stage can be scaled independently on the VPS
- no duplicate next-stage enqueue observed in canary
- no duplicate terminal `cv_ready` finalization observed in canary

### Observability gates

- every stage emits Langfuse traces with the canonical names
- per-job stage timeline is visible in the UI
- logs, work-item status, and Langfuse use the same stage vocabulary

### Infrastructure gates

- stage worker `systemd` units are installed
- `infra/` structure is introduced and documented
- Langfuse TTL or deletion fallback is configured
- storage monitoring exists for Langfuse

### Test gates

- lifecycle and snapshot invalidation tests exist
- idempotent next-stage enqueue tests exist (simulate crash between Phase A and B)
- unique `idempotency_key` on `work_items` is asserted by a test
- prerequisite-at-claim guard has a test (out-of-order claim rejected)
- dead-worker sweeper has a test (expired lease flipped back to `pending`)
- duplicate `cv_ready` finalization is proven impossible by test
- dual-path ownership guard has a test (legacy `claim_one` + DAG root-enqueuer cannot both own the same doc)
- snapshot-mid-flight invalidation has a test (cancels pending, re-enqueues root, old outputs preserved but not counted)
- stranded-outbox drainer has a dry-run test against a fixture
- retry/deadletter tests exist for each stage class
- rollback path is exercised on a non-critical slice

### Documentation gates

- `docs/current/architecture.md` updated with the new stage DAG, `orchestration` marker, sweeper topology, `cv_ready` lifecycle
- `missing.md` session entry added per AGENTS.md rules
- `docs/current/cv-generation-guide.md` terminal-state reference updated from `ready`/`ready_for_cv` to `cv_ready`

---

## 15. Verification Checklist

Required verification before iteration 4 can be called done:

1. A real selected canary job gets root-enqueued into the preenrich DAG.
2. Each required stage produces one durable completion record for that snapshot.
3. No duplicate downstream stage work items are produced in the canary.
4. A fully successful canary job lands in `cv_ready`.
5. A forced transient failure retries only the affected stage.
6. A forced terminal failure deadletters only with clear operator visibility.
7. Pausing one stage worker stops only that stage, not the whole lane.
8. Langfuse shows the full stage chain for the canary job.
9. Langfuse daily storage growth is within the chosen budget after canary.
10. Rollback to the legacy sequence path is verified on a safe slice.

## 15.1 Required Test Matrix

At minimum, implementation must add tests for:

- root enqueue from `selected` (idempotent; CAS prevents second enqueue)
- ownership marker prevents legacy `claim_one` from picking a DAG-owned doc
- per-stage claim and lease semantics (two workers, only one wins)
- stage success writes output and enqueues next stage once (simulated crash between Phase A and B; sweeper completes safely)
- `work_items.idempotency_key` unique violation on duplicate enqueue is a safe no-op
- retry after transient stage failure (attempt_count increments; `available_at` pushed; token unchanged until real retry)
- deadletter after retry exhaustion; `job_fail_policy` applied
- snapshot invalidation cancels stale pending AND in-claim work
- prerequisite-at-claim guard rejects out-of-order claim with correct Langfuse reason
- `cv_ready` finalization only after all required stages complete
- duplicate `cv_ready` finalization suppressed (two concurrent finalizer calls → exactly one $set)
- dashboard rendering for per-stage statuses and errors
- `attempt_token` excludes provider/model (regression guard)
- backfill script dry-run: produces identical counts on two consecutive runs (idempotence)
- outbox drainer: no stranded docs remain after drain completes

## 15.2 Canary Safety Acceptance

Before widening beyond the single-job canary:

- 10 canary jobs reach `cv_ready` with no duplicate work_items (query: `work_items` group by `idempotency_key` — all counts == 1)
- 0 double-writes to `stage_states.*.output` (query: `preenrich_stage_runs` for duplicate `(job_id, stage, attempt_token)`)
- 0 legacy-path claims on DAG-owned docs (query: `pre_enrichment.orchestration=="dag"` AND `lease_owner` set by legacy worker)
- 0 stranded `lifecycle in {ready, queued, running}` docs after outbox drain

---

## 16. Suggested Execution Order

1. inspect and document the current stage prerequisites and output contracts
2. define the stage registry and DAG metadata
3. add queue schema and indexes
4. add stage-level worker entrypoint with stage allowlists
5. convert each existing stage to queue-owned execution
6. implement atomic next-stage enqueue and `cv_ready` finalization
7. add UI for stage matrix and backlog visibility
8. add Langfuse naming alignment and retention guardrails
9. add `systemd` units and deploy scripts under `infra/`
10. run canary, soak, and rollback verification

---

## 16.1 Out-Of-Band Clarifications Still Needed

The plan proceeds on these assumptions; violating any requires a plan revision:

- Mongo deployment is a replica set (enables `$$NOW` and majority reads for sweepers). If standalone, revisit §6 atomicity.
- Deployed Langfuse edition supports project retention, OR §10.3 fallback is accepted.
- No downstream code outside `src/preenrich/` or `frontend/` currently reads `level-2.lifecycle in {ready, queued, running}` for business logic. If such readers exist, they must be enumerated and updated in the same iteration.
- Selector worker's current `lifecycle="selected"` + `selected_at` write contract is unchanged. Iteration 3's `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle` remains the only handoff shape.

## 17. Definition Of Done

Iteration 4 is done when:

- preenrich is a true stage-level Mongo queue DAG
- each of the 8 stages is independently deployable and controllable
- the live terminal lifecycle is `cv_ready`
- the old monolithic preenrich and Redis outbox paths are out of the active production path
- Langfuse, Mongo, and the dashboard all tell the same stage-by-stage story
- the architecture is ready for more preenrich stages later without another orchestration redesign

That is the correct production-ready boundary for this iteration.
