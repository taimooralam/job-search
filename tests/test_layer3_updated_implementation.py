"""
Test the updated Layer 3 implementation with Phase 5.2 improvements.

Improvements included:
1. Content quality gate
2. Keyword-based search queries (not LLM-style)
3. Enhanced prompts with reasoning block
4. Increased character limits
5. Quality filtering
"""

import json
import logging
from bson.objectid import ObjectId
from pymongo import MongoClient

from src.common.config import Config
from src.layer3.company_researcher import CompanyResearcher
from src.common.state import JobState


def main():
    """Test updated Layer 3 implementation"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*100)
    print("LAYER 3 UPDATED IMPLEMENTATION TEST (Phase 5.2)")
    print("="*100)

    # Fetch job
    print(f"\n1. Fetching job from MongoDB...")
    mongo_client = MongoClient(Config.MONGODB_URI)
    db = mongo_client["jobs"]
    job = db["level-2"].find_one({"_id": ObjectId("6929c97b45fa3c355f84ba2d")})

    company = job.get("company") or job.get("firm")
    print(f"   Company: {company}")
    print(f"   Role: {job.get('title')}")

    # Create JobState
    state: JobState = {
        "run_id": "test-layer3-phase5.2",
        "job_id": str(job["_id"]),
        "company": company,
        "role": job.get("title", ""),
        "job_description": job.get("job_description", ""),
        "job_url": job.get("jobURL", ""),
        # Add mock selected_stars for STAR-aware prompts
        "selected_stars": [
            {
                "domain_areas": [".NET", "Microservices", "Backend Architecture"],
                "outcome_types": ["Team Scaling", "Performance Optimization"]
            }
        ]
    }

    print(f"\n2. Running Layer 3 Company Researcher (Phase 5.2)...")
    researcher = CompanyResearcher()
    results = researcher.research_company(state)

    # Display results
    print("\n" + "="*100)
    print("RESULTS")
    print("="*100)

    if results.get("company_research"):
        research = results["company_research"]

        # Reasoning block (if present)
        if "reasoning" in research:
            print(f"\n📊 REASONING BLOCK:")
            reasoning = research["reasoning"]
            print(f"  Sources Analyzed: {len(reasoning.get('sources_analyzed', []))}")
            for idx, source in enumerate(reasoning.get('sources_analyzed', []), 1):
                quality = reasoning.get('source_quality', {}).get(source, 'unknown')
                print(f"    {idx}. {source} [quality: {quality}]")

            missing = reasoning.get('missing_context', [])
            assumptions = reasoning.get('assumptions', [])
            confidence = reasoning.get('confidence_level', 'unknown')

            if missing:
                print(f"\n  Missing Context:")
                for item in missing:
                    print(f"    - {item}")

            if assumptions:
                print(f"\n  Assumptions:")
                for item in assumptions:
                    print(f"    - {item}")

            print(f"\n  Confidence Level: {confidence}")

        # Summary
        print(f"\n📝 SUMMARY:")
        print(f"  {research['summary']}")

        # Signals
        signals = research.get('signals', [])
        print(f"\n🎯 SIGNALS ({len(signals)} found):")
        if signals:
            for idx, signal in enumerate(signals, 1):
                print(f"\n  {idx}. [{signal['type'].upper()}] {signal['description']}")
                print(f"     Date: {signal['date']}")
                print(f"     Source: {signal['source'][:70]}...")
                if signal.get('business_context'):
                    print(f"     💡 Context: {signal['business_context']}")
        else:
            print("  (none extracted)")

        print(f"\n🔗 PRIMARY URL: {research['url']}")

    else:
        print("\n⚠️  No company_research in results (legacy format or error)")
        if results.get("company_summary"):
            print(f"\nSummary (legacy): {results['company_summary']}")
        if results.get("errors"):
            print(f"\nErrors: {results['errors']}")

    print("\n" + "="*100)
    print("PHASE 5.2 IMPROVEMENTS APPLIED:")
    print("="*100)
    print("  ✅ Content quality gate (filters boilerplate)")
    print("  ✅ Keyword-based search queries (vs LLM-style)")
    print("  ✅ Enhanced prompts with reasoning block")
    print("  ✅ Few-shot examples")
    print("  ✅ Increased character limits (3000 chars/source, 8000 total)")
    print("  ✅ STAR-aware prompts (when candidate context available)")
    print("  ✅ Quality filtering (only medium/high sources)")
    print("\n" + "="*100)
    print("TEST COMPLETE")
    print("="*100 + "\n")


if __name__ == "__main__":
    main()
