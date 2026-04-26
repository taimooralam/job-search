#!/usr/bin/env python3
"""
Eval Step 2: Classify eligible jobs into 15 target categories.

Reads:  data/eval/raw/all_eligible_jobs.json
Outputs:
  data/eval/category_assignment_log.json
  data/eval/raw/{category}/jobs_all.json
  data/eval/raw/{category}/jd_texts/{nn}_{company}_{title}.md
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

EVAL_DIR = Path("data/eval")
RAW_DIR = EVAL_DIR / "raw"

# ── Category Definitions ──

CATEGORIES = [
    {"id": "head_of_ai_ksa", "name": "Head of AI — KSA", "macro": "ai_leadership",
     "title_re": r"(head|director|vp|vice.president|chief).*\b(ai|artificial.intelligence|genai|machine.learning)\b",
     "locations": ["saudi", "ksa", "riyadh", "jeddah", "dammam", "khobar", "dhahran", "neom"],
     "priority": "primary_target"},
    {"id": "head_of_ai_uae", "name": "Head of AI — UAE", "macro": "ai_leadership",
     "title_re": r"(head|director|vp|vice.president|chief).*\b(ai|artificial.intelligence|genai|machine.learning)\b",
     "locations": ["uae", "united arab emirates", "dubai", "abu dhabi", "sharjah", "al ain"],
     "priority": "primary_target"},
    {"id": "head_of_ai_eea", "name": "Head of AI — EEA", "macro": "ai_leadership",
     "title_re": r"(head|director|vp|vice.president|chief).*\b(ai|artificial.intelligence|genai|machine.learning)\b",
     "locations": "EEA", "priority": "primary_target"},
    {"id": "head_of_ai_global", "name": "Head of AI — Global/Remote", "macro": "ai_leadership",
     "title_re": r"(head|director|vp|vice.president|chief).*\b(ai|artificial.intelligence|genai|machine.learning)\b",
     "locations": "REMOTE", "priority": "primary_target"},
    {"id": "head_of_sw_pakistan", "name": "Head of Software/Engineering — Pakistan", "macro": "leadership_adjacent",
     "title_re": r"(head|director|vp|vice.president|chief|cto).*\b(software|engineering|technology|development)\b",
     "locations": ["pakistan", "karachi", "lahore", "islamabad", "rawalpindi"],
     "priority": "tertiary_target"},
    {"id": "staff_ai_engineer_eea", "name": "Staff AI Engineer — EEA", "macro": "ai_engineering_adjacent",
     "title_re": r"(staff|principal).*\b(ai|genai|llm|ml|machine.learning)\b.*\b(engineer|developer)\b|(staff|principal).*\b(engineer|developer)\b.*\b(ai|genai|llm|ml)\b",
     "locations": "EEA", "priority": "secondary_target"},
    {"id": "staff_ai_engineer_global", "name": "Staff AI Engineer — Global/Remote", "macro": "ai_engineering_adjacent",
     "title_re": r"(staff|principal).*\b(ai|genai|llm|ml|machine.learning)\b.*\b(engineer|developer)\b|(staff|principal).*\b(engineer|developer)\b.*\b(ai|genai|llm|ml)\b",
     "locations": "REMOTE", "priority": "secondary_target"},
    {"id": "tech_lead_ai_pakistan", "name": "Tech Lead AI — Pakistan", "macro": "ai_engineering_adjacent",
     "title_re": r"(lead|tech.?lead).*\b(ai|genai|llm|ml|machine.learning)\b|\b(ai|genai|llm|ml)\b.*(lead|tech.?lead)",
     "locations": ["pakistan", "karachi", "lahore", "islamabad", "rawalpindi"],
     "priority": "tertiary_target"},
    {"id": "tech_lead_ai_eea", "name": "Tech Lead AI — EEA", "macro": "ai_engineering_adjacent",
     "title_re": r"(lead|tech.?lead).*\b(ai|genai|llm|ml|machine.learning)\b|\b(ai|genai|llm|ml)\b.*(lead|tech.?lead)",
     "locations": "EEA", "priority": "secondary_target"},
    {"id": "ai_architect_eea", "name": "AI Architect — EEA", "macro": "ai_architect",
     "title_re": r"\b(ai|genai|llm|ml|machine.learning|artificial.intelligence)\b.*\b(architect)\b|\b(architect)\b.*\b(ai|genai|llm|ml)\b",
     "locations": "EEA", "priority": "primary_target"},
    {"id": "ai_architect_global", "name": "AI Architect — Global/Remote", "macro": "ai_architect",
     "title_re": r"\b(ai|genai|llm|ml|machine.learning|artificial.intelligence)\b.*\b(architect)\b|\b(architect)\b.*\b(ai|genai|llm|ml)\b",
     "locations": "REMOTE", "priority": "primary_target"},
    {"id": "ai_architect_ksa_uae", "name": "AI Architect — KSA/UAE", "macro": "ai_architect",
     "title_re": r"\b(ai|genai|llm|ml|machine.learning|artificial.intelligence)\b.*\b(architect)\b|\b(architect)\b.*\b(ai|genai|llm|ml)\b",
     "locations": ["saudi", "ksa", "riyadh", "jeddah", "dammam", "uae", "dubai", "abu dhabi", "sharjah"],
     "priority": "primary_target"},
    {"id": "ai_eng_manager_eea", "name": "AI Engineering Manager — EEA", "macro": "ai_engineering_adjacent",
     "title_re": r"(engineering.?manager|manager).*\b(ai|ml|genai|llm)\b|\b(ai|ml|genai|llm)\b.*(engineering.?manager|manager)",
     "locations": "EEA", "priority": "secondary_target"},
    {"id": "senior_ai_engineer_eea", "name": "Senior AI Engineer — EEA", "macro": "ai_engineering_adjacent",
     "title_re": r"senior.*\b(ai|genai|llm|ml)\b.*\b(engineer|developer)\b",
     "locations": "EEA", "priority": "secondary_target"},
    {"id": "ai_solutions_architect_global", "name": "AI Solutions Architect — Global", "macro": "ai_architect",
     "title_re": r"\b(ai|genai|artificial.intelligence)\b.*\bsolutions?\s*architect\b|\bsolutions?\s*architect\b.*\b(ai|genai)\b",
     "locations": "ANY", "priority": "primary_target"},
]

# ── EEA Countries ──

EEA_COUNTRIES = [
    "germany", "france", "netherlands", "belgium", "austria", "ireland",
    "spain", "italy", "portugal", "sweden", "denmark", "norway", "finland",
    "iceland", "poland", "czech", "romania", "hungary", "greece", "croatia",
    "bulgaria", "slovenia", "slovakia", "estonia", "latvia", "lithuania",
    "luxembourg", "malta", "cyprus", "liechtenstein",
    # Common city names for matching
    "berlin", "munich", "frankfurt", "hamburg", "cologne", "dusseldorf",
    "paris", "lyon", "amsterdam", "rotterdam", "brussels", "vienna",
    "dublin", "madrid", "barcelona", "milan", "rome", "lisbon", "porto",
    "stockholm", "copenhagen", "oslo", "helsinki",
    "warsaw", "prague", "bucharest", "budapest", "athens",
    # Meta
    "europe", "eu", "eea", "emea",
]

REMOTE_KEYWORDS = ["remote", "worldwide", "anywhere", "global", "work from home", "wfh"]


def normalize_text(text):
    """Lowercase and strip accents."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower().strip()


