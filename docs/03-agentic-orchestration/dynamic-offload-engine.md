# Dynamic Offload Engine — 邊緣端異質卸載策略(延伸方向)[R02] [R24]

> 受眾:資源層開發、長期路線圖規劃者
> 目的:說明為何 PoC 階段**不做** 動態 Offload、未來啟用時的契約輪廓,以及與上游推論伺服器的責任邊界。

## 定位:在 Action Item 中的角色

| 層面 | 狀態 |
|------|------|
| 是否為現階段 Action Item | ❌ 不是 |
| 是否為必然趨勢 | ✅ 邊緣叢集資源有限,動態 Offload 為中長期必然需求 |
| PoC 階段如何處理 | 「模型 × 硬體」靜態綁定,由**使用者啟動哪個上游 `api.py` 模型**決定 |
| 現階段文件的作用 | 預留契約輪廓,避免未來啟用時需大幅改動 SDK 的對外介面 |

## 一、PoC 階段為何不做

PoC 階段「模型在哪個硬體執行」這件事的責任歸屬:

| 責任 | 歸屬 |
|------|------|
| 模型權重在哪個硬體載入 | **上游** [`amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) `api.py` 啟動時的 `--model` 參數 |
| 使用者切換硬體 | **使用者** 自行停止舊 `api.py`、啟動另一個模型 ID(例:`gemma3-4b-npu` → `gemma4-2b-gpu`) |
| Agentic SDK 介入硬體選擇 | ❌ 不介入。Gateway 只認識一個 `UPSTREAM_API_BASE_URL` |

意即:**PoC 階段沒有「Offload Engine」這個元件**。本文件的剩餘內容描述的是未來若需要時的設計輪廓,不在 M0–M3 範圍。

## 二、未來啟用時的觸發條件

以下任一條件成立,才考慮啟用本元件:

- 上游 `api.py` 開始支援單一行程內多模型熱切換(目前單行程只服務一個模型)
- 部署規模擴張到單機跑多個 `api.py` 行程(各服務不同硬體),Gateway 需要選擇路由
- 出現「同一節點不同請求需走不同硬體」的真實業務場景

未達成上述條件時,本元件**持續延後**,工程資源不投入。

## 三、未來契約輪廓(預留接口)

當啟用時,Gateway 的 `UPSTREAM_API_BASE_URL` 配置從單字串擴充為多上游清單:

```env
UPSTREAM_API_BASE_URL=[
  "http://localhost:8000/v1",   # gemma3-4b-npu
  "http://localhost:8001/v1",   # gemma4-2b-gpu
]
```

Offload Engine 在 `POST /v1/chat/completions` 進入時,根據以下輸入選擇上游:

```
輸入:
  - 請求指定的 model ID
  - 各上游當下回報的健康度 / 排隊深度
  - 五節點工作流中當前節點的 required_capability

輸出:
  - 目標上游 base_url
  - 若所有上游皆飽和 → 進入排隊 or 回傳 429
```

關鍵設計約束:**Offload Engine 不替代上游做「模型載入到哪個硬體」的決策**——這仍是上游的責任。Engine 只在「多個已運行的上游之間」做路由選擇。

## 四、與觀測層的契約(預留)

未來啟用時,每次決策必須產出事件,由觀測層收集:

```json
{
  "event": "offload_decision",
  "request_id": "...",
  "model_id": "gemma3-4b-npu",
  "selected_upstream": "http://localhost:8000/v1",
  "fallback_used": false,
  "upstream_queue_depth_snapshot": {"http://localhost:8000/v1": 0, "http://localhost:8001/v1": 3},
  "decision_latency_ms": 3
}
```

`fallback_used=true` 是關鍵告警訊號——代表首選上游已壓力過高,需要評估擴容。

Dashboard 觀測-4 面板(降級事件 log)在 Engine 啟用後會新增此事件類型。

## 五、未解決的設計問題(預留)

未啟用前不強求答案,但記入待解:

- **跨上游的 Active Context 一致性**:同一工作流的不同節點被路由到不同上游時,Active Context 如何同步(可能需要 Redis 統一存放,呼應 [context-and-memory.md](context-and-memory.md) Phase 4)
- **抖動抑制**:上游負載在閾值附近波動時的決策遲滯設計
- **冷啟動代價告知**:被路由到非首選上游的請求 TTFT 升高,是否在 `x-agentic-metadata` 中明示
