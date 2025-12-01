# Implementation Gaps

**Last Updated**: 2025-12-01 (Week 2 Sprint: 28 gaps fixed/documented)

> **See also**: `plans/architecture.md` | `plans/next-steps.md` | `bugs.md`

---

## Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **P0 (CRITICAL)** | 3 (3 documented/fixed) | Must fix immediately - system broken or data integrity at risk |
| **P1 (HIGH)** | 18 (15 fixed) | Fix this week - user-facing bugs or important features |
| **P2 (MEDIUM)** | 25 (11 fixed) | Fix this sprint - enhancements and incomplete features |
| **P3 (LOW)** | 18 (4 fixed) | Backlog - nice-to-have improvements |
| **Total** | **64** (31 fixed/documented, 33 open) | All identified gaps |

**Test Coverage**: 879 unit tests passing, 48 E2E tests disabled, integration tests pending

### New Features Added (not in original gaps)
- **Bulk "Mark as Applied"**: Select multiple jobs → click "Mark Applied" → updates status for all

### Today's Fixes (2025-12-01)
- **GAP-007**: Time filters now include hidden datetime inputs for hour-level precision
- **GAP-009**: CV display now checks both `cv_text` and `cv_editor_state`
- **GAP-012**: Bold/italic markdown parsing now works in CV text conversion
- **GAP-014**: Middle East relocation tagline added automatically to CVs
- **GAP-026**: CV spacing reduced by 20% for more compact layout
- **GAP-028**: Runner terminal copy button verified as already implemented
- **GAP-040**: Swagger API documentation added at `/api-docs`
- **GAP-051**: Contact discovery improved with company name variations
- **GAP-052**: Page break visualization verified as already implemented
- **GAP-054**: CV display now matches editor exactly (headings, colors, borders)
- **GAP-056**: Contact management (delete/copy/import) verified as already implemented
- **GAP-058**: Button sizing hierarchy refined with btn-xs class
- **GAP-064**: appliedOn timestamp now set when marking jobs as applied
- **GAP-022**: Pipeline progress UI verified as already implemented (7-layer stepper)
- **Postman Collection**: Added runner API collection at `postman/Job-Search-Runner-API.postman_collection.json`

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
**Priority**: P0 CRITICAL | **Status**: ✅ DOCUMENTED (2025-12-01) | **Effort**: 4-6 hours
**Impact**: Credential backup procedures now documented

**Documentation Created**: `plans/credential-backup-vault.md`

Contents:
- Git-crypt setup instructions for encrypted credential storage
- Full list of critical credentials to backup
- Recovery process with step-by-step commands
- Monthly verification checklist
- AWS Secrets Manager alternative for production

**Next Steps**: Implement git-crypt setup and backup credentials

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

### GAP-005: CV V2 - STAR Format Enforcement
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1 day
**Impact**: All CV bullets now follow STAR format for maximum recruiter impact

**Fix Applied** (2025-12-01):
1. **Prompts**: STAR template already in `role_generation.py` (lines 39-61) with examples
2. **Validation**: `RoleQA.check_star_format()` validates Situation, Action, Result elements
3. **Retry Logic**: `RoleGenerator.generate_with_star_enforcement()` auto-corrects failing bullets
4. **Integration**: `CVGeneratorV2` uses STAR enforcement by default (`use_star_enforcement=True`)

**Key Components**:
- `src/layer6_v2/prompts/role_generation.py`: Added `STAR_CORRECTION_SYSTEM_PROMPT` and `build_star_correction_user_prompt()`
- `src/layer6_v2/role_generator.py`: Added `generate_with_star_enforcement()`, `_identify_failing_bullets()`, `_correct_bullet_star()`
- `src/layer6_v2/orchestrator.py`: Added `use_star_enforcement` parameter (default: True)
- `src/layer6_v2/role_qa.py`: Already had `check_star_format()` with pattern detection

**Behavior**:
- Initial bullet generation includes STAR requirements in prompt
- STAR validation checks for: situation opener, action with skill, quantified result
- Failing bullets (<80% STAR coverage) trigger up to 2 correction retries
- LLM rewrites only failing bullets with explicit STAR enforcement prompt

