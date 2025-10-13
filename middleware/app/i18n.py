"""Utilities for language selection and translations."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

__all__ = [
    "TranslationCatalog",
    "get_catalog",
    "override_catalog",
    "resolve_language",
    "translate_error",
    "translate_status",
]


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "jekyll-freelancer-theme" / "_data"


@dataclass
class TranslationCatalog:
    """Thread-safe loader for YAML-based translations."""

    data_dir: Path = field(default_factory=_default_data_dir)
    default_language: str = "ca"
    supported_languages: tuple[str, ...] = ("ca", "es", "en")
    _cache: Dict[str, Mapping[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def normalise(self, language: Optional[str]) -> str:
        if not language:
            return self.default_language
        candidate = language.lower().replace("_", "-")
        if candidate in self.supported_languages:
            return candidate
        short = candidate.split("-")[0]
        if short in self.supported_languages:
            return short
        return self.default_language

    def _load(self, language: str) -> Mapping[str, Any]:
        lang = self.normalise(language)
        with self._lock:
            cached = self._cache.get(lang)
            if cached is not None:
                return cached
            path = self.data_dir / f"{lang}.yml"
            if not path.exists():
                self._cache[lang] = {}
                return self._cache[lang]
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            self._cache[lang] = data
            return data

    def section(self, language: Optional[str], namespace: str) -> Mapping[str, Any]:
        lang = self.normalise(language)
        data = self._load(lang)
        section = data.get(namespace)
        if isinstance(section, Mapping):
            return section
        # Fallback to default language if the requested section is missing.
        if lang != self.default_language:
            default = self._load(self.default_language)
            fallback = default.get(namespace)
            if isinstance(fallback, Mapping):
                return fallback
        return {}

    def status_label(self, status: int, language: Optional[str] = None) -> str:
        labels = self.section(language, "statuses")
        # The YAML keys are strings; enforce the same for lookups.
        value = labels.get(str(status))
        if isinstance(value, str):
            return value
        unknown = labels.get("unknown")
        if isinstance(unknown, str):
            return unknown
        # As a final fallback return the default language value or a hardcoded string.
        if language and self.normalise(language) != self.default_language:
            return self.status_label(status, self.default_language)
        return "Desconegut"

    def error_message(self, code: str, language: Optional[str] = None) -> Optional[str]:
        errors = self.section(language, "errors")
        message = errors.get(code)
        if isinstance(message, str):
            return message
        if language and self.normalise(language) != self.default_language:
            return self.error_message(code, self.default_language)
        return None


_CATALOG: Optional[TranslationCatalog] = None


def get_catalog() -> TranslationCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = TranslationCatalog()
    return _CATALOG


def override_catalog(catalog: Optional[TranslationCatalog]) -> Optional[TranslationCatalog]:
    global _CATALOG
    previous = _CATALOG
    _CATALOG = catalog
    return previous


def resolve_language(language: Optional[str], accept_language: Optional[str]) -> str:
    catalog = get_catalog()
    if language:
        return catalog.normalise(language)
    if accept_language:
        primary = accept_language.split(",")[0].strip()
        if primary:
            return catalog.normalise(primary)
    return catalog.default_language


def translate_status(status: int, language: Optional[str] = None) -> str:
    return get_catalog().status_label(status, language)


def translate_error(code: str, language: Optional[str] = None) -> Optional[str]:
    return get_catalog().error_message(code, language)
