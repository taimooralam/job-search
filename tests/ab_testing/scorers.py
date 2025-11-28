"""
Scoring functions for A/B testing prompt quality.

These scorers evaluate prompt outputs on three dimensions:
1. Specificity: How specific vs generic is the output?
2. Grounding: How well does it cite evidence from provided context?
3. Hallucinations: Does it contain fabricated information?

All scores are normalized to 1-10 scale where higher is better
(except hallucinations where lower score = more hallucinations detected).
"""

import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


# Generic boilerplate phrases to detect
GENERIC_PHRASES = [
    "strong background",
    "proven track record",
    "excellent communication",
    "team player",
    "passionate about",
    "excited to apply",
    "perfect fit",
    "great opportunity",
    "looking forward",
    "hit the ground running",
    "add value",
    "unique opportunity",
    "dream job",
    "ideal candidate",
    "well-suited",
    "extensive experience",
    "seasoned professional",
]

# Metric patterns to detect
METRIC_PATTERNS = [
    r'\d+%',           # Percentages
    r'\d+x',           # Multipliers
    r'\$\d+[KMB]?',    # Dollar amounts
    r'€\d+[KMB]?',     # Euro amounts
    r'\d+\s*min',      # Time in minutes
    r'\d+\s*hour',     # Time in hours
    r'\d+\s*day',      # Time in days
    r'\d+\s*month',    # Time in months
    r'\d+\s*year',     # Time in years
    r'\d+\s*engineer', # Team size
    r'\d+\s*user',     # User counts
    r'\d+\s*tenant',   # Tenant counts
]


@dataclass
class ScoreResult:
    """Result from a scoring function."""
    score: float  # 1-10 scale
    details: Dict[str, Any]
    feedback: str


def score_specificity(text: str, context: Optional[Dict[str, Any]] = None) -> ScoreResult:
    """
    Score text on specificity (1-10).

    Measures:
    - Presence of specific metrics/numbers
    - Company/role names mentioned
    - Absence of generic boilerplate phrases
    - Specific dates, technologies, or outcomes

    Args:
        text: The text to score
        context: Optional context dict with company names, metrics, etc.

    Returns:
        ScoreResult with score (1-10), details, and feedback
    """
    if not text or not text.strip():
        return ScoreResult(score=1.0, details={}, feedback="Empty text")

    text_lower = text.lower()
    details = {}

    # Count generic phrases (negative indicator)
    generic_count = sum(1 for phrase in GENERIC_PHRASES if phrase in text_lower)
    details["generic_phrases_found"] = generic_count

    # Count metrics (positive indicator)
    metrics_found = []
    for pattern in METRIC_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        metrics_found.extend(matches)
    details["metrics_found"] = list(set(metrics_found))
    metrics_count = len(set(metrics_found))

    # Count company names from context if provided
    companies_mentioned = 0
    if context:
        # Check for STAR companies
        stars = context.get("selected_stars", [])
        for star in stars:
            company = star.get("company", "")
            if company and company.lower() in text_lower:
                companies_mentioned += 1

        # Check for target company
        target_company = context.get("company", "")
        if target_company and target_company.lower() in text_lower:
            companies_mentioned += 1

    details["companies_mentioned"] = companies_mentioned

    # Count specific technology terms
    tech_terms = ["aws", "kubernetes", "docker", "microservices", "ddd",
                  "python", "typescript", "nodejs", "react", ".net", "c#",
                  "rabbitmq", "kafka", "redis", "postgresql", "mongodb"]
    tech_count = sum(1 for term in tech_terms if term in text_lower)
    details["tech_terms_found"] = tech_count

    # Calculate score
    # Start at 5, adjust based on factors
    score = 5.0

    # Penalize generic phrases (-0.5 per phrase, max -3)
    score -= min(generic_count * 0.5, 3.0)

    # Reward metrics (+0.5 per unique metric, max +2)
    score += min(metrics_count * 0.5, 2.0)

    # Reward company mentions (+0.5 per company, max +1.5)
    score += min(companies_mentioned * 0.5, 1.5)

    # Reward tech specificity (+0.25 per term, max +1.5)
    score += min(tech_count * 0.25, 1.5)

    # Clamp to 1-10
    score = max(1.0, min(10.0, score))

    # Generate feedback
    feedback_parts = []
    if generic_count > 2:
        feedback_parts.append(f"High generic phrase count ({generic_count})")
    if metrics_count == 0:
        feedback_parts.append("No quantified metrics found")
    if companies_mentioned == 0 and context:
        feedback_parts.append("No company names cited")
    if score >= 8:
        feedback_parts.append("Good specificity with concrete details")

    feedback = "; ".join(feedback_parts) if feedback_parts else "Average specificity"

    return ScoreResult(score=round(score, 1), details=details, feedback=feedback)


