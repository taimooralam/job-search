"""
Runner service route modules.

This package contains modular route definitions for the runner service.
Each module handles a specific area of functionality.
"""

from .operations import router as operations_router
from .contacts import router as contacts_router
from .master_cv import router as master_cv_router

__all__ = ["operations_router", "contacts_router", "master_cv_router"]
