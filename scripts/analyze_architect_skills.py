#!/usr/bin/env python3
"""
Analyze Skills for Enterprise AI Architect Roles

This script queries MongoDB for target senior/architect roles and starred jobs to:
1. Extract and aggregate technical and soft skills by frequency
2. Weight skills from starred jobs 2x for priority scoring
3. Identify skills by role category and seniority level
4. Generate output for checklist creation

Usage:
    python scripts/analyze_architect_skills.py
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient

# Output directory
OUTPUT_DIR = Path.home() / "pers/projects/certifications/architect"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Target roles with their MongoDB regex patterns (expanded for architect analysis)
TARGET_ROLES = {
    "principal_engineer": r"principal.*(software|engineer|architect)",
    "staff_engineer": r"staff.*(software|engineer)",
    "software_architect": r"(software|solution|enterprise|ai|ml|data|cloud)\s*architect",
    "tech_lead": r"tech(nical)?\s*(lead|director)",
    "engineering_manager": r"engineering\s*(manager|lead)",
    "head_of_engineering": r"head\s*(of\s*)?(engineering|software|technology)",
    "director_engineering": r"director.*(engineering|software|technology|platform)",
    "vp_engineering": r"(vp|vice\s*president).*(engineering|technology|platform)",
    "cto": r"\bcto\b|chief\s*technolog",
}

# Keywords that indicate an engineering/architect role
ENGINEERING_KEYWORDS = [
    "software", "engineer", "developer", "programming", "code", "technical",
    "architecture", "system design", "backend", "frontend", "full-stack",
    "devops", "sre", "infrastructure", "cloud", "aws", "kubernetes",
    "python", "java", "typescript", "javascript", "golang", "rust",
    "microservices", "distributed", "api", "database", "ci/cd",
    "ai", "ml", "machine learning", "llm", "data", "platform",
]

# AI/ML specific keywords for gap analysis
AI_ML_KEYWORDS = [
    "llm", "large language model", "transformer", "fine-tuning", "fine tuning",
    "prompt engineering", "rag", "retrieval augmented", "vector database",
    "langchain", "langgraph", "agents", "agentic", "embedding", "huggingface",
    "pytorch", "tensorflow", "mlops", "model serving", "inference",
    "generative ai", "genai", "foundation model", "ai governance",
    "responsible ai", "ai ethics", "bias detection", "explainability",
    "ai security", "adversarial", "prompt injection", "guardrails",
    "knowledge graph", "neo4j", "chromadb", "pinecone", "weaviate",
]

# Skill categories for domain classification
SKILL_DOMAINS = {
    "ai_ml_engineering": [
        "python", "pytorch", "tensorflow", "huggingface", "langchain", "langgraph",
        "llm", "transformer", "fine-tuning", "rag", "agents", "mlops",
        "machine learning", "deep learning", "nlp", "computer vision",
        "model serving", "inference", "embeddings", "vector database",
    ],
    "ai_governance": [
        "ai governance", "responsible ai", "ai ethics", "bias detection",
        "explainability", "fairness", "compliance", "audit", "risk assessment",
        "model governance", "ai security", "guardrails", "safety",
    ],
    "enterprise_architecture": [
        "togaf", "enterprise architecture", "solution architecture",
        "reference architecture", "architectural patterns", "adm",
        "business architecture", "integration patterns",
    ],
    "system_design": [
        "system design", "distributed systems", "microservices", "scalability",
        "reliability", "performance", "latency", "throughput", "caching",
        "load balancing", "event-driven", "cqrs", "event sourcing",
    ],
    "cloud_platform": [
        "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
        "serverless", "lambda", "ecs", "eks", "cloud native", "infrastructure",
    ],
    "mlops_infrastructure": [
        "mlops", "feature store", "model registry", "ml pipeline",
        "kubeflow", "mlflow", "sagemaker", "vertex ai", "azure ml",
        "model monitoring", "drift detection", "a/b testing",
    ],
    "leadership": [
        "technical leadership", "team building", "mentoring", "coaching",
        "stakeholder management", "roadmap", "strategy", "vision",
        "hiring", "performance management", "cross-functional",
    ],
    "data_knowledge": [
        "data architecture", "data engineering", "knowledge graph",
        "ontology", "data modeling", "data quality", "data governance",
        "feature engineering", "data pipeline", "etl", "streaming",
    ],
}


def get_mongodb_client() -> MongoClient:
    """Get MongoDB client from environment."""
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise ValueError("MONGODB_URI not set in environment")
    return MongoClient(uri)


def is_engineering_role(job: dict) -> bool:
    """Check if job is actually an engineering/architect role."""
    description = job.get("job_description", "").lower()
    title = job.get("title", "").lower()

    # Count engineering keywords in description
    keyword_count = sum(1 for kw in ENGINEERING_KEYWORDS if kw in description)

    # Title should have tech indicator
    title_has_tech = any(kw in title for kw in [
        "engineer", "developer", "architect", "cto", "technical",
        "software", "lead", "platform", "infrastructure", "data", "ml", "ai"
    ])

    return keyword_count >= 3 and title_has_tech


def has_ai_ml_focus(job: dict) -> bool:
    """Check if job has AI/ML focus."""
    text = (job.get("job_description", "") + " " + job.get("title", "")).lower()
    return sum(1 for kw in AI_ML_KEYWORDS if kw in text) >= 2


def classify_skill_domain(skill: str) -> str:
    """Classify a skill into one of the domains."""
    skill_lower = skill.lower()
    for domain, keywords in SKILL_DOMAINS.items():
        if any(kw in skill_lower for kw in keywords):
            return domain
    return "other"


def extract_skills_from_job(job: dict) -> tuple[list[str], list[str], dict]:
    """Extract skills from a job's extracted_jd field."""
    extracted = job.get("extracted_jd", {})
    if not extracted:
        return [], [], {}

    tech_skills = extracted.get("technical_skills", [])
    soft_skills = extracted.get("soft_skills", [])

    metadata = {
        "role_category": extracted.get("role_category"),
        "seniority_level": extracted.get("seniority_level"),
        "pain_points": extracted.get("implied_pain_points", []),
        "keywords": extracted.get("top_keywords", []),
    }

    return tech_skills, soft_skills, metadata


