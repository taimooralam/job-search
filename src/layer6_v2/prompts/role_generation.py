"""
Prompts for Per-Role CV Bullet Generation (Phase 3).

These prompts generate tailored achievement bullets for a single role,
with full traceability to prevent hallucination.
"""

from typing import List, Optional
from src.layer6_v2.cv_loader import RoleData
from src.layer6_v2.types import CareerContext
from src.common.state import ExtractedJD


ROLE_GENERATION_SYSTEM_PROMPT = """You are an expert CV bullet writer specializing in senior technical and leadership roles.

Your mission: Transform raw achievements into ATS-optimized, JD-aligned CV bullets while STRICTLY preserving all factual claims from the source.

=== CRITICAL: ANTI-HALLUCINATION RULES ===

1. ONLY use achievements that appear in the source role content
2. ONLY use metrics/numbers that appear EXACTLY in the source (no rounding, no inventing)
3. If source lacks a metric, describe the outcome qualitatively WITHOUT inventing numbers
4. NEVER add companies, dates, technologies, or achievements not in source
5. Every generated bullet MUST have a clear source in the role content

=== BULLET FORMAT ===

Each bullet must follow this structure:
- {Strong action verb} {what you did}, {achieving/resulting in} {quantified outcome}
- Word count: 15-25 words per bullet
- Start with varied action verbs (no repeating verbs in same role)

=== ACTION VERB SELECTION ===

Match verb style to role category:

IC Roles (staff_principal_engineer):
- Technical: Architected, Designed, Engineered, Built, Optimized, Implemented
- Impact: Reduced, Improved, Accelerated, Streamlined, Automated

Leadership Roles (engineering_manager, director_of_engineering):
- People: Led, Mentored, Coached, Developed, Grew, Built (teams)
- Strategy: Drove, Established, Transformed, Scaled, Aligned

Executive Roles (head_of_engineering, cto):
- Vision: Spearheaded, Championed, Pioneered, Launched, Founded
- Business: Delivered, Generated, Secured, Achieved (business outcomes)

=== JD ALIGNMENT RULES ===

1. Prioritize achievements that address JD pain points
2. Integrate JD keywords NATURALLY (not forced)
3. Mirror JD terminology where it fits
4. Emphasize competencies matching JD weights (delivery, process, architecture, leadership)

=== OUTPUT FORMAT ===

Return ONLY valid JSON with this structure:
{
  "bullets": [
    {
      "text": "bullet text here",
      "source_text": "exact text from role file this came from",
      "source_metric": "exact metric used (e.g., '75%', '10M requests') or null",
      "jd_keyword_used": "keyword from JD that was integrated or null",
      "pain_point_addressed": "pain point addressed or null"
    }
  ],
  "total_word_count": 150,
  "keywords_integrated": ["keyword1", "keyword2"]
}

IMPORTANT: Return ONLY the JSON. No markdown, no preamble, no explanation."""


