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

### CV Rich Text Editor (NEW - See `plans/editor-solution.md`)
- [ ] **Phase 1: Foundation** - TipTap editor, side panel UI, open/close/expand
- [ ] **Phase 2: Rich Text** - Google Fonts, font family/size selectors, lists, indentation
- [ ] **Phase 3: Persistence** - Auto-save (3s debounce), MongoDB `cv_editor_state` field, save indicator
- [ ] **Phase 4: PDF Export** - Playwright on VPS, pixel-perfect rendering, ATS-compatible
- [ ] **Phase 5: Polish** - Ruler, keyboard shortcuts, unit/integration tests

**Estimated: 16-23 hours total**

Key Requirements:
- Notion-style collapsible side panel (expandable to full screen)
- Floating slidable toolbar with B/I/U, bullet points, numbered lists
- Professional fonts (Inter, Roboto, Open Sans, etc.)
- Tabbing and ruler feature
- Auto-save with visual indicator (●/○/◐)
- Exact state restoration from MongoDB (content + styles)
- PDF export to local machine

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
