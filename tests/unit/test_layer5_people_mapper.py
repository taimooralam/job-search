"""
Unit Tests for Layer 5: People Mapper (Phase 7)

Tests Phase 7 deliverables:
- Primary vs secondary contact separation
- Multi-source FireCrawl contact discovery
- JSON-only output with Pydantic validation
- Role-based fallback for missing names
- OutreachPackage generation with length constraints
- Quality gates: 4-6 primary, 4-6 secondary contacts
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from pydantic import ValidationError

from src.layer5.people_mapper import (
    PeopleMapper,
    people_mapper_node,
    ContactModel,
    PeopleMapperOutput
)


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState with full pipeline context."""
    return {
        "job_id": "test_001",
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable systems for 10M users. Required: Python, AWS, Kubernetes. Report to VP Engineering.",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "pain_points": [
            "Legacy monolith causing 40% of incidents",
            "Manual deployment process taking 3 hours per release"
        ],
        "strategic_needs": [
            "Migrate to microservices architecture",
            "Implement CI/CD automation"
        ],
        "selected_stars": [
            {
                "id": "1",
                "company": "AdTech Inc",
                "role": "Senior SRE",
                "metrics": "75% incident reduction, 24x faster deployments"
            }
        ],
        "company_research": {
            "summary": "TechCorp is a Series B SaaS platform with 10M users.",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $50M Series B",
                    "date": "2024-06-15",
                    "source": "https://techcorp.com/news"
                }
            ],
            "url": "https://techcorp.com"
        },
        "role_research": {
            "summary": "Senior engineer will lead platform team of 5.",
            "business_impact": [
                "Enable 10x user growth",
                "Reduce infrastructure costs by 30%"
            ],
            "why_now": "Recent $50M funding requires scaling infrastructure"
        },
        "errors": [],
        "status": "processing"
    }


@pytest.fixture
def firecrawl_team_page_result():
    """Mock FireCrawl result for team/leadership page."""
    return MagicMock(
        markdown="""
        # Leadership Team

        **Sarah Chen** - VP Engineering
        Leading our 50-person engineering team. Previously scaled infrastructure at Meta.

        **John Smith** - Director of Platform
        Owns core platform and infrastructure. 10+ years at Google Cloud.

        **Emily Rodriguez** - Head of Talent
        Building world-class engineering teams.
        """,
        url="https://techcorp.com/team"
    )


@pytest.fixture
def firecrawl_linkedin_result():
    """Mock FireCrawl LinkedIn search result."""
    return MagicMock(
        markdown="""
        TechCorp Employees on LinkedIn:
        - Sarah Chen, VP Engineering at TechCorp
        - John Smith, Director of Platform at TechCorp
        - Michael Lee, Senior Engineering Manager at TechCorp
        """,
        url="https://www.linkedin.com/company/techcorp/people"
    )


# ===== TESTS: Pydantic Schema Validation =====

