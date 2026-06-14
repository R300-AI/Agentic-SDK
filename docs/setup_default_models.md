# 新增與管理預設模型（Azure AI Foundry + Key Vault）

本指南說明如何為 Agentic SDK Playground 新增、修改或移除預設模型。
所有模型端點資訊統一存放於 Azure Key Vault（**agentic-sdk-model-registry**），
Playground 啟動時自動掃描並組成可用的模型池，對應前端模型選單。

---

## 事前準備

本指南所使用的 Azure 資源已由訂閱管理員預先建立於資源群組 **agentic-sdk** 下：

| 資源類型 | 名稱 |
|---|---|
| Key Vault | **agentic-sdk-model-registry** |
| App Service | **agentic-sdk-playground** |

> 若上述資源尚不存在，請聯繫訂閱管理員，依 `.github/azure-deploy-config.yml` 中的建立指令完成初始化後再繼續。

開始之前，請確認：

- 您擁有 Azure 訂閱 **eosl-r3-aihub** 的存取權
- 您的帳號已被授予 Key Vault **agentic-sdk-model-registry** 的 **Key Vault Secrets Officer** 角色（如尚未取得，請聯繫訂閱管理員）
- 您已有一個 Azure AI Foundry 專案（Hub）可供部署模型

---

## 第一節：在 Azure AI Foundry 部署模型

> 若模型已部署完畢並取得 endpoint，可跳至[第二節](#第二節在-key-vault-新增模型-secret)。

1. 開啟瀏覽器，前往 [Azure AI Foundry](https://ai.azure.com)，並以您的 Azure 帳號登入。

2. 在左側導覽列選取 **Models + endpoints**，再選取 **Deploy model**。

3. 在模型清單中，選取您要部署的模型（如 **Phi-4** 或 **GPT-4o**），然後選取 **Confirm**。

4. 在部署設定頁面，填入以下欄位：

   - **Deployment name**：輸入一個辨識用的名稱（如 `phi-4`）。請記下此名稱，後續步驟會用到。
   - **Deployment type**：依需求選擇（建議選 **Standard**）
   - 其餘設定保持預設即可

5. 選取 **Deploy**，等待部署完成（約 1–3 分鐘）。

6. 部署完成後，在模型詳細頁面找到並記錄以下資訊：

   - **Target URI**（即 endpoint URL，格式為 `https://....inference.ai.azure.com/`）
   - **Key**（選取 **Show** 後複製）

   > **重要**：請妥善保存以上資訊，不要貼入原始碼或任何公開文件。

---

## 第二節：在 Key Vault 新增模型 Secret

每個模型由四個 secret 組成，命名規則為 `model-{id}-{欄位}`，
其中 `{id}` 為您自訂的小寫英數字識別碼（如 `phi4`、`gpt4o`）。

### 步驟 2-1：前往 Key Vault

1. 開啟 [Azure Portal](https://portal.azure.com)。

2. 在頂部搜尋列輸入 `agentic-sdk-model-registry`，選取搜尋結果中的 **Key vault**。

3. 在左側導覽列選取 **Secrets**。

### 步驟 2-2：新增 `model-{id}-name`（顯示名稱）

1. 選取 **+ Generate/Import**。

2. 填入以下欄位：

   - **Upload options**：**Manual**
   - **Name**：`model-{id}-name`（將 `{id}` 換成您的識別碼，如 `model-phi4-name`）
   - **Secret value**：模型在前端顯示的名稱（如 `Phi-4`）

3. 選取 **Create**。

### 步驟 2-3：新增 `model-{id}-endpoint`

1. 再次選取 **+ Generate/Import**。

2. 填入：

   - **Name**：`model-{id}-endpoint`
   - **Secret value**：從第一節複製的 **Target URI**

3. 選取 **Create**。

### 步驟 2-4：新增 `model-{id}-key`

1. 選取 **+ Generate/Import**。

2. 填入：

   - **Name**：`model-{id}-key`
   - **Secret value**：從第一節複製的 **Key**

3. 選取 **Create**。

### 步驟 2-5：新增 `model-{id}-deployment`

1. 選取 **+ Generate/Import**。

2. 填入：

   - **Name**：`model-{id}-deployment`
   - **Secret value**：第一節步驟 4 設定的 **Deployment name**（如 `phi-4`）

3. 選取 **Create**。

完成後，**Secrets** 清單中應出現四筆以 `model-{id}-` 開頭的 secret。

---

## 第三節：驗證模型是否生效

新增 secret 後，**不需要重新部署**，Gateway 下次冷啟動時會自動讀取。
若需要立即生效，請重啟 App Service：

1. 在 Azure Portal 搜尋 **agentic-sdk-playground**，選取該 **App Service**。

2. 在左側導覽列選取 **Overview**。

3. 選取頂部的 **Restart**，確認提示後等待約 30 秒。

4. 前往前端網址（`https://r300-ai.github.io/Agentic-SDK/`），
   在模型選單中確認新模型已出現。

---

## 修改現有模型

1. 前往 **Key Vault** → **agentic-sdk-model-registry** → **Secrets**。

2. 選取要修改的 secret（如 `model-phi4-endpoint`）。

3. 選取 **+ New Version**。

4. 在 **Secret value** 填入新的值，選取 **Create**。

   > Key Vault 保留所有歷史版本，**Current version** 會自動切換為最新版本。

5. 重啟 App Service 以套用變更（參考[第三節](#第三節驗證模型是否生效)步驟 1–3）。

---

## 移除模型

1. 前往 **Key Vault** → **agentic-sdk-model-registry** → **Secrets**。

2. 選取 `model-{id}-name`，選取 **Delete**，確認刪除。

3. 對 `model-{id}-endpoint`、`model-{id}-key`、`model-{id}-deployment` 重複步驟 2。

   > **注意**：只要 `model-{id}-name` 存在，Gateway 就會嘗試讀取該模型的其餘三欄。
   > 四個 secret 需一併移除，否則 Gateway 啟動時會記錄讀取錯誤。

4. 重啟 App Service 以套用變更。

---

## 附錄：Secret 命名速查表

| Secret 名稱 | 內容範例 | 用途 |
|---|---|---|
| `model-{id}-name` | `Phi-4` | 前端顯示名稱 |
| `model-{id}-endpoint` | `https://xxx.inference.ai.azure.com/` | Foundry endpoint |
| `model-{id}-key` | `sk-...` | API 金鑰 |
| `model-{id}-deployment` | `phi-4` | Foundry 部署名稱 |
