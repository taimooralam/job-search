# Session Continuity Index

**Project**: Job Intelligence Pipeline - Prompt Optimization Phase
**Status**: Phase 1 COMPLETE (Infrastructure), Phase 2-5 PENDING (Implementation)
**Last Updated**: 2025-11-28
**Branch**: `prompt-optimisation`

---

## Documents in This Session Package

### 1. SESSION_CONTEXT.md (Comprehensive Reference)
**Size**: ~2000 lines
**Purpose**: Complete project context, detailed roadmap, technical specifications
**When to Use**: 
- Need full understanding of system architecture
- Implementing phase 2-5
- Debugging test failures
- Understanding A/B testing framework

**Key Sections**:
- Project overview
- Phase 1 completed work
- Phases 2-5 pending tasks
- Reference documents guide
- A/B testing protocol (detailed)
- Environment setup
- Critical notes for next session

### 2. QUICK_START.md (Action-Oriented Guide)
**Size**: ~400 lines
**Purpose**: Step-by-step execution guide for Phase 2
**When to Use**:
- Starting Phase 2 work
- Running A/B tests for first time
- Quick reference during development
- Troubleshooting common issues

**Key Sections**:
- 60-second overview
- Phase 2 workflow (Issue 1: Weak Grounding)
- All 12 issues roadmap
- Key commands (pytest, git)
- Test infrastructure reference
- Success criteria
- Troubleshooting guide

### 3. SESSION_INDEX.md (This File)
**Purpose**: Navigation guide for all context documents
**When to Use**: 
- Starting new session, unsure which doc to read
- Quick lookup of what's available
- Understanding document relationships

---

## Quick Navigation Guide

### "I'm starting fresh and need full context"
1. Start here: SESSION_INDEX.md (this file)
2. Read: QUICK_START.md (60-second overview + commands)
3. Deep dive: SESSION_CONTEXT.md (comprehensive reference)

### "I'm resuming Phase 2 implementation"
1. Start: QUICK_START.md (refresh on workflow)
2. Reference: SESSION_CONTEXT.md (A/B protocol section)
3. Run: `pytest tests/ab_testing -v` (verify green)

### "I need to understand the A/B testing framework"
1. Quick overview: QUICK_START.md (sections: "Test Infrastructure Reference", "The 12 Issues")
2. Detailed specs: SESSION_CONTEXT.md (section: "A/B Testing Protocol")
3. Code reference: 
   - `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/framework.py`
   - `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/scorers.py`

### "I need to implement Issue 1: Weak Grounding"
1. Quick reference: QUICK_START.md (section: "Phase 2: Layer 4 A/B Testing")
2. Detailed technique: SESSION_CONTEXT.md (section: "Pending Work: Phase 2")
3. Master specifications: `/Users/ala0001t/pers/projects/job-search/plans/prompt-optimization-plan.md` (lines 254-295)

### "I'm stuck and need to debug"
1. Troubleshooting: QUICK_START.md (section: "Troubleshooting")
2. Architecture: SESSION_CONTEXT.md (section: "Git Workflow", "Environment Setup")
3. Full plan: SESSION_CONTEXT.md (section: "Key Reference Documents")

---

## File Structure Overview

### Session Documentation (Root Level)
```
/Users/ala0001t/pers/projects/job-search/
├── SESSION_INDEX.md              ← Navigation guide (this file)
├── SESSION_CONTEXT.md            ← Comprehensive reference
├── QUICK_START.md                ← Action-oriented guide
└── SESSION_SUMMARY.md            ← Executive summary (optional)
```

### Master Plan
```
plans/
└── prompt-optimization-plan.md   ← 1778 lines, complete specification
```

### Test Infrastructure (Phase 1 Complete)
```
tests/ab_testing/
├── __init__.py
├── framework.py                  ← ABTestRunner class
├── scorers.py                    ← Scoring functions (3 dimensions)
├── conftest.py                   ← Test fixtures & data
├── test_layer4_ab.py            ← 18 tests for Layer 4
├── test_layer6a_ab.py           ← 14 tests for Layer 6a
└── test_layer6b_ab.py           ← 16 tests for Layer 6b
(All 48 tests PASSING)
```

