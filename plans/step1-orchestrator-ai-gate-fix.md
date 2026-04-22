# Step 1: Orchestrator AI Gate Fix — Support `ai_leadership` Role Category

**Date:** 2026-04-12
**Priority:** CRITICAL — blocks all downstream AI role work
**Estimated time:** 2-3 hours

---

## Problem Statement

The orchestrator's AI gate (`src/layer6_v2/orchestrator.py` line 481-494) unconditionally overrides `role_category` to `"ai_architect"` for ALL AI-detected jobs. This means:

1. A "Head of AI" job that should be `ai_leadership` gets forced to `ai_architect`
2. The variant selector at `src/layer6_v2/variant_selector.py` line 405 only checks for `ai_architect`
3. The header generator loads persona from taxonomy using `role_category`, which means Head of AI jobs get the IC Architect persona instead of a leadership persona
4. The grader's `category_keywords` dict has no entry for `ai_architect` or `ai_leadership`
5. The title map at line 1581 only maps `ai_architect` → "AI Architect"

**Root cause:** The JD extractor's `RoleCategory` enum (`src/layer1_4/claude_jd_extractor.py` line 43) has only 8 base roles — it does NOT include `ai_architect` or `ai_leadership`. The AI gate was designed as a post-extraction override, but it doesn't distinguish between IC architect and leadership roles.

## Current Flow (Broken for Head of AI)

```
JD Extractor → role_category="head_of_engineering" (closest enum match for Head of AI)
     ↓
AI Gate (orchestrator.py:492) → is_ai=True → OVERRIDE to "ai_architect"
     ↓
Variant Selector → sees "ai_architect" → forces Achievement 15
     ↓
Header Generator → loads ai_architect persona → IC-focused taglines
     ↓
Grader → no ai_architect in category_keywords → falls through to empty list
```

## Target Flow (After Fix)

```
JD Extractor → role_category="head_of_engineering" (or "engineering_manager", etc.)
     ↓
AI Gate (orchestrator.py) → is_ai=True
     ↓  Check: is the original role_category a LEADERSHIP role?
     ↓  YES (head_of_engineering, director_of_engineering, vp_engineering, cto, engineering_manager)
     ↓     → override to "ai_leadership"
     ↓  NO (tech_lead, staff_principal_engineer, senior_engineer)
     ↓     → override to "ai_architect" (existing behavior)
     ↓
Variant Selector → sees "ai_leadership" OR "ai_architect" → forces Achievement 15 for both
     ↓
Header Generator → loads ai_leadership persona (leadership-focused taglines)
                   OR ai_architect persona (IC/architecture taglines)
     ↓
Grader → has entries for both in category_keywords
```

## Files to Change

### 1. `src/layer6_v2/orchestrator.py` — AI Gate Logic

**Location:** Lines 481-494

**Current code:**
```python
# AI Gate: Override role_category for AI/GenAI/LLM jobs
is_ai = should_include_ai_section(state)
# ... logging ...
if is_ai:
    extracted_jd["role_category"] = "ai_architect"
    self._logger.info("  AI job detected — using ai_architect role category")
```

**New code:**
```python
# AI Gate: Override role_category for AI/GenAI/LLM jobs
is_ai = should_include_ai_section(state)
# ... logging ...
if is_ai:
    # Distinguish leadership vs IC AI roles based on original role_category
    original_category = extracted_jd.get("role_category", "senior_engineer")
    leadership_categories = {
        "engineering_manager", "director_of_engineering",
        "head_of_engineering", "vp_engineering", "cto",
    }
    if original_category in leadership_categories:
        extracted_jd["role_category"] = "ai_leadership"
        self._logger.info(
            f"  AI leadership job detected (was {original_category}) — using ai_leadership role category"
        )
    else:
        extracted_jd["role_category"] = "ai_architect"
        self._logger.info(
            f"  AI IC job detected (was {original_category}) — using ai_architect role category"
        )
```

**Also update the struct log (line 490):**
```python
ai_override = None
if is_ai:
    original_category = extracted_jd.get("role_category", "senior_engineer")
    ai_override = "ai_leadership" if original_category in leadership_categories else "ai_architect"

self._emit_struct_log("ai_classification", {
    "is_ai_job": is_ai,
    "ai_categories": state.get("ai_categories", []),
    "role_category": extracted_jd.get("role_category"),
    "role_category_override": ai_override,
})
```

### 2. `src/layer6_v2/orchestrator.py` — Title Map

**Location:** Line 1571-1583

**Add `ai_leadership` entry:**
```python
title_map = {
    # ... existing entries ...
    "ai_architect": "AI Architect",
    "ai_leadership": "Head of AI",  # NEW
}
```

### 3. `src/layer6_v2/variant_selector.py` — Achievement 15 Constraint

**Location:** Line 404-405

**Current:**
```python
if role_category == "ai_architect" and role.id == "01_seven_one_entertainment":
```

**New:**
```python
if role_category in ("ai_architect", "ai_leadership") and role.id == "01_seven_one_entertainment":
```

### 4. `src/layer6_v2/variant_selector.py` — Variant Priority Order

**Location:** Line 55-68

**Add `ai_leadership` entry:**
```python
# AI roles - emphasize technical depth and innovation
"ai_architect": ["Technical", "Architecture", "Innovation", "Impact"],
"ai_leadership": ["Leadership", "Architecture", "Technical", "Impact"],  # NEW — leadership first

# Default fallback
"default": ["Technical", "Impact", "Architecture", "Short"],
```

