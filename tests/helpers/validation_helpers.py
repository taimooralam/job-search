"""
Shared validation helper functions for prompt improvement tests.

These utilities support testing across Layer 4, 6a, and 6b by providing:
- Pain point reference counting
- STAR company extraction
- Sentence extraction
- Generic phrase detection
"""

import re
from typing import List, Dict, Any, Set


def count_pain_point_references(text: str, pain_points: List[str]) -> int:
    """
    Count how many pain points are semantically referenced in text.

    Uses key term extraction to detect pain point references even when
    paraphrased or reworded.

    Args:
        text: The text to search (cover letter, rationale, etc.)
        pain_points: List of pain point strings from job analysis

    Returns:
        Count of pain points that are referenced in the text

    Example:
        >>> pain_points = ["API latency >500ms causing churn", "Manual deployment taking 3 hours"]
        >>> text = "At StreamCo, I reduced API response time by 85%, addressing latency issues..."
        >>> count_pain_point_references(text, pain_points)
        1  # "latency" matches first pain point
    """
    if not text or not pain_points:
        return 0

    text_lower = text.lower()
    matched_count = 0

    for pain in pain_points:
        # Extract key terms from pain point (nouns, verbs, technical terms)
        pain_keywords = extract_key_terms(pain)

        if not pain_keywords:
            continue

        # Check if ≥30% of key terms appear in text (relaxed from 50% for semantic matching)
        # Also consider it a match if ANY 2+ keywords appear together
        matches = sum(1 for kw in pain_keywords if kw in text_lower)
        match_ratio = matches / len(pain_keywords) if pain_keywords else 0

        # Match if: 30%+ of terms match OR 2+ absolute matches for short pain points
        if match_ratio >= 0.30 or (len(pain_keywords) <= 5 and matches >= 2):
            matched_count += 1

    return matched_count


def extract_key_terms(text: str) -> List[str]:
    """
    Extract key terms (nouns, verbs, technical terms) from text.

    Used for semantic matching of pain points and requirements.

    Args:
        text: Text to extract key terms from

    Returns:
        List of lowercase key terms (2+ chars, excluding stop words)

    Example:
        >>> extract_key_terms("API latency >500ms causing customer churn")
        ['api', 'latency', '500ms', 'causing', 'customer', 'churn']
    """
    if not text:
        return []

    # Stop words to exclude
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
        'that', 'these', 'those', 'it', 'its', 'they', 'their', 'them'
    }

    # Extract words and technical terms (including numbers with units)
    # Match: alphanumeric sequences, numbers with units (10M, 500ms, 75%), technical terms
    pattern = r'\b(?:\d+(?:\.\d+)?[KMBkmb%xX]?(?:ms|MB|GB|TB)?|\w{2,})\b'
    matches = re.findall(pattern, text.lower())

    # Filter out stop words and single-letter terms
    key_terms = [m for m in matches if m not in stop_words and len(m) >= 2]

    return key_terms


def extract_sentences_with_keyword(text: str, keyword: str) -> List[str]:
    """
    Extract all sentences containing a specific keyword.

    Used to verify company+metric co-occurrence in cover letters.

    Args:
        text: Full text to search
        keyword: Keyword to find (case-insensitive)

    Returns:
        List of sentences containing the keyword

    Example:
        >>> text = "At StreamCo, I reduced latency by 85%. This improved uptime to 99.9%."
        >>> extract_sentences_with_keyword(text, "StreamCo")
        ["At StreamCo, I reduced latency by 85%."]
    """
    if not text or not keyword:
        return []

    # Improved sentence splitting that handles:
    # - Company names with periods (e.g., "Seven.One", "Inc.")
    # - Abbreviations (e.g., "Dr.", "Mr.", "U.S.")
    # - Decimal numbers (e.g., "99.9%")
    # Pattern: split on period/!/? followed by space and capital letter, or end of string
    sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])$'
    sentences = re.split(sentence_pattern, text)

    keyword_lower = keyword.lower()
    matching_sentences = []

    for sentence in sentences:
        sentence = sentence.strip()
        if sentence and keyword_lower in sentence.lower():
            matching_sentences.append(sentence)

    return matching_sentences


