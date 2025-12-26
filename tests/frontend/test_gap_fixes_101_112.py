"""
Unit tests for GAP-101 through GAP-112 fixes.

Tests cover:
- GAP-101: CV Preview Sync After Save (cvContentUpdated event)
- GAP-107: Annotation Dimension Toggle + Auto-Delete
- GAP-108: Batch Annotation Delete (getActiveAnnotationManager)
- GAP-109: Skill Color Timing Fix (requestAnimationFrame)
- GAP-100: CV Editor idPrefix support
- GAP-102: Application URL Button rendering
- GAP-112: Batch Pipeline Popups Removed
"""

import pytest
from pathlib import Path


# ==============================================================================
# GAP-101: CV Preview Sync After Save
# ==============================================================================

class TestCVPreviewSync:
    """Tests for GAP-101: cvContentUpdated event after save."""

    @pytest.fixture
    def cv_editor_js(self):
        """Read cv-editor.js content."""
        path = Path(__file__).parent.parent.parent / 'frontend/static/js/cv-editor.js'
        return path.read_text()

    def test_save_method_dispatches_event(self, cv_editor_js):
        """Save method should dispatch cvContentUpdated event."""
        assert "new CustomEvent('cvContentUpdated'" in cv_editor_js
        assert "window.dispatchEvent(event)" in cv_editor_js

    def test_event_contains_required_fields(self, cv_editor_js):
        """Event detail should contain jobId, content, savedAt."""
        assert "jobId: this.jobId" in cv_editor_js
        assert "content: this.editor.getJSON()" in cv_editor_js
        assert "savedAt:" in cv_editor_js

    def test_console_log_confirms_dispatch(self, cv_editor_js):
        """Console log should confirm event dispatch."""
        assert "Dispatched cvContentUpdated event" in cv_editor_js


# ==============================================================================
# GAP-107: Annotation Dimension Toggle + Auto-Delete
# ==============================================================================

class TestAnnotationDimensionToggle:
    """Tests for GAP-107: Clicking selected dimension toggles it off."""

    @pytest.fixture
    def jd_annotation_js(self):
        """Read jd-annotation.js content."""
        path = Path(__file__).parent.parent.parent / 'frontend/static/js/jd-annotation.js'
        return path.read_text()

    def test_toggle_logic_exists(self, jd_annotation_js):
        """Toggle logic should check if dimension is already selected."""
        # Should have toggle logic that checks current state
        assert "hasExplicitRelevance" in jd_annotation_js or "popoverState.relevance ===" in jd_annotation_js

    def test_check_auto_delete_method_exists(self, jd_annotation_js):
        """checkAutoDeleteAnnotation method should exist."""
        assert "checkAutoDeleteAnnotation" in jd_annotation_js

    def test_auto_delete_checks_all_dimensions(self, jd_annotation_js):
        """Auto-delete should check if all dimensions are unselected."""
        assert "hasExplicitRelevance" in jd_annotation_js
        assert "hasExplicitRequirement" in jd_annotation_js
        assert "hasExplicitPassion" in jd_annotation_js
        assert "hasExplicitIdentity" in jd_annotation_js

    def test_auto_delete_only_in_edit_mode(self, jd_annotation_js):
        """Auto-delete should only happen when editingAnnotationId exists."""
        assert "editingAnnotationId" in jd_annotation_js


# ==============================================================================
# GAP-108: Batch Annotation Delete Context
# ==============================================================================

class TestBatchAnnotationContext:
    """Tests for GAP-108: Batch page annotation delete uses correct context."""

    @pytest.fixture
    def jd_annotation_js(self):
        """Read jd-annotation.js content."""
        path = Path(__file__).parent.parent.parent / 'frontend/static/js/jd-annotation.js'
        return path.read_text()

    def test_get_active_annotation_manager_exists(self, jd_annotation_js):
        """getActiveAnnotationManager function should exist."""
        assert "getActiveAnnotationManager" in jd_annotation_js

    def test_onclick_uses_active_manager(self, jd_annotation_js):
        """Delete onclick handlers should use getActiveAnnotationManager()."""
        assert "getActiveAnnotationManager()?.deleteAnnotation" in jd_annotation_js

    def test_batch_manager_reference_exists(self, jd_annotation_js):
        """Should reference batchAnnotationManager for batch context."""
        assert "batchAnnotationManager" in jd_annotation_js


# ==============================================================================
# GAP-109: Skill Color Timing Fix
# ==============================================================================

