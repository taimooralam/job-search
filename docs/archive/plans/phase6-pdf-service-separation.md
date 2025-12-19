# Phase 6: PDF Service Separation - Architecture Plan

**Created**: 2025-11-28
**Status**: Planning
**Priority**: High (Infrastructure, 4-6 hours)
**Assigned to**: architecture-debugger or job-search-architect

---

## Executive Summary

Currently, the runner service handles both pipeline execution AND PDF generation (via Playwright). This creates tight coupling and limits scalability. This plan separates PDF generation into a dedicated Docker container for better separation of concerns, independent scaling, and preparation for future document types.

---

## Problem Statement

### Current Architecture Issues

1. **Tight Coupling**: Runner service responsible for two distinct concerns
   - Pipeline orchestration (layer execution, state management)
   - PDF rendering (Playwright, Chromium, file generation)

2. **Scalability Limitations**:
   - Can't scale PDF generation independently from pipeline
   - Playwright/Chromium is resource-heavy, impacts pipeline execution
   - One bottleneck blocks both services

3. **Resource Management**:
   - Chromium requires 100+ MB memory per instance
   - PDF rendering blocks pipeline execution if it takes >10 seconds
   - No way to prioritize pipeline over PDFs or vice versa

4. **Limited Extensibility**:
   - Adding new document types (cover letters, dossiers) requires modifying runner
   - Each new document type adds complexity to runner service
   - No clear separation for future document services

---

## Business Case

### Current Scope
- PDF generation for CVs only (via Phase 4 implementation)

### Future Scope
- Cover letter PDF export (planned Phase 6 feature)
- Dossier PDF export (planned Phase 7 feature)
- Possibly: resume PDF, portfolio PDF, etc.

### Why Separation Matters
- **Today**: CV PDFs are low-volume (manual user action)
- **Tomorrow**: Automated PDF generation for all 7-layer outputs
  - Layer 6 generates: CV + Cover Letter → both need PDF versions
  - Layer 7 generates: Dossier → also needs PDF version
- **Future**: Could add scheduled batch PDF generation

---

## Technical Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Job Search System (CURRENT)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐        ┌──────────────────────────────────────────┐   │
│  │ Vercel           │        │ VPS Runner Service (FastAPI)             │   │
│  │ (Frontend)       │       │  ┌──────────────────────────────────────┐ │   │
│  │ Flask/HTMX       │       │  │ Pipeline Execution                   │ │   │
│  │                  │◄──────┤  │ (Layers 1-7)                         │ │   │
│  │ POST /api/pdf    │       │  └──────────────────────────────────────┘ │   │
│  │                  │       │  ┌──────────────────────────────────────┐ │   │
│  └──────────────────┘       │  │ PDF Generation (Playwright)          │ │   │
│                              │  │ ├─ TipTap to HTML                   │ │   │
│                              │  │ ├─ Chromium rendering               │ │   │
│                              │  │ └─ PDF output                       │ │   │
│                              │  └──────────────────────────────────────┘ │   │
│                              │  PROBLEM: Two services in one container   │   │
│                              └──────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

                            PROPOSED ARCHITECTURE

┌─────────────────────────────────────────────────────────────────────────────┐
│                          Job Search System (PROPOSED)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐      ┌──────────────────┐    ┌──────────────────┐    │
│  │ Vercel           │      │ VPS Runner       │    │ VPS PDF Service  │    │
│  │ (Frontend)       │     │ (FastAPI)        │    │ (FastAPI)        │    │
│  │ Flask/HTMX       │     │                  │    │                  │    │
│  │                  │     │ Pipeline Layer   │    │ PDF Generation   │    │
│  │ POST /api/pdf◄─┐ │     │ Execution        │    │ ├─ TipTap→HTML   │    │
│  │                 │ │     │                  │    │ ├─ Rendering     │    │
│  └──────────────────┘ │    │ (Layers 1-7)     │    │ └─ PDF output    │    │
│                       │    │                  │    │                  │    │
│                       │    └──────────────────┘    └──────────────────┘    │
│                       │                                      ▲              │
│                       │    ┌──────────────────────────────────┘              │
│                       └────┤ Internal Docker Network                         │
│                            │ PDF Service exposed internally only            │
│                            │                                                │
│                      ┌─────┴────────────┐                                   │
│                      │ MongoDB Atlas    │                                   │
│                      │ (Shared)         │                                   │
│                      └──────────────────┘                                   │
│                                                                              │
│  BENEFITS:                                                                  │
│  • Clear separation of concerns                                             │
│  • Independent scaling (pipeline ≠ PDF)                                     │
│  • Better resource management                                               │
│  • Easier to add new document types                                         │
│  • PDF service isolated, can restart without affecting pipeline             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Specifications

