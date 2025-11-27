#!/bin/bash
set -e

# Deployment script for runner service on VPS
# Usage: ./scripts/deploy-runner.sh

VPS_HOST="72.61.92.76"
VPS_USER="root"
PROJECT_DIR="/root/job-search"  # Update this path if different
SERVICE_NAME="job-search-runner"

echo "🚀 Deploying runner service to VPS..."

# SSH into VPS and run deployment commands
ssh ${VPS_USER}@${VPS_HOST} << 'ENDSSH'
    set -e

    echo "📂 Navigating to project directory..."
    cd ${PROJECT_DIR}

    echo "📥 Pulling latest code from git..."
    git pull origin main

    echo "🔍 Current commit:"
    git log --oneline -1

    echo "📦 Installing dependencies (if requirements changed)..."
    source .venv/bin/activate
    pip install -q -r requirements.txt

    echo "🔄 Restarting runner service..."
    # Try Docker Compose first
    if [ -f "docker-compose.yml" ]; then
        echo "   Using Docker Compose..."
        docker-compose restart runner
    # Try systemd
    elif systemctl list-units --type=service | grep -q "${SERVICE_NAME}"; then
        echo "   Using systemd..."
        sudo systemctl restart ${SERVICE_NAME}
    # Manual restart with uvicorn
    else
        echo "   Using uvicorn (manual)..."
        pkill -f "uvicorn runner_service.app" || true
        sleep 2
        nohup .venv/bin/uvicorn runner_service.app:app --host 0.0.0.0 --port 8000 > runner.log 2>&1 &
        echo "   Started with PID: $!"
    fi

    echo "⏳ Waiting for service to start..."
    sleep 3

    echo "✅ Verifying service health..."
    curl -f http://localhost:8000/health || echo "❌ Health check failed!"

    echo "🎉 Deployment complete!"
ENDSSH

echo ""
echo "✅ Runner service deployed successfully!"
echo "🔗 Test at: http://72.61.92.76:8000/health"
