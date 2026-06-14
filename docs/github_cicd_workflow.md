# GitHub CI/CD 工作流程說明

本文件說明 Agentic SDK 的自動化部署架構，包含初次設定步驟、工作流程結構，
以及各 Azure 資源的建立時機與方式。

---

## 概覽

每次推送至 **main** 分支，工作流程會依序執行三個階段：

```
推送至 main
    │
    ▼
[1] deploy-gateway
    ├─ 以 OIDC 登入 Azure（無密碼）
    ├─ 確保 Azure 資源存在（App Service Plan、App Service、Key Vault）
    └─ 部署 Python 後端至 App Service
    │
    ▼
[2] build-pages
    └─ 以固定 Gateway URL 建置 Vite 前端
    │
    ▼
[3] deploy-pages
    └─ 發佈至 GitHub Pages
```

前端 URL：`https://r300-ai.github.io/Agentic-SDK/`
後端 URL：`https://agentic-sdk-playground.azurewebsites.net`

所有部署參數集中定義於 `.github/azure-deploy-config.yml`。

---

## 第一節：初次設定（一次性）

初次使用前，需在 Azure 與 GitHub 各完成一次性設定，讓工作流程取得部署權限。

### 步驟 1-1：建立 App Registration（OIDC 身分）

GitHub Actions 透過 OIDC（OpenID Connect）向 Azure 驗證身分，不需要任何密碼。

