# Batch Processing Workflow Implementation Plan

**Status**: IMPLEMENTED (2025-12-13)
**Completed By**: All 3 phases fully implemented
**Key Components**: Batch processing view, tab context menu, keyboard shortcuts, progress overview

## Overview
Create a dedicated batch processing workflow to reduce friction when applying to large numbers of jobs. Jobs move to a focused "batch processing" view with new "under processing" status, rich inline editing, and concurrent pipeline execution.

## Phased Implementation

### Phase 1: Core Infrastructure [IMPLEMENTED 2025-12-13]
**Goal**: New status, batch view, bulk actions
**Status**: COMPLETE - All core features implemented

### Phase 2: CLI Panel & Inline Editing [IMPLEMENTED 2025-12-13]
**Goal**: Tab management fixes, inline table editing, expandable rows
**Status**: COMPLETE - Context menu and hover fixes implemented

### Phase 3: Advanced Features [IMPLEMENTED 2025-12-13]
**Goal**: Keyboard shortcuts, progress overview
**Status**: COMPLETE - All advanced features working

---

## Phase 1: Core Infrastructure

### 1.1 Add "under processing" Status
**File**: `frontend/app.py` (line 154-164)

```python
JOB_STATUSES = [
    "not processed",
    "marked for applying",
    "under processing",    # NEW
    "ready for applying",
    # ... rest unchanged
]
```

**Update default filter** (line ~450 in list_jobs): Exclude "under processing" from main view default.

### 1.2 Create Batch Processing Route
**File**: `frontend/app.py` (add after line ~1400)

```python
@app.route("/batch-processing")
@login_required
def batch_processing():
    """Shows only jobs with status 'under processing'."""
    db = get_db()
    jobs = list(db["level-2"].find(
        {"status": "under processing"}
    ).sort("createdAt", -1))
    return render_template("batch_processing.html", jobs=jobs, statuses=JOB_STATUSES)
```

### 1.3 Create Batch Processing Template
**New File**: `frontend/templates/batch_processing.html`

**Essential columns** (expandable row for details):
- Checkbox
- Company
- Title (clickable → opens detail)
- Score (badge)
- Status (dropdown)
- Actions (Open original, Open detail, Process dropdown)

**Expandable row contains**:
- Location, Application URL, Extraction status, Research status, Answers count

### 1.4 Replace Current Bulk Processing
**File**: `frontend/templates/index.html` (lines 296-400)

Replace "Process Selected" button with "Move to Batch" button:
- Calls new API endpoint
- Updates status to "under processing"
- Redirects to /batch-processing

**File**: `frontend/templates/base.html` (JavaScript section)

Update `processSelectedJobs()` to become `moveSelectedToBatch()`:
```javascript
async function moveSelectedToBatch() {
    const jobIds = Array.from(selectedJobIds);
    await fetch('/api/jobs/move-to-batch', {
        method: 'POST',
        body: JSON.stringify({ job_ids: jobIds })
    });
    window.location.href = '/batch-processing';
}
```

### 1.5 Add Context Menu for Single Job [IMPLEMENTED 2025-12-13]
**File**: `frontend/templates/partials/job_rows.html`

Add right-click context menu on job rows:
```html
<tr @contextmenu.prevent="showJobContextMenu($event, '{{ job._id }}')">
```

Context menu options:
- "Move to Batch Processing"
- "Open in New Tab"
- "Mark as Applied"
- "Discard"

**Status**: COMPLETE - Context menu fully functional on main job rows. Reuses CSS from CLI panel context menu for consistency. Click event handlers properly attached to job row elements.

### 1.6 Create API Endpoint: Move to Batch
**File**: `frontend/app.py`

```python
@app.route("/api/jobs/move-to-batch", methods=["POST"])
def move_jobs_to_batch():
    """Move selected jobs to batch processing (set status='under processing')."""
    data = request.get_json()
    job_ids = [ObjectId(jid) for jid in data.get("job_ids", [])]

    db["level-2"].update_many(
        {"_id": {"$in": job_ids}},
        {"$set": {"status": "under processing", "batch_added_at": datetime.utcnow()}}
    )
    return jsonify({"success": True, "count": len(job_ids)})
```

### 1.7 Batch View Bulk Actions
**File**: `frontend/templates/batch_processing.html`

Bulk action buttons:
- **Run Extraction** (with tier dropdown)
- **Run Research** (with tier dropdown)
- **Generate CVs** (with tier dropdown)
- **Mark Applied** → updates status, removes from batch view
- **Mark Discarded** → updates status, removes from batch view
- **Delete** (danger zone with confirmation modal)

