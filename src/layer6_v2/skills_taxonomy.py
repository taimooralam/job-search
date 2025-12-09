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

        # Extract JD keywords and responsibilities
        jd_keywords = extracted_jd.get("top_keywords", [])
        jd_technical = extracted_jd.get("technical_skills", [])
        jd_responsibilities = extracted_jd.get("responsibilities", [])
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
