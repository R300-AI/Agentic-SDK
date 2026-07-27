from __future__ import annotations

import base64
import copy
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from agentic_sdk.core.entities import Attachment


ConversationRole = Literal["system", "user", "assistant", "tool"]


@runtime_checkable
class MemoryStore(Protocol):
    workflow_name: str
    workflow_id: str
    session_id: str

    @property
    def turns(self) -> list["ConversationTurn"]: ...

    def append_turn(self, turn: "ConversationTurn") -> "ConversationTurn": ...

    def append_message(
        self,
        role: ConversationRole,
        content: str,
        *,
        attachments: list[Attachment] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ConversationTurn": ...

    def latest_turn(self, role: ConversationRole | None = None) -> "ConversationTurn | None": ...

    def latest_user_turn(self) -> "ConversationTurn | None": ...

    def latest_assistant_turn(self) -> "ConversationTurn | None": ...

    def as_text_transcript(self) -> str: ...

    def as_openai_messages(self, *, include_attachments: bool = False) -> list[dict[str, Any]]: ...

    def copy_for_run(self) -> "MemoryStore": ...


@dataclass
class ConversationTurn:
    role: ConversationRole
    content: str
    workflow_name: str = "default"
    workflow_id: str = "default"
    session_id: str = "default"
    turn_index: int = -1
    attachments: list[Attachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)


@dataclass
class InContextMemory:
    workflow_name: str = "default"
    workflow_id: str = "default"
    session_id: str = "default"
    turns: list[ConversationTurn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def append_turn(self, turn: ConversationTurn) -> ConversationTurn:
        stored = copy.deepcopy(turn)
        stored.workflow_name = self.workflow_name
        stored.workflow_id = self.workflow_id
        stored.session_id = self.session_id
        stored.turn_index = len(self.turns)
        self.turns.append(stored)
        return stored

    def append_message(
        self,
        role: ConversationRole,
        content: str,
        *,
        attachments: list[Attachment] | None = None,
        metadata: dict[str, Any] | None = None,
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

    def latest_turn(self, role: ConversationRole | None = None) -> ConversationTurn | None:
        for turn in reversed(self.turns):
            if role is None or turn.role == role:
                return turn
        return None

    def latest_user_turn(self) -> ConversationTurn | None:
        return self.latest_turn("user")

    def latest_assistant_turn(self) -> ConversationTurn | None:
        return self.latest_turn("assistant")

    def as_text_transcript(self) -> str:
        return "\n".join(f"{turn.role}: {turn.content}" for turn in self.turns if turn.content)

    def as_openai_messages(self, *, include_attachments: bool = False) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in self.turns:
            content: str | list[dict[str, Any]]
            if include_attachments and turn.role == "user":
                content = _message_content_with_attachments(turn)
            else:
                content = turn.content
            messages.append({"role": turn.role, "content": content})
        return messages

    def copy_for_run(self) -> "InContextMemory":
        return InContextMemory(
            workflow_name=self.workflow_name,
            workflow_id=self.workflow_id,
            session_id=self.session_id,
            turns=copy.deepcopy(self.turns),
            metadata=copy.deepcopy(self.metadata),
        )


@runtime_checkable
class ConversationStore(Protocol):
    def get(self, session_id: str, *, workflow_name: str = "default") -> MemoryStore | None: ...

    def save(self, conversation: MemoryStore) -> None: ...


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[tuple[str, str], MemoryStore] = {}

    def get(self, session_id: str, *, workflow_name: str = "default") -> MemoryStore | None:
        conversation = self._conversations.get((workflow_name, session_id))
        return conversation.copy_for_run() if conversation is not None else None

    def save(self, conversation: MemoryStore) -> None:
        self._conversations[(conversation.workflow_name, conversation.session_id)] = conversation.copy_for_run()


def build_module_messages(
    conversation: MemoryStore | None,
    *,
    system_prompt: str,
    extra_context: dict[str, Any] | None = None,
    include_attachments: bool = False,
    latest_user_message: str | None = None,
    latest_user_attachments: list[Attachment] | None = None,
) -> list[dict[str, Any]]:
    resolved_prompt = system_prompt
    if extra_context:
        resolved_prompt = f"{system_prompt}\n\nmodule_context:\n{_format_module_context(extra_context)}"
    messages = [{"role": "system", "content": resolved_prompt}]
    if conversation is not None:
        messages.extend(conversation.as_openai_messages(include_attachments=include_attachments))
    elif latest_user_message is not None:
        turn = ConversationTurn(role="user", content=latest_user_message, attachments=list(latest_user_attachments or []))
        messages.append({"role": "user", "content": _message_content_with_attachments(turn) if include_attachments else latest_user_message})
    return messages


def _format_module_context(extra_context: dict[str, Any]) -> str:
    lines = []
    for key, value in extra_context.items():
        if value in (None, "", [], {}, ()):  # omit empty context entries
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _message_content_with_attachments(turn: ConversationTurn) -> str | list[dict[str, Any]]:
    image_parts = [
        {"type": "image_url", "image_url": {"url": image_url}}
        for attachment in turn.attachments
        if (image_url := _attachment_image_url(attachment)) is not None
    ]
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
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{media_type or 'image/png'};base64,{encoded}"
    text = str(content).strip()
    if text.startswith(("data:image/", "http://", "https://")):
        return text
    return None