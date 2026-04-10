---
title: Scout Jobs
description: LinkedIn job scouting pipeline — proxy refresh, search, scrape, score, select, and insert into MongoDB with pipeline triggering.
triggers:
  - scout jobs
  - find jobs
  - search linkedin
  - proxy refresh
  - run scout
---

# Scout Jobs

Automated LinkedIn job discovery pipeline with proxy rotation, rule-based scoring, and MongoDB insertion.

## Phases

### Phase 1: Proxy Refresh (every 20 min)
Fetches free proxies from 6 GitHub sources, validates against LinkedIn HTTPS, saves working pool.

```bash
python3 scripts/scout_proxy_refresh_cron.py
```

### Phase 2: LinkedIn Search (every 3h)
Searches LinkedIn guest API across multiple role/location combinations, deduplicates against MongoDB, enqueues new jobs.

```bash
python3 scripts/scout_linkedin_cron.py
python3 scripts/scout_linkedin_cron.py --test  # reduced dataset, no DB writes
```

### Phase 3: Scraper (every 5 min)
Dequeues jobs, fetches full details via proxy, scores with rule engine, appends to scored pool.

```bash
python3 scripts/scout_scraper_cron.py
```

### Phase 4: Selector (every 3h)
Reads scored pool, applies quotas and dedup, inserts top jobs into MongoDB level-2, triggers batch pipeline.

```bash
python3 scripts/scout_selector_cron.py --hourly-quota 1 --ai-quota 0
```

### Phase 5: Dimensional Selectors (profile-based, every 6-12h)
Re-ranks scored pool by location/seniority profiles, inserts additional jobs.

```bash
python3 scripts/scout_dimensional_selector.py --profile uae_ksa_leadership
python3 scripts/scout_dimensional_selector.py --profile global_remote
python3 scripts/scout_dimensional_selector.py --profile eea_remote
python3 scripts/scout_dimensional_selector.py --profile eea_staff_architect
```

## Data Files

All runtime data in `$SCOUT_QUEUE_DIR` (default: `/home/node/.openclaw/data/scout/`):
- `queue.jsonl` — jobs awaiting scraping
- `scored.jsonl` — scraped and scored jobs
- `scored_pool.jsonl` — persistent pool for dimensional selectors (48h TTL)
- `discarded.jsonl` — scored but not selected
- `queue_dead.jsonl` — permanently failed scrape attempts
- `proxies.json` — validated working proxies
- `proxies_blocklist.json` — failed proxies (30 min TTL)

## Config Files

- `data/blacklist.yaml` — company/title/keyword blacklist
- `data/selector_profiles.yaml` — dimensional selector profiles with quotas and boosts

## Environment Variables

- `MONGODB_URI` — MongoDB connection string
- `RUNNER_URL` — Pipeline runner API base URL
- `RUNNER_API_SECRET` — Bearer token for runner API
- `TELEGRAM_BOT_TOKEN` — Telegram notifications
- `TELEGRAM_CHAT_ID` — Telegram target chat
- `SCOUT_QUEUE_DIR` — Override data directory (default: skill-relative)

## MongoDB Collections

- **Reads**: `level-1`, `level-2` (deduplication)
- **Writes**: `level-2` (job insertion with `status: "under processing"`)

## Pipeline Trigger

Selectors POST to `{RUNNER_URL}/api/jobs/{job_id}/operations/batch-pipeline/queue` with Bearer auth.
