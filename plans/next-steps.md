# Next Steps - Immediate Priorities

**Last Updated**: 2025-11-28
**Current Focus**: Phase 5 Features (WYSIWYG Page Breaks, 8-10 hours)

> **Documentation Structure Note**: All agent-specific plans and reports are now organized in:
> - Plans: `plans/agents/{agent-name}/`
> - Reports: `reports/agents/{agent-name}/`
>
> See `plans/agents/README.md` for detailed guidelines.

---

## Current Blockers (Priority Order)

1. **CRITICAL - Anthropic API credits low**
   - Impact: CV generator may fail in production
   - Status: Blocking Phase 4+ pipeline execution
   - Workaround: Add `USE_ANTHROPIC=false` + configure OpenAI
   - Action: Add credits to Anthropic account or switch LLM provider

2. **LOW - E2E tests disabled**
   - Status: Non-blocking (Phase 1-4 unit tests passing)
   - Impact: Can't verify full user flow via Playwright
   - Plan: Re-enable with smoke test suite for Phase 1-4
   - See: `plans/e2e-testing-implementation.md`

---

## RESOLVED (2025-11-28)

- ✅ **Phase 2 Issue #2: Editor Not WYSIWYG** - RESOLVED 2025-11-26
  - Added 178 lines of CSS for `.ProseMirror` content nodes
  - Status: Working perfectly, all formatting visible in editor

- ✅ **Phase 2 Issue #1: CV Display Not Updating** - RESOLVED 2025-11-26
  - Added `updateMainCVDisplay()` function to sync editor changes to display
  - Status: Changes now visible immediately on editor close

---

## Priority 1: Phase 5 - WYSIWYG Page Break Visualization

**Status**: Design phase complete, ready for implementation
**Assigned to**: frontend-developer
**Effort**: 8-10 hours
**Plan Document**: `plans/phase5-page-break-visualization.md`

### Overview
Display visual page break indicators in CV editor showing where content breaks across pages when exported to PDF. Provides true WYSIWYG experience matching actual PDF output.

### Key Components
1. **Page Break Calculator** - Compute break positions from content height
2. **Page Break Renderer** - Insert visual break indicators in DOM
3. **Dynamic Update Integration** - Recalculate on content/style changes
4. **Detail Page Integration** - Show breaks in main CV display

### Dependencies (All Complete)
- ✓ Phase 1: TipTap editor foundation
- ✓ Phase 2: Text formatting and fonts
- ✓ Phase 3: Document styles (margins, page size, line height)
- ✓ Phase 4: PDF export with correct page dimensions

### Testing Strategy
- 50+ unit tests planned
- E2E tests for both editor and detail page
- Cross-browser compatibility validation
- Multiple page counts (1, 2, 3, 5+ pages)

### Next Steps
1. Review full specification in `plans/phase5-page-break-visualization.md`
2. Break down implementation into 5 phases (2 hours each)
3. Assign to frontend-developer for implementation
4. Coordinate with PDF export to ensure break positions match

---

## Step 1: Fix LLM Provider for CV Generation

**Problem**: Anthropic API returns "credit balance too low"

**Action**:
```bash
# Option A: Add credits at https://console.anthropic.com/settings/billing

# Option B: Use OpenAI for CV generation (add to .env)
USE_ANTHROPIC=false
USE_OPENROUTER=false
```

**Verify**:
```bash
source .venv/bin/activate
python -c "from src.common.config import Config; print(f'CV Provider: {Config.get_cv_llm_provider()}')"
```

**Success**: Output shows working provider (`openai` or `anthropic` with credits)

---

## Step 2: Run Local Pipeline Smoke Test

**Action**:
```bash
source .venv/bin/activate

# Get a job ID from MongoDB
python -c "
from src.common.database import get_database
db = get_database()
job = db['level-2'].find_one({}, {'_id': 1, 'title': 1, 'company': 1})
print(f'Job ID: {job[\"_id\"]}')
print(f'Title: {job.get(\"title\", \"N/A\")}')
print(f'Company: {job.get(\"company\", \"N/A\")}')
"

# Run pipeline with that ID
python scripts/run_pipeline.py --job-id <JOB_ID>
```

**Verify**:
```bash
ls -la applications/*/
# Should show: <Company>/<Role>/ with CV.md, dossier.txt, cover_letter.txt
```

**Success**: Pipeline completes all 7 layers, artifacts created

---

## Step 3: Run Unit Tests (Excluding API-Dependent)

**Action**:
```bash
source .venv/bin/activate
python -m pytest tests/unit/ \
  --ignore=tests/unit/test_layer6_markdown_cv_generator.py \
  --ignore=tests/unit/test_layer6_outreach_generator.py \
  -v --tb=short
```

**Success**: 135+ tests pass

---

## Step 4: Add Mocks to CV Generator Tests

**Problem**: Tests make real Anthropic API calls

**Action**: Edit `tests/unit/test_layer6_markdown_cv_generator.py`:

