#!/usr/bin/env python3
"""
Configuration verification script for frontend deployment.

Checks that all required environment variables are set correctly.
Run this before deploying to Vercel or after configuration changes.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_required_env_vars():
    """Verify all required environment variables are set."""
    errors = []
    warnings = []

    # Critical variables
    critical_vars = {
        "MONGODB_URI": "MongoDB connection string",
        "FLASK_SECRET_KEY": "Flask session encryption key",
        "LOGIN_PASSWORD": "UI authentication password",
        "RUNNER_URL": "VPS runner service URL",
        "RUNNER_API_SECRET": "Runner service authentication token"
    }

    # Optional but recommended variables
    optional_vars = {
        "FLASK_PORT": "Flask server port (default: 5000)",
        "FLASK_DEBUG": "Debug mode flag (default: false)",
        "FLASK_ENV": "Flask environment (default: production)"
    }

    print("=" * 70)
    print("Frontend Configuration Verification")
    print("=" * 70)
    print()

    # Check critical variables
    print("Critical Environment Variables:")
    print("-" * 70)
    for var_name, description in critical_vars.items():
        value = os.getenv(var_name)
        if not value:
            errors.append(f"❌ {var_name}: NOT SET")
            print(f"❌ {var_name:<25} NOT SET")
            print(f"   → {description}")
        else:
            # Mask sensitive values
            if "SECRET" in var_name or "PASSWORD" in var_name or "KEY" in var_name:
                masked_value = value[:8] + "..." if len(value) > 8 else "***"
            elif "MONGODB_URI" in var_name:
                # Show host but mask credentials
                if "@" in value:
                    masked_value = value.split("@")[1]
                else:
                    masked_value = value[:20] + "..."
            else:
                masked_value = value

            print(f"✅ {var_name:<25} {masked_value}")

    print()

    # Check optional variables
    print("Optional Environment Variables:")
    print("-" * 70)
    for var_name, description in optional_vars.items():
        value = os.getenv(var_name)
        if not value:
            warnings.append(f"⚠️  {var_name}: Using default")
            print(f"⚠️  {var_name:<25} Using default")
            print(f"   → {description}")
        else:
            print(f"✅ {var_name:<25} {value}")

    print()
    print("=" * 70)

    # Test runner service connectivity
    print()
    print("Runner Service Connectivity Test:")
    print("-" * 70)

    runner_url = os.getenv("RUNNER_URL")
    if runner_url:
        import requests
        try:
            response = requests.get(f"{runner_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"✅ Runner service is reachable at {runner_url}")
                health_data = response.json()
                print(f"   Status: {health_data.get('status', 'unknown')}")
                print(f"   Active runs: {health_data.get('active_runs', 'unknown')}")
            else:
                warnings.append(f"⚠️  Runner service returned {response.status_code}")
                print(f"⚠️  Runner service returned HTTP {response.status_code}")
        except requests.ConnectionError:
            errors.append(f"❌ Cannot connect to runner service at {runner_url}")
            print(f"❌ Cannot connect to runner service at {runner_url}")
            print(f"   → Check VPS is running and port 8000 is accessible")
        except requests.Timeout:
            warnings.append(f"⚠️  Runner service timed out")
            print(f"⚠️  Runner service health check timed out (>5s)")
        except Exception as e:
            errors.append(f"❌ Runner health check failed: {str(e)}")
            print(f"❌ Health check failed: {str(e)}")
    else:
        print("⚠️  RUNNER_URL not set - skipping connectivity test")

    print()
    print("=" * 70)

    # Summary
    print()
    print("Summary:")
    print("-" * 70)

    if errors:
        print(f"❌ {len(errors)} critical error(s) found:")
        for error in errors:
            print(f"   {error}")
        print()
        print("RECOMMENDATION: Fix all critical errors before deploying to production")
        return False

    if warnings:
        print(f"⚠️  {len(warnings)} warning(s) found:")
        for warning in warnings:
            print(f"   {warning}")
        print()
        print("RECOMMENDATION: Review warnings and configure optional settings")

    if not errors and not warnings:
        print("✅ All configuration checks passed!")
        print()
        print("READY FOR DEPLOYMENT")

    print("=" * 70)

    return len(errors) == 0


if __name__ == "__main__":
    success = check_required_env_vars()
    sys.exit(0 if success else 1)
