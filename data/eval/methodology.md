# Eval Framework Methodology

**Analysis Date:** 2026-04-13  
**MongoDB Collection:** `jobs.level-2`  
**Query Date Range:** All available data (no date filter applied)  
**Schema Version:** 1.0  
**Source Plan:** `plans/cv-eval-foundation.md`

---

## Inclusion Rules

A job is eligible if ALL of the following are true:

1. Has `job_description` field that exists, is not null, and has length >= 100 characters
2. Has `score` field that exists and is not null
3. Matches at least one signal tier (A, B, C, or D — see below)

## Exclusion Rules

A job is excluded if ANY of the following are true:

1. `job_description` is missing, null, or < 100 characters → `excluded_missing_jd`
2. `score` is missing or null → `excluded_no_score`
3. Identified as duplicate (see Deduplication Rules) → `excluded_duplicate`
4. JD text is clearly not a real job posting (e.g., test data, garbled HTML) → `excluded_low_quality_jd`

All exclusions are logged with reason in `data/eval/exclusions.json`.

---

## Signal Tiers and Weights

| Tier | Description | Query Logic | Weight |
|------|-------------|-------------|--------|
| A | Applied + received response/callback/interview | `status: "applied"` AND (`response_received: true` OR `interview_invited: true` OR `callback: true`) | 1.00 |
| B | Applied + high score | `status: "applied"` AND `score >= 60` | 0.85 |
| C | AI job + good score + JD present | `is_ai_job: true` AND `score >= 50` AND `job_description` exists | 0.65 |
| D | Any scored AI job with JD | `is_ai_job: true` AND `score` exists AND `job_description` exists | 0.40 |

A job is assigned to the **highest tier it qualifies for** (A > B > C > D). Each job appears in exactly one tier.

### Recency Adjustment

If `createdAt` or `applied_at` is available:

- Within 12 months of analysis date: multiplier = 1.00
- 12-24 months: multiplier = 0.90
- Older than 24 months: multiplier = 0.80

`effective_weight = signal_weight * recency_multiplier`

---

## Evidence Tagging Scheme

Every extracted requirement or signal carries one tag:

| Tag | Meaning | Use in Counts |
|-----|---------|---------------|
| `explicit` | Directly stated in JD text | Yes — primary basis for frequency tables |
| `derived` | Tightly inferred from explicit JD wording | Narrative synthesis only, labeled as derived |
| `not_specified` | Not present in JD | Counted as absent |

---

## Counting Rules

- Frequency tables are based on `explicit` evidence only
- Report both **raw count** (`N / M`) and **raw %**
- Report **weighted %** when signal weights materially change the picture (>10pp difference)
- If weighted and raw frequencies disagree by >10 percentage points, flag and show both

---

## Frequency Bands

| Band | Weighted Frequency | Meaning |
|------|-------------------|---------|
| `must_have` | >= 60% | Consistently required across the category |
| `common` | 35-59% | Frequent but not universal |
| `differentiator` | 15-34% | Strategically important, separates strong roles |
| `rare` | < 15% | Infrequent but noted |

---

## Deduplication Rules

Before analysis, deduplicate using this priority chain:

1. Exact match on `dedupeKey` field (if present)
2. Normalized match on (lowercase title + lowercase company + normalized location)
3. JD text similarity > 0.90 (Jaccard on word-level 3-grams)

When duplicates are found, keep the record with:
- Highest signal tier (A > B > C > D)
- Then highest score
- Then most recent `createdAt`

Log all excluded duplicates with the kept record's `_id` and reason.

---

## Category Assignment Rules

Each job is assigned to **exactly one primary category** and zero or more secondary categories.

### Classification Signal Priority

1. `ai_categories` array (if populated and high quality)
2. `extracted_jd.role_category` + `extracted_jd.seniority_level` + JD content
3. Title regex pattern matching (per category table in plan)
4. JD body signals (leadership/architecture/IC indicators)
5. Normalized location matching

### Region Definitions

- **EEA:** EU27 + Iceland + Liechtenstein + Norway (UK and Switzerland are NOT EEA)
- **KSA:** Saudi Arabia, Riyadh, Jeddah, Dammam, Khobar, Dhahran, NEOM
- **UAE:** UAE, Dubai, Abu Dhabi, Sharjah, Al Ain
- **Pakistan:** Pakistan, Karachi, Lahore, Islamabad, Rawalpindi
- **Remote/Global:** Location contains "remote", "worldwide", "anywhere", "global", or is blank/null with remote indicators in title/JD

### Conflict Resolution

If a job matches multiple categories equally:
- Prefer the category matching the candidate's primary target (categories 1-4, 10-12, 15)
- Then prefer the more specific category (e.g., "AI Architect — EEA" over "AI Architect — Global")
- Record the non-primary as `secondary_categories`

---

## Confidence Thresholds

| Classification Confidence | Criteria |
|--------------------------|---------|
| `high` | Title clearly matches category + location confirmed + JD supports role type |
| `medium` | Title partially matches OR location ambiguous OR JD signals mixed |
| `low` | Assigned primarily by JD content with weak title/location signals |

### Category Confidence

| Jobs in Category | Category Confidence |
|-----------------|-------------------|
| >= 20 | High |
| 8-19 | Medium |
| 5-7 | Low |
| < 5 | Exploratory (provisional rubric only) |
