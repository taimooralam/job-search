# CV Pipeline Overhaul Plan

## Context

The CV generation pipeline produces ~3,100 CVs but reviewer diagnostics show 63% WEAK_MATCH, 31% NEEDS_WORK, only 5% GOOD_MATCH. Root causes span five dimensions: architecture inefficiencies (45% token waste, Sonnet calls where Haiku/Codex suffice), weak AI positioning in generated output, no eval framework to measure quality, extraction/research happening too late in the VPS cron flow, and master CV not fully leveraging docs/archive and docs/current intelligence. This plan addresses all five.

**Source documents:** `reports/pipeline-skill-model-analysis-2026-04-12.md`, `reports/cv-pipeline-audit-2026-04-12.md`, `docs/current/architecture.md`, `docs/current/cv-generation-guide.md`, `docs/archive/`

---

## Execution Strategy: Foundational First, Then Iterative

**Foundational work** (do once, compounds across everything):
1. **Eval Framework** (Phase 2) — can't improve what you can't measure
2. **Architecture Refactoring** (Phase 3) — cost/efficiency, run evals cheaply
3. **Early Extraction** (Phase 4) — enriched data before pipeline runs

**Iterative work** (run repeatedly, guided by eval scores):
4. **Master CV Enhancement** (Phase 1) — improve source material, re-eval
5. **Live-Tail Integrity** (Phase 5) — continuous, verify after each phase

**Recommended order: 2 → 3 → 4 → 1 → 5 (continuous)**

Rationale: Build the eval first so every subsequent change is measurable. Then fix the architecture so eval runs are cheap. Then move extraction earlier so pipeline gets better input. Then iteratively curate evidence and improve the master CV, re-running evals after each round to track progress.

---

## Phase 2: Eval Framework (BUILD FIRST — Measurement Foundation)

**Goal:** Mine real job data from MongoDB, build category composites, score the current curated evidence store plus upstream-evidence curation completeness and current master-CV representation against each category, and create reusable eval rubrics for scoring generated CVs.

**Detailed sub-plan:** [`plans/cv-eval-foundation.md`](cv-eval-foundation.md)

**Summary of 11 steps:**

| Step | What | Key Output |
|------|------|------------|
| 0 | Methodology & evidence discipline | Tagging rules, counting rules, dedup rules |
| 1 | Data extraction from MongoDB | All eligible jobs across 4 signal tiers (weighted) |
| 2 | Category assignment | 15 categories, primary + secondary classification |
| 3 | Per-job normalized analysis | Full corpus counts + 20 deep exemplars/category |
| 4 | Category market composites | Skills, leadership, architecture, pain points per bucket |
| 5 | Top-third CV blueprint per category | Headline, tagline, competencies, tone guidance |
| 6 | Pre-generation curated-evidence + curation-completeness + master-CV representation baseline | 0-10 fit score per category, split into evidence coverage, curation completeness, and representation quality |
| 7 | Reusable CV eval rubrics | 5 dimensions x 2 layers (category core + job overlay) |
| 8 | Scorecard template | JSON template for longitudinal tracking |
| **8b** | **Intermediate stage eval rubrics** | **Per-stage scoring for pain points, bullets, header, competencies, grading, fit** |
| 9 | Store results | `data/eval/` with raw, normalized, composites, rubrics |
| 10 | Calibration from existing CV reviews | Diagnostic layer using 127 reviewer verdicts |
| 11 | Holdout validation | Verify composite accuracy against reserved jobs |

**Output:** `data/eval/` directory with composites, blueprints, baselines, rubrics, and scorecards.

---

## Phase 3: Architecture Refactoring (Cost + Efficiency)

**Goal:** ~49% cost reduction, configurable provider per step, eliminate stale code.

### 3a. STEP_CONFIGS Tier Downgrades (30 min)

**File:** `src/common/llm_config.py`

