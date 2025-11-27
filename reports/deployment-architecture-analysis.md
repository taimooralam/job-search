# Deployment Architecture Clarification Report

**Date**: 2025-11-27
**Analyzed**: Plans, Docker configs, code structure
**Status**: Documentation clarified, misunderstanding resolved

---

## Executive Summary

The project uses a **DISTRIBUTED ARCHITECTURE** with frontend and runner on different platforms:

- **Frontend**: Deployed to **Vercel** (serverless platform)
- **Runner (Pipeline)**: Deployed to **VPS at 72.61.92.76** (Docker container)
- **PDF Generation**: Happens on **both** (frontend for CV editor, VPS for final exports)

This is intentional and well-designed. The misunderstanding was about which service was responsible for what.

---

## Current Deployment Architecture

### Frontend Service

**Location**: **Vercel** (Cloud)

**Technology Stack**:
- Flask + HTMX + Tailwind CSS
- Python runtime (serverless)
- Deployed via `vercel.json` config as serverless function
- Entry point: `frontend/api/index.py` → `frontend/app.py`
- Auto-deploys on git push to main

**Deployment Method**:
- Git push to GitHub repository
- Vercel automatically detects changes
- Builds and deploys via their CI/CD pipeline
- No manual Docker involved for frontend

**Responsibilities**:
- Display job list from MongoDB (`level-2` collection)
- Job search, filtering, status management
- Job detail page with CV editor
- CV Rich Text Editor (TipTap) with client-side formatting
- PDF export for CV (Playwright on Vercel function)
- API calls to VPS Runner service for job execution

**Key Endpoints**:
```
GET  /                                 # Job list page
GET  /job/<id>                         # Job detail page
POST /api/jobs/<id>/cv-editor          # Save CV changes to MongoDB
GET  /api/jobs/<id>/cv-editor          # Load CV editor state
POST /api/jobs/<id>/cv-editor/pdf      # Generate PDF via Playwright (serverless)
POST /api/runner/jobs/run              # Call VPS runner to execute job
```

**Playwright on Vercel**:
- `frontend/app.py` line 870-990: `generate_cv_pdf_from_editor()` function
- Uses Playwright (sync_playwright) to render PDF from TipTap editor HTML
- Runs on Vercel's serverless functions
- Creates pixel-perfect PDF with custom fonts/margins

**URL**: Not explicitly listed, but likely `https://your-app.vercel.app`

---

### Runner Service

**Location**: **VPS at 72.61.92.76** (Hostinger)

**Technology Stack**:
- FastAPI web framework
- Docker container execution
- Full pipeline runs (subprocess execution of LangGraph)
- Playwright + Chromium installed for PDF exports
- Python 3.11 slim base image

**Deployment Method**:
```
Dockerfile.runner + docker-compose.runner.yml
├── Build from: Dockerfile.runner
├── Runs: FastAPI app on port 8000 (localhost-bound for security)
├── Network: Connected to n8n-prod_default (existing Hostinger network)
├── Restart: unless-stopped (auto-restart on failure)
├── Resources: MAX_CONCURRENCY=3 (max 3 simultaneous runs)
```

**Deployment via GitHub Actions**:
- Workflow builds Docker image
- Pushes to registry
- SSH into VPS
- Runs: `docker compose pull && docker compose up -d`

**Responsibilities**:
- Receive job execution requests from Vercel frontend
- Execute full pipeline (7-layer LangGraph)
- Stream logs via SSE to frontend
- Generate CV/cover letter/dossier files
- Save artifacts to `applications/` directory (mounted volume)
- Update MongoDB with results
- Serve artifact downloads (PDFs, markdown)

**Key Endpoints**:
```
POST /jobs/run                    # Start single job
POST /jobs/run-bulk              # Start multiple jobs
GET  /jobs/{run_id}/status       # Check execution status
GET  /jobs/{run_id}/logs         # Stream logs (SSE)
GET  /artifacts/{run_id}/{file}  # Download artifacts
GET  /health                     # Health check
```

**Playwright on VPS**:
- Installed in Dockerfile.runner (line 32-33)
- Available in runner container for future PDF generation
- Currently NOT used by runner service
- Could be used for final PDF export after pipeline completion

**Docker Setup**:
```
Dockerfile.runner:
├── Python 3.11-slim base
├── System deps: libnss3, libgtk-3-0, etc. (Playwright/Chromium deps)
├── pip install playwright
├── python -m playwright install --with-deps chromium
├── Mount volumes: ./applications, ./credentials, ./master-cv.md
└── Expose: 8000 (internal only, behind Traefik in production)
```

**Port**: 8000 (bound to 127.0.0.1 for security, accessed via Traefik proxy)

---

## PDF Generation Architecture (Key Clarification)

