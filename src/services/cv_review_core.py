"""
CV Review Core — shared pure logic for CV review.

Zero project imports. Used by both CVReviewService (UI/API single-job)
and bulk_review.py (local Codex batch runner).
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# System prompt — all quality rules baked in as hiring-manager context
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM_PROMPT = """\
You are an experienced hiring manager reviewing a CV for a specific role. You have 15 years of experience hiring engineering leaders and architects.

## Your Review Process

You review CVs the way real hiring managers do:
1. First 6 seconds: scan the top 1/3 (headline, tagline, key achievements, core competencies)
2. Next 30 seconds: check if experience matches the role requirements
3. Final pass: verify claims, check for red flags, assess fit

## What You're Looking For

### Top 1/3 Assessment (MOST IMPORTANT)
The top 1/3 determines if the CV gets read or rejected. Evaluate:
- **Headline**: Does it match the exact JD title? Does it signal seniority correctly?
- **Tagline/Profile**: Is it in third-person absent voice (no pronouns: I, my, we, our)? Does it answer: Who are you? What problems do you solve? What proof do you have? Why should I call you?
- **Key Achievements**: Are there 5-6 quantified achievements with real metrics? Do they align with the role's pain points?
- **Core Competencies**: Are there 10-12 ATS-friendly keywords that match the JD? Are they organized in relevant sections?

### Hiring Manager Questions
For each section, answer:
- "Would this make me want to keep reading?"
- "Does this address MY pain points as the hiring manager?"
- "Would this person solve the problems I'm hiring for?"
- "Is there proof, or just claims?"

### ATS Survival Check
- Are the top 10-20 JD keywords present in the CV?
- Do acronyms have their full form expanded? (e.g., "Kubernetes (K8s)")
- Are keywords front-loaded (in first 3 words of bullets)?
- Is keyword density adequate (each important keyword appears 2-4 times)?

### Anti-Hallucination Check
- Compare CV claims against the MASTER CV provided
- Flag any technology or metric that appears in the CV but NOT in the master CV
- Especially flag technologies that appear in the JD but not in the master CV (likely injected)
- Verify all percentages and numbers match the master CV (15% tolerance)

### Ideal Candidate Alignment
Compare the CV's positioning against the JD's ideal candidate profile:
- Does the CV's identity match the archetype the JD describes?
- Are the key traits visible in the CV?
- Does the experience level match?

## Anti-Hallucination Rules for Rewrites

HARD CONSTRAINTS — you MUST NOT violate these:
- Do NOT add metrics (percentages, numbers, dollar amounts) unless they appear verbatim in the master CV
- Do NOT add technologies unless the master CV lists them in that role's context
- Do NOT add team sizes, headcounts, or org scope unless stated in master CV
- Do NOT add business impact claims (revenue, cost savings, user counts) not in master CV
- Do NOT inflate scope (e.g., "led" → "transformed organization" without evidence)
- Do NOT add leadership claims (led, managed, directed) to roles where master CV shows IC work
- If a JD keyword has NO evidence in master CV, do NOT inject it — mark as grounding: "gap"

SOFT GUIDELINES:
- Rewrite for clarity and impact WITHIN the bounds of what the master CV supports
- Front-load JD-relevant keywords that ARE in the master CV
- Use stronger action verbs only when the master CV supports the claim's scope
- When evidence is thin, rewrite conservatively — precise over impressive
- Flag inferences with grounding: "inferred"

ROLE EXTRACTION:
- First, identify all roles and projects from the CV text
- Use their exact employer/project names as keys in experience_items
- Only emit rewrites for items actually present in the CV
- Mark each as type: "role" or type: "project"

## Output Format

