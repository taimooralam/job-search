"""
PDF Service - FastAPI application for PDF generation and LinkedIn scraping.

Provides endpoints for converting HTML/CSS and TipTap JSON to PDF
using Playwright/Chromium, plus a LinkedIn search scraper endpoint.
"""

import asyncio
import logging
import os
import random
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from io import BytesIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PDF Service",
    version="0.1.0",
    description="Dedicated PDF generation service using Playwright/Chromium"
)

# Configuration
MAX_CONCURRENT_PDFS = int(os.getenv("MAX_CONCURRENT_PDFS", "5"))
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))  # milliseconds
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"

# Semaphore for rate limiting
_pdf_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PDFS)

# Playwright readiness state
_playwright_ready = False
_playwright_error: Optional[str] = None


# ============================================================================
# Startup Event - Validate Playwright
# ============================================================================

@app.on_event("startup")
async def validate_playwright_on_startup():
    """
    Validate Playwright/Chromium is properly installed on startup.

    This ensures the service won't report as healthy if Playwright can't
    actually generate PDFs.
    """
    global _playwright_ready, _playwright_error

    logger.info("PDF Service starting - validating Playwright installation...")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            logger.info("Launching Chromium for validation...")
            browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
            page = await browser.new_page()

            # Render a simple test page
            await page.set_content("<html><body><h1>Test</h1></body></html>")

            # Generate a small test PDF
            # Note: timeout param not supported in all Playwright versions
            test_pdf = await page.pdf(format='Letter')

            await browser.close()

            if len(test_pdf) > 0:
                _playwright_ready = True
                logger.info(f"✅ Playwright validation successful - generated {len(test_pdf)} byte test PDF")
            else:
                _playwright_error = "Test PDF generation returned empty result"
                logger.error(f"❌ Playwright validation failed: {_playwright_error}")

    except Exception as e:
        _playwright_error = str(e)
        logger.error(f"❌ Playwright validation failed: {_playwright_error}")
        logger.error("PDF generation will not work until this is resolved.")


# ============================================================================
# Request/Response Models
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime
    active_renders: int
    max_concurrent: int
    playwright_ready: bool = True
    playwright_error: Optional[str] = None


class RenderPDFRequest(BaseModel):
    """Generic HTML/CSS to PDF request."""
    html: str = Field(..., description="HTML content to render")
    css: Optional[str] = Field(None, description="Additional CSS styles")
    pageSize: str = Field("letter", description="Page size: 'letter' or 'a4'")
    printBackground: bool = Field(True, description="Print background colors/images")


class CVToPDFRequest(BaseModel):
    """TipTap JSON to PDF request for CVs."""
    tiptap_json: Dict = Field(..., description="TipTap document JSON")
    documentStyles: Dict = Field(
        default_factory=lambda: {
            "fontFamily": "Inter",
            "fontSize": 11,
            "lineHeight": 1.15,
            "margins": {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0},
            "pageSize": "letter"
        },
        description="Document styling options"
    )
    header: Optional[str] = Field(None, description="Optional header text")
    footer: Optional[str] = Field(None, description="Optional footer text")
    company: Optional[str] = Field(None, description="Company name for filename")
    role: Optional[str] = Field(None, description="Role title for filename")


class URLToPDFRequest(BaseModel):
    """URL to PDF request for capturing web pages."""
    url: str = Field(..., description="URL to render as PDF")
    pageSize: str = Field("letter", description="Page size: 'letter' or 'a4'")
    printBackground: bool = Field(True, description="Print background colors/images")
    waitForSelector: Optional[str] = Field(None, description="Optional CSS selector to wait for")


class LinkedInScrapeRequest(BaseModel):
    """Request to scrape LinkedIn search results via Playwright."""
    url: str = Field(..., description="Full LinkedIn search URL")
    cookies: List[dict] = Field(..., description='Playwright cookies, e.g. [{"name":"li_at","value":"...","domain":".linkedin.com","path":"/"}]')
    scroll_count: int = Field(2, ge=0, le=5, description="Number of scrolls for lazy-loaded results")


class LinkedInScrapeResponse(BaseModel):
    """Response from LinkedIn scrape endpoint."""
    results: List[dict]
    result_count: int
    url: str


