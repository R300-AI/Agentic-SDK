# OpenAI-Compatible API — 對外端點規格 [R01]

> 受眾:應用端開發者(LangChain / AutoGen / OpenAI SDK 使用者)
> 目的:說明 Agentic SDK Gateway 對外提供的 OpenAI 相容端點規格,以及不同於 OpenAI 官方的行為差異。

## 一、設計原則

> **改 `base_url` 即可使用,業務程式碼一行不動。**

這條原則是本 API 規格設計的唯一準繩。任何違反此原則的端點設計,即使技術上更優雅,也不採用。

## 二、PoC 階段實作的端點

| 端點 | 狀態 | 備註 |
|------|------|------|
| `POST /v1/chat/completions` | ✅ 含 SSE 串流 | 完整支援,內部觸發五節點工作流 |
| `GET /v1/models` | ✅ | 轉發上游推論伺服器的回應 |
| `POST /v1/workflow/run` | ✅ | 接 WorkflowConfig YAML + user_message(+ 可選 attachments),於背景非同步跑工作流,立即回 `workflow_id` 與 `stream_url`;UI / 第三方編排器專用 |
| `GET /v1/workflow/{id}/stream` | ✅ | Server-Sent Events,推送該 workflow 的 telemetry 事件;含節點起訖與 `workflow.node.delta`(Action 串流 token) |
| `GET /v1/workflow/{id}/result` | ✅ | SSE 結束後拉一次,取 `final_message` / `aborted` / `visit_counts` / `usage` |
| `POST /v1/embeddings` | ❌ 未實作 | Retrieve 節點用本地 sentence-transformers,不依賴此端點 |
| `POST /v1/audio/transcriptions` | ❌ 未實作 | 待第二個使用者出現再評估 |
| `POST /v1/fine_tuning/*` | ❌ 不實作 | 不在本專案範圍 |
| `POST /v1/assistants/*` | ❌ 不實作 | 與本專案 Agent 編排理念衝突,改用內部編排層 |

## 三、`POST /v1/chat/completions`

### Request

完全相容 OpenAI 規格:

```http
POST /v1/chat/completions
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "gemma3-4b-npu",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": true,
  "temperature": 0.7
}
```

