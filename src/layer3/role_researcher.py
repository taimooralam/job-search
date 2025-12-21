"""
Layer 3.5: Role Researcher (Phase 5.2)

Analyzes the specific role's business impact and timing significance.
- Scrapes role-specific information (responsibilities, KPIs)
- Extracts structured role research with business_impact and "why now"
- JSON-only output with Pydantic validation
- Links to company signals to explain hiring timing

New in Phase 5.2: Complete role research with "why now" analysis.
"""

import asyncio
import json
import logging
import re
import traceback
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError
from firecrawl import FirecrawlApp
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.state import JobState, RoleResearch
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.common.claude_web_research import ClaudeWebResearcher, TierType, CLAUDE_MODEL_TIERS
from src.common.utils import run_async


# ===== FIRECRAWL RESPONSE NORMALIZER =====

def _extract_search_results(search_response: Any) -> List[Any]:
    """
    Normalize FireCrawl search responses across SDK versions.

    Supports:
      - New client (v4.8.0+): response.web
      - Older client: response.data
      - Dict responses: {"web": [...]} or {"data": [...]}
      - Bare lists: [ {...}, {...} ]

    Returns:
        List of search result objects, or empty list if no results.
    """
    if not search_response:
        return []

    # Attribute-based shapes (Pydantic models)
    results = getattr(search_response, "web", None)
    if results is None and hasattr(search_response, "data"):
        results = getattr(search_response, "data", None)

    # Dict shape (for test mocks or API changes)
    if results is None and isinstance(search_response, dict):
        results = (
            search_response.get("web")
            or search_response.get("data")
            or search_response.get("results")
        )

    # Bare list shape
    if results is None and isinstance(search_response, list):
        results = search_response

    return results or []


# ===== PYDANTIC SCHEMA VALIDATION (Phase 5.2) =====

class RoleResearchOutput(BaseModel):
    """
    Pydantic schema for role research output (Phase 5.2).

    ROADMAP Phase 5.2 Quality Gates:
    - JSON-only output (no text outside JSON object)
    - Business impact bullets (3-5 items)
    - "Why now" explicitly references company signals
    - No hallucinated facts (only from scraped content + company signals)

    Schema Enforcement:
    - summary: 2-3 sentence role overview
    - business_impact: 3-5 bullets on how role drives business outcomes
    - why_now: 1-2 sentences linking to company signals
    """
    summary: str = Field(..., min_length=10, description="2-3 sentence role summary (ownership, scope, team)")
    business_impact: List[str] = Field(..., min_length=3, max_length=5, description="3-5 bullets on business outcomes")
    why_now: str = Field(..., min_length=10, description="1-2 sentences explaining timing significance")


# ===== PROMPT DESIGN =====

SYSTEM_PROMPT_ROLE_RESEARCH = """You are a business intelligence analyst specializing in role analysis.

Your task: Analyze the provided job description and company signals to understand:
1. Role summary (what this person will do, scope, team structure)
2. Business impact (how this role drives business outcomes)
3. "Why now" (timing significance based on company signals)

**CRITICAL RULES:**
1. Output ONLY a valid JSON object - no text before or after
2. Only use facts from the provided job description and company signals
3. DO NOT invent any details not in the provided context
4. For "why_now", explicitly reference at least one company signal if available
5. If signals not provided, infer timing from job description urgency/context

**OUTPUT FORMAT:**
{
  "summary": "2-3 sentence role overview (ownership, scope, team size if mentioned)",
  "business_impact": [
    "How this role drives revenue/growth",
    "How this role reduces risk/costs",
    "How this role enables strategic initiatives",
    "How this role improves customer outcomes",
    "How this role builds organizational capability"
  ],
  "why_now": "1-2 sentences explaining why this hire is needed now, referencing company signals"
}

**HALLUCINATION PREVENTION:**
- Only use facts from job description and company signals
- If a detail is unclear, don't invent it
- "Why now" must reference provided context (signals, JD urgency, growth mentions)
- Business impact must be tied to role responsibilities in JD

NO TEXT OUTSIDE THE JSON OBJECT."""

