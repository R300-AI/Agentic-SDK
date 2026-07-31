from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - handled when a client is resolved.
    OpenAI = None  # type: ignore[assignment]


@dataclass
class OpenAIChatResponse:
    content: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: list[dict[str, Any]] | None = None

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
    if OpenAI is None:
        raise RuntimeError(
            "OpenAI SDK import failed. Reinstall the 'openai' package in the current environment."
        )
    return OpenAI(api_key=resolved_api_key, base_url=resolved_base_url)


def chat_json(
    client,
    *,
    model: str,
    system: str | None = None,
    user: str | list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
) -> OpenAIChatResponse:
    resolved_messages = messages or [
        {"role": "system", "content": system or ""},
        {"role": "user", "content": user or ""},
    ]
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": resolved_messages,
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
    system: str | None = None,
    user: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    on_delta: DeltaCallback | None = None,
    idle_timeout_sec: float = 30.0,
) -> OpenAIChatResponse:
    return chat_stream(
        client,
        model=model,
        system=system,
        user=user,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
        on_delta=on_delta,
        idle_timeout_sec=idle_timeout_sec,
    )


def chat_stream(
    client,
    *,
    model: str,
    system: str | None = None,
    user: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    response_format: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
    idle_timeout_sec: float = 30.0,
) -> OpenAIChatResponse:
    resolved_messages = messages or [
        {"role": "system", "content": system or ""},
        {"role": "user", "content": user or ""},
    ]
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": resolved_messages,
        "stream": True,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
    stream = client.chat.completions.create(**kwargs)
    chunks: list[str] = []
    resolved_model = model
    last_token_at = time.monotonic()
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: dict[int, dict[str, Any]] = {}
    try:
        for chunk in stream:
            resolved_model = _value(chunk, "model") or resolved_model
            usage = _value(chunk, "usage")
            if usage is not None:
                input_tokens = _value(usage, "prompt_tokens") or input_tokens
                output_tokens = _value(usage, "completion_tokens") or output_tokens
            choices = _value(chunk, "choices") or []
            if not choices:
                continue
            delta = _value(choices[0], "delta")
            content = _value(delta, "content")
            has_tool_delta = _accumulate_tool_call_deltas(tool_calls, _value(delta, "tool_calls"))
            if not content and not has_tool_delta:
                continue
            now = time.monotonic()
            idle_gap = now - last_token_at
            if idle_gap > idle_timeout_sec:
                raise TimeoutError(f"openai stream idle {idle_gap:.1f}s > {idle_timeout_sec}s")
            last_token_at = now
            if not content:
                continue
            text = str(content)
            if not text:
                continue
            chunks.append(text)
            if on_delta is not None:
                on_delta(text)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    return OpenAIChatResponse(
        content="".join(chunks),
        model=resolved_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=[tool_calls[index] for index in sorted(tool_calls)],
    )


def _accumulate_tool_call_deltas(
    accumulated: dict[int, dict[str, Any]],
    raw_tool_calls: object,
) -> bool:
    if not raw_tool_calls:
        return False
    calls = [raw_tool_calls] if isinstance(raw_tool_calls, dict) else raw_tool_calls
    for position, raw_call in enumerate(calls):
        raw_index = _value(raw_call, "index")
        index = int(raw_index) if isinstance(raw_index, int) or str(raw_index).isdigit() else position
        call = accumulated.setdefault(
            index,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        identifier = _value(raw_call, "id")
        if identifier:
            call["id"] = str(identifier)
        call_type = _value(raw_call, "type")
        if call_type:
            call["type"] = str(call_type)
        function = _value(raw_call, "function")
        function_name = _value(function, "name")
        if function_name:
            call["function"]["name"] = str(function_name)
        arguments = _value(function, "arguments")
        if arguments:
            call["function"]["arguments"] += str(arguments)
    return True


def _value(source: object, key: str) -> object:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)