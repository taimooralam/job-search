"""
Layer 5: People Mapper (Phase 7)

Multi-source contact discovery and classification into primary/secondary buckets.
Generates personalized outreach with length constraints and quality gates.

Phase 7 Enhancements:
- FireCrawl-based discovery (team pages, LinkedIn, Crunchbase)
- Primary vs secondary contact classification
- JSON-only output with Pydantic validation
- Role-based fallback for missing names
- OutreachPackage generation with constraints

Phase 6 Enhancement (JD Annotation System):
- Annotation context for personalized outreach
- Reframe guidance integration for gap/concern handling
- Must-have requirements emphasis in outreach
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from firecrawl import FirecrawlApp

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.state import JobState
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.common.rate_limiter import get_rate_limiter, RateLimitExceededError
from src.common.annotation_types import JDAnnotation, ConcernAnnotation
from src.common.persona_builder import get_persona_guidance
from src.common.claude_web_research import ClaudeWebResearcher, TierType, CLAUDE_MODEL_TIERS


# ===== SAFE NESTED ACCESS HELPER =====

def _safe_get_nested(obj: Any, *keys: str, default: Any = None) -> Any:
    """
    Safely access nested dictionary or object attributes.

    Handles None, dicts, and objects (Pydantic models, TypedDicts) uniformly.
    Returns default if any key in the chain is missing or None.

    Args:
        obj: Object to access (dict, Pydantic model, None, etc.)
        *keys: Keys to access in order (e.g., "company_research", "url")
        default: Default value to return if access fails

    Returns:
        The value at the nested path or default

    Example:
        >>> _safe_get_nested(state, "company_research", "url", default="")
        "https://techcorp.com"
        >>> _safe_get_nested(state, "company_research", "url", default="")
        ""  # if company_research is None
    """
    current = obj
    for key in keys:
        if current is None:
            return default

        # Try dict-style access first
        if isinstance(current, dict):
            current = current.get(key)
        # Then try object attribute access (Pydantic models, TypedDict instances)
        elif hasattr(current, key):
            current = getattr(current, key, None)
        else:
            return default

    # If we got None at the end, return default
    return current if current is not None else default


# ===== FIRECRAWL RESPONSE NORMALIZER =====

def _extract_search_results(search_response: Any) -> List[Any]:
    """
    Normalize FireCrawl search responses across SDK versions into a list of result objects.

    Supports:
      - New client (v4.8.0+): response.web (list of objects with .url / .markdown)
      - Older client (v4.7.x and earlier): response.data
      - Dict responses: {"web": [...]} or {"data": [...]}
      - Bare lists: [ {...}, {...} ]

    Args:
        search_response: Response from FirecrawlApp.search()

    Returns:
        List of search result objects

    Example:
        >>> search_response = app.search("company team")
        >>> results = _extract_search_results(search_response)
        >>> for result in results:
        ...     if hasattr(result, 'markdown'):
        ...         print(result.markdown)
    """
    if not search_response:
        return []

    # Attribute-based shapes (Pydantic models)
    # New SDK v4.8.0+: response.web, response.news, response.images
    results = getattr(search_response, "web", None)
    if results is None and hasattr(search_response, "data"):
        # Older SDK: response.data
        results = getattr(search_response, "data", None)

    # Dict shape (for test mocks or API changes)
    if results is None and isinstance(search_response, dict):
        results = (
            search_response.get("web")
            or search_response.get("data")
            or search_response.get("results")
        )

    # Bare list shape (unlikely but defensive)
    if results is None and isinstance(search_response, list):
        results = search_response

    return results or []


# ===== QUERY TEMPLATES (Option A - SEO-style) =====

# Targeted query patterns that work reliably with FireCrawl search
# These use site operators and boolean logic to get better results than natural language queries
QUERY_TEMPLATES = {
    "recruiters": 'site:linkedin.com/in "{company}" {department} recruiter',
    "recruiters_alt": 'site:linkedin.com/in "{company}" talent acquisition',
    "leadership": '"{company}" ("VP {department}" OR "Director {department}" OR "Head of {department}") LinkedIn',
    "hiring_manager": '"{company}" "{title}" (hiring manager OR engineering manager) LinkedIn',
    "senior_leadership": '"{company}" (CTO OR "Chief Technology Officer" OR "VP Engineering") LinkedIn',
}


# ===== CONSTANTS =====

# Maximum total contacts to return (GAP-060 fix)
# Prioritizes primary contacts (hiring-related) over secondary
MAX_TOTAL_CONTACTS = 5

# GAP-051: Common company name suffixes to strip for variations
COMPANY_SUFFIXES = [
    ' Inc.', ' Inc', ' LLC', ' Ltd.', ' Ltd', ' Corp.', ' Corp',
    ' Co.', ' Co', ' Limited', ' GmbH', ' AG', ' S.A.', ' PLC',
    ' Pty Ltd', ' Pty', ' Holdings', ' Group', ' International'
]

# GAP-051: Expanded team page paths to check
TEAM_PAGE_PATHS = [
    '/team', '/about', '/about-us', '/leadership', '/company',
    '/people', '/our-team', '/founders', '/executives', '/management',
    '/about/team', '/about/leadership', '/who-we-are', '/meet-the-team'
]

# ===== CONTACT TYPE CLASSIFICATION (linkedin/outreach.md) =====

# Keywords for classifying contact types (order matters - checked in priority)
CONTACT_TYPE_KEYWORDS = {
    "executive": [
        "cto", "ceo", "cfo", "coo", "chief", "c-suite",
        "founder", "co-founder", "cofounder", "president"
    ],
    "vp_director": [
        "vp ", "vp,", "vice president", "director", "head of",
        "senior director", "svp", "evp", "principal director",
        "department head", "general manager"
    ],
    "hiring_manager": [
        "hiring manager", "engineering manager", "team lead", "tech lead",
        "software development manager", "manager software", "manager,",
        "development manager", "delivery manager", "project manager"
    ],
    "recruiter": [
        "recruiter", "talent acquisition", "ta ", "talent partner",
        "sourcer", "recruiting", "hr business partner", "people partner",
        "talent ", "staffing"
    ],
    "peer": [
        "staff engineer", "principal engineer", "senior engineer",
        "lead engineer", "architect", "developer", "software engineer"
    ]
}

# Calendly link for connection messages (from linkedin/outreach.md)
CALENDLY_LINK = "calendly.com/taimooralam/15min"
CONNECTION_MESSAGE_HARD_LIMIT = 300  # LinkedIn enforced limit

# "Already applied" frames (from linkedin/outreach.md)
ALREADY_APPLIED_FRAMES = [
    "adding_context",    # "I submitted my application and wanted to share context..."
    "value_add",         # "Following up on my application—I came across..."
    "specific_interest"  # "I applied for [Role] because [specific reason]..."
]


def classify_contact_type(role: str) -> str:
    """
    Classify contact type based on role title keywords.

    Priority order: executive > vp_director > hiring_manager > recruiter > peer

    Args:
        role: Job title/role string

    Returns:
        ContactType string: "hiring_manager", "recruiter", "vp_director", "executive", "peer"
    """
    role_lower = role.lower()

    # Check in priority order
    for contact_type in ["executive", "vp_director", "hiring_manager", "recruiter", "peer"]:
        for keyword in CONTACT_TYPE_KEYWORDS[contact_type]:
            if keyword in role_lower:
                return contact_type

    # Default to peer if no match
    return "peer"


def get_company_name_variations(company: str) -> List[str]:
    """
    GAP-051: Generate variations of company name for better search matching.

    Args:
        company: Original company name

    Returns:
        List of company name variations (original first, then without suffixes)
    """
    variations = [company]

    # Try stripping common suffixes
    company_lower = company.lower()
    for suffix in COMPANY_SUFFIXES:
        if company_lower.endswith(suffix.lower()):
            stripped = company[:-len(suffix)].strip()
            if stripped and stripped not in variations:
                variations.append(stripped)
            break  # Only strip one suffix

    # Also try without trailing punctuation
    if company.endswith('.') or company.endswith(','):
        stripped = company[:-1].strip()
        if stripped and stripped not in variations:
            variations.append(stripped)

    return variations


# ===== PYDANTIC MODELS =====

class ContactModel(BaseModel):
    """
    Pydantic model for contact validation (Phase 7).

    Enforces required fields and structure for JSON-only output.
    """
    name: str = Field(..., min_length=1, description="Contact name or role-based identifier")
    role: str = Field(..., min_length=1, description="Job title/role")
    linkedin_url: str = Field(..., description="LinkedIn profile or company people page")
    why_relevant: str = Field(..., min_length=20, description="Specific reason this contact matters")
    recent_signals: List[str] = Field(default_factory=list, description="Recent posts, promotions, projects")
    is_synthetic: bool = Field(default=False, description="True if synthetic placeholder contact")

    @field_validator('name')
    @classmethod
    def name_not_generic(cls, v):
        """Ensure name is not overly generic."""
        generic_names = ["Unknown", "TBD", "N/A", "Contact"]
        if v in generic_names:
            raise ValueError(f"Name cannot be generic placeholder: {v}")
        return v


class PeopleMapperOutput(BaseModel):
    """
    Pydantic model for People Mapper JSON output (Phase 7).

    Enforces quality gates:
    - 4-6 primary contacts (hiring-related roles)
    - 4-6 secondary contacts (cross-functional, peers)
    """
    primary_contacts: List[ContactModel] = Field(
        ...,
        min_length=4,
        max_length=6,
        description="Hiring manager, recruiter, department head, team lead"
    )
    secondary_contacts: List[ContactModel] = Field(
        ...,
        min_length=4,
        max_length=6,
        description="Cross-functional partners, peers, executive sponsors"
    )

    @field_validator('primary_contacts', 'secondary_contacts')
    @classmethod
    def validate_contact_list(cls, v, info):
        """Validate contact list meets quality gates."""
        if len(v) < 4:
            raise ValueError(f"{info.field_name} must have at least 4 contacts (quality gate)")
        if len(v) > 6:
            raise ValueError(f"{info.field_name} must have at most 6 contacts (quality gate)")
        return v


# ===== PROMPTS =====

SYSTEM_PROMPT_CLASSIFICATION = """You are an expert recruiter specializing in identifying hiring contacts.

Your task: Classify contacts into PRIMARY (hiring-related) and SECONDARY (cross-functional) buckets.

PRIMARY CONTACTS (4-6):
- Hiring manager (direct manager for the role)
- Department heads (VP Engineering, Director of X, etc.)
- Team leads (Engineering Manager, Tech Lead, etc.)
- Recruiters/Talent Acquisition

SECONDARY CONTACTS (4-6):
- Cross-functional partners (Product, Design, Sales)
- Peer roles (other engineers, adjacent teams)
- Executive sponsors (CEO, CTO, Founders)
- Related stakeholders (DevOps, Security, Data)

