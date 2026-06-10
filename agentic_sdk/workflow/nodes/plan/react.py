"""Plan baseline — ReAct(Yao 2022, R09)的 PoC 形態。

PoC 簡化:不做多輪 Thought→Action 迴圈,只用一次 LLM 呼叫產 JSON
{"thought": "...", "next_node": "retrieve"|"action"}。next_node 不在白名單時
退回 "action" 並標記 fallback,避免無效路由。

LLM 來源:`get_foundry_client()`,正式金鑰未配置時自動拾 MockFoundryClient
(scripted),確保 PoC 在無 Azure 配額時也能跑通。
"""

from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.llm import FoundryClient, get_foundry_client
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


_ALLOWED_NEXT = {"retrieve", "action"}

SYSTEM_PROMPT_TEMPLATES: dict[str, str] = {
    "react": (
        "PLAN. 你是 Agent 工作流的規劃節點。閱讀 user message 與 perceived intent 後,"
        "決定下一個節點為 'retrieve'(需要外部知識)或 'action'(可直接產出回應)。"
        "只回 JSON,欄位:thought (string)、next_node (string)。"
    ),
    "cot": (
        "PLAN (Chain-of-Thought). 在決定下一節點前,先在 thought 欄位以條列式逐步推理:"
        "(1) 使用者問什麼、(2) 已有什麼資訊、(3) 缺什麼。再選 'retrieve' 或 'action'。"
        "只回 JSON,欄位:thought (string)、next_node (string)。"
    ),
    "plan_and_solve": (
        "PLAN (Plan-and-Solve, Wang 2023). 在 thought 欄位先列出完成本任務的子步驟,"
        "然後判斷第一個子步驟是需要 'retrieve' 還是可直接 'action'。"
        "只回 JSON,欄位:thought (string)、next_node (string)。"
    ),
}


class ReActPlan:
    name = "plan"
    gen_ai_system = "azure_openai"

    def __init__(
        self,
        foundry_client: FoundryClient | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._foundry = foundry_client or get_foundry_client()
        self._system_prompt = system_prompt or SYSTEM_PROMPT_TEMPLATES["react"]

    @property
    def gen_ai_request_model(self) -> str:
        return self._foundry.label

    def __call__(self, state: WorkflowState) -> NodeOutput:
        perceived = state.latest_of(ContextEntryType.PERCEIVED)
        retrieved = state.latest_of(ContextEntryType.RETRIEVED)
        intent = perceived.metadata.get("intent") if perceived else "general"

        user_prompt = (
            f"user_message: {state.user_message}\n"
            f"perceived_intent: {intent}\n"
            f"has_retrieved_context: {retrieved is not None}\n"
        )

        response = self._foundry.chat(system=self._system_prompt, user=user_prompt)
        decision = response.as_json()
        thought = str(decision.get("thought", "(no thought)"))
        next_node = decision.get("next_node")

        fallback = False
        if next_node not in _ALLOWED_NEXT:
            next_node = "action"
            fallback = True

        entry = ContextEntry(
            type=ContextEntryType.PLAN_DECISION,
            content=f"thought={thought} next={next_node}",
            metadata={
                "thought": thought,
                "next_node": next_node,
                "fallback": fallback,
                "llm": self._foundry.label,
            },
        )

        return NodeOutput(
            next_node=next_node,
            payload={
                "plan_thought": thought,
                "_llm_usage": {
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            },
            context_updates=[entry],
        )

