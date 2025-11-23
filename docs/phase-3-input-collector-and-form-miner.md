# Phase 3 – Layer 1 & 1.5: Input Collector and Application Form Miner

This document expands **Phase 3** of the roadmap and details how the Input Collector (Layer 1) and Application Form Miner (Layer 1.5) are implemented to meet the system-wide **requirements** and **architecture**.

It covers:

1. Objectives and scope  
2. Inputs, outputs, and data contracts  
3. Layer 1 – Job Input Collector  
4. Layer 1.5 – Application Form Field Miner  
5. Reliability, resilience, and UX considerations  
6. Alignment with `requirements.md` and `architecture.md`  
7. Testing and quality gates  

---

## 1. Objectives and Scope

**Goal:** Provide a robust front door to the pipeline that:

- Selects the right jobs from MongoDB to process today, and  
- Extracts the application form fields from each job’s actual posting URL,  

so that downstream layers operate on a clean, deduplicated job set and the candidate has a ready-to-use checklist for the actual form.

Phase 3 corresponds to:

- **Phase 3 – Layer 1 & 1.5** in `ROADMAP.md`  
- The **Input Collector** and **Job URL & Application Form Miner** sections in `architecture.md`  
- The **Job ingestion** and **Application Form Miner** functional requirements in `requirements.md`  

---

## 2. Inputs, Outputs, and Data Contracts

### 2.1 Inputs

- MongoDB `level-2` collection:
  - Job documents with fields like `jobId`, `dedupeKey`, `score`, `location`, `posted_at`, `job_url`, `tier`, etc.
- CLI arguments for the pipeline runner:
  - `--latest N`
  - `--location "City, Country"`
  - `--job-ids "id1,id2"`
  - Additional filters (e.g., score thresholds) as needed.
- Environment configuration (`Config`):
  - MongoDB connection details.
  - FireCrawl API keys and rate limit configs.

### 2.2 Data Contracts

- `JobState` fields populated / updated:
  - From Layer 1:
    - `job_id`
    - `title`
    - `company`
    - `location`
    - `description`
    - `criteria` (if available from DB)
    - `tier`
    - `status`
    - `run_id`, `created_at`, `updated_at`
  - From Layer 1.5:
    - `application_form_fields: List[FormField]`

- `FormField` TypedDict (shared types module):

  ```python
  class FormField(TypedDict):
      label: str
      field_type: Literal["text", "textarea", "url", "file", "checkbox", "select"]
      required: bool
      char_limit: Optional[int]
      word_limit: Optional[int]
      default_value: Optional[str]
      hint: Optional[str]
  ```

---

## 3. Layer 1 – Job Input Collector (`src/layer1/input_collector.py`)

### 3.1 Responsibilities

Layer 1 is responsible for:

- Fetching jobs from MongoDB based on CLI filters.
- Respecting deduplication and **previous pipeline runs**.
- Prioritizing the most promising jobs.
- Building initial `JobState` objects for each selected job.

This directly implements the **Job ingestion** requirement in `requirements.md`.

### 3.2 Detailed Steps

1. **Parse CLI arguments**
   - Read flags such as:
     - `--latest N` – limit to the most recently posted jobs.
     - `--location` – restrict to roles in specific geographic areas.
     - `--job-ids` – explicitly target certain jobs.
   - Validate that arguments are consistent (e.g., cannot combine mutually exclusive filters if any).

2. **Build MongoDB query**
   - Base filters:
     - Only jobs eligible for processing (e.g., `status` not set to archived or failed).
   - Add optional filters:
     - `location` (case-insensitive, partial match).
     - `posted_at` within last N days (derived from `--latest`).
     - Score threshold if configured.
   - Limit to a **maximum batch size** (e.g., 50 jobs) as specified in `requirements.md`.

3. **Deduplicate and skip already-processed jobs**
   - Exclude jobs where `pipeline_run_at` is set and is within a configured recent interval.
   - Use `dedupeKey` or `jobId` to avoid duplicates across sources.
   - This ensures the pipeline behaves idempotently and doesn’t re‑process jobs by default.

4. **Job prioritization**
   - Sort results by:
     - `tier` (if present) – higher tier jobs first.
     - `score` (descending).
     - `posted_at` (descending).
   - This matches the roadmap’s priority rule: “Sort by `score` then `posted_at` and respect `tier`.”

5. **Initialize `JobState` objects**
   - For each selected job document:
     - Populate the base `JobState` with all relevant fields.
     - Set:
       - `run_id` (UUID)
       - `created_at`, `updated_at`
       - `status` (e.g., `"queued"` or `"layer1_completed"` depending on orchestration)
   - This aligns with the architecture’s **stateful LangGraph** design and `JobState` definition.

6. **Return list of states**
   - The Input Collector returns `List[JobState]` to the LangGraph workflow.
   - These states become independent jobs in the graph (up to the concurrency limit).

### 3.3 UX and CLI Feedback

To support “terminal-native multi-progress display” and good developer UX:

- Log:
  - Total job count considered.
  - Count after filters, deduplication, and prioritization.
  - Clear messages when no jobs match filters.
- Provide a short summary per job (title, company, location, score) before starting the pipeline.

---

