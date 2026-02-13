"""
CV Generation Prompts with Reference Doc Integration.

Integrates key frameworks and best practices from:
- thoughts/prompt-generation-guide.md: Personas, CoT, Few-shot, Constraints
- docs/archive/reports/cv-guide.plan.md: CARS framework, role-level keywords
- docs/archive/reports/prompt-analysis/ats-guide.md: Keyword placement, acronym strategy

These prompts are designed to work with Claude Code CLI agents for multi-tier
CV generation using Sonnet (role bullets), Opus (profile), and Haiku (validation).

Usage:
    from src.layer6_v2.prompts.cv_generation_prompts import (
        ROLE_KEYWORDS,
        FEW_SHOT_BULLETS,
        build_role_bullet_prompt,
        build_profile_prompt,
        build_ats_validation_prompt,
    )
"""

from typing import Any, Dict, List, Optional

# ===== ROLE-LEVEL KEYWORDS (from cv-guide.plan.md) =====

ROLE_KEYWORDS: Dict[str, List[str]] = {
    "engineering_manager": [
        "Agile",
        "Scrum",
        "Kanban",
        "Sprint Planning",
        "Team Leadership",
        "People Management",
        "Performance Reviews",
        "Technical Architecture",
        "Code Review",
        "CI/CD",
        "Cross-functional Collaboration",
        "Stakeholder Management",
        "Hiring",
        "Onboarding",
        "Retention",
        "1:1 Meetings",
        "Career Development",
    ],
    "director": [
        "Organizational Design",
        "Team Scaling",
        "Engineering Strategy",
        "Technical Roadmap",
        "Budget Management",
        "Resource Planning",
        "Process Improvement",
        "Engineering Excellence",
        "Vendor Management",
        "Build vs Buy",
        "Multi-team Leadership",
        "Engineering Culture",
        "OKRs",
        "KPIs",
    ],
    "vp_head": [
        "Engineering Culture",
        "Developer Experience",
        "Technical Vision",
        "Platform Strategy",
        "Executive Communication",
        "Board Reporting",
        "Talent Acquisition",
        "Retention Strategy",
        "Product-Engineering Partnership",
        "Engineering Strategy",
        "Organizational Development",
        "M&A Integration",
        "Due Diligence",
    ],
    "cto": [
        "Technology Strategy",
        "Digital Transformation",
        "Innovation",
        "R&D",
        "Technical Due Diligence",
        "Enterprise Architecture",
        "Cloud Strategy",
        "Security",
        "Compliance",
        "Risk Management",
        "Board Relations",
        "Investor Communications",
        "Technology Investment",
        "P&L Responsibility",
    ],
    "staff_principal": [
        "System Design",
        "Architecture",
        "Scalability",
        "Technical Leadership",
        "Mentorship",
        "Code Quality",
        "Best Practices",
        "Performance Optimization",
        "Reliability",
        "Cross-team Collaboration",
        "Technical Influence",
        "RFC/Design Documents",
        "Architecture Patterns",
        "Distributed Systems",
    ],
}


# ===== FEW-SHOT BULLET EXAMPLES (from cv-guide.plan.md) =====

FEW_SHOT_BULLETS: Dict[str, List[str]] = {
    "engineering_manager": [
        "Led cross-functional team of 12 engineers to deliver customer platform on time, increasing user engagement by 30% and generating $2.4M incremental ARR",
        "Scaled engineering team from 5 to 18 members while maintaining 92% retention; implemented structured onboarding reducing ramp-up time by 40%",
        "Launched 2 applications earning $4.8M combined revenue in Q1; reduced deployment cycle time by 35% through CI/CD pipeline improvements",
    ],
    "director": [
        "Directed engineering organization of 6 teams (45 engineers) across 3 product lines, delivering 15% YoY revenue growth while reducing operational costs by $2M",
        "Restructured engineering department from project-based to product-aligned teams, improving delivery velocity by 40% and reducing cross-team dependencies by 60%",
        "Established engineering excellence program including tech radar, architecture review board, and career ladders; improved engineer satisfaction from 3.2 to 4.5",
    ],
    "vp_head": [
        "Built engineering organization from ground up: hired first 25 engineers, established culture of technical excellence, and delivered MVP securing $15M Series A",
        "Scaled engineering function 5x in 18 months while maintaining delivery velocity; established hiring process yielding 85% offer acceptance rate",
        "Spearheaded technical strategy enabling product expansion to 80+ countries; architected platform supporting 10x traffic growth",
    ],
    "cto": [
        "Drove technology transformation increasing company valuation from $50M to $400M; architected platform supporting 10M+ daily active users with 99.99% uptime",
        "Pioneered AI-driven product strategy generating 35% revenue increase; presented technology roadmap to board securing $25M additional investment",
        "Transformed legacy monolith to cloud-native architecture, reducing infrastructure costs by 40% while enabling expansion to 15 new markets",
    ],
    "staff_principal": [
        "Architected microservices platform handling 50K requests/second with 99.95% availability; reduced infrastructure costs by 35% through optimization",
        "Designed event-driven architecture enabling real-time processing for 10M+ daily events; mentored 8 engineers on distributed systems",
        "Spearheaded migration from monolith to microservices, reducing deployment time from 2 weeks to 2 hours; established architectural decision records adopted org-wide",
    ],
}


