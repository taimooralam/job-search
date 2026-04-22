# LinkedIn Intelligence & Brand Building System

## Architecture Reference

**Created:** 2026-02-17 | **Status:** Implementation Plan

---

## 1. System Overview

```
┌─────────────── VPS (72.61.92.76) ──────────────────────────┐
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Traefik  │  │  n8n     │  │ OpenClaw │  │  Ollama   │  │
│  │ (proxy)  │  │ (worker) │  │ (agent)  │  │ (7B LLM)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│                                                              │
│  Cookies: /root/n8n-prod/cookies/linkedin-cookies.txt       │
│  Skills:  /root/n8n-prod/skills/linkedin-intel/             │
│  Docker:  /root/n8n-prod/docker-compose.yml                 │
└──────────────────────┬───────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   MongoDB Atlas   Telegram    Job Search App
   (linkedin_intel) (briefing)  (dashboard UI)
```

### Data Flow

```
Sources (cron-scheduled)           Processing              Output
─────────────────────────         ──────────────          ──────────────
LinkedIn Jobs Search    ──┐                               ┌─ Telegram Briefing (7 AM)
LinkedIn Posts Search   ──┤      ┌──────────────┐        ├─ Dashboard UI (Flask/HTMX)
LinkedIn Pain Points    ──┼─────▶│ OpenClaw     │───────▶├─ Draft Comments/Posts
Reddit (future)         ──┤      │ Skill +      │        ├─ Trend Analytics
HN Who's Hiring (future)─┤      │ Local LLM    │        ├─ Video Scripts (Remotion)
RemoteOK API (future)   ──┘      └──────────────┘        └─ MongoDB (all data)
```

---

## 2. LinkedIn Cookie Authentication

### Storage
- **VPS path:** `/root/n8n-prod/cookies/linkedin-cookies.txt`
- **Container mount:** `/home/node/linkedin-cookies.txt:ro`
- **Format:** Netscape cookie file (same as yt-cookies.txt)
- **Critical cookies:** `li_at` (session), `JSESSIONID` (CSRF), `bcookie` (browser ID)
- **Expiry:** `li_at` lasts ~1 year. Bimonthly health check via cron.

### How to Extract
1. Login to linkedin.com in Chrome
2. Install "Get cookies.txt LOCALLY" extension
3. Export for `.linkedin.com` domain
4. SCP to VPS: `scp linkedin-cookies.txt root@72.61.92.76:/root/n8n-prod/cookies/`

### Docker-Compose Addition
```yaml
# Under openclaw.volumes, add:
- /root/n8n-prod/cookies/linkedin-cookies.txt:/home/node/linkedin-cookies.txt:ro
```

---

## 3. Cron Schedule

| Time | Cron | Task | LinkedIn API Budget |
|------|------|------|-------------------|
| 3 AM (±15m jitter) | `0 3 * * 1-6` | LinkedIn scrape (jobs + posts) | 50 calls |
| 8 PM (±15m jitter) | `0 20 * * 1-6` | Classify, score, generate drafts | 30 calls |
| 7 AM | `0 7 * * *` | Telegram morning briefing | 0 calls |
| Sat 10 AM | `0 10 * * 6` | Weekend deep dive (all categories) | 50 calls |
| 1st bimonthly | `0 12 1 */2 *` | Cookie health check | 1 call |
| 4 AM (future) | `0 4 * * 1-6` | Reddit + HN + RemoteOK scrape | N/A |

**Daily limit:** 150 LinkedIn API calls (self-imposed, well under 900/hr detection).
**Sunday:** Full rest day — no LinkedIn scraping.

### Keyword Rotation
```
Monday:    Jobs (AI Architect, Head of AI) + Thought Leadership
Tuesday:   Freelance (AI consulting, LLM implementation) + Pain Points
Wednesday: Niche (TOGAF AI, multi-agent enterprise) + Learning-related
Thursday:  Jobs (AI Strategy, AI Platform Lead) + Pain Points
Friday:    Thought Leadership + Freelance
Saturday:  All categories (reduced depth each)
```

---

## 4. Search Categories & Keywords

### Category 1 — Target Jobs
`"AI Architect"`, `"Enterprise AI"`, `"Chief AI Officer"`, `"Head of AI"`,
`"AI Strategy"`, `"AI Platform Lead"`, `"Solutions Architect AI"`,
`"ML Platform"`, `"AI Engineering Manager"`, `"VP Engineering AI"`,
`"Director AI"`, `"AI Transformation"`

### Category 2 — Freelance & Consulting
`"AI consulting project"`, `"LLM implementation"`, `"AI strategy consultant"`,
`"enterprise AI advisor"`, `"fractional CTO AI"`, `"AI transformation project"`,
`"RAG implementation"`, `"agentic AI project"`

### Category 3 — Thought Leadership
`"AI architecture challenges"`, `"enterprise AI strategy"`, `"AI governance"`,
`"responsible AI"`, `"AI ROI"`, `"LLM in production"`,
`"AI transformation pain"`, `"agentic AI enterprise"`, `"AI leadership lessons"`

### Category 4 — Pain Points & Opportunities
`"struggling with AI"`, `"AI project failed"`, `"need AI architect"`,
`"looking for AI help"`, `"AI budget"`, `"AI team building"`,
`"enterprise LLM challenges"`, `"RAG not working"`

### Category 5 — Niche (from certifications)
`"enterprise architecture AI"`, `"TOGAF AI integration"`,
`"multi-agent systems enterprise"`, `"AI agent governance"`,
`"model context protocol"`, `"vector database architect"`,
`"RAG production issues"`, `"AI tool integration"`

### Category 6 — Learning-Related
Auto-generated from recently completed concepts in:
`study-plan/01-ai-architect-knowledge-checklist.md`

---

## 5. MongoDB Schema

### Database: `job_search` (existing)

### Collection: `linkedin_intel`
```json
{
  "_id": "ObjectId",
  "source": "linkedin|reddit|hackernews|remoteok|rss",
  "type": "job|freelance|post|pain_point|opportunity|article",
  "category": "target_job|freelance|thought_leadership|pain_point|niche|learning_related",
  "title": "string",
  "url": "string",
  "author": { "name": "string", "headline": "string", "profile_url": "string" },
  "company": "string",
  "content_preview": "string (first 500 chars)",
  "full_content": "string",
  "engagement": { "likes": 0, "comments": 0, "reposts": 0 },
  "relevance_score": 8,
  "relevance_reasoning": "string",
  "keywords_matched": ["AI Architect", "enterprise"],
  "search_query_used": "string",
  "classification": {
    "model_used": "qwen2.5:7b|claude-haiku",
    "confidence": 0.92,
    "tags": ["high-value", "respond-worthy", "trending"]
  },
  "draft_response": {
    "comment": "string",
    "post_idea": "string",
    "generated_by": "claude-haiku|local",
    "status": "draft|approved|posted|skipped"
  },
  "dedupe_hash": "sha256(source+url+title)",
  "first_seen_at": "ISODate",
  "last_seen_at": "ISODate",
  "scraped_at": "ISODate",
  "session_id": "string",
  "acted_on": false,
  "notes": "string"
}
```

### Collection: `linkedin_sessions`
```json
{
  "_id": "ObjectId",
  "session_id": "uuid",
  "source": "linkedin",
  "started_at": "ISODate",
  "completed_at": "ISODate",
  "trigger": "cron|manual",
  "keywords_used": ["AI Architect"],
  "categories_searched": ["target_job"],
  "api_calls_made": 47,
  "items_found": 23,
  "items_new": 18,
  "items_duplicate": 5,
  "errors": [],
  "rate_limit_hit": false,
  "status": "completed|partial|failed|rate_limited"
}
```

### Collection: `draft_content`
```json
{
  "_id": "ObjectId",
  "type": "comment|post|article|video_script",
  "source_intel_id": "ObjectId (ref to linkedin_intel)",
  "content": "string",
  "platform": "linkedin|tiktok|twitter",
  "generated_by": "claude-haiku|claude-sonnet|local",
  "status": "draft|approved|posted|skipped",
  "created_at": "ISODate",
  "approved_at": "ISODate",
  "posted_at": "ISODate"
}
```

### Collection: `linkedin_trends`
```json
{
  "_id": "ObjectId",
  "period": "daily|weekly|monthly",
  "date": "ISODate",
  "top_keywords": [{"keyword": "string", "count": 0, "delta": 0}],
  "job_volume": { "total": 0, "high_relevance": 0 },
  "emerging_roles": ["string"],
  "pain_points_trending": ["string"],
  "recommended_actions": ["string"]
}
```

### Indexes
```javascript
db.linkedin_intel.createIndex({ "dedupe_hash": 1 }, { unique: true })
db.linkedin_intel.createIndex({ "scraped_at": -1 })
db.linkedin_intel.createIndex({ "relevance_score": -1, "scraped_at": -1 })
db.linkedin_intel.createIndex({ "type": 1, "category": 1, "scraped_at": -1 })
db.linkedin_intel.createIndex({ "classification.tags": 1 })
db.linkedin_intel.createIndex({ "title": "text", "content_preview": "text", "full_content": "text" })
// TTL: auto-delete low-relevance items after 90 days
db.linkedin_intel.createIndex({ "scraped_at": 1 }, { expireAfterSeconds: 7776000, partialFilterExpression: { "relevance_score": { "$lt": 5 } } })
```

