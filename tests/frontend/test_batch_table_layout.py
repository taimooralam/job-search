"""
Unit tests for batch table layout fixes.

Tests the table layout improvements in batch_job_rows.html and batch_job_single_row.html:
1. Table has correct classes (w-full table-fixed)
2. Header columns have explicit width classes
3. Company cell has overflow handling and truncation
4. Long company names get title attribute for tooltip
5. Table structure is valid (thead, tbody, correct column count)

Coverage:
- Table class changes from min-w-full to w-full table-fixed
- Explicit column widths on all header columns
- Company cell overflow-hidden and truncate classes
- Title attribute on long company names
- Proper table structure validation
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from bson import ObjectId
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ===== FIXTURES =====

@pytest.fixture
def app():
    """Create Flask app instance for testing."""
    from frontend.app import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    return flask_app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Create authenticated Flask test client."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


@pytest.fixture
def sample_batch_jobs():
    """Sample batch jobs for testing table rendering."""
    now = datetime.utcnow()
    return [
        {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Backend Engineer",
            "company": "TechCorp",
            "status": "under processing",
            "batch_added_at": now,
            "createdAt": now,
            "score": 85,
        },
        {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "title": "Staff Software Engineer",
            "company": "A Very Long Company Name That Should Be Truncated In The Table",
            "status": "under processing",
            "batch_added_at": now,
            "createdAt": now,
            "score": 92,
        },
        {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "title": "Principal Engineer",
            "company": "Startup",
            "status": "under processing",
            "batch_added_at": now,
            "createdAt": now,
            "score": 88,
        },
    ]


# ===== TESTS: Table Structure and Classes =====

class TestBatchTableStructure:
    """Tests for batch_job_rows.html table structure and classes."""

    @patch("frontend.app.get_collection")
    def test_table_has_correct_fixed_layout_classes(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should render table with 'w-full table-fixed' classes."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Verify table has w-full and table-fixed classes
        assert 'class="w-full table-fixed theme-table"' in html
        # Should NOT have min-w-full (old class)
        assert 'min-w-full' not in html

    @patch("frontend.app.get_collection")
    def test_table_has_theme_table_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should include theme-table class for consistent styling."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert 'theme-table' in html

    @patch("frontend.app.get_collection")
    def test_table_has_valid_structure(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should have valid HTML table structure with thead and tbody."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Verify table structure
        assert '<table' in html
        assert '<thead' in html
        assert '<tbody' in html
        assert '</thead>' in html
        assert '</tbody>' in html
        assert '</table>' in html

    @patch("frontend.app.get_collection")
    def test_empty_table_has_correct_structure(
        self, mock_get_collection, authenticated_client
    ):
        """Should render valid table structure even when no jobs are present."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should still have table with thead
        assert '<table' in html
        assert 'class="w-full table-fixed theme-table"' in html
        assert '<thead' in html
        # Should have empty state message in tbody
        assert 'No jobs in batch queue' in html


# ===== TESTS: Header Column Widths =====

class TestBatchTableHeaderColumns:
    """Tests for explicit width classes on header columns."""

    @patch("frontend.app.get_collection")
    def test_expand_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on expand toggle column (w-8)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # First column (expand) should have w-8
        # Looking for: <th scope="col" class="px-2 py-3 w-8"></th>
        assert 'w-8' in html

    @patch("frontend.app.get_collection")
    def test_checkbox_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on checkbox column (w-10)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Checkbox column should have w-10
        assert 'w-10' in html

    @patch("frontend.app.get_collection")
    def test_company_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on company column (w-[14%])."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Company column should have w-[14%]
        assert 'w-[14%]' in html

    @patch("frontend.app.get_collection")
    def test_role_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on role column (w-[18%])."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Role column should have w-[18%]
        assert 'w-[18%]' in html

    @patch("frontend.app.get_collection")
    def test_score_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on score column (w-16)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Score column should have w-16
        assert 'w-16' in html

    @patch("frontend.app.get_collection")
    def test_added_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on batch_added_at column (w-24)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Added column should have w-24
        assert 'w-24' in html

    @patch("frontend.app.get_collection")
    def test_status_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on status column (w-32)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Status column should have w-32
        assert 'w-32' in html

    @patch("frontend.app.get_collection")
    def test_progress_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on progress indicators column (w-20)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Progress column should have w-20
        assert 'w-20' in html

    @patch("frontend.app.get_collection")
    def test_pipeline_column_has_width_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should set explicit width on pipeline status column (w-24)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Pipeline column should have w-24 (appears twice in template)
        assert html.count('w-24') >= 2


# ===== TESTS: Company Cell Overflow and Truncation =====

