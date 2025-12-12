# CLAUDE.md

## ⚠️ MANDATORY WORKFLOW - READ BEFORE ANY ACTION ⚠️

**STOP. DO NOT PROCEED WITHOUT FOLLOWING THIS WORKFLOW.**

Before responding to ANY user request, you MUST:

1. **CLASSIFY** the request using the table below
2. **DELEGATE** to the appropriate agent (do NOT handle bugs/features yourself)
3. **NEVER** read code directly for bugs or features - always use agents first

**VIOLATION OF THIS WORKFLOW IS NOT ACCEPTABLE.**

---

### Step 0: Classify the Request (ALWAYS DO THIS FIRST)

| Type | Indicators | Action |
|------|------------|--------|
| **Information/Research** | "How does...", "What is...", "Explain...", "Where is..." | Answer directly or use `Explore` agent |
| **Architecture/Design** | "Should we...", "How should we architect...", "Design..." | → **DELEGATE to `job-search-architect`** |
| **Bug Fix** | "X is broken", "Error when...", "Not working", stack traces | → **DELEGATE to `job-search-architect`** |
| **Feature Request** | "Add...", "Implement...", "Build...", "Create..." | → **DELEGATE to `job-search-architect`** |
| **Simple Task** | Single file edit, typo fix, small config change | Handle directly, skip to Step 5 |

**IF YOU SEE A BUG REPORT OR FEATURE REQUEST → DELEGATE FIRST, ASK QUESTIONS NEVER**

---

### Step 1: Architecture Verification (REQUIRED for bugs & features)

**Use `job-search-architect` agent FIRST to:**
- Understand the correct/intended behavior
- Identify which components are involved
- Verify requirements against existing architecture
- Determine root cause (for bugs) or design approach (for features)

```
Example prompt: "Analyze [issue/feature]. What is the expected behavior? Which components are involved? What's the root cause / correct approach?"
```

---

### Step 2: Implementation (After architecture verification)

**Route to the appropriate developer agent:**

| Domain | Agent | Examples |
|--------|-------|----------|
| Python, FastAPI, MongoDB, LangGraph, pipeline | `backend-developer` | API endpoints, pipeline nodes, data models |
| Flask templates, TipTap, Tailwind, HTMX, JavaScript | `frontend-developer` | UI components, styling, editor features |
| Cross-cutting, integration issues | `architecture-debugger` | Multi-component bugs, system failures |

---

### Step 3: Write Tests

**Use `test-generator` agent to:**
- Write pytest tests covering the fix/feature
- Mock external dependencies (LLM, FireCrawl, MongoDB)
- Include edge cases identified during architecture review

---

### Step 4: Update Documentation

**Use `doc-sync` agent to:**
- Update `missing.md` if feature gaps were closed
- Update `architecture.md` if design changed
- Update relevant plan documents

---

### Step 5: Commit & Summarize

**⚠️ MANDATORY CHECKLIST - DO NOT SKIP ⚠️**

Before providing any summary, you MUST complete ALL of these for bugs/features:

| Step | Requirement | How to Verify |
|------|-------------|---------------|
| ✅ Tests | `test-generator` agent was used | Test file exists and all tests pass |
| ✅ Docs | `doc-sync` agent was used | `missing.md` or `architecture.md` was updated |
| ✅ Commit | Changes are committed | `git status` shows clean working tree |

**DO NOT provide a summary with empty checklist fields. If a step was skipped, go back and complete it.**

**Atomic commits (no Claude signature):**
```bash
# Run tests first
pytest -n auto tests/unit/

# Stage and commit atomically (one logical change per commit)
git add <specific-files>
git commit -m "fix(component): brief description"
```

**Final Summary Format (ALL FIELDS REQUIRED):**
```
## Summary

**Root Cause:** [What was wrong / What was missing]

**Fix/Implementation:** [What was changed and why]

**Files Changed:**
- `path/to/file.py` - [what changed]

## Workflow Checklist
- [x] Tests: `path/to/test_file.py` (X tests passing)
- [x] Docs: `missing.md` updated
- [x] Commits: `abc1234` - "commit message"

**INCOMPLETE CHECKLIST = INCOMPLETE TASK. Go back and finish.**
```

---

### Quick Reference Flowchart

