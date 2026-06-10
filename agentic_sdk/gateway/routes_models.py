"""GET /v1/models — 依 backend 回傳可用模型。"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/v1/models")
def list_models(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    backend = (settings.workflow_action_backend or "upstream").lower()

    if backend == "foundry":
        deployment = settings.azure_foundry_deployment or "agentic-sdk"
        return {
            "object": "list",
            "data": [
                {
                    "id": deployment,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "azure-foundry",
                }
            ],
        }

    upstream = request.app.state.upstream
    try:
        result = upstream.openai.models.list()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"無法存取上游 {upstream.base_url}:{exc}",
        ) from exc
    return result.model_dump()