# ============================================================================
# Health Check Endpoint
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for container orchestration.

    Returns service status, capacity information, and Playwright readiness.
    Returns HTTP 503 if Playwright validation failed on startup.
    """
    # If Playwright is not ready, return 503 Service Unavailable
    if not _playwright_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "active_renders": MAX_CONCURRENT_PDFS - _pdf_semaphore._value,
                "max_concurrent": MAX_CONCURRENT_PDFS,
                "playwright_ready": False,
                "playwright_error": _playwright_error,
                "message": "PDF service is unhealthy - Playwright/Chromium not available"
            }
        )

    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        active_renders=MAX_CONCURRENT_PDFS - _pdf_semaphore._value,
        max_concurrent=MAX_CONCURRENT_PDFS,
        playwright_ready=True,
        playwright_error=None
    )


# ============================================================================
# PDF Generation Endpoints
# ============================================================================

@app.post("/render-pdf")
async def render_pdf(request: RenderPDFRequest):
    """
    Generic HTML/CSS to PDF endpoint.

    Converts arbitrary HTML content to PDF with specified page settings.

    Args:
        request: HTML content, CSS, and page settings

    Returns:
        StreamingResponse with PDF binary data

    Raises:
        HTTPException: 400 for invalid input, 500 for rendering failures, 503 for overload
    """
    # Validate input
    if not request.html or not request.html.strip():
        raise HTTPException(status_code=400, detail="HTML content is required")

    # Check capacity
    if _pdf_semaphore._value <= 0:
        logger.warning("PDF service overloaded, rejecting request")
        raise HTTPException(
            status_code=503,
            detail="Service overloaded. Too many concurrent PDF operations."
        )

    async with _pdf_semaphore:
        try:
            logger.info(f"Starting generic PDF render (pageSize={request.pageSize})")

            # Import here to avoid loading Playwright on startup
            from playwright.async_api import async_playwright

            # Build complete HTML with CSS
            full_html = request.html
            if request.css:
                full_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>{request.css}</style>
                </head>
                <body>
                    {request.html}
                </body>
                </html>
                """

            # Generate PDF
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
                page = await browser.new_page()

                await page.set_content(full_html, wait_until='networkidle')
                await page.wait_for_load_state('networkidle')

                pdf_format = 'A4' if request.pageSize.lower() == 'a4' else 'Letter'
                # Set page timeout before PDF generation
                page.set_default_timeout(PLAYWRIGHT_TIMEOUT)
                pdf_bytes = await page.pdf(
                    format=pdf_format,
                    print_background=request.printBackground
                )

                await browser.close()

            logger.info("Generic PDF render completed successfully")

            return StreamingResponse(
                BytesIO(pdf_bytes),
                media_type='application/pdf',
                headers={
                    'Content-Disposition': 'attachment; filename="document.pdf"'
                }
            )

        except asyncio.TimeoutError:
            logger.error("PDF rendering timed out")
            raise HTTPException(
                status_code=500,
                detail=f"Rendering timed out after {PLAYWRIGHT_TIMEOUT}ms"
            )
        except Exception as e:
            logger.error(f"PDF rendering failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Rendering failed: {str(e)}"
            )


