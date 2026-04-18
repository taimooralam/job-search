# Iteration 3 Plan: Mongo-Native Selector Family And Preenrich Handoff

Author: Codex planning pass on 2026-04-18  
Parent plans:
- `plans/runnerless-vps-mongo-skill-pipeline.md`
- `plans/iteration-1-discovery-ui-langfuse.md`
- `plans/iteration-2-mongo-native-scrape.md`

Status: hardened after review pass on 2026-04-18

## 0. Objective

Iteration 3 removes the selector lane's primary dependence on JSONL files and makes the full discovery path native from search through selector handoff.

By the end of iteration 3, the primary path must be:

```text
search cron
  -> scout_search_hits + search_runs + work_items(scrape.hit)
  -> native scrape worker
  -> Mongo selector payload on scout_search_hits
  -> selector run work_items
  -> native main selector + native profile selectors
  -> level-1 / level-2 writes
  -> level-2 lifecycle=selected
  -> existing preenrich worker claims from level-2
```

That means iteration 3 must deliver all of the following together:

- main selector no longer depends on `scored.jsonl` in the primary path
- dimensional/profile selectors no longer depend on `scored_pool.jsonl` in the primary path
- selector decisions and quotas are visible in Mongo and Langfuse
- `level-2` remains the compatibility boundary for preenrich
- `lifecycle="selected"` remains the claim signal for the existing preenrich worker
- rollback to legacy selectors is still possible during cutover

This is the first iteration that makes the scout lane genuinely end-to-end native through selection while still avoiding a premature preenrich rewrite.

## 0.2 Parent-Plan And Architecture Constraints

The following are no longer local iteration-3 preferences. They are inherited from:

- `plans/runnerless-vps-mongo-skill-pipeline.md`
- `docs/current/architecture.md`

Iteration-3 implementation must therefore follow them explicitly:

- operator/debug UI is search-first
- stage heartbeat is shown before forensic detail
- hot list views use projection, pagination, and lazy disclosure
- new operational query paths ship with their indexes in the same slice
- Langfuse keeps run-level root traces while Mongo keeps stable job correlation
- compatibility files may remain for rollback, but they are not allowed to become the primary UI or selector truth again

### 0.0 Items Explicitly Deferred From Iteration 2

Iteration 2 closed out with the following items explicitly deferred here. Iteration 3 is the owner of all of them — none may slip again.

**Deferred from iteration 2 to iteration 3:**

- Selector migration off `scored.jsonl`.
- Removal of `scored.jsonl`, `scored_pool.jsonl`, and `level-1` staging **from the primary path** (full deletion of `level-1` staging is still NOT in iteration 3 — see §2 In/Out of Scope; only its role as iteration-2 staging is retired, via the §5.6 reconciliation rule).
- Preenrich / CV / scoring-review-publish migration — explicitly still out of scope here; iteration 3 only stops short at preenrich handoff via `lifecycle="selected"`.
- Broader queue orchestration beyond the scrape lane — iteration 3 extends orchestration exactly to the selector lane. Further lanes remain deferred.

**Residual risks inherited from iteration 2 that iteration 3 must address during rollout:**

- Iteration 2 was **not deployed to the VPS** and was **not run against live LinkedIn + production Mongo**. Iteration 3's cutover plan (§14) must therefore absorb iteration-2 VPS deployment as a *prerequisite gate*: iteration-3 canary cannot begin until iteration 2 has been live on the VPS, has produced real `scout_search_hits` with `scrape.status=succeeded`, and iteration-3's `selector_payload` backfill has covered those hits.
- Iteration 2 is locally verified and test-covered, but the VPS staged cutover is still pending. That cutover (native scrape owns scrape.hit end-to-end, legacy JSONL path demoted to rollback) is the baseline state iteration 3 assumes. If iteration 2 has not reached that state on the VPS, iteration 3 Step 1 cannot produce a durable payload for real hits.

**Implication for iteration-3 rollout order:**

1. Complete iteration-2 VPS deploy and live validation first (see §14 gate A).
2. Only then begin iteration-3 Step 1 (scrape worker payload extension).
3. Iteration-3 canary (§12) depends on iteration-2 canary having held for at least one full main-selector cadence (3h) without compatibility-write failures.

### 0.1 Review Deltas (must-close hazards)

The following hazards were identified in a review pass of the current code (`src/pipeline/scrape_worker.py`, `src/pipeline/discovery/store.py`, `src/pipeline/scrape_common.py`, `n8n/skills/scout-jobs/scripts/scout_selector_cron.py`, `n8n/skills/scout-jobs/scripts/scout_dimensional_selector.py`, `src/preenrich/lease.py`) and are load-bearing for iteration 3. Every one of these must be closed before production cutover:

1. **`scout_search_hits.scrape` does NOT persist `description` today.** Iteration 2 omits it from `mark_scrape_succeeded` (see `src/pipeline/discovery/store.py` `mark_scrape_succeeded`). Native selectors require it for the non-English filter, cross-location consolidation, and level-2 insert. Iteration 3 must add durable description persistence in Step 1, not as a side-effect.
2. **Iteration 2 already writes to `level-1`** via `upsert_level1_scored_job` per successful scrape. Iteration 3 also writes tier-D hits to level-1 from the selector. Both paths share the `dedupeKey` unique constraint, so the second write is idempotent, but we must explicitly decide whether to keep the scrape-side write, narrow it to tier-D only post-score, or retire it after cutover.
3. **Legacy `append_to_pool` is conditional on main-selector pre-filters** (blacklist → non-English → `score>0` → cross-location dedupe → DB dedupe). Profile selectors reading directly from `scout_search_hits` without that gating will see a larger, noisier pool. Iteration 3 must either mirror legacy pre-filter gating into pool eligibility, or explicitly document the expanded pool semantics and accept the diff.
4. **`selection.main` is single-state**; an audit trail is needed for discarded decisions that survive later reselection.
5. **Setting `lifecycle="selected"` on profile inserts is a NEW behavior.** Legacy dimensional selector inserts `status="under processing"` and POSTs the runner. Iteration 3 routes profile-selected jobs into preenrich via `lease.py`, which is correct for the target architecture but increases preenrich inbound rate.
6. **Legacy main selector top-N has a latent ordering inconsistency** — `batch_ids = all_inserted_ids[:quota]` does not strictly match score order. Parity harness must decide: freeze legacy, or correct to score-sorted. Recommendation: correct and document.

---

## 1. What Iteration 3 Changes

