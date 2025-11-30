# CLAUDE.md

Guidance for using Claude Code with this repository.

## Agent Delegation System

**IMPORTANT**: This project uses specialized subagents. Before starting work, reason about which agent is best suited for the task.

### Available Agents

| Agent | Model | When to Use |
|-------|-------|-------------|
| `session-continuity` | haiku | Start of session, context lost, need project briefing |
| `job-search-architect` | sonnet | System design, requirements analysis, architecture decisions |
| `pipeline-analyst` | sonnet | After pipeline runs, validating outputs, investigating failures |
| `test-generator` | sonnet | Writing tests after implementing features |
| `doc-sync` | haiku | Updating missing.md, architecture.md after work |
| `frontend-developer` | sonnet | TipTap editor, Tailwind UI, Flask templates |
| `architecture-debugger` | sonnet | Cross-cutting bugs, integration issues, system failures |

### Delegation Decision Tree

```
User Request
    │
    ├─ "Brief me / where were we?" ──────────→ session-continuity
    │
    ├─ "Design / architect / how should we..." ──→ job-search-architect
    │
    ├─ "Check pipeline / validate outputs" ───→ pipeline-analyst
    │
    ├─ "Write tests for..." ─────────────────→ test-generator
    │
    ├─ "Update docs / mark as complete" ─────→ doc-sync
    │
    ├─ "Build UI / implement editor" ────────→ frontend-developer
    │
    ├─ "Debug / fix / why is X failing" ─────→ architecture-debugger
    │
    └─ Simple/direct tasks ──────────────────→ Handle directly (no agent)
```

### Delegation Rules

1. **Always reason first**: Before delegating, think about which agent is best suited
2. **Don't over-delegate**: Simple tasks (read a file, make a small edit) don't need agents
3. **Chain agents when needed**: Complex work may need multiple agents sequentially
4. **Trust agent outputs**: Agents are specialized; incorporate their recommendations
5. **Proactive delegation**: Use agents without being asked when the situation fits

### Example Reasoning

```
User: "I just implemented the CV editor, what's next?"

Reasoning:
- User completed a feature → need to update documentation
- Should use doc-sync to update missing.md
- Then could use test-generator to write tests
- No need for architecture discussion (feature already built)

Action: Delegate to doc-sync first, then test-generator
```

## Current Context

- Goal: Complete the Job Intelligence Pipeline (7-layer LangGraph) with professional CV editor
- Inputs: MongoDB jobs, candidate profile from master-cv.md
- Integrations: FireCrawl, OpenRouter, LangSmith, Google Drive/Sheets, MongoDB. All config via env vars; no secrets in code.

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

- Whenever a package is available that is reliable, use the package and don't implement yourself. e.g. use the json parser package instead of implementing json parsing.
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
- whenever fetching a job fetch it with _id from the jobs database in MongoDB from the collection named level-2

