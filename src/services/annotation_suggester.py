"""
Annotation Suggester for Self-Correcting Suggestion System

Core logic for:
- Determining if a JD item should be annotated (selective generation)
- Finding the best matching historical annotation (sentence embeddings)
- Generating annotations for a job's structured JD

Uses master CV taxonomy for skill matching and historical priors
for semantic similarity matching.

Usage:
    from src.services.annotation_suggester import generate_annotations_for_job

    result = generate_annotations_for_job(job_id)
    # result = {
    #     "success": True,
    #     "created": 12,
    #     "skipped": 8,
    #     "annotations": [...]
    # }
"""

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Thread-safe singleton for embedding model
# Prevents race conditions when multiple runners load the model simultaneously
_embedding_model = None
_embedding_model_lock = threading.Lock()

from .annotation_priors import (
    PriorsDocument,
    load_priors,
    save_priors,
    should_rebuild_priors,
    rebuild_priors,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)


# ============================================================================
# MATCHING CONFIGURATION
# ============================================================================
#
# These thresholds control how aggressively the system suggests annotations.
# Higher values = more strict matching = fewer but higher-quality suggestions.
# Lower values = more lenient matching = more suggestions but may include noise.
#
# To tune these values:
# - Monitor the priors stats (accepted_unchanged vs edited vs deleted)
# - If many suggestions are deleted: increase thresholds
# - If too few suggestions are made: decrease thresholds
# - Target ~80% acceptance rate for good user experience
# ============================================================================

# Sentence embedding similarity threshold (0.0-1.0)
# Controls semantic matching against historical annotations.
# - Higher (0.90+): Only very similar sentences match, fewer suggestions
# - Lower (0.75-0.80): More lenient matching, more suggestions
# - Recommended range: 0.80-0.90
# - Default: 0.85 balances precision vs recall
SIMILARITY_THRESHOLD = 0.85

# Keyword prior confidence threshold for fallback matching (0.0-1.0)
# Only uses keyword priors with confidence above this value.
# - Higher: Only well-established priors are used
# - Lower: Uses priors with less historical evidence
# - Recommended range: 0.5-0.7
# - Default: 0.6 requires moderate confidence from past annotations
KEYWORD_CONFIDENCE_THRESHOLD = 0.6

# Confidence discount for keyword-based matches (0.0-1.0)
# Applied to keyword prior confidence when generating suggestions.
# Keyword matches are less precise than sentence similarity, so we discount.
# - Higher: Trust keyword priors more
# - Lower: Be more conservative with keyword-based suggestions
# - Default: 0.8 applies 20% discount to keyword confidence
KEYWORD_CONFIDENCE_DISCOUNT = 0.8

# Minimum prior relevance confidence to trigger generation (0.0-1.0)
# For learned priors (skills not in master CV), only suggest if
# the prior has accumulated enough confidence.
# - Higher: Requires more evidence before suggesting learned skills
# - Lower: Suggests learned skills with less evidence
# - Default: 0.5 requires weak-to-moderate confidence
LEARNED_PRIOR_RELEVANCE_THRESHOLD = 0.5

# Minimum text length for annotation generation
# Very short texts are usually not meaningful requirements.
# - Default: 10 characters filters out noise
MIN_TEXT_LENGTH = 10

# Minimum word overlap for requirement type inference (0.0-1.0)
# When matching JD items to extracted qualifications/nice-to-haves,
# require this proportion of words to match.
# - Higher: More exact matching required
# - Lower: Fuzzy matching allowed
# - Default: 0.5 requires half the words to match
WORD_OVERLAP_THRESHOLD = 0.5

# Maximum keywords to suggest per annotation
# Limits ATS keyword suggestions from extracted_jd.top_keywords.
# - Default: 3 provides focused keyword guidance
MAX_SUGGESTED_KEYWORDS = 3

# Sections to skip during annotation generation (not skill-related)
SKIP_ANNOTATION_SECTIONS = frozenset({
    "about_company",
    "benefits",
    "about_role",
    "company_culture",
})


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class MatchResult:
    """Result of finding a match for a JD item."""
    relevance: str
    requirement: str
    passion: str
    identity: str
    confidence: float
    method: str  # "sentence_similarity" | "keyword_prior"
    matched_text: Optional[str] = None
    matched_keyword: Optional[str] = None
    matched_score: Optional[float] = None


