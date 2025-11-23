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

import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError
from firecrawl import FirecrawlApp
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from pymongo import MongoClient

from src.common.config import Config
from src.common.state import JobState, CompanySignal, CompanyResearch


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

class CompanySignalModel(BaseModel):
    """Pydantic model for company signal validation."""
    type: str = Field(..., description="Signal type: funding, acquisition, leadership_change, product_launch, partnership, growth")
    description: str = Field(..., min_length=1, description="Brief description of the signal")
    date: str = Field(default="unknown", description="ISO date or 'unknown'")
    source: str = Field(..., min_length=1, description="Source URL where signal was found")


class CompanyResearchOutput(BaseModel):
    """
    Pydantic schema for company research output (Phase 5.1).

    ROADMAP Phase 5 Quality Gates:
    - JSON-only output (no text outside JSON object)
    - Structured signals with source attribution
    - No hallucinated facts (only from scraped content)
    - Each signal must have a source URL

    Schema Enforcement:
    - summary: 2-3 sentence company overview
    - signals: List of CompanySignal objects (0-10 items)
    - url: Primary company URL
    """
    summary: str = Field(..., min_length=10, description="2-3 sentence company summary")
    signals: List[CompanySignalModel] = Field(default_factory=list, max_length=10, description="0-10 company signals with sources")
    url: str = Field(..., min_length=1, description="Primary company URL")


# ===== PROMPT DESIGN =====

# Phase 5.1: Multi-source signal extraction prompts

SYSTEM_PROMPT_COMPANY_SIGNALS = """You are a business intelligence analyst specializing in extracting structured company signals.

Your task: Analyze scraped content from multiple sources and extract:
1. A 2-3 sentence company summary (what they do, market position, size if mentioned)
2. Structured business signals with SOURCE ATTRIBUTION

**CRITICAL RULES:**
1. Output ONLY a valid JSON object - no text before or after
2. Only use facts explicitly stated in the provided scraped content
3. DO NOT invent any details (funding amounts, dates, names, products) not in the scraped text
4. For each signal, you MUST cite the source URL where you found it
5. If a detail (date, amount, investor name) is not in the scraped text, set it to "unknown"

**SIGNAL TYPES:**
- "funding": Funding rounds, investments, capital raises
- "acquisition": Company acquisitions (as buyer or seller)
- "leadership_change": New executives, board changes, departures
- "product_launch": New products, features, or service launches
- "partnership": Strategic partnerships, collaborations
- "growth": Headcount growth, revenue milestones, expansion

**OUTPUT FORMAT:**
{
  "summary": "2-3 sentence company summary",
  "signals": [
    {
      "type": "funding",
      "description": "Exact fact from scraped content",
      "date": "YYYY-MM-DD or 'unknown'",
      "source": "URL where this fact was found"
    }
  ],
  "url": "primary company URL"
}

**HALLUCINATION PREVENTION:**
- If scraped content doesn't mention a signal, don't invent it
- If a field is unclear, use "unknown" not a guess
- Description must be a direct fact from the scraped content
- Every signal MUST have a source URL from the provided sources

**BEST-EFFORT EXTRACTION:**
- If you find ANY factual information (company description, products, team size, technology stack), extract at least one signal
- Even general facts ("the company operates in X industry", "they serve Y market") count as valid signals with type "growth"
- An empty signals array is only acceptable if the scraped content truly contains no factual information

NO TEXT OUTSIDE THE JSON OBJECT."""

