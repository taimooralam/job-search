---
name: apply-jobs
description: Automate job applications via browser — open job URL, fill forms, upload CV, submit with human confirmation. Queries MongoDB for pending jobs or accepts a specific job ID.
argument-hint: [job_id] [--count 3] [--dry-run] [--refresh]
---

# Job Application Co-Pilot

Browser-based job application automation with human-in-the-loop. Always confirms before submitting.

## Input

Parse `$ARGUMENTS`:
- **Positional**: 24-char hex MongoDB ObjectId → apply to that specific job
- `--count N` → process N jobs (default: 1)
- `--dry-run` → stop before submitting
- `--status "..."` → MongoDB status filter (default: `"under processing"`)
- `--skip-upload` → skip CV upload step
- `--refresh` → force re-fetch from MongoDB, ignore cache

**User commands during job list display:**
- "discard X, Y, Z" or "remove X, Y, Z" → set MongoDB `status: "discarded"` for those table row numbers, remove from cache. Jobs are permanently skipped.
- "apply X, Y, Z" or "X, Y, Z" → proceed with those jobs
- "check N" → stale-check top N jobs

## Paths

```
PROJECT      = /Users/ala0001t/pers/projects/job-search
GDRIVE_CVS   = /Users/ala0001t/Library/CloudStorage/GoogleDrive-alamtaimoor.de@gmail.com/My Drive/2 Areas/Job/Job Search/Resume/Companies
PROFILE      = {PROJECT}/data/applicant-profile.yaml
PLAYBOOKS    = {PROJECT}/data/portal-playbooks/
APP_LOG      = {PROJECT}/data/application-log.yaml
MODULES      = {PROJECT}/.claude/skills/apply-jobs/modules/
CACHE        = {PROJECT}/data/apply-jobs-cache.json
TMP_BASE     = /tmp/apply-jobs
```

## Workflow

Execute these steps in order. **Start a timer at session start** (`date +%s` via Bash) and record timestamps per job and per step.

### Step 0: Load Profile + Playbook (upfront)
**Start session timer**: `SESSION_START=$(date +%s)` via Bash. For each job, record `JOB_START` before Step 2 and `JOB_END` after Step 10. At session end (Step 12), compute and report:
- Total session time
- Per-job time
- Per-step breakdown (where possible)
- Tool call count per job (count each tool invocation)
Read **two files** at session start — these contain everything needed for known portals:
1. `data/applicant-profile.yaml` — name, email, phone, work auth, salary, question_cache, voluntary_disclosures
2. The matching portal playbook from `data/portal-playbooks/` (detect from jobUrl domain)

**Do NOT read module files (field-mapping.md, cv-upload.md, etc.) during execution.** The playbook contains all selectors, batch scripts, and CV upload methods. Only read a module file if you encounter an issue not covered by the playbook.

### Step 1: Fetch & Sort Jobs (with cache)

**Cache-first approach** to avoid re-fetching 1000+ jobs from MongoDB every run.

Cache file: `data/apply-jobs-cache.json` — a JSON array of sorted job objects (slim: `_id`, `company`, `title`, `location`, `jobUrl`, `tier`, `priority_label`, `is_ai`, `cv_generated_at`).

**Logic:**
1. If `--refresh` flag is set, skip to step 3 below
2. If cache file exists and is non-empty, read it and use it. Show the top N jobs from cache. Skip MongoDB entirely.
3. If cache is empty/missing OR `--refresh`: connect to MongoDB (`MONGODB_URI` from `.env`, db: `jobs`, collection: `level-2`), query `{status: "under processing", cv_text: {$ne: null}, cv_generated_at: {$ne: null}, jobUrl: {$ne: null}, gdrive_uploaded_at: {$ne: null}, dossier_gdrive_uploaded_at: {$ne: null}}`. **Read `{MODULES}/sorting.md`** for sorting logic. Save sorted list to cache file.

If specific job_id provided: `col.find_one({"_id": ObjectId(job_id)})` — bypass cache entirely.

**After each successful application or skip**, remove that job from the cache file so it won't appear next time.

**Batch stale-check (top N jobs):** Before presenting the list, offer to check the top N jobs for closure signals.

**Method: LinkedIn authenticated HTTP check**
LinkedIn job pages require auth to see closure signals. Use cookies from `data/linkedin-cookies.txt` (Netscape format):

