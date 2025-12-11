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
