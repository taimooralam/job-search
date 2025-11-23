# Phase 2 – STAR Library & Candidate Knowledge Base

This document expands **Phase 2** of the roadmap and explains how the STAR library and selector are designed and implemented to satisfy the system **requirements** and **architecture**.

It covers:

1. Objectives and scope  
2. Inputs, outputs, and data contracts  
3. Detailed implementation steps (parser, embeddings, MongoDB, selector)  
4. Reliability, safety, and non‑hallucination controls  
5. Alignment with `requirements.md` and `architecture.md`  
6. Testing and quality gates  

---

## 1. Objectives and Scope

**Goal:** Build a robust, reusable STAR library and selection layer that turns the static `knowledge-base.md` file into structured, queryable data and then selects the best 2–3 achievements per job based on the job’s pain points.

This phase addresses:

- The **STAR-Based Personalization (Layer 2.5)** requirement in `requirements.md`
- The **STAR Parser & Selector** components described in `architecture.md` (Layer 2.5)
- The Phase 2 roadmap items:
  - 2.1 STAR Parser & Structured Knowledge Base  
  - 2.2 Hybrid STAR Selector  

High-level outcomes:

- `knowledge-base.md` is parsed into validated `STARRecord` objects.
- Each STAR is enriched with embeddings and stored in MongoDB.
- A hybrid selector (embeddings + LLM scoring) maps job pain points to the most relevant STARs.
- Downstream layers (4, 6a, 6b) receive **precise, metric-backed** achievements instead of a monolithic blob.

---

## 2. Inputs, Outputs, and Data Contracts

### 2.1 Inputs

- `knowledge-base.md` – curated STAR stories in human-readable markdown.
- `JobState.pain_points`, `JobState.strategic_needs`, `JobState.risks_if_unfilled`, `JobState.success_metrics` – produced by Layer 2 (Pain-Point Miner).
- Configuration:
  - Model and API keys (OpenRouter / OpenAI embeddings, LLM ranker).
  - Selection strategy (`LLM_ONLY`, `HYBRID`, `EMBEDDING_ONLY`).

### 2.2 Core Types

- `STARRecord` (TypedDict, defined in shared types module):

  ```python
  class STARRecord(TypedDict):
      id: str
      company: str
      role: str
      timeframe: str  # "2019-2022"
      situation: str
      task: str
      actions: List[str]
      results: str
      metrics: List[str]
      keywords: List[str]
      embedding: Optional[List[float]]
  ```

- Additional state:
  - `JobState.selected_stars: List[STARRecord]`
  - `JobState.star_to_pain_mapping: Dict[str, List[str]]`

### 2.3 Outputs

For each job:

- `selected_stars`: The 2–3 highest‑relevance STARs for this job.
- `star_to_pain_mapping`: A mapping from `STARRecord.id` to the pain points / strategic needs it addresses.
- MongoDB:
  - `star_records` collection with:
    - Parsed STAR fields
    - Embedding vector
    - Metadata (timestamps, versioning)

These outputs are consumed by:

- **Layer 4 (Opportunity Mapper)** – fit scoring and rationale must cite STAR IDs and metrics.
- **Layer 6a / 6b (Cover Letter & Outreach)** – paragraphs and bullets must use `selected_stars`.

---

## 3. Implementation – STAR Parser (`src/common/star_parser.py`)

### 3.1 Parsing Strategy

1. **Load source markdown**
   - Read `knowledge-base.md` from the repository.
   - Split the file into blocks corresponding to individual STAR records (e.g., using headings or delimiters defined in `knowledge-base.md`).

2. **Extract structured fields**
   - For each block:
     - Parse required fields: `id`, `company`, `role`, `timeframe`, `situation`, `task`, `actions`, `results`.
     - Parse `metrics` and `keywords` as **lists of short strings**.
   - Use explicit markers where possible (e.g., `**Situation:**`, `**Task:**`) to reduce brittleness.

3. **Validation & normalization**
   - Validate presence of **required fields**:
     - Fail the record (with a warning) if `id`, `company`, `role`, `situation`, `task`, or `results` are missing.
   - Normalization:
     - Trim whitespace, collapse multiple spaces, normalize newlines.
     - Lowercase or normalize `keywords` for easier matching.
   - Metrics:
     - Require at least one **quantified metric** (`%`, absolute numbers, or time-based KPIs) per STAR.
     - Warn if no metrics are found and skip or mark as low-quality depending on configuration.