**Verification**: 49 new unit tests in `tests/unit/test_star_enforcement.py`, all passing

---

### GAP-006: CV V2 - Markdown Asterisks in Output
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2 hours
**Impact**: All CVs now output clean text without markdown formatting

**Fix Applied** (2025-12-01):
1. Prompts already have "NO MARKDOWN" instructions (verified in role_generation.py lines 26-37)
2. Created `src/common/markdown_sanitizer.py` with comprehensive sanitization functions
3. Applied sanitization in `src/layer6_v2/orchestrator.py`:
   - `sanitize_markdown()` for profile text
   - `sanitize_bullet_text()` for each experience bullet

**Verification**: All 11 orchestrator unit tests pass

---

### GAP-007: Time-Based Filters Bug ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 30 minutes
**Impact**: 1h/3h/6h/12h quick filters now work correctly with hour-level precision

**Root Cause Found**: The `#job-table-container` div was missing `hx-include=".filter-input"`, so when `triggerTableRefresh()` fired, the hidden datetime inputs weren't included in the request.

**Fix Applied** (2025-12-01):
Added `hx-include=".filter-input"` to the job table container in `frontend/templates/index.html:368-371`:
```html
<div id="job-table-container"
     hx-get="/partials/job-rows"
     hx-trigger="load, refresh from:body"
     hx-include=".filter-input"  <!-- ADDED -->
     hx-indicator=".htmx-indicator">
```

**How it works**:
- Quick filter buttons set hidden `datetime-from` and `datetime-to` inputs with full ISO timestamps
- HTMX now includes these hidden inputs when refreshing the table
- Backend parses ISO timestamps for hour-level precision filtering

---

### GAP-008: GitHub Workflow - Master-CV Sync
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1 hour
**Impact**: VPS now receives full `data/master-cv/` directory with role skill files

**Fix Applied**:
`.github/workflows/runner-ci.yml:146` now includes `data/master-cv`:
```yaml
source: "master-cv.md,docker-compose.runner.yml,data/master-cv"
```

This ensures the VPS gets the role-specific skill files needed for skill whitelist generation.

---

### GAP-009: CV Editor Not Synced with Detail Page ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 30 minutes
**Impact**: CV content now displays on job detail view whether from cv_text or cv_editor_state

**Root Cause Found**: The `has_cv` flag only checked for `cv_text` (markdown), not `cv_editor_state` (TipTap JSON). Jobs that were edited in the CV editor but never had markdown CV would show no content.

**Fix Applied** (2025-12-01):
Updated `frontend/app.py:1441-1447` to check both fields:
```python
# Check if CV was generated by pipeline (stored in MongoDB)
# GAP-009 Fix: Check both cv_text (markdown) AND cv_editor_state (TipTap JSON)
if job.get("cv_text") or job.get("cv_editor_state"):
    has_cv = True
```

**How it works**:
- `cv_text`: Markdown CV from pipeline (original format)
- `cv_editor_state`: TipTap JSON from CV editor (newer format)
- Now both trigger `has_cv = True`, enabling the CV preview section

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

### GAP-012: Inline Mark Parsing ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 1 hour
**Impact**: Bold/italic/bold+italic marks now properly parsed in CV text conversion

**Fix Applied** (2025-12-01):
Implemented `parse_inline_marks()` function with regex parsing in both:
- `frontend/app.py:2406-2468`
- `runner_service/app.py:472-534`

**Supports**:
- `**bold**` → text with bold mark
- `*italic*` → text with italic mark
- `***bold+italic***` → text with both marks
- Mixed text like "Hello **world** and *universe*"

**Implementation**:
```python
# Regex pattern for bold (**text**), italic (*text*), or bold+italic (***text***)
pattern = r'(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*([^*]+?)\*)'
# Returns TipTap-compatible mark nodes
```

**Verification**: All 862 unit tests pass

---

### GAP-013: Bare Except Block - Bad Practice
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 30 minutes
**Impact**: Fixed - all exceptions now caught explicitly

**Fix Applied** (2025-12-01):
1. `src/layer5/people_mapper.py:498`: Changed `except:` to `except Exception:` with comment
2. `src/common/database.py:57`: Changed `except:` to `except Exception:` with comment

