---
name: scout-jobs
description: Search LinkedIn for AI/engineering roles, score them, and inject approved jobs into the pipeline. Replaces the n8n scraping workflow.
argument-hint: --time day --region remote --profile ai --pages 2
model: sonnet
---

# LinkedIn AI Job Scout

Search LinkedIn for AI/GenAI/LLM/engineering roles, score with rule-based scorer, present results, and inject approved jobs into MongoDB + batch pipeline.

## Input

Parse `$ARGUMENTS` for flags (all optional with defaults):
- `--time` (hour|day|3days|week|month|2months) — default: hour
- `--region` (comma-separated: remote,us,mena,emea,pakistan,asia_pacific) — default: remote
- `--pages` (int) — max pages per query, default: 2
- `--min-score` (int) — filter threshold, default: 0
- `--limit` (int) — max total jobs, 0=unlimited, default: 0
- `--few-applicants` — only jobs with <10 applicants
- `--profile` (comma-separated: ai,engineering,leadership,architect) — default: ai

## Step 1: Run the Scout Script

```bash
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate && PYTHONPATH=/Users/ala0001t/pers/projects/job-search python scripts/scout_linkedin_jobs.py $ARGUMENTS 2>scout_stderr.log
```

Capture stdout (JSON) and stderr (logs). If the script fails, show the error from `scout_stderr.log`.

The script outputs:
- **stdout**: Slim JSON (no descriptions — saves ~90% tokens)
- **/tmp/scout_jobs_descriptions.json**: Full descriptions keyed by job_id (for MongoDB insertion)

Parse the JSON output which has structure:
```json
{
  "jobs": [...],
  "summary": { "found": N, "scored": N, "filtered": N }
}
```

## Step 2: Present Results Table

Display a formatted table sorted by score (descending):

```
# | Score | Tier | Title | Company | Location | Role
--|-------|------|-------|---------|----------|-----
1 |    82 |   A  | Senior AI Engineer | Acme Corp | Remote | ai_engineer
2 |    71 |   A  | GenAI Architect    | TechCo    | US     | ai_architect
...
```

Include summary line: `Found X → Scored Y → Z passed filter (min-score: N)`

If no jobs found, report that and stop.

## Step 3: Ask User for Approval

Ask which jobs to approve for pipeline processing:
- **all** — insert all filtered jobs
- **tier-a** — only Tier A (score >= 70)
- **specific numbers** — e.g., "1,3,5" or "1-5"
- **none** — skip insertion

## Step 4: Insert Approved Jobs into MongoDB

For each approved job, insert into MongoDB `level-2` collection:

```python
import json
import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("/Users/ala0001t/pers/projects/job-search/.env")

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["jobs"]
col = db["level-2"]

from src.common.dedupe import generate_dedupe_key

# Load descriptions from sidecar file (not in JSON stdout to save tokens)
with open("/tmp/scout_jobs_descriptions.json") as f:
    descriptions = json.load(f)

for job in approved_jobs:
    dedupe_key = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])

    # Cross-source dedupe: check both linkedin_scout and linkedin_import keys
    alt_key = generate_dedupe_key("linkedin_import", source_id=job["job_id"])
    existing = col.find_one({"dedupeKey": {"$in": [dedupe_key, alt_key]}})
    if existing:
        print(f"DUPLICATE: {job['title']} @ {job['company']} — already exists as {existing['_id']}")
        continue

    doc = {
        "company": job["company"],
        "title": job["title"],
        "location": job["location"],
        "jobUrl": job["job_url"],
        "description": descriptions.get(job["job_id"], ""),
        "dedupeKey": dedupe_key,
        "createdAt": datetime.utcnow(),
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "source": "linkedin_scout",
        "auto_discovered": True,
        "quick_score": job["score"],
        "quick_score_rationale": f"Rule scorer: {job['tier']} tier, role={job['detected_role']}, seniority={job['seniority_level']}",
        "tier": job["tier"],
        "starred": job["tier"] == "A",
        "starredAt": datetime.utcnow() if job["tier"] == "A" else None,
        "score": None,
        "salary": None,
        "jobType": job.get("employment_type"),
        "linkedin_metadata": {
            "linkedin_job_id": job["job_id"],
            "seniority_level": job.get("seniority"),
            "employment_type": job.get("employment_type"),
            "job_function": job.get("job_function"),
            "industries": job.get("industries"),
            "rule_score_breakdown": job.get("breakdown"),
        },
    }

    result = col.insert_one(doc)
    print(f"INSERTED: {job['title']} @ {job['company']} → {result.inserted_id}")
```

## Step 5: Trigger Batch Pipeline

The runner, Redis, and MongoDB all live on the VPS (`ssh root@72.61.92.76`). The runner containers are behind Traefik and not exposed to localhost — you must either SSH into the VPS or use the public `https://runner.uqab.digital` URL.

Queue all inserted jobs via SSH (most reliable):

```bash
ssh root@72.61.92.76 << SSHEOF
API_SECRET="701894c6bb27f56cfe9a0ed13e9f216790cbf8e067114ef1045813d7cfdd55fd"
RUNNER="https://runner.uqab.digital"

JOBS=( <space-separated list of inserted ObjectId strings> )

queued=0; failed=0
for jid in "\${JOBS[@]}"; do
  code=\$(curl -s -o /dev/null -w '%{http_code}' -k \\
    -X POST "\$RUNNER/api/jobs/\$jid/operations/batch-pipeline/queue" \\
    -H "Authorization: Bearer \$API_SECRET" \\
    -H "Content-Type: application/json" \\
    -d '{"tier":"quality"}' -m 10)
  if [ "\$code" = "200" ] || [ "\$code" = "201" ] || [ "\$code" = "202" ]; then
    queued=\$((queued + 1))
  else
    echo "FAILED \$jid: \$code"
    failed=\$((failed + 1))
  fi
done
echo "Queued: \$queued / Failed: \$failed / Total: \${#JOBS[@]}"
SSHEOF
```

Build the JOBS array from the list of `inserted_id` values collected in Step 4.

## Step 6: Report Summary

Print a final summary:

```
Scout Summary
─────────────
Found:      X jobs from LinkedIn search
Scored:     Y jobs with descriptions
Filtered:   Z jobs above min-score
Approved:   N jobs selected by user
Inserted:   M jobs into MongoDB level-2
Duplicates: D jobs already existed
Queued:     Q jobs for batch pipeline
```
