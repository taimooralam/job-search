# Job Intelligence Pipeline - Roadmap

## Vision vs Reality: What We're Building

### 🎯 **FULL VISION** (The Opportunity Dossier)
Your `sample-dossier.txt` shows the **comprehensive end goal**:
- 10-section Opportunity Dossier with deep company intelligence
- Company signals (acquisitions, funding, growth, leadership changes)
- Hiring reasoning and timing significance analysis
- Strategic pain point analysis (needs, risks, success metrics)
- People Mapper with 8-12 contacts (primary + secondary)
- Per-person outreach (LinkedIn message + email template for EACH contact)
- Validation metadata for each section
- Rich formatting and professional presentation

**This is what you've already built in n8n over months of iteration.**

---

### 📦 **TODAY'S GOAL** (16 Nov - Minimal Vertical Slice)
**Prove the LangGraph architecture works end-to-end** with simplified outputs:

| Layer | Full Vision | Today's Scope |
|-------|-------------|---------------|
| **Layer 2: Pain Points** | Strategic analysis (pain points, needs, risks, metrics) | 3-5 bullet points |
| **Layer 3: Company Research** | Signals, timing, "why now", industry keywords | 2-3 sentence summary |
| **Layer 4: Opportunity Mapper** | Hiring reasoning, timing significance, signal analysis | Simple fit score (0-100) + 2-3 sentence rationale |
| **Layer 5: People Mapper** | 8-12 contacts with personalized outreach each | ❌ SKIP for today |
| **Layer 6: Generator** | Cover letter + tailored CV + per-person templates | Simple 3-paragraph cover letter + basic CV |
| **Layer 7: Publisher** | Comprehensive dossier + CV + metadata | Cover letter + CV to Drive, log to Sheets |

**Success Criteria Today**:
- ✅ ONE job from MongoDB processes successfully
- ✅ Each layer runs and updates state
- ✅ Outputs saved to Google Drive
- ✅ Row logged in Google Sheets
- ✅ LangSmith shows full trace
- ✅ No secrets in code

---

### 🗺️ **FUTURE PHASES** (After Today)

#### **Phase 1.3: Immediate Improvements** (Week 1)
**Job List Enhancements:**
- ✅ Add time-based filtering to `list_jobs.py`:
  - `--last-hours N` - Jobs from last N hours
  - `--last-days N` - Jobs from last N days
  - `--last-minutes N` - Jobs from last N minutes
  - Filter by `createdAt` field in MongoDB

**Output Improvements:**
- ✅ Generate complete Opportunity Dossier as `dossier.txt`:
  - Save to `applications/<company_name>/dossier.txt`
  - Include all layer outputs in structured format
  - Match `sample-dossier.txt` structure (simplified version)
- ✅ Save CV to `applications/<company_name>/CV_<company>.docx`
- ✅ Create local `applications/` folder structure (not just temp files)

**MongoDB Integration:**
- ✅ Store generated outputs back to MongoDB `level-2` collection:
  - Add fields: `generated_dossier`, `cover_letter`, `fit_analysis`
  - Update job document with pipeline results
  - Add `pipeline_run_at` timestamp
  - Preserve existing fields (embeddings, score, etc.)

**LinkedIn Job ID Handling:**
- ✅ Assume all `jobId` values are LinkedIn job IDs
- ✅ Update job URLs to use LinkedIn format: `https://www.linkedin.com/jobs/view/{jobId}`
- ✅ Document LinkedIn job ID assumptions in code

**LangSmith Observability:**
- ✅ Add comprehensive guide: `docs/langsmith-usage.md`
- ✅ Document how to view traces in LangSmith dashboard
- ✅ Explain trace analysis, debugging, and performance monitoring
- ✅ Add examples of finding slow layers and errors

#### **Phase 2: Rich Company Intelligence** (Week 2)
- Implement full company signals extraction (acquisitions, funding, leadership)
- Add "why now" timing analysis
- Implement hiring reasoning logic
- Add industry classification and keywords

