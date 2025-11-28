# A/B Analysis: Layer 6a - Generic Company Research

**Issue**: Company signals not strongly integrated into cover letter
**Technique Applied**: Signal Integration with Planning (Section 2.3)
**Date**: 2025-11-28
**Status**: IMPLEMENTED

---

## Summary

Added explicit company signal selection step and made signal references mandatory in the hook paragraph.

## Changes Made

### 1. Planning Phase Step 2: Signal Selection

Added signal selection requirement:
```
STEP 2: COMPANY SIGNAL SELECTION
Choose 1 signal to reference in the hook:
- Signal: [type] - [description]
- Connection: How candidate strengths align
```

### 2. Hook Requirements

Enhanced hook structure:
```
1. **Hook**: Lead with {company}'s specific pain point and company signal
   - Name a specific problem they face
   - Reference their recent [funding/expansion/product launch]
```

### 3. System Prompt Enforcement

Added to CRITICAL RULES:
```
4. Company signals MUST be referenced (funding, growth, product launches)
```

Added to structure:
```
1. **Hook**: Specific interest + pain point + company signal (NOT "I am excited")
   - Lead with their problem, not your interest
   - Reference a specific company signal (recent funding, expansion, product launch)
```

## Expected Improvements

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Signal Reference Rate | ~40% | 90%+ | Mandatory in planning + hook |
| Company Specificity | Low | High | Signal-connected opening |
| Grounding Score | ~6.0 | 8.0+ | Concrete company references |

---

*Generated as part of Prompt Optimization Phase 3*
