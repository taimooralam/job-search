# System Architecture

## Overview

Job Intelligence Pipeline - 7-layer LangGraph system with professional CV editor and job matching.

## System Diagram

```
Inputs (MongoDB) → JD Processing → CV Analysis → Company Research → Contact Discovery → Enrichment → Output
                        ↓
                  CLI/Web UI (Flask, TipTap Editor)
```

## Pipeline Layers

1. **JD Structure Analysis** - Extract job requirements from job descriptions
2. **CV Coverage Mapping** - Map candidate qualifications to job requirements
3. **Gap Analysis** - Identify skill/experience gaps
4. **Company Research** - Gather company context and insights
5. **Contact Discovery** - Find hiring managers and decision makers
6. **Enrichment & Ranking** - Score fit and generate personalized output
7. **Output Generation** - Create tailored CV, cover letter, and strategy

## Data Model

### JobState (LangGraph State)

```python
class JobState(TypedDict):
    job_id: str                          # MongoDB _id from level-2 collection
    jd: str                             # Job description text
    jd_structured: dict                 # Extracted job requirements
    cv_coverage: dict                   # Section-level coverage mapping
    company_info: dict                  # Company research results
    contacts: list[ContactInfo]        # Discovered contacts
    enrichment: dict                    # Ranking and insights
    output: OutputFormat               # Final deliverables
    error: Optional[str]               # Error context
```

### MongoDB Collections

- **level-2**: Job listings with full descriptions
- **cv-annotations**: JD analysis with section markers
- **company-research**: Cached company data
- **contacts**: Discovered contacts and enrichment

## Key Design Patterns

### Section Coverage Tracking (BUG 4)

**Components:**

- `_annotation_list.html` - Data section attributes on annotation elements
- `jd-annotation.js` - updateCoverage() method updates DOM for section tracking
- Data flow: JD annotations → section attributes → frontend coverage display

**Purpose:** Enable precise tracking of which CV sections address which job requirements

### Verbose Logging Pipeline (BUG 1)

**Components:**

- `StructureJDService.execute()` - Accepts progress_callback and log_callback parameters
- `routes/operations.py` - Passes logging callbacks to service layer
- Data flow: Service layer → callbacks → web UI progress display

**Purpose:** Real-time visibility into JD processing progress for users

### Async-Safe Coroutine Handling (BUG 3/5)

**Components:**

- `orchestrator.py` - New \_run_async_safely() method
- Uses ThreadPoolExecutor to handle nested event loops
- Wraps async CV generation in thread-safe executor

**Purpose:** Prevent "RuntimeError: running event loop" when calling async code from sync context

**Architecture:**

```python
def _run_async_safely(self, coro):
    """Handle nested event loops with ThreadPoolExecutor"""
    executor = ThreadPoolExecutor(max_workers=1)
    return executor.submit(asyncio.run, coro).result()
```

### Smart Cache Logic (BUG 2)

**Components:**

- `company_research_service.py` - Modified cache check logic
- Partial cache hit detection triggers people_mapper
- Data flow: Check existing contacts → if partial → call people_mapper → merge results

**Purpose:** Improve contact discovery by combining cached company data with fresh contact mapping

**Logic:**

```
If cached_company_data exists:
  If contacts_from_cache are complete:
    Return cached + contacts
  Else (partial):
    Call people_mapper(company_data)
    Return merged results
```

### Parallel Batch Execution Pattern (BUG FIX)

**Problem:** FastAPI's `BackgroundTasks` runs async tasks sequentially (awaiting each before starting next)

**Components:**

- `routes/operations.py` - New `submit_service_task()` helper function
- Two ThreadPool executors: `_db_executor` (8 workers) and `_service_executor` (4 workers)
- Fire-and-forget pattern: `submit_service_task(coro)` submits without awaiting

**Purpose:** Enable true parallel execution of batch operations (full-extraction, research-company, generate-cv, all-ops)

**Architecture:**

```python
def submit_service_task(coro) -> None:
    """Submit task to executor thread pool (fire-and-forget)"""
    _service_executor.submit(_run_async_in_thread, coro)

# Usage in endpoints:
submit_service_task(_execute_extraction_bulk_task(...))  # Returns immediately
```

**Impact:**

- Previously: 4 batch jobs queued sequentially (10 min each = 40 min total)
- Now: 4 batch jobs execute in parallel (10 min each = 10 min total)
- Up to 4 concurrent batch operations (max_workers=4 limit)

