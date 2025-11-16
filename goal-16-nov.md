# 16 Nov Goal: Ship Vertical Slice

## Objective
Deliver a working slice of the 7-layer LangGraph pipeline today: pull jobs from MongoDB, run pain-point mining + company research + fit scoring, generate outreach and a tailored CV draft, store outputs in Google Drive, log to Sheets, and capture traces in LangSmith.

## Constraints & Inputs
- Data: Existing MongoDB jobs (`sample.json` schema; `jobId`/`dedupeKey` for uniqueness), partial candidate profile from LinkedIn/current CV (full knowledge graph later).
- Integrations: FireCrawl, OpenRouter (GPT-4/Anthropic), LangSmith, Google Drive/Sheets, MongoDB. All config via env; no secrets in code.
- Target throughput: 50 jobs/day eventually; accept per-job latency <~5 min with caching/retries.

## Architecture Notes
- Orchestration: LangGraph nodes per layer (2–6) with explicit state passing; retries on API/tool calls; error capture per node; manual review gate before any send.
- Data contracts: Use `sample.json` fields as input contract; outputs include pain points, company summary, fit score, outreach text, tailored CV draft, run metadata.
- Versioning/observability: Tag prompts/models per layer; LangSmith tracing on by default.

## Step-by-Step Plan (Today)
1) Ingestion: Node to read N queued jobs from MongoDB, dedupe, and hydrate state.
2) Pain-Point Miner: LLM prompt on job description to extract key challenges/requirements.
3) Company Researcher: FireCrawl fetch + LLM summary of company/role context.
4) Opportunity Mapper: Map candidate profile to pain points; compute fit score and rationale.
5) Generator: Draft outreach email/cover letter and tailored CV variant using current profile; timestamp outputs.
6) Publisher: Write drafts to Drive at `/applications/<company>/<role>/`, log row to Sheets, persist run status in DB, emit LangSmith trace.
7) Review Control: Mark runs pending review; allow rerun/skip on failure; no auto-send today.

## Acceptance Today
- For a MongoDB job, pipeline produces pain points, company summary, fit score, outreach draft, and tailored CV draft; saves to Drive; logs to Sheets; LangSmith trace recorded; no secrets hard-coded.
