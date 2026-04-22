# Scout Pre-Enrichment Refactor — Final Plan (v3, Codex-primary)

Author: planning session on 2026-04-17 (v1 → v2 Codex-reviewed → v3 Codex-primary by user directive)
Target commit location: `plans/scout-pre-enrichment-skills-plan.md`
Companion update: `plans/cv-pipeline-overhaul.md` Phase 4 rewrite (see §14)

**Status snapshot as of 2026-04-17 (after Phase 3 scripts shipped):**
- Phase 0, 1, 2, 3 code: committed and green (237 preenrich + 1181 regression tests)
- Phase 3 historical-replay scripts: committed; not yet run against production Mongo
- **Outstanding Codex-primary work (this plan revision):** Phase 2b provider flip, Phase 2.5 model pre-flight, Phase 3 re-interpretation, Phase 3.5 compressed to 6h, Phase 5 fit_signal re-add, Phase 6 retired

---

## Context

**Problem.** Pre-CV enrichment (JD extraction, JD structuring, AI classification, pain points, annotations, persona, company research, role research, fit signal) currently runs inside `BatchPipelineService.execute` on the runner. This monolith is:
- non-resumable (one failure kills partial progress)
- opaque (no per-stage status, no checksum, no cost/provenance)
- hardwired to Claude providers per step
- expensive on retries (re-runs everything including persona Opus)
- visually dishonest (selector marks `level-2.status = "under processing"` before enrichment begins)

**Intended outcome.** Move all pre-CV enrichment out of the runner into lease-based worker(s) that run on the VPS after the selector. Each stage persists incrementally in Mongo. The runner, when it dequeues, skips the completed upstream stages and runs only role selection + CV generation + upload.

**Provider strategy (REVISED 2026-04-17c per user directive "go hard to Codex"):**

- **Preenrich worker:** Codex is the production **default** for every LLM-backed stage from Phase 2 onwards. Claude is kept as an **automatic fallback** (Codex provider failure / schema-validation failure → retry with Claude once + record provenance). This is the subsystem this plan controls.
- **Runner (downstream of preenrich):** continues to use Claude Code CLI unchanged. Role selection, CV generation (Layer 6 V2), QA, cover letter, upload — all stay on Claude. This plan does NOT touch the runner's LLM choices.
- **Codex availability verified:** `codex-cli 0.121.0` installed on dev machine and VPS. Auth mounted at `/home/runner/.codex/auth.json` on VPS runner containers. No new infra work to ship Codex as preenrich primary.

Rationale: Codex uses a fraction of the tokens/cost Claude does for equivalent quality on strict-schema extraction tasks, which is exactly what preenrich stages do (JD → structured output, JD → classification, JD → pain points). The original shadow-first plan was over-cautious given existing VPS infra. The runner stays on Claude because it's generation-heavy (CV content, cover letters) and Claude's output style is already tuned for that.

This plan incorporates (a) a critical review by `codex exec gpt-5.4` which flagged five architectural changes (§15.2), and (b) a second Codex review that corrected the over-skilled design (§15.1), and (c) a user directive to cut to Codex as primary provider from Phase 2 (§15.3 added below).

**Infrastructure already on VPS (verified via SSH 2026-04-17):**
- `job-runner-runner-{3,4,5}`: 3 runner replicas, `MAX_CONCURRENCY=1`, Traefik LB at `runner.uqab.digital`
- `n8n-redis`: shared Redis, already used by runner for `logs:{run_id}:*` streams
- `mongodb-green:27018`: shared Mongo, single `jobs` DB
- `oc`: OpenClaw container (has Codex CLI + codex-auth.json baked in)
- `/root/job-runner/credentials/codex-auth.json`: already mounted into runner containers for CV review

**Deployment decision (2026-04-18, user directive):** preenrich-worker runs on the **VPS host alongside scout-cron at `/root/scout-cron/`**, NOT inside the runner docker container. Rationale:
- scout-cron already runs this way (per `MEMORY.md`: "ALL phases run on VPS host at `/root/scout-cron/` (NOT in oc container — OpenClaw cron too slow)")
- Preenrich is the logical continuation of the scout cron pipeline: selector → preenrich → enqueue → runner. Keeping preenrich adjacent to its upstream (selector cron) and away from its downstream (runner container) is cleaner boundary-wise.
- VPS host already has Codex CLI installed + authenticated, Python venv pattern, same Mongo access (27018), same Redis access (n8n-redis on the docker network, accessible from host).
- Avoids coupling preenrich deploy cadence to the runner image's GHA → GHCR pipeline.

The worker lives at `/root/scout-cron/preenrich/` on the VPS, invoked as a long-running systemd service or by a short-interval cron entry. JSONL audit at `/var/lib/scout/preenrich_audit.jsonl` (already specified in the plan).

---

## 1. Current-state E2E map (one paragraph)

Scraper cron (VPS host at `/root/scout-cron`) writes scored jobs to `/var/lib/scout/scored.jsonl`. Selector cron reads that file, applies dedup/filters, promotes tier-A/B/C jobs to Mongo `level-2` with `status=null`, then for the top HOURLY_QUOTA tier-C+ jobs it flips `level-2.status = "under processing"` and POSTs to the runner at `/api/jobs/{id}/operations/batch-pipeline/queue`. The runner's `BatchPipelineService.execute` runs `FullExtractionService` (layer 1.4 JD extractor + layer 2 pain points + annotation suggester + persona Opus), then conditionally `CompanyResearchService` (layer 3 + layer 3.5), then `CVGenerationService` (layer 6 V2), then uploads to Drive. All pre-CV stages run synchronously inside a single runner process; failure of any step aborts the rest of the run with no resumable state.

The refactor hoists the pre-CV block out into a separate **pre-enrichment worker** process, leaving the runner responsible only for role archetype selection + CV gen + QA + upload.

Detailed stage table (what moves upstream):

| Stage | Current code | Current model | Moves upstream? |
|-------|--------------|---------------|------------------|
| jd_structure | `src/layer1_4.process_jd` + `structure_jd_service.py` | rule + Haiku | yes |
| jd_extraction | `src/layer1_4/claude_jd_extractor.py` | Haiku (no fallback) | yes |
| ai_classification | `src/services/ai_classifier_llm.py` | Haiku | yes |
| pain_points | `src/layer2/pain_point_miner.py` | Sonnet | yes |
| annotations | `src/services/annotation_suggester.py` | embeddings + priors | yes |
| persona | `src/common/persona_builder.py` | Opus (downgrade target) | yes |
| company_research | `src/services/company_research_service.py` + `src/layer3/company_researcher.py` | Sonnet + WebSearch, 7d cache | yes |
| role_research | `src/layer3/role_researcher.py` | Sonnet | yes |
| fit_signal (lightweight) | `src/layer4/annotation_fit_signal.py` | rubric | yes — see §3.6 for consumer contract |
| opportunity_mapper (heavy) | `src/layer4/opportunity_mapper_v2.py` | Sonnet | **stays in runner for v1** (scope control) |
| role archetype + CV gen + QA + upload | Layer 6 V2, Layer 7 | various | stays in runner |

---

## 2. Target design — lease-based worker, one authoritative lifecycle, atomic writes

### 2.1 One authoritative lifecycle (replaces two competing state fields)

Today's ambiguity: `level-2.status` and the proposed `pre_enrichment.overall_status` would compete. Collapse to a single field `level-2.lifecycle` with explicit transitions:

```
selected → preenriching → ready → queued → running → completed
                     ↘ failed (terminal) ← retriable failures
                     ↘ stale → preenriching (after invalidation)
                     ↘ legacy (pre-existing jobs, runner-owned)
```

Rules:
- `level-2.status` is deprecated for new jobs. Kept read-only for legacy compatibility.
- Only the pre-enrichment worker may transition `selected → preenriching → ready → queued`.
- Only the runner may transition `queued → running → completed` / `running → failed`.
- Any process may mark `stale` when invalidation is detected; next worker tick repairs.

### 2.2 Lease-based work claim (no cron/PID files)

Replace cron+PID with a **lease model** using Mongo `findOneAndUpdate`:

```
db["level-2"].find_one_and_update(
  { "lifecycle": {"$in": ["selected", "stale"]},
    "$or": [ {"lease_expires_at": {"$lt": now}}, {"lease_expires_at": None} ] },
  { "$set": {"lifecycle": "preenriching",
             "lease_owner": worker_id,
             "lease_expires_at": now + 10.min,
             "lease_heartbeat_at": now } },
  sort=[("selected_at", 1)],
  return_document=AFTER
)
```

- `worker_id = hostname + pid + uuid`. Heartbeat every 60s renews `lease_expires_at` by 10 min.
- On worker crash, lease expires and another worker re-claims automatically.
- Runs identically on 1 or N workers, containers, or hosts. Single control plane (Mongo).

**Process model (updated 2026-04-18):** preenrich-worker runs as a **long-running Python process on the VPS host** at `/root/scout-cron/preenrich/`. It is NOT a docker container. Two supervision options:

1. **systemd service** (preferred): `/etc/systemd/system/preenrich-worker.service` with `Restart=always`, activated via `systemctl enable --now preenrich-worker`. One process per host. Logs to journald. Clean start/stop/restart semantics.
2. **cron tick** (fallback): `*/1 * * * * cd /root/scout-cron/preenrich && /root/scout-cron/.venv/bin/python -m src.preenrich.worker --single-tick` — short-lived Python process per tick, lease expiry handles crashes. Simpler, no systemd config; slower startup (~2s Python cold start per tick).

Start with systemd. Use venv at `/root/scout-cron/.venv/` (shared with the rest of scout-cron scripts — already exists). Environment loaded from `/root/scout-cron/preenrich/.env` (separate from `/root/job-runner/.env`).

**Scaling:** run as a single VPS-host process in v1 (same pattern as scout-cron). Concurrency comes from `PREENRICH_CLAIM_BATCH` (default 4) + asyncio semaphores per provider, NOT from multiple processes. If needed later, run a second systemd unit with a different `worker_id` suffix — the lease model handles it, no code change.