**Design Rationale:**

- Separate ThreadPoolExecutor for service tasks prevents starving DB operations
- Fire-and-forget doesn't block route handler - returns immediately
- Worker threads handle blocking operations (ThreadPoolExecutor.run_async internally blocks)
- Main event loop remains responsive for log polling and other endpoints

### Queue Thread-Safety Pattern (CRITICAL)

**Problem:** Worker threads were calling async Redis operations (`redis_queue.start_item()`, `redis_queue.complete()`, `redis_queue.fail()`) directly. However, aioredis clients are bound to the main event loop and cannot be used from worker threads. Result: bulk tasks stuck in "pending" state with "Stale: pending for over 60 minutes" errors.

**Root Cause:** Thread-safety violation - async Redis client used outside its event loop context

**Solution:** Thread-safe wrapper functions that schedule Redis operations on the main event loop

**Components:**

- `runner_service/routes/operations.py` - Three thread-safe wrapper functions:
  - `_queue_start_item_threadsafe(job_id)` - Schedule `redis_queue.start_item()` on main loop
  - `_queue_complete_threadsafe(job_id)` - Schedule `redis_queue.complete()` on main loop
  - `_queue_fail_threadsafe(job_id, error)` - Schedule `redis_queue.fail()` on main loop

**Implementation Pattern:**

```python
def _queue_start_item_threadsafe(job_id: str) -> None:
    """Schedule queue state update on main event loop (thread-safe)"""
    try:
        # Get main event loop and schedule coroutine from worker thread
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop in this thread, create one temporarily
        loop = asyncio.new_event_loop()

    # Schedule coroutine and get result
    future = asyncio.run_coroutine_threadsafe(
        redis_queue.start_item(job_id), loop
    )
    future.result(timeout=5)  # Block until complete

# Fixed usage in _execute_cv_bulk_task():
_queue_start_item_threadsafe(job_id)  # Instead of await redis_queue.start_item(job_id)
```

**Functions Fixed:**

- `_execute_cv_bulk_task()` - CV generation bulk operations
- `_execute_extraction_bulk_task()` - Full extraction bulk operations
- `_execute_research_bulk_task()` - Company research bulk operations
- `_execute_all_ops_bulk_task()` - Combined pipeline bulk operations

**Critical Design Constraint:**

- **ALWAYS use thread-safe wrappers** when calling queue operations from worker threads
- Direct async calls will cause silent failures (tasks stuck pending)
- Main event loop must remain responsive (hence asyncio.run_coroutine_threadsafe)

**Testing Implications:**

- Bulk operations that were timing out now complete successfully
- Tasks correctly transition from pending → running → completed
- No more stale task errors in logs

### Redis Log TTL Configuration

**File:** `runner_service/routes/operation_streaming.py`

**Change:** Reduced log retention from 24 hours to 6 hours

```python
# Before
REDIS_LOG_TTL = 86400  # 24 hours

# After
REDIS_LOG_TTL = 21600  # 6 hours
```

**Rationale:**

- 6 hours sufficient for UI log polling and debugging
- Reduces Redis memory overhead for long-running services
- Logs still available for complete operation lifecycle (most jobs < 1 hour)

## Frontend Architecture

### CV Editor (TipTap)

- Rich text editing with inline annotations
- Section-level highlighting for coverage display
- Two-way sync with MongoDB

### Annotation System

- JD annotations display alongside CV editor
- Coverage indicators show section alignment
- Click-to-edit for quick gap filling

### Progress Display

- Real-time callback integration
- Step-by-step logging of JD processing
- Status updates for long-running operations

### Header Generation V2 - Anti-Hallucination System

**Overview:** Three-component header generation system eliminating LLM hallucinations through strict whitelist enforcement and algorithmic selection.

**Components:**

1. **Value Proposition Statement** (LLM + role templates)
   - `src/layer6_v2/prompts/header_generation.py` - Role-specific templates for 8 categories
   - Formula: [Domain expertise] + [Scope/scale] + [Unique business impact]
   - Constraints: 40-word max, third-person absent voice
   - Examples: "Full-stack engineer maximizing cloud platform ROI across Fortune 500 infrastructure"

