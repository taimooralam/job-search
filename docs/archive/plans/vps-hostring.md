# Hostinger VPS Runner + Vercel UI Integration Plan

## 1) Current Status (repo)
- **Pipeline**: LangGraph workflow in `src/workflow.py`, invoked via CLI (`scripts/run_pipeline.py`) and queue helper (`scripts/process_pipeline_job.py`). Pulls jobs from Mongo (`level-1/level-2`), uses `.env` keys for OpenAI/OpenRouter, FireCrawl, Google. Outputs go to `./applications/<company>/<role>/` plus optional Drive/Sheets publishing in Layer 7. Logs are stdout only; no API or streaming.
- **Frontend (Vercel)**: Flask + HTMX UI (`frontend/app.py`, `frontend/templates/*`), deployed through `frontend/api/index.py` + `vercel.json` as a serverless function. Works with Mongo `level-2` for listing/searching/deleting/updating status. No “process” trigger, no job-run API calls, no artifact display.
- **Data/Docs**: Candidate profile defaults to `master-cv.md`; CV/dossier outputs live on disk/Drive, not exposed to the UI. LangSmith tracing available if configured, but not surfaced in UI.
- **Gap**: There is no persistent job runner service, queue, or log streaming channel that the Vercel frontend can call. Pipeline execution currently assumes local machine access to Mongo + secrets + filesystem.

## 2) Goals (from user)
- Clicking a “process” button on one or many rows kicks off pipeline runs on Hostinger VPS Docker containers.
- Realtime status + detailed logs visible in the UI while the job runs.
- When a job finishes, surface the generated CV markdown as HTML in a detail page/section.
- Allow in-browser edits to the CV and export both `dossier.pdf` and `CV.pdf` directly after edits.
- Support bulk job kicks while keeping Vercel frontend responsive.

## 3) Proposed Architecture (VPS service + Vercel UI)
- **Job Runner Service (VPS, FastAPI/Flask)**: REST + SSE/WS API in front of Docker. Responsible for auth, queuing, log streaming, artifact serving.
- **Queue & Workers**: Redis + RQ/Celery (or a simple in-process queue if low volume). Workers launch `docker run` of the pipeline image with job_id + profile path/env. Bulk requests enqueue N jobs.
- **Artifacts Store**: Keep `applications/` directory on VPS; optionally push PDFs/HTML to an object store or expose via signed-download endpoint. Persist CV markdown/HTML + PDF URLs back into Mongo so Vercel UI can fetch them.
- **Progress Streaming**: Stream stdout/stderr from the container to clients via SSE (simplest for Vercel) or WebSockets. Log lines also buffered to a capped store (Redis/list) for later retrieval.
- **Vercel Frontend Bridge**: Add serverless routes that call the VPS API with a signed token. HTMX can subscribe to SSE endpoints directly (CORS-allowed) or via a Vercel proxy if needed. Keep calls short-lived; use streaming endpoints for live logs.
- **Security**: Do not expose Docker socket; the runner service wraps it. Use JWT/shared secret between Vercel and VPS; apply CORS allowlist and rate limits.

## 4) API Sketch (VPS)
- `POST /jobs/run`: `{ job_id, profile_ref?, source? }` → `{ run_id, status_url, stream_url }` (enqueues one job).
- `POST /jobs/run-bulk`: `{ job_ids: [] }` → array of `{ job_id, run_id }`.
- `GET /jobs/{run_id}/status`: `{ status, started_at, updated_at, progress_pct?, current_step?, artifacts: { cv_md_url, cv_html_url, cv_pdf_url, dossier_pdf_url } }`.
- `GET /jobs/{run_id}/logs`: SSE/stream of log lines and step events.
- `GET /artifacts/{run_id}/{file}`: Authenticated download (for PDFs/markdown/HTML).

## 5) Execution Flow (single + bulk)
- **Trigger**: Frontend “Process” button calls Vercel route → VPS `POST /jobs/run` for each selected row (or `run-bulk`).
- **Queue/Run**: Worker starts Docker container (image contains pipeline + `.env` mount). Container writes outputs under `applications/` and emits structured progress events (e.g., JSON lines per layer start/stop).
- **Streaming**: Runner tails container logs and forwards to SSE. UI subscribes with `run_id` to render live steps/logs.
- **Completion**: Worker converts CV markdown to HTML (render template) and to PDF (headless Chromium/Playwright for fidelity). Update Mongo job doc with paths/URLs + final status + scores.
- **UI**: Detail page fetches status/artifacts by `run_id`/`job_id`, shows CV HTML. User edits HTML (contenteditable or form-bound fields), saves updated HTML/markdown back to VPS, then triggers PDF regeneration for `CV.pdf` and `dossier.pdf`.

