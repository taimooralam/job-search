"""
Layer 3: Company Researcher

Phase 5.1 Update: Multi-source scraping with structured signal extraction.
- Scrapes 4 sources: official site, LinkedIn, Crunchbase, news
- Extracts structured signals (funding, acquisitions, leadership changes, etc.)
- JSON-only output with Pydantic validation
- Enhanced MongoDB caching with full CompanyResearch structure
- Hallucination prevention with source attribution

Previous Phase 1.3: Added MongoDB caching with 7-day TTL.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError
from firecrawl import FirecrawlApp
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from pymongo import MongoClient

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.state import JobState, CompanySignal, CompanyResearch
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.common.utils import run_async
from src.common.claude_web_research import ClaudeWebResearcher, TierType, CLAUDE_MODEL_TIERS
from src.common.unified_llm import UnifiedLLM, invoke_unified_sync


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
        >>> search_response = app.search("company news")
        >>> results = _extract_search_results(search_response)
        >>> for result in results:
        ...     print(result.url, result.markdown)
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


# ===== PYDANTIC SCHEMA VALIDATION (Phase 5.1) =====

class ReasoningBlockModel(BaseModel):
    """Pydantic model for reasoning block (Phase 5.2 enhanced prompts)."""
    sources_analyzed: List[str] = Field(default_factory=list, description="URLs analyzed")
    source_quality: Dict[str, str] = Field(default_factory=dict, description="Quality assessment per source")
    missing_context: List[str] = Field(default_factory=list, description="Information gaps identified")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made")
    confidence_level: str = Field(default="unknown", description="Overall confidence: high/medium/low")


class CompanySignalModel(BaseModel):
    """Pydantic model for company signal validation."""
    type: str = Field(..., description="Signal type: funding, acquisition, leadership_change, product_launch, partnership, growth")
    description: str = Field(..., min_length=1, description="Brief description of the signal")
    date: str = Field(default="unknown", description="ISO date or 'unknown'")
    source: str = Field(..., min_length=1, description="Source URL where signal was found")
    business_context: str = Field(default="", description="What this signal reveals about company trajectory")


class CompanyResearchOutput(BaseModel):
    """
    Pydantic schema for company research output (Phase 5.2 enhanced).

    ROADMAP Phase 5 Quality Gates:
    - JSON-only output (no text outside JSON object)
    - Structured signals with source attribution
    - No hallucinated facts (only from scraped content)
    - Each signal must have a source URL
    - Reasoning block for transparency (Phase 5.2)

    Schema Enforcement:
    - reasoning: Optional reasoning block (Phase 5.2+)
    - summary: 2-3 sentence company overview
    - signals: List of CompanySignal objects (0-10 items)
    - url: Primary company URL
    """
    reasoning: Optional[ReasoningBlockModel] = Field(default=None, description="Reasoning block for enhanced prompts")
    summary: str = Field(..., min_length=10, description="2-3 sentence company summary")
    signals: List[CompanySignalModel] = Field(default_factory=list, max_length=10, description="0-10 company signals with sources")
    url: str = Field(..., min_length=1, description="Primary company URL")


class CompanyTypeClassification(BaseModel):
    """
    Pydantic schema for company type classification (recruitment agency detection).

    Used to determine if a company is a direct employer or recruitment/staffing agency.
    This affects the depth of research and outreach strategy.
    """
    company_type: str = Field(
        ...,
        description="Classification: 'employer' | 'recruitment_agency' | 'unknown'"
    )
    confidence: str = Field(
        default="medium",
        description="Confidence level: 'high' | 'medium' | 'low'"
    )
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Brief explanation for the classification"
    )


# ===== PROMPT DESIGN =====

# Phase 5.1: Multi-source signal extraction prompts

SYSTEM_PROMPT_COMPANY_SIGNALS = """You are a business intelligence analyst. Extract company signals showing business momentum, strategic priorities, and culture fit. Prioritize facts over speculation.

**REASONING-FIRST APPROACH**:
Before output, analyze:
1. Source quality (high/medium/low per URL)
2. Missing context/information gaps
3. Assumptions made
4. Overall confidence (high/medium/low)

**ANTI-HALLUCINATION RULES**:
- Output ONLY valid JSON
- Use ONLY explicit facts from scraped content
- NEVER invent details not in sources
- Every signal MUST cite source URL
- Unknown details = "unknown", not guesses
- If unsure, say "I don't know" in reasoning

**SIGNAL TYPES**:
- "funding": Capital raises, investments → signals growth trajectory, runway
- "acquisition": M&A activity → signals strategy, market consolidation
- "leadership_change": Executive moves → signals strategy shifts, culture changes
- "product_launch": New offerings → signals innovation velocity
- "partnership": Strategic alliances → signals ecosystem positioning
- "growth": Headcount, revenue, expansion → signals scaling needs

**FEW-SHOT EXAMPLE**:

INPUT:
Company: Acme Corp
Content: "Acme Corp raised $50M Series B led by Sequoia in Jan 2024. Serves 10,000+ customers..."

OUTPUT:
{{
  "reasoning": {{
    "sources_analyzed": ["https://acme.com"],
    "source_quality": {{"https://acme.com": "high"}},
    "missing_context": ["competitor landscape"],
    "assumptions": [],
    "confidence_level": "high"
  }},
  "summary": "Acme Corp is a B2B SaaS company serving 10,000+ customers, recently raising $50M Series B.",
  "signals": [
    {{
      "type": "funding",
      "description": "Raised $50M Series B led by Sequoia in January 2024",
      "date": "2024-01",
      "source": "https://acme.com",
      "business_context": "Strong investor confidence; extended runway for growth"
    }}
  ],
  "url": "https://acme.com"
}}

**YOUR OUTPUT FORMAT** (ALL FIELDS REQUIRED):
{{
  "reasoning": {{
    "sources_analyzed": ["url1", "url2"],
    "source_quality": {{"url1": "high|medium|low"}},
    "missing_context": ["list of gaps"],
    "assumptions": ["list of assumptions"],
    "confidence_level": "high|medium|low"
  }},
  "summary": "2-3 sentences emphasizing market position",
  "signals": [{{type, description, date, source, business_context}}, ...],
  "url": "primary URL"
}}

**CRITICAL**: You MUST include ALL 4 fields (reasoning, summary, signals, url).
Do NOT return only the reasoning block - the full JSON with all fields is required.

**BEST-EFFORT EXTRACTION**:
- Extract AT LEAST ONE signal if ANY facts exist
- General facts count as "growth" signals
- Empty signals only if content is completely non-informational

NO TEXT OUTSIDE JSON."""

# Phase 5 enhancement: STAR-aware signal extraction prompts (IMPROVED with reasoning-first)
SYSTEM_PROMPT_COMPANY_SIGNALS_STAR_AWARE = """You are a business intelligence analyst. Extract company signals showing business momentum, strategic priorities, and culture fit. Prioritize facts over speculation.

**CANDIDATE CONTEXT** (prioritize signals in these domains):
{candidate_domains}
{candidate_outcomes}

**REASONING-FIRST APPROACH**:
Before output, analyze:
1. Source quality (high/medium/low per URL)
2. Missing context/information gaps
3. Assumptions made
4. Overall confidence (high/medium/low)

**ANTI-HALLUCINATION RULES**:
- Output ONLY valid JSON
- Use ONLY explicit facts from scraped content
- NEVER invent details not in sources
- Every signal MUST cite source URL
- Unknown details = "unknown", not guesses
- If unsure, say "I don't know" in reasoning

**SIGNAL TYPES**:
- "funding": Capital raises, investments → signals growth trajectory, runway
- "acquisition": M&A activity → signals strategy, market consolidation
- "leadership_change": Executive moves → signals strategy shifts, culture changes
- "product_launch": New offerings → signals innovation velocity
- "partnership": Strategic alliances → signals ecosystem positioning
- "growth": Headcount, revenue, expansion → signals scaling needs

**FEW-SHOT EXAMPLE**:

INPUT:
Company: Acme Corp
Content: "Acme Corp raised $50M Series B led by Sequoia in Jan 2024. Serves 10,000+ customers..."

