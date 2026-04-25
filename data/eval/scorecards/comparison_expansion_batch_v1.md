# Step 9 Expansion Batch v1 — Comparison & Decision

**Purpose:** test whether the pipeline's good anchor-batch performance generalizes to 4 more representative categories using the same flow (pipeline-generated CV snapshots scored against Step 7 rubrics).

**Batch manifest:** `data/eval/scorecards/batches/step9_expansion_batch_v1_generated.json`
**Run root:** `data/eval/generated_cvs/step9_expansion_20260417_174209/`
**v2 anchor baseline for reference:** `data/eval/scorecards/comparison_v1_v2.md`

## Per-anchor results

| Category | JD | Overall | Verdict | Gates (all 3) | Failed gates | Top failure | Classification |
|---|---|---|---|---|---|---|---|
| ai_architect_eea | NEURONS LAB / AI Solution Architect | **7.00** | **GOOD_MATCH** | ✅ ✅ ✅ | — | JD expects AWS Solutions Architect Pro / ML Specialty cert; CV only has AWS Essentials | **real_fit_gap** (minor) |
| staff_ai_engineer_global | ZIP CO / Principal Engineer, Generative & Agentic AI | **7.35** | **GOOD_MATCH** | ✅ ✅ ✅ | — | JD requires 15+ years; CV has 10+ years | **real_fit_gap** (minor) |
| ai_eng_manager_eea | ZENDESK / Engineering Manager AI Agents | **7.97** | **GOOD_MATCH** | ✅ ✅ ✅ | — | JD emphasizes conversational/voice agents; CV focuses on AI workflow platform | **acceptable_fit** |
| senior_ai_engineer_eea | TEAM.BLUE / Senior AI Software Engineer | **8.10** | **GOOD_MATCH** | ✅ ✅ ✅ | — | Kafka not explicitly mentioned despite JD requirement | **strong_fit** |

## Dimension summary

| Category | ATS (20) | Impact (25) | JD Align (25) | Exec Pres (15) | Anti-Hall (15) |
|---|---|---|---|---|---|
| ai_architect_eea | 6.5 | 7.5 | 6.0 | 7.5 | 8.0 |
| staff_ai_engineer_global | 8.0 | 7.5 | 6.5 | 6.5 | 8.5 |
| ai_eng_manager_eea | 8.5 | 8.0 | 7.5 | 8.0 | 8.0 |
| senior_ai_engineer_eea | 8.5 | 8.0 | 8.0 | 7.5 | 8.5 |

## Integrity snapshot (vs v2 anchor guardrails)

- **Unsupported claims across the whole batch: 0.** (v2 anchor: 1 total)
- **Missing-must-have entries: 0 across all 4.** (v2 anchor: 4 on ALGOMINDS)
- **Persona fit notes: 0 across 3, 2 minor on senior_ai_engineer_eea (affirmative, not gating).**
- **Anti-hallucination ≥ 7.5 on 4/4 anchors** (regression guard passed; v2 anchor had same).
- **All 3 gates pass on 4/4 anchors.** (v2 anchor had 2/4 clean-gate pairs.)

## Cross-batch totals (anchor v2 + expansion v1 = 8 pairs)

| Verdict | Count | Notes |
|---|---|---|
| GOOD_MATCH | 6 | head_of_ai_global, tech_lead_ai_eea, ai_architect_eea, staff_ai_engineer_global, ai_eng_manager_eea, senior_ai_engineer_eea |
| NEEDS_WORK | 2 | ai_architect_global (ALGOMINDS — real_fit_gap: C#/.NET/PhD), staff_ai_engineer_eea (Reddit — real_fit_gap: 8y search/recsys, Golang) |
| WEAK_MATCH | 0 | — |
| STRONG_MATCH | 0 | — |

Gate pass rate across the 8-pair full active set: **22 of 24 gate checks pass**; the 2 failed gates are both `must_have_coverage_gate` on the two known `real_fit_gap` anchors.

## Generation-gap analysis

Looking for shared controllable failure clusters (would trigger Step 8b):

- **Keyword density / missing specific tools** (Kafka, AWS cert, conversational-agents vocabulary, Pulumi/Go from anchors): appears once per anchor, **never twice in the same category family, never with the same actionable root cause**. Each is an anchor-specific JD-alignment nit, not a stage failure.
- **Persona/title inflation**: zero occurrences. The pipeline correctly stays player-coach for manager category, IC for staff/senior/architect.
- **Unsupported claims**: zero. No fabrication, no cert/education/title invention.
- **Anti-hallucination**: stable at 8.0-8.5 across all 4 anchors.

**Conclusion:** no shared `generation_gap` cluster exists across ≥2 categories. The only systematic pattern is correct anti-hallucination behavior on authentic JD gaps (real_fit_gap), which is the intended pipeline behavior.

## Decision: **A. Pipeline generalizes — expand Step 9 to remaining categories**

All 4 expansion anchors land GOOD_MATCH with all 3 gates passing. Zero unsupported claims, zero missing-must-have entries, anti-hallucination regression guard passed on all 4. No controllable generation cluster appears in either the v2 anchor batch or this expansion batch. The 2 residual NEEDS_WORK pairs across the full 8-pair active set are both `real_fit_gap` (authentic candidate gaps against bad-fit JDs), not pipeline failures.

Step 8b stage diagnostics remain deferred.

**Recommended next steps (in order of value):**
1. Expand Step 9 to the remaining 4 Step 7 rubric categories: `head_of_ai_eea`, `head_of_ai_ksa`, `head_of_ai_uae`, `ai_architect_ksa_uae`.
2. After that 12-pair coverage is complete, sample 2-3 additional JDs per already-tested category to test within-category variance.
3. Only escalate to Step 8b if a repeated controllable generation cluster surfaces during expansion.

## Minor investigation notes (non-blocking)

- **senior_ai_engineer_eea / TEAM.BLUE** had a transient Claude CLI socket/timeout during scoring (first attempt hit `FailedToOpenSocket`, second timed out at 300s); the retry loop succeeded on attempt 3. Not a pipeline or scorer correctness issue; worth noting if it recurs.
- **staff_ai_engineer_global** anti_hallucination (8.5) and ATS (8.0) are the strongest of the batch despite the weakest JD-alignment (6.5) driven by the 15-year experience ask. The pipeline correctly did not inflate years.
- **ai_architect_eea** exec_presence at 7.5 is solid architect-authority framing without people-management drift.

## Artifact pointers

- Expansion manifest: `data/eval/scorecards/batches/step9_expansion_batch_v1_generated.json`
- Expansion scorecards: `data/eval/scorecards/<category>/<jd_stem>_scorecard.{json,md}` ×4
- Expansion snapshots: `data/eval/generated_cvs/step9_expansion_20260417_174209/snapshots/<category>/<jd_stem>__generated.md`
- Expansion logs + meta: `data/eval/generated_cvs/step9_expansion_20260417_174209/{logs,meta}/`
- Anchor v2 reference: `data/eval/scorecards/comparison_v1_v2.md`
- Anchor v1 archive: `data/eval/scorecards_archive/step9_v1_anchor/`