Downgrade mechanical tasks to Haiku:
- `improver` → low (targeted edits with constraints)
- `cv_tailorer` → low (keyword repositioning)
- `star_selection` → low (ranking task)
- `fit_analysis` → low (scoring with rubric)
- Add missing `title_sanitizer` → low (currently defaults to middle)
- Add missing `contact_classification` → low

Keep Sonnet for quality-sensitive: `role_generator`, `header_generator`, `ensemble_header`, `pain_point_extraction`, `cover_letter_generation`, `outreach_generation`

### 3b. Add Provider Routing to StepConfig (2h)

**Files:** `src/common/llm_config.py`, `src/common/unified_llm.py`

Add `provider` field to StepConfig. Update `UnifiedLLM.invoke()` to route to Codex CLI for configured steps (`grader`, `fit_analysis`, `title_sanitizer`, `jd_structure_parsing`).

### 3c. Enable Anthropic Prompt Caching (1h)

**File:** `src/common/claude_cli.py`

For role generation (6 calls with identical system prompt), leverage prompt caching. Saves ~9,600 tokens per CV.

### 3d. Merge Grader + Improver into Single Call (2h)

**Files:** `src/layer6_v2/grader.py`, `src/layer6_v2/improver.py`, `src/layer6_v2/orchestrator.py`

Single prompt: "Grade on 5 dimensions. If below 8.5, provide targeted improvements inline." Eliminates ~6K tokens of duplicate CV text.

### 3e. Skip Cover Letter for Tier C/D (15 min)

**File:** `src/layer6_v2/orchestrator.py`

Conditional skip saves ~5K tokens on ~80% of jobs.

### 3f. Remove Stale Code (30 min)

Delete: `src/layer6/generator.py`, `src/layer6/cv_generator.py`, `src/layer6/html_cv_generator.py`, root `prompts/*.md`. Remove `ENABLE_CV_GEN_V2` flag (always true).

### 3g. Re-run Eval

Run eval framework from Phase 2 to verify no quality regression from architecture changes. Cost metrics should show ~49% reduction.

---

## Phase 4: Pre-Enrichment Moves to a Lease-Based Worker (VPS)

**Goal:** Pre-CV enrichment (JD structure, JD extraction, AI classification,
pain points, annotations, persona, company research, role research, fit signal)
moves out of `BatchPipelineService` into a new `preenrich-worker` service that
runs inside the existing runner image on the VPS. Work is claimed from Mongo
via leases, stages run sequentially per job, and state is persisted atomically
after each stage. Enqueue to the runner goes through a durable Redis outbox.

**Detailed sub-plan:** [`plans/scout-pre-enrichment-skills-plan.md`](scout-pre-enrichment-skills-plan.md)

| Phase | What | Gate |
|-------|------|------|
| 0 | Foundations: `src/preenrich/` scaffolding, Codex CLI wrapper (shadow), Mongo indexes, `StepConfig.provider` | existing tests byte-identical |
| 1 | Dispatcher + `jd_structure` + `jd_extraction`; worker disabled by default | local fixture passes two stages |
| 2 | Remaining stages, Codex shadow enabled where available | VPS fixture reaches `lifecycle = "ready"` |
| 3 | Dual-run diff (worker + runner both run; runner ignores worker output) | ≥ 50 jobs 24h, ≥ 97% schema validity, ≥ 0.85 cosine parity |
| 4 | Selector enqueue ownership transfer to outbox | ≤ 1% orphans in 24h |
| 5 | Runner skip-upstream enabled | 48h production parity, measurable cost drop |
| 6 | Per-stage Codex cutover (evidence-gated) | per-stage diff report clears thresholds |

**Provider defaults (v1):** Claude stays default. Codex is shadow-only. Cutover
is per-stage and gated by the dual-run diff report, not by code review.

**Persistence:** Mongo `level-2.pre_enrichment` is authoritative.
`/var/lib/scout/preenrich_audit.jsonl` is audit-only (not recovery state).
Redis stream `preenrich:enqueue_outbox` provides at-least-once delivery.

