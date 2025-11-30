# Documentation Update Report: Dossier PDF Export Requirement

**Date**: 2025-11-30
**Agent**: doc-sync
**Status**: Documentation Updated
**Related Files**:
- `plans/missing.md` - Added new requirement #8
- `plans/dossier-pdf-export-implementation.md` - Detailed implementation plan (NEW)
- This report

---

## Summary

A significant architectural requirement change has been documented: **Remove local dossier file storage and replace with on-demand PDF export via API endpoint.**

This change improves system architecture by:
1. Making the service stateless (no local file accumulation)
2. Reducing disk space consumption on VPS
3. Ensuring PDFs always reflect current database state
4. Simplifying deployment and scaling

---

## Documentation Changes

### 1. Updated: `plans/missing.md`

**Section**: Remaining Gaps → UI/UX → #8 (NEW)

**Changes**:
- Added comprehensive requirement entry: "Remove Local Dossier Storage, Add PDF Export"
- Status: Planning Phase
- Priority: Medium (Architecture Improvement)
- Location: After #7b, before Documentation/Planning section (lines 1822-1935)

**Content Structure**:
- Objective statement
- Current behavior (with code references)
- New requirement details (PDF button, endpoint, content structure)
- Technical implementation checklist
- Files to remove (with line numbers)
- PDF generation approach (2 options)
- Files to modify/create
- Effort estimate: 5-6 hours
- Related code references
- Benefits & risks
- Testing strategy
- Deployment notes

### 2. Created: `plans/dossier-pdf-export-implementation.md`

**Purpose**: Detailed implementation guide for the requirement

**Sections**:
1. Executive Summary
2. Architecture (with diagram)
3. PDF Content Structure (with mockup)
4. Implementation Plan (4 phases)
   - Phase 1: Backend PDF Export Endpoint (2-3 hours)
   - Phase 2: Frontend UI Button (1 hour)
   - Phase 3: Remove Local Dossier Storage (1 hour)
   - Phase 4: Testing (1 hour)
5. File Changes Summary (what to modify/create/remove)
6. Dependencies & Considerations
7. Risk Mitigation
8. Success Criteria
9. Timeline
10. References & Next Steps

**Key Features**:
- Concrete code examples for implementation
- Test templates for unit & integration tests
- Manual testing checklist
- Risk analysis with mitigation strategies
- Deployment impact assessment

---

## Code Investigation: Current Dossier Storage

### Location: `src/layer7/output_publisher.py`

#### Current Implementation (Lines 185-234)

**What it does**:
```python
# 1. Creates directory structure
local_dir = Path('./applications') / company_safe / role_safe
local_dir.mkdir(parents=True, exist_ok=True)

# 2. Saves 4 types of files:
- dossier.txt (full opportunity dossier)
- cover_letter.txt (generated cover letter)
- fallback_cover_letters.txt (backup letters if no contacts)
- contacts_outreach.txt (formatted contact details)

# 3. Tracks saved paths in saved_paths dict for logging/reference
```

#### Files Generated

| File | Purpose | Size | Content |
|------|---------|------|---------|
| `dossier.txt` | Complete opportunity analysis (10 sections) | 5-20 KB | From DossierGenerator |
| `cover_letter.txt` | Personalized cover letter | 1-3 KB | Generated per opportunity |
| `fallback_cover_letters.txt` | Fallback letters (if no contacts found) | 2-6 KB | Multiple letters joined |
| `contacts_outreach.txt` | Formatted contact information | 1-2 KB | Primary + Secondary contacts |

#### Directory Structure

```
./applications/
├── Acme-Corp/                          (sanitized company name)
│   ├── Senior-Engineering-Manager/     (sanitized role title)
│   │   ├── dossier.txt
│   │   ├── cover_letter.txt
│   │   ├── contacts_outreach.txt
│   │   └── fallback_cover_letters.txt
│   └── Staff-Engineer/
│       ├── dossier.txt
│       ├── cover_letter.txt
│       └── ...
├── Google/
│   └── ...
└── ...
```

#### Total Size Impact

- Per opportunity: ~8-30 KB (4 text files)
- For 100 opportunities: ~1-3 MB
- For 1000 opportunities: ~8-30 MB (growing with each pipeline run)

---

## What Needs to Be Removed

### Code Removal Checklist

**File**: `src/layer7/output_publisher.py`

#### Import Removal
```python
# REMOVE:
from pathlib import Path

# KEEP: All other imports (os, etc.)
```

#### Method: `_save_local_artifacts()` (Lines 185-234)

**Action**: Remove entire method call and implementation

**Current Call Stack**:
1. Line 185: `def _save_local_artifacts(...)`
2. Lines 191-192: Create directories
3. Lines 198-228: Write 4 files to disk
4. Line 234+: Additional file operations