---

## 6. LinkedIn Safety Protocol

### Hard Limits (safety-config.json)
```json
{
  "max_calls_per_session": 50,
  "max_sessions_per_day": 3,
  "max_calls_per_day": 150,
  "min_delay_seconds": 5,
  "max_delay_seconds": 15,
  "rest_day": "sunday",
  "cooldown_on_429_hours": 24,
  "cooldown_on_403_hours": 168,
  "warmup_period_days": 14,
  "warmup_max_calls_per_day": 30,
  "session_max_duration_minutes": 30,
  "vary_session_start_minutes": 15,
  "max_consecutive_search_pages": 3
}
```

### Behavioral Mimicry
- Jitter all timings: `delay = random(5,15) + gaussian(0,2)`
- Session start variance: ±15 minutes from scheduled time
- Mix search types: alternate jobs ↔ posts, never hammer one endpoint
- Page depth: never beyond page 3
- Headers: rotate User-Agent from realistic pool
- Referer chain: include realistic referers

### Escalation Protocol
```
Level 0 (Normal):   Full configured limits
Level 1 (Caution):  CAPTCHA → 50% volume for 48h
Level 2 (Warning):  429 → stop 24h, resume at 30% for 1 week
Level 3 (Alert):    Multiple 429s/week → stop 1 week
Level 4 (Critical): 403 or account warning → FULL STOP, manual review
```

---

## 7. Telegram Morning Briefing Format

```
🌅 Morning Intelligence — {date}

📊 Last Night: {N} new ({jobs} jobs, {posts} posts, {opps} opportunities)
🎯 High-relevance: {count} items (score ≥ 7)

🏢 Top Jobs:
1. {title} @ {company} — {score}/10
   {url}
2. ...
3. ...

💬 Engage These Posts:
1. {author}: "{preview}..."
   Draft: "{comment_draft}"
   {url}
2. ...

📈 Trends: {top_keyword} (+{delta}%), {emerging}
⚙️ Health: {calls}/150 API | Cookie: ✓ valid | Errors: {n}
```

---

## 8. Model Routing

| Task | Model | Location | Cost |
|------|-------|----------|------|
| Classify scrape items | Qwen 2.5 7B Q4_K_M | VPS Ollama | $0 |
| Score relevance 1-10 | Qwen 2.5 7B | VPS Ollama | $0 |
| Extract keywords | Qwen 2.5 7B | VPS Ollama | $0 |
| Generate embeddings | nomic-embed-text | VPS Ollama | $0 |
| Compile briefing text | Qwen 2.5 7B | VPS Ollama | $0 |
| Draft short comments | Claude Haiku | API | ~$1/mo |
| Draft original posts | Claude Sonnet | API | ~$2/mo |
| Trend analysis | DeepSeek R1 | API (cached) | ~$3/mo |
| Video scripts | Claude Sonnet | API | ~$3/mo |
| Strategic decisions | Claude Opus | API (rare) | ~$5/mo |

**Estimated API cost:** ~$14/month + VPS hosting $13-25/month

### VPS Memory Budget (8GB)
```
OS + system:        1.0 GB
PostgreSQL:         0.5 GB
Redis:              0.3 GB
n8n (main+worker):  1.0 GB
OpenClaw:           0.5 GB
Traefik:            0.1 GB
Available→Ollama:   4.6 GB  ← fits Qwen 7B Q4_K_M (4.7GB)
```

---

## 9. Frontend Dashboard (Flask/HTMX)

### 9A. Intelligence Dashboard — `/dashboard`

Overview page: stats cards, scrape run list, top opportunities.

Routes:
- `GET /dashboard` — Main page
- `GET /dashboard/opportunities` — Filterable intel items
- `GET /dashboard/scrape-runs` — Session history and health

```
┌─────────────────────────────────────────────────────────────┐
│  🎯 Intelligence Dashboard                                    │
│                                                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ 47 New  │ │ 12 Jobs │ │ 8 Posts │ │ 3 Leads │          │
│  │ Today   │ │ Found   │ │ to Read │ │ Flagged │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│                                                               │
│  ┌──── Scrape Runs ────────────────────────── [View All] ──┐ │
│  │ ✓ Morning Scrape  03:12  47 items  48/150 API calls     │ │
│  │ ✓ Evening Analysis 20:04  12 drafts  28/150 calls       │ │
│  │ ⏳ Next: Morning Scrape in 6h 23m                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── Top Opportunities ──────────────────── [View All] ──┐ │
│  │ 🎯 9/10 Head of AI @ TechCorp — Remote                 │ │
│  │   [View] [Add to Pipeline] [Dismiss]                     │ │
│  │ 💼 8/10 "Need AI consulting for agent arch" — freelance │ │
│  │   [View] [Draft Response] [Save]                         │ │
│  │ 💡 8/10 Pain point post by VP Eng @BigCo                │ │
│  │   [View] [Draft Comment] [Skip]                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 9B. Content Marketing & Trending Dashboard — `/dashboard/content`

This is the **brand-building command center**. It connects three data streams into actionable content:

1. **What you're learning** (from AI Architect checklist progress)
2. **What's trending** (from LinkedIn post scrapes + engagement data)
3. **What people are hiring for** (from job scrapes + keyword frequency)

Routes:
- `GET /dashboard/content` — Content marketing hub
- `GET /dashboard/content/trends` — HTMX partial: trend visualization
- `GET /dashboard/content/calendar` — HTMX partial: content calendar
- `GET /dashboard/content/ideas` — HTMX partial: AI-generated content ideas
- `GET /dashboard/content/performance` — HTMX partial: post performance tracking
- `GET /dashboard/content/influencers` — HTMX partial: people to engage with
- `POST /dashboard/content/ideas/<id>/generate` — Generate draft from idea
- `POST /dashboard/content/drafts/<id>/approve` — Approve for posting
- `POST /dashboard/content/drafts/<id>/edit` — Edit draft content

```
┌─────────────────────────────────────────────────────────────┐
│  📈 Content Marketing & Trends                                │
│                                                               │
│  ┌──── Trending Topics (7 days) ───────────────────────────┐ │
│  │                                                           │ │
│  │  "AI governance"      ████████████████████ 34 (+62%)    │ │
│  │  "RAG production"     ███████████████░░░░░ 28 (+15%)    │ │
│  │  "agentic AI"         ██████████████░░░░░░ 25 (+41%)    │ │
│  │  "AI architect"       ████████████░░░░░░░░ 21 (+8%)     │ │
│  │  "LLM costs"          ████████░░░░░░░░░░░░ 14 (NEW)    │ │
│  │  "multi-agent"        ███████░░░░░░░░░░░░░ 12 (+23%)   │ │
│  │                                                           │ │
│  │  Timeframe: [7d] [14d] [30d]  Source: [All] [Jobs] [Posts]│
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── Intersection Engine ────────────────────────────────┐ │
│  │                                                           │ │
│  │  🎓 You're learning     📈 Trending         🏢 Hiring   │ │
│  │  ┌─────────────┐       ┌──────────────┐   ┌──────────┐ │ │
│  │  │ RAG (Course │       │ "RAG produc- │   │ 8 jobs   │ │ │
│  │  │ 3, active)  │──────▶│  tion issues"│──▶│ mention  │ │ │
│  │  │             │  HOT  │  +15% trend  │   │ RAG exp  │ │ │
│  │  └─────────────┘       └──────────────┘   └──────────┘ │ │
│  │                                                           │ │
│  │  💡 SUGGESTED POST: "3 RAG lessons from building         │ │
│  │     enterprise retrieval pipelines"                       │ │
│  │     Why: You're studying RAG + it's trending + companies │ │
│  │     are hiring for it = maximum relevance & credibility   │ │
│  │     [Generate Draft] [Save Idea] [Dismiss]                │ │
│  │                                                           │ │
│  │  💡 SUGGESTED COMMENT: On @JaneDoe's RAG struggles post  │ │
│  │     "Share your Course 3 insight on hybrid retrieval"     │ │
│  │     [Generate Draft] [Skip]                               │ │
│  │                                                           │ │
│  │  ┌─────────────┐       ┌──────────────┐   ┌──────────┐ │ │
│  │  │ AI Govern-  │       │ "AI governa- │   │ 5 jobs   │ │ │
│  │  │ ance (Crs 6 │──────▶│  nce" +62%   │──▶│ mention  │ │ │
│  │  │ upcoming)   │ WARM  │  trending    │   │ governan │ │ │
│  │  └─────────────┘       └──────────────┘   └──────────┘ │ │
│  │                                                           │ │
│  │  💡 SUGGESTED: Start Course 6 sooner — governance is      │ │
│  │     exploding in demand. Early authority = advantage.      │ │
│  │     [Reprioritize Learning] [Note] [Dismiss]              │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── Content Calendar ────────────────── [+ New Post] ───┐ │
│  │                                                           │ │
│  │  Mon 17 │ Tue 18  │ Wed 19  │ Thu 20  │ Fri 21         │ │
│  │  ───────┼─────────┼─────────┼─────────┼───────          │ │
│  │  💬 2   │ 📝 Post │         │ 💬 2   │ 📝 Post        │ │
│  │  comment│ "RAG    │  (rest) │ comment│ "AI Gov-        │ │
│  │  drafts │ lessons"│         │ drafts │ ernance"        │ │
│  │  ready  │ DRAFT   │         │ pending│ IDEA            │ │
│  │                                                           │ │
│  │  Publishing cadence: 2 posts/week + 2 comments/day      │ │
│  │  Status: ✓ 3 posted │ 📝 2 drafts │ 💡 4 ideas       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── Draft Queue ──────────────────────── [View All] ────┐ │
│  │                                                           │ │
│  │  📝 POST DRAFT — "3 RAG Lessons from Enterprise..."     │ │
│  │  Generated: 2h ago │ By: Claude Sonnet │ Words: 247     │ │
│  │  [Preview] [Edit] [Approve & Copy] [Regenerate] [Skip]  │ │
│  │                                                           │ │
│  │  💬 COMMENT DRAFT — Reply to @VP_Eng RAG post           │ │
│  │  "Great question. In production RAG, we found that..."   │ │
│  │  [Preview] [Edit] [Approve & Copy] [Regenerate] [Skip]  │ │
│  │                                                           │ │
│  │  💬 COMMENT DRAFT — Reply to @CTO_StartupX AI pain      │ │
│  │  "This mirrors what I see in enterprise AI adoption..."  │ │
│  │  [Preview] [Edit] [Approve & Copy] [Regenerate] [Skip]  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── Post Performance ─────────────────────── [7d|30d] ──┐ │
│  │                                                           │ │
│  │  Your Posts (manual tracking after posting):              │ │
│  │  1. "Why enterprise RAG fails" — 👍 47 💬 12 🔄 5      │ │
│  │     Profile views after: +23 │ Connection requests: +4   │ │
│  │  2. "TOGAF meets Agentic AI" — 👍 31 💬 8 🔄 3        │ │
│  │     Profile views after: +15 │ Connection requests: +2   │ │
│  │                                                           │ │
│  │  Best performing topic: RAG (2.3x avg engagement)        │ │
│  │  Best posting time: Tue/Thu 9-11 AM                      │ │
│  │  Follower growth: +18 this week                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── People to Engage ─────────────────── [View All] ────┐ │
│  │                                                           │ │
│  │  Recurring authors posting about your topics:             │ │
│  │  👤 Jane Doe — VP AI @ BigCo — Posts about: RAG, agents │ │
│  │     Seen 4x this week │ Avg engagement: 120 likes        │ │
│  │     [View Posts] [Draft Comment on Latest]                │ │
│  │  👤 John Smith — CTO @ AI Startup — Posts about: govnce │ │
│  │     Seen 3x this week │ Avg engagement: 85 likes         │ │
│  │     [View Posts] [Draft Comment on Latest]                │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Intersection Engine — MongoDB Aggregation