```python
import http.cookiejar, requests, json
from bson import ObjectId
from pymongo import MongoClient

cj = http.cookiejar.MozillaCookieJar('data/linkedin-cookies.txt')
cj.load(ignore_discard=True, ignore_expires=True)
s = requests.Session()
s.cookies = cj
s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})

# For each job URL:
r = s.get(url, timeout=15)
text = r.text  # Search FULL response, not truncated
closed = 'no longer accepting applications' in text.lower()
# Also check: HTTP 404, 'this job has expired', 'job is closed'
```

**Closure signals** (search full HTML, case-insensitive):
- `"No longer accepting applications"` — primary LinkedIn signal
- `"this job has expired"`
- `"job is closed"`
- HTTP 404

**If cookies expired** (auth fails — check for "Sign in" in first 2000 chars): ask user to refresh cookies. Export from browser via EditThisCookie extension → Netscape format → save to `data/linkedin-cookies.txt`.

Discard closed jobs: MongoDB `{status: "closed"}`, remove from cache. Rate limit: 2-second pause every 10 requests.

**Display format** — show a rich table for user selection. For each job, query MongoDB for extra fields and display:
```
# | Tier | Score | AI | Company — Title (truncated)
  | Location | Remote | Seniority | Source | Stale?
```
Fields from MongoDB: `tier`, `score`/`quick_score`, `is_ai_job`, `ai_categories`, `source`, `linkedin_metadata.seniority_level`.
Run stale-check inline (LinkedIn auth cookies) and mark CLOSED/OPEN.
Present sorted list to user, ask which to proceed with.

---

## Routing (MANDATORY)

**All applications run sequentially in the main thread — no subagents.**
- `--count 1` or specific job_id → apply to one job (Steps 2–10)
- `--count N where N > 1` → apply to N jobs by repeating Steps 2–10 for each, one at a time

## Application Loop (main thread, sequential)

For each job selected, execute Steps 2–10 in order. Record `JOB_START=$(date +%s)` before Step 2 and `JOB_END=$(date +%s)` after Step 10.

### Step 2: Resolve CV Path
GDrive pattern: `{GDRIVE_CVS}/{COMPANY}/{Title}_{mongodb_id}/Taimoor Alam Resume.pdf`

Fallbacks: search company folder for subfolder containing the job_id, then fuzzy title match. If not found, ask user for path or skip.

### Step 3: Stage CV
Create a job-specific temp directory and copy the CV there:
```bash
mkdir -p /tmp/apply-jobs/{company}_{job_id}
cp "<cv_path>" /tmp/apply-jobs/{company}_{job_id}/resume.pdf
```
CV available at `/tmp/apply-jobs/{company}_{job_id}/resume.pdf`.

The job-specific directory prevents conflicts if multiple applications are staged simultaneously.

### Step 4: Open Job URL & Detect Portal
**Read `{MODULES}/portal-detection.md`** for the full playbook system.

1. Open the jobUrl via `tabs_create_mcp`
2. Detect portal type from URL
3. Check `data/portal-playbooks/` for an existing playbook match
4. **If playbook exists** → load it, use its selectors and scripts for all subsequent steps
5. **If LinkedIn** → skip analysis, use standard Easy Apply flow
6. **If no playbook** → run the JS analysis script from portal-detection.md to inspect HTML/CSS/JS framework, form structure, buttons, file inputs. Auto-generate a new playbook YAML and save it. Use the new playbook for this application.

This means every portal is only analyzed once. Future jobs on the same portal reuse the playbook instantly.

### Step 4b: Check for Closed Posting
After reading the page, scan for closure signals **before** attempting to apply:
- LinkedIn: red "No longer accepting applications" banner
- Any portal: "This job is closed", "Position filled", "Application deadline passed", "Job no longer available"

If detected: immediately set MongoDB `{status: "closed", closed_detected_at: now, closed_reason: "no longer accepting applications"}`, remove from cache, inform user, and ask if they want to continue to the next job. Do **not** proceed to Step 5.

### Step 5: Navigate to Apply
Find and click the Apply button. Handle redirects and LinkedIn Easy Apply multi-step modals.

**Login wall protocol (MANDATORY):**
If the portal shows a login/register wall before the application form:
1. Tell the user exactly what's needed: "**[Company] portal requires login.** Please log in or create an account at [URL], then say 'done' to continue."
2. **STOP and wait** — do not proceed, do not time out, do not skip to the next job.
3. Resume only after the user explicitly confirms (e.g. "done", "logged in", "continue").
4. After confirmation, re-check the tab — if still on login page, ask user again.

