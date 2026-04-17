---
title: Top Jobs
description: Query MongoDB for top jobs by tier, location, category, recency, and other filters. Supports both level-2 and level-1 collections.
triggers:
  - top jobs
  - best jobs
  - give me jobs
  - list jobs
  - job search
---

# Top Jobs

Query MongoDB for ranked job slices from `jobs.level-2` and `jobs.level-1`.
The script uses a fixed T1→T7 waterfall by default, with optional region
override, category/title filters, promotion from `level-1`, and batch queueing.

## Run

```bash
python3 n8n/skills/top-jobs/scripts/top_jobs.py
```

Requires `MONGODB_URI` in repo-root `.env` or the current environment.

## Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--limit N` | Max jobs to return | `50` |
| `--tier T1,T2,...` | Comma-separated tier filter or `all` | `all` |
| `--profile NAME[,NAME...]` | Role-name profiles: `tech-lead`, `architect`, `staff-principal`, `head-director`, `engineering-manager` | none |
| `--region REGION` | Region override: `eea`, `gcc`, `pk`, `remote`, `ksa`, `uae`, `global` | tier default |
| `--category CAT` | Title category filter: `architect`, `lead`, `staff`, `head`, `manager` | derived from tier |
| `--days N` | Only jobs created within the last N days | none |
| `--min-score N` | Minimum score threshold | none |
| `--require-cv` | Only jobs with generated CV text | off |
| `--status STATUS` | Exact status filter, optionally comma-separated | exclude `applied, discarded, closed, rejected, skipped` |
| `--collection COL` | `level-2`, `level-1`, or `both` | `level-2` |
| `--sort FIELD` | `score`, `date`, or `score-date` | `date` |
| `--company NAME` | Company regex, case-insensitive | none |
| `--title PATTERN` | Custom title regex override | none |
| `--format FMT` | `table`, `json`, `csv`, or `ids` | `table` |
| `--ai-only` | Only `is_ai_job: true` | off |
| `--not-favorite` | Exclude jobs marked favorite/starred | off |
| `--no-header` | Suppress table header row | off |
| `--promote` | Promote matched `level-1` docs into `level-2` | off |
| `--batch` | Queue batch pipeline for queueable results | off |

## Tier Definitions

- `T1` — AI Architect, `remote OR eea`
- `T2` — AI Lead, `remote OR eea`
- `T3` — Staff/Principal AI, `remote OR eea`
- `T4` — Head/Director, `gcc OR pk`
- `T5` — High-score AI, any location, `is_ai_job=true`, `score>=65`, CV required
- `T6` — Engineering Manager + AI, `remote OR eea`
- `T7` — GCC/PK broader leadership, `score>=40`

When `--tier all` is used, the script fills from `T1`, then `T2`, then `T3`,
and continues until `--limit` is satisfied.

## Profile Definitions

Profiles are role-name presets curated from the current titles in both
`level-1` and `level-2`.

- `tech-lead` — lead engineer, lead software engineer, tech lead, technical lead, engineering lead, software/data/platform team lead
- `architect` — architect variants including solutions, enterprise, software, cloud, data, AI
- `staff-principal` — staff, principal, distinguished, fellow
- `head-director` — head, director, VP, chief, CTO/CIO/CAIO
- `engineering-manager` — engineering manager and software engineering manager variants

`--profile` is an alternative to `--tier`; do not combine them.

## Usage Examples

