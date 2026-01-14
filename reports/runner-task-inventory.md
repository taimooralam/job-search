# Runner Service Task Inventory

**Generated**: 2026-01-14
**Source**: runner_service/ directory analysis
**Total Endpoints**: 76 unique endpoints across 13 categories

---

## Executive Summary

The runner service is a FastAPI-based pipeline execution engine with:
- **76 unique HTTP endpoints** for job processing, CV generation, and pipeline management
- **Multi-trigger task execution**: HTTP sync, HTTP async, SSE streaming, Redis queue
- **Redis integration**: Queue management, log persistence, state recovery
- **No internal scheduled tasks**: External scheduling via Docker cron (job-ingest service)

---

## Task Categories Overview

| Category | Count | Trigger Type | Redis Role |
|----------|-------|--------------|------------|
| Pipeline Execution | 3 | HTTP POST | Queue + Logs |
| Job Import | 2 | HTTP POST | None (sync) |
| Status/Monitoring | 4 | HTTP GET/POST | State lookup |
| Direct Operations | 6 | HTTP POST (sync) | Logs only |
| Streaming Operations | 10 | HTTP POST (async + SSE) | Logs + State |
| Queue Management | 7 | HTTP GET/POST | Full queue access |
| Job Ingestion | 8 | HTTP POST (async) | Logs + State |
| Job Search | 9 | HTTP GET/POST | Cache |
| Contacts Management | 5 | HTTP GET/POST/DELETE | Partial logs |
| Master CV Management | 12 | HTTP GET/PUT/POST | None |
| Annotations | 4 | HTTP GET/POST | Partial logs |
| Log Polling | 2 | HTTP GET | Log buffer read |
| Health/Diagnostics | 3 | HTTP GET | Connection test |
| **TOTAL** | **76** | Mixed | Mixed |

---

## Detailed Task Inventory

### A. Pipeline Execution Tasks

**File**: `runner_service/app.py`

| Endpoint | Method | Line | Description | Duration | Redis Role |
|----------|--------|------|-------------|----------|------------|
| `/jobs/run` | POST | 415 | Execute pipeline for single job | 5-30 min | Queue + Logs |
| `/jobs/run-bulk` | POST | 433 | Execute pipeline for multiple jobs | N × (5-30 min) | Queue + Logs |
| `/api/jobs/{job_id}/extract` | POST | 712 | Trigger job extraction subprocess | 1-5 min | Logs only |

**Execution Pattern**:
- Creates `run_id`, enqueues to Redis `queue:pending`
- Background worker claims and executes via `_execute_pipeline_task()`
- Logs streamed to Redis `logs:{run_id}:buffer`

---

### B. Job Import Tasks

**File**: `runner_service/app.py`

| Endpoint | Method | Line | Description | Duration | Redis Role |
|----------|--------|------|-------------|----------|------------|
| `/jobs/import-linkedin` | POST | 475 | Scrape & import LinkedIn job | 5-15s | None |
| `/jobs/import-indeed` | POST | 595 | Scrape & import Indeed job | 5-15s | None |

**Gap Identified**: No livetail logging - operations run synchronously without progress visibility.

---

### C. Pipeline Status & Monitoring

**File**: `runner_service/app.py`

| Endpoint | Method | Line | Description | Redis Role |
|----------|--------|------|-------------|------------|
| `/jobs/{run_id}/status` | GET | 789 | Poll pipeline run status | State lookup |
| `/jobs/{run_id}/progress` | GET | 833 | Get layer-by-layer progress | State lookup |
| `/jobs/{run_id}/logs` | GET | 868 | Stream logs for run | Log buffer |
| `/jobs/{run_id}/cancel` | POST | 810 | Cancel running pipeline | Queue update |

---

### D. Direct Operations (Synchronous)

**File**: `runner_service/routes/operations.py`

| Endpoint | Method | Line | Description | Duration | Redis Role |
|----------|--------|------|-------------|----------|------------|
| `/{job_id}/structure-jd` | POST | 499 | Parse job description | 5-15s | Logs only |
| `/{job_id}/research-company` | POST | 579 | Research company intelligence | 30-90s | Logs only |
| `/{job_id}/generate-cv` | POST | 661 | Generate tailored CV | 2-5 min | Logs only |
| `/{job_id}/full-extraction` | POST | 744 | All extraction operations | 5-10 min | Logs only |
| `/{job_id}/estimate-cost` | GET | 823 | Estimate LLM cost | <1s | None |
| `/{job_id}/synthesize-persona` | POST | 1563 | Generate candidate persona | 30-60s | Logs only |

**Note**: These endpoints block until completion - prefer streaming variants for long operations.

---

### E. Streaming Operations (Async + SSE)

**File**: `runner_service/routes/operations.py`

