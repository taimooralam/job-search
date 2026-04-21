# Runnerless VPS Mongo Skill Pipeline Plan

Author: Codex planning pass on 2026-04-18  
Target file: `plans/runnerless-vps-mongo-skill-pipeline.md`  
Status: implementation plan for the VPS target architecture

## 0. Executive Summary

This plan replaces the current mixed `cron + JSONL + runner queue` model with a single runnerless execution plane on the VPS:

- MongoDB becomes the authoritative queue, lease, idempotency, and state store.
- Search, scrape, selector, pre-enrichment, CV generation, scoring, review, and publish run as host-side skill workers under `systemd`.
- Codex CLI and Claude CLI run on the VPS host only, under a persistent Unix user with a stable `HOME`, so auth refresh continues to work.
- Langfuse runs separately in Docker Compose on the VPS as internal observability infrastructure and traces every stage incrementally.
- The rollout is behavior-driven and phase-gated so each stage is visible in Langfuse before the next one is enabled.

This is the architecture to actually run on the VPS. Runners are removed from the target state.

---

## 1. Fixed Constraints

These constraints are treated as non-negotiable inputs:

- `runner` containers go away.
- Redis is not the orchestration backbone.
- Codex CLI auth must survive refresh-token flows, so Codex-invoking workers do not run in Docker.
- All execution from search to CV review is skill-driven on the VPS host.
- The pipeline is queue-based and round-robin at the work-item level.
- Intermediate JSONL files are replaced by MongoDB collections.
- Langfuse is self-hosted internally on the VPS via Docker Compose and used only for observability, not orchestration.
- The live code root on the VPS remains `/root/scout-cron/`, not a separate copy bundled into the runner image.
- Operator-facing pages must be search-first, not navigation-first.
- Operational list views must be projection-based, paginated, and lazily expanded.
- New hot Mongo query paths must ship with supporting indexes in the same slice that introduces them.
- Run-level Langfuse traces and cross-stage job correlation are both required; one does not replace the other.

## 1.1 Cross-Cutting UI And Observability Constraints

These rules are durable architecture decisions and future rollout plans must inherit them.

### Operator UI

- The first screen of an operator/debug page must answer “is the stage alive now?” before it optimizes for forensic browsing.
- Search boxes plus structured filters come before large tables.
- Heavy detail must be explicitly requested via expand, hover/peek, or detail views.
- Compatibility artifacts and rollback surfaces may be shown, but they must not dominate the primary operator experience once Mongo truth exists.
- Pipeline states must be displayed with semantic honesty. Future pages must not collapse distinct states into a single vague badge.

### Mongo Query And Indexing

- Every operator page must define its hot query shapes explicitly:
  - filter fields
  - sort keys
  - projection
  - pagination
- A slice is not production-ready if it introduces a hot query path without the supporting indexes.
- Cursor/keyset pagination is preferred for operational collections that grow continuously.
- Raw payloads, full nested documents, and full histories are detail-path data, not list-path data.

### Langfuse And Traceability

- Langfuse remains observability only. Queue ownership, leases, retries, and truth stay in Mongo.
- Each native stage must emit a run-level root trace when configured.
- Cross-stage job correlation must use stable correlation identifiers persisted in Mongo and passed into traces as metadata.
- Do not replace batch/run traces with one global job-centric session model. Sessions may group related traces, but operational debugging still requires per-run traces.
- Failure records exposed to operators should carry enough metadata to jump from Mongo/UI state into Langfuse directly when possible.

---

## 2. Problems With The Current Model

Current scout flow:

- `scout_linkedin_cron.py` discovers jobs and writes `queue.jsonl`.
- `scout_scraper_cron.py` reads `queue.jsonl`, scrapes, scores, and writes `scored.jsonl`.
- `scout_selector_cron.py` reads `scored.jsonl`, inserts into Mongo, then either:
  - queues the runner directly, or
  - sets `lifecycle="selected"` behind `SELECTOR_ENQUEUE_VIA_WORKER=true`.

Current gaps:

