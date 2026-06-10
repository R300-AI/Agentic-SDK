# Agentic SDK

> **邊緣叢集管理協定**：把上游已認證的「模型 × 國產晶片」組合，延伸為支援 Perceive / Plan / Retrieve / Reflect / Action 五節點工作流的 Agentic 編排層，並對外維持單一 OpenAI 相容 API。

當前狀態：**Phase 3 完成 + M4–M11 進行中** — Gateway `/v1/chat/completions` 已接上 Workflow，五節點端對端可用；圖形編輯器（`demo/`）可拖曳設計工作流並即時看到節點亮燈；Gateway `/v1/workflow/{id}/stream` 以 SSE 透出逐 token 串流事件（`workflow.node.delta`），長回覆只在「真的沒有新 token」時才會中止。69 個測試檔、158 項自動測試全綠。完整施工進度見 [blueprint/README.md](blueprint/README.md)。

---

## 三步上手（最小路徑）

> **目標**：在自己的開發機（Windows / macOS / Linux 任一）跑起 Gateway + 圖形編輯器，用瀏覽器拖曳工作流並按「跑一次」看到動畫。
> **不需要**：AMD Ryzen AI 主機、NPU、上游推論伺服器；Plan / Reflect / Action 都先走 Azure AI Foundry。

### 第一步：安裝必要工具

只需要四樣：Git、Python 3.12、`uv`、Node.js 22+。Azure AI Foundry 認證請向專案維護者索取。

