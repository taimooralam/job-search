# Eval Stack Freeze Recommendation

**Date:** 2026-04-18
**Scope:** final go/no-go on freezing the current Step 5-10 eval stack for operational use, plus a rollout plan for running the Step 9 rubric scorer on live pipeline-generated CVs.

## Inputs to the decision

### Per-pair results across all scoring passes

| Pass | Pairs scored | GOOD_MATCH | NEEDS_WORK | WEAK_MATCH | Unscoreable | Notes |
|---|---|---|---|---|---|---|
| Step 9 anchor v1 (legacy CVs) | 4 | 0 | 1 | 3 | 0 | scorer-validation only; all expected |
| Step 9 anchor v2 (generated) | 4 | 2 | 2 | 0 | 0 | 2 NEEDS_WORK are real_fit_gap |
| Step 9 expansion v1 (generated) | 4 | 4 | 0 | 0 | 0 | clean |
| Step 9 coverage v1 (generated) | 4 | 3 | 1 | 0 | 0 | 1 NEEDS_WORK is first generation_gap (head_of_ai_eea / REVOLUT) |
| Step 11 variance v1 (generated) | 3 (+1 unscoreable) | 1 | 1 | 1 | 1 | JD-specificity confirmed |
| Step 10 calibration (historical CVs) | 10 (+2 unscoreable) | 4 | 1 | 5 | 2 | directional alignment with cv_review |

### Across 15 generated-for-target-JD scorecards (anchors v2 + expansion + coverage + variance)

- **10 GOOD_MATCH (67%), 4 NEEDS_WORK (27%), 1 WEAK_MATCH (7%)**
- Gate pass rate: **40 / 45** (89%)
- Unsupported_claims total: **4** (3 on head_of_ai_eea / REVOLUT, 1 on head_of_ai_global / QUORA)
- Persona inflation: **0** (zero across all 15 — manager stays player-coach, IC categories stay IC)
- Anti-hallucination dim ≥ 7.5 on 14/15

### NEEDS_WORK / WEAK classification

