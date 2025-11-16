# API Keys & Integration Setup Guide

Complete step-by-step guide to set up all required integrations for the Job Intelligence Pipeline.

---

## **1. MongoDB** 🗄️

**What it's for**: Stores job listings from your existing scraper

**Setup**:
- If you already have MongoDB from your n8n workflow, reuse that URI
- **Option A**: MongoDB Atlas (Cloud - Free tier available)
  - Sign up at https://www.mongodb.com/cloud/atlas/register
  - Create a cluster → Get connection string
  - Format: `mongodb+srv://username:password@cluster.mongodb.net/job-search`
- **Option B**: Local MongoDB
  - Install: `brew install mongodb-community` (macOS)
  - URI: `mongodb://localhost:27017/job-search`

**Get the URI**: Database → Connect → Drivers → Copy connection string

---

## **2. OpenAI** 🤖

**What it's for**: Primary LLM for analysis (GPT-4o, GPT-4-turbo)

**Setup**:
- Sign up at https://platform.openai.com/signup
- Add payment method (API is pay-as-you-go, ~$0.01-0.03 per job)
- Go to https://platform.openai.com/api-keys
- Click "Create new secret key" → Copy it (starts with `sk-...`)

**Cost estimate**: ~$0.02-0.05 per job (6-7 LLM calls per job)

---

## **3. OpenRouter** 🔀

**What it's for**: Alternative to OpenAI (access to Claude, Llama, etc.)

**Setup**:
- Sign up at https://openrouter.ai/
- Go to https://openrouter.ai/keys
- Click "Create Key" → Copy it (starts with `sk-or-...`)
- Add credits ($5-10 minimum)

**When to use**: Set `USE_OPENROUTER=true` in `.env` to route through OpenRouter instead of OpenAI

---

## **4. FireCrawl** 🔥

**What it's for**: Clean web scraping of company websites (better than BeautifulSoup)

**Setup**:
- Sign up at https://www.firecrawl.dev/
- Go to https://www.firecrawl.dev/app/api-keys
- Copy your API key (starts with `fc-...`)

**Free tier**: 500 credits/month (enough for ~100-200 company pages)

---

## **5. LangSmith** 📊

**What it's for**: Observability/tracing for LangGraph pipelines (debugging & monitoring)

**Setup**:
- Sign up at https://smith.langchain.com/
- Go to Settings → API Keys → Create API Key
- Copy key (starts with `lsv2_...`)
- Note your project name (or use `job-intelligence-pipeline`)

**Free tier**: 5,000 traces/month

---

## **6. Google Cloud (Drive + Sheets)** ☁️

**What it's for**: Upload CV/cover letters to Drive, track applications in Sheets

**Setup** (Most complex - follow carefully):

### Step 1: Create Google Cloud Project
- Go to https://console.cloud.google.com/
- Create new project: "Job Pipeline"
- Enable APIs:
  - Google Drive API: https://console.cloud.google.com/apis/library/drive.googleapis.com
  - Google Sheets API: https://console.cloud.google.com/apis/library/sheets.googleapis.com

### Step 2: Create Service Account
- Go to https://console.cloud.google.com/iam-admin/serviceaccounts
- Create Service Account → Name: "job-pipeline-bot"
- Grant role: "Editor" (or "Owner")
- Click on service account → Keys → Add Key → JSON
- **Download the JSON file** → Save as `credentials/google-service-account.json`
- **IMPORTANT**: Add `credentials/` to `.gitignore`

### Step 3: Create Drive Folder
- Open Google Drive
- Create folder: "Job Applications"
- Right-click → Share → Add the service account email (from JSON: `client_email`)
- Give it "Editor" access
- Copy the folder ID from URL: `https://drive.google.com/drive/folders/{FOLDER_ID}`

### Step 4: Create Google Sheet
- Create new Google Sheet: "Job Tracker"
- Add headers: `Date | Company | Role | Fit Score | Drive URL | Status`
- Share with service account email (Editor access)
- Copy sheet ID from URL: `https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit`

---

## **7. File Structure Setup**

```bash
# Create credentials directory
mkdir -p credentials

# Add to .gitignore
echo "credentials/" >> .gitignore
echo ".env" >> .gitignore
```

---

## **8. Environment Variables Template**

After getting all API keys, create `.env` file with:

```bash
# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname

# LLM APIs
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
USE_OPENROUTER=false

# Web Scraping
FIRECRAWL_API_KEY=fc-...

# Observability
LANGSMITH_API_KEY=lsv2_...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=job-intelligence-pipeline

# Google APIs
GOOGLE_CREDENTIALS_PATH=./credentials/google-service-account.json
GOOGLE_DRIVE_FOLDER_ID=1abc...
GOOGLE_SHEET_ID=1xyz...

# Candidate Profile
CANDIDATE_PROFILE_PATH=./knowledge-base.md
```

---

## **9. Verification Checklist**

After setup, verify:
- [ ] MongoDB connection works (can query jobs collection)
- [ ] OpenAI/OpenRouter API key works (test with simple completion)
- [ ] FireCrawl can scrape a test URL
- [ ] LangSmith shows your project
- [ ] Service account can access Drive folder
- [ ] Service account can write to Google Sheet
- [ ] All credentials are in `.gitignore`
- [ ] No secrets committed to git

---

## **Cost Breakdown (Monthly Estimates)**

| Service | Free Tier | Estimated Cost (100 jobs/month) |
|---------|-----------|--------------------------------|
| MongoDB Atlas | 512MB free | $0 (fits in free tier) |
| OpenAI API | $5 free credit | $2-5 |
| OpenRouter | $0 | $2-5 (if using) |
| FireCrawl | 500 credits | $0 (fits in free tier) |
| LangSmith | 5K traces | $0 (fits in free tier) |
| Google Cloud | 15GB Drive | $0 (fits in free tier) |
| **Total** | | **~$2-5/month** |

---

## **Quick Tips**

**Security**:
- Never commit `.env` or `credentials/` to git
- Rotate API keys if accidentally exposed
- Use read-only MongoDB user if possible

**Cost Optimization**:
- Use GPT-4o-mini for non-critical layers (10x cheaper)
- Enable FireCrawl caching to reduce scraping costs
- Set LangSmith sampling rate to 50% in production

**Troubleshooting**:
- MongoDB connection issues: Check IP whitelist in Atlas
- Google API errors: Verify service account has Editor role
- LangSmith not showing traces: Check `LANGCHAIN_TRACING_V2=true`
- FireCrawl rate limits: Add retry logic with exponential backoff

---

## **Next Steps**

After completing this setup:
1. Create `.env` file with all keys
2. Test each integration individually
3. Run Phase 1 from `next.md` (project structure)
4. Start building the pipeline!
