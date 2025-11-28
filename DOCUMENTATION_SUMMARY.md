# Documentation Summary: PDF Service Separation + Export Button Bug
**Date**: 2025-11-28 | **Status**: Complete | **Committed**: Yes

---

## Overview

Two critical items have been comprehensively documented for the Job Intelligence Pipeline:

1. **Export PDF Button Bug** - Core feature broken on job detail page
2. **PDF Service Separation** - Infrastructure improvement for better architecture

Both include detailed investigation procedures, implementation plans, and success criteria.

---

## Item 1: CRITICAL BUG - Export PDF Button on Detail Page

### File Location
**`/Users/ala0001t/pers/projects/job-search/plans/bugs/export-pdf-detail-page.md`** (13 KB, ~10 pages)

### Issue Summary
- **Status**: Needs Investigation & Fix
- **Severity**: HIGH (breaks core feature)
- **Effort**: 1-3 hours (depends on root cause)
- **Expected**: User can export CV as PDF from detail page
- **Actual**: Button doesn't respond, no PDF downloads (side panel button works)
- **Workaround**: Users can export from CV editor side panel

### Investigation Included
- 40+ item checklist across 7 categories
- Step-by-step procedures with code examples
- Browser DevTools instructions (Network, Console tabs)
- curl commands to test API directly
- 6 root cause scenarios with effort estimates

### Root Cause Scenarios
1. Button doesn't exist in HTML (15 min fix)
2. Button hidden by CSS (15 min fix)
3. Click handler not attached (15 min fix)
4. Wrong endpoint or missing data (1-2 hours)
5. CORS or auth issue (30 min)
6. Feature not implemented (2-3 hours)

### Testing Plan
- Unit tests for endpoint
- E2E tests with Playwright
- Manual testing procedures
- Success criteria defined

### How to Use This Document
1. Start: Read "Issue Summary"
2. Investigate: Use "Investigation Steps" section
3. Follow: "Investigation Checklist" items 1-8
4. Identify: Root cause using "Root Cause Hypotheses"
5. Implement: Match scenario from "Implementation Scenarios"
6. Test: Run tests from "Testing Plan"
7. Verify: Check "Success Criteria"

---

## Item 2: Infrastructure Task - PDF Service Separation

### File Location
**`/Users/ala0001t/pers/projects/job-search/plans/phase6-pdf-service-separation.md`** (19 KB, ~15 pages)

### Objective
Separate PDF generation from runner service into dedicated Docker container for better separation of concerns and independent scaling.

### Business Case
- **Today**: CV PDF export (Phase 4)
- **Tomorrow**: Cover letter + dossier PDFs (Phase 6-7)
- **Problem**: Adding each new document type requires modifying runner service
- **Solution**: Dedicated PDF service handles all document rendering

### Proposed Architecture
```
Current (tight coupling):
  Runner Service
  ├─ Pipeline Execution
  └─ PDF Generation

Proposed (separation of concerns):
  Runner Service ──► PDF Service
  ├─ Pipeline       ├─ PDF Generation
  └─ (Orchestration)└─ (Rendering)
```

### API Endpoints
- POST `/render-pdf` (generic HTML/CSS → PDF)
- POST `/cv-to-pdf` (TipTap JSON → PDF, current)
- POST `/cover-letter-to-pdf` (planned Phase 6)
- POST `/dossier-to-pdf` (planned Phase 7)

### Implementation Phases
1. Create PDF service container (2 hours)
2. Implement PDF endpoints (2 hours)
3. Update runner integration (1 hour)
4. Deployment & testing (1 hour)
5. Future: Add cover letter support
6. Future: Add dossier support

**Total Effort**: 4-6 hours (can run parallel with Phase 5)

### Benefits
- Separation of concerns (pipeline ≠ PDF rendering)
- Independent scaling and resource management
- Easy to add new document types
- PDF service isolated (can restart without affecting pipeline)
- Better testability

### Configuration
- PDF service runs on internal Docker network
- No frontend changes needed (still calls runner, runner calls PDF service)
- Environment variables: PORT, PLAYWRIGHT_HEADLESS, timeouts
- Docker compose orchestration

### Files to Create/Modify
**New**:
- Dockerfile.pdf-service
- pdf_service/app.py
- tests/pdf_service/test_endpoints.py

**Modify**:
- docker-compose.runner.yml (add pdf-service)
- runner_service/app.py (proxy to pdf-service)

**No Changes**:
- frontend/app.py (API unchanged)
- frontend templates (UI unchanged)

### How to Use This Document
1. Start: Read "Executive Summary" and "Problem Statement"
2. Understand: Review "Technical Approach" and diagrams
3. Plan: Read "Implementation Phases" section
4. Implement: Follow phase-by-phase instructions
5. Test: Use "Migration Plan" and "Rollback Plan"
6. Deploy: Follow "Configuration" section
7. Verify: Check "Success Criteria"

---

## Updated Documentation Files

### 1. plans/missing.md
**Added**: New "Critical Issues (2025-11-28)" section (75 lines)
- Bug summary with investigation checklist
- Infrastructure task summary with implementation breakdown
- Both items linked to detailed plan documents
- Severity and effort estimates provided
- Timeline information included

