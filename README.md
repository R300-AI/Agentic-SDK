# Agentic SDK

> **邊緣叢集管理協定**:把上游已認證的「模型 × 國產晶片」組合,延伸為支援 Perceive / Plan / Retrieve / Reflect / Action 五節點工作流的 Agentic 編排層,並對外維持單一 OpenAI 相容 API。

當前狀態:**Phase 3 完成** — Gateway `/v1/chat/completions` 已接上 Workflow,五節點端對端可用;Multi-Model Dashboard 可即時觀察節點進度。完整施工進度見 [blueprint/README.md](blueprint/README.md)。

---

## 兩種啟動模式

| 模式 | 用途 | Action 上游 | 需要 AMD Ryzen AI 機台? |
|------|------|------------|------------------------|
| **A. 本機開發(Foundry-only)** | 開發、單元驗證、不便上機台時 | Azure AI Foundry | 否 |
| **B. 正式部署(Upstream + Foundry)** | 對齊產品形態,Action 走 NPU | AMD NPU(`amd-ryzen-ai-benchmark/api.py`) | 是 |

兩種模式共用相同的 Gateway 與 Workflow,差別只在 `.env` 的 `WORKFLOW_ACTION_BACKEND` 一個開關。建議先用模式 A 把開發環境跑通,再上 Ryzen AI 主機驗模式 B。

---

## 模式 A:本機開發(Foundry-only)

> **適用對象**:在自己的開發機(Windows / Mac / Linux 皆可)驗證 Agentic SDK 行為,不需要 NPU 推論硬體。
> **環境前提**:Python 3.12、`uv`、可連到 Azure AI Foundry 的 API key。

```powershell
git clone https://github.com/<your-org>/Agentic-SDK.git
cd Agentic-SDK
git submodule update --init      # 把 .claude/ 拉下來

uv sync --extra dev               # 安裝依賴(uv 會自備 Python 3.12 + .venv)

Copy-Item .env.example .env
```

編輯 `.env`,只需動兩處:

```ini
# 把 Action 切到 Foundry,免架上游
WORKFLOW_ACTION_BACKEND=foundry

# 填入專案維護者提供的 Azure AI Foundry 認證
AZURE_FOUNDRY_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_FOUNDRY_API_KEY=<由專案維護者提供>
AZURE_FOUNDRY_DEPLOYMENT=gpt-4o-mini
```

啟動 Gateway 與 Dashboard:

```powershell
.\scripts\start.ps1               # Gateway @ 8080,Dashboard @ 8501
```

一鍵驗證(另開 PowerShell):

```powershell
uv run python scripts\smoke_chat.py
```

預期輸出包含:模型回覆內容、`x-agentic-metadata` header(`workflow_id` / `visit_counts` / `aborted`)、token usage。同時 Dashboard 會出現一條 `perceive → plan → retrieve → plan → action → reflect` 的時間序列。

> 健康檢查:`http://127.0.0.1:8080/healthz`(模式 A 不會檢查 AMD 上游)。
> Gateway 是 API server,直接用瀏覽器打 `localhost:8080` 會回 `Not Found`,屬正常。

---

## 模式 B:正式部署(Upstream + Foundry)

> **適用對象**:在 AMD Ryzen AI 主機上對齊產品形態,Action 走 NPU。
> **環境前提**:模式 A 的所有條件 + AMD Ryzen AI Software 1.7.1 + 已備好 `amd-ryzen-ai-benchmark`。

### 第一步:依上游 README 啟動推論伺服器

```powershell
conda activate ryzen-ai-1.7.1
cd <path to amd-ryzen-ai-benchmark>
python api.py --model gemma3-4b-npu
```

預期 `curl http://localhost:8000/v1/models` 回傳 `gemma3-4b-npu`。上游不是本專案維護範圍,所有 NPU / iGPU 環境細節以上游 README 為準。

### 第二步:啟動 Gateway 與 Dashboard

跟模式 A 一樣裝好依賴與 `.env`,但保留 `WORKFLOW_ACTION_BACKEND=upstream`(預設值);Azure Foundry 認證仍需填(Plan / Reflect 使用)。

```powershell
.\scripts\start.ps1
```

預期(60 秒內):

- `http://localhost:8080/v1/models` 回傳上游模型清單
- 啟動日誌出現 AMD 與 Azure Foundry 兩條 inference path 的 healthcheck 通過訊息
- Dashboard「節點存活拓樸」面板同時顯示兩條 inference path 狀態

