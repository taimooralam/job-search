# Iteration 2 Plan: Mongo-Native Scrape Execution With Selector Compatibility

Author: Codex planning pass on 2026-04-18  
Parent plans:
- `plans/runnerless-vps-mongo-skill-pipeline.md`
- `plans/iteration-1-discovery-ui-langfuse.md`

Status: saved; external Claude Opus review blocked because `CLAUDE_CODE_OAUTH_TOKEN` is empty in repo `.env`

## 0. Objective

Iteration 2 replaces the temporary legacy scrape handoff introduced in iteration 1 with a Mongo-native scrape worker.

The scrape stage becomes Mongo-driven, but the selector remains unchanged for this iteration.

That means iteration 2 must deliver all of the following at once:

- `scrape.hit` is consumed natively from Mongo `work_items`
- scrape results are written back to Mongo with honest state transitions
- the current selector continues to receive selector-compatible scored payloads through `scored.jsonl`
- `level-1` staging remains intact
- the discovery/debug UI shows true scrape completion rather than only legacy handoff
- rollback to the legacy JSONL-driven scraper remains possible by flags

This is the next critical slice because it removes the first major compatibility bridge while still protecting the downstream selector boundary.

---

## 1. What Iteration 2 Changes

### Before Iteration 2

```text
search cron
  -> scout_search_hits
  -> work_items(scrape.hit)
  -> legacy scrape handoff bridge
  -> queue.jsonl
  -> old scraper cron
  -> scored.jsonl + level-1
  -> current selector
```

### After Iteration 2

```text
search cron
  -> scout_search_hits
  -> work_items(scrape.hit)
  -> native scrape worker
  -> Mongo scrape state/results
  -> compatibility handoff to scored.jsonl + level-1
  -> current selector
```

### Explicit Non-Goal

Selector is not migrated in iteration 2.

If the native scrape worker succeeds but selector stops receiving compatible inputs, iteration 2 has failed.

---

## 2. Scope

### In Scope

- Mongo-native scrape worker
- scrape run tracking
- scrape state persisted to Mongo
- selector compatibility outputs:
  - `scored.jsonl`
  - `scored_pool.jsonl`
  - `level-1`
- Langfuse scrape traces
- discovery/debug UI updates for true scrape state
- rollout flags and rollback path

### Out Of Scope

- selector consuming Mongo directly
- selector lifecycle migration
- preenrich
- CV generation
- scoring / review / publish
- multi-lane round-robin scheduling beyond what scrape needs
- deletion of compatibility files in the first iteration-2 implementation pass

---

## 3. Critical Risks

### Risk 1: Selector Starvation

The selector still does:

- `read_and_clear_scored()`
- `append_to_pool(...)`
- level-1 / level-2 dedupe and promotion

Therefore iteration 2 must still produce:

- selector-compatible `scored.jsonl`
- selector-compatible `scored_pool.jsonl`
- selector-compatible level-1 rows

### Risk 2: Two Scrapers Running Against The Same Work

If the old scraper and the native scrape worker both execute live without a clear ownership split, the system will double-fetch, double-score, and potentially double-write selector inputs.

Mitigation:

- explicit flags
- narrow cutover path
- one source of scrape truth at a time for a given work item

### Risk 3: UI Semantics Drift

The page must distinguish:

- queued for scrape
- scrape in progress
- scrape succeeded
- selector handoff written
- selector handoff failed
- retry pending
- deadletter

“Scraped” and “selector-ready” are not the same thing.

### Risk 4: Scrape Logic Divergence

The current scraper is already the reference implementation for:

- blacklist skip
- title filter skip
- fetch
- parse
- score
- retry
- deadletter

Iteration 2 must reuse or extract this logic, not quietly fork it.

---

## 4. Contracts And State Model

### 4.1 `work_items` Contract

The search step from iteration 1 continues to create:

```json
{
  "task_type": "scrape.hit",
  "lane": "scrape",
  "consumer_mode": "native_scrape|legacy_jsonl",
  "subject_type": "search_hit",
  "subject_id": "ObjectId",
  "status": "pending|leased|done|failed|deadletter",
  "attempt_count": 0,
  "max_attempts": 5,
  "idempotency_key": "sha256:source:external_job_id:scrape.hit",
  "correlation_id": "hit:linkedin:<external_job_id>",
  "payload": {
    "job_id": "...",
    "title": "...",
    "company": "...",
    "location": "...",
    "job_url": "...",
    "search_profile": "...",
    "source_cron": "hourly"
  },
  "result_ref": {
    "scrape_status": null,
    "scored_jsonl_written": false,
    "scored_pool_written": false,
    "level1_upserted": false
  }
}
```

