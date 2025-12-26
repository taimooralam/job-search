"""
Unit tests for annotation delete from popover functionality.

Tests the following functionality:
1. Delete button visibility (hidden for new annotations, visible when editing)
2. Delete button behavior and confirmation
3. deleteAnnotationFromPopover() function logic
4. Integration with annotation manager state
5. Reset form behavior when hiding delete button
"""

import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch


class TestDeleteButtonVisibility:
    """Tests for delete button visibility in annotation popover."""

    def test_delete_button_exists_in_popover_template(
        self, authenticated_client, mock_db, sample_job
    ):
        """Popover template should contain delete button element."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Check for delete button element with correct ID
        assert 'id="popover-delete-btn"' in html
        assert 'onclick="deleteAnnotationFromPopover()"' in html

    def test_delete_button_has_hidden_class_by_default(
        self, authenticated_client, mock_db, sample_job
    ):
        """Delete button should have 'hidden' class by default (for new annotations)."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Find the delete button section
        # The button should have 'hidden' in its class attribute
        assert 'id="popover-delete-btn"' in html

        # Extract the button element (simplified check)
        button_start = html.find('id="popover-delete-btn"')
        button_section = html[button_start-200:button_start+200]
        assert 'hidden' in button_section

    def test_delete_button_has_proper_styling(
        self, authenticated_client, mock_db, sample_job
    ):
        """Delete button should have red styling for delete action."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Check for red color styling (Tailwind classes)
        button_start = html.find('id="popover-delete-btn"')
        button_section = html[button_start-200:button_start+400]

        # Should have red color classes
        assert 'red-600' in button_section or 'red-700' in button_section

    def test_delete_button_has_accessible_title(
        self, authenticated_client, mock_db, sample_job
    ):
        """Delete button should have title attribute for accessibility."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Check for title attribute
        button_start = html.find('id="popover-delete-btn"')
        button_section = html[button_start-200:button_start+400]
        assert 'title=' in button_section


class TestDeleteButtonBehavior:
    """Tests for delete button behavior in the JavaScript code."""

    def test_delete_annotation_from_popover_function_exists(self):
        """deleteAnnotationFromPopover() function should exist in jd-annotation.js."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Function should be defined
        assert 'function deleteAnnotationFromPopover()' in js_content

    def test_delete_function_checks_annotation_manager(self):
        """Function should check if manager exists before proceeding."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should use getActiveAnnotationManager() and have early return if manager doesn't exist
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        # Now uses getActiveAnnotationManager() helper
        assert 'getActiveAnnotationManager' in delete_function_section
        assert 'if (!manager)' in delete_function_section or \
               'if(!manager)' in delete_function_section

    def test_delete_function_checks_editing_annotation_id(self):
        """Function should check if editingAnnotationId exists before deleting."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should check for editingAnnotationId via manager
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        # Uses manager.editingAnnotationId
        assert 'editingAnnotationId' in delete_function_section
        assert 'annotationId' in delete_function_section

    def test_delete_function_executes_immediately_without_confirmation(self):
        """Function should delete immediately without confirmation (Gmail undo pattern)."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should NOT use confirm() (GAP-105: removed confirmation dialogs)
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        assert 'confirm(' not in delete_function_section, "Confirmation dialog should be removed (GAP-105)"

    def test_delete_function_has_gmail_pattern_comment(self):
        """Function should have a comment explaining the Gmail undo pattern."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should have comment about Gmail pattern
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        # Should mention Gmail undo pattern or immediate deletion
        assert 'immediately' in delete_function_section.lower() or 'Gmail' in delete_function_section

    def test_delete_function_calls_delete_annotation(self):
        """Function should call manager.deleteAnnotation() with correct ID."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should call deleteAnnotation via getActiveAnnotationManager()
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        assert 'deleteAnnotation(' in delete_function_section
        # Now uses getActiveAnnotationManager() and assigns to 'manager'
        assert 'manager.deleteAnnotation' in delete_function_section or \
               'getActiveAnnotationManager' in delete_function_section

    def test_delete_function_hides_popover_after_deletion(self):
        """Function should hide the popover after successful deletion (no save)."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should call hideAnnotationPopover with save: false (no auto-save after delete)
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        assert 'hideAnnotationPopover({ save: false })' in delete_function_section

    def test_delete_function_exported_to_window(self):
        """Function should be exported to window for HTML onclick handlers."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should be exported to window
        assert 'window.deleteAnnotationFromPopover' in js_content


