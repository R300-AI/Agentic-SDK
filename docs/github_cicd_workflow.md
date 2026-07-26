# GitHub CI/CD 到 Azure App Service

此 workflow 會將正式 FastAPI Playground 部署到 Azure App Service。部署檔位於 `.github/workflows/deploy-playground.yml`，觸發條件是 `main` 分支中 `agentic_sdk/`、`playground/`、`requirements.txt` 或部署 workflow 本身變更，也可以手動從 GitHub Actions 執行。

## Repository Variables

請在 GitHub repository 的 `Settings > Secrets and variables > Actions > Variables` 建立下列 variables：

| 變數 | 說明 |
| --- | --- |
| `AZURE_CLIENT_ID` | 可透過 OIDC 登入 Azure 的 Entra application client id。 |
| `AZURE_TENANT_ID` | Azure tenant id。 |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription id。 |
| `AZURE_RESOURCE_GROUP` | App Service、Plan、Key Vault 所在 resource group。 |
| `AZURE_REGION` | Azure region，例如 `eastasia`。 |
| `AZURE_WEBAPP_NAME` | App Service name，必須全域唯一。 |
| `KEY_VAULT_NAME` | Key Vault name，必須全域唯一。 |

`PLAYGROUND_SECRET_KEY` 會由 workflow 讀取既有 App Service setting；如果尚未存在，部署時會在 Azure 端產生一次並寫入 App Service。模型 endpoint 和 API key 建議放在 Key Vault，由 App Service 的 managed identity 在 runtime 讀取。

## Azure OIDC 前置設定

在 Azure 建立 Entra application / service principal，並將 GitHub repository 設為 federated credential。Subject 可依環境調整，常見設定為：

```text
repo:R300-AI/Agentic-SDK:ref:refs/heads/main
```

這個 service principal 需要能建立或更新 Resource Group、Linux App Service Plan、App Service、Key Vault，以及 Key Vault role assignment。最小權限可依組織政策拆分；PoC 階段通常會先在目標 resource group scope 授予 Contributor，並在 Key Vault scope 授予可管理 role assignment 的權限。

## Workflow 行為

部署流程會：

1. 使用 GitHub OIDC 登入 Azure，不使用 Azure publish profile secret。
2. 冪等建立 Resource Group、Linux App Service Plan、Python 3.12 App Service、Key Vault。
3. 啟用 App Service managed identity，並授予 Key Vault Secrets User。
4. 設定 App Service startup command：

```bash
python -m playground.main
```

5. 設定 `PORT=8000`、`WEBSITES_PORT=8000`、`SCM_DO_BUILD_DURING_DEPLOYMENT=false`、`ENABLE_ORYX_BUILD=false`、`PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages:/home/site/wwwroot`、`KEY_VAULT_NAME`，並沿用或建立 `PLAYGROUND_SECRET_KEY`。Azure App Service 對外仍由平台提供 HTTP/HTTPS 80/443，容器內由 `PORT=8000` 接收流量。
6. 在 GitHub Actions runner 上安裝 Python dependencies 到 `.python_packages/lib/site-packages`，並用 FastAPI TestClient smoke test `/healthz`、`/playground`、`/playground/builder`。
7. 打包 `agentic_sdk/`、`playground/`、`.python_packages/`、`requirements.txt` 為 `deploy.zip`。
8. 使用 `azure/webapps-deploy` 部署到 App Service。
9. 對 `/playground`、`/playground/builder`、Runner 靜態 JS、`/static/css/app.css` 與 Builder 匯出的 source 執行 smoke check，確認公開站台回傳正式 Playground、Builder Q4 顯示 `純文字回覆` / `可互動元件`、互動 API 區塊包含 `回覆風格與規範`、`可互動元件 API`、`功能說明`，Runner 仍載入 ToolCallPanel 前端支援，匯出的互動 workflow 使用 `ToolCallAction` 且不含 `StructuredAction`。

部署完成後，正式入口為：

```text
https://<AZURE_WEBAPP_NAME>.azurewebsites.net/playground
```

## 本機驗證

部署前可先在本機執行：

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m playground.main --host 127.0.0.1 --port 5050 --reload
```

然後開啟 `http://127.0.0.1:5050/playground`。