```
User Request
     │
     ▼
┌─────────────────┐
│ CLASSIFY FIRST! │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Simple    Bug/Feature/Design
    │         │
    │         ▼
    │    ┌─────────────────────────────────┐
    │    │ job-search-architect            │ ← ALWAYS START HERE
    │    │ (verify architecture)           │
    │    └────────────┬────────────────────┘
    │                 ▼
    │    ┌─────────────────────────────────┐
    │    │ backend-developer OR            │
    │    │ frontend-developer OR           │
    │    │ architecture-debugger           │
    │    │ (implement fix/feature)         │
    │    └────────────┬────────────────────┘
    │                 ▼
    │    ┌─────────────────────────────────┐
    │    │ test-generator                  │
    │    │ (write tests)                   │
    │    └────────────┬────────────────────┘
    │                 ▼
    │    ┌─────────────────────────────────┐
    │    │ doc-sync                        │
    │    │ (update docs)                   │
    │    └────────────┬────────────────────┘
    │                 │
    └────────┬────────┘
             ▼
       Atomic Commits
       (run tests first, no Claude signature)
             │
             ▼
    ┌─────────────────────────────────┐
    │ ⚠️ MANDATORY CHECKLIST          │
    │ Before summary, verify:         │
    │ ✅ Tests created & passing      │
    │ ✅ Docs updated                 │
    │ ✅ Changes committed            │
    │ INCOMPLETE = GO BACK            │
    └────────────┬────────────────────┘
                 │
                 ▼
       Summary with Checklist
```

---

### Agent Quick Reference

| Agent | Model | Primary Use |
|-------|-------|-------------|
| `job-search-architect` | opus | **START HERE** for bugs/features - architecture verification |
| `backend-developer` | opus | Python, FastAPI, MongoDB, LangGraph, pipeline |
| `frontend-developer` | opus | Flask templates, TipTap, Tailwind, HTMX, JavaScript |
| `architecture-debugger` | opus | Cross-cutting bugs, integration issues |
| `test-generator` | sonnet | Writing pytest tests with mocks |
| `doc-sync` | haiku | Updating missing.md, architecture.md |
| `pipeline-analyst` | sonnet | Validating pipeline outputs, investigating failures |
| `session-continuity` | haiku | Start of session, context restoration |

---

### Example: Correct Workflow for a Bug Report

```
User: "There is a bug - TypeError: variations.map is not a function"

STEP 0 - CLASSIFY:
- Contains "bug", "TypeError", stack trace
- This is a BUG FIX → DELEGATE TO AGENT

STEP 1 - ARCHITECTURE:
- Delegate to job-search-architect
- "Analyze this TypeError in master-cv-editor.js. What component is involved?
   What data structure is expected? What's the root cause?"

STEP 2 - IMPLEMENT:
- Based on architect's analysis, delegate to frontend-developer
- "Fix the variations.map bug following the architecture analysis"

STEP 3-5 - Tests, Docs, Commit
```

**WRONG APPROACH (DO NOT DO THIS):**
```
User: "There is a bug..."
Claude: *immediately reads code files*  ← WRONG! Delegate first!
```

---

## Project Context

- Goal: Complete the Job Intelligence Pipeline (7-layer LangGraph) with professional CV editor
- Inputs: MongoDB jobs, candidate profile from master-cv.md
- Integrations: FireCrawl, OpenRouter, LangSmith, Google Drive/Sheets, MongoDB. All config via env vars; no secrets in code.

## Implementation Tracking

- **`missing.md`**: Tracks implementation gaps between codebase and `ROADMAP.md`
- **After completing work**: Always update `missing.md` to mark items complete
- **Plans**: All planning in `plans/` directory
- **Reports**: All reporting in `reports/` directory

## Development Notes

- Use existing packages instead of implementing yourself
- Style: PEP 8, typed functions, snake_case
- Tests: pytest with `test_*.py`; mock external dependencies
- **Run tests in parallel**: `pytest -n auto` or `pytest -n 14`
- Config: Use env vars, never commit secrets
- Use `.venv` virtual environment for Python
- Before committing: always run unit tests
- Atomic commits without Claude signature
- Fetch jobs with `_id` from MongoDB collection `level-2`
- When testing, skip integration and bulk tests

## Quality Principles

- **Bias toward quality over speed**
- Prioritize correctness, hyper-personalization, hallucination control
- Ground outputs only in provided context
- Encourage "unknown" over guessing
- Make sources explicit in state
