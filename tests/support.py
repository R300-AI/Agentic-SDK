from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

from agentic_sdk.core import Attachment
from agentic_sdk.llm import OpenAIChatResponse


class FoundryOpenAILikeClient:
    def __init__(
        self,
        *,
        perceive_intent: str = "test_intent",
        perceive_summary: str = "測試用感知摘要。",
        plan_sequence: list[str] | None = None,
        reflect_verdict: str = "pass",
        reflect_reason: str = "test reflect ok",
        action_text: str = "mock action response",
        tool_calls: list[dict] | None = None,
        model_id: str = "foundry-openai-like",
    ) -> None:
        self._perceive_intent = perceive_intent
        self._perceive_summary = perceive_summary
        self._plan_sequence = list(plan_sequence or ["retrieve", "action"])
        self._reflect_verdict = reflect_verdict
        self._reflect_reason = reflect_reason
        self._action_text = action_text
        self._tool_calls = list(tool_calls or [])
        self._plan_index = 0
        self._model_id = model_id
        self.last_create_kwargs: dict | None = None
        self.chat = _FoundryChatNamespace(self)
        self.models = _FoundryModelNamespace(self)

    def _respond(self, *, system: str, user: str) -> OpenAIChatResponse:
        if system.startswith("PERCEIVE"):
            payload = {
                "intent": self._perceive_intent,
                "summary": self._perceive_summary,
            }
        elif system.startswith("PLAN"):
            next_module = self._plan_sequence[min(self._plan_index, len(self._plan_sequence) - 1)]
            self._plan_index += 1
            payload = {
                "thought": f"route to {next_module}",
                "next_module": next_module,
            }
        elif system.startswith("REFLECT"):
            payload = {
                "verdict": self._reflect_verdict,
                "reason": self._reflect_reason,
                "suggestion": "",
            }
        else:
            return OpenAIChatResponse(
                content=self._action_text,
                model=self._model_id,
                input_tokens=max(1, len(user) // 4),
                output_tokens=max(1, len(self._action_text) // 4),
            )

        content = json.dumps(payload, ensure_ascii=False)
        return OpenAIChatResponse(
            content=content,
            model=self._model_id,
            input_tokens=max(1, len(user) // 4),
            output_tokens=max(1, len(content) // 4),
        )


class _FoundryChatNamespace:
    def __init__(self, owner: FoundryOpenAILikeClient) -> None:
        self.completions = _FoundryCompletionsNamespace(owner)


class _FoundryCompletionsNamespace:
    def __init__(self, owner: FoundryOpenAILikeClient) -> None:
        self._owner = owner

    def create(self, **kwargs):
        self._owner.last_create_kwargs = dict(kwargs)
        messages = kwargs.get("messages", [])
        system = next((str(message.get("content", "")) for message in messages if message.get("role") == "system"), "")
        user = next((str(message.get("content", "")) for message in messages if message.get("role") == "user"), "")
        response = self._owner._respond(system=system, user=user)
        model = kwargs.get("model", self._owner._model_id)

        if kwargs.get("stream"):
            chunks = [
                SimpleNamespace(
                    model=model,
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=char))],
                )
                for char in response.content
            ]
            for index, tool_call in enumerate(self._owner._tool_calls):
                function = tool_call.get("function") or {}
                chunks.append(
                    SimpleNamespace(
                        model=model,
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=index,
                                            id=tool_call.get("id"),
                                            type=tool_call.get("type"),
                                            function=SimpleNamespace(
                                                name=function.get("name"),
                                                arguments=function.get("arguments"),
                                            ),
                                        )
                                    ],
                                )
                            )
                        ],
                    )
                )
            return chunks

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response.content, tool_calls=self._owner._tool_calls))],
            usage=SimpleNamespace(
                prompt_tokens=response.input_tokens,
                completion_tokens=response.output_tokens,
            ),
            model=model,
        )


class _FoundryModelNamespace:
    def __init__(self, owner: FoundryOpenAILikeClient) -> None:
        self._owner = owner

    def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=self._owner._model_id)])


class ActionToReflectWrapper:
    name = "action"

    def __init__(self, action_module) -> None:
        self._action_module = action_module

    def __call__(self, state):
        output = dict(self._action_module(state))
        output["next_module"] = "reflect"
        return output


@dataclass
class StaticVisionQueryBuilder:
    rewritten_query: str

    def __call__(self, text: str, attachments: list[Attachment]) -> str:
        return self.rewritten_query if attachments else text