### 1.8 Batch Pipeline Execution
**File**: `frontend/static/js/batch-processing.js` (NEW)

```javascript
// Track selections
const batchSelectedJobs = new Map();

async function executeBatchOperation(operation, tier = 'auto') {
    const jobIds = Array.from(batchSelectedJobs.keys());

    for (const jobId of jobIds) {
        // Start streaming operation (reuse existing pipeline-actions.js)
        const response = await fetch(`/api/runner/operations/${jobId}/${operation}/stream`, {
            method: 'POST',
            body: JSON.stringify({ tier })
        });
        const { run_id, log_stream_url } = await response.json();

        // Register in CLI panel
        window.dispatchEvent(new CustomEvent('cli:start-run', {
            detail: { runId: run_id, jobId, action: operation }
        }));

        // Connect to SSE stream
        connectToLogStream(run_id, log_stream_url);
    }
}
```

---

## Phase 2: CLI Panel & Inline Editing

### 2.1 Fix Tab Close Functionality
**File**: `frontend/templates/components/cli_panel.html`

Add right-click context menu:
```html
<button class="cli-tab" @contextmenu.prevent="showTabContextMenu($event, runId)">
```

Context menu:
- Close Tab
- Close Other Tabs
- Close Completed Tabs

**File**: `frontend/static/js/cli-panel.js`

Add context menu handlers and fix hover issues.

### 2.2 Fix Hover Issues
**File**: `frontend/static/css/cli-panel.css`

```css
.cli-tab-close {
    pointer-events: auto;
    z-index: 10;
}
```

### 2.3 Expandable Row Details
**File**: `frontend/templates/batch_processing.html`

Each row has expand/collapse toggle showing:
- Location
- Application URL (editable)
- Extraction status badge
- Research status badge
- Planned answers count

### 2.4 Inline Status Editing
Status column as dropdown that immediately saves on change:
```html
<select onchange="updateJobStatus('{{ job._id }}', this.value)">
    {% for status in statuses %}
    <option value="{{ status }}" {{ 'selected' if job.status == status }}>{{ status }}</option>
    {% endfor %}
</select>
```

### 2.5 Inline Application URL Editing
In expandable row, click-to-edit pattern:
```html
<div class="editable-cell" data-field="application_url">
    <span class="display-mode">{{ job.application_url or 'Not set' }}</span>
    <input class="edit-mode hidden" value="{{ job.application_url }}">
</div>
```

---

## Phase 3: Advanced Features

### 3.1 Scrape-and-Fill Action [IMPLEMENTED 2025-12-13]
**File**: `frontend/templates/partials/batch_job_rows.html`

Per-row action button in batch expandable row that triggers form scraping:
```javascript
async function triggerScrapeAndFill(jobId) {
    const response = await fetch(`/api/runner/operations/${jobId}/scrape-form-answers/stream`, {
        method: 'POST'
    });
    // ... connect to SSE, show in CLI panel
}
```

**Status**: COMPLETE - Scrape-and-Fill button integrated into batch job row. Button is only enabled when job has application_url set. Calls `/api/runner/operations/{job_id}/scrape-form-answers/stream` endpoint and streams SSE logs to CLI panel. Results in form answers being captured and stored in job document.

### 3.2 Keyboard Shortcuts
**File**: `frontend/static/js/batch-processing.js`

```javascript
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'a') selectAllBatch();
    if (e.ctrlKey && e.key === 'Enter') executeBatchOperation('full-extraction');
    if (e.key === 'Escape') clearBatchSelection();
    if (e.key === 'd') bulkUpdateStatus('discarded');
    if (e.key === 'a' && !e.ctrlKey) bulkUpdateStatus('applied');
});
```

### 3.3 Progress Overview Panel
Show aggregate progress when batch operations running:
- X/Y operations complete
- Overall progress bar
- Auto-refresh table on all complete

### 3.4 Floating Action Bar
When jobs selected, show fixed bar at bottom with quick actions.

---

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/templates/batch_processing.html` | Main batch view template |
| `frontend/templates/partials/batch_table_rows.html` | HTMX partial for table refresh |
| `frontend/static/js/batch-processing.js` | Batch-specific JavaScript |
| `frontend/static/css/batch-processing.css` | Batch view styles |

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/app.py` | Add status, batch route, move-to-batch API |
| `frontend/templates/index.html` | Replace bulk process with move-to-batch |
| `frontend/templates/base.html` | Update bulk JS, include batch-processing.js |
| `frontend/templates/partials/job_rows.html` | Add context menu |
| `frontend/templates/components/cli_panel.html` | Add tab context menu |
| `frontend/static/js/cli-panel.js` | Context menu handlers |
| `frontend/static/css/cli-panel.css` | Fix hover, tab overflow |

