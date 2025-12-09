"""
API smoke tests for the Job Search UI.

These tests verify the basic functionality of the Flask API endpoints.
Uses mocked MongoDB to avoid requiring a real database connection.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from bson import ObjectId

# Import the Flask app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from frontend.app import app, JOB_STATUSES, serialize_job


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


class TestSerializeJob:
    """Tests for the serialize_job helper function."""

    def test_serialize_objectid(self):
        """Test that ObjectId is converted to string."""
        oid = ObjectId()
        job = {"_id": oid, "title": "Engineer"}
        result = serialize_job(job)
        assert result["_id"] == str(oid)
        assert result["title"] == "Engineer"

    def test_serialize_datetime(self):
        """Test that datetime is converted to ISO format."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        job = {"createdAt": dt, "title": "Engineer"}
        result = serialize_job(job)
        assert result["createdAt"] == "2024-01-15T10:30:00"

    def test_serialize_regular_fields(self):
        """Test that regular fields are passed through."""
        job = {"title": "Engineer", "company": "Acme", "score": 85}
        result = serialize_job(job)
        # Regular fields passed through
        assert result["title"] == "Engineer"
        assert result["company"] == "Acme"
        assert result["score"] == 85
        # Description is always normalized (empty string if not present)
        assert result["description"] == ""


