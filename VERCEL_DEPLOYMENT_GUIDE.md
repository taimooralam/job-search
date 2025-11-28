# Vercel Deployment Guide - PDF Export Fix

**Created**: 2025-11-28
**Issue**: PDF export failing with 503 "PDF service unavailable" error
**Root Cause**: Missing `RUNNER_API_SECRET` environment variable in Vercel

---

## Quick Fix (If You Just Want PDF Export Working NOW)

### Step 1: Get the Runner API Secret from VPS

SSH into your VPS and get the secret:

```bash
ssh root@72.61.92.76
cd /root/job-runner
cat .env | grep RUNNER_API_SECRET
```

Copy the value after `RUNNER_API_SECRET=` (e.g., `abc123def456...`)

### Step 2: Add to Vercel Environment Variables

1. Go to: https://vercel.com/ala0001t/job-search/settings/environment-variables
2. Click "Add New"
3. Configure:
   - **Key**: `RUNNER_API_SECRET`
   - **Value**: Paste the secret from Step 1
   - **Environments**: Check all three (Production, Preview, Development)
4. Click "Save"

### Step 3: Redeploy

1. Go to: https://vercel.com/ala0001t/job-search
2. Click "Deployments" tab
3. Find the latest deployment
4. Click "..." menu → "Redeploy"
5. Wait ~2-3 minutes for deployment to complete

### Step 4: Test PDF Export

1. Open: https://job-search-inky-sigma.vercel.app
2. Navigate to any job detail page
3. Click "Export PDF" button
4. PDF should download successfully

**Expected Result**: PDF downloads with filename like `CV_CompanyName_RoleTitle.pdf`

---

## Full Environment Variable Checklist

### Critical Variables (MUST SET)

| Variable | Description | How to Get | Where to Set |
|----------|-------------|------------|--------------|
| `MONGODB_URI` | MongoDB connection string | MongoDB Atlas dashboard | Vercel env vars |
| `FLASK_SECRET_KEY` | Session encryption key | Generate: `python -c "import os; print(os.urandom(24).hex())"` | Vercel env vars |
| `LOGIN_PASSWORD` | UI authentication password | Choose strong password | Vercel env vars |
| `RUNNER_URL` | VPS runner service URL | Default: `http://72.61.92.76:8000` | Vercel env vars |
| **`RUNNER_API_SECRET`** | **Runner authentication token** | **From VPS `/root/job-runner/.env`** | **Vercel env vars** |

### Optional Variables

| Variable | Description | Default | Where to Set |
|----------|-------------|---------|--------------|
| `FLASK_ENV` | Flask environment | `production` | Vercel env vars |
| `FLASK_DEBUG` | Debug mode | `false` | Vercel env vars |

---

## Troubleshooting

### PDF Export Still Fails After Adding RUNNER_API_SECRET

**Check 1: Variable is Set Correctly**
```bash
# Verify in Vercel dashboard that:
# - Variable name is exactly: RUNNER_API_SECRET (no typos)
# - Value matches VPS .env file exactly (no extra spaces)
# - All 3 environments are checked (Production, Preview, Development)
```

**Check 2: Redeploy Triggered Environment Refresh**
```bash
# Vercel doesn't reload env vars until redeployment
# Force redeploy:
# 1. Make any small change to code (e.g., add comment to README.md)
# 2. Push to GitHub
# 3. Vercel will auto-deploy
# OR use Redeploy button in Vercel dashboard
```

**Check 3: Runner Service is Healthy**
```bash
# Test runner service directly
curl -H "Authorization: Bearer YOUR_SECRET_HERE" \
  http://72.61.92.76:8000/health

# Expected: {"status":"healthy","active_runs":0,...}
# If connection refused: VPS runner service is down
# If 401 Unauthorized: Secret mismatch
```

**Check 4: Check Vercel Logs**
```bash
# View deployment logs in Vercel dashboard
# Look for:
# - "RUNNER_API_SECRET not set" warnings
# - "Authentication failed" errors
# - "Failed to connect to runner service" errors
```

### Error: "Authentication failed. Please contact support."

**Cause**: `RUNNER_API_SECRET` mismatch between Vercel and VPS

**Solution**:
1. SSH to VPS: `ssh root@72.61.92.76`
2. Check VPS secret: `cat /root/job-runner/.env | grep RUNNER_API_SECRET`
3. Compare with Vercel env var (Settings → Environment Variables)
4. Ensure they match EXACTLY (no trailing spaces, no quotes)
5. If different, update Vercel to match VPS
6. Redeploy

### Error: "PDF service unavailable. Please try again later."

