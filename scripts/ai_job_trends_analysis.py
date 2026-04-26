#!/usr/bin/env python3
"""Analyze AI/GenAI/LLM job trends from MongoDB level-2 collection.

Uses _id ObjectId generation time as the reliable date source since
createdAt is stored as string in 99.7% of documents.
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
coll = client["jobs"]["level-2"]

# ── AI/GenAI Keyword Definitions ─────────────────────────
AI_KEYWORDS = {
    "ai_general": [
        r"\bartificial intelligence\b", r"\bmachine learning\b",
        r"\bdeep learning\b", r"\bneural network\b",
    ],
    "ai_mention": [
        r"\bAI\b", r"\bML\b",
    ],
    "genai_llm": [
        r"\bgenai\b", r"\bgenerative ai\b", r"\bgen ai\b",
        r"\bLLM\b", r"\blarge language model\b",
        r"\bGPT\b", r"\bChatGPT\b", r"\bClaude\b", r"\bGemini\b",
        r"\btransformer\b", r"\bfoundation model\b",
        r"\bOpenAI\b", r"\bAnthropic\b",
    ],
    "agentic_ai": [
        r"\bagentic\b", r"\bai agent\b", r"\bagent framework\b",
        r"\blang\s?graph\b", r"\blangchain\b",
        r"\bcrewai\b", r"\bautogen\b",
        r"\bmulti.?agent\b", r"\btool.?call\b",
        r"\bfunction.?call\b",
    ],
    "rag_retrieval": [
        r"\bRAG\b", r"\bretrieval.augmented\b",
        r"\bvector.?database\b", r"\bvector.?store\b", r"\bvector.?search\b",
        r"\bembedding\b", r"\bpinecone\b", r"\bweaviate\b",
        r"\bqdrant\b", r"\bchroma\b", r"\bfaiss\b",
        r"\bsemantic.?search\b",
    ],
    "mlops_llmops": [
        r"\bMLOps\b", r"\bLLMOps\b",
        r"\bmodel.?serving\b", r"\bmodel.?deploy\b",
        r"\bmodel.?monitor\b", r"\bmodel.?registry\b",
        r"\blangfuse\b", r"\bweights.?biases\b", r"\bmlflow\b",
        r"\bsagemaker\b", r"\bvertex.?ai\b", r"\bbedrock\b",
        r"\bazure.?openai\b", r"\bazure.?ai\b",
        r"\bmodel.?pipeline\b", r"\bml.?pipeline\b",
    ],
    "fine_tuning": [
        r"\bfine.?tun\b", r"\bLoRA\b", r"\bQLoRA\b",
        r"\bRLHF\b", r"\bpeft\b",
        r"\binstruction.?tuning\b", r"\bdomain.?adapt\b",
    ],
    "ai_governance": [
        r"\bai governance\b", r"\bresponsible ai\b",
        r"\bai ethics\b", r"\bai safety\b",
        r"\beu ai act\b", r"\bnist ai\b",
        r"\bai risk\b", r"\bmodel card\b",
        r"\bai compliance\b",
    ],
    "prompt_engineering": [
        r"\bprompt engineer\b", r"\bprompt design\b",
        r"\bprompt optim\b",
    ],
    "mcp_protocol": [
        r"\bmodel context protocol\b", r"\bMCP\b",
    ],
    "data_science": [
        r"\bdata scientist?\b", r"\bdata engineer\b",
        r"\bdata platform\b", r"\bfeature store\b",
        r"\bdata lake\b", r"\bdata mesh\b",
    ],
}

# Skills you're actively learning
YOUR_SKILLS = {
    "Python": [r"\bpython\b"],
    "LangGraph": [r"\blang\s?graph\b"],
    "LangChain": [r"\blangchain\b"],
    "RAG": [r"\bRAG\b", r"\bretrieval.augmented\b"],
    "Vector DB": [r"\bvector.?(database|store|search)\b", r"\bpinecone\b", r"\bweaviate\b", r"\bqdrant\b", r"\bchroma\b"],
    "Fine-tuning": [r"\bfine.?tun\b", r"\bLoRA\b", r"\bQLoRA\b"],
    "LLM Eval": [r"\bllm.{0,20}eval\b", r"\beval.{0,20}llm\b", r"\bmodel.?eval\b", r"\bbenchmark\b", r"\bgolden.?dataset\b"],
    "Langfuse": [r"\blangfuse\b"],
    "MLflow": [r"\bmlflow\b"],
    "SageMaker": [r"\bsagemaker\b"],
    "Bedrock": [r"\bbedrock\b"],
    "Vertex AI": [r"\bvertex.?ai\b"],
    "Azure OpenAI": [r"\bazure.?openai\b", r"\bazure.?ai\b"],
    "AI Agent": [r"\bai agent\b", r"\bagentic\b"],
    "LLMOps": [r"\bllmops\b"],
    "MLOps": [r"\bmlops\b"],
    "FastAPI": [r"\bfastapi\b"],
    "Terraform": [r"\bterraform\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Docker": [r"\bdocker\b"],
    "AWS": [r"\bAWS\b", r"\bamazon web services\b"],
    "CI/CD": [r"\bci/?cd\b", r"\bcontinuous (integration|delivery|deployment)\b"],
    "Microservices": [r"\bmicroservice\b"],
    "Event-Driven": [r"\bevent.driven\b", r"\bevent.?sourc\b"],
    "DDD": [r"\bdomain.driven\b"],
    "GenAI": [r"\bgenai\b", r"\bgenerative ai\b", r"\bgen ai\b"],
    "LLM": [r"\bLLM\b", r"\blarge language model\b"],
    "GPT/OpenAI": [r"\bGPT\b", r"\bOpenAI\b", r"\bChatGPT\b"],
    "Anthropic/Claude": [r"\bClaude\b", r"\bAnthropic\b"],
}

LEADERSHIP_PATTERNS = {
    "C-Level": [r"\bCTO\b", r"\bCIO\b", r"\bChief\s+(Technology|AI|Data|Information)\b"],
    "VP": [r"\bVP\b", r"\bVice President\b"],
    "Director": [r"\bDirector\b"],
    "Head of": [r"\bHead of\b"],
    "Principal/Staff": [r"\bPrincipal\b", r"\bStaff\b", r"\bDistinguished\b"],
    "Lead/Manager": [r"\bTech\s*Lead\b", r"\bTeam\s*Lead\b", r"\bEng\w*\s*Manager\b", r"\bLead\s+(Eng|Software|Dev|Architect)\b"],
    "Senior": [r"\bSenior\b", r"\bSr[\.\s]\b"],
    "Architect": [r"\bArchitect\b"],
    "Mid/Junior": [],
}


def matches_any(text, patterns):
    if not text:
        return False
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def get_leadership_level(title):
    if not title:
        return "Unknown"
    for level, patterns in LEADERSHIP_PATTERNS.items():
        if patterns and matches_any(title, patterns):
            return level
    return "Mid/Junior"


def get_searchable_text(doc):
    """Build full searchable text from all relevant fields."""
    parts = [
        doc.get("title", "") or "",
        doc.get("job_description", "") or "",
        doc.get("description", "") or "",
        doc.get("job_criteria", "") or "",
    ]
    # extracted_jd fields
    ejd = doc.get("extracted_jd") or {}
    for field in ("technical_skills", "top_keywords", "responsibilities", "qualifications", "nice_to_haves"):
        val = ejd.get(field)
        if isinstance(val, list):
            parts.append(" ".join(str(v) for v in val))
        elif val:
            parts.append(str(val))
    return " ".join(parts)


def get_doc_date(doc):
    """Get document date from _id ObjectId generation time."""
    return doc["_id"].generation_time.replace(tzinfo=None)


def classify_job(searchable_text):
    """Classify searchable text into AI categories."""
    categories = []
    for cat, patterns in AI_KEYWORDS.items():
        if matches_any(searchable_text, patterns):
            categories.append(cat)
    return categories


# ── Load all jobs ────────────────────────────────────────
print("Loading all jobs from MongoDB level-2...")
all_jobs = list(coll.find({}))
total = len(all_jobs)
print(f"Total jobs: {total}")

# Add computed fields
for doc in all_jobs:
    doc["_date"] = get_doc_date(doc)
    doc["_text"] = get_searchable_text(doc)
    doc["_ai_cats"] = classify_job(doc["_text"])
    doc["_level"] = get_leadership_level(doc.get("title", ""))

oldest = min(d["_date"] for d in all_jobs)
newest = max(d["_date"] for d in all_jobs)
print(f"Date range: {oldest.strftime('%Y-%m-%d')} → {newest.strftime('%Y-%m-%d')}")

# ── Time Windows ─────────────────────────────────────────
now = datetime.utcnow()
windows = {
    "last_2_months": now.replace(day=1) - __import__("dateutil.relativedelta", fromlist=["relativedelta"]).relativedelta(months=1),
    "last_4_months": now.replace(day=1) - __import__("dateutil.relativedelta", fromlist=["relativedelta"]).relativedelta(months=3),
    "all_time": datetime(2020, 1, 1),
}
# Simpler: just use day offsets
windows = {
    "last_2_months": now - __import__("datetime").timedelta(days=60),
    "last_4_months": now - __import__("datetime").timedelta(days=120),
    "last_6_months": now - __import__("datetime").timedelta(days=180),
    "all_time": datetime(2020, 1, 1),
}

print(f"\n{'=' * 90}")
print("AI/GENAI/LLM JOB TRENDS ANALYSIS")
print(f"{'=' * 90}")

for window_name, cutoff in windows.items():
    jobs = [d for d in all_jobs if d["_date"] >= cutoff]
    ai_jobs = [d for d in jobs if d["_ai_cats"]]
    # Exclude jobs that ONLY match ai_mention (just "AI" or "ML" in passing)
    strong_ai_jobs = [d for d in jobs if any(c != "ai_mention" for c in d["_ai_cats"])]
    total_w = len(jobs)

    if total_w == 0:
        continue

    cat_counts = Counter()
    level_counts = Counter()
    ai_level_counts = Counter()
    tier_counts = Counter()
    companies = Counter()
    score_vals = []

    for d in jobs:
        level_counts[d["_level"]] += 1

    for d in strong_ai_jobs:
        for c in d["_ai_cats"]:
            cat_counts[c] += 1
        ai_level_counts[d["_level"]] += 1
        tier = d.get("tier") or d.get("quick_score_tier") or "unscored"
        tier_counts[str(tier)] += 1
        companies[d.get("company", "??")] += 1
        s = d.get("score") or d.get("quick_score")
        if s and isinstance(s, (int, float)):
            score_vals.append(s)

    print(f"\n{'─' * 90}")
    print(f"  {window_name.upper()} (since {cutoff.strftime('%Y-%m-%d')}) — {total_w} total jobs")
    print(f"{'─' * 90}")
    print(f"  AI-related (strong match):  {len(strong_ai_jobs):,} ({len(strong_ai_jobs)/total_w*100:.1f}%)")
    print(f"  AI-related (any mention):   {len(ai_jobs):,} ({len(ai_jobs)/total_w*100:.1f}%)")
    if score_vals:
        print(f"  Avg score (AI jobs):        {sum(score_vals)/len(score_vals):.1f}")

    print(f"\n  AI CATEGORY BREAKDOWN (% of all {total_w} jobs):")
    for cat, count in cat_counts.most_common():
        pct = count / total_w * 100
        bar = "█" * max(1, int(pct))
        print(f"    {cat:25s}: {count:5d} ({pct:5.1f}%) {bar}")

    print("\n  LEADERSHIP LEVELS — ALL JOBS:")
    for level, count in level_counts.most_common():
        pct = count / total_w * 100
        print(f"    {level:20s}: {count:5d} ({pct:5.1f}%)")

    print(f"\n  LEADERSHIP LEVELS — AI JOBS ONLY ({len(strong_ai_jobs)}):")
    for level, count in ai_level_counts.most_common():
        pct = count / len(strong_ai_jobs) * 100 if strong_ai_jobs else 0
        print(f"    {level:20s}: {count:5d} ({pct:5.1f}%)")

    if tier_counts:
        print("\n  TIER DISTRIBUTION (AI jobs):")
        for tier, count in tier_counts.most_common():
            pct = count / len(strong_ai_jobs) * 100 if strong_ai_jobs else 0
            print(f"    Tier {tier:10s}: {count:5d} ({pct:5.1f}%)")

    print("\n  TOP 15 COMPANIES (AI jobs):")
    for company, count in companies.most_common(15):
        print(f"    {company[:40]:40s}: {count:3d}")

# ── Monthly Trend ────────────────────────────────────────
print(f"\n{'=' * 90}")
print("MONTHLY TREND")
print(f"{'=' * 90}")

monthly = defaultdict(lambda: {"total": 0, "ai_strong": 0, "cats": Counter(), "levels": Counter()})
for d in all_jobs:
    m = d["_date"].strftime("%Y-%m")
    monthly[m]["total"] += 1
    if any(c != "ai_mention" for c in d["_ai_cats"]):
        monthly[m]["ai_strong"] += 1
        for c in d["_ai_cats"]:
            monthly[m]["cats"][c] += 1
        monthly[m]["levels"][d["_level"]] += 1

header = f"{'Month':8s} | {'Total':>6s} | {'AI':>5s} | {'AI%':>5s} | {'GenAI':>6s} | {'Agent':>6s} | {'RAG':>5s} | {'MLOps':>6s} | {'FTune':>6s} | {'Gov':>5s} | {'Prompt':>6s}"
print(f"\n  {header}")
print(f"  {'─' * len(header)}")
for m in sorted(monthly.keys()):
    d = monthly[m]
    pct = d["ai_strong"] / d["total"] * 100 if d["total"] else 0
    c = d["cats"]
    print(f"  {m:8s} | {d['total']:6d} | {d['ai_strong']:5d} | {pct:4.1f}% | {c.get('genai_llm', 0):6d} | {c.get('agentic_ai', 0):6d} | {c.get('rag_retrieval', 0):5d} | {c.get('mlops_llmops', 0):6d} | {c.get('fine_tuning', 0):6d} | {c.get('ai_governance', 0):5d} | {c.get('prompt_engineering', 0):6d}")

# ── Your Skills Deep Dive ────────────────────────────────
print(f"\n{'=' * 90}")
print("YOUR LEARNING TARGET SKILLS — DEMAND ACROSS TIME")
print(f"{'=' * 90}")

# Compute for each month
for m in sorted(monthly.keys()):
    m_jobs = [d for d in all_jobs if d["_date"].strftime("%Y-%m") == m]
    total_m = len(m_jobs)
    print(f"\n  {m} ({total_m} jobs):")
    skill_counts = {}
    for skill_name, patterns in YOUR_SKILLS.items():
        count = sum(1 for d in m_jobs if matches_any(d["_text"], patterns))
        skill_counts[skill_name] = count

    for skill, count in sorted(skill_counts.items(), key=lambda x: -x[1]):
        if count == 0:
            continue
        pct = count / total_m * 100
        bar = "█" * max(1, int(pct / 2))
        print(f"    {skill:20s}: {count:5d} ({pct:5.1f}%) {bar}")

# ── Aggregate skill frequencies ──────────────────────────
print(f"\n{'=' * 90}")
print("AGGREGATE SKILL FREQUENCIES (ALL TIME)")
print(f"{'=' * 90}")

skill_totals = {}
for skill_name, patterns in YOUR_SKILLS.items():
    count = sum(1 for d in all_jobs if matches_any(d["_text"], patterns))
    skill_totals[skill_name] = count

print(f"\n  {'Skill':20s} | {'Count':>6s} | {'% of {0}'.format(total):>10s} | {'Trend':30s}")
print(f"  {'─' * 75}")
for skill, count in sorted(skill_totals.items(), key=lambda x: -x[1]):
    pct = count / total * 100
    bar = "█" * max(1, int(pct / 2))
    print(f"  {skill:20s} | {count:6d} | {pct:9.1f}% | {bar}")

# ── High-Score AI Jobs ───────────────────────────────────
print(f"\n{'=' * 90}")
print("HIGH-SCORING AI JOBS (score >= 80)")
print(f"{'=' * 90}")

tier_a = []
for d in all_jobs:
    s = d.get("score") or d.get("quick_score") or 0
    if not isinstance(s, (int, float)):
        continue
    if s >= 80 and any(c != "ai_mention" for c in d["_ai_cats"]):
        tier_a.append(d)

tier_a.sort(key=lambda x: (x.get("score") or x.get("quick_score") or 0), reverse=True)
print(f"\n  Found {len(tier_a)} high-scoring AI jobs:\n")
for d in tier_a[:40]:
    s = d.get("score") or d.get("quick_score") or 0
    cats = [c for c in d["_ai_cats"] if c != "ai_mention"][:3]
    date = d["_date"].strftime("%Y-%m-%d")
    title = (d.get("title") or "")[:55]
    company = (d.get("company") or "")[:28]
    loc = (d.get("location") or "")[:20]
    print(f"  [{s:3.0f}] {d['_level']:15s} | {title:55s} | {company:28s} | {date} | {', '.join(cats)}")

# ── AI jobs by source ────────────────────────────────────
print(f"\n{'=' * 90}")
print("AI JOBS BY SOURCE")
print(f"{'=' * 90}")
source_ai = Counter()
source_all = Counter()
for d in all_jobs:
    src = d.get("source", "unknown")
    source_all[src] += 1
    if any(c != "ai_mention" for c in d["_ai_cats"]):
        source_ai[src] += 1

for src, total_s in source_all.most_common():
    ai_count = source_ai.get(src, 0)
    pct = ai_count / total_s * 100 if total_s else 0
    print(f"  {src:25s}: {ai_count:5d} / {total_s:5d} ({pct:5.1f}% AI)")

# ── Export JSON ──────────────────────────────────────────
output = {
    "generated_at": now.isoformat(),
    "total_jobs": total,
    "date_range": {"oldest": oldest.isoformat(), "newest": newest.isoformat()},
    "monthly": {},
    "skill_frequencies": skill_totals,
    "high_score_ai_jobs": [
        {
            "title": d.get("title"),
            "company": d.get("company"),
            "score": d.get("score") or d.get("quick_score"),
            "level": d["_level"],
            "categories": d["_ai_cats"],
            "date": d["_date"].isoformat(),
            "location": d.get("location"),
        }
        for d in tier_a[:50]
    ],
}

for m in sorted(monthly.keys()):
    d = monthly[m]
    output["monthly"][m] = {
        "total": d["total"],
        "ai_strong": d["ai_strong"],
        "ai_pct": round(d["ai_strong"] / d["total"] * 100, 1) if d["total"] else 0,
        "categories": dict(d["cats"]),
        "leadership": dict(d["levels"]),
    }

with open("reports/ai-job-trends-data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str)

print("\n\nRaw data exported to reports/ai-job-trends-data.json")
