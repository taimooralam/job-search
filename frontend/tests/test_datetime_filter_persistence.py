"""
Unit tests for datetime filter persistence in job listing frontend.

Bug Fix: The datetime_from and datetime_to parameters were not being preserved
in pagination and sorting links. The template was using date_from/date_to instead
of datetime_from/datetime_to.

Files changed:
- frontend/app.py: Added cache-busting headers for HTMX, fixed job_rows_partial()
  to pass current_datetime_from/current_datetime_to
- frontend/templates/partials/job_rows.html: Updated filter_params to use datetime params
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from bson import ObjectId

# Import the Flask app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from frontend.app import app


@pytest.fixture
def client():
    """Create an authenticated test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
        yield client


@pytest.fixture
def mock_db():
    """Mock the MongoDB database."""
    with patch('frontend.app.get_db') as mock_get_db:
        mock_database = MagicMock()
        mock_collection = MagicMock()
        mock_database.__getitem__ = MagicMock(return_value=mock_collection)
        mock_get_db.return_value = mock_database
        yield mock_database, mock_collection


class TestJobRowsPartialDatetimeParams:
    """Tests for job_rows_partial() datetime parameter handling."""

    def test_reads_datetime_from_param(self, client, mock_db):
        """Should correctly read datetime_from query parameter."""
        mock_database, mock_collection = mock_db

        # Mock the database response
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=2025-01-01T00:00:00')

        assert response.status_code == 200
        # Verify the datetime param appears in the rendered template
        assert b'datetime_from=2025-01-01T00:00:00' in response.data

    def test_reads_datetime_to_param(self, client, mock_db):
        """Should correctly read datetime_to query parameter."""
        mock_database, mock_collection = mock_db

        # Mock the database response
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_to=2025-01-31T23:59:59')

        assert response.status_code == 200
        # Verify the datetime param appears in the rendered template
        assert b'datetime_to=2025-01-31T23:59:59' in response.data

    def test_reads_both_datetime_params(self, client, mock_db):
        """Should correctly read both datetime_from and datetime_to."""
        mock_database, mock_collection = mock_db

        # Mock the database response
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get(
            '/partials/job-rows?datetime_from=2025-01-01T00:00:00&datetime_to=2025-01-31T23:59:59'
        )

        assert response.status_code == 200
        # Both params should appear in the rendered template
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_to=2025-01-31T23:59:59' in response.data

    def test_preserves_datetime_params_in_pagination(self, client, mock_db):
        """Should preserve datetime filters in pagination links."""
        mock_database, mock_collection = mock_db

        # When datetime filters are active, backend uses aggregation with $facet
        # Mock the aggregation response with multiple pages worth of data
        mock_collection.aggregate.return_value = iter([{
            "metadata": [{"total": 50}],  # 5 pages of 10 items
            "data": [
                {
                    "_id": ObjectId(),
                    "title": f"Job {i}",
                    "company": "Test Corp",
                    "status": "not processed",
                    "createdAt": datetime.now(),
                    "location": "Remote",
                    "url": f"https://example.com/job{i}",
                    "score": 75
                }
                for i in range(10)
            ]
        }])

        response = client.get(
            '/partials/job-rows?datetime_from=2025-01-01T00:00:00&datetime_to=2025-01-31T23:59:59&page=2'
        )

        assert response.status_code == 200
        # Datetime params should be preserved in the response (sort headers)
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_to=2025-01-31T23:59:59' in response.data

    def test_preserves_datetime_params_in_sort_links(self, client, mock_db):
        """Should preserve datetime filters in sort header links."""
        mock_database, mock_collection = mock_db

        # Mock the database response
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get(
            '/partials/job-rows?datetime_from=2025-01-01T00:00:00&datetime_to=2025-01-31T23:59:59'
        )

        assert response.status_code == 200
        # Sort headers should include datetime params
        assert b'hx-get="/partials/job-rows?sort=' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_to=2025-01-31T23:59:59' in response.data

    def test_fallback_to_date_params_for_compatibility(self, client, mock_db):
        """Should fall back to date_from/date_to if datetime_from/to not provided."""
        mock_database, mock_collection = mock_db

        # Mock the database response
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        # Use old date_from/date_to params
        response = client.get('/partials/job-rows?date_from=2025-01-01&date_to=2025-01-31')

        assert response.status_code == 200
        # Should use the date params (converted to datetime params in the template)
        assert b'datetime_from=2025-01-01' in response.data
        assert b'datetime_to=2025-01-31' in response.data

    def test_datetime_params_precedence_over_date_params(self, client, mock_db):
        """Should prefer datetime_from/to over date_from/to when both provided."""
        mock_database, mock_collection = mock_db

        # Mock the database response
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        # Provide both datetime_from and date_from
        response = client.get(
            '/partials/job-rows?datetime_from=2025-01-01T00:00:00&date_from=2024-01-01'
        )

        assert response.status_code == 200
        # Should use datetime_from, not date_from
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_from=2024-01-01' not in response.data


