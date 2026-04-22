# Iteration 1 Plan: Search Discovery, Mongo Queue Foundation, Legacy Scrape Handoff, And Debug UI

Author: Codex planning pass on 2026-04-18  
Parent plan: `plans/runnerless-vps-mongo-skill-pipeline.md`  
Status: marked done on 2026-04-18 for planning purposes; implementation prompt for iteration 2 follows next

## 0. What Changed In This Revision

The previous iteration-1 draft had real gaps. This revision closes them.

### Critical Blackholes Found

1. **Downstream blackhole**  
   The previous draft moved search from `queue.jsonl` to Mongo while keeping scraper out of scope. That would have starved the current scraper and broken the live pipeline immediately after search.

2. **Data-plane blackhole**  
   The previous draft assumed the Vercel UI would read the same Mongo data plane as the VPS workers, but it did not define how that would be configured without risking the existing Atlas-backed frontend behavior.

3. **Trace-link blackhole**  
   The previous draft mentioned Langfuse links but did not define how correlation IDs, run IDs, and Langfuse session IDs would actually be created and persisted so traces could be found reliably later.

4. **Observability blackhole**  
   The previous draft had no run-level collection for search executions, so the UI could show hits and queue rows but not “what just ran”, “what failed”, or “when the last search finished”.

5. **State semantics blackhole**  
   The previous draft risked showing `done` or “advanced” states without clarifying whether that meant “handed off to the current legacy scraper” versus “actually scraped”. That would make the debug UI misleading.

6. **Over-scoping blackhole**  
   The previous draft pulled in `queue_state` and round-robin cursor logic even though iteration 1 only activates one real next-stage lane. That adds complexity without producing user value in the first slice.

### Changes In This Revision

- Search remains on its existing cron schedule in iteration 1.
- Search writes to Mongo first, then a temporary **legacy scrape handoff bridge** mirrors the new Mongo work into the existing `queue.jsonl` path.
- `search_runs` is added so the UI can show actual run summaries and errors.
- The frontend gets a dedicated discovery repository and an explicit Mongo URI precedence instead of silently reusing whichever `MONGODB_URI` happens to exist.
- Langfuse tracing gets an explicit ID contract.
- Round-robin cursor logic is deferred to iteration 2. Iteration 1 only needs queue primitives, leases, and one real compatibility consumer.

---

## 1. Iteration 1 Contract

Iteration 1 is the first **safe** production slice of the runnerless architecture.

It does four things:

1. Deploy Langfuse independently on the VPS and prove browser-visible tracing.
2. Make search discovery write to Mongo (`scout_search_hits`, `search_runs`, `work_items`).
3. Preserve the current scraper by bridging Mongo work into legacy `queue.jsonl`.
4. Add a Vercel discovery/debug page that shows discovery state, queue state, and optional links or IDs for Langfuse.

It does **not** migrate scrape itself yet.

---

## 2. Definition Of Done

Iteration 1 is done only when all of these are true:

- a real search cron run on the VPS writes discovery hits to Mongo
- a real search cron run creates Mongo work items for the next stage
- a compatibility bridge mirrors those work items into `queue.jsonl` for the existing scraper
- the current scraper continues to receive new jobs after cutover
- a browser-visible Langfuse instance shows the search traces
- the Vercel frontend shows:
  - recent search runs
  - discovered hits
  - queue / handoff state
  - correlation or session IDs
  - optional external Langfuse links

If search writes to Mongo but the current scraper stops getting work, iteration 1 is **not** complete.

---

## 3. Scope

### In Scope

- self-hosted Langfuse on the VPS
- `search_runs`
- `scout_search_hits`
- `work_items`
- queue lease primitives
- search-to-Mongo write path
- temporary legacy scrape handoff bridge
- Vercel discovery/debug page

### Explicitly Out Of Scope

- native scrape worker migration
- selector migration
- preenrichment migration
- CV generation, scoring, review, publish
- full round-robin scheduling
- removal of `queue.jsonl`

`queue.jsonl` remains temporarily alive in iteration 1 as a compatibility boundary.

---

## 4. Architectural Decision For Iteration 1

### 4.1 Search Keeps Its Existing Cron Trigger

