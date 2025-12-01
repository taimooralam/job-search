# Automated Job Ingestion System Plan

## Overview

Implement a cron-based job ingestion system that automatically discovers, scores, and ingests jobs from multiple sources into the MongoDB `level-2` collection.

### User Selections
- **Data Source**: JobSpy (free, open-source) for Indeed
- **Additional Source**: Himalayas.app (free API + MCP server) for remote jobs
- **Frequency**: Every 6 hours (4 runs/day)
- **Score Threshold**: 70+ (Tier B+) for auto-ingestion
- **Focus**: Indeed only (via JobSpy) + Himalayas remote jobs

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   AUTOMATED JOB INGESTION                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CRON (every 6 hours: 00:00, 06:00, 12:00, 18:00 UTC)           │
│  │                                                               │
│  ├── Source 1: JobSpy (Indeed)                                  │
│  │   ├── Scrape ~50 jobs per run                                │
│  │   ├── Filter by search terms from config                     │
│  │   └── No rate limiting on Indeed                             │
│  │                                                               │
│  ├── Source 2: Himalayas.app API                                │
│  │   ├── Fetch latest remote jobs                               │
│  │   ├── Filter by keywords/country                             │
│  │   └── Free, legally compliant                                │
│  │                                                               │
│  └── Processing Pipeline                                         │
│      ├── Deduplicate (dedupeKey: company|title|location|source) │
│      ├── Quick Score (gpt-4o-mini, ~$0.001/job)                 │
│      ├── Filter: score >= 70 (Tier B+)                          │
│      └── Insert to MongoDB level-2 collection                   │
│                                                                  │
│  HIMALAYAS MCP SERVER (optional, for Claude Desktop)            │
│  └── https://mcp.himalayas.app/sse                              │
│      └── Tools: search_jobs, get_jobs, search_companies         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Day 1)

#### 1.1 Install Dependencies
```bash
pip install python-jobspy requests
```

Add to `requirements.txt`:
```
python-jobspy>=1.1.62
```

#### 1.2 Create Job Source Abstraction
**File**: `src/services/job_sources/__init__.py`

Create a unified interface for job sources:
```python
class JobSource(ABC):
    @abstractmethod
    def fetch_jobs(self, search_config: dict) -> List[JobData]

    @abstractmethod
    def get_source_name(self) -> str
```

#### 1.3 Implement Indeed Source (JobSpy)
**File**: `src/services/job_sources/indeed_source.py`

```python
from jobspy import scrape_jobs

class IndeedSource(JobSource):
    def fetch_jobs(self, search_config: dict) -> List[JobData]:
        jobs_df = scrape_jobs(
            site_name=["indeed"],
            search_term=search_config["search_term"],
            location=search_config.get("location", ""),
            results_wanted=search_config.get("results_wanted", 50),
            country_indeed=search_config.get("country", "USA"),
        )
        return self._convert_to_job_data(jobs_df)
```

#### 1.4 Implement Himalayas Source
**File**: `src/services/job_sources/himalayas_source.py`

```python
class HimalayasSource(JobSource):
    API_URL = "https://himalayas.app/jobs/api"

    def fetch_jobs(self, search_config: dict) -> List[JobData]:
        response = requests.get(self.API_URL)
        jobs = response.json()
        return self._filter_and_convert(jobs, search_config)
```

### Phase 2: Ingestion Pipeline (Day 1-2)

#### 2.1 Create Cron Ingestion Script
**File**: `scripts/ingest_jobs_cron.py`

```python
"""
Automated job ingestion script - run via cron every 6 hours.
"""
from src.services.job_sources import IndeedSource, HimalayasSource
from src.services.quick_scorer import quick_score_job, derive_tier_from_score
from src.common.database import DatabaseClient

def run_ingestion():
    sources = [IndeedSource(), HimalayasSource()]
    db = get_db()
    collection = db["level-2"]

    stats = {"fetched": 0, "scored": 0, "ingested": 0, "duplicates": 0}

    for source in sources:
        jobs = source.fetch_jobs(SEARCH_CONFIG)
        stats["fetched"] += len(jobs)

        for job in jobs:
            # Deduplication check
            dedupe_key = generate_dedupe_key(job, source.get_source_name())
            if collection.find_one({"dedupeKey": dedupe_key}):
                stats["duplicates"] += 1
                continue

            # Quick score
            score, rationale = quick_score_job(
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description,
            )
            stats["scored"] += 1

            # Filter by threshold
            if score and score >= SCORE_THRESHOLD:
                doc = create_job_document(job, source, score, rationale)
                collection.insert_one(doc)
                stats["ingested"] += 1

    return stats
```

