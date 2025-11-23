# Job-Intelligence Workflow System Summary

## System Architecture
You have a **7-layer AI job-intelligence pipeline** that automates personalized job application preparation using **LangGraph** for orchestration. The workflow is stateful, durable, and integrates multiple AI/web services.

## Current Operational Overrides
- **Master CV everywhere**: `Config.CANDIDATE_PROFILE_PATH` now defaults to `./master-cv.md` and candidate context is passed into fit, outreach, and CV generation prompts for Layers 3–6.
- **STAR selector paused**: Layer 2.5 remains in code but is bypassed by default via `Config.ENABLE_STAR_SELECTOR=False`; downstream prompts fall back to master CV evidence instead of STAR citations.
- **Privacy-safe FireCrawl**: Search queries in Layers 3 and 5 use natural-language, non-outreach phrasing. Layer 3 also scrapes the original job URL to capture the written JD text for dossiers.
- **Local-only outputs**: Google Drive/Sheets publishing is disabled by default (`ENABLE_REMOTE_PUBLISHING=False`); artifacts are saved only under `./applications/<company>/<role>/`.
- **CV generation**: Layer 6 now uses the prompt in `prompts/cv-creator.prompt.md` + the master CV to emit `CV.md` (no `.docx`) alongside an integrity check.
- **Contact fallbacks**: If contact discovery fails, Layer 5 returns three fallback cover letters and records them for publishing.

## The 7+ Layers (Your Process)

**Update (17 Nov):** Added Layer 2.5 based on external evaluation feedback to enable hyper-personalization.

### 1. Input Collector (Layer 1)
- Gathers job postings from sources (LinkedIn initially, expandable to Indeed, etc.)
- Jobs stored in MongoDB Atlas with rich metadata (as shown in your sample.json: embeddings, scores, job descriptions)
- Can process jobs from DB or via direct URL input

### 2. Pain-Point Miner (Layer 2) **UPDATED**
- Uses an LLM as a reasoning model called **“Pain-Point Miner”** to analyze job descriptions.
- Returns a **JSON-only** object capturing the deeper business drivers behind the role:

  ```json
  {
    "pain_points": ["..."],
    "strategic_needs": ["..."],
    "risks_if_unfilled": ["..."],
    "success_metrics": ["..."]
  }
  ```

  - Each array: 3–6 short, business-focused bullet phrases (no long paragraphs).
  - No text outside the JSON object is allowed.

- Focus is on:
  - Why the company needs this role (underlying business pain).
  - What outcomes are missing today.
  - What risks exist if the role is unfilled.
  - How success will be measured once the role is filled.

- **State contract:**
  - `JobState` is extended with:
    - `pain_points: List[str]`
    - `strategic_needs: List[str]`
    - `risks_if_unfilled: List[str]`
    - `success_metrics: List[str]`
  - These are consumed by the STAR Selector, Opportunity Mapper, People Mapper, and Outreach nodes.

### 1.5. Job URL & Application Form Miner (Layer 1.5) **NEW – High Priority**

- **Purpose:** Reduce friction when actually applying by extracting the **application form fields** from the original job URL.
- **Input:**
  - `job_url`
  - Optionally `job_description` for context.
- **Process:**
  - Use FireCrawl (or similar) to scrape `job_url` (not just the company site).
  - Convert HTML to markdown.
  - Use an LLM to identify likely application fields:
    - Labels/questions (e.g., “Current salary”, “LinkedIn URL”, “Cover letter”).
    - Field type (free text, URL, numeric, file upload, checkbox).
    - Optional/required hints and any obvious character/word limits.
- **Output:**
  - Structured list in state (e.g., `application_form_fields: List[FormField]`).
  - A human-friendly text file:
    - `applications/<company>/<role>/application_form_fields.txt`
    - Lists all fields and short hints.
- This runs before downstream analysis so you always get a “fill this in” checklist per job.

