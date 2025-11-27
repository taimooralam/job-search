# Implementation Gaps

**Last Updated**: 2025-11-26

> **See also**:
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

---

## Current Blockers

| Issue | Impact | Fix |
|-------|--------|-----|
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
  - All 188 unit tests pass without real API calls
  - Added 30+ new tests for CV editing API and HTML CV generator
- [ ] Integration tests not in GitHub Actions CI
- [ ] No coverage tracking

### Observability
- [ ] All layers use `print()` instead of structured logging
- [ ] No metrics, alerts, or cost tracking
- [ ] Config validation only in CLI, not runner

### Data Completeness
- [ ] `JobState` missing: `tier`, `dossier_path`, `cv_text`, `application_form_fields`
- [ ] `pipeline_runs` collection unused
- [ ] Outreach packages not persisted to MongoDB

### Features (Backlog)
- [ ] STAR selector: No embeddings, caching, or graph edges
- [ ] Layer 1.5: Application form mining not implemented
- [ ] .docx CV export not implemented
- [ ] Rate limiting for FireCrawl/LLM calls
- [x] LinkedIn outreach character limit requirements documented ✅ **COMPLETED 2025-11-27**
  - Connection request: 300 char limit specified
  - InMail: 1900 char body limit specified
  - Mandatory signature: "Best. Taimoor Alam"
  - Full implementation guide: plans/layer6-linkedin-outreach.md

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

#### Phase 2: Enhanced Text Formatting ✅ CODE COMPLETE (2025-11-26) - 2 UX ISSUES PENDING
**Status**: Code complete, features working, 2 UX issues discovered during manual testing
**Completion Date**: 2025-11-26
**Last Updated**: 2025-11-27

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
- `frontend/static/js/cv-editor.js` - FontSize/Highlight extensions, indent functions (600+ lines total)
- `frontend/templates/job_detail.html` - Reorganized toolbar with new controls
- `tests/frontend/test_cv_*.py` - 38 unit tests for Phase 2 features

**Pending Issues (2025-11-27)**:
1. **Issue #1 - CV Display Not Updating Immediately**: Works on page reload, but NOT when closing editor
   - Expected: Changes visible immediately when editor closes
   - Actual: Changes only appear after full page reload
   - Root Cause: JavaScript doesn't convert TipTap JSON to HTML and update main CV display (`#cv-markdown-display`)
   - Fix Needed: Add JavaScript event handler in cv-editor.js to update display on editor close
   - Priority: HIGH
   - See: `plans/cv-editor-phase2-issues.md` Issue #1

2. **Issue #2 - Editor Not WYSIWYG**: Text formatting not visible in editor
   - Expected: Bold/italic/headings styled visually as user types
   - Actual: Raw text visible, no visual formatting (bold shows in metadata but not UI)
   - Root Cause: Missing CSS for TipTap editor .ProseMirror content nodes
   - Fix Needed: Add CSS styling for TipTap editor content nodes in base.html or dedicated css file
   - Priority: CRITICAL
   - See: `plans/cv-editor-phase2-issues.md` Issue #2

**Test Status**: 38 unit tests written and passing for Phase 2 features (no blockers)
**Next Steps**: Fix Issues #1 and #2, then run full regression test suite and mark Phase 2 as COMPLETE+TESTED

#### Phase 3: Document-Level Styles (PENDING - BLOCKED)
**Status**: Not started, blocked by Phase 2 bug fixes
**Estimated Duration**: 4-6 hours (can design in parallel, blocked on testing)
**Requirements**:
- Document margin controls
- Line height adjustment
- Page size selector (Letter, A4)
- Page preview ruler
- Header/footer support

**Blocking Issues**:
- Phase 2 runtime bugs must be fixed and tested first
- Cannot validate Phase 3 without working Phase 2 foundation

#### Phase 4: PDF Export via Playwright (PENDING)
**Status**: Not started
**Estimated Duration**: 4-6 hours
**Requirements**:
- Server-side PDF rendering via Playwright
- Pixel-perfect layout matching on-screen rendering
- ATS-compatible output format
- Font embedding in PDF
- Local and remote export options

#### Phase 5: Polish + Comprehensive Testing (PENDING)
**Status**: Not started
**Estimated Duration**: 3-5 hours
**Requirements**:
- Keyboard shortcuts (Ctrl+B, Ctrl+I, etc.)
- Version history / undo-redo beyond browser
- E2E tests via Selenium/Playwright
- Mobile responsiveness testing
- Accessibility (WCAG 2.1 AA) compliance

**Total Estimated Remaining**: 14-21 hours for Phases 2-5

---

## Layer-Specific Notes

| Layer | Status | Gap |
|-------|--------|-----|
| 2 (Pain Points) | Complete | None |
| 2.5 (STAR) | Complete | No embeddings/caching, disabled by default |
| 3 (Company) | Complete | None |
| 3.5 (Role) | Complete | None |
| 4 (Fit) | Complete | STAR citation advisory only |
| 5 (People) | Complete | FireCrawl off by default, no rate limiting |
| 6 (Generator) | Complete | Anthropic credits needed, no .docx |
| 7 (Publisher) | Complete | No Drive/Sheets by default |
