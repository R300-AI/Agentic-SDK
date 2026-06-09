"""B-07 觀測-4:降級事件 log。

統合 gateway.request.error / context.degraded / workflow.fallback 三類事件,
依時間倒序顯示,提供前端工程師根因排查的單一入口。
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from agentic_sdk.observability.events import (
    EVENT_CONTEXT_DEGRADED,
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_WORKFLOW_FALLBACK,
)

_DEGRADATION_EVENT_NAMES = {
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_CONTEXT_DEGRADED,
    EVENT_WORKFLOW_FALLBACK,
}


def render(events: list[dict[str, Any]]) -> None:
    st.subheader("觀測-4 · 降級與錯誤事件")

    degraded = [e for e in events if e.get("event_name") in _DEGRADATION_EVENT_NAMES]

    if not degraded:
        st.success("過去視窗內無降級事件。")
        return

    by_type: dict[str, int] = {}
    for e in degraded:
        by_type[e["event_name"]] = by_type.get(e["event_name"], 0) + 1

    cols = st.columns(len(by_type))
    for col, (name, count) in zip(cols, by_type.items()):
        col.metric(name.split(".")[-1], count)

    rows = [
        {
            "時間": time.strftime("%H:%M:%S", time.localtime(e["ts"])),
            "事件": e["event_name"],
            "原因 / 錯誤類型": (
                e.get("reason")
                or e.get("error_type")
                or ""
            ),
            "訊息": e.get("error_message", ""),
            "模型": e.get("gen_ai_request_model", ""),
        }
        for e in reversed(degraded[-100:])
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
