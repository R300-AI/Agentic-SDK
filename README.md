# Agentic SDK

> **邊緣叢集管理協定**:把上游已認證的「模型 × 國產晶片」組合,延伸為支援 Perceive / Plan / Retrieve / Reflect / Action 五節點工作流的 Agentic 編排層,並對外維持單一 OpenAI 相容 API。

當前狀態:**Phase 3 完成** — Gateway `/v1/chat/completions` 已接上 Workflow,五節點端對端可用;Multi-Model Dashboard 可即時觀察節點進度。完整施工進度見 [blueprint/README.md](blueprint/README.md)。

---

## 三步啟動

> **目標對象**:想在 AMD Ryzen AI 主機上嘗試 Agentic SDK Gateway 的工程師。
> **環境前提**:Python 3.12;Gateway 本身可在任何作業系統啟動,但 AMD NPU 推論伺服器必須跑在 AMD 硬體上。

### 第一步:依上游 README 啟動推論伺服器

照上游 [amd-ryzen-ai-benchmark](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 完成 Ryzen AI Software 1.7.1 安裝,然後啟動 `api.py`:

```powershell
conda activate ryzen-ai-1.7.1
cd <path to amd-ryzen-ai-benchmark>
python api.py --model gemma3-4b-npu
```

預期 `curl http://localhost:8000/v1/models` 回傳 `gemma3-4b-npu`。上游不是本專案維護範圍,所有 NPU / iGPU 環境細節以上游 README 為準。

### 第二步:啟動 Agentic SDK Gateway 與 Dashboard

```powershell
git clone https://github.com/<your-org>/Agentic-SDK.git
cd Agentic-SDK
git submodule update --init      # 把 .claude/ 拉下來

uv sync --extra dev               # 依 pyproject.toml 裝 Python 3.12 + .venv + 套件與開發依賴

Copy-Item .env.example .env       # UPSTREAM_API_BASE_URL 預設指向 localhost:8000
```

接著編輯 `.env`,填入專案維護者提供的 Azure AI Foundry 認證(Plan / Reflect 節點必需):

```ini
AZURE_FOUNDRY_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/openai/v1/
AZURE_FOUNDRY_API_KEY=<由專案維護者提供>
AZURE_FOUNDRY_DEPLOYMENT=gpt-4o-mini
```

> 暫時沒有 Foundry 金鑰也能啟動 — Gateway 會在五節點工作流內自動切換至 Mock Foundry(行為對齊 [docs/01-architecture/](docs/01-architecture/) 內標注的「PoC 允許的例外」)。

```powershell
.\scripts\start.ps1               # 同時啟動 Gateway (8080) 與 Dashboard (8501)
```

預期(60 秒內):

- `http://localhost:8080/v1/models` 回傳上游模型清單
- 啟動日誌出現 AMD 與(若有金鑰)Azure Foundry 兩條 inference path 的 healthcheck 通過訊息
- `http://localhost:8501` 開得開 Streamlit Dashboard,「節點存活拓樸」面板同時顯示兩條 inference path 狀態

### 第三步:用 OpenAI SDK 跑一次五節點工作流

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")
response = client.chat.completions.create(
    model="gemma3-4b-npu",
    messages=[{"role": "user", "content": "幫我查 2024Q4 的銷售報表並摘要"}],
)
print(response.choices[0].message.content)

# Gateway 透過 response header 透出內部執行軌跡(JSON 字串)
print(response.response.headers["x-agentic-metadata"])
```

預期結果:

- 回應為標準 OpenAI ChatCompletion 形態
- `x-agentic-metadata` header 內含 `workflow_id` / `visit_counts` / `aborted` / `abort_reason`
- Dashboard「Workflow 執行進度」面板出現一條同 `workflow_id` 的節點時間序列(`perceive → plan → retrieve → plan → action → reflect`)
- Dashboard「推論指標時序圖」面板出現本次呼叫對應的 TTFT / tokens-per-sec 資料點

健康檢查端點:`GET http://127.0.0.1:8080/healthz`。

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

Phase 3 完成時測試共 82 項,涵蓋:基礎層(`/healthz`、`/v1/models`、Settings)、觀測層(事件 schema、RingBuffer、`/internal/telemetry/snapshot`)、Dashboard、Workflow 五節點端對端、Workflow 與 Gateway 的整合驗收(M3-2 / M3-4)。

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