@app.post("/cv-to-pdf")
async def cv_to_pdf(request: CVToPDFRequest):
    """
    Convert TipTap JSON CV to PDF.

    Specialized endpoint for CV export with full styling support.

    Args:
        request: TipTap document JSON and styling options

    Returns:
        StreamingResponse with PDF binary data

    Raises:
        HTTPException: 400 for invalid input, 500 for rendering failures, 503 for overload
    """
    # Validate input
    if not request.tiptap_json:
        raise HTTPException(status_code=400, detail="tiptap_json is required")

    if request.tiptap_json.get("type") != "doc":
        raise HTTPException(status_code=400, detail="Invalid TipTap document format")

    # Check capacity
    if _pdf_semaphore._value <= 0:
        logger.warning("PDF service overloaded, rejecting CV request")
        raise HTTPException(
            status_code=503,
            detail="Service overloaded. Too many concurrent PDF operations."
        )

    async with _pdf_semaphore:
        try:
            logger.info(f"Starting CV PDF generation (company={request.company}, role={request.role})")

            # Import helpers
            from .pdf_helpers import (
                tiptap_json_to_html,
                build_pdf_html_template,
                sanitize_for_path
            )
            from playwright.async_api import async_playwright

            # Convert TipTap JSON to HTML
            try:
                html_content = tiptap_json_to_html(request.tiptap_json)
            except RecursionError:
                logger.error("CV document structure too deeply nested")
                raise HTTPException(
                    status_code=400,
                    detail="CV document structure is too deeply nested. Please simplify the document."
                )
            except Exception as e:
                logger.error(f"Failed to convert TipTap to HTML: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to process CV content: {str(e)}"
                )

            # Extract document styles
            doc_styles = request.documentStyles
            page_size = doc_styles.get("pageSize", "letter")
            margins = doc_styles.get("margins", {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0})
            line_height = doc_styles.get("lineHeight", 1.15)
            font_family = doc_styles.get("fontFamily", "Inter")
            font_size = doc_styles.get("fontSize", 11)

            # Build complete HTML document
            full_html = build_pdf_html_template(
                html_content,
                font_family,
                font_size,
                line_height,
                request.header or "",
                request.footer or "",
                page_size,
                margins
            )

            # Generate PDF
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
                page = await browser.new_page()

                await page.set_content(full_html, wait_until='networkidle')
                await page.wait_for_load_state('networkidle')

                pdf_format = 'A4' if page_size.lower() == 'a4' else 'Letter'
                # Set page timeout before PDF generation
                page.set_default_timeout(PLAYWRIGHT_TIMEOUT)
                pdf_bytes = await page.pdf(
                    format=pdf_format,
                    print_background=True,
                    margin={
                        'top': f"{margins.get('top') or 1.0}in",
                        'right': f"{margins.get('right') or 1.0}in",
                        'bottom': f"{margins.get('bottom') or 1.0}in",
                        'left': f"{margins.get('left') or 1.0}in"
                    }
                )

                await browser.close()

            # Build filename
            if request.company and request.role:
                company_clean = sanitize_for_path(request.company)
                role_clean = sanitize_for_path(request.role)
                filename = f"CV_{company_clean}_{role_clean}.pdf"
            else:
                filename = "CV.pdf"

            logger.info(f"CV PDF generation completed: {filename}")

            return StreamingResponse(
                BytesIO(pdf_bytes),
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )

        except HTTPException:
            raise
        except asyncio.TimeoutError:
            logger.error("CV PDF rendering timed out")
            raise HTTPException(
                status_code=500,
                detail=f"Rendering timed out after {PLAYWRIGHT_TIMEOUT}ms"
            )
        except Exception as e:
            logger.error(f"CV PDF generation failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"PDF generation failed: {str(e)}"
            )


@app.post("/url-to-pdf")
async def url_to_pdf(request: URLToPDFRequest):
    """
    Render a URL to PDF (for job posting export).

    Navigates to the specified URL and captures the page as PDF.
    Useful for saving job postings that may disappear.

    Args:
        request: URL and page settings

    Returns:
        StreamingResponse with PDF binary data

    Raises:
        HTTPException: 400 for invalid URL, 500 for rendering failures, 503 for overload
    """
    # Validate URL
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    if not request.url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # Check capacity
    if _pdf_semaphore._value <= 0:
        logger.warning("PDF service overloaded, rejecting URL request")
        raise HTTPException(
            status_code=503,
            detail="Service overloaded. Too many concurrent PDF operations."
        )

    async with _pdf_semaphore:
        try:
            logger.info(f"Starting URL to PDF render: {request.url[:100]}...")

            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
                page = await browser.new_page()

                # Set timeout
                page.set_default_timeout(PLAYWRIGHT_TIMEOUT)

                # Navigate to URL
                try:
                    await page.goto(request.url, wait_until='networkidle')
                except Exception as nav_error:
                    # Some sites block navigation - try with domcontentloaded
                    logger.warning(f"networkidle navigation failed, trying domcontentloaded: {nav_error}")
                    await page.goto(request.url, wait_until='domcontentloaded')

                # Wait for optional selector
                if request.waitForSelector:
                    try:
                        await page.wait_for_selector(request.waitForSelector, timeout=10000)
                    except Exception:
                        logger.warning(f"Selector {request.waitForSelector} not found, continuing anyway")

                # Small delay to ensure page is fully rendered
                await asyncio.sleep(1)

                # Generate PDF
                pdf_format = 'A4' if request.pageSize.lower() == 'a4' else 'Letter'
                pdf_bytes = await page.pdf(
                    format=pdf_format,
                    print_background=request.printBackground
                )

                await browser.close()

            logger.info(f"URL to PDF completed: {len(pdf_bytes)} bytes")

            # Extract domain for filename
            from urllib.parse import urlparse
            domain = urlparse(request.url).netloc.replace('.', '_')
            filename = f"job_posting_{domain}.pdf"

            return StreamingResponse(
                BytesIO(pdf_bytes),
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )

        except HTTPException:
            raise
        except asyncio.TimeoutError:
            logger.error(f"URL to PDF timed out: {request.url}")
            raise HTTPException(
                status_code=500,
                detail=f"Page load timed out after {PLAYWRIGHT_TIMEOUT}ms. The site may be slow or blocking automation."
            )
        except Exception as e:
            logger.error(f"URL to PDF failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"PDF generation failed: {str(e)}"
            )


