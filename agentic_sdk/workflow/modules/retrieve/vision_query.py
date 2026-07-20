"""VisionQueryBuilder — Retrieve 模組的圖像→查詢轉換契約。

設計約束:
- Protocol 不依賴任何 LLM SDK，方便測試替身與第三方實作替換
- 失敗時必須回 fallback（通常為原始 user_message），不阻斷整條 Retrieve
- 預設實作 DefaultVisionQueryBuilder 使用 api_key / base_url / model
    在內部初始化 OpenAI-compatible client，與其他 LLM 模組一致
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from agentic_sdk.workflow.attachments import Attachment
from agentic_sdk.workflow.llm import require_model, resolve_openai_client

logger = logging.getLogger(__name__)


@runtime_checkable
class VisionQueryBuilder(Protocol):
    """把 (文字, 附件) 摘成可拿去檢索的查詢字串。"""

    def __call__(self, text: str, attachments: list[Attachment]) -> str: ...


_VISION_SYSTEM_PROMPT = (
    "你是檢索查詢產生器。請看完使用者輸入與附件圖片，"
    "在 30 字以內以空白分隔輸出 3~6 個可直接拿去檢索的關鍵字（中文為主）。"
    "只輸出關鍵字，不要任何解釋。"
)


class DefaultVisionQueryBuilder:
    """預設實作:呼叫 OpenAI-compatible 圖文模型萃取檢索關鍵字。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_keywords_chars: int = 60,
    ) -> None:
        self._max_chars = max_keywords_chars
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(
            self.__class__.__name__,
            api_key=api_key,
            base_url=base_url,
        )

    def __call__(self, text: str, attachments: list[Attachment]) -> str:
        if not attachments:
            return text

        user_parts: list[dict] = [{"type": "text", "text": text or "（無文字）"}]
        for att in attachments:
            if att.kind == "image":
                user_parts.append({"type": "image_url", "image_url": {"url": att.data_url}})

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _VISION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_parts},
                ],
                temperature=0.0,
            )
            raw = (completion.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("vision query builder failed, fallback to user text: %s", exc)
            return text

        if not raw:
            return text
        return raw[: self._max_chars]
