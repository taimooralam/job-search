"""
Unit tests for PDF service endpoints.

Tests health check, render-pdf, and cv-to-pdf endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def client():
    """Create test client for PDF service with Playwright marked as ready."""
    import pdf_service.app as app_module
    # Mark Playwright as ready for tests
    app_module._playwright_ready = True
    app_module._playwright_error = None
    from pdf_service.app import app
    return TestClient(app)


@pytest.fixture
def client_playwright_unavailable():
    """Create test client with Playwright marked as unavailable."""
    import pdf_service.app as app_module
    app_module._playwright_ready = False
    app_module._playwright_error = "Test: Playwright not available"
    from pdf_service.app import app
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check_returns_200(self, client):
        """Test that health check returns 200 OK when Playwright is ready."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_returns_correct_structure(self, client):
        """Test that health check returns expected fields."""
        response = client.get("/health")
        data = response.json()

        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "active_renders" in data
        assert "max_concurrent" in data
        assert data["playwright_ready"] is True
        assert isinstance(data["active_renders"], int)
        assert isinstance(data["max_concurrent"], int)

    def test_health_check_active_renders_within_bounds(self, client):
        """Test that active_renders is within valid range."""
        response = client.get("/health")
        data = response.json()

        assert 0 <= data["active_renders"] <= data["max_concurrent"]

    def test_health_check_returns_503_when_playwright_unavailable(self, client_playwright_unavailable):
        """Test that health check returns 503 when Playwright is not ready."""
        response = client_playwright_unavailable.get("/health")
        assert response.status_code == 503
        data = response.json()["detail"]
        assert data["status"] == "unhealthy"
        assert data["playwright_ready"] is False
        assert "Playwright not available" in data["playwright_error"]


class TestRenderPDFEndpoint:
    """Tests for /render-pdf endpoint."""

    def test_render_pdf_requires_html(self, client):
        """Test that render-pdf requires HTML content."""
        response = client.post("/render-pdf", json={})
        assert response.status_code == 422  # Validation error

    def test_render_pdf_rejects_empty_html(self, client):
        """Test that render-pdf rejects empty HTML."""
        response = client.post("/render-pdf", json={"html": ""})
        assert response.status_code == 400
        assert "HTML content is required" in response.json()["detail"]

    @patch("playwright.async_api.async_playwright")
    def test_render_pdf_success(self, mock_playwright, client):
        """Test successful PDF rendering."""
        # Mock Playwright
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=b"%PDF-1.4 fake pdf content")
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        response = client.post(
            "/render-pdf",
            json={
                "html": "<h1>Test Document</h1>",
                "pageSize": "letter",
                "printBackground": True
            }
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers.get("content-disposition", "")

    @patch("playwright.async_api.async_playwright")
    def test_render_pdf_handles_timeout(self, mock_playwright, client):
        """Test that render-pdf handles Playwright timeouts."""
        import asyncio

        # Mock Playwright to raise timeout
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        response = client.post(
            "/render-pdf",
            json={"html": "<h1>Test</h1>"}
        )

        assert response.status_code == 500
        assert "timed out" in response.json()["detail"].lower()

    def test_render_pdf_validates_page_size(self, client):
        """Test that render-pdf accepts valid page sizes."""
        with patch("playwright.async_api.async_playwright") as mock_playwright:
            mock_browser = AsyncMock()
            mock_page = AsyncMock()
            mock_page.pdf = AsyncMock(return_value=b"%PDF")
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_playwright.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    chromium=MagicMock(
                        launch=AsyncMock(return_value=mock_browser)
                    )
                )
            )

            # Test letter
            response = client.post(
                "/render-pdf",
                json={"html": "<h1>Test</h1>", "pageSize": "letter"}
            )
            assert response.status_code == 200

            # Test A4
            response = client.post(
                "/render-pdf",
                json={"html": "<h1>Test</h1>", "pageSize": "a4"}
            )
            assert response.status_code == 200


