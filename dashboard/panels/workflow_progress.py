"""B-06 觀測-3:工作流執行進度。

Phase 1:此面板於僅有 Gateway 事件時會提示「五節點尚未啟用」。
Phase 2:從 workflow.node.start / finish 事件聚合節點延遲分配與成功率。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from agentic_sdk.observability.events import EVENT_NODE_FINISH, EVENT_NODE_START


def render(events: list[dict[str, Any]]) -> None:
    st.subheader("觀測-3 · 工作流節點進度")

    starts = [e for e in events if e.get("event_name") == EVENT_NODE_START]
    finishes = [e for e in events if e.get("event_name") == EVENT_NODE_FINISH]

    if not starts and not finishes:
        st.info(
            "尚未收到任何節點事件。Phase 2 啟用五節點工作流後,本面板會顯示"
            "每個節點的呼叫次數、平均耗時與佔總工作流的時間比例。"
        )
        return

    df = pd.DataFrame([
        {
            "node": e.get("workflow_node", "unknown"),
            "duration_ms": e.get("duration_ms", 0),
        }
        for e in finishes
    ])

    if df.empty:
        st.warning("收到 node.start 但尚無 node.finish。請等待完整工作流走完。")
        return

    summary = df.groupby("node").agg(
        executions=("duration_ms", "count"),
        avg_ms=("duration_ms", "mean"),
        total_ms=("duration_ms", "sum"),
    ).round(0)
    summary["share_%"] = (summary["total_ms"] / summary["total_ms"].sum() * 100).round(1)

    # 強制依五節點順序顯示
    node_order = ["perceive", "plan", "retrieve", "reflect", "action"]
    summary = summary.reindex([n for n in node_order if n in summary.index])

    _NODE_DESC = {
        "perceive": "感知輸入 — 解析 user message,建立本次工作流的起始 context",
        "plan":    "決策規劃 — 由 LLM 決定下一步走哪個節點(retrieve / action)",
        "retrieve": "資料檢索 — 從知識庫取回相關上下文,補充 plan 的判斷依據",
        "reflect":  "結果評估 — 檢視 action 產出,決定接受(END)或要求重試(→ plan)",
        "action":   "產出執行 — 呼叫 LLM / 上游推論伺服器,產生最終回應",
    }

    cols = st.columns(2)
    with cols[0]:
        st.dataframe(summary, use_container_width=True)
        with st.expander("節點說明"):
            for node, desc in _NODE_DESC.items():
                if node in summary.index:
                    st.markdown(f"**{node}** — {desc}")
    with cols[1]:
        st.bar_chart(summary["avg_ms"], height=260)
