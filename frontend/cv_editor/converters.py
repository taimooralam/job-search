"""
Bridge module for CV text conversion.

Re-exports the markdown_to_prosemirror function from frontend.app
to satisfy imports from cv_generation_service.py.

This module uses lazy importing to avoid Flask initialization
overhead when the module is first loaded.
"""
from typing import Dict, Any


def markdown_to_prosemirror(cv_text: str) -> Dict[str, Any]:
    """
    Convert markdown CV text to TipTap/ProseMirror editor state.

    This is a bridge function that wraps the existing
    migrate_cv_text_to_editor_state() function from frontend.app.

    Args:
        cv_text: Markdown-formatted CV text

    Returns:
        Full TipTap editor state dict with:
        - version: Schema version
        - content: TipTap document structure
        - documentStyles: Professional styling defaults (fonts, colors, margins)
    """
    # Lazy import to avoid Flask initialization overhead at module load time
    from frontend.app import migrate_cv_text_to_editor_state

    return migrate_cv_text_to_editor_state(cv_text)