@dataclass
class MatchContext:
    """Context about why a JD item was selected for annotation."""
    type: str  # "jd_signal" | "hard_skill" | "soft_skill" | "skill_alias" | "prior"
    match: str  # The matched keyword/signal
    source: Optional[str] = None  # "master_cv" | "priors" | "taxonomy"
    section: Optional[str] = None  # Section name for jd_signals


# ============================================================================
# MASTER CV LOADING
# ============================================================================


def _load_master_cv_data() -> Dict[str, Any]:
    """
    Load master CV data (taxonomy + metadata) for matching.

    Returns dict with:
    - jd_signals: Dict[section_name, List[signal]]
    - skill_aliases: Dict[canonical, List[alias]]
    - hard_skills: Set[skill]
    - soft_skills: Set[skill]
    - keywords: Set[keyword]
    """
    try:
        from src.common.master_cv_store import get_taxonomy, get_metadata

        result = {
            "jd_signals": {},
            "skill_aliases": {},
            "hard_skills": set(),
            "soft_skills": set(),
            "keywords": set(),
        }

        # Load taxonomy for jd_signals and skill_aliases
        taxonomy = get_taxonomy()
        if taxonomy:
            # Extract jd_signals from all roles (use engineering_manager as default)
            target_roles = taxonomy.get("target_roles", {})
            for role_data in target_roles.values():
                for section in role_data.get("sections", []):
                    section_name = section.get("name", "Unknown")
                    signals = section.get("jd_signals", [])
                    if section_name not in result["jd_signals"]:
                        result["jd_signals"][section_name] = []
                    result["jd_signals"][section_name].extend(signals)

            # Extract skill_aliases
            result["skill_aliases"] = taxonomy.get("skill_aliases", {})

        # Load metadata for hard_skills, soft_skills, keywords
        metadata = get_metadata()
        if metadata:
            for role in metadata.get("roles", []):
                result["hard_skills"].update(role.get("hard_skills", []))
                result["soft_skills"].update(role.get("soft_skills", []))
                result["keywords"].update(role.get("keywords", []))

        logger.debug(
            f"Loaded master CV: {len(result['hard_skills'])} hard skills, "
            f"{len(result['soft_skills'])} soft skills, "
            f"{sum(len(s) for s in result['jd_signals'].values())} jd_signals"
        )
        return result

    except Exception as e:
        logger.warning(f"Failed to load master CV data: {e}")
        return {
            "jd_signals": {},
            "skill_aliases": {},
            "hard_skills": set(),
            "soft_skills": set(),
            "keywords": set(),
        }


# ============================================================================
# SHOULD GENERATE (Selective Generation)
# ============================================================================


def should_generate_annotation(
    jd_item: str,
    master_cv: Dict[str, Any],
    priors: PriorsDocument,
) -> Tuple[bool, Optional[MatchContext]]:
    """
    Determine if we should generate an annotation for this JD item.

    Only generates if item matches user's profile:
    - JD signals from taxonomy
    - Hard skills from role metadata
    - Soft skills from role metadata
    - Skill aliases (fuzzy matching)
    - Learned priors (extension to CV)

    Args:
        jd_item: Text of the JD item to evaluate
        master_cv: Master CV data from _load_master_cv_data()
        priors: Current priors document

    Returns:
        (should_generate, match_context) tuple
    """
    jd_lower = jd_item.lower()
    skill_priors = priors.get("skill_priors", {})

    # === CHECK 1: JD Signals from Taxonomy ===
    for section_name, signals in master_cv.get("jd_signals", {}).items():
        for signal in signals:
            if signal.lower() in jd_lower:
                # Check if user marked this as "avoid"
                if skill_priors.get(signal.lower(), {}).get("avoid"):
                    continue
                return (True, MatchContext(
                    type="jd_signal",
                    match=signal,
                    source="taxonomy",
                    section=section_name,
                ))

    # === CHECK 2: Hard Skills from Role Metadata ===
    for skill in master_cv.get("hard_skills", set()):
        if skill.lower() in jd_lower:
            # Check if user marked this as "avoid"
            if skill_priors.get(skill.lower(), {}).get("avoid"):
                continue
            return (True, MatchContext(
                type="hard_skill",
                match=skill,
                source="master_cv",
            ))

    # === CHECK 3: Soft Skills from Role Metadata ===
    for skill in master_cv.get("soft_skills", set()):
        if skill.lower() in jd_lower:
            # Check if user marked this as "avoid"
            if skill_priors.get(skill.lower(), {}).get("avoid"):
                continue
            return (True, MatchContext(
                type="soft_skill",
                match=skill,
                source="master_cv",
            ))

    # === CHECK 4: Skill Aliases (Fuzzy Matching) ===
    for canonical, aliases in master_cv.get("skill_aliases", {}).items():
        for alias in aliases:
            if alias.lower() in jd_lower:
                # Check if user marked this as "avoid"
                if skill_priors.get(canonical.lower(), {}).get("avoid"):
                    continue
                return (True, MatchContext(
                    type="skill_alias",
                    match=alias,
                    source="taxonomy",
                ))

    # === CHECK 5: Learned Priors (Extension to CV) ===
    for skill, data in skill_priors.items():
        if skill in jd_lower and not data.get("avoid"):
            relevance_conf = data.get("relevance", {}).get("confidence", 0)
            if relevance_conf > LEARNED_PRIOR_RELEVANCE_THRESHOLD:
                return (True, MatchContext(
                    type="prior",
                    match=skill,
                    source="priors",
                ))

    # No match - don't generate
    return (False, None)


