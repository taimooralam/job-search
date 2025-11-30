# Implementation Gaps

**Last Updated**: 2025-11-30 (Added GAP-059 to GAP-062 from production testing)

> **See also**: `plans/architecture.md` | `plans/next-steps.md` | `bugs.md`

---

## Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **P0 (CRITICAL)** | 3 (2 fixed, 1 open) | Must fix immediately - system broken or data integrity at risk |
| **P1 (HIGH)** | 17 | Fix this week - user-facing bugs or important features |
| **P2 (MEDIUM)** | 24 | Fix this sprint - enhancements and incomplete features |
| **P3 (LOW)** | 18 | Backlog - nice-to-have improvements |
| **Total** | **62** (2 fixed, 60 open) | All identified gaps |

**Test Coverage**: 708 unit tests passing, 48 E2E tests disabled, integration tests pending

---

## P0: CRITICAL (Must Fix Immediately)

### GAP-001: CV V2 - Hallucinated Skills
**Priority**: P0 CRITICAL | **Status**: ✅ FIXED (2025-11-30) | **Effort**: 1.5 days
**Impact**: CVs claim Java/PHP/Spring Boot expertise candidate DOESN'T have

**Root Cause**: Hardcoded skill lists in `src/layer6_v2/header_generator.py:200-226`

**Fix Implemented**:
1. Added `get_all_hard_skills()`, `get_all_soft_skills()`, `get_skill_whitelist()` to CVLoader
2. Replaced hardcoded skill lists with dynamic whitelist from master-CV
3. Only skills from `data/master-cv/roles/*.md` now appear in generated CVs
4. JD keywords only included if they have evidence in experience bullets

**Commit**: `85bebfea` - fix(cv-v2): prevent hallucinated skills and add dynamic categories

---

### GAP-002: CV V2 - Static Core Skills Categories
**Priority**: P0 CRITICAL | **Status**: ✅ FIXED (2025-11-30) | **Effort**: 1.5 days
**Impact**: All CVs have identical 4 categories instead of JD-derived dynamic categories

**Root Cause**: Hardcoded loop in `src/layer6_v2/header_generator.py:495`

**Fix Implemented**:
1. Created `src/layer6_v2/category_generator.py` with LLM-driven category clustering
2. Updated `header_generator.py` with `use_dynamic_categories` parameter (default: True)
3. Categories now derived from JD keywords and role type
4. Example output: ["Cloud Platform Engineering", "Backend Architecture", "Technical Leadership"]

**Commit**: `85bebfea` - fix(cv-v2): prevent hallucinated skills and add dynamic categories

---

### GAP-003: VPS Backup Strategy - No Backups
**Priority**: P0 CRITICAL | **Status**: PENDING | **Effort**: 20-30 hours
**Impact**: No backups for generated CVs/dossiers; disk failure = total data loss

**Current State**:
- VPS has no backup mechanism for generated artifacts
- MongoDB Atlas has PITR but never tested
- API keys exist only on VPS (no secure vault)

**Fix Required**:
1. Implement S3 backup for VPS artifacts
2. Create disaster recovery plan
3. Test MongoDB backup restoration

**Report**: `reports/agents/doc-sync/2025-11-30-vps-backup-assessment.md`

---

### GAP-004: Credential Backup Vault - No Secure Storage
**Priority**: P0 CRITICAL | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: API keys/MongoDB URI only on VPS; loss = system failure

**Fix Required**:
- AWS Secrets Manager or Git-crypt encrypted vault
- Document all credentials with recovery procedures

---

### GAP-046: Export PDF Button Not Working on Detail Page ✅ COMPLETE
**Priority**: P0 CRITICAL | **Status**: COMPLETE | **Effort**: 1-3 hours
**Impact**: Users can now export CV from job detail page

**Description**: Fixed the "Export PDF" button on job detail page. The issue was that the request body (tiptap_json) wasn't being sent to the PDF service.

**Root Cause**: The proxy endpoint was prepared to call `/cv-to-pdf` but forgot to include `json=pdf_request` in the requests.post() call.

