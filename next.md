# Next Steps to Ship Vertical Slice (16 Nov)

## Gap Analysis

### What We Have ✓
- **Documentation**: `goal-16-nov.md`, `architecture.md`, `AGENTS.md`, `requirements.md`
- **Candidate Profile**: `knowledge-base.md` (59KB), `profile.pdf`
- **Sample Job Data**: `sample.json` (MongoDB job schema)
- **Reference**: `sample-n8n-workflow.json` (old workflow), `star_schema.json`
- **Git Repo**: Initialized and ready
- **Project Guidelines**: AGENTS.md with structure, style, testing conventions

### What's Missing ✗
- **No Python code**: Zero implementation (no `src/`, `scripts/`, `tests/`)
- **No project infrastructure**: No `requirements.txt`, no virtual environment, no `.env` setup
- **No LangGraph workflow**: No graph definition, no nodes, no state schema
- **No integrations**: No MongoDB client, FireCrawl calls, OpenAI/OpenRouter setup, Google Drive/Sheets APIs
- **No CLI**: No entry point to run the pipeline
- **No configuration**: No `.env.example`, no secrets management

---

## Next Steps (Sequenced for Today)

### Phase 1: Foundation (30-45 min)

#### 1.1 Create Project Structure
```bash
mkdir -p src/common src/layer2 src/layer3 src/layer4 src/layer6 src/layer7
mkdir -p scripts tests/fixtures docs
touch src/__init__.py src/common/__init__.py
touch src/layer{2,3,4,6,7}/__init__.py
```

#### 1.2 Create `requirements.txt`
```txt
# Core LangGraph
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0
langchain-community>=0.3.0

# Integrations
firecrawl-py>=0.0.16
pymongo>=4.6.0
python-dotenv>=1.0.0

# Output Generation
python-docx>=1.1.0
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.1.1
gspread>=5.12.0

# Dev/Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

#### 1.3 Set Up Python Environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### 1.4 Create `.env.example`
```bash
# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname

# LLM APIs
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
USE_OPENROUTER=false

# Web Scraping
FIRECRAWL_API_KEY=fc-...

# Observability
LANGSMITH_API_KEY=lsv2_...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=job-intelligence-pipeline

# Google APIs
GOOGLE_CREDENTIALS_PATH=./credentials/google-service-account.json
GOOGLE_DRIVE_FOLDER_ID=1abc...
GOOGLE_SHEET_ID=1xyz...

# Candidate Profile
CANDIDATE_PROFILE_PATH=./knowledge-base.md
```

Copy to `.env` and fill in real values (add `.env` to `.gitignore`).

---

### Phase 2: State & Common Utilities (20-30 min)

#### 2.1 Define State Schema (`src/common/state.py`)
```python
from typing import TypedDict, List, Optional

class JobState(TypedDict):
    # Input (from MongoDB)
    job_id: str
    title: str
    company: str
    job_description: str
    job_url: str
    source: str

    # Candidate data
    candidate_profile: str

    # Layer 2: Pain-Point Miner outputs
    pain_points: Optional[List[str]]

    # Layer 3: Company Researcher outputs
    company_info: Optional[str]
    company_url: Optional[str]

    # Layer 4: Opportunity Mapper outputs
    fit_analysis: Optional[str]
    fit_score: Optional[int]  # 0-100

    # Layer 6: Generator outputs
    cover_letter: Optional[str]
    cv_path: Optional[str]

    # Layer 7: Publisher outputs
    drive_url: Optional[str]
    sheet_row_id: Optional[int]

    # Metadata
    run_id: Optional[str]
    errors: Optional[List[str]]
```

#### 2.2 Create Config Loader (`src/common/config.py`)
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI")

    # LLM
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    USE_OPENROUTER = os.getenv("USE_OPENROUTER", "false").lower() == "true"

    # FireCrawl
    FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

    # LangSmith
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true")
    LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "job-intelligence-pipeline")

    # Google
    GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

    # Candidate
    CANDIDATE_PROFILE_PATH = os.getenv("CANDIDATE_PROFILE_PATH", "./knowledge-base.md")
```

