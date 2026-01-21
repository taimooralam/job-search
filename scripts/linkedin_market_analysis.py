#!/usr/bin/env python3
"""
LinkedIn Market Analysis Script

Fetches AI Architect job listings from LinkedIn's guest API and analyzes
skill requirements for market research.

Uses pagination to fetch up to 2000 jobs (200 pages x 10 jobs per page).
"""

import json
import logging
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup

# Import existing LinkedIn scraper utilities
from src.services.linkedin_scraper import (
    HEADERS,
    REQUEST_TIMEOUT,
    scrape_linkedin_job,
    extract_job_id,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# LinkedIn search API
LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Search queries to execute
SEARCH_QUERIES = [
    {"keywords": "Enterprise AI Architect", "location": "Worldwide"},
    {"keywords": "AI Architect", "location": "Worldwide"},
    {"keywords": "AI Architect", "location": "United States"},
    {"keywords": "AI Architect", "location": "Germany"},
    {"keywords": "AI Architect", "location": "United Arab Emirates"},
    {"keywords": "AI Architect", "location": "Saudi Arabia"},
    {"keywords": "ML Architect", "location": "Worldwide"},
    {"keywords": "Machine Learning Architect", "location": "Worldwide"},
]

# Skills to extract (case-insensitive)
TECH_SKILLS = {
    # Programming Languages
    "python", "java", "scala", "sql", "r", "go", "rust", "c++", "javascript", "typescript",
    # AI/ML Frameworks
    "tensorflow", "pytorch", "keras", "scikit-learn", "langchain", "langgraph", "hugging face",
    "huggingface", "transformers", "openai", "anthropic", "llamaindex", "autogen", "crewai",
    # Cloud Platforms
    "aws", "azure", "gcp", "google cloud", "amazon web services", "microsoft azure",
    "sagemaker", "vertex ai", "bedrock", "azure openai", "databricks",
    # Data & ML Infrastructure
    "spark", "hadoop", "kafka", "airflow", "mlflow", "kubeflow", "ray", "dask",
    "docker", "kubernetes", "k8s", "terraform", "mlops", "devops",
    # Databases & Vector Stores
    "postgresql", "mongodb", "redis", "elasticsearch", "pinecone", "weaviate", "chroma",
    "milvus", "qdrant", "neo4j", "snowflake", "bigquery", "redshift",
    # Architecture & Methodology
    "togaf", "microservices", "event-driven", "api", "rest", "graphql", "grpc",
    "rag", "retrieval augmented", "fine-tuning", "prompt engineering", "llm",
    "large language model", "generative ai", "genai", "agentic", "multi-agent",
    # Governance & Compliance
    "nist", "iso 42001", "eu ai act", "responsible ai", "ai ethics", "model governance",
    "bias detection", "explainability", "xai", "fairness",
}

SOFT_SKILLS = {
    "leadership", "communication", "stakeholder", "presentation", "collaboration",
    "strategic", "problem-solving", "critical thinking", "mentoring", "coaching",
    "cross-functional", "influence", "negotiation", "decision-making", "agile",
    "executive", "c-level", "board", "strategy", "vision", "roadmap",
}

EXPERIENCE_PATTERNS = [
    (r"(\d+)\+?\s*years?\s*(?:of\s*)?experience", "years_experience"),
    (r"(bachelor|master|phd|doctorate|mba)", "degree"),
    (r"(certified|certification)", "certification"),
    (r"(senior|lead|principal|staff|director|vp|chief)", "seniority"),
]


def fetch_search_page(keywords: str, location: str, start: int = 0) -> str:
    """Fetch a single page of LinkedIn search results."""
    params = {
        "keywords": keywords,
        "location": location,
        "start": start,
        # Note: f_TPR=r2592000 is past month, but we'll fetch all available
    }

    try:
        response = requests.get(
            LINKEDIN_SEARCH_URL,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching search page: {e}")
        return ""


def parse_search_results(html: str) -> List[Dict[str, str]]:
    """Parse job listings from search results HTML."""
    if len(html) < 30:
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Find all job cards
    job_cards = soup.find_all("div", class_=re.compile(r"base-card"))

    for card in job_cards:
        try:
            # Extract title
            title_elem = card.find(class_=re.compile(r"base-search-card__title"))
            title = title_elem.get_text(strip=True) if title_elem else None

            # Extract company
            company_elem = card.find(class_=re.compile(r"base-search-card__subtitle"))
            company = company_elem.get_text(strip=True) if company_elem else None

            # Extract location
            location_elem = card.find(class_=re.compile(r"job-search-card__location"))
            location = location_elem.get_text(strip=True) if location_elem else None

            # Extract job URL and ID
            link_elem = card.find("a", class_=re.compile(r"base-card__full-link"))
            job_url = link_elem.get("href") if link_elem else None

            job_id = None
            if job_url:
                try:
                    job_id = extract_job_id(job_url)
                except ValueError:
                    pass

            if title and job_id:
                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                })
        except Exception as e:
            logger.debug(f"Error parsing job card: {e}")
            continue

    return jobs


