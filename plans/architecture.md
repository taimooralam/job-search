# Job Intelligence Pipeline - Architecture

**Last Updated**: 2025-11-26

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

## CV Rich Text Editor (Phase 1 COMPLETE + Phase 2 CODE COMPLETE as of 2025-11-27)

**Status**: Phase 1 complete and tested. Phase 2 code complete (283 lines) with 2 UX blockers pending. Phases 3-5 pending.

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

**Phase 2 (Code Complete - Known Runtime Issues)**:
- [x] Font library expanded (6 → 60+ Google Fonts)
- [x] Font size selector (8-24pt)
- [x] Font color / highlight with color picker
- [x] Text alignment (left/center/right/justify)
- [x] Indentation controls (Tab/Shift+Tab)
- [x] Toolbar reorganized into 7 logical groups
- [ ] ❌ Content loading from MongoDB (BLOCKER - not showing in editor)
- [ ] ❌ Error handling on editor open (BLOCKER - unspecified error)
- [ ] ❓ Save indicator visibility (UX issue - status unclear)

**Pending (Phase 3+)**:
- [ ] Document-level margins and line height
- [ ] Page size selector (Letter/A4)
- [ ] PDF export (server-side via Playwright)
- [ ] Keyboard shortcuts
- [ ] Version history / undo-redo persistence
- [ ] E2E tests

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

### Test Coverage (Phase 1)

| Test Suite | Tests | Coverage |
|-----------|-------|----------|
| API endpoints | 18 | 100% |
| Markdown migration | 17 | 100% |
| MongoDB integration | 11 | 100% |
| **Total** | **46** | **100%** |

**Execution Time**: 0.73 seconds
**Framework**: pytest with mock LLM providers

**Phase 2 Test Status**: Unit tests pending (blocked by bug investigation)

---

## Reliability

- **Retries**: tenacity with exponential backoff on all LLM calls
- **Validation**: Pydantic schemas for all structured outputs
- **Caching**: Company research cached 7 days in MongoDB
- **Error handling**: Errors accumulated in state, non-fatal where possible