| Endpoint | Method | Line | Description | Redis Role |
|----------|--------|------|-------------|------------|
| `/{job_id}/research-company/start` | POST | 959 | Start research streaming | Logs + State |
| `/{job_id}/research-company/stream` | POST | 966 | SSE log stream | Log buffer |
| `/{job_id}/generate-cv/start` | POST | 1064 | Start CV generation | Logs + State |
| `/{job_id}/generate-cv/stream` | POST | 1071 | SSE log stream | Log buffer |
| `/{job_id}/full-extraction/start` | POST | 1170 | Start full extraction | Logs + State |
| `/{job_id}/full-extraction/stream` | POST | 1177 | SSE log stream | Log buffer |
| `/{job_id}/all-ops/start` | POST | 1304 | Start all operations | Logs + State |
| `/{job_id}/all-ops/stream` | POST | 1311 | SSE log stream | Log buffer |
| `/{job_id}/scrape-form-answers/start` | POST | 1441 | Start form scraping | Logs + State |
| `/{job_id}/scrape-form-answers/stream` | POST | 1448 | SSE log stream | Log buffer |

**Pattern**: `/start` creates operation_run + returns run_id, `/stream` connects to SSE for real-time logs.

---

### F. Queue Management

**File**: `runner_service/app.py`

| Endpoint | Method | Line | Description | Redis Key |
|----------|--------|------|-------------|-----------|
| `/queue/state` | GET | 1517 | Get entire queue state | queue:* |
| `/queue/{queue_id}/retry` | POST | 1560 | Retry failed item | queue:failed |
| `/queue/{queue_id}/cancel` | POST | 1580 | Cancel pending item | queue:pending |
| `/queue/{queue_id}/dismiss` | POST | 1600 | Dismiss failed item | queue:failed |
| `/queue/item/{job_id}` | GET | 1620 | Check job queue status | queue:item:* |
| `/queue/cleanup` | POST | 1637 | Clean stale items | queue:* |
| `/queue/clear` | POST | 1651 | Admin: Clear all queue data | queue:* |

**Data Structures**:
- `queue:pending` - LIST (FIFO)
- `queue:running` - SET
- `queue:failed` - ZSET (sorted by timestamp)
- `queue:history` - LIST (capped at 100)
- `queue:item:{id}` - HASH (7-day TTL)

---

### G. Job Ingestion

**File**: `runner_service/routes/job_ingest.py`

| Endpoint | Method | Line | Source | Duration | Redis Role |
|----------|--------|------|--------|----------|------------|
| `/jobs/ingest/himalaya` | POST | 107 | Himalayas API | 30-60s | Logs + State |
| `/jobs/ingest/indeed` | POST | 260 | Indeed.com | 60-120s | Logs + State |
| `/jobs/ingest/bayt` | POST | 425 | Bayt.com | 30-60s | Logs + State |
| `/jobs/ingest/state/{source}` | GET | 576 | Get last fetch | - | State lookup |
| `/jobs/ingest/state/{source}` | DELETE | 607 | Reset ingest state | - | State mutation |
| `/jobs/ingest/history/{source}` | GET | 628 | Get ingest history | - | State lookup |
| `/jobs/ingest/{run_id}/logs` | GET | 684 | Stream ingest logs | - | Log buffer |
| `/jobs/ingest/{run_id}/result` | GET | 697 | Poll ingest result | - | State lookup |

**Gap Identified**: Logs are plain text, no StructuredLogger events, no cost tracking.

---

### H. Job Search

**File**: `runner_service/routes/job_search.py`

| Endpoint | Method | Line | Description | Duration | Redis Role |
|----------|--------|------|-------------|----------|------------|
| `/job-search/search` | POST | 142 | Execute job search | 10-30s | Cache |
| `/job-search/index` | GET | 184 | Query searchable index | <1s | Cache |
| `/job-search/presets` | GET | 231 | Get search presets | <1s | None |
| `/job-search/{job_id}` | GET | 247 | Get job details | <1s | None |
| `/job-search/promote/{job_id}` | POST | 261 | Promote to level-2 | <1s | None |
| `/job-search/hide/{job_id}` | POST | 278 | Hide job | <1s | None |
| `/job-search/unhide/{job_id}` | POST | 291 | Unhide job | <1s | None |
| `/job-search/cache` | DELETE | 302 | Clear search cache | <1s | Cache wipe |
| `/job-search/stats` | GET | 318 | Get index statistics | <1s | Cache stats |

**Gap Identified**: `/job-search/search` takes 10-30s with ZERO progress visibility.

---

### I. Contacts Management

**File**: `runner_service/routes/contacts.py`

| Endpoint | Method | Line | Description | Duration | Redis Role |
|----------|--------|------|-------------|----------|------------|
| `/{job_id}/contacts` | GET | 317 | List all contacts | <1s | None |
| `/{job_id}/contacts` | POST | 368 | Add contacts | <1s | None |
| `/{job_id}/contacts/{type}/{index}` | DELETE | 475 | Delete contact | <1s | None |
| `/{job_id}/contacts/{type}/{index}` | POST | 540 | Regenerate message | 10-15s | Logs only |
| `/{job_id}/contacts/generate-all-messages` | POST | 760 | Batch generate messages | 30-60s | Logs only |

