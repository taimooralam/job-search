# Commander-4 (Joyia) — Enterprise AI Workflow Platform
description: Enterprise AI workflow platform at ProSiebenSat.1 serving 2,000 users with 42 plugins — hybrid retrieval, document ingestion, structured outputs, and semantic caching
stack: TypeScript, Python, S3 Vectors, LiteLLM, Redis, DynamoDB, SQS, Vercel AI SDK, Zod, MCP, Vitest, text-embedding-3-small

## Bullets
- Engineered document ingestion pipeline processing Confluence XML (macro stripping, metadata extraction) and Jira ADF→markdown conversion with sentence-boundary chunking (500-token windows, 50-token overlap), SHA-256 change detection for incremental updates, and RAPTOR hierarchical indexing for multi-granularity retrieval.
- Built hybrid retrieval pipeline combining BM25 scoring from scratch (no inverted index on S3 Vectors — corpus statistics computed in-memory) with RRF fusion (k=60) and LLM-as-judge reranking via Claude Sonnet/LiteLLM with parallel Promise.all execution.
- Implemented retrieval evaluation harness with MRR@k and NDCG@k (exponential gain) scoring functions, guardrail profiles for per-silo content policy enforcement, and two-tier semantic cache threshold tuning validated against 14 unit tests.
- Designed structured output architecture using Zod schema validation for all LLM responses, 5 MCP server tools for external integrations, 42 workflow plugins with per-silo guardrail injection via LiteLLM proxy, and per-silo access control.
