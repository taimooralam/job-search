# Session Continuity Document: Prompt Optimization Phase

**Created**: 2025-11-28
**Branch**: `prompt-optimisation`
**Last Commit**: `25e15e0a` - feat(testing): Add A/B testing infrastructure for prompt optimization
**Status**: Phase 1 Complete, Phase 2-5 Pending

---

## Project Overview

Job Intelligence Pipeline - A 7-layer LangGraph system that transforms job descriptions into hyper-personalized CVs, cover letters, and outreach packages using AI agents.

**Key Components**:
- Frontend: Vercel Flask app (job-search-inky-sigma.vercel.app)
- Runner: VPS FastAPI service (72.61.92.76) with subprocess execution
- Pipeline: MongoDB-driven LangGraph workflow (Layers 1-7)
- Database: MongoDB Atlas with job collection, company cache, star records

---

## Current Session: Prompt Optimization Initiative

### Phase 1: COMPLETED - A/B Testing Infrastructure

**Objective**: Build framework to scientifically evaluate and improve prompts across 3 critical layers (Layer 4, 6a, 6b).

#### 1. Created Comprehensive Master Plan
**File**: `/Users/ala0001t/pers/projects/job-search/plans/prompt-optimization-plan.md` (1778 lines)

**Contents**:
- **Section A**: Current State Analysis
  - Layer 4 (Opportunity Mapper): 4 issues identified
    - Weak grounding: rationales don't cite specific evidence
    - No chain-of-thought: missing visible reasoning
    - Generic rationales: boilerplate passes validation
    - Context overload: irrelevant information cited

  - Layer 6a (Cover Letter Generator): 4 issues identified
    - Rigid structural constraints (forcing 3-4 paragraphs)
    - Weak pain point integration
    - Generic company research usage
    - STAR grounding issues

  - Layer 6b (CV Generator): 4 issues identified
    - Master CV interpretation gaps
    - STAR selection limitations
    - Role-specific nuance missing
    - Prompt gaps and validation weaknesses

- **Section B**: Proposed Improvements
  - Universal Prompt Template (8 blocks)
    1. PERSONA BLOCK - specific role with reputation stakes
    2. MISSION STATEMENT - single measurable outcome
    3. CONTEXT SECTIONS - structured data with sources
    4. REASONING STAGE - chain-of-thought before output
    5. CONSTRAINTS & FORMAT - hard rules + JSON schema
    6. FEW-SHOT EXAMPLES - domain-specific examples
    7. SELF-EVALUATION LOOP - quality scoring post-draft
    8. ANTI-HALLUCINATION GUARDRAILS - fact-only grounding

  - Layer 4 V2 improvements with enhanced persona, 4-step reasoning framework, few-shot examples
  - Layer 6a V2 improvements with dual identity (marketer + skeptical hiring manager), 3-phase structure
  - Layer 6b V2 improvements with master CV parser, competency mix analysis, hallucination QA

- **Section C**: Testing Strategy (TDD approach)
  - Write failing tests first
  - Implement prompt changes
  - Verify tests pass
  - Add regression tests

- **Section D**: Implementation Roadmap (7 weeks)
  - Week 1-2: Layer 4 improvements (4 issues x 3 iterations)
  - Week 3-4: Layer 6a improvements (4 issues)
  - Week 5-6: Layer 6b improvements (4 issues)
  - Week 7: Integration testing + final analysis

- **Section G**: A/B Testing Methodology
  1. BASELINE: Run current prompt with 3 test jobs, capture scores (specificity, grounding, hallucinations)
  2. ENHANCED: Apply technique, run same 3 jobs, capture scores
  3. ANALYZE: Compare side-by-side, calculate deltas
  4. ITERATE: If delta < target, refine prompt (max 3 iterations)
  5. DISPLAY: Output comparison table + recommendations

#### 2. Built A/B Testing Infrastructure (48 Tests Passing)

**Test Framework Files**:

- `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/framework.py` (90+ lines)
  - `ABTestRunner` class with methods:
    - `run_baseline()` - Execute baseline prompt on test jobs
    - `run_enhanced(technique)` - Execute enhanced prompt variant
    - `compare()` - Side-by-side comparison with delta calculation
    - `generate_analysis_report()` - Markdown output with recommendations
  - `OutputResult` dataclass - Single job result with scores + metadata
  - `ABTestResult` dataclass - Aggregated results with averages
  - `Comparison` dataclass - Baseline vs enhanced with deltas

