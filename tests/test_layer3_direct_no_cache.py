"""
Direct test of Phase 5.2 improvements - NO CACHE

Tests scraping and signal extraction directly without cache interference.
"""

import json
import logging
from src.layer3.company_researcher import CompanyResearcher


def main():
    """Test Phase 5.2 improvements directly"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*100)
    print("PHASE 5.2 DIRECT TEST (NO CACHE)")
    print("="*100)

    company = "KAIZEN GAMING"
    print(f"\nCompany: {company}")

    researcher = CompanyResearcher()

    # Step 1: Multi-source scraping with quality gate
    print(f"\n1. Scraping with keyword-based queries and quality gate...")
    scraped_data = researcher._scrape_multiple_sources(company)

    print(f"\n✓ Scraped {len(scraped_data)} high/medium quality source(s)")
    for source_name, data in scraped_data.items():
        print(f"  - {source_name}: {data['url']} [quality: {data['quality']}]")
        print(f"    Content length: {len(data['content'])} chars")
        print(f"    Preview: {data['content'][:150]}...")

    if not scraped_data:
        print("\n❌ No sources scraped. Stopping test.")
        return

    # Step 2: Signal extraction with enhanced prompt
    print(f"\n2. Extracting signals with Phase 5.2 enhanced prompt...")
    try:
        result = researcher._analyze_company_signals(
            company=company,
            scraped_data=scraped_data,
            star_domains=".NET, Microservices, Backend Architecture",
            star_outcomes="Team Scaling, Performance Optimization"
        )

        print(f"\n✅ Signal extraction succeeded!")

        # Show reasoning
        if result.reasoning:
            print(f"\n📊 REASONING:")
            print(f"  Sources: {result.reasoning.sources_analyzed}")
            print(f"  Quality: {result.reasoning.source_quality}")
            print(f"  Missing: {result.reasoning.missing_context}")
            print(f"  Assumptions: {result.reasoning.assumptions}")
            print(f"  Confidence: {result.reasoning.confidence_level}")

        # Show summary
        print(f"\n📝 SUMMARY:")
        print(f"  {result.summary}")

        # Show signals
        print(f"\n🎯 SIGNALS ({len(result.signals)} found):")
        for idx, signal in enumerate(result.signals, 1):
            print(f"\n  {idx}. [{signal.type.upper()}] {signal.description}")
            print(f"     Date: {signal.date}")
            print(f"     Source: {signal.source[:70]}...")
            if signal.business_context:
                print(f"     💡 Context: {signal.business_context}")

        print(f"\n🔗 URL: {result.url}")

    except Exception as e:
        print(f"\n❌ Signal extraction failed:")
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*100)
    print("TEST COMPLETE")
    print("="*100 + "\n")


if __name__ == "__main__":
    main()
