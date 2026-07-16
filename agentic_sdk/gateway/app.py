"""FastAPI 應用工廠。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ActiveStore, ArchivedStore
from agentic_sdk.gateway.keyvault_loader import load_first_model_from_keyvault
from agentic_sdk.gateway.routes_chat import router as chat_router
from agentic_sdk.gateway.routes_capabilities import router as capabilities_router
from agentic_sdk.gateway.routes_context import router as context_router
from agentic_sdk.gateway.routes_models import router as models_router
from agentic_sdk.gateway.routes_telemetry import router as telemetry_router
from agentic_sdk.gateway.routes_workflow import router as workflow_router
from agentic_sdk.gateway.upstream_client import UpstreamClient
from agentic_sdk.observability import configure_observability

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent.parent.parent / "demo" / "dist"


async def _periodic_upstream_health(app: FastAPI, interval_sec: float) -> None:
    """M2-2:背景週期性對上游做 healthcheck;UpstreamClient 內部已 emit 事件。"""
    upstream: UpstreamClient = app.state.upstream
    while True:
        try:
            await asyncio.sleep(interval_sec)
            await asyncio.to_thread(upstream.healthcheck)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("periodic upstream healthcheck failed")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    load_first_model_from_keyvault(settings)
    upstream_required = (settings.workflow_action_backend or "upstream").lower() == "upstream"

    if upstream_required:
        upstream: UpstreamClient = app.state.upstream
        health = upstream.healthcheck()
        if not health["reachable"]:
            logger.warning(
                "上游 %s 無法連線(error=%s)。Gateway 仍會啟動,/v1/* 將返回 502/503,直到上游就緒。",
                health["url"],
                health.get("error"),
            )
        else:
            logger.info("上游 %s 就緒,可用模型:%s", health["url"], health["models"])

        task = asyncio.create_task(
            _periodic_upstream_health(app, settings.upstream_health_poll_sec)
        )
    else:
        logger.info(
            "WORKFLOW_ACTION_BACKEND=foundry — Action 走 Azure Foundry,略過 AMD 上游 healthcheck。"
        )
        task = None

    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    telemetry = configure_observability(settings)

    app = FastAPI(
        title="Agentic SDK Gateway",
        version="0.0.1",
        description="OpenAI-compatible gateway proxying AMD NPU upstream and orchestrating five-module workflow.",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.upstream = UpstreamClient(settings)
    app.state.telemetry = telemetry
    app.state.active_context = ActiveStore(
        max_mb=settings.active_context_max_mb,
        idle_demote_sec=settings.context_idle_demote_sec,
        hard_ttl_sec=settings.context_hard_ttl_sec,
        archived=ArchivedStore(directory=settings.archived_context_dir),
    )

    app.include_router(models_router)
    app.include_router(capabilities_router)
    app.include_router(chat_router)
    app.include_router(telemetry_router)
    app.include_router(context_router)
    app.include_router(workflow_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        backend = (app.state.settings.workflow_action_backend or "upstream").lower()
        info: dict[str, object] = {
            "status": "ok",
            "action_backend": backend,
            "telemetry": app.state.telemetry.stats(),
            "active_context": app.state.active_context.stats(),
        }
        if backend == "upstream":
            info["upstream"] = app.state.upstream.healthcheck()
        elif backend == "foundry":
            info["foundry"] = {
                "endpoint": bool(app.state.settings.azure_foundry_endpoint),
                "deployment": app.state.settings.azure_foundry_deployment,
            }
        return info

    # 靜態前端（demo/dist/）— 僅在已 build 時掛載，本機 dev 可跳過
    if _STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            return FileResponse(str(_STATIC_DIR / "index.html"))

    return app