def extract_star_companies(state: Dict[str, Any]) -> List[str]:
    """
    Extract company names from STAR achievements in job state.

    Used for validation that cover letters and rationales cite actual companies.

    Args:
        state: JobState dictionary containing selected_stars

    Returns:
        List of unique company names from STARs

    Example:
        >>> state = {"selected_stars": [
        ...     {"company": "StreamCo", "results": "..."},
        ...     {"company": "DataCo", "results": "..."}
        ... ]}
        >>> extract_star_companies(state)
        ["StreamCo", "DataCo"]
    """
    if not state:
        return []

    stars = state.get("selected_stars") or []
    companies = []

    for star in stars:
        if isinstance(star, dict):
            company = star.get("company")
            if company:
                companies.append(company)

    # Return unique companies
    return list(set(companies))


def count_generic_phrases(text: str) -> int:
    """
    Count generic/boilerplate phrases in text.

    Used to enforce zero-tolerance for generic language in cover letters
    and rationales.

    Args:
        text: Text to check for generic phrases

    Returns:
        Count of generic phrases found

    Example:
        >>> text = "I am excited to apply for this perfect fit role as a strong team player."
        >>> count_generic_phrases(text)
        3  # "excited to apply", "perfect fit", "strong team player"
    """
    if not text:
        return 0

    # Expanded list of generic phrases to detect
    GENERIC_BOILERPLATE_PHRASES = [
        # Overused openers
        "excited to apply",
        "thrilled to apply",
        "writing to express my interest",
        "i am writing to",
        "i would like to apply",

        # Generic qualifications
        "perfect fit",
        "ideal candidate",
        "strong background",
        "proven track record",
        "extensive experience",
        "solid foundation",
        "well-suited",
        "excellent fit",

        # Vague descriptors
        "team player",
        "detail-oriented",
        "results-driven",
        "self-motivated",
        "passionate about",
        "highly motivated",
        "hard worker",

        # Generic skills
        "strong communication skills",
        "excellent problem-solving",
        "fast learner",
        "ability to work independently",

        # Cliché closers
        "look forward to hearing from you",
        "thank you for your consideration",
        "i believe i would be",
        "i am confident that",

        # Seasoned professional syndrome
        "seasoned professional",
        "years of experience",
        "diverse background",
        "broad range of",
    ]

    text_lower = text.lower()
    count = 0

    for phrase in GENERIC_BOILERPLATE_PHRASES:
        if phrase in text_lower:
            count += 1

    return count


