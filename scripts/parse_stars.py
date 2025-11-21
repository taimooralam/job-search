#!/usr/bin/env python3
"""
STAR Library Parser CLI

Parses knowledge-base.md into canonical STARRecord objects and exports to JSON.
This is the CLI tool required by ROADMAP Phase 2.1 for regenerating the canonical
STAR library from the human-authored knowledge-base.md source of truth.

Usage:
    python scripts/parse_stars.py                    # Parse and display summary
    python scripts/parse_stars.py --export           # Export to star_records.json
    python scripts/parse_stars.py --validate         # Run full validation
    python scripts/parse_stars.py --stats            # Show detailed statistics
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.star_parser import parse_star_records, validate_star_record
from src.common.types import STARRecord, OUTCOME_TYPES
from src.common.config import Config


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Parse knowledge-base.md into canonical STAR records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/parse_stars.py                    # Parse and display summary
    python scripts/parse_stars.py --export           # Export to star_records.json
    python scripts/parse_stars.py --export --output custom.json
    python scripts/parse_stars.py --validate         # Run full validation
    python scripts/parse_stars.py --stats            # Show detailed statistics
        """
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export parsed STAR records to JSON file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="star_records.json",
        help="Output JSON file path (default: star_records.json)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run full validation on all STAR records"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show detailed statistics about the STAR library"
    )
    parser.add_argument(
        "--kb-path",
        type=str,
        default=None,
        help="Path to knowledge-base.md (default: from Config or ./knowledge-base.md)"
    )
    return parser.parse_args()


def get_kb_path(args) -> Path:
    """Determine the knowledge base path."""
    if args.kb_path:
        return Path(args.kb_path)
    if hasattr(Config, 'KNOWLEDGE_BASE_PATH') and Config.KNOWLEDGE_BASE_PATH:
        return Path(Config.KNOWLEDGE_BASE_PATH)
    return Path(__file__).parent.parent / "knowledge-base.md"


def export_to_json(stars: List[STARRecord], output_path: str) -> None:
    """Export STAR records to JSON file."""
    # Convert to list of dicts (handling any non-serializable types)
    records = []
    for star in stars:
        record = dict(star)
        # Remove embeddings if present (they're too large for JSON export)
        if 'embedding' in record and record['embedding']:
            record['embedding'] = f"[{len(record['embedding'])} floats]"
        records.append(record)

    export_data = {
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
        "record_count": len(records),
        "schema": "canonical_star_record_v1",
        "records": records
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Exported {len(records)} STAR records to {output_path}")


def show_statistics(stars: List[STARRecord]) -> None:
    """Display detailed statistics about the STAR library."""
    print("\n" + "=" * 80)
    print("STAR LIBRARY STATISTICS")
    print("=" * 80)

    # Basic counts
    print(f"\n📊 Basic Metrics:")
    print(f"   Total STAR records: {len(stars)}")
    print(f"   Companies represented: {len(set(s['company'] for s in stars))}")
    print(f"   Unique role titles: {len(set(s['role_title'] for s in stars))}")

    # Content metrics
    total_pain_points = sum(len(s.get('pain_points_addressed', [])) for s in stars)
    total_outcome_types = sum(len(s.get('outcome_types', [])) for s in stars)
    total_metrics = sum(len(s.get('metrics', [])) for s in stars)
    total_hard_skills = sum(len(s.get('hard_skills', [])) for s in stars)
    total_soft_skills = sum(len(s.get('soft_skills', [])) for s in stars)
    total_actions = sum(len(s.get('actions', [])) for s in stars)

    print(f"\n📈 Content Distribution (avg per STAR):")
    print(f"   Pain Points Addressed: {total_pain_points/len(stars):.1f}")
    print(f"   Outcome Types: {total_outcome_types/len(stars):.1f}")
    print(f"   Quantified Metrics: {total_metrics/len(stars):.1f}")
    print(f"   Hard Skills: {total_hard_skills/len(stars):.1f}")
    print(f"   Soft Skills: {total_soft_skills/len(stars):.1f}")
    print(f"   Actions: {total_actions/len(stars):.1f}")

    # Outcome type distribution
    outcome_counts: Dict[str, int] = {}
    for star in stars:
        for ot in star.get('outcome_types', []):
            outcome_counts[ot] = outcome_counts.get(ot, 0) + 1

    print(f"\n🎯 Outcome Type Coverage:")
    for ot, count in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"   {ot:30s} {bar} ({count})")

    # Domain coverage
    domain_counts: Dict[str, int] = {}
    for star in stars:
        for domain in star.get('domain_areas', []):
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    print(f"\n🌐 Domain Coverage (top 10):")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:10]:
        bar = "█" * count
        print(f"   {domain:30s} {bar} ({count})")

    # Skill coverage
    skill_counts: Dict[str, int] = {}
    for star in stars:
        for skill in star.get('hard_skills', []):
            skill_counts[skill] = skill_counts.get(skill, 0) + 1

    print(f"\n🔧 Top Hard Skills (top 10):")
    for skill, count in sorted(skill_counts.items(), key=lambda x: -x[1])[:10]:
        bar = "█" * count
        print(f"   {skill:30s} {bar} ({count})")