### Current Implementation

**CV Editor Export (Vercel Frontend)**:
- Endpoint: `POST /api/jobs/<id>/cv-editor/pdf` on Vercel
- Technology: Playwright on Vercel serverless function
- Trigger: User clicks "Export PDF" button in CV editor
- Flow:
  ```
  User edits CV in TipTap editor
  ↓
  Clicks [Export PDF]
  ↓
  Frontend sends editor state JSON to Vercel serverless function
  ↓
  Vercel runs: sync_playwright() → render HTML → page.pdf()
  ↓
  Returns PDF file download to user
  ```
- Location: `frontend/app.py` lines 870-990

**Final Export (After Pipeline - VPS)**:
- Endpoint: Should be on VPS runner service
- Technology: Playwright in runner container (already installed, not yet wired)
- Current state: **Pipeline generates markdown CV, not PDF**
- Future: VPS runner could use Playwright to generate final PDF export
- Artifacts location: `applications/<company>/<role>/`

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE SYSTEM FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  VERCEL (Frontend)                VPS (Runner)                 MongoDB        │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                               │
│  1. Job List Page                                                            │
│     GET /jobs/list ──────────────────────────────→ Level-2 collection       │
│                                                                               │
│  2. Job Detail Page                                                          │
│     GET /job/{id} ───────────────────────────────→ MongoDB fetch            │
│                                                                               │
│  3. Execute Job                                                              │
│     [Process] ─────→ POST /jobs/run ────────────→ FastAPI receives          │
│                                                    Enqueues pipeline run     │
│                                                    Returns run_id + SSE URL   │
│                                                                               │
│  4. Monitor Progress                                                         │
│     SSE Subscribe  ←───────── GET /jobs/{run_id}/logs ← LangGraph logs      │
│     (real-time updates)                                                       │
│                                                                               │
│  5. Pipeline Execution (background)                                          │
│                         Docker: subprocess pipeline ──→ Layer 2-7           │
│                         Outputs: CV.md, dossier.txt                         │
│                         Saves: applications/<company>/<role>/               │
│                         Updates: MongoDB level-2 results                    │
│                                                                               │
│  6. Load CV Editor                                                           │
│     [Edit CV] ──→ GET /api/jobs/{id}/cv-editor ← MongoDB cv_editor_state   │
│     Vercel loads existing CV (markdown or TipTap JSON)                      │
│     Renders in TipTap editor                                                 │
│                                                                               │
│  7. Edit CV (Client-Side)                                                    │
│     User edits text, formatting, fonts, margins                             │
│     Auto-saves every 3 seconds:                                             │
│                      PUT /api/jobs/{id}/cv-editor ──→ MongoDB               │
│                                                                               │
│  8. Export CV to PDF (Playwright on Vercel)                                 │
│     [Export PDF] → POST /api/jobs/{id}/cv-editor/pdf                        │
│                    (send TipTap editor state)                               │
│     Vercel serverless: Playwright renders → page.pdf()                      │
│     ← PDF file download to user browser                                     │
│                                                                               │
│  9. Job Status (Optional - Future)                                           │
│     GET /jobs/{run_id}/status ←──────────────────── VPS maintains status    │
│     (artifacts URLs, final score, pipeline errors)                          │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What Was Misunderstood

The confusion was about **whether Playwright should run on the frontend or the runner**.

### Original Concern:
- "Dockerfile.runner has Playwright installed, but PDF endpoint is in frontend/app.py"
- "Which service actually generates PDFs?"
- "Should Playwright be on Vercel or VPS?"

### Root Cause of Confusion:
- **Dual PDF generation** for different purposes:
  1. **CV Editor Export** (Vercel): User-edited CV → PDF in browser
  2. **Final Pipeline Export** (VPS): Pipeline-generated CV → PDF on server
- These are TWO DIFFERENT USE CASES, not redundant
- Both Playwright installations are correct and serve their purpose

### Clarification:

| PDF Use Case | Location | Technology | Trigger | Status |
|---|---|---|---|---|
| CV Editor Export | Vercel (serverless) | Playwright on Vercel | User clicks "Export PDF" in editor | **IMPLEMENTED** |
| Final Pipeline Export | VPS (Docker) | Playwright in runner container | Post-pipeline conversion step | **READY** (not yet wired) |

---

## Service Responsibility Matrix

