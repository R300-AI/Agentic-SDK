# Storage

這一頁說明 Playground 如何保存與讀回 runtime bundle。AI Hub 負責簽發短效 Storage URL，Playground 負責打包、上傳、下載與還原 bundle。

AI Hub 相關文件：

- Connection model: <https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>
- Storage API: <https://r300-ai.github.io/ai-hub-webui/playground/storage-api/>
- 維運導讀：[整合自訂遊樂場](https://r300-ai.github.io/ai-hub-webui/platform-maintenance/custom-playground-integration/)
- 責任邊界：[連線方式與責任邊界](https://r300-ai.github.io/ai-hub-webui/platform-maintenance/custom-playground-integration/connection-and-responsibility/)
- 保存與讀回：[工作流保存與讀回](https://r300-ai.github.io/ai-hub-webui/platform-maintenance/custom-playground-integration/workflow-save-load/)

本頁對應 AI Hub 維運文件中的「工作流保存與讀回」：AI Hub 簽發短效上傳/下載 URL，Playground 打包、上傳、下載與還原 `agentic_playground_bundle.zip`。

## AI Hub 團隊先看這裡

Storage 串接分成兩件事：

| 使用情境 | AI Hub 要做的事 | Playground 要做的事 | 完成結果 |
| --- | --- | --- | --- |
| 保存 Agent | 驗證使用者權限，簽發短效 upload URL | 打包 `agentic_playground_bundle.zip`，再 PUT 到 Storage Account | Agent 設定與 runtime bundle 都保存完成 |
| 打開既有 Agent | 驗證使用者權限，簽發短效 download URL | 下載 zip，解壓到執行時暫存目錄 | Runner 可以使用原本的參考文件與 vectorstore |

AI Hub 端需要協助處理：

1. 在 config save/load 之外，提供 bundle save/load URL API。
2. 依 `agent_id` 驗證使用者是否能保存或讀回 bundle。
3. 簽發可直接對 Storage Account `PUT` / `GET` 的短效 URL。
4. 回傳 URL、HTTP method、必要 headers 與過期時間。

對 `SemanticRetrieve` Agent 來說，bundle save/load 是必要流程，不是附加備份。若 AI Hub 只完成 config save/load，使用者當次建立時仍可能查得到上傳資料，但重新載入後不會有原本的參考文件與 vectorstore。

## 這份文件會幫你完成什麼

完成這一頁後，Playground 應能支援：

1. 使用者把同一個 Agent 的 runtime bundle 保存到 Storage Account。
2. 使用者重新打開同一個 Agent 時，Playground 可以讀回同一包 bundle。
3. Agentic SDK / SemanticRetriever 解讀 bundle，還原原始參考文件與 vectorstore。
4. AI Hub 驗證權限並簽發短效 upload/download URL。

## 設計原則

| 元件 | 責任 |
| --- | --- |
| AI Hub config API | 保存 `python_source`、`workflow_name`、`description`，建立或更新 Agent，回傳 `agent_id`。 |
| AI Hub Storage API | 依 `agent_id` 驗證權限，簽發短效 Storage Account upload/download URL。 |
| Storage Account | 保存單一 `agentic_playground_bundle.zip` blob。 |
| Agentic SDK / SemanticRetriever | 打包、解包、解析原始參考文件、載入或重建 vectorstore。 |

zip 內容由 Agentic SDK 管理。AI Hub 保存整包 zip，並負責權限驗證與短效 URL。

## 儲存位置

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

`manifest.json`、`recipe/metadata.json` 與 vectorstore 內容都屬於 Agentic SDK runtime 資料。AI Hub 保存與讀回整包 zip。

## API 一覽

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| Get Bundle Upload URL | `POST` | `/api/playground/agents/{agent_id}/bundle/save` | AI Hub 驗證權限後，回傳可 `PUT` zip 的短效 URL。 |
| Get Bundle Download URL | `GET` | `/api/playground/agents/{agent_id}/bundle/load` | AI Hub 驗證權限後，回傳可 `GET` zip 的短效 URL。 |

Playground 拿到 URL 後，直接對 Storage Account `PUT` / `GET`。

## 保存流程

1. Playground 先依 connection model 呼叫 `POST /api/playground/config/save`。
2. 第一次保存新 Agent 時，AI Hub 建立 Agent 並回傳新的 `agent_id`。
3. 後續保存既有 Agent 時，帶同一個 `agent_id`。
4. Playground 以最新 runtime 狀態產生 `agentic_playground_bundle.zip`。
5. Playground 呼叫 `POST /api/playground/agents/{agent_id}/bundle/save` 取得 upload URL。
6. Playground 使用 response 中的 `upload_method`、`upload_url` 與 `upload_headers` 直接 PUT zip 到 Storage Account。
7. Storage Account PUT 成功後，Playground 才能視為完整保存成功。

若此 Agent 使用 `SemanticRetrieve` 且 bundle 保存失敗，Playground 會回傳 `config_saved: true`、`saved: false`、`bundle_saved: false`。這表示 AI Hub 的 config 已保存，但知識庫 runtime 尚未保存，之後重新載入不能保證語意搜尋可用。

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

## 讀回流程

1. 使用者選擇既有 Agent。
2. Playground 先依 connection model 呼叫 config load，取得 `python_source`、`workflow_name`、`description`。
3. Playground 呼叫 `GET /api/playground/agents/{agent_id}/bundle/load` 取得 download URL。
4. Playground 直接從 Storage Account GET `agentic_playground_bundle.zip`。
5. Playground 解壓 zip 到執行時暫存目錄。
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

如果 bundle 尚未建立，一般非檢索型 Agent 可以先載入 config。對使用 `SemanticRetrieve` 且依賴上傳支援文件的 Agent，bundle 是恢復知識庫的必要資料；Playground 需要阻止它以「已完整載入」狀態進入 Runner，或明確停在可修復的錯誤狀態。

匿名分享入口目前只載入公開 `python_source`。如果 AI Hub 需要讓匿名唯讀 Runner 也能使用 `SemanticRetrieve` 知識庫，AI Hub 需要另行提供可公開授權的 bundle 讀回方式，或在公開 config load 回應中提供等價的 bundle download 能力。

## Playground 實作分工

Playground 端實作分成三層：

1. `aihub_client`：呼叫 AI Hub config API 與 bundle URL API。
2. `bundle_store`：建立 / 還原 `agentic_playground_bundle.zip`，並對 signed URL 執行 PUT / GET。
3. route 串接：在 config save/load 成功後，串接 bundle save/load。

完整保存成功條件：

```text
config/save 成功 + bundle upload URL 成功 + Storage Account PUT 成功
```

重新打開成功條件：

```text
config/load 成功 + bundle download URL 成功 + Storage Account GET 成功 + zip 還原成功
```

對不需要 runtime bundle 的 Agent，config/load 成功即可建立 Runner session；對 `SemanticRetrieve` 知識庫型 Agent，上述 bundle 條件必須成立，否則只能算 config 讀回成功，不能算知識庫恢復成功。

## 後續擴充項目

下列能力可在後續規格處理：

- zip 內容轉送
- JSON base64 bundle payload
- 逐檔 upload/list/delete API
- per-file metadata
- cache key / 快取更新規則
- artifact lifecycle
- quota / retention / audit / LRU
- 多版本 bundle 管理
- vector database 查詢能力

目前版本先以單一 zip bundle 完成保存與讀回流程。
