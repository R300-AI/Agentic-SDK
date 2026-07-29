# Azure

這一頁說明如何用 GitHub Actions 將 Playground 部署到 Azure App Service。部署檔位於 `.github/workflows/deploy-playground.yml`。當 `main` 分支中的 `agentic_sdk/`、`playground/`、`.env`、`requirements.txt` 或部署檔變更時，GitHub 會執行部署；你也可以在 GitHub Actions 手動啟動。

## Repository Variables

請在 GitHub repository 的 `Settings > Secrets and variables > Actions > Variables` 建立下列 variables：

| 變數 | 說明 |
| --- | --- |
| `AZURE_CLIENT_ID` | 可讓 GitHub Actions 登入 Azure 的 Entra application client id。 |
| `AZURE_TENANT_ID` | Azure tenant id。 |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription id。 |
| `AZURE_RESOURCE_GROUP` | App Service、Plan、Key Vault 所在的 resource group。 |
| `AZURE_REGION` | Azure region，例如 `eastasia`。 |
| `AZURE_WEBAPP_NAME` | App Service 名稱，必須全域唯一。 |
| `KEY_VAULT_NAME` | Key Vault 名稱，必須全域唯一。 |

AI Hub host base URL 與 Playground origin 記錄在 repository 根目錄的 `.env`。部署流程會從 `.env` 讀取 `AI_HUB_BASE_URL`，並同步到 App Service。`PLAYGROUND_SECRET_KEY` 會沿用既有 App Service setting；第一次部署時，流程會在 Azure 端產生一次並寫入 App Service。模型 endpoint 和 API key 建議放在 Key Vault，由 App Service 的受控身分在執行時讀取。

## Azure 登入設定

在 Azure 建立 Entra application / service principal，並設定 GitHub repository 可以透過 OIDC 登入 Azure。Subject 可依環境調整，常見設定為：

```text
repo:R300-AI/Agentic-SDK:ref:refs/heads/main
```

這個 service principal 需要能建立或更新 Resource Group、Linux App Service Plan、App Service、Key Vault，以及 Key Vault role assignment。權限可以依組織政策拆分；PoC 階段通常會先在目標 resource group scope 授予 Contributor，並在 Key Vault scope 授予可管理 role assignment 的權限。

## Workflow 行為

部署流程會：

1. 使用 GitHub OIDC 登入 Azure。
2. 可重複執行地建立 Resource Group、Linux App Service Plan、Python 3.12 App Service、Key Vault。
3. 啟用 App Service 受控身分，並授予 Key Vault Secrets User。
4. 設定 App Service 啟動指令：

```bash
python -m playground.main
```

5. 設定 `PORT=8000`、`WEBSITES_PORT=8000`、`SCM_DO_BUILD_DURING_DEPLOYMENT=false`、`ENABLE_ORYX_BUILD=false`、`PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages:/home/site/wwwroot`、`KEY_VAULT_NAME`、`AI_HUB_PLAYGROUND_ORIGIN`、從 `.env` 讀取的 `AI_HUB_BASE_URL`，並沿用或建立 `PLAYGROUND_SECRET_KEY`。Azure App Service 對外由平台提供 HTTP/HTTPS 80/443，容器內由 `PORT=8000` 接收流量。
6. 在 GitHub Actions runner 上安裝 Python dependencies 到 `.python_packages/lib/site-packages`，並用 FastAPI TestClient 基本檢查 `/healthz`、`/playground`、`/playground/builder`。
7. 打包 `agentic_sdk/`、`playground/`、`.python_packages/`、`.env`、`requirements.txt` 為 `deploy.zip`。
8. 使用 `azure/webapps-deploy` 部署到 App Service。
9. 部署 zip 後 restart App Service，讓 Python worker 載入新的 route map。
10. 對 `/playground`、`/playground/agents`、`/playground/builder` 做重試檢查。部署驗證確認服務入口可回應；產品文案、版面、靜態資源細節與 Builder 匯出 source 的細部規格由 Playground 測試負責。

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