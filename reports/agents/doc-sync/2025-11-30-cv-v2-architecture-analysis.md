# Architecture Analysis: CV V2 Generation & Markdown Formatting Issue

**Date**: 2025-11-30
**Agent**: Doc Sync (Haiku 4.5)
**Focus**: System design review for markdown formatting problem
**Type**: Technical Analysis

---

## Overview

Analysis of the CV V2 generation architecture (`src/layer6_v2/`) to understand where markdown formatting is introduced and how to properly fix it without breaking the existing pipeline.

---

## Architecture Context

### Layer 6 V2: Six-Phase CV Generation Pipeline

```
Phase 1: CV Loader
  └─> Phase 2: Per-Role Generator
       └─> Phase 3: Role QA (Hallucination checking)
            └─> Phase 4: Stitcher (Combine roles + deduplication)
                 └─> Phase 5: Header Generator (Profile + Skills)
                      └─> Phase 6: Grader & Improver (Quality feedback)
                           └─> OUTPUT: Final CV (Plain Text)
```

### Current Data Flow

```
Source Files (master-cv/roles/*.md)
  ↓
RoleData (dataclass with company, title, achievements, skills)
  ↓
RoleGenerator.generate() → RoleBullets (with GeneratedBullet items)
  ↓
RoleQA.run() → Validated RoleBullets
  ↓
CVStitcher.stitch() → StitchedCV (with StitchedRole items)
  ↓
HeaderGenerator.generate() → HeaderOutput (ProfileOutput + SkillsSection)
  ↓
CVGrader.grade() → GradeResult (quality assessment)
  ↓
CVImprover.improve() → ImprovementResult
  ↓
[OUTPUT] CV Text → Database/Display
```

---

## Where Markdown is Introduced

### Source 1: LLM Generation (Implicit)

**Files**: `src/layer6_v2/prompts/*.py`

**Issue**: Prompts don't explicitly forbid markdown formatting

**Examples of LLM-generated markdown**:
```
From LLM response:
{
  "text": "Led **platform transformation** of microservices",
  "source_text": "Transformed legacy monolith to microservices",
  ...
}
```

**Why it happens**:
- LLMs trained on markdown-heavy corpora (GitHub, docs, etc.)
- Markdown is natural output format for LLMs
- No explicit "output plain text only" instruction

**Files**:
- `src/layer6_v2/prompts/role_generation.py` (ROLE_GENERATION_SYSTEM_PROMPT)
- `src/layer6_v2/prompts/header_generation.py` (profile/skills prompts)
- `src/layer6_v2/prompts/grading_rubric.py` (improvement suggestions)

---

### Source 2: Code-Level Markdown Formatting

**File**: `src/layer6_v2/types.py`

**Methods Adding Markdown**:

#### StitchedRole.to_markdown() (Line 353-362)

```python
def to_markdown(self) -> str:
    """Convert to markdown format for CV output."""
    lines = [
        f"### {self.company}",              # Header (markdown)
        f"**{self.title}** | {self.location} | {self.period}",  # BOLD (markdown)
        "",
    ]
    for bullet in self.bullets:
        lines.append(f"• {bullet}")         # Bullet list
    return "\n".join(lines)
```

**Issue**: Adds `**` around title, `###` headers

#### SkillsSection.to_markdown() (Line 466-469)

```python
def to_markdown(self) -> str:
    """Convert to markdown format for CV output."""
    skill_names = ", ".join(self.skill_names)
    return f"**{self.category}**: {skill_names}"  # BOLD (markdown)
```

**Issue**: Adds `**` around category name

#### Other `to_markdown()` Methods

- ProfileOutput.to_markdown() (likely around line 500+)
- Other dataclasses in types.py may also add markdown

**Method Naming Issue**:
- Methods are called `to_markdown()` suggesting markdown output is expected
- But final CV output should be plain text, not markdown
- Contradiction between method name and use case

---

### Source 3: Missing Post-Processing

**File**: `src/layer6_v2/orchestrator.py`

**Issue**: No sanitization step between generation and output

**Current Pipeline** (lines 94-200+):
```python
def generate(self, state: JobState) -> Dict[str, Any]:
    # ... CV loading ...
    # ... Per-role generation ...
    # ... Stitching ...
    # ... Header generation ...
    # ... Grading ...
    # ... Improvement ...
    # [OUTPUT] → Return CV text directly
    # NO SANITIZATION STEP
```

