# Next Session Quick Start Guide

**Use this to get back up to speed in under 5 minutes**

---

## Where We Left Off

**Last Commit**: `792b08ec` - fix(css): Add #cv-display-area to CV display CSS selectors
**Last Session**: 2025-11-30 (3 parallel agents, 30+ commits pushed)
**Status**: All 470 tests passing, production deployed to Vercel

---

## Critical Status

✅ **EVERYTHING IS WORKING** - No blockers or issues
✅ **470 Unit Tests Passing** (up from 432)
✅ **30+ Commits Pushed** to GitHub
✅ **All Bug Fixes Deployed** to production

⚠️ **IMPORTANT**: Jobs processed BEFORE 2025-11-30 don't have `extracted_jd` field in MongoDB - may need backfill

---

## What Just Got Done

| What | Status | Where |
|------|--------|-------|
| Bug #5 (Line height) | ✅ Fixed | `pdf_service/pdf_helpers.py` |
| Bug #7 (Iframe PDF export) | ✅ Fixed | pdf-service + runner + frontend |
| Terminal copy button | ✅ Added | `frontend/templates/job_detail.html` |
| Layer 1.4 JD persistence | ✅ Fixed | `src/layer7/output_publisher.py` |
| 38 new tests for role_qa | ✅ Added | `tests/unit/test_layer6_v2_role_qa.py` |
| System gap analysis | ✅ Complete | 62 gaps identified, documented |
| All docs synced | ✅ Updated | `plans/missing.md`, `plans/architecture.md` |

---

## Immediate Next Steps

### If starting fresh (1-2 hours)
```bash
# Get environment ready
source .venv/bin/activate

# Verify all tests pass
python -m pytest tests/unit/ -q
# Should see: 470 passed

# Check git is clean
git status
# Should show: working tree clean
```

### If continuing development (pick one)

