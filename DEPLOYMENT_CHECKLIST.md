# Deployment Checklist

This checklist tracks deployment steps for the VPS runner and Vercel frontend.

## ✅ Completed Today (Nov 26, 2025)

### Backend Fixes
- [x] Fixed Layer 6 API key mismatch (Anthropic vs OpenAI)
- [x] Enhanced MongoDB persistence to save full pipeline state
- [x] Auto-update job status to "ready for applying" on completion
- [x] Added structured logging with run_id tagging
- [x] Export pipeline state to JSON for runner consumption
- [x] All runner tests passing (18/18)
- [x] All frontend tests passing (32/32)

### Commits Created
1. `315a4707` - feat(logging): Add centralized structured logging system
2. `c020e320` - feat(workflow): Integrate structured logging and state export
3. `04c32c1e` - feat(runner): Complete pipeline state persistence and API fixes
4. `0209dd70` - test/docs: Update tests and document pipeline fixes

## ⏳ Pending Deployment Steps

### VPS Deployment (72.61.92.76)

1. **SSH into VPS**
   ```bash
   ssh root@72.61.92.76
   ```

2. **Pull latest changes**
   ```bash
   cd /path/to/job-search
   git pull origin main
   ```

3. **Verify environment variables**
   ```bash
   # Check .env or systemd service file has:
   - MONGODB_URI=mongodb://localhost:27017/jobs
   - ANTHROPIC_API_KEY=sk-ant-...  # For CV generation
   - OPENAI_API_KEY=sk-...  # For other layers (optional if using Anthropic everywhere)
   - FIRECRAWL_API_KEY=...
   - LOG_LEVEL=INFO
   - LOG_FORMAT=simple
   ```

4. **Restart runner service**
   ```bash
   systemctl restart runner
   systemctl status runner
   journalctl -u runner -f  # Watch logs
   ```

5. **Verify health endpoint**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"healthy","active_runs":0,"max_concurrency":3,...}
   ```

### Vercel Frontend Deployment

1. **Set environment variables in Vercel dashboard**
   - `LOGIN_PASSWORD` - Frontend auth password
   - `FLASK_SECRET_KEY` - Session secret
   - `MONGODB_URI` - `mongodb://72.61.92.76:27017/jobs` (or Atlas URI)
   - `RUNNER_URL` - `http://72.61.92.76:8000`
   - `RUNNER_API_SECRET` - JWT secret for runner auth

2. **Trigger deployment**
   ```bash
   git push origin main
   # Vercel will auto-deploy
   ```

3. **Verify deployment**
   - Visit Vercel URL
   - Login with LOGIN_PASSWORD
   - Check health indicators (VPS, MongoDB, n8n)
   - Test "Process Job" button on a job

## 🧪 End-to-End Testing

After deployment, test the full flow:

1. **Select a job in UI**
   - Navigate to job detail page
   - Click "Process Job" button

2. **Monitor execution**
   - Watch SSE log stream in UI
   - Verify progress bar updates
   - Check VPS logs: `journalctl -u runner -f`

3. **Verify persistence**
   ```bash
   # On VPS, check MongoDB
   mongosh "mongodb://localhost:27017/jobs"
   db['level-2'].findOne({_id: ObjectId("JOB_ID_HERE")}, {
     pain_points: 1,
     fit_score: 1,
     primary_contacts: 1,
     status: 1
   })
   # Should show all pipeline results
   ```

4. **Verify UI updates**
   - Page should auto-reload after 2 seconds
   - Pain Points section should appear
   - Fit Analysis section should show score/rationale
   - Key Contacts section should show primary/secondary contacts
   - Status should change to "ready for applying"
   - Progress bar should show 100%

## 📝 Post-Deployment Tasks

- [ ] Run full end-to-end test with real job
- [ ] Monitor VPS logs for errors
- [ ] Check MongoDB for proper state persistence
- [ ] Update missing.md to remove completed items
- [ ] Document any new issues in plans/

## 🚨 Rollback Plan

If issues occur:

```bash
# On VPS
git log --oneline -10  # Find previous working commit
git checkout <commit-hash>
systemctl restart runner

# On Vercel
# Use Vercel dashboard to rollback to previous deployment
```

## 📊 Success Metrics

After deployment, verify:
- [ ] All health endpoints return "healthy"
- [ ] Pipeline completes without errors
- [ ] MongoDB contains all pipeline state fields
- [ ] Job status updates to "ready for applying"
- [ ] Frontend displays all pipeline results
- [ ] Logs show structured messages with run_id tags
- [ ] No API key errors in logs
