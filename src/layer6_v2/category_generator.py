"""
Dynamic Category Generator (GAP-002 Fix).

Generates JD-specific skill categories instead of static 4 categories.

Problem (Before):
- Every CV had the same 4 categories: Leadership, Technical, Platform, Delivery
- This didn't reflect what the JD was actually looking for
- Made CVs feel generic instead of tailored

Solution (After):
- Parse JD keywords, requirements, and technical skills
- Use LLM to cluster skills into 3-4 JD-specific categories
- Category names reflect what the employer is looking for

Example Output:
- For an AI/ML role: ["Machine Learning & AI", "Cloud Platform", "Technical Leadership"]
- For a DevOps role: ["Infrastructure & Cloud", "CI/CD & Automation", "Engineering Leadership"]
- For a Backend role: ["Backend Architecture", "Cloud Services", "Agile Delivery"]

Usage:
    generator = CategoryGenerator()
    categories = generator.generate(
        jd_keywords=["kubernetes", "aws", "python", "machine learning"],
        candidate_skills=["aws", "python", "docker", "terraform"],
        role_category="engineering_manager",
    )
"""

from typing import List, Dict, Optional, Set
from collections import defaultdict

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.logger import get_logger
from src.common.config import Config


class CategoryOutput(BaseModel):
    """Structured output for dynamic category generation."""
    categories: List[str] = Field(
        description="3-4 JD-aligned skill category names",
        min_length=3,
        max_length=4,
    )
    rationale: str = Field(
        description="Brief explanation of why these categories were chosen"
    )


class SkillCategorization(BaseModel):
    """Structured output for skill-to-category mapping."""
    categorized_skills: Dict[str, List[str]] = Field(
        description="Mapping of category names to skills"
    )


