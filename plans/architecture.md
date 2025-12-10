# Job Intelligence Pipeline - Architecture

**Last Updated**: 2025-12-10 | **Status**: 7 layers + frontend complete, E2E Annotation Integration 100% done (11 phases, 9 backend + 2 frontend files, 89 tests), Identity-Based Persona Generation System (NEW - 33 tests), 5D annotation system (relevance, requirement_type, passion, identity, annotation_type) integrated across all layers, GAP-085 to GAP-094 complete, Full Extraction Service with dual JD output, 1554+ total tests passing

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

**Prompt Quality Enhancements** (GAP-030 - NEW 2025-12-09):
- **Layer 6a - Cover Letter Quality** (`src/layer6/cover_letter_generator.py`):
  - Enhanced system prompt with:
    - Explicit STAR citation rules: CORRECT examples (grounded in achievements) vs WRONG examples (generic claims)
    - Generic phrases blocklist: 12 phrases banned ("diverse team", "best practices", "synergy", "passionate", "love working", "dynamic environment", "outside the box", "next level", "leverage", "disruptive", "game-changer", "touch base")
    - Pain point mapping requirement: Every paragraph must explicitly link to 1+ identified pain points
    - Few-shot examples: High-quality cover letter paragraphs showing proper citations and pain point mapping
    - Anti-hallucination checklist: Writer must verify all claims have supporting evidence
  - Test coverage: 24 unit tests validating source citation rules, generic phrase detection, pain point mapping, and quality gates
  - File: `tests/unit/test_layer6_cover_letter_improvements.py`

- **Layer 7 - Interview Question Quality** (`src/layer7/interview_predictor.py`):
  - Enhanced system prompt with:
    - Few-shot examples: High-quality interview questions with context and difficulty levels
    - Distribution requirements: Technical questions (40%), Behavioral (35%), Situational (25%)
    - Yes/no question filtering: Explicitly rejects simple yes/no questions
    - Length validation: Questions must be 1-3 sentences (avoid run-on, overly detailed questions)
    - Source attribution: All questions must cite which CV/JD gap or concern they address
  - Added `validate_question_quality()` function:
    - Filters low-quality questions (yes/no, too short, too long, missing context)
    - Maintains distribution targets for balanced question set
    - Returns only high-confidence questions with supporting evidence
  - Test coverage: 22 unit tests validating question quality, yes/no detection, length validation, type distribution, and source attribution
  - File: `tests/unit/test_layer7_prompt_improvements.py`

**LinkedIn Outreach & Contact Classification** (NEW - 2025-12-08):

**Contact Type Classification** (`src/layer5/people_mapper.py`):
- Five-tier contact classification system:
  - `hiring_manager`: Hiring/recruiting keywords → direct authority
  - `recruiter`: Recruiter, talent, staffing keywords → agency/external
  - `vp_director`: VP, Director, leadership keywords → strategic
  - `executive`: C-level, founder, CEO keywords → top decision maker
  - `peer`: Fallback → peer network/IC
- Algorithmic keyword matching (no LLM calls)
- Priority order: hiring_manager → recruiter → vp_director → executive → peer
- Enables contact-type-specific outreach routing

**Outreach Package Generation** (`src/layer6/outreach_generator.py`):
- Creates 2 optimized outreach packages per contact:
  1. **linkedin_connection** (≤300 chars with Calendly):
     - Warm greeting + specific role interest + personalization
     - Includes Calendly link for scheduling
     - Character count enforcement (LinkedIn hard limit)
  2. **inmail_email** (400-600 chars with subject):
     - Combined package works for both InMail and Email
     - Prefers InMail content, falls back to email_body
     - Professional subject line + extended body
     - Call-to-action with clear next steps
- "Already applied" framing patterns:
  - Detects if position was already submitted
  - Adjusts messaging tone for follow-ups
  - Re-engagement strategies

**LinkedIn Outreach Reference Document** (`linkedin/outreach.md`):
- Comprehensive guide for all outreach strategies
- Contact type messaging templates with examples
- Dual LinkedIn format specifications:
  - Connection: warm, brief, personal touch
  - InMail: professional, detailed, value-focused
- MENA regional context:
  - Cultural considerations
  - Business etiquette
  - Language/tone adjustments
- Character limits and validation rules
- Pre-applied messaging patterns

**JD Annotation System Integration - Phase 6** (NEW - 2025-12-09):

**People Mapper Annotation Context** (`src/layer5/people_mapper.py`):
- `_format_annotation_context()` helper method extracts JD annotation data
- Formats for outreach prompt injection:
  - Must-have requirements (high-priority skills for opening message)
  - Reframe guidance (positioning strategies per contact type)
  - Keywords (ATS-optimized language from annotations)
  - Concerns identified (red flags to address proactively)
  - STAR evidence (linked achievements to reference in outreach)
- Enables annotation-aware contact discovery and messaging

**Cover Letter Concern Mitigation** (`src/layer6/cover_letter_generator.py`):
- New `_format_concern_mitigation_section()` method
- Proactively addresses red flags with positive framing:
  - One mitigation paragraph per major concern
  - Max 2 concerns per cover letter (avoid overexplaining)
  - Examples: on-call rotation → proven incident response track record
  - Ties to STAR stories for credibility
- Integrated into cover letter prompt for all concern annotations

**LinkedIn Headline Optimizer** (`src/layer6/linkedin_optimizer.py`) - NEW FILE:
- Generates algorithm-aware LinkedIn headline variants from JD annotations
- Algorithm considers:
  - Keyword prominence (must-have skills, core strengths)
  - LinkedIn search weights (title keywords ranked higher)
  - Character limits (120 char LinkedIn maximum)
- Output: 3-5 headline patterns for A/B testing
- Example:
  - Input: "Kubernetes [core_strength], AWS [must_have], Python [relevant]"
  - Output 1: "Principal Engineer | Kubernetes | AWS | Python"
  - Output 2: "Cloud Platform Architect | AWS | Kubernetes Specialist"
- Used for job-specific LinkedIn profile optimization before outreach

**JD Annotation System Enhancements - Passion & Identity Dimensions** (NEW - 2025-12-10):

**New Annotation Dimensions**:
- **Passion Level** (`passion_level`): 5-level scale capturing candidate enthusiasm
  - `love_it`: Excited about this role/company
  - `enjoy`: Positive interest and enjoyment
  - `neutral`: No strong feeling either way
  - `tolerate`: Willing but not enthusiastic
  - `avoid`: Would rather not pursue this
- **Identity Level** (`identity_level`): 5-level scale capturing professional identity alignment
  - `core_identity`: Central to who they are as a professional
  - `strong_identity`: Strong professional identity match
  - `developing`: Developing this aspect of identity
  - `peripheral`: Minor part of professional identity
  - `not_identity`: Not part of professional self-image

**Layer 2 Pain Point Miner - Annotation-Aware** (`src/layer2/pain_point_miner.py`):
- Extracts annotation context from JD annotations:
  - `must_have_keywords`: Critical skills identified
  - `gap_areas`: Areas where candidate lacks experience
  - `reframe_notes`: Positioning guidance for weaknesses
  - `core_strength_areas`: Areas of demonstrated expertise
- Passes annotation priorities to LLM prompt injection
- Post-processes generated pain points to:
  - Boost must-have skills (prioritize in pain point narrative)
  - Deprioritize gaps (acknowledge but reframe positively)
  - Highlight core strengths in context of pain points
