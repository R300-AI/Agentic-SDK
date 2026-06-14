# GitHub CI/CD 工作流程說明

本文件說明 Agentic SDK 的自動化部署架構，包含初次設定步驟、工作流程結構，
以及各 Azure 資源的建立方式。

完成初次設定約需 **20 分鐘**。

---

## 事前準備

開始之前，請確認：

- 您擁有一個 Azure 訂閱，且角色為 **Owner** 或 **Contributor**
- 您擁有該訂閱的 Azure Active Directory 存取權，可建立 **App Registration**
- 您擁有 GitHub 儲存庫 `R300-AI/Agentic-SDK` 的 **Admin** 權限（用於設定 Repository Variables）

> **本專案目前使用的訂閱為 `eosl-r3-aihub`。** 若您使用不同訂閱，後續步驟中所有涉及訂閱的選擇，請以您自己的訂閱取代。

---

## 概覽

每次推送至 **main** 分支，工作流程會依序執行三個階段：

```
推送至 main
    │
    ▼
[1] deploy-gateway ── 以 OIDC 登入您指定的 Azure 訂閱
    └─ 部署 Python 後端至您指定的 App Service
    │
    ▼
[2] build-pages ── 以您設定的 Gateway URL 建置 Vite 前端
    │
    ▼
[3] deploy-pages ── 發佈至 GitHub Pages
```

