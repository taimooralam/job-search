# Implementation Gaps

**Last Updated**: 2025-11-30 (CV Gen V2 - Phase 6 Grader + Improver Complete; V2 Enhancements: Languages, Certifications, Locations, Skills)

> **See also**:
>
> - `plans/architecture.md` - System architecture
> - `plans/next-steps.md` - Immediate action items

---

## Completed (Nov 2025)

- [x] All 7 pipeline layers implemented and working
- [x] Runner service with real pipeline execution
- [x] JWT authentication and CORS
- [x] MongoDB persistence for run status
- [x] Artifact serving with security validation
- [x] Frontend UI with process buttons, health indicators, time filters
- [x] CI/CD for runner and frontend
- [x] FireCrawl contact discovery (Option A - SEO queries)
- [x] Synthetic contact fallback (4 primary + 4 secondary)
- [x] Frontend-runner integration (runner.py proxy + job_detail.html)
- [x] CV Rich Text Editor Phase 1 ✅ **COMPLETED 2025-11-26** (46 unit tests, TipTap foundation, side panel UI)
- [x] CV Rich Text Editor Phase 2 - Code Implementation ✅ **COMPLETED 2025-11-27** (60+ fonts, formatting toolbar, 38 unit tests passing; 2 UX issues identified)
- [x] LinkedIn Outreach with Signature ✅ **COMPLETED 2025-11-27** (Character limits documented, signature requirement specified)
- [x] Agent Documentation Organization ✅ **COMPLETED 2025-11-27** (plans/agents/ and reports/agents/ structure established)
- [x] CV Rich Text Editor Phase 3 ✅ **COMPLETED 2025-11-27** (28 unit tests passing; document-level styles working)
- [x] CV Rich Text Editor Phase 4 ✅ **COMPLETED 2025-11-27** (22 unit tests passing; PDF export via Playwright)
- [x] CV Rich Text Editor Phase 4 - Migration to Runner Service ✅ **COMPLETED 2025-11-27** (Moved PDF generation from frontend to runner service)
- [x] PDF Export Recursion Fix ✅ **COMPLETED 2025-11-28** (Iterative stack-based approach eliminates recursion limit)
- [x] PDF Margins WYSIWYG via CSS @page ✅ **COMPLETED 2025-11-28** (Changed from parameter-based to CSS-based margin rendering)
- [x] Playwright Async API Conversion ✅ **COMPLETED 2025-11-28** (Converted to async API for FastAPI compatibility)
- [x] MongoDB URI Standardization ✅ **COMPLETED 2025-11-28** (Changed MONGO_URI to MONGODB_URI for consistency)
- [x] Export PDF Button Fix (Detail Page) ✅ **FIXED & VERIFIED 2025-11-30** (Enhanced error handling, logging, and user feedback via toast notifications)
- [x] CV Rich Text Editor Phase 5.1 - Page Break Visualization ✅ **COMPLETED 2025-11-28** (32 unit tests passing; visual indicators for page breaks in editor and detail page; commit c81c1ff4)
- [x] Phase 6: PDF Service Separation ✅ **COMPLETED 2025-11-28** (56 unit tests passing; separated PDF generation into dedicated microservice with Playwright/Chromium; runner proxies to PDF service; ready for deployment)
- [x] PDF Generation Bug Fixes (2025-11-28)
  - [x] Fixed "Nonein" Parse Error: Defense-in-depth margin validation across 3 layers
  - [x] Fixed Blank PDF from Pipeline: Markdown-to-TipTap migration in runner service
  - [x] All margin validation tested with 48 PDF service tests
- [x] Process Button Bug Fix ✅ **COMPLETED 2025-11-28** (Added missing showToast function, improved error handling in processJobDetail(); 22 unit tests passing)
- [x] CV WYSIWYG Sync Bug Fix ✅ **COMPLETED 2025-11-28** (Replaced markdown rendering with TipTap JSON rendering; added renderCVPreview() and tiptapJsonToHtml() functions; 34 unit tests passing)
- [x] PDF Service Availability Issue Fix ✅ **COMPLETED 2025-11-28** (Root cause: Old docker-compose.runner.yml on VPS + CI/CD not copying compose file. Fixed by: 1) Updated CI/CD to copy docker-compose.runner.yml to VPS, 2) Added Playwright startup validation in pdf_service/app.py, 3) Increased Playwright wait time from 10s to 20s. Result: 58 tests passing [49 PDF service + 9 runner integration]. See plans/pdf-service-debug-plan.md)
- [x] CV Generation V2 - Layer 1.4: JD Extractor ✅ **COMPLETED 2025-11-30** (33 unit tests passing; structured JD extraction for role-category-aware CV tailoring. See plans/cv-generation-v2-architecture.md)
- [x] CV Gen V2 Enhancements ✅ **COMPLETED 2025-11-30** (Languages, Certifications, Locations, Skills expanded to 4 categories; all 161 tests passing; JD keyword integration 79% coverage)
- [x] Frontend Job Detail Enhancements ✅ **COMPLETED 2025-11-30** (Extracted JD display section, collapsible job description, iframe viewer Phase 1, improved PDF error handling)
- [x] Layer-level Structured Logging ✅ **COMPLETED 2025-11-30** (Commit ed5aadf1; Added LayerContext to all 10 pipeline nodes; layer_start/layer_complete events with timing and metadata)
- [x] ATS Compliance Research ✅ **COMPLETED 2025-11-30** (Commit ca8e8f81; Research report in reports/ats-compliance-research.md; keyword stuffing analysis and best practice recommendations)

---

## Current Blockers

| Issue                 | Impact              | Fix                                      |
| --------------------- | ------------------- | ---------------------------------------- |
| Anthropic credits low | CV generation fails | Add credits or use `USE_ANTHROPIC=false` |

---

## Documentation Organization (2025-11-27)

**Status**: COMPLETE

All agent-specific documentation has been organized into:

- `plans/agents/{agent-name}/` - Implementation plans, testing guides, strategies
- `reports/agents/{agent-name}/` - Reports, summaries, analysis results

**Files Moved to Proper Locations**:

- `reports/agents/doc-sync/` - Documentation sync reports
- `reports/agents/frontend-developer/` - Frontend implementation reports
- `reports/agents/architecture-debugger/` - Deployment and DNS fix reports
- `reports/agents/pipeline-analyst/` - Analysis and context reports
- `plans/agents/doc-sync/` - Documentation planning documents

**Guidelines**: See `plans/agents/README.md` for comprehensive agent documentation structure and protocols.

---

## Remaining Gaps (Non-Blocking)

### Testing

- [x] CV generator tests need mocking to avoid real API calls ✅ **COMPLETED 2025-11-26**
  - Added `mock_llm_providers` fixture mocking ChatAnthropic and ChatOpenAI
  - All 220 unit tests pass without real API calls (188 Phase 1-4 + 32 Phase 5.1)
  - Added 30+ new tests for CV editing API and HTML CV generator
