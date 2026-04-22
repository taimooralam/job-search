# Claude Code Prompt: Implement LinkedIn Intelligence System on OpenClaw

## Context

You are implementing a LinkedIn Intelligence & Brand Building system on a VPS running OpenClaw + n8n. The full architecture and design is documented in:
**`/Users/ala0001t/pers/projects/job-search/plans/linkedin-intelligence-system.md`**

Read that plan file first — it contains all schemas, cron schedules, safety rules, keyword lists, and model routing decisions. This prompt tells you HOW to implement it.

## Infrastructure

- **VPS:** `ssh root@72.61.92.76`
- **Docker compose:** `/root/n8n-prod/docker-compose.yml`
- **Local mirror:** `/Users/ala0001t/pers/projects/job-search/n8n/docker-compose.yml`
- **OpenClaw container:** `openclaw` (image: `alpine/openclaw:latest`)
- **OpenClaw domain:** `claw.srv1112039.hstgr.cloud`
- **OpenClaw data volume:** `openclaw_data` → `/home/node/.openclaw`
- **Existing skills example:** `/root/n8n-prod/skills/yt-dlp` (mounted read-only into container)
- **Existing cookies example:** `/root/n8n-prod/yt-cookies.txt` (mounted read-only)
- **MongoDB:** Atlas (connection string in job-search `.env` file)
- **Existing job-search app:** `/Users/ala0001t/pers/projects/job-search/`
- **Existing LinkedIn scraper (public API, reference only):** `src/services/linkedin_scraper.py`

## Target Profile (for relevance scoring)

**Name:** Taimoor Alam
**Roles sought:** AI Architect, Head of AI, AI Strategy Lead, Enterprise AI Consultant, Fractional CTO (AI)
**Skills:** TOGAF, Agentic AI, RAG, LangGraph, CrewAI, MCP, LLM orchestration, multi-agent systems, AI governance, Python, FastAPI, MongoDB, n8n
**Learning:** Enterprise AI Architect certification — 15 courses, 1,638 concepts
**Brand:** Thought leader at intersection of Enterprise Architecture + AI
**TOGAF checklist:** `/Users/ala0001t/pers/projects/certifications/togaf/study-plan/02-knowledge-checklist.md`
**AI Architect checklist:** `/Users/ala0001t/pers/projects/certifications/agentic-ai/study-plan/01-ai-architect-knowledge-checklist.md`

---

## PHASE 0 — LinkedIn Cookie Auth

### Step 1: Create cookies directory on VPS

```bash
ssh root@72.61.92.76 "mkdir -p /root/n8n-prod/cookies"
```

### Step 2: User extracts cookies locally

The user will extract LinkedIn cookies from their browser using "Get cookies.txt LOCALLY" Chrome extension and save to a local file. Then upload:

```bash
scp /path/to/linkedin-cookies.txt root@72.61.92.76:/root/n8n-prod/cookies/linkedin-cookies.txt
```

### Step 3: Mount cookies into OpenClaw container

Edit `/root/n8n-prod/docker-compose.yml` — under the `openclaw` service `volumes` section, add:

```yaml
- /root/n8n-prod/cookies/linkedin-cookies.txt:/home/node/linkedin-cookies.txt:ro
```

This goes right after the existing yt-cookies mount line.

### Step 4: Restart OpenClaw

```bash
ssh root@72.61.92.76 "cd /root/n8n-prod && docker compose up -d openclaw"
```

### Step 5: Verify

```bash
ssh root@72.61.92.76 "docker exec openclaw cat /home/node/linkedin-cookies.txt | head -5"
```

---

## PHASE 1 — OpenClaw LinkedIn Intelligence Skill

### Skill Directory Structure

Create on VPS at `/root/n8n-prod/skills/linkedin-intel/`:

```
linkedin-intel/
├── SKILL.md
├── scripts/
│   ├── linkedin_search.py       # Main scraper: jobs + posts via Voyager API
│   ├── linkedin_cookies.py      # Cookie loader + session manager
│   ├── classifier.py            # Classify + score items (calls Ollama local)
│   ├── draft_generator.py       # Generate comment/post drafts (calls Claude API)
│   ├── mongo_store.py           # MongoDB CRUD for linkedin_intel collections
│   ├── telegram_briefing.py     # Compile + send morning briefing
│   ├── safety_manager.py        # Rate limiting, escalation, session tracking
│   └── utils.py                 # Deduplication, hashing, helpers
├── config/
│   ├── safety-config.json       # Rate limits (see plan doc)
│   ├── target-keywords.json     # All keyword categories (see plan doc)
│   ├── rotation-schedule.json   # Day-of-week → category mapping
│   └── brand-voice.md           # Tone/style guide for draft content
└── requirements.txt             # Python deps: pymongo, requests, etc.
```

