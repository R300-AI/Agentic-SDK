from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from queue import Queue
import time
from threading import Thread
from typing import Any
import uuid

from agentic_sdk.core.cancellation import CancellationToken, WorkflowInterrupted
from agentic_sdk.core.entities import ContextEntry, ContextEntryType
from agentic_sdk.core.events import ALL_STRUCTURED_FIELDS, normalize_events_schema, resolve_events_schema
from agentic_sdk.core.gates import Gates
from agentic_sdk.core.failures import EndpointUnavailable
from agentic_sdk.core.module import Module, ModuleOutput, WorkflowAborted, WorkflowResult, WorkflowState
from agentic_sdk.defaults import DEFAULT_MODULE_FAILURE_MESSAGES
from agentic_sdk.memory.in_context import InContextMemory, MemoryStore
from agentic_sdk.memory.in_memory import InMemoryStore
from agentic_sdk.memory.protocol import CrossContextMemory


_STREAM_COMPLETED = object()
_PLANNING_CHOICES = ("retrieve", "reflect", "action")

# What a module's failure is filed as: the entry type that module would have
# written had it succeeded, so planning can tell which module is missing its
# result without a type of its own for failure.
_FAILURE_ENTRY_TYPE = {
    "perceive": ContextEntryType.PERCEIVED,
    "plan": ContextEntryType.PLAN_DECISION,
    "retrieve": ContextEntryType.RETRIEVED,
    "action": ContextEntryType.ACTION_RESULT,
    "reflect": ContextEntryType.REFLECTION,
}


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
    memory_store: CrossContextMemory | None = None
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
        from agentic_sdk.modules.plan import PassThroughPlan
        from agentic_sdk.modules.retrieve import KeywordRetrieve

        self.gates = self.gates or Gates()
        self._memory_factory = _memory_factory_from(self.memory_type)
        if _is_memory_store(self.memory_type):
            self.memory = self.memory_type
        # Every run passes through planning, so there is always a planning
        # module. Nobody choosing one means planning by a fixed rule, not
        # skipping the step — see ADR-0005.
        self.modules = {
            "perceive": self.perceive or PassThroughPerceive(),
            "plan": self.plan or PassThroughPlan(),
            "retrieve": self.retrieve or KeywordRetrieve(),
            "action": self.action or DirectAnswerAction(),
        }
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
        memory_store: CrossContextMemory | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        events_schema: dict[str, dict[str, Any]] | None = None,
        cancel: "CancellationToken | None" = None,
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
            # A perceive module may already know what this turn is about. Speech
            # arrives when the person feels like talking, not when run() is
            # called, so demanding the words up front would mean a voice agent
            # could never be started without typing what was just said.
            supplied = _pending_input_from(self.perceive)
            if supplied:
                state_memory.append_message("user", supplied, attachments=list(attachments or []))
                latest_user_turn = state_memory.latest_user_turn()
        if latest_user_turn is None:
            raise ValueError("Workflow.run requires user_message or a conversation containing a user turn.")

        resolved_memory_store = memory_store or self.memory_store
        if resolved_memory_store is None and isinstance(state_memory, CrossContextMemory):
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
                {self.modules["action"].name},
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
        stop_reason = "end_turn"
        abort_reason: str | None = None
        interrupted = False
        interrupt_payload: dict[str, Any] = {}

        state.prompt_budget = self.gates.max_prompt_tokens
        _let_memory_collect_itself(state_memory, self.gates.max_prompt_tokens)
        state.cancel = cancel

        try:
            while current is not None:
                total_hops += 1
                if cancel is not None and cancel.cancelled:
                    raise WorkflowInterrupted(cancel.reason or "cancelled", cancel.payload)
                self.gates.before_visit(current, state, total_hops)
                state.increment_visit(current)

                module = self.modules.get(current)
                if module is None:
                    raise WorkflowAborted(f"unknown module '{current}'", "misconfigured")
                if current == "plan":
                    state.plan_options = _plan_options(self.modules, state, self.gates)

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
                try:
                    raw_output = module(state)
                except (WorkflowInterrupted, WorkflowAborted):
                    # Steering and self-protection, not a module failing at its
                    # job. Both already say what they are.
                    raise
                except Exception as exc:  # noqa: BLE001 - filed below, whatever it was
                    current = self._module_failed(
                        current, exc, state, event_callback, active_events_schema
                    )
                    continue
                output = _normalize_output(current, raw_output, state)
                state.apply(output)
                next_module = _next_module_after(current, output, state)
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
            if cancel is not None and cancel.cancelled:
                # Someone spoke while the last module was running, and there is
                # no next visit left to notice it. Falling out of the loop here
                # would file the turn as finished and keep every word of it,
                # including the ones that were cut off before anyone heard
                # them. Where the audio plays somewhere else this is the
                # ordinary case, not a corner of one: the words are handed over
                # in an instant and talked over long afterwards.
                raise WorkflowInterrupted(cancel.reason or "cancelled", cancel.payload)
        except WorkflowInterrupted as exc:
            # Not a failure. Someone asked for this to stop, and the result
            # says so plainly so the caller can pick up where it left off
            # rather than reporting a fault to the person who interrupted.
            # Interrupted, not aborted. An abort is the workflow protecting
            # itself and deserves an error on screen; this is the person
            # steering, and everything downstream reads the abort flag to
            # decide which of those to show.
            interrupted = True
            stop_reason = "interrupted"
            # One interruption, two accounts of it. A stream that sees the stop
            # flag reports how much it had produced by then; whoever asked for
            # the stop reports what they had received. Only the second was
            # there, so it stands where the two disagree, and the first is kept
            # where they do not.
            # A key reported as nothing is not a report: something noticed the
            # stop without being in a position to say anything about it, and
            # letting that land would replace what was known with what was not.
            stopper = {
                key: value
                for key, value in (cancel.payload if cancel is not None and cancel.cancelled else {}).items()
                if value is not None
            }
            account = {**exc.payload, **stopper}
            # Ask whoever delivered how much of it landed, and hand over that
            # account of the interruption. Audio played somewhere else leaves
            # the module whole and is cut off later, so this is the first
            # moment the answer exists. The engine knows something was cut
            # short, never that it was cut short mid-sentence out of a speaker.
            interrupt_payload = {
                **account,
                "reason": (
                    cancel.reason
                    if cancel is not None and cancel.cancelled and cancel.reason
                    else exc.reason
                ),
                "delivered": state.delivered_when_cut_short(account),
            }
            # Say so on the trace, and say where. Whoever is tuning how eagerly
            # the agent gives way needs to know it was stopped while answering,
            # not while deciding what to look up.
            if current is not None and self._should_emit_stage_event(current, event_callback, active_events_schema):
                event = self._stage_event(
                    phase="abort",
                    status="interrupted",
                    module_name=current,
                    module=self.modules.get(current),
                    state=state,
                    visit_count=state.visit_counts.get(current, 1),
                    events_schema=active_events_schema,
                )
                # Why, not just where. The abort reason belongs to the branch
                # that stops the workflow itself; this branch has its own.
                event["reason"] = exc.reason
                event["interrupted"] = True
                event_callback(event)
        except WorkflowAborted as exc:
            stop_reason = exc.stop_reason
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
        if interrupted:
            # What reached the person is the only part of this turn that
            # happened to them. The rest was written and received by nobody.
            final_message = interrupt_payload.get("delivered", state.delivered_so_far)
        elif stop_reason != "end_turn" and not final_message:
            # A limit stopped the run part-way. Whatever had already been
            # delivered is still what happened to the person; the limit's
            # own wording is for the trace.
            final_message = state.delivered_so_far
        if final_message and state.memory is not None:
            latest_assistant = state.memory.latest_assistant_turn()
            if latest_assistant is None or latest_assistant.content != final_message:
                state.memory.append_message(
                    "assistant",
                    final_message,
                    metadata={"source": "workflow.run", "interrupted": True} if interrupted else {"source": "workflow.run"},
                )
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
            stop_reason=stop_reason,
            interrupt_payload=interrupt_payload,
            entries=list(state.entries),
            visit_counts=dict(state.visit_counts),
            usage=state.payload.get("_llm_usage"),
            entities=state.entities.as_dict(),
            memory=state.memory.copy_for_run() if state.memory is not None else None,
        )

    def converse(
        self,
        *,
        audio: "Iterable[bytes] | None" = None,
        poll_seconds: float = 0.02,
        tail_seconds: float = 2.0,
        **run_kwargs: Any,
    ) -> Iterator[WorkflowResult]:
        """A spoken conversation: one result for each thing the person says.

        The wiring around a voice turn never varies between applications, and
        every part of it is easy to get wrong in a way that looks like the
        agent being broken. A run that reuses a cancelled token ends before it
        starts. A microphone that stops while the answer plays cannot be
        interrupted at all. Those belong here rather than in everyone's code.

        What stays outside is the device. ``audio`` is anything that yields
        16-bit mono chunks — a microphone, a recording, a socket — because
        audio sources are not interchangeable and the core does not know one
        from another, which is ADR-0003. Leave it out and whoever holds the
        microphone keeps feeding the perceive module; this then only runs the
        turns.

        Ends when the audio runs out and nothing more is said. The wait after
        it runs out is not politeness: a transcription service decides an
        utterance is over by hearing silence, so the last sentence of a
        recording arrives after the recording has finished.
        """
        listener = self.modules.get("perceive")
        if not (hasattr(listener, "hear") and hasattr(listener, "pending_input")):
            raise TypeError(
                "converse() needs a perceive module that listens, such as VoiceTextPerceive."
            )

        ended_at: float | None = None

        def pump() -> None:
            nonlocal ended_at
            try:
                for chunk in audio:
                    listener.hear(chunk)
            finally:
                ended_at = time.monotonic()

        if audio is not None:
            Thread(target=pump, daemon=True).start()

        while True:
            if listener.pending_input():
                # A token belongs to one turn. The one before it is spent —
                # someone interrupted with it, or it simply ran its course.
                yield self.run(cancel=CancellationToken(), **run_kwargs)
                continue
            if ended_at is not None and time.monotonic() - ended_at > tail_seconds:
                return
            time.sleep(poll_seconds)

    def stream(
        self,
        user_message: str | None = None,
        *,
        workflow_id: str | None = None,
        session_id: str | None = None,
        memory: MemoryStore | None = None,
        attachments: list[Any] | None = None,
        memory_store: CrossContextMemory | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        events_schema: dict[str, dict[str, Any]] | None = None,
        yield_action_deltas: bool | None = None,
        cancel: "CancellationToken | None" = None,
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
                "cancel": cancel,
            },
            event_callback,
            resolved_yield_action_deltas,
        )

    def _module_failed(
        self,
        module_name: str,
        exc: Exception,
        state: WorkflowState,
        event_callback: Callable[[dict[str, Any]], None],
        events_schema: dict[str, dict[str, Any]],
    ) -> str | None:
        """File one module's failure and say where the run goes next.

        A failure does not change where the run goes, only what is on record.
        Perception, retrieval and reflection hand back to planning whether or
        not they worked, and the action ends the run either way — the routing
        ADR-0005 fixed. What changes is that the failure is written onto the
        context for planning to read, instead of a module ending the run from
        the inside. Planning failing is the one case with nowhere to go: nobody
        else decides, so the run ends.
        """
        message = DEFAULT_MODULE_FAILURE_MESSAGES[module_name]
        state.append(
            ContextEntry(
                type=_FAILURE_ENTRY_TYPE[module_name],
                content=message,
                is_error=True,
                metadata={
                    # "ok" repeats is_error because the modules that catch their
                    # own failures have always written it, and the trace reads it.
                    "ok": False,
                    "stage": module_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
        )
        if isinstance(exc, EndpointUnavailable):
            # The endpoint layer has already retried. Handing this to
            # planning would spend the same call again against a service
            # that is down, and the person waits through every one of them.
            state.last_workflow_error = {"stage": module_name, "message": message}
            raise WorkflowAborted(message, "endpoint_unavailable") from exc
        if module_name == "plan":
            # Nobody else decides where the run goes, so it ends. The abort
            # branch announces that; announcing it here too reads as two faults.
            state.last_workflow_error = {"stage": module_name, "message": message}
            raise WorkflowAborted(message, "planning_failed") from exc
        if self._should_emit_stage_event(module_name, event_callback, events_schema):
            event = self._stage_event(
                phase="finish",
                status="error",
                module_name=module_name,
                module=self.modules.get(module_name),
                state=state,
                visit_count=state.visit_counts.get(module_name, 1),
                events_schema=events_schema,
            )
            event["reason"] = message
            event["error_type"] = type(exc).__name__
            event["error_message"] = str(exc)
            event_callback(event)
        if module_name == "action":
            # The action ends the run whether or not it worked — ADR-0005. The
            # person gets the plain sentence instead of silence, and a run is
            # not retried into five calls against an endpoint that is down.
            state.last_action_error = {"type": type(exc).__name__, "message": message}
            return None
        return "plan"

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


_UNSET = object()


def _let_memory_collect_itself(memory: MemoryStore, ceiling: int | None) -> None:
    """Point a memory that can collect its own oldest parts at the ceiling.

    Two numbers could say when to collect: the ceiling on a whole request, and
    a threshold given to the memory when it was built. The one given to the
    memory wins, because somebody chose it for that memory. Where nobody chose
    one, the ceiling becomes it — otherwise a run that declares a ceiling gets
    messages cut at the seam and never gets them collected into topics, which
    is the difference between losing what was said and keeping it as a topic.

    The conversation is only part of a request, so collecting it down to the
    ceiling does not on its own make the request fit. It is not meant to: what
    the conversation gives up here it keeps as a topic, and whatever still does
    not fit is cut afterwards. Compare the conversation against a fraction of
    the ceiling instead and the fraction would be a made-up number.
    """
    if ceiling is None:
        return
    if getattr(memory, "compaction_threshold_tokens", _UNSET) is None:
        memory.compaction_threshold_tokens = ceiling


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
        # Spellings this table has always tolerated, kept for the same reason
        # "persistant" is here: someone typed it and the workflow still ran.
        if key in {"cross_context", "persistent", "persistant", "in_memory"}:
            return InMemoryStore
        raise ValueError(f"unknown memory_type {memory_type!r}; use 'in_context', 'cross_context', or a MemoryStore instance")
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


def _pending_input_from(module: Any) -> str:
    """What a module has already taken in, before the workflow asks for it.

    Optional: a module without it simply has nothing waiting.
    """
    pending = getattr(module, "pending_input", None)
    if not callable(pending):
        return ""
    return str(pending() or "").strip()


def _plan_options(modules: dict[str, Module], state: WorkflowState, gates: Gates) -> dict[str, str | None]:
    """The steps planning may choose from, each with its module's description.

    Reflect drops out once planning has used up its rounds with it. The run is
    not aborted: planning can still retrieve or act.
    """
    reflect_available = state.visit_counts.get("reflect", 0) < gates.max_reflect_rounds
    return {
        role: _module_description(modules[role])
        for role in _PLANNING_CHOICES
        if role in modules and (role != "reflect" or reflect_available)
    }


def _module_description(module: Module) -> str | None:
    description = getattr(module, "description", None)
    return str(description) if isinstance(description, str) and description else None


def _next_module_after(current: str, output: ModuleOutput, state: WorkflowState) -> str | None:
    """Where the run goes next. The workflow decides this, not the module.

    Planning is the only step that chooses. Everything it can send work to
    hands back to it, and the action ends the run: whatever the action changed
    is observed by whoever starts the next turn — see ADR-0005.
    """
    if current == "plan":
        choice = output.get("next_module")
        return choice if isinstance(choice, str) and choice in state.plan_options else "action"
    if current == "action":
        return None
    return "plan"


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