### State Semantics

- `pending` = available for native scrape
- `leased` = currently being scraped
- `done` = scrape complete and compatibility outputs successfully written
- `failed` = retryable failure
- `deadletter` = retries exhausted or non-recoverable

In iteration 2, `done` now means true scrape completion plus compatibility handoff, not just queue mirroring.

### 4.1.1 Work-Item State Transitions

Required transitions:

```text
pending
  -> leased
  -> done

pending
  -> leased
  -> failed
  -> pending   (after backoff)

pending
  -> leased
  -> deadletter
```

Additional invariant:

- `done` is allowed only if scrape execution succeeded and selector compatibility outputs succeeded
- if scrape execution succeeded but `scored.jsonl` or `level-1` write failed, the item must not transition to `done`

### 4.2 `scout_search_hits` Contract

Add a dedicated `scrape` subdocument.

Suggested shape:

```json
{
  "scrape": {
    "status": "pending|leased|skipped_blacklist|skipped_title_filter|succeeded|retry_pending|failed|deadletter",
    "attempt_count": 0,
    "last_attempt_at": "ISODate|null",
    "lease_owner": "string|null",
    "lease_expires_at": "ISODate|null",
    "completed_at": "ISODate|null",
    "last_error": {
      "type": "string|null",
      "message": "string|null"
    },
    "http_status": 200,
    "used_proxy": true,
    "score": 78,
    "tier": "A",
    "detected_role": "ai_engineer",
    "seniority_level": "senior",
    "employment_type": "full-time",
    "job_function": "engineering",
    "industries": ["software"],
    "scored_at": "ISODate|null",
    "selector_handoff_status": "pending|written|failed",
    "selector_handoff_at": "ISODate|null",
    "scored_pool_written_at": "ISODate|null",
    "level1_upserted_at": "ISODate|null"
  }
}
```

Important rule:

- `hit_status` remains useful for high-level discovery state
- `scrape.status` becomes the authoritative scrape-phase state

### 4.3 `scrape_runs`

Add a new run-level collection.

Suggested shape:

