"""
Unit Tests for Layer 6 V2: CV Loader

Tests loading pre-split CV data from data/master-cv/:
- Metadata loading and parsing
- Role file loading
- Achievement and skill extraction
- Filtering by competency and industry
- Edge cases and error handling
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from src.layer6_v2.cv_loader import CVLoader, RoleData, CandidateData


# ===== FIXTURES =====

@pytest.fixture
def sample_metadata():
    """Sample role_metadata.json content."""
    return {
        "candidate": {
            "name": "Test Candidate",
            "title_base": "Engineering Leader / Software Architect",
            "contact": {
                "email": "test@example.com",
                "phone": "+1 555 123 4567",
                "linkedin": "linkedin.com/in/test",
                "location": "Test City, Country"
            },
            "languages": ["English (Native)", "German (B2)"],
            "education": {
                "masters": "M.Sc. Computer Science — Test University",
                "bachelors": "B.Sc. Software Engineering — Test Institute"
            },
            "certifications": ["AWS Certified", "K8s Admin"],
            "years_experience": 10
        },
        "roles": [
            {
                "id": "01_current_company",
                "company": "Current Company",
                "title": "Technical Lead",
                "location": "Munich, DE",
                "period": "2020–Present",
                "start_year": 2020,
                "end_year": None,
                "is_current": True,
                "duration_years": 4,
                "file": "roles/01_current_company.md",
                "industry": "AdTech",
                "team_size": "10+",
                "primary_competencies": ["leadership", "architecture"],
                "keywords": ["AWS", "DDD", "microservices"]
            },
            {
                "id": "02_previous_company",
                "company": "Previous Company",
                "title": "Senior Engineer",
                "location": "Berlin, DE",
                "period": "2018–2020",
                "start_year": 2018,
                "end_year": 2020,
                "is_current": False,
                "duration_years": 2,
                "file": "roles/02_previous_company.md",
                "industry": "SaaS",
                "team_size": "5",
                "primary_competencies": ["delivery", "process"],
                "keywords": ["Python", "Flask", "PostgreSQL"]
            }
        ]
    }


@pytest.fixture
def sample_role_content_current():
    """Sample role file content for current role."""
    return """# Current Company

**Role**: Technical Lead
**Location**: Munich, DE
**Period**: 2020–Present
**Is Current**: true

## Achievements

• Led team of 10 engineers to deliver critical platform migration
• Reduced incident rate by 75% through architectural improvements
• Implemented observability pipeline processing 1B events daily
• Mentored 5 senior engineers, promoting 2 to lead positions

## Skills

**Hard Skills**: Python, AWS, Kubernetes, DDD, microservices

**Soft Skills**: Leadership, Mentoring, Communication
"""


@pytest.fixture
def sample_role_content_previous():
    """Sample role file content for previous role."""
    return """# Previous Company

**Role**: Senior Engineer
**Location**: Berlin, DE
**Period**: 2018–2020
**Is Current**: false

## Achievements

• Built REST API serving 10M requests/day
• Improved test coverage from 40% to 85%
• Reduced deployment time by 80%

## Skills

**Hard Skills**: Python, Flask, PostgreSQL, Docker

**Soft Skills**: Agile, Collaboration
"""


@pytest.fixture
def mock_data_path(tmp_path, sample_metadata, sample_role_content_current, sample_role_content_previous):
    """Create mock data directory with all files."""
    # Create directory structure
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()

    # Write metadata
    metadata_file = tmp_path / "role_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(sample_metadata, f)

    # Write role files
    current_role = roles_dir / "01_current_company.md"
    with open(current_role, "w") as f:
        f.write(sample_role_content_current)

    previous_role = roles_dir / "02_previous_company.md"
    with open(previous_role, "w") as f:
        f.write(sample_role_content_previous)

    return tmp_path


# ===== TESTS: Basic Loading =====

class TestCVLoaderLoading:
    """Test basic CV data loading."""

    def test_loads_candidate_data(self, mock_data_path):
        """Loads candidate profile correctly."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        assert candidate.name == "Test Candidate"
        assert candidate.title_base == "Engineering Leader / Software Architect"
        assert candidate.email == "test@example.com"
        assert candidate.years_experience == 10
        assert len(candidate.languages) == 2

    def test_loads_all_roles(self, mock_data_path):
        """Loads all roles from metadata."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        assert len(candidate.roles) == 2
        assert candidate.roles[0].company == "Current Company"
        assert candidate.roles[1].company == "Previous Company"

    def test_loads_role_achievements(self, mock_data_path):
        """Parses achievements from role files."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        # Current role has 4 achievements
        assert len(candidate.roles[0].achievements) == 4
        assert "Led team of 10 engineers" in candidate.roles[0].achievements[0]

        # Previous role has 3 achievements
        assert len(candidate.roles[1].achievements) == 3

    def test_loads_role_skills(self, mock_data_path):
        """Parses skills from role files."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        # Check hard skills
        assert "Python" in candidate.roles[0].hard_skills
        assert "AWS" in candidate.roles[0].hard_skills

        # Check soft skills
        assert "Leadership" in candidate.roles[0].soft_skills

    def test_caches_loaded_data(self, mock_data_path):
        """Loads data only once and caches."""
        loader = CVLoader(data_path=mock_data_path)

        candidate1 = loader.load()
        candidate2 = loader.load()

        assert candidate1 is candidate2


# ===== TESTS: Role Metadata =====

class TestRoleMetadata:
    """Test role metadata is correctly loaded."""

    def test_role_dates(self, mock_data_path):
        """Role dates are parsed correctly."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        current = candidate.roles[0]
        assert current.start_year == 2020
        assert current.end_year is None
        assert current.is_current is True

        previous = candidate.roles[1]
        assert previous.start_year == 2018
        assert previous.end_year == 2020
        assert previous.is_current is False

    def test_role_competencies(self, mock_data_path):
        """Primary competencies are loaded."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        assert "leadership" in candidate.roles[0].primary_competencies
        assert "architecture" in candidate.roles[0].primary_competencies
        assert "delivery" in candidate.roles[1].primary_competencies

    def test_role_keywords(self, mock_data_path):
        """Keywords are loaded for each role."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        assert "AWS" in candidate.roles[0].keywords
        assert "Python" in candidate.roles[1].keywords