Output JSON ONLY. No explanatory text before or after."""

USER_PROMPT_CLASSIFICATION_TEMPLATE = """Classify contacts for this job opportunity:

=== JOB ===
Title: {title}
Company: {company}

Job Description:
{job_description}

=== COMPANY RESEARCH ===
{company_research_summary}

=== ROLE RESEARCH ===
{role_research_summary}

=== PAIN POINTS ===
{pain_points}

=== SCRAPED CONTACTS (from FireCrawl) ===
{raw_contacts}

=== YOUR TASK ===
Based on the above context, classify contacts into PRIMARY and SECONDARY buckets.

**REQUIREMENTS:**
- PRIMARY: 4-6 contacts directly involved in hiring (manager, recruiter, team lead, department head)
- SECONDARY: 4-6 contacts for cross-functional outreach (product partners, peers, executives)
- For each contact, provide:
  - name: Full name OR role-based identifier (e.g., "VP Engineering at {company}")
  - role: Job title
  - linkedin_url: Profile URL or company people page
  - why_relevant: Specific reason (20+ chars, not generic)
  - recent_signals: List of recent activities (from company research or empty list)
- If no real names found, use role-based identifiers: "<job_title> at {company}"
- Ground why_relevant in job requirements and company context

Output JSON format:
{{
  "primary_contacts": [
    {{
      "name": "...",
      "role": "...",
      "linkedin_url": "...",
      "why_relevant": "...",
      "recent_signals": [...]
    }}
  ],
  "secondary_contacts": [...]
}}"""

SYSTEM_PROMPT_OUTREACH = """You are an expert career strategist crafting personalized outreach messages.

Your task: Generate THREE outreach formats per contact, tailored to their contact_type:
1. LinkedIn Connection Request (≤300 chars INCLUDING Calendly link)
2. LinkedIn InMail (400-600 chars with subject)
3. Email (subject + body)

**CONTACT TYPE CUSTOMIZATION (from linkedin/outreach.md):**
- RECRUITER: Skills-focused, match job requirements, quantified achievements, transactional but warm
- HIRING_MANAGER: Team fit, technical depth, business impact, peer-level thinking, reference their projects
- VP_DIRECTOR: Strategic outcomes, 50-150 words max, reference company initiatives
- EXECUTIVE: Extreme brevity (<100 words), strategic framing, industry trends
- PEER: Technical credibility, shared challenges, collaborative tone

**"ALREADY APPLIED" FRAMING (MANDATORY in all messages):**
Every message MUST reference that the candidate has already applied using one of these frames:
1. "adding_context": "I submitted my application for [Role] and wanted to share context..."
2. "value_add": "Following up on my application for [Role]—I came across..."
3. "specific_interest": "I applied for [Role] because [specific reason]..."

=== LINKEDIN CONNECTION REQUEST - HARD 300 CHARACTER LIMIT ===
- STRICT 300 character limit enforced by LinkedIn
- MUST include Calendly link: calendly.com/taimooralam/15min
- This leaves ~250 chars for message content
- End with "Best. Taimoor Alam"
- COUNT CHARACTERS before responding

=== LINKEDIN INMAIL (longer format) ===
- Subject line: 25-30 characters for mobile display
- Body: 400-600 characters
- Include 1-2 concrete metrics from candidate's experience
- Reference company signals when available
- End with Calendly link and signature

=== EMAIL ===
- Subject: 5-10 words, ≤100 characters, pain-focused
- Body: 95-205 words (target 120-150)
- Include 2-3 achievements with metrics
- Reference company context

**PHASE 9 CONTENT CONSTRAINTS (CRITICAL):**
- NO EMOJIS in any message
- NO GENERIC PLACEHOLDERS like "[Company]", "[Date]"
- Use actual contact name or role-based addressee (e.g., "VP Engineering at Stripe")
- Be direct, technical, and metric-driven

**PHASE 6 ANNOTATION GUIDANCE (when provided):**
When "ANNOTATION CONTEXT" section is included in the prompt:
- Apply REFRAME GUIDANCE to position experience using JD-aligned terminology
- Prioritize MUST-HAVE requirements in your messaging
- Include ANNOTATION KEYWORDS for relevance signaling
- Address CONCERNS proactively with mitigation framing (but keep message positive)
- Use linked STAR metrics as evidence for claims"""

USER_PROMPT_OUTREACH_TEMPLATE = """Generate personalized outreach for this contact:

=== CONTACT ===
Name: {contact_name}
Role: {contact_role}
Contact Type: {contact_type}
Why Relevant: {contact_why}
Recent Signals: {contact_signals}

=== JOB ===
Title: {job_title}
Company: {company}
Already Applied: YES (candidate has submitted application)

Pain Points:
{pain_points}

Company Context:
{company_research_summary}

=== CANDIDATE EVIDENCE (Master CV or curated achievements) ===
{selected_stars_summary}

{annotation_context}=== YOUR TASK ===
Generate outreach TAILORED to {contact_type} contact type:
1. Use "already applied" framing in all messages
2. Reference at least one concrete metric from candidate's experience
3. Address job pain points with achievements from evidence
4. Show awareness of company context (funding, growth, timing)
5. Personalize to this contact's role and recent signals

**CRITICAL: Count characters/words carefully before outputting!**

Output JSON format:
{{
  "linkedin_connection_message": "...",  // HARD ≤300 chars WITH Calendly link (calendly.com/taimooralam/15min). End with "Best. Taimoor Alam"
  "linkedin_inmail_subject": "...",      // 25-30 chars for mobile
  "linkedin_inmail": "...",              // 400-600 chars, include metric, end with Calendly + signature
  "email_subject": "...",                // 5-10 words, ≤100 chars, pain-focused
  "email_body": "...",                   // 95-205 words, cite 2-3 achievements
  "already_applied_frame": "..."         // Which frame used: "adding_context", "value_add", or "specific_interest"
}}

=== EXAMPLES BY CONTACT TYPE ===

**RECRUITER Connection (298 chars):**
"Hi [Name], applied for [Role] at [Company]. 11+ yrs scaling distributed systems & leading teams of 40+. Would love to share how I reduced incidents 75% at [PrevCo]. calendly.com/taimooralam/15min Best. Taimoor Alam"

**HIRING_MANAGER Connection (295 chars):**
"Hi [Name], applied for [Role]. Led 12→45 engineer scaling with 92% retention. Your team's work on [specific] aligns with my experience. Let's connect: calendly.com/taimooralam/15min Best. Taimoor Alam"

**VP_DIRECTOR Connection (290 chars):**
"Hi [Name], applied for [Role]. Built eng orgs through 3x growth, drove $2.4M infra savings. Would value discussing your priorities: calendly.com/taimooralam/15min Best. Taimoor Alam"

