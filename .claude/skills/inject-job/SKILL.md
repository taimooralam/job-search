---
name: inject-job
description: Inject a job from a recruiter or job posting into MongoDB, run the full batch pipeline, research the company/role, perform gap analysis, and prepare for the interview. Use when a job description is provided and needs end-to-end processing.
argument-hint: <paste the full job description>
disable-model-invocation: true
---

# Recruiter Job Injection & Research Pipeline

You are given a job description (JD). Execute the full end-to-end workflow below.

## Input

The user will provide: `$ARGUMENTS`

This contains the job description text. Parse it to extract:
- **Company name** (may be the recruiter agency or end client)
- **Job title**
- **Location** (look for remote/hybrid/city)
- **Job type** (contract, permanent, freelance — infer from context)
- **Recruiter name and agency** (if mentioned)
- **Job URL** (if provided, otherwise use the company/agency website)
- **Description** (the full JD text)

## Step 1: Insert Job into MongoDB

Use pymongo to insert into the `level-2` collection. Read credentials from `.env` (MONGODB_URI).

Follow the schema from `scripts/ingest_jobs_cron.py:76-106`:

```python
from pymongo import MongoClient
from datetime import datetime
import os

# Load MONGODB_URI from .env
# Parse it or use it directly

doc = {
    "company": "<extracted company>",
    "title": "<extracted title>",
    "location": "<extracted location>",
    "jobUrl": "<extracted or inferred URL>",
    "description": "<full JD text>",
    "dedupeKey": "<company|title|location|source>".lower().strip(),
    "createdAt": datetime.utcnow(),
    "status": "under processing",
    "source": "recruiter_direct",  # or "job_board", "referral"
    "auto_discovered": False,
    "quick_score": 90,  # High score for manually injected jobs
    "quick_score_rationale": "<brief rationale for the score>",
    "tier": "A",
    "salary": None,  # or extracted salary if available
    "jobType": "<contract|permanent|freelance>",
    "starred": True,
    "starredAt": datetime.utcnow(),
}
```

Print the inserted `_id`.

## Step 2: Trigger Batch Pipeline

Call the runner service to queue the full 7-layer pipeline:

```
POST https://runner.uqab.digital/api/jobs/{job_id}/operations/batch-pipeline/queue
Authorization: Bearer {RUNNER_API_SECRET from .env}
Content-Type: application/json
Body: {"tier": "quality"}
```

Capture the `run_id` from the response.

## Step 3: Monitor Pipeline

Poll the job in MongoDB for `cv_text` field to confirm pipeline completion:

```python
job = col.find_one({"_id": ObjectId(job_id)}, {"cv_text": 1, "status": 1})
```

If `cv_text` is populated, the pipeline is done. Poll every 30 seconds, timeout after 10 minutes.

## Step 4: Internet Research & Gap Analysis

While waiting for / after pipeline completion, perform web research:

1. **Company intel** — Search for the company/agency, their size, reputation, industry
2. **Salary/rate benchmarks** — Search for the role title + location + contract type hourly/daily rates
3. **Market context** — Demand for this role type in the region

Then read the candidate's master CV data from `data/master-cv/roles/` and `data/master-cv/role_skills_taxonomy.json`.

Perform gap analysis: compare JD requirements against candidate skills.

Create a report at `reports/<company-slug>-<role-slug>.md` with:
- Company intelligence
- Rate/salary research with sources
- Recommended rate range (target, stretch, floor)
- Gap analysis table (requirement, strength, gap, severity)
- Gap mitigation strategies (narrative framing for each gap)
- Interview preparation (questions to ask, likely technical questions, negotiation tips)

## Step 5: CV Review

Read the generated `cv_text` from MongoDB. Provide:
- Specific improvement suggestions for this role
- Missing keywords or skills to add
- Summary positioning advice
- Salary/rate negotiation tips

## Output

Summarize what was done:
1. Job ID inserted
2. Pipeline status
3. Report location
4. Top 3 CV improvement tips
5. Recommended rate range
