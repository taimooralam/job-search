#!/usr/bin/env python3
"""
Eval Step 3: Per-job normalized analysis via Codex CLI (gpt-5.4-mini).

Reads:  data/eval/raw/{category}/jobs_all.json
Outputs:
  data/eval/normalized/{category}/normalized_jobs.json  (3a: all jobs)
  data/eval/normalized/{category}/deep_analysis.json    (3b: top 20 exemplars)

Usage:
  python scripts/eval_step3_analyze.py                     # all categories
  python scripts/eval_step3_analyze.py --category ai_architect_eea  # single category
  python scripts/eval_step3_analyze.py --dry-run            # test with 2 jobs
"""

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

EVAL_DIR = Path("data/eval")
RAW_DIR = EVAL_DIR / "raw"
NORM_DIR = EVAL_DIR / "normalized"

CODEX_MODEL = "gpt-5.4-mini"
BATCH_SIZE = 2  # Jobs per Codex call (reduced for retry pass)
TIMEOUT = 360   # Seconds per Codex call (increased for retry pass)

# All populated categories
CATEGORIES = [
    "head_of_ai_ksa", "head_of_ai_uae", "head_of_ai_eea", "head_of_ai_global",
    "head_of_sw_pakistan", "staff_ai_engineer_eea", "staff_ai_engineer_global",
    "tech_lead_ai_eea", "ai_architect_eea", "ai_architect_global",
    "ai_architect_ksa_uae", "ai_eng_manager_eea", "senior_ai_engineer_eea",
]

# ── Extraction Schema ──

EXTRACTION_SYSTEM_PROMPT = """You are a structured job description analyzer. Extract normalized fields from job descriptions.

For EACH job, output a JSON object with these fields. Use ONLY information explicitly stated in the JD text.

Evidence rules:
- "explicit" = directly stated in the JD
- "derived" = tightly inferred from explicit wording
- "not_specified" = not present — use this liberally, do NOT guess

Output a JSON array of objects, one per job. Each object has this schema:

{
  "job_id": "string — the _id provided",
  "title_normalized": "string — cleaned title without location/company",
  "title_family": "string — one of: head_of_ai, director_ai, vp_ai, ai_architect, solutions_architect, staff_engineer, principal_engineer, tech_lead, engineering_manager, senior_engineer, other",
  "seniority": "string — one of: executive, director, senior_manager, manager, senior_ic, mid_ic, junior, not_specified",
  "role_scope": "string — one of: ic, player_coach, manager, director, executive, not_specified",

  "management": {
    "direct_reports": "string — number or range if stated, else not_specified",
    "hiring": "explicit|derived|not_specified",
    "performance_management": "explicit|derived|not_specified",
    "org_building": "explicit|derived|not_specified",
    "budget_pnl": "explicit|derived|not_specified"
  },

  "architecture": {
    "platform_design": "explicit|derived|not_specified",
    "greenfield_vs_optimization": "string — greenfield|optimization|both|not_specified",
    "scale_signals": "string — user count, request volume, data size if mentioned, else not_specified",
    "latency_reliability": "string — SLA/latency/uptime requirements if mentioned, else not_specified"
  },

  "hard_skills_must_have": ["list of explicitly required technical skills"],
  "hard_skills_nice_to_have": ["list of preferred/bonus technical skills"],

  "programming_languages": {
    "required": ["languages explicitly required"],
    "preferred": ["languages mentioned as nice-to-have"]
  },

  "cloud_platform": {
    "primary": "string — AWS|Azure|GCP|multi_cloud|not_specified",
    "services_mentioned": ["specific cloud services named"]
  },

  "infrastructure": ["Docker|Kubernetes|Terraform|CI_CD|serverless|microservices|etc — only explicit"],

  "ai_ml_stack": {
    "rag": "explicit|derived|not_specified",
    "agents_orchestration": "explicit|derived|not_specified",
    "fine_tuning": "explicit|derived|not_specified",
    "evaluation_quality": "explicit|derived|not_specified",
    "guardrails_governance": "explicit|derived|not_specified",
    "prompt_engineering": "explicit|derived|not_specified",
    "vector_search": "explicit|derived|not_specified",
    "model_serving_routing": "explicit|derived|not_specified",
    "frameworks": ["LangChain|LangGraph|PyTorch|TensorFlow|HuggingFace|etc — only explicit"],
    "observability": ["Langfuse|LangSmith|Datadog|Prometheus|etc — only explicit"]
  },

  "data_stack": ["PostgreSQL|MongoDB|Redis|Elasticsearch|Qdrant|Pinecone|etc — only explicit"],

  "governance_compliance": ["GDPR|EU_AI_Act|SOC2|HIPAA|ISO27001|etc — only explicit"],

  "soft_skills": ["communication|collaboration|stakeholder_management|mentoring|etc — only explicit"],

  "domain_industry": "string — fintech|healthcare|media|ecommerce|enterprise_saas|consulting|defense|not_specified",
  "company_stage": "string — startup_seed|startup_a|startup_b|scaleup|enterprise|faang|consultancy|agency|not_specified",
  "collaboration_model": "string — remote_first|hybrid|onsite|distributed|not_specified",

  "stakeholder_level": "string — team|department|cross_functional|executive|board|not_specified",
  "success_metrics": ["explicit success criteria or KPIs mentioned"],
  "implied_pain_points": ["what problems is this hire expected to solve — derived from JD context"],

  "disqualifiers": {
    "requires_phd": false,
    "requires_publications": false,
    "requires_native_language": "string — language if required, else not_specified",
    "requires_security_clearance": false,
    "requires_specific_domain_years": "string — e.g. '5+ years healthcare' or not_specified",
    "research_heavy": false
  }
}

IMPORTANT:
- Return ONLY the JSON array, no markdown, no explanation
- Use "not_specified" for anything not explicitly in the JD
- Do NOT infer or hallucinate skills, tools, or requirements
- If a JD is very short or generic, most fields should be "not_specified"
"""