1. 前往 [Azure Portal](https://portal.azure.com)，在頂部搜尋列輸入 **App registrations**，選取搜尋結果。

2. 選取 **+ New registration**，填入：

   - **Name**：`agentic-sdk-github-actions`
   - **Supported account types**：**Accounts in this organizational directory only**

3. 選取 **Register**。

4. 建立完成後，記錄頁面上的以下兩個值（稍後設定 GitHub Variables 會用到）：

   - **Application (client) ID**
   - **Directory (tenant) ID**

### 步驟 1-2：建立 Federated Credential

1. 在 App registration 頁面，選取左側 **Certificates & secrets**。

2. 選取 **Federated credentials** 分頁，再選取 **+ Add credential**。

3. 在 **Federated credential scenario** 下拉選單選取 **GitHub Actions deploying Azure resources**。

4. 填入以下欄位：

   - **Organization**：`R300-AI`
   - **Repository**：`Agentic-SDK`
   - **Entity type**：**Branch**
   - **GitHub branch name**：`main`
   - **Name**：`agentic-sdk-main-branch`

5. 選取 **Add**。

### 步驟 1-3：授予資源群組的 Contributor 角色

1. 在 Azure Portal 搜尋 **Resource groups**，選取 **agentic-sdk**。

2. 選取左側 **Access control (IAM)**，再選取 **+ Add** → **Add role assignment**。

3. 在 **Role** 分頁，搜尋並選取 **Contributor**，選取 **Next**。

4. 在 **Members** 分頁：
   - **Assign access to**：**User, group, or service principal**
   - 選取 **+ Select members**，搜尋 `agentic-sdk-github-actions`，選取後確認

5. 選取 **Review + assign**，完成授權。

### 步驟 1-4：取得訂閱 ID

1. 在 Azure Portal 搜尋 **Subscriptions**，選取 **eosl-r3-aihub**。

2. 記錄 **Subscription ID**（GUID 格式）。

### 步驟 1-5：在 GitHub 設定 Repository Variables

1. 前往 GitHub 儲存庫 `R300-AI/Agentic-SDK`。

2. 選取 **Settings** → **Secrets and variables** → **Actions**。

3. 選取 **Variables** 分頁（注意：是 Variables，不是 Secrets）。

4. 依序選取 **New repository variable**，新增以下七個變數：

   **OIDC 身分驗證（值來自步驟 1-1 與 1-4）：**

   | 變數名稱 | 值 |
   |---|---|
   | **AZURE_CLIENT_ID** | 步驟 1-1 取得的 Application (client) ID |
   | **AZURE_TENANT_ID** | 步驟 1-1 取得的 Directory (tenant) ID |
   | **AZURE_SUBSCRIPTION_ID** | 步驟 1-4 取得的 Subscription ID |

   **部署目標參數：**

   | 變數名稱 | 值 |
   |---|---|
   | **AZURE_WEBAPP_NAME** | `agentic-sdk-playground` |
   | **AZURE_RESOURCE_GROUP** | `agentic-sdk` |
   | **GATEWAY_URL** | `https://agentic-sdk-playground.azurewebsites.net` |
   | **CORS_ORIGINS** | `https://r300-ai.github.io,http://localhost:5173` |

---

## 第二節：工作流程詳細說明

### deploy-gateway 階段

| 步驟 | 說明 |
|---|---|
| Azure 登入（OIDC） | 使用 `vars.AZURE_CLIENT_ID` 等三個 Variables 取得存取權杖，無需密碼 |
| 產生 requirements.txt | 以 `uv pip compile pyproject.toml` 鎖定所有相依版本 |
| 部署至 App Service | `azure/webapps-deploy@v3` 上傳原始碼，Oryx 在伺服器端執行 `pip install` |
| 設定 appsettings | 寫入非敏感執行參數（PORT、CORS、KEY_VAULT_NAME 等）|

> **敏感資料（Foundry API key）不經過 CI/CD**。
> App Service 在 runtime 透過 Managed Identity 直接從 Key Vault 讀取，
> 詳見 [setup_default_models.md](setup_default_models.md)。

### build-pages 階段

Gateway URL 固定為 `https://agentic-sdk-playground.azurewebsites.net`，
在 `VITE_GATEWAY_URL` 環境變數 bake 進前端靜態資源後，上傳為 Pages artifact。

### deploy-pages 階段

使用 GitHub 原生 Pages 部署動作，需在儲存庫 **Settings → Pages** 將
**Source** 設為 **GitHub Actions**（一次性設定）。

---

## 第三節：Azure 資源建立時機

| 資源 | 建立時機 | 建立方式 |
|---|---|---|
| Resource Group **agentic-sdk** | 工作流程執行前 | Azure Portal 手動建立 |
| App Service Plan **agentic-sdk-plan** | 工作流程執行前 | Azure Portal 手動建立 |
| App Service **agentic-sdk-playground** | 工作流程執行前 | Azure Portal 手動建立，並開啟 System Managed Identity |
| Key Vault **agentic-sdk-model-registry** | 工作流程執行前 | Azure Portal 手動建立，並授予 App Service MI 讀取權限 |
| 模型 endpoint secrets | 按需手動新增 | Azure Portal，詳見 [setup_default_models.md](setup_default_models.md) |

> 資源的命名與規格定義於 `.github/azure-deploy-config.yml`，
> 請依該檔案的規格建立，確保與工作流程參數一致。

### 建立 Resource Group

1. 在 Azure Portal 搜尋 **Resource groups**，選取 **+ Create**。
2. 填入：**Subscription** 選 `eosl-r3-aihub`、**Resource group** 填 `agentic-sdk`、**Region** 選 **Southeast Asia**。
3. 選取 **Review + create** → **Create**。

### 建立 App Service Plan

1. 搜尋 **App Service plans**，選取 **+ Create**。
2. 填入：**Resource group** 選 `agentic-sdk`、**Name** 填 `agentic-sdk-plan`、**Operating System** 選 **Linux**、**Region** 選 **Southeast Asia**、**Pricing plan** 選 **B2**。
3. 選取 **Review + create** → **Create**。

### 建立 App Service 並開啟 Managed Identity

1. 搜尋 **App Services**，選取 **+ Create** → **Web App**。
2. 填入：**Resource group** 選 `agentic-sdk`、**Name** 填 `agentic-sdk-playground`、**Runtime stack** 選 **Python 3.12**、**Region** 選 **Southeast Asia**、**Linux Plan** 選 `agentic-sdk-plan`。
3. 選取 **Review + create** → **Create**。
4. 建立完成後進入 App Service，選取左側 **Identity**。
5. 在 **System assigned** 分頁，將 **Status** 切換為 **On**，選取 **Save**。
6. 記錄頁面顯示的 **Object (principal) ID**，後續授予 Key Vault 存取權時會用到。

### 建立 Key Vault 並授予 App Service 讀取權限

1. 搜尋 **Key vaults**，選取 **+ Create**。
2. 填入：**Resource group** 選 `agentic-sdk`、**Key vault name** 填 `agentic-sdk-model-registry`、**Region** 選 **Southeast Asia**、**Pricing tier** 選 **Standard**。
3. 選取 **Review + create** → **Create**。
4. 建立完成後進入 Key Vault，選取左側 **Access control (IAM)**，再選取 **+ Add** → **Add role assignment**。
5. 選取 **Key Vault Secrets User** 角色，**Next**。
6. **Assign access to** 選 **Managed identity**，選取 **+ Select members**。
7. 在 **Managed identity** 下拉選取 **App Service**，找到 `agentic-sdk-playground` 後選取，確認。
8. 選取 **Review + assign**，完成授權。

---

## 附錄：工作流程檔案對應

| 檔案 | 用途 |
|---|---|
| `.github/workflows/deploy-gateway.yml` | 主工作流程：三階段串聯部署 |
| `.github/workflows/deploy-pages.yml` | 緊急備用：僅重新部署前端（手動觸發） |
| `.github/workflows/ci.yml` | 每次 PR/push 執行 Python 測試與 TypeScript 型別檢查 |
| `.github/azure-deploy-config.yml` | 所有 Azure 部署參數的唯一來源 |