def fetch_all_jobs_for_query(keywords: str, location: str, max_pages: int = 200) -> List[Dict]:
    """Fetch all jobs for a search query with pagination."""
    all_jobs = []
    seen_ids: Set[str] = set()

    logger.info(f"Fetching jobs for: {keywords} in {location}")

    for page in range(max_pages):
        start = page * 25  # LinkedIn uses 25 per page

        html = fetch_search_page(keywords, location, start)

        # Stop if response is too short (no more results)
        if len(html) < 30:
            logger.info(f"  No more results at page {page} (start={start})")
            break

        jobs = parse_search_results(html)

        if not jobs:
            logger.info(f"  No jobs parsed at page {page}, stopping")
            break

        # Dedupe by job_id
        new_jobs = 0
        for job in jobs:
            if job["job_id"] not in seen_ids:
                seen_ids.add(job["job_id"])
                all_jobs.append(job)
                new_jobs += 1

        logger.info(f"  Page {page}: {len(jobs)} jobs found, {new_jobs} new (total: {len(all_jobs)})")

        # Rate limiting
        time.sleep(1.5)

        # Stop if we got duplicates only (reached end)
        if new_jobs == 0:
            break

    return all_jobs


def fetch_job_descriptions(jobs: List[Dict], max_jobs: int = 100) -> List[Dict]:
    """Fetch full job descriptions for a subset of jobs."""
    jobs_with_desc = []

    for i, job in enumerate(jobs[:max_jobs]):
        try:
            job_data = scrape_linkedin_job(job["job_id"])
            job["description"] = job_data.description
            job["seniority_level"] = job_data.seniority_level
            job["employment_type"] = job_data.employment_type
            job["job_function"] = job_data.job_function
            job["industries"] = job_data.industries
            jobs_with_desc.append(job)

            if (i + 1) % 10 == 0:
                logger.info(f"  Fetched {i + 1}/{min(len(jobs), max_jobs)} job descriptions")

            time.sleep(1)  # Rate limiting

        except Exception as e:
            logger.debug(f"Error fetching job {job['job_id']}: {e}")
            continue

    return jobs_with_desc


def extract_skills_from_text(text: str) -> Dict[str, List[str]]:
    """Extract tech and soft skills from job description text."""
    text_lower = text.lower()

    found_tech = []
    found_soft = []

    for skill in TECH_SKILLS:
        # Use word boundary matching
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text_lower):
            found_tech.append(skill)

    for skill in SOFT_SKILLS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text_lower):
            found_soft.append(skill)

    return {"tech_skills": found_tech, "soft_skills": found_soft}


