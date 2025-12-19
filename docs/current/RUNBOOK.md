# Operations Runbook

**Job Intelligence Pipeline - Operational Procedures**

> Quick reference for diagnosing and resolving common issues.

---

## Table of Contents

1. [Quick Health Check](#quick-health-check)
2. [Service Status Commands](#service-status-commands)
3. [Common Issues & Solutions](#common-issues--solutions)
4. [Pipeline Troubleshooting](#pipeline-troubleshooting)
5. [Database Operations](#database-operations)
6. [Recovery Procedures](#recovery-procedures)
7. [Monitoring & Alerts](#monitoring--alerts)

---

## Quick Health Check

### Dashboard Health Indicators

Open the dashboard and check the **Service Health** panel (top right):
- **Green**: All services healthy
- **Yellow**: Some services degraded (check capacity)
- **Red**: Critical failure (requires intervention)

### API Health Endpoint

```bash
# Check all services via API
curl -H "Authorization: Bearer $JWT_TOKEN" https://your-app.vercel.app/api/health

# Expected response structure:
# {
#   "overall": "healthy",
#   "runner": {"status": "healthy", "active_runs": 0, "capacity_percent": 0},
#   "mongodb": {"status": "healthy"},
#   "pdf_service": {"status": "healthy"}
# }
```

---

## Service Status Commands

### VPS Runner Service

```bash
# SSH to VPS
ssh user@72.61.92.76

# Check service status
docker-compose ps

# View logs
docker-compose logs -f runner_service --tail=100

# Restart services
docker-compose restart runner_service pdf_service

# Check resource usage
docker stats
```

### MongoDB Atlas

```bash
# Test connection (from local dev)
python -c "from src.common.database import Database; db = Database(); print('Connected:', db.db.name)"

# Check collection counts
python -c "
from src.common.database import Database
db = Database()
print('Jobs:', db.jobs.count_documents({}))
print('Pipeline Runs:', db.pipeline_runs.count_documents({}))
print('STAR Records:', db.star_records.count_documents({}))
"
```

### PDF Service (Playwright)

```bash
# Check if Chromium is running
docker-compose exec pdf_service ps aux | grep chromium

# Test PDF generation
curl -X POST http://72.61.92.76:8000/api/jobs/test123/cv-editor/pdf \
  -H "Content-Type: application/json"
```

---

## Common Issues & Solutions

### Issue: "Pipeline stuck at processing"

**Symptoms**: Job shows "processing" for >10 minutes

**Diagnosis**:
```bash
# Check runner logs
docker-compose logs runner_service --since=10m | grep ERROR

# Check for orphaned runs
curl https://your-app.vercel.app/api/pipeline-runs?status=processing
```

**Resolution**:
1. Check runner health: `curl http://72.61.92.76:8000/health`
2. Restart runner if unresponsive: `docker-compose restart runner_service`
3. Manually update job status in MongoDB if needed

---

### Issue: "PDF generation fails"

**Symptoms**: "PDF generation failed" error in UI

**Diagnosis**:
```bash
# Check PDF service logs
docker-compose logs pdf_service --tail=50

# Common causes:
# - Chromium crashed (memory)
# - Font loading timeout
# - Google Fonts blocked
```

**Resolution**:
1. Restart PDF service: `docker-compose restart pdf_service`
2. If memory issue, increase container limits in `docker-compose.yml`
3. Check if Google Fonts accessible from VPS

---

### Issue: "FireCrawl rate limited"

**Symptoms**: Contact discovery returns empty results, logs show 429 errors

**Diagnosis**:
```bash
grep "429" runner_service.log
grep "rate_limit" runner_service.log
```

**Resolution**:
1. Circuit breaker should auto-recover (5-min backoff)
2. If persistent, check FireCrawl dashboard for quota
3. Temporary: Disable contact discovery (`ENABLE_FIRECRAWL=false`)

---

### Issue: "500 error on job list"

**Symptoms**: Dashboard shows error loading jobs

**Diagnosis**:
```bash
# Check frontend logs (Vercel)
vercel logs

# Common causes:
# - MongoDB connection timeout
# - Invalid datetime in filters
```

**Resolution**:
1. Check MongoDB Atlas status
2. Clear browser cache / try different filters
3. Check for recent deployment issues

---

### Issue: "LLM API errors"

**Symptoms**: "Error generating CV" or empty outputs

**Diagnosis**:
```bash
# Check which provider failed
grep "openrouter\|anthropic\|openai" runner_service.log | grep -i error

# Check rate limits
curl https://your-app.vercel.app/api/metrics | jq '.rate_limits'
```

**Resolution**:
1. Check provider status pages (Anthropic, OpenRouter)
2. Verify API keys in VPS `.env`
3. Circuit breaker auto-switches to backup provider
4. Manual fallback: Set `PRIMARY_LLM_PROVIDER=openai`

---

### Issue: "Contacts not found"

**Symptoms**: People Mapper returns synthetic contacts only

**Diagnosis**:
```bash
# Check if FireCrawl is enabled
grep ENABLE_FIRECRAWL .env

# Check company cache
python -c "
from src.common.database import Database
db = Database()
cache = db.company_cache.find_one({'company': 'CompanyName'})
print(cache)
"
```

**Resolution**:
1. If intentional (cost saving), no action needed
2. Enable FireCrawl: `ENABLE_FIRECRAWL=true`
3. Clear stale cache: Delete company from `company_cache` collection

---

## Pipeline Troubleshooting

### Check Pipeline Run History

```bash
# Get recent runs
curl https://your-app.vercel.app/api/pipeline-runs?limit=10

# Get runs for specific job
curl https://your-app.vercel.app/api/pipeline-runs?job_id=JOB_ID

# Get failed runs
curl https://your-app.vercel.app/api/pipeline-runs?status=failed
```

### View LangSmith Traces

1. Open run in UI, click "LangSmith Trace" link
2. Or find in LangSmith: `https://smith.langchain.com/` → Filter by run_id

### Re-run Failed Pipeline

```bash
# Via API
curl -X POST http://72.61.92.76:8000/run \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB_ID"}'
```

### Debug Layer-by-Layer

Enable verbose logging:
```bash
# In VPS .env
LOG_LEVEL=DEBUG
LOG_FORMAT=json

# Restart and watch
docker-compose restart runner_service
docker-compose logs -f runner_service | jq '.'
```

---

## Database Operations

### Backup (MongoDB Atlas)

MongoDB Atlas PITR is enabled. For manual snapshots:
1. Atlas Console → Clusters → ... → Take Snapshot

### Clear Stuck Jobs

```python
from src.common.database import Database
from datetime import datetime, timedelta

db = Database()

# Find stuck processing jobs (>30 min)
stuck_threshold = datetime.utcnow() - timedelta(minutes=30)
stuck = db.jobs.find({
    "status": "processing",
    "updated_at": {"$lt": stuck_threshold}
})

# Update to failed
for job in stuck:
    db.jobs.update_one(
        {"_id": job["_id"]},
        {"$set": {"status": "failed", "error": "Stuck processing - manual reset"}}
    )
```

### Clear Company Cache

```python
from src.common.database import Database

db = Database()

# Clear specific company
db.company_cache.delete_many({"company": "Company Name"})

# Clear all cache (force re-fetch)
db.company_cache.delete_many({})
```

### Reset Pipeline Runs

```python
from src.common.database import Database

db = Database()

# Clear all runs for testing
db.pipeline_runs.delete_many({})
```

---

## Recovery Procedures

### Full Service Restart (VPS)

```bash
ssh user@72.61.92.76
cd /opt/job-search
docker-compose down
docker-compose pull
docker-compose up -d
docker-compose logs -f
```

### Rollback Deployment

```bash
# List recent deployments
vercel ls

# Rollback to previous
vercel rollback [deployment-url]
```

### Emergency: Disable Pipeline

If pipeline is causing issues:
```bash
# On VPS, stop runner but keep PDF service
docker-compose stop runner_service

# Re-enable later
docker-compose start runner_service
```

---

## Monitoring & Alerts

### Key Metrics to Watch

| Metric | Warning | Critical | Source |
|--------|---------|----------|--------|
| Runner capacity | >80% | 100% | `/api/health` |
| Pipeline failure rate | >10% | >25% | `/api/pipeline-runs` |
| LLM cost per run | >$0.50 | >$1.00 | `/api/metrics` |
| Response time | >5s | >15s | Vercel Analytics |

### Set Up External Monitoring

1. **UptimeRobot**: Monitor `/api/health` endpoint
2. **Sentry**: Error tracking (already integrated)
3. **LangSmith**: LLM trace monitoring

### Daily Checks

1. Review `/api/pipeline-runs?status=failed&limit=10`
2. Check `/api/metrics` for unusual cost spikes
3. Verify runner capacity is not maxed

---

## Contacts

- **Infrastructure Issues**: Check runner logs first
- **LLM Quality Issues**: Check LangSmith traces
- **Database Issues**: MongoDB Atlas status page

---

*Last Updated: 2025-12-01*
