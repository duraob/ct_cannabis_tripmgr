"""
Simple in-memory cache for API responses
Minimal implementation for 2-3 users - no external dependencies
"""
import time
from typing import Optional, Dict, Any

# Simple cache storage: {key: {'data': value, 'expires_at': timestamp}}
_cache: Dict[str, Dict[str, Any]] = {}

def get(key: str) -> Optional[Any]:
    """Get value from cache if not expired"""
    if key not in _cache:
        return None
    
    entry = _cache[key]
    if time.time() > entry['expires_at']:
        # Expired - remove and return None
        del _cache[key]
        return None
    
    return entry['data']

def set(key: str, value: Any, ttl_seconds: int = 300):
    """Set value in cache with TTL (time to live) in seconds"""
    _cache[key] = {
        'data': value,
        'expires_at': time.time() + ttl_seconds
    }

def clear(key: str = None):
    """Clear cache entry or all cache if key is None"""
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()
