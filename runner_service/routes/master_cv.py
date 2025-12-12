"""
Master CV API Routes.

Provides REST endpoints for managing Master CV data stored in MongoDB:
- Metadata: Candidate info and role metadata
- Taxonomy: Skills taxonomy per target role
- Roles: Individual role documents with markdown content
- History: Version history for audit trail
- Rollback: Revert to previous versions

These endpoints enable the Master CV Editor frontend to perform CRUD operations
on candidate profile data without requiring the full pipeline codebase on Vercel.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/master-cv", tags=["master-cv"])


# =============================================================================
# Pydantic Models
# =============================================================================


class MetadataResponse(BaseModel):
    """Response model for metadata endpoint."""

    version: Optional[int] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    candidate: Dict[str, Any] = Field(default_factory=dict)
    roles: List[Dict[str, Any]] = Field(default_factory=list)


class MetadataUpdateRequest(BaseModel):
    """Request model for updating metadata."""

    candidate: Dict[str, Any] = Field(
        default_factory=dict,
        description="Candidate information (name, email, summary, etc.)",
    )
    roles: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of role metadata objects",
    )
    updated_by: str = Field(
        default="user",
        description="Who made the change (user, system, migration)",
    )
    change_summary: str = Field(
        default="",
        description="Description of the change",
    )


class TaxonomyResponse(BaseModel):
    """Response model for taxonomy endpoint."""

    version: Optional[int] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    target_roles: Dict[str, Any] = Field(default_factory=dict)
    skill_aliases: Dict[str, List[str]] = Field(default_factory=dict)
    default_fallback_role: str = "engineering_manager"


class TaxonomyUpdateRequest(BaseModel):
    """Request model for updating taxonomy."""

    target_roles: Dict[str, Any] = Field(
        default_factory=dict,
        description="Target roles with skill sections",
    )
    skill_aliases: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Skill name aliases mapping",
    )
    default_fallback_role: str = Field(
        default="engineering_manager",
        description="Default role for taxonomy lookups",
    )
    updated_by: str = Field(
        default="user",
        description="Who made the change",
    )
    change_summary: str = Field(
        default="",
        description="Description of the change",
    )


class AddSkillRequest(BaseModel):
    """Request model for adding a skill to taxonomy."""

    role_category: str = Field(
        ...,
        description="Target role category (e.g., 'engineering_manager')",
    )
    section_name: str = Field(
        ...,
        description="Section name (e.g., 'Technical Leadership')",
    )
    skill: str = Field(
        ...,
        description="Skill name to add",
    )
    updated_by: str = Field(
        default="user",
        description="Who made the change",
    )


class RoleResponse(BaseModel):
    """Response model for a single role document."""

    role_id: str
    version: Optional[int] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    markdown_content: str = ""
    parsed: Optional[Dict[str, Any]] = None


class RoleUpdateRequest(BaseModel):
    """Request model for updating a role."""

    markdown_content: str = Field(
        ...,
        description="Markdown content for the role",
    )
    parsed: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional parsed structure (achievements, skills, variants)",
    )
    updated_by: str = Field(
        default="user",
        description="Who made the change",
    )
    change_summary: str = Field(
        default="",
        description="Description of the change",
    )


class HistoryEntry(BaseModel):
    """Model for a version history entry."""

    collection: str
    doc_id: str
    version: int
    timestamp: str
    data: Dict[str, Any] = Field(default_factory=dict)


class HistoryResponse(BaseModel):
    """Response model for version history."""

    entries: List[HistoryEntry] = Field(default_factory=list)
    total: int = 0


class RollbackRequest(BaseModel):
    """Request model for rollback operation."""

    updated_by: str = Field(
        default="user",
        description="Who initiated the rollback",
    )


class RollbackResponse(BaseModel):
    """Response model for rollback operation."""

    success: bool
    message: str = ""
    new_version: Optional[int] = None


class StatsResponse(BaseModel):
    """Response model for stats endpoint."""

    mongodb_connected: bool = False
    metadata_version: Optional[int] = None
    taxonomy_version: Optional[int] = None
    roles_count: int = 0
    history_entries: int = 0


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str = ""


# =============================================================================
# Helper Functions
# =============================================================================


def _get_store():
    """
    Get the MasterCVStore instance with MongoDB enabled.

    Returns:
        MasterCVStore instance

    Raises:
        HTTPException: If store cannot be initialized
    """
    try:
        from src.common.master_cv_store import get_store

        store = get_store(use_mongodb=True)
        return store
    except ImportError as e:
        logger.error(f"Failed to import master_cv_store: {e}")
        raise HTTPException(
            status_code=500,
            detail="Master CV store module not available",
        )
    except Exception as e:
        logger.error(f"Failed to initialize master_cv_store: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize store: {str(e)}",
        )


# =============================================================================
# Metadata Endpoints
# =============================================================================


@router.get(
    "/metadata",
    dependencies=[Depends(verify_token)],
    summary="Get Master CV metadata",
    description="Retrieve candidate info and role list from the canonical metadata document",
)
async def get_metadata():
    """
    Get the canonical metadata document.

    Returns candidate information and role metadata used by the pipeline.
    Falls back to file-based data if MongoDB is unavailable.

    Returns:
        JSON with success flag and metadata document
    """
    logger.info("Getting Master CV metadata")

    try:
        store = _get_store()
        data = store.get_metadata()

        if not data:
            raise HTTPException(status_code=404, detail="Metadata not found")

        return {
            "success": True,
            "metadata": data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/metadata",
    dependencies=[Depends(verify_token)],
    summary="Update Master CV metadata",
    description="Update candidate info and role list with version history",
)
async def update_metadata(request: MetadataUpdateRequest):
    """
    Update the metadata document with version history.

    Creates a new version and archives the previous one for rollback.

    Args:
        request: MetadataUpdateRequest with new candidate and roles data

    Returns:
        JSON with success status and new version
    """
    logger.info(f"Updating Master CV metadata (by {request.updated_by})")

    try:
        store = _get_store()

        if not store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="MongoDB not connected - cannot update metadata",
            )

        success = store.update_metadata(
            data={
                "candidate": request.candidate,
                "roles": request.roles,
            },
            updated_by=request.updated_by,
            change_summary=request.change_summary,
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update metadata",
            )

        # Get new version
        metadata = store.get_metadata()

        return {
            "success": True,
            "message": "Metadata updated",
            "version": metadata.get("version") if metadata else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class MetadataRoleUpdateRequest(BaseModel):
    """Request model for updating a specific role in metadata."""
    change_summary: str = Field(default="Updated role via API")
    # All other fields are passed through as role data


@router.put(
    "/metadata/roles/{role_id}",
    dependencies=[Depends(verify_token)],
    summary="Update role in metadata",
    description="Update a specific role within the metadata document",
)
async def update_metadata_role(role_id: str, request: Dict[str, Any] = Body(...)):
    """
    Update a specific role within metadata.

    Args:
        role_id: The role ID to update
        request: Role fields to update (id, keywords, etc.)

    Returns:
        JSON with success status
    """
    logger.info(f"Updating metadata role: {role_id}")

    try:
        store = _get_store()

        if not store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="MongoDB not connected - cannot update role",
            )

        change_summary = request.pop("change_summary", f"Updated role {role_id}")

        success = store.update_metadata_role(
            role_id,
            request,
            updated_by="user",
            change_summary=change_summary
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update role metadata",
            )

        return {
            "success": True,
            "message": f"Role {role_id} updated"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update metadata role {role_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Taxonomy Endpoints
# =============================================================================


@router.get(
    "/taxonomy",
    dependencies=[Depends(verify_token)],
    summary="Get skills taxonomy",
    description="Retrieve the skills taxonomy for target roles",
)
async def get_taxonomy():
    """
    Get the canonical taxonomy document.

    Returns skills organized by target role category for CV generation.

    Returns:
        JSON with success flag and taxonomy document
    """
    logger.info("Getting skills taxonomy")

    try:
        store = _get_store()
        data = store.get_taxonomy()

        if not data:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        return {
            "success": True,
            "taxonomy": data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get taxonomy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/taxonomy",
    dependencies=[Depends(verify_token)],
    summary="Update skills taxonomy",
    description="Update the skills taxonomy with version history",
)
async def update_taxonomy(request: TaxonomyUpdateRequest):
    """
    Update the taxonomy document with version history.

    Args:
        request: TaxonomyUpdateRequest with new taxonomy data

    Returns:
        JSON with success status and new version
    """
    logger.info(f"Updating skills taxonomy (by {request.updated_by})")

    try:
        store = _get_store()

        if not store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="MongoDB not connected - cannot update taxonomy",
            )

        success = store.update_taxonomy(
            data={
                "target_roles": request.target_roles,
                "skill_aliases": request.skill_aliases,
                "default_fallback_role": request.default_fallback_role,
            },
            updated_by=request.updated_by,
            change_summary=request.change_summary,
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update taxonomy",
            )

        taxonomy = store.get_taxonomy()

        return {
            "success": True,
            "message": "Taxonomy updated",
            "version": taxonomy.get("version") if taxonomy else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update taxonomy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/taxonomy/skill",
    dependencies=[Depends(verify_token)],
    summary="Add skill to taxonomy",
    description="Add a new skill to a specific section in the taxonomy",
)
async def add_skill_to_taxonomy(request: AddSkillRequest):
    """
    Add a skill to a specific section in the taxonomy.

    Args:
        request: AddSkillRequest with role_category, section_name, and skill

    Returns:
        JSON with success status
    """
    logger.info(
        f"Adding skill '{request.skill}' to {request.role_category}/{request.section_name}"
    )

    try:
        store = _get_store()

        if not store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="MongoDB not connected - cannot add skill",
            )

        success = store.add_skill_to_taxonomy(
            role_category=request.role_category,
            section_name=request.section_name,
            skill=request.skill,
            updated_by=request.updated_by,
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to add skill",
            )

        return {
            "success": True,
            "message": f"Added '{request.skill}' to {request.role_category}/{request.section_name}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to add skill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Role Endpoints
# =============================================================================


@router.get(
    "/roles",
    dependencies=[Depends(verify_token)],
    summary="Get all role documents",
    description="Retrieve all role documents with markdown content",
)
async def get_all_roles():
    """
    Get all role documents.

    Returns a list of all role documents with their markdown content
    and optional parsed structure.

    Returns:
        JSON with success flag, roles list and count
    """
    logger.info("Getting all role documents")

    try:
        store = _get_store()
        roles = store.get_all_roles()

        return {
            "success": True,
            "roles": roles,
            "count": len(roles)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get roles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/roles/{role_id}",
    dependencies=[Depends(verify_token)],
    summary="Get specific role document",
    description="Retrieve a specific role document by ID",
)
async def get_role(role_id: str):
    """
    Get a specific role document.

    Args:
        role_id: Role identifier (e.g., "01_seven_one_entertainment")

    Returns:
        JSON with success flag and role document
    """
    logger.info(f"Getting role document: {role_id}")

    try:
        store = _get_store()
        role = store.get_role(role_id)

        if not role:
            raise HTTPException(
                status_code=404,
                detail=f"Role {role_id} not found",
            )

        return {
            "success": True,
            "role": role
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get role {role_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/roles/{role_id}",
    dependencies=[Depends(verify_token)],
    summary="Update role document",
    description="Update a role's markdown content and optional parsed structure",
)
async def update_role(role_id: str, request: RoleUpdateRequest):
    """
    Update a role document with version history.

    Args:
        role_id: Role identifier
        request: RoleUpdateRequest with new content

    Returns:
        JSON with success status and new version
    """
    logger.info(f"Updating role document: {role_id} (by {request.updated_by})")

    try:
        store = _get_store()

        if not store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="MongoDB not connected - cannot update role",
            )

        success = store.update_role(
            role_id=role_id,
            markdown_content=request.markdown_content,
            parsed=request.parsed,
            updated_by=request.updated_by,
            change_summary=request.change_summary,
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update role",
            )

        role = store.get_role(role_id)

        return {
            "success": True,
            "message": f"Role {role_id} updated",
            "version": role.get("version") if role else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update role {role_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# History & Rollback Endpoints
# =============================================================================


@router.get(
    "/history/{collection_name}",
    dependencies=[Depends(verify_token)],
    summary="Get version history",
    description="Retrieve version history for a collection",
)
async def get_history(
    collection_name: str,
    doc_id: Optional[str] = None,
    limit: int = 10,
):
    """
    Get version history for a collection or specific document.

    Args:
        collection_name: Collection name (master_cv_metadata, master_cv_taxonomy, master_cv_roles)
        doc_id: Optional document ID to filter by
        limit: Maximum entries to return (default 10)

    Returns:
        JSON with success flag, history list and count
    """
    logger.info(f"Getting history for {collection_name} (doc_id={doc_id}, limit={limit})")

    # Validate collection name
    valid_collections = ["master_cv_metadata", "master_cv_taxonomy", "master_cv_roles"]
    if collection_name not in valid_collections:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid collection. Must be one of: {valid_collections}",
        )

    try:
        store = _get_store()
        history = store.get_history(
            collection_name=collection_name,
            doc_id=doc_id,
            limit=limit,
        )

        return {
            "success": True,
            "history": history,
            "count": len(history)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get history for {collection_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/rollback/{collection_name}/{target_version}",
    dependencies=[Depends(verify_token)],
    summary="Rollback to previous version",
    description="Rollback a document to a specific previous version",
)
async def rollback(
    collection_name: str,
    target_version: int,
    request: Optional[RollbackRequest] = None,
):
    """
    Rollback a document to a previous version.

    For metadata and taxonomy, doc_id is "canonical".
    For roles, doc_id must be provided in request body.

    Args:
        collection_name: Collection name
        target_version: Version number to rollback to
        request: Optional rollback request with doc_id

    Returns:
        JSON with success status
    """
    # Validate collection name
    valid_collections = ["master_cv_metadata", "master_cv_taxonomy", "master_cv_roles"]
    if collection_name not in valid_collections:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid collection. Must be one of: {valid_collections}",
        )

    # Determine doc_id based on collection
    if collection_name == "master_cv_roles":
        if not request or not request.doc_id:
            raise HTTPException(
                status_code=400,
                detail="doc_id required for roles rollback",
            )
        doc_id = request.doc_id
    else:
        doc_id = "canonical"

    logger.info(
        f"Rolling back {collection_name}/{doc_id} to version {target_version}"
    )

    try:
        store = _get_store()

        if not store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="MongoDB not connected - cannot perform rollback",
            )

        success = store.rollback(
            collection_name=collection_name,
            doc_id=doc_id,
            target_version=target_version,
            updated_by="user",
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to rollback to version {target_version}",
            )

        return {
            "success": True,
            "message": f"Rolled back {collection_name}/{doc_id} to version {target_version}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to rollback {collection_name}/{doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Stats Endpoint
# =============================================================================


@router.get(
    "/stats",
    dependencies=[Depends(verify_token)],
    summary="Get Master CV statistics",
    description="Retrieve statistics about the Master CV data store",
)
async def get_stats():
    """
    Get statistics about the Master CV data.

    Returns counts and version information for monitoring.

    Returns:
        JSON with success flag and stats
    """
    logger.info("Getting Master CV stats")

    try:
        store = _get_store()
        stats = store.get_stats()

        return {
            "success": True,
            "stats": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
