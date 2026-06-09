"""Plan / Reflect 節點呼叫的 Azure Foundry LLM 客戶端。

邊界提醒(對齊 CLAUDE.md):**Foundry 由節點實作直接以 openai SDK 呼叫,不過 Gateway**。
此模組為 Plan / Reflect 共用的薄封裝;Action 節點呼叫 AMD NPU 的部分另走
gateway/upstream_client.py(同樣 openai SDK,但 base_url 不同)。

Mock 策略:
- `MockFoundryClient` 提供 deterministic、scripted 回應,讓 Phase 2 PoC 在無 Azure
  配額/網路時仍可走通五節點工作流
- `get_foundry_client()` 依 Settings 自動選用:當 AZURE_FOUNDRY_API_KEY 為空、
  或 WORKFLOW_FORCE_MOCK_FOUNDRY=true 時回 Mock,否則回 Real

Phase 5 若 Plan/Reflect 採進階演算法且需 streaming,擴 FoundryClient 介面即可。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agentic_sdk.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class FoundryResponse:
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None

    def as_json(self) -> dict:
        """嘗試將 content 解析為 JSON;失敗則回 {}。"""
        try:
            return json.loads(self.content)
        except (json.JSONDecodeError, TypeError):
            return {}


@runtime_checkable
class FoundryClient(Protocol):
    def chat(self, *, system: str, user: str, temperature: float = 0.0) -> FoundryResponse: ...

    @property
    def label(self) -> str: ...


class RealFoundryClient:
    """走 openai SDK → Azure OpenAI / Foundry deployment。"""

    def __init__(self, settings: Settings) -> None:
        from openai import AzureOpenAI

        settings.require_azure_foundry()
        self._settings = settings
        self._deployment = settings.azure_foundry_deployment
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_foundry_endpoint,
            api_key=settings.azure_foundry_api_key,
            api_version=settings.azure_foundry_api_version,
            timeout=settings.infer_request_timeout_sec,
        )

    @property
    def label(self) -> str:
        return f"azure_openai:{self._deployment}"

    def chat(self, *, system: str, user: str, temperature: float = 0.0) -> FoundryResponse:
        completion = self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        choice = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        return FoundryResponse(
            content=choice,
            model=getattr(completion, "model", self._deployment),
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
        )


class MockFoundryClient:
    """Scripted Foundry,讓 PoC 在無 Azure 配額時也能跑全鏈路。

    路由策略(Plan 節點消費):
      visit 1 → next_node="retrieve"(先補上下文)
      visit 2 → next_node="action"(產出回應)
      visit >=3 → next_node="action"(避免無限 Plan↔Retrieve 迴圈)
    Reflect 消費時,scripted 為 "ok",讓 reflect 走 END 路徑。

    輸出固定為 JSON 字串以模擬 response_format=json_object,呼叫端用 as_json() 解析。
    """

    def __init__(self, deployment: str = "mock-foundry") -> None:
        self._deployment = deployment
        self._plan_visit_counter = 0

    @property
    def label(self) -> str:
        return f"mock_foundry:{self._deployment}"

    def chat(self, *, system: str, user: str, temperature: float = 0.0) -> FoundryResponse:
        # 用 system prompt 開頭 keyword 區分 Plan / Reflect
        if system.startswith("PLAN"):
            self._plan_visit_counter += 1
            next_node = "retrieve" if self._plan_visit_counter == 1 else "action"
            payload = {
                "thought": f"mock plan thought visit={self._plan_visit_counter}",
                "next_node": next_node,
            }
        elif system.startswith("REFLECT"):
            # 收到「ERROR」開頭的 user → 視為失敗 → 回 plan;否則 END
            if user.startswith("ERROR"):
                payload = {"verdict": "fail", "next_node": "plan", "reason": "mock retry"}
            else:
                payload = {"verdict": "pass", "next_node": None, "reason": "mock ok"}
        else:
            payload = {"echo": user[:80]}

        content = json.dumps(payload, ensure_ascii=False)
        # 假裝有 token 計數
        return FoundryResponse(
            content=content,
            model=self._deployment,
            input_tokens=len(user) // 4,
            output_tokens=len(content) // 4,
        )


def get_foundry_client(settings: Settings | None = None) -> FoundryClient:
    settings = settings or get_settings()
    if settings.workflow_force_mock_foundry or not settings.azure_foundry_api_key:
        logger.info("Foundry client: MockFoundryClient(reason=key missing or forced)")
        return MockFoundryClient()
    logger.info("Foundry client: RealFoundryClient(deployment=%s)", settings.azure_foundry_deployment)
    return RealFoundryClient(settings)
