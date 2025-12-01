#!/bin/bash
set -e

# Export environment variables for cron
# Cron doesn't inherit environment, so we write them to a file
printenv | grep -E '^(MONGODB_URI|OPENROUTER_API_KEY|AUTO_INGEST|INDEED_|HIMALAYAS_|CANDIDATE_PROFILE_PATH)' > /app/.env.cron 2>/dev/null || true

# Source env vars in cron job
sed -i '1i source /app/.env.cron' /etc/cron.d/job-ingest 2>/dev/null || true

echo "========================================"
echo "Job Ingestion Service Starting"
echo "========================================"
echo "Schedule: Every 6 hours (0 */6 * * *)"
echo "MongoDB: ${MONGODB_URI:0:30}..."
echo "Score Threshold: ${AUTO_INGEST_SCORE_THRESHOLD:-70}"
echo "Indeed Terms: ${INDEED_SEARCH_TERMS:-not set}"
echo "Himalayas Keywords: ${HIMALAYAS_KEYWORDS:-not set}"
echo "========================================"

# Run initial ingestion on startup (optional, remove if not wanted)
if [ "${RUN_ON_STARTUP:-false}" = "true" ]; then
    echo "Running initial ingestion..."
    cd /app && python scripts/ingest_jobs_cron.py
fi

# Start cron daemon in foreground
echo "Starting cron daemon..."
exec cron -f