### Before Iteration 3

```text
search cron
  -> scout_search_hits
  -> work_items(scrape.hit)
  -> native scrape worker
  -> Mongo scrape state
  -> compatibility writes to scored.jsonl + level-1
  -> legacy main selector reads scored.jsonl
  -> legacy main selector appends scored_pool.jsonl
  -> legacy dimensional selectors read scored_pool.jsonl
  -> level-1 / level-2 writes
  -> either runner POST or lifecycle=selected
```

### After Iteration 3

```text
search cron
  -> scout_search_hits
  -> work_items(scrape.hit)
  -> native scrape worker
  -> scout_search_hits.scrape.selector_payload
  -> work_items(select.run.main / select.run.profile)
  -> native selector workers
  -> Mongo selector decisions
  -> level-1 / level-2 writes
  -> level-2 lifecycle=selected
  -> existing preenrich worker
```

### Explicit End-State For This Iteration

- `scored.jsonl` is not required for the primary path
- `scored_pool.jsonl` is not required for the primary path
- `discarded.jsonl` is not required for decision truth
- selector-triggered runner POST is not the primary path

The JSONL files may remain as temporary rollback artifacts, but they are no longer the production source of truth.

---

## 2. Scope

### In Scope

- native main selector migration
- native dimensional/profile selector migration
- Mongo-resident selector input contract
- selector run scheduling and leasing
- selector run summaries and error tracking
- selector decision state persisted to Mongo
- `level-1` and `level-2` compatibility outputs
- `lifecycle="selected"` handoff to the existing preenrich worker
- selector-stage Langfuse tracing
- discovery/debug UI expansion for selector state
- safe cutover and rollback

### Out Of Scope

- preenrich stage migration
- CV generation
- scoring/review/publish lanes
- replacement of `level-2` with a new canonical `jobs` collection
- removal of the existing preenrich lease model
- redesign of the entire queue fairness model across all future lanes

`level-2` remains the canonical handoff surface for preenrich in iteration 3 because the existing lease code claims from `level-2` using `lifecycle="selected"`.

---

## 3. Blackholes Iteration 3 Must Close

Iteration 2 leaves real gaps. Iteration 3 exists to close them explicitly.

### 3.1 `scored.jsonl` Blackhole

The main selector still reads `scored.jsonl`.

If scrape is native but selector still depends on a file append boundary, the lane is not actually Mongo-native.

### 3.2 `scored_pool.jsonl` Blackhole

The dimensional selectors still read `scored_pool.jsonl`, which is currently fed by the main selector.

If iteration 3 migrates only the main selector and ignores the scored pool, profile selectors silently starve.

### 3.3 Selector Input Blackhole

Current iteration-2 Mongo state stores scrape summary fields, but not a full selector-grade payload in Mongo. The selector logic needs:

- description
- score and breakdown
- job identity fields
- location and work mode
- role metadata
- search-profile context

Without a durable selector payload in Mongo, iteration 3 would be forced back onto JSONL.

### 3.4 Batch Semantics Blackhole

The current main selector is not a per-job consumer. It:

- reads a whole scored batch
- filters globally
- dedupes globally
- applies quota globally
- chooses top N globally

If iteration 3 treats selector as one `select.job` work item at a time, it breaks the current ranking semantics.

### 3.5 Preenrich Handoff Blackhole

The scout path currently has two incompatible downstream handoffs:

- legacy runner POST
- `level-2.lifecycle="selected"` for the preenrich worker

Iteration 3 must make the worker handoff path authoritative for native selector runs.

### 3.6 Dual-Selector Blackhole

If the legacy selector and native selector process the same candidate set without a hard ownership split, the result is:

- duplicate `level-1` writes
- duplicate `level-2` writes
- duplicate `selected` jobs
- confusing or misleading UI state

### 3.7 Observability Blackhole

The current discovery/debug surface can show discovery and scrape, but not:

- selector runs
- why jobs were selected or discarded
- top-N quota decisions
- profile-selector decisions
- whether preenrich handoff succeeded

### 3.8 File-Only Debug Blackhole

`discarded.jsonl` is currently the main record of discarded jobs. That is not durable enough to be the decision truth for a native pipeline.

---

## 4. Compatibility Boundary For Iteration 3

Iteration 3 intentionally keeps one compatibility boundary stable:

### Stable Boundary

- `level-1`
- `level-2`
- `level-2.lifecycle="selected"`
- existing preenrich lease claimant in `src/preenrich/lease.py`

### Boundary That Must Move In Iteration 3

- `scored.jsonl`
- `scored_pool.jsonl`
- selector-owned file-driven discard truth
- runner POST as the main scout-path handoff

### Operational Rule

Native selector is considered successful only if selected `level-2` jobs can still be claimed by the existing preenrich worker without any change to preenrich code.

---

## 5. Data Model And Contracts

## 5.1 `scout_search_hits.scrape.selector_payload`

Iteration 3 adds a durable selector-grade payload to each successfully scraped hit.

This payload is the new selector input truth. It supersedes the overlapping `scrape.*` scalar fields (`score`, `tier`, `detected_role`, `seniority_level`, `employment_type`, `job_function`, `industries`, `work_mode`, `scored_at`) which iteration 2 already writes — to eliminate drift, iteration 3 treats `selector_payload` as the only authoritative source of those fields for selector-time decisions. The top-level `scrape.*` scalars remain for iteration-2 UI compatibility but are written in a single atomic update with `selector_payload`.

**Critical gap from iteration 2:** `description` is NOT persisted on `scout_search_hits` today. Iteration 3 Step 1 MUST add `description` (and `breakdown`, `job_url`, `company`, `title`, `location`, `search_profile`, `source_cron`) to the scrape-success persistence path before any native selector can run. The scrape worker in `src/pipeline/scrape_worker.py` / `src/pipeline/discovery/store.py::mark_scrape_succeeded` is the code to change.

**Back-compat rule:** if `scrape.status="succeeded"` but `selector_payload` is missing (hit scraped before iteration 3 rolled out), the native selector must treat it as *ineligible* and log a counter `candidates_missing_payload`. Do not synthesize a partial payload, because description would be absent and would silently alter non-English/filter behavior.

Suggested shape:

```json
{
  "scrape": {
    "status": "succeeded",
    "selector_payload": {
      "job_id": "1234567890",
      "title": "Senior AI Engineer",
      "company": "Example Corp",
      "location": "Remote",
      "job_url": "https://www.linkedin.com/jobs/view/1234567890/",
      "description": "...",
      "score": 78,
      "tier": "A",
      "detected_role": "ai_engineer",
      "seniority_level": "senior",
      "employment_type": "full-time",
      "job_function": "engineering",
      "industries": ["software"],
      "work_mode": "remote",
      "search_profile": "ai",
      "search_region": "remote",
      "source_cron": "hourly",
      "breakdown": {},
      "scored_at": "ISODate"
    }
  }
}
```

Rules:

- store only what selector logic needs
- do not store raw HTML in `selector_payload`
- `selector_payload` is the durable replacement for `scored.jsonl` and `scored_pool.jsonl` content
- the scrape worker becomes responsible for keeping this payload current and idempotent
- `description` is required — absence means the hit is selector-ineligible
- when the scrape worker re-scrapes (freshness refresh), the payload must be overwritten atomically, never partially merged
- `selection.*` must be reset to `pending` if the payload is rewritten after a prior selector decision; this prevents stale ranking on refreshed data

## 5.2 `scout_search_hits.selection`

Iteration 3 adds explicit selection state to each hit.

Suggested shape:

```json
{
  "selection": {
    "main": {
      "status": "pending|leased|completed|failed|deadletter",
      "decision": "selected_for_preenrich|inserted_level2_only|inserted_level1|discarded_quota|duplicate_db|duplicate_cross_location|filtered_blacklist|filtered_non_english|filtered_score|none",
      "selector_run_id": "selectorrun:main:...",
      "reason": "string|null",
      "rank": 1,
      "selected_at": "ISODate|null",
      "level2_job_id": "ObjectId|null",
      "level1_upserted_at": "ISODate|null"
    },
    "pool": {
      "status": "available|expired|consumed|not_applicable",
      "pooled_at": "ISODate|null",
      "expires_at": "ISODate|null"
    },
    "profiles": {
      "global_remote": {
        "status": "pending|leased|completed|failed|deadletter",
        "decision": "selected|duplicate_db|filtered_location|filtered_non_english|filtered_score|quota_miss|none",
        "selector_run_id": "selectorrun:profile:global_remote:...",
        "reason": "string|null",
        "rank_score": 82.0,
        "selected_at": "ISODate|null",
        "level2_job_id": "ObjectId|null"
      }
    }
  }
}
```

Rules:

- `selection.main` is authoritative for the main selector decision
- `selection.pool` replaces scored-pool file truth
- `selection.profiles.<profile>` stores profile-selector outcomes independently
- one hit can be discarded by the main selector and still later be selected by a profile selector if it remains valid and dedupe checks pass
- **pool eligibility mirrors legacy gating**: a hit transitions `selection.pool.status` to `available` only after the main-selector pre-filter chain has cleared it (blacklist, non-English, `score>0`, cross-location consolidation, and DB dedupe against `level-1`+`level-2`). This mirrors the current `append_to_pool(new_jobs)` call-site in `scout_selector_cron.py`. Pool entry is therefore performed by the **main selector run**, not by the scrape worker. The scrape worker only seeds `selection.pool.status="not_applicable"` initially; the main selector promotes hits to `available` or `expired`. Expanding pool eligibility to bypass main-selector gating is explicitly OUT OF SCOPE for iteration 3.
- pool `expires_at` is `main_selector_run.completed_at + 48h` and is not extended by re-evaluation.
- **cross-selector ownership rule**: a profile selector must skip any hit where `selection.main.status in {pending, leased}` for the current or more recent run, or where `selection.main.level2_job_id` is set AND the referenced level-2 doc has `lifecycle in {selected, preenriching, ready_for_cv, cv_generating, reviewing, ready_to_apply, published}`. This prevents double-ownership with in-flight preenrich work.
- **immutable audit**: every selector decision on a hit must append to `selection.main.history[]` (or `selection.profiles.<profile>.history[]`), with `{run_id, decision, reason, at}`. The single-state `decision` field reflects the most recent run only; `history` is append-only. `history` is bounded to the last 20 entries per selector kind.

## 5.3 `selector_runs`

Purpose:

- run-level truth for native selector executions
- recovery and observability
- UI summary and Langfuse linkage

Suggested shape:

```json
{
  "_id": "ObjectId",
  "run_id": "selectorrun:main:2026-04-18T14:55:00Z:abc123",
  "run_kind": "main|profile",
  "profile_name": "global_remote|null",
  "trigger_mode": "timer|manual|shadow_compare",
  "status": "scheduled|running|completed|failed|deadletter",
  "scheduled_for": "ISODate",
  "started_at": "ISODate|null",
  "completed_at": "ISODate|null",
  "cutoff_at": "ISODate",
  "worker_id": "hostname-pid-uuid|null",
  "stats": {
    "candidates_seen": 0,
    "filtered_blacklist": 0,
    "filtered_non_english": 0,
    "filtered_score": 0,
    "duplicate_cross_location": 0,
    "duplicate_db": 0,
    "tier_low_level1": 0,
    "inserted_level2": 0,
    "selected_for_preenrich": 0,
    "discarded_quota": 0,
    "profile_selected": 0
  },
  "errors": [],
  "langfuse_session_id": "selectorrun:main:2026-04-18T14:55:00Z:abc123",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Required indexes:

- unique: `run_id`
- query: `run_kind + scheduled_for + status`
- query: `profile_name + scheduled_for`
- query: `status + updated_at`

**Retry semantics using `cutoff_at`:**

- `cutoff_at` is set exactly once at run creation and is immutable. Reruns of a failed run item MUST reuse the original `cutoff_at` by looking up the existing `selector_runs` document keyed on `run_id`.
- The worker loads `selector_runs` first; if `status=failed` the worker resets it to `running` and continues from the durable decision state already persisted on `selection.*.status` fields.
- Decision idempotency: a hit with `selection.<kind>.selector_run_id == current_run_id` and `status in {completed, failed}` is considered already processed in the current run and is not re-ranked.

**Immutable decisions array (operator audit):**

`selector_runs.decisions[]` (optional, bounded to ~top-N+deadletter count) records:

```json
{
  "hit_id": "ObjectId",
  "decision": "selected_for_preenrich|inserted_level2_only|...",
  "reason": "string",
  "rank": 1,
  "score": 78,
  "level2_job_id": "ObjectId|null"
}
```

This complements — not replaces — `selection.*.history[]` on the hit document. `decisions[]` is the per-run snapshot; `history[]` is the per-hit timeline.

## 5.4 `work_items` For Selector Runs

Iteration 3 should not enqueue one `select.job` work item per hit as the primary selector execution contract.

Reason:

- main selector semantics are batch-global
- profile selectors are batch-global
- per-job work items would break quota and ranking behavior

Instead, use run-level work items:

```json
{
  "task_type": "select.run.main|select.run.profile",
  "lane": "selector",
  "subject_type": "selector_run",
  "subject_id": "selectorrun:...",
  "status": "pending|leased|done|failed|deadletter",
  "priority": 100,
  "available_at": "ISODate",
  "lease_owner": "hostname-pid-uuid|null",
  "lease_expires_at": "ISODate|null",
  "attempt_count": 0,
  "max_attempts": 3,
  "idempotency_key": "selectorrun:<run_kind>:<profile>:<scheduled_for>",
  "payload": {
    "run_kind": "main|profile",
    "profile_name": "global_remote|null",
    "scheduled_for": "ISODate"
  }
}
```

The work item drives the run. The candidates are loaded from `scout_search_hits`.

**Missed-window + stale-run policy:**

- Missed schedule ticks are not caught up. A run whose `scheduled_for` is older than 2× its cadence and was never claimed is reaped to `deadletter` with `errors: ["missed_window"]`.
- A leased run item whose `lease_expires_at < now` with `status=leased` is reaped to `failed` and its `selector_runs.status` is flipped to `failed`. The next scheduled tick enqueues a new run with a new `run_id`. Reruns do not reuse the old `run_id`; reruns reuse `cutoff_at` only within the same `run_id` lease lifetime (see §5.3).
- A dedicated `scout-queue-seeder` timer (already envisioned in the parent runnerless plan) is the sole enqueuer; no selector worker self-enqueues next runs.

## 5.5 `level-2` Contract

`level-2` remains the output boundary for:

- all tier C+ jobs chosen by the main selector
- all jobs inserted by profile selectors

For native selector runs:

- inserted docs must preserve the existing level-2 schema shape used by downstream code (see `scout_selector_cron.py::insert_jobs` as reference)
- top N selected docs must receive:
  - `lifecycle="selected"`
  - `selected_at`
- non-top-N tier C+ docs are inserted with **no `lifecycle` field** (preenrich lease ignores them — see `src/preenrich/lease.py` `claim_one`); they remain visible in the UI but are not claimed downstream
- native selector must not POST the runner in the primary path
- **atomic selection rule**: for top-N candidates, the `$setOnInsert` document MUST include `lifecycle="selected"` and `selected_at` from the start. Do not insert with null lifecycle and patch lifecycle in a second write — a crash between the two leaves an orphan.
- **existing-doc promotion rule**: if a tier C+ candidate was already inserted by a prior run (or by a profile selector) with null lifecycle, a separate compare-and-set `update_one({"_id": <id>, "lifecycle": {"$in": [null, None]}}, {"$set": {"lifecycle": "selected", "selected_at": now}})` is used. Do not overwrite existing lifecycle values.
- `starred=True` for tier A is preserved from legacy dimensional selector behavior (`scout_dimensional_selector.py:262`) and should be applied in both main and profile native paths for schema parity.

## 5.6 `level-1` Contract

`level-1` remains the sink for:

- tier D and below jobs from the main selector
- optional compatibility staging still needed by existing tooling

But `level-1` is not the decision truth. Decision truth now lives in Mongo selector state on `scout_search_hits`.

**Reconciliation with iteration-2 scrape-side level-1 writes:**

Iteration 2 (`src/pipeline/scrape_common.py::upsert_level1_scored_job`) currently upserts every scored hit into `level-1` regardless of tier, with `source="scout_native_scrape"` and `status="scored"`. Iteration 3 selector also writes tier-D to `level-1` with `source="scout_discarded"` and `status="discovered"`.

Rules:

1. Both writes target the same `dedupeKey`; `$setOnInsert` ensures idempotency — only the first write wins on the shared fields.
2. After native selector cutover (§12 canary), narrow iteration-2's level-1 write behind a flag `SCOUT_SCRAPE_WRITE_LEVEL1` to `false`. Selector becomes the sole level-1 writer. Do this in the Step 13 retirement phase — not before — so level-1 never goes dark during cutover.
3. Until retirement, both writers are permitted, and the `source` field will reflect whichever ran first. This is acceptable for the cutover window.

---

## 6. Main Selector Contract

The native main selector must preserve the current legacy behavior, but read from Mongo instead of `scored.jsonl`.

Required behavior:

1. Query eligible candidates from `scout_search_hits` where:
   - `scrape.status="succeeded"`
   - `scrape.selector_payload` exists
   - `selection.main.status in [null, "pending", "failed"]`
   - `scrape.completed_at <= cutoff_at`

2. Apply filters in the same semantic order:
   - blacklist filter
   - non-English filter
   - score > 0 filter

3. Apply cross-location consolidation using the existing logic.

4. Dedupe against Mongo with the same effective semantics as the current selector:
   - dedupe key match against `level-2`
   - normalized company+title secondary check against `level-2`

5. Split by tier:
   - C+ to `level-2`
   - D and below to `level-1`

6. Insert all C+ to `level-2`.

7. Select the top N by current quota logic and mark them:
   - `lifecycle="selected"`
   - `selected_at`

8. Persist the decision back to `scout_search_hits.selection.main`.

Important rule:

The native main selector uses `lifecycle="selected"` + `selected_at` as the authoritative handoff to preenrich (via `src/preenrich/lease.py::claim_one`, which sorts by `selected_at`). Direct runner POST is legacy-only rollback behavior and is disabled in native runs by `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle`.

The legacy `SELECTOR_ENQUEUE_VIA_WORKER=true` env var (present in `scout_selector_cron.py`) is superseded by `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE` in iteration 3. When `SCOUT_SELECTOR_ENABLE_NATIVE_MAIN=true`, the native runner ignores `SELECTOR_ENQUEUE_VIA_WORKER` entirely; the flag continues to govern the legacy selector path only during rollback.

### 6.5 Legacy Behaviors Preserved vs Changed (Main Selector)

Preserved (must match legacy semantically, modulo noted correction):

- filter order: blacklist → non-English → `score>0` → cross-location consolidation → DB dedupe (two-pass: dedupeKey then normalized company+title against `level-2`)
- tier split: A/B/C → level-2 insert, D and below → level-1 insert
- quota default: `HOURLY_QUOTA=8` for top-N selection
- category weights and `apply_quota` overflow redistribution

Changed (intentional correction; document at cutover):

- **top-N ordering is strictly by score descending**, correcting the latent legacy inconsistency where `batch_ids = all_inserted_ids[:quota]` did not guarantee score order. Parity harness MUST assert native ordering matches score-descending and MUST document the divergence from legacy byte-parity.
- `AI_TOP15_QUOTA` dropping to 0 in legacy is preserved — no separate ai_top15 handling in native unless reintroduced.
- `status` field on non-top-N tier C+ inserts stays `None` (unchanged from legacy `status=None` in worker-mode path).

---

## 7. Profile Selector Contract

The native profile selectors replace `scout_dimensional_selector.py` reading from `scored_pool.jsonl`.

Required behavior:

1. Load profile definitions from the same profile source used today.

2. Query eligible candidates from `scout_search_hits` where:
   - `scrape.status="succeeded"`
   - `scrape.selector_payload` exists
   - `selection.pool.status="available"`
   - candidate not already expired from the 48h pool window

3. Apply profile-specific filtering:
   - blacklist
   - non-English
   - score > 0
   - location/profile match

4. Apply the same dimensional ranking logic used today, including:
   - leadership boosts
   - staff/architect boosts
   - remote boosts
   - freshness boosts
   - AI title boost

5. Dedupe against Mongo `level-1` and `level-2` with the same current semantics.

6. Insert selected jobs to `level-2`.

7. Mark profile-selected jobs as:
   - `lifecycle="selected"`
   - `selected_at`
   - inserted with appropriate source tags

8. Persist per-profile decisions under `selection.profiles.<profile>`.

Important rule:

Profile selectors must not depend on the main selector having appended `scored_pool.jsonl`. They read Mongo directly, but **pool-eligibility state is produced by the main selector run** (see §5.2) — so the main selector remains logically upstream of profile selectors. This preserves legacy pre-filter gating without reintroducing the file dependency.

### 7.5 Legacy Behaviors Preserved vs Changed (Profile Selector)

Preserved:

- profile definition loaded from existing `data/selector_profiles.yaml`
- location pattern matching semantics (`scout_dimensional_selector.py::matches_location`)
- dimensional rank score formula (leadership, staff_architect, remote, newest, AI-title boosts)
- two-pass DB dedupe against `level-1` + `level-2`
- quota per profile
- `starred=True`/`starredAt=now` for tier A inserts
- `source` tag per profile

Changed (intentional — document at cutover; increases preenrich inbound rate):

- profile-selected jobs are inserted with `lifecycle="selected"` + `selected_at` and do NOT set `status="under processing"`. They flow to preenrich via the lease, not the runner.
- `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle` is required for all native profile runs.
- profile-run cutover must be preceded by a preenrich-capacity check (see §18). If preenrich cannot keep up, stage cutover one profile at a time.

---

## 8. Scheduling, Timers, And Worker Model

Iteration 3 should move selector scheduling toward the final worker model without breaking the cadence semantics.

### 8.1 Main Selector

Keep the current schedule semantics:

- every 3 hours
- global ranking over the eligible window

Recommended model:

- a timer or cron-compatible scheduler enqueues one `select.run.main` work item per scheduled run
- the selector worker claims that run item

### 8.2 Profile Selectors

Keep the current profile schedules semantically identical:

- one scheduled run item per configured profile cadence

Recommended model:

- one `select.run.profile` work item per profile schedule
- payload contains profile name and scheduled window

### 8.3 Lease Rule

Only one selector run for a given `run_id` may be active at a time.

Required protections:

- unique `run_id` index on `selector_runs`
- unique `idempotency_key` on `work_items` (`selectorrun:<run_kind>:<profile>:<scheduled_for>`)
- work-item lease (`findOneAndUpdate` claim semantics consistent with the shared queue helper in `src/pipeline/queue.py`)
- `selector_runs.status` transition guarded by compare-and-set: `{_id, status: "scheduled"} → {status: "running", started_at, worker_id}`
- heartbeat on long runs (> 5 min): refresh `lease_expires_at` on the work item and `updated_at` on `selector_runs`

**Cross-selector ordering guarantee:**

- Main and profile selectors may run concurrently if, and only if, their cutoff windows do not overlap.
- When they do overlap (bounded cutover case), profile selectors must apply the ownership rule in §5.2 and skip hits owned by a main run in `{pending, leased}` state.

### 8.4 Cutoff Rule

Each selector run must operate on a stable cutoff:

- candidates with `scrape.completed_at <= cutoff_at` are in the run
- later arrivals wait for the next run

This is necessary to preserve batch semantics and avoid moving targets.

---

## 9. Rollout Flags

Iteration 3 needs explicit cutover controls.

Suggested flags:

- `SCOUT_SELECTOR_ENABLE_NATIVE_MAIN`
- `SCOUT_SELECTOR_ENABLE_NATIVE_PROFILES`
- `SCOUT_SELECTOR_USE_MONGO_INPUT`
- `SCOUT_SELECTOR_ENABLE_LEGACY_MAIN_JSONL`
- `SCOUT_SELECTOR_ENABLE_LEGACY_PROFILE_POOL`
- `SCOUT_SELECTOR_SHADOW_COMPARE_MAIN`
- `SCOUT_SELECTOR_SHADOW_COMPARE_PROFILES`
- `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle|legacy_runner`
- `SCOUT_SELECTOR_DISABLE_RUNNER_POST`
- `SCOUT_SCRAPE_PERSIST_SELECTOR_PAYLOAD`
- `SCOUT_SCRAPE_WRITE_SCORED_JSONL_COMPAT`
- `SCOUT_SELECTOR_WRITE_SCORED_POOL_COMPAT`

Required safety rules:

- native main selector cannot be enabled unless `SCOUT_SCRAPE_PERSIST_SELECTOR_PAYLOAD=true` has been live for at least one scrape cycle and at least 95% of `scrape.status=succeeded` hits in the last 24h have a `selector_payload` present
- native profiles cannot be enabled unless native main has been live and populating `selection.pool.status` transitions for at least one main-selector cadence (3h)
- `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle` is the required mode for native selector runs; `legacy_runner` is rollback-only
- rollback must be possible without code changes by toggling flags

**Cross-iteration flag mapping (iteration 2 ↔ iteration 3):**

| Iteration 2 flag | Iteration 3 behavior |
|---|---|
| `SCOUT_SCRAPE_WRITE_SCORED_JSONL=true` | MUST stay `true` until iteration-3 main selector is native + canary verified. Flipped to `false` in Step 13. |
| `SCOUT_SCRAPE_WRITE_LEVEL1=true` | Stays `true` through iteration-3 canary. Flipped to `false` only after native main selector owns level-1 writes (§5.6). |
| `SCOUT_SCRAPE_SELECTOR_COMPAT_MODE=true` | Stays `true` until legacy main selector is retired. |
| `SCOUT_SCRAPE_ENABLE_LEGACY_JSONL_CONSUMER` | Unchanged in iteration 3. |

Flag flip order for clean cutover:

1. Enable `SCOUT_SCRAPE_PERSIST_SELECTOR_PAYLOAD=true` (scrape worker writes new payload + description).
2. Wait for ≥24h of payload coverage.
3. Enable `SCOUT_SELECTOR_SHADOW_COMPARE_MAIN=true` (no writes, diffs only).
4. After parity hold, enable `SCOUT_SELECTOR_ENABLE_NATIVE_MAIN=true` + `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle`.
5. Disable `SCOUT_SELECTOR_ENABLE_LEGACY_MAIN_JSONL=false` (legacy reads off).
6. Leave compatibility writes on for one observation cycle after each native cutover so operators can compare steady-state Mongo-native behavior against rollback artifacts without re-enabling legacy ownership.
7. Repeat shadow + cutover per profile.
8. After the observation cycle is clean, disable `SCOUT_SCRAPE_WRITE_SCORED_JSONL=false` and `SCOUT_SELECTOR_WRITE_SCORED_POOL_COMPAT=false` (Step 13).
9. Disable `SCOUT_SCRAPE_WRITE_LEVEL1=false` only after native main selector has sole level-1 ownership.

**Shadow-mode invariants (hard rules):**

When `SCOUT_SELECTOR_SHADOW_COMPARE_*=true`:

- the shadow run MUST NOT write to `level-1` or `level-2`
- the shadow run MUST NOT set `lifecycle="selected"`
- the shadow run MUST NOT POST the runner
- the shadow run MUST NOT mutate `selection.*.status` or `selection.*.decision` (it may write to a dedicated `selection.main.shadow` subdoc or to `selector_runs.diff[]` only)
- the shadow run MUST read the *same* cutoff window that the legacy selector is about to consume, using a snapshot query (not `read_and_clear_scored`)
- a scheduled legacy run and its paired shadow run share a `shadow_pair_id` for diff analysis

---

## 10. Granular Implementation Plan

### Step 1: Finalize Selector Input Truth

- extend scrape success persistence (`src/pipeline/discovery/store.py::mark_scrape_succeeded`) to write `scrape.selector_payload` containing **at minimum** `description`, `breakdown`, `job_url`, `company`, `title`, `location`, `search_profile`, `source_cron` in addition to the scalars already persisted. Without `description`, native selectors cannot run.
- keep iteration-2 scalar fields on `scrape.*` for UI compatibility; write both from the same `$set` to avoid split writes.
- add `selection.main`, `selection.pool`, and `selection.profiles` scaffolding on insertion of every new `scout_search_hits` document (defaults to `status=pending`/`not_applicable`).
- add a one-shot backfill script that populates `selector_payload` from re-scrape for hits already succeeded without it, OR leaves them selector-ineligible by design — decision documented in the backfill runbook.
- add indexes for:
  - `scrape.status + scrape.completed_at`
  - `selection.main.status + scrape.completed_at`
  - `selection.pool.status + selection.pool.expires_at`
  - `selection.profiles.<profile>.status + scrape.completed_at` (one partial index per active profile)
  - `selection.main.selector_run_id` (sparse)
  - `selection.main.level2_job_id` (sparse)

### Step 2: Add `selector_runs`

- create collection and indexes
- define run kinds: `main` and `profile`
- define status transitions: `scheduled -> running -> completed|failed|deadletter`

### Step 3: Add Selector Scheduling

- create scheduler entrypoints that enqueue `select.run.main` and `select.run.profile`
- make run creation idempotent per schedule window
- keep current schedule cadence unchanged

### Step 4: Extract Shared Selector Logic

- pull common logic from `scout_selector_cron.py` into shared functions:
  - blacklist filter
  - non-English filter
  - score filter
  - cross-location consolidation
  - Mongo dedupe
  - level-1 insert helper
  - level-2 insert helper
- pull common logic from `scout_dimensional_selector.py` into shared functions:
  - profile load
  - location match
  - dimensional rank score
  - Mongo dedupe

Do not maintain two incompatible selector implementations.

### Step 5: Build Native Main Selector Worker

- claim `select.run.main`
- compute cutoff
- snapshot eligible candidates
- execute selection logic
- persist decisions
- write `level-1` / `level-2`
- mark top N `lifecycle="selected"`
- finalize `selector_runs`

### Step 6: Build Native Profile Selector Worker

- claim `select.run.profile`
- load profile config
- snapshot eligible pool candidates
- execute dimensional selection logic
- persist profile decisions
- write `level-2`
- mark selected docs for preenrich with `lifecycle="selected"` and `selected_at`
- finalize `selector_runs`

### Step 7: Replace File-Based Decision Truth

- move discarded-job truth from `discarded.jsonl` into Mongo decision state
- keep file writes only as temporary rollback diagnostics if needed

### Step 8: Wire Preenrich Compatibility

- ensure native selector-selected `level-2` docs are claimable by the current preenrich worker
- confirm `lifecycle="selected"` and `selected_at` are written exactly as the lease code expects
- do not require any preenrich code changes in iteration 3

### Step 9: Add Langfuse Instrumentation

- trace main selector runs
- trace profile selector runs
- capture:
  - candidate counts
  - filtering counts
  - dedupe counts
  - insert counts
  - top-N handoff
  - per-profile selection decisions

### Step 10: Expand Discovery/Debug UI

- show selector run summaries
- show main selector decision per hit
- show profile-selector decisions per hit
- show links to inserted `level-2` docs when available
- show preenrich handoff state
- keep Langfuse links optional and independent

### Step 11: Shadow Compare Mode

- add a no-write or compare-only mode for native selector runs
- compare native main selector outputs to legacy main selector outputs on the same candidate window
- compare native profile selector outputs to legacy dimensional selector outputs
- log decision diffs clearly before write cutover

### Step 12: Canary Cutover

- cut over main selector first
- then cut over profile selectors one by one
- keep legacy file compatibility enabled until each native selector path is proven

### Step 13: Retire Primary JSONL Use

After native selectors are stable:

- disable `scored.jsonl` as primary selector input
- disable `scored_pool.jsonl` as primary profile-selector input
- keep files only if rollback requires them

### Step 14: Documentation And Runbooks

- update `missing.md`
- update `architecture.md`
- document deploy, rollback, and operator checks

---

## 11. Risk Mitigation And Error Handling

### 11.1 Partial Run Protection

If a selector run crashes mid-way:

- `selector_runs` must show `failed` (via lease-expiry reaper if the worker died without marking)
- the work item must be retryable or deadlettered explicitly
- already persisted decisions must be idempotent on retry:
  - the worker loads `selector_runs` by `run_id` on retry and reuses the original `cutoff_at`
  - candidates whose `selection.<kind>.selector_run_id == run_id` and `status in {completed, failed}` are skipped
- `level-2` inserts rely on `dedupeKey` unique behavior; `$setOnInsert` plus the §5.5 atomic-selection rule prevents partial `lifecycle` state
- if the run persisted `level-2` inserts but crashed before atomic `lifecycle="selected"` on top-N, the retry must re-rank over the same cutoff snapshot and apply the compare-and-set promotion (§5.5 existing-doc promotion rule) — this is safe because the promotion only transitions `lifecycle` from null to `selected`

### 11.2 Duplicate Insert Protection

Required protections:

- `dedupeKey` unique behavior remains authoritative on `level-2`
- native and legacy selectors must not both own the same scheduled window
- run creation is idempotent per window
- hit-level decision state prevents re-selecting the same candidate unintentionally

### 11.3 Window Drift Protection

The selector run must persist its `cutoff_at`.

That value must be used consistently for:

- candidate query
- replay
- debugging
- parity comparison

### 11.4 Profile-Starvation Protection

Do not disable pool compatibility until native profile selectors are proven.

Main-selector cutover alone is not enough.

### 11.5 Preenrich Safety

If native selector reaches `level-2` but preenrich cannot claim the selected jobs, the cutover is not complete.

### 11.6 Honest UI

The UI must distinguish:

- scraped
- selector-eligible
- selected for preenrich
- inserted to level-2 but not top-N selected
- inserted to level-1
- discarded
- profile-selected

No step should imply pipeline completion.

---

## 12. Tests And Parity Harness

Required tests:

- selector payload persistence on scrape success
- main selector candidate query from Mongo
- main selector filter ordering matches legacy behavior
- cross-location consolidation matches legacy behavior
- Mongo dedupe matches legacy behavior
- tier split and level-1 writes
- level-2 insert behavior
- top-N `lifecycle="selected"` handoff
- profile selector location filter and rank scoring
- profile selector Mongo dedupe
- idempotent rerun for the same selector window
- rollback flags prevent double-processing
- UI rendering for selector run lists and decision chips

Required parity harness:

- feed the same fixed candidate fixture through:
  - legacy main selector
  - native main selector
- compare:
  - filtered counts
  - selected IDs
  - top-N chosen IDs
  - tier-low decisions

And separately:

- feed the same fixed pool fixture through:
  - legacy dimensional selector
  - native profile selector
- compare:
  - matched count
  - selected IDs
  - ranking order

Parity must be established before production cutover.

**Parity baseline policy:** parity is measured against legacy semantics *with the latent top-N ordering bug corrected*. Any intentional divergence from legacy byte-parity MUST be listed in a `parity_divergence.md` artifact alongside the harness. The acceptance gate is "no unintended divergence" — not "zero divergence".

**Shadow-mode diff schema:**

Each shadow run emits a record of shape:

```json
{
  "shadow_pair_id": "shadow:main:<legacy_run_ts>",
  "legacy_top_n_ids": ["job_id", ...],
  "native_top_n_ids": ["job_id", ...],
  "only_in_legacy": ["job_id", ...],
  "only_in_native": ["job_id", ...],
  "tier_c_plus_count_legacy": 0,
  "tier_c_plus_count_native": 0,
  "level1_count_legacy": 0,
  "level1_count_native": 0,
  "dedupe_reason_breakdown": {}
}
```

Stored on `selector_runs.diff` when `trigger_mode="shadow_compare"`. Cutover proceeds only after three consecutive shadow runs show no *unintended* divergence.

---

## 13. UI And Langfuse Requirements

### UI Additions

The discovery/debug page should now show:

- `selection.main.status`
- `selection.main.decision`
- `selection.main.reason`
- `selection.main.level2_job_id`
- `selection.pool.status`
- profile-selector decision chips
- recent main selector runs
- recent profile selector runs
- selector failures and deadletters
- whether a selected `level-2` doc has `lifecycle="selected"`

### Langfuse Trace Shape

Use one trace/session per selector run.

Recommended child spans:

- query candidates
- blacklist filter
- non-English filter
- score filter
- cross-location consolidation
- DB dedupe
- tier split
- level-1 writes
- level-2 writes
- preenrich handoff
- profile-specific ranking

If Langfuse is unavailable, selector logic must still run.

---

## 14. Deploy, Cutover, And Rollback

### Deploy Order

**Gate A (prerequisite):** iteration-2 is live on the VPS, native scrape worker owns `scrape.hit`, compatibility writes healthy for ≥24h.

**Gate B (payload coverage):** `SCOUT_SCRAPE_PERSIST_SELECTOR_PAYLOAD=true` live for ≥24h, ≥95% of recent succeeded hits carry `selector_payload`.

**Gate C (shadow parity):** three consecutive main shadow runs show no unintended divergence; same bar per profile before their cutover.

**Gate D (preenrich capacity):** preenrich claim lag ≤ 10 minutes under baseline load + expected increase from profile selectors (sized offline; see §18).

Deploy order:

1. ship selector payload persistence (Step 1) + indexes; backfill or accept skip
2. ship `selector_runs` collection, scheduler, and worker skeleton (Step 2–3) with native flags OFF
3. ship shared selector logic extraction (Step 4); run unit + parity harness in CI
4. deploy native main worker with `SCOUT_SELECTOR_SHADOW_COMPARE_MAIN=true`
5. hold through Gate C (main)
6. enable `SCOUT_SELECTOR_ENABLE_NATIVE_MAIN=true` and `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE=selected_lifecycle`; disable legacy main reads (`SCOUT_SELECTOR_ENABLE_LEGACY_MAIN_JSONL=false`)
7. confirm `level-2.lifecycle="selected"` is being claimed by preenrich within SLO
8. per-profile cutover: shadow → enable → legacy profile off — one at a time, with Gate D re-checked per profile
9. retire primary JSONL inputs (`SCOUT_SCRAPE_WRITE_SCORED_JSONL=false`, `SCOUT_SELECTOR_WRITE_SCORED_POOL_COMPAT=false`)
10. retire iteration-2 scrape-side `level-1` writes (`SCOUT_SCRAPE_WRITE_LEVEL1=false`) after native selector has sole ownership

**Per-step health checks (run after each of steps 6, 8, 9, 10):**

- no deadlettered selector runs in the last cadence
- preenrich claim lag within SLO
- discovery/debug UI shows expected selection state transitions (no stuck `pending`, no orphan `leased`)
- Langfuse selector trace count == `selector_runs` completed count
- no double-insert or dedupe-collision errors in logs

### Rollback Order

If native selector misbehaves:

1. disable native main/profile flags
2. re-enable legacy selector readers
3. keep scrape compatibility writes on
4. confirm legacy selectors are consuming the expected files again

Rollback must not require data migration.

---

## 15. Acceptance Criteria

Iteration 3 is complete only when all are true:

1. A scraped job reaches selector-ready state in Mongo without requiring `scored.jsonl`.
2. Native main selector can process a real selector run from Mongo and write the same effective outcomes as the legacy selector.
3. Native profile selectors can process real scheduled profile runs from Mongo without requiring `scored_pool.jsonl`.
4. Selected jobs are inserted into `level-2` and marked `lifecycle="selected"` in a way the current preenrich worker can claim.
5. Native selector does not require runner POST in the primary path.
6. Decision truth is visible in Mongo and the UI.
7. Selector runs are visible in Langfuse.
8. Legacy main and profile selector rollback remains possible during cutover.
9. After cutover, search -> scrape -> selector -> preenrich handoff is native end to end.

---

## 15.1 UI Honesty — required chip states

The discovery/debug page must render distinguishable chips for:

- `Discovered` / `Scraped`
- `Selector Pending` (eligible but not yet evaluated)
- `Selector Leased` (currently in a run)
- `Pool Available` (eligible for profile selectors)
- `Inserted L2 Only` (tier C+ not top-N)
- `Selected for Preenrich` (top-N / profile-selected with `lifecycle=selected`)
- `Claimed by Preenrich` (derived from `level-2.lifecycle ∈ {preenriching, …}`)
- `Profile Selected: <profile>` (one per profile active)
- `Inserted L1` (tier D)
- `Discarded: <reason>` (one chip per distinct discard reason)
- `Deadletter: <reason>`

`selection.*.history[]` powers a timeline view per hit so operators can see why a given job is currently classified as it is.

## 16. Explicit Non-Goals

Iteration 3 does not:

- migrate preenrich to `work_items`
- remove `level-2`
- redesign the preenrich lease model
- migrate CV generation or later lanes
- redesign all future selector profiles beyond preserving their current semantics

The goal is narrower and stricter:

make the selector family native, keep preenrich stable, and remove JSONL files from the selector hot path without introducing regressions.

---

## 17. Known Legacy Behaviors: Preserved vs Changed

Consolidated list for reviewers and operators. See §6.5 and §7.5 for detail.

Preserved exactly:

- main selector filter order and semantics (blacklist → non-English → `score>0` → cross-location consolidation → DB dedupe)
- tier split (A/B/C → level-2; D → level-1)
- `HOURLY_QUOTA=8`, `AI_TOP15_QUOTA=0`
- two-pass DB dedupe (dedupeKey + normalized company+title against `level-2`; profile selectors also check `level-1`)
- cross-location consolidation (`src/common/dedupe.py::consolidate_by_location`)
- profile dimensional ranking boosts (leadership, staff_architect, remote, newest, AI-title)
- `starred=True`/`starredAt=now` for tier A inserts in the profile path (extended to main path for schema parity)
- dedupeKey format (`linkedin_scout|<job_id>`, `linkedin_import|<job_id>`)

Changed intentionally (document at cutover):

- top-N ordering is strictly by score descending in native main (legacy ordering bug corrected)
- profile-selected jobs use `lifecycle="selected"` + `selected_at` instead of `status="under processing"` + runner POST
- all native selectors route to preenrich via the lease; runner POST is rollback-only
- pool eligibility transitions are written by the main selector, not inferred from file writes
- `selector_runs` + `selection.*.history[]` provide durable audit that legacy file writes did not

Retired:

- `scored.jsonl` as primary selector input
- `scored_pool.jsonl` as primary profile input
- `discarded.jsonl` as decision truth (retained as optional rollback diagnostic until Step 13 retirement)
- `SELECTOR_ENQUEUE_VIA_WORKER` env var (superseded by `SCOUT_SELECTOR_PREENRICH_HANDOFF_MODE`)

## 18. Out-of-Plan Prerequisites

These are not iteration-3 deliverables, but iteration 3 cannot cut over safely without them:

- **Iteration 2 must be live on the VPS** (see §0.0). No iteration-3 production cutover is permitted while iteration 2 is local-only.
- **Preenrich capacity sizing**: the preenrich worker must be benchmarked against the expected post-cutover inflow (main top-N + all active profile selections). If lag exceeds SLO, profile cutover proceeds one profile at a time and may pause.
- **Operator runbook** for: shadow-diff interpretation, native→legacy rollback, cutoff-at rerun semantics, deadletter triage, and payload backfill.
- **Alerting**: on `selector_runs.status=failed`, on shadow divergence above threshold, on preenrich claim lag, on hits stuck in `selection.main.status=leased` beyond lease expiry.

## 19. Residual Risks After This Plan

- **Profile-selector cutover increases preenrich load**; if preenrich is not sized, jobs will accumulate with `lifecycle="selected"` and `selected_at` will skew operator lag metrics. Mitigation: Gate D before each profile cutover; pause cutover if lag exceeds SLO.
- **Shadow-mode parity may hide cold-start divergence**: shadow runs only against recent hits. The first native live run may encounter backlog hits with older `scrape.completed_at`; cutoff semantics must include or exclude them deliberately.
- **Immutable `selector_runs.decisions[]` may grow large**; bound to top-N + deadlettered + optionally top-K discarded, not "all". Set explicit caps.
- **`selection.main.history[]` unbounded growth** on a long-lived hit. Cap to last 20 entries per kind.
- **Iteration 2 was not VPS-validated**; its own residual risks transitively apply to iteration 3 until the VPS cutover of iteration 2 is completed and observed under load.
