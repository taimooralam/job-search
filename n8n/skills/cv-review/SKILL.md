---
title: CV Review
description: Independent GPT-based CV critique from a hiring manager's perspective.
triggers:
  - review cv
  - grade cv
  - critique cv
  - check cv
---

# CV Review

Independent hiring manager critique of generated CVs. Focuses on what a hiring manager sees in the first 6 seconds (top 1/3) vs what they want to see.

Completely separate from the pipeline's CVGrader — this is a "second opinion" that sends a single large prompt to GPT with the CV, extracted JD, and master CV as context.

## Usage

```bash
# Trigger review via runner API
python3 scripts/trigger_review.py --job-id <id>

# Show existing review
python3 scripts/show_review.py --job-id <id>

# List jobs with CVs but no review
python3 scripts/list_unreviewed.py
```

## Review Dimensions
- Top 1/3 assessment (headline, tagline, achievements, competencies)
- Pain point alignment (covered vs missing)
- Hallucination flags (claims not in master CV)
- ATS survival check (keywords, acronyms, front-loading)
- Ideal candidate fit (archetype, traits, experience level)

## Output Fields
- `verdict`: STRONG_MATCH | GOOD_MATCH | NEEDS_WORK | WEAK_MATCH
- `would_interview`: true/false hiring decision
- `confidence`: 0.0-1.0
- `first_impression_score`: 1-10 (based on top 1/3 scan)
- `full_review`: complete structured JSON critique

## Bulk Review (Local Codex)

Run batch CV reviews locally via Codex CLI. Avoids VPS OAuth token contention
(see [openai/codex#10332](https://github.com/openai/codex/issues/10332)).

```bash
# Review all unreviewed CVs (default limit 20)
python3 scripts/bulk_review.py

# Review up to 50, only "ready for applying" jobs
python3 scripts/bulk_review.py --limit 50 --status "ready for applying"

# Dry run — just list candidates
python3 scripts/bulk_review.py --dry-run

# Re-review jobs that already have reviews
python3 scripts/bulk_review.py --re-review --limit 10

# Filter by company
python3 scripts/bulk_review.py --company Microsoft

# Single job
python3 scripts/bulk_review.py --job-id 6612abc123def456
```

Requires: `MONGODB_URI` in `.env` or environment. Runs `codex exec` locally (Mac).

### Why Local (Not Pipeline)

CV review uses Codex CLI with ChatGPT Plus OAuth. The VPS runs 3 runner
containers sharing one auth token — OAuth refresh token rotation kills the
token within minutes. Codex on a local Mac with a single process avoids this.

## Environment Variables
- `RUNNER_URL` — Pipeline runner API base URL
- `RUNNER_API_SECRET` — Bearer token for runner API
- `MONGODB_URI` — MongoDB connection string
- `OPENAI_API_KEY` — OpenAI API key for GPT calls
- `CV_REVIEW_MODEL` — Model override (default: gpt-5.4-mini)