class TestCVToPDFEndpoint:
    """Tests for /cv-to-pdf endpoint."""

    def test_cv_to_pdf_requires_tiptap_json(self, client):
        """Test that cv-to-pdf requires tiptap_json."""
        response = client.post("/cv-to-pdf", json={})
        assert response.status_code == 422  # Validation error

    def test_cv_to_pdf_validates_document_format(self, client):
        """Test that cv-to-pdf validates TipTap document format."""
        response = client.post(
            "/cv-to-pdf",
            json={"tiptap_json": {"type": "invalid"}}
        )
        assert response.status_code == 400
        assert "Invalid TipTap document format" in response.json()["detail"]

    @patch("playwright.async_api.async_playwright")
    def test_cv_to_pdf_success(self, mock_playwright, client):
        """Test successful CV PDF generation."""
        # Mock Playwright
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=b"%PDF-1.4 fake cv pdf")
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        tiptap_doc = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "John Doe"}]
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Software Engineer"}]
                }
            ]
        }

        response = client.post(
            "/cv-to-pdf",
            json={
                "tiptap_json": tiptap_doc,
                "documentStyles": {
                    "fontFamily": "Inter",
                    "fontSize": 11,
                    "lineHeight": 1.15,
                    "margins": {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0},
                    "pageSize": "letter"
                },
                "company": "TechCorp",
                "role": "Senior Engineer"
            }
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "CV_TechCorp_Senior_Engineer.pdf" in response.headers.get("content-disposition", "")

    def test_cv_to_pdf_handles_recursion_error(self, client):
        """Test that cv-to-pdf handles deeply nested documents."""
        with patch("pdf_service.pdf_helpers.tiptap_json_to_html", side_effect=RecursionError()):
            tiptap_doc = {
                "type": "doc",
                "content": []
            }

            response = client.post(
                "/cv-to-pdf",
                json={"tiptap_json": tiptap_doc}
            )

            assert response.status_code == 400
            assert "too deeply nested" in response.json()["detail"].lower()

    def test_cv_to_pdf_handles_conversion_error(self, client):
        """Test that cv-to-pdf handles TipTap conversion errors."""
        with patch("pdf_service.pdf_helpers.tiptap_json_to_html", side_effect=ValueError("Invalid node type")):
            tiptap_doc = {
                "type": "doc",
                "content": []
            }

            response = client.post(
                "/cv-to-pdf",
                json={"tiptap_json": tiptap_doc}
            )

            assert response.status_code == 400
            assert "Failed to process CV content" in response.json()["detail"]

    @patch("playwright.async_api.async_playwright")
    def test_cv_to_pdf_uses_default_styles(self, mock_playwright, client):
        """Test that cv-to-pdf uses default styles when not provided."""
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=b"%PDF")
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        tiptap_doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Test"}]
                }
            ]
        }

        response = client.post(
            "/cv-to-pdf",
            json={"tiptap_json": tiptap_doc}
        )

        assert response.status_code == 200

    def test_cv_to_pdf_builds_filename_from_company_role(self, client):
        """Test that cv-to-pdf builds correct filename."""
        with patch("playwright.async_api.async_playwright") as mock_playwright:
            mock_browser = AsyncMock()
            mock_page = AsyncMock()
            mock_page.pdf = AsyncMock(return_value=b"%PDF")
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_playwright.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    chromium=MagicMock(
                        launch=AsyncMock(return_value=mock_browser)
                    )
                )
            )

            tiptap_doc = {"type": "doc", "content": []}

            response = client.post(
                "/cv-to-pdf",
                json={
                    "tiptap_json": tiptap_doc,
                    "company": "Test & Co.",
                    "role": "Director (Engineering)"
                }
            )

            assert response.status_code == 200
            # Verify sanitized filename (new behavior: collapses underscores, no trailing)
            cd = response.headers.get("content-disposition", "")
            assert "CV_Test_Co_Director_Engineering.pdf" in cd


