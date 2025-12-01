"""
Unit tests for Layer 6 Markdown CV Generator (Phase 8.2).

Tests the MarkdownCVGenerator which:
- Uses master-cv.md as source of truth
- Generates CV.md output grounded in job dossier
- Includes integrity check for hallucination prevention
- Outputs to ./applications/<company>/<role>/CV.md
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path
import os
import shutil

from src.common.state import JobState


# ===== FIXTURES =====

@pytest.fixture
def mock_llm_providers():
    """
    Mock both ChatAnthropic and ChatOpenAI to prevent real API calls.

    This fixture ensures tests run without making real API requests,
    preventing costs and failures when API credits are low.
    """
    with patch('src.layer6.generator.ChatAnthropic') as mock_anthropic, \
         patch('src.layer6.generator.ChatOpenAI') as mock_openai, \
         patch('src.layer6.generator.Config') as mock_config:

        # Configure mock Config to use OpenAI by default (simpler for tests)
        mock_config.get_cv_llm_provider.return_value = "openai"
        mock_config.get_cv_llm_api_key.return_value = "test-api-key"
        mock_config.get_cv_llm_base_url.return_value = "https://api.openai.com/v1"
        mock_config.DEFAULT_MODEL = "gpt-4"
        mock_config.ANALYTICAL_TEMPERATURE = 0.3

        # Create mock LLM instances
        mock_llm_instance = MagicMock()
        mock_anthropic.return_value = mock_llm_instance
        mock_openai.return_value = mock_llm_instance

        yield {
            'anthropic': mock_anthropic,
            'openai': mock_openai,
            'config': mock_config,
            'instance': mock_llm_instance
        }


@pytest.fixture
def sample_job_state():
    """Sample JobState with all required fields for CV generation."""
    return {
        "job_id": "test_job_123",
        "title": "Senior Engineering Manager",
        "company": "TechCorp",
        "job_url": "https://linkedin.com/jobs/view/123456",
        "source": "linkedin",
        "job_description": """
We are seeking a Senior Engineering Manager to lead a team of 8-12 engineers.

Key Responsibilities:
- Lead agile delivery of core platform features
- Establish engineering processes (CI/CD, code review, testing)
- Design system architecture for multi-tenant SaaS platform
- Mentor junior engineers and build high-performing teams
""",
        "pain_points": [
            "Team velocity has decreased 40% over past 6 months",
            "No standardized engineering processes causing quality issues",
            "System architecture cannot scale beyond current 10K users"
        ],
        "strategic_needs": [
            "Build engineering culture of quality and velocity",
            "Establish clear career progression framework"
        ],
        "risks_if_unfilled": [
            "Continued productivity decline",
            "Key engineer attrition"
        ],
        "success_metrics": [
            "Restore team velocity within 6 months",
            "Implement CI/CD pipeline"
        ],
        "company_research": {
            "summary": "TechCorp is a fast-growing SaaS company recently secured Series B funding",
            "signals": [
                {"type": "funding", "description": "Raised $50M Series B", "date": "2024-01", "source": "techcrunch"},
                {"type": "product_launch", "description": "Launched enterprise tier", "date": "2024-02", "source": "linkedin"}
            ],
            "url": "https://techcorp.com"
        },
        "role_research": {
            "summary": "Engineering management role focused on team building and delivery",
            "business_impact": [
                "Reduce engineering toil",
                "Improve deployment frequency",
                "Build high-performing team"
            ],
            "why_now": "Series B funding requires scaling engineering capacity"
        },
        "candidate_profile": """
# Taimoor Alam
**Engineering Leader | Platform & Infrastructure | Team Builder**

Email: taimooralam@example.com
LinkedIn: https://linkedin.com/in/taimooralam

## Professional Experience

**Engineering Manager — AdTech Co — Munich, DE | 2020-2023**
- Led team of 10 engineers, reduced release cycle from 12 weeks to 2 weeks
- Improved team engagement by 60%, zero attrition over 2 years
- Implemented agile practices and code review standards

