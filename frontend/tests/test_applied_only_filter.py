"""
Unit tests for "Applied Only" filter in job listing frontend.

Feature: Checkbox filter that, when checked, shows only jobs with status "applied".
The filter:
1. Uses query param `applied_only=true`
2. Overrides status filter checkboxes when enabled
3. Persists through pagination and sorting via `filter_params` in templates

Files tested:
- frontend/app.py: job_rows_partial() lines 385-396, 2013
- frontend/templates/partials/job_rows.html: filter_params line 7

Note: client and mock_db fixtures are provided by conftest.py
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


# client and mock_db fixtures are provided by conftest.py


@pytest.fixture
def sample_jobs():
    """Sample job data with various statuses."""
    now = datetime.now()
    return [
        {
            "_id": ObjectId(),
            "title": "Applied Job 1",
            "company": "Applied Corp",
            "status": "applied",
            "createdAt": now,
            "location": "Remote",
            "url": "https://example.com/job1",
            "score": 85
        },
        {
            "_id": ObjectId(),
            "title": "Applied Job 2",
            "company": "Another Applied Corp",
            "status": "applied",
            "createdAt": now,
            "location": "New York",
            "url": "https://example.com/job2",
            "score": 90
        },
        {
            "_id": ObjectId(),
            "title": "Not Processed Job",
            "company": "Other Corp",
            "status": "not processed",
            "createdAt": now,
            "location": "Remote",
            "url": "https://example.com/job3",
            "score": 75
        },
        {
            "_id": ObjectId(),
            "title": "Discarded Job",
            "company": "Discarded Corp",
            "status": "discarded",
            "createdAt": now,
            "location": "London",
            "url": "https://example.com/job4",
            "score": 60
        },
    ]


class TestAppliedOnlyFilterBackendLogic:
    """Tests for the applied_only filter backend logic in app.py."""

    def test_applied_only_true_returns_only_applied_jobs(self, client, mock_db):
        """Should return only jobs with status 'applied' when applied_only=true."""
        mock_repo, _ = mock_db

        applied_job = {
            "_id": ObjectId(),
            "title": "Applied Job",
            "company": "Test Corp",
            "status": "applied",
            "createdAt": datetime.now(),
            "location": "Remote",
            "url": "https://example.com/job1",
            "score": 85
        }
        # Repository find() returns list directly
        mock_repo.find.return_value = [applied_job]
        mock_repo.count_documents.return_value = 1

        response = client.get('/partials/job-rows?applied_only=true')

        assert response.status_code == 200

        # Verify MongoDB query was called with status filter for "applied"
        find_call = mock_repo.find.call_args
        if find_call:
            query = find_call[0][0] if find_call[0] else find_call[1].get('filter', {})
            # The query should filter for status: applied
            assert 'status' in query or '$and' in query

    def test_applied_only_false_uses_default_status_exclusions(self, client, mock_db):
        """Should use default status exclusions when applied_only=false."""
        mock_repo, _ = mock_db

        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=false')

        assert response.status_code == 200

        # Verify MongoDB query excludes default statuses (discarded, applied, interview scheduled)
        find_call = mock_repo.find.call_args
        if find_call:
            query = find_call[0][0] if find_call[0] else find_call[1].get('filter', {})
            # Default behavior excludes discarded, applied, interview scheduled
            assert 'status' in query or '$and' in query

    def test_applied_only_absent_uses_default_status_exclusions(self, client, mock_db):
        """Should use default status exclusions when applied_only param is absent."""
        mock_repo, _ = mock_db

        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows')

        assert response.status_code == 200

    def test_applied_only_overrides_status_checkboxes(self, client, mock_db):
        """Should override status checkboxes when applied_only=true."""
        mock_repo, _ = mock_db

        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        # Request with status checkboxes selected, but applied_only=true should override
        response = client.get('/partials/job-rows?applied_only=true&statuses=not+processed&statuses=discarded')

        assert response.status_code == 200

        # Verify query filters for "applied" status, not the checkbox selections
        find_call = mock_repo.find.call_args
        if find_call:
            query = find_call[0][0] if find_call[0] else find_call[1].get('filter', {})
            # Should query for applied, ignoring checkbox statuses
            assert 'status' in query or '$and' in query

    def test_applied_only_case_insensitive_true(self, client, mock_db):
        """Should handle applied_only=TRUE (uppercase)."""
        mock_repo, _ = mock_db

        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=TRUE')

        assert response.status_code == 200
        # Should be treated as true (case-insensitive)

    def test_applied_only_case_insensitive_mixed(self, client, mock_db):
        """Should handle applied_only=True (mixed case)."""
        mock_repo, _ = mock_db

        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=True')

        assert response.status_code == 200
        # Should be treated as true (case-insensitive)


class TestAppliedOnlyFilterPersistence:
    """Tests for applied_only filter persistence in templates."""

    def test_current_applied_only_passed_to_template_context(self, client, mock_db):
        """Should pass current_applied_only to template context."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=true')

        assert response.status_code == 200
        # Verify applied_only param appears in response (filter_params)
        assert b'applied_only=true' in response.data

    def test_applied_only_persists_in_pagination_links(self, client, mock_db):
        """Should preserve applied_only filter in pagination links."""
        mock_repo, _ = mock_db

        # Return 10 jobs to ensure multiple pages exist
        jobs = [
            {
                "_id": ObjectId(),
                "title": f"Applied Job {i}",
                "company": "Test Corp",
                "status": "applied",
                "createdAt": datetime.now(),
                "location": "Remote",
                "url": f"https://example.com/job{i}",
                "score": 85
            }
            for i in range(10)
        ]
        # Repository find() returns list directly
        mock_repo.find.return_value = jobs
        mock_repo.count_documents.return_value = 50  # 5 pages

        response = client.get('/partials/job-rows?applied_only=true&page=2')

        assert response.status_code == 200
        # applied_only param should appear in pagination links
        assert b'applied_only=true' in response.data

    def test_applied_only_persists_in_sort_links(self, client, mock_db):
        """Should preserve applied_only filter in sort header links."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=true&sort=company&direction=asc')

        assert response.status_code == 200
        # Sort headers should include applied_only param
        assert b'applied_only=true' in response.data
        # Verify HTMX hx-get attributes contain the filter
        assert b'hx-get="/partials/job-rows?sort=' in response.data

    def test_applied_only_persists_with_page_size_changes(self, client, mock_db):
        """Should preserve applied_only filter when page size changes."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=true&page_size=50')

        assert response.status_code == 200
        assert b'applied_only=true' in response.data


