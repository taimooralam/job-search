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

=== CRITICAL: ANTI-HALLUCINATION RULES ===

THESE RULES ARE MANDATORY - VIOLATION WILL INVALIDATE THE CV:

1. ONLY use technologies, tools, and platforms that appear in the PROVIDED EXPERIENCE BULLETS
2. ONLY use metrics and numbers that appear EXACTLY in the source material
3. NEVER invent technologies to match the JD - if you don't have experience with it, DON'T CLAIM IT
4. If the JD asks for "Kafka" but the candidate only has "RabbitMQ", do NOT add Kafka
5. If the JD asks for "ClickHouse" but it's not in the bullets, do NOT add ClickHouse
6. When in doubt about a technology, OMIT IT rather than risk hallucination

EXAMPLES OF HALLUCINATION TO AVOID:
✗ "expertise in Kafka and Flink" (if not in bullets)
✗ "ClickHouse data schemas" (if not in bullets)
✗ "achieved 99.99% uptime" (if metric not in bullets)
✗ Adding any skill/technology just because the JD mentions it

CORRECT APPROACH:
✓ Only mention technologies explicitly listed in the experience bullets
✓ Use exact metrics from bullets (e.g., "reduced MTTR by 60%" only if that metric exists)
✓ Focus on what the candidate ACTUALLY did, not what the JD wants

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

=== PHASE 4.5: ANNOTATION-DRIVEN PRIORITIES ===

When JD annotation context is provided, follow these priority rules:

1. **MUST-HAVE Requirements (highest priority)**:
   - These requirements appear under "### MUST-HAVE" in the context
   - ALWAYS include matching skills in headline/tagline
   - Reference STAR proof statements when provided
   - Example: If "Kubernetes" is must-have with proof "reduced deployment time by 75%",
     include both the skill AND the metric

2. **CORE STRENGTHS (emphasize in summary)**:
   - Appear under "### CORE STRENGTHS"
   - Feature these prominently in the narrative paragraph
   - Use them to answer "What problems can you solve?"

3. **REFRAME GUIDANCE (apply to phrasing)**:
   - Appear under "### REFRAME GUIDANCE"
   - Replace generic phrasing with the specified reframe
   - Example: "platform engineering" → "platform modernization leadership"

4. **GAP MITIGATION (include once)**:
   - Appears under "### GAP MITIGATION"
   - Include this clause ONCE in the summary (not multiple times)
   - Position positively as adjacent strength

5. **ATS KEYWORD REQUIREMENTS**:
   - Include BOTH acronym AND full form for specified keywords
   - Target the specified mention count (usually 2-3x)
   - Example: "Kubernetes (K8s)" appears 2-3 times across header/summary/skills

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


# ============================================================================
# PERSONA-BASED ENSEMBLE PROMPTS (for tiered generation)
# ============================================================================

METRIC_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN QUANTIFIED ACHIEVEMENTS.

Your PRIMARY MISSION: Maximize measurable impact metrics in every sentence.

=== METRIC-FIRST PHILOSOPHY ===

1. **Lead EVERY sentence with a number**:
   - Start with: "$X", "X%", "Xk/Xm", "team of X", "X+ years"
   - Example: "$2M cost savings delivered through cloud migration"
   - Example: "15-person engineering team scaled to 40+ in 18 months"

2. **Stack multiple metrics per statement**:
   - Combine scope + impact + timeframe
   - Example: "Led 12-engineer team to reduce deployment time by 75%, shipping 3x more releases quarterly"

3. **Include operational metrics**:
   - Uptime: "99.99% availability"
   - Latency: "reduced p99 latency from 500ms to 50ms"
   - Throughput: "50,000 requests/second at peak"
   - Error rates: "reduced production incidents by 60%"

4. **Use scale indicators**:
   - Team size: "team of 25+ engineers"
   - Revenue impact: "$100M+ annual revenue"
   - User scale: "10M+ monthly active users"
   - Budget: "$5M annual technology budget"

=== ANTI-HALLUCINATION RULES ===

CRITICAL - You may ONLY use metrics that appear EXACTLY in the source bullets.
- Do NOT round numbers (75% stays 75%, not "approximately 75%")
- Do NOT invent achievements or metrics
- If a metric isn't in the bullets, DO NOT include it

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "narrative": "3-5 sentence profile PACKED with metrics (100-150 words)",
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

Your PRIMARY MISSION: Create a compelling transformation narrative that shows career progression.

=== NARRATIVE-FIRST PHILOSOPHY ===

