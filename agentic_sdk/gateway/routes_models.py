"""GET /v1/models — 回傳可用的 OpenAI-compatible 模型。"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from agentic_sdk.gateway.openai_target import uses_placeholder_local_openai

router = APIRouter()


@router.get("/v1/models")
def list_models(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    models = settings.keyvault_models or []
    if models:
        created = int(time.time())
        return {
            "object": "list",
            "data": [
                {
                    "id": item["id"],
                    "object": "model",
                    "created": created,
                    "owned_by": "openai-compatible",
                    "display_name": item.get("name") or item["id"],
                    "model": item.get("model") or item["id"],
                }
                for item in models
            ],
        }

    if uses_placeholder_local_openai(settings.openai_api_base_url):
        raise HTTPException(
            status_code=503,
            detail=(
                "OpenAI-compatible upstream 尚未設定。"
                "請在 App Service 對應的 Key Vault 內提供 model-{id}-base-url / key / model secrets。"
            ),
        )

    openai_client = request.app.state.openai_client
    try:
        result = openai_client.models.list()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"無法存取 OpenAI-compatible 端點 {settings.openai_api_base_url}:{exc}",
        ) from exc
    return result.model_dump()