#### 2.2 Create Job Document Schema
Following existing `level-2` schema from `linkedin_scraper.py`:

```python
def create_job_document(job, source, score, rationale):
    return {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "jobUrl": job.url,
        "description": job.description,
        "dedupeKey": generate_dedupe_key(job, source),
        "createdAt": datetime.utcnow(),
        "status": "not processed",
        "source": source.get_source_name(),  # "indeed_auto" or "himalayas_auto"
        "auto_discovered": True,
        "quick_score": score,
        "quick_score_rationale": rationale,
        "tier": derive_tier_from_score(score),
    }
```

### Phase 3: Configuration (Day 2)

#### 3.1 Add Environment Variables
**File**: `.env.example` (update)

```bash
# Automated Job Ingestion
AUTO_INGEST_ENABLED=true
AUTO_INGEST_SCORE_THRESHOLD=70
AUTO_INGEST_RESULTS_PER_SOURCE=50

# Indeed Search Configuration
INDEED_SEARCH_TERMS=engineering manager,staff engineer,technical lead
INDEED_LOCATIONS=Remote,San Francisco,New York
INDEED_COUNTRY=USA

# Himalayas Configuration
HIMALAYAS_KEYWORDS=engineering,python,machine learning
HIMALAYAS_WORLDWIDE_ONLY=true
```

#### 3.2 Create Config Module
**File**: `src/common/ingest_config.py`

```python
@dataclass
class IngestConfig:
    enabled: bool = True
    score_threshold: int = 70
    results_per_source: int = 50
    indeed_search_terms: List[str]
    indeed_locations: List[str]
    himalayas_keywords: List[str]
```

### Phase 4: Docker Deployment (Day 2-3)

#### 4.1 Docker Container (Selected Option)

**Files Created:**
- `docker/job-ingest/Dockerfile` - Container image
- `docker/job-ingest/crontab` - Cron schedule
- `docker/job-ingest/entrypoint.sh` - Startup script
- `docker-compose.ingest.yml` - Compose configuration

#### 4.2 Build and Deploy

```bash
# Build the image
docker-compose -f docker-compose.ingest.yml build

# Run standalone
docker-compose -f docker-compose.ingest.yml up -d

# Or run with existing runner service
docker-compose -f docker-compose.runner.yml -f docker-compose.ingest.yml up -d
```

#### 4.3 Environment Variables

Set in `.env` on VPS:
```bash
# Ingestion config
AUTO_INGEST_ENABLED=true
AUTO_INGEST_SCORE_THRESHOLD=70
INDEED_SEARCH_TERMS=engineering manager,staff engineer
HIMALAYAS_KEYWORDS=python,engineering

# Run on container start (for testing)
RUN_ON_STARTUP=false
```

#### 4.4 View Logs

```bash
# Container logs
docker logs job-search-job-ingest-1 -f

# Ingestion logs (inside container)
docker exec job-search-job-ingest-1 cat /app/logs/ingest_latest.json

# Cron logs
docker exec job-search-job-ingest-1 tail -f /app/logs/cron.log
```

### Phase 5: Himalayas MCP Server Integration (Day 3)

#### 5.1 Configure Claude Desktop
**File**: `~/.claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "himalayas": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.himalayas.app/sse"]
    }
  }
}
```

#### 5.2 Available MCP Tools
- `search_jobs`: Search by keyword, country, pagination
- `get_jobs`: Get latest remote job listings
- `search_companies`: Find remote-friendly companies
- `get_companies`: Browse companies with filters

### Phase 6: Frontend Updates (Day 3-4)

#### 6.1 Add Source Badge
**File**: `frontend/templates/components/job_card.html`

Add visual indicator for auto-discovered jobs:
```html
{% if job.auto_discovered %}
  <span class="badge bg-info">Auto-discovered</span>
{% endif %}
{% if job.source %}
  <span class="badge bg-secondary">{{ job.source }}</span>
{% endif %}
```

