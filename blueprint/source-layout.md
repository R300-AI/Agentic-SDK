# Source Layout — 程式碼目錄結構設計

> 受眾:Track Lead、所有工作項認領者
> 目的:定義本專案實作階段的**程式碼目錄結構**(對應 [CLAUDE.md §六](../.claude/CLAUDE.md) 「專案目錄與資產設計規範」),作為所有工作項放置的單一事實來源。

## 設計原則

1. **與 docs/ 對齊**:`agentic_sdk/` 內的模組劃分必須與 [docs/](../docs/README.md) 章節對應,讓設計與實作互為鏡像
2. **編排內聚於 `agentic_sdk/`,觀測內聚於 `dashboard/`**:對應 Track A / Track B 的工作軸劃分
3. **無狀態與可測試**:模組內禁止寫死本機路徑,所有 I/O 透過 `agentic_sdk/config.py` 統一注入
4. **YAGNI**:目錄只開到 PoC 真實需要的深度,不為 MVP 未來規劃預先建層;不採 `src/` layout,套件直接放在儲存庫根目錄

## 完整目錄結構

```
Agentic-SDK/
├── README.md                          # 三步啟動門戶(Phase 3 完成後對齊 blueprint/target-quickstart.md)
├── CLAUDE.md                          # 專案脈絡與協作預設規則
├── pyproject.toml                     # Python 套件描述、依賴宣告、entry point
├── .env.example                       # 配置範本(對應 docs/01-architecture/microservices-design.md §五)
├── .gitignore
├── .gitmodules                        # .claude/ submodule 設定
│
├── .claude/                           # 規範模組(submodule,唯讀)
│
├── docs/                              # What & Why(設計凍結後不常改)
│   ├── README.md
│   ├── 01-architecture/
│   ├── 02-model-card-contract/
│   ├── 03-agentic-orchestration/
│   ├── 04-observability-dashboard/
│   └── 05-api-reference/
│
├── blueprint/                         # How & When(隨執行進度更新)
│   ├── README.md
│   ├── tracks.md
│   ├── milestones.md
│   ├── target-quickstart.md
│   ├── risk-decisions.md
│   └── source-layout.md               # 本文件
│
├── agentic_sdk/                       # 主套件(pip install -e . 後可 import)
│   ├── __init__.py                    # 公開 API:AgenticClient, Workflow, Node, NodeOutput
│   ├── config.py                      # F-03:.env 解析、所有配置項統一管理
│   ├── client.py                      # AgenticClient(包裝 openai SDK + metadata 解析)
│   │
│   ├── gateway/                       # F-01 / F-02:對外 OpenAI 相容前端(只代理上游 AMD NPU api.py)
│   │   ├── __init__.py
│   │   ├── app.py                     # FastAPI 應用 entry point(python -m agentic_sdk.gateway)
│   │   ├── routes_chat.py             # POST /v1/chat/completions(觸發工作流)
│   │   ├── routes_models.py           # GET /v1/models(轉發上游)
│   │   ├── routes_internal.py         # GET /internal/context/{id}, /internal/telemetry/snapshot
│   │   ├── upstream_client.py         # F-02:openai SDK 包裝 UPSTREAM_API_BASE_URL + healthcheck
│   │   └── metadata.py                # x-agentic-metadata header / SSE metadata chunk 組裝
│   │
│   ├── workflow/                      # Track A:對應 docs/03-agentic-orchestration/react-workflow-routing.md
│   │   ├── __init__.py
│   │   ├── engine.py                  # A-02:LangGraph 整合,Workflow.run() 入口
│   │   ├── node.py                    # A-01:Node Protocol、NodeOutput TypedDict
│   │   ├── gates.py                   # A-06:三道閘門(MAX_NODE_HOPS / MAX_REVISIT / TIMEOUT)
│   │   └── nodes/                     # A-03:五大節點、每個節點一個資料夾,一個演算法一個檔案
│   │       ├── __init__.py            # 專門説明「如何新增一個演算法」的套件 docstring
│   │       ├── perceive/
│   │       │   ├── __init__.py        # 儲存 DEFAULT = RuleBasedPerceive
│   │       │   └── rule_based.py      # baseline:純規則抽 intent / role
│   │       ├── plan/
│   │       │   ├── __init__.py        # 儲存 DEFAULT = ReActPlan
│   │       │   └── react.py           # baseline:Yao 2022 ReAct (R09)
│   │       ├── retrieve/              # A-08:Chroma + sentence-transformers
│   │       │   ├── __init__.py        # 儲存 DEFAULT = VanillaRagRetrieve
│   │       │   └── vanilla_rag.py     # baseline:Lewis 2020 RAG (R10)
│   │       ├── reflect/               # A-09
│   │       │   ├── __init__.py        # 儲存 DEFAULT = ReflexionReflect(fallback=RuleBasedReflect())
│   │       │   ├── reflexion.py       # baseline:Shinn 2023 Reflexion (R12)
│   │       │   └── rule_based.py      # D4:exit code / schema 比對 fallback
│   │       └── action/
│   │           ├── __init__.py        # 儲存 DEFAULT = UpstreamCompletionAction
│   │           └── upstream_completion.py  # baseline:呼叫上游 /v1/chat/completions
│   │
│   ├── context/                       # Track A:對應 docs/03-agentic-orchestration/context-and-memory.md
│   │   ├── __init__.py
│   │   ├── entry.py                   # A-04:ContextEntry 資料結構
│   │   ├── active_store.py            # A-04:in-memory dict 實作(Phase 4 換 Redis 的抽象點)
│   │   ├── archived_store.py          # A-07:本機檔案系統實作
│   │   └── lifecycle.py               # A-07:Idle 降級、TTL 過期、Eviction
│   │
│   └── telemetry/                     # Track B 後端:對應 docs/04-observability-dashboard/telemetry-metrics.md
│       ├── __init__.py
│       ├── buffer.py                  # B-01:in-memory ring buffer
│       ├── otel_exporter.py           # B-02:OpenTelemetry 格式輸出(Phase 1 預留,不啟用)
│       └── events.py                  # 事件型別定義(node_visit, gate_triggered, context_degraded ...)
│
├── dashboard/                         # Track B 前端:Streamlit 觀測 Dashboard
│   ├── app.py                         # B-03:streamlit run 入口
│   ├── panels/                        # B-04 ~ B-07:四個觀測面板
│   │   ├── __init__.py
│   │   ├── topology.py                # B-04:觀測-1 節點存活拓樸
│   │   ├── inference_metrics.py       # B-05:觀測-2 推論指標時序圖
│   │   ├── workflow_progress.py       # B-06:觀測-3 工作流執行進度
│   │   └── degradation_log.py         # B-07:觀測-4 降級事件 log
│   └── data_source.py                 # 統一從 Gateway /internal/telemetry/snapshot 拉取資料
│
├── scripts/
│   ├── start.ps1                      # F-04:同時啟動 Gateway 與 Dashboard 的 PowerShell 腳本
│   ├── start.sh                       # Linux/macOS 版本(若團隊有需要再加)
│   └── healthcheck.ps1                # 對上游 + Gateway + Dashboard 三方探活
│
├── tests/
│   ├── unit/
│   │   ├── test_gates.py              # A-10:三道閘門觸發
│   │   ├── test_lifecycle.py          # A-10:Token 降級、TTL 過期
│   │   ├── test_context_failure.py    # A-10:404 / 410 失效模式
│   │   └── test_nodes/                # 各節點獨立單元測試(對應 M1-1)
│   │       ├── test_perceive.py
│   │       ├── test_plan.py
│   │       ├── test_retrieve.py
│   │       ├── test_reflect.py
│   │       └── test_action.py
│   └── integration/
│       ├── test_workflow_e2e.py       # M1-2:完整五節點工作流
│       ├── test_gate_termination.py   # M1-4:閘門 P99 < 5 秒驗證
│       └── test_m3_acceptance.py      # M3:整合 demo 驗收腳本
│
└── assets/                            # 非程式碼資產
    └── retrieve-corpus/               # A-08:Retrieve 節點的最小知識集(範例文件)
```

