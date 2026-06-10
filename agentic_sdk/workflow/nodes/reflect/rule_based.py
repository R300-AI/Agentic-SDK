"""Reflect rule-based baseline — 對應 D4「LLM-based reflect 失敗時的 fallback」。

PoC 階段不啟用 Reflexion LLM(R12);先以最便宜的規則判斷:
- state.last_action_error 不為 None → 視為失敗 → next_node 依 on_failure 設定
  ("retry_plan" → "plan",最多一次重試由 Gates.max_revisit 控制;"end" → None)
- 否則 → END

Phase 5 啟用 reflexion.py(Shinn 2023)後,此檔保留為 fallback,Reflect 子套件
__init__.py 改為:
    DEFAULT = lambda: ReflexionReflect(fallback=RuleBasedReflect())
"""

from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


_ON_FAILURE_TO_NEXT: dict[str, str | None] = {
    "retry_plan": "plan",
    "end": None,
}


class RuleBasedReflect:
    name = "reflect"

    def __init__(self, on_failure: str = "retry_plan") -> None:
        if on_failure not in _ON_FAILURE_TO_NEXT:
            raise ValueError(
                f"RuleBasedReflect.on_failure={on_failure!r} 不合法,"
                f"僅接受 {sorted(_ON_FAILURE_TO_NEXT)}。"
            )
        self._on_failure = on_failure

    def __call__(self, state: WorkflowState) -> NodeOutput:
        err = state.last_action_error
        if err:
            verdict = "fail"
            next_node = _ON_FAILURE_TO_NEXT[self._on_failure]
            reason = err.get("message", "(unknown action error)")
        else:
            verdict = "pass"
            next_node = None
            reason = "action_result ok"

        entry = ContextEntry(
            type=ContextEntryType.REFLECTION,
            content=f"verdict={verdict} reason={reason}",
            metadata={
                "verdict": verdict,
                "reason": reason,
                "strategy": "rule_based",
                "on_failure": self._on_failure,
            },
        )

        return NodeOutput(
            next_node=next_node,
            payload={"reflect_verdict": verdict},
            context_updates=[entry],
        )