**Tech Lead — FinTech Startup — Munich, DE | 2018-2020**
- Architected microservices migration on AWS/Kubernetes
- Scaled platform from 5K to 500K users with 99.99% uptime
- Achieved $1M cost savings via autoscaling

**Senior Software Engineer — Consulting Firm — Munich, DE | 2015-2018**
- Delivered 15+ production applications using Java/Python/React
- 100% on-time delivery, promoted to technical lead

## Education
B.S. Computer Science | State University | 2015
"""
    }


@pytest.fixture
def mock_evidence_response():
    """Sample LLM response for evidence (JSON) generation."""
    return """
{
  "roles": [
    {
      "role": "Engineering Manager — AdTech Co",
      "bullets": [
        {
          "situation": "Monolith slowing delivery and quality",
          "action": "led microservice migration and CI/CD rollout",
          "result": "restored team velocity and stability",
          "metric": "6x faster releases",
          "pain_point_hit": "Restore team velocity within 6 months"
        }
      ]
    }
  ]
}
"""


@pytest.fixture
def mock_llm_response():
    """Sample LLM response for CV generation."""
    return """# Taimoor Alam
**Senior Engineering Manager | Platform & Infrastructure | Team Builder**

## Professional Summary
Engineering leader with 8+ years experience building and scaling high-performing teams.
Proven track record of improving team velocity, implementing CI/CD pipelines, and mentoring engineers.

## Core Skills
- **Leadership**: Team building, agile methodologies, career development
- **Technical**: AWS, Kubernetes, microservices, CI/CD
- **Process**: Code review standards, engineering best practices

## Professional Experience

### Engineering Manager — AdTech Co — Munich, DE | 2020-2023
- Led team of 10 engineers, reduced release cycle from 12 weeks to 2 weeks (6x improvement) to restore team velocity within 6 months.
- Improved team engagement by 60%, achieved zero attrition over 2 years to restore team velocity within 6 months.
- Implemented agile practices and established code review standards to restore team velocity within 6 months.

### Tech Lead — FinTech Startup — Munich, DE | 2018-2020
- Architected microservices migration on AWS/Kubernetes to implement CI/CD pipeline.
- Scaled platform from 5K to 500K users with 99.99% uptime.
- Achieved $1M annual cost savings via autoscaling.

### Senior Software Engineer — Consulting Firm — Munich, DE | 2015-2018
- Delivered 15+ production applications using Java/Python/React.
- Maintained 100% on-time delivery record.

## Education
B.S. Computer Science | State University | 2015

---
Integrity Check: All facts verified against master CV. No fabrications. Dates and employers match source.
"""


@pytest.fixture
def messy_cv_response():
    """LLM response that ignores template headings and needs normalization."""
    return """
Here is the revised CV in Markdown format:

**Taimoor Alam**  
Engineering Leader / Application Security | Cloud | Leadership  
German National | Languages: English (C1), German (B2)  

---
**Profile**  
Security-focused engineering leader who reduced MTTR by 60% and embedded secure SDLC.

**Professional Experience**
**Technical Lead (Addressable TV)**
Seven.One Entertainment Group — Munich, DE | 2020–Present  
• Led zero-downtime microservices migration, reducing incidents by 75%.

**Education & Certifications**
- MSc. Computer Science — TU Munich