def query_target_jobs(collection) -> tuple[list[dict], list[dict]]:
    """Query jobs for target roles and starred jobs."""
    all_target_jobs = []
    starred_jobs = []

    # Query by role patterns
    for role_name, pattern in TARGET_ROLES.items():
        jobs = list(collection.find(
            {"title": {"$regex": pattern, "$options": "i"}},
            {
                "_id": 1,
                "jobId": 1,
                "title": 1,
                "company": 1,
                "job_description": 1,
                "extracted_jd": 1,
                "starred": 1,
            }
        ))

        # Filter to engineering roles
        eng_jobs = [j for j in jobs if is_engineering_role(j)]
        for job in eng_jobs:
            job["matched_role"] = role_name
        all_target_jobs.extend(eng_jobs)

    # Query starred jobs separately
    starred_cursor = collection.find(
        {"starred": True},
        {
            "_id": 1,
            "jobId": 1,
            "title": 1,
            "company": 1,
            "job_description": 1,
            "extracted_jd": 1,
            "starred": 1,
        }
    )
    starred_jobs = list(starred_cursor)

    # Deduplicate all_target_jobs by _id
    seen_ids = set()
    unique_target_jobs = []
    for job in all_target_jobs:
        job_id = str(job.get("_id"))
        if job_id not in seen_ids:
            seen_ids.add(job_id)
            unique_target_jobs.append(job)

    return unique_target_jobs, starred_jobs


