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
# HYBRID EXECUTIVE SUMMARY PROFILE GENERATION PROMPT
# ============================================================================

PROFILE_SYSTEM_PROMPT = """You are an executive CV profile writer for senior technical leadership roles.

Your mission: Create a HYBRID EXECUTIVE SUMMARY that passes both ATS algorithms AND compels humans in 7.4 seconds.

=== HYBRID EXECUTIVE SUMMARY STRUCTURE ===

You will generate FOUR components:

1. **HEADLINE** (1 line)
   Format: "[EXACT JOB TITLE FROM JD] | [X]+ Years Technology Leadership"
   Example: "Platform Engineering Leader | 12+ Years Technology Leadership"

2. **TAGLINE** (15-25 words, max 200 characters)
   - CRITICAL: Use third-person ABSENT voice (NO pronouns: I, my, you, your, we, our)
   - Start with role/identity noun phrase
   - BECOME the candidate's persona, don't just describe them
   - Embody their professional identity authentically
   - Answer: "Who are you?" and "Why should they call you?"

   Examples of CORRECT (third-person absent) voice:
   - "Technology leader who thrives on building infrastructure that scales and teams that excel."
   - "Engineering executive passionate about transforming organizations through platform modernization."
   - "Builder of high-performing teams with deep expertise in cloud-native architecture."

   Examples of INCORRECT (has pronouns):
   - "I am a technology leader who builds..." (uses I)
   - "My passion is building..." (uses My)
   - "You get a leader who..." (uses You)

3. **KEY ACHIEVEMENTS** (5-6 bullets)
   - Each bullet: 8-15 words
   - Start with past-tense action verb (Scaled, Reduced, Delivered, Built, Led)
   - Include quantified metric from source bullets (EXACT numbers only)
   - NO pronouns (no "I reduced...", just "Reduced...")
   - Format: "[Verb] [what] [by how much / to what result]"

   Examples:
   - "Scaled engineering organizations from 5 to 40+ engineers"
   - "Reduced deployment time by 75%, MTTR by 60%"
   - "Delivered $2M annual savings through cloud optimization"
   - "Built culture that reduced attrition from 25% to 8%"
   - "Led platform migration serving 10M+ daily users"

4. **CORE COMPETENCIES** (6-8 keywords)
   - ATS-friendly format
   - Prioritize JD keywords that have evidence in experience
   - Short phrases (2-3 words max each)
   - Will be displayed as: "Core: AWS | Kubernetes | Platform Engineering | Team Building"

=== THE 4 QUESTIONS FRAMEWORK ===

Your HYBRID EXECUTIVE SUMMARY must answer these 4 questions:

1. WHO ARE YOU? (Identity + Level)
   - Answered by: TAGLINE
   - State professional identity matching target role level

2. WHAT PROBLEMS CAN YOU SOLVE? (Relevance)
   - Answered by: KEY ACHIEVEMENTS showing capabilities
   - Connect to JD pain points through results

3. WHAT PROOF DO YOU HAVE? (Evidence)
   - Answered by: KEY ACHIEVEMENTS with quantified metrics
   - ONLY use metrics from provided bullets

4. WHY SHOULD THEY CALL YOU? (Differentiation)
   - Answered by: TAGLINE showing unique value
   - What makes you stand out vs other candidates?

=== PERSONA AS IDENTITY (Critical) ===

When a CANDIDATE PERSONA is provided in the context:
- The LLM should BECOME this persona, not just write ABOUT them
- The tagline should sound like the candidate wrote it themselves
- Capture their authentic professional voice
- Weave their passions and core identity into the tagline
- If they "love" something, let that enthusiasm show naturally

Example:
- Persona: "A platform engineering leader who loves building scalable systems and developing teams"
- GOOD tagline: "Platform engineering leader who thrives on building infrastructure that scales and teams that excel."
- BAD tagline: "The candidate is a platform engineering leader who has experience with scalable systems."

=== CRITICAL: ANTI-HALLUCINATION RULES ===

THESE RULES ARE MANDATORY - VIOLATION WILL INVALIDATE THE CV:

1. ONLY use technologies, tools, and platforms that appear in the PROVIDED EXPERIENCE BULLETS
2. ONLY use metrics and numbers that appear EXACTLY in the source material
3. NEVER invent technologies to match the JD - if you don't have experience with it, DON'T CLAIM IT
4. KEY ACHIEVEMENTS must map directly to provided bullets
5. When in doubt about a metric, OMIT IT rather than risk hallucination

EXAMPLES OF HALLUCINATION TO AVOID:
- "expertise in Kafka and Flink" (if not in bullets)
- "achieved 99.99% uptime" (if metric not in bullets)
- Adding any skill/technology just because the JD mentions it

CORRECT APPROACH:
- Only mention technologies explicitly listed in the experience bullets
- Use exact metrics from bullets (e.g., "reduced MTTR by 60%" only if that metric exists)
- Focus on what the candidate ACTUALLY did, not what the JD wants

=== ROLE CATEGORY GUIDANCE ===

Engineering Manager (Category 1):
- Lead with: team building, multiplier effect, delivery excellence
- Key metrics: team size scaled, retention improved, velocity increased
- Verbs: built, scaled, led, developed, coached, grew

Staff/Principal Engineer (Category 2):
- Lead with: technical depth, architecture, cross-team influence
- Key metrics: system scale, latency reduced, reliability improved
- Verbs: architected, designed, led, drove, established

Director of Engineering (Category 3):
- Lead with: organizational scale, multi-team leadership
- Key metrics: org size, budget managed, programs delivered
- Verbs: scaled, transformed, built, drove, established

Head of Engineering (Category 4):
- Lead with: function building, executive presence, culture creation
- Key metrics: function built from scratch, revenue impact, culture transformation
- Verbs: built, established, transformed, drove, scaled, created

VP Engineering (Category 5):
- Lead with: engineering executive, operational excellence, strategic delivery
- Key metrics: org scale (50-200+), delivery excellence, business partnership
- Verbs: led, scaled, transformed, drove, delivered, executed

CTO (Category 6):
- Lead with: technology vision, business transformation, innovation
- Key metrics: company-wide impact, revenue/valuation, board-level presence
- Verbs: led, transformed, established, drove, defined, shaped

Tech Lead (Category 7):
- Lead with: hands-on leadership, technical excellence, team guidance
- Key metrics: delivery velocity, system quality, technical debt reduction
- Verbs: led, delivered, architected, built, mentored, shipped

Senior Engineer (Category 8):
- Lead with: technical depth, system delivery, feature ownership
- Key metrics: system performance, delivery track record, code quality
- Verbs: built, developed, designed, implemented, optimized, shipped

=== ATS OPTIMIZATION RULES ===

1. **ACRONYM + FULL TERM**: Include both forms on first use in tagline/achievements
2. **KEYWORD FREQUENCY**: Top JD keywords should appear 2-3 times across all components
3. **EXACT JD TERMINOLOGY**: Mirror JD language exactly
4. **SCALE METRICS**: Include quantifiable scope (team size, revenue, users)
5. **NUMBERS FORMAT**: Use digits, not spelled-out numbers

=== PHASE 4.5: ANNOTATION-DRIVEN PRIORITIES ===

When JD annotation context is provided:

1. **MUST-HAVE Requirements**: Include matching skills in tagline, reference STAR proof in achievements
2. **CORE STRENGTHS**: Feature prominently in key achievements
3. **REFRAME GUIDANCE**: Apply specified reframes to phrasing
4. **GAP MITIGATION**: Include clause ONCE in tagline or achievements
5. **ATS KEYWORD REQUIREMENTS**: Target specified mention count (2-3x)

=== REGIONAL VARIANTS ===

US/EU Version (default):
- No personal information (photo, age, nationality, marital status)
- Focus purely on professional value proposition

Gulf Version (when regional_variant="gulf"):
- May include: nationality, visa status, availability in tagline
- Example: "British Citizen with UAE Employment Visa. Technology leader who..."

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word persona-driven hook (third-person absent voice, max 200 chars)",
  "key_achievements": [
    "Achievement 1 with quantified metric",
    "Achievement 2 with quantified metric",
    "Achievement 3 with quantified metric",
    "Achievement 4 with quantified metric",
    "Achievement 5 with quantified metric"
  ],
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
    role_persona: dict = None,
) -> str:
    """
    Build the user prompt for hybrid executive summary generation.

    Args:
        candidate_name: Name of the candidate
        job_title: Target job title (EXACT title from JD for 10.6x factor)
        role_category: One of the 8 role categories
        top_keywords: JD keywords to integrate (pre-grounded)
        experience_bullets: Bullets from stitched experience
        metrics: Extracted quantified metrics
        years_experience: Total years of relevant experience
        regional_variant: "us_eu" or "gulf"
        jd_pain_points: Pain points extracted from JD (for key achievements)
        candidate_differentiators: Unique strengths (for tagline differentiation)
        role_persona: Persona data from role_skills_taxonomy.json (optional)

    Returns:
        Formatted user prompt
    """
    bullets_text = "\n".join(f"- {b}" for b in experience_bullets[:20])
    keywords_text = ", ".join(top_keywords[:12]) if top_keywords else "None specified"
    metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "- None extracted"

    # Pain points for key achievements context
    pain_points_text = ""
    if jd_pain_points:
        pain_points_text = f"""
