"""A-07 — Archived 上下文儲存(本機檔案系統,JSONL append-only)。

Phase 2 PoC 的 archived 層只負責「保住降級後的條目可被後續審計取回」,
沒有複雜的索引或壓縮。Phase 5 MVP 階段若需要可換成 SQLite / DuckDB。
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from agentic_sdk.context.entry import ContextEntry, ContextEntryType


@dataclass
class ArchivedStore:
    directory: str = ".archived_context"
    filename: str = "entries.jsonl"

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _path(self) -> Path:
        p = Path(self.directory)
        p.mkdir(parents=True, exist_ok=True)
        return p / self.filename

    def put(self, entry: ContextEntry) -> None:
        record = asdict(entry)
        record["type"] = entry.type.value
        with self._lock, self._path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get(self, entry_id: str) -> ContextEntry | None:
        path = self._path()
        if not path.exists():
            return None
        with self._lock, path.open("r", encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                if record.get("entry_id") == entry_id:
                    record["type"] = ContextEntryType(record["type"])
                    return ContextEntry(**record)
        return None

    def count(self) -> int:
        path = self._path()
        if not path.exists():
            return 0
        with self._lock, path.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
