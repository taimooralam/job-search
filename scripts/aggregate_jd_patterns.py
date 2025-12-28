#!/usr/bin/env python3
"""
Phase 2: Aggregate JD Patterns from Existing Extractions

This script aggregates patterns from all existing extracted JDs in MongoDB.
It produces a comprehensive pattern analysis per role category.

Usage:
    python scripts/aggregate_jd_patterns.py
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient
from src.common.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_mongodb_client() -> MongoClient:
    """Get MongoDB client."""
    if not Config.MONGODB_URI:
        raise ValueError("MONGODB_URI not configured in .env")
    return MongoClient(Config.MONGODB_URI)


def aggregate_patterns_from_mongodb(client: MongoClient) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate patterns from all extracted JDs in MongoDB.

    Returns:
        Dict mapping role_category to aggregated patterns
    """
    level2 = client['jobs']['level-2']

    # Query all jobs with extracted_jd
    jobs = list(level2.find(
        {"extracted_jd": {"$type": "object"}},
        {"title": 1, "company": 1, "extracted_jd": 1}
    ))

    logger.info(f"Found {len(jobs)} jobs with extracted JDs")

    role_patterns = defaultdict(lambda: {
        "count": 0,
        "technical_skills": defaultdict(int),
        "soft_skills": defaultdict(int),
        "top_keywords": defaultdict(int),
        "implied_pain_points": [],
        "success_metrics": [],
        "responsibilities": [],
        "competency_weights": {
            "delivery": [],
            "process": [],
            "architecture": [],
            "leadership": [],
        },
        "seniority_levels": defaultdict(int),
        "sample_titles": [],
        "sample_companies": [],
    })

    for job in jobs:
        jd = job.get("extracted_jd", {})
        if not jd:
            continue

        role_cat = jd.get("role_category", "unknown")
        patterns = role_patterns[role_cat]

        patterns["count"] += 1

        # Sample titles and companies (first 10 each)
        if len(patterns["sample_titles"]) < 10:
            title = job.get("title", "")
            if title and title not in patterns["sample_titles"]:
                patterns["sample_titles"].append(title)

        if len(patterns["sample_companies"]) < 10:
            company = job.get("company", "")
            if company and company not in patterns["sample_companies"]:
                patterns["sample_companies"].append(company)

        # Aggregate technical skills
        for skill in jd.get("technical_skills", []):
            if skill:
                patterns["technical_skills"][skill.lower()] += 1

        # Aggregate soft skills
        for skill in jd.get("soft_skills", []):
            if skill:
                patterns["soft_skills"][skill.lower()] += 1

        # Aggregate keywords
        for keyword in jd.get("top_keywords", []):
            if keyword:
                patterns["top_keywords"][keyword.lower()] += 1

        # Collect pain points (unique, max 30)
        for pain in jd.get("implied_pain_points", []):
            if pain and len(patterns["implied_pain_points"]) < 30:
                if pain not in patterns["implied_pain_points"]:
                    patterns["implied_pain_points"].append(pain)

        # Collect success metrics (unique, max 20)
        for metric in jd.get("success_metrics", []):
            if metric and len(patterns["success_metrics"]) < 20:
                if metric not in patterns["success_metrics"]:
                    patterns["success_metrics"].append(metric)

        # Collect responsibilities (unique, max 30)
        for resp in jd.get("responsibilities", []):
            if resp and len(patterns["responsibilities"]) < 30:
                if resp not in patterns["responsibilities"]:
                    patterns["responsibilities"].append(resp)

        # Collect competency weights
        weights = jd.get("competency_weights", {})
        for key in ["delivery", "process", "architecture", "leadership"]:
            if key in weights and isinstance(weights[key], (int, float)):
                patterns["competency_weights"][key].append(weights[key])

        # Count seniority levels
        seniority = jd.get("seniority_level", "unknown")
        if seniority:
            patterns["seniority_levels"][seniority] += 1

    # Convert defaultdicts and compute statistics
    result = {}
    for role_cat, patterns in role_patterns.items():
        if role_cat is None:
            role_cat = "unknown"

        # Sort skills by frequency
        sorted_tech = sorted(
            patterns["technical_skills"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:25]
        sorted_soft = sorted(
            patterns["soft_skills"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:15]
        sorted_keywords = sorted(
            patterns["top_keywords"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:25]

        # Compute competency weight averages
        weight_stats = {}
        for key, values in patterns["competency_weights"].items():
            if values:
                weight_stats[key] = {
                    "avg": round(sum(values) / len(values), 1),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }

        result[role_cat] = {
            "count": patterns["count"],
            "sample_titles": patterns["sample_titles"],
            "sample_companies": patterns["sample_companies"],
            "top_technical_skills": sorted_tech,
            "top_soft_skills": sorted_soft,
            "top_keywords": sorted_keywords,
            "implied_pain_points": patterns["implied_pain_points"],
            "success_metrics": patterns["success_metrics"],
            "sample_responsibilities": patterns["responsibilities"][:15],
            "competency_weight_stats": weight_stats,
            "seniority_distribution": dict(patterns["seniority_levels"]),
        }

    return result


def print_pattern_summary(patterns: Dict[str, Dict[str, Any]]):
    """Print a summary of aggregated patterns."""
    print("\n" + "=" * 70)
    print("JD PATTERN ANALYSIS SUMMARY")
    print("=" * 70)

    # Sort by count
    sorted_roles = sorted(patterns.items(), key=lambda x: x[1]["count"], reverse=True)

    for role_cat, data in sorted_roles:
        print(f"\n{'─' * 70}")
        print(f"📋 {role_cat.upper().replace('_', ' ')} ({data['count']} jobs)")
        print(f"{'─' * 70}")

        # Sample titles
        print(f"\n  📝 Sample Titles:")
        for title in data["sample_titles"][:5]:
            print(f"     • {title}")

        # Competency weights
        if data["competency_weight_stats"]:
            print(f"\n  ⚖️  Competency Weights (average):")
            for key, stats in data["competency_weight_stats"].items():
                print(f"     • {key.capitalize()}: {stats['avg']}% (range: {stats['min']}-{stats['max']})")

        # Top technical skills
        print(f"\n  🔧 Top Technical Skills:")
        for skill, count in data["top_technical_skills"][:10]:
            pct = count / data["count"] * 100
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            print(f"     {bar} {skill}: {count} ({pct:.0f}%)")

        # Top keywords
        print(f"\n  🏷️  Top ATS Keywords:")
        for kw, count in data["top_keywords"][:10]:
            pct = count / data["count"] * 100
            print(f"     • {kw}: {count} ({pct:.0f}%)")

        # Pain points
        if data["implied_pain_points"]:
            print(f"\n  🎯 Common Pain Points:")
            for pain in data["implied_pain_points"][:5]:
                print(f"     • {pain}")

    # Cross-role summary
    print("\n" + "=" * 70)
    print("CROSS-ROLE ANALYSIS")
    print("=" * 70)

    # Aggregate all skills across roles
    all_tech = defaultdict(int)
    all_keywords = defaultdict(int)
    for role_data in patterns.values():
        for skill, count in role_data["top_technical_skills"]:
            all_tech[skill] += count
        for kw, count in role_data["top_keywords"]:
            all_keywords[kw] += count

    print("\n  🌐 Most Common Technical Skills (all roles):")
    for skill, count in sorted(all_tech.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"     • {skill}: {count}")

    print("\n  🏷️  Most Common ATS Keywords (all roles):")
    for kw, count in sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"     • {kw}: {count}")


def save_pattern_analysis(patterns: Dict[str, Dict[str, Any]], output_path: Path):
    """Save pattern analysis to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(patterns, f, indent=2)
    logger.info(f"Saved pattern analysis to {output_path}")


def main():
    """Run Phase 2: Aggregate patterns from existing extractions."""
    print("\n" + "=" * 70)
    print("PHASE 2: Aggregate JD Patterns from MongoDB")
    print("=" * 70)

    # Connect to MongoDB
    client = get_mongodb_client()

    # Aggregate patterns
    patterns = aggregate_patterns_from_mongodb(client)

    # Save to JSON
    output_path = project_root / "reports" / "jd-pattern-analysis.json"
    save_pattern_analysis(patterns, output_path)

    # Print summary
    print_pattern_summary(patterns)

    # Close connection
    client.close()

    print("\n" + "=" * 70)
    print("✅ Phase 2 complete! Pattern analysis saved to reports/jd-pattern-analysis.json")
    print("🚀 Ready to proceed with Phase 3: Analyze current bullet points")
    print("=" * 70)


if __name__ == "__main__":
    main()
