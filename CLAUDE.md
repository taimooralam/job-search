# CLAUDE.md

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

## Development Notes

- Use existing packages; don't reimplement
- Style: PEP 8, typed functions, snake_case
- Tests: pytest with `test_*.py`; mock external deps; run parallel: `pytest -n auto`
- Config: env vars only, never commit secrets
- Use `.venv` virtual environment
- Before committing: always run unit tests
- Atomic commits without Claude signature
- Fetch jobs with `_id` from MongoDB collection `level-2`
- Skip integration and bulk tests when testing

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
