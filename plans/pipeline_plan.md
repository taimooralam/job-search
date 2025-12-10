# Pipeline Overhaul Implementation Plan

**Date:** 2025-12-10
**Goal:** Transform monolithic pipeline into modular, button-triggered operations with tiered model selection, decoupled outreach, and professional annotation tooling.

---

## Executive Summary

This plan restructures the job-search pipeline from a single "Process Job" button into independent, button-triggered operations. Each operation persists to MongoDB immediately, supports 3-tier model selection (Fast/Balanced/Quality), and provides cost visibility. The heatmap bug is fixed by implementing the empty `applyHighlights()` function.

---

## Persona Assessment

| Persona | Key Concerns | Solutions |
|---------|-------------|-----------|
| **Job Applicant (You)** | Speed, cost control, tailored applications at scale | Independent buttons for parallel work; tier selection for cost/quality tradeoff; human annotations weighted over AI |
| **Hiring Manager** | Authentic, relevant applications | Variant-based CV generation (zero hallucination); annotation-driven customization; pain point mapping |
| **Recruiter** | ATS compatibility, quick screening | Structured JD extraction; keyword alignment; professional formatting |
| **ATS Product Manager** | Parseable format, standard sections | Consistent CV schema; markdown to TipTap migration; PDF export |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           VERCEL (Frontend)                         │
│  Flask + HTMX + Alpine.js + TipTap                                  │
│  - Job list, job detail pages                                       │
│  - Independent action buttons with tier dropdowns                   │
│  - Annotation panel with heatmap highlighting                       │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ HTTP (proxied)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     VPS RUNNER SERVICE (FastAPI)                    │
│  Port 8000 - Handles long-running operations                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Independent Operation Endpoints                              │   │
│  │  POST /api/jobs/{id}/structure-jd     [Layer 1]              │   │
│  │  POST /api/jobs/{id}/research-company [Layer 3]              │   │
│  │  POST /api/jobs/{id}/research-role    [Layer 3.5]            │   │
│  │  POST /api/jobs/{id}/generate-cv      [Layer 6]              │   │
│  │  POST /api/jobs/{id}/contacts/{cid}/generate-outreach        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        MONGODB ATLAS                                │
│  Collections:                                                       │
│  - level-2: Jobs + extracted_jd + annotations + contacts            │
│  - operation_runs: Per-button execution tracking                    │
│  - company_cache: 7-day TTL research cache                          │
│  - star_records: Pre-written achievement variants                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## UX/UI Plan

### 1. Pipeline Action Buttons (KEEP Both Options)

**Location:** Job detail page, Status & Actions section

**Decision:** Keep existing "Process All" button alongside new independent buttons.

```
┌─────────────────────────────────────────────────────────────────────┐
│  PIPELINE ACTIONS                                                    │
├─────────────────────────────────────────────────────────────────────┤
│  [Process All ▾]  │  [Structure JD ▾]  [Research ▾]  [Generate CV ▾]│
│  (Full Pipeline)  │       │               │              │          │
│  Auto/A/B/C/D     │   Fast/Balanced/  Fast/Balanced/ Fast/Balanced/ │
│                   │   Quality         Quality        Quality        │
│                   │                                                  │
│                   │  [Annotate JD]  (no tier - opens panel)         │
└─────────────────────────────────────────────────────────────────────┘
```

**Two-Mode Design:**
- **Process All (existing):** Full 7-layer pipeline with existing tier system (Auto/A/B/C/D)
- **Individual buttons (new):** Structure JD, Research, Generate CV - each with new 3-tier system

**Button Specifications:**

| Button | Default Tier | Triggers | Persists To |
|--------|-------------|----------|-------------|
| Structure JD | Balanced | Layer 1.4 JD extraction + structuring | `extracted_jd`, `processed_jd` |
| Role Research | Balanced | Layers 3 + 3.5 company/role research | `company_research`, `role_research` |
| Generate CV | Quality | Layer 6 CV generation | `cv_text`, `cv_editor_state` |
| Annotate JD | N/A (no LLM) | Opens annotation panel | `jd_annotations` |

