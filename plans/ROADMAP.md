# Roadmap (Nov 2025)

Quality-first plan grounded in the current codebase. The pipeline already runs Layers 2–7 via LangGraph with defaults that disable the STAR selector, keep outreach scraping off, and save outputs locally as markdown.

## Current Baseline
- LangGraph workflow: pain-point miner → optional STAR selector → company/role research → opportunity mapper → people mapper → outreach packager → cover letter/CV generator → publisher.
- Company research uses FireCrawl with a Mongo `company_cache` TTL (7 days) and Pydantic validation for summary + signals. People mapper defaults to synthetic contacts; outreach is still generated and packaged.
- CV generation is markdown-only (`CV.md`) via two-pass JSON evidence + QA; cover letters go through validation gates. Outputs live in `applications/<company>/<role>/`.
- Runner service (FastAPI) executes the CLI in a subprocess with log streaming; Flask/HTMX UI for browsing/updating Mongo job records. CI exists for runner and frontend; main pipeline tests are not wired to CI.

## Near-Term Priorities (ready to sequence)
1) **Logging & Config Hardening**
   - Add structured logging (json/logger) with run_id and layer tagging across layers 2–7 and the runner service.
   - Ensure `Config.validate()` runs in the runner path; surface actionable errors for missing env vars or files.

2) **STAR Selector Reliability**
   - Use Mongo `star_records` as the source of truth; add embedding generation + hybrid filter before LLM scoring.
   - Cache selections per `(job_id, pain_points hash)` to avoid rescoring; expose `selected_star_ids` + `star_to_pain_mapping` consistently.

3) **People & Outreach Fidelity**
   - Make FireCrawl outreach discovery configurable with token-bucket throttling; keep synthetic fallback when disabled or empty.
   - Persist outreach artifacts: write per-contact outreach files and store `outreach_packages`/`fallback_cover_letters` back to Mongo.
   - Enrich contacts with company signals (`recent_signals`) when available.

4) **State & Output Completeness**
   - Add missing fields to `JobState` (tier, dossier_path, application_form_fields, cv_text) and keep publisher/dossier in sync.
   - Implement application form miner (Layer 1.5) or remove it from docs; emit `application_form_fields.txt` when available.

5) **Testing & CI**
   - Add GitHub Actions workflow running unit + integration tests for the main pipeline (layers 2–7, star parser, outreach packaging).
   - Track coverage and fail on major regressions; add smoke test for the runner CLI path.

6) **Deployment & Observability**
   - Verify VPS deployment of the runner (docker-compose.runner.yml) with health checks and artifact serving.
   - Add basic metrics/alerts (cost per run, error rate) and minimal cost/rate-limit guards for FireCrawl and LLM calls.

## Backlog / Later
- Tiered execution, batch CLI, and scheduling; populate `pipeline_runs` with run metadata.
- Resume STAR knowledge-graph work (edges, graph filters) once embeddings and caching are in place.
- `.docx` CV export, dossier section validation metadata, and remote publishing defaults when quotas allow.
- Frontend buttons to trigger runs via the runner API and view artifacts.
