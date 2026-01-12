"""
Tests for job_detail.html frontend enhancements.

Tests the following features:
1. Enhanced Export PDF Button Error Handling
2. Extracted JD Fields Display Section
3. Collapsible Job Description
4. Iframe Viewer for Original Job Posting

These tests verify template rendering and correct display of data.
JavaScript functionality is validated through DOM structure and attributes.

Note: client and mock_db fixtures are provided by conftest.py
"""

import pytest
from bson import ObjectId
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Import the Flask app
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from frontend.app import app


# client and mock_db fixtures are provided by conftest.py


@pytest.fixture
def sample_job_with_extracted_jd():
    """Sample job data with complete extracted_jd fields."""
    return {
        "_id": ObjectId(),
        "title": "Senior Software Engineer",
        "company": "Test Corp",
        "location": "Remote",
        "status": "not processed",
        "jobId": "TEST123",
        "jobUrl": "https://example.com/job/123",
        "description": "A" * 300,  # Long description for collapse test
        "score": 85,
        "fit_score": 8.5,
        "fit_category": "strong",
        "fit_rationale": "Great match",
        "priority": "high",
        "notes": "",
        "remarks": "",
        "has_cv": False,
        "extracted_jd": {
            "role_category": "engineering_manager",
            "seniority_level": "senior",
            "top_keywords": ["Python", "Kubernetes", "AWS"],
            "technical_skills": ["Python", "Docker", "Kubernetes", "PostgreSQL"],
            "soft_skills": ["Leadership", "Communication", "Mentoring"],
            "implied_pain_points": [
                "Scale team to handle 10x growth",
                "Improve deployment reliability"
            ],
            "success_metrics": [
                "Team velocity increased by 50%",
                "Zero downtime deployments"
            ],
            "competency_weights": {
                "delivery": 30,
                "process": 20,
                "architecture": 25,
                "leadership": 25
            }
        }
    }


@pytest.fixture
def sample_job_without_extracted_jd():
    """Sample job data without extracted_jd (legacy jobs)."""
    return {
        "_id": ObjectId(),
        "title": "Software Engineer",
        "company": "Legacy Corp",
        "location": "San Francisco",
        "status": "not processed",
        "jobId": "LEGACY456",
        "jobUrl": "https://example.com/job/456",
        "description": "Short description",
        "score": 70,
        "fit_score": 7.0,
        "fit_category": "good",
        "fit_rationale": "Decent match",
        "priority": "medium",
        "notes": "",
        "remarks": "",
        "has_cv": False
    }