# Phase 5 enhancement: STAR-aware signal extraction prompts
SYSTEM_PROMPT_COMPANY_SIGNALS_STAR_AWARE = """You are a business intelligence analyst specializing in extracting structured company signals.

Your task: Analyze scraped content from multiple sources and extract:
1. A 2-3 sentence company summary (what they do, market position, size if mentioned)
2. Structured business signals with SOURCE ATTRIBUTION
3. **Pay special attention to signals in the candidate's domain areas** (listed below)

**CANDIDATE'S STRONGEST DOMAINS:**
{candidate_domains}

**CANDIDATE'S PROVEN OUTCOME TYPES:**
{candidate_outcomes}

Prioritize extracting signals that align with these domains and outcomes, as they will help demonstrate fit.

**CRITICAL RULES:**
1. Output ONLY a valid JSON object - no text before or after
2. Only use facts explicitly stated in the provided scraped content
3. DO NOT invent any details (funding amounts, dates, names, products) not in the scraped text
4. For each signal, you MUST cite the source URL where you found it
5. If a detail (date, amount, investor name) is not in the scraped text, set it to "unknown"

**SIGNAL TYPES:**
- "funding": Funding rounds, investments, capital raises
- "acquisition": Company acquisitions (as buyer or seller)
- "leadership_change": New executives, board changes, departures
- "product_launch": New products, features, or service launches
- "partnership": Strategic partnerships, collaborations
- "growth": Headcount growth, revenue milestones, expansion

**OUTPUT FORMAT:**
{
  "summary": "2-3 sentence company summary",
  "signals": [
    {
      "type": "funding",
      "description": "Exact fact from scraped content",
      "date": "YYYY-MM-DD or 'unknown'",
      "source": "URL where this fact was found"
    }
  ],
  "url": "primary company URL"
}

**BEST-EFFORT EXTRACTION:**
- If you find ANY factual information, extract at least one signal
- Even general facts count as valid signals with type "growth"
- An empty signals array is only acceptable if the scraped content truly contains no factual information

NO TEXT OUTSIDE THE JSON OBJECT."""

