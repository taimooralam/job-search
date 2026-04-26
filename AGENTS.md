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

Windows bootstrap and interrupted VPS recovery notes:
- see `docs/current/operational-development-manual.md`
- especially the `2026-04-22 Windows Bootstrap And VPS Recovery Notes` section before any fresh-machine live validation or stage-resume session

For long local development or live-debug runs:
- do not run blind
- prefer outside-sandbox execution when real MongoDB, Codex, or live web research is required
- always use `.venv`
- always use `python -u`
- load `.env` from Python with an explicit path, not `source .env`
- use `MONGODB_URI` correctly
- enable verbose logs, stage heartbeats, and inner Codex PID/stdout/stderr heartbeat logging
- use the worker-compatible `StageContext` shape and checksum/snapshot construction
- make repo context opt-in, not default, for Codex preenrich stage runs
- default `jd_facts`, `classification`, `application_surface`, and `research_enrichment` to isolated temp cwd unless repo context is explicitly required
- for VPS / production / Codex-skill launches, preserve the same default isolation and only override with `PREENRICH_CODEX_WORKDIR_<STAGE>` when a stage deliberately needs a specific working directory

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

## Source-File Format Policy (4.3 soft JSON->YAML migration)

YAML is preferred for human-authored Codex / preenrich / manual-review source
files in the migrated 4.3 subset. JSON is preserved for the legacy
`layer6_v2` runner, machine artifacts, validator reports, deterministic
hashing, and external workflow payloads. There is no universal conversion.

- **YAML-first (canonical for new authoring path)**: `data/master-cv/candidate_facts.yml`,
  future `data/master-cv/{roles,projects}/<id>.meta.yml`, future
  `data/master-cv/taxonomies/*.yml`, future `data/eval/cv_assembly/*.yml`.
- **Dual-format (JSON kept for legacy runner, YAML mirror added for the new
  reader path)**: `data/master-cv/role_metadata.{json,yml}`,
  `data/master-cv/role_skills_taxonomy.{json,yml}`,
  `data/master-cv/projects/{commander4,lantern}_skills.{json,yml}`.
- **JSON only (do not convert)**: `data/eval/baselines/*.json`,
  `data/eval/scorecards/**/*.json`, all 4.2 stage outputs and validator
  reports, all 4.3.2+ `expected/*.json`, draft/grade/winner/synthesis
  outputs, MongoDB state dumps, `n8n/workflows/cv-upload.json`, and any
  artifact whose canonical hash is defined in JSON terms.

New Codex/eval/manual readers should use `src/common/structured_data.py`:
`resolve_preferred_path` / `load_preferred` for single files,
`discover_preferred_files` for `*_skills`-style asset families, and
`dump_yaml_file` for stable block-style writes. `canonical_json` and the
4.3.9 determinism harness are unaffected.

## File-Encoding Policy

All text-mode `open()`, `Path.read_text()`, and `Path.write_text()` calls
**must** pass `encoding="utf-8"` explicitly. Default platform encoding
(cp1252 on Windows) has silently produced `UnicodeDecodeError` and mojibake
when reading role markdown, master-CV JSON, and CV outputs. The project's
canonical encoding is utf-8 everywhere.

Enforced by ruff rule `PLW1514` (configured in `ruff.toml`). To check:

```
python -m ruff check --preview src/ scripts/ tests/
```

Auto-fix new violations:

```
python -m ruff check --preview --fix --unsafe-fixes src/ scripts/ tests/
```

The `--unsafe-fixes` label is conservative — for this project the
auto-applied `encoding="utf-8"` is correct in 100% of cases since all
source/data files are utf-8.
