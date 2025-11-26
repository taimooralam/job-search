# Roadmap (Nov 2025)

> **See also**:
> - `plans/architecture.md` - System architecture
> - `plans/next-steps.md` - Immediate action items
> - `plans/missing.md` - Implementation gaps

---

## Current State

The 7-layer LangGraph pipeline is **fully implemented**:

| Layer | Component | Status |
|-------|-----------|--------|
| 2 | Pain Point Miner | Complete |
| 2.5 | STAR Selector | Complete (disabled by default) |
| 3 | Company Researcher | Complete |
| 3.5 | Role Researcher | Complete |
| 4 | Opportunity Mapper | Complete |
| 5 | People Mapper | Complete (SEO queries + synthetic fallback) |
| 6 | CV & Cover Letter Generator | Complete |
| 7 | Publisher | Complete |

**Infrastructure**:
- Runner Service: Complete (FastAPI, subprocess, JWT auth)
- Frontend: Complete (Flask/HTMX, process buttons, SSE logs)
- CI/CD: Complete (GitHub Actions for runner + frontend)

---

## Immediate Priorities

See `plans/next-steps.md` for detailed steps:

1. **Fix Anthropic credits** or switch to OpenAI for CV generation
2. **Run local pipeline smoke test**
3. **Configure VPS and Vercel environment variables**
4. **Deploy and verify end-to-end**

---

## Future Enhancements (Backlog)

### High Value
- [ ] Add mocking to CV generator tests (avoid real API calls in CI)
- [ ] Structured logging with run_id tagging
- [ ] Cost tracking per pipeline run

### Medium Value
- [ ] STAR selector with embeddings and caching
- [ ] Enable FireCrawl contact discovery (currently synthetic)
- [ ] .docx CV export
- [ ] Pipeline runs collection for history

### Lower Priority
- [ ] Layer 1.5: Application form mining
- [ ] Tiered execution and batch processing
- [ ] Knowledge graph edges for STAR records
- [ ] Google Drive/Sheets publishing (currently local only)

---

## Test Coverage

| Area | Tests | Status |
|------|-------|--------|
| Unit tests (core) | 135+ | Passing |
| Runner service | 18+ | Passing |
| Frontend | 32 | Passing |
| CV generator | 21 | Need mocking (API calls) |
| Integration | - | Not in CI |