| Category / JD | Classification |
|---|---|
| ai_architect_global / ALGOMINDS | real_fit_gap (deep C#/.NET + PhD) |
| staff_ai_engineer_eea / REDDIT | real_fit_gap (Golang + 8y search/recsys) |
| head_of_ai_eea / REVOLUT | **generation_gap** — skills-list padded with AI terms without experience backing |
| tech_lead_ai_eea / ZYTE (variance) | real_fit_gap (ML Ops depth) |
| head_of_ai_global / QUORA (variance) | upstream-classification-noise (JD isn't actually a Head-of-AI role) |

**Only 1/5 non-GOOD pairs is a controllable generation_gap.** It's a single occurrence, not a cluster.

### Step 10 calibration signal

- 3/10 exact verdict match with cv_review (gpt-5.2 reviewer)
- **8/10 within ±1 tier** — directional alignment
- Rubric runs ~0.5-1.5 tier more lenient than cv_review overall
- Worst-case (WEAK_MATCH + all gates fail) reliably agrees with cv_review verdicts
- Rubric's gate failures track reviewer-flagged pain points

## Decision: **A — freeze the eval stack**

All three conditions for A are met:
1. **Full 12-category Step 9 coverage is complete** (anchor v2 + expansion + coverage).
2. **Variance sampling did not reveal a repeated generation_gap cluster.** 1 isolated generation_gap on head_of_ai_eea remains the only controllable failure across 15 generated-for-JD pairs.
3. **Step 10 calibration is directionally acceptable.** Rubric agrees with cv_review on bottom-tier and on direction across 80% of pairs; lenience bias is documented and operationally trivial to compensate for.

**Step 8b stage diagnostics remain deferred.** The isolated head_of_ai_eea generation_gap (skills-without-experience) doesn't justify full stage-diagnostic infra; it can be addressed with a targeted `competency_selection` prompt tweak if it recurs in production.

## Operational rollout plan

### Phase 1 — shadow scoring on new pipeline runs (week 1)

- Add a post-CV-generation hook that invokes `scripts/eval_step9_score_cv_outputs.py` in single-pair mode for every successful CV run.
- Score target: if the job has a matching Step 7 rubric (via Step 2-style category assignment heuristic over `title + location`), score. Otherwise skip.
- Snapshot CV markdown to `data/eval/pipeline_scored/<yyyy-mm>/<category>/<job_id>_scorecard.{json,md}` and also write `scorecard.json` back to the Mongo job doc under `cv_scorecard_v1`.
- Shadow mode only: do not block publishing or queue actions. Goal is to collect live scoring telemetry.

Concrete work items:
- Add a category-inference helper reusing the Step 2 title-family + location regex (already validated).
- Add `--single-pair --job-id <id> --cv-path <p> --jd-path <p>` invocation path (already supported by the scorer).
- Telemetry: aggregate weekly scoring into `data/eval/telemetry/<yyyy-ww>_scorecards.md` (verdict distribution, gate-failure pareto, top failure clusters).

### Phase 2 — actionable gating (week 3, after ~20-40 shadow scorecards)

Once shadow telemetry confirms distribution:
- High-stakes flow (e.g., `apply-jobs` skill): require `verdict ∈ {STRONG_MATCH, GOOD_MATCH}` AND `all 3 gates pass` AND `anti_hallucination ≥ 7.5` before auto-apply.
- NEEDS_WORK or WEAK / failed gate: surface scorecard to the user before CV is allowed out; the `failure_modes` and `unsupported_claims` entries become the review punch list.
- The Step 10 lenience bias (rubric ≈ 0.5-1.5 tier higher than cv_review) means rubric GOOD_MATCH ≈ cv_review NEEDS_WORK-or-better — **this is acceptable for auto-apply gating** because of the `all gates + ≥ 7.5 anti_hallucination` hurdle.

### Phase 3 — continuous calibration (ongoing)

- Any job with both `cv_review` (legacy) and `cv_scorecard_v1` (new) fields in Mongo becomes a live calibration datapoint. Expand the Step 10 calibration report monthly.
- Track rubric-vs-review verdict drift. If drift > 2 tiers appears on more than 10% of paired cases, the rubric needs retuning (not the pipeline).
- File a light ticket to backfill the scorer's ref-validation ping-pong edge case (the RELATIVITY pattern): accept lightweight-repaired output on final attempt and attach `ref_warnings` instead of failing outright. Current graceful-accept path already handles cross-check-only failures; extending it to ref-only failures closes the loop.

## What is NOT frozen

- **Master CV content.** Ongoing curation of `data/master-cv/*` continues independently. Every material CV edit should trigger a Step 6 rerun for affected categories to keep baselines honest.
- **Blueprint / baseline / rubric JSONs.** These are versioned by the `rubric_version` field. Future edits require bumping the version and rerunning the Step 9 batches against the new version for any ongoing decisions.
- **The list of 12 rubric-backed categories.** If a new category is added (e.g., `ai_solutions_architect_global`, `principal_ai_engineer_ksa`), the full Step 5-7 chain must run first.

## Open watch-items (log, don't block)

1. **head_of_ai_eea skills-without-experience pattern.** If any live-pipeline scorecard for this category trips `must_have_coverage_gate=false` with the same "AI terms in skills without experience" failure mode, escalate to Step 8b targeting `competency_selection`.
2. **Scorer ref-validation ping-pong** on specific CVs (saw on 1/15 generated + 2/12 calibration). Mitigation backlog item; not blocking operational rollout.
3. **Upstream Step 2 classification noise** on head_of_ai_global and head_of_ai_eea. Not an eval-stack issue — an earlier-layer data quality issue. Document, don't fix here.

## Artifact inventory

### Completed artifacts

- `data/eval/raw/`, `data/eval/normalized/`, `data/eval/composites/` — Steps 1-4
- `data/eval/blueprints/*_blueprint.{json,md}` — Step 5 (12 categories)
- `data/eval/baselines/*_baseline.{json,md}` + `step6_report.md` — Step 6 (12 categories)
- `data/eval/rubrics/*_rubric.{json,md}` + `scorecard_template.json` + `stage_scorecard_template.json` + `index.md` + `README.md` — Step 7/8/8b
- `data/eval/scorecards/<category>/<jd_stem>_scorecard.{json,md}` — 12 active Step 9 scorecards
- `data/eval/scorecards/variance_v1/<category>/...` — 3 variance scorecards
- `data/eval/scorecards/calibration_v1/<category>/...` — 10 calibration scorecards
- `data/eval/scorecards/batches/*.json` — 5 batch manifests
- `data/eval/scorecards_archive/step9_v1_anchor/` — v1 legacy-CV scorecard archive
- `data/eval/generated_cvs/step9_{v2,expansion,coverage,variance_lite}_*/{snapshots,logs,meta}/` — immutable CV snapshots and run metadata

### Report artifacts

- `data/eval/scorecards/comparison_v1_v2.md`
- `data/eval/scorecards/comparison_expansion_batch_v1.md`
- `data/eval/scorecards/comparison_coverage_batch_v1.md`
- `data/eval/scorecards/comparison_step11_variance_key_batch_v1.md`
- `data/eval/scorecards/step10_calibration_report.md`
- `data/eval/scorecards/freeze_recommendation.md` (this file)
- `data/eval/scorecards/{index.md, summary.md}` — refreshed

### Tooling

- `scripts/eval_step9_score_cv_outputs.py` — rubric scorer (with `skip_jd_resolution`, `output_subdir`, and cross-check graceful-accept on final attempt)
- `scripts/eval_step9v2_run_batch.py` — sequential batch pipeline runner with `--tag` and `--anchors-json`
- `scripts/eval_step{5,6,7}_*.py` — blueprint / baseline / rubric generators (Step 5/6/7)
- `src/common/llm_config.py` — adds `eval_{blueprint,baseline,rubric,cv_scoring}_generation` step configs

## Sign-off condition (met)

- Does the current generation + rubric-scoring system hold up across **full category coverage**? **Yes** (12/12).
- Across **within-category variance**? **Yes** (JD-specificity confirmed; no shared generation_gap cluster).
- Across **historical calibration**? **Directionally yes** (8/10 within ±1 tier; worst-case reliable; rubric lenience documented).
- Freeze and start operational rollout in shadow mode. Next immediate step is Phase 1 above.
