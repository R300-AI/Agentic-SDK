"""Capability discovery endpoints for schema-driven clients."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from agentic_sdk.capabilities import KnowledgeBaseRegistry, build_capability_document

router = APIRouter()


@router.get("/v1/capabilities")
def get_capabilities() -> dict:
    return build_capability_document()


@router.get("/v1/knowledge-bases/{knowledge_base_ref}/preview")
def preview_knowledge_base(
    knowledge_base_ref: str,
    query: str = Query(..., min_length=1),
    top_k: int = Query(3, ge=1, le=20),
) -> dict:
    registry = KnowledgeBaseRegistry()
    try:
        return registry.preview(knowledge_base_ref, query=query, top_k=top_k)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
