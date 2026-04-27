"""Cross-cutting observability primitives shared by preenrich, cv_assembly,
runner, scout and ad-hoc scripts.

The public surface is intentionally tiny. Anything more involved (the MCP
server, the polling subscriptions, the resource renderers) lives under
``src.observability.langfuse_mcp`` and is not re-exported here.
"""

from src.observability.errors import record_error  # noqa: F401  re-export

__all__ = ["record_error"]
