# Job Intelligence Pipeline - Architecture

**Last Updated**: 2025-11-30 (Layer-level Structured Logging Complete; ATS Compliance Research)

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
│                                │         │     │ star_records     │         │
│                                │         │     └──────────────────┘         │
│                                │         │                                  │
│                                ▼         │     ┌──────────────────┐         │
│                    ┌───────────────────┐ └────►│ VPS PDF Service  │         │
│                    │ LangGraph Pipeline│       │ (FastAPI)        │         │
│                    │ (src/workflow.py) │       │ Playwright/Chrome│         │
│                    └───────────────────┘       │ Port 8001        │         │
│                                                └──────────────────┘         │
│                                                (Internal Docker Network)    │
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

## CV Rich Text Editor (Phase 1-5.1 COMPLETE as of 2025-11-28)

**Status**: Phases 1-5.1 complete, fully stable, and all bugs resolved (220 total tests passing: 188 Phase 1-4 + 32 Phase 5.1). Phase 5.2 (Keyboard Shortcuts, Version History, Mobile, A11y) starting. Phase 6 (PDF Service Separation) planned in parallel.

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

### Markdown-to-TipTap Migration Pattern (NEW - 2025-11-28)

**Context**: Pipeline Layer 6 generates CVs as Markdown (`cv_text`). User-edited CVs use TipTap JSON format (`cv_editor_state`). Hybrid system requires migration to support both.

**Migration Strategy**: Automatic conversion on first editor access, seamless backward compatibility.

**Locations**:

1. **Frontend** (`frontend/app.py` - GET endpoint):
   - Fetches job from MongoDB
   - If `cv_editor_state` exists: Return as-is
   - If `cv_editor_state` missing but `cv_text` exists: Migrate markdown → TipTap JSON
   - Send migrated state to editor

2. **Runner Service** (`runner_service/app.py` - PDF generation endpoint):
   - Function: `migrate_cv_text_to_editor_state()` (lines 368-495)
   - Fallback chain: `cv_editor_state` → migrate `cv_text` → empty default
   - Used when generating PDF from detail page (no manual edit required)
   - Ensures jobs from pipeline can be exported immediately to PDF

**Migration Process**:

```
Pipeline generates CV as Markdown (cv_text)
        ↓
User clicks "Edit CV" or "Export PDF" on detail page
        ↓
Backend checks MongoDB:
  - If cv_editor_state exists: Use it
  - If cv_text exists but no cv_editor_state: Migrate
  - If neither exist: Use empty template
        ↓
Markdown → TipTap JSON conversion:
  - Parse markdown lines
  - Identify block types (heading, paragraph, list)
  - Convert to TipTap node structure
  - Preserve formatting (bold, italic, links)
        ↓
Return TipTap state to frontend/generate PDF
        ↓
On save: Store both cv_text (for reference) and cv_editor_state (for editing)
```

**Key Design Decision**: Preserve `cv_text` field after migration for backward compatibility and audit trail. Both formats coexist in MongoDB.