---

### Phase 3: Build Layer Nodes (2-3 hours)

#### 3.1 Layer 2: Pain-Point Miner (`src/layer2/pain_point_miner.py`)
**Goal**: Extract 3-5 key challenges from job description using LLM

**Implementation**:
- Load LLM (OpenAI or OpenRouter)
- Prompt: "Given this job description, extract 3-5 key technical challenges or pain points the role needs to address. Return as bullet points."
- Parse response into list
- Return `{"pain_points": [...]}`

**Error Handling**: Retry on API failures, default to empty list on parse errors

---

#### 3.2 Layer 3: Company Researcher (`src/layer3/company_researcher.py`)
**Goal**: Scrape company info using FireCrawl, summarize with LLM

**Implementation**:
- Extract company name from job data
- Use FireCrawl to fetch company website (construct URL or search)
- Extract "About Us" or homepage text
- LLM prompt: "Summarize this company in 2-3 sentences: what they do, size, notable facts."
- Return `{"company_info": "...", "company_url": "..."}`

**Error Handling**: If FireCrawl fails, use LLM general knowledge as fallback

---

#### 3.3 Layer 4: Opportunity Mapper (`src/layer4/opportunity_mapper.py`)
**Goal**: Map candidate profile to pain points, compute fit score

**Implementation**:
- Load `knowledge-base.md` into context
- Prompt: "Given candidate background and job pain points, explain how candidate addresses each point. Rate overall fit 0-100."
- Parse fit analysis and score
- Return `{"fit_analysis": "...", "fit_score": 85}`

**Error Handling**: Default score to 50 if parsing fails

---

#### 3.4 Layer 6: Outreach Generator (`src/layer6/outreach_generator.py`)
**Goal**: Draft personalized cover letter/email

**Implementation**:
- Synthesize: company_info + pain_points + fit_analysis
- Prompt: "Draft a professional cover letter (3 paragraphs) highlighting how the candidate solves the company's challenges."
- Return `{"cover_letter": "..."}`

**Error Handling**: Retry on API failure, log errors

---

#### 3.5 Layer 6: CV Generator (`src/layer6/cv_generator.py`)
**Goal**: Create tailored CV .docx

**Implementation** (MVP):
- Use python-docx to create simple document
- Add tailored summary paragraph (LLM-generated based on fit_analysis)
- Append base CV content from `profile.pdf` or text version
- Save to `/tmp/cv_{job_id}.docx`
- Return `{"cv_path": "/tmp/cv_xyz.docx"}`

**Note**: For today, a simple text-based CV is acceptable

---

#### 3.6 Layer 7: Output Publisher (`src/layer7/output_publisher.py`)
**Goal**: Upload to Drive, log to Sheets, persist metadata

**Implementation**:
- **Google Drive**:
  - Authenticate using service account JSON
  - Create folder `/applications/{company}/{role}/` if not exists
  - Upload CV .docx and cover letter .txt
  - Get shareable link
- **Google Sheets**:
  - Append row: `[Date, Company, Role, Fit Score, Drive URL, Status]`
  - Return row ID
- **MongoDB** (optional for today): Update job record with `processed: true`
- Return `{"drive_url": "...", "sheet_row_id": 123}`

**Error Handling**: Log failures, don't block pipeline if non-critical

---

### Phase 4: LangGraph Workflow (45-60 min)

#### 4.1 Create Workflow (`src/workflow.py`)
**Steps**:
1. Import all node functions
2. Define `StateGraph` with `JobState`
3. Add nodes: `pain_point_miner`, `company_researcher`, `opportunity_mapper`, `outreach_generator`, `cv_generator`, `output_publisher`
4. Add edges in sequence: START → layer2 → layer3 → layer4 → layer6a (outreach) → layer6b (cv) → layer7 → END
5. Compile graph
6. Export `run_pipeline(job_data: dict) -> JobState` function

**Tracing**: Enable LangSmith via environment variables (already set in config)

---

### Phase 5: CLI Entry Point (20-30 min)

