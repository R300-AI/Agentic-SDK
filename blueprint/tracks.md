# Tracks — 兩條工作軸與整合點

> 受眾:Track Lead、工作項認領者
> 目的:把兩條主軸與共用基礎拆解為可被認領的工作項,並明確兩軸合流的條件。

## 軸劃分原則

- **Track A(上下文管理 / 工作流)**:對應 [docs/03-agentic-orchestration/](../docs/03-agentic-orchestration/react-workflow-routing.md) 的實作
- **Track B(觀測 Dashboard)**:對應 [docs/04-observability-dashboard/](../docs/04-observability-dashboard/visualization-ui.md) **Phase 1 範圍**(僅執行觀測,不含圖形編排)
- **共用基礎(Shared Foundation)**:Gateway 行程、`.env` 配置、上游推論伺服器接入,兩軸都依賴

## 對上游的依賴

依 [docs/02-model-card-contract/upstream-integration.md](../docs/02-model-card-contract/upstream-integration.md),本專案**不實作**:
- Runner 容器、Model Card SHA 驗證、`/internal/infer` 端點
- NPU / iGPU 驅動封裝、模型下載與量化

使用者照上游 [amd-ryzen-ai-benchmark README](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 啟動 `python api.py --model <model-id>` 後,本專案 Gateway 透過 `UPSTREAM_API_BASE_URL` 接上其 `http://localhost:8000/v1`。

---

## Phase 0:共用基礎(M0 前置)

兩軸開工前必須完成。建議由一名工程師主導,其他人在這階段做環境準備。

| 工作項 | 內容 | 對應 docs/ |
|--------|------|------------|
| F-01 | `agentic_sdk.gateway` Python 行程骨架(FastAPI),實作 `POST /v1/chat/completions` 與 `GET /v1/models`(後者轉發上游) | [01-architecture/microservices-design.md](../docs/01-architecture/microservices-design.md) §四 |
| F-02 | 上游客戶端封裝:用 `openai` SDK 連 `UPSTREAM_API_BASE_URL`,Gateway 啟動時做一次 healthcheck | [02-model-card-contract/upstream-integration.md](../docs/02-model-card-contract/upstream-integration.md) §四 |
| F-03 | `.env` 配置體系建立,涵蓋 `GATEWAY_PORT` / `UPSTREAM_API_BASE_URL` / `UPSTREAM_HEALTHCHECK_TIMEOUT_SEC` / `INFER_REQUEST_TIMEOUT_SEC` | [01-architecture/microservices-design.md](../docs/01-architecture/microservices-design.md) §五 |
| F-04 | 啟動指引文件:在根 README 寫明「先依上游 README 起 api.py、再啟動本專案 Gateway」的雙行程順序 | [blueprint/target-quickstart.md](target-quickstart.md) 第一、二步 |

**Phase 0 完成標準**:
- 上游 `api.py` 啟動後,Gateway healthcheck 通過並印出當前可用模型
- `curl POST localhost:8080/v1/chat/completions` 與直接呼叫上游結果一致(此時 Gateway 只是 pass-through,尚無 Agent 編排)

---

## Phase 1:Track A — 上下文管理 / 工作流軸

### 範圍邊界

- **PoC 內**:單機內邏輯節點(同一 Gateway 行程內的 LangGraph 節點)之間的 Active Context 引用 ID 傳遞
- **PoC 外**:跨實體機器的上下文同步(延至 Phase 4 TSiP 到位後驗證)

「節點」一詞在 PoC 期間指**邏輯節點**(同行程內的工作流節點),不是實體機器。

### 工作項

| 工作項 | 內容 | 對應 docs/ |
|--------|------|------------|
| A-01 | `Workflow` / `Node` 編排原語(Python),Node Protocol 含 `name` / `required_capability` / `run()` | [03-agentic-orchestration/react-workflow-routing.md](../docs/03-agentic-orchestration/react-workflow-routing.md) §三 |
| A-02 | LangGraph 作為內部編排引擎接入(對外不洩漏 LangGraph 概念),Gateway 在 `chat/completions` 路徑上啟動 Workflow | 同上 §八 |
| A-03 | 五大節點骨架實作:Perceive / Plan / Retrieve / Reflect / Action,每個有最小可跑版本(節點內呼叫上游 LLM 用 `openai` SDK) | 同上 §二 |
| A-04 | `ContextEntry` 資料結構 + Active Context in-memory 存放(Python dict,Phase 1 不上 Redis) | [03-agentic-orchestration/context-and-memory.md](../docs/03-agentic-orchestration/context-and-memory.md) §二 |
| A-05 | 跨節點傳遞契約:`GET /internal/context/{entry_id}` 端點實作(Phase 1 為同行程內呼叫,Phase 4 才會跨網路) | 同上 §四 |
| A-06 | 三道閘門實作:`WORKFLOW_MAX_NODE_HOPS` / `WORKFLOW_MAX_REVISIT` / `WORKFLOW_TIMEOUT_SEC` | [03-agentic-orchestration/react-workflow-routing.md](../docs/03-agentic-orchestration/react-workflow-routing.md) §六 |
| A-07 | Token 過期降級機制:`CONTEXT_IDLE_DEMOTE_SEC` / `CONTEXT_HARD_TTL_SEC` / `ACTIVE_CONTEXT_MAX_MB` | [03-agentic-orchestration/context-and-memory.md](../docs/03-agentic-orchestration/context-and-memory.md) §三 |
| A-08 | Retrieve 節點預設後端:Chroma + sentence-transformers,放最小知識集 | [03-agentic-orchestration/react-workflow-routing.md](../docs/03-agentic-orchestration/react-workflow-routing.md) §八 |
| A-09 | Reflect 節點預設策略:Reflexion 最小實作(verbal feedback,不訓練)。fallback:rule-based(輸出長度 < N 重試一次) | 同上 |
| A-10 | 單元測試:覆蓋三道閘門觸發、Token 降級、上下文引用失效三類失效模式 | — |

### Track A 完成標準(M1)

- 一個包含 5 個節點的 Workflow,在單機跑通 `Perceive → Plan → Retrieve → Plan → Action → Reflect → END` 的完整路徑
- Active Context 用量在 `ACTIVE_CONTEXT_MAX_MB` 內,觸達上限時能正確降級
- 故意觸發無限迴圈,三道閘門能在 P99 < 5 秒內中止並回傳降級事件

---

## Phase 2:Track B — 觀測 Dashboard 軸

### 範圍宣告(對應 docs §三 已決定的拆分)

Phase 2 **只做執行觀測**,不做圖形編排。圖形編排延後至 Phase 5(M3 後評估),Phase 1 / 2 不投入工程資源。

### 與 Track A 的並行性

Track B 不依賴 Track A 的內部實作,只依賴 Phase 0 的 Gateway 遙測介面。兩軸可同時推進。

### 工作項

| 工作項 | 內容 | 對應 docs/ |
|--------|------|------------|
| B-01 | 遙測收集器:Gateway 內部 hook,記錄每次工作流的節點動向、TTFT、tokens/sec、輸出長度,寫入 in-memory ring buffer | [04-observability-dashboard/telemetry-metrics.md](../docs/04-observability-dashboard/telemetry-metrics.md) |
| B-02 | OpenTelemetry 格式輸出(預留 Grafana 接入路徑,Phase 1 不啟用) | 同上 |
| B-03 | Streamlit Dashboard 行程骨架,讀取 Gateway 的遙測端點 `GET /internal/telemetry/snapshot` | [04-observability-dashboard/visualization-ui.md](../docs/04-observability-dashboard/visualization-ui.md) §三 |
| B-04 | 觀測-1 面板:節點存活拓樸(上游健康 + 當前模型清單) | 同上 觀測-1 |
| B-05 | 觀測-2 面板:即時推論指標時序圖(最近 N 次推論的 TTFT / tokens/sec) | 同上 觀測-2 |
| B-06 | 觀測-3 面板:Workflow 執行進度(五節點亮燈、累計 Token 消耗) | 同上 觀測-3 |
| B-07 | 觀測-4 面板:降級事件即時 log | 同上 觀測-4 |
| B-08 | Dashboard 啟動指令納入 `.env`(`DASHBOARD_PORT` 預設 8501) | — |

### Track B 完成標準(M2)

- Dashboard 可在 PoC 機器上以 `streamlit run dashboard/app.py` 啟動,瀏覽器看見四個面板
- 觀測-1 能反映上游 `api.py` 的健康變化(故意停掉上游,Dashboard 在 10 秒內顯示異常)
- 觀測-3 能即時顯示工作流節點進度(觸發一次工作流,五節點依序亮燈)

---

## Phase 3:整合點 — 兩軸合流

當 M1 與 M2 都達成,進入合流階段。

| 工作項 | 狀態 | 內容 |
|--------|------|------|
| I-01 | ✅ | Track A 的 Workflow 執行過程把節點進度即時推送到 Track B 的 in-memory 遙測 buffer(Gateway `/v1/chat/completions` 已接 Workflow,`x-agentic-metadata` header 透出 `workflow_id` / `visit_counts` / `aborted` / `abort_reason`) |
| I-02 | ✅ | 撰寫 PoC 驗收腳本:單一模型 × 五節點完整工作流 + Dashboard 即時看見(對應假設 A5)— `tests/test_m3_acceptance.py` 三案覆蓋 M3-2 / M3-4 |
| I-03 | ✅ | 完善根 README,讓使用者能依 [target-quickstart.md](target-quickstart.md) 三步啟動 |
| I-04 | ✅ | 整理已知限制清單,寫入 [docs/01-architecture/ai-hub-vision.md](../docs/01-architecture/ai-hub-vision.md) §五「PoC 允許的例外」(E-1~E-6) |
| I-05 | 🟡 文件已備 | [docs/quickstart-usability-check.md](../docs/quickstart-usability-check.md) 已定義 SOP 與紀錄格式;尚待找一名未參與開發的同事實際執行,結果回寫該檔 §六 |

**Phase 3 完成標準(M3)** 見 [milestones.md](milestones.md)。

---

## Phase 4:TSiP 到位後的延伸

不在 PoC 必要範圍,但接口需從 Phase 0 起就留好。當 TSiP NPU 到位時:

| 工作項 | 內容 |
|--------|------|
| E-01 | 在 TSiP 機器上啟動上游 `api.py`(若上游已支援 TSiP 後端;否則跟上游協商) |
| E-02 | Gateway 支援多個 `UPSTREAM_API_BASE_URL`(從單字串改為清單) |
| E-03 | 驗證跨實體機器的 Active Context 引用 ID 傳遞(in-memory dict 需升級為網路可達的儲存,如 Redis) |
| E-04 | Dashboard 觀測-1 面板擴充為「跨機節點視圖」 |
| E-05 | 修訂 [docs/03-agentic-orchestration/context-and-memory.md](../docs/03-agentic-orchestration/context-and-memory.md) §五 把「跨單機節點」改為「跨實體節點」實證紀錄 |

---

## Phase 5:圖形編排(延後評估)

啟動條件見 [docs/04-observability-dashboard/visualization-ui.md](../docs/04-observability-dashboard/visualization-ui.md) §四「Phase 2 啟動條件」(該文件已將圖形編排稱為「Phase 2」是 docs 視角的階段命名,在藍圖中對應到此 Phase 5)。

工作項待啟動時再展開,目前**完全不規劃**,以避免提早消耗認知資源。