### Reports Structure (Ready for Phase 2)
```
reports/prompt-ab/
├── layer4/
│   ├── weak-grounding/          ← Issue 1 results go here
│   ├── no-cot/                  ← Issue 2 results go here
│   ├── generic-rationales/      ← Issue 3 results go here
│   └── context-overload/        ← Issue 4 results go here
├── layer6a/
│   ├── rigid-structure/
│   ├── weak-painpoints/
│   ├── generic-research/
│   └── star-grounding/
└── layer6b/
    ├── regex-parsing/
    ├── role-selection/
    ├── generic-summaries/
    └── hallucination-gaps/
```

### Reference Documents
```
thoughts/
├── prompt-generation-guide.md        ← Universal techniques
├── prompt-modernization-blueprint.md ← Layer-specific improvements
└── change.md                         ← Vision for role-play flow

plans/
├── architecture.md                   ← System design
├── missing.md                        ← Implementation gaps
└── prompt-optimization-plan.md       ← Master plan (1778 lines)
```

### Implementation Files (To Be Updated)
```
src/
├── layer4/opportunity_mapper.py      ← Phase 2 target (Layer 4)
└── layer6/
    ├── cover_letter_generator.py     ← Phase 3 target (Layer 6a)
    └── cv_generator.py               ← Phase 4 target (Layer 6b)
```

---

## Session At A Glance

| Item | Status | Details |
|------|--------|---------|
| Master Plan | COMPLETE | `plans/prompt-optimization-plan.md` - 1778 lines |
| Test Framework | COMPLETE | `tests/ab_testing/framework.py` - ABTestRunner ready |
| Scoring System | COMPLETE | 3 dimensions: specificity, grounding, hallucinations |
| Unit Tests | COMPLETE | 48 tests, ALL PASSING |
| Test Data | COMPLETE | 3 jobs, master CV, fixtures in conftest.py |
| Report Structure | COMPLETE | 12 directories ready for results |
| Phase 1 | COMPLETE | Infrastructure only, zero implementation |
| Phase 2-5 | PENDING | Actual prompt improvements (12 issues across 3 layers) |

---

## What Each Phase Does

### Phase 1: Infrastructure (COMPLETED)
- Create A/B testing framework
- Build scoring system (specificity, grounding, hallucinations)
- Write 48 unit tests across 3 test modules
- Establish report directory structure
- Document process in master plan

**Outcome**: Everything ready to execute Phase 2

### Phase 2: Layer 4 (PENDING - Week 2-3)
- Issue 1: Weak grounding (anti-hallucination guardrails)
- Issue 2: No chain-of-thought (reasoning-first)
- Issue 3: Generic rationales (constraint prompting)
- Issue 4: Context overload (context prioritization)

**Approach**: 4 issues x (baseline + enhanced + compare + iterate up to 3x) = ~12 test runs

### Phase 3: Layer 6a (PENDING - Week 4)
- Issue 5: Rigid structure
- Issue 6: Weak pain points
- Issue 7: Generic research
- Issue 8: STAR grounding

### Phase 4: Layer 6b (PENDING - Week 5-6)
- Issue 9: Regex parsing
- Issue 10: Role selection
- Issue 11: Generic summaries
- Issue 12: Hallucination gaps

### Phase 5: Integration (PENDING - Week 7)
- End-to-end testing with real MongoDB jobs
- Performance comparison vs baseline
- Final recommendations for production rollout

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Days to Plan Phase | 1 day (Phase 1) |
| Days to Execute Phases 2-5 | ~14 days (2 weeks) |
| Total Unit Tests | 48 |
| Test Pass Rate | 100% (48/48) |
| Issues to Resolve | 12 |
| Issues per Layer | 4 (Layer 4), 4 (Layer 6a), 4 (Layer 6b) |
| Scoring Dimensions | 3 (specificity, grounding, hallucinations) |
| Max Iterations per Issue | 3 |
| Expected Improvement per Issue | 20-40% |
| Lines of Code (Framework) | ~500 |
| Lines of Code (Tests) | ~1200 |
| Lines of Code (Plan) | 1778 |

---

## Success Criteria (Per Issue)

Each of the 12 issues must achieve:

1. **Grounding Score**: 8.0 or higher
2. **Specificity Score**: 8.0 or higher
3. **Hallucinations Score**: 9.0 or higher
4. **Combined Score**: 8.0 or higher
5. **All Tests**: 48/48 passing (no regressions)
6. **Documentation**: Analysis report saved to `reports/prompt-ab/`

---

## Git Workflow

