"""
Skills Taxonomy Module - Role-Based Skills Selection.

Replaces the LLM-generated CategoryGenerator with a pre-defined,
role-specific skills taxonomy. This provides:
- Zero hallucinations (only candidate's real skills)
- ATS-optimized section names
- Predictable structure for manual pruning
- 1.3x "lax" generation for choice

Key Components:
- SkillsTaxonomy: Loads and manages the taxonomy JSON
- TaxonomyBasedSkillsGenerator: Generates skills sections using the taxonomy

Usage:
    taxonomy = SkillsTaxonomy()
    generator = TaxonomyBasedSkillsGenerator(taxonomy, skill_whitelist)
    sections = generator.generate_sections(extracted_jd, bullets, roles)
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass

from src.common.logger import get_logger
from src.layer6_v2.types import (
    TaxonomySection,
    RoleSkillsTaxonomy,
    SectionScore,
    SkillScore,
    SkillEvidence,
    SkillsSection,
    HeaderGenerationContext,
)


# Default path to taxonomy file
DEFAULT_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "master-cv" / "role_skills_taxonomy.json"


class SkillsTaxonomy:
    """
    Loads and manages the role-based skills taxonomy.

    The taxonomy defines pre-curated skill sections for each target role,
    with JD signals to determine which sections are most relevant.
    """

    def __init__(self, taxonomy_path: Optional[Path] = None, taxonomy_data: Optional[Dict] = None):
        """
        Initialize the taxonomy loader.

        Args:
            taxonomy_path: Path to the taxonomy JSON file.
                          Defaults to data/master-cv/role_skills_taxonomy.json
            taxonomy_data: Pre-loaded taxonomy data (from MongoDB).
                          If provided, file loading is skipped.
        """
        self._logger = get_logger(__name__)
        self._taxonomy_path = taxonomy_path or DEFAULT_TAXONOMY_PATH
        self._taxonomy_data: Dict = {}
        self._skill_aliases: Dict[str, List[str]] = {}
        self._default_role: str = "engineering_manager"

        if taxonomy_data:
            # Use pre-loaded data (e.g., from MongoDB)
            self._taxonomy_data = taxonomy_data
            self._skill_aliases = taxonomy_data.get("skill_aliases", {})
            self._default_role = taxonomy_data.get("default_fallback_role", "engineering_manager")
            self._logger.info(
                f"Loaded skills taxonomy from dict: {len(self._taxonomy_data.get('target_roles', {}))} roles"
            )
        else:
            self._load_taxonomy()

    @classmethod
    def from_dict(cls, taxonomy_data: Dict) -> "SkillsTaxonomy":
        """
        Create a SkillsTaxonomy from pre-loaded dictionary data.

        This factory method enables loading taxonomy from MongoDB
        without needing a file path.

        Args:
            taxonomy_data: Taxonomy data dictionary (same structure as JSON file)

        Returns:
            SkillsTaxonomy instance initialized from the data
        """
        return cls(taxonomy_data=taxonomy_data)

    def _load_taxonomy(self) -> None:
        """Load the taxonomy from the JSON file."""
        try:
            with open(self._taxonomy_path, "r", encoding="utf-8") as f:
                self._taxonomy_data = json.load(f)

            self._skill_aliases = self._taxonomy_data.get("skill_aliases", {})
            self._default_role = self._taxonomy_data.get("default_fallback_role", "engineering_manager")

            self._logger.info(
                f"Loaded skills taxonomy: {len(self._taxonomy_data.get('target_roles', {}))} roles, "
                f"{len(self._skill_aliases)} aliases"
            )
        except FileNotFoundError:
            self._logger.error(f"Taxonomy file not found: {self._taxonomy_path}")
            raise
        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid JSON in taxonomy file: {e}")
            raise

    def get_role_taxonomy(self, role_category: str) -> RoleSkillsTaxonomy:
        """
        Get the taxonomy for a specific role category.

        Args:
            role_category: The role category (e.g., "engineering_manager")

        Returns:
            RoleSkillsTaxonomy for the role, or default if not found
        """
        target_roles = self._taxonomy_data.get("target_roles", {})

        # Try exact match first
        role_data = target_roles.get(role_category)

        # Fall back to default if not found
        if not role_data:
            self._logger.warning(
                f"Role '{role_category}' not in taxonomy, using '{self._default_role}'"
            )
            role_data = target_roles.get(self._default_role, {})
            role_category = self._default_role

        # Parse sections
        sections = []
        for section_data in role_data.get("sections", []):
            sections.append(TaxonomySection(
                name=section_data.get("name", ""),
                priority=section_data.get("priority", 99),
                description=section_data.get("description", ""),
                skills=section_data.get("skills", []),
                jd_signals=section_data.get("jd_signals", []),
            ))

        return RoleSkillsTaxonomy(
            role_category=role_category,
            display_name=role_data.get("display_name", role_category),
            sections=sections,
            max_sections=role_data.get("max_sections", 4),
            max_skills_per_section=role_data.get("max_skills_per_section", 6),
            lax_multiplier=role_data.get("lax_multiplier", 1.3),
        )

    def get_available_roles(self) -> List[str]:
        """Return list of available role categories."""
        return list(self._taxonomy_data.get("target_roles", {}).keys())

    def _coerce_to_list(self, value) -> List[str]:
        """Coerce a value to a list of strings.

        Handles inconsistent YAML/JSON data where a value might be
        a string instead of a list.
        """
        if isinstance(value, str):
            return [value]
        elif isinstance(value, list):
            return value
        elif value is None:
            return []
        else:
            return list(value)

    def skill_matches(self, skill: str, target: str) -> bool:
        """
        Check if a skill matches a target (considering aliases).

        Args:
            skill: The skill to check
            target: The target to match against

        Returns:
            True if skill matches target or any of its aliases
        """
        skill_lower = skill.lower()
        target_lower = target.lower()

        # Direct match
        if skill_lower == target_lower:
            return True

        # Check if skill is an alias of target
        for alias_key, aliases in self._skill_aliases.items():
            aliases = self._coerce_to_list(aliases)
            aliases_lower = [a.lower() for a in aliases]
            if target_lower == alias_key.lower() or target_lower in aliases_lower:
                if skill_lower == alias_key.lower() or skill_lower in aliases_lower:
                    return True

        return False

    def get_skill_aliases(self, skill: str) -> List[str]:
        """
        Get all aliases for a skill.

        Args:
            skill: The skill to look up

        Returns:
            List of aliases (including the skill itself)
        """
        skill_lower = skill.lower()
        result = [skill]

        for alias_key, aliases in self._skill_aliases.items():
            aliases = self._coerce_to_list(aliases)
            aliases_lower = [a.lower() for a in aliases]
            if skill_lower == alias_key.lower() or skill_lower in aliases_lower:
                result.extend([alias_key] + aliases)
                break

        return list(set(result))


class TaxonomyBasedSkillsGenerator:
    """
    Generates skills sections using the pre-defined taxonomy.

    Replaces the LLM-based CategoryGenerator with deterministic,
    taxonomy-based selection that ensures:
    1. Only candidate's real skills appear (whitelist validation)
    2. Sections are selected based on JD alignment
    3. Skills within sections are ranked and selected
    4. "Lax" mode generates slightly more for manual pruning
    """

    # Minimum score threshold for including a section
    MIN_SECTION_SCORE = 0.15

    # Minimum sections to always include (even if low scores)
    MIN_SECTIONS = 3

    def __init__(
        self,
        taxonomy: SkillsTaxonomy,
        skill_whitelist: Dict[str, List[str]],
        lax_mode: bool = True,
        annotation_context: Optional[HeaderGenerationContext] = None,
    ):
        """
        Initialize the taxonomy-based generator.

        Args:
            taxonomy: SkillsTaxonomy instance for loading role taxonomies
            skill_whitelist: Candidate's skill whitelist (hard_skills, soft_skills)
            lax_mode: If True, generate more skills than target for pruning
            annotation_context: Phase 4.5 - HeaderGenerationContext with annotation
                               priorities for skill scoring boost
        """
        self._logger = get_logger(__name__)
        self._taxonomy = taxonomy
        self._skill_whitelist = skill_whitelist
        self._lax_mode = lax_mode

        # Phase 4.5: Store annotation context for skill scoring
        self._annotation_context = annotation_context
        self._annotation_skills: Set[str] = set()
        self._annotation_must_haves: Set[str] = set()
        self._annotation_boosts: Dict[str, float] = {}

        if annotation_context and annotation_context.has_annotations:
            self._build_annotation_skill_index(annotation_context)
            self._logger.info(
                f"Using annotation context: {len(self._annotation_skills)} annotated skills, "
                f"{len(self._annotation_must_haves)} must-haves"
            )

        # Build normalized whitelist for fast lookup
        self._whitelist_lower: Set[str] = set()
        for skill in skill_whitelist.get("hard_skills", []):
            self._whitelist_lower.add(skill.lower())
        for skill in skill_whitelist.get("soft_skills", []):
            self._whitelist_lower.add(skill.lower())

        self._logger.info(
            f"TaxonomyBasedSkillsGenerator initialized: "
            f"{len(self._whitelist_lower)} whitelisted skills, lax_mode={lax_mode}"
        )

    def _build_annotation_skill_index(self, context: HeaderGenerationContext) -> None:
        """
        Build an index of annotated skills for fast lookup.

        Creates sets and boost maps for:
        - All annotated skills
        - Must-have skills (highest priority)
        - Boost values per skill

        Phase 4.5: Annotation-aware skill scoring.
        """
        from src.common.annotation_types import RELEVANCE_MULTIPLIERS, REQUIREMENT_MULTIPLIERS

        for priority in context.priorities:
            # Index matching skill
            if priority.matching_skill:
                skill_lower = priority.matching_skill.lower()
                self._annotation_skills.add(skill_lower)

                # Track must-haves separately
                if priority.is_must_have:
                    self._annotation_must_haves.add(skill_lower)

                # Calculate and store boost
                relevance_boost = RELEVANCE_MULTIPLIERS.get(priority.relevance, 1.0)
                requirement_boost = REQUIREMENT_MULTIPLIERS.get(priority.requirement_type, 1.0)
                boost = relevance_boost * requirement_boost
                # Keep the highest boost for this skill
                if skill_lower not in self._annotation_boosts or boost > self._annotation_boosts[skill_lower]:
                    self._annotation_boosts[skill_lower] = boost

            # Also index ATS variants
            for variant in priority.ats_variants:
                variant_lower = variant.lower()
                self._annotation_skills.add(variant_lower)
                if priority.is_must_have:
                    self._annotation_must_haves.add(variant_lower)

    def generate_sections(
        self,
        extracted_jd: Dict,
        experience_bullets: List[str],
        role_companies: List[str],
    ) -> List[SkillsSection]:
        """
        Generate skills sections using the taxonomy.

        Args:
            extracted_jd: Extracted JD intelligence
            experience_bullets: All experience bullets for evidence finding
            role_companies: Company names for evidence tracking

        Returns:
            List of SkillsSection objects with evidence tracking
        """
        # Get target role category from JD
        role_category = extracted_jd.get("role_category", "engineering_manager")
        self._logger.info(f"Generating skills sections for role: {role_category}")

        # Load taxonomy for this role
        role_taxonomy = self._taxonomy.get_role_taxonomy(role_category)

        # Extract JD keywords and responsibilities (with type coercion for LLM output)
        jd_keywords = extracted_jd.get("top_keywords", [])
        if isinstance(jd_keywords, str):
            jd_keywords = [k.strip() for k in jd_keywords.split(",") if k.strip()]
        elif not isinstance(jd_keywords, list):
            jd_keywords = []

        jd_technical = extracted_jd.get("technical_skills", [])
        if isinstance(jd_technical, str):
            jd_technical = [t.strip() for t in jd_technical.split(",") if t.strip()]
        elif not isinstance(jd_technical, list):
            jd_technical = []

        jd_responsibilities = extracted_jd.get("responsibilities", [])
        if isinstance(jd_responsibilities, str):
            jd_responsibilities = [r.strip() for r in jd_responsibilities.split(",") if r.strip()]
        elif not isinstance(jd_responsibilities, list):
            jd_responsibilities = []

        all_jd_keywords = list(set(jd_keywords + jd_technical))

        # Select sections based on JD alignment
        selected_sections = self._select_sections(
            role_taxonomy=role_taxonomy,
            jd_keywords=all_jd_keywords,
            jd_responsibilities=jd_responsibilities,
        )

        # Generate skills for each section
        skills_sections = []
        for taxonomy_section in selected_sections:
            section = self._generate_section_skills(
                taxonomy_section=taxonomy_section,
                role_taxonomy=role_taxonomy,
                jd_keywords=all_jd_keywords,
                experience_bullets=experience_bullets,
                role_companies=role_companies,
            )
            if section and section.skills:
                skills_sections.append(section)

        self._logger.info(
            f"Generated {len(skills_sections)} sections with "
            f"{sum(s.skill_count for s in skills_sections)} total skills"
        )

        return skills_sections

    def _select_sections(
        self,
        role_taxonomy: RoleSkillsTaxonomy,
        jd_keywords: List[str],
        jd_responsibilities: List[str],
    ) -> List[TaxonomySection]:
        """
        Select which sections to include based on JD alignment.

        Args:
            role_taxonomy: Taxonomy for the target role
            jd_keywords: Keywords from the JD
            jd_responsibilities: Responsibilities from the JD

        Returns:
            List of TaxonomySection objects to include
        """
        jd_keywords_lower = {kw.lower() for kw in jd_keywords}
        jd_responsibilities_text = " ".join(jd_responsibilities).lower()

        # Score each section
        section_scores: List[SectionScore] = []
        max_priority = max(s.priority for s in role_taxonomy.sections)

        for section in role_taxonomy.sections:
            # Calculate JD keyword overlap score
            signals_lower = {sig.lower() for sig in section.jd_signals}
            keyword_overlap = len(signals_lower & jd_keywords_lower)
            jd_keyword_score = keyword_overlap / len(section.jd_signals) if section.jd_signals else 0.0

            # Calculate responsibility match score (fuzzy matching)
            responsibility_matches = sum(
                1 for sig in section.jd_signals
                if sig.lower() in jd_responsibilities_text
            )
            responsibility_score = responsibility_matches / len(section.jd_signals) if section.jd_signals else 0.0

            # Calculate priority score (higher priority = higher score)
            priority_score = (max_priority - section.priority + 1) / max_priority

            section_scores.append(SectionScore(
                section=section,
                jd_keyword_score=min(1.0, jd_keyword_score),  # Cap at 1.0
                responsibility_score=min(1.0, responsibility_score),
                priority_score=priority_score,
            ))

        # Sort by total score descending
        section_scores.sort(key=lambda s: s.total_score, reverse=True)

        # Log scores for debugging
        for score in section_scores:
            self._logger.debug(
                f"Section '{score.section.name}': score={score.total_score:.2f} "
                f"(kw={score.jd_keyword_score:.2f}, resp={score.responsibility_score:.2f}, "
                f"prio={score.priority_score:.2f})"
            )

        # Select sections: top N that meet threshold, or at least MIN_SECTIONS
        selected = []
        for score in section_scores:
            if len(selected) < role_taxonomy.max_sections:
                if score.total_score >= self.MIN_SECTION_SCORE or len(selected) < self.MIN_SECTIONS:
                    selected.append(score.section)

        self._logger.info(f"Selected {len(selected)} sections: {[s.name for s in selected]}")
        return selected

    def _generate_section_skills(
        self,
        taxonomy_section: TaxonomySection,
        role_taxonomy: RoleSkillsTaxonomy,
        jd_keywords: List[str],
        experience_bullets: List[str],
        role_companies: List[str],
    ) -> Optional[SkillsSection]:
        """
        Generate skills for a single section.

        Args:
            taxonomy_section: The taxonomy section to process
            role_taxonomy: Full role taxonomy (for config)
            jd_keywords: JD keywords for matching
            experience_bullets: Bullets for evidence finding
            role_companies: Company names for evidence tracking

        Returns:
            SkillsSection with selected skills and evidence
        """
        jd_keywords_lower = {kw.lower() for kw in jd_keywords}

        # Calculate target skill count (with lax multiplier)
        base_count = role_taxonomy.max_skills_per_section
        if self._lax_mode:
            target_count = int(base_count * role_taxonomy.lax_multiplier + 0.5)
        else:
            target_count = base_count

        # Score each skill in the section
        skill_scores: List[Tuple[str, SkillScore, Optional[SkillEvidence]]] = []

        for skill in taxonomy_section.skills:
            # Anti-hallucination check: skill must be in whitelist
            if not self._skill_in_whitelist(skill):
                self._logger.debug(f"Skill '{skill}' not in whitelist, skipping")
                continue

            # Find evidence for this skill
            evidence = self._find_skill_evidence(skill, experience_bullets, role_companies)

            # Skip skills with no evidence (grounding requirement)
            if not evidence or not evidence.evidence_bullets:
                self._logger.debug(f"Skill '{skill}' has no evidence, skipping")
                continue

            # Calculate skill score
            jd_match = 1.0 if self._skill_matches_jd(skill, jd_keywords_lower) else 0.0
            evidence_score = min(1.0, len(evidence.evidence_bullets) / 5)  # Cap at 5 bullets
            recency_score = 0.7  # Default recency (could be enhanced with actual recency data)

            # Phase 4.5: Calculate annotation boost
            annotation_boost = self._get_annotation_boost(skill)

            skill_score = SkillScore(
                skill=skill,
                jd_match_score=jd_match,
                evidence_score=evidence_score,
                recency_score=recency_score,
                annotation_boost=annotation_boost,
            )

            # Mark as JD keyword or annotated skill
            evidence.is_jd_keyword = jd_match > 0 or annotation_boost > 1.0

            skill_scores.append((skill, skill_score, evidence))

        # Sort by score and select top N
        skill_scores.sort(key=lambda x: x[1].total_score, reverse=True)
        selected = skill_scores[:target_count]

        if not selected:
            return None

        # Build SkillsSection with evidence
        skills_with_evidence = [evidence for _, _, evidence in selected if evidence]

        # Log selection
        self._logger.debug(
            f"Section '{taxonomy_section.name}': selected {len(skills_with_evidence)} skills "
            f"from {len(taxonomy_section.skills)} candidates"
        )

        return SkillsSection(
            category=taxonomy_section.name,
            skills=skills_with_evidence,
        )

    def _get_annotation_boost(self, skill: str) -> float:
        """
        Get the annotation boost for a skill.

        Phase 4.5: Returns the boost multiplier from annotation context.
        Higher boosts for must_have + core_strength combinations.

        Args:
            skill: The skill to check

        Returns:
            Boost multiplier (1.0 = no boost, >1.0 = boosted)
        """
        if not self._annotation_context or not self._annotation_context.has_annotations:
            return 1.0

        skill_lower = skill.lower()

        # Check direct match
        if skill_lower in self._annotation_boosts:
            return self._annotation_boosts[skill_lower]

        # Check aliases
        aliases = self._taxonomy.get_skill_aliases(skill)
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in self._annotation_boosts:
                return self._annotation_boosts[alias_lower]

        # Check if skill is in the annotated set (but without specific boost)
        if skill_lower in self._annotation_skills:
            return 1.5  # Default boost for annotated skills

        return 1.0

    def _skill_in_whitelist(self, skill: str) -> bool:
        """
        Check if a skill is in the candidate's whitelist.

        Uses alias matching for flexible lookup.

        Args:
            skill: The skill to check

        Returns:
            True if skill or any alias is in whitelist
        """
        skill_lower = skill.lower()

        # Direct check
        if skill_lower in self._whitelist_lower:
            return True

        # Check aliases
        aliases = self._taxonomy.get_skill_aliases(skill)
        for alias in aliases:
            if alias.lower() in self._whitelist_lower:
                return True

        return False

    def _skill_matches_jd(self, skill: str, jd_keywords_lower: Set[str]) -> bool:
        """
        Check if a skill matches any JD keyword.

        Uses alias matching and substring matching.

        Args:
            skill: The skill to check
            jd_keywords_lower: Lowercased JD keywords

        Returns:
            True if skill matches any JD keyword
        """
        skill_lower = skill.lower()

        # Direct match
        if skill_lower in jd_keywords_lower:
            return True

        # Substring match (skill in keyword or keyword in skill)
        for kw in jd_keywords_lower:
            if skill_lower in kw or kw in skill_lower:
                return True

        # Check aliases
        aliases = self._taxonomy.get_skill_aliases(skill)
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in jd_keywords_lower:
                return True
            for kw in jd_keywords_lower:
                if alias_lower in kw or kw in alias_lower:
                    return True

        return False

    # Skill evidence patterns: maps skill names to regex patterns that indicate evidence
    # This handles cases where the skill isn't mentioned explicitly but is demonstrated
    # Patterns are case-insensitive and use word boundaries for accuracy
    SKILL_EVIDENCE_PATTERNS = {
        # ═══════════════════════════════════════════════════════════════════════════
        # AWS & CLOUD INFRASTRUCTURE
        # ═══════════════════════════════════════════════════════════════════════════
        "aws": [r"\b(aws|lambda|ecs|eks|s3|cloudfront|eventbridge|dynamodb|rds|ec2|cloudwatch|sqs|sns|api.?gateway|route53|cloudformation|vpc|iam|cognito|athena|glue|kinesis|fargate|aurora)\b"],
        "aws lambda": [r"\b(lambda|serverless.*function|faas)\b"],
        "aws ecs": [r"\b(ecs|elastic.?container|fargate|container.*orchestrat)\b"],
        "eventbridge": [r"\b(eventbridge|event.?bridge|event.?bus|cloudwatch.*event)\b"],
        "serverless architecture": [r"\b(serverless|lambda|function.?as.?a.?service|faas)\b"],
        "terraform": [r"\b(terraform|hcl|infrastructure.?as.?code|iac)\b"],
        "infrastructure as code": [r"\b(terraform|iac|infrastructure.?as.?code|cloudformation|pulumi)\b"],
        "docker": [r"\b(docker|container|containeriz|image|dockerfile)\b"],
        "kubernetes": [r"\b(kubernetes|k8s|eks|gke|aks|helm|pod|kubectl|container.*orchestrat)\b"],
        "ci/cd": [r"\b(ci.?cd|continuous.?integrat|continuous.?deploy|pipeline|deploy.*automat|jenkins|github.*actions|gitlab.*ci|circleci)\b"],
        "observability": [r"\b(observ|monitor|logging|tracing|metric|apm|datadog|grafana|opensearch|prometheus|new.?relic|elastic|kibana|splunk|lightstep|instrumentation)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # LEADERSHIP & MANAGEMENT (detect from action verbs and outcomes)
        # ═══════════════════════════════════════════════════════════════════════════
        "technical leadership": [r"\b(led|lead|leading|drove|spearhead|architected|designed.*system|technical.*lead|tech.*lead|engineering.*lead)\b"],
        "team building": [r"\b(build.*team|built.*team|grow.*team|grew.*team|hired|expand.*team|scal.*team|assemble.*team|forming.*team)\b"],
        "hiring & interviewing": [r"\b(hired|hiring|interviewing|interview|recruit|onboard|talent.*acqui|technical.*assessment)\b"],
        "mentoring": [r"\b(mentor|coaching|coach|guide|develop.*engineer|grow.*engineer|train|nurtur|apprentice)\b"],
        "technical vision": [r"\b(vision|strategy|roadmap|direction|long.?term|multi.?year|technical.*direction)\b"],
        "stakeholder management": [r"\b(stakeholder|executive|cross-functional|align|collaborate.*business|business.*partner)\b"],
        "cross-functional collaboration": [r"\b(cross-functional|cross.?team|collaborate|partner|align.*team|work.*with.*product)\b"],
        "architectural runway": [r"\b(architectural.*runway|runway|tech.*runway|capability.*matur|incremental.*architect)\b"],
        "technical debt strategy": [r"\b(technical.?debt|debt.*reduction|refactor|legacy.*moderniz|tech.?debt|moderniz.*legacy)\b"],
        "engineering standards": [r"\b(standards|best.?practice|quality.*gate|code.*style|engineering.*standards|coding.*guideline)\b"],
        "code review leadership": [r"\b(code.*review|peer.*review|review.*process|pr.*review|pull.*request)\b"],
        "technical hiring": [r"\b(hired.*engineer|tech.*recruit|technical.*assessment|interview.*engineer|hiring.*process)\b"],
        "innovation culture": [r"\b(innovation|experiment|proof.?of.?concept|prototype|hackathon|lean.*friday|poc|spike)\b"],
        "performance management": [r"\b(performance.*review|feedback|goal.*setting|performance.*plan|okr|kpi|evaluation)\b"],
        "1:1 coaching": [r"\b(one.?on.?one|1:1|1-on-1|coaching|individual.*meeting|direct.*report)\b"],
        "career development": [r"\b(career.*growth|development.*plan|promot|succession|career.*path|talent.*develop)\b"],
        "change management": [r"\b(change.*management|organizational.*change|transition|transformation|process.*change)\b"],
        "blameless postmortems": [r"\b(postmortem|post.?mortem|post.?incident|rca|root.*cause|retrospective|blameless)\b"],
        "strategic planning": [r"\b(strategic.*plan|long.?term|vision|strategic.*roadmap|multi.?year|strategy)\b"],
        "risk analysis": [r"\b(risk.*analys|risk.*assess|compliance|mitigation|audit|risk.*management)\b"],
        "roadmap execution": [r"\b(roadmap|delivery.*plan|execution|milestone|quarter.*plan|release.*plan)\b"],
        "process improvement": [r"\b(process.*improv|continuous.*improv|lean|kaizen|efficiency|workflow.*optim)\b"],
        "knowledge sharing": [r"\b(knowledge.*shar|document|wiki|tech.*talk|brown.*bag|training|workshop)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # ARCHITECTURE & DESIGN
        # ═══════════════════════════════════════════════════════════════════════════
        "microservices": [r"\b(microservice|micro.?service|service.?oriented|soa|service.*boundar)\b"],
        "event-driven architecture": [r"\b(event.?driven|event.*sourcing|cqrs|pub.?sub|message|async.*architect|reactive)\b"],
        "domain-driven design": [r"\b(ddd|domain.?driven|bounded.?context|aggregate|ubiquitous.*language|event.*storm)\b"],
        "system design": [r"\b(architect|design.*system|system.*design|scalab|distributed|high.?level.*design)\b"],
        "distributed systems": [r"\b(distribut|scalable|fault.?tolerant|consensus|partition|eventual.*consist)\b"],
        "api design": [r"\b(api.*design|api.*specification|contract.*first|schema|openapi|swagger|rest.*design)\b"],
        "cqrs": [r"\b(cqrs|command.*query|read.*write.*separat)\b"],
        "event sourcing": [r"\b(event.*sourc|eventstore|event.*store|event.*log|append.?only)\b"],
        "backend development": [r"\b(backend|server.?side|api.*develop|rest.*api|backend.*engineer)\b"],
        "performance optimization": [r"\b(optimiz|performance.*tun|latency.*reduc|throughput|caching|index)\b"],
        "code quality": [r"\b(code.*quality|maintainab|clean.*code|refactor|code.*health|technical.*excellen)\b"],
        "scalability": [r"\b(scal|million|billion|throughput|capacity|load|horizontal.*scal|vertical.*scal)\b"],
        "fault tolerance": [r"\b(resilien|fault.?tolerant|high.?availability|failover|redundan|disaster.*recovery)\b"],
        "data modeling": [r"\b(data.*model|database.*design|schema.*design|data.*architect|entity.*relation)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # DELIVERY & QUALITY
        # ═══════════════════════════════════════════════════════════════════════════
        "agile": [r"\b(agile|scrum|sprint|kanban|iteration|velocity|standup|retro)\b"],
        "scrum": [r"\b(scrum|sprint.*planning|daily.*standup|sprint.*review|scrum.*master)\b"],
        "sprint planning": [r"\b(sprint.*planning|backlog.*groom|capacity.*plan|iteration.*plan)\b"],
        "quality engineering": [r"\b(test.*automat|test.*coverage|quality.*assurance|qa|tdd|bdd|unit.*test|integration.*test)\b"],
        "release management": [r"\b(release|deployment|production|version.*management|rollout|roll.*back)\b"],
        "incident management": [r"\b(incident|on.?call|alert|pager|mttr|mttd|production.*issue)\b"],
        "devops": [r"\b(devops|devsecops|sre|site.*reliability|infrastructure.*automat|platform.*engineer)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # DATABASES & DATA
        # ═══════════════════════════════════════════════════════════════════════════
        "mongodb": [r"\b(mongodb|mongo|nosql|document.*database|atlas)\b"],
        "postgresql": [r"\b(postgres|postgresql|sql.*database|rdbms|relational.*database)\b"],
        "mysql": [r"\b(mysql|mariadb|sql)\b"],
        "redis": [r"\b(redis|cache|in.?memory|key.?value)\b"],
        "rabbitmq": [r"\b(rabbitmq|amqp|message.*queue|message.*broker)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # LANGUAGES & FRAMEWORKS
        # ═══════════════════════════════════════════════════════════════════════════
        "typescript": [r"\b(typescript|ts)\b"],
        "javascript": [r"\b(javascript|js|ecmascript|es6|node)\b"],
        "python": [r"\b(python|python3|flask|django|fastapi)\b"],
        "node.js": [r"\b(node\.?js|nodejs|express|npm|yarn)\b"],
        "nestjs": [r"\b(nestjs|nest\.?js)\b"],
        "angular": [r"\b(angular|angularjs)\b"],
        "flask": [r"\b(flask)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # REAL-TIME & PROTOCOLS
        # ═══════════════════════════════════════════════════════════════════════════
        "webrtc": [r"\b(webrtc|peer.?to.?peer|video.*call|real.?time.*video|p2p.*video)\b"],
        "websocket": [r"\b(websocket|socket\.io|real.?time.*message)\b"],
        "rest api": [r"\b(rest|restful|rest.*api|http.*api|json.*api)\b"],
        "graphql": [r"\b(graphql|apollo|mutation|query.*language)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # COMPLIANCE & SECURITY
        # ═══════════════════════════════════════════════════════════════════════════
        "gdpr": [r"\b(gdpr|data.*privacy|privacy|data.*protection|consent.*management|tcf)\b"],
        "security": [r"\b(security|secure|authentication|authorization|oauth|jwt|encryption)\b"],

        # ═══════════════════════════════════════════════════════════════════════════
        # PROCESS & METHODOLOGY
        # ═══════════════════════════════════════════════════════════════════════════
        "event storming": [r"\b(event.*storm|domain.*discover|collaborative.*model|ddd.*workshop)\b"],
        "technical writing": [r"\b(technical.*documentation|software.*documentation|api.*documentation|document)\b"],
    }

    def _find_skill_evidence(
        self,
        skill: str,
        bullets: List[str],
        role_companies: List[str],
    ) -> Optional[SkillEvidence]:
        """
        Find evidence for a skill in the experience bullets.

        Uses multiple strategies:
        1. Direct mention of skill name
        2. Alias matching (e.g., "DDD" for "Domain-Driven Design")
        3. Pattern-based detection (e.g., "hired 5 engineers" for "Hiring & Interviewing")

        Args:
            skill: The skill to find evidence for
            bullets: Experience bullets to search
            role_companies: Company names for source tracking

        Returns:
            SkillEvidence if found, None otherwise
        """
        skill_lower = skill.lower()
        aliases = self._taxonomy.get_skill_aliases(skill)
        aliases_lower = [a.lower() for a in aliases]

        # Get pattern matchers for this skill
        patterns = self.SKILL_EVIDENCE_PATTERNS.get(skill_lower, [])
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

        evidence_bullets = []
        source_roles = []

        for i, bullet in enumerate(bullets):
            bullet_lower = bullet.lower()
            found = False

            # Strategy 1: Direct skill name match
            if skill_lower in bullet_lower:
                found = True

            # Strategy 2: Alias matching
            if not found:
                for alias in aliases_lower:
                    if alias in bullet_lower:
                        found = True
                        break

            # Strategy 3: Pattern-based detection
            if not found:
                for pattern in compiled_patterns:
                    if pattern.search(bullet):
                        found = True
                        break

            if found:
                evidence_bullets.append(bullet)
                if i < len(role_companies):
                    source_roles.append(role_companies[i])

        if not evidence_bullets:
            return None

        return SkillEvidence(
            skill=skill,
            evidence_bullets=evidence_bullets[:3],  # Limit to 3 examples
            source_roles=list(set(source_roles)),
            is_jd_keyword=False,  # Set by caller
        )


# ============================================================================
# V2 CORE COMPETENCY GENERATOR (Anti-Hallucination)
# ============================================================================
#
# This class implements the V2 header generation's core competencies component.
# Key differences from TaxonomyBasedSkillsGenerator:
# 1. Uses STATIC section names from taxonomy (not dynamic selection)
# 2. Returns Dict[str, List[str]] instead of SkillsSection objects
# 3. Provides full SkillsProvenance for anti-hallucination tracking
# 4. Designed for 4 fixed sections per role category
# ============================================================================


class CoreCompetencyGeneratorV2:
    """
    V2 Core Competency Generator - Algorithmic skills selection with static sections.

    This generator produces the CORE COMPETENCIES section for CV headers using
    a purely algorithmic approach (no LLM) with strict anti-hallucination guarantees:

    1. All skills MUST exist in candidate's whitelist
    2. Section names are STATIC (from taxonomy's static_competency_sections)
    3. JD keywords are used for PRIORITIZATION only, not ADDITION
    4. Full provenance tracking for every skill

    Usage:
        generator = CoreCompetencyGeneratorV2(
            role_category="engineering_manager",
            skill_whitelist={"hard_skills": [...], "soft_skills": [...]}
        )
        competencies, provenance = generator.generate(extracted_jd, annotations)
    """

    # Scoring weights for skill prioritization
    BASE_WEIGHT = 1.0
    JD_MATCH_BOOST = 2.0
    ANNOTATION_BOOST = 1.5
    COMPETENCY_ALIGNMENT_BONUS = 0.5

    # Configuration
    MIN_SKILLS_PER_SECTION = 4
    MAX_SKILLS_PER_SECTION = 10
    TARGET_JD_MATCH_RATIO = 0.5  # At least 50% of skills should match JD

    def __init__(
        self,
        role_category: str,
        skill_whitelist: Dict[str, List[str]],
        taxonomy: Optional[SkillsTaxonomy] = None,
    ):
        """
        Initialize the V2 Core Competency Generator.

        Args:
            role_category: Target role category (e.g., "engineering_manager")
            skill_whitelist: Candidate's verified skills {hard_skills: [...], soft_skills: [...]}
            taxonomy: Optional SkillsTaxonomy instance (loads default if not provided)
        """
        self._logger = get_logger(__name__)
        self._role_category = role_category
        self._skill_whitelist = skill_whitelist
        self._taxonomy = taxonomy or SkillsTaxonomy()

        # Build normalized whitelist for fast lookup
        self._whitelist_skills: Set[str] = set()
        self._whitelist_lower: Dict[str, str] = {}  # lower -> original

        for skill in skill_whitelist.get("hard_skills", []):
            self._whitelist_skills.add(skill)
            self._whitelist_lower[skill.lower()] = skill

        for skill in skill_whitelist.get("soft_skills", []):
            self._whitelist_skills.add(skill)
            self._whitelist_lower[skill.lower()] = skill

        # Load static sections for this role
        self._static_sections = self._load_static_sections()

        self._logger.info(
            f"CoreCompetencyGeneratorV2 initialized: role={role_category}, "
            f"{len(self._whitelist_skills)} whitelisted skills, "
            f"{len(self._static_sections)} static sections"
        )

    def _load_static_sections(self) -> List[Dict[str, str]]:
        """
        Load static section definitions from taxonomy.

        Returns:
            List of section dicts with 'name' and 'description'
        """
        role_taxonomy = self._taxonomy.get_role_taxonomy(self._role_category)
        taxonomy_data = self._taxonomy._taxonomy_data.get("target_roles", {})
        role_data = taxonomy_data.get(self._role_category, {})

        static_sections_data = role_data.get("static_competency_sections", {})

        sections = []
        for key in ["section_1", "section_2", "section_3", "section_4"]:
            section_data = static_sections_data.get(key, {})
            if section_data:
                sections.append({
                    "name": section_data.get("name", f"Section {key[-1]}"),
                    "description": section_data.get("description", ""),
                })

        # Fallback to dynamic sections if no static defined
        if not sections:
            self._logger.warning(
                f"No static_competency_sections for {self._role_category}, using dynamic sections"
            )
            for section in role_taxonomy.sections[:4]:
                sections.append({
                    "name": section.name,
                    "description": section.description,
                })

        return sections

    def generate(
        self,
        extracted_jd: Dict,
        annotations: Optional[Dict] = None,
    ) -> Tuple[Dict[str, List[str]], "SkillsProvenance"]:
        """
        Generate core competencies using algorithmic selection.

        Args:
            extracted_jd: Extracted JD data with keywords, pain_points, responsibilities
            annotations: Optional JD annotations with emphasis areas

        Returns:
            Tuple of:
            - Dict[str, List[str]]: section_name → list of skills
            - SkillsProvenance: Full traceability for anti-hallucination proof
        """
        from src.layer6_v2.types import SkillsProvenance

        # Extract JD keywords for prioritization
        jd_keywords = set()
        for key in ["priority_keywords", "top_keywords", "keywords", "technical_skills"]:
            for kw in extracted_jd.get(key, []):
                jd_keywords.add(kw.lower())

        # Extract annotation emphasis for additional boost
        annotation_keywords = set()
        if annotations:
            for key in ["core_strengths", "emphasis_areas", "must_haves"]:
                for item in annotations.get(key, []):
                    if isinstance(item, str):
                        annotation_keywords.add(item.lower())

        self._logger.debug(
            f"Generating competencies: {len(jd_keywords)} JD keywords, "
            f"{len(annotation_keywords)} annotation keywords"
        )

        # Step 1: Score all whitelist skills
        skill_scores = self._score_all_skills(jd_keywords, annotation_keywords)

        # Step 2: Assign skills to sections
        section_assignments = self._assign_skills_to_sections(skill_scores)

        # Step 3: Rank and select top skills per section
        final_sections = self._select_top_skills(section_assignments)

        # Step 4: Build provenance tracking
        provenance = self._build_provenance(
            final_sections, jd_keywords, annotation_keywords
        )

        return final_sections, provenance

    def _score_all_skills(
        self,
        jd_keywords: Set[str],
        annotation_keywords: Set[str],
    ) -> Dict[str, float]:
        """
        Score all whitelist skills based on JD and annotation relevance.

        Args:
            jd_keywords: Lowercased JD keywords
            annotation_keywords: Lowercased annotation emphasis keywords

        Returns:
            Dict mapping skill name → score
        """
        scores = {}

        for skill in self._whitelist_skills:
            skill_lower = skill.lower()

            # Base score for being in whitelist
            score = self.BASE_WEIGHT

            # JD keyword match boost
            if self._skill_matches_keywords(skill_lower, jd_keywords):
                score += self.JD_MATCH_BOOST

            # Annotation emphasis boost
            if self._skill_matches_keywords(skill_lower, annotation_keywords):
                score += self.ANNOTATION_BOOST

            scores[skill] = score

        return scores

    def _skill_matches_keywords(self, skill_lower: str, keywords: Set[str]) -> bool:
        """
        Check if a skill matches any keyword (with fuzzy matching).

        Args:
            skill_lower: Lowercased skill name
            keywords: Set of lowercased keywords

        Returns:
            True if skill matches any keyword
        """
        # Direct match
        if skill_lower in keywords:
            return True

        # Substring match (skill contains keyword or keyword contains skill)
        for kw in keywords:
            if skill_lower in kw or kw in skill_lower:
                return True

        # Check aliases
        aliases = self._taxonomy.get_skill_aliases(skill_lower)
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in keywords:
                return True
            for kw in keywords:
                if alias_lower in kw or kw in alias_lower:
                    return True

        return False

    def _assign_skills_to_sections(
        self,
        skill_scores: Dict[str, float],
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        Assign skills to the 4 static sections based on best fit.

        Uses the existing taxonomy sections to determine which skills
        belong in which category.

        Args:
            skill_scores: Dict of skill → score

        Returns:
            Dict of section_name → list of (skill, score) tuples
        """
        # Get the taxonomy sections for skill-to-section mapping
        role_taxonomy = self._taxonomy.get_role_taxonomy(self._role_category)

        # Build section → skills mapping from taxonomy
        section_skill_map: Dict[str, Set[str]] = {}
        for section in role_taxonomy.sections:
            section_skill_map[section.name.lower()] = {
                s.lower() for s in section.skills
            }

        # Assign skills to static sections
        assignments: Dict[str, List[Tuple[str, float]]] = {
            section["name"]: [] for section in self._static_sections
        }

        # Track assigned skills to avoid duplicates
        assigned_skills: Set[str] = set()

        # First pass: assign skills to their primary section
        for skill, score in skill_scores.items():
            skill_lower = skill.lower()

            # Find best matching section
            best_section = None
            best_match_score = 0

            for static_section in self._static_sections:
                section_name_lower = static_section["name"].lower()

                # Check taxonomy sections for this static section name
                for taxonomy_section_name, taxonomy_skills in section_skill_map.items():
                    if section_name_lower in taxonomy_section_name or taxonomy_section_name in section_name_lower:
                        if skill_lower in taxonomy_skills:
                            if score > best_match_score:
                                best_section = static_section["name"]
                                best_match_score = score

            if best_section and skill not in assigned_skills:
                assignments[best_section].append((skill, score))
                assigned_skills.add(skill)

        # Second pass: distribute unassigned high-score skills
        for skill, score in sorted(skill_scores.items(), key=lambda x: x[1], reverse=True):
            if skill in assigned_skills:
                continue

            # Add to section with fewest skills
            min_section = min(assignments.keys(), key=lambda s: len(assignments[s]))
            if len(assignments[min_section]) < self.MAX_SKILLS_PER_SECTION:
                assignments[min_section].append((skill, score))
                assigned_skills.add(skill)

        return assignments

    def _select_top_skills(
        self,
        section_assignments: Dict[str, List[Tuple[str, float]]],
    ) -> Dict[str, List[str]]:
        """
        Select top skills for each section, respecting min/max constraints.

        Args:
            section_assignments: Dict of section → (skill, score) list

        Returns:
            Dict of section_name → ordered skill list
        """
        final_sections = {}

        for section_name, skill_scores in section_assignments.items():
            # Sort by score descending
            sorted_skills = sorted(skill_scores, key=lambda x: x[1], reverse=True)

            # Select top N skills (within constraints)
            selected = [skill for skill, _ in sorted_skills[:self.MAX_SKILLS_PER_SECTION]]

            # Ensure minimum if we have enough skills
            if len(selected) < self.MIN_SKILLS_PER_SECTION and len(sorted_skills) >= self.MIN_SKILLS_PER_SECTION:
                selected = [skill for skill, _ in sorted_skills[:self.MIN_SKILLS_PER_SECTION]]

            final_sections[section_name] = selected

        return final_sections

    def _build_provenance(
        self,
        final_sections: Dict[str, List[str]],
        jd_keywords: Set[str],
        annotation_keywords: Set[str],
    ) -> "SkillsProvenance":
        """
        Build full provenance tracking for anti-hallucination proof.

        Args:
            final_sections: Final section → skills mapping
            jd_keywords: JD keywords used for matching
            annotation_keywords: Annotation keywords used

        Returns:
            SkillsProvenance with full traceability
        """
        from src.layer6_v2.types import SkillsProvenance

        # Track JD-matched vs whitelist-only skills
        jd_matched_skills = []
        whitelist_only_skills = []

        all_selected_skills = []
        for section_name, skills in final_sections.items():
            all_selected_skills.extend(skills)

            for skill in skills:
                skill_lower = skill.lower()
                if self._skill_matches_keywords(skill_lower, jd_keywords):
                    jd_matched_skills.append(skill)
                else:
                    whitelist_only_skills.append(skill)

        # Find JD skills we rejected (not in whitelist)
        rejected_jd_skills = []
        for kw in jd_keywords:
            # Check if this JD keyword was NOT in our whitelist
            matched_whitelist = False
            for skill in self._whitelist_skills:
                if self._skill_matches_keywords(kw, {skill.lower()}):
                    matched_whitelist = True
                    break
            if not matched_whitelist:
                # This JD skill was not in our whitelist - we rejected it
                rejected_jd_skills.append(kw)

        return SkillsProvenance(
            all_from_whitelist=True,  # Always true by construction
            whitelist_source="master_cv",
            total_skills_selected=len(all_selected_skills),
            jd_matched_skills=list(set(jd_matched_skills)),
            whitelist_only_skills=list(set(whitelist_only_skills)),
            rejected_jd_skills=list(set(rejected_jd_skills)),
            skills_by_section=final_sections,
        )

    def get_static_section_names(self) -> List[str]:
        """Get the static section names for this role category."""
        return [section["name"] for section in self._static_sections]


def create_core_competency_generator_v2(
    role_category: str,
    skill_whitelist: Dict[str, List[str]],
    taxonomy_path: Optional[Path] = None,
) -> CoreCompetencyGeneratorV2:
    """
    Factory function to create a V2 Core Competency Generator.

    Args:
        role_category: Target role category
        skill_whitelist: Candidate's verified skills
        taxonomy_path: Optional path to taxonomy file

    Returns:
        Configured CoreCompetencyGeneratorV2
    """
    taxonomy = SkillsTaxonomy(taxonomy_path)
    return CoreCompetencyGeneratorV2(
        role_category=role_category,
        skill_whitelist=skill_whitelist,
        taxonomy=taxonomy,
    )


def create_taxonomy_generator(
    skill_whitelist: Dict[str, List[str]],
    taxonomy_path: Optional[Path] = None,
    lax_mode: bool = True,
    annotation_context: Optional[HeaderGenerationContext] = None,
) -> TaxonomyBasedSkillsGenerator:
    """
    Factory function to create a TaxonomyBasedSkillsGenerator.

    Args:
        skill_whitelist: Candidate's skill whitelist
        taxonomy_path: Optional path to taxonomy file
        lax_mode: If True, generate more skills for pruning
        annotation_context: Phase 4.5 - HeaderGenerationContext with annotation priorities

    Returns:
        Configured TaxonomyBasedSkillsGenerator
    """
    taxonomy = SkillsTaxonomy(taxonomy_path)
    return TaxonomyBasedSkillsGenerator(
        taxonomy=taxonomy,
        skill_whitelist=skill_whitelist,
        lax_mode=lax_mode,
        annotation_context=annotation_context,
    )
