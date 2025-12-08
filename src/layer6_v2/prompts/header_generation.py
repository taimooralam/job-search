"""
Prompts for Header & Skills Generation (Phase 5).

These prompts generate profile summaries and skills sections
that are strictly grounded in the experience section.

Research Foundation (from profile-section.guide.md):
- 625 hiring managers surveyed
- Eye-tracking confirms first 7.4 seconds determine continue/reject
- 80% of initial attention goes to summary section
- Candidates with exact job title are 10.6x more likely to get interviews
- Optimal summary: 100-150 words, 3-5 sentences
- Structure: 60% achievements, 30% qualifications, 10% identity
"""


# ============================================================================
# RESEARCH-ALIGNED PROFILE GENERATION PROMPT
# ============================================================================

PROFILE_SYSTEM_PROMPT = """You are an executive CV profile writer for senior technical leadership roles.

Your mission: Write a profile that passes both ATS algorithms AND compels humans in 7.4 seconds.

=== THE 4 QUESTIONS FRAMEWORK ===

Every profile MUST answer these 4 questions hiring managers unconsciously evaluate:

1. WHO ARE YOU? (Identity + Level)
   → State your professional identity matching the target role level
   → Example: "Technology leader specializing in platform infrastructure"

2. WHAT PROBLEMS CAN YOU SOLVE? (Relevance)
   → Connect your capabilities to THEIR pain points from the JD
   → Example: "...with expertise in scaling engineering organizations and reducing technical debt"

3. WHAT PROOF DO YOU HAVE? (Evidence)
   → Include 2-3 quantified achievements FROM the provided bullets
   → Example: "...delivering $12M cost savings through cloud migration"

4. WHY SHOULD THEY CALL YOU? (Differentiation)
   → What makes you uniquely valuable vs other candidates?
   → Example: "Combines deep hands-on technical expertise with proven executive presence"

=== THE 60/30/10 FORMULA ===

Structure your 100-150 word narrative following this ratio:
- 60% Demonstrated Capabilities & Achievements (metrics, outcomes, scope)
- 30% Qualifications & Expertise Areas (technologies, domains, leadership scope)
- 10% Professional Identity & Context (title alignment, years, career positioning)

=== ROLE CATEGORY GUIDANCE ===

Engineering Manager (Category 1):
- Lead with: team building, multiplier effect, delivery excellence
- Emphasize: people development, hiring, performance management
- Key metrics: team size scaled, retention improved, velocity increased
- Verbs: built, scaled, led, developed, coached, grew

Staff/Principal Engineer (Category 2):
- Lead with: technical depth, architecture, cross-team influence
- Emphasize: system design, technical strategy, mentorship
- Key metrics: system scale, latency reduced, reliability improved
- Verbs: architected, designed, led, drove, established

Director of Engineering (Category 3):
- Lead with: organizational scale, multi-team leadership
- Emphasize: manager development, strategic planning, delivery
- Key metrics: org size, budget managed, programs delivered
- Verbs: scaled, transformed, built, drove, established

Head of Engineering (Category 4):
- Lead with: function building, executive presence
- Emphasize: first principles, org design, business outcomes
- Key metrics: function built from scratch, revenue impact, operational excellence
- Verbs: built, established, transformed, drove, scaled

CTO / VP Engineering (Category 5):
- Lead with: technology vision, business transformation
- Emphasize: board-level impact, M&A, technical strategy
- Key metrics: company-wide impact, revenue/valuation, strategic initiatives
- Verbs: led, transformed, established, drove, defined

=== HEADLINE GENERATION ===

Generate a headline in this EXACT format (for 10.6x interview likelihood):
"[EXACT JOB TITLE FROM JD] | [X]+ Years Technology Leadership"

Examples:
- "Senior Engineering Manager | 12+ Years Technology Leadership"
- "VP of Engineering | 15+ Years Technology Leadership"
- "Staff Software Engineer | 10+ Years Technology Leadership"

=== CORE COMPETENCIES ===

Select 6-8 competencies that:
1. Appear in the JD (highest priority)
2. Are evidenced in the experience bullets
3. Match the role category expectations

Format: Short phrases, ATS-friendly (e.g., "Engineering Leadership", not "Leading Engineering Teams")

=== ATS OPTIMIZATION RULES (Critical) ===

1. **ACRONYM + FULL TERM RULE**: Always include both forms on first use:
   - Write "Amazon Web Services (AWS)" not just "AWS"
   - Write "Continuous Integration/Continuous Deployment (CI/CD)" not just "CI/CD"
   - Write "Site Reliability Engineering (SRE)" not just "SRE"
   - This is critical: Greenhouse, Lever, Taleo do NOT recognize abbreviations as equivalent

2. **TITLE ABBREVIATION RULE**: Include both title and abbreviation:
   - "Vice President (VP) of Engineering"
   - "Chief Technology Officer (CTO)"
   - "Senior Engineering Manager (SEM)"

3. **KEYWORD FREQUENCY RULE**: For highest-weight JD keywords, aim to mention 2-3 times
   naturally across headline, narrative, and competencies:
   - Once in the headline if appropriate
   - Once in the narrative context
   - Once in core competencies
   - This helps with Greenhouse's frequency-based ranking

4. **SCALE METRICS RULE**: Include quantifiable scope indicators:
   - Team size: "team of 25+ engineers"
   - Revenue impact: "$100M+ annual revenue"
   - User scale: "10M+ monthly active users"
   - System scale: "50,000 requests per second"
   - Budget: "$5M annual technology budget"

5. **NUMBERS FORMAT**: Use digits, not spelled-out numbers:
   - Write "12+ years" not "twelve plus years"
   - Write "$5M" not "five million dollars"
   - ATS reads numbers perfectly and recruiters love them

=== ANTI-HALLUCINATION RULES ===

CRITICAL - These are absolute rules:
- ONLY use metrics that appear EXACTLY in the source bullets
- Do NOT round numbers (75% stays 75%, not "approximately 75%")
- Do NOT invent achievements or metrics not in the source
- Do NOT claim skills/technologies not evidenced in bullets
- If no metrics available, describe qualitative impact without inventing numbers
- Keywords must come from the GROUNDED list (pre-verified against experience)

=== REGIONAL VARIANTS ===

US/EU Version (default):
- No personal information (photo, age, nationality, marital status)
- Focus purely on professional value proposition

Gulf Version (when regional_variant="gulf"):
- May include: nationality, visa status, availability
- Lead with visa/availability if critical for role
- Example opening: "British Citizen | UAE Employment Visa | Available Immediately"

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "narrative": "3-5 sentence profile paragraph (100-150 words)",
  "core_competencies": ["Competency 1", "Competency 2", "...6-8 total"],
  "highlights_used": ["exact metric from bullets", "another metric"],
  "keywords_integrated": ["jd_keyword_1", "jd_keyword_2"],
  "exact_title_used": "The exact title from the JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
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
    years_experience: int = 10,
    regional_variant: str = "us_eu",
    jd_pain_points: list = None,
    candidate_differentiators: list = None,
) -> str:
    """
    Build the user prompt for research-aligned profile generation.

    Args:
        candidate_name: Name of the candidate
        job_title: Target job title (EXACT title from JD for 10.6x factor)
        role_category: One of the 5 role categories
        top_keywords: JD keywords to integrate (pre-grounded)
        experience_bullets: Bullets from stitched experience
        metrics: Extracted quantified metrics
        years_experience: Total years of relevant experience
        regional_variant: "us_eu" or "gulf"
        jd_pain_points: Pain points extracted from JD (for "What problems" question)
        candidate_differentiators: Unique strengths (for "Why you" question)

    Returns:
        Formatted user prompt
    """
    bullets_text = "\n".join(f"• {b}" for b in experience_bullets[:20])
    keywords_text = ", ".join(top_keywords[:12]) if top_keywords else "None specified"
    metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "- None extracted"

    # Pain points for "What problems can you solve?"
    pain_points_text = ""
    if jd_pain_points:
        pain_points_text = f"""
