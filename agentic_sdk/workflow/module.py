"""A-01 — Module Protocol、ModuleOutput、WorkflowState、WorkflowResult。

設計約束:
- 模組之間透過 WorkflowState 傳遞;Module 不持有 state 內容,只回傳 ModuleOutput
- ModuleOutput.next_module 為 None ⇒ 工作流結束(END)
- 同一 Module 實例可被多次重訪,內部不存可變狀態(testability)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict, runtime_checkable

from agentic_sdk.context import ContextEntry
from agentic_sdk.memory import MemoryStore
from agentic_sdk.workflow.attachments import Attachment


class ModuleOutput(TypedDict, total=False):
    """模組回傳契約。

    next_module:下一個模組名稱字串,或 None 代表 END
    payload:傳遞給下一模組的暫存資料(不寫入 Active Context)
    context_updates:本次模組寫入 Active Context 的條目串列
    """

    next_module: str | None
    payload: dict
    context_updates: list[ContextEntry]


@runtime_checkable
class Module(Protocol):
    """所有模組實作的最小契約。"""

    name: str

    def __call__(self, state: "WorkflowState") -> ModuleOutput: ...


@dataclass
class WorkflowState:
    """單次 Workflow.run() 的可變狀態。"""

    user_message: str
    workflow_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    workflow_name: str = "default"
    memory_store: MemoryStore | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    entries: list[ContextEntry] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    visit_counts: dict[str, int] = field(default_factory=dict)
    last_action_result: dict | None = None
    last_action_error: dict | None = None
    attachments: list[Attachment] = field(default_factory=list)

    def append(self, entry: ContextEntry) -> None:
        self.entries.append(entry)

    def latest_of(self, entry_type: str) -> ContextEntry | None:
        for entry in reversed(self.entries):
            if entry.type == entry_type:
                entry.touch()
                return entry
        return None

    def apply(self, output: ModuleOutput) -> None:
        for entry in output.get("context_updates", []) or []:
            self.append(entry)
        new_payload = output.get("payload")
        if new_payload:
            self.payload.update(new_payload)

    def increment_visit(self, module_name: str) -> int:
        self.visit_counts[module_name] = self.visit_counts.get(module_name, 0) + 1
        return self.visit_counts[module_name]

    def lookup(self, key: str) -> Any | None:
        if key in self.payload:
            return self.payload[key]
        if key == "latest_retrieved_content":
            from agentic_sdk.context import ContextEntryType

            entry = self.latest_of(ContextEntryType.RETRIEVED)
            return entry.content if entry is not None else None
        if key == "latest_final_message":
            result = self.last_action_result or {}
            return result.get("content")
        return None


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