class TestPydanticModels:
    """Test ContactModel and PeopleMapperOutput schemas."""

    def test_contact_model_valid(self):
        """ContactModel accepts valid contact data."""
        contact = ContactModel(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Direct hiring manager for platform team",
            recent_signals=["Recently posted about hiring engineers", "Shared infrastructure modernization article"]
        )

        assert contact.name == "Sarah Chen"
        assert contact.role == "VP Engineering"
        assert len(contact.recent_signals) == 2

    def test_contact_model_requires_name_and_role(self):
        """ContactModel fails without required fields."""
        with pytest.raises(ValidationError):
            ContactModel(
                linkedin_url="https://linkedin.com/in/someone",
                why_relevant="Relevant person"
            )

    def test_people_mapper_output_valid(self):
        """PeopleMapperOutput validates correct structure."""
        output = PeopleMapperOutput(
            primary_contacts=[
                ContactModel(name=f"Primary {i}", role=f"Role {i}", linkedin_url=f"https://li.com/p{i}", why_relevant=f"Primary contact {i} is directly involved in hiring for this position", recent_signals=[])
                for i in range(4)
            ],
            secondary_contacts=[
                ContactModel(name=f"Secondary {i}", role=f"Role {i}", linkedin_url=f"https://li.com/s{i}", why_relevant=f"Secondary contact {i} is a cross-functional stakeholder", recent_signals=[])
                for i in range(4)
            ]
        )

        assert len(output.primary_contacts) == 4
        assert len(output.secondary_contacts) == 4

    def test_people_mapper_output_enforces_min_contacts(self):
        """PeopleMapperOutput requires minimum contacts (quality gate)."""
        # Should fail with <4 primary contacts
        with pytest.raises(ValidationError) as exc_info:
            PeopleMapperOutput(
                primary_contacts=[
                    ContactModel(
                        name="Person 1",
                        role="Role 1",
                        linkedin_url="https://linkedin.com/in/person1",
                        why_relevant="This is a detailed reason for why this person is relevant to the role",
                        recent_signals=[]
                    )
                ],
                secondary_contacts=[
                    ContactModel(name=f"Sec {i}", role=f"Role {i}", linkedin_url=f"https://li.com/{i}", why_relevant=f"Secondary contact {i} with relevant background in technology", recent_signals=[])
                    for i in range(4)
                ]
            )

        assert "primary_contacts" in str(exc_info.value)
        assert "at least 4" in str(exc_info.value).lower()

    def test_people_mapper_output_enforces_max_contacts(self):
        """PeopleMapperOutput enforces maximum contacts (quality gate)."""
        # Should fail with >6 primary contacts
        too_many_contacts = [
            ContactModel(
                name=f"Person {i}",
                role=f"Role {i}",
                linkedin_url=f"https://linkedin.com/in/person{i}",
                why_relevant=f"This person {i} is relevant because they have experience in the domain",
                recent_signals=[]
            )
            for i in range(7)
        ]

        with pytest.raises(ValidationError) as exc_info:
            PeopleMapperOutput(
                primary_contacts=too_many_contacts,
                secondary_contacts=[
                    ContactModel(name=f"Sec {i}", role=f"Role {i}", linkedin_url=f"https://li.com/{i}", why_relevant=f"Secondary contact {i} with relevant background", recent_signals=[])
                    for i in range(4)
                ]
            )

        assert "primary_contacts" in str(exc_info.value)
        assert "at most 6" in str(exc_info.value).lower()


# ===== TESTS: FireCrawl Multi-Source Discovery =====

