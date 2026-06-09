"""Observability wire-up — 把 RingBufferHandler(以及可選的 JSONL FileHandler)
掛到 agentic_sdk logger 樹的根。

整個 SDK 內凡是 `logging.getLogger("agentic_sdk.*")` 的 logger,
只要呼叫 `logger.info(msg, extra={"event": event_dict})` 就會自動進 buffer。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agentic_sdk.config import Settings
from agentic_sdk.observability.handler import RingBufferHandler

_ROOT_LOGGER_NAME = "agentic_sdk"
_HANDLER_TAG = "_agentic_sdk_telemetry_owner"


class _JsonlFormatter(logging.Formatter):
    """只輸出 extra={'event': ...} 內容為單行 JSON。沒帶 event 的 record 略過。"""

    def format(self, record: logging.LogRecord) -> str:
        event: Any = getattr(record, "event", None)
        if event is None:
            return ""
        return json.dumps(event, ensure_ascii=False, default=str)


class _EventOnlyFilter(logging.Filter):
    """FileHandler 上掛這個,確保沒帶 event 的 log record 不寫進 JSONL。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "event", None) is not None


def configure_observability(settings: Settings) -> RingBufferHandler:
    """建立 RingBufferHandler 並掛到 agentic_sdk logger;若設定 JSONL 路徑則另掛 FileHandler。

    重複呼叫安全:先移除既有由本函式建立的 handler 再重新掛載,避免測試或熱重啟時
    出現多個 buffer 互相覆寫的鬼影。
    """
    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    for existing in list(logger.handlers):
        if getattr(existing, _HANDLER_TAG, False):
            logger.removeHandler(existing)

    ring = RingBufferHandler(maxlen=settings.telemetry_buffer_size)
    setattr(ring, _HANDLER_TAG, True)
    logger.addHandler(ring)

    if settings.telemetry_jsonl_path:
        target = Path(settings.telemetry_jsonl_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setFormatter(_JsonlFormatter())
        file_handler.addFilter(_EventOnlyFilter())
        setattr(file_handler, _HANDLER_TAG, True)
        logger.addHandler(file_handler)

    return ring