**Fix Applied** (2024-11-30):
1. Updated `frontend/app.py` `generate_cv_pdf_from_editor()` to pass `json=pdf_request`
2. Fixed error message references from `runner_url` to `pdf_service_url`
3. Improved error messages for clarity

---

## P1: HIGH (Fix This Week)

### GAP-005: CV V2 - Missing STAR Format
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 1 day
**Impact**: Experience bullets lack challenge→skill→result structure, appear generic

**Root Cause**: No STAR enforcement in `src/layer6_v2/prompts/role_generation.py`

**Current Bullet** (generic):
> "Led migration to microservices architecture, improving system reliability"

**Required STAR Bullet** (specific):
> "Facing 30% annual outage increase [SITUATION], led 12-month migration to event-driven microservices [TASK] using AWS Lambda and EventBridge [ACTION/SKILLS], achieving 75% incident reduction [RESULT]"

**Fix Required**:
1. Add STAR template to role generation prompts
2. Add validator to reject bullets without skill mentions
3. Add retry logic for non-STAR bullets

**Files**: `src/layer6_v2/prompts/role_generation.py`, `src/layer6_v2/role_qa.py`

---

### GAP-006: CV V2 - Markdown Asterisks in Output
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Every generated CV has `**text**` formatting needing manual removal

**Root Cause**: LLM prompts don't forbid markdown; `to_markdown()` methods add `**` syntax

**Fix Required**:
1. Add "no markdown" instruction to all generation prompts
2. Create `src/common/markdown_sanitizer.py` for post-processing

**Files**: `src/layer6_v2/types.py`, `src/layer6_v2/prompts/`, `src/layer6_v2/role_generator.py`
**Bug**: bugs.md #14

---

### GAP-007: Time-Based Filters Bug
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: 1h/3h/6h/12h quick filters return all-day results instead of hour-based

**Root Cause**: MongoDB query timezone/format mismatch or frontend parameter not reaching backend

**Files**: `frontend/templates/index.html`, `frontend/app.py`, MongoDB `createdAt` field
**Bug**: bugs.md #12
**Plan**: `plans/time-filter-bug-fix-and-enhancement.md`

---

### GAP-008: GitHub Workflow - Master-CV Sync
**Priority**: P1 HIGH | **Status**: FIXED (pending commit) | **Effort**: 1 hour
**Impact**: VPS only receives `master-cv.md` not `data/master-cv/` directory with role skill files

**Root Cause**: `.github/workflows/runner-ci.yml:147` only copies single file

**Fix**: Updated to include `data/master-cv` in source files (commit pending)

---

### GAP-009: CV Editor Not Synced with Detail Page
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: Generated CV content (TipTap editor) doesn't display on job detail view

**Component**: `frontend/templates/job_detail.html`
**Bug**: bugs.md #11

---

### GAP-010: Database Backup Monitoring
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 3-4 hours
**Impact**: MongoDB Atlas PITR enabled but never tested

**Fix Required**:
- Test monthly restore
- Document recovery procedures
- Verify backup retention

---

### GAP-011: LinkedIn 300 Char Message Limit ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2 hours
**Impact**: LinkedIn connection messages now enforced to ≤300 characters

**Fix Applied** (2024-11-30):
1. Updated prompts with STRICT 300 char limit and example (280-char target)
2. Changed signature from "Calendly link" to "Best. Taimoor Alam" (fits in limit)
3. Added intelligent truncation in `_validate_linkedin_message()` that:
   - Truncates at sentence boundaries
   - Preserves signature
   - Falls back to word boundary truncation
4. Updated `outreach_generator.py` with 300-char enforcement
5. Updated fallback messages to include signature
6. UI character counter deferred to future (Phase 3 of plan)

**Files Modified**: `src/layer5/people_mapper.py`, `src/layer6/outreach_generator.py`
**Plan**: `plans/linkedin-message-character-limit.md`

---

### GAP-012: TODO - Inline Mark Parsing Not Implemented
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Bold/italic marks not parsed in CV text conversion

