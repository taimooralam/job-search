"""
Annotation Priors Management for Self-Correcting Suggestion System

Manages the priors document that stores:
- Sentence embeddings for semantic matching (batch updated)
- Skill priors for keyword matching (real-time updated)
- Statistics for tracking accuracy and rebuild needs

The priors document is a singleton (one per user) stored in MongoDB.
It's ~5-6MB containing embeddings for all historical annotations.

Usage:
    from src.services.annotation_priors import (
        load_priors,
        save_priors,
        rebuild_priors,
        should_rebuild_priors,
        capture_feedback,
    )

    # Load priors (creates empty if not exists)
    priors = load_priors()

    # Check if rebuild needed
    if should_rebuild_priors(priors):
        priors = rebuild_priors(priors)
        save_priors(priors)

    # Capture feedback from user edit
    priors = capture_feedback(annotation, action="save", priors=priors)
    save_priors(priors)
"""

import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# LEARNING CONFIGURATION
# ============================================================================
#
# These parameters control how the system learns from user feedback.
# They affect how quickly the system adapts to user preferences and
# how strongly it responds to deletions.
#
# To tune these values:
# - Monitor priors stats (accuracy, deleted_full vs deleted_soft)
# - If system over-corrects (avoids skills user actually wants): reduce penalties
# - If system is slow to learn: increase adjustment rates
# - If suggestions are unstable: increase MIN_OBSERVATIONS_FOR_STABILITY
# ============================================================================

# --- Deletion Learning Penalties ---
# These multipliers reduce confidence when user deletes an annotation.
# Applied to all dimension confidences (relevance, passion, identity, requirement).

# Soft penalty multiplier for uncertain deletions (0.0-1.0)
# Applied when skill might just be noise (e.g., user has the skill but
# it wasn't relevant in this context).
# - Higher (0.9): Gentle confidence reduction, slow adaptation
# - Lower (0.5): Aggressive reduction, fast adaptation
# - Default: 0.8 provides conservative learning
SOFT_PENALTY_MULTIPLIER = 0.8

# Full penalty multiplier for confirmed skill gaps (0.0-1.0)
# Applied when user clearly doesn't have the skill (deletion in
# requirements/qualifications section for non-owned skill).
# Also marks the skill with "avoid" flag.
# - Higher (0.5): Moderate penalty, can still suggest later
# - Lower (0.2): Strong penalty, skill nearly blocked
# - Default: 0.3 strongly discourages future suggestions
FULL_PENALTY_MULTIPLIER = 0.3

# --- Confidence Adjustment Rates ---
# These control how confidence changes on correct/wrong predictions.

# Confidence boost for correct predictions (additive, 0.0-0.2)
# Added to confidence when user accepts annotation unchanged.
# - Higher: Faster confidence growth
# - Lower: More conservative, requires more validation
# - Default: 0.05 requires ~10 correct predictions to reach high confidence
CORRECT_PREDICTION_BOOST = 0.05

# Maximum confidence value (cap for correct prediction boosts)
MAX_CONFIDENCE = 0.99

# Confidence decay for wrong predictions (multiplicative, 0.0-1.0)
# Multiplied with confidence when user edits the predicted value.
# - Higher (0.9): Slow decay, tolerates some variance
# - Lower (0.5): Fast decay, quickly adopts new patterns
# - Default: 0.7 provides moderate adaptation speed
WRONG_PREDICTION_DECAY = 0.7

# Minimum confidence floor (prevents confidence from going to zero)
MIN_CONFIDENCE = 0.2

# --- Value Adoption Thresholds ---
# These control when the system switches to a new predicted value
# after observing different values from the user.

# Confidence threshold for adopting new value (0.0-1.0)
# If confidence drops below this after wrong predictions,
# adopt the user's value as the new prediction.
# - Higher: Requires more evidence before switching
# - Lower: Switches more eagerly
# - Default: 0.4 switches after ~2-3 wrong predictions
VALUE_ADOPTION_THRESHOLD = 0.4

# Minimum observations before value is considered stable
# If we have fewer observations than this, always adopt new value on correction.
# - Higher: Requires more history before trusting current value
# - Lower: Sticks with current value earlier
# - Default: 3 observations before value is "stable"
MIN_OBSERVATIONS_FOR_STABILITY = 3