#### 6.2 Add Source Filter
**File**: `frontend/app.py`

Add filter endpoint parameter:
```python
@app.route("/api/jobs")
def list_jobs():
    source = request.args.get("source")  # "indeed_auto", "himalayas_auto", etc.
    if source:
        query["source"] = source
```

### Phase 7: Logging & Error Handling (Day 4)

#### 7.1 Add Logging
```python
import logging
logger = logging.getLogger("job_ingestion")

# Log run statistics
logger.info(f"Ingestion complete: {stats}")
```

#### 7.2 Error Handling
- Retry with exponential backoff (3 attempts)
- Log errors to file for debugging
- Write last run status to simple JSON file for monitoring

**Note**: No notifications configured - auto-discovered jobs simply appear in the job list with source badges.

---

## Files to Create

| File | Description |
|------|-------------|
| `src/services/job_sources/__init__.py` | Job source base class and exports |
| `src/services/job_sources/indeed_source.py` | JobSpy Indeed integration |
| `src/services/job_sources/himalayas_source.py` | Himalayas API integration |
| `src/common/ingest_config.py` | Ingestion configuration |
| `scripts/ingest_jobs_cron.py` | Main cron script |
| `scripts/scheduler.py` | APScheduler alternative |
| `tests/test_job_sources.py` | Unit tests for sources |
| `tests/test_ingestion.py` | Integration tests |

## Files to Modify

| File | Changes |
|------|---------|
| `requirements.txt` | Add `python-jobspy` |
| `.env.example` | Add ingestion config vars |
| `frontend/app.py` | Add source filter, status endpoint |
| `frontend/templates/components/job_card.html` | Add source badge |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Indeed ToS violation | JobSpy is OSS; keep volume low (50/run); rotate searches |
| Scoring cost spike | Cap at 200 jobs/day (~$6/month); use cheaper model |
| Duplicate jobs | dedupeKey index; check before scoring |
| Cron failures | Logging + health monitoring + alerts |
| Low quality jobs | Tune threshold after 1 week based on feedback |

---

## Cost Estimate

| Item | Monthly Cost |
|------|--------------|
| Quick Scoring (~800 jobs/month) | ~$2.40 |
| Himalayas API | Free |
| JobSpy | Free (OSS) |
| **Total** | **~$3/month** |

---

## Testing Strategy

1. **Unit Tests**: Mock JobSpy and Himalayas API responses
2. **Integration Tests**: Test deduplication and scoring flow
3. **Manual Testing**: Run single ingestion, verify in frontend
4. **Production Validation**: Monitor first week, tune threshold

---

## Timeline

| Day | Tasks |
|-----|-------|
| 1 | Core infrastructure: job sources, Indeed/Himalayas adapters |
| 2 | Ingestion pipeline, configuration, cron setup |
| 3 | Himalayas MCP server, frontend source badge |
| 4 | Monitoring, error handling, testing |
| 5 | Deployment to VPS, production validation |

**Total: ~5 days**

---

---

## Appendix: Himalayas MCP Server Setup

The Himalayas MCP server provides Claude Desktop with direct access to remote job data via tool calls.

### Claude Desktop Configuration

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "himalayas": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.himalayas.app/sse"]
    }
  }
}
```

### Available MCP Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_jobs` | Search jobs by keyword | `keyword`, `country`, `page` |
| `get_jobs` | Get latest remote jobs | `page`, `limit` |
| `search_companies` | Find remote companies | `keyword`, `size`, `industry` |
| `get_companies` | Browse companies | `page`, `limit` |

### Example Usage in Claude

Once configured, you can ask Claude:
- "Search for Python remote jobs on Himalayas"
- "Find remote-first engineering companies"
- "What remote jobs are available for machine learning?"

Claude will use the MCP tools to fetch real-time data from Himalayas.app.

### MCP Server URL

Public SSE endpoint: `https://mcp.himalayas.app/sse`

No authentication required - rate limited to ensure fair usage.

---

## Sources

- [JobSpy GitHub](https://github.com/speedyapply/JobSpy) - Open source job scraper
- [Himalayas MCP Server](https://github.com/Himalayas-App/himalayas-mcp) - Remote jobs MCP
- [Himalayas API](https://himalayas.app/api) - Free remote jobs API
- [Indeed Terms of Service](https://www.indeed.com/legal) - Legal reference
