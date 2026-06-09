"""Perceive baseline — 純規則的 intent/role 抽取,無 LLM 呼叫。

策略(刻意保守,避免 PoC 對 NLP 細節過度承諾):
- 若 user message 開頭為「請」「help」「how」「what」→ intent = "question"
- 含「錯」「error」「fail」→ intent = "diagnose"
- 預設 → intent = "general"
- role 一律標為 "user"(未來 Perceive 可從上下文推 system/agent 角色)

進階 LLM-based perceive 留給 Phase 5,以 `perceive/llm_intent.py` 形式並列。
"""

from __future__ import annotations

import re

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


_QUESTION_RE = re.compile(r"^(請|怎麼|如何|為什麼|how|what|why|when|where|can\s+i)", re.IGNORECASE)
_DIAGNOSE_RE = re.compile(r"(錯誤|失敗|報錯|exception|error|fail|crash)", re.IGNORECASE)


class RuleBasedPerceive:
    name = "perceive"

    def __call__(self, state: WorkflowState) -> NodeOutput:
        msg = state.user_message.strip()
        if _DIAGNOSE_RE.search(msg):
            intent = "diagnose"
        elif _QUESTION_RE.search(msg):
            intent = "question"
        else:
            intent = "general"

        entry = ContextEntry(
            type=ContextEntryType.PERCEIVED,
            content=f"intent={intent} role=user msg_len={len(msg)}",
            metadata={"intent": intent, "role": "user", "msg_len": len(msg)},
        )

        return NodeOutput(
            next_node="plan",
            payload={"perceived_intent": intent},
            context_updates=[entry],
        )