The core of the content dashboard is the **intersection engine** that correlates three data streams:

```javascript
// Aggregation pipeline: find topics that are trending + you're learning + hiring for
db.linkedin_intel.aggregate([
  // Stage 1: Get keyword frequency from last 7 days
  { $match: { scraped_at: { $gte: sevenDaysAgo } } },
  { $unwind: "$keywords_matched" },
  { $group: {
    _id: "$keywords_matched",
    total: { $sum: 1 },
    jobs: { $sum: { $cond: [{ $eq: ["$type", "job"] }, 1, 0] } },
    posts: { $sum: { $cond: [{ $eq: ["$type", "post"] }, 1, 0] } },
    avg_engagement: { $avg: "$engagement.likes" },
    sample_urls: { $push: { $cond: [{ $gte: ["$relevance_score", 7] }, "$url", "$$REMOVE"] } }
  }},
  // Stage 2: Compare with previous 7 days for delta
  { $lookup: {
    from: "linkedin_trends",
    let: { keyword: "$_id" },
    pipeline: [
      { $match: { period: "weekly", date: { $gte: twoWeeksAgo, $lt: sevenDaysAgo } } },
      { $unwind: "$top_keywords" },
      { $match: { $expr: { $eq: ["$top_keywords.keyword", "$$keyword"] } } }
    ],
    as: "prev_week"
  }},
  { $addFields: {
    delta_pct: {
      $cond: [
        { $gt: [{ $size: "$prev_week" }, 0] },
        { $multiply: [
          { $divide: [
            { $subtract: ["$total", { $arrayElemAt: ["$prev_week.top_keywords.count", 0] }] },
            { $arrayElemAt: ["$prev_week.top_keywords.count", 0] }
          ]}, 100
        ]},
        null  // NEW keyword
      ]
    }
  }},
  { $sort: { total: -1 } },
  { $limit: 20 }
])
```

Then cross-reference with learning progress:

```python
def get_intersection_ideas(trends, learning_checklist):
    """Find topics where learning + trending + hiring overlap."""
    ideas = []
    for trend in trends:
        keyword = trend["_id"]
        # Check if keyword relates to a course being studied
        course_match = find_course_for_keyword(keyword, learning_checklist)
        if course_match and trend["jobs"] > 0 and trend["posts"] > 0:
            ideas.append({
                "keyword": keyword,
                "temperature": "HOT" if trend["delta_pct"] and trend["delta_pct"] > 30 else "WARM",
                "learning": course_match,
                "trending": {"count": trend["total"], "delta": trend["delta_pct"]},
                "hiring": {"job_count": trend["jobs"]},
                "suggested_post": generate_post_idea(keyword, course_match, trend),
                "suggested_comment_targets": trend["sample_urls"][:3]
            })
    return sorted(ideas, key=lambda x: x["trending"]["count"], reverse=True)
```

### Content Performance Tracking — MongoDB Schema

New collection: `content_performance`

```json
{
  "_id": "ObjectId",
  "platform": "linkedin",
  "type": "post|comment|article",
  "content": "string (what was posted)",
  "url": "string (LinkedIn post URL, manually entered after posting)",
  "topic_keywords": ["RAG", "enterprise"],
  "source_draft_id": "ObjectId (ref to draft_content)",
  "posted_at": "ISODate",
  "metrics_snapshots": [
    {
      "captured_at": "ISODate",
      "likes": 47,
      "comments": 12,
      "reposts": 5,
      "impressions": 2100
    }
  ],
  "profile_impact": {
    "profile_views_before": 45,
    "profile_views_after": 68,
    "connection_requests_after": 4
  },
  "notes": "string"
}
```

Index:
```javascript
db.content_performance.createIndex({ "posted_at": -1 })
db.content_performance.createIndex({ "topic_keywords": 1 })
```

### Influencer/People Tracking — MongoDB Schema

New collection: `tracked_authors`

```json
{
  "_id": "ObjectId",
  "source": "linkedin",
  "name": "string",
  "headline": "string",
  "profile_url": "string",
  "topics": ["RAG", "AI governance"],
  "times_seen": 12,
  "avg_engagement": 120,
  "last_seen_at": "ISODate",
  "first_seen_at": "ISODate",
  "relationship": "none|commented|connected|engaged",
  "notes": "string"
}
```

This is auto-populated: during classification, if the same author appears 3+ times in 7 days, they get added to `tracked_authors`.

### 9C. Drafts Dashboard — `/dashboard/drafts`

Routes:
- `GET /dashboard/drafts` — All pending drafts
- `POST /dashboard/drafts/<id>/approve` — Mark approved, copy to clipboard
- `POST /dashboard/drafts/<id>/edit` — Update draft text
- `POST /dashboard/drafts/<id>/skip` — Skip this draft
- `POST /dashboard/drafts/<id>/regenerate` — Regenerate with different prompt
- `POST /dashboard/drafts/<id>/posted` — Mark as posted, enter URL for tracking

### 9D. Analytics Dashboard — `/dashboard/analytics`

Routes:
- `GET /dashboard/analytics` — 7-day/30-day analytics overview
- `GET /dashboard/analytics/api-usage` — API call tracking chart
- `GET /dashboard/analytics/keyword-frequency` — Keyword trend chart
- `GET /dashboard/analytics/source-breakdown` — LinkedIn vs Reddit vs HN breakdown
- `GET /dashboard/analytics/relevance-distribution` — Score distribution histogram