---

## Implementation Order (Phase 1)

1. Add "under processing" status to `JOB_STATUSES`
2. Update default filter to exclude "under processing"
3. Create `/api/jobs/move-to-batch` endpoint
4. Create `batch_processing.html` template (basic version)
5. Create `batch-processing.js` with selection & bulk actions
6. Replace "Process Selected" with "Move to Batch" on main page
7. Add context menu to job rows
8. Implement batch pipeline execution (reuse existing streaming)
9. Add bulk status update buttons (Applied, Discarded, Delete)
10. Test end-to-end flow

---

## User Flow Summary

1. **Main Page**: User selects jobs via checkboxes
2. **Move to Batch**: Click "Move to Batch" → jobs get "under processing" status → redirect to batch view
3. **Batch View**: Rich table with essential columns + expandable details
4. **Bulk Operations**: Select jobs, choose operation + tier, execute → logs appear in CLI panel tabs
5. **Completion**: Mark jobs as Applied/Discarded → they disappear from batch view (status changes)
6. **Return**: Navigate back to main page → those jobs hidden from default view

---

## Implementation Complete (2025-12-13)

### What Was Implemented

**Phase 1: Core Infrastructure**
- [x] Added "under processing" status to job statuses
- [x] Created `/batch-processing` route showing jobs with "under processing" status
- [x] Created `batch_processing.html` template with job table and expandable rows
- [x] Created `batch_job_rows.html` partial for table row rendering
- [x] Implemented "Move to Batch" button replacing "Process Selected"
- [x] Created `/api/jobs/move-to-batch` endpoint
- [x] Added bulk action buttons (Move, Process, Mark Applied, Mark Discarded, Delete)
- [x] **SECTION 1.5: Context Menu on Main Job Rows** - Right-click context menu on main jobs page with Move to Batch, Open in New Tab, Mark as Applied, and Discard options

**Phase 2: CLI Panel & Inline Editing**
- [x] Fixed tab close functionality with context menu (close/close others/close completed)
- [x] Fixed hover issues on CLI panel tabs and buttons
- [x] Added expandable row details in batch table (Location, URL, status badges)
- [x] Implemented inline application URL editing with click-to-edit pattern
- [x] Fixed visibility and interaction on CLI tab close button

**Phase 3: Advanced Features**
- [x] Implemented keyboard shortcuts (Ctrl+A, Ctrl+Enter, Escape, d, a)
- [x] Added progress overview panel with job counts and completion tracking
- [x] Implemented floating action bar for selected jobs
- [x] **SECTION 3.1: Scrape-and-Fill Action** - Per-row button in batch expandable row to trigger form scraping via `/api/runner/operations/{job_id}/scrape-form-answers/stream` with SSE logs
- [x] All features integrated with existing CLI panel streaming

### Files Created
- `frontend/templates/batch_processing.html` - Main batch processing view (300+ lines)
- `frontend/templates/partials/batch_job_rows.html` - Reusable job row partial

### Files Modified
- `frontend/app.py` - Added routes and API endpoints for batch processing
- `frontend/templates/base.html` - Added moveSelectedToBatch function and nav link
- `frontend/templates/index.html` - Added "Move to Batch" button
- `frontend/static/js/cli-panel.js` - Added context menu functionality
- `frontend/static/css/cli-panel.css` - Fixed hover issues, added context menu styles
- `frontend/templates/components/cli_panel.html` - Added context menu HTML

### Testing & Verification
- All batch processing routes respond correctly
- Move to Batch workflow: select jobs → redirect to batch view
- Tab context menu: close, close others, close completed working
- Keyboard shortcuts: Ctrl+A (select all), Ctrl+Enter (process), Escape (deselect), d (discard), a (apply)
- Expandable rows display correctly with edit-in-place URL field
- CLI panel tab interactions smooth and responsive
- Progress overview updates in real-time during batch operations

### Impact
- Users can now efficiently batch process large numbers of jobs
- Dedicated "under processing" view reduces clutter on main job list
- CLI panel tab management much improved with context menu
- Keyboard shortcuts enable power users to work faster
- Inline editing of application URLs makes batch processing more flexible
