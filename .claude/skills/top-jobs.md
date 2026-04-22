---
description: Query MongoDB for top jobs by tier, location, category, and filters. Use when user asks for "top jobs", "best jobs", "give me jobs", or similar.
---

# Top Jobs Skill

Run the top-jobs query script with flags derived from the user request.

## Usage Patterns

- "give me top 50 jobs" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --limit 50`
- "top jobs in GCC" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --region gcc`
- "head of AI jobs in KSA and UAE" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --tier T4 --region gcc --category head`
- "AI architect jobs last 7 days" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --tier T1 --days 7`
- "tech lead jobs" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --profile tech-lead`
- "architect roles" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --profile architect`
- "staff or principal roles" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --profile staff-principal`
- "head/director roles" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --profile head-director`
- "engineering manager roles" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --profile engineering-manager`
- "promote level-1 jobs and run batch" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --collection level-1 --promote --batch`
- "jobs with score > 60" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --min-score 60`
- "list job IDs for piping" → `python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite --format ids`

## Execution

Run from the repo root:

```bash
cd /Users/ala0001t/pers/projects/job-search
python3 n8n/skills/top-jobs/scripts/top_jobs.py $ARGUMENTS
```

Capture:
- `stdout` as the result payload (`table`, `json`, `csv`, or `ids`)
- `stderr` as progress, promotion, and batch queue logs

Default implicit filters, unless the user explicitly overrides them:

- `--status "under processing"`
- `--require-cv`
- `--not-favorite`

If the user does not specify filters, run:

```bash
python3 n8n/skills/top-jobs/scripts/top_jobs.py --status "under processing" --require-cv --not-favorite
```

## Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--limit N` | Max jobs to return | `50` |
| `--tier T1,T2,...` | Comma-separated tiers or `all` | `all` |
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
| `--no-header` | Suppress header row in table output | off |
| `--promote` | Promote matched `level-1` docs into `level-2` | off |
| `--batch` | Queue batch pipeline for queueable results | off |

## Interpretation Rules

- Preserve direct CLI flags when the user already supplied them.
- Unless the user explicitly asks for a different status, missing CVs, or favorites/starred jobs, inject these defaults:
  - `--status "under processing"`
  - `--require-cv`
  - `--not-favorite`
- Translate natural language into flags when obvious:
  - "tech lead", "technical lead", "lead engineer", "engineering lead" → `--profile tech-lead`
  - "architect roles" → `--profile architect`
  - "staff/principal roles" → `--profile staff-principal`
  - "head/director roles" → `--profile head-director`
  - "engineering manager roles" → `--profile engineering-manager`
  - "last 3 days" → `--days 3`
  - "remote only" → `--region remote`
  - "GCC and Pakistan" → `--region gcc,pk`
  - "only AI jobs" → `--ai-only`
  - "with CV" → `--require-cv`
  - "favorites only" or "starred jobs" → omit `--not-favorite`
  - "any status" → omit default `--status "under processing"`
  - "JSON" → `--format json`
  - "CSV" → `--format csv`
  - "IDs only" → `--format ids`
- Do not combine `--profile` and `--tier` in the same command.
- If the user asks for level-1 jobs to be queued, add `--promote` before `--batch`.
- Prefer `--tier T1` for AI architect requests, `--tier T2` for AI lead requests,
  `--tier T3` for staff/principal AI requests, `--tier T4` for head/director
  leadership requests, `--tier T5` for high-score AI jobs, `--tier T6` for AI
  engineering manager requests, and `--tier T7` for broader GCC/PK leadership.

## Profile Notes

Profiles are role-name presets curated from current `level-1` and `level-2`
titles. They focus on title families rather than AI/non-AI content:

- `tech-lead` — lead engineer, tech lead, technical lead, engineering lead, software engineering lead, development/data/platform team lead
- `architect` — solution, enterprise, cloud, software, data, AI architect variants
- `staff-principal` — staff, principal, distinguished, fellow roles
- `head-director` — head, director, VP, chief, CTO/CIO/CAIO roles
- `engineering-manager` — engineering manager and software engineering manager families