# Neutral confidence value for newly adopted values
NEUTRAL_CONFIDENCE = 0.5


# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
#
# Controls caching behavior for performance optimization.
# ============================================================================

# Owned skills cache TTL in seconds
# How long to cache the list of skills user "owns" (from master CV + priors).
# - Higher: Better performance, may miss recent changes
# - Lower: More responsive to changes, more DB queries
# - Default: 300 (5 minutes) balances freshness vs performance
OWNED_SKILLS_CACHE_TTL = 300

# Ownership confidence threshold (0.0-1.0)
# Minimum prior relevance confidence to consider a skill "owned".
# Used for deletion response classification (skill gap vs noise).
# - Higher: More conservative, requires strong evidence of ownership
# - Lower: More lenient, considers weakly-associated skills as owned
# - Default: 0.7 requires moderate-to-high confidence
OWNERSHIP_CONFIDENCE_THRESHOLD = 0.7


# ============================================================================
# REBUILD CONFIGURATION
# ============================================================================
#
# Controls when the sentence embedding index should be rebuilt.
# Rebuilding is expensive (~15-30s for 3000 annotations) but necessary
# to incorporate new annotations into semantic matching.
# ============================================================================

# Hours threshold for staleness check
# Rebuild if index is older than this AND has new annotations.
REBUILD_AGE_HOURS = 24

# Minimum new annotations to trigger age-based rebuild
# Only rebuild old indexes if this many new annotations exist.
REBUILD_MIN_NEW_ANNOTATIONS = 20

# Maximum new annotations before forced rebuild
# Rebuild regardless of age if this many new annotations exist.
REBUILD_MAX_NEW_ANNOTATIONS = 100


# ============================================================================
# EMBEDDING MODEL CONFIGURATION
# ============================================================================

# Sentence transformer model for semantic matching
# all-MiniLM-L6-v2 is fast and good for sentence similarity.
# Changing this requires rebuilding the entire index.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Embedding dimension (must match the model above)
EMBEDDING_DIM = 384

# Batch size for computing embeddings during rebuild
EMBEDDING_BATCH_SIZE = 64


# ============================================================================
# PRIORS DOCUMENT CONFIGURATION
# ============================================================================

# Priors document ID (singleton per user)
PRIORS_DOC_ID = "user_annotation_priors"


# ============================================================================
# SECTION CATEGORIES
# ============================================================================
#
# Categorize JD sections for deletion learning behavior.
# ============================================================================

# Sections where deletion should NOT trigger learning
# These sections often contain contextual info, not skill requirements.
NO_LEARNING_SECTIONS = frozenset({
    "about_company", "benefits", "nice_to_have", "about_role", "company_culture"
})

# Sections where deletion should trigger full learning for skill gaps
# These sections contain hard requirements where deletion indicates
# user doesn't have the skill.
SKILL_REQUIREMENT_SECTIONS = frozenset({
    "requirements", "qualifications"
})


# ============================================================================
# DELETION RESPONSE CLASSIFICATION
# ============================================================================


class DeletionResponse(Enum):
    """Context-aware response to annotation deletion."""
    NO_LEARNING = "no_learning"
    SOFT_PENALTY = "soft_penalty"
    FULL_LEARNING = "full_learning"


# Module-level cache for owned skills
_owned_skills_cache: Optional[Tuple[Set[str], float]] = None


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================


class DimensionPrior(TypedDict):
    """Prior for a single dimension (relevance, passion, identity, requirement)."""
    value: Optional[str]  # Current best value (e.g., "core_strength")
    confidence: float     # 0.0 to 1.0
    n: int                # Number of observations


class SkillPrior(TypedDict):
    """Prior for a single skill/keyword."""
    relevance: DimensionPrior
    passion: DimensionPrior
    identity: DimensionPrior
    requirement: DimensionPrior
    avoid: bool  # If True, never suggest this skill


class AnnotationMetadata(TypedDict):
    """Metadata for a single annotation in the sentence index."""
    relevance: Optional[str]
    requirement: Optional[str]
    passion: Optional[str]
    identity: Optional[str]
    job_id: str  # Source job for traceability


class SentenceIndex(TypedDict):
    """Pre-computed sentence embeddings for semantic matching."""
    embeddings: List[List[float]]  # Shape: (N, 384)
    texts: List[str]               # Original annotation texts
    metadata: List[AnnotationMetadata]  # Annotation values per text
    built_at: str                  # ISO timestamp
    model: str                     # Model name used
    count: int                     # Number of entries


