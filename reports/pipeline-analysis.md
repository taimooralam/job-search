# Complete E2E Pipeline Analysis: UI to MongoDB

## Executive Summary

This document provides a comprehensive end-to-end analysis of the job intelligence pipeline, tracing every button click from the UI through Vercel/Runner endpoints to MongoDB storage. It identifies prompt strategies, schema fields, field dependencies, technical debt, and value assessment.

---

## 1. UI Button → Endpoint Mapping

### Main Jobs Page (index.html)

| Button | JS Handler | Flask Route | Runner Endpoint | Operation |
|--------|-----------|-------------|-----------------|-----------|
| **Process (Auto)** | `processSelectedJobs()` | `POST /api/runner/jobs/run-bulk` | `POST /jobs/run-bulk` | Full pipeline (all layers) |
| **Tier Dropdown** (Auto/Gold/Silver/Bronze) | `setBulkProcessingTier(tier)` | N/A (state only) | N/A | Sets `processing_tier` |
| **Move to Batch** | `moveSelectedToBatch()` | `POST /api/jobs/move-to-batch` | N/A (MongoDB only) | Update status to "under processing" |

### Batch Processing Page (batch_processing.html)

| Button | JS Handler | Flask Route | Runner Endpoint | Layers Executed |
|--------|-----------|-------------|-----------------|-----------------|
| **Full Extraction** | `executeBatchOperation('full-extraction')` | `POST /api/runner/jobs/full-extraction/bulk` | `POST /api/jobs/full-extraction/bulk` | 1.4 → 2 → 4 |
| **Extract JD** | `executeBatchOperation('process-jd')` | `POST /api/runner/jobs/full-extraction/bulk` | Same as above | 1.4 → 2 → 4 |
| **Research Company** | `executeBatchOperation('research-company')` | `POST /api/runner/jobs/research-company/bulk` | `POST /api/jobs/research-company/bulk` | 3 → 3.5 → 5 |
| **Generate CV** | `executeBatchOperation('generate-cv')` | `POST /api/runner/jobs/generate-cv/bulk` | `POST /api/jobs/generate-cv/bulk` | 6v2 |
| **All Ops** | `executeBatchOperation('all-ops')` | `POST /api/runner/jobs/all-ops/bulk` | `POST /api/jobs/all-ops/bulk` | (1.4→2→4) ‖ (3→3.5→5) |
| **Tier Dropdown** | `setBatchTier(tier)` | N/A | N/A | Sets tier: A/B/C |

### Job Detail Page

| Button | JS Handler | Flask Route | Runner Endpoint | Layers |
|--------|-----------|-------------|-----------------|--------|
| **Run All Operations** | Via dropdown | `POST /api/runner/jobs/{id}/all-ops/stream` | `POST /{id}/all-ops/stream` | Parallel: JD + Research |
| **Generate CV** | Via dropdown | `POST /api/runner/operations/{id}/generate-cv/stream` | `POST /{id}/generate-cv` | 6v2 |
| **Tier Selector** (Fast/Balanced/High-Quality) | Dropdown | Passed as `tier` param | Used for model selection | N/A |

---

## 2. Tier System Mapping

### Processing Tier (Batch/Main Page)

| UI Display | Value | Model Selection | Cost Estimate |
|------------|-------|-----------------|---------------|
| **Auto (by score)** | `auto` | Based on fit_score | Variable |
| **Gold (A)** | `A` | claude-opus-4.5 | ~$0.50/job |
| **Silver (B)** | `B` | claude-sonnet | ~$0.05/job |
| **Bronze (C)** | `C` | gpt-4o-mini | ~$0.02/job |

### Execution Tier (Detail Page)

| UI Display | Value | Models Used | Cost |
|------------|-------|-------------|------|
| **Fast** | `fast` | gpt-4o-mini + claude-haiku | ~$0.02 |
| **Balanced** | `balanced` | gpt-4o-mini + claude-sonnet | ~$0.05 |
| **High-Quality** | `quality` | gpt-4o + claude-opus-4.5 | ~$0.50 |

---

## 3. Layer-by-Layer Analysis

### Layer 1.4: JD Extractor

**File:** `src/layer1_4/claude_jd_extractor.py`

**Prompt Summary:**
| Aspect | Description |
|--------|-------------|
| **Persona** | Expert job description analyst |
| **Task** | Classify role into 8 categories, extract competency weights, identify 15 ATS keywords |
| **Output Format** | Structured JSON with validation |
| **Anti-Hallucination** | Only use facts from provided JD |

