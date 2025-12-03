"""
Redis helper for user-isolated data storage.
Ensures each user's data is stored separately in Redis.
"""

import os
import redis
import json
import logging
from typing import Any, Optional
from auth_middleware import auth_manager

logger = logging.getLogger(__name__)


class UserIsolatedRedis:
    """Redis client with user-specific data isolation"""
    
    def __init__(self):
        try:
            self.client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
            # Test connection
            self.client.ping()
            logger.info("✓ UserIsolatedRedis initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            self.client = None
    
    def get_user_key(self, token: str, key: str) -> str:
        """Generate user-specific key"""
        return auth_manager.get_user_data_key(token, key)
    
    def set_user_data(self, token: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set user-specific data"""
        if not self.client:
            logger.warning("Redis client not available")
            return False
        
        try:
            user_key = self.get_user_key(token, key)
            serialized = json.dumps(value)
            
            if ttl:
                self.client.setex(user_key, ttl, serialized)
            else:
                self.client.set(user_key, serialized)
            
            logger.debug(f"Saved user data: {user_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to set user data: {e}")
            return False
    
    def get_user_data(self, token: str, key: str) -> Optional[Any]:
        """Get user-specific data"""
        if not self.client:
            logger.warning("Redis client not available")
            return None
        
        try:
            user_key = self.get_user_key(token, key)
            data = self.client.get(user_key)
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get user data: {e}")
            return None
    
    def delete_user_data(self, token: str, key: str) -> bool:
        """Delete user-specific data"""
        if not self.client:
            logger.warning("Redis client not available")
            return False
        
        try:
            user_key = self.get_user_key(token, key)
            self.client.delete(user_key)
            logger.debug(f"Deleted user data: {user_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete user data: {e}")
            return False
    
    def get_all_user_keys(self, token: str, pattern: str = "*") -> list:
        """Get all keys for a user matching pattern"""
        if not self.client:
            return []
        
        try:
            user_id = auth_manager.get_session_user(token) if token else "anonymous"
            search_pattern = f"user:{user_id}:{pattern}"
            keys = self.client.keys(search_pattern)
            return keys
        except Exception as e:
            logger.error(f"Failed to get user keys: {e}")
            return []


# Global instance
redis_helper = UserIsolatedRedis()