**Replacement**: Replace with logging only
```python
def _log_dossier_content(self, state: JobState, dossier_content: str):
    """Log dossier content for debugging (replaces file storage)."""
    self.logger.info(f"Dossier content for {state['company']}/{state['title']}:")
    self.logger.info(dossier_content[:500] + "...")  # Log first 500 chars
```

#### Side Effects to Check
- [ ] No code depends on `saved_paths` dict
- [ ] No downstream process reads from `./applications/`
- [ ] No frontend serves files from `./applications/`
- [ ] No CI/CD archives `./applications/` directory
- [ ] No Docker volume mounts depend on `./applications/`

---

## Docker-Compose Changes

### File: `docker-compose.runner.yml`

#### Current Volume Mount (Lines 20-21)

```yaml
volumes:
  # Pipeline artifacts
  - ./applications:/app/applications
  # Google credentials (if using Drive/Sheets)
  - ./credentials:/app/credentials:ro
  # Master CV for pipeline
  - ./master-cv.md:/app/master-cv.md:ro
```

#### Change Required

Remove:
```yaml
- ./applications:/app/applications
```

**Rationale**:
- Directory no longer needed since files aren't saved
- Reduces Docker volume overhead
- Simplifies deployment

**Impact**:
- No impact on running pipeline
- No data loss (database is source of truth)
- Cleaner container filesystem

---

## Frontend File Serving

### Investigation: Does frontend serve these files?

**Search Results**:
- `frontend/app.py`: No routes serve from `./applications/`
- `frontend/templates/`: No links to dossier files
- No artifact serving logic found

**Conclusion**: Frontend doesn't serve these files; they're only for local access/debugging.

---

## Database Persistence

### What gets stored in MongoDB?

The pipeline stores complete JobState in MongoDB, which includes:
- `dossier_content` (if saved)
- `cover_letter` (generated text)
- `contacts` (primary + secondary)
- All other pipeline outputs

**Source**: `src/layer7/output_publisher.py` saves to MongoDB separately

**Implication**: All data is already persisted to database; local files are redundant.

---

## PDF Service Integration

### Existing PDF Service Endpoints

**Service**: Docker container on port 8001 (internal only)

**Endpoints** (from `pdf_service/app.py`):
1. `POST /render-pdf` - HTML/CSS → PDF
2. `POST /cv-to-pdf` - TipTap JSON → PDF
3. `GET /health` - Service health check

**Availability**: pdf-service is already running and tested

**For this requirement**: Use `/render-pdf` to generate dossier PDFs

---

## Related Components

### PDF Generation Infrastructure (Already Exists)

1. **PDF Service**: `pdf_service/app.py`
   - Playwright-based PDF rendering
   - Handles concurrency (MAX_CONCURRENT_PDFS=5)
   - Health check endpoint

2. **PDF Helpers**: `pdf_service/pdf_helpers.py`
   - HTML template builders
   - TipTap JSON conversion
   - Margin/styling utilities

3. **Runner Integration**: `runner_service/app.py` (lines 150-200)
   - Proxies requests to PDF service
   - Error handling and logging

4. **Frontend Integration**: `frontend/app.py`
   - Proxies PDF service responses to browser
   - Sets download headers

### Current PDF Exports

The system already has:
- [x] CV to PDF (via pdf-service)
- [x] Job posting page to PDF (via pdf-service)
- [ ] Dossier to PDF (NEW - this requirement)

---

## Effort Assessment

### Detailed Breakdown

| Task | Complexity | Effort | Notes |
|------|-----------|--------|-------|
| Create PDF export module | Medium | 2 hours | Build HTML builder, integrate with pdf-service |
| Add Flask endpoint | Low | 1 hour | Straightforward Flask route |
| Add frontend button | Low | 1 hour | Duplicate existing CV export button pattern |
| Remove local storage | Medium | 1 hour | Search for all references, update output_publisher |
| Unit tests | Medium | 1 hour | Mock mongodb, pdf-service |
| Manual testing | Low | 1 hour | End-to-end in browser |
| **Total** | | **6-7 hours** | Including contingency |

### Risk-Adjusted Timeline

- Base estimate: 6 hours
- Contingency (15%): +1 hour
- **Total: 7 hours** (1 full day)

---

## Implementation Roadmap

### Phase 1: Foundation (3 hours)
- [ ] Create `src/api/pdf_export.py` (DossierPDFExporter class)
- [ ] Add `GET /api/jobs/{id}/export-pdf` endpoint
- [ ] Integration testing with pdf-service

### Phase 2: UI (1 hour)
- [ ] Add button to `frontend/templates/job_detail.html`
- [ ] Add JavaScript handler (`exportDossierPDF()`)

### Phase 3: Cleanup (1 hour)
- [ ] Remove local file saving from `output_publisher.py`
- [ ] Update docker-compose.runner.yml

