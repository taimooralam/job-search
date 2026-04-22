# Automated Job Discovery → Stale Check → CV Review Pipeline

**Date:** 2026-04-13
**Goal:** Automate the full loop: discover best jobs → verify they're still open → run CV reviews — all from a single command.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Local Mac (single command)                                        │
│                                                                    │
│  Phase 1: DISCOVER                                                 │
│  ├─ Query MongoDB level-2 with 7-tier criteria                     │
│  ├─ Exact title priority → regex fallback → recency cap (7d)       │
│  └─ Output: ranked job list (IDs + URLs)                           │
│                                                                    │
│  Phase 2: STALE CHECK                                              │
│  ├─ Download working proxies from VPS /var/lib/scout/proxies.json  │
│  ├─ Load LinkedIn cookies from data/linkedin-cookies.txt           │
│  ├─ HTTP check each job URL through rotating proxies               │
│  ├─ Rate limit: 8-15s random delay, proxy rotation per request     │
│  ├─ Mark closed jobs in MongoDB (status: "closed")                 │
│  └─ Output: filtered list of OPEN jobs                             │
│                                                                    │
│  Phase 3: CV REVIEW (parallel)                                     │
│  ├─ Split open jobs across N worker processes                      │
│  ├─ Each worker: build prompt → call OpenAI API → parse → persist  │
│  ├─ Uses OpenAI API (not Codex CLI) — no OAuth token contention    │
│  └─ Output: cv_review written to MongoDB for each job              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Discover Jobs

### Query Logic

Use the 7-tier criteria from `memory/user_job_search_criteria.md`:

```python
# Global filters
base_filter = {
    "status": {"$nin": ["applied", "discarded", "closed", "rejected", "skipped"]},
    "createdAt": {"$gte": datetime.utcnow() - timedelta(days=7)},  # recency cap
    "cv_text": {"$exists": True, "$ne": ""},       # CV generated
    "extracted_jd": {"$exists": True},              # JD extracted
}

# Two-pass per tier: exact titles first, then regex
for tier in tiers:
    # Pass 1: exact title matches (surface first)
    exact_jobs = query(title__in=tier.exact_titles, **base_filter)
    # Pass 2: regex matches not already found
    regex_jobs = query(title__regex=tier.regex, _id__nin=seen, **base_filter)
    results.extend(exact_jobs + regex_jobs)
    if len(results) >= limit: break
```

### Exact Title Lists (from criteria)

```python
EXACT_TITLES = {
    1: ["AI Architect", "AI Solutions Architect", "AI Systems Architect",
        "AI Platform Architect", "GenAI Architect", "LLM Architect",
        "Agentic AI Architect", "Enterprise AI Architect",
        "Senior AI Architect", "Principal AI Architect"],
    2: ["Lead AI Engineer", "AI Tech Lead", "AI Engineering Lead",
        "AI Lead", "Lead GenAI Engineer", "Lead LLM Engineer",
        "AI Platform Lead", "Lead AI Architect", "AI Engineering Manager"],
    3: ["Staff AI Engineer", "Principal AI Engineer",
        "Staff GenAI Engineer", "Staff LLM Engineer",
        "Staff AI Architect", "Senior AI Engineer"],
    4: ["Head of AI", "Head of AI Engineering", "Head of GenAI",
        "Director of AI", "Director of AI Engineering",
        "VP of AI", "Chief AI Officer"],
}
```

### Output

```python
@dataclass
class DiscoveredJob:
    id: str
    tier: int
    exact_match: bool  # True if exact title, False if regex
    title: str
    company: str
    location: str
    score: int
    job_url: str
    created_at: datetime
```

---

## Phase 2: Stale Check via Proxies

### Proxy Download

```python
import subprocess, json

# Download working proxies from VPS
result = subprocess.run(
    ["ssh", "root@72.61.92.76", "cat /var/lib/scout/proxies.json"],
    capture_output=True, text=True, timeout=10
)
proxies = json.loads(result.stdout)  # ["http://1.2.3.4:8080", ...]
```

### LinkedIn Stale Check