def analyze_skills(
    target_jobs: list[dict],
    starred_jobs: list[dict]
) -> dict[str, Any]:
    """Analyze skills across all jobs with starred weighting."""

    # Starred job IDs for 2x weighting
    starred_ids = {str(j.get("_id")) for j in starred_jobs}

    # Counters for aggregation
    all_tech_skills = Counter()
    all_soft_skills = Counter()
    starred_tech_skills = Counter()
    starred_soft_skills = Counter()

    # By role category
    skills_by_role = defaultdict(lambda: {"tech": Counter(), "soft": Counter(), "count": 0})

    # By seniority
    skills_by_seniority = defaultdict(lambda: {"tech": Counter(), "soft": Counter(), "count": 0})

    # AI/ML specific
    ai_ml_tech_skills = Counter()
    ai_ml_soft_skills = Counter()
    ai_ml_count = 0

    # Pain points and keywords
    all_pain_points = []
    all_keywords = Counter()

    # Skill domain distribution
    domain_distribution = Counter()

    # Process all target jobs
    for job in target_jobs:
        job_id = str(job.get("_id"))
        is_starred = job_id in starred_ids
        is_ai_ml = has_ai_ml_focus(job)

        tech_skills, soft_skills, metadata = extract_skills_from_job(job)
        role_cat = metadata.get("role_category", "unknown")
        seniority = metadata.get("seniority_level", "unknown")

        # Weight factor (2x for starred)
        weight = 2 if is_starred else 1

        # Aggregate skills
        for skill in tech_skills:
            skill_norm = skill.lower().strip()
            all_tech_skills[skill_norm] += weight
            domain = classify_skill_domain(skill_norm)
            domain_distribution[domain] += weight

            if is_starred:
                starred_tech_skills[skill_norm] += 1
            if is_ai_ml:
                ai_ml_tech_skills[skill_norm] += 1

        for skill in soft_skills:
            skill_norm = skill.lower().strip()
            all_soft_skills[skill_norm] += weight

            if is_starred:
                starred_soft_skills[skill_norm] += 1
            if is_ai_ml:
                ai_ml_soft_skills[skill_norm] += 1

        # By role
        skills_by_role[role_cat]["count"] += 1
        for skill in tech_skills:
            skills_by_role[role_cat]["tech"][skill.lower().strip()] += weight
        for skill in soft_skills:
            skills_by_role[role_cat]["soft"][skill.lower().strip()] += weight

        # By seniority
        skills_by_seniority[seniority]["count"] += 1
        for skill in tech_skills:
            skills_by_seniority[seniority]["tech"][skill.lower().strip()] += weight
        for skill in soft_skills:
            skills_by_seniority[seniority]["soft"][skill.lower().strip()] += weight

        # AI/ML count
        if is_ai_ml:
            ai_ml_count += 1

        # Pain points and keywords
        all_pain_points.extend(metadata.get("pain_points", []))
        for kw in metadata.get("keywords", []):
            all_keywords[kw.lower().strip()] += weight

    # Process starred jobs that aren't in target roles
    for job in starred_jobs:
        job_id = str(job.get("_id"))
        # Skip if already processed as target job
        if any(str(tj.get("_id")) == job_id for tj in target_jobs):
            continue

        tech_skills, soft_skills, metadata = extract_skills_from_job(job)

        for skill in tech_skills:
            skill_norm = skill.lower().strip()
            starred_tech_skills[skill_norm] += 1
            all_tech_skills[skill_norm] += 2  # 2x weight
            domain = classify_skill_domain(skill_norm)
            domain_distribution[domain] += 2

        for skill in soft_skills:
            skill_norm = skill.lower().strip()
            starred_soft_skills[skill_norm] += 1
            all_soft_skills[skill_norm] += 2

    return {
        "summary": {
            "total_target_jobs": len(target_jobs),
            "total_starred_jobs": len(starred_jobs),
            "ai_ml_focused_jobs": ai_ml_count,
            "unique_tech_skills": len(all_tech_skills),
            "unique_soft_skills": len(all_soft_skills),
        },
        "all_tech_skills": all_tech_skills,
        "all_soft_skills": all_soft_skills,
        "starred_tech_skills": starred_tech_skills,
        "starred_soft_skills": starred_soft_skills,
        "skills_by_role": dict(skills_by_role),
        "skills_by_seniority": dict(skills_by_seniority),
        "ai_ml_tech_skills": ai_ml_tech_skills,
        "ai_ml_soft_skills": ai_ml_soft_skills,
        "domain_distribution": domain_distribution,
        "pain_points": all_pain_points,
        "keywords": all_keywords,
    }