def score_grounding(text: str, source_context: Dict[str, Any]) -> ScoreResult:
    """
    Score text on evidence grounding (1-10).

    Measures:
    - STAR citations by company name
    - Metrics that match source data
    - Pain point references
    - Company signal references

    Args:
        text: The text to score
        source_context: Context dict with STARs, pain points, company research

    Returns:
        ScoreResult with score (1-10), details, and feedback
    """
    if not text or not text.strip():
        return ScoreResult(score=1.0, details={}, feedback="Empty text")

    text_lower = text.lower()
    details = {}

    # Check STAR company citations
    stars = source_context.get("selected_stars", [])
    star_companies = [s.get("company", "") for s in stars if s.get("company")]
    stars_cited = sum(1 for company in star_companies if company.lower() in text_lower)
    details["stars_cited"] = stars_cited
    details["stars_available"] = len(star_companies)

    # Check if metrics from STARs appear in text
    star_metrics = []
    for star in stars:
        metrics_str = star.get("metrics", "")
        # Extract numbers from metrics
        found = re.findall(r'\d+[%x]|\$\d+[KMB]?|€\d+[KMB]?', metrics_str)
        star_metrics.extend(found)

    metrics_cited = sum(1 for m in star_metrics if m.lower() in text_lower)
    details["star_metrics_cited"] = metrics_cited
    details["star_metrics_available"] = len(star_metrics)

    # Check pain point references
    pain_points = source_context.get("pain_points", [])
    pain_keywords_matched = 0
    for pain in pain_points:
        # Extract key words (>3 chars) from pain point
        words = [w.lower() for w in pain.split() if len(w) > 3]
        # Check if at least 2 words appear in text
        matches = sum(1 for w in words if w in text_lower)
        if matches >= 2:
            pain_keywords_matched += 1

    details["pain_points_referenced"] = pain_keywords_matched
    details["pain_points_available"] = len(pain_points)

    # Check company signal references
    company_research = source_context.get("company_research", {})
    signals = company_research.get("signals", [])
    signal_keywords = ["funding", "series", "raised", "launch", "growth",
                       "expansion", "acquisition", "partnership"]
    signals_referenced = sum(1 for kw in signal_keywords if kw in text_lower)
    details["signals_referenced"] = min(signals_referenced, len(signals))

    # Calculate score
    score = 5.0

    # STAR citation (strong indicator)
    if stars_cited >= 2:
        score += 2.0
    elif stars_cited == 1:
        score += 1.0
    elif star_companies:  # Available but not cited
        score -= 1.0

    # Metrics grounding
    if star_metrics:
        citation_ratio = metrics_cited / len(star_metrics)
        score += citation_ratio * 1.5

    # Pain point coverage
    if pain_points:
        coverage_ratio = pain_keywords_matched / len(pain_points)
        score += coverage_ratio * 1.5

    # Signal references
    if signals and signals_referenced > 0:
        score += 0.5

    # Clamp
    score = max(1.0, min(10.0, score))

    # Feedback
    feedback_parts = []
    if stars_cited == 0 and star_companies:
        feedback_parts.append("No STAR companies cited")
    if metrics_cited == 0 and star_metrics:
        feedback_parts.append("No STAR metrics referenced")
    if pain_keywords_matched == 0 and pain_points:
        feedback_parts.append("Pain points not addressed")
    if score >= 8:
        feedback_parts.append("Strong evidence grounding")

    feedback = "; ".join(feedback_parts) if feedback_parts else "Moderate grounding"

    return ScoreResult(score=round(score, 1), details=details, feedback=feedback)


