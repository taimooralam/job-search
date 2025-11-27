# Job Intelligence Pipeline - Architecture

**Last Updated**: 2025-11-27 (Phase 4 Complete)

---

## Overview

Python-based LangGraph pipeline that processes job postings from MongoDB to generate hyper-personalized CVs, cover letters, and outreach packages. Uses master CV grounding to prevent hallucination.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SYSTEM ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐         │
│  │ Vercel       │     │ VPS Runner       │     │ MongoDB Atlas    │         │
│  │ (Frontend)   │────►│ (FastAPI)        │────►│                  │         │
│  │ Flask/HTMX   │ SSE │ subprocess exec  │     │ level-2 jobs     │         │
│  └──────────────┘     └────────┬─────────┘     │ company_cache    │         │
│                                │               │ star_records     │         │
│                                ▼               └──────────────────┘         │
│                    ┌───────────────────────┐                                │
│                    │  LangGraph Pipeline   │                                │
│                    │  (src/workflow.py)    │                                │
│                    └───────────────────────┘                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Execution Surfaces

| Surface | Location | Description |
|---------|----------|-------------|
| **CLI** | `scripts/run_pipeline.py` | Direct pipeline execution: `python scripts/run_pipeline.py --job-id <id>` |
| **Runner Service** | `runner_service/app.py` | FastAPI wrapper with subprocess execution, log streaming, JWT auth |
| **Frontend** | `frontend/app.py` | Flask/HTMX UI with job browsing, process buttons, health indicators |

---

## Pipeline Layers

### Layer 2: Pain Point Miner
**File**: `src/layer2/pain_point_miner.py`

Extracts structured intelligence from job descriptions:
- **Output**: `pain_points` (5-10), `strategic_needs`, `risks_if_unfilled`, `success_metrics`
- **Validation**: Pydantic schema, JSON-only output
- **Retries**: tenacity with exponential backoff

### Layer 2.5: STAR Selector (Optional)
**File**: `src/layer2_5/star_selector.py`

Selects relevant achievements from knowledge base:
- **Input**: `knowledge-base.md` parsed via `star_parser`
- **Strategy**: LLM-only scoring (no embeddings/graph currently)
- **Output**: 2-3 STARs + `star_to_pain_mapping`
- **Default**: Disabled (`ENABLE_STAR_SELECTOR=false`)

### Layer 3: Company Researcher
**File**: `src/layer3/company_researcher.py`

FireCrawl-based company intelligence:
- **Sources**: Official site, LinkedIn, Crunchbase, news, job URL
- **Output**: `CompanyResearch` (summary + signals with source URLs)
- **Cache**: MongoDB `company_cache` with 7-day TTL

### Layer 3.5: Role Researcher
**File**: `src/layer3/role_researcher.py`

Role context analysis:
- **Output**: Role summary, business impact bullets, "why now" timing
- **Inputs**: Job description, company signals, STAR context (when available)

### Layer 4: Opportunity Mapper
**File**: `src/layer4/opportunity_mapper.py`

