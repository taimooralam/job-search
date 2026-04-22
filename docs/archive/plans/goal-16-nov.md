# 16 Nov Goal: Ship Minimal Vertical Slice

## Objective
Deliver a **simplified working slice** of the 7-layer LangGraph pipeline today. Goal is to prove the architecture works end-to-end, NOT to replicate the full dossier format (which is comprehensive and took months in n8n).

**Today's Scope**: Pull ONE job from MongoDB → extract basic pain points → basic company research → simple fit score → generate outreach draft + CV → save to Drive → log to Sheets → LangSmith trace.

**NOT Today**: Full dossier format, people mapper (Layer 5), per-person outreach generation, comprehensive company signals analysis, hiring reasoning, timing significance.

## Constraints & Inputs
- Data: Existing MongoDB jobs (`sample.json` schema; `jobId`/`dedupeKey` for uniqueness), partial candidate profile from LinkedIn/current CV (full knowledge graph later).
- Integrations: FireCrawl, OpenRouter (GPT-4/Anthropic), LangSmith, Google Drive/Sheets, MongoDB. All config via env; no secrets in code.
- Target throughput: 50 jobs/day eventually; accept per-job latency <~5 min with caching/retries.

## Architecture Notes
- Orchestration: LangGraph nodes per layer (2–6) with explicit state passing; retries on API/tool calls; error capture per node; manual review gate before any send.
- Data contracts: Use `sample.json` fields as input contract; outputs include pain points, company summary, fit score, outreach text, tailored CV draft, run metadata.
- Versioning/observability: Tag prompts/models per layer; LangSmith tracing on by default.

## Step-by-Step Plan (Today) - **SIMPLIFIED**
1) **Ingestion**: Node to read ONE job from MongoDB by job_id
2) **Pain-Point Miner (Layer 2)**: LLM prompt extracts **3-5 pain point bullets** (NOT full strategic analysis yet)
3) **Company Researcher (Layer 3)**: FireCrawl fetch company website → LLM generates **2-3 sentence summary** (NOT full signals/timing analysis yet)
4) **Opportunity Mapper (Layer 4)**: Map candidate profile to pain points → **simple fit score 0-100 + 2-3 sentence rationale** (NOT hiring reasoning yet)
5) **SKIP Layer 5 (People Mapper)** for today
6) **Generator (Layer 6)**: Draft **simple cover letter** (3 paragraphs) + **basic tailored CV** (.docx with job-specific header)
7) **Publisher (Layer 7)**: Save cover letter + CV to Drive `/applications/<company>/<role>/` → log row to Sheets → capture LangSmith trace

## What We're NOT Building Today
- ❌ Full Opportunity Dossier format (that's the end goal, not day 1)
- ❌ Company signals, timing analysis, hiring reasoning
- ❌ People Mapper (Layer 5) - no LinkedIn contact search
- ❌ Per-person outreach templates
- ❌ Strategic needs, risks if unfilled, success metrics
- ❌ Validation metadata per section
- ❌ Batch processing (just ONE job)

## Acceptance Today
- For a MongoDB job, pipeline produces pain points, company summary, fit score, outreach draft, and tailored CV draft; saves to Drive; logs to Sheets; LangSmith trace recorded; no secrets hard-coded.

---

## 📊 **Current Progress (16 Nov - Paused)**

### ✅ **COMPLETED**
- All integrations configured (MongoDB, OpenAI, FireCrawl, LangSmith, Google APIs)
- Project structure and dependencies
- State schema (`src/common/state.py`)
- Config loader (`src/common/config.py`)
- **Layer 2: Pain-Point Miner** - DONE & TESTED ✓
- **Layer 3: Company Researcher** - DONE (code complete, not tested)

### 🔄 **NEXT STEPS**
1. Test Layer 3 (5 min)
2. Build Layer 4: Opportunity Mapper (45 min)
3. Build Layer 6: Generator (1.5 hours)
4. Build Layer 7: Publisher (1 hour)
5. Wire LangGraph workflow (45 min)
6. Create CLI (30 min)
7. End-to-end test (30 min)

**Time Remaining**: ~4-5 hours

See `PROGRESS.md` for detailed resume instructions.