USER_PROMPT_COMPANY_SIGNALS_TEMPLATE = """Analyze the following scraped content and extract company signals:

COMPANY: {company}

SCRAPED CONTENT FROM MULTIPLE SOURCES:
{scraped_content}

Extract:
1. summary: 2-3 sentence overview of the company
2. signals: List of business signals with type, description, date, source
3. url: Primary company URL

JSON only - no additional text:"""

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
    """

    def __init__(self):
        """Initialize FireCrawl client, LLM, and MongoDB cache."""
        # FireCrawl for web scraping
        self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

        # LLM for summarization
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for factual summaries
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )

        # MongoDB for caching (Phase 1.3)
        self.mongo_client = MongoClient(Config.MONGODB_URI)
        self.cache_collection = self.mongo_client["jobs"]["company_cache"]
        # Create TTL index on cached_at field (7 days)
        self.cache_collection.create_index("cached_at", expireAfterSeconds=7*24*60*60)

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
            print(f"   ✓ Cache HIT for {company_name}")

            # Phase 5.1: Check for new structured company_research
            if 'company_research' in cached:
                company_research = cached['company_research']
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

        print(f"   ✗ Cache MISS for {company_name}")
        return None

    def _store_cache(
        self,
        company_name: str,
        company_research: Optional[CompanyResearchOutput] = None,
        summary: Optional[str] = None,
        url: Optional[str] = None
    ):
        """
        Store company research in MongoDB cache with TTL (Phase 5.1 enhanced).

        Args:
            company_name: Company name
            company_research: CompanyResearchOutput (Phase 5.1 format)
            summary: Legacy format (backward compatibility)
            url: Legacy format (backward compatibility)
        """
        cache_key = self._get_cache_key(company_name)

        cache_doc = {
            "company_key": cache_key,
            "company_name": company_name,
            "cached_at": datetime.utcnow()
        }

        # Phase 5.1: Store structured company_research if provided
        if company_research:
            cache_doc["company_research"] = company_research.model_dump()
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

        print(f"   ✓ Cached research for {company_name}")

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

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        reraise=True
    )
    def _scrape_website(self, url: str) -> Optional[str]:
        """
        Scrape company website using FireCrawl.

        Returns cleaned text content or None if scraping fails.
        Retries once on failure.
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
                # Limit to first 2000 chars to avoid huge prompts
                return content[:2000] if content else None

            return None

        except Exception as e:
            print(f"   FireCrawl scraping failed: {str(e)}")
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
            print(f"   ⚠️  Job posting scrape failed: {e}")

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _summarize_with_llm(
        self,
        company: str,
        website_content: Optional[str] = None
    ) -> str:
        """
        Generate company summary using LLM.

        If website_content is provided, summarize it.
        Otherwise, use LLM's general knowledge as fallback.
        """
        if website_content:
            # Use scraped content
            messages = [
                SystemMessage(content=SYSTEM_PROMPT_SCRAPE),
                HumanMessage(
                    content=USER_PROMPT_SCRAPE_TEMPLATE.format(
                        company=company,
                        website_content=website_content
                    )
                )
            ]
        else:
            # Fallback to general knowledge
            messages = [
                SystemMessage(content=SYSTEM_PROMPT_FALLBACK),
                HumanMessage(
                    content=USER_PROMPT_FALLBACK_TEMPLATE.format(company=company)
                )
            ]

        response = self.llm.invoke(messages)
        return response.content.strip()

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
            print(f"[FireCrawl][CompanyResearcher] {source_name} search query: {query}")
            # Use FireCrawl search API to find relevant URLs
            # Limit to top 3 results to save API calls
            search_response = self.firecrawl.search(query, limit=3)

            # Use normalizer to extract results (handles SDK version differences)
            results = _extract_search_results(search_response)

            if not results:
                print(f"   No search results for {source_name}")
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
                print(f"   No suitable URL found for {source_name}")
                return None

            print(f"   Found URL: {top_result}")

            # Scrape the top result
            content = self._scrape_website(top_result)

            if content:
                return {
                    "url": top_result,
                    "content": content
                }

            return None

        except Exception as e:
            print(f"   Search failed for {source_name}: {e}")
            raise  # Re-raise for retry logic

    def _scrape_multiple_sources(self, company: str) -> Dict[str, Dict[str, str]]:
        """
        Scrape company information from multiple sources (Phase 5.1).

        Queries (LLM-style but keyword-rich):
        1. "official website and homepage for {company} (company site, about, careers)"
        2. "LinkedIn company profile for {company} (company page, people, about)"
        3. "{company} Crunchbase organization profile (funding, investors, overview)"
        4. "recent news about {company} funding, acquisitions, expansion, product launches, leadership changes"

        Returns:
            Dict with source_name -> {"url": str, "content": str}
            Omits sources where scraping failed.
        """
        # Build queries per ROADMAP Phase 5.1 (LLM-style)
        queries = {
            "official_site": (
                f"official website and homepage for {company} "
                f"(company site, about, careers)"
            ),
            "linkedin": (
                f"Where is the official LinkedIn page for {company}? "
                f"Find the company page that lists people and the about section."
            ),
            "crunchbase": (
                f"Locate the Crunchbase profile for {company} with funding, investors, and overview."
            ),
            "news": (
                f"What recent news stories mention {company} (funding, acquisitions, expansion, product launches, leadership changes)?"
            ),
        }

        scraped_data = {}

        for source_name, query in queries.items():
            try:
                print(f"   Searching: {query}")

                if source_name == "official_site":
                    # Use direct URL construction for official site
                    url = self._construct_company_url(company)
                    content = self._scrape_website(url)

                    if content:
                        scraped_data[source_name] = {
                            "url": url,
                            "content": content
                        }
                        print(f"   ✓ Scraped {len(content)} chars from {source_name}")
                else:
                    # Phase 5.1: Use FireCrawl search for LinkedIn, Crunchbase, news
                    search_results = self._search_with_firecrawl(query, source_name)

                    if search_results:
                        # Extract top result
                        url = search_results['url']
                        content = search_results['content']

                        scraped_data[source_name] = {
                            "url": url,
                            "content": content
                        }
                        print(f"   ✓ Scraped {len(content)} chars from {source_name}")

            except Exception as e:
                print(f"   ⚠️  Failed to scrape {source_name}: {e}")
                continue

        return scraped_data

    def _analyze_company_signals(
        self,
        company: str,
        scraped_data: Dict[str, Dict[str, str]],
        star_domains: Optional[str] = None,
        star_outcomes: Optional[str] = None
    ) -> CompanyResearchOutput:
        """
        Extract company signals from scraped content using LLM (Phase 5.1).

        Phase 5 enhancement: Supports STAR-aware prompts when candidate context available.

        Args:
            company: Company name
            scraped_data: Dict of {source_name: {"url": str, "content": str}}
            star_domains: Optional candidate domain areas from selected STARs
            star_outcomes: Optional candidate outcome types from selected STARs

        Returns:
            CompanyResearchOutput with validated signals

        Raises:
            ValueError: If LLM output is invalid JSON or fails validation
        """
        # Build concatenated content with source tags
        content_sections = []
        for source_name, data in scraped_data.items():
            content_sections.append(
                f"=== SOURCE: {source_name} ({data['url']}) ===\n{data['content']}\n"
            )

        scraped_content = "\n".join(content_sections)

        # Phase 5: Use STAR-aware prompt if candidate context available
        if star_domains and star_outcomes:
            system_prompt = SYSTEM_PROMPT_COMPANY_SIGNALS_STAR_AWARE.format(
                candidate_domains=star_domains,
                candidate_outcomes=star_outcomes
            )
            print(f"   Using STAR-aware prompt (domains: {star_domains[:50]}...)")
        else:
            system_prompt = SYSTEM_PROMPT_COMPANY_SIGNALS

        # Call LLM for signal extraction
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=USER_PROMPT_COMPANY_SIGNALS_TEMPLATE.format(
                    company=company,
                    scraped_content=scraped_content[:5000]  # Limit to avoid huge prompts
                )
            )
        ]

        response = self.llm.invoke(messages)
        llm_output = response.content.strip()

        # Extract JSON from response (in case LLM adds extra text)
        json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)

        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = llm_output

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
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

            raise ValueError(
                f"CompanyResearch schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_messages) +
                f"\nReceived data: {json.dumps(data, indent=2)[:500]}"
            )

        return validated

    def _fallback_signal_extraction(
        self,
        company: str,
        official_site_data: Dict[str, str]
    ) -> CompanyResearchOutput:
        """
        Defensive fallback: Extract minimal signals from official site content only.

        Phase 5 enhancement: When multi-source scrape yields 0 signals or LLM returns empty,
        run a second-pass extraction using only official_site content with best-effort rules.

        Args:
            company: Company name
            official_site_data: {"url": str, "content": str} from official site

        Returns:
            CompanyResearchOutput with at least 1 signal (or minimal valid output)
        """
        print(f"   Running fallback signal extraction from official site...")

        fallback_prompt = f"""Analyze this official company website content and extract ANY factual information as signals.

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

        messages = [
            SystemMessage(content="You are a business analyst. Extract factual company information. Output JSON only."),
            HumanMessage(content=fallback_prompt)
        ]

        response = self.llm.invoke(messages)
        llm_output = response.content.strip()

        # Extract JSON
        json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)
        json_str = json_match.group(0) if json_match else llm_output

        try:
            data = json.loads(json_str)

            # Ensure at least one signal if none extracted
            if not data.get('signals'):
                data['signals'] = [{
                    "type": "growth",
                    "description": f"{company} operates as a business (details from official website)",
                    "date": "unknown",
                    "source": official_site_data['url']
                }]

            return CompanyResearchOutput(**data)

        except (json.JSONDecodeError, ValidationError) as e:
            # Last resort: return minimal valid output
            print(f"   Fallback parsing failed: {e}, returning minimal output")
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

        Strategy (Phase 5.1 with multi-source scraping + Phase 5 enhancements):
        0. Check MongoDB cache (7-day TTL)
        1. Extract STAR context if available (Phase 5 STAR-awareness)
        2. If cache miss, scrape multiple sources (official site, LinkedIn, Crunchbase, news)
        3. Extract structured signals via LLM (JSON-only with Pydantic validation)
        4. If 0 signals extracted, run defensive fallback on official_site content
        5. Store result in cache with CompanyResearch structure
        6. Fall back to legacy approach if Phase 5.1 fails
        7. Log any errors but don't block pipeline

        Args:
            state: Current JobState with company name (and optionally selected_stars)

        Returns:
            Dict with company_research (structured) + legacy company_summary/company_url
        """
        company = state["company"]
        scraped_job_posting = self._scrape_job_posting(state.get("job_url", ""))

        # Phase 5 STAR-awareness: Extract candidate context if available
        star_domains, star_outcomes = self._extract_star_context(state)
        if star_domains:
            print(f"   STAR context available: {len(star_domains.split(', '))} domain(s)")

        # Step 0: Check cache first
        try:
            cached_data = self._check_cache(company)
            if cached_data:
                if scraped_job_posting:
                    cached_data["scraped_job_posting"] = scraped_job_posting
                return cached_data
        except Exception as e:
            print(f"   ⚠️  Cache check failed: {e}, proceeding with research")

        # Cache miss - proceed with Phase 5.1 research
        try:
            # Step 1: Multi-source scraping (Phase 5.1)
            print(f"   Phase 5.1: Multi-source scraping...")
            scraped_data = self._scrape_multiple_sources(company)

            if not scraped_data:
                raise ValueError("No sources successfully scraped")

            print(f"   ✓ Scraped {len(scraped_data)} source(s)")

            # Step 2: Extract signals via LLM (Phase 5.1 + STAR-aware)
            print(f"   Extracting company signals via LLM...")
            company_research_output = self._analyze_company_signals(
                company, scraped_data,
                star_domains=star_domains,
                star_outcomes=star_outcomes
            )

            print(f"   ✓ Extracted {len(company_research_output.signals)} signal(s)")

            # Phase 5 defensive fallback: If 0 signals, try second-pass extraction
            if len(company_research_output.signals) == 0 and 'official_site' in scraped_data:
                print(f"   ⚠️  No signals extracted, running fallback extraction...")
                company_research_output = self._fallback_signal_extraction(
                    company, scraped_data['official_site']
                )
                print(f"   ✓ Fallback extracted {len(company_research_output.signals)} signal(s)")

            # Step 3: Store in cache (Phase 5.1 format)
            try:
                self._store_cache(company, company_research=company_research_output)
            except Exception as e:
                print(f"   ⚠️  Failed to cache results: {e}")

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
                "url": company_research_output.url
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
            print(f"   ⚠️  Phase 5.1 research failed: {e}")
            print(f"   Falling back to legacy single-source approach...")

            try:
                # Legacy single-source scraping
                company_url = self._construct_company_url(company)
                website_content = self._scrape_website(company_url)

                if website_content:
                    print(f"   ✓ Legacy scrape: {len(website_content)} chars from {company_url}")
                else:
                    print(f"   Using LLM general knowledge fallback...")

                company_summary = self._summarize_with_llm(company, website_content)
                print(f"   ✓ Generated summary ({len(company_summary)} chars)")

                # Store in cache (legacy format)
                try:
                    self._store_cache(company, summary=company_summary, url=company_url)
                except Exception as cache_error:
                    print(f"   ⚠️  Failed to cache results: {cache_error}")

                return {
                    "company_summary": company_summary,
                    "company_url": company_url,
                    "scraped_job_posting": scraped_job_posting
                }

            except Exception as legacy_error:
                # Complete failure - log error and return empty
                error_msg = f"Layer 3 (Company Researcher) failed: {str(legacy_error)}"
                print(f"   ✗ {error_msg}")

                return {
                    "company_summary": None,
                    "company_url": None,
                    "scraped_job_posting": scraped_job_posting,
                    "errors": state.get("errors", []) + [error_msg]
                }


