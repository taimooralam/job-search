# Prompt Modernization Blueprint

Comprehensive prompt-improvement plan for the Job Intelligence Pipeline, grounded in the techniques from `thoughts/prompt-generation-guide.md`. The objective is to upgrade every LangGraph layer so each LLM call consistently applies the universal pattern: **persona → context → reasoning instructions → format constraints → improvement loop**.

---

## Source Material & Goals
- **Reference**: `thoughts/prompt-generation-guide.md` (Personas §1.1, Context §1.2, Tree-of-Thoughts §3.1, Battle-of-the-Bots §3.2, Constraint Prompting §3.5, Output Calibration §3.6, Prompt→Evaluate→Improve §4.1).
- **Architecture**: `src/workflow.py`, `plans/architecture.md`.
- **Goal**: Increase downstream quality (pain mining → research → fit → outreach → deliverables) without reordering LangGraph nodes.

---

## Universal Prompt Scaffolding
Apply this template to every LLM call before layer-specific tweaks:

1. **Persona Block** – “You are …” with role expertise (guide §1.1).
2. **Mission Statement** – Single sentence describing the outcome metric.
3. **Context Packets** – Structured sections (JOB, COMPANY SIGNALS, STARs, etc.) mapping directly to `JobState` data (guide §1.2).
4. **Reasoning Stage** – Explicit instructions to think step-by-step (guide §2.1/§2.2) and list missing info (output calibration, §3.6).
5. **Constraints & Format** – Bullet list of hard requirements, plus JSON/text schema (guide §3.5).
6. **Self-Eval Loop** – “Score your output on clarity/accuracy/completeness; if <9, revise” (guide §3.2 & §3.5.3).

Embed one few-shot exemplar wherever possible (guide §2.3) and use Show+Ask rubrics (§2.4) for high-variance outputs.

---

## Layer-by-Layer Improvements

### Layer 2 – Pain Point Miner (`src/layer2/pain_point_miner.py`)
- **Persona**: “Revenue-operations diagnostician” to bias toward measurable business problems.
- **Reasoning-first**: Require an internal “Reasoning” block (hidden) before emitting JSON.
- **Few-shot anchor**: Provide one short JD + perfect JSON pair before the actual JD.
- **Missing-info capture**: Ask “List any context gaps before generating; if list non-empty, proceed but highlight assumptions in reasoning.”
- **Format upgrade**:
  ```markdown
  SYSTEM:
    - Persona + mission
    - Chain-of-thought instructions
    - Guardrails (no hallucinations, no boilerplate)
  USER:
    - Context sections (JOB, PRIOR SIGNALS, MASTER CV DOMAIN HINTS)
    - Example block (Optional)
    - Output instructions with `<final>{JSON}</final>`
  ```

### Layer 2.5 – STAR Selector (`src/layer2_5/select_stars.py`)
- **Tree-of-Thoughts**: Ask for three candidate STAR mappings, score each 1–10 for relevance, choose the highest (guide §3.1).
- **Battle-of-the-Bots**: Introduce a “Skeptical hiring manager” critique stage; regenerate if critique flags missing metrics (§3.2).
- **Constraint**: Demand explicit ties to pain points (“STAR → Pain point IDs”).

### Layer 3 – Company Researcher (`src/layer3/company_researcher.py`)
- **Persona**: “Business intelligence analyst specializing in diligence” with emphasis on citing sources.
- **Candidate-aware context**: Automatically pass `{candidate_domains}` and `{candidate_outcomes}` from master CV tags so the LLM prioritizes relevant facts.
- **Rubric self-check**: After drafting JSON, ask the model to score each signal for specificity/source quality; remove any rated <7 before final output (§3.5, §3.6).
- **Few-shot**: Include “GOOD signal vs BAD signal” pair to illustrate desired granularity (guide §2.4).

### Layer 3.5 – Role Researcher (`src/layer3/role_researcher.py`)
- **Tree-of-Thoughts**: Generate three “Why now” hypotheses referencing different inputs (JD, company signals, market news), then select the best with justification.
- **Assumption ledger**: Provide two lists—“Confirmed facts” vs “Assumptions”—per anti-hallucination guidelines (§3.4).
- **Output calibration**: Flag sections where evidence is thin (“Confidence: Low – missing competitive intel”).

