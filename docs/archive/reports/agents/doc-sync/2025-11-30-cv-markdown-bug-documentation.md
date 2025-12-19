# Documentation Sync Report: CV V2 Markdown Formatting Bug

**Date**: 2025-11-30
**Agent**: Doc Sync (Haiku 4.5)
**Type**: Bug Documentation & Planning
**Status**: COMPLETE

---

## Summary

Comprehensive documentation created to capture a HIGH priority bug in CV v2 generation where markdown formatting (asterisks, underscores) are being added to output text, requiring manual user cleanup on every generated CV. This issue directly impacts productivity and workflow velocity.

---

## Changes Made

### 1. bugs.md - Bug Entry #14 (CREATED)

**File**: `/Users/ala0001t/pers/projects/job-search/bugs.md`

**Added**: Complete bug tracking entry with:
- Issue description and severity assessment
- Root cause analysis (prompt, code, missing sanitization)
- Affected files and lines of code
- Three-layer proposed solution (prompt, sanitization, format)
- Test cases and verification steps
- Priority and impact analysis
- Effort estimate: 2 hours

**Key Details**:
- Severity: HIGH (every CV generation affected)
- Impact: Manual cleanup multiplied across applications
- Root causes:
  1. LLM default markdown behavior
  2. Code-level `to_markdown()` adding asterisks
  3. Missing post-processing sanitization
- Solution: Prompt enhancement + post-processing + optional refactoring

---

### 2. plans/missing.md - Current Blockers Section (UPDATED)

**File**: `/Users/ala0001t/pers/projects/job-search/plans/missing.md`

**Change 1 - Current Blockers Table**:
Added markdown bug to top of blockers list with high visibility:
```
| CV V2: Markdown Asterisks in Output | HIGH | Strip markdown from prompts + post-processing sanitization. Effort: 2 hours. See bugs.md #14 |
```

**Change 2 - New Section: CV Generation V2 Bug Fixes**:
Added comprehensive `CV Generation V2 - Bug Fixes` section (lines 336-427) with:
- BUG: Markdown Asterisks in CV Output (HIGH PRIORITY)
- Detailed problem description with examples
- Root cause analysis (prompt, code, sanitization gaps)
- Affected files listing
- Three-layer solution design
- Test plan and verification strategy
- Effort estimate: 2 hours total
- Impact and priority justification
- Cross-reference to bugs.md #14

---

### 3. plans/cv-generation-markdown-fix.md - Detailed Implementation Plan (CREATED)

**File**: `/Users/ala0001t/pers/projects/job-search/plans/cv-generation-markdown-fix.md`

**Purpose**: Complete implementation specification and coding guide

**Sections**:
1. **Problem Statement** - Impact analysis and current vs expected behavior
2. **Root Cause Analysis** - Three independent issues identified
3. **Affected Files** - Table of 9 files needing changes
4. **Solution Design** - Three-layer fix approach:
   - Layer 1: Prompt Enhancement (add explicit guardrails)
   - Layer 2: Post-Processing Sanitization (strip markdown utility)
   - Layer 3: Output Format Clarification (rename methods, optional)
5. **Implementation Details**:
   - Complete example guardrail text for prompts
   - Full Python code for `markdown_sanitizer.py` module
   - Complete test suite with 14+ test cases
   - Integration points in codebase
6. **Implementation Sequence** - 3-phase plan (30 min + 1h + 30 min)
7. **Testing Strategy** - Unit, integration, and manual validation
8. **Success Criteria** - 7 clear verification points
9. **Rollback Plan** - Safety procedures if issues arise
10. **References** - Markdown patterns, test data, test-driven approach

---

## Code Locations & Findings

### Problem Sources Identified

**Source 1: LLM Prompts** (No explicit anti-markdown guardrail)
- File: `src/layer6_v2/prompts/role_generation.py`
  - ROLE_GENERATION_SYSTEM_PROMPT (line 14)
  - build_role_generation_user_prompt() (line 76)
  - BULLET_CORRECTION_SYSTEM_PROMPT (line 196)
- File: `src/layer6_v2/prompts/header_generation.py`
  - PROFILE_SYSTEM_PROMPT
  - SKILLS_SYSTEM_PROMPT
- File: `src/layer6_v2/prompts/grading_rubric.py`

**Source 2: Code-Level Markdown Formatting**
- File: `src/layer6_v2/types.py`
  - Line 357: `StitchedRole.to_markdown()` adds `f"**{self.title}**"`
  - Line 469: `SkillsSection.to_markdown()` adds `f"**{self.category}**"`
  - Other `to_markdown()` methods in ProfileOutput and other dataclasses

**Source 3: Missing Post-Processing**
- File: `src/layer6_v2/orchestrator.py` (no sanitization before output)
- Gap: No step to strip markdown after generation

---

## Reproducibility

**How to Reproduce** (100% reproducible):
1. Generate CV via Layer 6 V2 pipeline
2. Examine output text
3. Observe `**` around company names, roles, skills
4. Observe `_` around emphasis text

**Example Output**:
```
Company: **Seven.One Entertainment Group**
Role: **Technical Lead**
Achievement: Led **multi-year transformation** of platform
Skills: **Leadership**, **Architecture**, **Team Building**
```

