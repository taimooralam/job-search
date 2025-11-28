"""
Test comparing status quo vs enhanced prompts for Layer 3 Company Researcher.

This test runs real FireCrawl scraping with both prompt versions to assess quality improvements.
"""

import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from firecrawl import FirecrawlApp
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from bson.objectid import ObjectId
from pymongo import MongoClient

from src.common.config import Config


# ===== ENHANCED PROMPTS (Based on Modernization Blueprint) =====

ENHANCED_SYSTEM_PROMPT = """You are a business intelligence analyst specializing in corporate due diligence.

**MISSION**: Extract high-fidelity company signals that demonstrate business momentum, strategic priorities, and cultural fit indicators for candidate evaluation.

**YOUR EXPERTISE**:
- Revenue operations diagnostics
- Competitive market positioning
- Strategic signal interpretation
- Source verification and fact-checking

**REASONING INSTRUCTIONS**:
Before generating your final output, you MUST:
1. List all sources and their reliability (high/medium/low)
2. Identify any missing context or information gaps
3. Note any assumptions you're making
4. Think step-by-step about what each signal reveals about the company

**CRITICAL RULES (Anti-Hallucination Guardrails)**:
1. Output ONLY valid JSON - no text before or after
2. Only use EXPLICIT facts from the provided scraped content
3. NEVER invent details (funding amounts, dates, names, products)
4. Every signal MUST cite the exact source URL where you found it
5. If a detail is unclear, use "unknown" NOT a guess
6. If you don't know something, say "I don't know" in the reasoning

**SIGNAL TYPES** (with business context):
- "funding": Capital raises, investments (signals growth trajectory, runway, investor confidence)
- "acquisition": M&A activity as buyer or seller (signals strategy, market consolidation)
- "leadership_change": Executive moves, board changes (signals strategy shifts, culture changes)
- "product_launch": New offerings, features, services (signals innovation velocity, market direction)
- "partnership": Strategic alliances, collaborations (signals ecosystem positioning)
- "growth": Headcount expansion, revenue milestones, geographic expansion (signals scaling, hiring needs)

**OUTPUT FORMAT** (Reasoning First, Output Later):
```json
{
  "reasoning": {
    "sources_analyzed": ["url1", "url2", "url3"],
    "source_quality": {"url1": "high", "url2": "medium"},
    "missing_context": ["specific info you wish you had"],
    "assumptions": ["any assumptions made"],
    "confidence_level": "high|medium|low"
  },
  "summary": "2-3 sentence company overview emphasizing market position and strategic focus",
  "signals": [
    {
      "type": "funding",
      "description": "Exact fact from scraped content with specific metrics",
      "date": "YYYY-MM-DD or 'unknown'",
      "source": "URL where this fact was found",
      "business_context": "What this signal reveals about the company's trajectory"
    }
  ],
  "url": "primary company URL"
}
```

**BEST-EFFORT EXTRACTION**:
- Extract AT LEAST ONE signal if ANY factual information exists
- Even general facts ("operates in X industry", "serves Y market segment") count as "growth" signals
- Empty signals array only if content is completely non-informational

**SELF-EVALUATION**:
After generating your output, score it on:
- Clarity (1-10): Are signals specific and actionable?
- Accuracy (1-10): Are all facts directly from sources?
- Completeness (1-10): Did you extract all valuable signals?
If any score < 9, revise your output before finalizing.

NO TEXT OUTSIDE THE JSON OBJECT."""

ENHANCED_USER_PROMPT_TEMPLATE = """Analyze the following scraped content and extract company signals following the reasoning-first approach:

**COMPANY**: {company}

**CANDIDATE CONTEXT** (prioritize signals in these domains):
- Proven domains: .NET, Microservices, Team Leadership, Backend Architecture
- Proven outcomes: Team scaling, Performance optimization, System reliability

**SCRAPED CONTENT FROM MULTIPLE SOURCES**:
{scraped_content}

**YOUR TASK**:
1. First, fill in the "reasoning" block analyzing sources and gaps
2. Then extract signals with business context
3. Self-evaluate and revise if any dimension scores < 9

Output JSON only (with reasoning block first):"""


