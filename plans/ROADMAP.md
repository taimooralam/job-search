# Roadmap (Nov 2025)

Quality-first plan grounded in the current codebase. The pipeline already runs Layers 2–7 via LangGraph with defaults that disable the STAR selector, keep outreach scraping off, and save outputs locally as markdown.

## Current Baseline (Updated 25 Nov 2025)
- LangGraph workflow: pain-point miner → optional STAR selector → company/role research → opportunity mapper → people mapper → outreach packager → cover letter/CV generator → publisher.
- Company research uses FireCrawl with a Mongo `company_cache` TTL (7 days) and Pydantic validation for summary + signals. People mapper defaults to synthetic contacts; outreach is still generated and packaged.
- CV generation is markdown-only (`CV.md`) via two-pass JSON evidence + QA; cover letters go through validation gates. Outputs live in `applications/<company>/<role>/`.
- Runner service (FastAPI) executes the CLI in a subprocess with real-time log streaming, JWT auth, artifact serving, and MongoDB persistence. Deployed via Docker with CI/CD automation.
- Flask/HTMX UI on Vercel with password auth, health indicators, time filters, and process job buttons (UI complete, API wiring pending).
- CI/CD operational for runner (18/18 tests) and frontend (32/32 tests); main pipeline tests exist but not in GitHub Actions yet.

## Recently Completed (25 Nov 2025)
1. ✅ **Runner Service Production Readiness**
   - Real pipeline execution via subprocess with log streaming
   - JWT authentication and CORS middleware
   - Artifact serving with path validation
   - MongoDB persistence for run status
   - Docker deployment with CI/CD automation (GitHub Actions)
   - Comprehensive test coverage (18/18 tests passing)

2. ✅ **Frontend Deployment & UX**
   - Vercel deployment configuration and CI/CD
   - Password-protected session authentication
   - Health status indicators (VPS, MongoDB, n8n) with 30s refresh
   - Quick time filter buttons (1h-1m range)
   - Loading animations and responsive design
   - Process job button UI components
   - Frontend tests (32/32 passing)

## Near-Term Priorities (ready to sequence)
1) **Complete Frontend-Runner Integration** (~2-3 hours)
   - Wire process buttons to runner API endpoints
   - Implement SSE log streaming viewer in UI
   - Configure production environment variables (Vercel + VPS)
   - Test end-to-end: UI → VPS → MongoDB flow

2) **Deployment Verification**
   - Configure Vercel environment variables (LOGIN_PASSWORD, FLASK_SECRET_KEY, MONGODB_URI, RUNNER_URL, RUNNER_API_SECRET)
   - Configure VPS environment variables (.env with all pipeline secrets)
   - Trigger VPS deployment via CI/CD or manual deployment
   - Verify health endpoints and run test job

3) **Logging & Config Hardening**
   - Add structured logging (json/logger) with run_id and layer tagging across layers 2–7 and the runner service.
   - Ensure `Config.validate()` runs in the runner path; surface actionable errors for missing env vars or files.

4) **STAR Selector Reliability**
   - Use Mongo `star_records` as the source of truth; add embedding generation + hybrid filter before LLM scoring.
   - Cache selections per `(job_id, pain_points hash)` to avoid rescoring; expose `selected_star_ids` + `star_to_pain_mapping` consistently.

5) **People & Outreach Fidelity**
   - Make FireCrawl outreach discovery configurable with token-bucket throttling; keep synthetic fallback when disabled or empty.
   - Persist outreach artifacts: write per-contact outreach files and store `outreach_packages`/`fallback_cover_letters` back to Mongo.
   - Enrich contacts with company signals (`recent_signals`) when available.

6) **State & Output Completeness**
   - Add missing fields to `JobState` (tier, dossier_path, application_form_fields, cv_text) and keep publisher/dossier in sync.
   - Implement application form miner (Layer 1.5) or remove it from docs; emit `application_form_fields.txt` when available.

7) **Testing & CI**
   - Add GitHub Actions workflow running unit + integration tests for the main pipeline (layers 2–7, star parser, outreach packaging).
   - Track coverage and fail on major regressions; add smoke test for the runner CLI path.

8) **Observability & Cost Controls**
   - Add basic metrics/alerts (cost per run, error rate) and minimal cost/rate-limit guards for FireCrawl and LLM calls.
   - Implement structured logging for cost tracking and debugging.

## Backlog / Later
- Tiered execution, batch CLI, and scheduling; populate `pipeline_runs` with run metadata.
- Resume STAR knowledge-graph work (edges, graph filters) once embeddings and caching are in place.
- `.docx` CV export, dossier section validation metadata, and remote publishing defaults when quotas allow.
- Artifact download/viewing in frontend UI (currently artifacts accessible via API).