### 2. Model Tier Dropdown Component

Each button has a split-button design with tier dropdown:

```html
[Button Label ▾]
├── Fast (gpt-4o-mini)        ~$0.02  ⚡
├── Balanced (gpt-4o-mini)    ~$0.05  ⚖️  ← Default
└── Quality (claude-sonnet)   ~$0.15  ✨
```

**Tier-to-Model Mapping:**

| Tier | JD Tasks | Research Tasks | CV Generation |
|------|----------|----------------|---------------|
| Fast | gpt-4o-mini | gpt-4o-mini | claude-haiku |
| Balanced | gpt-4o-mini | gpt-4o-mini | claude-sonnet |
| Quality | gpt-4o | gpt-4o | claude-sonnet |

### 3. Heatmap/Annotator Improvements

**ROOT CAUSE IDENTIFIED:** `applyHighlights()` in `jd-annotation.js:708-711` is an empty TODO stub.

**Fix:** Implement text highlighting using TreeWalker DOM traversal:

```javascript
applyHighlights() {
    const contentEl = document.getElementById('jd-processed-content');
    if (!contentEl || !this.annotations.length) return;

    // Clear existing highlights
    contentEl.querySelectorAll('.annotation-highlight').forEach(el => {
        const text = el.textContent;
        el.replaceWith(document.createTextNode(text));
    });

    // Apply highlights for active annotations
    this.annotations.filter(a => a.is_active).forEach(ann => {
        this.highlightTextInElement(contentEl, ann.target?.text, ann.relevance);
    });
}
```

**Visual Improvements:**
- Increase opacity from 0.25 → 0.35 for better visibility
- Add section type indicators (colored left border)
- Add Human vs AI badge to annotations
- Keyboard shortcuts (1-5 for relevance levels)

### 4. Contacts & Outreach UX (Decoupled)

**Remove from pipeline:** Outreach generation now triggered per-contact, on-demand.

**Contact Card with Generation Buttons:**
```
┌─────────────────────────────────────────────────────────────────────┐
│  Jane Smith - VP Engineering                      [LinkedIn →]      │
│  Why: Department head for engineering teams                         │
├─────────────────────────────────────────────────────────────────────┤
│  [Generate Connection ▾]  [Generate InMail ▾]                       │
│  OR (if already generated):                                         │
│  ▶ Connection (285/300)    ▶ InMail/Email [Copy]                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5. Metadata & Cost Display

**Quick Info Bar additions:**
- Total cost: `$0.0234 (3 runs)`
- Hover tooltip with per-operation breakdown
- Budget warning at 80% threshold

---

## Backend Architecture Plan

### 1. New API Endpoints

| Endpoint | Method | Purpose | Request Body |
|----------|--------|---------|--------------|
| `/api/jobs/{id}/structure-jd` | POST | Extract + structure JD | `{tier, use_llm}` |
| `/api/jobs/{id}/research-company` | POST | Company research | `{tier, force_refresh}` |
| `/api/jobs/{id}/research-role` | POST | Role research | `{tier}` |
| `/api/jobs/{id}/generate-cv` | POST | CV generation only | `{tier, use_annotations}` |
| `/api/jobs/{id}/contacts` | POST | Add/manage contacts | `{contacts: [...]}` |
| `/api/jobs/{id}/contacts/{cid}/generate-outreach` | POST | On-demand outreach | `{tier, type: "connection"|"inmail"}` |
| `/api/jobs/{id}/estimate-cost` | GET | Pre-execution cost estimate | Query: `operations, tier` |

### 2. New 3-Tier Model System

**File:** `src/common/model_tiers.py` (new)

```python
class ModelTier(str, Enum):
    FAST = "fast"         # ~$0.02/op
    BALANCED = "balanced" # ~$0.05/op
    QUALITY = "quality"   # ~$0.15/op

