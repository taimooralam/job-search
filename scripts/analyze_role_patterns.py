#!/usr/bin/env python3
"""
Analyze Role Patterns from MongoDB Extracted JDs

This script queries MongoDB level-2 collection directly to analyze ALL extracted JDs:
1. Pain points by role type (IC vs Leadership) and theme
2. Keywords, hard skills, soft skills per role
3. Competency weights and core competency section definitions

Usage:
    python scripts/analyze_role_patterns.py
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict, Counter
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient

# Project paths
REPORTS_DIR = PROJECT_ROOT / "reports"

# Role categorization
IC_ROLES = ["senior_engineer", "tech_lead", "staff_principal_engineer"]
LEADERSHIP_ROLES = ["engineering_manager", "head_of_engineering", "director_of_engineering", "vp_engineering", "cto"]

# Role display info
ROLE_INFO = {
    "senior_engineer": {"display": "Senior Engineer", "type": "IC", "description": "Pure IC, delivery-focused"},
    "tech_lead": {"display": "Tech Lead", "type": "IC (Hybrid)", "description": "Hybrid IC/leadership, hands-on"},
    "staff_principal_engineer": {"display": "Staff/Principal Engineer", "type": "IC", "description": "IC leadership, cross-team influence"},
    "engineering_manager": {"display": "Engineering Manager", "type": "Leadership", "description": "First-line management"},
    "head_of_engineering": {"display": "Head of Engineering", "type": "Leadership", "description": "Function builder"},
    "director_of_engineering": {"display": "Director of Engineering", "type": "Leadership", "description": "Multi-team leadership"},
    "vp_engineering": {"display": "VP of Engineering", "type": "Leadership", "description": "Executive leadership"},
    "cto": {"display": "CTO", "type": "Leadership", "description": "Technology vision, C-level"},
}

# Pain point theme keywords for categorization
PAIN_POINT_THEMES = {
    "Scaling & Architecture": [
        "scale", "scalab", "distributed", "architecture", "system design",
        "performance", "latency", "throughput", "high-scale", "large-scale",
        "microservice", "cloud-native", "reliability", "availability"
    ],
    "Technical Debt": [
        "legacy", "moderniz", "migration", "refactor", "technical debt",
        "code quality", "maintenance", "outdated", "asp.net", ".net core",
        "monolith", "rewrite"
    ],
    "Platform & Infrastructure": [
        "cloud", "infrastructure", "devops", "ci/cd", "deployment",
        "kubernetes", "container", "aws", "azure", "gcp", "terraform",
        "observability", "monitoring", "pipeline"
    ],
    "AI/ML Integration": [
        "ai", "ml", "machine learning", "llm", "generative", "data pipeline",
        "model", "intelligence", "automation", "analytics"
    ],
    "Team Building": [
        "hiring", "recruit", "talent", "retention", "onboard", "attract",
        "grow team", "scale team", "build team", "engineering organization",
        "from scratch", "zero to"
    ],
    "Process & Delivery": [
        "agile", "delivery", "velocity", "sprint", "quality", "process",
        "standard", "practice", "workflow", "cadence", "deadline",
        "timeline", "ship"
    ],
    "Cross-Functional": [
        "stakeholder", "cross-functional", "collaboration", "communication",
        "coordination", "alignment", "product", "business partner",
        "cross-team"
    ],
    "Strategic Alignment": [
        "strategy", "roadmap", "vision", "direction", "business objective",
        "okr", "goal", "alignment", "executive", "board", "investor"
    ],
}

# Core competency header sections per role
HEADER_SECTIONS = {
    # IC Roles
    "senior_engineer": ["Core Technologies", "Architecture & Design", "Cloud & DevOps", "Delivery & Quality"],
    "tech_lead": ["Technical Excellence", "Architecture & Design", "Cloud & Platform", "Team Leadership"],
    "staff_principal_engineer": ["System Architecture", "Technical Excellence", "Cloud Platform", "Technical Influence"],
    # Leadership Roles
    "engineering_manager": ["Technical Leadership", "People Management", "Cloud & Platform", "Delivery & Process"],
    "head_of_engineering": ["Executive Leadership", "Strategic Delivery", "Technology Vision", "Business Impact"],
    "director_of_engineering": ["Engineering Leadership", "Operational Excellence", "Technology Strategy", "Business Partnership"],
    "vp_engineering": ["Engineering Leadership", "Operational Excellence", "Technology Strategy", "Business Partnership"],
    "cto": ["Technology Vision & Strategy", "Business Partnership", "Engineering Organization", "Technical Authority"],
}


def get_mongodb_client():
    """Get MongoDB client."""
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise ValueError("MONGODB_URI not set in environment")
    return MongoClient(uri)


def fetch_all_extracted_jds() -> List[Dict[str, Any]]:
    """Fetch all documents with extracted_jd from MongoDB."""
    client = get_mongodb_client()
    db = client["jobs"]
    collection = db["level-2"]

    # Query all docs with extracted_jd
    cursor = collection.find(
        {"extracted_jd": {"$exists": True, "$type": "object"}},
        {
            "title": 1,
            "company": 1,
            "extracted_jd": 1,
        }
    )

    docs = list(cursor)
    client.close()
    return docs


def categorize_pain_point(pain_point: str) -> str:
    """Categorize a pain point into one of the 8 themes."""
    pain_lower = pain_point.lower()

    # Score each theme
    theme_scores = {}
    for theme, keywords in PAIN_POINT_THEMES.items():
        score = sum(1 for kw in keywords if kw in pain_lower)
        if score > 0:
            theme_scores[theme] = score

    if theme_scores:
        return max(theme_scores, key=theme_scores.get)
    return "Other"


def aggregate_by_role(docs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate all data by role category.

    Returns dict with structure:
    {
        "role_category": {
            "count": int,
            "pain_points": [all pain points],
            "pain_points_by_theme": {theme: [pain points]},
            "technical_skills": Counter,
            "soft_skills": Counter,
            "top_keywords": Counter,
            "success_metrics": [all metrics],
            "competency_weights": {delivery: [], process: [], architecture: [], leadership: []},
            "sample_titles": [],
            "sample_companies": [],
        }
    }
    """
    role_data = defaultdict(lambda: {
        "count": 0,
        "pain_points": [],
        "pain_points_by_theme": defaultdict(list),
        "technical_skills": Counter(),
        "soft_skills": Counter(),
        "top_keywords": Counter(),
        "success_metrics": [],
        "competency_weights": {"delivery": [], "process": [], "architecture": [], "leadership": []},
        "sample_titles": [],
        "sample_companies": [],
        "seniority_levels": Counter(),
    })

    for doc in docs:
        jd = doc.get("extracted_jd", {})
        if not jd:
            continue

        role = jd.get("role_category", "unknown")
        if role is None:
            role = "unknown"

        data = role_data[role]
        data["count"] += 1

        # Sample titles and companies
        title = doc.get("title", "")
        company = doc.get("company", "")
        if title and len(data["sample_titles"]) < 20:
            if title not in data["sample_titles"]:
                data["sample_titles"].append(title)
        if company and len(data["sample_companies"]) < 20:
            if company not in data["sample_companies"]:
                data["sample_companies"].append(company)

        # Pain points - collect ALL
        for pain in jd.get("implied_pain_points", []):
            if pain:
                data["pain_points"].append(pain)
                theme = categorize_pain_point(pain)
                data["pain_points_by_theme"][theme].append(pain)

        # Success metrics - collect ALL
        for metric in jd.get("success_metrics", []):
            if metric:
                data["success_metrics"].append(metric)

        # Technical skills - count frequencies
        for skill in jd.get("technical_skills", []):
            if skill:
                data["technical_skills"][skill.lower().strip()] += 1

        # Soft skills - count frequencies
        for skill in jd.get("soft_skills", []):
            if skill:
                data["soft_skills"][skill.lower().strip()] += 1

        # Keywords - count frequencies
        for kw in jd.get("top_keywords", []):
            if kw:
                data["top_keywords"][kw.lower().strip()] += 1

        # Competency weights
        weights = jd.get("competency_weights", {})
        for dim in ["delivery", "process", "architecture", "leadership"]:
            if dim in weights and isinstance(weights[dim], (int, float)):
                data["competency_weights"][dim].append(weights[dim])

        # Seniority level
        seniority = jd.get("seniority_level", "unknown")
        if seniority:
            data["seniority_levels"][seniority] += 1

    return role_data


