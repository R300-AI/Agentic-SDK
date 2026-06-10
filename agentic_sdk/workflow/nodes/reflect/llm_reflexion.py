"""M6-6 — Reflexion 風格的 LLM 反思節點。

對齊 Shinn 2023(Reflexion);PoC 形態:
- 不重跑整個工作流,只在 Action 失敗或結果可疑時用 LLM 評估,提供反思訊息
- 沒有 LLM client 時自動退回 RuleBasedReflect 的判斷
- on_failure 決定當判定為 fail 時的 next_node(retry_plan / end)
"""

from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.llm import FoundryClient, get_foundry_client
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


_ON_FAILURE_TO_NEXT: dict[str, str | None] = {
    "retry_plan": "plan",
    "end": None,
}

_SYSTEM_PROMPT = (
    "REFLECT (Reflexion). 你是工作流的反思節點。檢視 user_message、plan_thought、"
    "action_result 與 action_error(若有),判斷此次 Action 是否回應到使用者真正的問題。"
    "只回 JSON,欄位:verdict ('pass'|'fail')、reason (string)、suggestion (string,失敗時的改進建議)。"
)


class ReflexionReflect:
    name = "reflect"
    gen_ai_system = "azure_openai"

    def __init__(
        self,
        on_failure: str = "retry_plan",
        foundry_client: FoundryClient | None = None,
    ) -> None:
        if on_failure not in _ON_FAILURE_TO_NEXT:
            raise ValueError(
                f"ReflexionReflect.on_failure={on_failure!r} 不合法,"
                f"僅接受 {sorted(_ON_FAILURE_TO_NEXT)}。"
            )
        self._on_failure = on_failure
        self._foundry = foundry_client or get_foundry_client()

    @property
    def gen_ai_request_model(self) -> str:
        return self._foundry.label

    def __call__(self, state: WorkflowState) -> NodeOutput:
        err = state.last_action_error
        action_result = state.last_action_result or {}

        user_prompt = (
            f"user_message: {state.user_message}\n"
            f"action_result: {action_result.get('content', '')[:500]}\n"
            f"action_error: {err.get('message') if err else 'none'}\n"
        )

        try:
            response = self._foundry.chat(system=_SYSTEM_PROMPT, user=user_prompt)
            decision = response.as_json()
            verdict = str(decision.get("verdict", "fail" if err else "pass"))
            reason = str(decision.get("reason", "(no reason)"))
            suggestion = str(decision.get("suggestion", ""))
            llm_usage = {
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        except Exception as exc:  # noqa: BLE001 — LLM 任何失敗都退回規則式
            verdict = "fail" if err else "pass"
            reason = f"(llm reflexion unavailable, fallback to rule: {exc})"
            suggestion = ""
            llm_usage = None

        if verdict not in ("pass", "fail"):
            verdict = "fail" if err else "pass"

        if verdict == "fail":
            next_node = _ON_FAILURE_TO_NEXT[self._on_failure]
        else:
            next_node = None

        metadata: dict = {
            "verdict": verdict,
            "reason": reason,
            "strategy": "reflexion",
            "on_failure": self._on_failure,
        }
        if suggestion:
            metadata["suggestion"] = suggestion
        if llm_usage:
            metadata["llm"] = self._foundry.label

        entry = ContextEntry(
            type=ContextEntryType.REFLECTION,
            content=f"verdict={verdict} reason={reason}",
            metadata=metadata,
        )

        payload: dict = {"reflect_verdict": verdict}
        if llm_usage:
            payload["_llm_usage"] = llm_usage

        return NodeOutput(
            next_node=next_node,
            payload=payload,
            context_updates=[entry],
        )
