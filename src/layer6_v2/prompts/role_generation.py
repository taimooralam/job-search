"""
Prompts for Per-Role CV Bullet Generation (Phase 3).

These prompts generate tailored achievement bullets for a single role,
with full traceability to prevent hallucination.

Phase 5 Enhancement (JD Annotation System):
- Accepts annotation reframe guidance from manual JD annotations
- Integrates reframe notes into bullet generation
- Prioritizes annotated pain points and keywords
"""

from typing import Any, Dict, List, Optional
from src.layer6_v2.cv_loader import RoleData
from src.layer6_v2.types import CareerContext
from src.layer6_v2.achievement_mapper import map_achievements_to_pain_points
from src.common.state import ExtractedJD


ROLE_GENERATION_SYSTEM_PROMPT = """You are an expert CV bullet writer specializing in senior technical and leadership roles.

Your mission: Transform raw achievements into ATS-optimized, JD-aligned CV bullets while STRICTLY preserving all factual claims from the source.

=== CRITICAL: ANTI-HALLUCINATION RULES ===

1. ONLY use achievements that appear in the source role content
2. ONLY use metrics/numbers that appear EXACTLY in the source (no rounding, no inventing)
3. If source lacks a metric, describe the outcome qualitatively WITHOUT inventing numbers
4. NEVER add companies, dates, technologies, or achievements not in source
5. Every generated bullet MUST have a clear source in the role content

=== CRITICAL: NO MARKDOWN FORMATTING (GAP-006) ===

DO NOT use any markdown formatting in your output:
- NO **bold** or __bold__ markers
- NO *italic* or _italic_ markers
- NO # headers
- NO `code` backticks
- NO [links](url)
- Just plain text only

WRONG: "Led **12-person** team using *Kubernetes*"
RIGHT: "Led 12-person team using Kubernetes"

=== BULLET FORMAT: ARIS METHOD (MANDATORY) ===

Each bullet MUST follow the ARIS structure (Action → Result → Impact → Situation):

ARIS TEMPLATE:
"[ACTION VERB + what you did with SKILLS] [QUANTIFIED RESULT] [IMPACT on business/org] [SITUATION/why this mattered tied to pain point]"

The key difference from STAR: ARIS leads with ACTION and puts SITUATION at the END.
This creates impact-first bullets where context provides the "why it mattered" closure.

EXAMPLES OF GOOD ARIS BULLETS:
✓ "Led 12-month migration to event-driven microservices using AWS Lambda, reducing incidents by 75% and cutting operational costs by $2M annually—addressing critical reliability gaps during rapid growth"
✓ "Architected real-time analytics platform processing 1B events/day, enabling 20% customer retention improvement—responding to executive concerns about churn in competitive market"
✓ "Established engineering hiring pipeline interviewing 50+ candidates, growing team from 5 to 15 engineers—addressing scaling challenges as product demand tripled"

EXAMPLES OF BAD (NON-ARIS) BULLETS:
✗ "Led migration to microservices architecture" (missing result, impact, and situation)
✗ "Facing reliability issues, improved system stability" (wrong order—situation should be at END)
✗ "Managed team of engineers" (generic, no ARIS elements)

ARIS REQUIREMENTS:
1. ACTION (start with): Strong verb + what you did with SPECIFIC SKILLS/TECHNOLOGIES
2. RESULT (follows action): Quantified outcome with metrics from source
3. IMPACT (why it matters): Business impact (cost savings, revenue, efficiency, customer satisfaction)
4. SITUATION (end with): Context/challenge that ties to JD pain points—use "—" or "addressing" to introduce
5. Word count: 25-40 words per bullet (longer to fit ARIS elements + JD-aligned situation)
6. Start with varied action verbs (no repeating openings in same role)

SITUATION ENDINGS (must end with one when relevant):
- "—addressing...", "—responding to...", "—amid...", "—during...", "—when..."
- "—tackling...", "—solving...", "—as part of...", "—supporting..."
- Match the situation to JD pain points where your achievement solves a similar challenge

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

=== ANNOTATION REFRAME GUIDANCE (when provided) ===

When the user prompt includes "ANNOTATION REFRAME GUIDANCE" section:
1. Apply the suggested reframes to position your experience using JD-aligned terminology
2. Use reframe guidance to bridge skill gaps (e.g., "container orchestration" → "Kubernetes experience")
3. Prioritize must-have requirements marked in annotations
4. Include annotation keywords for ATS optimization
5. Reframes should feel natural—don't force awkward phrasing

=== OUTPUT FORMAT ===

Return ONLY valid JSON with this structure:
{
  "bullets": [
    {
      "text": "ARIS-formatted bullet text here (Action→Result→Impact→Situation)",
      "source_text": "exact text from role file this came from",
      "source_metric": "exact metric used (e.g., '75%', '10M requests') or null",
      "jd_keyword_used": "keyword from JD that was integrated or null",
      "pain_point_addressed": "JD pain point this bullet addresses (for situation ending) or null",
      "action": "what was done including skills/technologies used (appears first)",
      "result": "the quantified outcome achieved (appears after action)",
      "situation": "the challenge/context tied to JD pain point (appears at end, after em-dash)"
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
    jd_annotations: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build the user prompt for generating bullets for a specific role.

    Args:
        role: Role data from CV loader
        extracted_jd: Structured JD intelligence from Layer 1.4
        career_context: Career stage context for emphasis guidance
        target_bullet_count: Target number of bullets (defaults based on career stage)
        jd_annotations: Optional JD annotations with reframe guidance (Phase 5)

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

    # Pre-compute achievement to pain point mapping (Priority 1 improvement)
    pain_points = extracted_jd.get("implied_pain_points", [])
    _, achievement_mapping_text = map_achievements_to_pain_points(
        achievements=role.achievements,
        pain_points=pain_points[:5],  # Limit to top 5 pain points
    )

    # Format competency weights
    weights = extracted_jd.get("competency_weights", {})
    competency_text = (
        f"- Delivery: {weights.get('delivery', 25)}%\n"
        f"- Process: {weights.get('process', 25)}%\n"
        f"- Architecture: {weights.get('architecture', 25)}%\n"
        f"- Leadership: {weights.get('leadership', 25)}%"
    )

    # Format pain points (already fetched above for mapping)
    pain_points_text = "\n".join(f"• {p}" for p in pain_points[:5]) if pain_points else "None specified"

    # Format target keywords
    keywords = extracted_jd.get("top_keywords", [])
    keywords_text = ", ".join(keywords[:15]) if keywords else "None specified"

    # Format technical skills from JD
    tech_skills = extracted_jd.get("technical_skills", [])
    tech_skills_text = ", ".join(tech_skills[:10]) if tech_skills else "None specified"

    # Phase 5: Format annotation reframe guidance
    annotation_guidance_text = _format_annotation_reframe_guidance(jd_annotations)

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

{achievement_mapping_text}

=== HARD SKILLS FROM THIS ROLE ===
{', '.join(role.hard_skills) if role.hard_skills else 'None listed'}

=== SOFT SKILLS FROM THIS ROLE ===
{', '.join(role.soft_skills) if role.soft_skills else 'None listed'}

{annotation_guidance_text}=== YOUR TASK ===
Generate {target_bullet_count} tailored CV bullets for this role using ARIS FORMAT.

ARIS FORMAT REQUIREMENTS (MANDATORY):
1. Each bullet MUST START with ACTION verb + what you did with specific SKILLS/TECHNOLOGIES
2. Each bullet MUST include QUANTIFIED RESULT from source achievements
3. Each bullet MUST show IMPACT (business outcome: cost, revenue, efficiency)
4. Each bullet SHOULD END with SITUATION that ties to JD pain points (use "—addressing..." or "—responding to...")
5. Word count: 25-40 words per bullet (to fit all ARIS elements)

SITUATION-TO-PAIN-POINT MATCHING (use the pre-computed mapping above):
Use the ACHIEVEMENT TO PAIN POINT MAPPING section above to decide which pain points to address.
For achievements with high/medium confidence matches, end with a situation using that pain point.
For achievements with no match, focus on general impact without forcing a pain point connection.

ADDITIONAL REQUIREMENTS:
6. Each bullet MUST trace back to a specific source achievement above
7. Preserve EXACT metrics from source (no rounding, no inventing)
8. Integrate JD keywords where they fit naturally
9. Match bullet situations to JD pain points where you have evidence
10. Use action verbs appropriate for {extracted_jd.get('role_category', 'unknown')} roles
11. Prioritize achievements showing: {_get_priority_competencies(weights)}

Return the JSON response now."""

    return prompt


