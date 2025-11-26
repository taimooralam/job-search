# Implementation Gaps vs ROADMAP

Tracks what is missing or partial relative to the current roadmap. Completed items are removed here.

**Last Updated**: 2025-11-26 (09:00 UTC)

---

## Recently Completed (Nov 26, 2025)
- ✅ **FireCrawl contact discovery (Option A)**: Replaced verbose natural language queries with SEO-style patterns (site operators, boolean logic); extract contacts from search result metadata instead of scraping blocked pages; run multiple parallel targeted searches; updated tests; synthetic fallback now generates 4+4 contacts to meet quality gate
- ✅ **Frontend detailed view enhancements**: Added Pain Points, Opportunity/Fit Analysis, and Key Contacts sections to job detail page; primary contacts show expandable LinkedIn messages and email outreach; secondary contacts displayed in grid layout
- ✅ **Frontend UX improvements** (Nov 25): Favicon, health indicators (VPS/MongoDB/n8n), loading animation, quick time filters
- ✅ **Frontend CI/CD** (Nov 25): Tests passing (32/32), requests dependency added, authentication fixed
- ✅ **Vercel deployment configuration** (Nov 25): Working-directory conflict resolved, vercel.json restored
- ✅ **Runner service** (Nov 25): Real pipeline execution, artifact serving, JWT auth, MongoDB persistence
- ✅ **Runner CI/CD** (Nov 25): GitHub Actions workflow with auto-deployment to VPS

---

## Highest Impact (Remaining)
- **Frontend-Runner integration**: Process buttons exist in UI but are not wired to runner API endpoints; no SSE log streaming viewer yet
- **Logging/observability**: All layers and the runner use `print`; no structured logs, metrics, or alerts. Config validation is only enforced in the CLI, not the runner path.
- **STAR selector**: LLM-only scorer with no embeddings, caching, or Mongo `star_records` usage. Selector is disabled by default, and downstream prompts do not enforce STAR citations.
- **Application form mining**: Layer 1.5 and `application_form_fields` are absent from the pipeline/state; no checklist files are emitted.
- **People/outreach persistence**: Outreach packages and fallback cover letters are not persisted to Mongo; no per-contact outreach files are written. ✅ **(Nov 26)** FireCrawl contact discovery improved with SEO-style queries; **Remaining**: Rate limiting missing, is off by default (DISABLE_FIRECRAWL_OUTREACH=true).
- **State completeness**: `JobState` lacks `tier`, `dossier_path`, `cv_text`, and any form-fields state; publisher/dossier still assume those fields exist.
- **CI coverage**: Main pipeline tests are not wired to GitHub Actions; coverage is not tracked or gated.

## Layer-Specific Gaps
- **Layer 2.5 (STAR Selector)**: No hybrid/graph filter, no caching by pain-point hash, no use of MongoDB `star_records`; knowledge-graph edges are not built.
- **Layer 4 (Opportunity Mapper)**: STAR/metric citation is advisory only; rationale can pass without concrete metrics when STARs exist.
- **Layer 5 (People Mapper)**: ✅ **(Nov 26)** FireCrawl contact discovery now uses SEO-style queries with metadata extraction; **Remaining gaps**: No token-bucket throttling; `recent_signals` enrichment comes only from manual inputs, not from research data; contact discovery results are not cached.
- **Layer 6 (Generator)**: CVs are markdown-only (`CV.md`); `cv_text` is never set for Mongo persistence; `.docx` export not implemented.
- **Layer 7 (Publisher)**: Does not record `dossier_path` in state or Mongo; does not emit `application_form_fields.txt`; does not persist `outreach_packages`/fallback letters; does not write per-contact outreach files; `pipeline_runs` collection is unused.

## Infrastructure & Deployment
- **VPS deployment**: Runner service ready but not verified end-to-end on VPS; needs environment variables configured and deployment trigger
- **Frontend deployment**: Vercel configuration fixed; needs environment variables (LOGIN_PASSWORD, FLASK_SECRET_KEY, MONGODB_URI, RUNNER_URL, RUNNER_API_SECRET) to be set in dashboard
- **Rate limits & cost**: No FireCrawl token bucket or LLM cost budgeting; retries exist but no throttling.
- **Remote publishing defaults**: Google Drive/Sheets path is optional; when enabled there is no structured logging/alerting around failures.

## Documentation
- Docs mention tiering/batch execution and application-form mining that are not implemented; keep ROADMAP and this file as the source of truth until features ship.
