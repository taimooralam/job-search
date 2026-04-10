#!/usr/bin/env python3
"""Fetch and display CV review results from MongoDB."""
import argparse
import os
import sys

from bson import ObjectId
from pymongo import MongoClient


def _print_list(label: str, items: list, prefix: str = "  -") -> None:
    if not items:
        return
    print(f"\n{label} ({len(items)}):")
    for item in items:
        print(f"{prefix} {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show CV review results for a job")
    parser.add_argument("--job-id", required=True, help="MongoDB job _id")
    args = parser.parse_args()

    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client.get_default_database()
    job = db["level-2"].find_one({"_id": ObjectId(args.job_id)})

    if not job:
        print("Job not found", file=sys.stderr)
        sys.exit(1)

    review = job.get("cv_review")
    if not review:
        print(f"No review yet for {job.get('company', '?')} — {job.get('title', '?')}")
        sys.exit(0)

    print(f"Company:   {job.get('company')}")
    print(f"Title:     {job.get('title')}")
    print(f"Model:     {review.get('model', '?')}")
    print(f"Reviewer:  {review.get('reviewer', 'unknown')}")
    print(f"Reviewed:  {review.get('reviewed_at', '?')}")

    verdict = review.get("verdict", "?")
    confidence = review.get("confidence", "?")
    would_interview = review.get("would_interview")
    first_score = review.get("first_impression_score", "?")

    interview_str = "YES" if would_interview else "NO"
    print(f"\nVerdict:   {verdict}  (confidence={confidence})")
    print(f"Interview: {interview_str}")
    print(f"Top-1/3 score: {first_score}/10")

    full = review.get("full_review") or {}

    # Top 1/3 assessment
    top_third = full.get("top_third_assessment") or {}
    if top_third:
        print("\n--- Top 1/3 Assessment ---")
        if top_third.get("first_impression_summary"):
            print(f"  {top_third['first_impression_summary']}")
        if top_third.get("headline_verdict"):
            print(f"  Headline:     {top_third['headline_verdict']}")
        if top_third.get("tagline_verdict"):
            print(f"  Tagline:      {top_third['tagline_verdict']}")
        if top_third.get("achievements_verdict"):
            print(f"  Achievements: {top_third['achievements_verdict']}")
        if top_third.get("competencies_verdict"):
            print(f"  Competencies: {top_third['competencies_verdict']}")

    # Pain point alignment
    pain = full.get("pain_point_alignment") or {}
    if pain:
        ratio = pain.get("coverage_ratio", "?")
        print(f"\n--- Pain Point Alignment (coverage={ratio}) ---")
        _print_list("Addressed", pain.get("addressed", []), prefix="  +")
        _print_list("Missing", pain.get("missing", []), prefix="  -")

    # ATS assessment
    ats = full.get("ats_assessment") or {}
    if ats:
        survival = "LIKELY" if ats.get("ats_survival_likely") else "AT RISK"
        print(f"\n--- ATS Assessment [{survival}] ---")
        print(f"  Keywords: {ats.get('keyword_coverage', '?')}")
        missing_kw = ats.get("missing_critical_keywords", [])
        if missing_kw:
            print(f"  Missing critical keywords: {', '.join(missing_kw)}")
        acronym_issues = ats.get("acronym_issues", [])
        if acronym_issues:
            _print_list("Acronym issues", acronym_issues)

    # Hallucination flags
    flags = full.get("hallucination_flags") or []
    if flags:
        print(f"\n--- Hallucination Flags ({len(flags)}) ---")
        for f in flags:
            severity = f.get("severity", "?")
            claim = f.get("claim", "?")
            issue = f.get("issue", "?")
            print(f"  [{severity.upper()}] {claim} — {issue}")

    # Strengths / weaknesses
    _print_list("Strengths", full.get("strengths", []), prefix="  +")
    _print_list("Weaknesses", full.get("weaknesses", []), prefix="  -")

    # Specific improvements
    improvements = full.get("specific_improvements") or []
    if improvements:
        print(f"\n--- Specific Improvements ({len(improvements)}) ---")
        for i, imp in enumerate(improvements, 1):
            section = imp.get("section", "?")
            reason = imp.get("reason", "")
            current = imp.get("current", "")
            suggested = imp.get("suggested", "")
            print(f"\n  {i}. [{section}] {reason}")
            if current:
                print(f"     Current:   {current}")
            if suggested:
                print(f"     Suggested: {suggested}")

    # Ideal candidate fit
    fit = full.get("ideal_candidate_fit") or {}
    if fit:
        print("\n--- Ideal Candidate Fit ---")
        if fit.get("archetype_match"):
            print(f"  Archetype: {fit['archetype_match']}")
        if fit.get("experience_level_match"):
            print(f"  Experience: {fit['experience_level_match']}")
        trait_cov = fit.get("trait_coverage") or {}
        present = trait_cov.get("present", [])
        missing_traits = trait_cov.get("missing", [])
        if present:
            print(f"  Traits present: {', '.join(present)}")
        if missing_traits:
            print(f"  Traits missing: {', '.join(missing_traits)}")


if __name__ == "__main__":
    main()
