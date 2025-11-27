#!/bin/bash
# Convenience script for running E2E tests locally

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Banner
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}CV Editor E2E Tests${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if LOGIN_PASSWORD is set
if [ -z "$LOGIN_PASSWORD" ]; then
    echo -e "${RED}Error: LOGIN_PASSWORD environment variable not set${NC}"
    echo "Please set it before running tests:"
    echo "  export LOGIN_PASSWORD='your-password'"
    exit 1
fi

# Check if Playwright browsers are installed
if ! command -v playwright &> /dev/null; then
    echo -e "${YELLOW}Warning: Playwright CLI not found${NC}"
    echo "Installing Playwright browsers..."
    playwright install
fi

# Parse arguments
BROWSER="chromium"
MODE="headless"
SLOWMO=0
MARKER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --headed)
            MODE="headed"
            shift
            ;;
        --slow)
            SLOWMO=500
            shift
            ;;
        --browser)
            BROWSER="$2"
            shift 2
            ;;
        --mobile)
            MARKER="-m mobile"
            shift
            ;;
        --a11y)
            MARKER="-m accessibility"
            shift
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            exit 1
            ;;
    esac
done

# Build pytest command
CMD="pytest tests/e2e/ -v --browser $BROWSER"

if [ "$MODE" = "headed" ]; then
    CMD="$CMD --headed"
fi

if [ "$SLOWMO" -gt 0 ]; then
    CMD="$CMD --slowmo $SLOWMO"
fi

if [ -n "$MARKER" ]; then
    CMD="$CMD $MARKER"
fi

CMD="$CMD --screenshot on --video retain-on-failure"

# Display configuration
echo -e "${YELLOW}Configuration:${NC}"
echo "  Browser: $BROWSER"
echo "  Mode: $MODE"
echo "  Slow motion: ${SLOWMO}ms"
echo "  Marker: ${MARKER:-all tests}"
echo ""

echo -e "${YELLOW}Running command:${NC}"
echo "  $CMD"
echo ""

# Run tests
echo -e "${GREEN}Starting tests...${NC}"
echo ""

$CMD

# Success message
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Tests completed!${NC}"
echo -e "${GREEN}================================${NC}"
