from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from agentic_sdk.core import ContextEntryType, InContextMemory, WorkflowResult


_STATE_VERSION = 1
_MAX_TURN_CHARS = 6_000
_MAX_EVIDENCE_CHARS = 4_000


@dataclass(frozen=True)
class RunnerConversationTurn:
    role: str
    content: str
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {"role": self.role, "content": self.content, "metadata": self.metadata}


@dataclass(frozen=True)
class RunnerConversationState:
    conversation_id: str
    workflow_fingerprint: str
    revision: int = 0
    turns: tuple[RunnerConversationTurn, ...] = ()
    retrieval_evidence: str = ""
    state_version: int = _STATE_VERSION

    @classmethod
    def for_workflow(cls, python_source: str) -> "RunnerConversationState":
        return cls(conversation_id=uuid.uuid4().hex, workflow_fingerprint=workflow_fingerprint(python_source))

    @classmethod
    def from_dict(cls, value: object, *, python_source: str) -> "RunnerConversationState":
        fingerprint = workflow_fingerprint(python_source)
        if not isinstance(value, dict):
            return cls.for_workflow(python_source)
        raw_turns = value.get("turns") if isinstance(value.get("turns"), list) else []
        turns = tuple(_turn_from_dict(turn) for turn in raw_turns if _turn_from_dict(turn) is not None)
        return cls(
            conversation_id=str(value.get("conversation_id") or uuid.uuid4().hex),
            workflow_fingerprint=fingerprint,
            revision=max(0, int(value.get("revision") or 0)),
            turns=turns,
            retrieval_evidence=_bounded_text(value.get("retrieval_evidence"), _MAX_EVIDENCE_CHARS),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "state_version": self.state_version,
            "conversation_id": self.conversation_id,
            "workflow_fingerprint": self.workflow_fingerprint,
            "revision": self.revision,
            "turns": [turn.as_dict() for turn in self.turns],
            "retrieval_evidence": self.retrieval_evidence,
        }

    def memory(self, *, workflow_name: str) -> InContextMemory:
        memory = InContextMemory(
            workflow_name=workflow_name,
            session_id=self.conversation_id,
            metadata={"continuity_evidence": self.retrieval_evidence} if self.retrieval_evidence else {},
        )
        for turn in self.turns:
            memory.append_message(turn.role, turn.content, metadata=turn.metadata)
        return memory

    def append_user(self, content: str, *, metadata: dict[str, object] | None = None) -> "RunnerConversationState":
        return self._append_turn("user", content, metadata=metadata)

    def append_assistant(
        self,
        content: str,
        *,
        metadata: dict[str, object] | None = None,
        retrieval_evidence: str | None = None,
    ) -> "RunnerConversationState":
        state = self._append_turn("assistant", content, metadata=metadata)
        return RunnerConversationState(
            conversation_id=state.conversation_id,
            workflow_fingerprint=state.workflow_fingerprint,
            revision=state.revision,
            turns=state.turns,
            retrieval_evidence=_bounded_text(retrieval_evidence, _MAX_EVIDENCE_CHARS) if retrieval_evidence else self.retrieval_evidence,
        )

    def append_turns(
        self,
        turns: tuple[RunnerConversationTurn, ...],
        *,
        retrieval_evidence: str | None = None,
    ) -> "RunnerConversationState":
        bounded_turns = tuple(
            RunnerConversationTurn(
                role=turn.role,
                content=_bounded_text(turn.content, _MAX_TURN_CHARS),
                metadata=_safe_metadata(turn.metadata),
            )
            for turn in turns
            if turn.role in {"user", "assistant", "tool"} and _bounded_text(turn.content, _MAX_TURN_CHARS)
        )
        if not bounded_turns:
            return self
        return RunnerConversationState(
            conversation_id=self.conversation_id,
            workflow_fingerprint=self.workflow_fingerprint,
            revision=self.revision + 1,
            turns=(*self.turns, *bounded_turns),
            retrieval_evidence=_bounded_text(retrieval_evidence, _MAX_EVIDENCE_CHARS) if retrieval_evidence else self.retrieval_evidence,
        )

    def _append_turn(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> "RunnerConversationState":
        bounded_content = _bounded_text(content, _MAX_TURN_CHARS)
        if not bounded_content:
            return self
        return RunnerConversationState(
            conversation_id=self.conversation_id,
            workflow_fingerprint=self.workflow_fingerprint,
            revision=self.revision + 1,
            turns=(*self.turns, RunnerConversationTurn(role=role, content=bounded_content, metadata=_safe_metadata(metadata))),
            retrieval_evidence=self.retrieval_evidence,
        )

    def update_from_result(self, result: WorkflowResult) -> "RunnerConversationState":
        return self.append_assistant(result.final_message, retrieval_evidence=_retrieval_evidence(result))


def workflow_fingerprint(python_source: str) -> str:
    return hashlib.sha256(str(python_source).encode("utf-8")).hexdigest()


def _turn_from_dict(value: object) -> RunnerConversationTurn | None:
    if not isinstance(value, dict):
        return None
    role = str(value.get("role") or "")
    if role not in {"user", "assistant", "tool"}:
        return None
    content = _bounded_text(value.get("content"), _MAX_TURN_CHARS)
    return RunnerConversationTurn(role=role, content=content, metadata=_safe_metadata(value.get("metadata"))) if content else None


def _safe_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
    return safe


def _bounded_text(value: object, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def _retrieval_evidence(result: WorkflowResult) -> str:
    for entry in reversed(result.entries):
        if entry.type == ContextEntryType.RETRIEVED or str(entry.type) == ContextEntryType.RETRIEVED.value:
            return _bounded_text(entry.content, _MAX_EVIDENCE_CHARS)
    return ""