**Schema Fields (ExtractedJDModel):**

| Field | Type | Description | Downstream Usage |
|-------|------|-------------|------------------|
| `title` | str | Job title | Display, matching |
| `company` | str | Company name | Research trigger |
| `location` | str | Job location | Display |
| `remote_policy` | enum | fully_remote/hybrid/onsite/not_specified | Filtering |
| `role_category` | enum | 8 categories (engineering_manager, staff_principal, etc.) | CV template selection, competency emphasis |
| `seniority_level` | enum | senior/staff/principal/director/vp/c_level | CV tone adjustment |
| `competency_weights` | dict | delivery/process/architecture/leadership (sum=100) | **Critical:** Drives CV bullet emphasis |
| `responsibilities` | List[str] | 5-10 items | Pain point extraction, keyword matching |
| `qualifications` | List[str] | Required quals | Gap detection |
| `nice_to_haves` | List[str] | Optional quals | Secondary keywords |
| `technical_skills` | List[str] | Technologies | ATS keywords |
| `soft_skills` | List[str] | Leadership, comm | Outreach personalization |
| `implied_pain_points` | List[str] | Inferred problems | Layer 2 input |
| `success_metrics` | List[str] | How success measured | Cover letter, outreach |
| `top_keywords` | List[str] | 15 ATS keywords | **Critical:** CV keyword placement |
| `industry_background` | Optional[str] | Domain (AdTech, FinTech) | STAR selection |
| `years_experience_required` | Optional[int] | Years needed | Fit scoring |
| `education_requirements` | Optional[str] | Degree requirements | Gap analysis |

**MongoDB Storage:** Stored as `extracted_jd` subdocument in `level-2` collection.

---

### Layer 2: Pain Point Miner

**File:** `src/layer2/pain_point_miner.py`

**Prompt Summary:**
| Aspect | Description |
|--------|-------------|
| **Persona** | Revenue-Operations Diagnostician (15 years analyzing hiring patterns) |
| **Task** | Extract 4 dimensions: pain_points, strategic_needs, risks_if_unfilled, success_metrics |
| **Chain-of-Thought** | Symptoms vs root causes, WHY NOW trigger, evidence grounding, metric extraction |
| **Domain-Aware** | 8 domains with domain-specific few-shot examples |
| **Confidence Scoring** | high/medium/low based on evidence strength |
| **Anti-Boilerplate** | Rejects "strong communication", "team player", etc. |

**Schema Fields (EnhancedPainPointAnalysis):**

| Field | Type | Constraints | Downstream Usage |
|-------|------|-------------|------------------|
| `pain_points` | List[AnalysisItem] | 2-6 items, text+evidence+confidence | **Critical:** STAR selection, fit scoring, CV bullets |
| `strategic_needs` | List[AnalysisItem] | 2-5 items | Outreach framing, cover letter |
| `risks_if_unfilled` | List[AnalysisItem] | 2-5 items | Urgency messaging |
| `success_metrics` | List[AnalysisItem] | 2-6 items | Achievement alignment |
| `reasoning_summary` | Optional[str] | Brief summary | Debugging |
| `why_now` | Optional[str] | Hiring urgency reason | Outreach hook |

**Annotation Integration:**
- Must-have keywords: +10 boost
- Gap keywords: -5 penalty
- Passion (love_it): +5 boost
- Passion (avoid): -3 penalty
- Identity (core): +3 boost
- Identity (not_me): -4 penalty

**MongoDB Storage:** `pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics` as top-level arrays.

---

### Layer 3: Company & Role Researcher

**Files:** `src/layer3/company_researcher.py`, `src/layer3/role_researcher.py`

**Layer 3.1: Company Researcher**

| Aspect | Description |
|--------|-------------|
| **Data Source** | FireCrawl multi-source scraping (official site, LinkedIn, Crunchbase, news) |
| **Persona** | Business intelligence analyst |
| **Task** | Extract company signals with dates and sources |
| **Caching** | MongoDB 7-day TTL |
| **Anti-Hallucination** | Every signal must have source URL |

**Schema Fields (CompanyResearchOutput):**

| Field | Type | Description | Downstream Usage |
|-------|------|-------------|------------------|
| `summary` | str | 2-3 sentence overview | Outreach personalization |
| `signals` | List[CompanySignal] | 0-10 business events | **Critical:** "Why now" context, interview prep |
| `url` | str | Primary company URL | Verification |
| `company_type` | str | employer/recruitment_agency/unknown | Process routing |

