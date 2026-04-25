# CV Eval Rubrics (Step 7 / Step 8 / Step 8b)

This directory holds reusable category-level CV eval rubrics grounded in Step 5 blueprints and Step 6 baselines.

## Contents

- `{category}_rubric.json` — strict rubric JSON (contract defined in scripts/eval_step7_rubrics.py)
- `{category}_rubric.md` — deterministic Markdown render of the JSON
- `scorecard_template.json` — Step 8 scorecard template (populate per CV eval run)
- `stage_scorecard_template.json` — Step 8b placeholder (stage-level diagnostics)
- `index.md` — rubric index
- `debug/{category}/{timestamp}/` — per-run prompt/response/validation artifacts

## Rubric contract

5 dimensions with fixed weights summing to 100:
- ats_optimization (20), impact_clarity (25), jd_alignment (25), executive_presence (15), anti_hallucination (15)

3 gates: must_have_coverage_gate, unsafe_claim_gate, persona_fit_gate

Verdicts:
- STRONG_MATCH >= 8.5, GOOD_MATCH >= 7.0, NEEDS_WORK >= 5.5, WEAK_MATCH <= 5.49

## Persona framing by category family

- ai_architect_*: executive_presence = architectural authority / system ownership
- staff_ai_engineer_* / senior_* / principal_*: senior IC authority / judgment / influence, no formal management
- head_of_ai_*: player-coach AI platform leadership (architect-first, not executive inflation)

## Regeneration

```
python scripts/eval_step7_rubrics.py --force --provider claude --verbose
python scripts/eval_step7_rubrics.py --category ai_architect_global --force
python scripts/eval_step7_rubrics.py --render-only
```

Rubric version: 2026-04-17
