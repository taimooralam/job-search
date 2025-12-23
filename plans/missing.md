# Implementation Gaps

## Completed (2025-12-23)

- [x] BUG FIX: Claude CLI output format - Changed from JSON to text format to avoid CLI bug #8126 where json format sometimes returns empty result field. Simplified error handling to use stderr/stdout directly. Text format returns raw LLM response (no JSON wrapper, no cost/token metadata) ✅ **COMPLETED 2025-12-24**
- [x] FEATURE: Job Ingestion Management UI - New `/ingestion` page for managing ingestion runs with history endpoint `GET /ingest/history/{source}` returning last 50 runs from MongoDB `system_state` collection. Added navigation link in header ✅ **COMPLETED 2025-12-23**
- [x] BUG FIX: Batch operations run in parallel - Replaced BackgroundTasks with submit_service_task() using ThreadPoolExecutor fire-and-forget pattern (4 workers max, separate from 8-worker DB pool). Updated full-extraction, research-company, generate-cv, and all-ops batch endpoints ✅ **COMPLETED 2025-12-23**
- [x] FEATURE: Discard Selected bulk action - Added "Discard Selected" button to job listing toolbar with confirmation dialog and status filter integration ✅ **COMPLETED 2025-12-23**
- [x] BUG 4: Section coverage indicators - Added data-section attributes to `_annotation_list.html` and DOM update code to `jd-annotation.js` updateCoverage() method ✅ **COMPLETED 2025-12-22**
- [x] BUG 1: Verbose logging for prepare-annotations - Added progress_callback and log_callback parameters to StructureJDService.execute() and updated routes/operations.py to pass callbacks ✅ **COMPLETED 2025-12-22**
- [x] BUG 3/5: CV generation coroutine error - Added _run_async_safely() method to orchestrator.py using ThreadPoolExecutor to handle nested event loops ✅ **COMPLETED 2025-12-22**
- [x] BUG 3/5 (second occurrence): CV generation coroutine error in _generate_all_role_bullets() - Wrapped generate_all_roles_from_variants() async call with _run_async_safely() at line 767 ✅ **COMPLETED 2025-12-23**
- [x] BUG 2: Discover contacts cache logic - Modified company_research_service.py to check for existing contacts before returning cached data (partial cache hit triggers people_mapper) ✅ **COMPLETED 2025-12-22**

## Current Blockers

| Issue | Impact | Fix |
|-------|--------|-----|
| (None identified) | - | - |

## Remaining Gaps (Non-Blocking)

### Core Features

- [ ] Pipeline validation and end-to-end testing
- [ ] Performance optimization for bulk job processing
- [ ] Advanced CV matching algorithm refinement
- [ ] **GAP-DIST**: Distributed Worker Pattern for Multi-Container Execution
  - **Status:** PLANNED
  - **Priority:** Medium
  - **Current State:**
    - 3 runner containers behind Traefik load balancer
    - Redis queue used for UI visibility only
    - Batch requests go to single container (Traefik routes per-request)
  - **Desired State:**
    - Each container runs a worker loop that pulls jobs from Redis queue
    - Jobs automatically distribute across whichever container pulls them first
    - True horizontal scaling for batch operations
  - **Implementation Notes:**
    - Add `queue_manager.dequeue()` worker loop in each container
    - Handle graceful shutdown (drain in-flight jobs)
    - Add health check for worker status
    - Consider using Redis BRPOP for blocking dequeue

### UI/UX

- [ ] Dark mode theme support
- [ ] Mobile responsiveness improvements
- [ ] Rich text formatting enhancements

### Integration

- [ ] Google Drive sync optimization
- [ ] LangSmith tracing improvements
- [ ] FireCrawl error recovery mechanisms

### Testing

- [ ] Comprehensive integration tests
- [ ] Load testing for concurrent users
- [ ] Cross-browser compatibility testing
