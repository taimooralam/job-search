"""
Unit tests for Answer Generator Service.

Tests the AnswerGeneratorService which generates planned answers
for job application forms using LLM with job context.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestAnswerGeneratorServiceInit:
    """Tests for AnswerGeneratorService initialization."""

    def test_init_creates_service(self):
        """Service initializes without error."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()

        assert service is not None
        assert service.llm is None  # Lazy initialization


class TestStaticAnswers:
    """Tests for static answer generation."""

    def test_linkedin_url_returns_placeholder(self):
        """LinkedIn URL field returns placeholder."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        answer = service._get_static_answer("LinkedIn profile URL", {})

        assert answer == "[Your LinkedIn URL]"

    def test_portfolio_url_returns_placeholder(self):
        """Portfolio/website URL returns placeholder."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        answer = service._get_static_answer("Portfolio/Website URL", {})

        assert answer == "[Your Portfolio/Website URL]"

    def test_authorized_returns_yes(self):
        """Authorization question returns Yes."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        answer = service._get_static_answer(
            "Are you authorized to work in this location?", {}
        )

        assert answer == "Yes"

    def test_salary_returns_placeholder(self):
        """Salary question returns placeholder."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        answer = service._get_static_answer("What is your expected salary range?", {})

        assert answer == "[Your expected salary range]"

    def test_availability_returns_placeholder(self):
        """Availability question returns placeholder."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        answer = service._get_static_answer(
            "What is your availability/notice period?", {}
        )

        assert answer == "[Your availability/notice period]"

    def test_unknown_question_returns_none(self):
        """Unknown question returns None."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        answer = service._get_static_answer("Some random question", {})

        assert answer is None


class TestGenerateAnswers:
    """Tests for answer generation."""

    @patch("src.services.answer_generator_service.database_client")
    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_generate_answers_returns_list(self, mock_create_llm, mock_db):
        """generate_answers returns a list of planned answers."""
        from src.services.answer_generator_service import AnswerGeneratorService

        # Mock LLM response
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="This is a generated answer about the role."
        )
        mock_create_llm.return_value = mock_llm

        # Mock database
        mock_db.get_all_star_records.return_value = []

        service = AnswerGeneratorService()
        job = {
            "company": "TestCo",
            "title": "Software Engineer",
            "location": "Remote",
            "job_description": "We are looking for a Python developer.",
        }

        # Provide form_fields (required parameter)
        form_fields = [
            {"label": "Why this role?", "field_type": "textarea", "required": True},
            {"label": "LinkedIn", "field_type": "url", "required": False},
        ]

        answers = service.generate_answers(job, form_fields=form_fields)

        assert isinstance(answers, list)
        assert len(answers) > 0

        # Check answer structure
        for answer in answers:
            assert "question" in answer
            assert "answer" in answer
            assert "field_type" in answer
            assert "source" in answer
            assert answer["source"] == "auto_generated"

    def test_generate_answers_raises_without_form_fields(self):
        """generate_answers raises ValueError when form_fields not provided."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        job = {"company": "TestCo", "title": "Developer"}

        with pytest.raises(ValueError, match="form_fields is required"):
            service.generate_answers(job)

    @patch("src.services.answer_generator_service.database_client")
    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_generate_answers_uses_job_context(self, mock_create_llm, mock_db):
        """generate_answers includes job context in LLM prompt."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Generated answer.")
        mock_create_llm.return_value = mock_llm
        mock_db.get_all_star_records.return_value = []

        service = AnswerGeneratorService()
        job = {
            "company": "Acme Corp",
            "title": "Backend Developer",
            "pain_points": ["Need to scale infrastructure"],
            "strategic_needs": ["Improve system reliability"],
        }

        form_fields = [
            {"label": "Why this role?", "field_type": "textarea", "required": True},
        ]

        service.generate_answers(job, form_fields=form_fields)

        # LLM should be invoked
        assert mock_llm.invoke.called

        # Check that context is passed to LLM
        call_args = mock_llm.invoke.call_args[0][0]
        assert "Acme Corp" in call_args
        assert "Backend Developer" in call_args

    @patch("src.services.answer_generator_service.database_client")
    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_generate_answers_includes_star_records(self, mock_create_llm, mock_db):
        """generate_answers includes relevant STAR records in context."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Generated answer.")
        mock_create_llm.return_value = mock_llm

        # Mock STAR records
        mock_db.get_all_star_records.return_value = [
            {
                "id": "star-1",
                "role_title": "Senior Engineer",
                "condensed_version": "Built scalable system handling 1M requests/day",
            },
            {
                "id": "star-2",
                "role_title": "Tech Lead",
                "condensed_version": "Led team of 5 engineers to deliver project on time",
            },
        ]

        service = AnswerGeneratorService()
        job = {
            "company": "TestCo",
            "title": "Staff Engineer",
            "selected_star_ids": ["star-1"],
        }

        form_fields = [
            {"label": "Describe a challenging project", "field_type": "textarea", "required": True},
        ]

        service.generate_answers(job, form_fields=form_fields)

        # Check STAR records are in context
        call_args = mock_llm.invoke.call_args[0][0]
        assert "Senior Engineer" in call_args or "scalable system" in call_args

    @patch("src.services.answer_generator_service.database_client")
    def test_generate_answers_handles_llm_error(self, mock_db):
        """generate_answers handles LLM errors gracefully."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_db.get_all_star_records.return_value = []

        service = AnswerGeneratorService()

        # Mock LLM to raise an error
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM API error")
        service.llm = mock_llm

        job = {
            "company": "TestCo",
            "title": "Developer",
        }

        form_fields = [
            {"label": "Why this role?", "field_type": "textarea", "required": True},
        ]

        answers = service.generate_answers(job, form_fields=form_fields)

        # Should still return answers (with fallback text for errors)
        assert isinstance(answers, list)

        # Check that LLM-generated answers have fallback text
        for answer in answers:
            if answer["field_type"] == "textarea":
                assert "[Please provide your answer" in answer["answer"]

    @patch("src.services.answer_generator_service.database_client")
    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_generate_answers_skips_llm_for_url_fields(self, mock_create_llm, mock_db):
        """generate_answers does not call LLM for URL fields."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Generated answer.")
        mock_create_llm.return_value = mock_llm
        mock_db.get_all_star_records.return_value = []

        service = AnswerGeneratorService()
        job = {"company": "TestCo", "title": "Developer"}

        form_fields = [
            {"label": "LinkedIn profile URL", "field_type": "url", "required": False},
            {"label": "Portfolio/Website URL", "field_type": "url", "required": False},
        ]

        answers = service.generate_answers(job, form_fields=form_fields)

        # Find URL field answers
        url_answers = [a for a in answers if a["field_type"] == "url"]

        # URL answers should have placeholder text, not LLM generated
        for answer in url_answers:
            assert "[Your" in answer["answer"]

    def test_generate_answers_handles_empty_form_fields(self):
        """generate_answers returns empty list for empty form_fields."""
        from src.services.answer_generator_service import AnswerGeneratorService

        service = AnswerGeneratorService()
        job = {"company": "TestCo", "title": "Developer"}

        answers = service.generate_answers(job, form_fields=[])

        assert answers == []

    @patch("src.services.answer_generator_service.database_client")
    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_generate_answers_respects_char_limit(self, mock_create_llm, mock_db):
        """generate_answers passes char_limit to LLM prompt."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_llm = MagicMock()
        # Return a very long answer to test truncation
        mock_llm.invoke.return_value = MagicMock(content="x" * 1000)
        mock_create_llm.return_value = mock_llm
        mock_db.get_all_star_records.return_value = []

        service = AnswerGeneratorService()
        job = {"company": "TestCo", "title": "Developer"}

        form_fields = [
            {"label": "Short answer", "field_type": "textarea", "required": True, "limit": 100},
        ]

        answers = service.generate_answers(job, form_fields=form_fields)

        assert len(answers) == 1
        # Answer should be truncated to around the limit
        assert len(answers[0]["answer"]) <= 103  # Allow for "..."


