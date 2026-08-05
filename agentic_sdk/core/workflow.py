from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from queue import Queue
from threading import Thread
from typing import Any
import uuid

from agentic_sdk.core.entities import ContextEntry, ContextEntryType
from agentic_sdk.core.events import ALL_STRUCTURED_FIELDS, normalize_events_schema, resolve_events_schema
from agentic_sdk.core.gates import Gates
from agentic_sdk.core.module import Module, ModuleOutput, WorkflowAborted, WorkflowResult, WorkflowState
from agentic_sdk.memory.in_context import InContextMemory, MemoryStore
from agentic_sdk.memory.in_memory import InMemoryStore
from agentic_sdk.memory.protocol import PersistentMemory


_STREAM_COMPLETED = object()


class WorkflowStream(Iterator[str]):
    """Iterator for user-visible action text from one workflow run.

    Iteration starts the workflow on a background thread so action deltas can be
    consumed as they arrive. An action that does not emit deltas contributes
    its final message once after it completes. After iteration is exhausted,
    :attr:`result` contains the same ``WorkflowResult`` that
    :meth:`Workflow.run` returns. Unexpected workflow exceptions are re-raised
    by the iterator after any already-emitted deltas; action modules that
    handle their own errors retain the normal ``Workflow.run`` result semantics.
    """

    def __init__(
        self,
        workflow: "Workflow",
        run_kwargs: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        yield_action_deltas: bool = True,
    ) -> None:
        self._workflow = workflow
        self._run_kwargs = run_kwargs
        self._event_callback = event_callback
        self._yield_action_deltas = yield_action_deltas
        self._deltas: Queue[str | object] = Queue()
        self._thread: Thread | None = None
        self._result: WorkflowResult | None = None
        self._error: BaseException | None = None
        self._exhausted = False
        self._emitted_action_text = False

    @property
    def result(self) -> WorkflowResult:
        """Return the completed workflow result.

        Raises:
            RuntimeError: If the stream has not been exhausted or the workflow
                ended with an unexpected exception.
        """
        if not self._exhausted:
            raise RuntimeError("WorkflowStream.result is available after the stream is exhausted.")
        if self._error is not None:
            raise RuntimeError("WorkflowStream did not produce a result.") from self._error
        if self._result is None:
            raise RuntimeError("WorkflowStream completed without a result.")
        return self._result

    def __iter__(self) -> "WorkflowStream":
        self._start()
        return self

    def __next__(self) -> str:
        self._start()
        if self._exhausted:
            raise StopIteration
        delta = self._deltas.get()
        if delta is _STREAM_COMPLETED:
            self._exhausted = True
            if self._error is not None:
                raise self._error
            raise StopIteration
        return str(delta)

    def _start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="agentic-sdk-workflow-stream", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._result = self._workflow.run(event_callback=self._on_event, **self._run_kwargs)
            if self._result.final_message and not self._emitted_action_text:
                self._deltas.put(self._result.final_message)
        except BaseException as exc:
            self._error = exc
        finally:
            self._deltas.put(_STREAM_COMPLETED)

    def _on_event(self, event: dict[str, Any]) -> None:
        if self._event_callback is not None:
            self._event_callback(event)
        if event.get("type") != "token_delta" or event.get("module") != "action":
            return
        metadata = event.get("metadata")
        if isinstance(metadata, dict) and metadata.get("structured") is True:
            return
        content = event.get("content")
        if content:
            self._emitted_action_text = True
            if self._yield_action_deltas:
                self._deltas.put(str(content))


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
    events_schema: dict[str, dict[str, Any]] | None = None

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
        self.events_schema = resolve_events_schema(self.events_schema)

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
        events_schema: dict[str, dict[str, Any]] | None = None,
    ) -> WorkflowResult:
        active_events_schema = (
            self.events_schema
            if events_schema is None
            else normalize_events_schema(events_schema)
        )
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
                        events_schema=active_events_schema,
                    )
                ),
                set(active_events_schema),
            )
            state.set_structured_field_callback(
                lambda module_name, field, value, metadata: event_callback(
                    self.structured_field_event(
                        module_name=module_name,
                        field=field,
                        value=value,
                        metadata=metadata,
                        state=state,
                        events_schema=active_events_schema,
                    )
                ),
                {
                    module: tuple(str(field) for field in schema["fields"])
                    for module, schema in active_events_schema.items()
                },
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

                if self._should_emit_stage_event(current, event_callback, active_events_schema):
                    event_callback(
                        self._stage_event(
                            phase="start",
                            status="running",
                            module_name=current,
                            module=module,
                            state=state,
                            visit_count=state.visit_counts.get(current, 1),
                            events_schema=active_events_schema,
                        )
                    )
                raw_output = module(state)
                output = _normalize_output(current, raw_output, state)
                state.apply(output)
                next_module = _next_module_after(current, output, self.modules)
                if self._should_emit_stage_event(current, event_callback, active_events_schema):
                    finish_event = self._stage_event(
                        phase="finish",
                        status="done",
                        module_name=current,
                        module=module,
                        state=state,
                        visit_count=state.visit_counts.get(current, 1),
                        events_schema=active_events_schema,
                    )
                    finish_event.update(
                        {
                            "fields": _completed_fields_for_stage(
                                schema=active_events_schema[current],
                                values=state.completed_structured_fields_for(current),
                            ),
                            "output": output,
                            "next_module": next_module,
                        }
                    )
                    event_callback(finish_event)
                current = next_module
        except WorkflowAborted as exc:
            aborted = True
            abort_reason = exc.reason
            if current is not None and self._should_emit_stage_event(current, event_callback, active_events_schema):
                module = self.modules.get(current)
                abort_event = self._stage_event(
                    phase="abort",
                    status="error",
                    module_name=current,
                    module=module,
                    state=state,
                    visit_count=state.visit_counts.get(current, 0),
                    events_schema=active_events_schema,
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

    def stream(
        self,
        user_message: str | None = None,
        *,
        workflow_id: str | None = None,
        session_id: str | None = None,
        memory: MemoryStore | None = None,
        attachments: list[Any] | None = None,
        memory_store: PersistentMemory | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        events_schema: dict[str, dict[str, Any]] | None = None,
        yield_action_deltas: bool | None = None,
    ) -> WorkflowStream:
        """Create an iterator of user-visible action text.

        This method accepts the same workflow input, session, memory, and
        attachment arguments as :meth:`run`. ``event_callback`` receives the
        same stage, token, and structured-field events as :meth:`run`. By
        default, the iterator yields user-visible Action token deltas only when no callback is
        supplied. This prevents double output when a callback itself renders
        ``token_delta`` events. Set ``yield_action_deltas=True`` to receive
        both event callbacks and iterator deltas, or ``False`` to use the
        iterator only for completion and ``stream.result``.
        """
        resolved_yield_action_deltas = (
            event_callback is None if yield_action_deltas is None else yield_action_deltas
        )
        return WorkflowStream(
            self,
            {
                "user_message": user_message,
                "workflow_id": workflow_id,
                "session_id": session_id,
                "memory": memory,
                "attachments": attachments,
                "memory_store": memory_store,
                "events_schema": events_schema,
            },
            event_callback,
            resolved_yield_action_deltas,
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
        events_schema: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        schema = events_schema[module_name]
        return {
            "type": "stage",
            "phase": phase,
            "status": status,
            "stage": module_name,
            "label": schema["label"],
            "module": module_name,
            "module_class": module.__class__.__name__ if module is not None else None,
            "workflow_name": self.workflow_name,
            "workflow_id": state.workflow_id,
            "session_id": state.session_id,
            "state": state,
            "visit_count": visit_count,
            "visit_id": _visit_id(state, module_name, visit_count),
            "schema": _schema_snapshot(schema),
            "metadata": {
                "schema_label": schema["label"],
                "schema_fields": list(schema["fields"]),
                "schema_metadata": dict(schema["metadata"]),
            },
        }

    def _should_emit_stage_event(
        self,
        module_name: str,
        event_callback: Callable[[dict[str, Any]], None] | None,
        events_schema: dict[str, dict[str, Any]],
    ) -> bool:
        return event_callback is not None and module_name in events_schema

    def token_delta_event(
        self,
        *,
        module_name: str,
        content: str,
        metadata: dict[str, Any] | None,
        state: WorkflowState,
        events_schema: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        module = self.modules.get(module_name)
        schema = (self.events_schema if events_schema is None else events_schema).get(module_name)
        return {
            "type": "token_delta",
            "phase": "delta",
            "status": "streaming",
            "module": module_name,
            "module_class": module.__class__.__name__ if module is not None else None,
            "content": content,
            "label": schema["label"] if schema is not None else None,
            "schema": _schema_snapshot(schema) if schema is not None else None,
            "metadata": {
                **dict(metadata or {}),
                **(
                    {
                        "schema_label": schema["label"],
                        "schema_fields": list(schema["fields"]),
                        "schema_metadata": dict(schema["metadata"]),
                    }
                    if schema is not None
                    else {}
                ),
            },
            "workflow_name": self.workflow_name,
            "workflow_id": state.workflow_id,
            "session_id": state.session_id,
            "visit_count": state.visit_counts.get(module_name, 0),
            "visit_id": _visit_id(state, module_name, state.visit_counts.get(module_name, 0)),
        }

    def structured_field_event(
        self,
        *,
        module_name: str,
        field: str,
        value: Any,
        metadata: dict[str, Any] | None,
        state: WorkflowState,
        events_schema: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        resolved_schema = (self.events_schema if events_schema is None else events_schema).get(module_name)
        if resolved_schema is None:
            raise ValueError(f"no events_schema is configured for module {module_name!r}")
        module = self.modules.get(module_name)
        visit_count = state.visit_counts.get(module_name, 0)
        return {
            "type": "structured_field",
            "phase": "field",
            "status": "completed",
            "module": module_name,
            "module_class": module.__class__.__name__ if module is not None else None,
            "field": field,
            "value": value,
            "label": resolved_schema["label"],
            "schema": _schema_snapshot(resolved_schema),
            "metadata": {
                **dict(metadata or {}),
                "schema_label": resolved_schema["label"],
                "schema_fields": list(resolved_schema["fields"]),
                "schema_metadata": dict(resolved_schema["metadata"]),
            },
            "workflow_name": self.workflow_name,
            "workflow_id": state.workflow_id,
            "session_id": state.session_id,
            "visit_count": visit_count,
            "visit_id": _visit_id(state, module_name, visit_count),
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
    workflow_error = state.last_workflow_error
    if workflow_error:
        return f"[workflow ended with error] {workflow_error['message']}"
    err = state.last_action_error
    if err:
        return f"[workflow ended with error] {err.get('message', '')}"
    return str(state.lookup("latest_final_message") or "")


def _schema_snapshot(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": schema["label"],
        "fields": list(schema["fields"]),
        "metadata": dict(schema["metadata"]),
    }


def _completed_fields_for_stage(
    *,
    schema: dict[str, Any],
    values: dict[str, Any],
) -> list[dict[str, Any]]:
    configured_fields = list(schema["fields"])
    ordered_fields = (
        list(values)
        if ALL_STRUCTURED_FIELDS in configured_fields
        else [field for field in configured_fields if field in values]
    )
    return [{"field": field, "value": values[field]} for field in ordered_fields]


def _visit_id(state: WorkflowState, module_name: str, visit_count: int) -> str:
    return f"{state.workflow_id}:{module_name}:{visit_count}"