OUTPUT:
{{
  "reasoning": {{
    "sources_analyzed": ["https://acme.com"],
    "source_quality": {{"https://acme.com": "high"}},
    "missing_context": ["competitor landscape"],
    "assumptions": [],
    "confidence_level": "high"
  }},
  "summary": "Acme Corp is a B2B SaaS company serving 10,000+ customers, recently raising $50M Series B.",
  "signals": [
    {{
      "type": "funding",
      "description": "Raised $50M Series B led by Sequoia in January 2024",
      "date": "2024-01",
      "source": "https://acme.com",
      "business_context": "Strong investor confidence; extended runway for growth"
    }}
  ],
  "url": "https://acme.com"
}}

**YOUR OUTPUT FORMAT** (ALL FIELDS REQUIRED):
{{
  "reasoning": {{
    "sources_analyzed": ["url1", "url2"],
    "source_quality": {{"url1": "high|medium|low"}},
    "missing_context": ["list of gaps"],
    "assumptions": ["list of assumptions"],
    "confidence_level": "high|medium|low"
  }},
  "summary": "2-3 sentences emphasizing market position",
  "signals": [{{type, description, date, source, business_context}}, ...],
  "url": "primary URL"
}}

**CRITICAL**: You MUST include ALL 4 fields (reasoning, summary, signals, url).
Do NOT return only the reasoning block - the full JSON with all fields is required.

**BEST-EFFORT EXTRACTION**:
- Extract AT LEAST ONE signal if ANY facts exist
- General facts count as "growth" signals
- Empty signals only if content is completely non-informational

NO TEXT OUTSIDE JSON."""

USER_PROMPT_COMPANY_SIGNALS_TEMPLATE = """Analyze the following scraped content and extract company signals:

COMPANY: {company}

SCRAPED CONTENT FROM MULTIPLE SOURCES:
{scraped_content}

Extract:
1. summary: 2-3 sentence overview of the company
2. signals: List of business signals with type, description, date, source
3. url: Primary company URL

JSON only - no additional text:"""

# ===== COMPANY TYPE CLASSIFICATION PROMPT =====

SYSTEM_PROMPT_COMPANY_TYPE = """You are a business analyst classifying companies as direct employers or recruitment/staffing agencies.

**CLASSIFICATION CRITERIA:**

RECRUITMENT AGENCY indicators:
- Company name contains: staffing, recruitment, recruiting, talent, placement, search, headhunters
- Company provides staffing/recruitment services to other companies
- Job description mentions "client", "on behalf of", "multiple clients"
- Company specializes in placing candidates at other organizations
- Terms like "contract positions", "temp-to-perm", "consulting services"
- Company is known recruitment firm (Robert Half, Hays, Michael Page, Randstad, etc.)

DIRECT EMPLOYER indicators:
- Company has its own products or services (not recruitment)
- Job description describes internal team/department
- Company is hiring for their own operations
- Well-known companies in tech, finance, retail, etc. (Google, Amazon, etc.)

**OUTPUT FORMAT (JSON only):**
{
  "company_type": "employer" | "recruitment_agency" | "unknown",
  "confidence": "high" | "medium" | "low",
  "reasoning": "Brief explanation (1-2 sentences)"
}

Rules:
- Output ONLY valid JSON, no other text
- "high" confidence: Clear indicators present
- "medium" confidence: Some indicators but not definitive
- "low" confidence: Insufficient information
- When unsure, default to "employer" (most jobs are direct hires)
"""

USER_PROMPT_COMPANY_TYPE_TEMPLATE = """Classify this company:

COMPANY: {company}
JOB TITLE: {job_title}
JOB DESCRIPTION (excerpt):
{job_description}

Is this a recruitment/staffing agency or a direct employer hiring for their own team?

JSON only:"""


# Legacy prompts (Phase 1.3 - for fallback)

SYSTEM_PROMPT_SCRAPE = """You are a business research analyst specializing in company intelligence.

Your task: Summarize a company based on their website content in 2-3 clear, concise sentences.

Focus on:
- What the company does (products/services)
- Industry and market position
- Company size or notable facts (if mentioned)

Be factual and professional. No marketing fluff.
"""

USER_PROMPT_SCRAPE_TEMPLATE = """Based on this company website content, write a 2-3 sentence summary:

COMPANY: {company}
WEBSITE CONTENT:
{website_content}

Summary (2-3 sentences):
"""

SYSTEM_PROMPT_FALLBACK = """You are a business research analyst with broad knowledge of companies across industries.

Your task: Provide a brief 2-3 sentence summary of a company based on general knowledge.

If you don't have specific information, acknowledge it but provide what context you can (industry, type of business, etc.).
"""

USER_PROMPT_FALLBACK_TEMPLATE = """Provide a brief 2-3 sentence summary of this company:

COMPANY: {company}

If you have information about what they do, their industry, or notable facts, share it.
If not, acknowledge limited information but provide what context you can infer.