| 工具 | Windows（建議用 winget） | macOS（建議用 Homebrew） | Linux（Debian / Ubuntu） |
|------|--------------------------|---------------------------|--------------------------|
| Git | `winget install Git.Git` | `brew install git` | `sudo apt install git` |
| Python 3.12 | 由 `uv` 代管，不必另裝 | 同左 | 同左 |
| `uv` | `winget install astral-sh.uv` | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js 22+ | `winget install OpenJS.NodeJS.LTS` | `brew install node@22` | 依官方步驟安裝 [NodeSource 22.x](https://github.com/nodesource/distributions) |

驗證安裝（任一平台終端機）：

```bash
git --version
uv --version
node --version    # 應為 v22.x 或以上
```

> macOS / Linux 使用者請把後續所有 `powershell` 指令改成等價的 `bash` 指令；`Copy-Item .env.example .env` 改為 `cp .env.example .env`，路徑分隔符以系統為準。腳本 `scripts/start.ps1` 目前僅支援 Windows，非 Windows 平台請參照第三步的「手動啟動」段落。

### 第二步：取得程式碼 + 安裝相依

```bash
git clone https://github.com/<your-org>/Agentic-SDK.git
cd Agentic-SDK
git submodule update --init       # 拉下 .claude/ 協作規範

# Python 端：uv 會自動裝 Python 3.12 + 建立 .venv
uv sync --extra dev

# 前端：進 demo/ 裝 npm 套件（首次約需 1 分鐘）
cd demo
npm install
cd ..
```

填 `.env`（只動三行即可跑起來）：

```bash
# Windows
Copy-Item .env.example .env
# macOS / Linux
cp .env.example .env
```

打開 `.env`，把以下三行填好：

```ini
WORKFLOW_ACTION_BACKEND=foundry
AZURE_FOUNDRY_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_FOUNDRY_API_KEY=<由專案維護者提供>
AZURE_FOUNDRY_DEPLOYMENT=gpt-4o-mini
```

### 第三步：啟動 Gateway 與圖形編輯器

需要兩個終端機視窗，**分別啟 Gateway 與編輯器**。

**終端機 1 — 啟 Gateway（埠 8080）**：

```bash
# Windows（建議；會額外順手帶起 Multi-Model Dashboard 於 8501）
.\scripts\start.ps1

# macOS / Linux（手動啟動，僅 Gateway）
uv run python -m agentic_sdk.gateway
```

**終端機 2 — 啟編輯器（埠 5173）**：

```bash
cd demo
npm run dev
```

瀏覽器打開 [http://localhost:5173](http://localhost:5173)，應看到預設五節點畫布；於下方對話框輸入訊息按「跑一次」，節點會依序亮燈並印出最終回應。Vite dev server 已設好 `/v1/workflow` proxy 到 `localhost:8080`，不必處理跨域。

> 健康檢查：`curl http://127.0.0.1:8080/healthz`。Gateway 是 API server，直接用瀏覽器打 `localhost:8080` 會回 `Not Found`，屬正常。

---

## 進階情境

### 切換 Action 上游到 AMD Ryzen AI NPU

> **適用對象**：已備好 Ryzen AI 主機，想對齊產品形態讓 Action 走 NPU。

先在 Ryzen 機器上依 [`amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 的 README 起 `api.py`，確認 `curl http://localhost:8000/v1/models` 能回傳模型清單。然後把 `.env` 的 `WORKFLOW_ACTION_BACKEND` 改回預設值 `upstream`（Plan / Reflect 仍走 Foundry），重啟 Gateway 即可。

### 多基台驗收（M4-1~M4-3）

驗證「同一份 WorkflowConfig，Action 可獨立指向 Ryzen 或 Foundry」：

```bash
# Ryzen 端先起好 api.py
uv run python scripts/demo_multi_backend.py "請用一句話自我介紹"
```

腳本會跑兩次工作流（Ryzen + Gemma3、Azure Foundry），比對 context entry 結構，並輸出 `docs/quickstart-runs/multi-backend-<timestamp>.json` 作為書面證據。

### 一鍵 smoke test

```bash
uv run python scripts/smoke_chat.py
```

走 `/v1/chat/completions` 跑完一次五節點工作流，印出回覆內容與 `x-agentic-metadata` header（含 `workflow_id` / `visit_counts` / `aborted`）。

### 無 Azure 配額時的離線 demo

```bash
uv run python scripts/demo_workflow.py
```

用 Mock Foundry 與故意不可達的上游跑完工作流，可驗證安裝是否正確、觀察 `workflow.node.start` / `delta` / `finish` 事件 schema。

### 啟動 Multi-Model Dashboard（Streamlit）

```bash
# 跟 Gateway 一併啟（Windows 已含於 start.ps1）
.\scripts\start.ps1
# 只啟 Gateway 不要 Dashboard
.\scripts\start.ps1 -GatewayOnly
# 任何平台手動單啟 Dashboard
uv run streamlit run agentic_sdk/observability/dashboard_app.py
```

### 跑全部測試

```bash
uv run pytest
```

Phase 3 對外宣告完成時測試共 99 項；Phase 4–10 隨工作軸加入 M5 圖形編排、M6 MVP 差異化、M7–M8 UX 收斂、M9–M10 多模態與 vision 橋接、與 Phase 11 串流與 idle-timeout 重構後，**總項來到 158 項**，涵蓋：基礎層（`/healthz`、`/v1/models`、Settings）、觀測層（事件 schema 含 `workflow.node.delta`、RingBuffer、`/internal/telemetry/snapshot`）、Dashboard、Workflow 五節點端對端、Workflow 與 Gateway 的整合驗收（M3-2 / M3-4）、WorkflowConfig 序列化 + Python SDK 注入、多基台拓樸（M4-1~M4-3）、Memory Stream、Semantic Retrieve、多模態與串流輸出。

### 直接呼叫 Gateway（OpenAI SDK 相容）

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")
response = client.with_raw_response.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "幫我查 2024Q4 的銷售報表並摘要"}],
)
completion = response.parse()
print(completion.choices[0].message.content)
print(response.http_response.headers["x-agentic-metadata"])
```

---

## 設計與施工文件

| 目錄 | 內容 | 何時看 |
|------|------|--------|
| [docs/](docs/README.md) | 系統設計（What & Why）：五節點對齊表、上下文管理、遙測契約、API reference | 想理解架構決策時 |
| [blueprint/](blueprint/README.md) | 施工藍圖（How & When）：兩條工作軸、M0–M12 里程碑、目錄結構、風險與決策紀錄 | 想認領工作項或追施工進度時 |
| [demo/README.md](demo/README.md) | 圖形編輯器的目錄結構、節點屬性對應、SSE 事件流 | 想擴充編輯器或除錯前端時 |
| [blueprint/target-quickstart.md](blueprint/target-quickstart.md) | 本 README 三步啟動的反推來源與驗收方式 | 想驗證 quickstart 是否退化時 |
| [.claude/](.claude/) | 協作預設規則（submodule，唯讀） | 跨專案套用 Connect AI style 時 |

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