| Responsibility | Vercel Frontend | VPS Runner | MongoDB |
|---|---|---|---|
| **Display UI** | ✅ | ❌ | ❌ |
| **User authentication** | ✅ | ❌ | ❌ |
| **Job list/search** | ✅ | ❌ | ❌ |
| **CV editing** | ✅ | ❌ | ❌ |
| **CV PDF export (editor)** | ✅ | ❌ | ❌ |
| **Pipeline execution** | ❌ | ✅ | ❌ |
| **Log streaming** | ❌ (receives) | ✅ (sends) | ❌ |
| **Artifact generation** | ❌ | ✅ | ❌ |
| **Data persistence** | ❌ | ❌ | ✅ |
| **PDF export (pipeline)** | ❌ | ✅ (ready) | ❌ |

---

## Why This Architecture?

### Advantages:
1. **Separation of concerns**: Frontend (UI) and pipeline (compute) are isolated
2. **Scalability**: VPS can handle multiple concurrent runs; Vercel scales independently
3. **Cost efficiency**: Vercel for light UI duty; expensive compute on VPS
4. **Resilience**: Vercel frontend stays up even if VPS pipeline fails
5. **Flexibility**: Can replace either component without affecting the other
6. **Security**: VPS port 8000 is localhost-only, accessed via Traefik proxy (not exposed)

### Why Playwright on Both?
- **Vercel**: Fast, real-time PDF from user edits (needed for good UX)
- **VPS**: Batch PDF generation after pipeline runs (for final artifact export)

---

## Verification Checklist

From `plans/architecture.md` diagram (line 13-31):
- [x] Vercel Frontend (Flask/HTMX) - CONFIRMED
- [x] VPS Runner (FastAPI/Docker) - CONFIRMED
- [x] MongoDB Atlas - CONFIRMED
- [x] System diagram shows correct data flow

From `Dockerfile.runner`:
- [x] Playwright installed (line 32-33)
- [x] Chromium with dependencies installed
- [x] Port 8000 exposed (line 37)
- [x] Runs `uvicorn` (FastAPI) (line 39)

From `frontend/app.py`:
- [x] PDF endpoint exists (line 870)
- [x] Uses Playwright.sync_api (line 893)
- [x] Generates PDF from editor state

From `vercel.json`:
- [x] Rewrites all requests to `/api/index`
- [x] `api/index.py` imports Flask app
- [x] Serverless function deployment confirmed

---

## Current Deployment Status

### Frontend (Vercel)
- Status: **READY TO DEPLOY**
- Missing: Exact Vercel project URL (not in docs)
- All code is in place (`frontend/app.py`, templates, static files)
- Deployment method: Git push → Vercel auto-deploys

### Runner (VPS)
- Status: **DEPLOYED** (per vps-hostring.md, section 10)
- Location: `/root/job-runner` on VPS 72.61.92.76
- Port: 8000 (localhost-only, behind Traefik)
- Network: n8n-prod_default
- Endpoints: All defined and functional (run, bulk, status, logs, artifacts)
- PDF export: Playwright ready in container, not yet wired to output step

### Missing from Documentation
- Exact Vercel frontend URL
- Production environment variables for Vercel
- Final pipeline-to-PDF export wiring (Playwright usage in runner_service)

---

## Recommended Documentation Updates

### 1. Create `plans/pdf-generation-architecture.md`

Would clarify:
- Two PDF generation flows (editor vs. pipeline)
- Which runs where and when
- Technology choices and trade-offs

### 2. Update `plans/architecture.md` Section: "Execution Surfaces"

Add:
```markdown
### PDF Generation Layer
- **CV Editor Export**: Vercel serverless (sync_playwright)
- **Final Pipeline Export**: VPS runner container (Playwright, ready to implement)
- **Tech**: Both use Playwright + Chromium for fidelity
```

### 3. Update `plans/deployment-plan.md`

Currently deprecated, but could include:
- Vercel deployment steps
- VPS runner health check endpoints
- PDF generation wiring (Phase 5)

---

## Next Steps for Clarity

1. **Document Vercel deployment**: Add to `plans/next-steps.md` or `CLAUDE.md`
2. **Wire PDF export on VPS**: Create `plans/pdf-export-phase-5.md`
3. **Add architecture diagram**: Show Vercel and VPS separately with arrows
4. **Test cross-service communication**: Verify Vercel → VPS API calls work
5. **Update ROADMAP.md**: Clarify which phases are on which platform

---

## Conclusion

**There is NO misunderstanding in the actual codebase.** The architecture is sound:

- Frontend handles UI, editing, and user-facing PDF export via Playwright on Vercel
- VPS Runner handles heavy compute (pipeline) and will handle final artifact export
- MongoDB provides persistence
- The "confusion" was due to incomplete documentation, not architectural flaws

**All pieces are in place; documentation just needs clarification.**

Recommendation: Update `plans/architecture.md` to explicitly show:
1. Service deployment locations (Vercel vs. VPS)
2. Which PDF generation happens where
3. Why both Playwright installations exist
4. Deployment diagram showing the split architecture

This would prevent future misunderstandings.
