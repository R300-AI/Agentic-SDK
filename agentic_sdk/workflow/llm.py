"""Workflow 模組共用的 LLM response helper。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class OpenAIChatResponse:
    content: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def as_json(self) -> dict:
        """嘗試將 content 解析為 JSON;失敗則回 {}。"""
        try:
            return json.loads(self.content)
        except (json.JSONDecodeError, TypeError):
            return {}


DeltaCallback = Callable[[str], None]


def require_client(client, module_name: str):
    if client is None:
        raise ValueError(
            f"{module_name} requires a user-injected OpenAI client via client=OpenAI(...)."
        )
    return client


def chat_json(
    client,
    *,
    model: str | None = None,
    system: str,
    user: str,
    temperature: float | None = None,
) -> OpenAIChatResponse:
    kwargs: dict = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if model:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    completion = client.chat.completions.create(**kwargs)
    content = completion.choices[0].message.content or ""
    usage = getattr(completion, "usage", None)
    return OpenAIChatResponse(
        content=content,
        model=getattr(completion, "model", model),
        input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
    )


def chat_stream_json(
    client,
    *,
    model: str | None = None,
    system: str,
    user: str,
    temperature: float | None = None,
    on_delta: DeltaCallback | None = None,
    idle_timeout_sec: float = 30.0,
) -> OpenAIChatResponse:
    kwargs: dict = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "response_format": {"type": "json_object"},
    }
    if model:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    stream = client.chat.completions.create(**kwargs)
    chunks: list[str] = []
    resolved_model = model
    last_token_at = time.monotonic()
    for chunk in stream:
        if getattr(chunk, "model", None):
            resolved_model = chunk.model
        if not getattr(chunk, "choices", None):
            continue
        delta = getattr(chunk.choices[0].delta, "content", None)
        if not delta:
            continue
        now = time.monotonic()
        idle_gap = now - last_token_at
        if idle_gap > idle_timeout_sec:
            raise TimeoutError(f"openai stream idle {idle_gap:.1f}s > {idle_timeout_sec}s")
        last_token_at = now
        chunks.append(delta)
        if on_delta is not None:
            on_delta(delta)
    content = "".join(chunks)
    return OpenAIChatResponse(content=content, model=resolved_model)
