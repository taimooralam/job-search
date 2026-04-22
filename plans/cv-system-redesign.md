# CV System Redesign — Implementation Plan

## Context

A 24-hour diagnostic across 127 pipeline-generated CVs showed 63% WEAK_MATCH, 31% NEEDS_WORK, only 5% GOOD_MATCH. Root causes confirmed by code review:

1. **Header over-positions**: `header_generator.py:158` uses `[EXACT JD TITLE] | [X]+ Years Technology Leadership` — mirrors JD title verbatim, causing "AI Architect" claims without evidence
2. **Review system misses project files**: `master_cv_store.py:get_candidate_profile_text()` does NOT include `data/master-cv/projects/commander4.md` or `lantern.md` — causes false hallucination flags on Commander-4/Lantern claims
3. **No architect persona**: `ensemble_header_generator.py` has METRIC/NARRATIVE/KEYWORD personas but no ARCHITECT persona
4. **AI evidence concentrated**: Only Role 01 (Seven.One) has AI evidence (Achievements 15-18). Roles 02-06 have zero AI content
5. **ARIS vs CARS confusion**: `role_generation.py` teaches ARIS format, `cv_generation_prompts.py` teaches CARS — no resolution of which to use when
6. **Grading lacks architect gates**: `grader.py` has no identity-to-impact bridge scoring or architecture-depth dimension

**Goal**: Non-hallucinated, ATS-heavy CVs that position Taimoor as an architect-level systems leader with credible AI platform evidence.

---

## Iteration 1: Foundation — Header Guardrails + Review Fix ✅ COMPLETE

> All items completed 2026-04-12:
> - 1A: Project files in reviewer context (cv_review_service.py B2 fix)
> - 1B: Headline grounding rules (A1 prompt fix) + `resolve_headline()` code enforcement
> - 1C: Evidence-first tagline ordering (A2 prompt fix)
> - 1D: Achievement diversity enforcement (`enforce_achievement_diversity()` post-LLM filter)
> - 1E: `headline_resolver.py` shared resolver for header_generator + orchestrator

### 1A. Fix Review System Source Truth (HIGHEST PRIORITY — unblocks feedback loop)

**File**: `src/common/master_cv_store.py`
**Function**: `get_candidate_profile_text()` (~lines 745-900)
**Problem**: Does not include `data/master-cv/projects/commander4.md` or `lantern.md`. Reviewer flags Commander-4 claims as hallucinations.
**Change**: After loading roles, also load and append project files from `data/master-cv/projects/`. Add a `## AI Projects` section to the profile text with pre-written project bullets.
**Impact**: Reviewer will stop flagging valid Commander-4/Lantern claims. No pipeline changes needed.
**Test**: Run `trigger_review.py` on a known GOOD_MATCH job → verify Commander-4 claims no longer flagged.

### 1B. Fix Headline Formula

**File**: `src/layer6_v2/prompts/header_generation.py`
**Current** (line ~11): `"Candidates with exact job title are 10.6x more likely to get interviews"`
**Current formula** (~line 158): `[CLEANED JD TITLE] | [X]+ Years Technology Leadership`
**Problem**: Mirrors JD title verbatim. If JD says "AI Architect", CV claims "AI Architect" without evidence.
**Change**: Replace with evidence-bounded title policy:
  - Base identity: `Software Architect | Engineering Leader` (always safe)
  - AI-adapted: `AI Platform Architect | Engineering Leader` (only when `ai_architect` or `ai_leadership` role detected AND current role has AI achievements)
  - Keep years count but change suffix: `[X]+ Years Architecture & Technology Leadership`
  - Add negative examples: "NEVER claim a title the candidate has not held unless the evidence directly supports it"
**Impact**: All downstream header generation uses this prompt. Ensemble personas inherit it.
**Test**: Score 10 sample jobs → verify headlines no longer mirror exotic JD titles.

### 1C. Add Proof-Ladder Rules to Tagline

**File**: `src/layer6_v2/prompts/header_generation.py`
**Current tagline rules** (~lines 44-65): "15-25 words, third-person absent voice, persona-driven hook"
**Problem**: No structure requiring identity → capability → outcome sequence.
**Change**: Add tagline template: `[Architect identity] building/designing [system type] that [delivers outcome] through [verified capability]`
  - Add 3 good examples grounded in master CV evidence
  - Add 3 bad examples showing over-positioning
  - Require at least one verifiable capability claim
