# MongoDB level-2 Collection Schema

**Database:** `jobs`
**Collection:** `level-2`
**Connection:** `MONGODB_URI` from `.env` (VPS at 72.61.92.76:27018)
**Total docs:** ~8,774 (as of 2026-02-26)
**Date range:** 2025-11-25 → 2026-02-26

## Date Handling

- `createdAt` is stored as **ISO string** in 99.7% of docs (8,748/8,774)
- Only 26 docs have `createdAt` as native BSON datetime
- **Use `_id` ObjectId generation time** as reliable date proxy: `doc["_id"].generation_time`

## Core Fields

| Field | Type | Present In | Description |
|-------|------|-----------|-------------|
| `_id` | ObjectId | 100% | MongoDB primary key; encodes creation timestamp |
| `title` | string | 100% | Job title |
| `company` | string | 100% | Company name (UPPERCASE in LinkedIn-sourced) |
| `Company Name` | string | some | Legacy field, sometimes None |
| `location` | string | 100% | Job location (may be empty string) |
| `job_description` | string | 99.7% (8,750) | Full job description text — **primary text field** |
| `description` | string | 0.3% (24) | Legacy field from non-LinkedIn sources |
| `createdAt` | string (ISO) | 100% | Creation timestamp as ISO string |
| `source` | string | 100% | "linkedin", "himalayas_auto", "manual", etc. |
| `score` | int | varies | Fit score 0-100 (from quick_score or pipeline) |
| `quick_score` | int | varies | LLM quick scoring result |
| `quick_score_rationale` | string | varies | Reasoning for score |
| `tier` | string | varies | "A" (85+), "B" (70-84), "C" (50-69), "D" (<50) |
| `status` | string | varies | "not processed", "processing", "completed", "failed" |
| `dedupeKey` | string | 100% | Deduplication key |
| `jobId` | string | most | Source platform job ID |
| `jobURL` | string | most | Full job posting URL |
| `jobScrapingUrl` | string | some | LinkedIn API URL used for scraping |
| `url` | string | some | Alternate URL field |
| `postedAt` | string | some | Relative posting time ("22 hours ago") |
| `firm` | string | some | Company name variant |
| `job_criteria` | string | most | LinkedIn sidebar metadata (seniority, type, function, industry) |
| `auto_discovered` | boolean | some | Whether auto-discovered vs manual |
| `embeddings_large` | array | some | Large embedding vector |
| `embeddings_small` | array | some | Small embedding vector |

## Extracted JD Fields (11.5% coverage — 1,005 docs)

Present when pipeline Layer 1.4 has processed the job. Stored under `extracted_jd` subdocument.

| Field | Type | Description |
|-------|------|-------------|
| `extracted_jd.title` | string | Cleaned title |
| `extracted_jd.company` | string | Cleaned company |
| `extracted_jd.location` | string | Cleaned location |
| `extracted_jd.remote_policy` | string | Remote/hybrid/onsite |
| `extracted_jd.role_category` | string | "senior_engineer", "engineering_manager", "staff_principal_engineer", "head_of_engineering", "cto", etc. |
| `extracted_jd.seniority_level` | string | "senior", "staff", "principal", "director", "vp", "c_level" |
| `extracted_jd.competency_weights` | object | `{delivery, process, architecture, leadership}` each 0-100 |
| `extracted_jd.responsibilities` | array[string] | 5-10 key responsibilities |
| `extracted_jd.qualifications` | array[string] | Required qualifications |
| `extracted_jd.nice_to_haves` | array[string] | Preferred qualifications |
| `extracted_jd.technical_skills` | array[string] | Extracted technical skills |
| `extracted_jd.soft_skills` | array[string] | Extracted soft skills |
| `extracted_jd.implied_pain_points` | array[string] | Problems this hire solves |
| `extracted_jd.success_metrics` | array[string] | How success is measured |
| `extracted_jd.top_keywords` | array[string] | 15 most important ATS keywords |
| `extracted_jd.industry_background` | string | Industry classification |
| `extracted_jd.years_experience_required` | string | Experience requirement |
| `extracted_jd.education_requirements` | string | Education requirement |

## Related Collections

| Collection | Purpose |
|------------|---------|
| `results` | Pipeline output (CV text, outreach, layer results) |
| `annotation_priors` | Cached annotations for CV tailoring |
| `company_cache` | Cached company research |
| `system_state` | Pipeline state, ingest timestamps |

## Useful Query Patterns

```python
# All jobs from a month
{"_id": {"$gte": ObjectId.from_datetime(start), "$lt": ObjectId.from_datetime(end)}}

# Jobs with extracted skills
{"extracted_jd.technical_skills": {"$exists": True}}

# Search job descriptions for keywords (regex)
{"job_description": {"$regex": "LLM|LangGraph|agentic", "$options": "i"}}

# High-scoring jobs
{"score": {"$gte": 85}}

# By source
{"source": "linkedin"}
```

## Source Distribution

| Source | Count | AI % |
|--------|-------|------|
| linkedin | 8,748 | 33.5% |
| linkedin_import | 16 | 31.2% |
| himalayas_auto | 3 | 0% |
| manual | 3 | 33.3% |
| recruiter_direct | 1 | 100% |
