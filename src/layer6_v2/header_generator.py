"""
Header & Skills Generator (Phase 5).

Generates profile summary and skills sections grounded in
the stitched experience section.

Key Principles:
1. Profile includes quantified highlights FROM experience section
2. Skills ONLY include items evidenced in experience bullets
3. JD keywords are prioritized when they have evidence
4. 4 skill categories: Leadership, Technical, Platform, Delivery

Usage:
    generator = HeaderGenerator()
    header = generator.generate(
        stitched_cv=stitched_cv,
        extracted_jd=extracted_jd,
        candidate_data=candidate_data,
    )
"""

import re
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.logger import get_logger
from src.common.config import Config
from src.layer6_v2.types import (
    StitchedCV,
    SkillEvidence,
    SkillsSection,
    ProfileOutput,
    ValidationResult,
    HeaderOutput,
)


# Pydantic models for structured LLM output
class ProfileResponse(BaseModel):
    """Structured response for profile generation."""
    profile_text: str = Field(description="2-3 sentence profile summary")
    highlights_used: List[str] = Field(description="Quantified achievements referenced")
    keywords_integrated: List[str] = Field(description="JD keywords naturally included")


class SkillExtraction(BaseModel):
    """Structured response for skill extraction from bullets."""
    leadership_skills: List[str] = Field(default_factory=list, description="Leadership skills evidenced")
    technical_skills: List[str] = Field(default_factory=list, description="Technical skills evidenced")
    platform_skills: List[str] = Field(default_factory=list, description="Platform/infrastructure skills")
    delivery_skills: List[str] = Field(default_factory=list, description="Delivery/process skills")


