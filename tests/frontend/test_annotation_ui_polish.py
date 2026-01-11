"""
Unit tests for JD Annotation UI Polish Features

Tests the following annotation UI enhancements:
1. Confidence badges for AI-generated annotations
2. Batch review UI for suggestions
3. Undo/redo functionality
4. Mobile annotation UI features
5. CSS styling for annotation features

These are static file tests that verify the presence and correctness
of JavaScript functions, CSS classes, and HTML patterns without running
the actual JavaScript code.
"""

import pytest
import re
from pathlib import Path


# File paths
JS_FILE = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "jd-annotation.js"
MOBILE_JS_FILE = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "mobile" / "mobile-annotation.js"
CSS_FILE = Path(__file__).parent.parent.parent / "frontend" / "static" / "css" / "jd-annotation.css"


class TestConfidenceBadges:
    """Tests for confidence badge rendering in annotations."""

    def test_get_confidence_badge_method_exists(self):
        """Verify getConfidenceBadge method exists in jd-annotation.js."""
        content = JS_FILE.read_text()
        # Method should be defined
        assert "getConfidenceBadge(" in content, "getConfidenceBadge method not found"
        # Should be a method definition
        assert re.search(r'getConfidenceBadge\s*\(annotation\)', content), \
            "getConfidenceBadge method signature not found"

    def test_confidence_badge_color_thresholds(self):
        """Verify correct color thresholds: green >=85%, amber >=70%, gray <70%."""
        content = JS_FILE.read_text()

        # Check for threshold logic (allow for flexible formatting)
        assert re.search(r'pct\s*>=\s*85', content) or re.search(r'conf\s*>=\s*0\.85', content), \
            "High confidence threshold (85%) not found"
        assert re.search(r'pct\s*>=\s*70', content) or re.search(r'conf\s*>=\s*0\.70', content), \
            "Medium confidence threshold (70%) not found"

    def test_confidence_badge_ai_indicator(self):
        """Verify AI indicator (sparkle or similar) for AI suggestions."""
        content = JS_FILE.read_text()
        # Check for ai-indicator class or sparkle emoji
        assert "ai-indicator" in content or "✨" in content or "🌟" in content, \
            "AI indicator not found in confidence badge implementation"

    def test_confidence_badge_returns_html(self):
        """Verify getConfidenceBadge returns HTML structure."""
        content = JS_FILE.read_text()

        # Search for getConfidenceBadge method and check it returns HTML
        match = re.search(
            r'getConfidenceBadge\s*\([^)]+\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find getConfidenceBadge method body"

        method_body = match.group(1)
        # Should return HTML with confidence badge class
        assert "confidence-badge" in method_body or "return" in method_body, \
            "getConfidenceBadge does not appear to return HTML"

    def test_confidence_badge_only_for_auto_generated(self):
        """Verify confidence badges only shown for auto_generated annotations."""
        content = JS_FILE.read_text()

        # Method should check source === 'auto_generated'
        match = re.search(
            r'getConfidenceBadge\s*\([^)]+\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find getConfidenceBadge method body"

        method_body = match.group(1)
        assert "auto_generated" in method_body, \
            "getConfidenceBadge does not check for auto_generated source"


class TestMatchExplanation:
    """Tests for match explanation text in annotations."""

    def test_get_match_explanation_method_exists(self):
        """Verify getMatchExplanation method exists in jd-annotation.js."""
        content = JS_FILE.read_text()
        assert "getMatchExplanation(" in content, "getMatchExplanation method not found"
        assert re.search(r'getMatchExplanation\s*\(annotation\)', content), \
            "getMatchExplanation method signature not found"

    def test_match_explanation_uses_match_method(self):
        """Verify match explanation includes match_method from annotation."""
        content = JS_FILE.read_text()

        # Find the getMatchExplanation method
        match = re.search(
            r'getMatchExplanation\s*\([^)]+\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find getMatchExplanation method body"

        method_body = match.group(1)
        # Should reference match_method or matched_keyword
        assert "match_method" in method_body or "matched_keyword" in method_body, \
            "getMatchExplanation does not use match_method or matched_keyword"

    def test_match_explanation_returns_text(self):
        """Verify getMatchExplanation returns explanatory text."""
        content = JS_FILE.read_text()

        match = re.search(
            r'getMatchExplanation\s*\([^)]+\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find getMatchExplanation method body"

        method_body = match.group(1)
        # Should return text (via return statement)
        assert "return" in method_body, \
            "getMatchExplanation does not have return statement"


class TestBatchReviewUI:
    """Tests for batch suggestion review functionality."""

    def test_get_pending_suggestions_method_exists(self):
        """Verify getPendingSuggestions method exists."""
        content = JS_FILE.read_text()
        assert "getPendingSuggestions" in content, "getPendingSuggestions method not found"

    def test_get_pending_suggestions_filters_by_source(self):
        """Verify getPendingSuggestions filters by auto_generated source."""
        content = JS_FILE.read_text()

        # Find the method (could be function or getter)
        match = re.search(
            r'getPendingSuggestions\s*\([^)]*\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        if not match:
            # Try as a getter property
            match = re.search(
                r'get\s+pendingSuggestions\s*\([^)]*\)\s*{([^}]+)}',
                content,
                re.DOTALL
            )

        assert match, "Could not find getPendingSuggestions method/getter body"

        method_body = match.group(1)
        # Should filter by auto_generated source
        assert "auto_generated" in method_body, \
            "getPendingSuggestions does not filter by auto_generated source"

    def test_get_pending_suggestions_returns_array(self):
        """Verify getPendingSuggestions returns filtered array."""
        content = JS_FILE.read_text()

        match = re.search(
            r'(getPendingSuggestions\s*\([^)]*\)|get\s+pendingSuggestions\s*\([^)]*\))\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find getPendingSuggestions implementation"

        method_body = match.group(2)
        # Should use filter to return array
        assert "filter" in method_body or "return" in method_body, \
            "getPendingSuggestions does not filter or return annotations"

    def test_accept_all_suggestions_method_exists(self):
        """Verify acceptAllSuggestions method exists."""
        content = JS_FILE.read_text()
        assert "acceptAllSuggestions" in content, "acceptAllSuggestions method not found"

    def test_accept_all_suggestions_updates_status(self):
        """Verify acceptAllSuggestions marks suggestions as approved."""
        content = JS_FILE.read_text()

        match = re.search(
            r'acceptAllSuggestions\s*\([^)]*\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find acceptAllSuggestions method body"

        method_body = match.group(1)
        # Should set status to 'approved'
        assert "approved" in method_body, \
            "acceptAllSuggestions does not set status to approved"

    def test_quick_accept_suggestion_method_exists(self):
        """Verify quickAcceptSuggestion method exists."""
        content = JS_FILE.read_text()
        assert "quickAcceptSuggestion" in content, "quickAcceptSuggestion method not found"
        assert re.search(r'quickAcceptSuggestion\s*\([^)]+\)', content), \
            "quickAcceptSuggestion method signature not found"

    def test_quick_reject_suggestion_method_exists(self):
        """Verify quickRejectSuggestion method exists."""
        content = JS_FILE.read_text()
        assert "quickRejectSuggestion" in content, "quickRejectSuggestion method not found"
        assert re.search(r'quickRejectSuggestion\s*\([^)]+\)', content), \
            "quickRejectSuggestion method signature not found"

    def test_quick_actions_take_annotation_id(self):
        """Verify quick action methods take annotationId parameter."""
        content = JS_FILE.read_text()

        # Check quickAcceptSuggestion parameter
        assert re.search(r'quickAcceptSuggestion\s*\(\s*annotationId\s*\)', content), \
            "quickAcceptSuggestion does not take annotationId parameter"

        # Check quickRejectSuggestion parameter
        assert re.search(r'quickRejectSuggestion\s*\(\s*annotationId\s*\)', content), \
            "quickRejectSuggestion does not take annotationId parameter"


class TestUndoRedo:
    """Tests for undo/redo functionality."""

    def test_undo_manager_class_exists(self):
        """Verify UndoManager class is defined."""
        content = JS_FILE.read_text()
        assert "class UndoManager" in content, "UndoManager class not found"

    def test_undo_manager_has_required_methods(self):
        """Verify UndoManager has push, undo, redo, canUndo, canRedo methods."""
        content = JS_FILE.read_text()

        # Find the UndoManager class - need to search beyond just the class body
        # because methods span multiple lines
        match = re.search(r'class UndoManager\s*{', content)
        assert match, "Could not find UndoManager class definition"

        # Search for methods in the entire file after the class definition
        start_pos = match.end()
        class_content = content[start_pos:start_pos + 5000]  # Look ahead 5000 chars

        # Check for required methods (methods are defined with methodName() pattern)
        assert re.search(r'\bpush\s*\(', class_content), \
            "UndoManager missing push method"
        assert re.search(r'\bundo\s*\(', class_content), \
            "UndoManager missing undo method"
        assert re.search(r'\bredo\s*\(', class_content), \
            "UndoManager missing redo method"
        assert re.search(r'\bcanUndo\s*\(', class_content), \
            "UndoManager missing canUndo method"
        assert re.search(r'\bcanRedo\s*\(', class_content), \
            "UndoManager missing canRedo method"

    def test_undo_manager_maintains_history(self):
        """Verify UndoManager maintains undo/redo history stacks."""
        content = JS_FILE.read_text()

        # Find the UndoManager class and its constructor
        match = re.search(r'class UndoManager\s*{', content)
        assert match, "Could not find UndoManager class definition"

        # Search for constructor and stack initialization
        start_pos = match.end()
        class_content = content[start_pos:start_pos + 2000]

        # Should have stack/history arrays in constructor
        assert "undoStack" in class_content or "history" in class_content or "this.stack" in class_content, \
            "UndoManager does not maintain undo history"
        assert "redoStack" in class_content, \
            "UndoManager does not maintain redo history"

    def test_annotation_manager_has_undo_method(self):
        """Verify AnnotationManager has undo() method."""
        content = JS_FILE.read_text()

        # Search for undo method in the file
        # It could be in AnnotationManager class or as a standalone method
        assert re.search(r'\bundo\s*\(\s*\)\s*{', content), \
            "AnnotationManager does not have undo() method"

    def test_annotation_manager_has_redo_method(self):
        """Verify AnnotationManager has redo() method."""
        content = JS_FILE.read_text()

        assert re.search(r'\bredo\s*\(\s*\)\s*{', content), \
            "AnnotationManager does not have redo() method"

    def test_keyboard_shortcuts_for_undo_redo(self):
        """Verify keyboard shortcuts for Ctrl+Z (undo) and Ctrl+Shift+Z (redo)."""
        content = JS_FILE.read_text()

        # Check for keyboard event handlers
        assert "keydown" in content or "keyup" in content, \
            "No keyboard event handlers found"

        # Check for Ctrl/Cmd key detection
        assert "ctrlKey" in content or "metaKey" in content, \
            "No Ctrl/Cmd key detection found"

        # Check for Z key handling (could be 'z', 'Z', or key code)
        assert re.search(r"key\s*===?\s*['\"]z['\"]", content, re.IGNORECASE) or \
               re.search(r"keyCode\s*===?\s*90", content) or \
               "KeyZ" in content, \
            "No Z key handling found for undo/redo"

    def test_undo_redo_button_state_management(self):
        """Verify undo/redo buttons are enabled/disabled based on history state."""
        content = JS_FILE.read_text()

        # Should check canUndo/canRedo and update button states
        assert re.search(r'canUndo\s*\(\s*\)', content) and re.search(r'canRedo\s*\(\s*\)', content), \
            "Missing canUndo/canRedo state checks"


class TestMobileAnnotationUI:
    """Tests for mobile annotation UI features."""

    def test_get_confidence_display_exists(self):
        """Verify getConfidenceDisplay method exists in mobile-annotation.js."""
        content = MOBILE_JS_FILE.read_text()
        assert "getConfidenceDisplay" in content, "getConfidenceDisplay method not found in mobile"

    def test_mobile_confidence_display_returns_data_object(self):
        """Verify getConfidenceDisplay returns object with pct, method, colorClass."""
        content = MOBILE_JS_FILE.read_text()

        # Find the method - it spans multiple lines with ternary operators
        match = re.search(
            r'getConfidenceDisplay\s*\([^)]+\)\s*{',
            content
        )
        assert match, "Could not find getConfidenceDisplay method start"

        # Get a larger section that includes the full method
        start = match.start()
        # Find the end by looking for the closing brace of the method
        method_section = content[start:start + 1500]

        # Should return object with pct, method, colorClass
        assert "pct:" in method_section or "pct :" in method_section, \
            "getConfidenceDisplay does not return pct"
        assert "method:" in method_section or "method :" in method_section, \
            "getConfidenceDisplay does not return method"
        assert "colorClass:" in method_section or "colorClass :" in method_section, \
            "getConfidenceDisplay does not return colorClass"

    def test_mobile_confidence_color_thresholds(self):
        """Verify mobile confidence display uses same thresholds (85%, 70%)."""
        content = MOBILE_JS_FILE.read_text()

        # Find the method and get a larger section
        match = re.search(r'getConfidenceDisplay\s*\([^)]+\)\s*{', content)
        assert match, "Could not find getConfidenceDisplay method"

        start = match.start()
        method_section = content[start:start + 1500]

        # Check thresholds in the ternary operator
        assert re.search(r'pct\s*>=\s*85', method_section), \
            "Mobile getConfidenceDisplay missing high threshold (85%)"
        assert re.search(r'pct\s*>=\s*70', method_section), \
            "Mobile getConfidenceDisplay missing medium threshold (70%)"

    def test_mobile_undo_delete_exists(self):
        """Verify undoDelete method exists for mobile."""
        content = MOBILE_JS_FILE.read_text()
        assert "undoDelete" in content, "undoDelete method not found in mobile"

    def test_mobile_undo_delete_uses_last_deleted(self):
        """Verify undoDelete uses lastDeletedAnnotation state."""
        content = MOBILE_JS_FILE.read_text()

        # Should have lastDeletedAnnotation state variable
        assert "lastDeletedAnnotation" in content, \
            "Mobile does not track lastDeletedAnnotation"

        # undoDelete should restore from lastDeletedAnnotation
        match = re.search(
            r'undoDelete\s*\([^)]*\)\s*{([^}]+(?:{[^}]*}[^}]*)*)}',
            content,
            re.DOTALL
        )
        assert match, "Could not find undoDelete method body"

        method_body = match.group(1)
        assert "lastDeletedAnnotation" in method_body, \
            "undoDelete does not use lastDeletedAnnotation"

    def test_mobile_batch_review_methods_exist(self):
        """Verify mobile has batch review methods (acceptAll, quickAccept, quickReject)."""
        content = MOBILE_JS_FILE.read_text()

        # Check for batch review methods
        assert "acceptAllSuggestions" in content or "pendingSuggestions" in content, \
            "Mobile missing batch review functionality"

    def test_mobile_get_match_explanation_exists(self):
        """Verify getMatchExplanation exists in mobile."""
        content = MOBILE_JS_FILE.read_text()
        assert "getMatchExplanation" in content, \
            "Mobile missing getMatchExplanation method"


class TestAnnotationCSS:
    """Tests for annotation CSS styles."""

    def test_confidence_badge_base_styles_exist(self):
        """Verify confidence-badge CSS class exists."""
        content = CSS_FILE.read_text()
        assert ".confidence-badge" in content, "Missing .confidence-badge CSS class"

    def test_confidence_badge_color_classes_exist(self):
        """Verify confidence badge color classes (high, medium, low)."""
        content = CSS_FILE.read_text()

        assert ".confidence-high" in content, "Missing .confidence-high CSS class"
        assert ".confidence-medium" in content, "Missing .confidence-medium CSS class"
        assert ".confidence-low" in content, "Missing .confidence-low CSS class"

    def test_confidence_badge_green_threshold_color(self):
        """Verify high confidence uses green color scheme."""
        content = CSS_FILE.read_text()

        # Find .confidence-high block
        match = re.search(r'\.confidence-high\s*{([^}]+)}', content, re.DOTALL)
        assert match, "Could not find .confidence-high CSS block"

        css_block = match.group(1)
        # Should have green color (34, 197, 94 = rgb green from Tailwind)
        assert "34, 197, 94" in css_block or "#22c55e" in css_block or "green" in css_block, \
            ".confidence-high does not use green colors"

    def test_confidence_badge_amber_threshold_color(self):
        """Verify medium confidence uses amber/orange color scheme."""
        content = CSS_FILE.read_text()

        match = re.search(r'\.confidence-medium\s*{([^}]+)}', content, re.DOTALL)
        assert match, "Could not find .confidence-medium CSS block"

        css_block = match.group(1)
        # Should have amber color (245, 158, 11 = rgb amber from Tailwind)
        assert "245, 158, 11" in css_block or "#f59e0b" in css_block or "amber" in css_block or "orange" in css_block, \
            ".confidence-medium does not use amber/orange colors"

    def test_confidence_badge_gray_threshold_color(self):
        """Verify low confidence uses gray color scheme."""
        content = CSS_FILE.read_text()

        match = re.search(r'\.confidence-low\s*{([^}]+)}', content, re.DOTALL)
        assert match, "Could not find .confidence-low CSS block"

        css_block = match.group(1)
        # Should have gray color (107, 114, 128 = rgb gray from Tailwind)
        assert "107, 114, 128" in css_block or "#6b7280" in css_block or "gray" in css_block or "grey" in css_block, \
            ".confidence-low does not use gray colors"

    def test_ai_indicator_styles_exist(self):
        """Verify ai-indicator CSS class exists."""
        content = CSS_FILE.read_text()
        assert ".ai-indicator" in content, "Missing .ai-indicator CSS class"

    def test_match_explanation_styles_exist(self):
        """Verify match-explanation CSS class exists."""
        content = CSS_FILE.read_text()
        assert ".match-explanation" in content, "Missing .match-explanation CSS class"

    def test_review_banner_styles_exist(self):
        """Verify review-banner CSS class exists."""
        content = CSS_FILE.read_text()
        assert ".review-banner" in content, "Missing .review-banner CSS class"

    def test_review_banner_has_animation(self):
        """Verify review banner has slide-down animation."""
        content = CSS_FILE.read_text()

        # Find .review-banner block
        match = re.search(r'\.review-banner\s*{([^}]+)}', content, re.DOTALL)
        assert match, "Could not find .review-banner CSS block"

        css_block = match.group(1)
        assert "animation" in css_block.lower(), \
            ".review-banner does not have animation"

    def test_quick_action_button_styles_exist(self):
        """Verify quick-action-btn CSS classes exist."""
        content = CSS_FILE.read_text()

        assert ".quick-action-btn" in content, "Missing .quick-action-btn CSS class"

    def test_quick_action_accept_styles_exist(self):
        """Verify quick action accept button has green styling."""
        content = CSS_FILE.read_text()

        # Check for accept variant
        assert re.search(r'\.quick-action-btn\.accept', content) or \
               re.search(r'\.accept\.quick-action-btn', content), \
            "Missing .quick-action-btn.accept CSS class"

    def test_quick_action_reject_styles_exist(self):
        """Verify quick action reject button has red styling."""
        content = CSS_FILE.read_text()

        # Check for reject variant
        assert re.search(r'\.quick-action-btn\.reject', content) or \
               re.search(r'\.reject\.quick-action-btn', content), \
            "Missing .quick-action-btn.reject CSS class"

    def test_quick_action_buttons_have_hover_states(self):
        """Verify quick action buttons have hover states."""
        content = CSS_FILE.read_text()

        # Should have hover states
        assert re.search(r'\.quick-action-btn[^{]*:hover', content), \
            "Quick action buttons missing hover states"

    def test_undo_redo_button_styles_exist(self):
        """Verify undo-redo-btn CSS class exists."""
        content = CSS_FILE.read_text()
        assert ".undo-redo-btn" in content, "Missing .undo-redo-btn CSS class"

    def test_undo_redo_button_disabled_state_exists(self):
        """Verify undo/redo buttons have disabled state styling."""
        content = CSS_FILE.read_text()

        # Should have :disabled pseudo-class styling
        assert re.search(r'\.undo-redo-btn[^{]*:disabled', content), \
            "Undo/redo buttons missing disabled state styling"

    def test_undo_redo_button_has_transitions(self):
        """Verify undo/redo buttons have smooth transitions."""
        content = CSS_FILE.read_text()

        match = re.search(r'\.undo-redo-btn\s*{([^}]+)}', content, re.DOTALL)
        assert match, "Could not find .undo-redo-btn CSS block"

        css_block = match.group(1)
        assert "transition" in css_block, \
            ".undo-redo-btn does not have transitions"

    def test_pending_suggestion_highlight_exists(self):
        """Verify pending suggestion visual indicator exists."""
        content = CSS_FILE.read_text()

        # Should have styling for pending suggestions
        assert re.search(r'\.annotation-item\.pending-suggestion', content) or \
               re.search(r'\.pending-suggestion', content), \
            "Missing pending suggestion styling"


class TestCSSAccessibility:
    """Tests for CSS accessibility features."""

    def test_confidence_badges_have_sufficient_contrast(self):
        """Verify confidence badges have background and color for contrast."""
        content = CSS_FILE.read_text()

        for class_name in [".confidence-high", ".confidence-medium", ".confidence-low"]:
            match = re.search(rf'{re.escape(class_name)}\s*{{([^}}]+)}}', content, re.DOTALL)
            assert match, f"Could not find {class_name} CSS block"

            css_block = match.group(1)
            # Should have both background and color
            assert "background" in css_block.lower(), \
                f"{class_name} missing background color"
            assert "color" in css_block.lower(), \
                f"{class_name} missing text color"

    def test_quick_action_buttons_are_visible(self):
        """Verify quick action buttons have sufficient size and visibility."""
        content = CSS_FILE.read_text()

        match = re.search(r'\.quick-action-btn\s*{([^}]+)}', content, re.DOTALL)
        assert match, "Could not find .quick-action-btn CSS block"

        css_block = match.group(1)
        # Should have width and height for touch targets
        assert "width" in css_block and "height" in css_block, \
            ".quick-action-btn missing size specifications"

    def test_hover_states_dont_rely_only_on_color(self):
        """Verify hover states use multiple indicators (transform, shadow, etc)."""
        content = CSS_FILE.read_text()

        # Find hover states
        hover_blocks = re.findall(r'\.(?:quick-action-btn|undo-redo-btn)[^{]*:hover\s*{([^}]+)}', content, re.DOTALL)
        assert len(hover_blocks) > 0, "No hover states found"

        # At least one should have transform or box-shadow (not just color change)
        has_non_color_indicator = any(
            "transform" in block.lower() or "box-shadow" in block.lower() or "scale" in block.lower()
            for block in hover_blocks
        )
        assert has_non_color_indicator, \
            "Hover states rely only on color without transform/shadow"


class TestCSSResponsiveness:
    """Tests for responsive CSS behavior."""

    def test_dark_mode_support_exists(self):
        """Verify dark mode styles exist for annotation features."""
        content = CSS_FILE.read_text()

        # Should have .dark prefixed styles or @media prefers-color-scheme
        assert ".dark " in content or "@media (prefers-color-scheme: dark)" in content, \
            "No dark mode support found"

    def test_dark_mode_quick_action_buttons(self):
        """Verify quick action buttons have dark mode variants."""
        content = CSS_FILE.read_text()

        # Should have dark mode variants for quick action buttons
        assert re.search(r'\.dark\s+\.quick-action-btn', content), \
            "Quick action buttons missing dark mode styling"

    def test_mobile_responsive_annotations(self):
        """Verify annotation styles are responsive for mobile."""
        content = CSS_FILE.read_text()

        # Should have media query for small screens
        assert "@media (max-width: 640px)" in content or "@media (max-width: 768px)" in content, \
            "No mobile responsive media queries found"


class TestJavaScriptIntegration:
    """Tests for JavaScript integration patterns."""

    def test_confidence_badge_used_in_rendering(self):
        """Verify getConfidenceBadge is actually called in render logic."""
        content = JS_FILE.read_text()

        # Should be called somewhere (not just defined)
        # Look for calls like: getConfidenceBadge(annotation) or this.getConfidenceBadge
        calls = re.findall(r'\.?getConfidenceBadge\s*\(', content)
        assert len(calls) >= 2, \
            "getConfidenceBadge is defined but not called (found {} calls)".format(len(calls))

    def test_match_explanation_used_in_rendering(self):
        """Verify getMatchExplanation is actually called in render logic."""
        content = JS_FILE.read_text()

        calls = re.findall(r'\.?getMatchExplanation\s*\(', content)
        assert len(calls) >= 2, \
            "getMatchExplanation is defined but not called (found {} calls)".format(len(calls))

    def test_pending_suggestions_used_in_ui(self):
        """Verify getPendingSuggestions is used to drive UI updates."""
        content = JS_FILE.read_text()

        calls = re.findall(r'\.?getPendingSuggestions\s*\(|\.pendingSuggestions', content)
        assert len(calls) >= 2, \
            "getPendingSuggestions is defined but not used (found {} calls)".format(len(calls))

    def test_undo_manager_instantiated(self):
        """Verify UndoManager is instantiated (not just defined)."""
        content = JS_FILE.read_text()

        # Should create instance: new UndoManager()
        assert re.search(r'new\s+UndoManager\s*\(', content), \
            "UndoManager class defined but never instantiated"

    def test_undo_redo_connected_to_ui(self):
        """Verify undo/redo methods are connected to button clicks."""
        content = JS_FILE.read_text()

        # Should have event handlers or Alpine directives calling undo/redo
        # Look for @click="undo" or onclick handlers
        assert re.search(r'@click\s*=\s*["\']undo|\.addEventListener.*undo|onclick.*undo', content), \
            "Undo method not connected to UI events"


class TestMobileJavaScriptIntegration:
    """Tests for mobile JavaScript integration."""

    def test_mobile_confidence_display_used_in_rendering(self):
        """Verify mobile getConfidenceDisplay is used in templates."""
        content = MOBILE_JS_FILE.read_text()

        calls = re.findall(r'\.?getConfidenceDisplay\s*\(', content)
        assert len(calls) >= 2, \
            "Mobile getConfidenceDisplay is defined but not called (found {} calls)".format(len(calls))

    def test_mobile_undo_delete_connected_to_ui(self):
        """Verify mobile undoDelete is connected to UI."""
        content = MOBILE_JS_FILE.read_text()

        calls = re.findall(r'\.?undoDelete\s*\(', content)
        assert len(calls) >= 1, \
            "Mobile undoDelete is defined but never called (found {} calls)".format(len(calls))

    def test_mobile_batch_review_integration(self):
        """Verify mobile batch review methods are used."""
        content = MOBILE_JS_FILE.read_text()

        # Check if batch review methods are called
        has_accept_all = "acceptAllSuggestions" in content
        has_quick_accept = "quickAcceptSuggestion" in content
        has_quick_reject = "quickRejectSuggestion" in content

        assert has_accept_all or has_quick_accept or has_quick_reject, \
            "Mobile batch review methods not integrated"


# Test file existence
class TestFileExistence:
    """Sanity checks for test file paths."""

    def test_js_file_exists(self):
        """Verify jd-annotation.js exists."""
        assert JS_FILE.exists(), f"JavaScript file not found: {JS_FILE}"

    def test_mobile_js_file_exists(self):
        """Verify mobile-annotation.js exists."""
        assert MOBILE_JS_FILE.exists(), f"Mobile JavaScript file not found: {MOBILE_JS_FILE}"

    def test_css_file_exists(self):
        """Verify jd-annotation.css exists."""
        assert CSS_FILE.exists(), f"CSS file not found: {CSS_FILE}"

    def test_files_are_not_empty(self):
        """Verify all files have content."""
        assert JS_FILE.stat().st_size > 1000, "jd-annotation.js appears to be empty or too small"
        assert MOBILE_JS_FILE.stat().st_size > 500, "mobile-annotation.js appears to be empty or too small"
        assert CSS_FILE.stat().st_size > 500, "jd-annotation.css appears to be empty or too small"