### 第三步:用 OpenAI SDK 跑一次五節點工作流

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")
response = client.with_raw_response.chat.completions.create(
    model="gemma3-4b-npu",
    messages=[{"role": "user", "content": "幫我查 2024Q4 的銷售報表並摘要"}],
)
completion = response.parse()
print(completion.choices[0].message.content)
print(response.http_response.headers["x-agentic-metadata"])
```

預期結果:

- 回應為標準 OpenAI ChatCompletion 形態
- `x-agentic-metadata` header 內含 `workflow_id` / `visit_counts` / `aborted` / `abort_reason`
- Dashboard 兩個面板(節點時間序列、推論指標時序圖)出現對應資料點

---

## 模式 C:多基台驗收(M4-1~M4-3)

> **適用對象**:已備好 Ryzen AI 主機 + Azure Foundry 認證,想一次驗證「node 屬性決定 backend」的多基台拓樸。
> **驗證重點**:Action node 可獨立指向 Ryzen 上的 Gemma3 或 Azure Foundry,Gateway 拓樸與 Workflow 五節點順序不變。

### 第一步:Ryzen 機器上起 Gemma3 推論

```powershell
conda activate ryzen-ai-1.7.1
cd <path to amd-ryzen-ai-benchmark>
python api.py --model gemma-3-4b-it
```

`curl http://127.0.0.1:8000/v1/models` 應回傳含 `gemma-3-4b-it` 的清單。

### 第二步:同機 clone Agentic SDK 並裝依賴

```powershell
git clone https://github.com/<your-org>/Agentic-SDK.git
cd Agentic-SDK
git submodule update --init
uv sync --extra dev
Copy-Item .env.example .env
# 編輯 .env 填入 AZURE_FOUNDRY_ENDPOINT / AZURE_FOUNDRY_API_KEY / AZURE_FOUNDRY_DEPLOYMENT
```

### 第三步:跑多基台 demo

```powershell
# 預設值:RYZEN_UPSTREAM_BASE_URL=http://127.0.0.1:8000/v1,RYZEN_MODEL=gemma-3-4b-it
uv run python scripts\demo_multi_backend.py "請用一句話自我介紹"
```

腳本會:

1. 用 `UpstreamCompletionAction(base_url=...)` 跑一次 Ryzen + Gemma3 工作流
2. 用 `FoundryCompletionAction(client=AzureOpenAI(...))` 跑一次 Azure Foundry 工作流
3. 比對兩次的 context entry 結構是否一致(驗證跨 backend 上下文 schema 不變)
4. 輸出結構化報告至 `docs/quickstart-runs/multi-backend-<timestamp>.json`

### 第四步:把報告推回 GitHub 共同檢視

```powershell
git checkout -b verify/m4-multi-backend-$(Get-Date -Format yyyyMMdd)
git add docs/quickstart-runs/multi-backend-*.json
git commit -m "M4 multi-backend verification run"
git push origin HEAD
```

開 PR 後,協作者拉下來打開 `multi-backend-*.json` 就能看到兩個 backend 的回應、耗時、節點訪問計數,作為 M4-1~M4-3 的書面證據。

---

## 選用工具

### 不啟 Dashboard 只起 Gateway

```powershell
.\scripts\start.ps1 -GatewayOnly
```

### 用 Mock Foundry 跑一次離線 demo

```powershell
uv run python scripts\demo_workflow.py
```

會用 Mock Foundry(無 Azure 配額亦可)與故意不可達的上游,跑完一次五節點工作流並印出節點事件序列,可用來驗證安裝與觀察 `workflow.node.start` / `finish` 事件 schema。

### 跑測試

```powershell
uv run pytest
```

Phase 3 完成時測試共 99 項(M4-6 WorkflowConfig + M4 多基台合計加 16 案),涵蓋:基礎層(`/healthz`、`/v1/models`、Settings)、觀測層(事件 schema、RingBuffer、`/internal/telemetry/snapshot`)、Dashboard、Workflow 五節點端對端、Workflow 與 Gateway 的整合驗收(M3-2 / M3-4)、WorkflowConfig 序列化 + Python SDK 注入、多基台拓樸(M4-1~M4-3)。

---

## 設計與施工文件

| 目錄 | 內容 | 何時看 |
|------|------|--------|
| [docs/](docs/README.md) | 系統設計(What & Why):五節點對齊表、上下文管理、遙測契約、API reference | 想理解架構決策時 |
| [blueprint/](blueprint/README.md) | 施工藍圖(How & When):兩條工作軸、M0–M5 里程碑、目錄結構、風險與決策紀錄 | 想認領工作項或追施工進度時 |
| [blueprint/target-quickstart.md](blueprint/target-quickstart.md) | 本 README 三步啟動的反推來源與驗收方式 | 想驗證 quickstart 是否退化時 |
| [.claude/](.claude/) | 協作預設規則(submodule,唯讀) | 跨專案套用 Connect AI style 時 |

---

## 上游與本專案的職責邊界

```
amd-ryzen-ai-benchmark           Agentic SDK(本專案)
─────────────────────            ──────────────────────
  Model Card 認證                   五節點工作流編排(Workflow)
  api.py(OpenAI 相容)   ◄─代理─    Gateway(:8080)
  AMD NPU 推論                ◄─直連─ Action 節點(走 openai SDK,不過 Gateway)
                                    Active Context 管理
                                    遙測 / Multi-Model Dashboard
                                    Plan / Reflect 直接呼叫 Azure Foundry
                                    (不過 Gateway 代理;無金鑰時自動降為 Mock)
```

依賴方向永遠由本專案指向上游;Gateway 不修改上游、不為上游加 patch。詳見 [docs/01-architecture/microservices-design.md](docs/01-architecture/microservices-design.md)。

---

## 授權

MIT License。
