#!/usr/bin/env python3
"""
Test script for MongoDB STAR records integration.

Tests:
1. Connection to MongoDB
2. STAR record insertion
3. STAR record retrieval
4. Search by pain points
5. Search by skills
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.database import db
from src.common.star_parser import parse_star_records
from src.common.config import Config


def test_connection():
    """Test 1: MongoDB connection."""
    print("\n" + "=" * 60)
    print("TEST 1: MongoDB Connection")
    print("=" * 60)

    try:
        db.connect()
        print(f"✅ Connected to database: {db.db.name}")
        print(f"✅ Collections: {db.db.list_collection_names()}")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_star_count():
    """Test 2: Count STAR records in database."""
    print("\n" + "=" * 60)
    print("TEST 2: STAR Record Count")
    print("=" * 60)

    try:
        count = db.star_records.count_documents({})
        print(f"✅ Total STAR records in database: {count}")

        if count == 0:
            print("⚠️  No STAR records found. Run load_stars_to_mongodb.py first")

        return True
    except Exception as e:
        print(f"❌ Count failed: {e}")
        return False


def test_retrieval():
    """Test 3: Retrieve STAR records."""
    print("\n" + "=" * 60)
    print("TEST 3: STAR Record Retrieval")
    print("=" * 60)

    try:
        # Get all STARs
        all_stars = db.get_all_star_records()
        print(f"✅ Retrieved {len(all_stars)} STAR records")

        if len(all_stars) > 0:
            # Show first STAR
            star = all_stars[0]
            print(f"\n📄 Sample STAR (first record):")
            print(f"   ID: {star['id']}")
            print(f"   Company: {star['company']}")
            print(f"   Role: {star['role_title']}")
            print(f"   Period: {star['period']}")
            print(f"   Pain Points: {len(star.get('pain_points_addressed', []))}")
            print(f"   Outcome Types: {len(star.get('outcome_types', []))}")

        return True
    except Exception as e:
        print(f"❌ Retrieval failed: {e}")
        return False


def test_pain_point_search():
    """Test 4: Search by pain points."""
    print("\n" + "=" * 60)
    print("TEST 4: Search by Pain Points")
    print("=" * 60)

    try:
        # Test pain point searches
        test_cases = [
            "Legacy monolith causing slow delivery cycles and high deployment risk",
            "Regulatory compliance risk",
            "Technical debt"
        ]

        for pain in test_cases:
            results = db.search_stars_by_pain_points([pain])
            print(f"\n🔍 Search: '{pain[:50]}...'")
            print(f"   ✅ Found {len(results)} matching STARs")

            if results:
                for star in results[:2]:  # Show first 2 matches
                    print(f"      - {star['id']}: {star['role_title']}")

        return True
    except Exception as e:
        print(f"❌ Pain point search failed: {e}")
        return False


def test_skill_search():
    """Test 5: Search by skills."""
    print("\n" + "=" * 60)
    print("TEST 5: Search by Skills")
    print("=" * 60)

    try:
        # Test skill searches
        test_cases = [
            ["Python", "TypeScript"],
            ["Leadership", "Stakeholder Management"],
            ["AWS", "Kubernetes"]
        ]

        for skills in test_cases:
            results = db.search_stars_by_skills(skills)
            print(f"\n🔍 Search: {skills}")
            print(f"   ✅ Found {len(results)} matching STARs")

            if results:
                for star in results[:2]:  # Show first 2 matches
                    print(f"      - {star['id']}: {star['role_title']}")

        return True
    except Exception as e:
        print(f"❌ Skill search failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 MONGODB STAR RECORDS TEST SUITE")
    print("=" * 60)

    tests = [
        ("Connection", test_connection),
        ("Count", test_star_count),
        ("Retrieval", test_retrieval),
        ("Pain Point Search", test_pain_point_search),
        ("Skill Search", test_skill_search)
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        if test_func():
            passed += 1
        else:
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")
    print("=" * 60)

    if failed == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        db.disconnect()
