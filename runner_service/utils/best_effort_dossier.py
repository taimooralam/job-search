"""
Best-Effort Dossier Generator

Builds dossier content from whatever MongoDB fields are available,
without requiring full pipeline processing.
"""

from datetime import datetime
from typing import Any, Dict, Tuple


def generate_best_effort_dossier(job: Dict[str, Any]) -> Tuple[str, Dict[str, bool]]:
    """
    Generate a dossier from available job data fields.

    Args:
        job: MongoDB job document

    Returns:
        Tuple of (dossier_content, sections_included)
        sections_included is a dict indicating which sections were populated
    """
    sections = []
    included = {}

    # Header (always)
    sections.append(_generate_header(job))

    # Persona (if available - from jd_annotations.synthesized_persona)
    persona_section, has_persona = _generate_persona_section(job)
    if has_persona:
        sections.append(persona_section)
        included["persona"] = True

    # 1. Job Analysis (extracted_jd, opportunity_mapper)
    analysis_section, has_analysis = _generate_analysis_section(job)
    if has_analysis:
        sections.append(analysis_section)
        included["analysis"] = True

    # 2. Company Overview
    company_section, has_company = _generate_company_section(job)
    if has_company:
        sections.append(company_section)
        included["company"] = True

    # 3. People & Outreach
    contacts_section, has_contacts = _generate_contacts_section(job)
    if has_contacts:
        sections.append(contacts_section)
        included["contacts"] = True

    # 4. Generated Outputs
    outputs_section, has_outputs = _generate_outputs_section(job)
    if has_outputs:
        sections.append(outputs_section)
        included["outputs"] = True

    # 5. Raw JD (fallback - always if available)
    jd_section, has_jd = _generate_raw_jd_section(job)
    if has_jd:
        sections.append(jd_section)
        included["raw_jd"] = True

    # Footer
    sections.append(_generate_footer(included))

    return "\n\n".join(sections), included


