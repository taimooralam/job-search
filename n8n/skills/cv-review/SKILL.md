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

## Environment Variables
- `RUNNER_URL` — Pipeline runner API base URL
- `RUNNER_API_SECRET` — Bearer token for runner API
- `MONGODB_URI` — MongoDB connection string
- `OPENAI_API_KEY` — OpenAI API key for GPT calls
- `CV_REVIEW_MODEL` — Model override (default: gpt-4o)