**Test**: Generate 5 taglines → verify each follows proof-ladder structure.

### 1D. Update Key Achievement Selection Rules

**File**: `src/layer6_v2/prompts/header_generation.py`
**Current** (~lines 72-73): "Each bullet MUST START with ACTION verb + specific SKILLS/TECHNOLOGIES"
**Change**: Add achievement selection requirements:
  - At least 1 bullet from platform/architecture (3 years zero downtime, 75% incident reduction)
  - At least 1 bullet from AI platform (Commander-4/Lantern) when targeting AI roles
  - At least 1 bullet showing leadership/team impact
  - No more than 2 bullets from the same role
**Test**: Check 5 generated headers → verify achievement diversity.

### 1E. Header Generator Code Changes

**File**: `src/layer6_v2/header_generator.py`
**Function**: `generate()` (line ~1471) and headline construction (~line 158)
**Change**:
  - Add `_resolve_evidence_bounded_headline()` function that checks:
    - Does candidate hold a title matching the JD? → use it
    - Does candidate have AI evidence (Achievement 15+)? → allow "AI Platform" modifier
    - Otherwise → use base identity from `role_metadata.json`
  - Load `title_base` from metadata instead of cleaning JD title
**Impact**: Ensemble header generator inherits corrected headline since it calls the same prompt.
**Test**: Unit test with mock JD titles → verify headline stays evidence-bounded.

**Verification for Iteration 1**:
1. Run cv-review on 5 known jobs → Commander-4 false flags should disappear
2. Generate CVs for 5 architect-fit jobs → headlines should not mirror exotic titles
3. Run existing tests: `.venv/bin/pytest tests/unit/ -v --ignore='tests/unit/test_integration*' --ignore='tests/unit/test_bulk*'`

---

## Iteration 2: Quality — Bullet Strategy + AI Highlights Section (partially complete)

> Completed 2026-04-12:
> - 2B: Architecture variant 1.5x boost for ai_architect/ai_leadership roles
> - 2C: Pain point rebalancing (post-selection, 12 tests) — fill + swap phases, base_score gate
> - 2D: ARIS vs CARS scope documentation

### 2A. Add AI Architecture Highlights Section

> **Detailed sub-plan**: [`plans/cv-system-redesign-2a-ai-highlights.md`](cv-system-redesign-2a-ai-highlights.md) (658 lines — full implementation spec with data file, orchestrator integration, dedup logic, ATS format, and sample output)

**File**: `src/layer6_v2/orchestrator.py`
**Location**: After Phase 5 (header generation), before Phase 6 (grading)
**Design**: New section placed between Core Competencies and Professional Experience
  - Only triggered for AI/architect/platform jobs (check `detected_role` in `ai_architect`, `ai_leadership`, `staff_principal_engineer`)
  - 3-4 bullets from AI portfolio (Commander-4 Achievements 15-18 + Lantern project)
  - Each bullet: `[Architecture capability] → [technique/skill used] → [measurable outcome]`
  - Deduplicate against header key achievements
**ATS Safety**: Plain text heading "AI & Platform Architecture" + standard bullet format. No tables, columns, or non-standard markup. ATS systems parse this as another skills/summary block.
**New file**: `data/master-cv/ai_portfolio.json` — structured AI evidence:
```json
{
  "highlights": [
    {
      "id": "commander4_retrieval",
      "text": "Designed hybrid retrieval architecture (BM25 + RRF fusion + LLM-as-judge reranking) for enterprise AI platform serving 2,000 users",
      "source_role": "01",
      "source_achievement": "15",
      "skills": ["RAG", "BM25", "Reranking", "LLM-as-Judge"],
      "metrics": ["2,000 users"],
      "architect_tags": ["system_design", "retrieval_architecture"]
    }
  ]
}
```
**Test**: Generate CV for AI architect job → verify section appears with 3-4 grounded bullets.

### 2B. Strengthen Variant Selection for Architect Roles