**CompanySignal Schema:**

| Field | Type | Values |
|-------|------|--------|
| `type` | str | funding, acquisition, leadership_change, product_launch, partnership, growth |
| `description` | str | Event description |
| `date` | str | ISO date or "unknown" |
| `source` | str | Source URL |

**Layer 3.5: Role Researcher**

| Field | Type | Description | Downstream Usage |
|-------|------|-------------|------------------|
| `summary` | str | 2-3 sentence role overview | Cover letter |
| `business_impact` | List[str] | 3-5 bullets | Achievement alignment |
| `why_now` | str | 1-2 sentences | **Critical:** Outreach hook, interview |

**MongoDB Storage:** `company_research`, `role_research` as subdocuments.

---

### Layer 4: Opportunity Mapper (Fit Scoring)

**File:** `src/layer4/opportunity_mapper.py`

**Prompt Summary:**
| Aspect | Description |
|--------|-------------|
| **Persona** | Senior executive recruiter (500+ placements) |
| **4-Step Process** | Pain Point Mapping → Gap Analysis → Strategic Alignment → Scoring Decision |
| **Rubric** | 90-100: Exceptional, 80-89: Strong, 70-79: Good, 60-69: Moderate, <60: Weak |
| **Anti-Hallucination** | Every metric must come from STAR records |
| **Annotation Blending** | 70% LLM score + 30% annotation signal |

**Schema Fields:**

| Field | Type | Description | Downstream Usage |
|-------|------|-------------|------------------|
| `fit_score` | int | 0-100 | **Critical:** Tier assignment, prioritization |
| `fit_rationale` | str | 2-3 sentences with STAR citations | Cover letter, interview prep |
| `fit_category` | str | exceptional/strong/good/moderate/weak | UI display, filtering |
| `tier` | str | A (85+), B (70-84), C (50-69), D (<50) | Model selection, priority |

**Annotation Fit Signal Weights:**
- Core strength: +1.0
- Extremely relevant: +0.8
- Relevant: +0.5
- Tangential: +0.2
- Gap: -0.5
- Passion love_it: +0.3
- Passion avoid: -0.2
- Identity core: +0.4
- Identity not_me: -0.3

**MongoDB Storage:** `fit_score`, `fit_rationale`, `fit_category`, `tier` as top-level fields.

---

### Layer 5: People Mapper

**File:** `src/layer5/people_mapper.py`

**Prompt Summary:**
| Aspect | Description |
|--------|-------------|
| **Discovery** | FireCrawl LinkedIn search with Boolean operators |
| **Classification** | 5 contact types with tailored outreach |
| **Character Limits** | Connection: ≤300, InMail: 400-600, Email: 95-205 words |
| **Calendly Integration** | Link included in connection messages |

**Contact Type Strategies:**

| Type | Keywords Focus | Length | Tone |
|------|---------------|--------|------|
| `hiring_manager` | JD match + metrics | Peer-level | Technical credibility |
| `recruiter` | JD keywords + achievements | Efficient | Quantified results |
| `vp_director` | Strategic outcomes | 50-150 words | Business impact |
| `executive` | Industry trends | Extreme brevity | Strategic vision |
| `peer` | Technical depth | Collaborative | Technical rapport |

**Schema Fields (Contact):**

| Field | Type | Description | Usage |
|-------|------|-------------|-------|
| `name` | str | Contact name | Outreach personalization |
| `role` | str | Job title | Classification |
| `linkedin_url` | str | Profile URL | Outreach delivery |
| `contact_type` | str | 5 types | Message tailoring |
| `why_relevant` | str | Relevance explanation | Personalization |
| `recent_signals` | List[str] | Posts, promotions | Conversation hooks |
| `linkedin_connection_message` | str | ≤300 chars | Connection request |
| `linkedin_inmail_subject` | str | 25-30 chars | InMail subject |
| `linkedin_inmail` | str | 400-600 chars | InMail body |
| `email_subject` | str | ≤100 chars | Email subject |
| `email_body` | str | 95-205 words | Email body |
| `reasoning` | str | Strategy explanation | Debugging |
| `already_applied_frame` | str | adding_context/value_add/specific_interest | Follow-up strategy |
| `is_synthetic` | bool | Placeholder flag | Filtering |

**MongoDB Storage:** `primary_contacts`, `secondary_contacts`, `outreach_packages` as arrays.

---

### Layer 6v2: CV Generator

