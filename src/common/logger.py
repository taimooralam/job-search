"""
Centralized logging configuration for the job intelligence pipeline.

Provides structured logging with run_id and layer tagging for easy debugging.
Supports debug_mode flag for verbose logging when API passes debug=true.
"""

import logging
import os
import sys
from typing import Optional


# Global debug mode flag - can be set via environment or API
_GLOBAL_DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


def set_global_debug_mode(enabled: bool) -> None:
    """Set global debug mode (used by API debug=true parameter)."""
    global _GLOBAL_DEBUG_MODE
    _GLOBAL_DEBUG_MODE = enabled


def is_debug_mode() -> bool:
    """Check if debug mode is enabled globally."""
    return _GLOBAL_DEBUG_MODE


class PipelineLogger:
    """
    Structured logger for pipeline execution.

    Adds contextual information like run_id and layer to all log messages.
    """

    def __init__(
        self,
        name: str,
        run_id: Optional[str] = None,
        layer: Optional[str] = None,
        debug_mode: Optional[bool] = None
    ):
        """
        Initialize pipeline logger.

        Args:
            name: Logger name (usually __name__)
            run_id: Optional run identifier for correlation
            layer: Optional layer name (e.g., "layer2", "layer6")
            debug_mode: If True, enables DEBUG level for this logger.
                       If None, uses global debug mode setting.
        """
        self.logger = logging.getLogger(name)
        self.run_id = run_id
        self.layer = layer

        # Determine debug mode: explicit param > global setting
        self._debug_mode = debug_mode if debug_mode is not None else is_debug_mode()

        # Set logger level based on debug mode
        if self._debug_mode:
            self.logger.setLevel(logging.DEBUG)

    @property
    def level(self) -> int:
        """Get current logging level."""
        return self.logger.level

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


def get_logger(
    name: str,
    run_id: Optional[str] = None,
    layer: Optional[str] = None,
    debug_mode: Optional[bool] = None
) -> PipelineLogger:
    """
    Get a pipeline logger instance.

    Args:
        name: Logger name (usually __name__)
        run_id: Optional run identifier
        layer: Optional layer name
        debug_mode: If True, enables DEBUG level. If None, uses global setting.

    Returns:
        PipelineLogger instance
    """
    return PipelineLogger(name, run_id, layer, debug_mode)
