"""RingBufferHandler — logging Handler 的記憶體環形緩衝實作。

服務於 Dashboard 的「即時最近 N 筆」查詢模式。容量上限保證 Gateway 行程
不會因事件爆量而 OOM,代價是 Gateway 重啟事件會清空(PoC 接受;
若需持久化請另外掛 logging.FileHandler 寫 JSONL)。
"""

from __future__ import annotations

import logging
from collections import deque
from threading import Lock
from typing import Any

from agentic_sdk.observability.events import TelemetryEvent


class RingBufferHandler(logging.Handler):
    def __init__(self, maxlen: int) -> None:
        super().__init__()
        if maxlen <= 0:
            raise ValueError(f"maxlen 必須 > 0,得到 {maxlen}")
        self._buffer: deque[TelemetryEvent] = deque(maxlen=maxlen)
        # deque.append 本身是 thread-safe,但 snapshot 期間需要凍結讀取以避免
        # 半新半舊的混合視圖(尤其多執行緒 uvicorn 工作者場景)。
        self._lock = Lock()

    @property
    def maxlen(self) -> int:
        assert self._buffer.maxlen is not None
        return self._buffer.maxlen

    def emit(self, record: logging.LogRecord) -> None:
        event = getattr(record, "event", None)
        if event is None:
            return
        if not isinstance(event, dict):
            return
        with self._lock:
            self._buffer.append(event)  # type: ignore[arg-type]

    def snapshot(self, limit: int | None = None) -> list[TelemetryEvent]:
        """回傳目前 buffer 內事件的快照(舊 → 新)。

        limit:只取最後 N 筆;None 代表全部。
        """
        with self._lock:
            items = list(self._buffer)
        if limit is None:
            return items
        if limit <= 0:
            return []
        return items[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def filter_by_name(self, event_name: str, limit: int | None = None) -> list[TelemetryEvent]:
        items = [e for e in self.snapshot() if e.get("event_name") == event_name]
        if limit is None:
            return items
        return items[-limit:] if limit > 0 else []

    def stats(self) -> dict[str, Any]:
        with self._lock:
            size = len(self._buffer)
        return {"size": size, "maxlen": self.maxlen}