class TestBatchTableCompanyCell:
    """Tests for company cell overflow handling and truncation."""

    @patch("frontend.app.get_collection")
    def test_company_cell_has_overflow_hidden(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should apply overflow-hidden to company cell."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Company cell should have overflow-hidden class
        assert 'overflow-hidden' in html

    @patch("frontend.app.get_collection")
    def test_company_cell_has_truncate_class(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should apply truncate class to company text."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Company div should have truncate class
        assert 'truncate' in html

    @patch("frontend.app.get_collection")
    def test_company_cell_has_title_attribute(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should add title attribute to company cell for tooltip."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should have title attributes with company names
        assert 'title="TechCorp"' in html
        assert 'title="A Very Long Company Name That Should Be Truncated In The Table"' in html
        assert 'title="Startup"' in html

    @patch("frontend.app.get_collection")
    def test_long_company_name_gets_truncated_visually(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should display long company names with truncate class and full name in title."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        long_name_job = sample_batch_jobs[1]  # Has very long company name
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [long_name_job]
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        long_company_name = "A Very Long Company Name That Should Be Truncated In The Table"

        # Should have full name in title attribute
        assert f'title="{long_company_name}"' in html

        # Should have company name in content (will be truncated by CSS)
        assert long_company_name in html

        # Should have truncate class
        assert 'truncate' in html

    @patch("frontend.app.get_collection")
    def test_company_cell_handles_missing_company_name(
        self, mock_get_collection, authenticated_client
    ):
        """Should handle jobs with missing company name gracefully."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job_no_company = {
            "_id": ObjectId("507f1f77bcf86cd799439014"),
            "title": "Software Engineer",
            # No company field
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 75,
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_no_company]
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should show "-" for missing company
        assert 'title="-"' in html or '>-<' in html

    @patch("frontend.app.get_collection")
    def test_company_cell_preserves_whitespace_nowrap(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should have whitespace-nowrap on company cell to prevent wrapping."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Company cell should have whitespace-nowrap
        assert 'whitespace-nowrap' in html


# ===== TESTS: Single Row Partial =====

class TestBatchSingleRowCompanyCell:
    """Tests for company cell in batch_job_single_row.html partial."""

    @patch("frontend.app.get_collection")
    def test_single_row_company_cell_has_overflow_handling(
        self, mock_get_collection, authenticated_client
    ):
        """Should apply overflow-hidden and truncate to company cell in single row."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Engineer",
            "company": "Very Long Company Name That Needs Truncation",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 85,
        }

        mock_collection.find_one.return_value = job

        # Act
        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should have overflow-hidden and truncate
        assert 'overflow-hidden' in html
        assert 'truncate' in html

    @patch("frontend.app.get_collection")
    def test_single_row_company_cell_has_title_attribute(
        self, mock_get_collection, authenticated_client
    ):
        """Should add title attribute to company cell in single row for tooltip."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "title": "Staff Engineer",
            "company": "TechCorp International",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 90,
        }

        mock_collection.find_one.return_value = job

        # Act
        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439012")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should have title attribute with company name
        assert 'title="TechCorp International"' in html

    @patch("frontend.app.get_collection")
    def test_single_row_handles_missing_company(
        self, mock_get_collection, authenticated_client
    ):
        """Should show '-' when company field is missing in single row."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "title": "DevOps Engineer",
            # No company field
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 80,
        }

        mock_collection.find_one.return_value = job

        # Act
        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439013")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should show "-" for missing company
        assert 'title="-"' in html or '>-<' in html


# ===== TESTS: Column Count Consistency =====

class TestBatchTableColumnCount:
    """Tests to ensure consistent column count across header and rows."""

    @patch("frontend.app.get_collection")
    def test_header_has_correct_column_count(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should have 9 header columns (expand, checkbox, company, role, score, added, status, progress, pipeline, actions)."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Count <th> elements in thead
        # Expected columns: expand, checkbox, company, role, score, added, status, progress, pipeline, actions
        # Total: 10 columns
        th_count = html.count('<th scope="col"')
        assert th_count == 10, f"Expected 10 header columns, found {th_count}"

    @patch("frontend.app.get_collection")
    def test_empty_state_colspan_matches_column_count(
        self, mock_get_collection, authenticated_client
    ):
        """Should have correct colspan on empty state message."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Empty state should span all 10 columns
        assert 'colspan="10"' in html


# ===== EDGE CASES =====

class TestBatchTableEdgeCases:
    """Edge case tests for batch table rendering."""

    @patch("frontend.app.get_collection")
    def test_handles_special_characters_in_company_name(
        self, mock_get_collection, authenticated_client
    ):
        """Should properly escape special characters in company name."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job_special_chars = {
            "_id": ObjectId("507f1f77bcf86cd799439015"),
            "title": "Engineer",
            "company": 'Company "Quotes" & <Tags>',
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 75,
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_special_chars]
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # HTML should be properly escaped
        # Jinja2 auto-escapes by default, so we expect escaped output
        assert 'Company &quot;Quotes&quot; &amp; &lt;Tags&gt;' in html or \
               'Company &#34;Quotes&#34; &amp; &lt;Tags&gt;' in html

    @patch("frontend.app.get_collection")
    def test_handles_unicode_in_company_name(
        self, mock_get_collection, authenticated_client
    ):
        """Should properly handle unicode characters in company name."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job_unicode = {
            "_id": ObjectId("507f1f77bcf86cd799439016"),
            "title": "Engineer",
            "company": "Tech株式会社 GmbH Société",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 88,
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_unicode]
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Unicode should be preserved
        assert "Tech株式会社 GmbH Société" in html

    @patch("frontend.app.get_collection")
    def test_handles_empty_string_company_name(
        self, mock_get_collection, authenticated_client
    ):
        """Should show '-' when company is empty string."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job_empty_company = {
            "_id": ObjectId("507f1f77bcf86cd799439017"),
            "title": "Engineer",
            "company": "",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 70,
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_empty_company]
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should show "-" for empty company (template uses: {{ job.company or '-' }})
        # Look for pattern: title="-"
        assert 'title="-"' in html

    @patch("frontend.app.get_collection")
    def test_table_renders_correctly_with_mixed_company_lengths(
        self, mock_get_collection, authenticated_client, sample_batch_jobs
    ):
        """Should render table correctly with mix of short and long company names."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # sample_batch_jobs already has mix: "TechCorp", "A Very Long...", "Startup"
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = sample_batch_jobs
        mock_collection.find.return_value = mock_cursor

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # All companies should appear with title attributes
        assert 'title="TechCorp"' in html
        assert 'title="A Very Long Company Name That Should Be Truncated In The Table"' in html
        assert 'title="Startup"' in html

        # Table structure should be valid
        assert '<table' in html
        assert 'w-full table-fixed' in html
        assert '<thead' in html
        assert '<tbody' in html
