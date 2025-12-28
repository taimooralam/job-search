#!/usr/bin/env python3
"""
Analyze master-cv bullet points against JD patterns from MongoDB.

This script:
1. Loads aggregated JD patterns from reports/jd-pattern-analysis.json
2. Loads all role files from data/master-cv/roles/
3. Scores each achievement against each target role
4. Generates structured analysis output

Usage:
    python scripts/analyze_bullets_vs_jds.py
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent

# Target roles we're analyzing for
TARGET_ROLES = [
    "engineering_manager",
    "staff_principal_engineer",
    "director_of_engineering",
    "head_of_engineering",
    "tech_lead",
    "senior_engineer",
    "cto",
    "vp_engineering",
]

# Competency ideal weights per role (from cv evaluation guidelines)
COMPETENCY_IDEALS = {
    "engineering_manager": {"leadership": 45, "delivery": 30, "process": 15, "architecture": 10},
    "staff_principal_engineer": {"architecture": 45, "delivery": 30, "process": 15, "leadership": 10},
    "director_of_engineering": {"leadership": 40, "architecture": 25, "delivery": 20, "process": 15},
    "head_of_engineering": {"leadership": 35, "architecture": 30, "delivery": 20, "process": 15},
    "tech_lead": {"architecture": 35, "delivery": 35, "leadership": 20, "process": 10},
    "senior_engineer": {"delivery": 45, "architecture": 30, "process": 15, "leadership": 10},
    "cto": {"architecture": 40, "leadership": 35, "delivery": 15, "process": 10},
    "vp_engineering": {"leadership": 40, "architecture": 30, "delivery": 20, "process": 10},
}

# Format recommendations per role
FORMAT_RECOMMENDATIONS = {
    "engineering_manager": {"primary": "ARIS", "ats_priority": "Moderate"},
    "staff_principal_engineer": {"primary": "ATRIS", "ats_priority": "High"},
    "director_of_engineering": {"primary": "ARIS", "ats_priority": "Moderate"},
    "head_of_engineering": {"primary": "ARIS/Narrative", "ats_priority": "Low"},
    "tech_lead": {"primary": "ATRIS", "ats_priority": "Moderate"},
    "senior_engineer": {"primary": "ATRIS", "ats_priority": "High"},
    "cto": {"primary": "Narrative/Impact", "ats_priority": "Low"},
    "vp_engineering": {"primary": "ARIS", "ats_priority": "Low"},
}


@dataclass
class Achievement:
    """Represents an achievement from a role file."""
    role_file: str
    achievement_id: str
    title: str
    core_fact: str
    variants: Dict[str, str]
    keywords: List[str]


@dataclass
class RolePattern:
    """JD patterns for a specific role category."""
    count: int
    top_technical_skills: List[Tuple[str, int]]
    top_soft_skills: List[Tuple[str, int]]
    top_keywords: List[Tuple[str, int]]
    implied_pain_points: List[str]
    competency_weights: Dict[str, Dict[str, float]]


def load_jd_patterns() -> Dict[str, RolePattern]:
    """Load aggregated JD patterns."""
    pattern_file = PROJECT_ROOT / "reports" / "jd-pattern-analysis.json"
    with open(pattern_file) as f:
        data = json.load(f)

    patterns = {}
    for role, info in data.items():
        if role == "unknown":
            continue
        patterns[role] = RolePattern(
            count=info.get("count", 0),
            top_technical_skills=[(s[0], s[1]) for s in info.get("top_technical_skills", [])],
            top_soft_skills=[(s[0], s[1]) for s in info.get("top_soft_skills", [])],
            top_keywords=[(s[0], s[1]) for s in info.get("top_keywords", [])],
            implied_pain_points=info.get("implied_pain_points", []),
            competency_weights=info.get("competency_weight_stats", {}),
        )
    return patterns


def parse_achievements_from_file(file_path: Path) -> List[Achievement]:
    """Parse achievements from a role markdown file."""
    with open(file_path) as f:
        content = f.read()

    achievements = []
    role_file = file_path.stem

    # Split by achievement headers
    achievement_blocks = re.split(r'### Achievement \d+:', content)

    for i, block in enumerate(achievement_blocks[1:], start=1):
        # Extract title
        title_match = re.search(r'^(.+?)(?:\n|$)', block.strip())
        title = title_match.group(1).strip() if title_match else f"Achievement {i}"

        # Extract core fact
        core_match = re.search(r'\*\*Core Fact\*\*:\s*(.+?)(?:\n\n|\*\*Variants)', block, re.DOTALL)
        core_fact = core_match.group(1).strip() if core_match else ""

        # Extract variants
        variants = {}
        variants_match = re.search(r'\*\*Variants\*\*:\s*\n(.+?)(?:\n\n\*\*Keywords)', block, re.DOTALL)
        if variants_match:
            for line in variants_match.group(1).split('\n'):
                variant_match = re.match(r'-\s*\*\*(\w+)\*\*:\s*(.+)', line.strip())
                if variant_match:
                    variants[variant_match.group(1).lower()] = variant_match.group(2).strip()

        # Extract keywords
        keywords = []
        keywords_match = re.search(r'\*\*Keywords\*\*:\s*(.+?)(?:\n|$)', block)
        if keywords_match:
            keywords = [k.strip().lower() for k in keywords_match.group(1).split(',')]

        achievements.append(Achievement(
            role_file=role_file,
            achievement_id=f"{role_file}_{i}",
            title=title,
            core_fact=core_fact,
            variants=variants,
            keywords=keywords,
        ))

    return achievements


def load_all_achievements() -> List[Achievement]:
    """Load all achievements from all role files."""
    roles_dir = PROJECT_ROOT / "data" / "master-cv" / "roles"
    all_achievements = []

    for role_file in sorted(roles_dir.glob("*.md")):
        achievements = parse_achievements_from_file(role_file)
        all_achievements.extend(achievements)

    return all_achievements


def calculate_keyword_overlap(achievement: Achievement, pattern: RolePattern) -> Tuple[float, List[str], List[str]]:
    """Calculate keyword overlap between achievement and role pattern."""
    achievement_keywords = set(achievement.keywords)

    # Get top keywords from pattern (use top 25)
    pattern_keywords = set(k[0].lower() for k in pattern.top_keywords[:25])
    pattern_tech = set(k[0].lower() for k in pattern.top_technical_skills[:25])
    pattern_soft = set(k[0].lower() for k in pattern.top_soft_skills[:15])

    all_pattern_keywords = pattern_keywords | pattern_tech | pattern_soft

    # Find matches
    matches = achievement_keywords & all_pattern_keywords
    missing = all_pattern_keywords - achievement_keywords

    # Calculate overlap score (0-100)
    if len(all_pattern_keywords) == 0:
        score = 0
    else:
        score = (len(matches) / min(len(achievement_keywords) + 5, len(all_pattern_keywords))) * 100

    return score, list(matches)[:10], list(missing)[:10]


def classify_achievement_competency(achievement: Achievement) -> Dict[str, float]:
    """Classify achievement by competency based on keywords and content."""
    text = (achievement.core_fact + " " + " ".join(achievement.keywords)).lower()

    # Competency indicators
    leadership_words = {"led", "mentored", "team", "hired", "promoted", "culture", "coaching", "stakeholder", "drove", "established", "built team"}
    architecture_words = {"architected", "designed", "microservices", "event-driven", "scalable", "platform", "system", "ddd", "cqrs", "distributed"}
    delivery_words = {"delivered", "shipped", "built", "implemented", "developed", "feature", "product", "sprint", "velocity"}
    process_words = {"ci/cd", "testing", "monitoring", "agile", "scrum", "deployment", "automation", "documentation", "standards"}

    scores = {
        "leadership": sum(1 for w in leadership_words if w in text),
        "architecture": sum(1 for w in architecture_words if w in text),
        "delivery": sum(1 for w in delivery_words if w in text),
        "process": sum(1 for w in process_words if w in text),
    }

    total = sum(scores.values()) or 1
    return {k: (v / total) * 100 for k, v in scores.items()}


def score_achievement_for_role(achievement: Achievement, role: str, pattern: RolePattern) -> Dict:
    """Score an achievement for a specific target role."""
    # Keyword overlap
    keyword_score, matches, missing = calculate_keyword_overlap(achievement, pattern)

    # Competency alignment
    achievement_competency = classify_achievement_competency(achievement)
    ideal_competency = COMPETENCY_IDEALS.get(role, {})

    # Calculate competency alignment score
    competency_diff = 0
    for comp in ["leadership", "architecture", "delivery", "process"]:
        actual = achievement_competency.get(comp, 0)
        ideal = ideal_competency.get(comp, 25)
        competency_diff += abs(actual - ideal)

    competency_score = max(0, 100 - competency_diff)

    # Determine best variant for this role
    format_rec = FORMAT_RECOMMENDATIONS.get(role, {})
    primary_format = format_rec.get("primary", "ARIS")

    best_variant = None
    if "ARIS" in primary_format and "leadership" in achievement.variants:
        best_variant = "leadership"
    elif "ATRIS" in primary_format and "technical" in achievement.variants:
        best_variant = "technical"
    elif "Narrative" in primary_format and "impact" in achievement.variants:
        best_variant = "impact"
    elif "architecture" in achievement.variants:
        best_variant = "architecture"
    else:
        best_variant = list(achievement.variants.keys())[0] if achievement.variants else None

    # Overall score (weighted average)
    overall_score = (keyword_score * 0.4 + competency_score * 0.6)

    return {
        "achievement_id": achievement.achievement_id,
        "title": achievement.title,
        "role_file": achievement.role_file,
        "overall_score": round(overall_score, 1),
        "keyword_score": round(keyword_score, 1),
        "competency_score": round(competency_score, 1),
        "matching_keywords": matches,
        "missing_keywords": missing[:5],
        "achievement_competency": {k: round(v, 1) for k, v in achievement_competency.items()},
        "ideal_competency": ideal_competency,
        "recommended_variant": best_variant,
        "recommended_format": primary_format,
    }


def analyze_all_achievements():
    """Run full analysis of achievements against JD patterns."""
    patterns = load_jd_patterns()
    achievements = load_all_achievements()

    print(f"Loaded {len(achievements)} achievements from {len(set(a.role_file for a in achievements))} role files")
    print(f"Loaded patterns for {len(patterns)} role categories\n")

    # Build analysis for each role
    analysis = {}

    for role in TARGET_ROLES:
        if role not in patterns:
            print(f"Skipping {role} - no patterns found")
            continue

        pattern = patterns[role]
        role_analysis = {
            "job_count": pattern.count,
            "competency_weights": pattern.competency_weights,
            "ideal_competency": COMPETENCY_IDEALS.get(role, {}),
            "format_recommendation": FORMAT_RECOMMENDATIONS.get(role, {}),
            "top_keywords": [k[0] for k in pattern.top_keywords[:15]],
            "top_tech_skills": [k[0] for k in pattern.top_technical_skills[:15]],
            "achievements": [],
        }

        # Score all achievements for this role
        for achievement in achievements:
            score = score_achievement_for_role(achievement, role, pattern)
            role_analysis["achievements"].append(score)

        # Sort by score
        role_analysis["achievements"].sort(key=lambda x: x["overall_score"], reverse=True)

        # Identify top 5 and bottom 5
        role_analysis["top_5"] = role_analysis["achievements"][:5]
        role_analysis["bottom_5"] = role_analysis["achievements"][-5:]

        analysis[role] = role_analysis

    return analysis


def generate_gap_analysis(analysis: Dict) -> Dict:
    """Generate gap analysis across all roles."""
    gaps = {}

    for role, data in analysis.items():
        pattern_keywords = set(data["top_keywords"] + data["top_tech_skills"])

        # Collect all keywords from achievements
        covered_keywords = set()
        for ach in data["achievements"]:
            covered_keywords.update(ach["matching_keywords"])

        missing = pattern_keywords - covered_keywords

        gaps[role] = {
            "covered": list(covered_keywords),
            "missing": list(missing),
            "coverage_rate": len(covered_keywords) / len(pattern_keywords) * 100 if pattern_keywords else 0,
        }

    return gaps


def main():
    """Run analysis and save results."""
    print("=" * 70)
    print("BULLET POINT ANALYSIS VS JD PATTERNS")
    print("=" * 70)

    analysis = analyze_all_achievements()
    gaps = generate_gap_analysis(analysis)

    # Save full analysis
    output = {
        "analysis_by_role": analysis,
        "gap_analysis": gaps,
    }

    output_file = PROJECT_ROOT / "reports" / "bullet-analysis-raw.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved raw analysis to {output_file}")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY BY ROLE")
    print("=" * 70)

    for role, data in analysis.items():
        print(f"\n## {role.upper().replace('_', ' ')} ({data['job_count']} jobs)")
        print(f"   Format: {data['format_recommendation'].get('primary', 'N/A')}")
        print(f"   Top 3 Achievements:")
        for ach in data["top_5"][:3]:
            print(f"     - {ach['title'][:50]} (score: {ach['overall_score']})")
        print(f"   Keyword Coverage: {gaps[role]['coverage_rate']:.1f}%")
        if gaps[role]["missing"][:3]:
            print(f"   Missing Keywords: {', '.join(gaps[role]['missing'][:3])}")

    return output


if __name__ == "__main__":
    main()