DEEP_ANALYSIS_EXTRA = """

Additionally, for this deep analysis, add these fields to each object:

  "cv_translation": {
    "what_strong_cv_proves": "string — 2-3 sentences on what evidence a top CV needs",
    "most_valued_evidence_types": ["scale|reliability|hiring|governance|cost|delivery|architecture|evaluation"],
    "unsafe_claims_for_candidate": ["claims that would be unsupported for an Engineering Leader / Software Architect with AI platform experience"],
    "best_candidate_experience_mapping": ["which of the candidate's roles/projects would map best to this JD and why"]
  }

The candidate is Taimoor Alam: 11yr Engineering Leader / Software Architect, Technical Lead at Seven.One Entertainment Group (Munich). Built Commander-4 (enterprise AI workflow platform, 42 plugins, 2000 users, RAG, semantic caching, evaluation, guardrails). Also built Lantern (LLM gateway, multi-provider routing, circuit breaker). Prior: Lead Engineer (CQRS/event-sourcing), Backend Engineer (Flask/MongoDB), Microservices/RabbitMQ, IoT (CoAP/MQTT), WebRTC/real-time.
"""


def call_codex(prompt: str, timeout: int = TIMEOUT) -> Optional[str]:
    """Call Codex CLI and return the response text."""
    with tempfile.NamedTemporaryFile(encoding="utf-8", mode="w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        result = subprocess.run(
            f"cat {prompt_file} | codex exec -m {CODEX_MODEL} --full-auto",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        os.unlink(prompt_file)

        if result.returncode != 0:
            print(f"  Codex error: {result.stderr[:200]}")
            return None

        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        os.unlink(prompt_file)
        print(f"  Codex timeout after {timeout}s")
        return None
    except Exception as e:
        if os.path.exists(prompt_file):
            os.unlink(prompt_file)
        print(f"  Codex exception: {e}")
        return None


def extract_json_from_response(response: str) -> Optional[list]:
    """Extract JSON array from Codex response (may have preamble text)."""
    if not response:
        return None

    # Try direct parse first
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in response
    start = response.find("[")
    if start == -1:
        start = response.find("{")
    if start == -1:
        return None

    # Find matching end bracket
    bracket_count = 0
    end = start
    open_char = response[start]
    close_char = "]" if open_char == "[" else "}"

    for i in range(start, len(response)):
        if response[i] == open_char:
            bracket_count += 1
        elif response[i] == close_char:
            bracket_count -= 1
        if bracket_count == 0:
            end = i + 1
            break

    try:
        data = json.loads(response[start:end])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        return None

    return None


def build_batch_prompt(jobs: List[Dict], system: str) -> str:
    """Build a prompt for a batch of jobs."""
    job_texts = []
    for job in jobs:
        jd = (job.get("job_description") or "")[:4000]  # Cap JD length
        job_texts.append(
            f'--- JOB (id: {job["_id"]}) ---\n'
            f'Title: {job.get("title", "Unknown")}\n'
            f'Company: {job.get("company", "Unknown")}\n'
            f'Location: {job.get("location", "Unknown")}\n'
            f'Score: {job.get("score", "N/A")}\n\n'
            f'{jd}\n'
        )

    return (
        f"{system}\n\n"
        f"Analyze these {len(jobs)} job descriptions and return a JSON array "
        f"with one object per job:\n\n"
        + "\n".join(job_texts)
    )


def process_category_normalized(category: str, dry_run: bool = False) -> Dict:
    """Run 3a: Full-corpus normalized extraction for a category."""
    cat_dir = RAW_DIR / category
    jobs_file = cat_dir / "jobs_all.json"

    if not jobs_file.exists():
        return {"category": category, "status": "skipped", "reason": "no jobs_all.json"}

    with open(jobs_file, encoding="utf-8") as f:
        jobs = json.load(f)

    if not jobs:
        return {"category": category, "status": "skipped", "reason": "empty"}

    if dry_run:
        jobs = jobs[:2]

    out_dir = NORM_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check for existing results (resume support)
    existing_file = out_dir / "normalized_jobs.json"
    existing_results = {}
    if existing_file.exists():
        try:
            with open(existing_file, encoding="utf-8") as f:
                existing = json.load(f)
            existing_results = {r["job_id"]: r for r in existing if "job_id" in r}
            print(f"  Resuming: {len(existing_results)} already extracted")
        except (json.JSONDecodeError, KeyError):
            pass

    # Filter to unprocessed jobs
    remaining = [j for j in jobs if j["_id"] not in existing_results]
    if not remaining:
        print(f"  All {len(jobs)} jobs already extracted")
        return {
            "category": category, "status": "complete",
            "total": len(jobs), "extracted": len(existing_results), "failed": 0,
        }

    print(f"  Processing {len(remaining)} remaining jobs (batch size {BATCH_SIZE})...")

    all_results = list(existing_results.values())
    failed = 0

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} jobs)...", end=" ", flush=True)

        prompt = build_batch_prompt(batch, EXTRACTION_SYSTEM_PROMPT)
        response = call_codex(prompt, timeout=TIMEOUT)
        parsed = extract_json_from_response(response)

        if parsed:
            all_results.extend(parsed)
            print(f"OK ({len(parsed)} extracted)")
        else:
            failed += len(batch)
            print("FAILED")
            # Create placeholder entries for failed jobs
            for job in batch:
                all_results.append({
                    "job_id": job["_id"],
                    "title_normalized": job.get("title", ""),
                    "_extraction_failed": True,
                    "_error": "codex_extraction_failed",
                })

        # Save incrementally after each batch
        with open(existing_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, default=str)

        # Brief pause between batches to avoid rate limiting
        if i + BATCH_SIZE < len(remaining):
            time.sleep(1)

    return {
        "category": category, "status": "complete",
        "total": len(jobs), "extracted": len(all_results) - failed, "failed": failed,
    }


