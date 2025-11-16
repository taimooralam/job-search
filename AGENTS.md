# Repository Guidelines

## Project Structure & Module Organization
- Current artifacts live at the repo root: `ChatGPT.md` (workflow summary), `CLAUDE.md` (agent notes), `sample.json` (sanitized job record example), and saved research assets. Keep new code under `src/` with one module per LangGraph node/layer, shared utilities in `src/common`, and CLI entry points in `scripts/`.
- Place tests in `tests/` mirroring the `src/` hierarchy; fixtures for scraped or generated job data belong in `tests/fixtures/` with sensitive details removed.
- Add design docs or diagrams to `docs/` and keep per-layer README files close to the code when behavior needs quick orientation.

## Build, Test, and Development Commands
- Set up a virtual environment (`python -m venv .venv && source .venv/bin/activate`) and install dependencies from `requirements.txt` once it is committed.
- Run `python -m pytest` for unit/integration coverage; use `pytest -k <pattern>` to target a single layer or node.
- If you introduce Make or task runners, prefer `make lint`, `make test`, and `make run` wrappers so contributors have one-line entry points; update this file when commands change.

## Coding Style & Naming Conventions
- Python: follow PEP 8 with 4-space indents, type hints on all public functions, snake_case modules/functions, PascalCase classes. Keep functions small and composable per LangGraph node.
- Data/JSON examples should use lowercase keys with underscores; redact PII and credentials before committing.
- Prefer declarative configs (YAML/JSON) for pipeline wiring and API endpoints; avoid hard-coding secrets.

## Testing Guidelines
- Use pytest with `test_*.py` naming. Co-locate integration tests per layer (e.g., `tests/layer3/test_company_researcher.py`) and mock external services (FireCrawl, OpenAI, MongoDB) to keep runs deterministic.
- Include regression tests for scoring, routing rules, and schema validations; add fixtures that mirror `sample.json` shape.

## Commit & Pull Request Guidelines
- Write imperative, concise commits (e.g., "Add layer3 company researcher node"). Squash noisy WIP commits before sharing.
- PRs should describe intent, list key changes, call out affected layers, and note test scope/outputs. Link issues/tasks and attach before/after samples for generated text when relevant.
- Update `ChatGPT.md` or add a short `docs/` note if you change architecture, data contracts, or external integrations.

## Security & Configuration Tips
- Load API keys and MongoDB URIs from environment variables; commit a `.env.example` only. Never check secrets or raw scraped resumes/job posts into the repo.
- Respect source site terms when scraping; throttle/firecrawl responsibly and log fetch metadata to aid auditing.
