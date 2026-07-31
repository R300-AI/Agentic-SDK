from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypedDict, runtime_checkable

from agentic_sdk.core.entities import Attachment, ContextEntry, ContextEntryType, Entities
from agentic_sdk.memory.in_context import InContextMemory, MemoryStore
from agentic_sdk.memory.protocol import PersistentMemory


class ModuleOutput(TypedDict, total=False):
    next_module: str | None
    payload: dict[str, Any]
    context_updates: list[ContextEntry]


@runtime_checkable
class Module(Protocol):
    name: str

    def __call__(self, state: "WorkflowState") -> ModuleOutput: ...


@dataclass
class WorkflowState:
    user_message: str
    workflow_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    workflow_name: str = "default"
    workflow_description: str | None = None
    session_id: str = "default"
    memory_store: PersistentMemory | None = None
    memory: MemoryStore | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    entities: Entities = field(default_factory=Entities)
    entries: list[ContextEntry] = field(default_factory=list)
    visit_counts: dict[str, int] = field(default_factory=dict)
    last_action_result: dict[str, Any] | None = None
    last_action_error: dict[str, Any] | None = None
    attachments: list[Attachment] = field(default_factory=list)
    _token_delta_callback: Callable[[str, str, dict[str, Any]], None] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.memory is None and self.memory_store is not None:
            self.memory = self.memory_store
        if self.memory_store is None and isinstance(self.memory, PersistentMemory):
            self.memory_store = self.memory

    @property
    def payload(self) -> dict[str, Any]:
        return self.entities.values

    def append(self, entry: ContextEntry) -> None:
        self.entries.append(entry)

    def latest_of(self, entry_type: ContextEntryType | str) -> ContextEntry | None:
        for entry in reversed(self.entries):
            if entry.type == entry_type or str(entry.type) == str(entry_type):
                entry.touch()
                return entry
        return None

    def apply(self, output: ModuleOutput) -> None:
        for entry in output.get("context_updates", []) or []:
            self.append(entry)
        self.entities.update(output.get("payload"))

    def increment_visit(self, module_name: str) -> int:
        self.visit_counts[module_name] = self.visit_counts.get(module_name, 0) + 1
        return self.visit_counts[module_name]

    def lookup(self, key: str) -> Any | None:
        if key in self.entities.values:
            return self.entities.values[key]
        if key == "latest_retrieved_content":
            entry = self.latest_of(ContextEntryType.RETRIEVED)
            return entry.content if entry is not None else None
        if key == "latest_final_message":
            result = self.last_action_result or {}
            return result.get("content")
        return None

    def latest_user_message(self) -> str:
        if self.memory is not None and self.memory.latest_user_turn() is not None:
            return self.memory.latest_user_turn().content
        return self.user_message

    def latest_assistant_message(self) -> str | None:
        if self.memory is None:
            return None
        turn = self.memory.latest_assistant_turn()
        return turn.content if turn is not None else None

    def persistent_memory(self) -> PersistentMemory | None:
        if self.memory_store is not None:
            return self.memory_store
        if isinstance(self.memory, PersistentMemory):
            return self.memory
        return None

    def set_token_delta_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], None] | None,
    ) -> None:
        self._token_delta_callback = callback

    def emit_token_delta(
        self,
        module: str,
        content: object,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._token_delta_callback is None or content is None:
            return
        resolved_content = str(content)
        if not resolved_content:
            return
        self._token_delta_callback(str(module), resolved_content, dict(metadata or {}))


@dataclass
class WorkflowResult:
    workflow_id: str
    final_message: str
    session_id: str = "default"
    aborted: bool = False
    abort_reason: str | None = None
    entries: list[ContextEntry] = field(default_factory=list)
    visit_counts: dict[str, int] = field(default_factory=dict)
    usage: dict[str, Any] | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    memory: MemoryStore | None = None


class WorkflowAborted(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason