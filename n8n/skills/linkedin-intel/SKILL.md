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

## Data Flow

```
LinkedIn API → linkedin_intel (MongoDB)
                    ↓
              classifier.py → classification added to docs
                    ↓
           draft_generator.py → draft_content (MongoDB)
                    ↓
          telegram_briefing.py → Telegram message
```

## Environment Variables

- `MONGODB_URI` — MongoDB connection string
- `TELEGRAM_BOT_TOKEN` — Telegram Bot API token
- `TELEGRAM_CHAT_ID` — Telegram chat ID for briefings
- `ANTHROPIC_API_KEY` — For Claude Haiku classification/drafts

## Cookie Maintenance

LinkedIn cookies must be refreshed periodically. Upload new cookies to:
```
/root/n8n-prod/cookies/linkedin-cookies.txt
```
Format: Netscape cookie export (use a browser extension like "Get cookies.txt LOCALLY").