- [ ] Integration tests not in GitHub Actions CI
- [ ] No coverage tracking
- [ ] E2E Tests Disabled (2025-11-28)
  - **Status**: 48 comprehensive Playwright tests exist in `tests/e2e/` but workflow disabled
  - **Location**: `.github/workflows/e2e-tests.yml.disabled`
  - **Reason for Disabling**: Configuration issues, tests written for Phase 5 features (mobile, accessibility) that are only partially implemented
  - **What Exists**:
    - 48 Playwright tests in `tests/e2e/test_cv_editor_e2e.py` covering Phases 1-5
    - Comprehensive `conftest.py` with browser configuration, fixtures, markers
    - Tests for: editor loading, formatting, fonts, alignment, document styles, PDF export, keyboard shortcuts, mobile, accessibility
  - **What's Needed to Re-enable**:
    - Fix `conftest.py` configuration (attempted previously, needs review)
    - Ensure Phase 5 features fully implemented in both backend and frontend
    - Set up proper test data/fixtures with valid MongoDB job records
    - Configure CI environment with valid `LOGIN_PASSWORD` and database access
    - Implement smoke test suite for working features (Phases 1-4 only)
  - **Recommended Approach**: See `plans/e2e-testing-implementation.md` for detailed re-enablement plan

### Observability

- [x] All layers use structured `LayerContext` logging ✅ **COMPLETED 2025-11-30** (Commit ed5aadf1)
  - Replaced `print()` with LayerContext in all 10 pipeline nodes
  - Each node emits `layer_start` and `layer_complete` events with timing and metadata
  - Fields: `layer_id`, `layer_name`, `node_name`, `status`, `duration_ms`, `timestamp`
  - Structured JSON format ready for log aggregation and monitoring
  - Files: All `src/layer*.py` files updated with LayerContext integration
- [ ] No metrics, alerts, or cost tracking
- [ ] Config validation only in CLI, not runner

### Data Completeness

- [ ] `JobState` missing: `tier`, `dossier_path`, `cv_text`, `application_form_fields`
- [ ] `pipeline_runs` collection unused
- [ ] Outreach packages not persisted to MongoDB

### Features (Backlog)

- [ ] Rate limiting for FireCrawl/LLM calls
- [x] LinkedIn outreach character limit requirements documented ✅ **COMPLETED 2025-11-27**
  - Connection request: 300 char limit specified
  - InMail: 1900 char body limit specified
  - Mandatory signature: "Best. Taimoor Alam"
  - Full implementation guide: plans/layer6-linkedin-outreach.md
- [ ] Layer 1.5: Application form mining not implemented
- [ ] .docx CV export not implemented
- [ ] STAR selector: No embeddings, caching, or graph edges

### Newly Identified Gaps (2025-11-28) - UPDATED 2025-11-30

- [x] Observability still minimal: ✅ **RESOLVED 2025-11-30** (Commit ed5aadf1)
  - Replaced `print()` with structured LayerContext logging across all 10 pipeline nodes
  - All layers now emit `layer_start` and `layer_complete` events with timing and metadata
- Planning docs stale: `plans/next-steps.md` still lists Phase 2 WYSIWYG issues as blockers; `reports/PROGRESS.md` frozen at Nov 16 with only Layers 2–3 done, conflicting with current repo state.
- [x] LLM retry policy inconsistent: ✅ **RESOLVED 2025-11-29** (Commit bde545b3)
  - Added tenacity backoff wrappers to all LLM calls in cover_letter_generator and generator
  - All LLM calls now use exponential backoff with proper retry logic

### Critical Issues (2025-11-28)

#### Infrastructure Task: PDF Service Separation (Phase 6) ✅ COMPLETE

**Status**: COMPLETE and TESTED (2025-11-28)
**Implementation Date**: 2025-11-28
**Actual Duration**: ~6 hours
**Test Coverage**: 56 unit tests (100% passing, 0.33s execution)
**Plan Document**: `plans/phase6-pdf-service-separation.md`

**Objective**: Separate PDF generation from runner service into dedicated Docker container for better separation of concerns and independent scaling.

**Delivered Solution**:
- ✅ New `pdf-service` Docker container with Playwright + Chromium
- ✅ API endpoints implemented:
  - POST `/health` - Health check with capacity monitoring
  - POST `/render-pdf` - Generic HTML/CSS → PDF conversion
  - POST `/cv-to-pdf` - TipTap JSON → PDF (current use case)
  - POST `/cover-letter-to-pdf` - Ready for implementation (Phase 6 feature)
  - POST `/dossier-to-pdf` - Ready for implementation (Phase 7 feature)
- ✅ Runner proxies PDF requests to PDF service via internal Docker network
- ✅ Frontend unchanged (still calls runner, runner calls PDF service)
- ✅ All error handling implemented (400/500/503 codes, timeout handling)
- ✅ Concurrency limiting (max 5 concurrent PDF operations)

**Implementation Completed**:
1. ✅ PDF service container created (Dockerfile.pdf-service)
2. ✅ PDF endpoints implemented with comprehensive error handling
3. ✅ Runner integration updated (HTTP client replaces local Playwright)
4. ✅ Docker Compose configuration updated for both services
5. ✅ Comprehensive test suite (56 tests: 48 PDF service + 8 integration)

**Benefits Achieved**:
- ✅ Clear separation of concerns (pipeline ≠ PDF generation)
- ✅ Independent scaling possible (services on separate containers)
- ✅ Better resource management (Chromium isolated)
- ✅ Easier to add new document types (architecture in place)
- ✅ PDF service can restart without affecting pipeline
- ✅ Internal-only exposure (no external port on PDF service)

**Architecture Changes**:
- **Before**: Runner service handled both pipeline execution and PDF generation
- **After**: Runner (port 8000) + PDF Service (port 8001, internal only) on shared Docker network

**Files Created**:
- `pdf_service/__init__.py`
- `pdf_service/app.py` (327 lines - FastAPI endpoints)
- `pdf_service/pdf_helpers.py` (369 lines - moved from runner)
- `Dockerfile.pdf-service` (48 lines)
- `tests/pdf_service/test_endpoints.py` (315 lines, 17 tests)
- `tests/pdf_service/test_pdf_helpers.py` (403 lines, 31 tests)
- `tests/runner/test_pdf_integration.py` (331 lines, 8 tests)
- `conftest.py` (root pytest config)
- `setup.py` (editable install config)

**Files Modified**:
- `docker-compose.runner.yml` - Added PDF service configuration
- `runner_service/app.py` - Replaced local Playwright with HTTP client
- `pytest.ini` - Added pythonpath config

**Test Coverage**:
- PDF service health check: 3 tests
- /render-pdf endpoint: 5 tests
- /cv-to-pdf endpoint: 7 tests
- Concurrency limits: 2 tests
- PDF helpers (TipTap conversion, HTML templates): 31 tests
- Runner integration (proxy, error handling): 8 tests
- **Total**: 56 tests, 100% passing

**Next Steps**:
- [ ] Deploy to VPS: Build images and start both services
- [ ] End-to-end testing from frontend
- [ ] Add cover letter PDF endpoint (future feature)
- [ ] Add dossier PDF endpoint (future feature)

### Frontend & UI Enhancements

#### Runner Terminal Copy Button (NEW - PENDING)

