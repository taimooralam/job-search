# Session Quick Start Guide

**Last Session**: November 30, 2025 | **Status**: All work staged, ready to commit | **Tests**: 228+ passing

---

## For Returning Developer (First 5 Minutes)

### What Happened?
Two major features implemented today:
1. **CV Gen V2 Enhancements** - Languages, certifications, location fields, 4-category skills
2. **Frontend Job Detail Page** - JD display section, collapsible description, iframe viewer, improved PDF error handling

### What's Staged?
236 files ready to commit. All tests passing (161 CV Gen V2 + 35 frontend).

### Next Immediate Step?
```bash
# 1. Verify tests pass
source .venv/bin/activate
pytest tests/unit/ -q

# 2. Create three atomic commits
git add src/layer6_v2/ tests/unit/test_layer6_v2_*.py data/
git commit -m "feat(cv-gen-v2): Add languages, certifications, location, 4-category skills

Languages support in header
Certifications in education section
Location field in role bullets
4-category skills (Leadership, Technical, Platform, Delivery)
JD keyword integration (79% coverage)
All 161 tests passing"

git add frontend/ frontend/tests/
git commit -m "feat(frontend): Add JD display, collapsible description, iframe viewer

Extracted JD fields display (7 sections)
Collapsible job description with 200-char preview
Iframe viewer Phase 1 (loading, error handling, fallback)
Improved PDF export error handling
35 new unit tests"

git add plans/ reports/
git commit -m "docs: Update missing.md and planning documents for Session 2025-11-30"
```

---

## Architecture at a Glance

```
Job (MongoDB)
    ↓
Layer 1: Intake → Layer 1.4: JD Extraction (NEW - structured requirements)
    ↓
Layer 2: Pain Points → Layer 2.5: STAR Selection → Layer 3: Research → Layer 4: Fit
    ↓
Layer 5: Contact Discovery → Layer 6: CV Generation V2 (NEW - 6-phase pipeline)
    ↓
CV Gen V2 Pipeline:
  1. Layer 1.4: JD Extractor → structured requirements
  2. CV Loader → load pre-split roles
  3. Per-Role Generator → bullets per role + QA
  4. Stitcher → deduplication + word budget
  5. Header Generator → profile + 4-category skills (ENHANCED)
  6. Grader + Improver → multi-dimensional grading
    ↓
Layer 7: Publisher → Google Drive/Sheets
    ↓
Output: Personalized CV + Outreach (LinkedIn, Email)
```

---

## Key Configuration

**Feature Flags** (Active):
```bash
ENABLE_CV_GEN_V2=true              # Use new 6-phase pipeline (default)
ENABLE_JD_EXTRACTOR=true          # Use structured JD extraction (default)
DEFAULT_MODEL=gpt-4o              # Primary LLM
USE_ANTHROPIC=False               # Anthropic credits depleted
```

**Running the Pipeline**:
```bash
# Local (development)
python src/cli.py process <job_id> --verbose

# Via Runner (production)
curl -X POST http://72.61.92.76:8000/process \
  -H "Authorization: Bearer $RUNNER_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "<mongo_id>"}'
```

---

## Test Command Reference

```bash
# All unit tests (fast, mocked)
pytest tests/unit/ -q

# CV Gen V2 only
pytest tests/unit/test_layer6_v2_*.py -v

# Frontend only
pytest frontend/tests/ -v

# Specific test
pytest tests/unit/test_layer6_v2_orchestrator.py::test_full_pipeline -v

# With coverage
pytest tests/unit/ --cov=src --cov-report=term-missing
```

---

## File Locations (Memory Aid)

| Component | Location |
|-----------|----------|
| CV Gen V2 orchestrator | `src/layer6_v2/orchestrator.py` |
| JD Extractor | `src/layer1_4/jd_extractor.py` |
| Role metadata | `data/master-cv/role_metadata.json` |
| Role markdown | `data/master-cv/roles/01_*.md` to `06_*.md` |
| Frontend job page | `frontend/templates/job_detail.html` |
| CV editor JavaScript | `frontend/static/js/cv-editor.js` |
| Pipeline workflow | `src/workflow.py` |
| Config | `src/common/config.py` |

---

## Active Blockers & Notes

1. **Anthropic Credits Depleted**
   - Mitigation: Using gpt-4o (OpenRouter)
   - Impact: CV generation works but quality may vary
   - Workaround: Add credits or set USE_ANTHROPIC=false

2. **Changes Not Deployed**
   - Status: Staged locally, not yet on VPS/Vercel
   - Next step: Push to GitHub, trigger CI/CD

3. **Layer 5 Null Handling**
   - Fix applied but needs production testing
   - Watch for LinkedIn data edge cases

---

## Common Tasks

### Run Full Pipeline for One Job
```bash
source .venv/bin/activate
python src/cli.py process <job_id> --verbose
```

### Test CV Gen V2 Specifically
```bash
pytest tests/unit/test_layer6_v2_*.py -v --tb=short
```

### Deploy to VPS
```bash
git push origin main
# GitHub Actions will build and deploy automatically
# Monitor: https://github.com/ala0001t/job-search/actions
```

### Check Runner Health
```bash
curl http://72.61.92.76:8000/health
```

### View MongoDB Job Document
```python
from pymongo import MongoClient
from os import getenv

client = MongoClient(getenv('MONGODB_URI'))
db = client[getenv('MONGO_DB_NAME')]
job = db['level-2'].find_one({'_id': ObjectId('<job_id>')})
print(job)
```

---

## Debugging Checklist

- [ ] Tests passing locally? `pytest tests/unit/ -q`
- [ ] Environment variables set? `env | grep -E "MONGO|RUNNER|ENABLE"`
- [ ] Runner service running? `curl http://72.61.92.76:8000/health`
- [ ] MongoDB accessible? Check connection string
- [ ] LLM model accessible? Check OpenRouter/Anthropic keys
- [ ] Frontend deployed? Check Vercel dashboard
- [ ] CI/CD logs? Check GitHub Actions

---

## Next Priority Tasks

1. **Commit changes** (5-10 min) ← START HERE
2. **Structured logging** (4-6 hours) ← After commits
3. **LLM retry policy** (1-2 hours) ← Quick win
4. **Deploy to production** (5-10 min) ← After testing
5. **Bug fixes** (#4, #5, #9) ← As bandwidth allows

See full briefing in `2025-11-30-session-continuity.md` for detailed context.
