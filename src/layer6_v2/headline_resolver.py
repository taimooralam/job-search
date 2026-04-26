"""
Evidence-bounded headline resolver.

Ensures CV headlines use the JD title for ATS matching but stay within
the candidate's verified evidence boundary. Shared by header_generator.py
(ProfileOutput headline) and orchestrator.py (final CV markdown title).
"""

import re

# Titles the candidate cannot credibly claim (no verified evidence)
_REJECTED_TITLE_PATTERNS = [
    r"\bdata\s+scientist\b",
    r"\bml\s+researcher\b",
    r"\bmachine\s+learning\s+researcher\b",
    r"\bresearch\s+scientist\b",
    r"\bcomputer\s+vision\s+engineer\b",
    r"\brobotic(?:s)?\s+engineer\b",
    r"\bandroid\s+engineer\b",
    r"\bios\s+engineer\b",
    r"\bmobile\s+engineer\b",
    r"\bfirmware\s+engineer\b",
    r"\bnetwork\s+engineer\b",
    r"\bdevops\s+engineer\b",
    r"\bdata\s+engineer\b",
    r"\bfront\s*end\s+engineer\b",
]

# Generic fallback titles per role category
_FALLBACK_TITLES = {
    "ai_architect": "AI Architect",
    "ai_leadership": "Head of AI",
    "engineering_manager": "Engineering Leader",
    "director_of_engineering": "Director of Engineering",
    "head_of_engineering": "Head of Engineering",
    "vp_engineering": "VP Engineering",
    "cto": "CTO",
    "tech_lead": "Technical Lead",
    "senior_engineer": "Senior Software Engineer",
    "staff_principal_engineer": "Staff Engineer",
}

# Role-category-specific suffixes
_HEADLINE_SUFFIXES = {
    "ai_architect": "Production Systems & AI Platform Architecture",
    "ai_leadership": "AI Platform Leadership & Production Systems",
    "engineering_manager": "Engineering Leadership",
    "director_of_engineering": "Engineering Leadership",
    "head_of_engineering": "Engineering Leadership",
    "vp_engineering": "Technology Executive Leadership",
    "cto": "Technology Executive Leadership",
    "tech_lead": "Technology Leadership",
    "senior_engineer": "Technology Leadership",
    "staff_principal_engineer": "Technology Leadership",
}


def resolve_headline(
    jd_title: str,
    role_category: str,
    years_experience: int,
) -> str:
    """
    Build an evidence-bounded headline from the JD title.

    Uses the JD title for ATS matching (10.6x interview likelihood) but:
    1. Strips dual-titles ("AI Engineer · AI Architect" → "AI Engineer")
    2. Rejects titles implying specializations the candidate lacks
    3. Selects a role-appropriate suffix instead of generic "Technology Leadership"
    """
    title = _clean_title(jd_title, role_category)
    suffix = _HEADLINE_SUFFIXES.get(role_category, "Technology Leadership")
    return f"{title} | {years_experience}+ Years {suffix}"


def clean_jd_title(jd_title: str, role_category: str) -> str:
    """Clean the JD title for use in CV markdown (no suffix, just the title)."""
    return _clean_title(jd_title, role_category)


def _clean_title(jd_title: str, role_category: str) -> str:
    """Apply dual-title stripping and rejection checks."""
    title = jd_title.strip()

    # Strip dual-titles: "AI Engineer · AI Architect" → "AI Engineer"
    for sep in (" · ", " / ", " | ", " - ", " – ", " — "):
        if sep in title:
            parts = title.split(sep)
            # Keep first part only if both parts look like distinct senior titles
            if len(parts) == 2 and _looks_like_senior_title(parts[1].strip()):
                title = parts[0].strip()
                break

    # Reject titles implying specializations candidate lacks
    title_lower = title.lower()
    for pattern in _REJECTED_TITLE_PATTERNS:
        if re.search(pattern, title_lower):
            title = _FALLBACK_TITLES.get(role_category, "Engineering Professional")
            break

    return title


def _looks_like_senior_title(text: str) -> bool:
    """Check if text looks like a standalone senior role title."""
    senior_words = {
        "engineer", "architect", "lead", "manager", "director",
        "head", "vp", "chief", "principal", "staff", "developer",
    }
    words = set(text.lower().split())
    return bool(words & senior_words)


# ---- Achievement Diversity ----

_ACHIEVEMENT_CATEGORIES = {
    "architecture": [
        "architected", "designed", "platform", "infrastructure",
        "system design", "modernized", "transformed", "microservices",
        "event-driven", "choreography", "monolith",
    ],
    "ai_platform": [
        "ai", "llm", "rag", "commander-4", "joyia", "lantern",
        "semantic", "retrieval", "embedding", "vector", "reranking",
        "plugin", "guardrail", "mcp",
    ],
    "leadership": [
        "led", "mentored", "team of", "hired", "promoted", "culture",
        "onboarding", "coaching", "lean friday", "engineers to lead",
    ],
    "delivery_impact": [
        "reduced", "shipped", "revenue", "cost", "incident",
        "zero downtime", "compliance", "gdpr", "tcf", "regulatory",
        "€30m", "$", "billion",
    ],
}


