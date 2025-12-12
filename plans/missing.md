# Implementation Gaps

**Last Updated**: 2025-12-12 (Session 9: LinkedIn Copy Button Fix)

> **See also**: `plans/architecture.md` | `plans/next-steps.md` | `bugs.md`

---

## Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **P0 (CRITICAL)** | 3 (3 documented/fixed) | Must fix immediately - system broken or data integrity at risk |
| **P1 (HIGH)** | 19 (17 fixed, 0 open) | Fix this week - user-facing bugs or important features |
| **P2 (MEDIUM)** | 38 (32 fixed, 0 open) | Fix this sprint - enhancements and incomplete features |
| **P3 (LOW)** | 23 (17 fixed, 0 open) | Backlog - nice-to-have improvements |
| **Total** | **83** (69 fixed/documented, 10 open → 6 open after E2E annotation) | All identified gaps |

**Test Coverage**: 1521 tests passing (1095 before + 426 new pipeline overhaul tests), 35 skipped, E2E tests pending

---

### Today's Session (2025-12-12 Session 9): LinkedIn Copy Button Fix + Visual Feedback

**BUG FIX 9: LinkedIn recruiter contact card copy buttons broken - FIXED**:
- **Issue**: Copy buttons on LinkedIn recruiter contact cards failed silently when messages contained single quotes (e.g., "I'd") or newlines
- **Root Cause**: Jinja `| e` (HTML escape) filter was escaping quotes and special characters incorrectly for JavaScript context. Single quotes broke onclick handler syntax: `onclick="copyToClipboard('I'd like to...')"` became malformed
- **Fix Applied**:
  - Replaced `| e` filter with `| tojson` on all 4 copy button handlers in `frontend/templates/job_detail.html` (lines 1392, 1408, 1469, 1485)
  - `tojson` properly escapes for JavaScript string literals instead of HTML
  - Enhanced `copyToClipboard()` function in `frontend/static/js/job-detail.js` to show visual feedback:
    - Button displays checkmark icon and "Copied!" text for 2 seconds
    - Provides user confirmation that copy operation succeeded
- **Files Modified**:
  - `frontend/templates/job_detail.html` - Fixed Jinja escaping from `| e` to `| tojson` on 4 onclick handlers, added `this` parameter
  - `frontend/static/js/job-detail.js` - Enhanced `copyToClipboard()` with button feedback (icon swap + text change with auto-revert)
- **Test Coverage**: Existing contact card tests continue to pass. Copy button now handles special characters and newlines correctly.
- **Impact**: LinkedIn recruiter messages now copy reliably regardless of content; users get immediate visual confirmation of successful copy

---

### Today's Session (2025-12-10 Session 4): SSE Streaming for Operations

**SSE Streaming Feature Implemented**:
- **Feature**: Server-Sent Events streaming for smaller pipeline operations (research-company, generate-cv, full-extraction)
- **Architecture**: Three-layer streaming system (FastAPI → Flask proxy → Frontend EventSource)
- **Files Created**:
  - `runner_service/routes/operation_streaming.py` - NEW: SSE infrastructure with `OperationState` dataclass and stream_operation_logs() generator
- **Files Modified**:
  - `runner_service/routes/operations.py` - Added stream endpoints for research-company, generate-cv, full-extraction + /operations/{run_id}/logs SSE proxy + /operations/{run_id}/status polling fallback
  - `frontend/runner.py` - Added Flask proxy routes for SSE streaming
  - `frontend/static/js/pipeline-actions.js` - Added executeWithSSE() method and EventSource API integration with polling fallback
- **API Endpoints** (new streaming endpoints):
  - `POST /{job_id}/research-company/stream` - Stream research-company operation with SSE logs
  - `POST /{job_id}/generate-cv/stream` - Stream CV generation with SSE logs
  - `POST /{job_id}/full-extraction/stream` - Stream full extraction with SSE logs
  - `GET /operations/{run_id}/logs` - SSE streaming endpoint for operation logs
  - `GET /operations/{run_id}/status` - Polling fallback endpoint for operation status
- **Frontend Features**:
  - In-memory operation state tracking with `_operation_runs` dict
  - Log/layer status management helpers
  - EventSource with automatic retry and polling fallback for browser compatibility
  - Real-time progress updates during long-running operations
- **Backward Compatibility**: Existing synchronous endpoints remain unchanged; streaming endpoints are opt-in

### Today's Session (2025-12-11 Session 6): SSE Streaming Progress Callbacks - BUG 8 Fixed

**BUG 8: Extract JD and Research operations timeout before completing - FIXED**:
- **Issue**: Full extraction and research operations timed out with "Runner service timeout" error during SSE streaming
- **Root Cause**: Services were not emitting intermediate progress updates during long LLM processing (2-5 minutes). SSE stream was idle, frontend thought operation stalled
- **Fix Applied**: Added `progress_callback` parameter to all three operation services with real-time progress emission at each step
  - `FullExtractionService`: Emits progress for jd_processor, jd_extractor, pain_points, fit_scoring, save_results
  - `CompanyResearchService`: Emits progress for fetch_job, cache_check, company_research, role_research, people_research, save_results
  - `CVGenerationService`: Emits progress for fetch_job, validate, build_state, cv_generator, persist
  - Streaming endpoints updated to pass `layer_cb` as `progress_callback`
- **Files Modified**:
  - `src/services/full_extraction_service.py` - Added progress_callback + emit_progress()
  - `src/services/company_research_service.py` - Added progress_callback + emit_progress()
  - `src/services/cv_generation_service.py` - Added progress_callback + emit_progress()
  - `runner_service/routes/operations.py` - Updated stream endpoints to pass progress_callback
- **Impact**: Operations now send continuous SSE updates, preventing frontend timeout during long LLM processing. Console logs appear in real-time during execution.
- **Test Coverage**: All 115 service-related unit tests pass. All 1598 unit tests pass.

### Today's Session (2025-12-11 Session 5): Annotation System Improvements

**Source-Based Weighting for Annotations** (P0.2):
- **Feature**: Human annotations now weighted 20% higher than LLM suggestions
- **Implementation**: Added `SOURCE_MULTIPLIERS` dict in `src/common/annotation_types.py`:
  - Human annotations: 1.2x multiplier
  - Preset templates: 1.1x multiplier
  - Pipeline suggestions: 1.0x multiplier (baseline)
- **Files Modified**: `src/common/annotation_boost.py` - Updated `calculate_boost()` to include source dimension in scoring
- **Impact**: Manual annotations have greater influence on downstream scoring (pain points, fit scores, STAR selection)

**Persona SYSTEM Prompt Migration** (P0.3):
- **Problem**: Persona was injected into USER prompts, inconsistent framing across outputs
- **Solution**: Moved persona from USER to SYSTEM prompts for stronger, more consistent LLM framing
- **Implementation**:
  - Added `_build_profile_system_prompt_with_persona()` helper in `src/layer6_v2/header_generator.py`
  - Added `_build_cover_letter_system_prompt_with_persona()` helper in `src/layer6_v2/cover_letter_generator.py`
  - Persona now injected into SYSTEM prompt for all CV and cover letter generation
- **Files Modified**: `src/layer6_v2/header_generator.py`, `src/layer6_v2/cover_letter_generator.py`
- **Impact**: More coherent and consistent persona expression across all LLM outputs

**Global CLI Panel - AWS/GCP CloudShell-style Terminal Interface** (P1.0 - NEW):
- **Feature**: Persistent, collapsible CLI bar at bottom of every page showing real-time pipeline logs via SSE streaming
- **Architecture**: Event-driven decoupling between pipeline-actions.js and cli-panel.js using custom Alpine.js store
- **Files Created**:
  - `frontend/templates/components/cli_panel.html` - Alpine.js-based HTML template with terminal UI
  - `frontend/static/js/cli-panel.js` - Alpine store with event handling, sessionStorage persistence, debounced saves
  - `frontend/static/css/cli-panel.css` - Terminal-themed dark styles (monospace font, color-coded logs)
- **Files Modified**:
  - `frontend/templates/base.html` - Added CSS/JS includes and CLI panel HTML include outside #htmx-main (persists across partial refreshes)
  - `frontend/static/js/pipeline-actions.js` - Refactored to dispatch custom events instead of direct panel function calls:
    - `cli:start-run` - Initializes new pipeline run in CLI panel
    - `cli:log` - Streams individual log entries with timestamps
    - `cli:layer-status` - Updates layer progress footer with completion status
    - `cli:complete` - Marks run as complete and preserves logs
    - `ui:refresh-job` - Replaces page reloads with HTMX partial refresh
  - `frontend/static/js/job-detail.js` - Added `ui:refresh-job` event handler for HTMX swaps
  - `frontend/templates/job_detail.html` - Updated tieredActionButton to pass jobTitle parameter for CLI context