**Verification**: `grep -r "except:" src/` returns no matches

---

### GAP-047: Line Spacing Bug in CV Editor ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-4 hours
**Impact**: Line height/spacing now consistent between TipTap editor and PDF output

**Fix Applied** (2025-12-01):
1. Audited `.ProseMirror` CSS line-height values in `frontend/templates/base.html`
2. Updated `pdf_service/pdf_helpers.py` to use relative units (`em`) matching editor:
   - Paragraphs: `margin: 0.5em 0` (was `margin-bottom: 8px`)
   - Lists: `padding-left: 1.5em` (was `20px`)
   - List items: `margin: 0.25em 0` (was `6px`)
   - All elements: `line-height: inherit` for document-level cascade
3. Editor and PDF now use identical spacing values

**Related**: GAP-048 (also fixed), GAP-049 (WYSIWYG Consistency)

---

### GAP-048: Line Spacing Bug in CV Generation ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-4 hours
**Impact**: Generated CVs now have consistent line spacing matching editor and PDF

**Fix Applied** (2025-12-01):
Updated `pdf_service/pdf_helpers.py` CSS to match editor styling exactly:
1. Headings: Added `line-height: inherit` to h1-h6 (matches editor cascade)
2. Paragraphs: Changed from `margin-bottom: 8px` to `margin: 0.5em 0`
3. First/last paragraph: Added margin override rules (matches editor)
4. Lists: Changed `padding-left` from `20px` to `1.5em`, `margin` from `6px 0` to `0.5em 0`
5. List items: Changed `margin` from `6px 0` to `0.25em 0`
6. Nested list items: Added `li > p { margin: 0 }` rule (matches editor)

**Files Modified**: `pdf_service/pdf_helpers.py`
**Tests**: All 31 PDF helper tests pass

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

### GAP-051: Missing Companies Bug in Contact Discovery ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-01) | **Effort**: 1 hour
**Impact**: Contact discovery now finds more contacts via company name variations and expanded paths

**Fix Applied** (2025-12-01):

1. **Added company name variations** (`get_company_name_variations()`):
   - Strips common suffixes: Inc., LLC, Ltd., Corp., GmbH, AG, etc.
   - Tries original name + stripped variant in searches
   - Example: "TechCorp Inc." → ["TechCorp Inc.", "TechCorp"]

2. **Expanded team page paths** (`TEAM_PAGE_PATHS` constant):
   - Added 9 new paths: `/people`, `/our-team`, `/founders`, `/executives`, `/management`, `/about/team`, `/about/leadership`, `/who-we-are`, `/meet-the-team`
   - Now checks 14 paths total (was 5)

3. **Improved search queries**:
   - Uses company variations in LinkedIn searches
   - Falls back to broader queries on empty results

**Files Modified**: `src/layer5/people_mapper.py`
**Commit**: `a1577289` - feat(pipeline): Improve contact discovery with company variations (GAP-051)

---

### GAP-064: Missing `appliedOn` Timestamp When Marking Jobs Applied ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Dashboard "applied by day/week/month" stats now use accurate timestamps

**Fix Applied** (2025-12-01):

1. **Updated `update_job_status()`** - Sets `appliedOn: datetime.utcnow()` when status = "applied"
2. **Updated `update_jobs_status_bulk()`** - Same logic for bulk updates
3. **Updated `/api/dashboard/application-stats`** - Queries by `appliedOn` instead of `pipeline_run_at`
4. **Edge case handled** - Clears `appliedOn` if status changes FROM "applied" to something else

**Implementation**:
```python
update_data = {"status": new_status}
if new_status == "applied":
    update_data["appliedOn"] = datetime.utcnow()
elif new_status != "applied":
    update_data["appliedOn"] = None  # Clear if no longer applied
```

**Files Modified**: `frontend/app.py`
**Commit**: `87f39e92` - feat(frontend): Add appliedOn timestamp for accurate stats (GAP-064)

---

### GAP-059: VPS Health Indicator Shows Grey (Unknown State)
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1-2 hours
**Impact**: VPS health status not visible to users; unclear if runner service is online