- JSONL files in `/var/lib/scout` are the actual queue boundary.
- Search, scrape, selector, preenrich, and CV generation do not share one control plane.
- Observability is fragmented. There is no end-to-end trace surface across skills.
- The runner boundary forces HTTP queueing and duplicate operational state that is no longer wanted.
- Existing Codex usage is split between wrappers and direct `subprocess.run(...)` call sites, so tracing and auth behavior are inconsistent.

---

## 3. Target Architecture

### 3.1 Final Model

The final system is:

- `MongoDB` = source of truth for job state, queue state, leases, retries, dedupe, and audit metadata.
- `systemd` host services = long-running skill workers that claim Mongo work items with leases.
- `Langfuse` = trace sink for every worker claim and every Claude/Codex invocation.

There is no runner service and no Redis queue in the target state.

### 3.2 Control Plane Rule

There is one control plane:

- `jobs` holds the canonical mutable job document.
- `work_items` holds pending and in-flight work.
- `job_runs` holds per-attempt audit history.
- `scout_search_hits` holds raw discoveries before canonicalization.

We do not pass full job documents from collection to collection.

### 3.3 Execution Rule

Every skill worker does exactly this:

1. Claim one eligible `work_item` with a lease.
2. Load the canonical subject from Mongo.
3. Execute the skill handler.
4. Write the result atomically to Mongo.
5. Enqueue the next `work_item` if needed.
6. Emit Langfuse observations for the claim, skill execution, and LLM/tool calls.
7. Mark the `work_item` `done|failed|deadletter`.

---

## 4. Collections And State Model

### 4.1 `scout_search_hits`

Purpose: raw discoveries from search before scrape and canonical merge.

Suggested fields:

```json
{
  "_id": "ObjectId",
  "source": "linkedin",
  "external_job_id": "1234567890",
  "canonical_url": "https://www.linkedin.com/jobs/view/1234567890/",
  "canonical_url_hash": "sha256:...",
  "title": "...",
  "company": "...",
  "location": "...",
  "search_profile": "ai",
  "search_region": "remote",
  "search_query": "...",
  "first_seen_at": "ISODate",
  "last_seen_at": "ISODate",
  "hit_status": "discovered|scheduled_for_scrape|scraped|merged|duplicate|discarded|failed",
  "correlation_id": "uuid-or-stable-hash",
  "raw_search_payload": {},
  "scrape_fresh_until": "ISODate|null",
  "linked_job_id": "ObjectId|null"
}
```

Indexes:

- unique: `source + external_job_id`
- unique sparse fallback: `canonical_url_hash`
- query: `hit_status + last_seen_at`
- query: `linked_job_id`

### 4.2 `jobs`

Purpose: canonical system-of-record document from dedupe onward.

Suggested top-level structure:

