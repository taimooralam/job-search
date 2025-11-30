#!/bin/bash
# Fix runner service - expose port and restart

cd /root/job-runner

# Backup current config
cp docker-compose.runner.yml docker-compose.runner.yml.backup

# Write new config with proper indentation
cat > docker-compose.runner.yml << 'EOF'
version: "3.9"

services:
  runner:
    image: ${RUNNER_IMAGE:-ghcr.io/taimooralam/job-search/runner:latest}
    build:
      context: .
      dockerfile: Dockerfile.runner
    env_file:
      - .env
    environment:
      - MAX_CONCURRENCY=3
      - LOG_BUFFER_LIMIT=500
      - PIPELINE_TIMEOUT_SECONDS=600
      - PDF_SERVICE_URL=http://pdf-service:8001
    ports:
      - "0.0.0.0:8000:8000"
    volumes:
      - ./applications:/app/applications
      - ./credentials:/app/credentials:ro
      - ./master-cv.md:/app/master-cv.md:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    depends_on:
      pdf-service:
        condition: service_healthy
    networks:
      - job-pipeline
      - n8n-prod_default

  pdf-service:
    image: ${PDF_SERVICE_IMAGE:-ghcr.io/taimooralam/job-search/pdf-service:latest}
    build:
      context: .
      dockerfile: Dockerfile.pdf-service
    environment:
      - PYTHONUNBUFFERED=1
      - PLAYWRIGHT_HEADLESS=true
      - PLAYWRIGHT_TIMEOUT=30000
      - MAX_CONCURRENT_PDFS=5
      - LOG_LEVEL=INFO
    expose:
      - "8001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 15s
      retries: 5
      start_period: 90s
    restart: unless-stopped
    networks:
      - job-pipeline

networks:
  job-pipeline:
    driver: bridge
  n8n-prod_default:
    external: true
EOF

echo "Config updated. Restarting services..."

# Restart services
docker compose -f docker-compose.runner.yml down
docker compose -f docker-compose.runner.yml up -d

# Wait for startup
echo "Waiting for services to start..."
sleep 10

# Test
echo "Testing health endpoint..."
curl http://72.61.92.76:8000/health

echo ""
echo "Done! If you see JSON above, it's working."