```
┌─────────────────────────────────────────────────────────────┐
│  📊 Analytics — Last 30 Days                                  │
│                                                               │
│  ┌──── Volume ─────────────────────────────────────────────┐ │
│  │ Items/day:   ▁▂▃▅▄▆▇▅▃▄▅▆▇▅▄▃▅▆▇▅▃▄▅▆▇▅▄▃▅▆       │ │
│  │ High-rel:    ▁▁▂▃▂▃▄▃▂▂▃▃▄▃▂▂▃▃▄▃▂▂▃▃▄▃▂▂▃▃       │ │
│  │ API calls:   ▃▃▃▃▃▃▅▃▃▃▃▃▃▅▃▃▃▃▃▃▅▃▃▃▃▃▃▅▃▃       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── By Source ──────────┐ ┌──── By Type ────────────────┐ │
│  │ LinkedIn  ████████ 78%  │ │ Jobs       ████████ 45%     │ │
│  │ Reddit    ██░░░░░░ 12%  │ │ Posts      █████░░░ 28%     │ │
│  │ HN        █░░░░░░░  6%  │ │ Pain pts   ██░░░░░░ 12%    │ │
│  │ RemoteOK  █░░░░░░░  4%  │ │ Freelance  █░░░░░░░  8%    │ │
│  └──────────────────────── │ │ Opps       █░░░░░░░  7%    │ │
│                             │ └────────────────────────────┘ │
│  ┌──── Relevance Distribution ─────────────────────────────┐ │
│  │ 9-10: ██ (12)                                            │ │
│  │ 7-8:  ████████ (43)                                      │ │
│  │ 5-6:  ██████████████ (78)                                │ │
│  │ 3-4:  ████████████ (65)                                  │ │
│  │ 1-2:  ████████ (41)                                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──── Content Performance ────────────────────────────────┐ │
│  │ Posts this month: 8 │ Comments: 22                       │ │
│  │ Avg post engagement: 35 likes, 8 comments               │ │
│  │ Best topic: "RAG" (2.3x avg)                            │ │
│  │ Best time: Tue/Thu 9-11 AM                              │ │
│  │ Follower growth: +52 this month                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 9E. Video Content Dashboard — `/dashboard/videos`

(Phase 8 — Remotion integration)
- `GET /dashboard/videos` — Video content queue and status
- `POST /dashboard/videos/generate` — Generate video from content idea
- `GET /dashboard/videos/<id>/preview` — Preview rendered video

---

## 10. Brand Strategy & Positioning

### 10A. Unique Positioning

**Core differentiator:** TOGAF-certified Enterprise Architect + hands-on Agentic AI builder. This combination is extremely rare — most AI people lack enterprise architecture discipline, most TOGAF people lack AI depth.

**Positioning statement:**
> "I bridge the gap between enterprise architecture governance and cutting-edge AI implementation — helping large organizations adopt agentic AI without the chaos."

**Content pillars** (3-4 themes you always post about):

| Pillar | What It Covers | Why It Works |
|--------|---------------|-------------|
| **1. Enterprise AI Architecture** | How to design AI systems that scale in large orgs. TOGAF + AI integration. Governance frameworks. | Your unique combo. Nobody else has both credentials. |
| **2. Agentic AI in Practice** | Real lessons from building multi-agent systems. RAG pitfalls. LangGraph/CrewAI/MCP in production. | You're actively learning + building. Authentic content. |
| **3. AI Transformation Leadership** | Pain points of AI adoption. Team building. ROI justification. Culture change. | Decision-makers read this. Attracts consulting leads. |
| **4. AI Tools & Techniques** | Practical how-tos. Tool comparisons. Quick wins. | Drives engagement. Establishes technical credibility. |

**Tone:** Thoughtful, experienced, practical. Share lessons (including failures). Ask questions that make people think. Never salesy. Never "AI is going to change everything" generic hype.

### 10B. Brand Voice Guide (`brand-voice.md`)

```markdown
# Brand Voice: Taimoor Alam — AI Architect

## Voice Attributes
- Thoughtful over reactive
- Practical over theoretical
- Honest over promotional
- Questioning over declarative
- Specific over vague

## Do
- Share concrete examples and numbers
- Admit what you don't know
- Ask questions that invite discussion
- Connect enterprise problems to AI solutions
- Reference frameworks (TOGAF, ADM) naturally, not as name-drops
- Use "In my experience..." or "What I've seen..." for credibility
- End posts with a genuine question

## Don't
- Use empty buzzwords ("game-changer", "revolutionary", "unlock potential")
- Hashtag spam (max 3 hashtags, only if relevant)
- Self-promote without providing value first
- Post "I'm excited to announce..." templates
- Agree with influencers just to be seen
- Use corporate jargon without explaining it
- Write comments shorter than 2 sentences

## Comment Templates (starting points, always customize)
- Insight pattern: "This resonates. In [context], we found that [specific lesson]. What's been your experience with [related aspect]?"
- Contrarian pattern: "Interesting perspective. I'd push back slightly on [point] — in enterprise settings, [nuance]. Though I agree that [common ground]."
- Question pattern: "Curious about your take on [related challenge]. We're seeing [observation] and wondering if others are hitting the same wall."
- Bridge pattern: "This connects to something in enterprise architecture — [TOGAF/framework concept] addresses exactly this pattern. The key is [practical takeaway]."

## Post Structure
- Hook: 1-2 sentences that state a provocative observation or question
- Body: 3-5 short paragraphs with specific examples
- Close: Genuine question or call for others' experiences
- Length: 150-300 words (LinkedIn sweet spot for engagement)
- Format: Short paragraphs, line breaks for readability

