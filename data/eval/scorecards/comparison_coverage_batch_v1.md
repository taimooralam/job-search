# Step 9 Coverage Batch v1 — 12-Category Full Coverage

**Purpose:** complete rubric-scored coverage of all 12 Step 7 rubric-backed categories by running pipeline-generated CVs against the final 4 untested categories, then produce one consolidated recommendation across all 12 categories.

**Batch manifest:** `data/eval/scorecards/batches/step9_coverage_batch_v1_generated.json`
**Run root:** `data/eval/generated_cvs/step9_coverage_20260417_221712/`

## Coverage-batch results (4 new pairs)

| Category | JD | Overall | Verdict | Gates (all 3) | Top failure | Classification |
|---|---|---|---|---|---|---|
| head_of_ai_eea | REVOLUT / Head of Engineering | **6.95** | NEEDS_WORK | ✅ ✅ ✅ except `must_have_coverage_gate=❌` | "LLM Integration in skills without experience evidence" | **generation_gap** (first occurrence in the full batch) |
| head_of_ai_ksa | MOZN / Engineering Manager, Agentic AI | **7.50** | GOOD_MATCH | ✅ ✅ ✅ | 12+y ask vs 10+y stated (timeline undersell) | acceptable_fit |
| head_of_ai_uae | TECHNOLOGY INNOVATION INSTITUTE / Senior Architect | **7.38** | GOOD_MATCH | ✅ ✅ ✅ | No geospatial/GIS workflow evidence | **real_fit_gap** |
| ai_architect_ksa_uae | NOVAPILOT / Software Architect Cloud/AI/Distributed | **7.15** | GOOD_MATCH | ✅ ✅ ✅ | No Kubernetes experience | **real_fit_gap** |

**Dimensions:**

| Category | ATS | Impact | JD Align | Exec Pres | Anti-Hall |
|---|---|---|---|---|---|
| head_of_ai_eea | 6.5 | 7.5 | 7.0 | 7.0 | **6.5** |
| head_of_ai_ksa | 7.5 | 8.0 | 7.0 | 7.5 | 7.5 |
| head_of_ai_uae | 7.0 | 8.0 | 6.0 | 8.0 | 8.5 |
| ai_architect_ksa_uae | 7.0 | 8.0 | 6.0 | 6.0 | **9.0** |

## Full 12-category results (all generated-for-JD CVs; v2-anchor + expansion + coverage)