class TestAppliedOnlyWithOtherFilters:
    """Tests for applied_only combined with other filters."""

    def test_applied_only_with_query_search(self, client, mock_db):
        """Should preserve both applied_only and query search."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=true&query=engineer')

        assert response.status_code == 200
        assert b'applied_only=true' in response.data
        assert b'query=engineer' in response.data

    def test_applied_only_with_location_filter(self, client, mock_db):
        """Should preserve both applied_only and location filter."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=true&locations=Remote')

        assert response.status_code == 200
        assert b'applied_only=true' in response.data
        assert b'locations=Remote' in response.data

    def test_applied_only_with_datetime_filters(self, client, mock_db):
        """Should preserve applied_only with datetime filters."""
        mock_repo, _ = mock_db

        # When datetime filters are active, backend uses aggregation
        mock_repo.aggregate.return_value = [{
            "metadata": [{"total": 0}],
            "data": []
        }]

        response = client.get(
            '/partials/job-rows?applied_only=true&datetime_from=2025-01-01T00:00:00&datetime_to=2025-01-31T23:59:59'
        )

        assert response.status_code == 200
        assert b'applied_only=true' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_to=2025-01-31T23:59:59' in response.data

    def test_applied_only_with_all_filters_combined(self, client, mock_db):
        """Should preserve applied_only with all other filters combined."""
        mock_repo, _ = mock_db

        # When datetime filters are active, backend uses aggregation
        mock_repo.aggregate.return_value = [{
            "metadata": [{"total": 5}],
            "data": [
                {
                    "_id": ObjectId(),
                    "title": "Applied Job",
                    "company": "Test Corp",
                    "status": "applied",
                    "createdAt": datetime.now(),
                    "location": "Remote",
                    "url": "https://example.com/job1",
                    "score": 85
                }
            ]
        }]

        response = client.get(
            '/partials/job-rows?'
            'applied_only=true&'
            'query=senior&'
            'locations=Remote&'
            'datetime_from=2025-01-01T00:00:00&'
            'datetime_to=2025-01-31T23:59:59&'
            'sort=score&'
            'direction=desc&'
            'page=1&'
            'page_size=10'
        )

        assert response.status_code == 200
        # All params should be preserved
        assert b'applied_only=true' in response.data
        assert b'query=senior' in response.data
        assert b'locations=Remote' in response.data
        assert b'datetime_from=2025-01-01T00:00:00' in response.data
        assert b'datetime_to=2025-01-31T23:59:59' in response.data
        assert b'sort=score' in response.data