Do not turn search into a new long-running worker in iteration 1.

Keep:

- existing VPS cron execution model
- existing `scout_linkedin_cron.py` entrypoint

Change:

- what search writes

This reduces moving parts in the first slice.

### 4.2 Mongo Is The New Authoritative Discovery Boundary

Search discovery becomes Mongo-authoritative immediately.

Search no longer owns `queue.jsonl` directly. Instead:

```text
search cron
  -> write search_runs
  -> upsert scout_search_hits
  -> enqueue work_items(task_type=scrape.hit, consumer_mode=legacy_jsonl)
  -> legacy handoff bridge
  -> queue.jsonl
  -> existing scraper cron
```

### 4.3 Legacy Bridge Is Required

The bridge is not optional.

Without it, iteration 1 creates a dead-end queue.

### 4.4 Langfuse Is Independent

Langfuse runs separately on the VPS.

The Vercel UI:

- reads Mongo
- displays IDs and links
- does not proxy, host, or embed Langfuse

---

## 5. Data Model

### 5.1 `search_runs`

Purpose:

- run-level visibility for the UI and operations

Suggested shape:

```json
{
  "_id": "ObjectId",
  "run_id": "searchrun:2026-04-18T10:00:00Z:abc123",
  "trigger_mode": "cron|manual",
  "command_mode": "full|direct",
  "region_filter": "eea|null",
  "profile_filter": "ai|null",
  "time_filter": "r43200",
  "status": "running|completed|failed",
  "started_at": "ISODate",
  "completed_at": "ISODate|null",
  "stats": {
    "raw_found": 0,
    "after_blacklist": 0,
    "after_db_dedupe": 0,
    "hits_upserted": 0,
    "work_items_created": 0,
    "legacy_handoffs_created": 0
  },
  "errors": [],
  "langfuse_session_id": "searchrun:2026-04-18T10:00:00Z:abc123",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Indexes:

- unique: `run_id`
- query: `started_at`
- query: `status + started_at`

### 5.2 `scout_search_hits`

Purpose:

- raw discoveries before scrape
- primary UI dataset

Suggested shape:

```json
{
  "_id": "ObjectId",
  "source": "linkedin",
  "external_job_id": "1234567890",
  "canonical_url": "https://www.linkedin.com/jobs/view/1234567890/",
  "canonical_url_hash": "sha256:...",
  "title": "Senior AI Engineer",
  "company": "Example Corp",
  "location": "Remote",
  "job_url": "https://www.linkedin.com/jobs/view/1234567890/",
  "search_profile": "ai",
  "search_region": "eea",
  "source_cron": "hourly",
  "run_id": "searchrun:...",
  "correlation_id": "hit:linkedin:1234567890",
  "langfuse_session_id": "hit:linkedin:1234567890",
  "hit_status": "discovered|queued_for_scrape|handed_to_legacy_scraper|duplicate_seen|discarded|failed",
  "times_seen": 1,
  "first_seen_at": "ISODate",
  "last_seen_at": "ISODate",
  "last_queued_at": "ISODate|null",
  "last_legacy_handoff_at": "ISODate|null",
  "scout_metadata": {},
  "raw_search_payload": {},
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Indexes:

- unique: `source + external_job_id`
- unique sparse: `canonical_url_hash`
- query: `hit_status + last_seen_at`
- query: `run_id`
- query: `correlation_id`

Important behavior:

- repeated discovery of the same hit must **upsert** and update `last_seen_at`
- repeated discovery must **not** create duplicate work items if a pending or in-flight next-stage item already exists

### 5.3 `work_items`

Iteration 1 keeps the full collection name but a reduced feature set.

Suggested shape:

```json
{
  "_id": "ObjectId",
  "task_type": "scrape.hit",
  "lane": "scrape",
  "consumer_mode": "legacy_jsonl",
  "subject_type": "search_hit",
  "subject_id": "ObjectId",
  "status": "pending|leased|done|failed|deadletter",
  "priority": 100,
  "available_at": "ISODate",
  "lease_owner": null,
  "lease_expires_at": null,
  "attempt_count": 0,
  "max_attempts": 5,
  "idempotency_key": "sha256:source:external_job_id:scrape.hit",
  "correlation_id": "hit:linkedin:1234567890",
  "payload": {
    "job_id": "1234567890",
    "title": "...",
    "company": "...",
    "location": "...",
    "job_url": "...",
    "search_profile": "ai",
    "source_cron": "hourly"
  },
  "result_ref": {
    "legacy_queue_written": false,
    "legacy_queue_written_at": null
  },
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Indexes:

- unique: `idempotency_key`
- query: `status + lane + available_at`
- query: `subject_type + subject_id`
- query: `correlation_id`

Important meaning:

- in iteration 1, `done` on `scrape.hit` means **handed off to legacy queue**, not **scrape finished**

This distinction must be visible in the UI.

### 5.4 `queue_state`

Defer `queue_state` and round-robin cursor logic to iteration 2.

Reason:

- only one real lane is active in iteration 1
- queue cursor logic adds complexity without protecting the first slice

Keep the `lane` field in `work_items` so the collection stays forward-compatible.

---

## 6. Trace And ID Contract

This is required, not optional.

### 6.1 IDs

- one `run_id` per search cron invocation
- one `correlation_id` per hit
- one `langfuse_session_id` persisted per run and per hit

Recommended values:

- `run_id = searchrun:<iso-start>:<short-uuid>`
- `correlation_id = hit:linkedin:<external_job_id>`
- `langfuse_session_id = correlation_id` for hit-level traces

### 6.2 Langfuse Structure

- root observation for the whole search run
- child spans per search combo / region / profile
- child observations for each new or updated hit
- child observations for work-item enqueue
- child observations for legacy queue handoff

### 6.3 Persistence Rule

The same session/correlation identifiers used in Langfuse must be persisted to Mongo before the run completes.

Without that, UI-to-trace navigation becomes guesswork.

---

## 7. Step-By-Step Execution Plan

### Step 1. Decide The Discovery Data Plane

Goal:

- make the UI read the correct Mongo source without risking unrelated frontend data

Decision:

- add a dedicated env precedence for the discovery UI repository:
  - `DISCOVERY_MONGODB_URI`
  - else `VPS_MONGODB_URI`
  - else `MONGODB_URI`

Why:

- current frontend repository code is Atlas-oriented
- global `MONGODB_URI` changes could have wider effects

Deliverables:

- documented env precedence
- one new dedicated discovery repository in `frontend/repositories/discovery_repository.py`

### Step 2. Deploy Langfuse On The VPS

Goal:

- make observability independently available before data migration work begins

Deliverables:

- Langfuse Docker Compose on the VPS
- HTTPS hostname
- worker env vars configured
- smoke trace script from host Python

Required env vars for VPS workers:

- `LANGFUSE_HOST`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

Optional env var for Vercel:

- `LANGFUSE_PUBLIC_URL`

Verification:

- open Langfuse in browser
- run smoke trace
- confirm trace exists

### Step 3. Add Search Run Logging

Goal:

- get operational visibility before changing the search data path

Create:

- helper for creating / updating `search_runs`

Modify:

- `n8n/skills/scout-jobs/scripts/scout_linkedin_cron.py`

Behavior:

- create `search_runs` doc at start
- update status and stats during execution
- mark `completed` or `failed` on exit

Verification:

- one real cron run creates one `search_runs` document

### Step 4. Add Queue Primitives

Goal:

- add idempotent work-item creation and lease logic

Create:

- `src/pipeline/queue.py`
- `src/pipeline/lease.py`
- `src/pipeline/tracing.py`

Keep iteration 1 minimal:

- enqueue idempotently
- claim with lease
- heartbeat
- mark done/failed/deadletter

Do not implement:

- round-robin cursor
- multi-lane balancing logic

Verification:

- unit tests for:
  - idempotent enqueue
  - lease expiry
  - retry/backoff

### Step 5. Add The Legacy Scrape Handoff Bridge

Goal:

- preserve the current scraper without keeping search bound to JSONL

Create:

- one temporary host-side bridge worker, for example:
  - `src/pipeline/legacy_scrape_handoff.py`

Suggested runtime:

- `systemd` service or short-interval cron tick on VPS

Behavior:

1. claim `work_items` where:
   - `task_type = scrape.hit`
   - `consumer_mode = legacy_jsonl`
   - `status = pending`
2. materialize queue entries into the existing `queue.jsonl`
3. update:
   - `work_items.status = done`
   - `work_items.result_ref.legacy_queue_written = true`
   - `work_items.result_ref.legacy_queue_written_at = now`
   - `scout_search_hits.hit_status = handed_to_legacy_scraper`
   - `scout_search_hits.last_legacy_handoff_at = now`

Implementation detail:

- reuse or wrap the existing `scout_queue.py` write path instead of re-implementing JSONL formatting from scratch

Verification:

- a pending `scrape.hit` item appears in `queue.jsonl`
- current scraper still picks it up

### Step 6. Migrate Search Writes To Mongo

Goal:

- make search produce Mongo-authoritative discovery state

Primary file:

- `n8n/skills/scout-jobs/scripts/scout_linkedin_cron.py`

Key changes:

- stop calling `enqueue_jobs(...)` directly from search
- upsert `scout_search_hits`
- create `work_items(task_type=scrape.hit, consumer_mode=legacy_jsonl)`
- update `search_runs`
- emit Langfuse traces using the persisted IDs

Important behavior:

- repeated rediscovery updates `last_seen_at`
- new queue item is only created when there is no active matching next-stage work item

Temporary flags:

- `SCOUT_WRITE_SEARCH_HITS_TO_MONGO=true`
- `SCOUT_ENQUEUE_WORK_ITEMS=true`
- `SCOUT_ENABLE_LEGACY_SCRAPE_HANDOFF=true`
- `SCOUT_DIRECT_JSONL_ENQUEUE=false`

Verification:

- search run writes Mongo hits
- work items are created
- bridge mirrors to JSONL
- scraper still processes new jobs

### Step 7. Build The Vercel Discovery Repository

Goal:

- isolate discovery page data access from the rest of the frontend

Create:

- `frontend/repositories/discovery_repository.py`

Required methods:

- `get_run_stats(since)`
- `get_recent_runs(limit)`
- `get_hits(filters, page, per_page)`
- `get_hit_detail(hit_id)`
- `get_related_work_items(hit_id)`
- `get_queue_snapshot()`
- `get_recent_failures(limit)`

Performance rule:

- use field projections for list views
- do not return full `raw_search_payload` in the main table

### Step 8. Build The Discovery UI

Goal:

- make the first slice visible in the browser

Routes to add under existing `/dashboard` blueprint:

- `GET /dashboard/discovery`
- `GET /dashboard/discovery/stats`
- `GET /dashboard/discovery/rows`
- `GET /dashboard/discovery/runs`
- `GET /dashboard/discovery/<hit_id>`
- `GET /dashboard/discovery/queue`

Templates to add:

- `frontend/templates/intel_discovery.html`
- `frontend/templates/partials/intel/discovery_stat_cards.html`
- `frontend/templates/partials/intel/discovery_table.html`
- `frontend/templates/partials/intel/discovery_run_list.html`
- `frontend/templates/partials/intel/discovery_detail.html`
- `frontend/templates/partials/intel/discovery_queue_panel.html`

Navigation change:

- add `Discovery` beside the existing `/dashboard`, `/dashboard/opportunities`, `/dashboard/drafts` navigation family

### Step 9. Make The UI Semantically Honest

Goal:

- avoid misleading status labels

The discovery page must not present “done” as “scraped”.

Recommended per-hit pipeline chips:

- `Discovered`
- `Queued`
- `Legacy Handoff`
- `Scraped`
- `Selected`
- `Preenrich`
- `CV`
- `Review`

Iteration 1 rules:

- first three may be live
- later stages must be greyed or marked “not yet migrated”

This gives a useful future-facing visual without lying about current stage coverage.

### Step 10. Add Optional Langfuse Links

Goal:

- give the operator a straight path from UI row to observability

If `LANGFUSE_PUBLIC_URL` is configured:

- show a global `Open Langfuse` link
- show copyable `langfuse_session_id`
- show copyable `correlation_id`
- optionally add deep links if the deployed Langfuse URL shape is confirmed

Do not block page render if this URL is missing.

### Step 11. Add Tests

Backend tests:

- search run doc created and finalized
- existing hit upsert updates `last_seen_at` and `times_seen`
- duplicate enqueue prevented by idempotency key
- legacy bridge writes one queue entry exactly once
- failed bridge attempts retry correctly

Frontend tests:

- `/dashboard/discovery` page renders with mocked repository
- stats partial renders
- rows partial renders
- detail modal renders
- empty-state and error-state render cleanly

Deployment smoke tests:

- real search run on VPS
- real queue handoff to JSONL
- real scraper still receives new work
- Langfuse trace visible
- Vercel page visible

---

## 8. UI Design And Debug Surface

### 8.1 Top Stat Cards

Show:

- search runs in last 24h
- discoveries last 24h
- pending handoffs
- handoffs completed
- failures / deadletters

### 8.2 Main Table

Columns:

- discovery status
- pipeline chips
- title
- company
- location
- profile
- region
- last seen
- queue state
- correlation ID
- actions

### 8.3 Right Rail

Show:

- last search runs
- queue snapshot
- recent failures
- Langfuse panel

### 8.4 Detail Modal

Show:

- key hit fields
- run ID
- correlation ID
- Langfuse session ID
- related work item
- raw payload excerpt
- timestamps

---

## 9. File-Level Change List

### Search / Queue

- `n8n/skills/scout-jobs/scripts/scout_linkedin_cron.py`
- `n8n/skills/scout-jobs/src/common/scout_queue.py`
- `src/pipeline/queue.py`
- `src/pipeline/lease.py`
- `src/pipeline/tracing.py`
- `src/pipeline/legacy_scrape_handoff.py`

### Frontend

- `frontend/intel_dashboard.py`
- `frontend/repositories/discovery_repository.py`
- `frontend/templates/base.html`
- `frontend/templates/intel_discovery.html`
- `frontend/templates/partials/intel/discovery_stat_cards.html`
- `frontend/templates/partials/intel/discovery_table.html`
- `frontend/templates/partials/intel/discovery_run_list.html`
- `frontend/templates/partials/intel/discovery_detail.html`
- `frontend/templates/partials/intel/discovery_queue_panel.html`

### Tests

- backend queue/search tests
- frontend dashboard route tests

---

## 10. Deploy Plan

### 10.1 Pre-Deploy

1. snapshot `/var/lib/scout/queue.jsonl`
2. confirm current scraper is healthy
3. confirm Mongo indexes can be created
4. deploy Langfuse first

### 10.2 Deploy Sequence

1. deploy Langfuse
2. deploy queue helpers and bridge worker
3. deploy search script changes with flags off
4. enable:
   - `SCOUT_WRITE_SEARCH_HITS_TO_MONGO=true`
   - `SCOUT_ENQUEUE_WORK_ITEMS=true`
   - `SCOUT_ENABLE_LEGACY_SCRAPE_HANDOFF=true`
5. disable:
   - `SCOUT_DIRECT_JSONL_ENQUEUE`
6. run one controlled search pass
7. verify Mongo, JSONL handoff, scraper, Langfuse
8. deploy Vercel discovery page

### 10.3 Rollback

If iteration 1 fails:

1. disable Mongo work-item enqueue flags
2. re-enable direct JSONL enqueue in search
3. stop the bridge worker
4. leave Langfuse and read-only UI in place if harmless

Rollback must restore live search-to-scraper flow within minutes.

---

## 11. Acceptance Checklist

- `search_runs` exists and records real cron executions
- `scout_search_hits` exists and upserts correctly
- `work_items` exists and is idempotent
- legacy bridge mirrors work into `queue.jsonl`
- current scraper still receives jobs
- Langfuse is independently viewable in a browser
- Vercel `/dashboard/discovery` renders real data
- UI statuses are explicit about “legacy handoff” vs “scraped”
- optional Langfuse links or copyable IDs are present

---

## 12. Non-Goals To Protect Iteration 1

Do not expand iteration 1 to include:

- native scrape worker
- full round-robin logic
- selector integration
- preenrichment
- CV generation
- deleting JSONL

That is the work of iteration 2 and later.

Iteration 1 succeeds if it creates the first Mongo queue boundary, keeps the current pipeline alive through a temporary bridge, and makes the new boundary visible in both the Vercel UI and Langfuse.
