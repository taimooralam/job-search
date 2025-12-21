"""
Claude Web Researcher - Company and People Research via Claude API with Web Search

Provides web research capabilities using Claude API with WebSearch/WebFetch tools.
Replaces FireCrawl for company research, role research, and people discovery.

Supports three Claude model tiers:
- Fast: Claude Haiku 4.5 (lowest cost, good for bulk)
- Balanced: Claude Sonnet 4.5 (DEFAULT - best quality/cost ratio)
- Quality: Claude Opus 4.5 (highest quality)

Usage:
    # Company research
    researcher = ClaudeWebResearcher(tier="balanced")
    result = await researcher.research_company("Acme Corp", job_context="...")

    # People research
    contacts = await researcher.research_people("Acme Corp", role="Engineering Manager")

    # Role research
    role_info = await researcher.research_role("Acme Corp", "Head of Engineering")
"""

import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from dataclasses import dataclass, asdict, field
from pydantic import BaseModel, Field, ValidationError

from src.common.json_utils import parse_llm_json
from src.common.unified_llm import invoke_unified_sync, LLMResult


logger = logging.getLogger(__name__)


# ===== CLAUDE MODEL TIERS =====

CLAUDE_MODEL_TIERS = {
    "fast": "claude-haiku-4-5-20251001",
    "balanced": "claude-sonnet-4-5-20250929",
    "quality": "claude-opus-4-5-20251101",
}

TierType = Literal["fast", "balanced", "quality"]


# ===== PYDANTIC SCHEMAS (compatible with existing state.py) =====

class CompanySignalModel(BaseModel):
    """Company signal with source attribution."""
    type: str = Field(..., description="Signal type: funding, acquisition, leadership_change, product_launch, partnership, growth")
    description: str = Field(..., min_length=1, description="Brief description of the signal")
    date: str = Field(default="unknown", description="ISO date or 'unknown'")
    source: str = Field(..., min_length=1, description="Source URL where signal was found")
    business_context: str = Field(default="", description="What this signal reveals about company trajectory")


class CompanyResearchModel(BaseModel):
    """Structured company research output."""
    summary: str = Field(..., min_length=10, description="2-3 sentence company summary")
    signals: List[CompanySignalModel] = Field(default_factory=list, max_length=10, description="Business signals with sources")
    url: str = Field(..., min_length=1, description="Primary company URL")
    company_type: str = Field(default="employer", description="'employer' | 'recruitment_agency' | 'unknown'")


class ContactModel(BaseModel):
    """Contact discovered through people research."""
    name: str = Field(..., min_length=1, description="Full name")
    role: str = Field(..., min_length=1, description="Job title/role")
    company: str = Field(..., description="Company name")
    why_relevant: str = Field(..., description="Why this person is relevant for outreach")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile URL if found")
    email: Optional[str] = Field(default=None, description="Email if publicly available")


class PeopleResearchModel(BaseModel):
    """People research output."""
    primary_contacts: List[ContactModel] = Field(default_factory=list, max_length=3, description="Key decision makers")
    secondary_contacts: List[ContactModel] = Field(default_factory=list, max_length=2, description="Other relevant contacts")


class RoleResearchModel(BaseModel):
    """Role-specific research output."""
    business_impact: List[str] = Field(default_factory=list, description="Key business impacts of this role")
    why_now: str = Field(default="", description="Why the company is hiring for this role now")
    team_context: str = Field(default="", description="Context about the team this role joins")
    challenges: List[str] = Field(default_factory=list, description="Challenges this role will address")


# ===== PROMPTS =====

