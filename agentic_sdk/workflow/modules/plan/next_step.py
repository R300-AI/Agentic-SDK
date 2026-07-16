"""NextStepPlan baseline — 決定下一步要 retrieve 或 action。"""

from __future__ import annotations

import logging

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.observability.events import EVENT_MODULE_DELTA, EVENT_MODULE_THOUGHT, make_event
from agentic_sdk.config import Settings, get_settings
from agentic_sdk.workflow.llm import chat_stream_json, require_client
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState

logger = logging.getLogger("agentic_sdk.workflow")


_ALLOWED_NEXT = {"retrieve", "action"}

_REACT_TEMPLATE = (
    "PLAN. 你是 Agent 工作流的規劃模組，決定下一步要「查詢知識庫（retrieve）」還是「直接產回應（action）」。\n"
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
    "根據推理結果決定 next_module。只回 JSON，欄位：thought (string)、next_module ('retrieve' 或 'action')。"
)

_DEFAULT_RETRIEVE_INDEX = "（未配置知識庫）— 這條規則下任何 user_message 都不應選 'retrieve'。"


def _format_retrieve_index(name: str | None, description: str | None) -> str:
    name = (name or "").strip()
    description = (description or "").strip()
    if not description and not name:
        return _DEFAULT_RETRIEVE_INDEX
    if name and description:
        return f"- {name}：{description}"
    return f"- {name or description}"


class NextStepPlan:
    name = "plan"
    gen_ai_system = "openai_compatible"

    def __init__(
        self,
        settings: Settings | None = None,
        client=None,
        model: str | None = None,
        system_prompt: str | None = None,
        retrieve_description: str | None = None,
        retrieve_name: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = require_client(client, self.__class__.__name__)
        self._model = model or self._settings.openai_model
        if system_prompt is not None:
            self._system_prompt = system_prompt
        else:
            index = _format_retrieve_index(retrieve_name, retrieve_description)
            self._system_prompt = _REACT_TEMPLATE.format(retrieve_index=index)

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        perceived = state.latest_of(ContextEntryType.PERCEIVED)
        retrieved = state.latest_of(ContextEntryType.RETRIEVED)
        intent = perceived.metadata.get("intent") if perceived else "general"

        user_prompt = (
            f"user_message: {state.user_message}\n"
            f"perceived_intent: {intent}\n"
            f"has_retrieved_context: {retrieved is not None}\n"
            f"has_attachment: {len(state.attachments) > 0}\n"
        )

        first_token_emitted = [False]

        def _on_delta(token: str) -> None:
            if not first_token_emitted[0]:
                first_token_emitted[0] = True
                logger.info(
                    "plan.first_token wid=%s",
                    state.workflow_id,
                    extra={"event": make_event(
                        EVENT_MODULE_DELTA,
                        workflow_id=state.workflow_id,
                        workflow_module="plan",
                        delta_index=0,
                        delta_text="",
                    )},
                )

        response = chat_stream_json(
            self._client,
            model=self._model,
            system=self._system_prompt,
            user=user_prompt,
            on_delta=_on_delta,
        )
        decision = response.as_json()
        thought = str(decision.get("thought", "(no thought)"))
        next_module = decision.get("next_module")
        subtasks_raw = decision.get("subtasks") or []
        subtasks = [str(item) for item in subtasks_raw] if isinstance(subtasks_raw, list) else []

        fallback = False
        if next_module not in _ALLOWED_NEXT:
            next_module = "action"
            fallback = True

        logger.info(
            "plan.thought wid=%s next=%s thought=%s",
            state.workflow_id,
            next_module,
            thought,
            extra={"event": make_event(
                EVENT_MODULE_THOUGHT,
                workflow_id=state.workflow_id,
                workflow_module="plan",
                plan_thought=thought,
                plan_next_module=next_module,
                plan_fallback=fallback,
            )},
        )

        metadata: dict = {
            "thought": thought,
            "next_module": next_module,
            "fallback": fallback,
            "llm": response.model,
        }
        if subtasks:
            metadata["subtasks"] = subtasks

        entry = ContextEntry(
            type=ContextEntryType.PLAN_DECISION,
            content=f"thought={thought} next={next_module}",
            metadata=metadata,
        )

        return ModuleOutput(
            next_module=next_module,
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