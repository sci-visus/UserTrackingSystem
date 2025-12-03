# Port Configuration

The application now uses environment variables for port configuration, making it easy to customize without modifying code.

## Configuration File

Ports are configured in `/app/.env`:

```env
# Application ports configuration
PANEL_APP_PORT=10565
DZI_SERVER_PORT=10566
```

## How It Works

1. **`.env` file**: Stores the port configuration
2. **`docker-compose.yml`**: Reads the `.env` file and passes values to the container
3. **`start.sh`**: Loads environment variables and uses them to start services
4. **Python scripts**: Use `python-dotenv` to read configuration

## Changing Ports

To change the default ports:

1. Edit **BOTH** `.env` files with the same port values:
   - `/app/.env` (used by Python scripts inside container)
   - `/Docker/.env` (used by docker-compose for port mapping)
   
   ```env
   PANEL_APP_PORT=8080
   DZI_SERVER_PORT=8081
   ```

2. Restart the container:
   ```bash
   cd Docker
   docker compose down
   docker compose up -d
   ```

   **Note:** You only need `--build` flag if you changed the code, not for port changes.

## Important: Two .env Files

The application uses **two** `.env` files:

- **`/Docker/.env`**: Used by `docker-compose.yml` for port mapping (host ↔ container)
- **`/app/.env`**: Used by Python scripts inside the container

**Both files must have the same port values!**

### Quick Update Script

To update both files at once:
```bash
echo "PANEL_APP_PORT=8080
DZI_SERVER_PORT=8081" | tee app/.env Docker/.env
```

## Default Values

If the `.env` file is missing or variables are not set, the system uses these defaults:
- Panel App Port: `10565`
- DZI Server Port: `10566`

## Components Using Port Configuration

- **Panel App** (`annotation_tool.py`): Main annotation interface
- **DZI Server** (`dzi_server.py`): Serves image tiles
- **Docker Compose**: Maps host ports to container ports
- **Start Script** (`start.sh`): Launches services with correct ports

## Architecture

```
.env file
   ↓
docker-compose.yml (reads .env)
   ↓
Container Environment Variables
   ↓
start.sh (exports variables)
   ↓
Python scripts (load with python-dotenv)
   ↓
Services running on configured ports
```