TIER_CONFIGS = {
    ModelTier.FAST: TierModelConfig(
        complex_model="gpt-4o-mini",
        analytical_model="gpt-4o-mini",
        simple_model="gpt-4o-mini",
    ),
    ModelTier.BALANCED: TierModelConfig(
        complex_model="gpt-4o",
        analytical_model="gpt-4o-mini",
        simple_model="gpt-4o-mini",
    ),
    ModelTier.QUALITY: TierModelConfig(
        complex_model="claude-sonnet-4-20250514",
        analytical_model="gpt-4o",
        simple_model="gpt-4o-mini",
    ),
}
```

### 3. MongoDB Schema Updates

**Job Document Additions:**

```javascript
{
  // NEW: Per-operation run tracking
  "operation_runs": [{
    "run_id": "op_structure-jd_abc123",
    "operation": "structure-jd",
    "tier": "balanced",
    "status": "completed",
    "cost_usd": 0.002,
    "started_at": Date,
    "completed_at": Date
  }],

  // NEW: Contacts (decoupled from pipeline)
  "contacts": [{
    "contact_id": "ct_001",
    "name": "Jane Smith",
    "role": "VP Engineering",
    "linkedin_url": "...",
    "contact_type": "vp_director",
    "outreach": {
      "linkedin_connection_message": "...",
      "generated_at": Date,
      "tier_used": "balanced"
    }
  }],

  // NEW: Aggregate cost tracking
  "total_operations_cost_usd": 0.15
}
```

**New Collection:** `operation_runs` for detailed tracking

### 4. Operation Service Architecture

**Base class:** `src/services/operation_base.py`

```python
class OperationService(ABC):
    operation_name: str

    async def execute(self, job_id: str, tier: ModelTier, **kwargs) -> OperationResult
    def get_model(self, tier: ModelTier) -> str
    def persist_run(self, ...) -> None
