# 2026-04-21: `jd_facts` Model Selection

## Decision

`jd_facts` is pinned to `gpt-5.2` as the default Codex model for iteration-4.1 extraction.

## Applies To

- `src/preenrich/types.py` stage defaults
- `src/preenrich/stages/jd_facts.py` internal default model selection
- `scripts/preenrich_model_preflight.py` default preflight model
- `.env.example`
- `infra/env/scout-workers.env.example`

## Why

- The 4.1 extraction path is schema-heavy and sensitive to model-to-model output drift.
- Recent local live runs showed that extraction validation work is easier to stabilize when the runtime is pinned to one explicit model rather than drifting between `gpt-5.4-mini` and other Codex variants.
- This keeps local validation, VPS rollout, and operator expectation aligned.

## Constraints

- Codex-only for iteration 4.1.x extraction.
- No implicit fallback to Claude.
- No unplanned model swaps between runs.

## Override Rule

Only override `PREENRICH_MODEL_JD_FACTS` intentionally for a named experiment or rollout, and record that change in the relevant runbook or validation notes.
