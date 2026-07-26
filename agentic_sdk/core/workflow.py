from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agentic_sdk.core.entities import ContextEntry, ContextEntryType
from agentic_sdk.core.gates import Gates
from agentic_sdk.core.module import Module, ModuleOutput, WorkflowAborted, WorkflowResult, WorkflowState
from agentic_sdk.memory.protocol import MemoryStore


@dataclass
class Workflow:
    perceive: Module | None = None
    plan: Module | None = None
    retrieve: Module | None = None
    action: Module | None = None
    reflect: Module | None = None
    memory_store: MemoryStore | None = None
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
        user_message: str,
        *,
        workflow_id: str | None = None,
        attachments: list[Any] | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> WorkflowResult:
        state = WorkflowState(user_message=user_message, workflow_name=self.workflow_name)
        if workflow_id:
            state.workflow_id = workflow_id
        state.memory_store = self.memory_store
        if attachments:
            state.attachments = list(attachments)

        state.append(ContextEntry(type=ContextEntryType.USER_INPUT, content=user_message))
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

        return WorkflowResult(
            workflow_id=state.workflow_id,
            final_message=_final_message_from(state),
            aborted=aborted,
            abort_reason=abort_reason,
            entries=list(state.entries),
            visit_counts=dict(state.visit_counts),
            usage=state.payload.get("_llm_usage"),
            entities=state.entities.as_dict(),
        )


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