class TestListJobsAPI:
    """Tests for the GET /api/jobs endpoint."""

    def test_list_jobs_default_params(self, client, mock_db):
        """Test listing jobs with default parameters."""
        mock_database, mock_collection = mock_db

        # Setup mock cursor
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([
            {"_id": ObjectId(), "title": "Engineer", "company": "Acme"}
        ])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 1

        response = client.get('/api/jobs')

        assert response.status_code == 200
        data = response.get_json()
        assert "jobs" in data
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 10

    def test_list_jobs_with_search(self, client, mock_db):
        """Test searching jobs."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/api/jobs?query=google')

        assert response.status_code == 200
        # Verify the find was called with search query (now nested in $and)
        call_args = mock_collection.find.call_args
        query = call_args[0][0]
        assert "$and" in query
        # Check that one of the $and conditions contains the search $or
        and_conditions = query["$and"]
        search_condition = next((c for c in and_conditions if "$or" in c and any("$regex" in cond.get("title", {}) for cond in c["$or"] if "title" in cond)), None)
        assert search_condition is not None

    def test_list_jobs_pagination(self, client, mock_db):
        """Test pagination parameters."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 100

        response = client.get('/api/jobs?page=3&page_size=50')

        assert response.status_code == 200
        data = response.get_json()
        assert data["pagination"]["page"] == 3
        assert data["pagination"]["page_size"] == 50
        assert data["pagination"]["total_pages"] == 2  # 100 / 50 = 2

    def test_list_jobs_invalid_page_size(self, client, mock_db):
        """Test that invalid page_size falls back to default."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/api/jobs?page_size=999')

        assert response.status_code == 200
        data = response.get_json()
        assert data["pagination"]["page_size"] == 10  # Falls back to default


class TestDeleteJobsAPI:
    """Tests for the POST /api/jobs/delete endpoint."""

    def test_delete_jobs_success(self, client, mock_db):
        """Test successful job deletion."""
        mock_database, mock_collection = mock_db

        mock_result = MagicMock()
        mock_result.deleted_count = 2
        mock_collection.delete_many.return_value = mock_result

        job_ids = [str(ObjectId()), str(ObjectId())]
        response = client.post('/api/jobs/delete',
                               json={"job_ids": job_ids},
                               content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["deleted_count"] == 2

    def test_delete_jobs_no_ids(self, client, mock_db):
        """Test delete with no job_ids provided."""
        response = client.post('/api/jobs/delete',
                               json={"job_ids": []},
                               content_type='application/json')

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_delete_jobs_invalid_ids(self, client, mock_db):
        """Test delete with invalid ObjectIds."""
        response = client.post('/api/jobs/delete',
                               json={"job_ids": ["invalid", "also-invalid"]},
                               content_type='application/json')

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data


class TestUpdateStatusAPI:
    """Tests for the POST /api/jobs/status endpoint."""

    def test_update_status_success(self, client, mock_db):
        """Test successful status update."""
        mock_database, mock_collection = mock_db

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        job_id = str(ObjectId())
        response = client.post('/api/jobs/status',
                               json={"job_id": job_id, "status": "applied"},
                               content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["status"] == "applied"

    def test_update_status_invalid_status(self, client, mock_db):
        """Test update with invalid status value."""
        job_id = str(ObjectId())
        response = client.post('/api/jobs/status',
                               json={"job_id": job_id, "status": "invalid_status"},
                               content_type='application/json')

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Invalid status" in data["error"]

    def test_update_status_missing_job_id(self, client, mock_db):
        """Test update with missing job_id."""
        response = client.post('/api/jobs/status',
                               json={"status": "applied"},
                               content_type='application/json')

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_update_status_job_not_found(self, client, mock_db):
        """Test update for non-existent job."""
        mock_database, mock_collection = mock_db

        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_collection.update_one.return_value = mock_result

        job_id = str(ObjectId())
        response = client.post('/api/jobs/status',
                               json={"job_id": job_id, "status": "applied"},
                               content_type='application/json')

        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data


class TestGetStatusesAPI:
    """Tests for the GET /api/jobs/statuses endpoint."""

    def test_get_statuses(self, client):
        """Test getting available statuses."""
        response = client.get('/api/jobs/statuses')

        assert response.status_code == 200
        data = response.get_json()
        assert "statuses" in data
        assert data["statuses"] == JOB_STATUSES


class TestGetStatsAPI:
    """Tests for the GET /api/stats endpoint."""

    def test_get_stats(self, client, mock_db):
        """Test getting database statistics."""
        mock_database, mock_collection = mock_db

        # Mock count_documents for different calls
        # 9 statuses: not processed, marked for applying, ready for applying,
        # to be deleted, discarded, applied, interview scheduled, rejected, offer received
        mock_collection.count_documents.side_effect = [
            1000,  # level-1 count
            150,   # level-2 count
            100, 30, 15, 5, 8, 10, 3, 2, 0,  # status counts (9 statuses)
            0,     # no status count
        ]

        response = client.get('/api/stats')

        assert response.status_code == 200
        data = response.get_json()
        assert "level1_count" in data
        assert "level2_count" in data
        assert "status_counts" in data


class TestGetJobAPI:
    """Tests for the GET /api/jobs/<job_id> endpoint."""

    def test_get_job_success(self, client, mock_db):
        """Test getting a single job."""
        mock_database, mock_collection = mock_db

        job_id = ObjectId()
        mock_collection.find_one.return_value = {
            "_id": job_id,
            "title": "Engineer",
            "company": "Acme"
        }

        response = client.get(f'/api/jobs/{str(job_id)}')

        assert response.status_code == 200
        data = response.get_json()
        assert "job" in data
        assert data["job"]["title"] == "Engineer"

    def test_get_job_not_found(self, client, mock_db):
        """Test getting a non-existent job."""
        mock_database, mock_collection = mock_db
        mock_collection.find_one.return_value = None

        job_id = ObjectId()
        response = client.get(f'/api/jobs/{str(job_id)}')

        assert response.status_code == 404

    def test_get_job_invalid_id(self, client, mock_db):
        """Test getting a job with invalid ID."""
        response = client.get('/api/jobs/invalid-id')

        assert response.status_code == 400


class TestUpdateJobAPI:
    """Tests for the PUT /api/jobs/<job_id> endpoint."""

    def test_update_job_success(self, client, mock_db):
        """Test updating a job."""
        mock_database, mock_collection = mock_db

        job_id = ObjectId()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result
        mock_collection.find_one.return_value = {
            "_id": job_id,
            "title": "Engineer",
            "remarks": "Great job"
        }

        response = client.put(f'/api/jobs/{str(job_id)}',
                              json={"remarks": "Great job"},
                              content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_update_job_invalid_status(self, client, mock_db):
        """Test updating job with invalid status."""
        job_id = ObjectId()
        response = client.put(f'/api/jobs/{str(job_id)}',
                              json={"status": "invalid_status"},
                              content_type='application/json')

        assert response.status_code == 400

    def test_update_job_no_data(self, client, mock_db):
        """Test updating job with no data."""
        job_id = ObjectId()
        response = client.put(f'/api/jobs/{str(job_id)}',
                              json={},
                              content_type='application/json')

        assert response.status_code == 400

    def test_update_job_not_found(self, client, mock_db):
        """Test updating non-existent job."""
        mock_database, mock_collection = mock_db

        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_collection.update_one.return_value = mock_result

        job_id = ObjectId()
        response = client.put(f'/api/jobs/{str(job_id)}',
                              json={"remarks": "test"},
                              content_type='application/json')

        assert response.status_code == 404


class TestHTMLRoutes:
    """Tests for the HTML routes."""

    def test_index_page(self, client):
        """Test that the index page renders."""
        response = client.get('/')

        assert response.status_code == 200
        assert b'Job Search' in response.data or b'JobSearch' in response.data

    def test_job_rows_partial(self, client, mock_db):
        """Test the HTMX partial for job rows."""
        mock_database, mock_collection = mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        mock_collection.find.return_value = mock_cursor
        mock_collection.count_documents.return_value = 0

        response = client.get('/partials/job-rows')

        assert response.status_code == 200
        # Should contain table structure
        assert b'<table' in response.data or b'No jobs found' in response.data

    def test_job_detail_page(self, client, mock_db):
        """Test that the job detail page renders."""
        mock_database, mock_collection = mock_db

        job_id = ObjectId()
        mock_collection.find_one.return_value = {
            "_id": job_id,
            "title": "Software Engineer",
            "company": "Acme Corp",
            "location": "Remote",
            "status": "not processed",
            "score": 85,
            "jobId": "JOB123",
            "jobUrl": "https://example.com/job/123"
        }

        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 200
        assert b'Software Engineer' in response.data or b'Acme Corp' in response.data

    def test_job_detail_page_not_found(self, client, mock_db):
        """Test job detail page for non-existent job."""
        mock_database, mock_collection = mock_db
        mock_collection.find_one.return_value = None

        job_id = ObjectId()
        response = client.get(f'/job/{str(job_id)}')

        assert response.status_code == 404


class TestGetLocationsAPI:
    """Tests for the GET /api/locations endpoint."""

    def test_get_locations_success(self, client, mock_db):
        """Test getting unique locations with counts."""
        mock_database, mock_collection = mock_db

        # Mock aggregation result
        mock_collection.aggregate.return_value = [
            {"location": "Remote", "count": 50},
            {"location": "New York, NY", "count": 30},
            {"location": "San Francisco, CA", "count": 20},
        ]

        response = client.get('/api/locations')

        assert response.status_code == 200
        data = response.get_json()
        assert "locations" in data
        assert len(data["locations"]) == 3
        assert data["locations"][0]["location"] == "Remote"
        assert data["locations"][0]["count"] == 50

    def test_get_locations_empty(self, client, mock_db):
        """Test getting locations when none exist."""
        mock_database, mock_collection = mock_db
        mock_collection.aggregate.return_value = []

        response = client.get('/api/locations')

        assert response.status_code == 200
        data = response.get_json()
        assert data["locations"] == []


class TestListJobsFilters:
    """Tests for the filter functionality in GET /api/jobs."""

    def test_list_jobs_with_date_filter(self, client, mock_db):
        """Test filtering jobs by date range.

        GAP-007: Date filtering now uses aggregation pipeline with $toDate to handle
        mixed types (strings from n8n, Date objects from other sources).
        """
        mock_database, mock_collection = mock_db

        # GAP-007: Date filtering uses aggregate() instead of find()
        mock_collection.aggregate.return_value = iter([{
            "metadata": [{"total": 5}],
            "data": []
        }])

        response = client.get('/api/jobs?date_from=2025-01-01&date_to=2025-01-31')

        assert response.status_code == 200
        # Verify aggregation was called
        assert mock_collection.aggregate.called
        call_args = mock_collection.aggregate.call_args
        pipeline = call_args[0][0]

        # Pipeline should have: $addFields (for $toDate), $match (date filter), $facet
        # Find the $match stage for normalized date
        date_match_stage = next((s for s in pipeline if "$match" in s and "_normalizedDate" in s.get("$match", {})), None)
        assert date_match_stage is not None
        date_filter = date_match_stage["$match"]["_normalizedDate"]
        assert "$gte" in date_filter
        assert "$lte" in date_filter
        # Values are now datetime objects, not strings
        from datetime import datetime
        assert isinstance(date_filter["$gte"], datetime)
        assert isinstance(date_filter["$lte"], datetime)

    def test_list_jobs_with_location_filter(self, client, mock_db):
        """Test filtering jobs by location."""
        mock_database, mock_collection = mock_db

        mock_collection.count_documents.return_value = 10
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = iter([])
        mock_collection.find.return_value = mock_cursor

        response = client.get('/api/jobs?locations=Remote&locations=New+York')

        assert response.status_code == 200
        # Verify the query included location filter (now nested in $and)
        call_args = mock_collection.find.call_args
        query = call_args[0][0]
        assert "$and" in query
        # Find the location condition within $and array
        and_conditions = query["$and"]
        location_condition = next((c for c in and_conditions if "location" in c), None)
        assert location_condition is not None
        assert "$in" in location_condition["location"]
        assert "Remote" in location_condition["location"]["$in"]
        assert "New York" in location_condition["location"]["$in"]

    def test_list_jobs_with_combined_filters(self, client, mock_db):
        """Test filtering jobs with multiple filters.

        GAP-007: When date filtering is present, aggregation pipeline is used.
        The initial $match stage contains non-date filters (search, location).
        """
        mock_database, mock_collection = mock_db

        # GAP-007: Date filtering uses aggregate() instead of find()
        mock_collection.aggregate.return_value = iter([{
            "metadata": [{"total": 3}],
            "data": []
        }])

        response = client.get(
            '/api/jobs?query=engineer&date_from=2025-01-01&locations=Remote'
        )

        assert response.status_code == 200
        # Verify aggregation was called
        assert mock_collection.aggregate.called
        call_args = mock_collection.aggregate.call_args
        pipeline = call_args[0][0]

        # First $match stage should contain non-date filters
        first_match_stage = next((s for s in pipeline if "$match" in s), None)
        assert first_match_stage is not None
        query = first_match_stage["$match"]

        # All non-date filters should be nested in $and
        assert "$and" in query
        and_conditions = query["$and"]
        # Check for text search $or (contains $regex for title)
        search_condition = next((c for c in and_conditions if "$or" in c and any("$regex" in cond.get("title", {}) for cond in c["$or"] if "title" in cond)), None)
        assert search_condition is not None
        # Check for location filter
        location_condition = next((c for c in and_conditions if "location" in c), None)
        assert location_condition is not None

        # Date filter is in a separate $match stage after $addFields
        date_match_stage = next((s for s in pipeline if "$match" in s and "_normalizedDate" in s.get("$match", {})), None)
        assert date_match_stage is not None