####  **Phase 3: Strategic Pain Point Analysis** (Week 2-3)
- Expand pain points to include:
  - Strategic needs
  - Risks if unfilled
  - Success metrics
- Enhance prompts with domain-specific templates

#### **Phase 4: People Mapper** (Week 3-4)
- LinkedIn search via FireCrawl/API
- Identify primary contacts (CEO, hiring managers, department heads)
- Identify secondary contacts (team members, adjacent roles)
- Generate per-person outreach templates

#### **Phase 5: Full Dossier Format** (Week 4-5)
- Implement 10-section dossier structure
- Add validation metadata per section
- Professional formatting (markdown → PDF)
- Query logging (Firecrawl searches used)

#### **Phase 6: Production Features** (Week 5-6)
- Batch processing (50 jobs/day)
- Error recovery and retries
- Scheduling (cron/daemon mode)
- Telegram notifications
- Cost optimization

---

## Why Start Simple?

**Iterative Development** > Big Bang
- ✅ Validate LangGraph architecture quickly
- ✅ Test all integrations (MongoDB, FireCrawl, OpenAI, Google APIs)
- ✅ Establish CI/CD and testing patterns
- ✅ Learn LangSmith observability
- ✅ Build confidence before complexity

**Your n8n workflow evolved over months**. We'll replicate that evolution in LangGraph, but with:
- Better error handling
- Clearer state management
- Easier debugging (LangSmith)
- Scalable architecture

---

## Current Status (16 Nov)

✅ **Phase 1.1: Foundation** (DONE)
- [x] Project structure (`src/`, `scripts/`, `tests/`)
- [x] Dependencies installed (`requirements.txt`)
- [x] Environment setup (`.env`, `.gitignore`)
- [x] Google Cloud service account
- [x] All API keys configured

✅ **Phase 1.2: Core Implementation** (DONE - 16 Nov)
- [x] State schema (`src/common/state.py`)
- [x] Config loader (`src/common/config.py`)
- [x] Layer 2: Pain-Point Miner (basic) - ✅ Tested
- [x] Layer 3: Company Researcher (basic) - ✅ Tested with FireCrawl
- [x] Layer 4: Opportunity Mapper (basic) - ✅ Tested
- [x] Layer 6: Outreach + CV Generator (basic) - ✅ Tested
- [x] Layer 7: Output Publisher - ✅ Tested (folders + Sheets)
- [x] LangGraph workflow - ✅ Working
- [x] CLI entry point - ✅ `run_pipeline.py`
- [x] End-to-end test with real MongoDB job - ✅ Completed

**Test Results:**
- ✅ Processed job 4335554955 from MongoDB `level-2` collection
- ✅ All 5 layers executed successfully
- ✅ Generated pain points, company research, fit score (30/100), cover letter, CV
- ✅ Logged to Google Sheets (row 5)
- ✅ Created Drive folder structure
- ⚠️ File uploads failed (service account quota) - non-blocking

🔄 **Phase 1.3: Immediate Improvements** (NEXT - Week 1)
- [ ] Time-based job filtering (`--last-hours`, `--last-days`)
- [ ] Generate complete `dossier.txt` file
- [ ] Save outputs to `applications/<company>/` folder locally
- [ ] Store generated content back to MongoDB `level-2`
- [ ] Document LangSmith usage guide
- [ ] Standardize LinkedIn job ID handling

---

## Key Principles

1. **Start simple, iterate often**
2. **Working code > comprehensive docs**
3. **Test integrations early**
4. **Commit frequently**
5. **Use LangSmith for everything**
6. **Don't replicate n8n exactly - improve on it**

---

## Questions for Later

- Should we generate PDF dossiers or markdown?
- What's the best format for per-person outreach storage?
- How to handle rate limits at scale (50 jobs/day)?
- Should we add a review UI or keep it CLI?
- Telegram vs email vs Slack for notifications?
