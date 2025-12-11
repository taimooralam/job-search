This is a document where I write reported bugs and their outcomes.

Use @architect-debugger agent to find the root cause
Use @job-search-archtiect agent to verify the architecture and how the requirements and correct functionality should be
Use @backend-developer to write backend code to fix it, if the work is substantial
Use @front-developer to write frontend code to fix it, if the work is substantial
Use @test-generator to write tests
Use @doc-sync agent to update documetation
Then do atomic commits
Then summarize the root cause, and the fix using your reasoning

BUG 1. [FIXED] When I launch Extract, Research, Generate CV button on the job detail page, the console logs that show SSE logs from the server do not show up. They did show up in the past when the button was only the process (complete) pipeline. Fix this issue to show up the console at the right place according to UX/UI even in the popup in the bottom right, but show it for all steps i.e. processing the whole pipeline, or running a partial processing such as structuring, extracting, researching and generating CV.

**Root Cause**: In `pipeline-actions.js:278`, the `eventSource.onmessage` handler only sent logs to `console.log()` instead of displaying them in the UI panel. The full pipeline in `job-detail.js` correctly appended logs to `#logs-content`, but partial operations did not.

**Fix Applied**:
1. Enhanced `showPipelineLogPanel()` in `job-detail.js` to include a collapsible log terminal section (dark bg, green monospace text)
2. Added `appendLogToPipelinePanel(logText)` function with color-coded log levels (ERROR=red, WARN=yellow, INFO=green, DEBUG=gray)
3. Added `togglePipelineLogTerminal()` function to show/hide logs
4. Modified `pipeline-actions.js` to call `window.appendLogToPipelinePanel()` in addition to `console.log()`
5. Exposed both new functions globally via `window` object

**Files Modified**:
- `frontend/static/js/job-detail.js` (lines 200-431)
- `frontend/static/js/pipeline-actions.js` (lines 277-283)

**Tests**: All 624 frontend tests pass. New tests added in `tests/frontend/test_sse_log_display.py`.

BUG 2. [FIXED] When I launch the extract button, the extraction happens but the company research, role research and people research and mapper doesn't show up on the detail page after reload.

**Root Cause Analysis**: This was NOT a bug but an intentional architectural design:
- **Extract JD button** runs Layers 1.4, 2, 4 (JD structuring, pain points, fit score) - local processing only
- **Research button** runs Layer 3, 3.5 (company + role research) - uses external FireCrawl APIs
- **People research** (Layer 5) was NOT included in the Research button

The separation exists for:
1. **Cost control** - People research uses FireCrawl API credits
2. **Caching** - Company data has 7-day TTL, can skip re-research
3. **Failure isolation** - Each layer can fail independently

**User Expectation vs Reality**: User expected Research to also discover contacts (people research). The original design separated this.

**Fix Applied**:
1. Modified `PeopleMapper.map_people()` to accept `skip_outreach: bool = False` parameter
2. When `skip_outreach=True`, only contact discovery runs (no outreach message generation)
3. Enhanced `CompanyResearchService.execute()` to also call Layer 5 with `skip_outreach=True`
4. Updated `_persist_research()` to save `primary_contacts` and `secondary_contacts` to MongoDB
5. Outreach message generation remains on-demand (to be triggered separately)

**New Workflow**:
| Button | Layers | What it does |
|--------|--------|--------------|
| Extract JD | 1.4, 2, 4 | JD structure, pain points, fit score |
| Research | 3, 3.5, **5** | Company research, role research, **contact discovery** |
| Generate CV | 6 | CV generation |
| (Future) Outreach | - | Outreach messages on-demand |

**Files Modified**:
- `src/layer5/people_mapper.py` - Added `skip_outreach` parameter to `map_people()`
- `src/services/company_research_service.py` - Added Layer 5 call and contact persistence
- `tests/unit/test_layer5_people_mapper.py` - Added 4 new tests for skip_outreach
- `tests/unit/test_company_research_service.py` - Added 5 new tests for people research integration