**Status**: Not started
**Priority**: Medium (UX enhancement)
**Estimated Duration**: 1-2 hours

**Description**:
Add a copy button to the runner terminal interface visible on the front-end that copies all displayed logs to the clipboard. Users need the ability to easily capture and share pipeline execution logs.

**Requirements**:
- Copy button visible and easily accessible in the runner terminal interface
- Button copies all terminal logs/output to clipboard on click
- Visual feedback when copy is successful (toast notification or button state change)
- Include timestamp or metadata in copied content (optional)
- Should work with logs from all pipeline layers
- Graceful fallback if clipboard API unavailable

**Technical Approach**:
- Add copy button next to or within the terminal output area
- Use Clipboard API (`navigator.clipboard.writeText()`)
- Capture all text content from terminal output container
- Show success toast notification on successful copy
- Handle large log output gracefully

**UI Location**: Runner terminal output panel, near the top or bottom of the log display area

**Files to Modify**:
- `frontend/templates/job_detail.html` - Add copy button HTML and styling
- `frontend/static/js/runner-terminal.js` (or cv-editor.js if using same location) - Add copy logic
- Possibly: Add/update toast notification styling in base.html

**Dependencies**:
- Clipboard API (modern browsers)
- Existing runner terminal implementation
- Toast notification system (likely already exists)

**Related**:
- Frontend-runner integration (already complete)
- Runner log streaming to frontend

#### Pipeline Progress Indicator (PENDING)

**Status**: Not started
**Priority**: Medium (UX enhancement)
**Estimated Duration**: 2-3 hours

**Description**:
Visual progress indicator for the 7-layer LangGraph pipeline execution displayed on the job detail page. Shows real-time status as each layer executes with visual indicators for success/failure states.

**Requirements**:
- Display pipeline progress bar showing all 7 layers:
  1. Layer 1: Job Intake & Validation
  2. Layer 2: Pain Point Mining
  3. Layer 2.5: STAR Story Selection
  4. Layer 3: Company & Role Research
  5. Layer 4: Fit Scoring & Analysis
  6. Layer 5: Strategic Positioning
  7. Layer 6: Outreach & CV Generation
- Real-time status updates as pipeline executes
- Visual indicators:
  - Pending/queued (gray)
  - Currently executing (blue/animated)
  - Completed successfully (green checkmark)
  - Failed with error (red X)
- Show error messages inline when layer fails
- Display alongside existing terminal output from runner
- Responsive design for mobile/tablet

**Technical Approach**:
- WebSocket or Server-Sent Events (SSE) for real-time updates
- Runner service emits layer status events
- Frontend subscribes to status updates
- CSS animations for smooth transitions
- Fallback to polling if WebSocket unavailable

**UI Location**: Job detail page, below "Run Pipeline" button (above terminal output)

**Dependencies**:
- Runner service must emit layer-level status events
- Frontend WebSocket/SSE connection to runner
- State management for pipeline progress (extend JobState or new field)

**Design Reference**: Similar to GitHub Actions progress indicator or CI/CD pipeline visualizations

**Related**:
- Frontend-runner integration (already complete)
- Pipeline execution tracking in MongoDB
- Runner service status event emission

#### UI/UX Design Refresh & Modern Styling (PENDING)

**Status**: Not started
**Priority**: High (User experience and product appeal)
**Estimated Duration**: 8-12 hours

**Description**:
Comprehensive design refresh to modernize the UI/UX with sleek, elegant, production-quality styling that makes the job application process delightful. Transform the application into a visually appealing, modern interface with intuitive navigation and consistent design system.

**Goals**:
- Elevate visual appeal and perceived product quality
- Create intuitive, user-friendly navigation and interactions
- Establish consistent design system across all pages
- Improve visual hierarchy, readability, and spacing
- Enhance user delight through animations and micro-interactions

**Design Principles**:
- **Modern**: Clean lines, appropriate whitespace, contemporary design patterns
- **Intuitive**: Self-evident interactions, clear call-to-actions, logical workflows
- **Sleek**: Minimal visual clutter, focused layouts, purposeful animations
- **Elegant**: Sophisticated color palette, refined typography, balanced composition
- **Production-Ready**: Polished, bug-free, consistent across browsers/devices
- **Delightful**: Smooth transitions, micro-interactions, satisfying feedback

**Scope**:

1. **Design System Foundation**:
   - Color palette: Primary, secondary, accent, neutral scales with semantic usage
   - Typography: Font families, sizes, weights, line heights for hierarchy
   - Spacing system: Consistent margins, padding, gaps (8px-based scale recommended)
   - Component library: Reusable buttons, cards, forms, modals, navigation
   - Icons: Consistent icon set (Heroicons, Lucide, or custom SVGs)
   - Shadows and depth: Subtle elevation for layering

2. **Page-Level Improvements**:
   - Job list/dashboard: Card-based layout with filters, search, sorting
   - Job detail page: Clear information architecture, visual hierarchy, section grouping
   - CV editor: Modern toolbar design, clean panel layout, visual feedback
   - Authentication pages: Welcoming, professional, on-brand
   - Settings/profile: Organized layout, easy navigation, clear sections

3. **Interactive Elements & Feedback**:
   - Button states: Hover, active, disabled, loading with visual feedback
   - Form inputs: Clear labels, validation feedback, helpful error states
   - Loading states: Skeleton screens, progress indicators, spinners
   - Animations: Page transitions, component entrances, smooth interactions
   - Micro-interactions: Button clicks, tooltips, notifications, hover effects

4. **Responsive & Accessible Design**:
   - Mobile-first responsive approach (320px, 640px, 1024px, 1280px breakpoints)
   - Tablet optimization with appropriate spacing and touch targets
   - Desktop layouts with proper use of horizontal space
   - Touch-friendly button and input targets (min 44x44px)
   - WCAG 2.1 AA compliance:
     - Color contrast ratios (4.5:1 for text)
     - Keyboard navigation fully supported
     - Screen reader compatibility
     - Focus indicators visible

5. **Technical Implementation**:
   - Tailwind CSS utility classes (extend existing, refine configuration)
   - CSS custom properties (variables) for theming and customization
   - Component-based styling patterns
   - Dark mode support structure (Phase 2 enhancement)
   - Performance-optimized CSS without unnecessary bloat

**Design Inspiration References**:
- Linear (linear.app) - Clean, minimal SaaS design
- Notion (notion.so) - Elegant content creation interface
- Stripe Dashboard - Professional, polished SaaS UI
- Vercel Dashboard - Modern developer experience
- Figma (figma.com) - Sophisticated collaboration UI

**Implementation Breakdown**:

1. **Phase A: Design System** (2-3 hours)
   - Define color palette with semantic meaning
   - Typography scale and usage guidelines
   - Spacing and sizing system
   - Component designs

2. **Phase B: Component Library** (2-3 hours)
   - Reusable button component patterns
   - Card component with variants
   - Form input components with states
   - Navigation components

3. **Phase C: Page Refactoring** (2-3 hours)
   - Job list/dashboard redesign
   - Job detail page layout improvements
   - CV editor UI refinement
   - Authentication flow design

