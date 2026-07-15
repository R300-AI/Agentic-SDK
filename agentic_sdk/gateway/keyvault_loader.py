"""啟動時從 Azure Key Vault 掃描 model-{id}-* secrets，
並將模型池保存到 Settings，同時把第一個模型注入既有 Foundry 設定。

只在 KEY_VAULT_NAME 環境變數存在時執行（本機開發不需要）。
使用 Managed Identity（DefaultAzureCredential），不需要任何額外憑證。
"""

from __future__ import annotations

import logging
import os

_MODEL_SUFFIXES = ("name", "endpoint", "key", "deployment", "api-version")

logger = logging.getLogger(__name__)


def load_first_model_from_keyvault(settings) -> None:
    """掃描 Key Vault 中的 model-{id}-* secrets，建立模型池並注入預設模型。

    若 KEY_VAULT_NAME 未設定、azure-identity/azure-keyvault-secrets 未安裝，
    或 Key Vault 無法存取，則靜默略過（不中斷啟動）。
    """
    kv_name = os.environ.get("KEY_VAULT_NAME", "").strip()
    if not kv_name:
        logger.debug("KEY_VAULT_NAME 未設定，跳過 Key Vault 載入。")
        return

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        logger.warning("azure-identity / azure-keyvault-secrets 未安裝，跳過 Key Vault 載入。")
        return

    vault_url = f"https://{kv_name}.vault.azure.net"
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        models = _load_models(client)
        settings.keyvault_models = models

        if not models:
            logger.warning("Key Vault %s 中找不到任何 model-{id}-key secret。", kv_name)
            return

        first_model = models[0]
        logger.info("Key Vault: 載入 %d 個模型，預設模型 id=%s", len(models), first_model["id"])

        if not settings.azure_foundry_endpoint and first_model.get("endpoint"):
            settings.azure_foundry_endpoint = first_model["endpoint"]
        if not settings.azure_foundry_api_key and first_model.get("api_key"):
            settings.azure_foundry_api_key = first_model["api_key"]
        if first_model.get("deployment"):
            settings.azure_foundry_deployment = first_model["deployment"]
        if first_model.get("api_version"):
            settings.azure_foundry_api_version = first_model["api_version"]

        logger.info(
            "Key Vault 載入完成: models=%d endpoint=%s deployment=%s api_version=%s",
            len(models),
            bool(first_model.get("endpoint")),
            first_model.get("deployment"),
            first_model.get("api_version") or "(使用預設)",
        )

    except Exception as exc:
        logger.warning("Key Vault 載入失敗（%s），Gateway 繼續以現有設定啟動。", exc)


def resolve_foundry_model(settings, requested_model: str | None) -> dict[str, str] | None:
    if not requested_model:
        return settings.keyvault_models[0] if settings.keyvault_models else None

    wanted = requested_model.strip().lower()
    for model in settings.keyvault_models:
        candidates = {
            model.get("id", "").lower(),
            model.get("name", "").lower(),
            model.get("deployment", "").lower(),
        }
        if wanted in candidates:
            return model
    return None


def _load_models(client) -> list[dict[str, str]]:
    model_ids: set[str] = set()
    for secret_prop in client.list_properties_of_secrets():
        name = (secret_prop.name or "").strip()
        model_id = _extract_model_id(name)
        if model_id:
            model_ids.add(model_id)

    models: list[dict[str, str]] = []
    for model_id in sorted(model_ids):
        model = {
            "id": model_id,
            "name": _safe_get_secret(client, model_id, "name") or model_id,
            "endpoint": _safe_get_secret(client, model_id, "endpoint"),
            "api_key": _safe_get_secret(client, model_id, "key"),
            "deployment": _safe_get_secret(client, model_id, "deployment"),
            "api_version": _safe_get_secret(client, model_id, "api-version"),
        }
        if not (model["endpoint"] and model["api_key"] and model["deployment"]):
            logger.warning("Key Vault 模型 %s 缺少 endpoint/key/deployment，略過。", model_id)
            continue
        models.append(model)
    return models


def _extract_model_id(secret_name: str) -> str | None:
    if not secret_name.startswith("model-"):
        return None
    for suffix in _MODEL_SUFFIXES:
        token = f"-{suffix}"
        if secret_name.endswith(token):
            model_id = secret_name[len("model-"):-len(token)]
            return model_id or None
    return None


def _safe_get_secret(client, model_id: str, suffix: str) -> str:
    try:
        return client.get_secret(f"model-{model_id}-{suffix}").value or ""
    except Exception:
        return ""
