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
        content = self.content.strip()
        if content.startswith("```"):
            newline = content.find("\n")
            if newline >= 0:
                content = content[newline + 1:]
            if content.rstrip().endswith("```"):
                content = content.rstrip()[:-3]
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


DeltaCallback = Callable[[str], None]
StructuredFieldCallback = Callable[[str, Any], None]


class IncrementalJsonFieldParser:
    """Find configured JSON fields as soon as their values are complete.

    The parser deliberately scans JSON syntax instead of matching JSON with a
    regular expression. Re-scanning the accumulated response keeps the parser
    safe across arbitrary transport chunk boundaries while the emitted-path
    set makes every configured field observable once.
    """

    def __init__(self, fields: tuple[str, ...] | list[str], on_field: StructuredFieldCallback) -> None:
        self._target_paths = {tuple(field.split(".")) for field in fields}
        self._emit_all_fields = "*" in fields
        self._target_paths.discard(("*",))
        self._on_field = on_field
        self._buffer = ""
        self._emitted_paths: set[tuple[str, ...]] = set()
        self._decoder = json.JSONDecoder()

    def feed(self, chunk: str) -> None:
        if not chunk or (not self._emit_all_fields and not self._target_paths):
            return
        self._buffer += chunk
        start = self._buffer.find("{")
        if start < 0:
            return
        self._parse_value(start, ())

    def _parse_value(self, start: int, path: tuple[str, ...]) -> int | None:
        start = self._skip_whitespace(start)
        if start >= len(self._buffer):
            return None
        character = self._buffer[start]
        if character == '"':
            end = self._parse_string(start)
        elif character == "{":
            end = self._parse_object(start, path)
        elif character == "[":
            end = self._parse_array(start, path)
        else:
            end = self._parse_scalar(start)
        if end is not None:
            self._emit_complete_field(path, start, end)
        return end

    def _parse_object(self, start: int, path: tuple[str, ...]) -> int | None:
        cursor = self._skip_whitespace(start + 1)
        if cursor >= len(self._buffer):
            return None
        if self._buffer[cursor] == "}":
            return cursor + 1
        while True:
            key_end = self._parse_string(cursor)
            if key_end is None:
                return None
            try:
                key = json.loads(self._buffer[cursor:key_end])
            except json.JSONDecodeError:
                return None
            if not isinstance(key, str):
                return None
            cursor = self._skip_whitespace(key_end)
            if cursor >= len(self._buffer) or self._buffer[cursor] != ":":
                return None
            value_end = self._parse_value(cursor + 1, path + (key,))
            if value_end is None:
                return None
            cursor = self._skip_whitespace(value_end)
            if cursor >= len(self._buffer):
                return None
            if self._buffer[cursor] == "}":
                return cursor + 1
            if self._buffer[cursor] != ",":
                return None
            cursor = self._skip_whitespace(cursor + 1)
            if cursor >= len(self._buffer):
                return None

    def _parse_array(self, start: int, path: tuple[str, ...]) -> int | None:
        cursor = self._skip_whitespace(start + 1)
        if cursor >= len(self._buffer):
            return None
        if self._buffer[cursor] == "]":
            return cursor + 1
        index = 0
        while True:
            value_end = self._parse_value(cursor, path + (str(index),))
            if value_end is None:
                return None
            index += 1
            cursor = self._skip_whitespace(value_end)
            if cursor >= len(self._buffer):
                return None
            if self._buffer[cursor] == "]":
                return cursor + 1
            if self._buffer[cursor] != ",":
                return None
            cursor = self._skip_whitespace(cursor + 1)
            if cursor >= len(self._buffer):
                return None

    def _parse_string(self, start: int) -> int | None:
        if start >= len(self._buffer) or self._buffer[start] != '"':
            return None
        cursor = start + 1
        while cursor < len(self._buffer):
            character = self._buffer[cursor]
            if character == '"':
                end = cursor + 1
                try:
                    json.loads(self._buffer[start:end])
                except json.JSONDecodeError:
                    return None
                return end
            if character == "\\":
                if cursor + 1 >= len(self._buffer):
                    return None
                escape = self._buffer[cursor + 1]
                if escape == "u":
                    if cursor + 5 >= len(self._buffer):
                        return None
                    cursor += 6
                    continue
                cursor += 2
                continue
            if ord(character) < 0x20:
                return None
            cursor += 1
        return None

    def _parse_scalar(self, start: int) -> int | None:
        try:
            _, end = self._decoder.raw_decode(self._buffer, start)
        except json.JSONDecodeError:
            return None
        end = self._skip_whitespace(end)
        if end >= len(self._buffer):
            return None
        return end if self._buffer[end] in {",", "}", "]"} else None

    def _emit_complete_field(self, path: tuple[str, ...], start: int, end: int) -> None:
        if (
            not path
            or (not self._emit_all_fields and path not in self._target_paths)
            or path in self._emitted_paths
        ):
            return
        try:
            value = json.loads(self._buffer[start:end])
        except json.JSONDecodeError:
            return
        self._emitted_paths.add(path)
        self._on_field(".".join(path), value)

    def _skip_whitespace(self, cursor: int) -> int:
        while cursor < len(self._buffer) and self._buffer[cursor] in " \t\r\n":
            cursor += 1
        return cursor


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
    structured_fields: tuple[str, ...] | list[str] = (),
    on_field: StructuredFieldCallback | None = None,
    idle_timeout_sec: float = 30.0,
) -> OpenAIChatResponse:
    parser = (
        IncrementalJsonFieldParser(structured_fields, on_field)
        if structured_fields and on_field is not None
        else None
    )

    def handle_delta(content: str) -> None:
        if on_delta is not None:
            on_delta(content)
        if parser is not None:
            parser.feed(content)

    return chat_stream(
        client,
        model=model,
        system=system,
        user=user,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
        on_delta=handle_delta,
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