"""
Master-CV MongoDB Store - CRUD operations with version history.

Provides MongoDB storage for master-cv data with:
- Version tracking for audit trail
- Rollback capability to previous versions
- File fallback for local development
- Real-time sync to pipeline runner

Collections:
- master_cv_metadata: Candidate info and role metadata (single canonical document)
- master_cv_taxonomy: Skills taxonomy per target role (single canonical document)
- master_cv_roles: Individual role markdown files with parsed achievements

Design decisions:
- Single canonical document per collection (except roles which has one per role)
- Version history stored in separate collection for space efficiency
- File fallback enables local development without MongoDB
- Timestamps use ISO 8601 format for consistency
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database

from .database import db as database_client

logger = logging.getLogger(__name__)

# Default paths for file fallback
DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "master-cv"
METADATA_FILE = "role_metadata.json"
TAXONOMY_FILE = "role_skills_taxonomy.json"
ROLES_DIR = "roles"


class MasterCVVersion(TypedDict):
    """Version history entry for audit trail."""
    version: int
    timestamp: str  # ISO 8601
    updated_by: str  # "user" | "system" | "migration"
    change_summary: str
    previous_data: Dict[str, Any]  # Snapshot of previous version


class MetadataDocument(TypedDict):
    """Schema for master_cv_metadata collection."""
    _id: str  # "canonical"
    version: int
    updated_at: str
    updated_by: str
    candidate: Dict[str, Any]
    roles: List[Dict[str, Any]]


class TaxonomyDocument(TypedDict):
    """Schema for master_cv_taxonomy collection."""
    _id: str  # "canonical"
    version: int
    updated_at: str
    updated_by: str
    target_roles: Dict[str, Any]
    skill_aliases: Dict[str, List[str]]
    default_fallback_role: str


class RoleDocument(TypedDict):
    """Schema for master_cv_roles collection."""
    _id: str  # role_id (e.g., "01_seven_one_entertainment")
    role_id: str
    version: int
    updated_at: str
    updated_by: str
    markdown_content: str
    parsed: Optional[Dict[str, Any]]  # Parsed achievements, skills, variants


class MasterCVStore:
    """
    MongoDB CRUD operations for master-cv data with version history.

    Supports:
    - Reading/writing metadata, taxonomy, and role documents
    - Version history for rollback
    - File fallback for local development (read-only)

    Usage:
        store = MasterCVStore(use_mongodb=True)
        metadata = store.get_metadata()
        store.update_metadata(new_data, updated_by="user", change_summary="Added keyword")
    """

    CANONICAL_ID = "canonical"

    def __init__(self, use_mongodb: bool = True, data_dir: Optional[Path] = None):
        """
        Initialize the master-cv store.

        Args:
            use_mongodb: If True, use MongoDB; if False, use file fallback (read-only)
            data_dir: Override default data directory for file fallback
        """
        self.use_mongodb = use_mongodb
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self._db: Optional[Database] = None

        if use_mongodb:
            try:
                self._db = database_client.db
                self._ensure_collections()
            except Exception as e:
                logger.warning(f"MongoDB unavailable, falling back to files: {e}")
                self.use_mongodb = False

    def _ensure_collections(self) -> None:
        """Create collections and indexes if they don't exist."""
        if self._db is None:
            return

        # Create indexes for version history collection
        history_collection = self._db["master_cv_history"]
        history_collection.create_index(
            [("collection", ASCENDING), ("doc_id", ASCENDING), ("version", DESCENDING)],
            name="collection_doc_version"
        )
        history_collection.create_index(
            [("timestamp", DESCENDING)],
            name="timestamp_desc"
        )

        # Create index for roles collection
        roles_collection = self._db["master_cv_roles"]
        roles_collection.create_index(
            [("role_id", ASCENDING)],
            name="role_id",
            unique=True
        )

        logger.info("Master-CV collections and indexes ensured")

    # ==========================================================================
    # METADATA OPERATIONS
    # ==========================================================================

    @property
    def _metadata_collection(self) -> Collection:
        """Get the metadata collection."""
        if self._db is None:
            raise RuntimeError("MongoDB not available")
        return self._db["master_cv_metadata"]

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Get the canonical metadata document.

        Returns:
            Metadata dict or None if not found
        """
        if self.use_mongodb and self._db is not None:
            doc = self._metadata_collection.find_one({"_id": self.CANONICAL_ID})
            if doc:
                doc.pop("_id", None)
                return doc
            # Fall through to file if not in MongoDB

        # File fallback
        metadata_path = self.data_dir / METADATA_FILE
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                data = json.load(f)
                return {
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": "file",
                    **data
                }
        return None

    def update_metadata(
        self,
        data: Dict[str, Any],
        updated_by: str = "user",
        change_summary: str = ""
    ) -> bool:
        """
        Update the metadata document with version history.

        Args:
            data: New metadata (candidate and roles fields)
            updated_by: Who made the change ("user", "system", "migration")
            change_summary: Description of the change

        Returns:
            True if successful
        """
        if not self.use_mongodb or not self._db:
            logger.warning("Cannot update metadata: MongoDB not available")
            return False

        # Get current version for history
        current = self._metadata_collection.find_one({"_id": self.CANONICAL_ID})
        current_version = current.get("version", 0) if current else 0

        # Save history
        if current:
            self._save_history("master_cv_metadata", self.CANONICAL_ID, current)

        # Prepare new document
        new_doc = {
            "_id": self.CANONICAL_ID,
            "version": current_version + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
            "candidate": data.get("candidate", {}),
            "roles": data.get("roles", [])
        }

        # Upsert
        self._metadata_collection.replace_one(
            {"_id": self.CANONICAL_ID},
            new_doc,
            upsert=True
        )

        logger.info(f"Updated metadata to version {new_doc['version']}: {change_summary}")
        return True

    def update_metadata_role(
        self,
        role_id: str,
        role_data: Dict[str, Any],
        updated_by: str = "user",
        change_summary: str = ""
    ) -> bool:
        """
        Update a specific role within metadata.

        Args:
            role_id: The role ID to update
            role_data: New role data
            updated_by: Who made the change
            change_summary: Description of the change

        Returns:
            True if successful
        """
        if not self.use_mongodb or not self._db:
            logger.warning("Cannot update metadata role: MongoDB not available")
            return False

        current = self.get_metadata()
        if not current:
            logger.error("No metadata found to update")
            return False

        # Find and update the role
        roles = current.get("roles", [])
        role_updated = False
        for i, role in enumerate(roles):
            if role.get("id") == role_id:
                roles[i] = {**role, **role_data}
                role_updated = True
                break

        if not role_updated:
            # Add new role
            roles.append(role_data)

        current["roles"] = roles
        return self.update_metadata(current, updated_by, change_summary)

    # ==========================================================================
    # TAXONOMY OPERATIONS
    # ==========================================================================

    @property
    def _taxonomy_collection(self) -> Collection:
        """Get the taxonomy collection."""
        if self._db is None:
            raise RuntimeError("MongoDB not available")
        return self._db["master_cv_taxonomy"]

    def get_taxonomy(self) -> Optional[Dict[str, Any]]:
        """
        Get the canonical taxonomy document.

        Returns:
            Taxonomy dict or None if not found
        """
        if self.use_mongodb and self._db is not None:
            doc = self._taxonomy_collection.find_one({"_id": self.CANONICAL_ID})
            if doc:
                doc.pop("_id", None)
                return doc

        # File fallback
        taxonomy_path = self.data_dir / TAXONOMY_FILE
        if taxonomy_path.exists():
            with open(taxonomy_path, "r") as f:
                data = json.load(f)
                return {
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": "file",
                    **data
                }
        return None

    def update_taxonomy(
        self,
        data: Dict[str, Any],
        updated_by: str = "user",
        change_summary: str = ""
    ) -> bool:
        """
        Update the taxonomy document with version history.

        Args:
            data: New taxonomy data
            updated_by: Who made the change
            change_summary: Description of the change

        Returns:
            True if successful
        """
        if not self.use_mongodb or not self._db:
            logger.warning("Cannot update taxonomy: MongoDB not available")
            return False

        current = self._taxonomy_collection.find_one({"_id": self.CANONICAL_ID})
        current_version = current.get("version", 0) if current else 0

        if current:
            self._save_history("master_cv_taxonomy", self.CANONICAL_ID, current)

        new_doc = {
            "_id": self.CANONICAL_ID,
            "version": current_version + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
            "target_roles": data.get("target_roles", {}),
            "skill_aliases": data.get("skill_aliases", {}),
            "default_fallback_role": data.get("default_fallback_role", "engineering_manager")
        }

        self._taxonomy_collection.replace_one(
            {"_id": self.CANONICAL_ID},
            new_doc,
            upsert=True
        )

        logger.info(f"Updated taxonomy to version {new_doc['version']}: {change_summary}")
        return True

    def add_skill_to_taxonomy(
        self,
        role_category: str,
        section_name: str,
        skill: str,
        updated_by: str = "user"
    ) -> bool:
        """
        Add a skill to a specific section in the taxonomy.

        Args:
            role_category: Target role (e.g., "engineering_manager")
            section_name: Section name (e.g., "Technical Leadership")
            skill: Skill to add
            updated_by: Who made the change

        Returns:
            True if successful
        """
        taxonomy = self.get_taxonomy()
        if not taxonomy:
            logger.error("No taxonomy found")
            return False

        target_roles = taxonomy.get("target_roles", {})
        if role_category not in target_roles:
            logger.error(f"Role category {role_category} not found")
            return False

        sections = target_roles[role_category].get("sections", [])
        for section in sections:
            if section.get("name") == section_name:
                skills = section.get("skills", [])
                if skill not in skills:
                    skills.append(skill)
                    section["skills"] = skills
                    break

        target_roles[role_category]["sections"] = sections
        taxonomy["target_roles"] = target_roles

        return self.update_taxonomy(
            taxonomy,
            updated_by,
            f"Added '{skill}' to {role_category}/{section_name}"
        )

    # ==========================================================================
    # ROLE CONTENT OPERATIONS
    # ==========================================================================

    @property
    def _roles_collection(self) -> Collection:
        """Get the roles collection."""
        if self._db is None:
            raise RuntimeError("MongoDB not available")
        return self._db["master_cv_roles"]

    def get_role(self, role_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific role document.

        Args:
            role_id: Role identifier (e.g., "01_seven_one_entertainment")

        Returns:
            Role document or None if not found
        """
        if self.use_mongodb and self._db is not None:
            doc = self._roles_collection.find_one({"role_id": role_id})
            if doc:
                doc.pop("_id", None)
                return doc

        # File fallback
        role_path = self.data_dir / ROLES_DIR / f"{role_id}.md"
        if role_path.exists():
            with open(role_path, "r") as f:
                content = f.read()
                return {
                    "role_id": role_id,
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": "file",
                    "markdown_content": content,
                    "parsed": None  # Parsing happens elsewhere
                }
        return None

    def get_all_roles(self) -> List[Dict[str, Any]]:
        """
        Get all role documents.

        Returns:
            List of role documents
        """
        if self.use_mongodb and self._db is not None:
            docs = list(self._roles_collection.find({}))
            for doc in docs:
                doc.pop("_id", None)
            if docs:
                return docs

        # File fallback
        roles = []
        roles_path = self.data_dir / ROLES_DIR
        if roles_path.exists():
            for role_file in sorted(roles_path.glob("*.md")):
                role_id = role_file.stem
                role_doc = self.get_role(role_id)
                if role_doc:
                    roles.append(role_doc)
        return roles

    def update_role(
        self,
        role_id: str,
        markdown_content: str,
        parsed: Optional[Dict[str, Any]] = None,
        updated_by: str = "user",
        change_summary: str = ""
    ) -> bool:
        """
        Update a role document with version history.

        Args:
            role_id: Role identifier
            markdown_content: New markdown content
            parsed: Optional parsed structure
            updated_by: Who made the change
            change_summary: Description of the change

        Returns:
            True if successful
        """
        if not self.use_mongodb or not self._db:
            logger.warning("Cannot update role: MongoDB not available")
            return False

        current = self._roles_collection.find_one({"role_id": role_id})
        current_version = current.get("version", 0) if current else 0

        if current:
            self._save_history("master_cv_roles", role_id, current)

        new_doc = {
            "role_id": role_id,
            "version": current_version + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
            "markdown_content": markdown_content,
            "parsed": parsed
        }

        self._roles_collection.replace_one(
            {"role_id": role_id},
            new_doc,
            upsert=True
        )

        logger.info(f"Updated role {role_id} to version {new_doc['version']}: {change_summary}")
        return True

    # ==========================================================================
    # VERSION HISTORY & ROLLBACK
    # ==========================================================================

    @property
    def _history_collection(self) -> Collection:
        """Get the version history collection."""
        if self._db is None:
            raise RuntimeError("MongoDB not available")
        return self._db["master_cv_history"]

    def _save_history(
        self,
        collection_name: str,
        doc_id: str,
        document: Dict[str, Any]
    ) -> None:
        """
        Save a document version to history.

        Args:
            collection_name: Source collection name
            doc_id: Document identifier
            document: Document to archive
        """
        if self._db is None:
            return

        # Remove MongoDB _id before storing in history
        doc_copy = {k: v for k, v in document.items() if k != "_id"}

        history_entry = {
            "collection": collection_name,
            "doc_id": doc_id,
            "version": document.get("version", 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": doc_copy
        }

        self._history_collection.insert_one(history_entry)

    def get_history(
        self,
        collection_name: str,
        doc_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a collection or document.

        Args:
            collection_name: Collection to get history for
            doc_id: Optional document ID to filter by
            limit: Maximum entries to return

        Returns:
            List of history entries, newest first
        """
        if not self.use_mongodb or not self._db:
            return []

        query: Dict[str, Any] = {"collection": collection_name}
        if doc_id:
            query["doc_id"] = doc_id

        cursor = self._history_collection.find(query).sort("timestamp", DESCENDING).limit(limit)

        history = []
        for doc in cursor:
            doc.pop("_id", None)
            history.append(doc)
        return history

    def rollback(
        self,
        collection_name: str,
        doc_id: str,
        target_version: int,
        updated_by: str = "user"
    ) -> bool:
        """
        Rollback a document to a previous version.

        Args:
            collection_name: Collection containing the document
            doc_id: Document identifier
            target_version: Version number to rollback to
            updated_by: Who initiated the rollback

        Returns:
            True if successful
        """
        if not self.use_mongodb or not self._db:
            logger.warning("Cannot rollback: MongoDB not available")
            return False

        # Find the target version in history
        history_entry = self._history_collection.find_one({
            "collection": collection_name,
            "doc_id": doc_id,
            "version": target_version
        })

        if not history_entry:
            logger.error(f"Version {target_version} not found in history")
            return False

        historical_data = history_entry.get("data", {})

        # Perform rollback based on collection type
        if collection_name == "master_cv_metadata":
            return self.update_metadata(
                historical_data,
                updated_by,
                f"Rollback to version {target_version}"
            )
        elif collection_name == "master_cv_taxonomy":
            return self.update_taxonomy(
                historical_data,
                updated_by,
                f"Rollback to version {target_version}"
            )
        elif collection_name == "master_cv_roles":
            return self.update_role(
                doc_id,
                historical_data.get("markdown_content", ""),
                historical_data.get("parsed"),
                updated_by,
                f"Rollback to version {target_version}"
            )

        logger.error(f"Unknown collection: {collection_name}")
        return False

    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================

    def is_connected(self) -> bool:
        """Check if MongoDB is available and connected."""
        return self.use_mongodb and self._db is not None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the master-cv data.

        Returns:
            Dict with counts and version info
        """
        stats = {
            "mongodb_connected": self.is_connected(),
            "metadata_version": None,
            "taxonomy_version": None,
            "roles_count": 0,
            "history_entries": 0
        }

        metadata = self.get_metadata()
        if metadata:
            stats["metadata_version"] = metadata.get("version")
            stats["roles_count"] = len(metadata.get("roles", []))

        taxonomy = self.get_taxonomy()
        if taxonomy:
            stats["taxonomy_version"] = taxonomy.get("version")

        if self.is_connected() and self._db is not None:
            stats["history_entries"] = self._history_collection.count_documents({})

        return stats

    def get_profile_for_suggestions(self) -> Dict[str, Any]:
        """
        Get candidate profile data formatted for strength suggestion service.

        Extracts skills, roles, and summary from metadata and taxonomy
        into a flat structure for LLM consumption.

        Returns:
            Dict with 'skills', 'roles', 'summary' keys
        """
        profile: Dict[str, Any] = {
            "skills": [],
            "roles": [],
            "summary": "",
        }

        # Get metadata for roles/experience
        metadata = self.get_metadata()
        if metadata:
            candidate = metadata.get("candidate", {})
            profile["summary"] = candidate.get("summary", "")

            # Extract role information
            for role in metadata.get("roles", []):
                role_info = {
                    "title": role.get("title", ""),
                    "company": role.get("company", ""),
                    "keywords": role.get("keywords", []),
                    "hard_skills": role.get("hard_skills", []),
                    "soft_skills": role.get("soft_skills", []),
                }
                profile["roles"].append(role_info)

                # Collect skills from roles
                for skill in role.get("hard_skills", []):
                    if skill not in profile["skills"]:
                        profile["skills"].append(skill)

        # Get taxonomy for additional skills
        taxonomy = self.get_taxonomy()
        if taxonomy:
            target_roles = taxonomy.get("target_roles", {})
            for role_category, role_data in target_roles.items():
                for section in role_data.get("sections", []):
                    for skill in section.get("skills", []):
                        if skill not in profile["skills"]:
                            profile["skills"].append(skill)

        return profile

    def get_candidate_profile_text(self) -> Optional[str]:
        """
        Get candidate profile as formatted text for fit scoring.

        Combines metadata and role content into a text representation
        suitable for LLM fit analysis. This provides the same context
        as the legacy master-cv.md file but sourced from MongoDB.

        Returns:
            Formatted candidate profile text, or None if not available
        """
        metadata = self.get_metadata()
        if not metadata:
            logger.warning("No metadata found in MongoDB for candidate profile")
            return None

        candidate = metadata.get("candidate", {})
        if not candidate:
            logger.warning("No candidate data in metadata")
            return None

        # Build profile text
        lines = []

        # Header
        name = candidate.get("name", "Unknown")
        title = candidate.get("title_base", "")
        lines.append(f"# {name}")
        if title:
            lines.append(f"**{title}**")
        lines.append("")

        # Contact info
        contact = candidate.get("contact", {})
        if contact:
            contact_parts = []
            if contact.get("email"):
                contact_parts.append(contact["email"])
            if contact.get("phone"):
                contact_parts.append(contact["phone"])
            if contact.get("nationality"):
                contact_parts.append(contact["nationality"])
            if contact.get("linkedin"):
                contact_parts.append(contact["linkedin"])
            if contact_parts:
                lines.append(" | ".join(contact_parts))
                lines.append("")

        # Summary
        summary = candidate.get("summary", "")
        if summary:
            lines.append("## Summary")
            lines.append(summary)
            lines.append("")

        # Years experience
        years_exp = candidate.get("years_experience", 0)
        if years_exp:
            lines.append(f"**Years of Experience:** {years_exp}+")
            lines.append("")

        # Languages
        languages = candidate.get("languages", [])
        if languages:
            lines.append(f"**Languages:** {', '.join(languages)}")
            lines.append("")

        # Education
        education = candidate.get("education", {})
        if education:
            lines.append("## Education")
            if education.get("masters"):
                lines.append(f"- {education['masters']}")
            if education.get("bachelors"):
                lines.append(f"- {education['bachelors']}")
            lines.append("")

        # Certifications
        certs = candidate.get("certifications", [])
        if certs:
            lines.append("## Certifications")
            for cert in certs:
                lines.append(f"- {cert}")
            lines.append("")

        # Roles from metadata
        roles = metadata.get("roles", [])
        if roles:
            lines.append("## Professional Experience")
            lines.append("")

            for role in roles:
                # Role header
                company = role.get("company", "Unknown Company")
                title = role.get("title", "Unknown Title")
                period = role.get("period", "")
                location = role.get("location", "")

                lines.append(f"### {title} at {company}")
                if period:
                    lines.append(f"*{period}*")
                if location:
                    lines.append(f"*{location}*")
                lines.append("")

                # Role details
                industry = role.get("industry", "")
                team_size = role.get("team_size", "")
                if industry or team_size:
                    details = []
                    if industry:
                        details.append(f"Industry: {industry}")
                    if team_size:
                        details.append(f"Team: {team_size}")
                    lines.append(f"*{' | '.join(details)}*")
                    lines.append("")

                # Keywords/competencies
                keywords = role.get("keywords", [])
                competencies = role.get("primary_competencies", [])
                if keywords or competencies:
                    all_tags = keywords + competencies
                    lines.append(f"**Key Areas:** {', '.join(all_tags[:10])}")
                    lines.append("")

                # Try to get role content from MongoDB
                role_id = role.get("id", "")
                if role_id:
                    role_doc = self.get_role(role_id)
                    if role_doc and role_doc.get("markdown_content"):
                        # Extract achievements from role markdown
                        content = role_doc["markdown_content"]
                        # Look for achievements section
                        if "## Achievements" in content:
                            achievements_start = content.find("## Achievements")
                            achievements_section = content[achievements_start:]
                            # Find next section
                            next_section = achievements_section.find("\n## ", 1)
                            if next_section > 0:
                                achievements_section = achievements_section[:next_section]
                            lines.append(achievements_section.strip())
                            lines.append("")

                # Skills from role metadata
                hard_skills = role.get("hard_skills", [])
                soft_skills = role.get("soft_skills", [])
                if hard_skills:
                    lines.append(f"**Technical Skills:** {', '.join(hard_skills[:8])}")
                if soft_skills:
                    lines.append(f"**Soft Skills:** {', '.join(soft_skills[:5])}")
                if hard_skills or soft_skills:
                    lines.append("")

        profile_text = "\n".join(lines)
        logger.info(f"Generated candidate profile text from MongoDB ({len(profile_text)} chars)")
        return profile_text


# ==========================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ==========================================================================

# Default store instance (MongoDB preferred, file fallback)
_default_store: Optional[MasterCVStore] = None


def get_store(use_mongodb: bool = True) -> MasterCVStore:
    """
    Get the default MasterCVStore instance.

    Args:
        use_mongodb: Whether to prefer MongoDB over files

    Returns:
        MasterCVStore instance
    """
    global _default_store
    if _default_store is None:
        _default_store = MasterCVStore(use_mongodb=use_mongodb)
    return _default_store


def get_metadata() -> Optional[Dict[str, Any]]:
    """Convenience function to get metadata."""
    return get_store().get_metadata()


def get_taxonomy() -> Optional[Dict[str, Any]]:
    """Convenience function to get taxonomy."""
    return get_store().get_taxonomy()


def get_role(role_id: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get a role."""
    return get_store().get_role(role_id)


def get_all_roles() -> List[Dict[str, Any]]:
    """Convenience function to get all roles."""
    return get_store().get_all_roles()


def get_candidate_profile_text() -> Optional[str]:
    """
    Convenience function to get candidate profile as text.

    Returns formatted profile text suitable for fit scoring,
    or None if MongoDB data is not available.
    """
    return get_store().get_candidate_profile_text()
