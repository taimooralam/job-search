This is a document where I write reported bugs and their outcomes.

Use @architect-debugger agent to find the root cause
Use @job-search-archtiect agent to verify the architecture and how the requirements and correct functionality should be
Use @backend-developer to write backend code to fix it, if the work is substantial
Use @front-developer to write frontend code to fix it, if the work is substantial
Use @test-generator to write tests
Use @doc-sync agent to update documetation
Then do atomic commits
Then summarize the root cause, and the fix using your reasoning

TODO: generate a persona in implied person so that it can fit into prompts for systems. e.g. As an {persona}, or you are a {persona}

TODO: I don't want to chose STARs rather I want to first filter out the annotations: core_strengths, identities, passions, pain points

TODO: I want to create a principle for header generation,
I want to divide them by the role

Engineering Manager, Director of Software Engineering, Head of Software Engineering, Staff Software Engineer, Principal Software Engineer, CTO, VP Engineering, Head of Technology

Persona System prompt:
Rather than this system prompt what about this prompt

You are a {persona guidance} writing a Tagline. PROFILE SYSTEM PROMPT

"CANDIDATE PERSONA (Frame ALL output around this identity) ===

{persona_guidance}

This persona defines WHO the candidate is as a professional.
The headline and opening of the narrative MUST embody this identity.
Frame every achievement through this persona's lens.
Avoid sounding like a generic list - BE this professional"

Tag line:
Explains who I am? What I do? What I am passionate about.

Butllet points:
explain real strengths
explain passions
explain technologies
explain how I can allieviate pain points

give examples:

Audience: hiring managers and recruiters and ATS, goal is for them to read the header for 6 seconds and be convinced that I am the ideal candidate. The goal is for the ATS is to generate maximum competence and mark me as the most top candidate as possible.

Why is profile not being called or executive summary?

Extraction run:
JD extraction waits pipelien with empty screen. Only starts with the extraction is complete

## Fixed Bugs

### [FIXED] Master CV Editor Changes Not Applied to CV Generation

**Issue**: CV edits made via the Master CV Editor (stored in MongoDB) were ignored during CV generation. CVLoader was defaulting to `use_mongodb=False`, causing the pipeline to fall back to local role files instead of using the edited master CV.

**Root Cause**: CVLoader initialization in `src/layer6_v2/orchestrator.py` was hardcoded to `use_mongodb=False` instead of respecting the configuration flag that enables MongoDB master CV usage.

**Fix**:
1. Added `USE_MASTER_CV_MONGODB` config flag in `src/common/config.py` (defaults to `true`)
2. Updated `CVLoader()` initialization in `src/layer6_v2/orchestrator.py` to use `Config.USE_MASTER_CV_MONGODB`
3. Enhanced logging in `src/layer6_v2/cv_loader.py` to clearly indicate MongoDB vs local file usage

**Files Changed**:
- `src/common/config.py` - Added config flag with default `true`
- `src/layer6_v2/orchestrator.py` - Pass config flag to CVLoader
- `src/layer6_v2/cv_loader.py` - Enhanced logging with indicators

**Verification**: 6 roles successfully loaded from MongoDB, 35 unit tests passing, config validation confirmed

---

### [FIXED] Marking Job as "Applied" Fails with JSON Parse Error

**Error**: `Failed to update outcome: JSON.parse: unexpected character at line 1 column 1 of the JSON data`

**Root Cause**: The `from src.analytics.outcome_tracker import OutcomeTracker` import statement in `frontend/app.py` was positioned OUTSIDE the try-except block in the `update_job_outcome` endpoint. When the `src` module is unavailable (e.g., on Vercel where only `frontend/` is deployed), Python raises an `ImportError` that wasn't caught, causing Flask to return an HTML 500 error page instead of JSON. The JavaScript then failed to parse this HTML response.

**Fix**: Moved the import inside the try-except block and added explicit `ImportError` handling that returns a proper JSON response with 503 status code. Applied the same fix to related endpoints:
- `/api/jobs/<job_id>/outcome` (PATCH)
- `/api/analytics/outcomes` (GET)
- `/api/analytics/funnel` (GET)
- `/api/jobs/<job_id>/interview-prep/generate` (POST)

**Files Changed**: `/Users/ala0001t/pers/projects/job-search/frontend/app.py`

**Verification**: All 1735 unit tests and 75 frontend tests pass.

---

### [FIXED] SSE Streaming Showed Empty Screen During Pipeline Execution

**Issue**: When running partial pipelines (research-company, generate-cv, full-extraction), the frontend displayed an empty/blank screen during execution. Logs only appeared after the operation completed, not in real-time.

**Root Cause**: Event loop starvation. Services emitted progress via `emit_progress()`, but this was a blocking synchronous call. While the service was processing LLM requests (2-5 minutes), it never yielded control back to the event loop, preventing the SSE generator from delivering logs to connected clients in real-time.

**Fix**: Multi-layer solution addressing event loop starvation and polling efficiency:

1. **Service Layer** - Made `emit_progress()` async with `await asyncio.sleep(0)` yield point:
   - `src/services/full_extraction_service.py` - Added async emit in `process_extraction()`
   - `src/services/company_research_service.py` - Added async emit in `research_company()`
   - `src/services/cv_generation_service.py` - Added async emit in `generate_cv()`

2. **SSE Generator** - Reduced poll interval from 500ms to 100ms for faster delivery:
   - `runner_service/routes/operation_streaming.py` - Changed interval from 0.5s to 0.1s

3. **Flask Proxy** - Changed from line-based to chunk-based streaming for real-time delivery:
   - `frontend/runner.py` - Replaced `iter_lines()` with `iter_content(chunk_size=1024)` for immediate chunk delivery

**Files Changed**:
- `src/services/full_extraction_service.py`
- `src/services/company_research_service.py`
- `src/services/cv_generation_service.py`
- `runner_service/routes/operation_streaming.py`
- `frontend/runner.py`

**Tests Added**: 12 new comprehensive tests in `tests/unit/test_sse_streaming_fix.py`:
- Test async emit doesn't block event loop
- Test poll interval respects 100ms window
- Test iter_content delivers chunks without buffering
- Test log delivery within 200ms of emit
- Test frontend receives logs during execution (not just after completion)

**Verification**: All 12 SSE streaming tests pass, 1735 unit tests passing, frontend displays logs in real-time during pipeline operations.
