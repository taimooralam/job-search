#!/usr/bin/env python3
"""
STAR Library Validation Script

Validates that all STAR records in knowledge-base.md:
1. Parse correctly into canonical STARRecord schema
2. Have all required fields populated
3. Include pain_points_addressed (1-3 items)
4. Include outcome_types (1+ items)
5. Have quantified metrics
6. Meet quality standards for pipeline use
"""

import sys
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.star_parser import parse_star_records, validate_star_record
from src.common.types import STARRecord, OUTCOME_TYPES


def validate_all_stars() -> bool:
    """Validate all STAR records and report results."""

    kb_path = Path(__file__).parent.parent / "knowledge-base.md"

    print("=" * 80)
    print("STAR LIBRARY VALIDATION")
    print("=" * 80)
    print(f"\nKnowledge Base: {kb_path}")

    # Parse all records
    try:
        stars = parse_star_records(str(kb_path))
        print(f"✅ Successfully parsed {len(stars)} STAR records\n")
    except Exception as e:
        print(f"❌ FAILED to parse knowledge base: {e}")
        return False

    # Expected count
    expected_count = 11
    if len(stars) != expected_count:
        print(f"⚠️  WARNING: Expected {expected_count} records, got {len(stars)}")

    # Validate each STAR
    print("=" * 80)
    print("PER-RECORD VALIDATION")
    print("=" * 80)

    all_valid = True
    validation_summary = []

    for i, star in enumerate(stars, 1):
        print(f"\n--- STAR #{i}: {star['company']} - {star['role_title'][:40]}...")
        print(f"    ID: {star['id']}")

        # Run built-in validator
        issues = validate_star_record(star)

        # Additional checks
        if len(star['pain_points_addressed']) == 0:
            issues.append("No pain points addressed")
        elif len(star['pain_points_addressed']) > 3:
            issues.append(f"Too many pain points ({len(star['pain_points_addressed'])} > 3)")

        if len(star['outcome_types']) == 0:
            issues.append("No outcome types specified")

        # Validate outcome types against known list
        invalid_outcomes = [ot for ot in star['outcome_types'] if ot not in OUTCOME_TYPES]
        if invalid_outcomes:
            issues.append(f"Invalid outcome types: {invalid_outcomes}")

        # Check condensed version quality
        if star['condensed_version'] and len(star['condensed_version']) < 50:
            issues.append("Condensed version too short (< 50 chars)")

        # Report results
        if issues:
            all_valid = False
            print(f"    ❌ ISSUES: {len(issues)}")
            for issue in issues:
                print(f"       • {issue}")
            validation_summary.append((i, star['id'][:8], "FAILED", len(issues)))
        else:
            print(f"    ✅ VALID")
            validation_summary.append((i, star['id'][:8], "PASSED", 0))

    # Summary report
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    passed_count = sum(1 for _, _, status, _ in validation_summary if status == "PASSED")
    failed_count = len(stars) - passed_count

    print(f"\nTotal Records: {len(stars)}")
    print(f"✅ Passed: {passed_count}")
    print(f"❌ Failed: {failed_count}")

    if all_valid:
        print("\n🎉 ALL STAR RECORDS ARE VALID!")
    else:
        print("\n⚠️  SOME STAR RECORDS NEED ATTENTION")

    # Detailed statistics
    print("\n" + "=" * 80)
    print("LIBRARY STATISTICS")
    print("=" * 80)

    total_pain_points = sum(len(s['pain_points_addressed']) for s in stars)
    total_outcome_types = sum(len(s['outcome_types']) for s in stars)
    total_metrics = sum(len(s['metrics']) for s in stars)
    total_hard_skills = sum(len(s['hard_skills']) for s in stars)
    total_actions = sum(len(s['actions']) for s in stars)

    print(f"\nPain Points: {total_pain_points} total ({total_pain_points/len(stars):.1f} avg per STAR)")
    print(f"Outcome Types: {total_outcome_types} total ({total_outcome_types/len(stars):.1f} avg per STAR)")
    print(f"Metrics: {total_metrics} total ({total_metrics/len(stars):.1f} avg per STAR)")
    print(f"Hard Skills: {total_hard_skills} total ({total_hard_skills/len(stars):.1f} avg per STAR)")
    print(f"Actions: {total_actions} total ({total_actions/len(stars):.1f} avg per STAR)")

    # Outcome type distribution
    outcome_counts = {}
    for star in stars:
        for ot in star['outcome_types']:
            outcome_counts[ot] = outcome_counts.get(ot, 0) + 1

    print(f"\nOutcome Type Distribution:")
    for ot, count in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        print(f"  • {ot}: {count} STARs")

    # Sample pain points
    print(f"\nSample Pain Points (first 3):")
    sample_count = 0
    for star in stars:
        for pain in star['pain_points_addressed'][:1]:
            print(f"  • {pain}")
            sample_count += 1
            if sample_count >= 3:
                break
        if sample_count >= 3:
            break

    print("\n" + "=" * 80)

    return all_valid


if __name__ == "__main__":
    success = validate_all_stars()
    sys.exit(0 if success else 1)