4. **Lenient handling of malformed records**
   - If a STAR block fails validation:
     - Log a structured warning with context (STAR id if available, line numbers).
     - Skip the record but continue parsing remaining blocks.
   - This aligns with the roadmap requirement: *“Lenient parsing: Skip malformed records with warnings.”*

5. **Return value**
   - Return `List[STARRecord]` with all valid records.

### 3.2 CLI Tool – `scripts/parse_stars.py`

1. Entry point:
   - `python -m scripts.parse_stars` (or `scripts/parse_stars.py`).
2. Behavior:
   - Calls `star_parser.parse()` to parse `knowledge-base.md`.
   - Writes a summary (count of records, warnings) to stdout.
   - Persists results to MongoDB (`star_records` collection).
   - Optionally writes a JSON export for debugging (e.g., `data/star_records.json`).

### 3.3 MongoDB Persistence

1. Upsert strategy:
   - Use `id` as the primary key.
   - On re-run, update existing entries (idempotent, safe to run multiple times).
2. Schema:
   - Mirror `STARRecord` fields.
   - Add metadata:
     - `created_at`, `updated_at`
     - `version` (optional, for future schema changes)
3. Indexing:
   - Index on `id`.
   - Optional compound index on `company`, `role` for debugging queries.

---

## 4. Implementation – Embedding Generation

### 4.1 Embedding Model

- Use OpenAI `text-embedding-3-small` (via OpenRouter) as specified in the roadmap.
- The embedding input is a compact representation:
  - `company`, `role`, `situation`, `task`, `results`, `metrics`, `keywords`.
  - Concatenate these with clear labels to give the model structure.

### 4.2 Embedding Workflow

1. **Batching**
   - Embed STARs in batches to respect rate limits.
   - Use a retry decorator with exponential backoff for transient failures.

2. **Idempotency**
   - Only compute embeddings for STARs that:
     - Are new, or
     - Have changed since last run (based on hash of core fields).
   - Store the hash in MongoDB for change detection.

3. **Persistence**
   - Write the embedding vector back to `star_records.embedding`.
   - Ensure embedding dimension matches the model spec.

4. **Error handling**
   - If embedding generation fails for a specific STAR:
     - Log the error with STAR id.
     - Continue processing other STARs.
   - Downstream selector can still use LLM-only mode if embeddings are missing.

---

## 5. Implementation – Hybrid STAR Selector (`src/layer2_5/star_selector.py`)

### 5.1 Inputs and Configuration

- Inputs:
  - `JobState` with populated:
    - `pain_points`
    - `strategic_needs`
  - Optionally `risks_if_unfilled`, `success_metrics` for richer context.
  - STAR records from MongoDB (`star_records`).
- Configuration:
  - `selection_strategy`: `HYBRID` (default), `LLM_ONLY`, or `EMBEDDING_ONLY`.
  - Maximum number of STARs to return (2–3).

### 5.2 Embedding-Based Candidate Filter

1. Build a **query embedding** per job:
   - Concatenate pain points and strategic needs into a single text string.
   - Generate one embedding using the same model as STAR records.

2. Compute similarity:
   - For each STAR, compute cosine similarity between query embedding and `STARRecord.embedding`.
   - Filter to top **5–7** STARs as candidates.

3. Rationale:
   - This step provides a **fast, scalable, model-agnostic pre‑filter** that narrows down the search space.
   - It satisfies the roadmap’s requirement for a `HYBRID` strategy and supports future expansion to larger STAR libraries.

### 5.3 LLM-Based Ranker

1. Prompt design:
   - Provide:
     - Job title, company, and summary of pain points / strategic needs.
     - Candidate STARs (5–7), each with id, short description, and key metrics.
   - Instructions:
     - Score each STAR **0–10** for how well it addresses each pain point.
     - Use **only provided STAR text**; no external knowledge or invented achievements.
     - Return **JSON-only** with a stable schema:

       ```json
       {
         "scores": [
           {
             "star_id": "STAR-1",
             "overall_score": 9.2,
             "per_pain_point": {
               "pain_point_1": 9,
               "pain_point_2": 8
             },
             "reason": "..."
           }
         ]
       }
       ```

2. Non-hallucination controls:
   - Explicit prompt constraints: “If a STAR does not clearly address a pain point, assign a low score and explain why. Do not invent details not present in the STAR text.”
   - Validate that:
     - All `star_id` values correspond to known STARs.
     - No extra, unknown STAR IDs are introduced.

3. Retry and validation:
   - Use a retry decorator with exponential backoff (as mandated for LLM calls).
   - On each attempt:
     - Parse JSON.
     - Validate schema (presence of required fields, numeric scores).
   - If validation fails after maximum retries:
     - Fallback to `EMBEDDING_ONLY` mode for this job and record an error in `JobState.errors`.