def validate_stars(stars: List[STARRecord]) -> bool:
    """Validate all STAR records and report issues."""
    print("\n" + "=" * 80)
    print("STAR VALIDATION REPORT")
    print("=" * 80)

    all_valid = True
    issues_by_record: Dict[str, List[str]] = {}

    for star in stars:
        issues = validate_star_record(star)

        # Additional quality checks
        if len(star.get('pain_points_addressed', [])) == 0:
            issues.append("Missing pain_points_addressed")
        if len(star.get('outcome_types', [])) == 0:
            issues.append("Missing outcome_types")
        if len(star.get('metrics', [])) == 0:
            issues.append("Missing quantified metrics")

        # Validate outcome types
        invalid_outcomes = [ot for ot in star.get('outcome_types', []) if ot not in OUTCOME_TYPES]
        if invalid_outcomes:
            issues.append(f"Invalid outcome_types: {invalid_outcomes}")

        if issues:
            all_valid = False
            issues_by_record[star['id']] = issues

    # Report
    valid_count = len(stars) - len(issues_by_record)
    print(f"\n✅ Valid records: {valid_count}/{len(stars)}")
    print(f"❌ Records with issues: {len(issues_by_record)}/{len(stars)}")

    if issues_by_record:
        print("\n📋 Issues by record:")
        for star_id, issues in issues_by_record.items():
            star = next((s for s in stars if s['id'] == star_id), None)
            if star:
                print(f"\n   {star['company']} - {star['role_title'][:30]}... (ID: {star_id[:8]}...)")
            for issue in issues:
                print(f"      • {issue}")

    return all_valid


def main():
    """Main entry point."""
    args = parse_args()

    # Determine knowledge base path
    kb_path = get_kb_path(args)

    print("=" * 80)
    print("STAR LIBRARY PARSER")
    print("=" * 80)
    print(f"\n📁 Knowledge Base: {kb_path}")

    if not kb_path.exists():
        print(f"\n❌ ERROR: Knowledge base file not found: {kb_path}")
        sys.exit(1)

    # Parse STAR records
    try:
        stars = parse_star_records(str(kb_path))
        print(f"✅ Successfully parsed {len(stars)} STAR records")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to parse knowledge base: {e}")
        sys.exit(1)

    # Brief summary
    print(f"\n📊 Quick Summary:")
    for i, star in enumerate(stars, 1):
        role = star.get('role_title', 'Unknown')[:40]
        metrics = len(star.get('metrics', []))
        pains = len(star.get('pain_points_addressed', []))
        print(f"   {i:2d}. {star['company']:20s} - {role:40s} ({metrics} metrics, {pains} pains)")

    # Handle actions
    if args.validate:
        validate_stars(stars)

    if args.stats:
        show_statistics(stars)

    if args.export:
        export_to_json(stars, args.output)

    # If no specific action, show usage hint
    if not (args.validate or args.stats or args.export):
        print("\n💡 TIP: Use --validate, --stats, or --export for more detailed output")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