def matches_location(loc_lower, location_spec):
    """Check if a job's location matches the category's location spec.
    Returns (matches: bool, is_specific: bool) — is_specific=True means
    the location explicitly names the target region (not just blank/ANY)."""
    if location_spec == "ANY":
        return True, False
    if location_spec == "REMOTE":
        # Explicit remote keywords in location field
        explicit_remote = any(kw in loc_lower for kw in REMOTE_KEYWORDS)
        return explicit_remote, explicit_remote
    if location_spec == "EEA":
        match = any(country in loc_lower for country in EEA_COUNTRIES)
        return match, match
    # List of specific locations
    match = any(loc in loc_lower for loc in location_spec)
    return match, match


def classify_job(job):
    """
    Classify a job into categories.
    Returns (primary_category_id, secondary_ids, confidence, rationale).
    """
    title = normalize_text(job.get("title", ""))
    location = normalize_text(job.get("location", ""))
    job.get("ai_categories", []) or []
    extracted = job.get("extracted_jd", {}) or {}
    (extracted.get("role_category") or "").lower()
    jd = normalize_text(job.get("job_description", ""))

    # Blank location with "remote" in title → treat as remote for matching
    is_blank_remote = (not location.strip()) and ("remote" in title)
    is_blank_location = not location.strip()

    matches = []

    for cat in CATEGORIES:
        # Title match
        title_match = bool(re.search(cat["title_re"], title, re.IGNORECASE))

        # Location match — blank-location + "remote" in title → match REMOTE categories
        loc_match, loc_specific = matches_location(location, cat["locations"])
        if not loc_match and cat["locations"] == "REMOTE" and is_blank_remote:
            loc_match, loc_specific = True, True
        # Blank location without remote → eligible for ANY and REMOTE (lower confidence)
        if not loc_match and cat["locations"] in ("ANY", "REMOTE") and is_blank_location:
            loc_match, loc_specific = True, False

        # JD body signals for AI-related categories
        jd_ai_signal = False
        if cat["macro"] in ("ai_leadership", "ai_architect", "ai_engineering_adjacent"):
            ai_jd_keywords = ["llm", "large language model", "genai", "generative ai",
                              "rag", "retrieval", "agentic", "langchain", "langgraph",
                              "prompt engineering", "ai platform", "machine learning"]
            jd_ai_signal = sum(1 for kw in ai_jd_keywords if kw in jd) >= 2

        # Compute confidence and match score
        if title_match and loc_specific:
            # Title + explicit location — strongest match
            confidence = "high"
            score = 4
        elif title_match and loc_match and not loc_specific:
            # Title match + ANY location (e.g., Solutions Architect Global)
            confidence = "medium"
            score = 2
        elif jd_ai_signal and loc_specific and cat["macro"] in ("ai_architect", "ai_leadership"):
            # JD strongly signals AI + specific location
            confidence = "medium"
            score = 2
        elif title_match and not loc_match:
            # Title matches but wrong region — secondary only
            confidence = "low"
            score = 1
        else:
            continue

        rationale_parts = []
        if title_match:
            rationale_parts.append(f"title_match:{cat['title_re'][:40]}")
        if loc_match:
            rationale_parts.append("loc_match")
        if jd_ai_signal:
            rationale_parts.append("jd_ai_signal")

        matches.append({
            "category_id": cat["id"],
            "category_name": cat["name"],
            "macro_family": cat["macro"],
            "priority": cat["priority"],
            "confidence": confidence,
            "score": score,
            "rationale": " + ".join(rationale_parts),
        })

    if not matches:
        return None, [], "low", "no_category_match"

    # Sort by score desc, prefer primary_target
    priority_rank = {"primary_target": 3, "secondary_target": 2, "tertiary_target": 1}
    matches.sort(key=lambda m: (m["score"], priority_rank.get(m["priority"], 0)), reverse=True)

    primary = matches[0]
    secondary_ids = [m["category_id"] for m in matches[1:] if m["score"] >= 2]

    return primary["category_id"], secondary_ids, primary["confidence"], primary["rationale"]