**Location**: `frontend/app.py:2116`, `runner_service/app.py:476`
```python
# TODO: Implement proper inline mark parsing
return [{"type": "text", "text": text}]  # Just returns plain text
```

---

### GAP-013: Bare Except Block - Bad Practice
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 30 minutes
**Impact**: Swallows all exceptions, hides bugs

**Location**: `src/layer5/people_mapper.py:479`
```python
except:  # Should catch specific exceptions
    continue
```

---

### GAP-047: Line Spacing Bug in CV Editor
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-4 hours
**Impact**: Line height/spacing inconsistent in TipTap editor vs PDF output

**Description**: Line spacing in the CV editor doesn't match PDF output, breaking WYSIWYG experience.

**Root Cause**: CSS line-height values in `.ProseMirror` may not match PDF rendering styles.

**Fix Required**:
1. Audit `.ProseMirror` CSS line-height values
2. Match with PDF service CSS
3. Test across all paragraph types

**Related**: GAP-049 (WYSIWYG Consistency)

---

### GAP-048: Line Spacing Bug in CV Generation
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-4 hours
**Impact**: Generated CVs have inconsistent line spacing compared to original master-cv

**Description**: CV generation (Layer 6 V2) produces text with different line spacing than expected.

**Fix Required**:
1. Review `src/layer6_v2/` generation logic
2. Ensure consistent spacing in output
3. Match output to editor and PDF standards

---

### GAP-049: Job Status Not Updating After Pipeline Completion ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-3 hours
**Impact**: Job status now updates to "ready for applying" after pipeline completion

**Description**: Fixed - job status now updates correctly after pipeline completion.

**Root Cause**: Same as GAP-050 - the `_persist_to_mongodb()` function couldn't find the job record because it was searching by `jobId` instead of `_id` (ObjectId).

**Fix Applied** (2024-11-30): See GAP-050 fix. The status update (`status: 'ready for applying'`) was already implemented in `output_publisher.py` but wasn't executing because the job lookup was failing.

---

### GAP-050: Pipeline State Not Persisting to MongoDB ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-3 hours
**Impact**: Pipeline outputs now persist correctly to MongoDB

**Description**: Fixed pipeline state persistence to MongoDB. Fields like pain_points, fit_score, and contacts now save correctly.

**Root Cause Found**: The `_persist_to_mongodb()` function in `output_publisher.py` was searching for jobs by `jobId` (integer) field, but jobs are stored with `_id` (ObjectId) as the primary identifier. When the job_id was an ObjectId string, the search would fail silently.

**Fix Applied** (2024-11-30):
1. Added ObjectId search as primary strategy in `_persist_to_mongodb()`
2. Fall back to integer jobId for legacy schema compatibility
3. Fall back to string jobId as last resort
4. Added detailed logging to track which strategy succeeded

---

### GAP-051: Missing Companies Bug in Contact Discovery
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-4 hours
**Impact**: Contact discovery returns incomplete results for some companies

**Description**: FireCrawl contact discovery not finding companies/contacts that should exist.

**Fix Required**:
- Investigate FireCrawl search parameters
- Check for rate limiting or API issues
- Improve search query patterns

---

### GAP-059: VPS Health Indicator Shows Grey (Unknown State)
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 1-2 hours
**Impact**: VPS health status not visible to users; unclear if runner service is online

**Description**: The VPS health indicator on the dashboard shows grey instead of green/red. Grey indicates "unknown" state - the `/api/health` endpoint returned unexpected data, timed out, or failed.

**Possible Causes**:
1. VPS runner service not running (`docker compose ps`)
2. Port 8000 not exposed/accessible from Vercel frontend
3. Network timeout (default 5s) exceeded
4. CORS issues on `/health` endpoint
5. Runner URL misconfigured (`RUNNER_URL` env var)

**Debug Steps**:
1. `curl http://72.61.92.76:8000/health` - Test runner directly
2. Browser DevTools → Network tab → Check `/api/health` response
3. Check Vercel logs for health check errors
4. Verify `RUNNER_URL` env var in Vercel settings

