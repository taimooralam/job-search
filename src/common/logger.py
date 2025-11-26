"""
Centralized logging configuration for the job intelligence pipeline.

Provides structured logging with run_id and layer tagging for easy debugging.
"""

import logging
import sys
from typing import Optional


class PipelineLogger:
    """
    Structured logger for pipeline execution.

    Adds contextual information like run_id and layer to all log messages.
    """

    def __init__(self, name: str, run_id: Optional[str] = None, layer: Optional[str] = None):
        """
        Initialize pipeline logger.

        Args:
            name: Logger name (usually __name__)
            run_id: Optional run identifier for correlation
            layer: Optional layer name (e.g., "layer2", "layer6")
        """
        self.logger = logging.getLogger(name)
        self.run_id = run_id
        self.layer = layer

    def _format_message(self, message: str) -> str:
        """Add contextual prefix to message."""
        prefix_parts = []
        if self.run_id:
            prefix_parts.append(f"[run:{self.run_id[:8]}]")
        if self.layer:
            prefix_parts.append(f"[{self.layer}]")

        if prefix_parts:
            return f"{' '.join(prefix_parts)} {message}"
        return message

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(self._format_message(message), **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(self._format_message(message), **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(self._format_message(message), **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(self._format_message(message), **kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        self.logger.exception(self._format_message(message), **kwargs)


def setup_logging(level: str = "INFO", format: str = "simple") -> None:
    """
    Configure global logging settings.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format: Log format ("simple" or "json")
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Set format
    if format == "json":
        # JSON format for production (parseable by log aggregators)
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
        )
    else:
        # Simple format for development
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str, run_id: Optional[str] = None, layer: Optional[str] = None) -> PipelineLogger:
    """
    Get a pipeline logger instance.

    Args:
        name: Logger name (usually __name__)
        run_id: Optional run identifier
        layer: Optional layer name

    Returns:
        PipelineLogger instance
    """
    return PipelineLogger(name, run_id, layer)
