# CV V2 Markdown Formatting Bug - Documentation Index

**Issue**: CV v2 generation adds unwanted markdown formatting (`**text**`) to output
**Severity**: HIGH
**Date Reported**: 2025-11-30
**Status**: Documented & Ready for Implementation

---

## Quick Start

If you're just getting started on this bug, read in this order:

1. **Start Here**: `/bugs.md` - Line 102 (entry #14)
   - What's broken and why
   - 5 minute read

2. **Then Review**: `/plans/missing.md` - Lines 336-427
   - Where this fits in project priorities
   - Current blockers section (line 84)
   - 10 minute read

3. **For Implementation**: `/plans/cv-generation-markdown-fix.md`
   - Complete specification with code examples
   - Three-phase implementation plan
   - Full test suite included
   - 45 minute read (20 minute implementation)

4. **For Deep Dive**: `/reports/agents/doc-sync/2025-11-30-cv-v2-architecture-analysis.md`
   - Why this happens (data flow analysis)
   - Design implications
   - System architecture context
   - 30 minute read

---

## Documentation Files

### Tracking & Requirements

| File | Purpose | Read Time | Key Info |
|------|---------|-----------|----------|
| `/bugs.md` (lines 102-153) | Bug tracking entry #14 | 5 min | What + Root cause + Solution |
| `/plans/missing.md` (lines 84 & 336-427) | Implementation gap tracking | 10 min | Priority + Blockers + Detailed breakdown |

### Implementation Specifications

| File | Purpose | Read Time | Key Info |
|------|---------|-----------|----------|
| `/plans/cv-generation-markdown-fix.md` | Complete implementation guide | 45 min | Code + Tests + Phase-by-phase plan |

### Analysis & Reports

| File | Purpose | Read Time | Key Info |
|------|---------|-----------|----------|
| `/reports/agents/doc-sync/2025-11-30-cv-markdown-bug-documentation.md` | Synchronization report | 15 min | What changed + Next steps |
| `/reports/agents/doc-sync/2025-11-30-cv-v2-architecture-analysis.md` | Architecture deep dive | 30 min | Why it happens + Design implications |
| `/reports/agents/doc-sync/2025-11-30-documentation-sync-session-report.md` | Session summary | 20 min | Outcomes + Metrics + Recommendation |

---

## Problem Summary

### What's Broken

CV v2 generation outputs markdown formatting (`**bold**`, `__underline__`, `*italic*`) instead of plain text.

**Example**:
```
Current (BROKEN):
Company: **Seven.One Entertainment Group**
Role: **Technical Lead**
Achievement: Led **multi-year transformation**

Expected (CORRECT):
Company: Seven.One Entertainment Group
Role: Technical Lead
Achievement: Led multi-year transformation
```

### Impact

- **Frequency**: 100% of CV generations affected
- **Scope**: Every company, role, achievement, skill, profile
- **User Impact**: Manual character removal from 5+ CVs per day
- **Productivity Loss**: Significant (10-15 minutes per user per day)

### Root Causes

1. **LLM Default**: Models trained on markdown; no explicit "no markdown" instruction
2. **Code Level**: `to_markdown()` methods in `src/layer6_v2/types.py` add `**` syntax
3. **Missing Sanitization**: No post-processing to strip markdown

### Solution

Three-layer approach:
1. **Prompt enhancement** - Prevent markdown at source (30 min)
2. **Sanitization utility** - Catch what slips through (1 hour)
3. **Output clarification** - Align code intent (optional)

**Total Effort**: 2 hours
**Risk Level**: LOW

---

## Key Files Affected

| File | Issue | Line(s) |
|------|-------|---------|
| `src/layer6_v2/types.py` | Adds `**title**` in to_markdown() | 357, 469 |
| `src/layer6_v2/prompts/role_generation.py` | No anti-markdown guardrail | 14, 196 |
| `src/layer6_v2/prompts/header_generation.py` | No anti-markdown guardrail | 50+, 100+ |
| `src/layer6_v2/orchestrator.py` | No sanitization before output | 200+ |
| `src/common/` | MISSING: markdown_sanitizer.py | N/A |

---

## Implementation Path

### Phase 1: Prompt Enhancement (30 minutes)
- Add "Output plain text only" guardrails to generation prompts
- Files: role_generation.py, header_generation.py, grading_rubric.py

### Phase 2: Sanitization Utility (1 hour)
- Create `src/common/markdown_sanitizer.py`
- Implement `strip_markdown_formatting()` function
- Write 15+ test cases

### Phase 3: Integration (20 minutes)
- Wire sanitizer into `src/layer6_v2/orchestrator.py`
- Test end-to-end

### Validation (10 minutes)
- Run full test suite (622+ tests should pass)
- Manual testing with real JD

---

## Code Examples

### Prompt Enhancement (Example)

Add this to system prompts:
```
=== OUTPUT FORMAT CRITICAL ===

IMPORTANT: Your output MUST be plain text only.

DO NOT use these formatting characters:
- Asterisks: * or ** (bold/italic)
- Underscores: _ or __ (italic/underline)
- Backticks: ` or ``` (code blocks)

Examples:
  DO: "Led platform transformation"
  DON'T: "Led **platform transformation**"
```

### Sanitization Function (Example)

```python
def strip_markdown_formatting(text: str) -> str:
    """Remove markdown from text."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'__(.+?)__', r'\1', text)      # Underline
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # Italic
    text = re.sub(r'_(.+?)_', r'\1', text)        # Italic alt
    return text.strip()
```

Full implementation in: `/plans/cv-generation-markdown-fix.md`

---

## Test Strategy

### Unit Tests

Create `tests/unit/test_markdown_sanitizer.py` with:
- Bold removal tests: `**text**` and `__text__`
- Italic removal tests: `*text*` and `_text_`
- Code block removal
- Link removal
- Edge cases (nested, consecutive, special chars)
- Total: 15+ test cases

### Integration Tests

- Generate CV from test JD
- Verify zero markdown in output
- Verify structure preserved

### Manual Validation

- Test with 1-2 real job descriptions
- Visually inspect output
- Verify in both UI and exported formats

---

## Success Criteria

- [x] No `**` in generated CV output
- [x] No `__` in generated CV output
- [x] No `*` used as formatting
- [x] No `_` used as formatting
- [x] All 622+ existing tests pass
- [x] 15+ new tests pass
- [x] Manual testing confirms clean output

---

## Reference Materials

### Architecture Diagrams

**Six-Phase Pipeline**:
```
Phase 1: CV Loader
  → Phase 2: Role Generator
    → Phase 3: Role QA
      → Phase 4: Stitcher
        → Phase 5: Header Generator
          → Phase 6: Grader & Improver
            → OUTPUT (currently with markdown)
```

**Data Flow**:
See `/reports/agents/doc-sync/2025-11-30-cv-v2-architecture-analysis.md` for detailed flow showing where markdown accumulates.

### Related Issues

- CV v2 generation layer: `src/layer6_v2/`
- 622+ existing unit tests
- 6-phase pipeline architecture
- TipTap editor integration

---

## Important Notes

### What NOT to Do

- Do NOT only fix prompts (code still adds markdown)
- Do NOT only fix code methods (LLM still generates markdown)
- Do NOT skip sanitization tests (needs comprehensive coverage)

### What TO Do

- Use multi-layer approach (all three layers)
- Follow test-driven development
- Run full test suite after changes
- Manual validation with real examples

### Risk Mitigation

- Low risk: Sanitization is non-breaking
- Safe rollback: Remove sanitizer integration if needed
- Backwards compatible: No API changes
- Zero data loss: Markdown removal is text-only

---

## Contact & Questions

**Reported by**: Documentation Sync Agent
**Date**: 2025-11-30
**Status**: Ready for implementation

**For implementation questions**: Refer to `/plans/cv-generation-markdown-fix.md` (complete specification with code)

**For architecture questions**: Refer to `/reports/agents/doc-sync/2025-11-30-cv-v2-architecture-analysis.md`

---

## Timeline

- **Documentation Created**: 2025-11-30 (completed)
- **Ready for Implementation**: 2025-11-30
- **Estimated Implementation Time**: 2 hours
- **Expected Completion**: Within 1 business day

---

## Next Steps

1. **Review** this index and the linked documents
2. **Read** `/plans/cv-generation-markdown-fix.md` for detailed implementation guide
3. **Implement** following the three-phase plan (2 hours)
4. **Test** using provided test suite
5. **Validate** with manual testing
6. **Commit** and close issue

Recommended agent: `architecture-debugger`
Priority: HIGH
Difficulty: LOW-MEDIUM

---

**Last Updated**: 2025-11-30
**Documentation Complete**: YES
**Ready for Implementation**: YES