2. **Key Achievement Bullets** (LLM selection + whitelist validation)
   - `src/layer6_v2/header_generator.py` - LLM selects and optionally tailors bullets from master CV
   - Strict whitelist: No skills/achievements not in candidate experience
   - Scoring: JD-matched bullets > annotation-emphasized > default bullets
   - Output: 3-4 achievement bullets with clear business impact

3. **Core Competencies** (Pure algorithmic, no LLM)
   - `src/layer6_v2/skills_taxonomy.py` - `CoreCompetencyGeneratorV2` class
   - 4 static sections per role (defined in `data/master-cv/role_skills_taxonomy.json`)
   - Selection algorithm: Pure whitelist + JD keyword prioritization (not addition)
   - Provenance tracking: `SkillsProvenance` dataclass with source (master_cv, jd_signal)

**Data Model:**

```python
# New V2 dataclasses in src/layer6_v2/types.py
class SkillsProvenance(TypedDict):
    source: Literal['master_cv', 'jd_signal']
    confidence: float  # 0.0-1.0

class HeaderGenerationV2Output(TypedDict):
    value_proposition: str              # 40-word statement
    achievement_bullets: list[str]     # 3-4 bullets from master CV
    core_competencies: dict[str, list[dict]]  # 4 sections, whitelist-backed
    provenance: dict[str, SkillsProvenance]   # Track all sources
```

**Role Skills Taxonomy:**

```json
{
  "Software Engineer": {
    "core_competencies": {
      "Languages": ["Python", "JavaScript", "Go"],
      "Platforms": ["AWS", "GCP", "Kubernetes"],
      "Practices": ["SOLID", "TDD", "Microservices"],
      "Tools": ["Docker", "Git", "GitHub Actions"]
    }
  }
}
```

**Anti-Hallucination Guarantees:**

- No invented skills: All listed skills must exist in master CV or be JD keywords used for PRIORITIZATION only
- Whitelist-backed: `CoreCompetencyGeneratorV2` validates against master CV before output
- Provenance tracking: Every competency tagged with source (master_cv or jd_signal)
- No synthetic synthesis: Bullets selected/tailored from existing master CV content, not generated

**Feature Flag:** `USE_HEADER_V2=true`

**Files Changed:**
- `src/layer6_v2/types.py` - New V2 dataclasses
- `src/layer6_v2/skills_taxonomy.py` - `CoreCompetencyGeneratorV2` implementation
- `src/layer6_v2/prompts/header_generation.py` - Role-specific templates
- `src/layer6_v2/header_generator.py` - V2 integration with LLM
- `src/layer6_v2/orchestrator.py` - V2 CV assembly orchestration
- `data/master-cv/role_skills_taxonomy.json` - Static section definitions
- `tests/unit/test_header_generation_v2.py` - 50 comprehensive tests

**Testing:** 50 tests covering template validation, whitelist enforcement, JD prioritization, provenance tracking, and edge cases.

### Phase 6.5 - Final Tailoring Pass with Keyword Emphasis

**Overview:** Post-improver tailoring pass that strategically repositions keywords from JD annotations to prominent locations (headline, opening, competencies) while maintaining ATS compliance.

**Components:**

1. **CVTailorer Class** (`src/layer6_v2/cv_tailorer.py`)
   - Single LLM call for targeted keyword repositioning
   - Validates output against ATS constraints before committing
   - Reverts to original CV on validation failure
   - Decision logic in orchestrator via `_should_apply_tailoring()`

2. **Keyword Emphasis Strategy**
   - **Must-have keywords** (e.g., "SAP", "ERP") → Positioned in first 50 words of summary
   - **Identity keywords** (e.g., "FinTech", "Cloud Architecture") → Positioned in headline
   - **Core strength keywords** (from competencies) → Expanded in skills section
   - Source: JD annotations with role-specific weighting

3. **Post-Tailoring Validation**
   - `ATSConstraintValidator.validate_tailored_cv()` checks:
     - Length increase ≤ 5% (prevent ATS parsing errors from bloated CV)
     - No formatting changes (maintains section integrity)
     - No invented content (only repositions existing bullets)
   - On failure: Automatically reverts to pre-tailored version (no manual recovery needed)

**Data Flow:**

```
Improved CV (from Phase 6 improver)
         ↓
_should_apply_tailoring() decision
         ↓ (if true)
CVTailorer.tailor()
         ↓
Generate LLM prompt: "Reposition keywords in prominent locations"
         ↓
Apply edits (rewrite bullets to naturally include keywords)
         ↓
ATSConstraintValidator.validate_tailored_cv()
         ↓
   If valid: Return tailored CV
   If invalid: Return original CV (auto-revert)
```