**Files**:
- `frontend/app.py:726-838` - Health endpoint aggregation
- `frontend/templates/base.html:1629-1697` - JavaScript polling
- `runner_service/app.py:372-384` - Runner health endpoint

---

### GAP-061: Budget/Alert Dashboard Widgets Not Visible
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-4 hours
**Impact**: Budget monitoring and alerts not visible despite being fully implemented

**Analysis**:
The budget and alert modules are **FULLY IMPLEMENTED** with 708 unit tests passing. The issue is visibility, not missing code.

**Implemented Components** (all working):
- `src/common/token_tracker.py` (1013 lines) - Token tracking with 12-model pricing
- `src/common/alerting.py` (581 lines) - Alert system with Slack
- `src/common/metrics.py` (709 lines) - Metrics collector
- `frontend/templates/partials/budget_monitor.html` (155 lines)
- `frontend/templates/partials/alert_history.html` (133 lines)
- `frontend/templates/partials/cost_trends.html` (110 lines)
- 8 Flask API endpoints (`/api/budget`, `/api/alerts`, `/partials/*`)

**Why Not Visible - Investigate**:
1. HTMX not loading widgets properly (check `hx-get` attributes)
2. Environment variables not set on Vercel:
   - `ENABLE_ALERTING=true`
   - `TOKEN_BUDGET_USD=100.0`
   - `ENABLE_TOKEN_TRACKING=true`
3. Partials not included in index.html template
4. JavaScript errors preventing render
5. CSS hiding elements

**Debug Steps**:
1. Check if `/api/budget` returns data (curl or browser)
2. Check if `/partials/budget-monitor` returns HTML
3. Verify widgets included in `index.html`
4. Check browser console for errors
5. Verify env vars on Vercel dashboard

---

### GAP-062: Job Extraction Not Showing on Detail Page
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: Extracted JD data missing from detail page when not pre-populated

**Description**: Job extraction results (requirements, qualifications, responsibilities parsed from JD) don't display on job detail page if the extracted fields weren't already present in the MongoDB document.

**Possible Causes**:
1. Template conditional hides empty fields completely (no "N/A" fallback)
2. Extraction data saved to wrong field name or collection
3. Frontend not fetching extracted data from correct MongoDB field
4. Race condition - display renders before extraction completes

**Files to Check**:
- `frontend/templates/job_detail.html` - Template conditionals
- `src/layer1_4/jd_extractor.py` - Extraction field names
- `frontend/app.py` - Job detail endpoint, field mapping

---

## P2: MEDIUM (Fix This Sprint)

### GAP-014: CV V2 - Dynamic Tagline for Location
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 0.5 days
**Impact**: Middle East jobs need "International Relocation in 2 months" tagline

**Trigger Countries**: Saudi Arabia, UAE, Kuwait, Qatar, Oman, Pakistan

**Implementation**:
1. Parse job location from `extracted_jd.location`
2. Check against MIDDLE_EAST_COUNTRIES list
3. Inject tagline in header

**Files**: `src/layer6_v2/orchestrator.py:315-333`, `src/common/constants.py`

---

### GAP-015: CV V2 - Color Scheme Change
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 0.5 days
**Impact**: Current teal/green doesn't suit; need dark greyish blue

**Current**: `#0f766e` (teal/green)
**Required**: `#475569` (slate-600 dark greyish blue)

**Additional**: Detail page design must match editor design (consistency)

**Files**: `frontend/templates/base.html`, `job_detail.html`, `pdf_service/`

---

### GAP-016: DateTime Range Picker Enhancement
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 1-2 hours
**Impact**: Date filter only allows day-level; users need hour/minute precision

**Fix**: Use HTML5 `datetime-local` input instead of `date` input
**Files**: `frontend/templates/index.html` (lines 175-188)

---

### GAP-017: E2E Tests Disabled
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: 48 Playwright tests exist but disabled due to config issues

**Plan**: `plans/e2e-testing-implementation.md`