### Layer 4 – Opportunity Mapper (`src/layer4/opportunity_mapper.py`)
- **Structured reasoning**: Force the model to fill a table before scoring:
  - Strengths (Top 3)
  - Gaps (Top 2)
  - Risk mitigations
  - Alignment with company signals
- **Scoring rubric**: Provide explicit thresholds (already present) but require citing at least one metric; add “If insufficient evidence, emit `SCORE: INSUFFICIENT_DATA` and list needed info.”
- **Self-check**: “Rate rationale 1–10 on specificity; rewrite until ≥9” (guide §3.5.3).

### Layer 5 – People Mapper (`src/layer5/people_mapper.py`)
- **Persona multiplexing**: Run persona instructions for (a) Recruiter, (b) Hiring manager, (c) Executive sponsor; each proposes contacts, and a final arbiter consolidates (Battle-of-the-Bots, §3.2).
- **Debate loop**: Skeptical persona challenges whether each contact actually influences hiring; discard entries that fail the debate (§5.2).
- **Fallback clarity**: Provide few-shot examples of role-based placeholders so the model keeps specificity even without names.
- **Constraint reinforcement**: Spell out min/max counts as equations; instruct the model to validate before final JSON.

### Layer 6a – CV & Cover Letter Generator (`src/layer6/generator.py`)
- **Reasoning plan**: Ask for an outline referencing STAR IDs, then final narrative (Reasoning-first, §2.2).
- **Rubric referencing**: Provide evaluation rubric (JD specificity, metric density, voice) and require self-scoring + revision loop until each dimension ≥9 (Prompt→Evaluate→Improve, §4.1).
- **Persona**: Blend “Executive career marketer” and “Mentor” to capture both persuasive tone and critique mindset.
- **Calibration**: Have the model list missing achievements or data needed for a perfect draft; log this for future iterations.

### Layer 6b – Outreach Generator (`src/layer6/outreach_generator.py`)
- **Hard constraints inline**: “Count characters and include totals” to prevent retries (Constraint prompting, §3.5).
- **Reasoning block**: Template:
  ```text
  PLAN:
    - Hook idea
    - Value proof
    - CTA phrasing
  FINAL:
    Hi …
  ```
- **Persona duel**: Generator persona writes draft; critic persona checks against LinkedIn/email rubric (Battle-of-the-Bots, §3.2).
- **Few-shot**: Store top-performing outreach samples and pass them as examples for similar industries (Few-shot, §2.3).

### Layer 7 – Publisher / Dossier (`src/layer7/output_publisher.py`)
- **Narrative clarity**: Use persona “Hiring committee secretary” to summarize outputs with emphasis on decision readiness.
- **Confidence scores**: Ask the model to assign High/Medium/Low confidence per artifact and explain deficits (Output calibration, §3.6).
- **Improvement prompts**: Capture “Next iteration opportunities” so future pipeline runs know what to focus on.

---

## Implementation Checklist
1. **Central Prompt Registry**: Create `src/common/prompts.py` with helper builders applying the universal scaffold.
2. **Shared Few-Shot Store**: Persist exemplar prompts/responses (YAML/JSON) keyed by layer.
3. **Testing Hooks**: Extend existing tests to assert new validation outputs (e.g., presence of `<final>` tags, confidence blocks).
4. **Telemetry**: Log self-scored quality metrics per run to measure impact (fit rationale specificity, outreach rubric compliance).

---

## Expected Impact
- **Higher-quality reasoning** → better pain points, fit scores, outreach targeting → more qualified leads/interviews/offers.
- **Reduced hallucinations** by forcing assumption ledgers and source scoring.
- **Faster iteration** because Prompt→Evaluate→Improve loops happen within a single model call, reducing manual retries.

Ship these prompt upgrades incrementally (layer-by-layer) while continuing to run the existing workflow so the application cadence is unaffected. Ground each change in the prompt guide to maintain consistency and maximize ROI.
