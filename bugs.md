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
