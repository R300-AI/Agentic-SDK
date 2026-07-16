"""TextPerceive 節點：透過 LLM 理解文字輸入意圖。"""

from __future__ import annotations

import json

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.memory import MemoryEntry
from agentic_sdk.workflow.llm import FoundryClient, get_foundry_client
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState


_PERCEIVE_SYSTEM = (
    "PERCEIVE. 你是 Agent 工作流的感知節點，負責理解使用者的輸入意圖。\n"
    "\n"
    "輸入欄位：\n"
    "- user_message：使用者輸入的原始文字（可能是手動輸入、點選選項或語音轉文字）。\n"
    "- available_options：系統提供的可選項目（若有），格式為 JSON 陣列。\n"
    "\n"
    "你的任務：\n"
    "完整閱讀 user_message，理解使用者的真實需求，不論輸入來源為何，都以相同標準分析語意。\n"
    "若 available_options 存在，可作為背景參考（理解系統支援的服務範圍），但不得直接用選項的 intent 欄位覆蓋你的判斷。\n"
    "\n"
    "只回 JSON，欄位：\n"
    "- intent (string)：簡短描述意圖的英文短語，使用底線連接（如 foot_analysis、product_inquiry、general_greeting）。\n"
    "- summary (string)：一句話說明你對此輸入的理解（繁體中文）。"
)


class TextPerceive:
    name = "perceive"

    def __init__(
        self,
        welcome_message: str = "",
        options: list[dict] | None = None,
        importance: float = 1.0,
        foundry_client: FoundryClient | None = None,
    ) -> None:
        self._welcome_message = welcome_message
        self._options = options or []
        self._importance = importance
        self._foundry = foundry_client or get_foundry_client()

    @property
    def welcome_message(self) -> str:
        return self._welcome_message

    @property
    def options(self) -> list[dict]:
        return list(self._options)

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        msg = state.user_message.strip()

        user_prompt = f"user_message: {msg}\n"
        if self._options:
            user_prompt += f"available_options: {json.dumps(self._options, ensure_ascii=False)}\n"

        response = self._foundry.chat(system=_PERCEIVE_SYSTEM, user=user_prompt)
        decision = response.as_json()
        intent = str(decision.get("intent", "general"))
        summary = str(decision.get("summary", msg))

        metadata: dict = {
            "intent": intent,
            "intent_summary": summary,
            "role": "user",
            "msg_len": len(msg),
        }
        if self._welcome_message:
            metadata["welcome_message"] = self._welcome_message
        if self._options:
            metadata["options"] = self._options

        entry = ContextEntry(
            type=ContextEntryType.PERCEIVED,
            content=f"intent={intent} summary={summary}",
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

        return ModuleOutput(
            next_module="plan",
            payload={"perceived_intent": intent},
            context_updates=[entry],
        )