def score_hallucinations(text: str, master_cv: str, state: Dict[str, Any]) -> ScoreResult:
    """
    Score text for hallucinations (1-10, higher = fewer hallucinations).

    Checks for:
    - Companies not in master CV
    - Metrics not in source data
    - Fabricated dates or timelines
    - Claims without evidence

    Args:
        text: The text to score
        master_cv: The master CV text for verification
        state: State dict with STARs and other context

    Returns:
        ScoreResult with score (1-10), details, and feedback
    """
    if not text or not text.strip():
        return ScoreResult(score=10.0, details={}, feedback="Empty text - no hallucinations")

    text_lower = text.lower()
    master_cv_lower = master_cv.lower() if master_cv else ""
    details = {}
    issues = []

    # Known companies from master CV and STARs
    known_companies = set()

    # Extract from STARs
    stars = state.get("selected_stars", [])
    for star in stars:
        company = star.get("company", "")
        if company:
            known_companies.add(company.lower())
            # Also add partial names
            for word in company.split():
                if len(word) > 3:
                    known_companies.add(word.lower())

    # Extract from master CV (look for company patterns)
    # Pattern: "Company Name" or "at Company"
    cv_company_patterns = [
        r'at\s+([A-Z][A-Za-z\s]+)[\s—\-|]',
        r'—\s*([A-Z][A-Za-z\s]+)\s*—',
    ]
    for pattern in cv_company_patterns:
        matches = re.findall(pattern, master_cv or "")
        for match in matches:
            known_companies.add(match.strip().lower())

    details["known_companies"] = list(known_companies)[:10]

    # Check for potential fabricated companies
    # Look for "At [Company]" or "at [Company]" patterns (case-insensitive)
    company_mentions = re.findall(r'[Aa]t\s+([A-Z][A-Za-z\s]+?)[\s,\.]', text)
    unknown_companies = []
    for company in company_mentions:
        company_clean = company.strip().lower()
        # Check if any known company is a substring or vice versa
        is_known = any(
            kc in company_clean or company_clean in kc
            for kc in known_companies
        )
        if not is_known and len(company_clean) > 3:
            unknown_companies.append(company.strip())

    details["potential_unknown_companies"] = unknown_companies
    if unknown_companies:
        issues.append(f"Unknown companies mentioned: {unknown_companies[:3]}")

    # Check for metrics in text that don't appear in STARs or master CV
    text_metrics = re.findall(r'\d+%|\d+x|\$\d+[KMB]?|€\d+[KMB]?', text)

    # Collect known metrics
    known_metrics = set()
    for star in stars:
        metrics_str = star.get("metrics", "") + " " + star.get("results", "")
        found = re.findall(r'\d+%|\d+x|\$\d+[KMB]?|€\d+[KMB]?', metrics_str, re.IGNORECASE)
        known_metrics.update(m.lower() for m in found)

    # Also from master CV
    cv_metrics = re.findall(r'\d+%|\d+x|\$\d+[KMB]?|€\d+[KMB]?', master_cv or "", re.IGNORECASE)
    known_metrics.update(m.lower() for m in cv_metrics)

    details["known_metrics"] = list(known_metrics)[:15]

    # Check for ungrounded metrics
    ungrounded_metrics = [m for m in text_metrics if m.lower() not in known_metrics]
    # Filter out common/reasonable metrics (years, common percentages)
    suspicious_metrics = [m for m in ungrounded_metrics
                         if not re.match(r'20\d\d', m)]  # Allow year mentions

    details["ungrounded_metrics"] = suspicious_metrics
    if suspicious_metrics:
        issues.append(f"Unverified metrics: {suspicious_metrics[:3]}")

    # Calculate score (start at 10, subtract for issues)
    score = 10.0

    # Penalize unknown companies (-1.5 each, max -4)
    score -= min(len(unknown_companies) * 1.5, 4.0)

    # Penalize suspicious metrics (-1.0 each, max -3) - stricter penalty
    score -= min(len(suspicious_metrics) * 1.0, 3.0)

    # Clamp
    score = max(1.0, min(10.0, score))

    # Feedback
    if score >= 9:
        feedback = "No significant hallucinations detected"
    elif score >= 7:
        feedback = "Minor verification concerns"
    elif score >= 5:
        feedback = f"Moderate hallucination risk: {'; '.join(issues[:2])}"
    else:
        feedback = f"High hallucination risk: {'; '.join(issues)}"

    return ScoreResult(score=round(score, 1), details=details, feedback=feedback)


def calculate_combined_score(
    specificity: ScoreResult,
    grounding: ScoreResult,
    hallucinations: ScoreResult,
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate weighted combined score from individual scores.

    Args:
        specificity: Specificity score result
        grounding: Grounding score result
        hallucinations: Hallucinations score result
        weights: Optional weights dict (defaults to equal weighting)

    Returns:
        Combined score (1-10)
    """
    if weights is None:
        weights = {"specificity": 0.3, "grounding": 0.4, "hallucinations": 0.3}

    combined = (
        specificity.score * weights.get("specificity", 0.3) +
        grounding.score * weights.get("grounding", 0.4) +
        hallucinations.score * weights.get("hallucinations", 0.3)
    )

    return round(combined, 1)