### 2.5. STAR Selector & Knowledge Graph (Layer 2.5) **MANDATORY FOR QUALITY**
- **Purpose**: Enable hyper-personalization by mapping each job’s pain points to specific, metric-backed achievements from your STAR library, treated as a small **knowledge graph** rather than a flat text blob.
- **Raw input surface**: You continue to author and maintain achievements in `knowledge-base.md` as human-readable **STAR RECORD** sections (S/T/A/R, BACKGROUND CONTEXT, ATS KEYWORDS, HARD/SOFT SKILLS, etc.).
- **Canonical STAR schema**:
  - A separate parsing/normalization step (Phase 2.1) converts each STAR from `knowledge-base.md` into a canonical `STARRecord` with at least:
    - Identity & context: `id`, `company`, `role_title`, `period`, `domain_areas`, `background_context`.
    - Story spine: `situation`, `tasks: List[str]`, `actions: List[str]`, `results: List[str]`, `impact_summary`, `condensed_version`.
    - Matching surface: `ats_keywords: List[str]`, `categories: List[str]`, `hard_skills: List[str]`, `soft_skills: List[str]`, `metrics: List[str]`.
    - Pain/outcome hooks: `pain_points_addressed: List[str]`, `outcome_types: List[str]` (e.g., `cost_reduction`, `risk_reduction`, `velocity_increase`).
    - Role targeting & metadata: `target_roles: List[str]`, `metadata` (seniority weights, sources, embedding metadata).
  - Canonical STARs are stored in a `star_records` collection and exposed to the pipeline as a **knowledge graph**:
    - Nodes: STAR, Company, Role, DomainArea, HardSkill, SoftSkill, PainPoint, OutcomeType, Metric.
    - Edges: STAR → Company, STAR → Role, STAR → DomainArea, STAR → HardSkill/SoftSkill, STAR → PainPoint(s), STAR → OutcomeType(s), STAR → Metric(s), STAR → TargetRole(s).
- **Selection process**:
  - Pre-selection:
    - Use embeddings + graph filters to retrieve a small candidate set (5–8 STARs) for a job based on:
      - Overlap between `pain_points` / `strategic_needs` and `pain_points_addressed`.
      - Matching `domain_areas`, `categories`, `hard_skills`, and `outcome_types` the job cares about.
    - This step is **deterministic** and cheap: no LLM yet, just vector similarity + rules.
  - LLM ranking (Layer 2.5 proper):
    - Feed the candidates to the LLM using their `condensed_version`, `metrics`, `hard_skills`, `pain_points_addressed`, and `outcome_types`.
    - Ask the model to score how well each STAR addresses the job’s top pains and desired outcomes.
    - Require it to output JSON with:
      - `selected_stars` (2–3 best STAR IDs),
      - `star_to_pain_mapping` (which pains each STAR addresses and why),
      - `star_selection_reasoning` (short, job-specific explanation).
- **Outputs in state**:
  - `selected_stars`: 2–3 canonical STAR records, including metrics and company/role context.
  - `star_to_pain_mapping`: explicit mapping from pain points to STAR IDs, with reasons.
  - `all_stars`: optional full canonical STAR library for CV generation and dossier building.
- **Downstream usage**:
  - Opportunity Mapper (Layer 4) must reference `selected_stars` and surface at least one concrete metric in its rationale (e.g., “75% incident reduction”).
  - People Mapper (Layer 5) and outreach layers must cite specific STAR metrics and company/role names when tailoring messages.
  - Generator (Layer 6) must build CV bullets and cover-letter paragraphs **only** from STARs present in `selected_stars` / `all_stars`, never inventing new companies or metrics.
- **Why**:
  - Passing the full knowledge base as plain text leads to “intelligent generic” outputs.
  - Treating STARs as a knowledge graph + explicit selector layer ensures every artifact reads as “**pain → proof (STAR) → plan**” and remains grounded in real, auditable achievements.