**Tests**: All 1645 unit tests pass. New tests in `TestSkipOutreachParameter` and `TestCompanyResearchServicePeopleResearch` classes.

BUG 3. [FIXED] QUICK ADD toolbar missing Passion and Identity dimensions

**Problem**: The QUICK ADD toolbar in the JD Annotation panel only had Relevance (Core, Strong, Medium, Weak, Gap) and Requirement (Must-Have, Nice-to-Have) buttons. The Passion and Identity dimensions were only available in:
- The full annotation popover (all 5 levels each)
- The sidebar filter buttons (love_it, avoid, core_identity, not_identity)

Users could not quickly annotate with Passion/Identity from the toolbar without opening the popover.

**Root Cause**: The toolbar in `_jd_annotation_panel.html` was never updated to include the Passion and Identity quick-add buttons, even though the data model, popover, and sidebar filters all supported these dimensions.

**Fix Applied**:
1. Added two new button groups to the QUICK ADD toolbar:
   - Passion: Love (love_it) and Avoid (avoid) - matching sidebar filters
   - Identity: Core ID (core_identity) and Not Me (not_identity) - matching sidebar filters
2. Added JavaScript handler functions `setQuickPassion()` and `setQuickIdentity()` in `jd-annotation.js`
3. Styled buttons consistently with existing toolbar buttons (pink for love, stone for avoid, indigo for core_identity, zinc for not_identity)

**Files Modified**:
- `frontend/templates/partials/job_detail/_jd_annotation_panel.html` (lines 149-179, added button groups)
- `frontend/static/js/jd-annotation.js` (lines 1959-1974, added handler functions)

BUG 4. [FIXED] Annotation showing "null" instead of relevance level in sidebar

**Problem**: In the annotation sidebar, some annotations displayed "null" as the relevance badge text instead of a proper label like "Core", "Strong", etc. This occurred when an annotation was created with only Passion or Identity set, but no Relevance selected.

**Root Cause**: In `jd-annotation.js`, the `formatRelevance()` function at line 968 returned the raw `relevance` value as a fallback: `return labels[relevance] || relevance;`. When `relevance` was `null`, this returned `null` which was rendered literally as "null" in the HTML.

The system intentionally allows saving annotations when ANY dimension is selected (relevance OR requirement OR passion OR identity) via OR logic in `updatePopoverSaveButton()`. This means users can create annotations with only passion set (e.g., "enjoy" = purple heart) and no relevance value.

**Fix Applied**:
Modified `renderAnnotationItem()` in `jd-annotation.js` to conditionally render the relevance badge only when `annotation.relevance` is truthy:

```javascript
// Relevance badge - only show if relevance is set (avoid showing "null")
const relevanceBadge = annotation.relevance
    ? `<span class="px-1.5 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}">
           ${this.formatRelevance(annotation.relevance)}
       </span>`
    : '';
```

This approach hides the relevance badge entirely when not set, rather than showing "null" or a confusing "Unset" label.

**Files Modified**:
- `frontend/static/js/jd-annotation.js` (lines 882-934, modified `renderAnnotationItem()` function)

BUG 5. [FIXED] Synthesized persona too short, not reflecting all identities/strengths

**Problem**: When users added many identity and core strength annotations, the synthesized persona was too short and didn't reflect all of them. Example persona was only ~27 words despite having 5+ core identity annotations.

**Root Cause**: Multiple hardcoded limits in `persona_builder.py`:
1. LLM prompt constrained to **20-35 words** only
2. Only **3 annotations per category** passed to LLM (core_identity, love_it, etc.)
3. Secondary identities capped at **5**
4. Source annotation tracking capped at **3 per level**