### Mount skill into OpenClaw container

Edit docker-compose.yml under `openclaw.volumes`:

```yaml
- /root/n8n-prod/skills/linkedin-intel:/home/node/skills/linkedin-intel:ro
```

### SKILL.md Content

Write the OpenClaw skill definition. Key points:
- `name: linkedin-intel`
- `requires: bins: ["python3", "curl"]`
- Three triggers: `morning-scrape` (cron `0 3 * * 1-6`), `evening-analysis` (cron `0 20 * * 1-6`), `morning-briefing` (cron `0 7 * * *`)
- Full instructions referencing the plan document's safety rules, keyword rotation, and MongoDB schema

### linkedin_search.py — Core Scraper

This is the main script. It must:

1. **Load cookies** from `/home/node/linkedin-cookies.txt` — parse Netscape format, extract `li_at` and `JSESSIONID`
2. **Read config** from `config/target-keywords.json` and `config/rotation-schedule.json`
3. **Determine today's categories** based on day of week
4. **Pick 2-3 keyword groups** from today's rotation (never all at once)
5. **For each keyword:**
   a. Call LinkedIn's Voyager API (the internal API that `linkedin-api` Python library uses):
      - Jobs endpoint: `https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards?decorationId=...&keywords={query}&start={offset}&count=25`
      - Posts/feed search: `https://www.linkedin.com/voyager/api/search/dash/clusters?q=all&keywords={query}&origin=GLOBAL_SEARCH_HEADER`
   b. Use headers:
      ```python
      headers = {
          "csrf-token": jsessionid_value,  # from JSESSIONID cookie, strip quotes
          "cookie": f"li_at={li_at}; JSESSIONID={jsessionid}; bcookie={bcookie}",
          "user-agent": random.choice(USER_AGENTS),
          "accept": "application/vnd.linkedin.normalized+json+2.1",
          "x-li-lang": "en_US",
          "x-restli-protocol-version": "2.0.0",
      }
      ```
   c. **Wait** `random.uniform(5, 15)` seconds between EACH request
   d. Extract from response: title, company, author, content preview, URL, engagement metrics
   e. Generate `dedupe_hash = hashlib.sha256(f"{source}|{url}|{title}".encode()).hexdigest()`
   f. Store to MongoDB via `mongo_store.py`
6. **Log session** to `linkedin_sessions` collection
7. **Handle errors:**
   - 429 → stop immediately, log, send Telegram alert, set cooldown flag
   - 401 → cookie expired, send Telegram alert
   - 403 → CRITICAL, full stop, alert

**IMPORTANT:** Use the `linkedin-api` Python library approach as reference but implement directly with `requests` for more control over rate limiting. The library (by Tom Quirk, `pip install linkedin-api`) shows the correct Voyager API endpoints and auth headers.

Alternatively, if implementing from scratch is too complex, use the `linkedin-api` library directly:

```python
from linkedin_api import Linkedin
api = Linkedin(cookies={"li_at": li_at_value, "JSESSIONID": jsessionid_value})
jobs = api.search_jobs(keywords="AI Architect", limit=25)
posts = api.search(params={"keywords": "enterprise AI challenges"}, limit=25)
```

The library handles auth from cookies. The safety wrapper (safety_manager.py) handles rate limiting on top.

### classifier.py — Local LLM Classification

Calls Ollama running on the VPS (install Ollama in Phase 9, until then use Claude Haiku as fallback):

```python
def classify_item(item: dict) -> dict:
    """Classify a scraped item using local Qwen model or Claude Haiku fallback."""
    prompt = f"""Classify this LinkedIn content.

Title: {item['title']}
Content: {item['content_preview'][:500]}
Author: {item.get('author', {}).get('headline', 'unknown')}

Tasks:
1. Type: job|freelance|post|pain_point|opportunity
2. Category: target_job|freelance|thought_leadership|pain_point|niche|learning_related
3. Relevance score 1-10 for an AI Architect seeking senior/director roles
4. Tags (pick applicable): high-value, respond-worthy, trending, niche-opportunity, apply-now
5. Brief reasoning (1 sentence)

Respond in JSON only."""

    # Try local Ollama first
    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "qwen2.5:7b-instruct-q4_K_M",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=30)
        return parse_json(response.json()["response"])
    except:
        # Fallback to Claude Haiku
        return classify_with_haiku(prompt)
```

