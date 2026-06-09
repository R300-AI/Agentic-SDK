"""B-01 — observability 套件單元測試。

涵蓋:
- RingBufferHandler 覆蓋語義(滿了擠掉最舊)
- snapshot 順序(舊 → 新)與 limit 行為
- 非結構化 record 不污染 buffer
- configure_observability 重複呼叫安全
- JSONL FileHandler 真的寫盤且只寫帶 event 的記錄
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from agentic_sdk.config import Settings
from agentic_sdk.observability import (
    EVENT_GATEWAY_REQUEST_START,
    RingBufferHandler,
    configure_observability,
    make_event,
)


def test_ring_buffer_overwrites_oldest():
    ring = RingBufferHandler(maxlen=3)
    for i in range(5):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="", args=(), exc_info=None,
        )
        record.event = {"event_name": "x", "i": i}
        ring.emit(record)

    items = ring.snapshot()
    assert [e["i"] for e in items] == [2, 3, 4]


def test_snapshot_limit_returns_last_n():
    ring = RingBufferHandler(maxlen=10)
    for i in range(5):
        record = logging.LogRecord("t", logging.INFO, "", 0, "", (), None)
        record.event = {"event_name": "x", "i": i}
        ring.emit(record)

    assert [e["i"] for e in ring.snapshot(limit=2)] == [3, 4]
    assert ring.snapshot(limit=0) == []
    assert [e["i"] for e in ring.snapshot()] == [0, 1, 2, 3, 4]


def test_records_without_event_are_ignored():
    ring = RingBufferHandler(maxlen=5)
    plain = logging.LogRecord("t", logging.INFO, "", 0, "純文字 log", (), None)
    ring.emit(plain)
    assert ring.snapshot() == []


def test_invalid_maxlen_rejected():
    with pytest.raises(ValueError):
        RingBufferHandler(maxlen=0)


def test_filter_by_name():
    ring = RingBufferHandler(maxlen=10)
    for name in ["a", "b", "a", "c", "a"]:
        rec = logging.LogRecord("t", logging.INFO, "", 0, "", (), None)
        rec.event = {"event_name": name}
        ring.emit(rec)
    assert len(ring.filter_by_name("a")) == 3


def test_configure_observability_is_idempotent(tmp_path):
    settings = Settings(_env_file=None, telemetry_buffer_size=5)  # type: ignore[call-arg]

    ring1 = configure_observability(settings)
    ring2 = configure_observability(settings)

    logger = logging.getLogger("agentic_sdk.test")
    logger.info("hello", extra={"event": make_event(EVENT_GATEWAY_REQUEST_START)})

    # 第二次 configure 應移除第一個 handler,事件只進 ring2,不進 ring1
    assert len(ring2.snapshot()) == 1
    assert len(ring1.snapshot()) == 0


def test_event_propagates_to_ring_via_logger(tmp_path):
    settings = Settings(_env_file=None, telemetry_buffer_size=10)  # type: ignore[call-arg]
    ring = configure_observability(settings)

    logger = logging.getLogger("agentic_sdk.test.module")
    logger.info(
        "msg",
        extra={"event": make_event(
            EVENT_GATEWAY_REQUEST_START,
            http_route="/v1/chat/completions",
            gen_ai_request_model="gemma-test",
        )},
    )

    events = ring.snapshot()
    assert len(events) == 1
    assert events[0]["event_name"] == EVENT_GATEWAY_REQUEST_START
    assert events[0]["http_route"] == "/v1/chat/completions"
    assert events[0]["gen_ai_request_model"] == "gemma-test"
    assert "ts" in events[0]


def test_jsonl_file_handler_writes_only_structured_events(tmp_path):
    jsonl = tmp_path / "telemetry.jsonl"
    settings = Settings(
        _env_file=None,                                # type: ignore[call-arg]
        telemetry_buffer_size=10,
        telemetry_jsonl_path=str(jsonl),
    )
    configure_observability(settings)

    logger = logging.getLogger("agentic_sdk.test.jsonl")
    logger.info("plain text, no event")  # 不該寫進 JSONL
    logger.info("with event", extra={"event": make_event(
        EVENT_GATEWAY_REQUEST_START, http_route="/x"
    )})

    # 強制 flush
    for h in logging.getLogger("agentic_sdk").handlers:
        h.flush()

    assert jsonl.exists()
    lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_name"] == EVENT_GATEWAY_REQUEST_START
    assert payload["http_route"] == "/x"


def test_make_event_strips_none_values():
    event = make_event(
        "x.y", gen_ai_request_model="m", gen_ai_response_model=None,
    )
    assert "gen_ai_request_model" in event
    assert "gen_ai_response_model" not in event
    assert event["event_name"] == "x.y"
    assert "ts" in event