**File**: `src/layer6_v2/variant_selector.py`
**Current** (lines 47-70): Role category preferences hardcoded — `ai_architect: [Technical, Architecture, Impact, Short]`
**Change**:
  - Boost "Architecture" variant type weight for all architect/leadership roles (not just staff/principal)
  - Add architecture-specific pain point keywords: "system design", "scalability", "technical vision", "platform", "reliability"
  - When detected role is `ai_architect` or `ai_leadership`, boost architecture variants by 1.5x multiplier
**Impact**: Variant selection will prefer architecture-framed bullets over generic technical ones.
**Test**: Score variants for 5 architect JDs → verify Architecture variants rank higher.

### 2C. Pain Point Rebalancing (Post-Selection)

**Diagnostic finding**: Mean pain point coverage is 37%, max 73%. Zero jobs reach 75%. The bullet selection logic optimizes for general JD relevance rather than explicit pain-point-to-achievement mapping. Infrastructure already exists: `matched_pain_point` field on `VariantScore` (variant_selector.py:104) is populated during scoring (variant_selector.py:568) but never used for coverage optimization.

**Files**:
- `src/layer6_v2/variant_selector.py` — add `_rebalance_for_pain_points()` method
- `src/layer6_v2/role_generator.py` — propagate `matched_pain_point` to bullets (line 574)

**Critical constraint (Codex review)**: `variant_selector.py:405` has forced AI-achievement insertion logic that runs AFTER initial selection for `ai_architect`/`ai_leadership` roles on Seven.One. Pain point rebalancing MUST run AFTER this forced insertion to avoid overwriting AI constraints and must recalculate coverage accounting for AI-forced bullets.

**Algorithm** — new method `_rebalance_for_pain_points()` on `VariantSelector`:
1. Called after initial selection AND after forced AI-achievement insertion (line ~440)
2. Identify which pain points are covered by selected variants via `matched_pain_point`
3. If coverage < 60%, build pool of unselected variants addressing uncovered pain points
4. For each candidate swap: replace weakest selected bullet IF:
   - The weakest bullet is NOT the sole coverage for another pain point
   - The weakest bullet is NOT a forced AI achievement (preserve AI constraint)
   - The candidate's score is at least 70% of the weakest's score
5. Stop when coverage >= 60% or no more swaps available

**Integration point**: In `select_variants()`, after the forced AI-achievement block (after line ~440), before `SelectionResult` is returned. Pass `extracted_jd["implied_pain_points"]`.

**role_generator.py change** (line 574): Propagate pain point from variant score:
```python
# Current: pain_point_addressed=None,
# New:
pain_point_addressed=selected.score.matched_pain_point if selected.score.matched_pain_point else None,
```

**Test strategy** — add to `tests/test_variant_selector.py`:
- 5 pain points, 3 covered by initial selection → verify swap brings coverage to 4-5
- All pain points already covered → verify no swaps (no-op)
- Empty pain points list → verify no-op
- Forced AI achievement protection → verify AI-forced bullet never swapped out
- Sole-coverage protection → bullet uniquely covering a pain point never swapped out
- Score threshold → candidate scoring <70% of weakest never swapped in

**Expected impact**: Mean pain point coverage 37% → 55%+. GOOD_MATCH rate improves as pain point coverage is the strongest predictor of positive review verdicts.

### 2D. Resolve ARIS vs CARS Confusion

**File**: `src/layer6_v2/prompts/role_generation.py` (line 71-102) and `cv_generation_prompts.py` (line 189-204)
**Decision**: Use ARIS for role bullets (25-40 words, detailed). Use summary-style for header bullets (8-15 words, concise). Add explicit comments documenting this division.
**Change**: Add comment block at top of each file clarifying scope. No functional change needed — current usage pattern is already correct, just undocumented.

### 2E. Update Grading Dimensions

> **Detailed sub-plan**: [`plans/cv-system-redesign-2e-identity-bridge-grading.md`](cv-system-redesign-2e-identity-bridge-grading.md) (634 lines — full implementation spec with dimension scoring, weight tables, rubric prompt, pydantic changes, and test strategy)