class TestDatetimeFilterFormats:
    """Tests for various datetime format handling."""

    def test_datetime_with_seconds(self, client, mock_db):
        """Should handle datetime format with seconds."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=2025-01-01T14:30:45')

        assert response.status_code == 200
        assert b'datetime_from=2025-01-01T14:30:45' in response.data

    def test_datetime_without_seconds(self, client, mock_db):
        """Should handle datetime format without seconds."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=2025-01-01T14:30')

        assert response.status_code == 200
        assert b'datetime_from=2025-01-01T14:30' in response.data

    def test_datetime_with_z_suffix(self, client, mock_db):
        """Should handle datetime format with Z (UTC) suffix."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=2025-01-01T14:30:45Z')

        assert response.status_code == 200
        assert b'datetime_from=2025-01-01T14:30:45Z' in response.data

    def test_date_only_format(self, client, mock_db):
        """Should handle date-only format (YYYY-MM-DD)."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=2025-01-01')

        assert response.status_code == 200
        assert b'datetime_from=2025-01-01' in response.data


class TestHTMXCacheBusting:
    """Tests for HTMX cache-busting headers."""

    def test_htmx_request_receives_cache_busting_headers(self, client, mock_db):
        """HTMX requests should receive Cache-Control: no-cache headers."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        # Make HTMX request (identified by HX-Request header)
        response = client.get(
            '/partials/job-rows',
            headers={'HX-Request': 'true'}
        )

        assert response.status_code == 200
        # Verify cache-busting headers
        assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'
        assert response.headers.get('Pragma') == 'no-cache'
        assert response.headers.get('Expires') == '0'

    def test_non_htmx_request_no_cache_busting_headers(self, client, mock_db):
        """Non-HTMX requests should NOT receive cache-busting headers."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        # Make regular request (no HX-Request header)
        response = client.get('/partials/job-rows')

        assert response.status_code == 200
        # Cache-Control should either be absent or not set to no-cache
        cache_control = response.headers.get('Cache-Control', '')
        assert cache_control != 'no-cache, no-store, must-revalidate'

    def test_htmx_header_value_case_sensitive(self, client, mock_db):
        """Cache-busting should only trigger for exact 'true' value."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        # Make request with HX-Request header but wrong value
        response = client.get(
            '/partials/job-rows',
            headers={'HX-Request': 'True'}  # Capital T
        )

        assert response.status_code == 200
        # Should not have cache-busting headers (case-sensitive check)
        cache_control = response.headers.get('Cache-Control', '')
        assert cache_control != 'no-cache, no-store, must-revalidate'


class TestDatetimeParamsWithOtherFilters:
    """Tests for datetime params combined with other filters."""

    def test_datetime_params_with_query_search(self, client, mock_db):
        """Should preserve datetime filters with text search."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get(
            '/partials/job-rows?query=engineer&datetime_from=2025-01-01T00:00:00'
        )

        assert response.status_code == 200
        assert b'query=engineer' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data

    def test_datetime_params_with_location_filter(self, client, mock_db):
        """Should preserve datetime filters with location filter."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get(
            '/partials/job-rows?locations=Remote&datetime_from=2025-01-01T00:00:00'
        )

        assert response.status_code == 200
        assert b'locations=Remote' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data

    def test_datetime_params_with_multiple_locations(self, client, mock_db):
        """Should preserve datetime filters with multiple location filters."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get(
            '/partials/job-rows?locations=Remote&locations=New+York&datetime_from=2025-01-01T00:00:00'
        )

        assert response.status_code == 200
        assert b'locations=Remote' in response.data
        assert b'locations=New+York' in response.data or b'locations=New%20York' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data

    def test_datetime_params_with_all_filters(self, client, mock_db):
        """Should preserve datetime filters with all other filters combined."""
        mock_database, mock_collection = mock_db

        # When datetime filters are active, backend uses aggregation with $facet
        mock_collection.aggregate.return_value = iter([{
            "metadata": [{"total": 0}],
            "data": []
        }])

        response = client.get(
            '/partials/job-rows?query=engineer&locations=Remote&datetime_from=2025-01-01T00:00:00&datetime_to=2025-01-31T23:59:59&sort=company&direction=asc&page=2'
        )

        assert response.status_code == 200
        # All params should be preserved in sort header links
        assert b'query=engineer' in response.data
        assert b'locations=Remote' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_to=2025-01-31T23:59:59' in response.data
        assert b'sort=company' in response.data
        # Note: Column headers show opposite direction (to toggle), so we just verify
        # that sort=company is preserved - the direction toggling is correct behavior


class TestEdgeCases:
    """Edge cases and error handling for datetime filters."""

    def test_empty_datetime_params(self, client, mock_db):
        """Should handle empty datetime parameters gracefully."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=&datetime_to=')

        assert response.status_code == 200
        # Empty params should not appear in filter links
        # (only non-empty params are added to filter_query in template)

    def test_only_datetime_from_provided(self, client, mock_db):
        """Should handle when only datetime_from is provided."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_from=2025-01-01T00:00:00')

        assert response.status_code == 200
        assert b'datetime_from=2025-01-01T00:00:00' in response.data

    def test_only_datetime_to_provided(self, client, mock_db):
        """Should handle when only datetime_to is provided."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows?datetime_to=2025-01-31T23:59:59')

        assert response.status_code == 200
        assert b'datetime_to=2025-01-31T23:59:59' in response.data

    def test_special_characters_in_datetime(self, client, mock_db):
        """Should handle URL encoding of datetime special characters."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        # Datetime with +00:00 timezone
        response = client.get('/partials/job-rows?datetime_from=2025-01-01T00:00:00%2B00:00')

        assert response.status_code == 200
        # URL-encoded datetime should be preserved
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