def classify_achievement(text: str) -> str:
    """Classify an achievement bullet into a category by keyword matching."""
    text_lower = text.lower()
    scores = {}
    for cat, keywords in _ACHIEVEMENT_CATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def enforce_achievement_diversity(
    achievements: list[str],
    all_candidates: list[str],
    role_category: str,
) -> list[str]:
    """
    Post-LLM filter ensuring achievement diversity across categories.

    Rules:
    1. ai_architect/ai_leadership: require at least 1 AI/Platform achievement
    2. All roles: require at least 1 Leadership achievement if available
    3. No more than 3 from the same category
    4. If missing required category, swap lowest-value same-category bullet
       for highest-value candidate from the missing category
    """
    if len(achievements) < 3:
        return achievements

    classified = [(a, classify_achievement(a)) for a in achievements]
    cat_counts = {}
    for _, cat in classified:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # Determine required categories
    required = set()
    if role_category in ("ai_architect", "ai_leadership"):
        required.add("ai_platform")
    required.add("leadership")

    # Check what's missing
    missing = {r for r in required if cat_counts.get(r, 0) == 0}

    if not missing:
        # Check max-3 rule
        over_represented = [c for c, n in cat_counts.items() if n > 3]
        if not over_represented:
            return achievements  # Already diverse

    # Build candidate pool from all_candidates not already selected
    selected_set = set(achievements)
    unselected = [a for a in all_candidates if a not in selected_set]

    result = list(achievements)

    # Fix missing categories first
    for needed_cat in missing:
        # Find best unselected achievement in the needed category
        candidates = [(a, classify_achievement(a)) for a in unselected]
        matching = [a for a, c in candidates if c == needed_cat]
        if not matching:
            continue

        # Find the most over-represented category to steal from
        swappable = sorted(
            [(i, a, c) for i, (a, c) in enumerate(classified) if c not in required and cat_counts.get(c, 0) > 1],
            key=lambda x: cat_counts.get(x[2], 0),
            reverse=True,
        )
        if not swappable:
            # Try swapping any non-required with count > 1
            swappable = sorted(
                [(i, a, c) for i, (a, c) in enumerate(classified) if cat_counts.get(c, 0) > 1],
                key=lambda x: cat_counts.get(x[2], 0),
                reverse=True,
            )
        if not swappable:
            continue

        swap_idx, swap_text, swap_cat = swappable[0]
        new_text = matching[0]

        result[swap_idx] = new_text
        cat_counts[swap_cat] = cat_counts.get(swap_cat, 1) - 1
        cat_counts[needed_cat] = cat_counts.get(needed_cat, 0) + 1
        classified[swap_idx] = (new_text, needed_cat)
        unselected.remove(new_text)

    return result


# ---- Tagline Evidence-First Validator ----

# Patterns that indicate AI-first framing (unverified lead)
_AI_FIRST_PATTERNS = [
    # Direct AI-first (word starts with AI keyword)
    r"^AI\s",
    r"^GenAI\s",
    r"^Generative\s+AI\s",
    r"^LLM\s",
    r"^Machine\s+Learning\s",
    r"^ML\s",
    r"^Agentic\s+AI\s",
    r"^NLP\s",
    r"^Deep\s+Learning\s",
    # Compound AI-first: 0-2 modifiers before AI keyword + role noun
    # Catches "Full-stack AI engineer", "Senior AI architect", "Lead AI developer"
    r"^(?:[A-Za-z-]+\s+){0,2}AI\s+(?:engineer|architect|leader|specialist|developer)\b",
    r"^(?:[A-Za-z-]+\s+){0,2}(?:GenAI|LLM)\s",
    # Slash/hyphen variants: "AI/ML engineer", "AI-focused..."
    r"^AI(?:/ML|-)",
]

# Evidence-first fallback taglines per role category (from taxonomy identity_statements)
_EVIDENCE_FIRST_FALLBACKS = {
    "ai_architect": (
        "Production infrastructure leader applying 11+ years of distributed systems "
        "rigor to LLM gateway design, evaluation pipelines, and AI reliability at scale."
    ),
    "ai_leadership": (
        "Hands-on AI platform leader with 11+ years building production systems — "
        "from LLM gateway design to AI governance at enterprise scale."
    ),
}


def validate_tagline_evidence_first(tagline: str, role_category: str) -> str:
    """
    Reject taglines that lead with unverified AI-specialist claims.

    The candidate's verified identity is "Engineering Leader / Software Architect"
    with hands-on AI platform experience. Taglines must lead with a verifiable
    claim before introducing AI framing.

    Args:
        tagline: Generated tagline text
        role_category: Target role category

    Returns:
        Original tagline if evidence-first, or fallback if AI-first
    """
    if not tagline:
        return _EVIDENCE_FIRST_FALLBACKS.get(role_category, tagline or "")

    for pattern in _AI_FIRST_PATTERNS:
        if re.match(pattern, tagline.strip(), re.IGNORECASE):
            fallback = _EVIDENCE_FIRST_FALLBACKS.get(role_category)
            if fallback:
                return fallback
            break

    return tagline
