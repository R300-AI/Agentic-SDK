from __future__ import annotations

import copy
import math
import re
import time

from agentic_sdk.core.entities import Attachment
from agentic_sdk.memory.in_context import ConversationRole, ConversationTurn
from agentic_sdk.memory.protocol import MemoryEntry, MemorySearchResult


class InMemoryStore:
    def __init__(
        self,
        *,
        workflow_name: str = "default",
        workflow_id: str = "default",
        session_id: str = "default",
    ) -> None:
        self.workflow_name = workflow_name
        self.workflow_id = workflow_id
        self.session_id = session_id
        self._entries: list[MemoryEntry] = []

    @property
    def turns(self) -> list[ConversationTurn]:
        return self._conversation_turns()

    def append(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)

    def append_turn(self, turn: ConversationTurn) -> ConversationTurn:
        stored = ConversationTurn(
            role=turn.role,
            content=turn.content,
            workflow_name=self.workflow_name,
            workflow_id=self.workflow_id,
            session_id=self.session_id,
            turn_index=len(self._conversation_turns()),
            attachments=copy.deepcopy(turn.attachments),
            metadata=copy.deepcopy(turn.metadata),
            turn_id=turn.turn_id,
            created_at=turn.created_at,
        )
        self.append(
            MemoryEntry(
                content=stored.content,
                workflow_name=stored.workflow_name,
                entry_type="conversation_turn",
                role=stored.role,
                workflow_id=stored.workflow_id,
                session_id=stored.session_id,
                turn_index=stored.turn_index,
                attachments=copy.deepcopy(stored.attachments),
                metadata=copy.deepcopy(stored.metadata),
                entry_id=stored.turn_id,
                created_at=stored.created_at,
                last_accessed_at=stored.created_at,
            )
        )
        return stored

    def append_message(
        self,
        role: ConversationRole,
        content: str,
        *,
        attachments: list[Attachment] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConversationTurn:
        return self.append_turn(
            ConversationTurn(
                role=role,
                content=str(content),
                workflow_name=self.workflow_name,
                workflow_id=self.workflow_id,
                session_id=self.session_id,
                attachments=list(attachments or []),
                metadata=dict(metadata or {}),
            )
        )

    def clear(self, workflow_name: str | None = None) -> None:
        if workflow_name is None:
            self._entries.clear()
            return
        self._entries = [entry for entry in self._entries if entry.workflow_name != workflow_name]

    def all_for_workflow(self, workflow_name: str) -> list[MemoryEntry]:
        return [entry for entry in self._entries if entry.workflow_name == workflow_name]

    def latest_turn(self, role: str | None = None) -> ConversationTurn | None:
        turns = self._conversation_turns()
        for turn in reversed(turns):
            if role is None or turn.role == role:
                return turn
        return None

    def latest_user_turn(self) -> ConversationTurn | None:
        return self.latest_turn("user")

    def latest_assistant_turn(self) -> ConversationTurn | None:
        return self.latest_turn("assistant")

    def as_text_transcript(self) -> str:
        return "\n".join(f"{turn.role}: {turn.content}" for turn in self._conversation_turns() if turn.content)

    def as_openai_messages(self, *, include_attachments: bool = False) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for turn in self._conversation_turns():
            if include_attachments and turn.role == "user" and turn.attachments:
                content: object = _message_content_with_attachments(turn)
            else:
                content = turn.content
            messages.append({"role": turn.role, "content": content})
        return messages

    def copy_for_run(self) -> "InMemoryStore":
        copied = InMemoryStore(
            workflow_name=self.workflow_name,
            workflow_id=self.workflow_id,
            session_id=self.session_id,
        )
        copied._entries = copy.deepcopy(self._entries)
        return copied

    def search(
        self,
        workflow_name: str,
        *,
        query_text: str = "",
        query_embedding: list[float] | None = None,
        top_k: int = 3,
        similarity_weight: float = 0.5,
        recency_weight: float = 0.3,
        importance_weight: float = 0.2,
    ) -> list[MemorySearchResult]:
        now = time.time()
        terms = _tokenize(query_text) if query_text else set()
        results: list[MemorySearchResult] = []
        for entry in self.all_for_workflow(workflow_name):
            if query_embedding and entry.embedding:
                similarity = _cosine(query_embedding, entry.embedding)
            elif terms:
                similarity = _jaccard(terms, _tokenize(entry.content))
            else:
                similarity = 0.0
            recency = _recency(entry.last_accessed_at, now)
            score = similarity_weight * similarity + recency_weight * recency + importance_weight * entry.importance
            results.append(
                MemorySearchResult(
                    entry=entry,
                    score=score,
                    similarity=similarity,
                    recency=recency,
                    importance=entry.importance,
                )
            )
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]

    def _conversation_turns(self) -> list[ConversationTurn]:
        turns: list[ConversationTurn] = []
        scoped_entries = [
            entry
            for entry in self._entries
            if entry.workflow_name == self.workflow_name
            and (entry.session_id is None or entry.session_id == self.session_id)
            and entry.role in {"system", "user", "assistant", "tool"}
        ]
        scoped_entries.sort(key=lambda entry: (entry.turn_index if entry.turn_index is not None else 10**9, entry.created_at))
        for index, entry in enumerate(scoped_entries):
            turns.append(
                ConversationTurn(
                    role=entry.role or "user",
                    content=entry.content,
                    workflow_name=entry.workflow_name,
                    workflow_id=entry.workflow_id or self.workflow_id,
                    session_id=entry.session_id or self.session_id,
                    turn_index=entry.turn_index if entry.turn_index is not None else index,
                    attachments=copy.deepcopy(entry.attachments),
                    metadata=dict(entry.metadata),
                    turn_id=entry.entry_id,
                    created_at=entry.created_at,
                )
            )
        return turns


def _message_content_with_attachments(turn: ConversationTurn) -> str | list[dict[str, object]]:
    image_parts: list[dict[str, object]] = []
    for attachment in turn.attachments:
        image_url = _attachment_image_url(attachment)
        if image_url is not None:
            image_parts.append({"type": "image_url", "image_url": {"url": image_url}})
    if not image_parts:
        return turn.content
    text_part = [{"type": "text", "text": turn.content}] if turn.content else []
    return [*text_part, *image_parts]


def _attachment_image_url(attachment: Attachment) -> str | None:
    media_type = (attachment.media_type or "").lower()
    if attachment.kind != "image" and not media_type.startswith("image/"):
        return None
    if media_type and media_type not in {"image/png", "image/jpeg", "image/webp"}:
        return None
    content = attachment.content
    if isinstance(content, bytes):
        return None
    text = str(content).strip()
    if text.startswith(("data:image/", "http://", "https://")):
        return text
    return None


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"\W+", text.lower()) if token}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(left * right for left, right in zip(a, b))
    left_norm = math.sqrt(sum(value * value for value in a))
    right_norm = math.sqrt(sum(value * value for value in b))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _recency(last_accessed_at: float, now: float, half_life_sec: float = 86400.0) -> float:
    elapsed = max(0.0, now - last_accessed_at)
    return math.pow(0.5, elapsed / half_life_sec)