### Step 6: Fill Form (Batch Fill Protocol)

**SPEED RULE: NEVER read_page between individual field fills. Read once, fill all, verify once.**

For each form step (page), follow this protocol:

#### A) Known Portal (playbook has `batch_fill_scripts`)
1. **BATCH JS FILL**: Execute the playbook's batch script for this step via `javascript_tool`. Interpolate profile values into the script. ONE call fills all JS-fillable fields.
2. **PHYSICAL-ONLY FIELDS**: The batch script returns `needs_physical` array. Handle each with `computer` clicks using playbook's `dropdown_sequences` (e.g., Workday source field = 4 physical clicks, phone country = JS char search).
3. **VERIFY + SAVE**: `get_page_text` once to confirm all fills → click Save/Next/Submit.
4. **Budget**: ~5-7 tool calls per step. If >10, something is wrong — check playbook.

#### B) Unknown Portal (no playbook)
1. **READ ONCE**: `read_page filter=interactive depth=4` — get all fields, refs, labels.
2. **MATCH ALL**: In ONE reasoning pass, match every field to `question_cache` in profile. Build field map: `[{selector, value, method: "js"|"physical"}]`
3. **GENERATE + EXECUTE BATCH JS**: Create a dynamic fill script with `fillInput()` helper + all selectors. Execute ONE `javascript_tool` call.
4. **PHYSICAL-ONLY**: Handle remaining 0-3 items (dropdowns, checkboxes) with `computer` clicks.
5. **VERIFY + SAVE**: `get_page_text` once → Save/Next.
6. **Auto-generate playbook** from the discovered structure for next time.

#### Question Matching (for Application Questions steps)
Before LLM reasoning, match each question label against `question_cache` patterns in profile (case-insensitive substring match). 90%+ of questions resolve from cache. Only invoke reasoning for truly novel questions. After session, append new Q&A to cache (Step 12).

### Step 7: Upload CV
Use the playbook's `cv_upload` script. Default method: **AppleScript base64 injection** (works on ALL portals, no CORS).

1. Encode CV in Python: `base64.b64encode(open(cv_path,'rb').read()).decode()`
2. Inject via AppleScript with the playbook's JS template (finds `input[type="file"]`, sets files via DataTransfer)
3. Verify: `get_page_text` should show "successfully uploaded" or filename

**CRITICAL: NEVER inject placeholder or fake files.** If CV upload fails, explicitly tell the user: "CV was NOT uploaded. Please upload manually from: `/tmp/apply-jobs/{company}_{job_id}/resume.pdf`". Do not proceed to submit without a real CV attached.

### Step 8: Cover Letter (if needed)
**Read `{MODULES}/cover-letter.md`** only if a cover letter field is detected.

Generate from JD + pain points + profile. Show draft, get user approval.

### Step 9: Pre-Submit Review
**ALWAYS** show filled fields summary and ask: `SUBMIT? (yes/no/review-in-browser)`

### Step 10: Post-Submit
**Read `{MODULES}/edge-cases.md`** if any issues arise during the session.

On success: verify confirmation page, update MongoDB `{status: "applied", appliedOn: now, application_method: "browser_automated"}`, log to `application-log.yaml`, save portal playbook if new, **remove this job from `data/apply-jobs-cache.json`**. Clean up temp dir.

On skip/failure: also **remove from cache** so it doesn't reappear.

---

## After all jobs in batch

### Step 11: Next Batch
If more jobs remain: show progress, ask to continue, loop back to Step 1.

Print session summary: applied/skipped/failed counts, new answers learned.

### Step 12: Post-Session Self-Improvement (ALWAYS run)

Active feedback loop — don't just log, **update the skill artifacts**:

1. **METRICS**: Count tool calls per job and per step. Compare against budget:
   | Portal | Budget |
   |--------|--------|
   | Workday | 28 |
   | Greenhouse | 10 |
   | Ashby | 6 |
   | LinkedIn Easy Apply | 10 |
   | Unknown | 20 |
   
   If any job exceeded 2x budget → investigate and log root cause.

2. **QUESTION CACHE UPDATE**: For every question answered this session:
   - If not in `question_cache` → append new entry with patterns + answer + type
   - If user corrected an answer → update existing entry
   - Never auto-update salary, nationality, or visa answers (user-controlled via "seed →")
   - Mark LLM-inferred answers as `confidence: "inferred"` vs user-provided as `confidence: "confirmed"`

