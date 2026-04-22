# Plan: Claude Code Skills & Rules System

**Created**: 2026-01-24
**Status**: Draft
**Priority**: P1 - Improve Claude Code Efficiency

---

## Overview

Establish a modular, maintainable system for Claude Code instructions using:
- **Skills** (`.claude/skills/`): Reusable procedural knowledge triggered by slash commands
- **Rules** (`.claude/rules/`): Path-specific instructions that auto-apply based on file patterns

```
.claude/
├── agents/              # Existing - 13 specialized agents
├── skills/              # NEW - Reusable procedures
│   ├── cv-validator/
│   ├── star-bullet/
│   ├── company-research/
│   └── thought-processor/
├── rules/               # NEW - Path-specific instructions
│   ├── cv-generation.md
│   ├── langgraph.md
│   ├── testing.md
│   └── mongodb.md
├── settings.json
├── settings.local.json
└── statusline.py
```

---

## Part 1: Skills System

### What Are Skills?

Skills are **procedural knowledge packages** that:
- Are triggered by slash commands (e.g., `/validate-cv`)
- Contain step-by-step instructions
- Can include reference files and scripts
- Auto-reload when modified (hot-reload)
- Have progressive disclosure (only metadata loaded initially)

### Skill Structure

```
.claude/skills/{skill-name}/
├── skill.md           # Main instructions (required)
├── *.md               # Additional reference files
└── scripts/           # Optional executable scripts
    └── *.py
```

### Skills to Create

#### 1. CV Validator Skill (`/validate-cv`)

**Purpose**: Validate CV content against ATS rules and master CV for hallucination prevention.

```
.claude/skills/cv-validator/
├── skill.md           # Main validation workflow
├── ats-rules.md       # ATS optimization checklist
└── scripts/
    └── check_keywords.py  # Keyword density checker
```

**skill.md content:**
```markdown
---
name: cv-validator
description: Validate CV against ATS rules and master CV for hallucination prevention
trigger: /validate-cv
---

# CV Validator

You are an ATS compliance and anti-hallucination validator.

## Workflow

### Step 1: Load Context
- Read `docs/current/cv-generation-guide.md`
- Read `docs/current/ats-guide.md`
- Read all files in `data/master-cv/roles/`

### Step 2: ATS Validation
Check these rules:

| Rule | Check |
|------|-------|
| No tables | Search for `|` table syntax |
| Standard headers | Summary, Experience, Skills, Education |
| Keyword placement | Keywords in first 100 chars of bullets |
| Acronym expansion | First use expanded: "AI (Artificial Intelligence)" |
| Date format | Consistent MMM YYYY |
| No special chars | Replace em-dashes, smart quotes |

### Step 3: Hallucination Check
For each claim in the CV:
1. Search master-cv files for supporting evidence
2. Flag any ungrounded claims
3. Verify metrics match exactly

### Step 4: Output Report
```markdown
## Validation Results

### ATS Score: X/10
- [x] Passing checks
- [ ] Failing checks with fixes

### Hallucination Score: X/10
- Grounded claims: X
- Ungrounded claims: X (list with line numbers)

### Recommended Fixes
1. [Specific fix]
2. [Specific fix]
```
```

#### 2. STAR Bullet Writer Skill (`/star-bullet`)

**Purpose**: Generate STAR-format achievement bullets from raw input.

```
.claude/skills/star-bullet/
├── skill.md
├── cars-framework.md  # CARS variation for technical roles
└── examples.md        # Few-shot examples by role category
```

**skill.md content:**
```markdown
---
name: star-bullet
description: Generate STAR-format achievement bullets grounded in master CV
trigger: /star-bullet
---

# STAR Bullet Writer

Transform raw achievement descriptions into polished STAR-format bullets.

## Input Format
User provides:
- Role context (which role in master CV)
- Raw achievement description
- Target job category (optional)

## STAR Framework

| Component | Description | Example |
|-----------|-------------|---------|
| **S**ituation | Context, challenge faced | "When video traffic spiked 300%..." |
| **T**ask | Your responsibility | "...I was tasked with scaling infrastructure..." |
| **A**ction | Specific actions YOU took | "...implemented Redis caching, optimized queries..." |
| **R**esult | Quantified outcome | "...reducing latency by 65% and costs by $2M annually." |

## Rules

1. **Grounding**: Only use facts from master CV files
2. **Metrics**: Always include numbers (%, $, time, scale)
3. **Action verbs**: Start with strong verbs (Led, Architected, Reduced, Scaled)
4. **Length**: 1-2 sentences, max 25 words
5. **Keywords**: Include relevant technical keywords for ATS

## Output Format

```
**Original**: [user input]