- `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/scorers.py` (416 lines)
  - `score_specificity()` - Detects generic phrases, counts metrics, company mentions, tech terms (1-10 scale)
  - `score_grounding()` - STAR citations, pain point references, signal usage (1-10 scale)
  - `score_hallucinations()` - Detects unknown companies, unverified metrics (1-10 scale, higher = fewer hallucinations)
  - `calculate_combined_score()` - Weighted average (specificity: 0.3, grounding: 0.4, hallucinations: 0.3)
  - `ScoreResult` dataclass - Score + details + feedback
  - Metric patterns: Percentages, multipliers, dollars, time, team size, user counts
  - Generic phrase library: 17 common boilerplate phrases

- `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/conftest.py` (Shared fixtures)
  - 3 test jobs with realistic data (from MongoDB + synthetic)
  - Master CV fixture with STAR achievements
  - Sample state object for testing

- `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/__init__.py` - Package marker

#### 3. Created Test Suite (48 tests across 3 modules)

**Test Modules**:

1. `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/test_layer4_ab.py` (18 tests)
   - TestWeakGrounding (5 tests)
     - test_baseline_captures_current_behavior
     - test_baseline_detects_weak_grounding
     - test_enhanced_applies_anti_hallucination_guardrails
     - test_comparison_shows_grounding_improvement
     - test_analysis_report_generated

   - TestNoChainOfThought (3 tests)
     - test_baseline_lacks_reasoning_steps
     - test_enhanced_includes_reasoning_blocks
     - test_comparison_measures_reasoning_presence

   - TestGenericRationales (3 tests)
     - test_baseline_allows_generic_phrases
     - test_enhanced_eliminates_generic_phrases
     - test_specificity_score_improves

   - TestContextOverload (3 tests)
     - test_baseline_cites_excessive_context
     - test_enhanced_prioritizes_context
     - test_comparison_measures_focus_improvement

   - TestScorerIntegration (4 tests)
     - test_specificity_scorer_detects_generic_text
     - test_specificity_scorer_rewards_specific_text
     - test_grounding_scorer_requires_star_citations
     - test_hallucination_scorer_detects_unknown_companies

2. `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/test_layer6a_ab.py` (14 tests)
   - TestRigidStructure (3 tests)
   - TestWeakPainPoints (3 tests)
   - TestGenericResearch (3 tests)
   - TestSTARGrounding (3 tests)
   - TestCoverLetterScorerIntegration (2 tests)

3. `/Users/ala0001t/pers/projects/job-search/tests/ab_testing/test_layer6b_ab.py` (16 tests)
   - TestRegexParsing (3 tests)
   - TestRoleSelection (3 tests)
   - TestGenericSummaries (3 tests)
   - TestHallucinationGaps (4 tests)
   - TestCVScorerIntegration (3 tests)

**All 48 tests currently PASSING** (verified 2025-11-28)

