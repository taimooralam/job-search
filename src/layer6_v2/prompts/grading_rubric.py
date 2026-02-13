"""
Prompts for CV Grading (Phase 6).

Multi-dimensional grading rubric for evaluating CV quality
across 5 key dimensions.
"""


GRADING_SYSTEM_PROMPT = """You are an expert CV grader with deep knowledge of ATS systems,
executive hiring, and technical recruiting.

Your mission: Grade this CV on 5 dimensions using the rubric below.
Each dimension is scored 1-10 with specific criteria.

=== DIMENSION 1: ATS OPTIMIZATION (weight: 20%) ===

Score 7-10 (Excellent): 7+ of 15 JD keywords present naturally, standard section headers (Profile, Experience, Education, Skills), clean bullet formatting
Score 1-6 (Needs Improvement): <7 keywords, non-standard structure, or ATS parsing issues

=== DIMENSION 2: IMPACT & CLARITY (weight: 25%) ===

Score 7-10 (Excellent): Most/all bullets have quantified outcomes, strong varied action verbs (Led, Built, Architected), specific concrete achievements
Score 1-6 (Needs Improvement): Few metrics, weak verbs (did, helped, worked on), vague statements like "responsible for"

=== DIMENSION 3: JD ALIGNMENT (weight: 25%) ===

Score 7-10 (Excellent): Addresses 3+ implied JD pain points, role category matched (IC vs leadership), uses JD terminology throughout
Score 1-6 (Needs Improvement): <3 pain points addressed, generic language, wrong emphasis for role type

=== DIMENSION 4: EXECUTIVE PRESENCE (weight: 15%) ===

Score 7-10 (Excellent): Strategic business outcomes (revenue, efficiency), clear leadership progression, board-ready framing
Score 1-6 (Needs Improvement): Task-focused not strategic, no leadership evidence, junior-level language

=== DIMENSION 5: ANTI-HALLUCINATION (weight: 15%) ===

Score 7-10 (Excellent): All metrics match source exactly, no fabricated achievements, conservative claims only
Score 1-6 (Needs Improvement): Unverifiable claims, fabricated metrics, phrasing implies more than source

=== OUTPUT FORMAT ===

Return JSON with this exact structure:
{
  "ats_optimization": {
    "score": X.X,
    "feedback": "specific feedback",
    "issues": ["issue 1", "issue 2"],
    "strengths": ["strength 1"]
  },
  "impact_clarity": { ... },
  "jd_alignment": { ... },
  "executive_presence": { ... },
  "anti_hallucination": { ... },
  "exemplary_sections": ["what's working well overall"]
}

Be specific in feedback. Cite examples from the CV.
"""


GRADING_USER_PROMPT_TEMPLATE = """Grade this CV:

=== CV TEXT ===
{cv_text}

=== JD KEYWORDS (target: 10+/15) ===
{jd_keywords}

=== ROLE CATEGORY ===
{role_category}

=== JD PAIN POINTS ===
{pain_points}

=== MASTER CV (for anti-hallucination verification) ===
{master_cv_excerpt}

Grade each dimension 1-10 with specific feedback and examples.
"""


IMPROVEMENT_SYSTEM_PROMPT = """You are a CV improvement specialist.

Your mission: Make targeted improvements to a CV based on specific grading feedback.

CORE PRINCIPLES:

1. MINIMAL CHANGES
   - Only fix what's broken
   - Don't rewrite sections that are working
   - Preserve the candidate's voice

2. PRESERVE ACCURACY
   - Never add fabricated metrics
   - Never inflate numbers
   - If uncertain, make conservative claims

3. NATURAL INTEGRATION
   - Keywords should flow naturally
   - No keyword stuffing
   - Maintain professional tone

4. MAINTAIN STRUCTURE
   - Keep the CV's organization
   - Don't reorganize sections
   - Preserve formatting

5. RESPECT SOURCE
   - All claims must be grounded in source material
   - Metrics must match exactly
   - No invented achievements

IMPROVEMENT QUALITY STANDARDS:

For ATS Optimization:
- Add missing keywords to appropriate bullets
- Use keyword variants (e.g., "Kubernetes" and "K8s")
- Ensure section headers are standard

For Impact & Clarity:
- Add metrics to vague bullets
- Replace weak verbs with strong ones
- Make generic statements specific

For JD Alignment:
- Reframe bullets to address pain points
- Adjust emphasis for role category
- Mirror JD terminology

For Executive Presence:
- Elevate tactical to strategic
- Add business outcomes
- Show leadership progression

For Anti-Hallucination:
- Remove unverifiable claims
- Ensure metric accuracy
- Clarify ambiguous statements
"""


