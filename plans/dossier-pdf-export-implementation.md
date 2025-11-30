# Dossier PDF Export Implementation Plan

**Created**: 2025-11-30
**Status**: Planning Phase
**Priority**: Medium (Architecture Improvement)
**Effort**: 5-6 hours

---

## Executive Summary

This plan removes local filesystem dossier storage and replaces it with on-demand PDF export via API endpoint. This improves the system's stateless architecture, reduces disk usage on VPS, and ensures PDFs always reflect current database state.

**Current Problem**:
- System stores dossier files locally at `./applications/<company>/<role>/`
- Creates file management overhead and disk space issues
- Files can get out of sync with database
- Harder to maintain and scale

**Solution**:
- Add "Export to PDF" button on job detail page
- Generate PDF on-demand via `GET /api/jobs/{job_id}/export-pdf` endpoint
- Stream PDF to browser (not stored on disk)
- Remove local file storage from Layer 7

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│ Job Detail Page (Frontend)                       │
│ ┌──────────────────────────────────────────────┐ │
│ │ Export to PDF Button                         │ │
│ └──────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────┘
                 │
                 │ GET /api/jobs/{job_id}/export-pdf
                 ▼
┌─────────────────────────────────────────────────┐
│ Frontend API (flask app.py)                      │
│ ┌──────────────────────────────────────────────┐ │
│ │ 1. Fetch JobState from MongoDB               │ │
│ │ 2. Build HTML dossier from state            │ │
│ │ 3. POST to pdf-service /render-pdf           │ │
│ │ 4. Stream response as PDF download           │ │
│ └──────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────┘
                 │
                 │ POST /render-pdf (HTML → PDF)
                 ▼
┌─────────────────────────────────────────────────┐
│ PDF Service (Docker container)                   │
│ ┌──────────────────────────────────────────────┐ │
│ │ 1. Receive HTML + CSS                        │ │
│ │ 2. Use Playwright/Chromium to render PDF     │ │
│ │ 3. Return PDF binary                         │ │
│ └──────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────┘
                 │
                 │ PDF binary
                 ▼
┌─────────────────────────────────────────────────┐
│ Browser Download                                 │
│ File: dossier-{company}-{role}.pdf              │
└─────────────────────────────────────────────────┘
```

---

## PDF Content Structure

The exported PDF will include all job detail information in a professional, readable format:

```
┌─────────────────────────────────────────────────┐
│ JOB DOSSIER                                     │
│ Generated: 2025-11-30 14:30:45 UTC              │
├─────────────────────────────────────────────────┤
│ COMPANY INFORMATION                             │
│ • Name: Acme Corp                               │
│ • Industry: SaaS / Cloud                        │
│ • Location: San Francisco, CA                   │
│ • Size: 200-500 employees                       │
│ • Website: https://acme.com                     │
├─────────────────────────────────────────────────┤
│ ROLE DETAILS                                    │
│ • Title: Senior Engineering Manager             │
│ • Department: Engineering                       │
│ • Level: Manager / Senior                       │
│ • Type: Full-time                               │
│ • Salary: $200k-250k + equity                   │
├─────────────────────────────────────────────────┤
│ JOB DESCRIPTION                                 │
│ [Full job description text...]                  │
├─────────────────────────────────────────────────┤
│ PAIN POINTS IDENTIFIED (4 Dimensions)           │
│ • Team Scaling: Need to grow from 12→25        │
│ • Tech Debt: Migrate from monolith              │
│ • Hiring Challenge: Hard to find IC talent      │
│ • Culture: Remote team coordination             │
├─────────────────────────────────────────────────┤
│ FIT ANALYSIS                                    │
│ • Overall Score: 8.2/10                         │
│ • Strengths: Deep IC background, built teams    │
│ • Gaps: No SaaS experience (managed services)   │
├─────────────────────────────────────────────────┤
│ PRIMARY CONTACTS                                │
│ • CEO: John Smith - LinkedIn: /in/jsmith       │
│ • VP Eng: Sarah Chen - LinkedIn: /in/schen     │
├─────────────────────────────────────────────────┤
│ SECONDARY CONTACTS                              │
│ • Senior Eng Mgr (current): Mike Johnson        │
│ • HR Lead: Lisa Park - LinkedIn: /in/lpark     │
├─────────────────────────────────────────────────┤
│ GENERATED CV EXCERPT                            │
│ [CV preview or "See attached CV: cv.pdf"]       │
├─────────────────────────────────────────────────┤
│ OUTREACH MESSAGE                                │
│ [LinkedIn message draft or email template]      │
├─────────────────────────────────────────────────┤
│ APPLICATION FORM FIELDS (if available)          │
│ • Cover letter: [Required]                      │
│ • Video intro: [Optional, 30 sec max]           │
│ • Take-home test: [Optional]                    │
└─────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Backend PDF Export Endpoint (2-3 hours)

