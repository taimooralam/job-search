"""
CV Generation V2 Orchestrator.

Ties all 6 phases together into a single pipeline:
1. CV Loader - Load pre-split role files
2. Per-Role Generator - Generate tailored bullets for each role
3. Stitcher - Combine roles with deduplication
4. Header Generator - Create profile/skills grounded in achievements
5. Grader - Multi-dimensional quality assessment
6. Improver - Single-pass targeted improvement

Usage:
    from src.layer6_v2.orchestrator import cv_generator_v2_node

    # In workflow:
    workflow.add_node("generator", cv_generator_v2_node)
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.common.config import Config
from src.common.state import JobState
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.common.utils import sanitize_path_component
from src.common.markdown_sanitizer import sanitize_markdown, sanitize_bullet_text

# GAP-014: Middle East countries for relocation tagline
MIDDLE_EAST_COUNTRIES = [
    "saudi arabia", "uae", "united arab emirates", "dubai", "abu dhabi",
    "kuwait", "qatar", "doha", "oman", "bahrain", "pakistan", "karachi",
    "lahore", "islamabad", "riyadh", "jeddah", "muscat", "manama"
]

RELOCATION_TAGLINE = "Open to International Relocation | Available to start within 2 months"


def is_middle_east_location(location: str) -> bool:
    """
    GAP-014: Check if job location is in Middle East region.

    Args:
        location: Job location string

    Returns:
        True if location matches any Middle East country/city
    """
    if not location:
        return False
    location_lower = location.lower()
    return any(country in location_lower for country in MIDDLE_EAST_COUNTRIES)


from src.layer6_v2.cv_loader import CVLoader, RoleData, CandidateData
from src.layer6_v2.role_generator import (
    RoleGenerator,
    generate_all_roles_sequential,
    generate_all_roles_with_star_enforcement,
    generate_all_roles_from_variants,
)
from src.layer6_v2.role_qa import RoleQA, run_qa_on_all_roles
from src.layer6_v2.stitcher import CVStitcher, stitch_all_roles
from src.layer6_v2.header_generator import HeaderGenerator, generate_header
from src.layer6_v2.grader import CVGrader, grade_cv
from src.layer6_v2.improver import CVImprover, improve_cv
from src.layer6_v2.types import (
    RoleBullets,
    StitchedCV,
    HeaderOutput,
    GradeResult,
    ImprovementResult,
    FinalCV,
)


class CVGeneratorV2:
    """
    Orchestrates all 6 phases of CV Generation V2.

    Design principles:
    - Sequential processing (predictable, debuggable)
    - Per-role hallucination QA
    - Role-category-aware emphasis
    - Single-pass improvement for cost control
    """

    def __init__(
        self,
        model: Optional[str] = None,
        passing_threshold: float = 8.5,
        word_budget: Optional[int] = None,  # None = no limit, include all roles fully
        use_llm_grading: bool = True,
        use_star_enforcement: bool = True,  # GAP-005: STAR format enforcement
        use_variant_selection: bool = True,  # Use pre-written variants (zero hallucination)
    ):
        """
        Initialize the CV Generator V2 orchestrator.

        Args:
            model: LLM model to use (default: Config.DEFAULT_MODEL)
            passing_threshold: Grade threshold to pass (default: 8.5)
            word_budget: Target word count (None = no limit, all roles included)
            use_llm_grading: Use LLM for grading vs rule-based (default: True)
            use_star_enforcement: Enable STAR format enforcement with retry (default: True)
            use_variant_selection: Use pre-written variants for zero-hallucination generation (default: True)
        """
        self._logger = get_logger(__name__)
        self.model = model or Config.DEFAULT_MODEL
        self.passing_threshold = passing_threshold
        self.word_budget = word_budget  # None = unlimited
        self.use_llm_grading = use_llm_grading
        self.use_star_enforcement = use_star_enforcement  # GAP-005
        self.use_variant_selection = use_variant_selection  # Variant-based generation

        # Initialize components
        self.cv_loader = CVLoader()
        self.role_generator = RoleGenerator(model=self.model)
        self.role_qa = RoleQA()
        self.stitcher = CVStitcher(word_budget=word_budget)  # None = no trimming
        # GAP-001 FIX: Get skill whitelist from cv_loader to prevent hallucinations
        # The whitelist is loaded lazily when cv_loader.load() is called
        self.header_generator = HeaderGenerator(model=self.model)  # Whitelist passed in generate()
        self.grader = CVGrader(
            model=self.model,
            passing_threshold=passing_threshold,
            use_llm_grading=use_llm_grading,
        )
        self.improver = CVImprover(model=self.model)

        self._logger.info(f"CVGeneratorV2 initialized with model: {self.model}")

    def generate(
        self,
        state: JobState,
    ) -> Dict[str, Any]:
        """
        Generate a tailored CV using the 6-phase pipeline.

        Args:
            state: Current job processing state with extracted_jd

        Returns:
            Dictionary with cv_text, cv_path, cv_reasoning, and grading results
        """
        self._logger.info("=" * 60)
        self._logger.info("CV GENERATION V2: Starting 6-phase pipeline")
        self._logger.info("=" * 60)

        # Extract required data from state
        extracted_jd = state.get("extracted_jd", {})
        if not extracted_jd:
            self._logger.warning("No extracted_jd in state - using defaults")
            extracted_jd = self._build_default_extracted_jd(state)

        company = state.get("company", "Unknown")
        title = state.get("title", "Unknown")

        try:
            # Phase 1: Load candidate data
            self._logger.info("Phase 1: Loading candidate data...")
            candidate_data = self.cv_loader.load()
            roles = candidate_data.roles
            self._logger.info(f"  Loaded {len(roles)} roles from master CV")

            # Phase 2: Generate tailored bullets for each role
            self._logger.info("Phase 2: Generating tailored bullets per role...")
            role_bullets_list = self._generate_all_role_bullets(roles, extracted_jd)
            self._logger.info(f"  Generated bullets for {len(role_bullets_list)} roles")

            # Phase 3: Run QA on all roles
            self._logger.info("Phase 3: Running hallucination QA...")
            qa_results, ats_results = run_qa_on_all_roles(
                role_bullets_list,
                roles,  # Pass full RoleData objects
                extracted_jd.get("top_keywords", []),
            )
            self._log_qa_summary(qa_results, role_bullets_list)

            # Phase 4: Stitch roles together
            self._logger.info("Phase 4: Stitching roles with deduplication...")
            stitched_cv = stitch_all_roles(
                role_bullets_list,
                word_budget=self.word_budget,
                target_keywords=extracted_jd.get("top_keywords", []),
            )
            self._logger.info(f"  Stitched CV: {stitched_cv.total_word_count} words, {stitched_cv.total_bullet_count} bullets")

            # Phase 5: Generate header and skills
            self._logger.info("Phase 5: Generating header and skills...")
            # GAP-001 FIX: Pass skill whitelist to prevent hallucinated skills
            skill_whitelist = self.cv_loader.get_skill_whitelist()
            self._logger.info(f"  Using skill whitelist: {len(skill_whitelist['hard_skills'])} hard, {len(skill_whitelist['soft_skills'])} soft skills")
            header_output = generate_header(
                stitched_cv,
                extracted_jd,
                {
                    "name": candidate_data.name,
                    "email": candidate_data.email,
                    "phone": candidate_data.phone,
                    "linkedin": candidate_data.linkedin,
                    "location": candidate_data.location,
                    "education": [
                        candidate_data.education_masters,
                        candidate_data.education_bachelors,
                    ] if candidate_data.education_bachelors else [candidate_data.education_masters],
                    "certifications": candidate_data.certifications,
                    "languages": candidate_data.languages,
                },
                skill_whitelist=skill_whitelist,
            )
            self._logger.info(f"  Profile: {header_output.profile.word_count} words")
            self._logger.info(f"  Skills sections: {len(header_output.skills_sections)}")

            # Assemble full CV text
            # GAP-014: Pass job location for Middle East relocation tagline
            job_location = extracted_jd.get("location", "") or state.get("location", "")
            cv_text = self._assemble_cv_text(
                header_output, stitched_cv, candidate_data, job_location, extracted_jd
            )

            # Phase 6: Grade and improve
            self._logger.info("Phase 6: Grading CV...")
            master_cv_text = self._get_master_cv_text()
            grade_result = grade_cv(cv_text, extracted_jd, master_cv_text)
            self._log_grade_result(grade_result)

            improvement_result = None
            if not grade_result.passed:
                self._logger.info("  CV below threshold - applying single-pass improvement...")
                improvement_result = improve_cv(cv_text, grade_result, extracted_jd)
                if improvement_result.improved:
                    cv_text = improvement_result.cv_text
                    self._logger.info(f"  Improved {improvement_result.target_dimension}")
                    self._logger.info(f"  Changes: {len(improvement_result.changes_made)}")

            # Save CV to disk
            cv_path = self._save_cv_to_disk(cv_text, company, title)

            # Build reasoning summary
            cv_reasoning = self._build_reasoning(
                grade_result, improvement_result, stitched_cv, header_output
            )

            self._logger.info("=" * 60)
            self._logger.info("CV GENERATION V2: Complete")
            self._logger.info(f"  Final score: {grade_result.composite_score:.1f}/10")
            self._logger.info(f"  Passed: {grade_result.passed}")
            self._logger.info("=" * 60)

            return {
                "cv_text": cv_text,
                "cv_path": cv_path,
                "cv_reasoning": cv_reasoning,
                # Extended fields for debugging/analysis
                "cv_grade_result": grade_result.to_dict() if hasattr(grade_result, 'to_dict') else None,
                "cv_improvement_result": improvement_result.to_dict() if improvement_result and hasattr(improvement_result, 'to_dict') else None,
            }

        except Exception as e:
            self._logger.error(f"CV Generation V2 failed: {e}")
            return {
                "cv_text": None,
                "cv_path": None,
                "cv_reasoning": f"Generation failed: {str(e)}",
                "errors": [f"CV Gen V2 error: {str(e)}"],
            }

    def _build_default_extracted_jd(self, state: JobState) -> Dict[str, Any]:
        """Build default extracted_jd from state when not available."""
        return {
            "title": state.get("title", ""),
            "company": state.get("company", ""),
            "role_category": "engineering_manager",
            "seniority_level": "senior",
            "top_keywords": [],
            "implied_pain_points": state.get("pain_points", []),
            "success_metrics": state.get("success_metrics", []),
            "technical_skills": [],
            "soft_skills": [],
            "responsibilities": [],
            "qualifications": [],
            "nice_to_haves": [],
            "competency_weights": {
                "delivery": 25,
                "process": 25,
                "architecture": 25,
                "leadership": 25,
            },
        }

    def _generate_all_role_bullets(
        self,
        roles: List[RoleData],
        extracted_jd: Dict[str, Any],
    ) -> List[RoleBullets]:
        """Generate bullets for all roles with variant selection or LLM generation."""
        from src.layer6_v2.types import CareerContext

        role_category = extracted_jd.get("role_category", "engineering_manager")

        # Log generation mode
        if self.use_variant_selection:
            self._logger.info("  Variant-based generation ENABLED (zero hallucination)")
            # Check if roles have variant data
            roles_with_variants = sum(1 for r in roles if r.has_variants)
            self._logger.info(f"  Roles with variants: {roles_with_variants}/{len(roles)}")

            # Use batch variant-based generation
            return generate_all_roles_from_variants(
                roles=roles,
                extracted_jd=extracted_jd,
                generator=self.role_generator,
                fallback_to_llm=True,  # Fall back to LLM for roles without variants
            )

        # Legacy LLM-based generation
        role_bullets_list = []

        # Log STAR enforcement status
        if self.use_star_enforcement:
            self._logger.info("  STAR format enforcement ENABLED (GAP-005)")

        for i, role in enumerate(roles):
            self._logger.info(f"  Generating bullets for: {role.title} @ {role.company}")

            # Build career context for this role
            career_context = CareerContext.build(
                role_index=i,
                total_roles=len(roles),
                is_current=role.is_current,
                target_role_category=role_category,
            )

            try:
                # GAP-005: Use STAR-enforced generation when enabled
                if self.use_star_enforcement:
                    role_bullets = self.role_generator.generate_with_star_enforcement(
                        role=role,
                        extracted_jd=extracted_jd,
                        career_context=career_context,
                        max_retries=2,
                        star_threshold=0.8,
                    )
                else:
                    role_bullets = self.role_generator.generate(
                        role=role,
                        extracted_jd=extracted_jd,
                        career_context=career_context,
                    )
                role_bullets_list.append(role_bullets)
            except Exception as e:
                self._logger.warning(f"  Failed to generate bullets for {role.company}: {e}")
                # Create fallback with original achievements as bullets
                from src.layer6_v2.types import GeneratedBullet
                fallback_bullets = [
                    GeneratedBullet(
                        text=achievement,
                        source_text=achievement,
                    )
                    for achievement in role.achievements[:5]  # Top 5 achievements
                ]
                role_bullets = RoleBullets(
                    role_id=f"{role.company}_{role.title}".replace(" ", "_").lower(),
                    company=role.company,
                    title=role.title,
                    period=role.period,
                    location=role.location,
                    bullets=fallback_bullets,
                    hard_skills=role.hard_skills,
                    soft_skills=role.soft_skills,
                    qa_result=None,
                )
                role_bullets_list.append(role_bullets)

        return role_bullets_list

    def _log_qa_summary(self, qa_results: List, role_bullets_list: List[RoleBullets]) -> None:
        """Log QA summary for all roles."""
        passed = sum(1 for qa in qa_results if qa.passed)
        self._logger.info(f"  QA passed: {passed}/{len(qa_results)} roles")
        for i, qa in enumerate(qa_results):
            if not qa.passed:
                role_id = role_bullets_list[i].role_id if i < len(role_bullets_list) else f"role_{i}"
                self._logger.warning(f"    {role_id}: {len(qa.flagged_bullets)} flagged bullets")

    def _log_grade_result(self, grade_result: GradeResult) -> None:
        """Log grading results."""
        self._logger.info(f"  Composite score: {grade_result.composite_score:.1f}/10")
        self._logger.info(f"  Passed: {grade_result.passed} (threshold: {grade_result.passing_threshold})")
        self._logger.info(f"  Lowest dimension: {grade_result.lowest_dimension}")
        for dim in grade_result.dimension_scores:
            self._logger.info(f"    {dim.dimension}: {dim.score:.1f}/10")

    def _get_generic_title(self, role_category: str) -> str:
        """Map role category to a generic professional title for the tagline."""
        title_map = {
            "engineering_manager": "Engineering Leader",
            "staff_principal_engineer": "Technical Leader",
            "director_of_engineering": "Engineering Executive",
            "head_of_engineering": "Engineering Executive",
            "cto": "Technology Executive",
            "tech_lead": "Technical Leader",
            "senior_engineer": "Software Engineer",
        }
        return title_map.get(role_category, "Engineering Professional")

    def _assemble_cv_text(
        self,
        header: HeaderOutput,
        stitched: StitchedCV,
        candidate: CandidateData,
        job_location: str = "",
        extracted_jd: Dict = None,
    ) -> str:
        """Assemble the full CV markdown text with formatting.

        Supports markdown formatting that will be parsed by TipTap editor:
        - **bold** for section headers and role titles
        - *italic* for tagline
        - Dot separators for elegant contact info
        """
        lines = []
        extracted_jd = extracted_jd or {}

        # Header with name in uppercase (as H1 heading)
        lines.append(f"# {candidate.name.upper()}")

        # Role tagline (H3): JD Title · Generic Title
        job_title = extracted_jd.get("title", "Engineering Professional")
        role_category = extracted_jd.get("role_category", "engineering_manager")
        generic_title = self._get_generic_title(role_category)
        lines.append(f"### {job_title} · {generic_title}")

        # Build contact info with dot separators - elegant styling, no emojis
        contact_parts = []
        if candidate.email:
            contact_parts.append(candidate.email)
        if candidate.phone:
            contact_parts.append(candidate.phone)
        if candidate.linkedin:
            contact_parts.append(candidate.linkedin)
        if candidate.location:
            contact_parts.append(candidate.location)

        contact_line = " · ".join(contact_parts)
        lines.append(f"*{contact_line}*")  # Italic formatting

        # GAP-014: Add relocation tagline for Middle East locations
        if job_location and is_middle_east_location(job_location):
            lines.append(RELOCATION_TAGLINE)
            self._logger.info(f"  [GAP-014] Added relocation tagline for: {job_location}")

        lines.append("")

        # Profile - bold section header, sanitize LLM output
        lines.append("**PROFILE**")
        lines.append(sanitize_markdown(header.profile.text))
        lines.append("")

        # Core competencies / Skills - bold section header and category names
        lines.append("**CORE COMPETENCIES**")
        for section in header.skills_sections:
            skill_names = ", ".join(section.skill_names)
            lines.append(f"**{section.category}:** {skill_names}")
        lines.append("")

        # Professional Experience - bold section header
        lines.append("**PROFESSIONAL EXPERIENCE**")
        lines.append("")

        for role in stitched.roles:
            # Role header: Bold company • title | location | period
            location_part = f" | {role.location}" if role.location else ""
            lines.append(f"**{role.company} • {role.title}**{location_part} | {role.period}")
            lines.append("")
            for bullet in role.bullets:
                # GAP-006: Sanitize any markdown that slipped through LLM prompts
                clean_bullet = sanitize_bullet_text(bullet)
                lines.append(f"• {clean_bullet}")
            # Add skills line for this role (computed in stitcher: JD-matching first, then role-specific)
            if role.skills:
                skills_str = ", ".join(role.skills[:8])  # Max 8 skills
                lines.append(f"**Skills:** {skills_str}")
            lines.append("")

        # Education & Certifications - bold section header
        lines.append("**EDUCATION & CERTIFICATIONS**")
        lines.append(f"• {candidate.education_masters}")
        if candidate.education_bachelors:
            lines.append(f"• {candidate.education_bachelors}")
        # Add certifications
        if candidate.certifications:
            for cert in candidate.certifications:
                lines.append(f"• {cert}")
        lines.append("")

        return "\n".join(lines)

    def _get_master_cv_text(self) -> str:
        """Load master CV text for anti-hallucination checking."""
        master_cv_path = Path("data/master-cv/master-cv.md")
        if master_cv_path.exists():
            return master_cv_path.read_text(encoding="utf-8")

        # Fallback: concatenate role files
        roles_dir = Path("data/master-cv/roles")
        if roles_dir.exists():
            role_texts = []
            for role_file in sorted(roles_dir.glob("*.md")):
                role_texts.append(role_file.read_text(encoding="utf-8"))
            return "\n\n".join(role_texts)

        return ""

    def _save_cv_to_disk(self, cv_text: str, company: str, title: str) -> str:
        """Save CV to disk and return the path."""
        # Create output directory
        output_dir = Path("outputs") / sanitize_path_component(company)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        safe_title = sanitize_path_component(title)
        cv_path = output_dir / f"cv_{safe_title}.md"

        # Write CV
        cv_path.write_text(cv_text, encoding="utf-8")
        self._logger.info(f"  CV saved to: {cv_path}")

        return str(cv_path)

    def _build_reasoning(
        self,
        grade_result: GradeResult,
        improvement_result: Optional[ImprovementResult],
        stitched: StitchedCV,
        header: HeaderOutput,
    ) -> str:
        """Build reasoning summary for the generated CV."""
        lines = []

        lines.append("CV GENERATION V2 REASONING")
        lines.append("")

        # Grading summary (GAP-006: no markdown)
        lines.append(f"Quality Score: {grade_result.composite_score:.1f}/10")
        lines.append(f"Passed: {'Yes' if grade_result.passed else 'No'}")
        lines.append("")

        lines.append("Dimension Scores:")
        for dim in grade_result.dimension_scores:
            status = "✓" if dim.score >= 8.5 else "⚠"
            lines.append(f"• {dim.dimension}: {dim.score:.1f}/10 {status}")
        lines.append("")

        # Improvement summary
        if improvement_result and improvement_result.improved:
            lines.append(f"Improvement Applied: {improvement_result.target_dimension}")
            lines.append(f"Changes Made: {len(improvement_result.changes_made)}")
            for change in improvement_result.changes_made[:3]:
                lines.append(f"  • {change}")
            lines.append("")

        # Structure summary
        lines.append("CV Structure:")
        lines.append(f"• Total words: {stitched.total_word_count}")
        lines.append(f"• Total bullets: {stitched.total_bullet_count}")
        lines.append(f"• Roles included: {len(stitched.roles)}")
        lines.append(f"• Skills sections: {len(header.skills_sections)}")

        return "\n".join(lines)


def cv_generator_v2_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for CV Generation V2.

    Drop-in replacement for the legacy generator_node.
    Uses the 6-phase pipeline for higher quality CVs.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer6_v2")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    logger.info("=" * 60)
    logger.info("LAYER 6 V2: CV Generation Pipeline")
    logger.info("=" * 60)

    with LayerContext(struct_logger, 6, "cv_generator_v2") as ctx:
        generator = CVGeneratorV2()
        updates = generator.generate(state)

        # Add metadata from CV Gen V2 output
        cv_output = updates.get("cv_gen_v2_output", {})
        if cv_output:
            ctx.add_metadata("roles_count", len(cv_output.get("roles", [])))
            ctx.add_metadata("grade", cv_output.get("grade"))

        return updates