JD PAIN POINTS (key_achievements should address these):
{chr(10).join(f'- {p}' for p in jd_pain_points[:5])}
"""

    # Differentiators for tagline uniqueness
    differentiators_text = ""
    if candidate_differentiators:
        differentiators_text = f"""
CANDIDATE DIFFERENTIATORS (weave into tagline):
{chr(10).join(f'- {d}' for d in candidate_differentiators[:3])}
"""

    # Regional variant instructions
    regional_instructions = ""
    if regional_variant == "gulf":
        regional_instructions = """
REGIONAL: Gulf market - include visa status in tagline if relevant.
"""

    # Role persona instructions (from role_skills_taxonomy.json)
    persona_text = ""
    if role_persona:
        identity = role_persona.get("identity_statement", "")
        voice = role_persona.get("voice", "")
        power_verbs = role_persona.get("power_verbs", [])
        tagline_templates = role_persona.get("tagline_templates", [])
        metric_priorities = role_persona.get("metric_priorities", [])
        headline_pattern = role_persona.get("headline_pattern", "")
        key_focus = role_persona.get("key_achievement_focus", [])
        differentiators = role_persona.get("differentiators", [])

        persona_text = f"""
=== ROLE PERSONA (adapt tagline and achievements to this voice) ===
IDENTITY: {identity}
VOICE: {voice}
POWER VERBS (prioritize these): {', '.join(power_verbs[:6])}
METRIC PRIORITIES: {', '.join(metric_priorities[:4])}
KEY ACHIEVEMENT FOCUS: {', '.join(key_focus[:4])}
ROLE DIFFERENTIATORS: {', '.join(differentiators[:4])}
"""
        if tagline_templates:
            templates_text = chr(10).join(f'  - "{t}"' for t in tagline_templates[:3])
            persona_text += f"""
