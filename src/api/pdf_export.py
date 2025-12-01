"""
PDF export functionality for job dossiers (GAP-033).

Builds structured HTML from JobState and renders to PDF via pdf-service.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

import requests

from src.common.state import JobState

logger = logging.getLogger(__name__)

# PDF service URL (from env or default)
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://localhost:8001")


class DossierPDFExporter:
    """Generate PDF dossiers from JobState."""

    def __init__(self, pdf_service_url: str = None):
        self.pdf_service_url = pdf_service_url or PDF_SERVICE_URL

    def build_dossier_html(self, state: Dict[str, Any]) -> str:
        """
        Build comprehensive HTML dossier from JobState.

        Args:
            state: Complete JobState with all pipeline outputs

        Returns:
            HTML string ready for PDF rendering
        """
        sections = [
            self._build_header(state),
            self._build_company_section(state),
            self._build_role_section(state),
            self._build_job_description_section(state),
            self._build_pain_points_section(state),
            self._build_fit_analysis_section(state),
            self._build_contacts_section(state),
            self._build_outreach_section(state),
            self._build_cv_section(state),
        ]

        body = "\n".join(filter(None, sections))
        return self._wrap_with_html(body)

    def _build_header(self, state: Dict[str, Any]) -> str:
        """Build header with job title and generation timestamp."""
        company = state.get("company", "Unknown Company")
        title = state.get("title", "Unknown Role")
        generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""
        <div class="section header">
            <h1>JOB DOSSIER</h1>
            <p class="subtitle">{title} at {company}</p>
            <p class="timestamp">Generated: {generated_at}</p>
        </div>
        """

    def _build_company_section(self, state: Dict[str, Any]) -> str:
        """Build company information section."""
        company = state.get("company", "N/A")
        job_url = state.get("job_url", "")
        source = state.get("source", "N/A")

        # Extract company research if available
        company_research = state.get("company_research") or {}
        summary = company_research.get("summary", "No company research available.")
        signals = company_research.get("signals", [])

        signals_html = ""
        if signals:
            signals_items = "".join(
                f'<li><strong>{s.get("type", "Signal")}:</strong> {s.get("description", "N/A")} ({s.get("date", "N/A")})</li>'
                for s in signals[:5]  # Limit to 5 signals
            )
            signals_html = f"<ul class='signals'>{signals_items}</ul>"

        return f"""
        <div class="section company">
            <h2>Company Information</h2>
            <table class="info-table">
                <tr><td>Company</td><td>{company}</td></tr>
                <tr><td>Source</td><td>{source}</td></tr>
                <tr><td>Job URL</td><td><a href="{job_url}">{job_url[:60] + '...' if len(job_url) > 60 else job_url}</a></td></tr>
            </table>
            <h3>Research Summary</h3>
            <p>{summary}</p>
            {signals_html}
        </div>
        """

    def _build_role_section(self, state: Dict[str, Any]) -> str:
        """Build role details section."""
        title = state.get("title", "N/A")

        # Extract role research if available
        role_research = state.get("role_research") or {}
        summary = role_research.get("summary", "No role research available.")
        business_impact = role_research.get("business_impact", [])
        why_now = role_research.get("why_now", "")

        impact_html = ""
        if business_impact:
            impact_items = "".join(f"<li>{impact}</li>" for impact in business_impact[:5])
            impact_html = f"<h3>Business Impact</h3><ul>{impact_items}</ul>"

        why_now_html = ""
        if why_now:
            why_now_html = f"<h3>Why Now</h3><p>{why_now}</p>"

        return f"""
        <div class="section role">
            <h2>Role Details</h2>
            <table class="info-table">
                <tr><td>Title</td><td>{title}</td></tr>
            </table>
            <h3>Role Summary</h3>
            <p>{summary}</p>
            {impact_html}
            {why_now_html}
        </div>
        """

    def _build_job_description_section(self, state: Dict[str, Any]) -> str:
        """Build job description section."""
        description = state.get("job_description", "No job description available.")
        # Truncate very long descriptions
        if len(description) > 5000:
            description = description[:5000] + "... [truncated]"

        return f"""
        <div class="section job-description">
            <h2>Job Description</h2>
            <div class="content">{self._escape_html(description).replace(chr(10), '<br>')}</div>
        </div>
        """

    def _build_pain_points_section(self, state: Dict[str, Any]) -> str:
        """Build pain points section with all 4 dimensions."""
        pain_points = state.get("pain_points") or []
        strategic_needs = state.get("strategic_needs") or []
        risks = state.get("risks_if_unfilled") or []
        success_metrics = state.get("success_metrics") or []

        sections = []

        if pain_points:
            items = "".join(f"<li>{self._escape_html(p)}</li>" for p in pain_points)
            sections.append(f"<h3>Pain Points</h3><ul>{items}</ul>")

        if strategic_needs:
            items = "".join(f"<li>{self._escape_html(s)}</li>" for s in strategic_needs)
            sections.append(f"<h3>Strategic Needs</h3><ul>{items}</ul>")

        if risks:
            items = "".join(f"<li>{self._escape_html(r)}</li>" for r in risks)
            sections.append(f"<h3>Risks if Unfilled</h3><ul>{items}</ul>")

        if success_metrics:
            items = "".join(f"<li>{self._escape_html(m)}</li>" for m in success_metrics)
            sections.append(f"<h3>Success Metrics</h3><ul>{items}</ul>")

        if not sections:
            sections.append("<p>No pain points analysis available.</p>")

        return f"""
        <div class="section pain-points">
            <h2>Pain Points Analysis (4 Dimensions)</h2>
            {''.join(sections)}
        </div>
        """

    def _build_fit_analysis_section(self, state: Dict[str, Any]) -> str:
        """Build fit analysis section."""
        fit_score = state.get("fit_score")
        fit_category = state.get("fit_category", "N/A")
        fit_rationale = state.get("fit_rationale", "No fit analysis available.")

        score_display = f"{fit_score}/100" if fit_score is not None else "N/A"

        # Determine score color based on category
        score_class = "score-high" if fit_score and fit_score >= 70 else "score-medium" if fit_score and fit_score >= 50 else "score-low"

        return f"""
        <div class="section fit-analysis">
            <h2>Fit Analysis</h2>
            <div class="score-box {score_class}">
                <span class="score">{score_display}</span>
                <span class="category">{fit_category.replace('_', ' ').title()}</span>
            </div>
            <h3>Rationale</h3>
            <p>{self._escape_html(fit_rationale)}</p>
        </div>
        """

    def _build_contacts_section(self, state: Dict[str, Any]) -> str:
        """Build contacts section."""
        primary_contacts = state.get("primary_contacts") or []
        secondary_contacts = state.get("secondary_contacts") or []

        def format_contacts(contacts: List[Dict]) -> str:
            if not contacts:
                return "<p>No contacts identified.</p>"
            items = []
            for c in contacts:
                name = c.get("name", "Unknown")
                role = c.get("role", "")
                linkedin = c.get("linkedin_url", "")
                email = c.get("email", "")

                contact_info = f"<strong>{name}</strong>"
                if role:
                    contact_info += f" - {role}"
                if linkedin:
                    contact_info += f' <a href="{linkedin}">[LinkedIn]</a>'
                if email:
                    contact_info += f" ({email})"

                items.append(f"<li>{contact_info}</li>")
            return f"<ul>{''.join(items)}</ul>"

        return f"""
        <div class="section contacts">
            <h2>Contacts</h2>
            <h3>Primary Contacts</h3>
            {format_contacts(primary_contacts)}
            <h3>Secondary Contacts</h3>
            {format_contacts(secondary_contacts)}
        </div>
        """

    def _build_outreach_section(self, state: Dict[str, Any]) -> str:
        """Build outreach section with cover letter and messages."""
        cover_letter = state.get("cover_letter", "")
        outreach_packages = state.get("outreach_packages") or []

        sections = []

        if cover_letter:
            sections.append(f"""
            <h3>Cover Letter</h3>
            <div class="content">{self._escape_html(cover_letter).replace(chr(10), '<br>')}</div>
            """)

        if outreach_packages:
            for i, package in enumerate(outreach_packages[:3], 1):
                contact = package.get("contact", {})
                message = package.get("message", "")
                if message:
                    name = contact.get("name", f"Contact {i}")
                    sections.append(f"""
                    <h3>Outreach to {name}</h3>
                    <div class="content">{self._escape_html(message).replace(chr(10), '<br>')}</div>
                    """)

        if not sections:
            sections.append("<p>No outreach materials generated.</p>")

        return f"""
        <div class="section outreach">
            <h2>Outreach Materials</h2>
            {''.join(sections)}
        </div>
        """

    def _build_cv_section(self, state: Dict[str, Any]) -> str:
        """Build CV reasoning section."""
        cv_reasoning = state.get("cv_reasoning", "")
        cv_path = state.get("cv_path", "")

        sections = []

        if cv_path:
            sections.append(f"<p><strong>CV Path:</strong> {cv_path}</p>")

        if cv_reasoning:
            sections.append(f"""
            <h3>CV Tailoring Rationale</h3>
            <div class="content">{self._escape_html(cv_reasoning).replace(chr(10), '<br>')}</div>
            """)

        if not sections:
            sections.append("<p>No CV information available.</p>")

        return f"""
        <div class="section cv">
            <h2>CV Information</h2>
            {''.join(sections)}
        </div>
        """

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _wrap_with_html(self, body: str) -> str:
        """Wrap content in HTML document with PDF styling."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Job Dossier</title>
    <style>
        @page {{
            size: A4;
            margin: 20mm;
        }}

        * {{
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}

        body {{
            font-size: 11pt;
            line-height: 1.5;
            color: #333;
            margin: 0;
            padding: 0;
        }}

        .header {{
            text-align: center;
            border-bottom: 2px solid #2563eb;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}

        .header h1 {{
            margin: 0;
            color: #1e40af;
            font-size: 24pt;
        }}

        .header .subtitle {{
            font-size: 14pt;
            color: #4b5563;
            margin: 10px 0 5px 0;
        }}

        .header .timestamp {{
            font-size: 9pt;
            color: #9ca3af;
            margin: 0;
        }}

        .section {{
            margin-bottom: 25px;
            page-break-inside: avoid;
        }}

        .section h2 {{
            color: #1e40af;
            border-bottom: 1px solid #dbeafe;
            padding-bottom: 5px;
            margin-top: 0;
            font-size: 14pt;
        }}

        .section h3 {{
            color: #374151;
            margin-top: 15px;
            margin-bottom: 5px;
            font-size: 11pt;
        }}

        .info-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}

        .info-table td {{
            padding: 5px 10px;
            border-bottom: 1px solid #e5e7eb;
        }}

        .info-table td:first-child {{
            font-weight: bold;
            width: 150px;
            color: #4b5563;
        }}

        ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}

        li {{
            margin-bottom: 5px;
        }}

        .signals li {{
            font-size: 10pt;
        }}

        .content {{
            background: #f9fafb;
            padding: 10px 15px;
            border-radius: 5px;
            border-left: 3px solid #2563eb;
        }}

        .score-box {{
            display: inline-block;
            padding: 15px 25px;
            border-radius: 8px;
            text-align: center;
            margin: 10px 0;
        }}

        .score-high {{
            background: #dcfce7;
            border: 2px solid #22c55e;
        }}

        .score-medium {{
            background: #fef3c7;
            border: 2px solid #f59e0b;
        }}

        .score-low {{
            background: #fee2e2;
            border: 2px solid #ef4444;
        }}

        .score {{
            display: block;
            font-size: 24pt;
            font-weight: bold;
            color: #1f2937;
        }}

        .category {{
            display: block;
            font-size: 10pt;
            color: #4b5563;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        a {{
            color: #2563eb;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
{body}
</body>
</html>
        """

    def export_to_pdf(self, state: Dict[str, Any]) -> bytes:
        """
        Export JobState as PDF via pdf-service (synchronous version).

        Args:
            state: JobState with all outputs

        Returns:
            PDF binary content
        """
        html = self.build_dossier_html(state)

        try:
            response = requests.post(
                f"{self.pdf_service_url}/render-pdf",
                json={"html": html},
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(f"PDF service error: {response.status_code} - {response.text[:200]}")
                raise Exception(f"PDF service error: {response.status_code}")

            return response.content

        except requests.exceptions.Timeout:
            logger.error("PDF service timeout")
            raise Exception("PDF service timeout - please try again")

        except requests.exceptions.ConnectionError:
            logger.error("PDF service unavailable")
            raise Exception("PDF service unavailable")
