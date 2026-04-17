# Commander-4 (Joyia) — Enterprise AI Workflow Platform
description: Enterprise AI workflow platform at ProSiebenSat.1 serving 2,000 users with 42 plugins - governed structured outputs, MCP integrations, per-silo guardrails/access control, hybrid retrieval, semantic caching, and evaluation harnesses
stack: TypeScript, Python, S3 Vectors, LiteLLM, Redis, DynamoDB, SQS, Vercel AI SDK, Zod, MCP, Vitest, text-embedding-3-small

## Bullets
- Designed governed structured-output architecture using Zod schema validation for all LLM responses, 5 MCP server tools for external integrations, 42 workflow plugins with per-silo guardrail injection via LiteLLM proxy, and access-control-aware workflow behavior.
- Implemented retrieval evaluation harness with MRR@k and NDCG@k (exponential gain) scoring functions, guardrail profiles for per-silo content policy enforcement, and two-tier semantic cache threshold tuning validated against 14 unit tests.
- Built hybrid retrieval pipeline combining BM25 scoring from scratch (no inverted index on S3 Vectors - corpus statistics computed in-memory) with RRF fusion (k=60) and LLM-as-judge reranking via Claude Sonnet/LiteLLM with parallel Promise.all execution.
- Engineered two-tier semantic caching with L1 exact-match and L2 semantic similarity using Redis TTL plus S3 Vectors cosine search, improving runtime efficiency for repeated and paraphrased prompts.
- Engineered document ingestion pipeline processing Confluence XML (macro stripping, metadata extraction) and Jira ADF to markdown conversion with sentence-boundary chunking (500-token windows, 50-token overlap), SHA-256 change detection for incremental updates, and RAPTOR hierarchical indexing for multi-granularity retrieval.