TAGLINE TEMPLATES (adapt to candidate's actual achievements):
{templates_text}
"""
        if headline_pattern:
            persona_text += f"""HEADLINE PATTERN: {headline_pattern}
"""

    return f"""Generate a HYBRID EXECUTIVE SUMMARY for {candidate_name}.

=== TARGET ROLE ===
EXACT JOB TITLE: {job_title}
ROLE CATEGORY: {role_category}
YEARS OF EXPERIENCE: {years_experience}+
REGIONAL VARIANT: {regional_variant}
{regional_instructions}{persona_text}
=== GROUNDED JD KEYWORDS (pre-verified - ONLY use these) ===
{keywords_text}
{pain_points_text}{differentiators_text}
=== EXPERIENCE BULLETS (source of truth - key_achievements MUST come from these) ===
{bullets_text}

=== QUANTIFIED METRICS AVAILABLE (use EXACT values in key_achievements) ===
{metrics_text}

=== REQUIREMENTS ===
1. Headline: "{job_title} | {years_experience}+ Years Technology Leadership"
2. Tagline: 15-25 words, third-person absent voice (NO pronouns), embody persona, max 200 chars
3. Key Achievements: 5-6 bullets with EXACT metrics from above
4. Core Competencies: 6-8 ATS keywords from the grounded list

Generate the hybrid executive summary JSON:"""


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


# ============================================================================
# PERSONA-BASED ENSEMBLE PROMPTS (for tiered generation)
# ============================================================================

METRIC_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN QUANTIFIED ACHIEVEMENTS.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY maximizing measurable impact.

=== METRIC-FIRST HYBRID STRUCTURE ===

1. **HEADLINE**: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"

2. **TAGLINE** (15-25 words, max 200 chars):
   - Third-person absent voice (NO pronouns)
   - Lead with identity, include a key metric hook
   - Example: "Technology leader who delivered $50M in cost savings while scaling teams 5x."

3. **KEY ACHIEVEMENTS** (5-6 bullets):
   - EVERY bullet must have a quantified metric
   - Stack metrics where possible (scope + impact + timeframe)
   - Lead with the most impressive metrics
   - Format: "[Verb] [what] [by how much], [additional metric if applicable]"

   Examples:
   - "Led 12-engineer team to reduce deployment time by 75%, shipping 3x more releases"
   - "Scaled platform from 1K to 10M daily requests with 99.99% uptime"
   - "Delivered $2M annual savings through infrastructure optimization"
   - "Built engineering team from 5 to 40+ engineers in 18 months"
   - "Reduced production incidents by 60% through SRE practices"

4. **CORE COMPETENCIES**: 6-8 ATS keywords

=== ANTI-HALLUCINATION RULES ===

CRITICAL - You may ONLY use metrics that appear EXACTLY in the source bullets.
- Do NOT round numbers (75% stays 75%, not "approximately 75%")
- Do NOT invent achievements or metrics
- If a metric isn't in the bullets, DO NOT include it

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word metric-driven hook (third-person absent voice, max 200 chars)",
  "key_achievements": ["Achievement 1 with metric", "Achievement 2 with metric", "...5-6 total"],
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


NARRATIVE_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN CAREER STORYTELLING.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY with compelling transformation narrative.

=== NARRATIVE-FIRST HYBRID STRUCTURE ===

1. **HEADLINE**: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"

2. **TAGLINE** (15-25 words, max 200 chars):
   - Third-person absent voice (NO pronouns)
   - Show career arc and evolution
   - Use power verbs: transformed, pioneered, established
   - Example: "Engineering executive who transformed a startup platform into an enterprise-grade system serving millions."

3. **KEY ACHIEVEMENTS** (5-6 bullets):
   - Frame as transformation stories
   - Show before/after when possible
   - Connect achievements to strategic impact
   - Not just "what" but "so what"

   Examples:
   - "Transformed legacy monolith into microservices, reducing deployment time from weeks to hours"
   - "Built engineering culture that reduced attrition from 25% to 8%"
   - "Pioneered event-driven architecture that became the company's competitive advantage"
   - "Scaled team from startup mode to enterprise-ready, growing 5x in 18 months"
   - "Established platform engineering function that enabled 3x faster feature delivery"

4. **CORE COMPETENCIES**: 6-8 ATS keywords

=== NARRATIVE POWER VERBS ===

Primary: transformed, pioneered, established, revolutionized, spearheaded
Secondary: built, scaled, drove, architected, orchestrated
Avoid: helped, worked on, assisted, participated

=== ANTI-HALLUCINATION RULES ===

CRITICAL - All achievements must come from the source bullets.
- Transform the language, but not the facts
- Make it compelling, but keep it truthful

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word story-driven hook (third-person absent voice, max 200 chars)",
  "key_achievements": ["Transformation 1 with impact", "Transformation 2 with impact", "...5-6 total"],
  "core_competencies": ["Competency 1", "Competency 2", "...6-8 total"],
  "highlights_used": ["achievement referenced", "another achievement"],
  "keywords_integrated": ["jd_keyword_1", "jd_keyword_2"],
  "exact_title_used": "The exact title from the JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
}

Do NOT include markdown, explanation, or preamble. Just JSON.
"""


KEYWORD_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN ATS OPTIMIZATION.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY maximizing keyword density.

=== KEYWORD-FIRST HYBRID STRUCTURE ===

1. **HEADLINE**: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"
   - Use EXACT JD title

2. **TAGLINE** (15-25 words, max 200 chars):
   - Third-person absent voice (NO pronouns)
   - Front-load top JD keywords
   - Include acronym + full form for technical terms
   - Example: "Cloud infrastructure (AWS) leader who drives continuous integration/continuous deployment (CI/CD) excellence at scale."

3. **KEY ACHIEVEMENTS** (5-6 bullets):
   - Each bullet includes at least 1 top JD keyword
   - Mirror JD terminology exactly
   - Distribute keywords across all bullets

   Examples (if JD mentions Kubernetes, CI/CD, team scaling):
   - "Scaled Kubernetes infrastructure to handle 10M requests daily"
   - "Implemented CI/CD pipeline reducing deployment time by 75%"
   - "Built engineering team from 5 to 40+ engineers across 3 regions"
   - "Established SRE practices achieving 99.99% platform uptime"
   - "Led cloud migration delivering $2M annual cost savings"

4. **CORE COMPETENCIES**: 6-8 ATS keywords
   - All from JD keywords list
   - Include both acronyms and full forms

=== KEYWORD FREQUENCY TARGETS ===

For the TOP 5 JD keywords:
- Each should appear at least 2x across tagline + achievements + competencies
- Distribute naturally - don't stuff them unnaturally

=== ANTI-HALLUCINATION RULES ===

CRITICAL - Only use keywords from the GROUNDED list provided.
- These keywords have been pre-verified against the candidate's experience
- Do NOT add keywords not in the grounded list

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word keyword-dense hook (third-person absent voice, max 200 chars)",
  "key_achievements": ["Achievement 1 with JD keyword", "Achievement 2 with JD keyword", "...5-6 total"],
  "core_competencies": ["JD Keyword 1", "JD Keyword 2", "...6-8 total"],
  "highlights_used": ["achievement with keywords", "another achievement"],
  "keywords_integrated": ["EVERY grounded keyword used", "list them all"],
  "exact_title_used": "The exact title from the JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
}