**Decision Logic (`_should_apply_tailoring()`):**

- Apply if: `USE_TAILORING=true` AND JD has annotation highlights
- Skip if: Annotation signals weak (< 3 must-have keywords) OR CV already contains keywords
- Fallback: Always safe (revert on any validation failure)

**Testing:** 33 comprehensive tests in `test_annotation_tailoring.py` covering:
- Keyword extraction from annotations
- Prominent location repositioning
- ATS constraint validation
- Auto-revert on failures
- Edge cases (empty CV, all keywords present, etc.)

**Files Changed:**
- `src/layer6_v2/cv_tailorer.py` - New `CVTailorer` class
- `src/layer6_v2/types.py` - New `TailoringResult` dataclass
- `src/layer6_v2/orchestrator.py` - Integrated Phase 6.5 after improver, added `_should_apply_tailoring()`
- `tests/unit/test_annotation_tailoring.py` - 33 tests with mocked LLM and validation

**Feature Flag:** `USE_TAILORING=true` (can be disabled to skip phase)

### Persona-Aware Role Generation

**Overview:** Integrates candidate persona into role bullet generation for context-aware professional framing.

**Components:**

1. **Persona System Prompt Builder** (`src/layer6_v2/prompts/role_generation.py`)
   - `build_role_system_prompt_with_persona()` function
   - Injects persona context into LLM system prompt
   - Persona frames bullet generation within professional identity (e.g., "You are a fintech architect describing achievements that demonstrate thought leadership in distributed systems")

2. **Integration in RoleGenerator** (`src/layer6_v2/role_generator.py`)
   - Calls `build_role_system_prompt_with_persona(persona)` before LLM bullet generation
   - System prompt now includes: role context + persona identity + expected tone/style
   - Improves bullet quality by aligning with candidate's professional brand

3. **Data Model:**

```python
# From JobState (LangGraph state)
persona: dict  # From master-cv.md metadata or user input
  - professional_identity: str  # e.g., "fintech architect"
  - key_themes: list[str]       # e.g., ["thought leadership", "system design"]
  - tone: str                   # e.g., "authoritative", "collaborative"
```

**Example Persona System Prompt:**

```
You are a cloud infrastructure architect with deep expertise in
distributed systems and enterprise DevOps. You value automation,
scalability, and operational resilience. When describing achievements,
emphasize architectural decisions, cross-team impact, and system outcomes.

Generate role-specific bullets that...
```

**Files Changed:**
- `src/layer6_v2/prompts/role_generation.py` - New persona prompt builder
- `src/layer6_v2/role_generator.py` - Integrated persona into system prompt

### Claude CLI Text Format with Error Detection (FIXED)

**Components:**

- `src/common/claude_cli.py` - Changed to `--output-format text` for reliability
- `_detect_cli_error_in_stdout()` - Detects CLI error messages in stdout before JSON parsing
- `src/common/unified_llm.py` - `max_turns` parameter for configurable turn limits
- `src/layer6_v2/header_generator.py` - Uses `max_turns=3`
- `src/layer6_v2/ensemble_header_generator.py` - Uses `max_turns=3`
- `tests/unit/test_claude_cli.py` - 13 new tests for error detection

**Problem:** Claude CLI bug #8126 - JSON format sometimes returns empty result field. Additionally, text format responses can include error messages like "Error: Reached max turns (1)" to stdout, which code was trying to parse as JSON.

**Solution:** Use text format with pre-parsing error detection

```python
# Error detection before JSON parsing
def _detect_cli_error_in_stdout(stdout: str) -> dict:
    """Detect CLI error messages in stdout (e.g., 'Error: Reached max turns')"""
    if "Error:" in stdout:
        logger.error(f"CLI error detected in stdout: {stdout[:200]}")
        return {"is_error": True, "error": stdout}
    return None

# In invoke():
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    return {"is_error": True, "error": result.stderr}

# Check for errors in stdout before parsing
error = _detect_cli_error_in_stdout(result.stdout)
if error:
    return error

return {"result": result.stdout}  # Raw LLM response
```

**Configurable Turn Limits:**

