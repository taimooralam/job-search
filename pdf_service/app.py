"""
PDF Service - FastAPI application for PDF generation.

Provides endpoints for converting HTML/CSS and TipTap JSON to PDF
using Playwright/Chromium.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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
