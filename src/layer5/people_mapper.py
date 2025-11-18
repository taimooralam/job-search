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
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from firecrawl import FirecrawlApp

from src.common.config import Config
from src.common.state import JobState


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

Your task: Generate hyper-personalized outreach citing specific achievements and metrics.

**REQUIREMENTS:**
- LinkedIn messages: 150-550 characters (Phase 9 constraint)
- Email subjects: ≤100 characters
- Cite specific STAR metrics (e.g., "75% incident reduction", "24x faster deployments")
- Reference company signals or role context when available
- Be direct, technical, and metric-driven"""

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

=== CANDIDATE'S TOP ACHIEVEMENTS ===
{selected_stars_summary}

=== YOUR TASK ===
Generate outreach that:
1. References ONE specific STAR metric in LinkedIn message
2. Addresses job pain points with concrete achievements
3. Shows awareness of company context (funding, growth, timing)
4. Personalizes to this contact's role and recent signals

Output JSON format:
{{
  "linkedin_message": "...",  // 150-550 chars, cite metric
  "subject": "...",           // ≤100 chars
  "email_body": "..."         // 3-4 short paragraphs, cite 2-3 achievements
}}"""


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

        # FireCrawl for contact discovery
        self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

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
    def _search_linkedin_contacts(self, company: str, department: str = "engineering") -> Optional[str]:
        """
        Search LinkedIn for company employees using FireCrawl search.

        Args:
            company: Company name
            department: Department to search (e.g., "engineering", "product")

        Returns:
            Markdown content from LinkedIn search results
        """
        try:
            query = f'{company} LinkedIn team {department}'
            search_response = self.firecrawl.search(query, limit=2)

            if search_response and search_response.data:
                # Find LinkedIn URL
                for result in search_response.data:
                    if hasattr(result, 'url') and 'linkedin.com' in result.url.lower():
                        # Return markdown content
                        if hasattr(result, 'markdown'):
                            return result.markdown[:1500]

            return None

        except Exception as e:
            print(f"  ⚠️  LinkedIn search failed: {e}")
            return None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _search_hiring_manager(self, company: str, title: str) -> Optional[str]:
        """
        Search for hiring manager using job title + company.

        Args:
            company: Company name
            title: Job title

        Returns:
            Markdown content about hiring manager
        """
        try:
            query = f'{company} {title} hiring manager'
            search_response = self.firecrawl.search(query, limit=2)

            if search_response and search_response.data:
                # Return first result
                if hasattr(search_response.data[0], 'markdown'):
                    return search_response.data[0].markdown[:1000]

            return None

        except Exception as e:
            print(f"  ⚠️  Hiring manager search failed: {e}")
            return None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _search_crunchbase_team(self, company: str) -> Optional[str]:
        """
        Search Crunchbase for company team information using FireCrawl search.

        Args:
            company: Company name

        Returns:
            Markdown content from Crunchbase team page
        """
        try:
            query = f'{company} Crunchbase team'
            search_response = self.firecrawl.search(query, limit=2)

            if search_response and search_response.data:
                # Find Crunchbase URL
                for result in search_response.data:
                    if hasattr(result, 'url') and 'crunchbase.com' in result.url.lower():
                        # Return markdown content
                        if hasattr(result, 'markdown'):
                            return result.markdown[:1500]

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

    def _discover_contacts(self, state: JobState) -> str:
        """
        Multi-source contact discovery using FireCrawl (Phase 7.2.2).

        Queries:
        1. Company team/about page
        2. LinkedIn team search
        3. Hiring manager search
        4. Crunchbase team

        Returns:
            Formatted string of raw contact snippets for LLM
        """
        company = state.get("company", "")
        title = state.get("title", "")
        company_url = state.get("company_research", {}).get("url", "")

        raw_content_parts = []

        print("  🔍 Discovering contacts from multiple sources...")

        # Source 1: Company team page
        team_page = self._scrape_company_team_page(company, company_url)
        if team_page:
            raw_content_parts.append(f"[SOURCE: Company Team Page]\n{team_page}\n")
            print(f"    ✓ Scraped company team page ({len(team_page)} chars)")

        # Source 2: LinkedIn
        linkedin_content = self._search_linkedin_contacts(company, "engineering")
        if linkedin_content:
            raw_content_parts.append(f"[SOURCE: LinkedIn]\n{linkedin_content}\n")
            print(f"    ✓ Searched LinkedIn ({len(linkedin_content)} chars)")

        # Source 3: Hiring manager
        manager_content = self._search_hiring_manager(company, title)
        if manager_content:
            raw_content_parts.append(f"[SOURCE: Hiring Manager Search]\n{manager_content}\n")
            print(f"    ✓ Searched for hiring manager ({len(manager_content)} chars)")

        # Source 4: Crunchbase team
        crunchbase_content = self._search_crunchbase_team(company)
        if crunchbase_content:
            raw_content_parts.append(f"[SOURCE: Crunchbase Team]\n{crunchbase_content}\n")
            print(f"    ✓ Searched Crunchbase team ({len(crunchbase_content)} chars)")

        if not raw_content_parts:
            print("    ⚠️  No contacts found via FireCrawl (will use role-based fallback)")
            return f"No specific contacts found. Use role-based identifiers for {company}."

        return "\n---\n".join(raw_content_parts)

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

    def _format_stars_summary(self, stars: List[Dict]) -> str:
        """Format STAR records for outreach context."""
        if not stars:
            return "No STAR records available."

        summaries = []
        for i, star in enumerate(stars[:3], 1):
            summary = f"""Achievement #{i}: {star.get('role', 'Role')} at {star.get('company', 'Company')}
Domain: {star.get('domain_areas', 'N/A')}
Results: {star.get('results', 'N/A')[:200]}
Metrics: {star.get('metrics', 'N/A')}""".strip()
            summaries.append(summary)

        return "\n\n".join(summaries)

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
                selected_stars_summary=self._format_stars_summary(state.get("selected_stars", []))
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

            # Validate lengths
            linkedin_msg = self._validate_linkedin_message(data.get("linkedin_message", ""))
            email_subject = self._validate_email_subject(data.get("subject", ""))
            email_body = data.get("email_body", "")

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

        1. Multi-source contact discovery via FireCrawl
        2. LLM-based classification into primary/secondary
        3. OutreachPackage generation for each contact
        4. Quality gates: 4-6 primary, 4-6 secondary

        Returns:
            Dict with primary_contacts, secondary_contacts, outreach_packages
        """
        print(f"\n{'='*80}")
        print(f"LAYER 5: PEOPLE MAPPER (Phase 7)")
        print(f"{'='*80}")

        try:
            # Step 1: Multi-source discovery
            raw_contacts = self._discover_contacts(state)

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
                "outreach_packages": None  # Future: per-contact packages
            }

        except Exception as e:
            print(f"\n  ❌ People mapping failed: {e}")
            return {
                "primary_contacts": [],
                "secondary_contacts": [],
                "people": [],
                "outreach_packages": [],
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
