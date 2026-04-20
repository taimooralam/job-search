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
