# Agentic SDK

> **邊緣叢集管理協定**：為通過 SLA 認證的「模型 × 國產晶片」組合提供跨節點 Agentic 工作流編排，並對外維持單一 OpenAI 相容 API。

---

## 架構概覽

```
使用者瀏覽器
    │
    ▼
Azure App Service（FastAPI Gateway + React 前端）
    │  執行時讀取
    ▼
Azure Key Vault（模型端點 Registry）
    │  推論請求
    ▼
Azure AI Foundry（模型部署）
```

- **前端**：React + Vite，build 後由 FastAPI 靜態 serve，與後端同一個 App Service。
- **後端**：FastAPI Gateway，部署於 Azure App Service，對外提供 OpenAI 相容 API。
- **模型端點 Registry**：Azure Key Vault，統一管理所有模型的 endpoint / key / deployment，Gateway 啟動時自動掃描。
- **推論後端**：Azure AI Foundry，支援多模型橫向部署。

---

## 快速上手（使用者）

直接開啟 Playground，無需任何本機設定：

👉 **[https://agentic-sdk-playground.azurewebsites.net](https://agentic-sdk-playground.azurewebsites.net)**

---

## 快速上手（本機開發）

### 前置需求

| 工具 | 版本 | 安裝 |
|---|---|---|
| Python | 3.12+ | 由 `uv` 代管，不必另裝 |
| `uv` | 最新版 | `winget install astral-sh.uv` |
| Node.js | 22+ | `winget install OpenJS.NodeJS.LTS` |

### 安裝

```bash
git clone https://github.com/R300-AI/Agentic-SDK.git
cd Agentic-SDK

# Python 環境
uv sync --extra dev

# 前端套件
cd demo && npm ci && cd ..
```

### 啟動 Gateway（本機）

```bash
uv run python -m agentic_sdk.gateway
```

Gateway 預設監聽 `http://127.0.0.1:8080`。健康確認：

```bash
curl http://127.0.0.1:8080/healthz
```

### 啟動前端（本機，連本機 Gateway）

```bash
cd demo
npm run dev
```

瀏覽器開啟 [http://localhost:5173](http://localhost:5173)。

> 本機 Gateway 需設定環境變數（`AZURE_FOUNDRY_ENDPOINT`、`AZURE_FOUNDRY_API_KEY`、`AZURE_FOUNDRY_DEPLOYMENT`），或改用 `WORKFLOW_FORCE_MOCK_FOUNDRY=true` 離線執行。

### 執行前端型別檢查

```bash
cd demo
npx tsc --noEmit
npm test   # vitest
```

### 呼叫 Gateway（OpenAI SDK 相容）

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "你好"}],
)
print(response.choices[0].message.content)
```

---

## 部署與維運

| 文件 | 說明 |
|---|---|
| [docs/github_cicd_workflow.md](docs/github_cicd_workflow.md) | CI/CD 初次設定：OIDC、GitHub Variables |
| [docs/setup_default_models.md](docs/setup_default_models.md) | 新增 / 修改 / 移除模型端點（Azure AI Foundry + Key Vault） |

---

## 上游職責邊界

| 子系統 | 儲存庫 | 職責 |
|---|---|---|
| **SLA 認證閘道** | [`R300-AI/amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) | 為「模型 × 晶片」組合產出可驗證的 SLA 履歷 |
| **Agentic SDK（本專案）** | `R300-AI/Agentic-SDK` | 消費通過認證的模型，提供跨節點工作流編排與 OpenAI 相容 API |

---

## 授權

MIT License。
