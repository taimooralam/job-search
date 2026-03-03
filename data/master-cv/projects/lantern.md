# Lantern — LLM Quality Gateway
description: Multi-provider LLM gateway with semantic caching, eval-driven quality gates, and cost-aware routing
github: github.com/taimooralam/lantern
stack: FastAPI, Pydantic V2, LiteLLM, Redis, Qdrant, Docker Compose, Prometheus, Grafana, GitHub Actions | Python 3.11, pytest

## Bullets
- Architected multi-provider LLM gateway with LiteLLM routing, model registry, and automatic fallback across OpenAI, Anthropic, and Azure endpoints.
- Built semantic caching layer using Redis + Qdrant vector similarity to deduplicate LLM calls, reducing redundant API spend by ~40% in testing.
- Implemented eval-driven quality gates with golden-set evaluation, scoring LLM responses against reference outputs before serving to downstream consumers.
- Provisioned full observability stack (Prometheus, Grafana, Langfuse tracing) with GitHub Actions CI and VPS deploy workflow for production-grade operations.
