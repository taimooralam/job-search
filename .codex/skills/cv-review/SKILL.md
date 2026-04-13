---
name: cv-review
description: Run bulk CV reviews locally via Codex CLI (gpt-5.2). Reviews generated CVs from a hiring manager's perspective.
argument-hint: --limit 10 --status "ready for applying"
---

# Bulk CV Review

Run independent hiring-manager CV reviews locally via Codex CLI. Reviews generated CVs against JD, master CV, and project files. Produces structured verdicts, rewrite suggestions, hallucination flags, and ATS checks.

## Argument Parsing

The user may pass `$ARGUMENTS` in many forms. Normalize them into flags for the script:

**Direct flags** (pass through as-is):
- `/cv-review --limit 10 --company Google`
- `/cv-review --dry-run --since 7`
- `/cv-review --job-id 6612abc123 6612def456`

**Natural language** (convert to flags):
- "review 5 jobs" → `--limit 5`
- "review Google jobs" → `--company Google`
- "review ready jobs" or "review ready for applying" → `--status "ready for applying"`
- "dry run" or "just list" or "show candidates" → `--dry-run`
- "re-review" or "redo reviews" → `--re-review`
- "last 3 days" or "since 3 days" → `--since 3`
- "tier A only" → `--tier A`

**Bare job IDs** (24 hex chars, with or without commas/spaces):
- `/cv-review 6612abc123def456789abcde` → `--job-id 6612abc123def456789abcde`
- `/cv-review 6612abc123def456789abcde, 6612abc123def456789abcdf` → `--job-id 6612abc123def456789abcde 6612abc123def456789abcdf`
- Pasted list (one per line) → collect all and pass as `--job-id ID1 ID2 ...`

**No arguments** → run with defaults (20 unreviewed jobs).

## Step 1: Run the Bulk Review Script

**IMPORTANT: This script needs network access to MongoDB (72.61.92.76:27018). Always run with full sandbox access to avoid connection failures.**

```bash
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate && python3 n8n/skills/cv-review/scripts/bulk_review.py $FLAGS
```

If the command fails with a MongoDB connection error, re-run it using `codex -s danger-full-access` or escalate to full network access immediately.

Where `$FLAGS` is the normalized argument string from parsing above.

## Step 2: Report Results

After the script completes, summarize:
- Total reviewed / failed / skipped
- Verdict distribution (STRONG_MATCH, GOOD_MATCH, NEEDS_WORK, WEAK_MATCH)
- Any hallucination flags or failure modes worth noting
- If auth failed, tell the user to re-authenticate Codex (`codex auth login`)

## Script Flags Reference

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit N` | int | 20 | Max jobs to review |
| `--status "..."` | str | — | Filter by job status |
| `--tier X` | str | — | Filter by tier (A/B/C) |
| `--company "..."` | str | — | Filter by company (substring) |
| `--since N` | int | — | Only jobs from last N days |
| `--job-id ID [ID ...]` | str+ | — | Specific job ID(s) |
| `--re-review` | flag | — | Overwrite existing reviews |
| `--dry-run` | flag | — | List candidates only |
| `--model MODEL` | str | gpt-5.2 | Override Codex model |
| `-v` | flag | — | Verbose output |

## Notes

- Reviews run **sequentially** (~2-3 min each with gpt-5.2)
- Uses local Codex OAuth (ChatGPT Plus) — no API key needed
- Results saved to MongoDB `level-2.cv_review`