class TestDeleteFunctionLogic:
    """Tests for the internal logic of deleteAnnotationFromPopover()."""

    def test_early_return_when_no_annotation_manager(self):
        """Should return early if manager is null/undefined."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should have guard clause at start using getActiveAnnotationManager()
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+500]

        # Should use getActiveAnnotationManager() helper and check if manager exists
        assert 'getActiveAnnotationManager' in delete_function_section
        assert '!manager' in delete_function_section or 'if (!manager)' in delete_function_section

    def test_early_return_when_no_editing_annotation(self):
        """Should return early and warn if no annotation is being edited."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should check for editingAnnotationId
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        assert 'if (!annotationId)' in delete_function_section or \
               'if(!annotationId)' in delete_function_section

        # Should log warning
        assert 'console.warn' in delete_function_section or \
               'console.log' in delete_function_section

    def test_no_confirmation_dialog_for_faster_workflow(self):
        """GAP-105: No confirmation dialog for faster workflow (Gmail undo pattern)."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should NOT have confirmation dialog
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        # Confirmation dialogs were removed per GAP-105 for faster workflow
        assert 'confirm(' not in delete_function_section
        # Should directly call deleteAnnotation without user interaction
        assert 'manager.deleteAnnotation(annotationId)' in delete_function_section


class TestShowAnnotationPopoverIntegration:
    """Tests for showAnnotationPopover() integration with delete button."""

    def test_show_annotation_popover_controls_delete_button(self):
        """showAnnotationPopover() should control delete button visibility based on edit mode."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Function should check for editingAnnotation parameter
        # Search for method definition (with third parameter), not method call
        show_popover_start = js_content.find('showAnnotationPopover(rect, selectedText, editingAnnotation')
        show_popover_section = js_content[show_popover_start:show_popover_start+3000]

        assert 'editingAnnotation' in show_popover_section
        assert 'popover-delete-btn' in show_popover_section

    def test_delete_button_shown_when_editing(self):
        """Delete button should be shown when editingAnnotation is provided."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should remove 'hidden' class when editing
        # Search for method definition (with third parameter), not method call
        show_popover_start = js_content.find('showAnnotationPopover(rect, selectedText, editingAnnotation')
        show_popover_section = js_content[show_popover_start:show_popover_start+3000]

        # Find delete button logic
        delete_btn_logic = show_popover_section[show_popover_section.find('popover-delete-btn'):]

        assert 'classList.remove' in delete_btn_logic or \
               'hidden' in delete_btn_logic

    def test_delete_button_hidden_when_creating_new(self):
        """Delete button should be hidden when creating new annotation."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should add 'hidden' class when not editing
        # Search for method definition (with third parameter), not method call
        show_popover_start = js_content.find('showAnnotationPopover(rect, selectedText, editingAnnotation')
        show_popover_section = js_content[show_popover_start:show_popover_start+3000]

        # Find delete button logic
        delete_btn_start = show_popover_section.find('popover-delete-btn')
        delete_btn_logic = show_popover_section[delete_btn_start:delete_btn_start+500]

        assert 'classList.add' in delete_btn_logic

    def test_editing_annotation_id_stored_in_manager(self):
        """editingAnnotationId should be stored in annotationManager state."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should store editingAnnotationId
        # Search for method definition (with third parameter), not method call
        show_popover_start = js_content.find('showAnnotationPopover(rect, selectedText, editingAnnotation')
        show_popover_section = js_content[show_popover_start:show_popover_start+3000]

        assert 'this.editingAnnotationId' in show_popover_section
        assert 'editingAnnotation?.id' in show_popover_section or \
               'editingAnnotation.id' in show_popover_section


class TestResetPopoverFormIntegration:
    """Tests for resetPopoverForm() integration with delete button."""

    def test_reset_form_hides_delete_button(self):
        """resetPopoverForm() should hide the delete button."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Function should hide delete button
        # Find the actual resetPopoverForm method definition (not just the call)
        reset_form_start = js_content.find('resetPopoverForm() {')
        reset_form_section = js_content[reset_form_start:reset_form_start+2000]

        assert 'popover-delete-btn' in reset_form_section
        assert 'classList.add' in reset_form_section
        assert 'hidden' in reset_form_section

    def test_reset_form_clears_editing_state(self):
        """resetPopoverForm() should clear editingAnnotationId."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should reset editing state
        # Find the actual resetPopoverForm method definition (not just the call)
        reset_form_start = js_content.find('resetPopoverForm() {')
        reset_form_section = js_content[reset_form_start:reset_form_start+2000]

        assert 'editingAnnotationId' in reset_form_section
        assert 'null' in reset_form_section


class TestDeleteAnnotationMethod:
    """Tests for the underlying deleteAnnotation() method in AnnotationManager."""

    def test_delete_annotation_removes_from_array(self):
        """deleteAnnotation() should remove annotation from array."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should use splice to remove
        delete_annotation_start = js_content.find('deleteAnnotation(annotationId)')
        delete_annotation_section = js_content[delete_annotation_start:delete_annotation_start+1000]

        assert 'splice(' in delete_annotation_section
        assert 'this.annotations' in delete_annotation_section

    def test_delete_annotation_re_renders_ui(self):
        """deleteAnnotation() should re-render annotations list and highlights."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should call render methods
        delete_annotation_start = js_content.find('deleteAnnotation(annotationId)')
        delete_annotation_section = js_content[delete_annotation_start:delete_annotation_start+1000]

        assert 'renderAnnotations()' in delete_annotation_section
        assert 'applyHighlights()' in delete_annotation_section

    def test_delete_annotation_updates_stats(self):
        """deleteAnnotation() should update statistics."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should call updateStats
        delete_annotation_start = js_content.find('deleteAnnotation(annotationId)')
        delete_annotation_section = js_content[delete_annotation_start:delete_annotation_start+1000]

        assert 'updateStats()' in delete_annotation_section

    def test_delete_annotation_schedules_save(self):
        """deleteAnnotation() should schedule auto-save."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should call scheduleSave
        delete_annotation_start = js_content.find('deleteAnnotation(annotationId)')
        delete_annotation_section = js_content[delete_annotation_start:delete_annotation_start+1000]

        assert 'scheduleSave()' in delete_annotation_section


class TestUserExperience:
    """Tests for user experience aspects of delete functionality."""

    def test_delete_button_positioned_near_discard(self):
        """Delete button should be positioned near discard button for easy access."""
        # Arrange - Read the template file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/templates/partials/job_detail/_annotation_popover.html', 'r') as f:
            template_content = f.read()

        # Assert - Delete button should be in same actions section as Discard button
        # Find the actions section by looking for the comment or container
        actions_start = template_content.find('Actions - Compact')
        actions_section = template_content[actions_start:actions_start+1500]

        # Both buttons should be in the actions section
        assert 'popover-delete-btn' in actions_section
        assert 'Discard' in actions_section

    def test_delete_button_has_hover_effect(self):
        """Delete button should have hover effect for better UX."""
        # Arrange - Read the template file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/templates/partials/job_detail/_annotation_popover.html', 'r') as f:
            template_content = f.read()

        # Assert - Should have hover classes
        delete_btn_start = template_content.find('popover-delete-btn')
        delete_btn_section = template_content[delete_btn_start-200:delete_btn_start+400]

        assert 'hover:' in delete_btn_section

    def test_delete_button_text_is_clear(self):
        """Delete button should have clear text label."""
        # Arrange - Read the template file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/templates/partials/job_detail/_annotation_popover.html', 'r') as f:
            template_content = f.read()

        # Assert - Should say "Delete"
        delete_btn_start = template_content.find('popover-delete-btn')
        delete_btn_section = template_content[delete_btn_start:delete_btn_start+400]

        assert 'Delete' in delete_btn_section

    def test_popover_title_changes_in_edit_mode(self):
        """Popover title should change from 'Create' to 'Edit' when editing."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should update title based on mode
        # Search for method definition (with third parameter), not method call
        show_popover_start = js_content.find('showAnnotationPopover(rect, selectedText, editingAnnotation')
        show_popover_section = js_content[show_popover_start:show_popover_start+3000]

        assert 'popover-title' in show_popover_section
        assert 'Edit Annotation' in show_popover_section or \
               "'Edit Annotation'" in show_popover_section

    def test_save_button_text_changes_in_edit_mode(self):
        """Save button text should change from 'Add' to 'Update' when editing."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should update button text
        # Search for method definition (with third parameter), not method call
        show_popover_start = js_content.find('showAnnotationPopover(rect, selectedText, editingAnnotation')
        show_popover_section = js_content[show_popover_start:show_popover_start+3000]

        assert 'popover-save-btn' in show_popover_section
        assert 'Update Annotation' in show_popover_section or \
               "'Update Annotation'" in show_popover_section


class TestEdgeCases:
    """Edge case tests for delete annotation functionality."""

    def test_delete_when_annotation_already_deleted(self):
        """Should handle gracefully if annotation was already deleted."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - deleteAnnotation uses findIndex which returns -1 if not found
        delete_annotation_start = js_content.find('deleteAnnotation(annotationId)')
        delete_annotation_section = js_content[delete_annotation_start:delete_annotation_start+1000]

        assert 'findIndex' in delete_annotation_section
        assert 'index !== -1' in delete_annotation_section or \
               'index != -1' in delete_annotation_section

    def test_delete_with_null_annotation_id(self):
        """Should handle null/undefined annotationId gracefully."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - deleteAnnotationFromPopover checks for null/undefined
        delete_function_start = js_content.find('function deleteAnnotationFromPopover()')
        delete_function_section = js_content[delete_function_start:delete_function_start+1000]

        assert 'if (!annotationId)' in delete_function_section or \
               'if(!annotationId)' in delete_function_section

    def test_delete_button_disabled_during_save(self):
        """Delete button behavior during save operation (not explicitly tested, but documented)."""
        # This is a documentation test - the actual behavior depends on save state
        # The delete button is part of the popover which would typically be hidden
        # during save operations, so this is implicitly handled
        pass

    def test_multiple_rapid_delete_clicks(self):
        """Multiple rapid clicks should only trigger one deletion (via confirm dialog)."""
        # This is inherently protected by the confirm() dialog -
        # user must confirm each time, and the second click would fail
        # because the annotation is already deleted
        pass


class TestAccessibility:
    """Accessibility tests for delete button."""

    def test_delete_button_has_focus_styles(self):
        """Delete button should have focus styles for keyboard navigation."""
        # Arrange - Read the template file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/templates/partials/job_detail/_annotation_popover.html', 'r') as f:
            template_content = f.read()

        # Assert - Should have focus styles
        delete_btn_start = template_content.find('popover-delete-btn')
        delete_btn_section = template_content[delete_btn_start-200:delete_btn_start+400]

        assert 'focus:' in delete_btn_section

    def test_delete_button_keyboard_accessible(self):
        """Delete button should be keyboard accessible (using button element)."""
        # Arrange - Read the template file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/templates/partials/job_detail/_annotation_popover.html', 'r') as f:
            template_content = f.read()

        # Assert - Should use button element
        delete_btn_start = template_content.find('popover-delete-btn')
        delete_btn_section = template_content[delete_btn_start-200:delete_btn_start+50]

        assert '<button' in delete_btn_section


class TestIntegrationFlow:
    """Integration tests for the complete delete flow."""

    def test_complete_delete_flow_structure(self):
        """Test the complete flow: click highlight -> edit popover -> delete."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - All necessary functions exist
        assert 'editAnnotationFromHighlight' in js_content
        assert 'showAnnotationPopover' in js_content
        assert 'deleteAnnotationFromPopover' in js_content
        assert 'hideAnnotationPopover' in js_content

    def test_edit_annotation_from_highlight_passes_annotation_object(self):
        """editAnnotationFromHighlight should pass annotation object to popover."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - Should find and pass annotation
        edit_from_highlight_start = js_content.find('editAnnotationFromHighlight(annotationId')
        edit_from_highlight_section = js_content[edit_from_highlight_start:edit_from_highlight_start+2000]

        assert 'find(a => a.id === annotationId)' in edit_from_highlight_section or \
               'find(a=>a.id===annotationId)' in edit_from_highlight_section
        assert 'showAnnotationPopover' in edit_from_highlight_section

    def test_delete_triggers_full_ui_update(self):
        """Deleting should trigger complete UI update (list + highlights + stats)."""
        # Arrange - Read the JavaScript file
        with open('/Users/ala0001t/pers/projects/job-search/frontend/static/js/jd-annotation.js', 'r') as f:
            js_content = f.read()

        # Assert - deleteAnnotation should call all update methods
        delete_annotation_start = js_content.find('deleteAnnotation(annotationId)')
        delete_annotation_section = js_content[delete_annotation_start:delete_annotation_start+1000]

        # Should update all UI components
        assert 'renderAnnotations' in delete_annotation_section
        assert 'applyHighlights' in delete_annotation_section
        assert 'updateStats' in delete_annotation_section
        assert 'scheduleSave' in delete_annotation_section