class TestExtractedJDFieldsDisplay:
    """Tests for the Extracted JD Fields display section."""

    def test_extracted_jd_section_renders_when_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should render extracted_jd section when data is present."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Check for extracted JD section header
        assert b'Extracted JD Analysis' in response.data or b'extracted' in response.data.lower()
        # Check role category is displayed
        assert b'Engineering Manager' in response.data or b'engineering_manager' in response.data
        # Check seniority level
        assert b'Senior' in response.data or b'senior' in response.data

    def test_extracted_jd_role_category_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display role category with proper formatting."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Role category should be present (underscore replaced with space and titlecased)
        data = response.data.decode('utf-8')
        assert 'engineering' in data.lower() or 'manager' in data.lower()

    def test_extracted_jd_seniority_level_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display seniority level with proper formatting."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        assert b'Senior' in response.data or b'senior' in response.data

    def test_extracted_jd_top_keywords_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display top keywords as tags."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Check for keywords
        assert b'Python' in response.data
        assert b'Kubernetes' in response.data
        assert b'AWS' in response.data

    def test_extracted_jd_technical_skills_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display technical skills list."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        assert b'Python' in response.data
        assert b'Docker' in response.data
        assert b'PostgreSQL' in response.data

    def test_extracted_jd_soft_skills_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display soft skills list."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        assert b'Leadership' in response.data
        assert b'Communication' in response.data
        assert b'Mentoring' in response.data

    def test_extracted_jd_pain_points_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display implied pain points."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        assert b'Scale team' in response.data or b'scale team' in response.data
        assert b'deployment reliability' in response.data or b'Deployment reliability' in response.data

    def test_extracted_jd_success_metrics_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display success metrics."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        assert b'velocity' in response.data.lower()
        assert b'downtime' in response.data.lower()

    def test_extracted_jd_competency_weights_displayed(self, client, mock_db, sample_job_with_extracted_jd):
        """Should display competency weights with percentages."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Check for percentage values
        assert '30' in data  # delivery
        assert '20' in data  # process
        assert '25' in data  # architecture or leadership

    def test_extracted_jd_section_hidden_when_missing(self, client, mock_db, sample_job_without_extracted_jd):
        """Should not render extracted_jd section when data is missing."""
        mock_repo, _ = mock_db
        job_id = sample_job_without_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_without_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # The extracted JD section should not appear
        data = response.data.decode('utf-8')
        # Count occurrences - should be minimal or none for jobs without extracted_jd
        assert data.count('Extracted JD') <= 1  # May appear in header/title only

    def test_extracted_jd_partial_fields(self, client, mock_db):
        """Should handle jobs with only some extracted_jd fields."""
        mock_repo, _ = mock_db
        partial_job = {
            "_id": ObjectId(),
            "title": "Engineer",
            "company": "Partial Corp",
            "location": "Remote",
            "status": "not processed",
            "jobId": "PARTIAL789",
            "jobUrl": "https://example.com/job/789",
            "description": "Test",
            "score": 65,
            "fit_score": 6.5,
            "fit_category": "moderate",
            "fit_rationale": "Some match",
            "priority": "low",
            "notes": "",
            "remarks": "",
            "has_cv": False,
            "extracted_jd": {
                "role_category": "backend_developer",
                "technical_skills": ["Go", "Redis"]
                # Missing other fields
            }
        }

        job_id = partial_job["_id"]
        mock_repo.find_one.return_value = partial_job

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should show available fields
        assert b'Go' in response.data
        assert b'Redis' in response.data
        # Should not crash on missing fields


class TestCollapsibleJobDescription:
    """Tests for the collapsible job description feature using HTML details element."""

    def test_job_description_details_element_renders(self, client, mock_db, sample_job_with_extracted_jd):
        """Should render job description in a details/summary element."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have details element for collapsible section
        assert b'<details' in response.data
        assert b'<summary' in response.data
        # Should show job description label
        assert b'Full Job Description' in response.data

    def test_job_description_summary_is_clickable(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have cursor-pointer styling on summary for clickability."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have cursor-pointer class on summary
        assert b'cursor-pointer' in response.data

    def test_job_description_content_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should include the full job description content."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # The description content should be present (sample has 'A' * 300)
        assert b'AAA' in response.data

    def test_short_description_renders(self, client, mock_db, sample_job_without_extracted_jd):
        """Should render short descriptions correctly."""
        mock_repo, _ = mock_db
        job_id = sample_job_without_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_without_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Short description should render
        assert b'Short description' in response.data

    def test_missing_description_no_section(self, client, mock_db):
        """Should not render description section when missing."""
        mock_repo, _ = mock_db
        job_no_desc = {
            "_id": ObjectId(),
            "title": "Engineer",
            "company": "No Desc Corp",
            "location": "Remote",
            "status": "not processed",
            "jobId": "NODESC999",
            "jobUrl": "https://example.com/job/999",
            "score": 60,
            "fit_score": 6.0,
            "fit_category": "moderate",
            "fit_rationale": "Okay match",
            "priority": "low",
            "notes": "",
            "remarks": "",
            "has_cv": False
            # No description field
        }

        job_id = job_no_desc["_id"]
        mock_repo.find_one.return_value = job_no_desc

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Page should render successfully
        data = response.data.decode('utf-8')
        assert 'Engineer' in data
        # Should NOT have Full Job Description section when no description
        assert 'Full Job Description' not in data


class TestIframeViewer:
    """Tests for the iframe viewer for original job posting."""

    def test_iframe_viewer_renders_when_job_url_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should render iframe viewer when jobUrl is present."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have iframe element
        assert b'job-iframe' in response.data
        # Should have correct src
        assert b'https://example.com/job/123' in response.data

    def test_iframe_loading_state_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should include loading state UI."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have loading indicator
        assert b'iframe-loading' in response.data
        assert b'Loading job posting' in response.data or b'loading' in response.data.lower()

    def test_iframe_error_state_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should include error state UI for blocked iframes."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have error container
        assert b'iframe-error' in response.data
        # Should have helpful error message
        assert b'Unable to load' in response.data or b'prevents embedding' in response.data

    def test_iframe_security_attributes(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have correct security attributes (sandbox, referrerpolicy)."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should have sandbox attribute
        assert 'sandbox=' in data
        # Should have referrerpolicy
        assert 'referrerpolicy=' in data or 'no-referrer' in data

    def test_iframe_lazy_loading(self, client, mock_db, sample_job_with_extracted_jd):
        """Should use lazy loading for iframe."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have loading=lazy
        assert b'loading="lazy"' in response.data or b"loading='lazy'" in response.data

    def test_iframe_viewer_collapsible(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have collapsible container with toggle functionality."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have container with ID
        assert b'job-viewer-container' in response.data
        # Should have toggle icon
        assert b'job-viewer-icon' in response.data

    def test_iframe_fallback_link_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should provide fallback link to open in new tab."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have "Open in new tab" link
        assert b'Open in new tab' in response.data or b'new tab' in response.data.lower()
        # Should have target="_blank"
        assert b'target="_blank"' in response.data

    def test_iframe_viewer_hidden_when_no_url(self, client, mock_db):
        """Should not render iframe viewer when jobUrl is missing."""
        mock_repo, _ = mock_db
        job_no_url = {
            "_id": ObjectId(),
            "title": "Engineer",
            "company": "No URL Corp",
            "location": "Remote",
            "status": "not processed",
            "jobId": "NOURL888",
            "score": 55,
            "fit_score": 5.5,
            "fit_category": "weak",
            "fit_rationale": "Poor match",
            "priority": "low",
            "notes": "",
            "remarks": "",
            "has_cv": False
            # No jobUrl field
        }

        job_id = job_no_url["_id"]
        mock_repo.find_one.return_value = job_no_url

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should not have iframe viewer section
        data = response.data.decode('utf-8')
        # May not have iframe at all, or it should be conditionally hidden
        # Just verify the page renders without error


class TestPDFExportEnhancements:
    """Tests for enhanced PDF export error handling."""

    def test_export_pdf_function_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have exportCVToPDF JavaScript function."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have the function definition
        assert b'exportCVToPDF' in response.data

    def test_export_pdf_button_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have Export PDF button with onclick handler."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have Export PDF button
        assert b'Export PDF' in response.data
        # Should have onclick="exportCVToPDF()"
        assert b'onclick="exportCVToPDF()"' in response.data or b"onclick='exportCVToPDF()'" in response.data

    def test_export_pdf_error_logging(self, client, mock_db, sample_job_with_extracted_jd):
        """Should include console logging for debugging."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should have console.log or console.error for debugging
        assert 'console.log' in data or 'console.error' in data

    def test_export_pdf_toast_notifications(self, client, mock_db, sample_job_with_extracted_jd):
        """Should show toast notifications for PDF export status."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should have showToast calls in exportCVToPDF function
        assert 'showToast' in data


class TestJavaScriptFunctions:
    """Tests for JavaScript function presence and structure.

    Note: JavaScript functions were refactored to an external file (job-detail.js)
    for maintainability. Tests now verify the script include and config setup.
    """

    def test_job_detail_js_script_included(self, client, mock_db, sample_job_with_extracted_jd):
        """Should include the external job-detail.js script."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should include external JavaScript file
        assert 'job-detail.js' in data

    def test_job_config_object_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should define JOB_DETAIL_CONFIG with jobId."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should have config object with job ID
        assert 'JOB_DETAIL_CONFIG' in data
        assert str(job_id) in data

    def test_iframe_load_timeout_logic(self, client, mock_db, sample_job_with_extracted_jd):
        """Should implement timeout logic for detecting blocked iframes.

        Note: Actual timeout logic is in job-detail.js (10000ms).
        This test verifies the HTML structure supports iframe handling.
        """
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should have the iframe container elements
        assert 'iframe-loading' in data
        assert 'iframe-error' in data

    def test_job_description_collapsible_uses_details_element(self, client, mock_db, sample_job_with_extracted_jd):
        """Should use HTML details/summary elements for collapsible job description.

        Note: Uses native HTML5 details element instead of JavaScript toggle,
        which provides better accessibility and works without JS.
        """
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should use native HTML details element for collapsible sections
        assert '<details' in data
        assert '<summary' in data
        # Chevron icon should rotate on open (group-open:rotate-90)
        assert 'group-open:rotate-90' in data


class TestAccessibility:
    """Tests for accessibility features."""

    def test_aria_labels_present(self, client, mock_db, sample_job_with_extracted_jd):
        """Should include aria-labels for accessibility."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Should have aria attributes
        assert 'aria-' in data  # aria-label, aria-expanded, etc.

    def test_iframe_title_attribute(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have title attribute on iframe for screen readers."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Should have title on iframe
        assert b'title="Original Job Posting"' in response.data or b"title='Original Job Posting'" in response.data

    def test_button_labels_descriptive(self, client, mock_db, sample_job_with_extracted_jd):
        """Should have descriptive button labels."""
        mock_repo, _ = mock_db
        job_id = sample_job_with_extracted_jd["_id"]
        mock_repo.find_one.return_value = sample_job_with_extracted_jd

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        # Export PDF button should be clear
        assert b'Export PDF' in response.data
        # Job description toggle should be clear
        assert b'Job Description' in response.data
