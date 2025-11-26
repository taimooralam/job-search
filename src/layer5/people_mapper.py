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
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from firecrawl import FirecrawlApp

from src.common.config import Config
from src.common.state import JobState


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

Your task: Generate hyper-personalized outreach citing specific achievements and metrics from the candidate's master CV or curated achievements.

**STRICT REQUIREMENTS (validation will reject non-compliant outputs):**
- LinkedIn messages: 150-550 characters (count carefully!)
- Email subjects: 5-10 words, ≤100 characters, MUST reference a pain point
  - Example (8 words): "Proven Experience Scaling Infrastructure for High-Growth SaaS"
  - Example (7 words): "Reducing Incidents 75% Through DevOps Transformation"
- Email body: 95-205 words (target 120-150 for safety)
  - Count words carefully! Aim for 3-4 short paragraphs
  - Include 1-2 concrete metrics from the candidate's experience
- Reference company signals or role context when available
- Be direct, technical, and metric-driven

**PHASE 9 CONTENT CONSTRAINTS (CRITICAL):**
- NO EMOJIS in any message (LinkedIn or email)
- NO GENERIC PLACEHOLDERS like "Contact's Name", "Director's Name", "[Company]", "[Date]"
  - If you don't have a real name, use specific role: "VP Engineering at [Company Name]"
- LinkedIn messages MUST end with: taimooralam@example.com | https://calendly.com/taimooralam/15min
- Email subject MUST be pain-focused (mention at least one pain point keyword)
- Keep professional, metric-driven tone
- ALWAYS use the actual contact name or role-based addressee (e.g., "VP Engineering at Stripe")"""

USER_PROMPT_OUTREACH_TEMPLATE = """Generate personalized outreach for this contact:

=== CONTACT ===
Name: {contact_name}
Role: {contact_role}
Why Relevant: {contact_why}
Recent Signals: {contact_signals}

=== JOB ===
Title: {job_title}
Company: {company}

Pain Points:
{pain_points}

Company Context:
{company_research_summary}

=== CANDIDATE EVIDENCE (Master CV or curated achievements) ===
{selected_stars_summary}

=== YOUR TASK ===
Generate outreach that:
1. References at least one concrete metric from the candidate's experience in the LinkedIn message
2. Addresses job pain points with concrete achievements grounded in supplied evidence
3. Shows awareness of company context (funding, growth, timing)
4. Personalizes to this contact's role and recent signals

**CRITICAL: Count words/characters carefully before outputting!**

Output JSON format:
{{
  "linkedin_message": "...",  // 150-550 chars, cite metric, use pain points + company research + fit analysis, MUST end with: I have applied for this role. Calendly: https://calendly.com/taimooralam/15min
  "subject": "...",           // 5-10 WORDS (count!), ≤100 chars, pain-focused
  "email_body": "..."         // 95-205 WORDS (count!), 3-4 paragraphs, cite 2-3 achievements using pain points/company context/fit analysis
}}