**VALIDATION CHECKLIST** (output rejected if these fail):
- ✓ linkedin_connection_message: ≤300 chars, INCLUDES calendly.com/taimooralam/15min, ends with "Best. Taimoor Alam"
- ✓ linkedin_inmail: 400-600 chars, includes subject (25-30 chars)
- ✓ email_subject: 5-10 words, pain-focused
- ✓ email_body: 95-205 words, cites metrics
- ✓ All messages use "already applied" framing
- ✓ NO emojis, NO generic placeholders"""


class PeopleMapper:
    """
    Phase 7: Enhanced People Mapper with multi-source discovery and classification.

    Supports two discovery backends:
    - Claude API (default): Uses Claude API with WebSearch for contact discovery
    - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility
    """

    def __init__(
        self,
        tier: TierType = "balanced",
        use_claude_api: bool = True,
    ):
        """
        Initialize the People Mapper.

        Args:
            tier: Claude model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus).
                  Only used when use_claude_api=True. Default is "balanced" (Sonnet 4.5).
            use_claude_api: If True (default), use Claude API with WebSearch for contact discovery.
                           If False, use FireCrawl (legacy mode).
                           Note: Classification and outreach always use OpenRouter LLM regardless
                           of this setting (Phase 1 only migrates discovery).
        """
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)
        self.tier = tier
        self.use_claude_api = use_claude_api

        # GAP-066: Token tracking enabled
        # LLM is always needed for classification and outreach generation
        # (even when using Claude API for discovery)
        self.llm = create_tracked_llm(
            model=Config.DEFAULT_MODEL,
            temperature=0.4,  # Slightly creative for outreach
            layer="layer5",
        )

        # Claude API for contact discovery (new backend)
        self.claude_researcher = None
        if use_claude_api:
            self.claude_researcher = ClaudeWebResearcher(tier=tier)
            self.logger.info(f"[Claude API] People Mapper initialized with tier={tier}")

        # FireCrawl for contact discovery (legacy backend, or fallback)
        self.firecrawl_disabled = Config.DISABLE_FIRECRAWL_OUTREACH or not Config.FIRECRAWL_API_KEY
        self.firecrawl = None
        self.firecrawl_rate_limiter = None
        if not self.firecrawl_disabled:
            self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)
            # Initialize rate limiter for FireCrawl credit tracking
            self.firecrawl_rate_limiter = get_rate_limiter("firecrawl")

    def _firecrawl_search(self, query: str, limit: int = 5) -> Any:
        """
        Perform a rate-limited FireCrawl search.

        Tracks usage against daily limit and logs credit consumption.

        Args:
            query: Search query string
            limit: Maximum results to return

        Returns:
            FireCrawl search response

        Raises:
            RateLimitExceededError: If daily FireCrawl limit exceeded
        """
        if self.firecrawl_rate_limiter:
            # Check remaining credits before search
            remaining = self.firecrawl_rate_limiter.get_remaining_daily()
            if remaining is not None and remaining <= 0:
                self.logger.warning(
                    f"[FireCrawl] Daily limit exhausted (0/{self.firecrawl_rate_limiter.daily_limit})"
                )
                raise RateLimitExceededError(
                    "firecrawl", "daily",
                    self.firecrawl_rate_limiter.daily_limit,
                    self.firecrawl_rate_limiter.daily_limit
                )

            # Acquire rate limit slot (tracks the request)
            if not self.firecrawl_rate_limiter.acquire():
                self.logger.warning("[FireCrawl] Rate limit exceeded, request blocked")
                raise RateLimitExceededError(
                    "firecrawl", "daily",
                    self.firecrawl_rate_limiter._daily_count,
                    self.firecrawl_rate_limiter.daily_limit
                )

            # Log credit consumption
            stats = self.firecrawl_rate_limiter.get_stats()
            self.logger.info(
                f"[FireCrawl] Credit used: {stats.requests_today}/{self.firecrawl_rate_limiter.daily_limit} "
                f"({self.firecrawl_rate_limiter.get_remaining_daily()} remaining)"
            )

        return self.firecrawl.search(query, limit=limit)

    # ===== CONTACT EXTRACTION FROM SEARCH METADATA =====

    def _extract_contact_from_search_result(self, result: Any, company: str) -> Optional[Dict[str, str]]:
        """
        Extract contact info from FireCrawl search result metadata (Option A).

        FireCrawl search returns {url, title, description} - we extract contact info from these
        fields instead of trying to scrape the full page (which often fails for LinkedIn).

        Args:
            result: Search result object/dict with url, title, description
            company: Company name for validation

        Returns:
            Dict with name, role, linkedin_url, source or None

        Example title: "Tanya Chen - VP | Head of Engineering @ Atlassian, ex-Meta"
        Example description: "VP | Head of Engineering @ Atlassian · Experience: Atlassian..."
        """
        # Extract fields (handle both object attributes and dict keys)
        url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)
        title = getattr(result, "title", None) or (result.get("title") if isinstance(result, dict) else None)
        description = getattr(result, "description", None) or (result.get("description") if isinstance(result, dict) else None)

        if not url or not title:
            return None

        # Only process LinkedIn URLs
        if "linkedin.com/in" not in url.lower():
            return None

        # Parse name from LinkedIn title pattern: "Name - Title at Company" or "Name | Title"
        name = None
        role = None

        # Pattern 1: "Name - Title" or "Name | Title"
        if " - " in title or " | " in title:
            separator = " - " if " - " in title else " | "
            parts = title.split(separator, 1)
            name = parts[0].strip()

            # Extract role from remaining title or description
            if len(parts) > 1:
                role_text = parts[1]
                # Remove "LinkedIn" suffix and clean up
                role = re.sub(r'\s*\|\s*LinkedIn\s*$', '', role_text).strip()
                # If role contains company name or "at", extract just the title
                if " at " in role.lower():
                    role = role.split(" at ")[0].strip()
                elif " @ " in role:
                    role = role.split(" @ ")[0].strip()

        # If no name extracted yet, try simpler pattern
        if not name:
            # Sometimes format is just "Name Title"
            words = title.split()
            if len(words) >= 2:
                # Assume first 2-3 words are name
                name = " ".join(words[:2])

        # Extract role from description if not found in title
        if not role and description:
            # Look for job titles in description
            desc_lower = description.lower()
            if " at " + company.lower() in desc_lower or " @ " + company.lower() in desc_lower:
                # Try to extract title before "at Company"
                for separator in [" at ", " @ "]:
                    if separator + company.lower() in desc_lower:
                        parts = description.split(separator, 1)
                        if parts:
                            # Get last sentence/phrase before the separator
                            potential_role = parts[0].split("·")[-1].strip()
                            if len(potential_role) < 100:  # Sanity check
                                role = potential_role
                                break

        # Default role if still not found
        if not role:
            role = "Contact"

        # Validate we have a reasonable name
        if not name or len(name) < 2 or len(name) > 100:
            return None

        return {
            "name": name,
            "role": role,
            "linkedin_url": url,
            "source": "linkedin_search"
        }

    # ===== FIRECRAWL MULTI-SOURCE DISCOVERY =====

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _scrape_company_team_page(self, company: str, company_url: str) -> Optional[str]:
        """
        Scrape company team/about page for contact names and roles.

        Args:
            company: Company name
            company_url: Company website URL

        Returns:
            Markdown content from team page (or None)
        """
        if self.firecrawl_disabled or not self.firecrawl:
            return None
        try:
            # GAP-051: Use expanded team page paths for better coverage
            team_urls = [f"{company_url.rstrip('/')}{path}" for path in TEAM_PAGE_PATHS]

            for url in team_urls:
                try:
                    result = self.firecrawl.scrape_url(
                        url,
                        params={'formats': ['markdown'], 'onlyMainContent': True}
                    )
                    if result and hasattr(result, 'markdown'):
                        # Limit to 2000 chars
                        return result.markdown[:2000]
                except Exception:
                    # URL not found or scraping failed - try next URL
                    continue

            return None

        except Exception as e:
            self.logger.warning(f"Team page scraping failed: {e}")
            return None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _search_linkedin_contacts(
        self,
        company: str,
        department: str = "engineering",
        title: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Search LinkedIn for company employees using FireCrawl search (Option A - improved).

        Uses SEO-style queries and extracts contacts from search result metadata
        instead of trying to scrape LinkedIn pages (which often fails).

        Args:
            company: Company name
            department: Department to search (e.g., "engineering", "product")
            title: Specific job title to target (optional)

        Returns:
            List of contact dicts with name, role, linkedin_url, source
        """
        if self.firecrawl_disabled or not self.firecrawl:
            return []

        contacts = []

        try:
            # GAP-051: Try company name variations for better matching
            company_variations = get_company_name_variations(company)
            self.logger.info(f"[GAP-051] Company variations: {company_variations}")

            for company_variant in company_variations:
                # Run multiple targeted queries
                queries = [
                    QUERY_TEMPLATES["recruiters"].format(company=company_variant, department=department),
                    QUERY_TEMPLATES["recruiters_alt"].format(company=company_variant),
                    QUERY_TEMPLATES["leadership"].format(company=company_variant, department=department),
                ]

                if title:
                    queries.append(QUERY_TEMPLATES["hiring_manager"].format(company=company_variant, title=title))

                for query in queries:
                    try:
                        self.logger.info(f"[FireCrawl] LinkedIn query: {query[:80]}...")
                        search_response = self._firecrawl_search(query, limit=5)

                        # GAP-051: Log result count for debugging
                        results = _extract_search_results(search_response)
                        self.logger.info(f"[FireCrawl] Got {len(results)} results")

                        # Extract contacts from metadata
                        for result in results:
                            contact = self._extract_contact_from_search_result(result, company)
                            if contact:
                                contacts.append(contact)
                                self.logger.info(f"Found: {contact['name']} - {contact['role']}")

                    except Exception as e:
                        self.logger.warning(f"Query failed: {e}")
                        continue

                # GAP-051: If we found contacts with this variation, don't try others
                if contacts:
                    self.logger.info(f"[GAP-051] Found {len(contacts)} contacts using '{company_variant}'")
                    break

            self.logger.info(f"Found {len(contacts)} contacts from LinkedIn search")
            return contacts

        except Exception as e:
            self.logger.warning(f"LinkedIn search failed: {e}")
            return []

    def _build_annotation_enhanced_queries(
        self,
        company: str,
        title: str,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Phase 8 (GAP-086): Build enhanced SEO queries using annotation keywords.

        Uses must_have keywords from JD annotations to find contacts with
        relevant technical expertise.

        Args:
            company: Company name
            title: Job title
            jd_annotations: JD annotations dict with annotations list

        Returns:
            List of enhanced query strings for FireCrawl search
        """
        if not jd_annotations:
            return []

        annotations = jd_annotations.get("annotations", [])
        if not annotations:
            return []

        # Extract must_have keywords
        keywords = []
        for ann in annotations:
            if ann.get("requirement_type") == "must_have" and ann.get("is_active", True):
                # Get keyword from matching_skill or suggested_keywords
                skill = ann.get("matching_skill")
                if skill:
                    keywords.append(skill)
                else:
                    suggested = ann.get("suggested_keywords", [])
                    if suggested:
                        keywords.append(suggested[0])

        if not keywords:
            return []

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique_keywords.append(kw)

        queries = []

        # Build queries with top 3 keywords
        top_keywords = unique_keywords[:3]
        if top_keywords:
            # Query 1: LinkedIn engineers with these skills
            keyword_or = " OR ".join(f'"{kw}"' for kw in top_keywords)
            queries.append(
                f'site:linkedin.com/in "{company}" ({keyword_or}) engineer'
            )

            # Query 2: Technical leadership with these skills
            if len(top_keywords) >= 2:
                queries.append(
                    f'site:linkedin.com/in "{company}" ({top_keywords[0]} OR {top_keywords[1]}) "tech lead" OR "engineering manager"'
                )

        self.logger.info(f"[Phase 8] Built {len(queries)} annotation-enhanced queries using keywords: {top_keywords}")
        return queries

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _search_hiring_manager(self, company: str, title: str) -> List[Dict[str, str]]:
        """
        Search for hiring manager using job title + company (Option A - improved).

        Uses SEO-style queries and extracts contacts from search result metadata.

        Args:
            company: Company name
            title: Job title

        Returns:
            List of contact dicts with name, role, linkedin_url, source
        """
        if self.firecrawl_disabled or not self.firecrawl:
            return []

        contacts = []

        try:
            # Use targeted query for senior leadership
            query = QUERY_TEMPLATES["senior_leadership"].format(company=company)
            self.logger.info(f"[FireCrawl] Hiring manager query: {query[:80]}...")

            search_response = self._firecrawl_search(query, limit=5)
            results = _extract_search_results(search_response)

            # Extract contacts from metadata
            for result in results:
                contact = self._extract_contact_from_search_result(result, company)
                if contact:
                    contacts.append(contact)
                    self.logger.info(f"Found: {contact['name']} - {contact['role']}")

            self.logger.info(f"Found {len(contacts)} senior contacts")
            return contacts

        except Exception as e:
            self.logger.warning(f"Hiring manager search failed: {e}")
            return []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _search_crunchbase_team(self, company: str) -> Optional[str]:
        """
        Search Crunchbase for company team information using FireCrawl search.

        Args:
            company: Company name

        Returns:
            Markdown content from Crunchbase team page
        """
        if self.firecrawl_disabled or not self.firecrawl:
            return None
        try:
            # LLM-style query focusing on leadership team information
            query = (
                f"{company} leadership team on Crunchbase "
                f"(VP Engineering, CTO, Head of Talent, Directors)"
            )
            self.logger.info(f"[FireCrawl] Crunchbase search query: {query[:80]}...")
            search_response = self._firecrawl_search(query, limit=2)

            # Use normalizer to extract results (handles SDK version differences)
            results = _extract_search_results(search_response)

            if results:
                # Find Crunchbase URL
                for result in results:
                    # Defensive URL extraction (handles both object attributes and dict keys)
                    url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)

                    if url and 'crunchbase.com' in url.lower():
                        # Return markdown content (handle both attribute and dict access)
                        markdown = getattr(result, 'markdown', None) or (result.get('markdown') if isinstance(result, dict) else None)
                        if markdown:
                            return markdown[:1500]

            return None

        except Exception as e:
            self.logger.warning(f"Crunchbase team search failed: {e}")
            return None

    def _deduplicate_contacts(self, raw_contacts: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Deduplicate contacts found across multiple sources.

        Args:
            raw_contacts: List of contact dicts with name, role, source

        Returns:
            Deduplicated list (keeps first occurrence)
        """
        seen_names = set()
        deduplicated = []

        for contact in raw_contacts:
            name = contact.get("name", "").strip().lower()
            if name and name not in seen_names:
                seen_names.add(name)
                deduplicated.append(contact)

        return deduplicated

    def _limit_contacts(
        self,
        primary_contacts: List[Dict],
        secondary_contacts: List[Dict],
        max_total: int = MAX_TOTAL_CONTACTS
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Limit total contacts to max_total, prioritizing primary contacts (GAP-060).

        Strategy:
        - Primary contacts (hiring-related) are more valuable for job search
        - Keep up to 3 primary contacts first
        - Fill remaining slots with secondary contacts
        - Ensures we don't exceed max_total (default: 5)

        Args:
            primary_contacts: List of primary (hiring-related) contacts
            secondary_contacts: List of secondary (cross-functional) contacts
            max_total: Maximum total contacts to return (default: 5)

        Returns:
            Tuple of (limited_primary, limited_secondary)
        """
        # Prioritize primary contacts (up to 3)
        max_primary = min(3, len(primary_contacts), max_total)
        limited_primary = primary_contacts[:max_primary]

        # Fill remaining slots with secondary contacts
        remaining_slots = max_total - len(limited_primary)
        limited_secondary = secondary_contacts[:remaining_slots]

        total = len(limited_primary) + len(limited_secondary)
        self.logger.info(
            f"Limited contacts: {len(primary_contacts)} primary + {len(secondary_contacts)} secondary "
            f"-> {len(limited_primary)} primary + {len(limited_secondary)} secondary "
            f"(total: {total}/{max_total})"
        )

        return limited_primary, limited_secondary

    def _generate_agency_recruiter_contacts(self, state: JobState) -> Dict[str, List[Dict]]:
        """
        Generate 2 recruiter contacts for recruitment agency jobs.

        For agencies, we only need to contact the recruiters handling this specific role,
        not the hiring company (which is unknown for agency postings).

        Args:
            state: JobState with company (agency name) and title info

        Returns:
            Dict with primary_contacts (2 recruiters) and secondary_contacts (empty)
        """
        agency = state.get("company") or "the agency"
        title = state.get("title") or "this role"
        agency_url = _safe_get_nested(
            state, "company_research", "url",
            default=f"https://linkedin.com/company/{agency.lower().replace(' ', '-')}"
        )

        # 2 recruiters for agency jobs
        recruiter_templates = [
            {
                "role": "Recruiter",
                "why": f"Primary recruiting contact sourcing candidates for {title}"
            },
            {
                "role": "Account Manager",
                "why": f"Manages client relationship for the {title} position at {agency}"
            },
        ]

        primary_contacts = []
        for template in recruiter_templates:
            primary_contacts.append({
                "name": f"{template['role']} at {agency}",
                "role": template["role"],
                "linkedin_url": f"{agency_url}/people",
                "why_relevant": template["why"],
                "recent_signals": [],
                "is_synthetic": True
            })

        return {
            "primary_contacts": primary_contacts,
            "secondary_contacts": []  # No secondary contacts for agencies
        }

    def _generate_synthetic_contacts(self, state: JobState) -> Dict[str, List[Dict]]:
        """
        Generate 3 minimal role-based synthetic contacts when FireCrawl discovery fails.

        Returns 2 primary contacts and 1 secondary contact as a minimal fallback.
        This bypasses the quality gate (which requires 4+4) for synthetic contacts.

        Args:
            state: JobState with company and title info

        Returns:
            Dict with primary_contacts (2) and secondary_contacts (1) lists
        """
        company = state.get("company") or "the company"
        title = state.get("title") or "this role"
        company_url = _safe_get_nested(
            state, "company_research", "url",
            default=f"https://linkedin.com/company/{company.lower().replace(' ', '-')}"
        )

        # 2 essential primary contacts (minimal fallback)
        primary_templates = [
            {"role": "Hiring Manager", "why": f"Direct decision-maker for {title} at {company}"},
            {"role": "Technical Recruiter", "why": f"Primary recruiting contact for engineering roles at {company}"},
        ]

        # 1 essential secondary contact (minimal fallback)
        secondary_templates = [
            {"role": "Engineering Director", "why": f"Technical leader overseeing teams related to {title} at {company}"},
        ]

        primary_contacts = []
        for template in primary_templates:
            primary_contacts.append({
                "name": f"{template['role']} at {company}",
                "role": template["role"],
                "linkedin_url": f"{company_url}/people",
                "why_relevant": template["why"],
                "recent_signals": [],
                "is_synthetic": True
            })

        secondary_contacts = []
        for template in secondary_templates:
            secondary_contacts.append({
                "name": f"{template['role']} at {company}",
                "role": template["role"],
                "linkedin_url": f"{company_url}/people",
                "why_relevant": template["why"],
                "recent_signals": [],
                "is_synthetic": True
            })

        return {
            "primary_contacts": primary_contacts,
            "secondary_contacts": secondary_contacts
        }

    def _discover_contacts(self, state: JobState) -> Tuple[str, bool]:
        """
        Multi-source contact discovery using FireCrawl (Phase 7.2.2 - Option A improved).

        Uses SEO-style queries and extracts contacts from search result metadata
        instead of relying on markdown scraping.

        Queries:
        1. Company team/about page (legacy scraping)
        2. LinkedIn recruiter search (metadata extraction)
        3. LinkedIn leadership search (metadata extraction)
        4. Hiring manager search (metadata extraction)
        5. Crunchbase team (legacy scraping)

        Returns:
            Tuple of (formatted contact data for LLM, found_any_contacts)
        """
        if self.firecrawl_disabled or not self.firecrawl:
            self.logger.info("FireCrawl outreach discovery disabled (role-based contacts only)")
            return "FireCrawl discovery is disabled. Use role-based identifiers.", False

        company = state.get("company", "")
        title = state.get("title", "")
        company_url = _safe_get_nested(state, "company_research", "url", default="")

        all_contacts = []
        raw_content_parts = []

        self.logger.info("Discovering contacts from multiple sources (Option A - improved)")

        # Source 1: Company team page (legacy - still useful for smaller companies)
        team_page = self._scrape_company_team_page(company, company_url)
        if team_page:
            raw_content_parts.append(f"[SOURCE: Company Team Page]\n{team_page}\n")
            self.logger.info(f"Scraped company team page ({len(team_page)} chars)")

        # Source 2: LinkedIn contacts (recruiters + leadership)
        linkedin_contacts = self._search_linkedin_contacts(company, "engineering", title)
        if linkedin_contacts:
            all_contacts.extend(linkedin_contacts)
            # Format for LLM
            contact_strs = [
                f"- {c['name']} ({c['role']}) - {c['linkedin_url']}"
                for c in linkedin_contacts
            ]
            raw_content_parts.append(f"[SOURCE: LinkedIn Search]\n" + "\n".join(contact_strs) + "\n")

        # Source 3: Hiring managers / senior leadership
        manager_contacts = self._search_hiring_manager(company, title)
        if manager_contacts:
            all_contacts.extend(manager_contacts)
            # Format for LLM
            contact_strs = [
                f"- {c['name']} ({c['role']}) - {c['linkedin_url']}"
                for c in manager_contacts
            ]
            raw_content_parts.append(f"[SOURCE: Senior Leadership Search]\n" + "\n".join(contact_strs) + "\n")

        # Source 4: Crunchbase team (legacy)
        crunchbase_content = self._search_crunchbase_team(company)
        if crunchbase_content:
            raw_content_parts.append(f"[SOURCE: Crunchbase Team]\n{crunchbase_content}\n")
            self.logger.info(f"Searched Crunchbase team ({len(crunchbase_content)} chars)")

        # Source 5 (Phase 8 - GAP-086): Annotation-enhanced queries
        jd_annotations = state.get("jd_annotations")
        if jd_annotations:
            enhanced_queries = self._build_annotation_enhanced_queries(company, title, jd_annotations)
            if enhanced_queries:
                self.logger.info(f"[Phase 8] Running {len(enhanced_queries)} annotation-enhanced queries")
                for query in enhanced_queries:
                    try:
                        self.logger.info(f"[FireCrawl] Annotation query: {query[:80]}...")
                        search_response = self._firecrawl_search(query, limit=5)
                        results = _extract_search_results(search_response)
                        self.logger.info(f"[FireCrawl] Got {len(results)} results from annotation query")

                        for result in results:
                            contact = self._extract_contact_from_search_result(result, company)
                            if contact:
                                all_contacts.append(contact)
                                self.logger.info(f"[Phase 8] Found: {contact['name']} - {contact['role']}")
                    except Exception as e:
                        self.logger.warning(f"Annotation query failed: {e}")
                        continue

                if all_contacts:
                    contact_strs = [f"- {c['name']} ({c['role']}) - {c['linkedin_url']}" for c in all_contacts[-5:]]
                    raw_content_parts.append(f"[SOURCE: Annotation-Enhanced Search]\n" + "\n".join(contact_strs) + "\n")

        # Deduplicate contacts
        if all_contacts:
            all_contacts = self._deduplicate_contacts(all_contacts)
            self.logger.info(f"Total unique contacts found: {len(all_contacts)}")

        if not raw_content_parts:
            self.logger.warning("No contacts found via FireCrawl (will use role-based fallback)")
            return f"No specific contacts found. Use role-based identifiers for {company}.", False

        return "\n---\n".join(raw_content_parts), True

    def _discover_contacts_with_claude_api(self, state: JobState) -> Tuple[str, bool]:
        """
        Contact discovery using Claude API with WebSearch (new backend).

        This is the primary discovery method when use_claude_api=True. It uses
        Claude's built-in web_search tool to find contacts in a single API call,
        replacing the multi-step FireCrawl approach.

        The output is formatted to be compatible with the existing classification
        LLM (same format as FireCrawl output), so classification and outreach
        generation continue to work unchanged.

        Args:
            state: JobState with company, title, and job context

        Returns:
            Tuple of (formatted contact data for classification LLM, found_any_contacts)
        """
        company = state.get("company", "")
        title = state.get("title", "")
        department = "engineering"  # Default department for tech roles

        self.logger.info(f"[Claude API] Discovering contacts at {company} for {title}")

        try:
            # Run async method in sync context
            result = asyncio.run(
                self.claude_researcher.research_people(
                    company_name=company,
                    role=title,
                    department=department,
                )
            )

            if not result.success:
                self.logger.warning(f"[Claude API] People research failed: {result.error}")
                return f"Claude API research failed: {result.error}. Use role-based identifiers for {company}.", False

            data = result.data
            self.logger.info(
                f"[Claude API] People research complete - {result.searches_performed} searches, "
                f"{result.duration_ms}ms"
            )

            # Extract contacts from response
            primary_contacts = data.get("primary_contacts", [])
            secondary_contacts = data.get("secondary_contacts", [])
            all_contacts = primary_contacts + secondary_contacts

            if not all_contacts:
                self.logger.warning("[Claude API] No contacts found (will use role-based fallback)")
                return f"No specific contacts found via Claude API. Use role-based identifiers for {company}.", False

            self.logger.info(
                f"[Claude API] Found {len(primary_contacts)} primary + "
                f"{len(secondary_contacts)} secondary contacts"
            )

            # Format contacts for the classification LLM (same format as FireCrawl output)
            # This ensures downstream classification works unchanged
            raw_content_parts = []

            if primary_contacts:
                contact_strs = []
                for c in primary_contacts:
                    linkedin_url = c.get("linkedin_url") or "No LinkedIn URL"
                    contact_strs.append(
                        f"- {c.get('name', 'Unknown')} ({c.get('role', 'Unknown')}) - {linkedin_url}"
                    )
                raw_content_parts.append(
                    f"[SOURCE: Claude API Primary Contacts]\n" + "\n".join(contact_strs) + "\n"
                )

            if secondary_contacts:
                contact_strs = []
                for c in secondary_contacts:
                    linkedin_url = c.get("linkedin_url") or "No LinkedIn URL"
                    contact_strs.append(
                        f"- {c.get('name', 'Unknown')} ({c.get('role', 'Unknown')}) - {linkedin_url}"
                    )
                raw_content_parts.append(
                    f"[SOURCE: Claude API Secondary Contacts]\n" + "\n".join(contact_strs) + "\n"
                )

            # Log metadata about the research
            self.logger.info(
                f"[Claude API] Research stats: model={result.model}, "
                f"searches={result.searches_performed}, "
                f"tokens={result.input_tokens or 'N/A'}/{result.output_tokens or 'N/A'}"
            )

            return "\n---\n".join(raw_content_parts), True

        except Exception as e:
            self.logger.error(f"[Claude API] People discovery failed: {e}")
            return f"Claude API error: {str(e)}. Use role-based identifiers for {company}.", False

    # ===== LLM CLASSIFICATION AND ENRICHMENT =====

    def _format_company_research_summary(self, company_research: Optional[Dict]) -> str:
        """Format company research for prompt."""
        if not company_research:
            return "No company research available."

        # Use _safe_get_nested for safe access
        summary = _safe_get_nested(company_research, "summary", default="")
        parts = [summary] if summary else []

        # Add key signals
        signals = _safe_get_nested(company_research, "signals", default=[])
        if signals and isinstance(signals, list):
            signal_texts = [
                f"- {_safe_get_nested(s, 'description', default='Unknown event')} "
                f"({_safe_get_nested(s, 'date', default='date unknown')})"
                for s in signals[:3]
            ]
            parts.append("Recent signals:\n" + "\n".join(signal_texts))

        return "\n".join(parts) if parts else "No company research available."

    def _format_role_research_summary(self, role_research: Optional[Dict]) -> str:
        """Format role research for prompt."""
        if not role_research:
            return "No role research available."

        # Use _safe_get_nested for safe access
        summary = _safe_get_nested(role_research, "summary", default="")
        parts = [summary] if summary else []

        # Add why_now
        why_now = _safe_get_nested(role_research, "why_now", default="")
        if why_now:
            parts.append(f"Why Now: {why_now}")

        return "\n".join(parts) if parts else "No role research available."

    def _format_pain_points(self, pain_points: List[str]) -> str:
        """Format pain points as bullets."""
        return "\n".join(f"- {p}" for p in pain_points[:5])

    def _candidate_profile_snippet(self, profile: str) -> str:
        """Return a trimmed snippet of the master CV for grounding."""
        if not profile:
            return "Master CV not available for outreach context."
        profile = profile.strip()
        return profile[:800] + ("..." if len(profile) > 800 else "")

    def _format_stars_summary(self, stars: List[Dict], candidate_profile: str = "") -> str:
        """Format STAR records for outreach context."""
        if not stars:
            return self._candidate_profile_snippet(candidate_profile)

        summaries = []
        for i, star in enumerate(stars[:3], 1):
            summary = f"""Achievement #{i}: {star.get('role', 'Role')} at {star.get('company', 'Company')}
Domain: {star.get('domain_areas', 'N/A')}
Results: {star.get('results', 'N/A')[:200]}
Metrics: {star.get('metrics', 'N/A')}""".strip()
            summaries.append(summary)

        return "\n\n".join(summaries)

    def _format_annotation_context(
        self,
        annotations: Optional[List[JDAnnotation]] = None,
        concerns: Optional[List[ConcernAnnotation]] = None,
        jd_annotations: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format JD annotations and concerns for outreach prompt injection.

        Phase 6: Annotation context enables personalized outreach by providing:
        - Must-have requirements for emphasis
        - Reframe guidance for positioning experience
        - Keywords for relevance signaling
        - Concern mitigation strategies

        Phase 5: Injects synthesized persona at the beginning when available.
        The persona provides a coherent narrative frame for the outreach message.

        Args:
            annotations: List of JDAnnotation from job state
            concerns: List of ConcernAnnotation from job state
            jd_annotations: Full jd_annotations dict for persona access

        Returns:
            Formatted annotation context string for prompt injection,
            or empty string if no annotations/concerns available
        """
        sections = []

        # Phase 5: Inject synthesized persona at the beginning
        # The persona provides the central theme for outreach messaging
        persona_guidance = get_persona_guidance(jd_annotations)
        if persona_guidance:
            sections.append(
                f"**{persona_guidance}**\n"
                "Open the message with this positioning.\n"
                "Use 'As a [persona]...' or similar natural framing."
            )

        if not annotations and not concerns and not persona_guidance:
            return ""

        # === Must-Have Requirements ===
        if annotations:
            must_haves = [
                a for a in annotations
                if a.get("requirement_type") == "must_have"
                and a.get("is_active", True)
            ]
            if must_haves:
                must_have_lines = []
                for a in must_haves[:5]:  # Top 5 for prompt length
                    text = a.get("target", {}).get("text", "")
                    skill = a.get("matching_skill", "")
                    if text:
                        line = f"- {text}"
                        if skill:
                            line += f" → Match: {skill}"
                        must_have_lines.append(line)
                if must_have_lines:
                    sections.append(
                        "**MUST-HAVE REQUIREMENTS (emphasize in outreach):**\n"
                        + "\n".join(must_have_lines)
                    )

        # === Reframe Guidance ===
        if annotations:
            reframes = [
                a for a in annotations
                if a.get("has_reframe") and a.get("reframe_note")
                and a.get("is_active", True)
            ]
            if reframes:
                reframe_lines = []
                for a in reframes[:4]:  # Top 4 reframes
                    reframe_note = a.get("reframe_note", "")
                    reframe_from = a.get("reframe_from", "")
                    reframe_to = a.get("reframe_to", "")
                    if reframe_note:
                        if reframe_from and reframe_to:
                            reframe_lines.append(f"- \"{reframe_from}\" → \"{reframe_to}\": {reframe_note}")
                        else:
                            reframe_lines.append(f"- {reframe_note}")
                if reframe_lines:
                    sections.append(
                        "**REFRAME GUIDANCE (use this positioning):**\n"
                        + "\n".join(reframe_lines)
                    )

        # === Annotation Keywords ===
        if annotations:
            all_keywords = []
            for a in annotations:
                if a.get("is_active", True):
                    all_keywords.extend(a.get("suggested_keywords", []))
                    all_keywords.extend(a.get("ats_variants", []))
            # Deduplicate while preserving order
            seen = set()
            unique_keywords = []
            for kw in all_keywords:
                if kw.lower() not in seen:
                    seen.add(kw.lower())
                    unique_keywords.append(kw)
            if unique_keywords:
                sections.append(
                    f"**ANNOTATION KEYWORDS (include in messaging):** {', '.join(unique_keywords[:12])}"
                )

        # === Concern Mitigation ===
        if concerns:
            active_concerns = [
                c for c in concerns
                if c.get("severity") in ("concern", "preference")  # Not blockers
            ]
            if active_concerns:
                concern_lines = []
                for c in active_concerns[:3]:  # Top 3 concerns
                    concern_text = c.get("concern", "")
                    mitigation = c.get("mitigation_strategy", "")
                    if concern_text and mitigation:
                        concern_lines.append(f"- {concern_text}: {mitigation}")
                if concern_lines:
                    sections.append(
                        "**CONCERNS TO ADDRESS (use positive framing):**\n"
                        + "\n".join(concern_lines)
                    )

        # === STAR Evidence Links ===
        if annotations:
            star_evidence = []
            for a in annotations:
                if a.get("is_active", True) and a.get("evidence_summary"):
                    star_evidence.append(f"- {a.get('evidence_summary')}")
            if star_evidence:
                sections.append(
                    "**LINKED EVIDENCE (cite in outreach):**\n"
                    + "\n".join(star_evidence[:3])
                )

        # === Phase 7 (GAP-091): Passion Areas for Genuine Enthusiasm ===
        if annotations:
            passion_items = [
                a for a in annotations
                if a.get("passion") == "love_it" and a.get("is_active", True)
            ]
            if passion_items:
                passion_lines = []
                for a in passion_items[:3]:  # Top 3 passion areas
                    text = a.get("target", {}).get("text", "")[:50]
                    skill = a.get("matching_skill", "")
                    passion_lines.append(f"- {skill or text}")
                if passion_lines:
                    sections.append(
                        "**PASSION AREAS (show authentic enthusiasm):**\n"
                        + "\n".join(passion_lines)
                        + "\nUse these naturally to demonstrate genuine interest"
                    )

        # === Phase 7 (GAP-091): Identity Areas for Positioning ===
        if annotations:
            identity_items = [
                a for a in annotations
                if a.get("identity") == "core_identity" and a.get("is_active", True)
            ]
            if identity_items:
                identity_lines = []
                for a in identity_items[:2]:  # Top 2 identity areas
                    text = a.get("target", {}).get("text", "")[:50]
                    skill = a.get("matching_skill", "")
                    identity_lines.append(f"- {skill or text}")
                if identity_lines:
                    sections.append(
                        "**PROFESSIONAL IDENTITY (frame opening around):**\n"
                        + "\n".join(identity_lines)
                        + "\nOpen with 'As a [identity]...' positioning"
                    )

        # === Phase 7 (GAP-091): Avoid Areas for Tone Adjustment ===
        if annotations:
            avoid_items = [
                a for a in annotations
                if a.get("passion") == "avoid" and a.get("is_active", True)
            ]
            if avoid_items:
                avoid_lines = []
                for a in avoid_items[:2]:  # Track top 2 avoid areas
                    text = a.get("target", {}).get("text", "")[:40]
                    avoid_lines.append(f"- {text}")
                if avoid_lines:
                    sections.append(
                        "**DE-EMPHASIZE (do NOT highlight in outreach):**\n"
                        + "\n".join(avoid_lines)
                        + "\nAvoid emphasizing these even if technically relevant"
                    )

        if not sections:
            return ""

        return "=== ANNOTATION CONTEXT ===\n" + "\n\n".join(sections) + "\n\n"

    def _generate_fallback_cover_letters(self, state: JobState, reason: str) -> List[str]:
        """
        Create three fallback cover letters when no contacts are discoverable.

        Uses the master CV, pain points, and company context to stay personalized
        without relying on named contacts.
        """
        candidate_profile = self._candidate_profile_snippet(state.get("candidate_profile", ""))
        pain_points = self._format_pain_points(state.get("pain_points", []))
        company_research = self._format_company_research_summary(state.get("company_research"))
        role_research = self._format_role_research_summary(state.get("role_research"))

        messages = [
            SystemMessage(content="You are drafting concise fallback cover letters for cold outreach."),
            HumanMessage(content=f"""FireCrawl could not find individual contacts.

Draft THREE distinct cover letter options (120-180 words each) for the role {state.get('title', '')} at {state.get('company', '')}.
Ground every statement in the provided pain points, research, and master CV. Avoid inventing facts.

Pain Points:
{pain_points}

Company Research:
{company_research}

Role Research:
{role_research}

Candidate (Master CV):
{candidate_profile}

Each option must:
- Be concise and specific
- Include at least one concrete metric from the candidate's experience if available
- End with: taimooralam@example.com | https://calendly.com/taimooralam/15min

Return the three letters separated by \"---\" lines.
""".replace("FireCrawl could not find individual contacts.", reason))
        ]

        try:
            response = self.llm.invoke(messages)
            response_text = response.content.strip()
            letters = [letter.strip() for letter in re.split(r'\n-{3,}\n', response_text) if letter.strip()]

            if len(letters) < 3 and response_text:
                # Try splitting by numbered options as a fallback
                alt_letters = re.split(r'\n\d\.\s', response_text)
                if alt_letters:
                    letters.extend([l.strip() for l in alt_letters if l.strip()])

            # Ensure exactly three options
            while len(letters) < 3:
                letters.append(f"Cover letter option {len(letters)+1} for {state.get('title', 'the role')} at {state.get('company', '')}.\n\n{candidate_profile[:200]}")

            return letters[:3]
        except Exception as e:
            self.logger.warning(f"Fallback cover letter generation failed: {e}")
            basic_letter = (
                f"Hi {state.get('company', '')} team,\n\n"
                f"I'm interested in the {state.get('title', 'role')} role. Drawing from my background ({candidate_profile[:180]}...), "
                f"I can address your needs around {pain_points.splitlines()[0] if pain_points else 'priority initiatives'}.\n\n"
                f"taimooralam@example.com | https://calendly.com/taimooralam/15min"
            )
            return [basic_letter] * 3

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _classify_contacts(self, raw_contacts: str, state: JobState) -> Dict[str, List[Dict]]:
        """
        Classify contacts into primary/secondary using LLM (Phase 7.2.3).

        Args:
            raw_contacts: Raw scraped content with contact mentions
            state: JobState with job/company context

        Returns:
            Dict with primary_contacts and secondary_contacts lists

        Raises:
            ValueError: If validation fails (triggers retry)
        """
        # Build prompt
        messages = [
            SystemMessage(content=SYSTEM_PROMPT_CLASSIFICATION),
            HumanMessage(content=USER_PROMPT_CLASSIFICATION_TEMPLATE.format(
                title=state.get("title", ""),
                company=state.get("company", ""),
                job_description=state.get("job_description", "")[:1500],
                company_research_summary=self._format_company_research_summary(state.get("company_research")),
                role_research_summary=self._format_role_research_summary(state.get("role_research")),
                pain_points=self._format_pain_points(state.get("pain_points", [])),
                raw_contacts=raw_contacts[:3000]
            ))
        ]

        # Get LLM response
        response = self.llm.invoke(messages)
        response_text = response.content.strip()

        # Parse JSON
        try:
            # Extract JSON (handle markdown code blocks)
            if "```json" in response_text:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
            elif "```" in response_text:
                json_match = re.search(r'```\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)

            data = json.loads(response_text)

            # Validate with Pydantic
            validated = PeopleMapperOutput(**data)

            # Convert to dicts
            return {
                "primary_contacts": [c.model_dump() for c in validated.primary_contacts],
                "secondary_contacts": [c.model_dump() for c in validated.secondary_contacts]
            }

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}")
        except Exception as e:
            raise ValueError(f"Validation failed: {e}")

    # ===== OUTREACH GENERATION =====

    def _validate_content_constraints(self, message: str, channel: str) -> None:
        """
        Validate Phase 9 content constraints.

        Args:
            message: Message to validate
            channel: "linkedin" or "email"

        Raises:
            ValueError: If validation fails (triggers retry)
        """
        # Check for emojis (Phase 9)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251"
            "]+"
        )

        if emoji_pattern.search(message):
            raise ValueError(f"{channel} message contains emojis (not allowed)")

        # Check for disallowed placeholders (only [Your Name] and role-based names allowed)
        # Role-based names like "VP Engineering at PayFlow" are valid addressees, not placeholders
        placeholders = re.findall(r'\[([^\]]+)\]', message)

        # Common role titles that indicate a role-based addressee (not a placeholder)
        role_keywords = [
            'vp', 'vice president', 'director', 'manager', 'engineer', 'lead', 'head',
            'chief', 'cto', 'ceo', 'cfo', 'coo', 'coordinator', 'specialist', 'analyst',
            'architect', 'developer', 'designer', 'recruiter', 'hr', 'talent', 'people',
            'principal', 'senior', 'staff', 'team lead', 'product', 'engineering',
            'technical', 'operations', 'strategy', 'marketing', 'sales', 'at '
        ]

        disallowed = []
        for p in placeholders:
            p_lower = p.lower()
            # Allow [Your Name]
            if p_lower == "your name":
                continue
            # Allow role-based addressees (contain role keywords)
            if any(keyword in p_lower for keyword in role_keywords):
                continue
            # Otherwise, it's a disallowed placeholder
            disallowed.append(p)

        if disallowed:
            raise ValueError(
                f"{channel} message contains disallowed placeholders: {disallowed}. "
                f"Only [Your Name] and role-based titles (e.g., 'VP Engineering at Company') are allowed."
            )

        # Check for possessive placeholders (not in brackets but still generic)
        # Examples: "Contact's Name", "Director's Name", "Manager's Name"
        possessive_placeholders = re.findall(
            r"\b(Contact|Director|Manager|Recruiter|Hiring Manager|VP|Engineer|Lead|Team Lead|Representative|Person)'s (Name|name|Email|email)",
            message
        )

        if possessive_placeholders:
            found_possessives = [f"{role}'s {field}" for role, field in possessive_placeholders]
            raise ValueError(
                f"{channel} message contains generic possessive placeholders: {found_possessives}. "
                f"Use actual names or specific role-based addressees like 'VP Engineering at {company}'."
            )

    def _validate_linkedin_closing(self, message: str) -> None:
        """
        Validate that LinkedIn message ends with signature (GAP-011 update).

        Args:
            message: LinkedIn message

        Raises:
            ValueError: If closing signature is missing
        """
        # GAP-011: Simplified closing to fit within 300 char limit
        # Just require the signature "Best. Taimoor Alam"
        if "best" not in message.lower() or "taimoor" not in message.lower():
            raise ValueError(
                'LinkedIn message must end with signature: "Best. Taimoor Alam"'
            )

    def _validate_linkedin_message(self, message: str) -> str:
        """
        Validate and trim LinkedIn message to ≤300 chars (GAP-011 fix).

        LinkedIn connection request messages have a HARD 300 character limit.
        This method enforces that limit with intelligent truncation.

        Args:
            message: Raw LinkedIn message from LLM

        Returns:
            Validated/truncated message (≤300 chars)
        """
        HARD_LIMIT = 300
        SIGNATURE = "Best. Taimoor Alam"

        if len(message) <= HARD_LIMIT:
            self.logger.info(f"LinkedIn message valid: {len(message)}/{HARD_LIMIT} chars")
            return message

        # Message exceeds limit - need to truncate intelligently
        self.logger.warning(
            f"LinkedIn message too long: {len(message)}/{HARD_LIMIT} chars. "
            f"Truncating (excess: {len(message) - HARD_LIMIT} chars)"
        )

        # Strategy: Preserve signature, truncate content at sentence boundary
        # Reserve space for signature + newline
        signature_space = len(SIGNATURE) + 2  # "\n" + signature
        content_limit = HARD_LIMIT - signature_space

        # Remove existing signature if present (we'll add it back)
        content = message
        if SIGNATURE in message:
            content = message.replace(SIGNATURE, "").strip()
        if "Best." in content:
            content = content.split("Best.")[0].strip()

        # Truncate content at sentence boundary
        if len(content) > content_limit:
            # Find last complete sentence within limit
            truncated = content[:content_limit]
            last_period = truncated.rfind('.')
            last_question = truncated.rfind('?')
            last_exclaim = truncated.rfind('!')

            # Use the latest sentence boundary
            best_boundary = max(last_period, last_question, last_exclaim)

            if best_boundary > content_limit * 0.5:  # Only use if we keep >50% of content
                content = content[:best_boundary + 1]
            else:
                # No good sentence boundary - truncate at word boundary
                content = truncated.rsplit(' ', 1)[0] + "..."

        # Reassemble with signature
        result = content.strip() + "\n" + SIGNATURE

        # Final safety check
        if len(result) > HARD_LIMIT:
            # Last resort: Hard truncate
            result = result[:HARD_LIMIT - 3] + "..."
            self.logger.warning(f"Hard truncation applied: {len(result)} chars")

        self.logger.info(f"LinkedIn message truncated: {len(message)} -> {len(result)} chars")
        return result

    def _validate_email_body_length(self, email_body: str) -> str:
        """
        Validate email body length (95-205 words - Phase 9 with 5% tolerance).

        Args:
            email_body: Email body text

        Returns:
            The validated email body

        Raises:
            ValueError: If word count is outside 95-205 range
        """
        words = email_body.split()
        word_count = len(words)

        if word_count < 95:
            raise ValueError(
                f"Email body too short ({word_count} words). "
                f"Requires 95-205 words (ROADMAP target: 100-200, 5% tolerance)."
            )

        if word_count > 205:
            raise ValueError(
                f"Email body too long ({word_count} words). "
                f"Requires 95-205 words (ROADMAP target: 100-200, 5% tolerance)."
            )

        return email_body

    def _validate_email_subject_words(self, subject: str, pain_points: List[str]) -> str:
        """
        Validate email subject word count and pain-focus (5-10 words - Phase 9 with tolerance).

        Args:
            subject: Email subject line
            pain_points: List of job pain points for pain-focus check

        Returns:
            The validated subject

        Raises:
            ValueError: If word count is outside 5-10 range or lacks pain-focus
        """
        words = subject.split()
        word_count = len(words)

        if word_count < 5:
            raise ValueError(
                f"Email subject too short ({word_count} words). "
                f"Requires 5-10 words (ROADMAP target: 6-10, 1-word tolerance)."
            )

        if word_count > 10:
            raise ValueError(
                f"Email subject too long ({word_count} words). "
                f"ROADMAP requires 6-10 words."
            )

        # If no pain points are available (e.g., Layer 2 failed),
        # treat the subject as valid based on length alone.
        # This prevents hard failures when upstream analysis is missing.
        if pain_points:
            # Check pain-focus: subject must reference at least one pain point
            subject_lower = subject.lower()
            has_pain_focus = False

            for pain_point in pain_points:
                # Check for exact phrase or significant keywords (3+ chars)
                pain_keywords = [word for word in pain_point.lower().split() if len(word) >= 3]

                # Check if any keyword appears in subject
                for keyword in pain_keywords:
                    if keyword in subject_lower:
                        has_pain_focus = True
                        break

                if has_pain_focus:
                    break

            if not has_pain_focus:
                raise ValueError(
                    f"Email subject must be pain-focused (reference at least one pain point). "
                    f"Subject: '{subject}', Pain points: {pain_points[:3]}"
                )

        return subject

    def _validate_email_subject(self, subject: str) -> str:
        """Validate and trim email subject to ≤100 chars."""
        if len(subject) <= 100:
            return subject
        return subject[:97] + "..."

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _generate_outreach_package(self, contact: Dict[str, Any], state: JobState) -> Dict[str, str]:
        """
        Generate OutreachPackage for one contact (Phase 7.2.4 + linkedin/outreach.md integration).

        Generates THREE outreach formats:
        - LinkedIn Connection Request (≤300 chars with Calendly)
        - LinkedIn InMail (400-600 chars with subject)
        - Email (subject + body)

        Args:
            contact: Contact dict with name, role, why_relevant, recent_signals
            state: JobState with job/STAR context

        Returns:
            Dict with dual LinkedIn formats, email, and contact_type classification
        """
        # Classify contact type based on role
        contact_type = classify_contact_type(contact["role"])

        # Format contact signals
        signals_text = ", ".join(contact.get("recent_signals", [])) if contact.get("recent_signals") else "None"

        # Phase 6: Format annotation context for personalized outreach
        # Extract annotations and concerns from the jd_annotations dict structure
        # Phase 5: Also pass full jd_annotations for persona access
        jd_annotations_data = state.get("jd_annotations") or {}
        annotation_context = self._format_annotation_context(
            annotations=jd_annotations_data.get("annotations") if isinstance(jd_annotations_data, dict) else None,
            concerns=jd_annotations_data.get("concerns") if isinstance(jd_annotations_data, dict) else None,
            jd_annotations=jd_annotations_data if isinstance(jd_annotations_data, dict) else None,
        )

        # Build prompt with contact_type and annotation context
        messages = [
            SystemMessage(content=SYSTEM_PROMPT_OUTREACH),
            HumanMessage(content=USER_PROMPT_OUTREACH_TEMPLATE.format(
                contact_name=contact["name"],
                contact_role=contact["role"],
                contact_type=contact_type,
                contact_why=contact["why_relevant"],
                contact_signals=signals_text,
                job_title=state.get("title", ""),
                company=state.get("company", ""),
                pain_points=self._format_pain_points(state.get("pain_points", [])),
                company_research_summary=self._format_company_research_summary(state.get("company_research")),
                selected_stars_summary=self._format_stars_summary(
                    state.get("selected_stars", []),
                    state.get("candidate_profile", "")
                ),
                annotation_context=annotation_context,
            ))
        ]

        # Get LLM response
        response = self.llm.invoke(messages)
        response_text = response.content.strip()

        # Parse JSON
        try:
            # Extract JSON
            if "```json" in response_text:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
            elif "```" in response_text:
                json_match = re.search(r'```\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)

            data = json.loads(response_text)

            # Get raw content - NEW dual LinkedIn format
            linkedin_connection_raw = data.get("linkedin_connection_message", "")
            linkedin_inmail_raw = data.get("linkedin_inmail", "")
            linkedin_inmail_subject_raw = data.get("linkedin_inmail_subject", "")
            email_subject_raw = data.get("email_subject", data.get("subject", ""))
            email_body_raw = data.get("email_body", "")
            already_applied_frame = data.get("already_applied_frame", "adding_context")

            # Validate Phase 9 content constraints (emojis, placeholders)
            self._validate_content_constraints(linkedin_connection_raw, "linkedin")
            self._validate_content_constraints(linkedin_inmail_raw, "linkedin")
            self._validate_content_constraints(email_body_raw, "email")

            # Validate LinkedIn closing line for connection message (Phase 9)
            self._validate_linkedin_closing(linkedin_connection_raw)

            # Validate connection message includes Calendly
            if CALENDLY_LINK not in linkedin_connection_raw.lower():
                self.logger.warning(f"Connection message missing Calendly link for {contact['name']}")

            # Validate Phase 9 ROADMAP word count requirements
            pain_points = state.get("pain_points", [])
            validated_subject = self._validate_email_subject_words(email_subject_raw, pain_points)
            validated_body = self._validate_email_body_length(email_body_raw)

            # Validate and trim lengths
            linkedin_connection = self._validate_linkedin_message(linkedin_connection_raw)
            email_subject = self._validate_email_subject(validated_subject)
            email_body = validated_body

            return {
                "contact_name": contact["name"],
                "contact_role": contact["role"],
                "contact_type": contact_type,
                "linkedin_url": contact["linkedin_url"],
                # Dual LinkedIn formats (linkedin/outreach.md)
                "linkedin_connection_message": linkedin_connection,
                "linkedin_inmail_subject": linkedin_inmail_subject_raw[:30] if linkedin_inmail_subject_raw else "",
                "linkedin_inmail": linkedin_inmail_raw,
                # Email
                "email_subject": email_subject,
                "email_body": email_body,
                # Metadata
                "why_relevant": contact["why_relevant"],
                "recent_signals": contact.get("recent_signals", []),
                "reasoning": f"Personalized for {contact_type} ({contact['role']})",
                "already_applied_frame": already_applied_frame,
                # Legacy field for backward compatibility
                "linkedin_message": linkedin_connection
            }

        except Exception as e:
            # Fallback: generate minimal outreach with dual LinkedIn format
            self.logger.warning(f"Outreach generation failed for {contact['name']}: {e}")
            title = state.get('title', 'role')
            company = state.get('company', '')
            contact_type = classify_contact_type(contact["role"])

            # Fallback connection message with Calendly (≤300 chars)
            fallback_connection = f"Hi, applied for {title} at {company}. 11+ yrs scaling eng teams. Let's connect: {CALENDLY_LINK} Best. Taimoor Alam"

            return {
                "contact_name": contact["name"],
                "contact_role": contact["role"],
                "contact_type": contact_type,
                "linkedin_url": contact["linkedin_url"],
                # Dual LinkedIn formats
                "linkedin_connection_message": fallback_connection,
                "linkedin_inmail_subject": f"Re: {title}",
                "linkedin_inmail": f"Hi, I submitted my application for {title} at {company} and wanted to introduce myself. With 11+ years leading engineering teams, I'd welcome the opportunity to discuss how my experience aligns. {CALENDLY_LINK} Best. Taimoor Alam",
                # Email
                "email_subject": f"Interest in {title}",
                "email_body": f"I recently applied for the {title} position at {company} and wanted to follow up.",
                # Metadata
                "why_relevant": contact["why_relevant"],
                "recent_signals": contact.get("recent_signals", []),
                "reasoning": "Fallback due to generation error",
                "already_applied_frame": "adding_context",
                # Legacy field for backward compatibility
                "linkedin_message": fallback_connection
            }

    # ===== MAIN MAPPER FUNCTION =====

    def map_people(self, state: JobState, skip_outreach: bool = False) -> Dict[str, Any]:
        """
        Layer 5: People Mapper (Phase 7).

        1. Multi-source contact discovery via FireCrawl (skipped when DISABLE_FIRECRAWL_OUTREACH is true)
        2. LLM-based classification into primary/secondary
        3. OutreachPackage generation for each contact (skipped if skip_outreach=True)
        4. Quality gates: 4-6 primary, 4-6 secondary (reduced for agencies: 2 primary, 0 secondary)

        Args:
            state: JobState with job/company context
            skip_outreach: If True, skip outreach generation and return contacts only.
                           Useful for Research button which only needs contact discovery.

        Returns:
            Dict with primary_contacts, secondary_contacts, outreach_packages
        """
        self.logger.info("="*80)
        self.logger.info("LAYER 5: PEOPLE MAPPER (Phase 7)")
        self.logger.info("="*80)
        if skip_outreach:
            self.logger.info("skip_outreach=True: Will discover contacts but skip outreach message generation")
        if self.firecrawl_disabled:
            self.logger.info("FireCrawl outreach scraping disabled via Config.DISABLE_FIRECRAWL_OUTREACH (role-based contacts only)")

        # Check if this is a recruitment agency
        company_type = _safe_get_nested(state, "company_research", "company_type", default="employer")
        is_agency = company_type == "recruitment_agency"
        if is_agency:
            self.logger.info("RECRUITMENT AGENCY DETECTED - Using limited recruiter discovery (2 contacts max)")

        # ===== VALIDATE UPSTREAM DEPENDENCIES =====
        # Check critical fields (Layer 5 cannot proceed without these)
        missing_fields = []
        if not state.get("company"):
            missing_fields.append("company")
        if not state.get("title"):
            missing_fields.append("title")
        if not state.get("job_id"):
            missing_fields.append("job_id")

        if missing_fields:
            error_msg = f"Layer 5 requires upstream data: {', '.join(missing_fields)}"
            self.logger.error(error_msg)
            return {
                "primary_contacts": [],
                "secondary_contacts": [],
                "people": [],
                "outreach_packages": [],
                "fallback_cover_letters": [],
                "errors": state.get("errors", []) + [error_msg]
            }

        # Log warnings for missing optional upstream data (non-fatal, but degrades quality)
        if not state.get("pain_points"):
            self.logger.warning("Layer 2 (pain_points) missing - outreach quality may be reduced")

        company_research = state.get("company_research")
        if not company_research:
            self.logger.warning("Layer 3 (company_research) missing - using fallback company URL")
        elif not _safe_get_nested(state, "company_research", "url"):
            self.logger.warning("Layer 3 (company_research.url) missing - using fallback company URL")

        if not state.get("role_research"):
            self.logger.warning("Layer 3 (role_research) missing - outreach will lack role context")

        if not state.get("selected_stars"):
            self.logger.warning("Layer 2.5 (selected_stars) missing - outreach will lack specific achievements")

        if not state.get("candidate_profile"):
            self.logger.warning("candidate_profile missing - outreach will use generic content")

        # ===== CHECK FOR EXISTING CONTACTS (Skip FireCrawl if already present) =====
        existing_primary = state.get("primary_contacts", [])
        existing_secondary = state.get("secondary_contacts", [])

        if existing_primary or existing_secondary:
            # Contacts already exist - skip FireCrawl discovery
            self.logger.info("="*60)
            self.logger.info("CONTACTS ALREADY PRESENT - SKIPPING FIRECRAWL DISCOVERY")
            self.logger.info("="*60)
            self.logger.info(f"  Existing primary contacts: {len(existing_primary)}")
            self.logger.info(f"  Existing secondary contacts: {len(existing_secondary)}")

            # Return existing contacts as-is (they may already have outreach)
            return {
                "primary_contacts": existing_primary,
                "secondary_contacts": existing_secondary,
                "people": existing_primary + existing_secondary,  # Legacy field
                "outreach_packages": [],  # May already be populated in contacts
                "fallback_cover_letters": state.get("fallback_cover_letters", []),
            }

        # ===== AGENCY-SPECIFIC HANDLING =====
        # For recruitment agencies, skip full discovery and use 2 recruiters only
        if is_agency:
            self.logger.info("="*60)
            self.logger.info("AGENCY FLOW: Generating 2 recruiter contacts only")
            self.logger.info("="*60)

            agency_contacts = self._generate_agency_recruiter_contacts(state)
            primary_contacts = agency_contacts["primary_contacts"]

            self.logger.info(f"Generated {len(primary_contacts)} agency recruiter contacts")

            # Skip outreach generation if requested (Research button flow)
            if skip_outreach:
                self.logger.info("skip_outreach=True: Returning contacts without outreach messages")
                return {
                    "primary_contacts": primary_contacts,
                    "secondary_contacts": [],
                    "people": primary_contacts,
                    "outreach_packages": [],
                    "fallback_cover_letters": []
                }

            # Generate outreach for recruiters (no secondary contacts for agencies)
            enriched_primary = []
            for i, contact in enumerate(primary_contacts, 1):
                self.logger.info(f"Generating outreach {i}/{len(primary_contacts)}: {contact['name']}")
                try:
                    outreach = self._generate_outreach_package(contact, state)
                    enriched_contact = {**contact, **outreach}
                    enriched_primary.append(enriched_contact)
                except Exception as e:
                    self.logger.warning(f"Failed to generate outreach for recruiter: {e}")
                    enriched_primary.append(contact)

            self.logger.info("Completed agency recruiter outreach generation")

            return {
                "primary_contacts": enriched_primary,
                "secondary_contacts": [],  # No secondary contacts for agencies
                "people": enriched_primary,  # Legacy field
                "outreach_packages": [],
                "fallback_cover_letters": []
            }

        try:
            # Step 1: Multi-source discovery (for regular employers only)
            # Route to Claude API or FireCrawl based on configuration
            if self.use_claude_api and self.claude_researcher:
                # Claude API path (new backend)
                self.logger.info("[Discovery] Using Claude API for contact discovery")
                raw_contacts, found_contacts = self._discover_contacts_with_claude_api(state)
            elif self.firecrawl_disabled:
                # FireCrawl disabled and Claude API not configured
                raw_contacts, found_contacts = (
                    "Contact discovery is disabled. Use role-based identifiers.",
                    False
                )
            else:
                # FireCrawl path (legacy backend)
                self.logger.info("[Discovery] Using FireCrawl for contact discovery")
                raw_contacts, found_contacts = self._discover_contacts(state)

            if not found_contacts:
                fallback_reason = (
                    "Claude API contact discovery returned no results (role-based synthetic contacts)."
                    if self.use_claude_api
                    else (
                        "FireCrawl outreach discovery disabled (role-based synthetic contacts)."
                        if self.firecrawl_disabled
                        else "No contacts found via FireCrawl - using role-based synthetic contacts."
                    )
                )
                self.logger.warning(fallback_reason)
                synthetic = self._generate_synthetic_contacts(state)
                primary_contacts = synthetic["primary_contacts"]
                secondary_contacts = synthetic["secondary_contacts"]
                self.logger.info(f"Generated {len(primary_contacts)} synthetic primary contacts")
                self.logger.info(f"Generated {len(secondary_contacts)} synthetic secondary contacts")

                # Apply contact limit (GAP-060)
                limited_primary, limited_secondary = self._limit_contacts(
                    primary_contacts, secondary_contacts
                )

                # Skip outreach generation if requested (Research button flow)
                if skip_outreach:
                    self.logger.info("skip_outreach=True: Returning synthetic contacts without outreach messages")
                    return {
                        "primary_contacts": limited_primary,
                        "secondary_contacts": limited_secondary,
                        "people": limited_primary + limited_secondary,
                        "outreach_packages": [],
                        "fallback_cover_letters": []
                    }

                # Also generate fallback cover letters for reference
                fallback_letters = self._generate_fallback_cover_letters(state, fallback_reason)

                # Generate outreach for synthetic contacts
                self.logger.info("Generating personalized outreach for synthetic contacts")
                all_contacts = limited_primary + limited_secondary
                enriched_primary = []
                enriched_secondary = []
                num_limited_primary = len(limited_primary)

                for i, contact in enumerate(all_contacts, 1):
                    self.logger.info(f"Generating outreach {i}/{len(all_contacts)}: {contact['name']}")
                    try:
                        outreach = self._generate_outreach_package(contact, state)
                        enriched_contact = {**contact, **outreach}
                        if i <= num_limited_primary:
                            enriched_primary.append(enriched_contact)
                        else:
                            enriched_secondary.append(enriched_contact)
                    except Exception as e:
                        self.logger.warning(f"Failed to generate outreach: {e}")
                        if i <= num_limited_primary:
                            enriched_primary.append(contact)
                        else:
                            enriched_secondary.append(contact)

                self.logger.info("Completed synthetic contact outreach generation")

                return {
                    "primary_contacts": enriched_primary,
                    "secondary_contacts": enriched_secondary,
                    "people": enriched_primary + enriched_secondary,
                    "outreach_packages": [],  # Future: structured packages
                    "fallback_cover_letters": fallback_letters
                }

            # Step 2: Classify contacts
            self.logger.info("Classifying contacts into primary/secondary")
            classified = self._classify_contacts(raw_contacts, state)

            primary_contacts = classified["primary_contacts"]
            secondary_contacts = classified["secondary_contacts"]

            self.logger.info(f"{len(primary_contacts)} primary contacts (hiring-related)")
            self.logger.info(f"{len(secondary_contacts)} secondary contacts (cross-functional)")

            # Step 3: Apply contact limit BEFORE outreach generation (GAP-060)
            # This saves LLM calls by only generating outreach for contacts we'll keep
            limited_primary, limited_secondary = self._limit_contacts(
                primary_contacts, secondary_contacts
            )

            # Skip outreach generation if requested (Research button flow)
            if skip_outreach:
                self.logger.info("skip_outreach=True: Returning classified contacts without outreach messages")
                return {
                    "primary_contacts": limited_primary,
                    "secondary_contacts": limited_secondary,
                    "people": limited_primary + limited_secondary,
                    "outreach_packages": [],
                    "fallback_cover_letters": []
                }

            # Step 4: Generate outreach for limited contacts only
            self.logger.info("Generating personalized outreach")

            all_contacts = limited_primary + limited_secondary
            enriched_primary = []
            enriched_secondary = []
            num_limited_primary = len(limited_primary)

            for i, contact in enumerate(all_contacts, 1):
                self.logger.info(f"Generating outreach {i}/{len(all_contacts)}: {contact['name']}")

                try:
                    outreach = self._generate_outreach_package(contact, state)

                    # Merge contact + outreach
                    enriched_contact = {**contact, **outreach}

                    # Add to appropriate bucket
                    if i <= num_limited_primary:
                        enriched_primary.append(enriched_contact)
                    else:
                        enriched_secondary.append(enriched_contact)

                except Exception as e:
                    self.logger.warning(f"Failed to generate outreach: {e}")
                    # Add contact without outreach
                    if i <= num_limited_primary:
                        enriched_primary.append(contact)
                    else:
                        enriched_secondary.append(contact)

            self.logger.info(f"Generated outreach for {len(enriched_primary + enriched_secondary)} contacts")

            # Step 5: Return updates (limit already applied in Step 3)
            return {
                "primary_contacts": enriched_primary,
                "secondary_contacts": enriched_secondary,
                "people": enriched_primary + enriched_secondary,  # Legacy field
                "outreach_packages": None,  # Future: per-contact packages
                "fallback_cover_letters": []
            }

        except Exception as e:
            self.logger.error(f"People mapping failed: {e}")
            return {
                "primary_contacts": [],
                "secondary_contacts": [],
                "people": [],
                "outreach_packages": [],
                "fallback_cover_letters": [],
                "errors": state.get("errors", []) + [f"People mapping error: {str(e)}"]
            }


# ===== NODE FUNCTION =====

def people_mapper_node(
    state: JobState,
    tier: TierType = "balanced",
    use_claude_api: bool = True,
) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 5 (Phase 7).

    Supports two discovery backends:
    - Claude API (default): Uses Claude API with WebSearch for contact discovery
    - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility

    Args:
        state: Current job state
        tier: Claude model tier for discovery - "fast", "balanced", or "quality".
              Only used when use_claude_api=True. Default is "balanced".
        use_claude_api: If True (default), use Claude API for contact discovery.
                       If False, use FireCrawl (legacy mode).

    Returns:
        State updates with primary_contacts, secondary_contacts, outreach_packages
    """
    # Note: Detailed logging happens inside PeopleMapper.map_people()
    # Node-level logger mainly for entry/exit tracking
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer5")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    with LayerContext(struct_logger, 5, "people_mapper") as ctx:
        # Log which backend is being used
        ctx.add_metadata("discovery_backend", "claude_api" if use_claude_api else "firecrawl")
        if use_claude_api:
            ctx.add_metadata("claude_tier", tier)

        mapper = PeopleMapper(tier=tier, use_claude_api=use_claude_api)
        result = mapper.map_people(state)

        # Add metadata
        primary = result.get("primary_contacts", [])
        secondary = result.get("secondary_contacts", [])
        ctx.add_metadata("primary_contacts", len(primary) if primary else 0)
        ctx.add_metadata("secondary_contacts", len(secondary) if secondary else 0)

        return result
