"""
HTML CV Generator - Generates editable HTML CVs with PDF export capability.

This generator creates clean, professional HTML CVs that can be:
1. Displayed in the job detail page
2. Edited inline using a rich text editor
3. Converted to PDF for download

Uses the same STAR selection logic as the .docx generator but outputs
semantic HTML with embedded CSS for styling.
"""

from typing import List, Dict, Tuple
from pathlib import Path
from datetime import datetime

from src.common.state import JobState
from src.layer6.cv_generator import CVGenerator


class HTMLCVGenerator:
    """
    Generates HTML-based CVs with inline editing and PDF export support.

    Extends the existing CV generator logic but outputs HTML instead of .docx.
    The HTML includes:
    - Semantic markup for accessibility
    - Embedded CSS for professional styling
    - Print-optimized styles for PDF generation
    - ContentEditable sections for inline editing
    """

    def __init__(self):
        """Initialize with the existing CV generator for STAR selection logic."""
        self.cv_generator = CVGenerator()

    def generate_html_cv(self, state: JobState) -> Tuple[str, str]:
        """
        Generate HTML CV using STAR selection from CVGenerator.

        Args:
            state: JobState with all pipeline outputs

        Returns:
            Tuple of (html_cv_path, cv_reasoning)
        """
        print("\n=== Layer 6: HTML CV Generator ===")

        # Use existing CVGenerator for competency analysis and STAR selection
        print("→ Analyzing competency mix and selecting STARs...")

        # Get the .docx generator's internal logic
        competency_mix = self.cv_generator._analyze_competency_mix(
            job_description=state["job_description"],
            title=state["title"],
            company=state["company"]
        )

        # Score and rank STARs
        all_stars = state.get("all_stars") or state.get("selected_stars") or []

        if not all_stars:
            print("  ⚠️  No STARs available - generating minimal HTML CV")
            return self._generate_minimal_html_cv(state, competency_mix)

        job_keywords = self.cv_generator._extract_keywords(state["job_description"])
        star_scores = self.cv_generator._score_stars(all_stars, competency_mix.dict(), job_keywords)

        top_n = min(5, max(3, len(all_stars)))
        ranked_stars = self.cv_generator._rank_stars(star_scores, top_n=top_n)

        # Get full STAR objects
        star_id_to_record = {star["id"]: star for star in all_stars}
        selected_stars = [star_id_to_record[r["id"]] for r in ranked_stars if r["id"] in star_id_to_record]

        if not selected_stars:
            selected_stars = all_stars[:top_n]

        # Detect gaps and generate reasoning
        gaps = self.cv_generator._detect_gaps(
            state["job_description"],
            selected_stars,
            all_stars
        )

        cv_reasoning = self.cv_generator._generate_cv_reasoning(
            competency_mix.dict(),
            selected_stars,
            gaps,
            state["title"]
        )

        # Build HTML CV
        print("→ Building HTML CV...")
        html_content = self._build_html_cv(state, competency_mix, selected_stars)

        # Save HTML file
        html_path = self._save_html_cv(state, html_content)
        print(f"  ✅ HTML CV saved: {html_path}")

        return html_path, cv_reasoning

    def _build_html_cv(self, state: JobState, competency_mix, selected_stars: List[Dict]) -> str:
        """
        Build HTML CV content with embedded CSS and semantic markup.

        Returns complete HTML document ready for display/editing/PDF generation.
        """
        # Extract candidate info
        candidate_name, contact_info = self.cv_generator._extract_candidate_header(
            state["candidate_profile"]
        )

        # Generate professional summary
        summary = self.cv_generator._generate_professional_summary(
            state["title"],
            state["company"],
            state.get("fit_score"),
            competency_mix
        )

        # Get key achievements
        achievements = self.cv_generator._extract_key_achievements(selected_stars)

        # Sort STARs by period
        sorted_stars = sorted(selected_stars, key=lambda s: s.get('period', ''), reverse=True)

        # Get education
        education = self.cv_generator._extract_education(state["candidate_profile"])

        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV - {candidate_name} - {state['title']}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #2d3748;
            background: #f7fafc;
            padding: 2rem;
        }}

        .cv-container {{
            max-width: 850px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            padding: 3rem;
        }}

        .cv-header {{
            text-align: center;
            border-bottom: 3px solid #2b6cb0;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}

        .cv-name {{
            font-size: 2.5rem;
            font-weight: 700;
            color: #1a202c;
            margin-bottom: 0.5rem;
        }}

        .cv-contact {{
            font-size: 0.95rem;
            color: #4a5568;
        }}

        .cv-section {{
            margin-bottom: 2rem;
        }}

        .cv-section-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #2b6cb0;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }}

        .cv-summary {{
            font-size: 1.05rem;
            color: #4a5568;
            line-height: 1.8;
        }}

        .cv-achievements {{
            list-style: none;
            padding-left: 0;
        }}

        .cv-achievements li {{
            padding-left: 1.5rem;
            margin-bottom: 0.75rem;
            position: relative;
        }}

        .cv-achievements li:before {{
            content: "▪";
            position: absolute;
            left: 0;
            color: #2b6cb0;
            font-weight: bold;
        }}

        .cv-experience-item {{
            margin-bottom: 1.5rem;
        }}

        .cv-experience-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 0.5rem;
        }}

        .cv-role {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #1a202c;
        }}

        .cv-company {{
            color: #2b6cb0;
            font-weight: 500;
        }}

        .cv-period {{
            color: #718096;
            font-size: 0.9rem;
        }}

        .cv-experience-bullets {{
            list-style: none;
            padding-left: 1.5rem;
        }}

        .cv-experience-bullets li {{
            margin-bottom: 0.5rem;
            position: relative;
        }}

        .cv-experience-bullets li:before {{
            content: "•";
            position: absolute;
            left: -1rem;
            color: #2b6cb0;
        }}

        .cv-education {{
            color: #4a5568;
        }}

        /* Print styles for PDF generation */
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}

            .cv-container {{
                box-shadow: none;
                max-width: 100%;
            }}
        }}

        /* Editable indicator */
        [contenteditable="true"]:hover {{
            background: #edf2f7;
            outline: 1px dashed #2b6cb0;
        }}

        [contenteditable="true"]:focus {{
            background: #e6fffa;
            outline: 2px solid #38b2ac;
        }}

        /* Skills Grid */
        .skills-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1rem;
        }}

        .skill-badge {{
            background: #edf2f7;
            color: #2d3748;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
            border: 1px solid #cbd5e0;
        }}
    </style>
