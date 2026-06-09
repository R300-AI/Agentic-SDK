"""B-04 觀測-1:節點存活拓樸。

Phase 1 只有一個上游(AMD NPU),拓樸退化成「上游是否健康 + 最後一次心跳時間」。
Phase 4 多上游時,本面板會橫向展開為多列。
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from agentic_sdk.observability.events import EVENT_GATEWAY_UPSTREAM_HEALTHCHECK


def render(events: list[dict[str, Any]]) -> None:
    st.subheader("觀測-1 · 節點存活拓樸")

    health_events = [e for e in events if e.get("event_name") == EVENT_GATEWAY_UPSTREAM_HEALTHCHECK]
    if not health_events:
        st.info("尚未收到 healthcheck 事件。Gateway 啟動後每次 /healthz 與 lifespan 都會產生事件。")
        return

    latest = health_events[-1]
    reachable = bool(latest.get("upstream_reachable"))
    age_sec = max(0.0, time.time() - float(latest.get("ts", time.time())))

    cols = st.columns([1, 2, 2])
    cols[0].metric("狀態", "🟢 就緒" if reachable else "🔴 不可達")
    cols[1].metric("最後心跳", f"{age_sec:.1f} 秒前")
    cols[2].metric("Healthcheck 累計", len(health_events))

    st.markdown(f"**上游 URL**:`{latest.get('upstream_url', 'unknown')}`")
    if reachable:
        models = latest.get("upstream_models") or []
        st.markdown(f"**可用模型**:{', '.join(models) if models else '(空)'}")
    else:
        st.error(f"`{latest.get('error_type', 'Error')}`: {latest.get('error_message', '')}")

    # 心跳時間軸(最近 N 次)
    with st.expander(f"最近 {len(health_events)} 次 healthcheck 紀錄", expanded=False):
        rows = [
            {
                "時間": time.strftime("%H:%M:%S", time.localtime(e["ts"])),
                "可達": "✓" if e.get("upstream_reachable") else "✗",
                "錯誤": e.get("error_message", ""),
            }
            for e in health_events[-20:]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
