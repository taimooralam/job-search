# Requirements Blueprint

## Overview & Goals
- Purpose: Single-candidate job search copilot that ingests scraped jobs from MongoDB, runs the 7-layer LangGraph pipeline, and drafts tailored outreach + CV bundles.
- Goals: Automate end-to-end prep for quality applications; create Drive folders per company/role with drafts; log runs; target 50 qualified jobs/day with matched cover letters and CVs ready to send.
- Today’s objective: ship a simple, working vertical slice (ingest → analyze → generate → store/log) with manual review before sending.

## Scope
- In-scope now: Read jobs from MongoDB (existing schema), run Layers 2–6 (pain-point mining, company research via FireCrawl, People Mapper/people research, fit scoring, LinkedIn outreach + CV tailoring), store outputs to Drive, log to Sheets, trace with LangSmith. Basic retries, manual approval gates, and basic CLI progress feedback.
- Out-of-scope for now: New job sources beyond current DB, production-grade scheduling, advanced People Mapper capabilities (bulk contact discovery/automation), automated sending, heavy RBAC/tenanting.

## Users & Personas
- Primary user: the candidate (you) running the pipeline locally/CLI; success = high-quality, application-ready artifacts with minimal editing.

## Functional Requirements

### Core Pipeline (Layers 2-7)
- **Job ingestion**: Pull queued jobs from MongoDB (`jobId`/`dedupeKey` as uniqueness) using CLI parameters for "latest" and `location` filters; fetch up to 50 matching jobs per run and start their pipelines in parallel while respecting API/DB limits and existing time-based filtering.
- **Analysis layers**: Pain-point mining (Layer 2), company/role research via FireCrawl + LLM (Layer 3), opportunity mapping/fit scoring (Layer 4).
- **People & profile research (Layer 5 - People Mapper)**: For each job, identify 1–3 relevant people (e.g., hiring manager, team leads) from public web/professional profiles and build lightweight person objects (name, role, relationship to company/team, key public signals) to feed into LinkedIn outreach, reusing company research and pain points while respecting source site terms.

### **STAR-Based Personalization (Layer 2.5 - NEW)**
**Critical requirement from Phase 1.3 evaluation (7/10 personalization gap)**

**Problem:** Current approach passes full 4,456-char knowledge base as monolithic text to LLM; no explicit mapping between pain points and specific achievements.

**Solution:** Add Layer 2.5 (STAR Selector) between Layer 2 and Layer 3:
1. **Parse** `knowledge-base.md` into structured STAR objects:
   - Extract 11 STAR records with fields: ID, company, role, situation, task, actions, results, metrics, keywords
   - Return: `List[STARRecord]` (TypedDict)
2. **Score** each STAR's relevance to each job pain point using LLM (0-10 scale)
3. **Select** top 2-3 STAR records with highest aggregate relevance scores
4. **Map** selected STARs to pain points explicitly
5. **Supply** only selected STARs (not full profile) to Layer 4 & 6

**Outputs:**
- `selected_stars: List[STARRecord]` - 2-3 best-fit achievements for this job
- `star_to_pain_mapping: Dict[str, List[str]]` - Which STAR addresses which pain point

**Downstream Impact:**
- Layer 4 (Opportunity Mapper): Must cite specific STAR IDs and metrics in fit rationale
- Layer 6 (Outreach Generator): Must include at least one quantified achievement from selected STARs

### Generation & Output (Layers 6-7)
- **LinkedIn outreach generation**: Personalized LinkedIn cover letter/message using **selected STAR records** with concrete metrics cited (e.g., "reduced incidents by 75%", "3-year zero-downtime record"), plus pain points, company research, opportunity mapping, and People Mapper signals; output must fit within LinkedIn's character limit and end with the candidate's email address and Calendly URL `https://calendly.com/taimooralam/15min`.
- **CV tailoring**: Job-specific CV in two-pass mode (JSON evidence per role → QA’d bullets) that injects the full job description into the prompt, enforces strong-verb + metric + pain/success tie-ins, and emits `CV.md` (no `.docx`) via `prompts/cv-creator.prompt.md` using OpenRouter `CV_MODEL` (`anthropic/claude-3-opus-20240229` default).
- **Dossier assembly**: Complete `dossier.txt` matching sample-dossier structure (simplified) with pain points, selected STARs, company summary, fit analysis, LinkedIn cover letter

