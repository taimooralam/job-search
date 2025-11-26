# VPS Deployment Guide with HTML CV Integration

Complete guide for deploying the job-intelligence pipeline to Hostinger VPS, including the new HTML CV editing and PDF export features.

---

## Prerequisites Checklist

- [x] VPS SSH access (`ssh root@72.61.92.76`)
- [x] GitHub repository secrets configured:
  - `VPS_HOST`
  - `VPS_USER`
  - `VPS_SSH_KEY`
- [x] Vercel project created
- [x] All API keys ready:
  - MongoDB URI
  - OpenAI API Key
  - OpenRouter API Key
  - FireCrawl API Key
  - LangSmith API Key (optional)

---

## Step 1: Configure VPS Environment Variables ✅ COMPLETED

SSH into your VPS and create the `.env` file:

```bash
ssh root@72.61.92.76
cd /root/job-runner

# Create .env file
nano .env
```

Paste the following configuration (replace placeholders with real values):

```bash
# RUNNER SERVICE SETTINGS
MAX_CONCURRENCY=3
LOG_BUFFER_LIMIT=500
PIPELINE_TIMEOUT_SECONDS=600
ENVIRONMENT=production

# SECURITY (REQUIRED)
RUNNER_API_SECRET=<generate-with: openssl rand -hex 32>
CORS_ORIGINS=https://<your-vercel-app>.vercel.app

# REDIS (Optional - uses existing n8n Redis)
REDIS_URL=redis://redis:6379/5

# MONGODB (REQUIRED)
MONGODB_URI=<your-mongodb-connection-string>

# PIPELINE SECRETS (REQUIRED)
OPENAI_API_KEY=<your-openai-key>
OPENROUTER_API_KEY=<your-openrouter-key>
FIRECRAWL_API_KEY=<your-firecrawl-key>

# LANGSMITH (Optional but recommended for debugging)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your-langsmith-key>
LANGCHAIN_PROJECT=job-intelligence

# GOOGLE (Optional - if using Drive/Sheets)
# GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
# GOOGLE_DRIVE_FOLDER_ID=...
# GOOGLE_SHEET_ID=...
```

**Important Notes:**
- Generate `RUNNER_API_SECRET` with: `openssl rand -hex 32`
- Keep this secret safe - it's used for API authentication
- The same secret must be configured in Vercel

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

---

## Step 2: Copy master-cv.md to VPS

The pipeline needs your master CV file:

```bash
# From your local machine
scp master-cv.md root@72.61.92.76:/root/job-runner/
```

Verify it's there:

```bash
ssh root@72.61.92.76 "ls -lh /root/job-runner/master-cv.md"
```

---

## Step 3: Configure Vercel Environment Variables ✅ COMPLETED

Go to your Vercel project dashboard:
1. Navigate to: **Settings > Environment Variables**
2. Add the following variables for **Production**:

| Variable | Value | Notes |
|----------|-------|-------|
| `LOGIN_PASSWORD` | (choose secure password) | For frontend authentication |
| `FLASK_SECRET_KEY` | (generate: `python -c "import os; print(os.urandom(24).hex())"`) | Flask session encryption |
| `MONGODB_URI` | (your MongoDB connection string) | Same as VPS |
| `RUNNER_URL` | `http://72.61.92.76:8000` | VPS runner endpoint |
| `RUNNER_API_SECRET` | (same as VPS RUNNER_API_SECRET) | **Must match VPS secret** |

**Critical:** The `RUNNER_API_SECRET` must be **identical** on both VPS and Vercel.

---

## Step 4: Deploy to VPS via CI/CD ✅ COMPLETED

Your GitHub Actions workflow will automatically deploy when you push to main:

```bash
# Commit any pending changes
git add -A
git commit -m "feat: Ready for VPS deployment with HTML CV"

# Push to main - this triggers CI/CD
git push origin main
```

**What happens:**
1. GitHub Actions runs tests (18 unit tests)
2. Builds Docker image with Playwright/Chromium
3. Pushes image to GitHub Container Registry
4. SSH into VPS and runs deployment
5. Copies `master-cv.md` to VPS (configured in workflow)

**Monitor deployment:**
- Go to GitHub repository → Actions tab
- Watch the "Runner CI/CD" workflow
- Should complete in 5-10 minutes

---

## Step 5: Verify VPS Health ✅ COMPLETED

Once deployment completes, check the health endpoint:

```bash
# From your local machine
curl http://72.61.92.76:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "runner_service": "operational",
  "mongodb": "connected"
}
```

Check Docker container is running:

```bash
ssh root@72.61.92.76 "docker ps | grep runner"
```

View recent logs:

```bash
ssh root@72.61.92.76 "docker logs job-runner-runner-1 --tail 50"
```

---

## Step 6: Test Pipeline Execution with HTML CV Generation

