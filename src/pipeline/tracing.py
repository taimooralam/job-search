"""Best-effort Langfuse tracing hooks for iteration 1 search observability."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - optional dependency
    Langfuse = None


class SearchTracingSession:
    """Thin, optional wrapper around Langfuse trace/span creation."""

    def __init__(
        self,
        *,
        run_id: str,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self.enabled = False
        self.run_id = run_id
        self.session_id = session_id
        self.trace = None
        self.trace_id = None
        self.trace_url = None
        self._client = None

        if Langfuse is None:
            return

        config = _langfuse_config()
        if config is None:
            return

        try:
            self._client = Langfuse(
                host=config["host"],
                public_key=config["public_key"],
                secret_key=config["secret_key"],
            )
            self.trace_id = self._client.create_trace_id(seed=run_id)
            self.trace = self._client.start_observation(
                trace_context={"trace_id": self.trace_id},
                name="scout.search.run",
                as_type="span",
                input=metadata,
                metadata=metadata,
            )
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(
                    name="scout.search.run",
                    session_id=session_id,
                    input=metadata,
                    metadata=metadata,
                )
            self.trace_url = _resolve_trace_url(self._client, self.trace_id)
            self.enabled = True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse disabled for run %s: %s", run_id, exc)
            self.enabled = False
            self.trace = None
            self.trace_id = None
            self.trace_url = None
            self._client = None

    def start_combo_span(self, metadata: dict[str, Any]):
        """Start a child span for one region/profile search request."""
        if not self.trace:
            return None
        try:
            return self.trace.start_observation(
                name="scout.search.combo",
                as_type="span",
                input=metadata,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse combo span failed: %s", exc)
            return None

    def end_span(self, span: Any, *, output: Optional[dict[str, Any]] = None) -> None:
        """End a previously started span."""
        if span is None:
            return
        try:
            if output is not None:
                span.update(output=output)
            span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse span end failed: %s", exc)

    def record_hit_event(self, event_name: str, metadata: dict[str, Any]) -> None:
        """Record a child hit event under the root trace."""
        self._record_event(name=f"scout.hit.{event_name}", metadata=metadata)

    def record_enqueue_event(self, metadata: dict[str, Any]) -> None:
        """Record a work-item enqueue event."""
        self._record_event(name="scout.work_item.enqueue", metadata=metadata)

    def record_legacy_handoff(self, metadata: dict[str, Any]) -> None:
        """Record a legacy queue handoff event."""
        self._record_event(name="scout.legacy_handoff", metadata=metadata)

    def complete(self, *, output: Optional[dict[str, Any]] = None) -> None:
        """Finalize the root trace."""
        if not self.trace:
            return
        try:
            self.trace.update(output=output)
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(output=output)
            self.trace.end()
            if self._client is not None:
                self._client.flush()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse trace finalize failed: %s", exc)

    def _record_event(self, *, name: str, metadata: dict[str, Any]) -> None:
        """Create a short-lived child span for one event."""
        if not self.trace:
            return
        try:
            if self._client is not None and self.trace_id is not None:
                self._client.create_event(
                    trace_context={"trace_id": self.trace_id},
                    name=name,
                    input=metadata,
                    output=metadata,
                    metadata=metadata,
                )
                return
            span = self.trace.start_observation(name=name, as_type="span", input=metadata, metadata=metadata)
            span.update(output=metadata)
            span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse event %s failed: %s", name, exc)


class ScrapeTracingSession:
    """Optional Langfuse wrapper for native scrape worker runs."""

    def __init__(
        self,
        *,
        run_id: str,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self.enabled = False
        self.run_id = run_id
        self.session_id = session_id
        self.trace = None
        self.trace_id = None
        self.trace_url = None
        self._client = None

        if Langfuse is None:
            return

        config = _langfuse_config()
        if config is None:
            return

        try:
            self._client = Langfuse(
                host=config["host"],
                public_key=config["public_key"],
                secret_key=config["secret_key"],
            )
            self.trace_id = self._client.create_trace_id(seed=run_id)
            self.trace = self._client.start_observation(
                trace_context={"trace_id": self.trace_id},
                name="scout.scrape.run",
                as_type="span",
                input=metadata,
                metadata=metadata,
            )
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(
                    name="scout.scrape.run",
                    session_id=session_id,
                    input=metadata,
                    metadata=metadata,
                )
            self.trace_url = _resolve_trace_url(self._client, self.trace_id)
            self.enabled = True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse disabled for scrape run %s: %s", run_id, exc)

    def start_work_item_span(self, metadata: dict[str, Any]):
        """Start a child span for one claimed work item."""
        if not self.trace:
            return None
        try:
            return self.trace.start_observation(
                name="scout.scrape.work_item",
                as_type="span",
                input=metadata,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse scrape work-item span failed: %s", exc)
            return None

    def record_stage(self, name: str, metadata: dict[str, Any]) -> None:
        """Record a scrape-stage event or short-lived child span."""
        if not self.trace:
            return
        full_name = f"scout.scrape.{name}"
        try:
            if self._client is not None and self.trace_id is not None:
                self._client.create_event(
                    trace_context={"trace_id": self.trace_id},
                    name=full_name,
                    input=metadata,
                    output=metadata,
                    metadata=metadata,
                )
                return
            span = self.trace.start_observation(name=full_name, as_type="span", input=metadata, metadata=metadata)
            span.update(output=metadata)
            span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse scrape stage %s failed: %s", name, exc)

    def end_span(self, span: Any, *, output: Optional[dict[str, Any]] = None) -> None:
        """End a previously started work-item span."""
        if span is None:
            return
        try:
            if output is not None:
                span.update(output=output)
            span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse scrape span end failed: %s", exc)

    def complete(self, *, output: Optional[dict[str, Any]] = None) -> None:
        """Finalize the scrape run trace."""
        if not self.trace:
            return
        try:
            self.trace.update(output=output)
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(output=output)
            self.trace.end()
            if self._client is not None:
                self._client.flush()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse scrape trace finalize failed: %s", exc)


class SelectorTracingSession:
    """Optional Langfuse wrapper for native selector run traces."""

    def __init__(
        self,
        *,
        run_id: str,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self.enabled = False
        self.run_id = run_id
        self.session_id = session_id
        self.trace = None
        self.trace_id = None
        self.trace_url = None
        self._client = None

        if Langfuse is None:
            return

        config = _langfuse_config()
        if config is None:
            return

        try:
            self._client = Langfuse(
                host=config["host"],
                public_key=config["public_key"],
                secret_key=config["secret_key"],
            )
            self.trace_id = self._client.create_trace_id(seed=run_id)
            self.trace = self._client.start_observation(
                trace_context={"trace_id": self.trace_id},
                name="scout.selector.run",
                as_type="span",
                input=metadata,
                metadata=metadata,
            )
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(
                    name="scout.selector.run",
                    session_id=session_id,
                    input=metadata,
                    metadata=metadata,
                )
            self.trace_url = _resolve_trace_url(self._client, self.trace_id)
            self.enabled = True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse disabled for selector run %s: %s", run_id, exc)

    def record_stage(self, name: str, metadata: dict[str, Any]) -> None:
        """Record one selector stage event."""
        if not self.trace:
            return
        full_name = f"scout.selector.{name}"
        try:
            if self._client is not None and self.trace_id is not None:
                self._client.create_event(
                    trace_context={"trace_id": self.trace_id},
                    name=full_name,
                    input=metadata,
                    output=metadata,
                    metadata=metadata,
                )
                return
            span = self.trace.start_observation(name=full_name, as_type="span", input=metadata, metadata=metadata)
            span.update(output=metadata)
            span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse selector stage %s failed: %s", name, exc)

    def complete(self, *, output: Optional[dict[str, Any]] = None) -> None:
        """Finalize the selector trace."""
        if not self.trace:
            return
        try:
            self.trace.update(output=output)
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(output=output)
            self.trace.end()
            if self._client is not None:
                self._client.flush()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse selector trace finalize failed: %s", exc)


class PreenrichStageTracingHandle:
    """Stage-scoped tracing handle that nests substages under one stage span."""

    def __init__(self, session: "PreenrichTracingSession", *, stage_name: str, span: Any) -> None:
        self._session = session
        self.stage_name = stage_name
        self.span = span
        self.trace = session.trace
        self.trace_id = session.trace_id
        self.trace_url = session.trace_url
        self.enabled = bool(session.enabled and span is not None)

    def start_substage_span(self, stage_name: str, substage: str, metadata: dict[str, Any]):
        target_stage = stage_name or self.stage_name
        return self._session._start_span(
            f"scout.preenrich.{target_stage}.{substage}",
            metadata,
            parent=self.span,
        )

    def end_span(self, span: Any, *, output: Optional[dict[str, Any]] = None) -> None:
        self._session.end_span(span, output=output)

    def record_event(self, name: str, metadata: dict[str, Any]) -> None:
        self._session.record_event(name, metadata)

    def complete(self, *, output: Optional[dict[str, Any]] = None) -> None:
        self._session.end_span(self.span, output=output)


class PreenrichTracingSession:
    """Optional Langfuse wrapper for iteration-4 preenrich traces."""

    def __init__(
        self,
        *,
        run_id: str,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self.enabled = False
        self.run_id = run_id
        self.session_id = session_id
        self.trace = None
        self.trace_id = None
        self.trace_url = None
        self._client = None
        self._metadata = _sanitize_langfuse_payload(metadata)
        self._lock = threading.RLock()
        self.job_span = None

        if Langfuse is None:
            return

        config = _langfuse_config()
        if config is None:
            return

        try:
            self._client = Langfuse(
                host=config["host"],
                public_key=config["public_key"],
                secret_key=config["secret_key"],
            )
            self.trace_id = self._client.create_trace_id(seed=run_id)
            self.trace = self._client.start_observation(
                trace_context={"trace_id": self.trace_id},
                name="scout.preenrich.run",
                as_type="span",
                input=self._metadata,
                metadata=self._metadata,
            )
            if hasattr(self.trace, "update_trace"):
                self.trace.update_trace(
                    name="scout.preenrich.run",
                    session_id=session_id,
                    input=self._metadata,
                    metadata=self._metadata,
                )
            self.job_span = self.trace.start_observation(
                name="scout.preenrich.job",
                as_type="span",
                input=self._metadata,
                metadata=self._metadata,
            )
            self.trace_url = _resolve_trace_url(self._client, self.trace_id)
            self.enabled = True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse disabled for preenrich run %s: %s", run_id, exc)

    def start_claim_span(self, metadata: dict[str, Any]):
        """Start the canonical claim span."""
        return self._start_span("scout.preenrich.claim", metadata, parent=self.job_span)

    def start_stage_span(self, stage_name: str, metadata: dict[str, Any]):
        """Start the stage execution span for one preenrich stage."""
        span = self._start_span(
            f"scout.preenrich.{stage_name}",
            metadata,
            parent=self.job_span,
        )
        return PreenrichStageTracingHandle(self, stage_name=stage_name, span=span)

    def start_substage_span(self, stage_name: str, substage: str, metadata: dict[str, Any]):
        """Start a stage-internal child span (e.g. research transport sub-call).

        Emitted as `scout.preenrich.<stage_name>.<substage>` so operators can
        see per-sub-call timing inside a stage without duplicating metadata
        assembly in every stage implementation.
        """
        return self._start_span(
            f"scout.preenrich.{stage_name}.{substage}",
            metadata,
            parent=self.job_span,
        )

    def record_event(self, name: str, metadata: dict[str, Any]) -> None:
        """Record one preenrich orchestration event."""
        if not self.trace:
            return
        payload = _sanitize_langfuse_payload(metadata)
        try:
            with self._lock:
                if self._client is not None and self.trace_id is not None:
                    self._client.create_event(
                        trace_context={"trace_id": self.trace_id},
                        name=name,
                        input=payload,
                        output=payload,
                        metadata=payload,
                    )
                    return
                span = self.trace.start_observation(name=name, as_type="span", input=payload, metadata=payload)
                span.update(output=payload)
                span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse preenrich event %s failed: %s", name, exc)

    def end_span(self, span: Any, *, output: Optional[dict[str, Any]] = None) -> None:
        """End a previously started preenrich span."""
        if hasattr(span, "span"):
            span = span.span
        if span is None:
            return
        try:
            with self._lock:
                if output is not None:
                    span.update(output=_sanitize_langfuse_payload(output))
                span.end()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse preenrich span end failed: %s", exc)

    def complete(self, *, output: Optional[dict[str, Any]] = None) -> None:
        """Finalize the preenrich trace."""
        if not self.trace:
            return
        try:
            safe_output = _sanitize_langfuse_payload(output or {})
            with self._lock:
                if self.job_span is not None:
                    self.job_span.update(output=safe_output)
                    self.job_span.end()
                    self.job_span = None
                self.trace.update(output=safe_output)
                if hasattr(self.trace, "update_trace"):
                    self.trace.update_trace(output=safe_output)
                self.trace.end()
                if self._client is not None:
                    self._client.flush()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse preenrich trace finalize failed: %s", exc)

    def _start_span(self, name: str, metadata: dict[str, Any], *, parent: Any = None):
        parent_observation = parent or self.job_span or self.trace
        if not parent_observation:
            return None
        payload = _sanitize_langfuse_payload(metadata)
        try:
            with self._lock:
                return parent_observation.start_observation(
                    name=name,
                    as_type="span",
                    input=payload,
                    metadata=payload,
                )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Langfuse preenrich span %s failed: %s", name, exc)
            return None


def emit_preenrich_sweeper_event(
    *,
    name: str,
    level2_job_id: str,
    metadata: dict[str, Any],
    run_id: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Emit a canonical preenrich sweeper/finalizer event.

    Pins `langfuse_session_id` to `job:<level2_job_id>` and emits the sweeper
    action inside a short-lived `scout.preenrich.run` trace with a real
    `scout.preenrich.job` span. Callers supply the canonical event `name` (e.g.
    `scout.preenrich.enqueue_next`, `scout.preenrich.release_lease`,
    `scout.preenrich.snapshot_invalidation`, `scout.preenrich.finalize_cv_ready`).
    """
    session_id = f"job:{level2_job_id}"
    enriched: dict[str, Any] = {
        "level2_job_id": level2_job_id,
        "langfuse_session_id": session_id,
    }
    enriched.update(metadata or {})
    session = PreenrichTracingSession(
        run_id=run_id
        or f"preenrich:sweeper:{name}:{level2_job_id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}:{uuid4().hex[:8]}",
        session_id=session_id,
        metadata=enriched,
    )
    span = session._start_span(name, enriched, parent=session.job_span)
    session.end_span(span, output=enriched)
    session.complete(output={"status": "completed", "event_name": name, "source": "sweeper"})
    return {"trace_id": session.trace_id, "trace_url": session.trace_url}