**Testing**: 9/9 runner PDF integration tests passing, including new migration test (`tests/runner/test_pdf_integration.py:337-396`)

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
     env: RUNNER_URL
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
RUNNER_URL=http://72.61.92.76:8000            # Runner service base URL
RUNNER_API_SECRET=<shared-secret>             # REQUIRED: Must match runner service RUNNER_API_SECRET
```

**Runner Service (app.py)** (Updated 2025-11-28):
```bash
MONGODB_URI=mongodb+srv://...                 # MongoDB connection (changed from MONGO_URI)
MONGO_DB_NAME=job_search                      # Database name
PLAYWRIGHT_HEADLESS=true                      # Always headless in production
RUNNER_API_SECRET=<shared-secret>             # Authentication token (changed from RUNNER_API_TOKEN)
```

**PDF Generation Details:**

1. **HTML Template** (from `build_pdf_html_template`):
   - DOCTYPE, meta tags, viewport settings
   - 60+ Google Fonts embedded via CSS
   - `documentStyles` applied as CSS (margins, line-height, page size)
   - Header/footer text (if provided)
   - TipTap content converted to semantic HTML using iterative stack-based approach (no recursion)
   - Print-optimized CSS for ATS compatibility

2. **TipTap-to-HTML Conversion** (2025-11-28):
   - **Approach**: Iterative stack-based conversion (eliminates recursion depth limits)
   - **Why**: Deeply nested TipTap nodes (complex documents) can exceed Python recursion limit
   - **Implementation**: Uses queue/stack to process nodes iteratively instead of recursively
   - **Benefit**: Supports arbitrarily deep document nesting without stack overflow errors
   - **Files**: `runner_service/pdf_helpers.py` - `tiptap_json_to_html()` function

3. **Playwright Configuration** (Updated 2025-11-28):
   - Format: `letter` (8.5" × 11") or `a4` (210mm × 297mm)
   - Margins: From `documentStyles.margins` applied via CSS `@page` rule (WYSIWYG)
   - Print background: `true` (preserves styling)
   - Scale: `1.0` (pixel-perfect rendering)
   - Timeout: 30 seconds
   - Async API: Converted to async for FastAPI compatibility (commit 86de8a00)

4. **Margin Validation Defense-in-Depth** (NEW - 2025-11-28)

   **Problem Root Cause**: Type conversion chain failure across 3 layers:
   - JavaScript: `parseFloat("")` returns NaN on empty margin fields
   - JSON serialization: Converts NaN to null
   - Python dict.get(): Returns None when value is None (doesn't use default)
   - String interpolation: `f"{None}in"` produces "Nonein" (fails Playwright validation)

   **Solution**: Three-layer validation ensures None values never reach Playwright:

   **Layer 1 - Frontend (JavaScript Prevention)**:
   - Location: `frontend/static/js/cv-editor.js` (lines 481-500)
   - `safeParseFloat()` helper function prevents NaN/null values
   - Returns default value (1.0) for invalid inputs
   - Validates before sending to backend

   **Layer 2 - Runner Service (Python Validation)**:
   - Location: `runner_service/app.py` (lines 498-526)
   - `sanitize_margins()` function checks for None values
   - Fallback to 1.0 inch default for any missing margin
   - Applied in PDF generation endpoint before proxying to PDF service

   **Layer 3 - PDF Service (Playwright Guard)**:
   - Location: `pdf_service/app.py` (lines 286-291)
   - `margins.get('top') or 1.0` pattern handles None values
   - Ensures Playwright never receives malformed strings
   - Final validation before passing to Playwright API

   **Testing**: 48 PDF service tests verify all margin scenarios:
   - Empty strings, null values, missing keys
   - All values together and individually
   - Edge cases: 0 values, max values, fractional values
   - All tests passing (100% pass rate)

5. **Output Quality** (Updated 2025-11-28):
   - ATS-compatible (selectable text, no image-based rendering)
   - Fonts embedded (no font substitution issues)
   - Colors preserved (heading colors, highlights, alignment)
   - Page breaks handled automatically by Chromium
   - Margins via CSS @page rule ensure WYSIWYG rendering (commit 39fc8274)

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
- [ ] WYSIWYG Page Break Visualization (NEW - 2025-11-28) - See section below
- [ ] Keyboard shortcuts (Ctrl+B, Ctrl+I, Ctrl+Z, etc.)
- [ ] Version history / undo-redo persistence beyond browser session
- [ ] E2E tests via Playwright
- [ ] Mobile responsiveness testing
- [ ] Accessibility (WCAG 2.1 AA) compliance

### Phase 5.1: WYSIWYG Page Break Visualization ✅ COMPLETE (2025-11-28)

**Status**: COMPLETE and TESTED (32 tests passing)
**Completion Date**: 2025-11-28
**Implementation Report**: `reports/PHASE5_1_IMPLEMENTATION_2025-11-28.md`

**Feature Overview**:
Visual page break indicators in the CV editor and detail page showing exactly where content will break across pages when exported to PDF. Provides true WYSIWYG experience matching actual PDF output.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CV Editor with Page Break Visualization                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Toolbar: Font | B | I | Margins | Line Height | Page Size | Export  │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │ TipTap Editor (8.5" x 11" preview)                             │ │   │
│  │  │                                                                │ │   │
│  │  │ John Doe                                                       │ │   │
│  │  │ Senior Software Engineer                                       │ │   │
│  │  │                                                                │ │   │
│  │  │ [Content fills first page...]                                 │ │   │
│  │  │                                                                │ │   │
│  │  ├────────────────────────────────────────────────────────────────┤ │   │
│  │  │ PAGE BREAK                                                     │ │   │
│  │  ├────────────────────────────────────────────────────────────────┤ │   │
│  │  │                                                                │ │   │
│  │  │ [Page 2 content...]                                           │ │   │
│  │  │                                                                │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Components** (ALL COMPLETE):

1. **Page Break Calculator Module** (`frontend/static/js/page-break-calculator.js`)
   - 240 lines of pure JavaScript
   - Function: `calculatePageBreaks()`
   - Input: TipTap editor state, page size (Letter/A4), margins, document styles
   - Process:
     - Calculate available page height = (page height - top margin - bottom margin)
     - Iterate through TipTap nodes, sum content heights
     - Record break positions when cumulative height exceeds available height
   - Output: Array of Y-pixel positions where breaks occur
   - Example: `[708, 1416, 2124]` for 3-page document

2. **Page Break Renderer** (`renderPageBreaks()` in cv-editor.js)
   - Input: Array of break positions
   - Process:
     - Insert visual break indicator divs at each position
     - Apply CSS styling (gray dashed line, "Page X" label)
     - Clean up previous breaks to avoid duplicates
   - Output: DOM with visual page break indicators

3. **Dynamic Update Integration** (300ms debounce)
   - Hooks into event handlers:
     - Content change (TipTap editor `onChange`)
     - Margin changes (Document Settings panel)
     - Line height changes (Document Settings panel)
     - Page size changes (Document Settings panel)
   - Debounced recalculation to prevent excessive DOM updates

4. **Detail Page Integration**
   - Displays page breaks in main CV display area
   - Reuses calculator and renderer logic
   - Non-editable view, breaks shown for preview only
   - Consistent styling with editor breaks

**Data Flow**:

```
User edits content/styles in CV editor
        ↓
