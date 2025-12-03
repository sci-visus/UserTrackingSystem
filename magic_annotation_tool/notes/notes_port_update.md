
## Solution Implemented

### 1. Created `/Docker/.env` file
Docker Compose now finds the `.env` file in its directory and uses it for port substitution.

### 2. Created `update_ports.sh` helper script
A convenient script that updates both `.env` files simultaneously:

```bash
cd Docker
./update_ports.sh 10111 10222
```

Or run interactively:
```bash
./update_ports.sh
```

## Correct Workflow for Changing Ports

### Option 1: Using the Helper Script (Recommended)
```bash
cd Docker
./update_ports.sh 8080 8081
docker compose down
docker compose up --build -d
```

### Option 2: Manual Update
```bash
# Update both .env files
echo "PANEL_APP_PORT=8080
DZI_SERVER_PORT=8081" | tee app/.env Docker/.env

# Restart container
cd Docker
docker compose down
docker compose up --build -d
```
