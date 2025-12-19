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
from dataclasses import dataclass, asdict
from pydantic import BaseModel, Field, ValidationError

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from src.common.json_utils import parse_llm_json


logger = logging.getLogger(__name__)


# ===== CLAUDE MODEL TIERS =====

CLAUDE_MODEL_TIERS = {
    "fast": "claude-haiku-4-5-20251101",
    "balanced": "claude-sonnet-4-5-20251101",
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
Your task is to find and synthesize information about a company from web searches.

IMPORTANT GUIDELINES:
1. Only include information you actually find from web searches - NO hallucination
2. Every signal must have a source URL from the search results
3. If you can't find information, say "unknown" rather than guessing
4. Focus on business signals: funding, acquisitions, leadership changes, product launches, partnerships, growth indicators
5. Detect if this is a recruitment agency (staffing firm) vs direct employer

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
    "summary": "2-3 sentence company overview",
    "signals": [
        {
            "type": "funding|acquisition|leadership_change|product_launch|partnership|growth",
            "description": "Brief description",
            "date": "YYYY-MM-DD or unknown",
            "source": "URL where you found this",
            "business_context": "What this means for the company"
        }
    ],
    "url": "https://company-website.com",
    "company_type": "employer|recruitment_agency|unknown"
}"""

PEOPLE_RESEARCH_SYSTEM_PROMPT = """You are a professional networking researcher helping job seekers identify key contacts.
Your task is to find relevant people at a company who might be involved in hiring or working with a specific role.

IMPORTANT GUIDELINES:
1. Only include real people you find from web searches - NO hallucination
2. Focus on: hiring managers, team leads, HR/recruiters, and potential colleagues
3. Prioritize people who would be decision makers for the given role
4. LinkedIn URLs should be from actual search results
5. Never invent contact details - only include what you find

CONTACT PRIORITIZATION:
- Primary: Direct hiring manager, VP of relevant department, HR/Recruiting lead
- Secondary: Senior team members, other department heads who might collaborate

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
    "primary_contacts": [
        {
            "name": "Full Name",
            "role": "Job Title",
            "company": "Company Name",
            "why_relevant": "Why this person matters for the job seeker",
            "linkedin_url": "URL if found or null",
            "email": "Email if publicly available or null"
        }
    ],
    "secondary_contacts": [...]
}"""

ROLE_RESEARCH_SYSTEM_PROMPT = """You are a career research analyst helping job seekers understand roles at companies.
Your task is to research what a specific role means at a particular company.

IMPORTANT GUIDELINES:
1. Use web searches to find information about the role and team
2. Look for: team structure, recent projects, challenges, why they're hiring
3. Only include information you actually find - NO hallucination
4. Focus on business impact and context

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
    "business_impact": ["Impact 1", "Impact 2", ...],
    "why_now": "Why the company is hiring for this role now",
    "team_context": "Context about the team this role joins",
    "challenges": ["Challenge this role will address", ...]
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


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

        Args:
            tier: Model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus)
            max_searches: Maximum web searches per operation (default 8)
            timeout: Request timeout in seconds (default 120)
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        self.tier = tier
        self.model = self._get_model_for_tier(tier)
        self.max_searches = max_searches
        self.timeout = timeout
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            timeout=timeout,
        )

    def _get_model_for_tier(self, tier: TierType) -> str:
        """Get Claude model ID for the given tier."""
        return CLAUDE_MODEL_TIERS.get(tier, CLAUDE_MODEL_TIERS["balanced"])

    def _create_web_search_tool(self) -> Dict[str, Any]:
        """Create the web search tool configuration for Claude API."""
        return {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": self.max_searches,
        }

    def _parse_response(
        self,
        response: Any,
        schema: type[BaseModel],
    ) -> tuple[Optional[Dict[str, Any]], int]:
        """
        Parse Claude API response and validate against schema.

        Args:
            response: Claude API response object
            schema: Pydantic model to validate against

        Returns:
            Tuple of (parsed_data, search_count)
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
            return validated.model_dump(), search_count
        except ValidationError as e:
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

        # Build the user prompt
        user_prompt = f"""Research the company "{company_name}" for a job seeker.

Company: {company_name}
{f'Job Title: {job_title}' if job_title else ''}
{f'Job Context: {job_context[:500]}...' if job_context else ''}

Please search the web for:
1. Company overview and what they do
2. Recent news (funding, acquisitions, product launches)
3. Leadership and team information
4. Whether this is a direct employer or recruitment agency

Return structured JSON with your findings."""

        try:
            # Call Claude API with web search tool
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=COMPANY_RESEARCH_SYSTEM_PROMPT,
                tools=[self._create_web_search_tool()],
                messages=[{"role": "user", "content": user_prompt}],
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse and validate response
            data, search_count = self._parse_response(response, CompanyResearchModel)

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

        # Build the user prompt
        user_prompt = f"""Find key contacts at "{company_name}" relevant to someone applying for a {role} position.

Company: {company_name}
Target Role: {role}
{f'Department: {department}' if department else ''}

Please search for:
1. Hiring managers or VPs in relevant departments
2. HR/Recruiting leads
3. Senior engineers or team leads who might be colleagues
4. Anyone who has posted about hiring for similar roles

Prioritize LinkedIn profiles and professional information.
Return structured JSON with primary (decision makers) and secondary (potential colleagues) contacts."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=PEOPLE_RESEARCH_SYSTEM_PROMPT,
                tools=[self._create_web_search_tool()],
                messages=[{"role": "user", "content": user_prompt}],
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse and validate response
            data, search_count = self._parse_response(response, PeopleResearchModel)

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

        # Build the user prompt
        user_prompt = f"""Research what a "{role_title}" role means at "{company_name}".

Company: {company_name}
Role: {role_title}
{f'Job Description Summary: {job_description[:500]}...' if job_description else ''}

Please search for:
1. What this team/department does at the company
2. Recent projects or initiatives they're working on
3. Why they might be hiring (growth, new projects, backfill)
4. Team structure and who this role reports to

Return structured JSON with business impact, why now, team context, and challenges."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=ROLE_RESEARCH_SYSTEM_PROMPT,
                tools=[self._create_web_search_tool()],
                messages=[{"role": "user", "content": user_prompt}],
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse and validate response
            data, search_count = self._parse_response(response, RoleResearchModel)

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