# ===== STATUS QUO PROMPTS (Current Implementation) =====

STATUS_QUO_SYSTEM_PROMPT = """You are a business intelligence analyst specializing in extracting structured company signals.

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

STATUS_QUO_USER_PROMPT_TEMPLATE = """Analyze the following scraped content and extract company signals:

COMPANY: {company}

SCRAPED CONTENT FROM MULTIPLE SOURCES:
{scraped_content}

Extract:
1. summary: 2-3 sentence overview of the company
2. signals: List of business signals with type, description, date, source
3. url: Primary company URL

JSON only - no additional text:"""


# ===== PYDANTIC SCHEMAS =====

class CompanySignalModel(BaseModel):
    """Pydantic model for company signal validation."""
    type: str = Field(..., description="Signal type")
    description: str = Field(..., min_length=1)
    date: str = Field(default="unknown")
    source: str = Field(..., min_length=1)
    business_context: str = Field(default="", description="What this signal reveals (enhanced only)")


class ReasoningBlock(BaseModel):
    """Enhanced: reasoning before output"""
    sources_analyzed: List[str] = Field(default_factory=list)
    source_quality: Dict[str, str] = Field(default_factory=dict)
    missing_context: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    confidence_level: str = Field(default="unknown")


class EnhancedCompanyResearchOutput(BaseModel):
    """Enhanced output with reasoning block"""
    reasoning: ReasoningBlock
    summary: str = Field(..., min_length=10)
    signals: List[CompanySignalModel] = Field(default_factory=list, max_length=10)
    url: str = Field(..., min_length=1)


class StatusQuoCompanyResearchOutput(BaseModel):
    """Status quo output (current implementation)"""
    summary: str = Field(..., min_length=10)
    signals: List[CompanySignalModel] = Field(default_factory=list, max_length=10)
    url: str = Field(..., min_length=1)


# ===== TEST RUNNER =====

class PromptComparisonTest:
    """Runs comparative test between status quo and enhanced prompts"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self.mongo_client = MongoClient(Config.MONGODB_URI)

    def fetch_job(self, job_id: str) -> Dict[str, Any]:
        """Fetch job from MongoDB"""
        db = self.mongo_client["jobs"]
        job = db["level-2"].find_one({"_id": ObjectId(job_id)})
        if not job:
            raise ValueError(f"Job {job_id} not found")
        return job

    def scrape_company_sources(self, company: str) -> Dict[str, Dict[str, str]]:
        """Scrape multiple sources for the company (limit to 2 sources for speed)"""
        import re

        # Construct official site URL
        clean_name = company.lower()
        clean_name = re.sub(r'\s+', '', clean_name)
        clean_name = re.sub(r'[^\w]', '', clean_name)
        clean_name = re.sub(r'(inc|llc|ltd|corp|corporation|company)$', '', clean_name)
        official_url = f"https://{clean_name}.com"

        scraped_data = {}

        # Source 1: Official site
        try:
            print(f"  Scraping official site: {official_url}")
            result = self.firecrawl.scrape(
                official_url,
                formats=['markdown'],
                only_main_content=True
            )
            if result and hasattr(result, 'markdown'):
                content = result.markdown[:2000] if result.markdown else None
                if content:
                    scraped_data["official_site"] = {
                        "url": official_url,
                        "content": content
                    }
                    print(f"    ✓ Scraped {len(content)} chars")
        except Exception as e:
            print(f"    ✗ Failed: {e}")

        # Source 2: LinkedIn (using search)
        try:
            print(f"  Searching LinkedIn for {company}")
            search_query = f"{company} LinkedIn company page"
            search_response = self.firecrawl.search(search_query, limit=2)

            # Extract results
            results = getattr(search_response, "web", None) or getattr(search_response, "data", None) or []

            linkedin_url = None
            for result in results:
                url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)
                if url and "linkedin.com/company" in url.lower():
                    linkedin_url = url
                    break

            if linkedin_url:
                print(f"    Found LinkedIn: {linkedin_url}")
                # Scrape it
                result = self.firecrawl.scrape(
                    linkedin_url,
                    formats=['markdown'],
                    only_main_content=True
                )
                if result and hasattr(result, 'markdown'):
                    content = result.markdown[:2000] if result.markdown else None
                    if content:
                        scraped_data["linkedin"] = {
                            "url": linkedin_url,
                            "content": content
                        }
                        print(f"    ✓ Scraped {len(content)} chars")
            else:
                print(f"    ✗ No LinkedIn URL found")

        except Exception as e:
            print(f"    ✗ LinkedIn search/scrape failed: {e}")

        return scraped_data

    def run_status_quo_prompt(self, company: str, scraped_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Run status quo prompt and return results"""
        # Build content sections
        content_sections = []
        for source_name, data in scraped_data.items():
            content_sections.append(
                f"=== SOURCE: {source_name} ({data['url']}) ===\n{data['content']}\n"
            )
        scraped_content = "\n".join(content_sections)

        # Call LLM
        messages = [
            SystemMessage(content=STATUS_QUO_SYSTEM_PROMPT),
            HumanMessage(
                content=STATUS_QUO_USER_PROMPT_TEMPLATE.format(
                    company=company,
                    scraped_content=scraped_content[:5000]
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
        validated = StatusQuoCompanyResearchOutput(**data)

        return {
            "raw_output": llm_output,
            "parsed": validated.model_dump(),
            "prompt_length": len(STATUS_QUO_SYSTEM_PROMPT) + len(messages[1].content)
        }

    def run_enhanced_prompt(self, company: str, scraped_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Run enhanced prompt and return results"""
        # Build content sections
        content_sections = []
        for source_name, data in scraped_data.items():
            content_sections.append(
                f"=== SOURCE: {source_name} ({data['url']}) ===\n{data['content']}\n"
            )
        scraped_content = "\n".join(content_sections)

        # Call LLM
        messages = [
            SystemMessage(content=ENHANCED_SYSTEM_PROMPT),
            HumanMessage(
                content=ENHANCED_USER_PROMPT_TEMPLATE.format(
                    company=company,
                    scraped_content=scraped_content[:5000]
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
        validated = EnhancedCompanyResearchOutput(**data)

        return {
            "raw_output": llm_output,
            "parsed": validated.model_dump(),
            "prompt_length": len(ENHANCED_SYSTEM_PROMPT) + len(messages[1].content)
        }

    def print_comparison(self, company: str, status_quo: Dict, enhanced: Dict):
        """Print side-by-side comparison"""
        print("\n" + "="*100)
        print("PROMPT COMPARISON RESULTS")
        print("="*100)
        print(f"\nCOMPANY: {company}")
        print("\n" + "-"*100)
        print("STATUS QUO PROMPT RESULTS")
        print("-"*100)

        sq_data = status_quo["parsed"]
        print(f"\nSummary:\n  {sq_data['summary']}\n")
        print(f"Signals ({len(sq_data['signals'])} found):")
        for idx, signal in enumerate(sq_data['signals'], 1):
            print(f"  {idx}. [{signal['type']}] {signal['description']}")
            print(f"     Date: {signal['date']}")
            print(f"     Source: {signal['source'][:80]}...")

        print(f"\nURL: {sq_data['url']}")
        print(f"Prompt Length: {status_quo['prompt_length']} chars")

        print("\n" + "-"*100)
        print("ENHANCED PROMPT RESULTS")
        print("-"*100)

        enh_data = enhanced["parsed"]

        # Show reasoning block
        print(f"\nREASONING BLOCK:")
        reasoning = enh_data['reasoning']
        print(f"  Sources Analyzed: {', '.join(reasoning['sources_analyzed']) if reasoning['sources_analyzed'] else 'None listed'}")
        print(f"  Source Quality: {reasoning['source_quality']}")
        print(f"  Missing Context: {reasoning['missing_context']}")
        print(f"  Assumptions: {reasoning['assumptions']}")
        print(f"  Confidence Level: {reasoning['confidence_level']}")

        print(f"\nSummary:\n  {enh_data['summary']}\n")
        print(f"Signals ({len(enh_data['signals'])} found):")
        for idx, signal in enumerate(enh_data['signals'], 1):
            print(f"  {idx}. [{signal['type']}] {signal['description']}")
            print(f"     Date: {signal['date']}")
            print(f"     Source: {signal['source'][:80]}...")
            if signal.get('business_context'):
                print(f"     Context: {signal['business_context']}")

        print(f"\nURL: {enh_data['url']}")
        print(f"Prompt Length: {enhanced['prompt_length']} chars")

        print("\n" + "="*100)
        print("ASSESSMENT")
        print("="*100)

        # Comparative metrics
        print(f"\nSignal Count:")
        print(f"  Status Quo: {len(sq_data['signals'])}")
        print(f"  Enhanced: {len(enh_data['signals'])}")

        print(f"\nSummary Length:")
        print(f"  Status Quo: {len(sq_data['summary'])} chars")
        print(f"  Enhanced: {len(enh_data['summary'])} chars")

        print(f"\nPrompt Complexity:")
        print(f"  Status Quo: {status_quo['prompt_length']} chars")
        print(f"  Enhanced: {enhanced['prompt_length']} chars (+{enhanced['prompt_length'] - status_quo['prompt_length']})")

        print(f"\nEnhanced Features:")
        print(f"  ✓ Reasoning block with source quality assessment")
        print(f"  ✓ Missing context identification")
        print(f"  ✓ Explicit assumptions tracking")
        print(f"  ✓ Confidence level reporting")
        print(f"  ✓ Business context per signal")
        print(f"  ✓ Self-evaluation loop")

        print("\n" + "="*100)

    def run_test(self, job_id: str):
        """Main test orchestration"""
        print("\n" + "="*100)
        print("LAYER 3 COMPANY RESEARCHER: PROMPT COMPARISON TEST")
        print("="*100)

        # 1. Fetch job
        print(f"\n1. Fetching job {job_id} from MongoDB...")
        job = self.fetch_job(job_id)
        company = job.get("company") or job.get("firm")
        print(f"   Company: {company}")
        print(f"   Role: {job.get('title')}")

        # 2. Scrape sources
        print(f"\n2. Scraping company sources (2 sources max for speed)...")
        scraped_data = self.scrape_company_sources(company)
        print(f"   Successfully scraped {len(scraped_data)} source(s)")

        if not scraped_data:
            print("   ERROR: No sources scraped. Cannot continue test.")
            return

        # 3. Run status quo prompt
        print(f"\n3. Running STATUS QUO prompt...")
        try:
            status_quo_results = self.run_status_quo_prompt(company, scraped_data)
            print(f"   ✓ Status quo prompt completed")
        except Exception as e:
            print(f"   ✗ Status quo prompt failed: {e}")
            status_quo_results = None

        # 4. Run enhanced prompt
        print(f"\n4. Running ENHANCED prompt...")
        try:
            enhanced_results = self.run_enhanced_prompt(company, scraped_data)
            print(f"   ✓ Enhanced prompt completed")
        except Exception as e:
            print(f"   ✗ Enhanced prompt failed: {e}")
            enhanced_results = None

        # 5. Compare and display
        if status_quo_results and enhanced_results:
            self.print_comparison(company, status_quo_results, enhanced_results)
        else:
            print("\n   ERROR: Cannot compare - one or both prompts failed")

        print("\n" + "="*100)
        print("TEST COMPLETE")
        print("="*100 + "\n")


# ===== MAIN =====

def main():
    """Run the comparison test"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    test = PromptComparisonTest()
    test.run_test("6929c97b45fa3c355f84ba2d")


if __name__ == "__main__":
    main()
