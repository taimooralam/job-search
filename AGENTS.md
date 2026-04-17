# Repository Guidelines

## Request Classification (ALWAYS DO THIS FIRST)

| Type | Indicators | Action |
|------|------------|--------|
| **Information/Research** | "How does...", "What is...", "Explain..." | Answer directly or use `Explore` agent |
| **Architecture/Design** | "Should we...", "How should we architect..." | Delegate to `job-search-architect` |
| **Bug Fix** | "X is broken", "Error when...", stack traces | Delegate to `job-search-architect` |
| **Feature Request** | "Add...", "Implement...", "Build...", "Create..." | Delegate to `job-search-architect` |
| **Simple Task** | Single file edit, typo, null check, config change, obvious fix, < 3 files | Handle directly |
| **Medium Task** | Multi-file change, non-obvious bug | architect → developer |
| **Complex Task** | New feature, architecture change, pipeline modification | Full chain: architect → developer → test-generator → doc-sync |

## Workflow Steps (bugs & features)

1. **Architecture**: `job-search-architect` → verify behavior, identify components, determine root cause/approach
2. **Implement**: Route to `backend-developer` (Python/FastAPI/MongoDB/LangGraph) or `frontend-developer` (Flask/HTMX/Tailwind/JS) or `architecture-debugger` (cross-cutting)
3. **Test**: `test-generator` → pytest tests with mocked external deps
4. **Docs**: `doc-sync` → update `missing.md`, `architecture.md`
5. **Commit**: Run tests first, atomic commits, no Claude signature

## Agent Quick Reference

| Agent | Model | Use |
|-------|-------|-----|
| `job-search-architect` | opus | Architecture verification for bugs/features |
| `backend-developer` | sonnet | Python, FastAPI, MongoDB, LangGraph, pipeline |
| `frontend-developer` | sonnet | Flask templates, TipTap, Tailwind, HTMX, JS |
| `architecture-debugger` | sonnet | Cross-cutting bugs, integration issues |
| `test-generator` | sonnet | Writing pytest tests with mocks |
| `doc-sync` | haiku | Updating missing.md, architecture.md |
| `pipeline-analyst` | sonnet | Validating pipeline outputs |
| `session-continuity` | haiku | Context restoration |

## Skill Quick Reference

| Skill | Use |
|-------|-----|
| `scout-jobs` | Search LinkedIn for AI/engineering roles, score, and inject into pipeline |
| `inject-job` | Inject a recruiter job description into MongoDB + run batch pipeline |
| `ingest-prep` | Ingest job (new or existing by _id), mark favorite, trigger pipeline, deep research + interview prep report in `../ai-engg/reports/` |
| `cv-review` | Run bulk CV reviews locally via Codex CLI (gpt-5.2). Reviews generated CVs from a hiring manager's perspective. |
| `top-jobs` | Query MongoDB for top jobs by tier, location, category, score, recency, and collection, with optional promotion and batch queueing. |

Project-local Codex skills are stored under `.codex/skills/`.

## Commit Checklist (bugs/features)

- Tests: `test-generator` used, tests pass
- Docs: `doc-sync` used, `missing.md` or `architecture.md` updated
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
