# Job Intelligence Pipeline - Architecture

**Last Updated**: 2025-12-08 | **Status**: 7 layers + frontend complete, API integrations & CV styling enhanced

---

## System Overview

Python LangGraph pipeline processing job postings from MongoDB to generate hyper-personalized CVs, cover letters, and outreach packages. Grounded in master CV to prevent hallucination.

```
Vercel Frontend ──► VPS Runner Service ──► MongoDB Atlas
(Flask/HTMX)       (FastAPI)              (level-2 jobs,
                   │                       company_cache)
                   ├──► PDF Service
                   │    (Playwright/Chrome)
                   │
                   └──► LangGraph Pipeline
                        (10 nodes, 7 layers)
```

---

## Execution Surfaces

| Surface | Location | Use Case |
|---------|----------|----------|
| **CLI** | `scripts/run_pipeline.py` | Direct pipeline execution |
| **Runner** | `runner_service/app.py` | FastAPI wrapper, JWT auth, log streaming |
| **Frontend** | `frontend/app.py` | Job browsing, CV editing, health indicators |

---

## Pipeline Layers (10 Nodes Total)

### Layer 1.4: JD Extractor (Completed 2025-11-30)
- Extracts structured job data: role, category, keywords
- Input: Job description | Output: Structured JD analysis
- Used by: CV Gen V2 for role-aware tailoring

### Layer 2: Pain Point Miner
- Extracts 5-10 pain points, strategic needs, success metrics
- Pydantic validation, JSON-only output
- Retries with exponential backoff

### Layer 2.5: STAR Selector (Optional)
- Selects 2-3 relevant achievements from knowledge-base.md
- Disabled by default (`ENABLE_STAR_SELECTOR=false`)

### Layer 3 & 3.5: Company & Role Research

**Company Research** (Layer 3):
- **Direct Employers**: FireCrawl queries → cached in MongoDB (7-day TTL)
  - Sources: Official site, LinkedIn, Crunchbase, news
  - Full research for company signals and culture fit
- **Recruitment Agencies** (NEW - 2025-12-08):
  - Company type detection: Heuristic keywords + LLM fallback
  - Skips deep research (no LinkedIn, Crunchbase, news scraping)
  - Returns basic summary with empty signals list
  - Sets `company_type: "recruitment_agency"` in response
  - Keywords detected: "recruitment", "staffing", "talent", "headhunter", "agency", "employment", "placement"

**Role Research** (Layer 3.5):
- **Direct Employers**: Summary, business impact, "why now" timing
- **Recruitment Agencies** (NEW):
  - Skips processing entirely (client company unknown)
  - Returns `role_research: None`
  - Signals downstream layers to adapt behavior

### Layer 4: Opportunity Mapper
- Fit scoring (0-100) with rationale
- Validates against job requirements
- **Recruitment Agencies** (NEW - 2025-12-08):
  - Adds contextual note to fit_rationale: "This is a recruitment agency position..."
  - Scoring based on job requirements only (no company signals considered)
  - Prevents culture fit assessment (client company unknown)

### Layer 5: People Mapper
- **Direct Employers**:
  - **FireCrawl Enabled** (default disabled): SEO-style LinkedIn queries + top-4 contact filtering
    - Scoring: Authority > Role relevance > Engagement recency > Accessibility
    - Cost impact: 80% reduction in API calls (4 vs 20 contacts)
  - **FireCrawl Disabled**: Synthetic contacts (4 primary + 4 secondary)
- **Recruitment Agencies** (NEW - 2025-12-08):
  - Limited contact count: 2 recruiter contacts maximum (vs 6+6 for employers)
  - Synthetic recruiter-specific contact generation
  - Reduces LLM calls and outreach cost
  - Method: `_generate_agency_recruiter_contacts()`
- Outreach: LinkedIn messages (150-550 chars), email (95-205 word body)

### Layer 6: Generator & LinkedIn Outreach

**Cover Letter Generation**:
- **Direct Employers**: Full cover letter (220-380 words) with company signals
  - Focus: Company research, culture fit, specific pain points
  - File: `src/layer6/cover_letter_generator.py`
