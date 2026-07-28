# AI Hub Playground Storage API

這份文件定義 Agentic SDK Playground 與 AI Hub Storage API 的 MVP 串接方式。它補充 AI Hub connection model，不取代既有 config save / load API。

Canonical AI Hub 文件：

- Connection model: <https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>
- Storage API: <https://r300-ai.github.io/ai-hub-webui/playground/storage-api/>

## 這份文件會幫你完成什麼

完成這一頁後，Playground 應能支援：

1. 使用者把同一個 Agent 的 runtime bundle 保存到 Storage Account。
2. 使用者重新打開同一個 Agent 時，Playground 可以讀回同一包 bundle。
3. Agentic SDK / SemanticRetriever 自行解讀 bundle、還原原始支援文件與 vectorstore。
4. AI Hub 只驗證權限並簽發短效 upload/download URL，不接收、不解析、不處理 zip 內容。

## 設計原則

| 元件 | 責任 |
| --- | --- |
| AI Hub config API | 保存 `python_source`、`workflow_name`、`description`，建立或更新 Agent，回傳 `agent_id`。 |
| AI Hub Storage API | 依 `agent_id` 驗證權限，簽發短效 Storage Account upload/download URL。 |
| Storage Account | 保存單一 `agentic_playground_bundle.zip` blob。 |
| Agentic SDK / SemanticRetriever | 打包、解包、解析原始支援文件、載入或重建 vectorstore。 |

AI Hub 不解析 zip，不讀 manifest，不檢查 zip 內有哪些檔案，不解讀 source files 如何 chunk，也不解讀 vectorstore 格式。

## Storage Layout

每個 `agent_id` 對應一個固定 zip blob path：

```text
playground-agents/{agent_id}/bundle/agentic_playground_bundle.zip
```

zip 內部結構由 Agentic SDK 管理。建議目前 Playground 產生的 bundle 包含：

```text
agentic_playground_bundle.zip
├─ manifest.json
├─ recipe/
│  ├─ python_source.py
│  └─ metadata.json
└─ tmp/
  ├─ source-files/
  │  └─ {original uploaded files}
  └─ vectorstore/
    └─ {SemanticRetriever vectorstore files}
```

`manifest.json`、`recipe/metadata.json` 與 vectorstore 內容都屬於 Agentic SDK runtime contract；AI Hub 只保存與讀回整包 zip。

## API Overview

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| Get Bundle Upload URL | `POST` | `/api/playground/agents/{agent_id}/bundle/save` | AI Hub 驗證權限後，回傳可 `PUT` zip 的短效 URL。 |
| Get Bundle Download URL | `GET` | `/api/playground/agents/{agent_id}/bundle/load` | AI Hub 驗證權限後，回傳可 `GET` zip 的短效 URL。 |

正式 API 不承載 zip bytes。Playground 拿到 URL 後，直接對 Storage Account `PUT` / `GET`。

## Save Flow

1. Playground 先依 connection model 呼叫 `POST /api/playground/config/save`。
2. 第一次保存新 Agent 時，不帶 `agent_id`；AI Hub 建立 Agent 並回傳 `agent_id`。
3. 後續保存既有 Agent 時，帶同一個 `agent_id`。
4. Playground 以最新 runtime 狀態產生 `agentic_playground_bundle.zip`。
5. Playground 呼叫 `POST /api/playground/agents/{agent_id}/bundle/save` 取得 upload URL。
6. Playground 使用 response 中的 `upload_method`、`upload_url` 與 `upload_headers` 直接 PUT zip 到 Storage Account。
7. Storage Account PUT 成功後，Playground 才能視為完整保存成功。

Upload URL response 範例：

```json
{
  "agent_id": "agt_001",
  "issued_at": "2026-07-28T12:00:00Z",
  "bundle_root": "playground-agents/agt_001/bundle",
  "bundle_path": "playground-agents/agt_001/bundle/agentic_playground_bundle.zip",
  "upload_url": "https://<account>.blob.core.windows.net/<container>/playground-agents/agt_001/bundle/agentic_playground_bundle.zip?...",
  "upload_url_expires_at": "2026-07-28T12:15:00Z",
  "upload_method": "PUT",
  "upload_headers": {
    "x-ms-blob-type": "BlockBlob"
  }
}
```

## Load Flow

1. 使用者選擇既有 Agent。
2. Playground 先依 connection model 呼叫 config load，取得 `python_source`、`workflow_name`、`description`。
3. Playground 呼叫 `GET /api/playground/agents/{agent_id}/bundle/load` 取得 download URL。
4. Playground 直接從 Storage Account GET `agentic_playground_bundle.zip`。
5. Playground 解壓 zip 到 runtime temp path。
6. Runner 初始化時使用 bundle 內的 source files 與 vectorstore。

Download URL response 範例：

```json
{
  "agent_id": "agt_001",
  "bundle_path": "playground-agents/agt_001/bundle/agentic_playground_bundle.zip",
  "download_url": "https://<account>.blob.core.windows.net/<container>/playground-agents/agt_001/bundle/agentic_playground_bundle.zip?...",
  "download_url_expires_at": "2026-07-28T12:15:00Z",
  "download_method": "GET"
}
```

如果 bundle 不存在，Playground 可以退回 config-only 載入，但必須提示語意搜尋支援文件與 vectorstore 尚未恢復。

## Playground Implementation Notes

Playground 端實作分成三層：

1. `aihub_client`：只呼叫 AI Hub config API 與 bundle URL API。
2. `bundle_store`：建立 / 還原 `agentic_playground_bundle.zip`，並對 signed URL 執行 PUT / GET。
3. route orchestration：在 config save/load 成功後，串接 bundle save/load。

完整保存成功條件：

```text
config/save 成功 + bundle upload URL 成功 + Storage Account PUT 成功
```

重新打開成功條件：

```text
config/load 成功 + bundle download URL 成功 + Storage Account GET 成功 + zip 還原成功
```

## 非 MVP 範圍

MVP 不包含：

- zip 內容轉送
- JSON base64 bundle payload
- 逐檔 upload/list/delete API
- per-file metadata
- cache key / invalidation policy
- artifact lifecycle
- quota / retention / audit / LRU
- 多版本 bundle 管理
- vector database 查詢能力

這些能力若未來需要，應另開規格；不應阻塞目前 zip bundle MVP。