```

**Services:**
- `StructureJDService` - Wraps Layer 1.4
- `CompanyResearchService` - Wraps Layer 3
- `RoleResearchService` - Wraps Layer 3.5
- `CVGenerationService` - Wraps Layer 6 V2
- `OutreachGenerationService` - Per-contact generation

### 5. Cost Control

- Pre-execution budget check with `BudgetEnforcer`
- Per-operation cost estimates via `estimate_operation_cost()`
- Warning at 80%, block at 100% of budget
- Per-job budget configurable

---

## Bug Fixes & Improvements

### 1. Heatmap Not Showing (P0)

**Root Cause:** `frontend/static/js/jd-annotation.js:708-711`
```javascript
applyHighlights() {
    // TODO: Apply CSS highlight classes to annotated text
    // This requires tracking character offsets in the processed HTML
}
```

**Fix:** Implement TreeWalker-based text highlighting (see UX section)

### 2. Annotator UX Improvements

| Improvement | Implementation |
|-------------|----------------|
| Keyboard shortcuts | `1-5` for relevance, `m/n` for must-have/nice-to-have |
| Human vs AI badge | Add `source` field to annotations, render badge |
| Better visual hierarchy | Increase opacity, add section type borders |
| Undo/redo | Track last 10 actions in state |

---

## Data Schema

### ExtractedJD (from structure-jd)

```typescript
{
  role_category: string,      // "engineering_manager", "senior_engineer", etc.
  seniority_level: string,    // "senior", "lead", "director"
  competency_weights: {
    delivery: number,
    process: number,
    architecture: number,
    leadership: number
  },
  responsibilities: string[],
  qualifications: string[],
  technical_skills: string[],
  implied_pain_points: string[],
  top_keywords: string[]
}
```

### JDAnnotation (human input)

```typescript
{
  annotation_id: string,
  target: {
    section_type: string,
    text: string,
    char_start: number,
    char_end: number
  },
  relevance: "core_strength" | "extremely_relevant" | "relevant" | "tangential" | "gap",
  requirement_type: "must_have" | "nice_to_have",
  star_id?: string,
  reframe_note?: string,
  source: "manual" | "auto",   // NEW: Human vs AI
  weight: number,              // Human: 1.0, AI: 0.5
  is_active: boolean
}
```

---

## Testing Plan

### Test Ownership Matrix

| Feature | Unit Tests | Integration Tests | Agent |
|---------|------------|-------------------|-------|
| Heatmap highlighting | test_jd_annotation_highlights.py | E2E annotation flow | @frontend-developer |
| Structure JD endpoint | test_structure_jd_service.py | API integration | @backend-developer |
| Model tier routing | test_model_tiers.py | - | @backend-developer |
| CV generation (decoupled) | test_cv_generation_service.py | - | @backend-developer |
| Outreach on-demand | test_outreach_service.py | - | @backend-developer |
| Cost estimation | test_cost_estimator.py | - | @backend-developer |
| Tier dropdown UI | test_tier_dropdown.py | E2E button flows | @frontend-developer |

### Key Test Cases

1. **Heatmap Fix:**
   - `test_highlight_applied_to_annotated_text()`
   - `test_highlight_removed_when_deactivated()`
   - `test_overlapping_annotations_handled()`

2. **Model Tiers:**
   - `test_tier_returns_correct_model()`
   - `test_cost_estimate_accurate()`
   - `test_tier_persisted_to_localStorage()`

3. **Independent Operations:**
   - `test_cv_generation_without_research()`
   - `test_state_merged_from_previous_operations()`
   - `test_operation_run_persisted_to_mongodb()`

---

## Execution Phases

### Phase 1: Foundation (3 days)
**Parallelizable: Yes**

| Task | Files | Agent |
|------|-------|-------|
| Create `src/common/model_tiers.py` | New file | @backend-developer |
| Create `src/services/operation_base.py` | New file | @backend-developer |
| Add MongoDB indexes | Migration script | @backend-developer |
| Create `pipeline-actions.css` | New file | @frontend-developer |
| Create `pipeline-actions.js` | New file | @frontend-developer |

### Phase 2: Heatmap Fix (2 days)
**Parallelizable: Partial**

| Task | Files | Agent |
|------|-------|-------|
| Implement `applyHighlights()` | `jd-annotation.js:708` | @frontend-developer |
| Enhance CSS opacity/borders | `jd-annotation.css` | @frontend-developer |
| Add keyboard shortcuts | `jd-annotation.js` | @frontend-developer |
| Write heatmap tests | `tests/frontend/test_jd_annotation_highlights.py` | @test-generator |

### Phase 3: Button Architecture (3 days)
**Parallelizable: Yes**

| Task | Files | Agent |
|------|-------|-------|
| TieredActionButton component | `job_detail.html:228-365` | @frontend-developer |
| Alpine.js state store | `pipeline-actions.js` | @frontend-developer |
| API route registration | `runner_service/routes/operations.py` | @backend-developer |
| StructureJDService | `src/services/structure_jd_service.py` | @backend-developer |

### Phase 4: Core Operations (4 days)
**Parallelizable: Yes**

| Task | Files | Agent |
|------|-------|-------|
| CVGenerationService | `src/services/cv_generation_service.py` | @backend-developer |
| CompanyResearchService | `src/services/company_research_service.py` | @backend-developer |
| Cost estimation endpoint | `runner_service/routes/operations.py` | @backend-developer |
| Frontend cost display | `job_detail.html` | @frontend-developer |

### Phase 5: Contacts & Outreach (3 days)
**Parallelizable: Yes**

| Task | Files | Agent |
|------|-------|-------|
| Contacts CRUD API | `runner_service/routes/contacts.py` | @backend-developer |
| OutreachGenerationService | `src/services/outreach_service.py` | @backend-developer |
| Contact card UI | `job_detail.html:1080-1357` | @frontend-developer |
| Per-contact generation buttons | `_contacts_section.html` | @frontend-developer |

### Phase 6: Testing & Polish (2 days)

| Task | Files | Agent |
|------|-------|-------|
| Unit tests for services | `tests/unit/test_*_service.py` | @test-generator |
| Integration tests | `tests/integration/` | @backend-developer |
| E2E annotation tests | `tests/e2e/test_annotation_ui.py` | @frontend-developer |
| Update documentation | `docs/`, `missing.md` | @doc-sync |

---

## Critical Files to Modify

### Frontend
- `frontend/templates/job_detail.html` - Button architecture (lines 228-365), contacts section (lines 1080-1357)
- `frontend/static/js/jd-annotation.js` - **FIX `applyHighlights()` at line 708**
- `frontend/static/css/jd-annotation.css` - Enhanced highlight visibility
- `frontend/static/js/pipeline-actions.js` - New file for Alpine.js state
- `frontend/static/css/pipeline-actions.css` - New file for button styling

### Backend
- `runner_service/app.py` - Register new operation routes
- `src/common/model_tiers.py` - New 3-tier system
- `src/services/operation_base.py` - Base class for operation services
- `src/services/structure_jd_service.py` - JD structuring service
- `src/services/cv_generation_service.py` - CV generation service
- `src/services/outreach_service.py` - On-demand outreach service
- `src/common/tiering.py` - Integrate with new tier system

### Tests
- `tests/frontend/test_jd_annotation_highlights.py` - Heatmap tests
- `tests/unit/test_model_tiers.py` - Tier routing tests
- `tests/unit/test_operation_services.py` - Service tests

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Anthropic credits depleted | HIGH | CV generation fails | Implement OpenAI fallback in Quality tier |
| Long-running operations timeout | MEDIUM | Poor UX | Async execution with SSE progress |
| State inconsistency between operations | MEDIUM | Data corruption | Validate state before each operation |
| Cost overruns | LOW | Budget exceeded | Pre-execution budget check, warnings at 80% |

---

## Cost/Data Control Levers

1. **Model Tier Selection**: User controls quality/cost tradeoff per operation
2. **Per-Job Budget**: Optional budget limit stored in job document
3. **Cost Estimation**: Display estimated cost before execution
4. **Operation Isolation**: Only pay for operations you trigger
5. **Caching**: Company research cached 7 days, skip if recent
6. **Rate Limiting**: Semaphore limits concurrent operations

---

## Agent Handoff Notes

### @frontend-developer
- **Priority 1:** Fix `applyHighlights()` in `jd-annotation.js:708` - this is the heatmap bug
- **Priority 2:** Create TieredActionButton component with Alpine.js state
- **Key pattern:** Follow existing Alpine.js patterns in `job-detail.js`

### @backend-developer
- **Priority 1:** Create `model_tiers.py` and `operation_base.py`
- **Priority 2:** Implement StructureJDService and CVGenerationService
- **Key pattern:** Follow existing service patterns, use TokenTracker for cost tracking

### @test-generator
- **Priority 1:** Write heatmap highlight tests
- **Priority 2:** Write model tier routing tests
- **Key pattern:** Mock LLMs and MongoDB per existing `conftest.py` patterns

### @doc-sync
- **After implementation:** Update `missing.md`, `architecture.md`, and create `plans/pipeline_overhaul_complete.md`

---

## Success Criteria

1. ✅ Heatmap highlights visible when annotations exist
2. ✅ Four independent action buttons with tier dropdowns
3. ✅ Each button triggers isolated API call and persists to MongoDB
4. ✅ Cost displayed before and after operations
5. ✅ Contacts and outreach decoupled from main pipeline
6. ✅ All unit tests pass (`pytest -n auto`)
7. ✅ No regressions in existing functionality