### 2. plans/architecture.md
**Added**: New "Phase 6: PDF Service Separation (PLANNED)" section (175 lines)
- Current architecture issue diagram
- Proposed architecture diagram
- Motivation for separation
- Detailed API endpoint specifications
- Implementation plan
- Benefits and success criteria
- Files to create/modify

### 3. plans/next-steps.md
**Updated**: Complete reorganization of priorities
- Added Priority 0: FIX CRITICAL BUG (detail page export)
  - Quick issue summary
  - Investigation steps checklist
  - Timeline: fix immediately
- Moved Phase 5 to Priority 1
  - Added note: "Blocked by Priority 0"
- Added Priority 2: Infrastructure (PDF Service)
  - Overview and problem statement
  - Implementation breakdown
  - Timeline: can run parallel with Priority 1

### 4. New Report
**Created**: `reports/agents/doc-sync/DOCUMENTATION_SYNC_2025_11_28.md`
- Complete sync report with all changes
- Verification checklist
- Recommended next steps
- Agent recommendations for implementation

---

## Key Specifications & References

### Export PDF Bug
- **Browser DevTools**: Network tab shows POST to `/api/jobs/{id}/cv-editor/pdf`
- **Comparison**: Working editor button uses `exportCVToPDF()` function
- **Testing**: Unit test + E2E test coverage planned
- **Success**: Button downloads PDF with name `CV_<Company>_<Title>.pdf`

### PDF Service
- **Container**: pdf-service on internal Docker network (http://pdf-service:8001)
- **Port**: 8001 (internal only, not exposed)
- **Technology**: FastAPI + Playwright + Chromium
- **Dependencies**: No frontend changes (transparent upgrade)
- **Rollback**: Simple (revert runner to local Playwright)

---

## Recommended Workflow

### Phase 1: Fix Critical Bug (Priority 0)
1. Assign to: frontend-developer
2. Effort: 1-3 hours
3. Steps:
   - Read `plans/bugs/export-pdf-detail-page.md`
   - Run investigation checklist
   - Identify root cause (use scenarios)
   - Implement fix
   - Add test coverage
   - Verify success criteria

### Phase 2: Infrastructure Parallel Work
1. Assign to: architecture-debugger
2. Effort: 4-6 hours
3. Timeline: Start after Phase 1 is identified (can be parallel)
4. Steps:
   - Review `plans/phase6-pdf-service-separation.md`
   - Create PDF service container
   - Implement endpoints
   - Update runner integration
   - Deploy and test

### Phase 3: Phase 5 Implementation
1. Assign to: frontend-developer
2. Effort: 8-10 hours
3. Timeline: Start after Priority 0 is fixed
4. Reference: `plans/phase5-page-break-visualization.md`

---

## File Structure Reference

### New Files Created
```
plans/
  phase6-pdf-service-separation.md    (19 KB) - Full implementation plan
  bugs/
    export-pdf-detail-page.md         (13 KB) - Bug report & investigation
reports/
  agents/doc-sync/
    DOCUMENTATION_SYNC_2025_11_28.md  (Complete sync report)
```

### Files Modified
```
plans/
  missing.md          (Added Critical Issues section)
  architecture.md     (Added Phase 6 specifications)
  next-steps.md       (Reorganized priorities)
```

### All Absolute Paths
- Bug plan: `/Users/ala0001t/pers/projects/job-search/plans/bugs/export-pdf-detail-page.md`
- Infrastructure plan: `/Users/ala0001t/pers/projects/job-search/plans/phase6-pdf-service-separation.md`
- Tracking: `/Users/ala0001t/pers/projects/job-search/plans/missing.md`
- Architecture: `/Users/ala0001t/pers/projects/job-search/plans/architecture.md`
- Next steps: `/Users/ala0001t/pers/projects/job-search/plans/next-steps.md`

---

## Commit Information

**Commit Hash**: 0ee18be5
**Message**: "docs: Document PDF service separation and export PDF button bug"

**Changes**:
- Modified: plans/architecture.md
- Modified: plans/missing.md
- Modified: plans/next-steps.md
- Created: plans/bugs/export-pdf-detail-page.md
- Created: plans/phase6-pdf-service-separation.md
- Created: reports/agents/doc-sync/DOCUMENTATION_SYNC_2025_11_28.md

**Total Lines Added**: 1655+

---

## Summary

Documentation has been successfully created and committed for both items:

1. **Export PDF Button Bug** - Ready for investigation and fix (1-3 hours)
   - Comprehensive investigation checklist
   - 6 implementation scenarios with effort estimates
   - Testing plan with success criteria

2. **PDF Service Separation** - Ready for implementation (4-6 hours)
   - Detailed architecture specifications
   - 6-phase implementation plan
   - API endpoint definitions
   - Migration and rollback procedures

All documentation is cross-referenced, prioritized correctly, and includes success criteria.

**Next Action**: Assign Priority 0 (bug fix) to frontend-developer to investigate and fix detail page export button.
