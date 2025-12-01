"""
Performance Benchmarks (GAP-042).

This module provides benchmark tests to establish baseline metrics and detect
performance regressions in the job search pipeline.

Usage:
    # Run all benchmarks
    pytest tests/benchmarks -v --benchmark

    # Run specific benchmark suite
    pytest tests/benchmarks/test_pipeline_benchmarks.py -v

    # Run with baseline comparison
    pytest tests/benchmarks --benchmark-compare

Target Latencies (p95):
- Layer 1-4 (JD Extractor): < 3s
- Layer 2 (Pain Point Miner): < 5s
- Layer 3.0 (Company Researcher): < 8s (with FireCrawl)
- Layer 3.5 (Role Researcher): < 3s
- Layer 4 (Opportunity Mapper): < 3s
- Layer 5 (People Mapper): < 10s (with FireCrawl)
- Layer 6 (CV Generator V2): < 15s
- Layer 7 (Output Publisher): < 2s
- Full Pipeline: < 60s
- PDF Generation: < 5s
- MongoDB Query: < 100ms
"""