### draft_generator.py — Content Drafts

For items tagged `respond-worthy` (score >= 7):

```python
def generate_comment_draft(item: dict) -> str:
    """Generate a thoughtful comment draft using Claude Haiku."""
    # Use Claude Haiku for short comments (cost: ~$0.001 per comment)
    # Use Claude Sonnet for original posts (cost: ~$0.01 per post)
    # Brand voice: thoughtful, experienced, practical, not salesy
    # Always include insight or question, never just agreement
    # Max 150 words for comments, 300 words for posts
```

### mongo_store.py — MongoDB Layer

```python
from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGODB_URI")  # Pass via docker-compose env
DB_NAME = "job_search"

def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def store_intel_item(item: dict) -> bool:
    """Store item, return False if duplicate."""
    db = get_db()
    try:
        db.linkedin_intel.insert_one(item)
        return True
    except DuplicateKeyError:
        # Update last_seen_at for existing item
        db.linkedin_intel.update_one(
            {"dedupe_hash": item["dedupe_hash"]},
            {"$set": {"last_seen_at": datetime.utcnow()}}
        )
        return False

def log_session(session: dict):
    db = get_db()
    db.linkedin_sessions.insert_one(session)

def get_briefing_data(since: datetime) -> dict:
    db = get_db()
    # Aggregate stats, top jobs, engagement opportunities
    ...
```

### safety_manager.py — Rate Limiting

```python
import json
import time
import random

class SafetyManager:
    def __init__(self, config_path="config/safety-config.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        self.calls_this_session = 0
        self.calls_today = self._get_today_calls_from_mongo()

    def can_make_call(self) -> bool:
        if self.calls_this_session >= self.config["max_calls_per_session"]:
            return False
        if self.calls_today >= self.config["max_calls_per_day"]:
            return False
        if self._is_in_cooldown():
            return False
        return True

    def wait_between_calls(self):
        delay = random.uniform(
            self.config["min_delay_seconds"],
            self.config["max_delay_seconds"]
        ) + random.gauss(0, 2)
        time.sleep(max(3, delay))  # Never less than 3s

    def record_call(self):
        self.calls_this_session += 1
        self.calls_today += 1

    def handle_error(self, status_code: int):
        if status_code == 429:
            self._set_cooldown(self.config["cooldown_on_429_hours"])
            self._alert_telegram("⚠️ LinkedIn rate limit hit! Cooling down 24h.")
            raise RateLimitError()
        elif status_code == 401:
            self._alert_telegram("🔑 LinkedIn cookies expired! Re-login needed.")
            raise AuthError()
        elif status_code == 403:
            self._set_cooldown(self.config["cooldown_on_403_hours"])
            self._alert_telegram("🚨 CRITICAL: LinkedIn 403. All scraping stopped.")
            raise BlockedError()
```

### telegram_briefing.py

Queries MongoDB at 7 AM and formats the briefing message (see format in plan doc), then sends via OpenClaw's built-in Telegram integration. If OpenClaw's Telegram isn't easily callable from a script, use the Telegram Bot API directly:

```python
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_briefing(message: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    )
```

### requirements.txt

```
requests>=2.31
pymongo>=4.6
python-dateutil>=2.8
linkedin-api>=2.2.0
```

---

## PHASE 2 — Cron Schedules in OpenClaw

OpenClaw cron is configured through its Telegram/messaging interface or via skill triggers in SKILL.md.

To set up via Telegram to OpenClaw:
```
Schedule "Run linkedin morning scrape" every day at 3am except Sunday
Schedule "Run linkedin evening analysis" every day at 8pm except Sunday
Schedule "Send linkedin morning briefing" every day at 7am
Schedule "Run linkedin weekend deep dive" every Saturday at 10am
Schedule "Check linkedin cookie health" on the 1st of every other month at noon
```

Or via SKILL.md triggers (already defined in Phase 1 SKILL.md).

---

## PHASE 3 — MongoDB Setup

### Create indexes

Run against MongoDB Atlas (use mongosh or the existing database.py pattern):