#### Step 1.1: Create PDF Export Helper (`src/api/pdf_export.py`)

**File**: `/Users/ala0001t/pers/projects/job-search/src/api/pdf_export.py`

```python
"""
PDF export functionality for job dossiers.
Builds structured HTML from JobState and renders to PDF via pdf-service.
"""

from typing import Dict, Optional
from src.common.state import JobState
from src.common.config import Config

class DossierPDFExporter:
    """Generate PDF dossiers from JobState."""

    def __init__(self, pdf_service_url: str = None):
        self.pdf_service_url = pdf_service_url or Config.PDF_SERVICE_URL

    def build_dossier_html(self, state: JobState) -> str:
        """
        Build comprehensive HTML dossier from JobState.

        Args:
            state: Complete JobState with all pipeline outputs

        Returns:
            HTML string ready for PDF rendering
        """
        # Extract sections
        sections = [
            self._build_header(state),
            self._build_company_section(state),
            self._build_role_section(state),
            self._build_job_description_section(state),
            self._build_pain_points_section(state),
            self._build_fit_analysis_section(state),
            self._build_contacts_section(state),
            self._build_cv_section(state),
            self._build_outreach_section(state),
            self._build_form_fields_section(state),
        ]

        body = "\n".join(filter(None, sections))
        return self._wrap_with_html(body)

    def _build_header(self, state: JobState) -> str:
        """Build header with generation timestamp."""
        # Implementation details
        pass

    def _build_company_section(self, state: JobState) -> str:
        """Build company information section."""
        # Implementation details
        pass

    # Additional _build_*_section methods...

    def _wrap_with_html(self, body: str) -> str:
        """Wrap content in HTML document with PDF styling."""
        # Implementation details
        pass

    async def export_to_pdf(self, state: JobState) -> bytes:
        """
        Export JobState as PDF via pdf-service.

        Args:
            state: JobState with all outputs

        Returns:
            PDF binary content
        """
        html = self.build_dossier_html(state)

        # POST to pdf-service /render-pdf endpoint
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.pdf_service_url}/render-pdf",
                json={"html": html}
            ) as response:
                if response.status != 200:
                    raise Exception(f"PDF service error: {response.status}")
                return await response.read()
```

**Key Considerations**:
- Use existing JobState TypedDict for type safety
- HTML should be self-contained (inline CSS, embedded fonts)
- Match Tailwind design system for professional appearance
- Test with various data scenarios (missing fields, long content)

#### Step 1.2: Add Flask API Endpoint (`frontend/app.py`)

**Route**: `GET /api/jobs/{job_id}/export-pdf`

```python
@app.route('/api/jobs/<job_id>/export-pdf', methods=['GET'])
@require_auth()
def export_dossier_pdf(job_id):
    """Export job dossier as PDF for download."""
    try:
        # 1. Fetch JobState from MongoDB (jobs collection, level-2)
        job_state = db.jobs.find_one({"_id": ObjectId(job_id)})
        if not job_state:
            return {"error": "Job not found"}, 404

        # 2. Generate PDF
        exporter = DossierPDFExporter()
        pdf_bytes = asyncio.run(exporter.export_to_pdf(job_state))

        # 3. Return as downloadable PDF
        company_slug = slugify(job_state.get('company', 'job'))
        role_slug = slugify(job_state.get('title', 'dossier'))
        filename = f"dossier-{company_slug}-{role_slug}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        return {"error": "PDF generation failed"}, 500
```

