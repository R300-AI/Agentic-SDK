from __future__ import annotations

import os
from functools import lru_cache

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


DEFAULT_KEY_VAULT_NAME = "agentic-sdk-models"


def load_key_vault_secrets(*, override: bool = False) -> dict[str, str]:
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
    client = _secret_client(vault_name)
    values: dict[str, str] = {}
    try:
        properties_iter = client.list_properties_of_secrets()
        for properties in properties_iter:
            secret_name = properties.name
            values[secret_name] = client.get_secret(secret_name).value or ""
    except AzureError as error:
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
    if os.environ.get("PLAYGROUND_SKIP_KEY_VAULT_LOAD", "").strip().lower() in {"1", "true", "yes"}:
        return ""
    configured_name = (
        os.environ.get("PLAYGROUND_KEY_VAULT_NAME")
        or os.environ.get("AZURE_KEY_VAULT_NAME")
        or os.environ.get("KEY_VAULT_NAME")
        or ""
    ).strip()
    if configured_name:
        return configured_name
    if os.environ.get("CI", "").strip().lower() == "true":
        return ""
    return DEFAULT_KEY_VAULT_NAME


@lru_cache(maxsize=4)
def _secret_client(vault_name: str) -> SecretClient:
    vault_url = f"https://{vault_name}.vault.azure.net/"
    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())


def _env_name_for_secret(secret_name: str) -> str:
    return secret_name.strip().replace("-", "_")