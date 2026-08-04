from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from urllib.parse import quote

import httpx


DEFAULT_KEY_VAULT_NAME = "agentic-sdk-models"


def load_key_vault_secrets(*, override: bool = False) -> dict[str, str]:
    if os.environ.get("PLAYGROUND_SKIP_KEY_VAULT_LOAD", "").strip().lower() in {"1", "true", "yes"}:
        return {}
    vault_name = _key_vault_name()
    if not vault_name:
        return {}

    loaded: dict[str, str] = {}
    for secret_name, value in _key_vault_values(vault_name).items():
        env_name = _env_name_for_secret(secret_name)
        if not override and os.environ.get(env_name):
            continue
        os.environ[env_name] = value
        loaded[env_name] = value
    return loaded


@lru_cache(maxsize=4)
def _key_vault_values(vault_name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        token = _access_token()
        for secret_name in _secret_names(vault_name, token):
            values[secret_name] = _secret_value(vault_name, token, secret_name)
    except (KeyError, OSError, subprocess.SubprocessError, httpx.HTTPError, ValueError) as error:
        os.environ["PLAYGROUND_KEY_VAULT_LOAD_ERROR"] = error.__class__.__name__
        return {}
    return values


def configured_key_vault_secret_names() -> tuple[str, ...]:
    vault_name = _key_vault_name()
    if not vault_name:
        return ()
    return tuple(sorted(_key_vault_values(vault_name)))


def configured_key_vault_env_names() -> tuple[str, ...]:
    return tuple(_env_name_for_secret(secret_name) for secret_name in configured_key_vault_secret_names())


def _key_vault_name() -> str:
    configured_name = (
        os.environ.get("PLAYGROUND_KEY_VAULT_NAME")
        or os.environ.get("AZURE_KEY_VAULT_NAME")
        or os.environ.get("KEY_VAULT_NAME")
        or ""
    ).strip()
    if configured_name:
        return configured_name
    return DEFAULT_KEY_VAULT_NAME


def _env_name_for_secret(secret_name: str) -> str:
    return secret_name.strip().replace("-", "_")


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
                secret_id = str(item.get("id") or "").rstrip("/")
                name = secret_id.rsplit("/", 1)[-1].strip()
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
    for command in ("az", "az.cmd"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    windows_default = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    if os.path.exists(windows_default):
        return windows_default
    return "az"