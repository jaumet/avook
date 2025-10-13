"""Audiobookshelf API client utilities.

This module provides a small synchronous client for talking to an
Audiobookshelf instance.  The middleware uses it to validate that share
codes exist and to produce absolute URLs that can be handed to the
player or an NGINX reverse proxy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from app.cache import get_cache

__all__ = [
    "AudiobookshelfClient",
    "AudiobookshelfError",
    "AudiobookshelfUnavailable",
    "AudiobookshelfNotFound",
]


class AudiobookshelfError(RuntimeError):
    """Base exception for Audiobookshelf integration errors."""


class AudiobookshelfUnavailable(AudiobookshelfError):
    """Raised when the Audiobookshelf service cannot be reached."""


class AudiobookshelfNotFound(AudiobookshelfError):
    """Raised when a requested resource does not exist on Audiobookshelf."""


def _resolve_base_url() -> str:
    """Return the configured Audiobookshelf base URL.

    The configuration accepts either a fully qualified ``ABS_BASE_URL`` or a
    bare ``ABS_HOST`` hostname/host:port pair.  When only the host is
    provided, HTTP is assumed as the scheme which mirrors the development
    docker-compose setup.
    """

    base_url = os.getenv("ABS_BASE_URL")
    if base_url:
        return base_url.rstrip("/")

    host = os.getenv("ABS_HOST", "localhost:13378").strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    scheme = os.getenv("ABS_SCHEME", "http")
    return f"{scheme}://{host}".rstrip("/")


@dataclass
class AudiobookshelfClient:
    """Tiny helper around the Audiobookshelf HTTP API."""

    base_url: str = field(default_factory=_resolve_base_url)
    api_token: Optional[str] = os.getenv("ABS_API_TOKEN")
    timeout: float = float(os.getenv("ABS_HTTP_TIMEOUT", "5.0"))
    cache_namespace: str = os.getenv("ABS_CACHE_NAMESPACE", "abs:share")
    cache_ttl: int = int(os.getenv("ABS_CACHE_TTL", "600"))

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _absolute(self, value: Optional[str]) -> Optional[str]:
        """Return an absolute URL for ``value`` if it is provided."""

        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return urljoin(f"{self.base_url}/", value.lstrip("/"))

    def _request(self, path: str) -> httpx.Response:
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        try:
            response = httpx.get(url, headers=self._headers(), timeout=self.timeout)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure
            raise AudiobookshelfUnavailable("Audiobookshelf is unreachable") from exc
        return response

    def ensure_share_available(self, share_code: str) -> Dict[str, Any]:
        """Return share metadata, raising if the share is not accessible."""

        if not share_code:
            raise AudiobookshelfError("Missing Audiobookshelf share code")

        cache = get_cache()
        cache_key = f"{self.cache_namespace}:{share_code}"
        if cache:
            cached = cache.get_json(cache_key)
            if cached:
                return cached

        response = self._request(f"api/shares/{share_code}")
        if response.status_code == 404:
            raise AudiobookshelfNotFound(f"Share {share_code!r} was not found")
        if response.status_code >= 400:
            raise AudiobookshelfUnavailable(
                f"Audiobookshelf responded with status {response.status_code}"
            )

        if "application/json" in response.headers.get("content-type", ""):
            data: Dict[str, Any] = response.json()
        else:
            data = {"raw": response.text}

        # Normalise URLs so downstream consumers always receive absolute URLs.
        for key in ("streamUrl", "shareUrl", "webUrl", "coverUrl"):
            if key in data:
                data[key] = self._absolute(data[key])
        if cache:
            cache.set_json(cache_key, data, ttl=self.cache_ttl)
        return data

    def health(self) -> Dict[str, Any]:
        """Fetch the Audiobookshelf health endpoint.

        This is primarily useful for diagnostics; the middleware does not
        currently require a healthy response to serve requests, but exposing
        the method simplifies future tests and tooling.
        """

        response = self._request("api/health")
        if response.status_code >= 400:
            raise AudiobookshelfUnavailable(
                f"Audiobookshelf health check failed with {response.status_code}"
            )
        return response.json() if response.headers.get("content-type") == "application/json" else {}

    def build_absolute(self, value: Optional[str]) -> Optional[str]:
        """Public helper mirroring :meth:`_absolute`."""

        return self._absolute(value)
