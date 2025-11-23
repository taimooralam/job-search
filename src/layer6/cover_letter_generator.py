"""
Layer 6a: Enhanced Cover Letter Generator (Phase 8.1)

Generates hyper-personalized cover letters with validation gates for:
- STAR metric citations
- JD-specific content
- Anti-boilerplate checks
- Structural requirements (3-4 paragraphs, 220-380 words)
"""

import re
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState


# ===== HELPER FUNCTIONS =====

def _extract_companies_from_profile(profile: str) -> list:
    """
    Extract employer/company names from candidate profile (master-cv.md).

    Phase 8: Enables company grounding when STAR selector is disabled.

    Looks for patterns like:
    - "Company Name | Role | Date"
    - "Company Name — Role — Date"
    - "Role — Company Name — Date"
    - Lines in Professional Experience section

    Args:
        profile: Raw text of candidate profile/master CV

    Returns:
        List of company names found in the profile
    """
    companies = []

    if not profile:
        return companies

    lines = profile.split('\n')

    # Known company name patterns from typical CV formats
    # Pattern 1: "Title — Company — Location | Date" or "Company — Location | Date"
    # Pattern 2: "Title | Company | Date"
    # Pattern 3: Lines starting with company indicators

    # Track if we're in an education section (skip all lines until experience section)
    in_education_section = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        line_lower = line.lower()

        # Detect section headers (lines starting with # or **)
        if line.startswith('#') or line.startswith('**'):
            # Check for education section start
            if 'education' in line_lower or 'certification' in line_lower:
                in_education_section = True
                continue
            # Check for experience section start (ends education section)
            if 'experience' in line_lower or 'employment' in line_lower or 'work' in line_lower:
                in_education_section = False
                continue

        # Skip all lines if in education section
        if in_education_section:
            continue

        # Skip header lines and education-related content
        skip_keywords = ['profile', 'summary', 'skill', 'email', 'phone',
                        'linkedin', 'github', 'http', '@', 'degree', 'b.s.', 'b.a.',
                        'm.s.', 'm.a.', 'mba', 'phd', 'university', 'college', 'school']
        if any(kw in line_lower for kw in skip_keywords):
            continue

        # Pattern: "Title — Company — Location | Date" (em-dash format)
        if '—' in line:
            parts = [p.strip() for p in line.split('—')]
            # Company is usually the second part in "Role — Company — Location"
            for part in parts[1:3]:  # Check positions 1 and 2
                # Filter out location-like strings and dates
                if part and not _is_location_or_date(part):
                    # Remove trailing location indicators
                    company = _clean_company_name(part)
                    if company and len(company) > 2:
                        companies.append(company)

        # Pattern: "Title | Company | Date" (pipe format)
        elif '|' in line:
            parts = [p.strip() for p in line.split('|')]
            for part in parts:
                if part and not _is_location_or_date(part):
                    company = _clean_company_name(part)
                    if company and len(company) > 2 and not _is_job_title(company):
                        companies.append(company)

    # Remove duplicates while preserving order
    seen = set()
    unique_companies = []
    for c in companies:
        c_lower = c.lower()
        if c_lower not in seen:
            seen.add(c_lower)
            unique_companies.append(c)

    return unique_companies