## Engagement Cadence Ramp-Up
Week 1-2:   2 thoughtful comments/day on others' posts
Week 3-4:   3 comments/day + 1 original post/week
Month 2:    3 comments/day + 2 posts/week
Month 3+:   4 comments/day + 2 posts/week + 1 article/month
```

### 10C. Competitive Intelligence

Track competitor AI architects/consultants to find positioning gaps.

**What to track:**
- Who else posts about AI architecture in enterprise?
- What topics do they cover vs. ignore?
- Where is their content weak (generic, no enterprise depth, no governance)?
- What engagement do they get? On what topics?

**New collection: `competitor_profiles`**
```json
{
  "_id": "ObjectId",
  "name": "string",
  "headline": "string",
  "profile_url": "string",
  "topics_covered": ["RAG", "AI strategy"],
  "topics_missing": ["TOGAF", "governance", "multi-agent"],
  "avg_engagement": 85,
  "posting_frequency": "3x/week",
  "positioning": "string (how they describe themselves)",
  "weaknesses": ["no enterprise architecture background", "only theoretical"],
  "first_tracked_at": "ISODate",
  "last_analyzed_at": "ISODate",
  "notes": "string"
}
```

**Detection:** During scraping, if the same author appears 5+ times in 14 days posting on your target topics AND has "AI architect" or similar in their headline, auto-add to `competitor_profiles` for review.

**Weekly competitive brief** (added to Saturday deep dive):
- Who posted the most about your topics?
- What topics are oversaturated vs. underserved?
- Where can you differentiate?

---

## 11. Freelance & Consulting Lead Qualification

### Scoring Rubric (different from job scoring)

Freelance/consulting leads need different criteria than full-time jobs:

```json
{
  "budget_signals": {
    "weight": 0.25,
    "indicators": [
      "mentions budget range",
      "funded startup (Crunchbase signal)",
      "enterprise company (high ability to pay)",
      "mentions 'consultant' not 'intern'",
      "project scope suggests >$10K"
    ]
  },
  "urgency_signals": {
    "weight": 0.20,
    "indicators": [
      "deadline mentioned",
      "ASAP language",
      "project already started, need help",
      "regulatory pressure",
      "board/exec mandate"
    ]
  },
  "scope_fit": {
    "weight": 0.25,
    "indicators": [
      "AI architecture design (perfect fit)",
      "RAG/agent implementation (strong fit)",
      "AI strategy advisory (strong fit)",
      "general ML engineering (moderate fit)",
      "data engineering only (weak fit)"
    ]
  },
  "client_sophistication": {
    "weight": 0.15,
    "indicators": [
      "has existing tech team (good, need architect not builder)",
      "understands AI terminology (can have real conversations)",
      "has tried and failed (appreciates expertise)",
      "first-time AI (needs more education, longer sales cycle)"
    ]
  },
  "engagement_ease": {
    "weight": 0.15,
    "indicators": [
      "posted publicly (can reply openly)",
      "tagged location compatible (timezone)",
      "responded to others' comments (active poster)",
      "remote-friendly language"
    ]
  }
}
```

### Freelance Lead Pipeline

```
Scrape detects freelance signal → Score with rubric above →
If score ≥ 7: tag "hot-lead" → generate personalized approach draft →
Surface in Telegram briefing under "🔥 Consulting Leads" section →
Track in new collection: lead_pipeline
```

### Collection: `lead_pipeline`
```json
{
  "_id": "ObjectId",
  "source_intel_id": "ObjectId (ref to linkedin_intel)",
  "type": "freelance|consulting|fractional|advisory",
  "company": "string",
  "contact": { "name": "string", "headline": "string", "profile_url": "string" },
  "project_description": "string",
  "budget_estimate": "string (inferred range)",
  "urgency": "high|medium|low",
  "scope_fit_score": 8,
  "overall_score": 8.2,
  "scoring_breakdown": {},
  "approach_draft": "string (personalized outreach message)",
  "status": "identified|approached|conversation|proposal|won|lost|stale",
  "status_history": [{"status": "string", "at": "ISODate", "notes": "string"}],
  "next_action": "string",
  "next_action_date": "ISODate",
  "value_estimate": "string ($5K-$15K)",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

---

## 12. Outreach & Conversion Strategy

### From Engagement to Leads

The plan currently generates draft comments, but stops there. This section covers the full funnel:

```
Stage 1: VISIBILITY (Automated)
  └─ Comment on relevant posts (2-4/day)
  └─ React to pain-point posts (adds to their notification)
  └─ Post original content (2/week)

Stage 2: CREDIBILITY (Semi-automated)
  └─ Share detailed technical insights in comments
  └─ Reference specific experience/frameworks
  └─ Post case-study-style content (monthly)
  └─ System suggests: "This person posted 3x about RAG issues.
     You've commented twice. Suggest connecting with personalized note."

Stage 3: CONNECTION (Manual, system assists)
  └─ System generates connection request drafts:
     "Hi {name}, I've been following your posts on {topic}. Your point about
     {specific_reference} mirrors what I've seen in enterprise AI adoption.
     Would love to connect and exchange notes."
  └─ Track in lead_pipeline: status → "approached"

Stage 4: CONVERSATION (Manual, system assists)
  └─ System prepares talking points based on their post history
  └─ System pulls relevant STAR records from your master-cv
  └─ Template DM after connection accepted:
     "Thanks for connecting! Saw your post about {topic}. I recently
     {relevant_experience}. Happy to share what worked/didn't if useful."

Stage 5: OPPORTUNITY (Manual)
  └─ Consulting discovery call
  └─ Proposal generation (could use existing Layer 6 CV/cover letter pipeline)
  └─ Track outcome in lead_pipeline
```

### Outreach Draft Templates (stored in `brand-voice.md`)

```markdown
## Connection Request Templates

### After commenting on their posts 2+ times:
"Hi {name}, enjoyed your recent post on {topic}. Your insight about
{specific_point} is spot on — I've been navigating similar challenges
from the enterprise architecture side. Would love to connect."

### Cold but high-relevance:
"Hi {name}, your work on {their_area} caught my attention. I'm focused
on bridging enterprise architecture (TOGAF) with AI implementation —
seems like we're tackling related problems from different angles."

### Freelance lead response:
"Hi {name}, saw your post about needing {project_type}. This is exactly
what I specialize in — designing {relevant_capability} for enterprise
teams. Happy to share some thoughts on approach if helpful."

## Follow-up DM Templates

### After connection accepted:
"Thanks for connecting, {name}! Your perspective on {topic} resonates —
especially the point about {specific}. I recently {relevant_experience}.
Would you be open to a 15-min call to exchange notes?"

### Value-first follow-up (no ask):
"Saw this article and thought of your post about {topic}: {link}.
It aligns with what you were describing about {challenge}."
```

---

## 13. Geo & Compensation Intelligence

### Salary/Rate Tracking

Enrich `linkedin_intel` items with compensation signals when detected:

```json
// Additional fields on linkedin_intel documents where type=job|freelance
{
  "compensation": {
    "salary_min": null,
    "salary_max": null,
    "currency": "USD",
    "type": "annual|monthly|hourly|project",
    "source": "posted|inferred|glassdoor",
    "confidence": "high|medium|low"
  },
  "location_detail": {
    "raw": "string",
    "country": "string",
    "region": "UAE|UK|EU|US|APAC|Remote",
    "remote_policy": "fully_remote|hybrid|onsite|not_specified",
    "timezone_compatible": true
  }
}
```

### Geographic Demand Heatmap

Weekly aggregation stored in `linkedin_trends`:

```json
{
  "period": "weekly",
  "date": "ISODate",
  "geo_demand": [
    { "region": "UAE", "jobs": 12, "avg_relevance": 7.2, "remote_pct": 30 },
    { "region": "UK", "jobs": 28, "avg_relevance": 6.8, "remote_pct": 55 },
    { "region": "EU", "jobs": 34, "avg_relevance": 6.5, "remote_pct": 45 },
    { "region": "US", "jobs": 89, "avg_relevance": 6.9, "remote_pct": 65 },
    { "region": "Remote", "jobs": 43, "avg_relevance": 7.5, "remote_pct": 100 }
  ],
  "compensation_ranges": [
    { "role": "AI Architect", "p25": 150000, "median": 185000, "p75": 220000, "currency": "USD", "sample_size": 15 },
    { "role": "Head of AI", "p25": 200000, "median": 250000, "p75": 300000, "currency": "USD", "sample_size": 8 }
  ],
  "freelance_rates": [
    { "type": "AI consulting", "low": 150, "median": 225, "high": 350, "unit": "hour", "currency": "USD" }
  ]
}
```

### Dashboard Widget: `/dashboard/analytics/geo`

```
┌──── Geographic Demand ─────────────────────────────────────┐
│                                                             │
│  Remote  ████████████████████████ 43 jobs (avg 7.5/10)    │
│  US      ████████████████████░░░ 89 jobs (avg 6.9/10)     │
│  EU      ████████████████░░░░░░ 34 jobs (avg 6.5/10)      │
│  UK      ██████████████░░░░░░░░ 28 jobs (avg 6.8/10)      │
│  UAE     ███████░░░░░░░░░░░░░░░ 12 jobs (avg 7.2/10)     │
│                                                             │
│  Comp. ranges (AI Architect): $150K — $185K — $220K        │
│  Freelance rates: $150-$350/hr (median $225)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 14. Telegram Interactive Actions

### Two-Way Telegram Commands

The morning briefing should be actionable. When you read it on your phone, you should be able to respond with commands:

```
User sends to bot:
  /apply 3          → Push item #3 into existing 7-layer job pipeline
  /draft 2          → Generate draft comment for item #2
  /save 1           → Bookmark item for later review
  /detail 4         → Get full content of item #4
  /skip 5           → Mark item as skipped
  /lead 3           → Move item to lead_pipeline as consulting lead
  /stats             → Quick stats: items today, API usage, cookie health
  /search "keyword" → Trigger manual single-keyword search (uses 5 API calls)
  /pause             → Pause all scraping for 24h (vacation, caution, etc.)
  /resume            → Resume scraping
  /trends            → Get this week's trending keywords
  /next              → Show next unread high-relevance items
```

### Implementation

In the OpenClaw skill, handle incoming Telegram messages:

```python
# telegram_commands.py

COMMANDS = {
    "/apply": handle_apply,      # Push to job pipeline
    "/draft": handle_draft,      # Generate draft for item
    "/save": handle_save,        # Bookmark item
    "/detail": handle_detail,    # Show full content
    "/skip": handle_skip,        # Skip item
    "/lead": handle_lead,        # Move to lead pipeline
    "/stats": handle_stats,      # System stats
    "/search": handle_search,    # Manual search
    "/pause": handle_pause,      # Pause scraping
    "/resume": handle_resume,    # Resume scraping
    "/trends": handle_trends,    # Weekly trends
    "/next": handle_next,        # Next unread items
}

def handle_apply(item_number: int):
    """Push scraped job into existing 7-layer LangGraph pipeline."""
    item = db.linkedin_intel.find_one({"_briefing_index": item_number, "scraped_at": {"$gte": today}})
    if item["type"] not in ["job", "freelance"]:
        return "This item isn't a job listing. Use /lead for consulting leads."
    # Convert to format expected by existing pipeline
    job_doc = convert_intel_to_job_doc(item)
    db.jobs.insert_one(job_doc)
    # Trigger pipeline via runner service API
    requests.post(f"{RUNNER_URL}/api/operations/run", json={"job_id": job_doc["job_id"]})
    return f"✅ Pushed to pipeline: {item['title']} @ {item['company']}"
```

### Briefing Format Update (with action numbers)

```
🌅 Morning Intelligence — Feb 17

📊 Last Night: 47 new (12 jobs, 22 posts, 8 pain points, 5 opps)

🏢 Top Jobs:
[1] 🎯 9/10 Head of AI @ TechCorp — Remote, $200-250K
    /apply 1 · /detail 1 · /skip 1
[2] 🎯 8/10 AI Architect @ FinCo — UK Hybrid
    /apply 2 · /detail 2 · /skip 2

💼 Consulting Leads:
[3] 🔥 8/10 "Need AI architect for agent system" — StartupX
    Budget signals: Series B, $15M raised
    /lead 3 · /draft 3 · /detail 3

💬 Engage These:
[4] 💡 @VP_Eng: "Our RAG pipeline breaks at scale..."
    Draft: "This resonates — hybrid retrieval was the key for us..."
    /draft 4 · /detail 4 · /skip 4
[5] 💡 @CTO_BigCo: "Building an AI governance framework..."
    Draft: "The TOGAF ADM Phase B maps well to AI governance..."
    /draft 5 · /detail 5 · /skip 5

📈 Trends: "AI governance" (+62%) | "LLM costs" (NEW)
⚙️ 48/150 API | Cookie ✓ | Errors: 0

Commands: /stats /trends /next /pause
```

---

## 15. Job Pipeline Integration

### Bridge: linkedin_intel → existing jobs collection

When a high-relevance job is found in scraping and the user wants to process it (via dashboard "Add to Pipeline" or Telegram `/apply`), convert and push:

```python
def convert_intel_to_job_doc(intel_item: dict) -> dict:
    """Convert linkedin_intel document to format expected by existing job pipeline."""
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

This feeds directly into the existing 7-layer LangGraph pipeline:
1. Layer 1-4: JD extraction → pain point mining → company research → opportunity mapping
2. Layer 5: People intelligence
3. Layer 6: CV + cover letter + outreach generation
4. Layer 7: Dossier + interview prep

### Dashboard "Add to Pipeline" button

On `/dashboard/opportunities`, each job item gets an "Add to Pipeline" button that:
1. Converts intel doc to job doc
2. Inserts into `jobs` collection
3. Triggers pipeline run via runner service API
4. Updates intel doc: `acted_on: true, acted_action: "pipeline"`
5. Shows confirmation toast

---

## 16. Edge & Niche Opportunity Detection

### Heuristic Engine

Beyond keyword matching, the system should proactively find non-obvious opportunities using compound signals:

```python
EDGE_OPPORTUNITY_RULES = [
    {
        "name": "funded_and_hiring_ai",
        "description": "Company just raised funding AND is hiring for AI roles",
        "signals": ["series_a", "series_b", "series_c", "funding_round"],
        "cross_reference": "AI|ML|architect|LLM in job title",
        "score_boost": +2,
        "reasoning": "Fresh funding = budget for senior hires"
    },
    {
        "name": "togaf_ai_crossover",
        "description": "Mentions both enterprise architecture AND AI",
        "signals": ["enterprise architecture", "TOGAF", "ADM"],
        "cross_reference": "AI|ML|digital transformation",
        "score_boost": +3,
        "reasoning": "Your TOGAF+AI combo is extremely rare — almost zero competition"
    },
    {
        "name": "industry_not_yet_ai_mature",
        "description": "Traditional industry starting AI journey",
        "signals": ["first AI hire", "AI transformation", "digital transformation"],
        "industries": ["manufacturing", "logistics", "healthcare", "government", "energy", "construction"],
        "score_boost": +2,
        "reasoning": "Less competition, they need guidance not just coding"
    },
    {
        "name": "geographic_arbitrage",
        "description": "US/UK salary but remote-friendly or UAE-based",
        "signals": ["remote", "anywhere"],
        "compensation_threshold": 180000,
        "score_boost": +1,
        "reasoning": "Premium compensation accessible from your timezone"
    },
    {
        "name": "pain_without_solution",
        "description": "Post describing AI pain with no responses offering help",
        "signals": ["struggling", "failed", "help", "looking for"],
        "cross_reference": "comments < 5 AND no consultant replies",
        "score_boost": +2,
        "reasoning": "Uncontested lead — be first to offer value"
    },
    {
        "name": "governance_vacuum",
        "description": "Company hiring AI engineers but no AI governance/architect role",
        "signals": ["hiring ML engineers", "AI team growing"],
        "cross_reference": "no 'architect' or 'governance' in their other postings",
        "score_boost": +2,
        "reasoning": "They'll need governance soon — position yourself early"
    },
    {
        "name": "multi_agent_early_adopter",
        "description": "Company exploring multi-agent or agentic AI",
        "signals": ["multi-agent", "agentic", "AI agents", "crew", "swarm"],
        "cross_reference": "enterprise OR large OR fortune 500",
        "score_boost": +2,
        "reasoning": "Cutting edge + enterprise = premium rates"
    }
]
```

### Implementation

During evening analysis, after basic classification, run edge detection:

```python
def detect_edge_opportunities(item: dict) -> list[dict]:
    """Check item against edge opportunity rules."""
    matched_rules = []
    for rule in EDGE_OPPORTUNITY_RULES:
        if matches_signals(item, rule["signals"]):
            if "cross_reference" in rule and matches_cross_reference(item, rule["cross_reference"]):
                matched_rules.append({
                    "rule": rule["name"],
                    "boost": rule["score_boost"],
                    "reasoning": rule["reasoning"]
                })
    return matched_rules
```

Store edge matches on the intel document:
```json
{
  "edge_opportunities": [
    { "rule": "togaf_ai_crossover", "boost": 3, "reasoning": "..." },
    { "rule": "pain_without_solution", "boost": 2, "reasoning": "..." }
  ],
  "adjusted_relevance_score": 12  // original 7 + boosts
}
```

Tag as `niche-opportunity` in classification tags. Surface prominently in Telegram briefing and dashboard.

---

## 17. Expanded Input Sources

### Full Source Inventory

| Source | Type | Auth | Cost | Frequency | Priority |
|--------|------|------|------|-----------|----------|
| **LinkedIn Jobs** | Voyager API | Cookie | Free | Daily | NOW |
| **LinkedIn Posts** | Voyager API | Cookie | Free | Daily | NOW |
| **Reddit** | PRAW (OAuth) | API key | Free | Daily | Phase 7 |
| **HN Who's Hiring** | Algolia API | None | Free | Monthly | Phase 7 |
| **RemoteOK** | JSON API | None | Free | 2x/week | Phase 7 |
| **WeWorkRemotely** | RSS | None | Free | 2x/week | Phase 7 |
| **Twitter/X** | API v2 | Bearer token | $100/mo (Basic) | Daily | Future |
| **AngelList/Wellfound** | Web scrape | Session | Free | Weekly | Future |
| **Toptal** | Job board scrape | None (public) | Free | Weekly | Future |
| **Gun.io** | Job board RSS | None | Free | Weekly | Future |
| **Glassdoor** | API/scrape | Session | Free | Weekly | Future |
| **Blind** | App (no API) | Manual | Free | Monitor only | Future |
| **ai-jobs.net** | RSS/scrape | None | Free | 2x/week | Phase 7 |
| **MLjobs.ai** | RSS/scrape | None | Free | 2x/week | Phase 7 |
| **LinkedIn Newsletters** | Via LinkedIn scrape | Cookie | Free | When posted | Future |
| **Substack feeds** | RSS | None | Free | Daily | Future |
| **TechCrunch AI** | RSS | None | Free | Daily | Phase 7 |
| **Simon Willison** | RSS | None | Free | Daily | Phase 7 |
| **MIT Tech Review** | RSS | None | Free | Weekly | Future |
| **Crunchbase** | API | API key | $29/mo | Weekly | Future |

### RSS Feed URLs (for n8n RSS Trigger)

```json
{
  "rss_feeds": [
    { "name": "WeWorkRemotely", "url": "https://weworkremotely.com/categories/remote-programming-jobs.rss", "frequency": "2x/week" },
    { "name": "RemoteOK RSS", "url": "https://remoteok.com/remote-ai-jobs.rss", "frequency": "2x/week" },
    { "name": "ai-jobs.net", "url": "https://ai-jobs.net/feed/", "frequency": "daily" },
    { "name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "frequency": "daily" },
    { "name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "frequency": "daily" },
    { "name": "The Batch (Andrew Ng)", "url": "https://www.deeplearning.ai/the-batch/feed/", "frequency": "weekly" },
    { "name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "frequency": "weekly" }
  ]
}
```

### Source Priority for n8n Workflow

Phase 7 implementation order:
1. RSS feeds (easiest, no auth, n8n native node)
2. Reddit (PRAW, well-documented)
3. HN Who's Hiring (simple API, monthly)
4. RemoteOK (free JSON, no auth)
5. Specialized AI job boards (scrape with existing tools)
6. Twitter/X (expensive API, defer unless needed)

---

## 18. Learning Reprioritization Engine

### Concept: Market-Driven Learning

The intersection engine (Section 9B) not only suggests content but should also suggest **reordering your study plan** based on market signals.

```python
def suggest_learning_reprioritization(trends, checklist_progress):
    """Suggest course order changes based on market demand."""
    suggestions = []

    for course in get_upcoming_courses(checklist_progress):
        # How much is this topic trending?
        trend_score = get_trend_score_for_course(course, trends)
        # How many jobs mention this topic?
        job_demand = get_job_demand_for_course(course, trends)
        # How much competition exists (how many people posting about it)?
        competition = get_competition_for_course(course, trends)

        market_urgency = (trend_score * 0.4) + (job_demand * 0.4) - (competition * 0.2)

        if market_urgency > current_course_priority(course):
            suggestions.append({
                "course": course,
                "current_position": course["scheduled_week"],
                "suggested_position": "move earlier",
                "market_urgency": market_urgency,
                "reasoning": f"'{course['name']}' is trending +{trend_score}% with {job_demand} job mentions. Low competition ({competition} active posters). Learning this now = first-mover advantage in content."
            })

    return sorted(suggestions, key=lambda x: x["market_urgency"], reverse=True)[:3]
```

### Dashboard Integration

On the content marketing dashboard, under the intersection engine, show:

```
📚 Learning Reprioritization Suggestions:
1. Move Course 6 (AI Governance) from Week 6 → NOW
   Reason: "AI governance" trending +62%, 5 job mentions, only 2 active posters
   [Accept & Update Plan] [Dismiss]

2. Move Course 3 (RAG) sections on production earlier
   Reason: "RAG production" pain point posts +15%, 8 jobs require RAG experience
   [Accept & Update Plan] [Dismiss]
```

### Telegram weekly suggestion

Every Monday morning briefing includes a learning priority section:

```
📚 This Week's Learning Priority:
Based on market signals, consider focusing on:
• AI Governance (Course 6) — demand surging +62%
• RAG production patterns (Course 3, Module 4) — 8 active job reqs
Your current plan has these in weeks 6 and 4 respectively.
```

---

## 19. Reddit Deep Dive (Expanded)

### Reddit-Specific Schema Fields

Extend `linkedin_intel` documents for Reddit items:

```json
{
  "source": "reddit",
  "reddit_meta": {
    "subreddit": "string",
    "flair": "string",
    "upvote_ratio": 0.95,
    "score": 234,
    "num_comments": 47,
    "is_self_post": true,
    "author_karma": 12500,
    "created_utc": "ISODate",
    "permalink": "string"
  }
}
```

### Reddit Search Queries by Subreddit

```python
REDDIT_SEARCHES = {
    "r/MachineLearning": {
        "queries": ["hiring AI architect", "looking for ML lead", "AI strategy"],
        "flair_filter": ["Job", "Discussion"],
        "min_score": 10,
        "frequency": "daily"
    },
    "r/forhire": {
        "queries": ["AI", "ML", "LLM", "architect", "consultant"],
        "flair_filter": ["Hiring"],
        "min_score": 5,
        "frequency": "daily"
    },
    "r/MLjobs": {
        "queries": None,  # Scrape all, it's a job board
        "min_score": 1,
        "frequency": "daily"
    },
    "r/RemoteJobs": {
        "queries": ["AI", "ML", "architect", "engineering manager"],
        "min_score": 5,
        "frequency": "2x/week"
    },
    "r/consulting": {
        "queries": ["AI", "technology", "digital transformation"],
        "min_score": 10,
        "frequency": "weekly"
    },
    "r/ExperiencedDevs": {
        "queries": ["AI architect", "principal engineer AI", "staff engineer ML"],
        "min_score": 20,
        "frequency": "weekly"
    },
    "r/LocalLLaMA": {
        "queries": ["enterprise", "production", "architect"],
        "min_score": 15,
        "frequency": "weekly"
    },
    "r/cscareerquestions": {
        "queries": ["AI architect salary", "ML lead", "AI career"],
        "min_score": 20,
        "frequency": "weekly"
    },
    "r/datascience": {
        "queries": ["architect", "lead", "enterprise AI"],
        "min_score": 15,
        "frequency": "weekly"
    }
}
```

### Reddit Engagement Strategy

Unlike LinkedIn (professional tone), Reddit requires different engagement:
- **r/forhire**: Direct, concise proposals. Include relevant experience and rate range
- **r/MachineLearning**: Technical depth, no self-promotion, share knowledge
- **r/ExperiencedDevs**: Honest, experienced perspective. Seniority is expected
- **Never**: self-promote in discussion subreddits — contribute value only

Draft generation for Reddit should use a different prompt template than LinkedIn.

### Reddit Cron Schedule

```
Daily (4 AM):     r/MachineLearning, r/forhire, r/MLjobs
2x/week (4 AM):   r/RemoteJobs, r/datascience
Weekly (Sat 11 AM): r/consulting, r/ExperiencedDevs, r/LocalLLaMA, r/cscareerquestions
```

---

## 20. Remotion Video Content System (Expanded)

### Video Content Templates

#### Template 1: Quick Tip (15-30 seconds)
```
Scene 1 (0-3s):  Hook text on gradient background + sound effect
                  "Most people get RAG wrong"
Scene 2 (3-18s): 3-4 bullet points appearing one by one
                  Problem → Why it happens → The fix → Result
Scene 3 (18-25s): Summary callout box
                  "Key takeaway: [one sentence]"
Scene 4 (25-30s): CTA + branding
                  "Follow for more AI architecture tips"
                  Name + title overlay
```

#### Template 2: AI Myth Buster (30-45 seconds)
```
Scene 1 (0-5s):  "MYTH:" in red with myth text
Scene 2 (5-10s): "REALITY:" in green with correction
Scene 3 (10-35s): 3 supporting points with icons/animation
Scene 4 (35-45s): "What's a myth YOU keep hearing?" + CTA
```

#### Template 3: Tool Demo (45-60 seconds)
```
Scene 1 (0-5s):   Tool name + "in 60 seconds"
Scene 2 (5-15s):  What it does (text + simple animation)
Scene 3 (15-45s): Step-by-step walkthrough (code snippets or screen)
Scene 4 (45-55s): Result / output shown
Scene 5 (55-60s): "Link in bio" + CTA
```

#### Template 4: Weekly Roundup (60 seconds)
```
Scene 1 (0-5s):   "This Week in Enterprise AI"
Scene 2-6 (5-50s): 5 items, 9s each:
                    Trending topic card → stat → one-line insight
Scene 7 (50-60s):  "What are you seeing? Comment below" + CTA
```

### Script JSON Structure

```json
{
  "template": "quick_tip",
  "topic": "RAG chunking strategies",
  "source_intel_ids": ["ObjectId1", "ObjectId2"],
  "source_course": "Course 3, Lesson 3.2",
  "scenes": [
    {
      "scene_number": 1,
      "duration_seconds": 3,
      "type": "hook",
      "text": "Your RAG pipeline is probably chunking wrong",
      "background": "gradient_red_dark",
      "animation": "text_slam"
    },
    {
      "scene_number": 2,
      "duration_seconds": 15,
      "type": "bullets",
      "items": [
        "Problem: Fixed-size chunks break semantic meaning",
        "Why: Tokens ≠ meaning boundaries",
        "Fix: Use semantic chunking with overlap",
        "Result: 40% improvement in retrieval accuracy"
      ],
      "animation": "fade_in_sequence"
    }
  ],
  "audio": {
    "background_music": "upbeat_tech",
    "voiceover": false
  },
  "format": { "width": 1080, "height": 1920, "fps": 30 },
  "status": "script_ready|rendering|rendered|posted",
  "generated_by": "claude-sonnet",
  "generated_at": "ISODate"
}
```

### Content-to-Video Pipeline (Detailed)

```
1. TRIGGER (automated)
   ├─ User completes concept → "Quick Tip" candidate
   ├─ Trending topic detected → "Weekly Roundup" candidate
   ├─ Pain point post with >50 likes → "Myth Buster" candidate
   └─ Manual: user clicks "Generate Video" on dashboard

2. SCRIPT GENERATION (Claude Sonnet)
   ├─ Input: source material + template + brand voice
   ├─ Output: JSON script matching template structure
   ├─ Store in: video_content collection, status: "script_draft"
   └─ Surface in: dashboard + Telegram

3. USER REVIEW
   ├─ Dashboard: edit script text, reorder scenes, change template
   ├─ Approve: status → "script_approved"
   └─ Reject: regenerate or discard

4. REMOTION COMPOSITION (Claude Code)
   ├─ Generate React component from script JSON
   ├─ Apply template styling + animations
   ├─ Preview in browser: localhost:3000
   └─ Status → "composition_ready"

5. RENDER
   ├─ Local: npx remotion render (development)
   ├─ Production: @remotion/renderer server-side
   ├─ Output: MP4 at 1080x1920, 30fps
   └─ Status → "rendered"

6. PUBLISH (manual for now)
   ├─ Download from dashboard
   ├─ Upload to TikTok / Instagram Reels / YouTube Shorts
   ├─ Enter post URL for tracking
   └─ Status → "posted"

7. TRACK
   ├─ Manual: enter views, likes, comments after 24h and 7d
   ├─ Store in content_performance collection
   └─ Feed back into trending/topic analysis
```

### Video Collection Schema

```json
{
  "_id": "ObjectId",
  "template": "quick_tip|myth_buster|tool_demo|weekly_roundup",
  "topic": "string",
  "content_pillar": "enterprise_ai_arch|agentic_ai|ai_leadership|tools_techniques",
  "source_intel_ids": ["ObjectId"],
  "source_course": "string",
  "script": {}, // Full JSON script as above
  "composition_path": "string (path to .tsx file)",
  "render_path": "string (path to .mp4)",
  "render_status": "pending|rendering|complete|failed",
  "render_progress": 0.72,
  "platforms": {
    "tiktok": { "url": null, "posted_at": null },
    "instagram_reels": { "url": null, "posted_at": null },
    "youtube_shorts": { "url": null, "posted_at": null }
  },
  "performance": {
    "tiktok": { "views": 0, "likes": 0, "comments": 0, "shares": 0, "captured_at": null },
    "instagram": { "views": 0, "likes": 0, "comments": 0, "captured_at": null }
  },
  "status": "idea|script_draft|script_approved|composition_ready|rendered|posted",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

### Remotion Project Structure

```
/Users/ala0001t/pers/projects/job-search/video-content/
├── src/
│   ├── Root.tsx                    # Entry point with all compositions
│   ├── templates/
│   │   ├── QuickTip.tsx            # 15-30s tip template
│   │   ├── MythBuster.tsx          # 30-45s myth/reality template
│   │   ├── ToolDemo.tsx            # 45-60s demo template
│   │   └── WeeklyRoundup.tsx       # 60s roundup template
│   ├── components/
│   │   ├── TextSlam.tsx            # Animated text entrance
│   │   ├── BulletList.tsx          # Sequential bullet reveal
│   │   ├── StatCard.tsx            # Number/stat callout
│   │   ├── CodeSnippet.tsx         # Syntax-highlighted code
│   │   ├── ProgressBar.tsx         # Animated progress bar
│   │   ├── Branding.tsx            # Name + title + CTA overlay
│   │   └── Background.tsx          # Gradient/pattern backgrounds
│   ├── styles/
│   │   └── theme.ts               # Colors, fonts, spacing
│   └── data/
│       └── scripts/                # Generated JSON scripts
├── public/
│   ├── fonts/                      # Brand fonts
│   ├── audio/                      # Background music tracks
│   └── images/                     # Logos, icons
├── out/                            # Rendered MP4s
├── remotion.config.ts
├── package.json
└── .claude/skills/remotion/        # Remotion Claude Code skills
```

### Publishing Cadence

```
Week 1-2: 1 video/week (Quick Tips only, build workflow)
Week 3-4: 2 videos/week (Quick Tips + Myth Busters)
Month 2:  3 videos/week (add Tool Demos)
Month 3+: 3 videos/week + 1 Weekly Roundup (Friday)
```

---

## 21. VPS Monitoring & Health Alerts

### Docker Health Checks

Add to docker-compose.yml for each service:

```yaml
openclaw:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:18789/health"]
    interval: 60s
    timeout: 10s
    retries: 3
    start_period: 30s
```

### System Monitor Script

New cron on VPS (outside Docker): `/root/n8n-prod/scripts/health-monitor.sh`

```bash
#!/bin/bash
# Runs every 5 minutes via crontab

ALERT_ENDPOINT="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
CHAT_ID="${TELEGRAM_CHAT_ID}"

# Check disk usage
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 85 ]; then
    curl -s -X POST "$ALERT_ENDPOINT" -d "chat_id=$CHAT_ID&text=⚠️ VPS disk usage: ${DISK_USAGE}%"