```javascript
// Connect to job_search database
use job_search

// linkedin_intel indexes
db.linkedin_intel.createIndex({ "dedupe_hash": 1 }, { unique: true })
db.linkedin_intel.createIndex({ "scraped_at": -1 })
db.linkedin_intel.createIndex({ "relevance_score": -1, "scraped_at": -1 })
db.linkedin_intel.createIndex({ "type": 1, "category": 1, "scraped_at": -1 })
db.linkedin_intel.createIndex({ "acted_on": 1, "relevance_score": -1 })
db.linkedin_intel.createIndex({ "classification.tags": 1 })
db.linkedin_intel.createIndex({ "source": 1, "scraped_at": -1 })
db.linkedin_intel.createIndex({ "title": "text", "content_preview": "text", "full_content": "text" })
db.linkedin_intel.createIndex({ "scraped_at": 1 }, { expireAfterSeconds: 7776000, partialFilterExpression: { "relevance_score": { "$lt": 5 } } })

// linkedin_sessions indexes
db.linkedin_sessions.createIndex({ "session_id": 1 }, { unique: true })
db.linkedin_sessions.createIndex({ "started_at": -1 })

// draft_content indexes
db.draft_content.createIndex({ "status": 1, "created_at": -1 })
db.draft_content.createIndex({ "source_intel_id": 1 })

// linkedin_trends indexes
db.linkedin_trends.createIndex({ "period": 1, "date": -1 })
```

### Add MongoDB URI to OpenClaw container

Edit docker-compose.yml, add under `openclaw.environment`:
```yaml
- MONGODB_URI=${MONGODB_URI}
```

Where `MONGODB_URI` comes from the existing `.env` file or is set directly.

---

## PHASE 4 — Telegram Briefing

### Setup
1. Create Telegram bot via @BotFather if not already done
2. Create private channel "AI Architect Intelligence"
3. Add bot as admin to channel
4. Get channel chat ID (send message, check via `getUpdates` API)
5. Add to docker-compose `openclaw.environment`:
   ```yaml
   - TELEGRAM_BOT_TOKEN=your_bot_token
   - TELEGRAM_CHAT_ID=your_channel_id
   ```

### Test
```bash
ssh root@72.61.92.76 "docker exec openclaw python3 /home/node/skills/linkedin-intel/scripts/telegram_briefing.py --test"
```

---

## PHASE 5 — Frontend Dashboard (Intelligence + Content Marketing + Analytics)

The frontend has **three main dashboard areas** plus supporting views. Full wireframes and schemas are in the plan doc Section 9A-9E.

### New files in job-search frontend

Create in `/Users/ala0001t/pers/projects/job-search/frontend/`:

#### Blueprint: `routes/dashboard.py`

```python
# --- 5A. Intelligence Dashboard ---
GET  /dashboard                          # Main intelligence overview
GET  /dashboard/opportunities            # HTMX: filterable intel items list
GET  /dashboard/scrape-runs              # HTMX: session history

# --- 5B. Content Marketing & Trending ---
GET  /dashboard/content                  # Content marketing hub (THE KEY PAGE)
GET  /dashboard/content/trends           # HTMX: trending keyword bars + delta %
GET  /dashboard/content/intersection     # HTMX: learning × trending × hiring engine
GET  /dashboard/content/calendar         # HTMX: weekly content calendar
GET  /dashboard/content/ideas            # HTMX: AI-suggested content ideas
GET  /dashboard/content/performance      # HTMX: post performance tracking
GET  /dashboard/content/influencers      # HTMX: recurring authors to engage
POST /dashboard/content/ideas/<id>/generate   # Generate draft from idea
POST /dashboard/content/track-post       # Log a posted piece for tracking

# --- 5C. Drafts ---
GET  /dashboard/drafts                   # All pending drafts (comments + posts)
POST /dashboard/drafts/<id>/approve      # Approve draft, copy to clipboard
POST /dashboard/drafts/<id>/edit         # Update draft text
POST /dashboard/drafts/<id>/skip         # Skip this draft
POST /dashboard/drafts/<id>/regenerate   # Regenerate with different prompt
POST /dashboard/drafts/<id>/posted       # Mark posted, enter URL for tracking

# --- 5D. Analytics ---
GET  /dashboard/analytics                # 7d/30d analytics overview
GET  /dashboard/analytics/api-usage      # HTMX: API call tracking chart
GET  /dashboard/analytics/keywords       # HTMX: keyword frequency chart
GET  /dashboard/analytics/sources        # HTMX: source breakdown (LinkedIn/Reddit/HN)
GET  /dashboard/analytics/relevance      # HTMX: score distribution histogram

# --- 5E. Video Content (Phase 8) ---
GET  /dashboard/videos                   # Video queue and status
POST /dashboard/videos/generate          # Generate video from content idea
GET  /dashboard/videos/<id>/preview      # Preview rendered video
```