```python
# unified_llm.py
def invoke(self, prompt: str, max_turns: int = 1) -> str:
    """Invoke Claude with configurable turn limit"""
    cmd = ["claude", "prompt", f"--max-turns {max_turns}", ...]
    # ... rest of implementation

# Usage in header generation (prevents "max turns" errors)
self.unified_llm.invoke(prompt, max_turns=3)
```

**Tradeoffs:**

- **Gain:** Reliable output without CLI format bugs; proper error detection
- **Loss:** Cost/token metadata no longer available (acceptable for reliability)
- **Impact:** Text format returns raw LLM response directly (no JSON wrapper); turn limits prevent truncation errors

### Bulk Job Management UI

**Discard Selected Feature:**

- Toolbar button for bulk discarding selected jobs
- Confirmation dialog to prevent accidental actions
- Uses existing `/api/jobs/status/bulk` endpoint with `status: 'discarded'`
- Visual feedback: success/error toast notifications
- Discarded jobs hidden from default view, accessible via "discarded" status filter
- Selection state management via `selectedJobIds` Set, updateSelectionCount() tracks button enabled state

**Components:**

- `frontend/templates/index.html` - "Discard Selected" button and toolbar integration
- `frontend/templates/base.html` - `.btn-warning` styling and `markSelectedAsDiscarded()` function
- Leverages existing checkbox selection system and `/api/jobs/status/bulk` API

### Google Drive CV Upload

**Overview:** Seamless CV export to Google Drive with visual feedback and persistent tracking.

**Components:**

1. **Backend Endpoint** (`runner_service/routes/operations.py`)
   - `POST /operations/jobs/<job_id>/cv/upload-drive` - Triggers CV upload to Google Drive
   - Calls PDF service to generate CV if not cached
   - Posts to n8n webhook for Drive file creation
   - Updates MongoDB with `gdrive_uploaded_at` timestamp upon success

2. **Frontend Proxy** (`frontend/app.py`)
   - `POST /api/jobs/<job_id>/cv/upload-drive` - Flask proxy to runner service
   - Handles authentication and request forwarding
   - Returns status: `{'status': 'success'}` or `{'error': message}`

3. **UI Components** (3 button locations)
   - Job detail page: `frontend/templates/job_detail.html` - "Upload to Drive" button in Generated CV section
   - CV editor panel: `frontend/templates/components/cv_editor.html` - Button next to "Export PDF"
   - CV editor sidebar: `frontend/static/js/batch-sidebars.js` - Batch upload for multiple CVs

4. **Frontend Logic**
   - `frontend/static/js/cv-editor.js` - `uploadCVToGDrive()` function
   - `frontend/static/js/batch-sidebars.js` - `uploadBatchCVToGDrive()` function for batch operations
   - Visual feedback via CSS classes: `uploading` (orange pulse), `uploaded` (green check), `error` (red)
   - Button state persists via MongoDB `gdrive_uploaded_at` field (re-enable on page load)

5. **Styling** (`frontend/static/css/cv-editor.css`)
   - `.btn-gdrive.uploading` - Orange pulse animation during upload
   - `.btn-gdrive.uploaded` - Green background and checkmark icon (persists)
   - `.btn-gdrive.error` - Red background for failed uploads
   - Smooth transitions between states

**Data Flow:**

```
User clicks "Upload to Drive"
        ↓
uploadCVToGDrive() (cv-editor.js)
        ↓
POST /api/jobs/<job_id>/cv/upload-drive (Flask proxy)
        ↓
POST /operations/jobs/<job_id>/cv/upload-drive (runner service)
        ↓
PDF Service generates/retrieves PDF
        ↓
POST to n8n webhook (Google Drive creation)
        ↓
Update MongoDB: gdrive_uploaded_at = current_timestamp
        ↓
Return success, button changes to green
```

**MongoDB Schema Addition:**

- Field: `gdrive_uploaded_at` (datetime or ISO string)
- Location: Job document in `level-2` collection
- Purpose: Track when CV was last uploaded to Drive
- Used for: Button state persistence, audit trail

**Error Handling:**

- Failed PDF generation: Returns error message, button shows red state
- n8n webhook timeout: Logs error, button shows red state
- Network errors: Client-side retry with exponential backoff

**Integration Points:**

- n8n webhook endpoint: Called for Google Drive file creation
- PDF service: Generates/retrieves tailored CV for upload
- MongoDB: Stores upload timestamp for state persistence

**Files Changed:**

