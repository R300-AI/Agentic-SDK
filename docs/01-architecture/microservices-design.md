# Service Topology — SDK 與上游推論伺服器的部署關係 [R01]

> 受眾:後端工程師、DevOps
> 目的:說明 Agentic SDK 與上游 [amd-ryzen-ai-benchmark](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 的部署拓樸,以及對外為何只暴露 OpenAI 相容介面。

## 一、設計目標

把上游已提供的 OpenAI 相容推論伺服器,延伸為支援 Perceive / Plan / Retrieve / Reflect / Action 五大節點工作流的 Agentic 編排層,並對外維持單一一致的 OpenAI API。

兩條硬性要求:

1. **零侵入接入**:應用端只改 `base_url`,不改業務程式碼
2. **上游不修改**:本專案不為上游 `api.py` 加任何 patch,所有 Agentic 能力都在本專案內實作

## 二、部署拓樸

兩個本機行程 + 一個雲端端點,使用者依序啟動:

```
┌─────────────────────────────────────────────────────────┐
│ Step 1. 使用者照上游 README 啟動 AMD NPU 推論伺服器       │
│   python api.py --model gemma3-4b-npu                   │
│   → http://localhost:8000  (上游維護、Model Card 身分)    │
└─────────────────────────────────────────────────────────┘
                          ▲ HTTP (UPSTREAM_API_BASE_URL)
                          │ Gateway 代理 + Action 節點呈繳推理
                          │
┌─────────────────────────────────────────────────────────┐
│ Step 2. 使用者啟動本專案 Agentic SDK Gateway              │
│   python -m agentic_sdk.gateway                         │
│   → http://localhost:8080  (本專案維護)                   │
│   ├─ Perceive / Plan / Retrieve / Reflect / Action 編排  │
│   ├─ Active Context 管理                                 │
│   └─ 遙測輸出                                             │
└─────────────────────────────────────────────────────────┘
                          ▲ HTTP (OpenAI 相容)
                          │
                應用端 / Dashboard / 任何 OpenAI SDK

另外由 Plan / Reflect 節點內部直接呼叫(不透過 Gateway 代理):

  Azure AI Foundry deployment
  → HTTPS (AZURE_FOUNDRY_ENDPOINT)
  由專案維護者提供 endpoint + API key
```

Gateway 本身是純 Python,不需 Docker。上游 AMD NPU 伺服器由使用者照上游 README 裝好 conda 環境,Azure Foundry deployment 則需事先由專案維護者提供 endpoint + API key。

> Phase 4 TSiP 到位後再考慮容器化。未來 Azure Foundry 可換成本機第二個 AMD NPU 伺服器(如跑小型控制平面模型),只需調整節點內的 base_url 設定,Gateway 與編排邏輯皆無需動。

## 三、為什麼選 OpenAI 相容,不是自訂協定

| 選項 | 取捨 |
|------|------|
| 自訂 RPC / gRPC | 完整控制,但需要為每個上層框架寫 Adapter,維護成本隨框架數線性增加 |
| OpenAI REST 相容 [R01] | LangChain / AutoGen / LlamaIndex 等主流框架原生支援,接入成本為零;且上游已採此標準,SDK 對外維持一致 |

選擇後者的關鍵理由:**OpenAI API 已經成為事實標準**,對抗事實標準的成本永遠高於擁抱它的成本。

PoC 階段只需實作最小相容子集(對應上游已支援的):
- `POST /v1/chat/completions`(含 `stream=true` SSE)
- `GET /v1/models`(轉發上游回應)

`embeddings`、`fine-tuning`、`assistants` 等端點皆暫不實作,待第二個使用者出現再決定。

## 四、Gateway 內部組成

Gateway 是單一 Python 行程,內部分兩層。本架構刻意不含「第三方 LLM 路由抽象」,那是節點實作的職責邊界:

```
┌──────────────────────────────────────────────┐
│ OpenAI API 相容層 (FastAPI)                   │
│   POST /v1/chat/completions   → 觸發工作流    │
│   GET  /v1/models             → 轉發上游      │
└────────────┬─────────────────────────────────┘
             ↓
┌──────────────────────────────────────────────┐
│ 五節點工作流引擎 (LangGraph)                  │
│   Perceive / Plan / Retrieve / Reflect /     │
│   Action 路由與 Active Context 管理           │
│                                              │
│   · 有 LLM 需求的節點(plan/reflect)直接以    │
│     openai SDK + agentic_sdk.config 組成     │
│     client 呼叫外部(如 Azure Foundry),      │
│     由各節點自行管理 — Gateway 不代理         │
│   · Action 節點呼叫上游可以包裝同一份         │
│     UPSTREAM_API_BASE_URL 的 client          │
└──────────────────────────────────────────────┘
```

**關鍵邊界**:Gateway 只代理一個上游——AMD NPU api.py(上游由 Model Card 交付)。其他 LLM 來源(Azure Foundry、未來 OpenAI 雲端、另一台 AMD)皆由個別節點實作自行呼叫,避免 Agentic SDK Gateway 越級接手 Model Card 以外的推論來源。

現階段五節點的 LLM 使用:

- **Action 節點** → `openai.OpenAI(base_url=settings.upstream_api_base_url).chat(...)` → 上游 AMD NPU api.py
- **Plan 節點** → `openai.AzureOpenAI(azure_endpoint=settings.azure_foundry_endpoint, api_key=settings.azure_foundry_api_key).chat(...)` → Azure Foundry deployment
- **Reflect 節點** → 同 Plan
- **Perceive / Retrieve** → 不呼叫任何雲端 LLM(Perceive 純規則、Retrieve 使用本機 sentence-transformers)

雙 LLM 來源的取捨見 [blueprint/risk-decisions.md D5](../../blueprint/risk-decisions.md);上游交鋒點規範見 [02-model-card-contract/upstream-integration.md](../02-model-card-contract/upstream-integration.md)。

## 五、配置體系(反硬編碼)

所有具業務意義的參數透過 `.env` 統一管理,嚴禁散落於程式碼:

| 參數名 | 預設值 | 量化依據 |
|--------|--------|----------|
| `GATEWAY_PORT` | `8080` | 與上游 `api.py` 預設 8000 區隔,避免本機衝突 |
| `UPSTREAM_API_BASE_URL` | `http://localhost:8000/v1` | 上游 AMD NPU 推論伺服器(Model Card 交付物);Gateway 代理與 Action 節點均走這個來源 |
| `UPSTREAM_HEALTHCHECK_TIMEOUT_SEC` | `5` | Gateway 啟動時對上游一次性 healthcheck |
| `AZURE_FOUNDRY_ENDPOINT` | 無預設(必填) | Azure AI Foundry deployment endpoint,供 Plan / Reflect 節點個別呼叫;**Gateway 不代理此來源** |
| `AZURE_FOUNDRY_API_KEY` | 無預設(必填) | Azure Foundry API key,寫入 `.env`,不進 git |
| `AZURE_FOUNDRY_DEPLOYMENT` | `gpt-4o-mini` | 由專案維護者提供的部署名稱 |
| `INFER_REQUEST_TIMEOUT_SEC` | `120` | 任一節點呼叫任一 LLM 來源的逯時(涵蓋 P99 長尾) |
| `WORKFLOW_MAX_NODE_HOPS` | `50` | 見 [03-agentic-orchestration/react-workflow-routing.md](../03-agentic-orchestration/react-workflow-routing.md) §六 |
| `WORKFLOW_MAX_REVISIT` | `5` | 同上 |
| `WORKFLOW_TIMEOUT_SEC` | `600` | 同上 |

修改任一參數只需改 `.env`,Gateway 重啟即生效。`AZURE_FOUNDRY_*` 是 Plan / Reflect 節點出現於工作流時的硬性前提條件,未設定則在該節點首次呼叫時拋出明確錯誤提示使用者填入。

## 六、PoC 階段允許的簡化

以下偏離 Production 級設計的選擇,必須在 MVP 後補強:

- **無認證中介層**:Gateway 對 `Authorization: Bearer` 僅做存在性檢查,不驗 token 內容。MVP 後需接入正式 IAM。
- **無水平擴展**:單 Gateway 單機部署,未驗證多副本下的 sticky session 行為
- **單一上游實例**:`UPSTREAM_API_BASE_URL` 是單一字串,PoC 不支援多個上游負載均衡
- **無流量配額**:超出上游 NPU 處理能力時直接逾時,無 token bucket

以上偏離在 [01-architecture/ai-hub-vision.md](ai-hub-vision.md) 中已標注於「PoC 允許的例外」清單。