**Files:** `src/layer6_v2/orchestrator.py`, `src/layer6_v2/*.py`

**Pipeline Phases:**
1. **CV Loader** - Load pre-split role files
2. **Role Generator** - Generate 3-5 STAR bullets per role
3. **Role QA** - Hallucination detection + STAR validation
4. **Stitcher** - Deduplication, word budget
5. **Header Generator** - Profile summary
6. **Grader & Improver** - Quality assessment + improvement

**Key Prompt Aspects:**
| Phase | Focus | Anti-Hallucination |
|-------|-------|-------------------|
| Role Generator | STAR format, JD keywords, annotation boost | Only use source text metrics |
| Role QA | Verify every metric has source | Flag invented metrics |
| Header Generator | Achievements-grounded summary | Only cite provided achievements |
| Grader | Multi-dimensional scoring | Evidence-based feedback |

**Schema Fields (GeneratedBullet):**

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | 20-35 words, STAR format |
| `source_text` | str | Original achievement |
| `source_metric` | Optional[str] | Quantified result |
| `jd_keyword_used` | Optional[str] | ATS keyword |
| `pain_point_addressed` | Optional[str] | Pain point match |
| `annotation_boost` | float | Priority boost from annotations |

**MongoDB Storage:** `cv_text`, `cv_path`, `cv_reasoning` as top-level fields.

---

### Layer 7: Dossier Generator

**File:** `src/layer7/dossier_generator.py`

**10 Sections:**
1. Pain → Proof → Plan (Executive summary)
2. Job Summary & Requirements
3. Pain Point Analysis
4. Role Research (Why Now, Business Impact)
5. Selected STAR Achievements
6. Company Overview & Signals
7. Fit Analysis
8. People & Outreach
9. Cover Letter
10. Metadata & Application Form Fields

**MongoDB Storage:** `dossier_path`, `drive_folder_url`, `sheet_row_id`.

---

## 4. Field Dependency Graph

```
INPUT (MongoDB level-2)
    ├── title, company, job_description, job_url
    │
    ▼
LAYER 1.4: JD Extractor
    ├── extracted_jd ──────────────────────────────────────┐
    │   ├── role_category ─────────────────────────────────┼──→ Layer 6 (CV template)
    │   ├── competency_weights ────────────────────────────┼──→ Layer 6 (bullet emphasis)
    │   ├── top_keywords ──────────────────────────────────┼──→ Layer 6 (ATS placement)
    │   ├── implied_pain_points ───────────────────────────┼──→ Layer 2 (enrichment)
    │   └── qualifications ────────────────────────────────┼──→ Layer 4 (gap analysis)
    │                                                      │
    ▼                                                      │
LAYER 2: Pain Point Miner                                  │
    ├── pain_points ───────────────────────────────────────┼──→ Layer 2.5 (STAR selection)
    │                                                      │    Layer 4 (fit scoring)
    │                                                      │    Layer 6 (CV bullets)
    ├── strategic_needs ───────────────────────────────────┼──→ Layer 6 (cover letter)
    ├── risks_if_unfilled ─────────────────────────────────┼──→ Outreach (urgency)
    └── success_metrics ───────────────────────────────────┼──→ Layer 4 (alignment)
                                                           │
    ▼                                                      │
LAYER 3: Company & Role Researcher                         │
    ├── company_research ──────────────────────────────────┤
    │   ├── summary ───────────────────────────────────────┼──→ Outreach personalization
    │   ├── signals ───────────────────────────────────────┼──→ Layer 3.5 (why_now)
    │   └── company_type ──────────────────────────────────┼──→ Process routing
    │                                                      │
    └── role_research                                      │
        ├── business_impact ───────────────────────────────┼──→ CV header
        └── why_now ───────────────────────────────────────┼──→ Outreach hook
                                                           │
    ▼                                                      │
LAYER 4: Opportunity Mapper                                │
    ├── fit_score ─────────────────────────────────────────┼──→ Tier assignment
    ├── fit_category ──────────────────────────────────────┼──→ UI display
    └── tier ──────────────────────────────────────────────┼──→ Model selection
                                                           │
    ▼                                                      │
LAYER 5: People Mapper                                     │
    ├── primary_contacts ──────────────────────────────────┼──→ Layer 7 (dossier)
    └── secondary_contacts ────────────────────────────────┼──→ Layer 7 (dossier)
                                                           │
    ▼                                                      │
LAYER 6: CV Generator                                      │
    ├── cv_text ───────────────────────────────────────────┼──→ Layer 7 (dossier)
    └── cv_reasoning ──────────────────────────────────────┼──→ Debugging
                                                           │
    ▼                                                      │
LAYER 7: Dossier Generator                                 │
    └── dossier_path, drive_folder_url ────────────────────┴──→ OUTPUT
```