**Fix Applied**:
1. Updated SYNTHESIS_PROMPT: Changed from "20-35 words" to "35-60 words, 1-2 sentences"
2. Increased annotation limits per category:
   | Category | Old | New |
   |----------|-----|-----|
   | core_identity | 3 | 6 |
   | strong_identity | 3 | 5 |
   | developing | 2 | 4 |
   | love_it | 3 | 5 |
   | enjoy | 3 | 5 |
   | core_strength | 3 | 5 |
   | extremely_relevant | 3 | 5 |
3. Increased secondary_identities cap from 5 to 10
4. Increased source annotation tracking from 3 to 6 per level
5. Added debug logging when annotations are truncated

**Files Modified**:
- `src/common/persona_builder.py` (SYNTHESIS_PROMPT, _build_persona_context, _get_source_annotation_ids, secondary_identities cap)

**Tests**: All 33 persona builder tests pass.

BUG 6. [FIXED] Research data (company, role, people) not displaying on detail page after Research button completes

**Problem**: User clicks the Research button, research completes successfully (persisted to MongoDB), but company research summary, role research (summary, business_impact, why_now), and contact information don't show on the job detail page after reload.

**Root Cause**: The template `job_detail.html` was missing a dedicated UI section to display research data independently. The only place showing company signals was inside the "Intelligence Summary" collapsible, which was **nested inside** the `{% if job.extracted_jd %}` block (lines 659-1006). This meant:
1. If a job had research data but no extracted_jd, company signals wouldn't display
2. `company_research.summary`, `role_research.summary`, `role_research.business_impact`, `role_research.why_now` were NEVER displayed anywhere in the template
3. The People/Contacts section existed and worked correctly (lines 1444+), but only if data existed

**Investigation**:
- Verified MongoDB has correct data: `company_research.summary`, `company_research.signals`, `role_research.summary`, `role_research.business_impact`, `role_research.why_now`, `primary_contacts`, `secondary_contacts` all present
- Grep for template usage found no references to `role_research.summary`, `role_research.business_impact`, `role_research.why_now`, or `company_research.summary`
- The `serialize_job()` function correctly passes all fields through
- The issue was purely a template display gap

**Fix Applied**:
Added a new "Company & Role Research" section to `job_detail.html` that renders **independently** of extracted_jd (inserted at line 1008, after the extracted_jd section closes). The new section includes:

1. **Company Intelligence Card**:
   - Company type badge (Employer/Recruitment Agency)
   - Company summary (2-3 sentences)
   - Company URL link
   - Business Signals list with type badges and dates

2. **Role Intelligence Card**:
   - Role summary (2-3 sentences)
   - Business Impact bullets (3-5 items with checkmarks)
   - "Why Now?" context box explaining timing significance

The section uses consistent dark mode support and styling matching the rest of the page.

**Files Modified**:
- `frontend/templates/job_detail.html` (lines 1008-1139, added new Company & Role Research section)

**Tests**: Template syntax validated via Jinja2. All 1682+ unit tests pass.

BUG 7. [FIXED] CV Generation fails with "list index out of range" error

**Problem**: When clicking Generate CV, the process fails with:
```
✅ build_state: State prepared
❌ cv_generator: CV Gen V2 error: list index out of range
```

**Root Cause**: Found by architecture-debugger agent. The bug was in `orchestrator.py:885` where:
```python
keyword = ann.get("matching_skill") or ann.get("suggested_keywords", [""])[0]
```

**The Python .get() Trap**: When `suggested_keywords` key **exists** but contains an **empty list `[]`**, the `.get()` method returns `[]` (not the default `[""]`). Then accessing `[][0]` raises `IndexError: list index out of range`.

This is a subtle Python gotcha: `dict.get(key, default)` only uses `default` when the key is **missing** - not when the value is empty/falsy!

**Additional instances found**:
1. `orchestrator.py:899` and `901` - Same pattern for `variants` field
2. `annotation_tracking_service.py:420` - Same pattern for keyword extraction