def build_role_generation_user_prompt(
    role: RoleData,
    extracted_jd: ExtractedJD,
    career_context: CareerContext,
    target_bullet_count: Optional[int] = None,
) -> str:
    """
    Build the user prompt for generating bullets for a specific role.

    Args:
        role: Role data from CV loader
        extracted_jd: Structured JD intelligence from Layer 1.4
        career_context: Career stage context for emphasis guidance
        target_bullet_count: Target number of bullets (defaults based on career stage)

    Returns:
        Formatted user prompt string
    """
    # Determine target bullet count based on career stage if not specified
    if target_bullet_count is None:
        if career_context.career_stage == "recent":
            target_bullet_count = 6  # Current role gets most detail
        elif career_context.career_stage == "mid-career":
            target_bullet_count = 4  # Mid-career roles get moderate detail
        else:
            target_bullet_count = 2  # Early career roles get brief treatment

    # Format achievements for the prompt
    achievements_text = "\n".join(f"• {a}" for a in role.achievements)

    # Format competency weights
    weights = extracted_jd.get("competency_weights", {})
    competency_text = (
        f"- Delivery: {weights.get('delivery', 25)}%\n"
        f"- Process: {weights.get('process', 25)}%\n"
        f"- Architecture: {weights.get('architecture', 25)}%\n"
        f"- Leadership: {weights.get('leadership', 25)}%"
    )

    # Format pain points
    pain_points = extracted_jd.get("implied_pain_points", [])
    pain_points_text = "\n".join(f"• {p}" for p in pain_points[:5]) if pain_points else "None specified"

    # Format target keywords
    keywords = extracted_jd.get("top_keywords", [])
    keywords_text = ", ".join(keywords[:15]) if keywords else "None specified"

    # Format technical skills from JD
    tech_skills = extracted_jd.get("technical_skills", [])
    tech_skills_text = ", ".join(tech_skills[:10]) if tech_skills else "None specified"

    # Build the prompt
    prompt = f"""=== TARGET JOB ===
Title: {extracted_jd.get('title', 'Unknown')}
Company: {extracted_jd.get('company', 'Unknown')}
Role Category: {extracted_jd.get('role_category', 'unknown')}
Seniority: {extracted_jd.get('seniority_level', 'senior')}

=== COMPETENCY WEIGHTS (emphasize accordingly) ===
{competency_text}

=== JD PAIN POINTS (address if you have matching achievements) ===
{pain_points_text}

=== TARGET ATS KEYWORDS (integrate naturally) ===
{keywords_text}

=== TECHNICAL SKILLS FROM JD ===
{tech_skills_text}

=== ROLE TO PROCESS ===
Company: {role.company}
Title: {role.title}
Period: {role.period}
Industry: {role.industry}
Is Current Role: {role.is_current}

=== CAREER CONTEXT ===
Position: Role {career_context.role_index + 1} of {career_context.total_roles}
Career Stage: {career_context.career_stage}

EMPHASIS GUIDANCE:
{career_context.emphasis_guidance}

=== SOURCE ACHIEVEMENTS (your ONLY source of truth) ===
{achievements_text}

=== HARD SKILLS FROM THIS ROLE ===
{', '.join(role.hard_skills) if role.hard_skills else 'None listed'}

=== SOFT SKILLS FROM THIS ROLE ===
{', '.join(role.soft_skills) if role.soft_skills else 'None listed'}

=== YOUR TASK ===
Generate {target_bullet_count} tailored CV bullets for this role.

Requirements:
1. Each bullet MUST trace back to a specific source achievement above
2. Preserve EXACT metrics from source (no rounding, no inventing)
3. Integrate JD keywords where they fit naturally
4. Address JD pain points where you have matching evidence
5. Use action verbs appropriate for {extracted_jd.get('role_category', 'unknown')} roles
6. Prioritize achievements showing: {_get_priority_competencies(weights)}

Return the JSON response now."""

    return prompt


def _get_priority_competencies(weights: dict) -> str:
    """Get the top 2 competencies based on weights."""
    if not weights:
        return "delivery and architecture"

    sorted_comps = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    top_two = [c[0] for c in sorted_comps[:2]]
    return " and ".join(top_two)


# Prompt for bullet correction after QA failure
BULLET_CORRECTION_SYSTEM_PROMPT = """You are a CV bullet editor correcting hallucination issues.

You have been given:
1. A generated bullet that FAILED hallucination QA
2. The original source achievement
3. The specific issue identified

Your task: Rewrite the bullet to fix the issue while maintaining JD alignment.

RULES:
- ONLY use facts from the source achievement
- NEVER invent metrics, technologies, or outcomes
- Preserve the JD keyword integration if possible
- Keep the same general structure and impact

Return ONLY the corrected bullet text, nothing else."""


def build_correction_user_prompt(
    failed_bullet: str,
    source_text: str,
    issue: str,
    jd_keyword: Optional[str] = None,
) -> str:
    """
    Build prompt for correcting a bullet that failed QA.

    Args:
        failed_bullet: The bullet that failed hallucination check
        source_text: Original source achievement
        issue: Specific issue identified (e.g., "Metric '95%' not found in source")
        jd_keyword: JD keyword to try to preserve (optional)

    Returns:
        Formatted user prompt for correction
    """
    keyword_text = f"\nTry to preserve this JD keyword if possible: {jd_keyword}" if jd_keyword else ""

    return f"""=== FAILED BULLET ===
{failed_bullet}

=== SOURCE ACHIEVEMENT ===
{source_text}

=== ISSUE TO FIX ===
{issue}
{keyword_text}

Rewrite this bullet to fix the issue. Return ONLY the corrected bullet text."""