Integrity Check: Verified against master CV; no fabricated employers or dates.
"""


@pytest.fixture
def cleanup_test_output(tmp_path, monkeypatch):
    """
    Use unique temp directory for each test to avoid parallel test race conditions.

    Monkeypatches the applications directory to be unique per test.
    """
    # Create unique applications dir for this test
    test_applications = tmp_path / "applications"
    test_applications.mkdir()

    # Store original cwd and change to temp directory for this test
    original_cwd = os.getcwd()

    # Monkeypatch Path calls in the generator to use relative paths from our temp
    # Actually, since the generator uses relative paths, we can just chdir
    os.chdir(tmp_path)

    yield tmp_path

    # Restore original directory
    os.chdir(original_cwd)

    # Cleanup happens automatically when tmp_path is cleaned up by pytest


# ===== BASIC FUNCTIONALITY TESTS =====

class TestMarkdownCVGenerator:
    """Test MarkdownCVGenerator class."""

    def test_generates_cv_successfully(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """MarkdownCVGenerator.generate_cv returns valid path and integrity check."""
        from src.layer6.generator import MarkdownCVGenerator

        # Configure mock LLM responses
        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        cv_path, integrity = generator.generate_cv(sample_job_state)

        assert cv_path is not None
        assert cv_path.endswith(".md")
        assert "TechCorp" in cv_path
        assert Path(cv_path).exists()

    def test_outputs_to_correct_directory(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """CV is saved to ./applications/<company>/<role>/CV.md."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        cv_path, _ = generator.generate_cv(sample_job_state)

        # Verify directory structure (relative to tmp_path from cleanup_test_output)
        expected_dir = cleanup_test_output / "applications" / "TechCorp" / "Senior_Engineering_Manager"
        assert expected_dir.exists()
        assert (expected_dir / "CV.md").exists()

    def test_extracts_integrity_check(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Generator extracts integrity check from LLM response."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        _, integrity = generator.generate_cv(sample_job_state)

        assert integrity is not None
        assert "fabrication" in integrity.lower() or "verified" in integrity.lower()

    def test_normalizes_markdown_for_template(self, mock_llm_providers, sample_job_state, mock_evidence_response, messy_cv_response, cleanup_test_output):
        """Generator normalizes loosely formatted markdown to template-friendly headings."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        messy = MagicMock()
        messy.content = messy_cv_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, messy, messy]

        generator = MarkdownCVGenerator()
        cv_path, _ = generator.generate_cv(sample_job_state)

        content = Path(cv_path).read_text()

        assert content.startswith("# Taimoor Alam")
        assert "## Profile" in content
        assert "## Professional Experience" in content
        assert "### Technical Lead (Addressable TV) — Seven.One Entertainment Group — Munich, DE | 2020–Present" in content
        assert "•" not in content
        assert "---" not in content

    def test_includes_pain_points_in_prompt(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response):
        """Generator includes pain points in LLM prompt."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        generator.generate_cv(sample_job_state)

        # Check prompt content (first call to evidence generator)
        call_args = mock_llm.invoke.call_args_list[0][0][0]
        prompt_text = " ".join(msg.content for msg in call_args)

        assert "velocity" in prompt_text.lower() or "40%" in prompt_text

    def test_includes_company_research_in_prompt(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response):
        """Generator includes company research in LLM prompt."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        generator.generate_cv(sample_job_state)

        call_args = mock_llm.invoke.call_args_list[0][0][0]
        prompt_text = " ".join(msg.content for msg in call_args)

        assert "Series B" in prompt_text or "funding" in prompt_text.lower()

    def test_includes_master_cv_in_prompt(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response):
        """Generator includes master CV (candidate_profile) in LLM prompt."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        generator.generate_cv(sample_job_state)

        call_args = mock_llm.invoke.call_args_list[0][0][0]
        prompt_text = " ".join(msg.content for msg in call_args)

        assert "Taimoor Alam" in prompt_text
        assert "AdTech Co" in prompt_text


# ===== EDGE CASE TESTS =====

class TestMarkdownCVGeneratorEdgeCases:
    """Test edge cases for CV generator."""

    def test_handles_missing_pain_points(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Generator handles missing pain points gracefully."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        # Remove pain points
        state = sample_job_state.copy()
        state["pain_points"] = None

        generator = MarkdownCVGenerator()
        cv_path, integrity = generator.generate_cv(state)

        assert cv_path is not None
        assert Path(cv_path).exists()

    def test_handles_missing_company_research(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Generator handles missing company research gracefully."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        # Remove company research
        state = sample_job_state.copy()
        state["company_research"] = None

        generator = MarkdownCVGenerator()
        cv_path, integrity = generator.generate_cv(state)

        assert cv_path is not None
        assert Path(cv_path).exists()

    def test_sanitizes_company_name_for_path(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Generator sanitizes company name for file system path."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]

        # Company with special characters
        state = sample_job_state.copy()
        state["company"] = "Tech/Corp Inc."

        generator = MarkdownCVGenerator()
        cv_path, _ = generator.generate_cv(state)

        # Path should not contain slashes or dots from company name
        assert "/" not in Path(cv_path).parent.name
        assert "Tech_Corp_Inc" in cv_path
        # Cleanup handled by cleanup_test_output fixture

    def test_handles_no_integrity_check_in_response(self, mock_llm_providers, sample_job_state, mock_evidence_response, cleanup_test_output):
        """Generator handles response without explicit verification section."""
        from src.layer6.generator import MarkdownCVGenerator

        mock_response = MagicMock()
        # Content without any "integrity" keyword to avoid regex match
        mock_response.content = "# CV Content\n\nThis is plain CV text without verification."
        evidence = MagicMock()
        evidence.content = mock_evidence_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, mock_response, mock_response]

        generator = MarkdownCVGenerator()
        cv_path, integrity = generator.generate_cv(sample_job_state)

        assert cv_path is not None
        assert "not provided" in integrity.lower()

    def test_retries_on_invalid_evidence_json(self, mock_llm_providers, sample_job_state, mock_llm_response, cleanup_test_output):
        """Generator retries evidence generation when required fields are missing."""
        from src.layer6.generator import MarkdownCVGenerator

        # First evidence missing metric/pain point, second fixes it
        bad_evidence = MagicMock()
        bad_evidence.content = '{"roles":[{"role":"Engineering Manager","bullets":[{"situation":"x","action":"","result":"","metric":"","pain_point_hit":""}]}]}'
        good_evidence = MagicMock()
        good_evidence.content = '{"roles":[{"role":"Engineering Manager","bullets":[{"situation":"x","action":"did a thing","result":"improved","metric":"10%","pain_point_hit":"Restore team velocity within 6 months"}]}]}'
        final_cv = MagicMock()
        final_cv.content = mock_llm_response

        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [bad_evidence, good_evidence, final_cv, final_cv]

        generator = MarkdownCVGenerator()
        cv_path, _ = generator.generate_cv(sample_job_state)

        assert Path(cv_path).exists()
        # At least two calls (retry on evidence) plus CV calls
        assert len(mock_llm.invoke.call_args_list) >= 3


# ===== PROMPT BUILDING TESTS =====

class TestMarkdownCVGeneratorPrompt:
    """Test prompt building logic."""

    def test_prompt_includes_job_dossier(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response):
        """Prompt includes all job dossier fields."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        generator = MarkdownCVGenerator()
        generator.generate_cv(sample_job_state)

        call_args = mock_llm.invoke.call_args_list[0][0][0]
        prompt_text = " ".join(msg.content for msg in call_args)

        # Check job dossier fields
        assert "Senior Engineering Manager" in prompt_text  # Title
        assert "TechCorp" in prompt_text  # Company
        assert "linkedin" in prompt_text.lower()  # Source or URL

    def test_prompt_includes_role_research(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response):
        """Prompt includes role research with business impact."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        generator = MarkdownCVGenerator()
        generator.generate_cv(sample_job_state)

        call_args = mock_llm.invoke.call_args_list[0][0][0]
        prompt_text = " ".join(msg.content for msg in call_args)

        # Check role research fields
        assert "team building" in prompt_text.lower() or "deployment" in prompt_text.lower()
        assert "Why now" in prompt_text or "why now" in prompt_text.lower()

    def test_prompt_includes_job_description(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response):
        """Prompt includes full job description text."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        generator = MarkdownCVGenerator()
        generator.generate_cv(sample_job_state)

        call_args = mock_llm.invoke.call_args_list[0][0][0]
        prompt_text = " ".join(msg.content for msg in call_args)

        assert "senior engineering manager" in prompt_text.lower()
        assert "lead agile delivery of core platform features".lower() in prompt_text.lower()


# ===== INTEGRATION TEST =====

class TestMarkdownCVGeneratorIntegration:
    """Integration tests for full CV generation flow."""

    def test_full_cv_generation_flow(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Test complete flow from state to saved CV."""
        from src.layer6.generator import Generator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        # Use the main Generator class that orchestrates both cover letter and CV
        with patch('src.layer6.cover_letter_generator.CoverLetterGenerator.generate_cover_letter') as mock_cl:
            mock_cl.return_value = "Sample cover letter with 75% improvement at AdTech Co"

            generator = Generator()
            result = generator.generate_outputs(sample_job_state)

            assert result.get("cv_path") is not None
            assert result.get("cv_reasoning") is not None
            assert result.get("cover_letter") is not None

    def test_generator_node_returns_state_updates(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Test LangGraph node function returns proper state updates."""
        from src.layer6.generator import generator_node

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        with patch('src.layer6.cover_letter_generator.CoverLetterGenerator.generate_cover_letter') as mock_cl:
            mock_cl.return_value = "Sample cover letter with 75% improvement at AdTech Co"

            updates = generator_node(sample_job_state)

            assert "cv_path" in updates
            assert "cv_reasoning" in updates
            assert "cover_letter" in updates

    def test_generator_node_returns_cv_text(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Test generator_node returns cv_text for MongoDB persistence."""
        from src.layer6.generator import generator_node

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        with patch('src.layer6.cover_letter_generator.CoverLetterGenerator.generate_cover_letter') as mock_cl:
            mock_cl.return_value = "Sample cover letter with 75% improvement at AdTech Co"

            updates = generator_node(sample_job_state)

            # Verify cv_text is included in updates for MongoDB persistence
            assert "cv_text" in updates
            assert updates["cv_text"] is not None
            assert len(updates["cv_text"]) > 0
            assert "Taimoor Alam" in updates["cv_text"]


# ===== QUALITY GATE TESTS =====

@pytest.mark.quality_gate
class TestMarkdownCVGeneratorQualityGates:
    """Quality gate tests for CV generator."""

    def test_quality_gate_master_cv_grounding(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Quality gate: Generated CV should be grounded in master CV."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        generator = MarkdownCVGenerator()
        cv_path, integrity = generator.generate_cv(sample_job_state)

        # Read generated CV
        cv_content = Path(cv_path).read_text()

        # CV should contain employers from master CV
        assert "AdTech Co" in cv_content or "FinTech Startup" in cv_content

        # CV should contain candidate name
        assert "Taimoor Alam" in cv_content

    def test_quality_gate_cv_contains_metrics(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Quality gate: Generated CV should contain quantified metrics."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        generator = MarkdownCVGenerator()
        cv_path, _ = generator.generate_cv(sample_job_state)

        cv_content = Path(cv_path).read_text()

        # CV should contain metrics
        import re
        metrics = re.findall(r'\d+%|\d+x|\$\d+[MKB]?|\d+K', cv_content)
        assert len(metrics) >= 2, f"CV should have at least 2 metrics, found: {metrics}"

    def test_quality_gate_cv_structure(self, mock_llm_providers, sample_job_state, mock_llm_response, mock_evidence_response, cleanup_test_output):
        """Quality gate: Generated CV should have proper structure."""
        from src.layer6.generator import MarkdownCVGenerator

        evidence = MagicMock()
        evidence.content = mock_evidence_response
        final_cv = MagicMock()
        final_cv.content = mock_llm_response
        
        mock_llm = mock_llm_providers['instance']
        mock_llm.invoke.side_effect = [evidence, final_cv, final_cv]


        generator = MarkdownCVGenerator()
        cv_path, _ = generator.generate_cv(sample_job_state)

        cv_content = Path(cv_path).read_text()

        # CV should have key sections (using markdown headers)
        section_patterns = ["experience", "summary", "skill"]
        sections_found = sum(1 for p in section_patterns if p in cv_content.lower())
        assert sections_found >= 2, f"CV should have at least 2 major sections, found {sections_found}"
