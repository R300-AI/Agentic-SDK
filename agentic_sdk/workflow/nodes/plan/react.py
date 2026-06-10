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
from agentic_sdk.observability.events import EVENT_NODE_THOUGHT, make_event

import logging
logger = logging.getLogger("agentic_sdk.workflow")


_ALLOWED_NEXT = {"retrieve", "action"}

_REACT_TEMPLATE = (
    "PLAN. 你是 Agent 工作流的規劃節點，記住：retrieve 是「查詢領域知識庫」，不是「隨話規劃」。「可查的內容」詳見下面 retrieve_index，不在清單上的主題一律走 action。\n"
    "\n"
    "retrieve_index：\n{retrieve_index}\n"
    "\n"
    "輸入欄位：user_message、perceived_intent、has_retrieved_context、has_attachment。\n"
    "\n"
    "規則（按優先序判斷，第一個命中就結束）：\n"
    "1. has_retrieved_context=true → 'action'（防迴圈）。\n"
    "2. has_attachment=true 或 perceived_intent=foot_analysis → 'action'（答案來自使用者上傳的圖片）。\n"
    "3. user_message 是「開場白 / 打招呼 / 原則性表態」（如：「我有 XX 想論詢」、「你好」、「幫我一下」）但沒有具體問題→ 'action'（讓 Action 反問、讓使用者補充具體診詢需求，不要預先拿一堆無關資料回來）。\n"
    "4. user_message 明確針對 retrieve_index 列出的主題提出具體問題（推薦某類產品、查尺碼、查庫存、關鍵字能讀到條目）→ 'retrieve'。\n"
    "5. 其餘一律→ 'action'。\n"
    "\n"
    "只回 JSON，欄位：thought (string)、next_node ('retrieve' 或 'action')。「thought」需明確寫出是依幾號規則、以及 user_message 是否命中 retrieve_index 中的哪個主題。"
)

_DEFAULT_RETRIEVE_INDEX = "（未配置知識庫）— 這條規則下任何 user_message 都不應選 'retrieve'。"

SYSTEM_PROMPT_TEMPLATES: dict[str, str] = {
    "react": _REACT_TEMPLATE,
    "cot": (
        "PLAN (Chain-of-Thought). 在決定下一節點前,先在 thought 欄位以條列式逐步推理:"
        "(1) 使用者問什麼、(2) 已有什麼資訊（has_retrieved_context）、(3) 缺什麼。"
        "若 has_retrieved_context=true 必選 'action'；否則依需求選 'retrieve' 或 'action'。"
        "只回 JSON,欄位:thought (string)、next_node (string)。"
    ),
    "plan_and_solve": (
        "PLAN (Plan-and-Solve, Wang 2023). 在 thought 欄位先列出完成本任務的子步驟,"
        "然後判斷:若 has_retrieved_context=true 必選 'action'；"
        "否則第一個子步驟若需要外部資料選 'retrieve'，可直接回應選 'action'。"
        "只回 JSON,欄位:thought (string)、next_node (string)。"
    ),
}


def _format_retrieve_index(name: str | None, description: str | None) -> str:
    name = (name or "").strip()
    description = (description or "").strip()
    if not description and not name:
        return _DEFAULT_RETRIEVE_INDEX
    if name and description:
        return f"- {name}：{description}"
    return f"- {name or description}"


class ReActPlan:
    name = "plan"
    gen_ai_system = "azure_openai"

    def __init__(
        self,
        foundry_client: FoundryClient | None = None,
        system_prompt: str | None = None,
        retrieve_description: str | None = None,
        retrieve_name: str | None = None,
    ) -> None:
        self._foundry = foundry_client or get_foundry_client()
        if system_prompt is not None:
            self._system_prompt = system_prompt
        else:
            index = _format_retrieve_index(retrieve_name, retrieve_description)
            self._system_prompt = _REACT_TEMPLATE.format(retrieve_index=index)

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
            f"has_attachment: {len(state.attachments) > 0}\n"
        )

        response = self._foundry.chat(system=self._system_prompt, user=user_prompt)
        decision = response.as_json()
        thought = str(decision.get("thought", "(no thought)"))
        next_node = decision.get("next_node")
        subtasks_raw = decision.get("subtasks") or []
        subtasks = [str(s) for s in subtasks_raw] if isinstance(subtasks_raw, list) else []

        fallback = False
        if next_node not in _ALLOWED_NEXT:
            next_node = "action"
            fallback = True

        # emit thought 讓前端可以顯示推理軌跡
        logger.info(
            "plan.thought wid=%s next=%s thought=%s",
            state.workflow_id, next_node, thought,
            extra={"event": make_event(
                EVENT_NODE_THOUGHT,
                workflow_id=state.workflow_id,
                workflow_node="plan",
                plan_thought=thought,
                plan_next_node=next_node,
                plan_fallback=fallback,
            )},
        )

        metadata: dict = {
            "thought": thought,
            "next_node": next_node,
            "fallback": fallback,
            "llm": self._foundry.label,
        }
        if subtasks:
            metadata["subtasks"] = subtasks

        entry = ContextEntry(
            type=ContextEntryType.PLAN_DECISION,
            content=f"thought={thought} next={next_node}",
            metadata=metadata,
        )

        return NodeOutput(
            next_node=next_node,
            payload={
                "plan_thought": thought,
                "plan_subtasks": subtasks,
                "_llm_usage": {
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            },
            context_updates=[entry],
        )