**Fix Applied**:
Changed the pattern from:
```python
ann.get("suggested_keywords", [""])[0]  # BUG: fails if key exists but value is []
```
To:
```python
suggested = ann.get("suggested_keywords") or []  # Handle both missing AND empty
keyword = ann.get("matching_skill") or (suggested[0] if suggested else "")
```

**Files Modified**:
- `src/layer6_v2/orchestrator.py` (lines 885-887, 897-903)
- `src/services/annotation_tracking_service.py` (lines 420-422)

**Tests**: Added 3 new test cases in `TestATSValidationEdgeCases`:
1. `test_handles_empty_suggested_keywords` - Tests empty `[]` case (the bug trigger)
2. `test_handles_missing_suggested_keywords` - Tests missing key case
3. `test_handles_none_annotation_values` - Tests `None` value case

All 14 orchestrator tests pass.

BUG 8. [FIXED] Extract JD and Research operations timeout before completing

**Problem**: When running Extract JD or Research operations, they timeout with "Runner service timeout" error:
```
full-extraction failed: Error: Runner service timeout
research-company failed: Error: Runner service timeout
```

Extract JD gets stuck at "Pain Points" → "Fit Scoring" step.
Research gets stuck at "Save Results" step.
SSE console logs don't appear during operation execution.

**Root Cause**: The SSE streaming architecture was working correctly, but the services were not emitting any progress updates **during** execution. The streaming endpoint in `operations.py` had `layer_cb` callbacks that only fired:
1. **Before** calling `service.execute()` (immediately sent)
2. **After** `service.execute()` completes (sent only after 2-5 minutes)

The actual LLM calls and processing inside each service (2-5 minutes) had no intermediate progress signals. The SSE stream was idle during this time, making the frontend think the operation had stalled.

**Fix Applied**:
Added `progress_callback` parameter to all three operation services and emit real-time progress updates at each step:

1. **FullExtractionService** (`src/services/full_extraction_service.py`):
   - Added `progress_callback: callable = None` parameter
   - Added `emit_progress()` helper function
   - Emits progress for: `jd_processor`, `jd_extractor`, `pain_points`, `fit_scoring`, `save_results`

2. **CompanyResearchService** (`src/services/company_research_service.py`):
   - Added `progress_callback: callable = None` parameter
   - Added `emit_progress()` helper function
   - Emits progress for: `fetch_job`, `cache_check`, `company_research`, `role_research`, `people_research`, `save_results`

3. **CVGenerationService** (`src/services/cv_generation_service.py`):
   - Added `progress_callback: callable = None` parameter
   - Added `emit_progress()` helper function
   - Emits progress for: `fetch_job`, `validate`, `build_state`, `cv_generator`, `persist`

4. **Streaming endpoints** (`runner_service/routes/operations.py`):
   - Updated `full_extraction_stream` to pass `layer_cb` as `progress_callback`
   - Updated `research_company_stream` to pass `layer_cb` as `progress_callback`
   - Updated `generate_cv_stream` to pass `layer_cb` as `progress_callback`
   - Removed redundant manual `layer_cb` calls that were only happening before/after execute

**Architecture Insight**: The callback pattern works as follows:
```
Frontend → POST /stream → Runner creates run_id, starts background task
         → GET /logs (SSE) → Stream connected

Background task:
  service.execute(progress_callback=layer_cb)
    └── emit_progress("jd_extractor", "processing", "Extracting JD...")
        └── layer_cb() → update_layer_status() → SSE emits to frontend
```

**Files Modified**:
- `src/services/full_extraction_service.py` (lines 83-89, 108-178)
- `src/services/company_research_service.py` (lines 96-102, 125-230)
- `src/services/cv_generation_service.py` (lines 83-89, 104-224)
- `runner_service/routes/operations.py` (lines 742-773, 822-857, 920-951)

**Tests**: All 115 service-related unit tests pass. All 1598 unit tests pass.