def calculate_priority_scores(analysis: dict) -> dict[str, dict]:
    """
    Calculate priority scores for skills.

    Priority Formula:
    Score = (Starred Frequency * 2) + (All Frequency * 1) + (AI/ML Bonus * 1.5)

    Thresholds:
    - TableStakes: Skills in 70%+ of ALL jobs
    - Interview: Skills in 40%+ of starred jobs
    - Differentiator: Director+ roles at 2x rate vs Senior
    - Trend: From AI/ML focus, <10% in regular jobs
    """
    total_jobs = analysis["summary"]["total_target_jobs"]
    total_starred = analysis["summary"]["total_starred_jobs"]

    all_tech = analysis["all_tech_skills"]
    starred_tech = analysis["starred_tech_skills"]
    ai_ml_tech = analysis["ai_ml_tech_skills"]

    all_soft = analysis["all_soft_skills"]
    starred_soft = analysis["starred_soft_skills"]
    ai_ml_soft = analysis["ai_ml_soft_skills"]

    # Get Director+ vs Senior skills
    dir_plus_skills = Counter()
    senior_skills = Counter()

    dir_plus_roles = ["director_of_engineering", "vp_engineering", "cto", "head_of_engineering"]
    senior_roles = ["senior_engineer", "staff_principal_engineer"]

    for role, data in analysis["skills_by_role"].items():
        if role in dir_plus_roles:
            for skill, count in data["tech"].items():
                dir_plus_skills[skill] += count
        elif role in senior_roles:
            for skill, count in data["tech"].items():
                senior_skills[skill] += count

    def classify_priority(skill: str, is_soft: bool = False) -> tuple[str, float]:
        """Classify a skill's priority level."""
        if is_soft:
            all_count = all_soft.get(skill, 0)
            starred_count = starred_soft.get(skill, 0)
            ai_ml_count = ai_ml_soft.get(skill, 0)
        else:
            all_count = all_tech.get(skill, 0)
            starred_count = starred_tech.get(skill, 0)
            ai_ml_count = ai_ml_tech.get(skill, 0)

        # Calculate percentages
        all_pct = (all_count / total_jobs * 100) if total_jobs > 0 else 0
        starred_pct = (starred_count / total_starred * 100) if total_starred > 0 else 0

        # Priority score
        score = (starred_count * 2) + all_count + (ai_ml_count * 1.5)

        # Classify
        if all_pct >= 70:
            return "TableStakes", score
        elif starred_pct >= 40:
            return "Interview", score
        elif not is_soft:
            # Check differentiator (2x in Director+ vs Senior)
            dir_count = dir_plus_skills.get(skill, 0)
            sen_count = senior_skills.get(skill, 0)
            if dir_count > 0 and (sen_count == 0 or dir_count / max(sen_count, 1) >= 2):
                return "Differentiator", score

        # Check if trend (AI/ML focused)
        if ai_ml_count > 0 and all_pct < 10:
            return "Trend", score

        return "Standard", score

    # Score all skills
    scored_tech = {}
    for skill in all_tech:
        priority, score = classify_priority(skill)
        scored_tech[skill] = {
            "priority": priority,
            "score": score,
            "all_count": all_tech.get(skill, 0),
            "starred_count": starred_tech.get(skill, 0),
            "ai_ml_count": ai_ml_tech.get(skill, 0),
            "domain": classify_skill_domain(skill),
        }

    scored_soft = {}
    for skill in all_soft:
        priority, score = classify_priority(skill, is_soft=True)
        scored_soft[skill] = {
            "priority": priority,
            "score": score,
            "all_count": all_soft.get(skill, 0),
            "starred_count": starred_soft.get(skill, 0),
        }

    return {
        "tech_skills": scored_tech,
        "soft_skills": scored_soft,
    }


