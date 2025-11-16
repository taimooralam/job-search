# CLAUDE.md

Guidance for using Claude Code with this repository.

## Current Context (16 Nov)
- Goal for today: ship a vertical slice of the 7-layer LangGraph pipeline (see `architecture.md`, `requirements.md`, `goal-16-nov.md`).
- Inputs: MongoDB jobs (see `sample.json` schema), partial candidate profile from LinkedIn/current CV (full knowledge graph coming later).
- Integrations: FireCrawl, OpenRouter (GPT-4/Anthropic), LangSmith, Google Drive/Sheets, MongoDB. All config via env vars; no secrets in code.

## Architecture Snapshot
- Orchestration: LangGraph nodes per layer (focus today on Layers 2–6: pain-point mining, company/role research, fit scoring, outreach + CV drafting). State passed explicitly; retries per node; error capture/logging.
- Outputs: Drive folder `/applications/<company>/<role>/` with outreach + CV drafts; tracker row in Sheets; run trace in LangSmith; status persisted in DB.

## Development Notes
- Style: PEP 8, typed functions, snake_case modules/functions; keep prompts/config declarative.
- Tests: Prefer pytest with `test_*.py`; mock FireCrawl/LLMs/Mongo for determinism.
- Config: Use env vars (`*.env`), never commit secrets; add `.env.example` placeholders.

## Claude Usage
- Provide focused help on prompts, LangGraph node design, and error handling.
- When suggesting code, keep secrets out, use env-driven config, and respect rate limits/ToS for scraping.
- If you propose changes, mention where they belong (e.g., `src/`, `tests/`, `docs/`). Use Drive/Sheets/LangSmith integration points from the context above.