fi

# Check RAM usage
RAM_USED=$(free | awk '/Mem:/ {printf("%.0f", $3/$2 * 100)}')
if [ "$RAM_USED" -gt 90 ]; then
    curl -s -X POST "$ALERT_ENDPOINT" -d "chat_id=$CHAT_ID&text=⚠️ VPS RAM usage: ${RAM_USED}%"
fi

# Check container health
for CONTAINER in openclaw n8n-main n8n-worker n8n-postgres n8n-redis n8n-traefik; do
    STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null)
    if [ "$STATUS" != "running" ]; then
        curl -s -X POST "$ALERT_ENDPOINT" -d "chat_id=$CHAT_ID&text=🚨 Container DOWN: $CONTAINER (status: $STATUS)"
    fi
done

# Check if Ollama is responding (when installed)
if command -v ollama &> /dev/null; then
    if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        curl -s -X POST "$ALERT_ENDPOINT" -d "chat_id=$CHAT_ID&text=⚠️ Ollama not responding"
    fi
fi
```

### Crontab entry

```
*/5 * * * * /root/n8n-prod/scripts/health-monitor.sh
```

### Dashboard Health Widget

Add to `/dashboard` bottom section:

```
┌──── System Health ─────────────────────────────────────────┐
│ VPS:      ● Online | CPU: 23% | RAM: 67% | Disk: 52%      │
│ OpenClaw: ● Running | Uptime: 12d 4h                       │
│ n8n:      ● Running | Workflows active: 3                  │
│ Ollama:   ● Running | Model: qwen2.5:7b loaded             │
│ MongoDB:  ● Connected | Collections: 8 | Docs: 2,341      │
│ Cookie:   ● Valid | Expires: ~Apr 2026                     │
│ Last scrape: 3h ago | Next: 6h 12m                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 22. Data Retention & Archival