def extract_metrics(text: str) -> Set[str]:
    """
    Extract all quantified metrics from text.

    Supports: percentages, multipliers, dollar amounts, counts, time, latency, data volumes.

    Args:
        text: Text to extract metrics from

    Returns:
        Set of metric strings found (normalized)

    Example:
        >>> extract_metrics("Reduced costs by 75% and saved $1.5M while improving 10x")
        {'75', '1.5', '10'}
    """
    if not text:
        return set()

    metrics = set()

    # Metric patterns
    patterns = [
        r'(\d+(?:\.\d+)?)\s*%',           # Percentages: 75%, 99.9%
        r'(\d+(?:\.\d+)?)[xX]',           # Multipliers: 10x, 2.5X
        r'\$\s*(\d+(?:\.\d+)?)[KMBkmb]?', # Dollar amounts: $1.5M, $500K
        r'(\d+(?:\.\d+)?)\s*[KMB](?:\s|$)',  # Counts with units: 10M, 500K
        r'(\d+)\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|days?|weeks?|months?|years?)',  # Time
        r'(\d+)\s*ms',                     # Latency: 50ms, 120ms
        r'(\d+)\s*[TGM]B',                # Data volumes: 10TB, 500GB
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Normalize (remove commas, convert to string)
            normalized = str(match).replace(',', '')
            metrics.add(normalized)

    return metrics


def validate_rationale_v2(
    rationale: str,
    selected_stars: List[Dict[str, Any]],
    pain_points: List[str],
    min_word_count: int = 50,
    max_generic_phrases: int = 1
) -> List[str]:
    """
    Validate rationale against V2 requirements (for Layer 4).

    Validation gates:
    1. Must cite ≥1 STAR by company name
    2. Must include ≥1 quantified metric
    3. Must reference ≥1 pain point by key terms
    4. Must not contain >max_generic_phrases generic phrases
    5. Must be ≥min_word_count words

    Args:
        rationale: Fit rationale text to validate
        selected_stars: List of STAR dictionaries with 'company' keys
        pain_points: List of pain point strings
        min_word_count: Minimum word count (default 50)
        max_generic_phrases: Maximum allowed generic phrases (default 1)

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not rationale:
        errors.append("Rationale is empty")
        return errors

    # Gate 1: STAR citation
    star_companies = [s.get('company', '') for s in selected_stars if isinstance(s, dict)]
    star_cited = any(company and company.lower() in rationale.lower() for company in star_companies)

    if not star_cited and star_companies:
        errors.append(
            f"Must cite at least one STAR by company name. "
            f"Available: {', '.join(star_companies[:3])}"
        )

    # Gate 2: Metric presence
    metrics = extract_metrics(rationale)
    if not metrics:
        errors.append("Must include at least one quantified metric (%, $, x, counts)")

    # Gate 3: Pain point reference (only when pain points are provided)
    if pain_points:
        pain_matches = count_pain_point_references(rationale, pain_points)
        if pain_matches < 1:
            errors.append(
                "Must explicitly reference at least one pain point from the job description"
            )

    # Gate 4: Generic phrases
    generic_count = count_generic_phrases(rationale)
    if generic_count > max_generic_phrases:
        errors.append(
            f"Too many generic phrases: {generic_count} found (max {max_generic_phrases})"
        )

    # Gate 5: Minimum length
    word_count = len(rationale.split())
    if word_count < min_word_count:
        errors.append(
            f"Rationale too short: {word_count} words (minimum {min_word_count})"
        )

    return errors


def validate_cover_letter_v2(
    text: str,
    state: Dict[str, Any],
    min_pain_points: int = 2,
    require_company_signal: bool = True,
    allow_generic_phrases: int = 0
) -> List[str]:
    """
    Validate cover letter against V2 requirements (for Layer 6a).

    Validation gates:
    1. Must reference ≥min_pain_points pain points semantically
    2. Must cite ≥1 company+metric in same sentence
    3. Must reference ≥1 company signal by type (if require_company_signal)
    4. Zero generic phrases allowed (default)

    Args:
        text: Cover letter text to validate
        state: JobState dictionary with pain_points, selected_stars, company_research
        min_pain_points: Minimum pain points to reference (default 2)
        require_company_signal: Require company signal reference (default True)
        allow_generic_phrases: Max generic phrases allowed (default 0)

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not text:
        errors.append("Cover letter is empty")
        return errors

    # Gate 1: Pain point references
    pain_points = state.get("pain_points") or []
    pain_matches = count_pain_point_references(text, pain_points)

    if pain_matches < min_pain_points:
        errors.append(
            f"Must reference at least {min_pain_points} pain points semantically. "
            f"Found {pain_matches}/{len(pain_points)}"
        )

    # Gate 2: Company + metric co-occurrence
    star_companies = extract_star_companies(state)
    metric_patterns = [r'\d+%', r'\d+x', r'\$\d+[KMB]?', r'\d+\s*(?:min|ms|M|K)']

    company_metric_pairs = 0
    for company in star_companies:
        sentences = extract_sentences_with_keyword(text, company)
        for sent in sentences:
            if any(re.search(pattern, sent, re.IGNORECASE) for pattern in metric_patterns):
                company_metric_pairs += 1
                break

    if star_companies and company_metric_pairs < 1:
        errors.append(
            "Must cite at least one metric in the same sentence as a company name"
        )

    # Gate 3: Company signal reference
    if require_company_signal:
        company_research = state.get("company_research") or {}
        signals = company_research.get("signals") or []

        if signals:
            signal_types = {s.get('type') for s in signals if isinstance(s, dict)}
            signal_type_keywords = {
                'funding': ['funding', 'raised', 'series', 'investment'],
                'product_launch': ['launch', 'launched', 'product', 'released'],
                'acquisition': ['acquired', 'acquisition', 'merger'],
                'growth': ['growth', 'expansion', 'scaling', 'hire', 'hiring']
            }

            signal_referenced = False
            for sig_type in signal_types:
                keywords = signal_type_keywords.get(sig_type, [])
                if any(kw in text.lower() for kw in keywords):
                    signal_referenced = True
                    break

            if not signal_referenced:
                errors.append(
                    f"Must reference company context. Available signals: {', '.join(signal_types)}"
                )

    # Gate 4: Generic phrases
    generic_count = count_generic_phrases(text)
    if generic_count > allow_generic_phrases:
        errors.append(
            f"Generic phrases detected ({generic_count}). Zero tolerance for boilerplate."
        )

    return errors
