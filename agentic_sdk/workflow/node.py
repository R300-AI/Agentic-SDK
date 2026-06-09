"""A-01 — Node Protocol、NodeOutput、WorkflowState、WorkflowResult。

設計約束:
- 節點之間透過 WorkflowState 傳遞;Node 不持有 state 內容,只回傳 NodeOutput
- NodeOutput.next_node 為 None ⇒ 工作流結束(END)
- 同一 Node 實例可被多次重訪,內部不存可變狀態(testability)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict, runtime_checkable

from agentic_sdk.context import ContextEntry


class NodeOutput(TypedDict, total=False):
    """節點回傳契約。

    next_node:下一個節點名稱字串(對應 nodes/ 子套件),或 None 代表 END
    payload:傳遞給下一節點的暫存資料(不寫入 Active Context)
    context_updates:本次節點寫入 Active Context 的條目串列
    """

    next_node: str | None
    payload: dict
    context_updates: list[ContextEntry]


@runtime_checkable
class Node(Protocol):
    """所有節點實作的最小契約。"""

    name: str

    def __call__(self, state: "WorkflowState") -> NodeOutput: ...


@dataclass
class WorkflowState:
    """單次 Workflow.run() 的可變狀態。"""

    user_message: str
    workflow_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_monotonic: float = field(default_factory=time.monotonic)
    entries: list[ContextEntry] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    visit_counts: dict[str, int] = field(default_factory=dict)
    last_action_result: dict | None = None
    last_action_error: dict | None = None

    def append(self, entry: ContextEntry) -> None:
        self.entries.append(entry)

    def latest_of(self, entry_type: str) -> ContextEntry | None:
        for entry in reversed(self.entries):
            if entry.type == entry_type:
                entry.touch()
                return entry
        return None

    def apply(self, output: NodeOutput) -> None:
        for entry in output.get("context_updates", []) or []:
            self.append(entry)
        new_payload = output.get("payload")
        if new_payload:
            self.payload.update(new_payload)

    def increment_visit(self, node_name: str) -> int:
        self.visit_counts[node_name] = self.visit_counts.get(node_name, 0) + 1
        return self.visit_counts[node_name]


@dataclass
class WorkflowResult:
    """Workflow.run() 的回傳結構。"""

    workflow_id: str
    final_message: str
    aborted: bool = False
    abort_reason: str | None = None
    entries: list[ContextEntry] = field(default_factory=list)
    visit_counts: dict[str, int] = field(default_factory=dict)
    usage: dict | None = None


class WorkflowAborted(RuntimeError):
    """閘門觸發 → 工作流提前終止;由 engine 捕捉並轉為 WorkflowResult(aborted=True)。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