```json
{
  "_id": "ObjectId",
  "run_id": "scraperun:2026-04-18T10:05:00Z:abc123",
  "worker_id": "host-pid-uuid",
  "trigger_mode": "daemon|single_tick|manual",
  "status": "running|completed|failed",
  "started_at": "ISODate",
  "completed_at": "ISODate|null",
  "stats": {
    "claimed": 0,
    "skipped_blacklist": 0,
    "skipped_title_filter": 0,
    "scraped_success": 0,
    "retried": 0,
    "deadlettered": 0,
    "level1_upserts": 0,
    "scored_jsonl_writes": 0,
    "scored_pool_writes": 0
  },
  "errors": [],
  "langfuse_session_id": "scraperun:2026-04-18T10:05:00Z:abc123",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Purpose:

- operator visibility
- UI rendering
- Langfuse run-level correlation

---

## 5. Compatibility Boundary To Preserve

The selector still expects the existing scored payload shape.

Current selector reads:

- `scored.jsonl`
- then writes to `scored_pool.jsonl`
- then promotes to `level-2`
- and writes low-tier jobs to `level-1`

### Therefore Iteration 2 Must Preserve

1. **`scored.jsonl` format**
   The native worker must materialize scored entries with the same shape the selector expects today.

2. **`append_to_pool(...)` remains selector-owned**
   The selector currently calls this after dedupe. Iteration 2 must not move that responsibility upstream into the scrape worker.

3. **`level-1` staging**
   The native scrape worker must keep writing selector-compatible scored documents to `level-1`, matching current behavior as closely as possible.

4. **retry / deadletter semantics**
   Rate limits and scrape failures should still be retried and then dead-lettered after budget exhaustion.

### 5.1 Selector-Compatible Scored Payload Contract

The native scrape worker must emit the same payload shape the current selector expects from `scored.jsonl`.

At minimum preserve:

```json
{
  "job_id": "string",
  "title": "string",
  "company": "string",
  "location": "string",
  "job_url": "string",
  "score": 78,
  "tier": "A",
  "detected_role": "ai_engineer",
  "seniority_level": "senior",
  "is_target_role": true,
  "description": "string",
  "seniority": "string|null",
  "employment_type": "string|null",
  "job_function": "string|null",
  "industries": ["string"],
  "breakdown": {},
  "search_profile": "string",
  "source_cron": "string",
  "scored_at": "ISO8601"
}
```

Do not “improve” or rename this payload in iteration 2 unless the selector is updated in the same change and parity is preserved.

### 5.2 Important Consequence

Iteration 2 is not allowed to “clean up” `scored.jsonl` yet.

Removing `scored.jsonl` belongs to a later selector migration iteration.

---

## 6. Reuse Strategy

Do not write a second scrape/scoring implementation from scratch.

### Current Code To Reuse Or Extract

- `n8n/skills/scout-jobs/scripts/scout_scraper_cron.py`
- `scrape_and_score(...)`
- `_title_passes_filter(...)`
- `src.services.linkedin_scraper`
- `src.common.rule_scorer.compute_rule_score`
- existing blacklist helpers
- existing JSONL helpers from `src.common.scout_queue`

### Recommended Refactor

Extract shared logic into reusable functions or a small service module, then have:

- legacy scraper path call the shared code
- native scrape worker call the shared code

This keeps behavior aligned and makes parity testing possible.

### 6.1 Parity Harness Is Required

Before live cutover, add a parity check against a fixed corpus of queue entries / HTML fixtures.

The parity harness should compare legacy vs native outputs for:

- skip reason
- parsed title/company/location
- score
- tier
- detected role
- selector-compatible scored payload shape

The goal is not byte-identical timestamps. The goal is semantic parity on the fields the selector and level-1 staging depend on.

---

## 7. Rollout Flags

Use explicit flags so cutover and rollback are safe.

Recommended flags:

- `SCOUT_SCRAPE_ENABLE_NATIVE_WORKER`
- `SCOUT_SCRAPE_USE_MONGO_WORK_ITEMS`
- `SCOUT_SCRAPE_ENABLE_LEGACY_JSONL_CONSUMER`
- `SCOUT_SCRAPE_WRITE_SCORED_JSONL`
- `SCOUT_SCRAPE_WRITE_LEVEL1`
- `SCOUT_SCRAPE_SELECTOR_COMPAT_MODE`
- `SCOUT_SEARCH_SCRAPE_CONSUMER_MODE`
- `SCOUT_DISABLE_ITERATION1_LEGACY_HANDOFF_BRIDGE`

### 7.1 Ownership Matrix

Iteration 2 must make ownership explicit.

| Phase | Search output owner | Scrape executor | Selector input owner |
|------|----------------------|-----------------|----------------------|
| A | Search + iteration-1 bridge | Old scraper cron | Old scraper writes `scored.jsonl` |
| B | Search writes `work_items` | Native worker on test subset | Native worker writes compatibility `scored.jsonl` for test subset only |
| C | Search writes `work_items` with `consumer_mode=native_scrape` | Native worker | Native worker writes compatibility `scored.jsonl` |
| Rollback | Search + iteration-1 bridge or direct JSONL path | Old scraper cron | Old scraper |

No phase may allow two different live executors to own the same `scrape.hit` items.

### 7.2 Expected Phases

#### Phase A: Old Scraper Owns Production

- native worker deployed but disabled
- old scraper still consumes `queue.jsonl`

#### Phase B: Native Worker Dry / Shadow Validation

- native worker may process test or isolated items only
- compatibility outputs validated
- old scraper still owns production

#### Phase C: Native Worker Owns Scrape

- native worker enabled for live `work_items`
- search emits `consumer_mode=native_scrape`
- iteration-1 legacy handoff bridge disabled
- old scraper disabled or held as rollback only
- selector compatibility outputs still enabled

---

## 8. Step-By-Step Execution Plan

### Step 1. Define The Mongo Scrape Contract

Goal:

- lock the state model before implementation

Deliverables:

- final `scrape` subdocument shape on `scout_search_hits`
- final `scrape_runs` schema
- updated `work_items.result_ref` fields

Success criteria:

- every meaningful scrape transition has a durable Mongo field
- the UI can be built off this contract without guessing

### Step 2. Add `scrape_runs`

Goal:

- provide operational visibility before native execution becomes live

Work:

- create helper(s) for opening/updating/finalizing scrape runs
- persist run-level stats and errors

Success criteria:

- one worker loop or single-tick run creates one `scrape_runs` entry

### Step 3. Extract Shared Scrape Logic

Goal:

- avoid divergence between old and new paths

Work:

- identify the minimal shared unit around:
  - queue entry input
  - blacklist/title filter
  - fetch
  - parse
  - score
  - scored payload generation
- refactor into a shared function/module without changing output semantics

Success criteria:

- legacy scraper behavior is preserved
- native worker can call the same logic
- a parity harness can compare both code paths on the same fixtures

### Step 4. Build The Native Scrape Worker

Goal:

- consume `scrape.hit` from Mongo

Suggested file:

- `src/pipeline/scrape_worker.py`

Behavior:

1. claim one or a small bounded batch of `scrape.hit` work-items
2. create/update a `scrape_runs` record
3. set `scout_search_hits.scrape.status = leased`
4. run the shared scrape logic
5. update scrape results in Mongo
6. perform compatibility writes
7. mark work-item done or failed

Success criteria:

- a real queued hit can be scraped from Mongo without using `queue.jsonl` as input

### Step 5. Add Selector Compatibility Handoff

Goal:

- keep selector alive while scrape goes native

Compatibility outputs to write on successful scrape:

- `append_scored([scored])` to `scored.jsonl`
- `level-1.update_one(... upsert=True)` matching current semantics

Mongo state to update:

- `scrape.selector_handoff_status = written`
- `scrape.selector_handoff_at = now`
- `scrape.scored_jsonl_written_at = now`
- `scrape.level1_upserted_at = now`

Failure behavior:

- if scrape succeeded but compatibility write failed, do not mark the work-item `done`
- surface this as a failed handoff requiring retry

Success criteria:

- selector still receives live scored jobs after native scrape takes ownership

### Step 6. Add Retry And Deadletter Semantics

Goal:

- preserve current resilience behavior

Rules:

- rate limit => retry
- transient fetch/parse failures => bounded retry
- retries exhausted => deadletter
- deadletter status visible in both Mongo and Langfuse

Mongo updates:

- `scrape.status = retry_pending|deadletter`
- `scrape.last_error`
- `work_items.status = failed|deadletter`

Success criteria:

- retry and deadletter state is visible and testable

### Step 7. Add Langfuse Scrape Traces

Goal:

- make scrape execution observable independently from the UI

Trace structure:

- root observation for the scrape run
- child observations per claimed work-item
- child observations for:
  - blacklist skip
  - title filter skip
  - fetch attempt
  - parse
  - score
  - Mongo write
  - scored.jsonl write
  - level-1 upsert
  - retry / deadletter transition

Persist:

- `run_id`
- `correlation_id`
- `langfuse_session_id`

Success criteria:

- an operator can open Langfuse and see true scrape execution, not only discovery

### Step 8. Extend The Discovery/Debug UI

Goal:

- show true scrape state in the Vercel app

Required additions:

- scrape run list panel
- scrape success / retry / deadletter badges
- score / tier / detected role columns or detail fields
- selector compatibility handoff state
- last scrape error and attempt count in detail view

Important UI rule:

- “scraped” and “selector handoff written” must be separate indicators

Success criteria:

- the discovery page tells the truth about where each hit is in iteration 2

### Step 9. Add Tests

Backend tests:

- claim and lease `scrape.hit`
- blacklist skip path
- title filter skip path
- successful scrape + score
- successful scrape + `scored.jsonl` compatibility write
- successful scrape + `level-1` upsert
- retry on rate limit
- deadletter after retry exhaustion
- parity harness comparing legacy vs native outputs on a controlled fixture corpus

Frontend tests:

- discovery page renders scrape success state
- discovery page renders retry/deadletter state
- scrape runs panel renders
- detail modal shows scrape metadata

Success criteria:

- the new slice is test-covered at the boundary points that matter

### Step 10. Production Verification And Cutover

Goal:

- switch scrape ownership without breaking selector

Verification sequence:

1. queue a controlled set of hits
2. run native worker
3. verify Mongo scrape state updated
4. verify `scored.jsonl` received scored rows
5. verify `level-1` got scored upserts
6. verify selector consumed the output successfully
7. verify discovery page reflects true scrape completion
8. verify Langfuse traces exist
9. disable iteration-1 legacy handoff bridge only after native scrape ownership is verified

Success criteria:

- native scrape owns production behavior
- selector remains unchanged and healthy

---

## 9. Frontend Plan

### 9.1 Page Purpose In Iteration 2

The discovery page stops being only a “search discovered this” view.

It becomes:

- discovery state
- scrape execution state
- selector-compatibility handoff state

### 9.2 UI Additions

Add to list views:

- scrape status badge
- score
- tier
- detected role
- selector handoff badge

Add to detail view:

- attempt count
- last scrape error
- completed_at
- scored_jsonl_written_at
- level1_upserted_at

Add to right rail:

- recent scrape runs
- recent scrape failures / deadletters

### 9.3 Semantics

Recommended state chips:

- `Discovered`
- `Queued`
- `Leased`
- `Scraped`
- `Selector Handoff`
- `Selected`
- `Preenrich`
- `CV`
- `Review`

Only the first five are expected to be live in iteration 2.

---

## 10. File-Level Change List

### Backend / Worker

- `n8n/skills/scout-jobs/scripts/scout_scraper_cron.py`
- `src/pipeline/scrape_worker.py`
- `src/pipeline/queue.py`
- `src/pipeline/lease.py`
- shared scrape/scoring helper module if extracted

### Queue Compatibility

- `n8n/skills/scout-jobs/src/common/scout_queue.py`

### Frontend

- discovery repository and routes from iteration 1
- related templates for discovery page

### Tests

- scrape worker tests
- compatibility handoff tests
- frontend discovery tests

---

## 11. Deployment Plan

### 11.1 Pre-Deploy

1. confirm iteration-1 search discovery and Langfuse are healthy
2. confirm selector still currently consumes `scored.jsonl`
3. snapshot:
   - `/var/lib/scout/scored.jsonl`
   - `/var/lib/scout/scored_pool.jsonl`
   - `/var/lib/scout/queue.jsonl`

### 11.2 Deploy Sequence

1. deploy shared scrape refactor
2. deploy native scrape worker with flags off
3. deploy Mongo scrape state writes
4. deploy compatibility output path
5. run parity harness on fixture corpus
6. run controlled test items through native worker
7. verify selector still receives them
8. switch search-produced `consumer_mode` to `native_scrape`
9. disable iteration-1 legacy handoff bridge
10. hold old scraper as rollback path initially

### 11.3 Rollback

If native scrape causes selector starvation or bad compatibility writes:

1. disable native scrape flags
2. switch search-produced `consumer_mode` back to `legacy_jsonl`
3. re-enable iteration-1 legacy handoff bridge or direct JSONL enqueue path
4. re-enable old scraper ownership
5. keep Mongo scrape state for debugging if harmless
6. inspect failed handoff traces in Langfuse and Mongo

---

## 12. Acceptance Checklist

- native scrape worker claims `scrape.hit` from Mongo
- scrape results are written back to Mongo
- `scrape_runs` exists and records live executions
- `scored.jsonl` compatibility output still works
- `level-1` staging still works
- selector-compatible scored payload shape remains semantically aligned with legacy scraper output
- selector still processes scored outputs successfully
- retry and deadletter state are visible
- discovery page shows true scrape completion
- Langfuse shows scrape traces

---

## 13. Explicit Deferrals To Iteration 3+

Do not touch yet:

- selector migration to Mongo-native consumption
- removal of `scored.jsonl`
- removal of `scored_pool.jsonl`
- preenrich
- CV generation
- scoring/review/publish
- broader queue scheduling sophistication

Iteration 2 succeeds if scrape becomes Mongo-native while selector remains stable behind a compatibility boundary.

---

## 14. Claude Review Attempt

I attempted to run a Claude Opus review with:

```bash
claude -p --model opus --output-format text "Review the plan file plans/iteration-2-mongo-native-scrape.md ..."
```

The command failed locally with:

```text
Not logged in · Please run /login
```

I then checked the repo `.env` because the intended fallback was to use a token from there.

Findings:

- `.env` defines `CLAUDE_CODE_OAUTH_TOKEN`
- that variable is empty in the current repo copy
- `claude auth status` reports `loggedIn: false`
- sourcing `.env` and rerunning `claude -p` still fails because there is no usable token value to pass through

So the saved plan includes my manual review and hardening, but it has not yet been reviewed by Claude Opus in this environment. To complete that step later, populate `CLAUDE_CODE_OAUTH_TOKEN` with a usable token or provide another supported Claude auth mechanism for this shell.
