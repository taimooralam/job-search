# Quick Start: Prompt Optimization Phase 2

**Last Updated**: 2025-11-28
**Current Phase**: Phase 1 COMPLETE
**Next Phase**: Phase 2 (Layer 4 A/B Testing)

---

## In 60 Seconds

1. **Read**: `/Users/ala0001t/pers/projects/job-search/SESSION_CONTEXT.md` (comprehensive reference)
2. **Verify**: `python -m pytest tests/ab_testing -v` (should show 48/48 PASSED)
3. **Start**: Execute Phase 2 using A/B testing protocol below

---

## Phase 2: Layer 4 A/B Testing (Week 2-3)

### Issue 1: Weak Grounding

**Goal**: Improve grounding score from ~5.8 to 8.0+

**Step 1: Run Baseline**
```python
from tests.ab_testing.framework import ABTestRunner

runner = ABTestRunner(
    layer="layer4",
    issue="weak-grounding",
    test_jobs=[...]  # Load from conftest fixture
)

baseline = runner.run_baseline()
print(f"Baseline grounding: {baseline.avg_grounding}")
```

**Step 2: Apply Enhancement**
Edit `/Users/ala0001t/pers/projects/job-search/src/layer4/opportunity_mapper.py`:

From `plans/prompt-optimization-plan.md` (lines 254-295):
- Add enhanced persona with evidence emphasis
- Add 4-step reasoning framework
- Add few-shot examples (domain-aware)
- Enhance validation to require STAR citations + pain point references

Key addition:
```python
SYSTEM_PROMPT_V2 = """You are a senior executive recruiter who has placed 500+ candidates.
Your reputation depends on ACCURATE fit assessments.
Your superpower: Spotting SPECIFIC evidence proving candidate solves company's SPECIFIC pain points.
You NEVER use generic phrases. You ALWAYS cite concrete examples with metrics.
"""
```

**Step 3: Run Enhanced**
```python
enhanced = runner.run_enhanced(technique="anti-hallucination-guardrails")
print(f"Enhanced grounding: {enhanced.avg_grounding}")
```

**Step 4: Compare**
```python
comparison = runner.compare(baseline, enhanced)
print(f"Improvement: {comparison.grounding_delta:.2f} ({comparison.improvement_percentage:.1f}%)")
```

**Step 5: Report**
```python
runner.generate_analysis_report(comparison)
# Saves to: reports/prompt-ab/layer4/weak-grounding/analysis.md
```

**Step 6: Decide**
- If improvement >= target: PASS, move to next issue
- If improvement < target: Refine prompt, repeat Steps 2-5 (max 3 iterations)

---

## The 12 Issues (Roadmap)

### Layer 4 (Week 2-3)
1. ✓ Weak grounding - anti-hallucination-guardrails
2. ✓ No chain-of-thought - reasoning-first approach
3. ✓ Generic rationales - constraint prompting
4. ✓ Context overload - context prioritization

### Layer 6a (Week 4)
5. ✓ Rigid structure - flexible planning phase
6. ✓ Weak pain points - structured mapping
7. ✓ Generic research - signal integration
8. ✓ STAR grounding - sourced metrics only

### Layer 6b (Week 5-6)
9. ✓ Regex parsing - LLM-based parsing
10. ✓ Role selection - competency alignment
11. ✓ Generic summaries - role-specific tailoring
12. ✓ Hallucination gaps - strict validation

---

## Key Commands

```bash
# Activate environment
source .venv/bin/activate

# Run all A/B tests (should always be 48/48)
python -m pytest tests/ab_testing -v

# Run Layer 4 tests only
python -m pytest tests/ab_testing/test_layer4_ab.py -v

# Run specific issue tests
python -m pytest tests/ab_testing/test_layer4_ab.py::TestWeakGrounding -v

# Run with coverage report
python -m pytest tests/ab_testing --cov=tests.ab_testing -v

# Check git status
git status

# Commit after Phase 2 completion
git add -A
git commit -m "feat(layer4): Implement prompt improvements per A/B testing Phase 2"
```

---

## Test Infrastructure Reference

### ABTestRunner Methods
- `run_baseline()` - Execute baseline prompt on 3 test jobs
- `run_enhanced(technique)` - Execute enhanced prompt on same jobs
- `compare(baseline, enhanced)` - Side-by-side comparison with deltas
- `generate_analysis_report(comparison)` - Markdown output

### Scoring Functions
- `score_specificity(text, context)` - 1-10, higher = less generic
- `score_grounding(text, source_context)` - 1-10, higher = more cited
- `score_hallucinations(text, master_cv, state)` - 1-10, higher = fewer hallucinations
- `calculate_combined_score(spec, ground, hall)` - Weighted average

### Test Data
- 3 test jobs in conftest.py (1 real from MongoDB, 2 synthetic)
- Master CV with STAR achievements
- Sample state objects with pain_points, selected_stars, company_research

---

## File Locations (Absolute Paths)

**Key Implementation Files**:
- Layer 4: `/Users/ala0001t/pers/projects/job-search/src/layer4/opportunity_mapper.py`
- Layer 6a: `/Users/ala0001t/pers/projects/job-search/src/layer6/cover_letter_generator.py`
- Layer 6b: `/Users/ala0001t/pers/projects/job-search/src/layer6/cv_generator.py`