</head>
<body>
    <div class="cv-container">
        <!-- Header -->
        <header class="cv-header">
            <h1 class="cv-name" contenteditable="true">{candidate_name}</h1>
            <p class="cv-contact" contenteditable="true">{contact_info}</p>
        </header>

        <!-- Professional Summary -->
        <section class="cv-section">
            <h2 class="cv-section-title">Professional Summary</h2>
            <p class="cv-summary" contenteditable="true">{summary}</p>
        </section>

        <!-- Skills -->
        <section class="cv-section">
            <h2 class="cv-section-title">Core Competencies</h2>
            {self._extract_skills(state["candidate_profile"], state["job_description"])}
        </section>

        <!-- Key Achievements -->
        <section class="cv-section">
            <h2 class="cv-section-title">Key Achievements</h2>
            <ul class="cv-achievements">
"""

        for achievement in achievements:
            html += f'                <li contenteditable="true">{achievement}</li>\n'

        html += """            </ul>
        </section>

        <!-- Professional Experience -->
        <section class="cv-section">
            <h2 class="cv-section-title">Professional Experience</h2>
"""

        for star in sorted_stars:
            role = star.get('role', 'Role')
            company = star.get('company', 'Company')
            period = star.get('period', 'Dates')

            html += f"""            <div class="cv-experience-item">
                <div class="cv-experience-header">
                    <div>
                        <span class="cv-role" contenteditable="true">{role}</span> |
                        <span class="cv-company" contenteditable="true">{company}</span>
                    </div>
                    <span class="cv-period" contenteditable="true">{period}</span>
                </div>
                <ul class="cv-experience-bullets">
"""

            bullets = self.cv_generator._format_star_as_bullets(star)
            for bullet in bullets:
                html += f'                    <li contenteditable="true">{bullet}</li>\n'

            html += """                </ul>
            </div>
"""

        html += """        </section>

        <!-- Education -->
        <section class="cv-section">
            <h2 class="cv-section-title">Education & Certifications</h2>
            <div class="cv-education" contenteditable="true">
"""

        # Format education with line breaks
        education_lines = education.split('\n')
        for line in education_lines:
            if line.strip():
                html += f"                <p>{line.strip()}</p>\n"

        html += """            </div>
        </section>

        <!-- Metadata (hidden, for tracking) -->
        <div style="display: none;">
            <meta name="job-id" content="{job_id}">
            <meta name="company" content="{company}">
            <meta name="role" content="{title}">
            <meta name="generated-at" content="{timestamp}">
        </div>
    </div>