3. **PLAYBOOK PATCHES**: For every interaction that took >3 attempts:
   - Identify root cause (wrong selector, JS vs physical mismatch, new form layout)
   - Update the playbook's `batch_fill_scripts` or `dropdown_sequences`
   - Add to `known_issues` if it's a new portal quirk
   - Only update selectors that were **verified working** in this session

4. **NEW PORTAL PLAYBOOK**: If new portal encountered:
   - Save auto-generated playbook to `data/portal-playbooks/`
   - Include `batch_fill_scripts` from the dynamic script used this session
   - Document `needs_physical` fields

5. **SPEED REGRESSION CHECK**: If tool calls for a known portal exceeded budget by >50%:
   - Batch scripts may be stale (selectors changed)
   - Flag: "Portal {X} needs batch script re-validation"

6. **TIMER REPORT**: Compute from `SESSION_START` and per-job timestamps:
   ```
   SESSION_END=$(date +%s)
   Total: $((SESSION_END - SESSION_START)) seconds
   Per job: {company}: {seconds}s ({tool_calls} calls)
   ```
   Print the timing report to the user. Flag any job that took >5 min.

7. **LOG**: Append structured entry to `{MODULES}/suggestions.md`:
   ```yaml
   ## Session: {date} — {applied}/{skipped}/{failed}
   ### Timing
   total_session_seconds: {N}
   per_job:
     - {company}: {seconds}s, {tool_calls} calls, portal: {type}
   ### Metrics
   tool_calls_total: {N}
   fields_from_cache: {N}
   fields_needed_user: {N}
   ### Failed Interactions
   - field: {name}, portal: {type}, attempts: {N}, fix_applied: {description}
   ### Artifacts Updated
   - {file}: {what changed}
   ```

**Budget for Step 12 itself**: <10 tool calls (3-4 Edit calls + 1 append).

### Step 13: Cleanup
Delete all temp files created during this session:
```bash
rm -rf /tmp/apply-jobs/
```
Also kill any lingering file servers: `pkill -f "python3 -m http.server 18923" 2>/dev/null || true`

---

## Human-in-the-Loop Triggers
- Final submit → always confirm (one job at a time even in batch mode)
- Login / account creation → user handles manually
- CAPTCHA → user solves
- Unknown form questions → ask user (collect all unknowns from parallel agents before starting Phase 3)
- Cover letter → show draft for approval
- Any 2 consecutive failures → ask user for help or skip

---

## Known Painpoints & Rules (learned from sessions)

1. **Workday 2-level source dropdown is the #1 time waster.** Use `source_fast` (pick first sub-option, 3-5 clicks). NEVER scroll through virtual list to find LinkedIn — any value is fine for the user.
2. **All applications run in the main thread — no subagents.** Sequential only. CV upload, Bash, AppleScript all require main thread. Never delegate to a subagent.
3. **Login walls: PAUSE and WAIT for user.** Tell user exactly what URL/portal needs login, then stop and wait for "done". Do not skip to next job. Do not time out.
4. **CV upload is ALWAYS AppleScript base64 injection from main thread.** Never attempt to upload via JS alone. Read the staged `.b64` file in Python, build the AppleScript, run via Bash. If upload fails: "CV not uploaded, please upload manually from {path}."
5. **NEVER inject placeholder/fake CV files.** If upload fails, tell the user explicitly.
6. **Bash output collapses in Claude Code CLI.** Tables with 20+ rows get truncated. Always output tables as markdown text in the response, NOT via Bash print.
7. **Field-by-field interaction = 150+ tool calls per app.** Always use batch fill protocol: read once → JS fill all → verify once. Budget: Workday=28, Greenhouse=10, Ashby=6, LinkedIn=10.
8. **Workday `data-automation-id` selectors vary across instances.** Discover actual input IDs via JS before filling. Use `id` attribute, not `data-automation-id`.
9. **LinkedIn stale-check needs auth cookies.** Use `data/linkedin-cookies.txt` (Netscape format). If expired, ask user to refresh.
10. **Job list display must show rich info.** Always show: ID (first 10 chars), Tier, Score, AI flag, Remote status, Company, Role, Location, Source, and Stale check. Output as markdown table (not Bash).
11. **Timer everything.** Record SESSION_START, per-job timestamps, tool call counts. Report at end. Flag any job >5 min or >2x tool call budget.
