"""防回歸:確保冷啟動匯入順序不會踩到 `gateway` ↔ `nodes.action` 的循環匯入。

歷史紀錄(2026-06-09):
    Ryzen 機台執行 `scripts/demo_multi_backend.py` 失敗,
    錯誤訊息為 `cannot import name 'UpstreamCompletionAction' from partially initialized module`。
    根因為 `agentic_sdk/gateway/__init__.py` 曾 re-export `create_app`,
    導致 `action → gateway.__init__ → app → routes_chat → action` 形成循環。
    修法:把 gateway `__init__` 改空,使用者改 `from agentic_sdk.gateway.app import create_app`。
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run_in_fresh_interpreter(snippet: str) -> subprocess.CompletedProcess:
    """以全新 Python 子程序執行,避免 pytest 既有 sys.modules 暖機掩蓋循環匯入。"""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(snippet)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cold_import_action_modules_does_not_trigger_gateway_app() -> None:
    """冷啟動匯入 action 節點不應拉起 gateway.app(避免循環匯入)。"""
    result = _run_in_fresh_interpreter(
        """
        import sys
        from agentic_sdk.workflow import Workflow, WorkflowConfig, NodeSpec, GateConfig
        from agentic_sdk.workflow.nodes.action import (
            UpstreamCompletionAction,
            FoundryCompletionAction,
        )
        assert UpstreamCompletionAction.__name__ == "UpstreamCompletionAction"
        assert FoundryCompletionAction.__name__ == "FoundryCompletionAction"
        assert "agentic_sdk.gateway.app" not in sys.modules, (
            "冷啟動匯入 action 不應觸發 gateway.app 載入"
        )
        print("OK")
        """
    )
    assert result.returncode == 0, (
        f"冷啟動匯入失敗 stderr=\n{result.stderr}\nstdout=\n{result.stdout}"
    )
    assert "OK" in result.stdout


def test_gateway_app_still_importable_for_users_who_need_it() -> None:
    """明確路徑 `from agentic_sdk.gateway.app import create_app` 仍可用(未破壞 Gateway 啟動)。"""
    result = _run_in_fresh_interpreter(
        """
        from agentic_sdk.gateway.app import create_app
        assert callable(create_app)
        print("OK")
        """
    )
    assert result.returncode == 0, f"gateway.app 匯入失敗:\n{result.stderr}"
    assert "OK" in result.stdout