#### New PDF Service Container

**Name**: `pdf-service`

**Location**: `/root/pdf-service` on VPS (alongside `/root/job-runner`)

**Technology Stack**:
- Python 3.11+ (FastAPI)
- Playwright 1.40.0+
- Chromium browser
- MongoDB driver (read-only for job data)

**Docker Image**:
```dockerfile
FROM python:3.11-slim

# Install Playwright + system dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    && python -m pip install --upgrade pip \
    && pip install playwright \
    && playwright install chromium

# Copy app
COPY pdf_service/ /app/
WORKDIR /app

# Install Python dependencies
RUN pip install fastapi uvicorn pymongo requests

# Run server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
```

**Resource Requirements**:
- Memory: 512 MB - 2 GB (depending on concurrent PDF operations)
- CPU: 0.5 - 2 cores
- Disk: 2 GB (for Chromium and Python env)

#### API Endpoints

**Base URL**: `http://pdf-service:8001` (internal Docker network only)

**Health Check**:
```http
GET /health
Response: {"status": "healthy", "timestamp": "2025-11-28T10:00:00Z"}
```

**Generic PDF Rendering**:
```http
POST /render-pdf
Content-Type: application/json

{
  "html": "<html>...</html>",
  "css": "body { margin: 1in; }",
  "pageSize": "letter",     // "letter" | "a4"
  "printBackground": true
}

Response: Binary PDF file
```

**CV PDF Export** (Specialized):
```http
POST /cv-to-pdf
Content-Type: application/json

{
  "tiptap_json": { "type": "doc", "content": [...] },
  "documentStyles": {
    "lineHeight": 1.15,
    "margins": { "top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0 },
    "pageSize": "letter"
  },
  "header": "Optional header text",
  "footer": "Optional footer text",
  "company": "TechCorp",
  "role": "Senior Engineer"
}

Response: Binary PDF file
Filename: CV_TechCorp_Senior_Engineer.pdf
```

**Cover Letter PDF Export** (Planned):
```http
POST /cover-letter-to-pdf
Content-Type: application/json

{
  "tiptap_json": { "type": "doc", "content": [...] },
  "company": "TechCorp"
}

Response: Binary PDF file
Filename: CoverLetter_TechCorp.pdf
```

**Dossier PDF Export** (Planned):
```http
POST /dossier-to-pdf
Content-Type: application/json

{
  "html": "<html>...</html>",  // From Layer 7 dossier_generator
  "company": "TechCorp",
  "role": "Senior Engineer"
}

Response: Binary PDF file
Filename: Dossier_TechCorp_Senior_Engineer.pdf
```

#### Error Handling

```http
400 Bad Request
{
  "error": "INVALID_REQUEST",
  "message": "Missing required field: tiptap_json"
}

500 Internal Server Error
{
  "error": "RENDERING_FAILED",
  "message": "Playwright rendering failed: timeout"
}

503 Service Unavailable
{
  "error": "SERVICE_OVERLOADED",
  "message": "Too many concurrent PDF operations"
}
```

---

## Implementation Phases

### Phase 1: Create PDF Service Container (2 hours)

**Tasks**:
- Create `/root/pdf-service` directory on VPS
- Create `Dockerfile.pdf-service` with Playwright + Chromium
- Create `pdf_service/app.py` with FastAPI scaffolding
- Add to `docker-compose.runner.yml` for orchestration
- Add health check endpoint

**Deliverables**:
- PDF service Docker image buildable
- Container starts without errors
- Health endpoint returns 200 OK

**Testing**:
- `curl http://pdf-service:8001/health` from runner service

