# Redis + Livetail + Transparency Analysis

**Generated**: 2026-01-14
**Scope**: runner_service/ directory + frontend/static/js/
**Status**: Current state analysis with gap identification

---

## Executive Summary

The runner service has **excellent livetail infrastructure** but **significant adoption gaps**:

- **Infrastructure**: Production-ready log polling, SSE streaming, structured logging
- **Problem**: Many long-running operations don't use it
- **Impact**: Users see nothing for 10-120 seconds on critical operations

**Critical Gaps (4 operations with zero visibility):**
1. Job Import (5-15s) - No logs at all
2. Job Search (10-30s) - Silent API calls
3. Annotation Generation (20-30s) - Silent LLM + embeddings
4. Job Ingestion (30-120s) - Plain text logs, no cost tracking

---

## Current Redis Architecture

### Production Configuration (SSH Confirmed 2026-01-14)

```
REDIS_URL: redis://n8n-redis:6379
Total Keys: 136
Queue Version: 1038 (active queue management)
```

### Redis Key Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                        REDIS INSTANCE                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ QUEUE MANAGEMENT                                         │   │
│  │ queue:pending     LIST    FIFO job queue                │   │
│  │ queue:running     SET     Currently executing jobs      │   │
│  │ queue:failed      ZSET    Failed jobs (by timestamp)    │   │
│  │ queue:history     LIST    Last 100 completed (capped)   │   │
│  │ queue:item:{id}   HASH    Job metadata (7-day TTL)      │   │
│  │ queue:version     STRING  Counter for polling           │   │
│  │ queue:events      PUBSUB  Cross-runner broadcasts       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LOG PERSISTENCE                                          │   │
│  │ logs:{run_id}:buffer  LIST    Raw log lines (max 1000)  │   │
│  │ logs:{run_id}:meta    HASH    Status, expected_count    │   │
│  │ logs:{run_id}:layers  STRING  Layer status JSON         │   │
│  │ TTL: 6 hours after completion                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ STATE PERSISTENCE                                        │   │
│  │ run:{run_id}       STRING  Run state JSON (24hr TTL)    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Livetail Implementation Analysis

### Log Flow: Backend → Frontend

```
StructuredLogger (Python)
    │ Emits JSON to stdout
    ▼
Runner captures subprocess stdout
    │ Appends to in-memory RunState.logs
    │ Fire-and-forget: RPUSH logs:{run_id}:buffer
    ▼
LogPoller (Frontend, 200ms interval)
    │ GET /api/logs/{run_id}?since={nextIndex}
    │ Receives: logs[], next_index, status, expected_log_count
    ▼
Alpine.js CLI Store
    │ Normalizes logs (backend, cost, tier)
    │ Parses structured JSON
    ▼
CLI Panel Template
    │ Renders with icons, colors, expandable metadata
    ▼
User sees real-time transparency
```

### Frontend Log Polling (log-poller.js)

```javascript
class LogPoller {
    pollInterval = 200;  // 200ms for responsive feel

    async _pollLoop() {
        while (this.polling) {
            const data = await this._fetchLogs();

            for (const log of data.logs) {
                this._emitLog(log);  // Includes backend, cost, traceback
            }

            this.nextIndex = data.next_index;

            // Race condition fix: wait for expected_log_count
            if (data.status === 'completed' || data.status === 'failed') {
                const targetCount = data.expected_log_count ?? this.totalCount;
                if (this.nextIndex >= targetCount) {
                    this._emitComplete(data.status);
                    break;
                }
            }

            await this._sleep(this.pollInterval);
        }
    }
}
```

### Backend Attribution Display

| Backend | Detection | Visual Indicator | Color |
|---------|-----------|------------------|-------|
| Claude CLI | `backend='claude_cli'` or `[Claude CLI]` | 🤖 Robot emoji | Green (emerald-400) |
| LangChain | `backend='langchain'` or `[Fallback]` | ⚠️ Warning emoji | Amber (amber-400) |

### Cost Tracking

- **Per-log**: `cost_usd` field from StructuredLogger
- **Aggregated**: `getBackendStats(runId)` in cli-panel.js
  - Claude CLI calls count + total cost
  - LangChain calls count + total cost
  - Grand total displayed in Backend Stats panel

### Layer Progress

- **Storage**: `runs[runId].layerStatus` in Alpine store
- **Visual**: `○` pending → `🔄` running → `✓` complete → `✗` error
- **Update**: Via `poller.onLayerStatus(callback)`