# ===== TESTS: Filtering =====

class TestCVLoaderFiltering:
    """Test filtering methods."""

    def test_filter_by_competency(self, mock_data_path):
        """Filters roles by primary competency."""
        loader = CVLoader(data_path=mock_data_path)

        leadership_roles = loader.filter_by_competency("leadership")
        assert len(leadership_roles) == 1
        assert leadership_roles[0].company == "Current Company"

        delivery_roles = loader.filter_by_competency("delivery")
        assert len(delivery_roles) == 1
        assert delivery_roles[0].company == "Previous Company"

    def test_filter_by_industry(self, mock_data_path):
        """Filters roles by industry."""
        loader = CVLoader(data_path=mock_data_path)

        adtech_roles = loader.filter_by_industry("AdTech")
        assert len(adtech_roles) == 1
        assert adtech_roles[0].company == "Current Company"

        saas_roles = loader.filter_by_industry("saas")  # Case insensitive
        assert len(saas_roles) == 1

    def test_get_current_role(self, mock_data_path):
        """Gets the current role correctly."""
        loader = CVLoader(data_path=mock_data_path)

        current = loader.get_current_role()
        assert current is not None
        assert current.company == "Current Company"
        assert current.is_current is True

    def test_get_all_keywords(self, mock_data_path):
        """Gets deduplicated keywords from all roles."""
        loader = CVLoader(data_path=mock_data_path)

        keywords = loader.get_all_keywords()
        assert "AWS" in keywords
        assert "Python" in keywords
        # Should be deduplicated and sorted
        assert keywords == sorted(set(keywords))

    def test_get_total_bullets(self, mock_data_path):
        """Gets total bullet count across all roles."""
        loader = CVLoader(data_path=mock_data_path)

        total = loader.get_total_bullets()
        assert total == 7  # 4 + 3


# ===== TESTS: Error Handling =====

class TestCVLoaderErrors:
    """Test error handling."""

    def test_missing_metadata_raises(self, tmp_path):
        """Raises error if metadata file missing."""
        loader = CVLoader(data_path=tmp_path)

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load()

        assert "role_metadata.json" in str(exc_info.value)

    def test_missing_role_file_raises(self, tmp_path, sample_metadata):
        """Raises error if role file missing."""
        # Create metadata but no role files
        metadata_file = tmp_path / "role_metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(sample_metadata, f)

        loader = CVLoader(data_path=tmp_path)

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load()

        assert "01_current_company.md" in str(exc_info.value)


# ===== TESTS: Data Conversion =====

class TestDataConversion:
    """Test data conversion to dict."""

    def test_role_to_dict(self, mock_data_path):
        """RoleData converts to dict correctly."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        role_dict = candidate.roles[0].to_dict()

        assert role_dict["company"] == "Current Company"
        assert role_dict["is_current"] is True
        assert len(role_dict["achievements"]) == 4
        assert "Python" in role_dict["hard_skills"]

    def test_candidate_to_dict(self, mock_data_path):
        """CandidateData converts to dict correctly."""
        loader = CVLoader(data_path=mock_data_path)
        candidate = loader.load()

        candidate_dict = candidate.to_dict()

        assert candidate_dict["name"] == "Test Candidate"
        assert len(candidate_dict["roles"]) == 2
        assert candidate_dict["roles"][0]["company"] == "Current Company"


# ===== TESTS: Integration with Real Data =====

class TestRealDataIntegration:
    """Test with actual data/master-cv/ files."""

    def test_loads_real_master_cv(self):
        """Loads the actual master CV data."""
        loader = CVLoader()

        # Skip if real data doesn't exist (CI environment)
        if not loader.metadata_path.exists():
            pytest.skip("Real master-cv data not available")

        candidate = loader.load()

        # Verify expected structure
        assert candidate.name == "Taimoor Alam"
        assert len(candidate.roles) == 6

        # Verify first role (Seven.One)
        current = loader.get_current_role()
        assert current.company == "Seven.One Entertainment Group"
        assert len(current.achievements) >= 30  # Has many bullets

        # Verify total bullets
        total = loader.get_total_bullets()
        assert total >= 60  # Should have plenty of bullets

    def test_real_data_filtering(self):
        """Tests filtering on real data."""
        loader = CVLoader()

        if not loader.metadata_path.exists():
            pytest.skip("Real master-cv data not available")

        # Filter by leadership competency
        leadership_roles = loader.filter_by_competency("leadership")
        assert len(leadership_roles) >= 1

        # Get all keywords
        keywords = loader.get_all_keywords()
        assert "AWS" in keywords
        assert "DDD" in keywords