### Data Persistence & Tracking
- **MongoDB storage**: Persist run metadata + generated outputs to `level-2` collection:
  - `generated_dossier`, `cover_letter`, `fit_analysis`, `selected_stars` (STAR IDs), `pipeline_run_at`
- **Local artifacts**: Write to `applications/<company>/<role>/`: dossier.txt, cover_letter.txt, CV_<company>.docx
- **Google integration**: Upload to Drive (when quota allows); log summary to Sheets tracker
- **LangSmith tracing**: Full pipeline trace with layer-level performance metrics

### Integrations & Infrastructure
- **FireCrawl** with caching (MongoDB `company_cache` collection, 7-day TTL)
- **OpenRouter** (OpenAI GPT-4o, Anthropic as fallback)
- **LangSmith** tracing enabled
- **MongoDB Atlas** (jobs in `level-2`, company cache in `company_cache`)
- **Google Drive/Sheets** (service account)
- **Config**: All secrets via env vars; `Config.validate()` fails fast on startup

### Control & Quality
- **Manual review** before sending (human-in-the-loop)
- **Rerun capability**: Re-process specific job IDs
- **Error handling**: Graceful degradation with tenacity retries; capture errors per layer in `JobState.errors`
- **Status tracking**: Set `run_id`, `created_at`, `status` ("processing"/"completed"/"failed"/"partial") in state

## Non-Functional Requirements
- Reliability: Retries on API calls; resumable/durable execution per LangGraph where possible.
- Performance: Throughput target = 50 jobs/day via concurrent execution (up to 50 jobs in parallel per run); acceptable per-job latency if end-to-end < ~5 minutes when inputs are cached.
- CLI UX: Terminal-native multi-progress display showing (a) an overall batch progress bar and (b) an individual progress bar or line-style progress indicator per running job (e.g., up to 50 lines like `Job 12: -----====> 60%`) while the pipeline is running.
- Security & Privacy: Keep PII and resumes redacted in logs; secrets in env only; avoid uploading raw scraped resumes/job posts.
- Compliance: Respect source site terms; throttle FireCrawl; avoid aggressive scraping.
- Observability: LangSmith tracing enabled by default; minimal structured logs for layer entry/exit.

## Data & Models
- Input contracts: Job schema per `sample.json` (title, company, description, criteria, URLs, embeddings, score); candidate profile as structured knowledge graph + current CV/LinkedIn fields.
- People profile data: Lightweight person objects (name, role, relationship to job/company, key public signals) sourced from public web/professional profile pages to guide LinkedIn personalization.
- Model selection: Default GPT-4 class via OpenRouter; Anthropic as optional fallback; set cost/latency budgets per layer.
- Versioning: Tag prompts/models per layer and record in LangSmith; track schema changes in git + `architecture.md`.

## UX & Outputs
- Formats: LinkedIn cover letter text only (no email drafts), tailored CV (.docx or PDF), tracker row entry. Tone: professional, specific to pain points/company and recipient; letter must respect LinkedIn character limits and include the candidate's email address and Calendly URL at the end.
- Review loop: Human review/edits before any sending; all drafts stored in Drive with timestamps.

### UI Layer (Local Server)
- Build a local-only Flask app in `frontend/` backed by `pymongo`, with a simple front-end framework of choice to visualize Level 2 job data.
- Provide general free-text search across jobs plus column sorting on `createdAt`, `jobUrl`, `dedupeKey`, `jobId`, `location`, `role/title`, and `company name/firm`.
- Display a table with at least the above fields plus a `status` column supporting string values like `"not processed"`, `"marked for applying"`, `"to be deleted"`, `"applied"`, etc.
- Allow selecting multiple jobs for deletion, with server-side removal.
- Support pagination controls for 5, 10, 50, and 100 rows per page.
- Runs locally on the user's machine (no external hosting).

## Acceptance Criteria (Phase 1.3)

