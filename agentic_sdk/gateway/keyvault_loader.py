"""啟動時從 Azure Key Vault 掃描 model-{id}-* secrets，
並將第一個模型的 endpoint / key / deployment 注入 Settings。

只在 KEY_VAULT_NAME 環境變數存在時執行（本機開發不需要）。
使用 Managed Identity（DefaultAzureCredential），不需要任何額外憑證。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_first_model_from_keyvault(settings) -> None:
    """掃描 Key Vault 中的 model-{id}-* secrets，取第一個模型注入 Settings。

    若 KEY_VAULT_NAME 未設定、azure-identity/azure-keyvault-secrets 未安裝，
    或 Key Vault 無法存取，則靜默略過（不中斷啟動）。
    """
    kv_name = os.environ.get("KEY_VAULT_NAME", "").strip()
    if not kv_name:
        logger.debug("KEY_VAULT_NAME 未設定，跳過 Key Vault 載入。")
        return

    if settings.azure_foundry_endpoint and settings.azure_foundry_api_key:
        logger.debug("AZURE_FOUNDRY_ENDPOINT/API_KEY 已設定，跳過 Key Vault 載入。")
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

        # 列出所有 secrets，找出所有 model id
        model_ids: set[str] = set()
        for secret_prop in client.list_properties_of_secrets():
            name: str = secret_prop.name or ""
            if name.startswith("model-") and name.endswith("-key"):
                model_id = name[len("model-"):-len("-key")]
                model_ids.add(model_id)

        if not model_ids:
            logger.warning("Key Vault %s 中找不到任何 model-{id}-key secret。", kv_name)
            return

        # 取第一個模型（按字母排序，確保穩定性）
        first_id = sorted(model_ids)[0]
        logger.info("Key Vault: 載入模型 id=%s", first_id)

        def _get(suffix: str) -> str:
            try:
                return client.get_secret(f"model-{first_id}-{suffix}").value or ""
            except Exception:
                return ""

        endpoint = _get("endpoint")
        api_key = _get("key")
        deployment = _get("deployment")

        if endpoint:
            settings.azure_foundry_endpoint = endpoint
        if api_key:
            settings.azure_foundry_api_key = api_key
        if deployment:
            settings.azure_foundry_deployment = deployment

        logger.info(
            "Key Vault 載入完成: endpoint=%s deployment=%s",
            bool(endpoint),
            deployment,
        )

    except Exception as exc:
        logger.warning("Key Vault 載入失敗（%s），Gateway 繼續以現有設定啟動。", exc)
