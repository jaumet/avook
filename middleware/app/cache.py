"""Caching utilities backed by Redis.

This module exposes a lightweight cache abstraction that wraps the
:mod:`redis` client.  It lazily connects to Redis so the application can
boot even when the cache service is temporarily unavailable.  Consumers can
serialise dictionaries to JSON with optional TTLs and the helper gracefully
falls back to ``None`` when operations fail.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import redis
from redis.exceptions import RedisError

__all__ = ["Cache", "get_cache", "override_cache"]


def _default_url() -> str:
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


def _default_ttl() -> int:
    return int(os.getenv("CACHE_DEFAULT_TTL", "300"))


def _client_factory() -> "redis.Redis":
    return redis.Redis.from_url(_default_url(), decode_responses=True)


@dataclass
class Cache:
    """Minimal Redis cache wrapper with JSON helpers."""

    client_factory: Callable[[], "redis.Redis"] = field(default=_client_factory)
    default_ttl: int = field(default_factory=_default_ttl)
    _client: Optional["redis.Redis"] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _get_client(self) -> Optional["redis.Redis"]:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is None:
                try:
                    self._client = self.client_factory()
                except RedisError:
                    return None
        return self._client

    def get_json(self, key: str) -> Optional[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None
        try:
            raw = client.get(key)
        except RedisError:
            return None
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(value, dict):
            return value
        return None

    def set_json(self, key: str, value: dict[str, Any], ttl: Optional[int] = None) -> bool:
        client = self._get_client()
        if client is None:
            return False
        payload = json.dumps(value)
        ttl = ttl if ttl is not None else self.default_ttl
        try:
            if ttl and ttl > 0:
                client.setex(key, ttl, payload)
            else:
                client.set(key, payload)
        except RedisError:
            return False
        return True

    def delete(self, key: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.delete(key)
        except RedisError:
            return False
        return True


_CACHE: Optional[Cache] = None


def get_cache() -> Optional[Cache]:
    """Return the global cache instance, honouring ``CACHE_DISABLED``."""

    if os.getenv("CACHE_DISABLED", "0").lower() in {"1", "true", "yes"}:
        return None
    global _CACHE
    if _CACHE is None:
        _CACHE = Cache()
    return _CACHE


def override_cache(cache: Optional[Cache]) -> Optional[Cache]:
    """Replace the global cache, returning the previous value."""

    global _CACHE
    previous = _CACHE
    _CACHE = cache
    return previous