class TestLazyLLMInit:
    """Tests for lazy LLM initialization."""

    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_llm_initialized_on_first_use(self, mock_create_llm):
        """LLM is initialized only when first needed."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        service = AnswerGeneratorService()

        # LLM should not be created yet
        assert service.llm is None
        mock_create_llm.assert_not_called()

        # Get LLM
        llm = service._get_llm()

        # Now it should be created
        assert llm is mock_llm
        mock_create_llm.assert_called_once()

    @patch("src.services.answer_generator_service.create_tracked_llm")
    def test_llm_reused_on_subsequent_calls(self, mock_create_llm):
        """LLM instance is reused on subsequent calls."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        service = AnswerGeneratorService()

        # Call _get_llm multiple times
        llm1 = service._get_llm()
        llm2 = service._get_llm()
        llm3 = service._get_llm()

        # Should only create once
        mock_create_llm.assert_called_once()
        assert llm1 is llm2 is llm3


class TestLoadStarRecords:
    """Tests for STAR record loading."""

    @patch("src.services.answer_generator_service.database_client")
    def test_load_star_records_from_database(self, mock_db):
        """STAR records are loaded from database."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_stars = [
            {"id": "star-1", "role_title": "Engineer"},
            {"id": "star-2", "role_title": "Manager"},
        ]
        mock_db.get_all_star_records.return_value = mock_stars

        service = AnswerGeneratorService()
        stars = service._load_star_records()

        assert stars == mock_stars
        mock_db.get_all_star_records.assert_called_once()

    @patch("src.services.answer_generator_service.database_client")
    def test_load_star_records_handles_error(self, mock_db):
        """STAR record loading handles errors gracefully."""
        from src.services.answer_generator_service import AnswerGeneratorService

        mock_db.get_all_star_records.side_effect = Exception("DB error")

        service = AnswerGeneratorService()
        stars = service._load_star_records()

        # Should return empty list on error
        assert stars == []
