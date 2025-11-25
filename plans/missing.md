# Implementation Gaps vs ROADMAP

Tracks what is missing or partial relative to the current roadmap. Completed items are removed here.

**Last Updated**: 2025-11-25 (22:30 UTC)

---

## Recently Completed (Nov 25, 2025)
- ✅ **Frontend UX improvements**: Favicon, health indicators (VPS/MongoDB/n8n), loading animation, quick time filters
- ✅ **Frontend CI/CD**: Tests passing (32/32), requests dependency added, authentication fixed
- ✅ **Vercel deployment configuration**: Working-directory conflict resolved, vercel.json restored
- ✅ **Runner service**: Real pipeline execution, artifact serving, JWT auth, MongoDB persistence
- ✅ **Runner CI/CD**: GitHub Actions workflow with auto-deployment to VPS

---

## Highest Impact (Remaining)
- **Frontend-Runner integration**: Process buttons exist in UI but are not wired to runner API endpoints; no SSE log streaming viewer yet
- **Logging/observability**: All layers and the runner use `print`; no structured logs, metrics, or alerts. Config validation is only enforced in the CLI, not the runner path.
- **STAR selector**: LLM-only scorer with no embeddings, caching, or Mongo `star_records` usage. Selector is disabled by default, and downstream prompts do not enforce STAR citations.
- **Application form mining**: Layer 1.5 and `application_form_fields` are absent from the pipeline/state; no checklist files are emitted.
- **People/outreach persistence**: Outreach packages and fallback cover letters are not persisted to Mongo; no per-contact outreach files are written. FireCrawl outreach discovery lacks rate limiting and is off by default, so contacts are synthetic.
- **State completeness**: `JobState` lacks `tier`, `dossier_path`, `cv_text`, and any form-fields state; publisher/dossier still assume those fields exist.
- **CI coverage**: Main pipeline tests are not wired to GitHub Actions; coverage is not tracked or gated.

## Layer-Specific Gaps
- **Layer 2.5 (STAR Selector)**: No hybrid/graph filter, no caching by pain-point hash, no use of MongoDB `star_records`; knowledge-graph edges are not built.
- **Layer 4 (Opportunity Mapper)**: STAR/metric citation is advisory only; rationale can pass without concrete metrics when STARs exist.
- **Layer 5 (People Mapper)**: When FireCrawl is enabled there is no token-bucket throttling; `recent_signals` enrichment comes only from manual inputs, not from research data; contact discovery results are not cached.
- **Layer 6 (Generator)**: CVs are markdown-only (`CV.md`); `cv_text` is never set for Mongo persistence; `.docx` export not implemented.
- **Layer 7 (Publisher)**: Does not record `dossier_path` in state or Mongo; does not emit `application_form_fields.txt`; does not persist `outreach_packages`/fallback letters; does not write per-contact outreach files; `pipeline_runs` collection is unused.

## Infrastructure & Deployment
- **VPS deployment**: Runner service ready but not verified end-to-end on VPS; needs environment variables configured and deployment trigger
- **Frontend deployment**: Vercel configuration fixed; needs environment variables (LOGIN_PASSWORD, FLASK_SECRET_KEY, MONGODB_URI, RUNNER_URL, RUNNER_API_SECRET) to be set in dashboard
- **Rate limits & cost**: No FireCrawl token bucket or LLM cost budgeting; retries exist but no throttling.
- **Remote publishing defaults**: Google Drive/Sheets path is optional; when enabled there is no structured logging/alerting around failures.

## Documentation
- Docs mention tiering/batch execution and application-form mining that are not implemented; keep ROADMAP and this file as the source of truth until features ship.
