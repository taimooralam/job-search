# System Notes – STAR Design & Usage

## 1. What your STARs really are

- Each STAR is the canonical, lossless source of truth for a single CV bullet (or cluster of closely related bullets) — not just a shorthand note.
- The schema you described is rich enough to support three distinct uses:
  - Narrative grounding: BACKGROUND_CONTEXT + S/T/A/R + IMPACT_SUMMARY.
  - Retrieval & matching: DOMAIN_AREAS, CATEGORIES, HARD/SOFT_SKILLS, ATS_KEYWORDS, METRICS.
  - Compression for generation: CONDENSED_VERSION, plus a few key metrics.
- The problem you’re seeing (“STAR input to outreach/cover letter/CV not working properly”) is mostly:
  - Incomplete/under-structured records (Dimension A).
  - The LLM getting a giant blob of semi-structured content without a clear contract for how to read and use it (Dimension B).

---

## 2. Micro-level: how to design and feed individual STARs

Goal: make each STAR maximally useful and unambiguous to the model with minimal per-job overhead.

- Normalize S/T/A/R semantics explicitly
  - Keep S/T/A/R fields short and atomic: 1–3 sentences each, no essays.
  - Use BACKGROUND_CONTEXT for nuance (story, org dynamics), but treat S/T/A/R as the “API surface” the model must consume.
  - For each STAR, write the RESULT and METRICS as “business lever + number” (e.g. “reduced cloud infra spend by 27%” not “saved a lot of money”).
- Use CONDENSED_VERSION as the primary LLM input
  - Treat CONDENSED_VERSION as: “[Role] at [Company]: [S/T compressed] → [A compressed] → [R with 1–2 metrics].”
  - For generation tasks, feed mostly CONDENSED_VERSION + METRICS + 2–3 key HARD_SKILLS, and only pull in BACKGROUND_CONTEXT when you need narrative richness (e.g. long-form dossier).
  - This reduces cognitive load: the LLM doesn’t have to “re-discover” the story from raw S/T/A/R fields.
- Make downstream intent explicit per STAR
  - Add (even if just conceptually at first) “intended uses” as tags, e.g. `best_for: ["team_leadership", "platform_cost_optimization", "greenfield_delivery"]`.
  - This helps you pick obvious matches fast without recomputing similarity every time.
- Introduce “pain-points” fields at the STAR level
  - Add 1–3 explicit `PAIN_POINTS_ADDRESSSED` per STAR, written in the language of hiring managers, e.g.:
    - “High deployment risk due to manual releases”
    - “Slow feature delivery due to monolithic architecture”
  - This is the bridge between Layer 2 (pain-point miner) and the STAR library: you can select STARs by overlap between job pains and STAR pains instead of asking the LLM to infer everything from scratch.
- Give the LLM a strict reading contract
  - In system prompts, say things like:
    - “You are given a set of STAR records. Each is a complete story about one achievement. You MUST:
       1. Only claim achievements explicitly present in the STAR fields,
       2. Only use metrics from METRICS/RESULTS,
       3. Treat CONDENSED_VERSION as the primary summary and use BACKGROUND_CONTEXT only for nuance.”
  - Add explicit instructions for each task:
    - Outreach: “Select 1–2 STARs whose PAIN_POINTS_ADDRESSSED best match the job’s top 2 pains.”
    - Cover letter: “Weave 2–3 STARs into the body; name the company/role and reuse the real metrics.”
    - CV: “Use STARs as one bullet each. Do not invent new companies, roles, or metrics.”
- Limit how many STARs you send per call
  - If one experience has 20–30 STARs, don’t dump them all into one LLM call for outreach.
  - Instead, do a pre-selection step:
    - Use rules/embeddings/graph (see macro section) to get top 5–8 STARs per job.
    - Pass those to the LLM with CONDENSED_VERSION + METRICS + HARD_SKILLS + PAIN_POINTS_ADDRESSSED.
  - For the CV, you can run a separate selection for “core experience bullets” vs “extra achievements.”

---

## 3. Macro-level: STARs as a knowledge graph

Goal: treat your STAR library as a small, personal knowledge graph that your layers query, not as a flat JSON list.