**Error Handling**:
- Job not found (404)
- Missing required JobState fields (400)
- PDF service timeout (503)
- Large content size (413)

---

### Phase 2: Frontend UI Button (1 hour)

#### Step 2.1: Add Export Button to Job Detail Page

**File**: `frontend/templates/job_detail.html`

Location: Near existing "Export CV to PDF" and "Export Page PDF" buttons (around line 1040-1050)

```html
<!-- Dossier PDF Export Button (NEW) -->
<button id="export-dossier-pdf-btn"
        onclick="exportDossierPDF()"
        class="btn btn-primary gap-2"
        title="Export complete job dossier as PDF">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
    <span id="export-dossier-text">Export Dossier</span>
</button>
```

#### Step 2.2: Add JavaScript Handler with "Save As" Dialog Support

**File**: `frontend/static/js/pdf-export.js` (NEW - Reusable utility)

```javascript
/**
 * Export PDF with browser "Save As" dialog support
 * Uses File System Access API (Chrome 86+) with fallback to legacy download
 *
 * @param {string} apiUrl - URL to fetch PDF from
 * @param {string} suggestedFilename - Filename to suggest in save dialog (e.g., "dossier-company.pdf")
 */
async function exportPDFWithDialog(apiUrl, suggestedFilename) {
    try {
        // Fetch PDF from API
        const response = await fetch(apiUrl);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const blob = await response.blob();

        // Try File System Access API first (modern browsers - Chrome, Edge, Opera)
        if ('showSaveFilePicker' in window) {
            try {
                const handle = await window.showSaveFilePicker({
                    suggestedName: suggestedFilename,
                    types: [{
                        description: 'PDF Document',
                        accept: {'application/pdf': ['.pdf']},
                    }],
                });

                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();

                return { success: true, method: 'file_system_api' };
            } catch (err) {
                // User cancelled or permission denied - try fallback
                if (err.name === 'AbortError') {
                    console.log('File save cancelled by user');
                    return { success: false, cancelled: true };
                }
                // Other error - fall through to legacy method
                console.warn('File System Access API failed, using legacy download:', err);
            }
        }

        // Fallback: Legacy download (all browsers)
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = suggestedFilename;
        document.body.appendChild(a);
        a.click();

        // Cleanup
        setTimeout(() => {
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        }, 100);

        return { success: true, method: 'legacy_download' };
    } catch (error) {
        console.error('PDF export error:', error);
        throw error;
    }
}

// Export for use in templates
window.exportPDFWithDialog = exportPDFWithDialog;
```

**File**: `frontend/templates/job_detail.html` (updated script section)

```javascript
async function exportDossierPDF() {
    const btn = document.getElementById('export-dossier-pdf-btn');
    const textEl = document.getElementById('export-dossier-text');
    const originalText = textEl.textContent;
    const companyName = document.getElementById('company-name')?.textContent || 'Company';
    const roleTitle = document.getElementById('role-title')?.textContent || 'Role';

    try {
        btn.disabled = true;
        textEl.textContent = 'Generating...';

        // Generate filename from company and role
        const slugify = (str) => str
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '');

        const filename = `dossier-${slugify(companyName)}-${slugify(roleTitle)}.pdf`;

        // Use the File System Access API with fallback
        const result = await window.exportPDFWithDialog(
            `/api/jobs/${jobId}/export-pdf`,
            filename
        );

        if (result.cancelled) {
            showToast('PDF export cancelled', 'info');
        } else if (result.success) {
            const method = result.method === 'file_system_api'
                ? 'with save dialog'
                : 'to downloads folder';
            showToast(`Dossier exported successfully ${method}`, 'success');
        }
    } catch (error) {
        console.error('Dossier PDF export failed:', error);
        showToast(error.message || 'Dossier export failed', 'error');
    } finally {
        btn.disabled = false;
        textEl.textContent = originalText;
    }
}

window.exportDossierPDF = exportDossierPDF;
```

