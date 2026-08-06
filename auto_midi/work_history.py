"""Persistent editable work records for the Gradio workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import tempfile
import threading
import uuid
from typing import Callable


@dataclass(frozen=True)
class WorkRecord:
    record_id: str
    title: str
    created_at: str
    updated_at: str
    lyrics_and_requirements: str = ""
    feel_plan_json: str = ""
    execution_config_json: str = ""
    version: int = 1


class WorkHistoryStore:
    def __init__(self, root: Path, now_provider: Callable[[], datetime] | None = None):
        self.root = Path(root)
        self.records_dir = self.root / "records"
        self.index_path = self.root / "index.json"
        self._now_provider = now_provider or datetime.now
        self._lock = threading.RLock()

    def list_records(self) -> tuple[WorkRecord, ...]:
        with self._lock:
            records = self._read_all_records()
            return tuple(sorted(records, key=lambda item: item.updated_at, reverse=True))

    def titles(self) -> list[str]:
        return [record.title for record in self.list_records()]

    def load(self, title: str | None) -> WorkRecord | None:
        normalized = _normalize_title(title)
        if not normalized:
            return None
        with self._lock:
            return next(
                (record for record in self._read_all_records() if record.title.casefold() == normalized.casefold()),
                None,
            )

    def save(
        self,
        title: str | None,
        lyrics_and_requirements: str | None,
        feel_plan_json: str | None,
        execution_config_json: str | None,
    ) -> WorkRecord:
        with self._lock:
            self.records_dir.mkdir(parents=True, exist_ok=True)
            records = self._read_all_records()
            normalized = _normalize_title(title) or self._next_date_title(records)
            existing = next(
                (record for record in records if record.title.casefold() == normalized.casefold()),
                None,
            )
            now = self._now_provider().isoformat(timespec="seconds")
            record = WorkRecord(
                record_id=existing.record_id if existing else uuid.uuid4().hex,
                title=existing.title if existing else normalized,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                lyrics_and_requirements=lyrics_and_requirements or "",
                feel_plan_json=feel_plan_json or "",
                execution_config_json=execution_config_json or "",
            )
            _atomic_write_json(self.records_dir / f"{record.record_id}.json", asdict(record))
            by_id = {item.record_id: item for item in records}
            by_id[record.record_id] = record
            ordered = sorted(by_id.values(), key=lambda item: item.updated_at, reverse=True)
            _atomic_write_json(
                self.index_path,
                {
                    "version": 1,
                    "records": [
                        {
                            "record_id": item.record_id,
                            "title": item.title,
                            "created_at": item.created_at,
                            "updated_at": item.updated_at,
                        }
                        for item in ordered
                    ],
                },
            )
            return record

    def _next_date_title(self, records: list[WorkRecord]) -> str:
        base = self._now_provider().strftime("%Y-%m-%d")
        existing = {record.title.casefold() for record in records}
        if base.casefold() not in existing:
            return base
        suffix = 2
        while f"{base}-{suffix:02d}".casefold() in existing:
            suffix += 1
        return f"{base}-{suffix:02d}"

    def _read_all_records(self) -> list[WorkRecord]:
        if not self.records_dir.exists():
            return []
        records = []
        for path in self.records_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                records.append(WorkRecord(**payload))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return records


def _normalize_title(title: str | None) -> str:
    return str(title or "").strip()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