def extract_experience_requirements(text: str) -> Dict[str, Any]:
    """Extract experience requirements from job description."""
    text_lower = text.lower()
    requirements = {}

    # Years of experience
    years_match = re.search(r'(\d+)\+?\s*years?\s*(?:of\s*)?experience', text_lower)
    if years_match:
        requirements["min_years"] = int(years_match.group(1))

    # Degree requirements
    degrees = []
    if re.search(r'\b(bachelor|bs|ba)\b', text_lower):
        degrees.append("Bachelor's")
    if re.search(r'\b(master|ms|ma|msc)\b', text_lower):
        degrees.append("Master's")
    if re.search(r'\b(phd|doctorate|doctoral)\b', text_lower):
        degrees.append("PhD")
    if re.search(r'\bmba\b', text_lower):
        degrees.append("MBA")
    if degrees:
        requirements["degrees"] = degrees

    # Certifications mentioned
    certs = []
    if re.search(r'\btogaf\b', text_lower):
        certs.append("TOGAF")
    if re.search(r'\baws\s*(certified|certification)', text_lower):
        certs.append("AWS Certified")
    if re.search(r'\bazure\s*(certified|certification)', text_lower):
        certs.append("Azure Certified")
    if re.search(r'\bgcp\s*(certified|certification)|google cloud\s*(certified|certification)', text_lower):
        certs.append("GCP Certified")
    if re.search(r'\biso\s*42001', text_lower):
        certs.append("ISO 42001")
    if certs:
        requirements["certifications"] = certs

    return requirements


def analyze_jobs(jobs: List[Dict]) -> Dict[str, Any]:
    """Analyze job listings and extract skill frequencies."""
    tech_skills_counter = Counter()
    soft_skills_counter = Counter()
    years_experience = []
    degrees_counter = Counter()
    certs_counter = Counter()
    seniority_counter = Counter()
    locations_counter = Counter()
    companies = set()

    for job in jobs:
        desc = job.get("description", "")
        if not desc:
            continue

        # Extract skills
        skills = extract_skills_from_text(desc)
        tech_skills_counter.update(skills["tech_skills"])
        soft_skills_counter.update(skills["soft_skills"])

        # Extract experience requirements
        exp = extract_experience_requirements(desc)
        if "min_years" in exp:
            years_experience.append(exp["min_years"])
        if "degrees" in exp:
            degrees_counter.update(exp["degrees"])
        if "certifications" in exp:
            certs_counter.update(exp["certifications"])

        # Track metadata
        if job.get("seniority_level"):
            seniority_counter[job["seniority_level"]] += 1
        if job.get("location"):
            locations_counter[job["location"]] += 1
        if job.get("company"):
            companies.add(job["company"])

    return {
        "total_jobs": len(jobs),
        "jobs_with_descriptions": len([j for j in jobs if j.get("description")]),
        "tech_skills": dict(tech_skills_counter.most_common(50)),
        "soft_skills": dict(soft_skills_counter.most_common(20)),
        "avg_years_experience": sum(years_experience) / len(years_experience) if years_experience else None,
        "years_distribution": Counter(years_experience),
        "degrees": dict(degrees_counter.most_common()),
        "certifications": dict(certs_counter.most_common()),
        "seniority_levels": dict(seniority_counter.most_common()),
        "top_locations": dict(locations_counter.most_common(20)),
        "unique_companies": len(companies),
    }


def query_mongodb_jobs() -> List[Dict]:
    """Query MongoDB level-2 collection for AI Architect jobs."""
    try:
        from src.common.mongo_utils import get_mongo_client

        client = get_mongo_client()
        db = client["jobs"]
        collection = db["level-2"]

        # Query for AI Architect related jobs
        query = {
            "title": {
                "$regex": r"ai.*architect|architect.*ai|ml.*architect|machine learning.*architect|enterprise.*ai",
                "$options": "i"
            }
        }

        projection = {
            "title": 1,
            "company": 1,
            "description": 1,
            "structured_jd": 1,
            "location": 1,
            "_id": 1,
        }

        jobs = list(collection.find(query, projection))
        logger.info(f"Found {len(jobs)} AI Architect jobs in MongoDB")

        # Convert to common format
        for job in jobs:
            job["job_id"] = str(job.get("_id", ""))
            if "structured_jd" in job and job["structured_jd"]:
                # Extract description from structured_jd if available
                jd = job["structured_jd"]
                if isinstance(jd, dict):
                    desc_parts = []
                    for key in ["summary", "responsibilities", "requirements", "qualifications"]:
                        if key in jd:
                            val = jd[key]
                            if isinstance(val, list):
                                desc_parts.extend(val)
                            elif isinstance(val, str):
                                desc_parts.append(val)
                    if desc_parts:
                        job["description"] = "\n".join(desc_parts)

        return jobs

    except Exception as e:
        logger.error(f"Error querying MongoDB: {e}")
        return []