def process_category_deep(category: str, dry_run: bool = False) -> Dict:
    """Run 3b: Deep analysis on top 20 exemplars for a category."""
    cat_dir = RAW_DIR / category
    jobs_file = cat_dir / "jobs_all.json"

    if not jobs_file.exists():
        return {"category": category, "status": "skipped", "reason": "no jobs_all.json"}

    with open(jobs_file, encoding="utf-8") as f:
        jobs = json.load(f)

    if not jobs:
        return {"category": category, "status": "skipped", "reason": "empty"}

    # Select top 20 exemplars: Tier B first, then highest score
    tier_rank = {"A": 4, "B": 3, "C": 2, "D": 1}
    jobs.sort(
        key=lambda j: (
            tier_rank.get(j.get("_signal_tier", "D"), 0),
            j.get("score", 0) or 0,
        ),
        reverse=True,
    )
    exemplars = jobs[:20] if not dry_run else jobs[:2]

    out_dir = NORM_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check for existing deep analysis
    deep_file = out_dir / "deep_analysis.json"
    existing_results = {}
    if deep_file.exists():
        try:
            with open(deep_file, encoding="utf-8") as f:
                existing = json.load(f)
            existing_results = {r["job_id"]: r for r in existing if "job_id" in r}
        except (json.JSONDecodeError, KeyError):
            pass

    remaining = [j for j in exemplars if j["_id"] not in existing_results]
    if not remaining:
        print(f"  All {len(exemplars)} deep exemplars already analyzed")
        return {
            "category": category, "status": "complete",
            "total": len(exemplars), "analyzed": len(existing_results),
        }

    print(f"  Deep analysis: {len(remaining)} exemplars (batch size 3)...")

    all_results = list(existing_results.values())
    deep_system = EXTRACTION_SYSTEM_PROMPT + DEEP_ANALYSIS_EXTRA
    failed = 0

    # Smaller batches for deep analysis (richer output)
    deep_batch = 3
    for i in range(0, len(remaining), deep_batch):
        batch = remaining[i:i + deep_batch]
        batch_num = i // deep_batch + 1
        total_batches = (len(remaining) + deep_batch - 1) // deep_batch
        print(f"  Deep batch {batch_num}/{total_batches} ({len(batch)} jobs)...", end=" ", flush=True)

        prompt = build_batch_prompt(batch, deep_system)
        response = call_codex(prompt, timeout=180)  # Longer timeout for deep analysis
        parsed = extract_json_from_response(response)

        if parsed:
            all_results.extend(parsed)
            print(f"OK ({len(parsed)} analyzed)")
        else:
            failed += len(batch)
            print("FAILED")
            for job in batch:
                all_results.append({
                    "job_id": job["_id"],
                    "_extraction_failed": True,
                })

        with open(deep_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, default=str)

        if i + deep_batch < len(remaining):
            time.sleep(1)

    return {
        "category": category, "status": "complete",
        "total": len(exemplars), "analyzed": len(all_results) - failed, "failed": failed,
    }


