"""Database backup utilities and scheduler."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Type
from uuid import UUID

from sqlmodel import Session, SQLModel, select

from app.models import Batch, Card, Claim, ListeningProgress, PlaySession, Store, Title, User

BackupPayload = Dict[str, Any]

_MODELS: Sequence[Type[SQLModel]] = (
    User,
    Title,
    Card,
    PlaySession,
    ListeningProgress,
    Store,
    Batch,
    Claim,
)


def _serialise(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _serialise(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    return value


def _row_to_dict(row: SQLModel) -> Dict[str, Any]:
    data: Dict[str, Any]
    if hasattr(row, "model_dump"):
        data = row.model_dump()
    elif hasattr(row, "dict"):
        data = row.dict()
    else:  # pragma: no cover - sqlmodel always provides ``dict``
        data = row.__dict__.copy()
    return {key: _serialise(val) for key, val in data.items()}


def perform_backup(engine, directory: os.PathLike[str] | str, now: Optional[datetime] = None) -> Path:
    """Persist the current database state to a timestamped JSON file."""

    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    backup_dir = Path(directory)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"backup-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
    target = backup_dir / backup_name

    payload: BackupPayload = {
        "created_at": timestamp.isoformat(),
        "tables": {},
    }

    with Session(engine) as session:
        for model in _MODELS:
            rows: Iterable[SQLModel] = session.exec(select(model)).all()
            payload["tables"][model.__name__] = [_row_to_dict(row) for row in rows]

    target.write_text(json.dumps(payload, indent=2, default=_serialise))
    return target


@dataclass
class BackupScheduler:
    engine: Any
    directory: Path
    interval_seconds: int
    run_on_start: bool = True
    _task: Optional[asyncio.Task] = None
    _stop: Optional[asyncio.Event] = None

    async def start(self) -> None:
        if self._task is not None:
            return
        if self.run_on_start:
            try:
                perform_backup(self.engine, self.directory)
            except Exception as exc:  # pragma: no cover - depends on runtime setup
                print(f"[backup] initial run failed: {exc}")
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        if self._stop is not None:
            self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:  # pragma: no cover - depends on shutdown timing
            pass
        self._task = None
        self._stop = None

    async def _loop(self) -> None:
        assert self._stop is not None
        while True:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
                break
            except asyncio.TimeoutError:
                try:
                    perform_backup(self.engine, self.directory)
                except Exception as exc:  # pragma: no cover
                    print(f"[backup] periodic run failed: {exc}")
                    continue


_SCHEDULER: Optional[BackupScheduler] = None


def get_backup_scheduler(engine) -> BackupScheduler:
    global _SCHEDULER
    if _SCHEDULER is None:
        interval = int(os.getenv("BACKUP_INTERVAL_SECONDS", str(3600)))
        directory = Path(os.getenv("BACKUP_DIRECTORY", "backups"))
        run_on_start = os.getenv("BACKUP_RUN_ON_START", "1").lower() not in {"0", "false", "no"}
        _SCHEDULER = BackupScheduler(
            engine=engine,
            directory=directory,
            interval_seconds=interval,
            run_on_start=run_on_start,
        )
    return _SCHEDULER