**Files**:
- `Dockerfile.pdf-service` (new)
- `pdf_service/app.py` (new)
- `pdf_service/__init__.py` (new)
- Update `docker-compose.runner.yml`

### Phase 2: Implement PDF Endpoints (2 hours)

**Tasks**:
- Move `pdf_helpers.py` logic to PDF service
- Implement `/render-pdf` endpoint (generic HTML/CSS → PDF)
- Implement `/cv-to-pdf` endpoint (TipTap JSON → PDF)
- Add error handling and validation
- Add logging for debugging

**Deliverables**:
- Both endpoints functional
- Test calls work from localhost
- Error responses match spec

**Testing**:
- Unit tests for each endpoint
- Manual test with curl/Postman
- Test with invalid payloads (400 errors)
- Test with large documents (timeout handling)

**Files**:
- `pdf_service/app.py` (endpoints)
- `pdf_service/pdf_helpers.py` (moved from runner)
- `tests/pdf_service/test_endpoints.py` (new)

### Phase 3: Update Runner Service Integration (1 hour)

**Tasks**:
- Update `runner_service/app.py` POST `/api/jobs/{id}/cv-editor/pdf` endpoint
- Change from local Playwright to HTTP call to PDF service
- Update error handling for network failures
- Update timeouts and retry logic

**Deliverables**:
- Runner proxies to PDF service
- CV export still works end-to-end
- Proper error messages on service unavailable

**Testing**:
- Integration test: runner → PDF service → PDF
- Test network failure handling (PDF service down)
- Test timeout handling (slow PDF generation)

**Files**:
- `runner_service/app.py` (modified)
- `runner_service/pdf_helpers.py` (delete or deprecate)
- `tests/runner/test_pdf_proxy.py` (new)

### Phase 4: Update Frontend Integration (30 minutes)

**Tasks**:
- Verify frontend still works with updated runner endpoint
- No changes needed (frontend calls runner, runner calls PDF service)
- Ensure frontend error handling still works

**Deliverables**:
- CV export button in editor still works
- PDF downloads to user's computer
- Error messages display correctly

**Testing**:
- Manual test: Edit CV, export PDF, verify file downloads

**Files**:
- No changes (frontend-facing API unchanged)

### Phase 5: Deployment & Testing (1 hour)

**Tasks**:
- Build and push PDF service image
- Update VPS docker-compose.yml with both services
- Deploy both runner and PDF services
- Verify inter-service communication on Docker network
- Test end-to-end CV export from frontend

**Deliverables**:
- Both services running on VPS
- CV export working end-to-end
- All unit/integration tests passing

**Testing**:
- `docker compose ps` shows both services running
- `docker compose logs pdf-service` shows no errors
- Frontend CV export completes successfully
- Check MongoDB for generated PDF artifacts

**Files**:
- Updated `docker-compose.runner.yml`
- VPS deployment scripts

### Phase 6: Add Cover Letter Support (Planned Phase 6)

**Status**: Post-implementation
**Tasks**:
- Implement `/cover-letter-to-pdf` endpoint in PDF service
- Update Layer 6 to call PDF service for cover letter export
- Add UI button in frontend for cover letter PDF export

**Effort**: 2-3 hours

### Phase 7: Add Dossier Support (Planned Phase 7)

**Status**: Post-implementation
**Tasks**:
- Implement `/dossier-to-pdf` endpoint in PDF service
- Update Layer 7 to call PDF service for dossier export
- Add UI button for dossier PDF export

**Effort**: 2-3 hours

---

## Migration Plan

### Step 1: Validate Current Implementation

```bash
# Test CV export works before changes
curl -X POST http://localhost:8000/api/jobs/{job_id}/cv-editor/pdf \
  -H "Content-Type: application/json" \
  -d '{"version": 1, "content": {...}, "documentStyles": {...}}' \
  -o test.pdf
```

### Step 2: Build PDF Service Locally

```bash
# On VPS
cd /root/pdf-service
docker build -f Dockerfile.pdf-service -t pdf-service:latest .
docker run -d --name pdf-service -p 8001:8001 pdf-service:latest
```

### Step 3: Test PDF Service Directly

