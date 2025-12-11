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

BUG 2. When I launch the extract button, the extraction happens but the company research, role research and people research and mapper doesn't show up.
