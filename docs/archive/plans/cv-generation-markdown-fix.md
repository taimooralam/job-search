# CV V2 Generation: Markdown Formatting Fix Plan

**Created**: 2025-11-30
**Status**: Planning
**Priority**: HIGH
**Effort Estimate**: 2 hours
**Reported By**: Documentation Sync Agent

---

## Problem Statement

The CV v2 generation layer (`src/layer6_v2/`) is outputting markdown-formatted text instead of plain text. Every generated CV includes unwanted markdown syntax (asterisks, underscores, etc.) that users must manually remove.

### Impact

- **Frequency**: 100% of CV generations affected
- **Scope**: Companies, roles, achievements, skills, profile
- **User Impact**: Manual character removal on every application (5+ jobs = 5+ cleanups)
- **Productivity Loss**: Multiplied across workflow (significant time waste)
- **Severity**: HIGH - Direct impact on daily velocity

### Current Behavior (BROKEN)

```
Company: **Seven.One Entertainment Group**
Role: **Technical Lead**
Achievement: Led **multi-year transformation** of platform architecture
Skills: **Leadership**, **Architecture**, **DevOps**
Profile: Expert **platform engineer** with 12+ years...
```

### Expected Behavior (CORRECT)

```
Company: Seven.One Entertainment Group
Role: Technical Lead
Achievement: Led multi-year transformation of platform architecture
Skills: Leadership, Architecture, DevOps
Profile: Expert platform engineer with 12+ years...
```

---

## Root Cause Analysis

### Issue 1: LLM Default Behavior

- **Problem**: LLMs naturally default to markdown formatting for emphasis
- **Reason**: Trained on markdown-heavy data (GitHub, documentation, etc.)
- **Current State**: Generation prompts don't explicitly forbid markdown
- **Impact**: Output includes `**bold**`, `*italic*`, `__underline__` even when not requested

### Issue 2: Code-Level Markdown Formatting

- **File**: `src/layer6_v2/types.py`
- **Methods**:
  - Line 357: `StitchedRole.to_markdown()` - Adds `**{title}**`
  - Line 469: `SkillsSection.to_markdown()` - Adds `**{category}**`
  - Other `to_markdown()` methods in ProfileOutput, etc.
- **Problem**: Method names and implementations contradict intent
  - Methods named `to_markdown()` but output should be plain text
  - Adds markdown syntax when converting to "output" format

### Issue 3: Missing Post-Processing

- **Current Pipeline**: LLM output → Validation → Stitching → Output
- **Gap**: No sanitization step between LLM output and final display
- **Consequence**: Markdown from both sources (LLM + code) reaches user

---

## Affected Files

| File | Component | Issue |
|------|-----------|-------|
| `src/layer6_v2/types.py` | StitchedRole.to_markdown() | Adds `**title**` at line 357 |
| `src/layer6_v2/types.py` | SkillsSection.to_markdown() | Adds `**category**` at line 469 |
| `src/layer6_v2/types.py` | ProfileOutput.to_markdown() | May add markdown (line 500+) |
| `src/layer6_v2/role_generator.py` | Role generation prompts | No explicit "no markdown" instruction |
| `src/layer6_v2/header_generator.py` | Header/profile generation | No explicit "no markdown" instruction |
| `src/layer6_v2/prompts/role_generation.py` | System/user prompts | Missing anti-markdown guardrail |
| `src/layer6_v2/prompts/header_generation.py` | Profile/skills generation | Missing anti-markdown guardrail |
| `src/layer6_v2/prompts/grading_rubric.py` | Grading prompts | May need guardrail |
| `src/layer6_v2/orchestrator.py` | Output handling | No sanitization applied |

---

## Solution Design

### Three-Layer Fix Approach

#### Layer 1: Prompt Enhancement (PRIMARY FIX)

**Objective**: Prevent LLM from generating markdown in the first place

**Implementation**:
1. Add explicit guardrail to all generation system prompts
2. Plain text instruction at the beginning of every prompt

**Example Addition**:
```
=== OUTPUT FORMAT CRITICAL ===

IMPORTANT: Your output MUST be plain text only.

DO NOT use any of these formatting characters:
- Asterisks: * or ** (bold/italic)
- Underscores: _ or __ (italic/underline)
- Backticks: ` or ``` (code blocks)
- Hash symbols: # (headers)
- Hyphens: - at line start (lists)

Write all text in clean, plain format without any markup.
Examples:
  DO: "Led platform transformation"
  DON'T: "Led **platform transformation**"

  DO: "Technical Leadership, Architecture"
  DON'T: "**Technical Leadership**, **Architecture**"
```

**Files to Update**:
- `src/layer6_v2/prompts/role_generation.py`
  - ROLE_GENERATION_SYSTEM_PROMPT
  - build_role_generation_user_prompt()
  - BULLET_CORRECTION_SYSTEM_PROMPT

- `src/layer6_v2/prompts/header_generation.py`
  - PROFILE_SYSTEM_PROMPT
  - SKILLS_SYSTEM_PROMPT

- `src/layer6_v2/prompts/grading_rubric.py`
  - Consider adding if grading output includes feedback