# Phase 5 enhancement: STAR-aware role research prompt
SYSTEM_PROMPT_ROLE_RESEARCH_STAR_AWARE = """You are a business intelligence analyst specializing in role analysis.

Your task: Analyze the provided job description and company signals to understand:
1. Role summary (what this person will do, scope, team structure)
2. Business impact (how this role drives business outcomes)
3. "Why now" (timing significance based on company signals)

**CANDIDATE'S STRONGEST DOMAINS:**
{candidate_domains}

**CANDIDATE'S PROVEN OUTCOME TYPES:**
{candidate_outcomes}

When analyzing business impact, consider how the role relates to the candidate's proven areas above.
This helps us understand which aspects of the role align with demonstrated expertise.

**CRITICAL RULES:**
1. Output ONLY a valid JSON object - no text before or after
2. Only use facts from the provided job description and company signals
3. DO NOT invent any details not in the provided context
4. For "why_now", explicitly reference at least one company signal if available
5. If signals not provided, infer timing from job description urgency/context

**OUTPUT FORMAT:**
{
  "summary": "2-3 sentence role overview (ownership, scope, team size if mentioned)",
  "business_impact": [
    "How this role drives revenue/growth",
    "How this role reduces risk/costs",
    "How this role enables strategic initiatives",
    "How this role improves customer outcomes",
    "How this role builds organizational capability"
  ],
  "why_now": "1-2 sentences explaining why this hire is needed now, referencing company signals"
}

**HALLUCINATION PREVENTION:**
- Only use facts from job description and company signals
- If a detail is unclear, don't invent it
- "Why now" must reference provided context (signals, JD urgency, growth mentions)
- Business impact must be tied to role responsibilities in JD

NO TEXT OUTSIDE THE JSON OBJECT."""

USER_PROMPT_ROLE_RESEARCH_TEMPLATE = """Analyze this role and explain its business impact:

JOB TITLE: {title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description}

ROLE-SPECIFIC CONTEXT (responsibilities & KPIs from external sources):
{role_context}

COMPANY SIGNALS (if available):
{company_signals}

Extract:
1. summary: 2-3 sentence role overview
2. business_impact: 3-5 bullets on how this role drives business outcomes
3. why_now: Why this hire is needed now (reference signals if available)

JSON only - no additional text:"""