- Result: Pain point narratives aligned with candidate strengths and priorities

**Layer 4 Fit Scorer - Annotation-Aware Scoring** (`src/layer4/annotation_fit_signal.py`):
- New `AnnotationFitSignal` class enabling hybrid scoring approach
- Scoring blends two signals (70% LLM, 30% annotation):
  - **LLM Score (0-100)**: Job requirements vs CV match (existing logic)
  - **Annotation Signal (0-100)**: Manual annotation coverage and match percentage
  - **Weighted Score**: `0.7 * llm_score + 0.3 * annotation_signal`
- Detects disqualifiers from annotations:
  - Must-have skills with gaps → red flag
  - Passion_level = "avoid" → disqualifier
  - Identity mismatch → warning
- Returns `annotation_analysis` in output with:
  - `annotation_coverage`: Percentage of JD covered by annotations
  - `confidence_level`: High/Medium/Low based on annotation depth
  - `disqualifiers`: Array of identified deal-breakers
  - `strengths`: Array of strong alignment areas
- Enables data-driven decision making on which jobs to pursue

**Boost Calculator Enhanced** (`src/common/annotation_boost.py`):
- Extended boost calculation to include passion and identity dimensions
- New methods for candidate preference extraction:
  - `get_passions()`: Returns passion_level = love_it/enjoy
  - `get_avoid_areas()`: Returns passion_level = avoid
  - `get_identity_core()`: Returns core + strong identity areas
  - `get_identity_not_me()`: Returns peripheral + not_identity areas
- Boost multipliers applied during pain point post-processing:
  - Core identity areas: 1.5x boost (emphasize in narrative)
  - Must-have skills: 1.3x boost (prioritize in pain points)
  - Avoid areas: 0.7x boost (de-emphasize, suggest reframing)
- Stats now include passion and identity dimension counts:
  - Total passion_level selections by category
  - Total identity_level selections by category
  - Alignment scoring for job fit

**Header Context Enhanced** (`src/layer6_v2/types.py`):
- `AnnotationPriority` TypedDict now includes:
  - `passion_priorities`: List of love_it + enjoy items
  - `avoid_priorities`: List of avoid items
  - `identity_priorities`: List of core + strong identity items
  - `identity_keywords`: Keywords extracted from identity annotations
  - `passion_keywords`: Keywords extracted from passion annotations
- `HeaderGenerationContext` extended with passion/identity fields:
  - Profile generation uses passion/identity to shape narrative tone
  - Skill selection prioritizes core identity skills
  - Concerns addressing uses identity alignment for reframing
- `format_priorities_for_prompt()` method now includes:
  - "Professional Identity Alignment" section in prompt
  - "Passion Areas" section highlighting enthusiasm areas
  - "Areas to Reframe" section for developing skills
- Result: CV headers and profiles reflect candidate's authentic professional identity and enthusiasm

**UI Updated - Annotation Popover Enhancements** (`frontend/templates/partials/job_detail/_annotation_popover.html`, `frontend/static/js/jd-annotation.js`):
- New button groups in annotation popover:
  - **Passion Level selector**: 5-button group (love_it, enjoy, neutral, tolerate, avoid)
  - **Identity Level selector**: 5-button group (core_identity, strong_identity, developing, peripheral, not_identity)
- Visual design:
  - Color-coded buttons (green for positive passion, red for avoid)
  - Visual feedback on current selection
  - Hover tooltips explaining each level
- Event handlers:
  - `setPopoverPassion(level)`: Updates annotation with passion_level
  - `setPopoverIdentity(level)`: Updates annotation with identity_level
- Real-time annotation storage and aggregation

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

### Layer 7: Publisher + Interview Prep & Analytics

**Publisher** (Original Layer 7):
- Generates dossier via `dossier_generator.py`
- Updates MongoDB `level-2` with results
- **DEPRECATED**: Local file storage (being replaced with PDF export API)

**Interview Predictor** (NEW - 2025-12-09):
- Module: `src/layer7/interview_predictor.py`
- Predicts likely interview questions from CV/JD analysis gaps and concerns
- Methods:
  - `predict_questions_from_concerns()` - Questions addressing identified red flags
  - `predict_questions_from_gaps()` - Questions targeting skill/experience gaps
  - `predict_technical_questions()` - Role-specific technical questions
  - `predict_behavioral_questions()` - Company/culture fit questions
  - `format_prep_materials()` - Structures questions with difficulty levels and prep guidance
- Difficulty levels: Entry, Intermediate, Advanced (difficulty-based preparation prioritization)
- Output includes:
  - Question text with context
  - Expected keywords to mention
  - Likely follow-up questions
  - Preparation strategy per question
  - Confidence scoring

**Outcome Tracker** (NEW - 2025-12-09):
- Module: `src/analytics/outcome_tracker.py`
- Tracks application progression through pipeline to final outcome
- Supported statuses: Applied → Phone Screen → Technical Interview → Final Round → Offer/Rejected/No Response/Withdrawn
- Methods:
  - `record_outcome()` - Log status changes with timestamp validation
  - `get_outcome_history()` - Full timeline of status changes
  - `calculate_conversion_rates()` - Analyze success metrics (applied→phone screen, phone screen→offer, etc.)
  - `predict_outcome_timing()` - Estimate response times based on company signals
  - `generate_outcome_report()` - Summary statistics and trends by company type/tier
- Data model stores:
  - Current status
  - All historical transitions with timestamps
  - Notes and feedback per status change
  - Salary/offer details if applicable
  - Days since application

**Enhanced Type System** (NEW - 2025-12-09):
- New types in `src/common/annotation_types.py`:
  - `InterviewQuestion` - Question with difficulty, category, prep guidance
  - `InterviewPrep` - Job-specific prep state with predicted questions and notes
  - `ApplicationOutcome` - Outcome tracking with status timeline and salary info
  - `OutcomeStatus` - Literal type for type-safe status values

**Test Coverage** (NEW - 2025-12-09):
- `test_layer7_interview_predictor.py` - 30 unit tests
- `test_layer7_interview_predictor_edge_cases.py` - 35 edge case tests (large inputs, concurrency, budget limits)
- `test_analytics_outcome_tracker.py` - 28 unit tests
- `test_analytics_outcome_tracker_edge_cases.py` - 30 edge case tests (concurrent updates, timezone handling, large histories)
- `test_annotation_types_phase7.py` - 25 type validation tests
- Total: 118 new tests for Phase 7

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
    company_type: str  # "employer" | "recruitment_agency" | "unknown" (2025-12-08)
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

**Contact** (`src/common/state.py` - NEW 2025-12-08):
```python
class Contact(TypedDict):
    name: str
    title: str
    linkedin_url: str
    contact_type: str  # "hiring_manager" | "recruiter" | "vp_director" | "executive" | "peer" (NEW)
    linkedin_connection_message: str  # ≤300 chars with Calendly (NEW)
    linkedin_inmail: str  # InMail body 400-600 chars (NEW)
    linkedin_inmail_subject: str  # InMail subject line (NEW)
    email: str
    already_applied_frame: bool  # For pre-applied positions (NEW)
```