**VALIDATION CHECKLIST** (your output will be rejected if these fail):
- ✓ LinkedIn message: 150-550 characters AND ends with contact info
- ✓ Email subject: 5-10 words AND references a pain point keyword
- ✓ Email body: 95-205 words AND cites specific metrics
- ✓ NO generic placeholders (use actual name or "VP Engineering at {company}")
- ✓ NO emojis anywhere"""


class PeopleMapper:
    """
    Phase 7: Enhanced People Mapper with multi-source discovery and classification.
    """

    def __init__(self):
        """Initialize LLM and FireCrawl."""
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=0.4,  # Slightly creative for outreach
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )

        # FireCrawl for contact discovery (disabled by default via config)
        self.firecrawl_disabled = Config.DISABLE_FIRECRAWL_OUTREACH or not Config.FIRECRAWL_API_KEY
        self.firecrawl = None
        if not self.firecrawl_disabled:
            self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

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
            # Try common team page paths
            team_urls = [
                f"{company_url}/team",
                f"{company_url}/about",
                f"{company_url}/about-us",
                f"{company_url}/leadership",
                f"{company_url}/company"
            ]

            for url in team_urls:
                try:
                    result = self.firecrawl.scrape_url(
                        url,
                        params={'formats': ['markdown'], 'onlyMainContent': True}
                    )
                    if result and hasattr(result, 'markdown'):
                        # Limit to 2000 chars
                        return result.markdown[:2000]
                except:
                    continue

            return None

        except Exception as e:
            print(f"  ⚠️  Team page scraping failed: {e}")
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
            # Run multiple targeted queries in parallel
            queries = [
                QUERY_TEMPLATES["recruiters"].format(company=company, department=department),
                QUERY_TEMPLATES["recruiters_alt"].format(company=company),
                QUERY_TEMPLATES["leadership"].format(company=company, department=department),
            ]

            if title:
                queries.append(QUERY_TEMPLATES["hiring_manager"].format(company=company, title=title))

            for query in queries:
                try:
                    print(f"[FireCrawl][PeopleMapper] LinkedIn query: {query}")
                    search_response = self.firecrawl.search(query, limit=5)

                    # Use normalizer to extract results (handles SDK version differences)
                    results = _extract_search_results(search_response)

                    # Extract contacts from metadata
                    for result in results:
                        contact = self._extract_contact_from_search_result(result, company)
                        if contact:
                            contacts.append(contact)
                            print(f"    ✓ Found: {contact['name']} - {contact['role']}")

                except Exception as e:
                    print(f"    ⚠️  Query failed: {e}")
                    continue

            print(f"  ✓ Found {len(contacts)} contacts from LinkedIn search")
            return contacts

        except Exception as e:
            print(f"  ⚠️  LinkedIn search failed: {e}")
            return []

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
            print(f"[FireCrawl][PeopleMapper] Hiring manager query: {query}")

            search_response = self.firecrawl.search(query, limit=5)
            results = _extract_search_results(search_response)

            # Extract contacts from metadata
            for result in results:
                contact = self._extract_contact_from_search_result(result, company)
                if contact:
                    contacts.append(contact)
                    print(f"    ✓ Found: {contact['name']} - {contact['role']}")

            print(f"  ✓ Found {len(contacts)} senior contacts")
            return contacts

        except Exception as e:
            print(f"  ⚠️  Hiring manager search failed: {e}")
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
            print(f"[FireCrawl][PeopleMapper] Crunchbase search query: {query}")
            search_response = self.firecrawl.search(query, limit=2)

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
            print(f"  ⚠️  Crunchbase team search failed: {e}")
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
        company_url = (state.get("company_research") or {}).get("url") or f"https://linkedin.com/company/{company.lower().replace(' ', '-')}"

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
                "recent_signals": []
            })

        secondary_contacts = []
        for template in secondary_templates:
            secondary_contacts.append({
                "name": f"{template['role']} at {company}",
                "role": template["role"],
                "linkedin_url": f"{company_url}/people",
                "why_relevant": template["why"],
                "recent_signals": []
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
            print("  🔌 FireCrawl outreach discovery disabled (role-based contacts only).")
            return "FireCrawl discovery is disabled. Use role-based identifiers.", False

        company = state.get("company", "")
        title = state.get("title", "")
        company_url = state.get("company_research", {}).get("url", "")

        all_contacts = []
        raw_content_parts = []

        print("  🔍 Discovering contacts from multiple sources (Option A - improved)...")

        # Source 1: Company team page (legacy - still useful for smaller companies)
        team_page = self._scrape_company_team_page(company, company_url)
        if team_page:
            raw_content_parts.append(f"[SOURCE: Company Team Page]\n{team_page}\n")
            print(f"    ✓ Scraped company team page ({len(team_page)} chars)")

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
            print(f"    ✓ Searched Crunchbase team ({len(crunchbase_content)} chars)")

        # Deduplicate contacts
        if all_contacts:
            all_contacts = self._deduplicate_contacts(all_contacts)
            print(f"  ✓ Total unique contacts found: {len(all_contacts)}")

        if not raw_content_parts:
            print("    ⚠️  No contacts found via FireCrawl (will use role-based fallback)")
            return f"No specific contacts found. Use role-based identifiers for {company}.", False

        return "\n---\n".join(raw_content_parts), True

    # ===== LLM CLASSIFICATION AND ENRICHMENT =====

    def _format_company_research_summary(self, company_research: Optional[Dict]) -> str:
        """Format company research for prompt."""
        if not company_research:
            return "No company research available."

        parts = [company_research.get("summary", "")]

        # Add key signals
        signals = company_research.get("signals", [])
        if signals:
            signal_texts = [f"- {s['description']} ({s['date']})" for s in signals[:3]]
            parts.append("Recent signals:\n" + "\n".join(signal_texts))

        return "\n".join(parts)

    def _format_role_research_summary(self, role_research: Optional[Dict]) -> str:
        """Format role research for prompt."""
        if not role_research:
            return "No role research available."

        parts = [role_research.get("summary", "")]

        # Add why_now
        why_now = role_research.get("why_now", "")
        if why_now:
            parts.append(f"Why Now: {why_now}")

        return "\n".join(parts)

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
            print(f"   ⚠️  Fallback cover letter generation failed: {e}")
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
        Validate that LinkedIn message ends with required contact info (Phase 9).

        Args:
            message: LinkedIn message

        Raises:
            ValueError: If closing line is missing
        """
        required_phrase = "calendly.com/taimooralam/15min"

        if required_phrase not in message.lower() or "applied" not in message.lower():
            raise ValueError(
                "LinkedIn message must state you have applied and include Calendly only "
                "(no email): I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"
            )

    def _validate_linkedin_message(self, message: str) -> str:
        """Validate and trim LinkedIn message to ≤550 chars (Phase 9)."""
        if len(message) <= 550:
            return message
        # Trim to 550 and end at last complete sentence
        trimmed = message[:547]
        last_period = trimmed.rfind('.')
        if last_period > 400:
            return trimmed[:last_period + 1]
        return trimmed + "..."

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
        Generate OutreachPackage for one contact (Phase 7.2.4).

        Args:
            contact: Contact dict with name, role, why_relevant, recent_signals
            state: JobState with job/STAR context

        Returns:
            Dict with linkedin_message, email_subject, email_body
        """
        # Format contact signals
        signals_text = ", ".join(contact.get("recent_signals", [])) if contact.get("recent_signals") else "None"

        # Build prompt
        messages = [
            SystemMessage(content=SYSTEM_PROMPT_OUTREACH),
            HumanMessage(content=USER_PROMPT_OUTREACH_TEMPLATE.format(
                contact_name=contact["name"],
                contact_role=contact["role"],
                contact_why=contact["why_relevant"],
                contact_signals=signals_text,
                job_title=state.get("title", ""),
                company=state.get("company", ""),
                pain_points=self._format_pain_points(state.get("pain_points", [])),
                company_research_summary=self._format_company_research_summary(state.get("company_research")),
                selected_stars_summary=self._format_stars_summary(
                    state.get("selected_stars", []),
                    state.get("candidate_profile", "")
                )
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

            # Get raw content
            linkedin_msg_raw = data.get("linkedin_message", "")
            email_subject_raw = data.get("subject", "")
            email_body_raw = data.get("email_body", "")

            # Validate Phase 9 content constraints (emojis, placeholders)
            self._validate_content_constraints(linkedin_msg_raw, "linkedin")
            self._validate_content_constraints(email_body_raw, "email")

            # Validate LinkedIn closing line (Phase 9)
            self._validate_linkedin_closing(linkedin_msg_raw)

            # Validate Phase 9 ROADMAP word count requirements
            pain_points = state.get("pain_points", [])
            validated_subject = self._validate_email_subject_words(email_subject_raw, pain_points)
            validated_body = self._validate_email_body_length(email_body_raw)

            # Validate and trim lengths
            linkedin_msg = self._validate_linkedin_message(linkedin_msg_raw)
            email_subject = self._validate_email_subject(validated_subject)
            email_body = validated_body

            return {
                "contact_name": contact["name"],
                "contact_role": contact["role"],
                "linkedin_url": contact["linkedin_url"],
                "linkedin_message": linkedin_msg,
                "email_subject": email_subject,
                "email_body": email_body,
                "why_relevant": contact["why_relevant"],
                "recent_signals": contact.get("recent_signals", []),
                "reasoning": f"Personalized for {contact['role']} role"
            }

        except Exception as e:
            # Fallback: generate minimal outreach
            print(f"  ⚠️  Outreach generation failed for {contact['name']}: {e}")
            return {
                "contact_name": contact["name"],
                "contact_role": contact["role"],
                "linkedin_url": contact["linkedin_url"],
                "linkedin_message": f"Interested in {state.get('title', 'role')} at {state.get('company', '')}",
                "email_subject": f"Interest in {state.get('title', 'Role')}",
                "email_body": "Generic fallback message",
                "why_relevant": contact["why_relevant"],
                "recent_signals": contact.get("recent_signals", []),
                "reasoning": "Fallback due to generation error"
            }

    # ===== MAIN MAPPER FUNCTION =====

    def map_people(self, state: JobState) -> Dict[str, Any]:
        """
        Layer 5: People Mapper (Phase 7).

        1. Multi-source contact discovery via FireCrawl (skipped when DISABLE_FIRECRAWL_OUTREACH is true)
        2. LLM-based classification into primary/secondary
        3. OutreachPackage generation for each contact
        4. Quality gates: 4-6 primary, 4-6 secondary

        Returns:
            Dict with primary_contacts, secondary_contacts, outreach_packages
        """
        print(f"\n{'='*80}")
        print(f"LAYER 5: PEOPLE MAPPER (Phase 7)")
        print(f"{'='*80}")
        if self.firecrawl_disabled:
            print("  🔌 FireCrawl outreach scraping disabled via Config.DISABLE_FIRECRAWL_OUTREACH (role-based contacts only).")

        try:
            # Step 1: Multi-source discovery
            if self.firecrawl_disabled:
                raw_contacts, found_contacts = (
                    "FireCrawl discovery is disabled. Use role-based identifiers.",
                    False
                )
            else:
                raw_contacts, found_contacts = self._discover_contacts(state)

            if not found_contacts:
                fallback_reason = (
                    "FireCrawl outreach discovery disabled (role-based synthetic contacts)."
                    if self.firecrawl_disabled
                    else "No contacts found via FireCrawl - using role-based synthetic contacts."
                )
                print(f"\n  ⚠️  {fallback_reason}")
                synthetic = self._generate_synthetic_contacts(state)
                primary_contacts = synthetic["primary_contacts"]
                secondary_contacts = synthetic["secondary_contacts"]
                print(f"    ✓ Generated {len(primary_contacts)} synthetic primary contacts")
                print(f"    ✓ Generated {len(secondary_contacts)} synthetic secondary contacts")

                # Also generate fallback cover letters for reference
                fallback_letters = self._generate_fallback_cover_letters(state, fallback_reason)

                # Generate outreach for synthetic contacts
                print("\n  📧 Generating personalized outreach for synthetic contacts...")
                all_contacts = primary_contacts + secondary_contacts
                enriched_primary = []
                enriched_secondary = []

                for i, contact in enumerate(all_contacts, 1):
                    print(f"    Generating outreach {i}/{len(all_contacts)}: {contact['name']}")
                    try:
                        outreach = self._generate_outreach_package(contact, state)
                        enriched_contact = {**contact, **outreach}
                        if i <= len(primary_contacts):
                            enriched_primary.append(enriched_contact)
                        else:
                            enriched_secondary.append(enriched_contact)
                    except Exception as e:
                        print(f"      ⚠️  Failed to generate outreach: {e}")
                        if i <= len(primary_contacts):
                            enriched_primary.append(contact)
                        else:
                            enriched_secondary.append(contact)

                print(f"\n  ✅ Completed synthetic contact outreach generation")

                return {
                    "primary_contacts": enriched_primary,
                    "secondary_contacts": enriched_secondary,
                    "people": enriched_primary + enriched_secondary,
                    "outreach_packages": [],  # Future: structured packages
                    "fallback_cover_letters": fallback_letters
                }

            # Step 2: Classify contacts
            print("\n  🏷️  Classifying contacts into primary/secondary...")
            classified = self._classify_contacts(raw_contacts, state)

            primary_contacts = classified["primary_contacts"]
            secondary_contacts = classified["secondary_contacts"]

            print(f"    ✓ {len(primary_contacts)} primary contacts (hiring-related)")
            print(f"    ✓ {len(secondary_contacts)} secondary contacts (cross-functional)")

            # Step 3: Generate outreach for all contacts
            print("\n  📧 Generating personalized outreach...")

            all_contacts = primary_contacts + secondary_contacts
            enriched_primary = []
            enriched_secondary = []

            for i, contact in enumerate(all_contacts, 1):
                print(f"    Generating outreach {i}/{len(all_contacts)}: {contact['name']}")

                try:
                    outreach = self._generate_outreach_package(contact, state)

                    # Merge contact + outreach
                    enriched_contact = {**contact, **outreach}

                    # Add to appropriate bucket
                    if i <= len(primary_contacts):
                        enriched_primary.append(enriched_contact)
                    else:
                        enriched_secondary.append(enriched_contact)

                except Exception as e:
                    print(f"      ⚠️  Failed to generate outreach: {e}")
                    # Add contact without outreach
                    if i <= len(primary_contacts):
                        enriched_primary.append(contact)
                    else:
                        enriched_secondary.append(contact)

            print(f"\n  ✅ Generated outreach for {len(enriched_primary + enriched_secondary)} contacts")

            # Step 4: Return updates
            return {
                "primary_contacts": enriched_primary,
                "secondary_contacts": enriched_secondary,
                "people": enriched_primary + enriched_secondary,  # Legacy field
                "outreach_packages": None,  # Future: per-contact packages
                "fallback_cover_letters": []
            }

        except Exception as e:
            print(f"\n  ❌ People mapping failed: {e}")
            return {
                "primary_contacts": [],
                "secondary_contacts": [],
                "people": [],
                "outreach_packages": [],
                "fallback_cover_letters": [],
                "errors": state.get("errors", []) + [f"People mapping error: {str(e)}"]
            }


# ===== NODE FUNCTION =====

def people_mapper_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 5 (Phase 7).

    Args:
        state: Current job state

    Returns:
        State updates with primary_contacts, secondary_contacts, outreach_packages
    """
    mapper = PeopleMapper()
    return mapper.map_people(state)
