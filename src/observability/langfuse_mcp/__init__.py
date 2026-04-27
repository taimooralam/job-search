"""Langfuse-backed MCP server.

Read-only tool surface that wraps the Langfuse Public REST API and exposes it
to Claude Code, Codex CLI, and the OpenClaw ``oc`` container via MCP HTTP+SSE.
See ``plans/iteration-4.4-langfuse-mcp-feedback-loop.md`` for the full spec.

Sub-modules
-----------

- :mod:`.aggregations` — pure fingerprint/group/rollup helpers
- :mod:`.client` — async wrapper around the Langfuse REST API
- :mod:`.auth` — bearer-token middleware (constant-time compare, multi-token rotation)
- :mod:`.server` — FastMCP wiring; not yet present in this skeleton
"""
