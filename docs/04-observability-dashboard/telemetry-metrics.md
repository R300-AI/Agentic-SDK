# Telemetry Metrics — token/sec、記憶體峰值的遵測資料流 [R03] [R25]

> 受眾：觀測層開發
> 目的：定義 Agentic SDK 內部產生的遙測資料種類、流向,以及與外部 Observability 平台的對接點。

## 〇、Phase 1 實作策略(現況)

長期方向是 OpenTelemetry(下方第三節「資料流架構」即為終態),但 Phase 1 採**最輕實作**:

| 元件 | Phase 1 實作 | Phase 2/3 升級目標 |
|------|--------------|--------------------|
| 事件發送介面 | Python `logging`,呼叫端寫 `logger.info(..., extra={"event": {...}})` | 不變(Handler 抽換即可) |
| 緩衝層 | `agentic_sdk.observability.RingBufferHandler`(in-memory deque,固定上限) | 加 `OTLPLogExporter` 推送至本機 collector |
| 可選持久化 | `logging.FileHandler` 寫 JSONL(由 `TELEMETRY_JSONL_PATH` 啟用) | collector 接 Phoenix / Tempo |
| Dashboard 取資料方式 | HTTP pull:`GET /internal/telemetry/snapshot` | 改連 Phoenix / Grafana 既有 UI,或保留自製 Dashboard 接 collector |

### 為什麼 Phase 1 不直接上 OTel SDK?

- **OTel 真正的價值在跨節點 trace 串接**(Phase 2 五節點上線後才有此需求)與**跨機器聚合**(Phase 3)
- Phase 1 只有 Gateway 一個行程、Dashboard 一個讀者,logging + ring buffer 的 50 行實作即可滿足
- 完整 OTel 鏈(SDK + collector + 後端)在 PoC 階段會把 80% 心力花在配置對接上,違反 YAGNI

### 為什麼 Phase 2 能無痛升級

- **事件 attribute key 從第一天就對齊 OpenTelemetry Semantic Conventions 1.27**(GenAI + HTTP + Error 穩定子集),Phase 2 升 OTel SDK 時只換 emit 機制,事件 schema 不變
- 呼叫端只認 `logging.Logger` 介面;`RingBufferHandler` 換成 `LoggingHandler`(OTel)是 wire-up 一行的事
- 詳細 schema 與事件名稱常數見 [`agentic_sdk/observability/events.py`](../../agentic_sdk/observability/events.py)

---

## 一、為什麼觀測必須是第一公民

跨節點 Agent 工作流的失敗模式幾乎不會發出例外——它們表現為「越來越慢」「結果品質下降」「偶爾失準」。沒有觀測資料,這類失敗無法歸因,也無法量化改善。

本專案把觀測層的優先級提到與編排層同等,而非事後加裝的旁支功能。

## 二、遙測資料分類

| 分類 | 來源 | 取樣頻率 | 用途 |
|------|------|----------|------|
| **推論指標**(TTFT、tokens/sec、output length) | Runner 容器內部計時 | 每次請求 | 對齊 Model Card SLA,偵測效能退化 [R03] |
| **資源指標**(NPU/iGPU/CPU 使用率、可用記憶體) | 節點層 sidecar 監控 | 每秒 1 次 | Offload 決策依據、容量規劃 |
| **叢集拓樸**(節點清單、每節點正在運行的模型 runner) | Gateway 定期推送 | 每 10 秒 | Multi-Model Dashboard 需求 1(叢集拓樸與健康度) |
| **多模型資源競爭**(同一節點上所有模型的記憶體 / 算力使用率並列時序) | sidecar + Gateway 聚合 | 每 5 秒 | Multi-Model Dashboard 需求 2(多模型資源視圖) |
| **跨模型工作流分配**(工作流 ID × 節點 → 實際執行的模型 ID) | Orchestrator 注入 | 事件驅動 | Multi-Model Dashboard 需求 3(跨模型分配檢視) |
| **工作流事件**(節點轉換、Reflect 回環、降級事件) | Orchestrator 注入 | 事件驅動 | 工作流品質歸因 |
| **錯誤與告警**(OOM、上下文降級、Model Card 驗證失敗) | 全層注入 | 事件驅動 | 立即告警與根因分析 |

其中 **叢集拓樸、多模型資源競爭、跨模型工作流分配** 這三類是 Multi-Model Dashboard 獨有的需求,在 Phoenix / LangSmith 中不會出現——這是本專案補位的關鍵視角。