```bash
# Default waterfall from level-2, max 50 rows
python3 n8n/skills/top-jobs/scripts/top_jobs.py

# Limit results
python3 n8n/skills/top-jobs/scripts/top_jobs.py --limit 10

# Query specific tiers in order
python3 n8n/skills/top-jobs/scripts/top_jobs.py --tier T1,T3,T6

# Explicitly request the full waterfall
python3 n8n/skills/top-jobs/scripts/top_jobs.py --tier all

# Role-name profile query
python3 n8n/skills/top-jobs/scripts/top_jobs.py --profile tech-lead

# Multiple profiles in order
python3 n8n/skills/top-jobs/scripts/top_jobs.py --profile tech-lead,architect

# Override tier geography with GCC and Pakistan
python3 n8n/skills/top-jobs/scripts/top_jobs.py --tier T1 --region gcc,pk

# Narrow by title category
python3 n8n/skills/top-jobs/scripts/top_jobs.py --tier T4 --category head

# Only recent jobs from the last 7 days
python3 n8n/skills/top-jobs/scripts/top_jobs.py --days 7

# Require a minimum score
python3 n8n/skills/top-jobs/scripts/top_jobs.py --min-score 60

# Only jobs with CV output already generated
python3 n8n/skills/top-jobs/scripts/top_jobs.py --require-cv

# Override default status exclusions
python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "ready for applying"

# Pull from staging only
python3 n8n/skills/top-jobs/scripts/top_jobs.py --collection level-1

# Search both primary and staging collections
python3 n8n/skills/top-jobs/scripts/top_jobs.py --collection both

# Sort highest score first
python3 n8n/skills/top-jobs/scripts/top_jobs.py --sort score

# Sort by score then recency
python3 n8n/skills/top-jobs/scripts/top_jobs.py --sort score-date

# Filter company names with a regex
python3 n8n/skills/top-jobs/scripts/top_jobs.py --company "Google|DeepMind"

# Override tier title regex entirely
python3 n8n/skills/top-jobs/scripts/top_jobs.py --title "agentic.*architect"

# Emit full JSON instead of a table
python3 n8n/skills/top-jobs/scripts/top_jobs.py --format json

# Emit CSV for spreadsheets or shell pipelines
python3 n8n/skills/top-jobs/scripts/top_jobs.py --format csv

# Emit IDs only
python3 n8n/skills/top-jobs/scripts/top_jobs.py --format ids

# Only AI-classified jobs
python3 n8n/skills/top-jobs/scripts/top_jobs.py --ai-only

# Exclude favorite/starred jobs
python3 n8n/skills/top-jobs/scripts/top_jobs.py --not-favorite

# Print table rows without a header
python3 n8n/skills/top-jobs/scripts/top_jobs.py --no-header

# Promote matched staging jobs into level-2
python3 n8n/skills/top-jobs/scripts/top_jobs.py --collection level-1 --promote

# Queue the current result set into the batch runner
python3 n8n/skills/top-jobs/scripts/top_jobs.py --batch

# Combined example: promote staging jobs, then queue the promoted level-2 IDs
python3 n8n/skills/top-jobs/scripts/top_jobs.py --collection level-1 --tier T5 --require-cv --promote --batch

# Combined example: GCC leadership search with score floor and compact output
python3 n8n/skills/top-jobs/scripts/top_jobs.py --tier T4,T7 --region gcc --min-score 50 --format ids
```

## Output Modes

- `table` — human-readable summary table
- `json` — full documents with helper metadata
- `csv` — flat export with core columns
- `ids` — one Mongo `_id` per line

## Promotion Semantics

With `--promote`, matched `level-1` jobs are checked against `level-2` by
`dedupeKey` first, then by case-insensitive `title + company`.

- If an existing `level-2` doc is found, the `level-1` doc is marked with:
  `promoted_to_level2=True`, `promoted_job_id`, `promoted_at`
- If no match exists, the script copies the document into `level-2` with:
  `status="under processing"`, `source="level1_promoted"`,
  `promoted_from_level1=True`, `level1_job_id=<original_id>`

## Batch Queueing

With `--batch`, the script POSTs queueable `level-2` job IDs to:

`{RUNNER_URL}/api/jobs/{job_id}/operations/batch-pipeline/queue`

Requires `RUNNER_API_SECRET`. If a result only exists in `level-1`, use
`--promote --batch` so it has a `level-2` ID to queue.