**STAR Bullet**:
[Polished bullet]

**Components**:
- S: [situation]
- T: [task]
- A: [action]
- R: [result with metrics]

**Source**: [master-cv file:line]
```
```

#### 3. Thought Processor Skill (`/process-thoughts`)

**Purpose**: Process voice memos and notes from thoughts/inbox.

```
.claude/skills/thought-processor/
├── skill.md
└── categories.md      # How to categorize different thought types
```

**skill.md content:**
```markdown
---
name: thought-processor
description: Process thoughts from inbox, create tasks, update relevant files
trigger: /process-thoughts
---

# Thought Processor

Process captured thoughts from `thoughts/inbox/` and route them appropriately.

## Workflow

### Step 1: Read Inbox
- Read all `.md` files in `thoughts/inbox/`
- Parse each thought for intent and content

### Step 2: Categorize Each Thought

| Category | Indicators | Action |
|----------|------------|--------|
| **Achievement** | "I did", "accomplished", metrics | Add to master-cv role |
| **Task** | "need to", "should", "todo" | Create in plans/ |
| **Idea** | "what if", "could we", "idea:" | Add to plans/raw_thoughts.md |
| **Bug** | "broken", "not working", error | Create issue/task |
| **Research** | "look into", "investigate" | Add to research queue |

### Step 3: Execute Actions

For each thought:
1. Determine category
2. Execute appropriate action
3. Log what was done

### Step 4: Archive
- Move processed files to `thoughts/processed/`
- Add timestamp to filename

### Step 5: Report
```markdown
## Processed Thoughts

| File | Category | Action Taken |
|------|----------|--------------|
| 2026-01-24-0915.md | Achievement | Added to 01_seven_one.md |
| 2026-01-24-1030.md | Task | Created in plans/todo.md |

**Files moved to processed/**: 2
```
```

#### 4. Company Research Skill (`/research-company`)

**Purpose**: Deep research a company for interview prep.

```
.claude/skills/company-research/
├── skill.md
├── research-template.md
└── interview-questions.md
```

---

## Part 2: Rules System

### What Are Rules?

Rules are **contextual instructions** that:
- Auto-apply based on file path patterns
- Are modular and maintainable
- Don't require explicit triggering
- Supplement (not replace) CLAUDE.md

### Rule Structure

```markdown
---
paths:
  - "src/layer6/**/*.py"
  - "data/master-cv/**/*"
---

# Rule Title

[Instructions that apply when working with matched files]
```

### Rules to Create

#### 1. CV Generation Rules

**File**: `.claude/rules/cv-generation.md`

```markdown
---
paths:
  - "src/layer6/**/*.py"
  - "src/cv_pipeline/**/*.py"
  - "data/master-cv/**/*"
  - "docs/current/cv-*.md"
---

# CV Generation Rules

## Source of Truth
Always consult `docs/current/cv-generation-guide.md` before modifying CV generation code.

## STAR Bullet Format
Every achievement bullet MUST follow:
- **S**ituation: Context (1-2 words)
- **T**ask: What was required
- **A**ction: What YOU did (use strong verbs)
- **R**esult: Quantified outcome (%, $, time saved)

## ATS Optimization
- No tables, columns, or graphics
- Standard section headers: Summary, Experience, Skills, Education
- Keywords in first 1/3 of bullet text
- Expand acronyms on first use

## Hallucination Prevention
- ONLY cite achievements from `data/master-cv/` files
- If achievement not found, respond "Not found in master CV"
- Never fabricate metrics or company names

## Code Patterns
When modifying CV generation code:
- Use Pydantic models for all structured output
- Validate against `CVSection` schema
- Include source attribution in generated content
```

#### 2. LangGraph Pipeline Rules

**File**: `.claude/rules/langgraph.md`

```markdown
---
paths:
  - "src/workflow.py"
  - "src/layer*/**/*.py"
  - "src/common/state.py"