class TestFireCrawlContactDiscovery:
    """Test multi-source FireCrawl contact discovery."""

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', False)
    @patch('src.layer5.people_mapper.Config.FIRECRAWL_API_KEY', 'test_key')
    @patch('src.layer5.people_mapper.FirecrawlApp')
    def test_searches_company_team_page(self, mock_firecrawl_class, sample_job_state, firecrawl_team_page_result):
        """Scrapes company team/about page for contacts."""
        mock_firecrawl = MagicMock()
        mock_firecrawl.scrape_url.return_value = firecrawl_team_page_result
        mock_firecrawl_class.return_value = mock_firecrawl

        mapper = PeopleMapper()
        raw_contacts = mapper._scrape_company_team_page(
            company="TechCorp",
            company_url="https://techcorp.com"
        )

        # Should have scraped team page
        assert mock_firecrawl.scrape_url.called
        assert raw_contacts is not None
        assert "Sarah Chen" in raw_contacts or "VP Engineering" in raw_contacts

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', False)
    @patch('src.layer5.people_mapper.Config.FIRECRAWL_API_KEY', 'test_key')
    @patch('src.layer5.people_mapper.FirecrawlApp')
    def test_searches_linkedin_with_firecrawl(self, mock_firecrawl_class, sample_job_state):
        """Uses FireCrawl search to find LinkedIn profiles (Option A - metadata extraction)."""
        mock_firecrawl = MagicMock()
        mock_search_response = MagicMock()

        # Mock search results with realistic LinkedIn profile metadata
        mock_linkedin_result = MagicMock()
        mock_linkedin_result.url = "https://www.linkedin.com/in/sarahchen"
        mock_linkedin_result.title = "Sarah Chen - VP Engineering at TechCorp"
        mock_linkedin_result.description = "VP Engineering at TechCorp · Experience: TechCorp · Location: San Francisco"

        # Support both old and new SDK formats
        mock_search_response.web = [mock_linkedin_result]
        mock_search_response.data = [mock_linkedin_result]
        mock_firecrawl.search.return_value = mock_search_response
        mock_firecrawl_class.return_value = mock_firecrawl

        mapper = PeopleMapper()
        contacts = mapper._search_linkedin_contacts(
            company="TechCorp",
            department="engineering"
        )

        # Should have searched for LinkedIn with SEO-style queries
        mock_firecrawl.search.assert_called()
        call_args = mock_firecrawl.search.call_args[0][0]
        assert "TechCorp" in call_args
        assert "site:linkedin.com/in" in call_args or "LinkedIn" in call_args

        # Should return list of contact dicts (Option A improvement)
        assert isinstance(contacts, list)
        if contacts:  # If extraction succeeded
            assert "name" in contacts[0]
            assert "role" in contacts[0]
            assert "linkedin_url" in contacts[0]

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', False)
    @patch('src.layer5.people_mapper.Config.FIRECRAWL_API_KEY', 'test_key')
    @patch('src.layer5.people_mapper.FirecrawlApp')
    def test_searches_for_hiring_manager(self, mock_firecrawl_class, sample_job_state):
        """Searches for hiring manager using title + company (Option A - metadata extraction)."""
        mock_firecrawl = MagicMock()
        mock_search_response = MagicMock()

        # Mock senior leadership search result
        mock_leader_result = MagicMock()
        mock_leader_result.url = "https://www.linkedin.com/in/johnsmith"
        mock_leader_result.title = "John Smith - CTO at TechCorp"
        mock_leader_result.description = "Chief Technology Officer at TechCorp"

        # Support both old and new SDK formats
        mock_search_response.web = [mock_leader_result]
        mock_search_response.data = [mock_leader_result]
        mock_firecrawl.search.return_value = mock_search_response
        mock_firecrawl_class.return_value = mock_firecrawl

        mapper = PeopleMapper()
        contacts = mapper._search_hiring_manager(
            company="TechCorp",
            title="Senior Software Engineer"
        )

        # Should search for senior leadership with SEO-style query
        mock_firecrawl.search.assert_called()
        call_args = mock_firecrawl.search.call_args[0][0]
        assert "TechCorp" in call_args
        assert "CTO" in call_args or "VP Engineering" in call_args or "LinkedIn" in call_args

        # Should return list of contact dicts (Option A improvement)
        assert isinstance(contacts, list)

    @patch('src.layer5.people_mapper.FirecrawlApp')
    def test_deduplicates_contacts_across_sources(self, mock_firecrawl_class, sample_job_state):
        """Deduplicates same person found in multiple sources."""
        # Mock multiple sources returning same person
        mapper = PeopleMapper()

        raw_contacts = [
            {"name": "Sarah Chen", "role": "VP Engineering", "source": "team_page"},
            {"name": "Sarah Chen", "role": "VP Engineering", "source": "linkedin"},
            {"name": "John Smith", "role": "Director", "source": "team_page"}
        ]

        deduplicated = mapper._deduplicate_contacts(raw_contacts)

        # Should have 2 unique people (Sarah Chen once, John Smith once)
        assert len(deduplicated) == 2
        names = [c["name"] for c in deduplicated]
        assert names.count("Sarah Chen") == 1
        assert names.count("John Smith") == 1

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', False)
    @patch('src.layer5.people_mapper.Config.FIRECRAWL_API_KEY', 'test_key')
    @patch('src.layer5.people_mapper.FirecrawlApp')
    def test_searches_crunchbase_team(self, mock_firecrawl_class, sample_job_state):
        """Uses FireCrawl search to find Crunchbase team page."""
        mock_firecrawl = MagicMock()
        mock_search_response = MagicMock()
        crunchbase_result = MagicMock()
        crunchbase_result.url = "https://www.crunchbase.com/organization/techcorp/people"
        crunchbase_result.markdown = """
        TechCorp Leadership Team on Crunchbase:
        - Sarah Chen, VP Engineering
        - Michael Torres, CTO
        - Jennifer Liu, Head of Product
        - David Kim, Director of Engineering
        """
        # Support both old and new SDK formats
        mock_search_response.web = [crunchbase_result]
        mock_search_response.data = [crunchbase_result]
        mock_firecrawl.search.return_value = mock_search_response
        mock_firecrawl_class.return_value = mock_firecrawl

        mapper = PeopleMapper()
        raw_contacts = mapper._search_crunchbase_team(company="TechCorp")

        # Should have searched for Crunchbase
        mock_firecrawl.search.assert_called()
        call_args = mock_firecrawl.search.call_args[0][0]
        assert "TechCorp" in call_args
        assert "Crunchbase" in call_args or "crunchbase" in call_args.lower()

        # Should return markdown content
        assert raw_contacts is not None
        assert "Sarah Chen" in raw_contacts or "Leadership" in raw_contacts


