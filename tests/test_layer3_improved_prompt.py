"""
Test enhanced prompt WITH improvements for Layer 3 Company Researcher.

Improvements implemented:
- Content quality gate (detects boilerplate)
- Fallback source strategy (Crunchbase, news)
- FireCrawl search instead of direct URLs
- Few-shot example
- Compressed prompt
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from firecrawl import FirecrawlApp
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from bson.objectid import ObjectId
from pymongo import MongoClient

from src.common.config import Config


# ===== IMPROVED ENHANCED PROMPT (Compressed + Few-Shot) =====

IMPROVED_SYSTEM_PROMPT = """You are a business intelligence analyst. Extract company signals showing business momentum, strategic priorities, and culture fit. Prioritize facts over speculation.

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
Content: "Acme Corp raised $50M Series B led by Sequoia in Jan 2024. The company serves 10,000+ customers..."

OUTPUT:
{
  "reasoning": {
    "sources_analyzed": ["https://acme.com"],
    "source_quality": {"https://acme.com": "high"},
    "missing_context": ["competitor landscape"],
    "assumptions": [],
    "confidence_level": "high"
  },
  "summary": "Acme Corp is a B2B SaaS company serving 10,000+ customers, recently raising $50M Series B.",
  "signals": [
    {
      "type": "funding",
      "description": "Raised $50M Series B led by Sequoia in January 2024",
      "date": "2024-01",
      "source": "https://acme.com",
      "business_context": "Strong investor confidence; extended runway for growth"
    },
    {
      "type": "growth",
      "description": "Serves 10,000+ customers",
      "date": "unknown",
      "source": "https://acme.com",
      "business_context": "Established customer base signals product-market fit"
    }
  ],
  "url": "https://acme.com"
}

**YOUR OUTPUT FORMAT** (follow the example above):
{
  "reasoning": {...},
  "summary": "2-3 sentences emphasizing market position",
  "signals": [{type, description, date, source, business_context}, ...],
  "url": "primary URL"
}

**BEST-EFFORT EXTRACTION**:
- Extract AT LEAST ONE signal if ANY facts exist
- General facts count as "growth" signals
- Empty signals only if content is completely non-informational

NO TEXT OUTSIDE JSON."""

IMPROVED_USER_PROMPT_TEMPLATE = """Extract company signals:

**COMPANY**: {company}

**CANDIDATE CONTEXT** (prioritize these domains):
- Proven: .NET, Microservices, Team Leadership, Backend Architecture
- Outcomes: Team scaling, Performance optimization, System reliability

**SCRAPED CONTENT**:
{scraped_content}

