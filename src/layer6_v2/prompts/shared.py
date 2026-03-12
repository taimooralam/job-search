"""
Shared prompt constants for CV Gen V2.

Single source of truth for rules that appear across multiple prompts,
preventing drift and enabling single-point compression.
"""

ANTI_HALLUCINATION_RULES = """=== CRITICAL: ANTI-HALLUCINATION RULES ===

SOURCE OF TRUTH: "Source material" means ONLY the candidate's MASTER CV and ROLE ACHIEVEMENTS.
JD pain points, JD keywords, and JD technical skills are ALIGNMENT TARGETS — use them to
decide WHICH achievements to highlight and HOW to frame them, but NEVER as source for claims.

1. ONLY use achievements/skills that appear in the candidate's ROLE ACHIEVEMENTS (not from JD)
2. ONLY use metrics/numbers that appear EXACTLY in the role achievements (no rounding, no inventing)
3. If source lacks a metric, describe the outcome qualitatively WITHOUT inventing numbers
4. NEVER add technologies, platforms, or tools from the JD that are NOT in the candidate's role achievements
5. NEVER swap candidate's actual technologies (e.g., "OpenAI, Anthropic") with JD technologies (e.g., "AWS Bedrock, Gemini")
6. When in doubt about a claim, OMIT IT rather than risk hallucination

EXAMPLE OF VIOLATION:
- Role achievement says: "LiteLLM routing across OpenAI, Anthropic, and Azure endpoints"
- JD mentions: "AWS Bedrock, Google Gemini, Azure ML Studio"
- WRONG: "multi-provider gateway across AWS Bedrock, Azure ML Studio, and Google Gemini"
- RIGHT: "multi-provider gateway across OpenAI, Anthropic, and Azure endpoints" """