# ===== BOARD-FACING LANGUAGE TRANSFORMATIONS (from cv-guide.plan.md) =====

BOARD_LANGUAGE_TRANSFORMS: Dict[str, str] = {
    "Led engineering team": "Drove organizational capability enabling market expansion",
    "Built features": "Delivered product innovations generating revenue growth",
    "Reduced costs": "Unlocked savings through strategic infrastructure consolidation",
    "Improved performance": "Enhanced platform reliability supporting revenue growth",
    "Managed developers": "Built and scaled high-performing engineering organization",
    "Fixed bugs": "Established engineering excellence reducing production incidents",
    "Wrote code": "Architected solutions driving technical strategy",
    "Led project": "Drove cross-functional initiative delivering business outcomes",
}


# ===== ATS KEYWORD PLACEMENT WEIGHTS (from ats-guide.md) =====

KEYWORD_PLACEMENT_WEIGHTS: Dict[str, int] = {
    "professional_summary": 40,
    "skills_section": 30,
    "job_titles": 20,
    "first_bullets": 10,
}


# ===== ACRONYM EXPANSION LIST (from ats-guide.md) =====

ACRONYM_EXPANSIONS: Dict[str, str] = {
    "AWS": "Amazon Web Services (AWS)",
    "GCP": "Google Cloud Platform (GCP)",
    "CI/CD": "Continuous Integration/Continuous Deployment (CI/CD)",
    "ML": "Machine Learning (ML)",
    "AI": "Artificial Intelligence (AI)",
    "SRE": "Site Reliability Engineering (SRE)",
    "K8s": "Kubernetes (K8s)",
    "IaC": "Infrastructure as Code (IaC)",
    "API": "Application Programming Interface (API)",
    "MVP": "Minimum Viable Product (MVP)",
    "OKR": "Objectives and Key Results (OKRs)",
    "PMP": "Project Management Professional (PMP)",
    "MBA": "Master of Business Administration (MBA)",
    "VP": "Vice President (VP)",
    "CTO": "Chief Technology Officer (CTO)",
    "DevOps": "DevOps (Development Operations)",
}


# ===== CARS FRAMEWORK STRUCTURE =====

CARS_FRAMEWORK = """
## CARS Framework (Challenge-Action-Results-Strategic Impact)

Structure each bullet following this narrative arc:

1. **Challenge** (implied): The business/technical problem that existed
2. **Action**: What YOU specifically did - use strong action verbs
3. **Results**: Quantified outcomes with specific metrics
4. **Strategic Impact**: The broader business effect

Example transformation:
- Raw: "Led team to rebuild authentication system"
- CARS: "Architected OAuth2-based authentication platform [ACTION] reducing security incidents by 85% [RESULT], enabling SOC2 certification and $2M enterprise contract [STRATEGIC IMPACT]"
"""


# ===== PROMPT BUILDERS =====


