# Job Intelligence Architecture (Nov 2025)

Python-based LangGraph pipeline that assembles job-specific dossiers, outreach, and a tailored CV from MongoDB-stored job postings and a local master CV. The system runs as a CLI, a FastAPI runner service, and a lightweight Flask UI for browsing jobs.

## Execution Surfaces
- CLI: `python scripts/run_pipeline.py --job-id <id> [--profile path]` loads jobs from MongoDB (`level-2`/`level-1`) and runs the LangGraph workflow.
- Runner service (`runner_service/`): FastAPI wrapper that executes the CLI in a subprocess with log streaming, concurrency guard, and artifact lookup.
- Frontend (`frontend/app.py`): Flask + HTMX table over MongoDB for browsing/updating job records and statuses.

## Feature Flags & Defaults (`src/common/config.py`)
- `ENABLE_STAR_SELECTOR=false` → skip the STAR selector node; downstream layers fall back to master CV achievements.
- `DISABLE_FIRECRAWL_OUTREACH=true` → People Mapper uses role-based synthetic contacts and still generates outreach; FireCrawl discovery can be re-enabled.
- `ENABLE_REMOTE_PUBLISHING=false` → save all artifacts locally under `applications/<company>/<role>/`; Google Drive/Sheets is optional.
- `USE_OPENROUTER=false` by default; when true, CV generation uses the configured OpenRouter model.
- `CANDIDATE_PROFILE_PATH=./master-cv.md` is the canonical profile input for all layers.

## Pipeline (LangGraph in `src/workflow.py`)
1) **Pain-Point Miner (Layer 2, `src/layer2/pain_point_miner.py`)**  
   ChatOpenAI prompt returns JSON-only `pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics`; validated with Pydantic and retried with tenacity.
2) **STAR Selector (Layer 2.5, `src/layer2_5/star_selector.py`, optional)**  
   Parses `knowledge-base.md` via `star_parser`; LLM-only scoring across all STARs (no embeddings/graph/caching) to pick 2–3 STARs plus `star_to_pain_mapping`. Default disabled by flag; still exposes `all_stars` for downstream prompts.
3) **Company Researcher (Layer 3, `src/layer3/company_researcher.py`)**  
   FireCrawl searches official site, LinkedIn, Crunchbase, news, and the job URL; LLM extracts `CompanyResearch` (summary + signals with source URLs). Cached in Mongo `company_cache` with a 7-day TTL index and returned early on cache hits.
4) **Role Researcher (Layer 3.5, `src/layer3/role_researcher.py`)**  
   LLM generates role summary, business impact bullets, and “why now” using job description and company signals (optionally STAR context when available).
5) **Opportunity Mapper (Layer 4, `src/layer4/opportunity_mapper.py`)**  
   Produces `fit_score`, `fit_rationale`, `fit_category`. Warns (does not fail) when STAR metrics/citations are missing.
6) **People Mapper (Layer 5, `src/layer5/people_mapper.py`)**  
   When outreach scraping is disabled (default), generates synthetic primary/secondary contacts and fallback cover letters. When enabled, FireCrawl search + LLM classification (4–6 contacts per bucket) with outreach generation (LinkedIn/email) enforcing word counts, placeholder bans, and closing-line checks.
7) **Outreach Generator (Layer 6b, `src/layer6/outreach_generator.py`)**  
   Packages enriched contacts into `OutreachPackage` objects (LinkedIn + email per contact) with soft validation that messages cite companies from STARs or the master CV.
8) **Cover Letter & CV Generator (Layer 6a, `src/layer6/generator.py`)**  
   CoverLetterGenerator with multiple validation gates. MarkdownCVGenerator runs a two-pass JSON-evidence → QA flow using `master-cv.md`, job description, and research; saves `applications/<company>/<role>/CV.md` and returns `cv_reasoning`.
9) **Output Publisher (Layer 7, `src/layer7/output_publisher.py`)**  
   Builds dossier text (`layer7/dossier_generator.py`) and saves dossier, cover letter, contacts_outreach, fallback letters, and reuses the CV path under `applications/<company>/<role>/`. Optional Drive/Sheets upload when enabled. Updates the Mongo `level-2` record with fit analysis, cover letter, `cv_path/cv_reasoning`, selected STAR IDs, and contact names/roles; does not persist to `pipeline_runs`.

## Data & Storage
- **MongoDB**: Jobs live in `level-1`/`level-2` (loaded by the CLI). `company_cache` has a TTL index. `star_records`/`pipeline_runs` collections and indexes exist in `src/common/database.py` but the pipeline does not use them yet. Runner service can persist run status best-effort via `persistence.py`.
- **Filesystem**: `knowledge-base.md` (STAR source), `prompts/` for templates, outputs under `applications/`. No `.docx` generation; CVs are markdown.
- **State model**: `src/common/state.py` TypedDict is the authoritative runtime schema; it lacks tiering/application-form fields mentioned in older plans.

## External Services
- **LLM**: `langchain_openai.ChatOpenAI` for all layers; OpenRouter only for CV when enabled.
- **Scraping**: FireCrawl for company research (always used) and for contact discovery when outreach scraping is enabled.
- **Google APIs**: Drive/Sheets uploads are gated behind `ENABLE_REMOTE_PUBLISHING`.

## Reliability & Testing
- Tenacity retries around all LLM calls; CLI invokes `Config.validate()` before running. Logging is via `print` statements (no structured logger or metrics).
- Test coverage spans star parsing, layers 2–7, outreach packaging, and the runner service (unit + integration suites under `tests/`). GitHub Actions exist for the frontend and runner; no CI workflow runs the main pipeline tests.

## Not Implemented / Out-of-Scope Today
- Layer 1 job ingestion and Layer 1.5 application-form mining are not present in the pipeline or state.
- No STAR embeddings, hybrid selector, or knowledge-graph edges; no caching of STAR selection results.
- No tiered execution, batch runner, or scheduler; pipeline_runs collection is unused.
- Local outputs only by default; no structured logging, alerts, or cost tracking.