**Cause**: Cannot connect to VPS runner service

**Check 1: VPS Runner is Running**
```bash
ssh root@72.61.92.76
cd /root/job-runner
docker compose ps

# Expected: runner service shows "Up (healthy)"
# If not running: docker compose up -d
```

**Check 2: Port 8000 is Accessible**
```bash
# From local machine
curl -v http://72.61.92.76:8000/health

# Expected: HTTP 200 OK with JSON response
# If connection timeout: VPS firewall blocking port
# If connection refused: Service not running
```

**Check 3: PDF Service is Running**
```bash
ssh root@72.61.92.76
cd /root/job-runner
docker compose ps pdf-service

# Expected: pdf-service shows "Up (healthy)"
# Check logs: docker compose logs pdf-service
```

### Error: "PDF generation timed out (>30s). Please try again."

**Cause**: PDF generation taking longer than 30 seconds

**Solutions**:
1. **Reduce CV complexity** - Large documents with many images take longer
2. **Check VPS resources**:
   ```bash
   ssh root@72.61.92.76
   htop  # Check CPU/memory usage
   docker stats  # Check container resource usage
   ```
3. **Check PDF service logs**:
   ```bash
   docker compose logs pdf-service | tail -50
   # Look for Playwright timeout errors
   ```

---

## Architecture Overview

Understanding the request flow helps debug issues:

```
User Browser
  ↓ Click "Export PDF"
  ↓
Frontend JavaScript (cv-editor.js)
  ↓ POST /api/jobs/{id}/cv-editor/pdf
  ↓ credentials: 'same-origin' (sends session cookie)
  ↓
Frontend Flask (app.py:916)
  ↓ @login_required decorator checks session
  ↓ Reads RUNNER_URL from env (default: http://72.61.92.76:8000)
  ↓ Reads RUNNER_API_SECRET from env (CRITICAL - must match VPS)
  ↓ POST http://72.61.92.76:8000/api/jobs/{id}/cv-editor/pdf
  ↓ Authorization: Bearer {RUNNER_API_SECRET}
  ↓
VPS Runner Service (runner_service/app.py:528)
  ↓ Depends(verify_token) - validates Bearer token
  ↓ Fetches cv_editor_state from MongoDB
  ↓ Sanitizes margins, migrates cv_text if needed
  ↓ POST http://pdf-service:8001/cv-to-pdf
  ↓ Payload: {tiptap_json, documentStyles, company, role}
  ↓
VPS PDF Service (pdf_service/app.py)
  ↓ Converts TipTap JSON to HTML
  ↓ Uses Playwright to render HTML in Chromium
  ↓ Generates PDF binary
  ↓ Returns PDF with Content-Disposition header
  ↓
VPS Runner Service
  ↓ Streams PDF back to frontend
  ↓
Frontend Flask
  ↓ Streams PDF to user browser
  ↓
User Browser
  ✓ PDF downloads with filename
```

**Key Failure Points**:
1. **Frontend → Runner**: Missing RUNNER_API_SECRET → 401 Unauthorized
2. **Runner → PDF Service**: PDF service down → 503 Service Unavailable
3. **PDF Service**: Playwright failure → 500 Internal Server Error

---

## Verification Steps

After deploying fixes, verify each step:

### 1. Verify Environment Variable is Set

```bash
# In Vercel dashboard:
# Settings → Environment Variables → Search for "RUNNER_API_SECRET"
# Should show:
# - RUNNER_API_SECRET = ******* (masked value)
# - Environments: Production, Preview, Development
```

### 2. Verify Deployment Picked Up New Env Var

```bash
# In Vercel Deployments tab:
# Latest deployment should show "Ready" status
# Build logs should not show "RUNNER_API_SECRET not set" warnings
```

### 3. Verify Runner Service is Accessible

```bash
# Test from local machine
curl -H "Authorization: Bearer $(cat /root/job-runner/.env | grep RUNNER_API_SECRET | cut -d= -f2)" \
  http://72.61.92.76:8000/health

# Expected: {"status":"healthy",...}
```

### 4. Verify PDF Export Works End-to-End

```bash
# 1. Open frontend: https://job-search-inky-sigma.vercel.app
# 2. Log in with LOGIN_PASSWORD
# 3. Navigate to any job detail page
# 4. Click "Export PDF" button in CV editor
# 5. Wait 5-10 seconds
# 6. PDF should download automatically

# Check browser console (F12) for errors
# Network tab should show:
# - POST /api/jobs/{id}/cv-editor/pdf
# - Status: 200 OK
# - Response type: application/pdf
```

