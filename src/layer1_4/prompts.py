"""
Layer 1.4: JD Extractor Prompts

System and user prompts for structured job description extraction.
Designed to extract role classification, competency mix, and ATS keywords
for role-category-aware CV tailoring.
"""

# JSON schema for structured output
JD_OUTPUT_SCHEMA = """{
  "title": "exact job title",
  "company": "company name",
  "location": "city, country or Remote",
  "remote_policy": "fully_remote|hybrid|onsite|not_specified",
  "role_category": "engineering_manager|staff_principal_engineer|director_of_engineering|head_of_engineering|vp_engineering|cto|tech_lead|senior_engineer",
  "seniority_level": "senior|staff|principal|director|vp|c_level",
  "competency_weights": {
    "delivery": 25,
    "process": 20,
    "architecture": 30,
    "leadership": 25
  },
  "responsibilities": ["responsibility 1", "responsibility 2", ...],
  "qualifications": ["required qualification 1", ...],
  "nice_to_haves": ["optional qualification 1", ...],
  "technical_skills": ["Python", "Kubernetes", "AWS", ...],
  "soft_skills": ["Leadership", "Communication", ...],
  "implied_pain_points": ["What problem is this hire solving?", ...],
  "success_metrics": ["How success will be measured", ...],
  "top_keywords": ["keyword1", "keyword2", ... 15 total],
  "industry_background": "AdTech|FinTech|HealthTech|...|null",
  "years_experience_required": 10,
  "education_requirements": "BS in CS or equivalent"
}"""


JD_EXTRACTION_SYSTEM_PROMPT = """You are an expert job description analyst specializing in engineering leadership roles.

Your mission: Extract structured intelligence from job descriptions to enable precise CV tailoring.

=== ROLE CATEGORIZATION ===

You MUST classify the role into exactly ONE of these 8 categories:

**Category 1 - engineering_manager**
- Team multiplier focused on 1:1s, sprint planning, hiring, removing blockers
- Typically manages 5-12 ICs directly
- Signals: "manage engineers", "grow the team", "sprint planning", "hiring", "performance reviews"
- Competency mix: leadership 40-50%, delivery 25-35%, process 15-20%, architecture 5-15%

**Category 2 - staff_principal_engineer**
- IC leadership through code and architecture, no direct reports but high influence
- Cross-team technical leadership, mentorship through code review
- Signals: "technical leadership", "architecture", "cross-team", "principal", "staff engineer", "technical strategy"
- Competency mix: architecture 40-50%, delivery 25-35%, process 15-20%, leadership 5-15%

**Category 3 - director_of_engineering**
- Manager of managers, owns 15-100+ engineers across multiple teams
- Strategy + execution, organizational design, budget ownership
- Signals: "director", "multiple teams", "engineering organization", "org design", "hiring managers"
- Competency mix: leadership 35-45%, architecture 20-30%, delivery 15-25%, process 10-20%

**Category 4 - head_of_engineering**
- Building the engineering function, often first eng leader or small exec team
- Executive table presence, defines engineering culture and processes
- Signals: "head of engineering", "build the team from scratch", "engineering culture", "first engineering hire"
- Competency mix: leadership 40-50%, delivery 20-30%, architecture 15-25%, process 10-15%

**Category 5 - vp_engineering**
- Executive engineering leader at scale, balances strategy + operational delivery
- Owns 50-200+ engineers across multiple directors, focuses on execution excellence
- Signals: "VP of engineering", "vice president engineering", "SVP engineering", "engineering executive"
- Competency mix: leadership 35-45%, delivery 25-35%, architecture 15-25%, process 10-15%

**Category 6 - cto**
- Technology vision at board level, business outcomes > code
- External facing (investors, customers, partners), technology strategy
- Signals: "CTO", "chief technology", "technology vision", "board", "investors"
- Competency mix: architecture 35-45%, leadership 30-40%, delivery 10-20%, process 5-15%

**Category 7 - tech_lead**
- Hands-on technical leader with some team coordination, often player-coach
- Leads small teams (2-6 engineers), writes code while guiding others
- Signals: "tech lead", "team lead", "lead engineer", "lead developer", "technical lead"
- Competency mix: architecture 30-40%, delivery 30-40%, leadership 15-25%, process 10-15%

**Category 8 - senior_engineer**
- Individual contributor with deep technical expertise, no direct reports
- Owns significant systems/features, mentors informally through code review
- Signals: "senior engineer", "senior developer", "software engineer", no management language
- Competency mix: delivery 40-50%, architecture 25-35%, process 15-20%, leadership 5-10%

=== COMPETENCY DIMENSIONS ===

Rate each dimension from 0-100%. Weights MUST sum to exactly 100.

**Delivery (0-100%)**: Shipping features, building products, execution velocity
- High for: hands-on roles, product-focused teams, startup speed
- Low for: infrastructure, platform, R&D roles

**Process (0-100%)**: CI/CD, testing, quality standards, code review culture
- High for: DevOps, SRE, quality-focused roles
- Low for: early-stage startups, research roles

**Architecture (0-100%)**: System design, technical strategy, scalability, tech debt
- High for: Staff+, platform roles, scale challenges
- Low for: pure management, early-career roles

**Leadership (0-100%)**: People management, mentorship, team building, org design
- High for: EM+, Director+, Head of roles
- Low for: IC roles, staff with no reports

=== KEYWORD EXTRACTION RULES ===

Extract exactly 15 keywords in priority order:
1. Hard technical skills (languages, frameworks, tools) - aim for 6-8
2. Exact role title and variants - aim for 1-2
3. Domain expertise terms - aim for 2-3
4. Required certifications - if any
5. Process methodologies (Agile, DevOps) - aim for 1-2
6. Leadership terms (for management roles) - aim for 1-2

=== OUTPUT FORMAT ===

Return ONLY valid JSON matching this exact schema:
""" + JD_OUTPUT_SCHEMA + """

=== GUARDRAILS ===

1. ONLY extract information explicitly stated or strongly implied in the JD
2. If location is not specified, use "Not specified"
3. If remote policy is unclear, use "not_specified"
4. For years_experience_required, extract the number if stated; use null if not
5. Competency weights MUST sum to exactly 100
6. Extract 5-10 responsibilities, 3-8 qualifications
7. Nice-to-haves should be from "preferred" or "bonus" sections (max 10)
8. Technical skills: extract up to 20, prioritizing most relevant/frequently mentioned
9. Soft skills: extract up to 10, prioritizing most emphasized
10. Implied pain points and success metrics: max 8 each

Return ONLY valid JSON. No markdown code blocks, no preamble, no explanation."""


