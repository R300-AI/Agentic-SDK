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

## 四、`GET /v1/models`

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