### Retention Policy

| Collection | High-relevance (≥5) | Low-relevance (<5) | Archival |
|------------|--------------------|--------------------|----------|
| linkedin_intel | Keep indefinitely | TTL: 90 days | Monthly export |
| linkedin_sessions | Keep 1 year | N/A | Quarterly export |
| draft_content | Keep indefinitely | TTL: 30 days (skipped) | Monthly export |
| content_performance | Keep indefinitely | N/A | N/A |
| tracked_authors | Keep indefinitely | TTL: 180 days (inactive) | N/A |
| lead_pipeline | Keep indefinitely | N/A | N/A |
| linkedin_trends | Keep indefinitely | N/A | N/A |
| competitor_profiles | Keep indefinitely | N/A | N/A |
| video_content | Keep indefinitely | N/A | N/A |

### Monthly Export to Google Sheets

Reuse existing Google Drive/Sheets integration from the job-search pipeline.

Script: `scripts/monthly_export.py` (cron: `0 6 1 * *` — 1st of month)

```python
def monthly_export():
    """Export last month's intel data to Google Sheets for manual review."""
    last_month = get_last_month_range()

    # Export high-value items
    high_value = db.linkedin_intel.find({
        "scraped_at": {"$gte": last_month["start"], "$lt": last_month["end"]},
        "relevance_score": {"$gte": 7}
    })
    export_to_sheets(high_value, sheet_name=f"Intel {last_month['label']}")

    # Export trends summary
    trends = db.linkedin_trends.find({"period": "weekly", "date": {"$gte": last_month["start"]}})
    export_to_sheets(trends, sheet_name=f"Trends {last_month['label']}")

    # Export lead pipeline status
    leads = db.lead_pipeline.find({"created_at": {"$gte": last_month["start"]}})
    export_to_sheets(leads, sheet_name=f"Leads {last_month['label']}")

    # Export content performance
    content = db.content_performance.find({"posted_at": {"$gte": last_month["start"]}})
    export_to_sheets(content, sheet_name=f"Content {last_month['label']}")
```

