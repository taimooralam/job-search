"""
Unit tests for Layer 2: Pain-Point Miner

Tests JSON parsing, schema validation, and error handling with mocked LLM responses.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError

from src.layer2.pain_point_miner import (
    PainPointMiner,
    PainPointAnalysis,
    pain_point_miner_node
)
from src.common.state import JobState


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState for testing."""
    return {
        "job_id": "test123",
        "title": "Senior Software Engineer",
        "company": "Test Corp",
        "job_description": "Build amazing software with Python and distributed systems...",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "pain_points": None,
        "strategic_needs": None,
        "risks_if_unfilled": None,
        "success_metrics": None,
        "selected_stars": None,
        "star_to_pain_mapping": None,
        "company_summary": None,
        "company_url": None,
        "fit_score": None,
        "fit_rationale": None,
        "people": None,
        "cover_letter": None,
        "cv_path": None,
        "drive_folder_url": None,
        "sheet_row_id": None,
        "run_id": None,
        "created_at": None,
        "errors": [],
        "status": "processing"
    }


@pytest.fixture
def valid_pain_point_json():
    """Valid pain-point analysis JSON matching schema."""
    return {
        "pain_points": [
            "Modernize legacy monolith to microservices",
            "Scale infrastructure to handle 10x traffic growth",
            "Reduce incident response time from hours to minutes"
        ],
        "strategic_needs": [
            "Enable rapid feature delivery for competitive advantage",
            "Build technical foundation for international expansion",
            "Attract and retain top engineering talent"
        ],
        "risks_if_unfilled": [
            "Critical customer-facing incidents continue",
            "Inability to meet Q2 scalability targets"
        ],
        "success_metrics": [
            "95% reduction in production incidents within 6 months",
            "Deploy new features 3x faster",
            "Zero downtime during traffic spikes"
        ]
    }


@pytest.fixture
def minimal_valid_json():
    """Minimal valid JSON (minimum counts)."""
    return {
        "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
        "strategic_needs": ["Need 1", "Need 2", "Need 3"],
        "risks_if_unfilled": ["Risk 1", "Risk 2"],
        "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
    }


# ===== SCHEMA VALIDATION TESTS =====

