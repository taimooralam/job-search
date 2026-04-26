#!/usr/bin/env python3
"""
Eval Step 4: Generate Category Market Composites from normalized extraction data.

Reads:  data/eval/normalized/{category}/normalized_jobs.json
        data/eval/normalized/{category}/deep_analysis.json (if available)
Outputs:
  data/eval/composites/{category}.md    — human-readable composite
  data/eval/composites/{category}.json  — machine-readable composite
  data/eval/composites/summary.md       — cross-category comparison

Usage:
  python scripts/eval_step4_composites.py
  python scripts/eval_step4_composites.py --category ai_architect_eea
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional

EVAL_DIR = Path("data/eval")
NORM_DIR = EVAL_DIR / "normalized"
COMP_DIR = EVAL_DIR / "composites"
COMP_DIR.mkdir(parents=True, exist_ok=True)

# Signal tier weights
TIER_WEIGHTS = {"A": 1.00, "B": 0.85, "C": 0.65, "D": 0.40}

# Frequency bands
FREQ_BANDS = {
    "must_have": 0.60,
    "common": 0.35,
    "differentiator": 0.15,
    "rare": 0.0,
}

CATEGORY_META = {
    "head_of_ai_ksa": {"name": "Head of AI — KSA", "macro": "ai_leadership", "priority": "primary_target"},
    "head_of_ai_uae": {"name": "Head of AI — UAE", "macro": "ai_leadership", "priority": "primary_target"},
    "head_of_ai_eea": {"name": "Head of AI — EEA", "macro": "ai_leadership", "priority": "primary_target"},
    "head_of_ai_global": {"name": "Head of AI — Global/Remote", "macro": "ai_leadership", "priority": "primary_target"},
    "head_of_sw_pakistan": {"name": "Head of Software/Engineering — Pakistan", "macro": "leadership_adjacent", "priority": "tertiary_target"},
    "staff_ai_engineer_eea": {"name": "Staff AI Engineer — EEA", "macro": "ai_engineering_adjacent", "priority": "secondary_target"},
    "staff_ai_engineer_global": {"name": "Staff AI Engineer — Global/Remote", "macro": "ai_engineering_adjacent", "priority": "secondary_target"},
    "tech_lead_ai_eea": {"name": "Tech Lead AI — EEA", "macro": "ai_engineering_adjacent", "priority": "secondary_target"},
    "ai_architect_eea": {"name": "AI Architect — EEA", "macro": "ai_architect", "priority": "primary_target"},
    "ai_architect_global": {"name": "AI Architect — Global/Remote", "macro": "ai_architect", "priority": "primary_target"},
    "ai_architect_ksa_uae": {"name": "AI Architect — KSA/UAE", "macro": "ai_architect", "priority": "primary_target"},
    "ai_eng_manager_eea": {"name": "AI Engineering Manager — EEA", "macro": "ai_engineering_adjacent", "priority": "secondary_target"},
    "senior_ai_engineer_eea": {"name": "Senior AI Engineer — EEA", "macro": "ai_engineering_adjacent", "priority": "secondary_target"},
}


def load_category_data(category: str) -> tuple:
    """Load normalized + deep analysis data for a category."""
    norm_file = NORM_DIR / category / "normalized_jobs.json"
    deep_file = NORM_DIR / category / "deep_analysis.json"

    normalized = []
    if norm_file.exists():
        with open(norm_file, encoding="utf-8") as f:
            normalized = [j for j in json.load(f) if not j.get("_extraction_failed")]

    deep = []
    if deep_file.exists():
        with open(deep_file, encoding="utf-8") as f:
            deep = [j for j in json.load(f) if not j.get("_extraction_failed")]

    return normalized, deep


def load_raw_jobs(category: str) -> list:
    """Load raw jobs for tier/score metadata."""
    raw_file = EVAL_DIR / "raw" / category / "jobs_all.json"
    if raw_file.exists():
        with open(raw_file, encoding="utf-8") as f:
            return json.load(f)
    return []


def count_frequency(items: List[str], total: int) -> List[dict]:
    """Count and classify items by frequency band."""
    counts = Counter(items)
    results = []
    for item, count in counts.most_common():
        pct = count / total if total > 0 else 0
        band = "rare"
        for band_name, threshold in sorted(FREQ_BANDS.items(), key=lambda x: -x[1]):
            if pct >= threshold:
                band = band_name
                break
        results.append({"skill": item, "count": count, "total": total, "pct": round(pct * 100, 1), "band": band})
    return results


def count_field_values(jobs: list, field: str) -> Counter:
    """Count occurrences of a field value across jobs."""
    counter = Counter()
    for job in jobs:
        val = job.get(field)
        if val and val != "not_specified":
            counter[val] += 1
    return counter


def collect_list_field(jobs: list, field: str) -> list:
    """Collect all items from a list field across jobs."""
    items = []
    for job in jobs:
        val = job.get(field, [])
        if isinstance(val, list):
            items.extend([v for v in val if v and v != "not_specified"])
    return items


def collect_ai_stack(jobs: list) -> dict:
    """Aggregate AI/ML stack signals."""
    stack_keys = [
        "rag", "agents_orchestration", "fine_tuning", "evaluation_quality",
        "guardrails_governance", "prompt_engineering", "vector_search",
        "model_serving_routing",
    ]
    total = len(jobs)
    results = {}
    for key in stack_keys:
        explicit_count = 0
        for job in jobs:
            ai_stack = job.get("ai_ml_stack", {})
            if isinstance(ai_stack, dict) and ai_stack.get(key) == "explicit":
                explicit_count += 1
        pct = round(explicit_count / total * 100, 1) if total > 0 else 0
        results[key] = {"count": explicit_count, "total": total, "pct": pct}

    # Frameworks
    frameworks = []
    observability = []
    for job in jobs:
        ai_stack = job.get("ai_ml_stack", {})
        if isinstance(ai_stack, dict):
            frameworks.extend(ai_stack.get("frameworks", []))
            observability.extend(ai_stack.get("observability", []))

    results["top_frameworks"] = count_frequency(frameworks, total)[:15]
    results["top_observability"] = count_frequency(observability, total)[:10]
    return results


def collect_management(jobs: list) -> dict:
    """Aggregate management/leadership signals."""
    total = len(jobs)
    fields = ["hiring", "performance_management", "org_building", "budget_pnl"]
    results = {}
    for field in fields:
        explicit_count = 0
        for job in jobs:
            mgmt = job.get("management", {})
            if isinstance(mgmt, dict) and mgmt.get(field) in ("explicit", "derived"):
                explicit_count += 1
        pct = round(explicit_count / total * 100, 1) if total > 0 else 0
        results[field] = {"count": explicit_count, "total": total, "pct": pct}

    # Direct reports
    dr_values = []
    for job in jobs:
        mgmt = job.get("management", {})
        if isinstance(mgmt, dict):
            dr = mgmt.get("direct_reports", "not_specified")
            if dr != "not_specified":
                dr_values.append(dr)
    results["direct_reports_samples"] = dr_values[:10]
    return results


def collect_architecture(jobs: list) -> dict:
    """Aggregate architecture signals."""
    total = len(jobs)
    results = {}

    # Platform design
    platform_count = sum(1 for j in jobs
                         if isinstance(j.get("architecture", {}), dict)
                         and j["architecture"].get("platform_design") in ("explicit", "derived"))
    results["platform_design_pct"] = round(platform_count / total * 100, 1) if total > 0 else 0

    # Greenfield vs optimization
    gf_counts = Counter()
    for job in jobs:
        arch = job.get("architecture", {})
        if isinstance(arch, dict):
            gf = arch.get("greenfield_vs_optimization", "not_specified")
            if gf != "not_specified":
                gf_counts[gf] += 1
    results["greenfield_split"] = dict(gf_counts)

    # Cloud preference
    cloud_counts = Counter()
    for job in jobs:
        cloud = job.get("cloud_platform", {})
        if isinstance(cloud, dict):
            primary = cloud.get("primary", "not_specified")
            if primary != "not_specified":
                cloud_counts[primary] += 1
    results["cloud_preference"] = dict(cloud_counts.most_common(5))

    return results


def collect_pain_points(jobs: list) -> list:
    """Aggregate implied pain points."""
    all_points = []
    for job in jobs:
        points = job.get("implied_pain_points", [])
        if isinstance(points, list):
            all_points.extend(points)
    # Deduplicate similar pain points by lowercasing
    normalized = Counter(p.lower().strip() for p in all_points if p)
    return [{"pain_point": pp, "count": c} for pp, c in normalized.most_common(20)]


def generate_composite(category: str) -> Optional[dict]:
    """Generate a full composite for a category."""
    meta = CATEGORY_META.get(category)
    if not meta:
        return None

    normalized, deep = load_category_data(category)
    raw_jobs = load_raw_jobs(category)

    if not normalized:
        return None

    total = len(normalized)

    # Tier breakdown from raw jobs
    tier_counts = Counter(j.get("_signal_tier", "D") for j in raw_jobs)

    # Signal strength
    applied_count = sum(1 for j in raw_jobs if j.get("status") == "applied")
    scores = [j.get("score", 0) or 0 for j in raw_jobs]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    sorted_scores = sorted(scores)
    median_score = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 0

    # Title variants
    title_counts = Counter(j.get("title_normalized", j.get("title", "")) for j in normalized if j.get("title_normalized"))
    title_family_counts = count_field_values(normalized, "title_family")

    # Hard skills
    must_haves = collect_list_field(normalized, "hard_skills_must_have")
    collect_list_field(normalized, "hard_skills_nice_to_have")
    hard_skills_freq = count_frequency(must_haves, total)

    # Soft skills
    soft_skills = collect_list_field(normalized, "soft_skills")
    soft_skills_freq = count_frequency(soft_skills, total)

    # Programming languages
    all_required_langs = []
    all_preferred_langs = []
    for job in normalized:
        langs = job.get("programming_languages", {})
        if isinstance(langs, dict):
            all_required_langs.extend(langs.get("required", []))
            all_preferred_langs.extend(langs.get("preferred", []))
    req_langs_freq = count_frequency(all_required_langs, total)
    pref_langs_freq = count_frequency(all_preferred_langs, total)

    # Infrastructure
    infra = collect_list_field(normalized, "infrastructure")
    infra_freq = count_frequency(infra, total)

    # Data stack
    data_stack = collect_list_field(normalized, "data_stack")
    data_freq = count_frequency(data_stack, total)

    # Governance
    governance = collect_list_field(normalized, "governance_compliance")
    governance_freq = count_frequency(governance, total)

    # AI/ML stack
    ai_stack = collect_ai_stack(normalized)

    # Management/Leadership
    management = collect_management(normalized)

    # Architecture
    architecture = collect_architecture(normalized)

    # Seniority / Role scope
    seniority_counts = count_field_values(normalized, "seniority")
    scope_counts = count_field_values(normalized, "role_scope")

    # Domain / Company stage
    domain_counts = count_field_values(normalized, "domain_industry")
    stage_counts = count_field_values(normalized, "company_stage")
    collab_counts = count_field_values(normalized, "collaboration_model")

    # Pain points
    pain_points = collect_pain_points(normalized)

    # Disqualifiers
    phd_count = sum(1 for j in normalized if isinstance(j.get("disqualifiers", {}), dict) and j["disqualifiers"].get("requires_phd"))
    research_count = sum(1 for j in normalized if isinstance(j.get("disqualifiers", {}), dict) and j["disqualifiers"].get("research_heavy"))

    # Confidence
    if total >= 20:
        confidence = "high"
    elif total >= 8:
        confidence = "medium"
    elif total >= 5:
        confidence = "low"
    else:
        confidence = "exploratory"

    composite = {
        "category_id": category,
        "category_name": meta["name"],
        "macro_family": meta["macro"],
        "priority": meta["priority"],
        "confidence": confidence,
        "total_jobs": total,
        "deep_analysis_count": len(deep),
        "tier_breakdown": dict(tier_counts),
        "signal_strength": {
            "applied_count": applied_count,
            "avg_score": avg_score,
            "median_score": median_score,
            "score_range": [min(scores), max(scores)] if scores else [0, 0],
        },
        "title_variants": dict(title_counts.most_common(10)),
        "title_families": dict(title_family_counts.most_common(5)),
        "seniority_distribution": dict(seniority_counts),
        "role_scope_distribution": dict(scope_counts),
        "hard_skills": hard_skills_freq[:30],
        "soft_skills": soft_skills_freq[:15],
        "programming_languages": {
            "required": req_langs_freq[:10],
            "preferred": pref_langs_freq[:10],
        },
        "infrastructure": infra_freq[:15],
        "data_stack": data_freq[:10],
        "governance_compliance": governance_freq[:10],
        "ai_ml_stack": ai_stack,
        "management_leadership": management,
        "architecture": architecture,
        "domain_industry": dict(domain_counts.most_common(5)),
        "company_stage": dict(stage_counts.most_common(5)),
        "collaboration_model": dict(collab_counts.most_common(5)),
        "pain_points": pain_points[:15],
        "disqualifiers": {
            "requires_phd_pct": round(phd_count / total * 100, 1) if total > 0 else 0,
            "research_heavy_pct": round(research_count / total * 100, 1) if total > 0 else 0,
        },
    }

    return composite


def render_markdown(composite: dict) -> str:
    """Render a composite as markdown."""
    c = composite
    lines = []
    lines.append(f"# Category: {c['category_name']}")
    lines.append("")
    lines.append("## Category Metadata")
    lines.append(f"- **Macro family:** {c['macro_family']}")
    lines.append(f"- **Target priority:** {c['priority']}")
    lines.append(f"- **Confidence:** {c['confidence']}")
    lines.append(f"- **Total jobs analyzed:** {c['total_jobs']}")
    lines.append(f"- **Deep analysis exemplars:** {c['deep_analysis_count']}")
    lines.append(f"- **Tier mix:** {c['tier_breakdown']}")
    lines.append("")

    lines.append("## Signal Strength")
    ss = c["signal_strength"]
    lines.append(f"- Applied jobs: {ss['applied_count']}")
    lines.append(f"- Average score: {ss['avg_score']}")
    lines.append(f"- Median score: {ss['median_score']}")
    lines.append(f"- Score range: {ss['score_range'][0]}–{ss['score_range'][1]}")
    lines.append("")

    lines.append("## Title Variants")
    for title, count in list(c["title_variants"].items())[:10]:
        lines.append(f"- {title} ({count})")
    lines.append("")

    lines.append("## Seniority & Scope")
    lines.append(f"- Seniority: {c['seniority_distribution']}")
    lines.append(f"- Role scope: {c['role_scope_distribution']}")
    lines.append("")

    # Hard skills by band
    lines.append("## Required Hard Skills")
    lines.append("")
    lines.append("| Skill | Count | % | Band |")
    lines.append("|-------|-------|---|------|")
    for s in c["hard_skills"][:25]:
        lines.append(f"| {s['skill']} | {s['count']}/{s['total']} | {s['pct']}% | {s['band']} |")
    lines.append("")

    # Soft skills
    lines.append("## Soft Skills")
    lines.append("")
    lines.append("| Skill | Count | % |")
    lines.append("|-------|-------|---|")
    for s in c["soft_skills"][:10]:
        lines.append(f"| {s['skill']} | {s['count']}/{s['total']} | {s['pct']}% |")
    lines.append("")

    # Programming languages
    lines.append("## Programming Languages")
    lines.append("")
    lines.append("**Required:**")
    for l in c["programming_languages"]["required"][:8]:
        lines.append(f"- {l['skill']} ({l['pct']}%)")
    lines.append("")
    lines.append("**Preferred:**")
    for l in c["programming_languages"]["preferred"][:5]:
        lines.append(f"- {l['skill']} ({l['pct']}%)")
    lines.append("")

    # AI/ML Stack
    lines.append("## AI/ML and LLM Profile")
    lines.append("")
    ai = c["ai_ml_stack"]
    for key in ["rag", "agents_orchestration", "fine_tuning", "evaluation_quality",
                 "guardrails_governance", "prompt_engineering", "vector_search", "model_serving_routing"]:
        data = ai.get(key, {})
        lines.append(f"- **{key.replace('_', ' ').title()}:** {data.get('pct', 0)}% explicit ({data.get('count', 0)}/{data.get('total', 0)})")
    lines.append("")
    if ai.get("top_frameworks"):
        lines.append("**Top Frameworks:**")
        for f in ai["top_frameworks"][:10]:
            lines.append(f"- {f['skill']} ({f['pct']}%)")
        lines.append("")

    # Architecture
    lines.append("## Architecture Expectations")
    arch = c["architecture"]
    lines.append(f"- Platform design: {arch.get('platform_design_pct', 0)}%")
    lines.append(f"- Greenfield split: {arch.get('greenfield_split', {})}")
    lines.append(f"- Cloud preference: {arch.get('cloud_preference', {})}")
    lines.append("")

    # Leadership
    lines.append("## Leadership Profile")
    mgmt = c["management_leadership"]
    for key in ["hiring", "performance_management", "org_building", "budget_pnl"]:
        data = mgmt.get(key, {})
        lines.append(f"- **{key.replace('_', ' ').title()}:** {data.get('pct', 0)}% ({data.get('count', 0)}/{data.get('total', 0)})")
    if mgmt.get("direct_reports_samples"):
        lines.append(f"- Direct reports samples: {mgmt['direct_reports_samples'][:5]}")
    lines.append("")

    # Pain points
    lines.append("## Top Pain Points")
    lines.append("")
    for pp in c["pain_points"][:10]:
        lines.append(f"- {pp['pain_point']} ({pp['count']}x)")
    lines.append("")

    # Domain / stage
    lines.append("## Market Context")
    lines.append(f"- **Industry domains:** {c['domain_industry']}")
    lines.append(f"- **Company stages:** {c['company_stage']}")
    lines.append(f"- **Collaboration models:** {c['collaboration_model']}")
    lines.append("")

    # Disqualifiers
    lines.append("## Disqualifiers")
    dq = c["disqualifiers"]
    lines.append(f"- Requires PhD: {dq['requires_phd_pct']}%")
    lines.append(f"- Research-heavy: {dq['research_heavy_pct']}%")
    lines.append("")

    return "\n".join(lines)


def generate_summary(composites: List[dict]) -> str:
    """Generate cross-category summary."""
    lines = []
    lines.append("# Cross-Category Summary")
    lines.append("")
    lines.append("**Analysis date:** 2026-04-14")
    lines.append(f"**Categories analyzed:** {len(composites)}")
    lines.append(f"**Total jobs:** {sum(c['total_jobs'] for c in composites)}")
    lines.append("")

    # Overview table
    lines.append("## Category Overview")
    lines.append("")
    lines.append("| Category | Jobs | Confidence | Macro | Priority | Avg Score |")
    lines.append("|----------|------|------------|-------|----------|-----------|")
    for c in sorted(composites, key=lambda x: x["total_jobs"], reverse=True):
        lines.append(
            f"| {c['category_name']} | {c['total_jobs']} | {c['confidence']} | "
            f"{c['macro_family']} | {c['priority']} | {c['signal_strength']['avg_score']} |"
        )
    lines.append("")

    # Universal skills (appear in >60% of categories)
    lines.append("## Universal Skills (across categories)")
    lines.append("")
    skill_presence = defaultdict(int)
    total_cats = len(composites)
    for c in composites:
        seen = set()
        for s in c["hard_skills"]:
            if s["band"] in ("must_have", "common") and s["skill"].lower() not in seen:
                skill_presence[s["skill"]] += 1
                seen.add(s["skill"].lower())
    universal = [(s, cnt) for s, cnt in skill_presence.items() if cnt >= total_cats * 0.5]
    universal.sort(key=lambda x: -x[1])
    for skill, cnt in universal[:20]:
        lines.append(f"- {skill} (in {cnt}/{total_cats} categories)")
    lines.append("")

    # Top AI signals across categories
    lines.append("## AI/ML Signal Strength by Category")
    lines.append("")
    lines.append("| Category | RAG | Agents | Fine-tune | Eval | Guardrails | Prompt Eng |")
    lines.append("|----------|-----|--------|-----------|------|------------|------------|")
    for c in composites:
        ai = c["ai_ml_stack"]
        lines.append(
            f"| {c['category_name'][:30]} | "
            f"{ai.get('rag', {}).get('pct', 0)}% | "
            f"{ai.get('agents_orchestration', {}).get('pct', 0)}% | "
            f"{ai.get('fine_tuning', {}).get('pct', 0)}% | "
            f"{ai.get('evaluation_quality', {}).get('pct', 0)}% | "
            f"{ai.get('guardrails_governance', {}).get('pct', 0)}% | "
            f"{ai.get('prompt_engineering', {}).get('pct', 0)}% |"
        )
    lines.append("")

    # Top pain points across all categories
    lines.append("## Top Pain Points (Cross-Category)")
    lines.append("")
    all_pains = Counter()
    for c in composites:
        for pp in c["pain_points"]:
            all_pains[pp["pain_point"]] += pp["count"]
    for pp, count in all_pains.most_common(15):
        lines.append(f"- {pp} ({count}x)")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Eval Step 4: Generate category composites")
    parser.add_argument("--category", help="Process single category")
    args = parser.parse_args()

    categories = [args.category] if args.category else list(CATEGORY_META.keys())

    print(f"Step 4: Generating composites for {len(categories)} categories")
    print()

    composites = []
    for cat in categories:
        norm_file = NORM_DIR / cat / "normalized_jobs.json"
        if not norm_file.exists():
            print(f"[{cat}] Skipped — no normalized data")
            continue

        print(f"[{cat}]", end=" ")
        composite = generate_composite(cat)
        if not composite:
            print("— no data")
            continue

        # Save JSON
        with open(COMP_DIR / f"{cat}.json", "w", encoding="utf-8") as f:
            json.dump(composite, f, indent=2, default=str)

        # Save markdown
        md = render_markdown(composite)
        with open(COMP_DIR / f"{cat}.md", "w", encoding="utf-8") as f:
            f.write(md)

        composites.append(composite)
        print(f"— {composite['total_jobs']} jobs, confidence={composite['confidence']}")

    # Generate cross-category summary
    if composites:
        summary = generate_summary(composites)
        with open(COMP_DIR / "summary.md", "w", encoding="utf-8") as f:
            f.write(summary)
        # Also save as JSON
        with open(COMP_DIR / "cross_category_matrix.json", "w", encoding="utf-8") as f:
            json.dump({"categories": [c["category_id"] for c in composites], "total_jobs": sum(c["total_jobs"] for c in composites)}, f, indent=2)
        print("\nSummary written to data/eval/composites/summary.md")

    print(f"\nStep 4 complete: {len(composites)} composites generated")


if __name__ == "__main__":
    main()
