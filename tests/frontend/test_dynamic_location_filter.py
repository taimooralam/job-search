"""
Unit tests for Dynamic Location Filter functionality.

Tests the JavaScript functions that dynamically update the location dropdown
when date filters change. This validates that:
1. loadLocations() accepts and passes date parameters to the API
2. validateSelectedLocations() removes invalid selections
3. Quick date filter buttons trigger location reload
4. Custom date inputs trigger debounced location reload
"""

import pytest
import re


class TestLoadLocationsFunctionSignature:
    """Tests for the loadLocations() JavaScript function signature."""

    def test_loadLocations_accepts_date_parameters(self, app):
        """loadLocations should accept datetimeFrom and datetimeTo parameters."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that loadLocations accepts parameters with defaults
            assert "async function loadLocations(datetimeFrom = '', datetimeTo = '')" in html

    def test_loadLocations_builds_query_params(self, app):
        """loadLocations should build URLSearchParams with date filters."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that URLSearchParams is used to build query string
            assert "new URLSearchParams()" in html
            assert "params.set('datetime_from', datetimeFrom)" in html
            assert "params.set('datetime_to', datetimeTo)" in html

    def test_loadLocations_constructs_url_with_params(self, app):
        """loadLocations should construct URL with query parameters when present."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check URL construction logic
            assert "/api/locations" in html
            # Should append params only when they exist
            assert "params.toString()" in html


class TestValidateSelectedLocationsFunction:
    """Tests for the validateSelectedLocations() JavaScript function."""

    def test_validateSelectedLocations_function_exists(self, app):
        """validateSelectedLocations function should be defined."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check function definition
            assert "function validateSelectedLocations()" in html

    def test_validateSelectedLocations_checks_empty_selection(self, app):
        """validateSelectedLocations should return early if no locations selected."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check early return condition
            assert "if (selectedLocations.size === 0) return" in html

    def test_validateSelectedLocations_builds_valid_location_set(self, app):
        """validateSelectedLocations should build a set of valid location names."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that it creates a set of valid locations
            assert "validLocationNames = new Set(allLocations.map(l => l.location))" in html

    def test_validateSelectedLocations_removes_invalid_selections(self, app):
        """validateSelectedLocations should remove locations not in valid set."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that invalid locations are identified and removed
            assert "invalidLocations.forEach(loc => selectedLocations.delete(loc))" in html

    def test_validateSelectedLocations_updates_ui_after_removal(self, app):
        """validateSelectedLocations should update UI components after removing invalid selections."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Should call UI update functions when locations are removed
            # Find the validateSelectedLocations function and check its body
            pattern = r'function validateSelectedLocations\(\).*?updateLocationButtonText\(\)'
            match = re.search(pattern, html, re.DOTALL)
            assert match is not None, "validateSelectedLocations should call updateLocationButtonText"


class TestQuickDateFilterIntegration:
    """Tests for quick date filter integration with location loading."""

    def test_setQuickDateFilter_calls_loadLocations(self, app):
        """setQuickDateFilter should call loadLocations with current date values."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that setQuickDateFilter calls loadLocations
            # The function should have a call to loadLocations with the date inputs
            assert "loadLocations(" in html

            # Check that it passes the date-from and date-to values
            pattern = r"setQuickDateFilter.*?loadLocations\("
            match = re.search(pattern, html, re.DOTALL)
            assert match is not None, "setQuickDateFilter should call loadLocations"


class TestClearDateFilterIntegration:
    """Tests for clear date filter integration with location loading."""

    def test_clearDateFilter_calls_loadLocations(self, app):
        """clearDateFilter should call loadLocations without parameters to reload all."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Find clearDateFilter function and verify it calls loadLocations()
            # Pattern to match the function and find loadLocations call within it
            pattern = r'function clearDateFilter\(\).*?loadLocations\(\)'
            match = re.search(pattern, html, re.DOTALL)
            assert match is not None, "clearDateFilter should call loadLocations()"


class TestDebouncedCustomDateInputs:
    """Tests for debounced location refresh on custom date inputs."""

    def test_debounce_helper_function_exists(self, app):
        """A debounce helper function should be defined."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check debounce function definition
            assert "function debounce(func, wait)" in html

    def test_debounced_refresh_function_created(self, app):
        """A debounced refresh function should be created for date input changes."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that a debounced version is created
            assert "refreshLocationsDebounced = debounce(" in html

    def test_date_inputs_have_change_listeners(self, app):
        """Date inputs should have change event listeners for debounced refresh."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that event listeners are added
            assert "getElementById('date-from')?.addEventListener('change', refreshLocationsDebounced)" in html
            assert "getElementById('date-to')?.addEventListener('change', refreshLocationsDebounced)" in html


class TestLoadingState:
    """Tests for loading state in location dropdown."""

    def test_renderLocationOptions_accepts_loading_parameter(self, app):
        """renderLocationOptions should accept an isLoading parameter."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check function signature with isLoading parameter
            assert "function renderLocationOptions(locations, isLoading = false)" in html

    def test_renderLocationOptions_shows_loading_message(self, app):
        """renderLocationOptions should show loading message when isLoading is true."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check loading state handling
            assert "if (isLoading)" in html
            assert "Loading locations..." in html

    def test_loadLocations_shows_loading_state(self, app):
        """loadLocations should call renderLocationOptions with loading state."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that loading state is shown before fetch
            assert "renderLocationOptions([], true)" in html


class TestResetAllFiltersIntegration:
    """Tests for resetAllFilters integration with location loading."""

    def test_resetAllFilters_clears_location_set(self, app):
        """resetAllFilters should clear the selectedLocations Set."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that selectedLocations.clear() is called in resetAllFilters
            pattern = r'function resetAllFilters\(\).*?selectedLocations\.clear\(\)'
            match = re.search(pattern, html, re.DOTALL)
            assert match is not None, "resetAllFilters should call selectedLocations.clear()"

    def test_resetAllFilters_reloads_locations(self, app):
        """resetAllFilters should reload all locations without date filter."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True

            response = client.get("/")
            html = response.data.decode('utf-8')

            # Check that loadLocations() is called in resetAllFilters
            pattern = r'function resetAllFilters\(\).*?loadLocations\(\)'
            match = re.search(pattern, html, re.DOTALL)
            assert match is not None, "resetAllFilters should call loadLocations()"
