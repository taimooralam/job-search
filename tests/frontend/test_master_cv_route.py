"""
Unit tests for Master CV Editor Flask route.

Tests the /master-cv route that renders the Master CV editor page.
"""

import pytest


class TestMasterCVRoute:
    """Tests for the /master-cv route."""

    def test_master_cv_route_returns_200(self, authenticated_client, mock_db):
        """Should return 200 and render master_cv.html template."""
        # Act
        response = authenticated_client.get("/master-cv")

        # Assert
        assert response.status_code == 200
        assert b"Master CV Editor" in response.data or b"master-cv" in response.data

    def test_master_cv_route_requires_authentication(self, client, mock_db):
        """Should redirect to login when not authenticated."""
        # Act
        response = client.get("/master-cv")

        # Assert
        assert response.status_code == 302  # Redirect to login
        assert "/login" in response.location or "login" in response.location.lower()

    def test_master_cv_route_renders_correct_template(self, authenticated_client, mock_db):
        """Should render the master_cv.html template with expected content."""
        # Act
        response = authenticated_client.get("/master-cv")

        # Assert
        assert response.status_code == 200
        # Check for key elements from the master_cv.html template
        data = response.data.decode("utf-8")

        # Template should contain these key elements:
        # 1. Page title
        assert "Master CV Editor" in data or "Master CV" in data

        # 2. JS file inclusion
        assert "master-cv-editor.js" in data

        # 3. CSS file inclusion
        assert "master-cv-editor.css" in data

    def test_master_cv_route_includes_required_scripts(self, authenticated_client, mock_db):
        """Should include necessary JavaScript and CSS resources."""
        # Act
        response = authenticated_client.get("/master-cv")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Should include the master CV editor JavaScript
        assert "master-cv-editor.js" in html

        # Should include the master CV editor CSS
        assert "master-cv-editor.css" in html

    def test_master_cv_route_includes_tab_structure(self, authenticated_client, mock_db):
        """Should render tab navigation structure for Candidate, Roles, Taxonomy."""
        # Act
        response = authenticated_client.get("/master-cv")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Check for tab structure indicators
        # The actual tab content is rendered by JavaScript, but the container should exist
        assert "tab" in html.lower()

    def test_master_cv_route_multiple_requests(self, authenticated_client, mock_db):
        """Should handle multiple requests to the same route."""
        # Act
        response1 = authenticated_client.get("/master-cv")
        response2 = authenticated_client.get("/master-cv")
        response3 = authenticated_client.get("/master-cv")

        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

    def test_master_cv_route_with_query_params(self, authenticated_client, mock_db):
        """Should ignore query parameters and still render page."""
        # Act
        response = authenticated_client.get("/master-cv?tab=roles&foo=bar")

        # Assert
        assert response.status_code == 200
        # Query params should not affect rendering
        assert b"Master CV" in response.data or b"master-cv" in response.data

    def test_master_cv_route_does_not_accept_post(self, authenticated_client, mock_db):
        """Should return 405 Method Not Allowed for POST requests."""
        # Act
        response = authenticated_client.post("/master-cv")

        # Assert
        assert response.status_code == 405  # Method Not Allowed

    def test_master_cv_route_does_not_accept_put(self, authenticated_client, mock_db):
        """Should return 405 Method Not Allowed for PUT requests."""
        # Act
        response = authenticated_client.put("/master-cv")

        # Assert
        assert response.status_code == 405  # Method Not Allowed

    def test_master_cv_route_does_not_accept_delete(self, authenticated_client, mock_db):
        """Should return 405 Method Not Allowed for DELETE requests."""
        # Act
        response = authenticated_client.delete("/master-cv")

        # Assert
        assert response.status_code == 405  # Method Not Allowed