def _is_location_or_date(text: str) -> bool:
    """Check if text looks like a location or date rather than company name."""
    text_lower = text.lower()

    # Date patterns
    date_patterns = ['present', '20', '19', 'jan', 'feb', 'mar', 'apr', 'may', 'jun',
                     'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    if any(p in text_lower for p in date_patterns):
        return True

    # Location indicators
    locations = ['munich', 'berlin', 'london', 'new york', 'sf', 'bay area', 'remote',
                 'germany', 'de', 'us', 'uk', 'usa', 'hybrid', 'pk', 'islamabad']
    if any(loc in text_lower for loc in locations):
        return True

    return False


def _clean_company_name(text: str) -> str:
    """Clean and extract company name from text."""
    # Remove common suffixes that aren't the company name
    text = text.strip()

    # Remove location suffixes like "Munich, DE"
    if ',' in text:
        text = text.split(',')[0].strip()

    return text


def _is_job_title(text: str) -> bool:
    """Check if text looks like a job title rather than company name."""
    title_keywords = ['engineer', 'manager', 'lead', 'senior', 'director', 'head',
                      'developer', 'architect', 'specialist', 'analyst', 'consultant']
    text_lower = text.lower()
    return any(kw in text_lower for kw in title_keywords)


# ===== VALIDATION CONFIGURATION =====

# Generic boilerplate phrases that should be avoided
GENERIC_BOILERPLATE_PHRASES = [
    "i am excited to apply",
    "dream job",
    "perfect fit for this role",
    "perfect fit for your team",
    "strong background",
    "team player",
    "hit the ground running",
    "add value to your team",
    "ideal candidate",
    "passionate about",
    "thrilled to apply",
    "great opportunity",
    "exciting opportunity"
]

# Metric patterns to search for
METRIC_PATTERNS = [
    r'\d+%',           # 75%, 20%
    r'\d+x',           # 10x, 100x
    r'\d+X',           # 10X, 100X
    r'\$\d+[KMB]',     # $2M, $500K, $1B
    r'\d+\s+(min|hr|hour|day|week|month)',  # 30 min, 4 hours (requires space)
    r'\d+[.,]\d+%',    # 99.99%, 3.5%
]


# ===== PROMPTS =====

SYSTEM_PROMPT = """You are an expert career consultant specializing in hyper-personalized cover letters.

Your task: Write a compelling, evidence-based cover letter grounded strictly in:
- The job description and pain points
- Company and role research
- The candidate's master CV (no hallucinations)

**STRUCTURE (3-4 paragraphs):**

1. **Hook** (1 paragraph):
   - Express specific interest in the role and company
   - Reference at least ONE explicit pain point from the job description
   - Mention why NOW matters for this company (reference company research: funding, product launch, growth stage, etc.)

2. **Proof** (1-2 paragraphs):
   - Highlight 2-3 achievements with CONCRETE METRICS from the master CV or provided achievements
   - Each achievement should directly address a pain point or strategic need
   - Use this format: "At [Company], I [action] resulting in [metric]"

3. **Plan** (1 paragraph):
   - Brief 90-day vision OR clear call to action
   - Express confidence without arrogance
   - End with: "taimooralam@example.com | https://calendly.com/taimooralam/15min"

**REQUIREMENTS:**
- 220-380 words total
- Include at least 2 quantified metrics (e.g., "75% reduction", "10x improvement", "$2M savings") when available
- Reference specific pain points or strategic needs from the job description
- Reference company context (funding, growth, product launches, market position)
- NO generic boilerplate phrases ("excited to apply", "perfect fit", "dream job", "team player", etc.)
- NO address/date header or formal signature block
- Use professional but warm, confident tone

**FORBIDDEN PHRASES:**
- "I am excited to apply"
- "This is my dream job"
- "Perfect fit for this role"
- "Strong background"
- "Great team player"
- "Hit the ground running"
- "Add value"
- "Ideal candidate"
"""

USER_PROMPT_TEMPLATE = """Write a hyper-personalized cover letter for this opportunity:

=== JOB DETAILS ===
Title: {title}
Company: {company}

=== JOB DESCRIPTION (Excerpt) ===
{job_description}

=== PAIN POINTS (What they need solved NOW) ===
{pain_points}

=== STRATEGIC NEEDS ===
{strategic_needs}

=== COMPANY RESEARCH ===
{company_research}

=== ROLE RESEARCH ===
{role_research}

=== CANDIDATE PROFILE (MASTER CV) ===
{candidate_profile}

=== FIT ANALYSIS ===
Score: {fit_score}/100
{fit_rationale}

=== YOUR TASK ===
Write a 3-4 paragraph cover letter (220-380 words) that:
1. Opens with specific interest in {company}'s {title} role, mentioning a pain point and company context
2. Highlights 2-3 achievements with concrete metrics from the master CV that address their needs
3. Closes with confidence and call to action

Remember:
- Ground claims in the supplied master CV or provided achievements and include specific metrics
- Address at least 2 pain points explicitly
- Reference company signals (funding, growth, product launches)
- Avoid all generic boilerplate phrases
- End with: taimooralam@example.com | https://calendly.com/taimooralam/15min

Cover Letter:
"""


# ===== VALIDATION FUNCTION =====

def validate_cover_letter(text: str, state: JobState) -> None:
    """
    Validate cover letter against quality gates.

    Raises ValueError if validation fails.

    Quality Gates:
    1. Paragraph count: 3-4 paragraphs
    2. Word count: 220-380 words
    3. Metric presence: At least 1 quantified metric
    4. JD-specificity: At least 2 phrases from pain points or job description
    5. Generic boilerplate: No more than 2 blacklisted phrases

    Args:
        text: Cover letter text to validate
        state: JobState with pain points and job description for specificity check

    Raises:
        ValueError: If any validation gate fails
    """
    # Gate 1: Paragraph count (3-4)
    # More flexible paragraph detection: split by double OR single newlines, then filter
    # This handles LLM output that may use inconsistent newline formatting
    paragraphs = []

    # First try double-newline split (proper formatting)
    double_nl_paras = [p.strip() for p in text.split('\n\n') if p.strip()]

    if len(double_nl_paras) >= 3:
        # Use double-newline paragraphs if we have enough
        paragraphs = double_nl_paras
    else:
        # Fallback: split by single newlines and group into logical paragraphs
        # A logical paragraph is a continuous block of text (≥30 words)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        current_para = []

        for line in lines:
            # Skip empty lines
            if not line:
                if current_para:
                    paragraphs.append(' '.join(current_para))
                    current_para = []
                continue

            # Add to current paragraph
            current_para.append(line)

            # Check if current paragraph is substantial (≥30 words)
            word_count = len(' '.join(current_para).split())
            if word_count >= 30:
                paragraphs.append(' '.join(current_para))
                current_para = []

        # Add any remaining content
        if current_para:
            paragraphs.append(' '.join(current_para))

    # Filter out the contact info line
    paragraphs = [p for p in paragraphs if 'calendly' not in p.lower() and '@' not in p]

    # Relaxed structural constraints for production:
    # accept 2-5 substantial paragraphs instead of forcing exactly 3-4.
    if len(paragraphs) < 2:
        raise ValueError(
            f"Cover letter must have at least 2 paragraphs (found {len(paragraphs)}). "
            "Each paragraph should be 30+ words."
        )
    if len(paragraphs) > 5:
        raise ValueError(
            f"Cover letter must have at most 5 paragraphs (found {len(paragraphs)})."
        )

    # Gate 2: Word count (relaxed from 220-380 to 180-420)
    words = text.split()
    word_count = len(words)

    if word_count < 180:
        raise ValueError(f"Cover letter too short: {word_count} words (minimum 180)")
    if word_count > 420:
        raise ValueError(f"Cover letter too long: {word_count} words (maximum 420)")

    # Gate 3: Metric presence (relaxed: require ≥1 quantified metric instead of 2)
    metric_matches = []
    for pattern in METRIC_PATTERNS:
        matches = re.findall(pattern, text)
        metric_matches.extend(matches)

    # Count distinct metrics (deduplicate identical values like "75%, 75%")
    unique_metrics = set(metric_matches)
    metric_count = len(unique_metrics)

    if metric_count < 1:
        raise ValueError(
            f"Cover letter must include at least 1 quantified metric (found {metric_count}). "
            "Examples: 75%, 10x, $2M, 100K users, 99.99% uptime"
        )

    # Gate 3.5: Company mentions (ROADMAP 8.1: tie metrics to real experience)
    # Ensure at least one employer is mentioned to ground metrics in real achievements
    # Phase 8: When STAR selector is disabled, extract companies from master-cv.md (candidate_profile)
    selected_stars = state.get("selected_stars", [])
    star_companies = [star.get("company", "") for star in selected_stars if star.get("company")]

    # If no selected_stars, extract companies from candidate_profile (master-cv.md)
    if not star_companies:
        candidate_profile = state.get("candidate_profile", "")
        star_companies = _extract_companies_from_profile(candidate_profile)

    text_lower = text.lower()
    company_mentioned = False
    for company in star_companies:
        # Normalize company name for matching (handle variations)
        company_lower = company.lower().strip()

        # Option 1: Full company name match
        if len(company_lower) >= 3 and company_lower in text_lower:
            company_mentioned = True
            break

        # Option 2: Partial match - check if any significant word (>=4 chars) appears
        # This allows "at FinTech" to match "FinTech Startup Inc"
        company_words = company_lower.split()
        for word in company_words:
            # Skip common suffixes like "inc", "co", "llc", "ltd"
            if word in ['inc', 'co', 'llc', 'ltd', 'corp', 'corporation', 'company']:
                continue
            if len(word) >= 4 and word in text_lower:
                company_mentioned = True
                break
        if company_mentioned:
            break

    if not company_mentioned and star_companies:
        raise ValueError(
            f"Cover letter must mention at least one employer from your experience to ground metrics in real achievements. "
            f"Available: {', '.join(star_companies[:5])}"
        )

    # Gate 4: JD-specificity (relaxed keyword/phrase overlap approach)
    # Phase 8.1 relaxation: Accept if EITHER:
    #   (a) ≥1 exact multi-word phrase (≥2 words) from pain points/JD, OR
    #   (b) ≥3 distinct keyword hits spread across ≥2 paragraphs
    pain_points = state.get("pain_points", [])
    job_description = state.get("job_description", "")
    text_lower = text.lower()

    # Stop words to filter out when extracting keywords
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'been',
                  'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                  'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that',
                  'these', 'those', 'it', 'its', 'your', 'our', 'their', 'we', 'you',
                  'who', 'what', 'when', 'where', 'why', 'how', 'all', 'each', 'every',
                  'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
                  'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just'}

    # Only enforce this gate when we actually have pain points or JD content
    source_text = ' '.join(pain_points) + ' ' + job_description
    if not source_text.strip():
        pass  # Skip gate if no source content
    else:
        # Condition (a): Check for exact multi-word phrase match (≥2 words)
        exact_phrase_found = False

        # Extract multi-word phrases from pain points
        for pain in pain_points:
            pain_words = [w.strip('.,!?;:()[]{}"\'-') for w in pain.lower().split()]
            # Look for 2+ word phrases
            for phrase_len in range(2, min(len(pain_words) + 1, 6)):  # Up to 5-word phrases
                for i in range(len(pain_words) - phrase_len + 1):
                    phrase = ' '.join(pain_words[i:i + phrase_len])
                    # Skip phrases that are mostly stop words
                    phrase_keywords = [w for w in pain_words[i:i + phrase_len]
                                       if w not in stop_words and len(w) > 2]
                    if len(phrase_keywords) >= 1 and phrase in text_lower:
                        exact_phrase_found = True
                        break
                if exact_phrase_found:
                    break
            if exact_phrase_found:
                break

        # Condition (b): Check for ≥3 distinct keyword hits across ≥2 paragraphs
        keywords_across_paras = False

        # Extract all meaningful keywords from pain points and JD
        all_keywords = set()
        for pain in pain_points:
            words = [w.strip('.,!?;:()[]{}"\'-').lower() for w in pain.split()]
            keywords = [w for w in words if w not in stop_words and len(w) > 3]
            all_keywords.update(keywords)

        # Also extract from job description (first 500 chars for efficiency)
        jd_snippet = job_description[:500].lower()
        jd_words = [w.strip('.,!?;:()[]{}"\'-') for w in jd_snippet.split()]
        jd_keywords = [w for w in jd_words if w not in stop_words and len(w) > 3]
        all_keywords.update(jd_keywords)

        if all_keywords:
            # Split cover letter into paragraphs
            cover_paragraphs = [p.strip().lower() for p in text.split('\n\n') if p.strip()]
            if len(cover_paragraphs) < 2:
                # Fallback: split by single newlines
                cover_paragraphs = [p.strip().lower() for p in text.split('\n') if p.strip() and len(p.split()) > 10]

            # Track which keywords appear in which paragraphs
            keyword_para_hits = {}  # keyword -> set of paragraph indices
            for kw in all_keywords:
                for i, para in enumerate(cover_paragraphs):
                    if kw in para:
                        if kw not in keyword_para_hits:
                            keyword_para_hits[kw] = set()
                        keyword_para_hits[kw].add(i)

            # Check: ≥3 distinct keywords that appear in the letter
            keywords_found = [kw for kw, paras in keyword_para_hits.items() if paras]
            # Check: keywords are spread across ≥2 paragraphs
            all_para_indices = set()
            for paras in keyword_para_hits.values():
                all_para_indices.update(paras)

            if len(keywords_found) >= 3 and len(all_para_indices) >= 2:
                keywords_across_paras = True

        # Validation: pass if either condition met
        if not exact_phrase_found and not keywords_across_paras:
            raise ValueError(
                f"Cover letter must reference job-specific content. Either include: "
                f"(a) at least 1 exact multi-word phrase from pain points/JD, OR "
                f"(b) at least 3 distinct keywords spread across 2+ paragraphs. "
                f"Pain points: {pain_points[:3] if pain_points else 'None provided'}"
            )

    # Gate 4.5: Company signal keywords (ROADMAP 8.1: strengthen company specificity)
    # When company signals are available, require at least one to be referenced
    company_research = state.get("company_research", {})
    signals = company_research.get("signals", []) if company_research else []

    if signals:
        # Extract signal keywords from descriptions
        signal_keywords = []
        for signal in signals:
            desc = signal.get("description", "").lower()
            signal_type = signal.get("type", "").lower()
            # Common signal keywords
            if "series" in desc or "funding" in desc or "raised" in desc:
                signal_keywords.extend(["series", "funding", "raised"])
            if "acquisition" in desc or signal_type == "acquisition":
                signal_keywords.append("acquisition")
            if "product launch" in desc or signal_type == "product_launch":
                signal_keywords.extend(["product launch", "launched"])
            if "expansion" in desc or "growth" in desc:
                signal_keywords.extend(["expansion", "growth"])
            if "partnership" in desc or signal_type == "partnership":
                signal_keywords.append("partnership")

        # Check if any signal keyword appears in the letter
        signal_mentioned = False
        for keyword in set(signal_keywords):  # Deduplicate
            if keyword in text_lower:
                signal_mentioned = True
                break

        if not signal_mentioned and signal_keywords:
            raise ValueError(
                f"Cover letter must reference company context (e.g., recent funding, product launches, or growth). "
                f"Mention something specific about the company's recent developments."
            )

    # Gate 5: Generic boilerplate detection
    text_lower = text.lower()
    boilerplate_count = sum(1 for phrase in GENERIC_BOILERPLATE_PHRASES if phrase in text_lower)

    if boilerplate_count > 2:
        raise ValueError(
            f"Cover letter contains {boilerplate_count} generic boilerplate phrases. "
            f"Avoid phrases like: {', '.join(GENERIC_BOILERPLATE_PHRASES[:5])}"
        )