class RoleResearcher:
    """
    Researches roles to understand business impact and timing (Phase 5.2).
    Phase 5 enhancement: STAR-aware prompts when candidate context available.

    Supports two execution backends:
    - Claude API (default): Uses Claude with WebSearch for research
    - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility
    """

    def __init__(
        self,
        tier: TierType = "balanced",
        use_claude_api: bool = True,
    ):
        """
        Initialize Role Researcher with dual backend support.

        Args:
            tier: Claude model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus).
                  Only used when use_claude_api=True. Default is "balanced" (Sonnet 4.5).
            use_claude_api: If True (default), use Claude API with WebSearch.
                           If False, use FireCrawl + OpenRouter (legacy mode).
        """
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)
        self.tier = tier
        self.use_claude_api = use_claude_api

        if use_claude_api:
            # Claude API with WebSearch for research (new default)
            self.claude_researcher = ClaudeWebResearcher(tier=tier)
            self.llm = None
            self.firecrawl = None
        else:
            # Legacy mode: FireCrawl + OpenRouter
            self.claude_researcher = None
            # GAP-066: Token tracking enabled
            self.llm = create_tracked_llm(
                model=Config.DEFAULT_MODEL,
                temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for factual analysis
                layer="layer3_role",
            )
            # FireCrawl for role-specific context (Phase 5.2)
            self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

    def _extract_star_context(self, state: JobState) -> tuple[Optional[str], Optional[str]]:
        """
        Extract candidate domains and outcome types from selected_stars.

        Phase 5 STAR-awareness: When STAR selector has run, extract the candidate's
        strongest domains and proven outcome types to bias role analysis.

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

    def _research_role_with_claude_api(self, state: JobState) -> Dict[str, Any]:
        """
        Research role using Claude API with WebSearch (new backend).

        This is the primary research method when use_claude_api=True. It uses
        Claude's built-in web_search tool to find and synthesize role information
        in a single API call, replacing the multi-step FireCrawl + LLM approach.

        Args:
            state: JobState with title, company, job_description, company_research

        Returns:
            Dict with role_research (structured)
        """
        title = state["title"]
        company = state["company"]
        job_description = state.get("job_description", "")

        # Log which method is being used for visibility
        self.logger.info(f"[Claude API] Using Claude API ({self.tier} tier, model: {CLAUDE_MODEL_TIERS.get(self.tier, 'unknown')}) for role research")
        self.logger.info(f"[Claude API] Researching role: {title} at {company}")

        # Extract company signals if available (from Phase 5.1)
        company_signals_text = "No company signals available."
        company_research = state.get("company_research")
        if company_research:
            signals = company_research.get("signals", [])
            if signals:
                signal_lines = []
                for sig in signals:
                    signal_lines.append(
                        f"- [{sig.get('type', 'unknown')}] {sig.get('description', 'N/A')} "
                        f"({sig.get('date', 'unknown')})"
                    )
                company_signals_text = "\n".join(signal_lines)

        # Call Claude API with web search
        try:
            # Run async method in sync context (handles nested event loops)
            result = run_async(
                self.claude_researcher.research_role(
                    company_name=company,
                    role_title=title,
                    job_description=job_description[:2000] if job_description else "",
                )
            )

            if not result.success:
                raise ValueError(f"Claude API role research failed: {result.error}")

            data = result.data
            self.logger.info(
                f"[Claude API] Role research complete - {result.searches_performed} searches, "
                f"{result.duration_ms}ms"
            )

            # Convert to RoleResearch format for JobState
            role_research: RoleResearch = {
                "summary": data.get("summary", ""),
                "business_impact": data.get("business_impact", []),
                "why_now": data.get("why_now", ""),
            }

            # Validate with Pydantic if needed
            if not role_research["business_impact"] or len(role_research["business_impact"]) < 3:
                # Ensure minimum 3 business impact points
                default_impacts = [
                    f"Drive key initiatives for the {title} role",
                    f"Improve operational efficiency at {company}",
                    "Contribute to strategic business objectives",
                ]
                while len(role_research["business_impact"]) < 3:
                    role_research["business_impact"].append(
                        default_impacts[len(role_research["business_impact"])]
                    )

            self.logger.info(
                f"[Claude API] Extracted {len(role_research['business_impact'])} business impact points"
            )

            return {
                "role_research": role_research
            }

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Claude API role research failed: {type(e).__name__}: {str(e)}"
            self.logger.error(f"{error_msg}\nTraceback:\n{tb}")

            return {
                "role_research": None,
                "errors": state.get("errors", []) + [error_msg],
                "role_research_traceback": tb,
            }

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        reraise=True
    )
    def _scrape_role_context(
        self,
        title: str,
        company: str,
        industry: Optional[str] = None
    ) -> Optional[str]:
        """
        Scrape role-specific context using FireCrawl (ROADMAP Phase 5.2).

        Queries (LLM-style but keyword-rich):
        1. "responsibilities and scope for {title} at {company}"
        2. "KPIs and success metrics for {title} in {industry or 'similar SaaS companies'}"

        Args:
            title: Job title
            company: Company name
            industry: Industry name (optional, extracted from job description)

        Returns:
            Combined scraped content or None if scraping fails
        """
        try:
            # Build queries per ROADMAP Phase 5.2 (LLM-style)
            queries = [
                (
                    f"What does a {title} typically own at {company}? "
                    f"Focus on engineering leadership, day-to-day impact, and team size."
                ),
                (
                    f"How is a {title} measured in {industry or 'similar SaaS companies'}? "
                    f"List the KPIs and success metrics that leaders watch."
                ),
            ]

            scraped_content = []

            for query in queries:
                try:
                    self.logger.info(f"[FireCrawl] Role search query: {query[:80]}...")

                    # Use FireCrawl search API
                    search_response = self.firecrawl.search(query, limit=2)

                    # Use normalizer to extract results (handles SDK version differences)
                    results = _extract_search_results(search_response)

                    if not results:
                        continue

                    # Get first result
                    if len(results) > 0:
                        top_result = results[0]
                        # Defensive URL extraction (handles both object attributes and dict keys)
                        url = getattr(top_result, "url", None) or (top_result.get("url") if isinstance(top_result, dict) else None)

                        if url:
                            self.logger.info(f"Found role context: {url}")

                            # Scrape the URL
                            scrape_result = self.firecrawl.scrape(
                                url,
                                formats=['markdown'],
                                only_main_content=True
                            )

                            if scrape_result and hasattr(scrape_result, 'markdown'):
                                content = scrape_result.markdown
                                # Limit to 1000 chars per query to avoid huge prompts
                                if content:
                                    scraped_content.append(content[:1000])
                                    self.logger.info(f"Scraped {len(content[:1000])} chars")

                except Exception as e:
                    self.logger.warning(f"Query failed: {e}")
                    continue

            if scraped_content:
                return "\n\n".join(scraped_content)

            return None

        except Exception as e:
            self.logger.warning(f"Role context scraping failed: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _analyze_role(
        self,
        title: str,
        company: str,
        job_description: str,
        company_signals: Optional[List[Dict[str, str]]] = None,
        role_context: Optional[str] = None,
        star_domains: Optional[str] = None,
        star_outcomes: Optional[str] = None
    ) -> RoleResearchOutput:
        """
        Extract role research from job description and company signals.

        Phase 5 enhancement: Supports STAR-aware prompts when candidate context available.

        Args:
            title: Job title
            company: Company name
            job_description: Full job description text
            company_signals: Optional list of company signals from Phase 5.1
            role_context: Optional scraped role context (responsibilities, KPIs)
            star_domains: Optional candidate domain areas from selected STARs
            star_outcomes: Optional candidate outcome types from selected STARs

        Returns:
            RoleResearchOutput with validated structure

        Raises:
            ValueError: If LLM output is invalid JSON or fails validation
        """
        # Format company signals for prompt
        signals_text = "No company signals available."
        if company_signals:
            signal_lines = []
            for sig in company_signals:
                signal_lines.append(
                    f"- [{sig.get('type', 'unknown')}] {sig.get('description', 'N/A')} "
                    f"({sig.get('date', 'unknown')})"
                )
            signals_text = "\n".join(signal_lines)

        # Format role context
        context_text = role_context if role_context else "No additional role context available."

        # Phase 5: Use STAR-aware prompt if candidate context available
        if star_domains and star_outcomes:
            system_prompt = SYSTEM_PROMPT_ROLE_RESEARCH_STAR_AWARE.format(
                candidate_domains=star_domains,
                candidate_outcomes=star_outcomes
            )
            self.logger.info(f"Using STAR-aware role prompt (domains: {star_domains[:50]}...)")
        else:
            system_prompt = SYSTEM_PROMPT_ROLE_RESEARCH

        # Call LLM for role analysis
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=USER_PROMPT_ROLE_RESEARCH_TEMPLATE.format(
                    title=title,
                    company=company,
                    job_description=job_description[:3000],  # Limit to avoid huge prompts
                    role_context=context_text,
                    company_signals=signals_text
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
            validated = RoleResearchOutput(**data)
        except ValidationError as e:
            error_messages = []
            for error in e.errors():
                field = ' -> '.join(str(x) for x in error['loc'])
                msg = error['msg']
                error_messages.append(f"{field}: {msg}")

            raise ValueError(
                f"RoleResearch schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_messages) +
                f"\nReceived data: {json.dumps(data, indent=2)[:500]}"
            )

        return validated

    def research_role(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to analyze role and generate research.

        Supports two execution backends:
        - Claude API (default): Uses Claude with WebSearch for research
        - FireCrawl (legacy): Uses FireCrawl + OpenRouter for backward compatibility

        Phase 5 enhancement: STAR-aware role analysis when candidate context available.

        Args:
            state: Current JobState with title, company, job_description, company_research
                   (and optionally selected_stars for STAR-aware analysis)

        Returns:
            Dict with role_research (RoleResearch structure)
        """
        # Route to Claude API backend if enabled (new default)
        if self.use_claude_api:
            self.logger.info(f"[Research Backend] Using Claude API ({self.tier} tier) for role research")
            return self._research_role_with_claude_api(state)

        # Legacy FireCrawl + OpenRouter mode
        self.logger.info(f"[Research Backend] Using FireCrawl + OpenRouter (legacy mode) for role research")

        try:
            # Extract company signals if available (from Phase 5.1)
            company_signals = None
            if state.get("company_research"):
                company_signals = state["company_research"].get("signals", [])

            # Phase 5 STAR-awareness: Extract candidate context if available
            star_domains, star_outcomes = self._extract_star_context(state)
            if star_domains:
                self.logger.info(f"STAR context available for role analysis: {len(star_domains.split(', '))} domain(s)")

            # Phase 5.2 ROADMAP: Scrape role-specific context
            self.logger.info(f"Scraping role-specific context for: {state['title']}")
            role_context = None
            try:
                # Extract industry from job description if available (simple heuristic)
                industry = None
                # Could enhance this to extract industry from JD, but keeping simple for now

                role_context = self._scrape_role_context(
                    title=state["title"],
                    company=state["company"],
                    industry=industry
                )

                if role_context:
                    self.logger.info(f"Scraped {len(role_context)} chars of role context")
                else:
                    self.logger.info("No role context found, using job description only")
            except Exception as scrape_error:
                self.logger.warning(f"Role context scraping failed: {scrape_error}, continuing without it")
                role_context = None

            # Analyze role (Phase 5 STAR-aware)
            self.logger.info(f"Analyzing role: {state['title']}")
            role_research_output = self._analyze_role(
                title=state["title"],
                company=state["company"],
                job_description=state["job_description"],
                company_signals=company_signals,
                role_context=role_context,
                star_domains=star_domains,
                star_outcomes=star_outcomes
            )

            self.logger.info(f"Extracted {len(role_research_output.business_impact)} business impact points")

            # Convert to TypedDict format for JobState
            role_research: RoleResearch = {
                "summary": role_research_output.summary,
                "business_impact": role_research_output.business_impact,
                "why_now": role_research_output.why_now
            }

            return {
                "role_research": role_research
            }

        except Exception as e:
            # Log error with full traceback and return empty (don't block pipeline)
            tb = traceback.format_exc()
            error_msg = f"Layer 3.5 (Role Researcher) failed: {type(e).__name__}: {str(e)}"
            self.logger.error(f"{error_msg}\nTraceback:\n{tb}")

            return {
                "role_research": None,
                "errors": state.get("errors", []) + [error_msg],
                "role_research_traceback": tb,
            }