4. **Phase D: Polish & Testing** (1-2 hours)
   - Cross-browser testing
   - Mobile device testing
   - Accessibility audit
   - Performance optimization

**Deliverables**:
- Updated Tailwind configuration with new design tokens
- Refactored base.html and all page templates
- CSS style guide with usage examples
- Component library documentation
- Design system specification document

**Dependencies**:
- Tailwind CSS (already installed - v3.x)
- Optional: Headless UI for accessible components
- Optional: Framer Motion for advanced animations
- Design tool reference (Figma file or design specs)

**Related Components**:
- CV Rich Text Editor (styled, needs integration with design system)
- Pipeline Progress Indicator (visual consistency)
- All frontend templates and pages

**Testing & Validation**:
- Visual regression testing across pages
- Cross-browser testing (Chrome, Firefox, Safari, Edge)
- Mobile device testing (iOS Safari, Chrome Mobile)
- Accessibility audit (axe DevTools, WAVE, manual review)
- User feedback on new design before finalization

**Priority Justification**:
High priority because:
- User experience directly impacts engagement and retention
- Professional appearance increases confidence in the application
- Consistent design system enables faster future development
- Competitive differentiation in crowded job application space
- Improved usability reduces support burden

**Success Criteria**:
- Design system fully implemented in Tailwind config
- All pages consistently styled per design system
- Mobile responsive and touch-friendly
- WCAG 2.1 AA accessibility compliance verified
- Cross-browser testing passing (Chrome, Firefox, Safari, Edge)
- User feedback positive on visual appeal and usability

### CV Rich Text Editor (Phase 1 COMPLETE - 2025-11-26)

#### Phase 1: TipTap Foundation + Side Panel UI ✅ COMPLETE

**Status**: Implemented and fully tested
**Completion Date**: 2025-11-26
**Test Coverage**: 46 unit tests (100% passing, 0.73s execution time)

**Delivered Features**:

- TipTap editor with StarterKit extensions (bold, italic, underline, headings)
- Bullet lists (• List button) - unordered list formatting
- Numbered lists (1. List button) - ordered list formatting
- Side panel UI with slide-in animation and responsive design
- MongoDB persistence via `cv_editor_state` field
- GET/PUT API endpoints: `/api/jobs/<job_id>/cv-editor`
- Auto-save with 3-second debounce
- Markdown-to-TipTap migration for backward compatibility
- Editor state restoration from MongoDB
- Visual save indicator with timestamp

**Files Modified/Created**:

- `frontend/templates/base.html` - TipTap CDN scripts + Google Fonts integration
- `frontend/static/js/cv-editor.js` - NEW (450+ lines)
- `frontend/templates/job_detail.html` - Side panel UI integration
- `frontend/app.py` - GET/PUT API endpoints for editor state
- `tests/frontend/test_cv_editor_api.py` - NEW (18 tests for API endpoints)
- `tests/frontend/test_cv_migration.py` - NEW (17 tests for markdown migration)
- `tests/frontend/test_cv_editor_db.py` - NEW (11 tests for MongoDB persistence)

**Key Accomplishments**:

- All editor state changes auto-save after 3-second debounce
- Migration from legacy markdown CV format is automatic
- API endpoints validated with comprehensive unit tests
- No hallucinations or missing features - fully grounded in TipTap/ProseMirror
- Side panel collapse/expand functional and responsive
- Bullet and numbered lists confirmed working (tested 2025-11-26)

**User Feedback (Manual Testing - 2025-11-26)**:

- Confirmed bullet points (• List) and numbered lists (1. List) are present and functional
- User initially thought lists were missing, but discovered they work correctly
- User feedback on button labels: "List 1 and 2" reference suggests labels could be clearer
- No functional bug - this was user discovery of existing features

#### Phase 2: Enhanced Text Formatting ✅ COMPLETE + TESTED (2025-11-27)

**Status**: Code fully implemented, unit tested (38 tests passing), and all blocking issues RESOLVED
**Implementation Date**: 2025-11-27
**Code Status**: Complete with all UX issues fixed
**Last Updated**: 2025-11-27
**Analysis Date**: 2025-11-27 (comprehensive codebase review confirms issues resolved)

**Delivered Features**:

- 60+ professional Google Fonts organized by category (Serif, Sans-Serif, Monospace, Display, Condensed, Rounded)
- Font size selector (8-24pt) with custom TipTap extension
- Text alignment controls (left/center/right/justify) with active state highlighting
- Indentation controls with Tab/Shift+Tab keyboard shortcuts and toolbar buttons
- Highlight color picker with remove button
- Reorganized toolbar with 7 logical groups (Font, Text Format, Alignment, Indentation, Lists, Highlighting, Tools)
- 60+ Google Fonts (test coverage: 38 tests, all passing)

**Files Modified/Created**:

- `frontend/templates/base.html` (lines 17-106) - ESM import maps, 60+ Google Fonts, TipTap Highlight extension
- `frontend/templates/base.html` (lines 284-461) - Comprehensive `.ProseMirror` CSS styles for WYSIWYG rendering
- `frontend/static/js/cv-editor.js` - FontSize/Highlight extensions, indent functions, `updateMainCVDisplay()` (600+ lines total)
- `frontend/templates/job_detail.html` - Reorganized toolbar with new controls, editor panel
- `tests/frontend/test_cv_*.py` - 38 unit tests for Phase 2 features

**Resolved Issues Analysis (2025-11-27)**:

| Issue                                           | Status   | Root Cause                                | Resolution                                                                                                                                                                |
| ----------------------------------------------- | -------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #1: CV Display Not Updating Immediately         | RESOLVED | Missing event handler on editor close     | `updateMainCVDisplay()` function added to `closeCVEditorPanel()` (cv-editor.js:674) - converts TipTap JSON to HTML and updates `#cv-markdown-display`                     |
| #2: Editor Not WYSIWYG - Formatting Not Visible | RESOLVED | Missing CSS for ProseMirror content nodes | 178 lines of `.ProseMirror` CSS rules added to base.html (lines 287-464) covering all formatting: bold, italic, underline, headings, lists, alignment, colors, highlights |

**Verification**:

- Issue #1: `updateMainCVDisplay()` function present and functional (cv-editor.js:689-719)
- Issue #2: CSS styles verified for: `.ProseMirror strong`, `.ProseMirror em`, `.ProseMirror h1-h3`, `.ProseMirror ul/ol`, `.ProseMirror mark`, text alignment, and more
- Google Fonts CSS loaded with 60+ fonts (base.html:109-111)
- All 38 Phase 2 unit tests passing

**Test Status**: 38 unit tests written and passing for Phase 2 features (all code issues resolved)
**Code Status**: All features committed and fully functional
**Next Steps**:

1. Integration testing with manual user validation (if not already done)
2. Mark Phase 2 as PRODUCTION READY
3. Begin Phase 3: Document-level styles

#### Phase 3: Document-Level Styles ✅ COMPLETE (2025-11-27)

**Status**: Code complete and tested (28 tests passing)
**Implementation Date**: 2025-11-27
**Actual Duration**: ~4 hours

**Delivered Features**:

- Line height adjustment (Single 1.0, Standard 1.15, 1.5 Lines, Double 2.0)
- Document margins with 0.25" increments (0.5" to 2.0" range)
- Independent control for top, right, bottom, left margins
- Default: 1.0" all sides (standard resume format)
- Page size selector: Letter (8.5"×11") and A4 (210mm×297mm)
- Optional header text input (appears at top of CV)
- Optional footer text input (appears at bottom of CV)
- Real-time CSS application to editor preview
- MongoDB persistence of all Phase 3 settings

**Files Modified/Created**:

- `frontend/app.py` (+22 lines) - Backend defaults and MongoDB schema
- `frontend/static/js/cv-editor.js` (+182 lines) - Document style functions
- `frontend/templates/job_detail.html` (+111 lines) - Document Settings toolbar
- `tests/frontend/conftest.py` (+30 lines) - Updated fixtures
- `tests/frontend/test_cv_editor_phase3.py` (+852 lines) - 28 comprehensive tests

**Technical Implementation**:

- Document Settings collapsible toolbar section
- CSS applied as inline styles to `.ProseMirror` element
- Margins implemented as padding (preserves editor background)
- Page size controls max-width and min-height
- Auto-save on any document style change

**Test Status**: 28/28 tests passing (100%)

- Document margin controls: 5 tests
- Line height adjustment: 5 tests
- Page size selector: 6 tests
- Header/footer support: 4 tests
- Phase 3 integration: 3 tests
- CSS application: 3 tests
- Backward compatibility: 2 tests

**MongoDB Schema Extensions**:

- `documentStyles.lineHeight`: float (default 1.15)
- `documentStyles.margins`: object with top/right/bottom/left (default 1.0 each)
- `documentStyles.pageSize`: string "letter" or "a4" (default "letter")
- `header`: string (optional)
- `footer`: string (optional)

**Next Steps**: Phase 3 complete, ready for Phase 4 (PDF Export)

#### Phase 4: PDF Export via Playwright ✅ COMPLETE & MIGRATED TO RUNNER (2025-11-27)

**Status**: Code complete, tested (22 tests passing), and migrated to runner service
**Initial Implementation Date**: 2025-11-27
**Migration Date**: 2025-11-27
**Actual Duration**: ~8 hours (initial implementation + migration)

**Initial Implementation (Frontend - Option A - DEPRECATED)**:
- Initially implemented in `frontend/app.py` using local Playwright
- Problem: Vercel serverless functions don't support browser automation
- Playwright requires Chromium binary (~130 MB) not available on Vercel
- Solution: Migrated to runner service where Playwright already installed

**Current Implementation (Runner Service - Option B - ACTIVE)**:

**Location**: Runner Service (VPS 72.61.92.76)

**Architecture Decision:**
PDF generation moved from frontend (Vercel) to runner service (VPS) because:
- Vercel is a serverless platform with no system-level access for Chromium
- Runner service already has Playwright 1.40.0+ installed in Docker
- VPS provides full control over dependencies and resource allocation
- Better performance and cost efficiency for compute-heavy PDF rendering

