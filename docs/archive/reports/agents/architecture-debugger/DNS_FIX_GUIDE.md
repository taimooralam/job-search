# MongoDB DNS Resolution Fix Guide

## Problem Summary
After disconnecting from VPN, macOS DNS configuration still points to unreachable VPN DNS server (100.64.0.2), causing MongoDB Atlas connection failures with 21-second timeout.

## Quick Fix (Immediate Action Required)

### Step 1: Flush DNS Cache
Open Terminal and run:

```bash
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

**Expected output**: No output (command succeeds silently)

### Step 2: Verify DNS Resolution Works
```bash
nslookup cluster0.mongodb.net
```

**Expected output**: Should show IP addresses without timeout errors

### Step 3: Test MongoDB Connection
```bash
mongosh "$MONGODB_URI" --eval "db.adminCommand('ping')"
```

**Expected output**: `{ ok: 1 }`

### Step 4: Restart Flask Application
```bash
# Kill existing Flask processes
pkill -f "python app.py"

# Restart Flask
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate
cd frontend
python app.py
```

---

## Permanent Fix (Change DNS Servers)

If DNS cache flush doesn't work or problem persists:

### macOS System Settings Method

1. Open **System Settings** → **Network**
2. Select your active connection (Wi-Fi or Ethernet)
3. Click **Details** → **DNS** tab
4. Click **+** and add these DNS servers (in order):
   - `8.8.8.8` (Google Primary)
   - `8.8.4.4` (Google Secondary)
   - `1.1.1.1` (Cloudflare Primary)
5. Click **OK** → **Apply**

### Command Line Method

```bash
# For Wi-Fi
networksetup -setdnsservers Wi-Fi 8.8.8.8 8.8.4.4 1.1.1.1

# For Ethernet
networksetup -setdnsservers Ethernet 8.8.8.8 8.8.4.4 1.1.1.1

# Verify DNS servers
scutil --dns | grep 'nameserver\[0\]'
```

---

## Code Changes Applied

### Updated `frontend/app.py`

**Changes**:
1. Added retry logic with exponential backoff (3 attempts)
2. Reduced MongoDB timeout from 30s → 5s (fail fast)
3. Added helpful error messages for DNS issues
4. Automatic retry on DNS failures

**New behavior**:
- **Before**: 21-second wait → crash with cryptic error
- **After**: 5-second wait → retry 3 times → helpful troubleshooting steps

**Example output on DNS failure**:
```
⚠️  DNS resolution failed (attempt 1/3). Retrying in 2s...
   Hint: Run 'sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder' to clear DNS cache
⚠️  DNS resolution failed (attempt 2/3). Retrying in 4s...
   Hint: Run 'sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder' to clear DNS cache
❌ MongoDB connection failed after 3 attempts
   Error: The resolution lifetime expired after 5.012 seconds...
   Troubleshooting:
   1. Flush DNS cache: sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
   2. Change DNS servers to 8.8.8.8 (Google DNS) in System Settings
   3. Verify MongoDB connection: mongosh "$MONGODB_URI" --eval "db.adminCommand('ping')"
   4. Restart Flask app after fixing DNS
```

---

## Verification Checklist

After applying fix:

- [ ] DNS flush completed without errors
- [ ] `nslookup cluster0.mongodb.net` resolves successfully
- [ ] `mongosh` connection test returns `{ ok: 1 }`
- [ ] Flask app starts without MongoDB errors
- [ ] http://localhost:5001 loads login page
- [ ] Job detail page loads without errors
- [ ] CV editor opens and displays content
- [ ] No DNS-related errors in browser console

---

## Debugging Commands

### Check Current DNS Configuration
```bash
scutil --dns | grep 'nameserver\[0\]'
```

**Problem**: Shows `100.64.0.2` (VPN DNS)
**Fixed**: Shows `8.8.8.8` or your router IP

### Monitor DNS Queries (Advanced)
```bash
sudo log stream --predicate 'process == "mDNSResponder"' --level debug
```

### Test MongoDB Connection Directly
```bash
# From project root
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate
python -c "from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); client = MongoClient(os.getenv('MONGODB_URI'), serverSelectionTimeoutMS=5000); print(client.admin.command('ping'))"
```

**Expected output**: `{'ok': 1.0}`

---

## Root Cause Analysis

**What Happened**:
1. VPN was active → Configured custom DNS server (100.64.0.2)
2. VPN disconnected → DNS server no longer reachable
3. macOS kept VPN DNS configuration → All DNS queries timeout
4. PyMongo tried to resolve MongoDB Atlas hostname → 21-second timeout → Connection failure

**Why 100.64.0.2**:
- This is a Carrier-Grade NAT (CGNAT) IP address (100.64.0.0/10 range)
- Used by VPN providers for internal DNS routing
- Only accessible while VPN tunnel is active

**Why 21 Seconds**:
- PyMongo default timeout: 30 seconds
- DNS resolver tries multiple times before giving up: ~21 seconds
- Total wait time before error: 21+ seconds (very long)

---

## Prevention

To avoid this issue in the future:

1. **Use public DNS servers permanently**:
   - Set DNS to 8.8.8.8/8.8.4.4 (Google) or 1.1.1.1 (Cloudflare)
   - VPN can override temporarily but won't break DNS when disconnected

2. **Flush DNS after VPN disconnect**:
   - Create alias in `~/.zshrc` or `~/.bashrc`:
     ```bash
     alias flushdns='sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder && echo "DNS cache flushed"'
     ```
   - Run `flushdns` after disconnecting VPN

3. **Monitor DNS health**:
   - Check DNS servers: `scutil --dns | head -20`
   - Verify before starting services: `nslookup google.com`

---

## Related Issues

- **TipTap CDN Scripts**: Previously blocked by VPN (MIME type issue) → Fixed by disconnecting VPN
- **MongoDB Connection**: Now broken by stale DNS → Fixed by flushing DNS cache

Both issues stemmed from VPN configuration conflicts.