**Reference Documents**:
- Master Plan: `/Users/ala0001t/pers/projects/job-search/plans/prompt-optimization-plan.md`
- Techniques: `/Users/ala0001t/pers/projects/job-search/thoughts/prompt-modernization-blueprint.md`
- Context: `/Users/ala0001t/pers/projects/job-search/SESSION_CONTEXT.md`

**Test Files**:
- Framework: `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/framework.py`
- Scorers: `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/scorers.py`
- Fixtures: `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/conftest.py`
- Tests: `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/test_layer*.py`

**Report Output**:
- Results: `/Users/ala0001t/pers/projects/job-search/reports/prompt-ab/layer{4,6a,6b}/{issue}/`

---

## Success Criteria

For **EACH** of the 12 issues:

| Metric | Target | How to Check |
|--------|--------|--------------|
| Grounding Score | 8.0+ | `enhanced.avg_grounding >= 8.0` |
| Specificity Score | 8.0+ | `enhanced.avg_specificity >= 8.0` |
| Hallucinations Score | 9.0+ | `enhanced.avg_hallucinations >= 9.0` |
| Combined Score | 8.0+ | `enhanced.avg_combined >= 8.0` |
| All Tests Passing | 48/48 | `pytest tests/ab_testing -v` shows 48 PASSED |
| No Regressions | 0 failures | All Layer 2-7 integration tests still pass |

---

## Git Workflow

**Current Branch**: `prompt-optimisation` (from main)

**Before Committing**:
1. Verify all tests pass: `pytest tests/ab_testing -v`
2. Run broader tests to check regressions (if available)
3. Update analysis reports in `reports/prompt-ab/`

**Commit Format**:
```bash
git add -A
git commit -m "feat(layer4): Apply anti-hallucination guardrails to opportunity mapper

- Enhanced persona with evidence emphasis
- Added 4-step reasoning framework (STAR mapping, gap analysis, strategic alignment, scoring)
- Added domain-specific few-shot examples
- Enhanced validation requiring STAR citations and pain point references

A/B Testing Results:
- Baseline grounding: 5.8
- Enhanced grounding: 8.2
- Improvement: +2.4 (41% increase)
- Status: PASS (exceeds target)"
```

---

## Troubleshooting

**Tests not running?**
```bash
source .venv/bin/activate
pip install -e .
pytest tests/ab_testing -v
```

**Tests failing after prompt edit?**
- Check that prompt returns valid JSON
- Verify no syntax errors in Python code
- Run baseline first to establish comparison point
- Check test logs for specific assertion failures

**Scoring seems off?**
- Review scorer logic in `tests/ab_testing/scorers.py`
- Verify test data in conftest.py
- Check that state object has all required fields
- Print debug info: `print(baseline.outputs[0].specificity.feedback)`

**Can't find test jobs?**
- They're in conftest.py as fixtures
- Load with: `from tests.ab_testing.conftest import sample_job_1, master_cv_fixture`
- Or use: `runner = ABTestRunner(..., test_jobs=[...])` with explicit list

---

## Phase 2 Timeline

| Week | Days | Focus | Issues | Status |
|------|------|-------|--------|--------|
| 2 | 1-3 | Layer 4 issues 1-2 | Grounding, CoT | TODO |
| 2-3 | 4-7 | Layer 4 issues 3-4 | Generics, overload | TODO |
| 4 | 1-5 | Layer 6a issues 5-8 | Structure, signals, STAR | TODO |
| 5-6 | 1-7 | Layer 6b issues 9-12 | Parsing, selection, tailoring | TODO |
| 7 | 1-5 | Integration + final analysis | End-to-end testing | TODO |

---

## Quick Reference: Prompting Techniques

### For Weak Grounding (Issue 1)
From `thoughts/prompt-modernization-blueprint.md`:
- Technique 3.4: Anti-hallucination guardrails
  - Add "Only use facts from provided context"
  - Add "If unsure, state Unknown"
  - Add "Cite sources for all claims"
  - Add "Flag assumptions explicitly"

### For No Chain-of-Thought (Issue 2)
- Technique 2.2: Reasoning-first approach
  - Add "BEFORE generating output, think through:"
  - Add step-by-step analysis blocks
  - Make reasoning visible in output

### For Generic Rationales (Issue 3)
- Technique 3.5: Constraint prompting
  - Add "You NEVER use generic phrases"
  - Blacklist specific phrases
  - Require quantified metrics in every claim

### For Context Overload (Issue 4)
- Technique 2.3: Context prioritization
  - Add "Focus on: [top 3 items only]"
  - Reorder context by relevance
  - Explicitly say which context to use

See `plans/prompt-optimization-plan.md` lines 185-320 for detailed specifications.

---

## Before Starting Phase 2

- [x] Read SESSION_CONTEXT.md
- [x] Review plans/prompt-optimization-plan.md (at least Section B & C)
- [x] Run: `pytest tests/ab_testing -v` (verify 48/48 passing)
- [x] Review Layer 4 current implementation
- [x] Understand A/B testing protocol
- [x] Prepare Git commit message template

## After Completing Each Issue

- [ ] Generate analysis report
- [ ] Save to reports/prompt-ab/layer{N}/{issue}/
- [ ] Document delta percentages
- [ ] Commit with detailed message
- [ ] Create PR description for main branch
- [ ] Mark issue as DONE in tracking

---

**Status**: READY TO START PHASE 2
**Confidence**: High (all infrastructure validated)
**Estimated Time**: 2 weeks for Phase 2-5
**Branch**: `prompt-optimisation`
**Target**: Main branch PR with all 12 issues resolved
