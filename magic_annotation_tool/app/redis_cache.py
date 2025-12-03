import redis
import json
import logging
import os
from typing import Optional, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis cache manager for annotation tool"""
    
    def __init__(self):
        self.host = os.getenv('REDIS_HOST', 'redis')
        self.port = int(os.getenv('REDIS_PORT', 6379))
        self.db = int(os.getenv('REDIS_DB', 0))
        self.ttl = int(os.getenv('REDIS_TTL', 3600))
        
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.client.ping()
            logger.info(f"✓ Redis connected: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.client:
            return None
        
        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        if not self.client:
            return False
        
        try:
            ttl = ttl or self.ttl
            self.client.setex(
                key,
                ttl,
                json.dumps(value)
            )
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.client:
            return False
        
        try:
            self.client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error for {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self.client:
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                count = self.client.delete(*keys)
                logger.info(f"Cache CLEAR: {count} keys matching '{pattern}'")
                return count
            return 0
        except Exception as e:
            logger.error(f"Cache clear error for pattern {pattern}: {e}")
            return 0
    
    def get_metadata(self, image_name: str) -> Optional[dict]:
        """Get cached metadata for an image"""
        return self.get(f"metadata:{image_name}")
    
    def set_metadata(self, image_name: str, metadata: dict) -> bool:
        """Cache metadata for an image (1 hour TTL)"""
        return self.set(f"metadata:{image_name}", metadata, ttl=3600)
    
    def get_annotation(self, image_name: str, annotation_id: str) -> Optional[dict]:
        """Get cached annotation"""
        return self.get(f"annotation:{image_name}:{annotation_id}")
    
    def set_annotation(self, image_name: str, annotation_id: str, data: dict) -> bool:
        """Cache annotation (5 minutes TTL for frequently changing data)"""
        return self.set(f"annotation:{image_name}:{annotation_id}", data, ttl=300)
    
    def clear_image_cache(self, image_name: str) -> int:
        """Clear all cached data for an image"""
        return self.clear_pattern(f"*:{image_name}:*")

    def keys(self, pattern: str) -> list:
        """Get all keys matching pattern"""
        if not self.client:
            return []
        
        try:
            keys = self.client.keys(pattern)
            logger.debug(f"Cache KEYS: {len(keys)} keys matching '{pattern}'")
            return keys
        except Exception as e:
            logger.error(f"Cache keys error for pattern {pattern}: {e}")
            return []

# Global cache instance
cache = RedisCache()