# ===== TESTS: LLM Classification and Enrichment =====

class TestLLMContactClassification:
    """Test LLM-based contact classification into primary/secondary."""

    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_classifies_into_primary_and_secondary(self, mock_llm_class, sample_job_state):
        """LLM classifies contacts into primary vs secondary buckets."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "primary_contacts": [
                {
                    "name": "Sarah Chen",
                    "role": "VP Engineering",
                    "linkedin_url": "https://linkedin.com/in/sarahchen",
                    "why_relevant": "Direct hiring manager for platform team",
                    "recent_signals": ["Posted about hiring"]
                },
                {
                    "name": "John Smith",
                    "role": "Director of Platform",
                    "linkedin_url": "https://linkedin.com/in/johnsmith",
                    "why_relevant": "Technical decision maker for infrastructure",
                    "recent_signals": []
                },
                {
                    "name": "Emily Rodriguez",
                    "role": "Head of Talent",
                    "linkedin_url": "https://linkedin.com/in/emilyrodriguez",
                    "why_relevant": "Recruiter responsible for engineering hires",
                    "recent_signals": []
                },
                {
                    "name": "Michael Lee",
                    "role": "Engineering Manager",
                    "linkedin_url": "https://linkedin.com/in/michaellee",
                    "why_relevant": "Team lead for platform engineering group",
                    "recent_signals": []
                }
            ],
            "secondary_contacts": [
                {
                    "name": "Alex Kim",
                    "role": "Product Director",
                    "linkedin_url": "https://linkedin.com/in/alexkim",
                    "why_relevant": "Cross-functional partner for product strategy",
                    "recent_signals": []
                },
                {
                    "name": "Lisa Wang",
                    "role": "CTO",
                    "linkedin_url": "https://linkedin.com/in/lisawang",
                    "why_relevant": "Executive sponsor of infrastructure initiatives",
                    "recent_signals": []
                },
                {
                    "name": "David Brown",
                    "role": "Senior Engineer",
                    "linkedin_url": "https://linkedin.com/in/davidbrown",
                    "why_relevant": "Peer contact on platform engineering team",
                    "recent_signals": []
                },
                {
                    "name": "Rachel Green",
                    "role": "DevOps Lead",
                    "linkedin_url": "https://linkedin.com/in/rachelgreen",
                    "why_relevant": "Adjacent team lead for DevOps operations",
                    "recent_signals": []
                }
            ]
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper._classify_contacts(
            raw_contacts=[],  # LLM will use state context
            state=sample_job_state
        )

        # Should have both primary and secondary
        assert len(result["primary_contacts"]) == 4
        assert len(result["secondary_contacts"]) == 4

        # Primary should be hiring-related roles
        primary_roles = [c["role"] for c in result["primary_contacts"]]
        assert any("VP" in role or "Director" in role or "Manager" in role or "Talent" in role for role in primary_roles)

    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_falls_back_to_role_based_contacts(self, mock_llm_class, sample_job_state):
        """Generates role-based contacts when no names found."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "primary_contacts": [
                {
                    "name": "VP Engineering at TechCorp",
                    "role": "VP Engineering",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Direct hiring manager for platform team and infrastructure",
                    "recent_signals": []
                },
                {
                    "name": "Director of Platform at TechCorp",
                    "role": "Director of Platform",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Technical decision maker for infrastructure projects",
                    "recent_signals": []
                },
                {
                    "name": "Head of Talent at TechCorp",
                    "role": "Head of Talent",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Recruiter responsible for engineering hiring process",
                    "recent_signals": []
                },
                {
                    "name": "Engineering Manager at TechCorp",
                    "role": "Engineering Manager",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Team lead responsible for day-to-day management",
                    "recent_signals": []
                }
            ],
            "secondary_contacts": [
                {
                    "name": "CTO at TechCorp",
                    "role": "CTO",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Executive sponsor for infrastructure initiatives",
                    "recent_signals": []
                },
                {
                    "name": "Product Director at TechCorp",
                    "role": "Product Director",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Cross-functional partner for product strategy",
                    "recent_signals": []
                },
                {
                    "name": "Senior Engineer at TechCorp",
                    "role": "Senior Engineer",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Peer engineer on the platform engineering team",
                    "recent_signals": []
                },
                {
                    "name": "DevOps Lead at TechCorp",
                    "role": "DevOps Lead",
                    "linkedin_url": "https://www.linkedin.com/company/techcorp/people",
                    "why_relevant": "Infrastructure owner for DevOps operations",
                    "recent_signals": []
                }
            ]
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper._classify_contacts(raw_contacts=[], state=sample_job_state)

        # Should have role-based names
        assert all("at TechCorp" in c["name"] for c in result["primary_contacts"])
        assert len(result["primary_contacts"]) >= 4
        assert len(result["secondary_contacts"]) >= 4

    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_enriches_contacts_with_recent_signals(self, mock_llm_class, sample_job_state):
        """Enriches contacts with recent_signals from company research."""
        # Add company signals to state
        sample_job_state["company_research"]["signals"].append({
            "type": "leadership_change",
            "description": "Sarah Chen promoted to VP Engineering",
            "date": "2024-10-01",
            "source": "https://techcorp.com/news"
        })

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "primary_contacts": [
                {
                    "name": "Sarah Chen",
                    "role": "VP Engineering",
                    "linkedin_url": "https://linkedin.com/in/sarahchen",
                    "why_relevant": "Newly promoted VP who is actively building the team",
                    "recent_signals": ["Recently promoted to VP Engineering"]
                },
                {"name": "John Smith", "role": "Director", "linkedin_url": "https://linkedin.com/in/john", "why_relevant": "Technical lead for platform infrastructure projects", "recent_signals": []},
                {"name": "Emily R", "role": "Recruiter", "linkedin_url": "https://linkedin.com/in/emily", "why_relevant": "Talent acquisition specialist for engineering roles", "recent_signals": []},
                {"name": "Mike L", "role": "Manager", "linkedin_url": "https://linkedin.com/in/mike", "why_relevant": "Engineering manager responsible for team operations", "recent_signals": []}
            ],
            "secondary_contacts": [
                {"name": "Alex K", "role": "Product", "linkedin_url": "https://linkedin.com/in/alex", "why_relevant": "Product manager for platform strategy", "recent_signals": []},
                {"name": "Lisa W", "role": "CTO", "linkedin_url": "https://linkedin.com/in/lisa", "why_relevant": "Executive sponsor for technology initiatives", "recent_signals": []},
                {"name": "David B", "role": "Engineer", "linkedin_url": "https://linkedin.com/in/david", "why_relevant": "Peer engineer on the infrastructure team", "recent_signals": []},
                {"name": "Rachel G", "role": "DevOps", "linkedin_url": "https://linkedin.com/in/rachel", "why_relevant": "Operations lead for DevOps and infrastructure", "recent_signals": []}
            ]
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper._classify_contacts(raw_contacts=[], state=sample_job_state)

        # Sarah Chen should have recent signal
        sarah = next(c for c in result["primary_contacts"] if c["name"] == "Sarah Chen")
        assert len(sarah["recent_signals"]) > 0
        assert "promoted" in sarah["recent_signals"][0].lower() or "VP" in sarah["recent_signals"][0]


