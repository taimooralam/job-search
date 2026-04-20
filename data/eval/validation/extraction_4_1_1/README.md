# Extraction 4.1.1 Frozen Check

This directory holds the durable reference bundle for the frozen single-job
`jd_facts` extraction check that was run with:

- model: `gpt-5.2`
- upward escalation: disabled
- fallback: disabled
- live compat write: disabled

## Purpose

Use this as the first extraction sanity check whenever `jd_facts`,
`build_p_jd_extract()`, post-processing, or extraction model routing is in
question.

This is not the full sign-off corpus. It is the fast, stable debug eval that
should be run before broader smoke or sign-off corpora.

## Files

- `extraction_4_1_1_one_job.json`
  - one-job benchmark corpus input, including the JD text and
    `processed_jd_sections`
- `extraction_4_1_1_one_job_runner.json`
  - runner-era baseline extraction for the same job
- `extraction_4_1_1_one_job_candidate_gpt52_frozen.json`
  - frozen `gpt-5.2` candidate extraction output
- `extraction_4_1_1_one_job_report_gpt52_frozen.json`
  - benchmark summary and field-by-field comparison report

## Frozen command

```bash
PYTHONUNBUFFERED=1 \
PREENRICH_JD_FACTS_V2_ENABLED=true \
PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED=false \
PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED=false \
./.venv/bin/python scripts/benchmark_extraction_4_1_1.py \
  --corpus data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job.json \
  --model gpt-5.2 \
  --codex-timeout-seconds 3600 \
  --report-out data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_report_gpt52_frozen.rerun.json
```

## Frozen result

- `schema_validity_pass_rate = 1.0`
- `remote_policy_match_rate = 1.0`
- `responsibilities_item_f1_mean = 0.8571428571428571`
- `qualifications_item_f1_mean = 0.5`
- `technical_skills_item_f1_mean = 0.56`
- `success_metrics_item_f1_mean = 0.8`
- `keyword_precision_at_10 = 0.3`
- `keyword_recall_at_10 = 0.3`
- `ideal_candidate_archetype_match_rate = 1.0`
- `passes_thresholds = false`

## Review guidance

Treat this as the minimum debug gate.

Investigate immediately if any rerun shows:

- schema validity dropping below `1.0`
- remote policy mismatch
- responsibilities regressing materially from the frozen result
- success metrics regressing materially from the frozen result
- archetype mismatch

Known weak areas in the frozen baseline:

- role-category mismatch vs runner baseline
- qualifications below target threshold
- technical-skills coverage below target threshold
- keyword ranking below target threshold