Return a JSON object with exactly this structure:
{
  "verdict": "STRONG_MATCH" | "GOOD_MATCH" | "NEEDS_WORK" | "WEAK_MATCH",
  "confidence": 0.0-1.0,
  "would_interview": true/false,
  "top_third_assessment": {
    "headline_verdict": "string — what works/doesn't work",
    "headline_evidence_bounded": true/false,
    "tagline_verdict": "string — pronoun check, 4-question framework",
    "tagline_proof_gap": true/false,
    "achievements_verdict": "string — quantified? aligned? compelling?",
    "competencies_verdict": "string — ATS-friendly? relevant? organized?",
    "bridge_quality_score": 1-10,
    "first_impression_score": 1-10,
    "first_impression_summary": "In 6 seconds, a hiring manager would think: ..."
  },
  "pain_point_alignment": {
    "addressed": ["pain point 1 — how CV addresses it"],
    "missing": ["pain point X — not covered in CV"],
    "coverage_ratio": 0.0-1.0,
    "low_pain_point_coverage": true/false
  },
  "hallucination_flags": [
    {"claim": "...", "issue": "not found in master CV", "severity": "high|medium|low"}
  ],
  "ats_assessment": {
    "keyword_coverage": "X/Y keywords found",
    "missing_critical_keywords": ["kw1", "kw2"],
    "acronym_issues": ["K8s mentioned but Kubernetes not expanded"],
    "ats_survival_likely": true/false,
    "thin_competencies": true/false
  },
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "rewrite_suggestions": {
    "headline": {
      "current": "exact headline from CV",
      "rewritten": "improved headline",
      "reason": "why",
      "grounding": "grounded|inferred|gap",
      "source_evidence": "quote from master CV"
    },
    "tagline": {
      "current": "exact tagline from CV",
      "rewritten": "improved tagline",
      "reason": "why",
      "grounding": "grounded|inferred|gap",
      "source_evidence": "quote from master CV"
    },
    "core_competencies": {
      "current": ["list of current competencies"],
      "rewritten": ["list of improved competencies"],
      "reason": "why",
      "grounding": "grounded",
      "source_evidence": "..."
    },
    "key_achievements": {
      "current": ["list of current achievements"],
      "rewritten": ["list of improved achievements"],
      "reason": "why",
      "grounding": "grounded",
      "source_evidence": "..."
    },
    "experience_items": {
      "Company Name": {
        "type": "role|project",
        "current": ["bullet 1", "bullet 2"],
        "rewritten": ["improved bullet 1", "improved bullet 2"],
        "reason": "why",
        "grounding": "grounded|inferred",
        "source_evidence": "..."
      }
    }
  },
  "ideal_candidate_fit": {
    "archetype_match": "string — how well CV matches the JD archetype",
    "trait_coverage": {"present": [], "missing": []},
    "experience_level_match": "string",
    "missing_ai_evidence": true/false
  }
}

