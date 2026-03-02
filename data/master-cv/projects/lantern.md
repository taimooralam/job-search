# Lantern — LLM Quality Gateway
github: github.com/taimooralam/lantern
stack: FastAPI, Pydantic V2, LiteLLM, Redis, Qdrant, Docker Compose, Prometheus, Grafana, GitHub Actions | Python 3.11, pytest

## Bullets
- Built FastAPI gateway scaffold with Pydantic chat models, health/ready endpoints, request validation, and structured error middleware.
- Added LiteLLM provider configuration loader and model registry to support multi-provider routing setup.
- Provisioned Docker Compose stack (Redis, Qdrant, Prometheus, Grafana) plus GitHub Actions CI and VPS deploy workflow for reproducible environments.
- In progress: implementing fallback routing, semantic cache, Langfuse tracing, rate limiting, and golden-set evaluation to enable quality gates.
