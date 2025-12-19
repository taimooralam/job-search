# Bug Report: Export PDF Button Not Working on Job Detail Page

**Reported**: 2025-11-28
**Severity**: High (Core Feature)
**Status**: Needs Investigation & Fix
**Assigned to**: frontend-developer or architecture-debugger

---

## Issue Summary

The "Export PDF" button on the job detail page is not functioning. Users cannot export a PDF from the main detail page view; the only working export option is the "Export PDF" button in the CV editor side panel.

### Expected Behavior
- User can export CV as PDF from job detail page
- Button should download CV as PDF with filename: `CV_<Company>_<Title>.pdf`
- Button should show loading state during PDF generation
- Button should display success/error toast notification

### Actual Behavior
- "Export PDF" button on detail page does not respond to clicks
- No PDF downloads
- No error message or visual feedback
- CV export button in side panel DOES work correctly

### Workaround
Users can currently:
1. Click "Edit CV" to open side panel
2. Click "Export PDF" in editor toolbar (works correctly)
3. Download PDF from there

But they cannot export directly from detail page without opening the editor.

---

## Impact Assessment

**Severity**: HIGH

**Users Affected**:
- All users attempting to export CV from detail page view
- Impacts workflow efficiency (requires extra click to open editor)

**Business Impact**:
- Incomplete feature (export should work from main view)
- Poor user experience (confusing why one button works, other doesn't)
- Suggests buggy implementation

**Timeline Impact**:
- Blocks Phase 5 (Polish) feature refinement
- Should be fixed before production release

---

## Investigation Checklist

### 1. Button Existence
- [ ] Does the button exist in `frontend/templates/job_detail.html`?
- [ ] Button HTML: `<button id="...">Export PDF</button>`
- [ ] Button visible in browser (DevTools > Elements)?
- [ ] Button CSS not hiding it (check `display: none`, `opacity: 0`, etc.)

### 2. Click Handler Attachment
- [ ] Is click event handler attached to button?
- [ ] Check browser DevTools > Elements > Event Listeners on button
- [ ] JavaScript function exists: `exportCVToPDF()` or similar?
- [ ] Click handler properly bound in DOM ready event?

### 3. API Endpoint
- [ ] POST endpoint exists: `/api/jobs/{id}/cv-editor/pdf`?
- [ ] Frontend code calling correct URL?
- [ ] Request body properly formatted (TipTap JSON)?
- [ ] Request headers correct (Content-Type, auth)?

### 4. API Response
- [ ] Does endpoint return binary PDF or error?
- [ ] Response status code: 200, 400, 500, 503?
- [ ] Response headers: `Content-Type: application/pdf`?
- [ ] Response body: Valid PDF or error JSON?

### 5. Network Monitoring
- [ ] Use browser DevTools > Network tab
- [ ] Click detail page "Export PDF" button
- [ ] Look for HTTP POST request to `/api/jobs/{id}/cv-editor/pdf`
- [ ] Check request: Headers, body, response status
- [ ] Check response: Headers, body (binary PDF or error JSON?)

### 6. Browser Console
- [ ] Any JavaScript errors in Console?
- [ ] Any network errors or CORS issues?
- [ ] Any warnings about missing functions?
- [ ] Look for exception stack traces

### 7. Page Source Comparison
- [ ] Compare detail page button with editor button
- [ ] Detail page: `<button id="export-pdf-detail">...</button>`
- [ ] Editor panel: `<button id="export-pdf-editor">...</button>`
- [ ] Are they different elements? Different handlers?

### 8. Functional Comparison
- [ ] Editor button works: Triggers PDF download
- [ ] Editor button calls: `exportCVToPDF()`?
- [ ] Detail button calls: Same function or different?
- [ ] What's different between working and broken button?

---

## Root Cause Hypotheses

### Hypothesis 1: Button Missing or Hidden
**Status**: To investigate
- Button not rendered in job_detail.html
- Button exists but hidden by CSS
- Button only rendered for certain conditions (auth, page state)

### Hypothesis 2: Click Handler Not Attached
**Status**: To investigate
- JavaScript file not loaded on detail page
- Event listener not attached (script loads before DOM)
- Function name mismatch (button calls `exportPDF()`, function is `exportCVToPDF()`)

### Hypothesis 3: Wrong Endpoint or Path
**Status**: To investigate
- Button calls different endpoint than editor button
- Wrong job ID in request (passing undefined or null)
- Missing query parameters or request body
- Frontend service URL not configured correctly

### Hypothesis 4: Missing CV Editor State
**Status**: To investigate
- Detail page doesn't have access to TipTap JSON
- Request body empty or missing `cv_editor_state`
- Fallback to legacy markdown CV, which breaks endpoint

### Hypothesis 5: CORS or Authentication Issue
**Status**: To investigate
- Browser CORS policy blocking request
- Missing auth header or expired session
- Runner service not accessible from frontend

### Hypothesis 6: Feature Not Implemented
**Status**: To investigate
- Detail page export never implemented
- Only editor panel button implemented
- Detail page button is UI placeholder with no backend

---

## Investigation Steps

### Step 1: Inspect Button in Browser

```javascript
// In browser console on job detail page
document.getElementById('export-pdf-button')  // Try various IDs
document.querySelector('button[onclick*="pdf"]')
document.querySelector('[data-action="export-pdf"]')

// If found, check properties
let btn = document.querySelector('button');  // Find export button
console.log('Button HTML:', btn?.outerHTML);
console.log('Click listeners:', getEventListeners(btn));  // Chrome only
```

### Step 2: Check Network Request

```
1. Open DevTools (F12)
2. Go to Network tab
3. Click "Export PDF" button on detail page
4. Look for POST request to /api/jobs/{id}/cv-editor/pdf
5. If request missing: Button handler not firing
6. If request fails: Check status code and response
```

### Step 3: Check JavaScript Console

```javascript
// In browser console on detail page
// Try calling export function manually
exportCVToPDF()  // If function exists, may return error

// Check if TipTap editor accessible
window.currentEditor  // Look for editor state
document.querySelector('.ProseMirror')  // Look for TipTap element
```

### Step 4: Review Source Code

```bash
# Check if button exists in template
grep -n "export-pdf" frontend/templates/job_detail.html

# Check if handler attached in JavaScript
grep -n "exportCVToPDF\|export-pdf" frontend/static/js/*.js

# Check if endpoint exists in Flask
grep -n "cv-editor/pdf" frontend/app.py
```

### Step 5: Test with curl

```bash
# Get job ID from MongoDB
MONGO_URI="..."
JOB_ID=$(mongosh "$MONGO_URI" --eval "db.level-2.findOne({}, {_id: 1})._id")

# Get CV editor state
curl http://localhost:5000/api/jobs/$JOB_ID/cv-editor \
  -H "Authorization: Bearer $TOKEN"

# Try to export PDF directly
curl -X POST http://localhost:5000/api/jobs/$JOB_ID/cv-editor/pdf \
  -H "Content-Type: application/json" \
  -d '{
    "version": 1,
    "content": {"type": "doc", "content": []},
    "documentStyles": {"lineHeight": 1.15}
  }' \
  -o test.pdf

# Check if PDF valid
file test.pdf  # Should say "PDF document"
```

---

## Implementation Scenarios

### Scenario A: Button Doesn't Exist

**Evidence**: No `<button>` element with export-pdf ID in HTML

**Fix**:
1. Add button to `frontend/templates/job_detail.html`:
```html
<button
  id="export-pdf-detail"
  class="btn btn-secondary"
  onclick="exportCVToPDFFromDetail()"
>
  Export PDF
</button>
```

2. Add handler in `frontend/static/js/cv-editor.js`:
```javascript
function exportCVToPDFFromDetail() {
  // Same logic as editor export
  const jobId = new URLSearchParams(window.location.search).get('id');
  exportCVToPDF(jobId);
}
```

**Files to Modify**:
- `frontend/templates/job_detail.html`
- `frontend/static/js/cv-editor.js`

**Effort**: 30 minutes

### Scenario B: Button Hidden by CSS

**Evidence**: Button element exists but `display: none`, `visibility: hidden`, or `opacity: 0`

**Fix**:
1. Find CSS hiding the button
2. Remove or update CSS rule
3. Test button visibility

**Files to Modify**:
- `frontend/templates/base.html` or `frontend/static/css/*.css`

**Effort**: 15 minutes

### Scenario C: Click Handler Not Attached

**Evidence**: Button exists, visible, but clicking does nothing

**Fix**:
1. Check if `cv-editor.js` loaded on detail page
2. Verify JavaScript runs on DOM ready
3. Ensure event listener attached to correct element

**Example Fix** (if script not loading):
```html
<!-- Add to job_detail.html -->
<script src="{{ url_for('static', filename='js/cv-editor.js') }}"></script>
```

**Files to Modify**:
- `frontend/templates/job_detail.html`

**Effort**: 15 minutes

### Scenario D: Wrong Endpoint or Missing Data

**Evidence**: Network tab shows 400 or 500 error, or request body incomplete

**Fix**:
1. Verify endpoint path correct: `/api/jobs/{id}/cv-editor/pdf`
2. Ensure TipTap JSON available on detail page
3. Check request body includes all required fields

**Example Issue**:
```javascript
// WRONG - missing cv_editor_state
const body = { version: 1 };

// CORRECT - includes all fields
const body = {
  version: 1,
  content: editor.getJSON().content,
  documentStyles: {...}
};
```

**Files to Modify**:
- `frontend/static/js/cv-editor.js` - Export function
- Possibly `frontend/templates/job_detail.html` - Data passing

**Effort**: 1-2 hours

### Scenario E: CORS or Auth Issue

**Evidence**: Network tab shows CORS error, 401 Unauthorized, or network error

**Fix**:
1. Check CORS headers in runner service response
2. Verify session cookie sent with request
3. Check auth token not expired

**Example Fix**:
```javascript
// Add credentials to fetch request
fetch(url, {
  method: 'POST',
  credentials: 'same-origin',  // Include cookies
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken  // If needed
  }
});
```

**Files to Modify**:
- `frontend/static/js/cv-editor.js`
- Possibly `frontend/app.py` - CORS configuration

**Effort**: 30 minutes

### Scenario F: Feature Not Implemented

**Evidence**: Code review shows detail page export button never implemented

**Fix**:
Implement from scratch (combine Button fix + Handler + Endpoint verification)

**Files to Create/Modify**:
- `frontend/templates/job_detail.html` - Add button
- `frontend/static/js/cv-editor.js` - Add handler
- `frontend/app.py` - Verify endpoint exists
- `tests/frontend/test_cv_editor_pdf.py` - Add test for detail page export

**Effort**: 2-3 hours

---

## Testing Plan

### Unit Tests

```python
# tests/frontend/test_cv_editor_pdf.py
def test_export_pdf_from_detail_page(client, mock_job):
    """Test exporting PDF from detail page button."""
    response = client.post(
        f'/api/jobs/{mock_job["_id"]}/cv-editor/pdf',
        json={
            'version': 1,
            'content': {'type': 'doc', 'content': []},
            'documentStyles': {'lineHeight': 1.15}
        }
    )
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/pdf'
    assert len(response.data) > 0  # PDF data not empty

def test_export_pdf_detail_button_calls_endpoint(client):
    """Test detail page export button calls correct endpoint."""
    # This would require Playwright E2E test
    pass
```

### E2E Tests (Playwright)

```python
# tests/e2e/test_export_pdf_detail_page.py
async def test_export_pdf_from_detail_page():
    """Test exporting PDF from detail page without opening editor."""
    page = await browser.new_page()
    await page.goto('https://job-search.vercel.app/job/123')

    # Wait for page load
    await page.wait_for_selector('button[id*="export"]')

    # Click export button
    async with page.expect_download() as download_info:
        await page.click('#export-pdf-detail')

    # Verify download
    download = await download_info.value
    assert download.filename.endswith('.pdf')

    await page.close()
```

### Manual Testing

1. Navigate to job detail page (any job)
2. Scroll to find "Export PDF" button
3. Click button
4. Verify PDF downloads to Downloads folder
5. Open PDF and verify content matches CV editor content
6. Check filename format: `CV_<Company>_<Title>.pdf`

---

## Success Criteria (Fix)

- [x] Button exists and visible on job detail page
- [x] Button click triggers PDF export request
- [x] PDF downloads to user's computer
- [x] PDF filename correct: `CV_<Company>_<Title>.pdf`
- [x] PDF content matches CV editor content
- [x] No console errors
- [x] Works across browsers (Chrome, Firefox, Safari)
- [x] Unit tests passing
- [x] E2E test passing (if enabled)

---

## Related Documentation

- Phase 4 Implementation: `plans/missing.md` - CV Rich Text Editor Phase 4
- Current Architecture: `plans/architecture.md` - PDF Generation Architecture section
- Frontend Implementation: `frontend/templates/job_detail.html`
- Export Handler: `frontend/static/js/cv-editor.js` - `exportCVToPDF()` function

---

## Appendix: File Locations Reference

### Frontend Templates
- Main detail page: `frontend/templates/job_detail.html`
- Base template: `frontend/templates/base.html`
- CSS: `frontend/templates/` (inline or external)

### JavaScript
- CV editor logic: `frontend/static/js/cv-editor.js`
- Utility functions: `frontend/static/js/*.js`

### Backend (Flask)
- PDF proxy endpoint: `frontend/app.py` - lines 870-939
- CV editor endpoints: `frontend/app.py` - `@app.route('/api/jobs/<job_id>/cv-editor')`

### Tests
- Frontend tests: `tests/frontend/test_*.py`
- E2E tests: `tests/e2e/test_cv_editor_e2e.py`

### Runner Service
- PDF generation: `runner_service/app.py` - lines 368-498
- PDF helpers: `runner_service/pdf_helpers.py`
