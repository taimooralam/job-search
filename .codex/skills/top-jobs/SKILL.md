---
name: top-jobs
description: Query MongoDB for top jobs by tier, location, category, score, recency, and collection. Use when the user asks for top jobs, best jobs, give me jobs, or job lists.
argument-hint: --status "under processing" --require-cv --not-favorite --limit 20 --profile tech-lead --format table
---

# Top Jobs

Use `n8n/skills/top-jobs/scripts/top_jobs.py` to query MongoDB for ranked job
results from `jobs.level-2` and `jobs.level-1`.

## Input

Parse `$ARGUMENTS` into CLI flags for the script.

Direct flags:
- `/top-jobs --limit 10 --tier T1,T3`
- `/top-jobs --profile tech-lead`
- `/top-jobs --region gcc,pk --min-score 50`
- `/top-jobs --collection level-1 --promote --batch`

Natural language:
- "give me top 50 jobs" → `--limit 50`
- "top jobs in GCC" → `--region gcc`
- "AI architect jobs" → `--tier T1`
- "tech lead jobs" → `--profile tech-lead`
- "architect roles" → `--profile architect`
- "staff/principal roles" → `--profile staff-principal`
- "head/director roles" → `--profile head-director`
- "engineering manager roles" → `--profile engineering-manager`
- "head/director jobs in KSA or UAE" → `--tier T4 --region gcc`
- "last 7 days" → `--days 7`
- "score above 60" → `--min-score 60`
- "with CV only" → `--require-cv`
- "AI jobs only" → `--ai-only`
- "JSON" → `--format json`
- "CSV" → `--format csv`
- "IDs only" → `--format ids`
- "promote level-1 jobs and queue them" → `--collection level-1 --promote --batch`

No arguments:
- Run with defaults: `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite`

## Step 1: Run the Script

IMPORTANT: This script needs network access to MongoDB (`72.61.92.76:27018`).
Run with full network access or escalate immediately if the first attempt fails
with a MongoDB connection error.

```bash
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate && python3 n8n/skills/top-jobs/scripts/top_jobs.py $FLAGS
```

Where `$FLAGS` is the normalized flag string from the user request.

Implicit defaults, unless the user explicitly overrides them:
- `--status "under processing"`
- `--require-cv`
- `--not-favorite`

## Step 2: Interpret Output

- `stdout` contains the result payload
- `stderr` contains progress logs, promotion logs, and batch queue logs

If the format is:
- `table`: present the table and summarize the number of matches
- `json`: return the JSON payload directly or summarize it if the user asked for analysis
- `csv`: return the CSV payload directly
- `ids`: return one ID per line

## Step 3: Report Mutations

If `--promote` is used, report:
- how many `level-1` docs were checked
- how many were newly promoted
- how many were already present in `level-2`

If `--batch` is used, report:
- how many jobs were queued
- how many failed
- whether any `level-1` rows were skipped because they had no `level-2` ID

## Flag Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | `50` | Max jobs to return |
| `--tier T1,T2,...` | `all` | Tiers to query, in order |
| `--profile NAME[,NAME...]` | none | Role-name profiles: `tech-lead`, `architect`, `staff-principal`, `head-director`, `engineering-manager` |
| `--region REGION` | tier default | Region override: `eea`, `gcc`, `pk`, `remote`, `ksa`, `uae`, `global` |
| `--category CAT` | tier-derived | Title category filter |
| `--days N` | none | Only jobs created within the last N days |
| `--min-score N` | none | Minimum score threshold |
| `--require-cv` | off | Only jobs with generated CV text |
| `--status STATUS` | exclude terminal statuses | Exact status filter |
| `--collection COL` | `level-2` | `level-2`, `level-1`, or `both` |
| `--sort FIELD` | `date` | `score`, `date`, or `score-date` |
| `--company NAME` | none | Company regex filter |
| `--title PATTERN` | none | Custom title regex override |
| `--format FMT` | `table` | `table`, `json`, `csv`, or `ids` |
| `--ai-only` | off | Only `is_ai_job: true` |
| `--not-favorite` | off | Exclude jobs marked favorite/starred |
| `--no-header` | off | Suppress table header row |
| `--promote` | off | Promote matched `level-1` docs into `level-2` |
| `--batch` | off | Queue batch pipeline for queueable results |

## Override Rules

- If the user does not specify status, use `--status "under processing"`.
- If the user does not explicitly ask to include missing-CV jobs, use `--require-cv`.
- If the user does not explicitly ask for favorites/starred jobs, use `--not-favorite`.
- If the user asks for favorites/starred jobs, omit `--not-favorite`.
- If the user asks for another status or "any status", omit the default status flag.
- If the user asks for a role-name family like tech lead or architect, prefer `--profile` over `--tier`.
- Do not combine `--profile` and `--tier`.

## Profiles

Profiles are curated from current `level-1` and `level-2` role titles:

- `tech-lead` — lead engineer, lead software engineer, tech lead, technical lead, engineering lead, software/data/platform team lead
- `architect` — architect variants including solutions, enterprise, software, cloud, data, AI
- `staff-principal` — staff, principal, distinguished, fellow
- `head-director` — head, director, VP, chief, CTO/CIO/CAIO
- `engineering-manager` — engineering manager and software engineering manager variants