```python
import http.cookiejar, requests, random, time

# Load cookies
cj = http.cookiejar.MozillaCookieJar("data/linkedin-cookies.txt")
cj.load(ignore_discard=True, ignore_expires=True)

CLOSURE_SIGNALS = [
    "no longer accepting applications",
    "this job has expired",
    "job is closed",
    "this job is no longer available",
]

def stale_check(job_url: str, proxy_pool: list) -> tuple[bool, str]:
    """Returns (is_open, reason)."""
    proxy_url = random.choice(proxy_pool)
    proxies = {"http": proxy_url, "https": proxy_url}

    s = requests.Session()
    s.cookies = cj
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/125.0.0.0 Safari/537.36"
    })

    try:
        r = s.get(job_url, proxies=proxies, timeout=15)
        if r.status_code == 404:
            return False, "404"
        text = r.text.lower()
        for signal in CLOSURE_SIGNALS:
            if signal in text:
                return False, signal
        # Check if cookies expired (login wall)
        if "sign in" in text[:2000] and "job" not in text[:2000]:
            return True, "cookies_expired"  # Can't confirm, assume open
        return True, "open"
    except Exception as e:
        return True, f"error:{e}"  # Can't confirm, assume open
```

### Rate Limiting Strategy

```
- Random delay: 8-15 seconds between requests (gaussian, mean=11s)
- Proxy rotation: different proxy per request (round-robin from pool)
- Batch pause: after every 10 checks, pause 30-60 seconds
- Cookie session: reuse same cookie jar, but new Session per request
- If 429 received: pause 5 minutes, switch to direct (no proxy)
- If cookies expired: stop immediately, ask user to refresh
- Total throughput: ~4-5 checks/minute = safe for LinkedIn
```

### MongoDB Updates

```python
# For closed jobs:
collection.update_one(
    {"_id": ObjectId(job_id)},
    {"$set": {
        "status": "closed",
        "closed_detected_at": datetime.utcnow(),
        "closed_reason": reason,
    }}
)

# For open jobs: no update, just pass to Phase 3
```

---

## Phase 3: Parallel CV Review

### Why Not Codex CLI for Parallelism

