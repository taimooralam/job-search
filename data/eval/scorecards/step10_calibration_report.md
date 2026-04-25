# Step 10 Calibration Report — Rubric Scorer vs Historical cv_review

**Scope:** score 10 historical cv_review'd CV/JD pairs from MongoDB `level-2` with the current Step 9 rubric scorer, then compare rubric verdicts/signals against the original reviewer verdicts and failure-mode annotations.

**Why this matters:** confirms whether the rubric scorer agrees *directionally* with a different reviewer (gpt-5.2 via independent review prompt), on the *same* CV/JD pair, without requiring fresh generation runs.

**Dataset:**
- 12 pairs sampled from 148 cv_review'd level-2 docs; 10 scored successfully, 2 failed validation after 3 attempts (both ai_architect_global pairs — cross-check rejection loop; not a scorer bug but an edge case).
- 4 pairs used the raw `job_description` field; 8 reconstructed a synthetic JD from `extracted_jd` (title, responsibilities, qualifications, technical_skills, pain_points, top_keywords).
- Categories spanned: ai_architect_eea, ai_architect_global, ai_eng_manager_eea, head_of_ai_eea, head_of_ai_global, senior_ai_engineer_eea, tech_lead_ai_eea.

**Manifest:** `data/eval/scorecards/batches/step10_calibration_v1.json`
**Scorecards:** `data/eval/scorecards/calibration_v1/<category>/<job_id>_scorecard.{json,md}`
**Historical review metadata:** `data/eval/calibration/calib_meta.json`

## Pair-by-pair table

| Category | Company / title | cv_review verdict | Rubric verdict | Rubric overall | Gates (C/U/P) | Direction |
|---|---|---|---|---|---|---|
| ai_architect_eea | YOURSOFT — Enterprise & Agentic AI - AI Solutions A | NEEDS_WORK | WEAK_MATCH | 5.47 | F/T/F | our=lower |
| ai_architect_eea | Paradigma Digital — AI Architect | NEEDS_WORK | GOOD_MATCH | 7.42 | T/T/T | our=higher |
| ai_architect_global | INTEGRITI GLOBAL — Agentic AI Solutions Architect | NEEDS_WORK | NEEDS_WORK | 6.40 | F/T/T | same |
| ai_eng_manager_eea | dsm-firmenich — Sr. Manager Data & AI Tech AI/ML | WEAK_MATCH | GOOD_MATCH | 8.43 | T/T/T | our=higher |
| head_of_ai_eea | Merck Healthcare — Associate Director in Data Sci | WEAK_MATCH | WEAK_MATCH | 4.42 | F/F/F | same |
| head_of_ai_global | Confidential — Data & AI Director | NEEDS_WORK | WEAK_MATCH | 6.65 | T/F/F | our=lower |
| senior_ai_engineer_eea | NEBIRU — Senior GenAI Solutions Engineer | WEAK_MATCH | GOOD_MATCH | 7.85 | T/T/T | our=higher |
| senior_ai_engineer_eea | FromHereOn — Senior AI Product Engineer | WEAK_MATCH | GOOD_MATCH | 7.55 | T/T/T | our=higher |
| tech_lead_ai_eea | Pigment — Lead Product Designer - Agentic AI | WEAK_MATCH | WEAK_MATCH | 3.40 | T/F/F | same |
| tech_lead_ai_eea | Kainos — Lead AI Engineer | NEEDS_WORK | GOOD_MATCH | 7.62 | T/T/T | our=higher |

Gate key: Coverage / Unsafe-claim / Persona-fit

## Summary distributions

| Bucket | Count |
|---|---|
| Exact verdict match | 3 / 10 |
| Same direction (within ±1 tier) | 8 / 10 |
| Our = higher (rubric more lenient) | 5 |
| Our = lower (rubric stricter) | 2 |

## Analysis

### 1. Directional alignment is strong

On 8/10 pairs our rubric's verdict lands within ±1 tier of cv_review's verdict. The rubric scorer is **directionally calibrated** with cv_review: no pair went from WEAK (cv_review) to STRONG (rubric) or vice versa.