# ============================================================================
# REQUIREMENT TYPE INFERENCE
# ============================================================================


def _get_section_default_requirement(section_type: str) -> str:
    """Section-based default requirement_type."""
    section_defaults = {
        "responsibilities": "must_have",
        "requirements": "must_have",
        "qualifications": "must_have",
        "nice_to_have": "nice_to_have",
        "technical_skills": "must_have",
        "experience": "must_have",
        "education": "nice_to_have",
        "benefits": "nice_to_have",
        "other": "neutral",
    }
    return section_defaults.get(section_type, "neutral")


def infer_requirement_type(
    jd_item: str,
    section_type: str,
    extracted_jd: Optional[Dict[str, Any]],
) -> str:
    """
    Infer requirement_type from extracted_jd lists and section context.

    Priority:
    1. Match in extracted_jd.qualifications -> "must_have"
    2. Match in extracted_jd.nice_to_haves -> "nice_to_have"
    3. Section-based defaults
    """
    if not extracted_jd:
        return _get_section_default_requirement(section_type)

    jd_lower = jd_item.lower()
    jd_words = set(jd_lower.split())

    # Check qualifications list (word overlap above threshold = match)
    for qual in extracted_jd.get("qualifications") or []:
        qual_words = set(qual.lower().split())
        if qual_words and len(jd_words & qual_words) / len(qual_words) > WORD_OVERLAP_THRESHOLD:
            return "must_have"

    # Check nice_to_haves list
    for nice in extracted_jd.get("nice_to_haves") or []:
        nice_words = set(nice.lower().split())
        if nice_words and len(jd_words & nice_words) / len(nice_words) > WORD_OVERLAP_THRESHOLD:
            return "nice_to_have"

    return _get_section_default_requirement(section_type)


# ============================================================================
# FIND BEST MATCH (Semantic Matching)
# ============================================================================


