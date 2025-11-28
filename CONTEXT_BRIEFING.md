# Session Continuity Briefing - 2025-11-28

## Project Summary

Job Intelligence Pipeline: A Python/LangGraph system that ingests job postings from MongoDB and generates hyper-personalized CVs, cover letters, and outreach packages. Features a professional CV rich-text editor with PDF export via Playwright.

## Current Architecture

- **Frontend**: Vercel (Flask + TipTap editor + Tailwind CSS)
  - URL: https://job-search-inky-sigma.vercel.app
  - Endpoints: Job listing, CV editor, PDF export proxy

- **Runner Service**: VPS 72.61.92.76 (FastAPI + Python)
  - Port: 8000
  - Endpoints: PDF generation, pipeline execution

- **Pipeline**: 7-layer LangGraph workflow
  - Layers 2-6: Pain mining → Fit scoring → CV drafting
  - Input: MongoDB job documents
  - Output: Google Drive artifacts + Sheets tracker

- **Database**: MongoDB Atlas
  - Collections: users, jobs (named "level-2"), cv, company_cache
  - Connection: Via MONGODB_URI env var

## Recent Work (Last Session)

1. **Frontend Recursion Bug (FIXED ✅)**
   - Renamed `showToast()` → `notifyUser()` to avoid name collision
   - Location: frontend/static/js/cv-editor.js

2. **Backend Recursion Bug (FIXED ✅)**
   - Rewrote `tiptap_json_to_html()` with iterative stack-based approach
   - Eliminated recursion from tree traversal
   - Location: runner_service/pdf_helpers.py

3. **Session Cookie Security (FIXED ✅)**
   - Set `SameSite=None` + `Secure=True` for HTTPS
   - Location: frontend/app.py lines 49-85

4. **Authentication Mismatch #1 (FIXED ✅)**
   - Frontend changed from `RUNNER_API_TOKEN` → `RUNNER_API_SECRET`
   - Location: frontend/app.py line 929

5. **Authentication Mismatch #2 (FIXED ✅)**
   - Backend bearer token properly configured
   - Verified in runner_service/app.py

## Current State

**What's Working:**
- ✅ All recursion bugs fixed (frontend + backend)
- ✅ Session authentication functional
- ✅ Bearer token authentication configured
- ✅ CV editor fully functional with 46+ unit tests
- ✅ Phase 4 PDF export moved to runner service

**What's Broken:**
- ❌ PDF export endpoint returns "MongoDB not configured"
- **Root Cause**: runner_service/app.py line 396 reads `MONGO_URI`, but env var is `MONGODB_URI`
- **Secondary Issue**: Database name defaults to "job_search" instead of "jobs"

## Critical Fix Needed

**File**: `/Users/ala0001t/pers/projects/job-search/runner_service/app.py` (line 396)

**Current Code**:
```python
mongo_uri = os.getenv("MONGO_URI")  # WRONG
if not mongo_uri:
    raise HTTPException(status_code=500, detail="MongoDB not configured")
```

**Required Change**:
```python
mongo_uri = os.getenv("MONGODB_URI")  # CORRECT
if not mongo_uri:
    raise HTTPException(status_code=500, detail="MongoDB not configured")
```

**Also at line 402**: Verify `MONGO_DB_NAME` should default to `"jobs"` (not `"job_search"`)

## Environment Variables Verification

**Vercel Frontend Must Have**:
- `FLASK_SECRET_KEY` = [generated key]
- `RUNNER_API_SECRET` = [matches VPS]
- `MONGODB_URI` = [Atlas connection string]

**VPS Runner Must Have**:
- `MONGODB_URI` = [Atlas connection string] ← CRITICAL
- `MONGO_DB_NAME` = "jobs" ← Verify this
- `RUNNER_API_SECRET` = [matches Vercel]

## Code Changes Made This Session

