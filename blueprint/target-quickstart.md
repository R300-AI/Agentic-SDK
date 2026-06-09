# Target Quickstart — 三步啟動目標形態

> 受眾:Phase 3 收尾時的根 README 改寫負責人
> 目的:把「PoC 完成後使用者該怎麼用」這件事先寫死,作為 M3 的反推目標。

本文件描述的內容,**在 M3 達成前都是目標,不是現況**。Phase 3 完成時,本文件內容應與根目錄 [README.md](../README.md) 一致;若不一致則 M3 未完成。

---

## 目標讀者

一位有工程背景、拿到 Ryzen AI PC、沒讀過本專案內部設計、想在 30 分鐘內讓 PoC 跑起來的工程師。

> 為何不是 15 分鐘:Ryzen AI Software 1.7.1 與 conda 環境的安裝本身就需要時間,15 分鐘只能讓「已裝好環境」的使用者過關。30 分鐘是含環境準備的合理上限。

## 三步啟動

### 第一步:依上游 README 啟動推論伺服器

依 [amd-ryzen-ai-benchmark README](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 的「📥 安裝指南」+「📦 支援的模型列表 — 快速開始」完成:

```powershell
# 已照上游 README 安裝完 Ryzen AI Software 1.7.1
conda activate ryzen-ai-1.7.1
cd <path to amd-ryzen-ai-benchmark>
python api.py --model gemma3-4b-npu
```

預期結果:

- 上游於 `http://localhost:8000` 啟動 OpenAI 相容 API server
- `curl http://localhost:8000/v1/models` 回傳 `gemma3-4b-npu`

> 上游推論伺服器是**本專案的前置條件**,本專案不重新封裝 NPU / iGPU 環境。

### 第二步:啟動本專案 Agentic SDK Gateway + Dashboard

開新的 Terminal:

```powershell
git clone https://github.com/<org>/Agentic-SDK.git
cd Agentic-SDK
git submodule update --init   # 把 .claude/ 拉下來
pip install -e .              # 安裝本專案
cp .env.example .env          # UPSTREAM_API_BASE_URL 已預設指向 localhost:8000
```

接著在 `.env` 填入專案維護者提供的 Azure AI Foundry 認證(Plan / Reflect 節點必需):

```
AZURE_FOUNDRY_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/openai/v1/
AZURE_FOUNDRY_API_KEY=<由專案維護者提供>
AZURE_FOUNDRY_DEPLOYMENT=gpt-4o-mini
```

```powershell
.\scripts\start.ps1           # 同時啟動 Gateway (8080) 與 Streamlit Dashboard (8501)
```

預期結果(60 秒內):

- `http://localhost:8080/v1/models` 回傳上游的模型清單(AMD backend healthcheck 通過)
- Gateway 啟動日誌顯示 Azure Foundry backend healthcheck 通過
- `http://localhost:8501` 開得開 Streamlit Dashboard
- Dashboard 「觀測-1:節點存活拓樸」同時顯示 AMD NPU 與 Azure Foundry 兩條 inference path 健康

### 第三步:跑一個五節點工作流

只有一個入口:**用 OpenAI SDK 直接呼叫**。

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="local")
response = client.chat.completions.create(
    model="gemma3-4b-npu",
    messages=[{"role": "user", "content": "幫我查 2024Q4 的銷售報表並摘要"}],
)
print(response.choices[0].message.content)
```

預期結果:

- 回傳結果包含五節點各自的中間紀錄(透過 `x-agentic-metadata` header)
- Dashboard 「觀測-3:Workflow 執行進度」面板在這次呼叫期間有五節點依序亮燈
- Dashboard 「觀測-2:推論指標時序圖」面板出現對應 TTFT / tokens/sec 資料點

> 圖形拖曳編排不在 M3 範圍,延後至 [tracks.md](tracks.md) Phase 5 評估。

---

## 驗收這個 quickstart 的方法

M3 階段必須找一名**未參與本專案開發、但有工程背景**的同事,按上述三步操作,並回答:

| 問題 | 期望答案 |
|------|----------|
| 從第二步開始到看見 Dashboard 第一個面板,花了多久? | ≤ 5 分鐘(第一步上游環境安裝不計時) |
| 整個流程過程中卡關幾次?卡在哪? | ≤ 2 次,且每次卡關都有明確錯誤訊息指引 |
| 第三步「跑一個五節點工作流」,你能否說出五節點各自做了什麼? | 能,且與 [docs/03-agentic-orchestration/react-workflow-routing.md](../docs/03-agentic-orchestration/react-workflow-routing.md) §二 描述一致 |

任一問題不過關,Phase 3 視為未完成,回頭優化 quickstart 流程而非「請使用者再多讀點文件」。

> 上游環境安裝時間(第一步)不在本驗收範圍——這是上游的責任。本專案只對「第二步開始」負責。

---

## 不在 quickstart 範圍的事項

明確記錄,避免 quickstart 文件膨脹:

- ❌ Production 部署(TLS、IAM、多副本)— 進階文件
- ❌ 自製節點型別 — 進階文件,留到 MVP
- ❌ 跨機部署 — 等 Phase 4 TSiP 到位後另寫
- ❌ Dashboard 客製主題 — 由整合商於 Streamlit 之上自行擴充
- ❌ 圖形拖曳編排 — 延至 M5 啟動條件成立後另寫

quickstart 文件的天職是讓使用者**第一次成功**,不是窮盡所有用法。