Test the full pipeline with a real job from MongoDB:

### 6.1 Get a test job ID

```bash
# SSH into VPS
ssh root@72.61.92.76

# Connect to MongoDB and get a job ID
mongo "$MONGODB_URI"
> use jobs
> db.getCollection('level-2').findOne({}, {_id: 1, title: 1, company: 1})
```

Copy the job ID (e.g., `67442f1e5e8d9a001234abcd`).

### 6.2 Trigger pipeline via API

```bash
# From local machine - use the RUNNER_API_SECRET from VPS
export RUNNER_API_SECRET="<your-secret-here>"
export JOB_ID="<job-id-from-mongodb>"

curl -X POST http://72.61.92.76:8000/api/runner/jobs/run \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: $RUNNER_API_SECRET" \
  -d "{\"job_id\": \"$JOB_ID\", \"level\": 2}"
```

Expected response:
```json
{
  "run_id": "abc123...",
  "status": "running",
  "job_id": "67442f1e..."
}
```

### 6.3 Monitor logs via SSE

```bash
export RUN_ID="<run-id-from-above>"

curl -N http://72.61.92.76:8000/api/runner/jobs/$RUN_ID/logs
```

You should see real-time log streaming from the pipeline, including:
- Pain point mining
- Company research
- Role research
- STAR selection
- **HTML CV generation** ← NEW
- Cover letter generation

### 6.4 Check status and artifacts

```bash
curl http://72.61.92.76:8000/api/runner/jobs/$RUN_ID/status
```

Expected response when complete:
```json
{
  "run_id": "abc123...",
  "status": "completed",
  "progress": 1.0,
  "artifacts": {
    "cover_letter.md": "/path/to/file",
    "CV.html": "/path/to/file",
    "CV.md": "/path/to/file",
    "dossier.md": "/path/to/file"
  }
}
```

---

## Step 7: Verify Frontend Integration

1. Go to your Vercel-deployed frontend: `https://<your-app>.vercel.app`
2. Log in with your `LOGIN_PASSWORD`
3. Navigate to a job detail page
4. Click the **"Process Job"** button
5. Watch the pipeline status UI update in real-time
6. Verify logs stream in the terminal component
7. Check artifacts appear when complete

---

## Step 8: Test HTML CV Editing and PDF Export (NEW)

Once a job has been processed with an HTML CV:

### 8.1 View HTML CV

1. Navigate to the job detail page
2. Scroll to the **"Generated CV"** section
3. The CV should display in an iframe with professional styling

### 8.2 Edit CV Inline

1. Click the **"Edit CV"** button
   - Button changes to red "Cancel Edit"
   - "Save Changes" button appears
2. Click into any section of the CV (name, summary, experience bullets)
3. Make your edits directly in the CV
4. Click **"Save Changes"** to persist your edits

### 8.3 Generate and Download PDF

1. Click the **"Generate PDF"** button
2. Wait for "PDF generated successfully" message
3. PDF automatically downloads
4. Verify PDF has:
   - Clean A4 formatting
   - All your edits preserved
   - Professional styling
   - Print-optimized layout

### 8.4 Verify PDF on VPS

```bash
# SSH into VPS and check artifacts
ssh root@72.61.92.76

# Navigate to job application directory
cd /root/job-runner/applications/<Company_Name>/<Role_Title>

# List files
ls -lh

# You should see:
# - CV.html (editable HTML CV)
# - CV.md (markdown CV)
# - CV.pdf (generated PDF)
# - cover_letter.md
# - dossier.md
```

---

## Troubleshooting

### Pipeline fails immediately

**Check logs:**
```bash
ssh root@72.61.92.76 "docker logs job-runner-runner-1 --tail 100"
```

**Common causes:**
- Missing environment variables
- Invalid API keys
- MongoDB connection issues
- Missing `master-cv.md` file

**Fix:**
```bash
# Check .env file exists and has all required vars
ssh root@72.61.92.76 "cat /root/job-runner/.env | grep -E 'MONGODB_URI|OPENAI_API_KEY|FIRECRAWL_API_KEY'"

# Verify master-cv.md exists
ssh root@72.61.92.76 "ls -lh /root/job-runner/master-cv.md"

# Restart container after fixing
ssh root@72.61.92.76 "cd /root/job-runner && docker compose -f docker-compose.runner.yml restart"
```

### Frontend can't reach VPS

**Check CORS configuration:**
```bash
# Verify CORS_ORIGINS in VPS .env matches Vercel URL
ssh root@72.61.92.76 "cat /root/job-runner/.env | grep CORS_ORIGINS"
```

**Check network connectivity:**
```bash
# From Vercel serverless function, test VPS connectivity
curl -v http://72.61.92.76:8000/health
```

### 401 Unauthorized errors

