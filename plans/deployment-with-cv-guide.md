# VPS Deployment Guide with HTML CV Integration

> **Note**: This document is deprecated. See:
> - `plans/architecture.md` for system architecture
> - `plans/next-steps.md` for deployment steps

## Summary

The CV generation workflow is integrated into the main pipeline (Layer 6). Key points:

- CV generation uses Anthropic Claude by default (`USE_ANTHROPIC=true`)
- Falls back to OpenRouter or OpenAI if Anthropic unavailable
- Output: `applications/<Company>/<Role>/CV.md`
- Two-pass generation: Evidence JSON extraction then QA pass

See `plans/next-steps.md` Step 1 for LLM provider configuration.