所有部署目標（App Service 名稱、Resource Group、URL 等）均來自您在 GitHub Repository Variables 中設定的值，設定步驟見[第三節](#第三節設定-github-repository-variables)。

---

## 第一節：建立 Azure 資源（初次設定）

工作流程執行前，需先手動建立以下資源。資源的命名請與您稍後在 GitHub Variables 中填入的值保持一致。

### 步驟 1-1：建立 Resource Group

1. 前往 [Azure Portal](https://portal.azure.com)，在頂部搜尋列輸入 **Resource groups**，選取搜尋結果。

2. 選取 **+ Create**，填入：

   - **Subscription**：選取您的 Azure 訂閱
   - **Resource group**：輸入您為此專案指定的名稱（本專案使用 `agentic-sdk`）
   - **Region**：選取 **Southeast Asia**（或您偏好的區域）

3. 選取 **Review + create** → **Create**。

### 步驟 1-2：建立 App Service Plan

1. 在頂部搜尋列輸入 **App Service plans**，選取搜尋結果。

2. 選取 **+ Create**，填入：

   - **Subscription**：選取您的 Azure 訂閱
   - **Resource group**：選取步驟 1-1 建立的資源群組
   - **Name**：輸入 Plan 名稱（本專案使用 `agentic-sdk-plan`）
   - **Operating System**：**Linux**
   - **Region**：與 Resource Group 相同
   - **Pricing plan**：**B2**

3. 選取 **Review + create** → **Create**。

### 步驟 1-3：建立 App Service 並開啟 Managed Identity

1. 在頂部搜尋列輸入 **App Services**，選取搜尋結果。

2. 選取 **+ Create** → **Web App**，填入：

   - **Subscription**：選取您的 Azure 訂閱
   - **Resource group**：選取步驟 1-1 建立的資源群組
   - **Name**：輸入您為後端指定的名稱（本專案使用 `agentic-sdk-playground`）
   - **Runtime stack**：**Python 3.12**
   - **Region**：與 Resource Group 相同
   - **Linux Plan**：選取步驟 1-2 建立的 App Service Plan

3. 選取 **Review + create** → **Create**。

4. 建立完成後，進入該 App Service，選取左側 **Identity**。

5. 在 **System assigned** 分頁，將 **Status** 切換為 **On**，選取 **Save**。

6. 記錄頁面顯示的 **Object (principal) ID**，下一步驟授予 Key Vault 存取權時會用到。

### 步驟 1-4：建立 Key Vault 並授予 App Service 讀取權限

Key Vault 作為模型端點的集中儲存庫。App Service 透過 Managed Identity 在執行時讀取其中的 secret，金鑰不經過 CI/CD。

1. 在頂部搜尋列輸入 **Key vaults**，選取搜尋結果。

2. 選取 **+ Create**，填入：

   - **Subscription**：選取您的 Azure 訂閱
   - **Resource group**：選取步驟 1-1 建立的資源群組
   - **Key vault name**：輸入您為模型儲存庫指定的名稱（本專案使用 `agentic-sdk-model-registry`）
   - **Region**：與 Resource Group 相同
   - **Pricing tier**：**Standard**

3. 選取 **Review + create** → **Create**。

4. 建立完成後，進入該 Key Vault，選取左側 **Access control (IAM)**。

5. 選取 **+ Add** → **Add role assignment**，在 **Role** 分頁選取 **Key Vault Secrets User**，選取 **Next**。

6. 在 **Members** 分頁，**Assign access to** 選取 **Managed identity**，選取 **+ Select members**。

7. 在 **Managed identity** 下拉選取 **App Service**，找到您在步驟 1-3 建立的 App Service，選取後確認。

8. 選取 **Review + assign**，完成授權。

---

## 第二節：設定 OIDC 身分驗證（初次設定）

GitHub Actions 透過 OIDC（OpenID Connect）向 Azure 驗證身分，無需儲存任何密碼。

### 步驟 2-1：建立 App Registration

1. 在 Azure Portal 頂部搜尋列輸入 **App registrations**，選取搜尋結果。

2. 選取 **+ New registration**，填入：

   - **Name**：`agentic-sdk-github-actions`
   - **Supported account types**：**Accounts in this organizational directory only**

3. 選取 **Register**。

4. 建立完成後，記錄以下兩個值：

   - **Application (client) ID**
   - **Directory (tenant) ID**

### 步驟 2-2：建立 Federated Credential

1. 在 App registration 頁面，選取左側 **Certificates & secrets**。

2. 選取 **Federated credentials** 分頁，再選取 **+ Add credential**。

3. 在 **Federated credential scenario** 下拉選單選取 **GitHub Actions deploying Azure resources**，填入：

   - **Organization**：`R300-AI`
   - **Repository**：`Agentic-SDK`
   - **Entity type**：**Branch**
   - **GitHub branch name**：`main`
   - **Name**：`agentic-sdk-main-branch`

4. 選取 **Add**。

### 步驟 2-3：授予 Contributor 角色

1. 在 Azure Portal 搜尋 **Resource groups**，選取您在步驟 1-1 建立的資源群組。

2. 選取左側 **Access control (IAM)**，再選取 **+ Add** → **Add role assignment**。

3. 在 **Role** 分頁選取 **Contributor**，選取 **Next**。

4. 在 **Members** 分頁，**Assign access to** 選取 **User, group, or service principal**，選取 **+ Select members**，搜尋並選取 `agentic-sdk-github-actions`。

5. 選取 **Review + assign**，完成授權。

### 步驟 2-4：取得訂閱 ID

1. 在 Azure Portal 頂部搜尋列輸入 **Subscriptions**，選取搜尋結果。

2. 選取您使用的訂閱，記錄 **Subscription ID**（GUID 格式）。

---

## 第三節：設定 GitHub Repository Variables

所有部署參數統一存放於 GitHub Repository Variables，不寫入原始碼。

1. 前往 GitHub 儲存庫 `R300-AI/Agentic-SDK`，選取 **Settings**。

2. 在左側選取 **Secrets and variables** → **Actions**。

3. 選取 **Variables** 分頁，依序選取 **New repository variable**，新增以下七個變數：

   **OIDC 身分驗證（值來自第二節）：**

   | 變數名稱 | 值 |
   |---|---|
   | **AZURE_CLIENT_ID** | 步驟 2-1 取得的 Application (client) ID |
   | **AZURE_TENANT_ID** | 步驟 2-1 取得的 Directory (tenant) ID |
   | **AZURE_SUBSCRIPTION_ID** | 步驟 2-4 取得的 Subscription ID |

   **部署目標（值來自第一節建立的資源）：**

   | 變數名稱 | 值（本專案預設） |
   |---|---|
   | **AZURE_WEBAPP_NAME** | 您在步驟 1-3 指定的 App Service 名稱（`agentic-sdk-playground`） |
   | **AZURE_RESOURCE_GROUP** | 您在步驟 1-1 指定的資源群組名稱（`agentic-sdk`） |
   | **GATEWAY_URL** | `https://{您的 App Service 名稱}.azurewebsites.net` |
   | **CORS_ORIGINS** | `https://r300-ai.github.io,http://localhost:5173` |

4. 完成後，推送任何變更至 **main** 分支即可觸發工作流程。

---

## 第四節：啟用 GitHub Pages

1. 前往 GitHub 儲存庫 `R300-AI/Agentic-SDK`，選取 **Settings**。

2. 在左側選取 **Pages**。

3. 在 **Source** 下拉選單選取 **GitHub Actions**，選取 **Save**。

---

## 附錄：工作流程階段說明

| 階段 | 說明 |
|---|---|
| **deploy-gateway** | 以 OIDC 登入、產生 requirements.txt、部署原始碼、設定 App Service 執行參數 |
| **build-pages** | 以 `GATEWAY_URL` 建置 Vite 前端靜態資源 |
| **deploy-pages** | 發佈靜態資源至 GitHub Pages |

> 敏感資料（模型 API key）不經過 CI/CD，App Service 在執行時透過 Managed Identity 從 Key Vault 讀取。詳見 [setup_default_models.md](setup_default_models.md)。

## 附錄：工作流程檔案對應

| 檔案 | 用途 |
|---|---|
| `.github/workflows/deploy-gateway.yml` | 主工作流程：三階段串聯部署 |
| `.github/workflows/deploy-pages.yml` | 緊急備用：僅重新部署前端（手動觸發） |
| `.github/workflows/ci.yml` | 每次 PR/push 執行 Python 測試與 TypeScript 型別檢查 |
