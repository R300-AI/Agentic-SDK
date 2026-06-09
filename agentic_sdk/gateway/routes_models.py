"""GET /v1/models — 轉發上游 api.py 的回應。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/v1/models")
def list_models(request: Request) -> dict[str, object]:
    upstream = request.app.state.upstream
    try:
        result = upstream.openai.models.list()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"無法存取上游 {upstream.base_url}:{exc}",
        ) from exc
    return result.model_dump()
