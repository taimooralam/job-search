# Pipeline Completion Issues & Fixes

## Issues Identified (From Screenshot)

### ✅ Fixed - Frontend Issues

1. **Progress Bar Stuck at 0%**
   - **Problem**: Progress bar showed 0% even when pipeline completed
   - **Root Cause**: `data.progress` was undefined/null after completion
   - **Fix**: Default to 100% (1.0) when status is 'completed' or 'failed'
   - **Commit**: `97c76030`

2. **New Fields Not Showing After Processing**
   - **Problem**: pain_points, fit_score, contacts fields don't appear even after pipeline completes
   - **Root Cause**: Page doesn't reload to fetch updated job document from MongoDB
   - **Fix**: Auto-reload page 2 seconds after completion with visual feedback
   - **Commit**: `97c76030`

---

## ⚠️ Outstanding Backend Issues (Require VPS Changes)

### 1. OpenAI API Key Error in Layer 6 (Generator)

**Error from logs:**
```
Layer 6 (Generator) failed: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-ant-a***...DQAA. You can find your API key at https://platform.openai.com/account/api-keys.', 'type': 'invalid_request_error', 'code': 'invalid_api_key', 'param': None}}
```

**Issue**: The runner service on VPS is configured with an **Anthropic API key** (sk-ant-...) but Layer 6 is trying to use it with **OpenAI's API**.

**Root Cause**:
- `src/layer6/generator.py` uses `ChatOpenAI` from LangChain
- The OPENAI_API_KEY environment variable is set to an Anthropic key instead

**Fix Required** (on VPS):
```bash
# SSH into VPS
ssh root@72.61.92.76

# Edit the runner service environment
vim /etc/systemd/system/runner.service
# OR
vim ~/.env  # If runner loads from .env

# Change:
OPENAI_API_KEY=sk-ant-...  # ❌ Wrong!

# To valid OpenAI key:
OPENAI_API_KEY=sk-proj-...  # ✅ Correct

# Restart runner service
systemctl restart runner
```

**Alternative**: Switch Layer 6 to use Anthropic (Claude) instead:
```python
# In src/layer6/generator.py
from langchain_anthropic import ChatAnthropic  # Instead of ChatOpenAI

self.llm = ChatAnthropic(
    model="claude-sonnet-4",
    api_key=Config.ANTHROPIC_API_KEY  # Use Anthropic key
)
```

---

### 2. Job Status Not Updating After Completion

**Problem**: Job status remains "not processed" even after pipeline completes successfully.

**Expected Behavior**: Status should change to "ready for applying" after successful processing.

**Current Behavior**: Status field is never updated by the runner service.

**Fix Required** (in runner service code):

The runner service needs to update the job document in MongoDB after completion:

```python
# In runner service (likely in VPS codebase)
async def _finalize_run(self, run_id: str, job_id: str, state: dict, status: str):
    """Finalize pipeline run and update job status."""

    # Update job document with new status
    if status == 'completed':
        await db['level-2'].update_one(
            {'_id': ObjectId(job_id)},
            {
                '$set': {
                    'status': 'ready for applying',  # ← Add this
                    'pain_points': state.get('pain_points'),
                    'fit_score': state.get('fit_score'),
                    'fit_rationale': state.get('fit_rationale'),
                    'fit_category': state.get('fit_category'),
                    'primary_contacts': state.get('primary_contacts'),
                    'secondary_contacts': state.get('secondary_contacts'),
                    'updatedAt': datetime.utcnow()
                }
            }
        )
```

**Available Status Values** (from `frontend/app.py`):
- `"not processed"` ← Default
- `"marked for applying"` ← Manually set by user
- `"ready for applying"` ← **Should be set after successful pipeline**
- `"to be deleted"`
- `"discarded"`
- `"applied"`
- `"interview scheduled"`
- `"rejected"`
- `"offer received"`

---

### 3. Pipeline State Not Persisting to MongoDB

**Problem**: After pipeline completes, the job document doesn't contain the new fields (pain_points, fit_score, contacts).

**Root Cause**: The runner service may be:
1. Not saving state back to MongoDB after completion
2. Saving to wrong collection (e.g., level-3 instead of level-2)
3. Using wrong MongoDB URI
4. Failing silently during state persistence

**Debug Steps**:

```bash
# 1. SSH into VPS and check logs
ssh root@72.61.92.76
journalctl -u runner -n 100 --no-pager

# 2. Check MongoDB connection in runner
# Look for connection errors or wrong database/collection

# 3. Verify job document after processing
mongosh "mongodb://localhost:27017/jobs"
db['level-2'].findOne(
  {_id: ObjectId("JOB_ID_HERE")},
  {pain_points: 1, fit_score: 1, primary_contacts: 1}
)
# Should show these fields after processing
```

**Fix Required** (in runner service):

Ensure state is persisted after **each layer** completes:

```python
# In runner service pipeline execution
async def execute_pipeline(job_id: str):
    # ... execute layers ...

    # After each layer, save state
    await save_state_to_mongo(job_id, state)

# Function to save state
async def save_state_to_mongo(job_id: str, state: dict):
    """Persist complete state to MongoDB."""
    mongo_updates = {
        'pain_points': state.get('pain_points'),
        'strategic_needs': state.get('strategic_needs'),
        'fit_score': state.get('fit_score'),
        'fit_rationale': state.get('fit_rationale'),
        'fit_category': state.get('fit_category'),
        'primary_contacts': state.get('primary_contacts'),
        'secondary_contacts': state.get('secondary_contacts'),
        'company_research': state.get('company_research'),
        'role_research': state.get('role_research'),
        'selected_stars': state.get('selected_stars'),
        'updatedAt': datetime.utcnow()
    }

    # Remove None values
    mongo_updates = {k: v for k, v in mongo_updates.items() if v is not None}

    await db['level-2'].update_one(
        {'_id': ObjectId(job_id)},
        {'$set': mongo_updates}
    )
```

---

## Testing Checklist

After applying VPS fixes:

- [ ] OpenAI API key is valid (test: `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`)
- [ ] Runner service restarts successfully
- [ ] Process a job and verify:
  - [ ] Layer 6 (Generator) completes without errors
  - [ ] Job status changes to "ready for applying"
  - [ ] Pain points appear in detailed view
  - [ ] Fit analysis shows score and rationale
  - [ ] Primary and secondary contacts are displayed
  - [ ] Progress bar shows 100% at completion
  - [ ] Page auto-reloads and shows new data

---

## Quick Fix Summary

**Frontend (✅ Complete):**
```bash
git pull origin main  # Get latest frontend fixes
# Progress bar and auto-reload now work
```

**Backend (⚠️ VPS Configuration Required):**
```bash
# 1. Fix OpenAI API key
vim ~/.env  # or /etc/systemd/system/runner.service
# Set valid OPENAI_API_KEY=sk-proj-...

# 2. Restart runner
systemctl restart runner

# 3. Test pipeline on a job
# Check that fields persist and status updates
```

---

## Alternative: Disable Layer 6 Temporarily

If you can't fix the OpenAI key immediately, you can disable Layer 6 (CV Generator) and still see the other pipeline fields:

```python
# In runner service pipeline configuration
SKIP_LAYERS = [6]  # Skip CV generation for now
```

This allows you to verify that Layers 1-5 are working correctly and persisting data, while you fix the API key issue separately.
