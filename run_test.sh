#!/bin/bash
# Helper script to run e2e tests using venv

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐍 Using virtual environment (.venv)${NC}"

# Activate venv and run pytest
source .venv/bin/activate

echo -e "${GREEN}✓ venv activated${NC}"
echo -e "${BLUE}🧪 Running e2e tests...${NC}\n"

# Run the test with all arguments passed
.venv/bin/pytest "$@"

# Deactivate after test
deactivate