---

### GAP-018: Integration Tests Not in CI/CD
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 3-4 hours
**Impact**: No automated integration testing on push

---

### GAP-019: Code Coverage Not Tracked
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Unknown test coverage percentage

---

### GAP-020: STAR Selector Disabled/Incomplete
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Feature flag `ENABLE_STAR_SELECTOR=false` by default

**Missing**: Embeddings, caching, graph edges for STAR selection

---

### GAP-021: Remote Publishing Disabled
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Feature flag `ENABLE_REMOTE_PUBLISHING=false` by default

**Missing**: Google Drive/Sheets integration not tested

---

### GAP-022: Job Application Progress UI Frontend
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Backend API done; frontend components pending

**Completed**: `/api/dashboard/application-stats`, `/jobs/{run_id}/progress`
**Missing**: Frontend progress bar, layer indicators, real-time updates

---

### GAP-023: Application Form Mining (Layer 1.5)
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Form field extraction from job postings not implemented

---

### GAP-024: V2 Parser/Tailoring Not Implemented
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: 18+ unit tests skipped with reason "Will fail until V2 parser/tailoring implemented"

**Evidence**: `tests/unit/test_layer6_cv_generator_v2.py` - multiple skipped tests

---

### GAP-025: V2 Prompts Not Implemented
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Multiple tests skipped for V2 prompts (opportunity mapper, cover letter, CV QA)

**Evidence**:
- `tests/unit/test_layer4_opportunity_mapper_v2.py` - 6 skipped
- `tests/unit/test_layer6_cover_letter_generator_v2.py` - 8 skipped

---

### GAP-052: Phase 5 - WYSIWYG Page Break Visualization
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 8-10 hours
**Impact**: No visual page break indicators; users surprised by PDF page breaks

**Description**: Add visual page break indicators to CV editor showing where content breaks across pages when exported to PDF. Provides true WYSIWYG experience.

**Key Components**:
1. Page Break Calculator - compute break positions from content height
2. Page Break Renderer - insert visual break indicators in DOM
3. Dynamic Update Integration - recalculate on content/style changes
4. Detail Page Integration - show breaks in main CV display

**Dependencies**: Phase 1-4 complete ✅

**Plan**: `plans/phase5-page-break-visualization.md`

---

### GAP-053: Phase 6 - PDF Service Separation
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: PDF generation tightly coupled to runner service; scalability limited

**Description**: Separate PDF generation from runner service into dedicated Docker container for better separation of concerns and independent scaling.

**Benefits**:
- Clear separation of concerns (pipeline ≠ PDF rendering)
- Independent scaling and resource management
- Easy to add new document types (cover letters, dossiers)
- PDF service isolated, can restart without affecting pipeline

**Plan**: `plans/phase6-pdf-service-separation.md`

---

### GAP-054: CV Editor WYSIWYG Consistency
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Editor and detail page display render differently; breaks WYSIWYG

**Description**: The CV editor (`.ProseMirror`) and detail page display (`#cv-markdown-display`) have different CSS styles, causing visual inconsistency.

**Fix Required**:
1. Create unified `.cv-content` CSS class
2. Apply to both editor and display containers
3. Ensure both match PDF output
4. Remove duplicate/conflicting CSS rules

**Plan**: `plans/cv-editor-wysiwyg-consistency.md`

---

### GAP-055: Auto-Save on Blur for Form Fields
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: Users must manually save form fields; risk of data loss

**Description**: Implement auto-save functionality for job detail page form fields. On blur, automatically save to MongoDB with visual feedback.

**Features**:
- Auto-save on field blur
- Visual feedback: "Saving..." → "Saved" → normal
- Debounce rapid changes (500ms)
- Skip if value unchanged
- Error handling with retry

**Plan**: `plans/frontend-ui-system-design.md` (Component 2)

---

### GAP-056: Contact Management (Delete/Copy/Import)
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-5 hours
**Impact**: No way to manage contacts discovered by FireCrawl

