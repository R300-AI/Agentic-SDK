"""統一配置入口。所有具業務意義的參數來自 .env,嚴禁散落於程式碼。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gateway_host: str = Field(default="127.0.0.1")
    gateway_port: int = Field(default=8080, ge=1, le=65535)

    dashboard_port: int = Field(default=8501, ge=1, le=65535)
    dashboard_refresh_sec: float = Field(default=2.0, gt=0)
    dashboard_snapshot_limit: int = Field(default=500, ge=1, le=10000)

    upstream_api_base_url: str = Field(default="http://localhost:8000/v1")
    upstream_api_key: str = Field(default="not-needed")
    upstream_healthcheck_timeout_sec: float = Field(default=5.0, gt=0)

    azure_foundry_endpoint: str = Field(default="")
    azure_foundry_api_key: str = Field(default="")
    azure_foundry_deployment: str = Field(default="gpt-4o-mini")
    azure_foundry_api_version: str = Field(default="2024-12-01-preview")

    infer_request_timeout_sec: float = Field(default=120.0, gt=0)

    telemetry_buffer_size: int = Field(default=2000, gt=0)
    telemetry_jsonl_path: str = Field(default="")

    workflow_max_node_hops: int = Field(default=50, ge=1, le=10_000)
    workflow_max_revisit: int = Field(default=5, ge=1, le=1_000)
    workflow_timeout_sec: float = Field(default=30.0, gt=0)
    workflow_force_mock_foundry: bool = Field(default=False)
    workflow_action_backend: str = Field(default="upstream")

    active_context_max_mb: float = Field(default=8.0, gt=0)
    context_idle_demote_sec: float = Field(default=300.0, gt=0)
    context_hard_ttl_sec: float = Field(default=3600.0, gt=0)
    archived_context_dir: str = Field(default=".archived_context")

    upstream_health_poll_sec: float = Field(default=5.0, gt=0)

    gateway_cors_origins: str = Field(
        default="http://localhost:5173",
        description="允許通過 CORS 的 Origin 白名單，可用逗號或 JSON 陣列。GH Pages 部署需加入 https://<user>.github.io。",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        raw = (self.gateway_cors_origins or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            import json
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [s.strip() for s in raw.split(",") if s.strip()]

    def require_azure_foundry(self) -> None:
        missing = [
            name
            for name, value in (
                ("AZURE_FOUNDRY_ENDPOINT", self.azure_foundry_endpoint),
                ("AZURE_FOUNDRY_API_KEY", self.azure_foundry_api_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Azure Foundry 配置缺失:" + ", ".join(missing) + "。請於 .env 補上後重啟。"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