#### 5.1 Create CLI (`scripts/run_pipeline.py`)
```python
import argparse
from pymongo import MongoClient
from src.workflow import run_pipeline
from src.common.config import Config

def load_job_from_mongo(job_id: str) -> dict:
    """Fetch job from MongoDB by job_id"""
    client = MongoClient(Config.MONGODB_URI)
    db = client.get_database()  # Use default DB
    jobs = db.jobs  # Collection name
    job = jobs.find_one({"jobId": job_id})
    if not job:
        raise ValueError(f"Job {job_id} not found")
    return job

def load_candidate_profile() -> str:
    """Load candidate profile from knowledge-base.md"""
    with open(Config.CANDIDATE_PROFILE_PATH, 'r') as f:
        return f.read()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True, help="MongoDB job ID")
    args = parser.parse_args()

    # Load job and candidate data
    job = load_job_from_mongo(args.job_id)
    profile = load_candidate_profile()

    # Initialize state
    initial_state = {
        "job_id": job["jobId"],
        "title": job["title"],
        "company": job["company"],
        "job_description": job["job_description"],
        "job_url": job["jobURL"],
        "source": job["source"],
        "candidate_profile": profile,
    }

    # Run pipeline
    print(f"Processing job: {job['title']} at {job['company']}")
    result = run_pipeline(initial_state)

    # Print results
    print(f"\n✓ Fit Score: {result['fit_score']}/100")
    print(f"✓ Drive URL: {result['drive_url']}")
    print(f"✓ Sheet Row: {result['sheet_row_id']}")
    print(f"✓ LangSmith Trace: Check your LangSmith dashboard")
```

---

### Phase 6: Testing & Validation (30-45 min)

#### 6.1 Run End-to-End Test
```bash
source .venv/bin/activate
python scripts/run_pipeline.py --job-id 4334580868
```

**Expected Output**:
- Console logs showing each layer execution
- Drive folder created with CV and cover letter
- Sheets row appended
- LangSmith trace URL

#### 6.2 Verify Acceptance Criteria
- [ ] Pain points extracted (3-5 bullets)
- [ ] Company summary generated
- [ ] Fit score computed (0-100)
- [ ] Outreach draft created
- [ ] Tailored CV saved
- [ ] Files uploaded to Drive
- [ ] Tracking row in Sheets
- [ ] LangSmith trace visible
- [ ] No secrets in code (all from .env)

#### 6.3 Handle Errors
- Add retry logic for API calls (use `tenacity` library)
- Log errors to `errors` field in state
- Graceful degradation (e.g., skip company research if FireCrawl fails)

---

## Time Estimate (Total: ~6-8 hours)

| Phase | Task | Time |
|-------|------|------|
| 1 | Foundation (structure, deps, config) | 30-45 min |
| 2 | State & utilities | 20-30 min |
| 3 | Layer nodes (6 nodes × 20-30 min each) | 2-3 hours |
| 4 | LangGraph workflow | 45-60 min |
| 5 | CLI entry point | 20-30 min |
| 6 | Testing & debugging | 30-45 min |
| **Total** | | **5-7 hours** |

---

## Success Criteria (Today)

Run this command:
```bash
python scripts/run_pipeline.py --job-id 4334580868
```

And get:
1. ✅ Console output showing each layer completing
2. ✅ Google Drive folder with CV + cover letter
3. ✅ Google Sheets new row with job details
4. ✅ LangSmith trace showing full execution
5. ✅ No errors blocking the pipeline
6. ✅ `.env` file not committed (in `.gitignore`)

---

## After Today (Future Improvements)

- **Batch Processing**: Loop through multiple jobs from MongoDB
- **Layer 5**: People Mapper (LinkedIn search)
- **Better CV Generation**: Template-based with styling
- **Retry & Rate Limiting**: Robust error handling
- **Tests**: Unit tests for each layer, integration tests
- **Review Gate**: Manual approval before sending
- **Monitoring**: Slack/Telegram alerts for failures
- **Deployment**: Dockerize and deploy to VPS

---

## Quick Start

```bash
# 1. Set up environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env
# Edit .env with real API keys

# 3. Run pipeline
python scripts/run_pipeline.py --job-id 4334580868
```
