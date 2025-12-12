# Bug Fix & Feature Implementation Protocol

**When the user reports a bug, requests a feature, or asks a question, follow this decision tree and workflow.**

---

## Step 0: Classify the Request

| Type | Indicators | Action |
|------|------------|--------|
| **Information/Research** | "How does...", "What is...", "Explain...", "Where is..." | Answer directly or use `Explore` agent for codebase questions |
| **Architecture/Design** | "Should we...", "How should we architect...", "Design..." | → Go to Step 1 |
| **Bug Fix** | "X is broken", "Error when...", "Not working", stack traces | → Go to Step 1 |
| **Feature Request** | "Add...", "Implement...", "Build...", "Create..." | → Go to Step 1 |
| **Simple Task** | Single file edit, typo fix, small config change | Handle directly, skip to Step 5 |

---

## Step 1: Architecture Verification (Required for bugs & features)

**Use `job-search-architect` agent to:**
- Understand the correct/intended behavior
- Identify which components are involved
- Verify requirements against existing architecture
- Determine root cause (for bugs) or design approach (for features)

```
Prompt: "Analyze [issue/feature]. What is the expected behavior? Which components are involved? What's the correct architectural approach?"
```

---

## Step 2: Implementation (If substantial work needed)

**Route to the appropriate developer agent:**

| Domain | Agent | Examples |
|--------|-------|----------|
| Python, FastAPI, MongoDB, LangGraph, pipeline | `backend-developer` | API endpoints, pipeline nodes, data models |
| Flask templates, TipTap, Tailwind, HTMX | `frontend-developer` | UI components, styling, editor features |
| Cross-cutting, integration issues | `architecture-debugger` | Multi-component bugs, system failures |

```
Prompt: "Implement the fix/feature for [X] following the architecture recommendations from Step 1."
```

---

## Step 3: Write Tests

**Use `test-generator` agent to:**
- Write pytest tests covering the fix/feature
- Mock external dependencies (LLM, FireCrawl, MongoDB)
- Include edge cases identified during architecture review

```
Prompt: "Write tests for [component] covering [the fix/feature just implemented]."
```

---

## Step 4: Update Documentation

**Use `doc-sync` agent to:**
- Update `missing.md` if feature gaps were closed
- Update `architecture.md` if design changed
- Update relevant plan documents

```
Prompt: "Update documentation to reflect [changes made]."
```

---

## Step 5: Commit & Summarize

**Atomic commits (no Claude signature):**
```bash
# Run tests first
pytest -n auto tests/unit/

# Stage and commit atomically (one logical change per commit)
git add <specific-files>
git commit -m "fix(component): brief description"
```

**Final Summary Format:**
```
## Summary

**Root Cause:** [What was wrong / What was missing]

**Fix/Implementation:** [What was changed and why]

**Files Changed:**
- `path/to/file.py` - [what changed]

**Tests Added:** [test file names]

**Docs Updated:** [which docs]
```

---

## Quick Reference Flowchart

```
User Request
     │
     ▼
┌─────────────────┐
│ Classify Request│
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Simple    Complex
    │         │
    │    ┌────┴────────────────────────┐
    │    ▼                             │
    │  job-search-architect            │
    │  (verify architecture)           │
    │    │                             │
    │    ▼                             │
    │  backend-developer OR            │
    │  frontend-developer OR           │
    │  architecture-debugger           │
    │  (implement fix/feature)         │
    │    │                             │
    │    ▼                             │
    │  test-generator                  │
    │  (write tests)                   │
    │    │                             │
    │    ▼                             │
    │  doc-sync                        │
    │  (update docs)                   │
    │    │                             │
    └────┴─────────────────────────────┘
         │
         ▼
   Atomic Commits
   (run tests first, no Claude signature)
         │
         ▼
   Summary with Root Cause & Fix
```

---

## Agent Quick Reference

| Agent | Model | Primary Use |
|-------|-------|-------------|
| `job-search-architect` | opus | Architecture verification, requirements analysis |
| `backend-developer` | opus | Python, FastAPI, MongoDB, LangGraph, pipeline |
| `frontend-developer` | opus | Flask templates, TipTap, Tailwind, HTMX |
| `architecture-debugger` | opus | Cross-cutting bugs, integration issues |
| `test-generator` | sonnet | Writing pytest tests with mocks |
| `doc-sync` | haiku | Updating missing.md, architecture.md |
| `pipeline-analyst` | sonnet | Validating pipeline outputs, investigating failures |
| `session-continuity` | haiku | Start of session, context restoration |