COMPANY_RESEARCH_SYSTEM_PROMPT = """You are a business intelligence analyst researching companies for job seekers.
Your task is to find and synthesize information about a company using STRATEGIC WEB SEARCHES.

**SEARCH STRATEGY (execute queries in this order):**
1. Official site: "{company_name}" (about OR careers OR company)
2. LinkedIn: site:linkedin.com/company "{company_name}"
3. Financial data: site:crunchbase.com "{company_name}"
4. Recent news: "{company_name}" (funding OR acquisition OR partnership) after:2024-01-01
5. Agency detection: "{company_name}" (staffing OR recruitment OR "on behalf of")

**SEARCH OPTIMIZATION RULES:**
- Always quote company names for exact matching: "Seven.One Entertainment"
- Use site: operator for trusted sources: site:linkedin.com, site:crunchbase.com
- Use OR operator for comprehensive coverage: (funding OR raised OR series)
- Use after:YYYY-MM-DD for recent information: after:2024-01-01
- If a search returns no results, try name variations (abbreviations, without Inc/LLC/Ltd)

**HANDLING SEARCH FAILURES:**
- If official site not found: Try without quotes or with common variations
- If LinkedIn fails: Try company name + "linkedin" without site: operator
- If no recent news: Expand to after:2023-01-01
- If ALL searches fail: Return minimal response with summary = "Limited information available"

**ANTI-HALLUCINATION RULES:**
1. Only include information you ACTUALLY FIND from web searches - NO invention
2. Every signal MUST have a verifiable source URL from search results
3. If you can't find information, explicitly say "unknown" rather than guessing
4. Focus on business signals: funding, acquisitions, leadership changes, product launches, partnerships, growth
5. Detect if this is a recruitment agency (staffing firm) vs direct employer based on evidence

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
    "summary": "2-3 sentence company overview based on what you found",
    "signals": [
        {
            "type": "funding|acquisition|leadership_change|product_launch|partnership|growth",
            "description": "Brief factual description with specifics",
            "date": "YYYY-MM-DD or YYYY-MM or unknown",
            "source": "Full URL where you found this exact information",
            "business_context": "What this signal reveals about company trajectory"
        }
    ],
    "url": "https://company-website.com",
    "company_type": "employer|recruitment_agency|unknown"
}"""

PEOPLE_RESEARCH_SYSTEM_PROMPT = """You are a professional networking researcher helping job seekers identify key contacts.
Your task is to find relevant people at a company using STRATEGIC LINKEDIN-FOCUSED SEARCHES.

**SEARCH STRATEGY (execute queries in this order):**
1. Hiring manager: site:linkedin.com/in "{company_name}" ({role} manager OR VP OR director OR head)
2. Recruiters: site:linkedin.com/in "{company_name}" (recruiter OR "talent acquisition" OR "talent partner")
3. Team leads: site:linkedin.com/in "{company_name}" (senior OR lead OR principal) {department}
4. Hiring posts: "{company_name}" "we're hiring" OR "join our team" site:linkedin.com

**SEARCH OPTIMIZATION RULES:**
- Always quote company names for exact matching: "Acme Corp"
- Use site:linkedin.com/in for individual profiles
- Use OR operator for role variations: (VP OR director OR head of)
- Combine company + department + seniority: "{company}" engineering (VP OR director)
- If no results, try without site: operator or broader search terms

**HANDLING SEARCH FAILURES:**
- If specific title search fails: Try broader department search
- If LinkedIn blocked: Search for company + team + names without site: operator
- If no contacts found: Look for company blog, about page, or team page
- If ALL searches fail: Return empty arrays (do NOT invent people)

**ANTI-HALLUCINATION RULES:**
1. Only include REAL people you ACTUALLY FIND from web searches
2. LinkedIn URLs must come from actual search results - never construct them
3. Never invent names, roles, or contact details
4. If you can't find contacts, return empty arrays rather than making up people
5. Mark uncertain information appropriately

**CONTACT PRIORITIZATION:**
- Primary (max 3): Direct hiring manager, VP of relevant department, HR/Recruiting lead
- Secondary (max 2): Senior team members, potential colleagues, other department heads

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
    "primary_contacts": [
        {
            "name": "Full Name from search results",
            "role": "Job Title as found",
            "company": "Company Name",
            "why_relevant": "Why this person matters for the job seeker",
            "linkedin_url": "Actual URL from search results or null",
            "email": "Email if publicly found or null"
        }
    ],
    "secondary_contacts": [...]
}"""