**Fix Applied**: The frontend JS was checking `data.vps?.status` but backend returns `data.runner.status`. Fixed property name mismatch in `frontend/templates/base.html`.

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

### GAP-061: Budget/Alert Dashboard Widgets Not Visible ✅ ANALYZED
**Priority**: P1 HIGH | **Status**: ANALYZED (Code Correct) | **Effort**: Deployment verification
**Impact**: Budget monitoring and alerts will display once token usage is recorded

**Analysis Complete** (2025-12-01):
The code is **FULLY CORRECT**. Investigation revealed:

1. ✅ **HTMX attributes correct**: `hx-get="/partials/budget-monitor"` with `hx-trigger="load, every 30s"` in `index.html:89-92`
2. ✅ **Environment variables have sensible defaults**:
   - `ENABLE_TOKEN_TRACKING=true` (default)
   - `TOKEN_BUDGET_USD=100.0` (default)
   - `ENABLE_ALERTING=true` (default)
3. ✅ **Template correctly included** in index.html
4. ✅ **Endpoint works**: `/partials/budget-monitor` proxies to VPS `/api/metrics/budget`

**Expected Behavior**:
- Dashboard shows "No token trackers registered" until pipeline runs record token usage
- Token trackers auto-register when LLM calls occur (during pipeline execution)
- After first pipeline run with token tracking, budget data will appear

**Verification Steps**:
1. Run a pipeline job on VPS to generate token usage data
2. Check browser Network tab for `/partials/budget-monitor` response
3. Verify VPS is reachable from Vercel (`RUNNER_URL` env var)

**Implemented Components** (all working):
- `src/common/token_tracker.py` (1013 lines) - Token tracking with 12-model pricing
- `src/common/alerting.py` (581 lines) - Alert system with Slack
- `src/common/metrics.py` (709 lines) - Metrics collector
- `frontend/templates/partials/budget_monitor.html` (155 lines)
- 8 Flask API endpoints (`/api/budget`, `/api/alerts`, `/partials/*`)

---

### GAP-062: Job Extraction Not Showing on Detail Page
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2-3 hours
**Impact**: Extracted JD data now displays prominently at top of detail page

**Fix Applied**:
1. Verified Layer 1.4 JD extraction is working correctly and saving to MongoDB
2. Added responsibilities and qualifications display to frontend template
3. **MOVED** extracted JD, pain points, and opportunities sections to TOP of detail page for prominence
4. Added debug logging to output_publisher to trace extracted_jd persistence

**What Changed**:
- `frontend/templates/job_detail.html` - Reorganized layout, moved JD intelligence to top
- `src/layer7/output_publisher.py` - Added debug logging for extracted_jd
- Extracted JD now appears immediately after pipeline progress indicator

**Verification**: Run pipeline for job, then view detail page - extracted JD section shows at top

---

## P2: MEDIUM (Fix This Sprint)

### GAP-014: CV V2 - Dynamic Tagline for Location ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Middle East jobs now get "Open to International Relocation" tagline automatically

**Fix Applied** (2025-12-01):
1. Added `MIDDLE_EAST_COUNTRIES` list in `src/layer6_v2/orchestrator.py`
2. Created `is_middle_east_location()` function for location matching
3. Modified `_assemble_cv_text()` to inject tagline after contact line
4. Tagline: "Open to International Relocation | Available to start within 2 months"

**Trigger Countries**: Saudi Arabia, UAE, Kuwait, Qatar, Oman, Pakistan, Dubai, Abu Dhabi, Riyadh, etc.

**Commit**: `03a996c8` - feat(pipeline): Add relocation tagline for Middle East jobs (GAP-014)

---

### GAP-015: CV V2 - Color Scheme Change ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE | **Effort**: 30 minutes
**Impact**: CV now uses professional slate-600 color instead of teal/green

**Fix Applied** (2025-12-01):
Changed `#0f766e` (teal/green) → `#475569` (slate-600 dark greyish blue) in:
1. `pdf_service/pdf_helpers.py` - PDF output `--color-accent` variable
2. `frontend/templates/base.html` - CV editor heading colors (4 locations)
3. `frontend/app.py` - Default `colorAccent` config (2 locations)