```json
{
  "_id": "ObjectId",
  "dedupe_key": "sha256:...",
  "source_links": {
    "linkedin_ids": ["1234567890"],
    "search_hit_ids": ["ObjectId"]
  },
  "company": "...",
  "title": "...",
  "location": "...",
  "job_url": "...",
  "description": "...",
  "lifecycle": "discovered|scraped|selected|preenriching|cv_ready|cv_generating|reviewing|ready_to_apply|published|failed|deadletter",
  "scout": {},
  "scrape": {},
  "selection": {},
  "pre_enrichment": {},
  "cv": {},
  "review": {},
  "publish": {},
  "observability": {
    "langfuse_session_id": "job:<_id>"
  },
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Rules:

- `jobs` is the only canonical mutable job document.
- Search and scrape enrich `jobs`; they do not create parallel mutable copies.
- `lifecycle` reflects the current highest durable state of the canonical job.
- Stage-specific outputs live under phase subdocuments plus any legacy top-level fields still needed by existing code during migration.

### 4.3 `work_items`

Purpose: the round-robin queue and outbox.

Suggested fields:

```json
{
  "_id": "ObjectId",
  "task_type": "search.query|scrape.hit|dedupe.merge|select.job|preenrich.jd_structure|preenrich.annotations|cv.generate|cv.score|cv.review|publish.upload",
  "lane": "search|scrape|selector|preenrich|cv|review|publish",
  "subject_type": "search_seed|search_hit|job",
  "subject_id": "ObjectId|string",
  "status": "pending|leased|done|failed|deadletter|cancelled",
  "priority": 100,
  "available_at": "ISODate",
  "lease_owner": "hostname-pid-uuid|null",
  "lease_expires_at": "ISODate|null",
  "attempt_count": 0,
  "max_attempts": 5,
  "idempotency_key": "sha256:...",
  "correlation_id": "uuid-or-stable-hash",
  "payload": {},
  "result_ref": {},
  "parent_work_item_id": "ObjectId|null",
  "last_error": {},
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Required indexes:

- unique: `idempotency_key`
- query: `status + available_at + lane + priority + created_at`
- query: `lane + status + lease_expires_at`
- query: `subject_type + subject_id + task_type + status`

### 4.4 `job_runs`

Purpose: immutable per-attempt audit for non-trivial stages.

Use for:

- preenrich stage attempts
- CV generation attempts
- review attempts
- publish attempts

This is where long-form prompts, model metadata, checksums, timings, and failure details belong when they are too noisy for the canonical `jobs` doc.

### 4.5 Optional `artifacts`

Purpose: metadata for generated CV files, review reports, uploads, and published outputs.

This can remain optional in phase 1. The plan does not depend on it for orchestration.

---

## 5. Round-Robin Queue Model

### 5.1 Lane Order

The queue rotates through lanes in this order:

1. `search`
2. `scrape`
3. `selector`
4. `preenrich`
5. `cv`
6. `review`
7. `publish`

### 5.2 Fairness Rule

Round-robin is implemented at claim time, not by manually alternating cron jobs.

Shared behavior:

- each worker claims at most one item per polling cycle
- the claim helper advances from the last successful lane
- if the current lane has no eligible work, the helper scans forward to the next eligible lane
- a lane cannot monopolize the queue just because it has more backlog

### 5.3 Lease Rule

Claiming is atomic via `findOneAndUpdate`.

Example claim semantics:

```python
db.work_items.find_one_and_update(
    {
        "lane": chosen_lane,
        "status": "pending",
        "available_at": {"$lte": now},
        "$or": [
            {"lease_expires_at": {"$lt": now}},
            {"lease_expires_at": None},
            {"lease_expires_at": {"$exists": False}},
        ],
    },
    {
        "$set": {
            "status": "leased",
            "lease_owner": worker_id,
            "lease_expires_at": now + lease_delta,
            "updated_at": now,
        },
        "$inc": {"attempt_count": 1},
    },
    sort=[("priority", -1), ("created_at", 1)],
    return_document=AFTER,
)
```

### 5.4 Retry Rule

- transient failures: set `status="pending"` and push `available_at` forward with backoff
- permanent failures: set `status="deadletter"`
- retries are bounded by `max_attempts`
- backoff policy is per task type

### 5.5 Queue State

Add a tiny `queue_state` collection:

```json
{
  "_id": "lane_cursor",
  "next_lane": "search",
  "updated_at": "ISODate"
}
```

This keeps round-robin deterministic across worker restarts and multiple replicas.

---

## 6. VPS Process Model

### 6.1 Code Root

Use one authoritative checkout on the VPS:

- `/root/scout-cron/`

Do not create a second partial source bundle for preenrich or CV review.

### 6.2 Host-Only Execution

All skill workers run on the host via `systemd`.

Reasons:

- Codex CLI auth refresh is tied to a persistent host home directory.
- Claude/Codex wrappers already assume a local CLI environment.
- The existing scout deployment model already uses host execution under `/root/scout-cron/`.

### 6.3 Required Host Paths

Expected layout:

```text
/root/scout-cron/
  .venv/
  .env
  n8n/skills/scout-jobs/
  n8n/skills/cv-review/
  src/
  scripts/
  deploy/

/root/.codex/auth.json
/root/.config/claude/...
/etc/systemd/system/
/var/lib/scout/
```

### 6.4 Service Strategy

Use `systemd` template units with one shared Python entrypoint and lane-specific environment.

Suggested units:

- `scout-queue-seeder.service`
- `scout-queue-seeder.timer`
- `scout-skill-worker@search.service`
- `scout-skill-worker@scrape.service`
- `scout-skill-worker@selector.service`
- `scout-skill-worker@preenrich.service`
- `scout-skill-worker@cv.service`
- `scout-skill-worker@review.service`
- `scout-skill-worker@publish.service`

Each worker runs from:

```text
WorkingDirectory=/root/scout-cron
Environment=HOME=/root
ExecStart=/root/scout-cron/.venv/bin/python -m src.pipeline.worker --lane %i
```

### 6.5 Resource Policy

This VPS currently has modest headroom. Start conservatively:

- add swap before scaling up
- `MemoryMax` per worker
- `CPUQuota` per worker
- `TasksMax` per worker
- one Codex subprocess at a time per worker

Initial target shape after runner removal:

- `1x search`
- `2x scrape`
- `1x selector`
- `2x preenrich`
- `1x cv`
- `1x review`
- `1x publish`

Scale only the bottleneck lane after observing queue depth and Langfuse timings.

---

## 7. Langfuse Observability Model

### 7.1 Deployment Choice

Langfuse runs internally on the VPS via Docker Compose.

Reasoning:

- official Langfuse self-hosting docs recommend Docker Compose for low-scale deployments on a VM
- all core OSS features and APIs are available self-hosted without limits
- Langfuse is observability infrastructure, so Docker is acceptable here even though workers are host-only

Official references:

- self-hosting overview: `https://langfuse.com/self-hosting`
- OSS/core feature note: `https://langfuse.com/self-hosting/license-key`
- instrumentation: `https://langfuse.com/docs/observability/sdk/instrumentation`
- OTEL endpoint: `https://langfuse.com/integrations/native/opentelemetry`
- sessions: `https://langfuse.com/docs/observability/features/sessions`

### 7.2 What Langfuse Does

Langfuse is used for:

- end-to-end traces
- worker latency
- LLM call timing and metadata
- retry visibility
- stage-by-stage progress
- human verification that each incremental phase is alive on the VPS

Langfuse is not used for:

- queueing
- leases
- retries
- idempotency
- authoritative state

### 7.3 Trace Structure

Recommended structure:

- one Langfuse `session_id` per canonical job: `job:<job_id>`
- one trace per claimed `work_item`
- child observations for:
  - Mongo claim
  - scrape/search HTTP calls
  - dedupe/selection logic
  - Claude CLI calls
  - Codex CLI calls
  - validation
  - enqueue-next-task

For early search hits before a canonical job exists:

- use `session_id = hit:<source>:<external_job_id>`
- when the hit is merged into a canonical job, write the canonical session ID to the job and link the old correlation ID in metadata

### 7.4 Instrumentation Point

The instrumentation point is the Python wrapper layer, not the CLI binaries.

Primary targets:

- `src/common/claude_cli.py`
- `src/common/codex_cli.py`
- shared worker claim/complete code

Secondary cleanup target:

- direct `subprocess.run(...)` Codex/Claude call sites in skills and scripts must be migrated to the shared traced wrappers if the goal is full Langfuse coverage across all skill calls

### 7.5 Implementation Choice

Use the Langfuse Python SDK first.

Why:

- it supports `@observe()` and manual observations directly
- it is easier to introduce incrementally inside the existing Python wrappers
- it is enough for the current repo, which is Python-heavy

OTEL export to Langfuse remains a later option if cross-language instrumentation becomes necessary. Langfuse supports OTLP over HTTP on `/api/public/otel`.

---

## 8. Behavior-Driven Rollout

Each phase has one requirement: it is not complete until the user can see that phase working in Langfuse on the VPS.

### Phase 0. VPS Foundation And Langfuse

Goal:

- make the VPS ready for runnerless workers
- bring up Langfuse internally
- prove a traced host-side Python process reaches Langfuse

Implementation:

- create Docker Compose deployment for Langfuse on the VPS
- create Langfuse project and API keys
- add Langfuse env vars to `/root/scout-cron/.env`
- add a tiny traced smoke script in the repo
- add swap on the VPS
- define `systemd` unit template skeletons for workers

BDD:

- Given Langfuse Docker services are up on the VPS
- When `python -m scripts.langfuse_smoke_test` runs on the host
- Then a trace appears in Langfuse with one root span and one child observation

Gate:

- no pipeline work starts until host-to-Langfuse tracing is visible

### Phase 1. Shared Mongo Queue Library

Goal:

- introduce `work_items`, leases, retries, and round-robin claiming without changing scout behavior yet

Implementation:

- add shared queue models and helpers under `src/pipeline/`
- add `queue_state` lane cursor logic
- add queue indexes migration
- add worker skeleton that claims synthetic tasks and marks them done

BDD:

- Given pending synthetic tasks in `search`, `scrape`, and `selector`
- When two worker ticks run
- Then the claim order follows the round-robin lane cursor instead of draining a single lane

- Given a worker crashes after claiming a task
- When the lease expires
- Then a second worker can reclaim that task safely

Gate:

- synthetic work-item traces are visible in Langfuse with lane metadata and lease timing

### Phase 2. Search Writes To Mongo, Not JSONL

Goal:

- replace `queue.jsonl` creation with Mongo discovery documents and scrape work items

Implementation:

- refactor `n8n/skills/scout-jobs/scripts/scout_linkedin_cron.py`
- replace `enqueue_jobs(...)` usage from `n8n/skills/scout-jobs/src/common/scout_queue.py`
- write raw discoveries into `scout_search_hits`
- enqueue `scrape.hit` work items
- keep old JSONL path behind a temporary rollback flag during this phase only

BDD:

- Given a scheduled search task for profile `ai` and region `remote`
- When the search skill runs
- Then raw discoveries are written to `scout_search_hits`
- And matching `scrape.hit` work items are created
- And no new `queue.jsonl` entries are required for the new path

Gate:

- Langfuse shows search traces with counts for discovered hits and enqueued scrape items

### Phase 3. Scrape, Dedupe, And Canonical Job Upsert

Goal:

- turn raw hits into canonical jobs
- prevent repeated scraping of the same fresh job

Implementation:

- refactor `scout_scraper_cron.py` into a queue-driven handler
- add scrape freshness fields to `scout_search_hits`
- upsert into `jobs`
- add `dedupe.merge` step or fold merge into scrape completion if simpler
- create `select.job` work items only for canonical jobs that pass freshness and merge checks

BDD:

- Given two search hits that point to the same job
- When scrape and dedupe run
- Then one canonical `jobs` document exists
- And both hits link to it
- And duplicate future scrape scheduling is suppressed while freshness is valid

- Given a scrape fails transiently
- When retry budget is not exhausted
- Then the `work_item` returns to `pending` with a future `available_at`

Gate:

- Langfuse shows scrape traces, merge traces, and one canonical job lineage per deduped job

### Phase 4. Selector Moves Fully Onto Mongo Work Items

Goal:

- make selector read canonical jobs and enqueue the first preenrich task

Implementation:

- refactor `scout_selector_cron.py` to read from Mongo instead of `scored.jsonl`
- retire direct runner queueing logic
- replace `SELECTOR_ENQUEUE_VIA_WORKER` with the new default path
- selector marks jobs `selected`
- selector enqueues the first preenrich `work_item`

BDD:

- Given a canonical job that passes selection thresholds
- When the selector skill runs
- Then `jobs.lifecycle` becomes `selected`
- And a preenrich work item is created
- And no runner HTTP queue call occurs

Gate:

- Langfuse shows selector decisions, reasons, and downstream preenrich enqueue events

### Phase 5. Pre-Enrichment Skill Lane

Goal:

- move pre-CV enrichment into queue-driven host workers with atomic stage persistence

Detailed rollout plan:

- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`

Iteration note:

- the first production-ready slice of phase 5 now stops at `lifecycle="cv_ready"`
- native CV generation, review, and publish are intentionally deferred to later iterations/phases
- `ready_for_cv` should be treated as a legacy transitional label during migration, not the new target state

Implementation:

- build on existing `src/preenrich/`
- adapt it from direct `level-2.lifecycle` claims to `work_items`
- stages:
  - `preenrich.jd_structure`
  - `preenrich.jd_extraction`
  - `preenrich.ai_classification`
  - `preenrich.pain_points`
  - `preenrich.annotations`
  - `preenrich.persona`
  - `preenrich.company_research`
  - `preenrich.role_research`
  - optional `preenrich.fit_signal`
- each stage writes outputs atomically and enqueues the next stage
- when the final required stage completes, set `jobs.lifecycle="cv_ready"`
- later phases create `cv.generate` from the `cv_ready` boundary

BDD:

- Given a selected job with description text
- When the preenrich worker claims `preenrich.jd_structure`
- Then the stage output and stage status are written atomically
- And the next stage work item is created exactly once

- Given a Codex invocation fails because auth is unavailable or output is invalid
- When fallback policy allows Claude
- Then the failure is recorded
- And the fallback provider run is traced in Langfuse under the same session

Gate:

- Langfuse shows one visible trace per preenrich stage with model/provider metadata

### Phase 6. CV Generation Skill Lane

Goal:

- replace runner-owned CV generation with a host-side queue-driven CV worker

Implementation:

- extract the CV-generation entrypoint from the runner-owned path into a host-safe service layer
- create `cv.generate` work item handler
- keep generated artifact metadata on `jobs.cv`
- write attempt details to `job_runs`
- enqueue `cv.score`

BDD:

- Given a job with `jobs.lifecycle="cv_ready"`
- When the CV worker claims `cv.generate`
- Then a CV artifact is produced or recorded
- And `jobs.lifecycle` becomes `reviewing`
- And `cv.score` is queued

Gate:

- Langfuse shows generation traces for the actual VPS-host CV worker, not a runner container

### Phase 7. Scoring And Review Skill Lane

Goal:

- run CV scoring and review on the VPS as queue workers

Implementation:

- turn current CV review logic into queue handlers
- refactor direct Codex subprocess usage to the shared traced wrapper
- add `cv.score` and `cv.review` task types
- persist structured results on `jobs.review`

BDD:

- Given a generated CV exists for a job
- When `cv.score` and `cv.review` run
- Then structured verdicts, issues, and scores are persisted
- And both calls are visible in Langfuse

Gate:

- Langfuse shows end-to-end job sessions from selection through review

### Phase 8. Publish Lane

Goal:

- make publish side effects explicit and retryable

Implementation:

- create `publish.upload` and any downstream notification tasks
- persist artifact refs and publish state in Mongo
- use `work_items` as the outbox for external side effects

BDD:

- Given a reviewed CV is approved for publish
- When `publish.upload` runs
- Then output metadata is persisted
- And failure/retry state is captured in Mongo and Langfuse

Gate:

- publish traces are visible in Langfuse and recoverable without manual ad hoc reruns

### Phase 9. Cutover And Decommission

Goal:

- remove obsolete file-queue and runner coupling

Implementation:

- remove JSONL queue dependency from `scout_queue.py`
- remove runner queueing from selector-related scripts
- remove runner-specific operational docs for this pipeline path
- archive or migrate old `/var/lib/scout/*.jsonl` state for audit only

BDD:

- Given the new Mongo pipeline is live
- When the old cron path is disabled
- Then the full search-to-review pipeline still executes on the VPS
- And all stages remain visible in Langfuse

Gate:

- no active production dependency remains on runners or JSONL files

---

## 9. VPS Deployment Flow

### 9.1 Code Deploy

Use a normal full-checkout deploy on the VPS:

- `git pull` in `/root/scout-cron/`
- or `rsync` the repo into `/root/scout-cron/`

Do not deploy a curated source subset for this architecture.

### 9.2 Python Environment

Use one shared venv:

- `/root/scout-cron/.venv`

All worker services should use that venv so wrapper behavior, imports, and auth assumptions stay consistent.

### 9.3 Systemd Reload Flow

Deployment sequence:

1. sync code to `/root/scout-cron/`
2. update `.env`
3. install or update worker unit files
4. `systemctl daemon-reload`
5. restart changed workers
6. watch Langfuse and journald for the current phase gate

### 9.4 Langfuse Deploy Flow

Keep Langfuse compose separate from worker services.

Recommended path:

- `/root/langfuse/`

Deployment sequence:

1. place Docker Compose file and `.env`
2. `docker compose up -d`
3. create project/API keys
4. inject keys into `/root/scout-cron/.env`
5. run host smoke trace

---

## 10. Implementation Areas In This Repo

Likely change areas:

- `n8n/skills/scout-jobs/src/common/scout_queue.py`
- `n8n/skills/scout-jobs/scripts/scout_linkedin_cron.py`
- `n8n/skills/scout-jobs/scripts/scout_scraper_cron.py`
- `n8n/skills/scout-jobs/scripts/scout_selector_cron.py`
- `src/preenrich/`
- `src/common/claude_cli.py`
- `src/common/codex_cli.py`
- `n8n/skills/cv-review/scripts/bulk_review.py`
- new shared queue and worker code under `src/pipeline/`
- deploy assets for `systemd` units and Langfuse compose

Companion docs that should later be updated once implementation starts:

- `plans/scout-pre-enrichment-skills-plan.md`
- `plans/cv-pipeline-overhaul.md`
- `docs/current/architecture.md`
- `missing.md`

---

## 11. Acceptance Criteria

The plan is complete only when all of these are true:

- search, scrape, selector, preenrich, CV generation, scoring, review, and publish all run on the VPS host without runners
- every stage claims from Mongo `work_items`
- JSONL files are no longer the active orchestration boundary
- Codex-authenticated workers run only on the host and survive refresh-token usage
- one canonical `jobs` document is maintained per deduped job
- retries and deadletters are visible in Mongo
- Langfuse shows every phase incrementally as it is enabled
- the user can open Langfuse and watch a real job move from search discovery to CV review

---

## 12. Risks And Mitigations

### Risk: direct CLI subprocess calls bypass tracing

Mitigation:

- standardize Claude/Codex invocation through shared wrappers before calling the phase complete

### Risk: one overloaded lane starves the rest

Mitigation:

- enforce one-claim-per-tick and lane-cursor round robin
- add per-lane concurrency caps

### Risk: Codex auth drift on the host

Mitigation:

- keep workers under one persistent user
- expose auth health in worker startup diagnostics
- trace auth failures explicitly in Langfuse

### Risk: the VPS is memory-constrained

Mitigation:

- remove runners
- add swap
- start with conservative worker counts
- cap `systemd` resource usage

### Risk: phased migration leaves both JSONL and Mongo paths active too long

Mitigation:

- explicit phase gates
- short rollback flags only during migration
- one final cutover phase that deletes the old boundary

---

## 13. Recommendation

Build this in the exact phase order above.

Do not start with CV generation migration first. The correct order is:

1. Langfuse visibility
2. Mongo queue primitives
3. search to Mongo
4. scrape and dedupe
5. selector
6. preenrich
7. CV generation
8. score/review
9. publish
10. decommission old paths

That ordering gives the cleanest feedback loop on the VPS and keeps the architecture coherent from day one.

---

## 14. First Implementation Slice

The first slice should be intentionally narrow:

- bring up Langfuse on the VPS
- add traced queue helpers and synthetic workers
- migrate search discovery to `scout_search_hits`
- enqueue `scrape.hit` into `work_items`

Why this slice first:

- it proves observability before deeper refactors
- it removes the first JSONL boundary early
- it creates the queue contract the rest of the pipeline can build on

Success for the first slice means:

- a real search task runs on the VPS
- Langfuse shows the trace
- `scout_search_hits` receives documents
- `work_items` receives `scrape.hit`
- no runner is involved