class TestSkillColorTiming:
    """Tests for GAP-109: requestAnimationFrame for applyHighlights."""

    @pytest.fixture
    def jd_annotation_js(self):
        """Read jd-annotation.js content."""
        path = Path(__file__).parent.parent.parent / 'frontend/static/js/jd-annotation.js'
        return path.read_text()

    def test_apply_highlights_uses_raf(self, jd_annotation_js):
        """applyHighlights should use requestAnimationFrame."""
        assert "requestAnimationFrame" in jd_annotation_js

    def test_raf_wraps_apply_highlights_call(self, jd_annotation_js):
        """requestAnimationFrame should wrap applyHighlights call."""
        assert "requestAnimationFrame(() =>" in jd_annotation_js
        # Should have applyHighlights inside RAF
        raf_index = jd_annotation_js.find("requestAnimationFrame(() =>")
        next_500_chars = jd_annotation_js[raf_index:raf_index+500]
        assert "applyHighlights" in next_500_chars


# ==============================================================================
# GAP-100: CV Editor idPrefix Support
# ==============================================================================

class TestCVEditorIdPrefix:
    """Tests for GAP-100: CVEditor accepts idPrefix option."""

    @pytest.fixture
    def cv_editor_js(self):
        """Read cv-editor.js content."""
        path = Path(__file__).parent.parent.parent / 'frontend/static/js/cv-editor.js'
        return path.read_text()

    def test_constructor_accepts_options(self, cv_editor_js):
        """Constructor should accept options parameter."""
        assert "options = {}" in cv_editor_js

    def test_id_prefix_defaults_to_cv(self, cv_editor_js):
        """idPrefix should default to 'cv' if not provided."""
        assert "options.idPrefix || 'cv'" in cv_editor_js

    def test_get_element_method_exists(self, cv_editor_js):
        """getElement() method should exist."""
        assert "getElement(suffix)" in cv_editor_js

    def test_get_element_uses_id_prefix(self, cv_editor_js):
        """getElement() should use configured idPrefix."""
        assert "${this.idPrefix}-${suffix}" in cv_editor_js

    def test_batch_sidebars_uses_prefix(self):
        """batch-sidebars.js should use idPrefix: 'batch-cv'."""
        path = Path(__file__).parent.parent.parent / 'frontend/static/js/batch-sidebars.js'
        content = path.read_text()
        assert "idPrefix: 'batch-cv'" in content


# ==============================================================================
# GAP-102: Application URL Button
# ==============================================================================

class TestApplicationURLButton:
    """Tests for GAP-102: Application URL button conditional rendering."""

    @pytest.fixture
    def job_detail_template(self):
        """Read job_detail.html template."""
        path = Path(__file__).parent.parent.parent / 'frontend/templates/job_detail.html'
        return path.read_text()

    def test_apply_button_has_conditional_rendering(self, job_detail_template):
        """Apply button should have conditional check for application_url."""
        assert "{% if job.application_url" in job_detail_template

    def test_apply_button_href_uses_application_url(self, job_detail_template):
        """Apply button href should use job.application_url."""
        assert "{{ job.application_url }}" in job_detail_template

    def test_apply_button_opens_in_new_tab(self, job_detail_template):
        """Apply button should open in new tab with security attributes."""
        assert 'target="_blank"' in job_detail_template
        assert 'rel="noopener noreferrer"' in job_detail_template


# ==============================================================================
# GAP-112: Batch Pipeline Popups Removed
# ==============================================================================

class TestBatchPipelinePopupsRemoved:
    """Tests for GAP-112: No confirm() popups in batch operations."""

    @pytest.fixture
    def batch_template(self):
        """Read batch_processing.html template."""
        path = Path(__file__).parent.parent.parent / 'frontend/templates/batch_processing.html'
        return path.read_text()

    @pytest.fixture
    def batch_job_rows(self):
        """Read batch_job_rows.html partial."""
        path = Path(__file__).parent.parent.parent / 'frontend/templates/partials/batch_job_rows.html'
        return path.read_text()

    def test_no_confirm_in_execute_batch_operation(self, batch_template):
        """executeBatchOperation should not use confirm()."""
        # Find the function and check it doesn't have confirm
        if "function executeBatchOperation" in batch_template:
            func_start = batch_template.find("function executeBatchOperation")
            func_section = batch_template[func_start:func_start+2000]
            assert "confirm(" not in func_section

    def test_no_confirm_in_scrape_and_fill(self, batch_job_rows):
        """scrapeAndFillJob should not use confirm()."""
        if "function scrapeAndFillJob" in batch_job_rows:
            func_start = batch_job_rows.find("function scrapeAndFillJob")
            func_section = batch_job_rows[func_start:func_start+1000]
            assert "confirm(" not in func_section

    def test_no_confirm_in_process_single_job(self, batch_job_rows):
        """processSingleBatchJob should not use confirm()."""
        if "function processSingleBatchJob" in batch_job_rows:
            func_start = batch_job_rows.find("function processSingleBatchJob")
            func_section = batch_job_rows[func_start:func_start+1000]
            assert "confirm(" not in func_section
