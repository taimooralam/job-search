#!/usr/bin/env python3
"""Trigger CV review for a job via the runner API."""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description="Trigger CV review for a job")
    parser.add_argument("--job-id", required=True, help="MongoDB job _id")
    parser.add_argument("--tier", default="quality", help="Model tier (default: quality)")
    args = parser.parse_args()

    runner_url = os.getenv("RUNNER_URL", "http://job-runner-runner-4:8000")
    secret = os.getenv("RUNNER_API_SECRET", "")

    url = f"{runner_url}/api/jobs/{args.job_id}/operations/cv-review/queue"
    data = json.dumps({"tier": args.tier}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Connection error: {exc.reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
