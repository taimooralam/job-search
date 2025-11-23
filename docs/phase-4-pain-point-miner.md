# Phase 4 – Layer 2: Pain-Point Miner

This document expands **Phase 4** of the roadmap and describes in detail how the Pain-Point Miner (Layer 2) is designed and implemented to meet the **requirements** and **architecture**.

It covers:

1. Objectives and role in the pipeline  
2. Inputs, outputs, and state contract  
3. LLM prompt and response design  
4. Implementation steps and control flow  
5. Non-hallucination and validation strategies  
6. Alignment with `requirements.md` and `architecture.md`  
7. Testing and quality gates  

---

## 1. Objectives and Role in the Pipeline

**Goal:** Transform raw job descriptions into a structured representation of business context that downstream layers can reason about:

- `pain_points` – why the company needs this role now.  
- `strategic_needs` – what outcomes they seek.  
- `risks_if_unfilled` – what goes wrong if the role remains open.  
- `success_metrics` – how success will be measured.  

Layer 2 is the **first reasoning layer** after input collection, and it:

- Powers STAR selection (Layer 2.5).  
- Provides a backbone for company research, opportunity mapping, people mapping, and outreach.  
- Enforces the “JSON-only, business-focused” contract described in `architecture.md`.  

---

## 2. Inputs, Outputs, and State Contract

### 2.1 Inputs

- `JobState` fields from Layer 1:
  - `title`
  - `company`
  - `location`
  - `description`
  - `criteria` (if available)
  - `job_url`
  - Any metadata useful for context (industry, seniority).
- Global configuration:
  - LLM model (GPT-4o via OpenRouter).
  - Temperature (`0.3` – analytical).

### 2.2 Outputs

The Pain-Point Miner **must** populate the following fields in `JobState`:

- `pain_points: List[str]` (3–6 items)
- `strategic_needs: List[str]` (3–6 items)
- `risks_if_unfilled: List[str]` (2–4 items)
- `success_metrics: List[str]` (3–5 items)

These outputs are consumed by:

- **Layer 2.5 (STAR Selector)** – uses them to score STARs.
- **Layer 3 (Company + Role Researcher)** – uses them as a lens to interpret signals.
- **Layer 4 (Opportunity Mapper)** – uses them for fit scoring and rationale.
- **Layer 5 (People Mapper)** and **Layer 6 (Outreach)** – reference them to keep messaging “pain → proof → plan” focused.

---

## 3. LLM Prompt and Response Design

### 3.1 Prompt Goals

The prompt is designed to:

- Extract **business context**, not HR boilerplate.
- Force specific, company/role/industry‑tuned bullets.
- Return strictly **JSON-only** output that can be parsed and validated.

### 3.2 Prompt Structure (Conceptual)

1. **System message**
   - Describes the assistant as a business-focused hiring analyst.
   - Emphasizes:
     - No generic traits (“team player”, “communication skills”) unless explicitly present and linked to business outcomes.
     - No hallucinated company facts; only use the job description text.
     - Output must be a single JSON object.

2. **User message**
   - Includes:
     - Job title, company, location.
     - Full job description and criteria.
   - Clear instructions to produce:

     ```json
     {
       "pain_points": [...],
       "strategic_needs": [...],
       "risks_if_unfilled": [...],
       "success_metrics": [...]
     }
     ```

   - Specifies the required bullet counts:
     - 3–6 pain points and strategic needs.
     - 2–4 risks if unfilled.
     - 3–5 success metrics.

3. **Examples (optional)**
   - Provide 1–2 short, anonymized examples of good outputs for similar roles to anchor style and specificity.

### 3.3 JSON-Only Contract

- The prompt explicitly states:
  - “Return **only** a JSON object, with no extra text before or after.”
- The implementation:
  - Trims whitespace.
  - Rejects responses with any non‑JSON leading or trailing text.

---

## 4. Implementation Steps and Control Flow (`src/layer2/pain_point_miner.py`)