def generate_analysis_report(analysis: dict, scored: dict) -> str:
    """Generate markdown report of the analysis."""
    lines = [
        "# Enterprise AI Architect Skills Analysis",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "**Purpose:** Skills analysis from MongoDB jobs for Enterprise AI Architect learning roadmap",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **Target Role Jobs:** {analysis['summary']['total_target_jobs']}",
        f"- **Starred Jobs:** {analysis['summary']['total_starred_jobs']}",
        f"- **AI/ML Focused Jobs:** {analysis['summary']['ai_ml_focused_jobs']}",
        f"- **Unique Technical Skills:** {analysis['summary']['unique_tech_skills']}",
        f"- **Unique Soft Skills:** {analysis['summary']['unique_soft_skills']}",
        "",
        "---",
        "",
        "## Skill Domain Distribution",
        "",
        "| Domain | Weighted Count | Priority |",
        "|--------|---------------|----------|",
    ]

    for domain, count in analysis["domain_distribution"].most_common():
        priority = "HIGH" if count > 50 else "MEDIUM" if count > 20 else "LOW"
        lines.append(f"| {domain.replace('_', ' ').title()} | {count} | {priority} |")

    lines.extend([
        "",
        "---",
        "",
        "## Top Technical Skills by Priority",
        "",
        "### TableStakes (70%+ of jobs)",
        "",
        "| Skill | All Jobs | Starred | AI/ML | Domain |",
        "|-------|----------|---------|-------|--------|",
    ])

    # Sort by score within each priority
    table_stakes = [(s, d) for s, d in scored["tech_skills"].items() if d["priority"] == "TableStakes"]
    table_stakes.sort(key=lambda x: x[1]["score"], reverse=True)

    for skill, data in table_stakes[:20]:
        lines.append(f"| {skill} | {data['all_count']} | {data['starred_count']} | {data['ai_ml_count']} | {data['domain']} |")

    lines.extend([
        "",
        "### Interview Priority (40%+ of starred jobs)",
        "",
        "| Skill | All Jobs | Starred | AI/ML | Domain |",
        "|-------|----------|---------|-------|--------|",
    ])

    interview = [(s, d) for s, d in scored["tech_skills"].items() if d["priority"] == "Interview"]
    interview.sort(key=lambda x: x[1]["score"], reverse=True)

    for skill, data in interview[:20]:
        lines.append(f"| {skill} | {data['all_count']} | {data['starred_count']} | {data['ai_ml_count']} | {data['domain']} |")

    lines.extend([
        "",
        "### Differentiator (Director+ roles 2x)",
        "",
        "| Skill | All Jobs | Starred | AI/ML | Domain |",
        "|-------|----------|---------|-------|--------|",
    ])

    diff = [(s, d) for s, d in scored["tech_skills"].items() if d["priority"] == "Differentiator"]
    diff.sort(key=lambda x: x[1]["score"], reverse=True)

    for skill, data in diff[:15]:
        lines.append(f"| {skill} | {data['all_count']} | {data['starred_count']} | {data['ai_ml_count']} | {data['domain']} |")

    lines.extend([
        "",
        "### Trend Skills (AI/ML focused, <10% in regular jobs)",
        "",
        "| Skill | All Jobs | Starred | AI/ML | Domain |",
        "|-------|----------|---------|-------|--------|",
    ])

    trend = [(s, d) for s, d in scored["tech_skills"].items() if d["priority"] == "Trend"]
    trend.sort(key=lambda x: x[1]["score"], reverse=True)

    for skill, data in trend[:15]:
        lines.append(f"| {skill} | {data['all_count']} | {data['starred_count']} | {data['ai_ml_count']} | {data['domain']} |")

    lines.extend([
        "",
        "---",
        "",
        "## Soft Skills Analysis",
        "",
        "### Top Soft Skills (All Jobs)",
        "",
        "| Skill | All Jobs | Starred | Priority |",
        "|-------|----------|---------|----------|",
    ])

    soft_sorted = sorted(scored["soft_skills"].items(), key=lambda x: x[1]["score"], reverse=True)
    for skill, data in soft_sorted[:25]:
        lines.append(f"| {skill} | {data['all_count']} | {data['starred_count']} | {data['priority']} |")

    lines.extend([
        "",
        "---",
        "",
        "## Skills by Role Category",
        "",
    ])

    for role, data in sorted(analysis["skills_by_role"].items(), key=lambda x: x[1]["count"], reverse=True):
        if data["count"] == 0:
            continue
        lines.append(f"### {role.replace('_', ' ').title()} ({data['count']} jobs)")
        lines.append("")
        lines.append("**Top Tech Skills:**")
        for skill, count in data["tech"].most_common(10):
            lines.append(f"- {skill} ({count})")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Top Pain Points",
        "",
    ])

    # Deduplicate and count pain points
    pain_counter = Counter(analysis["pain_points"])
    for pain, count in pain_counter.most_common(25):
        lines.append(f"- ({count}) {pain}")

    lines.extend([
        "",
        "---",
        "",
        "## Top ATS Keywords",
        "",
    ])

    for kw, count in analysis["keywords"].most_common(30):
        lines.append(f"- {kw} ({count})")

    return "\n".join(lines)


