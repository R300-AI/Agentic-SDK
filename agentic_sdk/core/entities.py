from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContextEntryType(str, Enum):
    USER_INPUT = "user_input"
    PERCEIVED = "perceived"
    PLAN_DECISION = "plan_decision"
    RETRIEVED = "retrieved"
    ACTION_RESULT = "action_result"
    REFLECTION = "reflection"


@dataclass
class ContextEntry:
    type: ContextEntryType | str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_accessed_at = time.time()


@dataclass
class Attachment:
    kind: str
    content: bytes | str
    media_type: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Entities:
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def update(self, values: dict[str, Any] | None) -> None:
        if values:
            self.values.update(values)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)