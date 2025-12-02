"""
Centralized error handling for the job intelligence pipeline.

Provides decorators and utilities for consistent error handling,
logging, and fallback behavior across all pipeline layers.
"""

import logging
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, List
from dataclasses import dataclass, field
from datetime import datetime

# Type variable for generic return types
T = TypeVar("T")


@dataclass
class PipelineError:
    """
    Structured error information for pipeline failures.

    Provides consistent error tracking with severity and recoverability.
    """

    layer: str  # e.g., "layer7", "mongodb"
    operation: str  # e.g., "mongodb_persistence", "drive_upload"
    severity: str  # "critical", "high", "medium", "low"
    message: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    recoverable: bool = True  # Can pipeline continue?
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "layer": self.layer,
            "operation": self.operation,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp,
            "recoverable": self.recoverable,
            "exception_type": self.exception_type,
        }


class ErrorCollector:
    """
    Collects errors during pipeline execution.

    Provides aggregation and summary capabilities for error tracking.
    """

    def __init__(self):
        self.errors: List[PipelineError] = []

    def add(self, error: PipelineError) -> None:
        """Add an error to the collection."""
        self.errors.append(error)

    def add_error(
        self,
        layer: str,
        operation: str,
        message: str,
        severity: str = "medium",
        recoverable: bool = True,
        exception: Optional[Exception] = None,
    ) -> None:
        """Convenience method to add an error with parameters."""
        error = PipelineError(
            layer=layer,
            operation=operation,
            message=message,
            severity=severity,
            recoverable=recoverable,
            exception_type=type(exception).__name__ if exception else None,
        )
        self.errors.append(error)

    def has_critical_errors(self) -> bool:
        """Check if any critical (non-recoverable) errors occurred."""
        return any(e.severity == "critical" and not e.recoverable for e in self.errors)

    def get_error_messages(self) -> List[str]:
        """Get list of error messages for backward compatibility."""
        return [e.message for e in self.errors]

    def summary(self) -> dict:
        """Get error summary statistics."""
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for error in self.errors:
            if error.severity in by_severity:
                by_severity[error.severity] += 1
        return {
            "total": len(self.errors),
            "by_severity": by_severity,
            "recoverable": sum(1 for e in self.errors if e.recoverable),
            "non_recoverable": sum(1 for e in self.errors if not e.recoverable),
        }


def pipeline_operation(
    operation_name: str,
    layer: str = "unknown",
    critical: bool = False,
    log_success: bool = True,
    fallback_value: Any = None,
    reraise: bool = False,
):
    """
    Decorator for pipeline operations with consistent error handling.

    Provides:
    - Automatic INFO logging on success (if log_success=True)
    - ERROR logging on failure for critical operations
    - WARNING logging on failure for non-critical operations
    - Stack traces for critical errors
    - Optional re-raising of exceptions

    Args:
        operation_name: Human-readable operation name (e.g., "MongoDB persistence")
        layer: Layer identifier (e.g., "layer7", "mongodb")
        critical: If True, logs at ERROR level with stack trace; if False, WARNING
        log_success: If True, logs successful completion at INFO level
        fallback_value: Value to return on failure (default: None)
        reraise: If True, re-raises the exception after logging

    Usage:
        @pipeline_operation("MongoDB job lookup", layer="layer7", critical=True)
        def _find_job_record(self, job_id: str):
            # ... lookup logic ...
            return job_record
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            logger = logging.getLogger(func.__module__)
            try:
                result = func(*args, **kwargs)
                if log_success:
                    logger.info(f"[{layer}] [{operation_name}] ✓ Completed successfully")
                return result
            except Exception as e:
                log_level = logging.ERROR if critical else logging.WARNING
                logger.log(
                    log_level,
                    f"[{layer}] [{operation_name}] ✗ Failed: {e}",
                    exc_info=critical,  # Stack trace for critical errors only
                )
                if reraise:
                    raise
                return fallback_value

        return wrapper

    return decorator


def log_on_exception(
    logger: logging.Logger,
    operation: str,
    level: int = logging.WARNING,
    include_traceback: bool = False,
):
    """
    Context manager for logging exceptions without swallowing them silently.

    Usage:
        with log_on_exception(self.logger, "MongoDB update", level=logging.ERROR, include_traceback=True):
            collection.update_one(...)

    Args:
        logger: Logger instance to use
        operation: Operation description for the log message
        level: Log level (default: WARNING)
        include_traceback: Whether to include stack trace in log
    """

    class ExceptionLogger:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_val is not None:
                if include_traceback:
                    logger.log(level, f"[{operation}] Failed: {exc_val}", exc_info=True)
                else:
                    logger.log(level, f"[{operation}] Failed: {exc_val}")
            # Return False to not suppress the exception
            return False

    return ExceptionLogger()


def safe_execute(
    func: Callable[..., T],
    *args,
    operation_name: str = "operation",
    logger: Optional[logging.Logger] = None,
    fallback: T = None,
    critical: bool = False,
    **kwargs,
) -> T:
    """
    Execute a function safely with error handling and logging.

    This is an alternative to the decorator for one-off operations.

    Args:
        func: Function to execute
        *args: Positional arguments for func
        operation_name: Name for logging
        logger: Logger instance (uses module logger if None)
        fallback: Value to return on failure
        critical: If True, log at ERROR level with traceback
        **kwargs: Keyword arguments for func

    Returns:
        Function result or fallback value on error

    Usage:
        result = safe_execute(
            collection.update_one,
            {"_id": doc_id},
            {"$set": update_data},
            operation_name="MongoDB update",
            logger=self.logger,
            fallback=None,
            critical=True
        )
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        return func(*args, **kwargs)
    except Exception as e:
        log_level = logging.ERROR if critical else logging.WARNING
        logger.log(
            log_level,
            f"[{operation_name}] Failed: {e}",
            exc_info=critical,
        )
        return fallback
