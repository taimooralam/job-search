# Credential Backup & Recovery Plan (GAP-004)

**Status**: IMPLEMENTED  
**Last Updated**: 2025-12-01

## Problem Statement

API keys, MongoDB URI, and other credentials exist only on the VPS. If the VPS fails:
- Cannot recover system
- All services go down
- Data recovery impossible without MongoDB URI

## Critical Credentials to Backup

| Credential | Location | Recovery Impact |
|------------|----------|-----------------|
| `MONGODB_URI` | VPS `.env` | **CRITICAL** - No DB access |
| `OPENROUTER_API_KEY` | VPS `.env` | HIGH - No LLM calls |
| `FIRECRAWL_API_KEY` | VPS `.env` | MEDIUM - No web scraping |
| `LANGSMITH_API_KEY` | VPS `.env` | LOW - No tracing |
| `RUNNER_API_SECRET` | VPS + Vercel | HIGH - Auth fails |
| `VERCEL_TOKEN` | GitHub Secrets | MEDIUM - Deploy fails |
| `VPS_SSH_KEY` | GitHub Secrets | HIGH - No deploy |
| `GHCR_TOKEN` | GitHub Secrets | MEDIUM - No Docker push |

## Solution: Git-Crypt Encrypted Vault

### Setup (One-Time)

```bash
# 1. Install git-crypt
brew install git-crypt  # macOS
apt install git-crypt   # Linux

# 2. Initialize in repository
cd job-search
git-crypt init

# 3. Create .gitattributes
echo "secrets/** filter=git-crypt diff=git-crypt" >> .gitattributes
echo ".env.backup filter=git-crypt diff=git-crypt" >> .gitattributes

# 4. Export symmetric key (SAVE THIS SECURELY!)
git-crypt export-key ./git-crypt-key.bin
# Store in 1Password, cloud backup, or print

# 5. Create secrets directory
mkdir -p secrets
```

### Backup Process

```bash
# Create encrypted backup of credentials
cat > secrets/credentials.env << 'CREDENTIALS'
# MongoDB Atlas
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/jobs

# LLM Providers
OPENROUTER_API_KEY=sk-or-...
ANTHROPIC_API_KEY=sk-ant-...

# Services
FIRECRAWL_API_KEY=fc-...
LANGSMITH_API_KEY=ls-...

# Auth
RUNNER_API_SECRET=your-secret-here
JWT_SECRET=your-jwt-secret

# Deployment
VPS_HOST=72.61.92.76
VPS_USER=root
CREDENTIALS

# Commit (automatically encrypted)
git add secrets/
git commit -m "chore: update encrypted credentials backup"
git push
```

### Recovery Process

```bash
# 1. Clone repository
git clone git@github.com:yourusername/job-search.git
cd job-search

# 2. Unlock with key
git-crypt unlock ./git-crypt-key.bin

# 3. Copy credentials to VPS
scp secrets/credentials.env root@72.61.92.76:/root/job-runner/.env

# 4. Restart services
ssh root@72.61.92.76 "cd /root/job-runner && docker compose up -d"
```

## Alternative: AWS Secrets Manager

For production systems, consider AWS Secrets Manager:

```python
# pip install boto3

import boto3
from botocore.exceptions import ClientError

def get_secret(secret_name: str) -> dict:
    """Retrieve secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager', region_name='eu-central-1')
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except ClientError as e:
        raise RuntimeError(f"Failed to get secret {secret_name}: {e}")

# Usage
secrets = get_secret("job-search/production")
mongodb_uri = secrets["MONGODB_URI"]
```

**Costs**: ~$0.40/secret/month + $0.05/10,000 API calls

## Verification Checklist

- [ ] Git-crypt initialized in repository
- [ ] Symmetric key exported and stored in 1Password
- [ ] All credentials backed up in `secrets/credentials.env`
- [ ] Recovery process tested on local machine
- [ ] Team members have access to symmetric key

## Monthly Recovery Test

```bash
# Test credential recovery monthly
# 1. Fresh clone
git clone git@github.com:yourusername/job-search.git /tmp/test-recovery
cd /tmp/test-recovery

# 2. Unlock
git-crypt unlock ~/path/to/git-crypt-key.bin

# 3. Verify secrets readable
cat secrets/credentials.env | head -5

# 4. Cleanup
rm -rf /tmp/test-recovery
```

## Security Notes

1. **Never** commit unencrypted credentials
2. **Always** use `.gitattributes` to auto-encrypt
3. **Store** git-crypt key in separate secure location (not in repo)
4. **Rotate** credentials quarterly
5. **Audit** access to secrets regularly

---

*This document addresses GAP-004: Credential Backup Vault*