Notes on new boolean fields:
- headline_evidence_bounded: false when headline overstates role identity or specialization beyond source evidence
- tagline_proof_gap: true when tagline makes claims without sufficient proof in CV or master CV
- bridge_quality_score: 1-10 rating of how well top third connects identity -> proof -> pain-point relevance
- thin_competencies: true when competencies section is too sparse or generic for ATS survival
- missing_ai_evidence: true when JD asks for AI/LLM/GenAI depth and CV lacks convincing proof
- low_pain_point_coverage: true when CV misses a material portion of JD pain points
"""

# Required fields for a valid review JSON
_REQUIRED_REVIEW_FIELDS = {"verdict", "confidence", "would_interview", "top_third_assessment"}


# ---------------------------------------------------------------------------
# Taxonomy derivation helpers
# ---------------------------------------------------------------------------

def _text_contains_any(text: str, phrases: list) -> bool:
    """Check if lowercased text contains any of the given phrases."""
    text_lower = text.lower()
    return any(p in text_lower for p in phrases)


def derive_failure_modes(review: dict) -> list:
    """Derive failure mode enums from review data."""
    modes = []
    tt = review.get("top_third_assessment", {})
    pp = review.get("pain_point_alignment", {})
    ats = review.get("ats_assessment", {})
    fit = review.get("ideal_candidate_fit", {})
    weaknesses = " ".join(review.get("weaknesses", []))

    # headline_overclaim
    if tt.get("headline_evidence_bounded") is False or _text_contains_any(
        tt.get("headline_verdict", "") + " " + weaknesses,
        ["overclaim", "inflated", "not supported", "overstates", "not grounded", "mispositioned"],
    ):
        modes.append("headline_overclaim")

    # tagline_proof_gap
    if tt.get("tagline_proof_gap") is True or _text_contains_any(
        tt.get("tagline_verdict", "") + " " + weaknesses,
        ["proof", "not credibly", "unsupported", "generic", "fails the"],
    ):
        modes.append("tagline_proof_gap")

    # thin_competencies
    if ats.get("thin_competencies") is True or _text_contains_any(
        tt.get("competencies_verdict", "") + " " + weaknesses,
        ["thin", "sparse", "too few", "not enough keywords", "underdeveloped"],
    ):
        modes.append("thin_competencies")

    # low_pain_point_coverage
    coverage = pp.get("coverage_ratio")
    if pp.get("low_pain_point_coverage") is True or (
        isinstance(coverage, (int, float)) and coverage < 0.5
    ):
        modes.append("low_pain_point_coverage")

    # hallucination_project_context
    for flag in review.get("hallucination_flags", []):
        claim = (flag.get("claim", "") + " " + flag.get("issue", "")).lower()
        if any(w in claim for w in ["commander", "lantern", "not found in master", "project"]):
            modes.append("hallucination_project_context")
            break

    # missing_ai_evidence
    if fit.get("missing_ai_evidence") is True:
        modes.append("missing_ai_evidence")

    return modes


def derive_headline_evidence_bounded(review: dict) -> bool:
    """Derive whether headline stays within evidence bounds."""
    tt = review.get("top_third_assessment", {})
    explicit = tt.get("headline_evidence_bounded")
    if isinstance(explicit, bool):
        return explicit
    # Infer from text
    verdict = tt.get("headline_verdict", "")
    if _text_contains_any(verdict, ["overclaim", "not supported", "overstates", "not grounded", "mispositioned"]):
        return False
    return True


def derive_bridge_quality_score(review: dict) -> int:
    """Derive identity-to-impact bridge quality score (1-10)."""
    tt = review.get("top_third_assessment", {})
    explicit = tt.get("bridge_quality_score")
    if isinstance(explicit, (int, float)) and 1 <= explicit <= 10:
        return int(explicit)
    # Fallback: start from first_impression_score and adjust
    base = tt.get("first_impression_score", 5)
    if not isinstance(base, (int, float)):
        base = 5
    score = float(base)
    if tt.get("tagline_proof_gap") is True:
        score -= 1
    if tt.get("headline_evidence_bounded") is False:
        score -= 1
    pp = review.get("pain_point_alignment", {})
    coverage = pp.get("coverage_ratio")
    if isinstance(coverage, (int, float)) and coverage < 0.4:
        score -= 1
    return max(1, min(10, int(round(score))))


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_user_prompt(
    cv_text: str,
    extracted_jd: Dict[str, Any],
    master_cv_text: str,
    pain_points: Optional[Any] = None,
    company_research: Optional[Any] = None,
    project_texts: Optional[Dict[str, str]] = None,
) -> str:
    """
    Build the user-side prompt from job data.

    Args:
        cv_text: The generated CV markdown text.
        extracted_jd: Structured JD extraction document.
        master_cv_text: Master CV text for hallucination checking.
        pain_points: Mined pain points (list or None).
        company_research: Company research dict or None.
        project_texts: Pre-loaded project file texts, e.g.
            {"commander4.md": "...", "lantern.md": "..."}.

    Returns:
        Formatted user prompt string.
    """
    sections: List[str] = []

    sections.append("## JOB DESCRIPTION INTELLIGENCE")
    sections.append(f"Title: {extracted_jd.get('title', 'Unknown')}")
    sections.append(f"Company: {extracted_jd.get('company', 'Unknown')}")
    sections.append(f"Role Category: {extracted_jd.get('role_category', 'Unknown')}")
    sections.append(f"Seniority: {extracted_jd.get('seniority_level', 'Unknown')}")

    responsibilities = extracted_jd.get("responsibilities", [])
    if responsibilities:
        resp_lines = "\n".join(f"- {r}" for r in responsibilities)
        sections.append(f"\nResponsibilities:\n{resp_lines}")

    technical_skills = extracted_jd.get("technical_skills", [])
    if technical_skills:
        sections.append(f"\nRequired Technical Skills: {', '.join(technical_skills)}")

    top_keywords = extracted_jd.get("top_keywords", [])
    if top_keywords:
        sections.append(f"\nTop ATS Keywords: {', '.join(top_keywords)}")

    implied_pain_points = extracted_jd.get("implied_pain_points", [])
    if implied_pain_points:
        pain_lines = "\n".join(f"- {p}" for p in implied_pain_points)
        sections.append(f"\nImplied Pain Points:\n{pain_lines}")

    ideal = extracted_jd.get("ideal_candidate_profile") or {}
    if ideal:
        sections.append("\nIdeal Candidate Profile:")
        sections.append(f"  Archetype: {ideal.get('archetype', 'Unknown')}")
        sections.append(f"  Identity: {ideal.get('identity_statement', '')}")
        key_traits = ideal.get("key_traits", [])
        if key_traits:
            sections.append(f"  Key Traits: {', '.join(key_traits)}")

    if pain_points:
        if isinstance(pain_points, list):
            pp_lines = "\n".join(f"- {p}" for p in pain_points)
            sections.append(f"\nMined Pain Points:\n{pp_lines}")
        else:
            sections.append(f"\nMined Pain Points:\n{str(pain_points)}")

    if company_research:
        try:
            cr_text = json.dumps(company_research, default=str)[:2000]
        except Exception:
            cr_text = str(company_research)[:2000]
        sections.append(f"\nCompany Research:\n{cr_text}")

    sections.append("\n## MASTER CV (Source of Truth for Hallucination Check)")
    sections.append(master_cv_text[:8000] if master_cv_text else "Master CV not available")

    sections.append("\n## AI PROJECT FILES (Additional Source of Truth)")
    if project_texts:
        for name, text in project_texts.items():
            sections.append(f"\n### {name}")
            sections.append(text[:3000])

    sections.append("\n## CV TO REVIEW")
    sections.append(cv_text)

    sections.append("\n## INSTRUCTIONS")
    sections.append(
        "Review this CV from a hiring manager's perspective. "
        "Focus on the top 1/3 first. "
        "Return your assessment as JSON per the schema in your instructions."
    )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def parse_review_json(raw_output: str) -> Optional[Dict[str, Any]]:
    """
    Parse review JSON from Codex CLI output.

    Tries direct parse first, then regex fallback for mixed output
    (codex may prepend status lines). Validates required fields.

    Returns parsed dict or None if parsing/validation fails.
    """
    review = None

    # Try direct parse
    try:
        review = json.loads(raw_output)
    except (json.JSONDecodeError, ValueError):
        pass

    # Regex fallback — extract first JSON object
    if review is None:
        match = re.search(r'\{[\s\S]*\}', raw_output)
        if match:
            try:
                review = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                return None
        else:
            return None

    # Validate required fields
    if not isinstance(review, dict):
        return None
    if not _REQUIRED_REVIEW_FIELDS.issubset(review.keys()):
        return None

    return review


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------

def build_cv_review_document(
    review: Dict[str, Any],
    model: str,
    failure_modes: List[str],
    headline_bounded: bool,
    bridge_score: int,
) -> Dict[str, Any]:
    """
    Build the cv_review MongoDB document from a parsed review.

    Returns the standard shape persisted to the job document.
    """
    return {
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "reviewer": "independent_gpt",
        "verdict": review.get("verdict"),
        "would_interview": review.get("would_interview"),
        "confidence": review.get("confidence"),
        "first_impression_score": (
            review.get("top_third_assessment", {}).get("first_impression_score")
        ),
        "failure_modes": failure_modes,
        "headline_evidence_bounded": headline_bounded,
        "bridge_quality_score": bridge_score,
        "full_review": review,
    }
