# Token-Based Authentication Setup

## Overview
The annotation tool now supports secure token-based authentication for multiple users sharing a single port (10333). Each user gets a unique, cryptographically random token (UUID4) to access the dashboard.

## Quick Start

### 1. Generate Tokens
For the current setup with 1 user, your token is already configured in `.env`:
```
USER_TOKENS=user1:a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
```

To generate tokens for additional users (when you expand to 12):
```bash
cd /local/data/magicscan/dev_sam/ink_annotation_tool
python scripts/generate_tokens.py -n 12
```

Copy the generated `USER_TOKENS` line to both:
- `app/.env`
- `Docker/.env`

### 2. Start the Application
```bash
cd Docker
docker-compose down
docker-compose up -d
```

### 3. Access the Dashboard
Current user access URL:
```
http://localhost:10333/annotation_tool?token=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
```

## Configuration

### Environment Variables (in `.env`)

```bash
# Enable/disable authentication
ENABLE_TOKEN_AUTH=true

# Session timeout in seconds (1 hour = 3600)
SESSION_TIMEOUT=3600

# User tokens (comma-separated)
USER_TOKENS=user1:token1,user2:token2,user3:token3,...
```

### Disable Authentication (for testing)
Set in `.env`:
```bash
ENABLE_TOKEN_AUTH=false
```
Then access without token: `http://localhost:10333/annotation_tool`

## Security Features

✅ **Single Port Access** - All users use port 10333, no need for multiple ports
✅ **Cryptographic Tokens** - UUID4 tokens are virtually impossible to guess
✅ **Session Management** - Sessions expire after configured timeout
✅ **User Isolation** - Each user's data is isolated in Redis
✅ **No Sequential Patterns** - Tokens are random, preventing enumeration attacks
✅ **Easy Revocation** - Remove token from USER_TOKENS and restart

## How It Works

1. **Token Validation**: When a user accesses the URL with `?token=xxx`, the token is validated against `USER_TOKENS`
2. **Session Creation**: Valid tokens create a session in Redis with automatic expiration
3. **Data Isolation**: All user data (annotations, progress) is stored with user-specific Redis keys
4. **Session Refresh**: Each request refreshes the session timeout
5. **Access Denial**: Invalid/missing/expired tokens show an error page

## Adding More Users

### Step 1: Generate New Tokens
```bash
python scripts/generate_tokens.py -n 12
```

### Step 2: Update .env Files
Copy the generated `USER_TOKENS` line to:
- `app/.env`
- `Docker/.env`

### Step 3: Restart Container
```bash
cd Docker
docker-compose restart annotation-tool
```

### Step 4: Share URLs
Give each user their unique URL:
```
user1:  http://localhost:10333/annotation_tool?token=a1b2c3d4-...
user2:  http://localhost:10333/annotation_tool?token=b2c3d4e5-...
user3:  http://localhost:10333/annotation_tool?token=c3d4e5f6-...
...
```

## Monitoring & Management

### Check Active Sessions
```bash
docker exec -it ink_annotation_redis redis-cli
> KEYS session:*
> GET session:a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
```

### View User Data
```bash
docker exec -it ink_annotation_redis redis-cli
> KEYS user:user1:*
```

### Clear All Sessions
```bash
docker exec -it ink_annotation_redis redis-cli FLUSHDB
```

## Troubleshooting

### "Access Denied" Page
- Check that token is correct (case-sensitive)
- Verify `ENABLE_TOKEN_AUTH=true` in .env
- Ensure Redis is running: `docker ps | grep redis`
- Check logs: `docker logs ink_annotation_tool`

### Session Expired
- Sessions expire after `SESSION_TIMEOUT` seconds (default 3600 = 1 hour)
- Simply refresh the page - it will create a new session
- Increase timeout in .env if needed

### Token Not Working
- Verify token exists in `USER_TOKENS` in .env
- Restart container after changing .env: `docker-compose restart`
- Check for typos or extra spaces in token string

## Best Practices

1. **Keep Tokens Secret** - Treat tokens like passwords
2. **Use HTTPS** - In production, serve over HTTPS to encrypt tokens in transit
3. **Regular Rotation** - Generate new tokens periodically
4. **Monitor Sessions** - Check Redis for suspicious activity
5. **Backup Tokens** - Keep a secure copy of USER_TOKENS

## Future Enhancements

- Token expiration dates
- Admin dashboard for token management
- User activity logging
- IP-based access restrictions
- Two-factor authentication
