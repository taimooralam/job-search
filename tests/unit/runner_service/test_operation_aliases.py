"""
Tests for operation name aliases and backward compatibility.

Ensures legacy operation names are correctly mapped to canonical names
and that deprecation warnings are logged appropriately.
"""

import pytest
import logging
from unittest.mock import patch


class TestOperationAliases:
    """Tests for OPERATION_ALIASES mapping."""

    def test_aliases_include_full_extraction(self):
        """full-extraction should map to analyze-job."""
        from runner_service.routes.operations import OPERATION_ALIASES

        assert "full-extraction" in OPERATION_ALIASES
        assert OPERATION_ALIASES["full-extraction"] == "analyze-job"

    def test_aliases_include_structure_jd(self):
        """structure-jd should map to prepare-annotations."""
        from runner_service.routes.operations import OPERATION_ALIASES

        assert "structure-jd" in OPERATION_ALIASES
        assert OPERATION_ALIASES["structure-jd"] == "prepare-annotations"

    def test_aliases_include_all_ops(self):
        """all-ops should map to full-analysis."""
        from runner_service.routes.operations import OPERATION_ALIASES

        assert "all-ops" in OPERATION_ALIASES
        assert OPERATION_ALIASES["all-ops"] == "full-analysis"

    def test_aliases_include_process_jd(self):
        """process-jd should map to analyze-job (duplicate removed)."""
        from runner_service.routes.operations import OPERATION_ALIASES

        assert "process-jd" in OPERATION_ALIASES
        assert OPERATION_ALIASES["process-jd"] == "analyze-job"


class TestResolveOperationAlias:
    """Tests for resolve_operation_alias function."""

    def test_resolves_legacy_to_canonical(self):
        """Legacy names should resolve to canonical names."""
        from runner_service.routes.operations import resolve_operation_alias

        # Full extraction -> analyze-job
        assert resolve_operation_alias("full-extraction") == "analyze-job"

        # Structure JD -> prepare-annotations
        assert resolve_operation_alias("structure-jd") == "prepare-annotations"

        # All ops -> full-analysis
        assert resolve_operation_alias("all-ops") == "full-analysis"

    def test_canonical_names_unchanged(self):
        """Canonical names should remain unchanged."""
        from runner_service.routes.operations import resolve_operation_alias

        assert resolve_operation_alias("analyze-job") == "analyze-job"
        assert resolve_operation_alias("prepare-annotations") == "prepare-annotations"
        assert resolve_operation_alias("research-company") == "research-company"
        assert resolve_operation_alias("discover-contacts") == "discover-contacts"
        assert resolve_operation_alias("generate-cv") == "generate-cv"
        assert resolve_operation_alias("generate-cover-letter") == "generate-cover-letter"
        assert resolve_operation_alias("full-analysis") == "full-analysis"

    def test_logs_deprecation_warning_for_legacy_name(self, caplog):
        """Using a legacy name should log a deprecation warning."""
        from runner_service.routes.operations import resolve_operation_alias

        with caplog.at_level(logging.WARNING):
            resolve_operation_alias("full-extraction")

        assert "DEPRECATED" in caplog.text
        assert "full-extraction" in caplog.text
        assert "analyze-job" in caplog.text

    def test_no_warning_for_canonical_name(self, caplog):
        """Using a canonical name should not log a warning."""
        from runner_service.routes.operations import resolve_operation_alias

        with caplog.at_level(logging.WARNING):
            resolve_operation_alias("analyze-job")

        assert "DEPRECATED" not in caplog.text


class TestOperationRouting:
    """Tests for OPERATION_ROUTING mapping."""

    def test_discover_contacts_routes_to_research(self):
        """discover-contacts should route to research-company."""
        from runner_service.routes.operations import OPERATION_ROUTING

        assert "discover-contacts" in OPERATION_ROUTING
        assert OPERATION_ROUTING["discover-contacts"] == "research-company"

    def test_generate_cover_letter_routes_to_cv(self):
        """generate-cover-letter should route to generate-cv."""
        from runner_service.routes.operations import OPERATION_ROUTING

        assert "generate-cover-letter" in OPERATION_ROUTING
        assert OPERATION_ROUTING["generate-cover-letter"] == "generate-cv"

    def test_generate_outreach_routes_to_research(self):
        """generate-outreach should route to research-company."""
        from runner_service.routes.operations import OPERATION_ROUTING

        assert "generate-outreach" in OPERATION_ROUTING
        assert OPERATION_ROUTING["generate-outreach"] == "research-company"


class TestGetRoutedOperation:
    """Tests for get_routed_operation function."""

    def test_new_ops_get_routed(self):
        """New operations should be routed to parent services."""
        from runner_service.routes.operations import get_routed_operation

        assert get_routed_operation("discover-contacts") == "research-company"
        assert get_routed_operation("generate-cover-letter") == "generate-cv"
        assert get_routed_operation("generate-outreach") == "research-company"

    def test_existing_ops_unchanged(self):
        """Existing operations should remain unchanged."""
        from runner_service.routes.operations import get_routed_operation

        assert get_routed_operation("research-company") == "research-company"
        assert get_routed_operation("generate-cv") == "generate-cv"
        assert get_routed_operation("analyze-job") == "analyze-job"
        assert get_routed_operation("full-analysis") == "full-analysis"


class TestValidQueueOperations:
    """Tests for VALID_QUEUE_OPERATIONS set."""

    def test_includes_canonical_names(self):
        """All canonical operation names should be valid."""
        from runner_service.routes.operations import VALID_QUEUE_OPERATIONS

        canonical_ops = {
            "analyze-job",
            "prepare-annotations",
            "research-company",
            "discover-contacts",
            "generate-cv",
            "generate-cover-letter",
            "generate-outreach",
            "full-analysis",
        }

        for op in canonical_ops:
            assert op in VALID_QUEUE_OPERATIONS, f"Missing canonical op: {op}"

    def test_includes_legacy_names(self):
        """Legacy operation names should still be valid for backward compat."""
        from runner_service.routes.operations import VALID_QUEUE_OPERATIONS

        legacy_ops = {
            "structure-jd",
            "full-extraction",
            "all-ops",
            "extract",
        }

        for op in legacy_ops:
            assert op in VALID_QUEUE_OPERATIONS, f"Missing legacy op: {op}"


class TestOperationTimeEstimates:
    """Tests for OPERATION_TIME_ESTIMATES mapping."""

    def test_has_canonical_estimates(self):
        """All canonical operations should have time estimates."""
        from runner_service.routes.operations import (
            OPERATION_TIME_ESTIMATES,
            VALID_QUEUE_OPERATIONS,
        )

        canonical_ops = {
            "analyze-job",
            "prepare-annotations",
            "research-company",
            "discover-contacts",
            "generate-cv",
            "generate-cover-letter",
            "generate-outreach",
            "full-analysis",
        }

        for op in canonical_ops:
            assert op in OPERATION_TIME_ESTIMATES, f"Missing time estimate: {op}"
            assert OPERATION_TIME_ESTIMATES[op] > 0

    def test_has_legacy_estimates(self):
        """Legacy operations should also have time estimates."""
        from runner_service.routes.operations import OPERATION_TIME_ESTIMATES

        legacy_ops = {
            "structure-jd",
            "full-extraction",
            "all-ops",
            "extract",
        }

        for op in legacy_ops:
            assert op in OPERATION_TIME_ESTIMATES, f"Missing time estimate: {op}"
            assert OPERATION_TIME_ESTIMATES[op] > 0
