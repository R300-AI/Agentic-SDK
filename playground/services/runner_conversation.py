from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from agentic_sdk.core import ContextEntryType, InContextMemory, WorkflowResult


_STATE_VERSION = 1
_MAX_TURN_CHARS = 6_000
_MAX_EVIDENCE_CHARS = 4_000


SESSION_KEY = "runner_conversation"
"""Where the runner keeps the conversation it is in the middle of.

Named here rather than in the route, because whoever starts a different
conversation — picking another agent, say — has to be able to drop it.
"""


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
    revision: int = 0
    turns: tuple[RunnerConversationTurn, ...] = ()
    retrieval_evidence: str = ""
    state_version: int = _STATE_VERSION

    @classmethod
    def start(cls) -> "RunnerConversationState":
        return cls(conversation_id=uuid.uuid4().hex)

    @classmethod
    def from_dict(cls, value: object) -> "RunnerConversationState":
        if not isinstance(value, dict):
            return cls.start()
        raw_turns = value.get("turns") if isinstance(value.get("turns"), list) else []
        turns = tuple(_turn_from_dict(turn) for turn in raw_turns if _turn_from_dict(turn) is not None)
        return cls(
            conversation_id=str(value.get("conversation_id") or uuid.uuid4().hex),
            revision=max(0, int(value.get("revision") or 0)),
            turns=turns,
            retrieval_evidence=_bounded_text(value.get("retrieval_evidence"), _MAX_EVIDENCE_CHARS),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "state_version": self.state_version,
            "conversation_id": self.conversation_id,
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
            revision=self.revision + 1,
            turns=(*self.turns, RunnerConversationTurn(role=role, content=bounded_content, metadata=_safe_metadata(metadata))),
            retrieval_evidence=self.retrieval_evidence,
        )

    def rebased_onto(self, current: "RunnerConversationState") -> "RunnerConversationState | None":
        """這一筆寫回是在舊狀態上算出來的；把新增的回合接到目前狀態上。

        連著講兩句時兩輪的寫回會交錯，後到的那一筆版本號已經過期。整筆拒絕的
        代價是那一輪的回答就此消失，而畫面只能叫使用者重新整理頁面。

        只有「內容相容」才接得上：目前狀態的每一則，在這一筆裡都要是同一個角色
        且內容相同或更長——更長的情形就是打斷之後的截短先落地了，那一則要以
        目前狀態為準。對不上就不是同一段對話的延伸，維持衝突。
        """
        if self.conversation_id != current.conversation_id:
            return None
        if len(self.turns) < len(current.turns):
            return None
        for mine, theirs in zip(self.turns, current.turns):
            if mine.role != theirs.role or not mine.content.startswith(theirs.content):
                return None
        added = self.turns[len(current.turns):]
        if not added:
            return None
        return RunnerConversationState(
            conversation_id=current.conversation_id,
            revision=current.revision + 1,
            turns=(*current.turns, *added),
            retrieval_evidence=self.retrieval_evidence or current.retrieval_evidence,
        )

    def cut_off_after_the_run(self, *, heard_seconds: float | None) -> "RunnerConversationState":
        """The record as the person heard it, corrected once playback stopped.

        Playback outlives the run. An answer is produced in a few seconds and
        takes far longer to say, so most interruptions arrive with no run left
        to stop and the turn already stored whole — including the half nobody
        heard. Only whatever played the audio knows how far it got, and it can
        only say so afterwards. See ADR-0008.

        Unknown stays unknown: something can notice an interruption without
        having played a note, and trimming to nothing there would erase an
        answer the person did hear.
        """
        from agentic_sdk.audio import heard_portion

        if heard_seconds is None:
            return self
        # The answer being played, not the last thing written down. Talking
        # over an answer interrupts it and asks the next question in one go,
        # and the question reaches the record first: a run registers what was
        # said the moment it starts, while this takes a round trip through the
        # page. Insisting on the last turn finds that question and corrects
        # nothing.
        spoken_at = next(
            (index for index in range(len(self.turns) - 1, -1, -1) if self.turns[index].role == "assistant"),
            None,
        )
        if spoken_at is None:
            return self
        answer = self.turns[spoken_at]
        heard = heard_portion(answer.content, heard_seconds)
        if heard == answer.content:
            return self
        before, after = self.turns[:spoken_at], self.turns[spoken_at + 1 :]
        kept = (
            (*before, *after)
            if not heard
            # Nothing reached them, so nothing happened for them to refer back
            # to — the same rule the run itself applies.
            else (
                *before,
                RunnerConversationTurn(
                    role="assistant",
                    content=heard,
                    metadata={**answer.metadata, "interrupted": True},
                ),
                *after,
            )
        )
        return RunnerConversationState(
            conversation_id=self.conversation_id,
            revision=self.revision + 1,
            turns=kept,
            retrieval_evidence=self.retrieval_evidence,
        )

    def update_from_result(self, result: WorkflowResult) -> "RunnerConversationState":
        return self.append_assistant(
            _what_reached_the_person(result), retrieval_evidence=_retrieval_evidence(result)
        )


def _what_reached_the_person(result: WorkflowResult) -> str:
    """The answer as far as it got, when the page reports how far that was.

    Playback happens in the browser and finishes on its own schedule, so the
    duration arrives after the run has ended — too late for the workflow and
    far too specific to ask of every kind of memory. The record this trims is
    the Playground's own, which is the one the next run is built from. See
    ADR-0002.
    """
    payload = getattr(result, "interrupt_payload", None) or {}
    if not getattr(result, "interrupted", False):
        return result.final_message
    delivered = str(payload.get("delivered") or result.final_message or "")
    heard_seconds = payload.get("heard_seconds")
    if heard_seconds is None:
        # Unknown is not nought: something noticed the interruption without
        # having played a note, and trimming to nothing would erase an answer
        # the person did hear.
        return delivered
    from agentic_sdk.audio import heard_portion

    return heard_portion(delivered, heard_seconds)


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