class TestPainPointAnalysisSchema:
    """Test Pydantic schema validation."""

    def test_valid_schema(self, valid_pain_point_json):
        """Valid JSON should pass schema validation."""
        validated = PainPointAnalysis(**valid_pain_point_json)
        assert len(validated.pain_points) == 3
        assert len(validated.strategic_needs) == 3
        assert len(validated.risks_if_unfilled) == 2
        assert len(validated.success_metrics) == 3

    def test_minimal_valid_counts(self, minimal_valid_json):
        """Minimal counts (3, 3, 2, 3) should pass."""
        validated = PainPointAnalysis(**minimal_valid_json)
        assert validated.pain_points == minimal_valid_json["pain_points"]

    def test_missing_required_field(self):
        """Missing required field should raise ValidationError."""
        invalid = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            # Missing risks_if_unfilled
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('risks_if_unfilled',) for e in errors)

    def test_too_few_pain_points(self):
        """Empty pain points list should fail validation."""
        invalid = {
            "pain_points": [],  # Empty list is not allowed
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

        errors = exc_info.value.errors()
        assert any(
            e['loc'] == ('pain_points',) and 'at least 1 item' in e['msg'].lower()
            for e in errors
        )

    def test_too_many_strategic_needs(self):
        """Too many strategic needs (> 8) should fail."""
        invalid = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            "strategic_needs": [f"Need {i}" for i in range(1, 11)],  # 10 items, max 8
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

        errors = exc_info.value.errors()
        assert any(
            e['loc'] == ('strategic_needs',) and 'at most 8 items' in e['msg'].lower()
            for e in errors
        )

    def test_empty_string_in_array(self):
        """Empty strings should fail validation."""
        invalid = {
            "pain_points": ["Pain 1", "", "Pain 3"],  # Empty string
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

    def test_wrong_type_for_field(self):
        """Non-list type should fail."""
        invalid = {
            "pain_points": "Not a list",  # Should be list
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError):
            PainPointAnalysis(**invalid)


# ===== PAIN POINT MINER TESTS =====

class TestPainPointMinerParsing:
    """Test JSON parsing logic."""

    def test_parse_clean_json(self, valid_pain_point_json):
        """Parse clean JSON response."""
        miner = PainPointMiner()
        llm_response = json.dumps(valid_pain_point_json)

        result = miner._parse_json_response(llm_response)

        assert result["pain_points"] == valid_pain_point_json["pain_points"]
        assert result["strategic_needs"] == valid_pain_point_json["strategic_needs"]
        assert len(result["risks_if_unfilled"]) == 2

    def test_parse_json_with_extra_text_before(self, valid_pain_point_json):
        """Parse JSON even if LLM adds text before."""
        miner = PainPointMiner()
        llm_response = "Here's the analysis:\n\n" + json.dumps(valid_pain_point_json)

        result = miner._parse_json_response(llm_response)

        assert len(result["pain_points"]) == 3

    def test_parse_json_with_extra_text_after(self, valid_pain_point_json):
        """Parse JSON even if LLM adds text after."""
        miner = PainPointMiner()
        llm_response = json.dumps(valid_pain_point_json) + "\n\nHope this helps!"

        result = miner._parse_json_response(llm_response)

        assert len(result["pain_points"]) == 3

    def test_parse_invalid_json(self):
        """Invalid JSON should raise ValueError."""
        miner = PainPointMiner()
        llm_response = "Not JSON at all!"

        with pytest.raises(ValueError, match="Failed to parse JSON"):
            miner._parse_json_response(llm_response)

    def test_parse_json_missing_field(self):
        """JSON missing required field should raise ValueError with clear message."""
        miner = PainPointMiner()
        invalid_json = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            # Missing other required fields
        }
        llm_response = json.dumps(invalid_json)

        with pytest.raises(ValueError, match="JSON schema validation failed"):
            miner._parse_json_response(llm_response)

    def test_parse_json_too_few_items(self):
        """JSON with empty lists should raise clear validation error."""
        miner = PainPointMiner()
        invalid_json = {
            "pain_points": [],
            "strategic_needs": [],
            "risks_if_unfilled": [],
            "success_metrics": []
        }
        llm_response = json.dumps(invalid_json)

        with pytest.raises(ValueError, match="at least 1 item"):
            miner._parse_json_response(llm_response)


# ===== INTEGRATION TESTS WITH MOCKED LLM =====

class TestPainPointMinerWithMockedLLM:
    """Test full extraction flow with mocked LLM calls."""

    @patch('src.layer2.pain_point_miner.ChatOpenAI')
    def test_successful_extraction(self, mock_llm_class, sample_job_state, valid_pain_point_json):
        """Successful LLM call should return validated data."""
        # Mock LLM to return valid JSON
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(valid_pain_point_json)
        mock_llm_instance.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        assert result["pain_points"] == valid_pain_point_json["pain_points"]
        assert result["strategic_needs"] == valid_pain_point_json["strategic_needs"]
        assert "errors" not in result

    @patch('src.layer2.pain_point_miner.ChatOpenAI')
    def test_llm_returns_invalid_json(self, mock_llm_class, sample_job_state):
        """LLM returning invalid JSON should return empty lists with error."""
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Not valid JSON at all!"
        mock_llm_instance.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        # Should return empty lists (graceful degradation)
        assert result["pain_points"] == []
        assert result["strategic_needs"] == []
        assert result["risks_if_unfilled"] == []
        assert result["success_metrics"] == []

        # Should include error message
        assert len(result["errors"]) > 0
        assert "failed" in result["errors"][0].lower()

    @patch('src.layer2.pain_point_miner.ChatOpenAI')
    def test_llm_returns_incomplete_schema(self, mock_llm_class, sample_job_state):
        """LLM returning incomplete schema should return empty lists with error."""
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        incomplete_json = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            # Missing other fields
        }
        mock_response.content = json.dumps(incomplete_json)
        mock_llm_instance.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        assert result["pain_points"] == []
        assert len(result["errors"]) > 0
        assert "validation failed" in result["errors"][0].lower()


# ===== NODE FUNCTION TESTS =====

class TestPainPointMinerNode:
    """Test LangGraph node wrapper function."""

    @patch('src.layer2.pain_point_miner.ChatOpenAI')
    def test_node_returns_updates_dict(self, mock_llm_class, sample_job_state, valid_pain_point_json):
        """Node function should return dict with pain point updates."""
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(valid_pain_point_json)
        mock_llm_instance.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm_instance

        updates = pain_point_miner_node(sample_job_state)

        # Should return dict with all 4 fields
        assert "pain_points" in updates
        assert "strategic_needs" in updates
        assert "risks_if_unfilled" in updates
        assert "success_metrics" in updates
        assert len(updates["pain_points"]) == 3

    @patch('src.layer2.pain_point_miner.ChatOpenAI')
    def test_node_handles_errors_gracefully(self, mock_llm_class, sample_job_state):
        """Node function should handle errors without crashing."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.side_effect = Exception("LLM API error")
        mock_llm_class.return_value = mock_llm_instance

        updates = pain_point_miner_node(sample_job_state)

        # Should return empty lists, not crash
        assert updates["pain_points"] == []
        assert "errors" in updates