- **Recruitment Agencies** (NEW - 2025-12-08): Recruiter-specific format (150-250 words)
  - Focus: Skills match and availability (not company signals)
  - Tone: Direct and professional
  - Message structure: Greeting → Skills match → Availability → CTA → Signature
  - File: `src/layer6/recruiter_cover_letter.py`
  - Routing: `CoverLetterGenerator` checks `company_type` to select appropriate generator

**CV Styling & Display** (Updated - 2025-12-08):

**Name & Contact Formatting**:
- Name: Uppercase rendering "TAIMOOR ALAM"
- Contact separators: Dot format (·) instead of emoji
- Contact line: `Email · Phone · LinkedIn · GitHub`

**Role Tagline** (NEW):
- H3 format: `{JD Title} · {Generic Title}`
- Example: "Principal Engineer · Staff Architect"
- Helper method: `_get_generic_title()` maps role categories to generic titles
- Auto-inserted after contact line

**Small Caps Option** (NEW - Frontend):
- Toggle button in CV editor toolbar
- Applies `font-variant: small-caps` to headings
- Persistent across editor sessions

**CV Generation - Variant-Based Selection** (Completed - 2025-12-06):

```
JD Keywords + Pain Points
        │
        ▼
┌──────────────────────────┐
│ VariantSelector (NEW)    │  Weighted Algorithm:
│ (variant_selector.py)    │  40% keyword overlap
│                          │  30% pain point alignment
│ ZERO LLM CALLS           │  20% role category match
│ (algorithmic only)       │  10% achievement keywords
└──────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│ RoleGenerator Integration        │  Production Method:
│ generate_with_variant_fallback() │  1. Try variant selection
│ (role_generator.py)              │  2. If no variants, LLM fallback
└──────────────────────────────────┘
        │
        ▼
Final CV: 100% pre-written, interview-defensible, no hallucinations
```

**Architecture Components**:

1. **VariantParser** (`src/layer6_v2/variant_parser.py`)
   - Parses role files with variant structure
   - Supports: Technical, Architecture, Impact, Leadership, Short variants
   - Backward compatible with legacy format
   - 35 unit tests passing

2. **VariantSelector** (`src/layer6_v2/variant_selector.py`)
   - Weighted scoring algorithm for optimal variant selection
   - Zero LLM calls (pure algorithm)
   - Per-role variant preference configuration
   - 20 unit tests passing

3. **CVLoader Integration** (`src/layer6_v2/cv_loader.py`)
   - Supports `enhanced_data` with variants
   - Properties: `has_variants`, `variant_count`, `get_achievement_variants()`
   - Graceful fallback to legacy format
   - 21 unit tests passing

4. **RoleGenerator Integration** (`src/layer6_v2/role_generator.py`)
   - `generate_from_variants()` - Zero-hallucination selection
   - `generate_with_variant_fallback()` - LLM backup (production method)
   - `generate_all_roles_from_variants()` - Batch processing
   - 9 unit tests passing

**Data Format** (2025-12-06):
- All 6 role files in `data/master-cv/roles/` converted to enhanced format
- 189 total variants across all roles
- Updated `role_metadata.json` with variant counts and selection guides

**Benefits**:
- Zero hallucination (all text pre-written)
- Faster generation (no LLM calls for selection)
- Deterministic output (same inputs → same outputs)
- ATS optimized (keywords pre-embedded)
- Interview ready (provenance tracking)

**Legacy LinkedIn Outreach**:
- Connection request: 300 char hard limit (LinkedIn enforces)
- InMail: 1900 char body, 200 char subject
- **Character Limit Enforcement** (2025-11-30):
  1. Prompt guardrail: "Output ONLY plain text, strictly <300 characters"
  2. Output validation: `len(message) <= 300` with retry
  3. UI counter: Real-time "X/300" display with color warnings
  4. API validation: Reject > 300 chars
- Signature: "Best. Taimoor Alam" (MANDATORY)

### Layer 7: Publisher
- Generates dossier via `dossier_generator.py`
- Updates MongoDB `level-2` with results
- **DEPRECATED**: Local file storage (being replaced with PDF export API)

---

## Data Model

