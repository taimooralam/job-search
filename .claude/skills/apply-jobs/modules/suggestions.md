# Run Suggestions Log

This file is updated after every `/apply-jobs` session. It captures issues, optimizations, and improvements to feed back into the skill.

## Format

Append a new entry after each session:

```yaml
## Session: {ISO date} — {N applied}/{M skipped}/{K failed}

### Issues
- {description of problem} → {how it was resolved or workaround}

### Token Optimization
- {what consumed excessive tokens — e.g. "full page read on Workday returned 50k chars"}
- {suggestion — e.g. "use targeted CSS selector instead of full read_page"}

### Quality Improvements
- {what could be better — e.g. "salary field auto-filled 'negotiable' but portal expected a number"}
- {suggestion — e.g. "detect numeric-only salary fields and ask user for a number"}

### Cost Optimization
- {what was expensive — e.g. "cover letter generation used Opus, could use Sonnet"}
- {suggestion}

### Portal Learnings
- {portal}: {what worked, what didn't, quirks discovered}

### Code Execution Problems
- {Python/JS errors encountered and fixes applied}

### New Patterns Discovered
- {reusable patterns — e.g. "Greenhouse always has input[type=file] with accept=.pdf,.doc"}
```

---

*Entries below are appended automatically after each session.*

## Session: 2026-04-05 — 1 applied / 5 skipped (closed) / 0 failed

### Issues
- **Ashby SPA blank screenshots**: Viewport >700px renders content off-screen in screenshot tool. Fix: always `resize_window` to 700px before capturing Ashby pages. ✅ DONE — in ashby.yaml viewport_fix
- **Submit button not advancing**: Previous JS `.click()` calls weren't progressing the form. Fix: physical click via `computer` at viewport coordinates after `scrollIntoView`. ✅ DONE — in batch fill protocol
- **CORS blocking CV upload**: `fetch('http://localhost:18923')` blocked from external domains. Fix: AppleScript base64 injection as default method. ✅ DONE — in all playbooks cv_upload
- **Phone country dropdown conflict**: Typing "Germany" into phone country selector triggered location autocomplete. Fix: enter full international number directly. ✅ DONE — in workday.yaml phone_country_germany sequence
- **File picker opens at wrong location**: macOS native file picker uncontrollable. Fix: AppleScript b64 injection bypasses file picker entirely. ✅ DONE — default CV method
- **Salary field**: Always "1" in mandatory salary fields. ✅ DONE — in profile mandatory_field_value + question_cache

### Token Optimization
- Batch HTTP stale-check at start saves time vs browser closures. ✅ DONE — in skill Step 1 with LinkedIn cookies auth
- Reading master-cv once to answer unknown questions avoids back-and-forth. ✅ DONE — question_cache in profile (25 entries)

### Quality Improvements
- Visa sponsorship context-aware: "No" for EU, "Yes" for non-EU. ✅ DONE — in profile work_authorization + question_cache
- Ashby `scrollIntoView` + `getBoundingClientRect()` check. ✅ DONE — in ashby.yaml automation_script

### Portal Learnings
- **Ashby**: Playbook saved. ✅ DONE — batch_fill_scripts added
- **Closed posting detection**: Step 4b in skill. ✅ DONE

### Code Execution Problems
- `dotenv.load_dotenv()` needs explicit path. ✅ NOTED — in playbook scripts
- `await` not valid in JS tool (sync context). ✅ NOTED — batch scripts avoid async

### New Patterns Discovered
- React setter pattern. ✅ DONE — in all batch_fill_scripts
- HTMLTextAreaElement.prototype for textarea. ✅ DONE — in batch scripts
- URL check for submit success. ✅ DONE — in all playbook success_indicators
- `elementFromPoint` for off-screen detection. ✅ DONE — in workday source_linkedin_slow (scrollIntoView before click)

---

## Session: 2026-04-06 — 3 applied (Alcoa, CSG, IQVIA) / 0 skipped / 0 failed

### Issues
- **Workday source field JS .click() silently fails** ✅ DONE — source_fast strategy in workday.yaml (pick first sub-option, 5 calls max)
- **Source field is 2-level hierarchy** ✅ DONE — dropdown_sequences in workday.yaml
- **Family name prefix mis-click** ✅ DONE — use element id ('hereditary') to distinguish, noted in batch_fill_scripts
- **Phone country virtual scroll** ✅ DONE — char-by-char JS in workday.yaml phone_country_germany
- **Escape key doesn't close phone dropdown** ✅ DONE — verify via [aria-label="items selected"]
- **T&C consent is checkbox not button** ✅ DONE — Type-C in dropdown_strategy + voluntary_disclosures batch script
- **Text inputs need click+type** ✅ DONE — noted in known_issues, batch scripts use native setter
- **CV upload required in My Experience** ✅ DONE — noted in known_issues
- **Alcoa salary 150000 instead of 1** ✅ DONE — question_cache always returns "1"
- **IQVIA auto-submitted** ✅ DONE — noted in known_issues, verify URL for completed/application