### Backup Strategy

```bash
# Weekly MongoDB dump (cron: 0 2 * * 0 — Sunday 2 AM)
mongodump --uri="$MONGODB_URI" --db=job_search --out=/root/backups/mongo/$(date +%Y%m%d)
# Keep last 4 backups, delete older
find /root/backups/mongo -maxdepth 1 -mtime +28 -exec rm -rf {} \;
```

---

## 23. Implementation Order (Updated)

| # | Phase | Effort | Priority | Dependencies |
|---|-------|--------|----------|-------------|
| 0 | Cookie auth on VPS | 1 hour | NOW | Browser access |
| 1 | OpenClaw skill + scripts | 2-3 days | HIGH | Phase 0 |
| 2 | Cron schedules | 2 hours | HIGH | Phase 1 |
| 3 | MongoDB collections + indexes (all collections) | 4-6 hours | HIGH | Phase 1 |
| 4 | Telegram briefing + interactive commands | 6-8 hours | HIGH | Phase 1, 3 |
| 5A | Intelligence dashboard | 2-3 days | HIGH | Phase 3 |
| 5B | Content marketing & trending dashboard | 3-5 days | HIGH | Phase 3, 5A |
| 5C | Drafts + analytics dashboards | 2-3 days | MEDIUM | Phase 5A |
| 6 | Draft engine + brand voice | 2-3 days | HIGH | Phase 3 |
| 7 | Job pipeline integration bridge | 4-6 hours | HIGH | Phase 3 |
| 8 | Edge opportunity detection | 1-2 days | MEDIUM | Phase 6 |
| 9 | Freelance lead pipeline + outreach strategy | 2-3 days | MEDIUM | Phase 6, 8 |
| 10 | Competitive intelligence tracker | 1-2 days | MEDIUM | Phase 3 |
| 11 | Geo & compensation intelligence | 1-2 days | MEDIUM | Phase 3 |
| 12 | Learning reprioritization engine | 1 day | MEDIUM | Phase 5B |
| 13 | Reddit + public web expansion (full) | 3-5 days | MEDIUM | Phase 3 |
| 14 | VPS monitoring + health alerts | 3-4 hours | MEDIUM | VPS SSH |
| 15 | Data retention + archival + exports | 4-6 hours | LOW | Phase 3 |
| 16 | Local LLM on VPS | 4-6 hours | MEDIUM | VPS SSH |
| 17 | Remotion video system (full) | 1-2 weeks | LOW | Phase 5B, 6 |
| 18 | Expanded input sources (Twitter, Toptal, etc.) | Ongoing | LOW | Phase 13 |