def emit_standalone_event(
    *,
    name: str,
    session_id: str,
    metadata: dict[str, Any],
) -> dict[str, Optional[str]]:
    """Emit a standalone trace event when no parent search run is active."""
    if Langfuse is None:
        return {"trace_id": None, "trace_url": None}

    config = _langfuse_config()
    if config is None:
        return {"trace_id": None, "trace_url": None}

    trace_seed = f"{name}:{session_id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}:{uuid4().hex[:8]}"
    payload = _sanitize_langfuse_payload(metadata)
    try:
        client = Langfuse(
            host=config["host"],
            public_key=config["public_key"],
            secret_key=config["secret_key"],
        )
        trace_id = client.create_trace_id(seed=trace_seed)
        trace = client.start_observation(
            trace_context={"trace_id": trace_id},
            name=name,
            as_type="span",
            input=payload,
            metadata=payload,
        )
        trace.update(output=payload)
        trace.end()
        client.create_event(
            trace_context={"trace_id": trace_id},
            name=name,
            input=payload,
            output=payload,
            metadata=payload,
        )
        trace_url = _resolve_trace_url(client, trace_id)
        client.flush()
        return {"trace_id": trace_id, "trace_url": trace_url}
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Langfuse standalone event %s failed: %s", name, exc)
        return {"trace_id": None, "trace_url": None}


def _langfuse_config() -> Optional[dict[str, str]]:
    """Return Langfuse client configuration from environment."""
    host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not (host and public_key and secret_key):
        return None
    return {
        "host": host,
        "public_key": public_key,
        "secret_key": secret_key,
    }


def _resolve_trace_url(client: Any, trace_id: Optional[str]) -> Optional[str]:
    """Resolve a shareable Langfuse trace URL when supported by the SDK."""
    if client is None or trace_id is None:
        return None
    try:
        return client.get_trace_url(trace_id=trace_id)
    except Exception:  # pragma: no cover - best effort
        return None


def _sanitize_langfuse_payload(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Keep Langfuse payloads metadata-first unless full prompt capture is enabled."""
    if not payload:
        return {}
    if os.getenv("LANGFUSE_CAPTURE_FULL_PROMPTS", "false").lower() == "true":
        return payload

    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if _is_prompt_key(key):
            sanitized[key] = _prompt_preview(value)
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_langfuse_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_langfuse_payload(item) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[key] = value
    return sanitized


def _is_prompt_key(key: str) -> bool:
    normalized = key.lower()
    return "prompt" in normalized


def _prompt_preview(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value)
    return {
        "captured": False,
        "preview": text[:160],
        "length": len(text),
    }