</body>
</html>
""".format(
            job_id=state.get('job_id', ''),
            company=state['company'],
            title=state['title'],
            timestamp=datetime.now().isoformat()
        )

        return html

    def _generate_minimal_html_cv(self, state: JobState, competency_mix) -> Tuple[str, str]:
        """Generate enhanced HTML CV when no STARs available."""
        candidate_name, contact_info = self.cv_generator._extract_candidate_header(
            state["candidate_profile"]
        )

        # Generate professional summary
        summary = self.cv_generator._generate_professional_summary(
            state["title"],
            state["company"],
            state.get("fit_score"),
            competency_mix
        )

        # Get skills and education
        skills_html = self._extract_skills(state["candidate_profile"], state["job_description"])
        education = self.cv_generator._extract_education(state["candidate_profile"])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV - {candidate_name} - {state['title']}</title>
    <style>
        * {{margin: 0; padding: 0; box-sizing: border-box;}}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #2d3748;
            background: #f7fafc;
            padding: 2rem;
        }}
        .cv-container {{
            max-width: 850px;
            margin: 0 auto;
            background: white;
            padding: 3rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .cv-header {{
            text-align: center;
            border-bottom: 3px solid #2b6cb0;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}
        h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            color: #1a202c;
            margin-bottom: 0.5rem;
        }}
        .cv-contact {{
            font-size: 0.95rem;
            color: #4a5568;
        }}
        .cv-section {{
            margin-bottom: 2rem;
        }}
        h2 {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #2b6cb0;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }}
        p {{
            line-height: 1.8;
            color: #4a5568;
        }}
        .skills-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1rem;
        }}
        .skill-badge {{
            background: #edf2f7;
            color: #2d3748;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
            border: 1px solid #cbd5e0;
        }}
        .notice {{
            background: #fef5e7;
            border-left: 4px solid #f39c12;
            padding: 1rem;
            margin: 1rem 0;
            color: #856404;
            font-size: 0.9rem;
        }}
        [contenteditable="true"]:hover {{
            background: #edf2f7;
            outline: 1px dashed #2b6cb0;
        }}
        [contenteditable="true"]:focus {{
            background: #e6fffa;
            outline: 2px solid #38b2ac;
        }}
        @media print {{
            body {{background: white; padding: 0;}}
            .cv-container {{box-shadow: none; max-width: 100%;}}
            .notice {{display: none;}}
        }}
    </style>
</head>
<body>
    <div class="cv-container">
        <header class="cv-header">
            <h1 contenteditable="true">{candidate_name}</h1>
            <p class="cv-contact" contenteditable="true">{contact_info}</p>
        </header>

        <div class="notice">
            <strong>⚠️ Note:</strong> This is a preliminary CV. Detailed achievement metrics (STAR records) will be added once your experience history is populated in the knowledge base.
        </div>

        <section class="cv-section">
            <h2>Professional Summary</h2>
            <p contenteditable="true">{summary}</p>
        </section>

        <section class="cv-section">
            <h2>Core Competencies</h2>
            {skills_html}
        </section>

        <section class="cv-section">
            <h2>Education & Certifications</h2>
            <div contenteditable="true">
"""

        # Format education with line breaks
        education_lines = education.split('\n')
        for line in education_lines:
            if line.strip():
                html += f"                <p>{line.strip()}</p>\n"

        html += f"""            </div>
        </section>

        <div style="display: none;">
            <meta name="job-id" content="{state.get('job_id', '')}">
            <meta name="company" content="{state['company']}">
            <meta name="role" content="{state['title']}">
            <meta name="generated-at" content="{datetime.now().isoformat()}">
        </div>
    </div>
</body>
</html>"""

        html_path = self._save_html_cv(state, html)

        cv_reasoning = f"Enhanced minimal CV generated for {state['title']} at {state['company']} with profile summary, skills, and education. STAR records to be added when available."

        return html_path, cv_reasoning

    def _extract_skills(self, profile: str, job_description: str = "") -> str:
        """
        Extract skills from candidate profile and format as HTML.

        Looks for common skill indicators in the profile text.
        Returns HTML string with skill badges/list.
        """
        skills = []

        # Common technical skills to look for
        tech_keywords = [
            'Python', 'JavaScript', 'TypeScript', 'Java', 'C++', 'Go', 'Rust',
            'React', 'Vue', 'Angular', 'Node.js', 'Django', 'Flask',
            'AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes', 'Terraform',
            'PostgreSQL', 'MongoDB', 'Redis', 'MySQL',
            'Git', 'CI/CD', 'Jenkins', 'GitHub Actions',
            'Machine Learning', 'AI', 'Data Science', 'NLP',
            'Microservices', 'REST API', 'GraphQL', 'gRPC',
            'Agile', 'Scrum', 'Leadership', 'Team Management'
        ]

        profile_lower = profile.lower()
        for keyword in tech_keywords:
            if keyword.lower() in profile_lower:
                skills.append(keyword)

        if not skills:
            return '<p class="text-gray-500">Skills being updated...</p>'

        # Create skill badges HTML
        html = '<div class="skills-grid">\n'
        for skill in skills[:15]:  # Limit to top 15
            html += f'  <span class="skill-badge">{skill}</span>\n'
        html += '</div>'

        return html

    def _save_html_cv(self, state: JobState, html_content: str) -> str:
        """
        Save HTML CV to applications directory.

        Returns path to saved HTML file.
        """
        # Create output directory
        company_clean = state["company"].replace(" ", "_").replace("/", "_")
        title_clean = state["title"].replace(" ", "_").replace("/", "_")
        output_dir = Path("applications") / company_clean / title_clean
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save HTML file
        html_path = output_dir / "CV.html"
        html_path.write_text(html_content, encoding='utf-8')

        return str(html_path)
