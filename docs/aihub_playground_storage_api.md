# AI Hub Playground Storage API

這份文件定義 AI Hub 為 Agentic SDK Playground 提供原始支援文件與 FAISS index artifact 持久化時，建議採用的資料模型與 API。它是 AI Hub Playground handoff / connection model 的下一版補充契約，不取代既有的 config save / load API。

現有 AI Hub connection model 文件仍是帳密驗證、Agent 清單、config load、config save 的 canonical contract：<https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>。

## 這份文件會幫你完成什麼

完成這一頁後，AI Hub 與 Playground 應能共同支援：

1. 使用者上傳的語意搜尋支援文件可隨 `agent_id` 持久保存。
2. 使用者重新載入同一個 Agent 時，可以找回原始文件。
3. 已建立過的 FAISS index 可作為 cache artifact 重用，避免每次進 Runner 都重新 embedding。
4. 當文件、embedding model 或 chunking 設定改變時，Playground 可以判斷 index 是否失效並重建。

## 設計原則

| 類型 | 角色 | 是否 canonical | 儲存目的 |
| --- | --- | --- | --- |
| 原始文件 | 使用者上傳的 `.txt`、`.md`、`.pdf`、`.pptx`、`.docx` 等支援文件 | Yes | 保留使用者知識來源，供 reload、重建 index、稽核與後續管理使用 |
| FAISS index artifact | 由原始文件、embedding model、chunking 設定產生的向量索引 | No | 加速 Runner 初始化，避免重複 embedding |

原始文件是長期真相來源。FAISS index 是可重建 cache，不應取代原始文件，也不應成為唯一可讀資料。

## Storage Layout

AI Hub 可以使用 Azure Storage Account 保存 blob。建議以 `agent_id` 作為第一層隔離單位：

```text
playground-agents/{agent_id}/files/{file_id}/{original_filename}
playground-agents/{agent_id}/artifacts/faiss/{artifact_id}/index.faiss
playground-agents/{agent_id}/artifacts/faiss/{artifact_id}/metadata.json
```

`file_id` 與 `artifact_id` 由 AI Hub 產生。檔名只作為顯示與下載用途，不作為唯一識別。

## File Metadata

AI Hub 保存每個原始文件時，至少需要記錄：

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `file_id` | string | Yes | AI Hub 產生的文件 id。 |
| `agent_id` | string | Yes | 文件所屬 Agent。 |
| `filename` | string | Yes | 使用者上傳時的檔名。 |
| `content_type` | string | Yes | MIME type。 |
| `size_bytes` | number | Yes | 檔案大小。 |
| `sha256` | string | Yes | 原始檔案內容 hash，用於 cache key 與重複檔案判斷。 |
| `role` | string | Yes | 建議固定為 `semantic_support`。 |
| `created_at` | string | Yes | ISO 8601 timestamp。 |
| `created_by` | string | Yes | AI Hub 使用者 id 或 username。 |

範例：

```json
{
  "file_id": "file_01JABCDEF123",
  "agent_id": "agt_01JABCDEF999",
  "filename": "產品手冊.pptx",
  "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "size_bytes": 2842210,
  "sha256": "9f3c...",
  "role": "semantic_support",
  "created_at": "2026-07-28T10:30:00Z",
  "created_by": "admin"
}
```

## FAISS Artifact Metadata

FAISS artifact 的 metadata 必須足以判斷「這份 index 是否能重用」。建議欄位：

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `artifact_id` | string | Yes | AI Hub 產生的 artifact id。 |
| `agent_id` | string | Yes | 所屬 Agent。 |
| `artifact_type` | string | Yes | 固定為 `faiss_index`。 |
| `file_ids` | string[] | Yes | 建立 index 時使用的文件 id 清單。 |
| `file_hashes` | string[] | Yes | 建立 index 時使用的文件 hash 清單，需排序後保存。 |
| `embedding_provider` | string | Yes | 例如 `openai-compatible`。 |
| `embedding_model` | string | Yes | 建立 embedding 的 model 名稱。 |
| `chunk_size` | number | Yes | 切 chunk 大小。 |
| `chunk_overlap` | number | Yes | chunk overlap。 |
| `index_format` | string | Yes | 例如 `faiss-flat-l2`。 |
| `index_version` | string | Yes | Playground index schema 版本，例如 `agentic-sdk-faiss-v1`。 |
| `cache_key` | string | Yes | 由上述關鍵欄位產生的穩定 hash。 |
| `created_at` | string | Yes | ISO 8601 timestamp。 |

範例：

```json
{
  "artifact_id": "art_01JINDEX123",
  "agent_id": "agt_01JABCDEF999",
  "artifact_type": "faiss_index",
  "file_ids": ["file_01JABCDEF123"],
  "file_hashes": ["9f3c..."],
  "embedding_provider": "openai-compatible",
  "embedding_model": "text-embedding-3-small",
  "chunk_size": 1000,
  "chunk_overlap": 120,
  "index_format": "faiss-flat-l2",
  "index_version": "agentic-sdk-faiss-v1",
  "cache_key": "sha256:4aa8...",
  "created_at": "2026-07-28T10:35:00Z"
}
```

`cache_key` 建議用以下資料正規化後計算 SHA-256：

```json
{
  "file_hashes": ["..."],
  "embedding_provider": "openai-compatible",
  "embedding_model": "text-embedding-3-small",
  "chunk_size": 1000,
  "chunk_overlap": 120,
  "index_format": "faiss-flat-l2",
  "index_version": "agentic-sdk-faiss-v1"
}
```