```python
# Add at top of file
from unittest.mock import patch, MagicMock

# Add fixture
@pytest.fixture(autouse=True)
def mock_llm():
    """Mock ChatAnthropic for all tests."""
    with patch('src.layer6.generator.ChatAnthropic') as mock_class:
        mock_instance = MagicMock()
        mock_instance.invoke.return_value.content = '''
{
  "evidence_json": {
    "contact_info": {"name": "Test User", "email": "test@example.com"},
    "summary": "Experienced engineer...",
    "experience": [{"company": "Acme", "role": "Senior Engineer", "bullets": ["Led team..."]}]
  },
  "cv_markdown": "# Test User\\n\\n## Summary\\nExperienced engineer..."
}
'''
        mock_class.return_value = mock_instance
        yield mock_instance
```

**Verify**:
```bash
python -m pytest tests/unit/test_layer6_markdown_cv_generator.py -v --tb=short
```

**Success**: All CV generator tests pass without API calls

---

## Step 5: Configure VPS Environment (Updated 2025-11-28)

**Action**:
```bash
ssh root@72.61.92.76
cd /root/job-runner

# Create .env file
cat > .env << 'EOF'
# Runner
MAX_CONCURRENCY=3
PIPELINE_TIMEOUT_SECONDS=600
RUNNER_API_SECRET=<run: openssl rand -hex 32>
CORS_ORIGINS=https://your-app.vercel.app

# Pipeline
MONGODB_URI=<your-connection-string>              # CHANGED 2025-11-28: was MONGO_URI
MONGO_DB_NAME=job_search
OPENAI_API_KEY=<your-key>
ANTHROPIC_API_KEY=<your-key-or-empty>
FIRECRAWL_API_KEY=<your-key>

# Feature Flags
DISABLE_FIRECRAWL_OUTREACH=true
USE_ANTHROPIC=true
PLAYWRIGHT_HEADLESS=true
EOF

# Copy master CV from local
exit
scp master-cv.md root@72.61.92.76:/root/job-runner/
```

**Verify**:
```bash
ssh root@72.61.92.76 "ls -la /root/job-runner/.env /root/job-runner/master-cv.md"
```

**Success**: Both files exist on VPS

---

## Step 6: Configure Vercel Environment

**Action**: In Vercel Dashboard > Settings > Environment Variables:

| Variable | Value |
|----------|-------|
| `LOGIN_PASSWORD` | (secure password) |
| `FLASK_SECRET_KEY` | (run: `python -c "import os; print(os.urandom(24).hex())"`) |
| `MONGODB_URI` | (same as VPS) |
| `RUNNER_URL` | `http://72.61.92.76:8000` |
| `RUNNER_API_SECRET` | (same as VPS .env) |

**Success**: All 5 variables set, secrets match VPS

---

## Step 7: Deploy Runner to VPS

**Action**:
```bash
# Option A: Push to trigger CI/CD
git push origin main

# Option B: Manual deploy
ssh root@72.61.92.76
cd /root/job-runner
docker compose -f docker-compose.runner.yml pull
docker compose -f docker-compose.runner.yml up -d
```

**Verify**:
```bash
curl http://72.61.92.76:8000/health
```

**Success**: Returns `{"status": "healthy", "active_runs": 0, ...}`

---

## Step 8: End-to-End Test via UI

**Action**:
1. Open Vercel frontend URL
2. Login with `LOGIN_PASSWORD`
3. Navigate to job detail page
4. Click "Process Job" button
5. Watch log stream in UI
6. Wait for completion

**Verify**:
```bash
# Check MongoDB
mongosh "$MONGODB_URI" --eval "
  db.getSiblingDB('jobs').getCollection('level-2').findOne(
    {_id: ObjectId('JOB_ID')},
    {status: 1, pain_points: 1, fit_score: 1, cv_path: 1}
  )
"
```

**Success**:
- Logs stream in real-time
- Progress bar reaches 100%
- Job status = "ready for applying"
- MongoDB has pain_points, fit_score, cv_path

---

## Quick Reference: Environment Variables (Updated 2025-11-28)

### VPS (.env)
```bash
MAX_CONCURRENCY=3
PIPELINE_TIMEOUT_SECONDS=600
RUNNER_API_SECRET=<shared-secret>                 # Changed from RUNNER_API_TOKEN (2025-11-28)
CORS_ORIGINS=https://your-app.vercel.app
MONGODB_URI=mongodb+srv://...                     # Changed from MONGO_URI (2025-11-28)
MONGO_DB_NAME=job_search
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...                      # Optional
FIRECRAWL_API_KEY=fc-...
DISABLE_FIRECRAWL_OUTREACH=true
USE_ANTHROPIC=true
PLAYWRIGHT_HEADLESS=true
```

### Vercel
```
LOGIN_PASSWORD=<secure>
FLASK_SECRET_KEY=<hex>
MONGODB_URI=mongodb+srv://...
RUNNER_SERVICE_URL=http://72.61.92.76:8000
RUNNER_API_SECRET=<same-as-vps>                  # Changed from RUNNER_API_TOKEN (2025-11-28)
```

---

## Rollback

```bash
# VPS
ssh root@72.61.92.76
cd /root/job-runner
git log --oneline -5
git checkout <working-commit>
docker compose -f docker-compose.runner.yml up -d --build

# Vercel: Use dashboard to redeploy previous version
```