---

## 5. Technical Debt Identification

### High Priority (Blocking/Risky)

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **Dual Tier Systems** | UI vs Backend | Confusion: A/B/C vs fast/balanced/quality | Unify to single tier enum |
| **Legacy Field Duplication** | `company_summary` vs `company_research.summary` | Data inconsistency | Remove legacy fields |
| **Sync/Async Mixing** | `pain_point_miner.py:951-982` | Thread pool overhead, potential deadlocks | Full async migration |
| **Claude CLI Dependency** | All layers | Single point of failure | Better fallback testing |

### Medium Priority (Performance/Maintenance)

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **No Batch Optimization** | Full extraction | Sequential layer execution | Parallel where possible |
| **Redundant LLM Calls** | Company research | Same company researched per job | Better caching strategy |
| **Large State Objects** | `state.py` | Memory pressure, slow serialization | Lazy loading |
| **Hardcoded Limits** | `MAX_TOTAL_CONTACTS = 5` | Arbitrary caps | Configurable |

### Low Priority (Cleanup)

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **Unused `people` Field** | `state.py:259` | Dead code | Remove entirely |
| **Deprecated `linkedin_message`** | `state.py:117` | Confusion | Remove after migration |
| **Multiple JSON Parsers** | Various layers | Inconsistent error handling | Centralize |

---

## 6. Field Value Assessment

### Critical Fields (Never Remove)

| Field | Layer | Reason |
|-------|-------|--------|
| `extracted_jd` | 1.4 | Foundation for all downstream processing |
| `pain_points` | 2 | Drives STAR selection, fit scoring, CV generation |
| `fit_score` | 4 | Primary prioritization metric |
| `competency_weights` | 1.4 | Determines CV bullet emphasis |
| `top_keywords` | 1.4 | ATS optimization critical for job success |

### High Value Fields

| Field | Layer | Reason |
|-------|-------|--------|
| `company_research.signals` | 3 | Powers "why now" and interview prep |
| `role_research.business_impact` | 3.5 | Achievement alignment |
| `primary_contacts` | 5 | Direct outreach targets |
| `cv_text` | 6 | Final deliverable |

### Medium Value Fields

| Field | Layer | Reason |
|-------|-------|--------|
| `strategic_needs` | 2 | Useful for cover letter, not critical |
| `risks_if_unfilled` | 2 | Urgency messaging |
| `secondary_contacts` | 5 | Backup contacts |
| `nice_to_haves` | 1.4 | Secondary keywords |

### Redundant/Low Value Fields (Consider Removal)

| Field | Layer | Reason | Recommendation |
|-------|-------|--------|----------------|
| `company_summary` | Legacy | Duplicates `company_research.summary` | **Remove** |
| `company_url` | Legacy | Duplicates `company_research.url` | **Remove** |
| `people` | Legacy | Replaced by `primary_contacts` + `secondary_contacts` | **Remove** |
| `linkedin_message` | Legacy | Replaced by `linkedin_connection_message` | **Remove** |
| `education_requirements` | 1.4 | Rarely used in downstream | Keep but optional |
| `years_experience_required` | 1.4 | Simple matching, limited value | Keep but optional |

---

## 7. MongoDB Field Summary Table