def main():
    """Main analysis workflow."""
    print("\n" + "=" * 70)
    print("ENTERPRISE AI ARCHITECT SKILLS ANALYSIS")
    print("=" * 70)

    # Connect to MongoDB
    print("\n📊 Connecting to MongoDB...")
    client = get_mongodb_client()
    db = client["jobs"]
    collection = db["level-2"]

    # Query jobs
    print("\n🔍 Querying target roles and starred jobs...")
    target_jobs, starred_jobs = query_target_jobs(collection)
    print(f"   Found {len(target_jobs)} target role jobs")
    print(f"   Found {len(starred_jobs)} starred jobs")

    # Analyze skills
    print("\n📈 Analyzing skills...")
    analysis = analyze_skills(target_jobs, starred_jobs)
    print(f"   {analysis['summary']['unique_tech_skills']} unique tech skills")
    print(f"   {analysis['summary']['unique_soft_skills']} unique soft skills")
    print(f"   {analysis['summary']['ai_ml_focused_jobs']} AI/ML focused jobs")

    # Calculate priority scores
    print("\n🎯 Calculating priority scores...")
    scored = calculate_priority_scores(analysis)

    # Count by priority
    priority_counts = Counter()
    for skill, data in scored["tech_skills"].items():
        priority_counts[data["priority"]] += 1

    for priority, count in priority_counts.most_common():
        print(f"   {priority}: {count} skills")

    # Generate report
    print("\n📝 Generating reports...")
    report = generate_analysis_report(analysis, scored)

    # Save to reports directory
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "architect-skills-analysis.md"
    report_path.write_text(report)
    print(f"   ✓ Saved report to {report_path}")

    # Save raw data as JSON
    json_data = {
        "generated": datetime.now().isoformat(),
        "summary": analysis["summary"],
        "domain_distribution": dict(analysis["domain_distribution"]),
        "scored_tech_skills": scored["tech_skills"],
        "scored_soft_skills": scored["soft_skills"],
        "skills_by_role": {
            role: {
                "count": data["count"],
                "top_tech": data["tech"].most_common(30),
                "top_soft": data["soft"].most_common(15),
            }
            for role, data in analysis["skills_by_role"].items()
        },
        "top_pain_points": Counter(analysis["pain_points"]).most_common(50),
        "top_keywords": analysis["keywords"].most_common(50),
    }

    json_path = REPORTS_DIR / "architect-skills-analysis.json"
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    print(f"   ✓ Saved JSON data to {json_path}")

    # Close MongoDB connection
    client.close()

    print("\n" + "=" * 70)
    print("✅ Analysis complete!")
    print("=" * 70)

    return analysis, scored


if __name__ == "__main__":
    main()