# ===== LANGGRAPH NODE FUNCTION =====

def company_researcher_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 3: Company Researcher (Phase 5.1).

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    print("\n" + "="*60)
    print("LAYER 3: Company Researcher (Phase 5.1)")
    print("="*60)
    print(f"Researching: {state['company']}")

    researcher = CompanyResearcher()
    updates = researcher.research_company(state)

    # Print results (Phase 5.1 format)
    if updates.get("company_research"):
        company_research = updates["company_research"]
        print("\nCompany Summary:")
        print(f"  {company_research['summary']}")

        if company_research.get("signals"):
            print(f"\nCompany Signals ({len(company_research['signals'])} found):")
            for idx, signal in enumerate(company_research['signals'], 1):
                print(f"  {idx}. [{signal['type']}] {signal['description']}")
                if signal.get('date') and signal['date'] != 'unknown':
                    print(f"     Date: {signal['date']}")

        if company_research.get("url"):
            print(f"\nPrimary URL: {company_research['url']}")

    elif updates.get("company_summary"):
        # Legacy format fallback
        print("\nCompany Summary (legacy format):")
        print(f"  {updates['company_summary']}")
        if updates.get("company_url"):
            print(f"\nSource: {updates['company_url']}")
    else:
        print("\n⚠️  No company summary generated")

    print("="*60 + "\n")

    return updates