**Description**: Add contact management features to job detail page:
1. Delete contact button with confirmation
2. Copy FireCrawl prompt for Claude Code contact discovery
3. Bulk import contacts via JSON modal

**Plan**: `plans/frontend-ui-system-design.md` (Component 3)

---

### GAP-060: Limit FireCrawl Contacts to 5 (Currently 10)
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 30 minutes
**Impact**: 10 contacts is too heavy; causes processing overhead and increased costs

**Description**: FireCrawl contact discovery currently fetches up to 10 contacts per company. This is excessive and should be reduced to 5 for efficiency.

**Fix Required**:
1. Find FireCrawl contact discovery limit parameter in `src/layer5/people_mapper.py`
2. Change limit from 10 to 5
3. Update any related tests

**Files**:
- `src/layer5/people_mapper.py` - Contact discovery logic
- FireCrawl MCP tool parameters

---

## P3: LOW (Backlog)

### GAP-026: CV V2 - Spacing 20% Narrower
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 2 hours
**Impact**: CV needs more compact layout

**Files**: Frontend templates, PDF service CSS

---

### GAP-027: .docx CV Export
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Currently PDF only; some recruiters prefer Word format

---

### GAP-028: Runner Terminal Copy Button
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 1 hour
**Impact**: No easy way to copy pipeline logs

---

### GAP-029: UI/UX Design Refresh
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 8-16 hours
**Impact**: Modern styling improvements needed

---

### GAP-030: Layer-Specific Prompt Optimization
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: Ongoing
**Impact**: Phase 2 focus - improve prompt quality per layer

**Plan**: `plans/prompt-optimization-plan.md`

---

### GAP-031: FireCrawl Contact Discovery Fallback
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 8-12 hours
**Impact**: When FireCrawl fails, no fallback mechanism

**Plan**: `plans/ai-agent-fallback-implementation.md`

---

### GAP-032: Job Iframe Viewer
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: View original job posting in iframe

**Plan**: `plans/job-iframe-viewer-implementation.md`

---

### GAP-033: Dossier PDF Export
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Export complete dossier as PDF

**Plan**: `plans/dossier-pdf-export-implementation.md`

---

### GAP-034: Bulk Job Processing
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 8-12 hours
**Impact**: No batch processing capability; must process jobs one at a time

**Current State**:
- Pipeline processes single job per invocation
- No queue management for multiple jobs
- No parallel processing optimization
- No bulk progress tracking

**Fix Required**:
1. Implement job queue with priority ordering
2. Add batch processing endpoint in runner service
3. Create bulk progress dashboard in frontend
4. Optimize for parallel layer execution where possible

**Files**: `runner_service/app.py`, `scripts/run_pipeline.py`, `frontend/`

---

### GAP-035: CV Generator Test Mocking
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 2 hours
**Impact**: CV generator tests make real API calls, fail when credits low

**Fix**: Add pytest fixture with mocked ChatAnthropic responses
**Files**: `tests/unit/test_layer6_markdown_cv_generator.py`

---

### GAP-036: Cost Tracking Per Pipeline Run
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 3 hours
**Impact**: No visibility into LLM costs per job

**Fix**: Create `src/common/cost_tracker.py` with token counting + pricing

---

### GAP-037: External Health Monitoring
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 1 hour
**Impact**: No external alerting when VPS goes down

**Fix**: Set up UptimeRobot for `http://72.61.92.76:8000/health`

---

### GAP-038: Complete JobState Model
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Missing fields: tier, dossier_path, cv_text, application_form_fields

**Files**: `src/common/state.py`, Layer 7 publisher

---

### GAP-039: Security Audit
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4 hours
**Impact**: No formal security review

**Fix**: Git history scan, path traversal check, input validation, `safety check`

---

### GAP-040: API Documentation (OpenAPI)
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 2 hours
**Impact**: No interactive API docs for runner service

**Fix**: Add custom_openapi() to FastAPI at `/docs`

---

### GAP-041: Operational Runbook
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4 hours
**Impact**: No documented procedures for common issues

**Fix**: Create `RUNBOOK.md` with troubleshooting guides