**Verify secrets match:**
```bash
# VPS secret
ssh root@72.61.92.76 "cat /root/job-runner/.env | grep RUNNER_API_SECRET"

# Compare with Vercel environment variable in dashboard
# They must be IDENTICAL
```

### MongoDB connection fails

**Test connection:**
```bash
ssh root@72.61.92.76

# Test MongoDB connectivity
python3 -c "from pymongo import MongoClient; print(MongoClient('$MONGODB_URI').server_info())"
```

**Check firewall:**
- Ensure MongoDB Atlas allows VPS IP: `72.61.92.76`
- Go to Atlas → Network Access → Add IP Address

### HTML CV not displaying

**Check if CV.html exists:**
```bash
ssh root@72.61.92.76
cd /root/job-runner/applications/<Company>/<Role>
ls -lh CV.html
```

**View CV HTML directly:**
```bash
cat CV.html | head -50
```

**Common issues:**
- Pipeline didn't reach Layer 6 (CV generation)
- Artifacts directory not mounted correctly
- Permissions issue with file creation

### PDF generation fails

**Check Playwright installation:**
```bash
ssh root@72.61.92.76 "docker exec job-runner-runner-1 python -c 'from playwright.sync_api import sync_playwright; print(\"OK\")'"
```

**View Playwright logs:**
```bash
ssh root@72.61.92.76 "docker logs job-runner-runner-1 | grep -i playwright"
```

**Common issues:**
- Chromium not installed in Docker image
- Missing system dependencies for Playwright
- Insufficient memory for browser launch

**Fix:**
- Dockerfile.runner includes Playwright installation
- Rebuild image: `docker compose -f docker-compose.runner.yml build --no-cache`

---

## Success Indicators

✅ **Deployment successful when:**
- Health endpoint returns `{"status": "healthy"}`
- Pipeline executes without errors
- Logs stream in real-time
- Artifacts are created in `applications/` directory
- **HTML CV displays in job detail page** ← NEW
- **CV editing works and saves changes** ← NEW
- **PDF generates and downloads successfully** ← NEW
- MongoDB `pipeline_runs` collection has new documents
- Frontend can trigger and monitor pipeline runs

---

## Manual Deployment (Alternative)

If CI/CD isn't working, deploy manually:

```bash
# SSH into VPS
ssh root@72.61.92.76
cd /root/job-runner

# Pull latest code (if git-managed)
git pull origin main

# Or manually update docker-compose.runner.yml if needed

# Pull latest image
docker compose -f docker-compose.runner.yml pull

# Restart services
docker compose -f docker-compose.runner.yml up -d --remove-orphans

# Clean up
docker system prune -f

# Verify
curl http://localhost:8000/health
```

---

## Architecture: HTML CV Workflow

```
Pipeline Run → Layer 6 (CV Generator)
                    ↓
        HTMLCVGenerator.generate_html_cv()
                    ↓
    Generates: applications/<Company>/<Role>/CV.html
                    ↓
Frontend Job Detail Page
                    ↓
        Displays CV in iframe
                    ↓
        User clicks "Edit CV"
                    ↓
    contenteditable enabled → user edits inline
                    ↓
        User clicks "Save Changes"
                    ↓
    PUT /api/jobs/<id>/cv (saves full HTML)
                    ↓
        User clicks "Generate PDF"
                    ↓
    POST /api/jobs/<id>/cv/pdf
                    ↓
    Playwright renders HTML → creates CV.pdf
                    ↓
    GET /api/jobs/<id>/cv/download
                    ↓
        PDF downloads automatically
```

`★ Insight ─────────────────────────────────────`
The HTML CV architecture separates concerns cleanly: the LLM only generates content (STAR selection, professional summary), while Python code programmatically builds the HTML structure. This prevents hallucinated HTML tags and ensures consistent professional styling across all CVs.
`─────────────────────────────────────────────────`

---

## Next Steps After Successful Deployment

1. ✅ **Test with multiple jobs** - Verify concurrent execution works
2. ✅ **Test HTML CV workflow** - Edit, save, generate PDF for different roles
3. **Monitor resource usage** - Check CPU/memory with `docker stats`
4. **Set up log rotation** - Docker logs can grow large
5. **Enable HTTPS** - Add Traefik or nginx reverse proxy
6. **Set up monitoring** - Consider adding health check alerts
7. **Batch processing** - Test processing multiple jobs simultaneously
8. **CV template customization** - Adjust HTML/CSS in HTMLCVGenerator if needed

---

## Support

If you encounter issues:
1. Check logs: `docker logs job-runner-runner-1`
2. Review environment variables: `.env` file on VPS
3. Test health endpoint: `curl http://72.61.92.76:8000/health`
4. Check GitHub Actions for deployment errors
5. Verify all API keys are valid and have sufficient quota
6. For HTML CV issues: check `applications/` directory structure
7. For PDF issues: verify Playwright installation in container