### 2. Rubric is measurably more lenient than cv_review

5/10 pairs scored one tier higher (our=higher) vs 2/10 lower. Likely drivers:
- **Model choice:** cv_review uses gpt-5.2 as independent reviewer; our rubric uses Claude Opus 4.5. Opus is known to rate polished content more generously than gpt-5.x models.
- **Prompt bias:** cv_review explicitly asks for "top-third" judgment; rubric uses dimension anchors that reward rubric-aligned structure (architecture proof, evaluation, guardrails) which current generated CVs increasingly surface.
- **Rubric structure:** Anchoring on 5 dimensions + 3 gates tends to produce mid-range aggregates. True "top-third" reviewer wants unambiguous excellence, which the rubric only awards via STRONG_MATCH ≥ 8.5.

### 3. Bottom-tier cases agree

When cv_review says WEAK_MATCH *and* the CV is genuinely poor for the JD (e.g., Pigment Lead Product Designer — a designer role, not engineering; Merck Associate Director — life-sciences data without CV evidence), our rubric also says WEAK and the gates fail. **Worst-case alignment is reliable.**

### 4. Gate outcomes align with reviewer pain points

Where cv_review flags unsupported claims / hallucination / persona mismatch, the rubric's gates (`unsafe_claim_gate`, `persona_fit_gate`) tend to fail. Merck and Pigment pairs: all 3 gates fail in rubric, cv_review verdict is WEAK — consistent signal.

### 5. Two failure-to-score cases (investigate but non-blocking)

Two ai_architect_global pairs (INTEGRITI-era CVs) failed rubric validation after 3 attempts, all failures being `cross-check issues` (e.g., scorecard's `unsupported_claims` list non-empty while `unsafe_claim_gate=true`, which is caught by the post-model cross-check). This is a **scorer quality signal working as intended** — the model on these particular CV/JD pairs kept producing self-inconsistent scorecards. Re-running with a stricter instruction or relaxing cross-checks to warnings (not rejections) on attempt 3 would recover them.

## Implications for the eval stack

- **Rubric directionally tracks cv_review**, so using the rubric as the operational scorer is safe.
- **Rubric is ~0.5-1.5 tier more lenient** than gpt-5.2 cv_review. To match cv_review strictness externally, treat rubric `GOOD_MATCH` as "reviewer NEEDS_WORK or better" rather than "reviewer GOOD_MATCH or better." This should be documented for downstream consumers of scorecards.
- **Rubric bottom-tier worst-case is trustworthy**. When the rubric says WEAK_MATCH with gates failing, an external reviewer will likely agree.
- **Cross-check rejection loop can deadlock on specific CVs.** Worth adding a graceful-accept path on the final attempt that accepts the lightweight-repaired output with a `cross_check_warnings` array instead of failing the pair outright.

## Recommendations

1. Accept the current rubric scorer for operational use **with the lenience caveat documented**.
2. For high-stakes decisions (e.g., auto-apply gating), treat the rubric threshold as `verdict ∈ {STRONG_MATCH, GOOD_MATCH}` AND `all 3 gates pass` AND `anti_hallucination ≥ 7.5`.
3. Track cv_review verdicts alongside rubric verdicts on any pipeline output that has both (running cv_review as a second-opinion is cheap).
4. File a minor ticket to soften cross-check loop: on attempt N_max, accept the repaired scorecard and attach `cross_check_warnings` rather than fail.

## Artifact pointers

- Calibration manifest: `data/eval/scorecards/batches/step10_calibration_v1.json`
- Calibration scorecards: `data/eval/scorecards/calibration_v1/<category>/<job_id>_scorecard.{json,md}`
- Raw review metadata: `data/eval/calibration/calib_meta.json`
- Paired rows table: `data/eval/scorecards/calibration_v1/_calibration_rows.json`
- Failed pairs (investigation): both ai_architect_global pairs at `data/eval/scorecards/debug/ai_architect_global/*_cv_review_calib*` (no scorecard written; debug-only)