**Option A: Implement Pipeline Progress Indicator** (Gap #25)
- Estimated: 3-4 hours
- Why: Enables real-time layer status on frontend
- Files: `runner_service/app.py`, `frontend/templates/job_detail.html`
- Plan: `plans/missing.md` (line ~273)

**Option B: Enable Runner CI Tests** (Gap #4)
- Estimated: 2-3 hours
- Why: GitHub Actions not running runner tests
- Files: `.github/workflows/` directory
- Plan: `plans/missing.md` (line ~267)

**Option C: Backfill extracted_jd Field**
- Estimated: 1-2 hours
- Why: Pre-2025-11-30 jobs missing new field
- Files: Script in `scripts/` directory (create)
- Process: Re-run pipeline or backfill from job descriptions

**Option D: CV Editor Phase 5.2**
- Estimated: 4-6 hours
- Why: Keyboard shortcuts + mobile optimization
- Files: `frontend/static/js/cv-editor.js`, `frontend/templates/job_detail.html`
- Plan: `plans/missing.md` (line ~741)

---

## Key System Paths

### Pipeline Entry Points
- **CLI**: `python scripts/run_pipeline.py --job-id <id>`
- **Frontend**: https://job-search-inky-sigma.vercel.app → Job List → Process Job
- **Runner**: POST http://72.61.92.76:8000/api/jobs/<id>/process (with auth)

### Core Services
- **Runner Service**: `runner_service/app.py` (port 8000)
- **PDF Service**: `pdf_service/app.py` (port 8001, internal)
- **Frontend**: `frontend/app.py` (deployed to Vercel)
- **Pipeline**: `src/workflow.py` (7-layer LangGraph)

### Data Storage
- **MongoDB**: `mongodb+srv://...` (MONGODB_URI)
- **Google Drive**: `/applications/<company>/<role>/` (optional)
- **Google Sheets**: Run tracker (optional)

---

## Architecture Diagram (Quick Reference)

```
User Browser
    ↓
Vercel Frontend (Flask)
    ↓
VPS Runner Service (FastAPI) ← Subprocess: LangGraph Pipeline
    ├─→ PDF Service (Playwright) → PDFs
    └─→ MongoDB (job results)
```

---

## Testing Quick Checks

```bash
# All unit tests
source .venv/bin/activate
python -m pytest tests/unit/ -q

# Just PDF service
python -m pytest tests/pdf_service/ -v

# Just runner service
python -m pytest tests/runner/ -v

# Just frontend
python -m pytest tests/frontend/ -v

# Just layer6_v2 (CV generation)
python -m pytest tests/unit/test_layer6_v2*.py -v
```

---

## Configuration to Know

| Variable | Value | Used By |
|----------|-------|---------|
| `MONGODB_URI` | `mongodb+srv://...` | All services |
| `MONGO_DB_NAME` | `job_search` | All services |
| `RUNNER_URL` | `http://72.61.92.76:8000` | Frontend |
| `ENABLE_CV_GEN_V2` | `true` | Pipeline |
| `ENABLE_JD_EXTRACTOR` | `true` | Pipeline Layer 1.4 |
| `ENABLE_STAR_SELECTOR` | `false` | Layer 2.5 (optional) |
| `DISABLE_FIRECRAWL_OUTREACH` | `true` | Layer 5 (use synthetic) |

---

## Git Workflow Reminder

```bash
# Make changes
# ... code changes ...

# Run tests
python -m pytest tests/unit/ -q

# Stage and commit (atomic commits!)
git add <specific files>
git commit -m "fix(component): Brief description"

# Push
git push origin main

# Frontend auto-deploys to Vercel
# Runner service needs manual restart if docker changes
```

**No Claude signature on commits** ✅

---

## One-Minute Health Check

```bash
# 1. Tests passing?
python -m pytest tests/unit/ -q --tb=no
# Should show: 470 passed

# 2. Git clean?
git status
# Should show: working tree clean

# 3. Frontend up?
curl -s https://job-search-inky-sigma.vercel.app | grep -q "Job Search"
# No error = working

# 4. Runner up?
curl -s http://72.61.92.76:8000/health | grep -q "healthy"
# Should see: healthy status
```

---

## Common Dev Tasks

### Run a single job through pipeline
```bash
source .venv/bin/activate
python scripts/run_pipeline.py --job-id <mongodb_id>
```

### Check MongoDB for recent jobs
```bash
# Use MongoDB Atlas UI or:
# mongo shell commands in runner_service/app.py
```

### Export CV as PDF (test)
```bash
# Via frontend: Job Detail → CV Editor → Export PDF button
# Or direct API: POST /api/jobs/<id>/cv-editor/pdf
```

### View pipeline logs
```bash
# Frontend: Job Detail page → Terminal Output section
# Or check runner service logs:
# ssh to VPS and docker logs
```

---

## If Something Breaks

1. **Verify tests still pass**: `python -m pytest tests/unit/ -q`
2. **Check git diff**: `git diff HEAD~5` (last 5 commits)
3. **Read error carefully** - often tells you exactly what's wrong
4. **Consult architecture.md** - system design reference
5. **Check missing.md** - known gaps and workarounds

---

## Most Important Files This Session

| File | Purpose | Last Updated |
|------|---------|--------------|
| `plans/missing.md` | Gap tracking (62 gaps identified) | 2025-11-30 |
| `plans/architecture.md` | System design | 2025-11-30 |
| `src/layer6_v2/orchestrator.py` | CV generation engine | Complete |
| `pdf_service/app.py` | PDF generation service | Complete |
| `runner_service/app.py` | Pipeline runner & proxies | 2025-11-30 |
| `tests/unit/test_layer6_v2_role_qa.py` | New 38 tests | 2025-11-30 |

---

## Recommended Reading (5-15 min)

1. **Missing.md** (Current state vs goal) - 5 min
2. **Architecture.md** (System design) - 10 min
3. **This document** (Quick start) - 2 min

---

## Questions? Check These First

| Question | Answer Location |
|----------|-----------------|
| "What's left to do?" | `plans/missing.md` → "Remaining Gaps" section |
| "How does the system work?" | `plans/architecture.md` |
| "Where's the X endpoint?" | `plans/architecture.md` → "Output Structure" section |
| "What test covers Y?" | `tests/unit/` → Find test_* file matching component |
| "Why is X failing?" | Check git history: `git log --oneline -20` |
| "What agent should I use?" | `CLAUDE.md` → "Agent Delegation System" section |

---

## Session Continuity Documents

- **Full Report**: `reports/agents/session-continuity/2025-11-30-SESSION-CONTINUITY-REPORT.md` (comprehensive)
- **Quick Start** (this file): `reports/agents/session-continuity/NEXT-SESSION-QUICKSTART.md` (5-minute restore)
- **Changes Summary**: `reports/agents/session-continuity/CHANGES_SUMMARY.md` (if exists)

---

## Status Dashboard

```
PIPELINE:           ✅ 7 layers working
CV GEN V2:          ✅ Complete (194 tests)
CV EDITOR:          ✅ Phase 5.1 complete
PDF SERVICE:        ✅ Running (56 tests)
TESTS:              ✅ 470/470 passing
DEPLOYMENT:         ✅ Live on Vercel + VPS
DOCUMENTATION:      ✅ All current
GIT:                ✅ Clean

BLOCKERS:           None
WARNINGS:           Pre-2025-11-30 jobs lack extracted_jd field
```

---

**Last Updated**: 2025-11-30
**Read Time**: 2-5 minutes
**Refresh Time**: 5 minutes
**Accuracy**: High (auto-generated from session work)
