"""Gateway 套件 — 對外 OpenAI 相容前端,只代理上游 AMD NPU api.py。"""

from agentic_sdk.gateway.app import create_app

__all__ = ["create_app"]