- **Key Features**:
  - Multi-run support with tabs (up to 10 concurrent runs)
  - Auto-scroll logs with color-coded output (errors=red, warnings=yellow, success=green)
  - Layer status footer showing real-time pipeline progress (Layers 1-7)
  - Copy logs and clear logs buttons
  - Toast notifications when panel collapsed (prevents missed updates)
  - Keyboard shortcut: Ctrl+` (backtick) to toggle panel visibility
  - sessionStorage persistence with debounced saves (logs survive page navigation)
  - HTMX partial refresh preserves CLI state (panel positioned outside swap target div)
- **Technical Details**:
  - Alpine.js store pattern for reactive state management
  - EventSource-based SSE integration with automatic polling fallback
  - Debounced save (500ms) to sessionStorage for performance
  - Terminal-style styling with dark background, monospace font, color-coded text
- **Impact**: Users see real-time pipeline execution across all pages without page reloads; logs persist during navigation; professional AWS/GCP-style UX
- **Test Coverage**: Unit tests for event dispatch, sessionStorage persistence, and tab management

**Suggest Strengths Feature** (P1.1):
- **Feature**: New "Strengths" button in annotation panel with AI-powered strength suggestions
- **Architecture**: New `StrengthSuggestionService` in `src/services/strength_suggestion_service.py`
- **API Endpoint**: `POST /api/jobs/{job_id}/suggest-strengths` - Returns suggested strength skills with patterns and LLM analysis
- **Frontend Integration** (`frontend/static/js/jd-annotation.js`):
  - "Strengths" button in annotation popover panel
  - Modal dialog displays suggested strengths from LLM analysis
  - Patterns: 20+ hardcoded skill patterns (Python, AWS, K8s, Docker, leadership, communication, etc.)
  - LLM analysis for deeper semantic matches beyond pattern matching
- **Files Created/Modified**:
  - `src/services/strength_suggestion_service.py` - NEW service with pattern and LLM-based suggestion logic
  - `frontend/static/js/jd-annotation.js` - Added suggestStrengths() method and modal rendering
- **Impact**: Users can quickly discover relevant skills from JD without manual analysis

**ATS Keyword Placement Validator** (P1.2):
- **Feature**: Validates that keywords appear in high-visibility CV sections for ATS optimization
- **Architecture**: New `KeywordPlacementValidator` in `src/layer6_v2/keyword_placement.py`
- **Scoring Rules**:
  - Headline section: 40 points (highest priority)
  - Narrative section: 30 points
  - Competencies/Skills section: 20 points
  - First role description: 10 points (lowest priority)
  - Passing score: 70+ points (covers multiple sections)
- **Output**:
  - `ATS violations` - Keywords missing from priority sections
  - `improvement_suggestions` - Specific placement recommendations
- **Integration**:
  - Enhanced CV generation prompts with explicit ATS placement rules
  - Validation runs post-generation to identify and suggest improvements
  - Results included in CV output for user feedback
- **Files Created/Modified**:
  - `src/layer6_v2/keyword_placement.py` - NEW validator with placement scoring logic
  - `src/layer6_v2/types.py` - Added `KeywordPlacementResult` type
- **Impact**: CVs now optimized for ATS parsing with keywords in strategic positions; users receive actionable improvement suggestions

**E2E Annotation Integration Complete** (GAP-085 to GAP-094 - All DONE 2025-12-10):
| GAP ID | Title | Priority | Status | Completed |
|--------|-------|----------|--------|-----------|
| GAP-085 | Company/Role Research Not Annotation-Aware | P2 | ✅ COMPLETE | Phase 4 |
| GAP-086 | People Mapper Not Annotation-Aware | P3 | ✅ COMPLETE | Phase 8 |
| GAP-087 | Interview/Outcome Not Using Annotations | P2 | ✅ COMPLETE | Phase 5 |
| GAP-088 | Cover Letter Passion/Identity Not Used | P1 | ✅ COMPLETE | Phase 3 |
| GAP-089 | ATS Keyword Coverage Not Validated | P2 | ✅ COMPLETE | Phase 6 |
| GAP-090 | STAR Selector Annotation Boost Disabled | P2 | ✅ COMPLETE | Phase 2 |
| GAP-091 | Outreach Not Annotation-Aware | P2 | ✅ COMPLETE | Phase 7 |
| GAP-092 | Reframe Application Not Traced | P3 | ✅ COMPLETE | Phase 9 |
| GAP-093 | Section Coverage Not Enforced | P3 | ✅ COMPLETE | Phase 10 |
| GAP-094 | Review Workflow Not Implemented | P3 | ✅ COMPLETE | Phase 11 |

### New Features Added (not in original gaps)
- **Bulk "Mark as Applied"**: Select multiple jobs → click "Mark Applied" → updates status for all
- **Identity-Based Persona Generation** (2025-12-10): Transform identity annotations into coherent persona statements injected into CV, cover letter, and outreach

### Today's Fixes (2025-12-10) Session 3

**LLM-Based JD Processor - Intelligent Parsing Enhancement**:
- **Problem Solved**: Original JD text from job boards arrives as compressed blob with escape characters stripped, section headers run directly into content (e.g., "ABOUT THE ROLEThe company is...")
- **Solution**: Switched to LLM-based parsing with "HR document analyst" expert system prompt
- **Model Selection**:
  - Default: `google/gemini-flash-1.5-8b` (cheap OpenRouter model, 8B parameters, fast)
  - Fallback: `gpt-4o-mini` (OpenAI) if OpenRouter API key not available
  - Removed regex-based fallback completely - LLM is now the only parser
- **Enhancements** (`src/layer1_4/jd_processor.py`):
  - Updated system prompt with expert "HR document analyst with 20 years experience" persona
  - Increased input limit from 8,000 to 12,000 characters for longer JDs
  - Removed `use_llm` parameter deprecation - always uses LLM (parameter kept for backward compatibility)
  - System prompt guides LLM to identify semantic section boundaries even in unformatted text
  - Handles: Headers merged with content, bullet points inline, line breaks stripped, multiple sections collapsed
- **Section Categories Supported**: about_company, about_role, responsibilities, qualifications, nice_to_have, technical_skills, experience, education, benefits, other
- **Frontend Fallback** (`frontend/app.py`):
  - Lightweight regex-based `normalize_section_headers()` fallback kept for Vercel deployments where LangChain imports fail
  - Ensures annotation UI has structured content even if backend LLM unavailable
- **Files Changed**: `src/layer1_4/jd_processor.py`, `frontend/app.py`
- **Impact**: JD sections now correctly parsed from compressed/blob JD text, enabling accurate annotation and better downstream layer intelligence

**CV Generation - ATS Variants List Index Safety Check**:
- **Bug**: CV generation failed with "list index out of range" error when accessing `p.ats_variants[0]` in `HeaderGenerationContext` properties
- **Root Cause**: Three properties (`top_keywords`, `identity_keywords`, `passion_keywords`) in `src/layer6_v2/types.py` accessed the first element of `ats_variants` list without validating the list was non-empty
- **Fix Applied**: Added defensive checks `and len(p.ats_variants) > 0` before accessing `[0]` index in:
  - `HeaderGenerationContext.top_keywords` property
  - `HeaderGenerationContext.identity_keywords` property
  - `HeaderGenerationContext.passion_keywords` property
- **Files Changed**: `src/layer6_v2/types.py`
- **Impact**: CV generation no longer crashes when persona has empty ATS variants list; gracefully handles edge cases with empty variant lists

### Today's Fixes (2025-12-10) Session 2

**JD Extractor Integration - Full Extraction Service Enhancement**:
- **Schema Alignment Fix**: `JDExtractor` now outputs structured intelligence (role_category, responsibilities, keywords, etc.) matching expected output format
- **Layer Consolidation**: Renamed `_run_layer_1_4()` to `_run_jd_processor()` for clarity, added new `_run_jd_extractor()` method
- **Dual Output Storage**: Service now persists both `processed_jd` (HTML sections for annotation UI) and `extracted_jd` (structured intelligence for template display)
- **Per-Layer Status Tracking**: Added `layer_status` dict for detailed pipeline logging and layer-specific error reporting
- **Annotation Aggregation**: New `_aggregate_annotations()` method computes weighted fit scores from manual annotations
- **Files Changed**: `src/services/full_extraction_service.py`
- **Impact**: Extract JD button now properly displays structured intelligence from JD Extractor, fixes schema mismatch bugs

**PDF Export Module Import Fix**:
- **Issue**: `src/api/pdf_export.py` import error when running from frontend context
- **Fix**: Changed to `TYPE_CHECKING` conditional import pattern for `JobState`
- **Files Changed**: `src/api/pdf_export.py`
- **Impact**: Dossier export functionality restored, no module import errors

**Annotation Insights Heatmap UI Enhancement**:
- **Visual Heatmap**: "Opportunity & Fit Analysis" section now shows colored bar (green/yellow/red) proportional to manual annotation match counts
- **Match Score Display**: Shows "Match X%" derived from annotation counts
- **Gap Warnings**: Displays must-have gaps alert when present
- **Files Changed**: `frontend/templates/job_detail.html`
- **Impact**: Users get visual feedback on how well their annotations match the JD

**Research/CV Button Proxy Routes**:
- **Routes Added**: `/api/jobs/<job_id>/research-company` and `/api/jobs/<job_id>/generate-cv` proxy endpoints
- **Implementation**: Forward requests to VPS runner service with Bearer token authentication
- **Error Handling**: Proper error propagation and status codes
- **Files Changed**: `frontend/app.py`
- **Impact**: Research and Generate CV buttons now functional from job detail page

**Annotation System Enhancements - Passion & Identity Dimensions**:
- **New Annotation Dimensions**:
  - `passion_level`: 5-level scale (love_it, enjoy, neutral, tolerate, avoid) - captures candidate enthusiasm for role/company
  - `identity_level`: 5-level scale (core_identity, strong_identity, developing, peripheral, not_identity) - captures professional identity alignment
- **Layer 2 Pain Point Miner - Annotation-Aware** (`src/layer2/pain_point_miner.py`):
  - Extracts annotation context: must_have_keywords, gap_areas, reframe_notes, core_strength_areas
  - Passes annotation priorities to LLM prompt for pain point generation
  - Post-processes pain points to boost must-haves and deprioritize gaps
- **Layer 4 Fit Scorer - Uses Annotation Signal** (`src/layer4/annotation_fit_signal.py`):
  - New `AnnotationFitSignal` class blending LLM score with annotation signal (70% LLM, 30% annotation)
  - Detects and flags disqualifiers from annotations
  - Returns `annotation_analysis` in output with confidence levels
- **Boost Calculator Enhanced** (`src/common/annotation_boost.py`):
  - Added passion and identity multipliers for enhanced scoring
  - New methods: `get_passions()`, `get_avoid_areas()`, `get_identity_core()`, `get_identity_not_me()`
  - Stats now include passion and identity dimension counts
- **Header Context Enhanced** (`src/layer6_v2/types.py`):
  - `AnnotationPriority` and `HeaderGenerationContext` now include passion/identity fields
  - New properties: `passion_priorities`, `avoid_priorities`, `identity_priorities`, `identity_keywords`, `passion_keywords`
  - `format_priorities_for_prompt()` now includes passion/identity sections in prompt injection
- **UI Updated** (`frontend/templates/partials/job_detail/_annotation_popover.html`, `frontend/static/js/jd-annotation.js`):
  - Passion and identity button groups in annotation popover for comprehensive candidate preferences
  - Handlers for setPopoverPassion and setPopoverIdentity actions
- **Files Changed/Created**:
  - `src/layer2/pain_point_miner.py` - Added annotation context extraction
  - `src/layer4/annotation_fit_signal.py` - NEW file with annotation-aware fit scoring
  - `src/common/annotation_boost.py` - Enhanced with passion/identity methods
  - `src/layer6_v2/types.py` - Extended context types
  - `frontend/templates/partials/job_detail/_annotation_popover.html` - UI enhancements
  - `frontend/static/js/jd-annotation.js` - Handler methods
- **Impact**: Annotation system now captures full candidate preference spectrum (passion levels) and professional identity alignment, enabling more nuanced job matching and personalized outreach

**Identity-Based Persona Generation System** (NEW FEATURE - 2025-12-10):
- **Purpose**: Transform identity annotations into coherent persona statements for hyper-personalized CVs, cover letters, and outreach
- **Core Module** (`src/common/persona_builder.py` - NEW):
  - `SynthesizedPersona` dataclass for storing persona data
  - `PersonaBuilder` class with LLM synthesis method: `synthesize_from_annotations()`
  - `get_persona_guidance()` convenience function for prompt injection
  - 33 unit tests covering synthesis, validation, and edge cases
- **Data Flow**:
  - Extract identity annotations (core_identity, strong_identity, developing)
  - LLM synthesizes coherent persona statement (e.g., "Solutions architect who leads engineering teams through complex cloud transformations")
  - UI preview with optional user editing
  - Save to MongoDB `jd_annotations.synthesized_persona`
  - Inject persona into CV, cover letter, and outreach
- **API Endpoints** (`frontend/app.py`):
  - `POST /api/jobs/<id>/synthesize-persona` - Generate persona from identity annotations
  - `POST /api/jobs/<id>/save-persona` - Save user-edited persona
- **UI Components** (`frontend/static/js/jd-annotation.js`):
  - Persona panel with synthesis button
  - Live preview with markdown formatting
  - Edit textarea for user refinement
  - Save/cancel buttons with status feedback
- **Pipeline Integration**:
  - Layer 6 (Header Generator): Injects persona into CV profile section for central theme
  - Layer 6 (Cover Letter): Frames passion/identity section with "As a [persona]..." opening
  - Layer 5 (People Mapper): Positions persona in outreach message opener
  - Layer 6 (Ensemble): Passes jd_annotations to header generators for persona access
- **Files Created**:
  - `src/common/persona_builder.py` - PersonaBuilder module (NEW)
  - `tests/unit/test_persona_builder.py` - Comprehensive test suite (NEW)
- **Files Modified**:
  - `frontend/app.py` - Added synthesis and save endpoints
  - `frontend/static/js/jd-annotation.js` - Added UI component and state management
  - `frontend/templates/partials/job_detail/_jd_annotation_panel.html` - Added persona panel container
  - `src/layer6_v2/header_generator.py` - Injects persona into CV profile
  - `src/layer6_v2/ensemble_header_generator.py` - Passes jd_annotations
  - `src/layer6_v2/orchestrator.py` - Passes jd_annotations to generators
  - `src/layer6/cover_letter_generator.py` - Injects persona at start of passion section
  - `src/layer5/people_mapper.py` - Injects persona in outreach context
- **Impact**: CVs and outreach now reflect authentic professional persona derived from candidate's identity annotations, enabling deeper personal connection while maintaining grounding in actual professional identity claims

---

### Today's Fixes (2025-12-10) Session 1

**Master CV Editor Page Implemented (Full-Page Tab-Based Editor)**:
- **Frontend Page** (`frontend/templates/master_cv.html`): Main editor page with 3-tab navigation
  - Tab 1: Candidate Info (personal details, location, availability)
  - Tab 2: Work Experience (role editor with TipTap rich text for achievements)
  - Tab 3: Skills Taxonomy (accordion-based skill categories editor)
- **Partial Templates** (7 files):
  - `frontend/templates/partials/master_cv/_candidate_tab.html` - Candidate info form with auto-save
  - `frontend/templates/partials/master_cv/_roles_tab.html` - Two-panel role editor (list + editor)
  - `frontend/templates/partials/master_cv/_taxonomy_tab.html` - Accordion taxonomy editor with chips
  - `frontend/templates/partials/master_cv/_version_history_modal.html` - Version history with rollback
  - `frontend/templates/partials/master_cv/_delete_confirm_modal.html` - Delete confirmation dialog
- **Editor JavaScript** (`frontend/static/js/master-cv-editor.js` - 1100 lines):
  - MasterCVEditor class with full state management
  - 3-second debounced auto-save with visual save indicator
  - TipTap rich-text editor integration for role achievements
  - Chip-based array editing (languages, certifications, keywords, skills)
  - Version history with rollback capability
  - Delete confirmation with 2-second safety delay
  - Keyboard shortcuts (Ctrl+S to save, Escape to cancel)
  - Error handling and retry logic
- **Editor Styles** (`frontend/static/css/master-cv-editor.css`):
  - Tab navigation styling with active state indicators
  - Two-panel layout for role editor (responsive)
  - Chip styles for array data (tags, languages, skills)
  - Form controls and input validation visual feedback
  - Modal and version history list styling
  - "Use with caution" warning banner styling
- **Frontend Routes** (`frontend/app.py`):
  - Added `GET /master-cv` route returning master_cv.html template
  - Loads MongoDB data via existing API endpoints: `/api/master-cv/*`
- **UI Integration** (`frontend/templates/base.html`):
  - Added "Master CV" button to main navigation menu
  - Links to `/master-cv` page
- **Data Source**: All data from MongoDB collections:
  - `master_cv_metadata` (candidate info, status)
  - `master_cv_taxonomy` (skill categories, taxonomy)
  - `master_cv_roles` (work experience, achievements)
- **API Integration**: Uses existing endpoints `/api/master-cv/*` (no new backend routes needed)
- **Features**:
  - Auto-save with visual feedback (3-second debounce)
  - Version history with timestamps and rollback
  - Rich text editing for role achievements (TipTap)
  - Chip-based editing for arrays (languages, certifications, keywords, skills)
  - Delete confirmation with safety delay (2 seconds)
  - "Use with caution" warning banner
  - Keyboard shortcuts for power users
  - Error recovery with retry logic
  - No page reload needed (AJAX-based)

**Full Extraction Service Implemented (Layer 1.4 + Layer 2 + Layer 4 Combined)**:
- **Full Extraction Service** (`src/services/full_extraction_service.py`): NEW service combining JD structuring (Layer 1.4), pain point mining (Layer 2), and fit scoring (Layer 4)
  - Single operation that runs all three layers in sequence
  - Returns: structured JD, pain points, fit score in one call
  - Enables cost-optimized analysis without running full 7-layer pipeline
  - 25 lines POST endpoint for `full-extraction` in `runner_service/routes/operations.py`

- **Structure JD Service Reverted** (`src/services/structure_jd_service.py`): Now runs ONLY Layer 1.4 (JD formatting)
  - Triggered from JD Annotator panel's "Structure JD" button
  - Separate from full extraction for granular control

- **UI Enhancements**:
  - Added purple "Extract JD" button (btn-action-accent) for full extraction in `frontend/templates/job_detail.html`
  - Updated keyboard shortcuts: Alt+1 (Structure), Alt+2 (Extract), Alt+3 (Research), Alt+4 (Generate CV)
  - Added btn-action-accent CSS styling in `frontend/static/css/pipeline-actions.css`
  - Full extraction support in Alpine.js store in `frontend/static/js/pipeline-actions.js`

- **Bug Fixes**:
  - Fixed LinkedIn import environment variable mismatch in `frontend/app.py` line 793: Changed `RUNNER_TOKEN` to `RUNNER_API_SECRET` to match `.env.example`

**Files Created** (Pipeline Overhaul Phase 1-3):
- `src/common/model_tiers.py` - 3-tier model system (Fast/Balanced/Quality)
- `src/services/operation_base.py` - Base class for operations with health checks and retries
- `src/services/full_extraction_service.py` - Full JD extraction + pain mining + fit scoring
- `frontend/static/css/pipeline-actions.css` - Button and state styling
- `frontend/static/js/pipeline-actions.js` - Alpine.js state management for action buttons
- `runner_service/routes/operations.py` - Independent operation endpoints
- `runner_service/routes/__init__.py` - Router registration

**Files Modified**:
- `src/services/structure_jd_service.py` - Reverted to Layer 1.4 only (JD formatting)
- `frontend/static/js/jd-annotation.js` - applyHighlights() fully implemented with proper DOM targeting
- `frontend/templates/job_detail.html` - Added full-extraction button and tier selector
- `frontend/static/js/pipeline-actions.js` - Added full-extraction API function and store tracking
- `frontend/static/css/pipeline-actions.css` - Added btn-action-accent styling
- `frontend/app.py` - Added proxy route for full-extraction, fixed RUNNER_TOKEN bug
- `runner_service/app.py` - Integrated operation routes

**Tests Added**:
- `tests/unit/test_model_tiers.py` - 46 unit tests for model tier system
- `tests/unit/test_operation_base.py` - 22 unit tests for operation base class

**Phase 4 Complete** (5 commits):
- `src/services/structure_jd_service.py` - JD extraction service
- `src/services/cv_generation_service.py` - CV generation service
- `src/services/company_research_service.py` - Company/role research with caching
- Operations wired to API endpoints (no longer stubbed)
- 3 service test files with comprehensive coverage

**Phase 5 Complete** (4 commits):
- `src/services/outreach_service.py` - Per-contact outreach generation
- `runner_service/routes/contacts.py` - Contacts CRUD and outreach API
- Per-contact Generate Connection/InMail buttons in UI
- 49 tests for OutreachGenerationService

**Pipeline Overhaul Summary** (17 commits total):
- Phases 1-3: 8 commits (model tiers, operation base, heatmap fix, buttons, routes)
- Phase 4: 5 commits (services implementation)
- Phase 5: 4 commits (contacts & outreach decoupling)

### Today's Fixes (2025-12-09)

**Job Detail Page Frontend Fixes (4 Issues)**:
1. **Job Description Button Not Visible**: Fixed field normalization in `frontend/app.py` - `serialize_job()` now normalizes both `job_description` and `jobDescription` to `description`
2. **Progress Bar Goes Backwards**: Fixed monotonic tracking in `frontend/static/js/job-detail.js` - Added `highestLayerReached` to ensure progress only moves forward, improved regex patterns to avoid false positives
3. **CV Not Displayed After Pipeline**: Added disk fallback in `frontend/app.py` `get_cv_editor_state()` and warning logging in `src/layer7/output_publisher.py` for missing cv_text
4. **JD Annotation Editor Not Visible**: Fixed button implementation - `frontend/templates/job_detail.html` now passes jobId to `openAnnotationPanel()`, `frontend/static/js/jd-annotation.js` reads jobId from data attribute as fallback

**Prompt Optimization (GAP-030 - COMPLETE)**:
- **Layer 7 Interview Predictor**: 22 unit tests validating question quality, distribution, and format
  - Added `validate_question_quality()` function for filtering low-quality questions
  - Enhanced system prompt with few-shot examples, yes/no detection, length validation
  - Tests: question quality validation, yes/no detection, type distribution, source attribution
- **Layer 6a Cover Letter Generator**: 24 unit tests validating citations and content quality
  - Enhanced system prompt with explicit STAR citation rules (CORRECT/WRONG examples)
  - Added 12-phrase generic blocklist ("diverse team", "best practices", "synergy", etc.)
  - Implemented pain point mapping requirements and anti-hallucination checklist
  - Tests: source citation rules, generic phrase detection, pain point mapping, quality gates
- **Integration**: All 1275 unit tests passing, prompts integrated into production pipeline

**Previous Phase 7 Fixes** (documented earlier):
- Phase 7 Interview Predictor backend completed
- Phase 7 Outcome Tracker backend completed
- Phase 7 Frontend panels (interview_prep_panel.html, outcome_tracker.html)
- Total Phase 7: 118 tests (30 interview + 28 outcome + 25 types + 35 edge cases)

### Today's Fixes (2025-12-08)

- **Pipeline UI Horizontal Layout**: Converted vertical pipeline steps to horizontal with progress line and icons
- **Meta-Prompt Endpoint Fix**: Fixed "db not defined" error in meta-prompt route
- **CV Save Display Refresh**: Added renderCVPreview() call after successful save for immediate visual feedback
- **Skills Hallucination Fix - Profile**: Added keyword grounding filter to only use JD keywords with evidence
- **Skills Hallucination Fix - Improver**: Updated IMPROVEMENT_STRATEGIES with anti-hallucination rules

### Today's Fixes (2025-12-01)
- **GAP-007**: Time filters now include hidden datetime inputs for hour-level precision
- **GAP-007 (UTC Fix)**: Fixed timezone mismatch - JS now uses UTC methods to match MongoDB UTC dates
- **GAP-009**: CV display now checks both `cv_text` and `cv_editor_state`
- **GAP-012**: Bold/italic markdown parsing now works in CV text conversion
- **GAP-014**: Middle East relocation tagline added automatically to CVs
- **GAP-025**: V2 Prompts verified as already implemented (validation running as warnings)
- **GAP-026**: CV spacing reduced by 20% for more compact layout
- **GAP-028**: Runner terminal copy button verified as already implemented
- **GAP-033**: Dossier PDF Export - complete job dossier exportable with 9 sections
- **GAP-040**: Swagger API documentation added at `/api-docs` and `/api/docs` (both routes work)
- **GAP-042**: Performance benchmarks - target latencies documented, benchmark test suite created
- **GAP-051**: Contact discovery improved with company name variations
- **GAP-052**: Page break visualization verified as already implemented
- **GAP-054**: CV display now matches editor exactly (headings, colors, borders)
- **GAP-056**: Contact management (delete/copy/import) verified as already implemented
- **GAP-058**: Button sizing hierarchy refined with btn-xs class
- **GAP-064**: appliedOn timestamp now set when marking jobs as applied
- **GAP-066**: Token tracking callbacks - LLM factory with automatic token tracking across 17 layers
- **GAP-022**: Pipeline progress UI verified as already implemented (7-layer stepper)
- **Postman Collection**: Added runner API collection at `postman/Job-Search-Runner-API.postman_collection.json`
- **MongoDB $project Bug**: Fixed aggregation pipeline error - removed exclusion from inclusion projection
- **Default 1h Filter**: Dashboard now loads with 1-hour date filter pre-selected

---

## P0: CRITICAL (Must Fix Immediately)

### GAP-001: CV V2 - Hallucinated Skills
**Priority**: P0 CRITICAL | **Status**: ✅ FIXED (2025-12-08 ENHANCED) | **Effort**: 1.5 days
**Impact**: CVs claim Java/PHP/Spring Boot expertise candidate DOESN'T have

**Root Cause**: Hardcoded skill lists in `src/layer6_v2/header_generator.py:200-226`

**Original Fix** (2025-11-30):
1. Added `get_all_hard_skills()`, `get_all_soft_skills()`, `get_skill_whitelist()` to CVLoader
2. Replaced hardcoded skill lists with dynamic whitelist from master-CV
3. Only skills from `data/master-cv/roles/*.md` now appear in generated CVs
4. JD keywords only included if they have evidence in experience bullets

**Enhanced Fix** (2025-12-08):
1. **Profile Section** (`header_generator.py:440-502`): Added keyword grounding filter
   - Only uses JD keywords if candidate has explicit evidence
   - Checks against experience bullets and master-CV skills whitelist
   - Prevents profile from claiming skills with no defensive evidence
2. **CV Improver** (`improver.py`): Added anti-hallucination tactics to IMPROVEMENT_STRATEGIES
   - Explicit "CRITICAL ANTI-HALLUCINATION RULES" in system prompt
   - Forbids adding skills candidate doesn't have evidence for
   - Validates all generated skills against master-CV whitelist

**Commits**: `85bebfea`, `[session-08-12-2025]` - Enhanced anti-hallucination filtering

---

### GAP-002: CV V2 - Static Core Skills Categories
**Priority**: P0 CRITICAL | **Status**: ✅ FIXED (2025-11-30) | **Effort**: 1.5 days
**Impact**: All CVs have identical 4 categories instead of JD-derived dynamic categories

**Root Cause**: Hardcoded loop in `src/layer6_v2/header_generator.py:495`

**Fix Implemented**:
1. Created `src/layer6_v2/category_generator.py` with LLM-driven category clustering
2. Updated `header_generator.py` with `use_dynamic_categories` parameter (default: True)
3. Categories now derived from JD keywords and role type
4. Example output: ["Cloud Platform Engineering", "Backend Architecture", "Technical Leadership"]

**Commit**: `85bebfea` - fix(cv-v2): prevent hallucinated skills and add dynamic categories

---

### GAP-003: VPS Backup Strategy - No Backups
**Priority**: P0 CRITICAL | **Status**: PENDING | **Effort**: 20-30 hours
**Impact**: No backups for generated CVs/dossiers; disk failure = total data loss

**Current State**:
- VPS has no backup mechanism for generated artifacts
- MongoDB Atlas has PITR but never tested
- API keys exist only on VPS (no secure vault)

**Fix Required**:
1. Implement S3 backup for VPS artifacts
2. Create disaster recovery plan
3. Test MongoDB backup restoration

**Report**: `reports/agents/doc-sync/2025-11-30-vps-backup-assessment.md`

---

### GAP-004: Credential Backup Vault - No Secure Storage
**Priority**: P0 CRITICAL | **Status**: ✅ DOCUMENTED (2025-12-01) | **Effort**: 4-6 hours
**Impact**: Credential backup procedures now documented

**Documentation Created**: `plans/credential-backup-vault.md`

Contents:
- Git-crypt setup instructions for encrypted credential storage
- Full list of critical credentials to backup
- Recovery process with step-by-step commands
- Monthly verification checklist
- AWS Secrets Manager alternative for production

**Next Steps**: Implement git-crypt setup and backup credentials

---

### GAP-046: Export PDF Button Not Working on Detail Page ✅ COMPLETE
**Priority**: P0 CRITICAL | **Status**: COMPLETE | **Effort**: 1-3 hours
**Impact**: Users can now export CV from job detail page

**Description**: Fixed the "Export PDF" button on job detail page. The issue was that the request body (tiptap_json) wasn't being sent to the PDF service.

**Root Cause**: The proxy endpoint was prepared to call `/cv-to-pdf` but forgot to include `json=pdf_request` in the requests.post() call.

**Fix Applied** (2024-11-30):
1. Updated `frontend/app.py` `generate_cv_pdf_from_editor()` to pass `json=pdf_request`
2. Fixed error message references from `runner_url` to `pdf_service_url`
3. Improved error messages for clarity

---

## P1: HIGH (Fix This Week)

### GAP-005: CV V2 - STAR Format Enforcement
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1 day
**Impact**: All CV bullets now follow STAR format for maximum recruiter impact

**Fix Applied** (2025-12-01):
1. **Prompts**: STAR template already in `role_generation.py` (lines 39-61) with examples
2. **Validation**: `RoleQA.check_star_format()` validates Situation, Action, Result elements
3. **Retry Logic**: `RoleGenerator.generate_with_star_enforcement()` auto-corrects failing bullets
4. **Integration**: `CVGeneratorV2` uses STAR enforcement by default (`use_star_enforcement=True`)

**Key Components**:
- `src/layer6_v2/prompts/role_generation.py`: Added `STAR_CORRECTION_SYSTEM_PROMPT` and `build_star_correction_user_prompt()`
- `src/layer6_v2/role_generator.py`: Added `generate_with_star_enforcement()`, `_identify_failing_bullets()`, `_correct_bullet_star()`
- `src/layer6_v2/orchestrator.py`: Added `use_star_enforcement` parameter (default: True)
- `src/layer6_v2/role_qa.py`: Already had `check_star_format()` with pattern detection

**Behavior**:
- Initial bullet generation includes STAR requirements in prompt
- STAR validation checks for: situation opener, action with skill, quantified result
- Failing bullets (<80% STAR coverage) trigger up to 2 correction retries
- LLM rewrites only failing bullets with explicit STAR enforcement prompt

**Verification**: 49 new unit tests in `tests/unit/test_star_enforcement.py`, all passing

---

### GAP-006: CV V2 - Markdown Asterisks in Output
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2 hours
**Impact**: All CVs now output clean text without markdown formatting

**Fix Applied** (2025-12-01):
1. Prompts already have "NO MARKDOWN" instructions (verified in role_generation.py lines 26-37)
2. Created `src/common/markdown_sanitizer.py` with comprehensive sanitization functions
3. Applied sanitization in `src/layer6_v2/orchestrator.py`:
   - `sanitize_markdown()` for profile text
   - `sanitize_bullet_text()` for each experience bullet

**Verification**: All 11 orchestrator unit tests pass

---

---

### GAP-008: GitHub Workflow - Master-CV Sync
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1 hour
**Impact**: VPS now receives full `data/master-cv/` directory with role skill files

**Fix Applied**:
`.github/workflows/runner-ci.yml:146` now includes `data/master-cv`:
```yaml
source: "master-cv.md,docker-compose.runner.yml,data/master-cv"
```

This ensures the VPS gets the role-specific skill files needed for skill whitelist generation.

---

### GAP-009: CV Editor Not Synced with Detail Page ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 30 minutes
**Impact**: CV content now displays on job detail view whether from cv_text or cv_editor_state

**Root Cause Found**: The `has_cv` flag only checked for `cv_text` (markdown), not `cv_editor_state` (TipTap JSON). Jobs that were edited in the CV editor but never had markdown CV would show no content.

**Fix Applied** (2025-12-01):
Updated `frontend/app.py:1441-1447` to check both fields:
```python
# Check if CV was generated by pipeline (stored in MongoDB)
# GAP-009 Fix: Check both cv_text (markdown) AND cv_editor_state (TipTap JSON)
if job.get("cv_text") or job.get("cv_editor_state"):
    has_cv = True
```

**How it works**:
- `cv_text`: Markdown CV from pipeline (original format)
- `cv_editor_state`: TipTap JSON from CV editor (newer format)
- Now both trigger `has_cv = True`, enabling the CV preview section

---

### GAP-010: Database Backup Monitoring
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 3-4 hours
**Impact**: MongoDB Atlas PITR enabled but never tested

**Fix Required**:
- Test monthly restore
- Document recovery procedures
- Verify backup retention

---

### GAP-011: LinkedIn 300 Char Message Limit ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2 hours
**Impact**: LinkedIn connection messages now enforced to ≤300 characters

**Fix Applied** (2024-11-30):
1. Updated prompts with STRICT 300 char limit and example (280-char target)
2. Changed signature from "Calendly link" to "Best. Taimoor Alam" (fits in limit)
3. Added intelligent truncation in `_validate_linkedin_message()` that:
   - Truncates at sentence boundaries
   - Preserves signature
   - Falls back to word boundary truncation
4. Updated `outreach_generator.py` with 300-char enforcement
5. Updated fallback messages to include signature
6. UI character counter deferred to future (Phase 3 of plan)

**Files Modified**: `src/layer5/people_mapper.py`, `src/layer6/outreach_generator.py`
**Plan**: `plans/linkedin-message-character-limit.md`

---

### GAP-012: Inline Mark Parsing ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 1 hour
**Impact**: Bold/italic/bold+italic marks now properly parsed in CV text conversion

**Fix Applied** (2025-12-01):
Implemented `parse_inline_marks()` function with regex parsing in both:
- `frontend/app.py:2406-2468`
- `runner_service/app.py:472-534`

**Supports**:
- `**bold**` → text with bold mark
- `*italic*` → text with italic mark
- `***bold+italic***` → text with both marks
- Mixed text like "Hello **world** and *universe*"

**Implementation**:
```python
# Regex pattern for bold (**text**), italic (*text*), or bold+italic (***text***)
pattern = r'(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*([^*]+?)\*)'
# Returns TipTap-compatible mark nodes
```

**Verification**: All 862 unit tests pass

---

### GAP-013: Bare Except Block - Bad Practice
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 30 minutes
**Impact**: Fixed - all exceptions now caught explicitly

**Fix Applied** (2025-12-01):
1. `src/layer5/people_mapper.py:498`: Changed `except:` to `except Exception:` with comment
2. `src/common/database.py:57`: Changed `except:` to `except Exception:` with comment

**Verification**: `grep -r "except:" src/` returns no matches

---

### GAP-047: Line Spacing Bug in CV Editor ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-4 hours
**Impact**: Line height/spacing now consistent between TipTap editor and PDF output

**Fix Applied** (2025-12-01):
1. Audited `.ProseMirror` CSS line-height values in `frontend/templates/base.html`
2. Updated `pdf_service/pdf_helpers.py` to use relative units (`em`) matching editor:
   - Paragraphs: `margin: 0.5em 0` (was `margin-bottom: 8px`)
   - Lists: `padding-left: 1.5em` (was `20px`)
   - List items: `margin: 0.25em 0` (was `6px`)
   - All elements: `line-height: inherit` for document-level cascade
3. Editor and PDF now use identical spacing values

**Related**: GAP-048 (also fixed), GAP-049 (WYSIWYG Consistency)

---

### GAP-048: Line Spacing Bug in CV Generation ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-4 hours
**Impact**: Generated CVs now have consistent line spacing matching editor and PDF

**Fix Applied** (2025-12-01):
Updated `pdf_service/pdf_helpers.py` CSS to match editor styling exactly:
1. Headings: Added `line-height: inherit` to h1-h6 (matches editor cascade)
2. Paragraphs: Changed from `margin-bottom: 8px` to `margin: 0.5em 0`
3. First/last paragraph: Added margin override rules (matches editor)
4. Lists: Changed `padding-left` from `20px` to `1.5em`, `margin` from `6px 0` to `0.5em 0`
5. List items: Changed `margin` from `6px 0` to `0.25em 0`
6. Nested list items: Added `li > p { margin: 0 }` rule (matches editor)

**Files Modified**: `pdf_service/pdf_helpers.py`
**Tests**: All 31 PDF helper tests pass

---

### GAP-049: Job Status Not Updating After Pipeline Completion ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-3 hours
**Impact**: Job status now updates to "ready for applying" after pipeline completion

**Description**: Fixed - job status now updates correctly after pipeline completion.

**Root Cause**: Same as GAP-050 - the `_persist_to_mongodb()` function couldn't find the job record because it was searching by `jobId` instead of `_id` (ObjectId).

**Fix Applied** (2024-11-30): See GAP-050 fix. The status update (`status: 'ready for applying'`) was already implemented in `output_publisher.py` but wasn't executing because the job lookup was failing.

---

### GAP-050: Pipeline State Not Persisting to MongoDB ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE | **Effort**: 2-3 hours
**Impact**: Pipeline outputs now persist correctly to MongoDB

**Description**: Fixed pipeline state persistence to MongoDB. Fields like pain_points, fit_score, and contacts now save correctly.

**Root Cause Found**: The `_persist_to_mongodb()` function in `output_publisher.py` was searching for jobs by `jobId` (integer) field, but jobs are stored with `_id` (ObjectId) as the primary identifier. When the job_id was an ObjectId string, the search would fail silently.

**Fix Applied** (2024-11-30):
1. Added ObjectId search as primary strategy in `_persist_to_mongodb()`
2. Fall back to integer jobId for legacy schema compatibility
3. Fall back to string jobId as last resort
4. Added detailed logging to track which strategy succeeded

---

### GAP-051: Missing Companies Bug in Contact Discovery ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-01) | **Effort**: 1 hour
**Impact**: Contact discovery now finds more contacts via company name variations and expanded paths

**Fix Applied** (2025-12-01):

1. **Added company name variations** (`get_company_name_variations()`):
   - Strips common suffixes: Inc., LLC, Ltd., Corp., GmbH, AG, etc.
   - Tries original name + stripped variant in searches
   - Example: "TechCorp Inc." → ["TechCorp Inc.", "TechCorp"]

2. **Expanded team page paths** (`TEAM_PAGE_PATHS` constant):
   - Added 9 new paths: `/people`, `/our-team`, `/founders`, `/executives`, `/management`, `/about/team`, `/about/leadership`, `/who-we-are`, `/meet-the-team`
   - Now checks 14 paths total (was 5)

3. **Improved search queries**:
   - Uses company variations in LinkedIn searches
   - Falls back to broader queries on empty results

**Files Modified**: `src/layer5/people_mapper.py`
**Commit**: `a1577289` - feat(pipeline): Improve contact discovery with company variations (GAP-051)

---

### GAP-064: Missing `appliedOn` Timestamp When Marking Jobs Applied ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Dashboard "applied by day/week/month" stats now use accurate timestamps

**Fix Applied** (2025-12-01):

1. **Updated `update_job_status()`** - Sets `appliedOn: datetime.utcnow()` when status = "applied"
2. **Updated `update_jobs_status_bulk()`** - Same logic for bulk updates
3. **Updated `/api/dashboard/application-stats`** - Queries by `appliedOn` instead of `pipeline_run_at`
4. **Edge case handled** - Clears `appliedOn` if status changes FROM "applied" to something else

**Implementation**:
```python
update_data = {"status": new_status}
if new_status == "applied":
    update_data["appliedOn"] = datetime.utcnow()
elif new_status != "applied":
    update_data["appliedOn"] = None  # Clear if no longer applied
```

**Files Modified**: `frontend/app.py`
**Commit**: `87f39e92` - feat(frontend): Add appliedOn timestamp for accurate stats (GAP-064)

---

### GAP-059: VPS Health Indicator Shows Grey (Unknown State)
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1-2 hours
**Impact**: VPS health status not visible to users; unclear if runner service is online

**Fix Applied**: The frontend JS was checking `data.vps?.status` but backend returns `data.runner.status`. Fixed property name mismatch in `frontend/templates/base.html`.

**Description**: The VPS health indicator on the dashboard shows grey instead of green/red. Grey indicates "unknown" state - the `/api/health` endpoint returned unexpected data, timed out, or failed.

**Possible Causes**:
1. VPS runner service not running (`docker compose ps`)
2. Port 8000 not exposed/accessible from Vercel frontend
3. Network timeout (default 5s) exceeded
4. CORS issues on `/health` endpoint
5. Runner URL misconfigured (`RUNNER_URL` env var)

**Debug Steps**:
1. `curl http://72.61.92.76:8000/health` - Test runner directly
2. Browser DevTools → Network tab → Check `/api/health` response
3. Check Vercel logs for health check errors
4. Verify `RUNNER_URL` env var in Vercel settings

**Files**:
- `frontend/app.py:726-838` - Health endpoint aggregation
- `frontend/templates/base.html:1629-1697` - JavaScript polling
- `runner_service/app.py:372-384` - Runner health endpoint

---

### GAP-061: Budget/Alert Dashboard Widgets Not Visible ✅ ANALYZED
**Priority**: P1 HIGH | **Status**: ANALYZED (Code Correct) | **Effort**: Deployment verification
**Impact**: Budget monitoring and alerts will display once token usage is recorded

**Analysis Complete** (2025-12-01):
The code is **FULLY CORRECT**. Investigation revealed:

1. ✅ **HTMX attributes correct**: `hx-get="/partials/budget-monitor"` with `hx-trigger="load, every 30s"` in `index.html:89-92`
2. ✅ **Environment variables have sensible defaults**:
   - `ENABLE_TOKEN_TRACKING=true` (default)
   - `TOKEN_BUDGET_USD=100.0` (default)
   - `ENABLE_ALERTING=true` (default)
3. ✅ **Template correctly included** in index.html
4. ✅ **Endpoint works**: `/partials/budget-monitor` proxies to VPS `/api/metrics/budget`

**Expected Behavior**:
- Dashboard shows "No token trackers registered" until pipeline runs record token usage
- Token trackers auto-register when LLM calls occur (during pipeline execution)
- After first pipeline run with token tracking, budget data will appear

**Verification Steps**:
1. Run a pipeline job on VPS to generate token usage data
2. Check browser Network tab for `/partials/budget-monitor` response
3. Verify VPS is reachable from Vercel (`RUNNER_URL` env var)

**Implemented Components** (all working):
- `src/common/token_tracker.py` (1013 lines) - Token tracking with 12-model pricing
- `src/common/alerting.py` (581 lines) - Alert system with Slack
- `src/common/metrics.py` (709 lines) - Metrics collector
- `frontend/templates/partials/budget_monitor.html` (155 lines)
- 8 Flask API endpoints (`/api/budget`, `/api/alerts`, `/partials/*`)

---

### GAP-062: Job Extraction Not Showing on Detail Page
**Priority**: P1 HIGH | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2-3 hours
**Impact**: Extracted JD data now displays prominently at top of detail page

**Fix Applied**:
1. Verified Layer 1.4 JD extraction is working correctly and saving to MongoDB
2. Added responsibilities and qualifications display to frontend template
3. **MOVED** extracted JD, pain points, and opportunities sections to TOP of detail page for prominence
4. Added debug logging to output_publisher to trace extracted_jd persistence

**What Changed**:
- `frontend/templates/job_detail.html` - Reorganized layout, moved JD intelligence to top
- `src/layer7/output_publisher.py` - Added debug logging for extracted_jd
- Extracted JD now appears immediately after pipeline progress indicator

**Verification**: Run pipeline for job, then view detail page - extracted JD section shows at top

---

## P2: MEDIUM (Fix This Sprint)

### GAP-014: CV V2 - Dynamic Tagline for Location ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Middle East jobs now get "Open to International Relocation" tagline automatically

**Fix Applied** (2025-12-01):
1. Added `MIDDLE_EAST_COUNTRIES` list in `src/layer6_v2/orchestrator.py`
2. Created `is_middle_east_location()` function for location matching
3. Modified `_assemble_cv_text()` to inject tagline after contact line
4. Tagline: "Open to International Relocation | Available to start within 2 months"

**Trigger Countries**: Saudi Arabia, UAE, Kuwait, Qatar, Oman, Pakistan, Dubai, Abu Dhabi, Riyadh, etc.

**Commit**: `03a996c8` - feat(pipeline): Add relocation tagline for Middle East jobs (GAP-014)

---

### GAP-015: CV V2 - Color Scheme Change ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE | **Effort**: 30 minutes
**Impact**: CV now uses professional slate-600 color instead of teal/green

**Fix Applied** (2025-12-01):
Changed `#0f766e` (teal/green) → `#475569` (slate-600 dark greyish blue) in:
1. `pdf_service/pdf_helpers.py` - PDF output `--color-accent` variable
2. `frontend/templates/base.html` - CV editor heading colors (4 locations)
3. `frontend/app.py` - Default `colorAccent` config (2 locations)

**Commit**: `0676a5da` - style: Change CV color scheme from teal to slate-600

---

### GAP-016: DateTime Range Picker Enhancement
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 min
**Impact**: Date filter now supports hour/minute precision

**Fix Applied** (2025-12-01):
- Changed `type="date"` to `type="datetime-local"` for date range inputs
- Updated input names from `date_from/date_to` to `datetime_from/datetime_to`
- Removed redundant hidden datetime inputs
- Updated `setQuickDateFilter()` JS to format datetime-local values
- Updated `clearAllFilters()` and `clearDateFilter()` for new input type

**Files**: `frontend/templates/index.html`

---

### GAP-017: E2E Tests Disabled
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: 48 Playwright tests exist but disabled due to config issues

**Plan**: `plans/e2e-testing-implementation.md`

---

### GAP-018: Integration Tests Not in CI/CD
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 3-4 hours
**Impact**: No automated integration testing on push

---

### GAP-019: Code Coverage Not Tracked
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 min
**Impact**: Test coverage now tracked automatically

**Fix Applied** (2025-12-01):
- Added `pytest-cov` configuration to `pytest.ini`
- Created `.coveragerc` with detailed coverage settings
- Configured coverage for `src/`, `frontend/`, `runner_service/`, `pdf_service/`
- Enabled branch coverage and HTML/XML reports
- Added `coverage_html/` and `coverage.xml` to `.gitignore`

**Files**: `pytest.ini`, `.coveragerc`, `.gitignore`

---

### GAP-020: STAR Selector → Variant-Based Selection ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-06) | **Effort**: 3 days
**Impact**: Zero-hallucination CV generation via pre-written variants with deterministic selection

**Implementation** (2025-12-06):

**Phase 1: VariantParser** (`src/layer6_v2/variant_parser.py` - 476 lines)
- Dataclasses: `AchievementVariant`, `Achievement`, `RoleMetadata`, `SelectionGuide`, `EnhancedRoleData`
- Parses role files with variant structure: Technical, Architecture, Impact, Leadership, Short
- Supports both enhanced format (variants) and legacy format (simple bullets)
- 35 unit tests in `tests/test_variant_parser.py` - all passing

**Phase 2: VariantSelector** (`src/layer6_v2/variant_selector.py` - 391 lines)
- Weighted scoring algorithm for variant selection:
  - 40% keyword overlap (JD keywords in variant text)
  - 30% pain point alignment (pain points in variant text)
  - 20% role category match (variant category vs role category)
  - 10% achievement keywords (contextual relevance)
- `VARIANT_PREFERENCES` mapping role categories to preferred variant types
- Zero LLM calls - pure algorithm-based selection
- 20 unit tests in `tests/test_variant_selector.py` - all passing

**Phase 3: CVLoader Integration** (`src/layer6_v2/cv_loader.py` - updated)
- Added `enhanced_data` field to `RoleData` with variant support
- Added properties: `has_variants`, `variant_count`, `get_achievement_variants()`
- Helper methods: `get_total_variants()`, `get_enhanced_roles()`
- Backward compatible with legacy format (graceful fallback)
- 21 tests updated/added in `tests/unit/test_layer6_v2_cv_loader.py` - all passing

**Phase 4: RoleGenerator Integration** (`src/layer6_v2/role_generator.py` - updated)
- `generate_from_variants()` - Zero-hallucination bullet selection from variants
- `generate_with_variant_fallback()` - Production method with LLM backup
- `generate_all_roles_from_variants()` - Batch processing function
- `_extract_metric()` - Extracts metrics from variant text
- 9 new tests in `tests/unit/test_layer6_v2_role_generator.py` - all passing

**Data Migration** (2025-12-06):
All 6 role files in `data/master-cv/roles/` converted to enhanced format:
- 01_senior_backend.md, 02_platform_engineer.md, 03_staff_architect.md
- 04_tech_lead.md, 05_startup_engineer.md, 06_clary_icon.md
- Each achievement has 4-5 variants (Technical, Architecture, Impact, Leadership, Short)
- Total: 189 variants across all roles
- Updated `role_metadata.json` with variant counts and selection guides

**Benefits**:
1. **Zero Hallucination**: All text is pre-written and interview-defensible
2. **Faster Generation**: No LLM calls for variant selection (algorithmic)
3. **Deterministic**: Same inputs produce same outputs
4. **ATS Optimized**: Keywords pre-embedded in variants during role file creation
5. **Interview Ready**: Each variant has defensibility context and notes
6. **Provenance**: Every bullet traces back to pre-approved variant

**Test Coverage**: 85 tests - 35 variant parser + 20 selector + 21 cv_loader + 9 role_generator

**Files Modified**:
- `src/layer6_v2/variant_parser.py` - New (476 lines)
- `src/layer6_v2/variant_selector.py` - New (391 lines)
- `src/layer6_v2/cv_loader.py` - Updated with enhanced_data support
- `src/layer6_v2/role_generator.py` - Added variant generation methods
- `tests/test_variant_parser.py` - New (35 tests)
- `tests/test_variant_selector.py` - New (20 tests)
- `tests/unit/test_layer6_v2_cv_loader.py` - Updated (21 tests)
- `tests/unit/test_layer6_v2_role_generator.py` - Updated (9 tests)
- `data/master-cv/roles/*.md` - All 6 files converted to enhanced format
- `data/master-cv/role_metadata.json` - Updated with variant counts

---

### GAP-021: Remote Publishing Disabled
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Feature flag `ENABLE_REMOTE_PUBLISHING=false` by default

**Missing**: Google Drive/Sheets integration not tested

---

### GAP-022: Job Application Progress UI Frontend ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Full pipeline progress visualization available on job detail page

**Verification** (2025-12-01): Feature was already fully implemented

**Existing Implementation**:
1. **CSS Styles**: `frontend/static/css/pipeline-progress.css` (400 lines) with:
   - 5 visual states: pending, executing, success, failed, skipped
   - Animated pulse ring for executing steps
   - Overall progress bar with shimmer effect
   - Responsive design + accessibility support

2. **HTML Stepper**: 7-layer visual stepper in `job_detail.html:192-327`:
   - Intake → Pain Points → Company Research → Role Research → Fit Scoring → People Mapping → CV/Outreach

3. **JavaScript** (`job_detail.html:2329-2480`):
   - `monitorPipeline(runId)` - Starts monitoring with polling
   - `updatePipelineStep(layer, status)` - Updates individual layers
   - `handlePipelineProgressUpdate(data)` - Handles SSE/polling updates
   - SSE support ready (commented, awaiting backend SSE endpoint)

---

### GAP-023: Application Form Mining (Layer 1.5)
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Form field extraction from job postings not implemented

---

### GAP-024: V2 Parser/Tailoring Not Implemented
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: 18+ unit tests skipped with reason "Will fail until V2 parser/tailoring implemented"

**Evidence**: `tests/unit/test_layer6_cv_generator_v2.py` - multiple skipped tests

---

### GAP-025: V2 Prompts ✅ ALREADY IMPLEMENTED
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (already implemented) | **Effort**: N/A
**Impact**: V2 validation already running in production

**Verification** (2025-12-01):
The V2 prompts and validation were ALREADY IMPLEMENTED. Tests show:
- 18 passed, 6 skipped in `test_layer4_opportunity_mapper_v2.py`
- 15 passed, 8 skipped in `test_layer6_cover_letter_generator_v2.py`

Skipped tests are A/B comparison tests for LLM output quality, not implementation tests.

**Existing Implementation**:
1. **Opportunity Mapper** (`src/layer4/opportunity_mapper.py:167-277`):
   - 4-step reasoning framework in prompts
   - `_validate_rationale()` checks: STAR citations, pain point refs, min length (30 words), generic phrase detection, metric presence
   - Validation runs on every response (warnings logged, not hard failures)

2. **Cover Letter Generator** (`src/layer6/cover_letter_generator.py`):
   - Company signal references validation
   - Metric co-occurrence checks
   - Pain point coverage requirements

---

### GAP-052: Phase 5 - WYSIWYG Page Break Visualization ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Visual page break indicators show where PDF pages will break

**Verification** (2025-12-01): Feature was already fully implemented

**Existing Implementation**:
1. **Page Break Calculator** (`frontend/static/js/page-break-calculator.js`):
   - `calculatePageBreaks(pageSize, margins, contentElement)` - computes Y positions
   - `renderPageBreaks(breakPositions, container)` - renders dashed line indicators
   - `clearPageBreaks(container)` - removes indicators
   - Supports Letter (8.5x11") and A4 page sizes
   - Algorithm iterates elements and tracks cumulative height

2. **CV Editor Integration** (`frontend/static/js/cv-editor.js:1261-1286`):
   - Calls `PageBreakCalculator.calculatePageBreaks()` when content changes
   - Renders break indicators with "Page N" labels

3. **CSS Styling** (`frontend/static/css/cv-editor.css:365-396`):
   - Dashed line with gray background
   - "Page N" label in top-right corner

**Plan**: `plans/phase5-page-break-visualization.md`

---

### GAP-053: Phase 6 - PDF Service Separation
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: PDF generation tightly coupled to runner service; scalability limited

**Description**: Separate PDF generation from runner service into dedicated Docker container for better separation of concerns and independent scaling.

**Benefits**:
- Clear separation of concerns (pipeline ≠ PDF rendering)
- Independent scaling and resource management
- Easy to add new document types (cover letters, dossiers)
- PDF service isolated, can restart without affecting pipeline

**Plan**: `plans/phase6-pdf-service-separation.md`

---

### GAP-054: CV Editor WYSIWYG Consistency ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Editor and detail page now render identically - true WYSIWYG achieved

**Fix Applied** (2025-12-01):
Unified display container styles with `.ProseMirror` editor in `frontend/templates/base.html`:

| Element | Before (Display) | After (Matches Editor) |
|---------|------------------|------------------------|
| h1 | `2em`, no color | `34px`, slate-600, Playfair Display |
| h2 | `1.5em`, no border | `20px`, slate-600, border-top |
| h3 | `1.25em`, no color | `16px`, slate-600 |
| links | blue underline | slate-600, no underline |

**Changes**:
1. Updated `#cv-markdown-display`, `#cv-container`, `#cv-display-area` heading styles to exactly match `.ProseMirror`
2. Added h2:first-child rule for consistent border behavior
3. Updated link color from blue to slate-600 to match editor accent

**Plan**: `plans/cv-editor-wysiwyg-consistency.md`

---

### GAP-055: Auto-Save on Blur for Form Fields
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Users have auto-save with visual feedback

**Verification** (2025-12-01): Feature was already fully implemented at `frontend/templates/job_detail.html:2135-2174`

**Existing Implementation**:
- `saveFieldEdit()` function handles auto-save on blur
- Visual feedback: "Saving..." → "✓ Saved" → normal state
- Handles Enter key (save) and Escape key (cancel)
- Error handling with user-friendly messages
- Debounce built into save mechanism

---

### GAP-056: Contact Management (Delete/Copy/Import) ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Full contact management available on job detail page

**Verification** (2025-12-01): Feature was already fully implemented in `frontend/templates/job_detail.html` and `frontend/app.py`

**Existing Implementation**:
1. **Delete Contact**: `deleteContact()` function with confirmation, smooth animation removal
2. **Copy FireCrawl Prompt**: `copyFirecrawlPrompt()` copies discovery prompt to clipboard
3. **Import Contacts Modal**: `openAddContactsModal()` with JSON validation, preview, and bulk import

**API Endpoints** (`frontend/app.py`):
- `DELETE /api/jobs/<id>/contacts/<type>/<index>` - Delete single contact
- `POST /api/jobs/<id>/contacts` - Bulk import contacts
- `GET /api/jobs/<id>/contacts/prompt` - Get FireCrawl discovery prompt

**UI Elements** (job detail page):
- "Copy Prompt" button in contacts header
- "Add Contacts" button for import modal
- Delete (trash) button on each contact card

---

### GAP-060: Limit FireCrawl Contacts to 5 (Currently 10)
**Priority**: P2 MEDIUM | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 30 minutes
**Impact**: 10 contacts is too heavy; causes processing overhead and increased costs

**Fix Applied**: Added `MAX_TOTAL_CONTACTS=5` constant and `_limit_contacts()` method in `src/layer5/people_mapper.py`. Limits to 3 primary + 2 secondary contacts. Applied BEFORE outreach generation to save LLM calls.

**Description**: FireCrawl contact discovery currently fetches up to 10 contacts per company. This is excessive and should be reduced to 5 for efficiency.

**Fix Required**:
1. Find FireCrawl contact discovery limit parameter in `src/layer5/people_mapper.py`
2. Change limit from 10 to 5
3. Update any related tests

**Files**:
- `src/layer5/people_mapper.py` - Contact discovery logic
- FireCrawl MCP tool parameters

---

### GAP-063: Parallel Pytest Execution in CI/CD
**Priority**: P2 MEDIUM | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2-3 hours
**Impact**: 813+ tests now run in parallel; ~60-80% CI time reduction

**Fix Applied** (2025-12-01):
1. Added `pytest-xdist>=3.5.0` and `pytest-cov>=4.0.0` to `requirements.txt`
2. Updated `pytest.ini` with `-n auto` for parallel execution by default
3. Updated `.github/workflows/runner-ci.yml`:
   - Re-enabled test job with parallel execution
   - Added PDF service tests
   - Tests now required before build
4. Updated `.github/workflows/frontend-ci.yml` with parallel execution

**Verification**:
```bash
# Local: 813 tests in 48.61s (parallel) vs ~3 min (sequential)
python -m pytest tests/unit -n auto --tb=short
```

**Note**: Use `-n 0` to disable parallel execution for debugging

---

### GAP-065: LinkedIn Job Scraper - Import Jobs via Job ID ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 4 hours
**Impact**: Quick job import from LinkedIn without manual data entry

**Fix Applied** (2025-12-01):
Implemented ability to import LinkedIn jobs by entering just the job ID or URL. Scrapes LinkedIn's public guest API to extract job details and creates job records in both level-1 and level-2 MongoDB collections.

**User Flow**:
1. User enters LinkedIn job ID (e.g., `4081234567`) or URL in dashboard input field
2. System scrapes `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}`
3. Parses HTML to extract: title, company, location, description, job criteria
4. Creates job document in both MongoDB level-1 and level-2 collections with status "not processed"
5. Runs quick LLM (gpt-4o-mini) to score job fit
6. Redirects user to job detail page

**Implementation Complete**:
1. `src/services/linkedin_scraper.py` - Scraper service with BeautifulSoup HTML parsing
2. `src/services/quick_scorer.py` - Lightweight LLM scoring using gpt-4o-mini
3. `frontend/app.py` - POST `/api/jobs/import-linkedin` endpoint with duplicate detection
4. `frontend/templates/index.html` - Input field + button UI with LinkedIn icon
5. `frontend/templates/base.html` - JavaScript handler `importLinkedInJob()` with loading states
6. `requirements.txt` - Added beautifulsoup4 and lxml dependencies
7. `tests/unit/test_linkedin_scraper.py` - 24 unit tests passing

**DedupeKey Format**: `company|title|location|source` (all lowercase)
Example: `testcorp|senior software engineer|san francisco, ca|linkedin_import`

**Supported Input Formats**:
- Raw job ID: `4081234567`
- Full URL: `https://www.linkedin.com/jobs/view/4081234567`
- URL with params: `https://linkedin.com/jobs/view/4081234567?trk=search`
- currentJobId param: `https://linkedin.com/jobs/search/?currentJobId=4081234567`

---

### GAP-066: Token Tracking Callback Integration ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-01) | **Effort**: 2-3 hours
**Impact**: Dashboard token/cost metrics now track accurately; budget enforcement works

**Implementation** (2025-12-01):

1. **LLM Factory Module** (`src/common/llm_factory.py`):
   - `create_tracked_llm()` - Standard OpenRouter LLM with token tracking
   - `create_tracked_cv_llm()` - Claude Anthropic for CV stitching
   - `create_tracked_cheap_llm()` - GPT-4o-mini for cost-effective operations
   - `create_tracked_llm_with_tier()` - Tier-aware model selection
   - `set_run_context()` / `clear_run_context()` - Global run/job ID context
   - `get_run_context()` - Retrieve current context for callbacks

2. **17 Layer Files Updated**:
   - `src/layer1_4/jd_extractor.py` - JD Extraction
   - `src/layer2/pain_point_miner.py` - Pain Point Mining
   - `src/layer2_5/star_selector.py` - STAR Selection
   - `src/layer3/company_researcher.py` - Company Research
   - `src/layer3/role_researcher.py` - Role Research
   - `src/layer4/opportunity_mapper.py` - Fit Scoring
   - `src/layer5/people_mapper.py` - Contact Discovery
   - `src/layer6/generator.py` - CV Generation (Legacy)
   - `src/layer6/cv_generator.py` - CV Generation
   - `src/layer6/cover_letter_generator.py` - Cover Letter
   - `src/layer6_v2/role_generator.py` - Role Generation V2
   - `src/layer6_v2/header_generator.py` - Header Generation V2
   - `src/layer6_v2/category_generator.py` - Category Generation V2
   - `src/layer6_v2/improver.py` - CV Improvement V2
   - `src/layer6_v2/grader.py` - CV Grading V2
   - `src/services/quick_scorer.py` - Quick Scoring

3. **Workflow Integration** (`src/workflow.py`):
   - Calls `set_run_context(run_id=run_id, job_id=job_id)` at pipeline start
   - Calls `clear_run_context()` at pipeline end and in error handlers
   - All LLM calls automatically tagged with run context

4. **Test Updates**:
   - Updated all test fixtures to mock `create_tracked_llm` instead of `ChatOpenAI`
   - 892 tests passing (887 unit + 5 benchmark)

**Factory Usage Example**:
```python
from src.common.llm_factory import create_tracked_llm

# In layer constructor
self.llm = create_tracked_llm(layer="layer2_pain_points")

# Automatically includes TokenTrackerCallback with:
# - Per-layer cost attribution
# - Run ID and Job ID context
# - Provider-specific token counting
```

**Files**: `src/common/llm_factory.py` (new), 17 layer files updated, `src/workflow.py`

---

### GAP-067: Editable Score Field in Table and Detail Page ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 1 hour
**Impact**: Users can manually adjust fit scores after reviewing jobs

**Fix Applied** (2025-12-01):
Implemented inline editable score fields across all views.

**Files Modified**:
- `frontend/templates/partials/job_rows.html` - Editable score in job table
- `frontend/templates/job_detail.html` - Editable score badge in header
- `frontend/templates/base.html` - JavaScript functions (enableScoreEdit, saveScore, etc.)
- `frontend/app.py` - New `/api/jobs/score` POST endpoint

**Features**:
- Click score badge to edit (table & detail page)
- Save on blur or Enter key
- Cancel on Escape key
- Validates 0-100 range
- Visual feedback with toast notifications
- Score badge color updates dynamically (green ≥80, yellow ≥60, gray otherwise)

---

### GAP-068: Automated Job Ingestion System
**Priority**: P2 MEDIUM | **Status**: PLANNED (2025-12-01) | **Effort**: 5 days
**Impact**: Manual job discovery bottleneck; 4x more jobs discovered automatically

**Detailed Plan**: `plans/job-ingestion-plan.md`

**Overview**:
Automated cron-based system to discover jobs from Indeed (via JobSpy) and Himalayas.app, quick-score them with gpt-4o-mini, and ingest into MongoDB `level-2` collection.

**Architecture**:
```
CRON (every 6 hours)
    ├── Indeed (JobSpy) → 50 jobs × 4 search terms × 3 locations
    ├── Himalayas.app API → Remote jobs filtered by keywords
    │
    └── Processing Pipeline
        ├── Deduplicate (company|title|location|source)
        ├── Quick Score (gpt-4o-mini, ~$0.001/job)
        ├── Filter: score >= 70 (Tier B+)
        └── Insert to MongoDB level-2 collection
```

**Files to Create**:
| File | Description |
|------|-------------|
| `src/services/job_sources/__init__.py` | JobSource ABC + JobData dataclass |
| `src/services/job_sources/indeed_source.py` | JobSpy Indeed integration |
| `src/services/job_sources/himalayas_source.py` | Himalayas API integration |
| `src/common/ingest_config.py` | IngestConfig from env |
| `scripts/ingest_jobs_cron.py` | Main cron script |
| `docker/job-ingest/Dockerfile` | Cron container |
| `docker-compose.ingest.yml` | Docker Compose for ingestion |

**Dependencies**: `python-jobspy>=1.1.62`

**Cost Estimate**: ~$3/month (800 jobs × $0.003/scoring)

**ROI**: HIGH - Automates job discovery, reduces manual work, multiplies pipeline throughput

---

### GAP-069: FireCrawl SEO Query Result Caching
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: Repeated FireCrawl queries for same company waste API credits

**Description**: Cache FireCrawl search results per company in MongoDB with 7-day TTL. Same company searches within TTL use cached contacts instead of new API calls.

**Implementation**:
1. Add `firecrawl_contact_cache` collection with TTL index
2. Check cache before FireCrawl search in `people_mapper.py`
3. Store search results with timestamp and company key
4. Invalidate cache on company name variations

**Expected Savings**: ~30% reduction in FireCrawl API calls

---

### GAP-070: FireCrawl Credit Dashboard ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 2 hours
**Impact**: No visibility into FireCrawl API credit usage; risk of exhausting daily limit

**Implementation** (2025-12-01):
Added comprehensive FireCrawl credit tracking and dashboard widget.

**Files Created/Modified**:
- `src/layer5/people_mapper.py` - Added `_firecrawl_search()` method with rate limiting
- `runner_service/app.py` - Added `/firecrawl/credits` endpoint
- `runner_service/models.py` - Added `FireCrawlCreditsResponse` model
- `frontend/app.py` - Added `/api/firecrawl/credits` and `/partials/firecrawl-credits` endpoints
- `frontend/templates/partials/firecrawl_credits.html` - Dashboard widget
- `frontend/templates/index.html` - Added widget to dashboard (3-column grid)
- `tests/runner/test_runner_api.py` - Added 3 tests for FireCrawl credits endpoint

**Features**:
- Real-time credit usage tracking (used/remaining/daily_limit)
- Status indicators: healthy (<80%), warning (80-90%), critical (90-100%), exhausted (100%)
- Per-minute rate tracking
- Auto-refresh every 30 seconds via HTMX
- Progress bar with color coding
- Fallback to local rate limiter when VPS unavailable

---

### GAP-071: FireCrawl API Integration & Token Usage ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-08) | **Effort**: 1.5 hours
**Impact**: Real-time API usage tracking and fallback support

**Implementation** (2025-12-08):

**FireCrawl API Usage** (`runner_service/app.py:533-614`):
1. Calls actual `GET https://api.firecrawl.dev/v1/team/token-usage` API
2. Parses response with proper error handling
3. Falls back to local rate limiter if API unavailable
4. Added `firecrawl_api_key` to `src/common/config.py`

**OpenRouter Credits API** (`runner_service/app.py:618-674`):
1. New endpoint `/openrouter/credits` calls OpenRouter API
2. Returns remaining credits and reset date
3. Models added to `runner_service/models.py`:
   - `OpenRouterCreditsResponse` - Full response with credits and reset info
   - Used in `/openrouter/credits` endpoint
4. Frontend proxy endpoint in `frontend/app.py` for CORS handling
5. Added `openrouter_api_key` to `src/common/config.py`

**Files Modified**:
- `runner_service/app.py` - Added both API endpoints with error handling
- `runner_service/models.py` - Added `OpenRouterCreditsResponse` model
- `frontend/app.py` - Added proxy endpoint for OpenRouter credits
- `src/common/config.py` - Added `firecrawl_api_key` and `openrouter_api_key`

**API Endpoints**:
- `GET /firecrawl/credits` - Returns FireCrawl token usage data
- `GET /openrouter/credits` - Returns OpenRouter credits info
- Frontend proxies: `/api/firecrawl/credits`, `/api/openrouter/credits`

---

### GAP-072: CV Editor & Generation Styling Enhancements ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-08) | **Effort**: 2 hours
**Impact**: Professional CV styling with improved typography and consistency

**Implementation** (2025-12-08):

**Name Display Styling** (`cv-editor.js:207`):
- Name now renders in full caps: "TAIMOOR ALAM"
- Uses text-transform: uppercase CSS
- Consistent across editor and PDF output

**Role Tagline** (`cv-editor.js:210-212`):
- New H3 role tagline placeholder added
- Format: `{JD Title} · {Generic Title}`
- Example: "Principal Engineer · Staff Architect"
- Added `_get_generic_title()` helper in orchestrator for role category mapping

**Small Caps Toggle** (`_cv_editor_panel.html:235-240`):
- New button added to CV editor toolbar
- Toggles small caps styling on name and section headings
- Visual indicator shows when small caps is active

**CV Generation Styling** (`src/layer6_v2/orchestrator.py`):
- Removed emojis from contact info for professional appearance
- Changed separators to dot (·) format
- Contact line format: `Email · Phone · LinkedIn · GitHub`
- Name renders in uppercase
- Added role tagline as H3: `{JD Title} · {Generic Title}`
- Added `_get_generic_title()` helper for role category mapping:
  - Backend Engineer → "Senior Backend Engineer"
  - Platform Engineer → "Staff Platform Engineer"
  - etc.

**Small Caps CSS** (`cv-editor.css:337-341`):
```css
.small-caps-enabled h1 {
    font-variant: small-caps;
}
.small-caps-enabled h2 {
    font-variant: small-caps;
}
```

**Files Modified**:
- `frontend/static/js/cv-editor.js` - Updated name display and tagline logic
- `frontend/templates/_cv_editor_panel.html` - Added small caps toggle button
- `frontend/static/css/cv-editor.css` - Added small caps styling
- `src/layer6_v2/orchestrator.py` - Updated CV text assembly with new styling
  - Removed emojis from contact info
  - Added dot separators
  - Added uppercase name and tagline
  - Added `_get_generic_title()` helper method

**Result**: CVs now have consistent, professional styling across editor and generated output

---

### GAP-073: Recruitment Agency Detection & Handling ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-08) | **Effort**: 4 hours
**Impact**: Recruitment agency positions now handled distinctly with optimized processing, contacts, and copy

**Implementation** (2025-12-08):

**Layer 3: Company Type Classification** (`src/common/state.py`, `src/layer3/company_researcher.py`):
- Added `company_type` field to `CompanyResearch` TypedDict (values: `"employer"` | `"recruitment_agency"` | `"unknown"`)
- New `_classify_company_type()` method uses heuristic keyword matching (fast path) + LLM fallback for ambiguous cases
- Keywords detected: "recruitment", "staffing", "talent", "headhunter", "agency", "employment", "placement", "hunter"
- Agencies skip deep research (no LinkedIn, Crunchbase, news scraping) - returns basic summary only
- Test coverage: 15 unit tests in `tests/unit/test_agency_detection.py`

**Layer 3.5: Role Research Skip** (`src/layer3/role_researcher.py`):
- Role researcher skips processing for agencies (client company unknown)
- Returns `role_research: None` to signal downstream layers to adapt

**Layer 4: Fit Scoring Note** (`src/layer4/opportunity_mapper.py`):
- Adds contextual note to `fit_rationale`: "This is a recruitment agency position..."
- Scoring based on job requirements only (no company signals considered)

**Layer 5: Optimized Contact Count** (`src/layer5/people_mapper.py`):
- Limit to 2 recruiter contacts maximum (vs 6+6 for employers)
- New method `_generate_agency_recruiter_contacts()` creates synthetic recruiter contacts
- Reduces LLM calls and outreach cost for agencies

**Layer 6: Recruiter-Specific Cover Letter** (`src/layer6/recruiter_cover_letter.py` - NEW):
- New file with `RecruiterCoverLetterGenerator` class
- Shorter format: 150-250 words (vs 220-380 for employers)
- Focus: skills match and availability (not company signals/culture fit)
- Tone: Direct and professional
- Message structure:
  1. Greeting + role interest
  2. Skills match (2-3 key technical + soft skills)
  3. Availability statement
  4. Call to action
  5. Signature

**Generator Adaptation** (`src/layer6/generator.py`):
- Updated `CoverLetterGenerator` to conditionally select appropriate cover letter type
- Uses `company_type` from state to route to `RecruiterCoverLetterGenerator` for agencies

**Frontend UI** (`frontend/templates/job_detail.html`):
- Company type badge displays in Quick Info Bar (top right)
- Purple badge: "Agency" for recruitment agencies
- Blue badge: "Direct" for direct employers
- Badge position: Next to processing tier

**Test Coverage**:
- `tests/unit/test_agency_detection.py` (15 unit tests):
  - Heuristic detection for common agency keywords
  - LLM fallback classification
  - Minimal research path validation
  - Contact generation verification
  - Recruiter cover letter formatting validation
  - All tests passing with full coverage

**Files Modified**:
- `src/common/state.py` - Added company_type to CompanyResearch
- `src/layer3/company_researcher.py` - Agency classification logic
- `src/layer3/role_researcher.py` - Skip logic for agencies
- `src/layer4/opportunity_mapper.py` - Agency note in rationale
- `src/layer5/people_mapper.py` - Contact limits (2 max)
- `src/layer6/generator.py` - Conditional cover letter selection
- `frontend/templates/job_detail.html` - Agency badge display

**Files Created**:
- `src/layer6/recruiter_cover_letter.py` - Recruiter-specific generator (NEW)
- `tests/unit/test_agency_detection.py` - 15 agency detection tests (NEW)

**Benefits**:
- Improved processing efficiency for agency roles (skip expensive company research)
- Cost savings (fewer contacts, minimal research)
- Better user experience (appropriate copy tailored to recruiter audience)
- Full pipeline traceability with company_type field

---

### GAP-075: Pipeline UI Horizontal Layout ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-08) | **Effort**: 2-3 hours
**Impact**: Pipeline progress steps now display horizontally with progress line and visual icons

**Implementation** (2025-12-08):

**Frontend Updates** (`frontend/templates/partials/job_detail/_pipeline_progress.html`):
- Converted 7-layer pipeline from vertical stepper to horizontal layout
- Added progress line connecting steps with gradient styling
- Added circular icons for each pipeline layer (integrated, analyzing, researching, scoring, mapping, generating, publishing)
- Visual states: pending (gray) → executing (blue animated pulse) → success (green checkmark) → failed (red X) → skipped (gray)
- Responsive design with horizontal scrolling on mobile

**JavaScript Updates** (`frontend/static/js/job-detail.js`):
- Updated `resetPipelineSteps()` for horizontal layout
- Updated `updatePipelineStep()` to handle new DOM structure
- Added `showCurrentStepDetails()` to display layer details on click
- Added `updateProgressLine()` to render connecting line as steps complete

**Visual Enhancements**:
- Progress line animates from left to right as steps complete
- Current executing step has animated pulse ring effect
- Completed steps show green checkmark with instant color transition
- Step labels display below horizontal row for clarity
- Overall progress percentage displayed in header

**Files Modified**:
- `frontend/templates/partials/job_detail/_pipeline_progress.html` - New horizontal layout
- `frontend/static/js/job-detail.js` - Updated progress functions

---

### GAP-076: Meta-Prompt Endpoint Database Connection ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-08) | **Effort**: 15 minutes
**Impact**: Meta-prompt endpoint now properly connects to MongoDB without "db not defined" error

**Issue**: Endpoint was calling `db["level-2"]` without first obtaining database connection

**Fix Applied** (2025-12-08):
Added `db = get_db()` at start of meta-prompt route in `frontend/app.py:~2314`:
```python
@app.route('/api/meta-prompt/<job_id>', methods=['GET'])
def get_meta_prompt(job_id):
    db = get_db()  # ADDED: Initialize database connection
    job = db["level-2"].find_one({"_id": ObjectId(job_id)})
    # ... rest of endpoint
```

**Files Modified**:
- `frontend/app.py` - Added `db = get_db()` initialization

---

### GAP-077: CV Save Display Refresh ✅ COMPLETE
**Priority**: P1 HIGH | **Status**: COMPLETE (2025-12-08) | **Effort**: 30 minutes
**Impact**: CV editor changes now display immediately in preview after save

**Issue**: After saving CV in editor, preview pane didn't refresh showing new changes

**Fix Applied** (2025-12-08):
Added `renderCVPreview()` call immediately after successful save in `frontend/static/js/cv-editor.js`:
```javascript
// After successful save response
response = await response.json();
if (response.status === "success") {
    showToast("CV saved successfully", "success");
    renderCVPreview();  // ADDED: Refresh preview immediately
    updatePageBreaks();
}
```

**Files Modified**:
- `frontend/static/js/cv-editor.js` - Added `renderCVPreview()` after save success

**Result**: Users see CV changes reflected instantly in preview pane, improving UX feedback

---

### GAP-074: LinkedIn Outreach Integration - Simplified 2-Package Design ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-08) | **Effort**: 3 hours
**Impact**: Simplified LinkedIn outreach with 2 optimized packages per contact (reduced from 3)

**Implementation** (2025-12-08):

**State Schema Updates** (`src/common/state.py`):
- Added `ContactType` Literal type: `"hiring_manager"` | `"recruiter"` | `"vp_director"` | `"executive"` | `"peer"`
- Enhanced `Contact` TypedDict with new fields:
  - `contact_type`: Classification for routing decisions
  - `linkedin_connection_message`: Connection request text (≤300 chars with Calendly)
  - `linkedin_inmail`: Combined InMail/Email body (400-600 chars)
  - `linkedin_inmail_subject`: InMail subject line
  - `already_applied_frame`: Boolean flag for pre-applied positions
- Updated `OutreachPackage` with `contact_type` field

**Layer 5: People Mapper - Contact Classification** (`src/layer5/people_mapper.py`):
- New `classify_contact_type()` function using keyword matching:
  - Priority order: hiring_manager → recruiter → vp_director → executive → peer
  - Keywords per type (e.g., "hiring" → hiring_manager, "recruiter" → recruiter)
  - Fallback to "peer" if no keywords match
- Integrated into contact generation workflow
- No additional LLM calls (algorithmic classification)

**Layer 6: Outreach Generator - Simplified 2-Package Design** (`src/layer6/outreach_generator.py`):
- Creates 2 optimized packages per contact (simplified from 3):
  1. **linkedin_connection** (≤300 chars with Calendly):
     - Warm greeting + specific role interest + personalization
     - Includes Calendly link for scheduling
     - Character count enforcement (LinkedIn hard limit)
  2. **inmail_email** (400-600 chars with subject):
     - Combined package works for both InMail and Email
     - Prefers InMail content, falls back to email_body
     - Professional subject line + extended body
     - Call-to-action with clear next steps
- "Already applied" framing patterns for positions already submitted
- System prompts simplified for 2-format consistency

**LinkedIn/Outreach Document** (`linkedin/outreach.md` - NEW):
- Comprehensive guide synthesizing outreach best practices
- Contact type strategies with messaging templates
- Simplified 2-package specifications:
  - Connection package: Warm greeting + role interest + personalization + Calendly (≤300 chars)
  - InMail/Email package: Subject + professional body + CTA (400-600 chars)
- "Already applied" framing patterns for follow-ups
- MENA regional context and cultural considerations
- Character limits and tone guidance per contact type

**Frontend Updates** (`frontend/templates/job_detail.html`):
- New Intelligence Summary collapsible section combining:
  - Pain points (4 dimensions)
  - Company signals
  - Strategic needs
  - Risks
- Contact cards with contact type badges (color-coded):
  - Purple: Recruiter
  - Blue: Hiring Manager
  - Green: VP/Director
  - Orange: Executive
  - Grey: Peer
- Simplified outreach options for each contact:
  - Connection Request button (≤300 chars preview)
  - InMail/Email button (subject + body, works for both)
- Primary and secondary contacts now have identical formatting
- Contact type and outreach options visible at a glance

**Files Modified**:
- `src/common/state.py` - New ContactType + updated Contact/OutreachPackage
- `src/layer5/people_mapper.py` - Added `classify_contact_type()` function
- `src/layer6/outreach_generator.py` - Simplified 2-package generation
- `frontend/templates/job_detail.html` - Simplified contact cards (2 options instead of 3)

**Files Created**:
- `linkedin/outreach.md` - Comprehensive LinkedIn outreach guide

**Files Deleted**:
- `linkedin/outreach-claude.md` - Replaced by unified document
- `linkedin/outreach-chatgpt.md` - Replaced by unified document

**Benefits**:
- Reduced complexity (2 packages vs 3)
- Smarter contact routing (message tailored to contact type)
- Better response rates (contact-type-specific messaging)
- Faster outreach (2 optimized formats pre-generated)
- Simplified UX (fewer options per contact)
- MENA regional awareness (cultural context)
- Interview-ready (proven outreach patterns)
- Complete pipeline traceability with contact type

---

### GAP-078: Phase 7 - Interview Predictor ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-09) | **Effort**: 3 hours
**Impact**: Predicts likely interview questions from JD gaps and concerns identified during pipeline analysis

**Implementation** (2025-12-09):

**Backend Module** (`src/layer7/interview_predictor.py`):
- `InterviewPredictor` class predicting interview questions from CV/JD analysis
- Methods:
  - `predict_questions_from_concerns()` - Generate questions from identified red flags
  - `predict_questions_from_gaps()` - Generate questions from skill/experience gaps
  - `predict_technical_questions()` - Role-specific technical questions
  - `predict_behavioral_questions()` - Company/culture fit questions
  - `format_prep_materials()` - Structure questions with difficulty levels and prep guidance
- Integration with gap analysis, concern mitigation strategies
- Difficulty levels: Entry, Intermediate, Advanced
- Preparation materials with context, expected answers, follow-up strategies

**Tests** (`tests/unit/test_layer7_interview_predictor.py` - 30 tests):
- Question generation from various concern types
- Difficulty level assignment
- Behavioral vs technical split
- Deduplication logic
- Priority ranking
- Empty concern/gap handling

**Edge Cases** (`tests/unit/test_layer7_interview_predictor_edge_cases.py` - 35 tests):
- Large concern lists
- Malformed inputs
- Unicode handling
- Concurrency scenarios
- Token limit scenarios
- Budget exhaustion handling

**Files Created**:
- `src/layer7/interview_predictor.py` - Main implementation
- `tests/unit/test_layer7_interview_predictor.py` - 30 unit tests
- `tests/unit/test_layer7_interview_predictor_edge_cases.py` - 35 edge case tests

**Result**: Interview prep module ready for production use with comprehensive test coverage

---

### GAP-079: Phase 7 - Outcome Tracker ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-09) | **Effort**: 2.5 hours
**Impact**: Tracks application outcomes (rejected, no response, phone screen, offer, etc.)

**Implementation** (2025-12-09):

**Backend Module** (`src/analytics/outcome_tracker.py`):
- `OutcomeTracker` class for tracking application progression
- Methods:
  - `record_outcome()` - Log application status change
  - `get_outcome_history()` - Retrieve full outcome timeline
  - `calculate_conversion_rates()` - Analyze success metrics by tier/company type
  - `predict_outcome_timing()` - Estimate response times based on company signals
  - `generate_outcome_report()` - Summary statistics and trends
- Outcome statuses: Applied, Phone Screen, Technical Interview, Final Round, Offer, Rejected, No Response, Withdrawn
- Status transitions with timestamp validation
- Outcome impact analysis (company size, role type, effort invested)

**Tests** (`tests/unit/test_analytics_outcome_tracker.py` - 28 tests):
- Outcome recording and retrieval
- Timeline ordering
- Status transition validation
- Duplicate detection
- Conversion rate calculations
- Timing prediction accuracy
- Report generation

**Edge Cases** (`tests/unit/test_analytics_outcome_tracker_edge_cases.py` - 30 tests):
- Large outcome histories
- Concurrent updates
- Timezone handling
- Data corruption scenarios
- Missing data handling
- Performance with large datasets
- Concurrent writes from multiple sources

**Files Created**:
- `src/analytics/outcome_tracker.py` - Main implementation
- `tests/unit/test_analytics_outcome_tracker.py` - 28 unit tests
- `tests/unit/test_analytics_outcome_tracker_edge_cases.py` - 30 edge case tests

**Result**: Outcome tracking system fully operational with 58 comprehensive tests

---

### GAP-080: Phase 7 - Enhanced Annotation Types ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-09) | **Effort**: 1 hour
**Impact**: New type definitions for interview prep and outcome tracking

**Implementation** (2025-12-09):

**Type Additions** (`src/common/annotation_types.py`):

1. **InterviewQuestion** TypedDict:
   - `question_text: str` - The interview question
   - `category: Literal["technical", "behavioral", "situational"]` - Question type
   - `difficulty: Literal["entry", "intermediate", "advanced"]` - Difficulty level
   - `suggested_preparation: str` - How to prepare
   - `expected_keywords: List[str]` - Key points to mention
   - `followup_questions: List[str]` - Likely follow-ups
   - `company_specific: bool` - Is this company-specific?
   - `created_at: str` - ISO timestamp
   - `updated_at: str` - ISO timestamp

2. **InterviewPrep** TypedDict:
   - `job_id: str` - Associated job
   - `predicted_questions: List[InterviewQuestion]` - Generated questions
   - `preparation_status: Literal["none", "started", "complete"]` - User progress
   - `notes: str` - User's prep notes
   - `last_updated: str` - ISO timestamp

3. **ApplicationOutcome** TypedDict:
   - `job_id: str` - Associated job
   - `status: Literal["applied", "phone_screen", "technical", "final", "offer", "rejected", "no_response", "withdrawn"]` - Current status
   - `outcome_date: str` - ISO timestamp
   - `notes: str` - Outcome details
   - `feedback: str` - Recruiter/interviewer feedback if available
   - `salary_range: Optional[Dict[str, float]]` - If offer received
   - `offer_details: Optional[str]` - Offer specifics

4. **OutcomeStatus** Literal type for type safety

**Tests** (`tests/unit/test_annotation_types_phase7.py` - 25 tests):
- Type validation
- Field completeness
- Timezone handling
- Schema consistency
- Serialization/deserialization
- Default value behavior

**Files Modified**:
- `src/common/annotation_types.py` - Added 4 new types + enum

**Files Created**:
- `tests/unit/test_annotation_types_phase7.py` - 25 unit tests

**Result**: Type system extended for Phase 7 with full type safety

---

### GAP-081: Phase 7 - Frontend Interview Prep Panel ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-09) | **Effort**: 2 hours
**Impact**: UI for interview preparation with predicted questions and notes

**Implementation** (2025-12-09):

**Frontend Template** (`frontend/templates/partials/job_detail/_interview_prep_panel.html`):
- Collapsible panel showing predicted interview questions
- Question cards with:
  - Question text
  - Difficulty badge (Entry/Intermediate/Advanced with color coding)
  - Category tag (Technical/Behavioral/Situational)
  - "Preparation Guide" accordion with suggested preparation
  - Expected keywords highlight
  - Likely follow-up questions list
  - "Mark as Prepared" checkbox
- User notes textarea for personal prep notes
- Progress indicator: X/Y questions prepared
- Search/filter by difficulty and category
- Responsive design for mobile
- Collapsible by default to save space

**API Integration** (`frontend/app.py`):
- `GET /api/jobs/<id>/interview-prep` - Fetch interview prep data
- `POST /api/jobs/<id>/interview-prep/mark-prepared` - Mark question as prepared
- `PUT /api/jobs/<id>/interview-prep/notes` - Save preparation notes
- `GET /api/jobs/<id>/predict-interview-questions` - Trigger question prediction

**JavaScript Functions** (`frontend/static/js/interview-prep.js`):
- `loadInterviewPrep()` - Fetch and display questions
- `markQuestionPrepared()` - Toggle prepared status
- `savePreparationNotes()` - Auto-save notes
- `filterQuestionsByDifficulty()` - Filter display
- `expandQuestionDetails()` - Show full preparation guide
- `generateNewQuestions()` - Trigger re-prediction

**Files Created**:
- `frontend/templates/partials/job_detail/_interview_prep_panel.html` - Interview prep UI
- `frontend/static/js/interview-prep.js` - Interview prep functions

**Result**: Interview prep UI integrated into job detail page

---

### GAP-082: Phase 7 - Frontend Outcome Tracker Panel ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-09) | **Effort**: 1.5 hours
**Impact**: UI for tracking and updating application outcomes

**Implementation** (2025-12-09):

**Frontend Template** (`frontend/templates/partials/job_detail/_outcome_tracker.html`):
- Timeline view showing application status progression
- Status change form with:
  - Dropdown for status selection (Applied → Phone Screen → Final → Offer/Rejected)
  - Date/time picker for outcome date
  - Notes textarea for outcome details
  - Optional feedback text area (for rejections/feedback)
  - "Log Outcome" button
- Status timeline:
  - Vertical timeline with status badges
  - Timestamp for each status change
  - Notes preview on hover
  - Color-coded status (green=progress, yellow=pending, red=rejected)
- Outcome summary:
  - Current status with large badge
  - Days since application
  - Expected next steps based on status
- Salary/offer details section (visible when status="offer")
- Statistics (if multiple applications):
  - Conversion rate to phone screens
  - Conversion rate to offers
  - Average time to response

**API Endpoints** (`frontend/app.py`):
- `GET /api/jobs/<id>/outcome-history` - Fetch full outcome timeline
- `POST /api/jobs/<id>/outcome` - Log outcome status change
- `GET /api/jobs/<id>/outcome-stats` - Get conversion statistics
- `PUT /api/jobs/<id>/outcome/<timestamp>` - Edit past outcome

**Frontend Integration**:
- Outcome tracker loaded in job detail page
- Auto-refresh every 60 seconds to catch external updates
- Optimistic UI updates (show change immediately, sync with backend)
- Toast notifications for outcome changes

**Files Created**:
- `frontend/templates/partials/job_detail/_outcome_tracker.html` - Outcome tracking UI

**Result**: Outcome tracker fully integrated into job detail page with timeline visualization

---

### GAP-083: Phase 7 - API Endpoints for Interview & Outcome ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-09) | **Effort**: 1.5 hours
**Impact**: 7 new API endpoints for interview prep and outcome tracking

**Implementation** (2025-12-09):

**Endpoints** (`frontend/app.py`):

1. **GET /api/jobs/<id>/interview-prep**
   - Returns: `{ predicted_questions: [...], preparation_status: "...", notes: "..." }`
   - Query params: `?include_preparation_guides=true`
   - Cache: 1 hour TTL

2. **POST /api/jobs/<id>/interview-prep/predict**
   - Triggers interview question prediction
   - Input: Optional concern list override
   - Returns: `{ status: "queued|completed", question_count: X }`

3. **POST /api/jobs/<id>/interview-prep/mark-prepared**
   - Mark individual question as prepared
   - Input: `{ question_index: N, prepared: true|false }`
   - Returns: `{ prepared_count: X, total_count: Y }`

4. **PUT /api/jobs/<id>/interview-prep/notes**
   - Save user preparation notes
   - Input: `{ notes: "..." }`
   - Returns: `{ status: "success", updated_at: "..." }`

5. **GET /api/jobs/<id>/outcome-history**
   - Returns full timeline of status changes
   - Returns: `{ outcomes: [{ status, date, notes }, ...] }`

6. **POST /api/jobs/<id>/outcome**
   - Log new outcome status change
   - Input: `{ status: "phone_screen|...", date: ISO8601, notes: "...", feedback: "..." }`
   - Returns: `{ recorded: true, outcome_count: X }`

7. **GET /api/jobs/<id>/outcome-stats**
   - Returns conversion statistics for user's applications
   - Returns: `{ total_applied: N, phone_screens: N, offers: N, conversion_rate: X% }`

**Error Handling**:
- 400 Bad Request for invalid status transitions
- 404 Not Found for invalid job_id
- 422 Unprocessable Entity for invalid data
- 500 Internal Server Error with descriptive messages

**Authentication**: All endpoints require session authentication (cookie-based)

**Rate Limiting**: Standard 1000 requests/hour per user

**Files Modified**:
- `frontend/app.py` - Added 7 new endpoint implementations

**Result**: Full API coverage for Phase 7 features

---

### GAP-084: Pipeline Overhaul Phase 1-3 - Tiered Model System, Operation Base, Independent Actions ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-10) | **Effort**: 12 hours
**Impact**: Foundation for decoupled operations with cost-optimized model selection per action

**Implementation** (2025-12-10):

**Phase 1: Model Tier System** (`src/common/model_tiers.py`):
- 3-tier model selection: Fast (Haiku), Balanced (Sonnet), Quality (Opus)
- Per-operation model configuration matrix
- Cost estimation per tier (Fast: $0.01, Balanced: $0.05, Quality: $0.15 per operation)
- Dynamic model fallback when preferred model unavailable
- Test coverage: 46 unit tests validating tier selection, cost calculations, fallback logic

**Phase 2: Operation Base Class** (`src/services/operation_base.py`):
- Reusable base class for button-triggered operations (OperationBase)
- Built-in health checks, retry logic with exponential backoff
- State management: pending → executing → completed|failed
- Progress tracking with 0-100% completion indicator
- Error recovery: automatic retry up to 3 times with circuit breaker
- Timeout handling: configurable per operation (default 300s)
- Test coverage: 22 unit tests validating state transitions, retries, health checks, timeout handling

**Phase 3: Independent Action Buttons & API Routes**:

**Frontend UI** (`frontend/templates/job_detail.html`):
- Three independent action buttons: "Structure JD", "Research Job", "Generate CV"
- Tiered model selector (Fast/Balanced/Quality) with cost indicators
- Real-time status display (pending → executing → completed)
- Progress bar with percentage and elapsed time
- One-click execution without full pipeline run

**JavaScript State Management** (`frontend/static/js/pipeline-actions.js`):
- Alpine.js state machine for button states
- Automatic polling of operation status (500ms interval)
- Cost calculator UI: Shows estimated cost per tier before execution
- Result display: Shows operation output with copy-to-clipboard

**CSS Styling** (`frontend/static/css/pipeline-actions.css`):
- Button states: normal → loading → success/error
- Animated spinner during execution
- Progress bar with gradient fill
- Toast notifications for completion/error

**Heatmap Fix** (`frontend/static/js/jd-annotation.js`):
- applyHighlights() fully implemented with DOM targeting
- Proper selection targeting: `document.querySelectorAll('[data-annotation-id="..."]')`
- Background color application with rgba styling
- Cleanup: Removes previous highlights before applying new ones

**API Routes** (`runner_service/routes/operations.py`):
- POST `/api/operations/structure-jd` - Structure raw JD with tiered models
  - Input: `{ job_id, tier: "fast|balanced|quality" }`
  - Output: `{ status, structured_jd, cost_usd, elapsed_seconds }`
- POST `/api/operations/research-company` - Research company with tiered models
  - Input: `{ company_name, tier }`
  - Output: `{ status, research_summary, signals, cost_usd }`
- POST `/api/operations/generate-cv-variant` - Generate CV variant with selected tier
  - Input: `{ job_id, tier, variant_type }`
  - Output: `{ status, cv_text, elapsed_seconds, cost_usd }`
- GET `/api/operations/{operation_id}/status` - Poll operation status
  - Output: `{ status, progress_percent, elapsed_seconds, error_message }`

**Router Registration** (`runner_service/routes/__init__.py`):
- Centralized route registration
- Middleware attachment for auth and logging
- Operation route mounting at `/api/operations`

**Files Created**:
- `src/common/model_tiers.py` - 3-tier model system (380 lines)
- `src/services/operation_base.py` - Operation base class (450 lines)
- `frontend/static/css/pipeline-actions.css` - Button and state styling (200 lines)
- `frontend/static/js/pipeline-actions.js` - Alpine.js state machine (320 lines)
- `runner_service/routes/operations.py` - Independent operation endpoints (280 lines)
- `runner_service/routes/__init__.py` - Router registration (40 lines)

**Files Modified**:
- `frontend/static/js/jd-annotation.js` - applyHighlights() implementation (80 lines added)
- `frontend/templates/job_detail.html` - Added action buttons and tier selector
- `runner_service/app.py` - Integrated operation routes via router

**Tests Added**:
- `tests/unit/test_model_tiers.py` - 46 tests (tier selection, costs, fallback)
- `tests/unit/test_operation_base.py` - 22 tests (state machine, retries, health checks)

**Next Phases**:
- **Phase 4** (pending): Implement actual service logic in operation handlers
- **Phase 5** (pending): Decouple contacts and outreach from main pipeline
- **Phase 6** (pending): End-to-end testing and final documentation

**Cost Impact**:
- Fast tier: ~$0.01 per operation (suitable for low-value jobs)
- Balanced tier: ~$0.05 per operation (default for most jobs)
- Quality tier: ~$0.15 per operation (for high-value positions)

**Commits**: Pipeline overhaul Phase 1-3 with 68 new tests passing

---

### GAP-085: Layer 3/3.5 - Company/Role Research Not Annotation-Aware
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 8 hours
**Impact**: Company research now integrates annotation guidance for targeted research

**Implementation Complete** (Phase 4):
- `src/services/company_research_service.py` now accepts and uses `jd_annotations` parameter
- Research is now guided by must-have priorities and passion areas
- Annotation context (must_have_keywords, gap_areas, core_strength_areas) passed to FireCrawl queries and LLM analysis
- Company research focused on passion annotations (love_it) for culture research priorities
- Must-have priorities inform technical research areas
- Identity annotations guide which company values to emphasize

**Implementation Details**:
- Added `_extract_annotation_research_focus()` method to extract research priorities from annotations
- Annotation context injected into company research prompts
- Research outputs enriched with annotation-aligned insights

---

### GAP-086: Layer 5 - People Mapper Not Annotation-Aware
**Priority**: P3 LOW | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 6 hours
**Impact**: Contact discovery now uses annotation-derived focus for targeted discovery

**Implementation Complete** (Phase 8):
- `src/layer5/people_mapper.py` now accepts and uses `jd_annotations` parameter
- SEO queries now incorporate pain point keywords for focused searches
- Must-have annotations now prioritize which contacts to find
- Technical skill keywords guide search query refinement
- Annotation context injected into contact discovery prompts

**Implementation Details**:
- Added `_build_annotation_enhanced_queries()` method for SEO keyword query building
- Annotation priorities (must_have_keywords, core_strengths) used in contact filtering
- Technical focus areas extracted from annotations to refine LinkedIn searches

---

### GAP-087: Layer 7 - Interview/Outcome Not Using Annotations
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 12 hours
**Impact**: Interview prediction now uses annotations for targeted question generation, outcome tracking links to predictions

**Implementation Complete** (Phase 5):
- `src/layer7/interview_predictor.py` now actively uses `jd_annotations` parameter
- `src/layer7/outcome_tracker.py` now links outcomes to annotation predictions
- Gap annotations used to predict "Tell me about your experience with X" weakness questions
- Reframe notes now populate preparation_note field in question prep materials
- Core strength annotations now predict deep-dive behavioral and impact questions
- Outcomes track which annotation predictions proved accurate

**Implementation Details**:
- Added passion_probe and identity_probe question types in interview_predictor.py
- Gap analysis drives question generation for areas where candidate may have weaknesses
- Reframe guidance injected into prep materials for answering sensitive questions
- Outcome tracker correlates application status with annotation-driven predictions

---

### GAP-088: Cover Letter - Passion/Identity Dimensions Not Used
**Priority**: P1 HIGH | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 8 hours
**Impact**: Cover letters now authentic enthusiasm hooks and proper professional positioning using passion/identity data

**Implementation Complete** (Phase 3):
- `src/layer6/cover_letter_generator.py` now uses passion and identity dimensions
- Passion dimension (love_it, enjoy, avoid) now drives content generation
- Identity dimension (core_identity, not_identity) now shapes positioning and tone
- Cover letters include authentic enthusiasm hooks based on passion annotations
- Topics tagged with `passion=avoid` are de-emphasized or excluded
- Positioning aligns with `identity=core_identity` for authentic professional narrative
- Introductions avoid areas marked as `identity=not_identity`

**Implementation Details**:
- Added `_format_passion_identity_section()` method for authentic enthusiasm hooks
- Passion/identity priorities injected into cover letter prompt
- Content generation uses identity context to shape tone and positioning
- Multi-dimensional annotation context passed through header generation context

---

### GAP-089: ATS Keyword Coverage Not Validated Post-Generation
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 4 hours
**Impact**: ATS requirements are now validated post-generation with detailed coverage reports

**Implementation Complete** (Phase 6):
- `annotation_header_context.py` builds `ats_requirements` dict with min/max occurrences
- CV is generated with keywords injected
- Post-generation validation now validates that targets were met
- `ats_variants` fully propagated and utilized
- Post-generation keyword count validation enabled
- Warnings generated if min_occurrences not met
- Warnings generated if max_occurrences exceeded
- ATS readiness score recalculated after generation

**Implementation Details**:
- Added `ATSValidationResult` type in `src/layer6_v2/types.py`
- Added `_validate_ats_coverage()` method in orchestrator for post-generation validation
- ATS validation reports included in generation output
- Keyword occurrence counts tracked and reported per category

---

### GAP-090: STAR Selector Annotation Boost Disabled
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 2 hours
**Impact**: STAR selection now uses annotation boost for optimal STAR prioritization

**Implementation Complete** (Phase 2):
- `src/layer2_5/star_selector.py` now has `enabled: True` in config
- Annotation boost code fully operational and applied to STAR selection
- Infrastructure concerns resolved through proper dependency management

**Implementation Details**:
- STAR records linked via `star_ids` now properly prioritized
- Annotation boost multiplier applied to STAR selection scoring
- Core strength STARs elevated in ranking based on identity annotations
- Passion-annotated STARs boosted with enthusiasm markers

---

### GAP-091: Outreach Generation Not Annotation-Aware
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 12 hours
**Impact**: Connection requests and InMails now use annotation-derived personalization for authentic engagement

**Implementation Complete** (Phase 7):
- `src/layer6c/outreach_generator.py` now actively uses `jd_annotations` parameter
- Templates now dynamic with annotation-derived substitution
- Passion-based hooks provide authentic enthusiasm in opening messages
- Identity-based positioning for compelling value proposition
- Passion dimension now drives genuine connection hooks in opener
- Identity dimension now guides professional positioning and framing
- Must-have priorities emphasized in value proposition section
- Core strengths highlighted prominently in outreach narrative

**Implementation Details**:
- Added `_format_annotation_context()` method to extract and format annotation priorities
- Extended with passion/identity/avoid sections in outreach formatting
- Must-have requirements highlighted in opening message
- Identity alignment emphasized in professional positioning statement
- Concern mitigation integrated into outreach messaging

---

### GAP-095: Annotation Tracking Service - A/B Testing Framework ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-11) | **Effort**: 8 hours
**Impact**: Complete annotation outcome tracking and A/B testing analytics for persona variants

**Implementation Complete** (Phase P2):
- `src/services/annotation_tracking_service.py` - NEW service with full A/B testing capability
- Complete ApplicationTracking lifecycle with PersonaVariant configurations
- AnnotationOutcome tracking for individual keyword usage
- ApplicationOutcome enum for PENDING → OFFER → ACCEPTED progression
- AnnotationEffectivenessStats aggregating keyword → interview correlation

**Key Features**:
1. **PersonaVariant** - Captures identity/passion/core_strength keyword sets for A/B testing
2. **ApplicationTracking** - Records complete application with persona variant snapshot
3. **AnnotationOutcome** - Individual annotation usage tracking with outcome linkage
4. **Effectiveness Analytics**:
   - `calculate_keyword_effectiveness()` - Aggregates keyword success rates
   - `compare_persona_variants()` - Compares A/B test results statistically
   - `get_placement_effectiveness()` - CV position → interview rate correlation

**Integration Points**:
- Hooks into pipeline Layer 7 Outcome Tracker for feedback loop
- Ingests application outcomes from interview/offer tracking
- Provides analytics dashboard for persona optimization

**Test Coverage**: 20 unit tests in `tests/unit/test_annotation_tracking_service.py` - all passing
- PersonaVariant validation (5 tests)
- AnnotationOutcome tracking (5 tests)
- ApplicationTracking lifecycle (5 tests)
- AnnotationEffectivenessStats calculation (5 tests)

**Files Created**:
- `src/services/annotation_tracking_service.py` - Core service (450+ lines)
- `tests/unit/test_annotation_tracking_service.py` - Full test suite (350+ lines)

---

### GAP-096: KeywordPlacementValidator Integration into CV Generation ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-11) | **Effort**: 6 hours
**Impact**: ATS keyword placement optimization with position-based validation

**Implementation Complete** (Phase P2.1):
- `src/layer6_v2/keyword_placement.py` - NEW validator with 4-section scoring algorithm
- Integrated as Phase 5.7 in `src/layer6_v2/orchestrator.py` CV generation pipeline
- Post-generation validation running after all CV text assembly

**Validation Rules**:
- Headline section: 40 points (highest priority)
- Narrative section: 30 points (professional summary)
- Competencies/Skills section: 20 points
- First role description: 10 points (lowest priority)
- Passing score: 70+ points (covers multiple sections)

**Output**:
- `keyword_placement_validation` in orchestrator output
- ATS violations list (missing priority keywords)
- Improvement suggestions (placement recommendations)
- Per-keyword placement analysis

**Integration**:
- Runs post-CV generation in orchestrator as Phase 5.7
- Validates top_keywords from JD annotations
- Provides actionable feedback for CV improvement

**Test Coverage**: Covered in existing layer6_v2 tests
- Integration tested in `test_layer6_cv_generator_v2.py`

**Files Modified**:
- `src/layer6_v2/orchestrator.py` - Added Phase 5.7 validation
- `src/layer6_v2/keyword_placement.py` - Validator implementation (existing)
- `src/layer6_v2/types.py` - Added `KeywordPlacementResult` type

---

### GAP-092: Reframe Application Not Traced
**Priority**: P3 LOW | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 4 hours
**Impact**: Full traceability for reframe guidance application across generated content

**Implementation Complete** (Phase 9):
- `GeneratedBullet` with `reframe_applied` field fully validated
- Reframe map built and passed through generators with tracking
- Post-generation validation confirms reframes were applied
- Detailed logging of which reframes influenced which bullets
- Traceability in output showing reframe→bullet mapping
- Warnings generated if reframe note exists but wasn't applied

**Implementation Details**:
- Added `_validate_reframe_application()` method in orchestrator
- Bullet generation logs reframe application events
- Output includes reframe traceability metadata
- Warnings generated for unimplemented reframe guidance

---

### GAP-093: Section Coverage Not Enforced
**Priority**: P3 LOW | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 3 hours
**Impact**: JD section coverage is now enforced with visual indicators and validation

**Implementation Complete** (Phase 10):
- `AnnotationSettings` with `require_full_section_coverage` boolean fully operational
- `section_coverage` dict now properly populated and tracked
- UI indicators show section coverage status in real-time
- Validation prevents save with incomplete coverage (when setting enabled)
- Per-section annotation count tracking operational
- Visual indicators show uncovered sections with progress bars
- Warnings displayed when saving with incomplete coverage
- Coverage targets enforced: 5 responsibilities, 5 qualifications, 4 technical skills, 2 nice-to-haves

**Implementation Details**:
- Added `validateCoverage()` function in jd-annotation.js
- Coverage warnings displayed in annotation panel
- Per-section progress tracking with visual feedback
- Save validation checks coverage requirements

---

### GAP-094: Annotation Review Workflow Not Implemented
**Priority**: P3 LOW | **Status**: ✅ COMPLETE (2025-12-10) | **Effort**: 16 hours
**Impact**: Annotation review workflow fully implemented with status transitions and bulk operations

**Implementation Complete** (Phase 11):
- `JDAnnotation` with `status` field (draft, approved, rejected, needs_review) fully operational
- `created_by` tracking (human, pipeline_suggestion, preset) active
- UI review queue for pipeline-generated suggestions fully implemented
- Status transition workflow enforced with validation
- Review queue interface shows pending suggestions
- Approve/reject buttons with notes functional
- Status filters available in annotation list
- Bulk approve/reject functionality operational
- Review history tracking with timestamps and user attribution

**Implementation Details**:
- Added review queue UI in annotation panel
- Approve/reject buttons with optional note fields
- Status filters for dashboard and bulk operations
- Bulk operation handlers for approve/reject/discard
- Review history stored with annotation changes

---

## P3: LOW (Backlog)

### GAP-026: CV V2 - Spacing 20% Narrower ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: CV layout is now 20% more compact for better information density

**Fix Applied** (2025-12-01):
Reduced margins/spacing across all CV elements by ~20%:

| Element | Before | After |
|---------|--------|-------|
| h1 margin | 0 0 12px 0 | 0 0 10px 0 |
| h2 margin | 16px 0 10px | 12px 0 8px |
| h2 padding-top | 8px | 6px |
| h3 margin | 12px 0 8px | 10px 0 6px |
| Paragraph margin | 0.5em | 0.4em |
| List margin | 0.5em | 0.4em |
| List item margin | 0.25em | 0.2em |

**Files Modified**:
- `pdf_service/pdf_helpers.py` - PDF output CSS
- `frontend/templates/base.html` - Editor + display container CSS

---

### GAP-027: .docx CV Export
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Currently PDF only; some recruiters prefer Word format

---

### GAP-028: Runner Terminal Copy Button ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (already implemented) | **Effort**: N/A
**Impact**: Copy button for pipeline logs already exists and works

**Verification** (2025-12-01): Feature was already fully implemented at `frontend/templates/job_detail.html:2737`

**Existing Implementation**:
- `copyLogsToClipboard()` function in job detail template
- Uses Clipboard API with execCommand fallback for older browsers
- Visual feedback: "Copied!" notification on success
- Button located in runner terminal header

---

### GAP-029: UI/UX Design Refresh
**Priority**: P3 LOW | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 2 hours
**Impact**: Modern styling improvements needed

**Fix Applied**:
Design system enhancements:
1. **Dark Mode Badges**: Added proper visibility adjustments for all badge variants
2. **Status Colors**: Created theme-aware status classes (`status-success`, `status-error`, etc.)
3. **Quick Date Filters**: Theme-aware button styles for hour/week/month filters
4. **LinkedIn Brand Color**: Added `linkedin-color` class with dark mode support
5. **Button Consistency**: Process Job button now uses design system `.btn-success`
6. **Template Updates**: Replaced hardcoded Tailwind colors with theme variables

**Files Modified**:
- `frontend/templates/base.html` - Extended design system
- `frontend/templates/index.html` - Updated quick date filter buttons
- `frontend/templates/job_detail.html` - Updated Process Job button

---

### GAP-030: Layer-Specific Prompt Optimization
**Priority**: P3 LOW | **Status**: ✅ COMPLETE (2025-12-09) | **Effort**: Ongoing
**Impact**: Phase 2 focus - improve prompt quality per layer

**Completion Summary** (2025-12-09):

**Layer 7 (Interview Predictor) - P1**:
- Created `tests/unit/test_layer7_prompt_improvements.py` - 22 unit tests
- Added `validate_question_quality()` function in `src/layer7/interview_predictor.py`
- Enhanced system prompt with:
  - Few-shot examples of high-quality questions
  - Distribution requirements (technical/behavioral balance)
  - Yes/no detection for filtering
  - Length validation rules
- Test coverage: question quality validation, yes/no detection, length validation, question type distribution, source attribution

**Layer 6a (Cover Letter Generator) - P2**:
- Created `tests/unit/test_layer6_cover_letter_improvements.py` - 24 unit tests
- Enhanced `SYSTEM_PROMPT` in `src/layer6/cover_letter_generator.py` with:
  - Explicit STAR citation rules with CORRECT/WRONG examples
  - Complete generic phrases blocklist (12 phrases: "diverse team", "best practices", "synergy", etc.)
  - Pain point mapping requirements (every paragraph maps to identified pain points)
  - Few-shot examples showing high-quality citations
  - Anti-hallucination checklist for writers
- Test coverage: source citation rules, generic phrase detection, pain point mapping, quality gates

**Integration**:
- All 1275 unit tests passing (35 skipped)
- Prompts integrated into production pipeline
- Layer 6a and Layer 7 now have enhanced quality controls for generated content

**Plan**: `plans/prompt-optimization-plan.md`

---

### GAP-031: FireCrawl Contact Discovery AI Fallback Agent
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 8-12 hours
**Impact**: When FireCrawl fails (rate limits, blocked sites, network errors), pipeline returns empty contacts

**Detailed Plan**: `plans/ai-agent-fallback-implementation.md`

**Architecture**:
```
FireCrawl Search → [Success?] → Yes → Return Contacts
                         ↓ No (after 2 retries)
              AI Agent Fallback (gpt-4o-mini)
                         ↓
              Generate 8 Synthetic Contacts
              (Recruiter, Hiring Manager, VP, etc.)
```

**Implementation Required**:
1. Create `src/layer5/contact_fallback_agent.py` - ContactFallbackAgent class
2. Integrate into `src/layer5/people_mapper.py` - Add fallback logic after FireCrawl failures
3. Add config: `ENABLE_FIRECRAWL_FALLBACK=true`, `FIRECRAWL_MAX_RETRIES=2`
4. Track fallback usage in metrics

**Cost Impact**: +$0.02/job when fallback triggers

---

### GAP-032: Job Iframe Viewer
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: View original job posting in iframe

**Plan**: `plans/job-iframe-viewer-implementation.md`

---

### GAP-033: Dossier PDF Export ✅ COMPLETE
**Priority**: P3 LOW | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 2 hours
**Impact**: Complete job dossier now exportable as PDF

**Implementation** (2025-12-01):

1. **DossierPDFExporter** (`src/api/pdf_export.py`):
   - Builds comprehensive HTML with 9 sections:
     - Header (title, timestamp)
     - Company Information (research, signals)
     - Role Details (summary, business impact, why now)
     - Job Description
     - Pain Points (4 dimensions)
     - Fit Analysis (score box, rationale)
     - Contacts (primary/secondary)
     - Outreach Materials (cover letter, messages)
     - CV Information
   - Professional styling with A4 page format
   - Renders via pdf-service `/render-pdf` endpoint

2. **Flask Endpoint** (`frontend/app.py:2072-2150`):
   - `GET /api/jobs/{job_id}/export-dossier-pdf`
   - Fetches job from MongoDB, generates PDF, streams to browser
   - Auto-generates filename: `dossier-{company}-{title}.pdf`

3. **Frontend Button** (`frontend/templates/job_detail.html`):
   - "Export Dossier" button next to Process button
   - Loading state, success/error toasts
   - `exportDossierPDF()` JavaScript function

**Plan**: `plans/dossier-pdf-export-implementation.md`

---

### GAP-034: Bulk Job Processing ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE | **Effort**: 2 hours (backend existed)
**Impact**: Batch processing now available via UI - select multiple jobs and process together

**Discovery** (2025-12-01):
The backend bulk processing was **already implemented** but had no frontend UI:
- `/jobs/run-bulk` endpoint existed in `runner_service/app.py:236-256`
- `RunBulkRequest` model existed in `runner_service/models.py:23-28`
- Proxy endpoint existed in `frontend/runner.py:71-104`
- Concurrency control via `asyncio.Semaphore(MAX_CONCURRENCY)` already in place

**Fix Applied** (2025-12-01):
1. Added "Process Selected" button to job list (`frontend/templates/index.html`)
2. Updated `updateSelectionCount()` to enable/disable process button
3. Added `processSelectedJobs()` function in `frontend/templates/base.html`
4. Button calls `/api/runner/jobs/run-bulk` with selected job IDs
5. Confirmation dialog shows job count before processing
6. Selection clears after successful queue submission

**Concurrency Configuration**:
```bash
# Environment variable (default: 3, range: 1-20)
MAX_CONCURRENCY=5  # Increase for batch processing day
```

**Usage**:
1. Go to job list page
2. Select jobs via checkboxes (or "Select All")
3. Click green "Process Selected" button
4. Confirm batch processing
5. Jobs queued and processed (up to MAX_CONCURRENCY simultaneously)

---

### GAP-035: CV Generator Test Mocking
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: CV generator tests run reliably without API calls

**Fix Applied** (2025-12-01):
1. LLM mocking was already in place (`mock_llm_providers` fixture lines 22-51)
2. Fixed parallel test race condition with `tmp_path` isolation
3. Updated `cleanup_test_output` to use unique temp directories per test
4. All 21 tests now pass with parallel execution

**Key Changes**:
- `tests/unit/test_layer6_markdown_cv_generator.py`: Changed `cleanup_test_output` fixture to use `tmp_path` and `os.chdir()` for test isolation
- Removed manual cleanup code that caused race conditions

**Verification** (2025-12-09):
- Test mocking confirmed working with comprehensive `mock_llm_providers` fixture (lines 22-41 of test_layer6_markdown_cv_generator.py)
- Patches `create_tracked_cv_llm` factory for reliable offline testing
- Unit test suite passes: 1095 tests passing, 35 skipped

---

### GAP-036: Cost Tracking Per Pipeline Run
**Priority**: P2 MEDIUM | **Status**: ✅ COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Full visibility into LLM costs per job

**Fix Applied** (2025-12-01):
1. Added `total_cost_usd` and `token_usage` to initial state in `src/workflow.py`
2. Capture token usage from `get_global_tracker()` after pipeline execution
3. Persist cost fields to MongoDB in `src/layer7/output_publisher.py:374-379`
4. Added cost summary to pipeline completion logs

**Token Tracking Infrastructure** (already existed):
- `src/common/token_tracker.py`: Comprehensive `TokenTracker` class with per-provider cost estimates
- `UsageSummary` with `by_provider` dict containing input/output tokens and costs
- Global tracker accessed via `get_global_tracker()`

---

### Configuration: MongoDB URI Environment Variable Fallback Chain
**Status**: ✅ VERIFIED (2025-12-09) | **Impact**: Backward-compatible MongoDB configuration

**Implementation** (Already in codebase):
1. **Primary**: `MONGODB_URI` environment variable (standard MongoDB URI format)
2. **Fallback**: `MONGO_URI` (legacy variable name for backward compatibility)
3. **Default**: `mongodb://localhost:27017` (local development)

**Locations**:
- `runner_service/app.py:301` - Main MongoDB connection with error handling
- `runner_service/app.py:987-990` - CV PDF generation with sensible defaults
- `runner_service/persistence.py:40` - Pipeline state persistence with graceful skip if not configured

**Verification** (2025-12-09):
- Backward-compatible fallback chain confirmed in code
- Allows flexible deployment across environments (local, VPS, Atlas)
- Production uses `MONGODB_URI`; development can use local default
- No configuration gaps identified

---

### GAP-037: External Health Monitoring ✅ COMPLETE
**Priority**: P2 MEDIUM | **Status**: COMPLETE (2025-12-01) | **Effort**: 15 minutes
**Impact**: External alerting when VPS goes down

**Fix Applied** (2025-12-01):
Added public `/health` endpoint to frontend (`frontend/app.py:1067-1099`) that doesn't require authentication.

**Monitoring Endpoints**:
| Service | URL | Auth Required |
|---------|-----|---------------|
| VPS Runner | `http://72.61.92.76:8000/health` | No |
| Frontend | `https://job-search-inky-sigma.vercel.app/health` | No |

**UptimeRobot Setup** (User Action Required):

1. **Create UptimeRobot account** (free tier: 50 monitors)
   - Go to https://uptimerobot.com/
   - Sign up with email

2. **Add VPS Runner Monitor**:
   - Monitor Type: HTTP(s)
   - Friendly Name: "Job Search - VPS Runner"
   - URL: `http://72.61.92.76:8000/health`
   - Monitoring Interval: 5 minutes

3. **Add Frontend Monitor**:
   - Monitor Type: HTTP(s)
   - Friendly Name: "Job Search - Frontend"
   - URL: `https://job-search-inky-sigma.vercel.app/health`
   - Monitoring Interval: 5 minutes

4. **Configure Alerts**:
   - Email alerts (free)
   - Slack webhook (optional)
   - Mobile push (free mobile app)

**Expected Health Response**:
```json
{
  "status": "healthy",
  "version": "1.0.3",
  "services": {
    "mongodb": "connected",
    "runner": "healthy"
  }
}
```

---

### GAP-038: Complete JobState Model
**Priority**: P2 MEDIUM | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 30 min
**Impact**: Missing fields: tier, dossier_path, cv_text, application_form_fields

**Fix Applied**:
Added missing fields to canonical `src/common/state.py`:
- `tier` (Layer 4): Job priority tier derived from fit_score ("A"/"B"/"C"/"D")
- `dossier_path` (Layer 7): Path to generated dossier file
- `application_form_fields` (Layer 1.5): FormField list for job application pre-filling
- Note: `cv_text` was already present in state.py

**Files**: `src/common/state.py` (updated), `src/common/types.py` (FormField import)

---

### GAP-039: Security Audit
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4 hours
**Impact**: No formal security review

**Fix**: Git history scan, path traversal check, input validation, `safety check`

---

### GAP-040: API Documentation (OpenAPI) ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 2 hours
**Impact**: Interactive API documentation now available

**Fix Applied** (2025-12-01):
1. Created `frontend/static/openapi.yaml` - Full OpenAPI 3.0.3 spec covering all API endpoints
2. Created `frontend/templates/api_docs.html` - Swagger UI with custom styling
3. Added routes in `frontend/app.py`:
   - `/api-docs` → Swagger UI interface
   - `/api/openapi.yaml` → Raw spec file
4. Created `postman/Job-Search-Runner-API.postman_collection.json` - Postman collection

**Access**: https://job-search-inky-sigma.vercel.app/api-docs

---

### GAP-041: Operational Runbook
**Priority**: P3 LOW | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1 hour
**Impact**: No documented procedures for common issues

**Fix Applied**:
Created comprehensive `RUNBOOK.md` covering:
1. **Quick Health Check** - Dashboard indicators, API endpoints
2. **Service Status** - VPS, MongoDB, PDF service commands
3. **Common Issues** - Pipeline stuck, PDF fails, FireCrawl rate limits, 500 errors
4. **Pipeline Troubleshooting** - Run history, LangSmith traces, re-run commands
5. **Database Operations** - Backup, clear stuck jobs, reset cache
6. **Recovery Procedures** - Full restart, rollback, emergency disable
7. **Monitoring** - Key metrics, UptimeRobot setup, daily checks

---

### GAP-042: Performance Benchmarks ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 3 hours
**Impact**: Baseline metrics and benchmark tests established

**Implementation** (2025-12-01):

1. **Target Latencies Documented** (`tests/benchmarks/__init__.py`):
   - Layer 1-4 (JD Extractor): < 3s
   - Layer 2 (Pain Point Miner): < 5s
   - Layer 3.0 (Company Researcher): < 8s (with FireCrawl)
   - Layer 3.5 (Role Researcher): < 3s
   - Layer 4 (Opportunity Mapper): < 3s
   - Layer 5 (People Mapper): < 10s (with FireCrawl)
   - Layer 6 (CV Generator V2): < 15s
   - Layer 7 (Output Publisher): < 2s
   - Full Pipeline: < 60s
   - PDF Generation: < 5s
   - MongoDB Query: < 100ms

2. **Benchmark Test Suite** (`tests/benchmarks/test_pipeline_benchmarks.py`):
   - `TestMockedLayerBenchmarks`: Layer processing with mocked LLMs
   - `TestValidationBenchmarks`: Validation helper performance (10ms target)
   - `TestHTMLGenerationBenchmarks`: Dossier HTML generation (100ms target)
   - `TestDatabaseBenchmarks`: MongoDB query latency (100ms target)
   - `BenchmarkResult` class with pass/fail margin calculation
   - `run_benchmark()` utility for consistent measurement

**Running Benchmarks**:
```bash
pytest tests/benchmarks -v --benchmark
pytest tests/benchmarks/test_pipeline_benchmarks.py -v
```

**Files**: `tests/benchmarks/__init__.py`, `tests/benchmarks/test_pipeline_benchmarks.py`

---

### GAP-043: Pipeline Runs History Collection
**Priority**: P3 LOW | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1.5 hours
**Impact**: No historical record of pipeline runs

**Fix Applied**:
Added pipeline run persistence to MongoDB:
1. **Collection**: `pipeline_runs` with indexes (run_id, job_id, created_at, status)
2. **Tracking**: Runs saved at start, updated at completion with:
   - Status (processing → completed/partial/failed)
   - Duration, fit_score, fit_category, errors
   - LangSmith trace_url, total_cost_usd
3. **API**: `GET /api/pipeline-runs?job_id=X&status=completed&limit=50`

**Files**:
- `src/workflow.py` - Added `save_pipeline_run_start()` and `update_pipeline_run_complete()`
- `frontend/app.py` - Added `/api/pipeline-runs` endpoint
- `src/common/database.py` - Collection accessor already existed

---

### GAP-044: Knowledge Graph Edges for STAR
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 6-8 hours
**Impact**: STAR records lack relationship graph

**Fix**: Add graph edges linking STARs by skills, domains, outcomes

---

### GAP-045: Tiered Job Execution ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 4 hours
**Impact**: Smart resource allocation - premium models for high-value operations, economy models for analysis

**Fix Applied** (2025-12-01):
Implemented comprehensive tiered processing system with per-operation model selection.

**Files Created/Modified**:
- `src/common/tiering.py` - New module with tier definitions and model matrix
- `src/common/state.py` - Added `processing_tier` and `tier_config` fields
- `src/workflow.py` - Accept tier_config parameter, log tier info
- `scripts/run_pipeline.py` - Added `--tier` CLI argument
- `runner_service/models.py` - Added `processing_tier` to request models
- `runner_service/executor.py` - Pass tier to subprocess
- `runner_service/app.py` - Flow tier through endpoints
- `frontend/templates/job_detail.html` - Dropdown UI for tier selection

**Tier Model Matrix**:

| Tier | Fit Score | CV Model | Role Model | Research | Pain Points | Contacts | CV | Outreach | Est. Cost |
|------|-----------|----------|------------|----------|-------------|----------|-----|----------|-----------|
| **A (Gold)** | 85-100% | Claude Sonnet 4 | GPT-4o | GPT-4o-mini | GPT-4o-mini | 5 | ✅ STAR | ✅ | $0.50 |
| **B (Silver)** | 70-84% | Claude Haiku | GPT-4o-mini | GPT-4o-mini | GPT-4o-mini | 3 | ✅ STAR | ✅ | $0.25 |
| **C (Bronze)** | 50-69% | Claude Haiku | GPT-4o-mini | GPT-4o-mini | GPT-4o-mini | 2 | ✅ | ❌ | $0.15 |
| **D (Skip)** | <50% | - | - | GPT-4o-mini | GPT-4o-mini | 0 | ❌ | ❌ | $0.05 |

**Design Philosophy**:
- High-value ops (CV stitching, role tailoring): Premium models even in lower tiers
- Analytical ops (research, pain points): Cost-effective GPT-4o-mini across all tiers
- Lower tiers skip expensive operations (contacts, outreach) for cost savings

**UI**: Process Job button now has dropdown with tier selection (Auto, Gold, Silver, Bronze, Skip)

---

### GAP-057: CV Editor Margin Presets
**Priority**: P3 LOW | **Status**: ✅ FIXED (2025-12-01) | **Effort**: 1 hour
**Impact**: Users must manually set margins; no quick presets

**Fix Applied**:
Added margin preset dropdown to CV editor Document Settings:
- **Normal** (1" all sides) - default
- **Narrow** (0.5" all sides) - for compact CVs
- **Moderate** (0.75" all sides) - balanced option
- **Wide** (1.5" all sides) - for formal documents
- **Custom** - shows individual margin controls

**Files**:
- `frontend/templates/job_detail.html` - Added preset dropdown UI
- `frontend/static/js/cv-editor.js` - Added `applyMarginPreset()` and `updateMarginPreset()` functions

**UX**: Selecting Custom shows detailed controls; changing individual margins auto-detects matching presets

---

### GAP-058: Smaller UI Buttons ✅ COMPLETE
**Priority**: P3 LOW | **Status**: COMPLETE (2025-12-01) | **Effort**: 30 minutes
**Impact**: Button sizing now follows consistent design hierarchy

**Fix Applied** (2025-12-01):
Added refined button sizing hierarchy in `frontend/templates/base.html`:

```css
.btn-xs { padding: 0.25rem 0.5rem; font-size: var(--text-xs); }  /* New */
.btn-sm { padding: 0.375rem 0.75rem; font-size: var(--text-xs); }
.btn-md { padding: 0.5rem 1rem; }
.btn-lg { padding: 0.625rem 1.25rem; font-size: var(--text-base); }
```

**Sizes**: xs (tiny) → sm (small) → md (default) → lg (large)

**Commit**: `13d940d6` - style(frontend): Refine button sizing hierarchy (GAP-058)

---

## Completed (Nov 2025)

### Core Infrastructure
- [x] All 7 pipeline layers implemented and tested (180+ unit tests)
- [x] Runner service with subprocess execution, JWT auth, artifact serving
- [x] Frontend with job browsing, process buttons, health indicators
- [x] MongoDB persistence, FireCrawl integration, rate limiting, circuit breaker pattern
- [x] Metrics collection, error alerting, budget monitoring

### CV Rich Text Editor
- [x] Phase 1-5: TipTap foundation, formatting toolbar, document styles, PDF export, page breaks
- [x] Phase 6: PDF service separation into dedicated microservice
- [x] Playwright async API conversion, PDF generation bug fixes, WYSIWYG sync fix
- [x] 270+ unit tests for CV editor

### Observability & Safety
- [x] Token budget enforcement (TokenTracker, sliding window algorithm)
- [x] Rate limiting (RateLimiter with per-minute and daily limits)
- [x] Circuit breaker pattern (3-state, pre-configured for external services)
- [x] Structured logging across all 10 pipeline nodes (LayerContext)
- [x] Metrics dashboard (token usage, rate limits, health status)
- [x] Budget monitoring UI (progress bars, thresholds, alerts)
- [x] Error alerting system (ConsoleNotifier, SlackNotifier, deduplication)

### Pipeline & Features
- [x] CV Generation V2 (Layer 1.4 JD Extractor)
- [x] Layer-level structured logging with timing metadata
- [x] ATS compliance research (keyword integration best practices)
- [x] Pipeline progress UI backend API
- [x] Config validation (Pydantic Settings)
- [x] Service health status indicator with capacity metrics
- [x] Application stats dashboard (today/week/month/total counts)

---

## Completed (Dec 2025)

### MongoDB Master CV Integration Fix
- [x] Fix CVLoader default MongoDB flag (2025-12-12): Changed CVLoader to use MongoDB master CV by default instead of falling back to local files. This ensures CV edits via the Master CV Editor are properly used in CV generation.
  - **Root Cause**: CVLoader was initialized with `use_mongodb=False`, causing the CV Editor's MongoDB changes to be ignored during generation
  - **Fix Applied**:
    - Added `USE_MASTER_CV_MONGODB` config flag in `src/common/config.py` (defaults to `true`)
    - Updated `CVLoader()` initialization in `src/layer6_v2/orchestrator.py` to use `Config.USE_MASTER_CV_MONGODB`
    - Enhanced logging in `src/layer6_v2/cv_loader.py` with clear indicators for MongoDB vs local file usage
  - **Files**: `src/common/config.py`, `src/layer6_v2/orchestrator.py`, `src/layer6_v2/cv_loader.py`
  - **Verification**: 6 roles successfully loaded from MongoDB, config flag set to `True`, 35 unit tests passing

### Job Detail Page 3-Column Responsive Dashboard Layout
- [x] Complete UI/UX overhaul (2025-12-11): Restructured job detail page from single-column narrow layout to responsive multi-column dashboard with CSS Grid.
  - **Files**: `frontend/static/css/job-detail.css` (NEW - 577 lines), `frontend/templates/job_detail.html` (RESTRUCTURED), `frontend/static/js/job-detail.js` (ENHANCED), `frontend/templates/base.html` (MODIFIED)
  - **Desktop layout (≥1280px)**: 3-column grid (left sidebar 280px + main fluid + right sidebar 320px) with sticky sidebars
  - **Tablet layout (768-1279px)**: 2-column grid (left sidebar 240px + combined main content)
  - **Mobile layout (<768px)**: Single column with reordered sections
  - **Features**: Dual header system, compact sticky header at 150px scroll threshold, CSS custom properties for theming, Alpine.js scroll behavior
  - **Testing**: All 1713 unit tests passing, HTML structure verified via Flask test client, CSS breakpoints verified programmatically

### CLI Panel & Page Refresh
- [x] Fix HTMX script redeclaration errors (2025-12-11): Changed `ui:refresh-job` handler to use full page reload instead of HTMX partial swap. CLI state preserved via sessionStorage. 2-second delay allows completion status visibility.

### Annotation System Enhancements
- [x] Delete annotation from popover (2025-12-11): Added delete button to annotation popover for editing existing annotations, with visibility controls and confirmation handling

### Master CV API Vercel Deployment Fix
- [x] Master CV API proxy pattern (2025-12-12): Fixed 500 errors on Vercel deployment by proxying Master CV endpoints to Runner Service instead of importing `src.common.master_cv_store` directly.
  - **Problem**: Frontend running on Vercel doesn't have access to `src` module; direct imports of `master_cv_store` caused 500 errors
  - **Solution**: Implemented HTTP proxy layer in `frontend/app.py` that forwards all Master CV requests to Runner Service (VPS:8000)
  - **Architecture**: Frontend (Vercel) → proxies to → Runner Service (VPS) → uses → MasterCVStore (MongoDB)
  - **Files Modified**:
    - `frontend/app.py` - Removed direct imports of `src.common.master_cv_store`, added `proxy_master_cv_to_runner()` helper function
    - Updated all 6 Master CV endpoints to use proxy pattern: `GET/PUT /api/master-cv/{metadata,roles,taxonomy}`
  - **Timeout**: 30 seconds per request; headers proxied via `get_runner_headers()`
  - **Backward Compatibility**: Runner Service continues to implement actual Master CV logic; all MongoDB operations happen on VPS
  - **Verification**: Master CV Editor UI continues to work; API calls now routed through proxy layer

### Third-Person Absent Voice Enforcement in PersonaBuilder
- [x] Third-person voice validation fix (2025-12-12): Enforced third-person absent voice (e.g., "who thrives on...") instead of first-person pronouns (e.g., "I thrive on...") in synthesized personas.
  - **Root Cause**: `SYNTHESIS_PROMPT` in `src/common/persona_builder.py` lacked explicit third-person voice constraints; LLM defaulted to first-person language
  - **Impact**: Personas were generated with "I/my" pronouns, breaking the professional third-person-absent voice required for CV profiles
  - **Fix Applied**:
    1. Updated `SYNTHESIS_PROMPT` with explicit third-person rules and negative examples (bad: "I thrive", good: "who thrives")
    2. Added `_check_third_person_voice()` validation in `src/layer6_v2/header_generator.py` for defense-in-depth
    3. Header generator validates compliance before finalizing persona injection into CV profiles
  - **Files Modified**:
    - `src/common/persona_builder.py` - Enhanced SYNTHESIS_PROMPT with voice constraints
    - `src/layer6_v2/header_generator.py` - Added third-person voice validation helper
  - **Tests Added**:
    - `tests/unit/test_persona_builder.py` - 10 tests for prompt structure and synthesis validation
    - `tests/unit/test_layer6_v2_header_generator.py` - 20 tests for voice validation logic
  - **Verification**: All new tests pass; voice validation catches first-person violations; prompt enforces third-person-absent
  - **Important Note**: Existing personas in MongoDB were synthesized before this fix. Users must re-synthesize personas to get third-person voice. New personas will be generated correctly by default.

### VP Engineering Role Category Separation
- [x] Added VP_ENGINEERING to RoleCategory enum (2025-12-12): Separated VP Engineering from CTO role to enable role-specific CV generation and persona injection.
  - **Implementation**: Updated `src/common/role_category.py` to add `VP_ENGINEERING` as distinct enum value
  - **Files Modified**: `src/common/role_category.py`
  - **Impact**: System now supports 8 distinct role categories enabling hyper-personalized CV generation per role type
  - **Verification**: RoleCategory enum extended; role references throughout codebase maintain compatibility

### Role Persona Registry Implementation
- [x] Added comprehensive persona data to role_skills_taxonomy.json (2025-12-12): Populated persona registry for all 8 role categories with identity, voice, power verbs, tagline templates, and achievement focus.
  - **Data Added** (`data/master-cv/role_skills_taxonomy.json`):
    - `identity_statement`: Role-specific professional identity (e.g., "Solutions-focused engineering leader")
    - `voice`: Writing tone and style indicators
    - `power_verbs`: High-impact action verbs specific to role category
    - `tagline_templates`: Role-specific professional taglines with placeholders
    - `metric_priorities`: Quantifiable measures most relevant to role
    - `key_achievement_focus`: Strategic impact areas for this role
    - `differentiators`: Unique value propositions per role category
  - **Roles Covered**: Principal Engineer, Staff Engineer, Engineering Manager, VP Engineering, CTO, Solutions Architect, Product Manager, Data Science Lead
  - **Files Modified**: `data/master-cv/role_skills_taxonomy.json`
  - **Impact**: CV generation now uses role-specific persona data to inject coherent identity, voice, and achievement framing into headers and profiles

### Persona-Enhanced Layer 6 Prompts
- [x] Injected role persona context into CV generation prompts (2025-12-12): Updated build_profile_user_prompt and build_persona_user_prompt to include role persona data from taxonomy.
  - **Implementation**:
    - `build_profile_user_prompt()`: Extracts persona data from job's role_category and injects identity_statement, voice, and power_verbs
    - `build_persona_user_prompt()`: Uses role-specific tagline_templates and key_achievement_focus for coherent persona synthesis
    - Persona guidance automatically populated from role_skills_taxonomy during CV generation
  - **Files Modified**: `src/layer6_v2/prompts/header_generation.py`
  - **Impact**: CV headers now reflect role-specific professional identity, making each application feel tailored to the role category rather than generic
  - **Verification**: Persona data flows from taxonomy → prompts → LLM → CV header during generation

### Job List Multi-Criteria Sorting
- [x] Implemented multi-criteria job sorting (2025-12-12): Default sort now prioritizes Gulf region locations + match score + seniority level.
  - **Implementation**: Updated job list view to sort by:
    1. Priority locations (Gulf region jobs sorted first)
    2. Match score (highest score first within location tier)
    3. Seniority level (senior roles ranked higher)
  - **Files Modified**: `frontend/templates/job_list.html`, `frontend/runner.py`
  - **Impact**: Users see most relevant opportunities (Gulf locations + high match) at top of list; dramatically improves job targeting efficiency
  - **Verification**: Job list displays Gulf-region jobs first, then sorted by match score descending, then by seniority

### Pipeline Stop/Cancel Feature
- [x] Implemented pipeline cancellation (2025-12-12): Users can now stop a running pipeline from the frontend console. All partial results are discarded when stopped.
  - **Backend Changes** (`runner_service/`):
    - Added `_processes: Dict[str, asyncio.subprocess.Process]` to track subprocess handles for immediate cancellation
    - Added `POST /jobs/{run_id}/cancel` endpoint that kills subprocess with SIGKILL
    - Updated `_execute_pipeline_task()` to register process via callback and handle "cancelled" status
    - Updated `stream_logs()` to handle "cancelled" as terminal status
    - Modified `executor.py` with `process_callback` parameter to register subprocess immediately after creation
  - **Frontend Changes** (`frontend/`):
    - Added `/jobs/<run_id>/cancel` proxy route in `runner.py`
    - Added red "Stop" button in pipeline progress card header (partial `_pipeline_progress.html`)
    - Added JavaScript functions: `cancelPipeline()`, `showPipelineStopButton()`, `hidePipelineStopButton()` in `base.html`
    - Updated `monitorPipeline()` to show stop button when pipeline starts
    - Added `handlePipelineCancelled()` for UI state updates when cancelled
    - Updated SSE 'end' event handler and status polling to handle "cancelled" status
  - **Behavior**:
    - Stop button appears only while pipeline is running
    - Clicking stop kills subprocess immediately (SIGKILL)
    - No MongoDB updates occur; all partial results discarded
    - Job status changes to "cancelled" in UI
    - Logs show cancellation point
  - **Files Modified**:
    - Backend: `runner_service/app.py`, `runner_service/executor.py`
    - Frontend: `frontend/runner.py`, `frontend/templates/partials/job_detail/_pipeline_progress.html`, `frontend/templates/base.html`, `frontend/static/js/job-detail.js`
  - **Impact**: Users have full control over long-running pipelines; can immediately halt operations that are stuck or unnecessary

### Complete MongoDB Migration for Master CV System
- [x] MongoDB-first architecture implementation (2025-12-12): Completed full migration to use MongoDB as primary source for Master CV data across all code paths.
  - **Scope**: Unified all CV loading, CV generation, and CV service endpoints to use MongoDB with file fallback
  - **Changes Completed**:
    1. **Quick Scorer Service** (`src/services/quick_scorer.py`):
       - Now uses `MasterCVStore.get_profile_for_suggestions()` instead of reading `master-cv.md` directly
       - Profile data sourced from MongoDB `master_cv_metadata` collection
    2. **Pipeline Runner** (`scripts/run_pipeline.py`):
       - Now uses `CVLoader(use_mongodb=True)` for all CV loading operations
       - All role data sourced from MongoDB `master_cv_roles` collection
    3. **Orchestrator** (`src/layer6_v2/orchestrator.py`):
       - `_get_master_cv_text()` method now uses `self.cv_loader` instead of file I/O
       - Consistent MongoDB-first loading across all pipeline layers
    4. **Configuration Validation** (`src/common/config.py`):
       - `USE_MASTER_CV_MONGODB` flag defaults to `true`
       - File validation skipped when MongoDB flag enabled
       - Backward-compatible with local files when MongoDB unavailable
    5. **Test Fixtures** (`tests/ab_testing/conftest.py`, `scripts/run_integration_ab_tests.py`):
       - Updated all CV loading to use MongoDB-first pattern
       - Mock MongoDB collections for deterministic test behavior
    6. **Docker Compose** (all 4 files):
       - Removed `master-cv.md` volume mounts (no longer needed)
       - Simplified deployment configuration
    7. **CI/CD Pipeline** (`.github/workflows/runner-ci.yml`):
       - Removed `master-cv.md` from deployment to VPS
       - Reduced artifact size; all CV data persisted in MongoDB
    8. **Legacy File Removal**:
       - Deleted `master-cv.md` from project root (no longer used)
       - Data fully migrated to MongoDB collections
  - **Architecture**:
    - **MongoDB Primary Source**: All CV data stored in 3 collections:
      - `master_cv_metadata`: Candidate personal info, summary, languages, certifications
      - `master_cv_roles`: Work experience, achievements, keywords per role
      - `master_cv_taxonomy`: Skill categories and skill definitions
    - **CVLoader**: Encapsulates MongoDB vs file logic; transparent to consumers
    - **File Fallback**: If MongoDB unavailable, `data/master-cv/roles/*.md` files still used
    - **Frontend Integration**: Master CV Editor (Vercel) → proxies through Runner Service (VPS) → accesses MongoDB
  - **Data Flow**:
    ```
    CV Editor UI (Vercel)
         ↓ (auto-save, 3s debounce)
    Frontend API proxy layer
         ↓ (HTTP proxy)
    Runner Service (VPS:8000)
         ↓ (direct connection)
    MongoDB (master_cv_* collections)
         ↓ (on-demand loading)
    CV Generation Pipeline
         ↓ (all CV text injected into CVs)
    Output: Role-tailored CVs with MongoDB data
    ```
  - **Benefits**:
    1. **Single Source of Truth**: CV data lives in MongoDB, not scattered across files
    2. **Real-Time Edits**: CV Editor changes immediately available to all pipeline code paths
    3. **Simplified Deployment**: No file synchronization needed; VPS only needs MongoDB URI
    4. **Scalable**: Easy to add CV variants, versioning, or historical tracking
    5. **Audit Trail**: All CV edits tracked in MongoDB for compliance
  - **Files Modified**:
    - `src/services/quick_scorer.py` - Uses MasterCVStore instead of file reading
    - `scripts/run_pipeline.py` - Uses CVLoader(use_mongodb=True)
    - `src/layer6_v2/orchestrator.py` - Uses self.cv_loader for all CV access
    - `src/common/config.py` - USE_MASTER_CV_MONGODB flag and validation
    - `tests/ab_testing/conftest.py`, `scripts/run_integration_ab_tests.py` - MongoDB fixtures
    - `docker-compose.*.yml` (4 files) - Removed master-cv.md mounts
    - `.github/workflows/runner-ci.yml` - Removed master-cv.md from deployment
    - **Deleted**: `master-cv.md` (no longer needed)
  - **Backward Compatibility**:
    - All code paths default to MongoDB (`USE_MASTER_CV_MONGODB=true`)
    - Automatic fallback to `data/master-cv/roles/*.md` if MongoDB unavailable
    - No breaking changes to API contracts; CVLoader transparent interface
  - **Verification**: All unit tests passing; 6 roles successfully loaded from MongoDB; file fallback tested

### Keyword Front-Loading for ATS Optimization
- [x] Implemented keyword front-loading for CV bullet generation (2025-12-12): CV bullets now position JD keywords in the first 3 words to enable recruiters' 6-7 second initial CV scan to instantly match experience to requirements.
  - **Feature**: Generation prompts instruct LLM to place JD keywords naturally in opening of bullets (e.g., "Architected Kubernetes migration..." instead of "Led migration to Kubernetes...")
  - **Grading Enhancement**: Added `_check_keyword_front_loading()` method in `src/layer6_v2/grader.py` that:
    - Extracts bullets from CV using regex pattern for markers (•, -, *)
    - Identifies JD keywords appearing anywhere in each bullet
    - Checks if keyword appears within first 3 words of bullet text
    - Calculates front-loading ratio: (front_loaded_count / keyword_addressable_count)
  - **ATS Scoring Integration**:
    - 0.5 point bonus added to ATS dimension score when front-loading ratio >= 50%
    - Feedback includes front-loading metrics: "5/8 front-loaded (62%)"
    - Issues flagged when addressable keywords have low front-loading ratio
  - **Generation Prompts Updated**:
    - `src/layer6_v2/prompts/role_generation.py`: Added KEYWORD FRONT-LOADING section (21 lines) with guidelines and examples
    - `src/layer6_v2/prompts/header_generation.py`: Enhanced KEY ACHIEVEMENTS section with front-loading guidance
  - **Unit Tests Added**: 8 new tests covering all edge cases:
    - `test_detects_front_loaded_keywords()` - All keywords in first 3 words (100% ratio)
    - `test_detects_buried_keywords()` - All keywords buried later in bullets (0% ratio)
    - `test_mixed_front_loading()` - Mix of front-loaded and buried (67% ratio)
    - `test_empty_keywords()` - No keywords to check (perfect score)
    - `test_no_keyword_matches()` - Bullets with no keyword matches
    - `test_case_insensitive()` - Keyword matching ignores case
    - `test_short_bullets()` - Handles bullets with <3 words
    - `test_integration_with_ats_scoring()` - Front-loading integrated into ATS dimension
  - **Example Transformation**:
    - Before: "Created clean architecture by devolving monolith to microservices"
    - After: "Architected microservices migration from monolith, reducing deployment time 75%"
  - **Files Modified**:
    - `src/layer6_v2/grader.py` - Added `_check_keyword_front_loading()` method + ATS scoring bonus
    - `src/layer6_v2/prompts/role_generation.py` - Added keyword front-loading guidance (lines 94-122)
    - `src/layer6_v2/prompts/header_generation.py` - Enhanced KEY ACHIEVEMENTS section
    - `tests/unit/test_layer6_v2_grader_improver.py` - Added 8 new test methods
  - **Impact**: CVs now optimized for recruiter scanning patterns; front-loaded keywords increase likelihood of passing keyword screening filters and improve initial impression during rapid review
  - **Verification**: All 8 new tests passing; front-loading ratio calculation correct; ATS bonus applied conditionally; feedback includes metrics

### Time-Based Filters Bug & Datetime Parameter Persistence Fix
- [x] Time-based filter persistence and cache-busting (2025-12-12): Fixed datetime filter parameters not persisting through pagination and sorting, and added cache-busting headers to prevent stale responses.
  - **Root Cause**: Parameter name mismatch - template was looking for `date_from`/`date_to` but filter params were `datetime_from`/`datetime_to`; additionally, browser cache was causing stale HTML to be served
  - **Impact**: Time-based quick filters (1h, 3h, 6h, 12h) now correctly preserve selected time range through pagination, sorting, and job list interactions; cache-busting headers (Cache-Control, ETag) prevent serving stale HTML
  - **Fix Applied**:
    1. Updated `job_rows_partial()` in `frontend/app.py` to properly pass `datetime_from` and `datetime_to` parameters to template
    2. Fixed `job_rows.html` template to use correct `datetime_from`/`datetime_to` parameter names in filter_params dict
    3. Added `@app.after_request` handler in `frontend/app.py` for cache-busting: sets Cache-Control, Pragma, and ETag headers
    4. Verified parameter flow: JavaScript creates hidden inputs → HTMX sends params → Flask receives → template constructs query → results returned fresh
  - **Files Modified**:
    - `frontend/app.py` - Fixed param passing in `job_rows_partial()`, added `@app.after_request` handler for cache-busting (lines 152-160, 285-305)
    - `frontend/templates/partials/job_rows.html` - Fixed filter_params to use `datetime_from`/`datetime_to` (line 48)
  - **Tests Added**: 22 new comprehensive tests in `frontend/tests/test_datetime_filter_persistence.py`:
    - Parameter persistence through pagination (8 tests)
    - Parameter persistence through sorting (8 tests)
    - Cache-busting header validation (6 tests)
    - All tests pass with full coverage of edge cases
  - **Verification**: All 22 tests passing; manual testing confirms time-based filters persist through pagination/sorting; ETag headers returned with 304 Not Modified responses
  - **Related Documentation**: `plans/time-filter-bug-fix-and-enhancement.md`, `reports/sessions/2025-11-30-time-filter-bug-investigation.md`

### Applied Only Filter Toggle
- [x] Added applied filter toggle (2025-12-12): Users can now filter job list to show only applied jobs (those with CV and outreach data).
  - **Implementation**:
    - Added `show_applied_only` boolean filter input (default: unchecked)
    - Updated MongoDB query to exclude jobs without cv_text and outreach_body when toggle is enabled
    - Added visual toggle button with "Applied Only" label in filter panel
  - **Files Modified**:
    - `frontend/templates/index.html` - Added checkbox filter input for "Applied Only"
    - `frontend/app.py` - Updated query construction to filter based on toggle state
  - **UX**: Toggle appears next to existing date filters; improves ability to see application progress at a glance
  - **Verification**: Filter works correctly; applied jobs properly filtered; no regression on other filters

---

## Quick Reference

### Priority Definitions

| Priority | Definition | SLA |
|----------|------------|-----|
| **P0** | System broken, data integrity at risk, production down | Fix immediately |
| **P1** | User-facing bugs, important features broken | Fix this week |
| **P2** | Enhancements, incomplete features, tech debt | Fix this sprint |
| **P3** | Nice-to-have, backlog items | When time permits |

### Key Files

| File | Purpose |
|------|---------|
| `plans/missing.md` | This file - all gaps tracked |
| `plans/architecture.md` | System architecture |
| `bugs.md` | Bug-specific tracking |
| `plans/next-steps.md` | Immediate action items |

### Agent Reports

- `reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`
- `reports/debugging/2025-11-30-cv-hallucination-root-cause-analysis.md`
- `reports/agents/doc-sync/2025-11-30-vps-backup-assessment.md`
