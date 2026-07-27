from __future__ import annotations

import base64
import json
from typing import Any

from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import chat_json, require_model, resolve_openai_client
from agentic_sdk.memory import MemoryEntry


_SYSTEM_PROMPT = (
    "PERCEIVE. Understand the user message and return JSON with fields "
    "intent, summary, and details. Use a concise snake_case English intent. "
    "When fields_to_notice is provided, use those names in details when possible."
)


class TextPerceive:
    name = "perceive"
    gen_ai_system = "openai_compatible"

    def __init__(
        self,
        welcome_message: str = "",
        options: list[dict] | None = None,
        importance: float = 1.0,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._welcome_message = welcome_message
        self._options = options or []
        self._importance = importance
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def _user_prompt(self, state: WorkflowState) -> str:
        message = state.user_message.strip()
        user_prompt = f"user_message: {message}\n"
        if self._welcome_message:
            user_prompt += f"guidance: {self._welcome_message}\n"
        if self._options:
            user_prompt += f"fields_to_notice: {json.dumps(self._options, ensure_ascii=False)}\n"
        return user_prompt

    def _user_content(self, state: WorkflowState) -> str | list[dict[str, Any]]:
        return self._user_prompt(state)

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        message = state.user_message.strip()
        response = chat_json(self._client, model=self._model, system=_SYSTEM_PROMPT, user=self._user_content(state))
        parsed = response.as_json()
        intent = str(parsed.get("intent", "general"))
        summary = str(parsed.get("summary", message))
        details = parsed.get("details")
        if not isinstance(details, dict):
            details = {}

        metadata = {"intent": intent, "summary": summary, "llm": response.model}
        if details:
            metadata["details"] = details
        if self._welcome_message:
            metadata["welcome_message"] = self._welcome_message
        if self._options:
            metadata["options"] = self._options
        if state.memory_store is not None:
            state.memory_store.append(
                MemoryEntry(
                    workflow_name=state.workflow_name,
                    entry_type="user_input",
                    content=message,
                    metadata={"intent": intent, "workflow_id": state.workflow_id},
                    importance=self._importance,
                )
            )

        return ModuleOutput(
            next_module="plan",
            payload={"perceived_intent": intent, "perceived_summary": summary, "perceived_details": details},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.PERCEIVED,
                    content=f"intent={intent} summary={summary}",
                    metadata=metadata,
                )
            ],
        )


class TextImagePerceive(TextPerceive):
    def __init__(
        self,
        welcome_message: str = "",
        options: list[dict] | None = None,
        importance: float = 1.0,
        *,
        image_instruction: str = "",
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(welcome_message, options, importance, api_key=api_key, base_url=base_url, model=model)
        self._image_instruction = image_instruction.strip()

    def _user_prompt(self, state: WorkflowState) -> str:
        user_prompt = super()._user_prompt(state)
        if self._image_instruction:
            user_prompt += f"image_instruction: {self._image_instruction}\n"
        image_summaries = [
            {"name": attachment.name or "image", "media_type": attachment.media_type or "image/*"}
            for attachment in state.attachments
            if _attachment_image_url(attachment) is not None
        ]
        if image_summaries:
            user_prompt += f"input_images: {json.dumps(image_summaries, ensure_ascii=False)}\n"
        return user_prompt

    def _user_content(self, state: WorkflowState) -> str | list[dict[str, Any]]:
        image_parts = [
            {"type": "image_url", "image_url": {"url": image_url}}
            for attachment in state.attachments
            if (image_url := _attachment_image_url(attachment)) is not None
        ]
        if not image_parts:
            return self._user_prompt(state)
        return [{"type": "text", "text": self._user_prompt(state)}, *image_parts]


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