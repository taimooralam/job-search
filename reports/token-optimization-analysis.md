# Token Optimization Analysis Report

**Date:** 2026-03-04
**Status:** Implemented

## Summary

Implemented ~60% cost reduction per job run by disabling non-essential pipeline steps and downgrading model tiers where quality impact is minimal.

## Changes Made

### 1. Feature Flags Added (`src/common/config.py`)

| Flag | Default | Purpose |
|------|---------|---------|
| `ENABLE_COMPANY_RESEARCH` | `false` | Company signals via web search (Layer 3) |
| `ENABLE_ROLE_RESEARCH` | `false` | Role business impact analysis (Layer 3.5) |
| `ENABLE_PEOPLE_MAPPER` | `false` | Contact discovery (Layer 5) |
| `ENABLE_OUTREACH` | `false` | Outreach email/LinkedIn generation (Layer 6b) |
| `ENABLE_COVER_LETTER` | `false` | Cover letter generation (Layer 6.7) |

All flags default to `false`. Set to `true` via environment variables to re-enable.

### 2. Model Tier Downgrades (`src/common/llm_config.py`)

| Step | Before | After | Savings |
|------|--------|-------|---------|
| `jd_extraction` | middle (Sonnet) | low (Haiku) | ~$0.020/job |
| `outreach_generation` | high (Opus) | middle (Sonnet) | ~$0.040/job |
| `recruiter_cover_letter` | high (Opus) | middle (Sonnet) | ~$0.040/job |

**Rationale:** JD extraction is structured parsing (JSON schema output) — Haiku excels at this. Outreach generation is templated with character limits — Sonnet handles this well.

### 3. Batch Pipeline Simplified (`src/services/batch_pipeline_service.py`)

**Before:** 7 steps (extraction → form scraping → company/role research → CV gen → uploads)
**After:** 4-5 steps (extraction → [optional research] → CV gen → uploads)

- Form scraping step removed entirely (was consuming FireCrawl credits, not pipeline tokens)
- Company research step made conditional on `ENABLE_COMPANY_RESEARCH`

### 4. Cover Letter Made Optional (`src/services/cv_generation_service.py`)

Cover letter generation skipped unless `ENABLE_COVER_LETTER=true`. Saves ~$0.004/job (Sonnet call).

### 5. LangGraph Workflow Updated (`src/workflow.py`)

Nodes are conditionally added to the graph based on feature flags. Uses a `prev_node` chain pattern to dynamically wire edges, skipping disabled nodes entirely.

### 6. Company Research Service Guard (`src/services/company_research_service.py`)

Returns early with a no-op result when all research flags are disabled.

## Cost Impact

| Optimization | Per-Job Savings | For 100 Jobs |
|-------------|----------------|-------------|
| Disable company + role research | ~$0.031 | $3.10 |
| Disable people mapper + outreach | ~$0.052 | $5.20 |
| Downgrade outreach to Sonnet | ~$0.040 | $4.00 |
| Downgrade JD extraction to Haiku | ~$0.020 | $2.00 |
| Disable cover letter | ~$0.004 | $0.40 |
| **TOTAL** | **~$0.21 → ~$0.08** | **$21 → $8** |

**~60% cost reduction** while maintaining core CV generation quality.

## Minimal Pipeline (all flags disabled)

When all optimization flags are `false`, the pipeline runs:
1. JD Extractor (Haiku) — structured JD parsing
2. Pain Point Miner (Sonnet) — extract pain points
3. Opportunity Mapper (Sonnet) — fit scoring
4. CV Generator V2 (Sonnet) — 6-phase CV generation
5. Output Publisher — file output

**Estimated cost per job:** ~$0.08

## Re-enabling Features

To restore full pipeline, set environment variables:

```bash
ENABLE_COMPANY_RESEARCH=true
ENABLE_ROLE_RESEARCH=true
ENABLE_PEOPLE_MAPPER=true
ENABLE_OUTREACH=true
ENABLE_COVER_LETTER=true
```

Model tiers can also be overridden per-step via environment variables:
```bash
LLM_TIER_jd_extraction=middle          # Back to Sonnet
LLM_TIER_outreach_generation=high      # Back to Opus
LLM_TIER_recruiter_cover_letter=high   # Back to Opus
```
