# Job Intelligence Pipeline - Architecture

**Last Updated**: 2025-11-26

---

## Overview

Python-based LangGraph pipeline that processes job postings from MongoDB to generate hyper-personalized CVs, cover letters, and outreach packages. Uses master CV grounding to prevent hallucination.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SYSTEM ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐         │
│  │ Vercel       │     │ VPS Runner       │     │ MongoDB Atlas    │         │
│  │ (Frontend)   │────►│ (FastAPI)        │────►│                  │         │
│  │ Flask/HTMX   │ SSE │ subprocess exec  │     │ level-2 jobs     │         │
│  └──────────────┘     └────────┬─────────┘     │ company_cache    │         │
│                                │               │ star_records     │         │
│                                ▼               └──────────────────┘         │
│                    ┌───────────────────────┐                                │
│                    │  LangGraph Pipeline   │                                │
│                    │  (src/workflow.py)    │                                │
│                    └───────────────────────┘                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Execution Surfaces

| Surface | Location | Description |
|---------|----------|-------------|
| **CLI** | `scripts/run_pipeline.py` | Direct pipeline execution: `python scripts/run_pipeline.py --job-id <id>` |
| **Runner Service** | `runner_service/app.py` | FastAPI wrapper with subprocess execution, log streaming, JWT auth |
| **Frontend** | `frontend/app.py` | Flask/HTMX UI with job browsing, process buttons, health indicators |

---

## Pipeline Layers

### Layer 2: Pain Point Miner
**File**: `src/layer2/pain_point_miner.py`

Extracts structured intelligence from job descriptions:
- **Output**: `pain_points` (5-10), `strategic_needs`, `risks_if_unfilled`, `success_metrics`
- **Validation**: Pydantic schema, JSON-only output
- **Retries**: tenacity with exponential backoff

### Layer 2.5: STAR Selector (Optional)
**File**: `src/layer2_5/star_selector.py`

Selects relevant achievements from knowledge base:
- **Input**: `knowledge-base.md` parsed via `star_parser`
- **Strategy**: LLM-only scoring (no embeddings/graph currently)
- **Output**: 2-3 STARs + `star_to_pain_mapping`
- **Default**: Disabled (`ENABLE_STAR_SELECTOR=false`)

### Layer 3: Company Researcher
**File**: `src/layer3/company_researcher.py`

FireCrawl-based company intelligence:
- **Sources**: Official site, LinkedIn, Crunchbase, news, job URL
- **Output**: `CompanyResearch` (summary + signals with source URLs)
- **Cache**: MongoDB `company_cache` with 7-day TTL

### Layer 3.5: Role Researcher
**File**: `src/layer3/role_researcher.py`

Role context analysis:
- **Output**: Role summary, business impact bullets, "why now" timing
- **Inputs**: Job description, company signals, STAR context (when available)

### Layer 4: Opportunity Mapper
**File**: `src/layer4/opportunity_mapper.py`

