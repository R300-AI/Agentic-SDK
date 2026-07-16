# 新增與管理預設模型（OpenAI-compatible Endpoint + Key Vault）

本指南說明如何為 Agentic SDK Playground 新增、修改或移除預設模型。
所有模型端點資訊統一存放於您在 GitHub Variables 中指定的 Key Vault，
Gateway 啟動時自動掃描並組成可用模型池，對應前端模型選單。

完成首次新增模型約需 **15 分鐘**。

---

## 事前準備

本指南所使用的 Azure 資源由本專案的 GitHub CI/CD 工作流程自動部署建立。
在繼續之前，請確認工作流程至少已成功執行一次，且以下資源已存在於您指定的資源群組下：

| 資源類型 | 本專案使用的名稱 |
|---|---|
| Key Vault | 您在 `AZURE_RESOURCE_GROUP` 中指定的資源群組內的 Key Vault（`agentic-sdk-models`） |
| App Service | 您在 `AZURE_WEBAPP_NAME` 中指定的 App Service（`agentic-sdk-playground`） |

> 若上述資源尚不存在，請先完成 [GitHub CI/CD 工作流程說明](github_cicd_workflow.md) 中的初次設定，再回到本指南。

開始之前，請確認：

- 您擁有存取 Azure 訂閱的權限
- 您的帳號已被授予上述 Key Vault 的 **Key Vault Secrets Officer** 角色

  若尚未取得，請訂閱管理員依下列步驟授予：

  1. 前往 [Azure Portal](https://portal.azure.com)，搜尋並開啟 Key Vault **`agentic-sdk-models`**。
  2. 選取左側 **Access control (IAM)**，再選取 **+ Add → Add role assignment**。
  3. 在 **Role** 分頁搜尋並選取 **Key Vault Secrets Officer**，選取 **Next**。
  4. 在 **Members** 分頁，選取 **+ Select members**，搜尋並選取需要授權的使用者帳號。
  5. 選取 **Review + assign**，完成授權（角色傳播約需 1–2 分鐘）。

---

## 第一節：準備 OpenAI-compatible 模型端點

1. 準備一個可被 `from openai import OpenAI` 直接呼叫的模型端點。

2. 確認您已取得以下三項資訊：

   - **Base URL**（例如 `http://localhost:11434/v1` 或其他 OpenAI-compatible endpoint）
   - **API Key**（若端點不需要，可用 `not-needed`）
   - **Model 名稱**（例如 `gpt-4o-mini`、`llama3.1:8b`）

---

## 第二節：在 Key Vault 新增模型 Secret

每個模型由四個 secret 組成，命名規則為 `model-{id}-{欄位}`，
其中 `{id}` 為您自訂的小寫英數字識別碼（如 `phi4`、`gpt4o`）。

### 步驟 2-1：前往 Key Vault

1. 開啟 [Azure Portal](https://portal.azure.com)。

2. 在頂部搜尋列輸入您指定的 Key Vault 名稱（本專案為 `agentic-sdk-models`），選取搜尋結果中的 **Key vault**。

3. 在左側導覽列選取 **Secrets**。

### 步驟 2-2：新增 `model-{id}-name`（顯示名稱）

1. 選取 **+ Generate/Import**。

2. 填入以下欄位：

   - **Upload options**：**Manual**
   - **Name**：`model-{id}-name`（將 `{id}` 換成您的識別碼，如 `model-phi4-name`）
   - **Secret value**：模型在前端顯示的名稱（如 `Phi-4`）

3. 選取 **Create**。

### 步驟 2-3：新增 `model-{id}-base-url`

1. 再次選取 **+ Generate/Import**。

2. 填入：

   - **Name**：`model-{id}-base-url`
   - **Secret value**：第一節準備的 **Base URL**

3. 選取 **Create**。

### 步驟 2-4：新增 `model-{id}-key`

1. 選取 **+ Generate/Import**。

2. 填入：

   - **Name**：`model-{id}-key`
   - **Secret value**：第一節準備的 **API Key**

3. 選取 **Create**。

### 步驟 2-5：新增 `model-{id}-model`

1. 選取 **+ Generate/Import**。

2. 填入：

   - **Name**：`model-{id}-model`
   - **Secret value**：第一節準備的 **Model 名稱**（如 `gpt-4o-mini`）

3. 選取 **Create**。

完成後，**Secrets** 清單中應出現四筆以 `model-{id}-` 開頭的 secret。

---

## 第三節：驗證模型是否生效

新增 secret 後，**不需要重新部署**，Gateway 下次冷啟動時會自動讀取。
若需要立即生效，請重啟 App Service：

1. 在 Azure Portal 搜尋您指定的 App Service 名稱（本專案為 `agentic-sdk-playground`），選取該 **App Service**。

2. 在左側導覽列選取 **Overview**。

3. 選取頂部的 **Restart**，確認提示後等待約 30 秒。

4. 前往前端網址，在模型選單中確認新模型已出現。

---

## 修改現有模型

1. 前往 Azure Portal，進入您指定的 Key Vault → **Secrets**。

2. 選取要修改的 secret（如 `model-phi4-base-url`）。

3. 選取 **+ New Version**。

4. 在 **Secret value** 填入新的值，選取 **Create**。

   > Key Vault 保留所有歷史版本，**Current version** 會自動切換為最新版本。

5. 重啟 App Service 以套用變更（參考[第三節](#第三節驗證模型是否生效)步驟 1–3）。

---

## 移除模型

1. 前往 Azure Portal，進入您指定的 Key Vault → **Secrets**。

2. 選取 `model-{id}-name`，選取 **Delete**，確認刪除。

3. 對 `model-{id}-base-url`、`model-{id}-key`、`model-{id}-model` 重複步驟 2。

   > **注意**：只要 `model-{id}-name` 存在，Gateway 就會嘗試讀取該模型的其餘三欄。
   > 四個 secret 需一併移除，否則 Gateway 啟動時會記錄讀取錯誤。

4. 重啟 App Service 以套用變更。

---

## 附錄：Secret 命名速查表

| Secret 名稱 | 內容範例 | 用途 |
|---|---|---|
| `model-{id}-name` | `Phi-4` | 前端顯示名稱 |
| `model-{id}-base-url` | `http://localhost:11434/v1` | OpenAI-compatible base URL |
| `model-{id}-key` | `BgNw...` | API 金鑰 |
| `model-{id}-model` | `gpt-4o-mini` | OpenAI-compatible model 名稱 |