1. **frontend/app.py**
   - Session cookie config (SameSite=None, Secure=True)
   - Line 929: RUNNER_API_TOKEN → RUNNER_API_SECRET
   - Bearer token header configuration

2. **frontend/static/js/cv-editor.js**
   - showToast() → notifyUser() (eliminates recursion)
   - Proper credentials: 'same-origin' for fetch

3. **runner_service/pdf_helpers.py**
   - Iterative stack-based tiptap_json_to_html() (no recursion)
   - 349 lines, fully tested

4. **frontend/templates/job_detail.html**
   - Cache-busting version params

5. **plans/architecture.md**
   - Documentation updates

## Git Status

**Branch**: main (clean)

**Recent Commits**:
```
347df1d1 fix(auth): Change RUNNER_API_TOKEN to RUNNER_API_SECRET
0a6f38da fix(auth): Set SameSite=None + Secure=True for HTTPS session cookies
56138011 fix(pdf-export): Add credentials: 'same-origin' to send session cookies
ace976c6 revert: Remove unnecessary auth fixes, keep only the real fix
616d92de fix(auth): Use stable secret key and add SameSite cookie config
20eb86b0 fix(pdf-export): Add credentials to fetch for session authentication
d536324f fix(frontend): Replace showToast with notifyUser to eliminate recursion
```

## Pending Tasks (Blocking Issue)

1. **Apply MongoDB env var fix** (CRITICAL - 5 minutes)
   - File: `/Users/ala0001t/pers/projects/job-search/runner_service/app.py`
   - Change line 396: `MONGO_URI` → `MONGODB_URI`
   - Verify line 402: database name is `"jobs"`

2. **Deploy to VPS** (10 minutes)
   - Push changes to runner service
   - Restart FastAPI service
   - Verify health check

3. **Test PDF export** (5 minutes)
   - Generate CV in frontend
   - Click "Export as PDF"
   - Verify PDF downloads

4. **Update missing.md** (5 minutes)
   - Mark "PDF Export Recursion Fix" as complete
   - Mark "MongoDB env var naming" as fixed

## Key Files to Know

| File | Purpose |
|------|---------|
| `/Users/ala0001t/pers/projects/job-search/src/workflow.py` | Main LangGraph pipeline (7 layers) |
| `/Users/ala0001t/pers/projects/job-search/runner_service/app.py` | FastAPI runner service (**NEEDS FIX**) |
| `/Users/ala0001t/pers/projects/job-search/frontend/app.py` | Vercel Flask frontend |
| `/Users/ala0001t/pers/projects/job-search/runner_service/pdf_helpers.py` | PDF generation helpers (FIXED) |
| `/Users/ala0001t/pers/projects/job-search/frontend/static/js/cv-editor.js` | TipTap editor (FIXED) |
| `/Users/ala0001t/pers/projects/job-search/plans/missing.md` | Implementation tracking |
| `/Users/ala0001t/pers/projects/job-search/SESSION_SUMMARY.md` | Detailed session summary |

## Recommended Next Action

Use **architecture-debugger** agent to:
1. Apply MongoDB env var fix to runner_service/app.py
2. Verify database name configuration
3. Deploy and test PDF export endpoint
4. Confirm end-to-end PDF generation works

## Multi-Agent Suggestion

After the critical MongoDB fix is deployed:
- Use **doc-sync** to update `missing.md` marking PDF fixes as complete
- Use **pipeline-analyst** to validate full PDF export workflow
- Use **test-generator** to add integration tests for PDF endpoint

## Session Continuity Notes

- All recursion bugs eliminated ✅
- All authentication issues resolved ✅
- One critical env var naming issue remains (5-minute fix)
- No schema changes needed, just env var naming
- Safe to deploy once fix applied

**Success Criteria for Next Session**:
1. MongoDB connection established in PDF endpoint
2. PDF export button functional
3. End-to-end CV → PDF workflow validated
4. missing.md updated