**Delivered Features**:
- Server-side PDF generation using Playwright (Chromium) on runner
- Frontend proxies requests to runner service via HTTP
- ATS-compatible PDF output with selectable text
- 60+ Google Fonts properly embedded in PDFs
- Page size support: Letter (8.5×11") and A4 (210×297mm)
- Custom margins, line height, and document styles from Phase 3
- Optional header/footer text inclusion
- Export button integrated in CV editor toolbar
- Filename format: `CV_<Company>_<Title>.pdf`
- Comprehensive error handling with fallback messaging

**Files Modified/Created**:

*Runner Service*:
- `runner_service/pdf_helpers.py` (349 lines) - NEW
  - `sanitize_for_path()` - Path sanitization for filenames
  - `tiptap_json_to_html()` - Convert TipTap JSON to HTML with embedded fonts
  - `build_pdf_html_template()` - Build complete HTML document for PDF rendering
- `runner_service/app.py` (lines 368-498) - PDF generation endpoint
  - `POST /api/jobs/{id}/cv-editor/pdf`
  - Fetches cv_editor_state from MongoDB
  - Generates PDF with Playwright
  - Returns binary PDF with proper headers

*Frontend*:
- `frontend/app.py` (lines 870-939) - PDF proxy endpoint
  - `POST /api/jobs/{id}/cv-editor/pdf`
  - Forwards request to runner service
  - Handles timeout/error cases
  - Streams PDF response to user
- `frontend/static/js/cv-editor.js` - `exportCVToPDF()` function unchanged

**Test Status**: 22/22 tests passing (100%)
**Dependencies**:
- Runner: Playwright 1.40.0+, Chromium installed in Dockerfile.runner
- Frontend: `requests` library (standard Flask dependency)

**Technical Details**:
- Runner generates HTML from TipTap JSON with embedded Google Fonts
- Playwright configured with: `format=pageSize, margin=custom, printBackground=True`
- Auto-save before export ensures latest content included
- Download filename: `CV_<Company>_<Title>.pdf`
- Comprehensive error handling with proper HTTP status codes

**Configuration (Environment Variables)**:
```bash
# Frontend (app.py)
RUNNER_URL=http://72.61.92.76:8000

# Runner Service (app.py)
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=job_search
PLAYWRIGHT_HEADLESS=true
```

**Endpoint Details**:
- **Frontend Endpoint**: `POST /api/jobs/{id}/cv-editor/pdf` (proxy only)
- **Runner Endpoint**: `POST http://72.61.92.76:8000/api/jobs/{id}/cv-editor/pdf` (actual generation)

**Benefits of Migration**:
- Eliminates Vercel serverless limitations
- Leverages existing Playwright installation
- Better PDF rendering consistency on dedicated VPS
- Improves frontend performance (offloads compute)
- Easier to scale PDF generation independently

#### Phase 5: Polish + Comprehensive Testing (PENDING - MULTIPLE FEATURES)

**Status**: Multiple Phase 5 sub-features identified; partial implementation in progress
**Total Estimated Duration**: 16-20 hours (all Phase 5 sub-features combined)

**Phase 5 Sub-Features**:

##### Phase 5.1: WYSIWYG Page Break Visualization ✅ **COMPLETED 2025-11-28**

**Status**: COMPLETE and TESTED
**Completion Date**: 2025-11-28
**Implementation Duration**: 8-10 hours
**Test Coverage**: 32 unit tests (100% passing, 0.02s execution)
**Implementation Report**: See `reports/PHASE5_1_IMPLEMENTATION_2025-11-28.md`
**Plan Document**: See `plans/phase5-page-break-visualization.md`

**Description**:
Visual page break indicators in CV editor and detail page showing exactly where content will break across pages in PDF export. Respects page size (Letter/A4) and margin settings for true WYSIWYG experience.

**Features Delivered**:
- [x] Page break calculator (calculate break positions from content height)
- [x] Page break renderer (insert visual break indicators with "Page X" labels)
- [x] Dynamic update integration (recalculate on content/style changes with 300ms debounce)
- [x] Detail page integration (show breaks in main CV display)
- [x] Comprehensive test suite (32 tests, all passing)
- [x] Visual indicators (gray dashed lines)
- [x] Support for Letter and A4 page sizes
- [x] Respects all margin and layout settings

**New Module**:
- `frontend/static/js/page-break-calculator.js` (240 lines)

**Files Modified**:
- `frontend/static/js/cv-editor.js` - Integration of page break calculator
- `frontend/templates/job_detail.html` - Detail page integration

**Test Coverage**:
- Basic page break scenarios: 4 tests
- Page size support (Letter/A4): 6 tests
- Margin variations: 5 tests
- Content type handling: 4 tests
- Edge cases: 4 tests
- Position accuracy: 5 tests
- Real-world scenarios: 4 tests

**Dependencies Completed**:
- Phase 3: Document margins, page size, line height (COMPLETE)
- Phase 4: PDF export respects margins and page size (COMPLETE)

##### Phase 5.2: Other Polish Features

**Status**: Not started
**Components Identified**:
- [ ] Keyboard shortcuts (Ctrl+B, Ctrl+I, Ctrl+Z, etc.) - 2-3 hours
- [ ] Version history / undo-redo beyond browser (API + frontend) - 3-4 hours
- [ ] Mobile responsiveness testing - 1-2 hours
- [ ] Accessibility (WCAG 2.1 AA) compliance - 4-6 hours
- [ ] E2E test re-enablement and CI/CD integration - 2-3 hours

**Total Estimated Remaining**:
- Phase 5.1 (Page Breaks): 8-10 hours
- Phase 5.2 (Other Features): 12-18 hours
- **Total**: 20-28 hours

---

## Layer-Specific Notes

| Layer                | Status   | Gap                                        |
| -------------------- | -------- | ------------------------------------------ |
| 1.4 (JD Extractor)   | Complete | None - CV Gen V2 Phase 1 complete          |
| 2 (Pain Points)      | Complete | None                                       |
| 2.5 (STAR)      | Complete | No embeddings/caching, disabled by default |
| 3 (Company)     | Complete | None                                       |
| 3.5 (Role)      | Complete | None                                       |
| 4 (Fit)         | Complete | STAR citation advisory only                |
| 5 (People)      | Complete | FireCrawl off by default, no rate limiting |
| 6 (Generator)   | Complete | Anthropic credits needed, no .docx         |
| 7 (Publisher)   | Complete | No Drive/Sheets by default                 |

---

## New Requirements (2025-11-29)

> Added via doc-sync agent. See approved plan: `.claude/plans/cheerful-stirring-capybara.md`

### Bugs

#### #1 Export CV Button on Detail Page
**Status**: FIXED ✅ **COMPLETED 2025-11-30**
**Priority**: High
- [x] Enhanced error handling with console logging and user feedback
- [x] Improved error messages displayed via toast notifications
- **Files**: `frontend/templates/job_detail.html`, `frontend/static/js/cv-editor.js`

#### #4 Line Spacing in Editor
**Status**: Not started
**Priority**: High
- [ ] Line spacing CSS (`line-height`) not cascading to all elements in editor
- [ ] Affects: headings, lists, paragraphs within `.ProseMirror`
- Root cause: Likely missing CSS selectors for nested elements
- **Files**: `frontend/templates/base.html` (CSS rules ~lines 284-461)

#### #5 Line Spacing with Multiple Companies in CV
**Status**: Not started
**Priority**: High
- [ ] Separate issue from #4 - affects CV GENERATION not editor
- [ ] When CV has 2+ companies, line spacing breaks in generated output
- Root cause: TipTap JSON conversion or HTML template logic
- **Files**: `pdf_service/pdf_helpers.py`, `src/layer6/generator.py`

#### #9 ATS Compliance Research ✅ **COMPLETED 2025-11-30**
**Status**: RESEARCHED (Commit ca8e8f81)
**Priority**: High
- [x] Comprehensive ATS compliance analysis completed
- [x] Report: `reports/ats-compliance-research.md`
- [x] Key Findings:
  - Keyword stuffing backfires (modern ATS penalizes repetition)
  - Context-aware keyword integration is best practice
  - Recommendations for CV generator improvements documented
- **Files**: `reports/ats-compliance-research.md`, bugs.md

### Features

#### #2 WYSIWYG Style Consistency
**Status**: Not started
**Priority**: Medium
- [ ] Editor (.ProseMirror) and detail page (#cv-markdown-display) have different styles
- [ ] Create unified CSS system for consistent rendering
- **Plan document**: `plans/cv-editor-wysiwyg-consistency.md`
- **Files**: `frontend/templates/base.html` (CSS), `frontend/static/js/cv-editor.js`

#### #3 Margin Presets (MS Word Style)
**Status**: Not started
**Priority**: Medium
- [ ] Add "Narrow" (0.5"), "Normal" (1.0"), "Wide" (1.5") margin presets
- [ ] Keep existing 0.25" increment controls as "Custom" option
- Implementation: Dropdown in Document Settings toolbar
- **Files**: `frontend/templates/job_detail.html`, `frontend/static/js/cv-editor.js`

#### #6 Structured Logging for Pipeline Status
**Status**: Not started
**Priority**: Medium
- [ ] Replace print() with structured JSON logging in all layers
- [ ] Emit events for frontend status button updates
- [ ] Format: `{"event": "layer_complete", "layer": N, "status": "success/error"}`
- **Plan document**: `plans/structured-logging-implementation.md`
- **Files**: All `src/layer*.py` files, `runner_service/app.py`

#### #10 Fallback AI Agent Infrastructure (Option B)
**Status**: Not started
**Priority**: Medium
- [ ] Implement LangGraph sub-agent fallback for contact discovery
- [ ] Config flag: `ENABLE_FIRECRAWL_FALLBACK=true/false`
- [ ] When FireCrawl fails, use LLM agent to generate contacts
- **Reference**: `plans/firecrawl-contact-discovery-solution.md`
- **Plan document**: `plans/ai-agent-fallback-implementation.md`
- **Files**: `src/layer5/people_mapper.py`

#### #11 Job Iframe Viewer
**Status**: Phase 1 Complete ✅ **COMPLETED 2025-11-30**
**Priority**: Low
- [x] Collapsible iframe showing original job posting URL (Option B: expandable section)
- [x] Loading state with spinner animation
- [x] Error handling for X-Frame-Options blocking with user-friendly fallback message
- [x] "Open in New Tab" button as escape hatch for blocked sites
- [ ] PDF export button for iframe content (Phase 3 - future enhancement)
- **Plan document**: `plans/job-iframe-viewer-implementation.md`
- **Files**: `frontend/templates/job_detail.html`
- **Implementation Details**:
  - Collapsible section with arrow icon (▶/▼)
  - Timeout detection (3 seconds) for X-Frame-Options blocking
  - Fallback message shown when iframe blocked by security headers
  - Responsive layout (500px height, full width)
  - Security: sandbox attributes for script execution control

### UI/UX

#### #7 Smaller Pipeline Status Buttons
**Status**: Not started
**Priority**: Low
- [ ] Reduce size of pipeline status buttons on job detail page
- [ ] Improve visual hierarchy
- **Files**: `frontend/templates/job_detail.html`, CSS in base.html

### Documentation/Planning

#### #8 Prompt Optimization Plan
**Status**: Plan exists - ready for implementation
**Priority**: CRITICAL
- [x] Comprehensive plan created: `plans/prompt-optimization-plan.md`
- [ ] Implement fixes for layers not meeting thresholds (per `reports/prompt-ab/integration-final.md`):
  - layer4: Improve specificity (6.8→7.0), grounding (7.2→8.0)
  - layer6a: Reduce hallucinations (8.5→9.0)
  - layer6b: Improve all metrics (specificity 6.5, grounding 5.8, combined 7.3)
- **Files**: `src/layer4/opportunity_mapper.py`, `src/layer6/*.py`

---

## CV Generation V2: Multi-Stage Architecture (2025-11-30)

> **Plan document**: `plans/cv-generation-v2-architecture.md`
> **Status**: Phase 1 Complete (Layer 1.4: JD Extractor)

**Objective**: Replace monolithic CV generation with divide-and-conquer multi-stage pipeline.

**Key Benefits**:
- 100% career coverage (all 6 companies, not just last 2)
- Sequential processing (predictable, debuggable, cost-controlled)
- Per-role hallucination QA (smaller scope = better validation)
- Role-category-aware emphasis (IC vs leadership tailoring)
- ATS optimization with 15-keyword tracking

### Phase Progress

| Phase | Component | Status | Tests | Notes |
|-------|-----------|--------|-------|-------|
| 1 | Layer 1.4: JD Extractor | ✅ Complete | 33 | Structured JD intelligence |
| 2 | CV Loader | ✅ Complete | 19 | Load pre-split role files |
| 3 | Per-Role Generator | ✅ Complete | 39 | Tailored bullets per role with QA |
| 4 | Stitcher | ✅ Complete | 26 | Cross-role deduplication + word budget |
| 5 | Header/Skills Generator | ✅ Complete | 34 | Profile + skills grounded in achievements |
| 6 | Grader + Improver | ✅ Complete | 32 | Multi-dimensional grading + single-pass improvement |

### Layer 1.4 Implementation (COMPLETE)

**Delivered** (2025-11-30):
- [x] `ExtractedJD` TypedDict added to `src/common/state.py`
- [x] `CompetencyWeights` TypedDict for role-category emphasis
- [x] `src/layer1_4/` package with prompts and extractor
- [x] Pydantic validation for 5 role categories and competency weights
- [x] Workflow integration (entry point when enabled)
- [x] Config flag: `ENABLE_JD_EXTRACTOR=true` (default)
- [x] 33 unit tests (100% passing)

**ExtractedJD Schema**:
- Role classification: engineering_manager, staff_principal_engineer, director_of_engineering, head_of_engineering, cto
- Competency weights: delivery, process, architecture, leadership (sum=100)
- ATS keywords: Top 15 for optimization
- Structured content: responsibilities, qualifications, nice_to_haves, skills
- Inferred intelligence: implied_pain_points, success_metrics, industry_background

**Files Created**:
- `src/layer1_4/__init__.py`
- `src/layer1_4/prompts.py` (JD extraction prompts)
- `src/layer1_4/jd_extractor.py` (extraction logic + node function)
- `tests/unit/test_layer1_4_jd_extractor.py` (33 tests)

**Files Modified**:
- `src/common/state.py` - Added ExtractedJD and CompetencyWeights TypedDicts
- `src/common/config.py` - Added ENABLE_JD_EXTRACTOR flag
- `src/workflow.py` - Added jd_extractor_node, updated flow

### Phase 2: CV Loader Implementation (COMPLETE)

**Delivered** (2025-11-30):
- [x] Renamed from CV Splitter to CV Loader (loads pre-split files, not dynamic parsing)
- [x] `CVLoader` class with data loading and filtering methods
- [x] `RoleData` dataclass with computed `bullet_count` property
- [x] `CandidateData` dataclass (static fields only - profile/skills generated dynamically)
- [x] 6 pre-split role markdown files in `data/master-cv/roles/`
- [x] `role_metadata.json` with role metadata and candidate info
- [x] Filtering by competency, industry, current role
- [x] 19 unit tests (100% passing)

**Files Created**:
- `src/layer6_v2/cv_loader.py` (331 lines)
- `src/layer6_v2/__init__.py`
- `data/master-cv/role_metadata.json`
- `data/master-cv/roles/01_seven_one_entertainment.md`
- `data/master-cv/roles/02_samdock_daypaio.md`
- `data/master-cv/roles/03_ki_labs.md`
- `data/master-cv/roles/04_fortis.md`
- `data/master-cv/roles/05_osram.md`
- `data/master-cv/roles/06_clary_icon.md`
- `tests/unit/test_layer6_v2_cv_loader.py` (19 tests)

**Design Decision**: Profile and core_skills are NOT stored in metadata - they are generated dynamically by Header Generator (Phase 5) after stitching, tailored to each application.

### Phase 3: Per-Role Generator Implementation (COMPLETE)

**Delivered** (2025-11-30):
- [x] `GeneratedBullet` dataclass with source traceability
- [x] `RoleBullets` dataclass for role-level output
- [x] `CareerContext` dataclass with stage-aware emphasis guidance
- [x] `RoleGenerator` class with LLM-based bullet generation
- [x] `RoleQA` class with hallucination detection and ATS keyword checking
- [x] Pydantic validation for LLM response parsing
- [x] Sequential role processing with `generate_all_roles_sequential()`
- [x] 39 unit tests (100% passing)

**Files Created**:
- `src/layer6_v2/types.py` (165 lines) - Data types for generation pipeline
- `src/layer6_v2/role_generator.py` (275 lines) - Per-role bullet generation
- `src/layer6_v2/role_qa.py` (315 lines) - Hallucination and ATS QA
- `src/layer6_v2/prompts/__init__.py`
- `src/layer6_v2/prompts/role_generation.py` (155 lines) - Generation prompts
- `tests/unit/test_layer6_v2_role_generator.py` (39 tests)

**Key Features**:
- **Anti-Hallucination QA**: Rule-based metric verification with configurable tolerance
- **Career Stage Awareness**: Different emphasis for recent/mid-career/early roles
- **ATS Keyword Tracking**: Coverage analysis with suggestions for missing keywords
- **Lenient Thresholds**: 15% metric tolerance, 40% flagged bullets allowed

**Configuration Options**:
- `similarity_threshold`: Fuzzy match threshold (default 0.5)
- `metric_tolerance`: Numeric variance allowed (default 15%)
- `max_flagged_ratio`: Bullets allowed to fail QA (default 40%)

### Phase 4: Stitcher Implementation (COMPLETE)

**Delivered** (2025-11-30):
- [x] `StitchedRole` dataclass with markdown output
- [x] `StitchedCV` dataclass combining all roles
- [x] `DuplicatePair` and `DeduplicationResult` for transparency
- [x] `CVStitcher` class with similarity-based deduplication
- [x] Word budget enforcement with career-stage-aware trimming
- [x] Keyword coverage tracking
- [x] 26 unit tests (100% passing)

**Files Created/Modified**:
- `src/layer6_v2/types.py` (+155 lines) - Stitcher types added
- `src/layer6_v2/stitcher.py` (285 lines) - CVStitcher implementation
- `tests/unit/test_layer6_v2_stitcher.py` (26 tests)

**Key Features**:
- **Semantic Deduplication**: Keyword overlap + string similarity + metric matching
- **Career-Stage Trimming**: Trims early-career roles first, never current role
- **Word Budget**: Target 550-650 words with configurable budget
- **Transparency**: Full report of what was deduplicated and why

**Configuration Options**:
- `word_budget`: Target word count (default 600)
- `similarity_threshold`: Deduplication threshold (default 0.75)
- `min_bullets_per_role`: Minimum bullets to keep (default 2)

### Phase 5: Header/Skills Generator Implementation (COMPLETE)

**Delivered** (2025-11-30):
- [x] `SkillEvidence` dataclass mapping skills to bullet evidence
- [x] `SkillsSection` dataclass for skill category with grounding
- [x] `ProfileOutput` dataclass with highlights and keywords
- [x] `ValidationResult` dataclass for skills grounding validation
- [x] `HeaderOutput` dataclass combining all header sections
- [x] `HeaderGenerator` class with LLM-based profile generation
- [x] Skills extraction with evidence tracking (4 categories)
- [x] JD keyword prioritization for extracted skills
- [x] Skills grounding validation (removes ungrounded skills)
- [x] Fallback profile generation when LLM fails
- [x] 34 unit tests (100% passing)

**Files Created**:
- `src/layer6_v2/header_generator.py` (380 lines) - Header generation logic
- `src/layer6_v2/prompts/header_generation.py` (180 lines) - Header prompts
- `tests/unit/test_layer6_v2_header_generator.py` (34 tests)

**Files Modified**:
- `src/layer6_v2/types.py` (+200 lines) - Phase 5 types added
- `src/layer6_v2/__init__.py` - Added Phase 5 exports

**Key Features**:
- **Profile Generation**: 2-3 sentence summary with quantified highlights from experience
- **Skills Extraction**: 4 categories (Leadership, Technical, Platform, Delivery)
- **Evidence Tracking**: Every skill maps to bullets that demonstrate it
- **JD Keyword Priority**: Skills matching JD keywords appear first
- **Grounding Validation**: Ungrounded skills are automatically removed
- **Role-Category Awareness**: Profile tone matches target role (IC vs leadership)

**Skill Categories**:
- Leadership: Team Leadership, Mentorship, Hiring, Strategic Planning
- Technical: Python, Java, TypeScript, Microservices, System Design
- Platform: AWS, Kubernetes, Docker, CI/CD, DevOps
- Delivery: Agile, Scrum, Release Management, Process Improvement

**Configuration Options**:
- `model`: LLM model to use (default: Config.DEFAULT_MODEL)
- `temperature`: Generation temperature (default: 0.3 for consistency)

### Phase 6: Grader + Improver Implementation (COMPLETE)

**Delivered** (2025-11-30):
- [x] `DimensionScore` dataclass for individual dimension grading
- [x] `GradeResult` dataclass with composite scoring and pass/fail logic
- [x] `ImprovementResult` dataclass for improvement tracking
- [x] `FinalCV` dataclass combining all CV components
- [x] `CVGrader` class with 5-dimension multi-dimensional grading
- [x] `CVImprover` class with single-pass targeted improvement
- [x] Rule-based + LLM-based grading with automatic fallback
- [x] Weighted composite scoring (8.5 passing threshold)
- [x] Dimension-specific improvement strategies
- [x] 32 unit tests (100% passing)

**Files Created**:
- `src/layer6_v2/grader.py` (580 lines) - Multi-dimensional grading
- `src/layer6_v2/improver.py` (358 lines) - Single-pass improvement
- `src/layer6_v2/prompts/grading_rubric.py` (338 lines) - Grading prompts
- `tests/unit/test_layer6_v2_grader_improver.py` (32 tests)

**Files Modified**:
- `src/layer6_v2/types.py` (+120 lines) - Phase 6 types added
- `src/layer6_v2/__init__.py` - Added Phase 6 exports

**Grading Dimensions** (weighted):
- ATS Optimization (20%): Keyword coverage, format compliance, parsability
- Impact & Clarity (25%): Metrics, action verbs, specificity
- JD Alignment (25%): Pain point coverage, role match, terminology
- Executive Presence (15%): Strategic framing, leadership evidence, business outcomes
- Anti-Hallucination (15%): Factual accuracy, metric preservation, no fabrication

**Key Features**:
- **Multi-Dimensional Grading**: 5 weighted dimensions with specific rubrics
- **Composite Scoring**: Weighted average with 8.5/10 passing threshold
- **Rule-Based Fallback**: Works without LLM if needed (regex/heuristic scoring)
- **Single-Pass Improvement**: Targets lowest-scoring dimension for cost control
- **Dimension-Specific Strategies**: Different tactics per dimension

**Design Decisions**:
- **Single-pass improvement** (user choice): Grade once, improve once, accept result
- **Cost control**: No iterative re-grading loops that multiply LLM calls
- **Targeted improvement**: Only fix the weakest dimension
- **Graceful degradation**: Rule-based fallback when LLM fails

**Configuration Options**:
- `passing_threshold`: Score needed to pass (default: 8.5)
- `use_llm_grading`: Enable LLM-based grading (default: True)
- `temperature`: LLM generation temperature (default: 0.3)

### CV Gen V2 Orchestrator Integration (COMPLETE)

**Delivered** (2025-11-30):
- [x] `CVGeneratorV2` orchestrator class tying all 6 phases together
- [x] `cv_generator_v2_node` LangGraph node function (drop-in replacement)
- [x] Wired into `workflow.py` with config flag
- [x] `ENABLE_CV_GEN_V2` config flag (default: true)
- [x] 11 orchestrator integration tests (100% passing)

**Files Created**:
- `src/layer6_v2/orchestrator.py` (410 lines) - Full pipeline orchestration
- `tests/unit/test_layer6_v2_orchestrator.py` (11 tests)

**Files Modified**:
- `src/workflow.py` - Conditionally uses CV Gen V2 or legacy generator
- `src/common/config.py` - Added `ENABLE_CV_GEN_V2` flag

**Orchestrator Features**:
- Sequential 6-phase pipeline execution
- Per-role bullet generation with QA
- Cross-role deduplication and word budget enforcement
- Header/skills generation grounded in achievements
- Multi-dimensional grading with fallback
- Single-pass targeted improvement

### CV Gen V2 Complete! 🎉

All 6 phases + orchestrator are now implemented with **194 total unit tests**:
- Phase 1: JD Extractor (33 tests)
- Phase 2: CV Loader (19 tests)
- Phase 3: Per-Role Generator (39 tests)
- Phase 4: Stitcher (26 tests)
- Phase 5: Header Generator (34 tests)
- Phase 6: Grader + Improver (32 tests)
- Orchestrator: Integration (11 tests)

### Next Steps (CV Gen V2)

1. **End-to-End Testing**: Test complete CV generation with real JDs
2. **Production Deployment**: Deploy to VPS with runner service
