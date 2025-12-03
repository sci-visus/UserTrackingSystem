#!/bin/bash
# Helper script to update port configuration in both .env files

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

APP_ENV="$PROJECT_ROOT/app/.env"
DOCKER_ENV="$SCRIPT_DIR/.env"

echo -e "${YELLOW}Port Configuration Update Tool${NC}"
echo "================================"
echo ""

# Check if arguments provided
if [ $# -eq 2 ]; then
    PANEL_PORT=$1
    DZI_PORT=$2
else
    # Interactive mode
    echo "Current configuration:"
    if [ -f "$APP_ENV" ]; then
        cat "$APP_ENV"
    else
        echo "  (no configuration found)"
    fi
    echo ""
    
    read -p "Enter Panel App Port (default 10565): " PANEL_PORT
    PANEL_PORT=${PANEL_PORT:-10565}
    
    read -p "Enter DZI Server Port (default 10566): " DZI_PORT
    DZI_PORT=${DZI_PORT:-10566}
fi

# Validate ports are numbers
if ! [[ "$PANEL_PORT" =~ ^[0-9]+$ ]] || ! [[ "$DZI_PORT" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}Error: Ports must be numbers${NC}"
    exit 1
fi

# Validate port range
if [ "$PANEL_PORT" -lt 1024 ] || [ "$PANEL_PORT" -gt 65535 ] || [ "$DZI_PORT" -lt 1024 ] || [ "$DZI_PORT" -gt 65535 ]; then
    echo -e "${RED}Error: Ports must be between 1024 and 65535${NC}"
    exit 1
fi

# Check if ports are the same
if [ "$PANEL_PORT" -eq "$DZI_PORT" ]; then
    echo -e "${RED}Error: Panel App and DZI Server ports must be different${NC}"
    exit 1
fi

# Create the configuration content
CONFIG="# Application ports configuration
PANEL_APP_PORT=$PANEL_PORT
DZI_SERVER_PORT=$DZI_PORT"

# Write to both files
echo "$CONFIG" > "$APP_ENV"
echo "$CONFIG" > "$DOCKER_ENV"

echo ""
echo -e "${GREEN}✓ Configuration updated successfully!${NC}"
echo ""
echo "Files updated:"
echo "  - $APP_ENV"
echo "  - $DOCKER_ENV"
echo ""
echo "New configuration:"
echo "  Panel App Port: $PANEL_PORT"
echo "  DZI Server Port: $DZI_PORT"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Restart the container:"
echo "     cd Docker"
echo "     docker compose down &&docker compose up --build -d"
echo ""
echo "  2. Access the application at:"
echo "     http://localhost:$PANEL_PORT/annotation_tool"
