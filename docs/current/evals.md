# Evals

## Extraction 4.1.1 periodic check

When `jd_facts` extraction quality is in question, run the frozen single-job
extraction eval before doing broader smoke or sign-off runs.

Durable eval bundle:

- [data/eval/validation/extraction_4_1_1/README.md](/Users/ala0001t/pers/projects/job-search/data/eval/validation/extraction_4_1_1/README.md)
- [data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job.json](/Users/ala0001t/pers/projects/job-search/data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job.json)
- [data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_runner.json](/Users/ala0001t/pers/projects/job-search/data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_runner.json)
- [data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_candidate_gpt52_frozen.json](/Users/ala0001t/pers/projects/job-search/data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_candidate_gpt52_frozen.json)
- [data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_report_gpt52_frozen.json](/Users/ala0001t/pers/projects/job-search/data/eval/validation/extraction_4_1_1/extraction_4_1_1_one_job_report_gpt52_frozen.json)

Use this check:

- periodically during extraction work
- after prompt changes
- after post-processing changes
- after model-routing changes
- before widening any extraction rollout

Frozen rerun command:

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

Current frozen benchmark outcome:

- schema valid
- remote policy matched
- archetype matched
- responsibilities strong enough to keep
- success metrics strong enough to keep
- qualifications, technical skills, keyword ranking, and role-category remain
  the known weak spots

This eval is the operational baseline for extraction sanity checks until a
larger corpus replaces it as the default fast gate.

## Classification 4.1.2 periodic check

Classification already has a stage-local benchmark harness and should be run
after:

- taxonomy changes
- classification prompt changes
- `jd_facts` model / schema changes that affect `classification` inputs
- routing changes between `gpt-5.4-mini` and `gpt-5.2`

Primary harness:

- [scripts/benchmark_classification_4_1_2.py](/Users/ala0001t/pers/projects/job-search/scripts/benchmark_classification_4_1_2.py)
- [tests/unit/scripts/test_benchmark_classification_4_1_2.py](/Users/ala0001t/pers/projects/job-search/tests/unit/scripts/test_benchmark_classification_4_1_2.py)

Debug live single-job command:

```bash
PYTHONUNBUFFERED=1 \
PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED=false \
./.venv/bin/python -u scripts/debug_classification_v2.py \
  --job-id 69e63f7e12725d7147cc499c \
  --jd-model gpt-5.2 \
  --classification-model gpt-5.4-mini \
  --timeout-seconds 0 \
  --heartbeat-seconds 20 \
  --jd-out /tmp/jd_facts_69e63f7e12725d7147cc499c.json \
  --classification-out /tmp/classification_69e63f7e12725d7147cc499c.json
```

Use this eval surface to inspect:

- primary-role correctness
- top-2 recall under ambiguity
- AI taxonomy quality
- agreement/disagreement with `jd_facts`
- deterministic short-circuit vs LLM disambiguation behavior

This remains the operational classification gate until a durable frozen
classification corpus is checked in under `data/eval/validation/`.