Fit analysis and scoring:
- **Output**: `fit_score` (0-100), `fit_rationale`, `fit_category`
- **Behavior**: Warns (doesn't fail) when STAR metrics missing

### Layer 5: People Mapper
**File**: `src/layer5/people_mapper.py`

Contact discovery and outreach generation:

**When FireCrawl enabled** (`DISABLE_FIRECRAWL_OUTREACH=false`):
- SEO-style queries: `site:linkedin.com/in "{company}" recruiter`
- Extracts contacts from search metadata (title, description, URL)
- Parallel searches for recruiters, leadership, hiring managers
- LLM classification into primary (4-6) and secondary (4-6) buckets

**When FireCrawl disabled** (default):
- Generates synthetic role-based contacts (4 primary + 4 secondary)
- Still generates personalized outreach packages

**Outreach Generation**:
- LinkedIn messages: 150-550 chars with Calendly link
- Email: 5-10 word subject + 95-205 word body
- Validation: No emojis, no placeholders, pain-point focus

### Layer 6: Generator
**Files**: `src/layer6/generator.py`, `src/layer6/outreach_generator.py`

CV and Cover Letter generation:

**CV Generator** (`MarkdownCVGenerator`):
- Two-pass flow: Evidence JSON → QA pass
- Uses Anthropic Claude (default) or OpenRouter/OpenAI
- Grounded in master-cv.md
- Output: `applications/<company>/<role>/CV.md`

**Cover Letter Generator** (`CoverLetterGenerator`):
- Multiple validation gates
- Company mention check, JD specificity check
- Master CV grounding validation

### Layer 7: Publisher
**File**: `src/layer7/publisher.py`

Output aggregation and persistence:
- Generates dossier text via `dossier_generator.py`
- Saves to `applications/<company>/<role>/`:
  - `dossier.txt`
  - `cover_letter.txt`
  - `CV.md`
- Updates MongoDB `level-2` with: fit analysis, cover letter, cv_path, selected STARs
- Optional: Google Drive/Sheets upload (`ENABLE_REMOTE_PUBLISHING=true`)

---

## Data Model

### JobState (`src/common/state.py`)

```python
class JobState(TypedDict):
    # Input
    job_id: str
    title: str
    company: str
    job_description: str
    candidate_profile: str  # master-cv.md content

    # Layer 2
    pain_points: List[str]
    strategic_needs: List[str]

    # Layer 2.5 (optional)
    selected_stars: List[Dict]
    star_to_pain_mapping: Dict
    all_stars: List[Dict]

    # Layer 3
    company_research: Dict  # CompanyResearch

    # Layer 3.5
    role_research: Dict

    # Layer 4
    fit_score: int
    fit_rationale: str
    fit_category: str

    # Layer 5
    primary_contacts: List[Dict]
    secondary_contacts: List[Dict]

    # Layer 6
    cv_path: str
    cv_reasoning: str
    cover_letter: str

    # Layer 7
    output_dir: str

    # Meta
    errors: List[str]
```

### MongoDB Collections

| Collection | Purpose | TTL |
|------------|---------|-----|
| `level-2` | Job postings with pipeline results | None |
| `company_cache` | Cached company research | 7 days |
| `star_records` | STAR achievements (future) | None |
| `pipeline_runs` | Run metadata (unused) | None |

---

## Configuration

### Feature Flags (`src/common/config.py`)

| Flag | Default | Effect |
|------|---------|--------|
| `ENABLE_STAR_SELECTOR` | `false` | Skip STAR selection, use master CV directly |
| `DISABLE_FIRECRAWL_OUTREACH` | `true` | Use synthetic contacts instead of FireCrawl |
| `ENABLE_REMOTE_PUBLISHING` | `false` | Save locally only, skip Drive/Sheets |
| `USE_ANTHROPIC` | `true` | Use Anthropic Claude for CV generation |
| `USE_OPENROUTER` | `false` | Use OpenRouter for CV generation |

### LLM Provider Priority (CV Generation)

1. Anthropic Claude (`USE_ANTHROPIC=true`, default)
2. OpenRouter (`USE_OPENROUTER=true`)
3. OpenAI (fallback)

---

## External Services

| Service | Used By | Purpose |
|---------|---------|---------|
| **OpenAI** | Layers 2-5 | General LLM calls |
| **Anthropic** | Layer 6 | CV generation (default) |
| **FireCrawl** | Layer 3, 5 | Web scraping, company research |
| **Google Drive** | Layer 7 | Optional file storage |
| **Google Sheets** | Layer 7 | Optional tracker |

---

## Output Structure

```
applications/
└── <Company_Name>/
    └── <Role_Title>/
        ├── CV.md
        ├── dossier.txt
        ├── cover_letter.txt
        └── contacts_outreach.json (when enabled)
```

---

## Reliability

- **Retries**: tenacity with exponential backoff on all LLM calls
- **Validation**: Pydantic schemas for all structured outputs
- **Caching**: Company research cached 7 days in MongoDB
- **Error handling**: Errors accumulated in state, non-fatal where possible