---

# LangGraph Pipeline Rules

## State Management
- All state changes via `JobState` TypedDict
- Never use global state
- Pass state explicitly between nodes

## Node Patterns
```python
def node_name(state: JobState) -> JobState:
    # 1. Extract needed state
    job_id = state["job_id"]

    # 2. Do work
    result = process(...)

    # 3. Return updated state (spread existing)
    return {**state, "new_field": result}
```

## Error Handling
- Use `tenacity` for retries on external calls
- Propagate errors via state, don't raise
- Log to StructuredLogger, not print()

## Layer Dependencies
```
Layer 1.4 (JD) → Layer 2 (Pains) → Layer 2.5 (STAR)
                       ↓
              Layer 3 (Company) → Layer 3.5 (Role)
                       ↓
              Layer 4 (Opportunity) → Layer 5 (People)
                       ↓
              Layer 6 (Generator) → Layer 7 (Publisher)
```
```

#### 3. Testing Rules

**File**: `.claude/rules/testing.md`

```markdown
---
paths:
  - "tests/**/*.py"
---

# Testing Rules

## Execution
- Always run tests in parallel: `pytest -n auto tests/unit/`
- Skip integration tests unless explicitly requested
- Mock ALL external dependencies (LLM, FireCrawl, MongoDB)

## Test Naming
- File: `test_{module_name}.py`
- Function: `test_{function}_{scenario}_{expected}`
- Example: `test_cover_letter_missing_pains_raises_error`

## Mocking Patterns
```python
# LLM mocking
@patch("src.common.llm_factory.create_tracked_chat")
def test_with_mocked_llm(mock_llm):
    mock_llm.return_value.invoke.return_value = AIMessage(content="...")

# MongoDB mocking
@pytest.fixture
def mock_mongo():
    with patch("pymongo.MongoClient") as mock:
        yield mock
```

## Coverage
- New features: >80% coverage
- Bug fixes: Include regression test
```

#### 4. MongoDB Rules

**File**: `.claude/rules/mongodb.md`

```markdown
---
paths:
  - "src/common/mongodb*.py"
  - "src/**/mongo*.py"
  - "scripts/*mongo*.py"
---

# MongoDB Rules

## Collections Reference
| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `level-2` | Job postings | `_id`, `status`, `extracted_jd` |
| `company_cache` | Company research | `company_name`, `cached_at` |
| `star_records` | Achievement bullets | `role_id`, `bullets` |

## Query Patterns
- Always use `_id` for lookups
- Include timeout on all operations
- Use projections to limit returned fields

## Caching
- Company research: 7-day TTL
- Check cache before external API calls
```

---

## Implementation Plan

### Phase 1: Create Directory Structure (5 min)

```bash
mkdir -p .claude/skills/{cv-validator,star-bullet,thought-processor,company-research}
mkdir -p .claude/rules
```

### Phase 2: Create Rules (30 min)

1. Create `cv-generation.md` rule
2. Create `langgraph.md` rule
3. Create `testing.md` rule
4. Create `mongodb.md` rule

### Phase 3: Create Skills (1-2 hours)

1. Create `cv-validator/skill.md`
2. Create `star-bullet/skill.md`
3. Create `thought-processor/skill.md`
4. Create `company-research/skill.md`

### Phase 4: Test & Iterate (30 min)

1. Test each skill with `/skill-name`
2. Verify rules apply when editing matched files
3. Adjust based on behavior

---

## Validation Checklist

- [ ] Skills trigger correctly with slash commands
- [ ] Rules auto-apply when editing matched paths
- [ ] Skills hot-reload when modified
- [ ] No conflicts between rules and CLAUDE.md
- [ ] Agent workflow still functions correctly

---

## Benefits

| Current State | With Skills/Rules |
|---------------|-------------------|
| Monolithic CLAUDE.md | Modular, maintainable files |
| Manual workflow | Slash command triggers |
| Same instructions everywhere | Path-specific guidance |
| Hard to share patterns | Reusable skill packages |
| Full context always loaded | Progressive disclosure |
