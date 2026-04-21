Note: Codex will review your output once you are done.

# Repository Guidelines

## Skill Quick Reference

| Skill         | Use                                                                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `scout-jobs`  | Search LinkedIn for AI/engineering roles, score, and inject into pipeline                                                             |
| `inject-job`  | Inject a recruiter job description into MongoDB + run batch pipeline                                                                  |
| `ingest-prep` | Ingest job (new or existing by \_id), mark favorite, trigger pipeline, deep research + interview prep report in `../ai-engg/reports/` |
| `cv-review`   | Run bulk CV reviews locally via Codex CLI (gpt-5.2). Reviews generated CVs from a hiring manager's perspective.                       |
| `top-jobs`    | Query MongoDB for top jobs by tier, location, category, score, recency, and collection, with optional promotion and batch queueing.   |

Project-local Codex skills are stored under `.codex/skills/`.

## Commit Checklist (bugs/features)

- Tests written and passing
- Docs updated (`missing.md` or `architecture.md`) if behaviour changed
- Commit: `git status` clean

## Project Context

- Goal: Complete the Job Intelligence Pipeline (7-layer LangGraph) with professional CV editor
- Inputs: MongoDB jobs, candidate profile from master-cv.md
- Integrations: FireCrawl, OpenRouter, LangSmith, Google Drive/Sheets, MongoDB. All config via env vars; no secrets in code.

## Implementation Tracking

- **`missing.md`**: Tracks gaps between codebase and `ROADMAP.md`. Update after completing work.
- **Plans**: `plans/` directory
- **Reports**: `reports/` directory

## Development Setup

- Python environment: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Run all tests: `python -m pytest`
- Run specific layer: `pytest -k "layer2"` or specific test: `python scripts/test_layer2.py`
- Run workflow: `python -m scripts.run_pipeline`

## Project Structure

- LangGraph workflow in `src/workflow.py`, layer-specific code in `src/layerN/` modules
- Shared utilities in `src/common/`, CLI scripts in `scripts/`
- Test files follow `test_*.py` naming convention

## Coding Style

- Python: PEP 8 with type hints, docstrings on all public functions
- Imports order: stdlib → third-party → local (grouped, alphabetized)
- Classes: PascalCase, functions/variables: snake_case
- Use error handling with specific exceptions and error context
- Separate implementation classes from LangGraph node functions for testability

## Development Notes

- Use existing packages; don't reimplement
- Tests: pytest with `test_*.py`; mock external deps; run parallel: `pytest -n auto`
- Config: env vars only, never commit secrets
- Use `.venv` virtual environment
- Before committing: always run unit tests
- Atomic commits without Claude signature
- Fetch jobs with `_id` from MongoDB collection `level-2`, use .env for the connection string
- Skip integration and bulk tests when testing

## Long-Running Debug Sessions

Source of truth: **`docs/current/operational-development-manual.md`**

For long local development or live-debug runs:
- do not run blind
- prefer outside-sandbox execution when real MongoDB, Codex, or live web research is required
- always use `.venv`
- always use `python -u`
- load `.env` from Python with an explicit path, not `source .env`
- use `MONGODB_URI` correctly
- enable verbose logs, stage heartbeats, and inner Codex PID/stdout/stderr heartbeat logging
- use the worker-compatible `StageContext` shape and checksum/snapshot construction

When a long run appears stuck:
- inspect the live heartbeat first
- inspect the inner Codex PID and last output age
- do not assume silence means progress

## LLM Integration

- Use retry decorators with exponential backoff for all LLM calls
- Load API keys from environment variables via `config.py`
- Structure prompts as class constants for readability
- Parse and validate LLM responses before returning

## Security & Validation

- Never commit credentials or `.env` files (only `.env.example`)
- Sanitize all external inputs and validate response schemas
- Follow FireCrawl rate limiting guidelines for web scraping
- Redact PII and sensitive data before logging

## Quality Principles

- Bias toward quality over speed
- Prioritize correctness, hyper-personalization, hallucination control
- Ground outputs only in provided context; prefer "unknown" over guessing
- Make sources explicit in state

## Debugging Principle

**When user expresses frustration → SLOW DOWN.** Deep analysis, trace complete data flow, fix root cause correctly the first time.

## CV Generation Reference

Source of truth: **`docs/current/cv-generation-guide.md`**

- Pipeline architecture → Part 2, Data structures → Part 3, Scoring → Part 4
- Quality gates → Part 5, Role guidance → Part 6, ATS rules → Part 7