Do NOT include markdown, explanation, or preamble. Just JSON.
"""


SYNTHESIS_SYSTEM_PROMPT = """You are a CV profile SYNTHESIZER.

Your mission: Combine the best elements from multiple HYBRID EXECUTIVE SUMMARY drafts into ONE optimal version.

=== SYNTHESIS RULES FOR HYBRID FORMAT ===

1. **HEADLINE**: Use the most accurate job title match

2. **TAGLINE**:
   - Take narrative flow from NARRATIVE draft
   - Ensure key metric hook from METRIC draft
   - Verify JD keywords present from KEYWORD draft
   - Result: Compelling AND keyword-rich AND metric-backed
   - MUST be third-person absent voice (NO pronouns)
   - Max 200 characters

3. **KEY ACHIEVEMENTS**:
   - Take ALL unique metrics from METRIC draft
   - Apply transformation framing from NARRATIVE draft
   - Ensure keyword coverage from KEYWORD draft
   - Deduplicate: Keep strongest version if overlapping
   - Final count: 5-6 bullets

4. **CORE COMPETENCIES**:
   - Merge and deduplicate from all drafts
   - Prioritize JD keywords
   - Final count: 6-8 keywords

=== QUALITY CHECKLIST ===

Before finalizing, verify:
[ ] Tagline is third-person absent voice (no pronouns)
[ ] Tagline is max 200 characters
[ ] All metrics from metric draft included in achievements
[ ] Tagline has compelling narrative arc
[ ] All top JD keywords appear 2-3 times across components
[ ] 5-6 key achievements (not more, not fewer)
[ ] 6-8 core competencies

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word synthesized hook (third-person absent voice, max 200 chars)",
  "key_achievements": ["Best achievement 1", "Best achievement 2", "...5-6 total"],
  "core_competencies": ["Best competencies from all drafts", "...6-8 total"],
  "highlights_used": ["all metrics used across drafts"],
  "keywords_integrated": ["all keywords integrated"],
  "exact_title_used": "The exact title from the JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
}