def main():
    parser = argparse.ArgumentParser(description="Eval Step 3: Per-job analysis via Codex")
    parser.add_argument("--category", help="Process single category")
    parser.add_argument("--deep-only", action="store_true", help="Only run deep analysis (3b)")
    parser.add_argument("--normalize-only", action="store_true", help="Only run normalized extraction (3a)")
    parser.add_argument("--dry-run", action="store_true", help="Test with 2 jobs per category")
    args = parser.parse_args()

    categories = [args.category] if args.category else CATEGORIES
    categories = [c for c in categories if (RAW_DIR / c / "jobs_all.json").exists()]

    print(f"Step 3: Processing {len(categories)} categories")
    print(f"Model: {CODEX_MODEL}, Batch size: {BATCH_SIZE}")
    if args.dry_run:
        print("DRY RUN: 2 jobs per category")
    print()

    # 3a: Normalized extraction
    norm_results = []
    if not args.deep_only:
        print("=" * 60)
        print("STEP 3a: Full-corpus normalized extraction")
        print("=" * 60)
        for cat in categories:
            print(f"\n[{cat}]")
            result = process_category_normalized(cat, dry_run=args.dry_run)
            norm_results.append(result)
            print(f"  Result: {result['status']} — {result.get('extracted', 0)}/{result.get('total', 0)} extracted, {result.get('failed', 0)} failed")

    # 3b: Deep analysis
    deep_results = []
    if not args.normalize_only:
        print(f"\n{'=' * 60}")
        print("STEP 3b: Deep exemplar analysis")
        print("=" * 60)
        for cat in categories:
            print(f"\n[{cat}]")
            result = process_category_deep(cat, dry_run=args.dry_run)
            deep_results.append(result)
            print(f"  Result: {result['status']} — {result.get('analyzed', 0)}/{result.get('total', 0)} analyzed")

    # Summary
    print(f"\n{'=' * 60}")
    print("STEP 3 SUMMARY")
    print("=" * 60)

    if norm_results:
        total_extracted = sum(r.get("extracted", 0) for r in norm_results)
        total_failed = sum(r.get("failed", 0) for r in norm_results)
        total_jobs = sum(r.get("total", 0) for r in norm_results)
        print(f"3a Normalized: {total_extracted}/{total_jobs} extracted, {total_failed} failed")

    if deep_results:
        total_deep = sum(r.get("analyzed", 0) for r in deep_results)
        total_deep_target = sum(r.get("total", 0) for r in deep_results)
        print(f"3b Deep: {total_deep}/{total_deep_target} analyzed")


if __name__ == "__main__":
    main()