#### STAR Library Maintenance (Offline AI Agent)
- An **offline STAR Curator agent** (Phase 2.1) runs outside the main pipeline using the Codex CLI (recommended model: `o3-mini` or `gpt-4.1`):
  - Reads `knowledge-base.md`, detects incomplete/messy STARs, and prompts you for missing fields (metrics, pain_points_addressed, hard/soft skills, outcome_types, etc.).
  - Rewrites each `STAR RECORD` in `knowledge-base.md` into the canonical format and regenerates the machine-friendly `star_records` representation (JSON and/or MongoDB `star_records` collection).
  - This keeps your editing experience lightweight (one markdown file) while ensuring the pipeline always sees fully structured, graph-ready STAR data.

### 3. Company + Role Researcher (Layer 3) **UPDATED**

Layer 3 is conceptually split into two sub-nodes: **Company Researcher** and **Role Researcher**.

- **Company Researcher:**
  - Uses FireCrawl with multiple queries, not just `https://{company}.com`:
    - `${company} official site`
    - `${company} LinkedIn`
    - `${company} Crunchbase`
    - `${company} news`
  - Extracts:
    - 2–3 sentence **summary** of what the company does and its market.
    - **Signals**: funding, acquisitions, growth, leadership changes, new product launches, major partnerships.
  - Writes into state:
    - `company_research.summary`
    - `company_research.signals: List[str]`
    - `company_url` (canonical site if found).

- **Role Researcher:**
  - Focuses on the specific role at this company:
    - Responsibilities and ownership.
    - KPIs and success criteria.
    - “Why now?” – timing and context using company signals.
  - Uses a query like:
    - `"${title}" responsibilities ${company}`
  - Writes into state:
    - `role_research.summary`
    - `role_research.business_impact: List[str]`

These outputs feed directly into the Opportunity Mapper, People Mapper, and Outreach nodes so personalization is grounded in **real company and role signals**, not just the raw JD.

#### Hallucination Guardrails (Layer 3 and beyond)
- Research layers must treat scraped content and the job description as the **only ground truth** for company facts.
- Prompts should:
  - Encourage answers like “unknown” or “not found in the provided context” instead of guessing.
  - Avoid using general world knowledge to invent funding, acquisitions, or leadership changes.
- Where possible, analytical outputs (e.g., structured research summaries) should be **JSON-only**, making it easier to validate and test for hallucinations programmatically.

### 4. Opportunity Mapper (Layer 4) **ENHANCED**

- **Input:**
  - Job title, company, job description.
  - Pain-point JSON from Layer 2:
    - `pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics`.
  - Company + role research (summaries + signals).
  - `selected_stars` from Layer 2.5 (2–3 most relevant STAR achievements).