**Commit**: `0676a5da` - style: Change CV color scheme from teal to slate-600

---

### GAP-016: DateTime Range Picker Enhancement
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 min
**Impact**: Date filter now supports hour/minute precision

**Fix Applied** (2025-12-01):
- Changed `type="date"` to `type="datetime-local"` for date range inputs
- Updated input names from `date_from/date_to` to `datetime_from/datetime_to`
- Removed redundant hidden datetime inputs
- Updated `setQuickDateFilter()` JS to format datetime-local values
- Updated `clearAllFilters()` and `clearDateFilter()` for new input type

**Files**: `frontend/templates/index.html`

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
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 min
**Impact**: Test coverage now tracked automatically

**Fix Applied** (2025-12-01):
- Added `pytest-cov` configuration to `pytest.ini`
- Created `.coveragerc` with detailed coverage settings
- Configured coverage for `src/`, `frontend/`, `runner_service/`, `pdf_service/`
- Enabled branch coverage and HTML/XML reports
- Added `coverage_html/` and `coverage.xml` to `.gitignore`

**Files**: `pytest.ini`, `.coveragerc`, `.gitignore`

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

### GAP-022: Job Application Progress UI Frontend ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Full pipeline progress visualization available on job detail page

**Verification** (2025-12-01): Feature was already fully implemented

**Existing Implementation**:
1. **CSS Styles**: `frontend/static/css/pipeline-progress.css` (400 lines) with:
   - 5 visual states: pending, executing, success, failed, skipped
   - Animated pulse ring for executing steps
   - Overall progress bar with shimmer effect
   - Responsive design + accessibility support

2. **HTML Stepper**: 7-layer visual stepper in `job_detail.html:192-327`:
   - Intake → Pain Points → Company Research → Role Research → Fit Scoring → People Mapping → CV/Outreach

3. **JavaScript** (`job_detail.html:2329-2480`):
   - `monitorPipeline(runId)` - Starts monitoring with polling
   - `updatePipelineStep(layer, status)` - Updates individual layers
   - `handlePipelineProgressUpdate(data)` - Handles SSE/polling updates
   - SSE support ready (commented, awaiting backend SSE endpoint)

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

### GAP-052: Phase 5 - WYSIWYG Page Break Visualization ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Visual page break indicators show where PDF pages will break

**Verification** (2025-12-01): Feature was already fully implemented

