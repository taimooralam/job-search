# Job Ingestion Service Dockerfile
# Runs automated job discovery from Indeed (JobSpy) and Himalayas
# Scheduled via cron every 6 hours

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - cron for scheduling
# - curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY scripts/ingest_jobs_cron.py ./scripts/

# Create logs directory
RUN mkdir -p /app/logs

# Copy cron configuration
COPY docker/job-ingest/crontab /etc/cron.d/job-ingest
RUN chmod 0644 /etc/cron.d/job-ingest && \
    crontab /etc/cron.d/job-ingest

# Copy entrypoint script
COPY docker/job-ingest/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables (override in docker-compose or .env)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Healthcheck - verify last run was within 12 hours
HEALTHCHECK --interval=6h --timeout=30s --start-period=1m --retries=2 \
    CMD python -c "import json, os; from datetime import datetime, timedelta; \
        f='/app/logs/ingest_latest.json'; \
        d=json.load(open(f)) if os.path.exists(f) else {}; \
        t=datetime.fromisoformat(d.get('end_time','2000-01-01')); \
        exit(0 if datetime.utcnow()-t < timedelta(hours=12) else 1)"

# Run cron in foreground
ENTRYPOINT ["/entrypoint.sh"]