- **Process:**
  - LLM analyzes fit using a rubric and must:
    - Reference at least one STAR by number (e.g., “STAR #1”).
    - Cite concrete metrics from STARs (e.g., 75% incident reduction, €30M revenue protected).
    - Explicitly map which STAR addresses which **pain point/strategic_need/risk/success_metric**.
  - Produces:
    - `fit_score` (0–100, banded).
    - `fit_rationale` (2–3 sentences).
- **Output example:**
  - “Excellent fit (92/100). STAR #1 (AdTech modernization) addresses pain_point #1 and strategic_need #2 with a 75% incident reduction and 3-year zero-downtime record.”

### 5. People Mapper (Layer 5) **IMPLEMENTED, TO BE HARDENED**

- **Goal:** Identify real humans to contact and generate lead-specific outreach context.
- **Input:**
  - Job details.
  - Pain-point JSON (`pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics`).
  - Company + role research (including signals).
  - `selected_stars`.
- **Discovery:**
  - Uses multiple signals to propose 4–6 **primary contacts**:
    - Likely hiring manager.
    - Department head (e.g., VP Engineering).
    - Key stakeholders.
    - Recruiters / Talent Acquisition.
  - Next iteration:
    - Multi-source FireCrawl queries (`${company} LinkedIn`, `${company} Crunchbase`, `${company} people`).
    - Fallback patterns when no explicit names are found (role‑based targets).
- **Output contract (JSON):**
  - `people: List[Contact]`, where each `Contact` contains:
    - `name`
    - `role`
    - `linkedin_url`
    - `why_relevant`
  - Lead-level outreach fields are now produced by the Outreach JSON Generator in Layer 6b.
- Parsing should rely on **JSON responses**, not brittle regex over free-form text.

### 6a. Outreach & CV Generator (Layer 6a)

- **Purpose:** Produce a job-specific cover letter and tailored CV using STARs and research layers.
- **Input:**
  - Job details.
  - Pain-point JSON.
  - Company + role research.
  - `selected_stars`.
  - `fit_score`, `fit_rationale`.
  - Full candidate profile from `knowledge-base.md`.
- **Cover Letter:**
  - Target: 3–4 paragraphs, ~250–350 words (allowed range: 2–5 paragraphs, 180–420 words to accommodate LLM variance).
  - Must reference at least one **quantified achievement** from `selected_stars`.
  - Ties achievements to explicit pain points and strategic needs where available.
- **CV Generator:**
  - Builds a **job-specific, hyper-personalized CV**, not a generic marketing résumé.
  - Analyses the full knowledge base and selects the most relevant STAR records as base material.
  - Classifies the target job into a competency mix (e.g., delivery, process, architecture, leadership) with percentage weights inferred from the JD.
  - Re-weights and re-ranks STARs against this competency mix, then selects the highest-signal achievements.
  - Detects gaps between the knowledge base and the job requirements and surfaces mitigation strategies in the dossier (e.g., adjacent experience, fast-learning signals).
  - Creates an internal representation of the ideal CV for this specific job, grounded in pain points, company signals, Opportunity Mapper output, and ATS considerations.
  - Fills this representation with realistic, positive, crisp, and professional content that reflects actual history (no invented roles, employers, or education).
  - Runs a second, independent QA/verification pass to catch hallucinations, inconsistencies, and ATS pitfalls.
  - Uses STAR records and your compressed profile (AdTech, distributed systems, DDD, AWS, etc.).
  - Removes all hard-coded education/work history from the previous prototype.
  - Writes the reasoning behind STAR selection, weighting, gap analysis, and final CV structure into the dossier and MongoDB.
  - Outputs a `.docx` at:
    - `applications/<company>/<role>/CV_<company>.docx`.
- **State contract:**
  - `JobState` uses:
    - `cover_letter: str` – 3-paragraph outreach draft.
    - `cv_path: str` – local path to the generated tailored CV file.
  - Additional CV reasoning is persisted via the dossier and MongoDB updates in Layer 7 rather than as separate state fields.

### 6b. Lead Outreach JSON Generator (Layer 6b) **NEW – High Priority**

- **Purpose:** For every single **lead/contact at one company**, generate a hyper-personalized outreach package that downstream tools/UIs can consume.
- **Input:**
  - Job details.
  - Pain-point JSON.
  - Company research (summary + signals).
  - Role research (summary + business impact).
  - `opportunity_mapper` output (`fit_score`, `fit_rationale`).
  - One selected `Contact` from Layer 5.
  - `selected_stars` (for quantifiable achievements).
- **Prompt shape:** Follows the “Outreach Generator” spec you provided:
  - Includes ROLE, TARGET LEAD, PAIN POINTS, STRATEGIC NEEDS, COMPANY RESEARCH, ROLE RESEARCH, OPPORTUNITY SIGNALS, JOB DESCRIPTION.
  - Must be **lead-centric**, value-focused, and grounded in real signals and metrics.
- **Output (JSON ONLY):**
  ```json
  {
    "name": "",
    "role": "",
    "company": "",
    "subject_line": "",
    "linkedin_message": "",
    "email": "",
    "reasoning_summary": [""]
  }
  ```
  - `linkedin_message`: ≤ 550 characters.
  - `email`: 100–200 words, with whitespace formatting.
  - `subject_line`: 6–10 words.
  - No emojis; no placeholders except `[Your Name]`.
  - **No text outside the JSON object.**
- This layer encodes MCP-style discipline: exact schema, no extra fields, and no strings where objects are required.

### 7. Output Publisher (Layer 7) **ENHANCED - 17 Nov**
- **Dossier Generation**:
  - Assembles complete `dossier.txt` with all layer outputs
  - Saves to `applications/<company>/<role>/dossier.txt` locally
  - Includes: pain points, selected STARs, company summary, fit analysis, cover letter, metadata
  - Future: Full 10-section format matching sample-dossier.txt
- **File Management**:
  - Saves CV to `applications/<company>/<role>/CV_<company>.docx`
  - Saves cover letter to `applications/<company>/<role>/cover_letter.txt`
  - Uploads to Google Drive (when quota allows)
- **Data Persistence**:
  - Updates MongoDB `level-2` collection with:
    - `generated_dossier`: Full dossier text
    - `cover_letter`: Generated outreach
    - `fit_analysis`: Score + rationale
    - `selected_stars`: STAR IDs used
    - `pipeline_run_at`: Timestamp
- **Tracking**:
  - Logs to Google Sheets with all metadata
  - Future: Telegram notifications for high scores (>80)

## Output Format: Opportunity Dossier

The final output is a comprehensive **Opportunity Dossier** containing:

1. **Job Summary**: Role, company, location, score, URLs, posting metadata
2. **Job Requirements/Criteria**: Seniority, employment type, job function, industries
3. **Company Overview**: Summary, key signals, industry, keywords
4. **Opportunity Mapper**: Hiring signals, reasoning, timing significance
5. **Role Research**: Summary, "why now", key skills, business impact
6. **Pain Point Analysis**: Pain points, strategic needs, risks if unfilled, success metrics
7. **People & Outreach Mapper**:
   - Primary contacts (4-6 people) with LinkedIn + email templates each
   - Secondary contacts (4-6 people) with LinkedIn + email templates each
   - Each contact includes: name, role, URL, subject line, message, reasoning
8. **Notes**: Hiring manager info, talent acquisition team, additional context
9. **Firecrawl/Opportunity Queries**: Search queries used for research (LLM-style, keyword-rich to surface best company pages, role context, and decision makers)
10. **Validation & Metadata**: Validation status per section, timestamps, source, dedup key

## Technical Stack

- **Workflow Engine**: LangGraph (for stateful, resumable multi-step execution)
- **LLM**: OpenAI GPT-4/3.5 via LangChain
- **Web Scraping**: FireCrawl API (gets original job descriptions, company info)
- **Database**: MongoDB Atlas (stores scraped jobs with embeddings)
- **Job Data Model**: Your sample.json shows jobs have:
  - Embeddings (large: 3072-dim, small: 1536-dim) for semantic search
  - Score field (0-100 match rating)
  - Structured fields: title, company, description, criteria, source, URLs
  - Deduplication keys
- **Output**: Google Drive (CV storage), Google Sheets (application tracking), python-docx (CV generation)
- **Notifications**: Telegram/email for high-scoring matches

## Why LangGraph Over Static Workflows (like n8n)

- **Durability**: Can pause/resume if steps fail (e.g., scraping blocks, CAPTCHA)
- **Complex Logic**: Handles conditional branches, loops through multiple jobs, retries
- **LLM Integration**: Native LangChain integration for tools and models
- **Scalability**: Easier to add new job sources, monitoring via LangSmith
- **State Management**: Passes enriched state through each node

## Key Workflow Features

- **Node-Based Design**: Each layer = one or more nodes that take state, perform task, return updates
- **Sequential Flow**: Mostly linear with potential conditional edges (skip steps if data unavailable)
- **Candidate Profile**: Your "knowledge graph" (detailed experience/skills) fed into multiple nodes
- **Original JD Fetching**: Uses FireCrawl to find full job posting (follows "Apply" links or Google search)
- **Scoring System**: LLM-based rubric (from your n8n workflow) rates match quality

### Tiered Processing Model (A/B/C Tiers)

To scale toward 100–200 jobs/day **without sacrificing quality**, the workflow supports a tiered strategy:

- **Tier A (Dream / High-Signal Roles)**:
  - Run all layers: Pain-Point Miner, STAR Selector, full Company/Role Research, Opportunity Mapper, People Mapper, Generator, Publisher.
  - Expect manual review of dossiers, outreach, and CV before sending.
- **Tier B (Good but not dream roles)**:
  - Always run Layers 2, 2.5, 3 (light), 4, 6, 7.
  - People Mapper optional or limited (1–2 contacts).
  - Use `selected_stars` to keep personalization strong while reducing heavy research.
- **Tier C (Low-signal roles / volume)**:
  - Minimal path: Layers 2, 2.5, 4, 6.
  - Focus on fit score, short rationale, and small CV tweaks; skip expensive research and people mapping.

The `tier` value is part of `JobState` and can be set via CLI flags or job metadata. This design keeps the system **quality-first** for A-tier roles while still enabling high throughput overall.

## Current vs Future State

### External Evaluation Results (17–18 Nov)
**Overall Score (averaged): ~7.3–7.5/10** - Ready for supervised personal use, not yet production-ready

**Strengths:**
- Architecture: 8/10 - Clean, modular LangGraph design with clear separation of concerns
- Code Quality: 8/10 - Well-organized, typed, PEP 8-compliant
- Scalability: 7/10 - Can handle 50–100 jobs/day at ~$0.10–0.15/job with supervision

**Gaps Identified:**
- Personalization: 7/10 - Job-aware but **not STAR-structured** (monolithic profile text)
- Production Readiness: 6–7/10 - Missing pytest tests, full caching, and hardened batch processing
- Feature Coverage: **~40% of full n8n dossier** (missing People Mapper, company signals, timing analysis)
- Hallucination Risk: Research layers can still speculate about company details when sources are thin.

**Critical Fixes (Quality-First Phase):**
- **Layer 2.5 implementation** to parse STAR records and map to pain points explicitly, then feed into Layers 4 and 6.
- Update Layer 4 & 6 prompts to require citing specific STAR metrics and mapping each artifact paragraph to pain points.
- Add pytest tests with mocked services (LLMs, FireCrawl, Google APIs, MongoDB) plus parsing tests for JSON-only layers.
- Implement company research caching and tier-aware skipping of heavy steps.
- Enable `Config.validate()` at startup to prevent half-configured runs.
- Introduce hallucination guardrails: context-only research, “unknown over guessing,” and JSON schemas for analytical outputs.

### Currently Implemented (Phase 1.2 - COMPLETE)
- ✅ Layers 2, 3, 4, 6, 7 working end-to-end
- ✅ MongoDB ingestion, FireCrawl scraping, LLM analysis
- ✅ Cover letter + CV generation with job-specific tailoring
- ✅ Google Sheets logging, LangSmith tracing
- ⚠️ Layer 2.5 (STAR Selector) - **PLANNED, not implemented**
- ⚠️ Layer 5 (People Mapper) - **NOT IMPLEMENTED**

### LangGraph Migration Goals
- More resilient (handle failures gracefully) - ✅ **DONE** (tenacity retries, graceful degradation)
- CLI-friendly initially, then VPS-deployed persistent service - ✅ **CLI DONE**, VPS pending
- Extensible to multiple job platforms - 🔄 **IN PROGRESS** (MongoDB-agnostic design)
- Better observability and debugging - ✅ **DONE** (LangSmith integration)
