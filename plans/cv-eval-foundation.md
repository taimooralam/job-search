# CV Eval Foundation: Market Composites, Candidate-Evidence + Master-CV Representation Baseline, and Category Rubrics

## Mission

You are building the evaluation foundation for Taimoor Alam's CV-generation pipeline.

This work must **not** stop at "analyzing job descriptions." It must produce an end-to-end foundation that answers four questions:

1. What does the real market consistently ask for in each target category?
2. How well does the candidate's **evidence base** match each category, and how well does the current **master CV representation** surface that evidence, **before any CV generation happens**?
3. What does a **top-third CV** look like for each category, in evidence-bounded terms?
4. How should future **generated CVs** be scored against both:
   - the **specific job description**, and
   - the **category-level market rubric**?

The outputs from this run will become the ground truth for measuring whether CV quality is improving.

---

## Execution Status (as of 2026-04-17)

| Step | Status | Artifacts / Notes |
|---|---|---|
| Step 0 — Methodology | ✅ Done | Applied throughout Steps 1-4 |
| Step 1 — MongoDB extraction | ✅ Done | `data/eval/raw/<category>/jobs_all.json` + `jd_texts/` for 15 categories |
| Step 2 — Category assignment | ✅ Done | `data/eval/raw/<category>/jobs_all.json` (per-category files = primary assignment) |
| Step 3 — Per-job normalized analysis | ✅ Done | `data/eval/normalized/<category>/normalized_jobs.json` + deep analyses |
| Step 4 — Category market composite | ✅ Done | `data/eval/composites/<category>.{json,md}` |
| Step 5 — Top-third CV blueprint | ✅ Done (12 categories) | `data/eval/blueprints/<category>_blueprint.{json,md}` + `index.md` |
| Step 6 — Baseline scoring | ✅ Done (12 categories) | `data/eval/baselines/<category>_baseline.{json,md}` + `step6_report.md`. Regenerated after master-CV Phase 1 edits. |
| Step 7 — Category eval rubrics | ✅ Done (12 categories) | `data/eval/rubrics/<category>_rubric.{json,md}` + `index.md`, `README.md` |
| Step 8 — Scorecard template | ✅ Done | `data/eval/rubrics/scorecard_template.json` |
| Step 8b — Stage eval rubrics | ⏸ Deferred | `data/eval/rubrics/stage_scorecard_template.json` (placeholder only); deferred per Step 9 decision record. |
| Step 9 — Rubric-bound CV scoring | ✅ Done (12/12 coverage) | `scripts/eval_step9_score_cv_outputs.py` + `scripts/eval_step9v2_run_batch.py`. See `data/eval/scorecards/comparison_{v1_v2,expansion_batch_v1,coverage_batch_v1}.md`. Final aggregate: 9 GOOD_MATCH, 3 NEEDS_WORK (2 real_fit_gap, 1 generation_gap), 0 WEAK. |
| Step 10 — Calibration from existing reviews | 🔲 Not started | — |
| Step 11 — Holdout validation | 🔲 Not started | Per-category holdout set and edge-case checks still to do. |

