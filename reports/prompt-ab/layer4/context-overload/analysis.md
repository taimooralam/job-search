# A/B Analysis: Layer 4 - Context Overload

**Issue**: Prompt receives too much context without prioritization of relevance
**Technique Applied**: Context Prioritization (Section 2.3 from prompt-generation-guide.md)
**Date**: 2025-11-28
**Status**: PARTIALLY IMPLEMENTED (via Issues 1-3 changes)

---

## Summary

The 4-step reasoning framework implicitly addresses context overload by forcing structured prioritization of information. However, additional explicit prioritization could further improve focus.

## Problem Statement

### V1 Behavior
- Received full JD + research + master CV (1200 chars truncated)
- No guidance on which context to prioritize
- LLM could cite irrelevant details
- Output verbosity varied widely

### V2 Improvements (Implicit)
- 4-step process forces focus on pain points first
- Step 1 explicitly maps pain points to STAR evidence
- Step 3 focuses on strategic signals only
- Scoring rubric ties to specific evidence count

## Current Implementation

### Step 1: Pain Point Mapping (Primary Focus)
```
STEP 1: PAIN POINT MAPPING
For each pain point, identify which STAR achievement (if any) demonstrates relevant experience.
Format: [Pain Point] -> [STAR company + metric] OR [No direct evidence]
```

This step forces the LLM to:
- Focus on pain points as primary context
- Ignore irrelevant JD details
- Only cite STARs that match pain points

### Step 3: Strategic Alignment (Secondary Focus)
```
STEP 3: STRATEGIC ALIGNMENT
How do company signals (growth, expansion, product) align with candidate's proven strengths?
Cite: [company signal] + [STAR evidence]
```

This step:
- Limits company research to actionable signals
- Connects signals to candidate strengths only
- Ignores generic company information

## Potential Additional Improvements

If further prioritization is needed, consider:

1. **Explicit Priority Statement**:
   ```
   CONTEXT PRIORITY (Focus in this order):
   1. Pain points + matching STARs (CRITICAL)
   2. Company signals with growth/timing relevance (IMPORTANT)
   3. Role research context (SECONDARY)
   4. Full JD and CV (REFERENCE ONLY)
   ```

2. **Context Truncation**:
   - Reduce master CV snippet to 800 chars
   - Limit company research to 3 signals max
   - Summarize role research to 2-3 bullets

3. **Token Budget**:
   ```
   BUDGET:
   - Reasoning: 200-300 tokens
   - Score: 5 tokens
   - Rationale: 50-75 tokens
   ```

## Expected Improvements

| Metric | Baseline (V1) | Current (V2) | With Full Prioritization |
|--------|--------------|--------------|--------------------------|
| Focus on Pain Points | ~50% | ~80% | 95%+ |
| Irrelevant Citations | ~30% | ~10% | <5% |
| Output Consistency | Variable | Moderate | High |

## Verification

- The structured 4-step process naturally limits context usage
- TestContextOverload tests verify focused output
- Output length is now bounded by format requirements

## Status

**PARTIALLY IMPLEMENTED**: The 4-step reasoning framework provides implicit prioritization. Explicit context priority instructions could be added in a future iteration if needed.

## Recommendation

Monitor integration test results. If outputs still cite irrelevant context:
1. Add explicit CONTEXT PRIORITY section
2. Reduce context truncation limits
3. Add token budgets

---

*Generated as part of Prompt Optimization Phase 2*