### 5.4 Selection Logic and Mapping

1. Aggregate scores:
   - For each STAR candidate:
     - Compute `overall_score` as a weighted average of per‑pain‑point scores.
     - Optionally give more weight to top N pain points.

2. Select top 2–3 STARs:
   - Sort by `overall_score` descending.
   - Pick top 2–3 items, with tie-breaking by:
     - Diversity of metrics (avoid selecting multiple STARs that prove the exact same thing).
     - Coverage of different pain points.

3. Build `star_to_pain_mapping`:
   - For each selected STAR:
     - Collect all pain points with score above a threshold (e.g., ≥7).
     - Store as `Dict[str, List[str]]` keyed by `star_id`.

4. Write into `JobState`:
   - `selected_stars`: full STAR objects (including metrics, actions).
   - `star_to_pain_mapping`: mapping described above.

5. Downstream rationale:
   - Provide a short internal explanation for each selected STAR (to be used by Layer 4 and 6):
     - Why it was selected.
     - Which pain points it addresses.
     - Which metrics are most relevant.

---

## 6. Reliability, Safety, and Non‑Hallucination Controls

Phase 2 is central to the **quality-first, zero hallucination tolerance** principle.

Key controls:

- **Structured parsing only** – STAR library is derived from a tightly structured markdown format to reduce ambiguity.
- **Strict validation** – malformed STARs never reach the selector; they are skipped with explicit warnings.
- **JSON-only LLM outputs** – all LLM responses are parsed as JSON and validated against schemas.
- **No invented achievements** – prompts explicitly forbid adding history not found in `knowledge-base.md`.
- **Graceful fallbacks** – if embeddings or LLM ranking fail, fallback modes ensure the system still produces reasonable selections while recording issues in `JobState.errors`.

These controls directly support:

- Requirements around **personalization depth**, **error handling**, and **state tracking**.
- Architecture requirements for **JSON-only contracts** and **non-hallucinating, context‑bounded LLM usage**.

---

## 7. Alignment with `requirements.md`

Phase 2 directly addresses:

- **STAR-Based Personalization (Layer 2.5 – NEW)**  
  - The parser implements step 1 (“Parse `knowledge-base.md` into structured STAR objects”).  
  - The selector implements steps 2–4 (“Score”, “Select”, “Map”).  
  - Outputs (`selected_stars`, `star_to_pain_mapping`) match the required state fields.

- **Generation & Output (Layers 6–7)**  
  - By limiting downstream layers to `selected_stars`, we ensure cover letters, CVs, and dossiers cite **specific, metric-backed achievements** instead of generic profile text.

- **Control & Quality**  
  - Retry logic, JSON validation, and `JobState.errors` integration satisfy the error handling and traceability requirements.

---

## 8. Alignment with `architecture.md`

Phase 2 implements and strengthens the architecture’s Layer 2.5 description:

- **Explicit STAR selection** instead of passing the full 4,456‑character knowledge base.
- **Pain → Proof → Plan** pattern:
  - Pain points from Layer 2.
  - Proof via `selected_stars` with metrics.
  - Plan articulated later in Opportunity Mapper and Outreach layers.
- **Stateful design**:
  - `selected_stars` and `star_to_pain_mapping` are first‑class members of `JobState`, making the selection traceable and testable across the graph.

This phase ensures that every later artifact is grounded in the same, shared, structured achievements.

---

## 9. Testing and Quality Gates

The roadmap defines strict quality gates for Phase 2. Implementation should include:

1. **Parser tests**
   - Happy path: all 11 STAR records parsed.
   - Edge cases: missing fields, malformed markdown, duplicate IDs.
   - Verify that malformed records are skipped with warnings, not crashes.

2. **Embedding tests**
   - Validate embedding dimension and type.
   - Ensure repeated runs do not create duplicate records.

3. **Selector tests**
   - Use mocked embeddings and LLM responses.
   - Verify that:
     - At least 2–3 STARs are selected when candidates exist.
     - `star_to_pain_mapping` correctly links STAR IDs to pain points.
     - Fallback strategies work when LLM responses are invalid.

4. **End-to-end checks**
   - For 5 representative jobs:
     - Selection results are **intuitively correct**.
     - Downstream fit rationales and cover letters cite the selected STAR IDs and metrics.

Meeting these gates confirms that Phase 2 delivers the structured, reliable personalization backbone envisioned in the roadmap, requirements, and architecture documents.