---

## Livetail Coverage Per Task Category

| Task Category | Has Livetail | Method | Redis Keys Used | Issues |
|---------------|--------------|--------|-----------------|--------|
| **Pipeline Execution** | ✅ Full | HTTP Polling | logs:*, queue:* | None |
| **Streaming Operations** | ✅ Full | SSE + HTTP | logs:* | None |
| **Direct Operations** | ⚠️ Partial | HTTP Polling | logs:* | Sync blocking |
| **Job Ingestion** | ⚠️ Partial | HTTP Polling | logs:* | No structured events |
| **Job Search** | ❌ None | N/A | N/A | **CRITICAL: 10-30s blind** |
| **Annotations** | ❌ None | N/A | N/A | **CRITICAL: 20-30s blind** |
| **Contacts (sync)** | ❌ None | N/A | N/A | 10-15s blind |
| **Master CV** | N/A | N/A | N/A | Fast, no need |
| **Queue Ops** | ✅ Full | QueuePoller | queue:* | None |
| **Log Polling** | ✅ Full | N/A | logs:* | None |

---

## Critical Gap Analysis

### Gap 1: Job Import (job_ingest.py)

**Status**: 🔴 INCOMPLETE - Plain text logs, no cost tracking

**Current Behavior**:
```python
log_callback(f"[ingest_start] source=himalayas, keywords={keywords}...")
log_callback(f"[fetch_complete] Received {len(jobs)} jobs")
```

**What's Missing**:
- No StructuredLogger events (no JSON structure)
- No `cost_usd` field (Claude scorer costs invisible)
- No per-job progress events
- No LLM backend attribution

**Duration**: 30-120 seconds with minimal visibility

---

### Gap 2: Job Search (job_search.py)

**Status**: 🔴 NO LIVETAIL - Silent 10-30s operation

**Current Behavior**:
```python
@router.post("/search")
async def search_jobs(request: SearchRequest):
    result = await service.search(...)  # Silent
    return SearchResponse(...)
```

**What's Missing**:
- No `create_operation_run()` call
- No log callbacks
- No per-source progress (Indeed, Bayt, Himalayas)
- No cache hit/miss visibility

**Duration**: 10-30 seconds with ZERO visibility

---

### Gap 3: Annotation Generation (annotations.py)

**Status**: 🔴 NO LIVETAIL - Silent 20-30s operation

**Current Behavior**:
```python
@router.post("/jobs/{job_id}/generate-annotations")
async def generate_annotations(job_id: str):
    result = generate_annotations_for_job(job_id)  # Blocks
    return GenerateAnnotationsResponse(...)
```

**What's Missing**:
- No `create_operation_run()` call
- No background task (blocks endpoint)
- No per-annotation progress
- No LLM cost tracking

**Duration**: 20-30 seconds with ZERO visibility

---

### Gap 4: Contact Outreach (contacts.py - sync endpoints)

**Status**: 🟡 PARTIAL - Has streaming variant but sync still used

**Sync Endpoint (problematic)**:
```python
@router.post("/{job_id}/contacts/{type}/{index}")
async def regenerate_contact_message(...):
    result = OutreachGenerator().generate(...)  # Silent LLM call
    return {...}
```

**What's Missing**:
- Sync endpoint has no logging
- LLM calls have no cost attribution
- No fallback tracking

**Duration**: 10-15 seconds with no visibility

---

## StructuredLogger Event Coverage

### Events Supported by log_polling.py Parser

The frontend parser recognizes 100+ event types:

```
llm_call_start, llm_call_complete, llm_call_error, llm_call_fallback
layer_start, layer_complete, layer_error, layer_skip
phase_start, phase_complete
subphase_start, subphase_complete
decision_point, validation_result
cv_struct_* (100+ variants)
pipeline_start, pipeline_complete, pipeline_error
```

### Events NOT Being Emitted

| Operation | Expected Events | Currently Emitted |
|-----------|-----------------|-------------------|
| Job Import | llm_call_*, ingest_start, job_scored | Plain text only |
| Job Search | search_start, source_*, cache_hit | None |
| Annotations | annotation_start, annotation_* | None |
| Contact Outreach (sync) | llm_call_*, outreach_* | None |

**Conclusion**: Parser is comprehensive, but **runner_service rarely uses StructuredLogger**.

---

## Logging Behavior Behind Redis Load Distribution

When scaling to multiple runners, logging behavior changes based on task type:

### Tasks That Will Work Unchanged

| Task | Current | Behind Redis | Reason |
|------|---------|--------------|--------|
| Pipeline Execution | ✅ | ✅ | Already writes to Redis |
| Streaming Operations | ✅ | ✅ | Already writes to Redis |
| Queue Operations | ✅ | ✅ | Native Redis operations |
| Log Polling | ✅ | ✅ | Reads from Redis |

### Tasks Needing `logs:owner` Routing

| Task | Current | Behind Redis | Required Change |
|------|---------|--------------|-----------------|
| All operations with run_id | In-memory | Redis lookup | Add `logs:owner:{run_id}` key |

### Tasks Requiring Fixes Before Scaling

| Task | Current | Behind Redis | Required Change |
|------|---------|--------------|-----------------|
| Job Import | Plain text | Plain text | Add StructuredLogger |
| Job Search | No logs | No logs | Add operation tracking |
| Annotations | No logs | No logs | Add operation tracking |
| Contacts (sync) | No logs | No logs | Use streaming only |

**Key Insight**: Operations with no logging TODAY will have no logging AFTER scaling. Fix gaps first.

---

## Recommendations

### Priority 1: Job Import (Highest Impact)

Add StructuredLogger events to `job_ingest.py`:

```python
from src.common.structured_logger import StructuredLogger

logger = StructuredLogger(job_id="ingest")
logger.info("ingest_start", {"source": "himalayas", "keywords": keywords})

for job in jobs:
    logger.info("job_scored", {
        "job_id": job["id"],
        "score": score,
        "cost_usd": cost,
        "backend": "openrouter",
    })

logger.info("ingest_complete", {
    "ingested": stats["ingested"],
    "duplicates": stats["duplicates_skipped"],
    "total_cost_usd": total_cost,
})
```

### Priority 2: Job Search (Longest Blind Wait)

Add operation tracking to `job_search.py`:

```python
run_id = create_operation_run("search", "job-search")
log_cb = create_log_callback(run_id)

log_cb("search_start", {"sources": sources, "job_titles": job_titles})

for source in sources:
    log_cb(f"source_search_start: {source}")
    jobs = await source.search(...)
    log_cb(f"source_search_complete: {source} ({len(jobs)} jobs, cache_hit={cache_hit})")

return SearchResponse(run_id=run_id, ...)
```

### Priority 3: Annotation Generation

Convert to background task with operation tracking:

```python
@router.post("/jobs/{job_id}/generate-annotations")
async def generate_annotations(job_id: str, background_tasks: BackgroundTasks):
    run_id = create_operation_run(job_id, "generate-annotations")
    background_tasks.add_task(_generate_annotations_task, job_id, run_id)
    return {"run_id": run_id, "status": "queued"}

async def _generate_annotations_task(job_id: str, run_id: str):
    log_cb = create_log_callback(run_id)
    log_cb("annotation_start", {"job_id": job_id})
    # ... generate with progress logging
```

### Priority 4: Contact Outreach

Deprecate sync endpoint, use streaming only:

```python
# Remove or deprecate:
# @router.post("/{job_id}/contacts/{type}/{index}")

# Keep only streaming variant:
@router.post("/{job_id}/contacts/{type}/{index}/stream")
async def regenerate_contact_message_stream(...):
    # ... with proper logging
```

---

## Current Limitations

| Issue | Impact | Severity | Mitigation |
|-------|--------|----------|------------|
| Race Condition | Logs not in Redis at completion | Medium | `expected_log_count` |
| Memory Growth | Long runs exceed buffers | Low | Capped at 1000 logs |
| Single-Writer | One runner per run_id | Medium | Add `logs:owner` |
| No Replay | State lost on restart | Medium | 6hr Redis TTL |
| Queue Scan O(N) | Slow job lookup | Low | <1000 items typical |
| Pub/Sub Loss | Events lost if offline | Medium | Poll state endpoint |

---

## Verification Checklist

After fixing each gap, verify:

- [ ] Operation creates `create_operation_run()`
- [ ] Log callbacks receive events
- [ ] Events persist to Redis (`logs:{run_id}:buffer`)
- [ ] Log polling endpoint returns parsed events
- [ ] Frontend CLI panel displays logs
- [ ] `cost_usd` fields populated
- [ ] Error tracebacks captured in metadata
- [ ] Background tasks complete without blocking
- [ ] Redis TTL set on completion (6 hours)
