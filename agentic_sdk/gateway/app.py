"""FastAPI 應用工廠。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ActiveStore, ArchivedStore
from agentic_sdk.gateway.keyvault_loader import load_first_model_from_keyvault
from agentic_sdk.gateway.routes_chat import router as chat_router
from agentic_sdk.gateway.routes_capabilities import router as capabilities_router
from agentic_sdk.gateway.routes_context import router as context_router
from agentic_sdk.gateway.routes_models import router as models_router
from agentic_sdk.gateway.routes_telemetry import router as telemetry_router
from agentic_sdk.gateway.routes_workflow import router as workflow_router
from agentic_sdk.observability.events import EVENT_GATEWAY_OPENAI_HEALTHCHECK, make_event
from agentic_sdk.observability import configure_observability

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent.parent.parent / "demo" / "dist"


def _healthcheck_openai_endpoint(settings: Settings, client: OpenAI) -> dict[str, object]:
    url = settings.openai_api_base_url.rstrip("/") + "/models"
    try:
        response = httpx.get(url, timeout=settings.openai_healthcheck_timeout_sec)
        response.raise_for_status()
        payload = response.json()
        models = [item.get("id") for item in payload.get("data", [])]
        logger.info(
            "openai healthcheck ok url=%s models=%s",
            url,
            models,
            extra={"event": make_event(
                EVENT_GATEWAY_OPENAI_HEALTHCHECK,
                openai_url=url,
                openai_reachable=True,
                openai_models=models,
            )},
        )
        return {"reachable": True, "url": url, "models": models}
    except Exception as exc:
        logger.warning(
            "openai healthcheck failed url=%s error=%s",
            url,
            exc,
            extra={"event": make_event(
                EVENT_GATEWAY_OPENAI_HEALTHCHECK,
                openai_url=url,
                openai_reachable=False,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )},
        )
        return {"reachable": False, "url": url, "error": str(exc)}


async def _periodic_openai_health(app: FastAPI, interval_sec: float) -> None:
    """M2-2:背景週期性對 OpenAI-compatible 端點做 healthcheck。"""
    settings: Settings = app.state.settings
    openai_client: OpenAI = app.state.openai_client
    while True:
        try:
            await asyncio.sleep(interval_sec)
            await asyncio.to_thread(_healthcheck_openai_endpoint, settings, openai_client)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("periodic openai healthcheck failed")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    load_first_model_from_keyvault(settings)
    openai_client: OpenAI = app.state.openai_client
    health = _healthcheck_openai_endpoint(settings, openai_client)
    if not health["reachable"]:
        logger.warning(
            "OpenAI-compatible 端點 %s 無法連線(error=%s)。Gateway 仍會啟動,/v1/* 將返回 502/503,直到端點就緒。",
            health["url"],
            health.get("error"),
        )
    else:
        logger.info("OpenAI-compatible 端點 %s 就緒,可用模型:%s", health["url"], health["models"])

    task = asyncio.create_task(
        _periodic_openai_health(app, settings.openai_health_poll_sec)
    )

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
        description="OpenAI-compatible gateway orchestrating five-module workflow.",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.openai_client = OpenAI(
        base_url=settings.openai_api_base_url,
        api_key=settings.openai_api_key or "not-needed",
        timeout=settings.infer_request_timeout_sec,
    )
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
        info: dict[str, object] = {
            "status": "ok",
            "telemetry": app.state.telemetry.stats(),
            "active_context": app.state.active_context.stats(),
            "openai": _healthcheck_openai_endpoint(app.state.settings, app.state.openai_client),
        }
        return info

    # 靜態前端（demo/dist/）— 僅在已 build 時掛載，本機 dev 可跳過
    if _STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            return FileResponse(str(_STATIC_DIR / "index.html"))

    return app