## 三、資料流架構

```
┌──────────────────────────────────────────────────────┐
│  Runner 容器 / Gateway / Offload Engine               │
│         ↓ OpenTelemetry SDK (trace + metric)          │
│  OTLP 協定(gRPC over localhost)                      │
│         ↓                                              │
│  agentic-sdk-otel-collector(每節點 1 個 sidecar)     │
│         ↓ 可同時匯出多個 backend                       │
│  ┌────────────┬─────────────┬──────────────────┐    │
│  │ Prometheus │ Phoenix [R25] │ JSON file (PoC)  │    │
│  │ (resource) │ (LLM trace) │ (debug)          │    │
│  └────────────┴─────────────┴──────────────────┘    │
└──────────────────────────────────────────────────────┘
```

選擇 OpenTelemetry 的理由:
- 業界標準,Phoenix / LangSmith / Datadog 皆原生支援
- 雙資料模型(metric + trace)可同時涵蓋資源與工作流
- 對應用碼幾乎零侵入(裝飾器層級即可)

## 四、關鍵指標規格

每個指標都附明確的單位、標籤、聚合方式,避免 Dashboard 端的解讀歧義:

### TTFT(Time To First Token)
- 單位:毫秒
- 標籤:`upstream_model_id`, `upstream_base_url`
- 聚合:P50 / P95 / P99 滑動視窗 5 分鐘
- 告警閾值:P95 超過上游 README 註明的實測值(若有)130% 持續 3 分鐘

### tokens/sec
- 單位:tokens per second
- 標籤:同 TTFT,加 `phase=prefill|decode`
- 聚合:每分鐘平均

### Gateway 側記憶體使用
- 單位:MB
- 標籤:`process=gateway|dashboard`
- 聚合:每分鐘最大值
- 告警閾值:Gateway 行程 RSS 超過 1 GB 持續 5 分鐘(PoC 兩條軸合併作為單行程的預算上限)

### 工作流降級事件
- 型別:counter
- 標籤:`reason=context_evicted|offload_fallback|workflow_timeout|max_hops`
- 聚合:每小時計數
- 告警閾值:任一 reason 在 1 小時內超過 10 次

### 多模型並列快照(Multi-Model 獨有,Phase 4 驗證)
- 型別:gauge 陣列
- 標籤:`upstream_base_url`,內容為同一 Gateway 連接的所有上游的即時健康狀態
- 聚合:每 5 秒 snapshot
- 用途:Dashboard 觀測-1 面板的來源資料;Phase 1–3 隻上游時只有一個條目

### 跨模型工作流路徑(Multi-Model 獨有)
- 型別:trace event
- 標籤:`workflow_id`, `node_name`, `upstream_model_id`
- 聚合:每個工作流一條路徑記錄
- 用途:Dashboard 觀測-3 面板的來源資料,回答「哪個節點質獻了多少延遲」

## 五、配置驅動(反硬編碼)

| 配置項 | 預設值 | 量化依據 |
|--------|--------|----------|
| `OTEL_EXPORT_INTERVAL_SEC` | `10` | 平衡時效性與 IO 負擔,過去 Phoenix 部署觀察值 |
| `RESOURCE_SAMPLE_INTERVAL_SEC` | `1` | 1 秒粒度足以捕捉 Offload 決策所需的記憶體變動 |
| `TELEMETRY_LOCAL_BUFFER_MB` | `100` | 對外網路中斷時的本地暫存上限,約等於 24 小時的工作流事件量 |

## 六、PoC 範圍

| 範圍 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| Gateway 結構化事件(logging + RingBuffer) | ✅ | ✅(維持) | ✅(轉由 OTel handler 取代) |
| 事件 schema 對齊 OTel SemConv(GenAI / HTTP / Error) | ✅ | ✅ | ✅ |
| Runner 內 TTFT、tokens/sec 量測 | ⚠️ 僅蒐集 usage tokens,TTFT 留待五節點接入 | ✅ | ✅ |
| Streamlit Dashboard(pull `/internal/telemetry/snapshot`) | ✅ | ✅(加上五節點面板) | 視需求保留或改 Grafana |
| OpenTelemetry Collector 部署 | ❌(避免 PoC 配置爆炸) | ⚠️ 評估 | ✅ |
| 接 Phoenix 做 LLM trace 視覺化 | ❌ | ⚠️ 評估 | ✅(若多機需求成立) |
| 跨節點 trace stitching | ❌ | ✅(OTel context propagation) | ✅ |
