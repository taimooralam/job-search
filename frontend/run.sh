#!/bin/bash
# Run the Job Search UI locally
#
# Usage:
#   ./frontend/run.sh              # Start the server
#   ./frontend/run.sh --seed       # Seed sample data first, then start
#   ./frontend/run.sh --seed-only  # Just seed data, don't start server
#   ./frontend/run.sh --test       # Run tests only

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the project root directory (parent of frontend/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  Job Search UI - Local Runner${NC}"
echo -e "${BLUE}======================================${NC}"

# Change to project root
cd "$PROJECT_ROOT"

# Check if .venv exists, create if not
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source .venv/bin/activate

# Install dependencies if needed
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q flask pymongo python-dotenv pytest pytest-mock
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Warning: No .env file found.${NC}"
    echo -e "${YELLOW}Copy .env.example and configure MONGODB_URI:${NC}"
    echo -e "  cp .env.example .env"
    echo ""
fi

# Parse command line arguments
case "$1" in
    --seed)
        echo -e "${GREEN}Seeding sample jobs...${NC}"
        python -m frontend.seed_jobs --count 20
        echo ""
        echo -e "${GREEN}Starting server...${NC}"
        python -m frontend.app
        ;;
    --seed-only)
        echo -e "${GREEN}Seeding sample jobs...${NC}"
        python -m frontend.seed_jobs --count 20
        echo -e "${GREEN}Done! Run './frontend/run.sh' to start the server.${NC}"
        ;;
    --seed-clear)
        echo -e "${GREEN}Clearing and seeding sample jobs...${NC}"
        python -m frontend.seed_jobs --clear --count 20
        echo ""
        echo -e "${GREEN}Starting server...${NC}"
        python -m frontend.app
        ;;
    --test)
        echo -e "${GREEN}Running tests...${NC}"
        python -m pytest frontend/tests/ -v
        ;;
    --help|-h)
        echo "Usage: ./frontend/run.sh [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  (none)        Start the server"
        echo "  --seed        Seed 20 sample jobs, then start server"
        echo "  --seed-clear  Clear all jobs, seed 20 new ones, then start"
        echo "  --seed-only   Just seed data, don't start server"
        echo "  --test        Run tests only"
        echo "  --help, -h    Show this help message"
        echo ""
        echo "Environment:"
        echo "  FLASK_PORT    Server port (default: 5000)"
        echo "  FLASK_DEBUG   Enable debug mode (default: true)"
        echo "  MONGODB_URI   MongoDB connection string"
        ;;
    *)
        echo -e "${GREEN}Starting server...${NC}"
        echo -e "Open ${BLUE}http://localhost:${FLASK_PORT:-5000}${NC} in your browser"
        echo ""
        python -m frontend.app
        ;;
esac
