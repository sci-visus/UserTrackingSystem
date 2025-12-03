#!/bin/bash

# Set umask to 0 so all created files are world-readable/writable
umask 0000

# Load environment variables from .env file
if [ -f "app/.env" ]; then
    export $(grep -v '^#' app/.env | xargs)
    echo "✓ Environment variables loaded from .env"
fi

# Set default values if not defined
export PANEL_APP_PORT=${PANEL_APP_PORT:-10565}
export DZI_SERVER_PORT=${DZI_SERVER_PORT:-10566}

echo "Configuration:"
echo "  Panel App Port: $PANEL_APP_PORT"
echo "  DZI Server Port: $DZI_SERVER_PORT"
echo ""

# Fix permissions for data directories to allow editing from host
# Run in background to avoid blocking startup
if [ -d "/data/dzi_output" ]; then
    echo "Fixing permissions for /data/dzi_output in background..."
    chmod -R 777 /data/dzi_output &
fi

if [ -d "/data/anno" ]; then
    echo "Fixing permissions for /data/anno in background..."
    chmod -R 777 /data/anno &
fi

echo "Starting DZI static file server on port $DZI_SERVER_PORT..."
# Start DZI static file server in background
python app/dzi_server.py &

echo "Starting Panel app on port $PANEL_APP_PORT..."
# Start Panel app (this runs in foreground to keep container alive)
panel serve app/app.py \
  --address 0.0.0.0 \
  --port $PANEL_APP_PORT \
  --allow-websocket-origin "localhost:$PANEL_APP_PORT" \
  --allow-websocket-origin "127.0.0.1:$PANEL_APP_PORT" \
  --allow-websocket-origin "olympus.sci.utah.edu:$PANEL_APP_PORT"