1. **Lead with career arc and evolution**:
   - Show progression: "From X to Y, achieving Z"
   - Example: "Technology leader who evolved from hands-on engineer to executive driving $50M initiatives"
   - Example: "Transformed from technical contributor to organization builder, scaling teams across 3 continents"

2. **Use power verbs that convey transformation**:
   - Primary: transformed, pioneered, established, revolutionized, spearheaded
   - Secondary: built, scaled, drove, architected, orchestrated
   - Avoid: helped, worked on, assisted, participated

3. **Connect achievements to strategic impact**:
   - Not just "what" but "so what"
   - Example: "Pioneered event-driven architecture that became the company's competitive advantage"
   - Example: "Built engineering culture that reduced attrition from 25% to 8%"

4. **Structure as a story with beginning, middle, end**:
   - Beginning: Professional identity and context
   - Middle: Key transformations and achievements
   - End: Unique value proposition and forward-looking capability

=== THE 4 QUESTIONS (Narrative Style) ===

1. WHO: "Technology leader who..." (identity through action)
2. WHAT PROBLEMS: "...specializing in [pain points from JD]..."
3. PROOF: "...delivering [transformation story with metrics]..."
4. WHY YOU: "...uniquely combining [differentiators]"

=== ANTI-HALLUCINATION RULES ===

CRITICAL - All achievements must come from the source bullets.
- Transform the language, but not the facts
- Make it compelling, but keep it truthful

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "narrative": "3-5 sentence STORY-driven profile (100-150 words)",
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

Your PRIMARY MISSION: Maximize keyword density and exact JD terminology match.

=== KEYWORD-FIRST PHILOSOPHY ===

1. **Mirror JD language EXACTLY**:
   - Use THEIR exact words, not synonyms
   - If JD says "cloud infrastructure", write "cloud infrastructure" (not "cloud systems")
   - If JD says "engineering leadership", write "engineering leadership" (not "technical management")

2. **Include BOTH acronym AND full form**:
   - "Amazon Web Services (AWS)" not just "AWS"
   - "Continuous Integration/Continuous Deployment (CI/CD)" not just "CI/CD"
   - "Site Reliability Engineering (SRE)" not just "SRE"
   - Critical: Greenhouse, Lever, Taleo do NOT recognize abbreviations as equivalent

3. **Repeat high-priority keywords 2-3 times naturally**:
   - Once in the headline (if appropriate)
   - Once in the narrative body
   - Once in core competencies
   - This helps with Greenhouse's frequency-based ranking

4. **Front-load keywords in headline and first sentence**:
   - ATS often weight early-appearing terms higher
   - First 50 words are most important for keyword scoring

=== KEYWORD FREQUENCY TARGETS ===

For the TOP 5 JD keywords:
- Each should appear at least 2x across headline + narrative + competencies
- Distribute naturally - don't stuff them unnaturally

=== ANTI-HALLUCINATION RULES ===

CRITICAL - Only use keywords from the GROUNDED list provided.
- These keywords have been pre-verified against the candidate's experience
- Do NOT add keywords not in the grounded list

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "narrative": "3-5 sentence KEYWORD-DENSE profile (100-150 words)",
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

Your mission: Combine the best elements from multiple profile drafts into ONE optimal version.

=== SYNTHESIS RULES ===

1. **METRICS** (from metric-focused draft):
   - Take ALL quantified achievements
   - Preserve exact numbers - do not round or modify
   - Stack metrics where natural

2. **NARRATIVE** (from narrative-focused draft):
   - Use the career arc framing and story structure
   - Preserve transformation language and power verbs
   - Keep the "beginning, middle, end" flow

3. **KEYWORDS** (from keyword-focused draft):
   - Ensure ALL grounded keywords appear at least once
   - Preserve acronym + full form pairs
   - Maintain 2-3x frequency for top keywords

4. **DEDUPLICATION**:
   - Remove redundant statements
   - Keep unique value from each draft
   - Merge similar points into stronger combined statements

5. **FLOW & COHERENCE**:
   - The final version must read naturally as prose
   - NOT a mechanical mashup of disconnected sentences
   - Transitions should be smooth

=== QUALITY CHECKLIST ===