# ============================================================================
# LinkedIn Scraping Endpoint
# ============================================================================

# JavaScript executed inside the browser to extract search results.
# Uses multiple fallback selectors to handle LinkedIn DOM changes.
_LINKEDIN_EXTRACT_JS = """
() => {
    const selectors = [
        '.search-results-container .reusable-search__result-container',
        '.search-results-container li.reusable-search__result-container',
        '[data-chameleon-result-urn]',
        '.scaffold-finite-scroll__content > li',
        '.search-results-container > div > ul > li',
        // Broader fallbacks for newer LinkedIn layouts
        '[class*="search-result"]',
        '[class*="feed-shared-update"]',
        'main [class*="artdeco-list"] > li',
        'main ul > li',
    ];

    let containers = [];
    let matchedSelector = '';
    for (const sel of selectors) {
        const found = document.querySelectorAll(sel);
        if (found.length > 0) {
            containers = found;
            matchedSelector = sel;
            break;
        }
    }

    const results = [];
    for (const el of containers) {
        const text = (el.innerText || '').trim();
        if (!text || text.length < 30) continue;

        // Try to find the post/content link
        let url = '';
        const allLinks = el.querySelectorAll('a[href]');
        for (const a of allLinks) {
            const href = a.getAttribute('href') || '';
            if (href.includes('/feed/update/') || href.includes('/posts/') || href.includes('/pulse/')) {
                url = href.startsWith('http') ? href : 'https://www.linkedin.com' + href;
                break;
            }
        }
        // Fallback: first link with linkedin.com
        if (!url) {
            for (const a of allLinks) {
                const href = a.getAttribute('href') || '';
                if (href.includes('linkedin.com') && !href.includes('/search/')) {
                    url = href;
                    break;
                }
            }
        }

        // Try to extract author from actor/header area
        let author = '';
        const authorSelectors = [
            '.update-components-actor__name',
            '.feed-shared-actor__name',
            '[data-anonymize="person-name"]',
            'span[class*="actor-name"]',
            'a[class*="actor"] span',
        ];
        for (const aSel of authorSelectors) {
            const actorEl = el.querySelector(aSel);
            if (actorEl) {
                author = (actorEl.innerText || '').split('\\n')[0].trim();
                if (author) break;
            }
        }

        // Try to extract engagement counts
        let reactions = '';
        const socialEl = el.querySelector('[class*="social-details"], [class*="social-counts"]');
        if (socialEl) {
            reactions = (socialEl.innerText || '').trim();
        }

        results.push({text, url, author, reactions, _selector: matchedSelector});
    }
    return results;
}
"""


