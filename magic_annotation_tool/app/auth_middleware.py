"""
Token-based authentication middleware for multi-user annotation tool.
Provides token validation, session management, and user isolation.
"""

import os
import redis
from typing import Optional, Dict
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class TokenAuthManager:
    """Manages token-based authentication and user sessions"""
    
    def __init__(self):
        self.enabled = os.getenv('ENABLE_TOKEN_AUTH', 'false').lower() == 'true'
        self.session_timeout = int(os.getenv('SESSION_TIMEOUT', '36000'))
        self.tokens = self._load_tokens()
        
        # Redis connection for session management
        try:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"✓ Connected to Redis for authentication (enabled={self.enabled})")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def _load_tokens(self) -> Dict[str, str]:
        """Load user tokens from environment variable"""
        tokens = {}
        token_string = os.getenv('USER_TOKENS', '')
        
        if token_string:
            for pair in token_string.split(','):
                if ':' in pair:
                    parts = pair.strip().split(':')
                    if len(parts) >= 2:
                        user_id = parts[0]
                        token = parts[1]
                        # Format: user1:token or user1:token:1-247
                        # We only care about user_id and token for authentication
                        tokens[token] = user_id
            logger.info(f"Loaded {len(tokens)} user tokens")
        else:
            logger.warning("No USER_TOKENS found in environment")
        
        return tokens
    
    def validate_token(self, token: str) -> Optional[str]:
        """Validate token and return user_id if valid"""
        if not self.enabled:
            logger.debug("Auth disabled, returning anonymous user")
            return "anonymous"
        
        if not token:
            logger.warning("No token provided")
            return None
        
        user_id = self.tokens.get(token)
        if user_id and self.redis_client:
            # Create/update session in Redis
            session_key = f"session:{token}"
            try:
                self.redis_client.setex(
                    session_key,
                    self.session_timeout,
                    user_id
                )
                logger.info(f"✓ Token validated for user: {user_id}")
            except Exception as e:
                logger.error(f"Failed to create session: {e}")
        elif not user_id:
            logger.warning(f"Invalid token attempted: {token[:8]}...")
        
        return user_id
    
    def get_session_user(self, token: str) -> Optional[str]:
        """Get user from active session"""
        if not self.enabled:
            return "anonymous"
        
        if not token or not self.redis_client:
            return None
        
        session_key = f"session:{token}"
        try:
            user_id = self.redis_client.get(session_key)
            if user_id:
                # Refresh session timeout
                self.redis_client.expire(session_key, self.session_timeout)
            return user_id
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None
    
    def invalidate_session(self, token: str):
        """Invalidate user session"""
        if not self.redis_client:
            return
        
        session_key = f"session:{token}"
        try:
            self.redis_client.delete(session_key)
            logger.info(f"Session invalidated for token: {token[:8]}...")
        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}")
    
    def get_user_data_key(self, token: str, key_suffix: str) -> str:
        """Generate Redis key for user-specific data"""
        user_id = self.get_session_user(token) if token else None
        if not user_id:
            user_id = "anonymous"
        return f"user:{user_id}:{key_suffix}"


# Global instance
auth_manager = TokenAuthManager()


def require_token(func):
    """Decorator to require valid token for functions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = kwargs.get('token')
        
        if auth_manager.enabled:
            user_id = auth_manager.get_session_user(token)
            if not user_id:
                raise PermissionError("Invalid or expired token")
            kwargs['user_id'] = user_id
        else:
            kwargs['user_id'] = 'anonymous'
        
        return func(*args, **kwargs)
    
    return wrapper