**Lifecycle states:** `selected → preenriching → ready → queued → running →
completed | failed`. `stale` loops back to `preenriching`. `legacy` bypasses
the worker.

**Runner impact:** `BatchPipelineService.execute` gains a `skip_upstream`
branch gated by `RUNNER_SKIP_UPSTREAM=true` and a checksum match. Until that
flag flips, the runner continues to run Full Extraction + Company Research +
Persona itself (zero-risk rollback).

---

## Phase 1: Master CV Enhancement (ITERATIVE — Guided by Evals)

**Goal:** Systematically improve the curated evidence store and master CV representation using intelligence from `docs/archive/`, `docs/current/`, and eval results.

### 1a. Inventory Upstream Evidence and Provenance

**Process:**
1. Read every file in `docs/current/` and `docs/archive/` that contains CV quality insights, interview feedback, positioning guidance, or achievement recommendations
2. Classify each useful item as one of:
   - already curated in `data/master-cv/*`
   - valid upstream evidence pending curation
   - guidance only, not claimable evidence
3. Record provenance so promoted claims remain traceable

### 1b. Promote High-Value Evidence into the Curated Store

Prioritize promotion based on eval impact, starting with primary and secondary target categories.

- Add vetted upstream achievements to `data/master-cv/roles/*.md` and project files
- Update skills JSONs when the evidence is strong enough to become reusable pipeline input
- Maintain a backlog for valid evidence that is lower priority or still too ambiguous to promote

**Key docs to mine:**
- `docs/current/prompt-optimization-plan.md` — prompt quality improvements
- `docs/archive/knowledge-base.md` — 11+ STAR records with rich context
- `docs/archive/prompt-ab/` — A/B test results showing what works/fails
- `docs/current/cv-generation-guide.md` — quality gates and grading dimensions
- `reports/agentic-ai-architect-focus-plan-2026-04-11.md` — Part 4 Commander-4 contribution plan

### 1c. Enhance Role Files Based on Promoted Evidence and Eval Gaps

**Files:** `data/master-cv/roles/01_seven_one_entertainment.md` (primary), others as needed

For each high-value gap identified by Step 6:
- Add new achievements with 4 variants (Technical, Architecture, Impact, Leadership)
- Reframe existing achievements to strengthen AI positioning
- Ensure every claimed competency has at least one grounding achievement

### 1d. Update Identity & Metadata

**Files:** `data/master-cv/role_metadata.json`, `data/master-cv/role_skills_taxonomy.json`

- Align `title_base` with target AI Architect identity
- Update `primary_competencies` to lead with AI-relevant skills
- Ensure taxonomy persona statements match updated identity

### 1e. Enhance Project Files

**Files:** `data/master-cv/projects/commander4_skills.json`, `lantern_skills.json`, `commander4.md`

- Add any new verified competencies from recent Commander-4 work
- Ensure bullet text in `commander4.md` reflects latest contributions

### 1f. Re-run Eval After Each Round

After each batch of master CV changes:
1. Run eval framework on same 5 categories × 3 jobs
2. Compare dimension scores vs baseline
3. Identify which dimensions improved, which regressed, and which `curation_gaps` remain
4. Iterate: fix regressions, push on weakest dimensions

**Target after 2-3 rounds:** GOOD_MATCH rate from 5% → 25%+, mean score from 4.2 → 7.0+

---

## Phase 5: Redis Live-Tail Integrity (CONTINUOUS)

**Goal:** Verify live-tail works correctly after each phase.

### After Each Phase:

1. Run 1 pipeline job with live-tail open in browser
2. Verify all log events appear (layer starts/completes, LLM calls, validations)
3. Verify layer progress tracking updates correctly
4. Verify cost/token aggregation is accurate
5. Check Redis key TTLs (`logs:{run_id}:*` should expire after 6h)