### Token Optimization
- **Workday playbook** now saved — next Workday sessions reuse known patterns without re-discovering.
- **read_page filter=interactive depth=4** sufficient for Workday — don't use filter=all unless debugging source field structure.
- **Dropdown option enumeration**: use `Array.from(document.querySelectorAll('[role="option"]')).map(o => o.textContent.trim())` once to see all options, then click target by exact text.

### Quality Improvements
- Profile: German language level corrected B2 → B1.
- Profile: `voluntary_disclosures` section added (Male, no disability, prefer not to say, not US veteran).
- Profile: `notice_period` = "3 months" already present, confirmed as "3 calendar months" in Workday dropdowns.
- Salary "1" rule: already in profile as `mandatory_field_value`, now also documented in Workday playbook.
- Nationality: always German only — profile already has `nationality: "German"`. Do not mention Pakistani nationality anywhere.

### Portal Learnings
- **Workday Type-A dropdowns** (Yes/No, degree, gender, notice period): `computer left_click ref=` to open → JS find+click `[role="option"]` by exact text → closes automatically. Fast and reliable.
- **Workday Type-B multi-select** (source field): physical click only, two levels. Verification: `document.body.innerText` contains "Minimized LinkedIn".
- **Workday Type-C consent checkboxes**: `document.querySelector('input[type="checkbox"]').click()` or `computer left_click ref=<checkbox_ref>`. NOT buttons.
- **EU vs US Voluntary Disclosures**: US portals (Alcoa) have full EEO (gender/disability/veteran). EU portals (IQVIA, CSG) may only have gender + T&C or T&C only. Check page content each time.
- **Playbook created**: `data/portal-playbooks/workday.yaml` — covers all 3 instances with dropdown strategy, CV upload, field mapping, known issues.

### Code Execution Problems
- AppleScript base64 injection works on all 3 Workday tenants (alcoa.wd5, csgi.wd5, iqvia.wd1).
- Python `col.update_one({'_id': ObjectId(id)}, {'$set': {...}})` worked for MongoDB updates on all 3 jobs.

### New Patterns Discovered
- `Array.from(document.querySelectorAll('[role="option"]')).find(o => o.textContent.trim() === 'TARGET')?.click()` — standard Workday Type-A dropdown selection.
- Workday success URL pattern: `*/jobTasks/completed/application*` — check tab URL to confirm submission.
- `document.querySelector('[aria-label="items selected"]').textContent.trim()` — canonical way to verify phone country selection in Workday.
- Char-by-char input simulation needed for virtual-scroll search fields: keydown + keypress + native setter (append char) + input event + keyup — per character.

---

## Session: 2026-04-06 (dry-run batch) — 3 applied / 0 skipped / 0 failed

### Timing
total_session_seconds: ~1200 (20 min for dry-run + submit)
per_job:
  - CrowdStrike: ~900s (15 min), ~40 calls, portal: workday (crowdstrike.wd5) — source dropdown ate 15+ calls
  - Zyte: ~750s (12.5 min), 92 calls, portal: linkedin_easy_apply_workable — subagent, many custom questions
  - HR POD: ~850s (14 min), 118 calls, portal: manatal — subagent, shadow DOM, CV placeholder issue

### Failed Interactions
- field: source_dropdown, portal: workday, attempts: 8, fix_applied: "Added source_fast strategy (pick first sub-option, no scrolling)"
- field: cv_upload, portal: manatal, attempts: 3, fix_applied: "Moved CV upload to main thread Phase 3 — subagents cannot use Bash/AppleScript"
- field: cv_upload, portal: linkedin_workable, attempts: 2, fix_applied: "Same — subagent used LinkedIn's stored resume instead of custom CV"
- field: date_from_spinbutton, portal: workday, attempts: 2, fix_applied: "native setter doesn't trigger Workday date validation — must physical click + type"

### Key Learnings
- Subagents CANNOT do CV upload (no Bash for AppleScript). All CV uploads must happen in main thread.
- NEVER inject placeholder files — tell user "CV not uploaded" and provide path.
- Workday source dropdown: "source_fast" (pick first available sub-option) is 5 calls vs "source_linkedin_slow" (15+ calls with virtual scroll). Default to fast.
- Workday date fields need physical click + type, not native setter alone.
- Workday `data-automation-id` selectors vary between instances — use `id` attribute instead (e.g., `name--legalName--firstName`).
- Timer tracking added to skill for future sessions.

### Artifacts Updated
- workday.yaml: Added source_fast dropdown sequence as default, demoted source_linkedin to source_linkedin_slow
- skill.md: Timer tracking (Step 0), CV upload in Phase 3 main thread, never-placeholder rule, subagent budget constraint
- applicant-profile.yaml: question_cache expanded to 25 entries
- All 4 playbooks: batch_fill_scripts added