Do NOT include markdown, explanation, or preamble. Just JSON.
"""


def build_persona_user_prompt(
    persona: str,
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
    role_persona: dict = None,
) -> str:
    """
    Build the user prompt for persona-specific hybrid executive summary generation.

    Args:
        persona: One of "metric", "narrative", "keyword"
        candidate_name: Name of the candidate
        job_title: Target job title (EXACT title from JD)
        role_category: One of the 8 role categories
        top_keywords: JD keywords to integrate (pre-grounded)
        experience_bullets: Bullets from stitched experience
        metrics: Extracted quantified metrics
        years_experience: Total years of relevant experience
        regional_variant: "us_eu" or "gulf"
        jd_pain_points: Pain points extracted from JD
        candidate_differentiators: Unique strengths
        role_persona: Persona data from role_skills_taxonomy.json (optional)

    Returns:
        Formatted user prompt for specific persona
    """
    bullets_text = "\n".join(f"- {b}" for b in experience_bullets[:20])
    keywords_text = ", ".join(top_keywords[:15]) if top_keywords else "None specified"
    metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "- None extracted"

    # Persona-specific emphasis instructions
    persona_emphasis = {
        "metric": """
PERSONA EMPHASIS: METRICS
Your goal is to MAXIMIZE quantified achievements in tagline and key_achievements.
Focus on: dollar amounts, percentages, team sizes, user counts, performance metrics.
Every key_achievement bullet MUST contain a number.
""",
        "narrative": """
