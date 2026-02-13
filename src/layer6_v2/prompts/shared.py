"""
Shared prompt constants for CV Gen V2.

Single source of truth for rules that appear across multiple prompts,
preventing drift and enabling single-point compression.
"""

ANTI_HALLUCINATION_RULES = """=== CRITICAL: ANTI-HALLUCINATION RULES ===

1. ONLY use achievements/skills that appear in the PROVIDED source material
2. ONLY use metrics/numbers that appear EXACTLY in the source (no rounding, no inventing)
3. If source lacks a metric, describe the outcome qualitatively WITHOUT inventing numbers
4. NEVER add companies, dates, technologies, or achievements not in source
5. When in doubt about a claim, OMIT IT rather than risk hallucination"""