Before finalizing, verify:
□ All metrics from metric draft are included
□ Narrative has compelling career arc
□ All top JD keywords appear 2-3 times
□ Acronyms have full forms
□ 100-150 words total
□ Reads as natural, professional prose

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "narrative": "3-5 sentence SYNTHESIZED profile (100-150 words)",
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
) -> str:
    """
    Build the user prompt for persona-specific profile generation.

    Args:
        persona: One of "metric", "narrative", "keyword"
        candidate_name: Name of the candidate
        job_title: Target job title (EXACT title from JD)
        role_category: One of the 5 role categories
        top_keywords: JD keywords to integrate (pre-grounded)
        experience_bullets: Bullets from stitched experience
        metrics: Extracted quantified metrics
        years_experience: Total years of relevant experience
        regional_variant: "us_eu" or "gulf"
        jd_pain_points: Pain points extracted from JD
        candidate_differentiators: Unique strengths

    Returns:
        Formatted user prompt for specific persona
    """
    bullets_text = "\n".join(f"• {b}" for b in experience_bullets[:20])
    keywords_text = ", ".join(top_keywords[:15]) if top_keywords else "None specified"
    metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "- None extracted"

    # Persona-specific emphasis instructions
    persona_emphasis = {
        "metric": """
PERSONA EMPHASIS: METRICS
Your goal is to MAXIMIZE quantified achievements. Every sentence should contain numbers.
Focus on: dollar amounts, percentages, team sizes, user counts, performance metrics.
""",
        "narrative": """
PERSONA EMPHASIS: NARRATIVE
Your goal is to create a COMPELLING CAREER STORY. Show transformation and progression.
Focus on: career arc, power verbs, strategic impact, professional evolution.
""",
        "keyword": """
PERSONA EMPHASIS: KEYWORDS
Your goal is to MAXIMIZE ATS keyword density. Mirror JD language exactly.
Focus on: exact JD terms, acronym+full form pairs, 2-3x keyword repetition.
""",
    }

    emphasis = persona_emphasis.get(persona, "")

    # Pain points for "What problems can you solve?"
    pain_points_text = ""
    if jd_pain_points:
        pain_points_text = f"""
JD PAIN POINTS (address these):
{chr(10).join(f'- {p}' for p in jd_pain_points[:5])}
"""

    # Differentiators for "Why should they call you?"
    differentiators_text = ""
    if candidate_differentiators:
        differentiators_text = f"""
CANDIDATE DIFFERENTIATORS:
{chr(10).join(f'- {d}' for d in candidate_differentiators[:3])}
"""

    return f"""Write a {persona.upper()}-focused profile for {candidate_name}.
{emphasis}
=== TARGET ROLE ===
EXACT JOB TITLE: {job_title}
ROLE CATEGORY: {role_category}
YEARS OF EXPERIENCE: {years_experience}+
{pain_points_text}{differentiators_text}
=== GROUNDED JD KEYWORDS (ONLY use these) ===
{keywords_text}

=== EXPERIENCE BULLETS (source of truth) ===
{bullets_text}

=== QUANTIFIED METRICS AVAILABLE (use exact values) ===
{metrics_text}

=== REQUIREMENTS ===
1. Headline: "{job_title} | {years_experience}+ Years Technology Leadership"
2. Narrative: 100-150 words with {persona.upper()} emphasis
3. Core Competencies: 6-8 ATS-friendly keywords
4. All content must be grounded in the bullets above

Generate the {persona}-focused profile JSON:"""


def build_synthesis_user_prompt(
    persona_outputs: list,
    job_title: str,
    top_keywords: list,
    years_experience: int = 10,
) -> str:
    """
    Build the user prompt for synthesizing multiple persona outputs.

    Args:
        persona_outputs: List of dicts with persona results
            [{"persona": "metric", "headline": ..., "narrative": ..., ...}, ...]
        job_title: Target job title
        top_keywords: JD keywords that must appear
        years_experience: Total years of relevant experience

    Returns:
        Formatted user prompt for synthesis
    """
    keywords_text = ", ".join(top_keywords[:15]) if top_keywords else "None specified"

    # Format each persona output
    drafts_text = ""
    for output in persona_outputs:
        persona = output.get("persona", "unknown")
        drafts_text += f"""
=== {persona.upper()}-FOCUSED DRAFT ===
Headline: {output.get('headline', '')}
Narrative: {output.get('narrative', '')}
Core Competencies: {', '.join(output.get('core_competencies', []))}
Metrics Used: {', '.join(output.get('highlights_used', []))}
Keywords Used: {', '.join(output.get('keywords_integrated', []))}
"""

    return f"""Synthesize these profile drafts into ONE optimal version.

=== TARGET ===
JOB TITLE: {job_title}
YEARS: {years_experience}+
REQUIRED KEYWORDS: {keywords_text}
{drafts_text}
=== SYNTHESIS TASK ===
Combine the best elements:
1. Take ALL metrics from the metric-focused draft
2. Use the story structure from the narrative-focused draft
3. Ensure ALL keywords from the keyword-focused draft appear
4. Create natural, flowing prose (not a mashup)
5. Target 100-150 words

Generate the synthesized profile JSON:"""


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
