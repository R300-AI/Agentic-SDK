"""A-04 + A-07 — Active Context in-memory 存放與生命週期。

Phase 2 PoC 實作:
- 純 dict 為底,單行程內可存取
- 寫入時若 content 體積使 ActiveStore 總量逾 `ACTIVE_CONTEXT_MAX_MB`,
  依 LRU(last_accessed_at)逐項降級至 ArchivedStore 直到回到上限以下
- 讀取時若條目 idle 超過 `CONTEXT_IDLE_DEMOTE_SEC` 或 created 超過
  `CONTEXT_HARD_TTL_SEC`,亦觸發降級;對應 get() 視為 not_found

降級/失敗皆 emit `context.degraded`,attributes 對齊 events.py 的
context_* 欄位。Phase 4 換 Redis 時只換本檔。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from agentic_sdk.context.archived_store import ArchivedStore
from agentic_sdk.context.entry import ContextEntry
from agentic_sdk.observability import make_event
from agentic_sdk.observability.events import EVENT_CONTEXT_DEGRADED

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024


def _estimate_bytes(entry: ContextEntry) -> int:
    return (
        len(entry.content.encode("utf-8"))
        + sum(len(str(k).encode()) + len(str(v).encode()) for k, v in entry.metadata.items())
        + len(entry.entry_id)
    )


@dataclass
class ActiveStore:
    """同行程 in-memory 上下文儲存。

    所有公開方法 thread-safe(內部 RLock);Phase 2 PoC 不引入 asyncio。
    """

    max_mb: float = 8.0
    idle_demote_sec: float = 300.0
    hard_ttl_sec: float = 3600.0
    archived: ArchivedStore | None = None

    _entries: dict[str, ContextEntry] = field(default_factory=dict, init=False, repr=False)
    _sizes: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.archived = self.archived or ArchivedStore()

    # ---------- 寫入 ----------

    def put(self, entry: ContextEntry) -> ContextEntry:
        with self._lock:
            size = _estimate_bytes(entry)
            self._entries[entry.entry_id] = entry
            self._sizes[entry.entry_id] = size
            self._enforce_capacity()
        return entry

    def put_many(self, entries: list[ContextEntry]) -> None:
        for e in entries:
            self.put(e)

    # ---------- 讀取 ----------

    def get(self, entry_id: str) -> ContextEntry | None:
        """讀取單筆。命中即 touch;若條目已過期則 emit not_found(M1-5)。"""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                self._emit_degraded(
                    entry_id=entry_id,
                    entry_type="unknown",
                    reason="not_found",
                )
                return None

            now = time.time()
            if (now - entry.created_at) > self.hard_ttl_sec:
                self._demote(entry, reason="hard_ttl")
                self._emit_degraded(
                    entry_id=entry_id,
                    entry_type=entry.type.value,
                    reason="not_found",
                )
                return None
            if (now - entry.last_accessed_at) > self.idle_demote_sec:
                self._demote(entry, reason="idle_demote")
                self._emit_degraded(
                    entry_id=entry_id,
                    entry_type=entry.type.value,
                    reason="not_found",
                )
                return None

            entry.touch()
            return entry

    # ---------- 維運 ----------

    def active_bytes(self) -> int:
        with self._lock:
            return sum(self._sizes.values())

    def active_mb(self) -> float:
        return self.active_bytes() / _BYTES_PER_MB

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "count": len(self._entries),
                "active_mb": round(self.active_mb(), 4),
                "max_mb": self.max_mb,
            }

    # ---------- 內部 ----------

    def _enforce_capacity(self) -> None:
        max_bytes = int(self.max_mb * _BYTES_PER_MB)
        if self.active_bytes() <= max_bytes:
            return

        ordered = sorted(
            self._entries.values(),
            key=lambda e: (e.eviction_priority, e.last_accessed_at),
        )
        demoted = 0
        for entry in ordered:
            if self.active_bytes() <= max_bytes:
                break
            self._demote(entry, reason="max_mb", emit=False)
            demoted += 1

        if demoted:
            self._emit_degraded(
                entry_id="",
                entry_type="batch",
                reason="max_mb",
                active_mb=round(self.active_mb(), 4),
                demoted_count=demoted,
            )

    def _demote(self, entry: ContextEntry, *, reason: str, emit: bool = True) -> None:
        self.archived.put(entry)
        self._entries.pop(entry.entry_id, None)
        self._sizes.pop(entry.entry_id, None)
        if emit:
            self._emit_degraded(
                entry_id=entry.entry_id,
                entry_type=entry.type.value,
                reason=reason,
            )

    def _emit_degraded(
        self,
        *,
        entry_id: str,
        entry_type: str,
        reason: str,
        active_mb: float | None = None,
        demoted_count: int | None = None,
    ) -> None:
        attrs: dict[str, object] = {
            "context_entry_id": entry_id,
            "context_entry_type": entry_type,
            "context_reason": reason,
        }
        if active_mb is not None:
            attrs["context_active_mb"] = active_mb
        if demoted_count is not None:
            attrs["context_demoted_count"] = demoted_count

        logger.info(
            "context.degraded reason=%s entry_id=%s",
            reason, entry_id,
            extra={"event": make_event(EVENT_CONTEXT_DEGRADED, **attrs)},
        )