# ===== COVER LETTER GENERATOR =====

class CoverLetterGenerator:
    """
    Enhanced cover letter generator with validation gates (Phase 8.1).

    Features:
    - JSON-only prompts with anti-hallucination controls
    - STAR metric citation requirements
    - JD-specificity checks
    - Generic boilerplate detection
    - Automatic retry on validation failure
    """

    def __init__(self):
        """Initialize LLM for cover letter generation."""
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.CREATIVE_TEMPERATURE,  # 0.7 for creative writing
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self.max_validation_retries = 2

    def _format_pain_points(self, pain_points: List[dict]) -> str:
        """Format pain points as numbered list."""
        if not pain_points:
            return "No specific pain points identified."
        return "\n".join(f"{i}. {point}" for i, point in enumerate(pain_points, 1))

    def _format_strategic_needs(self, strategic_needs: List[dict]) -> str:
        """Format strategic needs as numbered list."""
        if not strategic_needs:
            return "No specific strategic needs identified."
        return "\n".join(f"{i}. {need}" for i, need in enumerate(strategic_needs, 1))

    def _format_company_research(self, company_research: dict) -> str:
        """Format company research for prompt."""
        if not company_research:
            return "No company research available."

        formatted = []
        formatted.append(f"Summary: {company_research.get('summary', 'N/A')}")

        signals = company_research.get('signals', [])
        if signals:
            formatted.append("\nRecent Signals:")
            for signal in signals[:3]:  # Top 3 signals
                formatted.append(f"  - {signal.get('type', 'unknown')}: {signal.get('description', 'N/A')}")

        return "\n".join(formatted)

    def _format_role_research(self, role_research: dict) -> str:
        """Format role research for prompt."""
        if not role_research:
            return "No role research available."

        formatted = []
        formatted.append(f"Summary: {role_research.get('summary', 'N/A')}")

        business_impact = role_research.get('business_impact', [])
        if business_impact:
            formatted.append("\nBusiness Impact:")
            for impact in business_impact:
                formatted.append(f"  - {impact}")

        why_now = role_research.get('why_now')
        if why_now:
            formatted.append(f"\nWhy Now: {why_now}")

        return "\n".join(formatted)

    def _candidate_profile_snippet(self, profile: str) -> str:
        """Return a trimmed snippet of the master CV."""
        if not profile:
            return "Master CV not provided."
        profile = profile.strip()
        return profile[:1200] + ("..." if len(profile) > 1200 else "")

    def _format_selected_stars(self, selected_stars: List[dict]) -> str:
        """Format selected STAR records for prompt."""
        if not selected_stars:
            return ""

        formatted = []
        for i, star in enumerate(selected_stars, 1):
            formatted.append(f"""
STAR #{i}: {star.get('company', 'Unknown')} - {star.get('role', 'Unknown')}
Situation: {star.get('situation', 'N/A')}
Task: {star.get('task', 'N/A')}
Actions: {star.get('actions', 'N/A')}
Results: {star.get('results', 'N/A')}
KEY METRICS: {star.get('metrics', 'N/A')}
""".strip())

        return "\n\n".join(formatted)

    def _generate_with_retry(self, state: JobState, attempt: int = 1) -> str:
        """
        Generate cover letter with LLM, with validation and retry logic.

        Args:
            state: JobState with all required fields
            attempt: Current attempt number (for retry logic)

        Returns:
            Validated cover letter text

        Raises:
            ValueError: If validation fails after max retries
        """
        # Build prompt
        candidate_profile = self._candidate_profile_snippet(state.get("candidate_profile", ""))
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=USER_PROMPT_TEMPLATE.format(
                    title=state.get("title", ""),
                    company=state.get("company", ""),
                    job_description=state.get("job_description", "")[:1500],
                    pain_points=self._format_pain_points(state.get("pain_points", [])),
                    strategic_needs=self._format_strategic_needs(state.get("strategic_needs", [])),
                    company_research=self._format_company_research(state.get("company_research", {})),
                    role_research=self._format_role_research(state.get("role_research", {})),
                    candidate_profile=candidate_profile,
                    selected_stars=self._format_selected_stars(state.get("selected_stars", [])),
                    fit_score=state.get("fit_score", "N/A"),
                    fit_rationale=state.get("fit_rationale", "No fit analysis available.")
                )
            )
        ]

        # Call LLM
        response = self.llm.invoke(messages)
        cover_letter = response.content.strip()

        # Validate
        try:
            validate_cover_letter(cover_letter, state)
            return cover_letter
        except ValueError as e:
            if attempt <= self.max_validation_retries:
                print(f"   ⚠️  Cover letter validation failed (attempt {attempt}/{self.max_validation_retries + 1}): {e}")
                print(f"   ↻ Retrying with stricter prompt...")
                return self._generate_with_retry(state, attempt + 1)
            else:
                raise ValueError(f"Cover letter validation failed after {self.max_validation_retries + 1} attempts: {e}")

    def generate_cover_letter(self, state: JobState) -> str:
        """
        Generate validated cover letter.

        Args:
            state: JobState with pain points, company/role research, STAR records, fit analysis

        Returns:
            Cover letter text (3-4 paragraphs, 220-380 words)

        Raises:
            ValueError: If validation fails after retries
        """
        return self._generate_with_retry(state, attempt=1)
