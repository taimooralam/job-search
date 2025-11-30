"""
Unit tests for structured logger module.
"""

import json
import pytest
from io import StringIO
from unittest.mock import patch
import time

from src.common.structured_logger import (
    StructuredLogger,
    LogEvent,
    EventType,
    LayerStatus,
    LayerContext,
    get_structured_logger,
)


class TestLogEvent:
    """Tests for LogEvent dataclass."""

    def test_to_json_includes_required_fields(self):
        """Should include timestamp, event, and job_id."""
        event = LogEvent(
            timestamp="2025-11-30T10:00:00Z",
            event="layer_start",
            job_id="job123",
        )
        result = json.loads(event.to_json())

        assert result["timestamp"] == "2025-11-30T10:00:00Z"
        assert result["event"] == "layer_start"
        assert result["job_id"] == "job123"

    def test_to_json_excludes_none_values(self):
        """Should exclude fields that are None."""
        event = LogEvent(
            timestamp="2025-11-30T10:00:00Z",
            event="layer_start",
            job_id="job123",
            layer=2,
            layer_name="pain_point_miner",
            status=None,  # Should be excluded
            duration_ms=None,  # Should be excluded
        )
        result = json.loads(event.to_json())

        assert "layer" in result
        assert "layer_name" in result
        assert "status" not in result
        assert "duration_ms" not in result

    def test_to_json_includes_all_provided_fields(self):
        """Should include all non-None fields."""
        event = LogEvent(
            timestamp="2025-11-30T10:00:00Z",
            event="layer_complete",
            job_id="job123",
            layer=4,
            layer_name="opportunity_mapper",
            status="success",
            duration_ms=4500,
            metadata={"fit_score": 85},
            error=None,
        )
        result = json.loads(event.to_json())

        assert result["layer"] == 4
        assert result["layer_name"] == "opportunity_mapper"
        assert result["status"] == "success"
        assert result["duration_ms"] == 4500
        assert result["metadata"]["fit_score"] == 85


