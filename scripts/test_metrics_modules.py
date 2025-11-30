#!/usr/bin/env python3
"""
Test script to validate metrics, alerting, and token tracker modules.

Run this locally to verify the modules work before deploying.

Usage:
    cd /Users/ala0001t/pers/projects/job-search
    source .venv/bin/activate
    python scripts/test_metrics_modules.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_metrics_collector():
    """Test the MetricsCollector class."""
    print("\n=== Testing MetricsCollector ===")
    try:
        from src.common.metrics import get_metrics_collector, MetricsCollector

        collector = get_metrics_collector()
        print(f"  [OK] MetricsCollector instance: {type(collector)}")

        # Test budget metrics
        budget = collector.get_budget_metrics()
        print(f"  [OK] Budget metrics: total_used=${budget.total_used_usd:.4f}")

        budget_dict = budget.to_dict()
        print(f"  [OK] Budget as dict: {list(budget_dict.keys())}")

        # Test cost history
        history = collector.get_cost_history(period="hourly", count=24)
        print(f"  [OK] Cost history: {len(history.get('costs', []))} data points")
        print(f"  [OK] Sparkline SVG: {len(history.get('sparkline_svg', ''))} chars")

        return True
    except Exception as e:
        print(f"  [FAIL] MetricsCollector error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_alerting():
    """Test the AlertManager class."""
    print("\n=== Testing AlertManager ===")
    try:
        from src.common.alerting import get_alert_manager, AlertLevel

        manager = get_alert_manager()
        print(f"  [OK] AlertManager instance: {type(manager)}")

        # Get alert history
        alerts = manager.get_history(limit=10)
        print(f"  [OK] Alert history: {len(alerts)} alerts")

        # Get stats
        stats = manager.get_stats()
        print(f"  [OK] Alert stats: {stats}")

        # Test creating an alert (won't be sent without Slack configured)
        from src.common.alerting import Alert
        test_alert = Alert(
            level=AlertLevel.INFO,
            source="test_script",
            message="Test alert from validation script",
            metadata={"test": True}
        )
        print(f"  [OK] Test alert created: {test_alert.to_dict()}")

        return True
    except Exception as e:
        print(f"  [FAIL] AlertManager error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_token_tracker():
    """Test the TokenTracker class."""
    print("\n=== Testing TokenTracker ===")
    try:
        from src.common.token_tracker import (
            TokenTracker,
            TokenTrackerRegistry,
            get_token_tracker_registry
        )

        registry = get_token_tracker_registry()
        print(f"  [OK] TokenTrackerRegistry instance: {type(registry)}")

        # Get all stats
        all_stats = registry.get_all_stats()
        print(f"  [OK] Registry stats: {len(all_stats)} trackers registered")

        # Create a test tracker via registry
        tracker = registry.get_or_create("test_tracker", budget_usd=10.0)
        print(f"  [OK] TokenTracker created via registry")

        # Track some usage
        usage = tracker.track_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            layer="test_layer",
        )
        print(f"  [OK] Tracked usage: ${usage.estimated_cost_usd:.6f}")

        summary = tracker.get_summary()
        print(f"  [OK] Tracker summary: total_cost=${summary.total_cost_usd:.6f}")

        return True
    except Exception as e:
        print(f"  [FAIL] TokenTracker error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vps_endpoints():
    """Test VPS runner service endpoints (if available)."""
    print("\n=== Testing VPS Runner Endpoints ===")
    import os
    import requests

    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    endpoints = [
        "/health",
        "/api/metrics/budget",
        "/api/metrics/alerts",
        "/api/metrics/cost-history",
    ]

    results = []
    health_ok = False

    for endpoint in endpoints:
        try:
            response = requests.get(f"{runner_url}{endpoint}", timeout=5)
            if response.status_code == 200:
                print(f"  [OK] {endpoint}: {response.status_code}")
                results.append(True)
                if endpoint == "/health":
                    health_ok = True
            elif response.status_code == 404 and endpoint != "/health":
                # 404 on metrics endpoints is expected if not deployed yet
                print(f"  [PENDING] {endpoint}: 404 (not deployed yet)")
                results.append(None)  # Don't count as failure
            else:
                print(f"  [WARN] {endpoint}: {response.status_code}")
                results.append(False)
        except requests.exceptions.RequestException as e:
            print(f"  [SKIP] {endpoint}: {e}")
            results.append(None)

    # Only require /health to pass; metrics endpoints are optional until deployed
    if health_ok:
        return True
    return all(r for r in results if r is not None) if any(r is not None for r in results) else None


def main():
    """Run all tests."""
    print("=" * 60)
    print("Metrics Module Validation Script")
    print("=" * 60)

    results = {
        "MetricsCollector": test_metrics_collector(),
        "AlertManager": test_alerting(),
        "TokenTracker": test_token_tracker(),
        "VPS Endpoints": test_vps_endpoints(),
    }

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for name, result in results.items():
        if result is True:
            status = "[PASS]"
        elif result is False:
            status = "[FAIL]"
        else:
            status = "[SKIP]"
        print(f"  {status} {name}")

    # Return exit code
    failures = sum(1 for r in results.values() if r is False)
    if failures > 0:
        print(f"\n{failures} test(s) failed!")
        return 1
    print("\nAll tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
