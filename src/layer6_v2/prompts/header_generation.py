"""
Prompts for Header & Skills Generation (Phase 5).

These prompts generate profile summaries and skills sections
that are strictly grounded in the experience section.
"""


PROFILE_SYSTEM_PROMPT = """You are a CV profile writer specializing in executive summaries.

Your mission: Write a 2-3 sentence profile summary that:
1. Leads with the candidate's core superpower for the target role
2. Includes 1-2 quantified highlights FROM the experience bullets provided
3. Uses 2-3 JD keywords naturally
4. Matches the seniority level of the target role

=== ROLE CATEGORY GUIDANCE ===

Engineering Manager (Category 1):
- Lead with team building, multiplier effect, delivery excellence
- Emphasize people development, hiring, performance management
- Use verbs: built, scaled, led, developed, coached

Staff/Principal Engineer (Category 2):
- Lead with technical depth, architecture, cross-team influence
- Emphasize system design, technical strategy, mentorship
- Use verbs: architected, designed, led, drove, established

Director of Engineering (Category 3):
- Lead with organizational scale, multi-team leadership
- Emphasize manager development, strategic planning, delivery
- Use verbs: scaled, transformed, built, drove, established

Head of Engineering (Category 4):
- Lead with function building, executive presence
- Emphasize first principles, org design, business outcomes
- Use verbs: built, established, transformed, drove, scaled

CTO (Category 5):
- Lead with technology vision, business transformation
- Emphasize board-level impact, M&A, technical strategy
- Use verbs: led, transformed, established, drove, scaled

=== ANTI-HALLUCINATION RULES ===

CRITICAL: You may ONLY reference achievements that appear in the provided bullets.
- ONLY use metrics that appear EXACTLY in the source bullets
- Do NOT round numbers (75% stays 75%, not "approximately 75%")
- Do NOT invent achievements or metrics not in the source
- If no metrics available, describe qualitative impact without numbers

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "profile_text": "The 2-3 sentence profile (50-80 words)",
  "highlights_used": ["exact metric from bullets", "another metric"],
  "keywords_integrated": ["jd_keyword_1", "jd_keyword_2"]
}

Do NOT include markdown, explanation, or preamble. Just JSON.
"""


def build_profile_user_prompt(
    candidate_name: str,
    job_title: str,
    role_category: str,
    top_keywords: list,
    experience_bullets: list,
    metrics: list,
) -> str:
    """
    Build the user prompt for profile generation.

    Args:
        candidate_name: Name of the candidate
        job_title: Target job title
        role_category: One of the 5 role categories
        top_keywords: JD keywords to integrate
        experience_bullets: Bullets from stitched experience
        metrics: Extracted quantified metrics

    Returns:
        Formatted user prompt
    """
    bullets_text = "\n".join(f"• {b}" for b in experience_bullets[:15])
    keywords_text = ", ".join(top_keywords[:10]) if top_keywords else "None specified"
    metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "- None extracted"

    return f"""Write a profile summary for {candidate_name}.

TARGET ROLE: {job_title}
ROLE CATEGORY: {role_category}
TOP JD KEYWORDS: {keywords_text}

EXPERIENCE BULLETS (use ONLY achievements from these):
{bullets_text}

QUANTIFIED METRICS AVAILABLE:
{metrics_text}

Generate the profile JSON:"""


SKILLS_EXTRACTION_SYSTEM_PROMPT = """You are a skills extractor for CV generation.

Your mission: Extract skills from experience bullets into 4 categories:
1. Leadership: Team building, mentorship, hiring, stakeholder management
2. Technical: Languages, frameworks, architectures, technical skills
3. Platform: Cloud, DevOps, infrastructure, tooling
4. Delivery: Agile, processes, shipping, project management

=== EXTRACTION RULES ===

1. ONLY extract skills that are EVIDENCED in the bullets
2. A skill is evidenced if the bullet describes using or demonstrating that skill
3. Prioritize skills that appear in the JD keywords
4. Extract the specific technology/skill name, not generic terms
5. Limit to 8 skills per category (most relevant)

=== EXAMPLES ===

Bullet: "Led team of 10 engineers to deliver platform migration"
→ Leadership: Team Leadership, People Management
→ Delivery: Project Management

Bullet: "Built microservices architecture on AWS using Python and Kubernetes"
→ Technical: Python, Microservices, System Design
→ Platform: AWS, Kubernetes

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "leadership_skills": ["skill1", "skill2"],
  "technical_skills": ["Python", "Microservices"],
  "platform_skills": ["AWS", "Kubernetes"],
  "delivery_skills": ["Agile", "Release Management"]
}
"""