## API Overview

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| List Files | `GET` | `/api/playground/agents/{agent_id}/files` | 列出 Agent 的原始支援文件。 |
| Create Upload URL | `POST` | `/api/playground/agents/{agent_id}/files/upload-url` | 建立原始文件上傳 URL。 |
| Complete Upload | `POST` | `/api/playground/agents/{agent_id}/files/{file_id}/complete` | 上傳完成後寫入 metadata。 |
| Download File | `GET` | `/api/playground/agents/{agent_id}/files/{file_id}/download-url` | 取得原始文件下載 URL。 |
| Delete File | `DELETE` | `/api/playground/agents/{agent_id}/files/{file_id}` | 刪除原始文件與相關 metadata。 |
| Find FAISS Artifact | `GET` | `/api/playground/agents/{agent_id}/artifacts/faiss?cache_key=...` | 查詢可重用的 FAISS artifact。 |
| Create Artifact Upload URL | `POST` | `/api/playground/agents/{agent_id}/artifacts/faiss/upload-url` | 建立 FAISS artifact 上傳 URL。 |
| Complete Artifact Upload | `POST` | `/api/playground/agents/{agent_id}/artifacts/faiss/{artifact_id}/complete` | 上傳完成後寫入 artifact metadata。 |
| Download FAISS Artifact | `GET` | `/api/playground/agents/{agent_id}/artifacts/faiss/{artifact_id}/download-url` | 取得 FAISS artifact 下載 URL。 |

建議使用 pre-signed URL 或 Azure Blob SAS URL 進行大檔上傳/下載，避免 AI Hub Web API 直接代理大檔內容。

## Upload Flow

1. 使用者在 Playground Builder 上傳支援文件。
2. Playground 呼叫 AI Hub `Create Upload URL`。
3. Playground 使用回傳的 URL 將檔案上傳到 Storage Account。
4. Playground 呼叫 AI Hub `Complete Upload`，提交 `filename`、`content_type`、`size_bytes`、`sha256`、`role`。
5. AI Hub 將 file metadata 綁定到 `agent_id`。
6. Playground 更新 `python_source` 或 config metadata，保留 `file_id` 清單。

`python_source` 不應內嵌檔案內容。它可以保存語意搜尋設定與 file references，例如：

```json
{
  "retrieve": {
    "module": "SemanticRetrieve",
    "file_ids": ["file_01JABCDEF123"],
    "top_k": 3,
    "chunk_size": 1000,
    "chunk_overlap": 120
  }
}
```

## Runner Reload Flow

1. AI Hub handoff 或 Playground reload 載入 Agent config。
2. Playground 讀取 config 中的 `file_ids`。
3. Playground 呼叫 AI Hub `List Files` 或依 `file_id` 取得 file metadata。
4. Playground 根據 file hashes、embedding model、chunk config、index version 計算 `cache_key`。
5. Playground 呼叫 `Find FAISS Artifact`。
6. 如果找到相同 `cache_key` 的 artifact：
   - 下載 FAISS artifact。
   - 跳過 embedding rebuild。
   - Runner 初始化進度顯示「已載入語意索引」。
7. 如果找不到 artifact：
   - 下載原始文件。
   - 建立 embedding 與 FAISS index。
   - 上傳新的 FAISS artifact。
   - Runner 初始化進度顯示文件解析、embedding、index 建立進度。

## Invalidation Rules

FAISS artifact 在以下任一條件成立時不得重用：

1. 任一原始文件 `sha256` 改變。
2. `file_ids` 集合改變。
3. `embedding_model` 改變。
4. `embedding_provider` 或 endpoint family 改變。
5. `chunk_size` 或 `chunk_overlap` 改變。
6. `index_format` 或 `index_version` 改變。
7. AI Hub 判定 artifact 已過期、刪除或不可讀。

## Save Config Interaction

既有 config save API 不需要直接接收檔案 blob 或 FAISS binary。建議保持：

- Config save 保存 `python_source`、`workflow_name`、`description`、語意搜尋設定與 `file_ids`。
- File APIs 保存原始文件。
- Artifact APIs 保存 FAISS index cache。

這樣可以避免 config payload 過大，也能讓原始文件與 artifact 有獨立的權限、生命週期與審計紀錄。

## Current Playground Behavior Before This API Exists

在 AI Hub 完成這份 storage API 前，Playground 目前只能使用暫存目錄保存：

```text
{temp}/agentic-sdk-playground/builder-uploads/{builder_upload_id}
{temp}/agentic-sdk-playground/semantic-index/{builder_upload_id}
```

這些資料屬於 session/runtime cache，不保證跨 reload、重啟或 App Service instance 轉移後仍存在。

因此，在 storage API 完成前，Playground 應清楚提示使用者：語意搜尋支援文件尚未持久化；如果 reload 後暫存檔不存在，需要重新上傳支援文件。

## Security Requirements

1. 所有 API 必須驗證使用者對 `agent_id` 的讀寫權限。
2. Upload/download URL 必須短效，建議有效期不超過 15 分鐘。
3. AI Hub 必須限制單檔大小、總容量、檔案類型與上傳頻率。
4. AI Hub 應保存 `created_by`、`created_at`、`deleted_by`、`deleted_at` 等審計欄位。
5. Storage Account 不應公開；外部存取一律透過短效 URL 或 AI Hub 授權流程。
6. 刪除 Agent 時，AI Hub 應同步清除相關原始文件與 artifacts，或依保留政策標記為待清理。

## Recommended Rollout

1. 第一階段：實作原始文件 upload/list/download/delete API。
2. 第二階段：Playground save config 保存 `file_ids`，reload 後可下載原始文件並重建 index。
3. 第三階段：實作 FAISS artifact upload/find/download API，使用 `cache_key` 避免重複 embedding。
4. 第四階段：加入 artifact lifecycle policy，例如容量限制、LRU 清理、版本失效與管理介面。