ROLE_RESEARCH_SYSTEM_PROMPT = """You are a career research analyst helping job seekers understand roles at companies.
Your task is to research what a specific role means at a particular company using STRATEGIC SEARCHES.

**SEARCH STRATEGY (execute queries in this order):**
1. Team/department: site:linkedin.com/company "{company_name}" {department} team
2. Recent hires: "{company_name}" hired OR "joined as" "{role_title}" site:linkedin.com
3. Tech/projects: "{company_name}" (engineering blog OR tech stack OR architecture)
4. Company growth: "{company_name}" (expansion OR growing OR hiring) {department}

**SEARCH OPTIMIZATION RULES:**
- Quote company and role names for exact matching
- Use site: operator for reliable sources (LinkedIn, company blog)
- Look for recent posts/announcements about the team or role
- Search for engineering blogs if technical role
- If no results, broaden search without site: restrictions

**HANDLING SEARCH FAILURES:**
- If team info not found: Search for department + company + recent projects
- If no tech blog: Look for GitHub org or conference talks
- If hiring context unclear: Check company news for growth/funding signals
- If ALL fail: Return partial data with "unknown" for missing fields

**ANTI-HALLUCINATION RULES:**
1. Only include information you ACTUALLY FIND from searches
2. If you can't find "why now" reasons, say "unknown" or leave empty
3. Don't invent team structure or challenges - base on evidence
4. Focus on business impact backed by findings

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
    "business_impact": ["Specific impact backed by search findings", ...],
    "why_now": "Why hiring now (based on evidence) or 'unknown'",
    "team_context": "Team info from searches or 'unknown'",
    "challenges": ["Challenge based on findings", ...]
}"""


# ===== RESULT DATACLASS =====

@dataclass
class WebResearchResult:
    """Result of a web research operation."""
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]
    model: str
    tier: str
    duration_ms: int
    researched_at: str
    searches_performed: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    partial: bool = False  # True if data is partial (validation failed but some fields extracted)
    quality_score: float = 0.0  # 0-1 based on completeness/freshness

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def calculate_quality_score(data: Optional[Dict[str, Any]], research_type: str = "company") -> float:
    """
    Calculate a quality score for research results based on completeness and freshness.

    Score ranges from 0.0 (poor quality) to 1.0 (high quality).

    Scoring factors:
    - Company: summary present (+0.2), 3+ signals (+0.3), recent signals (+0.3), diverse sources (+0.2)
    - People: primary contacts found (+0.4), secondary contacts (+0.2), LinkedIn URLs (+0.2), role relevance (+0.2)
    - Role: business impact (+0.3), why now (+0.3), team context (+0.2), challenges (+0.2)
    """
    if not data:
        return 0.0

    score = 0.0

    if research_type == "company":
        # Summary present
        if data.get("summary") and len(str(data.get("summary", ""))) >= 20:
            score += 0.2

        # Has signals
        signals = data.get("signals", [])
        if len(signals) >= 3:
            score += 0.3

        # Recent signals (2024+)
        recent = [s for s in signals if isinstance(s, dict) and "2024" in str(s.get("date", ""))]
        if recent:
            score += 0.3

        # Diverse sources
        unique_sources = len(set(s.get("source", "") for s in signals if isinstance(s, dict)))
        if unique_sources >= 3:
            score += 0.2

    elif research_type == "people":
        primary = data.get("primary_contacts", [])
        secondary = data.get("secondary_contacts", [])

        # Has primary contacts
        if len(primary) >= 1:
            score += 0.4

        # Has secondary contacts
        if len(secondary) >= 1:
            score += 0.2

        # Has LinkedIn URLs
        all_contacts = primary + secondary
        has_linkedin = any(c.get("linkedin_url") for c in all_contacts if isinstance(c, dict))
        if has_linkedin:
            score += 0.2

        # Has relevance explanations
        has_relevance = any(c.get("why_relevant") for c in all_contacts if isinstance(c, dict))
        if has_relevance:
            score += 0.2

    elif research_type == "role":
        # Business impact
        if data.get("business_impact") and len(data.get("business_impact", [])) >= 1:
            score += 0.3

        # Why now
        if data.get("why_now") and len(str(data.get("why_now", ""))) >= 10:
            score += 0.3

        # Team context
        if data.get("team_context") and len(str(data.get("team_context", ""))) >= 10:
            score += 0.2

        # Challenges
        if data.get("challenges") and len(data.get("challenges", [])) >= 1:
            score += 0.2

    return min(score, 1.0)