| # | Category | Overall | Verdict | Gates | Classification |
|---|---|---|---|---|---|
| 1 | ai_architect_eea | 7.00 | GOOD_MATCH | 3/3 | real_fit_gap (minor) |
| 2 | ai_architect_global | 6.97 | NEEDS_WORK | 2/3 (must_have) | **real_fit_gap** (C#/.NET/PhD) |
| 3 | ai_architect_ksa_uae | 7.15 | GOOD_MATCH | 3/3 | real_fit_gap (K8s) |
| 4 | ai_eng_manager_eea | 7.97 | GOOD_MATCH | 3/3 | acceptable_fit |
| 5 | head_of_ai_eea | 6.95 | NEEDS_WORK | 2/3 (must_have) | **generation_gap** (skills-without-evidence) |
| 6 | head_of_ai_global | 8.15 | GOOD_MATCH | 3/3 | strong_fit |
| 7 | head_of_ai_ksa | 7.50 | GOOD_MATCH | 3/3 | acceptable_fit |
| 8 | head_of_ai_uae | 7.38 | GOOD_MATCH | 3/3 | real_fit_gap (geospatial) |
| 9 | senior_ai_engineer_eea | 8.10 | GOOD_MATCH | 3/3 | strong_fit |
| 10 | staff_ai_engineer_eea | 6.97 | NEEDS_WORK | 2/3 (must_have) | **real_fit_gap** (Golang/search-8y) |
| 11 | staff_ai_engineer_global | 7.35 | GOOD_MATCH | 3/3 | real_fit_gap (15y) |
| 12 | tech_lead_ai_eea | 8.05 | GOOD_MATCH | 3/3 | strong_fit |

**Aggregate:**
- Verdicts: **9 GOOD_MATCH, 3 NEEDS_WORK, 0 WEAK_MATCH, 0 STRONG_MATCH** (9/12 ≥ GOOD)
- Gate pass rate: **33 / 36** (3 failed gates, all `must_have_coverage_gate`)
- Mean overall: 7.39
- Anti-hallucination mean: ~8.0; low point 6.5 (head_of_ai_eea), high 9.0 (ai_architect_ksa_uae)

**Failure-type tally (across the 3 NEEDS_WORK pairs):**
- 2 × `real_fit_gap` (ai_architect_global, staff_ai_engineer_eea — authentic candidate gaps, pipeline correctly did not fabricate)
- 1 × `generation_gap` (head_of_ai_eea — first controllable generation issue across the full 12-pair set)

## The one generation_gap: head_of_ai_eea

The Revolut Head-of-Engineering CV surfaced AI-related terms ("LLM Integration", category AI stack) in the **Core Competencies / skills** section without backing evidence in the **Professional Experience** bullets. Scorer flagged this correctly:
- 3 unsupported_claims (all pointing at skill-list entries with no experience-section backing)
- 2 missing_must_haves (production AI platform evidence)
- `must_have_coverage_gate = false`
- anti_hallucination dropped to 6.5 (the lowest of all 12)

**Root cause signal (not confirmed, would need diagnostic):** The Revolut JD is heavier on credit/eng-leadership than pure AI, but `head_of_ai_eea` category rubric biases toward AI platform signal. The generator appears to have padded the skills section with rubric-driven AI keywords while the experience bullets stayed faithful to the JD. This is a **curation/weighting stage** issue, not a fabrication of experience.

**Is it a cluster?** No — it's a single occurrence across 12 pairs. The same pipeline produced 4 other Head-of-AI-family CVs (head_of_ai_global GOOD, head_of_ai_ksa GOOD, head_of_ai_uae GOOD) without this pattern. Step 8b stays deferred unless within-category variance sampling surfaces a repeat.

## Integrity & persona summary (12-pair active set)

- Total `unsupported_claims`: **3** (all in head_of_ai_eea)
- Total `missing_must_haves` entries: 2 in head_of_ai_eea + must-have rollups in the 2 `real_fit_gap` anchors
- Persona inflation: **zero** across all 12 (no pipeline run drifted into exec/VP framing on staff/architect/tech-lead categories; manager category stayed player-coach; architect categories stayed IC/architect-first)
- Anti-hallucination ≥ 7.5 on 11/12

## Final recommendation: **A (with a watch-item)**

**The eval stack is validated across all 12 rubric-backed categories.**

- Pipeline produces rubric-compliant CVs in 9/12 categories on first attempt.
- The 2 residual WEAK/NEEDS_WORK verdicts in the 8-pair prior batches are both `real_fit_gap` — correctly-refused fabrication, not pipeline failure.
- The 1 new `generation_gap` (head_of_ai_eea) is isolated, not a cluster.
- **Step 8b stage diagnostics remain deferred.**

**Watch-item:** the "skills-without-experience-evidence" pattern (head_of_ai_eea) is the single failure pattern worth testing for repetition. If within-category variance sampling surfaces the same pattern on ≥ 1 more head_of_ai or head_of_ai_* JD, that flips the decision to **B** targeting the `competency_selection` stage (Layer 6 V2's core-competency / skills-whitelist module).

## Next operational step

**Within-category variance sampling** (already queued per prior user plan):
- Pick 3-4 key categories and generate 2-3 additional JDs each to test intra-category stability.
- **Priority categories for variance:**
  1. `head_of_ai_eea` — confirm whether the generation_gap recurs or was a single Revolut-specific distortion (highest signal value)
  2. `ai_architect_global` — confirm that ALGOMINDS real_fit_gap reproduces as `real_fit_gap` (not `generation_gap`) on a different EEA-ish ai_architect JD
  3. `tech_lead_ai_eea` — already landed 8.05, one more JD tests whether AI-tech-lead strong fit is JD-specific
  4. `staff_ai_engineer_global` — already GOOD, one more JD tests generalization within senior-IC global

Run 2 additional JDs per category → 8 more pairs → ~80 min pipeline + ~20 min scoring. If anti_hallucination stays ≥ 7.5 and no new `generation_gap` clusters appear, the system is ready to **freeze** as the baseline and the next phase is operational use (applying CVs to real jobs on the queue).

## Artifact pointers

- Coverage manifest: `data/eval/scorecards/batches/step9_coverage_batch_v1_generated.json`
- Coverage scorecards: `data/eval/scorecards/<category>/<jd_stem>_scorecard.{json,md}` ×4 (4 new categories)
- Coverage snapshots: `data/eval/generated_cvs/step9_coverage_20260417_221712/snapshots/<category>/<jd_stem>__generated.md`
- Prior reports: `data/eval/scorecards/comparison_v1_v2.md` (anchor v2), `data/eval/scorecards/comparison_expansion_batch_v1.md` (expansion)
- Full active scorecard inventory: `data/eval/scorecards/index.md`