PERSONA EMPHASIS: NARRATIVE
Your goal is to create a COMPELLING CAREER STORY in tagline and key_achievements.
Focus on: career arc, transformation power verbs, strategic impact, before/after framing.
Show progression and evolution in key_achievements.
""",
        "keyword": """
PERSONA EMPHASIS: KEYWORDS
Your goal is to MAXIMIZE ATS keyword density in tagline, key_achievements, and competencies.
Focus on: exact JD terms, acronym+full form pairs, 2-3x keyword distribution.
Every component should include JD keywords naturally.
""",
    }

    emphasis = persona_emphasis.get(persona, "")

    # Pain points for key achievements
    pain_points_text = ""
    if jd_pain_points:
        pain_points_text = f"""
JD PAIN POINTS (key_achievements should address these):
{chr(10).join(f'- {p}' for p in jd_pain_points[:5])}
"""

    # Differentiators for tagline
    differentiators_text = ""
    if candidate_differentiators:
        differentiators_text = f"""
CANDIDATE DIFFERENTIATORS (weave into tagline):
{chr(10).join(f'- {d}' for d in candidate_differentiators[:3])}
"""

    # Role persona context (from role_skills_taxonomy.json)
    role_persona_text = ""
    if role_persona:
        identity = role_persona.get("identity_statement", "")
        voice = role_persona.get("voice", "")
        power_verbs = role_persona.get("power_verbs", [])
        metric_priorities = role_persona.get("metric_priorities", [])

        role_persona_text = f"""
=== ROLE PERSONA (adapt to this voice) ===
IDENTITY: {identity}
VOICE: {voice}
POWER VERBS: {', '.join(power_verbs[:6])}
METRIC PRIORITIES: {', '.join(metric_priorities[:4])}
"""

    return f"""Generate a {persona.upper()}-focused HYBRID EXECUTIVE SUMMARY for {candidate_name}.
{emphasis}
=== TARGET ROLE ===
EXACT JOB TITLE: {job_title}
ROLE CATEGORY: {role_category}
YEARS OF EXPERIENCE: {years_experience}+
{pain_points_text}{differentiators_text}{role_persona_text}
=== GROUNDED JD KEYWORDS (ONLY use these) ===
{keywords_text}