Summary (2-3 sentences):
"""


class CompanyResearcher:
    """
    Researches companies using web scraping and LLM analysis.
    Phase 1.3: Includes MongoDB caching to reduce FireCrawl costs.
    Phase 5 enhancement: STAR-aware prompts and defensive fallback.

    Supports two execution backends:
    - Claude API (default): Uses Claude API with WebSearch for research
    - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility
    """

    def __init__(
        self,
        tier: TierType = "balanced",
        use_claude_api: bool = True,
    ):
        """
        Initialize the company researcher.

        Args:
            tier: Claude model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus).
                  Only used when use_claude_api=True. Default is "balanced" (Sonnet 4.5).
            use_claude_api: If True (default), use Claude API with WebSearch.
                           If False, use FireCrawl + OpenRouter (legacy mode).
        """
        # Logger for internal operations (no run_id context yet)
        self.logger = logging.getLogger(__name__)
        self.tier = tier
        self.use_claude_api = use_claude_api

        if use_claude_api:
            # Claude API with WebSearch for research
            self.claude_researcher = ClaudeWebResearcher(tier=tier)
            self.firecrawl = None
            self.llm = None
        else:
            # Legacy mode: FireCrawl + OpenRouter
            self.claude_researcher = None
            # FireCrawl for web scraping
            self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)
            # LLM for summarization (GAP-066: Token tracking enabled)
            self.llm = create_tracked_llm(
                model=Config.DEFAULT_MODEL,
                temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for factual summaries
                layer="layer3_company",
            )

        # MongoDB for caching (Phase 1.3) - always enabled
        self.mongo_client = MongoClient(Config.MONGODB_URI)
        self.cache_collection = self.mongo_client["jobs"]["company_cache"]
        # Create TTL index on cached_at field (7 days)
        self.cache_collection.create_index("cached_at", expireAfterSeconds=7*24*60*60)

    def _classify_company_type(self, state: JobState) -> str:
        """
        Classify company as employer or recruitment agency using LLM.

        Uses job description and company name to determine if this is a
        direct employer or a recruitment/staffing agency. Agencies get
        minimal research and different outreach strategies.

        Migrated to UnifiedLLM: Uses step_name="classify_company_type" (low tier).

        Args:
            state: JobState with company, title, job_description

        Returns:
            "employer" | "recruitment_agency" | "unknown"
        """
        company = state.get("company", "")
        job_title = state.get("title", "")
        job_description = state.get("job_description", "")
        job_id = state.get("job_id", "unknown")

        # Quick heuristic check first (avoid LLM call for obvious cases)
        company_lower = company.lower()
        agency_keywords = [
            "staffing", "recruitment", "recruiting", "talent",
            "placement", "headhunter", "search firm", "hays",
            "robert half", "michael page", "randstad", "adecco",
            "manpower", "kelly services", "kforce"
        ]

        for keyword in agency_keywords:
            if keyword in company_lower:
                self.logger.info(f"Agency detected by keyword '{keyword}' in company name")
                return "recruitment_agency"

        # LLM classification for ambiguous cases using UnifiedLLM
        try:
            user_prompt = USER_PROMPT_COMPANY_TYPE_TEMPLATE.format(
                company=company,
                job_title=job_title,
                job_description=job_description[:800]  # Limit for token efficiency
            )

            # Use UnifiedLLM with step config for classify_company_type (low tier)
            result = invoke_unified_sync(
                prompt=user_prompt,
                step_name="classify_company_type",
                system=SYSTEM_PROMPT_COMPANY_TYPE,
                job_id=job_id,
                validate_json=True,
            )

            if not result.success:
                self.logger.warning(f"Company type classification LLM call failed: {result.error}, defaulting to 'employer'")
                return "employer"

            # Log backend attribution
            self.logger.info(f"Company type classification via {result.backend} ({result.model}) in {result.duration_ms}ms")

            # Parse and validate using parsed_json if available
            if result.parsed_json:
                data = result.parsed_json
            else:
                # Fallback to manual parsing
                llm_output = result.content.strip()
                if llm_output.startswith("```"):
                    llm_output = re.sub(r'^```(?:json)?\s*', '', llm_output)
                    llm_output = re.sub(r'\s*```$', '', llm_output)
                    llm_output = llm_output.strip()
                data = json.loads(llm_output)

            classification = CompanyTypeClassification(**data)

            self.logger.info(
                f"Company type classification: {classification.company_type} "
                f"(confidence: {classification.confidence}) - {classification.reasoning}"
            )

            return classification.company_type

        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.warning(f"Company type classification failed: {e}, defaulting to 'employer'")
            return "employer"
        except Exception as e:
            self.logger.warning(f"Company type classification error: {e}, defaulting to 'employer'")
            return "employer"

    def _research_company_with_claude_api(self, state: JobState) -> Dict[str, Any]:
        """
        Research company using Claude API with WebSearch (new backend).

        This is the primary research method when use_claude_api=True. It implements
        a fallback chain for resilient company research:

        Fallback Chain:
        1. Primary: Claude API WebSearch with original company name
        2a. If fails: Try name variations (DLOCAL -> dLocal, DLocal, etc.)
        2b. If still fails: Try FireCrawl mode if available (legacy scraping)
        2c. If still fails: Use LLM knowledge fallback (training data, low confidence)
        3. If ALL fail: Return error with company_research: None

        Args:
            state: JobState with company name, title, job_description

        Returns:
            Dict with company_research (structured) + legacy fields for compatibility
        """
        company = state["company"]
        job_title = state.get("title", "")
        job_description = state.get("job_description", "")
        job_id = state.get("job_id", "unknown")

        self.logger.info(f"[Claude API] Researching company: {company}")

        # Check cache first (same caching logic as FireCrawl mode)
        try:
            cached_data = self._check_cache(company)
            if cached_data:
                self.logger.info(f"[Cache] HIT for {company}")
                return cached_data
        except Exception as e:
            self.logger.info(f"[Cache] Check failed, proceeding with fresh research: {e}")

        # ===== STEP 1: Primary research with original company name =====
        primary_error = None
        try:
            result = run_async(
                self.claude_researcher.research_company(
                    company_name=company,
                    job_context=job_description[:1000] if job_description else "",
                    job_title=job_title,
                )
            )

            if result.success and result.data:
                self.logger.info(f"[Claude API] Primary research successful for {company}")
                return self._build_research_result(company, result.data, state)

            primary_error = result.error or "No data returned"
            self.logger.warning(f"[Claude API] Primary research failed: {primary_error}")

        except Exception as e:
            primary_error = str(e)
            self.logger.warning(f"[Claude API] Primary research exception: {primary_error}")

        # ===== STEP 2a: Try name variations =====
        name_variations = self._normalize_company_name(company)
        # Remove original (already tried) and limit to remaining variations
        variations_to_try = [v for v in name_variations if v != company][:4]

        for variant in variations_to_try:
            self.logger.info(f"[Fallback 2a] Trying name variation: {variant}")
            try:
                result = run_async(
                    self.claude_researcher.research_company(
                        company_name=variant,
                        job_context=job_description[:1000] if job_description else "",
                        job_title=job_title,
                    )
                )

                if result.success and result.data:
                    self.logger.info(f"[Fallback 2a] Name variation '{variant}' successful")
                    # Use original company name for caching/result, but research was with variant
                    return self._build_research_result(company, result.data, state)

            except Exception as e:
                self.logger.debug(f"[Fallback 2a] Variation '{variant}' failed: {e}")
                continue

        self.logger.warning(f"[Fallback 2a] All name variations failed for {company}")

        # ===== STEP 2b: Try FireCrawl mode if available =====
        if self.firecrawl:
            self.logger.info(f"[Fallback 2b] Trying FireCrawl mode for {company}")
            try:
                # Use the legacy research method
                scraped_data = self._scrape_multiple_sources(company)
                if scraped_data:
                    # Extract STAR context if available
                    star_domains, star_outcomes = self._extract_star_context(state)
                    annotation_focus = self._extract_annotation_research_focus(state)

                    company_research_output = self._analyze_company_signals(
                        company, scraped_data,
                        star_domains=star_domains,
                        star_outcomes=star_outcomes,
                        annotation_focus=annotation_focus,
                        job_id=job_id
                    )

                    if company_research_output:
                        self.logger.info(f"[Fallback 2b] FireCrawl mode successful for {company}")
                        # Convert to result format
                        company_research: CompanyResearch = {
                            "summary": company_research_output.summary,
                            "signals": [
                                {
                                    "type": sig.type,
                                    "description": sig.description,
                                    "date": sig.date,
                                    "source": sig.source,
                                }
                                for sig in company_research_output.signals
                            ],
                            "url": company_research_output.url,
                            "company_type": "employer",
                        }

                        # Cache the result
                        try:
                            self._store_cache(company, company_research=company_research_output, company_type="employer")
                            self.logger.info(f"[Cache] ✓ Stored FireCrawl fallback research for {company}")
                        except Exception as cache_error:
                            self.logger.warning(f"[Cache] ✗ Failed to cache: {cache_error}")

                        return {
                            "company_research": company_research,
                            "scraped_job_posting": None,
                            "company_summary": company_research["summary"],
                            "company_url": company_research["url"],
                        }

            except Exception as e:
                self.logger.warning(f"[Fallback 2b] FireCrawl mode failed: {e}")
        else:
            self.logger.debug("[Fallback 2b] FireCrawl not available, skipping")

        # ===== STEP 2c: LLM knowledge fallback (last resort) =====
        self.logger.info(f"[Fallback 2c] Using LLM knowledge fallback for {company}")
        try:
            llm_result = run_async(
                self._research_with_llm_knowledge(company, job_title, job_description)
            )
            if llm_result:
                self.logger.info(f"[Fallback 2c] LLM knowledge fallback successful for {company}")
                # NOTE: Do NOT cache LLM knowledge results (may be stale)
                return llm_result

        except Exception as e:
            self.logger.warning(f"[Fallback 2c] LLM knowledge fallback failed: {e}")

        # ===== ALL FALLBACKS FAILED =====
        error_msg = f"Claude API company research failed after all fallbacks: {primary_error}"
        self.logger.error(error_msg)

        # Return minimal result with error - include company_research: None
        # so downstream layers can properly detect failure
        return {
            "company_research": None,
            "company_summary": None,
            "company_url": None,
            "scraped_job_posting": None,
            "errors": state.get("errors", []) + [error_msg],
        }

    def _build_research_result(
        self,
        company: str,
        data: Dict[str, Any],
        state: JobState,
    ) -> Dict[str, Any]:
        """
        Build the standard research result dict from Claude API response data.

        Helper method to avoid code duplication in the fallback chain.

        Args:
            company: Company name (for caching)
            data: Parsed research data from Claude API
            state: JobState for context

        Returns:
            Dict with company_research + legacy fields
        """
        self.logger.info(
            f"[Claude API] Research complete - {len(data.get('signals', []))} signals"
        )

        # Convert to CompanyResearch format for JobState
        company_research: CompanyResearch = {
            "summary": data.get("summary", ""),
            "signals": [
                {
                    "type": sig.get("type", "growth"),
                    "description": sig.get("description", ""),
                    "date": sig.get("date", "unknown"),
                    "source": sig.get("source", ""),
                }
                for sig in data.get("signals", [])
            ],
            "url": data.get("url", self._construct_company_url(company)),
            "company_type": data.get("company_type", "employer"),
        }

        # Store in cache
        try:
            cache_output = CompanyResearchOutput(
                summary=company_research["summary"],
                signals=[
                    CompanySignalModel(
                        type=sig["type"],
                        description=sig["description"],
                        date=sig["date"],
                        source=sig["source"],
                    )
                    for sig in company_research["signals"]
                ],
                url=company_research["url"],
            )
            self._store_cache(
                company,
                company_research=cache_output,
                company_type=company_research["company_type"]
            )
            self.logger.info(f"[Cache] ✓ Stored Claude API research for {company}")
        except Exception as cache_error:
            self.logger.warning(f"[Cache] ✗ Failed to cache Claude API results: {cache_error}")

        # Scrape job posting if URL available (for dossier completeness)
        scraped_job_posting = None
        # In Claude API mode, we don't have FireCrawl available for job posting scraping

        return {
            "company_research": company_research,
            "scraped_job_posting": scraped_job_posting,
            # Legacy fields for backward compatibility
            "company_summary": company_research["summary"],
            "company_url": company_research["url"],
        }

    def _assess_content_quality(self, content: str) -> str:
        """
        Phase 5.2: Content quality gate to detect boilerplate.

        Detects low-value content (cookie policies, legal text, paywalls)
        and assigns quality score for filtering.

        Args:
            content: Scraped content text

        Returns:
            "high", "medium", or "low" quality score
        """
        if not content or len(content) < 100:
            return "low"

        content_lower = content.lower()

        # Low-value boilerplate indicators
        boilerplate_phrases = [
            "cookie policy", "privacy policy", "terms of service",
            "we use cookies", "accept all cookies", "manage preferences",
            "gdpr", "this website uses cookies", "cookie settings",
            "please enable javascript", "javascript is required"
        ]

        boilerplate_count = sum(1 for phrase in boilerplate_phrases if phrase in content_lower)

        # High boilerplate density = low quality
        if boilerplate_count >= 3:
            return "low"
        elif boilerplate_count >= 1:
            return "medium"

        # Business content indicators
        business_phrases = [
            "funding", "raised", "series", "customers", "revenue",
            "partnership", "acquisition", "launched", "product",
            "team", "employees", "growth", "market", "ceo",
            "founded", "investor", "valuation", "expansion"
        ]

        business_count = sum(1 for phrase in business_phrases if phrase in content_lower)

        # High business density = high quality
        if business_count >= 3:
            return "high"
        elif business_count >= 1:
            return "medium"

        return "low"

    def _extract_star_context(self, state: JobState) -> tuple[Optional[str], Optional[str]]:
        """
        Extract candidate domains and outcome types from selected_stars.

        Phase 5 STAR-awareness: When STAR selector has run, extract the candidate's
        strongest domains and proven outcome types to bias signal extraction.

        Args:
            state: JobState which may contain selected_stars

        Returns:
            Tuple of (domains_text, outcomes_text) or (None, None) if no STARs
        """
        selected_stars = state.get('selected_stars', [])
        if not selected_stars:
            return None, None

        # Collect unique domains and outcomes across selected STARs
        domains = set()
        outcomes = set()

        for star in selected_stars:
            # Extract domain_areas (List[str] in canonical schema)
            star_domains = star.get('domain_areas', [])
            if isinstance(star_domains, list):
                domains.update(star_domains)

            # Extract outcome_types (List[str] in canonical schema)
            star_outcomes = star.get('outcome_types', [])
            if isinstance(star_outcomes, list):
                outcomes.update(star_outcomes)

        if not domains and not outcomes:
            return None, None

        domains_text = ", ".join(sorted(domains)) if domains else "Not specified"
        outcomes_text = ", ".join(sorted(outcomes)) if outcomes else "Not specified"

        return domains_text, outcomes_text

    def _extract_annotation_research_focus(self, state: JobState) -> Optional[str]:
        """
        Extract annotation-guided research focus areas.

        Phase 4: When JD annotations exist, extract focus areas to guide
        company signal extraction toward what matters to the candidate.

        Args:
            state: JobState which may contain jd_annotations

        Returns:
            Formatted focus text or None if no annotations
        """
        jd_annotations = state.get("jd_annotations")
        if not jd_annotations:
            return None

        annotations = jd_annotations.get("annotations", [])
        if not annotations:
            return None

        # Extract focus areas from annotations
        technical_focus = []
        culture_focus = []
        identity_focus = []

        for ann in annotations:
            # Only process active annotations (default to True for backward compatibility)
            if not ann.get("is_active", True):
                continue

            target = ann.get("target", {})
            target_text = target.get("text", "")[:60]
            matching_skill = ann.get("matching_skill", "")
            requirement_type = ann.get("requirement_type")
            passion = ann.get("passion")
            identity = ann.get("identity")

            # Technical focus: must_have requirements
            if requirement_type == "must_have":
                keywords = ann.get("suggested_keywords", [])
                if keywords:
                    technical_focus.extend(keywords[:2])
                elif matching_skill:
                    technical_focus.append(matching_skill)

            # Culture/passion focus: areas candidate loves
            if passion == "love_it":
                culture_focus.append(matching_skill or target_text)

            # Identity focus: core professional identity
            if identity == "core_identity":
                identity_focus.append(matching_skill or target_text)

        # If no focus areas extracted, return None
        if not any([technical_focus, culture_focus, identity_focus]):
            return None

        # Build focus text
        parts = []
        if technical_focus:
            unique_tech = list(dict.fromkeys(technical_focus))[:5]
            parts.append(f"Technical areas: {', '.join(unique_tech)}")
        if culture_focus:
            unique_culture = list(dict.fromkeys(culture_focus))[:3]
            parts.append(f"Culture/passion areas: {', '.join(unique_culture)}")
        if identity_focus:
            unique_identity = list(dict.fromkeys(identity_focus))[:2]
            parts.append(f"Identity alignment: {', '.join(unique_identity)}")

        return " | ".join(parts)

    def _get_cache_key(self, company_name: str) -> str:
        """Generate cache key from company name (normalized)."""
        # Normalize: lowercase, remove extra whitespace
        return company_name.lower().strip()

    def _check_cache(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Check MongoDB cache for company research (Phase 5.1 enhanced).

        Returns:
            Dict with company_research (CompanyResearch structure) if found
            Falls back to legacy company_summary/company_url if old cache format
        """
        cache_key = self._get_cache_key(company_name)

        cached = self.cache_collection.find_one({"company_key": cache_key})

        if cached:
            self.logger.info(f"Cache HIT for {company_name}")

            # Phase 5.1: Check for new structured company_research
            if 'company_research' in cached:
                company_research = cached['company_research']
                # Ensure company_type is present (backward compat for old cached data)
                if 'company_type' not in company_research:
                    company_research['company_type'] = cached.get('company_type', 'employer')
                return {
                    'company_research': company_research,
                    # Populate legacy fields for backward compatibility
                    'company_summary': company_research.get('summary'),
                    'company_url': company_research.get('url')
                }

            # Legacy Phase 1.3 cache format
            return {
                'company_summary': cached.get('company_summary'),
                'company_url': cached.get('company_url')
            }

        self.logger.info(f"Cache MISS for {company_name}")
        return None

    def _store_cache(
        self,
        company_name: str,
        company_research: Optional[CompanyResearchOutput] = None,
        summary: Optional[str] = None,
        url: Optional[str] = None,
        company_type: str = "employer"
    ):
        """
        Store company research in MongoDB cache with TTL (Phase 5.1 enhanced).

        Args:
            company_name: Company name
            company_research: CompanyResearchOutput (Phase 5.1 format)
            summary: Legacy format (backward compatibility)
            url: Legacy format (backward compatibility)
            company_type: Classification - 'employer' or 'recruitment_agency'
        """
        cache_key = self._get_cache_key(company_name)

        cache_doc = {
            "company_key": cache_key,
            "company_name": company_name,
            "cached_at": datetime.utcnow(),
            "company_type": company_type  # Store company classification
        }

        # Phase 5.1: Store structured company_research if provided
        if company_research:
            research_dict = company_research.model_dump()
            research_dict["company_type"] = company_type  # Include in company_research dict
            cache_doc["company_research"] = research_dict
            # Also store legacy fields for backward compatibility
            cache_doc["company_summary"] = company_research.summary
            cache_doc["company_url"] = company_research.url
        else:
            # Legacy format (Phase 1.3)
            cache_doc["company_summary"] = summary
            cache_doc["company_url"] = url

        # Upsert (insert or update)
        self.cache_collection.update_one(
            {"company_key": cache_key},
            {"$set": cache_doc},
            upsert=True
        )

        self.logger.info(f"Cached research for {company_name}")

    def _construct_company_url(self, company_name: str) -> str:
        """
        Construct likely company website URL from company name.

        Examples:
        - "Launch Potato" -> "launchpotato.com"
        - "Google Inc." -> "google.com"
        - "Amazon" -> "amazon.com"
        """
        # Clean company name: lowercase, remove special chars, spaces
        clean_name = company_name.lower()
        clean_name = re.sub(r'\s+', '', clean_name)  # Remove spaces
        clean_name = re.sub(r'[^\w]', '', clean_name)  # Remove special chars
        clean_name = re.sub(r'(inc|llc|ltd|corp|corporation|company)$', '', clean_name)  # Remove suffixes

        return f"https://{clean_name}.com"

    def _normalize_company_name(self, company_name: str) -> List[str]:
        """
        Generate name variations for company research fallback.

        Generates variations by:
        1. Case variations (DLOCAL -> dLocal, DLocal, etc.)
        2. Suffix removal (Acme Inc. -> Acme)
        3. Domain extraction (acme.com -> Acme)

        Args:
            company_name: Original company name

        Returns:
            List of up to 8 name variations (including original)
        """
        variations = set()
        name = company_name.strip()

        # Always include original
        variations.add(name)

        # Common suffixes to try removing
        suffixes = [
            " Inc", " Inc.", " Incorporated",
            " LLC", " L.L.C.",
            " Ltd", " Ltd.", " Limited",
            " Corp", " Corp.", " Corporation",
            " Co.", " Company",
            " GmbH", " AG", " S.A.", " S.A",
            " PLC", " Pty", " Pty Ltd",
        ]

        # Try removing suffixes
        base_name = name
        for suffix in suffixes:
            if name.endswith(suffix):
                base_name = name[:-len(suffix)].strip()
                variations.add(base_name)
                variations.add(base_name.title())
                break

        # Extract from domain if URL-like (e.g., "acme.com" -> "Acme")
        if "." in name and not any(name.endswith(s) for s in suffixes):
            # Looks like a domain
            domain_part = name.split(".")[0]
            if len(domain_part) >= 2:
                variations.add(domain_part.title())
                variations.add(domain_part.upper())

        # Generate case variations for base name (or original if no suffix removed)
        for n in [name, base_name]:
            # All uppercase
            variations.add(n.upper())

            # All lowercase
            variations.add(n.lower())

            # Title case
            variations.add(n.title())

            # Capitalize first letter only
            if n:
                variations.add(n[0].upper() + n[1:].lower() if len(n) > 1 else n.upper())

        # camelCase variations (for multi-word or dLocal pattern)
        words = base_name.split()
        if len(words) > 1:
            camel = words[0].lower() + ''.join(w.title() for w in words[1:])
            variations.add(camel)
        elif base_name:
            # Single word: try dLocal pattern
            variations.add(base_name[0].lower() + base_name[1:].title() if len(base_name) > 1 else base_name.lower())

        # Remove empty strings and limit to 8 variations (increased for more coverage)
        variations.discard("")
        return list(variations)[:8]

    async def _research_with_llm_knowledge(
        self,
        company: str,
        job_title: str,
        job_description: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback: Research company using Claude's training knowledge (no web search).

        This is used when web search fails for all name variations. Uses Claude
        WITHOUT the web_search tool to leverage its training data about companies.

        Results are marked with low confidence and NOT cached (stale knowledge).

        Args:
            company: Company name
            job_title: Job title for context
            job_description: Job description for context

        Returns:
            Dict with company_research marked as llm_knowledge source, or None on failure
        """
        if not self.claude_researcher:
            self.logger.warning("[LLM Knowledge] Claude researcher not initialized")
            return None

        self.logger.info(f"[Fallback 2c] Using LLM knowledge fallback for {company}")

        # Build prompt for knowledge-based research (no web search)
        knowledge_prompt = f"""Based on your training knowledge, provide information about the company "{company}".

Company: {company}
Job Title: {job_title}
Job Context: {job_description[:500] if job_description else 'Not provided'}

IMPORTANT: You do NOT have web search available. Only provide information from your training knowledge.
If you don't have reliable information about this company, say so clearly.

Return JSON with your findings:
{{
    "summary": "2-3 sentence company overview based on training knowledge, or 'Limited information available' if unknown",
    "signals": [],
    "url": "https://likely-company-url.com",
    "company_type": "employer|recruitment_agency|unknown"
}}

Be honest about uncertainty. Prefix summary with '[Based on training knowledge]' to indicate the source."""

        try:
            import anthropic
            from datetime import datetime

            start_time = datetime.utcnow()

            # Call Claude API WITHOUT web_search tool (pure LLM knowledge)
            response = self.claude_researcher.client.messages.create(
                model=self.claude_researcher.model,
                max_tokens=1024,
                system="You are a business analyst providing company information from your training knowledge. Be honest about limitations.",
                messages=[{"role": "user", "content": knowledge_prompt}],
                # NO tools parameter - this forces pure LLM knowledge
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Extract text content
            text_content = None
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    text_content = block.text
                    break

            if not text_content:
                self.logger.warning("[LLM Knowledge] No text content in response")
                return None

            # Parse JSON using existing utility
            from src.common.json_utils import parse_llm_json
            data = parse_llm_json(text_content)

            # Ensure summary has the training knowledge prefix
            summary = data.get("summary", f"Limited information available for {company}")
            if not summary.startswith("[Based on training knowledge]"):
                summary = f"[Based on training knowledge] {summary}"

            # Build company_research with low confidence markers
            company_research = {
                "summary": summary,
                "signals": [],  # No signals from training knowledge (unreliable)
                "url": data.get("url", self._construct_company_url(company)),
                "company_type": data.get("company_type", "unknown"),
                "_source": "llm_knowledge",
                "_confidence": "low",
            }

            self.logger.info(
                f"[LLM Knowledge] Research complete for {company} - {duration_ms}ms "
                f"(source: llm_knowledge, confidence: low)"
            )

            # NOTE: Do NOT cache LLM knowledge results (they may be stale)

            return {
                "company_research": company_research,
                "company_summary": company_research["summary"],
                "company_url": company_research["url"],
            }

        except Exception as e:
            self.logger.error(f"[LLM Knowledge] Fallback failed for {company}: {e}")
            return None

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        reraise=True
    )
    def _scrape_website(self, url: str, char_limit: int = 3000) -> Optional[str]:
        """
        Scrape company website using FireCrawl.

        Phase 5.2: Increased character limit for better content extraction.

        Args:
            url: URL to scrape
            char_limit: Character limit (default 3000, increased from 2000)

        Returns:
            Cleaned text content or None if scraping fails
        """
        try:
            # Use FireCrawl's scrape endpoint
            result = self.firecrawl.scrape(
                url,
                formats=['markdown'],  # Get clean markdown text
                only_main_content=True  # Skip nav, footer, etc.
            )

            # Extract markdown content from Document object
            if result and hasattr(result, 'markdown'):
                content = result.markdown
                # Phase 5.2: Increased limit (2000 → 3000) for better extraction
                return content[:char_limit] if content else None

            return None

        except Exception as e:
            self.logger.warning(f"FireCrawl scraping failed: {str(e)}")
            raise  # Re-raise for retry logic

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=False
    )
    def _scrape_job_posting(self, job_url: str) -> Optional[str]:
        """
        Scrape the original job posting to preserve the written JD for the dossier.

        Returns:
            Markdown content truncated for prompt safety or None if scraping fails.
        """
        try:
            if not job_url:
                return None

            result = self.firecrawl.scrape(
                job_url,
                formats=['markdown'],
                only_main_content=True
            )
            if result and hasattr(result, "markdown"):
                return result.markdown[:4000]
        except Exception as e:
            self.logger.warning(f"Job posting scrape failed: {e}")

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _summarize_with_llm(
        self,
        company: str,
        website_content: Optional[str] = None,
        job_id: str = "unknown"
    ) -> str:
        """
        Generate company summary using LLM.

        If website_content is provided, summarize it.
        Otherwise, use LLM's general knowledge as fallback.

        Migrated to UnifiedLLM: Uses step_name="summarize_with_llm" (low tier).

        Args:
            company: Company name
            website_content: Optional scraped website content
            job_id: Job ID for tracking (optional)

        Returns:
            Company summary string
        """
        if website_content:
            # Use scraped content
            system_prompt = SYSTEM_PROMPT_SCRAPE
            user_prompt = USER_PROMPT_SCRAPE_TEMPLATE.format(
                company=company,
                website_content=website_content
            )
        else:
            # Fallback to general knowledge
            system_prompt = SYSTEM_PROMPT_FALLBACK
            user_prompt = USER_PROMPT_FALLBACK_TEMPLATE.format(company=company)

        # Use UnifiedLLM with step config for summarize_with_llm (low tier)
        result = invoke_unified_sync(
            prompt=user_prompt,
            step_name="summarize_with_llm",
            system=system_prompt,
            job_id=job_id,
            validate_json=False,  # Summary is plain text, not JSON
        )

        if not result.success:
            self.logger.warning(f"Company summarization LLM call failed: {result.error}")
            raise ValueError(f"LLM summarization failed: {result.error}")

        # Log backend attribution
        self.logger.info(f"Company summary via {result.backend} ({result.model}) in {result.duration_ms}ms")

        return result.content.strip()

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        reraise=True
    )
    def _search_with_firecrawl(self, query: str, source_name: str) -> Optional[Dict[str, str]]:
        """
        Search for a URL using FireCrawl search API and scrape the top result.

        Args:
            query: Search query string
            source_name: Name of the source (for filtering results)

        Returns:
            Dict with {"url": str, "content": str} or None if search/scrape fails
        """
        try:
            self.logger.info(f"[FireCrawl] {source_name} search query: {query}")
            # Use FireCrawl search API to find relevant URLs
            # Limit to top 3 results to save API calls
            search_response = self.firecrawl.search(query, limit=3)

            # Use normalizer to extract results (handles SDK version differences)
            results = _extract_search_results(search_response)

            if not results:
                self.logger.info(f"No search results for {source_name}")
                return None

            # Extract the most relevant URL
            # For LinkedIn/Crunchbase, prioritize URLs containing those domains
            top_result = None
            for result in results:
                # Defensive URL extraction (handles both object attributes and dict keys)
                url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)

                if not url:
                    continue

                # Filter by source preference
                if source_name == "linkedin" and "linkedin.com" in url.lower():
                    top_result = url
                    break
                elif source_name == "crunchbase" and "crunchbase.com" in url.lower():
                    top_result = url
                    break
                elif source_name == "news":
                    # For news, accept first result
                    top_result = url
                    break
                elif not top_result:
                    # Fallback to first result if no domain match
                    top_result = url

            if not top_result:
                self.logger.info(f"No suitable URL found for {source_name}")
                return None

            self.logger.info(f"Found URL for {source_name}: {top_result}")

            # Scrape the top result
            content = self._scrape_website(top_result)

            if content:
                return {
                    "url": top_result,
                    "content": content
                }

            return None

        except Exception as e:
            self.logger.warning(f"Search failed for {source_name}: {e}")
            raise  # Re-raise for retry logic

    def _scrape_multiple_sources(self, company: str) -> Dict[str, Dict[str, str]]:
        """
        Scrape company information from multiple sources (Phase 5.2 IMPROVED).

        Phase 5.2 improvements:
        - Keyword-based search queries (not LLM-style questions)
        - Search operators for precision (site:, "quotes", OR, etc.)
        - Content quality gate filtering
        - Increased character limits for better extraction

        Queries (keyword-based with operators):
        1. "{company}" (about OR careers OR company) - Official site
        2. "{company}" site:linkedin.com/company - LinkedIn
        3. "{company}" site:crunchbase.com/organization - Crunchbase
        4. "{company}" (funding OR acquisition OR partnership) 2024 - Recent news

        Returns:
            Dict with source_name -> {"url": str, "content": str, "quality": str}
            Only includes sources with medium/high quality (low-quality filtered out).
        """
        # Phase 5.2: Keyword-based queries with search operators
        queries = {
            "official_site": f'"{company}" (about OR careers OR company)',
            "linkedin": f'"{company}" site:linkedin.com/company',
            "crunchbase": f'"{company}" site:crunchbase.com/organization',
            "news": f'"{company}" (funding OR acquisition OR partnership OR launch) 2024',
        }

        scraped_data = {}

        for source_name, query in queries.items():
            try:
                self.logger.info(f"Searching {source_name}: {query[:60]}...")

                # Phase 5.2: All sources use FireCrawl search (no direct URL construction)
                search_results = self._search_with_firecrawl(query, source_name)

                if search_results:
                    url = search_results['url']
                    content = search_results['content']

                    # Phase 5.2: Apply content quality gate
                    quality = self._assess_content_quality(content)
                    self.logger.info(f"Scraped {len(content)} chars from {source_name} (quality: {quality})")

                    # Only keep medium/high quality sources
                    if quality in ['medium', 'high']:
                        scraped_data[source_name] = {
                            "url": url,
                            "content": content,
                            "quality": quality
                        }
                        self.logger.info(f"✓ Kept {source_name} (quality: {quality})")
                    else:
                        self.logger.info(f"✗ Filtered {source_name} (low quality)")

            except Exception as e:
                self.logger.info(f"[Scrape] ✗ {source_name} failed (non-critical): {e}")
                continue

        return scraped_data

    def _analyze_company_signals(
        self,
        company: str,
        scraped_data: Dict[str, Dict[str, str]],
        star_domains: Optional[str] = None,
        star_outcomes: Optional[str] = None,
        annotation_focus: Optional[str] = None,
        job_id: str = "unknown"
    ) -> CompanyResearchOutput:
        """
        Extract company signals from scraped content using LLM (Phase 5.2 enhanced).

        Phase 5.2 enhancements:
        - Reasoning-first prompts with transparency
        - Quality assessment per source
        - Few-shot examples
        - STAR-aware when candidate context available
        - Phase 4: Annotation-aware when JD annotations available

        Migrated to UnifiedLLM: Uses step_name="analyze_company_signals" (middle tier).

        Args:
            company: Company name
            scraped_data: Dict of {source_name: {"url": str, "content": str, "quality": str}}
            star_domains: Optional candidate domain areas from selected STARs
            star_outcomes: Optional candidate outcome types from selected STARs
            annotation_focus: Optional focus areas from JD annotations
            job_id: Job ID for tracking (optional)

        Returns:
            CompanyResearchOutput with validated signals and reasoning block

        Raises:
            ValueError: If LLM output is invalid JSON or fails validation
        """
        # Phase 5.2: Build concatenated content with quality indicators
        content_sections = []
        for source_name, data in scraped_data.items():
            quality_tag = f"[quality: {data.get('quality', 'unknown')}]"
            content_sections.append(
                f"=== SOURCE: {source_name} ({data['url']}) {quality_tag} ===\n{data['content']}\n"
            )

        scraped_content = "\n".join(content_sections)

        # Phase 4: Add annotation focus context if available
        if annotation_focus:
            annotation_section = (
                f"\n\n=== CANDIDATE ANNOTATION FOCUS (Phase 4) ===\n"
                f"Research signals should prioritize these areas based on candidate annotations:\n"
                f"{annotation_focus}\n"
                f"Look for company signals that align with these focus areas.\n"
            )
            scraped_content = annotation_section + scraped_content
            self.logger.info(f"Annotation focus injected into research prompt")

        # Phase 5: Use STAR-aware prompt if candidate context available
        if star_domains and star_outcomes:
            system_prompt = SYSTEM_PROMPT_COMPANY_SIGNALS_STAR_AWARE.format(
                candidate_domains=star_domains,
                candidate_outcomes=star_outcomes
            )
            self.logger.info(f"Using STAR-aware prompt (domains: {star_domains[:50]}...)")
        else:
            system_prompt = SYSTEM_PROMPT_COMPANY_SIGNALS

        # Build user prompt
        # Phase 5.2: Increased content limit (5000 -> 8000) for better extraction
        user_prompt = USER_PROMPT_COMPANY_SIGNALS_TEMPLATE.format(
            company=company,
            scraped_content=scraped_content[:8000]  # Phase 5.2: Increased limit
        )

        # Use UnifiedLLM with step config for analyze_company_signals (middle tier)
        result = invoke_unified_sync(
            prompt=user_prompt,
            step_name="analyze_company_signals",
            system=system_prompt,
            job_id=job_id,
            validate_json=True,
        )

        if not result.success:
            self.logger.error(f"Company signals LLM call failed: {result.error}")
            raise ValueError(f"LLM signal extraction failed: {result.error}")

        # Log backend attribution
        self.logger.info(f"Company signals via {result.backend} ({result.model}) in {result.duration_ms}ms")

        # Use parsed_json if available, otherwise parse manually
        if result.parsed_json:
            data = result.parsed_json
        else:
            llm_output = result.content.strip()

            # Phase 5.2: Simple JSON parsing (Python's json module handles nested structures)
            # Remove markdown code blocks if present
            if llm_output.startswith("```"):
                llm_output = re.sub(r'^```(?:json)?\s*', '', llm_output)
                llm_output = re.sub(r'\s*```$', '', llm_output)
                llm_output = llm_output.strip()

            # Parse JSON directly - Python handles nested structures automatically
            try:
                data = json.loads(llm_output)
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON parsing failed: {e}")
                self.logger.error(f"LLM output:\n{llm_output}")
                raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {llm_output[:500]}")

        # Validate with Pydantic
        try:
            validated = CompanyResearchOutput(**data)
        except ValidationError as e:
            error_messages = []
            for error in e.errors():
                field = ' -> '.join(str(x) for x in error['loc'])
                msg = error['msg']
                error_messages.append(f"{field}: {msg}")

            self.logger.error(f"Pydantic validation failed:")
            self.logger.error(f"Errors: {error_messages}")
            self.logger.error(f"LLM output:\n{result.content}")
            self.logger.error(f"Parsed data:\n{json.dumps(data, indent=2)}")

            raise ValueError(
                f"CompanyResearch schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_messages) +
                f"\nReceived data: {json.dumps(data, indent=2)[:500]}"
            )

        return validated

    def _fallback_signal_extraction(
        self,
        company: str,
        official_site_data: Dict[str, str],
        job_id: str = "unknown"
    ) -> CompanyResearchOutput:
        """
        Defensive fallback: Extract minimal signals from official site content only.

        Phase 5 enhancement: When multi-source scrape yields 0 signals or LLM returns empty,
        run a second-pass extraction using only official_site content with best-effort rules.

        Migrated to UnifiedLLM: Uses step_name="fallback_signal_extraction" (middle tier).

        Args:
            company: Company name
            official_site_data: {"url": str, "content": str} from official site
            job_id: Job ID for tracking (optional)

        Returns:
            CompanyResearchOutput with at least 1 signal (or minimal valid output)
        """
        self.logger.info("Running fallback signal extraction from official site")

        system_prompt = "You are a business analyst. Extract factual company information. Output JSON only."
        user_prompt = f"""Analyze this official company website content and extract ANY factual information as signals.

COMPANY: {company}

SCRAPED CONTENT FROM OFFICIAL SITE:
=== SOURCE: official_site ({official_site_data['url']}) ===
{official_site_data['content'][:3000]}

**EXTRACTION RULES (BEST-EFFORT):**
1. Extract AT LEAST ONE signal from the content
2. If no funding/acquisition/leadership news, use "growth" type for general facts:
   - What industry/market they operate in
   - What products/services they offer
   - Company description or mission
   - Technology stack or platforms used
3. Use the official site URL as the source for all signals
4. Summary should describe what the company does

Output JSON only:
{{"summary": "...", "signals": [...], "url": "{official_site_data['url']}"}}"""

        # Use UnifiedLLM with step config for fallback_signal_extraction (middle tier)
        result = invoke_unified_sync(
            prompt=user_prompt,
            step_name="fallback_signal_extraction",
            system=system_prompt,
            job_id=job_id,
            validate_json=True,
        )

        if not result.success:
            self.logger.warning(f"Fallback signal extraction LLM call failed: {result.error}")
            # Return minimal valid output
            return CompanyResearchOutput(
                summary=f"{company} is a business (limited information available from website).",
                signals=[{
                    "type": "growth",
                    "description": f"{company} official website found",
                    "date": "unknown",
                    "source": official_site_data['url']
                }],
                url=official_site_data['url']
            )

        # Log backend attribution
        self.logger.info(f"Fallback signals via {result.backend} ({result.model}) in {result.duration_ms}ms")

        # Use parsed_json if available, otherwise parse manually
        if result.parsed_json:
            data = result.parsed_json
        else:
            llm_output = result.content.strip()
            # Extract JSON
            json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)
            json_str = json_match.group(0) if json_match else llm_output

            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Fallback JSON parsing failed: {e}, returning minimal output")
                return CompanyResearchOutput(
                    summary=f"{company} is a business (limited information available from website).",
                    signals=[{
                        "type": "growth",
                        "description": f"{company} official website found",
                        "date": "unknown",
                        "source": official_site_data['url']
                    }],
                    url=official_site_data['url']
                )

        try:
            # Ensure at least one signal if none extracted
            if not data.get('signals'):
                data['signals'] = [{
                    "type": "growth",
                    "description": f"{company} operates as a business (details from official website)",
                    "date": "unknown",
                    "source": official_site_data['url']
                }]

            return CompanyResearchOutput(**data)

        except ValidationError as e:
            # Last resort: return minimal valid output
            self.logger.warning(f"Fallback validation failed: {e}, returning minimal output")
            return CompanyResearchOutput(
                summary=f"{company} is a business (limited information available from website).",
                signals=[{
                    "type": "growth",
                    "description": f"{company} official website found",
                    "date": "unknown",
                    "source": official_site_data['url']
                }],
                url=official_site_data['url']
            )

    def research_company(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to research company and generate structured research.

        Supports two execution backends:
        - Claude API (default): Uses Claude with WebSearch for research (new)
        - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility

        Strategy (when use_claude_api=True):
        - Uses Claude API with web_search tool for one-shot research
        - Caches results in MongoDB with 7-day TTL
        - Handles company type detection inline

        Strategy (when use_claude_api=False - legacy FireCrawl mode):
        0. Classify company type (employer vs recruitment agency)
        1. Check MongoDB cache (7-day TTL)
        2. If recruitment agency: minimal research (basic summary, no signals)
        3. If employer: Extract STAR context if available (Phase 5 STAR-awareness)
        4. If cache miss, scrape multiple sources (official site, LinkedIn, Crunchbase, news)
        5. Extract structured signals via LLM (JSON-only with Pydantic validation)
        6. If 0 signals extracted, run defensive fallback on official_site content
        7. Store result in cache with CompanyResearch structure
        8. Fall back to legacy approach if Phase 5.1 fails
        9. Log any errors but don't block pipeline

        Args:
            state: Current JobState with company name (and optionally selected_stars)

        Returns:
            Dict with company_research (structured) + legacy company_summary/company_url
        """
        company = state["company"]
        job_id = state.get("job_id", "unknown")

        # Route to Claude API backend if enabled (new default)
        if self.use_claude_api:
            self.logger.info(f"Using Claude API ({self.tier} tier) for company research")
            return self._research_company_with_claude_api(state)

        # Legacy FireCrawl + OpenRouter mode
        self.logger.info("Using FireCrawl + OpenRouter (legacy mode) for company research")
        scraped_job_posting = self._scrape_job_posting(state.get("job_url", ""))

        # Step 0: Classify company type (employer vs recruitment agency)
        company_type = self._classify_company_type(state)
        self.logger.info(f"Company classification: {company_type}")

        # Step 0.5: Handle recruitment agencies with minimal research
        if company_type == "recruitment_agency":
            self.logger.info("Recruitment agency detected - using minimal research flow")
            company_research: CompanyResearch = {
                "summary": f"{company} is a recruitment/staffing agency sourcing candidates for their clients.",
                "signals": [],  # No business signals needed for agencies
                "url": self._construct_company_url(company),
                "company_type": "recruitment_agency"
            }
            return {
                "company_research": company_research,
                "scraped_job_posting": scraped_job_posting,
                "company_summary": company_research["summary"],
                "company_url": company_research["url"]
            }

        # Phase 5 STAR-awareness: Extract candidate context if available (employers only)
        star_domains, star_outcomes = self._extract_star_context(state)
        if star_domains:
            self.logger.info(f"STAR context available: {len(star_domains.split(', '))} domain(s)")

        # Phase 4: Extract annotation research focus if available
        annotation_focus = self._extract_annotation_research_focus(state)
        if annotation_focus:
            self.logger.info(f"Annotation focus available: {annotation_focus[:80]}...")

        # Step 1: Check cache first
        try:
            cached_data = self._check_cache(company)
            if cached_data:
                if scraped_job_posting:
                    cached_data["scraped_job_posting"] = scraped_job_posting
                return cached_data
        except Exception as e:
            self.logger.info(f"[Cache] Check failed, proceeding with fresh research: {e}")

        # Cache miss - proceed with Phase 5.1 research
        try:
            # Step 1: Multi-source scraping (Phase 5.1)
            self.logger.info("Phase 5.1: Multi-source scraping")
            scraped_data = self._scrape_multiple_sources(company)

            if not scraped_data:
                raise ValueError("No sources successfully scraped")

            self.logger.info(f"Scraped {len(scraped_data)} source(s)")

            # Step 2: Extract signals via LLM (Phase 5.1 + STAR-aware + Annotation-aware)
            self.logger.info("Extracting company signals via LLM")
            company_research_output = self._analyze_company_signals(
                company, scraped_data,
                star_domains=star_domains,
                star_outcomes=star_outcomes,
                annotation_focus=annotation_focus,
                job_id=job_id
            )

            self.logger.info(f"Extracted {len(company_research_output.signals)} signal(s)")

            # Phase 5 defensive fallback: If 0 signals, try second-pass extraction
            if len(company_research_output.signals) == 0 and 'official_site' in scraped_data:
                self.logger.warning("No signals extracted, running fallback extraction")
                company_research_output = self._fallback_signal_extraction(
                    company, scraped_data['official_site'],
                    job_id=job_id
                )
                self.logger.info(f"Fallback extracted {len(company_research_output.signals)} signal(s)")

            # Step 3: Store in cache (Phase 5.1 format)
            try:
                # Pass company_type="employer" since agencies return early before this point
                self._store_cache(company, company_research=company_research_output, company_type="employer")
                self.logger.info(f"[Cache] ✓ Stored research for {company}")
            except Exception as e:
                self.logger.error(f"[Cache] ✗ Failed to cache results (future lookups will re-scrape): {e}")

            # Convert to TypedDict format for JobState
            company_research: CompanyResearch = {
                "summary": company_research_output.summary,
                "signals": [
                    {
                        "type": sig.type,
                        "description": sig.description,
                        "date": sig.date,
                        "source": sig.source
                    }
                    for sig in company_research_output.signals
                ],
                "url": company_research_output.url,
                "company_type": "employer"  # Classified as direct employer
            }

            return {
                "company_research": company_research,
                "scraped_job_posting": scraped_job_posting,
                # Legacy fields for backward compatibility
                "company_summary": company_research_output.summary,
                "company_url": company_research_output.url
            }

        except Exception as e:
            # Phase 5.1 failed - fall back to legacy approach (Phase 1.3)
            self.logger.warning(f"Phase 5.1 research failed: {e}")
            self.logger.info("Falling back to legacy single-source approach")

            try:
                # Legacy single-source scraping
                company_url = self._construct_company_url(company)
                website_content = self._scrape_website(company_url)

                if website_content:
                    self.logger.info(f"Legacy scrape: {len(website_content)} chars from {company_url}")
                else:
                    self.logger.info("Using LLM general knowledge fallback")

                company_summary = self._summarize_with_llm(company, website_content, job_id=job_id)
                self.logger.info(f"Generated summary ({len(company_summary)} chars)")

                # Store in cache (legacy format)
                try:
                    # Legacy path is only reached for employers (agencies return early)
                    self._store_cache(company, summary=company_summary, url=company_url, company_type="employer")
                    self.logger.info(f"[Cache] ✓ Stored legacy research for {company}")
                except Exception as cache_error:
                    self.logger.error(f"[Cache] ✗ Failed to cache legacy results: {cache_error}")

                return {
                    "company_summary": company_summary,
                    "company_url": company_url,
                    "scraped_job_posting": scraped_job_posting
                }

            except Exception as legacy_error:
                # Complete failure - log error and return empty
                error_msg = f"Layer 3 (Company Researcher) failed: {str(legacy_error)}"
                self.logger.error(error_msg)

                return {
                    "company_summary": None,
                    "company_url": None,
                    "scraped_job_posting": scraped_job_posting,
                    "errors": state.get("errors", []) + [error_msg]
                }


# ===== LANGGRAPH NODE FUNCTION =====

def company_researcher_node(
    state: JobState,
    tier: TierType = "balanced",
    use_claude_api: bool = True,
) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 3: Company Researcher.

    Supports two execution backends:
    - Claude API (default): Uses Claude with WebSearch for research
    - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility

    Args:
        state: Current job processing state
        tier: Claude model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus).
              Only used when use_claude_api=True. Default is "balanced" (Sonnet 4.5).
        use_claude_api: If True (default), use Claude API with WebSearch.
                       If False, use FireCrawl + OpenRouter (legacy mode).

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer3")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    backend_name = f"Claude API ({tier} tier)" if use_claude_api else "FireCrawl + OpenRouter (legacy)"
    logger.info("="*60)
    logger.info(f"LAYER 3: Company Researcher - {backend_name}")
    logger.info("="*60)
    logger.info(f"Researching: {state['company']}")

    with LayerContext(struct_logger, 3, "company_researcher") as ctx:
        researcher = CompanyResearcher(tier=tier, use_claude_api=use_claude_api)
        updates = researcher.research_company(state)

        # Log results and add metadata (Phase 5.1 format)
        if updates.get("company_research"):
            company_research = updates["company_research"]
            signals_count = len(company_research.get("signals", []))
            ctx.add_metadata("signals_count", signals_count)
            logger.info("Company Summary:")
            logger.info(f"  {company_research['summary']}")

            if company_research.get("signals"):
                logger.info(f"Company Signals ({signals_count} found):")
                for idx, signal in enumerate(company_research['signals'], 1):
                    logger.info(f"  {idx}. [{signal['type']}] {signal['description']}")
                    if signal.get('date') and signal['date'] != 'unknown':
                        logger.info(f"     Date: {signal['date']}")

            if company_research.get("url"):
                logger.info(f"Primary URL: {company_research['url']}")

        elif updates.get("company_summary"):
            # Legacy format fallback
            logger.info("Company Summary (legacy format):")
            logger.info(f"  {updates['company_summary']}")
            if updates.get("company_url"):
                logger.info(f"Source: {updates['company_url']}")
        else:
            logger.warning("No company summary generated")

    logger.info("="*60)

    return updates