def format_markdown_report(linkedin_analysis: Dict, mongodb_analysis: Dict) -> str:
    """Format analysis results as markdown for marketability.md."""
    report = []

    report.append("## 4.5 Job Market Skills Analysis (January 2026)")
    report.append("")
    report.append("### Data Sources")
    report.append(f"- **LinkedIn Jobs API**: {linkedin_analysis['total_jobs']} jobs analyzed ({linkedin_analysis['jobs_with_descriptions']} with full descriptions)")
    report.append(f"- **MongoDB level-2**: {mongodb_analysis['total_jobs']} jobs analyzed")
    report.append("")

    # Combine skill counts
    combined_tech = Counter(linkedin_analysis["tech_skills"])
    combined_tech.update(mongodb_analysis["tech_skills"])

    combined_soft = Counter(linkedin_analysis["soft_skills"])
    combined_soft.update(mongodb_analysis["soft_skills"])

    report.append("### Technical Skills Frequency")
    report.append("")
    report.append("| Skill | Frequency | Category |")
    report.append("|-------|-----------|----------|")

    # Categorize skills
    skill_categories = {
        "python": "Programming", "java": "Programming", "scala": "Programming", "sql": "Programming",
        "r": "Programming", "go": "Programming", "rust": "Programming", "c++": "Programming",
        "tensorflow": "AI/ML Framework", "pytorch": "AI/ML Framework", "keras": "AI/ML Framework",
        "langchain": "AI/ML Framework", "langgraph": "AI/ML Framework", "hugging face": "AI/ML Framework",
        "openai": "AI/ML Framework", "anthropic": "AI/ML Framework",
        "aws": "Cloud Platform", "azure": "Cloud Platform", "gcp": "Cloud Platform",
        "sagemaker": "Cloud Platform", "vertex ai": "Cloud Platform", "databricks": "Cloud Platform",
        "docker": "Infrastructure", "kubernetes": "Infrastructure", "mlops": "Infrastructure",
        "spark": "Data Engineering", "kafka": "Data Engineering", "airflow": "Data Engineering",
        "togaf": "Architecture", "microservices": "Architecture", "api": "Architecture",
        "rag": "AI Technique", "llm": "AI Technique", "genai": "AI Technique", "agentic": "AI Technique",
        "nist": "Governance", "responsible ai": "Governance", "ai ethics": "Governance",
    }

    for skill, count in combined_tech.most_common(30):
        category = skill_categories.get(skill, "Other")
        report.append(f"| {skill.title()} | {count} | {category} |")

    report.append("")
    report.append("### Soft Skills Frequency")
    report.append("")
    report.append("| Skill | Frequency |")
    report.append("|-------|-----------|")

    for skill, count in combined_soft.most_common(15):
        report.append(f"| {skill.title()} | {count} |")

    report.append("")
    report.append("### Experience Requirements")
    report.append("")

    # Combine experience data
    all_years = list(linkedin_analysis.get("years_distribution", {}).keys()) + list(mongodb_analysis.get("years_distribution", {}).keys())
    if all_years:
        avg_years = sum(all_years) / len(all_years)
        report.append(f"- **Average Years Required**: {avg_years:.1f} years")

    combined_degrees = Counter(linkedin_analysis.get("degrees", {}))
    combined_degrees.update(mongodb_analysis.get("degrees", {}))
    if combined_degrees:
        report.append(f"- **Degree Requirements**: {', '.join([f'{d} ({c})' for d, c in combined_degrees.most_common()])}")

    combined_certs = Counter(linkedin_analysis.get("certifications", {}))
    combined_certs.update(mongodb_analysis.get("certifications", {}))
    if combined_certs:
        report.append(f"- **Certifications Mentioned**: {', '.join([f'{c} ({n})' for c, n in combined_certs.most_common()])}")

    report.append("")
    report.append("### Key Insights")
    report.append("")

    # Generate insights based on data
    top_tech = list(combined_tech.most_common(5))
    if top_tech:
        report.append(f"1. **Top Technical Skills**: {', '.join([s[0].title() for s in top_tech])} dominate job requirements")

    top_soft = list(combined_soft.most_common(3))
    if top_soft:
        report.append(f"2. **Critical Soft Skills**: {', '.join([s[0].title() for s in top_soft])} are most frequently required")

    # Check for governance/compliance skills
    governance_skills = [s for s, c in combined_tech.items() if s in ["nist", "iso 42001", "responsible ai", "ai ethics", "eu ai act"]]
    if governance_skills:
        report.append(f"3. **Governance Focus**: AI governance skills ({', '.join(governance_skills)}) increasingly required")

    # Check for agentic AI skills
    agentic_skills = [s for s, c in combined_tech.items() if s in ["langchain", "langgraph", "agentic", "multi-agent", "autogen", "crewai"]]
    if agentic_skills:
        report.append(f"4. **Agentic AI Demand**: {', '.join(agentic_skills)} frameworks appearing in job requirements")

    report.append("")
    report.append(f"*Analysis performed: {datetime.now().strftime('%Y-%m-%d')}*")
    report.append("")

    return "\n".join(report)