**Gap**: Generated CV (potentially containing markdown from LLM + code) is returned as-is

---

## Data Flow: Where Markdown Accumulates

```
INPUT: Job Description
  ↓
[LLM generates bullets with potential **markdown**]
  ↓
RoleBullets (may contain: "Led **platform** transformation")
  ↓
[RoleQA validation - doesn't strip markdown]
  ↓
StitchedRole.to_markdown()
  ├─> Adds `###` for company
  ├─> Adds `**title**` for role
  └─> Includes bullets with internal markdown
  ↓
StitchedCV (double markdown: from LLM + code)
  ↓
HeaderGenerator.generate()
  ├─> Profile may have LLM markdown: "Led **transformation**"
  └─> SkillsSection adds `**category**`
  ↓
Final CV Output
  ├─> `### Seven.One Entertainment Group` (header markdown)
  ├─> `**Technical Lead**` (code-added bold)
  ├─> Achievement bullets with internal markdown: `**platform**`, `**Kubernetes**`
  ├─> `**Leadership**: ...` (code-added bold)
  └─> No opportunity to strip - output as-is

OUTPUT: CV with LAYERED MARKDOWN
  - From LLM: "**transformation**"
  - From code: "**Technical Lead**"
  - From code: "**Leadership**: ..."
```

---

## Why This Matters for the Fix

### Approach 1: Prompt-Only Fix (Insufficient)
- Add "no markdown" to prompts
- Problem: Code still adds `**` via `to_markdown()` methods
- Result: Still have markdown in output

### Approach 2: Code-Only Fix (Better)
- Remove markdown from `to_markdown()` methods
- Remove `**` from SkillsSection.to_markdown()
- Problem: LLM might still generate markdown
- Risk: Users see `**` in their achievements (just not in headers)

### Approach 3: Multi-Layer Fix (BEST)
1. **Prompt enhancement** (prevent LLM markdown)
2. **Sanitization** (catch anything that slips through)
3. **Code cleanup** (optional: rename methods, clarify intent)

---

## Implementation Design Implications

### Key Decision: Method Naming

**Current**: `to_markdown()` method adds markdown syntax
**Problem**: Confuses intent - output should be plain text, not markdown
**Options**:

**Option A: Keep method name, update implementation**
- Rename implementation goal
- `to_markdown()` calls internal sanitization
- Backward compatible
- But confusing (method name suggests markdown output)

**Option B: Rename to `to_plain_text()`**
- Clear intent
- Breaking change (need to update all callers)
- Better for long-term code clarity

**Option C: Add new method, deprecate old**
- `to_plain_text()` for new code
- `to_markdown()` stays (redirects to sanitized version)
- Gradual migration
- Safest approach

**Recommendation**: Start with Option A (keep method names, just remove markdown), then refactor to Option B/C if time allows.

---

## Integration Points

### Where to Apply Sanitization

**Option 1: Early (at RoleBullets level)**
```python
# In RoleGenerator
generated_bullets = [sanitize_markdown(b) for b in bullets]
```
Pros: Catches markdown early
Cons: May need multiple sanitization passes

**Option 2: At Stitcher output**
```python
# In CVStitcher.stitch()
stitched = StitchedCV(...)
return sanitize_cv_output(stitched.to_markdown())
```
Pros: Single sanitization point before output
Cons: Happens after code-level markdown added

**Option 3: In Orchestrator (safest)**
```python
# In CVGeneratorV2.generate()
final_cv = improvement_result.text
return sanitize_cv_output(final_cv)
```
Pros: Last chance to clean up (both LLM and code markdown)
Cons: Slightly late in pipeline

**Recommendation**: Option 3 (orchestrator level) - catches everything, safest fallback

---

## Testing Strategy Implications

### Unit Tests Needed

1. **Markdown Sanitizer Tests**
   - Test each markdown pattern individually
   - Test combinations
   - Test edge cases (nested, consecutive, etc.)
   - ~15-20 test cases

2. **Integration Tests**
   - Generate CV from test JD
   - Assert no markdown in output
   - Assert structure preserved

3. **Regression Tests**
   - Existing 622+ tests should pass unchanged
   - No performance impact
   - No data loss

### Test Data Considerations

**Sample CV with markdown** (before sanitization):
```
### **Seven.One Entertainment Group**
**Technical Lead** | Berlin | 2021-2024