**UX Considerations**:
- Disable button during generation
- Show "Generating..." state
- Trigger "Save As" dialog (modern browsers) or auto-download (fallback)
- User can choose save location and filename (if supported)
- Display success/error/cancelled toast notifications
- Auto-filename with company + role slugs
- Handle network errors gracefully
- Support graceful degradation for older browsers

---

### Phase 3: Remove Local Dossier Storage (1 hour)

#### Step 3.1: Identify Code to Remove

**File**: `src/layer7/output_publisher.py` (lines 185-230)

Current code writes files to local disk:
```python
# Line 191-192: Create directory
local_dir = Path('./applications') / company_safe / role_safe
local_dir.mkdir(parents=True, exist_ok=True)

# Line 200-201: Write dossier
with open(dossier_path, 'w', encoding='utf-8') as f:
    f.write(dossier_content)

# Line 208-209: Write cover letter
with open(cover_letter_path, 'w', encoding='utf-8') as f:
    f.write(state['cover_letter'])

# Line 216-217: Write fallback cover letters
with open(fallback_path, 'w', encoding='utf-8') as f:
    f.write("\n\n---\n\n".join(state['fallback_cover_letters']))

# Line 225-226: Write contacts
with open(contacts_path, 'w', encoding='utf-8') as f:
    f.write(contacts_content)
```

#### Step 3.2: Removal Strategy

**Option A (Complete Removal)**: Remove all file writing, keep only database updates
- Pro: Clean, simple
- Con: No local files for debugging/fallback

**Option B (Phase Removal)**: Add config flag `SAVE_LOCAL_DOSSIER=false`
- Pro: Backward compatible during transition
- Con: Technical debt if not cleaned up

**Recommendation**: Use **Option A** with logging
- Remove local file writes entirely
- Add debug logging of dossier content to stdout (for pipeline traces)
- Keep MongoDB as single source of truth

#### Step 3.3: Update Docker Compose

**File**: `docker-compose.runner.yml`

Remove volume mount:
```yaml
# REMOVE THIS:
volumes:
  # Pipeline artifacts
  - ./applications:/app/applications
```

This volume was only used for storing dossier files.

---

### Phase 4: Testing (1 hour)

#### Step 4.1: Unit Tests for PDF Export

**File**: `tests/unit/test_dossier_pdf_export.py`

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.api.pdf_export import DossierPDFExporter

class TestDossierPDFExporter:

    @pytest.fixture
    def exporter(self):
        return DossierPDFExporter(pdf_service_url="http://mock:8001")

    @pytest.fixture
    def sample_job_state(self):
        return {
            "job_id": "123",
            "company": "Acme Corp",
            "title": "Senior Engineer",
            "job_description": "We are looking for...",
            "pain_points": ["Team scaling", "Tech debt"],
            "fit_score": 8.2,
            "primary_contacts": [...],
            "secondary_contacts": [...],
            "cover_letter": "Dear hiring manager...",
            "cv_path": "s3://bucket/cv.pdf",
            # ... other fields
        }

    def test_build_dossier_html_includes_all_sections(self, exporter, sample_job_state):
        """Verify HTML includes all required sections."""
        html = exporter.build_dossier_html(sample_job_state)

        assert "JOB DOSSIER" in html
        assert "Acme Corp" in html
        assert "Senior Engineer" in html
        assert "Team scaling" in html
        assert "8.2" in html
        assert "<html" in html
        assert "</html>" in html

    def test_build_dossier_html_handles_missing_fields(self, exporter):
        """Verify graceful handling of missing fields."""
        minimal_state = {
            "job_id": "123",
            "company": "Acme",
            "title": "Engineer",
            "job_description": "Job desc",
        }

        html = exporter.build_dossier_html(minimal_state)
        # Should not raise, should have placeholders
        assert "Acme" in html

    @pytest.mark.asyncio
    async def test_export_to_pdf_calls_pdf_service(self, exporter, sample_job_state):
        """Verify PDF service is called correctly."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(return_value=b"PDF_BINARY_DATA")
            mock_post.return_value.__aenter__.return_value = mock_response

            pdf_bytes = await exporter.export_to_pdf(sample_job_state)

            assert pdf_bytes == b"PDF_BINARY_DATA"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_to_pdf_handles_service_error(self, exporter, sample_job_state):
        """Verify error handling when pdf-service fails."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_post.return_value.__aenter__.return_value = mock_response

            with pytest.raises(Exception, match="PDF service error"):
                await exporter.export_to_pdf(sample_job_state)