## 4. Layer 1.5 – Application Form Field Miner (`src/layer1_5/form_miner.py`)

### 4.1 Responsibilities

Layer 1.5:

- Scrapes the actual job posting URL (`job_url`) for each job.
- Extracts a structured representation of application form fields via an LLM.
- Writes both:
  - A machine-readable `application_form_fields` list in `JobState`, and
  - A human-readable checklist file per job:  
    `applications/<company>/<role>/application_form_fields.txt`

This fulfills the **Application Form Miner** component in `architecture.md` and the UX-focused requirements in `requirements.md`.

### 4.2 Detailed Steps

1. **Preconditions**
   - `JobState.job_url` is available.
   - FireCrawl configuration is valid (checked via `Config.validate()`).

2. **Scrape page content with FireCrawl**
   - Request the specific `job_url` (not generic company site).
   - Convert the HTML to markdown or simplified text.
   - Respect FireCrawl rate limits and add backoff/retries for network/server errors.
   - Log and tag failures in `JobState.errors` without stopping the entire job.

3. **Prepare LLM prompt for field extraction**
   - Inputs:
     - The scraped markdown content.
     - Optional `job_description` / criteria from `JobState` for extra context.
   - Instructions:
     - Identify **only** fields that appear in the page.
     - For each field, output:
       - `label`, `field_type`, `required`, `char_limit`/`word_limit` if visible, `hint`, `default_value` if visible.
     - Respond with **JSON-only** following the `FormField` schema.
     - If no fields are present, return an empty list.
     - Never invent fields “commonly present” but not visible in markup.

4. **Call LLM with retries and validation**
   - Use the standard retry decorator with exponential backoff.
   - On each attempt:
     - Parse the response as JSON.
     - Validate against the `FormField` schema.
   - If all attempts fail:
     - Set `application_form_fields` to an empty list.
     - Record an error in `JobState.errors`.

5. **Populate `JobState.application_form_fields`**
   - Store the validated list of fields.
   - Ensure that all string fields are trimmed and normalized.

6. **Write human-readable checklist file**
   - Path: `applications/<company>/<role>/application_form_fields.txt`.
   - Content:
     - Heading (job title, company, URL).
     - For each field:
       - Label
       - Type and “Required/Optional”
       - Any limits or hints.
   - This file acts as a **prep checklist** before manually filling out the real application form.

7. **Graceful degradation**
   - If scraping fails (network issues, blocked pages, etc.):
     - Continue pipeline with an empty `application_form_fields` list.
     - Annotate `JobState.errors` with reason.
   - This ensures that the **rest of the pipeline (Layers 2–6)** is not blocked by scraping issues.

---

## 5. Reliability, Resilience, and UX Considerations

- **Idempotent runs** – Layer 1 logic avoids re‑processing jobs with recent `pipeline_run_at` values, satisfying the requirements around efficient batch processing.
- **Rate-limit aware** – FireCrawl interaction uses backoff and caching where appropriate.
- **Clear failure modes** – All scraping and parsing failures are captured as structured errors in `JobState.errors` and do not crash the whole run.
- **Candidate-centric UX** – The application fields checklist reduces friction at the exact point where candidates typically lose time and context switching.

---

## 6. Alignment with `requirements.md`

Phase 3 implements:

- **Job ingestion**:
  - CLI-based selection of up to 50 jobs.
  - Filtering by `latest`, `location`, and explicit job IDs.
  - Parallel execution based on the list of `JobState` objects.

- **Data persistence & tracking**:
  - `JobState` initialization includes `run_id`, timestamps, and status fields.
  - Integration of `pipeline_run_at` and deduplication logic.

- **Control & quality**:
  - Manual review is supported by explicit logging and human-readable artifacts (`application_form_fields.txt`).
  - Error handling and graceful degradation behaviors match the global error-handling requirements.

---

## 7. Alignment with `architecture.md`

In the architecture:

- **Layer 1 (Input Collector)**:
  - Provides the stateful entrypoint to the 7-layer pipeline.
  - Ensures jobs arrive in a normalized, LangGraph‑friendly format.

- **Layer 1.5 (Job URL & Application Form Miner)**:
  - Runs early in the graph, before deeper analysis.
  - Directly reduces friction at the “real application” boundary.
  - Uses FireCrawl → LLM → JSON pattern that mirrors the rest of the system.

Together, these layers make the rest of the pipeline more efficient, focused, and user-friendly.

---

## 8. Testing and Quality Gates

1. **Layer 1 tests**
   - MongoDB query construction based on different CLI argument combinations.
   - Deduplication logic with various `pipeline_run_at` scenarios.
   - Priority ordering (tier > score > posted_at).

2. **Layer 1.5 tests**
   - Mock FireCrawl responses for different job pages (well-structured, messy, no form).
   - Mock LLM responses for field extraction, including malformed JSON that triggers retry logic.
   - Validation of `FormField` structure and checklist file formatting.

3. **End-to-end smoke tests**
   - From CLI → Layer 1 → Layer 1.5 → Layer 2 for a small batch.
   - Confirm that jobs flow correctly and that missing form data does not break downstream layers.

These gates ensure Phase 3 provides a solid, user-focused front door to the rest of the system.

