from __future__ import annotations

import json

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import chat_json, require_model, resolve_openai_client
from agentic_sdk.memory import MemoryEntry


_SYSTEM_PROMPT = (
    "PERCEIVE. Understand the user message and return JSON with fields "
    "intent and summary. Use a concise snake_case English intent."
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

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        message = state.user_message.strip()
        user_prompt = f"user_message: {message}\n"
        if self._options:
            user_prompt += f"available_options: {json.dumps(self._options, ensure_ascii=False)}\n"
        response = chat_json(self._client, model=self._model, system=_SYSTEM_PROMPT, user=user_prompt)
        parsed = response.as_json()
        intent = str(parsed.get("intent", "general"))
        summary = str(parsed.get("summary", message))

        metadata = {"intent": intent, "summary": summary, "llm": response.model}
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
            payload={"perceived_intent": intent, "perceived_summary": summary},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.PERCEIVED,
                    content=f"intent={intent} summary={summary}",
                    metadata=metadata,
                )
            ],
        )