Content change event (TipTap or style change)
        ↓
Debounce (500ms)
        ↓
calculatePageBreaks():
  ├─ Get page dimensions (letter: 541.8×708px, a4: 793×1123px @ 96DPI)
  ├─ Get margins and calculate available height
  ├─ Measure cumulative TipTap node heights
  └─ Return break positions
        ↓
renderPageBreaks():
  ├─ Clear previous indicators
  ├─ Insert <div class="page-break-indicator">
  └─ Apply CSS styling
        ↓
User sees page breaks updated in real-time
```

**CSS Styling**:

```css
.page-break-indicator {
  position: absolute;
  width: 100%;
  height: 3px;
  background: linear-gradient(to right, #ddd 40%, transparent 40%, transparent 60%, #ddd 60%);
  border-top: 1px dashed #ccc;
  margin: 8px 0;
  text-align: center;
  font-size: 0.75rem;
  color: #aaa;
  pointer-events: none;
  user-select: none;
}

.page-break-indicator::after {
  content: "Page Break";
  display: block;
  padding-top: 4px;
}
```

**Page Dimensions** (at 96 DPI):

| Size | Width | Height |
|------|-------|--------|
| Letter | 8.5" (612px) | 11" (792px) |
| A4 | 210mm (793px) | 297mm (1122px) |

**Integration** (No API changes - purely client-side):
- Reuses Phase 3: Document styles (margins, page size, line height)
- Reuses Phase 4: PDF export (validates break positions)
- Calculation purely JavaScript, no backend changes needed

**Testing Strategy**:
- 50+ unit tests: Calculator, Renderer, Integration
- E2E tests: Editor and detail page functionality
- Test coverage: Single/multi-page, page sizes, margins, style changes

**Files to Create/Modify**:
- `frontend/static/js/cv-editor.js` - Page break logic
- `frontend/templates/base.html` - CSS styling
- `frontend/templates/job_detail.html` - Detail page integration
- `tests/frontend/test_cv_editor_phase5.py` - Test suite (new)
- `plans/phase5-page-break-visualization.md` - Full plan

**Dependencies** (All complete):
- Phase 3: Document styles
- Phase 4: PDF export

**Success Criteria** (ALL MET):
- [x] Page breaks visible in editor matching PDF output
- [x] Breaks update dynamically on content/style changes (300ms debounce)
- [x] All 32 tests passing (100% coverage)
- [x] No performance degradation (0.02s test execution)
- [x] Cross-browser compatible
- [x] Support for Letter and A4 page sizes
- [x] Respect all margin and layout settings

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

### Test Coverage (Phases 1-5.1)

| Test Suite | Tests | Status |
|-----------|-------|--------|
| Phase 1: API endpoints | 18 | 100% passing |
| Phase 1: Markdown migration | 17 | 100% passing |
| Phase 1: MongoDB integration | 11 | 100% passing |
| Phase 2: Text formatting & fonts | 38 | 100% passing |
| Phase 3: Document-level styles | 28 | 100% passing |
| Phase 4: PDF export | 22 | 100% passing |
| Phase 5.1: Page break visualization | 32 | 100% passing |
| Phase 2-4: Integration tests | 94 | 100% passing |
| **Total** | **260** | **100% passing** |

**Execution Time**: ~0.02 seconds (Phase 5.1 suite) + ~0.5 seconds (all phases)
**Framework**: pytest with mock LLM providers and Playwright fixtures

---

## Testing Strategy

### E2E Testing Status (2025-11-28)

**Current State**: Disabled (workflow in `.github/workflows/e2e-tests.yml.disabled`)

**What Exists**:
- 48 comprehensive Playwright tests in `tests/e2e/test_cv_editor_e2e.py`
- Browser configuration and fixtures in `tests/e2e/conftest.py`
- Test coverage for Phases 1-5 (formatting, fonts, document styles, PDF export, keyboard shortcuts, mobile, accessibility)
- Markers for cross-browser (Firefox, WebKit), mobile, accessibility, slow tests

**Why Disabled**:
1. Configuration issues with pytest-playwright integration
2. Tests written for Phase 5 features (keyboard shortcuts, mobile responsiveness, accessibility) that are not fully implemented
3. Requires valid test environment (LOGIN_PASSWORD, MongoDB access)
4. Test data fixtures needed for reliable reproduction

**Re-enablement Plan** (See `plans/e2e-testing-implementation.md`):

1. **Phase 1: Smoke Tests Only** (Phases 1-4 working features)
   - Keep E2E workflow disabled for now
   - Create subset of smoke tests for core functionality
   - Tests: editor load, basic formatting, font changes, document styles

2. **Phase 2: Phase 5 Feature Implementation** (blocked until backend support added)
   - Implement version history API for undo/redo beyond browser
   - Add keyboard shortcut handlers to frontend
   - Validate mobile responsiveness on runner PDF generation
   - Implement WCAG 2.1 AA compliance in PDF rendering

3. **Phase 3: Test Infrastructure**
   - Fix conftest.py configuration
   - Set up test data fixtures with valid MongoDB jobs
   - Configure CI environment properly
   - Add screenshot/video capture on failure

4. **Phase 4: Full E2E Re-enablement**
   - Enable all 48 tests once Phase 5 features complete
   - Run smoke tests on every PR
   - Full E2E suite on release builds

**Test Environment Requirements**:
- `E2E_BASE_URL`: Deployed frontend URL (default: https://job-search-inky-sigma.vercel.app)
- `LOGIN_PASSWORD`: Valid password for test authentication
- MongoDB access: Valid job records for testing
- Playwright: Already in requirements.txt (currently commented out - `.disabled` suffix)

---

## Observability & Logging (2025-11-30)

### Structured Logging Architecture

All 10 pipeline nodes now emit structured JSON events for monitoring and debugging:

**Event Format**:
```json
{
  "timestamp": "2025-11-30T14:30:45.123Z",
  "event": "layer_start|layer_complete",
  "layer_id": 2,
  "layer_name": "pain_point_miner",
  "node_name": "pain_point_miner_node",
  "status": "running|success|error",
  "duration_ms": 4500,
  "metadata": {
    "job_id": "67a8f3c9...",
    "company": "Acme Corp",
    "error": null
  }
}
```

**Instrumented Layers**:
1. Layer 1.4: JD Extractor - `src/layer1_4/jd_extractor.py`
2. Layer 2: Pain Point Miner - `src/layer2/pain_point_miner.py`
3. Layer 3: Company Researcher - `src/layer3/company_researcher.py`
4. Layer 3.5: Role Researcher - `src/layer3/role_researcher.py`
5. Layer 4: Opportunity Mapper - `src/layer4/opportunity_mapper.py`
6. Layer 5: People Mapper - `src/layer5/people_mapper.py`
7. Layer 6: CV Generator - `src/layer6/generator.py`
8. Layer 6: Outreach Generator - `src/layer6/outreach_generator.py`
9. Layer 6 V2: CV Generator V2 - `src/layer6_v2/orchestrator.py`
10. Layer 7: Output Publisher - `src/layer7/publisher.py`

**Integration Pattern**:
```python
from src.common.logging_context import LayerContext

context = LayerContext(
    layer_id=2,
    layer_name="pain_point_miner",
    node_name="pain_point_miner_node",
    job_id=state["job_id"],
    metadata={"company": state["company"]}
)

with context.log_layer():
    # Layer implementation
    result = process_job(state)
    # Events logged automatically on enter/exit
```

**Monitoring Benefits**:
- Real-time pipeline execution tracking
- Per-layer performance metrics (duration_ms)
- Error tracking and debugging
- Production log aggregation ready
- LangSmith trace correlation (future)

---

## Reliability

- **Retries**: tenacity with exponential backoff on all LLM calls (includes cover letter + CV generation)
- **Validation**: Pydantic schemas for all structured outputs
- **Caching**: Company research cached 7 days in MongoDB
- **Error handling**: Errors accumulated in state, non-fatal where possible
- **Logging**: Structured LayerContext logging in all 10 pipeline nodes

---

## Runner Terminal Interface

**Current Status**: Implemented with basic log streaming
**Location**: `frontend/templates/job_detail.html`, `frontend/static/js/cv-editor.js`

**Features**:
- Real-time log streaming from runner service
- Display of all pipeline layer execution logs
- Error highlighting and status indicators
- Terminal output visible in job detail page

**Architecture**:

```
┌────────────────────────────────────────────────────────────────┐
│                      Job Detail Page                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  [Run Pipeline] [Stop]                                        │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ [Copy] Runner Terminal Output                            │ │
│  ├──────────────────────────────────────────────────────────┤ │
│  │ Layer 2: Pain Point Mining...                           │ │
│  │ Layer 3: Company Research...                            │ │
│  │ Layer 4: Fit Scoring...                                 │ │
│  │ [More logs...]                                          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Data Flow**:

```
Runner Service (subprocess logs)
  ↓
SSE (Server-Sent Events) or WebSocket
  ↓
Frontend receives logs
  ↓
Append to terminal output container (#terminal-output)
  ↓
Display in job detail page
```

### Planned Enhancement: Copy Button for Terminal Output

**Status**: Pending implementation
**Priority**: Medium (UX convenience feature)
**Estimated Effort**: 1-2 hours

**Feature Description**:
Add a copy button to the runner terminal interface that copies all displayed logs to the clipboard, allowing users to easily capture and share pipeline execution logs.

**Technical Implementation**:

**Button Placement**:
- Top-right corner of terminal output area
- Inline with terminal title bar

**Implementation**:
- Use JavaScript Clipboard API (`navigator.clipboard.writeText()`)
- Extract all text content from terminal output container
- Include timestamp or metadata (optional)
- Show success toast notification on successful copy
- Handle error gracefully with user-friendly message

**Files to Modify**:
- `frontend/templates/job_detail.html` - Add copy button HTML and styling
- `frontend/static/js/cv-editor.js` or new `runner-terminal.js` - Add copy functionality
- `frontend/templates/base.html` - Toast notification styles (if not already present)

**Button Styling**:
- Hover state with cursor change
- Icon: Copy icon (e.g., feather icons, Material Design)
- Label: "Copy Logs" or just icon with tooltip
- Disabled state if no logs available
- Loading state during copy operation (optional)

**Copy Behavior**:
```
User clicks "Copy" button
  ↓
Extract all text from #terminal-output container
  ↓
Call navigator.clipboard.writeText(logs)
  ↓
On success: Show "Logs copied!" toast notification
On error: Show "Failed to copy logs" error message
```

**Accessibility**:
- Keyboard accessible (Tab to button, Enter to activate)
- ARIA label: "Copy terminal output to clipboard"
- Focus indicator visible
- Works with screen readers

**Success Criteria**:
- Copy button visible and functional in terminal interface
- All logs copied to clipboard successfully
- Toast notification provides clear feedback
- Works with logs of any size
- Graceful error handling for clipboard API failures
- No performance impact on log streaming

---

## Phase 6: PDF Service Separation ✅ COMPLETE

**Status**: COMPLETE and TESTED (2025-11-28)
**Implementation Date**: 2025-11-28
**Actual Effort**: ~6 hours
**Test Coverage**: 56 unit tests (100% passing, 0.33s execution)
**Plan Document**: `plans/phase6-pdf-service-separation.md`

### Previous Architecture Issue (RESOLVED)

PDF generation was previously handled by the runner service, creating tight coupling:

```
┌─────────────────┐
│ Runner Service  │
├─────────────────┤
│ Pipeline Layer  │
│ Execution       │
├─────────────────┤
│ PDF Generation  │  ← Separate concern, resource-intensive
│ (Playwright)    │
└─────────────────┘
```

### Implemented Architecture

PDF generation is now separated into a dedicated service:

```
┌──────────────────┐      ┌──────────────────┐
│ Runner Service   │      │ PDF Service      │
├──────────────────┤      ├──────────────────┤
│ Pipeline Layer   │      │ PDF Generation   │
│ Execution        │──┐   │ (Playwright)     │
└──────────────────┘  │   └──────────────────┘
                      │
                      └─Internal Docker Network
                        (http://pdf-service:8001)
```

### Motivation

1. **Today**: CV PDF export (manual, low volume)
2. **Tomorrow**: Cover letter + dossier PDFs (planned Phase 6-7)
3. **Future**: Possible batch PDF generation
4. **Problem**: Adding each new document type requires modifying runner service
5. **Solution**: Dedicated service handles all document rendering

### Implemented Endpoints

**PDF Service** (internal Docker network only - port 8001):

```
POST /health
  Response: {"status": "healthy", "timestamp": "..."}

POST /render-pdf
  Input: {html, css, pageSize, printBackground}
  Output: Binary PDF

POST /cv-to-pdf
  Input: {tiptap_json, documentStyles, header, footer, company, role}
  Output: Binary PDF (CV_<Company>_<Title>.pdf)

POST /cover-letter-to-pdf (PLANNED)
  Input: {tiptap_json, company}
  Output: Binary PDF (CoverLetter_<Company>.pdf)

POST /dossier-to-pdf (PLANNED)
  Input: {html, company, role}
  Output: Binary PDF (Dossier_<Company>_<Role>.pdf)
```

**Runner Service** (proxies to PDF service):

```
POST /api/jobs/{id}/cv-editor/pdf
  Input: {version, content, documentStyles}
  Behavior: Calls pdf-service:/cv-to-pdf, returns PDF
  Output: Binary PDF
```

**Frontend** (unchanged):

```
POST /api/jobs/{id}/cv-editor/pdf
  (Calls runner, which calls PDF service)
  Output: Binary PDF
```

### Implementation Delivered

1. **✅ PDF Service Container Created** (2 hours)
   - ✅ Dockerfile with Playwright + Chromium (`Dockerfile.pdf-service`)
   - ✅ FastAPI application with endpoints (`pdf_service/app.py`)
   - ✅ Health check endpoint with capacity monitoring
   - ✅ Docker Compose integration (`docker-compose.runner.yml`)
   - ✅ Internal Docker network configuration (job-pipeline)

2. **✅ PDF Endpoints Implemented** (2 hours)
   - ✅ Moved `pdf_helpers.py` from runner to PDF service
   - ✅ Implemented `/render-pdf` (generic HTML/CSS → PDF)
   - ✅ Implemented `/cv-to-pdf` (TipTap JSON → PDF)
   - ✅ Comprehensive error handling (400/500/503 status codes)
   - ✅ Concurrency limiting via asyncio.Semaphore (max 5 concurrent)
   - ✅ Structured logging for monitoring

3. **✅ Runner Integration Updated** (1 hour)
   - ✅ Modified CV export endpoint to use HTTP client (httpx)
   - ✅ Replaced local Playwright with PDF service calls
   - ✅ Error handling for network failures (timeout, connection, HTTP errors)
   - ✅ 60-second timeout configuration
   - ✅ Frontend API unchanged (backward compatible)

4. **✅ Testing Completed** (1 hour)
   - ✅ 17 tests for PDF service endpoints
   - ✅ 31 tests for PDF helpers (TipTap conversion, HTML templates)
   - ✅ 8 tests for runner integration (proxy, error handling)
   - ✅ All 56 tests passing (100% pass rate)

### Benefits

- **Separation of Concerns**: Pipeline ≠ PDF rendering
- **Independent Scaling**: Can scale each service separately
- **Better Resource Management**: Playwright isolated from pipeline
- **Extensibility**: Easy to add new document types (cover letter, dossier)
- **Reliability**: PDF service crash doesn't affect pipeline execution
- **Testability**: Can test PDF service independently

### Timeline

- **Total Effort**: 4-6 hours (1 developer, 1 session)
- **Can be parallel**: Implement while Phase 5 in progress
- **Risk**: LOW (easy rollback, isolated service)
- **Deployment Window**: 1-2 hours (low-risk)

### Related Features

- **Phase 5**: WYSIWYG Page Break Visualization (uses Phase 4 PDF calculation)
- **Phase 6** (future): Cover Letter PDF export (uses pdf-service:/cover-letter-to-pdf)
- **Phase 7** (future): Dossier PDF export (uses pdf-service:/dossier-to-pdf)

### Success Criteria

- [x] PDF service container builds without errors
- [x] Health endpoint returns 200 OK
- [x] /cv-to-pdf endpoint generates valid PDF
- [x] Runner calls PDF service (not local Playwright)
- [x] CV export works end-to-end (unchanged from user perspective)
- [x] Error handling covers all failure modes
- [x] No performance degradation
- [x] Both services stable for 24+ hours

### Files Created/Modified

**New Files Created**:
- ✅ `Dockerfile.pdf-service` (48 lines)
- ✅ `pdf_service/__init__.py`
- ✅ `pdf_service/app.py` (327 lines)
- ✅ `pdf_service/pdf_helpers.py` (369 lines - moved from runner)
- ✅ `tests/pdf_service/__init__.py`
- ✅ `tests/pdf_service/test_endpoints.py` (315 lines, 17 tests)
- ✅ `tests/pdf_service/test_pdf_helpers.py` (403 lines, 31 tests)
- ✅ `tests/runner/test_pdf_integration.py` (331 lines, 8 tests)
- ✅ `conftest.py` (root pytest configuration)
- ✅ `setup.py` (editable install configuration)

**Modified Files**:
- ✅ `docker-compose.runner.yml` - Added PDF service configuration
- ✅ `runner_service/app.py` - Replaced local Playwright with HTTP client
- ✅ `pytest.ini` - Added pythonpath configuration

**No Changes Needed**:
- ✅ `frontend/app.py` (API unchanged - backward compatible)
- ✅ `frontend/templates/job_detail.html` (UI unchanged)
- ✅ `frontend/static/js/cv-editor.js` (client logic unchanged)

---

## Planned Enhancements (2025-11-29)

> See `plans/missing.md` section "New Requirements (2025-11-29)" for full tracking.

### Observability: Structured Logging

**Status**: Planned
**Plan**: `plans/structured-logging-implementation.md`

Replace `print()` with structured JSON logging across all pipeline layers to enable:
- Real-time frontend status button updates
- Production debugging with log aggregation
- LangSmith trace correlation (future)

**Event Format**:
```json
{
  "timestamp": "2025-11-29T10:30:45.123Z",
  "event": "layer_complete",
  "layer": 4,
  "layer_name": "opportunity_mapper",
  "status": "success",
  "duration_ms": 4500
}
```

### AI Agent Fallback Infrastructure

**Status**: Planned
**Plan**: `plans/ai-agent-fallback-implementation.md`
**Reference**: `plans/firecrawl-contact-discovery-solution.md` (Option B)

When FireCrawl contact discovery fails, fall back to LLM-powered synthetic contact generation:

```
FireCrawl Search → [Failed?] → AI Fallback Agent → Synthetic Contacts
                       ↓
              Config: ENABLE_FIRECRAWL_FALLBACK=true
```

### CV Editor Improvements

**WYSIWYG Consistency** (`plans/cv-editor-wysiwyg-consistency.md`):
- Unify CSS between editor (`.ProseMirror`) and display (`#cv-markdown-display`)
- Create shared `.cv-content` class for consistent rendering

**Margin Presets** (like MS Word):
- Add "Narrow" (0.5"), "Normal" (1.0"), "Wide" (1.5") presets
- Keep existing 0.25" increments as "Custom" option

### Prompt Optimization

**Status**: Comprehensive plan exists
**Plan**: `plans/prompt-optimization-plan.md`
**Metrics**: `reports/prompt-ab/integration-final.md`

Improve prompts for layers not meeting quality thresholds:
- Layer 4: Specificity (6.8→7.0), Grounding (7.2→8.0)
- Layer 6a: Hallucinations (8.5→9.0)
- Layer 6b: All metrics below threshold

### Job Iframe Viewer

**Status**: Planned
**Plan**: `plans/job-iframe-viewer-implementation.md`

Collapsible iframe showing original job posting URL within job detail page:
- Side-by-side comparison with generated CV
- PDF export of job posting (bonus)
- Fallback for sites that block iframes
