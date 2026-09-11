from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol, TypedDict, runtime_checkable

from agentic_sdk.core.entities import Attachment, ContextEntry, ContextEntryType, Entities

if TYPE_CHECKING:
    from agentic_sdk.core.cancellation import CancellationToken
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
    # What the planning module may choose from on this visit, each with the
    # mounted module's own description when it has one. Set by the workflow
    # before every visit to planning, because only the workflow knows which
    # modules are mounted — see ADR-0005.
    plan_options: dict[str, str | None] = field(default_factory=dict)
    last_action_result: dict[str, Any] | None = None
    last_action_error: dict[str, Any] | None = None
    last_workflow_error: dict[str, str] | None = None
    attachments: list[Attachment] = field(default_factory=list)
    # Carried on the state because that is what every module already receives.
    # A module that streams can offer it to the transport without the workflow
    # having to reach inside the module to wire anything up.
    cancel: "CancellationToken | None" = None
    delivered_so_far: str = ""
    _token_delta_callback: Callable[[str, str, dict[str, Any]], None] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _token_delta_modules: set[str] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _delivering_modules: set[str] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _structured_field_callback: Callable[[str, str, Any, dict[str, Any]], None] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _structured_fields_by_module: dict[str, tuple[str, ...]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _emitted_structured_fields: set[tuple[str, int, str]] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _completed_structured_fields: dict[tuple[str, int], dict[str, Any]] = field(
        default_factory=dict,
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

    def report_delivered(self, delivered_so_far: str) -> None:
        """Record how much of the answer actually reached the person.

        Only whoever did the delivering knows this, and it is not the same as
        how much the model has written: an answer cut off halfway leaves a tail
        that exists only on paper. Carrying that tail forward would let the next
        turn refer back to something nobody received.

        Channel-neutral on purpose. A screen delivers and so does a speaker,
        and the core is not allowed to know which — see ADR-0001 and ADR-0002.
        """
        self.delivered_so_far = str(delivered_so_far or "")

    def should_stop(self) -> bool:
        """Whether whoever started this run has asked for it to stop."""
        token = self.cancel
        return bool(token is not None and token.cancelled)

    def set_token_delta_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], None] | None,
        modules: set[str] | None = None,
        delivering_modules: set[str] | None = None,
    ) -> None:
        """Subscribe to token deltas, and name which of them reach the person.

        Streaming and delivering are two different things. A plan and a check
        stream as well, and both stream raw JSON to a trace panel nobody reads
        as an answer. Counting those as delivered hands an interrupted turn
        back its own scratch work wrapped around the sentence — see ADR-0002.

        Whoever wires the modules together knows which one answers; the core
        does not, and stays out of it.
        """
        self._token_delta_callback = callback
        self._token_delta_modules = set(modules or ())
        self._delivering_modules = set(delivering_modules or ())

    def emit_token_delta(
        self,
        module: str,
        content: object,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._token_delta_callback is None or str(module) not in self._token_delta_modules or content is None:
            return
        resolved_content = str(content)
        if not resolved_content:
            return
        # Reaching the person is what delivery means, so only the answering
        # module adds to the record. A structured stream is the envelope the
        # answer arrives in — field names and a second channel — so whoever
        # produces one reports delivery outright instead. This is the only
        # place the core learns what reached them without being told.
        resolved_metadata = dict(metadata or {})
        if str(module) in self._delivering_modules and not resolved_metadata.get("structured"):
            self.delivered_so_far += resolved_content
        self._token_delta_callback(str(module), resolved_content, resolved_metadata)

    def set_structured_field_callback(
        self,
        callback: Callable[[str, str, Any, dict[str, Any]], None] | None,
        fields_by_module: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._structured_field_callback = callback
        self._structured_fields_by_module = dict(fields_by_module or {})

    def structured_fields_for(self, module: str) -> tuple[str, ...]:
        return self._structured_fields_by_module.get(str(module), ())

    def completed_structured_fields_for(self, module: str) -> dict[str, Any]:
        """Return configured fields completed during the module's current visit."""
        visit_count = self.visit_counts.get(str(module), 0)
        return dict(self._completed_structured_fields.get((str(module), visit_count), {}))

    def emit_structured_field(
        self,
        module: str,
        field: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        module_name = str(module)
        field_path = str(field)
        visit_count = self.visit_counts.get(module_name, 0)
        key = (module_name, visit_count, field_path)
        if (
            self._structured_field_callback is None
            or not _includes_structured_field(self.structured_fields_for(module_name), field_path)
            or key in self._emitted_structured_fields
        ):
            return
        self._emitted_structured_fields.add(key)
        self._completed_structured_fields.setdefault((module_name, visit_count), {})[field_path] = value
        self._structured_field_callback(module_name, field_path, value, dict(metadata or {}))


def _includes_structured_field(configured_fields: tuple[str, ...], field_path: str) -> bool:
    return "*" in configured_fields or field_path in configured_fields


@dataclass
class WorkflowResult:
    workflow_id: str
    final_message: str
    session_id: str = "default"
    aborted: bool = False
    abort_reason: str | None = None
    # Told apart from aborted so a caller can resume rather than apologise.
    interrupted: bool = False
    interrupt_payload: dict[str, Any] = field(default_factory=dict)
    entries: list[ContextEntry] = field(default_factory=list)
    visit_counts: dict[str, int] = field(default_factory=dict)
    usage: dict[str, Any] | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    memory: MemoryStore | None = None


class WorkflowAborted(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason