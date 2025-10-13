"""Monitoring utilities with structured logging support."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

__all__ = [
    "configure_logging",
    "RequestMonitoringMiddleware",
    "Telemetry",
    "get_telemetry",
    "override_telemetry",
    "override_publisher",
    "InMemoryLogPublisher",
]


_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialise_record(record: logging.LogRecord, app_name: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "app": app_name,
        "timestamp": _now_iso(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    extras = {
        key: value
        for key, value in record.__dict__.items()
        if key not in _LOG_RECORD_ATTRS and not key.startswith("_")
    }
    if extras:
        payload.update(extras)
    if record.exc_info:
        payload["exc_info"] = logging.Formatter().formatException(record.exc_info)
    return payload


class _JsonConsoleHandler(logging.StreamHandler):
    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin wrapper
        try:
            payload = _serialise_record(record, self.app_name)
            msg = json.dumps(payload, ensure_ascii=False)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:  # noqa: BLE001 - logging should never raise
            self.handleError(record)


class BaseLogPublisher:
    @property
    def is_enabled(self) -> bool:
        raise NotImplementedError

    def publish(self, payload: Mapping[str, Any]) -> bool:
        raise NotImplementedError


@dataclass
class HttpLogPublisher(BaseLogPublisher):
    url: Optional[str] = None
    timeout: float = 2.0
    _client: Optional[httpx.Client] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def is_enabled(self) -> bool:
        return bool(self.url or os.getenv("LOG_AGGREGATOR_URL"))

    def _get_url(self) -> Optional[str]:
        if self.url:
            return self.url
        self.url = os.getenv("LOG_AGGREGATOR_URL")
        return self.url

    def publish(self, payload: Mapping[str, Any]) -> bool:
        url = self._get_url()
        if not url:
            return False
        try:
            client = self._get_client()
            client.post(url, json=payload)
        except httpx.HTTPError:
            return False
        return True

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(timeout=self.timeout)
        return self._client


@dataclass
class InMemoryLogPublisher(BaseLogPublisher):
    records: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def is_enabled(self) -> bool:
        return True

    def publish(self, payload: Mapping[str, Any]) -> bool:
        self.records.append(dict(payload))
        return True


class _CentralisedLogHandler(logging.Handler):
    def __init__(self, publisher: BaseLogPublisher, app_name: str):
        super().__init__()
        self.publisher = publisher
        self.app_name = app_name

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin wrapper
        try:
            payload = _serialise_record(record, self.app_name)
            self.publisher.publish(payload)
        except Exception:  # noqa: BLE001
            self.handleError(record)


@dataclass
class EndpointStats:
    total_requests: int = 0
    error_requests: int = 0
    total_duration: float = 0.0
    max_duration: float = 0.0

    def record(self, status_code: int, duration: float) -> None:
        self.total_requests += 1
        self.total_duration += duration
        if duration > self.max_duration:
            self.max_duration = duration
        if status_code >= 500:
            self.error_requests += 1

    def snapshot(self) -> Dict[str, Any]:
        average = 0.0
        if self.total_requests:
            average = self.total_duration / self.total_requests
        return {
            "total_requests": self.total_requests,
            "error_requests": self.error_requests,
            "average_duration_ms": round(average * 1000, 3),
            "max_duration_ms": round(self.max_duration * 1000, 3),
        }


@dataclass
class Telemetry:
    app_name: str = "audiovook-middleware"
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _endpoints: Dict[str, EndpointStats] = field(default_factory=dict)

    def record(self, method: str, path: str, status_code: int, duration: float) -> None:
        key = f"{method.upper()} {path}"
        with self._lock:
            stats = self._endpoints.setdefault(key, EndpointStats())
            stats.record(status_code, duration)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            endpoints = {key: stats.snapshot() for key, stats in self._endpoints.items()}
            total_requests = sum(item["total_requests"] for item in endpoints.values())
            error_requests = sum(item["error_requests"] for item in endpoints.values())
            total_duration = sum(
                stats.total_duration for stats in self._endpoints.values()
            )
        average = 0.0
        if total_requests:
            average = total_duration / total_requests
        return {
            "app": self.app_name,
            "generated_at": _now_iso(),
            "total_requests": total_requests,
            "error_requests": error_requests,
            "average_duration_ms": round(average * 1000, 3),
            "endpoints": endpoints,
        }

    def reset(self) -> None:
        with self._lock:
            self._endpoints.clear()


_TELEMETRY: Optional[Telemetry] = None
_PUBLISHER: Optional[BaseLogPublisher] = None


def get_telemetry() -> Telemetry:
    global _TELEMETRY
    if _TELEMETRY is None:
        _TELEMETRY = Telemetry()
    return _TELEMETRY


def override_telemetry(telemetry: Optional[Telemetry]) -> Optional[Telemetry]:
    global _TELEMETRY
    previous = _TELEMETRY
    _TELEMETRY = telemetry
    return previous


def _get_publisher() -> BaseLogPublisher:
    global _PUBLISHER
    if _PUBLISHER is None:
        _PUBLISHER = HttpLogPublisher()
    return _PUBLISHER


def override_publisher(publisher: Optional[BaseLogPublisher]) -> Optional[BaseLogPublisher]:
    global _PUBLISHER
    previous = _PUBLISHER
    _PUBLISHER = publisher
    return previous


def configure_logging(app_name: str = "audiovook-middleware", publisher: Optional[BaseLogPublisher] = None) -> None:
    if publisher is not None:
        override_publisher(publisher)
    root = logging.getLogger()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)
    root.handlers = []
    console = _JsonConsoleHandler(app_name)
    root.addHandler(console)
    publisher_instance = _get_publisher()
    if publisher_instance and publisher_instance.is_enabled:
        root.addHandler(_CentralisedLogHandler(publisher_instance, app_name))


class RequestMonitoringMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        telemetry: Optional[Telemetry] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(app)
        self.telemetry = telemetry or get_telemetry()
        self.logger = logger or logging.getLogger("app.monitoring")

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status_code = 500
        error: Optional[BaseException] = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:  # noqa: BLE001 - re-raised after logging
            error = exc
            status_code = 500
            self.logger.exception(
                "request.failed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else None,
                },
            )
            raise
        finally:
            duration = time.perf_counter() - start
            self.telemetry.record(request.method, request.url.path, status_code, duration)
            if error is None:
                if status_code < 400:
                    log = self.logger.info
                elif status_code < 500:
                    log = self.logger.warning
                else:
                    log = self.logger.error
                log(
                    "request.completed",
                    extra={
                        "http_method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 3),
                        "client": request.client.host if request.client else None,
                    },
                )