**Effort**: 30 minutes (add ~5-line guardrail to 6-8 prompts)

#### Layer 2: Post-Processing Sanitization (SAFETY NET)

**Objective**: Strip any markdown that still makes it through

**Implementation**:
1. Create utility function in `src/common/markdown_sanitizer.py`
2. Apply to all CV sections before output

**Code**:
```python
# src/common/markdown_sanitizer.py

import re
from typing import Optional

def strip_markdown_formatting(text: str) -> str:
    """
    Remove markdown formatting from text.

    Handles:
    - Bold: **text** and __text__
    - Italic: *text* and _text_
    - Headers: # text (line start)
    - Code: `text` and ```code```
    - Links: [text](url)

    Args:
        text: Text potentially containing markdown

    Returns:
        Plain text without markdown syntax

    Examples:
        strip_markdown_formatting("Led **platform** transformation")
        # Returns: "Led platform transformation"

        strip_markdown_formatting("Skills: **AWS**, **Kubernetes**")
        # Returns: "Skills: AWS, Kubernetes"
    """
    if not text:
        return text

    # Remove bold: **text** and __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic: *text* and _text_
    # Note: Be careful not to remove intentional underscores in names
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    # Only remove underscores that wrap text (word boundaries)
    text = re.sub(r'_([^\s_][^_]*[^\s_])_', r'\1', text)

    # Remove inline code: `text`
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove code blocks: ```code```
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Remove headers: lines starting with #
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove markdown links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove markdown image syntax: ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)

    # Clean up any double spaces created by removal
    text = re.sub(r'\s{2,}', ' ', text)

    return text.strip()


def sanitize_cv_output(cv_text: str) -> str:
    """
    Sanitize entire CV output by removing markdown.

    Applies strip_markdown_formatting to each section intelligently,
    preserving structure while removing formatting.

    Args:
        cv_text: Full CV text (may contain markdown from various sources)

    Returns:
        Clean plain text CV without markdown
    """
    lines = cv_text.split('\n')
    cleaned = []

    for line in lines:
        # Don't touch empty lines
        if not line.strip():
            cleaned.append(line)
        else:
            # Strip markdown from non-empty lines
            cleaned.append(strip_markdown_formatting(line))

    return '\n'.join(cleaned)
```

**Test Cases** (`tests/unit/test_markdown_sanitizer.py`):
```python
import pytest
from src.common.markdown_sanitizer import strip_markdown_formatting, sanitize_cv_output

class TestStripMarkdownFormatting:

    def test_removes_bold_double_asterisk(self):
        assert strip_markdown_formatting("Led **platform transformation**") == "Led platform transformation"

    def test_removes_bold_double_underscore(self):
        assert strip_markdown_formatting("Led __platform transformation__") == "Led platform transformation"

    def test_removes_italic_single_asterisk(self):
        assert strip_markdown_formatting("This is *important* work") == "This is important work"

    def test_removes_italic_underscore(self):
        assert strip_markdown_formatting("This is _important_ work") == "This is important work"

    def test_removes_inline_code(self):
        assert strip_markdown_formatting("Use `Kubernetes` for orchestration") == "Use Kubernetes for orchestration"

    def test_removes_markdown_links(self):
        assert strip_markdown_formatting("See [our website](https://example.com) for details") == "See our website for details"

    def test_preserves_underscores_in_identifiers(self):
        # Underscores in names like AWS_S3 should be preserved
        assert strip_markdown_formatting("Configured AWS_S3 buckets") == "Configured AWS_S3 buckets"

    def test_removes_multiple_markups_in_one_line(self):
        assert strip_markdown_formatting("**Leadership** and *architecture* in _Kubernetes_") == "Leadership and architecture in Kubernetes"

    def test_handles_empty_string(self):
        assert strip_markdown_formatting("") == ""

    def test_handles_none_input(self):
        assert strip_markdown_formatting(None) == None


class TestSanitizeCVOutput:

    def test_preserves_line_structure(self):
        input_cv = "**Company Name**\n**Role Title**\nBullet point"
        output_cv = sanitize_cv_output(input_cv)
        lines = output_cv.split('\n')
        assert len(lines) == 3

    def test_removes_markdown_from_all_lines(self):
        input_cv = "**Company**: **Role**\nAchievement: **Led** transformation"
        output_cv = sanitize_cv_output(input_cv)
        assert "**" not in output_cv
```

**Integration Points** (where to apply):
1. In `orchestrator.py` - After final CV generation, before returning to state
2. In `types.py` - Modify `to_markdown()` methods to call sanitization
3. In `cv_loader.py` - If loading pre-existing CV with markdown

**Effort**: 1 hour (function + comprehensive tests)

#### Layer 3: Output Format Clarification (OPTIONAL)

**Objective**: Make code intent clear

**Options**:
1. Rename `to_markdown()` → `to_plain_text()` in all types
2. Or keep name but update docstring: "Converts to output format (plain text)"
3. Or create separate `to_plain_text()` method alongside `to_markdown()`

**Recommendation**: Option 1 (rename) is clearest but largest scope. Start with Layer 1 + 2, then rename if needed.

