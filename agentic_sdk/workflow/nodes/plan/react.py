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
from agentic_sdk.observability.events import EVENT_NODE_DELTA, EVENT_NODE_THOUGHT, make_event

import logging
logger = logging.getLogger("agentic_sdk.workflow")


_ALLOWED_NEXT = {"retrieve", "action"}

_REACT_TEMPLATE = (
    "PLAN. 你是 Agent 工作流的規劃節點，決定下一步要「查詢知識庫（retrieve）」還是「直接產回應（action）」。\n"
    "\n"
    "可查詢的知識庫：\n{retrieve_index}\n"
    "\n"
    "你拿到的完整上下文：\n"
    "- user_message：使用者的原始輸入。\n"
    "- perceived_intent：感知節點對使用者意圖的理解。\n"
    "- has_retrieved_context：若為 true，表示本輪已有知識庫查詢結果。\n"
    "- has_attachment：若為 true，表示使用者有附上檔案或圖片。\n"
    "\n"
    "請在 thought 欄位寫下你的完整推理：\n"
    "- 使用者真正想問或需要什麼？\n"
    "- 這個需求能從上述知識庫中找到答案嗎？請對照 retrieve_index 的內容具體說明。\n"
    "- has_retrieved_context、has_attachment 的狀態對此決策有何影響？\n"
    "\n"
    "根據推理結果決定 next_node。只回 JSON，欄位：thought (string)、next_node ('retrieve' 或 'action')。"
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

        # 用串流模式呼叫 LLM，在第一個 token 抵達時 emit EVENT_NODE_DELTA(delta_index=0)，
        # 讓前端與測試可以量測三個時間點：
        #   T1 plan.start（黃燈）→ T2 delta_index=0（LLM 第一字）→ T3 plan.finish（綠燈）
        _first_token_emitted: list[bool] = [False]

        def _on_delta(token: str) -> None:
            if not _first_token_emitted[0]:
                _first_token_emitted[0] = True
                logger.info(
                    "plan.first_token wid=%s",
                    state.workflow_id,
                    extra={"event": make_event(
                        EVENT_NODE_DELTA,
                        workflow_id=state.workflow_id,
                        workflow_node="plan",
                        delta_index=0,
                        delta_text="",  # 不洩漏推理原文，僅作為時間戳記錨點
                    )},
                )

        response = self._foundry.chat_stream(
            system=self._system_prompt,
            user=user_prompt,
            on_delta=_on_delta,
            response_format={"type": "json_object"},
        )
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

