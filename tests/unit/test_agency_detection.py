"""
Unit tests for Recruitment Agency Detection Feature.

Tests the detection and handling of recruitment agencies in the pipeline:
- Company type classification
- Minimal research for agencies
- Agency-specific contact limits (2 recruiters max)
- Recruiter cover letter generation
- Agency note in fit rationale
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.common.state import JobState, CompanyResearch


# ===== FIXTURES =====

@pytest.fixture
def sample_employer_state():
    """Sample state for a direct employer job."""
    return {
        "job_id": "test-123",
        "title": "Engineering Manager",
        "company": "TechCorp Inc",
        "job_description": "We are hiring an engineering manager to lead our platform team...",
        "job_url": "https://linkedin.com/jobs/123",
        "source": "linkedin",
        "candidate_profile": "Experienced engineering leader...",
        "company_research": {
            "summary": "TechCorp Inc is a technology company...",
            "signals": [],
            "url": "https://techcorp.com",
            "company_type": "employer"
        }
    }


@pytest.fixture
def sample_agency_state():
    """Sample state for a recruitment agency job."""
    return {
        "job_id": "test-456",
        "title": "Senior Software Engineer",
        "company": "Robert Half Technology",
        "job_description": "Our client is seeking a senior software engineer...",
        "job_url": "https://linkedin.com/jobs/456",
        "source": "linkedin",
        "candidate_profile": "Experienced software engineer...",
        "company_research": {
            "summary": "Robert Half Technology is a recruitment/staffing agency sourcing candidates for their clients.",
            "signals": [],
            "url": "https://roberthalf.com",
            "company_type": "recruitment_agency"
        }
    }


# ===== TESTS: Company Type Classification =====

class TestCompanyTypeClassification:
    """Test company type classification logic."""

    def test_detects_agency_by_keyword_in_name(self):
        """Detects agency when company name contains agency keywords."""
        from src.layer3.company_researcher import CompanyResearcher

        with patch.object(CompanyResearcher, '__init__', lambda x: None):
            researcher = CompanyResearcher.__new__(CompanyResearcher)
            researcher.logger = MagicMock()

            # Test various agency names
            agency_names = [
                "Robert Half Technology",
                "Hays Recruitment",
                "Randstad Staffing",
                "TechStaffing Solutions",
                "Global Talent Partners",
            ]

            for name in agency_names:
                state = {"company": name, "title": "Engineer", "job_description": "Job desc"}
                result = researcher._classify_company_type(state)
                assert result == "recruitment_agency", f"Failed for: {name}"

    def test_employer_classification_for_regular_companies(self):
        """Regular companies are classified as employers."""
        from src.layer3.company_researcher import CompanyResearcher

        with patch.object(CompanyResearcher, '__init__', lambda x: None):
            researcher = CompanyResearcher.__new__(CompanyResearcher)
            researcher.logger = MagicMock()
            researcher.llm = MagicMock()

            # Mock LLM response
            researcher.llm.invoke.return_value = MagicMock(
                content='{"company_type": "employer", "confidence": "high", "reasoning": "Tech company"}'
            )

            state = {"company": "Google", "title": "Engineer", "job_description": "Join our team"}
            result = researcher._classify_company_type(state)
            assert result == "employer"


# ===== TESTS: Minimal Agency Research =====

class TestMinimalAgencyResearch:
    """Test that agencies get minimal research."""

    @patch('src.layer3.company_researcher.CompanyResearcher._classify_company_type')
    @patch('src.layer3.company_researcher.CompanyResearcher._scrape_job_posting')
    def test_agency_research_returns_minimal_data(self, mock_scrape, mock_classify):
        """Agency research returns minimal data with company_type set."""
        from src.layer3.company_researcher import CompanyResearcher

        mock_classify.return_value = "recruitment_agency"
        mock_scrape.return_value = "Job posting content"

        with patch.object(CompanyResearcher, '__init__', lambda x: None):
            researcher = CompanyResearcher.__new__(CompanyResearcher)
            researcher.logger = MagicMock()
            researcher._classify_company_type = mock_classify
            researcher._scrape_job_posting = mock_scrape
            researcher._construct_company_url = lambda x: f"https://{x.lower().replace(' ', '-')}.com"

            state = {"company": "Hays Recruitment", "job_url": "https://linkedin.com/jobs/123"}
            result = researcher.research_company(state)

            # Verify minimal research
            assert result["company_research"]["company_type"] == "recruitment_agency"
            assert result["company_research"]["signals"] == []
            assert "recruitment/staffing agency" in result["company_research"]["summary"]


# ===== TESTS: Agency-Specific Contact Limits =====

class TestAgencyContactLimits:
    """Test that agencies get only 2 recruiter contacts."""

    def test_agency_recruiter_contacts_method_returns_two_contacts(self, sample_agency_state):
        """Agency recruiter method generates exactly 2 contacts."""
        from src.layer5.people_mapper import PeopleMapper

        with patch.object(PeopleMapper, '__init__', lambda x: None):
            mapper = PeopleMapper.__new__(PeopleMapper)
            mapper.logger = MagicMock()

            result = mapper._generate_agency_recruiter_contacts(sample_agency_state)

            assert len(result["primary_contacts"]) == 2
            assert len(result["secondary_contacts"]) == 0
            assert all("Recruiter" in c["role"] or "Account Manager" in c["role"]
                      for c in result["primary_contacts"])


# ===== TESTS: Role Research Skip =====

class TestRoleResearchSkip:
    """Test that role research is skipped for agencies."""

    def test_role_researcher_skips_for_agency(self, sample_agency_state):
        """Role researcher skips processing for agencies."""
        from src.layer3.role_researcher import role_researcher_node

        result = role_researcher_node(sample_agency_state)

        assert result["role_research"] is None

    def test_role_researcher_processes_for_employer(self, sample_employer_state):
        """Role researcher processes normally for employers."""
        from src.layer3.role_researcher import role_researcher_node

        with patch('src.layer3.role_researcher.RoleResearcher') as MockResearcher:
            mock_instance = MagicMock()
            mock_instance.research_role.return_value = {
                "role_research": {
                    "summary": "Role summary",
                    "business_impact": ["Impact 1", "Impact 2", "Impact 3"],
                    "why_now": "Why now explanation"
                }
            }
            MockResearcher.return_value = mock_instance

            result = role_researcher_node(sample_employer_state)

            assert result["role_research"] is not None


# ===== TESTS: Fit Rationale Agency Note =====

class TestFitRationaleAgencyNote:
    """Test that agency note is added to fit rationale."""

    @patch('src.layer4.opportunity_mapper.OpportunityMapper._analyze_fit')
    def test_agency_note_added_to_rationale(self, mock_analyze, sample_agency_state):
        """Agency note is appended to fit rationale for agencies."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        mock_analyze.return_value = (75, "Good fit based on skills.", "strong")

        with patch.object(OpportunityMapper, '__init__', lambda x: None):
            mapper = OpportunityMapper.__new__(OpportunityMapper)
            mapper.logger = MagicMock()
            mapper._analyze_fit = mock_analyze

            result = mapper.map_opportunity(sample_agency_state)

            assert "recruitment agency position" in result["fit_rationale"]
            assert "undisclosed client company" in result["fit_rationale"]

    @patch('src.layer4.opportunity_mapper.OpportunityMapper._analyze_fit')
    def test_no_agency_note_for_employer(self, mock_analyze, sample_employer_state):
        """No agency note for direct employer jobs."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        mock_analyze.return_value = (85, "Excellent fit.", "exceptional")

        with patch.object(OpportunityMapper, '__init__', lambda x: None):
            mapper = OpportunityMapper.__new__(OpportunityMapper)
            mapper.logger = MagicMock()
            mapper._analyze_fit = mock_analyze

            result = mapper.map_opportunity(sample_employer_state)

            assert "recruitment agency" not in result["fit_rationale"]


# ===== TESTS: Recruiter Cover Letter =====

class TestRecruiterCoverLetter:
    """Test recruiter-specific cover letter generation."""

    def test_recruiter_cover_letter_validation_word_count(self):
        """Recruiter cover letter validation enforces word count limits."""
        from src.layer6.recruiter_cover_letter import validate_recruiter_cover_letter

        # Too short
        short_letter = "Hello, I want the job. Thanks."
        with pytest.raises(ValueError) as excinfo:
            validate_recruiter_cover_letter(short_letter, {})
        assert "too short" in str(excinfo.value).lower()

        # Too long
        long_letter = "word " * 300
        with pytest.raises(ValueError) as excinfo:
            validate_recruiter_cover_letter(long_letter, {})
        assert "too long" in str(excinfo.value).lower()

    def test_recruiter_cover_letter_requires_metric(self):
        """Recruiter cover letter requires at least one metric."""
        from src.layer6.recruiter_cover_letter import validate_recruiter_cover_letter

        # Letter with 120+ words but no metrics
        no_metric_letter = (
            "I am writing to express my interest in the Senior Software Engineer role "
            "at your recruitment agency. Throughout my career, I have developed expertise "
            "in building scalable backend systems and leading engineering teams across "
            "multiple organizations. At my previous company, I worked on several high-impact "
            "projects that significantly improved system performance and user experience. "
            "I have extensive experience with Python, Kubernetes, and modern cloud "
            "infrastructure including AWS and GCP. I have a proven track record of delivering "
            "complex features on time and collaborating effectively with cross-functional teams "
            "including product managers and designers. I believe my background makes me an "
            "excellent fit for this position. I am available to discuss this opportunity "
            "at your earliest convenience and look forward to hearing from you soon. "
            "I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"
        )
        with pytest.raises(ValueError) as excinfo:
            validate_recruiter_cover_letter(no_metric_letter, {})
        assert "metric" in str(excinfo.value).lower()

    def test_recruiter_cover_letter_requires_calendly(self):
        """Recruiter cover letter requires Calendly link."""
        from src.layer6.recruiter_cover_letter import validate_recruiter_cover_letter

        # Letter with metrics but no Calendly
        no_calendly = (
            "I am interested in the Engineering Manager role at your agency. "
            "At my previous company, I led a team of 12 engineers and reduced latency by 75%. "
            "I implemented CI/CD pipelines that improved deployment frequency by 10x. "
            "Our team delivered three major platform migrations on schedule. "
            "I have experience managing engineering teams of up to 15 people "
            "and have consistently met sprint commitments with a 95% success rate. "
            "I also mentored junior engineers and conducted technical interviews. "
            "My expertise spans Python, Kubernetes, AWS, and modern DevOps practices. "
            "I am excited about the opportunity to bring my leadership experience "
            "to this role and help your clients build great engineering teams. "
            "Please let me know if you would like to schedule a conversation."
        )
        with pytest.raises(ValueError) as excinfo:
            validate_recruiter_cover_letter(no_calendly, {})
        assert "calendly" in str(excinfo.value).lower()

    def test_recruiter_cover_letter_passes_validation(self):
        """Valid recruiter cover letter passes validation."""
        from src.layer6.recruiter_cover_letter import validate_recruiter_cover_letter

        valid_letter = (
            "I am interested in the Senior Engineer role at Robert Half and believe "
            "my background makes me an excellent candidate for this position. "
            "At TechCorp, I built backend services that processed 100K requests daily "
            "and reduced system latency by 50%. I led a team of 8 engineers to deliver "
            "a new authentication system that improved security posture significantly "
            "and reduced security incidents across the platform. "
            "My experience includes Python, Kubernetes, and AWS cloud infrastructure "
            "as well as modern DevOps practices and CI/CD pipeline development. "
            "I have a strong track record of delivering complex features on time "
            "and collaborating effectively with product managers and design teams. "
            "I am available for an interview at your convenience and would welcome "
            "the opportunity to discuss how my skills align with your client's needs. "
            "I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"
        )
        # Should not raise
        validate_recruiter_cover_letter(valid_letter, {})


# ===== TESTS: Generator Uses Correct Cover Letter =====

class TestGeneratorCoverLetterSelection:
    """Test that Generator uses correct cover letter based on company type."""

    @patch('src.layer6.generator.CoverLetterGenerator')
    @patch('src.layer6.generator.RecruiterCoverLetterGenerator')
    @patch('src.layer6.generator.MarkdownCVGenerator')
    def test_uses_recruiter_cover_letter_for_agency(
        self, mock_cv_gen, mock_recruiter_gen, mock_cover_gen, sample_agency_state
    ):
        """Uses RecruiterCoverLetterGenerator for agency jobs."""
        from src.layer6.generator import Generator

        mock_recruiter_instance = MagicMock()
        mock_recruiter_instance.generate_cover_letter.return_value = "Recruiter cover letter"
        mock_recruiter_gen.return_value = mock_recruiter_instance

        mock_cv_instance = MagicMock()
        mock_cv_instance.generate_cv.return_value = ("/path/to/cv.md", "reasoning")
        mock_cv_gen.return_value = mock_cv_instance

        generator = Generator()
        generator.html_cv_gen = None  # Disable HTML CV
        result = generator.generate_outputs(sample_agency_state)

        # Verify recruiter generator was used
        mock_recruiter_instance.generate_cover_letter.assert_called_once()
        mock_cover_gen.return_value.generate_cover_letter.assert_not_called()
        assert result["cover_letter"] == "Recruiter cover letter"

    @patch('src.layer6.generator.CoverLetterGenerator')
    @patch('src.layer6.generator.RecruiterCoverLetterGenerator')
    @patch('src.layer6.generator.MarkdownCVGenerator')
    def test_uses_standard_cover_letter_for_employer(
        self, mock_cv_gen, mock_recruiter_gen, mock_cover_gen, sample_employer_state
    ):
        """Uses standard CoverLetterGenerator for employer jobs."""
        from src.layer6.generator import Generator

        mock_cover_instance = MagicMock()
        mock_cover_instance.generate_cover_letter.return_value = "Standard cover letter"
        mock_cover_gen.return_value = mock_cover_instance

        mock_cv_instance = MagicMock()
        mock_cv_instance.generate_cv.return_value = ("/path/to/cv.md", "reasoning")
        mock_cv_gen.return_value = mock_cv_instance

        generator = Generator()
        generator.html_cv_gen = None  # Disable HTML CV
        result = generator.generate_outputs(sample_employer_state)

        # Verify standard generator was used
        mock_cover_instance.generate_cover_letter.assert_called_once()
        mock_recruiter_gen.return_value.generate_cover_letter.assert_not_called()
        assert result["cover_letter"] == "Standard cover letter"


# ===== TESTS: CompanyResearch TypedDict =====

class TestCompanyResearchTypeAnnotation:
    """Test that CompanyResearch TypedDict includes company_type."""

    def test_company_research_has_company_type_field(self):
        """CompanyResearch TypedDict includes company_type field."""
        from src.common.state import CompanyResearch
        import typing

        # Get the annotations from the TypedDict
        annotations = typing.get_type_hints(CompanyResearch)

        assert "company_type" in annotations
        assert annotations["company_type"] == str
