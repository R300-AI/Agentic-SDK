"""A-01 — ContextEntry 資料結構。

對齊 docs/03-agentic-orchestration/context-and-memory.md 的契約:每條目可被
獨立引用、可降級、可丟棄。Phase 2 僅在 Workflow 內存形式存活;A-04 將提供
ActiveStore 抽象與 HTTP /internal/context/{id} 端點。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class ContextEntryType(str, Enum):
    """條目語意分類,供 Reflect / Retrieve 等節點選擇性消費。"""

    USER_INPUT = "user_input"
    PERCEIVED = "perceived"           # Perceive 節點抽出的結構化表示
    PLAN_DECISION = "plan_decision"   # Plan 節點的 Thought + 路由決策
    RETRIEVED = "retrieved"           # Retrieve 節點取回的外部知識片段
    ACTION_RESULT = "action_result"   # Action 節點的執行結果
    REFLECTION = "reflection"         # Reflect 節點的審查結論


@dataclass
class ContextEntry:
    """單一上下文條目;eviction_priority 預設為 1(可降級)。"""

    type: ContextEntryType
    content: str
    metadata: dict = field(default_factory=dict)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    eviction_priority: int = 1

    def touch(self) -> None:
        self.last_accessed_at = time.time()