**File**: `src/layer6_v2/grader.py`
**Current weights**: ATS 20%, Impact 25%, JD Alignment 25%, Executive Presence 15%, Anti-Hallucination 15%
**New weights for architect roles** (when detected_role in architect categories):
  - JD Alignment: 22%
  - Anti-Hallucination: 20% (increased — grounding is critical for pivot positioning)
  - Impact & Clarity: 20%
  - ATS Optimization: 15%
  - Executive Presence: 13%
  - NEW gate: Identity-to-Impact Bridge: 10% (headline evidence-bounded, tagline has proof, AI highlights present for AI jobs)
**Implementation**: Add `_grade_identity_bridge()` method that checks:
  - Headline doesn't claim unearned titles
  - Tagline contains at least one verifiable claim
  - AI highlights section present when job is AI-targeted
**Test**: Grade 5 existing GOOD_MATCH CVs → verify they still pass under new weights.

**File**: `src/layer6_v2/prompts/grading_rubric.py`
**Change**: Add identity-bridge dimension description and scoring criteria.

**Verification for Iteration 2**:
1. Generate CVs for 5 AI architect jobs → verify AI highlights section appears
2. Check pain point coverage → should be >50% on top-3 pain points
3. Grade existing GOOD_MATCH CVs → must still pass (no regression)
4. Run full test suite

---

## Iteration 3: Feedback Loop — Review Integration (partially complete)

> Completed 2026-04-12:
> - 3A: Project files in reviewer context (implemented as B2 in quality fixes batch)
> - 3B: Structured review taxonomy — failure_modes, headline_evidence_bounded, bridge_quality_score

### 3A. Add Project Files to Review Context

**File**: `src/services/cv_review_service.py`
**Change**: In `execute()`, after loading master CV text, also load project files and append to context. Increase char limit from 8000 to 10000 to accommodate.
**Test**: Review a CV with Commander-4 claims → verify no false hallucination flags.

### 3B. Structured Review Taxonomy

**File**: `src/services/cv_review_service.py`
**Current**: Review produces nested JSON with `full_review` containing 8 sections
**Change**: Add top-level classification fields for automated tracking:
  - `failure_modes`: list of enum values: `headline_overclaim`, `tagline_proof_gap`, `missing_ai_evidence`, `hallucination_project_context`, `thin_competencies`, `low_pain_point_coverage`
  - `headline_evidence_bounded`: bool
  - `bridge_quality_score`: 1-10
**Test**: Review 5 CVs → verify failure_mode classification is accurate.

### 3C. Update VPS Review Scripts

**File**: `n8n/skills/cv-review/scripts/show_review.py`
**Change**: Display new structured fields (failure_modes, bridge_quality_score). Add summary stats line.
**Deploy**: SCP updated scripts to VPS `/root/scout-cron/`

**Verification for Iteration 3**:
1. Run batch review on 10 jobs → verify structured failure_modes populated
2. Compare failure patterns to the 24-hour diagnostic baseline
3. Deploy to VPS and run one review cycle

---

## Iteration 4: Optimization — Token Savings + Pipeline Integration (partially complete)

> Completed 2026-04-12:
> - 4D: Negative scoring integration — cap GOLD/SILVER to BRONZE when jdNegativeHard > 20 or experienceMismatch > 15

### 4A. Collapse Ensemble Passes

> **Detailed sub-plan**: [`plans/cv-system-redesign-4a-architect-persona.md`](cv-system-redesign-4a-architect-persona.md) (616 lines — full implementation spec with ARCHITECT persona prompt, tier reconfiguration, synthesis changes, token budget, and test strategy)

**File**: `src/layer6_v2/ensemble_header_generator.py`
**Current**: GOLD=3 passes (~6.5K tokens), SILVER=2 passes (~4.5K tokens)
**Change**: GOLD=2 passes (METRIC + ARCHITECT) + synthesis. Drop NARRATIVE persona (replaced by proof-ladder tagline rules from Iteration 1). Add new ARCHITECT persona that emphasizes system design, platform thinking, and architecture decisions.
**Token savings**: ~2K tokens per GOLD-tier CV (30% reduction on header generation)
**Test**: Generate 5 GOLD-tier headers → verify quality not degraded.

### 4B. Tier-Based Pass Pruning

**File**: `src/layer6_v2/orchestrator.py`
**Change**: For BRONZE tier, skip grading improvement loop entirely (generate once, accept). For SILVER, skip ensemble synthesis (use best single-persona result).
**Token savings**: ~1.5K tokens per BRONZE CV, ~1K per SILVER
**Test**: Generate 5 BRONZE CVs → verify acceptable quality without grading loop.