### 2.3 Atomic stage writes (dispatcher is the sole writer)

Every stage completion is one Mongo update that writes **both** stage metadata and stage output together:

```python
db["level-2"].update_one(
  { "_id": job_id,
    "lease_owner": worker_id,
    f"pre_enrichment.stages.{stage}.attempt_token": {"$ne": attempt_token} },  # idempotency
  { "$set": {
      f"pre_enrichment.stages.{stage}": stage_status_doc,
      **{ path: value for path, value in stage_output_patch.items() },  # legacy top-level fields
      "lease_heartbeat_at": now,
  }}
)
```

- Stage outputs continue to live in legacy top-level fields (`extracted_jd`, `pain_points`, `persona`, `company_research`, …) so existing consumers are unchanged, **but** they are only written when the stage atomically transitions to `completed` for the current `jd_checksum` / `company_checksum`. No exceptions — the existing `annotation_suggester` direct-write path is refactored to emit a patch instead.
- `attempt_token = sha256(job_id|stage|jd_checksum|prompt_version|attempt_number)` — **excludes provider/model** so a fallback provider attempt does not duplicate work (Codex review item #26).
- If the update matches 0 docs (lease lost or attempt_token already written), the worker discards the result without retry — another worker or prior attempt owns it.

### 2.4 Durable enqueue via outbox

The worker does not POST the runner directly. Instead:

1. When all required stages are `completed`, the worker sets `lifecycle = "ready"` + `ready_at` atomically.
2. A separate small **outbox stage** (same worker, runs every tick) finds jobs with `lifecycle = "ready"` and writes an entry to Redis stream `preenrich:enqueue_outbox` (XADD), then flips to `lifecycle = "queued"` only on XADD success.
3. A lightweight **outbox consumer** (inside the runner image, runs in its own loop) XREADs the stream, POSTs the runner's own HTTP queue endpoint, and ACKs the stream entry only on 2xx response. On failure it retries with backoff; on exceeded budget it routes to `preenrich:deadletter` and sets `lifecycle = "failed"` + `failure_context`.

Why: makes delivery at-least-once with explicit de-dup keys, survives network blips, separates worker from HTTP call, and matches how `scout_preenrich_cron` would have had to behave anyway.

Queue key: `batch-pipeline:<job_id>:<jd_checksum>`.

**Explicit dedupe lifecycle** (replaces hand-wavy "runner treats repeats as no-ops"):

- **Producer side (worker outbox):** before XADD, check Redis SET `preenrich:outbox_seen:<queue_key>` with `SET ... NX EX 86400`. If the key already exists, skip XADD — already delivered. This is the at-least-once guard on the producer.
- **Consumer side (outbox → runner):** the HTTP POST to the runner includes header `X-Idempotency-Key: <queue_key>`. Runner's queue endpoint persists the key in a capped collection `runner_idempotency` (TTL 48h). On duplicate key, returns 200 with `{status: "duplicate"}`. Consumer ACKs the stream entry on both new-accept and duplicate responses.
- **On 5xx/timeout:** consumer does NOT ACK. Retries with exponential backoff (1s, 4s, 16s, 60s, 300s). After 5 failed attempts, entry moves to `preenrich:deadletter` and worker sets `lifecycle = "failed"` with `failure_context.reason = "outbox_exhausted"`.
- **Key expiry:** 48h TTL matches worst-case runner backlog. After expiry, a job that still needs enqueue (e.g. stale → re-enriched) gets a fresh key because `jd_checksum` changes; if checksum is unchanged, the Redis SET is gone and producer re-delivers, runner's `runner_idempotency` collection accepts it as new. This is the only case where we intentionally allow re-execution and it requires stale invalidation to have fired, which is already logged.

### 2.5 Per-stage persistence schema

```json
{ "pre_enrichment": {
    "schema_version": 1,
    "jd_checksum": "sha256:...",
    "company_checksum": "sha256:...",
    "input_snapshot_id": "sha256(jd_text_at_dispatch_time)",  // immutable per attempt sequence
    "stages": {
      "jd_structure": {
        "status": "completed",          // pending|in_progress|completed|failed|stale|skipped|failed_terminal
        "provider": "claude",            // actually used
        "model": "claude-haiku-4-5",
        "prompt_version": "v3",
        "jd_checksum_at_completion": "sha256:...",
        "input_snapshot_id": "sha256:...",
        "attempt_token": "sha256:...",
        "started_at": "...", "completed_at": "...", "duration_ms": 1234,
        "retry_count": 0, "last_error_at": null, "failure_context": null,
        "tokens_input": 850, "tokens_output": 420, "cost_usd": 0.0021,
        "skip_reason": null, "cache_source_job_id": null
      },
      "…": {}
    }
}}
```

Stages: `jd_structure`, `jd_extraction`, `ai_classification`, `pain_points`, `annotations`, `persona`, `company_research`, `role_research`, `fit_signal`. DAG order enforced by the dispatcher.

Terminal state `failed_terminal` is in the enum (fixes Codex review item #29). The `overall_status` field is removed — lifecycle is on `level-2.lifecycle`.

### 2.6 Transitive invalidation DAG

Staleness propagation is explicit:

```
jd_text change  → jd_checksum changes
                → {jd_structure, jd_extraction, ai_classification, pain_points, annotations} → stale
                → persona (depends on annotations) → stale
                → role_research (depends on jd_extraction + company_research) → stale (jd side only)
                → fit_signal (depends on all) → stale

company change  → company_checksum changes
                → {company_research, role_research, fit_signal} → stale

priors rebuild (priors_version change)
                → annotations → stale
                → persona → stale
                → fit_signal → stale
```

Encoded in `src/preenrich/dag.py` so a single test fixture validates the full propagation.

### 2.7 Input snapshot per attempt sequence

At the start of a claim, the worker captures `input_snapshot_id = sha256(jd_text)` and uses that same snapshot for every stage in the sequence. If during the sequence a scraper re-updates the JD, the snapshot protects consistency; the next claim re-reads the fresh text and all stages are marked stale via normal checksum logic.

### 2.8 BDD scenarios (the 12 that must exist as tests)

- **S1 — Selected job enters pre-enrichment.** Given a tier-C+ job promoted to `level-2` with `lifecycle = "selected"`, when the worker ticks, then it claims the lease, runs stages in DAG order, and after each stage atomically writes stage metadata + legacy output.
- **S2 — Mid-sequence failure is resumable.** Given stages jd_structure, jd_extraction, pain_points completed and persona failed with retry_count=1, when the next tick runs, then only persona is retried with retry_count=2 and the attempt_token advances.
- **S3 — Runner skips when upstream is ready.** Given `lifecycle == "queued"` and valid `jd_checksum`, when the runner begins, then `BatchPipelineService` detects readiness and skips Full Extraction + Company Research + Persona.
- **S4 — JD text change triggers transitive invalidation.** Given a job with most stages completed at checksum X, when JD is re-scraped to checksum Y, then exactly the JD-dependent subgraph is marked stale and the company-only stages are not.
- **S5 — Two workers claim concurrently.** Given two workers tick in the same millisecond, when both call `findOneAndUpdate`, then exactly one acquires the lease and the other gets a null result (validated via `test_dispatcher_claim_race`).
- **S6 — Provider success + Mongo write crash.** Given a stage ran successfully but the Mongo write crashed before persisting, when the worker restarts, then the stage is re-run and produces the same `attempt_token` (because provider/model are excluded), so the idempotency guard short-circuits duplicate work.
- **S7 — Outbox delivery.** Given `lifecycle == "ready"`, when outbox consumer fails POST, then it retries with backoff and does not flip to `queued` until HTTP 2xx. After budget exhaustion, it routes to `preenrich:deadletter` and sets `lifecycle = "failed"` with context.
- **S8 — Lease expiry and recovery.** Given a crashed worker with `lease_expires_at` in the past, when another worker ticks, then it re-claims the job without manual intervention; no duplicate outputs are produced thanks to `attempt_token`.
- **S9 — Company cache hit.** Given another level-2 job has `company_research` completed within 7 days, when the stage runs, then it reads the canonical `company_cache` entry (not the other job's document), materializes a per-job copy into `job.company_research`, and marks the stage `skipped` with `skip_reason="company_cache_hit"`.
- **S10 — Codex shadow mode produces parity.** Given `PREENRICH_SHADOW_CODEX=true`, when a stage runs with Claude as primary, then Codex runs in parallel and writes its output to `pre_enrichment.stages.<stage>.shadow_output`. A diff report runs nightly; cutover gated on parity metrics.
- **S11 — Legacy job unchanged.** Given a pre-existing level-2 job with no `pre_enrichment` field, when the worker ticks, then it sets `lifecycle = "legacy"` and the job is handled by the runner with today's Full Extraction path (back-compat).
- **S12 — Feature flag off.** Given `PREENRICH_WORKER_ENABLED=false`, when selector promotes a new job, then no worker claims it and selector's direct-enqueue path still runs (rollback safety for Phases 0–2).

---

## 3. Modularization — stage modules + ONE operator skill + ONE generic CLI (revised twice)

### 3.0 How this section evolved

User pushback (2026-04-17a): "why just one skill and not 4? did I not say modularization?" → I proposed 9 per-stage skills (v2).

Second Codex gpt-5.4 review (2026-04-17b) rejected v2: 9 skills is interface sprawl and misreads the `scout-jobs` precedent. `scout-jobs` is **one real skill with many internal phases** (proxy/search/scrape/selector are phases, not separate skills — see `n8n/skills/scout-jobs/SKILL.md`). The correct answer to modularization is **stage modules internally + one operator-facing skill externally**. Per-stage skills would freeze internal DAG nodes into the public operator surface, pollute UX, create 9 dead-weight smoke-test files for paths production never uses, and open footguns where `preenrich-persona --job-id X --force` runs without lease/snapshot validation.

**v3 design (this section).**

### 3.1 Three surfaces, one execution contract

| Surface | Who uses it | How |
|---------|-------------|-----|
| `src/preenrich/stages/*.py` | worker, manual CLI, tests | Python import of `run(ctx) -> StageResult`. Pure function. No Mongo I/O. |
| `src/preenrich/dispatcher.py` | worker, manual CLI | `dispatcher.single_stage(ctx, stage_name)` and `dispatcher.run_sequence(ctx)`. **Sole Mongo writer.** Sole lease holder. Sole persister. |
| `.codex/skills/preenrich-pipeline/` | operators, OpenClaw, Codex agents | ONE real operator-facing skill. Calls `dispatcher.run_sequence()` for a given `--job-id` (or batch). Follows `scout-jobs` SKILL.md convention. |
| `scripts/preenrich_ops.py` | operators, on-call, debugging | Generic manual CLI. Subcommand `run-stage --stage X --job-id Y [--force]` calls `dispatcher.single_stage()`. Also hosts the operator subcommands in §10 (requeue, clear-lease, inspect, deadletter-*, stats). |

**No per-stage skills.** Internal stage names are implementation detail, not public UX. Changing a stage name or splitting a stage must not break an operator interface.

**Dispatcher is the only persister.** Manual stage execution via `preenrich_ops.py run-stage` goes through `dispatcher.single_stage()` which:
1. Acquires/extends lease (refuses if another worker holds it, unless `--force` is passed with explicit override semantics documented in the script).
2. Validates prerequisites per `dag.py` (e.g. `persona` refuses to run if `annotations` is not `completed` for current checksum).
3. Creates or reuses `input_snapshot_id`.
4. Invokes `stages.<stage>.run(ctx)`.
5. Persists atomically.

Bypassing the dispatcher is not supported from any surface.

### 3.2 When manual stage execution is allowed

- **Permitted:** operator debugging, running a single stage on a fixture job, backfilling a stage after a priors rebuild, shadow-provider comparison.
- **Forbidden by default:** running `persona` before `annotations` is `completed`. The dispatcher refuses. `--force` is available but logs a Telegram warning and marks the stage's `provenance.forced=true`.
- **Never:** writing outputs directly without going through `dispatcher.single_stage()`.

### 3.3 Package + skill layout

```
src/preenrich/
  __init__.py
  types.py          # StageStatus, StageResult, StageContext, attempt_token()
  checksums.py      # normalize_jd, jd_checksum, company_checksum
  dag.py            # stage order, dependencies, invalidation propagation, prerequisite checks
  lease.py          # findOneAndUpdate-based claim, heartbeat loop
  outbox.py         # Redis XADD producer + consumer with dedupe-key lifecycle (§5.2)
  dispatcher.py     # single_stage(ctx, stage) + run_sequence(ctx) — SOLE Mongo writer, SOLE lease/snapshot enforcer
  worker.py         # long-running entrypoint (docker compose service); claims leases, calls dispatcher.run_sequence()
  stages/
    base.py         # StageBase protocol
    jd_structure.py
    jd_extraction.py
    ai_classification.py
    pain_points.py
    annotations.py       # refactored: returns patch, does NOT write directly
    persona.py
    company_research.py  # reads/writes shared company_cache, emits per-job patch
    role_research.py
    fit_signal.py

scripts/
  preenrich_ops.py             # operator CLI: run-stage, requeue, clear-lease, inspect, deadletter-*, stats
  preenrich_replay.py          # fixture-job smoke
  preenrich_shadow_diff.py     # shadow/parity diff report
  migrations/add_preenrich_indexes.py

.codex/skills/
  preenrich-pipeline/          # ONE skill. SKILL.md + run.py that calls dispatcher.run_sequence() for --job-id or --batch.
```

### 3.4 Decomposition is real, not a thin wrap

Three existing services are **coupled orchestrators**, not extract-ready units. The plan must acknowledge real decomposition work, not "thin wrap":

- `src/services/full_extraction_service.py` — currently does `jd_extraction → partial Mongo write → reload doc for annotation suggester → persona later`. The coupled orchestration must be teased apart into `stages/jd_extraction.py`, `stages/pain_points.py`, `stages/annotations.py`, `stages/persona.py` each returning patches. Expect ~200–400 LOC of refactor across these four stage adapters plus removal of the orchestration glue.
- `src/services/annotation_suggester.py` — `generate_annotations_for_job()` writes directly to Mongo today; must be split into a pure function that returns annotations + a separate Mongo write in the dispatcher. Callers outside preenrich must be updated to the new signature (search `generate_annotations_for_job` usage before Phase 2).
- `src/services/company_research_service.py` — current contract treats a cache hit as "skip role research too." The stage split makes `company_research` and `role_research` independent; the cache-hit behaviour is preserved by (a) `company_research` stage marks itself `skipped` + materializes per-job data, (b) `role_research` stage still runs because the dependency graph requires it. This is a behaviour change and must be called out in the Phase 2 gate review.

Adapter work is listed in §13 as modifications. Tests T7–T14 cover the stage contracts; additional tests must assert the pre-decomposition outputs are bit-identical on fixture jobs before the decomposition commits.

### 3.5 Skill convention

`.codex/skills/preenrich-pipeline/SKILL.md` follows the scout-jobs template: name, triggers, inputs, outputs, example invocation, failure modes. `run.py` is ~40 lines: parse args → build `StageContext` → call `dispatcher.run_sequence(ctx)` → print JSON summary.

One skill, one surface, one execution contract. Decomposition lives in `src/preenrich/` where it can be tested properly.

### 3.6 fit_signal: consumer contract

Current `BatchPipelineService` deliberately skips Layer-4 fit scoring during batch extraction — it is computed ad-hoc for UI display. Moving `fit_signal` upstream only pays off if a consumer exists. The v1 consumer contract:

- **Consumer:** `BatchPipelineService.execute()` role-selection step reads `job.fit_signal` (produced by the upstream stage) as one input to archetype ranking. If absent (legacy job), falls back to computing it inline as today.
- **Output fields:** `fit_signal.overall_score: float`, `fit_signal.axis_scores: dict[str, float]`, `fit_signal.rationale: str`. Same schema as `annotation_fit_signal.py` produces today.
- **Relationship to Layer-4 opportunity_mapper:** `fit_signal` is the cheap rubric score. `opportunity_mapper_v2` remains runner-side, runs only for QUALITY tier, and is unchanged. They are distinct outputs; `fit_signal` is NOT a replacement.
- **If no consumer exists post-review:** drop `fit_signal` from the v1 upstream stage list. Cost saved, scope reduced. This is a **Phase 2 planning check** — before implementing `stages/fit_signal.py`, verify at least one live consumer will read it.

### 3.1 Where the worker runs (REVISED 2026-04-18)

**On the VPS host at `/root/scout-cron/preenrich/`, as a systemd service.** NOT in the runner docker container. Supersedes the earlier "inside the runner image" design.

Why this location: preenrich is the logical continuation of the scout-cron pipeline (selector → preenrich → enqueue). It should live with its upstream (selector cron) on the VPS host, not with its downstream (runner container). Also matches memory note: "ALL phases run on VPS host at `/root/scout-cron/` (NOT in oc container — OpenClaw cron too slow)".

Directory layout on VPS:
```
/root/scout-cron/
  .venv/                                   # existing shared venv
  scout_selector_cron.py                   # existing
  scout_scraper_cron.py                    # existing
  ...
  preenrich/                               # NEW
    .env                                   # MONGODB_URI, REDIS_URL, PREENRICH_* vars, TELEGRAM_*, CODEX auth path
    src/                                   # subset of repo (rsync'd or git submodule): src/preenrich/, src/common/codex_cli.py, src/layer*, src/services/*, etc. Whatever the stages import.
    scripts/                               # preenrich_ops.py, preenrich_shadow_replay.py, preenrich_shadow_diff.py, preenrich_model_preflight.py
    run_worker.sh                          # thin wrapper: source venv, exec python -m src.preenrich.worker
```

systemd unit `/etc/systemd/system/preenrich-worker.service`:

```ini
[Unit]
Description=Preenrich worker (scout-cron companion)
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/scout-cron/preenrich
EnvironmentFile=/root/scout-cron/preenrich/.env
ExecStart=/root/scout-cron/.venv/bin/python -m src.preenrich.worker
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Env vars in `/root/scout-cron/preenrich/.env`:
```
PREENRICH_WORKER_ENABLED=false          # flip to true at Phase 3.5
PREENRICH_SHADOW_MODE=false             # Phase 3 uses the replay script, not this flag
PREENRICH_CLAIM_BATCH=4
PREENRICH_TICK_SECONDS=30
PREENRICH_LEASE_MINUTES=10
MONGODB_URI=mongodb://.../jobs
REDIS_URL=redis://localhost:6379        # n8n-redis via docker port forward to host
CODEX_AUTH_PATH=/root/.codex/auth.json  # codex CLI auth already on VPS per memory
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=6992463920
RUNNER_API_URL=https://runner.uqab.digital
RUNNER_API_SECRET=...                   # for outbox consumer to POST runner
```

Deploy flow:
1. Build source bundle in CI (or rsync from dev box) → `/root/scout-cron/preenrich/src/`
2. `pip install -r /root/scout-cron/preenrich/requirements.txt` into the existing `/root/scout-cron/.venv/`
3. `systemctl daemon-reload && systemctl restart preenrich-worker`
4. Health check: `journalctl -u preenrich-worker -f` + Telegram startup ping

Selector cron at `/root/scout-cron/scout_selector_cron.py` is changed minimally: when `SELECTOR_ENQUEUE_VIA_WORKER=true` env var is set, it stops POSTing the runner directly and instead sets `lifecycle="selected"` + `selected_at=now` on newly-promoted level-2 docs. The preenrich worker (also on the VPS host, same Mongo) picks them up.

The outbox consumer (Redis XREAD → HTTP POST to runner) also runs inside the same preenrich-worker process — it calls `runner.uqab.digital` over HTTPS. Same machine, but the HTTP boundary gives us the idempotency key guard and the dedup collection on the runner side.

---

## 4. Provider / model strategy — Codex primary for preenrich, Claude fallback

REVISED 2026-04-17c. Codex is the production default for all LLM-backed preenrich stages. Claude is the automatic fallback. Per-stage model picks below reflect "cheapest Codex model that likely clears the parity bar" — each is validated by a quick pre-flight eval before Phase 2 flip.

| Stage | Provider (v2+) | Primary model | Fallback model | Why |
|-------|----------------|---------------|----------------|-----|
| jd_structure | **rule-based (no LLM)** | — | — | Shipped code already runs `process_jd_sync(use_llm=False)`. Fixed by Codex review-3 item #2; do not move to an LLM provider. |
| jd_extraction | Codex | `gpt-5.4` | Claude Haiku | Tight Pydantic schema; full model for reliable JSON. |
| ai_classification | Codex | `gpt-5.4-mini` | Claude Haiku | Single-label; mini is plenty. |
| pain_points | Codex | `gpt-5.4` | Claude Sonnet | Quality-sensitive synthesis; full model. |
| annotations | embeddings + priors | — | — | No LLM. Unchanged. |
| persona | Codex | `gpt-5.4` | Claude Sonnet | Identity-synthesis; full model. Replaces Opus — main cost win. |
| company_research | Claude Sonnet + WebSearch | — | — | **Stays on Claude.** Codex CLI web access is not a production contract; WebSearch tool matters here. |
| role_research | **Claude Sonnet + WebSearch** | — | — | **Stays on Claude for v1.** Current implementation uses Claude WebSearch, not local synthesis (see `src/layer3/role_researcher.py:162, 239`). Moving to Codex requires splitting into web-research + synthesis first; out of scope for this cutover. Fixed by Codex review-3 item #1. |
| fit_signal | Codex | `gpt-5.4-mini` | Claude Haiku | Rubric scoring; mini is plenty. Treat as soft signal in role selection (Codex review-3 item #2). |

Rules:

1. **Fallback trigger (updated per Codex review-3 item #4):** any of the three → one Claude failover attempt:
   - Codex wrapper returns `CodexResult.success == False` (the wrapper does NOT reliably raise `CodexCLIError`; check the result object)
   - `CodexCLIError` or generic exception does raise
   - Output doesn't parse against the stage's Pydantic schema (`ValidationError`)

   On failover, record in the stage doc:
   ```json
   "provider_attempts": [
     {"provider": "codex", "model": "gpt-5.4", "outcome": "validation_error", "error": "...", "duration_ms": 1234},
     {"provider": "claude", "model": "claude-sonnet-4-5", "outcome": "success", "duration_ms": 2345}
   ],
   "provider_used": "claude",
   "provider_fallback_reason": "validation_error"
   ```
   Inline failover is one attempt max. Further reliability is handled by outer retry across worker ticks (existing retry_count logic in `dispatcher.py`). Telegram alert if fallback rate > 10% over any 50-job window.

2. **Per-stage model pre-flight (SMOKE ONLY per Codex review-3 item #5):** `scripts/preenrich_model_preflight.py --stage X --model gpt-5.4-mini --n 5` is a smoke test, not a confidence gate. 5 samples is enough to catch obvious model failures (e.g. mini can't parse the prompt) and choose between mini vs full. It is NOT enough to prove 97% schema validity — any such claim comes from Phase 3 with a forced 15-20 job sample and persisted diffs. Do not advertise preflight as "validated parity."

3. **Switchability:** `StepConfig.provider` + `StepConfig.primary_model` + `StepConfig.fallback_provider` + `StepConfig.fallback_model`. Env-var override `PREENRICH_PROVIDER_<stage>` / `PREENRICH_MODEL_<stage>` for one-off rollbacks without redeploy.

4. **Scope guard:** the runner's LLM calls (Layer 6 V2 CV gen, QA, cover letter, upload) are **not** switched. Those continue on Claude Code CLI. `UnifiedLLM` is NOT modified to route Codex globally — Codex routing stays local to `src/preenrich/stages/*.py` (verified: `src/common/unified_llm.py:106` is still Claude-first; `src/common/llm_config.py:77` already expresses this). Note the runner is not literally unchanged: `src/services/batch_pipeline_service.py:186` still needs the Phase-5 `skip_upstream` check + `fit_signal` read, but those are orchestration changes, not provider changes.

5. **Codex CLI is the transport.** `src/common/codex_cli.py` wraps `codex exec --model <M> --skip-git-repo-check "<prompt>"`. Existing wrapper already works; docstring updated from "shadow only" to "production for preenrich." **Known contract detail:** the wrapper returns `CodexResult.success=False` on subprocess non-zero; it does NOT always raise. `_call_llm_with_fallback()` must inspect the result object, not only catch exceptions (Codex review-3 item #4).

6. **`company_research` and `role_research` stay on Claude.** Both use Anthropic WebSearch tool. Codex CLI's web access is not a production contract on VPS; moving either risks the whole stage. Keep both on Claude Sonnet + WebSearch as today.

### 4.1 Parallel-run validation window (compressed from Phase 3)

Under the shadow-first plan, Phase 3 was 24h of passive dual-run for parity. Under the Codex-primary plan, we compress:

- **Phase 2.5 (new)** — model pre-flight per stage (~30 min total). Run `preenrich_model_preflight.py` on 5 fixture jobs per stage. Report per-stage: schema validity rate, mean cosine vs Claude on the same input, token + cost numbers. This gates which model each stage defaults to.
- **Phase 3 (revised)** — 20-job historical replay (§9 unchanged in mechanism). Now it validates Codex-as-primary instead of shadow. If ≥ 97% schema validity and ≥ 0.85 cosine parity on all stages, flip the worker to live writer.
- **Phase 3.5 (shortened)** — live Codex + Claude parallel-run for **6 hours** (was 48h) on ~10 jobs. Worker writes live fields using Codex; runner still re-runs Full Extraction on Claude in parallel. Diff is computed on the fly and emitted to Telegram. Pass iff no stage regression > 5% cosine drop vs Phase 3 historical numbers and zero crashes.
- **Phase 4/5** unchanged, but can start immediately after 3.5 passes.

### 4.2 What "update the code" means in Phase 2

Currently (committed), each stage has `if provider == "codex": raise NotImplementedError("codex provider pending Phase 6 cutover")`. The Phase 2 code update replaces that with:

1. Real Codex invocation path via `src/common/codex_cli.py::CodexCLI.invoke()`.
2. A shared `_call_llm_with_fallback()` helper in `src/preenrich/stages/base.py` that tries primary provider, catches known exceptions (`CodexCLIError`, Pydantic `ValidationError`), retries with fallback, records provenance.
3. Stage-specific prompt templates for Codex — where Claude prompts included Claude-isms (e.g. XML-tag scaffolding, "think step by step"), port them to the Codex idiom (tight system prompt, explicit JSON schema reminder).
4. `StepConfig` for each stage updated to `provider="codex"` + correct model per §4 table.
5. Codex CLI wrapper docstring updated — no longer "shadow only."
6. Fallback rate metric added to Telegram summary.

The `NotImplementedError` path is flipped: `provider == "claude"` stays supported as the fallback, `provider == "codex"` becomes the default happy path.

Cutover per stage requires 100 jobs with ≥ 97% schema validity and ≥ 0.85 cosine to production. Defined as acceptance criteria, not vibes (Codex review item #43).

---

## 5. Persistence: Mongo-authoritative, JSONL for audit, Redis for outbox

| Artifact | Role | Location |
|----------|------|----------|
| Stage state + outputs | Source of truth | `level-2.{job}.pre_enrichment` + legacy top-level fields |
| Audit log | Append-only journal, 7-day retention | `/var/lib/scout/preenrich_audit.jsonl` on VPS host (mounted into worker) |
| Enqueue outbox | At-least-once delivery | Redis stream `preenrich:enqueue_outbox` on `n8n-redis` |
| Dead letter | Manual inspection | Redis stream `preenrich:deadletter` + `lifecycle = "failed"` on doc |

JSONL is strictly audit/observability, never recovery state (fixes Codex review item #33). A redaction helper elides JD body / research text to keep sensitive content out of logs; only checksums, counts, and identifiers are stored (fixes Codex review item #64).

Required compound indexes on `level-2` (add in Phase 0 migration):

```
{ lifecycle: 1, lease_expires_at: 1, selected_at: 1 }      // claim query
{ "pre_enrichment.jd_checksum": 1 }                         // stale detection
{ "pre_enrichment.company_checksum": 1 }
{ lease_owner: 1, lease_heartbeat_at: 1 }                   // operator debugging
```

Fixes Codex review item #34.

---

## 6. Concurrency

- **Intra-job: strictly sequential** across stages (DAG order).
- **Inter-job: parallelism = worker replica count × PREENRICH_CLAIM_BATCH** with provider-bounded asyncio semaphores: `claude_sem=2`, `codex_sem=2`, `websearch_sem=1`.
- **Cross-worker correctness: Mongo lease + attempt_token**, not PID files.
- **Backpressure:** worker refuses new claims while `lifecycle = "preenriching"` count > `PREENRICH_MAX_IN_FLIGHT` (default 12). Selector is unaware; jobs simply wait in `selected` state. Prevents runaway cost if workers lag (fixes Codex review item #66).

---

## 7. Runner skip / resume contract

`BatchPipelineService.execute` gains one early check:

```python
job = db["level-2"].find_one({"_id": oid})
pre = job.get("pre_enrichment") or {}
current_jd_cs = jd_checksum(job.get("description", ""))
if job.get("lifecycle") in ("queued", "running") and pre.get("jd_checksum") == current_jd_cs:
    skip_upstream = True                     # scenario S3
elif job.get("lifecycle") == "legacy":
    skip_upstream = False                    # today's behaviour
else:
    # stale or missing
    db["level-2"].update_one({"_id": oid}, {"$set": {"lifecycle": "stale"}})
    raise NeedsReenrichment(job_id=oid)      # worker repairs on next tick
```

Worker claims `stale` + `selected` on next tick (§2.2). The runner never runs upstream stages itself, keeping responsibilities clean (Codex review item #17 resolved).

Queue idempotency: `batch-pipeline:<job_id>:<jd_checksum>`. Runner checks and dedups. Runner writes `lifecycle = "running" → "completed" | "failed"` atomically.

---

## 8. Test strategy

### 8.1 Tests that already cover pieces (must keep green throughout)

`tests/unit/test_layer1_4_claude_jd_extractor.py`, `test_layer1_4_jd_extractor.py`, `test_layer1_4_jd_processor.py`, `test_annotation_suggester.py`, `test_annotation_priors.py`, `test_company_research_service.py`, `test_layer3_researchers.py`, `test_layer4_opportunity_mapper_v2.py`, `test_layer4_annotation_fit_signal.py`, `test_queue_manager.py`, `test_queue_debug_metadata.py`, `tests/runner/test_runner_api.py`, `test_cross_location_dedup.py`, `test_telegram.py`.

### 8.2 Tests to add (file-level, pytest-runnable, each maps to a BDD scenario)

| # | File | Covers |
|---|------|--------|
| T1 | `tests/unit/preenrich/test_types.py` | StageResult contract, attempt_token excludes provider/model |
| T2 | `tests/unit/preenrich/test_dag.py` | DAG order + transitive invalidation (S4) |
| T3 | `tests/unit/preenrich/test_checksums.py` | JD normalization, deterministic checksums |
| T4 | `tests/unit/preenrich/test_lease.py` | findOneAndUpdate claim race (S5), heartbeat, expiry recovery (S8) |
| T5 | `tests/unit/preenrich/test_dispatcher.py` | State transitions S1/S2, atomic write with idempotency (S6) |
| T6 | `tests/unit/preenrich/test_outbox.py` | XADD producer + retry consumer, deadletter (S7) |
| T7 | `tests/unit/preenrich/test_stage_jd_structure.py` | adapter over process_jd |
| T8 | `tests/unit/preenrich/test_stage_jd_extraction.py` | Claude primary + Codex shadow path |
| T9 | `tests/unit/preenrich/test_stage_pain_points.py` | quality-gate unchanged vs pre-refactor baseline |
| T10 | `tests/unit/preenrich/test_stage_annotations.py` | patch-returning refactor (no direct Mongo write) |
| T11 | `tests/unit/preenrich/test_stage_persona.py` | Sonnet default replaces Opus, output schema unchanged |
| T12 | `tests/unit/preenrich/test_stage_company_research.py` | 7d cache hit → skipped with per-job materialization (S9) |
| T13 | `tests/unit/preenrich/test_stage_role_research.py` | depends on company + extracted_jd |
| T14 | `tests/unit/preenrich/test_stage_fit_signal.py` | consumes upstream |
| T15 | `tests/unit/preenrich/test_codex_cli.py` | subprocess wrapper, error mapping, timeout, shadow-only mode |
| T16 | `tests/unit/preenrich/test_legacy_passthrough.py` | S11 legacy jobs handled by runner |
| T17 | `tests/unit/preenrich/test_feature_flag_off.py` | S12 worker disabled leaves selector direct-enqueue intact |
| T18 | `tests/unit/preenrich/test_backpressure.py` | MAX_IN_FLIGHT enforced |
| T19 | `tests/integration/test_preenrich_slice.py` | End-to-end fixture job with real Mongo + fake Redis → ready |
| T20 | `tests/integration/test_runner_skip.py` | `lifecycle=queued` + matching checksum → runner skips |
| T21 | `tests/integration/test_stale_roundtrip.py` | JD change → runner refuses → worker repairs → runner skips |
| T22 | `tests/integration/test_dual_run_diff.py` | Shadow Codex vs Claude production diff report structure |

Unit tests use `mongomock` for Mongo and `fakeredis` for Redis so they run in CI without infra. Integration tests use the local `docker-compose.local.yml` with real Mongo + Redis.

### 8.3 Local validation loop (run after every phase)

```bash
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate

# 1) Fast unit tests (changed surface)
pytest tests/unit/preenrich/ -n 4 -v

# 2) Regression: ensure untouched layers still pass
pytest tests/unit/ -n 4 \
  --ignore='tests/unit/test_integration*' \
  --ignore='tests/unit/test_bulk*' \
  -k "layer1_4 or annotation or persona or layer3 or layer4 or queue or scout" -v

# 3) Integration slice (needs Docker + Redis + Mongo)
docker compose -f docker-compose.local.yml up -d redis mongo
pytest tests/integration/test_preenrich_slice.py -v
pytest tests/integration/test_runner_skip.py -v
pytest tests/integration/test_stale_roundtrip.py -v

# 4) Codex auth (shadow only; skipped if unavailable)
which codex && codex --version && \
  codex exec --model gpt-5.4 --skip-git-repo-check "echo {\"ok\":true}" | jq .

# 5) Manual single-job smoke
# On VPS: systemctl start preenrich-worker (or locally: python -m src.preenrich.worker)
python -m scripts.preenrich_replay --job-id <fixture_oid> --dry-run
redis-cli -p 6379 XRANGE preenrich:enqueue_outbox - + COUNT 10
```

Each phase passes only when steps 1–3 are green and the relevant BDD scenarios execute.

---

## 9. Revised rollout plan (shadow-first, reversible at every step)

Codex review was right that the original ordering was unsafe. Revised:

**Phase 0 — Foundations, no behaviour change.** ~0.5 day.
- Add `src/preenrich/` scaffolding (types, checksums, dag, lease, outbox stubs).
- Add `src/common/codex_cli.py` (shadow only).
- Extend `StepConfig.provider` and route inside stages (not globally).
- Mongo migration script: add compound indexes; default existing level-2 docs with `lifecycle = "legacy"`.
- T1–T4, T15 green.
- **Gate:** existing unit test suite passes byte-identical; no runner behaviour change.
- **Rollback:** `git revert`; indexes are additive.

**Phase 1 — Dispatcher + two stages, WORKER DISABLED BY DEFAULT.** ~1 day.
- Build dispatcher, lease, outbox modules.
- Implement `jd_structure` and `jd_extraction` stages.
- Add `preenrich-worker` systemd unit on VPS at `/root/scout-cron/preenrich/` with `PREENRICH_WORKER_ENABLED=false`. (Historical note: Phase 1 in the earliest draft proposed a runner-image docker-compose service; superseded 2026-04-18 — see §3.1.)
- Selector cron remains unchanged; still POSTs runner directly.
- T5–T10 for those two stages, T17, T18 green.
- **Gate:** enable flag locally only, verify fixture job advances through two stages, outputs byte-identical vs current runner.
- **Rollback:** unset flag.

**Phase 2 — Remaining stages in worker.** **[COMPLETED 2026-04-17 with Claude defaults; status quo baseline.]**
- Status: ai_classification, pain_points, annotations, persona, company_research, role_research all shipped with `provider="claude"` + `NotImplementedError` on Codex path. `fit_signal` dropped (§3.6 no consumer). `jd_structure` is rule-based (no LLM).

**Phase 2a — Dispatcher context refresh (PRE-REQUISITE for 2b per Codex review-3 item #3).** ~0.5 day.
- **Problem:** `src/preenrich/dispatcher.py:416` runs `run_sequence` against a frozen `ctx.job_doc`. When `annotations` runs, it does NOT see `extracted_jd` written by the prior `jd_extraction` stage in the same claim — only what was in the doc at claim time. `persona` depends on `annotations`, `role_research` depends on `company_research` — all currently broken in-sequence. Tests (`tests/unit/preenrich/test_dispatcher_full_sequence.py:107`) dodge this by mocking stage `.run()`.
- **Fix:** after each stage's atomic persist, merge the stage's output patch into `ctx.job_doc` so the next stage sees upstream state. Two options:
  1. In-memory merge: `ctx.job_doc.update(patch)` after dispatcher's Mongo write succeeds. Cheap, no re-read.
  2. Re-read from Mongo between stages: authoritative but slower. Use only if invariants (lease check, atomicity) require it.
  
  Pick option 1 unless audit shows cross-claim drift. Either way, `ctx.job_doc` must reflect all completed-in-this-claim stage outputs when the next stage starts.
- **Test:** replace mock `.run()` in `test_dispatcher_full_sequence.py` with a real DAG run (mock provider calls, not stage dispatch) that asserts `annotations.run()` receives `extracted_jd` in its `ctx.job_doc` populated by the prior `jd_extraction` call in the same claim.
- **Gate:** new test passes; manual run of `preenrich_shadow_replay --sample 3` produces plausible `persona` / `role_research` outputs (they depend on upstream state; previously would have been built against empty inputs in a single-claim run).
- **Rollback:** revert the patch; context stays frozen as today.

**Phase 2b — Codex primary provider flip.** ~1 day.
- Pre-requisite: Phase 2a merged. Stages must see upstream state in same claim.
- Implement Codex branch in `jd_extraction`, `ai_classification`, `pain_points`, `persona` (NOT `role_research`, NOT `company_research`, NOT `jd_structure` per §4 table).
- Add shared helper `src/preenrich/stages/base.py::_call_llm_with_fallback(primary_cfg, fallback_cfg, prompt, schema)` implementing the Codex review-3 item #4 contract: try primary → inspect `CodexResult.success` + catch exception + validate against Pydantic schema → on any failure, one Claude attempt → record `provider_attempts[]`. Exactly one Claude failover per stage.
- Port Claude prompts to Codex-idiomatic form where needed (tight system prompt, explicit JSON schema reminder, no XML-tag scaffolding).
- Worker Telegram summary: add fallback-rate metric.
- **Gate:** unit tests parameterised for `provider="codex"` and `provider="claude"` both pass; Codex CLI reachable on VPS; 3-job smoke via `preenrich_shadow_replay --sample 3` produces valid outputs for all Codex-primary stages; fallback rate on smoke ≤ 20% (if higher, investigate before proceeding).
- **Rollback:** `PREENRICH_PROVIDER_<stage>=claude` env var; no redeploy.

**Phase 2.5 — Model pre-flight (new).** ~0.5 day.
- New script `scripts/preenrich_model_preflight.py --stage <name> --model <m> --n 5`. Runs each stage on 5 fixture jobs with both Codex and Claude; reports per-stage schema validity %, cosine parity, token + cost numbers.
- For each stage, lock in the cheapest Codex model that clears ≥ 97% schema validity + ≥ 0.85 cosine on the 5-sample preflight. If mini fails, upgrade to `gpt-5.4`.
- **Gate:** preflight report signed off. `StepConfig` models committed.
- **Rollback:** change model in `StepConfig`; restart worker.

**Phase 3 — 20-job historical replay (Codex-primary parity).** ~1 day. **[Scripts already built and committed.]**
- Revised gate from the shadow-first plan. Under Codex-primary, Phase 3 validates that the Codex-driven worker produces outputs bit-close to what Claude-driven runner produced historically.
- Run `scripts/preenrich_shadow_replay.py --sample 20 --source historical` on 20 already-processed level-2 jobs. Worker runs in `shadow_mode=True`; writes go to `pre_enrichment.stages.<stage>.shadow_output` + `pre_enrichment.shadow_legacy_fields.<field>`. Live fields untouched.
- Run `scripts/preenrich_shadow_diff.py --limit 20 --out report.md`. Per-stage schema validity %, cosine vs historical live fields, cost delta, latency delta.
- **Gate:** ≥ 97% schema validity per stage (≤ 1/20 stage failure tolerated); ≥ 0.85 cosine parity per stage; Codex cost ≤ historical Claude cost; no stage regression > 5% cosine vs preflight numbers.
- **Rollback:** flag worker off; drop shadow namespace via `scripts/migrations/drop_preenrich_shadow.py`. Live fields untouched.

**Phase 3.5 — Live Codex + Claude parallel run (FORCED 15-20 job sample over 6h).** ~0.5 day.
- Worker flipped to live writer (`PREENRICH_SHADOW_MODE=false`, `PREENRICH_WORKER_ENABLED=true`).
- Runner still runs Full Extraction on its own Claude path in parallel — idempotent dual-write on same checksum is fine.
- **Per Codex review-3 item #5:** 6-hour organic volume is 5-10 jobs on this VPS — too few for confidence. Force the sample: select 15-20 tier-C+ jobs from the last 48h, re-mark them `lifecycle="selected"` to trigger worker claim, let runner process them normally. Window stays 6h but sample is 15-20.
- **Persisted diffs, not Telegram-only (per review item #5):** each job's per-stage diff (cosine, schema validity, cost delta, latency delta, fallback reasons) writes to `/var/lib/scout/phase3_5_diffs.jsonl`. Telegram gets summary only. JSONL is the audit record for gate approval.
- **Gate:** on the forced 15-20 sample:
  - no stage regression > 5% cosine drop vs Phase 3 historical numbers
  - zero worker crashes
  - fallback rate < 10% per stage
  - cost reduction visible (expected ~70-80% vs Claude baseline on Codex-primary stages)
  - `persona`, `pain_points` specifically flagged — these are the highest-risk stages for semantic drift
- **Rollback:** `PREENRICH_WORKER_ENABLED=false`. Worker leaves live fields as-is; next runner pass on any given job uses Claude and overwrites cleanly.

**Phase 4 — Selector enqueue ownership transfer.** ~0.25 day.
- `SELECTOR_ENQUEUE_VIA_WORKER=true`: selector stops direct-POST; sets `lifecycle="selected"` only.
- Outbox consumer takes over runner enqueue. Workflow: selector → lease claim → stages (Codex) → outbox → runner (Claude).
- Runner still runs Full Extraction (Claude) redundantly — no skip yet.
- **Gate:** 24h production with ≤ 1% orphans (jobs stuck in `selected` > 30 min).
- **Rollback:** flag OFF; selector resumes direct POST; operator manually re-POSTs stuck `selected` jobs.

**Phase 5 — Runner skip-upstream enable + fit_signal re-add.** ~0.5 day.
- `RUNNER_SKIP_UPSTREAM=true`. `BatchPipelineService.execute()` pre-check: `lifecycle in ("queued","running")` + matching `jd_checksum` → skip `FullExtractionService` + `CompanyResearchService` + persona synthesis. Load persisted fields.
- fit_signal re-added (plan §3.6 consumer check now passes): `src/preenrich/stages/fit_signal.py` created with Codex primary / Claude fallback; wired into DAG; `BatchPipelineService` role-selection reads `job.fit_signal`.
- Stale path: runner sees mismatched checksum → sets `lifecycle="stale"` → worker repairs.
- **Gate:** 48h production parity. CV quality unchanged vs baseline. Cost drop measurable.
- **Rollback:** `RUNNER_SKIP_UPSTREAM=false`; runner resumes running upstream. No data migration — legacy fields already populated by Codex worker.

**Phase 6 — (DELETED, subsumed into Phase 2b).** Codex cutover is no longer a separate phase because Codex is primary from Phase 2b. What remains is ongoing per-stage model tuning if a particular stage shows persistent fallback-rate > 10%; in that case, either upgrade the Codex model or demote that one stage back to Claude primary. Handled operationally, not as a dedicated phase.

Each phase ends with the full local validation loop in §8.3.

---

## 10. Operator tooling

Add `scripts/preenrich_ops.py` with subcommands (fixes Codex review item #61):

- `requeue --job-id X` → clears lease, resets lifecycle to `selected`
- `clear-lease --job-id X`
- `mark-stale --job-id X --stages jd_extraction,persona`
- `mark-legacy --job-id X`
- `inspect --job-id X` → pretty-prints pre_enrichment
- `deadletter-list` → reads Redis `preenrich:deadletter`
- `deadletter-retry --stream-id N`
- `stats` → latency, success, retry, cache-hit, stale, enqueue-lag, cost per stage (reads from JSONL audit)

---

## 11. Metrics

Emitted per stage (Telegram + JSONL + optional Prometheus later):

- stage latency p50/p95
- success / failure / retry / stale / skipped rate
- cache-hit rate (company_research)
- enqueue lag (`selected_at` → `queued_at`)
- backlog depth (count by lifecycle)
- cost USD by stage by provider
- provider fallback rate

Fixes Codex review item #63.

---

## 12. Risks and mitigations (updated)

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | Codex CLI auth drift on VPS | Health check (`codex --version`) at worker startup; Claude fallback per stage invocation; Telegram alert if fallback rate > 10% / 50-job window |
| R2 | Provider output drift (Codex fallback to Claude changes output silently) | `provider_attempts[]` recorded per stage; fallback-rate metric in Telegram; Phase 3 and Phase 3.5 diff-report gates catch systematic drift; rollback per stage via `PREENRICH_PROVIDER_<stage>=claude` |
| R3 | Lease recovery races | attempt_token excludes provider/model; update-with-lease-owner guard |
| R4 | Runner image mismatch (new pre_enrichment schema unknown to older runner) | Flag `RUNNER_SKIP_UPSTREAM` default OFF until runner image is redeployed; runner tolerates missing `pre_enrichment` |
| R5 | Priors-version rebuild invalidates many annotations at once | Throttled re-enrichment in worker with `PREENRICH_MAX_IN_FLIGHT` |
| R6 | VPS CPU throttling under concurrent LLM subprocesses | Provider semaphores; single worker replica in v1 |
| R7 | Mongo index bloat | Compound indexes scoped to lifecycle/checksum; reviewed at Phase 2 gate |
| R8 | Cost regression from persona downgrade | Phase 2 eval gates the Sonnet-vs-Opus decision; can roll back per-stage |
| R9 | Legacy jobs mis-claimed by worker | `lifecycle = "legacy"` set in Phase 0 migration; worker only claims `selected`/`stale` |
| R10 | Outbox delivery stuck | Backoff + deadletter + operator retry tool |

---

## 13. Critical files — modify vs create

**Create:**
- `src/preenrich/{types,checksums,dag,lease,outbox,dispatcher,worker}.py`
- `src/preenrich/stages/{base,jd_structure,jd_extraction,ai_classification,pain_points,annotations,persona,company_research,role_research,fit_signal}.py` (fit_signal conditional on Phase 2 consumer check per §3.6)
- `src/common/codex_cli.py`
- `scripts/preenrich_ops.py` (run-stage + operator subcommands)
- `scripts/preenrich_shadow_diff.py`
- `scripts/preenrich_replay.py`
- `scripts/migrations/add_preenrich_indexes.py`
- `.codex/skills/preenrich-pipeline/{SKILL.md,run.py}` — ONE operator-facing skill
- `tests/unit/preenrich/*` (T1–T18)
- `tests/integration/test_preenrich_slice.py`, `test_runner_skip.py`, `test_stale_roundtrip.py`, `test_dual_run_diff.py`
- `plans/scout-pre-enrichment-skills-plan.md` (this document, copied)
- `docker-compose.local.yml` (if missing, adds redis + mongo for local integration)

**Modify (real decomposition, not thin wraps — see §3.4):**
- `src/common/llm_config.py` — `StepConfig.provider` / `primary_model` / `fallback_provider` / `fallback_model` fields (already started)
- `src/common/unified_llm.py` — **NOT MODIFIED.** Codex routing lives inside `src/preenrich/stages/*.py` only. UnifiedLLM stays Claude-first for the rest of the pipeline (Codex review-3 item #7).
- `src/services/batch_pipeline_service.py` — `skip_upstream` check in `execute()`; consume `job.fit_signal` when present (§3.6)
- `src/services/full_extraction_service.py` — **decompose** into stage adapters. Current orchestration (jd_extraction → partial write → reload → annotations → persona) is teased apart. Each stage returns a patch; dispatcher writes. Expect ~200–400 LOC change across stage adapters + removal of orchestration glue.
- `src/services/annotation_suggester.py` — split `generate_annotations_for_job` into pure function returning annotations + a separate Mongo write driven by dispatcher. Update any other callers of the old signature.
- `src/services/company_research_service.py` — make `company_research` and `role_research` independent stages. Cache-hit behaviour preserved by materializing per-job output in the stage. Behaviour change called out at Phase 2 gate.
- `n8n/skills/scout-jobs/scripts/scout_selector_cron.py` — set `lifecycle = "selected"`; stop POSTing runner under feature flag
- `.github/workflows/runner-ci.yml` — deploy step adds `--scale preenrich-worker=N` when replica count > 1
- **VPS: `/root/scout-cron/preenrich/`** — new directory hosting preenrich worker; systemd unit at `/etc/systemd/system/preenrich-worker.service`; reuses `/root/scout-cron/.venv/`. NOT in the runner docker-compose (per §3.1).
- `plans/cv-pipeline-overhaul.md` — Phase 4 rewrite (§14)

**Do NOT touch:**
- Layer 6 V2 CV generation code
- Layer 7 upload
- Scout scraper or scorer

---

## 14. Updates to `plans/cv-pipeline-overhaul.md`

Replace Phase 4 with:

```markdown
## Phase 4: Pre-Enrichment Moves to a Lease-Based Worker (VPS)

**Goal:** Pre-CV enrichment (JD structure, JD extraction, AI classification,
pain points, annotations, persona, company research, role research, fit signal)
moves out of `BatchPipelineService` into a new `preenrich-worker` systemd service
that runs on the VPS host at `/root/scout-cron/preenrich/` alongside the existing
scout-cron scripts. Work is claimed from Mongo via leases, stages run sequentially
per job, and state is persisted atomically after each stage. Enqueue to the runner
goes through a durable Redis outbox that HTTPS-POSTs the runner container.

**Detailed sub-plan:** [`plans/scout-pre-enrichment-skills-plan.md`](scout-pre-enrichment-skills-plan.md)

| Phase | What | Gate | Status |
|-------|------|------|--------|
| 0 | Foundations: `src/preenrich/` scaffolding, Codex CLI wrapper, Mongo indexes, `StepConfig.provider` | existing tests byte-identical | DONE |
| 1 | Dispatcher + `jd_structure` + `jd_extraction`; worker disabled by default | local fixture passes two stages | DONE |
| 2 | Remaining stages (Claude defaults) | VPS fixture reaches `lifecycle = "ready"` | DONE |
| 2a | Dispatcher refresh `ctx.job_doc` between stages so downstream sees upstream patches | real DAG test passes; 3-job smoke has plausible persona/role_research | PENDING |
| 2b | Flip Codex primary for jd_extraction, ai_classification, pain_points, persona, fit_signal | unit tests parameterised; 3-job smoke ≤ 20% fallback rate | PENDING |
| 2.5 | Smoke-only model preflight (5 samples/stage) to triage mini vs full | script runs; obvious misfits caught | PENDING |
| 3 | 20-job historical replay validates Codex-primary parity | ≥ 97% schema validity, ≥ 0.85 cosine, cost ≤ Claude, persisted JSONL diffs | PENDING |
| 3.5 | Forced 15-20 job sample in 6h live Codex+Claude parallel run | < 5% cosine drop vs Phase 3; crashes = 0; fallback < 10%; persisted JSONL | PENDING |
| 4 | Selector enqueue ownership transfer to outbox | ≤ 1% orphans in 24h | PENDING |
| 5 | Runner skip-upstream enabled + fit_signal re-added | 48h production parity, measurable cost drop | PENDING |

**Provider defaults (v3):** Codex primary for preenrich stages except `jd_structure` (rule-based), `company_research` / `role_research` (Claude + WebSearch), `annotations` (embeddings). Claude is automatic fallback on Codex failure / Pydantic-invalid output.

**Persistence:** Mongo `level-2.pre_enrichment` is authoritative.
`/var/lib/scout/preenrich_audit.jsonl` is audit-only (not recovery state).
Redis stream `preenrich:enqueue_outbox` provides at-least-once delivery.

**Lifecycle states:** `selected → preenriching → ready → queued → running →
completed | failed`. `stale` loops back to `preenriching`. `legacy` bypasses
the worker.

**Runner impact:** `BatchPipelineService.execute` gains a `skip_upstream`
branch gated by `RUNNER_SKIP_UPSTREAM=true` and a checksum match. Until that
flag flips, the runner continues to run Full Extraction + Company Research +
Persona itself (zero-risk rollback).
```

---

## 15. What the Codex reviews changed in this plan (audit trail — two passes)

### 15.4 Third Codex review (post Codex-primary revision, 2026-04-18)

Codex gpt-5.4 review on the Codex-primary plan found 5 real issues. All folded in:

| Review-3 item | Change here |
|---------------|-------------|
| #1 role_research is Claude WebSearch-backed, not synthesis | §4 table: role_research stays on Claude; moved to the "stays on Claude" rule |
| #2 jd_structure should stay rule-based | §4 table: jd_structure provider = "rule-based (no LLM)" |
| #3 dispatcher runs on frozen `ctx.job_doc`, downstream stages see stale state | New Phase 2a prerequisite: merge stage output patch into `ctx.job_doc` after each atomic persist; real DAG test replaces mocked one |
| #4 codex_cli returns `success=False`, doesn't raise reliably; "retry once" insufficient by itself | §4 rule 1 rewritten: check result.success + exception + ValidationError; record `provider_attempts[]`; inline fallback is one attempt, outer retry across ticks handles further reliability |
| #5 6h window catches crashes but not semantic drift; 5-sample preflight is smoke | §4.1 / Phase 2.5 now explicitly "smoke only"; Phase 3.5 forces 15-20 job sample with persisted JSONL diffs, not Telegram-only |
| #7 UnifiedLLM does not need Codex route | §13 modify list: "NOT MODIFIED" |
| #8 stale shadow-first language in §12 R1/R2, §14 table, §13 note | Rewritten §12 R1/R2, §14 phase table + provider defaults, §13 UnifiedLLM note |

### 15.3 User directive: "go hard to Codex" (2026-04-17c)

After Phase 3 shipped, user directed a plan revision to make Codex the production default for preenrich stages instead of shadow-first. Clarifications captured:

- Scope: **preenrich stages only**. The runner (Layer 6 V2 CV gen + downstream) stays on Claude Code CLI unchanged.
- Codex installed on VPS with auth mounted — no new infra.
- Claude remains automatic fallback on Codex provider failure / schema-validation failure.
- Parallel-run validation window shortened to 6 hours (was 48h).
- Per-stage model picks: `gpt-5.4-mini` where satisfactory, `gpt-5.4` where quality-sensitive (pain_points, persona, jd_extraction).
- `company_research` stays on Claude Sonnet + WebSearch — Codex CLI web access is not a production contract.

Plan changes: §4 rewritten; Phases 2, 2.5, 3, 3.5, 5, 6 updated (§9); context block updated.

### 15.1 Second Codex review (post user-modularization pushback)

| Review-2 finding | Change here |
|------------------|-------------|
| 9 per-stage skills = dead-weight interface sprawl | Dropped. ONE `preenrich-pipeline` skill only (§3.1–3.3) |
| scout-jobs is precedent for ONE skill with phases, not many | §3.0 explicitly cites this |
| Two invocation paths only half-justified | Manual path collapsed to `scripts/preenrich_ops.py run-stage` (one CLI, not 9 skills) (§3.1) |
| §3 contradicted itself on who persists | Dispatcher is sole persister from every surface (§3.1) |
| Manual stage execution needed lease/snapshot/prereq rules | Defined explicitly (§3.2) |
| FullExtractionService is not a thin wrap | §3.4 calls out real decomposition; §13 modify list reflects LOC expectation |
| Phase 3 dual-run racing on legacy fields | Phase 3 writes to SHADOW namespace only; Phase 3.5 added for controlled live-write transition (§9) |
| Outbox "runner treats repeats as no-ops" is not a design | Explicit dedupe key lifecycle (§2.4): producer Redis SET NX, consumer X-Idempotency-Key header, runner idempotency collection, 48h TTL |
| fit_signal consumer undefined | §3.6 consumer contract + Phase 2 check to drop if no consumer |
| `deploy.replicas` scaling claim sloppy | Honest scaling note (§3.1 container model): one-line GHA `--scale` flag, Mongo sort avoids HoL |

### 15.2 First Codex review (original)

| Codex item | Change here |
|------------|-------------|
| One control plane | Mongo lease is the ONLY claim mechanism; cron/PID removed (§2.2) |
| Two competing states | Collapsed to single `lifecycle` field (§2.1) |
| Annotations write-through exception | Refactored to return patch (§3 package layout, §13 modify list) |
| Legacy top-level fields drift | Written atomically with stage-completion update only (§2.3) |
| fit_signal boundary unresolved | Lightweight fit_signal moves; heavy opportunity_mapper stays in runner v1 (§1 table) |
| Company cache brittleness | Shared `company_cache` is authoritative; per-job materialization in the stage (§2.8 S9) |
| Wrong home for orchestration | Moved from n8n skill script to runner-image compose service (§3.1) |
| Global StepConfig blast radius | Routing isolated inside `src/preenrich/stages/*` first (§4) |
| Claim race untested | T4 added (§8.2) |
| Provider success + Mongo crash untested | T5 covers it (§8.2) |
| At-least-once enqueue untested | T6 outbox tests (§8.2) |
| Transitive invalidation untested | T2 + DAG module (§2.6) |
| S8 process-theater scenario | Removed; replaced with real behaviours |
| Legacy-job tests missing | T16 added |
| Feature-flag tests missing | T17 added |
| Backlog/backpressure untested | T18 added |
| attempt_token includes provider | Removed provider/model from the token (§2.3) |
| started_at used as lock | Replaced with `lease_owner` + `lease_expires_at` (§2.2) |
| Split writes | One atomic `$set` per stage (§2.3) |
| `failed_terminal` missing from enum | Added (§2.5) |
| Pre-flight `lifecycle = "under processing"` | Removed; flipped only after runner accepts (§7 + outbox) |
| `enqueued_at` set before POST | Replaced with outbox ACK on HTTP 2xx (§2.4) |
| Cron + PID as concurrency | Replaced with lease model (§2.2) |
| JSONL as recovery | Downgraded to audit-only (§5) |
| No indexes | Compound indexes added in Phase 0 migration (§5) |
| Cross-job cache reference | Shared `company_cache` + materialization (§2.8 S9) |
| No input snapshot | `input_snapshot_id` per attempt sequence (§2.7) |
| Codex CLI production default | Claude default; Codex shadow-first; evidence-gated cutover (§4) |
| Codex web-tool contract | Company research stays on Claude WebSearch; Codex not shadowed there (§4) |
| Cost strategy hand-wavy | Per-stage acceptance thresholds (§4); §11 metrics |
| Rollout order wrong | New 7-phase rollout, shadow-before-ownership (§9) |
| Decomm contradiction | Single Phase 4 for enqueue transfer, flag-gated (§9) |
| Dual-run diff missing | Phase 3 makes it the gate (§9) |
| Legacy job plan weak | Phase 0 migration + `lifecycle = "legacy"` + T16 (§9, §8.2) |
| Rollback undefined | Per-phase rollback explicitly documented (§9) |
| Success criteria arbitrary | Normalized (≥ 50/100 jobs, schema validity %, cosine, cost/latency bounds) (§4, §9) |
| No outbox | Added (§2.4) |
| No operator tooling | `scripts/preenrich_ops.py` subcommands (§10) |
| No metrics plan | §11 emitted metrics |
| No redaction policy | JSONL redaction helper (§5) |
| No schema-evolution plan | `schema_version` + additive-only migrations (§2.5) |
| No backpressure | `PREENRICH_MAX_IN_FLIGHT` (§6) |
| Checksum normalization undefined | `src/preenrich/checksums.py` is the single implementation used by worker and runner (§13) |

---

## 16. Verification (how to test this end-to-end)

1. **Unit:** `pytest tests/unit/preenrich/ -n 4 -v` — T1–T18 all pass.
2. **Integration (local):** `docker compose -f docker-compose.local.yml up -d redis mongo` then `pytest tests/integration/test_preenrich_slice.py tests/integration/test_runner_skip.py tests/integration/test_stale_roundtrip.py tests/integration/test_dual_run_diff.py -v`.
3. **Regression:** `pytest tests/unit/ -n 4 --ignore='tests/unit/test_integration*' --ignore='tests/unit/test_bulk*'` — green.
4. **Codex shadow auth (optional):** `codex exec --model gpt-5.4 --skip-git-repo-check "echo {\"ok\":true}" | jq .`.
5. **Single-job smoke:** `python -m scripts.preenrich_replay --job-id <fixture_oid>` → inspect `level-2.{job}.pre_enrichment` in Mongo, inspect Redis `preenrich:enqueue_outbox`, inspect runner log for `skipping Full Extraction`.
6. **VPS staged rollout:** each Phase 2/3/4/5 gate is validated on the VPS with a Telegram summary emitted per tick; dual-run diff report reviewed before enabling runner skip.

---

## 16b. Reconciliation: already-implemented v1 code vs v3 plan

A previous session implemented Phase 0 + Phase 1 against the v1 plan before the skills-rework and Codex review-2 corrections. Current working-tree state (verified 2026-04-17):

**Already written (uncommitted, staged modifications + new files):**
- `src/preenrich/` — `__init__.py`, `types.py`, `checksums.py`, `dag.py`, `lease.py`, `outbox.py`, `dispatcher.py`, `worker.py`
- `src/preenrich/stages/` — `__init__.py`, `base.py`, `jd_structure.py`, `jd_extraction.py`
- `src/common/codex_cli.py`
- `scripts/migrations/add_preenrich_indexes.py`
- `requirements.txt` — `mongomock` + `fakeredis` added
- `src/common/llm_config.py` — `StepConfig.provider` field added
- `n8n/skills/scout-jobs/scripts/scout_selector_cron.py` — flag-gated lifecycle-selected path
- Deleted: `.claude/agents/architecture-debugger.md`; modified `AGENTS.md`

**Not yet written (v1 plan said Phase 1 only, these fall in later phases anyway):**
- Stages beyond `jd_structure` / `jd_extraction` (ai_classification, pain_points, annotations, persona, company_research, role_research, fit_signal) — Phase 2
- `tests/unit/preenrich/` test files — T1–T18 were named in both v1 and v3; not written yet
- `tests/integration/test_preenrich_*.py` — Phase 2/3
- `.codex/skills/preenrich-pipeline/` — v3 introduced this
- `scripts/preenrich_ops.py`, `preenrich_replay.py`, `preenrich_shadow_diff.py`

### 16b.1 Deltas the v1 code needs to absorb to match v3

| v3 requirement | Where | Current state | Change needed |
|----------------|-------|---------------|---------------|
| Dispatcher exposes `single_stage(ctx, stage)` AND `run_sequence(ctx)` as the ONLY execution contract | `src/preenrich/dispatcher.py` | v1 implements sequence iteration inline in dispatcher | Extract `single_stage()` as a public function; have `run_sequence()` call it in a loop. Mandatory for `preenrich_ops.py run-stage` to reuse. |
| Dispatcher is sole Mongo writer from EVERY surface | `src/preenrich/dispatcher.py` | Mostly OK — stages don't write | Audit that no code path in worker/stages writes to `level-2` directly. Add assertion in dev mode if feasible. |
| Outbox dedupe key lifecycle (producer Redis SET NX + consumer X-Idempotency-Key header) | `src/preenrich/outbox.py` | v1 outbox has XADD + ACK but no explicit dedupe store | Add `SET preenrich:outbox_seen:<key> NX EX 86400` before XADD; add `X-Idempotency-Key` header to runner POST; extend 5-stage backoff to `[1,4,16,60,300]s` with 5 attempts. |
| Phase 3 writes to SHADOW namespace only (no racing on legacy fields) | future worker code + stage adapters | Not yet implemented; but dispatcher currently is wired to write legacy fields | Add `shadow_mode: bool` flag to `StageContext`; dispatcher writes to `pre_enrichment.stages.<stage>.shadow_output` + `pre_enrichment.shadow_legacy_fields.<field>` instead of live fields when `shadow_mode=True`. Default false. |
| Input-snapshot per claim sequence | worker + dispatcher | Check if `input_snapshot_id` is threaded through | Ensure `StageContext.input_snapshot_id` is captured at claim time and passed to every stage in the sequence. |
| attempt_token excludes provider/model | `src/preenrich/types.py` | Needs verification | `grep attempt_token` implementation — if it includes provider/model, strip them. |
| Manual stage execution (`preenrich_ops.py run-stage`) enforces lease + prerequisite + snapshot | `scripts/preenrich_ops.py` | Not written | Phase 1.5 deliverable. Must call `dispatcher.single_stage()` with proper lease acquire; `--force` bypasses prereq with Telegram warning. |
| ONE `preenrich-pipeline` skill, no per-stage skills | `.codex/skills/` | Nothing created — good | Create only `preenrich-pipeline/` when Phase 2 ships. Do NOT create per-stage skills. |
| fit_signal consumer check before building the stage | Phase 2 planning gate | N/A | When Phase 2 starts, verify a live consumer exists (§3.6); otherwise drop fit_signal from v1 scope. |
| `runner_idempotency` collection on runner side (48h TTL, X-Idempotency-Key) | runner | Not written — runner unchanged so far | Part of Phase 3.5 / 4 (runner changes). Need TTL index on the collection. |
| Decomposition of `FullExtractionService`, `annotation_suggester`, `company_research_service` | Phase 2+ | Not touched | Real decomposition, not thin-wrap (§3.4). |

### 16b.2 Recommended next actions in order

1. **Audit the v1 code.** `grep -rn "level-2" src/preenrich/` and confirm only `dispatcher.py` and `lease.py` write. Confirm `attempt_token` excludes provider/model. Confirm `input_snapshot_id` is threaded.
2. **Write the v1 tests that were planned but not yet written** (T1–T18 unit tests using mongomock/fakeredis). They'll catch v1-vs-v3 divergence as we adjust.
3. **Apply the 5 minimal v3 deltas** that matter before Phase 2 starts:
   - Extract `single_stage()` in dispatcher
   - Add outbox producer-side dedupe SET and X-Idempotency-Key header
   - Add `shadow_mode` to StageContext and shadow-namespace write path
   - Add input_snapshot_id capture at claim time if missing
   - Verify attempt_token signature
4. **Stage migration index script.** Verify it's idempotent, honours `--dry-run`, and backfills `lifecycle = "legacy"`.
5. **Commit in atomic slices** (`feat(preenrich): …`, `test(preenrich): …`).

None of this requires rewriting what's on disk; only the dispatcher's `single_stage` extraction and the outbox dedupe lifecycle are real code changes. Everything else is additive.

---

## 17. First slice to implement next

Phase 0 + Phase 1 together (~1.5 days), worker disabled by default. Concretely:

1. `src/preenrich/{types,checksums,dag,lease,outbox}.py`
2. `src/common/codex_cli.py` (shadow only)
3. `StepConfig.provider` field; routing inside `src/preenrich/stages/*`
4. Mongo migration: compound indexes + mark existing `level-2` docs `lifecycle = "legacy"`
5. `src/preenrich/dispatcher.py` + `worker.py`
6. `src/preenrich/stages/{base,jd_structure,jd_extraction}.py`
7. `preenrich-worker` compose service (disabled by default)
8. Selector cron behind flag `SELECTOR_ENQUEUE_VIA_WORKER=false` (no behaviour change yet)
9. Tests T1–T10, T15, T17, T18 — green
10. Local validation loop (§8.3) green

Gate to Phase 2: fixture job on laptop advances through both stages with byte-identical outputs vs current runner; worker disabled on VPS; existing pipeline untouched.

---

**Plan ready for ExitPlanMode approval. On approval, this file should be copied to `plans/scout-pre-enrichment-skills-plan.md` and §14 applied to `plans/cv-pipeline-overhaul.md` Phase 4.**