| Collection | Field Path | Type | Written By | Read By | Critical |
|------------|------------|------|------------|---------|----------|
| `level-2` | `extracted_jd` | Object | Layer 1.4 | 2, 4, 5, 6 | Yes |
| `level-2` | `extracted_jd.role_category` | String | Layer 1.4 | Layer 6 | Yes |
| `level-2` | `extracted_jd.competency_weights` | Object | Layer 1.4 | Layer 6 | Yes |
| `level-2` | `extracted_jd.top_keywords` | Array | Layer 1.4 | Layer 6 | Yes |
| `level-2` | `pain_points` | Array | Layer 2 | 2.5, 4, 6 | Yes |
| `level-2` | `strategic_needs` | Array | Layer 2 | Layer 6 | No |
| `level-2` | `risks_if_unfilled` | Array | Layer 2 | Outreach | No |
| `level-2` | `success_metrics` | Array | Layer 2 | Layer 4 | No |
| `level-2` | `company_research` | Object | Layer 3 | 3.5, 5, 7 | Yes |
| `level-2` | `company_research.signals` | Array | Layer 3 | 3.5, Outreach | Yes |
| `level-2` | `role_research` | Object | Layer 3.5 | 6, 7 | Yes |
| `level-2` | `role_research.why_now` | String | Layer 3.5 | Outreach | Yes |
| `level-2` | `fit_score` | Integer | Layer 4 | UI, Tier | Yes |
| `level-2` | `fit_rationale` | String | Layer 4 | Layer 7 | No |
| `level-2` | `fit_category` | String | Layer 4 | UI | No |
| `level-2` | `tier` | String | Layer 4 | Model selection | Yes |
| `level-2` | `primary_contacts` | Array | Layer 5 | Layer 7 | Yes |
| `level-2` | `secondary_contacts` | Array | Layer 5 | Layer 7 | No |
| `level-2` | `cv_text` | String | Layer 6 | Layer 7 | Yes |
| `level-2` | `cv_reasoning` | String | Layer 6 | Debug | No |
| `level-2` | `dossier_path` | String | Layer 7 | UI | No |
| `company_cache` | (7-day TTL) | Object | Layer 3 | Layer 3 | N/A |

---

## 8. Prompt Quality Summary

| Layer | Persona | Anti-Hallucination | Domain-Aware | Confidence | Grade |
|-------|---------|-------------------|--------------|------------|-------|
| 1.4 | Expert analyst | Source citation | 8 role categories | N/A | A |
| 2 | Revenue Diagnostician | Evidence+confidence | 8 domains | Yes | A+ |
| 3 | BI Analyst | Source URLs required | N/A | N/A | A |
| 3.5 | Role Analyst | Signal references | N/A | N/A | B+ |
| 4 | Executive Recruiter | STAR citations | Rubric-based | Implicit | A |
| 5 | Discovery + Classification | Contact verification | Contact types | N/A | B+ |
| 6 | CV Expert | Source text matching | Role-aware | QA phase | A |

---

## 9. Operation Execution Summary

| Operation | Layers | Execution | Est. Duration | Est. Cost |
|-----------|--------|-----------|---------------|-----------|
| **Full Extraction** | 1.4 → 2 → 4 | Sequential | 20-30s | $0.02-0.15 |
| **Research Company** | 3 → 3.5 → 5 | Sequential | 40-60s | $0.03-0.20 |
| **Generate CV** | 6v2 (6 phases) | Sequential | 60-90s | $0.05-0.50 |
| **All Ops** | (1.4→2→4) ‖ (3→3.5→5) | Parallel | 50-60s | $0.05-0.35 |
| **Full Pipeline** | All layers | Mixed | 2-3min | $0.15-1.00 |

---

## 10. Recommendations Summary

### Immediate Actions

1. **Unify Tier System** - Single enum: `fast`/`balanced`/`quality` everywhere
2. **Remove Legacy Fields** - `company_summary`, `company_url`, `people`, `linkedin_message`
3. **Add Field Validation** - Pydantic models for all MongoDB writes

### Short-Term Improvements

1. **Parallel Execution** - Full Extraction layers can run some phases in parallel
2. **Better Caching** - Company research should check cache before FireCrawl
3. **Progress Streaming** - Per-phase progress updates for long operations

### Long-Term Architecture

1. **Event-Driven** - Pub/sub for layer completion instead of sequential
2. **Partial Results** - Return usable results even if later layers fail
3. **Cost Budgets** - Per-job cost caps with automatic tier adjustment

---

## Files Referenced

- `frontend/templates/index.html` - Main jobs page
- `frontend/templates/batch_processing.html` - Batch processing page
- `frontend/templates/base.html` - Base JS handlers
- `frontend/app.py` - Flask routes (jobs API)
- `frontend/runner.py` - Flask routes (runner proxy)
- `runner_service/routes/operations.py` - FastAPI operations
- `src/layer1_4/claude_jd_extractor.py` - JD extraction
- `src/layer2/pain_point_miner.py` - Pain point mining
- `src/layer3/company_researcher.py` - Company research
- `src/layer3/role_researcher.py` - Role research
- `src/layer4/opportunity_mapper.py` - Fit scoring
- `src/layer5/people_mapper.py` - Contact discovery
- `src/layer6_v2/orchestrator.py` - CV generation
- `src/layer7/dossier_generator.py` - Dossier assembly
- `src/common/state.py` - State schema (JobState)
- `src/common/unified_llm.py` - LLM wrapper
