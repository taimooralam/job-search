# Job Iframe Viewer Implementation Plan

**Created**: 2025-11-29
**Status**: Phase 1 Complete (2025-11-30)
**Priority**: Low
**Related Requirement**: #11 from missing.md

---

## Status Update (2025-11-30)

### Phase 1: Basic Iframe Viewer ✅ COMPLETE

**Completion Date**: 2025-11-30
**Implementation Location**: `frontend/templates/job_detail.html` (lines 1030-1080)

**Features Delivered**:
- Collapsible iframe viewer section with expand/collapse toggle
- Loading spinner animation while iframe loads
- Error detection and handling for X-Frame-Options blocked sites
- Fallback message with "Open in New Tab" button
- Responsive design with 500px height
- Security sandbox attributes
- Console logging for debugging

---

### Phase 2: PDF Export of Job Posting ✅ COMPLETE

**Completion Date**: 2025-11-30
**Commits**: db1907a7 (PDF service), 030913ae (runner proxy), f3c4e45a (frontend proxy), f6406865 (UI button), 5df4907d (bug fix)

**Architecture**:
- **PDF Service** (`pdf_service/app.py`): New endpoint `/url-to-pdf` for converting URLs to PDF
- **Runner Service** (`runner_service/app.py`): New proxy endpoint `/api/url-to-pdf`
- **Frontend** (`frontend/app.py`): New proxy endpoint `/api/jobs/<id>/export-page-pdf`
- **UI** (`frontend/templates/job_detail.html`): Export PDF button in iframe viewer header

**Features Delivered**:
- Export original job posting as PDF from iframe viewer
- Uses Playwright/Chromium to render URL to PDF (same as CV export)
- Integrated with existing pdf-service architecture
- Full error handling and user feedback via toast notifications
- Filename: `job-posting-<company>.pdf`
- Works end-to-end from frontend through runner to pdf-service
- Graceful fallback if PDF generation fails

**Implementation Details**:
- Job posting URL captured from `job.url` field
- Rendered using same Playwright configuration as CV export
- Internal Docker network communication between runner and pdf-service
- No external API calls (Playwright local Chromium rendering)
- Respects X-Frame-Options blocking (can still export even if iframe blocked)

---

## Problem Statement

Users currently need to open job postings in a separate browser tab to view the original content. This breaks the workflow when comparing the job description with the generated CV/cover letter.

---

## Solution Overview

Add a collapsible iframe viewer that displays the original job posting URL directly within the job detail page. Include a bonus feature to export the iframe content as PDF.

---

## UX Options

### Option A: Collapsible Side Panel (Recommended)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Job Detail Page                                          [👁 View Original] │
├─────────────────────────────────────────┬───────────────────────────┤
│                                         │                            │
│  Job Title: Senior Backend Engineer     │  ┌────────────────────┐   │
│  Company: Atlassian                     │  │  Original Posting  │   │
│  Status: Ready for applying             │  │  [iframe content]  │   │
│                                         │  │                    │   │
│  ─────────────────────────────────────  │  │  ... job details   │   │
│                                         │  │  ... requirements  │   │
│  CV Preview                             │  │  ... benefits      │   │
│  [Generated CV content]                 │  │                    │   │
│                                         │  │  [Export PDF]      │   │
│                                         │  └────────────────────┘   │
│                                         │                            │
└─────────────────────────────────────────┴───────────────────────────┘
```

**Pros**:
- Side-by-side comparison with CV
- Doesn't disrupt main content flow
- Can resize panel width

**Cons**:
- Limited width on smaller screens
- May conflict with CV editor panel

### Option B: Expandable Section

```
┌─────────────────────────────────────────────────────────────────────┐
│ Job Detail Page                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [▼ View Original Job Posting]                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                                                                  │ │
│  │  [iframe: original job URL]                                     │ │
│  │  Height: 500px (expandable)                                     │ │
│  │                                                                  │ │
│  │  [Export PDF] [Open in New Tab]                                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────   │
│                                                                      │
│  CV Preview                                                          │
│  [Generated CV content]                                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Full width for iframe content
- Simple implementation
- Works well on all screen sizes

**Cons**:
- Pushes main content down when expanded
- Not ideal for side-by-side comparison

### Option C: Modal Overlay

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Original Job Posting                               [X Close]  │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │                                                                │  │
│  │  [iframe: original job URL]                                   │  │
│  │  Width: 90vw, Height: 80vh                                    │  │
│  │                                                                │  │
│  │  [Export PDF] [Open in New Tab]                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Maximum viewport for iframe content
- Doesn't affect page layout

**Cons**:
- Can't see CV while viewing job posting
- Requires closing modal to switch context

---

## Recommended: Option B (Expandable Section)

Simple, accessible, and works on all devices. Users can collapse when not needed.

---

## Implementation

### Phase 1: Basic Iframe Viewer (2 hours)

**File**: `frontend/templates/job_detail.html`

