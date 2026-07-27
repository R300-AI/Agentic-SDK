from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
import uuid

from agentic_sdk.core.entities import ContextEntry, ContextEntryType
from agentic_sdk.core.gates import Gates
from agentic_sdk.core.module import Module, ModuleOutput, WorkflowAborted, WorkflowResult, WorkflowState
from agentic_sdk.memory.in_context import ConversationStore, ConversationTurn, InContextMemory, MemoryStore
from agentic_sdk.memory.protocol import PersistentMemory


@dataclass
class Workflow:
    perceive: Module | None = None
    plan: Module | None = None
    retrieve: Module | None = None
    action: Module | None = None
    reflect: Module | None = None
    memory: MemoryStore | None = None
    memory_store: PersistentMemory | None = None
    conversation_store: ConversationStore | None = None
    gates: Gates | None = None
    workflow_name: str = "default"
    entry_module: str = "perceive"

    modules: dict[str, Module] = field(init=False)

    def __post_init__(self) -> None:
        from agentic_sdk.modules.action import DirectAnswerAction
        from agentic_sdk.modules.perceive import PassThroughPerceive
        from agentic_sdk.modules.retrieve import KeywordRetrieve

        self.gates = self.gates or Gates()
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
        conversation: MemoryStore | None = None,
        conversation_turns: list[ConversationTurn] | None = None,
        attachments: list[Any] | None = None,
        memory_store: PersistentMemory | None = None,
        conversation_store: ConversationStore | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> WorkflowResult:
        resolved_workflow_id = workflow_id or uuid.uuid4().hex
        resolved_session_id = session_id or resolved_workflow_id
        resolved_conversation_store = conversation_store or self.conversation_store
        state_memory = _resolve_memory(
            workflow_name=self.workflow_name,
            workflow_id=resolved_workflow_id,
            session_id=resolved_session_id,
            memory=memory or self.memory,
            conversation=conversation,
            conversation_turns=conversation_turns,
            conversation_store=resolved_conversation_store,
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
            workflow_id=resolved_workflow_id,
            session_id=resolved_session_id,
            memory=state_memory,
            memory_store=resolved_memory_store,
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
                    event_callback({"phase": "start", "module": current, "state": state, "visit_count": state.visit_counts.get(current, 1)})
                raw_output = module(state)
                output = _normalize_output(current, raw_output, state)
                state.apply(output)
                next_module = _next_module_after(current, output, self.modules)
                if event_callback is not None:
                    event_callback(
                        {
                            "phase": "finish",
                            "module": current,
                            "state": state,
                            "output": output,
                            "next_module": next_module,
                            "visit_count": state.visit_counts.get(current, 1),
                        }
                    )
                current = next_module
        except WorkflowAborted as exc:
            aborted = True
            abort_reason = exc.reason
            if event_callback is not None and current is not None:
                event_callback({"phase": "abort", "module": current, "state": state, "reason": abort_reason})

        final_message = _final_message_from(state)
        if final_message and state.memory is not None:
            latest_assistant = state.memory.latest_assistant_turn()
            if latest_assistant is None or latest_assistant.content != final_message:
                state.memory.append_message("assistant", final_message, metadata={"source": "workflow.run"})
        if resolved_conversation_store is not None and state.memory is not None:
            resolved_conversation_store.save(state.memory)

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


def _resolve_memory(
    *,
    workflow_name: str,
    workflow_id: str,
    session_id: str,
    memory: MemoryStore | None,
    conversation: MemoryStore | None,
    conversation_turns: list[ConversationTurn] | None,
    conversation_store: ConversationStore | None,
) -> MemoryStore:
    if memory is not None:
        resolved = memory.copy_for_run()
    elif conversation is not None:
        resolved = conversation.copy_for_run()
    elif conversation_store is not None:
        loaded = conversation_store.get(session_id, workflow_name=workflow_name)
        resolved = loaded.copy_for_run() if loaded is not None else InContextMemory()
    else:
        resolved = InContextMemory()
    resolved.workflow_name = workflow_name
    resolved.workflow_id = workflow_id
    resolved.session_id = session_id
    if conversation_turns:
        for turn in conversation_turns:
            resolved.append_turn(turn)
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