### 5. Verify Logs Show No Errors

```bash
# Vercel logs (Functions tab)
# Should show:
# - "PDF generation request for job {id} - authentication configured"
# - "Requesting PDF generation from http://72.61.92.76:8000/..."
# - "Runner service responded with status 200"
# - "PDF generated successfully for job {id}, filename: CV_..."

# Should NOT show:
# - "RUNNER_API_SECRET not set"
# - "Authentication failed"
# - "Failed to connect to runner service"
```

---

## Security Notes

### RUNNER_API_SECRET Best Practices

1. **Generate Strong Secret**:
   ```bash
   openssl rand -hex 32
   # Output: 64-character hex string (256 bits)
   ```

2. **Never Commit Secrets to Git**:
   - ✅ Add to `.env` (gitignored)
   - ✅ Add to Vercel env vars
   - ❌ NEVER add to `.env.example` (committed to repo)
   - ❌ NEVER hardcode in source code

3. **Rotate Secrets Periodically**:
   - Every 90 days or after team member leaves
   - Update both VPS and Vercel at same time
   - Test immediately after rotation

4. **Limit Secret Exposure**:
   - Only deploy to Production, Preview, Development (not public)
   - Use different secrets for staging vs production if possible
   - Monitor Vercel access logs for unauthorized access

---

## Rollback Plan

If deployment causes issues:

### Option 1: Revert to Previous Deployment

```bash
# In Vercel dashboard:
# 1. Go to Deployments tab
# 2. Find previous working deployment
# 3. Click "..." menu → "Promote to Production"
# 4. Confirm promotion
# 5. Wait 1-2 minutes for rollback
```

### Option 2: Remove New Environment Variable

```bash
# If RUNNER_API_SECRET causes issues:
# 1. Vercel → Settings → Environment Variables
# 2. Find RUNNER_API_SECRET
# 3. Click "..." → "Delete"
# 4. Redeploy

# WARNING: This will break PDF export
# Only do this if PDF is causing more issues than it solves
```

### Option 3: Emergency Hotfix

```bash
# If logger import causes crashes:
# 1. Revert frontend/app.py changes
# 2. git checkout HEAD~1 frontend/app.py
# 3. git push
# 4. Vercel auto-deploys

# Then investigate issue locally before redeploying fix
```

---

## Post-Deployment Monitoring

### What to Monitor

1. **Vercel Functions Logs**:
   - Check for `PDF generation request` log entries
   - Look for `Authentication failed` errors
   - Monitor `Failed to connect to runner service` errors

2. **VPS Runner Logs**:
   ```bash
   ssh root@72.61.92.76
   cd /root/job-runner
   docker compose logs -f runner | grep -i pdf
   ```

3. **VPS PDF Service Logs**:
   ```bash
   docker compose logs -f pdf-service
   # Look for Playwright errors
   # Monitor PDF generation duration
   ```

4. **Error Rates**:
   - Track 503 errors in Vercel analytics
   - Track 401 errors (authentication failures)
   - Track 504 errors (timeouts)

### Success Metrics

- **Before Fix**: 100% PDF exports fail with 503
- **After Fix**: >95% PDF exports succeed with 200 OK
- **Acceptable**: <5% failures (timeout, VPS down, etc.)

---

## Contact & Escalation

If issues persist after all troubleshooting:

1. **Collect Diagnostics**:
   ```bash
   # VPS side
   ssh root@72.61.92.76
   cd /root/job-runner
   docker compose ps > diagnostics.txt
   docker compose logs runner --tail=100 >> diagnostics.txt
   docker compose logs pdf-service --tail=100 >> diagnostics.txt
   curl http://localhost:8000/health >> diagnostics.txt

   # Vercel side
   # Screenshot of Environment Variables page
   # Screenshot of latest deployment logs
   # Copy full error message from browser console
   ```

2. **Check GitHub Issues**:
   - https://github.com/taimooralam/job-search/issues
   - Search for "PDF export" or "503 error"

3. **Create Bug Report**:
   - Include diagnostics from step 1
   - Include exact steps to reproduce
   - Include browser/OS information
   - Include screenshots of errors

---

## Related Documentation

- **Frontend Configuration**: `/frontend/.env.example`
- **Runner Configuration**: `/.env.runner.example`
- **PDF Service Architecture**: `/plans/phase6-pdf-service-separation.md`
- **Deployment Plan**: `/plans/deployment-plan.md`
- **Bug Tracking**: `/plans/bugs.md`

---

**Last Updated**: 2025-11-28
**Next Review**: After successful PDF export verification
