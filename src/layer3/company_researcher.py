"""
Layer 3: Company Researcher

Scrapes company website using FireCrawl and generates a concise summary using LLM.
This is the SIMPLIFIED version for today's vertical slice.

FUTURE: Will expand to include signals, timing analysis, industry keywords, "why now".
"""

import re
from typing import Dict, Any, Optional, Tuple
from firecrawl import FirecrawlApp
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState


# ===== PROMPT DESIGN =====

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
    """

    def __init__(self):
        """Initialize FireCrawl client and LLM."""
        # FireCrawl for web scraping
        self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

        # LLM for summarization
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,  # 0.3 for factual summaries
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )

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

    def research_company(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to research company and generate summary.

        Strategy:
        1. Try to scrape company website
        2. If successful, summarize scraped content
        3. If scraping fails, use LLM general knowledge as fallback
        4. Log any errors but don't block pipeline

        Args:
            state: Current JobState with company name

        Returns:
            Dict with company_summary and company_url keys
        """
        company = state["company"]
        company_url = None
        website_content = None

        # Step 1: Try to scrape company website
        try:
            company_url = self._construct_company_url(company)
            print(f"   Attempting to scrape: {company_url}")

            website_content = self._scrape_website(company_url)

            if website_content:
                print(f"   ✓ Scraped {len(website_content)} chars from {company_url}")
            else:
                print(f"   ⚠️  Scraping returned no content")

        except Exception as e:
            print(f"   ⚠️  Website scraping failed, will use LLM fallback")
            company_url = None  # Don't return invalid URL

        # Step 2: Generate summary (either from scraped content or general knowledge)
        try:
            if website_content:
                print(f"   Generating summary from scraped content...")
            else:
                print(f"   Generating summary from LLM general knowledge...")

            company_summary = self._summarize_with_llm(company, website_content)
            print(f"   ✓ Generated summary ({len(company_summary)} chars)")

            return {
                "company_summary": company_summary,
                "company_url": company_url
            }

        except Exception as e:
            # Complete failure - log error and return empty
            error_msg = f"Layer 3 (Company Researcher) failed: {str(e)}"
            print(f"   ✗ {error_msg}")

            return {
                "company_summary": None,
                "company_url": None,
                "errors": state.get("errors", []) + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def company_researcher_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 3: Company Researcher.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    print("\n" + "="*60)
    print("LAYER 3: Company Researcher")
    print("="*60)
    print(f"Researching: {state['company']}")

    researcher = CompanyResearcher()
    updates = researcher.research_company(state)

    # Print results
    if updates.get("company_summary"):
        print("\nCompany Summary:")
        print(f"  {updates['company_summary']}")
        if updates.get("company_url"):
            print(f"\nSource: {updates['company_url']}")
    else:
        print("\n⚠️  No company summary generated")

    print("="*60 + "\n")

    return updates