**Existing Implementation**:
1. **Page Break Calculator** (`frontend/static/js/page-break-calculator.js`):
   - `calculatePageBreaks(pageSize, margins, contentElement)` - computes Y positions
   - `renderPageBreaks(breakPositions, container)` - renders dashed line indicators
   - `clearPageBreaks(container)` - removes indicators
   - Supports Letter (8.5x11") and A4 page sizes
   - Algorithm iterates elements and tracks cumulative height

2. **CV Editor Integration** (`frontend/static/js/cv-editor.js:1261-1286`):
   - Calls `PageBreakCalculator.calculatePageBreaks()` when content changes
   - Renders break indicators with "Page N" labels

3. **CSS Styling** (`frontend/static/css/cv-editor.css:365-396`):
   - Dashed line with gray background
   - "Page N" label in top-right corner

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

### GAP-054: CV Editor WYSIWYG Consistency ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Editor and detail page now render identically - true WYSIWYG achieved

**Fix Applied** (2025-12-01):
Unified display container styles with `.ProseMirror` editor in `frontend/templates/base.html`:

| Element | Before (Display) | After (Matches Editor) |
|---------|------------------|------------------------|
| h1 | `2em`, no color | `34px`, slate-600, Playfair Display |
| h2 | `1.5em`, no border | `20px`, slate-600, border-top |
| h3 | `1.25em`, no color | `16px`, slate-600 |
| links | blue underline | slate-600, no underline |

**Changes**:
1. Updated `#cv-markdown-display`, `#cv-container`, `#cv-display-area` heading styles to exactly match `.ProseMirror`
2. Added h2:first-child rule for consistent border behavior
3. Updated link color from blue to slate-600 to match editor accent

**Plan**: `plans/cv-editor-wysiwyg-consistency.md`

---

### GAP-055: Auto-Save on Blur for Form Fields
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Users have auto-save with visual feedback

**Verification** (2025-12-01): Feature was already fully implemented at `frontend/templates/job_detail.html:2135-2174`

**Existing Implementation**:
- `saveFieldEdit()` function handles auto-save on blur
- Visual feedback: "Saving..." → "✓ Saved" → normal state
- Handles Enter key (save) and Escape key (cancel)
- Error handling with user-friendly messages
- Debounce built into save mechanism

---

### GAP-056: Contact Management (Delete/Copy/Import) ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Full contact management available on job detail page

**Verification** (2025-12-01): Feature was already fully implemented in `frontend/templates/job_detail.html` and `frontend/app.py`

**Existing Implementation**:
1. **Delete Contact**: `deleteContact()` function with confirmation, smooth animation removal
2. **Copy FireCrawl Prompt**: `copyFirecrawlPrompt()` copies discovery prompt to clipboard
3. **Import Contacts Modal**: `openAddContactsModal()` with JSON validation, preview, and bulk import

**API Endpoints** (`frontend/app.py`):
- `DELETE /api/jobs/<id>/contacts/<type>/<index>` - Delete single contact
- `POST /api/jobs/<id>/contacts` - Bulk import contacts
- `GET /api/jobs/<id>/contacts/prompt` - Get FireCrawl discovery prompt

**UI Elements** (job detail page):
- "Copy Prompt" button in contacts header
- "Add Contacts" button for import modal
- Delete (trash) button on each contact card

---

### GAP-060: Limit FireCrawl Contacts to 5 (Currently 10)
**Priority**: P2 MEDIUM | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 30 minutes
**Impact**: 10 contacts is too heavy; causes processing overhead and increased costs

**Fix Applied**: Added `MAX_TOTAL_CONTACTS=5` constant and `_limit_contacts()` method in `src/layer5/people_mapper.py`. Limits to 3 primary + 2 secondary contacts. Applied BEFORE outreach generation to save LLM calls.

**Description**: FireCrawl contact discovery currently fetches up to 10 contacts per company. This is excessive and should be reduced to 5 for efficiency.

**Fix Required**:
1. Find FireCrawl contact discovery limit parameter in `src/layer5/people_mapper.py`
2. Change limit from 10 to 5
3. Update any related tests

**Files**:
- `src/layer5/people_mapper.py` - Contact discovery logic
- FireCrawl MCP tool parameters

---

### GAP-063: Parallel Pytest Execution in CI/CD
**Priority**: P2 MEDIUM | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2-3 hours
**Impact**: 813+ tests now run in parallel; ~60-80% CI time reduction

**Fix Applied** (2025-12-01):
1. Added `pytest-xdist>=3.5.0` and `pytest-cov>=4.0.0` to `requirements.txt`
2. Updated `pytest.ini` with `-n auto` for parallel execution by default
3. Updated `.github/workflows/runner-ci.yml`:
   - Re-enabled test job with parallel execution
   - Added PDF service tests
   - Tests now required before build
4. Updated `.github/workflows/frontend-ci.yml` with parallel execution

**Verification**:
```bash
# Local: 813 tests in 48.61s (parallel) vs ~3 min (sequential)
python -m pytest tests/unit -n auto --tb=short
```

**Note**: Use `-n 0` to disable parallel execution for debugging

---

### GAP-065: LinkedIn Job Scraper - Import Jobs via Job ID ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 4 hours
**Impact**: Quick job import from LinkedIn without manual data entry

**Fix Applied** (2025-12-01):
Implemented ability to import LinkedIn jobs by entering just the job ID or URL. Scrapes LinkedIn's public guest API to extract job details and creates job records in both level-1 and level-2 MongoDB collections.

**User Flow**:
1. User enters LinkedIn job ID (e.g., `4081234567`) or URL in dashboard input field
2. System scrapes `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}`
3. Parses HTML to extract: title, company, location, description, job criteria
4. Creates job document in both MongoDB level-1 and level-2 collections with status "not processed"
5. Runs quick LLM (gpt-4o-mini) to score job fit
6. Redirects user to job detail page

**Implementation Complete**:
1. `src/services/linkedin_scraper.py` - Scraper service with BeautifulSoup HTML parsing
2. `src/services/quick_scorer.py` - Lightweight LLM scoring using gpt-4o-mini
3. `frontend/app.py` - POST `/api/jobs/import-linkedin` endpoint with duplicate detection
4. `frontend/templates/index.html` - Input field + button UI with LinkedIn icon
5. `frontend/templates/base.html` - JavaScript handler `importLinkedInJob()` with loading states
6. `requirements.txt` - Added beautifulsoup4 and lxml dependencies
7. `tests/unit/test_linkedin_scraper.py` - 24 unit tests passing

**DedupeKey Format**: `company|title|location|source` (all lowercase)
Example: `testcorp|senior software engineer|san francisco, ca|linkedin_import`

**Supported Input Formats**:
- Raw job ID: `4081234567`
- Full URL: `https://www.linkedin.com/jobs/view/4081234567`
- URL with params: `https://linkedin.com/jobs/view/4081234567?trk=search`
- currentJobId param: `https://linkedin.com/jobs/search/?currentJobId=4081234567`

---

## P3: LOW (Backlog)

### GAP-026: CV V2 - Spacing 20% Narrower ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: CV layout is now 20% more compact for better information density

**Fix Applied** (2025-12-01):
Reduced margins/spacing across all CV elements by ~20%:

| Element | Before | After |
|---------|--------|-------|
| h1 margin | 0 0 12px 0 | 0 0 10px 0 |
| h2 margin | 16px 0 10px | 12px 0 8px |
| h2 padding-top | 8px | 6px |
| h3 margin | 12px 0 8px | 10px 0 6px |
| Paragraph margin | 0.5em | 0.4em |
| List margin | 0.5em | 0.4em |
| List item margin | 0.25em | 0.2em |

**Files Modified**:
- `pdf_service/pdf_helpers.py` - PDF output CSS
- `frontend/templates/base.html` - Editor + display container CSS

---

### GAP-027: .docx CV Export
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Currently PDF only; some recruiters prefer Word format

---

### GAP-028: Runner Terminal Copy Button ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Copy button for pipeline logs already exists and works

**Verification** (2025-12-01): Feature was already fully implemented at `frontend/templates/job_detail.html:2737`

**Existing Implementation**:
- `copyLogsToClipboard()` function in job detail template
- Uses Clipboard API with execCommand fallback for older browsers
- Visual feedback: "Copied!" notification on success
- Button located in runner terminal header

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

### GAP-034: Bulk Job Processing ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE | **Effort**: 2 hours (backend existed)
**Impact**: Batch processing now available via UI - select multiple jobs and process together

**Discovery** (2025-12-01):
The backend bulk processing was **already implemented** but had no frontend UI:
- `/jobs/run-bulk` endpoint existed in `runner_service/app.py:236-256`
- `RunBulkRequest` model existed in `runner_service/models.py:23-28`
- Proxy endpoint existed in `frontend/runner.py:71-104`
- Concurrency control via `asyncio.Semaphore(MAX_CONCURRENCY)` already in place

**Fix Applied** (2025-12-01):
1. Added "Process Selected" button to job list (`frontend/templates/index.html`)
2. Updated `updateSelectionCount()` to enable/disable process button
3. Added `processSelectedJobs()` function in `frontend/templates/base.html`
4. Button calls `/api/runner/jobs/run-bulk` with selected job IDs
5. Confirmation dialog shows job count before processing
6. Selection clears after successful queue submission

**Concurrency Configuration**:
```bash
# Environment variable (default: 3, range: 1-20)
MAX_CONCURRENCY=5  # Increase for batch processing day
```

**Usage**:
1. Go to job list page
2. Select jobs via checkboxes (or "Select All")
3. Click green "Process Selected" button
4. Confirm batch processing
5. Jobs queued and processed (up to MAX_CONCURRENCY simultaneously)

---

### GAP-035: CV Generator Test Mocking
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: CV generator tests run reliably without API calls

**Fix Applied** (2025-12-01):
1. LLM mocking was already in place (`mock_llm_providers` fixture lines 22-51)
2. Fixed parallel test race condition with `tmp_path` isolation
3. Updated `cleanup_test_output` to use unique temp directories per test
4. All 21 tests now pass with parallel execution

**Key Changes**:
- `tests/unit/test_layer6_markdown_cv_generator.py`: Changed `cleanup_test_output` fixture to use `tmp_path` and `os.chdir()` for test isolation
- Removed manual cleanup code that caused race conditions

---

### GAP-036: Cost Tracking Per Pipeline Run
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Full visibility into LLM costs per job

**Fix Applied** (2025-12-01):
1. Added `total_cost_usd` and `token_usage` to initial state in `src/workflow.py`
2. Capture token usage from `get_global_tracker()` after pipeline execution
3. Persist cost fields to MongoDB in `src/layer7/output_publisher.py:374-379`
4. Added cost summary to pipeline completion logs

**Token Tracking Infrastructure** (already existed):
- `src/common/token_tracker.py`: Comprehensive `TokenTracker` class with per-provider cost estimates
- `UsageSummary` with `by_provider` dict containing input/output tokens and costs
- Global tracker accessed via `get_global_tracker()`

---

### GAP-037: External Health Monitoring
**Priority**: P2 MEDIUM | **Status**: ✅ READY TO IMPLEMENT (2025-12-01) | **Effort**: 15 minutes
**Impact**: External alerting when VPS goes down

**Setup Instructions**:

1. **Create UptimeRobot account** (free tier: 50 monitors)
   - Go to https://uptimerobot.com/
   - Sign up with email

2. **Add VPS Runner Monitor**:
   - Monitor Type: HTTP(s)
   - Friendly Name: "Job Search - VPS Runner"
   - URL: `http://72.61.92.76:8000/health`
   - Monitoring Interval: 5 minutes

3. **Add Vercel Frontend Monitor**:
   - Monitor Type: HTTP(s)
   - Friendly Name: "Job Search - Frontend"
   - URL: `https://your-app.vercel.app/api/health`
   - Monitoring Interval: 5 minutes

4. **Configure Alerts**:
   - Email alerts (free)
   - Slack webhook (optional)
   - Mobile push (free mobile app)

**Expected Health Response**:
```json
{
  "status": "healthy",
  "runner": {"status": "healthy", "model": "..."},
  "services": {"mongodb": "connected"}
}
```

**Alternative**: Use cron job on separate server:
```bash
# Add to crontab -e
*/5 * * * * curl -f http://72.61.92.76:8000/health || curl -X POST https://hooks.slack.com/... -d '{"text":"VPS DOWN!"}'
```

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

### GAP-040: API Documentation (OpenAPI) ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 2 hours
**Impact**: Interactive API documentation now available

**Fix Applied** (2025-12-01):
1. Created `frontend/static/openapi.yaml` - Full OpenAPI 3.0.3 spec covering all API endpoints
2. Created `frontend/templates/api_docs.html` - Swagger UI with custom styling
3. Added routes in `frontend/app.py`:
   - `/api-docs` → Swagger UI interface
   - `/api/openapi.yaml` → Raw spec file
4. Created `postman/Job-Search-Runner-API.postman_collection.json` - Postman collection

**Access**: https://job-search-inky-sigma.vercel.app/api-docs

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

### GAP-058: Smaller UI Buttons ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Button sizing now follows consistent design hierarchy

**Fix Applied** (2025-12-01):
Added refined button sizing hierarchy in `frontend/templates/base.html`:

```css
.btn-xs { padding: 0.25rem 0.5rem; font-size: var(--text-xs); }  /* New */
.btn-sm { padding: 0.375rem 0.75rem; font-size: var(--text-xs); }
.btn-md { padding: 0.5rem 1rem; }
.btn-lg { padding: 0.625rem 1.25rem; font-size: var(--text-base); }
```

**Sizes**: xs (tiny) → sm (small) → md (default) → lg (large)

**Commit**: `13d940d6` - style(frontend): Refine button sizing hierarchy (GAP-058)

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