class LearnedMapping(TypedDict):
    """A learned phrase-to-skill mapping."""
    phrase: str
    skill: str
    confidence: float
    learned_from_job: str


class PriorsStats(TypedDict):
    """Statistics for tracking priors health."""
    total_annotations_at_build: int
    annotations_since_build: int
    total_suggestions_made: int
    accepted_unchanged: int
    edited: int
    deleted: int
    last_rebuild: Optional[str]


class PriorsDocument(TypedDict):
    """Full priors document schema."""
    _id: str
    version: int
    sentence_index: SentenceIndex
    skill_priors: Dict[str, SkillPrior]
    learned_mappings: List[LearnedMapping]
    stats: PriorsStats
    updated_at: str


# ============================================================================
# LOAD / SAVE FUNCTIONS
# ============================================================================


def _empty_priors() -> PriorsDocument:
    """Create an empty priors document."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id": PRIORS_DOC_ID,
        "version": 1,
        "sentence_index": {
            "embeddings": [],
            "texts": [],
            "metadata": [],
            "built_at": now,
            "model": EMBEDDING_MODEL,
            "count": 0,
        },
        "skill_priors": {},
        "learned_mappings": [],
        "stats": {
            "total_annotations_at_build": 0,
            "annotations_since_build": 0,
            "total_suggestions_made": 0,
            "accepted_unchanged": 0,
            "edited": 0,
            "deleted": 0,
            "last_rebuild": None,
        },
        "updated_at": now,
    }


def load_priors() -> PriorsDocument:
    """
    Load the priors document from MongoDB.

    Creates an empty priors document if none exists.
    Uses repository pattern for future dual-write support.

    Returns:
        PriorsDocument dict
    """
    try:
        from src.common.repositories import get_priors_repository

        repo = get_priors_repository()
        doc = repo.find_one({"_id": PRIORS_DOC_ID})

        if doc:
            logger.debug(f"Loaded priors: {doc.get('stats', {}).get('total_annotations_at_build', 0)} annotations indexed")
            return doc  # type: ignore

        # Create empty priors if not exists
        logger.info("No priors document found, creating empty one")
        empty = _empty_priors()
        repo.insert_one(empty)
        return empty

    except ValueError as e:
        # MONGODB_URI not configured - return empty priors for dev
        logger.debug(f"MongoDB not configured, using empty priors: {e}")
        return _empty_priors()
    except Exception as e:
        logger.warning(f"Failed to load priors from MongoDB: {e}")
        return _empty_priors()


def save_priors(priors: PriorsDocument) -> bool:
    """
    Save the priors document to MongoDB.

    Uses repository pattern for future dual-write support.

    Args:
        priors: PriorsDocument to save

    Returns:
        True if successful, False otherwise
    """
    try:
        from src.common.repositories import get_priors_repository

        repo = get_priors_repository()
        priors["updated_at"] = datetime.now(timezone.utc).isoformat()

        result = repo.replace_one(
            {"_id": PRIORS_DOC_ID},
            priors,
            upsert=True
        )

        logger.debug(f"Saved priors: matched={result.matched_count}, modified={result.modified_count}")
        return True

    except ValueError as e:
        # MONGODB_URI not configured - skip save in dev
        logger.debug(f"MongoDB not configured, skipping priors save: {e}")
        return True  # Return True since this is expected in dev
    except Exception as e:
        logger.error(f"Failed to save priors: {e}")
        return False


# ============================================================================
# REBUILD FUNCTIONS
# ============================================================================


def should_rebuild_priors(priors: PriorsDocument) -> bool:
    """
    Determine if the sentence_index needs rebuilding.

    Rebuild conditions:
    - No index yet
    - More than 24 hours old AND >20 new annotations
    - More than 100 new annotations regardless of time

    Args:
        priors: Current priors document

    Returns:
        True if rebuild recommended
    """
    sentence_index = priors.get("sentence_index", {})
    stats = priors.get("stats", {})

    # No index yet - definitely rebuild
    if not sentence_index.get("embeddings"):
        logger.info("Rebuild needed: no embeddings exist")
        return True

    built_at = sentence_index.get("built_at")
    if not built_at:
        logger.info("Rebuild needed: no built_at timestamp")
        return True

    # Calculate staleness
    try:
        built_time = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
        hours_since_build = (datetime.now(timezone.utc) - built_time).total_seconds() / 3600
    except (ValueError, TypeError):
        logger.info("Rebuild needed: invalid built_at timestamp")
        return True

    new_annotations = stats.get("annotations_since_build", 0)

    # Rebuild conditions
    if hours_since_build > REBUILD_AGE_HOURS and new_annotations > REBUILD_MIN_NEW_ANNOTATIONS:
        logger.info(f"Rebuild needed: {hours_since_build:.1f}h old with {new_annotations} new annotations")
        return True

    if new_annotations > REBUILD_MAX_NEW_ANNOTATIONS:
        logger.info(f"Rebuild needed: {new_annotations} new annotations")
        return True

    return False


def _load_all_annotations() -> List[Dict[str, Any]]:
    """
    Load all annotations from all jobs in MongoDB.

    Returns:
        List of annotation dicts with text and metadata
    """
    from src.common.repositories import get_job_repository

    repo = get_job_repository()
    annotations = []

    # Find all jobs with annotations
    jobs = repo.find(
        filter={"jd_annotations.annotations": {"$exists": True, "$ne": []}},
        projection={"_id": 1, "jd_annotations.annotations": 1}
    )

    for job in jobs:
        job_id = str(job.get("_id", ""))
        jd_annotations = job.get("jd_annotations", {})

        for ann in jd_annotations.get("annotations", []):
            text = ann.get("target", {}).get("text", "")

            # Skip very short texts
            if not text or len(text) < 10:
                continue

            annotations.append({
                "text": text,
                "relevance": ann.get("relevance"),
                "requirement": ann.get("requirement_type"),
                "passion": ann.get("passion"),
                "identity": ann.get("identity"),
                "job_id": job_id,
            })

    logger.info(f"Loaded {len(annotations)} annotations from {len(jobs)} jobs")
    return annotations


def _compute_embeddings(texts: List[str]) -> np.ndarray:
    """
    Compute sentence embeddings for a list of texts.

    Uses sentence-transformers with all-MiniLM-L6-v2 model.
    First call downloads the model (~80MB), subsequent calls use cache.

    Args:
        texts: List of text strings to embed

    Returns:
        numpy array of shape (len(texts), 384)
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
        raise ImportError("sentence-transformers required for rebuild. Install with: pip install sentence-transformers")

    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    logger.info(f"Computing embeddings for {len(texts)} texts...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=EMBEDDING_BATCH_SIZE)

    return embeddings


def _recompute_skill_priors(annotations: List[Dict[str, Any]]) -> Dict[str, SkillPrior]:
    """
    Recompute skill_priors from all annotations.

    Extracts keywords from annotation texts and aggregates their
    annotation values into priors.

    Args:
        annotations: List of annotation dicts

    Returns:
        Dict mapping skill name to SkillPrior
    """
    from collections import defaultdict

    # Aggregate values per skill
    skill_aggregates: Dict[str, Dict[str, List[str]]] = defaultdict(
        lambda: {"relevance": [], "passion": [], "identity": [], "requirement": []}
    )

    # Common skills to look for (could be expanded)
    skill_keywords = _get_skill_keywords()

    for ann in annotations:
        text_lower = ann["text"].lower()

        # Find skills mentioned in this annotation
        for skill in skill_keywords:
            if skill.lower() in text_lower:
                if ann.get("relevance"):
                    skill_aggregates[skill.lower()]["relevance"].append(ann["relevance"])
                if ann.get("passion"):
                    skill_aggregates[skill.lower()]["passion"].append(ann["passion"])
                if ann.get("identity"):
                    skill_aggregates[skill.lower()]["identity"].append(ann["identity"])
                if ann.get("requirement"):
                    skill_aggregates[skill.lower()]["requirement"].append(ann["requirement"])

    # Convert aggregates to priors
    skill_priors: Dict[str, SkillPrior] = {}

    for skill, dims in skill_aggregates.items():
        skill_priors[skill] = {
            "relevance": _aggregate_dimension(dims["relevance"]),
            "passion": _aggregate_dimension(dims["passion"]),
            "identity": _aggregate_dimension(dims["identity"]),
            "requirement": _aggregate_dimension(dims["requirement"]),
            "avoid": False,
        }

    logger.info(f"Computed priors for {len(skill_priors)} skills")
    return skill_priors


def _get_skill_keywords() -> List[str]:
    """
    Get list of skill keywords to track in priors.

    Sources from master CV taxonomy jd_signals.
    """
    try:
        from src.common.master_cv_store import get_taxonomy

        taxonomy = get_taxonomy()
        if not taxonomy:
            return _default_skill_keywords()

        # Extract all jd_signals from all sections of all roles
        skills = set()
        target_roles = taxonomy.get("target_roles", {})

        for role_data in target_roles.values():
            for section in role_data.get("sections", []):
                for signal in section.get("jd_signals", []):
                    # Only add signals with 3+ characters to avoid single-letter matches
                    if len(signal) >= 3:
                        skills.add(signal.lower())

        # Also add skill aliases (with minimum length filter)
        for aliases in taxonomy.get("skill_aliases", {}).values():
            for alias in aliases:
                if len(alias) >= 3:
                    skills.add(alias.lower())

        logger.debug(f"Loaded {len(skills)} skill keywords from taxonomy")
        return list(skills)

    except Exception as e:
        logger.warning(f"Failed to load taxonomy, using defaults: {e}")
        return _default_skill_keywords()


def _default_skill_keywords() -> List[str]:
    """Default skill keywords if taxonomy not available."""
    return [
        "python", "typescript", "javascript", "aws", "docker", "kubernetes",
        "microservices", "api", "cloud", "devops", "agile", "scrum",
        "leadership", "mentoring", "architecture", "ci/cd", "terraform",
        "react", "node.js", "mongodb", "postgresql", "redis", "kafka",
        "machine learning", "ai", "data", "security", "performance",
        "team", "management", "stakeholder", "cross-functional",
    ]


def _aggregate_dimension(values: List[str]) -> DimensionPrior:
    """
    Aggregate a list of dimension values into a DimensionPrior.

    Uses majority voting with confidence based on agreement.
    """
    if not values:
        return {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0}

    # Count occurrences
    from collections import Counter
    counts = Counter(values)
    most_common_value, most_common_count = counts.most_common(1)[0]

    # Confidence = agreement ratio
    confidence = most_common_count / len(values)

    return {
        "value": most_common_value,
        "confidence": round(confidence, 3),
        "n": len(values),
    }


def rebuild_priors(priors: PriorsDocument) -> PriorsDocument:
    """
    Rebuild the sentence_index by re-embedding all historical annotations.

    This is a batch operation that takes ~15-30 seconds for 3000 annotations.
    Should be called when should_rebuild_priors() returns True.

    Args:
        priors: Current priors document (will be mutated)

    Returns:
        Updated priors document with new sentence_index
    """
    logger.info("Starting priors rebuild...")
    start_time = datetime.now()

    # 1. Load all annotations
    all_annotations = _load_all_annotations()

    if not all_annotations:
        logger.warning("No annotations found to build index from")
        return priors

    # 2. Compute embeddings
    texts = [a["text"] for a in all_annotations]
    embeddings = _compute_embeddings(texts)

    # 3. Update sentence_index
    now = datetime.now(timezone.utc).isoformat()
    priors["sentence_index"] = {
        "embeddings": embeddings.tolist(),
        "texts": texts,
        "metadata": [
            {
                "relevance": a["relevance"],
                "requirement": a["requirement"],
                "passion": a["passion"],
                "identity": a["identity"],
                "job_id": a["job_id"],
            }
            for a in all_annotations
        ],
        "built_at": now,
        "model": EMBEDDING_MODEL,
        "count": len(all_annotations),
    }

    # 4. Recompute skill_priors
    priors["skill_priors"] = _recompute_skill_priors(all_annotations)

    # 5. Update stats
    priors["stats"]["total_annotations_at_build"] = len(all_annotations)
    priors["stats"]["annotations_since_build"] = 0
    priors["stats"]["last_rebuild"] = now

    # 6. Increment version
    priors["version"] = priors.get("version", 0) + 1

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Priors rebuild complete: {len(all_annotations)} annotations indexed in {duration:.1f}s")

    return priors


# ============================================================================
# DELETION RESPONSE FUNCTIONS
# ============================================================================


def determine_deletion_response(
    skill: str,
    section: Optional[str],
    owned_skills: Set[str],
) -> Tuple[DeletionResponse, str]:
    """
    Determine appropriate learning response for a deleted annotation.

    Args:
        skill: The skill/keyword from the deleted annotation
        section: The JD section the annotation was in
        owned_skills: Set of skills the user owns (lowercase)

    Returns:
        Tuple of (response_level, reason)
    """
    skill_lower = skill.lower() if skill else ""
    section_lower = (section or "").lower().strip()
    user_owns = skill_lower in owned_skills if skill_lower else False

    # Rule 1: Non-skill sections -> NO_LEARNING
    if section_lower in NO_LEARNING_SECTIONS:
        return (DeletionResponse.NO_LEARNING, f"non_skill_section:{section_lower}")

    # Rule 2: Requirements/Qualifications
    if section_lower in SKILL_REQUIREMENT_SECTIONS:
        if not user_owns and skill_lower:
            return (DeletionResponse.FULL_LEARNING, "skill_gap")
        else:
            return (DeletionResponse.SOFT_PENALTY, "has_skill_noise")

    # Rule 3: Responsibilities
    if section_lower == "responsibilities":
        if user_owns:
            return (DeletionResponse.NO_LEARNING, "responsibility_has_skill")
        else:
            return (DeletionResponse.SOFT_PENALTY, "responsibility_uncertain")

    # Default: Conservative - soft penalty
    return (DeletionResponse.SOFT_PENALTY, f"unknown_section:{section_lower}")


def get_owned_skills(priors: Dict[str, Any]) -> Set[str]:
    """
    Load all skills the user 'owns' for ownership checking.

    Sources:
    1. Master CV: hard_skills, soft_skills, keywords
    2. High-confidence priors (>0.7 relevance confidence)

    Args:
        priors: The priors document

    Returns:
        Set of owned skill names (lowercase)
    """
    global _owned_skills_cache

    # Check cache
    if _owned_skills_cache:
        cached_skills, cached_time = _owned_skills_cache
        if time.time() - cached_time < OWNED_SKILLS_CACHE_TTL:
            return cached_skills

    owned: Set[str] = set()

    # Source 1: Master CV
    try:
        from src.common.master_cv_store import get_metadata
        metadata = get_metadata()
        if metadata:
            for role in metadata.get("roles", []):
                owned.update(s.lower() for s in role.get("hard_skills", []))
                owned.update(s.lower() for s in role.get("soft_skills", []))
                owned.update(s.lower() for s in role.get("keywords", []))
    except Exception as e:
        logger.warning(f"Failed to load master CV for owned skills: {e}")

    # Source 2: High-confidence priors
    for skill, data in priors.get("skill_priors", {}).items():
        relevance_conf = data.get("relevance", {}).get("confidence", 0)
        if relevance_conf >= OWNERSHIP_CONFIDENCE_THRESHOLD and not data.get("avoid"):
            owned.add(skill.lower())

    # Update cache
    _owned_skills_cache = (owned, time.time())
    logger.debug(f"Loaded {len(owned)} owned skills")

    return owned


# ============================================================================
# FEEDBACK FUNCTIONS
# ============================================================================


def capture_feedback(
    annotation: Dict[str, Any],
    action: str,  # "save" | "delete"
    priors: PriorsDocument,
) -> PriorsDocument:
    """
    Capture feedback from user edits to improve priors.

    Called when user saves or deletes an auto-generated annotation.
    Updates skill_priors in real-time based on user's corrections.

    Args:
        annotation: The annotation dict (with original_values if auto-generated)
        action: "save" or "delete"
        priors: Current priors document (will be mutated)

    Returns:
        Updated priors document
    """
    # Only process auto-generated annotations
    if annotation.get("source") != "auto_generated":
        return priors

    # Skip if feedback already captured (avoid double-counting)
    if annotation.get("feedback_captured") and action == "save":
        return priors

    original = annotation.get("original_values", {})
    match_method = original.get("match_method")

    # Extract skill/keyword that was matched
    if match_method == "sentence_similarity":
        skill = _extract_primary_skill(original.get("matched_text", ""))
    elif match_method == "keyword_prior":
        skill = original.get("matched_keyword")
    else:
        skill = _extract_primary_skill(annotation.get("target", {}).get("text", ""))

    if not skill:
        logger.debug("No skill extracted from annotation, skipping feedback")
        return priors

    skill_lower = skill.lower()

    # Initialize skill prior if new
    if skill_lower not in priors["skill_priors"]:
        priors["skill_priors"][skill_lower] = {
            "relevance": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "passion": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "identity": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "requirement": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "avoid": False,
        }

    prior = priors["skill_priors"][skill_lower]

    if action == "delete":
        # === CONTEXT-AWARE DELETION LEARNING ===
        # Get section from annotation target
        section = annotation.get("target", {}).get("section")

        # Load owned skills
        owned_skills = get_owned_skills(priors)

        # Determine response based on context
        response, reason = determine_deletion_response(skill_lower, section, owned_skills)

        if response == DeletionResponse.NO_LEARNING:
            priors["stats"]["deleted_no_learning"] = priors["stats"].get("deleted_no_learning", 0) + 1
            logger.info(f"Deletion: NO_LEARNING for '{skill_lower}' ({reason})")

        elif response == DeletionResponse.SOFT_PENALTY:
            for dim in ["relevance", "passion", "identity", "requirement"]:
                if dim in prior:
                    prior[dim]["confidence"] *= SOFT_PENALTY_MULTIPLIER
            priors["stats"]["deleted_soft"] = priors["stats"].get("deleted_soft", 0) + 1
            logger.info(f"Deletion: SOFT_PENALTY for '{skill_lower}' ({reason})")

        elif response == DeletionResponse.FULL_LEARNING:
            prior["avoid"] = True
            for dim in ["relevance", "passion", "identity", "requirement"]:
                if dim in prior:
                    prior[dim]["confidence"] *= FULL_PENALTY_MULTIPLIER
            priors["stats"]["deleted_full"] = priors["stats"].get("deleted_full", 0) + 1
            logger.info(f"Deletion: FULL_LEARNING for '{skill_lower}' ({reason})")

        priors["stats"]["deleted"] = priors["stats"].get("deleted", 0) + 1

    elif action == "save":
        # === LEARN FROM EDITS ===
        any_change = False

        for dim in ["relevance", "passion", "identity"]:
            original_val = original.get(dim)
            # Handle requirement_type vs requirement naming
            final_val = annotation.get(dim) or annotation.get(f"{dim}_type")

            if not original_val or not final_val:
                continue

            prior[dim]["n"] += 1

            if original_val == final_val:
                # Correct prediction - increase confidence
                prior[dim]["confidence"] = min(MAX_CONFIDENCE, prior[dim]["confidence"] + CORRECT_PREDICTION_BOOST)
            else:
                # Wrong prediction - decrease confidence, maybe change value
                any_change = True
                prior[dim]["confidence"] = max(MIN_CONFIDENCE, prior[dim]["confidence"] * WRONG_PREDICTION_DECAY)

                # If confidence drops below threshold, adopt new value
                if prior[dim]["confidence"] < VALUE_ADOPTION_THRESHOLD or prior[dim]["n"] < MIN_OBSERVATIONS_FOR_STABILITY:
                    prior[dim]["value"] = final_val
                    prior[dim]["confidence"] = NEUTRAL_CONFIDENCE  # Reset to neutral

        # Update stats
        if any_change:
            priors["stats"]["edited"] = priors["stats"].get("edited", 0) + 1
            logger.debug(f"Feedback: user edited annotation for '{skill_lower}'")
        else:
            priors["stats"]["accepted_unchanged"] = priors["stats"].get("accepted_unchanged", 0) + 1
            logger.debug(f"Feedback: user accepted annotation for '{skill_lower}'")

    # Increment annotations since build (for rebuild trigger)
    priors["stats"]["annotations_since_build"] = priors["stats"].get("annotations_since_build", 0) + 1

    priors["updated_at"] = datetime.now(timezone.utc).isoformat()

    return priors


def _extract_primary_skill(text: str) -> Optional[str]:
    """
    Extract the primary skill/keyword from a text.

    Simple implementation: finds first matching skill keyword.
    """
    if not text:
        return None

    text_lower = text.lower()
    skill_keywords = _get_skill_keywords()

    for skill in skill_keywords:
        if skill.lower() in text_lower:
            return skill

    return None


def capture_manual_annotation(
    annotation: Dict[str, Any],
    priors: PriorsDocument,
) -> PriorsDocument:
    """
    Capture positive learning signal from manually created annotations.

    Manual annotations represent explicit user interest - the user took the time
    to manually highlight and annotate text, indicating it's relevant to them.

    Args:
        annotation: The manual annotation dict with target.text and values
        priors: Current priors document (will be mutated)

    Returns:
        Updated priors document
    """
    # Extract skill from the annotated text
    target_text = annotation.get("target", {}).get("text", "")
    skill = _extract_primary_skill(target_text)

    if not skill:
        logger.debug(f"No skill extracted from manual annotation: {target_text[:50]}...")
        # Still count it in stats
        priors["stats"]["manual_annotations"] = priors["stats"].get("manual_annotations", 0) + 1
        return priors

    skill_lower = skill.lower()

    # Initialize skill prior if new
    if skill_lower not in priors["skill_priors"]:
        priors["skill_priors"][skill_lower] = {
            "relevance": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "passion": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "identity": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "requirement": {"value": None, "confidence": NEUTRAL_CONFIDENCE, "n": 0},
            "avoid": False,
        }

    prior = priors["skill_priors"][skill_lower]

    # Clear avoid flag if user manually annotated this skill
    if prior.get("avoid"):
        prior["avoid"] = False
        logger.info(f"Manual annotation cleared 'avoid' flag for '{skill_lower}'")

    # Boost confidence for dimensions that match user's values
    # Manual annotation = strong positive signal
    MANUAL_BOOST = 0.15  # Strong boost for explicit user action

    for dim in ["relevance", "passion", "identity"]:
        user_value = annotation.get(dim)
        if user_value:
            prior[dim]["n"] += 1

            # If prior has no value yet, adopt user's value
            if prior[dim]["value"] is None:
                prior[dim]["value"] = user_value
                prior[dim]["confidence"] = NEUTRAL_CONFIDENCE + MANUAL_BOOST

            # If prior matches user's value, boost confidence
            elif prior[dim]["value"] == user_value:
                prior[dim]["confidence"] = min(MAX_CONFIDENCE, prior[dim]["confidence"] + MANUAL_BOOST)

            # If prior differs from user's value, reduce confidence and maybe adopt
            else:
                prior[dim]["confidence"] = max(MIN_CONFIDENCE, prior[dim]["confidence"] * 0.9)
                if prior[dim]["confidence"] < VALUE_ADOPTION_THRESHOLD:
                    prior[dim]["value"] = user_value
                    prior[dim]["confidence"] = NEUTRAL_CONFIDENCE

    # Handle requirement_type
    req_type = annotation.get("requirement_type")
    if req_type:
        prior["requirement"]["n"] += 1
        if prior["requirement"]["value"] is None:
            prior["requirement"]["value"] = req_type
            prior["requirement"]["confidence"] = NEUTRAL_CONFIDENCE + MANUAL_BOOST
        elif prior["requirement"]["value"] == req_type:
            prior["requirement"]["confidence"] = min(MAX_CONFIDENCE, prior["requirement"]["confidence"] + MANUAL_BOOST)

    # Update stats
    priors["stats"]["manual_annotations"] = priors["stats"].get("manual_annotations", 0) + 1
    priors["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"Manual annotation captured for '{skill_lower}': relevance={annotation.get('relevance')}")

    return priors


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_priors_stats(priors: PriorsDocument) -> Dict[str, Any]:
    """
    Get summary statistics about the priors.

    Returns:
        Dict with accuracy, coverage, and health metrics
    """
    stats = priors.get("stats", {})
    sentence_index = priors.get("sentence_index", {})

    total_suggestions = stats.get("total_suggestions_made", 0)
    accepted = stats.get("accepted_unchanged", 0)
    edited = stats.get("edited", 0)
    deleted = stats.get("deleted", 0)

    # Calculate accuracy (unchanged / total)
    total_feedback = accepted + edited + deleted
    accuracy = accepted / total_feedback if total_feedback > 0 else 0.0

    return {
        "accuracy": round(accuracy, 3),
        "total_suggestions": total_suggestions,
        "accepted_unchanged": accepted,
        "edited": edited,
        "deleted": deleted,
        "annotations_indexed": sentence_index.get("count", 0),
        "skills_tracked": len(priors.get("skill_priors", {})),
        "needs_rebuild": should_rebuild_priors(priors),
        "last_rebuild": stats.get("last_rebuild"),
    }