### Phase 4: Testing & QA (2 hours)
- [ ] Unit tests
- [ ] Manual end-to-end testing
- [ ] Performance validation (<6 seconds per PDF)

---

## Success Criteria

1. **Functional**:
   - PDF exports successfully with all dossier content
   - File downloads with correct filename format
   - All 10 dossier sections present in PDF

2. **Technical**:
   - No local files created in `./applications/`
   - MongoDB remains single source of truth
   - PDF generation uses existing pdf-service

3. **Performance**:
   - PDF export completes in <6 seconds
   - No performance regression on job detail page

4. **Quality**:
   - 90%+ test coverage for pdf_export module
   - Error handling for all failure modes
   - Proper logging for debugging

5. **Deployment**:
   - No database migrations needed
   - No new environment variables
   - Clean removal of legacy code

---

## Verification Checklist

### Code Review
- [ ] PDF export module follows existing patterns (pdf_service, runner_service)
- [ ] Error handling covers all failure cases
- [ ] Logging is informative and doesn't expose secrets
- [ ] No hardcoded paths or magic numbers

### Testing
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass (mock pdf-service)
- [ ] Manual test: export works from job detail page
- [ ] Manual test: PDF renders correctly
- [ ] Manual test: No local files created

### Deployment
- [ ] Docker-compose changes validated
- [ ] No breaking changes to existing APIs
- [ ] Rollback plan documented (revert to local files if needed)

---

## Related Documentation

### See Also
- `plans/architecture.md` - System architecture (will need update)
- `plans/next-steps.md` - Next priority items
- `src/layer7/dossier_generator.py` - Current dossier generation logic
- `pdf_service/app.py` - PDF service implementation
- `frontend/templates/job_detail.html` - Frontend UI

---

## Questions for Implementation

1. **Should we include CV content in PDF or just link?**
   - Recommendation: Include link, reference to external CV
   - Rationale: Keeps PDF size manageable, CV already exported separately

2. **Should we support batch PDF exports?**
   - Out of scope for initial implementation
   - Can be added in Phase 2 if needed

3. **How do we handle very large dossiers (edge case)?**
   - Limit HTML size to 50KB max
   - Truncate long sections with "...see full content in MongoDB"
   - Test with real-world data

4. **Should we add PDF watermarks or company branding?**
   - Out of scope for initial implementation
   - Could be added as enhancement

5. **How do we monitor PDF generation failures?**
   - Log all errors with context
   - Track pdf-service health status
   - Add metrics to monitoring system

---

## Next Recommended Actions

1. **Design Phase**: Create HTML/CSS mockup for PDF template
2. **Implementation**: Follow phases in dossier-pdf-export-implementation.md
3. **Code Review**: Have team review pdf_export.py for patterns/security
4. **Testing**: Full manual testing before merging
5. **Deployment**: Include in next release
6. **Communication**: Document removal of local files in release notes

---

## Appendix: Code References

### Current Dossier Storage
**File**: `/Users/ala0001t/pers/projects/job-search/src/layer7/output_publisher.py`
**Lines**: 185-234
**Method**: `_save_local_artifacts()`

### Current Dossier Generation
**File**: `/Users/ala0001t/pers/projects/job-search/src/layer7/dossier_generator.py`
**Lines**: 1-100
**Class**: `DossierGenerator`
**Method**: `generate_dossier()`

### PDF Service
**File**: `/Users/ala0001t/pers/projects/job-search/pdf_service/app.py`
**Endpoints**: `/health`, `/render-pdf`, `/cv-to-pdf`, `/url-to-pdf`

### Frontend PDF Integration
**File**: `/Users/ala0001t/pers/projects/job-search/frontend/app.py`
**Routes**: `/api/jobs/<id>/cv-editor/pdf`, `/api/jobs/<id>/export-page-pdf`

### Job Detail UI
**File**: `/Users/ala0001t/pers/projects/job-search/frontend/templates/job_detail.html`
**Lines**: 367-372 (CV export), 536-541 (cover letter), 1043-1049 (page PDF)

---

## Report Metadata

**Generated By**: Documentation Sync Agent (doc-sync)
**Report Type**: Requirement Change Documentation
**Status**: Complete
**Next Review**: After implementation phase

---

## Sign-Off

Documentation updated to reflect new requirement: **Remove Local Dossier Storage, Add PDF Export**

**Files Updated**:
1. `plans/missing.md` - Added requirement entry (lines 1822-1935)
2. `plans/dossier-pdf-export-implementation.md` - Created new detailed plan
3. `reports/agents/doc-sync/2025-11-30-dossier-pdf-export-requirement.md` - This report

**Status**: Ready for implementation planning and team review

**Next Priority**: Approve requirement, begin design phase for HTML template
