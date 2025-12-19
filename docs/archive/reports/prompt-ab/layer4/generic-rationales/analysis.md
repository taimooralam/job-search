# A/B Analysis: Layer 4 - Generic Rationales

**Issue**: Boilerplate phrases pass validation; rationales lack specificity
**Technique Applied**: Constraint Prompting (Section 3.5 from prompt-generation-guide.md)
**Date**: 2025-11-28
**Status**: IMPLEMENTED (via Issue 1 changes)

---

## Summary

Enhanced Layer 4 prompts to explicitly forbid generic phrases and enforce specific, evidence-based language through both prompt design and stricter validation.

## Problem Statement

### V1 Behavior
- Only 7 generic phrases blacklisted
- Allowed up to 2 generic phrases per rationale
- Validation didn't require STAR citations
- Easy to pass validation with boilerplate text

### V2 Solution
- Explicit "You NEVER use generic phrases" in persona
- Expanded blacklist to 14 phrases
- Reduced tolerance to 1 generic phrase maximum
- Required STAR citations and pain point references

## Changes Made

### 1. Persona Constraint

Added explicit prohibition in SYSTEM_PROMPT:
```
CRITICAL RULES:
1. You NEVER use generic phrases like "strong background", "great fit", or "proven track record"
2. You ALWAYS cite concrete examples with metrics from the provided context
```

### 2. Expanded Generic Phrase Blacklist

**V1 (7 phrases)**:
- strong background
- great communication skills
- team player
- well-suited for this position
- good fit
- extensive experience
- proven track record

**V2 (14 phrases)**:
- strong background
- great communication skills
- team player
- well-suited
- good fit
- great fit
- excellent fit
- extensive experience
- proven track record
- highly qualified
- ideal candidate
- perfect fit
- excited to
- passionate about

### 3. Stricter Validation

| Gate | V1 | V2 |
|------|----|----|
| Generic phrases allowed | <=2 | <=1 |
| STAR citation required | No | Yes |
| Pain point reference | No | Yes |
| Minimum length | 10 words | 30 words |

### 4. Positive Constraint (Required Format)

```
**RATIONALE:** [2-3 sentences citing specific STARs by company name and metrics]
Format: "At [STAR company], candidate [result with metric], directly addressing [pain point]."
```

## Expected Improvements

| Metric | Baseline (V1) | Target (V2) | Improvement |
|--------|--------------|-------------|-------------|
| Specificity Score | ~5.5 | 7.0+ | +27% |
| Generic Phrase Count | 2-3 avg | <1 avg | -60% |
| STAR Citation Rate | ~40% | 100% | +150% |

## Verification

- All 48 A/B testing infrastructure tests pass
- TestGenericRationales tests validate phrase elimination
- Scorer detects generic phrases and penalizes appropriately

## Files Modified

Same as Issue 1:
- `src/layer4/opportunity_mapper.py`
  - Lines 27-46: SYSTEM_PROMPT with explicit constraints
  - Lines 247-274: Expanded generic phrase blacklist in validation

## Related Issues

- **Issue 1 (Weak Grounding)**: Primary implementation
- **Issue 2 (No Chain-of-Thought)**: Structured reasoning reduces generic output

---

*Generated as part of Prompt Optimization Phase 2*
