# 🎯 Quick Reference Card

## Your Access URL
```
http://localhost:10333/annotation_tool?token=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
```

## Quick Commands

| Task | Command |
|------|---------|
| **Test authentication** | `./scripts/test_auth.sh` |
| **Generate tokens** | `python scripts/generate_tokens.py -n 12` |
| **Restart containers** | `cd Docker && docker compose restart` |
| **View logs** | `docker logs -f ink_annotation_tool` |
| **Stop containers** | `cd Docker && docker compose down` |
| **Start containers** | `cd Docker && docker compose up -d` |
| **Rebuild containers** | `cd Docker && docker compose build` |

## Configuration Files

| File | Purpose |
|------|---------|
| `app/.env` | Main configuration (ports, auth, tokens) |
| `Docker/.env` | Docker environment config |
| `app/auth_middleware.py` | Authentication logic |
| `app/redis_helper.py` | User data isolation |

## Authentication Settings

```bash
# Enable/disable authentication
ENABLE_TOKEN_AUTH=true  # or false

# Session timeout (seconds)
SESSION_TIMEOUT=3600    # 1 hour

# User tokens
USER_TOKENS=user1:token1,user2:token2,...
```

## Adding More Users

1. Generate tokens: `python scripts/generate_tokens.py -n 12`
2. Update `app/.env` with new `USER_TOKENS=...`
3. Update `Docker/.env` with same tokens
4. Rebuild: `cd Docker && docker compose down && docker compose build && docker compose up -d`
5. Share URLs with users

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Access Denied page | Check token in URL is correct |
| Session expired | Refresh page (auto-creates new session) |
| Can't access at all | Check containers: `docker ps` |
| Changes not applied | Rebuild: `docker compose build` |
| Redis issues | Restart Redis: `docker restart ink_annotation_redis` |

## Redis Commands

```bash
# Connect to Redis
docker exec -it ink_annotation_redis redis-cli

# View active sessions
KEYS session:*

# View user data
KEYS user:user1:*

# Clear all sessions
FLUSHDB

# Exit
exit
```

## Port Information

- **10333** - Main annotation tool (Panel)
- **10444** - DZI tile server (Flask)
- **10379** - Redis (internal)

## Security Best Practices

✅ Keep tokens secret (treat like passwords)
✅ Share URLs individually with each user
✅ Use HTTPS in production
✅ Rotate tokens periodically
✅ Monitor Redis for unusual activity

## Documentation

- **Complete Setup**: `AUTH_SETUP.md`
- **Implementation**: `IMPLEMENTATION_SUMMARY.md`
- **This Card**: `QUICK_REFERENCE.md`

---

**Need Help?**
1. Run test: `./scripts/test_auth.sh`
2. Check logs: `docker logs ink_annotation_tool`
3. Review docs: `AUTH_SETUP.md`