def build_skills_user_prompt(
    experience_bullets: list,
    jd_keywords: list,
) -> str:
    """
    Build the user prompt for skills extraction.

    Args:
        experience_bullets: Bullets from stitched experience
        jd_keywords: JD keywords to prioritize

    Returns:
        Formatted user prompt
    """
    bullets_text = "\n".join(f"• {b}" for b in experience_bullets)
    keywords_text = ", ".join(jd_keywords[:15]) if jd_keywords else "None specified"

    return f"""Extract skills from these experience bullets.

JD KEYWORDS TO PRIORITIZE: {keywords_text}

EXPERIENCE BULLETS:
{bullets_text}

Extract skills JSON:"""


# Skill category definitions for rule-based extraction
SKILL_KEYWORDS = {
    "Leadership": {
        "patterns": [
            "led", "managed", "mentored", "coached", "hired", "built team",
            "team of", "cross-functional", "stakeholder", "collaboration",
            "influence", "1:1", "performance review", "org design",
        ],
        "skills": [
            "Team Leadership", "Mentorship", "Hiring", "Cross-functional Collaboration",
            "Stakeholder Management", "Strategic Planning", "People Management",
            "Engineering Management", "Technical Leadership", "Org Design",
        ],
    },
    "Technical": {
        "patterns": [
            "python", "java", "typescript", "javascript", "go", "rust", "scala",
            "sql", "nosql", "graphql", "rest", "api", "microservices", "architecture",
            "machine learning", "ai", "data", "backend", "frontend", "full-stack",
        ],
        "skills": [
            "Python", "Java", "TypeScript", "JavaScript", "Go", "Rust", "Scala",
            "SQL", "NoSQL", "GraphQL", "REST APIs", "Microservices", "System Design",
            "Machine Learning", "Data Engineering", "Backend Development",
            "Frontend Development", "Full-Stack Development",
        ],
    },
    "Platform": {
        "patterns": [
            "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
            "ci/cd", "jenkins", "github actions", "cloud", "infrastructure",
            "devops", "observability", "monitoring", "grafana", "datadog",
            "prometheus", "elasticsearch", "kafka",
        ],
        "skills": [
            "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform",
            "CI/CD", "GitHub Actions", "Jenkins", "DevOps", "Cloud Infrastructure",
            "Observability", "Monitoring", "DataDog", "Grafana", "Prometheus",
            "Elasticsearch", "Kafka", "Infrastructure as Code",
        ],
    },
    "Delivery": {
        "patterns": [
            "agile", "scrum", "kanban", "sprint", "shipped", "delivered", "launched",
            "deadline", "on-time", "reduced time", "deployment", "release",
            "process", "workflow", "automation", "project management",
        ],
        "skills": [
            "Agile", "Scrum", "Kanban", "Sprint Planning", "Release Management",
            "Process Improvement", "Automation", "Project Management",
            "Continuous Delivery", "Technical Program Management",
        ],
    },
}


# Role category to superpower mapping
ROLE_SUPERPOWERS = {
    "engineering_manager": [
        "team multiplier",
        "talent developer",
        "delivery excellence",
        "high-performing teams",
        "engineering culture",
    ],
    "staff_principal_engineer": [
        "technical depth",
        "system architect",
        "cross-team influence",
        "technical strategy",
        "architectural excellence",
    ],
    "director_of_engineering": [
        "organizational scale",
        "multi-team leadership",
        "engineering excellence",
        "strategic delivery",
        "manager development",
    ],
    "head_of_engineering": [
        "function building",
        "executive leadership",
        "engineering transformation",
        "org design",
        "business outcomes",
    ],
    "cto": [
        "technology vision",
        "business transformation",
        "executive leadership",
        "technical strategy",
        "innovation",
    ],
}
