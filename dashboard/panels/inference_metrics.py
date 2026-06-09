"""B-05 觀測-2:推論指標時序圖。

從 gateway.request.finish 事件聚合 token throughput、延遲分佈、success rate。
Phase 2 加入 TTFT 後本面板會多一條曲線。
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import streamlit as st

from agentic_sdk.observability.events import (
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_GATEWAY_REQUEST_FINISH,
)


def render(events: list[dict[str, Any]]) -> None:
    st.subheader("觀測-2 · 推論指標時序圖")

    finish = [e for e in events if e.get("event_name") == EVENT_GATEWAY_REQUEST_FINISH]
    errors = [e for e in events if e.get("event_name") == EVENT_GATEWAY_REQUEST_ERROR]

    if not finish and not errors:
        st.info("尚未收到任何完成的請求事件。")
        return

    total = len(finish) + len(errors)
    success_rate = len(finish) / total * 100 if total else 0.0
    avg_duration = (
        sum(e.get("duration_ms", 0) for e in finish) / len(finish) if finish else 0
    )
    total_out_tokens = sum(e.get("gen_ai_usage_output_tokens", 0) or 0 for e in finish)

    cols = st.columns(4)
    cols[0].metric("請求總數", total)
    cols[1].metric("成功率", f"{success_rate:.1f}%")
    cols[2].metric("平均延遲", f"{avg_duration:.0f} ms")
    cols[3].metric("產出 tokens", total_out_tokens)

    if not finish:
        st.warning("僅有失敗請求,無延遲與 token 數據可繪。")
        return

    df = pd.DataFrame([
        {
            "time": pd.to_datetime(e["ts"], unit="s"),
            "model": e.get("gen_ai_request_model", "unknown"),
            "duration_ms": e.get("duration_ms", 0),
            "tokens_out": e.get("gen_ai_usage_output_tokens", 0) or 0,
            "tokens_per_sec": (
                (e.get("gen_ai_usage_output_tokens", 0) or 0) /
                max(e.get("duration_ms", 1) / 1000, 0.001)
            ),
        }
        for e in finish
    ])

    tab1, tab2, tab3 = st.tabs(["延遲時序", "Tokens/sec 時序", "依模型分佈"])
    with tab1:
        st.line_chart(df.set_index("time")["duration_ms"], height=240)
    with tab2:
        st.line_chart(df.set_index("time")["tokens_per_sec"], height=240)
    with tab3:
        by_model = df.groupby("model").agg(
            requests=("duration_ms", "count"),
            avg_ms=("duration_ms", "mean"),
            tokens_out=("tokens_out", "sum"),
        ).round(0)
        st.dataframe(by_model, use_container_width=True)