def _generate_header(job: Dict[str, Any]) -> str:
    """Generate dossier header."""
    lines = [
        "=" * 80,
        "OPPORTUNITY DOSSIER",
        "=" * 80,
        "",
        f"Company: {job.get('company', 'Unknown')}",
        f"Role: {job.get('title', 'Unknown')}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    if job.get("fit_score") is not None:
        category = job.get("fit_category", "")
        lines.append(f"Fit Score: {job['fit_score']}/100 {f'({category})' if category else ''}")

    if job.get("location"):
        lines.append(f"Location: {job['location']}")

    if job.get("jobId"):
        lines.append(f"Job ID: {job['jobId']}")

    lines.append("=" * 80)
    return "\n".join(lines)


def _generate_persona_section(job: Dict[str, Any]) -> Tuple[str, bool]:
    """Generate candidate persona section from jd_annotations."""
    jd_annotations = job.get("jd_annotations", {})
    if not jd_annotations:
        return "", False

    synthesized_persona = jd_annotations.get("synthesized_persona", {})
    persona_statement = synthesized_persona.get("persona_statement")

    if not persona_statement:
        return "", False

    lines = [
        "=" * 80,
        "CANDIDATE PERSONA",
        "=" * 80,
        "",
        persona_statement,
        "",
    ]

    # Add edit indicator if user-modified
    if synthesized_persona.get("is_user_edited"):
        lines.append("(User-edited)")
        lines.append("")

    return "\n".join(lines), True


def _generate_analysis_section(job: Dict[str, Any]) -> Tuple[str, bool]:
    """Generate job analysis section from extracted_jd and fit data."""
    lines = []
    has_content = False

    extracted_jd = job.get("extracted_jd", {})

    if extracted_jd:
        has_content = True
        lines.extend([
            "=" * 80,
            "1. JOB ANALYSIS",
            "=" * 80,
            "",
        ])

        # Role classification
        if extracted_jd.get("role_category") or extracted_jd.get("seniority_level"):
            lines.extend([
                "ROLE CLASSIFICATION",
                "-" * 40,
            ])
            if extracted_jd.get("role_category"):
                lines.append(f"Category: {extracted_jd['role_category']}")
            if extracted_jd.get("seniority_level"):
                lines.append(f"Seniority: {extracted_jd['seniority_level']}")
            if extracted_jd.get("remote_policy"):
                lines.append(f"Remote Policy: {extracted_jd['remote_policy']}")
            lines.append("")

        # Ideal Candidate Profile (from Layer 1.4 extraction)
        ideal_profile = extracted_jd.get("ideal_candidate_profile", {})
        if ideal_profile:
            lines.extend([
                "IDEAL CANDIDATE PROFILE",
                "-" * 40,
            ])
            if ideal_profile.get("identity_statement"):
                lines.append(f"Identity: {ideal_profile['identity_statement']}")
            if ideal_profile.get("archetype"):
                lines.append(f"Archetype: {ideal_profile['archetype']}")
            if ideal_profile.get("experience_profile"):
                lines.append(f"Experience: {ideal_profile['experience_profile']}")
            if ideal_profile.get("key_traits"):
                traits = ideal_profile["key_traits"]
                if isinstance(traits, list):
                    lines.append(f"Key Traits: {', '.join(traits)}")
            if ideal_profile.get("culture_signals"):
                signals = ideal_profile["culture_signals"]
                if isinstance(signals, list):
                    lines.append(f"Culture Signals: {', '.join(signals)}")
            lines.append("")

        # Responsibilities
        responsibilities = extracted_jd.get("responsibilities") or extracted_jd.get("key_responsibilities", [])
        if responsibilities:
            lines.extend([
                "KEY RESPONSIBILITIES",
                "-" * 40,
            ])
            for i, resp in enumerate(responsibilities[:8], 1):
                lines.append(f"  {i}. {resp}")
            lines.append("")

        # Qualifications
        qualifications = extracted_jd.get("qualifications") or extracted_jd.get("required_qualifications", [])
        if qualifications:
            lines.extend([
                "REQUIRED QUALIFICATIONS",
                "-" * 40,
            ])
            for qual in qualifications[:6]:
                lines.append(f"  * {qual}")
            lines.append("")

        # Technical skills
        if extracted_jd.get("technical_skills"):
            lines.extend([
                "TECHNICAL SKILLS",
                "-" * 40,
                ", ".join(extracted_jd["technical_skills"]),
                "",
            ])

        # Soft skills
        if extracted_jd.get("soft_skills"):
            lines.extend([
                "SOFT SKILLS",
                "-" * 40,
                ", ".join(extracted_jd["soft_skills"]),
                "",
            ])

        # Competency weights (if available)
        if extracted_jd.get("competency_weights"):
            weights = extracted_jd["competency_weights"]
            if isinstance(weights, dict) and weights:
                lines.extend([
                    "COMPETENCY WEIGHTS",
                    "-" * 40,
                ])
                for skill, weight in weights.items():
                    lines.append(f"  * {skill}: {weight}")
                lines.append("")

        # ATS Keywords
        if extracted_jd.get("top_keywords"):
            lines.extend([
                "ATS KEYWORDS",
                "-" * 40,
                ", ".join(extracted_jd["top_keywords"][:15]),
                "",
            ])

        # Full Pain Point Analysis (4 dimensions)
        pain_points = job.get("pain_points") or extracted_jd.get("implied_pain_points", [])
        strategic_needs = job.get("strategic_needs", [])
        risks_if_unfilled = job.get("risks_if_unfilled", [])
        success_metrics = job.get("success_metrics") or extracted_jd.get("success_metrics", [])

        has_any_pain_data = pain_points or strategic_needs or risks_if_unfilled or success_metrics

        if has_any_pain_data:
            lines.extend([
                "PAIN POINT ANALYSIS (4 Dimensions)",
                "-" * 40,
            ])

            # Pain Points
            if pain_points:
                lines.append("Pain Points:")
                for pp in pain_points[:5]:
                    text = pp if isinstance(pp, str) else pp.get("text", str(pp))
                    lines.append(f"  * {text}")
                lines.append("")

            # Strategic Needs
            if strategic_needs:
                lines.append("Strategic Needs:")
                for need in strategic_needs[:5]:
                    lines.append(f"  * {need}")
                lines.append("")

            # Risks if Unfilled
            if risks_if_unfilled:
                lines.append("Risks if Unfilled:")
                for risk in risks_if_unfilled[:5]:
                    lines.append(f"  * {risk}")
                lines.append("")

            # Success Metrics
            if success_metrics:
                lines.append("Success Metrics:")
                for metric in success_metrics[:5]:
                    lines.append(f"  * {metric}")
                lines.append("")

    # Fit analysis from opportunity_mapper
    if job.get("fit_score") is not None or job.get("fit_rationale"):
        if not has_content:
            lines.extend([
                "=" * 80,
                "1. JOB ANALYSIS",
                "=" * 80,
                "",
            ])
        has_content = True

        lines.extend([
            "FIT ANALYSIS",
            "-" * 40,
        ])
        if job.get("fit_score") is not None:
            category = job.get("fit_category", "")
            lines.append(f"Score: {job['fit_score']}/100 {f'({category})' if category else ''}")
        if job.get("fit_rationale"):
            lines.append(f"Rationale: {job['fit_rationale']}")
        lines.append("")

    return "\n".join(lines), has_content


def _generate_company_section(job: Dict[str, Any]) -> Tuple[str, bool]:
    """Generate company overview section."""
    lines = []
    has_content = False

    company_metadata = job.get("company_metadata", {})
    company_research = job.get("company_research", {})
    company_summary = job.get("company_summary")

    if company_metadata or company_research or company_summary:
        has_content = True
        lines.extend([
            "=" * 80,
            "2. COMPANY OVERVIEW",
            "=" * 80,
            "",
        ])

        # Company metadata (from scraping/enrichment)
        if company_metadata:
            lines.extend([
                "COMPANY INFO",
                "-" * 40,
            ])
            if company_metadata.get("industry"):
                lines.append(f"Industry: {company_metadata['industry']}")
            if company_metadata.get("size"):
                lines.append(f"Size: {company_metadata['size']}")
            if company_metadata.get("location"):
                lines.append(f"Location: {company_metadata['location']}")
            if company_metadata.get("founded"):
                lines.append(f"Founded: {company_metadata['founded']}")
            if company_metadata.get("about"):
                lines.extend(["", "About:", company_metadata["about"][:800]])
            lines.append("")

        # Company research (from pipeline)
        if company_research:
            if company_research.get("summary"):
                lines.extend([
                    "RESEARCH SUMMARY",
                    "-" * 40,
                    company_research["summary"],
                    "",
                ])

            signals = company_research.get("signals", [])
            if signals:
                lines.extend([
                    "COMPANY SIGNALS",
                    "-" * 40,
                ])
                for signal in signals[:5]:
                    signal_type = signal.get("type", "unknown")
                    desc = signal.get("description", "N/A")
                    date = signal.get("date", "")
                    lines.append(f"  [{signal_type.upper()}] {desc} {f'({date})' if date else ''}")
                lines.append("")

        # Fallback to simple summary
        elif company_summary:
            lines.extend([
                "COMPANY SUMMARY",
                "-" * 40,
                company_summary,
                "",
            ])

    return "\n".join(lines), has_content


def _generate_contacts_section(job: Dict[str, Any]) -> Tuple[str, bool]:
    """Generate contacts and outreach section."""
    lines = []
    has_content = False

    primary = job.get("primary_contacts", [])
    secondary = job.get("secondary_contacts", [])
    contacts = job.get("contacts", [])  # Legacy field

    all_contacts = primary + secondary + contacts

    if all_contacts:
        has_content = True
        lines.extend([
            "=" * 80,
            "3. PEOPLE & OUTREACH",
            "=" * 80,
            "",
        ])

        if primary:
            lines.extend([
                "PRIMARY CONTACTS (Hiring-Related)",
                "-" * 40,
            ])
            for i, c in enumerate(primary[:5], 1):
                lines.append(f"P{i}. {c.get('name', 'Unknown')} - {c.get('role', 'N/A')}")
                if c.get("linkedin_url"):
                    lines.append(f"    LinkedIn: {c['linkedin_url']}")
                if c.get("why_relevant"):
                    why = c["why_relevant"]
                    lines.append(f"    Why: {why[:150]}{'...' if len(why) > 150 else ''}")
                # Include outreach if available
                if c.get("linkedin_connection_message"):
                    msg = c["linkedin_connection_message"]
                    lines.append(f"    Connection msg: {msg[:200]}{'...' if len(msg) > 200 else ''}")
                lines.append("")

        if secondary:
            lines.extend([
                "SECONDARY CONTACTS (Cross-Functional)",
                "-" * 40,
            ])
            for i, c in enumerate(secondary[:5], 1):
                lines.append(f"S{i}. {c.get('name', 'Unknown')} - {c.get('role', 'N/A')}")
                if c.get("linkedin_url"):
                    lines.append(f"    LinkedIn: {c['linkedin_url']}")
                lines.append("")

        # Legacy contacts field
        if contacts and not primary and not secondary:
            lines.extend([
                "CONTACTS",
                "-" * 40,
            ])
            for i, c in enumerate(contacts[:6], 1):
                lines.append(f"{i}. {c.get('name', 'Unknown')} - {c.get('role', 'N/A')}")
                if c.get("linkedin_url"):
                    lines.append(f"   LinkedIn: {c['linkedin_url']}")
                lines.append("")

    return "\n".join(lines), has_content


def _generate_outputs_section(job: Dict[str, Any]) -> Tuple[str, bool]:
    """Generate section with cover letter and CV preview."""
    lines = []
    has_content = False

    cover_letter = job.get("cover_letter")
    cv_text = job.get("cv_text")

    # Try to extract text from cv_editor_state if cv_text is not available
    if not cv_text:
        editor_state = job.get("cv_editor_state", {})
        if editor_state and isinstance(editor_state, dict):
            content = editor_state.get("content", {})
            if content:
                # TipTap JSON format - try to extract text
                cv_text = _extract_text_from_tiptap(content)

    if cover_letter or cv_text:
        has_content = True
        lines.extend([
            "=" * 80,
            "4. GENERATED OUTPUTS",
            "=" * 80,
            "",
        ])

        if cover_letter:
            lines.extend([
                "COVER LETTER",
                "-" * 40,
                cover_letter,
                "",
            ])

        if cv_text:
            # Include full CV content, only truncate if extremely long
            cv_content = cv_text[:8000] if len(cv_text) > 8000 else cv_text
            lines.extend([
                "TAILORED CV",
                "-" * 40,
                cv_content,
            ])
            if len(cv_text) > 8000:
                lines.append("...[truncated at 8000 chars]...")
            lines.append("")

    return "\n".join(lines), has_content


def _extract_text_from_tiptap(content: Dict[str, Any]) -> str:
    """Extract plain text from TipTap JSON content structure."""
    if not content:
        return ""

    text_parts = []

    def extract_recursive(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                text_parts.append(node.get("text", ""))
            if "content" in node:
                for child in node.get("content", []):
                    extract_recursive(child)
        elif isinstance(node, list):
            for item in node:
                extract_recursive(item)

    extract_recursive(content)
    return " ".join(text_parts)


def _generate_raw_jd_section(job: Dict[str, Any]) -> Tuple[str, bool]:
    """Generate raw job description section as fallback."""
    jd = (
        job.get("job_description")
        or job.get("description")
        or job.get("jobDescription")
        or job.get("scraped_job_posting", "")
    )

    if jd:
        lines = [
            "=" * 80,
            "5. RAW JOB DESCRIPTION",
            "=" * 80,
            "",
            jd[:5000],  # Limit to 5000 chars
        ]
        if len(jd) > 5000:
            lines.append("\n[...truncated...]")

        return "\n".join(lines), True

    return "", False


def _generate_footer(included: Dict[str, bool]) -> str:
    """Generate dossier footer with content summary."""
    lines = [
        "=" * 80,
        "END OF DOSSIER",
        "=" * 80,
    ]

    sections_list = [k for k, v in included.items() if v]
    if sections_list:
        lines.append(f"Sections included: {', '.join(sections_list)}")
    else:
        lines.append("Note: Limited data available - only basic info included.")

    lines.append("Generated on-demand from available data fields.")
    lines.append("=" * 80)

    return "\n".join(lines)


def has_minimum_dossier_data(job: Dict[str, Any]) -> bool:
    """
    Check if job has at least some useful data for dossier generation.

    Returns True if:
    - company and title exist
    - AND at least one of: job_description, description, or extracted_jd
    """
    has_company = bool(job.get("company"))
    has_title = bool(job.get("title"))
    has_jd = bool(
        job.get("job_description")
        or job.get("description")
        or job.get("jobDescription")
    )
    has_extraction = bool(job.get("extracted_jd"))

    return has_company and has_title and (has_jd or has_extraction)
