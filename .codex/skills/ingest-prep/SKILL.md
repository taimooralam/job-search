---
name: ingest-prep
description: Ingest a job into MongoDB (or resolve existing by _id), mark as favorite, trigger batch pipeline if needed, then do deep internet research and create an interview prep document in the ai-engg/reports folder.
argument-hint: <_id or job description or company + role context>
model: opus
---

# Job Ingestion & Interview Prep Pipeline

You are given either a MongoDB `_id`, a job description, or company/role context. Execute the full workflow below.

## Input

The user will provide: `$ARGUMENTS`

This may be:
- A MongoDB ObjectId (24-char hex string) — look up existing job
- A full job description — parse and inject
- Company name + role context (e.g. from recruiter message) — research and inject

## Step 1: Resolve Job in MongoDB

Connect to MongoDB using `MONGODB_URI` from `.env`. Collection: `jobs` database, `level-2` collection.

```python
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["jobs"]
col = db["level-2"]
```

### If `_id` provided (24-char hex):
```python
job = col.find_one({"_id": ObjectId("<id>")})
```
If found, proceed to Step 2. If not found, tell the user.

### If new job (no _id):
Parse the input to extract company, title, location, jobUrl, description. Then search the internet for the full job posting if only partial info is provided.

Insert using this schema:
```python
doc = {
    "company": "<company>",
    "title": "<title>",
    "location": "<location>",
    "jobUrl": "<url or company website>",
    "description": "<full JD text>",
    "dedupeKey": f"recruiter_direct|{normalize(company)}|{normalize(title)}|{normalize(location)}",
    "createdAt": datetime.utcnow(),
    "status": "under processing",
    "batch_added_at": datetime.utcnow(),
    "source": "recruiter_direct",
    "auto_discovered": False,
    "quick_score": 90,
    "quick_score_rationale": "Manually injected — interview scheduled",
    "tier": "A",
    "salary": None,
    "jobType": "permanent",
    "starred": True,
    "starredAt": datetime.utcnow(),
}
result = col.insert_one(doc)
job_id = str(result.inserted_id)
```

Print the inserted `_id`.

## Step 2: Mark as Favorite

If not already starred:
```python
col.update_one(
    {"_id": ObjectId(job_id), "starred": {"$ne": True}},
    {"$set": {"starred": True, "starredAt": datetime.utcnow()}}
)
```

## Step 3: Trigger Batch Pipeline (if CV not generated)

Check if CV already exists:
```python
job = col.find_one({"_id": ObjectId(job_id)}, {"cv_text": 1, "status": 1})
```

If `cv_text` is empty/None, trigger the pipeline:
```
POST https://runner.uqab.digital/api/jobs/{job_id}/operations/batch-pipeline/queue
Authorization: Bearer {RUNNER_API_SECRET from .env}
Content-Type: application/json
Body: {"tier": "quality"}
```

Do NOT block waiting for completion — proceed to research.

## Step 4: Deep Research & Interview Prep Report

### 4a. Internet Research

Use WebSearch to research:
1. **Company profile** — what they do, mission, size, funding, key people
2. **Tech stack** — engineering blog posts, job postings, StackShare, GitHub
3. **Engineering culture** — Glassdoor reviews, blog posts, interview experiences
4. **Salary benchmarks** — Levels.fyi, Glassdoor, Kununu (for DACH region), LinkedIn Salary
5. **Interview process** — Glassdoor interview reviews, Blind, Reddit
6. **Recent news** — funding, acquisitions, product launches

### 4b. Read Candidate Profile

Read master CV data from:
- `data/master-cv/roles/` — role-specific experience
- `data/master-cv/role_skills_taxonomy.json` — skills taxonomy

### 4c. Determine Report Number

List files in `../ai-engg/reports/` and find the next available number (currently 42+).

### 4d. Write Interview Prep Report

Write to `../ai-engg/reports/{NN}-{company-slug}-{role-slug}-interview-prep.md` using this template:

```markdown
# {Company} — {Role Title} Interview Prep

**Date:** {today's date}
**Job ID:** `{mongodb_id}`
**Location:** {location}
**Stage:** Interview
**Interview Date:** {if known}

---

## Company Profile

- **Company:** {name}
- **Product/Service:** {what they do}
- **Customers:** {key customers if known}
- **Team size:** {employees}
- **Funding:** {funding stage/amount}
- **Mission:** {mission statement}

### Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | {technologies} |
| Backend | {technologies} |
| Database | {technologies} |
| AI | {technologies} |
| Infra | {technologies} |

### Engineering Culture

- {key engineering principles from research}

---

## Why They Need This Role

{Analysis of what the role is really about, based on JD and research}

### Pain Points (Inferred)

- {pain point 1}
- {pain point 2}

---

## Signal to Give

### Primary Narrative: "{one-line positioning}"

| Their Need | Your Signal |
|------------|-------------|
| {requirement} | {matching experience from master CV} |

### Key Stories to Tell

1. **{Story title}** — "{STAR-format story}"

---

## Estimated Salary Range

| Source | Range |
|--------|-------|
| {source} | {range} |

### Your Ask

- **Base:** {recommended range}
- **Equity/Bonus:** {if applicable}
- **Benefits:** {notable benefits}

---

## Questions to Ask

### Product & Vision
1. "{question}"

### Architecture & Infrastructure
2. "{question}"

### Team & Process
3. "{question}"

### Business & Growth
4. "{question}"

---

## CV Gap Analysis

### Strengths in Generated CV
- {strength}

### Weaknesses to Address
- {weakness + bridge strategy}

### Verbal Corrections to Make
> "{suggested verbal correction}"

---

## Interview Debrief

**Date:** {to be filled after interview}
**Type:** {interview type}
**Stage:** {stage}

### Key Takeaways
- {to be filled}

### Compensation Discussion
- {to be filled}

### Next Steps
- {to be filled}
```

## Output

Summarize:
1. Job ID (existing or newly inserted)
2. Favorite status
3. Pipeline status (already complete / triggered)
4. Report file path
5. Top 3 preparation priorities for this interview