**JobState** (`src/common/state.py`):
```python
class JobState(TypedDict):
    # Input
    job_id: str
    title: str
    company: str
    job_description: str
    candidate_profile: str  # master-cv.md

    # Layer outputs
    pain_points: List[str]
    company_research: Dict
    company_type: str  # "employer" | "recruitment_agency" | "unknown" (NEW - 2025-12-08)
    fit_score: int
    primary_contacts: List[Dict]
    cv_path: str
    cover_letter: str

    # Token tracking
    token_usage: Dict
    total_cost_usd: float

    # Errors
    errors: List[str]
```

**MongoDB Collections**:
| Collection | Purpose | TTL |
|------------|---------|-----|
| `level-2` | Jobs + pipeline results | None |
| `company_cache` | Cached research | 7 days |
| `star_records` | STAR achievements | None |

---

## Configuration & Safety

### Feature Flags (`src/common/config.py`)
- `ENABLE_STAR_SELECTOR`: Use STAR selection (default: false)
- `DISABLE_FIRECRAWL_OUTREACH`: Use synthetic contacts (default: true)
- `ENABLE_REMOTE_PUBLISHING`: Upload to Google Drive/Sheets (default: false)
- `ENABLE_RATE_LIMITING`: Enforce rate limits (default: true)
- `ENABLE_ALERTING`: Send alerts to Slack (default: true)

### Budget & Rate Limiting (Completed 2025-11-30)
- **Token Budget**: Per-provider caps (OpenAI, Anthropic, FireCrawl)
- **RateLimiter**: Sliding window algorithm, per-minute + daily limits
- **Circuit Breaker**: 3-state pattern for external services
- **Config**: `OPENAI_RATE_LIMIT_PER_MIN=350`, `FIRECRAWL_DAILY_LIMIT=600`

### Observability (Completed 2025-11-30)
- **Structured Logging**: LayerContext in all 10 nodes (layer_start/layer_complete events)
- **Metrics Dashboard**: Token usage, rate limits, health status, budget tracking
- **Error Alerting**: AlertManager + ConsoleNotifier/SlackNotifier with 5-min dedup window
- **Health Status**: Service health aggregation with capacity metrics

---

## External Services

| Service | Layer | Purpose |
|---------|-------|---------|
| **OpenAI** | 2-5 | General LLM calls |
| **Anthropic** | 6 | CV generation (default) |
| **FireCrawl** | 3, 5 | Web scraping, contact discovery |
| **Google Drive** | 7 | Optional output storage |
| **Google Sheets** | 7 | Optional tracking |
| **FireCrawl Credits API** | 5 | Real-time token usage tracking (NEW 2025-12-08) |
| **OpenRouter Credits API** | Dashboard | Credit balance monitoring (NEW 2025-12-08) |

### API Integration Details (NEW - 2025-12-08)

**FireCrawl Token Usage**:
- Endpoint: `GET /firecrawl/credits` (runner service)
- Calls: `GET https://api.firecrawl.dev/v1/team/token-usage`
- Returns: Used credits, remaining, daily limit
- Fallback: Local rate limiter if API unavailable
- Config: `FIRECRAWL_API_KEY` env variable

**OpenRouter Credits**:
- Endpoint: `GET /openrouter/credits` (runner service)
- Calls: OpenRouter REST API
- Returns: Remaining credits, reset date
- Frontend proxy: `/api/openrouter/credits` (CORS handling)
- Config: `OPENROUTER_API_KEY` env variable

---

## Frontend Architecture

### Job Detail Page
- Main content: Cover letter, pain points, contacts
- Side panel: CV editor (TipTap, Phase 1-5 complete)
- Buttons: Process, Export PDF, Edit CV
- Auto-refresh: Health status, metrics, application stats
- **Company Type Badge** (NEW - 2025-12-08):
  - Displays in Quick Info Bar (top right)
  - Purple badge: "Agency" for recruitment agencies
  - Blue badge: "Direct" for direct employers
  - Helps users quickly identify agency vs direct roles

### Dashboard
- Application stats: Today/week/month/total counts
- Budget monitor: Progress bars, per-provider usage, thresholds
- Service health: Overall status + capacity metrics
- Alert history: Recent errors/warnings with dedup

---

## CV Rich Text Editor (Phases 1-6 Complete, Enhanced 2025-12-08)

**Technology**: TipTap v2 (ProseMirror), 60+ Google Fonts, Playwright PDF

