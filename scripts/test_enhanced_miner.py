"""
Test the enhanced Layer 2 Pain Point Miner with a real job.
"""

import sys
import json
from bson import ObjectId
from pymongo import MongoClient

sys.path.insert(0, ".")

from src.common.config import Config
from src.layer2.pain_point_miner import PainPointMiner, detect_domain


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_enhanced_miner.py <job_id>")
        sys.exit(1)

    job_id = sys.argv[1]

    print(f"\n🔍 Fetching job {job_id} from MongoDB...")

    # Connect to correct database
    client = MongoClient(Config.MONGODB_URI)
    db = client['jobs']
    collection = db['level-2']

    job = collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        print(f"❌ Job not found: {job_id}")
        sys.exit(1)

    title = job.get("title", "Unknown")
    company = job.get("company", "Unknown")
    job_description = job.get("job_description", "")

    print(f"✅ Found: {title} at {company}")
    print(f"   Description length: {len(job_description)} chars")

    # Detect domain
    domain = detect_domain(title, job_description)
    print(f"   Detected domain: {domain.value}")

    # Create mock state
    state = {
        "job_id": str(job["_id"]),
        "title": title,
        "company": company,
        "job_description": job_description,
        "run_id": "test-run",
        "errors": []
    }

    # Run enhanced miner
    print(f"\n🔄 Running ENHANCED miner...")

    miner = PainPointMiner(use_enhanced_format=True)
    result = miner.extract_pain_points(state)

    print(f"\n{'='*70}")
    print("  ENHANCED MINER OUTPUT")
    print(f"{'='*70}")

    if result.get("why_now"):
        print(f"\n❓ WHY NOW: {result['why_now']}")

    if result.get("reasoning_summary"):
        print(f"\n💭 REASONING SUMMARY: {result['reasoning_summary']}")

    print(f"\n🎯 PAIN POINTS ({len(result.get('pain_points', []))}):")
    for i, point in enumerate(result.get('pain_points', []), 1):
        if isinstance(point, dict):
            conf = point.get('confidence', 'unknown')
            text = point.get('text', str(point))
            evidence = point.get('evidence', 'N/A')
            print(f"  {i}. [{conf.upper() if isinstance(conf, str) else conf.value.upper()}] {text}")
            print(f"      📎 Evidence: {evidence}")
        else:
            print(f"  {i}. {point}")

    print(f"\n📈 STRATEGIC NEEDS ({len(result.get('strategic_needs', []))}):")
    for i, need in enumerate(result.get('strategic_needs', []), 1):
        if isinstance(need, dict):
            conf = need.get('confidence', 'unknown')
            text = need.get('text', str(need))
            print(f"  {i}. [{conf.upper() if isinstance(conf, str) else conf.value.upper()}] {text}")
        else:
            print(f"  {i}. {need}")

    print(f"\n⚠️  RISKS IF UNFILLED ({len(result.get('risks_if_unfilled', []))}):")
    for i, risk in enumerate(result.get('risks_if_unfilled', []), 1):
        if isinstance(risk, dict):
            conf = risk.get('confidence', 'unknown')
            text = risk.get('text', str(risk))
            print(f"  {i}. [{conf.upper() if isinstance(conf, str) else conf.value.upper()}] {text}")
        else:
            print(f"  {i}. {risk}")

    print(f"\n📏 SUCCESS METRICS ({len(result.get('success_metrics', []))}):")
    for i, metric in enumerate(result.get('success_metrics', []), 1):
        if isinstance(metric, dict):
            conf = metric.get('confidence', 'unknown')
            text = metric.get('text', str(metric))
            print(f"  {i}. [{conf.upper() if isinstance(conf, str) else conf.value.upper()}] {text}")
        else:
            print(f"  {i}. {metric}")

    # Count confidence distribution
    all_items = (
        result.get('pain_points', []) +
        result.get('strategic_needs', []) +
        result.get('risks_if_unfilled', []) +
        result.get('success_metrics', [])
    )

    if all_items and isinstance(all_items[0], dict):
        confidence_counts = {'high': 0, 'medium': 0, 'low': 0}
        for item in all_items:
            conf = item.get('confidence', 'medium')
            if hasattr(conf, 'value'):
                conf = conf.value
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

        print(f"\n📊 CONFIDENCE DISTRIBUTION:")
        print(f"   🟢 High: {confidence_counts.get('high', 0)}")
        print(f"   🟡 Medium: {confidence_counts.get('medium', 0)}")
        print(f"   🔴 Low: {confidence_counts.get('low', 0)}")

    print(f"\n{'='*70}")
    print("  TEST COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