def main():
    """Main entry point for LinkedIn market analysis."""
    logger.info("Starting LinkedIn Market Analysis for AI Architect roles")

    # Step 1: Fetch LinkedIn jobs
    all_linkedin_jobs = []
    for query in SEARCH_QUERIES:
        jobs = fetch_all_jobs_for_query(query["keywords"], query["location"], max_pages=50)
        all_linkedin_jobs.extend(jobs)
        logger.info(f"Total LinkedIn jobs so far: {len(all_linkedin_jobs)}")
        time.sleep(2)  # Rate limiting between queries

    # Dedupe by job_id
    seen_ids = set()
    unique_jobs = []
    for job in all_linkedin_jobs:
        if job["job_id"] not in seen_ids:
            seen_ids.add(job["job_id"])
            unique_jobs.append(job)

    logger.info(f"Total unique LinkedIn jobs: {len(unique_jobs)}")

    # Step 2: Fetch job descriptions (sample for efficiency)
    logger.info("Fetching job descriptions...")
    jobs_with_desc = fetch_job_descriptions(unique_jobs, max_jobs=150)
    logger.info(f"Fetched {len(jobs_with_desc)} job descriptions")

    # Step 3: Query MongoDB
    logger.info("Querying MongoDB for AI Architect jobs...")
    mongodb_jobs = query_mongodb_jobs()

    # Step 4: Analyze both sources
    logger.info("Analyzing LinkedIn jobs...")
    linkedin_analysis = analyze_jobs(jobs_with_desc)

    logger.info("Analyzing MongoDB jobs...")
    mongodb_analysis = analyze_jobs(mongodb_jobs)

    # Step 5: Generate markdown report
    report = format_markdown_report(linkedin_analysis, mongodb_analysis)

    # Save report
    output_path = Path(__file__).parent.parent / "reports" / "ai_architect_skills_analysis.md"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(report)
    logger.info(f"Report saved to: {output_path}")

    # Also print summary
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    print(f"LinkedIn jobs analyzed: {linkedin_analysis['total_jobs']}")
    print(f"MongoDB jobs analyzed: {mongodb_analysis['total_jobs']}")
    print("\nTop 10 Technical Skills:")
    for skill, count in list(linkedin_analysis["tech_skills"].items())[:10]:
        print(f"  {skill}: {count}")
    print("\nTop 5 Soft Skills:")
    for skill, count in list(linkedin_analysis["soft_skills"].items())[:5]:
        print(f"  {skill}: {count}")
    print("="*60)

    # Return the report for direct insertion
    return report


if __name__ == "__main__":
    main()