Fit analysis and scoring:
- **Output**: `fit_score` (0-100), `fit_rationale`, `fit_category`
- **Behavior**: Warns (doesn't fail) when STAR metrics missing

### Layer 5: People Mapper
**File**: `src/layer5/people_mapper.py`

Contact discovery and outreach generation:

**When FireCrawl enabled** (`DISABLE_FIRECRAWL_OUTREACH=false`):
- SEO-style queries: `site:linkedin.com/in "{company}" recruiter`
- Extracts contacts from search metadata (title, description, URL)
- Parallel searches for recruiters, leadership, hiring managers
- LLM classification into primary (4-6) and secondary (4-6) buckets

**When FireCrawl disabled** (default):
- Generates synthetic role-based contacts (4 primary + 4 secondary)
- Still generates personalized outreach packages

**Outreach Generation**:
- LinkedIn messages: 150-550 chars with Calendly link
- Email: 5-10 word subject + 95-205 word body
- Validation: No emojis, no placeholders, pain-point focus

### Layer 6: Generator & LinkedIn Outreach
**Files**: `src/layer6/generator.py`, `src/layer6/outreach_generator.py`

CV, Cover Letter, and LinkedIn outreach generation:

**CV Generator** (`MarkdownCVGenerator`):
- Two-pass flow: Evidence JSON → QA pass
- Uses Anthropic Claude (default) or OpenRouter/OpenAI
- Grounded in master-cv.md
- Output: `applications/<company>/<role>/CV.md`

**Cover Letter Generator** (`CoverLetterGenerator`):
- Multiple validation gates
- Company mention check, JD specificity check
- Master CV grounding validation

**LinkedIn Outreach Generator**:

**Character Limits** (ENFORCED):
- Connection requests: 300 characters (hard limit, LinkedIn enforces)
- InMail messages: 1900 characters for body, 200 for subject
- Direct messages: No hard limit (recommend 500-1000 chars)

**Required Components**:
1. Personalized greeting: "Hi {FirstName},"
2. Hook: Reference pain point or specific achievement (1-2 sentences)
3. Value proposition: Candidate's relevant experience (2-3 sentences for InMail, 1 sentence for connection)
4. Call-to-action: Calendly URL with context
5. Signature: **"Best. Taimoor Alam"** (with period, MANDATORY in all messages)

**Connection Request Format** (300 char max):
```
Hi {FirstName}, I saw your {Role} at {Company} and your work on {PainPoint}.
Let's connect and discuss {Value}.
Book time: {CalendlyURL}
Best. Taimoor Alam
```

**InMail Format** (1900 char max for body):
```
Subject: {Role} - {PainPoint} Solution

Hi {FirstName},

[Hook paragraph - reference specific achievement or pain point]

[Value paragraph - map candidate's experience to their needs]

[CTA paragraph - Calendly link and next steps]

Best. Taimoor Alam
{CalendlyURL}
```

**Post-Generation Validation**:
- Length check: `len(message) <= 300` (connection) or `<= 1900` (InMail)
- Signature presence: `"Best. Taimoor Alam"` must be in final message
- Calendly URL presence: `calendly_url` must be included
- Token replacement: No `{Token}` placeholders remain
- If validation fails: Regenerate with stricter length constraints

### Layer 7: Publisher
**File**: `src/layer7/publisher.py`

Output aggregation and persistence:
- Generates dossier text via `dossier_generator.py`
- Saves to `applications/<company>/<role>/`:
  - `dossier.txt`
  - `cover_letter.txt`
  - `CV.md`
- Updates MongoDB `level-2` with: fit analysis, cover letter, cv_path, selected STARs
- Optional: Google Drive/Sheets upload (`ENABLE_REMOTE_PUBLISHING=true`)

---

## Data Model

### JobState (`src/common/state.py`)

```python
class JobState(TypedDict):
    # Input
    job_id: str
    title: str
    company: str
    job_description: str
    candidate_profile: str  # master-cv.md content

    # Layer 2
    pain_points: List[str]
    strategic_needs: List[str]

    # Layer 2.5 (optional)
    selected_stars: List[Dict]
    star_to_pain_mapping: Dict
    all_stars: List[Dict]

    # Layer 3
    company_research: Dict  # CompanyResearch

    # Layer 3.5
    role_research: Dict

    # Layer 4
    fit_score: int
    fit_rationale: str
    fit_category: str

    # Layer 5
    primary_contacts: List[Dict]
    secondary_contacts: List[Dict]

    # Layer 6
    cv_path: str
    cv_reasoning: str
    cover_letter: str

    # Layer 7
    output_dir: str

    # Meta
    errors: List[str]
```

### MongoDB Collections

| Collection | Purpose | TTL |
|------------|---------|-----|
| `level-2` | Job postings with pipeline results | None |
| `company_cache` | Cached company research | 7 days |
| `star_records` | STAR achievements (future) | None |
| `pipeline_runs` | Run metadata (unused) | None |

---

## Configuration

### Feature Flags (`src/common/config.py`)

| Flag | Default | Effect |
|------|---------|--------|
| `ENABLE_STAR_SELECTOR` | `false` | Skip STAR selection, use master CV directly |
| `DISABLE_FIRECRAWL_OUTREACH` | `true` | Use synthetic contacts instead of FireCrawl |
| `ENABLE_REMOTE_PUBLISHING` | `false` | Save locally only, skip Drive/Sheets |
| `USE_ANTHROPIC` | `true` | Use Anthropic Claude for CV generation |
| `USE_OPENROUTER` | `false` | Use OpenRouter for CV generation |

### LLM Provider Priority (CV Generation)

1. Anthropic Claude (`USE_ANTHROPIC=true`, default)
2. OpenRouter (`USE_OPENROUTER=true`)
3. OpenAI (fallback)

---

## External Services

| Service | Used By | Purpose |
|---------|---------|---------|
| **OpenAI** | Layers 2-5 | General LLM calls |
| **Anthropic** | Layer 6 | CV generation (default) |
| **FireCrawl** | Layer 3, 5 | Web scraping, company research |
| **Google Drive** | Layer 7 | Optional file storage |
| **Google Sheets** | Layer 7 | Optional tracker |

---

## Output Structure

```
applications/
└── <Company_Name>/
    └── <Role_Title>/
        ├── CV.md
        ├── dossier.txt
        ├── cover_letter.txt
        └── contacts_outreach.json (when enabled)
```

---

## CV Rich Text Editor (Phase 1-4 COMPLETE as of 2025-11-27)

**Status**: Phases 1-4 complete and fully tested (228 total tests passing). Phase 5 (Polish) pending.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Job Detail Page                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │   Main Content Area         │  │   CV Editor Side Panel (Right)     │   │
│  │   - Cover Letter            │  │  ┌───────────────────────────────┐  │   │
│  │   - Pain Points             │  │  │ [✕] [↔ Expand]  [Export PDF]  │  │   │
│  │   - Contacts                │  │  │ ● Saved 3s ago                │  │   │
│  │                             │  │  ├───────────────────────────────┤  │   │
│  │  [Edit CV] ─────────────────┼──┤  │ Toolbar: Font | B | I | U | • │  │   │
│  │                             │  │  ├───────────────────────────────┤  │   │
│  │                             │  │  │                               │  │   │
│  │                             │  │  │  TipTap Rich Text Editor      │  │   │
│  │                             │  │  │  (Letter/A4 Preview)          │  │   │
│  │                             │  │  │                               │  │   │
│  │                             │  │  └───────────────────────────────┘  │   │
│  └─────────────────────────────┘  └─────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Status |
|-----------|------------|--------|
| Rich Text | TipTap v2 (ProseMirror) + StarterKit | Complete (Phase 1) |
| Fonts | Google Fonts (6 fonts) | Complete (Phase 1); Phase 2 will expand to 60+ |
| PDF Export | html2pdf.js (client-side) | Phase 4 (pending) |
| Persistence | MongoDB `cv_editor_state` field | Complete (Phase 1) |
| UI Framework | Vanilla JS + Tailwind | Complete (Phase 1) |

### Data Flow

```
Pipeline (Layer 6)  →  cv_text (Markdown)  →  MongoDB
                                                  ↓
                                       cv_editor_state migration (auto on first access)
                                                  ↓
                          TipTap Editor  ←  GET /api/jobs/{id}/cv-editor
                                  ↓
                           User edits (B/I/U, headings, lists)
                                  ↓
                    Auto-save (3s debounce)  →  PUT /api/jobs/{id}/cv-editor  →  MongoDB
                                  ↓
                           Save indicator updates (● synced, ◐ saving)
```

### API Endpoints (Phase 1 Complete)

#### GET `/api/jobs/<job_id>/cv-editor`
**Purpose**: Retrieve editor state or migrate from legacy markdown format
**Response**:
```json
{
  "success": true,
  "editor_state": {
    "version": 1,
    "content": { "type": "doc", "content": [...] },
    "documentStyles": {
      "fontFamily": "Inter",
      "fontSize": 11,
      "lineHeight": 1.5,
      "margins": { "top": 0.75, "right": 0.75, "bottom": 0.75, "left": 0.75 }
    },
    "lastSavedAt": "2025-11-26T15:30:00Z"
  }
}
```

#### PUT `/api/jobs/<job_id>/cv-editor`
**Purpose**: Save editor state to MongoDB
**Request**:
```json
{
  "version": 1,
  "content": { "type": "doc", "content": [...] },
  "documentStyles": { "fontFamily": "Inter", "fontSize": 11 }
}
```
**Response**:
```json
{
  "success": true,
  "savedAt": "2025-11-26T15:30:03Z",
  "message": "CV editor state saved successfully"
}
```

#### POST `/api/jobs/<job_id>/cv-editor/pdf` (Phase 4 - Migrated to Runner Service)
**Purpose**: Generate and download PDF from current CV editor state
**Architecture**: Frontend proxies requests to runner service (VPS)
**Request**:
```json
{
  "version": 1,
  "content": { "type": "doc", "content": [...] },
  "documentStyles": { "fontFamily": "Inter", "fontSize": 11, "lineHeight": 1.5, "margins": {...} }
}
```
**Response**: Binary PDF file with filename: `CV_<Company>_<Title>.pdf`
**Status Codes**:
- 200 OK - PDF generated successfully
- 400 Bad Request - Invalid editor state or missing fields
- 500 Internal Server Error - Playwright rendering failed
- 503 Service Unavailable - Runner service unreachable
**Error Response**:
```json
{
  "error": "PDF generation failed",
  "message": "Specific error details",
  "code": "ERROR_CODE"
}
```

### PDF Generation Architecture

**Location**: Runner Service (VPS 72.61.92.76)

**Why Runner, Not Frontend?**
- Vercel serverless functions don't support browser automation (no system-level access)
- Playwright requires Chromium browser binary (~130 MB) - not available on Vercel
- Runner service already has Playwright installed (Dockerfile.runner lines 32-33)
- VPS has full control over dependencies, execution time, and resource allocation
- Better resource utilization and cost efficiency for PDF generation

**Architecture Flow:**

```
┌─────────────────────────────┐
│  Frontend (Vercel)          │
│  - User clicks Export PDF    │
│  - Validates editor state    │
│  - Shows loading toast       │
└──────────────┬──────────────┘
               │
               ▼
         HTTP Request
    POST /api/jobs/{id}/
      cv-editor/pdf
               │
               ▼
┌─────────────────────────────────┐
│  Frontend Proxy (app.py)        │
│  - Routes request to runner     │
│  - Handles timeout/errors       │
│  - Streams response back        │
└──────────────┬──────────────────┘
               │
     env: RUNNER_SERVICE_URL
     (http://72.61.92.76:8000)
               │
               ▼
┌─────────────────────────────────────────┐
│  Runner Service (VPS FastAPI)           │
│  POST /api/jobs/{id}/cv-editor/pdf      │
│  - Fetch job from MongoDB               │
│  - Fetch cv_editor_state                │
│  - Convert TipTap JSON → HTML           │
│  - Embed 60+ Google Fonts               │
│  - Launch Playwright/Chromium           │
│  - Render to PDF with margins/styles    │
│  - Return binary PDF                    │
└──────────────┬──────────────────────────┘
               │
               ▼
        PDF Binary Stream
               │
               ▼
   Browser Download: CV_<Company>_<Title>.pdf
```

**Endpoints:**

**Frontend (Proxy Only):**
```
POST https://job-search-inky-sigma.vercel.app/api/jobs/{id}/cv-editor/pdf
Content-Type: application/json

{
  "version": 1,
  "content": { ... },
  "documentStyles": { ... }
}

Response: Binary PDF file (streams from runner)
```

**Runner Service (Actual Generation):**
```
POST http://72.61.92.76:8000/api/jobs/{id}/cv-editor/pdf
Content-Type: application/json

{
  "version": 1,
  "content": { ... },
  "documentStyles": { ... }
}

Response: Binary PDF file (Playwright generated)
```

**Implementation Files:**

- **Runner Service Helpers**: `runner_service/pdf_helpers.py` (349 lines)
  - `sanitize_for_path()` - Sanitize company/role for filesystem paths
  - `tiptap_json_to_html()` - Convert TipTap JSON document to HTML with styling
  - `build_pdf_html_template()` - Build complete HTML document with embedded fonts and styles

- **Runner Service Endpoint**: `runner_service/app.py` lines 368-498
  - Fetch `cv_editor_state` from MongoDB
  - Validate request body
  - Convert TipTap JSON to HTML
  - Generate PDF with Playwright
  - Return PDF binary with proper headers

- **Frontend Proxy**: `frontend/app.py` lines 870-939
  - `POST /api/jobs/{id}/cv-editor/pdf` endpoint
  - Forward request to runner service
  - Handle timeout/error cases
  - Stream PDF response to user
  - Proper Content-Disposition header for download

**Dependencies:**

- **Runner Service**: Playwright 1.40.0+ (already in Dockerfile.runner)
- **Runner Service**: Chromium browser (installed by Playwright)
- **Frontend**: `requests` library for HTTP proxy (standard in Flask)
- **Both**: MongoDB driver for fetching job data

**Configuration (Environment Variables):**

**Frontend (app.py)**:
```bash
RUNNER_SERVICE_URL=http://72.61.92.76:8000    # Runner service base URL
RUNNER_API_TOKEN=<optional-jwt-token>         # Optional: For runner authentication
```

**Runner Service (app.py)**:
```bash
MONGO_URI=mongodb+srv://...                   # MongoDB connection
MONGO_DB_NAME=job_search                      # Database name
PLAYWRIGHT_HEADLESS=true                      # Always headless in production
```

**PDF Generation Details:**

1. **HTML Template** (from `build_pdf_html_template`):
   - DOCTYPE, meta tags, viewport settings
   - 60+ Google Fonts embedded via CSS
   - `documentStyles` applied as CSS (margins, line-height, page size)
   - Header/footer text (if provided)
   - TipTap content converted to semantic HTML
   - Print-optimized CSS for ATS compatibility

2. **Playwright Configuration**:
   - Format: `letter` (8.5" × 11") or `a4` (210mm × 297mm)
   - Margins: From `documentStyles.margins` (converted to inches/mm)
   - Print background: `true` (preserves styling)
   - Scale: `1.0` (pixel-perfect rendering)
   - Timeout: 30 seconds

3. **Output Quality**:
   - ATS-compatible (selectable text, no image-based rendering)
   - Fonts embedded (no font substitution issues)
   - Colors preserved (heading colors, highlights, alignment)
   - Page breaks handled automatically by Chromium

**Error Handling:**

| Error | Root Cause | User Message |
|-------|-----------|--------------|
| 400 Bad Request | Invalid editor state | "Invalid CV editor state" |
| 404 Not Found | Job not in MongoDB | "Job not found" |
| 500 Playwright Error | PDF rendering failed | "PDF generation failed" |
| 503 Runner Unavailable | Runner service down | "PDF service temporarily unavailable" |

**Testing:**

- 22 unit tests for Phase 4 PDF export (`tests/frontend/test_cv_editor_phase4.py`)
- Tests cover: HTML conversion, CSS application, error handling, edge cases
- Mock Playwright for deterministic testing
- All tests passing (100%)

### MongoDB Schema Addition (Phase 1 Complete)

```javascript
// level-2 collection - new field
{
  _id: ObjectId,
  job_id: string,
  // ... existing fields ...

  cv_editor_state: {
    version: 1,                           // Schema version for migrations
    content: {                            // TipTap JSON document
      type: "doc",
      content: [
        {
          type: "heading",
          attrs: { level: 1 },
          content: [{ type: "text", text: "John Doe" }]
        },
        {
          type: "paragraph",
          content: [{ type: "text", text: "Software Engineer" }]
        }
        // ... more nodes ...
      ]
    },
    documentStyles: {
      fontFamily: "Inter",                // Font from Google Fonts
      fontSize: 11,                       // Points
      lineHeight: 1.5,                    // Line spacing
      margins: {
        top: 0.75,                        // Inches
        right: 0.75,
        bottom: 0.75,
        left: 0.75
      },
      pageSize: "letter"                  // letter | a4
    },
    lastSavedAt: ISODate("2025-11-26T15:30:03Z")
  }
}
```

### Phase 3: Document-Level Styles (Complete as of 2025-11-27)

**Status**: Production-ready with 28 unit tests passing

**Features Implemented**:

1. **Line Height Control** (4 preset options)
   - Single (1.0) - Tight spacing
   - Standard (1.15) - Default, Microsoft Word "single" spacing
   - 1.5 Lines (1.5) - Readable spacing
   - Double (2.0) - Generous spacing

2. **Document Margins** (Independent controls)
   - Top, Right, Bottom, Left margins
   - Range: 0.5" to 2.0" in 0.25" increments
   - Default: 1.0" all sides (ATS-friendly standard)
   - Implemented as CSS padding to preserve editor background

3. **Page Size Selector**
   - Letter: 8.5" × 11" (US standard)
   - A4: 210mm × 297mm (International standard)
   - Controls max-width and min-height in CSS

4. **Header/Footer Text**
   - Optional header text input (appears at top of CV)
   - Optional footer text input (appears at bottom of CV)
   - Auto-saved to MongoDB
   - Used in Phase 4 PDF export

**UI Design**:

- Collapsible "Document Settings (Page Layout)" toolbar section
- 4 margin dropdowns (top, right, bottom, left)
- Line height dropdown with descriptive labels
- Page size dropdown (Letter/A4)
- Header/footer text inputs (show/hide toggle)

**Technical Architecture**:

```javascript
// Key JavaScript Functions (cv-editor.js)
getCurrentLineHeight()       // Returns current line height value
getCurrentMargins()          // Returns {top, right, bottom, left}
getCurrentPageSize()         // Returns "letter" or "a4"
applyDocumentStyles()        // Applies inline styles to .ProseMirror
saveEditorState()            // Includes Phase 3 fields in save
restoreDocumentStyles()      // Restores styles on editor load
```

**Default Values**:

```javascript
{
  documentStyles: {
    lineHeight: 1.15,        // Standard Microsoft Word spacing
    margins: {
      top: 1.0,              // 1 inch (standard resume format)
      right: 1.0,
      bottom: 1.0,
      left: 1.0
    },
    pageSize: "letter"       // US Letter 8.5" × 11"
  },
  header: "",                // Optional
  footer: ""                 // Optional
}
```

**MongoDB Schema Extensions**:

```javascript
cv_editor_state: {
  version: 1,
  content: { /* TipTap JSON */ },
  documentStyles: {
    lineHeight: 1.15,        // float
    margins: {               // inches
      top: 1.0,
      right: 1.0,
      bottom: 1.0,
      left: 1.0
    },
    pageSize: "letter"       // "letter" | "a4"
  },
  header: "Optional text",   // string (optional)
  footer: "Optional text",   // string (optional)
  lastSavedAt: ISODate("2025-11-27T...")
}
```

**Integration with Phase 4 (PDF Export)**:

- Phase 4 PDF generation uses Phase 3 `documentStyles` fields
- Margins apply to page layout in PDF
- Line height applied to all paragraphs
- Page size determines PDF dimensions
- Header/footer text included in PDF output

**Test Coverage**: 28 tests across 6 categories
- Margin controls: 5 tests
- Line height adjustment: 5 tests
- Page size selector: 6 tests
- Header/footer support: 4 tests
- Phase 3 integration: 3 tests
- CSS application: 3 tests
- Backward compatibility: 2 tests

### Implemented Features (Phase 1-2)

**Phase 1 (Complete)**:
- [x] TipTap editor initialization with StarterKit extensions
- [x] Basic formatting: bold, italic, underline
- [x] Block formatting: headings (h1-h3), bullet lists, numbered lists
- [x] Side panel UI with slide-in/collapse animation
- [x] Auto-save with 3-second debounce
- [x] Visual save indicator (● synced, ◐ saving, error on fail)
- [x] MongoDB persistence to `cv_editor_state` field
- [x] Markdown-to-TipTap migration for legacy CVs
- [x] GET/PUT API endpoints with validation
- [x] 46 comprehensive unit tests (100% passing)

**Phase 2 (Code Complete - 2025-11-27)**:
- [x] Font library expanded (6 → 60+ Google Fonts)
- [x] Font size selector (8-24pt)
- [x] Font color / highlight with color picker
- [x] Text alignment (left/center/right/justify)
- [x] Indentation controls (Tab/Shift+Tab)
- [x] Toolbar reorganized into 7 logical groups
- [x] Content loading from MongoDB restored
- [x] Error handling on editor open
- [x] Save indicator visibility and updates
- [x] 38 unit tests (100% passing)

**Phase 3 (Complete - 2025-11-27)**:
- [x] Document-level margin controls (top, right, bottom, left) with 0.25" increments
- [x] Line height adjustment (4 presets: 1.0, 1.15, 1.5, 2.0)
- [x] Page size selector (Letter 8.5×11", A4 210×297mm)
- [x] Header text input (optional, appears at top)
- [x] Footer text input (optional, appears at bottom)
- [x] Real-time CSS application to editor preview
- [x] MongoDB persistence of document styles
- [x] 28 unit tests (100% passing)

**Phase 4 (Complete - 2025-11-27)**:
- [x] Server-side PDF generation using Playwright
- [x] Pixel-perfect rendering with Chromium headless browser
- [x] ATS-compatible output with text extraction
- [x] Google Fonts embedding (60+ fonts)
- [x] Custom margins, line height, and styles applied to PDF
- [x] Header/footer text inclusion in PDF
- [x] Export button in CV editor toolbar
- [x] Auto-save before export
- [x] Proper error handling with toast notifications
- [x] 22 unit tests (100% passing)

**Pending (Phase 5)**:
- [ ] Keyboard shortcuts (Ctrl+B, Ctrl+I, Ctrl+Z, etc.)
- [ ] Version history / undo-redo persistence beyond browser session
- [ ] E2E tests via Playwright
- [ ] Mobile responsiveness testing
- [ ] Accessibility (WCAG 2.1 AA) compliance

### Phase 2 Troubleshooting (Known Issues)

**Issue #1: CV Content Not Loading**
- **Symptom**: Editor panel opens, but no CV content appears
- **Check List**:
  1. Browser DevTools Console → Look for JavaScript errors
  2. Network tab → Verify GET `/api/jobs/<id>/cv-editor` returns 200 OK with valid JSON
  3. Response payload → Check if `editor_state` contains `content` nodes
  4. TipTap init → Verify `editor.setContent()` executes after load
  5. CSS → Check for hidden/display:none on editor container
- **Likely Cause**: API response missing content, or TipTap not initializing with data
- **Fix Path**: architecture-debugger to trace API call and editor initialization

**Issue #2: Error on Editor Open**
- **Symptom**: Unspecified error message appears when opening editor
- **Check List**:
  1. Browser DevTools Console → Capture exact error message and stack trace
  2. Network tab → Look for failed requests (404, 500, etc.)
  3. CDN scripts → Verify Google Fonts and TipTap extensions loaded (Status 200)
  4. Extensions → Test if TipTap extensions (FontSize, Highlight) initialized correctly
- **Likely Cause**: Missing CDN resource, extension initialization failure, or API error
- **Fix Path**: architecture-debugger to capture error details and trace source

**Issue #3: Save Indicator Unclear**
- **Symptom**: User unsure if auto-save is working or indicator visible
- **Check List**:
  1. DOM → Verify `#cv-save-indicator` element exists in HTML
  2. CSS → Check visibility (not `display:none`, `visibility:hidden`, `opacity:0`)
  3. Save trigger → Test by editing text, wait 3 seconds
  4. Indicator update → Check if text/color changes during save
  5. Persistence → Verify data actually saved to MongoDB after indicator shows "Saved"
- **Likely Cause**: Indicator hidden by CSS, or save logic not triggering
- **Fix Path**: frontend-developer to improve CSS visibility and save feedback

### Test Coverage (Phases 1-4)

| Test Suite | Tests | Status |
|-----------|-------|--------|
| Phase 1: API endpoints | 18 | 100% passing |
| Phase 1: Markdown migration | 17 | 100% passing |
| Phase 1: MongoDB integration | 11 | 100% passing |
| Phase 2: Text formatting & fonts | 38 | 100% passing |
| Phase 3: Document-level styles | 28 | 100% passing |
| Phase 4: PDF export | 22 | 100% passing |
| Phase 2-4: Integration tests | 94 | 100% passing |
| **Total** | **228** | **100% passing** |

**Execution Time**: ~0.5 seconds
**Framework**: pytest with mock LLM providers and Playwright fixtures

---

## Reliability

- **Retries**: tenacity with exponential backoff on all LLM calls
- **Validation**: Pydantic schemas for all structured outputs
- **Caching**: Company research cached 7 days in MongoDB
- **Error handling**: Errors accumulated in state, non-fatal where possible