class TestScrapeLinkedInEndpoint:
    """Tests for /scrape-linkedin endpoint."""

    VALID_COOKIES = [
        {"name": "li_at", "value": "AQEDATest123", "domain": ".linkedin.com", "path": "/"},
        {"name": "JSESSIONID", "value": "ajax:123", "domain": ".linkedin.com", "path": "/"},
    ]
    VALID_URL = "https://www.linkedin.com/search/results/content/?keywords=AI+architect"

    def test_scrape_linkedin_rejects_non_linkedin_url(self, client):
        """Test that non-LinkedIn URLs are rejected with 400."""
        response = client.post(
            "/scrape-linkedin",
            json={
                "url": "https://www.google.com/search?q=test",
                "cookies": self.VALID_COOKIES,
            },
        )
        assert response.status_code == 400
        assert "LinkedIn URL" in response.json()["detail"]

    def test_scrape_linkedin_rejects_missing_cookies(self, client):
        """Test that empty cookies list is rejected with 400."""
        response = client.post(
            "/scrape-linkedin",
            json={"url": self.VALID_URL, "cookies": []},
        )
        assert response.status_code == 400
        assert "Cookies are required" in response.json()["detail"]

    def test_scrape_linkedin_rejects_missing_li_at(self, client):
        """Test that cookies without li_at are rejected with 400."""
        response = client.post(
            "/scrape-linkedin",
            json={
                "url": self.VALID_URL,
                "cookies": [{"name": "JSESSIONID", "value": "ajax:123", "domain": ".linkedin.com", "path": "/"}],
            },
        )
        assert response.status_code == 400
        assert "li_at" in response.json()["detail"]

    @patch("playwright.async_api.async_playwright")
    def test_scrape_linkedin_success(self, mock_playwright, client):
        """Test successful LinkedIn scrape returns structured results."""
        fake_posts = [
            {"text": "Great post about AI architecture", "url": "https://www.linkedin.com/feed/update/urn:li:activity:123", "author": "John Doe", "reactions": "42 reactions"},
            {"text": "Enterprise transformation insights", "url": "https://www.linkedin.com/feed/update/urn:li:activity:456", "author": "Jane Smith", "reactions": "18 reactions"},
        ]

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = self.VALID_URL  # No redirect
        mock_page.evaluate = AsyncMock(return_value=fake_posts)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        response = client.post(
            "/scrape-linkedin",
            json={"url": self.VALID_URL, "cookies": self.VALID_COOKIES, "scroll_count": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result_count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["author"] == "John Doe"
        assert data["url"] == self.VALID_URL

    @patch("playwright.async_api.async_playwright")
    def test_scrape_linkedin_handles_timeout(self, mock_playwright, client):
        """Test that navigation timeouts return 500."""
        import asyncio

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        response = client.post(
            "/scrape-linkedin",
            json={"url": self.VALID_URL, "cookies": self.VALID_COOKIES},
        )

        assert response.status_code == 500
        assert "timed out" in response.json()["detail"].lower()

    @patch("pdf_service.app._pdf_semaphore")
    def test_scrape_linkedin_respects_concurrency_limit(self, mock_semaphore, client):
        """Test that scrape endpoint returns 503 when semaphore is full."""
        mock_semaphore._value = 0

        response = client.post(
            "/scrape-linkedin",
            json={"url": self.VALID_URL, "cookies": self.VALID_COOKIES},
        )

        assert response.status_code == 503
        assert "overloaded" in response.json()["detail"].lower()

    @patch("playwright.async_api.async_playwright")
    def test_scrape_linkedin_detects_login_redirect(self, mock_playwright, client):
        """Test that expired cookies (login redirect) return 401."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        # Simulate redirect to login page
        mock_page.url = "https://www.linkedin.com/login?fromSignIn=true"
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_playwright.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            )
        )

        response = client.post(
            "/scrape-linkedin",
            json={"url": self.VALID_URL, "cookies": self.VALID_COOKIES},
        )

        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()


class TestConcurrencyLimits:
    """Tests for concurrency limits and rate limiting."""

    @patch("pdf_service.app._pdf_semaphore")
    def test_render_pdf_respects_concurrency_limit(self, mock_semaphore, client):
        """Test that render-pdf respects MAX_CONCURRENT_PDFS."""
        # Mock semaphore to appear full
        mock_semaphore._value = 0

        response = client.post(
            "/render-pdf",
            json={"html": "<h1>Test</h1>"}
        )

        assert response.status_code == 503
        assert "overloaded" in response.json()["detail"].lower()

    @patch("pdf_service.app._pdf_semaphore")
    def test_cv_to_pdf_respects_concurrency_limit(self, mock_semaphore, client):
        """Test that cv-to-pdf respects MAX_CONCURRENT_PDFS."""
        # Mock semaphore to appear full
        mock_semaphore._value = 0

        tiptap_doc = {"type": "doc", "content": []}

        response = client.post(
            "/cv-to-pdf",
            json={"tiptap_json": tiptap_doc}
        )

        assert response.status_code == 503
        assert "overloaded" in response.json()["detail"].lower()
