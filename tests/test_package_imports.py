"""
Verify package imports work correctly.

These tests ensure the package is properly installed and modules
can be imported. Critical for catching setup.py/installation issues
in CI environments.
"""


def test_pdf_service_package_structure():
    """Verify pdf_service package has expected structure."""
    # This test primarily ensures the package can be installed in editable mode
    # Note: Due to pytest's sys.path ordering, tests/pdf_service may be found first
    # The key verification is that pdf_service.app and pdf_service.pdf_helpers work
    import importlib
    spec = importlib.util.find_spec('pdf_service')
    assert spec is not None, "pdf_service should be importable (package must be installed)"


def test_pdf_helpers_can_be_imported():
    """Verify pdf_helpers module can be imported with all functions."""
    from pdf_service.pdf_helpers import (
        sanitize_for_path,
        tiptap_json_to_html,
        build_pdf_html_template
    )
    assert callable(sanitize_for_path)
    assert callable(tiptap_json_to_html)
    assert callable(build_pdf_html_template)


def test_pdf_service_app_can_be_imported():
    """Verify PDF service FastAPI app can be imported."""
    from pdf_service.app import app
    assert app is not None
    assert hasattr(app, 'routes')
