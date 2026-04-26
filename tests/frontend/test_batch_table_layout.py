"""
Tests for batch table layout and rendering.

These assertions track the current repository-backed batch table contract:
- routes use `_get_repo()` rather than `get_collection()`
- the batch table renders via the `batch_job_rows.html` partial
- the current column set includes location and actions columns
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def app():
    from frontend.app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


@pytest.fixture
def sample_batch_jobs():
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


@pytest.fixture
def batch_repo_factory(mocker):
    def _build(jobs=None, total_count=None, single_job=None):
        jobs = list(jobs or [])
        total_count_value = len(jobs) if total_count is None else total_count
        repo = MagicMock()
        repo.aggregate.return_value = [{
            "metadata": [{"total": total_count_value}] if total_count_value else [],
            "data": jobs,
        }]
        repo.count_documents.return_value = total_count_value
        repo.find.return_value = jobs
        repo.find_one.return_value = single_job
        mocker.patch("frontend.app._get_repo", return_value=repo)
        return repo

    return _build


class TestBatchTableStructure:
    def test_table_has_correct_fixed_layout_classes(
        self, authenticated_client, sample_batch_jobs, batch_repo_factory
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert 'class="w-full table-fixed theme-table"' in html
        assert "min-w-full" not in html
        assert "<table" in html
        assert "<thead" in html
        assert "<tbody" in html

    def test_empty_table_has_correct_structure(self, authenticated_client, batch_repo_factory):
        batch_repo_factory(jobs=[], total_count=0)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "No jobs in batch queue" in html
        assert 'colspan="11"' in html


class TestBatchTableHeaderColumns:
    @pytest.mark.parametrize(
        ("expected_label", "expected_width"),
        [
            ("Company", "w-[120px]"),
            ("Loc.", "w-[45px]"),
            ("Score", "w-[60px]"),
            ("Added", "w-[100px]"),
            ("Status", "w-[140px]"),
            ("Progress", "w-[120px]"),
            ("Pipeline", "w-[70px]"),
            ("Actions", "w-[85px]"),
        ],
    )
    def test_header_columns_have_current_width_classes(
        self,
        authenticated_client,
        sample_batch_jobs,
        batch_repo_factory,
        expected_label,
        expected_width,
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert expected_label in html
        assert expected_width in html

    def test_expand_and_checkbox_columns_have_current_width_classes(
        self, authenticated_client, sample_batch_jobs, batch_repo_factory
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "w-8" in html
        assert "w-10" in html


class TestBatchTableCompanyCell:
    def test_company_cell_has_overflow_and_truncate(
        self, authenticated_client, sample_batch_jobs, batch_repo_factory
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "overflow-hidden" in html
        assert "truncate" in html
        assert 'title="TechCorp"' in html
        assert 'title="A Very Long Company Name That Should Be Truncated In The Table"' in html
        assert 'title="Startup"' in html

    def test_company_cell_handles_missing_company_name(self, authenticated_client, batch_repo_factory):
        job_no_company = {
            "_id": ObjectId("507f1f77bcf86cd799439014"),
            "title": "Software Engineer",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 75,
        }
        batch_repo_factory(jobs=[job_no_company])

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert 'title="-"' in html or ">-<" in html

    def test_company_cell_preserves_whitespace_nowrap(
        self, authenticated_client, sample_batch_jobs, batch_repo_factory
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "whitespace-nowrap" in html


class TestBatchSingleRowCompanyCell:
    def test_single_row_company_cell_has_current_overflow_handling(
        self, authenticated_client, batch_repo_factory
    ):
        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Engineer",
            "company": "Very Long Company Name That Needs Truncation",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 85,
        }
        batch_repo_factory(single_job=job)

        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439011")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "overflow-hidden" in html
        assert "truncate" in html
        assert 'title="Very Long Company Name That Needs Truncation"' in html

    def test_single_row_handles_missing_company(self, authenticated_client, batch_repo_factory):
        job = {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "title": "DevOps Engineer",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 80,
        }
        batch_repo_factory(single_job=job)

        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439013")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert 'title="-"' in html or ">-<" in html


class TestBatchTableColumnCount:
    def test_header_has_correct_column_count(
        self, authenticated_client, sample_batch_jobs, batch_repo_factory
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        th_count = html.count('<th scope="col"')
        assert th_count == 11, f"Expected 11 header columns, found {th_count}"

    def test_empty_state_colspan_matches_column_count(self, authenticated_client, batch_repo_factory):
        batch_repo_factory(jobs=[], total_count=0)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert 'colspan="11"' in html


class TestBatchTableEdgeCases:
    def test_handles_special_characters_in_company_name(self, authenticated_client, batch_repo_factory):
        job_special_chars = {
            "_id": ObjectId("507f1f77bcf86cd799439015"),
            "title": "Engineer",
            "company": 'Company "Quotes" & <Tags>',
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 75,
        }
        batch_repo_factory(jobs=[job_special_chars])

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert (
            'Company &#34;Quotes&#34; &amp; &lt;Tags&gt;' in html
            or 'Company &#39;Quotes&#39; &amp; &lt;Tags&gt;' in html
            or 'Company &quot;Quotes&quot; &amp; &lt;Tags&gt;' in html
        )

    def test_handles_unicode_in_company_name(self, authenticated_client, batch_repo_factory):
        job_unicode = {
            "_id": ObjectId("507f1f77bcf86cd799439016"),
            "title": "Engineer",
            "company": "Tech株式会社 GmbH Société",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
            "score": 88,
        }
        batch_repo_factory(jobs=[job_unicode])

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Tech株式会社 GmbH Société" in html

    def test_table_renders_correctly_with_mixed_company_lengths(
        self, authenticated_client, sample_batch_jobs, batch_repo_factory
    ):
        batch_repo_factory(jobs=sample_batch_jobs)

        response = authenticated_client.get("/partials/batch-job-rows")

        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "<table" in html
        assert "w-full table-fixed" in html
        assert "<thead" in html
        assert "<tbody" in html
