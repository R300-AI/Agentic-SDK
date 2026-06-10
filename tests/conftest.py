"""Pytest 共用 fixture。

設計重點:
- `test_settings` 不讀本機 .env(避免測試環境受真實 Azure Key 污染),
  改以 `_env_file=None` + 顯式參數產生獨立 Settings 實例。
- `make_app` factory 採顯式注入(`create_app(settings=...)`),
  繞過 `get_settings()` 的 lru_cache,讓每個測試擁有獨立的 app/state。
- 上游 HTTP 一律以 respx mock,測試不依賴外部服務。
"""

from __future__ import annotations

from typing import Callable

import pytest
import respx
from fastapi.testclient import TestClient

from agentic_sdk.config import Settings
from agentic_sdk.gateway.app import create_app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        gateway_host="127.0.0.1",
        gateway_port=8080,
        upstream_api_base_url="http://upstream.test/v1",
        upstream_api_key="test-key",
        upstream_healthcheck_timeout_sec=1.0,
        infer_request_timeout_sec=2.0,
        # 顯式鎖定測試用值，避免 OS 環境變數污染
        workflow_action_backend="upstream",
        workflow_force_mock_foundry=False,
        azure_foundry_endpoint="",
        azure_foundry_api_key="",
    )


@pytest.fixture
def make_client(test_settings: Settings) -> Callable[[Settings | None], TestClient]:
    def _factory(settings: Settings | None = None) -> TestClient:
        app = create_app(settings or test_settings)
        return TestClient(app)

    return _factory


@pytest.fixture
def respx_mock():
    with respx.mock(assert_all_called=False) as router:
        yield router
