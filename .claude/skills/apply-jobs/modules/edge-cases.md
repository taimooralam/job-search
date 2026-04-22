# Edge Cases & Error Recovery

Read this module when issues arise during application.

## CAPTCHA
```
CAPTCHA DETECTED. Please solve it in the browser.
Type 'done' when passed.
```

## Login Required
1. Check `known_accounts` in applicant profile
2. Ask: "This portal requires login. Do you have an account? (y/n)"
3. "Please log in manually. Type 'done' when ready."

## Multi-Step Forms (Workday, LinkedIn Easy Apply)
Fill each page → click Next → read new page → repeat. Pause for review on final page only.

## Popups & Modals
- Cookie consent → accept
- Login prompt → ask user
- **NEVER trigger alert/confirm/prompt JS dialogs** — blocks the browser extension

## Job Already Applied
Page shows "You've already applied" → inform user, update MongoDB to "applied", skip.

## Job Expired
Page shows "no longer available" → inform user, update MongoDB `{status: "discarded", discard_reason: "expired"}`, skip.

## Page Won't Load
After 2 attempts: inform user, log failure, skip. Offer: "Try opening manually? {url}"

## Form Validation Errors
Read error messages, try to fix fields. If unfixable → ask user.

## General Error Recovery
After 2 failures on same step:
```
Trouble with: {issue}
URL: {current URL}
Tried: {what}
Result: {what happened}

Options:
1. Try different approach
2. Help in browser (type 'done')
3. Skip this job
4. Abort session
```

## Post-Submit Verification
Look for: "Thank you", "Application received", "Successfully submitted", confirmation email mention.

## MongoDB Update on Success
```python
col.update_one({"_id": ObjectId(job_id)}, {"$set": {
    "status": "applied",
    "appliedOn": datetime.utcnow(),
    "application_method": "browser_automated",
    "application_portal": portal_type,
}})
```

## Application Log
Append to `data/application-log.yaml`:
```yaml
- job_id: "{id}"
  company: "{company}"
  title: "{title}"
  portal: "{portal}"
  applied_at: "{ISO timestamp}"
  cv_path: "{path}"
  cover_letter: true/false
  notes: "{issues}"
```

## Cleanup
```bash
kill $FILE_SERVER_PID 2>/dev/null
rm -rf /tmp/apply-jobs-server
```
