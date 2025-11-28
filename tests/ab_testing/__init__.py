"""
A/B Testing Framework for Prompt Optimization.

This package provides infrastructure for testing prompt improvements
across Layer 4 (Opportunity Mapper), Layer 6a (Cover Letter), and
Layer 6b (CV Generator).

Usage:
    pytest tests/ab_testing/ -v

Structure:
    - framework.py: ABTestRunner class for running and comparing prompts
    - scorers.py: Scoring functions (specificity, grounding, hallucinations)
    - conftest.py: Shared fixtures (test jobs, runners)
    - fixtures/: JSON test job data
    - test_layer*_ab.py: A/B tests for each layer
"""

from .framework import ABTestRunner, ABTestResult, Comparison
from .scorers import score_specificity, score_grounding, score_hallucinations

__all__ = [
    "ABTestRunner",
    "ABTestResult",
    "Comparison",
    "score_specificity",
    "score_grounding",
    "score_hallucinations",
]
