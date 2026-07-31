from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
import uuid

from agentic_sdk.core.entities import ContextEntry, ContextEntryType
from agentic_sdk.core.gates import Gates
from agentic_sdk.core.module import Module, ModuleOutput, WorkflowAborted, WorkflowResult, WorkflowState
from agentic_sdk.memory.in_context import InContextMemory, MemoryStore
from agentic_sdk.memory.in_memory import InMemoryStore
from agentic_sdk.memory.protocol import PersistentMemory


DEFAULT_STAGE_LABELS: dict[str, str] = {
    "perceive": "正在理解你的問題",
    "retrieve": "正在查找參考資料",
    "plan": "正在規劃處理方式",
    "action": "正在準備回覆",
    "reflect": "正在檢查回覆內容",
}


@dataclass
class Workflow:
    perceive: Module | None = None
    plan: Module | None = None
    retrieve: Module | None = None
    action: Module | None = None
    reflect: Module | None = None
    memory_type: str | type[MemoryStore] | MemoryStore = "in_context"
    memory_store: PersistentMemory | None = None
    gates: Gates | None = None
    workflow_name: str = "default"
    description: str | None = None
    entry_module: str = "perceive"
    stage_labels: dict[str, str] = field(default_factory=dict)

    modules: dict[str, Module] = field(init=False)
    memory: MemoryStore | None = field(init=False, default=None)
    _session_memories: dict[str, MemoryStore] = field(init=False, repr=False, default_factory=dict)
    _memory_factory: type[MemoryStore] = field(init=False, repr=False, default=InContextMemory)

    def __post_init__(self) -> None:
        from agentic_sdk.modules.action import DirectAnswerAction
        from agentic_sdk.modules.perceive import PassThroughPerceive
        from agentic_sdk.modules.retrieve import KeywordRetrieve

        self.gates = self.gates or Gates()
        self._memory_factory = _memory_factory_from(self.memory_type)
        if _is_memory_store(self.memory_type):
            self.memory = self.memory_type
        self.modules = {
            "perceive": self.perceive or PassThroughPerceive(),
            "retrieve": self.retrieve or KeywordRetrieve(),
            "action": self.action or DirectAnswerAction(),
        }
        if self.plan is not None:
            self.modules["plan"] = self.plan
        if self.reflect is not None:
            self.modules["reflect"] = self.reflect

    def run(
        self,
        user_message: str | None = None,
        *,
        workflow_id: str | None = None,
        session_id: str | None = None,
        memory: MemoryStore | None = None,
        attachments: list[Any] | None = None,
        memory_store: PersistentMemory | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> WorkflowResult:
        resolved_workflow_id = workflow_id or uuid.uuid4().hex
        resolved_session_id = session_id or resolved_workflow_id
        state_memory = _resolve_memory(
            workflow_name=self.workflow_name,
            workflow_id=resolved_workflow_id,
            session_id=resolved_session_id,
            memory=memory,
            memory_type=self.memory_type,
            memory_factory=self._memory_factory,
            session_memories=self._session_memories,
        )
        if user_message is not None:
            state_memory.append_message("user", user_message, attachments=list(attachments or []))
        latest_user_turn = state_memory.latest_user_turn()
        if latest_user_turn is None:
            raise ValueError("Workflow.run requires user_message or a conversation containing a user turn.")

        resolved_memory_store = memory_store or self.memory_store
        if resolved_memory_store is None and isinstance(state_memory, PersistentMemory):
            resolved_memory_store = state_memory

        state = WorkflowState(
            user_message=latest_user_turn.content,
            workflow_name=self.workflow_name,
            workflow_description=self.description,
            workflow_id=resolved_workflow_id,
            session_id=resolved_session_id,
            memory=state_memory,
            memory_store=resolved_memory_store,
        )
        if event_callback is not None:
            state.set_token_delta_callback(
                lambda module_name, content, metadata: event_callback(
                    self.token_delta_event(
                        module_name=module_name,
                        content=content,
                        metadata=metadata,
                        state=state,
                    )
                )
            )
        if workflow_id:
            state.workflow_id = workflow_id
        state.attachments = list(latest_user_turn.attachments)

        state.append(ContextEntry(type=ContextEntryType.USER_INPUT, content=latest_user_turn.content))
        current: str | None = self.entry_module
        total_hops = 0
        aborted = False
        abort_reason: str | None = None

        try:
            while current is not None:
                total_hops += 1
                self.gates.before_visit(current, state, total_hops)
                state.increment_visit(current)

                module = self.modules.get(current)
                if module is None:
                    raise WorkflowAborted(f"unknown module '{current}'")

                if event_callback is not None:
                    event_callback(
                        self._stage_event(
                            phase="start",
                            status="running",
                            module_name=current,
                            module=module,
                            state=state,
                            visit_count=state.visit_counts.get(current, 1),
                        )
                    )
                raw_output = module(state)
                output = _normalize_output(current, raw_output, state)
                state.apply(output)
                next_module = _next_module_after(current, output, self.modules)
                if event_callback is not None:
                    finish_event = self._stage_event(
                        phase="finish",
                        status="done",
                        module_name=current,
                        module=module,
                        state=state,
                        visit_count=state.visit_counts.get(current, 1),
                    )
                    finish_event.update({"output": output, "next_module": next_module})
                    event_callback(finish_event)
                current = next_module
        except WorkflowAborted as exc:
            aborted = True
            abort_reason = exc.reason
            if event_callback is not None and current is not None:
                module = self.modules.get(current)
                abort_event = self._stage_event(
                    phase="abort",
                    status="error",
                    module_name=current,
                    module=module,
                    state=state,
                    visit_count=state.visit_counts.get(current, 0),
                )
                abort_event["reason"] = abort_reason
                event_callback(abort_event)

        final_message = _final_message_from(state)
        if final_message and state.memory is not None:
            latest_assistant = state.memory.latest_assistant_turn()
            if latest_assistant is None or latest_assistant.content != final_message:
                state.memory.append_message("assistant", final_message, metadata={"source": "workflow.run"})
        if state.memory is not None:
            self.memory = state.memory
            if memory is not None or _is_memory_store(self.memory_type):
                self._session_memories[resolved_session_id] = state.memory
            else:
                self._session_memories[resolved_session_id] = state.memory.copy_for_run()

        return WorkflowResult(
            workflow_id=state.workflow_id,
            final_message=final_message,
            session_id=state.session_id,
            aborted=aborted,
            abort_reason=abort_reason,
            entries=list(state.entries),
            visit_counts=dict(state.visit_counts),
            usage=state.payload.get("_llm_usage"),
            entities=state.entities.as_dict(),
            memory=state.memory.copy_for_run() if state.memory is not None else None,
        )

    def _stage_event(
        self,
        *,
        phase: str,
        status: str,
        module_name: str,
        module: Module | None,
        state: WorkflowState,
        visit_count: int,
    ) -> dict[str, Any]:
        label = self.stage_labels.get(module_name) or DEFAULT_STAGE_LABELS.get(module_name) or f"正在執行 {module_name}"
        return {
            "type": "stage",
            "phase": phase,
            "status": status,
            "stage": module_name,
            "label": label,
            "module": module_name,
            "module_class": module.__class__.__name__ if module is not None else None,
            "workflow_name": self.workflow_name,
            "workflow_id": state.workflow_id,
            "session_id": state.session_id,
            "state": state,
            "visit_count": visit_count,
        }

    def token_delta_event(
        self,
        *,
        module_name: str,
        content: str,
        metadata: dict[str, Any] | None,
        state: WorkflowState,
    ) -> dict[str, Any]:
        module = self.modules.get(module_name)
        return {
            "type": "token_delta",
            "phase": "delta",
            "status": "streaming",
            "module": module_name,
            "module_class": module.__class__.__name__ if module is not None else None,
            "content": content,
            "metadata": dict(metadata or {}),
            "workflow_name": self.workflow_name,
            "workflow_id": state.workflow_id,
            "session_id": state.session_id,
            "visit_count": state.visit_counts.get(module_name, 0),
        }


def _resolve_memory(
    *,
    workflow_name: str,
    workflow_id: str,
    session_id: str,
    memory: MemoryStore | None,
    memory_type: str | type[MemoryStore] | MemoryStore,
    memory_factory: type[MemoryStore],
    session_memories: dict[str, MemoryStore],
) -> MemoryStore:
    if memory is not None:
        resolved = memory
    elif _is_memory_store(memory_type):
        resolved = memory_type
    elif session_id in session_memories:
        resolved = session_memories[session_id].copy_for_run()
    else:
        resolved = _new_memory(memory_factory, workflow_name=workflow_name, workflow_id=workflow_id, session_id=session_id)
    resolved.workflow_name = workflow_name
    resolved.workflow_id = workflow_id
    resolved.session_id = session_id
    return resolved


def _memory_factory_from(memory_type: str | type[MemoryStore] | MemoryStore) -> type[MemoryStore]:
    if isinstance(memory_type, str):
        key = memory_type.strip().lower().replace("-", "_")
        if key in {"in_context", "context"}:
            return InContextMemory
        if key in {"persistent", "persistant", "in_memory"}:
            return InMemoryStore
        raise ValueError(f"unknown memory_type {memory_type!r}; use 'in_context', 'persistent', or a MemoryStore instance")
    if isinstance(memory_type, type):
        return memory_type
    if _is_memory_store(memory_type):
        return type(memory_type)
    raise TypeError("memory_type must be a string, MemoryStore class, or MemoryStore instance")


def _is_memory_store(value: object) -> bool:
    return all(
        hasattr(value, attribute)
        for attribute in (
            "turns",
            "append_message",
            "latest_user_turn",
            "latest_assistant_turn",
            "as_text_transcript",
            "copy_for_run",
        )
    )


def _new_memory(memory_type: type[MemoryStore], *, workflow_name: str, workflow_id: str, session_id: str) -> MemoryStore:
    try:
        return memory_type(workflow_name=workflow_name, workflow_id=workflow_id, session_id=session_id)
    except TypeError:
        resolved = memory_type()
        resolved.workflow_name = workflow_name
        resolved.workflow_id = workflow_id
        resolved.session_id = session_id
        return resolved


def _normalize_output(current: str, raw_output: Any, state: WorkflowState) -> ModuleOutput:
    if isinstance(raw_output, dict):
        return raw_output
    if current == "action":
        content = "" if raw_output is None else str(raw_output)
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": "custom-action"}
        return ModuleOutput(
            next_module=None,
            payload={"latest_final_message": content},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.ACTION_RESULT,
                    content=content,
                    metadata={"ok": True, "model": "custom-action"},
                )
            ],
        )
    raise TypeError(f"module '{current}' returned unsupported output type: {type(raw_output).__name__}")


def _next_module_after(current: str, output: ModuleOutput, modules: dict[str, Module]) -> str | None:
    next_module = output.get("next_module")
    if current == "perceive" and "plan" in modules and next_module in {None, "retrieve"}:
        return "plan"
    if current == "perceive" and next_module == "plan" and "plan" not in modules:
        return "retrieve" if "retrieve" in modules else "action" if "action" in modules else None
    if current == "action" and "reflect" in modules and next_module is None:
        return "reflect"
    return next_module


def _final_message_from(state: WorkflowState) -> str:
    result = state.last_action_result or {}
    if "content" in result:
        return str(result["content"])
    err = state.last_action_error
    if err:
        return f"[workflow ended with error] {err.get('message', '')}"
    return str(state.lookup("latest_final_message") or "")