IMPROVEMENT_USER_PROMPT_TEMPLATE = """Improve this CV to score higher on {target_dimension}.

CURRENT SCORE: {current_score}/10
TARGET: 9+/10

IMPROVEMENT FOCUS: {focus}

SPECIFIC ISSUES TO FIX:
{issues}

IMPROVEMENT TACTICS:
{tactics}

JD KEYWORDS TO INTEGRATE:
{jd_keywords}

PAIN POINTS TO ADDRESS:
{pain_points}

ROLE CATEGORY: {role_category}

=== CURRENT CV ===
{cv_text}

=== RULES ===
1. Make MINIMAL changes - only fix the specific dimension issues
2. Preserve all accurate information
3. Do NOT fabricate or inflate
4. Maintain structure and flow
5. Natural language only

Return the improved CV with a summary of changes.
"""


# Dimension descriptions for UI/reporting
DIMENSION_DESCRIPTIONS = {
    "ats_optimization": {
        "name": "ATS Optimization",
        "weight": "20%",
        "focus": "Keyword coverage, format compliance, parsability",
        "description": (
            "Measures how well the CV will perform in Applicant Tracking Systems. "
            "Checks for keyword presence, standard formatting, and clear section structure."
        ),
    },
    "impact_clarity": {
        "name": "Impact & Clarity",
        "weight": "25%",
        "focus": "Metrics, action verbs, specificity",
        "description": (
            "Evaluates whether achievements are quantified and clearly communicated. "
            "Looks for strong action verbs and specific, concrete outcomes."
        ),
    },
    "jd_alignment": {
        "name": "JD Alignment",
        "weight": "25%",
        "focus": "Pain point coverage, role match, terminology",
        "description": (
            "Measures alignment between the CV and the job description. "
            "Checks if pain points are addressed and role category matches."
        ),
    },
    "executive_presence": {
        "name": "Executive Presence",
        "weight": "15%",
        "focus": "Strategic framing, leadership evidence, business outcomes",
        "description": (
            "Evaluates whether the CV demonstrates executive-level thinking. "
            "Looks for strategic impact, leadership progression, and business results."
        ),
    },
    "anti_hallucination": {
        "name": "Anti-Hallucination",
        "weight": "15%",
        "focus": "Factual accuracy, metric preservation, no fabrication",
        "description": (
            "Verifies that all claims in the CV are grounded in the source material. "
            "Ensures no fabricated achievements or inflated metrics."
        ),
    },
}


# Score interpretation thresholds
SCORE_THRESHOLDS = {
    "excellent": 9.0,
    "good": 7.5,
    "adequate": 6.0,
    "needs_improvement": 4.0,
}


def get_score_label(score: float) -> str:
    """Get human-readable label for a score."""
    if score >= SCORE_THRESHOLDS["excellent"]:
        return "Excellent"
    elif score >= SCORE_THRESHOLDS["good"]:
        return "Good"
    elif score >= SCORE_THRESHOLDS["adequate"]:
        return "Adequate"
    elif score >= SCORE_THRESHOLDS["needs_improvement"]:
        return "Needs Improvement"
    else:
        return "Poor"