def _get_priority_competencies(weights: dict) -> str:
    """Get the top 2 competencies based on weights."""
    if not weights:
        return "delivery and architecture"

    sorted_comps = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    top_two = [c[0] for c in sorted_comps[:2]]
    return " and ".join(top_two)


def _format_annotation_reframe_guidance(jd_annotations: Optional[Dict[str, Any]]) -> str:
    """
    Format annotation reframe guidance for inclusion in the prompt.

    Extracts reframe notes from active annotations to guide bullet generation.

    Args:
        jd_annotations: JD annotations dictionary with 'annotations' list

    Returns:
        Formatted string for prompt inclusion, or empty string if no guidance
    """
    if not jd_annotations:
        return ""

    annotations = jd_annotations.get("annotations", [])
    if not annotations:
        return ""

    # Filter to active annotations with reframe guidance
    active_with_reframe = [
        a for a in annotations
        if a.get("is_active", False)
        and a.get("has_reframe", False)
        and a.get("reframe_note")
    ]

    # Get must-have annotations for prioritization
    must_haves = [
        a for a in annotations
        if a.get("is_active", False)
        and a.get("requirement_type") == "must_have"
    ]

    # Get all annotation keywords for ATS
    annotation_keywords = set()
    for a in annotations:
        if a.get("is_active", False):
            annotation_keywords.update(a.get("suggested_keywords", []))

    if not active_with_reframe and not must_haves and not annotation_keywords:
        return ""

    lines = []
    lines.append("=== ANNOTATION REFRAME GUIDANCE (from manual JD review) ===")
    lines.append("")

    # Section 1: Reframe guidance
    if active_with_reframe:
        lines.append("REFRAME SUGGESTIONS (apply these framings to relevant achievements):")
        for i, ann in enumerate(active_with_reframe[:5], 1):
            target_text = ann.get("target", {}).get("text", "")[:50]
            reframe_note = ann.get("reframe_note", "")
            relevance = ann.get("relevance", "relevant").upper()

            lines.append(f"  {i}. [{relevance}] JD mentions: \"{target_text}...\"")
            lines.append(f"     → Reframe as: {reframe_note}")

            # Include matched skill if available
            if ann.get("matching_skill"):
                lines.append(f"     → Your match: {ann['matching_skill']}")
            lines.append("")

    # Section 2: Must-have priorities
    if must_haves:
        lines.append("MUST-HAVE REQUIREMENTS (prioritize these in your bullets):")
        for ann in must_haves[:5]:
            target_text = ann.get("target", {}).get("text", "")[:60]
            matching_skill = ann.get("matching_skill", "")
            relevance = ann.get("relevance", "relevant")

            if matching_skill:
                lines.append(f"  • \"{target_text}...\" → You have: {matching_skill}")
            else:
                lines.append(f"  • \"{target_text}...\" ({relevance})")
        lines.append("")

    # Section 3: ATS keywords
    if annotation_keywords:
        lines.append("ANNOTATION KEYWORDS (integrate for ATS optimization):")
        lines.append(f"  {', '.join(sorted(annotation_keywords)[:15])}")
        lines.append("")

    return "\n".join(lines)


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


