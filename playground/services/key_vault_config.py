from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote

import httpx


DEFAULT_KEY_VAULT_NAME = "agentic-sdk-models"
_CHAT_ENDPOINT_PREFIXES = ("GPT-54", "GPT-55")
_EMBEDDING_ENDPOINT_PREFIXES = ("EMBEDDED-LARGE", "EMBEDDED-SMALL")


class KeyVaultConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AiHubSettings:
    base_url: str
    playground_origin: str


@dataclass(frozen=True)
class ChatEndpointSettings:
    id: str
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class EmbeddingEndpointSettings:
    id: str
    api_key: str
    endpoint: str
    deployment_name: str


@dataclass(frozen=True)
class KeyVaultSettings:
    ai_hub: AiHubSettings
    chat_endpoints: tuple[ChatEndpointSettings, ...]
    embedding_endpoints: tuple[EmbeddingEndpointSettings, ...]


def key_vault_settings() -> KeyVaultSettings:
    if _test_mode_enabled():
        return _settings_from_values(
            {
                "AI-HUB-BASE-URL": os.environ.get("PLAYGROUND_TEST_AI_HUB_BASE_URL", "https://aihub.test"),
                "AI-HUB-PLAYGROUND-ORIGIN": os.environ.get("PLAYGROUND_TEST_AI_HUB_PLAYGROUND_ORIGIN", "https://playground.test"),
            }
        )
    return _settings_from_values(_key_vault_values(_key_vault_name()))


def _test_mode_enabled() -> bool:
    return os.environ.get("PLAYGROUND_TEST_MODE", "").strip().lower() in {"1", "true", "yes"}


def _settings_from_values(values: dict[str, str]) -> KeyVaultSettings:
    normalized = {str(name).strip().upper(): str(value or "").strip() for name, value in values.items()}
    base_url = _required_setting(normalized, "AI-HUB-BASE-URL")
    playground_origin = _required_setting(normalized, "AI-HUB-PLAYGROUND-ORIGIN")
    chat_endpoints = tuple(
        endpoint
        for prefix in _CHAT_ENDPOINT_PREFIXES
        if (endpoint := _chat_endpoint_settings(normalized, prefix)) is not None
    )
    embedding_endpoints = tuple(
        endpoint
        for prefix in _EMBEDDING_ENDPOINT_PREFIXES
        if (endpoint := _embedding_endpoint_settings(normalized, prefix)) is not None
    )
    return KeyVaultSettings(
        ai_hub=AiHubSettings(base_url=base_url.rstrip("/"), playground_origin=playground_origin.rstrip("/")),
        chat_endpoints=chat_endpoints,
        embedding_endpoints=embedding_endpoints,
    )


def _required_setting(values: dict[str, str], secret_name: str) -> str:
    value = values.get(secret_name, "")
    if not value:
        raise KeyVaultConfigurationError("missing_secret", f"Key Vault is missing required secret {secret_name}.")
    return value


def _chat_endpoint_settings(values: dict[str, str], prefix: str) -> ChatEndpointSettings | None:
    secret_names = (f"{prefix}-API-KEY", f"{prefix}-BASE-URL", f"{prefix}-MODEL")
    if not any(values.get(name) for name in secret_names):
        return None
    return ChatEndpointSettings(
        id=prefix.lower(),
        api_key=_required_setting(values, secret_names[0]),
        base_url=_required_setting(values, secret_names[1]),
        model=_required_setting(values, secret_names[2]),
    )


def _embedding_endpoint_settings(values: dict[str, str], prefix: str) -> EmbeddingEndpointSettings | None:
    secret_names = (f"{prefix}-API-KEY", f"{prefix}-ENDPOINT", f"{prefix}-DEPLOYMENT-NAME")
    if not any(values.get(name) for name in secret_names):
        return None
    return EmbeddingEndpointSettings(
        id=prefix.lower(),
        api_key=_required_setting(values, secret_names[0]),
        endpoint=_required_setting(values, secret_names[1]),
        deployment_name=_required_setting(values, secret_names[2]),
    )


@lru_cache(maxsize=4)
def _key_vault_values(vault_name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        token = _access_token()
        for secret_name in _secret_names(vault_name, token):
            values[secret_name] = _secret_value(vault_name, token, secret_name)
    except (KeyError, OSError, subprocess.SubprocessError, httpx.HTTPError, ValueError) as error:
        return {}
    return values


def configured_key_vault_secret_names() -> tuple[str, ...]:
    vault_name = _key_vault_name()
    if not vault_name:
        return ()
    return tuple(sorted(_key_vault_values(vault_name)))


def _key_vault_name() -> str:
    return DEFAULT_KEY_VAULT_NAME


def _secret_names(vault_name: str, token: str) -> list[str]:
    names: list[str] = []
    url = f"https://{vault_name}.vault.azure.net/secrets?api-version=7.4"
    headers = _vault_headers(token)
    with httpx.Client(timeout=10.0) as client:
        while url:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("value", []):
                secret_path = str(item.get("id") or "").rstrip("/").split("/")
                try:
                    secrets_index = secret_path.index("secrets")
                    name = secret_path[secrets_index + 1].strip()
                except (ValueError, IndexError):
                    name = ""
                if name:
                    names.append(name)
            url = str(payload.get("nextLink") or "")
    return names


def _secret_value(vault_name: str, token: str, secret_name: str) -> str:
    url = f"https://{vault_name}.vault.azure.net/secrets/{quote(secret_name, safe='')}?api-version=7.4"
    response = httpx.get(url, headers=_vault_headers(token), timeout=10.0)
    response.raise_for_status()
    return str(response.json().get("value") or "")


def _vault_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _access_token() -> str:
    if os.environ.get("IDENTITY_ENDPOINT") and os.environ.get("IDENTITY_HEADER"):
        return _managed_identity_token(
            os.environ["IDENTITY_ENDPOINT"],
            {"X-IDENTITY-HEADER": os.environ["IDENTITY_HEADER"]},
            "api-version=2019-08-01&resource=https://vault.azure.net",
        )
    if os.environ.get("MSI_ENDPOINT") and os.environ.get("MSI_SECRET"):
        return _managed_identity_token(
            os.environ["MSI_ENDPOINT"],
            {"Secret": os.environ["MSI_SECRET"]},
            "api-version=2017-09-01&resource=https://vault.azure.net",
        )
    return _azure_cli_token()


def _managed_identity_token(endpoint: str, headers: dict[str, str], query: str) -> str:
    separator = "&" if "?" in endpoint else "?"
    response = httpx.get(f"{endpoint}{separator}{query}", headers=headers, timeout=10.0)
    response.raise_for_status()
    token = str(response.json().get("access_token") or "").strip()
    if not token:
        raise ValueError("Managed identity did not return an access token.")
    return token


def _azure_cli_token() -> str:
    az_command = _azure_cli_command()
    completed = subprocess.run(
        [az_command, "account", "get-access-token", "--resource", "https://vault.azure.net", "--query", "accessToken", "-o", "tsv"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    token = completed.stdout.strip()
    if not token:
        raise ValueError("Azure CLI did not return an access token.")
    return token


def _azure_cli_command() -> str:
    commands = ("az.cmd", "az") if os.name == "nt" else ("az", "az.cmd")
    for command in commands:
        resolved = shutil.which(command)
        if resolved:
            return resolved
    windows_default = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    if os.path.exists(windows_default):
        return windows_default
    return "az"