def sanitize_filename(text, max_len=60):
    """Create a safe filename from text."""
    text = re.sub(r"[^\w\s-]", "", normalize_text(text))
    text = re.sub(r"[-\s]+", "_", text).strip("_")
    return text[:max_len]


def main():
    # Load eligible jobs
    with open(RAW_DIR / "all_eligible_jobs.json", encoding="utf-8") as f:
        jobs = json.load(f)
    print(f"Loaded {len(jobs)} eligible jobs")

    # Classify each job
    assignment_log = []
    category_jobs = defaultdict(list)
    unclassified = []

    for job in jobs:
        primary, secondaries, confidence, rationale = classify_job(job)

        entry = {
            "_id": job["_id"],
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "score": job.get("score"),
            "signal_tier": job.get("_signal_tier"),
            "primary_category": primary,
            "secondary_categories": secondaries,
            "classification_confidence": confidence,
            "classification_rationale": rationale,
        }

        # Find macro_family from category definition
        cat_def = next((c for c in CATEGORIES if c["id"] == primary), None)
        entry["macro_family"] = cat_def["macro"] if cat_def else "unclassified"

        assignment_log.append(entry)

        if primary:
            category_jobs[primary].append(job)
        else:
            unclassified.append(job)

    print(f"Classified: {len(jobs) - len(unclassified)}")
    print(f"Unclassified: {len(unclassified)}")

    # Save assignment log
    with open(EVAL_DIR / "category_assignment_log.json", "w", encoding="utf-8") as f:
        json.dump(assignment_log, f, indent=2, default=str)

    # Create per-category directories and files
    for cat in CATEGORIES:
        cat_id = cat["id"]
        cat_dir = RAW_DIR / cat_id
        jd_dir = cat_dir / "jd_texts"
        jd_dir.mkdir(parents=True, exist_ok=True)

        cat_job_list = category_jobs.get(cat_id, [])

        # Save jobs_all.json
        with open(cat_dir / "jobs_all.json", "w", encoding="utf-8") as f:
            json.dump(cat_job_list, f, indent=2, default=str)

        # Save individual JD text files
        for i, job in enumerate(cat_job_list):
            company = sanitize_filename(job.get("company", "unknown"))
            title = sanitize_filename(job.get("title", "unknown"))
            filename = f"{i+1:02d}_{company}_{title}.md"

            jd_text = job.get("job_description", "")
            header = f"# {job.get('title', 'Unknown')}\n\n"
            header += f"**Company:** {job.get('company', 'Unknown')}\n"
            header += f"**Location:** {job.get('location', 'Unknown')}\n"
            header += f"**Score:** {job.get('score', 'N/A')} (Tier {job.get('_signal_tier', '?')})\n"
            header += f"**Status:** {job.get('status', 'N/A')}\n\n---\n\n"

            with open(jd_dir / filename, "w", encoding="utf-8") as f:
                f.write(header + jd_text)

    # ── Summary Table ──
    print(f"\n{'='*90}")
    print(f"{'Category':<45} {'Count':>6} {'A':>4} {'B':>4} {'C':>4} {'D':>4} {'Hi':>4} {'Med':>4} {'Lo':>4}")
    print(f"{'='*90}")

    total_classified = 0
    low_confidence_cats = []

    for cat in CATEGORIES:
        cat_id = cat["id"]
        cat_jobs = category_jobs.get(cat_id, [])
        count = len(cat_jobs)
        total_classified += count

        # Tier breakdown
        tiers = Counter(j.get("_signal_tier") for j in cat_jobs)

        # Confidence breakdown from assignment log
        cat_entries = [e for e in assignment_log if e["primary_category"] == cat_id]
        conf = Counter(e["classification_confidence"] for e in cat_entries)

        flag = ""
        if count < 5:
            flag = " ** EXPLORATORY"
            low_confidence_cats.append(cat["name"])
        elif count < 8:
            flag = " * LOW"
            low_confidence_cats.append(cat["name"])

        print(f"{cat['name']:<45} {count:>6} {tiers.get('A',0):>4} {tiers.get('B',0):>4} "
              f"{tiers.get('C',0):>4} {tiers.get('D',0):>4} {conf.get('high',0):>4} "
              f"{conf.get('medium',0):>4} {conf.get('low',0):>4}{flag}")

    print(f"{'='*90}")
    print(f"{'Total classified':<45} {total_classified:>6}")
    print(f"{'Unclassified':<45} {len(unclassified):>6}")

    if low_confidence_cats:
        print("\nLow-confidence categories (<8 jobs):")
        for c in low_confidence_cats:
            print(f"  - {c}")


if __name__ == "__main__":
    main()