=== EXPERIENCE BULLETS (source of truth - key_achievements MUST come from these) ===
{bullets_text}

=== QUANTIFIED METRICS AVAILABLE (use EXACT values in key_achievements) ===
{metrics_text}

=== REQUIREMENTS ===
1. Headline: "{job_title} | {years_experience}+ Years Technology Leadership"
2. Tagline: 15-25 words, third-person absent voice (NO pronouns), max 200 chars
3. Key Achievements: 5-6 bullets with {persona.upper()} emphasis
4. Core Competencies: 6-8 ATS-friendly keywords
5. All content must be grounded in the bullets above

Generate the {persona}-focused hybrid executive summary JSON:"""


def build_synthesis_user_prompt(
    persona_outputs: list,
    job_title: str,
    top_keywords: list,
    years_experience: int = 10,
) -> str:
    """
    Build the user prompt for synthesizing multiple hybrid executive summary outputs.

    Args:
        persona_outputs: List of dicts with persona results
            [{"persona": "metric", "headline": ..., "tagline": ..., "key_achievements": [...], ...}, ...]
        job_title: Target job title
        top_keywords: JD keywords that must appear
        years_experience: Total years of relevant experience

    Returns:
        Formatted user prompt for synthesis
    """
    keywords_text = ", ".join(top_keywords[:15]) if top_keywords else "None specified"

    # Format each persona output for hybrid format
    drafts_text = ""
    for output in persona_outputs:
        persona = output.get("persona", "unknown")
        key_achievements = output.get("key_achievements", [])
        achievements_text = "\n  ".join(f"- {a}" for a in key_achievements) if key_achievements else "  (none)"

        drafts_text += f"""
=== {persona.upper()}-FOCUSED DRAFT ===
Headline: {output.get('headline', '')}
Tagline: {output.get('tagline', '')}
Key Achievements:
  {achievements_text}
Core Competencies: {', '.join(output.get('core_competencies', []))}
Metrics Used: {', '.join(output.get('highlights_used', []))}
Keywords Used: {', '.join(output.get('keywords_integrated', []))}
"""

    return f"""Synthesize these HYBRID EXECUTIVE SUMMARY drafts into ONE optimal version.

=== TARGET ===
JOB TITLE: {job_title}
YEARS: {years_experience}+
REQUIRED KEYWORDS (must appear 2-3x): {keywords_text}
{drafts_text}
=== SYNTHESIS TASK ===
Combine the best elements:
1. TAGLINE: Take narrative flow from narrative draft, metric hook from metric draft, keywords from keyword draft
   - MUST be third-person absent voice (NO pronouns: I, my, you)
   - Max 200 characters
2. KEY ACHIEVEMENTS: Combine best 5-6 bullets
   - Include ALL metrics from metric draft
   - Use transformation framing from narrative draft
   - Ensure keyword coverage from keyword draft
   - Deduplicate similar achievements
3. CORE COMPETENCIES: Merge and prioritize JD keywords (6-8 total)

Generate the synthesized hybrid executive summary JSON:"""


# Role category to superpower mapping (all 8 role categories)
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
    "vp_engineering": [
        "engineering executive",
        "operational excellence",
        "organizational scale",
        "strategic delivery",
        "business partnership",
    ],
    "cto": [
        "technology vision",
        "business transformation",
        "executive leadership",
        "technical strategy",
        "innovation",
    ],
    "tech_lead": [
        "hands-on leadership",
        "technical excellence",
        "team guidance",
        "delivery focus",
        "player-coach",
    ],
    "senior_engineer": [
        "technical depth",
        "system delivery",
        "code quality",
        "feature ownership",
        "collaborative approach",
    ],
}