---

### GAP-042: Performance Benchmarks
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 3 hours
**Impact**: No baseline metrics; can't detect regressions

**Fix**: Create benchmark tests, document target latencies

---

### GAP-043: Pipeline Runs History Collection
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 3 hours
**Impact**: No historical record of pipeline runs

**Fix**: Create `pipeline_runs` MongoDB collection with run metadata

---

### GAP-044: Knowledge Graph Edges for STAR
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 6-8 hours
**Impact**: STAR records lack relationship graph

**Fix**: Add graph edges linking STARs by skills, domains, outcomes

---

### GAP-045: Tiered Job Execution
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: All jobs treated equally; no priority-based processing

**Fix**: Add job tiers (high/medium/low) with different processing depths

---

### GAP-057: CV Editor Margin Presets
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: Users must manually set margins; no quick presets

**Description**: Add preset margin options (Normal, Narrow, Wide, Custom) for CV editor document styles.

**Presets**:
- Normal: 1" all sides
- Narrow: 0.5" all sides
- Wide: 1.5" all sides
- Custom: user-defined

---

### GAP-058: Smaller UI Buttons
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 1 hour
**Impact**: Some buttons appear oversized; inconsistent with design system

**Description**: Reduce size of certain UI buttons for better visual hierarchy and space efficiency.

**Fix Required**: Review and resize buttons according to design system specifications in `plans/frontend-ui-system-design.md`.

---

## Completed (Nov 2025)

### Core Infrastructure
- [x] All 7 pipeline layers implemented and tested (180+ unit tests)
- [x] Runner service with subprocess execution, JWT auth, artifact serving
- [x] Frontend with job browsing, process buttons, health indicators
- [x] MongoDB persistence, FireCrawl integration, rate limiting, circuit breaker pattern
- [x] Metrics collection, error alerting, budget monitoring

### CV Rich Text Editor
- [x] Phase 1-5: TipTap foundation, formatting toolbar, document styles, PDF export, page breaks
- [x] Phase 6: PDF service separation into dedicated microservice
- [x] Playwright async API conversion, PDF generation bug fixes, WYSIWYG sync fix
- [x] 270+ unit tests for CV editor

### Observability & Safety
- [x] Token budget enforcement (TokenTracker, sliding window algorithm)
- [x] Rate limiting (RateLimiter with per-minute and daily limits)
- [x] Circuit breaker pattern (3-state, pre-configured for external services)
- [x] Structured logging across all 10 pipeline nodes (LayerContext)
- [x] Metrics dashboard (token usage, rate limits, health status)
- [x] Budget monitoring UI (progress bars, thresholds, alerts)
- [x] Error alerting system (ConsoleNotifier, SlackNotifier, deduplication)

### Pipeline & Features
- [x] CV Generation V2 (Layer 1.4 JD Extractor)
- [x] Layer-level structured logging with timing metadata
- [x] ATS compliance research (keyword integration best practices)
- [x] Pipeline progress UI backend API
- [x] Config validation (Pydantic Settings)
- [x] Service health status indicator with capacity metrics
- [x] Application stats dashboard (today/week/month/total counts)

---

## Quick Reference

### Priority Definitions

| Priority | Definition | SLA |
|----------|------------|-----|
| **P0** | System broken, data integrity at risk, production down | Fix immediately |
| **P1** | User-facing bugs, important features broken | Fix this week |
| **P2** | Enhancements, incomplete features, tech debt | Fix this sprint |
| **P3** | Nice-to-have, backlog items | When time permits |

### Key Files

| File | Purpose |
|------|---------|
| `plans/missing.md` | This file - all gaps tracked |
| `plans/architecture.md` | System architecture |
| `bugs.md` | Bug-specific tracking |
| `plans/next-steps.md` | Immediate action items |

### Agent Reports

- `reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`
- `reports/debugging/2025-11-30-cv-hallucination-root-cause-analysis.md`
- `reports/agents/doc-sync/2025-11-30-vps-backup-assessment.md`
