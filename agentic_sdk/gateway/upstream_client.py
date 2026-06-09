"""上游 AMD NPU api.py 的薄封裝。

邊界提醒:本模組只連 `UPSTREAM_API_BASE_URL`(Model Card 交付的 AMD NPU 推論伺服器)。
其他 LLM 來源(如 Azure Foundry)由節點實作自行用 openai SDK 呼叫,不進這一層。
"""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

from agentic_sdk.config import Settings
from agentic_sdk.observability.events import (
    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
    make_event,
)

logger = logging.getLogger(__name__)


class UpstreamClient:
    def __init__(self, settings: Settings, base_url: str | None = None) -> None:
        self._settings = settings
        self._base_url = base_url or settings.upstream_api_base_url
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=settings.upstream_api_key or "not-needed",
            timeout=settings.infer_request_timeout_sec,
        )

    @property
    def openai(self) -> OpenAI:
        return self._client

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def base_url(self) -> str:
        return self._base_url

    def healthcheck(self) -> dict[str, object]:
        url = self._base_url.rstrip("/") + "/models"
        try:
            response = httpx.get(
                url,
                timeout=self._settings.upstream_healthcheck_timeout_sec,
            )
            response.raise_for_status()
            payload = response.json()
            models = [item.get("id") for item in payload.get("data", [])]
            logger.info(
                "upstream healthcheck ok url=%s models=%s",
                url,
                models,
                extra={"event": make_event(
                    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
                    upstream_url=url,
                    upstream_reachable=True,
                    upstream_models=models,
                )},
            )
            return {"reachable": True, "url": url, "models": models}
        except Exception as exc:
            logger.warning(
                "upstream healthcheck failed url=%s error=%s",
                url,
                exc,
                extra={"event": make_event(
                    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
                    upstream_url=url,
                    upstream_reachable=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )},
            )
            return {"reachable": False, "url": url, "error": str(exc)}