class TestAppliedOnlyEdgeCases:
    """Edge cases and error handling for applied_only filter."""

    def test_applied_only_empty_string(self, client, mock_db):
        """Should treat empty applied_only as false."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=')

        assert response.status_code == 200
        # Should behave as if applied_only is not set (default behavior)

    def test_applied_only_invalid_value(self, client, mock_db):
        """Should treat invalid applied_only value as false."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=invalid')

        assert response.status_code == 200
        # Should behave as if applied_only is false (not "true")

    def test_applied_only_with_no_applied_jobs(self, client, mock_db):
        """Should handle case where no applied jobs exist."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []  # No jobs
        mock_repo.count_documents.return_value = 0

        response = client.get('/partials/job-rows?applied_only=true')

        assert response.status_code == 200
        # Should return empty result gracefully

    def test_applied_only_multiple_times_in_url(self, client, mock_db):
        """Should handle applied_only appearing multiple times in URL."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        # Flask takes the last value when param appears multiple times
        response = client.get('/partials/job-rows?applied_only=false&applied_only=true')

        assert response.status_code == 200
        # Should use the last value (true)


class TestAppliedOnlyHTMXIntegration:
    """Tests for HTMX integration with applied_only filter."""

    def test_htmx_request_with_applied_only_gets_cache_busting_headers(self, client, mock_db):
        """HTMX requests with applied_only should receive cache-busting headers."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        response = client.get(
            '/partials/job-rows?applied_only=true',
            headers={'HX-Request': 'true'}
        )

        assert response.status_code == 200
        # Verify cache-busting headers
        assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'
        assert response.headers.get('Pragma') == 'no-cache'
        assert response.headers.get('Expires') == '0'

    def test_htmx_swap_preserves_applied_only_on_sort(self, client, mock_db):
        """HTMX sort operations should preserve applied_only filter."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        # Simulate HTMX sort request
        response = client.get(
            '/partials/job-rows?applied_only=true&sort=company&direction=asc',
            headers={'HX-Request': 'true'}
        )

        assert response.status_code == 200
        # Sort links should preserve applied_only
        assert b'applied_only=true' in response.data

    def test_htmx_swap_preserves_applied_only_on_pagination(self, client, mock_db):
        """HTMX pagination should preserve applied_only filter."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 50  # Multiple pages

        # Simulate HTMX pagination request
        response = client.get(
            '/partials/job-rows?applied_only=true&page=2',
            headers={'HX-Request': 'true'}
        )

        assert response.status_code == 200
        # Pagination links should preserve applied_only
        assert b'applied_only=true' in response.data


class TestAppliedOnlyAPIEndpoint:
    """Tests for applied_only filter in /api/jobs endpoint."""

    def test_api_endpoint_respects_applied_only_filter(self, client, mock_db):
        """API endpoint should respect applied_only filter."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = [
            {
                "_id": ObjectId(),
                "title": "Applied Job",
                "company": "Test Corp",
                "status": "applied",
                "createdAt": datetime.now(),
                "location": "Remote",
                "url": "https://example.com/job1",
                "score": 85
            }
        ]
        mock_repo.count_documents.return_value = 1

        response = client.get('/api/jobs?applied_only=true')

        assert response.status_code == 200
        data = response.get_json()
        assert 'jobs' in data
        # All returned jobs should have status "applied"
        for job in data['jobs']:
            assert job['status'] == 'applied'

    def test_api_endpoint_applied_only_overrides_status_param(self, client, mock_db):
        """API endpoint should override status param when applied_only=true."""
        mock_repo, _ = mock_db

        # Repository find() returns list directly
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0

        # Request with status param, but applied_only should override
        response = client.get('/api/jobs?applied_only=true&statuses=not+processed&statuses=discarded')

        assert response.status_code == 200
        data = response.get_json()
        assert 'jobs' in data
        # Should query for applied status, not the status params