- Model STARs as nodes connected to multiple dimensions
  - Nodes: STAR, Company, Role, DomainArea, HardSkill, SoftSkill, PainPoint, Metric, OutcomeType (e.g. cost, speed, risk, quality).
  - Edges:
    - STAR → Company, STAR → Role, STAR → DomainArea(s),
    - STAR → HardSkill(s), STAR → SoftSkill(s),
    - STAR → PainPoint(s) (your `PAIN_POINTS_ADDRESSSED`),
    - STAR → Metric(s) (each metric as a structured object),
    - STAR → OutcomeType(s) (e.g. `cost_reduction`, `risk_reduction`, `velocity_increase`).
  - This can live in Mongo as documents, not a fancy graph DB: one STAR doc with arrays of IDs / enums is enough to behave like a knowledge graph.
- Connect the graph to your pipeline layers
  - Layer 2 (Pain-Point Miner): map mined pains (and their categories) to graph PainPoint nodes and fetch linked STARs.
  - Layer 4 (Opportunity Mapper): when you map job opportunities and gaps, retrieve STARs that:
    - match the opportunity’s domain/skills, and
    - cover missing gaps you want to highlight as “transferable evidence.”
  - Layer 6 (CV & Cover Letter): use the graph to:
    - pick diversified STARs (different companies/skills) for variety,
    - prioritize those hitting the same pain category from different angles.
- Use a hybrid ranking strategy (rules + embeddings)
  - For each job/pain, STAR score = weighted sum of:
    - Exact/enum matches: company/industry, domain, HARD_SKILLS.
    - PainPoint overlap: number/importance of shared `PAIN_POINTS_ADDRESSSED`.
    - Embedding similarity: between job description/pains and CONDENSED_VERSION/ATS_KEYWORDS.
    - Outcome mix: prefer STARs that demonstrate the outcome type the job cares most about (e.g. “cost discipline” vs “innovation”).
  - This keeps things robust: rules give you stability, embeddings give you fuzziness.
- Design the graph to be incrementally extensible
  - When you add a new STAR:
    - Enforce a small checklist: all major fields filled, `PAIN_POINTS_ADDRESSSED` tagged, HARD/SOFT skills listed, METRICS present.
    - Precompute and store embeddings for CONDENSED_VERSION and perhaps METRICS/RESULTS text.
    - Auto-wire STAR to relevant nodes (skills, domains, pains) using a small classifier or rule-based tags.
  - As the library grows, the graph becomes richer without changing the pipeline code: selection just keeps working better.
- Separate “canonical STAR data” from “job-specific views”
  - Canonical STAR = what you described in `star-selection-requirements.md`.
  - Job-specific view = “STAR as used for job X,” e.g.:
    - which pains it supports,
    - which parts were used in which layer (outreach vs cover letter vs CV),
    - how it performed (did that job lead to interviews?).
  - Store those job-specific annotations in `pipeline_runs` or a `star_usage` collection; over time, you can:
    - boost STARs that historically correlate with interviews,
    - learn which skills and outcome types are most impactful in different industries.
- Macro prompting: let the LLM see the structure, not the raw dump
  - Rather than dumping 5 full STAR JSONs, consider passing a summary table derived from the graph, e.g.:
    - ID, Company, Role, PainPointsAddressed, HardSkills, KeyMetrics, CondensedVersion.
  - Then, in the same prompt, give the LLM instructions like:
    - “Pick 2 STARs that best address pains A and B and are not from the same company. Use their CondensedVersion and metrics exactly.”

---

## 4. How to use this “to the best of your ability”

- When you write or edit STARs:
  - Think: “If I knew nothing about my background and only saw this STAR doc, could I precisely reconstruct the CV bullet and explain why it matters to a hiring manager?”
- When you hook STARs into the system:
  - Think: “What small, structured signals can I compute once (pains, skills, outcome types, embeddings) so that the LLM only has to do composition (writing) rather than discovery (figuring out what the story even is)?”
- Over time:
  - Treat STARs as a living asset: every new role, project, or interview should lead to new STARs or better tags/metrics on existing ones, and your knowledge graph + selection logic should automatically make everything downstream (outreach, CV, letters) stronger without changing prompts.