### For New Steps:

- Any new `_emit_struct_log()` calls (early extraction, merged grader+improver) must include: event name, model, tokens, cost, duration
- Frontend log parser must handle new event types without breaking

### Health Check Endpoint:

Add `/api/health/live-tail` that verifies Redis connection + log round-trip for monitoring.

---

## Future Work: Model Benchmark Matrix (After Step 9 Expansion Stabilizes)

**Goal:** Compare generation quality across model tiers without turning every CV run into an expensive multi-model experiment.

### Principle

Do **not** generate every CV with every GPT and Claude model by default.

That creates:
- unnecessary cost
- noisy comparisons
- unclear baselines
- slower iteration loops

Instead, use a **tiered model strategy**:

### 1. Reference Quality Runs

Use one strong reference model for quality benchmarking on important eval batches.

Purpose:
- establish the best-known quality baseline
- validate major prompt or pipeline changes
- compare against cheaper models on a fixed benchmark set

### 2. Cheap CI / Smoke Runs

Use one cheaper model for CI and frequent checks.

Purpose:
- verify pipeline execution still works
- verify outputs parse and save correctly
- verify scorecards render correctly
- catch unsupported-claim regressions or schema drift on a very small sample

This CI layer is for **pipeline health**, not for final quality judgments.

### 3. Scheduled Frontier Benchmark Runs

Run a scheduled benchmark matrix on a fixed representative job set using:
- one strong GPT model
- one strong Claude model
- optionally one cheaper comparison model

Purpose:
- measure quality deltas over time
- detect regressions after prompt, pipeline, or master-CV changes
- compare cost/quality tradeoffs across providers

### Operating Rule

Default workflow:
- PR / CI: cheap smoke model on 1-2 representative jobs
- scheduled benchmark: frontier models on a fixed benchmark set
- major release or prompt overhaul: rerun the full benchmark set

### Benchmark Design Notes

When this is implemented:
- use the same JD set, rubrics, and scorecard logic across all models
- compare model outputs using the existing Step 9 scoring system
- preserve immutable generated CV snapshots and scorecards per model
- optimize for reproducibility over volume
- only expand the matrix after the Step 9 scoring workflow is stable across more categories

---

## Key Files

| Component | File |
|-----------|------|
| Master CV roles | `data/master-cv/roles/01_seven_one_entertainment.md` |
| Role metadata | `data/master-cv/role_metadata.json` |
| Skills taxonomy | `data/master-cv/role_skills_taxonomy.json` |
| Project skills | `data/master-cv/projects/commander4_skills.json`, `lantern_skills.json` |
| LLM config | `src/common/llm_config.py` |
| Unified LLM | `src/common/unified_llm.py` |
| Claude CLI | `src/common/claude_cli.py` |
| Orchestrator | `src/layer6_v2/orchestrator.py` |
| Grader | `src/layer6_v2/grader.py` |
| Improver | `src/layer6_v2/improver.py` |
| Scraper cron | `n8n/skills/scout-jobs/scripts/scout_scraper_cron.py` |
| Selector cron | `n8n/skills/scout-jobs/scripts/scout_selector_cron.py` |
| Workflow | `src/workflow.py` |
| Eval runner (new) | `scripts/eval_cv_quality.py` |
| Ideal CVs (new) | `data/eval/ideal_cvs/` |
| Docs for mining | `docs/current/`, `docs/archive/` |

---

## Verification

| Phase | Test |
|-------|------|
| 2 (Eval) | Baseline scores established for 5 categories × 3 jobs |
| 3 (Architecture) | 70+ unit tests pass, eval scores stable, cost reduced ~49% |
| 4 (Early Extraction) | VPS dry-run on 10 jobs, extracted fields in level-2 |
| 1 (Master CV) | Eval scores improve by ≥1.5 points per round |
| 5 (Live-Tail) | Browser live-tail shows all events for 1 complete pipeline run |
