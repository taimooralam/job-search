"""
Runner service route modules.

This package contains modular route definitions for the runner service.
Each module handles a specific area of functionality.
"""

from .operations import router as operations_router
from .contacts import router as contacts_router
from .master_cv import router as master_cv_router
from .log_polling import router as log_polling_router
from .job_ingest import router as job_ingest_router

__all__ = [
    "operations_router",
    "contacts_router",
    "master_cv_router",
    "log_polling_router",
    "job_ingest_router",
]
