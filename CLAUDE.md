# CLAUDE.md

Guidance for using Claude Code with this repository.

## Current Context

- Goal for today (18 Nov): complete the full of 7-layer LangGraph pipeline (see `architecture.md`, `requirements.md`, `ROADMAP.md`).
- Inputs: MongoDB jobs (see `sample.json` schema), partial candidate profile from LinkedIn/current CV (full knowledge graph coming later).
- Integrations: FireCrawl, OpenRouter (GPT-4/Anthropic), LangSmith, Google Drive/Sheets, MongoDB. All config via env vars; no secrets in code.

## Implementation Tracking

- **`missing.md`**: This file tracks all implementation gaps between the current codebase and `ROADMAP.md`. It's organized by phase and lists what's missing, partially implemented, or differs from the full roadmap spec.
- **IMPORTANT**: After completing any task or feature, **always check `missing.md`** and update it to mark items as complete or remove them from the gaps list. This ensures the tracking document stays current and we can quickly see what's left to implement.
- The deployment for the pipeline to VPS hostinger is in plans/deployment-plan.md.
- When reviewing progress, consult `missing.md` first to understand current state vs target state.

## Plans

- All the planning is done in the plans/ directory.
- Allt the reporting is done in the reports/ directory.

## Architecture Snapshot

- Orchestration: LangGraph nodes per layer (focus today on Layers 2–6: pain-point mining, company/role research, fit scoring, outreach + CV drafting). State passed explicitly; retries per node; error capture/logging.
- Outputs: Drive folder `/applications/<company>/<role>/` with outreach + CV drafts; tracker row in Sheets; run trace in LangSmith; status persisted in DB.

## Development Notes

- Style: PEP 8, typed functions, snake_case modules/functions; keep prompts/config declarative.
- Tests: Prefer pytest with `test_*.py`; mock FireCrawl/LLMs/Mongo for determinism.
- Config: Use env vars (`*.env`), never commit secrets; add `.env.example` placeholders.

## Claude Usage

- **Bias toward quality over speed.** When there is a trade-off, prioritize correctness, hyper-personalization, and hallucination control over implementation speed or throughput.
- Provide focused help on prompts, LangGraph node design, and error handling, with special attention to: (1) mapping job pain points to concrete STAR stories, and (2) JSON-only, schema-validated outputs for analytical layers.
- When suggesting code, keep secrets out, use env-driven config, and respect rate limits/ToS for scraping.
- Prefer designs that reduce hallucinations (grounding outputs only in provided context, encouraging "unknown" over guessing, and making sources explicit in state) even if they require slightly more code or complexity.
- If you propose changes, mention where they belong (e.g., `src/`, `tests/`, `docs/`). Use Drive/Sheets/LangSmith integration points from the context above.
- **After completing work**: Review and update `missing.md` to check off completed items and keep implementation tracking current.
- Use TDD approach to implementing the system
- whenever you run tests or python remember to use .venv virtual environment
- whenever you git commit, commit without claude signature
- whenever you git commit, plan atomic commits
- remember not to add claude signature to commits
- before committing always run unit tests
- when testing during development do not test integration or bulk tests