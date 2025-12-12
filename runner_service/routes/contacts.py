"""
Contacts CRUD and Outreach Generation API Routes.

Provides endpoints for managing contacts and generating outreach messages:
- GET /api/jobs/{job_id}/contacts - List all contacts for a job
- POST /api/jobs/{job_id}/contacts - Add new contacts (batch or single)
- DELETE /api/jobs/{job_id}/contacts/{contact_type}/{contact_index} - Delete a contact
- POST /api/jobs/{job_id}/contacts/{contact_type}/{contact_index}/generate-outreach - Generate outreach

This decouples outreach generation from the main pipeline, allowing on-demand
per-contact message generation with tier selection.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo import MongoClient

from src.common.model_tiers import (
    ModelTier,
    get_model_for_operation,
    get_tier_from_string,
    TIER_CONFIGS,
)

from ..auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["contacts"])


# =============================================================================
# Pydantic Models
# =============================================================================


class ContactCreate(BaseModel):
    """Model for creating a single contact."""

    name: str = Field(..., min_length=1, description="Contact's full name")
    role: str = Field(..., min_length=1, description="Contact's job title/role")
    linkedin_url: str = Field(..., description="LinkedIn profile URL")
    contact_type: Literal[
        "hiring_manager", "recruiter", "vp_director", "executive", "team_member", "peer"
    ] = Field(
        default="peer",
        description="Type of contact for outreach tailoring",
    )
    why_relevant: str = Field(
        default="",
        description="Why this contact is relevant for outreach",
    )
    primary: bool = Field(
        default=True,
        description="True = primary_contacts, False = secondary_contacts",
    )

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, v: str) -> str:
        """Validate that URL looks like a LinkedIn URL."""
        v = v.strip()
        if not v:
            raise ValueError("LinkedIn URL is required")
        if "linkedin.com" not in v.lower():
            raise ValueError("Must be a LinkedIn URL")
        return v


class ContactsAddRequest(BaseModel):
    """Request body for adding contacts (batch)."""

    contacts: List[ContactCreate] = Field(
        ...,
        min_length=1,
        description="List of contacts to add",
    )


class ContactsAddResponse(BaseModel):
    """Response for adding contacts."""

    success: bool
    added_count: int
    primary_added: int = 0
    secondary_added: int = 0
    errors: List[str] = Field(default_factory=list)


class ContactInfo(BaseModel):
    """Contact info returned in list responses."""

    name: str
    role: str
    linkedin_url: str
    contact_type: str = "peer"
    why_relevant: str = ""
    # Outreach messages if already generated
    linkedin_connection_message: Optional[str] = None
    linkedin_inmail: Optional[str] = None
    email_body: Optional[str] = None


class ContactsResponse(BaseModel):
    """Response for listing contacts."""

    primary_contacts: List[ContactInfo] = Field(default_factory=list)
    secondary_contacts: List[ContactInfo] = Field(default_factory=list)
    total: int


class DeleteContactResponse(BaseModel):
    """Response for deleting a contact."""

    success: bool
    message: str = ""


class OutreachRequest(BaseModel):
    """Request body for generating outreach message."""

    tier: Literal["fast", "balanced", "quality"] = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    message_type: Literal["connection", "inmail"] = Field(
        default="connection",
        description="Type of message to generate: 'connection' (<=300 chars) or 'inmail' (400-600 chars)",
    )


class OutreachResponse(BaseModel):
    """Response for outreach generation."""

    success: bool
    message: str = ""
    subject: Optional[str] = None  # Only for inmail
    char_count: int = 0
    cost_usd: float = 0.0
    run_id: str = ""
    model_used: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================


def _get_db_client() -> MongoClient:
    """
    Get MongoDB client for job operations.

    Returns:
        MongoClient instance
    """
    mongo_uri = (
        os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
        or "mongodb://localhost:27017"
    )
    return MongoClient(mongo_uri)


def _validate_job_exists(job_id: str) -> dict:
    """
    Validate that a job exists in MongoDB.

    Args:
        job_id: MongoDB ObjectId as string

    Returns:
        Job document if found

    Raises:
        HTTPException: If job_id is invalid or job not found
    """
    # Validate ObjectId format
    try:
        object_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    client = _get_db_client()
    try:
        db = client[os.getenv("MONGO_DB_NAME", "jobs")]
        job = db["level-2"].find_one({"_id": object_id})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        client.close()


def _get_contact(
    job: dict, contact_type: str, index: int
) -> Optional[dict]:
    """
    Get a specific contact from job document.

    Args:
        job: Job document from MongoDB
        contact_type: "primary" or "secondary"
        index: 0-based index into the contacts array

    Returns:
        Contact dict if found, None otherwise

    Raises:
        HTTPException: If contact_type is invalid or index out of range
    """
    if contact_type not in ("primary", "secondary"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid contact type '{contact_type}'. Must be 'primary' or 'secondary'",
        )

    field_name = f"{contact_type}_contacts"
    contacts = job.get(field_name) or []

    if not isinstance(contacts, list):
        contacts = []

    if index < 0 or index >= len(contacts):
        raise HTTPException(
            status_code=400,
            detail=f"Contact index {index} out of range. {contact_type}_contacts has {len(contacts)} items",
        )

    return contacts[index]


def _update_contacts(
    job_id: str, contact_type: str, contacts: list
) -> bool:
    """
    Update contacts array in MongoDB.

    Args:
        job_id: MongoDB ObjectId as string
        contact_type: "primary" or "secondary"
        contacts: New contacts list

    Returns:
        True if update succeeded, False otherwise
    """
    if contact_type not in ("primary", "secondary"):
        return False

    field_name = f"{contact_type}_contacts"

    client = _get_db_client()
    try:
        db = client[os.getenv("MONGO_DB_NAME", "jobs")]
        result = db["level-2"].update_one(
            {"_id": ObjectId(job_id)},
            {
                "$set": {
                    field_name: contacts,
                    "updatedAt": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Failed to update contacts for job {job_id}: {e}")
        return False
    finally:
        client.close()


def _validate_tier(tier_str: str) -> ModelTier:
    """
    Validate and convert tier string to ModelTier enum.

    Args:
        tier_str: Tier string ('fast', 'balanced', 'quality')

    Returns:
        ModelTier enum value

    Raises:
        HTTPException: If tier is invalid
    """
    tier = get_tier_from_string(tier_str)
    if tier is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier_str}'. Must be 'fast', 'balanced', or 'quality'",
        )
    return tier


def _generate_run_id() -> str:
    """Generate unique run ID for outreach generation."""
    return f"outreach_{uuid.uuid4().hex[:12]}"


def _contact_to_info(contact: dict) -> ContactInfo:
    """Convert a contact dict to ContactInfo model."""
    return ContactInfo(
        name=contact.get("name", contact.get("contact_name", "Unknown")),
        role=contact.get("role", contact.get("contact_role", "Unknown")),
        linkedin_url=contact.get("linkedin_url", ""),
        contact_type=contact.get("contact_type", "peer"),
        why_relevant=contact.get("why_relevant", ""),
        linkedin_connection_message=contact.get("linkedin_connection_message"),
        linkedin_inmail=contact.get("linkedin_inmail"),
        email_body=contact.get("email_body"),
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/{job_id}/contacts",
    response_model=ContactsResponse,
    dependencies=[Depends(verify_token)],
    summary="List all contacts for a job",
    description="Get all primary and secondary contacts associated with a job",
)
async def list_contacts(job_id: str) -> ContactsResponse:
    """
    List all contacts for a job.

    Returns both primary_contacts (hiring-related) and secondary_contacts
    (cross-functional/peer contacts) with any generated outreach messages.

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        ContactsResponse with primary and secondary contact lists
    """
    logger.info(f"Listing contacts for job {job_id}")

    try:
        job = _validate_job_exists(job_id)

        primary = job.get("primary_contacts") or []
        secondary = job.get("secondary_contacts") or []

        # Convert to response format
        primary_contacts = [_contact_to_info(c) for c in primary if isinstance(c, dict)]
        secondary_contacts = [_contact_to_info(c) for c in secondary if isinstance(c, dict)]

        total = len(primary_contacts) + len(secondary_contacts)

        logger.info(
            f"Found {len(primary_contacts)} primary, {len(secondary_contacts)} secondary contacts for job {job_id}"
        )

        return ContactsResponse(
            primary_contacts=primary_contacts,
            secondary_contacts=secondary_contacts,
            total=total,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list contacts for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{job_id}/contacts",
    response_model=ContactsAddResponse,
    dependencies=[Depends(verify_token)],
    summary="Add new contacts to a job",
    description="Add one or more contacts to a job's primary or secondary contacts list",
)
async def add_contacts(
    job_id: str,
    request: ContactsAddRequest,
) -> ContactsAddResponse:
    """
    Add new contacts to a job.

    Supports batch addition of contacts. Each contact specifies whether it
    should be added to primary_contacts or secondary_contacts via the
    'primary' field.

    Args:
        job_id: MongoDB ObjectId of the job
        request: ContactsAddRequest with list of contacts to add

    Returns:
        ContactsAddResponse with counts of added contacts
    """
    logger.info(f"Adding {len(request.contacts)} contacts to job {job_id}")

    try:
        job = _validate_job_exists(job_id)

        # Get existing contacts
        primary = list(job.get("primary_contacts") or [])
        secondary = list(job.get("secondary_contacts") or [])

        primary_added = 0
        secondary_added = 0
        errors: List[str] = []

        for i, contact in enumerate(request.contacts):
            try:
                # Create contact dict
                contact_dict = {
                    "name": contact.name,
                    "role": contact.role,
                    "linkedin_url": contact.linkedin_url,
                    "contact_type": contact.contact_type,
                    "why_relevant": contact.why_relevant,
                    "recent_signals": [],
                    # Initialize empty outreach fields
                    "linkedin_connection_message": "",
                    "linkedin_inmail_subject": "",
                    "linkedin_inmail": "",
                    "email_subject": "",
                    "email_body": "",
                    "reasoning": "",
                    "already_applied_frame": "adding_context",
                    "linkedin_message": "",  # Legacy field
                }

                if contact.primary:
                    primary.append(contact_dict)
                    primary_added += 1
                else:
                    secondary.append(contact_dict)
                    secondary_added += 1

            except Exception as e:
                errors.append(f"Contact {i}: {str(e)}")

        # Update MongoDB
        client = _get_db_client()
        try:
            db = client[os.getenv("MONGO_DB_NAME", "jobs")]
            result = db["level-2"].update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "primary_contacts": primary,
                        "secondary_contacts": secondary,
                        "updatedAt": datetime.utcnow(),
                    }
                },
            )

            if result.modified_count == 0 and (primary_added + secondary_added) > 0:
                # Document may not have changed if contacts were identical
                logger.warning(f"No documents modified when adding contacts to job {job_id}")

        finally:
            client.close()

        added_count = primary_added + secondary_added
        logger.info(
            f"Added {primary_added} primary, {secondary_added} secondary contacts to job {job_id}"
        )

        return ContactsAddResponse(
            success=added_count > 0,
            added_count=added_count,
            primary_added=primary_added,
            secondary_added=secondary_added,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to add contacts to job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{job_id}/contacts/{contact_type}/{contact_index}",
    response_model=DeleteContactResponse,
    dependencies=[Depends(verify_token)],
    summary="Delete a specific contact",
    description="Delete a contact by type (primary/secondary) and index",
)
async def delete_contact(
    job_id: str,
    contact_type: str,
    contact_index: int,
) -> DeleteContactResponse:
    """
    Delete a specific contact from a job.

    Args:
        job_id: MongoDB ObjectId of the job
        contact_type: "primary" or "secondary"
        contact_index: 0-based index of the contact to delete

    Returns:
        DeleteContactResponse indicating success
    """
    logger.info(
        f"Deleting {contact_type} contact at index {contact_index} from job {job_id}"
    )

    try:
        job = _validate_job_exists(job_id)

        # Validate contact exists
        contact = _get_contact(job, contact_type, contact_index)
        contact_name = contact.get("name", "Unknown")

        # Get contacts list and remove the contact
        field_name = f"{contact_type}_contacts"
        contacts = list(job.get(field_name) or [])
        del contacts[contact_index]

        # Update MongoDB
        success = _update_contacts(job_id, contact_type, contacts)

        if success:
            logger.info(
                f"Deleted {contact_type} contact '{contact_name}' from job {job_id}"
            )
            return DeleteContactResponse(
                success=True,
                message=f"Deleted contact '{contact_name}'",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to update contacts in database",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Failed to delete contact from job {job_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{job_id}/contacts/{contact_type}/{contact_index}/generate-outreach",
    response_model=OutreachResponse,
    dependencies=[Depends(verify_token)],
    summary="Generate outreach message for a contact",
    description="Generate a personalized outreach message for a specific contact",
)
async def generate_outreach(
    job_id: str,
    contact_type: str,
    contact_index: int,
    request: OutreachRequest,
) -> OutreachResponse:
    """
    Generate outreach message for a specific contact.

    Uses the OutreachGenerator to create personalized messages based on:
    - Contact type (hiring_manager, recruiter, vp_director, etc.)
    - Message type (connection or inmail)
    - Job context (company, role, pain points)
    - Candidate profile

    Args:
        job_id: MongoDB ObjectId of the job
        contact_type: "primary" or "secondary"
        contact_index: 0-based index of the contact
        request: OutreachRequest with tier and message_type

    Returns:
        OutreachResponse with generated message and metadata
    """
    run_id = _generate_run_id()
    logger.info(
        f"[{run_id}] Generating {request.message_type} outreach for "
        f"{contact_type} contact {contact_index} on job {job_id}"
    )

    try:
        job = _validate_job_exists(job_id)
        contact = _get_contact(job, contact_type, contact_index)
        tier = _validate_tier(request.tier)

        # Get model for this tier
        model = get_model_for_operation(tier, "outreach")

        # Check if we have the OutreachGenerationService
        # If not available, use the OutreachGenerator from layer6 directly
        try:
            from src.services.outreach_service import OutreachGenerationService

            service = OutreachGenerationService()
            result = await service.execute(
                job_id=job_id,
                contact_index=contact_index,
                contact_type=contact_type,
                tier=tier,
                message_type=request.message_type,
            )

            return OutreachResponse(
                success=result.success,
                message=result.data.get("message", "") if result.data else "",
                subject=result.data.get("subject") if result.data else None,
                char_count=result.data.get("char_count", 0) if result.data else 0,
                cost_usd=result.cost_usd,
                run_id=result.run_id,
                model_used=result.model_used,
                error=result.error,
            )

        except ImportError:
            # OutreachGenerationService not implemented yet
            # Use a simplified approach with the existing OutreachGenerator
            logger.warning(
                "OutreachGenerationService not available, using simplified generation"
            )

            from src.layer6.outreach_generator import OutreachGenerator
            from src.common.state import JobState

            # Build minimal state for outreach generation
            state: JobState = {
                "job_id": job_id,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "job_description": job.get("jd_text", job.get("job_description", "")),
                "scraped_job_posting": job.get("scraped_job_posting"),
                "job_url": job.get("job_url", job.get("url", "")),
                "source": job.get("source", "unknown"),
                "candidate_profile": job.get("candidate_profile", ""),
                "selected_stars": job.get("selected_stars", []),
                "primary_contacts": [contact] if contact_type == "primary" else [],
                "secondary_contacts": [contact] if contact_type == "secondary" else [],
                # Fill required fields with defaults
                "extracted_jd": job.get("extracted_jd"),
                "jd_annotations": job.get("jd_annotations"),
                "improvement_suggestions": job.get("improvement_suggestions"),
                "interview_prep": job.get("interview_prep"),
                "pain_points": job.get("pain_points"),
                "strategic_needs": job.get("strategic_needs"),
                "risks_if_unfilled": job.get("risks_if_unfilled"),
                "success_metrics": job.get("success_metrics"),
                "star_to_pain_mapping": job.get("star_to_pain_mapping"),
                "all_stars": job.get("all_stars"),
                "company_research": job.get("company_research"),
                "company_summary": job.get("company_summary"),
                "company_url": job.get("company_url"),
                "role_research": job.get("role_research"),
                "application_form_fields": job.get("application_form_fields"),
                "fit_score": job.get("fit_score"),
                "fit_rationale": job.get("fit_rationale"),
                "fit_category": job.get("fit_category"),
                "tier": job.get("tier"),
                "people": job.get("people"),
                "outreach_packages": job.get("outreach_packages"),
                "fallback_cover_letters": job.get("fallback_cover_letters"),
                "cover_letter": job.get("cover_letter"),
                "cv_path": job.get("cv_path"),
                "cv_text": job.get("cv_text"),
                "cv_reasoning": job.get("cv_reasoning"),
                "dossier_path": job.get("dossier_path"),
                "drive_folder_url": job.get("drive_folder_url"),
                "sheet_row_id": job.get("sheet_row_id"),
                "run_id": run_id,
                "created_at": datetime.utcnow().isoformat(),
                "errors": [],
                "status": "processing",
                "trace_url": None,
                "token_usage": None,
                "total_tokens": None,
                "total_cost_usd": None,
                "processing_tier": request.tier.upper() if request.tier else "B",
                "tier_config": None,
                "pipeline_runs": None,
                "debug_mode": False,
            }

            generator = OutreachGenerator()
            packages = generator.generate_outreach_packages(state)

            # Find the package for the requested message type
            message = ""
            subject = None
            char_count = 0

            channel_map = {
                "connection": "linkedin_connection",
                "inmail": "inmail_email",
            }
            target_channel = channel_map.get(request.message_type, "linkedin_connection")

            for pkg in packages:
                if pkg.get("channel") == target_channel:
                    message = pkg.get("message", "")
                    subject = pkg.get("subject")
                    char_count = len(message)
                    break

            if message:
                # Update the contact with the generated message
                field_name = f"{contact_type}_contacts"
                contacts = list(job.get(field_name) or [])

                if request.message_type == "connection":
                    contacts[contact_index]["linkedin_connection_message"] = message
                else:
                    contacts[contact_index]["linkedin_inmail"] = message
                    if subject:
                        contacts[contact_index]["linkedin_inmail_subject"] = subject

                _update_contacts(job_id, contact_type, contacts)

                logger.info(
                    f"[{run_id}] Generated {request.message_type} message: {char_count} chars"
                )

                return OutreachResponse(
                    success=True,
                    message=message,
                    subject=subject,
                    char_count=char_count,
                    cost_usd=0.0,  # Simplified version doesn't track cost yet
                    run_id=run_id,
                    model_used=model,
                )
            else:
                return OutreachResponse(
                    success=False,
                    message="",
                    run_id=run_id,
                    error="Failed to generate outreach message - no valid content produced",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"[{run_id}] Failed to generate outreach for job {job_id}: {e}"
        )
        return OutreachResponse(
            success=False,
            message="",
            run_id=run_id,
            error=str(e),
        )
