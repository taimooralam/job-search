# Complete Job Intelligence Pipeline - Full Implementation Roadmap

**Approach**: Waterfall with clear phases, dependencies, and quality gates
**Target**: Production-ready system matching/exceeding n8n workflow capabilities
**Principle**: Quality-first, zero hallucination tolerance, hyper-personalized outputs

> **Operational note (current build)**  
> - STAR selector is temporarily disabled via `Config.ENABLE_STAR_SELECTOR=False`; downstream layers lean on the master CV instead of STAR citations.  
> - Google Drive/Sheets publishing is switched off (`ENABLE_REMOTE_PUBLISHING=False`); outputs stay in `./applications/<company>/<role>/`.  
> - CV generation now runs two-pass (JSON evidence → QA'd bullets) with JD text injected; outputs `CV.md` (no `.docx`) via OpenRouter `CV_MODEL` (`anthropic/claude-3-5-haiku-20241022` by default).  
> - FireCrawl queries use privacy-safe natural language, and the original job URL is scraped into the dossier when available.  
> - People discovery now falls back to three master-CV-grounded cover letters if no contacts are found.  
> - FireCrawl outreach discovery for People Mapper is disabled by default (`DISABLE_FIRECRAWL_OUTREACH=true`); role-based synthetic contacts and generic outreach are generated without scraping.  

---

## Phase 1: Foundation & Core Infrastructure (Week 1)

### 1.1 Project Infrastructure Setup
**Duration**: 2 days
**Dependencies**: None

**Deliverables**:
- ✅ Complete environment configuration with `.env` validation
- ✅ MongoDB Atlas schema finalized with all collections:
  - `level-2`: Job storage with embeddings and metadata
  - `company_cache`: 7-day TTL cache for company research
  - `star_records`: Parsed STAR library with metadata
  - `pipeline_runs`: Audit trail of all executions
- ✅ Google Drive/Sheets integration with service account
- ✅ LangSmith tracing configured for all layers
- ✅ FireCrawl API integration with rate limiting
- ✅ OpenRouter integration (GPT-4o + Anthropic fallback)
- ✅ Local directory structure: `applications/<company>/<role>/`
- ✅ Logging infrastructure: Structured JSON logs with log levels
- ✅ Git hooks for pre-commit linting (black, mypy, flake8)

**Quality Gate**:
- All secrets loaded from environment
- `Config.validate()` fails fast with actionable errors
- Test connectivity to all external services
- Zero hard-coded credentials in codebase

### 1.2 State Management & Type System
**Duration**: 1 day
**Dependencies**: 1.1

**Deliverables**:
- ✅ Complete `JobState` TypedDict with all fields:
  - Metadata: `run_id`, `created_at`, `updated_at`, `status`, `tier`
  - Job data: `job_id`, `title`, `company`, `location`, `description`, `criteria`
  - Layer 1.5: `application_form_fields`
  - Layer 2: `pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics`
  - Layer 2.5: `selected_stars`, `star_to_pain_mapping`, `star_selection_reasoning`
  - Layer 3: `company_research` (summary, signals, url), `role_research` (summary, business_impact, why_now)
  - Layer 4: `fit_score`, `fit_rationale`, `fit_category`
  - Layer 5: `primary_contacts`, `secondary_contacts`
  - Layer 6a: `cover_letter`, `cv_path`, `cv_reasoning`
  - Layer 6b: `outreach_packages` (per-lead messages)
  - Layer 7: `dossier_path`, `drive_folder_url`, `sheets_row_id`
  - Error tracking: `errors`, `warnings`, `validation_flags`
- ✅ Helper types: `STARRecord`, `Contact`, `OutreachPackage`, `FormField`, `CompanyResearch`, `RoleResearch`
- ✅ State validation functions with Pydantic schemas
- ✅ State serialization/deserialization for MongoDB persistence

**Quality Gate**:
- All state fields documented with docstrings
- Type annotations pass mypy strict mode
- State can round-trip to/from MongoDB without data loss

---

## Phase 2: STAR Library & Candidate Knowledge Base (Week 1)

### 2.1 Canonical STAR Schema, Parser & Structured Knowledge Base
**Duration**: 2 days
**Dependencies**: 1.2

**Deliverables**:
- ✅ Human-authored source of truth: `knowledge-base.md`:
  - You maintain all achievements as human-friendly **STAR RECORD** sections with rich fields:
    - ID, COMPANY, ROLE TITLE, PERIOD, DOMAIN AREAS, BACKGROUND CONTEXT, SITUATION, TASK, ACTIONS, RESULTS, IMPACT SUMMARY, CONDENSED VERSION, ATS KEYWORDS, CATEGORIES, HARD SKILLS, SOFT SKILLS, METRICS, TARGET ROLES, SENIORITY WEIGHTS, METADATA.
  - This file remains your primary editing surface for adding and refining STARs.
- ✅ Canonical `STARRecord` schema for the pipeline:
  ```python
  class STARRecord(TypedDict):
      id: str
      company: str
      role_title: str
      period: str  # e.g., "2019–2022"
      domain_areas: List[str]
      background_context: str
      situation: str
      tasks: List[str]
      actions: List[str]
      results: List[str]
      impact_summary: str
      condensed_version: str
      ats_keywords: List[str]
      categories: List[str]
      hard_skills: List[str]
      soft_skills: List[str]
      metrics: List[str]                 # Quantified achievements, derived from RESULTS / METRICS section
      pain_points_addressed: List[str]   # 1–3 job/manager pains this STAR solves
      outcome_types: List[str]           # e.g. ["cost_reduction", "risk_reduction", "velocity_increase"]
      target_roles: List[str]            # From TARGET ROLES section
      metadata: Dict[str, Any]           # Seniority weights, sources, versioning, free-form tags
      embedding: Optional[List[float]]  # For hybrid selection
  ```
- ✅ `src/common/star_parser.py`:
  - Parse `knowledge-base.md` → canonical `STARRecord` objects.
  - Normalize free-text fields into lists where needed (tasks, actions, results, metrics, hard/soft skills, categories).
  - Validate that each STAR has: ID, company, role_title, period, at least one metric, and at least one `pain_points_addressed` item.
  - Lenient parsing: skip malformed records with warnings but never crash the pipeline.
- ✅ Knowledge-graph-friendly storage:
  - Store canonical STARs in MongoDB `star_records` collection.
  - Derive graph edges (STAR → Company/Role/DomainArea/HardSkill/SoftSkill/PainPoint/OutcomeType/Metric/TargetRole) from the canonical fields.
  - Optionally persist a JSON export (`star_records.json`) for offline inspection and tests.
- ✅ One-time (and incremental) embedding generation for all STAR records using OpenAI `text-embedding-3-small` (or equivalent):
  - At least two embeddings per STAR: one for `condensed_version`, one for `metrics + ats_keywords`.
  - Store embeddings on the `STARRecord` itself under `embedding` (and/or a separate `embeddings` subfield).
- ✅ CLI tool: `scripts/parse_stars.py` to regenerate canonical STAR library from `knowledge-base.md` and refresh the `star_records` collection.
- ✅ Offline STAR Curator AI agent:
  - Implemented as a Codex CLI profile (recommended model: `o3-mini`, alternative: `gpt-4.1`).
  - Responsibilities:
    - Read `knowledge-base.md` and detect incomplete STARs (missing metrics, pain_points_addressed, skills, etc.).
    - Interactively prompt you for missing attributes and clarifications, then rewrite each `STAR RECORD` block into the canonical format.
    - Invoke `scripts/parse_stars.py` (or emit a diff) to keep `star_records` in sync with the edited knowledge base.

**Quality Gate**:
- All 11 STAR records parsed successfully
- Each STAR has ≥1 quantified metric and ≥1 `pain_points_addressed` entry
- Embeddings generated and stored
- Graph edges derivable from canonical fields (no orphan references)
- pytest tests for parser edge cases (missing fields, malformed markdown, duplicate IDs), plus round-trip tests from `knowledge-base.md` → `STARRecord` → JSON/Mongo

### 2.2 STAR Knowledge Graph & Hybrid Selector
**Duration**: 2 days
**Dependencies**: 2.1

**Deliverables**:
- ✅ `src/layer2_5/star_selector.py`:
  - **Graph + embedding-based filter**:
    - Represent STARs and related entities (Company, Role, DomainArea, HardSkill, SoftSkill, PainPoint, OutcomeType) as a simple knowledge graph over the `star_records` collection.
    - Given a job’s `pain_points`, `strategic_needs`, `success_metrics`, and basic metadata (title, company, domain), compute:
      - A candidate set of 5–8 STAR IDs via:
        - Exact/enum matches on domain_areas, categories, hard_skills, outcome_types.
        - Overlap between job pains and `pain_points_addressed`.
        - Cosine similarity between job text and STAR embeddings.
  - **LLM-based ranker**:
    - Use an LLM (GPT-4o / `o3-mini`) to score candidates (0–10) against each pain point + strategic need using only:
      - `condensed_version`, `metrics`, `hard_skills`, `pain_points_addressed`, and `outcome_types`.
    - Enforce JSON-only output summarizing, per STAR:
      - relevance scores,
      - which pains it addresses and why,
      - any diversity constraints (e.g., prefer different companies/roles).
  - **Selection logic**:
    - Aggregate scores across pains/needs and select top 2–3 STARs with highest job-level relevance.
    - Enforce diversity rules (e.g., avoid selecting 3 STARs from the same company unless unavoidable).
  - **Mapping output**:
    - Explicit `star_to_pain_mapping` dict `{pain_point_id: [star_ids...]}`.
    - `star_selection_reasoning`: short explanation of why each STAR was chosen and how it supports “pain → proof → plan”.
- ✅ Configurable selection strategy:
  - `LLM_ONLY`: Skip embedding filter (simple, slower)
  - `HYBRID`: Graph + embedding filter + LLM ranker (recommended)
  - `EMBEDDING_ONLY`: Pure cosine similarity (fast, less accurate)
- ✅ Caching:
  - Cache STAR selections per `job_id` + `pain_points_hash` in MongoDB (or `pipeline_runs`).
  - Persist the candidate set, scores, and mappings for auditability and offline analysis.

**Quality Gate**:
- For 5 test jobs, STAR selector returns sensible 2–3 STARs with clear mappings
- LLM ranker prompt forbids hallucination (only use provided STAR text and parsed fields)
- Selection reasoning cites specific pain point phrases and real STAR metrics
- pytest tests with mocked LLM responses and synthetic STAR libraries
- Performance: <3s for hybrid selection per job (after embeddings cached)

---

## Phase 3: Layer 1 & 1.5 - Input Collection & Application Form Mining (Week 2)

### 3.1 Layer 1: Job Input Collector
**Duration**: 1 day
**Dependencies**: 1.2

**Deliverables**:
- ✅ `src/layer1/input_collector.py`:
  - Fetch jobs from MongoDB `level-2` collection
  - CLI filters: `--latest N`, `--location "City, Country"`, `--job-ids "id1,id2"`
  - Batch mode: Fetch up to 50 jobs matching criteria
  - Time-based filtering: `posted_at` within last N days
  - Deduplication: Skip jobs already processed (check MongoDB `pipeline_run_at`)
- ✅ Job prioritization:
  - Sort by `score` (descending) then `posted_at` (descending)
  - Respect `tier` if pre-set in MongoDB
- ✅ Output: List of `JobState` objects ready for pipeline

**Quality Gate**:
- Can fetch jobs with complex filters (location + date + score threshold)
- Deduplication prevents re-processing
- Clear CLI messages for "no matching jobs"

### 3.2 Layer 1.5: Application Form Field Miner
**Duration**: 2 days
**Dependencies**: 3.1

**Deliverables**:
- ✅ `src/layer1_5/form_miner.py`:
  - FireCrawl scrape of `job_url` (not company site, actual job posting)
  - LLM extraction of application form fields:
    - Field labels/questions
    - Field types (text, textarea, url, file, checkbox, select)
    - Required vs optional
    - Character/word limits
    - Default values or hints
  - JSON-only output schema
- ✅ Output to `JobState.application_form_fields: List[FormField]`
- ✅ Save to file: `applications/<company>/<role>/application_form_fields.txt`
- ✅ Graceful degradation: If scrape fails or no form found, continue with empty list

**Quality Gate**:
- For 5 test LinkedIn job URLs, extracts at least 3-5 form fields
- Output is human-readable checklist
- LLM prompt forbids inventing fields not in scraped HTML

---

## Phase 4: Layer 2 - Pain-Point Miner (Week 2)

### 4.1 Enhanced Pain-Point Miner
**Duration**: 2 days
**Dependencies**: 1.2

**Deliverables**:
- ✅ `src/layer2/pain_point_miner.py` (enhanced):
  - JSON-only output (no text outside JSON)
  - Four categories:
    1. `pain_points`: 3-6 core business challenges driving this hire
    2. `strategic_needs`: 3-6 strategic outcomes the company seeks
    3. `risks_if_unfilled`: 2-4 risks/costs of leaving role unfilled
    4. `success_metrics`: 3-5 measurable outcomes for the role
  - Prompt engineering:
    - Emphasize "why now" and business context
    - Forbid generic boilerplate (e.g., "team player")
    - Require specificity to company/role/industry
  - Temperature: 0.3 (analytical)
  - Model: GPT-4o
- ✅ Validation: JSON schema check, minimum bullet counts
- ✅ Retry logic: 3 attempts with exponential backoff
- ✅ Store in `JobState` with all four fields

**Quality Gate**:
- For 5 test jobs, output is JSON-only, well-structured
- Pain points are specific (not "strong communication skills")
- pytest tests with mocked LLM responses + schema validation
- Hallucination test: LLM doesn't invent company facts not in JD

---

## Phase 5: Layer 3 - Company & Role Researcher (Week 3)

### 5.1 Company Researcher with Multi-Source Scraping
**Duration**: 3 days
**Dependencies**: 4.1

**Deliverables**:
- ✅ `src/layer3/company_researcher.py` (full version):
  - **Multi-query FireCrawl scraping**:
    1. `${company} official site`
    2. `${company} LinkedIn`
    3. `${company} Crunchbase`
    4. `${company} news funding acquisition`
  - **Signal extraction**:
    - Funding rounds (amount, date, investors)
    - Acquisitions (target, date, rationale)
    - Leadership changes (new C-suite, board members)
    - Product launches (new offerings, markets)
    - Partnerships (strategic alliances)
    - Growth indicators (headcount, revenue, expansion)
  - **LLM summarization**:
    - 2-3 sentence company summary (what they do, market position)
    - List of signals with dates and sources
  - **Hallucination controls**:
    - Prompt: "Only use facts from provided scraped text. If unknown, output 'unknown'."
    - JSON-only output for signals (structured, parseable)
    - Source attribution: Each signal tagged with source URL
  - **MongoDB caching**:
    - Store in `company_cache` collection keyed by normalized company name
    - TTL: 7 days
    - Check cache before scraping
- ✅ Output to `JobState.company_research`:
  ```python
  {
    "summary": str,
    "signals": [{"type": str, "description": str, "date": str, "source": str}],
    "url": str
  }
  ```

**Quality Gate**:
- For 5 test companies, retrieves ≥3 signals (or "unknown" if truly not found)
- No hallucinated funding rounds or acquisitions
- Cache hit reduces latency from ~10s to <500ms
- pytest tests with mocked FireCrawl responses

### 5.2 Role Researcher
**Duration**: 2 days
**Dependencies**: 5.1

**Deliverables**:
- ✅ `src/layer3/role_researcher.py`:
  - **FireCrawl queries**:
    - `"${title}" responsibilities ${company}`
    - `"${title}" KPIs ${industry}`
  - **Analysis**:
    - Role summary (2-3 sentences: ownership, scope, team structure)
    - Business impact (how this role drives company outcomes)
    - "Why now?" (timing significance using company signals from Layer 3)
  - **Hallucination controls**: Same as Company Researcher (context-only, no speculation)
  - **JSON-only output** for structured fields
- ✅ Output to `JobState.role_research`:
  ```python
  {
    "summary": str,
    "business_impact": [str],  # 3-5 bullets
    "why_now": str  # 1-2 sentences linking to company signals
  }
  ```

**Quality Gate**:
- "Why now?" explicitly references ≥1 company signal from Layer 3
- Business impact is role-specific (not generic)
- pytest tests with mocked responses

---

## Phase 6: Layer 4 - Opportunity Mapper (Week 3)

### 6.1 Enhanced Opportunity Mapper with STAR Citations
**Duration**: 2 days
**Dependencies**: 2.2, 5.2

**Deliverables**:
- ✅ `src/layer4/opportunity_mapper.py` (enhanced):
  - **Inputs**: Pain points, strategic needs, risks, success metrics, company/role research, `selected_stars` (from Layer 2.5)
  - **LLM analysis**:
    - Fit scoring (0-100) with clear rubric:
      - 90-100: Exceptional fit (3+ STARs directly address pain points)
      - 80-89: Strong fit (2+ STARs align well)
      - 70-79: Good fit (1-2 STARs relevant)
      - 60-69: Moderate fit (adjacent experience)
      - <60: Weak fit (skill gaps present)
    - Rationale (3-5 sentences, with soft quality gates):
      - Should cite ≥1 STAR ID and ≥1 metric where possible
      - Prefer explicit mapping: "STAR #1 (AdTech modernization) addresses pain point #1 (legacy system migration) with 75% incident reduction."
      - Should reference company signals for timing when available
    - Fit category: "exceptional" | "strong" | "good" | "moderate" | "weak"
  - **Output validation (soft)**:
    - Detect when rationale is missing STAR IDs or metrics and surface warnings
    - Detect generic boilerplate (regex for "experience", "skills" without specifics)
    - Do not block fit score generation; treat validation as quality signalling, not a hard failure
  - Temperature: 0.3
  - Model: GPT-4o
- ✅ Store in `JobState`: `fit_score`, `fit_rationale`, `fit_category`

**Quality Gate**:
- For 5 test jobs, most rationales cite specific STAR IDs and metrics
- Generic statements like "strong background" are discouraged and surfaced via warnings
- pytest tests validate that validation helpers correctly flag missing STAR citations/metrics and boilerplate without preventing `fit_score` from being returned

---

## Phase 7: Layer 5 - People Mapper (Week 4)

### 7.1 Complete People Mapper with 8-12 Contacts
**Duration**: 4 days
**Dependencies**: 5.2

**Deliverables**:
- ✅ `src/layer5/people_mapper.py`:
  - Operational override: FireCrawl outreach discovery is disabled by default (`DISABLE_FIRECRAWL_OUTREACH=true`); People Mapper emits role-based synthetic contacts and generic outreach without scraping.
  - **Multi-source contact discovery** (when enabled):
    - FireCrawl queries (LLM-style, keyword-rich):
      1. `best people to contact on LinkedIn for ${company} ${department/function} team (VP Engineering, Directors, Engineering Managers, recruiters, Head of Talent)`
      2. `${company} leadership team and hiring decision makers for ${title}`
      3. `best people to send a cover letter to for ${title} at ${company} (hiring manager, VP Engineering, Director of Engineering, recruiter, Head of Talent)`
      4. `${company} leadership team on Crunchbase (VP Engineering, CTO, Head of Talent, Directors)`
      5. Company careers/about/team pages
    - Parse scraped results for names, titles, LinkedIn URLs
  - **LLM-based contact classification**:
    - Primary contacts (4-6):
      - Hiring manager (direct role owner)
      - Department head (VP/Director level)
      - Team lead (senior IC or manager)
      - Recruiter/TA (talent acquisition)
    - Secondary contacts (4-6):
      - Cross-functional stakeholders
      - Peer roles
      - Executive sponsors
  - **Contact enrichment**:
    - For each contact, extract:
      - `name`, `role`, `linkedin_url`
      - `why_relevant`: 1-2 sentences explaining why to contact them
      - `recent_signals`: Recent posts, promotions, projects (from LinkedIn scrape)
  - **Fallback logic**:
    - If no names found, create role-based targets (e.g., "VP Engineering at ${company}")
  - **JSON-only output**
- ✅ Output to `JobState`:
  ```python
  {
    "primary_contacts": [Contact],  # 4-6
    "secondary_contacts": [Contact]  # 4-6
  }
  ```

**Quality Gate**:
- For 5 test companies, finds ≥4 primary contacts (real names or role-based)
- Each contact has clear `why_relevant`
- No hallucinated names (if unsure, use role-based target)
- pytest tests with mocked FireCrawl responses

---

## Phase 8: Layer 6a - Cover Letter & CV Generator (Week 4-5)

### 8.1 Enhanced Cover Letter Generator
**Duration**: 2 days
**Dependencies**: 6.1

**Deliverables**:
- ✅ `src/layer6/cover_letter_generator.py`:
  - **Inputs**: All layer outputs (pain points, company/role research, fit analysis, `selected_stars`)
  - **Structure**:
    - Paragraph 1: Hook (pain point + why this company)
    - Paragraph 2-3: Proof (2-3 STARs with metrics)
    - Paragraph 4: Plan (90-day vision or call to action)
  - **Constraints (target vs allowed range)**:
    - **Must cite ≥1 quantified achievement** from `selected_stars`
    - Target: 3-4 paragraphs, ~250-350 words total
    - Allowed: 2-5 paragraphs, 180-420 words total (to account for LLM variance while preserving quality)
    - Professional tone (no emojis, no placeholders except `[Your Name]`)
    - End with: candidate email + Calendly URL `https://calendly.com/taimooralam/15min`
  - **Anti-generic checks**:
    - Require ≥2 job-specific phrases from JD
    - Map each paragraph to specific pain point (in internal reasoning)
  - Temperature: 0.7 (creative but grounded)
  - Model: GPT-4o
- ✅ Validation: Check for STAR citations, metrics, no generic boilerplate
- ✅ Store in `JobState.cover_letter`

**Quality Gate**:
- For 5 test jobs, cover letters cite specific metrics
- No generic phrases like "I am excited to apply"
- Clear mapping to pain points using robust keyword/phrase matching (must reference role- and company-specific problems, but allows natural paraphrasing rather than exact string matches)
- pytest tests for validation logic

### 8.2 Complete CV Generator with STAR-Driven Tailoring
**Duration**: 4 days
**Dependencies**: 6.1

**Deliverables**:
- ✅ `src/layer6/cv_generator.py` (complete rewrite):
  - **Analysis phase**:
    - Parse `knowledge-base.md` for full candidate history
    - Classify job into competency mix (delivery, process, architecture, leadership) with % weights
    - Re-rank all STARs against competency mix
    - Detect gaps (required skills not in knowledge base)
  - **CV structure**:
    - Contact info (from knowledge-base.md)
    - Professional summary (2-3 sentences, job-specific, highlights fit score if ≥80)
    - Key achievements (3-5 bullets from `selected_stars`, metrics-driven)
    - Work experience (reverse chronological, with STAR-based bullets)
    - Education & certifications
  - **STAR-driven bullets**:
    - Each bullet starts with impact verb + metric
    - Prioritize STARs matching pain points
    - Reorder experience sections to surface most relevant roles first
  - **Gap mitigation**:
    - If job requires skills not in STARs, highlight adjacent experience or learning signals
    - Document gaps in `cv_reasoning` for dossier
  - **QA pass**:
    - Second LLM call to check for hallucinations, inconsistencies, ATS pitfalls
    - Validate no invented employers, dates, or degrees
  - **Output**: `.docx` file using `python-docx`
- ✅ Store in `JobState`: `cv_path`, `cv_reasoning`

**Quality Gate**:
- For 5 test jobs, CV highlights different STARs based on pain points
- Professional summary is job-specific (not generic)
- No hallucinated work history
- ATS-friendly formatting (proper headings, bullet points, no tables)
- pytest tests for gap detection and QA logic

---

## Phase 9: Layer 6b - Per-Lead Outreach Generator (Week 5)

### 9.1 Lead-Specific Outreach Package Generator
**Duration**: 3 days
**Dependencies**: 7.1, 8.1

**Deliverables**:
- ✅ `src/layer6/outreach_generator.py`:
  - **Per-contact outreach**:
    - For each contact from Layer 5, generate:
      1. Subject line (6-10 words, pain-focused)
      2. LinkedIn message (≤550 chars, fits LinkedIn limit)
      3. Email (100-200 words, professional formatting)
      4. Reasoning (why this message for this person)
  - **Personalization**:
    - Reference contact's role and `why_relevant`
    - Tie to pain points and company signals
    - Cite ≥1 STAR metric
    - Mention contact's recent signals if available
  - **JSON-only output**:
    ```python
    {
      "name": str,
      "role": str,
      "company": str,
      "subject_line": str,
      "linkedin_message": str,
      "email": str,
      "reasoning_summary": [str]
    }
    ```
  - **Constraints**:
    - No emojis
    - No placeholders except `[Your Name]` (role-based contacts like "VP Engineering at {company}" are treated as valid addressees, not placeholders)
    - LinkedIn message ends with email + Calendly URL
  - Temperature: 0.7
  - Model: GPT-4o
- ✅ Generate outreach for all primary contacts (4-6 packages per job)
- ✅ Store in `JobState.outreach_packages: List[OutreachPackage]`

**Quality Gate**:
- For 5 test jobs, generates 4-6 distinct outreach packages
- Each package is personalized to contact's role
- LinkedIn messages respect 550-char limit
- pytest tests validate structure and constraints

### 9.2 End-to-End Pipeline Regression & Report (Claude)
**Duration**: 1 day
**Dependencies**: 3.1–9.1

**Deliverables**:
- Claude runs the full pipeline end-to-end for a small, fixed set of real jobs pulled from the MongoDB `level-2` cache by `job_id` (initially 4 jobs: `4306263685`, `4323221685`, `42320338018`, `4335702439`), covering functionality from Phases 3–9 (Layers 1–6b).
- Validate data flow, retries, and outputs (application form fields, pain points, research, fit score, dossier, outreach, CV) against ROADMAP quality gates.
- Produce a written summary of findings, regressions, and follow-ups in `@report.md` at the repository root, organized with one section per relevant phase.

**Quality Gate**:
- All configured real jobs complete without unhandled errors.
- Any deviations from ROADMAP expectations are documented with concrete examples and next actions in `@report.md`.

---

## Phase 10: Layer 7 - Output Publisher & Dossier Generator (Week 6)

### 10.1 Complete Opportunity Dossier Generator
**Duration**: 3 days
**Dependencies**: 9.1

**Deliverables**:
- ✅ `src/layer7/dossier_generator.py`:
  - **10-section dossier** matching n8n workflow:
    1. **Job Summary**: Title, company, location, fit score, URLs, posting metadata
    2. **Job Requirements/Criteria**: Seniority, employment type, function, industries
    3. **Company Overview**: Summary, signals, industry, keywords
    4. **Opportunity Mapper**: Hiring signals, timing, "why now"
    5. **Role Research**: Summary, business impact, KPIs, success criteria
    6. **Pain Point Analysis**: Pain points, strategic needs, risks, success metrics
    7. **People & Outreach Mapper**:
       - Primary contacts (4-6) with full outreach packages
       - Secondary contacts (4-6) with full outreach packages
    8. **Notes**: Hiring manager hints, TA team, additional context
    9. **FireCrawl/Opportunity Queries**: Search queries used, sources
    10. **Validation & Metadata**: Per-section validation status, timestamps, run_id
  - **Pain → Proof → Plan structure** (top of file):
    - Top 3 business pains
    - Proof from selected STARs (metrics)
    - 90-day plan (3-5 bullets)
  - **Format**: Markdown with clear section headers
  - **File output**: `applications/<company>/<role>/dossier.txt`
- ✅ Store full dossier text in `JobState.dossier_path`

**Quality Gate**:
- Dossier is comprehensive, skimmable, professional
- Pain → Proof → Plan section is punchy (fits on one screen)
- All 10 sections present (or marked "N/A" if data missing)
- pytest tests for section generation

### 10.2 Output Publisher with Drive/Sheets/MongoDB
**Duration**: 2 days
**Dependencies**: 10.1

**Deliverables**:
- ✅ `src/layer7/output_publisher.py` (enhanced):
  - **Local file writes**:
    - `applications/<company>/<role>/dossier.txt`
    - `applications/<company>/<role>/cover_letter.txt`
    - `applications/<company>/<role>/CV_<company>.docx`
    - `applications/<company>/<role>/application_form_fields.txt` (if present)
    - `applications/<company>/<role>/outreach/` (per-contact packages as individual files)
  - **Google Drive upload**:
    - Create folder structure: `Job Applications/<company>/<role>/`
    - Upload all files
    - Graceful degradation if quota exceeded (log error, continue)
    - Store `drive_folder_url` in JobState
  - **Google Sheets logging**:
    - Append row with: date, company, role, location, fit score, status, drive URL, dossier URL
    - Retry logic (3 attempts)
  - **MongoDB persistence**:
    - Update `level-2` collection with:
      - `generated_dossier`, `cover_letter`, `cv_path`
      - `fit_analysis`, `selected_stars` (STAR IDs)
      - `outreach_packages` (all contact outreach)
      - `pipeline_run_at`, `run_id`, `status`
    - Preserve existing embeddings and metadata
- ✅ Status tracking:
  - Set `JobState.status`: "completed" | "failed" | "partial"
  - Append errors to `JobState.errors` if layers failed
- ✅ Retry logic for all external services (Drive, Sheets, MongoDB)

**Quality Gate**:
- For 5 test jobs, all files written locally
- Drive uploads succeed (or gracefully degrade with clear errors)
- Sheets row includes all key fields
- MongoDB document updated correctly
- pytest tests with mocked Google/Mongo clients

---

## Phase 11: Tier System & Batch Processing (Week 6-7)

### 11.1 Tier System Implementation
**Duration**: 2 days
**Dependencies**: 10.2

**Deliverables**:
- ✅ Add `tier` field to `JobState`: "A" | "B" | "C"
- ✅ CLI flag: `--tier A` (default: infer from fit score or manual assignment)
- ✅ Tier-based layer execution:
  - **Tier A** (Dream roles):
    - All layers enabled
    - Full People Mapper (8-12 contacts)
    - Full dossier (10 sections)
    - Manual review required
  - **Tier B** (Good roles):
    - Skip Layer 1.5 (application form)
    - Limited People Mapper (2-4 contacts)
    - Simplified dossier (6 core sections)
    - Cheaper model for Layers 2-3 (gpt-4o-mini)
  - **Tier C** (Volume roles):
    - Skip Layers 1.5, 5 (no form mining, no people mapper)
    - Skip role research (Layer 3 company only)
    - Minimal dossier (pain points + fit score + cover letter only)
    - Cheapest model (gpt-4o-mini) for all layers
- ✅ Cost tracking: Log token usage and cost per tier in LangSmith
- ✅ Tier auto-assignment:
  - Fit score ≥85 → Tier A
  - Fit score 70-84 → Tier B
  - Fit score <70 → Tier C (or skip entirely)

**Quality Gate**:
- Tier A jobs get full pipeline
- Tier C jobs complete in <2 min with <$0.05 cost
- Clear CLI output shows tier assignment per job

### 11.2 Batch Processing CLI
**Duration**: 2 days
**Dependencies**: 11.1

**Deliverables**:
- ✅ `scripts/run_batch.py`:
  - CLI args:
    - `--max-jobs 50`: Process up to N jobs
    - `--tier A|B|C`: Filter by tier
    - `--location "City, Country"`: Location filter
    - `--posted-since 7`: Jobs posted in last N days
    - `--min-score 70`: Minimum fit score threshold
    - `--concurrency 5`: Number of parallel workers
  - Execution:
    - Fetch jobs matching criteria from MongoDB
    - Process jobs in parallel (up to `--concurrency`)
    - Terminal multi-progress display (overall + per-job progress bars)
    - Graceful shutdown on Ctrl+C (save partial results)
  - Summary report:
    - Total processed/failed/skipped
    - Average latency per job
    - Total cost (from LangSmith)
    - Top errors
  - Error handling:
    - Continue on single-job failures
    - Log all errors to `pipeline_runs` collection
- ✅ Progress display:
  - Overall: `[=========>    ] 65/100 jobs (65%)`
  - Per-job: `Job 42 (Acme Inc - SRE): [=====>] Layer 5 (People Mapper)`

**Quality Gate**:
- Can process 50 jobs in parallel without crashes
- Clear terminal output with real-time progress
- Summary report includes cost and latency
- Ctrl+C saves partial results and exits cleanly

---

## Phase 12: Caching & Performance Optimization (Week 7)

### 12.1 Company Research Caching
**Duration**: 1 day
**Dependencies**: 5.1

**Deliverables**:
- ✅ MongoDB `company_cache` collection:
  - Schema: `{company_name_normalized, research_data, cached_at, expires_at}`
  - TTL index: 7 days
- ✅ Cache check before FireCrawl scraping
- ✅ Cache invalidation: Manual CLI command `scripts/clear_cache.py --company "Acme"`
- ✅ Cache hit metrics in LangSmith

**Quality Gate**:
- Cache hit reduces Layer 3 latency by ~80%
- Repeated companies don't trigger FireCrawl re-scrape within 7 days

### 12.2 STAR Selection Caching
**Duration**: 1 day
**Dependencies**: 2.2

**Deliverables**:
- ✅ Cache STAR selections keyed by `pain_points_hash`
- ✅ If pain points identical to previous job, reuse STAR selection
- ✅ Cache stored in MongoDB with 30-day TTL

**Quality Gate**:
- Cache hit reduces Layer 2.5 latency by ~90%

### 12.3 Batch Optimization
**Duration**: 2 days
**Dependencies**: 11.2

**Deliverables**:
- ✅ Batch jobs by company to maximize cache hits
- ✅ Pre-fetch company research for all companies in batch before running pipelines
- ✅ Parallel embedding generation for STAR selection (batch embed pain points)
- ✅ Rate limiting for FireCrawl (max 10 concurrent requests)
- ✅ Connection pooling for MongoDB
- ✅ OpenAI batch API for Layer 2/4 (async batch scoring)

**Quality Gate**:
- Batch of 50 jobs completes in <30 minutes (avg 36s/job)
- Cost: <$0.12/job average across tiers
- No rate limit errors

---

## Phase 13: Testing & Quality Assurance (Week 8)

### 13.1 Unit Tests
**Duration**: 3 days
**Dependencies**: All implementation phases

**Deliverables**:
- ✅ pytest test suite covering:
  - `tests/unit/test_star_parser.py`: STAR parsing edge cases
  - `tests/unit/test_star_selector.py`: Mocked LLM responses, selection logic
  - `tests/unit/test_pain_point_miner.py`: JSON validation, schema checks
  - `tests/unit/test_company_researcher.py`: Mocked FireCrawl, hallucination checks
  - `tests/unit/test_opportunity_mapper.py`: STAR citation validation
  - `tests/unit/test_cv_generator.py`: Gap detection, QA logic
  - `tests/unit/test_outreach_generator.py`: Character limits, personalization
  - `tests/unit/test_dossier_generator.py`: Section generation, formatting
- ✅ Mock all external services (OpenAI, FireCrawl, MongoDB, Google APIs)
- ✅ Test coverage: ≥80% line coverage
- ✅ CI integration: pytest runs on every commit (GitHub Actions)

**Quality Gate**:
- All tests pass
- Coverage ≥80%
- Tests run in <2 minutes

### 13.2 Integration Tests
**Duration**: 2 days
**Dependencies**: 13.1

**Deliverables**:
- ✅ `tests/integration/test_end_to_end.py`:
  - Full pipeline run on 3 test jobs (with real external services)
  - Validate all outputs (dossier, cover letter, CV, outreach packages)
  - Check MongoDB persistence
  - Verify Drive uploads (test folder)
- ✅ Hallucination detection tests:
  - For 10 test jobs, manually review company research for invented facts
  - Flag hallucinations, refine prompts
  - Re-test until zero hallucinations in test set
- ✅ Cost validation:
  - Run on 10 test jobs, measure actual cost
  - Compare to projections ($0.10-0.15/job)

**Quality Gate**:
- 3 end-to-end tests pass with real services
- Zero hallucinations in company research test set
- Actual cost matches projections (±20%)

### 13.3 Manual QA & Red-Team Review
**Duration**: 3 days
**Dependencies**: 13.2

**Deliverables**:
- ✅ Manual review of 20 random dossiers:
  - Check for hallucinations (company facts, STAR metrics)
  - Verify personalization (STAR citations, pain point mapping)
  - Assess output quality (professional, skimmable, actionable)
- ✅ Red-team prompts:
  - Try to trick LLM into hallucinating
  - Test edge cases (missing data, malformed JDs)
  - Adversarial company names, weird job titles
- ✅ Document all issues in GitHub Issues
- ✅ Fix critical issues, defer minor polish to Phase 14

**Quality Gate**:
- Zero critical hallucinations in 20-dossier sample
- All red-team edge cases handled gracefully
- Output quality rated ≥8/10 by hiring manager lens (per feedback.md)

---

## Phase 14: Production Deployment & Monitoring (Week 9)

### 14.1 Deployment Infrastructure
**Duration**: 2 days
**Dependencies**: 13.3

**Deliverables**:
- ✅ Dockerfile for containerized deployment
- ✅ `docker-compose.yml` for local testing
- ✅ VPS deployment guide (Ubuntu/systemd)
- ✅ Environment variable deployment strategy:
  - `.env.production` template
  - Secret management (not committed to git)
- ✅ Process supervisor: systemd unit file for batch cron job
- ✅ Cron schedule: Daily batch at 2 AM local time

**Quality Gate**:
- Docker image builds successfully
- Container runs pipeline without errors
- VPS deployment documented step-by-step

### 14.2 Observability & Monitoring
**Duration**: 3 days
**Dependencies**: 14.1

**Deliverables**:
- ✅ Structured logging:
  - JSON logs with log levels (DEBUG, INFO, WARNING, ERROR)
  - Log rotation (daily, 7-day retention)
  - Centralized log aggregation (optional: Logtail, Papertrail)
- ✅ LangSmith dashboards:
  - Per-layer latency and token usage
  - Error rate by layer
  - Cost tracking (daily/weekly aggregates)
- ✅ MongoDB audit trail:
  - `pipeline_runs` collection with full metadata
  - Query by date, tier, status, company
- ✅ Alerting:
  - Telegram bot for critical errors
  - Daily summary: jobs processed, failures, cost
  - Threshold alerts: error rate >10%, cost >$20/day
- ✅ Performance metrics:
  - Track avg latency per tier
  - Track cache hit rates
  - Track cost per job by tier

**Quality Gate**:
- All errors logged to structured logs + Telegram
- LangSmith dashboard shows per-layer metrics
- Daily summary sent to Telegram

### 14.3 Cost Management & Throttling
**Duration**: 1 day
**Dependencies**: 14.2

**Deliverables**:
- ✅ Cost budget enforcement:
  - Daily cost cap: $50 (halt batch if exceeded)
  - Per-job cost tracking
  - Alert if cost trends exceed budget
- ✅ Rate limiting:
  - Max 50 jobs/batch
  - Max 10 concurrent jobs
  - FireCrawl: Max 10 concurrent requests
  - OpenAI: Respect tier limits
- ✅ Graceful degradation:
  - If Drive quota exceeded, save locally only
  - If FireCrawl rate limited, use cached data or skip research
  - Continue pipeline even if non-critical layers fail

**Quality Gate**:
- Cost cap prevents runaway spending
- Rate limits prevent service bans
- System degrades gracefully under load

---

## Phase 15: Advanced Features & Polish (Week 10)

### 15.1 Tier Auto-Tuning
**Duration**: 2 days
**Dependencies**: 14.2

**Deliverables**:
- ✅ Historical analysis:
  - Track which tier assignments led to interviews
  - Adjust tier thresholds based on outcomes
- ✅ ML-based tier prediction:
  - Train simple classifier (fit score + company signals + role keywords → tier)
  - Use historical data (50+ jobs) to predict optimal tier
- ✅ Feedback loop:
  - CLI command: `scripts/mark_outcome.py --job-id 123 --outcome interview`
  - Store outcomes in MongoDB
  - Re-tune tier model monthly

**Quality Gate**:
- Tier predictions improve interview rate by ≥10% vs manual

### 15.2 Advanced STAR Matching
**Duration**: 2 days
**Dependencies**: 2.2

**Deliverables**:
- ✅ Fine-tune embedding model on STAR library for better relevance
- ✅ Multi-turn STAR selection:
  - First pass: Select 3 STARs
  - Second pass: Ask LLM "Any better STARs for pain point X?"
  - Refine selection
- ✅ Diversity constraint: Ensure selected STARs span different competencies

**Quality Gate**:
- STAR selection subjectively "feels right" for 10 test jobs
- Diversity: No more than 2 STARs from same company/role

### 15.3 Dossier Customization
**Duration**: 1 day
**Dependencies**: 10.1

**Deliverables**:
- ✅ CLI flag: `--dossier-template custom.md`
- ✅ Template variables: `{{job_title}}`, `{{company}}`, `{{fit_score}}`, `{{pain_points}}`, etc.
- ✅ Support custom section ordering
- ✅ Markdown + HTML export options

**Quality Gate**:
- Custom templates render correctly
- All variables populated

### 15.4 UI Layer (Optional)
**Duration**: 5 days
**Dependencies**: 10.2

**Deliverables**:
- ✅ Simple web UI (Streamlit or Flask):
  - Dashboard: Recent jobs, fit scores, statuses
  - Dossier viewer: Render dossiers with syntax highlighting
  - Approval interface: Approve/reject cover letters and CVs
  - Rerun pipeline: Trigger reruns for specific jobs
  - Outcome tracking: Mark interviews, offers
- ✅ Authentication: Basic auth (single user)
- ✅ Deployment: Same VPS, nginx reverse proxy

**Quality Gate**:
- UI accessible at `https://yourdomain.com/jobs`
- Dossiers render beautifully
- Approval flow works

---

## Phase 16: Documentation & Handoff (Week 10)

### 16.1 User Documentation
**Duration**: 2 days
**Dependencies**: 15.4

**Deliverables**:
- ✅ `docs/user-guide.md`:
  - Installation & setup
  - CLI commands reference
  - Tier system explanation
  - Troubleshooting common issues
- ✅ `docs/architecture.md` (updated with full implementation)
- ✅ `docs/configuration.md`:
  - Environment variables reference
  - Model selection guide
  - Cost optimization tips
- ✅ `docs/langsmith-usage.md` (updated)
- ✅ Video walkthrough (10-minute Loom):
  - Running batch job
  - Reviewing dossier
  - Approving outreach

**Quality Gate**:
- Documentation is complete, clear, and tested
- Video walkthrough covers end-to-end flow

### 16.2 Developer Documentation
**Duration**: 2 days
**Dependencies**: 16.1

**Deliverables**:
- ✅ `docs/developer-guide.md`:
  - Code structure overview
  - Adding new layers
  - Testing strategy
  - Deployment process
- ✅ `docs/prompts.md`:
  - All LLM prompts documented
  - Rationale for each prompt
  - Versioning and A/B testing strategy
- ✅ `docs/api.md`:
  - Internal API reference (state contracts, function signatures)
  - External API integrations (FireCrawl, OpenAI, MongoDB, Google)
- ✅ Inline code documentation:
  - All functions have docstrings
  - Complex logic has comments

**Quality Gate**:
- New developer can add a layer in <1 day using docs
- All prompts versioned and documented

### 16.3 Maintenance Playbook
**Duration**: 1 day
**Dependencies**: 16.2

**Deliverables**:
- ✅ `docs/maintenance.md`:
  - Monitoring checklist (daily, weekly, monthly)
  - Cost review process
  - Prompt tuning workflow
  - Cache management
  - Database maintenance (indexes, backups)
- ✅ Runbooks for common issues:
  - "FireCrawl rate limited" → wait + retry
  - "Drive quota exceeded" → local save only
  - "High cost day" → review LangSmith, check for runaway jobs
- ✅ Backup strategy:
  - MongoDB backups (weekly via Atlas)
  - Local artifacts backed up to external drive (monthly)

**Quality Gate**:
- Maintenance playbook covers all common scenarios
- Runbooks tested with simulated failures

---

## Success Metrics & Final Validation

### Quantitative Metrics
- **Throughput**: 100-200 jobs/day across tiers (Tier A: 5-10, Tier B: 30-50, Tier C: 50-150)
- **Cost**: Average <$0.12/job (Tier A: $0.25, Tier B: $0.10, Tier C: $0.05)
- **Latency**: Average <60s/job (Tier A: 4-5 min, Tier B: 1-2 min, Tier C: 30s)
- **Quality**: Zero hallucinations in manual review of 50 random dossiers
- **Interview rate**: ≥10% interview rate for Tier A jobs (vs <5% baseline)
- **Test coverage**: ≥80% line coverage
- **Uptime**: ≥99% pipeline success rate (non-critical failures allowed)

### Qualitative Metrics (Hiring Manager Lens)
- **Personalization**: Outputs feel "painfully specific" not "intelligently generic" (≥8/10)
- **Professionalism**: Artifacts require minimal editing before sending (≥8/10)
- **Completeness**: Dossier provides all context needed for application strategy (≥9/10)
- **Trust**: Candidate trusts system outputs for dream jobs with minimal review (≥7/10)

### Final Validation
- ✅ Run on 100 real jobs across tiers
- ✅ Manual review of 20 Tier A dossiers (hiring manager evaluation)
- ✅ Track outcomes: applications sent, responses, interviews, offers
- ✅ Compare to baseline (manual application prep): time savings, quality improvement
- ✅ Cost analysis: total spend vs projected budget
- ✅ System passes all acceptance criteria from requirements.md

### Production Readiness Checklist
- ✅ All layers implemented and tested
- ✅ All n8n workflow features covered (10-section dossier, 8-12 contacts, full outreach)
- ✅ STAR-based hyper-personalization working
- ✅ Hallucination controls validated (zero hallucinations in test set)
- ✅ Tier system operational
- ✅ Batch processing at scale (50+ jobs/run)
- ✅ Caching reduces cost by ≥40%
- ✅ Monitoring and alerting active
- ✅ Documentation complete
- ✅ VPS deployment successful
- ✅ Cost within budget (<$100/month for 1000 jobs)

---

## Risk Mitigation

### Technical Risks
1. **LLM hallucinations in research layers**
   - Mitigation: Context-only prompts, JSON schemas, regular audits
2. **FireCrawl rate limiting/blocks**
   - Mitigation: Caching, graceful degradation, backup scraping methods
3. **Google API quota limits**
   - Mitigation: Local-first saves, quota monitoring, fallback to CLI outputs
4. **MongoDB performance at scale**
   - Mitigation: Proper indexes, connection pooling, query optimization
5. **Cost overruns**
   - Mitigation: Daily cost caps, per-job budgets, tier system

### Business Risks
1. **Low interview conversion rate**
   - Mitigation: A/B test prompts, manual review of Tier A, outcome tracking
2. **Excessive time on manual review**
   - Mitigation: Tier system focuses review on high-value jobs only
3. **System too complex to maintain**
   - Mitigation: Comprehensive docs, simple architecture, avoid over-engineering

---

## Timeline Summary

| Phase | Duration | Cumulative |
|-------|----------|------------|
| 1. Foundation | 3 days | Week 1 |
| 2. STAR Library | 4 days | Week 1 |
| 3. Layer 1 & 1.5 | 3 days | Week 2 |
| 4. Layer 2 | 2 days | Week 2 |
| 5. Layer 3 | 5 days | Week 3 |
| 6. Layer 4 | 2 days | Week 3 |
| 7. Layer 5 | 4 days | Week 4 |
| 8. Layer 6a | 6 days | Week 4-5 |
| 9. Layer 6b | 3 days | Week 5 |
| 10. Layer 7 | 5 days | Week 6 |
| 11. Tier & Batch | 4 days | Week 6-7 |
| 12. Optimization | 4 days | Week 7 |
| 13. Testing & QA | 8 days | Week 8 |
| 14. Deployment | 6 days | Week 9 |
| 15. Advanced Features | 10 days | Week 10 |
| 16. Documentation | 5 days | Week 10 |

**Total: 10 weeks (50 working days)**

---

## Next Steps

1. **Review and approve this roadmap**
2. **Set up project tracking** (GitHub Projects, Linear, or Notion board)
3. **Begin Phase 1: Foundation** (next action)
4. **Weekly checkpoints** to assess progress vs plan
5. **Adjust scope** if timeline slips (defer Phase 15 features if needed)

---

**Roadmap Version**: 1.1
**Last Updated**: 2025-11-22
**Owner**: Taimoor Alam
**Status**: Phases 1-9 Production-Ready; Phase 10 Partially Complete

### Recent Completions (22 Nov 2025)
- ✅ Phase 8.1 validator relaxation: keyword/phrase-based JD matching
- ✅ Phase 10.1 dossier generator: 10-section structure with Pain→Proof→Plan
- ✅ Layer-specific e2e tests: 11 tests covering Phases 5-8