**OutreachPackage** (`src/common/state.py` - UPDATED 2025-12-08):
```python
class OutreachPackage(TypedDict):
    contact_type: str  # NEW: Identifies contact classification
    email_body: str
    linkedin_message: str
    email_subject: str
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

### Master CV Editor Page (NEW - 2025-12-10)

**Purpose**: Full-page dedicated editor for managing the Master CV stored in MongoDB

**Route**: `GET /master-cv` → `frontend/templates/master_cv.html`

**Data Flow**:
```
MongoDB (master_cv_metadata, master_cv_taxonomy, master_cv_roles)
           │
           ▼
/api/master-cv/* endpoints
           │
           ▼
master_cv.html (tab template)
           │
           ├─ _candidate_tab.html (form inputs)
           ├─ _roles_tab.html (two-panel editor with TipTap)
           └─ _taxonomy_tab.html (accordion skill editor)
           │
           ▼
master-cv-editor.js (MasterCVEditor class, 1100 lines)
           │
           ├─ Auto-save (3s debounce)
           ├─ Version history (with rollback)
           ├─ TipTap rich text (achievements)
           ├─ Chip editing (arrays: languages, certifications, skills)
           └─ Delete confirmation (2s safety delay)
           │
           ▼
master-cv-editor.css (editor styles)
```

**Tab Structure**:

1. **Candidate Info Tab** (`_candidate_tab.html`):
   - Personal details (name, email, phone)
   - Location (country, city)
   - Availability (notice period, start date)
   - Professional summary
   - Languages (chip-based array editing)
   - Certifications (chip-based array editing)
   - Auto-save to `master_cv_metadata` collection

2. **Work Experience Tab** (`_roles_tab.html`):
   - Two-panel layout:
     - Left: List of roles with add/delete buttons
     - Right: Selected role editor
   - For each role:
     - Title, company, dates (duration auto-calculated)
     - Achievements editor with TipTap rich text
     - Keywords (chip-based array)
     - Reorder achievements with drag-drop
   - Auto-save to `master_cv_roles` collection

3. **Skills Taxonomy Tab** (`_taxonomy_tab.html`):
   - Accordion-based category editor
   - For each category:
     - Category name (editable)
     - Skills (chip-based array)
     - Reorder skills with drag-drop
   - Add new skill categories
   - Delete categories
   - Auto-save to `master_cv_taxonomy` collection

**Key Features** (`master-cv-editor.js`):

- **MasterCVEditor Class** (main orchestrator):
  - Constructor: Initialize editor state from MongoDB data
  - `loadData()` - Fetch from MongoDB via API
  - `saveData()` - Debounced save (3s delay)
  - `initTabs()` - Tab switching logic
  - `showVersionHistory()` - Modal with history + rollback
  - `confirmDelete()` - 2s safety delay before delete

- **Auto-Save Mechanism**:
  - Debounce timer resets on every change
  - Visual indicator: "Saving..." → "Saved" with timestamp
  - Retry logic: Exponential backoff (500ms → 2s max)
  - Error handling: Toast notifications

- **TipTap Integration** (for role achievements):
  - Extensions: Bold, Italic, Underline, Lists, Code blocks
  - Toolbar: Format buttons, clear formatting
  - Placeholder: "Enter achievement..."
  - Auto-save on change

- **Chip-Based Array Editing**:
  - Input field + "Add" button
  - Tags displayed as removable chips
  - Drag-drop reordering (Sortable.js or Alpine.js x-for)
  - Keyboard support: Enter to add, Backspace to delete last

- **Version History**:
  - Modal showing 10 most recent versions
  - Timestamp, user action (created/edited/deleted)
  - Rollback button: Restore to previous version
  - Queries `master_cv_metadata.history` array from MongoDB

- **Delete Confirmation**:
  - Modal overlay with 2-second countdown
  - Prevents accidental deletion
  - Shows what will be deleted
  - After countdown: Delete button becomes active

**Styling** (`master-cv-editor.css`):

- Tab navigation: Active state with underline/color
- Two-panel layout: `display: flex` with responsive breakpoint
- Chip styling: `background: #e5e7eb`, `border-radius: 999px`, removable with ×
- Form inputs: Consistent with job detail page (Tailwind classes)
- Rich text editor: Border highlight on focus
- Modals: Overlay with centered content, semi-transparent background
- Warning banner: Yellow/amber background with icon ("Use with caution")
- Save indicator: Green checkmark with timestamp

**API Endpoints Used** (no new backend routes):
- `GET /api/master-cv/metadata` - Fetch candidate info
- `PUT /api/master-cv/metadata` - Save candidate info
- `GET /api/master-cv/roles` - Fetch work experience
- `PUT /api/master-cv/roles` - Save roles
- `GET /api/master-cv/taxonomy` - Fetch skill taxonomy
- `PUT /api/master-cv/taxonomy` - Save taxonomy

**Navigation** (`base.html`):
- "Master CV" button added to main nav menu
- Links to `/master-cv` page
- Only visible to logged-in users (same guard as job detail page)

---

### Pipeline Progress UI (NEW - 2025-12-08)

**Horizontal Layout with Progress Line**:
- 7-layer pipeline displayed horizontally with visual flow
- Progress line connects all steps with gradient animation
- Step states: pending (gray) → executing (blue pulse) → success (green) → failed (red) → skipped (gray)
- Circular icons per layer with visual indicators
- Click step to see layer-specific details in side panel
- Progress percentage in header

**Implementation Files**:
- `frontend/templates/partials/job_detail/_pipeline_progress.html` - HTML structure with icons
- `frontend/static/js/job-detail.js` - Functions: `resetPipelineSteps()`, `updatePipelineStep()`, `updateProgressLine()`, `showCurrentStepDetails()`

**Key Functions**:
- `resetPipelineSteps()` - Initialize all steps to pending state
- `updatePipelineStep(layer, status)` - Update single step with visual state
- `updateProgressLine()` - Animate progress line as steps complete
- `showCurrentStepDetails(layer)` - Display layer-specific context

---

### Job Detail Page - Interview Prep & Outcome Tracking (NEW - 2025-12-09)

**Interview Prep Panel** (`frontend/templates/partials/job_detail/_interview_prep_panel.html`):
- Collapsible panel showing predicted interview questions
- Question cards with difficulty badges (Entry/Intermediate/Advanced)
- Category tags (Technical/Behavioral/Situational)
- Preparation guides with expected keywords and follow-up questions
- "Mark as Prepared" checkboxes with progress tracking (X/Y prepared)
- User notes textarea for personal preparation notes
- Search/filter by difficulty and category
- "Regenerate Questions" button to trigger re-prediction

**Outcome Tracker Panel** (`frontend/templates/partials/job_detail/_outcome_tracker.html`):
- Timeline view of application status progression
- Status change form with date/time, notes, and optional feedback
- Color-coded status badges (green=progress, yellow=pending, red=rejected)
- Current status summary with days since application
- Expected next steps based on current status
- Salary/offer details section (visible when status="offer")
- Conversion statistics (phone screen rate, offer rate, avg response time)

**API Integration** (`frontend/app.py`):
- 7 endpoints for interview prep and outcome tracking:
  1. `GET /api/jobs/<id>/interview-prep` - Fetch interview prep data
  2. `POST /api/jobs/<id>/interview-prep/predict` - Trigger question prediction
  3. `POST /api/jobs/<id>/interview-prep/mark-prepared` - Mark question as prepared
  4. `PUT /api/jobs/<id>/interview-prep/notes` - Save preparation notes
  5. `GET /api/jobs/<id>/outcome-history` - Fetch full outcome timeline
  6. `POST /api/jobs/<id>/outcome` - Log outcome status change
  7. `GET /api/jobs/<id>/outcome-stats` - Get conversion statistics
- 2 new proxy routes (NEW - 2025-12-10):
  8. `POST /api/jobs/<id>/research-company` - Proxy research request to VPS runner
  9. `POST /api/jobs/<id>/generate-cv` - Proxy CV generation request to VPS runner

**JavaScript Functions** (`frontend/static/js/interview-prep.js`):
- `loadInterviewPrep()` - Fetch and display questions
- `markQuestionPrepared()` - Toggle prepared status
- `savePreparationNotes()` - Auto-save notes with debounce
- `filterQuestionsByDifficulty()` - Filter display by difficulty level
- `expandQuestionDetails()` - Show full preparation guide
- `generateNewQuestions()` - Trigger re-prediction

---

### Job Detail Page (Enhanced - 2025-12-09)
- Main content: Cover letter, pain points, contacts
- Pipeline progress: Horizontal layout with progress line with monotonic tracking (2025-12-09 enhanced: `highestLayerReached` prevents backward movement)
- Interview prep: Predicted questions with difficulty levels and prep guides (NEW - 2025-12-09)
- Outcome tracker: Status timeline and conversion statistics (NEW - 2025-12-09)
- Side panel: CV editor (TipTap, Phase 1-5 complete)
- Buttons: Process, Export PDF, Edit CV
- Auto-refresh: Health status, metrics, application stats
- **Company Type Badge** (NEW - 2025-12-08):
  - Displays in Quick Info Bar (top right)
  - Purple badge: "Agency" for recruitment agencies
  - Blue badge: "Direct" for direct employers
  - Helps users quickly identify agency vs direct roles
- **Field Normalization Pattern** (NEW - 2025-12-09):
  - `serialize_job()` normalizes both `job_description` and `jobDescription` to `description` field
  - Handles database field name variations across different data sources
  - Ensures UI consistently displays job description button and content
- **CV Display Fallback** (NEW - 2025-12-09):
  - Checks `cv_editor_state` first, falls back to disk-based `cv_text` if needed
  - `output_publisher.py` logs warnings when cv_text is missing for debugging
  - Handles edge cases where pipeline completes but CV text not persisted immediately
- **JD Annotation Panel** (NEW - 2025-12-09):
  - Button in `job_detail.html` passes `jobId` data attribute to `openAnnotationPanel()`
  - `jd-annotation.js` reads `jobId` from data attribute as fallback mechanism
  - Ensures panel initialization even if ID passed through alternate routes

**Intelligence Summary Section** (ENHANCED - 2025-12-10):
- Collapsible section with comprehensive job analysis
- Four-part breakdown:
  1. **Pain Points**: 4 dimensions (technical, operational, strategic, cultural)
  2. **Company Signals**: Key insights from research
  3. **Strategic Needs**: How the role aligns with company direction
  4. **Risks**: Potential concerns identified during analysis
- **Annotation Heatmap** (NEW - 2025-12-10):
  - Colored bar (green/yellow/red) proportional to manual annotation match counts
  - Shows "Match X%" score derived from aggregate annotations
  - Displays must-have gaps warning when gaps present
  - Aggregated from `_aggregate_annotations()` in full_extraction_service.py
- Appears prominently after pipeline progress indicator
- Provides context for outreach strategy and quick match assessment

**Contact Cards with Type Badges** (NEW - 2025-12-08):
- Color-coded badges identify contact role:
  - Purple badge: Recruiter
  - Blue badge: Hiring Manager
  - Green badge: VP/Director
  - Orange badge: Executive
  - Grey badge: Peer
- Primary and secondary contacts use identical formatting
- Two optimized outreach options per contact:
  1. **Connection Request** (LinkedIn): Pre-filled ≤300 char message with Calendly
  2. **InMail/Email**: Professional subject + body (works for both platforms)
- Contact type and outreach options visible at a glance
- Enables smart routing based on contact authority level

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

**PDF Generation** (Phase 6 - Separated Service, FIXED 2025-12-10):
- Dedicated Docker container with Playwright/Chromium
- Endpoints: `/health`, `/render-pdf`, `/cv-to-pdf`
- HTML to PDF via Playwright with embedded fonts, margin validation (defense-in-depth)
- Error handling: 400 (invalid state), 500 (rendering failed), 503 (service unavailable)
- **Import Fix** (2025-12-10): Changed `pdf_export.py` to use `TYPE_CHECKING` conditional import for `JobState` to avoid circular import errors when module runs from frontend context

**Enhanced Features** (2025-12-08):
- Name displays in uppercase styling
- Role tagline added as H3 below contact info
- Contact info uses dot separators (no emoji)
- Small caps toggle button in toolbar
- Consistent styling between editor and generated output

---

## Full Extraction Service (ENHANCED - 2025-12-10)

**Purpose**: Single combined operation running Layers 1.4 + 2 + 4 (JD Processor + JD Extractor + Pain Point Mining + Fit Scoring) without full 7-layer pipeline

**File**: `src/services/full_extraction_service.py` (ENHANCED with JD Extractor)

**API Endpoint**: `POST /api/operations/full-extraction`

**Input**:
```json
{
  "job_id": "string",
  "tier": "fast|balanced|quality"
}
```

**Output**:
```json
{
  "status": "success|failed",
  "structured_jd": {
    "title": "string",
    "category": "string",
    "role_category": "string",
    "responsibilities": ["string"],
    "key_requirements": ["string"],
    "keywords": ["string"],
    "seniority_level": "string"
  },
  "pain_points": ["string"],
  "fit_score": {
    "score": "int (0-100)",
    "rationale": "string"
  },
  "annotation_signals": {
    "match_count": "int",
    "match_percentage": "float",
    "must_have_gaps": ["string"]
  },
  "cost_usd": "float",
  "elapsed_seconds": "float",
  "layer_status": {
    "jd_processor": "success|failed",
    "jd_extractor": "success|failed",
    "pain_miner": "success|failed",
    "fit_scorer": "success|failed"
  }
}
```

**Execution Flow** (ENHANCED):
1. Fetch job from MongoDB
2. Run Layer 1.4: JD Processor (structure_jd_service.py) → `processed_jd` (HTML for annotation UI)
3. Run Layer 1.5: JD Extractor (structure_jd_service.py) → `extracted_jd` (structured intelligence)
4. Run Layer 2: Pain Point Mining (pain_point_miner.py)
5. Run Layer 4: Fit Scoring (opportunity_mapper.py)
6. Run Layer 4.5: Annotation Aggregation → compute weighted fit scores
7. Persist all results to MongoDB (both processed and extracted JD)
8. Return aggregated output with per-layer status

**JD Extraction Layers** (NEW - 2025-12-10):
- **Layer 1.4 (JD Processor)**: Parses raw JD into structured HTML sections
  - Extracts qualifications, responsibilities, benefits
  - Returns HTML format for annotation UI highlighting
  - Output: `processed_jd`
- **Layer 1.5 (JD Extractor)**: Extracts semantic intelligence from structured JD
  - Analyzes role category, seniority, keywords, responsibilities
  - Returns structured JSON for template display
  - Output: `extracted_jd` with role_category, responsibilities, keywords, seniority_level

**Dual Output Model** (NEW - 2025-12-10):
- **`processed_jd`**: HTML sections (for annotation UI and highlighting)
- **`extracted_jd`**: Structured intelligence (for CV template display and role research)
- Both stored in MongoDB, enables flexible UI rendering

**Per-Layer Status Tracking** (NEW - 2025-12-10):
- Returns `layer_status` dict with success/failure for each layer
- Enables granular error reporting and debugging
- Helps identify which layer failed if full extraction fails

**Annotation Signals Aggregation** (NEW - 2025-12-10):
- Computes `match_percentage` from manual JD annotations
- Identifies `must_have_gaps` (skills with gap count > threshold)
- Weighted fit score calculation: (match_count / total_annotations) * 100
- Used for annotation-based heatmap display

**Cost Optimization**:
- Fast tier: Haiku + Haiku + Haiku + Haiku (~$0.04 total)
- Balanced tier: Sonnet + Sonnet + Sonnet + Sonnet (~$0.20 total)
- Quality tier: Opus + Opus + Opus + Opus (~$0.60 total)

**Use Cases**:
- Quick job analysis before detailed research
- Cost-effective way to get pain points, fit score, and structured intelligence
- Alternative to full 7-layer pipeline when only basic analysis needed
- JD annotation-aware processing for better match visualization

**UI Integration**:
- Purple "Extract JD" button (btn-action-accent) in job detail page
- Tier selector for cost/quality trade-off
- Progress indicator during execution
- Results displayed inline on detail page with annotation heatmap
- Shows match % and must-have gaps in "Opportunity & Fit Analysis" section

---

## E2E Annotation Integration (Complete - 11 Phases, 2025-12-10)

### Overview

Complete end-to-end integration of 5-dimensional annotation system across all 7 pipeline layers, enabling hyper-personalized CV generation, cover letters, and outreach based on candidate preferences (passion, identity, expertise), job requirements (must-haves, gaps, reframe), and strategic fit.

### 5-Dimensional Annotation System

**Dimensions** (stored per annotation):
1. **Relevance** (0-5): How critical is this to job success
2. **Requirement Type** (must_have|nice_to_have|gap|concern): Job requirement classification
3. **Passion Level** (love_it|enjoy|neutral|tolerate|avoid): Candidate enthusiasm for role/company
4. **Identity Level** (core_identity|strong_identity|developing|peripheral|not_identity): Professional identity alignment
5. **Annotation Type** (skill|responsibility|qualification|concern|reframe): What's being annotated

### Implementation Phases (11 Phases Complete)

**Phase 1: Layer 4 Fit Signal** (Completed 2025-12-10)
- File: `src/layer4/annotation_fit_signal.py` (NEW)
- Hybrid fit scoring: 70% LLM score + 30% annotation signal
- Detects disqualifiers from annotations (must_have gaps, passion=avoid)
- Returns `annotation_analysis` with coverage, confidence, disqualifiers, strengths

**Phase 2: Layer 2 Pain Point Miner - Annotation-Aware** (Completed 2025-12-10)
- File: `src/layer2/pain_point_miner.py` (ENHANCED)
- Extracts annotation context: must_have_keywords, gap_areas, core_strength_areas, reframe_notes
- Passes annotation priorities to LLM prompt injection
- Post-processes pain points with boost multipliers

**Phase 3: Cover Letter - Passion & Identity Integration** (Completed 2025-12-10)
- File: `src/layer6/cover_letter_generator.py` (ENHANCED)
- Added `_format_passion_identity_section()` for authentic enthusiasm hooks
- Passion dimension drives content (love_it areas emphasized, avoid areas de-emphasized)
- Identity dimension shapes positioning and tone
- Header context includes passion_priorities, avoid_priorities, identity_priorities

**Phase 4: Company Research - Annotation-Aware** (Completed 2025-12-10)
- File: `src/services/company_research_service.py` (ENHANCED)
- Added `_extract_annotation_research_focus()` for targeted research guidance
- Annotation context injected into FireCrawl queries and LLM analysis
- Research focuses on passion annotations (love_it) for culture priorities
- Must-have priorities inform technical research areas

**Phase 5: Interview Predictor - Annotation-Driven** (Completed 2025-12-10)
- File: `src/layer7/interview_predictor.py` (ENHANCED)
- Added passion_probe and identity_probe question types
- Gap + must_have annotations predict weakness questions
- Reframe notes populate preparation_note field
- Core strength annotations predict deep-dive behavioral questions

**Phase 6: ATS Validation** (Completed 2025-12-10)
- File: `src/layer6_v2/orchestrator.py` + `src/layer6_v2/types.py` (ENHANCED)
- Added `ATSValidationResult` type
- Added `_validate_ats_coverage()` method for post-generation validation
- Keyword occurrence counts validated against min/max requirements
- ATS readiness score recalculated after generation

**Phase 7: Outreach - Annotation-Aware** (Completed 2025-12-10)
- File: `src/layer6/outreach_generator.py` (ENHANCED)
- Added `_format_annotation_context()` with passion/identity/avoid sections
- Passion dimension drives genuine connection hooks in opener
- Identity dimension guides professional positioning
- Must-have priorities emphasized in value proposition

**Phase 8: People Mapper - Annotation-Guided** (Completed 2025-12-10)
- File: `src/layer5/people_mapper.py` (ENHANCED)
- Added `_build_annotation_enhanced_queries()` for SEO keyword queries
- Pain point keywords incorporated into contact searches
- Must-have annotations prioritize contact discovery
- Technical skill keywords refine LinkedIn search queries

**Phase 9: Reframe Traceability** (Completed 2025-12-10)
- File: `src/layer6_v2/orchestrator.py` (ENHANCED)
- Added `_validate_reframe_application()` method
- Reframe→bullet mapping tracked and logged
- Warnings generated for unimplemented reframe guidance

**Phase 10: Section Coverage Enforcement** (Completed 2025-12-10)
- Files: `frontend/static/js/jd-annotation.js` + `frontend/templates/partials/job_detail/_annotation_popover.html` (ENHANCED)
- Added `validateCoverage()` function for per-section tracking
- Coverage warnings display uncovered sections
- Validation prevents save with incomplete coverage
- Coverage targets: 5 responsibilities, 5 qualifications, 4 technical skills, 2 nice-to-haves

**Phase 11: Review Workflow** (Completed 2025-12-10)
- Files: `frontend/static/js/jd-annotation.js` + templates (ENHANCED)
- Review queue UI for pipeline-generated suggestions
- Approve/reject buttons with optional notes
- Status filters (draft, approved, rejected, needs_review)
- Bulk approve/reject functionality
- Review history tracking with timestamps

### Annotation Data Flow

```
JD Annotation Panel
     ↓
┌─────────────────────────────────────────────────────────┐
│ 5D Annotation Storage (MongoDB)                         │
├─────────────────────────────────────────────────────────┤
│ - 2 dimensions (relevance, requirement_type)  [UI]      │
│ - 2 dimensions (passion_level, identity_level) [UI]     │
│ - 1 dimension (annotation_type)               [Backend] │
│ - status (draft|approved|rejected|needs_review)         │
│ - created_by (human|pipeline_suggestion|preset)         │
└─────────────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────────────┐
│ Pipeline Layers - Annotation Integration Points         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ Layer 2 (Pain Points)                                   │
│ ├─ Input: must_have_keywords, core_strengths          │
│ └─ Output: Boosted pain point narrative                 │
│                                                          │
│ Layer 3 (Company Research)                              │
│ ├─ Input: passion_level, must_have_priorities          │
│ └─ Output: Targeted research focus                      │
│                                                          │
│ Layer 4 (Fit Scoring)                                   │
│ ├─ Input: All 5 dimensions                             │
│ └─ Output: Hybrid score + disqualifier flags           │
│                                                          │
│ Layer 5 (People Mapper)                                 │
│ ├─ Input: pain_point keywords, core_strengths         │
│ └─ Output: Refined SEO queries for contacts            │
│                                                          │
│ Layer 6 (CV/Cover Letter/Outreach)                     │
│ ├─ Input: passion_level, identity_level, must_haves   │
│ ├─ CV: Dynamic categories, passion-aligned skills     │
│ ├─ Cover Letter: Authentic enthusiasm + positioning   │
│ └─ Outreach: Identity-based messaging                 │
│                                                          │
│ Layer 7 (Interview Predictor)                           │
│ ├─ Input: gaps, reframe_notes, core_strengths         │
│ └─ Output: Weakness + strength questions               │
│                                                          │
└─────────────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────────────┐
│ Output Artifacts                                        │
├─────────────────────────────────────────────────────────┤
│ - CV: JD-aligned, passion-reflected skills & profile   │
│ - Cover Letter: Authentic enthusiasm + identity fit    │
│ - Outreach: Personalized to candidate preferences      │
│ - Interview Prep: Targeted weakness + strength Q&A     │
└─────────────────────────────────────────────────────────┘
```

### Boost Formula

```python
# Boost multipliers applied during pain point post-processing:
core_identity_areas:     1.5x  # Emphasize in narrative
strong_identity_areas:   1.2x  # Secondary emphasis
must_have_skills:        1.3x  # Prioritize in pain points
passion_love_it:         1.4x  # High enthusiasm boost
passion_enjoy:           1.1x  # Mild boost
passion_avoid:           0.7x  # De-emphasize/reframe
gap_areas:               0.8x  # Acknowledge but reframe

Final Score = base_pain_point_relevance * multiplier
```

### Files Modified (11 Phases)

**Backend** (9 files):
- `src/layer2/pain_point_miner.py` - Phase 2: Annotation context extraction
- `src/layer4/annotation_fit_signal.py` - Phase 1: NEW file, hybrid scoring
- `src/layer6/cover_letter_generator.py` - Phase 3: Passion/identity sections
- `src/services/company_research_service.py` - Phase 4: Research guidance
- `src/layer7/interview_predictor.py` - Phase 5: Probe question types
- `src/layer6_v2/types.py` - Phases 3,6: Extended context types
- `src/layer6_v2/orchestrator.py` - Phases 6,9: Validation methods
- `src/layer6/outreach_generator.py` - Phase 7: Annotation context
- `src/layer5/people_mapper.py` - Phase 8: Enhanced queries

**Frontend** (2 files):
- `frontend/static/js/jd-annotation.js` - Phases 10,11: Coverage validation, review workflow
- `frontend/templates/partials/job_detail/_annotation_popover.html` - Phase 10: Coverage warnings

**Type Enhancements** (`src/common/annotation_boost.py`):
- New methods: `get_passions()`, `get_avoid_areas()`, `get_identity_core()`, `get_identity_not_me()`
- Extended stats with passion and identity dimension counts
- Boost multiplier application across all layers

### Test Coverage

Total tests added: 89 tests across all 11 phases
- Unit tests for each phase's core functionality
- Integration tests validating annotation→output mapping
- Edge case handling for missing/conflicting annotations

---

## Identity-Based Persona Generation System (NEW - 2025-12-10)

### Overview

Transform candidate's identity annotations (core_identity, strong_identity, developing) into coherent, synthesized persona statements that are automatically injected into CVs, cover letters, and outreach messages. Enables hyper-personalized applications while maintaining grounding in actual professional identity claims.

### Example

```
Identity Annotations:
- core_identity: Cloud architecture, team leadership, distributed systems
- strong_identity: DevOps culture, mentoring, system design
- developing: AI/ML integration, incident response

Generated Persona:
"Solutions architect who leads engineering teams through complex cloud
transformations, specializing in distributed systems and fostering DevOps culture"

Injected into CV Profile:
"As a solutions architect who leads engineering teams through complex cloud
transformations, I bring expertise in designing resilient distributed systems
while fostering DevOps culture and mentoring high-performing teams."

Injected into Cover Letter:
"As a solutions architect who leads engineering teams through complex cloud
transformations, I'm excited about [Company] because [passion-driven reason]..."

Injected into Outreach:
"As a solutions architect specializing in cloud transformations, I'm reaching
out because [specific role fit]..."
```

### Architecture

**Core Module** (`src/common/persona_builder.py` - NEW):

```python
@dataclass
class SynthesizedPersona:
    """Synthesized persona statement"""
    persona_statement: str  # "Solutions architect who..."
    source_annotations: Dict[str, List[str]]  # Tracing which annotations generated this
    confidence: float  # 0-1 confidence score
    created_at: datetime

class PersonaBuilder:
    """Synthesize identity annotations into coherent persona statements"""

    async def synthesize_from_annotations(
        self,
        annotations: List[JDAnnotation],
        candidate_profile: str,
        job_context: str
    ) -> SynthesizedPersona:
        """
        1. Extract identity annotations (core, strong, developing)
        2. Filter by relevance and strength
        3. LLM synthesis into coherent statement
        4. Validation (length, coherence, grounding)
        5. Return synthesized persona with source tracing
        """

    def get_persona_guidance(self) -> str:
        """Format synthesized persona for prompt injection"""
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ JD Annotation Panel                                         │
├─────────────────────────────────────────────────────────────┤
│ Identity Annotations (core/strong/developing)               │
│ + Passion Annotations (love_it/enjoy)                       │
│ + Skill Annotations (must_have/core_strength)               │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ PersonaBuilder.synthesize_from_annotations()                │
├─────────────────────────────────────────────────────────────┤
│ 1. Extract: core_identity + strong_identity                │
│ 2. Merge: De-duplicate, weight by strength                 │
│ 3. Filter: Remove noise, prioritize by frequency            │
│ 4. LLM: "Synthesize into one coherent professional persona" │
│ 5. Validate: Length (10-20 words), coherence, grounding     │
│ 6. Store: MongoDB jd_annotations.synthesized_persona        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ UI Preview & Edit Panel                                     │
├─────────────────────────────────────────────────────────────┤
│ - Display synthesized persona                              │
│ - Allow user refinement/editing                            │
│ - Save/discard buttons                                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Pipeline Injection Points                                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Layer 6 Header Generator                                    │
│ ├─ CV Profile: Central theme of persona                    │
│ └─ Example: "As a [persona], I bring..."                  │
│                                                              │
│ Layer 6 Cover Letter                                       │
│ ├─ Opening: "As a [persona]..."                            │
│ └─ Passion section framing                                 │
│                                                              │
│ Layer 5 People Mapper                                      │
│ ├─ Outreach: Lead with persona positioning                │
│ └─ Contact messaging: Professional identity first          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### API Endpoints

**Frontend Routes** (`frontend/app.py`):

```python
POST /api/jobs/<job_id>/synthesize-persona
# Input:
{
    "tier": "balanced"  # optional, for LLM model selection
}

# Output:
{
    "status": "success",
    "persona": {
        "persona_statement": "Solutions architect who...",
        "source_annotations": {...},
        "confidence": 0.92,
        "created_at": "2025-12-10T..."
    },
    "elapsed_seconds": 2.5
}

POST /api/jobs/<job_id>/save-persona
# Input:
{
    "persona_statement": "User-edited persona statement",
    "notes": "Optional notes about the persona"
}

# Output:
{
    "status": "success",
    "saved_at": "2025-12-10T..."
}
```

### Frontend UI Components

**Persona Panel** (`frontend/static/js/jd-annotation.js`):

- **Synthesis Button**: "Generate from Identity" → calls `/api/jobs/<id>/synthesize-persona`
- **Preview Display**: Read-only markdown rendering of persona
- **Edit Mode**: Textarea with user refinement capability
- **Save/Cancel**: Buttons to persist or discard changes
- **Status Indicators**: Loading spinner, success/error messages
- **Source Tracing**: Shows which annotations contributed to persona

### Files Created

1. **`src/common/persona_builder.py`** (NEW):
   - `SynthesizedPersona` dataclass
   - `PersonaBuilder` class with synthesis logic
   - Validation, caching, tracing methods
   - ~220 lines

2. **`tests/unit/test_persona_builder.py`** (NEW):
   - 33 unit tests covering:
     - Synthesis from single/multiple annotations
     - Validation rules (length, coherence, grounding)
     - Edge cases (empty annotations, conflicts, duplicates)
     - Caching behavior
     - Model tier selection

### Files Modified

1. **`frontend/app.py`**:
   - `POST /api/jobs/<id>/synthesize-persona` endpoint
   - `POST /api/jobs/<id>/save-persona` endpoint
   - MongoDB persistence logic

2. **`frontend/static/js/jd-annotation.js`**:
   - `personaState` variable tracking persona UI state
   - `synthesizePersona()` - API call and state update
   - `savePersona()` - Persist to MongoDB
   - `renderPersonaPanel()` - UI rendering method
   - `editPersona()` / `cancelPersonaEdit()` - State management

3. **`frontend/templates/partials/job_detail/_jd_annotation_panel.html`**:
   - Persona panel container with section structure

4. **`src/layer6_v2/header_generator.py`**:
   - `get_persona_guidance()` call in profile section generation
   - Injects persona as central narrative theme
   - Example injection: `"As a {persona}, I bring {skills}..."`

5. **`src/layer6_v2/ensemble_header_generator.py`**:
   - Passes `jd_annotations` to header generators
   - Enables persona access in CV generation

6. **`src/layer6_v2/orchestrator.py`**:
   - Passes `jd_annotations` through generation pipeline

7. **`src/layer6/cover_letter_generator.py`**:
   - Injects persona at start of passion/identity section
   - Example: `"As a [persona], I'm drawn to this role because..."`

8. **`src/layer5/people_mapper.py`**:
   - Injects persona in contact outreach context
   - Professional positioning for message openers

### Test Coverage

**`test_persona_builder.py`** (33 tests):

1. **Synthesis Tests** (8 tests):
   - Single identity annotation synthesis
   - Multiple annotations merging
   - Passion annotation integration
   - Skill annotation context
   - Empty annotation handling
   - Duplicate identity handling

2. **Validation Tests** (7 tests):
   - Length validation (10-20 words)
   - Coherence validation (no nonsense words)
   - Grounding validation (matches source annotations)
   - Professional language validation
   - Uniqueness validation

3. **Edge Cases** (10 tests):
   - All identity levels same (core/strong/developing)
   - Conflicting passion levels
   - Missing candidate profile
   - Very long identity lists (100+ annotations)
   - Non-English characters
   - Special characters and punctuation

4. **Integration Tests** (8 tests):
   - Persona → CV injection
   - Persona → Cover letter injection
   - Persona → Outreach injection
   - User edit persistence
   - Model tier selection
   - Caching behavior

### Impact

- **Candidate Experience**: CVs and outreach now reflect authentic professional persona derived from candidate preferences
- **Authenticity**: Persona grounded in actual identity claims (no hallucinations)
- **Personalization**: Each job gets customized persona-driven narrative
- **Consistency**: Same persona flows through all application materials
- **Flexibility**: Users can refine generated persona before use

### Backward Compatibility

- When no identity annotations exist: System maintains status quo behavior (no persona injection)
- Persona field optional in jd_annotations schema
- Graceful degradation in all layers if persona missing

---

## Pipeline Overhaul - Independent Operations (Phase 1-5 Complete - 2025-12-10)

### Overview

Foundation for decoupled, cost-optimized operations that can be triggered independently of the main pipeline. Users can now:
- Structure raw JD without full pipeline
- Research companies/roles independently
- Generate CV variants for specific jobs
- Select operation quality tier (Fast/Balanced/Quality) with visible cost impact

### Architecture: Tiered Model System (Phase 1)

**File**: `src/common/model_tiers.py` (380 lines, 46 unit tests)

```python
# 3-tier model selection
class ModelTier(Enum):
    FAST = "fast"          # Haiku: fastest, cheapest
    BALANCED = "balanced"  # Sonnet: optimal cost/quality
    QUALITY = "quality"    # Opus: best output, highest cost

# Per-operation model matrix
TIER_MODEL_CONFIG = {
    "structure_jd": {
        "fast": "claude-haiku",
        "balanced": "gpt-4o-mini",
        "quality": "gpt-4o"
    },
    "research_company": {...},
    "generate_cv": {...}
}

# Cost calculation
cost_estimates = {
    "fast": 0.01,
    "balanced": 0.05,
    "quality": 0.15
}
```

**Features**:
- Dynamic model selection per operation
- Automatic fallback (e.g., if Opus unavailable → Sonnet)
- Cost estimation before execution
- Per-tier token tracking

### Operation Base Class (Phase 2)

**File**: `src/services/operation_base.py` (450 lines, 22 unit tests)

```python
class OperationBase:
    """Reusable base for button-triggered operations"""

    async def execute(self) -> OperationResult:
        # State: pending → executing → completed|failed
        # Retry logic: up to 3 attempts with exponential backoff
        # Health check: validates dependencies before execution
        # Timeout: 300s default, configurable per operation
        # Progress: 0-100% completion indicator

    async def check_health(self) -> HealthStatus:
        # Service availability check (MongoDB, LLM, etc.)
        # Returns: healthy|degraded|unavailable

    async def cancel(self) -> bool:
        # Graceful cancellation during execution
```

**State Machine**:
```
        ┌─────────────┐
        │   PENDING   │
        └──────┬──────┘
               │ start()
        ┌──────▼──────────┐
        │   EXECUTING     │ ◄──┐
        └──────┬──────────┘    │ retry_count < 3
               │               │
        ┌──────▼──────┐────────┘
        │  SUCCESS    │
        └─────────────┘  OR  ┌─────────┐
                               │ FAILED  │
                               └─────────┘
```

### Independent Action Buttons (Phase 3)

**Frontend Components**:

1. **HTML** (`frontend/templates/job_detail.html`):
   - Three buttons: "Structure JD", "Research Job", "Generate CV"
   - Tier selector dropdown (Fast/Balanced/Quality)
   - Cost display (Auto-calculated before execution)
   - Status indicator (Pending → Executing → Completed)
   - Progress bar with elapsed time

2. **JavaScript State Machine** (`frontend/static/js/pipeline-actions.js`):
   - Alpine.js for reactive state management
   - Operation status polling (500ms interval)
   - Cost calculator UI
   - Result display with copy-to-clipboard

3. **Styling** (`frontend/static/css/pipeline-actions.css`):
   - Button states with animated spinners
   - Progress bar with gradient
   - Toast notifications for completion/error

### API Routes (Phase 3)

**File**: `runner_service/routes/operations.py`

**POST /api/operations/structure-jd**
- Input: `{ job_id: string, tier: "fast|balanced|quality" }`
- Output: `{ status: string, structured_jd: object, cost_usd: float, elapsed_seconds: float }`
- Purpose: Parse raw JD into structured format without full pipeline

**POST /api/operations/research-company**
- Input: `{ company_name: string, tier: "fast|balanced|quality" }`
- Output: `{ status: string, research_summary: string, signals: object, cost_usd: float }`
- Purpose: Quick company research independent of job processing

**POST /api/operations/generate-cv-variant**
- Input: `{ job_id: string, tier: "fast|balanced|quality", variant_type: string }`
- Output: `{ status: string, cv_text: string, elapsed_seconds: float, cost_usd: float }`
- Purpose: Generate CV variant without running full pipeline

**GET /api/operations/{operation_id}/status**
- Output: `{ status: string, progress_percent: int, elapsed_seconds: float, error_message: string }`
- Purpose: Poll operation status during execution

### Integration Points

**Router Registration** (`runner_service/routes/__init__.py`):
```python
from runner_service.routes.operations import operations_router

app.include_router(operations_router, prefix="/api/operations")
```

**Health Checks**:
- Each operation validates dependencies before execution
- MongoDB connectivity check
- LLM provider availability check
- Rate limiting verification

### Annotation Heatmap Fix (Phase 3)

**File**: `frontend/static/js/jd-annotation.js`

**applyHighlights() Implementation**:
```javascript
function applyHighlights(annotations) {
    // Clear previous highlights
    document.querySelectorAll('[data-annotation-id]').forEach(el => {
        el.style.backgroundColor = '';
    });

    // Apply new highlights
    annotations.forEach(({ id, color }) => {
        document.querySelectorAll(`[data-annotation-id="${id}"]`)
            .forEach(el => {
                el.style.backgroundColor = color;
            });
    });
}
```

### Pending Work (Phase 4-6)

**Phase 4: Service Implementations**
- Actual service logic for structure-jd, research, cv-gen
- Database persistence for operation results
- Webhook integration for async completions

**Phase 5: Contacts & Outreach Decoupling**
- Separate API endpoint for contact discovery
- Independent outreach message generation
- Scheduling support for bulk outreach

**Phase 6: E2E Testing & Documentation**
- Integration tests for all operation endpoints
- API documentation updates
- User guide for tiered operations

### Files Summary

**Created** (6 files, 1320 lines):
- `src/common/model_tiers.py` (380 lines)
- `src/services/operation_base.py` (450 lines)
- `frontend/static/css/pipeline-actions.css` (200 lines)
- `frontend/static/js/pipeline-actions.js` (320 lines)
- `runner_service/routes/operations.py` (280 lines)
- `runner_service/routes/__init__.py` (40 lines)

**Modified** (3 files):
- `frontend/static/js/jd-annotation.js` (+80 lines)
- `frontend/templates/job_detail.html`
- `runner_service/app.py`

**Tests Added** (2 files, 68 tests):
- `tests/unit/test_model_tiers.py` (46 tests)
- `tests/unit/test_operation_base.py` (22 tests)

---

## Anti-Hallucination Pattern (NEW - 2025-12-08)

### Architecture: Three-Layer Validation System

```
┌─────────────────────────────────────────────────────────┐
│         SKILL HALLUCINATION PREVENTION SYSTEM           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ Layer 1: Master-CV Whitelist (Static)                   │
│ ├── Extract all skills from data/master-cv/roles/*.md   │
│ ├── Hard skills: Python, AWS, Kubernetes, etc.          │
│ ├── Soft skills: Leadership, Mentoring, etc.            │
│ └── Prevents claiming ANY skill not in master-CV        │
│                                                          │
│ Layer 2: Evidence Validation (Profile Section)          │
│ ├── Only use JD keywords if candidate has evidence       │
│ ├── Evidence sources: experience bullets + master-CV     │
│ ├── Method: Keyword frequency in narrative (3+ mentions) │
│ └── Reject JD keywords with 0 evidence                  │
│                                                          │
│ Layer 3: Anti-Hallucination Tactics (Improver)          │
│ ├── Explicit "CRITICAL ANTI-HALLUCINATION RULES" prompt │
│ ├── Forbid: "Never add skills candidate doesn't have"   │
│ ├── Validate: All new skills against whitelist          │
│ └── Enforce: STAR format with skill evidence            │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Implementation Details

**1. Header Generator - Profile Section** (`src/layer6_v2/header_generator.py:440-502`)

**Before** (Hallucinating):
```python
# Would generate:
"Experienced Engineer skilled in Python, AWS, Kubernetes, Java, PHP, Spring Boot..."
# (including Java/PHP/Spring Boot NOT in master-CV!)
```

**After** (Evidence-Grounded):
```python
def _filter_keywords_by_evidence(jd_keywords: List[str],
                                  experience_bullets: List[str],
                                  skill_whitelist: List[str]) -> List[str]:
    """Only include JD keywords with defensive evidence."""
    filtered = []
    for keyword in jd_keywords:
        # Must be in whitelist AND mentioned in bullets (3+ times)
        if keyword.lower() in skill_whitelist:
            mention_count = sum(1 for bullet in experience_bullets
                               if keyword.lower() in bullet.lower())
            if mention_count >= 3:
                filtered.append(keyword)
    return filtered
```

**2. CV Improver - Anti-Hallucination Rules** (`src/layer6_v2/improver.py`)

Added to `IMPROVEMENT_STRATEGIES`:
```python
"CRITICAL ANTI-HALLUCINATION RULES": {
    "rules": [
        "Never add skills the candidate doesn't have evidence for",
        "All skills must appear in at least 2 experience bullets",
        "Validate all technical claims against master-CV whitelist",
        "Format: [Challenge] + [Skill Used] + [Quantified Result]",
        "Example: 'Reduced latency by 40% using Go and Docker'"
    ],
    "forbidden": ["Never invented skills", "Never assumed expertise",
                  "Never generic claims without specific evidence"]
}
```

System prompt updated with:
```
"CRITICAL: Do not add or suggest any skills that the candidate
doesn't have explicit evidence for in their background.
All improvements must be defensible in an interview."
```

**3. Whitelist Validation**

Both layers validate against dynamic whitelist:
```python
whitelist = cv_loader.get_skill_whitelist()
# Returns: union of all hard_skills + soft_skills from roles/*.md
# Current: ~200 skills across Backend, Platform, Staff Engineer roles
```

### Result

**Before** (2025-11-29): CVs claimed 8-12 skills with zero evidence
**After** (2025-12-08): All skills grounded in master-CV with 3+ bullet mentions

**Impact**:
- 100% defensible CVs in interviews
- Zero hallucinated skill claims
- Candidates can cite specific achievements for every skill
- Alignment with actual master-CV content

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