```bash
# Test /health
curl http://localhost:8001/health

# Test /cv-to-pdf
curl -X POST http://localhost:8001/cv-to-pdf \
  -H "Content-Type: application/json" \
  -d '{"tiptap_json": {...}, "documentStyles": {...}}' \
  -o test.pdf
```

### Step 4: Update Runner Service

```bash
# Modify runner_service/app.py to call PDF service
# Test runner endpoint still works
curl -X POST http://localhost:8000/api/jobs/{job_id}/cv-editor/pdf \
  -H "Content-Type: application/json" \
  -d '{"version": 1, "content": {...}, "documentStyles": {...}}' \
  -o test.pdf
```

### Step 5: Deploy Both Services

```bash
# Update docker-compose.runner.yml with both services
docker compose -f docker-compose.runner.yml up -d

# Verify both running
docker compose ps
```

### Step 6: Test End-to-End

1. Open frontend (Vercel)
2. Edit CV
3. Click "Export PDF"
4. Verify PDF downloads
5. Check VPS logs for calls between services

### Rollback Plan

If PDF service causes issues:

```bash
# Quickly revert runner to local Playwright
git checkout runner_service/app.py
docker compose -f docker-compose.runner.yml restart runner

# Keep PDF service running (no harm, not called)
# OR stop it
docker compose stop pdf-service
```

---

## Configuration

### Environment Variables

**PDF Service (.env)**:
```bash
PORT=8001                              # Internal port only
PYTHONUNBUFFERED=1                    # Logging
PLAYWRIGHT_HEADLESS=true              # Always headless
PLAYWRIGHT_TIMEOUT=30000              # 30 seconds
MAX_CONCURRENT_PDFS=5                 # Rate limiting
LOG_LEVEL=INFO
```

**Runner Service Changes**:
```bash
# NEW
PDF_SERVICE_URL=http://pdf-service:8001

# REMOVE (no longer used locally)
# PLAYWRIGHT_HEADLESS (now in PDF service)
```

### Docker Network

Both services on same internal Docker network:

```yaml
# docker-compose.runner.yml
services:
  runner:
    networks:
      - job-pipeline
    environment:
      PDF_SERVICE_URL: http://pdf-service:8001

  pdf-service:
    networks:
      - job-pipeline

networks:
  job-pipeline:
    driver: bridge
```

---

## Success Criteria

- [x] PDF service container builds without errors
- [x] Health endpoint returns 200 OK
- [x] `/cv-to-pdf` endpoint generates valid PDF
- [x] Runner calls PDF service instead of local Playwright
- [x] CV export works end-to-end (frontend → runner → PDF service → PDF)
- [x] Error handling covers all failure modes
- [x] No performance degradation (<500ms latency increase)
- [x] Both services running stably for 24+ hours
- [x] Integration tests passing (100%)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Network latency between services | Low | Low (10-50ms typical) | Monitor inter-service calls |
| PDF service crash | Low | Medium (CV export fails) | Auto-restart policy, health checks |
| Docker network misconfiguration | Medium | Medium (services can't talk) | Test on staging first |
| Chromium out of memory | Low | High (OOM kill) | Set memory limits, monitor usage |
| Breaking changes to PDF helpers | Low | High (CV export broken) | Comprehensive unit tests before deploy |

---

## Timeline

**Total Effort**: 4-6 hours (1 developer, 1 session)

- Phase 1: 2 hours
- Phase 2: 2 hours
- Phase 3: 1 hour
- Phase 4: 30 minutes
- Phase 5: 1 hour
- **Total**: ~6-7 hours

**Deployment Window**: 1-2 hours (low-risk, easy rollback)

---

## Next Steps

1. Review and approve this architecture plan
2. Assign to architecture-debugger for implementation
3. Create Phase 6 implementation task in missing.md
4. Schedule 1-session sprint (4-6 hours)
5. After completion: Add cover letter and dossier PDF endpoints (Phase 6-7 features)

---

## Related Documentation

- Architecture: See `plans/architecture.md` - PDF Generation Architecture section
- Current Implementation: Phase 4 in `plans/missing.md`
- Deployment: See `plans/next-steps.md` for VPS configuration
