# Lantern — LLM Quality Gateway
description: Multi-provider LLM gateway with routing/fallback, semantic caching, eval-driven quality gates, and production observability
github: github.com/taimooralam/lantern
stack: FastAPI, Pydantic V2, LiteLLM, Redis, Qdrant, Docker Compose, Prometheus, Grafana, GitHub Actions | Python 3.11, pytest

## Bullets
- Architected multi-provider LLM gateway with LiteLLM routing, model registry, request validation, and automatic fallback across OpenAI, Anthropic, and Azure endpoints.
- Implemented eval-driven quality gates with golden-set evaluation, scoring LLM responses against reference outputs before serving them to downstream consumers and catching regressions earlier.
- Provisioned full observability stack (Prometheus, Grafana, Langfuse tracing) with GitHub Actions CI and VPS deploy workflow for production-grade operations.
- Built semantic caching layer using Redis + Qdrant vector similarity to deduplicate LLM calls, reducing redundant API spend by ~40% in testing.
- Added operational safeguards around multi-provider routing with request ID propagation, retry/backoff behavior, and circuit-breaker protections for degraded provider conditions.