## 關鍵設計決定

### 為何不採 `src/` layout

- `src/agentic_sdk/` 是大型套件防止「本機目錄誤被 import」的慣例,PoC 階段沒這個風險
- 多一層 `src/` 對應的是「發行套件 vs. 開發工作區」的嚴格隔離需求,本專案目前沒有
- 直接 `agentic_sdk/` 在根目錄,`pip install -e .` 與直接 `python -m agentic_sdk.gateway` 都更直觀
- MVP 後若要發行到 PyPI 且踩到 import 衝突,再評估遷移成本(只是一次 `git mv`)

### 為何 `dashboard/` 不放在 `agentic_sdk/` 內

- Streamlit 應用本質是「另一個行程」,不是 SDK 套件的一部分
- 使用者 `pip install agentic-sdk` 不應強制安裝 Streamlit 依賴
- 對應 [tracks.md](tracks.md) Track B 與 Track A 的工作軸隔離原則

### 為何 `tests/` 平鋪而非鏡像 `agentic_sdk/`

- PoC 階段測試數量有限,平鋪比鏡像結構更易瀏覽
- M3 達成後若測試數量爆增,再評估改為鏡像結構

### 為何 `nodes/` 下每個節點是資料夾而非單一檔案

這是本架構最重要的可擴展性設計。類比 `torchvision.models` 裡 ResNet / MobileNet / EfficientNet 各自一個檔案,本專案讓同一節點的不同演算法變體可以平行存在:

- **一個演算法 = 一個檔案**:`plan/react.py`、`plan/tree_of_thoughts.py`、`plan/llm_compiler.py` 並列
- **檔名 = 論文讀本名的 snake_case**:讀者能一眼對應 `docs/` 與 R-index 論文編號
- **每個演算法類實作 Node Protocol**:與 A-01 定義的 `__call__(state) -> NodeOutput` 一致
- **`__init__.py` 提供 `DEFAULT`**:Workflow 預設拾 baseline,使用者可透過 `Workflow(plan=TreeOfThoughtsPlan())` 覆寫
- **依賴局部化**:進階演算法的重依賴(Neo4j、vector graph DB 等)寫在個別檔案頂部 `import`,不拖累主線 baseline

新增一個演算法的 SOP(詳見下文「節點演算法擴展規範」):

1. 在對應節點資料夾新增 `<algo_name>.py`
2. 實作符合 Node Protocol 的類別
3. 在 `docs/03-agentic-orchestration/` 對應章節註明論文、適用情境與與 baseline 的差異
4. 在 [docs/README.md](../docs/README.md) R-index 新增參考倉項目

### 為何沒有 `models/` 或 `weights/` 目錄

- 模型權重由上游 [`amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 管理(見 [risk-decisions.md D1](risk-decisions.md))
- 本專案任何時候都不下載模型權重,故無需該目錄

### 為何沒有 `docker/` 目錄

- PoC 階段純 Python 行程,不容器化(見 [docs/01-architecture/microservices-design.md](../docs/01-architecture/microservices-design.md) §二)
- Phase 4 TSiP 到位後若需容器化,屆時新增 `docker/` 目錄與 `compose.yaml`

## 工作項與檔案的對應表

供 Track Lead 認領工作項時快速定位:

| 工作項 | 主要產出檔案 |
|--------|-------------|
| F-01 | `agentic_sdk/gateway/app.py`, `routes_chat.py`, `routes_models.py` |
| F-02 | `agentic_sdk/gateway/upstream_client.py`(只包裝 AMD NPU 上游;Azure Foundry 由個別節點實作以 openai SDK 呼叫,不進 Gateway) |
| F-03 | `agentic_sdk/config.py`, `.env.example`(含 AMD + Azure Foundry 雙一組變數) |
| F-04 | `scripts/start.ps1`, 根 `README.md` 對應段落 |
| A-01 | `agentic_sdk/workflow/node.py`, `agentic_sdk/context/entry.py` |
| A-02 | `agentic_sdk/workflow/engine.py`, `agentic_sdk/workflow/llm.py`, `agentic_sdk/workflow/gates.py` |
| A-03 | `agentic_sdk/workflow/nodes/{perceive,plan,retrieve,reflect,action}/*.py`(五節點各交付一個 baseline;`retrieve/stub.py` 代替 Phase 5 才交的 `vanilla_rag.py`;`reflect/rule_based.py` 代替 Phase 5 才交的 `reflexion.py`) |
| A-04 | `agentic_sdk/context/entry.py`, `active_store.py` |
| A-05 | `agentic_sdk/gateway/routes_internal.py` |
| A-06 | `agentic_sdk/workflow/gates.py` |
| A-07 | `agentic_sdk/context/lifecycle.py`, `archived_store.py` |
| A-08 | `agentic_sdk/workflow/nodes/retrieve/vanilla_rag.py`, `assets/retrieve-corpus/` |
| A-09 | `agentic_sdk/workflow/nodes/reflect/reflexion.py`, `reflect/rule_based.py` |
| A-10 | `tests/unit/*.py` |
| B-01 | `agentic_sdk/observability/{events,handler,setup,spans}.py`(原藍圖命名 `telemetry/`,為避免與 Settings 的 `telemetry_*` 欄位混淆改為 `observability/`) |
| B-02 | `agentic_sdk/observability/exporters/otel.py`【待交付、Phase 2 預留、不啟用】 |
| B-03 | `dashboard/app.py`, `data_source.py` |
| B-04 | `dashboard/panels/topology.py` |
| B-05 | `dashboard/panels/inference_metrics.py`(面板)、`agentic_sdk/gateway/routes_telemetry.py`(端點)— 同一編號覆蓋「為面板提供資料」的一體兩面,以免拆為兩項才能驗證 |
| B-06 | `dashboard/panels/workflow_progress.py` |
| B-07 | `dashboard/panels/degradation_log.py` |
| B-08 | `.env.example` 新增 `DASHBOARD_PORT` |
| I-01 | `agentic_sdk/workflow/engine.py` 與 `telemetry/buffer.py` 整合 |
| I-02 | `tests/integration/test_m3_acceptance.py` |
| I-03 | 根 `README.md` |

## 五節點 PoC 基線演算法對照表

A-03 工作項需交付的**每個節點一個演算法實作**。這是 PoC 階段的唯一必交項;進階演算法列為 Phase 5+ 可選增量。

| 節點 | Baseline 檔案 | 演算法 | 論文 / 來源 | LLM Backend | 核心依賴 | Phase 5+ 候選變體 |
|------|--------------|--------|--------------|-------------|----------|-------------------|
| perceive | `rule_based.py` | 從 user message 抽 intent + role 寫入 `ContextEntry(type=perceived)` | 純規則,無論文 | 無(不呼叫 LLM) | 無 | LLM-based intent classifier |
| plan | `react.py` | ReAct 迴圏:Foundry client 產 JSON `{thought, next_node}` | Yao 2022 ReAct (R09) | **azure**(Foundry deployment;無金鑰自動降為 Mock) | openai SDK | Tree of Thoughts、LLM Compiler |
| retrieve | `stub.py`【PoC 限定】 | 內建關鍵字字典命中則回片段;未命中回 fallback | 無論文(為 Phase 5 代替品) | 無 | 無 | Phase 5 換 `vanilla_rag.py`(Lewis 2020 RAG, R10),並列 HyDE、GraphRAG、Self-RAG |
| reflect | `rule_based.py`【PoC 限定】 | 依 `state.last_action_error` 路由回 `plan` 或 END | D4 | 無 | 無 | Phase 5 加上 `reflexion.py`(Shinn 2023 Reflexion, R12)為主策略,本檔退為 fallback |
| action | `upstream_completion.py` | 呼叫 AMD NPU backend 產出最終回應(共用 `gateway.upstream_client.UpstreamClient`) | 上游 api.py | **amd**(本機 NPU) | openai SDK | Function calling router、Code Interpreter |

**與原藍圖的差異**:Phase 2 PoC 為了在無 Azure 配額 / 無 chromadb 依賴下能跑通五節點,`retrieve` 與 `reflect` 先交付最便宜的 baseline,原藍圖記的進階版本(`vanilla_rag.py` / `reflexion.py`)到 Phase 5 才交付;Plan 節點頭上加一層 `MockFoundryClient`,讓 PoC 在離線環境也能驗證路由。

雙 LLM 來源的分工依據見 [risk-decisions.md D5](risk-decisions.md)。邊界:Gateway 只代理上游 AMD NPU(Model Card 交付物);Plan / Reflect 需的 Azure Foundry 由節點實作直接以 openai SDK 呼叫,透過 `agentic_sdk.config` 拿 endpoint 與 key。

## 節點演算法擴展規範

PoC 交付五個 baseline 後,任何人(包含未來社群)都能以同一型式新增進階演算法,無需動架構。以 retrieve 節點新增 HyDE 為例:

```
agentic_sdk/workflow/nodes/retrieve/
├── __init__.py            # DEFAULT = VanillaRagRetrieve(保持不動)
├── vanilla_rag.py         # 既有 baseline
└── hyde.py                # 新增:Gao 2022 HyDE
```

`hyde.py` 只需實作符合 Node Protocol 的類別:

```python
from agentic_sdk.workflow.node import Node, NodeOutput

class HyDERetrieve(Node):
    def __call__(self, state) -> NodeOutput:
        # 1. LLM 生成假設性答案
        # 2. 將假設答案 embedding 後查 Chroma
        # 3. 寫入 ContextEntry
        ...
```

使用者透過 三行程式切換:

```python
from agentic_sdk.workflow import Workflow
from agentic_sdk.workflow.nodes.retrieve.hyde import HyDERetrieve

wf = Workflow(retrieve=HyDERetrieve())
```

全程不需以下任何一項:

- 不需修改 `engine.py`
- 不需修改 `gates.py`
- 不需變動 telemetry 收集邏輯
- 不需增加 Workflow 的構造函數參數

這是「與 PyTorch backbone zoo 同型式」的具體含義:**新演算法的加入是中心化的補給,不是架構修改**。

## 不在本結構內的事項

- ❌ `migrations/` — PoC 無資料庫,不需要
- ❌ `i18n/` — 介面文字目前只有中文,不做多語系
- ❌ `examples/` — 範例已在 [docs/05-api-reference/python-sdk-integration.md](../docs/05-api-reference/python-sdk-integration.md) 內,不重複
- ❌ `notebooks/` — PoC 階段不採 Jupyter 工作流;若 MVP 後客戶需要再評估

## 變更管理

任何新增目錄或重大重構(例如把 `dashboard/` 改為內嵌於 `src/agentic_sdk/`):

1. 在本文件對應段落寫明變更原因
2. 同步調整 [tracks.md](tracks.md) 的「工作項與檔案的對應表」
3. 若觸發 [docs/](../docs/README.md) 章節重組,在該 docs 文件首段標注「結構變更於 YYYY-MM-DD」

避免「實作目錄無聲漂移」是這份文件存在的最大價值。