def find_best_match(
    jd_item: str,
    priors: PriorsDocument,
    embedding_model: Any = None,
) -> Optional[MatchResult]:
    """
    Find the best matching historical annotation for this JD item.

    Uses sentence embeddings as primary, keyword priors as fallback.

    Args:
        jd_item: Text of the JD item to match
        priors: Current priors document with sentence_index
        embedding_model: Optional pre-loaded SentenceTransformer model

    Returns:
        MatchResult if found, None otherwise
    """
    # === Layer 1: Sentence Similarity ===
    sentence_index = priors.get("sentence_index", {})
    embeddings_list = sentence_index.get("embeddings", [])

    if embeddings_list:
        try:
            # Load model if not provided (uses thread-safe singleton)
            if embedding_model is None:
                embedding_model = get_embedding_model()

            # Compute embedding for new JD item
            jd_embedding = embedding_model.encode(jd_item)

            # Compare against all historical embeddings
            embeddings = np.array(embeddings_list)
            similarities = _cosine_similarity(jd_embedding, embeddings)

            # Find best match
            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])

            if best_score > SIMILARITY_THRESHOLD:
                metadata = sentence_index.get("metadata", [])[best_idx]
                matched_text = sentence_index.get("texts", [])[best_idx]

                return MatchResult(
                    relevance=metadata.get("relevance") or "relevant",
                    requirement=metadata.get("requirement") or "neutral",
                    passion=metadata.get("passion") or "neutral",
                    identity=metadata.get("identity") or "peripheral",
                    confidence=best_score,
                    method="sentence_similarity",
                    matched_text=matched_text,
                    matched_score=best_score,
                )

        except Exception as e:
            logger.warning(f"Sentence similarity matching failed: {e}")

    # === Layer 2: Keyword Prior Matching (Fallback) ===
    keywords = _extract_keywords(jd_item)
    skill_priors = priors.get("skill_priors", {})

    for keyword in keywords:
        skill_prior = skill_priors.get(keyword.lower())
        if skill_prior and not skill_prior.get("avoid"):
            relevance_data = skill_prior.get("relevance", {})
            if relevance_data.get("confidence", 0) > KEYWORD_CONFIDENCE_THRESHOLD:
                return MatchResult(
                    relevance=relevance_data.get("value") or "relevant",
                    requirement=skill_prior.get("requirement", {}).get("value") or "neutral",
                    passion=skill_prior.get("passion", {}).get("value") or "neutral",
                    identity=skill_prior.get("identity", {}).get("value") or "peripheral",
                    confidence=relevance_data.get("confidence", 0.6) * KEYWORD_CONFIDENCE_DISCOUNT,
                    method="keyword_prior",
                    matched_keyword=keyword,
                )

    # === Layer 3: No match - use defaults ===
    return None