def generate_pain_points_report(role_data: Dict[str, Dict[str, Any]]) -> str:
    """Generate the pain points analysis report."""
    lines = [
        "# Role Pain Points Analysis",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "**Purpose:** ALL pain points from MongoDB extracted JDs, organized by role type and theme.",
        "",
        "---",
        "",
        "## Summary by Role Type",
        "",
        "### IC Roles",
        "| Role | Jobs | Total Pain Points | Top Themes |",
        "|------|------|-------------------|------------|",
    ]

    # IC Summary
    for role in IC_ROLES:
        if role in role_data:
            data = role_data[role]
            count = data["count"]
            total_pains = len(data["pain_points"])
            themes = data["pain_points_by_theme"]
            top_themes = sorted(themes.keys(), key=lambda t: len(themes[t]), reverse=True)[:3]
            top_themes_str = ", ".join(f"{t} ({len(themes[t])})" for t in top_themes)
            display = ROLE_INFO.get(role, {}).get("display", role)
            lines.append(f"| {display} | {count} | {total_pains} | {top_themes_str} |")

    lines.extend([
        "",
        "### Leadership Roles",
        "| Role | Jobs | Total Pain Points | Top Themes |",
        "|------|------|-------------------|------------|",
    ])

    # Leadership Summary
    for role in LEADERSHIP_ROLES:
        if role in role_data:
            data = role_data[role]
            count = data["count"]
            total_pains = len(data["pain_points"])
            themes = data["pain_points_by_theme"]
            top_themes = sorted(themes.keys(), key=lambda t: len(themes[t]), reverse=True)[:3]
            top_themes_str = ", ".join(f"{t} ({len(themes[t])})" for t in top_themes)
            display = ROLE_INFO.get(role, {}).get("display", role)
            lines.append(f"| {display} | {count} | {total_pains} | {top_themes_str} |")

    # Detailed breakdown by role
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Pain Points by Role",
        "",
        "# IC Roles",
        "",
    ])

    for role in IC_ROLES:
        if role not in role_data:
            continue

        info = ROLE_INFO.get(role, {"display": role, "type": "IC", "description": ""})
        data = role_data[role]
        count = data["count"]
        total_pains = len(data["pain_points"])

        lines.extend([
            f"## {info['display']} ({info['type']})",
            "",
            f"**Job Count:** {count} | **Total Pain Points:** {total_pains} | **Description:** {info['description']}",
            "",
        ])

        themes = data["pain_points_by_theme"]
        for theme in sorted(themes.keys(), key=lambda t: len(themes[t]), reverse=True):
            pains = themes[theme]
            if pains:
                # Deduplicate and show unique pain points
                unique_pains = list(dict.fromkeys(pains))  # Preserve order, remove dupes
                lines.append(f"### {theme} ({len(pains)} occurrences, {len(unique_pains)} unique)")
                lines.append("")
                for pain in unique_pains[:25]:  # Show top 25 unique
                    lines.append(f"- {pain}")
                if len(unique_pains) > 25:
                    lines.append(f"- ... and {len(unique_pains) - 25} more")
                lines.append("")

    # Leadership Roles
    lines.append("---")
    lines.append("")
    lines.append("# Leadership Roles")
    lines.append("")

    for role in LEADERSHIP_ROLES:
        if role not in role_data:
            continue

        info = ROLE_INFO.get(role, {"display": role, "type": "Leadership", "description": ""})
        data = role_data[role]
        count = data["count"]
        total_pains = len(data["pain_points"])

        lines.extend([
            f"## {info['display']} ({info['type']})",
            "",
            f"**Job Count:** {count} | **Total Pain Points:** {total_pains} | **Description:** {info['description']}",
            "",
        ])

        themes = data["pain_points_by_theme"]
        for theme in sorted(themes.keys(), key=lambda t: len(themes[t]), reverse=True):
            pains = themes[theme]
            if pains:
                unique_pains = list(dict.fromkeys(pains))
                lines.append(f"### {theme} ({len(pains)} occurrences, {len(unique_pains)} unique)")
                lines.append("")
                for pain in unique_pains[:25]:
                    lines.append(f"- {pain}")
                if len(unique_pains) > 25:
                    lines.append(f"- ... and {len(unique_pains) - 25} more")
                lines.append("")

    return "\n".join(lines)


