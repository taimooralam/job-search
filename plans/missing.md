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