# ===== TESTS: OutreachPackage Generation =====

class TestOutreachPackageGeneration:
    """Test OutreachPackage generation with length constraints."""

    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_generates_outreach_packages_for_contacts(self, mock_llm_class, sample_job_state):
        """Generates OutreachPackage for each primary contact."""
        # Mock outreach generation
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "linkedin_message": "Hi Sarah! Reduced incidents 75% at AdTech through CI/CD automation. Would love to chat about TechCorp's platform modernization. Coffee?",
            "subject": "Platform Engineer with 75% Incident Reduction Experience",
            "email_body": "Hi Sarah,\n\nI saw TechCorp recently raised $50M and is scaling infrastructure...\n\nBest,\nCandidate"
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        contact = {
            "name": "Sarah Chen",
            "role": "VP Engineering",
            "linkedin_url": "https://linkedin.com/in/sarahchen",
            "why_relevant": "Hiring manager",
            "recent_signals": []
        }

        outreach_package = mapper._generate_outreach_package(contact, sample_job_state)

        # Should have outreach package structure
        assert "contact_name" in outreach_package
        assert "linkedin_message" in outreach_package
        assert "email_subject" in outreach_package
        assert "email_body" in outreach_package

    def test_enforces_linkedin_length_constraint(self):
        """LinkedIn messages must be ≤550 characters (Phase 9 requirement)."""
        mapper = PeopleMapper()

        long_message = "A" * 600  # Too long

        # Validation should truncate or reject
        trimmed = mapper._validate_linkedin_message(long_message)
        assert len(trimmed) <= 550

    def test_enforces_email_subject_length(self):
        """Email subjects should be concise (≤100 chars recommended)."""
        mapper = PeopleMapper()

        long_subject = "This is an extremely long email subject line that goes on and on and provides way too much detail about the candidate"

        trimmed = mapper._validate_email_subject(long_subject)
        assert len(trimmed) <= 100

    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_outreach_cites_star_metrics(self, mock_llm_class, sample_job_state):
        """Outreach messages cite specific STAR metrics."""
        mock_llm = MagicMock()
        mock_response = MagicMock()

        # Create 150-word email body for Phase 9 validation (100-200 words)
        email_body_150_words = (
            "Dear Hiring Manager, I noticed your role involves addressing legacy monolith challenges. "
            "At AdTech Corp, I achieved 75% incident reduction and 24x faster deployments through platform modernization. "
            "My experience includes automated deployment pipelines, microservices migration, and incident response optimization. "
            "These align perfectly with your manual deployment process challenges. I specialize in transforming legacy systems into modern, scalable architectures. "
            "My approach combines strategic planning with hands-on implementation. I have successfully led similar transformations at multiple organizations, "
            "consistently delivering measurable improvements in system reliability and developer productivity. I would love to discuss how my proven track record "
            "can help TechCorp achieve similar results. My methodology focuses on incremental modernization to minimize risk while delivering continuous value. "
            "I am available for a brief call at your convenience to explore how we can address your specific challenges. Best regards, [Your Name]"
        )

        mock_response.content = json.dumps({
            "linkedin_message": "Reduced incidents 75% at AdTech through automation. Interested in TechCorp's platform challenges. I have applied for this role. Calendly: https://calendly.com/taimooralam/15min",
            "subject": "Solving legacy monolith incidents with proven results",  # 7 words, mentions "legacy monolith incidents"
            "email_body": email_body_150_words
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        contact = {"name": "Sarah", "role": "VP", "linkedin_url": "https://li.com/sarah", "why_relevant": "Manager", "recent_signals": []}
        outreach = mapper._generate_outreach_package(contact, sample_job_state)

        # Should reference metrics from selected_stars
        linkedin_msg = outreach["linkedin_message"]
        email_body = outreach["email_body"]

        # Check for metrics from STAR (75%, 24x)
        assert "75%" in linkedin_msg or "75%" in email_body or "incident" in linkedin_msg.lower()

    def test_validates_email_body_length_too_short(self):
        """Email body must be at least 100 words (Phase 9 ROADMAP requirement)."""
        mapper = PeopleMapper()

        short_email = "This is too short."  # ~4 words

        with pytest.raises(ValueError, match="100"):
            mapper._validate_email_body_length(short_email)

    def test_validates_email_body_length_too_long(self):
        """Email body must be at most 200 words (Phase 9 ROADMAP requirement)."""
        mapper = PeopleMapper()

        # Create a 250-word email
        long_email = " ".join(["word"] * 250)

        with pytest.raises(ValueError, match="200"):
            mapper._validate_email_body_length(long_email)

    def test_validates_email_body_length_valid(self):
        """Email body between 100-200 words passes validation."""
        mapper = PeopleMapper()

        # Create a 150-word email (valid)
        valid_email = " ".join(["word"] * 150)

        # Should not raise
        result = mapper._validate_email_body_length(valid_email)
        assert result == valid_email

    def test_validates_email_subject_words_too_few(self):
        """Email subject must have at least 6 words (Phase 9 ROADMAP requirement)."""
        mapper = PeopleMapper()

        short_subject = "Too short"  # 2 words
        pain_points = ["scaling challenges", "legacy systems"]

        with pytest.raises(ValueError, match="6"):
            mapper._validate_email_subject_words(short_subject, pain_points)

    def test_validates_email_subject_words_too_many(self):
        """Email subject must have at most 10 words (Phase 9 ROADMAP requirement)."""
        mapper = PeopleMapper()

        long_subject = "This is a very long email subject line with way too many words"  # 14 words
        pain_points = ["scaling challenges", "legacy systems"]

        with pytest.raises(ValueError, match="10"):
            mapper._validate_email_subject_words(long_subject, pain_points)

    def test_validates_email_subject_pain_focus_missing(self):
        """Email subject must reference at least one pain point (pain-focused requirement)."""
        mapper = PeopleMapper()

        subject = "Generic subject line with no pain"  # 7 words, but no pain point
        pain_points = ["scaling challenges", "legacy systems"]

        with pytest.raises(ValueError, match="pain"):
            mapper._validate_email_subject_words(subject, pain_points)

    def test_validates_email_subject_words_valid(self):
        """Email subject with 6-10 words and pain focus passes."""
        mapper = PeopleMapper()

        subject = "Solving your scaling challenges with proven results"  # 7 words, mentions "scaling challenges"
        pain_points = ["scaling challenges", "legacy systems"]

        # Should not raise
        result = mapper._validate_email_subject_words(subject, pain_points)
        assert result == subject

    def test_validates_email_subject_words_valid_partial_match(self):
        """Email subject passes if it contains part of a pain point phrase."""
        mapper = PeopleMapper()

        subject = "Platform scaling expertise for modern infrastructure"  # 7 words, contains "scaling"
        pain_points = ["scaling challenges", "technical debt"]

        # Should not raise (partial match on "scaling" from "scaling challenges")
        result = mapper._validate_email_subject_words(subject, pain_points)
        assert result == subject


# ===== TESTS: Integration and Quality Gates =====

@pytest.mark.integration
@patch('src.layer5.people_mapper.FirecrawlApp')
@patch('src.layer5.people_mapper.ChatOpenAI')
def test_people_mapper_node_integration(mock_llm_class, mock_firecrawl_class, sample_job_state):
    """Integration test for people_mapper_node."""
    # Mock FireCrawl
    mock_firecrawl = MagicMock()
    mock_firecrawl.search.return_value = MagicMock(data=[])
    mock_firecrawl.scrape_url.return_value = MagicMock(markdown="Team page content")
    mock_firecrawl_class.return_value = mock_firecrawl

    # Mock LLM for classification
    mock_llm = MagicMock()
    classification_response = MagicMock()
    classification_response.content = json.dumps({
        "primary_contacts": [
            {"name": "Sarah Chen", "role": "VP Engineering", "linkedin_url": "https://linkedin.com/in/sarahchen", "why_relevant": "Direct hiring manager for platform team", "recent_signals": []},
            {"name": "John Smith", "role": "Director", "linkedin_url": "https://linkedin.com/in/john", "why_relevant": "Technical lead for infrastructure projects", "recent_signals": []},
            {"name": "Emily R", "role": "Recruiter", "linkedin_url": "https://linkedin.com/in/emily", "why_relevant": "Talent acquisition for engineering roles", "recent_signals": []},
            {"name": "Mike L", "role": "Manager", "linkedin_url": "https://linkedin.com/in/mike", "why_relevant": "Engineering manager for platform team", "recent_signals": []}
        ],
        "secondary_contacts": [
            {"name": "Alex K", "role": "Product", "linkedin_url": "https://linkedin.com/in/alex", "why_relevant": "Product partner for platform strategy", "recent_signals": []},
            {"name": "Lisa W", "role": "CTO", "linkedin_url": "https://linkedin.com/in/lisa", "why_relevant": "Executive sponsor for infrastructure initiatives", "recent_signals": []},
            {"name": "David B", "role": "Engineer", "linkedin_url": "https://linkedin.com/in/david", "why_relevant": "Peer engineer on infrastructure team", "recent_signals": []},
            {"name": "Rachel G", "role": "DevOps", "linkedin_url": "https://linkedin.com/in/rachel", "why_relevant": "Operations lead for DevOps and SRE", "recent_signals": []}
        ]
    })

    # Mock LLM for outreach (will be called once per contact)
    outreach_response = MagicMock()
    outreach_response.content = json.dumps({
        "linkedin_message": "Reduced incidents 75% at AdTech. Interested in TechCorp platform challenges.",
        "subject": "Platform Engineer - Infrastructure Modernization",
        "email_body": "Hi,\n\nI reduced incidents 75% at AdTech...\n\nBest"
    })

    mock_llm.invoke.side_effect = [classification_response] + [outreach_response] * 8  # 1 classification + 8 outreach calls
    mock_llm_class.return_value = mock_llm

    # Run node
    updates = people_mapper_node(sample_job_state)

    # Assertions
    assert "primary_contacts" in updates
    assert "secondary_contacts" in updates
    assert len(updates["primary_contacts"]) == 4
    assert len(updates["secondary_contacts"]) == 4

    # Each contact should have outreach
    for contact in updates["primary_contacts"]:
        assert "linkedin_message" in contact
        assert "email_subject" in contact
        assert "email_body" in contact


@pytest.mark.quality_gate
class TestPeopleMapperQualityGates:
    """Test Phase 7 quality gates."""

    @patch('src.layer5.people_mapper.FirecrawlApp')
    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_quality_gate_minimum_primary_contacts(self, mock_llm_class, mock_firecrawl_class, sample_job_state):
        """Quality gate: ≥4 primary contacts."""
        # Setup mocks (similar to integration test)
        mock_firecrawl = MagicMock()
        mock_firecrawl.search.return_value = MagicMock(data=[])
        mock_firecrawl.scrape_url.return_value = MagicMock(markdown="Content")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        classification_response = MagicMock()
        classification_response.content = json.dumps({
            "primary_contacts": [
                {"name": f"Person {i}", "role": f"Role {i}", "linkedin_url": f"https://li.com/{i}", "why_relevant": f"Primary contact {i} with relevant hiring authority and experience", "recent_signals": []}
                for i in range(4)
            ],
            "secondary_contacts": [
                {"name": f"Secondary {i}", "role": f"Role {i}", "linkedin_url": f"https://li.com/s{i}", "why_relevant": f"Secondary contact {i} with cross-functional responsibilities", "recent_signals": []}
                for i in range(4)
            ]
        })
        outreach_response = MagicMock()
        outreach_response.content = json.dumps({"linkedin_message": "msg", "subject": "subj", "email_body": "body"})
        mock_llm.invoke.side_effect = [classification_response] + [outreach_response] * 8
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper.map_people(sample_job_state)

        # Quality gate: ≥4 primary contacts
        assert len(result["primary_contacts"]) >= 4

    @patch('src.layer5.people_mapper.FirecrawlApp')
    @patch('src.layer5.people_mapper.ChatOpenAI')
    def test_quality_gate_specific_why_relevant(self, mock_llm_class, mock_firecrawl_class, sample_job_state):
        """Quality gate: why_relevant is specific and grounded."""
        # Setup mocks
        mock_firecrawl = MagicMock()
        mock_firecrawl.search.return_value = MagicMock(data=[])
        mock_firecrawl.scrape_url.return_value = MagicMock(markdown="Content")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        classification_response = MagicMock()
        classification_response.content = json.dumps({
            "primary_contacts": [
                {"name": "Sarah Chen", "role": "VP Engineering", "linkedin_url": "https://li.com/sarah", "why_relevant": "Direct hiring manager for platform team, oversees infrastructure modernization", "recent_signals": []},
                {"name": "John", "role": "Director", "linkedin_url": "https://li.com/john", "why_relevant": "Technical decision maker for cloud architecture", "recent_signals": []},
                {"name": "Emily", "role": "Recruiter", "linkedin_url": "https://li.com/emily", "why_relevant": "Talent acquisition for engineering roles", "recent_signals": []},
                {"name": "Mike", "role": "Manager", "linkedin_url": "https://li.com/mike", "why_relevant": "Team lead for platform engineering", "recent_signals": []}
            ],
            "secondary_contacts": [
                {"name": "Alex", "role": "Product", "linkedin_url": "https://li.com/alex", "why_relevant": "Cross-functional partner", "recent_signals": []},
                {"name": "Lisa", "role": "CTO", "linkedin_url": "https://li.com/lisa", "why_relevant": "Executive sponsor", "recent_signals": []},
                {"name": "David", "role": "Engineer", "linkedin_url": "https://li.com/david", "why_relevant": "Peer", "recent_signals": []},
                {"name": "Rachel", "role": "DevOps", "linkedin_url": "https://li.com/rachel", "why_relevant": "Operations lead", "recent_signals": []}
            ]
        })
        outreach_response = MagicMock()
        outreach_response.content = json.dumps({"linkedin_message": "msg", "subject": "subj", "email_body": "body"})
        mock_llm.invoke.side_effect = [classification_response] + [outreach_response] * 8
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper.map_people(sample_job_state)

        # Quality gate: why_relevant should be specific (not generic)
        for contact in result["primary_contacts"]:
            why = contact["why_relevant"]
            # Should not be generic phrases
            assert why != "Relevant person"
            assert why != "Good contact"
            assert len(why) > 20  # Should be detailed