### 5. `src/layer6_v2/grader.py` — Category Keywords

**Location:** Line 378-384

**Add entries:**
```python
category_keywords = {
    "engineering_manager": ["team", "led", "managed", "hired", "mentored"],
    "staff_principal_engineer": ["architecture", "designed", "technical", "system"],
    "director_of_engineering": ["built", "multiple", "organization", "scaled", "strategy"],
    "head_of_engineering": ["built", "function", "executive", "transformation"],
    "cto": ["vision", "board", "technology", "business", "transformation"],
    # NEW entries:
    "ai_architect": ["architecture", "designed", "llm", "ai", "evaluation", "production", "scale", "platform"],
    "ai_leadership": ["led", "team", "ai", "platform", "architecture", "governance", "built", "scale"],
}
```

### 6. `src/layer6_v2/grader.py` — Executive Presence Adjustment

**Location:** Line 449

**Current:**
```python
if role_category in ["cto", "head_of_engineering", "director_of_engineering"]:
```

**New:**
```python
if role_category in ["cto", "head_of_engineering", "director_of_engineering", "ai_leadership"]:
```

### 7. `src/layer6_v2/header_generator.py` — Value Proposition Template

**Location:** Around line 998 (in the VALUE_PROPOSITION_TEMPLATES dict in `prompts/header_generation.py`)

**Add `ai_leadership` entry:**
```python
"ai_leadership": {
    "formula": "[Hands-on AI leader] building [AI platforms] with [X years] production systems + [team building/governance].",
    "examples": [
        "Hands-on AI leader with 11+ years building production platforms — from LLM gateway design to AI governance at enterprise scale.",
        "AI platform leader bridging distributed systems architecture with team building and AI governance.",
    ],
    "emphasis": ["team building", "AI platform architecture", "governance", "production reliability"],
},
```

### 8. `src/layer6_v2/skills_taxonomy.py` — Role Taxonomy Fallback

**No change needed** — if `ai_leadership` is not in the taxonomy JSON, `get_role_taxonomy()` falls back to the default role. Once we add `ai_leadership` to the taxonomy JSON (Step 4 from main plan), it will be picked up automatically.

However, verify the fallback is correct by checking that the taxonomy loader at line 130-134 gracefully handles missing roles.

## Test Plan

### Unit Tests

```python
# test_orchestrator_ai_gate.py

def test_ai_gate_leadership_role():
    """Head of AI job → ai_leadership category."""
    state = {"ai_categories": ["genai", "llm"]}
    extracted_jd = {"role_category": "head_of_engineering", "title": "Head of AI Engineering"}
    # Simulate: should_include_ai_section returns True
    # After gate: extracted_jd["role_category"] == "ai_leadership"

def test_ai_gate_ic_role():
    """AI Architect job → ai_architect category (unchanged behavior)."""
    state = {"ai_categories": ["genai"]}
    extracted_jd = {"role_category": "senior_engineer", "title": "AI Solutions Architect"}
    # After gate: extracted_jd["role_category"] == "ai_architect"

def test_ai_gate_engineering_manager():
    """Engineering Manager + AI → ai_leadership."""
    state = {"ai_categories": ["llm"]}
    extracted_jd = {"role_category": "engineering_manager", "title": "AI Engineering Manager"}
    # After gate: extracted_jd["role_category"] == "ai_leadership"

def test_ai_gate_tech_lead():
    """Tech Lead + AI → ai_architect (IC track)."""
    state = {"ai_categories": ["genai"]}
    extracted_jd = {"role_category": "tech_lead", "title": "AI Tech Lead"}
    # After gate: extracted_jd["role_category"] == "ai_architect"

def test_non_ai_job_unchanged():
    """Non-AI job → role_category unchanged."""
    state = {}
    extracted_jd = {"role_category": "engineering_manager", "title": "Engineering Manager"}
    # After gate: extracted_jd["role_category"] == "engineering_manager" (no change)
```

### Integration Tests (Manual)

Run pipeline on 3 real jobs from MongoDB:
1. **Head of AI job** — verify role_category="ai_leadership" in logs, leadership-first variant ordering, header has leadership framing
2. **AI Architect job** — verify role_category="ai_architect" unchanged, achievement 15 forced, technical-first variant ordering
3. **Non-AI Engineering Manager** — verify role_category unchanged, no AI override

### Regression Check

Re-run on 3 previously generated CVs for AI Architect jobs. Output should be identical (no regression from adding the leadership branch — existing ai_architect path unchanged).

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `ai_leadership` not in taxonomy JSON yet → falls back to default (engineering_manager) | Acceptable for Phase 1. Full taxonomy added in Step 4. |
| Variant selector change could affect existing AI Architect CVs | No — we're adding `ai_leadership` to the condition, not removing `ai_architect`. |
| Some "Head of AI" jobs may be classified as `senior_engineer` by extractor | The AI gate already handles this — it overrides. The new logic only checks the original category. |
| Grader category_keywords for `ai_leadership` may not cover all Head of AI JD terms | Start with core terms, iterate based on grading results. |

## Success Criteria

1. Head of AI jobs get `role_category="ai_leadership"` after AI gate
2. AI Architect jobs still get `role_category="ai_architect"` (no regression)
3. Non-AI jobs are completely unaffected
4. Variant selector forces Achievement 15 for both `ai_architect` and `ai_leadership`
5. Grader has category keywords for both new role categories
6. Title map returns "Head of AI" for `ai_leadership`
7. All existing unit tests pass