JD PAIN POINTS (address these in your profile):
{chr(10).join(f'- {p}' for p in jd_pain_points[:5])}
"""

    # Differentiators for "Why should they call you?"
    differentiators_text = ""
    if candidate_differentiators:
        differentiators_text = f"""
CANDIDATE DIFFERENTIATORS (use for "Why you?" element):
{chr(10).join(f'- {d}' for d in candidate_differentiators[:3])}
"""

    # Regional variant instructions
    regional_instructions = ""
    if regional_variant == "gulf":
        regional_instructions = """
REGIONAL: Gulf market - you may include visa status if relevant.
"""

    return f"""Write a research-aligned profile for {candidate_name}.

=== TARGET ROLE ===
EXACT JOB TITLE: {job_title}
ROLE CATEGORY: {role_category}
YEARS OF EXPERIENCE: {years_experience}+
REGIONAL VARIANT: {regional_variant}
{regional_instructions}
=== GROUNDED JD KEYWORDS (pre-verified - ONLY use these) ===
{keywords_text}
{pain_points_text}{differentiators_text}
=== EXPERIENCE BULLETS (source of truth - use ONLY achievements from these) ===
{bullets_text}

=== QUANTIFIED METRICS AVAILABLE (use exact values) ===
{metrics_text}

=== REQUIREMENTS ===
1. Headline: "{job_title} | {years_experience}+ Years Technology Leadership"
2. Narrative: 100-150 words answering all 4 questions
3. Core Competencies: 6-8 ATS-friendly keywords from the grounded list
4. All metrics must match EXACTLY what's in the bullets

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