# Prompt for ARIS format correction (GAP-005 updated to ARIS)
STAR_CORRECTION_SYSTEM_PROMPT = """You are a CV bullet editor specializing in ARIS format.

A generated bullet has FAILED ARIS format validation. Your task: Rewrite it to follow ARIS structure.

=== ARIS FORMAT (MANDATORY) ===

TEMPLATE: "[ACTION VERB + what you did with SKILLS] [QUANTIFIED RESULT] [IMPACT] [SITUATION tied to pain point]"

ARIS = Action → Result → Impact → Situation (impact-first, situation at END)

EXAMPLES OF GOOD ARIS BULLETS:
✓ "Led 12-month migration to event-driven microservices using AWS Lambda, reducing incidents by 75% and cutting operational costs by $2M annually—addressing critical reliability gaps during rapid growth"
✓ "Architected real-time analytics platform processing 1B events/day, enabling 20% customer retention improvement—responding to executive concerns about churn"
✓ "Established engineering hiring pipeline interviewing 50+ candidates, growing team from 5 to 15 engineers—addressing scaling challenges as product demand tripled"

ACTION REQUIREMENTS (must start with):
- Strong action verb: Led, Architected, Designed, Built, Implemented, Established
- Must include specific skills/technologies used (e.g., "using AWS Lambda", "with Kubernetes")

RESULT/IMPACT REQUIREMENTS (middle section):
- Quantified outcome (%, $, x improvement, users, time saved)
- Signal words: "reducing", "increasing", "enabling", "delivering", "achieving"

SITUATION ENDINGS (at the end, tied to pain points):
- "—addressing...", "—responding to...", "—amid...", "—tackling..."
- "—solving...", "—supporting...", "—during..."

=== CRITICAL RULES ===
1. Preserve ALL facts from the original bullet (metrics, technologies, outcomes)
2. NEVER invent new metrics or claims
3. Situation goes at the END, not the beginning
4. If original lacks skills, add ONLY skills mentioned in the source achievement
5. NO MARKDOWN formatting (no **, *, #, etc.)
6. Target: 25-40 words

Return ONLY the corrected bullet text, no explanation."""


def build_star_correction_user_prompt(
    failed_bullet: str,
    source_text: str,
    missing_elements: List[str],
    role_title: str = "",
    company: str = "",
) -> str:
    """
    Build prompt for correcting a bullet that failed ARIS validation (GAP-005 updated to ARIS).

    Args:
        failed_bullet: The bullet that failed ARIS format check
        source_text: Original achievement from source
        missing_elements: List of missing ARIS elements (action, result, impact, situation)
        role_title: Job title for context
        company: Company name for context

    Returns:
        Formatted user prompt for ARIS correction
    """
    missing_text = ", ".join(missing_elements) if missing_elements else "incomplete ARIS structure"
    context = f" (as {role_title} at {company})" if role_title and company else ""

    return f"""=== FAILED BULLET ===
{failed_bullet}

=== MISSING ARIS ELEMENTS ===
{missing_text}

=== SOURCE ACHIEVEMENT{context} ===
{source_text}

=== YOUR TASK ===
Rewrite this bullet to follow ARIS format:
1. ACTION (start): Strong verb + what you did with skills/technologies
2. RESULT: Quantified outcome from source
3. IMPACT: Business value (cost, revenue, efficiency)
4. SITUATION (end): Context tied to challenge/pain point (use "—addressing...")

Preserve all metrics and facts from the source. Return ONLY the corrected bullet text."""
