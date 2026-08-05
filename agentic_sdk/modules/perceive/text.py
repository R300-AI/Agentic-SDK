from __future__ import annotations

import json
from typing import Any

from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, ModuleOutput, WorkflowAborted, WorkflowState
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client
from agentic_sdk.memory import MemoryEntry
from agentic_sdk.memory.in_context import build_module_messages


_SYSTEM_PROMPT = (
    "PERCEIVE. Understand the user message and return JSON with fields "
    "intent, summary, and details. Use a concise snake_case English intent. "
    "When fields_to_notice is provided, use those names in details when possible. "
    "For image-derived measurements, only report a value as a named fact when both its label "
    "and value are legible. Never infer a label from a value's position or surrounding layout; "
    "record it as uncertain when either is unclear. Never treat an unmarked comparison chart, "
    "legend, or example category as the user's selected classification. A category name appearing "
    "beside a foot illustration is only an example, even when its text is legible. Report a left or "
    "right foot classification only when the image explicitly identifies that user's foot side and "
    "shows a selected result or result field; otherwise state that the classification is uncertain."
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
        message = state.latest_user_message().strip()
        user_prompt = f"user_message: {message}\n"
        if self._welcome_message:
            user_prompt += f"guidance: {self._welcome_message}\n"
        if self._options:
            user_prompt += f"fields_to_notice: {json.dumps(self._options, ensure_ascii=False)}\n"
        return user_prompt

    def _user_content(self, state: WorkflowState) -> str | list[dict[str, Any]]:
        return self._user_prompt(state)

    def _messages(self, state: WorkflowState) -> list[dict[str, Any]]:
        return build_module_messages(
            state.memory,
            system_prompt=_SYSTEM_PROMPT,
            extra_context={
                "guidance": self._welcome_message,
                "fields_to_notice": json.dumps(self._options, ensure_ascii=False) if self._options else "",
            },
            latest_user_message=self._user_prompt(state),
        )

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        message = state.latest_user_message().strip()
        try:
            response = chat_stream_json(
                self._client,
                model=self._model,
                messages=self._messages(state),
                on_delta=lambda content: state.emit_token_delta(
                    self.name,
                    content,
                    metadata={"model": self._model, "structured": True},
                ),
                structured_fields=state.structured_fields_for(self.name),
                on_field=lambda field, value: state.emit_structured_field(
                    self.name,
                    field,
                    value,
                    metadata={"model": self._model, "structured": True},
                ),
            )
        except Exception as exc:
            _abort_for_provider_failure(state, self.name, exc)
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
        persistent_memory = state.persistent_memory()
        if persistent_memory is not None:
            persistent_memory.append(
                MemoryEntry(
                    workflow_name=state.workflow_name,
                    entry_type="user_input",
                    content=message,
                    role="user",
                    workflow_id=state.workflow_id,
                    session_id=state.session_id,
                    attachments=list(state.attachments),
                    turn_index=state.memory.latest_user_turn().turn_index if state.memory else None,
                    metadata={"intent": intent, "workflow_id": state.workflow_id, "session_id": state.session_id},
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
        importance: float = 1.5,
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
            if attachment.kind == "image" or (attachment.media_type or "").lower().startswith("image/")
        ]
        if image_summaries:
            user_prompt += f"input_images: {json.dumps(image_summaries, ensure_ascii=False)}\n"
        return user_prompt

    def _user_content(self, state: WorkflowState) -> str | list[dict[str, Any]]:
        return self._user_prompt(state)

    def _messages(self, state: WorkflowState) -> list[dict[str, Any]]:
        return build_module_messages(
            state.memory,
            system_prompt=_SYSTEM_PROMPT,
            extra_context={
                "guidance": self._welcome_message,
                "fields_to_notice": json.dumps(self._options, ensure_ascii=False) if self._options else "",
                "image_instruction": self._image_instruction,
                "input_images": json.dumps(
                    [
                        {"name": attachment.name or "image", "media_type": attachment.media_type or "image/*"}
                        for attachment in state.attachments
                    ],
                    ensure_ascii=False,
                )
                if state.attachments
                else "",
            },
            include_attachments=True,
            latest_user_message=self._user_prompt(state),
            latest_user_attachments=state.attachments,
        )


def _abort_for_provider_failure(state: WorkflowState, stage: str, exc: Exception) -> None:
    message = "Unable to understand the input right now."
    state.last_workflow_error = {"stage": stage, "message": message}
    state.append(
        ContextEntry(
            type=ContextEntryType.PERCEIVED,
            content=f"error:{type(exc).__name__}",
            metadata={"ok": False, "stage": stage, "error_type": type(exc).__name__},
        )
    )
    raise WorkflowAborted(message) from exc