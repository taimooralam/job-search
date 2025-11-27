#!/usr/bin/env python3
"""
Test MongoDB connection with retry logic.

Usage:
    cd /Users/ala0001t/pers/projects/job-search
    source .venv/bin/activate
    python test_mongodb_connection.py
"""

import os
import sys
import time
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")

if not MONGO_URI:
    print("❌ Error: MONGODB_URI not found in .env file")
    sys.exit(1)

# Hide credentials in output
uri_display = MONGO_URI[:30] + "..." if len(MONGO_URI) > 30 else MONGO_URI


def test_connection_with_retry():
    """Test MongoDB connection with same retry logic as app.py."""
    max_retries = 3
    retry_delay = 2  # seconds

    print(f"🔍 Testing MongoDB connection...")
    print(f"   URI: {uri_display}")
    print()

    for attempt in range(max_retries):
        try:
            print(f"📡 Attempt {attempt + 1}/{max_retries}: Connecting to MongoDB...")

            # Set shorter timeouts to fail fast (5s instead of 30s default)
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=5000,
                socketTimeoutMS=5000
            )

            # Test connection with ping
            start_time = time.time()
            result = client.admin.command('ping')
            elapsed = time.time() - start_time

            if result.get('ok') == 1:
                print(f"✅ MongoDB connection successful! (took {elapsed:.2f}s)")
                print()

                # Test database access
                db = client["jobs"]
                collections = db.list_collection_names()
                print(f"✅ Database 'jobs' accessible")
                print(f"   Collections: {', '.join(collections[:5])}" + ("..." if len(collections) > 5 else ""))
                print()

                # Test query
                level2_count = db["level-2"].count_documents({})
                print(f"✅ Query test successful")
                print(f"   level-2 collection: {level2_count} documents")
                print()

                client.close()
                return True

        except (ConfigurationError, ServerSelectionTimeoutError) as e:
            error_str = str(e)
            is_dns_error = (
                "DNS" in error_str or
                "resolution lifetime expired" in error_str or
                "getaddrinfo failed" in error_str
            )

            if is_dns_error:
                print(f"⚠️  DNS resolution failed")
                if attempt < max_retries - 1:
                    print(f"   Retrying in {retry_delay}s...")
                    print()
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print()
                    print(f"❌ MongoDB connection failed after {max_retries} attempts")
                    print()
                    print("DNS Error Details:")
                    print(f"   {error_str[:200]}...")
                    print()
                    print("Troubleshooting Steps:")
                    print()
                    print("1. Flush DNS cache:")
                    print("   sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder")
                    print()
                    print("2. Verify DNS resolution:")
                    print("   nslookup cluster0.mongodb.net")
                    print("   (Should show IP addresses, not timeout)")
                    print()
                    print("3. Change DNS servers to Google DNS:")
                    print("   System Settings → Network → Wi-Fi → Details → DNS")
                    print("   Add: 8.8.8.8, 8.8.4.4, 1.1.1.1")
                    print()
                    print("4. Check current DNS servers:")
                    print("   scutil --dns | grep 'nameserver\\[0\\]'")
                    print("   (Should NOT show 100.64.0.2 - that's VPN DNS)")
                    print()
                    return False
            else:
                print(f"❌ MongoDB connection error (non-DNS):")
                print(f"   {error_str[:200]}...")
                print()
                return False

        except Exception as e:
            print(f"❌ Unexpected error:")
            print(f"   {type(e).__name__}: {str(e)[:200]}...")
            print()
            return False

    return False


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("MongoDB Connection Test")
    print("=" * 70)
    print()

    success = test_connection_with_retry()

    if success:
        print("=" * 70)
        print("✅ All tests passed! MongoDB connection is working.")
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Start Flask app: cd frontend && python app.py")
        print("  2. Open browser: http://localhost:5001")
        print()
        sys.exit(0)
    else:
        print("=" * 70)
        print("❌ Tests failed. Fix DNS issues and retry.")
        print("=" * 70)
        print()
        sys.exit(1)
