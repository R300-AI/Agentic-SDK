from __future__ import annotations

from collections.abc import Mapping
from typing import Any


WORKFLOW_MODULE_NAMES = frozenset({"perceive", "plan", "retrieve", "action", "reflect"})
ALL_STRUCTURED_FIELDS = "*"
DEFAULT_EVENTS_SCHEMA = {
    "perceive": {
        "label": "理解輸入",
        "fields": [ALL_STRUCTURED_FIELDS],
    },
    "plan": {
        "label": "判斷工具順序",
        "fields": [ALL_STRUCTURED_FIELDS],
    },
    "retrieve": {
        "label": "整理相關來源",
        "fields": [],
    },
    "action": {
        "label": "準備輸出回覆",
        "fields": [],
    },
    "reflect": {
        "label": "檢查回覆",
        "fields": [ALL_STRUCTURED_FIELDS],
    },
}


def default_events_schema() -> dict[str, dict[str, Any]]:
    """Return a mutable copy of the SDK's full event schema."""
    return normalize_events_schema(DEFAULT_EVENTS_SCHEMA)


def default_event_label(module: str) -> str | None:
    schema = DEFAULT_EVENTS_SCHEMA.get(module)
    return str(schema["label"]) if schema is not None else None


def resolve_events_schema(
    events_schema: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Resolve omitted configuration to the SDK full-event default.

    An explicitly supplied schema, including an empty mapping, remains an
    explicit observation boundary.
    """
    if events_schema is None:
        return default_events_schema()
    return normalize_events_schema(events_schema)


def normalize_events_schema(
    events_schema: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Validate and normalize canonical workflow event configuration.
    """
    normalized: dict[str, dict[str, Any]] = {}
    if events_schema is not None:
        if not isinstance(events_schema, Mapping):
            raise TypeError("events_schema must be a mapping of workflow module names to schema objects.")
        for module, raw_schema in events_schema.items():
            _validate_module_name(module, source="events_schema")
            if not isinstance(raw_schema, Mapping):
                raise TypeError(f"events_schema[{module!r}] must be a mapping.")
            label = raw_schema.get("label")
            if not isinstance(label, str):
                raise TypeError(f"events_schema[{module!r}]['label'] must be a string.")
            if not label.strip():
                raise ValueError(f"events_schema[{module!r}]['label'] must not be blank.")
            fields = raw_schema.get("fields", [])
            if not isinstance(fields, (list, tuple)):
                raise TypeError(f"events_schema[{module!r}]['fields'] must be a list of dot paths.")
            normalized_fields = [_validate_field_path(module, field) for field in fields]
            if len(set(normalized_fields)) != len(normalized_fields):
                raise ValueError(f"events_schema[{module!r}]['fields'] must not contain duplicates.")
            metadata = raw_schema.get("metadata", {})
            if not isinstance(metadata, Mapping):
                raise TypeError(f"events_schema[{module!r}]['metadata'] must be a mapping.")
            normalized[module] = {
                "label": label,
                "fields": normalized_fields,
                "metadata": dict(metadata),
            }

    return normalized


def _validate_module_name(module: object, *, source: str) -> None:
    if not isinstance(module, str) or module not in WORKFLOW_MODULE_NAMES:
        supported = ", ".join(sorted(WORKFLOW_MODULE_NAMES))
        raise ValueError(f"{source} module key {module!r} is invalid; supported module keys: {supported}.")


def _validate_field_path(module: str, field: object) -> str:
    if not isinstance(field, str):
        raise TypeError(f"events_schema[{module!r}]['fields'] entries must be strings.")
    path = field.strip()
    if path == ALL_STRUCTURED_FIELDS:
        return path
    parts = path.split(".")
    if not path or any(not part or not part.isidentifier() for part in parts):
        raise ValueError(
            f"events_schema[{module!r}] field {field!r} must be a dot path with identifier segments."
        )
    return path