**Data Flow**:
```
Pipeline (Markdown) ──► MongoDB cv_text
                          │ (auto-migrate on first access)
                          ▼
                       TipTap Editor (cv_editor_state)
                          │ (3s debounce auto-save)
                          ▼
                       PDF Export (Playwright/Runner Service)
```

**API Endpoints**:
- `GET /api/jobs/<id>/cv-editor` - Fetch editor state or migrate markdown
- `PUT /api/jobs/<id>/cv-editor` - Save editor state
- `POST /api/jobs/<id>/cv-editor/pdf` - Generate PDF (frontend proxy to runner)

**PDF Generation** (Phase 6 - Separated Service):
- Dedicated Docker container with Playwright/Chromium
- Endpoints: `/health`, `/render-pdf`, `/cv-to-pdf`
- HTML to PDF via Playwright with embedded fonts, margin validation (defense-in-depth)
- Error handling: 400 (invalid state), 500 (rendering failed), 503 (service unavailable)

**Enhanced Features** (2025-12-08):
- Name displays in uppercase styling
- Role tagline added as H3 below contact info
- Contact info uses dot separators (no emoji)
- Small caps toggle button in toolbar
- Consistent styling between editor and generated output

---

## CV Generation V2 - Architecture & Critical Fixes (P0)

> **Analysis Reports**:
> - `reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`
> - `reports/debugging/2025-11-30-cv-hallucination-root-cause-analysis.md`