class HeaderGenerator:
    """
    Generates CV header sections grounded in experience.

    Features:
    - Profile summary with quantified highlights
    - Skills extraction with evidence tracking
    - JD keyword prioritization
    - Grounding validation
    """

    # Skill category keywords for evidence matching
    SKILL_PATTERNS = {
        "Leadership": [
            r"\b(?:led|managed|mentored|coached|hired|built team|team of \d+|"
            r"cross-functional|stakeholder|collaboration|influence)\b",
        ],
        "Technical": [
            r"\b(?:python|java|typescript|javascript|go|rust|scala|kotlin|"
            r"sql|nosql|graphql|rest|api|microservices|architecture|"
            r"algorithms|data structures|machine learning|ai)\b",
        ],
        "Platform": [
            r"\b(?:aws|azure|gcp|kubernetes|docker|terraform|ci/cd|"
            r"jenkins|github actions|cloud|infrastructure|devops|"
            r"observability|monitoring|grafana|datadog)\b",
        ],
        "Delivery": [
            r"\b(?:agile|scrum|kanban|sprint|shipped|delivered|launched|"
            r"deadline|on-time|reduced time|deployment|release|"
            r"process|workflow|automation)\b",
        ],
    }

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ):
        """
        Initialize the header generator.

        Args:
            model: LLM model to use (default: Config.DEFAULT_MODEL)
            temperature: Generation temperature (default: 0.3 for consistency)
        """
        self._logger = get_logger(__name__)
        self.temperature = temperature

        # Initialize LLM
        model_name = model or Config.DEFAULT_MODEL
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self._logger.info(f"HeaderGenerator initialized with model: {model_name}")

    def _extract_metrics_from_bullets(self, bullets: List[str]) -> List[str]:
        """Extract quantified metrics from bullet points."""
        metrics = []
        for bullet in bullets:
            # Look for percentages
            percentages = re.findall(r'\d+(?:\.\d+)?%', bullet)
            for pct in percentages:
                # Find context around the percentage
                match = re.search(rf'(\w+\s+)?{re.escape(pct)}', bullet)
                if match:
                    metrics.append(f"{match.group(0)}")

            # Look for numbers with context (e.g., "team of 10", "$2M")
            numbers = re.findall(
                r'(?:\$?\d+(?:,\d{3})*(?:\.\d+)?(?:M|K|B)?)\s*(?:engineers?|team|requests?|users?|transactions?)',
                bullet,
                re.IGNORECASE
            )
            metrics.extend(numbers)

        return list(set(metrics))[:5]  # Return top 5 unique metrics

    def _find_skill_evidence(
        self,
        skill: str,
        bullets: List[str],
        roles: List[str],
    ) -> Optional[SkillEvidence]:
        """
        Find evidence for a skill in the bullet points.

        Returns SkillEvidence if found, None otherwise.
        """
        skill_lower = skill.lower()
        evidence_bullets = []
        source_roles = []

        for i, bullet in enumerate(bullets):
            bullet_lower = bullet.lower()
            if skill_lower in bullet_lower:
                evidence_bullets.append(bullet)
                # Map bullet index to role (simplified - assumes sequential)
                if i < len(roles):
                    source_roles.append(roles[i])

        if evidence_bullets:
            return SkillEvidence(
                skill=skill,
                evidence_bullets=evidence_bullets[:3],  # Limit to 3 examples
                source_roles=list(set(source_roles)),
                is_jd_keyword=False,  # Will be set by caller
            )
        return None

    def _extract_skills_from_bullets(
        self,
        bullets: List[str],
        role_companies: List[str],
        jd_keywords: Optional[List[str]] = None,
    ) -> Dict[str, List[SkillEvidence]]:
        """
        Extract skills from bullets with evidence tracking.

        Uses pattern matching to find skills and their evidence.
        Also includes JD keywords when they have evidence in bullets.
        """
        skills_by_category: Dict[str, List[SkillEvidence]] = {
            "Leadership": [],
            "Technical": [],
            "Platform": [],
            "Delivery": [],
        }

        combined_text = " ".join(bullets).lower()

        # Expanded pre-defined skill lists for extraction
        skill_lists = {
            "Leadership": [
                "Team Leadership", "Mentorship", "Hiring", "Cross-functional Collaboration",
                "Stakeholder Management", "Strategic Planning", "People Management",
                "Engineering Management", "Technical Leadership", "Coaching", "Performance Management",
                "Talent Development", "Team Building", "Executive Communication",
            ],
            "Technical": [
                # Languages
                "Python", "Java", "TypeScript", "JavaScript", "Go", "Rust", "Scala", "Kotlin",
                "C#", ".NET", ".NET Core", "Node.js", "Ruby", "PHP",
                # Databases
                "SQL", "NoSQL", "PostgreSQL", "MySQL", "MongoDB", "MS SQL Server", "Redis", "DynamoDB",
                # APIs & Architecture
                "REST API", "REST APIs", "GraphQL", "gRPC", "Microservices", "System Design",
                "Event-Driven Architecture", "CQRS", "Domain-Driven Design",
                # Messaging
                "RabbitMQ", "Kafka", "SQS", "Event Sourcing",
                # Other
                "Machine Learning", "Data Engineering", "Backend Development",
            ],
            "Platform": [
                "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform", "OpenShift",
                "CI/CD", "GitHub Actions", "Jenkins", "GitLab CI", "DevOps", "Cloud Infrastructure",
                "Observability", "Monitoring", "DataDog", "Grafana", "Prometheus",
                "ECS", "EKS", "Lambda", "CloudFormation",
            ],
            "Delivery": [
                "Agile", "Scrum", "Kanban", "Sprint Planning", "Release Management",
                "Process Improvement", "Automation", "Project Management",
                "Continuous Delivery", "Technical Program Management",
                "Code Quality", "Code Review", "TDD", "Test-Driven Development",
            ],
        }

        # Add JD keywords to skill lists (categorized by pattern matching)
        if jd_keywords:
            jd_keywords_to_check = set()
            for kw in jd_keywords:
                kw_lower = kw.lower()
                # Categorize JD keywords
                if any(term in kw_lower for term in ["lead", "manage", "mentor", "coach", "team"]):
                    if kw not in skill_lists["Leadership"]:
                        skill_lists["Leadership"].append(kw)
                elif any(term in kw_lower for term in ["aws", "azure", "gcp", "kubernetes", "docker", "ci/cd", "devops", "openshift"]):
                    if kw not in skill_lists["Platform"]:
                        skill_lists["Platform"].append(kw)
                elif any(term in kw_lower for term in ["agile", "scrum", "kanban", "project", "delivery", "quality"]):
                    if kw not in skill_lists["Delivery"]:
                        skill_lists["Delivery"].append(kw)
                else:
                    # Default technical skills
                    if kw not in skill_lists["Technical"]:
                        jd_keywords_to_check.add(kw)

            # Add remaining JD keywords to Technical
            for kw in jd_keywords_to_check:
                if kw not in skill_lists["Technical"]:
                    skill_lists["Technical"].append(kw)

        for category, skills in skill_lists.items():
            for skill in skills:
                evidence = self._find_skill_evidence(skill, bullets, role_companies)
                if evidence:
                    skills_by_category[category].append(evidence)

        return skills_by_category

    def _prioritize_jd_keywords(
        self,
        skills_by_category: Dict[str, List[SkillEvidence]],
        jd_keywords: List[str],
    ) -> Dict[str, List[SkillEvidence]]:
        """
        Prioritize JD keywords that have evidence.

        Marks JD keywords and moves them to the front of each category.
        """
        jd_keywords_lower = {kw.lower() for kw in jd_keywords}

        for category, skills in skills_by_category.items():
            # Mark JD keywords
            for skill in skills:
                if skill.skill.lower() in jd_keywords_lower:
                    skill.is_jd_keyword = True

            # Sort: JD keywords first, then alphabetically
            skills_by_category[category] = sorted(
                skills,
                key=lambda s: (not s.is_jd_keyword, s.skill.lower())
            )

        return skills_by_category

    def validate_skills_grounded(
        self,
        skills_sections: List[SkillsSection],
        stitched_cv: StitchedCV,
    ) -> ValidationResult:
        """
        Verify all skills are evidenced in experience.

        Returns ValidationResult with grounded/ungrounded skills.
        """
        all_bullets = []
        for role in stitched_cv.roles:
            all_bullets.extend(role.bullets)
        combined_text = " ".join(all_bullets).lower()

        grounded = []
        ungrounded = []
        evidence_map: Dict[str, List[str]] = {}

        for section in skills_sections:
            for skill_evidence in section.skills:
                skill = skill_evidence.skill
                if skill.lower() in combined_text or skill_evidence.evidence_bullets:
                    grounded.append(skill)
                    evidence_map[skill] = skill_evidence.evidence_bullets
                else:
                    ungrounded.append(skill)

        return ValidationResult(
            passed=len(ungrounded) == 0,
            grounded_skills=grounded,
            ungrounded_skills=ungrounded,
            evidence_map=evidence_map,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _generate_profile_llm(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_name: str,
    ) -> ProfileResponse:
        """
        Generate profile using LLM with structured output.

        Uses Pydantic for response validation.
        """
        # Collect all bullets for context
        all_bullets = []
        for role in stitched_cv.roles:
            all_bullets.extend(role.bullets)

        # Extract top metrics for grounding
        top_metrics = self._extract_metrics_from_bullets(all_bullets)

        # Build prompt
        system_prompt = """You are a CV profile writer specializing in executive summaries.

Your mission: Write a 2-3 sentence profile summary that:
1. Leads with the candidate's core superpower for the target role
2. Includes 1-2 quantified highlights FROM the experience bullets provided
3. Uses 2-3 JD keywords naturally
4. Matches the seniority level of the target role

RULES:
- ONLY reference achievements that appear in the experience bullets
- ONLY use metrics that appear EXACTLY in the bullets (no rounding or inventing)
- Keep to 50-80 words
- Write in third person or omit subject (e.g., "Engineering leader with..." not "I am...")

Return valid JSON with:
{
  "profile_text": "The 2-3 sentence profile",
  "highlights_used": ["metric 1 used", "metric 2 used"],
  "keywords_integrated": ["keyword1", "keyword2"]
}
"""

        user_prompt = f"""Write a profile summary for {candidate_name}.

TARGET ROLE: {extracted_jd.get('title', 'Engineering Leader')}
ROLE CATEGORY: {extracted_jd.get('role_category', 'engineering_manager')}
TOP JD KEYWORDS: {', '.join(extracted_jd.get('top_keywords', [])[:10])}

EXPERIENCE BULLETS (use ONLY achievements from these):
{chr(10).join(f'• {b}' for b in all_bullets[:15])}

QUANTIFIED METRICS AVAILABLE:
{chr(10).join(f'- {m}' for m in top_metrics)}

Generate the profile JSON:"""

        # Call LLM with structured output
        structured_llm = self.llm.with_structured_output(ProfileResponse)
        response = structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])

        return response

    def generate_profile(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_name: str,
    ) -> ProfileOutput:
        """
        Generate profile summary grounded in achievements.

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted JD intelligence
            candidate_name: Candidate name for profile

        Returns:
            ProfileOutput with grounded summary
        """
        self._logger.info("Generating profile summary...")

        try:
            response = self._generate_profile_llm(stitched_cv, extracted_jd, candidate_name)
            profile = ProfileOutput(
                text=response.profile_text,
                highlights_used=response.highlights_used,
                keywords_integrated=response.keywords_integrated,
            )
        except Exception as e:
            self._logger.warning(f"LLM profile generation failed: {e}. Using fallback.")
            # Fallback: Simple template-based profile
            role_category = extracted_jd.get("role_category", "engineering_manager")
            profile = self._generate_fallback_profile(stitched_cv, role_category, candidate_name)

        self._logger.info(f"Profile generated: {profile.word_count} words")
        return profile

    def _generate_fallback_profile(
        self,
        stitched_cv: StitchedCV,
        role_category: str,
        candidate_name: str,
    ) -> ProfileOutput:
        """Generate a simple fallback profile when LLM fails."""
        # Extract some metrics
        all_bullets = []
        for role in stitched_cv.roles:
            all_bullets.extend(role.bullets)
        metrics = self._extract_metrics_from_bullets(all_bullets)

        # Role-specific opening
        openings = {
            "engineering_manager": "Engineering leader with track record of building high-performing teams",
            "staff_principal_engineer": "Staff engineer specializing in system architecture and technical strategy",
            "director_of_engineering": "Engineering director experienced in scaling organizations",
            "head_of_engineering": "Head of Engineering with experience building engineering functions",
            "cto": "Technology executive driving business outcomes through engineering excellence",
        }

        opening = openings.get(role_category, openings["engineering_manager"])
        metric_phrase = f", achieving {metrics[0]}" if metrics else ""

        text = f"{opening}{metric_phrase}. Proven ability to deliver complex technical initiatives while developing talent and improving processes."

        return ProfileOutput(
            text=text,
            highlights_used=metrics[:2],
            keywords_integrated=[],
        )

    def generate_skills(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
    ) -> List[SkillsSection]:
        """
        Generate skills sections grounded in experience.

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted JD intelligence

        Returns:
            List of SkillsSection with evidence tracking
        """
        self._logger.info("Extracting skills from experience...")

        # Collect all bullets and role companies
        all_bullets = []
        role_companies = []
        for role in stitched_cv.roles:
            for bullet in role.bullets:
                all_bullets.append(bullet)
                role_companies.append(role.company)

        # Extract JD keywords for skill matching
        jd_keywords = extracted_jd.get("top_keywords", [])
        # Also include technical_skills from JD
        jd_technical = extracted_jd.get("technical_skills", [])
        all_jd_keywords = list(set(jd_keywords + jd_technical))

        # Extract skills with evidence, including JD keywords
        skills_by_category = self._extract_skills_from_bullets(
            all_bullets, role_companies, jd_keywords=all_jd_keywords
        )
        skills_by_category = self._prioritize_jd_keywords(skills_by_category, jd_keywords)

        # Build SkillsSection objects
        sections = []
        for category in ["Leadership", "Technical", "Platform", "Delivery"]:
            skills = skills_by_category.get(category, [])
            if skills:  # Only include categories with skills
                sections.append(SkillsSection(
                    category=category,
                    skills=skills[:8],  # Limit to 8 skills per category
                ))

        self._logger.info(f"Extracted {sum(s.skill_count for s in sections)} skills across {len(sections)} categories")
        return sections

    def generate(
        self,
        stitched_cv: StitchedCV,
        extracted_jd: Dict,
        candidate_data: Dict,
    ) -> HeaderOutput:
        """
        Generate complete header with profile, skills, and education.

        Args:
            stitched_cv: Stitched experience section
            extracted_jd: Extracted JD intelligence
            candidate_data: Candidate info (name, email, phone, linkedin, education, certifications, languages)

        Returns:
            HeaderOutput with all header sections
        """
        self._logger.info("Generating CV header sections...")

        # Extract candidate info - support both flat dict and nested dict formats
        if "header" in candidate_data:
            # Nested format (legacy)
            candidate_name = candidate_data.get("header", {}).get("name", "Candidate")
            contact_info = candidate_data.get("header", {}).get("contact", {})
            contact_info["name"] = candidate_name
            education = candidate_data.get("education", [])
            certifications = candidate_data.get("certifications", [])
            languages = candidate_data.get("languages", [])
        else:
            # Flat format (from orchestrator)
            candidate_name = candidate_data.get("name", "Candidate")
            contact_info = {
                "name": candidate_name,
                "email": candidate_data.get("email", ""),
                "phone": candidate_data.get("phone", ""),
                "linkedin": candidate_data.get("linkedin", ""),
                "location": candidate_data.get("location", ""),
            }
            education = candidate_data.get("education", [])
            certifications = candidate_data.get("certifications", [])
            languages = candidate_data.get("languages", [])

        # Generate profile
        profile = self.generate_profile(stitched_cv, extracted_jd, candidate_name)

        # Generate skills
        skills_sections = self.generate_skills(stitched_cv, extracted_jd)

        # Validate grounding
        validation = self.validate_skills_grounded(skills_sections, stitched_cv)
        if not validation.passed:
            self._logger.warning(
                f"Skills validation failed. Ungrounded skills: {validation.ungrounded_skills}"
            )
            # Remove ungrounded skills
            skills_sections = self._remove_ungrounded_skills(
                skills_sections, validation.ungrounded_skills
            )
            validation = self.validate_skills_grounded(skills_sections, stitched_cv)

        # Build final output
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills_sections,
            education=education,
            contact_info=contact_info,
            certifications=certifications,
            languages=languages,
            validation_result=validation,
        )

        self._logger.info(f"Header generation complete:")
        self._logger.info(f"  Profile: {profile.word_count} words")
        self._logger.info(f"  Skills: {header.total_skills_count} across {len(skills_sections)} categories")
        self._logger.info(f"  Validation: {'PASSED' if validation.passed else 'FAILED'}")

        return header

    def _remove_ungrounded_skills(
        self,
        skills_sections: List[SkillsSection],
        ungrounded: List[str],
    ) -> List[SkillsSection]:
        """Remove ungrounded skills from sections."""
        ungrounded_lower = {s.lower() for s in ungrounded}
        filtered_sections = []

        for section in skills_sections:
            filtered_skills = [
                s for s in section.skills
                if s.skill.lower() not in ungrounded_lower
            ]
            if filtered_skills:
                filtered_sections.append(SkillsSection(
                    category=section.category,
                    skills=filtered_skills,
                ))

        return filtered_sections


def generate_header(
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_data: Dict,
) -> HeaderOutput:
    """
    Convenience function to generate CV header.

    Args:
        stitched_cv: Stitched experience section
        extracted_jd: Extracted JD intelligence
        candidate_data: Candidate info (name, contact, education)

    Returns:
        HeaderOutput with all header sections
    """
    generator = HeaderGenerator()
    return generator.generate(stitched_cv, extracted_jd, candidate_data)