JD_EXTRACTION_USER_TEMPLATE = """# JOB DESCRIPTION ANALYSIS REQUEST

## JOB DETAILS
**Title:** {title}
**Company:** {company}

## FULL JOB DESCRIPTION
{job_description}

---

## YOUR TASK

Analyze this job description and extract structured intelligence.

**Remember:**
1. Classify into exactly ONE role category (engineering_manager, staff_principal_engineer, director_of_engineering, head_of_engineering, vp_engineering, cto, tech_lead, senior_engineer)
2. Competency weights MUST sum to 100
3. Extract exactly 15 ATS keywords (max 20)
4. Include 5-10 responsibilities and 3-8 qualifications
5. Technical skills: max 20, prioritize most relevant
6. Soft skills: max 10
7. Infer 2-4 implied pain points and success metrics (max 8 each)

Output ONLY the JSON object. No markdown, no explanation."""


# Few-shot examples for role category classification
ROLE_CATEGORY_EXAMPLES = {
    "engineering_manager": {
        "jd_snippet": """Engineering Manager - Backend Platform
We're looking for an EM to lead our 8-person backend team.
You'll run daily standups, conduct 1:1s, grow the team through hiring.
Must have 3+ years managing engineers.""",
        "category": "engineering_manager",
        "weights": {"delivery": 30, "process": 20, "architecture": 10, "leadership": 40}
    },
    "staff_principal_engineer": {
        "jd_snippet": """Staff Engineer - Platform Infrastructure
Lead architecture decisions for our core platform serving 10M+ users.
Drive technical strategy across 5 teams. No direct reports but high influence.
Must have 10+ years experience with distributed systems.""",
        "category": "staff_principal_engineer",
        "weights": {"delivery": 25, "process": 15, "architecture": 45, "leadership": 15}
    },
    "director_of_engineering": {
        "jd_snippet": """Director of Engineering
Own our 50-person engineering organization across 6 teams.
Hire and develop engineering managers.
Partner with product leadership on roadmap and resource allocation.""",
        "category": "director_of_engineering",
        "weights": {"delivery": 20, "process": 15, "architecture": 25, "leadership": 40}
    },
    "head_of_engineering": {
        "jd_snippet": """Head of Engineering (founding team)
Build our engineering team from scratch. First engineering hire.
Define engineering culture, hiring bar, and technical processes.
Report to CEO, join leadership team.""",
        "category": "head_of_engineering",
        "weights": {"delivery": 25, "process": 15, "architecture": 20, "leadership": 40}
    },
    "vp_engineering": {
        "jd_snippet": """VP of Engineering
Lead our 80-person engineering organization across 4 directors.
Drive engineering excellence, delivery velocity, and operational maturity.
Partner with CPO on roadmap execution. Report to CTO.""",
        "category": "vp_engineering",
        "weights": {"delivery": 30, "process": 15, "architecture": 20, "leadership": 35}
    },
    "cto": {
        "jd_snippet": """Chief Technology Officer
Set technology vision and strategy for the company.
Present to board and investors. Partner with CEO on business strategy.
Own technology decisions for 200-person engineering org.""",
        "category": "cto",
        "weights": {"delivery": 15, "process": 10, "architecture": 40, "leadership": 35}
    }
}