class CategoryGenerator:
    """
    Generate dynamic skill categories based on JD requirements.

    Instead of always using [Leadership, Technical, Platform, Delivery],
    this generator creates JD-specific categories that better match
    what the employer is looking for.
    """

    # Default categories to fall back to if LLM fails
    DEFAULT_CATEGORIES = ["Leadership", "Technical", "Platform", "Delivery"]

    # Category generation templates based on role type
    ROLE_CATEGORY_HINTS = {
        "engineering_manager": {
            "hints": ["Technical Leadership", "People Management", "Delivery"],
            "emphasis": "leadership and team-building",
        },
        "staff_principal_engineer": {
            "hints": ["System Architecture", "Technical Strategy", "Engineering Excellence"],
            "emphasis": "technical depth and architectural impact",
        },
        "director_of_engineering": {
            "hints": ["Engineering Leadership", "Organizational Design", "Strategic Delivery"],
            "emphasis": "organizational scaling and strategy",
        },
        "head_of_engineering": {
            "hints": ["Executive Leadership", "Engineering Operations", "Business Alignment"],
            "emphasis": "business impact and executive presence",
        },
        "cto": {
            "hints": ["Technology Strategy", "Business Partnership", "Innovation"],
            "emphasis": "business transformation through technology",
        },
    }

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ):
        """
        Initialize the category generator.

        Args:
            model: LLM model to use (default: Config.DEFAULT_MODEL)
            temperature: Generation temperature (default: 0.3 for consistency)
        """
        self._logger = get_logger(__name__)
        self.temperature = temperature

        model_name = model or Config.DEFAULT_MODEL
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self._logger.info(f"CategoryGenerator initialized with model: {model_name}")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _generate_categories_llm(
        self,
        jd_keywords: List[str],
        candidate_skills: List[str],
        role_category: str,
    ) -> CategoryOutput:
        """
        Use LLM to generate JD-specific categories.

        Args:
            jd_keywords: Keywords extracted from job description
            candidate_skills: Skills the candidate actually has
            role_category: Type of role (engineering_manager, etc.)

        Returns:
            CategoryOutput with 3-4 category names
        """
        # Get role-specific hints
        role_hints = self.ROLE_CATEGORY_HINTS.get(
            role_category,
            self.ROLE_CATEGORY_HINTS["engineering_manager"]
        )

        # Find overlap between JD keywords and candidate skills
        jd_set = {kw.lower() for kw in jd_keywords}
        candidate_set = {s.lower() for s in candidate_skills}
        overlap = jd_set & candidate_set

        system_prompt = """You are a CV optimization expert who creates skill categories for CVs.

Your task: Create 3-4 skill category NAMES that:
1. Align with what the job description is asking for
2. Highlight the candidate's relevant strengths
3. Are specific enough to be meaningful (not generic)
4. Are professional and ATS-friendly

RULES:
- Create exactly 3-4 categories
- Each category name should be 2-4 words
- Categories should reflect the JD's priorities
- Do NOT use generic names like just "Skills" or "Competencies"
- DO use compound names like "Cloud Platform Engineering" or "Agile Delivery"

Return valid JSON with:
{
  "categories": ["Category 1", "Category 2", "Category 3", "Category 4"],
  "rationale": "Brief explanation of why these categories were chosen"
}
"""

        user_prompt = f"""Create skill category names for this CV:

ROLE TYPE: {role_category.replace('_', ' ').title()}
ROLE EMPHASIS: {role_hints['emphasis']}

JD KEYWORDS (what employer wants):
{', '.join(jd_keywords[:20])}

CANDIDATE SKILLS (what they have):
{', '.join(candidate_skills[:30])}

OVERLAP (strong match areas):
{', '.join(overlap) if overlap else 'Limited direct overlap - emphasize transferable skills'}

SUGGESTED CATEGORY THEMES:
{', '.join(role_hints['hints'])}

Generate 3-4 category names that highlight the candidate's fit for this specific role:"""

        structured_llm = self.llm.with_structured_output(CategoryOutput)
        response = structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])

        return response

    def generate(
        self,
        jd_keywords: List[str],
        candidate_skills: List[str],
        role_category: str = "engineering_manager",
    ) -> List[str]:
        """
        Generate JD-specific skill categories.

        Args:
            jd_keywords: Keywords from job description
            candidate_skills: Skills from master-CV
            role_category: Type of role

        Returns:
            List of 3-4 category names
        """
        self._logger.info(f"Generating dynamic categories for {role_category}...")

        try:
            result = self._generate_categories_llm(
                jd_keywords,
                candidate_skills,
                role_category,
            )
            categories = result.categories
            self._logger.info(f"Generated categories: {categories}")
            self._logger.debug(f"Rationale: {result.rationale}")
            return categories

        except Exception as e:
            self._logger.warning(f"LLM category generation failed: {e}. Using defaults.")
            return self.DEFAULT_CATEGORIES

    def categorize_skills(
        self,
        categories: List[str],
        skills: List[str],
        jd_keywords: List[str],
    ) -> Dict[str, List[str]]:
        """
        Assign skills to the generated categories.

        Uses pattern matching first, then LLM for ambiguous cases.

        Args:
            categories: Generated category names
            skills: Candidate skills to categorize
            jd_keywords: JD keywords for prioritization

        Returns:
            Dict mapping category names to skill lists
        """
        self._logger.info(f"Categorizing {len(skills)} skills into {len(categories)} categories...")

        # Initialize result
        categorized: Dict[str, List[str]] = {cat: [] for cat in categories}

        # Pattern-based categorization
        category_patterns = self._build_category_patterns(categories)

        uncategorized = []
        for skill in skills:
            skill_lower = skill.lower()
            assigned = False

            for category, patterns in category_patterns.items():
                if any(pattern in skill_lower for pattern in patterns):
                    categorized[category].append(skill)
                    assigned = True
                    break

            if not assigned:
                uncategorized.append(skill)

        # Assign uncategorized skills using best-fit heuristics
        if uncategorized:
            self._assign_uncategorized_skills(uncategorized, categorized, jd_keywords)

        # Log results
        for cat, cat_skills in categorized.items():
            self._logger.debug(f"  {cat}: {len(cat_skills)} skills")

        return categorized

    def _build_category_patterns(self, categories: List[str]) -> Dict[str, List[str]]:
        """Build pattern lists for each category based on category name."""
        patterns: Dict[str, List[str]] = {}

        for category in categories:
            cat_lower = category.lower()
            category_keywords = []

            # Leadership-related
            if any(term in cat_lower for term in ["lead", "manage", "people", "team"]):
                category_keywords.extend([
                    "leadership", "lead", "manage", "mentor", "coach", "team",
                    "hiring", "interview", "stakeholder", "communication",
                ])

            # Platform/Cloud-related
            if any(term in cat_lower for term in ["platform", "cloud", "infrastructure", "devops"]):
                category_keywords.extend([
                    "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
                    "lambda", "ecs", "eks", "s3", "serverless", "cloud",
                    "ci/cd", "devops", "infrastructure",
                ])

            # Delivery/Process-related
            if any(term in cat_lower for term in ["delivery", "agile", "process", "quality"]):
                category_keywords.extend([
                    "agile", "scrum", "kanban", "sprint", "delivery", "release",
                    "tdd", "bdd", "testing", "quality", "process",
                ])

            # Architecture-related
            if any(term in cat_lower for term in ["architect", "design", "system"]):
                category_keywords.extend([
                    "architecture", "microservices", "ddd", "cqrs", "design",
                    "event-driven", "distributed", "scalab",
                ])

            # Technical/Backend-related (default for technical skills)
            if any(term in cat_lower for term in ["technical", "backend", "engineer", "develop"]):
                category_keywords.extend([
                    "python", "javascript", "typescript", "nodejs", "java",
                    "api", "rest", "graphql", "mongodb", "sql", "redis",
                    "backend", "frontend",
                ])

            patterns[category] = category_keywords

        return patterns

    def _assign_uncategorized_skills(
        self,
        uncategorized: List[str],
        categorized: Dict[str, List[str]],
        jd_keywords: List[str],
    ) -> None:
        """Assign uncategorized skills to best-fit categories."""
        jd_set = {kw.lower() for kw in jd_keywords}

        # Get the category with fewest skills (for balance)
        categories = list(categorized.keys())

        for skill in uncategorized:
            skill_lower = skill.lower()

            # If it's a JD keyword, put it in the most relevant technical category
            if skill_lower in jd_set:
                # Find category that seems most technical
                for cat in categories:
                    if any(term in cat.lower() for term in ["technical", "engineer", "develop", "backend"]):
                        categorized[cat].append(skill)
                        break
                else:
                    # Default to last category if no technical category found
                    categorized[categories[-1]].append(skill)
            else:
                # Put in least populated category for balance
                min_cat = min(categories, key=lambda c: len(categorized[c]))
                categorized[min_cat].append(skill)


def generate_dynamic_categories(
    jd_keywords: List[str],
    candidate_skills: List[str],
    role_category: str = "engineering_manager",
) -> List[str]:
    """
    Convenience function to generate dynamic categories.

    Args:
        jd_keywords: Keywords from job description
        candidate_skills: Skills from master-CV
        role_category: Type of role

    Returns:
        List of 3-4 JD-specific category names
    """
    generator = CategoryGenerator()
    return generator.generate(jd_keywords, candidate_skills, role_category)
