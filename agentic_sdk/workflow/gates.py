"""A-06 — 工作流回環閘門。

Phase 2 启用三道閘門,皆透過 Settings 驅動,反硬編碼:
- MAX_NODE_HOPS:單次 Workflow.run() 全域節點執行次數上限
- MAX_REVISIT:同一節點重複進入次數上限
- TIMEOUT:單次工作流 wall-clock 上限(同步實作,每節點進入前檢查)

TIMEOUT 需認知:同步實作不能強製中斷正在跑的節點,只能在下一個節點入口拒絕。
PoC 內部內容可受;Phase 5 若需 hard cancel 再換為 asyncio.wait_for。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from agentic_sdk.workflow.node import WorkflowAborted, WorkflowState


@dataclass
class Gates:
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0

    def before_visit(self, node_name: str, state: WorkflowState, total_hops: int) -> None:
        if total_hops > self.max_node_hops:
            raise WorkflowAborted(
                f"total node hops {total_hops} 超過上限 {self.max_node_hops}"
            )
        if state.visit_counts.get(node_name, 0) >= self.max_revisit:
            raise WorkflowAborted(
                f"node '{node_name}' 重訪次數 {state.visit_counts[node_name]} "
                f"已達上限 {self.max_revisit}"
            )
        elapsed = time.monotonic() - state.started_monotonic
        if elapsed > self.timeout_sec:
            raise WorkflowAborted(
                f"workflow 逾時(elapsed={elapsed:.2f}s 上限 {self.timeout_sec}s)"
            )