#### Templates (Jinja2 + HTMX + Tailwind)
```
templates/
├── dashboard.html                           # Intelligence overview
├── dashboard_content.html                   # Content marketing hub
├── dashboard_drafts.html                    # Draft review queue
├── dashboard_analytics.html                 # Analytics overview
├── dashboard_videos.html                    # Video content (Phase 8)
├── components/
│   ├── dashboard_stats_cards.html           # Summary stat cards
│   ├── dashboard_opportunities.html         # Opportunity list
│   ├── dashboard_scrape_runs.html           # Session history table
│   ├── content_trends.html                  # Trending keyword bars
│   ├── content_intersection.html            # Learning × Trending × Hiring
│   ├── content_calendar.html                # Weekly publishing calendar
│   ├── content_ideas.html                   # AI-generated content ideas
│   ├── content_performance.html             # Post performance cards
│   ├── content_influencers.html             # People to engage list
│   ├── draft_card.html                      # Single draft card (approve/edit/skip)
│   ├── analytics_api_usage.html             # API calls sparkline
│   ├── analytics_keywords.html              # Keyword frequency bars
│   ├── analytics_sources.html               # Source pie/bar breakdown
│   └── analytics_relevance.html             # Relevance score histogram
```

#### Static assets
```
static/
├── dashboard.js              # HTMX polling, auto-refresh, copy-to-clipboard
├── charts.js                 # Lightweight charts (Chart.js or inline SVG bars)
└── dashboard.css             # Dashboard-specific styles (if needed beyond Tailwind)
```

### Register blueprint in app.py

```python
from routes.dashboard import dashboard_bp
app.register_blueprint(dashboard_bp)
```

### Repository layer

Add `repositories/intel_repository.py` using the existing repository pattern from `src/common/repositories/base.py`:

```python
class IntelRepository:
    # --- Intelligence ---
    def get_recent_intel(since, filters, page, per_page) -> list
    def get_stats(since) -> dict                    # aggregate counts
    def get_top_opportunities(limit) -> list         # highest relevance
    def get_scrape_sessions(limit) -> list           # session history

    # --- Content Marketing ---
    def get_trending_keywords(period, source_filter) -> list  # keyword + count + delta%
    def get_intersection_ideas(learning_progress) -> list     # THE KEY QUERY: learning × trending × hiring
    def get_tracked_authors(min_appearances) -> list           # recurring influencers
    def get_content_performance(period) -> list                # post performance metrics
    def get_content_calendar(week_start) -> dict               # drafts/ideas by day

    # --- Drafts ---
    def get_pending_drafts(type_filter) -> list
    def approve_draft(id) -> bool
    def skip_draft(id) -> bool
    def edit_draft(id, new_content) -> bool
    def regenerate_draft(id) -> dict
    def mark_posted(id, url) -> bool

    # --- Analytics ---
    def get_daily_volume(days) -> list               # items per day
    def get_api_usage(days) -> list                  # calls per day
    def get_source_breakdown(since) -> dict          # by source
    def get_relevance_distribution(since) -> dict    # score histogram
    def get_type_breakdown(since) -> dict            # job/post/freelance/etc
```

### Intersection Engine (most important query)

