# Step 9 v1 vs v2 Comparison

**Purpose:** separate scorer-correctness from generation-quality by comparing rubric-based scores of the legacy (v1) CV outputs with scores of pipeline-generated CVs (v2) for the same 4 anchor jobs.

**v1 batch:** legacy CVs, ambiguous/misaligned provenance (`data/eval/scorecards_archive/step9_v1_anchor/`).
**v2 batch:** pipeline-generated snapshots, frozen at `data/eval/generated_cvs/step9_v2_20260417_124150/snapshots/`.
**Rubrics, scorer, candidate evidence:** unchanged between v1 and v2.

## Pair-by-pair deltas

| Category | v1 overall/verdict | v2 overall/verdict | Δ | unsupported_claims Δ | missing_must_haves Δ | persona gate v1→v2 | dominant failures (v2) | failure type | Step 8b relevant? | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| ai_architect_global | 5.00 / WEAK_MATCH | **6.97 / NEEDS_WORK** | **+1.97** | 2 → 1 | 6 → 4 | ❌ → ✅ | Pulumi expert-level absent; deep C#/.NET absent | **real_fit_gap** | no | Residual WEAK-ish is JD-authentic: ALGOMINDS requires expert C#/.NET + Pulumi + PhD/Master's. Pipeline correctly did not fabricate these; match headline adopted; AI platform proof surfaced; persona normalized to architect/player-coach. |
| head_of_ai_global | 5.22 / WEAK_MATCH | **8.15 / GOOD_MATCH** | **+2.93** | 2 → 0 | 3 → 0 | ❌ → ✅ | Remote-first keyword density; AI-platform headline density | `generation_gap` (mild) | no (single, minor) | Clean GOOD_MATCH. All 3 gates pass. Commander-4 / GenAI evidence fully surfaced. Remaining nits are weight-tuning, not category-level failure. |
| staff_ai_engineer_eea | 5.05 / WEAK_MATCH | **6.97 / NEEDS_WORK** | **+1.92** | 0 → 0 | 6 → 0 | ✅ → ✅ | Golang absent; Lucene/Solr/ElasticSearch absent | **real_fit_gap** | no | Reddit ML Search JD demands 8y search/recsys + Golang. Pipeline did not invent them — correctly. Commander-4 hybrid retrieval (BM25+RRF+reranking) foregrounded; reliability metrics quantified. must_have_coverage now passes; cap comes from anti_hallucination on missing Go/search-engine evidence. |
| tech_lead_ai_eea | 5.97 / NEEDS_WORK | **8.05 / GOOD_MATCH** | **+2.08** | 0 → 0 | 3 → 0 | ❌ → ✅ | TypeScript > Python emphasis; no GoLang/GraphQL | `generation_gap` (mild, stack-weighting) | no (single, minor) | Clean GOOD_MATCH, all gates pass. Commander-4 AI platform evidence, billions-of-events reliability, and tech-lead persona all surface correctly. Python dominance not fully shifted over TypeScript in roles where both exist — a weighting tweak, not a missing capability. |

## Dimension-level deltas

| Category | ATS (20%) | Impact (25%) | JD Align (25%) | Exec Presence (15%) | Anti-Hall (15%) |
|---|---|---|---|---|---|
| ai_architect_global | 4.0→7.0 (+3.0) | 6.5→7.5 (+1.0) | 4.0→5.5 (+1.5) | 5.0→7.5 (+2.5) | 5.5→8.0 (+2.5) |
| head_of_ai_global | 4.5→7.5 (+3.0) | 6.5→8.5 (+2.0) | 4.5→8.5 (+4.0) | 5.5→7.5 (+2.0) | 5.0→8.5 (+3.5) |
| staff_ai_engineer_eea | 3.5→6.0 (+2.5) | 6.5→8.0 (+1.5) | 2.5→5.5 (+3.0) | 6.5→7.5 (+1.0) | 7.5→8.5 (+1.0) |
| tech_lead_ai_eea | 3.5→7.5 (+4.0) | 7.5→8.5 (+1.0) | 4.0→7.5 (+3.5) | 7.5→8.5 (+1.0) | 8.5→8.5 (0.0) |

