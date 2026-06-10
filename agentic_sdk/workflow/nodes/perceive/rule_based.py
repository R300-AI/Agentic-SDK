"""M6-7 — Perceive 規則式節點 + Chat Panel 注入宣告。

策略(刻意保守,避免 PoC 對 NLP 細節過度承諾):
- 若 user message 開頭為「請」「help」「how」「what」→ intent = "question"
- 含「錯」「error」「fail」→ intent = "diagnose"
- 預設 → intent = "general"

M6-7 擴充:`welcome_message` 與 `options[]` 兩個欄位供 UI Chat Panel 渲染;
本節點不直接渲染對話框,只把宣告寫入 PERCEIVED entry metadata,由 UI 端依此渲染。

M6-1 擴充:`importance` 參數宣告本次 perceive 條目的重要性,若 state.memory_store
存在則寫入 Memory Stream(workflow_name 隔離),供後續 Retrieve 語意撈回。
"""

from __future__ import annotations

import re

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.memory import MemoryEntry
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


_QUESTION_RE = re.compile(r"^(請|怎麼|如何|為什麼|how|what|why|when|where|can\s+i)", re.IGNORECASE)
_DIAGNOSE_RE = re.compile(r"(錯誤|失敗|報錯|exception|error|fail|crash)", re.IGNORECASE)


class RuleBasedPerceive:
    name = "perceive"

    def __init__(
        self,
        welcome_message: str = "",
        options: list[dict] | None = None,
        importance: float = 1.0,
    ) -> None:
        self._welcome_message = welcome_message
        self._options = options or []
        self._importance = importance

    @property
    def welcome_message(self) -> str:
        return self._welcome_message

    @property
    def options(self) -> list[dict]:
        return list(self._options)

    def __call__(self, state: WorkflowState) -> NodeOutput:
        msg = state.user_message.strip()
        intent = self._intent_from_option(msg) or self._intent_from_text(msg)

        metadata: dict = {
            "intent": intent,
            "role": "user",
            "msg_len": len(msg),
        }
        if self._welcome_message:
            metadata["welcome_message"] = self._welcome_message
        if self._options:
            metadata["options"] = self._options

        entry = ContextEntry(
            type=ContextEntryType.PERCEIVED,
            content=f"intent={intent} role=user msg_len={len(msg)}",
            metadata=metadata,
        )

        if state.memory_store is not None:
            state.memory_store.append(
                MemoryEntry(
                    workflow_name=state.workflow_name,
                    entry_type="user_input",
                    content=msg,
                    metadata={"intent": intent, "workflow_id": state.workflow_id},
                    importance=self._importance,
                )
            )

        return NodeOutput(
            next_node="plan",
            payload={"perceived_intent": intent},
            context_updates=[entry],
        )

    def _intent_from_option(self, msg: str) -> str | None:
        for opt in self._options:
            if opt.get("value") == msg or opt.get("label") == msg:
                return str(opt.get("intent") or opt.get("value") or "general")
        return None

    @staticmethod
    def _intent_from_text(msg: str) -> str:
        if _DIAGNOSE_RE.search(msg):
            return "diagnose"
        if _QUESTION_RE.search(msg):
            return "question"
        return "general"

