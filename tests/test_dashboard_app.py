"""B-03 — dashboard/app.py 整體渲染煙霧測試。

用 Streamlit 內建的 AppTest 模擬 streamlit run,確認:
- 在 Mock 模式下完整渲染不拋例外
- sidebar / title / fragment 內四個面板皆呈現
- 偵測 panels 對「空事件列表」的優雅降級
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")


def _set_mock_mode(at: AppTest) -> None:
    """切換 sidebar 的資料來源到 mock。"""
    # radio 預設第一個選項是 'gateway',要切到 'mock'
    radios = at.sidebar.radio
    assert len(radios) >= 1, "預期 sidebar 有資料來源 radio"
    radios[0].set_value("mock")


def test_app_renders_without_exception_in_mock_mode():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    _set_mock_mode(at)
    at.run()
    assert not at.exception, f"app 渲染拋例外:{at.exception}"


def test_app_renders_all_four_panels_in_mock_mode():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    _set_mock_mode(at)
    at.run()

    headers = " | ".join(s.value for s in at.subheader)
    assert "觀測-1" in headers
    assert "觀測-2" in headers
    assert "觀測-3" in headers
    assert "觀測-4" in headers


def test_app_renders_without_exception_when_gateway_unreachable():
    """預設 gateway 模式 + 沒起 Gateway → 應顯示 error meta 而非崩潰。"""
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    # 保持預設 gateway 模式,Gateway 不存在 → HttpDataSource 會回 Snapshot(events=[], meta={error: ...})
    assert not at.exception, f"Gateway 不可達時 app 應優雅降級,但拋:{at.exception}"
    # 應該看到 error 元件
    errors = at.error
    assert len(errors) >= 1, "預期顯示連線錯誤提示"
