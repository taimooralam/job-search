"""
Dossier Generator (Phase 10 - 10-Section Roadmap Spec)

Creates comprehensive opportunity dossier documents with all pipeline outputs.
Formats data for human readability and downstream processing.

Enhanced sections (22 Nov 2025):
1. Pain → Proof → Plan block at top
2. Job requirements/criteria and role research
3. Opportunity mapper details with pain→STAR mapping
4. People & outreach using primary/secondary contacts and outreach_packages
5. Application form fields (if available from Layer 1.5)
6. Master-CV fallback note when STAR selector disabled
"""

from datetime import datetime
from typing import List, Dict, Optional
from src.common.config import Config
from src.common.state import JobState, STARRecord, Contact, OutreachPackage


class DossierGenerator:
    """
    Generates formatted opportunity dossiers from pipeline state.

    Produces human-readable text files with all analysis, research,
    and generated outputs organized by section.

    10-Section Structure (Phase 10):
    1. Pain → Proof → Plan (Executive Summary)
    2. Job Summary & Requirements
    3. Pain Point Analysis (4 Dimensions)
    4. Role Research (Why Now, Business Impact)
    5. Selected STAR Achievements / Master-CV Fallback
    6. Company Overview & Signals
    7. Fit Analysis (Opportunity Mapper)
    8. People & Outreach (Primary/Secondary Contacts)
    9. Cover Letter
    10. Metadata & Application Form Fields
    """

    def generate_dossier(self, state: JobState) -> str:
        """
        Generate complete opportunity dossier (10-section structure).

        Args:
            state: Final JobState with all outputs

        Returns:
            Formatted dossier as string
        """
        sections = []

        # Header
        sections.append(self._generate_header(state))

        # 1. Pain → Proof → Plan (NEW - Executive Summary)
        sections.append(self._generate_pain_proof_plan_section(state))

        # 2. Job Summary & Requirements
        sections.append(self._generate_job_summary(state))

        # 3. Pain Point Analysis (4 Dimensions)
        sections.append(self._generate_pain_points_section(state))

        # 4. Role Research (NEW - Why Now, Business Impact)
        sections.append(self._generate_role_research_section(state))

        # 5. Selected STAR Achievements / Master-CV Fallback
        sections.append(self._generate_selected_stars_section(state))

        # 6. Company Overview & Signals
        sections.append(self._generate_company_section(state))

        # 7. Fit Analysis (Opportunity Mapper)
        sections.append(self._generate_fit_analysis_section(state))

        # 8. People & Outreach (Primary/Secondary + OutreachPackages)
        sections.append(self._generate_contacts_section(state))

        # 9. Cover Letter
        sections.append(self._generate_cover_letter_section(state))

        # 10. Metadata & Application Form Fields
        sections.append(self._generate_metadata_section(state))

        # Join all sections
        return "\n\n".join(sections)

    def _generate_header(self, state: JobState) -> str:
        """Generate dossier header."""
        lines = []
        lines.append("=" * 80)
        lines.append("OPPORTUNITY DOSSIER")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Company: {state['company']}")
        lines.append(f"Role: {state['title']}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if state.get('fit_score'):
            lines.append(f"Fit Score: {state['fit_score']}/100")

        lines.append("=" * 80)
        return "\n".join(lines)

    def _generate_pain_proof_plan_section(self, state: JobState) -> str:
        """Generate Pain → Proof → Plan executive summary (NEW - Phase 10)."""
        lines = []
        lines.append("=" * 80)
        lines.append("1. PAIN → PROOF → PLAN (Executive Summary)")
        lines.append("=" * 80)
        lines.append("")

        # PAIN: Top 2-3 pain points
        pain_points = state.get('pain_points', [])
        lines.append("📍 PAIN (What They Need)")
        lines.append("-" * 40)
        if pain_points:
            for pain in pain_points[:3]:
                lines.append(f"  • {pain}")
        else:
            lines.append("  • Pain points not yet extracted")
        lines.append("")

        # PROOF: Top STAR metrics or master-CV highlights
        lines.append("✓ PROOF (Why I'm the Solution)")
        lines.append("-" * 40)
        selected_stars = state.get('selected_stars', [])
        if selected_stars and Config.ENABLE_STAR_SELECTOR:
            for star in selected_stars[:2]:
                metrics = star.get('metrics', 'N/A')
                if isinstance(metrics, list):
                    metrics = '; '.join(metrics[:2])
                lines.append(f"  • {star.get('company', 'N/A')}: {metrics}")
        else:
            # Master-CV fallback
            fit_rationale = state.get('fit_rationale', '')
            if fit_rationale:
                # Extract first sentence with metrics
                import re
                metric_sentences = re.findall(r'[^.]*\d+[%xX]?[^.]*\.', fit_rationale)
                for sentence in metric_sentences[:2]:
                    lines.append(f"  • {sentence.strip()}")
            if not fit_rationale or not metric_sentences:
                lines.append("  • Using master-CV achievements (STAR selector disabled)")
        lines.append("")

        # PLAN: Outreach strategy summary
        lines.append("📋 PLAN (Next Steps)")
        lines.append("-" * 40)
        primary_count = len(state.get('primary_contacts', []))
        secondary_count = len(state.get('secondary_contacts', []))
        outreach_count = len(state.get('outreach_packages', []))

        if primary_count or secondary_count:
            lines.append(f"  • {primary_count} primary contacts + {secondary_count} secondary contacts identified")
            lines.append(f"  • {outreach_count} personalized outreach packages prepared")
        else:
            lines.append("  • Contacts and outreach to be generated")

        if state.get('cover_letter'):
            lines.append("  • Cover letter ready")
        if state.get('cv_path'):
            lines.append(f"  • Tailored CV at: {state.get('cv_path')}")
        lines.append("")

        return "\n".join(lines)

    def _generate_job_summary(self, state: JobState) -> str:
        """Generate job summary section."""
        lines = []
        lines.append("=" * 80)
        lines.append("2. JOB SUMMARY & REQUIREMENTS")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Title: {state['title']}")
        lines.append(f"Company: {state['company']}")
        lines.append(f"Source: {state.get('source', 'unknown')}")
        lines.append(f"Job URL: {state.get('job_url', 'N/A')}")
        lines.append(f"Job ID: {state['job_id']}")
        lines.append("")
        lines.append("Job Description:")
        lines.append("-" * 80)
        lines.append(state['job_description'])
        if state.get('scraped_job_posting'):
            lines.append("")
            lines.append("Scraped Job Posting (from job URL):")
            lines.append("-" * 80)
            lines.append(state.get('scraped_job_posting', '')[:4000])
        return "\n".join(lines)

    def _generate_pain_points_section(self, state: JobState) -> str:
        """Generate pain points analysis section (Phase 1.3 - 4 dimensions)."""
        lines = []
        lines.append("=" * 80)
        lines.append("3. PAIN POINT ANALYSIS (4 Dimensions)")
        lines.append("=" * 80)
        lines.append("")

        # Dimension 1: Pain Points
        pain_points = state.get('pain_points', [])
        lines.append("A. KEY PAIN POINTS (Current Problems)")
        lines.append("-" * 80)
        if pain_points:
            for i, point in enumerate(pain_points, 1):
                lines.append(f"{i}. {point}")
        else:
            lines.append("Not extracted.")
        lines.append("")

        # Dimension 2: Strategic Needs
        strategic_needs = state.get('strategic_needs', [])
        lines.append("B. STRATEGIC NEEDS (Why This Role Matters)")
        lines.append("-" * 80)
        if strategic_needs:
            for i, need in enumerate(strategic_needs, 1):
                lines.append(f"{i}. {need}")
        else:
            lines.append("Not extracted.")
        lines.append("")

        # Dimension 3: Risks if Unfilled
        risks = state.get('risks_if_unfilled', [])
        lines.append("C. RISKS IF UNFILLED (Consequences of Not Hiring)")
        lines.append("-" * 80)
        if risks:
            for i, risk in enumerate(risks, 1):
                lines.append(f"{i}. {risk}")
        else:
            lines.append("Not extracted.")
        lines.append("")

        # Dimension 4: Success Metrics
        metrics = state.get('success_metrics', [])
        lines.append("D. SUCCESS METRICS (How They'll Measure Success)")
        lines.append("-" * 80)
        if metrics:
            for i, metric in enumerate(metrics, 1):
                lines.append(f"{i}. {metric}")
        else:
            lines.append("Not extracted.")

        return "\n".join(lines)

    def _generate_role_research_section(self, state: JobState) -> str:
        """Generate role research section (NEW - Phase 10)."""
        lines = []
        lines.append("=" * 80)
        lines.append("4. ROLE RESEARCH (Why Now & Business Impact)")
        lines.append("=" * 80)
        lines.append("")

        role_research = state.get('role_research', {})

        if role_research:
            # Summary
            if role_research.get('summary'):
                lines.append("ROLE SUMMARY")
                lines.append("-" * 40)
                lines.append(role_research['summary'])
                lines.append("")

            # Why Now
            if role_research.get('why_now'):
                lines.append("WHY NOW (Timing & Urgency)")
                lines.append("-" * 40)
                lines.append(role_research['why_now'])
                lines.append("")

            # Business Impact
            business_impact = role_research.get('business_impact', [])
            if business_impact:
                lines.append("BUSINESS IMPACT")
                lines.append("-" * 40)
                for i, impact in enumerate(business_impact, 1):
                    lines.append(f"{i}. {impact}")
                lines.append("")
        else:
            lines.append("Role research not available.")
            lines.append("")

        return "\n".join(lines)

    def _generate_selected_stars_section(self, state: JobState) -> str:
        """Generate selected STAR achievements section (NEW - Phase 1.3)."""
        lines = []
        lines.append("=" * 80)
        lines.append("5. SELECTED STAR ACHIEVEMENTS")
        lines.append("=" * 80)
        lines.append("")
        lines.append("Top 2-3 achievements most relevant to this role:")
        lines.append("")

        selected_stars = state.get('selected_stars', [])

        if not Config.ENABLE_STAR_SELECTOR or not selected_stars:
            lines.append("STAR selector disabled — using master CV achievements instead.")
            return "\n".join(lines)

        for i, star in enumerate(selected_stars, 1):
            lines.append("-" * 80)
            lines.append(f"STAR #{i}")
            lines.append("-" * 80)
            lines.append("")
            lines.append(f"ID: {star['id']}")
            lines.append(f"Company: {star['company']}")
            lines.append(f"Role: {star['role']}")
            lines.append(f"Period: {star['period']}")
            lines.append(f"Domain: {star['domain_areas']}")
            lines.append("")
            lines.append("SITUATION:")
            lines.append(star['situation'])
            lines.append("")
            lines.append("TASK:")
            lines.append(star['task'])
            lines.append("")
            lines.append("ACTIONS:")
            lines.append(star['actions'])
            lines.append("")
            lines.append("RESULTS:")
            lines.append(star['results'])
            lines.append("")
            lines.append("KEY METRICS:")
            lines.append(star['metrics'])
            lines.append("")

        # Add pain point mapping if available
        mapping = state.get('star_to_pain_mapping', {})
        if mapping:
            lines.append("-" * 80)
            lines.append("PAIN POINT → STAR MAPPING")
            lines.append("-" * 80)
            lines.append("")
            for pain_point, star_ids in mapping.items():
                lines.append(f"{pain_point}:")
                for star_id in star_ids:
                    lines.append(f"  - {star_id}")
            lines.append("")

        return "\n".join(lines)

    def _generate_company_section(self, state: JobState) -> str:
        """Generate company overview section."""
        lines = []
        lines.append("=" * 80)
        lines.append("6. COMPANY OVERVIEW & SIGNALS")
        lines.append("=" * 80)
        lines.append("")

        if state.get('company_url'):
            lines.append(f"Company URL: {state['company_url']}")
            lines.append("")

        if state.get('company_summary'):
            lines.append("Summary:")
            lines.append(state['company_summary'])
            lines.append("")

        # Company Signals (NEW - Phase 10)
        company_research = state.get('company_research', {})
        signals = company_research.get('signals', [])
        if signals:
            lines.append("COMPANY SIGNALS")
            lines.append("-" * 40)
            for signal in signals:
                signal_type = signal.get('type', 'unknown')
                description = signal.get('description', 'N/A')
                lines.append(f"  [{signal_type.upper()}] {description}")
            lines.append("")

        if not state.get('company_summary') and not signals:
            lines.append("No company research available.")

        return "\n".join(lines)

    def _generate_fit_analysis_section(self, state: JobState) -> str:
        """Generate fit analysis section (Opportunity Mapper output)."""
        lines = []
        lines.append("=" * 80)
        lines.append("7. FIT ANALYSIS (Opportunity Mapper)")
        lines.append("=" * 80)
        lines.append("")

        if state.get('fit_score') is not None:
            lines.append(f"Fit Score: {state['fit_score']}/100")

            # Fit category (Phase 6)
            fit_category = state.get('fit_category', '')
            if fit_category:
                lines.append(f"Fit Category: {fit_category.upper()}")
            lines.append("")

            # Score interpretation
            score = state['fit_score']
            if score >= 90:
                interpretation = "Exceptional fit - rare alignment"
            elif score >= 80:
                interpretation = "Strong fit - highly qualified"
            elif score >= 70:
                interpretation = "Good fit - meets most requirements"
            elif score >= 60:
                interpretation = "Moderate fit - some gaps"
            elif score >= 50:
                interpretation = "Weak fit - significant gaps"
            else:
                interpretation = "Poor fit - major misalignment"

            lines.append(f"Interpretation: {interpretation}")
            lines.append("")

        if state.get('fit_rationale'):
            lines.append("Rationale:")
            lines.append(state['fit_rationale'])
        else:
            lines.append("No fit analysis available.")

        return "\n".join(lines)

    def _generate_contacts_section(self, state: JobState) -> str:
        """Generate key contacts and outreach section (Phase 10 - uses primary/secondary + outreach_packages)."""
        lines = []
        lines.append("=" * 80)
        lines.append("8. PEOPLE & OUTREACH")
        lines.append("=" * 80)
        lines.append("")

        # Get contacts from new fields (primary/secondary) with fallback to legacy 'people'
        primary_contacts = state.get('primary_contacts', [])
        secondary_contacts = state.get('secondary_contacts', [])
        outreach_packages = state.get('outreach_packages', [])
        legacy_people = state.get('people', [])

        total_contacts = len(primary_contacts) + len(secondary_contacts)
        if total_contacts == 0 and legacy_people:
            # Fallback to legacy people field
            total_contacts = len(legacy_people)
            lines.append(f"Identified {total_contacts} contacts (legacy format):")
            lines.append("")
            for i, person in enumerate(legacy_people, 1):
                lines.append("-" * 40)
                lines.append(f"Contact #{i}: {person.get('name', 'Unknown')}")
                lines.append(f"Role: {person.get('role', 'N/A')}")
                lines.append(f"LinkedIn: {person.get('linkedin_url', 'N/A')}")
                lines.append(f"Why Relevant: {person.get('why_relevant', 'N/A')}")
                lines.append("")
            return "\n".join(lines)

        if total_contacts == 0:
            lines.append("No contacts identified.")
            return "\n".join(lines)

        lines.append(f"Total: {len(primary_contacts)} primary + {len(secondary_contacts)} secondary contacts")
        lines.append(f"Outreach Packages: {len(outreach_packages)}")
        lines.append("")

        # PRIMARY CONTACTS
        if primary_contacts:
            lines.append("-" * 80)
            lines.append("PRIMARY CONTACTS (Hiring-Related)")
            lines.append("-" * 80)
            lines.append("")
            for i, contact in enumerate(primary_contacts, 1):
                lines.append(f"P{i}. {contact.get('name', 'Unknown')} - {contact.get('role', 'N/A')}")
                lines.append(f"    LinkedIn: {contact.get('linkedin_url', 'N/A')}")
                lines.append(f"    Why Relevant: {contact.get('why_relevant', 'N/A')[:100]}...")
                lines.append("")

        # SECONDARY CONTACTS
        if secondary_contacts:
            lines.append("-" * 80)
            lines.append("SECONDARY CONTACTS (Cross-Functional)")
            lines.append("-" * 80)
            lines.append("")
            for i, contact in enumerate(secondary_contacts, 1):
                lines.append(f"S{i}. {contact.get('name', 'Unknown')} - {contact.get('role', 'N/A')}")
                lines.append(f"    LinkedIn: {contact.get('linkedin_url', 'N/A')}")
                lines.append(f"    Why Relevant: {contact.get('why_relevant', 'N/A')[:100]}...")
                lines.append("")

        # OUTREACH PACKAGES (Phase 9)
        if outreach_packages:
            lines.append("-" * 80)
            lines.append("OUTREACH PACKAGES (Ready to Send)")
            lines.append("-" * 80)
            lines.append("")

            # Group by contact name
            packages_by_contact: Dict[str, List[OutreachPackage]] = {}
            for pkg in outreach_packages:
                name = pkg.get('contact_name', 'Unknown')
                if name not in packages_by_contact:
                    packages_by_contact[name] = []
                packages_by_contact[name].append(pkg)

            for contact_name, pkgs in packages_by_contact.items():
                lines.append(f">>> {contact_name}")
                for pkg in pkgs:
                    channel = pkg.get('channel', 'unknown').upper()
                    lines.append(f"    [{channel}]")
                    if pkg.get('subject'):
                        lines.append(f"    Subject: {pkg['subject']}")
                    message = pkg.get('message', '')[:200]
                    lines.append(f"    Message: {message}...")
                    lines.append("")

        return "\n".join(lines)

    def _generate_cover_letter_section(self, state: JobState) -> str:
        """Generate cover letter section."""
        lines = []
        lines.append("=" * 80)
        lines.append("9. COVER LETTER")
        lines.append("=" * 80)
        lines.append("")

        if state.get('cover_letter'):
            lines.append(state['cover_letter'])
        else:
            lines.append("No cover letter generated.")

        return "\n".join(lines)

    def _generate_metadata_section(self, state: JobState) -> str:
        """Generate metadata section with application form fields (Phase 10)."""
        lines = []
        lines.append("=" * 80)
        lines.append("10. METADATA & APPLICATION FORM FIELDS")
        lines.append("=" * 80)
        lines.append("")

        # Pipeline metadata
        lines.append("PIPELINE METADATA")
        lines.append("-" * 40)
        lines.append(f"Run ID: {state.get('run_id', 'N/A')}")
        lines.append(f"Started: {state.get('created_at', 'N/A')}")
        lines.append(f"Status: {state.get('status', 'unknown')}")
        lines.append("")

        # Output paths
        lines.append("OUTPUT PATHS")
        lines.append("-" * 40)
        if state.get('dossier_path'):
            lines.append(f"Dossier: {state['dossier_path']}")
        if state.get('cv_path'):
            lines.append(f"CV: {state['cv_path']}")
        if state.get('drive_folder_url'):
            lines.append(f"Drive Folder: {state['drive_folder_url']}")
        if state.get('sheet_row_id'):
            lines.append(f"Sheets Row: {state['sheet_row_id']}")
        lines.append("")

        # Application Form Fields (Layer 1.5 - if available)
        form_fields = state.get('application_form_fields', [])
        if form_fields:
            lines.append("APPLICATION FORM FIELDS (Layer 1.5)")
            lines.append("-" * 40)
            for field in form_fields:
                lines.append(f"  • {field}")
            lines.append("")
        else:
            lines.append("Application form fields: Not scraped (Layer 1.5 not implemented)")
            lines.append("")

        # Feature flags
        lines.append("FEATURE FLAGS")
        lines.append("-" * 40)
        lines.append(f"STAR Selector: {'Enabled' if Config.ENABLE_STAR_SELECTOR else 'Disabled (using master-CV)'}")
        lines.append(f"Remote Publishing: {'Enabled' if Config.ENABLE_REMOTE_PUBLISHING else 'Disabled (local output only)'}")
        lines.append("")

        # Errors/warnings
        errors = state.get('errors', [])
        if errors:
            lines.append("WARNINGS/ERRORS")
            lines.append("-" * 40)
            for error in errors:
                lines.append(f"  ⚠️  {error}")
            lines.append("")

        lines.append("=" * 80)
        lines.append("END OF DOSSIER")
        lines.append("=" * 80)

        return "\n".join(lines)
