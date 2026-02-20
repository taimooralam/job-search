---
title: URL Resolver
description: Resolves direct application URLs (Greenhouse, Lever, Workday, etc.) for jobs missing them in the level-2 collection. Uses DuckDuckGo search + Claude Haiku extraction.
triggers:
  - resolve urls
  - find application urls
  - url resolver
  - fix missing urls
---

# URL Resolver Skill

Automated cycle: **query MongoDB → search → extract with Claude → update**.

## Tasks

### 1. Resolve URLs (every 30 min)
Finds jobs missing application URLs and resolves them via web search + AI extraction.

```bash
python3 /home/node/skills/url-resolver/scripts/resolver.py
```

**Test mode** (1 job, no DB write, prints output):
```bash
python3 /home/node/skills/url-resolver/scripts/resolver.py --test
```

**Dry run** (all jobs, no DB write):
```bash
python3 /home/node/skills/url-resolver/scripts/resolver.py --dry-run
```

### Setup (run once)
Create MongoDB indexes:
```bash
python3 /home/node/skills/url-resolver/scripts/setup_indexes.py
```

## Data Flow

```
level-2 (MongoDB) → jobs missing application_url
                         ↓
                   DuckDuckGo search (4 templates per job)
                         ↓
                   Claude Haiku extraction + validation
                         ↓
                   Update MongoDB (application_url + tracking fields)
                         ↓
                   Telegram summary notification
```

## MongoDB Fields Added

| Field | Type | Description |
|-------|------|-------------|
| `url_resolved_at` | datetime | When URL was resolved |
| `url_resolution_source` | string | Description of where URL was found |
| `url_resolution_confidence` | float | 0.0–1.0 confidence from Claude |
| `url_resolution_attempts` | int | Counter, capped at 3 |
| `url_resolution_last_error` | string | Last failure reason |

## Environment Variables

- `MONGODB_URI` — VPS MongoDB connection string
- `ANTHROPIC_API_KEY` — For Claude Haiku URL extraction
- `TELEGRAM_BOT_TOKEN` — Telegram Bot API token
- `TELEGRAM_CHAT_ID` — Telegram chat ID for notifications
