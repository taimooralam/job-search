---
title: LinkedIn Intelligence
description: Automated LinkedIn monitoring for job opportunities, thought leadership content, and networking signals. Scrapes, classifies, and delivers daily briefings.
triggers:
  - linkedin intel
  - linkedin scrape
  - linkedin briefing
  - morning intelligence
  - check linkedin
---

# LinkedIn Intelligence Skill

Automated daily cycle: **scrape → classify → draft → brief**.

## Tasks

### 1. Morning Scrape (3 AM Mon-Sat)
Searches LinkedIn for jobs and posts based on a rotating keyword schedule.

```bash
python3 /home/node/skills/linkedin-intel/scripts/linkedin_search.py
```

**Test mode** (1 keyword, 5 results):
```bash
python3 /home/node/skills/linkedin-intel/scripts/linkedin_search.py --test
```

### 2. Evening Analysis (8 PM Mon-Sat)
Classifies new items with Claude Haiku and generates engagement drafts.

```bash
python3 /home/node/skills/linkedin-intel/scripts/classifier.py
python3 /home/node/skills/linkedin-intel/scripts/draft_generator.py
```

**Test mode**:
```bash
python3 /home/node/skills/linkedin-intel/scripts/classifier.py --test
python3 /home/node/skills/linkedin-intel/scripts/draft_generator.py --test
```

### 3. Morning Briefing (7 AM daily)
Sends a Telegram summary of last 24h intelligence.

```bash
python3 /home/node/skills/linkedin-intel/scripts/telegram_briefing.py
```

**Test mode** (print to stdout):
```bash
python3 /home/node/skills/linkedin-intel/scripts/telegram_briefing.py --test
```

### Setup (run once)
Create MongoDB indexes:
```bash
python3 /home/node/skills/linkedin-intel/scripts/setup_indexes.py
```

## Safety Rules

- **Sunday rest day** — no scraping
- **Warmup period** (first 14 days): max 30 calls/day
- **Normal limits**: max 50 calls/session, 150 calls/day
- **Random delays**: 5-15 seconds between calls (with gaussian jitter)
- **Session max**: 30 minutes
- **Cooldowns**: HTTP 429 → 24h pause, HTTP 403 → 7-day pause
- **Alerts**: Telegram notification on any cooldown trigger

### 4. Edge Detection (8 PM Mon-Sat, after classifier)
Applies heuristic rules to detect niche opportunities (TOGAF+AI crossover, funded companies, governance vacuums, etc.).

```bash
python3 /home/node/skills/linkedin-intel/scripts/edge_detector.py
```

**Test mode** (1 item):
```bash
python3 /home/node/skills/linkedin-intel/scripts/edge_detector.py --test
```

### 5. Pipeline Bridge
Push a LinkedIn intel item to the job pipeline (Atlas MongoDB → runner).

```bash
python3 /home/node/skills/linkedin-intel/scripts/pipeline_bridge.py --test <item_id>
python3 /home/node/skills/linkedin-intel/scripts/pipeline_bridge.py --push <item_id>
```

## Telegram Commands

Interactive commands via OpenClaw subprocess. Each returns text to Telegram.

```bash
python3 /home/node/skills/linkedin-intel/scripts/telegram_commands.py <command> [arg]
```

| Command | Description |
|---------|-------------|
| `/apply <n>` | Push job #n to pipeline |
| `/draft <n>` | Show/generate draft for item #n |
| `/save <n>` | Bookmark item #n |
| `/detail <n>` | Full content of item #n |
| `/skip <n>` | Mark as skipped |
| `/lead <n>` | Move to lead pipeline |
| `/stats` | Today's intelligence stats |
| `/search "kw"` | Search intel items by keyword |
| `/pause` | Pause scraping for 24h |
| `/resume` | Resume scraping (clear cooldowns) |
| `/trends` | This week's trending keywords |
| `/next` | Next 3 unread high-relevance items |

Numbers reference the daily briefing index (e.g., `[1]` in the morning message).

## Data Flow

```
LinkedIn API → linkedin_intel (MongoDB)
                    ↓
              classifier.py → classification added to docs
                    ↓
            edge_detector.py → edge_opportunities + score boost
                    ↓
           draft_generator.py → draft_content (MongoDB)
                    ↓
          telegram_briefing.py → Telegram message (with indexes)
                    ↓
         telegram_commands.py → Interactive actions via Telegram
                    ↓
          pipeline_bridge.py → Atlas MongoDB level-2 → Runner
```

## Environment Variables

- `MONGODB_URI` — VPS MongoDB connection string
- `ATLAS_MONGODB_URI` — Atlas MongoDB for job pipeline
- `TELEGRAM_BOT_TOKEN` — Telegram Bot API token
- `TELEGRAM_CHAT_ID` — Telegram chat ID for briefings
- `ANTHROPIC_API_KEY` — For Claude Haiku classification/drafts
- `RUNNER_URL` — Runner API URL for pipeline triggers
- `RUNNER_API_SECRET` — Runner API authentication

## Cookie Maintenance

LinkedIn cookies must be refreshed periodically. Upload new cookies to:
```
/root/n8n-prod/cookies/linkedin-cookies.txt
```
Format: Netscape cookie export (use a browser extension like "Get cookies.txt LOCALLY").
