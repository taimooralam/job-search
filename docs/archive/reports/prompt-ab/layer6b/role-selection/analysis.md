# A/B Analysis: Layer 6b - Role Selection

**Issue**: Algorithmic STAR scoring is simplistic (keyword matching only)
**Technique Applied**: Context-Aware Competency Alignment
**Date**: 2025-11-28
**Status**: IMPLEMENTED (via competency mix enhancement)

---

## Summary

Enhanced the competency mix analysis to consider role seniority and context, improving STAR selection beyond simple keyword matching.

## Changes Made

### 1. Context Analysis Step

Added seniority-aware weighting guidance:
```
STEP 2: CONTEXT ANALYSIS
Beyond keywords, analyze the role's seniority and scope:
- Junior roles: Higher delivery weight
- Staff/Principal: Higher architecture weight
- Team Lead/Manager: Higher leadership weight
- DevOps/Platform: Higher process weight
```

### 2. Evidence-Based Reasoning

Required JD-grounded justification:
```
Each percentage MUST be justified with evidence from the JD
```

This means the competency mix analysis now:
1. Considers role title/level (not just keywords)
2. Weighs competencies appropriately for seniority
3. Produces grounded reasoning that guides STAR selection

## STAR Scoring Integration

The enhanced competency mix feeds into existing STAR scoring:
```python
def _score_stars(all_stars, competency_mix, job_keywords):
    # 60% weight: Competency dimension alignment
    # 40% weight: Keyword match score
```

Better competency mix = Better STAR alignment = More relevant CV content.

## Expected Improvements

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| STAR Relevance | ~70% | 85%+ | Context-aware competency weights |
| Leadership Role Fit | ~60% | 80%+ | Seniority-based adjustments |
| Technical Role Fit | ~75% | 90%+ | Better dimension matching |

---

*Generated as part of Prompt Optimization Phase 4*