### 4C. Evidence Bundle Context Curation

**File**: `src/layer6_v2/role_generator.py`
**Change**: Instead of passing full role markdown to LLM generation, extract and pass only:
  - Selected achievement variants (pre-scored)
  - Matched pain points
  - Relevant skills from whitelist
  - Compact evidence bundle (~500 tokens instead of ~2000)
**Token savings**: ~1.5K tokens per role with LLM generation
**Test**: Compare bullet quality with full context vs curated context on 5 jobs.

### 4D. Deploy Negative Scoring Integration

**File**: `src/layer6_v2/orchestrator.py`
**Change**: Read `rule_score` breakdown from job document. If `jdNegativeHard < -20` or `experienceMismatch < -15`, auto-downgrade to BRONZE tier regardless of fit_score. This prevents expensive generation on jobs the negative scorer already flagged as poor fits.
**Test**: Generate CV for a PyTorch-heavy job → verify BRONZE tier selected.

**Verification for Iteration 4**:
1. Measure token usage before/after on 10 jobs → target 25-35% reduction
2. Quality spot-check: no GOOD_MATCH CVs degraded by pass pruning
3. Negative scoring integration: bad-fit jobs use BRONZE path

---

## File Change Manifest

| File | Change | Iteration | Est. Lines |
|------|--------|-----------|------------|
| `src/common/master_cv_store.py` | Add project file loading | 1A | +30 |
| `src/layer6_v2/prompts/header_generation.py` | Headline formula, tagline rules, achievement rules | 1B-1D | +80, ~40 modified |
| `src/layer6_v2/header_generator.py` | Evidence-bounded headline resolver | 1E | +50 |
| `data/master-cv/ai_portfolio.json` | New structured AI evidence | 2A | +60 (new file) |
| `src/layer6_v2/orchestrator.py` | AI highlights section assembly, tier pruning, negative score integration | 2A, 4B, 4D | +80 |
| `src/layer6_v2/variant_selector.py` | Architecture variant boosting | 2B | +20 |
| `src/layer6_v2/variant_selector.py` | Pain point rebalancing (post-selection, post-AI-force) | 2C | +60 |
| `src/layer6_v2/role_generator.py` | Pain point propagation, evidence bundles | 2C, 4C | +40 |
| `tests/test_variant_selector.py` | Pain point rebalancing unit tests | 2C | +80 |
| `src/layer6_v2/prompts/role_generation.py` | ARIS scope documentation | 2D | +10 |
| `src/layer6_v2/prompts/cv_generation_prompts.py` | CARS scope documentation | 2D | +10 |
| `src/layer6_v2/grader.py` | New weights, identity-bridge dimension | 2E | +60 |
| `src/layer6_v2/prompts/grading_rubric.py` | Identity-bridge criteria | 2E | +30 |
| `src/services/cv_review_service.py` | Project context, structured taxonomy | 3A-3B | +40 |
| `n8n/skills/cv-review/scripts/show_review.py` | Display new fields | 3C | +15 |
| `src/layer6_v2/ensemble_header_generator.py` | ARCHITECT persona, collapsed passes | 4A | +40, ~30 modified |

---

## Success Metrics

| Metric | Before | Target |
|--------|--------|--------|
| GOOD_MATCH rate | 5% | >20% |
| WEAK_MATCH rate | 63% | <35% |
| Headline over-positioning flags | 94% | <20% |
| Pain point coverage (mean) | 37% | >55% |
| Commander-4 false hallucination flags | High | Near zero |
| Token cost per quality-tier CV | ~$0.26 | <$0.19 |
| Thin competencies flags | 88% | <30% |

## Rollback Plan

Each iteration is independently deployable and reversible:
- **Iter 1**: Revert prompt file changes (git checkout). Review fix is additive-only.
- **Iter 2**: Feature-flag AI highlights section. Revert variant boost multiplier. Grading weights configurable.
- **Iter 3**: Review taxonomy is additive — old format still works.
- **Iter 4**: Ensemble persona swap is behind tier routing. Token optimization reverts by restoring full context pass.