@app.post("/scrape-linkedin", response_model=LinkedInScrapeResponse)
async def scrape_linkedin(request: LinkedInScrapeRequest):
    """
    Scrape LinkedIn search results using Playwright with cookie auth.

    Navigates to a LinkedIn search URL with injected session cookies,
    scrolls to load lazy content, then extracts post data from the DOM.

    Args:
        request: LinkedIn URL, cookies, and scroll settings

    Returns:
        JSON with extracted search results

    Raises:
        HTTPException: 400 for invalid input, 401 for expired cookies,
                       500 for navigation errors, 503 for overload
    """
    # Validate URL is LinkedIn
    if not request.url.startswith("https://www.linkedin.com/"):
        raise HTTPException(status_code=400, detail="URL must be a LinkedIn URL (https://www.linkedin.com/...)")

    # Validate li_at cookie is present
    has_li_at = any(c.get("name") == "li_at" and c.get("value") for c in request.cookies)
    if not request.cookies:
        raise HTTPException(status_code=400, detail="Cookies are required")
    if not has_li_at:
        raise HTTPException(status_code=400, detail="li_at cookie is required for LinkedIn authentication")

    # Check capacity
    if _pdf_semaphore._value <= 0:
        logger.warning("Service overloaded, rejecting LinkedIn scrape request")
        raise HTTPException(
            status_code=503,
            detail="Service overloaded. Too many concurrent operations."
        )

    async with _pdf_semaphore:
        try:
            logger.info(f"Starting LinkedIn scrape: {request.url[:100]}...")

            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                )
                await context.add_cookies(request.cookies)
                page = await context.new_page()
                page.set_default_timeout(PLAYWRIGHT_TIMEOUT)

                # Navigate — LinkedIn blocks networkidle, use domcontentloaded
                await page.goto(request.url, wait_until="domcontentloaded")

                # Detect login redirect (cookies expired)
                current_url = page.url
                page_title = await page.title()
                logger.info(f"LinkedIn navigation complete — URL: {current_url[:120]}, title: {page_title[:80]}")

                if "/login" in current_url or "/checkpoint" in current_url:
                    await browser.close()
                    raise HTTPException(
                        status_code=401,
                        detail="LinkedIn session expired — cookies are no longer valid"
                    )

                # Wait for search results to appear
                result_selectors = [
                    ".search-results-container",
                    ".scaffold-finite-scroll__content",
                    "main ul > li",
                ]
                matched_selector = None
                for sel in result_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=10000)
                        matched_selector = sel
                        logger.info(f"Matched selector: {sel}")
                        break
                    except Exception:
                        continue

                if not matched_selector:
                    # Log page state for debugging
                    body_text = await page.evaluate("() => (document.body?.innerText || '').substring(0, 500)")
                    logger.warning(f"No search result selector matched. Body preview: {body_text[:300]}")

                # Wait for dynamic content to render
                await asyncio.sleep(3)

                # Scroll to trigger lazy loading
                for i in range(request.scroll_count):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2 + random.random())

                # Small settle after last scroll
                await asyncio.sleep(1)

                # Extract results via JS
                results = await page.evaluate(_LINKEDIN_EXTRACT_JS)

                if not results:
                    # Capture DOM structure for debugging selector mismatches
                    dom_debug = await page.evaluate("""() => {
                        const main = document.querySelector('main') || document.body;
                        const walk = (el, depth) => {
                            if (depth > 4) return '';
                            const tag = el.tagName?.toLowerCase() || '';
                            const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).slice(0, 3).join('.') : '';
                            const kids = el.children ? Array.from(el.children).length : 0;
                            const textLen = (el.innerText || '').length;
                            let out = '  '.repeat(depth) + `<${tag}${cls}> children=${kids} textLen=${textLen}\\n`;
                            if (depth < 3 && el.children) {
                                for (const child of Array.from(el.children).slice(0, 10)) {
                                    out += walk(child, depth + 1);
                                }
                            }
                            return out;
                        };
                        return walk(main, 0).substring(0, 2000);
                    }""")
                    logger.warning(f"0 results extracted. DOM structure:\\n{dom_debug}")

                await browser.close()

            logger.info(f"LinkedIn scrape completed: {len(results)} results extracted")

            return LinkedInScrapeResponse(
                results=results,
                result_count=len(results),
                url=request.url,
            )

        except HTTPException:
            raise
        except asyncio.TimeoutError:
            logger.error(f"LinkedIn scrape timed out: {request.url}")
            raise HTTPException(
                status_code=500,
                detail=f"LinkedIn page load timed out after {PLAYWRIGHT_TIMEOUT}ms"
            )
        except Exception as e:
            logger.error(f"LinkedIn scrape failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"LinkedIn scrape failed: {str(e)}"
            )
