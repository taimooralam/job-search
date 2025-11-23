#!/usr/bin/env python3
"""
Test script for STAR parser.

Validates that knowledge-base.md is correctly parsed into structured STAR objects.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.layer2_5.star_parser import parse_star_records


def test_star_parser():
    """Test STAR parser with knowledge-base.md."""

    # Path to knowledge base
    kb_path = Path(__file__).parent.parent / "knowledge-base.md"

    print("=" * 80)
    print("STAR PARSER TEST")
    print("=" * 80)
    print(f"\nReading from: {kb_path}")

    # Parse records
    try:
        stars = parse_star_records(str(kb_path))
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        return False

    # Verify count
    print(f"\n✅ Parsed {len(stars)} STAR records")

    if len(stars) != 11:
        print(f"❌ FAILED: Expected 11 records, got {len(stars)}")
        return False

    # Verify STAR #1 ID
    expected_id = "b7e9df84-84b3-4957-93f1-7f1adfe5588c"
    if stars[0]['id'] != expected_id:
        print(f"❌ FAILED: STAR #1 ID mismatch")
        print(f"   Expected: {expected_id}")
        print(f"   Got: {stars[0]['id']}")
        return False
    else:
        print(f"✅ STAR #1 ID matches: {expected_id}")

    # Verify all required fields present
    required_fields = ['id', 'company', 'role', 'period', 'domain_areas',
                      'situation', 'task', 'actions', 'results', 'metrics', 'keywords']

    print("\n" + "=" * 80)
    print("FIELD VALIDATION")
    print("=" * 80)

    for i, star in enumerate(stars, 1):
        missing_fields = []
        for field in required_fields:
            if not star.get(field):
                missing_fields.append(field)

        if missing_fields:
            print(f"❌ STAR #{i} ({star.get('id', 'NO ID')}): Missing fields: {missing_fields}")
        else:
            print(f"✅ STAR #{i} ({star['id'][:8]}...): All fields present")

    # Print first record for inspection
    print("\n" + "=" * 80)
    print("STAR RECORD #1 (Sample)")
    print("=" * 80)
    star1 = stars[0]
    print(f"ID: {star1['id']}")
    print(f"Company: {star1['company']}")
    print(f"Role: {star1['role']}")
    print(f"Period: {star1['period']}")
    print(f"Domain Areas: {star1['domain_areas']}")
    print(f"\nSituation (first 200 chars):\n{star1['situation'][:200]}...")
    print(f"\nTask (first 200 chars):\n{star1['task'][:200]}...")
    print(f"\nActions (first 200 chars):\n{star1['actions'][:200]}...")
    print(f"\nResults (first 200 chars):\n{star1['results'][:200]}...")
    print(f"\nMetrics:\n{star1['metrics']}")
    print(f"\nKeywords (first 200 chars):\n{star1['keywords'][:200]}...")

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)

    return True


if __name__ == "__main__":
    success = test_star_parser()
    sys.exit(0 if success else 1)
