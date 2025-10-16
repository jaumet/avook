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

    The middleware might run in an environment where the public host that
    clients use (for example ``localhost:13378``) differs from the internal
    address the container must call (for example ``audiobookshelf`` on the
    Docker network).  ``ABS_API_BASE_URL`` allows operators to point the
    middleware at the internal address without changing the public-facing
    value used for signed URLs.
    """

    api_base_url = os.getenv("ABS_API_BASE_URL")
    if api_base_url:
        return api_base_url.rstrip("/")

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
    api_token: Optional[str] = field(default=None)
    username: Optional[str] = field(default=None)
    password: Optional[str] = field(default=None)
    timeout: float = field(
        default_factory=lambda: float(os.getenv("ABS_HTTP_TIMEOUT", "5.0"))
    )
    cache_namespace: str = field(
        default_factory=lambda: os.getenv("ABS_CACHE_NAMESPACE", "abs:share")
    )
    cache_ttl: int = field(default_factory=lambda: int(os.getenv("ABS_CACHE_TTL", "600")))

    def __post_init__(self) -> None:
        if self.api_token is None:
            self.api_token = os.getenv("ABS_API_TOKEN")
        if self.username is None:
            self.username = os.getenv("ABS_USERNAME")
        if self.password is None:
            self.password = os.getenv("ABS_PASSWORD")

    def _ensure_token(self) -> None:
        """Authenticate with Audiobookshelf when credentials are configured."""

        if self.api_token or not (self.username and self.password):
            return

        login_url = urljoin(f"{self.base_url}/", "api/login")
        payload = {"username": self.username, "password": self.password}
        try:
            response = httpx.post(login_url, json=payload, timeout=self.timeout)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure
            raise AudiobookshelfUnavailable("Audiobookshelf login failed") from exc

        if response.status_code >= 400:
            raise AudiobookshelfUnavailable(
                f"Audiobookshelf login failed with status {response.status_code}"
            )

        data: Dict[str, Any]
        if "application/json" in response.headers.get("content-type", ""):
            data = response.json()
        else:
            data = {}

        token = data.get("token")
        if not token:
            raise AudiobookshelfUnavailable("Audiobookshelf login did not return a token")

        self.api_token = token

    def _headers(self) -> Dict[str, str]:
        self._ensure_token()
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def with_base_url(self, base_url: str) -> "AudiobookshelfClient":
        """Return a copy of the client that targets ``base_url``."""

        clone = AudiobookshelfClient(
            base_url=base_url,
            api_token=self.api_token,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            cache_namespace=self.cache_namespace,
            cache_ttl=self.cache_ttl,
        )
        return clone

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

        attempted_not_found = False
        last_error_status: Optional[int] = None

        # Audiobookshelf exposes share metadata through two endpoints.  The
        # authenticated ``/api/shares`` route is preferred because it returns
        # richer metadata, but self-hosted installations often disable the
        # public API or require admin authentication.  When the primary call
        # fails due to lack of credentials we fall back to the public share
        # endpoint that powers the hosted share pages.
        for path, kind in (
            (f"api/shares/{share_code}", "admin"),
            (f"api/public/share/{share_code}", "public"),
        ):
            response = self._request(path)

            if response.status_code == 404:
                attempted_not_found = True
                continue

            if response.status_code in {401, 403} and kind == "admin":
                # Authenticated route rejected our request; try the public API
                # without surfacing an error yet.
                last_error_status = response.status_code
                continue

            if response.status_code >= 400:
                last_error_status = response.status_code
                continue

            if "application/json" in response.headers.get("content-type", ""):
                payload = response.json()
            else:  # pragma: no cover - non JSON response
                payload = {"raw": response.text}

            if isinstance(payload, dict):
                # Some responses wrap the share metadata under a "share" key
                # (public API) while others return it at the top level (admin
                # API).  Normalise both forms to the same dictionary.
                candidate = payload.get("share")
                if isinstance(candidate, dict):
                    payload = candidate

                # Occasionally the public endpoint nests the share data inside
                # a ``data`` key; handle that gracefully as well.
                candidate = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(candidate, dict) and "libraryItem" in candidate:
                    payload = candidate
            else:
                payload = {"raw": payload}

            data: Dict[str, Any] = payload  # type: ignore[assignment]

            # Normalise URLs so downstream consumers always receive absolute URLs.
            for key in ("streamUrl", "shareUrl", "webUrl", "coverUrl"):
                if key in data:
                    data[key] = self._absolute(data[key])

            if cache:
                cache.set_json(cache_key, data, ttl=self.cache_ttl)
            return data

        if attempted_not_found and last_error_status in {None, 404}:
            raise AudiobookshelfNotFound(f"Share {share_code!r} was not found")

        status_msg = (
            f"Audiobookshelf responded with status {last_error_status}"
            if last_error_status
            else "Audiobookshelf returned an empty response"
        )
        raise AudiobookshelfUnavailable(status_msg)

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