• Led **platform transformation** involving **3 teams**
• Designed **microservices architecture** using **Kubernetes**

**Technical Skills**: **AWS**, **Kubernetes**, **Go**
**Leadership Skills**: **Team Building**, **Mentorship**
```

**Expected output** (after sanitization):
```
### Seven.One Entertainment Group
Technical Lead | Berlin | 2021-2024

• Led platform transformation involving 3 teams
• Designed microservices architecture using Kubernetes

Technical Skills: AWS, Kubernetes, Go
Leadership Skills: Team Building, Mentorship
```

---

## Backwards Compatibility Considerations

### Will This Break Anything?

**Current Users**: None (CV v2 in development)
**Risk**: LOW - This is new pipeline, no existing users depend on markdown format

**Existing Tests**: 622 unit tests
- Most mock LLM calls
- Don't depend on markdown format
- Sanitization is non-breaking change

**Recommendation**: Safe to implement without extensive compatibility work

---

## Code Quality Implications

### Before Fix

```
Types.py: to_markdown() adds markdown syntax
Prompts: Don't forbid markdown
Orchestrator: Returns output as-is
Result: User gets unwanted markdown
```

### After Fix

```
Types.py: to_markdown() returns plain text (or stripped markdown)
Prompts: Explicitly forbid markdown
Sanitizer: Strip any remaining markdown
Orchestrator: Sanitizes before return
Result: User gets clean plain text
```

### Code Clarity Improvement

- Method names align with actual output (plain text, not markdown)
- Sanitizer is explicit about its job
- Prompts are explicit about expectations
- Pipeline is clear and defensible

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Sanitizer removes non-markdown asterisks | Low | Medium | Regex patterns carefully designed |
| Break existing functionality | Low | High | All 622 tests must pass |
| Incomplete sanitization | Medium | High | Multi-layer approach ensures coverage |
| Performance impact | Very Low | Low | String operations are fast |
| Upstream dependencies affected | Low | Medium | No external systems depend on markdown |

---

## Performance Considerations

### Sanitization Overhead

```python
text = "Company: **name** Role: **title** ..."
# Regex operations on 1000-char string
# Cost: < 1ms per operation
# For 10 CV operations: ~10ms overhead
# Negligible impact
```

**Performance**: Not a concern for this fix

---

## Architecture Recommendations

### Short-term (Current Fix)

1. Add prompt guardrails (no code changes to architecture)
2. Add sanitization at orchestrator output (minimal intrusion)
3. Leave `to_markdown()` methods as-is (reduce breaking changes)

### Long-term (Future Refactoring)

1. Rename `to_markdown()` → `to_plain_text()` (clarify intent)
2. Consider whether markdown output is ever needed for this pipeline
3. Unify all output paths through single sanitization point
4. Add type hints for "sanitized text" vs "raw text"

---

## Code Locations Summary

### Immediate Changes Needed

| File | Lines | Change | Reason |
|------|-------|--------|--------|
| `prompts/role_generation.py` | 14, 196 | Add no-markdown guardrail | Prevent LLM markdown |
| `prompts/header_generation.py` | 50+, 100+ | Add no-markdown guardrail | Prevent LLM markdown |
| `common/markdown_sanitizer.py` | NEW | Create sanitization module | Remove markdown |
| `layer6_v2/orchestrator.py` | 200+ | Apply sanitization | Clean final output |

### Optional Future Changes

| File | Lines | Change | Reason |
|------|-------|--------|--------|
| `types.py` | 353-405 | Rename `to_markdown()` → `to_plain_text()` | Clarify intent |
| `types.py` | ALL | Remove markdown syntax from implementations | Align with intent |

---

## Conclusion

The markdown formatting issue stems from three independent sources:
1. LLM default markdown behavior (prompt level)
2. Code-level markdown in `to_markdown()` methods (implementation level)
3. Lack of post-processing sanitization (pipeline level)

The fix requires all three layers for robustness:
- Layer 1 prevents markdown at source
- Layer 2 catches what slips through
- Layer 3 is a safety net

Architecture remains sound; fix requires no major redesign. Implementation is straightforward and low-risk.