Output JSON with reasoning block first:"""


# ===== PYDANTIC SCHEMAS =====

class CompanySignalModel(BaseModel):
    type: str
    description: str = Field(..., min_length=1)
    date: str = Field(default="unknown")
    source: str = Field(..., min_length=1)
    business_context: str = Field(default="")


class ReasoningBlock(BaseModel):
    sources_analyzed: List[str] = Field(default_factory=list)
    source_quality: Dict[str, str] = Field(default_factory=dict)
    missing_context: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    confidence_level: str = Field(default="unknown")


class ImprovedCompanyResearchOutput(BaseModel):
    reasoning: ReasoningBlock
    summary: str = Field(..., min_length=10)
    signals: List[CompanySignalModel] = Field(default_factory=list, max_length=10)
    url: str = Field(..., min_length=1)


# ===== IMPROVED SCRAPING WITH QUALITY GATES =====

class ImprovedCompanyResearcher:
    """Enhanced Company Researcher with scraping improvements"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )

    def _assess_content_quality(self, content: str) -> str:
        """
        IMPROVEMENT #9: Content quality gate

        Detects low-value boilerplate content (cookie policies, legal text).
        Returns: "high", "medium", or "low"
        """
        if not content or len(content) < 100:
            return "low"

        content_lower = content.lower()

        # Low-value indicators
        boilerplate_phrases = [
            "cookie policy", "privacy policy", "terms of service",
            "we use cookies", "accept all cookies", "manage preferences",
            "gdpr", "this website uses cookies", "cookie settings"
        ]

        boilerplate_count = sum(1 for phrase in boilerplate_phrases if phrase in content_lower)

        # Calculate boilerplate density
        if boilerplate_count >= 3:
            return "low"
        elif boilerplate_count >= 1:
            return "medium"

        # Check for business content indicators
        business_phrases = [
            "funding", "raised", "series", "customers", "revenue",
            "partnership", "acquisition", "launched", "product",
            "team", "employees", "growth", "market", "ceo"
        ]

        business_count = sum(1 for phrase in business_phrases if phrase in content_lower)

        if business_count >= 3:
            return "high"
        elif business_count >= 1:
            return "medium"

        return "low"

    def _search_and_scrape(self, query: str, expected_domain: Optional[str] = None) -> Optional[Dict[str, str]]:
        """
        IMPROVEMENT #3: Use FireCrawl search to find and scrape best result

        Args:
            query: Search query
            expected_domain: Optional domain filter (e.g., "crunchbase.com")

        Returns:
            {"url": str, "content": str} or None
        """
        try:
            print(f"    Searching: {query[:60]}...")
            search_response = self.firecrawl.search(query, limit=3)

            # Extract results
            results = getattr(search_response, "web", None) or getattr(search_response, "data", None) or []

            if not results:
                return None

            # Find best result (prefer expected_domain if provided)
            best_url = None
            for result in results:
                url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)
                if not url:
                    continue

                # Filter by expected domain
                if expected_domain and expected_domain in url.lower():
                    best_url = url
                    break
                elif not best_url:
                    best_url = url

            if not best_url:
                return None

            print(f"      Found: {best_url}")

            # Scrape the URL
            scrape_result = self.firecrawl.scrape(
                best_url,
                formats=['markdown'],
                only_main_content=True
            )

            if scrape_result and hasattr(scrape_result, 'markdown'):
                content = scrape_result.markdown[:2000] if scrape_result.markdown else None
                if content:
                    quality = self._assess_content_quality(content)
                    print(f"      Scraped: {len(content)} chars (quality: {quality})")
                    return {
                        "url": best_url,
                        "content": content,
                        "quality": quality
                    }

            return None

        except Exception as e:
            print(f"      ✗ Search/scrape failed: {e}")
            return None

    def scrape_with_fallbacks(self, company: str) -> Dict[str, Dict[str, str]]:
        """
        IMPROVEMENT #2: Aggressive multi-source scraping with fallbacks

        Strategy:
        1. Search for official site (not direct URL construction)
        2. Search Crunchbase
        3. Search recent news
        4. Only keep high/medium quality sources
        """
        scraped_data = {}

        # Source 1: Official site (using search, not URL construction)
        print(f"  [1/3] Searching for official site...")
        official_result = self._search_and_scrape(
            f"{company} official website about careers company",
            expected_domain=None
        )
        if official_result and official_result['quality'] in ['high', 'medium']:
            scraped_data['official_site'] = official_result
        else:
            print(f"      ✗ Official site: low quality or failed")

        # Source 2: Crunchbase (IMPROVEMENT #2: fallback source)
        print(f"  [2/3] Searching Crunchbase...")
        crunchbase_result = self._search_and_scrape(
            f"{company} crunchbase company profile funding",
            expected_domain="crunchbase.com"
        )
        if crunchbase_result and crunchbase_result['quality'] in ['high', 'medium']:
            scraped_data['crunchbase'] = crunchbase_result
        else:
            print(f"      ✗ Crunchbase: not found or low quality")

        # Source 3: Recent news (IMPROVEMENT #2: fallback source)
        print(f"  [3/3] Searching recent news...")
        news_result = self._search_and_scrape(
            f"{company} news funding acquisition partnership launch 2024",
            expected_domain=None
        )
        if news_result and news_result['quality'] in ['high', 'medium']:
            scraped_data['news'] = news_result
        else:
            print(f"      ✗ News: not found or low quality")

        return scraped_data

    def extract_signals(self, company: str, scraped_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Extract signals using improved prompt"""
        # Build content sections
        content_sections = []
        for source_name, data in scraped_data.items():
            content_sections.append(
                f"=== SOURCE: {source_name} ({data['url']}) [quality: {data.get('quality', 'unknown')}] ===\n{data['content']}\n"
            )

        scraped_content = "\n".join(content_sections)

        # Call LLM
        messages = [
            SystemMessage(content=IMPROVED_SYSTEM_PROMPT),
            HumanMessage(
                content=IMPROVED_USER_PROMPT_TEMPLATE.format(
                    company=company,
                    scraped_content=scraped_content[:6000]
                )
            )
        ]

        response = self.llm.invoke(messages)
        llm_output = response.content.strip()

        # Parse JSON
        import re
        json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)
        json_str = json_match.group(0) if json_match else llm_output

        data = json.loads(json_str)
        validated = ImprovedCompanyResearchOutput(**data)

        return {
            "raw_output": llm_output,
            "parsed": validated.model_dump(),
            "prompt_length": len(IMPROVED_SYSTEM_PROMPT) + len(messages[1].content),
            "sources_used": len(scraped_data)
        }


# ===== TEST RUNNER =====

def main():
    """Run the improved test"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*100)
    print("LAYER 3 COMPANY RESEARCHER: ENHANCED + IMPROVEMENTS TEST")
    print("="*100)

    # Fetch job
    print(f"\n1. Fetching job from MongoDB...")
    mongo_client = MongoClient(Config.MONGODB_URI)
    db = mongo_client["jobs"]
    job = db["level-2"].find_one({"_id": ObjectId("6929c97b45fa3c355f84ba2d")})

    company = job.get("company") or job.get("firm")
    print(f"   Company: {company}")
    print(f"   Role: {job.get('title')}")

    # Run improved researcher
    researcher = ImprovedCompanyResearcher()

    print(f"\n2. Scraping with improved strategy (quality gates + fallbacks)...")
    scraped_data = researcher.scrape_with_fallbacks(company)
    print(f"   ✓ Successfully scraped {len(scraped_data)} source(s)")

    if not scraped_data:
        print("\n   ERROR: No high/medium quality sources found. Cannot proceed.")
        return

    print(f"\n3. Extracting signals with improved prompt...")
    results = researcher.extract_signals(company, scraped_data)

    # Display results
    print("\n" + "="*100)
    print("RESULTS: ENHANCED + IMPROVEMENTS")
    print("="*100)

    parsed = results["parsed"]

    # Reasoning block
    print(f"\n📊 REASONING BLOCK:")
    reasoning = parsed['reasoning']
    print(f"  Sources Analyzed: {len(reasoning['sources_analyzed'])}")
    for idx, source in enumerate(reasoning['sources_analyzed'], 1):
        quality = reasoning['source_quality'].get(source, 'unknown')
        print(f"    {idx}. {source} [quality: {quality}]")

    print(f"\n  Missing Context: {reasoning['missing_context'] if reasoning['missing_context'] else 'None'}")
    print(f"  Assumptions: {reasoning['assumptions'] if reasoning['assumptions'] else 'None'}")
    print(f"  Confidence Level: {reasoning['confidence_level']}")

    # Summary
    print(f"\n📝 SUMMARY:")
    print(f"  {parsed['summary']}")

    # Signals
    print(f"\n🎯 SIGNALS ({len(parsed['signals'])} found):")
    if parsed['signals']:
        for idx, signal in enumerate(parsed['signals'], 1):
            print(f"\n  {idx}. [{signal['type'].upper()}] {signal['description']}")
            print(f"     Date: {signal['date']}")
            print(f"     Source: {signal['source'][:70]}...")
            if signal.get('business_context'):
                print(f"     💡 Context: {signal['business_context']}")
    else:
        print("  (none extracted)")

    print(f"\n🔗 PRIMARY URL: {parsed['url']}")

    # Metrics
    print(f"\n" + "-"*100)
    print("📈 METRICS:")
    print(f"  Sources scraped: {results['sources_used']}")
    print(f"  Signals extracted: {len(parsed['signals'])}")
    print(f"  Prompt length: {results['prompt_length']} chars")
    print(f"  Confidence: {reasoning['confidence_level']}")

    print("\n" + "="*100)
    print("IMPROVEMENTS APPLIED:")
    print("="*100)
    print("  ✅ #9: Content quality gate (filters boilerplate)")
    print("  ✅ #2: Fallback sources (Crunchbase, news)")
    print("  ✅ #3: FireCrawl search (vs direct URLs)")
    print("  ✅ #7: Few-shot example in prompt")
    print("  ✅ #8: Compressed prompt (more concise)")
    print("\n" + "="*100)
    print("TEST COMPLETE")
    print("="*100 + "\n")


if __name__ == "__main__":
    main()