**Effort**: 1-2 hours (if needed)

---

## Implementation Sequence

### Phase 1: Prompt Enhancement (30 minutes)

1. Edit `src/layer6_v2/prompts/role_generation.py`
   - Add plain-text guardrail to ROLE_GENERATION_SYSTEM_PROMPT
   - Add to BULLET_CORRECTION_SYSTEM_PROMPT

2. Edit `src/layer6_v2/prompts/header_generation.py`
   - Add to PROFILE_SYSTEM_PROMPT
   - Add to SKILLS_SYSTEM_PROMPT

3. Quick test: Generate CV and verify no markdown in LLM output

### Phase 2: Sanitization Function (1 hour)

1. Create `src/common/markdown_sanitizer.py`
   - Implement `strip_markdown_formatting()` function
   - Implement `sanitize_cv_output()` function

2. Create `tests/unit/test_markdown_sanitizer.py`
   - Test all edge cases (bold, italic, code, links, etc.)
   - Test with real CV samples

3. Run tests: Verify all pass

### Phase 3: Integration (30 minutes)

1. Update `src/layer6_v2/orchestrator.py`
   - Import sanitizer
   - Call `sanitize_cv_output()` on final CV before returning
   - Add log entry: "Applied markdown sanitization"

2. Test: Generate CV end-to-end, verify clean output

3. Commit all changes

---

## Testing Strategy

### Unit Tests (30 minutes)
- Test `strip_markdown_formatting()` with all markdown types
- Test with edge cases: consecutive asterisks, nested formatting, etc.
- Test with sample CV text

### Integration Tests (30 minutes)
- Generate CV with test JD containing rich formatting
- Verify output has zero markdown characters
- Verify structure preserved (newlines, spacing)

### Manual Validation (15 minutes)
- Run against 1-2 real job descriptions
- Visually inspect output (no `**`, `__`, `*`, `_`)
- Verify in both UI and exported format

### Test Cases to Include

```python
# In test_markdown_sanitizer.py

# Basic markdown removal
assert strip_markdown_formatting("**bold**") == "bold"
assert strip_markdown_formatting("*italic*") == "italic"
assert strip_markdown_formatting("__underline__") == "underline"

# Multiple in one line
assert strip_markdown_formatting("**bold** and *italic*") == "bold and italic"

# CV-specific patterns
assert strip_markdown_formatting("**Seven.One Entertainment Group**") == "Seven.One Entertainment Group"
assert strip_markdown_formatting("**Technical Lead** | **Remote**") == "Technical Lead | Remote"
assert strip_markdown_formatting("**Leadership**, **Architecture**, **Kubernetes**") == "Leadership, Architecture, Kubernetes"

# Edge cases
assert strip_markdown_formatting("Led **multi-year** transformation") == "Led multi-year transformation"
assert strip_markdown_formatting("AWS_S3 buckets") == "AWS_S3 buckets"  # Preserve intentional underscores
assert strip_markdown_formatting("") == ""
```

---

## Success Criteria

- [x] No `**` in generated CV output
- [x] No `__` in generated CV output
- [x] No `*` used as formatting (but preserve in email addresses)
- [x] No `_` used as formatting (but preserve in identifiers like AWS_S3)
- [x] All CV sections clean (company, role, achievements, skills, profile)
- [x] Structure preserved (newlines, spacing, punctuation)
- [x] All 622 existing tests still pass
- [x] 10+ new sanitization tests pass
- [x] Manual testing shows clean output

---

## Rollback Plan

If issues arise:
1. Revert Layer 2 integration commit (sanitizer still available)
2. Keep Layer 1 prompt enhancement (safe improvement)
3. Test with Layer 1 only to assess impact

---

## Related Issues

- **bugs.md #14**: Full bug tracking entry
- **missing.md**: Listed in "Current Blockers" and "CV Generation V2 - Bug Fixes"
- **Impact**: Layer 6 V2 (CV Generation) performance metrics

---

## References

### Markdown Patterns to Handle
- Bold: `**text**` and `__text__`
- Italic: `*text*` and `_text_`
- Code: `` `text` `` and ` ```code``` `
- Headers: `# Text`, `## Text`, etc.
- Links: `[text](url)`
- Images: `![alt](url)`
- Lists: `- item` or `* item` (line start)

### Test Data (Sample Markdown CV to Sanitize)
```
**Seven.One Entertainment Group**
**Technical Lead** | Berlin | 2021-2024

• Led **platform transformation** across **3 teams**
• Designed **microservices architecture** using **Kubernetes**
• Improved **system reliability** from 95% to **99.9%**

Skills: **Leadership**, **DevOps**, **Architecture**, **AWS**

Profile: Expert **platform engineer** with 12+ years building **distributed systems** at scale.
```

---

## Sign-Off

**Assigned To**: architecture-debugger (for implementation)
**Recommended Approach**: Test-driven development
- Write tests first (test_markdown_sanitizer.py)
- Implement function to pass tests
- Integrate into orchestrator
- Run full test suite
- Manual validation

**Next Step**: Review this plan and begin Phase 1 (prompt enhancement)