```

#### Step 4.2: Frontend Integration Test

Test the full flow: Click button → Fetch → Download

```python
def test_export_dossier_pdf_endpoint(client, sample_job_in_db):
    """Test GET /api/jobs/{id}/export-pdf endpoint."""
    job_id = sample_job_in_db["_id"]

    response = client.get(f"/api/jobs/{job_id}/export-pdf")

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert b"PDF" in response.data or len(response.data) > 1000
    assert "Content-Disposition" in response.headers
    assert "dossier-" in response.headers["Content-Disposition"]
```

#### Step 4.3: Manual Testing Checklist

- [ ] Click "Export Dossier" button on job detail page
- [ ] Verify PDF downloads with correct filename
- [ ] Verify all sections present in PDF (company, role, pain points, fit, contacts, etc.)
- [ ] Verify PDF renders correctly (text selectable, images visible)
- [ ] Test with job missing optional fields (CV, contacts, etc.)
- [ ] Test error handling (click button while offline)
- [ ] Verify no local files created in `./applications/` directory
- [ ] Check pdf-service logs for errors

---

## File Changes Summary

### Files to Modify

1. **`frontend/app.py`**
   - Add `/api/jobs/{job_id}/export-pdf` route
   - Import DossierPDFExporter
   - Lines: ~50 new

2. **`frontend/templates/job_detail.html`**
   - Add "Export Dossier" button (near line 1040)
   - Add `exportDossierPDF()` JavaScript function (updated with Save As dialog support)
   - Lines: ~40 new
   - Include script reference to pdf-export.js utility

3. **`frontend/templates/cv_editor.html`** (if CV export exists)
   - Update CV export button handler to use `exportPDFWithDialog()`
   - Lines: ~5 modified

4. **`src/layer7/output_publisher.py`**
   - Remove lines 191-226 (file writing code)
   - Remove import: `from pathlib import Path`
   - Lines: ~40 to remove
   - Keep: Database writes, Drive uploads, Sheets updates

5. **`docker-compose.runner.yml`**
   - Remove `./applications:/app/applications` volume mount
   - Lines: ~2 to remove

### Files to Create

1. **`src/api/pdf_export.py`** (NEW)
   - DossierPDFExporter class
   - HTML builder methods
   - PDF service integration
   - Lines: ~300

2. **`frontend/static/js/pdf-export.js`** (NEW - UX Enhancement)
   - Reusable PDF export utility with File System Access API support
   - Export function with Save As dialog (Chrome/Edge/Opera) + fallback (all browsers)
   - Lines: ~70

3. **`tests/unit/test_dossier_pdf_export.py`** (NEW)
   - PDF export endpoint tests
   - HTML generation tests
   - Error handling tests
   - Lines: ~100

### No Changes Needed

- `src/common/state.py` - JobState already has all needed fields
- `src/common/config.py` - PDF_SERVICE_URL already configured
- MongoDB - No schema changes
- `.env.example` - No new env vars needed

---

## Dependencies & Considerations

### Required Packages

- `aiohttp` - Async HTTP client (for pdf-service calls)
- Existing: FastAPI, Playwright (already in pdf-service)

### Performance Notes

- PDF generation: 2-5 seconds (depends on content size)
- HTML building: <100ms
- Network round-trip: <500ms
- Total expected: 2-6 seconds per export

### Scalability

- pdf-service already handles concurrency (MAX_CONCURRENT_PDFS=5)
- Frontend request queuing: Consider rate limiting (1 PDF every 3 seconds)
- No disk I/O on main service = better response times

### Deployment Impact

- **Before**: dossier files accumulate in `./applications/` (grows unbounded)
- **After**: Stateless, no disk accumulation, cleaner VPS

---

## Risk Mitigation

### Risk 1: Large JobState → PDF timeout
**Mitigation**: Limit content size per section (max 10,000 chars)
- Test with real job states
- Add timeout handling (5-second max)
- Show user-friendly error message

### Risk 2: PDF Service unavailable
**Mitigation**: Health check endpoint
- Verify pdf-service health before export
- Show error if service unreachable
- Add fallback: "Unable to generate PDF, try again later"

### Risk 3: Breaking change (users expect files)
**Mitigation**: Clear communication
- Document removal in release notes
- Provide 2-week notice before removal
- Offer alternative: "Export to PDF" button (this feature)

### Risk 4: JobState missing required fields
**Mitigation**: Defensive HTML building
- Check field existence before rendering
- Use "N/A" or "Not available" for missing data
- Log warnings for debugging

---

## Success Criteria

- [ ] All unit tests pass (>90% coverage of pdf_export.py)
- [ ] PDF exports successfully from job detail page
- [ ] PDF includes all 10 sections of dossier
- [ ] PDF renders correctly (text selectable, formatting intact)
- [ ] No local files created in `./applications/`
- [ ] Frontend button has proper error handling
- [ ] Performance: PDF export completes in <6 seconds
- [ ] pdf-service logs show successful /render-pdf calls
- [ ] Code review approved

---

## Timeline

| Phase | Task | Duration | Owner |
|-------|------|----------|-------|
| 1 | Create PDF export helper | 1 hour | Backend |
| 1 | Add Flask endpoint | 1 hour | Backend |
| 1 | Test endpoint | 1 hour | QA |
| 2 | Add frontend button | 0.5 hour | Frontend |
| 2 | JavaScript handler (basic) | 0.5 hour | Frontend |
| 2a | Create pdf-export.js utility (Save As dialog) | 1 hour | Frontend |
| 2a | Update button handlers to use new utility | 0.5 hour | Frontend |
| 3 | Remove local storage | 1 hour | Backend |
| 4 | Unit tests | 1 hour | QA |
| 4 | Browser compatibility testing | 1 hour | QA |
| 4 | Manual testing | 1 hour | QA |
| **Total** | | **9 hours** | |

**Note**: If implementing UX feature #8a (Save As dialog) in parallel with Phase 2, add 1.5-2 hours to timeline. If deferring UX feature, base implementation is 6.5 hours.

---

## References

- **Existing PDF Service**: `pdf_service/app.py` (endpoints, error handling)
- **Current Dossier Storage**: `src/layer7/output_publisher.py` (lines 185-230)
- **Frontend PDF Buttons**: `frontend/templates/job_detail.html` (patterns to follow)
- **PDF Rendering Tests**: `tests/unit/test_pdf_service.py` (test patterns)

---

## Next Steps

1. **Approval**: Get sign-off on this plan
2. **Detailed Design**: Create HTML template mockup with CSS
3. **Implementation**: Follow phases 1-4 above
4. **Code Review**: Ensure error handling, logging, security
5. **Testing**: Full manual testing across browsers
6. **Deployment**: Include in next release with removal notes
7. **Monitoring**: Track pdf-service metrics for export usage

---

## Questions & Decisions

**Q1: Should we keep a fallback/archive option?**
- A: No, cleanly transition to PDF-only. Database has all data for audit.

**Q2: Should PDF include generated CV content?**
- A: Yes, as a link or preview. CV is critical for application tracking.

**Q3: How do we handle very large JobStates (edge case)?**
- A: Limit HTML size, truncate long sections, add warning to user.

**Q4: Should we version the PDF format for future changes?**
- A: Not needed now, but easy to add if dossier structure evolves.

**Q5: Should we support scheduled/bulk exports?**
- A: Out of scope for this phase, consider for v2 if needed.
