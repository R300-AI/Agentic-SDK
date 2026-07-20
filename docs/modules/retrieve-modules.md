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

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `top_k` | `integer` | 否 | `3` | 從 knowledge base 或 memory store 取回的最大筆數。 |
| `similarity_weight` | `number` | 否 | `0.5` | 記憶搜尋的語意相似度權重。 |
| `recency_weight` | `number` | 否 | `0.3` | 記憶搜尋的新近性權重。 |
| `importance_weight` | `number` | 否 | `0.2` | 記憶搜尋的重要性權重。 |
| `embedder` | `Embedder|null` | 否 | `null` | 可插拔向量嵌入器；未提供時使用內建文字相似度路徑。 |
| `knowledge_base` | `KnowledgeBase|null` | 否 | `null` | 靜態知識庫來源；未提供時只使用 workflow memory。 |
| `vision_query` | `VisionQueryBuilder|null` | 否 | `null` | 圖文查詢改寫器；有圖片附件時可先產生檢索查詢。 |

## HybridRetrieve

舊名對應：`HybridRetrieve`

`HybridRetrieve` 混合關鍵字、語意與欄位條件取回內容。當流程同時需要欄位比對與語意補證據時，這個模組會把多種檢索線索合併成同一輪結果。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `items` | `array<object>` | 否 | `[]` | 關鍵字條目清單；命中時會與語意結果合併。 |
| `fallback` | `string` | 否 | `"沒有命中任何條目。"` | 關鍵字路徑沒有命中時的 fallback 文字。 |
| `top_k` | `integer` | 否 | `3` | 語意路徑取回的最大筆數。 |
| `similarity_weight` | `number` | 否 | `0.5` | 記憶搜尋的語意相似度權重。 |
| `recency_weight` | `number` | 否 | `0.3` | 記憶搜尋的新近性權重。 |
| `importance_weight` | `number` | 否 | `0.2` | 記憶搜尋的重要性權重。 |
| `embedder` | `Embedder|null` | 否 | `null` | 可插拔向量嵌入器。 |
| `knowledge_base` | `KnowledgeBase|null` | 否 | `null` | 靜態知識庫來源。 |
| `vision_query` | `VisionQueryBuilder|null` | 否 | `null` | 圖文查詢改寫器。 |

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