- `runner_service/routes/operations.py` - `upload_cv_to_gdrive()` endpoint
- `frontend/app.py` - `/api/jobs/<job_id>/cv/upload-drive` proxy
- `frontend/templates/job_detail.html` - Upload button in CV section
- `frontend/templates/components/cv_editor.html` - Upload button in editor
- `frontend/static/css/cv-editor.css` - Button states and animations
- `frontend/static/js/cv-editor.js` - `uploadCVToGDrive()` function
- `frontend/static/js/batch-sidebars.js` - `uploadBatchCVToGDrive()` function

### Job Ingestion Management Page

**New `/ingestion` Page:**

- Dedicated UI for managing job ingestion runs and viewing ingestion history
- Displays run history with status, timestamps, and source information
- Accessible via header navigation link in `base.html`

**Backend Endpoints:**

- `GET /ingest/history/{source}` - Returns last 50 ingestion runs for a given source
  - Response: List of run records with metadata (timestamp, status, job count, errors)
  - Storage: MongoDB `system_state` collection with TTL-based retention
  - Performance: Indexed queries on source and timestamp for fast retrieval

**Data Model:**

- MongoDB `system_state` collection stores ingestion run history
- Each run record includes: source, timestamp, status, job_count, errors, run_duration
- Last 50 runs per source retained for audit and debugging

**Components:**

- `frontend/templates/ingestion.html` - Ingestion management UI
- `frontend/app.py` - Route handler for `/ingestion` page
- `frontend/runner.py` - Proxy routes for history endpoint
- `runner_service/routes/job_ingest.py` - History endpoint implementation
- `src/services/job_ingest_service.py` - Run history storage and retrieval logic

## Backend Architecture

### Pipeline Orchestration

- LangGraph state machine coordinating 7 layers
- Async-safe execution for event loop compatibility
- Error handling and recovery at each layer

### Service Layer

- StructureJDService: JD analysis with callbacks
- CVMappingService: Coverage calculation
- CompanyResearchService: Smart caching with fallback
- ContactDiscoveryService: Enriched contact mapping

### Database Layer

- MongoDB for persistent state
- Indexed queries on job_id and cv_section
- TTL indexes for cache expiration

## Configuration (Feature Flags)

All config via environment variables:

```bash
# Pipeline
PIPELINE_TIMEOUT=300
ENABLE_VERBOSE_LOGGING=true

# Services
COMPANY_RESEARCH_CACHE_TTL=604800  # 1 week
ENABLE_PEOPLE_MAPPER=true

# Integrations
FIRECRAWL_API_KEY=...
OPENROUTER_API_KEY=...
MONGODB_URI=...
```

## External Services

- **FireCrawl**: Web scraping for company research
- **OpenRouter**: LLM for JD analysis, gap identification
- **MongoDB**: State persistence
- **Google Drive**: CV/cover letter storage

## Error Handling & Recovery

### Nested Event Loop Errors (FIXED)

- Scenario: Async CV generation called from sync routes
- Solution: ThreadPoolExecutor wrapper in orchestrator
- Impact: Eliminates "RuntimeError: running event loop" crashes

### Cache Consistency (IMPROVED)

- Scenario: Partial cache hit in company research
- Solution: Check completeness before cache return
- Impact: More comprehensive contact discovery

### Progress Visibility (ENHANCED)

- Scenario: Long JD processing with no feedback
- Solution: progress_callback and log_callback in service layer
- Impact: Real-time user feedback on processing status

## Data Flow Examples

### JD Processing with Coverage Tracking

```
1. Upload JD → StructureJDService.execute(jd, progress_callback, log_callback)
2. Extract sections → Mark with data-section attributes
3. Update frontend → Coverage display via updateCoverage()
4. Map to CV → Section-level matching
5. Display results → User sees aligned requirements
```

### Contact Discovery with Smart Cache

```
1. Company research triggered
2. Check MongoDB cache
3. If cached + has contacts → return (full cache hit)
4. If cached + no/partial contacts → call people_mapper
5. Merge results → return comprehensive contact list
```

### CV Generation with Safe Async

```
1. User requests CV generation
2. orchestrator._run_async_safely(async_cv_gen_coro)
3. ThreadPoolExecutor spawns new event loop
4. Async operation completes safely
5. Result returned to caller without event loop conflicts
```

## See Also

- `ROADMAP.md` - Overall project direction
- `missing.md` - Implementation gaps tracker
- `next-steps.md` - Immediate action items
