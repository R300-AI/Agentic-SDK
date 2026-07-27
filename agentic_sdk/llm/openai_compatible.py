from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class OpenAIChatResponse:
    content: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def as_json(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self.content)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


DeltaCallback = Callable[[str], None]


def require_model(model: str | None, module_name: str) -> str:
    resolved = (model or "").strip()
    if not resolved:
        raise ValueError(f"{module_name} requires explicit model.")
    return resolved


def resolve_openai_client(module_name: str, *, api_key: str | None = None, base_url: str | None = None):
    resolved_api_key = (api_key or "").strip()
    resolved_base_url = (base_url or "").strip()
    missing = []
    if not resolved_api_key:
        missing.append("api_key")
    if not resolved_base_url:
        missing.append("base_url")
    if missing:
        raise ValueError(f"{module_name} requires explicit {'/'.join(missing)}.")
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(
            "OpenAI SDK import failed. Reinstall the 'openai' package in the current environment."
        ) from exc
    return OpenAI(api_key=resolved_api_key, base_url=resolved_base_url)


def chat_json(
    client,
    *,
    model: str,
    system: str,
    user: str,
    temperature: float | None = None,
) -> OpenAIChatResponse:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    completion = client.chat.completions.create(**kwargs)
    usage = getattr(completion, "usage", None)
    return OpenAIChatResponse(
        content=completion.choices[0].message.content or "",
        model=getattr(completion, "model", model),
        input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
    )


def chat_stream_json(
    client,
    *,
    model: str,
    system: str,
    user: str,
    temperature: float | None = None,
    on_delta: DeltaCallback | None = None,
    idle_timeout_sec: float = 30.0,
) -> OpenAIChatResponse:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "response_format": {"type": "json_object"},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    stream = client.chat.completions.create(**kwargs)
    chunks: list[str] = []
    resolved_model = model
    last_token_at = time.monotonic()
    for chunk in stream:
        resolved_model = getattr(chunk, "model", None) or resolved_model
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0].delta, "content", None)
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
    return OpenAIChatResponse(content="".join(chunks), model=resolved_model)