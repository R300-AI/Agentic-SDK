"""A-06 — 工作流回環閘門。

Phase 2 启用三道閘門,皆透過 Settings 驅動,反硬編碼:
- MAX_NODE_HOPS:單次 Workflow.run() 全域模組執行次數上限
- MAX_REVISIT:同一模組重複進入次數上限
- TIMEOUT:單次工作流 wall-clock 上限(同步實作,每模組進入前檢查)

TIMEOUT 需認知:同步實作不能強製中斷正在跑的模組,只能在下一個模組入口拒絕。
PoC 內部內容可受;Phase 5 若需 hard cancel 再換為 asyncio.wait_for。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from agentic_sdk.workflow.module import WorkflowAborted, WorkflowState


@dataclass
class Gates:
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0

    def before_visit(self, module_name: str, state: WorkflowState, total_hops: int) -> None:
        if total_hops > self.max_node_hops:
            raise WorkflowAborted(
                f"total module hops {total_hops} 超過上限 {self.max_node_hops}"
            )
        if state.visit_counts.get(module_name, 0) >= self.max_revisit:
            raise WorkflowAborted(
                f"module '{module_name}' 重訪次數 {state.visit_counts[module_name]} "
                f"已達上限 {self.max_revisit}"
            )
        elapsed = time.monotonic() - state.started_monotonic
        if elapsed > self.timeout_sec:
            raise WorkflowAborted(
                f"workflow 逾時(elapsed={elapsed:.2f}s 上限 {self.timeout_sec}s)"
            )