**Current Branch**: `prompt-optimisation` (from main)

**Before Each Commit**:
```bash
# Verify all tests pass
python -m pytest tests/ab_testing -v

# Expected: 48 passed in ~0.5s
```

**After Completing Each Issue**:
```bash
git add -A
git commit -m "feat(layer{N}): Resolve issue {M} via A/B testing

- Applied technique: [technique name]
- Baseline score: [metric before]
- Enhanced score: [metric after]
- Improvement: [+X, Y%]
- Status: PASS/FAIL"
```

**After All Phases Complete**:
```bash
git push origin prompt-optimisation
# Create PR to main with full A/B testing report
```

---

## Environment Checklist

Before starting Phase 2:

- [ ] Virtual environment activated: `source .venv/bin/activate`
- [ ] Dependencies installed: `pip install -e .`
- [ ] Tests passing: `pytest tests/ab_testing -v` → 48/48
- [ ] Environment variables set: `.env` file configured
- [ ] Git branch correct: `git branch` shows `* prompt-optimisation`
- [ ] Documentation read: Reviewed SESSION_CONTEXT.md

---

## Recommended Reading Order

### For New Session Starters
1. **This file** (2 min) - Get oriented
2. **QUICK_START.md** (10 min) - Understand workflow
3. **SESSION_CONTEXT.md** (20 min) - Deep technical knowledge
4. **Master plan** (30 min) - Full specification (optional)

### For Resuming Developers
1. **QUICK_START.md** (5 min) - Refresh on commands
2. **SESSION_CONTEXT.md** (relevant section only)
3. **Test output** - Run `pytest tests/ab_testing -v`

---

## Common Tasks

### "Run Phase 2 Issue 1 workflow"
```bash
source .venv/bin/activate
python -m pytest tests/ab_testing/test_layer4_ab.py::TestWeakGrounding -v
# Edit src/layer4/opportunity_mapper.py per QUICK_START.md
pytest tests/ab_testing -v  # Verify no regressions
git commit -m "feat(layer4): Apply anti-hallucination guardrails..."
```

### "Check A/B test results"
```bash
cat reports/prompt-ab/layer4/weak-grounding/analysis.md
```

### "See which tests cover which issue"
```bash
pytest tests/ab_testing/test_layer4_ab.py::TestWeakGrounding -v --collect-only
```

### "Run all tests with coverage"
```bash
pytest tests/ab_testing --cov=tests.ab_testing -v
```

---

## Support & Reference

**Questions About**:
- A/B testing protocol → SESSION_CONTEXT.md, section "A/B Testing Protocol"
- Test infrastructure → QUICK_START.md, section "Test Infrastructure Reference"
- Prompt techniques → `thoughts/prompt-modernization-blueprint.md`
- Phase specifics → SESSION_CONTEXT.md, section "Pending Work: Phases 2-5"
- Implementation → `plans/prompt-optimization-plan.md` (sections A-D)

**Key Contact Points**:
- Master plan: `plans/prompt-optimization-plan.md`
- Test code: `tests/ab_testing/framework.py`, `scorers.py`
- Implementation targets: `src/layer{4,6}/`
- Results: `reports/prompt-ab/`

---

## Session Timeline

| Phase | Status | Week | Deliverable |
|-------|--------|------|-------------|
| Phase 1 | COMPLETE | Week 1 | A/B infrastructure + 48 tests |
| Phase 2 | PENDING | Week 2-3 | Layer 4 improvements (4 issues) |
| Phase 3 | PENDING | Week 4 | Layer 6a improvements (4 issues) |
| Phase 4 | PENDING | Week 5-6 | Layer 6b improvements (4 issues) |
| Phase 5 | PENDING | Week 7 | Integration + final report |

---

## Next Steps

1. **For New Sessions**: Read QUICK_START.md, then SESSION_CONTEXT.md
2. **For Resuming**: Verify tests with `pytest tests/ab_testing -v`
3. **For Implementation**: Follow Phase 2 workflow in QUICK_START.md
4. **For Questions**: Check relevant section in SESSION_CONTEXT.md

---

**Status**: Ready for Phase 2
**Confidence**: High - All infrastructure validated
**Time to Start**: < 5 minutes
**Effort to Complete**: ~2 person-weeks (Phases 2-5)
**Branch**: `prompt-optimisation`

Last updated: 2025-11-28 22:45 UTC