Codex CLI uses ChatGPT OAuth with refresh token rotation. Multiple processes = multiple
concurrent `codex exec` calls = same auth.json = token race = all fail (openai/codex#10332).

### Solution: OpenAI API via `openai` Python SDK

Use `OPENAI_API_KEY` directly. No OAuth, no token contention, fully parallelizable.

```python
import openai
from multiprocessing import Pool

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def review_job(job: dict) -> dict:
    """Run CV review for a single job using OpenAI API."""
    prompt = build_review_prompt(job)  # Same prompt as CVReviewService

    response = client.chat.completions.create(
        model="gpt-4o",  # or gpt-5.4-mini
        messages=[
            {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    review = json.loads(response.choices[0].message.content)
    # Derive taxonomy fields
    failure_modes = _derive_failure_modes(review)
    headline_bounded = _derive_headline_evidence_bounded(review)
    bridge_score = _derive_bridge_quality_score(review)

    return {
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "model": "gpt-4o",
        "reviewer": "independent_gpt",
        "verdict": review.get("verdict"),
        "would_interview": review.get("would_interview"),
        "confidence": review.get("confidence"),
        "first_impression_score": review.get("top_third_assessment", {}).get("first_impression_score"),
        "failure_modes": failure_modes,
        "headline_evidence_bounded": headline_bounded,
        "bridge_quality_score": bridge_score,
        "full_review": review,
    }

# Parallel execution
with Pool(processes=4) as pool:
    results = pool.map(review_job, open_jobs)
```

### Parallelism Constraints

| Workers | Rate (RPM) | Cost/review | Notes |
|---------|-----------|-------------|-------|
| 1       | ~8-10     | ~$0.02      | Safe, sequential |
| 2       | ~16-20    | ~$0.02      | Good balance |
| 4       | ~30-40    | ~$0.02      | Hits Tier 1 RPM limits |
| 8       | ~60-80    | ~$0.02      | Needs Tier 2+ API access |

**Recommendation:** Start with 3-4 workers. OpenAI Tier 1 allows 500 RPM for gpt-4o,
so even 4 workers won't hit limits. Each review takes ~30-45s (mostly API latency),
so 4 workers = ~6-8 reviews/minute.

### Error Handling

```python
# Per-worker error handling:
# - API rate limit (429): exponential backoff (2s, 4s, 8s)
# - API error (500): retry once, then skip
# - Invalid JSON: regex extract, retry once
# - Timeout: skip after 120s
# All errors logged, job skipped but not marked — can retry next run
```

---

## CLI Interface

### Single Command

```bash
python scripts/discover_check_review.py [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--limit` | 20 | Max jobs to discover |
| `--days` | 7 | Recency cap (days) |
| `--skip-stale` | false | Skip stale check (trust all as open) |
| `--skip-review` | false | Only discover + stale check, no CV review |
| `--workers` | 3 | Parallel CV review workers |
| `--model` | gpt-4o | OpenAI model for review |
| `--dry-run` | false | Show plan, don't execute |
| `--tier` | all | Filter to specific tier (1-7) |
| `--re-review` | false | Re-review jobs that already have cv_review |

### Output

```
=== Phase 1: Discovery ===
Found 23 jobs matching criteria (7-day window)
  Tier 1 (exact): 3 | Tier 1 (regex): 5 | Tier 2: 8 | Tier 3: 7

=== Phase 2: Stale Check ===
Downloaded 142 working proxies from VPS
Checking 23 jobs... [████████████████████] 23/23
  Open: 18 | Closed: 4 | Error: 1
  Closed: NVIDIA (expired), TUI (filled), SII POLAND (expired), Kainos (closed)

=== Phase 3: CV Review (4 workers) ===
Reviewing 18 jobs... [████████████████████] 18/18
  STRONG_MATCH: 3 | GOOD_MATCH: 7 | NEEDS_WORK: 5 | WEAK_MATCH: 3
  Would interview: 10/18 (56%)
  Avg confidence: 0.87 | Total time: 4m 22s

=== Summary ===
Discovered: 23 → Open: 18 → Reviewed: 18
Top 5 by verdict:
  1. [STRONG] Qodea — Senior AI Engineer (score: 88, confidence: 0.94)
  2. [STRONG] Hunter Bond — AI Engineering Manager (score: 82, confidence: 0.91)
  3. [STRONG] Kainos — Lead AI Engineer (score: 76, confidence: 0.89)
  ...
```

---

## File Location

```
n8n/skills/cv-review/scripts/discover_check_review.py
```

Lives in cv-review skill since CV review is the terminal action. Imports discovery
logic inline (just MongoDB queries) and stale-check logic (requests + cookies).

### Dependencies

```
# Already in project:
pymongo, requests, openai, python-dotenv, bson

# Reuse from existing code:
src.services.cv_review_service  →  REVIEWER_SYSTEM_PROMPT, _derive_failure_modes, etc.
src.common.master_cv_store      →  MasterCVStore (loads master-cv.md)
```

---

## Safety & Rate Limits

### LinkedIn (stale check)
- 4-5 requests/minute via proxies (safe threshold)
- Rotate proxy per request (never same IP twice in a row)
- Gaussian delay 8-15s (not fixed interval — harder to fingerprint)
- Cookie session isolation (new Session per request, shared cookie jar)
- Stop on 429 or cookie expiration

### OpenAI API (CV review)
- gpt-4o: 500 RPM, 30K TPM (Tier 1) — 4 workers easily fits
- gpt-4o-mini: 500 RPM, 200K TPM — even more headroom
- Exponential backoff on 429
- Each review prompt: ~4-8K tokens input, ~2-3K tokens output

### MongoDB
- No rate limit concern (direct connection)
- Batch updates after each phase (not per-job)

---

## Alternative: Keep Codex CLI (Sequential) + API (Parallel)

If user prefers Codex CLI for the ChatGPT Plus cost advantage:

```python
# Mode A: Codex CLI (free with ChatGPT Plus, sequential only)
python scripts/discover_check_review.py --engine codex --workers 1

# Mode B: OpenAI API (paid per token, parallelizable)
python scripts/discover_check_review.py --engine api --workers 4

# Mode C: Hybrid (Codex for small batches, API for large)
python scripts/discover_check_review.py --engine auto  # codex if ≤5 jobs, api if >5
```

---

## Implementation Order

1. **Phase 1 (Discovery)**: MongoDB query with tier logic — straightforward, ~100 lines
2. **Phase 2 (Stale Check)**: Proxy download + LinkedIn check — ~150 lines
3. **Phase 3 (CV Review)**: Fork existing bulk_review.py to use OpenAI API + multiprocessing — ~200 lines
4. **Glue**: CLI argument parsing, progress output, summary — ~100 lines

Total: ~550 lines, single file. Reuses existing prompt/taxonomy code via imports.