def _cosine_similarity(vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between a vector and each row of a matrix.

    Args:
        vec: Query vector (384,)
        matrix: Embedding matrix (N, 384)

    Returns:
        Similarities array (N,)
    """
    # Normalize
    vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
    matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    matrix_normalized = matrix / matrix_norms

    # Dot product
    similarities = np.dot(matrix_normalized, vec_norm)
    return similarities


def _extract_keywords(text: str) -> List[str]:
    """
    Extract keywords from text for prior matching.

    Simple implementation: lowercase words longer than 3 chars.
    """
    import re
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    # Deduplicate while preserving order
    seen = set()
    keywords = []
    for word in words:
        if word not in seen:
            seen.add(word)
            keywords.append(word)
    return keywords


def suggest_keywords_for_item(
    jd_item: str,
    extracted_jd: Optional[Dict[str, Any]],
    max_keywords: int = MAX_SUGGESTED_KEYWORDS,
) -> List[str]:
    """
    Suggest ATS keywords from extracted_jd.top_keywords for a JD item.

    Returns keywords that appear in the item text, prioritized by position
    in the top_keywords list (earlier = more important).
    """
    if not extracted_jd:
        return []

    jd_lower = jd_item.lower()
    top_keywords = extracted_jd.get("top_keywords") or []

    matched = []
    for keyword in top_keywords:
        if keyword.lower() in jd_lower:
            matched.append(keyword)
            if len(matched) >= max_keywords:
                break

    return matched


# ============================================================================
# GENERATE ANNOTATIONS
# ============================================================================


def generate_annotations_for_job(
    job_id: str,
    extracted_jd: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate annotations for a job's structured JD.

    This is the main entry point called by the API endpoint.

    Uses 4 sources for matching:
    1. Master CV (skills I have)
    2. Structured JD (where to annotate)
    3. Extracted JD (what to look for, requirement type inference)
    4. Priors (patterns I prefer)

    Args:
        job_id: MongoDB ObjectId string of the job
        extracted_jd: Optional pre-loaded extracted_jd, loaded from job if None

    Returns:
        Dict with success, created, skipped, annotations, error
    """
    from bson import ObjectId
    from src.common.repositories import get_job_repository

    logger.info(f"Generating annotations for job {job_id}")

    try:
        # 1. Load job
        repo = get_job_repository()
        try:
            job_oid = ObjectId(job_id)
        except Exception:
            job_oid = job_id  # Fallback for invalid ObjectId

        job = repo.find_one({"_id": job_oid})
        if not job:
            return {"success": False, "error": "Job not found"}

        # 2. Get structured JD sections
        # The JD structuring saves to 'processed_jd_sections' as a list of section objects
        jd_annotations = job.get("jd_annotations", {})
        processed_sections = jd_annotations.get("processed_jd_sections", [])

        if not processed_sections:
            return {"success": False, "error": "No structured JD found. Please structure the JD first."}

        # Load extracted_jd if not provided (Source 3)
        if extracted_jd is None:
            extracted_jd = job.get("extracted_jd") or {}
        elif not isinstance(extracted_jd, dict):
            logger.warning(f"Invalid extracted_jd type: {type(extracted_jd)}, using job document")
            extracted_jd = job.get("extracted_jd") or {}

        # 3. Load priors (rebuild if needed)
        priors = load_priors()
        if should_rebuild_priors(priors):
            logger.info("Rebuilding priors before generation...")
            priors = rebuild_priors(priors)
            save_priors(priors)

        # 4. Load master CV data
        master_cv = _load_master_cv_data()

        # 5. Load embedding model once (uses thread-safe singleton)
        embedding_model = None
        if priors.get("sentence_index", {}).get("embeddings"):
            try:
                embedding_model = get_embedding_model()
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")

        # 6. Get existing annotations to avoid duplicates
        existing_annotations = jd_annotations.get("annotations", [])
        existing_texts = {
            ann.get("target", {}).get("text", "").lower()
            for ann in existing_annotations
        }

        # 7. Generate annotations for each section
        # Process sections directly from processed_jd_sections to preserve headers
        new_annotations = []
        skipped = 0
        skipped_sections = 0

        for section in processed_sections:
            section_type = section.get("section_type", "other")
            section_header = section.get("header", "")  # Original header from JD
            items = section.get("items") or []

            # Skip non-skill sections (about_company, benefits, etc.)
            if section_type in SKIP_ANNOTATION_SECTIONS:
                logger.debug(f"Skipping section '{section_type}' (non-skill section)")
                skipped_sections += 1
                skipped += len(items)
                continue

            for item in items:
                item_text = item.get("text", "") if isinstance(item, dict) else str(item)

                if not item_text or len(item_text) < MIN_TEXT_LENGTH:
                    skipped += 1
                    continue

                # Skip if already annotated
                if item_text.lower() in existing_texts:
                    skipped += 1
                    continue

                # Check if should generate (uses master_cv + priors)
                should_gen, match_ctx = should_generate_annotation(item_text, master_cv, priors)
                if not should_gen:
                    skipped += 1
                    continue

                # Find best match for annotation values (uses priors/MiniLM)
                match_result = find_best_match(item_text, priors, embedding_model)

                # Infer requirement_type from extracted_jd (Source 3)
                inferred_requirement = infer_requirement_type(
                    item_text, section_type, extracted_jd
                )

                # Suggest ATS keywords from extracted_jd (Source 3)
                suggested_keywords = suggest_keywords_for_item(item_text, extracted_jd)

                # Create annotation with section_header and extracted_jd for dimension inference
                annotation = _create_annotation(
                    item_text,
                    section_type,
                    match_result,
                    match_ctx,
                    item if isinstance(item, dict) else None,
                    section_header=section_header,
                    extracted_jd=extracted_jd,
                    master_cv=master_cv,
                )

                # Override requirement_type if inferred (when no match_result)
                if match_result is None and inferred_requirement != "neutral":
                    annotation["requirement_type"] = inferred_requirement
                    annotation["original_values"]["requirement_type"] = inferred_requirement

                # Add suggested keywords if any
                if suggested_keywords:
                    annotation["suggested_keywords"] = suggested_keywords

                new_annotations.append(annotation)
                existing_texts.add(item_text.lower())

        logger.debug(f"Skipped {skipped_sections} non-skill sections")

        # 8. Save annotations to job
        if new_annotations:
            all_annotations = existing_annotations + new_annotations

            result = repo.update_one(
                {"_id": job_oid},
                {"$set": {"jd_annotations.annotations": all_annotations}}
            )

            if result.matched_count == 0:
                return {"success": False, "error": "Failed to save annotations"}

        # 9. Update priors stats
        priors["stats"]["total_suggestions_made"] = (
            priors["stats"].get("total_suggestions_made", 0) + len(new_annotations)
        )
        save_priors(priors)

        logger.info(f"Generated {len(new_annotations)} annotations, skipped {skipped}")

        return {
            "success": True,
            "created": len(new_annotations),
            "skipped": skipped,
            "annotations": [
                {
                    "id": ann["id"],
                    "target": ann["target"],
                    "relevance": ann["relevance"],
                    "confidence": ann.get("original_values", {}).get("confidence", 0),
                    "match_method": ann.get("original_values", {}).get("match_method", "default"),
                }
                for ann in new_annotations
            ],
        }

    except Exception as e:
        logger.error(f"Failed to generate annotations: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _infer_dimensions_from_extracted_jd(
    item_text: str,
    section: str,
    extracted_jd: Dict[str, Any],
    master_cv: Dict[str, Any],
    match_ctx: Optional[MatchContext],
) -> Dict[str, str]:
    """
    Infer persona-ready dimensions (relevance/identity/passion) from extracted_jd context.

    This enhancement ensures auto-generated annotations have dimensions that
    enable persona synthesis, even without historical priors.

    Logic:
    - RELEVANCE: If user has the skill (hard_skill/jd_signal match) → core_strength
    - IDENTITY: If skill matches extracted_jd technical_skills → strong_identity
    - PASSION: If nice_to_have section with user skill → enjoy

    Args:
        item_text: The JD requirement text
        section: Section type (e.g., "requirements", "nice_to_have")
        extracted_jd: Extracted JD intelligence with role_category, technical_skills, etc.
        master_cv: User's CV data with hard_skills, soft_skills
        match_ctx: Context about why this item was selected

    Returns:
        Dict with dimension overrides (relevance, identity, passion) - only includes
        dimensions that should be upgraded from defaults
    """
    result = {}

    if not extracted_jd:
        return result

    # Get user's skills from master CV (lowercase for matching)
    user_hard_skills = {s.lower() for s in master_cv.get("hard_skills", set())}
    user_soft_skills = {s.lower() for s in master_cv.get("soft_skills", set())}
    user_all_skills = user_hard_skills | user_soft_skills

    # Get extracted_jd data
    tech_skills = [s.lower() for s in extracted_jd.get("technical_skills", [])]
    responsibilities = [r.lower() for r in extracted_jd.get("responsibilities", [])]
    qualifications = [q.lower() for q in extracted_jd.get("qualifications", [])]

    item_lower = item_text.lower()

    # 1. RELEVANCE (strength) - boost to core_strength if user has the skill
    if match_ctx:
        if match_ctx.type in ("hard_skill", "jd_signal"):
            # User has this core skill → core_strength
            result["relevance"] = "core_strength"
        elif match_ctx.type == "soft_skill":
            # User has this soft skill → extremely_relevant
            result["relevance"] = "extremely_relevant"
        elif match_ctx.type == "skill_alias":
            # User has aliased skill → core_strength
            result["relevance"] = "core_strength"

    # 2. IDENTITY - set strong_identity if skill matches extracted_jd tech skills + user has it
    for skill in tech_skills:
        if skill in item_lower:
            # Check if user has this skill
            if skill in user_all_skills or any(skill in us for us in user_all_skills):
                result["identity"] = "strong_identity"
                break

    # Also check qualifications for identity
    if "identity" not in result:
        for qual in qualifications:
            # If the qualification mentions a skill the user has
            for user_skill in user_hard_skills:
                if user_skill in qual and user_skill in item_lower:
                    result["identity"] = "strong_identity"
                    break

    # 3. PASSION - nice_to_have items that user has → enjoy
    if section in ("nice_to_have", "nice_to_haves") and match_ctx:
        result["passion"] = "enjoy"
    elif section == "benefits" and match_ctx:
        # Benefits the user would appreciate
        result["passion"] = "enjoy"

    return result


def _create_annotation(
    text: str,
    section: str,
    match_result: Optional[MatchResult],
    match_ctx: Optional[MatchContext],
    item_dict: Optional[Dict[str, Any]],
    section_header: Optional[str] = None,
    extracted_jd: Optional[Dict[str, Any]] = None,
    master_cv: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create an annotation dict with original values for feedback tracking.

    Args:
        text: The JD item text
        section: Section type (e.g., "requirements", "responsibilities")
        match_result: Result from find_best_match if any
        match_ctx: Context about why this was selected for annotation
        item_dict: Original item dict with position info
        section_header: Optional original section header from JD
        extracted_jd: Optional extracted JD intelligence for dimension inference
        master_cv: Optional master CV data for skill matching
    """
    now = datetime.now(timezone.utc).isoformat()
    ann_id = f"ann_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"

    # Default values if no match
    if match_result:
        relevance = match_result.relevance
        requirement_type = match_result.requirement
        passion = match_result.passion
        identity = match_result.identity
        confidence = match_result.confidence
        method = match_result.method
        matched_text = match_result.matched_text
        matched_keyword = match_result.matched_keyword
        matched_score = match_result.matched_score
    else:
        # Defaults based on section
        section_defaults = {
            "responsibilities": {"relevance": "relevant", "requirement": "must_have"},
            "requirements": {"relevance": "relevant", "requirement": "must_have"},
            "qualifications": {"relevance": "relevant", "requirement": "must_have"},
            "nice_to_have": {"relevance": "relevant", "requirement": "nice_to_have"},
            "benefits": {"relevance": "tangential", "requirement": "nice_to_have"},
        }
        defaults = section_defaults.get(section, {"relevance": "relevant", "requirement": "neutral"})
        relevance = defaults["relevance"]
        requirement_type = defaults["requirement"]
        passion = "neutral"
        identity = "peripheral"
        confidence = 0.5
        method = "default"
        matched_text = None
        matched_keyword = match_ctx.match if match_ctx else None
        matched_score = None

    # Enhance dimensions using extracted_jd context (makes annotations persona-ready)
    # This ensures auto-generated annotations have meaningful identity/passion/strength
    # even without historical priors
    if extracted_jd and master_cv:
        dimension_overrides = _infer_dimensions_from_extracted_jd(
            text, section, extracted_jd, master_cv, match_ctx
        )
        if dimension_overrides:
            relevance = dimension_overrides.get("relevance", relevance)
            identity = dimension_overrides.get("identity", identity)
            passion = dimension_overrides.get("passion", passion)
            # Update method to indicate enhancement
            if method == "default":
                method = "extracted_jd_enhanced"

    # Build target
    target = {
        "text": text,
        "original_text": text,
        "section": section,
    }
    # Add section_header if provided
    if section_header:
        target["section_header"] = section_header

    # Add position info if available
    if item_dict:
        if "char_start" in item_dict:
            target["char_start"] = item_dict["char_start"]
        if "char_end" in item_dict:
            target["char_end"] = item_dict["char_end"]

    return {
        "id": ann_id,
        "target": target,
        "relevance": relevance,
        "requirement_type": requirement_type,
        "passion": passion,
        "identity": identity,
        "matching_skill": match_ctx.match if match_ctx else None,
        "original_values": {
            "relevance": relevance,
            "requirement_type": requirement_type,
            "passion": passion,
            "identity": identity,
            "confidence": confidence,
            "match_method": method,
            "matched_text": matched_text,
            "matched_keyword": matched_keyword,
            "matched_score": matched_score,
            "match_context": {
                "type": match_ctx.type if match_ctx else None,
                "match": match_ctx.match if match_ctx else None,
                "source": match_ctx.source if match_ctx else None,
            } if match_ctx else None,
        },
        "source": "auto_generated",
        "feedback_captured": False,
        "created_at": now,
        "updated_at": now,
    }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_embedding_model():
    """
    Get the sentence transformer model (thread-safe singleton).

    Uses double-checked locking to ensure only one instance is created,
    even when multiple runners attempt to load simultaneously.

    This fixes the PyTorch 2.x "Cannot copy out of meta tensor; no data!"
    error that occurs when multiple processes race to load the model.

    Returns:
        SentenceTransformer model instance (cached globally)
    """
    global _embedding_model

    # Fast path: model already loaded
    if _embedding_model is not None:
        return _embedding_model

    # Slow path: acquire lock and load model
    with _embedding_model_lock:
        # Double-check after acquiring lock (another thread may have loaded it)
        if _embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
                # Explicitly set device='cpu' to avoid PyTorch 2.x meta tensor issues
                _embedding_model = SentenceTransformer(EMBEDDING_MODEL, device='cpu')
                logger.info("Embedding model loaded successfully")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )

    return _embedding_model