def build_role_bullet_prompt(
    role_title: str,
    role_company: str,
    role_achievements: List[str],
    persona_statement: str,
    core_strengths: List[str],
    pain_points: List[str],
    role_level: str,
    priority_keywords: List[str],
    annotations: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build prompt for role bullet generation with reference doc integration.

    Integrates CARS framework, role-level keywords, and ATS optimization.

    Args:
        role_title: The role title
        role_company: The company name
        role_achievements: Raw achievements/bullets to transform
        persona_statement: Synthesized persona from annotations
        core_strengths: Key strengths from candidate profile
        pain_points: JD pain points to address
        role_level: Target role level (engineering_manager, director, etc.)
        priority_keywords: Must-include keywords from JD
        annotations: Optional annotation data for identity/passion context

    Returns:
        Formatted prompt string
    """
    # Get role-specific keywords
    role_keywords = ROLE_KEYWORDS.get(role_level, ROLE_KEYWORDS["engineering_manager"])

    # Get few-shot examples
    few_shot = FEW_SHOT_BULLETS.get(role_level, FEW_SHOT_BULLETS["engineering_manager"])

    # Format lists
    strengths_text = "\n".join(f"- {s}" for s in core_strengths[:5])
    pain_points_text = "\n".join(f"- {p}" for p in pain_points[:3])
    achievements_text = "\n".join(f"- {a}" for a in role_achievements[:10])
    few_shot_text = "\n".join(f"• {b}" for b in few_shot[:3])

    # Build annotation context if available
    annotation_context = ""
    if annotations:
        identity_keywords = []
        passion_keywords = []
        for ann in annotations[:5]:  # Limit to top 5
            if ann.get("identity") in ["core_identity", "strong_identity"]:
                skill = ann.get("matching_skill", "")
                if skill:
                    identity_keywords.append(skill)
            if ann.get("passion") in ["love_it", "enjoy"]:
                skill = ann.get("matching_skill", "")
                if skill:
                    passion_keywords.append(skill)

        if identity_keywords:
            annotation_context += f"\nIdentity keywords (emphasize): {', '.join(identity_keywords)}"
        if passion_keywords:
            annotation_context += f"\nPassion keywords (weave naturally): {', '.join(passion_keywords)}"

    return f"""You ARE a senior CV writer specializing in technical leadership roles.

## ROLE TO TRANSFORM
Title: {role_title}
Company: {role_company}

## RAW ACHIEVEMENTS TO TRANSFORM
{achievements_text}

## CANDIDATE CONTEXT
Persona: {persona_statement}

Core Strengths:
{strengths_text}

## JD PAIN POINTS (address 1-2 in your bullets)
{pain_points_text}

{CARS_FRAMEWORK}

## ROLE-LEVEL KEYWORDS (integrate naturally)
Target Level: {role_level}
Keywords to use: {', '.join(role_keywords[:10])}

## PRIORITY JD KEYWORDS (must include)
{', '.join(priority_keywords[:10])}
{annotation_context}

## ATS OPTIMIZATION RULES
1. Front-load keywords in first 3 words when possible
2. Include BOTH acronym AND full term on first use (e.g., "Amazon Web Services (AWS)")
3. Repeat key terms 3-5 times naturally across bullets
4. Include specific numbers (ATS reads numbers perfectly)

## FEW-SHOT EXAMPLES (for this role level)
{few_shot_text}

## CONSTRAINTS
- 25-40 words per bullet
- 3-5 bullets total
- Third-person absent voice (no "I", "my")
- Ground ONLY in provided achievements - NO hallucination
- Address at least 1 JD pain point

Return ONLY valid JSON:
{{
  "role_bullets": [
    {{
      "text": "Full bullet text (25-40 words)",
      "keywords_used": ["keyword1", "keyword2"],
      "pain_point_addressed": "Which pain point this addresses"
    }}
  ],
  "keyword_coverage": {{"term": count}}
}}
"""


def build_profile_prompt(
    persona_statement: str,
    primary_identity: str,
    core_strengths: List[str],
    role_bullets_summary: str,
    priority_keywords: List[str],
    pain_points: List[str],
    target_role_level: str,
) -> str:
    """
    Build prompt for profile synthesis with multi-pass technique.

    Uses Tree-of-Thoughts: Metric → Narrative → Keyword passes.

    Args:
        persona_statement: Synthesized persona from annotations
        primary_identity: Core professional archetype
        core_strengths: Key strengths from candidate profile
        role_bullets_summary: Summary of generated role bullets
        priority_keywords: Must-include keywords from JD
        pain_points: JD pain points addressed
        target_role_level: Target role level for language calibration

    Returns:
        Formatted prompt string
    """
    strengths_text = "\n".join(f"- {s}" for s in core_strengths[:5])

    return f"""You ARE the candidate, writing YOUR OWN professional profile.

## YOUR IDENTITY
Persona: {persona_statement}
Primary Identity: {primary_identity}
Target Level: {target_role_level}

## YOUR CORE STRENGTHS
{strengths_text}

## YOUR ACHIEVEMENTS (from role bullets)
{role_bullets_summary}

## PRIORITY KEYWORDS (must appear in profile)
{', '.join(priority_keywords[:10])}

## PAIN POINTS ADDRESSED
{', '.join(pain_points[:5])}

## MULTI-PASS TECHNIQUE (Tree-of-Thoughts)

Generate THREE profile versions, then synthesize:

### Pass 1: Metric Focus
- Lead with largest team size, highest revenue impact
- Every sentence contains a number
- Emphasis on scale

### Pass 2: Narrative Focus
- Career transformation story
- Show progression and growth
- Connect past to future potential

### Pass 3: Keyword Focus
- All must-have JD keywords
- Role-appropriate terminology
- ATS optimization

### Synthesis
Combine best elements from all passes.

## BOARD-FACING LANGUAGE
Transform operational language:
- "Led team" → "Drove organizational capability"
- "Built features" → "Delivered product innovations generating revenue"
- "Reduced costs" → "Unlocked savings through strategic consolidation"

## PROFILE STRUCTURE
1. **Headline**: [Role Level] | [Years] | [Signature Strength]
2. **Tagline**: 2 lines, value proposition
3. **Key Achievements**: 5-6 quantified bullets
4. **Core Competencies**: Skill clusters

## CONSTRAINTS
- 100-150 words total
- Third-person absent voice
- No "I" or "my"
- Ground ONLY in provided achievements

Return ONLY valid JSON:
{{
  "headline": "Single line headline",
  "tagline": "Two line value proposition",
  "key_achievements": ["bullet1", "bullet2", ...],
  "core_competencies": {{
    "leadership": ["skill1", "skill2"],
    "technical": ["skill1", "skill2"],
    "delivery": ["skill1", "skill2"]
  }},
  "reasoning": {{
    "metric_pass_summary": "...",
    "narrative_pass_summary": "...",
    "keyword_pass_summary": "...",
    "synthesis_rationale": "..."
  }}
}}
"""


def build_ats_validation_prompt(
    cv_text: str,
    must_have_keywords: List[str],
    nice_to_have_keywords: List[str],
    target_role_level: str,
) -> str:
    """
    Build prompt for ATS validation with comprehensive checks.

    Args:
        cv_text: Full CV text to validate
        must_have_keywords: Critical keywords that must appear
        nice_to_have_keywords: Preferred keywords
        target_role_level: Target role level for keyword checking

    Returns:
        Formatted prompt string
    """
    role_keywords = ROLE_KEYWORDS.get(target_role_level, ROLE_KEYWORDS["engineering_manager"])

    return f"""You validate CVs against ATS optimization requirements.

## CV TO VALIDATE
{cv_text}

## MUST-HAVE KEYWORDS (must appear 2-5 times each)
{', '.join(must_have_keywords[:15])}

## NICE-TO-HAVE KEYWORDS (should appear 1-4 times each)
{', '.join(nice_to_have_keywords[:10])}

## ROLE-LEVEL KEYWORDS FOR {target_role_level.upper()}
Must include at least 2 of: {', '.join(role_keywords[:8])}

## VALIDATION CHECKS

### 1. Keyword Match Rate
Calculate: (Keywords Found / Required) * 100
Target: 75%+

### 2. Acronym Expansion
Flag terms appearing only as acronyms without expansion.
Examples: AWS should be "Amazon Web Services (AWS)"

### 3. Keyword Placement
Check presence in high-weight locations:
- Professional Summary (40 points)
- Skills Section (30 points)
- Job Titles (20 points)
- First Role Bullets (10 points)

### 4. Red Flags
Detect vague language:
- "responsible for" → suggest action verb
- "helped with" → suggest specific contribution
- "worked on" → suggest role/outcome

### 5. Keyword Density
Optimal: 3-5 mentions per key term
Flag: <2 (too few) or >6 (stuffing)

Return ONLY valid JSON:
{{
  "ats_score": 0-100,
  "missing_keywords": {{
    "critical": ["keyword1"],
    "nice_to_have": ["keyword2"]
  }},
  "acronyms_to_expand": [
    {{"term": "AWS", "expansion": "Amazon Web Services (AWS)"}}
  ],
  "keyword_placement_issues": [
    {{"keyword": "Agile", "issue": "Not in summary", "suggestion": "Add to first line"}}
  ],
  "red_flags": [
    {{"location": "Role 1, Bullet 2", "text": "...", "issue": "Vague", "fix": "..."}}
  ],
  "role_level_check": {{
    "required_found": 3,
    "required_missing": ["keyword"],
    "pass": true
  }},
  "fixes": [
    {{"priority": "high", "location": "...", "original": "...", "suggested": "..."}}
  ],
  "summary": {{
    "overall": "Good/Fair/Poor",
    "top_3_actions": ["action1", "action2", "action3"]
  }}
}}
"""


def get_role_level_from_category(role_category: str) -> str:
    """
    Map role category from extracted_jd to role level for prompts.

    Args:
        role_category: Role category from JD extraction

    Returns:
        Normalized role level key
    """
    category_map = {
        "engineering_manager": "engineering_manager",
        "senior_engineering_manager": "engineering_manager",
        "director_of_engineering": "director",
        "director": "director",
        "vp_engineering": "vp_head",
        "head_of_engineering": "vp_head",
        "vp_head": "vp_head",
        "cto": "cto",
        "chief_technology_officer": "cto",
        "staff_engineer": "staff_principal",
        "principal_engineer": "staff_principal",
        "staff_principal_engineer": "staff_principal",
        "staff_principal": "staff_principal",
        "tech_lead": "engineering_manager",
        "senior_engineer": "staff_principal",
    }
    return category_map.get(role_category.lower(), "engineering_manager")


def expand_acronym(term: str) -> str:
    """
    Expand an acronym to include both forms.

    Args:
        term: Technical term or acronym

    Returns:
        Expanded form if known, otherwise original
    """
    return ACRONYM_EXPANSIONS.get(term.upper(), term)
