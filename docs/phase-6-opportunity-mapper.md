# Phase 6 – Layer 4: Opportunity Mapper

This document expands **Phase 6** of the roadmap and explains how the Opportunity Mapper (Layer 4) is designed and implemented to meet the **requirements** and **architecture**.

It covers:

1. Objectives and role in the pipeline  
2. Inputs, outputs, and state contract  
3. Fit scoring rubric and categories  
4. LLM analysis and rationale generation  
5. Validation, non-hallucination, and STAR citation checks  
6. Alignment with `requirements.md` and `architecture.md`  
7. Testing and quality gates  

---

## 1. Objectives and Role in the Pipeline

**Goal:** Provide a **single, authoritative assessment** of how well the candidate fits each job, with:

- A numeric `fit_score` (0–100).  
- A categorical `fit_category` (“exceptional”, “strong”, “good”, “moderate”, “weak”).  
- A detailed `fit_rationale` that explicitly cites STAR IDs, metrics, and company signals.  

Layer 4 acts as:

- The bridge between **analysis** (pain points, research, STAR selection) and **generation** (outreach and CV).  
- The primary **decision signal** used to prioritize jobs and drive messaging.  

---

## 2. Inputs, Outputs, and State Contract

### 2.1 Inputs

From previous layers:

- `JobState.pain_points`
- `JobState.strategic_needs`
- `JobState.risks_if_unfilled`
- `JobState.success_metrics`
- `JobState.selected_stars`
- `JobState.star_to_pain_mapping`
- `JobState.company_research`
- `JobState.role_research`

### 2.2 Outputs

Layer 4 must populate:

- `fit_score: int` (0–100)
- `fit_rationale: str` (3–5 sentences)
- `fit_category: Literal["exceptional", "strong", "good", "moderate", "weak"]`

These outputs are consumed by:

- **Layer 6a (Cover Letter & CV Generator)** – to shape tone, confidence, and narrative.
- **Layer 6b (Lead Outreach JSON Generator)** – to prioritize leads and personalize messaging.
- **Layer 7** – for logging to MongoDB and Google Sheets.

---

## 3. Fit Scoring Rubric and Categories

### 3.1 Rubric Definition

The scoring rubric connects qualitative reasoning to a numeric score:

- **90–100 – Exceptional fit**
  - 3+ STARs directly address the most important pain points and success metrics.
  - Metrics show strong, recent, and highly relevant achievements.
- **80–89 – Strong fit**
  - At least 2 STARs align well with key pain points.
  - Some minor gaps, but overall profile is very compelling.
- **70–79 – Good fit**
  - 1–2 relevant STARs with solid metrics.
  - Some experience is adjacent rather than direct.
- **60–69 – Moderate fit**
  - Experience is partially aligned; relevant competencies but not a perfect match.
  - Gaps in either domain, scale, or recency.
- **<60 – Weak fit**
  - Limited overlap between STARs and pain points.
  - Significant gaps in key requirements or scale.

### 3.2 Implementation of Rubric

1. **Heuristic pre-score (optional)**
   - Compute a preliminary numeric score using:
     - Count of pain points covered by `selected_stars`.
     - Average relevance from Layer 2.5 (if available).
     - Alignment between success metrics and STAR metrics.

2. **LLM-adjusted score**
   - Provide the heuristic pre-score to the LLM as context.
   - Ask the LLM to:
     - Adjust the score within a narrow band (e.g., ±10 points) based on holistic reasoning.
     - Assign the category and explanation consistent with the rubric.

3. **Final mapping**
   - Map the final numeric score to one of the five categories using clear thresholds.

---

## 4. LLM Analysis and Rationale Generation (`src/layer4/opportunity_mapper.py`)

### 4.1 Prompt Design

Inputs to the LLM:

- Job title, company, and core job description.
- Pain points, strategic needs, risks, success metrics.
- Selected STARs (IDs, short summaries, key metrics).
- `star_to_pain_mapping`.
- Company and role research (summaries + key signals).

Instructions:

- Evaluate the candidate’s fit for this role.
- Produce:
  - `fit_score` (0–100).
  - `fit_category`.
  - `fit_rationale` – 3–5 sentences that:
    - Explicitly reference at least **one STAR ID and metric**.
    - Tie STARs to specific pain points and/or success metrics.
    - Use at least one company signal or role insight when available.
- Use only the provided information; do not invent history, employers, or events.

### 4.2 JSON Output Contract

The LLM should return JSON-only:

```json
{
  "fit_score": 92,
  "fit_category": "exceptional",
  "fit_rationale": "..."
}
```

Implementation:

- Parse the JSON.
- Validate:
  - `fit_score` is an integer between 0 and 100.
  - `fit_category` is one of the allowed strings.
  - `fit_rationale` is non-empty and reasonably short (e.g., < 800 characters).

---

## 5. Validation, Non-Hallucination, and STAR Citation Checks

### 5.1 STAR Citation Checks

After parsing:

1. Ensure `fit_rationale` mentions at least one **STAR ID**:
   - Simple pattern: `"STAR"` followed by digit(s) or use known IDs from `selected_stars`.
2. Ensure `fit_rationale` includes at least one **metric-like token**:
   - Numbers with `%`, currency, or clearly quantitative statements.
3. If these checks fail:
   - Optionally:
     - Retry with a more explicit prompt instruction.
     - Or append a validation error and lower the `fit_score`.

These checks enforce the roadmap requirement: “Must cite ≥1 STAR ID and metric.”

### 5.2 Genericness and Specificity Checks

Detect generic rationales:

- Look for overuse of vague phrases:
  - “strong background”, “great fit”, “excellent skills” without concrete details.
- Validate that at least one pain point or strategic need phrase appears in the rationale.
- If the rationale is too generic:
  - Either:
    - Retry the LLM call with stricter instructions, or
    - Mark the job with a `validation_flags` entry and optionally reduce the `fit_score`.

### 5.3 Non-Hallucination Constraints

The prompt and implementation jointly ensure:

- No invented employers, roles, or metrics beyond what is in `selected_stars` and the job description.
- No fabricated company events; company signals must come from `company_research.signals`.
- If the candidate is a weaker fit:
  - The LLM is allowed and encouraged to say so, rather than over-selling.

---

## 6. Alignment with `requirements.md`

Layer 4 supports multiple requirements:

- **STAR-Based Personalization**:
  - Consumes `selected_stars` and `star_to_pain_mapping`.
  - Requires STAR IDs and metrics in rationale.

- **Generation & Output**:
  - `fit_score` is logged to MongoDB and Google Sheets (Layer 7).
  - Guides later generation layers (cover letter, CV, outreach).

- **Control & quality**:
  - Uses JSON schemas, retry logic, and validation flags.
  - Provides a central, numeric signal that can be used to:
    - Filter weak-fit jobs.
    - Prioritize outreach for high-fit opportunities.

---

## 7. Alignment with `architecture.md`

The architecture defines the Opportunity Mapper as:

- A layer that takes:
  - Pain points and research from previous layers.
  - STAR selections from Layer 2.5.
  - Produces a fit score and short rationale.

Phase 6 extends this with:

- A precise rubric that maps reasoning to scores and categories.
- Mandatory STAR and metric citations.
- Robust validation and non-hallucination checks.

This ensures that the Opportunity Mapper is not just a “nice-to-have explanation” but a **reliable decision engine** for the entire pipeline.

---

## 8. Testing and Quality Gates

1. **Unit tests with mocked LLM**
   - Validate JSON parsing and schema enforcement.
   - Check STAR ID and metric presence detection.

2. **Content tests**
   - For 5 test jobs with varying degrees of fit:
     - Ensure scores and categories are consistent with the rubric.
     - Confirm rationales reference specific STARs, metrics, and pain points.

3. **Edge cases**
   - Jobs with very few relevant STARs (weak fit).
   - Jobs with ambiguous pain points or minimal company signals.

These tests confirm that Layer 4 provides stable, interpretable, and high-quality fit assessments that downstream layers can safely rely on.

