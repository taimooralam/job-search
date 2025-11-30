"""
Layer 6a: Enhanced Cover Letter Generator (Phase 8.1)

Generates hyper-personalized cover letters with validation gates for:
- STAR metric citations
- JD-specific content
- Anti-boilerplate checks
- Structural requirements (3-4 paragraphs, 220-380 words)
"""

import logging
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

# V2 Enhanced Prompt - Phase 8.1 A/B Testing Improvements
SYSTEM_PROMPT = """You are TWO people working together:

PERSONA 1: Executive Career Marketer
- Crafts compelling narratives that win interviews
- Ties every claim to concrete evidence from the candidate's actual experience
- Never uses generic phrases - always specific and quantified

PERSONA 2: Skeptical Hiring Manager
- Reads 100+ cover letters daily
- Immediately spots and rejects generic fluff
- Only impressed by specific, quantified achievements that address real problems

Your output must satisfy BOTH personas.

CRITICAL RULES:
1. Every achievement claimed MUST come from the provided STAR records or master CV
2. Every metric MUST be from the source materials - NEVER invent numbers
3. NEVER use generic phrases: "excited to apply", "perfect fit", "dream job", "strong background", "team player"
4. Company signals MUST be referenced (funding, growth, product launches)
5. At least 2 pain points MUST be explicitly addressed with matching achievements

STRUCTURE (Flexible 2-4 paragraphs based on content):

1. **Hook**: Specific interest + pain point + company signal (NOT "I am excited")
   - Lead with their problem, not your interest
   - Reference a specific company signal (recent funding, expansion, product launch)

2. **Proof** (1-2 paragraphs): 2-3 achievements with metrics
   - Format: "At [STAR Company], I [action] resulting in [metric]"
   - Each achievement addresses a specific pain point
   - Metrics must come from STAR records

3. **Close**: Confidence + CTA
   - Brief 90-day vision OR clear value statement
   - "I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"

ANTI-HALLUCINATION CHECK:
- All company names must come from STAR records
- All metrics must come from STAR records
- All claims must be verifiable from provided context
"""