**Storage inventory (§Step 9 spec'd):**
- `data/eval/raw/`, `data/eval/normalized/`, `data/eval/composites/`, `data/eval/blueprints/`, `data/eval/baselines/`, `data/eval/rubrics/`, `data/eval/scorecards/` all populated.
- `data/eval/generated_cvs/step9_{v2_<ts>,expansion_<ts>,coverage_<ts>}/` hold immutable CV snapshots + logs + meta for the 3 Step 9 batches.
- `data/eval/scorecards_archive/step9_v1_anchor/` preserves the v1 legacy-CV scorecards.

**Open watch-item (from Step 9 coverage batch):** single `generation_gap` on `head_of_ai_eea` (skills-without-experience-evidence pattern) — isolated, not a cluster. Next planned phase: within-category variance sampling (2-3 additional JDs across 3-4 key categories) to confirm the pattern does not recur before Step 10/11.

---

## Candidate Ground Truth

The candidate is **Taimoor Alam**.

Use this as the candidate anchor when performing gap analysis and pre-generation fit scoring:

- Current anchor identity: **Engineering Leader / Software Architect**
- Experience: **11 years**
- Current role: **Technical Lead at Seven.One Entertainment Group (ProSiebenSat.1), Munich**
- Strongest AI evidence:
  - Built **Commander-4**, an enterprise AI workflow platform
  - **42 plugins**
  - **2,000 users**
  - Strong evidence in LLM platform engineering, RAG, hybrid retrieval, evaluation, guardrails, semantic caching, observability, governance, and engineering leadership
- Primary target role families:
  - **AI Architect**
  - **Head of AI / AI Leadership**
- Secondary adjacency:
  - Staff/Principal AI Engineer
  - Tech Lead AI
  - AI Engineering Manager
  - AI Solutions Architect
- Tertiary adjacency:
  - Head of Software / Engineering

### Candidate evidence hierarchy

Do **not** assume `data/master-cv/*` is the complete source of truth.
It is the current **curated evidence store**: useful, structured, and auditable, but potentially incomplete.

Treat candidate evidence as a 3-layer hierarchy:

1. **Upstream raw evidence**
   - authoritative but messy source material that may contain valid evidence not yet curated
   - examples:
     - `docs/current/`
     - `docs/archive/`
     - vetted project notes, achievement reviews, interview prep notes, and other candidate-authored material with clear provenance
2. **Curated evidence store**
   - normalized evidence already promoted into pipeline-friendly files
   - current examples:
     - `data/master-cv/roles/*.md`
     - `data/master-cv/projects/commander4.md`
     - `data/master-cv/projects/commander4_skills.json`
     - `data/master-cv/projects/lantern.md`
     - `data/master-cv/projects/lantern_skills.json`
     - `data/master-cv/role_skills_taxonomy.json`
     - `data/master-cv/role_metadata.json`
3. **Representation layer**
   - the current master CV and any generated CV outputs that select and frame evidence from the curated store

### Candidate evidence rules

- `data/master-cv/*` is the working **curated evidence base**, not a claim that all real evidence has already been captured
- Treat `*_skills.json` files as structured evidence maps:
  - `verified_*` = direct evidence
  - `post_checklist_*` = supporting/secondary evidence
  - `not_yet_built` = explicit **do-not-claim** items
- Upstream raw evidence may be used to identify likely missing signals, but it must be tagged as one of:
  - `curated_supported` = already promoted into `data/master-cv/*`
  - `upstream_supported_pending_curation` = supported in vetted upstream material, but not yet normalized into `data/master-cv/*`
  - `unsupported` = not safely evidenced
- No signal should be treated as fully reusable pipeline evidence until it is promoted into the curated evidence store with provenance
- The candidate must be evaluated with an **evidence-first** lens:
  - Do **not** assume deep ML research, fine-tuning, RLHF, or PhD-style model-training depth unless explicitly supported
  - Do **not** penalize the candidate merely for lacking the exact title "Head of AI" if equivalent scope is strongly evidenced
- Every claim in gap analysis or scoring must cite exact local file references with **1-based line numbers**

---

## Non-Negotiables

Do **not** do any of the following:

- Do **not** classify jobs using title regex + location alone if stronger signals exist
- Do **not** limit quantitative analysis to only the top 20 jobs
- Do **not** double-count the same job across multiple primary categories
- Do **not** infer tools, skills, or requirements that are absent from JD text
- Do **not** turn the composite into a generic buzzword dump
- Do **not** use existing CV-review verdicts as ground truth for market requirements
- Do **not** create an "ideal CV" that requires unsupported claims from the candidate

This must be an **evidence-based, auditable, reusable scoring foundation**.

---

## Step 0: Methodology, Provenance, and Evidence Discipline

Before analysis, define and record:

- Analysis date
- MongoDB query date range, if any
- Inclusion rules
- Exclusion rules
- Deduplication rules
- Category assignment rules
- Signal weighting rules
- Confidence thresholds
- Output schema version

### Evidence tagging

Every extracted requirement or signal must carry one of these tags:

- `explicit` = directly stated in the JD
- `derived` = tightly derived from explicit JD wording or structured JD extraction
- `not_specified` = not present

### Counting rules

- **Frequency tables must be based on explicit JD evidence**
- `derived` signals may appear in narrative synthesis, but must be labeled as synthesized
- If something is not mentioned, mark it `not_specified`
- Report both:
  - **raw count**: `N / M`
  - **raw %**
- Also report **weighted %** when signal weighting materially changes the picture

### Deduplication rules

Deduplicate likely duplicate postings before analysis using any available combination of:

- normalized title
- normalized company
- normalized location
- job URL
- JD similarity
- identical or near-identical JD text

Keep the best-quality record and log all excluded duplicates.

---

## Step 1: Data Extraction from MongoDB

Use MongoDB connection from `.env` via `MONGODB_URI`.

Query `jobs.level-2` and extract **all unique eligible jobs** across the following signal tiers.

### Signal tiers and weights

**Tier A — strongest signal**  
Applied and received positive response / callback / interview:
```javascript
{status: "applied", $or: [{response_received: true}, {interview_invited: true}, {callback: true}]}
```
Weight: `1.00`

**Tier B — strong signal**  
Applied and scored strongly:
```javascript
{status: "applied", score: {$gte: 60}}
```
Weight: `0.85`

**Tier C — good market signal**  
AI job, scored reasonably, JD present:
```javascript
{is_ai_job: true, score: {$gte: 50}, job_description: {$exists: true, $ne: null}}
```
Weight: `0.65`

**Tier D — baseline market signal**  
All scored AI jobs with JD text:
```javascript
{is_ai_job: true, score: {$exists: true, $ne: null}, job_description: {$exists: true, $ne: null}}
```
Weight: `0.40`

### Optional recency adjustment

If reliable date fields exist, apply a mild recency multiplier and record it:

- within 12 months: `1.00`
- 12-24 months: `0.90`
- older than 24 months: `0.80`

Compute:

`effective_weight = signal_weight * recency_multiplier`

### Fields to extract per job

Extract all available:

- `_id`, `title`, `company`, `location`
- `job_description`, `job_criteria`
- `score`, `tier`, `score_breakdown`
- `status`, `is_ai_job`, `ai_categories`
- `extracted_jd`, `cv_review`
- `applied_at`, `response_received`, `interview_invited`, `callback`
- `fit_score`
- any job URL / source metadata if present

Also record an `extraction_status`:

- `eligible`
- `excluded_duplicate`
- `excluded_missing_jd`
- `excluded_low_quality_jd`
- `excluded_other`

Store all exclusions with reasons.

---

## Step 2: Category Assignment

Classify each job into **exactly one primary category** and optionally one or more `secondary_categories`.

Primary category is used for counts, composites, and rubrics. Secondary categories are for overlap analysis only.

### Target categories

| # | Category | Title Pattern | Location |
|---|----------|--------------|----------|
| 1 | Head of AI — KSA | `(head\|director\|vp).*ai` | Saudi Arabia, Riyadh, Jeddah, Dammam, Khobar, Dhahran, NEOM |
| 2 | Head of AI — UAE | `(head\|director\|vp).*ai` | UAE, Dubai, Abu Dhabi, Sharjah, Al Ain |
| 3 | Head of AI — EEA | `(head\|director\|vp).*ai` | EEA countries only |
| 4 | Head of AI — Global/Remote | `(head\|director\|vp).*ai` | Remote, global, anywhere, worldwide |
| 5 | Head of Software/Engineering — Pakistan | `(head\|director\|vp).*(software\|engineering\|technology)` | Pakistan, Karachi, Lahore, Islamabad |
| 6 | Staff AI Engineer — EEA | `(staff\|principal).*(ai\|genai\|llm\|ml)` | EEA |
| 7 | Staff AI Engineer — Global/Remote | `(staff\|principal).*(ai\|genai\|llm\|ml)` | Remote/global |
| 8 | Tech Lead AI — Pakistan | `(lead\|tech.?lead).*(ai\|genai\|llm\|ml)` | Pakistan cities |
| 9 | Tech Lead AI — EEA | `(lead\|tech.?lead).*(ai\|genai\|llm\|ml)` | EEA |
| 10 | AI Architect — EEA | `(ai\|genai\|llm\|ml).*(architect)` | EEA |
| 11 | AI Architect — Global/Remote | `(ai\|genai\|llm\|ml).*(architect)` | Remote/global |
| 12 | AI Architect — KSA/UAE | `(ai\|genai\|llm\|ml).*(architect)` | KSA + UAE |
| 13 | AI Engineering Manager — EEA | `(engineering.?manager\|manager).*(ai\|ml\|genai)` | EEA |
| 14 | Senior AI Engineer — EEA | `senior.*(ai\|genai\|llm\|ml).*(engineer)` | EEA |
| 15 | AI Solutions Architect — Global | `(ai\|genai).*(solutions.?architect)` | Any |

### Region normalization rules

- `EEA` = EU27 + Iceland + Liechtenstein + Norway
- Do **not** silently include UK or Switzerland in EEA
- Remote/global must be explicitly remote/global or clearly not region-bound
- Normalize common abbreviations and variants: `KSA`, `UAE`, `EMEA remote`, etc.

### Classification priority

Use signals in this order:

1. `ai_categories` if high quality
2. `extracted_jd.role_category`, `seniority_level`, and JD content
3. title pattern
4. JD leadership / architecture / IC signals
5. normalized location

### Classification metadata

Store for every job:

- `primary_category`
- `secondary_categories`
- `macro_family`: `ai_leadership` | `ai_architect` | `ai_engineering_adjacent` | `leadership_adjacent`
- `classification_confidence`: `high` | `medium` | `low`
- `classification_rationale`

### Priority tiers for downstream recommendations

- `primary_target`: categories 1, 2, 3, 4, 10, 11, 12, 15
- `secondary_target`: categories 6, 7, 9, 13, 14
- `tertiary_target`: categories 5, 8

---

## Step 3: Per-Job Normalized Analysis

### 3a. Full-corpus normalized extraction

For **every eligible job** in every category, create a normalized structured record.

Use existing `extracted_jd` as a bootstrap if present, but verify against raw JD text. If `extracted_jd` conflicts with the raw JD, raw JD wins and the conflict must be logged.

Extract and normalize:

- title and title family, seniority
- role scope: IC / player-coach / manager / director / executive
- management expectations: direct reports, hiring, performance management, org building, budget/P&L
- architecture scope: platform design, greenfield vs optimization, scale signals, latency/reliability/throughput
- must-have hard skills, nice-to-have hard skills
- programming languages
- cloud/platform stack, infrastructure/DevOps
- AI/ML stack, LLM-specific capabilities
- evaluation/quality signals, governance/compliance/risk
- observability/ops, data/vector/search stack
- domain/industry, company stage, collaboration model
- stakeholder level, success metrics, implied pain points
- disqualifiers: research-heavy, publications/PhD, native language, security clearance, relocation, domain-specific

### 3b. Deep-analysis exemplar set (up to 20 per category)

Selection: Tier A first, then Tier B, then highest effective_weight, then highest score, then best JD quality.

#### Deep-analysis dimensions per exemplar

**Technical:** Programming languages, AI/ML frameworks, cloud platforms, infrastructure, data/vector/search, LLM-specific techniques, observability

**AI Architecture:** System design scope, RAG depth, agent/orchestration, evaluation/quality, governance/guardrails, cost optimization, production LLM ops

**Leadership & Scope:** Seniority, people leadership, mentorship, stakeholder management, strategic scope, transformation/org-build

**Market & Culture:** Communication, collaboration model, industry domain, company stage, risk appetite

**CV-Relevant Translation Layer:** What would a strong CV prove? What evidence types matter most? Which claims would be unsafe? Which candidate experiences map best?

---

## Step 4: Category Market Composite

For each of the 15 categories, synthesize into a **Category Market Composite** containing:

- Category metadata (macro family, target priority, confidence, sample sizes, tier mix)
- Signal strength (applied count, response count, score stats)
- Title variants
- Market requirement stack (must-haves, common, differentiators, nice-to-haves, disqualifiers) with raw % and weighted %
- Required hard skills, soft skills, programming languages (frequency ranked)
- AI/ML and LLM profile (RAG, agents, fine-tuning, evaluation, guardrails, prompt engineering, vector, routing, observability)
- Architecture expectations (competency mix, greenfield vs optimization, scale, cloud, ops)
- Leadership profile (team size, hiring, mentorship, stakeholder, budget, org-building)
- Pain points and hiring motives
- Identity statement (2-3 sentences, grounded in category evidence)
- Employer proof expectations
- Candidate gap analysis vs evidence base and current master-CV representation (direct matches, adjacent, true gaps, representation gaps, unsafe claims, file+line refs)
- Category fit outlook (strong/good/stretch/low-priority)

### Frequency bands

- `must_have` >= 60% weighted
- `common` = 35-59%
- `differentiator` = 15-34% but strategically important
- `rare` < 15%

---

## Step 5: Top-Third CV Blueprint Per Category

Each composite includes a **Top-Third CV Blueprint** (candidate-safe, evidence-first):

- **Headline:** pattern, evidence-first framing, title-family guidance
- **Tagline/Profile:** angle, safe positioning, what to foreground/avoid
- **Core Competencies:** 6-10 themes grouped into coherent sections
- **Key Achievement Mix:** 4-6 archetypes (architecture, reliability, evaluation, governance, org building, etc.)
- **Role Weighting:** which roles/projects carry most weight, what to compress
- **Language and Tone:** executive vs architect vs hands-on vs player-coach
- **Unsafe or Weak Framing:** claims to avoid, buzzword patterns, title/research inflation

---

## Step 6: Pre-Generation Candidate-Evidence and Master-CV Representation Baseline

Implementation contract: [`plans/eval-step6-implementation-contract.md`](eval-step6-implementation-contract.md)

Do **not** treat the current master CV as the source of truth.
Do **not** treat the current curated evidence store as complete.

Step 6 must evaluate three separate things against each category blueprint:

1. **Candidate evidence coverage**
   - How much category-relevant evidence is already present in the curated evidence store?
2. **Evidence curation completeness**
   - How much category-relevant evidence likely exists in vetted upstream sources but has not yet been promoted into the curated evidence store?
3. **Current master-CV representation quality**
   - How well does the current master CV surface, prioritize, and frame that evidence?

### Step 6 scoring outputs

Produce both a combined fit score and split sub-scores:

- `Candidate Evidence Coverage` — 30%
- `Evidence Curation Completeness` — 15%
- `Master CV Representation Quality` — 25%
- `AI / Architecture Fit` — 15%
- `Leadership / Scope Fit` — 10%
- `Impact Proof Strength` — 5%

Plus modifiers: domain_adjacency, location_market_fit, hard_disqualifiers, unsafe_claims_risk

### Required Step 6 distinctions

For every category, classify gaps into exactly one of these buckets:

- `evidence_gap`
  - the candidate does not appear to have sufficient evidence in curated or vetted upstream sources
- `curation_gap`
  - the candidate likely has valid evidence in vetted upstream material, but it has not yet been promoted into `data/master-cv/*`
- `representation_gap`
  - the curated evidence exists, but the current master CV does not surface it clearly
- `unsafe_claim_gap`
  - the market rewards the signal, but it would be unsafe to claim from existing evidence

### Required outputs per category

- combined fit score
- readiness tier (`STRONG >= 8.5`, `GOOD 7.0-8.49`, `STRETCH 5.5-6.99`, `LOW < 5.5`)
- `candidate_evidence_coverage_score`
- `evidence_curation_completeness_score`
- `master_cv_representation_score`
- top evidence refs with exact file+line citations
- strongest supported safe claims
- biggest `curation_gaps`
- biggest `representation_gaps`
- biggest `true_evidence_gaps`
- biggest unsafe claims / overclaim risks
- recommended master-CV upgrade actions

### Why this split matters

This step is not just measuring whether the current master CV reads well.
It is producing the baseline needed to improve the master CV safely:

- fix `curation_gaps` by promoting vetted upstream evidence into `data/master-cv/*` with provenance
- fix `representation_gaps` through better framing, ordering, and bullet selection
- do **not** fabricate `true_evidence_gaps`
- rerun Step 6 after master-CV changes to verify that representation improved without inflating unsupported claims

---

## Step 7: Reusable CV Evaluation Rubric

For each category, create a **Category Eval Rubric** with two layers:

- **Layer A — Category Core:** what a strong CV consistently needs across many JDs
- **Layer B — Job-Specific Overlay:** company/domain/stack/region specifics

### 5 scored dimensions (matching existing grader)

- `ATS Optimization` — 20%
- `Impact & Clarity` — 25%
- `JD Alignment` — 25%
- `Executive Presence` — 15% (interpreted by category: leadership vs architectural authority)
- `Anti-Hallucination` — 15%

Each dimension includes: what 9-10 / 7-8 / 5-6 / <=4 looks like, category-core criteria, job-specific overlay criteria.

Plus gates: must-have coverage, unsafe-claim, persona-fit.

Verdict thresholds: STRONG_MATCH >= 8.5, GOOD_MATCH 7.0-8.49, NEEDS_WORK 5.5-6.99, WEAK_MATCH < 5.5

---

## Step 8: Scorecard Template

Reusable JSON template for longitudinal tracking:

```json
{
  "rubric_version": "YYYY-MM-DD",
  "category_id": "...",
  "job_id": "...",
  "dimension_scores": { "ats_optimization": 0, "impact_clarity": 0, "jd_alignment": 0, "executive_presence": 0, "anti_hallucination": 0 },
  "gates": { "must_have_coverage_passed": true, "unsafe_claim_gate_passed": true, "persona_fit_passed": true },
  "overall_score": 0,
  "verdict": "STRONG_MATCH|GOOD_MATCH|NEEDS_WORK|WEAK_MATCH",
  "top_strengths": [], "top_failures": [], "unsupported_claims": [], "missing_must_haves": []
}
```

---

## Step 8b: Intermediate Stage Eval Rubrics

The final CV eval (Steps 7-8) measures end-to-end output quality. But when a CV scores poorly, you need to diagnose **which stage** failed. Each pipeline stage has its own quality dimensions that should be independently measurable.

### Stage-Level Eval Definitions

| Stage | Input | Output | Eval Dimensions |
|-------|-------|--------|----------------|
| **Pain Point Extraction** (Layer 2) | Raw JD text | 4-8 pain points + strategic needs | Coverage (% of JD themes captured), Specificity (actionable vs generic), Grounding (traceable to JD text), Prioritization (ranked by hiring urgency) |
| **JD Extraction** (Layer 1.4) | Raw JD text | role_category, seniority, top_keywords, competency_weights | Accuracy (role_category correct?), Completeness (keywords capture JD breadth?), Seniority detection (IC vs manager vs director correct?) |
| **Role Bullet Selection** (Layer 6 Phase 2) | Pain points + master CV achievements | 4-6 bullets per role with variants | Pain point coverage (each pain point addressed?), Achievement relevance (bullets match JD?), ARIS format compliance, Metric grounding (numbers from source), Keyword integration (JD terms in bullets) |
| **Header/Tagline Generation** (Layer 6 Phase 5) | Stitched CV + JD + persona | Headline, tagline, key achievements, core competencies | Headline accuracy (JD title + credibility anchor), Tagline evidence-first (verified identity leads), Achievement diversity (across categories), Competency coverage (ATS keyword match rate) |
| **Core Competency Selection** (CoreCompetencyGeneratorV2) | Skill whitelist + taxonomy + JD | 4 sections × 4-10 skills | Section coverage (all 4 sections populated?), JD keyword match (% of JD skills surfaced), Whitelist compliance (all from verified list), ATS density (enough for ATS survival) |
| **Grading + Improvement** (Layer 6 Phase 6) | Generated CV + JD | 5-dimension scores + improvements | Score accuracy (does the score reflect actual quality?), Improvement effectiveness (did improvements actually help?), Hallucination detection (caught unsupported claims?) |
| **Fit Analysis** (Layer 4) | Pain points + candidate profile | fit_score 0-100 + rationale | Score calibration (does score predict reviewer verdict?), Rationale quality (specific vs generic), Gap identification (true gaps flagged?) |

### How to Evaluate Each Stage

For each stage, use the category composites (Step 4) as ground truth:

1. **Run pipeline on 3 representative jobs per category** with intermediate state capture enabled
2. **Extract each stage's output** from the pipeline state
3. **Score the stage output** against the category composite's expectations for that dimension
4. **Compare** stage-level scores to final CV score — identify which stages are the bottleneck

### Stage Scorecard Template

```json
{
  "job_id": "...",
  "category_id": "...",
  "stage": "pain_point_extraction|jd_extraction|role_bullet_selection|header_generation|competency_selection|grading|fit_analysis",
  "stage_scores": {
    "coverage": 0,
    "specificity": 0,
    "grounding": 0,
    "format_compliance": 0
  },
  "stage_verdict": "strong|adequate|weak|failed",
  "bottleneck_contribution": "float — how much this stage drags down the final score",
  "specific_failures": [],
  "improvement_suggestions": []
}
```

### Diagnostic Query

After running evals, answer: **"For category X, which pipeline stage is the primary bottleneck?"**

If pain points are weak → fix Layer 2 prompts.
If bullets are irrelevant → fix variant selection weights.
If header is AI-first → fix tagline validator.
If competencies are thin → fix taxonomy/whitelist.
If grading is wrong → fix rubric calibration.

This turns the eval from "the CV is bad" into "the CV is bad because Stage Y produced Z."

---

## Step 9: Store Results

```
data/eval/
├── methodology.md
├── queries.json
├── exclusions.json
├── category_assignment_log.json
├── raw/[category]/          (jobs_all.json, jobs_deep_sample.json, jd_texts/)
├── normalized/[category]/   (normalized_jobs.json, deep_analysis.json, evidence_spans.json)
├── composites/              ([category].md, [category].json, summary.md, cross_category_matrix.json)
├── blueprints/              ([category]_top_third.md, [category]_top_third.json)
├── baselines/               (candidate_evidence_representation_baseline.md, .json, evidence_map.json)
├── rubrics/                 ([category]_rubric.md, .json, scorecard_template.json)
├── calibration/             (existing_cv_review_summary.md, .json)
└── validation/              (holdout_checks.md, random_spot_checks.md, validation_summary.json)
```

---

## Step 10: Calibration Using Existing CV Reviews

Aggregate `cv_review` data for calibration only (not ground truth). Per category: verdict distribution, recurring failures, hallucination patterns, ATS failures. Answer: are weak outcomes from source-evidence gaps or poor generation choices?

---

## Step 11: Validation

1. Reserve holdout set per category (20% or at least 1 random + 1 edge case)
2. Compare holdout JD against composite
3. Validate Tier A/B influence on weighted outputs
4. Verify master-CV gap analysis cites real evidence with line numbers
5. Validate `not_yet_built` items never rewarded
6. Check blueprint recommendations are candidate-safe
7. Flag categories with <8 jobs (medium/low confidence) or <5 (low/exploratory)

---

## Constraints

- All analysis grounded in actual JD text or labeled structured extraction
- Raw frequency counts exact, weighted frequencies reproducible
- Absent dimensions marked `not_specified`
- All master-CV references with exact file paths and 1-based line numbers
- Preserve raw data, normalized data, and reasoning artifacts
- Do not hallucinate candidate capabilities or reward unsupported claims
- Final output must be usable as scoring foundation, not just a research report