### Current Architecture (Flawed)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CV GENERATION V2 PIPELINE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 1: CV Loader (cv_loader.py)                                     │
│  ├── Loads: data/master-cv/role_metadata.json                          │
│  ├── Loads: data/master-cv/roles/*.md                                  │
│  ├── Parses: achievements per role                                     │
│  └── ⚠️ DOES NOT EXTRACT: hard_skills, soft_skills sections           │
│                                                                          │
│  Phase 5: Header Generator (header_generator.py)                       │
│  ├── Generates: Profile summary (LLM-based)                            │
│  └── ⚠️ CRITICAL BUG: Core Competencies use HARDCODED skill lists     │
│      ├── Line 200-226: Includes PHP, Java, Spring Boot - NOT in CV!   │
│      └── Line 495: Always ["Leadership", "Technical", "Platform",     │
│                            "Delivery"] - NOT JD-derived               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Required Architecture (Fixed)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 CV GENERATION V2 - FIXED ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  JD Keywords + Master-CV Skills                                        │
│        │                                                                │
│        ▼                                                                │
│  ┌──────────────────────────┐                                          │
│  │ LLM Category Generator   │  NEW: Dynamic categories from JD         │
│  │ (category_generator.py)  │  Input: JD keywords + master-CV skills   │
│  │                          │  Output: 3-4 JD-specific category names  │
│  └──────────────────────────┘                                          │
│        │                                                                │
│        ▼                                                                │
│  ┌──────────────────────────┐                                          │
│  │ Skill Matcher            │  NEW: Grounded in master-CV ONLY         │
│  │ (skill_validator.py)     │  1. Extract skills FROM master-CV roles  │
│  │                          │  2. Match against JD requirements        │
│  │                          │  3. REJECT any skill not in master-CV    │
│  └──────────────────────────┘                                          │
│        │                                                                │
│        ▼                                                                │
│  ┌──────────────────────────┐                                          │
│  │ Evidence Validator       │  NEW: STAR format enforcement            │
│  │ (role_qa.py - enhanced)  │  Bullets MUST mention skills explicitly  │
│  │                          │  Format: Challenge → Skill → Result      │
│  └──────────────────────────┘                                          │
│        │                                                                │
│        ▼                                                                │
│  Final CV (100% grounded, JD-aligned, no hallucinations)              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Master-CV Skill Extraction (Required)

**Source Files**: `data/master-cv/roles/*.md`

Each role file has a `## Skills` section that MUST be extracted:

```markdown
## Skills

**Hard Skills**: domain-driven-design, architecture, nodejs, lambda, s3, aws...
**Soft Skills**: technical leadership, mentoring, SCRUM, hiring & interviewing...
```

**Implementation**:
1. Modify `RoleData` in `cv_loader.py` to include:
   - `hard_skills: List[str]`
   - `soft_skills: List[str]`
2. Parse skills from markdown using regex or structure detection
3. Aggregate all skills across roles for whitelist

### Dynamic Skill Categories (Required)

**Before** (broken):
```
Leadership: Leadership, Team Leadership
Technical: Python, Java, PHP, TypeScript, ...
Platform: AWS, GCP, Azure, ...
Delivery: Agile, Scrum, Kanban, ...
```

**After** (JD-aligned):
```
Cloud Platform Engineering: AWS, Lambda, Terraform, EKS
Backend Architecture: Python, Microservices, Event-Driven
Technical Leadership: Team Leadership, Mentoring, DDD
Agile Delivery: Scrum, CI/CD, Release Management
```

### STAR Format Enforcement (Required)

**Template** (add to `role_generation.py` prompts):
```
Each bullet MUST follow STAR format:
- [SITUATION] Start with challenge indicator: "Facing...", "To address...", "Despite..."
- [TASK] What needed to be done
- [ACTION] HOW it was done - MUST explicitly mention hard OR soft skill
- [RESULT] Quantified impact with metrics

Example:
"Facing 30% annual outage increase in monolithic system, led 12-month migration
to event-driven microservices using AWS Lambda and EventBridge, achieving 75%
incident reduction and zero downtime for 3 years."
```

### Dynamic Location Tagline (Required)

**Trigger Countries**: Saudi Arabia, UAE, Kuwait, Qatar, Oman, Pakistan

**Tagline**: `"International Relocation in 2 months"`

**Location in CV**: After contact line, before Profile section

**Implementation**: `orchestrator.py:_assemble_cv_text()`

### Design System Updates (Required)

**Color Change**:
- Current: Teal/green `#0f766e`
- New: Dark greyish blue `#475569` (Tailwind slate-600)

**Spacing**: Reduce margins/padding by 20%

**Consistency**: Detail page must match editor styling

**Phase 5.1: Page Breaks** (Completed 2025-11-28):
- Visual page break indicators in editor
- CSS-based margin rendering (WYSIWYG)
- Iterative stack-based TipTap-to-HTML conversion (no recursion limits)

**Bugs Fixed** (Nov 2025):
- Line spacing CSS cascading (child elements now use `line-height: inherit`)
- Markdown asterisk rendering (TipTap JSON instead of markdown)
- PDF service unavailable (Docker Compose + CI/CD fixed)
- Process button (showToast function added)

---

## Testing & Observability

**Unit Tests**: 708 passing (config validation, rate limiting, circuit breaker, metrics, pipeline nodes)
**E2E Tests**: 48 Playwright tests exist but disabled (config issues; see `plans/e2e-testing-implementation.md`)
**Integration Tests**: Not in GitHub Actions CI yet
**Code Coverage**: Not tracked yet

**Completed Observability**:
- Layer-level structured logging (all 10 nodes)
- Metrics collection (token usage, rate limits, health)
- Budget monitoring (progress bars, thresholds, alerts)
- Error alerting (Slack + console notifiers)
- Service health dashboard

---

## Known Issues & Gaps

| Issue | Priority | Status | Effort |
|-------|----------|--------|--------|
| Time-based filters bug (1h/3h filters return all-day) | HIGH | OPEN | 2-3h |
| CV markdown asterisks in output | HIGH | OPEN | 2h |
| CV editor not synced with detail page | HIGH | OPEN | 2-3h |
| VPS backup strategy (no artifact backups) | CRITICAL | OPEN | 20-30h |
| Credential backup vault (API keys not backed up) | CRITICAL | OPEN | 4-6h |
| E2E tests disabled | MEDIUM | PENDING | TBD |
| Integration tests in CI/CD | MEDIUM | PENDING | TBD |
| Database backup testing | HIGH | PENDING | 3-4h |

---

## Deployment

**Production**: VPS at 72.61.92.76:8000 (FastAPI runner service)
**Frontend**: Vercel (Flask app proxies to runner)
**Database**: MongoDB Atlas (PITR enabled but not tested)
**PDF Service**: Docker container on VPS, internal network

---

## Next Priorities

1. Fix time-based filters bug (affects all users)
2. Sanitize markdown from CV generation (affects every CV)
3. Implement S3 backup strategy (production blocker)
4. Test MongoDB backup restoration
5. Re-enable and fix E2E tests
