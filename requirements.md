# Requirements Blueprint

## Overview & Goals
- Purpose: Single-candidate job search copilot that ingests scraped jobs from MongoDB, runs the 7-layer LangGraph pipeline, and drafts tailored outreach + CV bundles.
- Goals: Automate end-to-end prep for quality applications; create Drive folders per company/role with drafts; log runs; target 50 qualified jobs/day with matched cover letters and CVs ready to send.
- Today’s objective: ship a simple, working vertical slice (ingest → analyze → generate → store/log) with manual review before sending.

## Scope
- In-scope now: Read jobs from MongoDB (existing schema), run Layers 2–6 (pain-point mining, company research via FireCrawl, fit scoring, outreach + CV tailoring), store outputs to Drive, log to Sheets, trace with LangSmith. Basic retries and manual approval gates.
- Out-of-scope for now: New job sources beyond current DB, production-grade scheduling, advanced People Mapper (Layer 5), automated sending, heavy RBAC/tenanting.

## Users & Personas
- Primary user: the candidate (you) running the pipeline locally/CLI; success = high-quality, application-ready artifacts with minimal editing.

## Functional Requirements
- Job ingestion: Pull queued jobs from MongoDB (`jobId`/`dedupeKey` as uniqueness), process one-by-one or small batches.
- Analysis layers: Pain-point mining, company/role research (FireCrawl + LLM), opportunity mapping/fit scoring per `architecture.md`.
+- Generation: Outreach email/cover letter and tailored CV using the candidate knowledge graph (initially partial: LinkedIn + current CV; later full master resume graph).
- Data storage: Persist run metadata to DB; write artifacts to Google Drive in `/applications/<company>/<role>/`; log summary to Google Sheets tracker.
- Integrations: FireCrawl, OpenRouter (OpenAI/Anthropic models), LangSmith tracing, MongoDB, Google Drive/Sheets. No secrets in code; env-driven config.
- Control & overrides: Manual review/approve before sending; ability to rerun a job; skip/resume failed steps; capture errors per layer.

## Non-Functional Requirements
- Reliability: Retries on API calls; resumable/durable execution per LangGraph where possible.
- Performance: Throughput target = 50 jobs/day; acceptable per-job latency if end-to-end < ~5 minutes when inputs are cached.
- Security & Privacy: Keep PII and resumes redacted in logs; secrets in env only; avoid uploading raw scraped resumes/job posts.
- Compliance: Respect source site terms; throttle FireCrawl; avoid aggressive scraping.
- Observability: LangSmith tracing enabled by default; minimal structured logs for layer entry/exit.

## Data & Models
- Input contracts: Job schema per `sample.json` (title, company, description, criteria, URLs, embeddings, score); candidate profile as structured knowledge graph + current CV/LinkedIn fields.
- Model selection: Default GPT-4 class via OpenRouter; Anthropic as optional fallback; set cost/latency budgets per layer.
- Versioning: Tag prompts/models per layer and record in LangSmith; track schema changes in git + `architecture.md`.

## UX & Outputs
- Formats: Outreach email/cover letter text, tailored CV (.docx or PDF), tracker row entry. Tone: professional, specific to pain points/company.
- Review loop: Human review/edits before any sending; all drafts stored in Drive with timestamps.

## Acceptance Criteria
- Given a MongoDB job (from existing corpus), pipeline produces pain points, company summary, fit score, and drafts outreach + tailored CV saved to Drive and logged to Sheets; LangSmith captures the run trace; no secrets hard-coded.

## Risks & Open Questions
- Full candidate knowledge graph not finalized; interim data may reduce personalization quality.
- Google API quotas/consent need to be configured; FireCrawl rate limits and scraping blocks possible.
- Decide on automated scheduling vs. manual runs after the first vertical slice. 
