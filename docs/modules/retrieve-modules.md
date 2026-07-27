# Retrieve

Retrieve 模組負責把 workflow 需要的內容取回來。這一頁先整理 Retrieve 家族中的檢索角色，再依序展開目前文件採用的檢索模組與配套元件。每個模組會先列出建立物件時使用的初始化參數；檢索過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解。

## KeywordRetrieve

舊名對應：`KeywordRetrieve`

`KeywordRetrieve` 依關鍵字規則取回內容，適合 README 的最小流程與條目式知識查找。它代表的是最直接的檢索路徑：有明確查詢字串，就回傳最對應的條目內容。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `items` | `array<object>` | 否 | `[]` | 關鍵字條目清單；每筆通常包含 `keywords` 與 `content`。 |
| `fallback` | `string` | 否 | `"沒有命中任何條目。"` | 沒有命中任何條目時寫入取回內容的文字。 |

## SemanticRetrieve

舊名對應：`SemanticRetrieve`

`SemanticRetrieve` 依語意相似度從知識來源取回內容。當流程需要從較長知識片段裡找出真正相關的內容時，這個模組會把檢索重心放在語意接近度。

從這個版本開始，`SemanticRetrieve` 對外採用統一配置介面：應用層優先提供 embedding provider、OpenAI-compatible 端點、索引路徑與來源文件路徑；SDK 內部再自動組裝預設 `OpenAIEmbedder` 與 `FaissKnowledgeBase`。若你要自訂底層行為，仍可用 `embedder` 與 `knowledge_base` 覆蓋預設組裝。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `top_k` | `integer` | 否 | `3` | 從 knowledge base 或 memory store 取回的最大筆數。 |
| `provider` | `string|null` | 否 | `null` | 預設 embedder provider；目前支援 `openai` 與 `openai_compatible`。 |
| `api_key` | `string|null` | 否 | `null` | 建立預設 embedder 時使用的 OpenAI-compatible 金鑰。 |
| `base_url` | `string|null` | 否 | `null` | 建立預設 embedder 時使用的 OpenAI-compatible base URL。 |
| `embedding_model` | `string|null` | 否 | `null` | 建立預設 embedder 時使用的 embedding model 名稱。 |
| `index_path` | `string|null` | 否 | `null` | 預設 FAISS index artifact 路徑；可為 `.faiss` 檔案或目錄。 |
| `source_path` | `string|null` | 否 | `null` | 預設知識來源目錄；首次建置或重建時會掃描這個路徑。 |
| `rebuild_if_missing` | `boolean` | 否 | `false` | 若 index artifact 不存在，是否自動建置。 |
| `rebuild_if_stale` | `boolean` | 否 | `false` | 若來源文件比 index artifact 新，是否自動重建。 |
| `chunk_size` | `integer` | 否 | `1200` | 每個知識 chunk 的目標最大字元數。 |
| `chunk_overlap` | `integer` | 否 | `150` | 相鄰 chunk 之間保留的重疊字元數。 |
| `embedder` | `Embedder|null` | 否 | `null` | 進階 override；提供時會覆蓋 `provider/api_key/base_url/embedding_model` 的預設組裝。 |
| `knowledge_base` | `KnowledgeBase|null` | 否 | `null` | 進階 override；提供時會覆蓋 `index_path/source_path/rebuild_*` 的預設組裝。 |
| `vision_query` | `VisionQueryBuilder|null` | 否 | `null` | 圖文查詢改寫器；有圖片附件時可先產生檢索查詢。 |

### 官方預設資料流

若你使用統一配置介面而不手動注入底層元件，`SemanticRetrieve` 的預設資料流如下：

1. 使用 OpenAI-compatible embeddings 將查詢與文件內容向量化。
2. 使用 FAISS 保存與查詢靜態知識索引。
3. 來源文件預設從 `source_path` 掃描。
4. 文件內容會先切成較小的 chunk，再以 chunk 為單位建立索引與回傳結果。
5. 純文字檔會直接讀取；非純文字檔可透過 MarkItDown 轉成文字。
6. 若 workflow 同時配置 persistent memory，retriever 會再把語意查詢結果與 memory 搜尋結果一起整合。

### 使用建議

- 一般使用者：優先使用 `provider/api_key/base_url/embedding_model/index_path/source_path` 這組 facade 參數。
- 若文件較長或段落很密，可以再調整 `chunk_size` 與 `chunk_overlap` 來換取較好的召回品質。
- 進階使用者：只有在要替換 embeddings backend 或知識庫實作時，才自行傳入 `embedder` / `knowledge_base`。
- 若只想查 workflow memory，可以不提供 `index_path` 與 `source_path`；此時 `SemanticRetrieve` 仍可運作，但不會查靜態知識庫。

## Retrieve 配套元件：VisionQueryBuilder

舊名對應：`FoundryVisionQuery`

前面三個模組直接參與 workflow 的 Retrieve 節點；這個配套元件則負責在檢索前先把圖文輸入整理成可檢索的查詢字串，讓圖像輸入也能順利接上同一套檢索流程。

`VisionQueryBuilder` 是搭配 `TextImagePerceive` 或 `SemanticRetrieve` 使用的查詢改寫器。它的責任是把圖片與文字整理成一段可檢索的查詢字串，供後續檢索流程使用。

`VisionQueryBuilder` 本身是 protocol；SDK 內建的 `DefaultVisionQueryBuilder` 需要明確的 OpenAI-compatible 連線設定，並在內部初始化 client。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 圖文模型名稱；端點需支援圖片輸入。 |
| `max_keywords_chars` | `integer` | 否 | `60` | 查詢改寫結果最多保留的字元數。 |