Anti-hallucination is up or flat across all 4 anchors. No integrity regression in v2.

## Gate transitions

| Category | must_have_coverage | unsafe_claim | persona_fit |
|---|---|---|---|
| ai_architect_global | ❌ → ❌ | ❌ → ✅ | ❌ → ✅ |
| head_of_ai_global | ❌ → ✅ | ❌ → ✅ | ❌ → ✅ |
| staff_ai_engineer_eea | ❌ → ✅ | ✅ → ✅ | ✅ → ✅ |
| tech_lead_ai_eea | ❌ → ✅ | ✅ → ✅ | ❌ → ✅ |

- 7 of 12 failed gates in v1 now pass in v2.
- Zero regressions on any gate.
- The only remaining failed gate is `must_have_coverage` on ai_architect_global — and the missing must-haves (deep C#/.NET, expert Pulumi, PhD/Master's) are authentic candidate gaps, not pipeline omissions.

## Unsupported claims: integrity improved

- v1: total 4 unsupported claims across anchors, dominated by legacy "Head of Engineering / Engineering Executive" title inflation in the cMatter CV.
- v2: total 1 unsupported claim, and that one is a legitimate over-weight of C# in the Core Technologies section for ai_architect_global (correctly flagged by scorer, because C# is only evidenced in a 2014-2016 role).
- Pipeline did **not** fabricate C#/.NET, Go, Lucene, Pulumi, PhD, or search/recsys experience where the candidate lacks it. This is the single strongest signal that the generator is honest.

## Persona-fit: all 4 now pass

v1 persona failures were all driven by the cMatter CV's "Engineering Executive" framing being scored against IC-architect, staff-IC, and tech-lead categories. v2 outputs use the correct per-category persona (architect / player-coach / senior IC / tech lead) with no exec inflation.

## Decision: **A. No Step 8b stage diagnostics needed**

All 4 anchors are scoreable. Two land GOOD_MATCH (head_of_ai_global 8.15, tech_lead_ai_eea 8.05) with all 3 gates passing. The two NEEDS_WORK anchors are **`real_fit_gap`**, not `generation_gap`:
- ai_architect_global (ALGOMINDS) requires deep C#/.NET, expert Pulumi, and PhD/Master's depth that Taimoor genuinely lacks. The pipeline correctly did not fabricate these. All other dimensions jumped by 1-4 points.
- staff_ai_engineer_eea (Reddit ML Search) requires 8+ years search/recsys and Golang that Taimoor lacks. The pipeline surfaced the strongest adjacent evidence (Commander-4 hybrid retrieval with BM25+RRF+reranking, reliability metrics) without inventing Golang or search-engine expertise.

No shared controllable `generation_gap` cluster exists across ≥2 anchors. The two mild `generation_gap`-flavored nits (AI-platform keyword density in head_of_ai_global headline; TypeScript-vs-Python weighting in tech_lead_ai_eea) are isolated to single anchors and are weighting/keyword-density tuning, not stage failures. Neither justifies a Step 8b diagnostic pass; both can be addressed by category-level prompt tweaks if the pattern recurs in the next batch.

**Recommended next step:** expand Step 9 scoring to the next 4 categories per the Step 7 rubric inventory — `ai_architect_eea`, `staff_ai_engineer_global`, `ai_eng_manager_eea`, `senior_ai_engineer_eea`. Reuse the same pipeline-generation + snapshot flow. Step 8b stays on ice until a controllable generation cluster actually appears.

## Artifact pointers

- v2 manifest: `data/eval/scorecards/batches/step9_anchor_batch_v2_generated.json`
- v2 scorecards: `data/eval/scorecards/<category>/<jd_stem>_scorecard.json` + `.md`
- v2 snapshots: `data/eval/generated_cvs/step9_v2_20260417_124150/snapshots/<category>/<jd_stem>__generated.md`
- v2 run logs + meta: `data/eval/generated_cvs/step9_v2_20260417_124150/{logs,meta}/`
- v1 archive: `data/eval/scorecards_archive/step9_v1_anchor/<category>/<jd_stem>_scorecard.{json,md}`
