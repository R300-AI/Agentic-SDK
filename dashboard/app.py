"""Dashboard 入口 — 以 `streamlit run dashboard/app.py` 啟動。

設計:
- DataSource 來源由 sidebar 選擇(Gateway HTTP / Mock),預設依 .env 連 Gateway
- 自動輪詢:`st.fragment(run_every=...)` 區段每 N 秒重新拉資料,
  其他靜態元件(sidebar / 標題)不重複渲染,避免閃爍
- 四個面板共享同一份 events 快照,避免各自輪詢造成事件視窗錯位
"""

from __future__ import annotations

import streamlit as st

from agentic_sdk.config import get_settings
from dashboard.data_source import DataSource, HttpDataSource, MockDataSource, Snapshot
from dashboard.panels import (
    degradation_log,
    inference_metrics,
    topology,
    workflow_progress,
)


st.set_page_config(
    page_title="Agentic SDK · Multi-Model Dashboard",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def _build_data_source(mode: str, gateway_url: str) -> DataSource:
    if mode == "mock":
        return MockDataSource()
    return HttpDataSource(gateway_url)


def _sidebar(settings) -> tuple[DataSource, int, float]:
    st.sidebar.title("Agentic SDK")
    st.sidebar.caption("Multi-Model Dashboard · Phase 1")

    default_url = f"http://{settings.gateway_host}:{settings.gateway_port}"
    mode = st.sidebar.radio(
        "資料來源",
        options=["gateway", "mock"],
        format_func=lambda x: "Gateway HTTP" if x == "gateway" else "Mock(離線)",
        horizontal=True,
    )
    gateway_url = st.sidebar.text_input("Gateway URL", value=default_url)
    limit = st.sidebar.slider(
        "拉取事件上限",
        min_value=50, max_value=2000,
        value=settings.dashboard_snapshot_limit, step=50,
    )
    refresh_sec = st.sidebar.slider(
        "刷新週期(秒)",
        min_value=1.0, max_value=10.0,
        value=settings.dashboard_refresh_sec, step=0.5,
    )

    data_source = _build_data_source(mode, gateway_url)
    st.sidebar.caption(f"來源:{data_source.label()}")
    return data_source, limit, refresh_sec


def _render_panels(snapshot: Snapshot) -> None:
    meta = snapshot.meta
    if meta.get("error"):
        st.error(f"無法連線資料來源:{meta['error']}")

    cols = st.columns(2)
    with cols[0]:
        topology.render(snapshot.events)
    with cols[1]:
        inference_metrics.render(snapshot.events)

    st.divider()

    cols = st.columns(2)
    with cols[0]:
        workflow_progress.render(snapshot.events)
    with cols[1]:
        degradation_log.render(snapshot.events)

    with st.expander("快照 metadata", expanded=False):
        st.json(meta)


def main() -> None:
    settings = get_settings()
    data_source, limit, refresh_sec = _sidebar(settings)

    st.title("Multi-Model Dashboard")
    st.caption(
        "邊緣叢集即時觀測 · 依賴 Gateway `/internal/telemetry/snapshot` · "
        "資料來源切換為 Mock 時可離線迭代 UI"
    )

    @st.fragment(run_every=refresh_sec)
    def _live() -> None:
        snapshot = data_source.fetch(limit=limit)
        _render_panels(snapshot)

    _live()


main()