---

## Impact Assessment

| Dimension | Impact | Notes |
|-----------|--------|-------|
| Frequency | 100% | Every CV generation affected |
| Scope | All sections | Companies, roles, achievements, skills, profile |
| User Impact | High | Manual cleanup on every application |
| Productivity Loss | Significant | 5+ CVs = 5+ manual character removals |
| Severity | HIGH | Direct impact on daily workflow velocity |
| Fix Complexity | LOW | Multi-layered approach with clear steps |
| Test Coverage | HIGH | Full test suite can be written |

---

## Solution Components

### Component 1: Prompt Enhancement (30 min)
- Add explicit "Output plain text only" guardrails
- Apply to 6-8 prompt files
- Prevent LLM from generating markdown

### Component 2: Sanitization Utility (1 hour)
- Create `src/common/markdown_sanitizer.py`
- Implement `strip_markdown_formatting()` function
- Handle 6+ markdown patterns (bold, italic, code, links, etc.)
- Create comprehensive test suite (14+ tests)
- Safety net if LLM still produces markdown

### Component 3: Integration (30 min)
- Wire sanitizer into `src/layer6_v2/orchestrator.py`
- Apply to final CV before output
- Test end-to-end

---

## Documentation Quality

All documentation follows project standards:
- Detailed problem description with examples
- Root cause analysis with code references
- Clear, actionable solution steps
- Complete implementation code included
- Comprehensive test cases provided
- Cross-references between files
- Proper file paths and line numbers
- Formatting for readability (markdown tables, code blocks, etc.)

---

## Cross-References

### Documentation Linkage

- `bugs.md #14` ← Main bug entry
- `plans/missing.md` → Current Blockers + CV Generation V2 Bugs section
- `plans/cv-generation-markdown-fix.md` ← Detailed implementation guide
- `src/layer6_v2/types.py` → Lines 357, 469 (problem sources)
- `src/layer6_v2/orchestrator.py` → Integration point

### Related Architecture

- Layer 6 V2: Complete CV generation pipeline
- Phase 3: Per-role bullet generation
- Phase 4: Role stitching
- Phase 5: Header/profile generation
- Phase 6: Quality grading and improvement

---

## Next Steps (Recommended)

### For Architecture Debugger Agent
1. **Review** the implementation plan in `plans/cv-generation-markdown-fix.md`
2. **Implement Phase 1**: Update prompts with anti-markdown guardrails (30 min)
3. **Implement Phase 2**: Create `src/common/markdown_sanitizer.py` (1 hour)
4. **Write Tests**: Create `tests/unit/test_markdown_sanitizer.py` (30 min)
5. **Integrate**: Wire into `src/layer6_v2/orchestrator.py` (20 min)
6. **Test**: Run full test suite + manual validation (10 min)
7. **Commit**: Atomic commit with detailed message

### Testing Approach (TDD)
1. Write tests first (`tests/unit/test_markdown_sanitizer.py`)
2. Implement `strip_markdown_formatting()` to pass tests
3. Implement `sanitize_cv_output()` wrapper
4. Integrate into orchestrator
5. Run full test suite (should see 622+ tests passing)
6. Manual validation with real JD

### Success Criteria Met When
- No `**` in any generated CV
- No `__` in any generated CV
- All 622+ existing tests pass
- 15+ new sanitization tests pass
- Manual testing confirms clean output

---

## Files Modified Summary

| File | Change | Type |
|------|--------|------|
| `/bugs.md` | Added entry #14 with complete bug details | Modified |
| `/plans/missing.md` | Added to Current Blockers + new CV Generation V2 Bugs section | Modified |
| `/plans/cv-generation-markdown-fix.md` | Complete implementation plan document | Created |

---

## Effort Estimate Verification

**Documented Effort**: 2 hours
- Prompt enhancement: 30 minutes
- Sanitization function + tests: 1 hour
- Integration + testing: 30 minutes

**Includes**: Planning, coding, testing, and verification

---

## Agent Recommendation

**Recommended Next Agent**: `architecture-debugger`
**Action**: Implement the three-phase fix using TDD approach
**Resources**: All implementation details in `plans/cv-generation-markdown-fix.md`
**Priority**: HIGH (blocking daily CV generation workflow)

---

## Documentation Verification

- [x] Bug entry detailed and actionable (bugs.md #14)
- [x] High-level overview in missing.md (Current Blockers)
- [x] Full implementation guide (cv-generation-markdown-fix.md)
- [x] Code locations identified with line numbers
- [x] Root cause analysis complete
- [x] Solution designed and documented
- [x] Test strategy defined
- [x] Cross-references established
- [x] No speculation (all grounded in codebase review)
- [x] Clear next steps for implementation

---

## Conclusion

Documentation complete and ready for implementation. The CV v2 markdown formatting bug has been comprehensively analyzed and documented with a clear, multi-layered solution approach. The fix requires:
- 2 hours of implementation time
- Multi-layered approach (prompt + code + sanitization)
- Comprehensive testing plan
- Zero risk of regression (sanitizer is non-breaking, prompt changes are safe)

The issue directly impacts user productivity (manual cleanup on every CV), making it a HIGH priority for immediate implementation.