This is the core content-marketing intelligence — see full aggregation pipeline in plan doc Section 9B. It cross-references:
1. `linkedin_intel` keyword frequency (what's trending)
2. AI Architect checklist (what you're currently learning)
3. Job keyword frequency (what companies are hiring for)

And outputs ranked content ideas with temperature ratings (HOT/WARM/COLD).

### New MongoDB collections for content dashboard

Add these to Phase 3 index creation:

```javascript
// content_performance — tracks posted content metrics
db.content_performance.createIndex({ "posted_at": -1 })
db.content_performance.createIndex({ "topic_keywords": 1 })

// tracked_authors — recurring influencers to engage with
db.tracked_authors.createIndex({ "profile_url": 1 }, { unique: true })
db.tracked_authors.createIndex({ "times_seen": -1 })
db.tracked_authors.createIndex({ "topics": 1 })
```

Schemas for these collections are in plan doc Section 9B.

---

## PHASE 6 — Draft Engine + Brand Voice

### 6A. Brand Voice File

Create `/root/n8n-prod/skills/linkedin-intel/config/brand-voice.md` with:
- Voice attributes: thoughtful, practical, honest, questioning, specific
- Comment templates (insight pattern, contrarian pattern, question pattern, bridge pattern)
- Post structure: hook → body → close → question
- Engagement cadence ramp-up: week 1-2 → month 2 → month 3+
- Full guide is in plan doc Section 10B

### 6B. Draft Engine (Evening Cron)

Already covered in classifier.py and draft_generator.py (Phase 1). The engine:
1. Runs during evening analysis cron
2. For items scored >= 7 and tagged `respond-worthy`: generates comment via Claude Haiku
3. For items tagged `post-inspiration`: generates post idea via Claude Sonnet
4. Uses brand-voice.md as system prompt context for all generation
5. Stores in `draft_content` collection with `status: "draft"`
6. Surfaced in Dashboard drafts section + Telegram briefing
7. User approves/edits/skips via Dashboard UI
8. Approved content is copied to clipboard for manual LinkedIn posting

---

## PHASE 7 — Job Pipeline Integration Bridge

### Bridge: linkedin_intel → existing jobs collection

When user clicks "Add to Pipeline" or sends `/apply N` via Telegram:

```python
def convert_intel_to_job_doc(intel_item: dict) -> dict:
    """Convert linkedin_intel document to format expected by existing 7-layer pipeline."""
    return {
        "job_id": intel_item.get("url", "").split("/")[-1] or str(ObjectId()),
        "company": intel_item.get("company", "Unknown"),
        "role": intel_item.get("title", ""),
        "job_url": intel_item.get("url", ""),
        "location": intel_item.get("location_detail", {}).get("raw", ""),
        "description": intel_item.get("full_content", intel_item.get("content_preview", "")),
        "posted_at": intel_item.get("scraped_at"),
        "source": "linkedin_intel",
        "source_intel_id": intel_item["_id"],
        "score": intel_item.get("relevance_score"),
        "tier": "Tier 1" if intel_item.get("relevance_score", 0) >= 8 else "Tier 2",
        "created_at": datetime.utcnow(),
        "status": "new",
        "pipeline_status": "pending"
    }
```

This feeds into the existing pipeline: L1-4 extraction → L5 people intel → L6 CV/cover letter → L7 dossier.

Add to `intel_repository.py`:
```python
def push_to_pipeline(intel_id: str) -> dict:
    # Convert, insert into jobs collection, trigger runner API, mark acted_on
```

---

## PHASE 8 — Edge & Niche Opportunity Detection

### Add to classifier.py: edge detection rules

After basic classification, run edge detection using compound signal rules. Full rules in plan doc Section 16, key ones:

```python
EDGE_RULES = [
    {"name": "togaf_ai_crossover", "boost": +3, "signals": ["enterprise architecture + AI"]},
    {"name": "funded_and_hiring_ai", "boost": +2, "signals": ["series A/B/C + AI role"]},
    {"name": "industry_not_yet_ai_mature", "boost": +2, "signals": ["manufacturing/logistics/gov + AI"]},
    {"name": "pain_without_solution", "boost": +2, "signals": ["struggling + low comments"]},
    {"name": "governance_vacuum", "boost": +2, "signals": ["hiring ML eng but no architect"]},
    {"name": "multi_agent_early_adopter", "boost": +2, "signals": ["agentic + enterprise"]},
    {"name": "geographic_arbitrage", "boost": +1, "signals": ["remote + US salary"]},
]
```

Store on intel doc as `edge_opportunities` array with rule name, boost, reasoning.
Tag as `niche-opportunity`. Surface prominently in briefing and dashboard.

---

## PHASE 9 — Freelance Lead Pipeline + Outreach Strategy

### 9A. Freelance Lead Scoring

Different from job scoring. Full rubric in plan doc Section 11:
- Budget signals (25%): funding, enterprise, scope
- Urgency signals (20%): deadlines, ASAP language
- Scope fit (25%): architecture vs engineering
- Client sophistication (15%): has team, understands AI
- Engagement ease (15%): public post, timezone, responsive

### 9B. Lead Pipeline Collection

Create `lead_pipeline` collection (schema in plan doc Section 11):
- Status flow: identified → approached → conversation → proposal → won/lost/stale
- Status history tracking
- Next action + date
- Value estimate

### 9C. Outreach Templates

Create outreach draft templates in `brand-voice.md` (plan doc Section 12):
- Connection request templates (after commenting, cold, freelance response)
- Follow-up DM templates (value-first, discovery call ask)
- The system generates personalized versions using Claude Haiku

### 9D. Engagement → Lead Funnel

Visibility → Credibility → Connection → Conversation → Opportunity
System tracks where each contact is in the funnel and suggests next actions.

---

## PHASE 10 — Competitive Intelligence

### Auto-detect competitors

During scraping, if author appears 5+ times in 14 days on your target topics AND has "AI architect" or similar in headline → auto-add to `competitor_profiles` collection.

Track: topics covered, topics missing, avg engagement, posting frequency, positioning, weaknesses.

Weekly competitive brief on Saturday deep dive.

Schema in plan doc Section 10C.

---

## PHASE 11 — Geo & Compensation Intelligence

### Enrich intel items with:
- Compensation signals (salary range, inferred bracket)
- Location detail (country, region, remote policy, timezone compatibility)

### Weekly geo aggregation in linkedin_trends:
- Demand by region (UAE, UK, EU, US, Remote)
- Compensation ranges by role
- Freelance rate ranges

Dashboard widget at `/dashboard/analytics/geo`. Schema in plan doc Section 13.

---

## PHASE 12 — Learning Reprioritization Engine

### Market-driven learning suggestions

Cross-reference trending topics with your study plan. If "AI governance" is surging (+62%), suggest moving Course 6 earlier.

Logic: `market_urgency = (trend_score * 0.4) + (job_demand * 0.4) - (competition * 0.2)`

Show in content dashboard intersection engine + Monday Telegram briefing.

Full algorithm in plan doc Section 18.

---

## PHASE 13 — Telegram Interactive Commands

### Add to OpenClaw skill: command handler

```python
COMMANDS = {
    "/apply N":  # Push item N into 7-layer job pipeline
    "/draft N":  # Generate draft comment for item N
    "/save N":   # Bookmark item
    "/detail N": # Get full content
    "/skip N":   # Skip item
    "/lead N":   # Move to lead_pipeline
    "/stats":    # System stats
    "/search Q": # Manual keyword search (5 API calls)
    "/pause":    # Pause all scraping 24h
    "/resume":   # Resume scraping
    "/trends":   # Weekly trending keywords
    "/next":     # Next unread high-relevance items
}
```

Update briefing format to include action numbers `[1] [2] [3]` and command hints.
Full implementation in plan doc Section 14.

---

## PHASE 14 — Reddit & Public Web (Full)

### Reddit-specific fields

Extend `linkedin_intel` with `reddit_meta` subdocument: subreddit, flair, upvote_ratio, score, num_comments, author_karma.

### Subreddit search config

Full config in plan doc Section 19:
- Daily: r/MachineLearning, r/forhire, r/MLjobs
- 2x/week: r/RemoteJobs, r/datascience
- Weekly: r/consulting, r/ExperiencedDevs, r/LocalLLaMA

### Reddit engagement uses different tone than LinkedIn

Draft generation prompt template should be adapted per platform.

### Add to skill: `scripts/reddit_search.py`

Uses PRAW library. Add `praw>=7.7` to requirements.txt.

### HN Who's Hiring, RemoteOK, RSS feeds

- HN: Algolia API, monthly (1st of month)
- RemoteOK: JSON API, Mon/Thu
- RSS: n8n RSS Trigger → webhook → OpenClaw skill
- Full source list with URLs in plan doc Section 17

---

## PHASE 15 — VPS Monitoring & Health

### health-monitor.sh

Create on VPS at `/root/n8n-prod/scripts/health-monitor.sh`. Checks: disk, RAM, container status, Ollama health. Alerts via Telegram. Run every 5 min via crontab.

Full script in plan doc Section 21.

### Docker healthchecks

Add healthcheck to each service in docker-compose.yml.

### Dashboard health widget

System health panel at bottom of `/dashboard`. Shows: VPS status, container health, Ollama status, MongoDB connection, cookie validity, last/next scrape time.

---

## PHASE 16 — Data Retention & Archival

### Retention policy

- High-relevance items: keep indefinitely
- Low-relevance: TTL 90 days
- Skipped drafts: TTL 30 days
- Everything else: keep indefinitely

### Monthly export

`scripts/monthly_export.py` — exports high-value intel, trends, leads, content performance to Google Sheets. Cron: 1st of month 6 AM.

### Weekly backup

`mongodump` weekly (Sunday 2 AM), keep last 4 backups. Full details in plan doc Section 22.

---

## PHASE 17 — Local LLM on VPS

```bash
ssh root@72.61.92.76
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2.5:7b-instruct-q4_K_M    # 4.7GB, primary
ollama pull phi4-mini                       # 2.4GB, lightweight fallback
ollama pull nomic-embed-text                # 274MB, embeddings
```

Until Ollama is installed, all classification falls back to Claude Haiku API.

---

## PHASE 18 — Remotion Video System (Full)

### Setup
```bash
cd /Users/ala0001t/pers/projects/job-search
npm init video@latest video-content
cd video-content
npx skills add remotion-dev/skills
```

### Templates
4 video templates: QuickTip (15-30s), MythBuster (30-45s), ToolDemo (45-60s), WeeklyRoundup (60s).
Format: 1080x1920 TikTok vertical, 30fps.
Full template structures, JSON script schema, pipeline, and project structure in plan doc Section 20.

### Publishing cadence
Week 1-2: 1/week → Month 2: 2/week → Month 3+: 3/week + 1 roundup

### Dashboard at `/dashboard/videos`
Video queue, preview, script editor, render progress, performance tracking.

---

## STAGED EXECUTION PLAN

This system is large. **Do NOT attempt to implement everything at once.** Break into 4 stages:

### STAGE 1 — Foundation (Week 1)
Phases: 0, 1, 2, 3, 4 (partial)
Goal: Cookie auth + working OpenClaw skill + cron scraping + MongoDB storage + basic Telegram briefing
Deliverable: System scrapes LinkedIn daily and sends a morning briefing to Telegram

### STAGE 2 — Intelligence (Week 2-3)
Phases: 4 (full), 5A, 6, 7, 8, 13
Goal: Interactive Telegram commands + intelligence dashboard + brand voice + draft engine + pipeline bridge + edge detection
Deliverable: Full scrape → classify → draft → review loop. Jobs flow into existing pipeline.

### STAGE 3 — Growth (Week 4-5)
Phases: 5B, 5C, 9, 10, 11, 12, 14
Goal: Content marketing dashboard + freelance lead pipeline + competitive intel + geo/comp tracking + learning reprioritization + Reddit expansion
Deliverable: Complete brand-building command center with multi-source intelligence

### STAGE 4 — Scale (Week 6+)
Phases: 15, 16, 17, 18
Goal: VPS monitoring + data archival + local LLM + Remotion video system
Deliverable: Self-sustaining autonomous system with video content creation

### Per-Stage Approach

For each stage, the Claude Code session should:
1. **Read the plan doc** first: `job-search/plans/linkedin-intelligence-system.md`
2. **Create a stage-specific sub-plan** in `job-search/plans/stage-N-plan.md`
3. **Implement phase by phase** within the stage
4. **Test each phase** before moving to the next
5. **Commit working code** at each phase boundary
6. **Update the plan doc** with actual implementation notes and any deviations

---

## Constraints & Reminders

1. **LinkedIn safety is non-negotiable.** Never exceed 150 calls/day. Never scrape Sundays. Stop immediately on 429/403.
2. **No Claude co-author signature** on any git commits.
3. **Preserve tokens** — use Haiku for simple tasks, Sonnet for code/content, Opus only for architecture decisions.
4. **MongoDB** — use existing `job_search` database, new collections only.
5. **Docker-compose changes** — always update BOTH local mirror (`/Users/ala0001t/pers/projects/job-search/n8n/docker-compose.yml`) and VPS (`/root/n8n-prod/docker-compose.yml`).
6. **Test incrementally** — get Phase 0 working first (cookie mount + verify), then Phase 1 script-by-script, then cron.
7. **Warmup period** — first 14 days, limit to 30 LinkedIn calls/day max.
8. **Staged execution** — follow the 4-stage plan. Do NOT jump ahead. Each stage must be working before starting the next.
9. **Sub-plans** — create `stage-N-plan.md` for each stage with specific tasks, files to create, and test criteria.
10. **Existing patterns** — follow the repository pattern from `src/common/repositories/base.py`, the Flask blueprint pattern from `frontend/`, and the existing docker-compose conventions.