#### 4. Created Reports Directory Structure
```
reports/prompt-ab/
├── layer4/
│   ├── weak-grounding/
│   ├── no-cot/
│   ├── generic-rationales/
│   └── context-overload/
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

---

## Pending Work: Phases 2-5

### Phase 2: Layer 4 A/B Testing (Layer 4 - Opportunity Mapper)

**Timeline**: Week 2-3
**Issues to Test**: 4 total

1. **Weak Grounding Issue**
   - Technique: Anti-hallucination guardrails (technique 3.4 from thoughts/prompt-modernization-blueprint.md)
   - Target: Improve grounding score from baseline to 8.0+
   - Test Strategy: Run baseline, apply guardrails, compare with test_layer4_ab.py tests
   - Iterations: Max 3 refinements

2. **No Chain-of-Thought Issue**
   - Technique: Reasoning-first approach (technique 2.2)
   - Target: Add visible reasoning steps, improve specificity by 20%
   - Test Strategy: Use test_layer4_ab.py::TestNoChainOfThought tests
   - Iterations: Max 3 refinements

3. **Generic Rationales Issue**
   - Technique: Constraint prompting (technique 3.5)
   - Target: Reduce generic phrases to 0, specificity score 8.5+
   - Test Strategy: Use test_layer4_ab.py::TestGenericRationales tests
   - Iterations: Max 3 refinements

4. **Context Overload Issue**
   - Technique: Context prioritization (technique 2.3)
   - Target: Focus on most relevant context, reduce irrelevant citations
   - Test Strategy: Use test_layer4_ab.py::TestContextOverload tests
   - Iterations: Max 3 refinements

### Phase 3: Layer 6a A/B Testing (Cover Letter Generator)

**Timeline**: Week 4
**Issues to Test**: 4 total

1. Rigid structural constraints
2. Weak pain point integration
3. Generic company research usage
4. STAR grounding issues

### Phase 4: Layer 6b A/B Testing (CV Generator)

**Timeline**: Week 5-6
**Issues to Test**: 4 total

1. Master CV interpretation gaps
2. STAR selection limitations
3. Role-specific nuance missing
4. Prompt validation gaps

### Phase 5: Integration & Final Analysis

**Timeline**: Week 7
**Deliverables**:
- Integrated V2 prompts into pipeline
- End-to-end testing with real MongoDB jobs
- Performance comparison report
- Recommendations for production rollout

---

## Key Reference Documents

### Prompting Guides (in thoughts/)
- `/Users/ala0001t/pers/projects/job-search/thoughts/prompt-generation-guide.md` - Universal techniques (8-block template, reasoning patterns, few-shot strategy)
- `/Users/ala0001t/pers/projects/job-search/thoughts/prompt-modernization-blueprint.md` - Layer-specific improvements with numbered techniques
- `/Users/ala0001t/pers/projects/job-search/thoughts/change.md` - Vision for role-play flow

### Planning Documents (in plans/)
- `/Users/ala0001t/pers/projects/job-search/plans/architecture.md` - System design, layers, execution surfaces
- `/Users/ala0001t/pers/projects/job-search/plans/missing.md` - Implementation gaps tracking
- `/Users/ala0001t/pers/projects/job-search/plans/prompt-optimization-plan.md` - Master optimization plan (THIS SESSION)

### Implementation Files (in src/)
- `/Users/ala0001t/pers/projects/job-search/src/layer4/opportunity_mapper.py` - Current Layer 4 implementation
- `/Users/ala0001t/pers/projects/job-search/src/layer6/cover_letter_generator.py` - Current Layer 6a implementation
- `/Users/ala0001t/pers/projects/job-search/src/layer6/cv_generator.py` - Current Layer 6b implementation

---

## A/B Testing Protocol (Quick Reference)

### For Each Issue:

1. **Setup Test Job**:
   - Use test fixtures from conftest.py
   - Prepare state object with pain_points, selected_stars, company_research

2. **Run Baseline**:
   ```python
   runner = ABTestRunner(layer="layer4", issue="weak-grounding", test_jobs=[...])
   baseline = runner.run_baseline()
   print(f"Baseline grounding score: {baseline.avg_grounding}")
   ```

3. **Apply Enhancement**:
   - Edit prompt in relevant layer file
   - Apply technique from thoughts/*.md
   - Save changes

4. **Run Enhanced**:
   ```python
   enhanced = runner.run_enhanced(technique="anti-hallucination-guardrails")
   print(f"Enhanced grounding score: {enhanced.avg_grounding}")
   ```

5. **Compare & Analyze**:
   ```python
   comparison = runner.compare(baseline, enhanced)
   runner.generate_analysis_report(comparison)
   ```

6. **Iterate if Needed**:
   - If improvement < target: refine prompt further
   - Max 3 iterations per issue
   - Document refinements in analysis report

---

## Test Job Data

### Test Job 1: Kaizen Gaming (Real from MongoDB)
- Job ID: `6929c97b45fa3c355f84ba2d`
- Role: Software Engineering Team Lead
- Company: Kaizen Gaming
- Industry: Gaming/Tech
- Key Pain Points: Team coordination, technical debt, scaling

### Test Job 2: FinSecure Technologies (Synthetic)
- Role: Compliance Officer
- Industry: FinTech
- Key Pain Points: Regulatory compliance, risk management, audit trails

### Test Job 3: GlobalTech Enterprise (Synthetic)
- Role: Infrastructure Architect
- Industry: Enterprise Tech
- Key Pain Points: System reliability, cost optimization, cloud migration

---

## Git Workflow

**Current Branch**: `prompt-optimisation`
**Main Branch**: `main` (406c9bac - ahead 1)

**Commit Convention**:
- No Claude signature (per CLAUDE.md)
- Atomic commits
- Run unit tests before committing
- Format: `feat(layer4): Add chain-of-thought to opportunity mapper`

**Recent Commits**:
```
25e15e0a feat(testing): Add A/B testing infrastructure for prompt optimization
a35dc737 chore: add more files
b8b249d7 test(layer3): add Phase 5.2 comparison and validation tests
b91280f4 feat(layer3): implement Phase 5.2 enhanced company research
b28f09e5 docs: update tracking after bug fixes (2025-11-28)
```

---

## Running Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all A/B tests
python -m pytest tests/ab_testing -v

# Run specific test class
python -m pytest tests/ab_testing/test_layer4_ab.py::TestWeakGrounding -v

# Run with coverage
python -m pytest tests/ab_testing --cov=tests.ab_testing -v

# Quick test (no capture)
python -m pytest tests/ab_testing -s
```