### End-to-End Pipeline Requirements
Given a MongoDB job (from existing corpus), pipeline must:

1. **Extract pain points** (Layer 2)
   - 3-5 key job challenges/requirements as bullet points

2. **Select best STAR records** (Layer 2.5 - NEW)
   - Parse `knowledge-base.md` → 11 structured STAR objects
   - Score each STAR's relevance to pain points using LLM
   - Select top 2-3 STARs with highest aggregate relevance
   - Output: `selected_stars` + `star_to_pain_mapping`

3. **Research company** (Layer 3)
   - Scrape company website via FireCrawl (with caching)
   - Generate 2-3 sentence company summary
   - Cache results in MongoDB `company_cache` (7-day TTL)

4. **Generate fit score + rationale** (Layer 4)
   - Input: Pain points + **selected STARs** (not full profile)
   - Output: 0-100 fit score
   - Rationale **must cite at least one STAR ID and metric**
   - Example: "Excellent fit (92/100). STAR #1 (AdTech modernization) addresses pain point #1 with 75% incident reduction."

5. **Generate LinkedIn cover letter** (Layer 6)
   - Input: Pain points + company summary + opportunity mapping + **selected STARs** + People Mapper/person profile context (when available)
   - **Must include at least one quantified achievement** from selected STARs
   - 2–4 short paragraphs optimized for LinkedIn message format with concrete examples, kept within LinkedIn's character limit
   - No separate email template is generated for this job; only the LinkedIn cover letter is produced
   - Ends with the candidate's email address and Calendly URL `https://calendly.com/taimooralam/15min`

6. **Generate tailored CV** (Layer 6)
   - Job-specific summary highlighting selected STAR achievements
   - Output: `.docx` file

7. **Assemble dossier** (Layer 7)
   - Create `dossier.txt` with: pain points, selected STARs, company summary, fit analysis, cover letter
   - Match simplified `sample-dossier.txt` structure

8. **Save locally** (Layer 7)
   - Write to `applications/<company>/<role>/`:
     - `dossier.txt`
     - `cover_letter.txt`
     - `CV_<company>.docx`

9. **Persist to MongoDB** (Layer 7)
   - Update `level-2` collection with:
     - `generated_dossier`, `cover_letter`, `fit_analysis`
     - `selected_stars` (STAR IDs)
     - `pipeline_run_at` timestamp
   - Preserve existing fields (embeddings, score, etc.)

10. **Log to Google Sheets** (Layer 7)
    - Summary row with job details, fit score, timestamps

11. **Trace to LangSmith**
    - Full pipeline trace with layer-level performance
    - Proper run metadata (`run_id`, layer names, timing)

12. **Config validation**
    - `Config.validate()` called at startup
    - Pipeline fails fast with clear error if env vars missing
    - No secrets hard-coded

13. **Parallel job execution & filtering**
    - CLI accepts "latest" and `location` parameters to select jobs from MongoDB.
    - When invoked, the pipeline fetches up to 50 matching jobs and runs their pipelines in parallel (max 50 concurrent jobs), while respecting API and MongoDB rate limits.
    - A terminal-native multi-progress display shows overall batch progress and one progress bar/indicator per job (up to 50) with status (`queued`/`running`/`completed`/`failed`) during execution.

14. **People Mapper / profile research**
    - For at least one job in a batch, People Mapper resolves 1–3 relevant people with basic profile fields (name, role, relationship to company/team).
    - LinkedIn cover letter content reflects at least one person-specific detail (e.g., team focus, recent work, or public signals) reusing company research, opportunity mapping, and pain points.

### Quality Requirements
- **Personalization depth**: Cover letters must cite specific STAR metrics (not generic claims)
- **Error handling**: Graceful degradation; failed layers append to `JobState.errors`
- **State tracking**: `run_id`, `created_at`, `status` set in JobState
- **Caching**: Repeated companies don't trigger FireCrawl re-scrape

## Risks & Open Questions
- Full candidate knowledge graph not finalized; interim data may reduce personalization quality.
- Google API quotas/consent need to be configured; FireCrawl rate limits and scraping blocks possible.
- Decide on automated scheduling vs. manual runs after the first vertical slice. 