class ClaudeWebResearcher:
    """
    Claude API client with web search capabilities for company/role/people research.

    Uses Claude's built-in web_search tool to find and synthesize information.
    Supports three model tiers for cost/quality tradeoffs.

    Attributes:
        tier: Model tier ("fast", "balanced", "quality")
        model: Actual Claude model ID
        max_searches: Maximum web searches per research operation
    """

    def __init__(
        self,
        tier: TierType = "balanced",
        max_searches: int = 8,
        timeout: int = 120,
    ):
        """
        Initialize the Claude web researcher.

        Uses Claude CLI via UnifiedLLM with ANTHROPIC_AUTH_TOKEN for web research.
        WebSearch is enabled via --dangerously-skip-permissions flag in CLI.

        Args:
            tier: Model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus)
            max_searches: Maximum web searches per operation (default 8)
            timeout: Request timeout in seconds (default 120)
        """
        self.tier = tier
        self.model = self._get_model_for_tier(tier)
        self.max_searches = max_searches
        self.timeout = timeout
        # Map tier names to UnifiedLLM tier names
        self._unified_tier_map = {
            "fast": "low",
            "balanced": "middle",
            "quality": "high",
        }

    def _get_model_for_tier(self, tier: TierType) -> str:
        """Get Claude model ID for the given tier."""
        return CLAUDE_MODEL_TIERS.get(tier, CLAUDE_MODEL_TIERS["balanced"])

    def _invoke_cli_research(
        self,
        system_prompt: str,
        user_prompt: str,
        research_type: str = "company",
        job_id: str = "unknown",
    ) -> LLMResult:
        """
        Invoke Claude CLI for web research via UnifiedLLM.

        Uses Claude CLI with --dangerously-skip-permissions to enable WebSearch.
        This routes through the ANTHROPIC_AUTH_TOKEN (Max subscription, $0 cost).

        Args:
            system_prompt: System prompt for the research
            user_prompt: User prompt with specific request
            research_type: Type of research (for logging)
            job_id: Job ID for tracking

        Returns:
            LLMResult with research content and backend attribution

        Raises:
            RuntimeError: If research fails (propagated to console)
        """
        # Combine prompts - CLI doesn't have separate system prompt in headless mode
        combined_prompt = f"""{system_prompt}

---

{user_prompt}

IMPORTANT: Use WebSearch to find current information. Return your findings as valid JSON."""

        # Map tier to UnifiedLLM tier
        unified_tier = self._unified_tier_map.get(self.tier, "middle")

        # Invoke via UnifiedLLM (routes to Claude CLI with WebSearch enabled)
        result = invoke_unified_sync(
            prompt=combined_prompt,
            step_name=f"research_{research_type}",
            tier=unified_tier,
            job_id=job_id,
            validate_json=True,  # Parse JSON response
        )

        # Propagate errors to console as requested
        if not result.success:
            raise RuntimeError(f"Research failed ({research_type}): {result.error}")

        logger.info(
            f"Research complete: type={research_type}, backend={result.backend}, "
            f"model={result.model}, duration={result.duration_ms}ms"
        )

        return result

    def _extract_partial_data(
        self,
        data: Dict[str, Any],
        schema: type[BaseModel],
    ) -> Optional[Dict[str, Any]]:
        """
        Extract partial data when full schema validation fails.

        Tries to salvage useful fields even when the full response doesn't validate.
        This prevents complete data loss for minor schema issues.

        Args:
            data: Raw parsed JSON data
            schema: The target Pydantic schema

        Returns:
            Dictionary with extracted fields, or None if insufficient data
        """
        partial = {}

        # Common extraction for all schemas
        if "summary" in data and isinstance(data.get("summary"), str):
            if len(data["summary"]) >= 5:  # More lenient than schema
                partial["summary"] = data["summary"]

        if "url" in data and isinstance(data.get("url"), str):
            partial["url"] = data["url"]

        # CompanyResearchModel fields
        if schema == CompanyResearchModel:
            if "signals" in data and isinstance(data.get("signals"), list):
                # Extract valid signals, skip malformed ones
                valid_signals = []
                for sig in data["signals"][:10]:  # Limit to max_length
                    if isinstance(sig, dict) and sig.get("text"):
                        valid_signals.append({
                            "text": sig.get("text", ""),
                            "source": sig.get("source", "unknown"),
                            "date": sig.get("date"),
                            "signal_type": sig.get("signal_type", "general"),
                            "is_warning": sig.get("is_warning", False),
                        })
                if valid_signals:
                    partial["signals"] = valid_signals

            partial.setdefault("company_type", data.get("company_type", "employer"))
            partial.setdefault("url", data.get("url", ""))

            # Require at least summary or signals for partial success
            if partial.get("summary") or partial.get("signals"):
                logger.warning(f"Extracted partial company data: {list(partial.keys())}")
                return partial

        # PeopleResearchModel fields
        elif schema == PeopleResearchModel:
            for field in ["primary_contacts", "secondary_contacts"]:
                if field in data and isinstance(data.get(field), list):
                    valid_contacts = []
                    for contact in data[field][:5]:
                        if isinstance(contact, dict) and contact.get("name"):
                            valid_contacts.append({
                                "name": contact.get("name", ""),
                                "role": contact.get("role", "Unknown"),
                                "company": contact.get("company", ""),
                                "why_relevant": contact.get("why_relevant", "Discovered during research"),
                                "linkedin_url": contact.get("linkedin_url"),
                                "email": contact.get("email"),
                            })
                    if valid_contacts:
                        partial[field] = valid_contacts

            # Require at least one contact for partial success
            if partial.get("primary_contacts") or partial.get("secondary_contacts"):
                logger.warning(f"Extracted partial people data: {len(partial.get('primary_contacts', []))} primary, {len(partial.get('secondary_contacts', []))} secondary")
                return partial

        # RoleResearchModel fields
        elif schema == RoleResearchModel:
            if "business_impact" in data and isinstance(data.get("business_impact"), list):
                partial["business_impact"] = [str(x) for x in data["business_impact"] if x][:5]
            if "challenges" in data and isinstance(data.get("challenges"), list):
                partial["challenges"] = [str(x) for x in data["challenges"] if x][:5]
            if "why_now" in data:
                partial["why_now"] = str(data.get("why_now", ""))
            if "team_context" in data:
                partial["team_context"] = str(data.get("team_context", ""))

            # Require at least one meaningful field for partial success
            if any(partial.get(k) for k in ["business_impact", "why_now", "challenges"]):
                logger.warning(f"Extracted partial role data: {list(partial.keys())}")
                return partial

        return None

    def _parse_response(
        self,
        response: Any,
        schema: type[BaseModel],
    ) -> tuple[Optional[Dict[str, Any]], int, bool]:
        """
        Parse Claude API response and validate against schema.

        Attempts partial extraction on validation failure to salvage useful data.

        Args:
            response: Claude API response object
            schema: Pydantic model to validate against

        Returns:
            Tuple of (parsed_data, search_count, is_partial)
            - is_partial=False for fully validated data
            - is_partial=True for partially extracted data
        """
        # Extract text content from response
        text_content = None
        search_count = 0

        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    text_content = block.text
                elif block.type == "tool_use" and getattr(block, "name", None) == "web_search":
                    search_count += 1

        if not text_content:
            raise ValueError("No text content in response")

        # Parse JSON from response
        try:
            data = parse_llm_json(text_content)
        except ValueError as e:
            raise ValueError(f"Failed to parse response JSON: {e}")

        # Validate against schema
        try:
            validated = schema(**data)
            return validated.model_dump(), search_count, False  # Full validation success
        except ValidationError as e:
            # Try partial extraction before giving up
            partial_data = self._extract_partial_data(data, schema)
            if partial_data:
                logger.info(f"Using partial data extraction after validation failure")
                return partial_data, search_count, True  # Partial extraction success

            # No partial data could be extracted, raise original error
            error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise ValueError(f"Schema validation failed:\n" + "\n".join(f"  - {msg}" for msg in error_msgs))

    async def research_company(
        self,
        company_name: str,
        job_context: str = "",
        job_title: str = "",
    ) -> WebResearchResult:
        """
        Research a company using web search.

        Args:
            company_name: Name of the company to research
            job_context: Optional context about the job (JD summary)
            job_title: Optional job title for context

        Returns:
            WebResearchResult with CompanyResearch data
        """
        start_time = datetime.utcnow()

        # Build the user prompt with search query suggestions
        user_prompt = f'''Research the company "{company_name}" for a job seeker.

**CONTEXT:**
- Company: {company_name}
{f"- Job Title: {job_title}" if job_title else ""}
{f"- Job Context: {job_context[:500]}..." if job_context else ""}

**SUGGESTED SEARCH QUERIES (try these in order):**
1. "{company_name}" about company overview
2. site:linkedin.com/company "{company_name}"
3. site:crunchbase.com "{company_name}"
4. "{company_name}" (funding OR acquisition OR partnership) after:2024-01-01
5. "{company_name}" (staffing OR recruitment OR "on behalf of") -job -careers

**IF SEARCHES FAIL, TRY VARIATIONS:**
- Without quotes: {company_name} company
- Shorter name: {company_name.split()[0] if ' ' in company_name else company_name}
- With industry: "{company_name}" {job_title.split()[0] if job_title else "technology"}

**RESEARCH GOALS:**
1. Company overview and what they do
2. Recent news (funding, acquisitions, product launches)
3. Leadership and team information
4. Whether this is a direct employer or recruitment agency

Return structured JSON with your findings.'''

        try:
            # Call Claude API with web search tool (with retry on transient failures)
            response = self._call_api_with_retry(
                system_prompt=COMPANY_RESEARCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                research_type="company",
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse and validate response (with partial extraction fallback)
            data, search_count, is_partial = self._parse_response(response, CompanyResearchModel)

            return WebResearchResult(
                success=True,
                data=data,
                error=None,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                researched_at=start_time.isoformat(),
                searches_performed=search_count,
                input_tokens=response.usage.input_tokens if hasattr(response, "usage") else None,
                output_tokens=response.usage.output_tokens if hasattr(response, "usage") else None,
                partial=is_partial,
                quality_score=calculate_quality_score(data, "company"),
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            logger.error(f"Company research failed for {company_name}: {e}")
            return WebResearchResult(
                success=False,
                data=None,
                error=str(e),
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                researched_at=start_time.isoformat(),
            )

    async def research_people(
        self,
        company_name: str,
        role: str,
        department: str = "",
    ) -> WebResearchResult:
        """
        Research key people at a company for networking.

        Args:
            company_name: Name of the company
            role: The role the job seeker is applying for
            department: Optional department context

        Returns:
            WebResearchResult with PeopleResearch data
        """
        start_time = datetime.utcnow()

        # Build the user prompt with LinkedIn-optimized search queries
        # Extract department keywords for more targeted searches
        dept_keywords = department if department else role.split()[0] if role else "engineering"

        user_prompt = f'''Find key contacts at "{company_name}" relevant to someone applying for a {role} position.

**CONTEXT:**
- Company: {company_name}
- Target Role: {role}
{f"- Department: {department}" if department else ""}

**SUGGESTED SEARCH QUERIES (LinkedIn-focused):**
1. site:linkedin.com/in "{company_name}" ({dept_keywords} manager OR director OR VP)
2. site:linkedin.com/in "{company_name}" (recruiter OR talent acquisition)
3. site:linkedin.com/in "{company_name}" (senior OR lead) {dept_keywords}
4. "{company_name}" "we're hiring" {role} site:linkedin.com

**IF NO RESULTS, TRY BROADER SEARCHES:**
- "{company_name}" hiring team linkedin
- "{company_name}" {dept_keywords} team lead

**TARGET CONTACTS (in priority order):**
1. Hiring managers or VPs in relevant departments
2. HR/Recruiting leads
3. Senior engineers or team leads who might be colleagues
4. Anyone who has posted about hiring for similar roles

Prioritize LinkedIn profiles and professional information.
Return structured JSON with primary (decision makers) and secondary (potential colleagues) contacts.'''

        try:
            # Use retry helper for resilience against transient failures
            response = self._call_api_with_retry(
                system_prompt=PEOPLE_RESEARCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                research_type="people",
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse and validate response (with partial extraction fallback)
            data, search_count, is_partial = self._parse_response(response, PeopleResearchModel)

            return WebResearchResult(
                success=True,
                data=data,
                error=None,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                researched_at=start_time.isoformat(),
                searches_performed=search_count,
                input_tokens=response.usage.input_tokens if hasattr(response, "usage") else None,
                output_tokens=response.usage.output_tokens if hasattr(response, "usage") else None,
                partial=is_partial,
                quality_score=calculate_quality_score(data, "people"),
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            logger.error(f"People research failed for {company_name}: {e}")
            return WebResearchResult(
                success=False,
                data=None,
                error=str(e),
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                researched_at=start_time.isoformat(),
            )

    async def research_role(
        self,
        company_name: str,
        role_title: str,
        job_description: str = "",
    ) -> WebResearchResult:
        """
        Research what a specific role means at a company.

        Args:
            company_name: Name of the company
            role_title: The job title/role
            job_description: Optional JD for context

        Returns:
            WebResearchResult with RoleResearch data
        """
        start_time = datetime.utcnow()

        # Build the user prompt with team/role-focused search queries
        # Extract role keywords for targeted searches
        role_keywords = role_title.split()[0] if role_title else "engineering"

        user_prompt = f'''Research what a "{role_title}" role means at "{company_name}".

**CONTEXT:**
- Company: {company_name}
- Role: {role_title}
{f"- Job Description Summary: {job_description[:500]}..." if job_description else ""}

**SUGGESTED SEARCH QUERIES:**
1. site:linkedin.com/company "{company_name}" {role_keywords} team
2. "{company_name}" hired "{role_title}" site:linkedin.com
3. "{company_name}" engineering blog OR tech stack
4. "{company_name}" {role_keywords} projects OR initiatives

**IF NO RESULTS, TRY:**
- "{company_name}" team structure
- "{company_name}" hiring growth

**RESEARCH GOALS:**
1. What this team/department does at the company
2. Recent projects or initiatives they're working on
3. Why they might be hiring (growth, new projects, backfill)
4. Team structure and who this role reports to

Return structured JSON with business impact, why now, team context, and challenges.'''

        try:
            # Use retry helper for resilience against transient failures
            response = self._call_api_with_retry(
                system_prompt=ROLE_RESEARCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                research_type="role",
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse and validate response (with partial extraction fallback)
            data, search_count, is_partial = self._parse_response(response, RoleResearchModel)

            return WebResearchResult(
                success=True,
                data=data,
                error=None,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                researched_at=start_time.isoformat(),
                searches_performed=search_count,
                input_tokens=response.usage.input_tokens if hasattr(response, "usage") else None,
                output_tokens=response.usage.output_tokens if hasattr(response, "usage") else None,
                partial=is_partial,
                quality_score=calculate_quality_score(data, "role"),
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            logger.error(f"Role research failed for {role_title} at {company_name}: {e}")
            return WebResearchResult(
                success=False,
                data=None,
                error=str(e),
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                researched_at=start_time.isoformat(),
            )

    def check_api_available(self) -> bool:
        """
        Check if Claude API is available and authenticated.

        Returns:
            True if API is accessible
        """
        try:
            # Simple test call
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Say 'ok'"}],
            )
            return True
        except Exception as e:
            logger.warning(f"Claude API not available: {e}")
            return False

    @staticmethod
    def get_tier_display_info() -> list:
        """
        Get tier information for UI display.

        Returns:
            List of tier display dictionaries
        """
        return [
            {
                "value": "fast",
                "label": "Fast",
                "model": "Claude Haiku 4.5",
                "description": "Quick research, lower cost",
                "badge": "~$0.02/research",
            },
            {
                "value": "balanced",
                "label": "Balanced (Default)",
                "model": "Claude Sonnet 4.5",
                "description": "Thorough research, best value",
                "badge": "~$0.10/research",
            },
            {
                "value": "quality",
                "label": "Quality",
                "model": "Claude Opus 4.5",
                "description": "Deep research, highest quality",
                "badge": "~$0.50/research",
            },
        ]


# Convenience async functions for quick usage

async def research_company(
    company_name: str,
    job_context: str = "",
    tier: TierType = "balanced",
) -> WebResearchResult:
    """Convenience function for company research."""
    researcher = ClaudeWebResearcher(tier=tier)
    return await researcher.research_company(company_name, job_context)


async def research_people(
    company_name: str,
    role: str,
    tier: TierType = "balanced",
) -> WebResearchResult:
    """Convenience function for people research."""
    researcher = ClaudeWebResearcher(tier=tier)
    return await researcher.research_people(company_name, role)


async def research_role(
    company_name: str,
    role_title: str,
    tier: TierType = "balanced",
) -> WebResearchResult:
    """Convenience function for role research."""
    researcher = ClaudeWebResearcher(tier=tier)
    return await researcher.research_role(company_name, role_title)