class TestStructuredLogger:
    """Tests for StructuredLogger class."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="test-job-123")

    @pytest.fixture
    def disabled_logger(self):
        """Create a disabled logger instance."""
        return StructuredLogger(job_id="test-job-123", enabled=False)

    def test_init_stores_job_id(self, logger):
        """Should store job_id for correlation."""
        assert logger.job_id == "test-job-123"

    def test_disabled_logger_does_not_emit(self, disabled_logger, capsys):
        """Disabled logger should not emit any output."""
        disabled_logger.layer_start(2)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_layer_start_emits_json(self, logger, capsys):
        """layer_start should emit JSON with correct event type."""
        logger.layer_start(2, "pain_point_miner")
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["event"] == "layer_start"
        assert event["layer"] == 2
        assert event["layer_name"] == "pain_point_miner"
        assert event["job_id"] == "test-job-123"
        assert "timestamp" in event

    def test_layer_start_auto_derives_name(self, logger, capsys):
        """layer_start should auto-derive layer name if not provided."""
        logger.layer_start(4)
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["layer_name"] == "opportunity_mapper"

    def test_layer_complete_emits_success_status(self, logger, capsys):
        """layer_complete should emit success status."""
        logger.layer_complete(4, duration_ms=5000)
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["event"] == "layer_complete"
        assert event["status"] == "success"
        assert event["duration_ms"] == 5000

    def test_layer_complete_includes_metadata(self, logger, capsys):
        """layer_complete should include metadata if provided."""
        logger.layer_complete(4, metadata={"fit_score": 85, "tokens_used": 1200})
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["metadata"]["fit_score"] == 85
        assert event["metadata"]["tokens_used"] == 1200

    def test_layer_complete_auto_calculates_duration(self, logger, capsys):
        """layer_complete should auto-calculate duration from layer_start."""
        logger.layer_start(2)
        time.sleep(0.1)  # 100ms
        logger.layer_complete(2)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        complete_event = json.loads(lines[1])

        assert complete_event["duration_ms"] >= 100

    def test_layer_error_emits_error_status(self, logger, capsys):
        """layer_error should emit error status and message."""
        logger.layer_error(3, "Connection timeout")
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["event"] == "layer_error"
        assert event["status"] == "error"
        assert event["error"] == "Connection timeout"
        assert event["layer"] == 3

    def test_layer_error_auto_calculates_duration(self, logger, capsys):
        """layer_error should auto-calculate duration from layer_start."""
        logger.layer_start(3)
        time.sleep(0.05)  # 50ms
        logger.layer_error(3, "API error")

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        error_event = json.loads(lines[1])

        assert error_event["duration_ms"] >= 50

    def test_layer_skip_emits_skipped_status(self, logger, capsys):
        """layer_skip should emit skipped status with reason."""
        logger.layer_skip(5, "Feature disabled")
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["event"] == "layer_skip"
        assert event["status"] == "skipped"
        assert event["metadata"]["reason"] == "Feature disabled"

    def test_pipeline_start(self, logger, capsys):
        """pipeline_start should emit pipeline_start event."""
        logger.pipeline_start(metadata={"job_title": "Software Engineer"})
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["event"] == "pipeline_start"
        assert event["metadata"]["job_title"] == "Software Engineer"

    def test_pipeline_complete(self, logger, capsys):
        """pipeline_complete should emit final status."""
        logger.pipeline_complete(status="success", duration_ms=45000)
        captured = capsys.readouterr()

        event = json.loads(captured.out.strip())
        assert event["event"] == "pipeline_complete"
        assert event["status"] == "success"
        assert event["duration_ms"] == 45000

    def test_layer_names_mapping(self, logger):
        """Should have correct layer name mapping."""
        assert logger._get_layer_name(1) == "jd_extractor"
        assert logger._get_layer_name(2) == "pain_point_miner"
        assert logger._get_layer_name(3) == "company_researcher"
        assert logger._get_layer_name(4) == "opportunity_mapper"
        assert logger._get_layer_name(5) == "people_mapper"
        assert logger._get_layer_name(6) == "cv_generator"
        assert logger._get_layer_name(7) == "publisher"

    def test_unknown_layer_returns_generic_name(self, logger):
        """Unknown layer should return generic name."""
        assert logger._get_layer_name(99) == "layer_99"


class TestLayerContext:
    """Tests for LayerContext context manager."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="ctx-test-123")

    def test_context_manager_emits_start_and_complete(self, logger, capsys):
        """Context manager should emit start on enter and complete on exit."""
        with LayerContext(logger, 4, "opportunity_mapper"):
            pass

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        start_event = json.loads(lines[0])
        complete_event = json.loads(lines[1])

        assert start_event["event"] == "layer_start"
        assert complete_event["event"] == "layer_complete"
        assert complete_event["status"] == "success"

    def test_context_manager_calculates_duration(self, logger, capsys):
        """Context manager should calculate duration automatically."""
        with LayerContext(logger, 4):
            time.sleep(0.05)  # 50ms

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        complete_event = json.loads(lines[1])

        assert complete_event["duration_ms"] >= 50

    def test_context_manager_handles_exception(self, logger, capsys):
        """Context manager should emit error on exception."""
        with pytest.raises(ValueError):
            with LayerContext(logger, 4):
                raise ValueError("Test error")

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        error_event = json.loads(lines[1])

        assert error_event["event"] == "layer_error"
        assert error_event["status"] == "error"
        assert "Test error" in error_event["error"]

    def test_context_manager_add_metadata(self, logger, capsys):
        """Context manager should allow adding metadata."""
        with LayerContext(logger, 4) as ctx:
            ctx.add_metadata("fit_score", 85)
            ctx.add_metadata("tokens_used", 1200)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        complete_event = json.loads(lines[1])

        assert complete_event["metadata"]["fit_score"] == 85
        assert complete_event["metadata"]["tokens_used"] == 1200

    def test_context_manager_metadata_included_on_error(self, logger, capsys):
        """Context manager should include metadata even on error."""
        with pytest.raises(RuntimeError):
            with LayerContext(logger, 4) as ctx:
                ctx.add_metadata("partial_result", True)
                raise RuntimeError("Partial failure")

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        error_event = json.loads(lines[1])

        assert error_event["metadata"]["partial_result"] is True


class TestFactoryFunction:
    """Tests for get_structured_logger factory function."""

    def test_returns_structured_logger(self):
        """Factory should return StructuredLogger instance."""
        logger = get_structured_logger("factory-test-123")
        assert isinstance(logger, StructuredLogger)
        assert logger.job_id == "factory-test-123"

    def test_can_disable_logger(self):
        """Factory should respect enabled flag."""
        logger = get_structured_logger("test", enabled=False)
        assert logger.enabled is False


class TestEventTypes:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Should have correct string values."""
        assert EventType.LAYER_START.value == "layer_start"
        assert EventType.LAYER_COMPLETE.value == "layer_complete"
        assert EventType.LAYER_ERROR.value == "layer_error"
        assert EventType.LAYER_SKIP.value == "layer_skip"
        assert EventType.PIPELINE_START.value == "pipeline_start"
        assert EventType.PIPELINE_COMPLETE.value == "pipeline_complete"


class TestLayerStatus:
    """Tests for LayerStatus enum."""

    def test_layer_status_values(self):
        """Should have correct string values."""
        assert LayerStatus.SUCCESS.value == "success"
        assert LayerStatus.ERROR.value == "error"
        assert LayerStatus.SKIPPED.value == "skipped"
        assert LayerStatus.PARTIAL.value == "partial"
