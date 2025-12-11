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
