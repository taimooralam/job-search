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

## Application Surface 4.1.3 periodic check

Application-surface resolution should be rerun after:

- URL normalization changes
- portal-family / ATS detection changes
- fail-open policy changes
- application-surface prompt changes
- research transport changes that affect live Codex verification

Primary harness:

- [scripts/benchmark_application_surface_4_1_3.py](/Users/ala0001t/pers/projects/job-search/scripts/benchmark_application_surface_4_1_3.py)
- [tests/unit/scripts/test_benchmark_application_surface_4_1_3.py](/Users/ala0001t/pers/projects/job-search/tests/unit/scripts/test_benchmark_application_surface_4_1_3.py)
- [tests/fixtures/application_surface_benchmark.json](/Users/ala0001t/pers/projects/job-search/tests/fixtures/application_surface_benchmark.json)

Debug live single-job command:

```bash
PYTHONUNBUFFERED=1 \
WEB_RESEARCH_ENABLED=true \
PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED=false \
./.venv/bin/python -u scripts/debug_application_surface_v2.py \
  --job-id 69e63f7e12725d7147cc499c \
  --jd-model gpt-5.2 \
  --classification-model gpt-5.4-mini \
  --application-model gpt-5.2 \
  --application-transport codex_web_search \
  --timeout-seconds 0 \
  --heartbeat-seconds 20 \
  --jd-out /tmp/jd_facts_69e63f7e12725d7147cc499c.application.json \
  --classification-out /tmp/classification_69e63f7e12725d7147cc499c.application.json \
  --application-out /tmp/application_surface_69e63f7e12725d7147cc499c.json
```

Use this eval surface to inspect:

- exact canonical URL matches
- partial employer-portal correctness when exact deep link is unavailable
- portal-family and ATS-vendor accuracy
- stale/closed/duplicate correctness
- unresolved-but-useful handling
- cross-company rejection behavior
- source and evidence preservation

Fixture benchmark command:

```bash
./.venv/bin/python scripts/benchmark_application_surface_4_1_3.py \
  --corpus tests/fixtures/application_surface_benchmark.json \
  --use-fixture-candidate
```

## Company / Role Enrichment 4.1.3 periodic check

Company and role enrichment should be rerun after:

- company prompt changes
- role prompt changes
- ingress normalization changes for `company_profile` or `role_profile`
- canonical company/role schema changes
- research transport changes that affect live Codex company/role research

Primary harness:

- [scripts/benchmark_company_role_enrichment_4_1_3.py](/Users/ala0001t/pers/projects/job-search/scripts/benchmark_company_role_enrichment_4_1_3.py)
- [tests/unit/scripts/test_benchmark_company_role_enrichment_4_1_3.py](/Users/ala0001t/pers/projects/job-search/tests/unit/scripts/test_benchmark_company_role_enrichment_4_1_3.py)
- [tests/fixtures/research_enrichment_benchmark/sample_job.json](/Users/ala0001t/pers/projects/job-search/tests/fixtures/research_enrichment_benchmark/sample_job.json)
- [tests/fixtures/research_enrichment_benchmark/robson_bale_company_role.json](/Users/ala0001t/pers/projects/job-search/tests/fixtures/research_enrichment_benchmark/robson_bale_company_role.json)

Debug live single-job command:

```bash
PYTHONUNBUFFERED=1 \
WEB_RESEARCH_ENABLED=true \
PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED=false \
PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true \
PREENRICH_RESEARCH_FALLBACK_PROVIDER=none \
PREENRICH_RESEARCH_FALLBACK_TRANSPORT=none \
./.venv/bin/python -u scripts/debug_company_role_enrichment_v2.py \
  --job-id 69e63f7e12725d7147cc499c \
  --jd-model gpt-5.2 \
  --classification-model gpt-5.4-mini \
  --application-model gpt-5.2 \
  --research-model gpt-5.2 \
  --application-transport codex_web_search \
  --research-transport codex_web_search \
  --timeout-seconds 0 \
  --heartbeat-seconds 20 \
  --jd-out /tmp/jd_facts_69e63f7e12725d7147cc499c.research.json \
  --classification-out /tmp/classification_69e63f7e12725d7147cc499c.research.json \
  --application-out /tmp/application_surface_69e63f7e12725d7147cc499c.research.json \
  --research-out /tmp/research_enrichment_69e63f7e12725d7147cc499c.json
```

Use this eval surface to inspect:

- company identity correctness
- company summary factuality
- role summary factuality
- why-now and role/company alignment quality
- source and evidence preservation
- richness retention in companion fields
- compact alias availability for downstream readers
- unresolved-but-useful handling for company/role artifacts

Fixture benchmark command:

```bash
./.venv/bin/python scripts/benchmark_company_role_enrichment_4_1_3.py \
  --corpus-dir tests/fixtures/research_enrichment_benchmark
```

## Stakeholder Surface 4.2.1 periodic check

Stakeholder-surface evaluation should be rerun after:

- stakeholder identity schema changes
- stakeholder discovery / profile / inferred-persona prompt changes
- evaluator coverage derivation changes
- persona fail-open policy changes
- safety/privacy validation changes

Primary harness:

- [scripts/benchmark_stakeholder_surface_4_2_1.py](/Users/ala0001t/pers/projects/job-search/scripts/benchmark_stakeholder_surface_4_2_1.py)
- [tests/unit/scripts/test_benchmark_stakeholder_surface_4_2_1.py](/Users/ala0001t/pers/projects/job-search/tests/unit/scripts/test_benchmark_stakeholder_surface_4_2_1.py)
- [evals/stakeholder_surface_4_2_1/README.md](/Users/ala0001t/pers/projects/job-search/evals/stakeholder_surface_4_2_1/README.md)
- [evals/stakeholder_surface_4_2_1/stakeholder_surface_cases.json](/Users/ala0001t/pers/projects/job-search/evals/stakeholder_surface_4_2_1/stakeholder_surface_cases.json)

Use this eval surface to inspect:

- real stakeholder identity precision
- inferred-persona fallback correctness
- ambiguous/cross-company identity rejection
- privacy and public-professional safety compliance
- resolved vs inferred labeling correctness
- usefulness of downstream CV preference signals

Fixture benchmark command:

```bash
./.venv/bin/python scripts/benchmark_stakeholder_surface_4_2_1.py \
  --corpus evals/stakeholder_surface_4_2_1/stakeholder_surface_cases.json
```