### 4.1 Pre-checks

1. Validate that required `JobState` fields are present (title, company, description).
2. If the description is missing or too short:
   - Optionally aggregate additional context from the DB.
   - If still insufficient, mark the job with a validation flag and either:
     - Skip Layer 2 for this job, or
     - Run with a warning and store minimal results.

### 4.2 LLM Call with Retry Logic

1. Build the input prompt from `JobState`.
2. Call the LLM using:
   - Configured client (OpenRouter).
   - Model `gpt-4o`.
   - Temperature `0.3`.
3. Wrap the call in a retry decorator:
   - Up to 3 attempts.
   - Exponential backoff (e.g., 1s, 2s, 4s).
   - Retries on:
     - Network errors.
     - 5xx API responses.
     - JSON parsing/validation failures.

### 4.3 Response Parsing and Validation

1. Parse the raw string as JSON.
2. Validate:
   - All four keys are present.
   - Each value is a list of strings.
   - Bullet counts meet minimum thresholds.
3. Additional semantic checks:
   - Non-empty, non-duplicated items.
   - No obviously generic phrases (e.g., “good communication skills”) unless the job description truly emphasizes them.
   - Length constraints for each bullet (short phrases, not long paragraphs).

4. If validation fails:
   - Retry with adjusted instructions, or
   - On final failure, record error in `JobState.errors` and mark the job with a `validation_flags` entry.

### 4.4 State Update

On success:

- Write the validated lists to `JobState`:
  - `pain_points`
  - `strategic_needs`
  - `risks_if_unfilled`
  - `success_metrics`
- Update timestamps and status (e.g., `status = "layer2_completed"`).

---

## 5. Non-Hallucination and Validation Strategies

Non-hallucination is a core principle in this system.

Layer 2 enforces it via:

- **Context-only rule** – prompt instructs the LLM to use only the provided job description, not external knowledge.
- **Company fact discipline** – anything that sounds like a funding round, acquisition, or product launch must not appear here; those belong in Layer 3 with web context.
- **Schema validation** – any deviation from the JSON schema triggers retries.
- **Content heuristics** – detection of generic, uninformative bullets encourages more specific language.

These strategies ensure downstream layers (STAR selection, research, outreach) build on **accurate, grounded** business context.

---

## 6. Alignment with `requirements.md`

Layer 2 implements:

- The **Analysis layers** requirement (Pain-Point Miner) as the first major analytic step.
- The **STAR-Based Personalization** requirement by:
  - Producing the structured pain points that Layer 2.5 uses as its primary input.
- Broader **Control & Quality** requirements:
  - Error handling via `JobState.errors` and `validation_flags`.
  - JSON-only state that is easy to store in MongoDB and trace with LangSmith.

---

## 7. Alignment with `architecture.md`

In the architecture:

- Layer 2 is explicitly defined as the **Pain-Point Miner**:
  - It transforms the job description into structured JSON with four categories.
  - It extends `JobState` with the four new fields.
- This layer’s outputs are referenced in:
  - Layer 2.5 (STAR Selector).
  - Layer 4 (Opportunity Mapper).
  - Layer 5 and Layer 6 for outreach personalization.

Phase 4 therefore locks in the **business reasoning spine** that ties the entire pipeline together.

---

## 8. Testing and Quality Gates

1. **Unit tests with mocked LLM**
   - Validate JSON parsing and schema enforcement.
   - Test response variations (missing keys, wrong types, extra fields).
   - Confirm that retry logic behaves correctly.

2. **Content tests**
   - For 5 sample job descriptions:
     - Ensure output is JSON-only.
     - Verify the minimum bullet counts per category.
     - Check that bullets are specific to the job/company/industry.

3. **Hallucination checks**
   - Use synthetic jobs with minimal information to ensure the LLM:
     - Either produces conservative, generic business statements or fails gracefully.
     - Does not fabricate specific company facts.

Meeting these gates ensures Layer 2 is reliable, explainable, and aligned with the overall design.