```html
<!-- Expandable Job Viewer Section -->
<div class="mb-6">
    <button
        onclick="toggleJobViewer()"
        class="flex items-center gap-2 text-blue-600 hover:text-blue-800"
    >
        <span id="job-viewer-icon">▶</span>
        <span>View Original Job Posting</span>
    </button>

    <div id="job-viewer-container" class="hidden mt-4">
        <div class="border rounded-lg overflow-hidden">
            <div class="bg-gray-100 px-4 py-2 flex justify-between items-center">
                <span class="text-sm text-gray-600">
                    Source: <a href="{{ job.url }}" target="_blank" class="text-blue-600 hover:underline">
                        {{ job.url | truncate(50) }}
                    </a>
                </span>
                <div class="flex gap-2">
                    <button onclick="exportIframePDF()" class="px-3 py-1 text-sm bg-gray-200 hover:bg-gray-300 rounded">
                        Export PDF
                    </button>
                    <button onclick="window.open('{{ job.url }}', '_blank')" class="px-3 py-1 text-sm bg-gray-200 hover:bg-gray-300 rounded">
                        Open in New Tab
                    </button>
                </div>
            </div>
            <iframe
                id="job-iframe"
                src="{{ job.url }}"
                class="w-full h-[500px] border-0"
                sandbox="allow-scripts allow-same-origin"
                loading="lazy"
            ></iframe>
        </div>
    </div>
</div>

<script>
function toggleJobViewer() {
    const container = document.getElementById('job-viewer-container');
    const icon = document.getElementById('job-viewer-icon');

    if (container.classList.contains('hidden')) {
        container.classList.remove('hidden');
        icon.textContent = '▼';
    } else {
        container.classList.add('hidden');
        icon.textContent = '▶';
    }
}
</script>
```

### Phase 2: Security & Error Handling (1 hour)

```javascript
// Handle iframe load errors
document.getElementById('job-iframe').addEventListener('error', function() {
    this.parentElement.innerHTML = `
        <div class="p-4 bg-yellow-50 text-yellow-800">
            <p>Unable to load job posting in iframe.</p>
            <p>Some sites block iframe embedding.</p>
            <a href="{{ job.url }}" target="_blank" class="text-blue-600 hover:underline">
                Open in new tab instead →
            </a>
        </div>
    `;
});

// Handle X-Frame-Options blocked iframes
window.addEventListener('message', function(e) {
    if (e.data.type === 'iframe-blocked') {
        // Show fallback UI
    }
});
```

### Phase 3: PDF Export (Bonus) (2 hours)

**Backend**: `frontend/app.py`

```python
@app.route('/api/jobs/<job_id>/export-page-pdf', methods=['POST'])
def export_page_to_pdf(job_id):
    """Export a URL to PDF using Playwright."""
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL required'}), 400

    # Proxy to runner service (has Playwright)
    runner_url = os.getenv('RUNNER_URL')
    response = requests.post(
        f'{runner_url}/api/render-page-pdf',
        json={'url': url},
        timeout=30
    )

    if response.status_code == 200:
        return Response(
            response.content,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="job-posting.pdf"'}
        )
    else:
        return jsonify({'error': 'PDF generation failed'}), 500
```

**Runner**: `runner_service/app.py`

```python
@app.post('/api/render-page-pdf')
async def render_page_pdf(request: PageRenderRequest):
    """Render a URL to PDF using Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(request.url, wait_until='networkidle')
        pdf_bytes = await page.pdf(format='A4')

        await browser.close()

    return Response(content=pdf_bytes, media_type='application/pdf')
```

**Frontend JS**:

```javascript
async function exportIframePDF() {
    const jobUrl = '{{ job.url }}';
    const button = event.target;
    button.textContent = 'Generating...';
    button.disabled = true;

    try {
        const response = await fetch('/api/jobs/{{ job._id }}/export-page-pdf', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: jobUrl})
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'job-posting.pdf';
            a.click();
            URL.revokeObjectURL(url);
        } else {
            alert('PDF export failed. Try opening in new tab instead.');
        }
    } finally {
        button.textContent = 'Export PDF';
        button.disabled = false;
    }
}
```

---

## Security Considerations

### Iframe Sandbox Attributes

```html
<iframe
    sandbox="allow-scripts allow-same-origin"
    referrerpolicy="no-referrer"
    loading="lazy"
>
```

| Attribute | Purpose |
|-----------|---------|
| `allow-scripts` | Enable JS in iframe (required for most job sites) |
| `allow-same-origin` | Allow cookies/auth (may be needed) |
| `no-referrer` | Don't send referrer header |

### Sites That Block Iframes

Many job boards set `X-Frame-Options: DENY` or `SAMEORIGIN`:
- LinkedIn
- Indeed
- Glassdoor

**Fallback**: Show message with "Open in New Tab" button.

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/templates/job_detail.html` | Add collapsible iframe section |
| `frontend/app.py` | Add PDF export endpoint (optional) |
| `runner_service/app.py` | Add page-to-PDF endpoint (optional) |

---

## Test Cases

1. **Basic Display**: Iframe loads job URL
2. **Toggle**: Expand/collapse works
3. **Blocked Sites**: Fallback UI shown for LinkedIn/Indeed
4. **PDF Export**: Generates downloadable PDF
5. **Mobile**: Responsive layout on small screens

---

## Success Criteria

- [ ] Collapsible iframe viewer works on job detail page
- [ ] Blocked sites show helpful fallback message
- [ ] "Open in New Tab" always works as escape hatch
- [ ] PDF export works (bonus feature)
- [ ] Mobile responsive

---

## Effort Estimate

**Total**: 4-6 hours

- Phase 1 (Basic Viewer): 2 hours
- Phase 2 (Security/Errors): 1 hour
- Phase 3 (PDF Export): 2 hours (bonus)
- Testing: 1 hour

---

## Known Limitations

1. **X-Frame-Options**: Many job boards block iframes
2. **Dynamic Content**: Some sites use JavaScript that may not render in iframe
3. **Authentication**: Logged-in content won't display
4. **Rate Limiting**: Frequent iframe loads may trigger rate limits

**Mitigation**: Always provide "Open in New Tab" as fallback.