**Gap Identified**: Sync endpoints for LLM operations (regenerate, batch generate) lack progress visibility.

---

### J. Master CV Management

**File**: `runner_service/routes/master_cv.py`

| Endpoint | Method | Line | Description | Redis Role |
|----------|--------|------|-------------|------------|
| `/metadata` | GET | 243 | Get candidate metadata | None |
| `/metadata` | PUT | 280 | Update metadata | None |
| `/metadata/roles/{role_id}` | PUT | 346 | Update specific role | None |
| `/cv` | GET | 406 | Get master CV | None |
| `/cv` | PUT | 442 | Update master CV | None |
| `/cv/export` | POST | 500 | Export CV (PDF/DOCX) | None |
| `/cv/validate` | GET | 559 | Validate CV structure | None |
| `/cv/health` | GET | 594 | Check CV data integrity | None |
| `/cv-editor/state` | PUT | 634 | Save editor state | None |
| `/cv-editor/state` | GET | 696 | Load editor state | None |
| `/cv-editor/publish` | POST | 749 | Publish CV changes | None |
| `/cv-editor/upload` | GET | 836 | Upload to Google Drive | None |

**Note**: All operations are fast (<5s) and synchronous - no livetail needed.

---

### K. Annotations

**File**: `runner_service/routes/annotations.py`

| Endpoint | Method | Line | Description | Duration | Redis Role |
|----------|--------|------|-------------|----------|------------|
| `/jobs/{job_id}/generate-annotations` | POST | 95 | Generate annotations | 20-30s | Logs only |
| `/user/annotation-priors` | GET | 143 | Get annotation stats | <1s | None |
| `/user/annotation-priors/rebuild` | POST | 173 | Rebuild priors | 5-10s | Logs only |
| `/user/annotation-feedback` | POST | 220 | Capture feedback | <1s | None |

**Gap Identified**: `generate-annotations` runs silently for 20-30s with no progress visibility.

---

### L. Log Polling

**File**: `runner_service/routes/log_polling.py`

| Endpoint | Method | Line | Description | Redis Key |
|----------|--------|------|-------------|-----------|
| `/operations/{run_id}` | GET | 479 | Poll logs with pagination | logs:{run_id}:buffer |
| `/operations/{run_id}/status` | GET | 631 | Get operation status | logs:{run_id}:meta |

**Pattern**: Frontend polls every 200ms with `?since={nextIndex}` for incremental log fetch.

---

### M. Health & Diagnostics

**File**: `runner_service/app.py`

| Endpoint | Method | Line | Description | Redis Role |
|----------|--------|------|-------------|------------|
| `/health` | GET | 916 | Service health check | Connection test |
| `/diagnostics` | GET | 957 | System diagnostics | Queue stats |
| `/api/claude/status` | GET | 734 | Claude CLI status | None |

---

## Scheduled/Background Tasks

**Currently: NO internal scheduled tasks.**

The `job-ingest` Docker service runs on a 6-hour cron schedule externally via Docker, but no internal APScheduler/Celery/cron jobs exist within the runner service itself.

---

## Redis Key Summary

| Key Pattern | Type | Purpose | TTL |
|-------------|------|---------|-----|
| `queue:pending` | LIST | FIFO job queue | Persistent |
| `queue:running` | SET | Currently executing jobs | Persistent |
| `queue:failed` | ZSET | Failed jobs (by timestamp) | Persistent |
| `queue:history` | LIST | Last 100 completed | Persistent |
| `queue:item:{id}` | HASH | Job metadata | 7 days |
| `queue:version` | STRING | Polling version counter | Persistent |
| `queue:events` | PUBSUB | Cross-runner broadcasts | N/A |
| `logs:{run_id}:buffer` | LIST | Raw log lines (max 1000) | 6 hours |
| `logs:{run_id}:meta` | HASH | Status, expected_count | 6 hours |
| `logs:{run_id}:layers` | STRING | Layer status JSON | 6 hours |
| `run:{run_id}` | STRING | Run state JSON | 24 hours |
| `search:*` | Various | Job search cache | Variable |

---

## Gap Summary: Operations Missing Livetail

| Operation | Duration | Current Visibility | Priority |
|-----------|----------|-------------------|----------|
| Job Import (LinkedIn/Indeed) | 5-15s | None | High |
| Job Ingestion (Himalaya/Indeed/Bayt) | 30-120s | Plain text only | High |
| Job Search | 10-30s | None | High |
| Annotation Generation | 20-30s | None | High |
| Contact Outreach (sync) | 10-15s | None | Medium |
