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
import time
from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

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


DeltaCallback = Callable[[str], None]


@runtime_checkable
class FoundryClient(Protocol):
    def chat(self, *, system: str, user: str, temperature: float = 0.0) -> FoundryResponse: ...

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        on_delta: DeltaCallback | None = None,
        idle_timeout_sec: float = 30.0,
        response_format: dict | None = None,
    ) -> FoundryResponse: ...

    @property
    def label(self) -> str: ...


class RealFoundryClient:
    """走 openai SDK → Azure OpenAI / Foundry deployment。

    chat / chat_stream 統一走 stream=True 路徑;chat 只是不傳 on_delta、最後一次回完整內容。
    chunk 之間的等待用 httpx read timeout 控制,實現 idle-timeout 而非 wall-clock timeout,
    讓長回覆只要持續產 token 就不會被砍。
    """

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
        return self.chat_stream(
            system=system,
            user=user,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        on_delta: DeltaCallback | None = None,
        idle_timeout_sec: float = 30.0,
        response_format: dict | None = None,
    ) -> FoundryResponse:
        import httpx

        timeout_cfg = httpx.Timeout(
            connect=10.0,
            write=10.0,
            pool=10.0,
            read=idle_timeout_sec,
        )
        kwargs: dict = {
            "model": self._deployment,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "stream": True,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        stream = self._client.with_options(timeout=timeout_cfg).chat.completions.create(**kwargs)

        chunks: list[str] = []
        response_model = self._deployment
        last_token_at = time.monotonic()
        try:
            for chunk in stream:
                if getattr(chunk, "model", None):
                    response_model = chunk.model
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                now = time.monotonic()
                idle_gap = now - last_token_at
                if idle_gap > idle_timeout_sec:
                    raise TimeoutError(
                        f"foundry stream idle {idle_gap:.1f}s > {idle_timeout_sec}s"
                    )
                last_token_at = now
                chunks.append(delta)
                if on_delta is not None:
                    on_delta(delta)
        except httpx.ReadTimeout as exc:
            raise TimeoutError(
                f"foundry stream idle > {idle_timeout_sec}s (httpx read timeout)"
            ) from exc

        content = "".join(chunks)
        return FoundryResponse(
            content=content,
            model=response_model,
            input_tokens=None,
            output_tokens=None,
        )


class MockFoundryClient:
    """Scripted Foundry,讓 PoC 在無 Azure 配額時也能跑全鏈路。

    路由策略(Plan 節點消費):
    visit 1 → next_module="retrieve"(先補上下文)
    visit 2 → next_module="action"(產出回應)
    visit >=3 → next_module="action"(避免無限 Plan↔Retrieve 迴圈)
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
        return self._scripted(system=system, user=user)

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        on_delta: DeltaCallback | None = None,
        idle_timeout_sec: float = 30.0,
        response_format: dict | None = None,
    ) -> FoundryResponse:
        response = self._scripted(system=system, user=user)
        if on_delta is not None:
            for ch in response.content:
                on_delta(ch)
        return response

    def _scripted(self, *, system: str, user: str) -> FoundryResponse:
        # 用 system prompt 開頭 keyword 區分 Perceive / Plan / Reflect
        if system.startswith("PERCEIVE"):
            payload = {
                "intent": "mock_intent",
                "summary": "mock perceive：使用者輸入已被模擬感知節點解析。",
            }
        elif system.startswith("PLAN"):
            self._plan_visit_counter += 1
            next_module = "retrieve" if self._plan_visit_counter == 1 else "action"
            payload = {
                "thought": f"mock plan thought visit={self._plan_visit_counter}",
                "next_module": next_module,
            }
        elif system.startswith("REFLECT"):
            # 收到「ERROR」開頭的 user → 視為失敗 → 回 plan;否則 END
            if user.startswith("ERROR"):
                payload = {"verdict": "fail", "next_module": "plan", "reason": "mock retry"}
            else:
                payload = {"verdict": "pass", "next_module": None, "reason": "mock ok"}
        else:
            payload = {"echo": user[:80]}

        content = json.dumps(payload, ensure_ascii=False)
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
