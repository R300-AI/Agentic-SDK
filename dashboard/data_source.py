"""DataSource 抽象與兩個實作。

DataSource:面板程式碼唯一認得的介面。
HttpDataSource:正常情境,連 Gateway 的 /internal/telemetry/snapshot。
MockDataSource:無 Gateway 也能起 Dashboard,供 UI 迭代與 demo。

Phase 3 若改用 OTel collector,新增第三個實作(例:OtelLogsDataSource)即可,
面板程式碼不動。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from agentic_sdk.observability.events import (
    EVENT_CONTEXT_DEGRADED,
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_GATEWAY_REQUEST_FINISH,
    EVENT_GATEWAY_REQUEST_START,
    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
    EVENT_WORKFLOW_FALLBACK,
)


@dataclass(frozen=True)
class Snapshot:
    events: list[dict[str, Any]]
    meta: dict[str, Any]


class DataSource(Protocol):
    def fetch(self, limit: int, event_name: str | None = None) -> Snapshot:
        """同步拉取目前的事件快照。"""
        ...

    def label(self) -> str:
        """供 UI 顯示資料來源名稱(例:'Gateway @ 127.0.0.1:8080' / 'Mock')。"""
        ...


# ----- HTTP 實作 ---------------------------------------------------------------


class HttpDataSource:
    def __init__(self, base_url: str, timeout_sec: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec

    def fetch(self, limit: int, event_name: str | None = None) -> Snapshot:
        url = f"{self._base_url}/internal/telemetry/snapshot"
        params: dict[str, Any] = {"limit": limit}
        if event_name:
            params["event_name"] = event_name
        try:
            resp = httpx.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return Snapshot(
                events=[],
                meta={"error": str(exc), "source": self.label()},
            )
        payload = resp.json()
        return Snapshot(
            events=payload.get("events", []),
            meta={**payload.get("meta", {}), "source": self.label()},
        )

    def label(self) -> str:
        return f"Gateway @ {self._base_url}"


# ----- Mock 實作 ---------------------------------------------------------------


class MockDataSource:
    """產生語意上合理的假事件流,用於無 Gateway 時迭代 UI 與煙霧測試。

    Mock 範圍同時覆蓋 Phase 1 真實事件與 Phase 2 預鎖事件名稱,
    讓四個面板都能在沒有真實工作流的情況下顯示有意義內容。
    """

    _MODELS = ["gemma3-4b-npu", "phi-3-mini-npu", "llama3.1-8b-npu"]
    _NODES = ["perceive", "plan", "retrieve", "reflect", "action"]
    _FALLBACK_REASONS = ["context_evicted", "offload_fallback", "max_hops"]

    def __init__(self, *, seed: int | None = 42, history_sec: float = 120.0) -> None:
        self._rng = random.Random(seed)
        self._history_sec = history_sec
        self._cached: list[dict[str, Any]] | None = None
        self._cached_until: float = 0.0

    def fetch(self, limit: int, event_name: str | None = None) -> Snapshot:
        events = self._regenerate_if_needed()
        if event_name:
            events = [e for e in events if e.get("event_name") == event_name]
        events = events[-limit:]
        return Snapshot(
            events=events,
            meta={
                "returned": len(events),
                "buffer": {"size": len(events), "maxlen": limit},
                "source": self.label(),
                "is_mock": True,
            },
        )

    def label(self) -> str:
        return "Mock (no gateway connected)"

    # --- 內部 ---------------------------------------------------------------

    def _regenerate_if_needed(self) -> list[dict[str, Any]]:
        now = time.time()
        if self._cached is not None and now < self._cached_until:
            return self._cached
        self._cached = self._generate(now)
        self._cached_until = now + 1.0  # 同一秒內視為穩定,避免 UI 抖動
        return self._cached

    def _generate(self, now: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        start = now - self._history_sec

        # healthcheck 每 10 秒一次,模擬偶發失敗
        t = start
        while t < now:
            reachable = self._rng.random() > 0.05
            base = {
                "ts": t,
                "event_name": EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
                "upstream_url": "http://localhost:8000/v1/models",
                "upstream_reachable": reachable,
            }
            if reachable:
                base["upstream_models"] = self._MODELS
            else:
                base["error_type"] = "ConnectError"
                base["error_message"] = "connection refused"
            events.append(base)
            t += 10.0

        # 過去 history_sec 內模擬 ~30 個請求
        for _ in range(30):
            request_ts = self._rng.uniform(start, now - 1.0)
            model = self._rng.choice(self._MODELS)
            duration = self._rng.uniform(150, 1800)
            tokens_in = self._rng.randint(20, 200)
            tokens_out = self._rng.randint(30, 400)
            failed = self._rng.random() < 0.08

            events.append({
                "ts": request_ts,
                "event_name": EVENT_GATEWAY_REQUEST_START,
                "http_request_method": "POST",
                "http_route": "/v1/chat/completions",
                "gen_ai_system": "amd_npu",
                "gen_ai_operation_name": "chat",
                "gen_ai_request_model": model,
            })

            if failed:
                events.append({
                    "ts": request_ts + duration / 1000,
                    "event_name": EVENT_GATEWAY_REQUEST_ERROR,
                    "http_response_status_code": 502,
                    "gen_ai_request_model": model,
                    "duration_ms": duration,
                    "error_type": "TimeoutError",
                    "error_message": "upstream timed out",
                })
            else:
                events.append({
                    "ts": request_ts + duration / 1000,
                    "event_name": EVENT_GATEWAY_REQUEST_FINISH,
                    "http_response_status_code": 200,
                    "gen_ai_request_model": model,
                    "gen_ai_response_model": model,
                    "gen_ai_usage_input_tokens": tokens_in,
                    "gen_ai_usage_output_tokens": tokens_out,
                    "duration_ms": duration,
                })

            # 為通過的請求模擬五節點 trace(Phase 2 才會真實 emit,Phase 1 mock)
            if not failed and self._rng.random() < 0.6:
                node_ts = request_ts
                for node in self._NODES:
                    node_duration = duration / len(self._NODES) * self._rng.uniform(0.7, 1.3)
                    events.append({
                        "ts": node_ts,
                        "event_name": EVENT_NODE_START,
                        "workflow_node": node,
                        "gen_ai_request_model": model,
                    })
                    events.append({
                        "ts": node_ts + node_duration / 1000,
                        "event_name": EVENT_NODE_FINISH,
                        "workflow_node": node,
                        "duration_ms": node_duration,
                    })
                    node_ts += node_duration / 1000

        # 偶發降級事件
        for _ in range(self._rng.randint(2, 6)):
            ts = self._rng.uniform(start, now)
            reason = self._rng.choice(self._FALLBACK_REASONS)
            events.append({
                "ts": ts,
                "event_name": (
                    EVENT_CONTEXT_DEGRADED if reason == "context_evicted"
                    else EVENT_WORKFLOW_FALLBACK
                ),
                "reason": reason,
            })

        events.sort(key=lambda e: e.get("ts", 0.0))
        return events