## 6) CV Editing/Export Approach (avoid canvas)
- Keep CV as semantic HTML + CSS; allow inline edits via `contenteditable` or structured form fields. Canvas is poor for text editing/searchability and complicates PDF quality.
- Export PDFs on VPS using Playwright/Chromium `page.pdf()` with `@page` rules and embedded fonts. Alternative client-only path: `html2canvas + jsPDF` (lower fidelity).
- Store both edited HTML and markdown (if needed for versioning). Regenerate PDFs after edits and update artifact URLs in Mongo.

## 7) Implementation Steps (phased)
1) **Dockerize pipeline**: Build image with repo + `.env` mount points; add entrypoint that accepts `job_id`/`profile_path` and writes logs to stdout + structured JSON events.
2) **Runner service on VPS**: FastAPI app with job enqueue/start, status store, SSE log streaming, artifact serving; wrap Docker CLI; add JWT auth + CORS.
3) **Queue + worker**: Plug Redis/RQ; implement bulk enqueue; ensure only N concurrent containers; add timeouts/retries; persist run metadata to Mongo.
4) **Artifacts**: Save outputs to disk + optional object storage; add HTML render + PDF export step post-run; expose signed download URLs.
5) **Frontend wiring (Vercel)**: Add “Process” buttons (single + multi-select) that hit Vercel API route → VPS. Add job detail view with status polling + SSE logs, CV HTML viewer/editor, and buttons to “Save edits”, “Export CV PDF”, “Export Dossier PDF”.
6) **Observability/ops**: Ship logs to file/Loki; health checks; backpressure on queue; alerts on failures. Keep LangSmith enabled for trace links if available.

## 8) Decisions / Defaults
- Concurrency cap: start with `MAX_CONCURRENCY=3` runner slots on the VPS; keep configurable via env.
- PDF path: **Server-side Playwright/Chromium** for CV/dossier export with `page.pdf()` and `@page` rules (primary). Client-only html2canvas/jsPDF remains fallback only.
- Render flow: CV stays as semantic HTML; edits captured via contenteditable/form, saved server-side, then regenerated to PDF with Playwright. Fonts embedded or bundled to keep fidelity.

## 8) Open Questions / Decisions
- Any GPU/CPU constraints beyond the 3-run cap? (adjust MAX_CONCURRENCY accordingly)
- Where should artifacts live (VPS disk vs. S3-compatible bucket)? Retention policy?
- Preferred auth between Vercel and VPS (JWT with shared secret vs. mTLS)?
- Should status updates also backfill into Mongo `level-2` docs (status, score, artifact URLs) for UI caching?

## 9) Development & Deployment Steps
- **Branch & image**: Add a Playwright-enabled Dockerfile for the pipeline + runner; build locally to validate PDF export and runtime deps.
- **Runner service**: Implement FastAPI endpoints (run, bulk run, status, SSE logs, artifacts) wrapping `docker run` of the pipeline image; enforce `MAX_CONCURRENCY=3` via worker config.
- **Queue & artifacts**: Add Redis/RQ worker, structured log events, post-run Playwright PDF generation for CV/dossier, and persist artifact URLs + status into Mongo.
- **Frontend wiring**: Add Vercel serverless proxy with JWT/shared secret → VPS runner; HTMX UI updates for process buttons, detail view, SSE log stream, CV edit/save/export buttons.
- **Deploy to VPS**: Use Docker Compose (runner + Redis). GitHub Actions workflow builds the runner image, pushes to registry, SSHes into VPS, runs `docker compose pull && docker compose up -d` to roll updates. Keep Vercel deploys via its own pipeline.
- **Ops/verification**: Add health checks, basic logging/rotation, and smoke tests (API run + PDF generation) in CI before deploy.

## 10) Current Runner State (VPS)
- Runner container is up and reachable; using `docker-compose.runner.temp.yml`, attached to the existing `n8n-prod_default` network and reusing the production Redis (`redis` alias at 172.18.0.5, DB 5). No new Redis is started now.
- Endpoints are stubbed: `_simulate_run` fakes progress/logs; no real pipeline execution or artifact serving yet.
- Port `8000` is exposed directly (not behind Traefik); `.env` on the runner host is currently empty and needs real pipeline secrets (Mongo, OpenAI, Firecrawl, etc.) before wiring the pipeline.
- Files on VPS live in `/root/job-runner` as a copy (not git-managed). Directory contains `runner_service/` (renamed from `runner-service`), `Dockerfile.runner`, and `docker-compose.runner.temp.yml`.
- Next actions: replace `_simulate_run` with the real pipeline invocation + stdout streaming + artifact URLs, populate `.env`, consider moving the runner to a git-managed path with CI/CD, and optionally expose via Traefik/HTTPS instead of raw port 8000.
