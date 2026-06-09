"""Settings 行為驗證:預設值、env 檔載入、Azure Foundry 守門。"""

from __future__ import annotations

import pytest

from agentic_sdk.config import Settings


def test_defaults_when_no_env_file():
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.gateway_host == "127.0.0.1"
    assert settings.gateway_port == 8080
    assert settings.upstream_api_base_url == "http://localhost:8000/v1"
    assert settings.upstream_healthcheck_timeout_sec == 5.0
    assert settings.azure_foundry_deployment == "gpt-4o-mini"


def test_env_file_overrides(tmp_path):
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "GATEWAY_PORT=9090\n"
        "UPSTREAM_API_BASE_URL=http://amd-host:8000/v1\n"
        "AZURE_FOUNDRY_ENDPOINT=https://example.cognitiveservices.azure.com/\n"
        "AZURE_FOUNDRY_API_KEY=fake-key\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]

    assert settings.gateway_port == 9090
    assert settings.upstream_api_base_url == "http://amd-host:8000/v1"
    assert settings.azure_foundry_endpoint.startswith("https://example.")
    assert settings.azure_foundry_api_key == "fake-key"


def test_require_azure_foundry_lists_missing_keys():
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        azure_foundry_endpoint="",
        azure_foundry_api_key="",
    )

    with pytest.raises(RuntimeError) as exc_info:
        settings.require_azure_foundry()

    msg = str(exc_info.value)
    assert "AZURE_FOUNDRY_ENDPOINT" in msg
    assert "AZURE_FOUNDRY_API_KEY" in msg


def test_require_azure_foundry_passes_when_filled():
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        azure_foundry_endpoint="https://example.cognitiveservices.azure.com/",
        azure_foundry_api_key="fake-key",
    )

    settings.require_azure_foundry()  # 不應拋例外


def test_invalid_port_rejected():
    with pytest.raises(ValueError):
        Settings(_env_file=None, gateway_port=70000)  # type: ignore[call-arg]