# ===== LANGGRAPH NODE FUNCTION =====

def role_researcher_node(
    state: JobState,
    tier: TierType = "balanced",
    use_claude_api: bool = True,
) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 3.5: Role Researcher.

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
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer3.5")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    backend_name = f"Claude API ({tier} tier)" if use_claude_api else "FireCrawl + OpenRouter (legacy)"
    logger.info("="*60)
    logger.info(f"LAYER 3.5: Role Researcher - {backend_name}")
    logger.info("="*60)

    # Skip role research if company_research is None (upstream failure)
    company_research = state.get("company_research")
    if company_research is None:
        logger.info("SKIP_LAYER: role_research: Skipped (reason: company_research is None)")
        logger.info("="*60)
        return {"role_research": None}

    # Skip role research for recruitment agencies (no client company to research)
    company_type = company_research.get("company_type", "employer")
    if company_type == "recruitment_agency":
        logger.info("SKIP_LAYER: role_research: Skipped (reason: company_type is recruitment_agency)")
        logger.info("="*60)
        return {"role_research": None}

    logger.info(f"Analyzing role: {state['title']} at {state['company']}")

    # Use layer number 3.5 rounded to 4 for structured events (layer_start uses int)
    struct_logger.layer_start(4, "role_researcher")  # 3.5 -> use 4 slot for sub-layer

    try:
        researcher = RoleResearcher(tier=tier, use_claude_api=use_claude_api)
        updates = researcher.research_role(state)

        # Log results
        if updates.get("role_research"):
            role_research = updates["role_research"]
            logger.info("Role Summary:")
            logger.info(f"  {role_research['summary']}")

            impact_count = len(role_research['business_impact'])
            logger.info(f"Business Impact ({impact_count} points):")
            for idx, impact in enumerate(role_research['business_impact'], 1):
                logger.info(f"  {idx}. {impact}")

            logger.info("Why Now:")
            logger.info(f"  {role_research['why_now']}")

            struct_logger.layer_complete(4, "role_researcher", metadata={"impact_count": impact_count})
        else:
            logger.warning("No role research generated")
            struct_logger.layer_complete(4, "role_researcher")

    except Exception as e:
        tb = traceback.format_exc()
        error_detail = f"{type(e).__name__}: {str(e)}"
        struct_logger.layer_error(
            4,
            error_detail,
            "role_researcher",
            metadata={
                "exception_type": type(e).__name__,
                "traceback": tb,
            }
        )
        logger.error(f"Role research failed: {error_detail}\n{tb}")
        raise

    logger.info("="*60)

    return updates