**Current Status**: All 48 tests PASSING

---

## Environment Setup

**Key Environment Variables** (in .env):
- `OPENROUTER_API_KEY` - LLM calls (OpenRouter)
- `MONGODB_URI` - MongoDB Atlas connection
- `FIRECRAWL_API_KEY` - Web scraping (Company research)
- `USE_ANTHROPIC=false` - Use OpenRouter instead of Anthropic (credit conservation)
- `ENABLE_STAR_SELECTOR=false` - Disable STAR selector (default)

**Python**: 3.11.9
**Virtual Env**: `.venv/` (activated with `source .venv/bin/activate`)

---

## Critical Notes for Next Session

1. **Do NOT edit prompt files during A/B testing** - Changes go through the framework only
2. **All 48 tests must remain PASSING** - Add regression tests after each change
3. **Documentation hierarchy**:
   - `plans/prompt-optimization-plan.md` - Master reference
   - `tests/ab_testing/` - Test implementations
   - `reports/prompt-ab/` - Results and analysis
4. **Phase 1 is COMPLETE** - Phase 2 starts with Layer 4 weak grounding issue
5. **Success criteria**: Improvement deltas >= targets with zero test regressions
6. **Maximum iterations**: 3 per issue (if < target after 3, re-evaluate technique)

---

## Agent Delegation Recommendation

For next session:
- **Starting work**: Use `session-continuity` agent to restore context
- **Phase 2 (Layer 4)**: Use `test-generator` to expand test coverage, then `prompt-optimisation` (custom agent or `job-search-architect`) to refine prompts
- **Phase 3-4 (Layers 6a, 6b)**: Same approach
- **Integration Phase**: Use `pipeline-analyst` to validate outputs end-to-end

---

## Files Modified This Session

1. Created (new):
   - `plans/prompt-optimization-plan.md` (1778 lines)
   - `tests/ab_testing/__init__.py`
   - `tests/ab_testing/framework.py`
   - `tests/ab_testing/scorers.py`
   - `tests/ab_testing/conftest.py`
   - `tests/ab_testing/test_layer4_ab.py`
   - `tests/ab_testing/test_layer6a_ab.py`
   - `tests/ab_testing/test_layer6b_ab.py`

2. Directories Created:
   - `reports/prompt-ab/` (with layer4, layer6a, layer6b subdirectories)

3. Updated:
   - `bugs.md` - Added prompt optimization tasks (#4, #5, #6)
   - `.gitignore` - Added report directories

---

## Quick Start for Next Session

1. **Activate virtual environment**:
   ```bash
   cd /Users/ala0001t/pers/projects/job-search
   source .venv/bin/activate
   ```

2. **Verify tests still pass**:
   ```bash
   python -m pytest tests/ab_testing -v
   ```

3. **Review master plan**:
   ```bash
   cat plans/prompt-optimization-plan.md | head -100
   ```

4. **Start Phase 2 (Layer 4)**:
   - Edit `/Users/ala0001t/pers/projects/job-search/src/layer4/opportunity_mapper.py`
   - Apply technique from `thoughts/prompt-modernization-blueprint.md` (technique 3.4 for grounding)
   - Run tests to verify improvement
   - Document in `reports/prompt-ab/layer4/weak-grounding/`

---

**Session Created**: 2025-11-28 22:45 UTC
**Prepared by**: Session Continuity Agent (Haiku)
**Next Steps**: Execute Phase 2 (Layer 4 A/B Testing)