def generate_skills_report(role_data: Dict[str, Dict[str, Any]]) -> str:
    """Generate the skills analysis report (hard + soft skills + keywords)."""
    lines = [
        "# Role Skills Analysis",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "**Purpose:** ALL technical skills, soft skills, and keywords from MongoDB extracted JDs.",
        "",
        "---",
        "",
    ]

    all_roles = IC_ROLES + LEADERSHIP_ROLES

    for role in all_roles:
        if role not in role_data:
            continue

        info = ROLE_INFO.get(role, {"display": role, "type": "Unknown", "description": ""})
        data = role_data[role]
        count = data["count"]

        lines.extend([
            f"## {info['display']} ({info['type']})",
            "",
            f"**Job Count:** {count} | **Description:** {info['description']}",
            "",
        ])

        # Technical Skills (Hard Skills)
        tech_skills = data["technical_skills"]
        if tech_skills:
            lines.append("### Technical Skills (Hard Skills)")
            lines.append("")
            lines.append("| Skill | Count | % of Jobs |")
            lines.append("|-------|-------|-----------|")
            for skill, cnt in tech_skills.most_common(30):
                pct = cnt / count * 100
                lines.append(f"| {skill} | {cnt} | {pct:.1f}% |")
            lines.append("")

        # Soft Skills
        soft_skills = data["soft_skills"]
        if soft_skills:
            lines.append("### Soft Skills")
            lines.append("")
            lines.append("| Skill | Count | % of Jobs |")
            lines.append("|-------|-------|-----------|")
            for skill, cnt in soft_skills.most_common(20):
                pct = cnt / count * 100
                lines.append(f"| {skill} | {cnt} | {pct:.1f}% |")
            lines.append("")

        # Top Keywords
        keywords = data["top_keywords"]
        if keywords:
            lines.append("### Top ATS Keywords")
            lines.append("")
            lines.append("| Keyword | Count | % of Jobs |")
            lines.append("|---------|-------|-----------|")
            for kw, cnt in keywords.most_common(25):
                pct = cnt / count * 100
                lines.append(f"| {kw} | {cnt} | {pct:.1f}% |")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_competencies_report(role_data: Dict[str, Dict[str, Any]]) -> str:
    """Generate the core competencies by role report."""
    lines = [
        "# Core Competencies by Role",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "**Purpose:** Static header section NAMES per role. CV generator populates skills dynamically from JD keywords.",
        "",
        "---",
        "",
        "## Section Names Summary",
        "",
        "### IC Roles",
        "",
        "| Role | Section 1 | Section 2 | Section 3 | Section 4 |",
        "|------|-----------|-----------|-----------|-----------|",
    ]

    # IC Summary table
    for role in IC_ROLES:
        if role in HEADER_SECTIONS:
            display = ROLE_INFO.get(role, {}).get("display", role)
            sections = HEADER_SECTIONS[role]
            lines.append(f"| {display} | {sections[0]} | {sections[1]} | {sections[2]} | {sections[3]} |")

    lines.extend([
        "",
        "### Leadership Roles",
        "",
        "| Role | Section 1 | Section 2 | Section 3 | Section 4 |",
        "|------|-----------|-----------|-----------|-----------|",
    ])

    # Leadership Summary table
    for role in LEADERSHIP_ROLES:
        if role in HEADER_SECTIONS:
            display = ROLE_INFO.get(role, {}).get("display", role)
            sections = HEADER_SECTIONS[role]
            lines.append(f"| {display} | {sections[0]} | {sections[1]} | {sections[2]} | {sections[3]} |")

    # Detailed breakdown
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Role Profiles",
        "",
        "# IC Roles",
        "",
    ])

    all_roles = IC_ROLES + LEADERSHIP_ROLES

    for i, role in enumerate(all_roles):
        if role not in role_data:
            continue

        # Add Leadership header
        if i == len(IC_ROLES):
            lines.append("---")
            lines.append("")
            lines.append("# Leadership Roles")
            lines.append("")

        info = ROLE_INFO.get(role, {"display": role, "type": "Unknown", "description": ""})
        data = role_data[role]
        count = data["count"]

        # Calculate weight averages
        weights = data["competency_weights"]
        weight_avgs = {}
        for dim in ["delivery", "process", "architecture", "leadership"]:
            vals = weights[dim]
            if vals:
                weight_avgs[dim] = sum(vals) / len(vals)

        lines.extend([
            f"## {info['display']} ({info['type']})",
            "",
            f"**Job Count:** {count} | **Description:** {info['description']}",
            "",
        ])

        # Competency weights
        if weight_avgs:
            lines.append("**Competency Weight Profile:**")
            for dim in ["delivery", "process", "architecture", "leadership"]:
                if dim in weight_avgs:
                    lines.append(f"- {dim.capitalize()}: {weight_avgs[dim]:.1f}%")
            lines.append("")

        # Header sections
        if role in HEADER_SECTIONS:
            lines.append("**Header Sections (in priority order):**")
            for i, section in enumerate(HEADER_SECTIONS[role], 1):
                lines.append(f"{i}. {section}")
            lines.append("")

        # Top JD keywords for this role
        keywords = data["top_keywords"]
        if keywords:
            top_kws = [kw for kw, _ in keywords.most_common(15)]
            lines.append("**JD Signal Keywords (for dynamic skill population):**")
            lines.append(f"`{', '.join(top_kws)}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_weights_report(role_data: Dict[str, Dict[str, Any]]) -> str:
    """Generate the competency weights analysis report."""
    lines = [
        "# Role Competency Weights Analysis",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "**Purpose:** Competency weight analysis from MongoDB extracted JDs for CV emphasis recommendations.",
        "",
        "**Dimensions:**",
        "- **Delivery**: Shipping features, product execution",
        "- **Process**: CI/CD, testing, quality standards",
        "- **Architecture**: System design, technical strategy",
        "- **Leadership**: People management, team building",
        "",
        "---",
        "",
        "## Weight Distribution Summary",
        "",
        "| Role | Jobs | Delivery | Process | Architecture | Leadership | Primary Focus |",
        "|------|------|----------|---------|--------------|------------|---------------|",
    ]

    all_roles = IC_ROLES + LEADERSHIP_ROLES

    for role in all_roles:
        if role not in role_data:
            continue

        data = role_data[role]
        count = data["count"]
        weights = data["competency_weights"]

        # Calculate averages
        avgs = {}
        for dim in ["delivery", "process", "architecture", "leadership"]:
            vals = weights[dim]
            if vals:
                avgs[dim] = sum(vals) / len(vals)
            else:
                avgs[dim] = 0

        display = ROLE_INFO.get(role, {}).get("display", role)
        primary = max(avgs, key=avgs.get).capitalize()

        lines.append(
            f"| {display} | {count} | {avgs['delivery']:.1f}% | {avgs['process']:.1f}% | "
            f"{avgs['architecture']:.1f}% | {avgs['leadership']:.1f}% | {primary} |"
        )

    # IC vs Leadership comparison
    lines.extend([
        "",
        "---",
        "",
        "## IC vs Leadership Comparison",
        "",
        "### IC Roles (Aggregate)",
        "",
    ])

    # Calculate IC aggregates
    ic_weights = {"delivery": [], "process": [], "architecture": [], "leadership": []}
    ic_count = 0
    for role in IC_ROLES:
        if role in role_data:
            ic_count += role_data[role]["count"]
            for dim in ic_weights:
                ic_weights[dim].extend(role_data[role]["competency_weights"][dim])

    lines.append(f"**Total Jobs:** {ic_count}")
    lines.append("")
    lines.append("| Dimension | Average | Min | Max |")
    lines.append("|-----------|---------|-----|-----|")
    for dim in ["delivery", "process", "architecture", "leadership"]:
        values = ic_weights[dim]
        if values:
            avg = sum(values) / len(values)
            lines.append(f"| {dim.capitalize()} | {avg:.1f}% | {min(values)}% | {max(values)}% |")

    lines.extend([
        "",
        "### Leadership Roles (Aggregate)",
        "",
    ])

    # Calculate Leadership aggregates
    lead_weights = {"delivery": [], "process": [], "architecture": [], "leadership": []}
    lead_count = 0
    for role in LEADERSHIP_ROLES:
        if role in role_data:
            lead_count += role_data[role]["count"]
            for dim in lead_weights:
                lead_weights[dim].extend(role_data[role]["competency_weights"][dim])

    lines.append(f"**Total Jobs:** {lead_count}")
    lines.append("")
    lines.append("| Dimension | Average | Min | Max |")
    lines.append("|-----------|---------|-----|-----|")
    for dim in ["delivery", "process", "architecture", "leadership"]:
        values = lead_weights[dim]
        if values:
            avg = sum(values) / len(values)
            lines.append(f"| {dim.capitalize()} | {avg:.1f}% | {min(values)}% | {max(values)}% |")

    # CV Emphasis recommendations
    lines.extend([
        "",
        "---",
        "",
        "## CV Emphasis Recommendations",
        "",
        "Based on the competency weight analysis:",
        "",
        "| Role | Primary Emphasis | Secondary Emphasis | De-emphasize |",
        "|------|------------------|-------------------|--------------|",
    ])

    for role in all_roles:
        if role not in role_data:
            continue

        data = role_data[role]
        weights = data["competency_weights"]

        avgs = {}
        for dim in ["delivery", "process", "architecture", "leadership"]:
            vals = weights[dim]
            if vals:
                avgs[dim] = sum(vals) / len(vals)
            else:
                avgs[dim] = 0

        display = ROLE_INFO.get(role, {}).get("display", role)
        sorted_dims = sorted(avgs.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_dims[0][0].capitalize()
        secondary = sorted_dims[1][0].capitalize()
        deemph = sorted_dims[-1][0].capitalize()
        lines.append(f"| {display} | {primary} | {secondary} | {deemph} |")

    return "\n".join(lines)


def save_raw_data(role_data: Dict[str, Dict[str, Any]]):
    """Save raw aggregated data to JSON for reference."""
    output = {}
    for role, data in role_data.items():
        output[role] = {
            "count": data["count"],
            "sample_titles": data["sample_titles"],
            "sample_companies": data["sample_companies"],
            "pain_points_count": len(data["pain_points"]),
            "pain_points_by_theme": {
                theme: len(pains) for theme, pains in data["pain_points_by_theme"].items()
            },
            "top_technical_skills": data["technical_skills"].most_common(50),
            "top_soft_skills": data["soft_skills"].most_common(30),
            "top_keywords": data["top_keywords"].most_common(50),
            "competency_weight_stats": {
                dim: {
                    "avg": sum(vals) / len(vals) if vals else 0,
                    "min": min(vals) if vals else 0,
                    "max": max(vals) if vals else 0,
                    "count": len(vals),
                }
                for dim, vals in data["competency_weights"].items()
            },
            "seniority_distribution": dict(data["seniority_levels"]),
        }

    output_file = REPORTS_DIR / "role-analysis-raw.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"   ✓ Saved raw data to {output_file.name}")


def main():
    """Run the role pattern analysis from MongoDB."""
    print("\n" + "=" * 70)
    print("ROLE PATTERN ANALYSIS (from MongoDB)")
    print("=" * 70)

    # Fetch all extracted JDs from MongoDB
    print("\n📊 Fetching extracted JDs from MongoDB...")
    docs = fetch_all_extracted_jds()
    print(f"   Found {len(docs)} documents with extracted_jd")

    # Aggregate by role
    print("\n🔄 Aggregating data by role category...")
    role_data = aggregate_by_role(docs)

    for role in IC_ROLES + LEADERSHIP_ROLES:
        if role in role_data:
            data = role_data[role]
            print(f"   {role}: {data['count']} jobs, {len(data['pain_points'])} pain points, "
                  f"{len(data['technical_skills'])} unique tech skills")

    # Generate reports
    print("\n📝 Generating reports...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Pain points report
    pain_report = generate_pain_points_report(role_data)
    pain_file = REPORTS_DIR / "role-pain-points-analysis.md"
    pain_file.write_text(pain_report)
    print(f"   ✓ Created {pain_file.name}")

    # Skills report (NEW - includes hard/soft skills and keywords)
    skills_report = generate_skills_report(role_data)
    skills_file = REPORTS_DIR / "role-skills-keywords.md"
    skills_file.write_text(skills_report)
    print(f"   ✓ Created {skills_file.name}")

    # Competencies report
    comp_report = generate_competencies_report(role_data)
    comp_file = REPORTS_DIR / "core-competencies-by-role.md"
    comp_file.write_text(comp_report)
    print(f"   ✓ Created {comp_file.name}")

    # Weights report
    weights_report = generate_weights_report(role_data)
    weights_file = REPORTS_DIR / "role-competency-weights.md"
    weights_file.write_text(weights_report)
    print(f"   ✓ Created {weights_file.name}")

    # Save raw data
    save_raw_data(role_data)

    print("\n" + "=" * 70)
    print("✅ Analysis complete! Reports generated in reports/")
    print("=" * 70)


if __name__ == "__main__":
    main()