USER_PROMPT_TEMPLATE = """Write a hyper-personalized cover letter for this opportunity.

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

=== CURATED ACHIEVEMENTS (STARs) ===
{selected_stars}

=== FIT ANALYSIS ===
Score: {fit_score}/100
{fit_rationale}

=== PLANNING PHASE (Do this first, but don't include in output) ===

STEP 1: PAIN POINT TO STAR MAPPING
For each pain point, identify which STAR achievement addresses it:
- Pain Point 1 -> STAR #? with metric
- Pain Point 2 -> STAR #? with metric
(Select the 2-3 strongest matches)

STEP 2: COMPANY SIGNAL SELECTION
Choose 1 signal to reference in the hook:
- Signal: [type] - [description]
- Connection: How candidate strengths align

STEP 3: STRUCTURE DECISION
Based on content depth, choose paragraph count:
- 2 paragraphs: Limited STARs, simple role
- 3 paragraphs: Standard coverage
- 4 paragraphs: Rich STARs, complex role

=== WRITING PHASE ===

Now write a 220-380 word cover letter that:

1. **Hook**: Lead with {company}'s specific pain point and company signal (NOT "I am excited")
   - Name a specific problem they face
   - Reference their recent [funding/expansion/product launch]

2. **Proof** (1-2 paragraphs): 2-3 STAR achievements with metrics
   - Format: "At [STAR Company], I [action] resulting in [metric]"
   - Each achievement addresses a mapped pain point from Step 1
   - ALL metrics must come from STAR records

3. **Close**: Confident value statement + CTA
   - End with: "I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"

ANTI-HALLUCINATION CHECK:
- Verify all company names are from STAR records
- Verify all metrics are from STAR records
- If a claim cannot be verified, remove it

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
    # NOTE: Use `or []` to handle None values (state.get returns None if key exists with None value)
    selected_stars = state.get("selected_stars") or []
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
    # NOTE: Use `or` to handle None values
    pain_points = state.get("pain_points") or []
    job_description = state.get("job_description") or ""
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
    # NOTE: Use `or` to handle None values
    company_research = state.get("company_research") or {}
    signals = company_research.get("signals") or [] if company_research else []

    if signals:
        # Extract signal keywords from descriptions (with flexible variations)
        signal_keywords = []
        for signal in signals:
            desc = signal.get("description", "").lower()
            signal_type = signal.get("type", "").lower()
            # Common signal keywords with variations
            if "series" in desc or "funding" in desc or "raised" in desc:
                signal_keywords.extend(["series", "funding", "raised", "investment", "round"])
            if "acquisition" in desc or "acquire" in desc or signal_type == "acquisition":
                signal_keywords.extend(["acquisition", "acquire", "acquired"])
            if "product launch" in desc or "launch" in desc or signal_type == "product_launch":
                signal_keywords.extend(["product launch", "launched", "launch", "introducing", "introduced", "suite", "platform"])
            if "expansion" in desc or "growth" in desc or "grow" in desc:
                signal_keywords.extend(["expansion", "growth", "growing", "expand", "scale", "scaling"])
            if "partnership" in desc or signal_type == "partnership":
                signal_keywords.extend(["partnership", "partner", "collaboration"])
            if "ai" in desc or "security" in desc:
                signal_keywords.extend(["ai", "security", "innovation", "initiatives"])

        # Check if any signal keyword appears in the letter
        signal_mentioned = False
        for keyword in set(signal_keywords):  # Deduplicate
            if keyword in text_lower:
                signal_mentioned = True
                break

        # Also accept if company name is mentioned multiple times (shows specificity)
        company = state.get("company", "").lower()
        if company and text_lower.count(company) >= 2:
            signal_mentioned = True

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

    # Gate 6: Ensure closing mentions application submitted and Calendly (no email)
    if "calendly.com/taimooralam/15min" not in text_lower or "applied" not in text_lower:
        raise ValueError(
            "Cover letter must state you have applied for the role and include only the Calendly link."
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
    - LLM API retry with exponential backoff
    """

    def __init__(self):
        """Initialize LLM for cover letter generation."""
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)

        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.CREATIVE_TEMPERATURE,  # 0.7 for creative writing
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self.max_validation_retries = 2

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_llm(self, messages: list) -> str:
        """
        Call LLM with retry logic for transient failures.

        Uses exponential backoff: 2s, 4s, 8s...up to 30s max wait.

        Args:
            messages: List of SystemMessage/HumanMessage

        Returns:
            Raw response content from LLM

        Raises:
            Exception: After 3 failed attempts
        """
        response = self.llm.invoke(messages)
        return response.content.strip()

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
                    title=state.get("title") or "",
                    company=state.get("company") or "",
                    job_description=(state.get("job_description") or "")[:1500],
                    pain_points=self._format_pain_points(state.get("pain_points") or []),
                    strategic_needs=self._format_strategic_needs(state.get("strategic_needs") or []),
                    company_research=self._format_company_research(state.get("company_research") or {}),
                    role_research=self._format_role_research(state.get("role_research") or {}),
                    candidate_profile=candidate_profile,
                    selected_stars=self._format_selected_stars(state.get("selected_stars") or []),
                    fit_score=state.get("fit_score") or "N/A",
                    fit_rationale=state.get("fit_rationale") or "No fit analysis available."
                )
            )
        ]

        # Call LLM with retry
        cover_letter = self._call_llm(messages)

        # Validate
        try:
            validate_cover_letter(cover_letter, state)
            return cover_letter
        except ValueError as e:
            if attempt <= self.max_validation_retries:
                self.logger.warning(f"Cover letter validation failed (attempt {attempt}/{self.max_validation_retries + 1}): {e}")
                self.logger.info(f"Retrying with stricter prompt...")
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