**`model` 欄位語意**:直接傳遞給上游推論伺服器,模型 ID 由上游 [amd-ryzen-ai-benchmark README](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 的「📦 支援的模型列表」決定(例:`gemma3-4b-npu`、`gemma4-2b-gpu`)。本專案不重新命名、不加裝飾。

### Response

`stream=false`:回傳結構同 OpenAI,額外於 `x-agentic-metadata` header 附帶五節點工作流的中間紀錄:

```
x-agentic-metadata: {"upstream_model_id":"gemma3-4b-npu","workflow_id":"...","nodes_visited":["perceive","plan","action"],"ttft_ms":820}
```

此 header 為附加資訊,不影響相容性——OpenAI SDK 會忽略未知 header。

`stream=true`:遵循 OpenAI SSE 格式 `data: {...}\n\n`,結尾 `data: [DONE]`。在第一個 `chat.completion.chunk` 之前插入 metadata chunk:

```
data: {"object":"agentic.metadata","workflow_id":"...","upstream_model_id":"gemma3-4b-npu","ttft_ms":820}
```

`object` 開頭非 `chat.completion.chunk` 的事件,主流 OpenAI SDK 會自動跳過,不破壞相容性。

工作流執行過程中的節點進度事件,額外推送至遙測 buffer(供 Dashboard 觀測-3 面板讀取),**不**透過 SSE 推給呼叫端,避免汙染 OpenAI 標準回應流。

## 四、`POST /v1/workflow/run` + SSE(編排器專用)

`/v1/chat/completions` 把整條工作流包成 OpenAI 形態,適合「想當作 LLM 用」的呼叫端。但若呼叫端是**自製編排器或圖形編輯器**(本專案 `demo/` 是第一個案例),需要的不是「最終回應字串」,而是「五節點的逐 token 進度 + 最終結果」。為此 Gateway 另開一組 `/v1/workflow/*` 端點,語意不與 OpenAI 相容,但 schema 對齊 [telemetry-metrics.md](../04-observability-dashboard/telemetry-metrics.md)。

### 4.1 `POST /v1/workflow/run`

```json
{
  "workflow_yaml": "<完整 WorkflowConfig YAML>",
  "user_message": "請幫我查...",
  "attachments": [
    {"kind": "image", "mime": "image/png", "data_url": "data:image/png;base64,..."}
  ]
}
```

立即回:

```json
{ "workflow_id": "abc...", "stream_url": "/v1/workflow/abc.../stream" }
```

工作流於背景非同步執行,呼叫端必須立刻訂閱 SSE 才不會漏事件。

###六4.2 `GET /v1/workflow/{id}/stream`(SSE)

每筆 `data:` 為一個 telemetry 事件,共三類:

| event_name | 何時出現 | 主要欄位 |
|------------|----------|----------|
| `workflow.node.start` | 節點進入 | `workflow_node`、`workflow_node_visit` |
| `workflow.node.delta` | **Action 節點串流 token**(每收到一個 chunk 就推一筆) | `workflow_node="action"`、`delta_text`、`delta_index` |
| `workflow.node.finish` | 節點離開(無 `workflow_next_node` 代表整條結束) | `workflow_node`、`workflow_next_node`、`duration_ms`、`gen_ai_response_model`、`gen_ai_usage_*` |

`delta_text` 即可在前端逐字累加渲染,實現 ChatGPT 樣的即時打字效果。Plan / Reflect 節點雖然內部也走 stream(用 httpx idle timeout 取代 wall-clock timeout,長 Thought 不會被砍),但**不**對外發 delta — 它們的輸出是結構化 JSON,只在 finish 事件公布結果。

SSE 在以下任一條件結束:
- 收到「沒有 `workflow_next_node` 的 `workflow.node.finish`」(正常終止)
- 收到 `workflow.fallback`(中止)
- 連線開啟超過 600 秒(寫死的硬上限,僅作為連線洩漏的安全網)

### 4.3 `GET /v1/workflow/{id}/result`

SSE 結束後拉一次,取最終結果:

```json
{
  "workflow_id": "abc...",
  "final_message": "整段最終回應...",
  "aborted": false,
  "abort_reason": null,
  "visit_counts": {"perceive": 1, "plan": 2, "retrieve": 1, "action": 1, "reflect": 1},
  "usage": {"model": "gpt-5.2", "input_tokens": null, "output_tokens": null}
}
```

> 串流模式下 `input_tokens` / `output_tokens` 為 `null`,因為 OpenAI 串流 chunk 不附 usage。`final_message` 仍可由 SSE delta 累加在前端取得,呼叫端可二選一。

## 五、`GET /v1/models`

直接轉發上游回應,僅在每筆 model 物件補上 `agentic_extension`:

```json
{
  "object": "list",
  "data": [
    {
      "id": "gemma3-4b-npu",
      "object": "model",
      "created": 1717804800,
      "owned_by": "upstream-ryzen-ai-benchmark",
      "agentic_extension": {
        "upstream_base_url": "http://localhost:8000/v1",
        "supports_vision": true
      }
    }
  ]
}
```

`agentic_extension` 為附加欄位,標準 OpenAI SDK 會忽略。**模型認證與 SLA 履歷由上游負責**,Gateway 不二次驗證(詳見 [02-model-card-contract/upstream-integration.md](../02-model-card-contract/upstream-integration.md))。

## 五、與 OpenAI 官方的行為差異

明示差異,避免使用者誤判:

| 行為 | OpenAI | Agentic SDK |
|------|--------|-------------|
| `model` 欄位語意 | OpenAI 模型名稱 | 上游 `api.py` 支援的模型 ID(見上游 README) |
| `/v1/models` 內容 | OpenAI 帳號可用模型 | 上游當前載入的模型(由使用者啟動 `api.py` 時決定) |
| 計費 | Usage-based | 不計費,僅記錄 token 使用量於遙測層 |
| Rate Limit 回應 | 429 + `Retry-After` header | 同 OpenAI 行為,上限由 `INFER_REQUEST_TIMEOUT_SEC` 與上游處理能力共同決定 |
| Function calling | 完整支援 | PoC 階段透過 Action 節點實作,不直接支援 OpenAI function calling 欄位(MVP 後評估) |
| Vision LM | 完整支援 | 直接透傳給上游,上游 Vision LM 模型(如 `gemma3-4b-npu`)即支援 |
| 工作流可觀測 | 不存在此概念 | `x-agentic-metadata` 帶五節點軌跡;Dashboard 觀測-3 即時呈現 |
