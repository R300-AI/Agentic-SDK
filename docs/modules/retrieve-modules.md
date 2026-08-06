# 參考資料

查找資料模組負責把工作流程需要的內容交給下一步。這一頁依序說明關鍵字查找、原文交接、語意查找與圖片查詢整理。查找步驟寫入的資料會放在 [模組家族](index.md) 說明的共用資料中。

以設定資料建立工作流程時，`ModuleSpec.params` 會使用本頁列出的建構參數。

## KeywordRetrieve

參考論文：無特定 arXiv 對應；此模組是關鍵字檢索 baseline。

`KeywordRetrieve` 依關鍵字規則取回內容，適合 README 的最小流程與條目式知識查找。它代表的是最直接的檢索路徑：有明確查詢字串，就回傳最對應的條目內容。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `items` | `array<object>` | 否 | `[]` | 關鍵字條目清單；每筆通常包含 `keywords` 與 `content`。 |
| `fallback` | `string` | 否 | `"No matching entries."` | 沒有命中任何條目時寫入取回內容的文字。 |

## PassThroughRetrieve

### 原文交接

`PassThroughRetrieve` 會把已整理的使用者輸入交給回覆步驟。它依序使用 `perceived_input`、`query` 與最新使用者訊息，將文字放入 `retrieved_snippet` 和 `latest_retrieved_content`。這個模組不需要建構參數，適合流程要保留查找步驟的位置、但本輪直接使用已讀取的訊息時。

## SemanticRetrieve

參考論文：[Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)

`SemanticRetrieve` 依語意相似度從知識來源取回內容。當流程需要從較長知識片段裡找出真正相關的內容時，這個模組會把檢索重心放在語意接近度。

`SemanticRetrieve` 使用 `sources` 指定來源檔案或資料夾，並以 `saved_path` 指定保存位置。SDK 會先把來源複製到 `saved_path/source-files/`，再從這份副本建立索引；向量索引存放在 `saved_path/vectorstore/`。你的程式可在之後保存或搬移整個 `saved_path`，保留來源副本與索引資料。需要自行提供向量模型或知識庫時，可傳入 `embedder` 與 `knowledge_base`。

`top_k`、`saved_path`、`source-files` 與 `vectorstore` 的預設值由 `agentic_sdk.defaults` 定義。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `top_k` | `integer` | 否 | `3` | 從 knowledge base 或 memory store 取回的最大筆數。 |
| `provider` | `string|null` | 否 | `null` | 預設 embedder provider；目前支援 `openai` 與 `openai_compatible`。 |
| `api_key` | `string|null` | 否 | `null` | 建立預設 embedder 時使用的 OpenAI-compatible 金鑰。 |
| `base_url` | `string|null` | 否 | `null` | 建立預設 embedder 時使用的 OpenAI-compatible base URL。 |
| `embedding_model` | `string|null` | 否 | `null` | 建立預設 embedder 時使用的 embedding model 名稱。 |
| `sources` | `list[string]|null` | 否 | `null` | 要匯入的來源檔案或目錄清單；目錄會遞迴複製到 `saved_path/source-files/`。 |
| `saved_path` | `string` | 否 | `./tmp` | 保存目錄；來源副本放在 `saved_path/source-files/`，FAISS 索引檔放在 `saved_path/vectorstore/`。 |
| `rebuild_if_missing` | `boolean` | 否 | `true` | 索引檔尚未建立時，自動建立索引。 |
| `rebuild_if_stale` | `boolean` | 否 | `true` | 來源文件更新後，自動重建索引。 |
| `chunk_size` | `integer` | 否 | `1200` | 每個知識 chunk 的目標最大字元數。 |
| `chunk_overlap` | `integer` | 否 | `150` | 相鄰 chunk 之間保留的重疊字元數。 |
| `embedder` | `Embedder|null` | 否 | `null` | 自行提供的文字向量產生器。 |
| `knowledge_base` | `KnowledgeBase|null` | 否 | `null` | 自行提供的知識查找來源。 |
| `vision_query` | `VisionQueryBuilder|null` | 否 | `null` | 圖片與文字的查詢整理器；有圖片附件時先產生查找用文字。 |

### 建立索引的步驟

使用 `sources`、嵌入模型和保存位置建立 `SemanticRetrieve` 時，SDK 會依下列步驟處理資料：

1. 使用 OpenAI-compatible embeddings 將查詢與文件內容向量化。
2. 使用 FAISS 保存與查詢靜態知識索引。
3. 來源文件先從 `sources` 複製到 `saved_path/source-files/`，再從這份 copy 掃描。
4. 文件內容會先切成較小的 chunk，再以 chunk 為單位建立索引與回傳結果。
5. 可讀文字會直接使用；文件需要先轉成文字，才能建立索引。
6. 若 workflow 同時配置 persistent memory，retriever 會再把語意查詢結果與 memory 搜尋結果一起整合。

### 使用方式

- 一般情況可設定 `provider`、`api_key`、`base_url`、`embedding_model`、`sources` 與 `saved_path`。
- 文件內容較長或段落較密時，可調整 `chunk_size` 與 `chunk_overlap`。
- 需要自行管理向量模型或知識庫時，可傳入 `embedder` 或 `knowledge_base`。
- 工作流程也可搭配持久記憶查找；此時語意查找會一併使用記憶中的相關內容。

例如，來源檔案可用相對路徑指定：

```python
SemanticRetrieve(
	api_key="<RETRIEVE_API_KEY>",
	base_url="<RETRIEVE_API_BASE_URL>",
	embedding_model="<RETRIEVE_EMBEDDING_MODEL>",
	sources=["./manual.pdf"],
)
```

### 文件文字讀取

SDK 會先以 UTF-8 讀取文字來源。其他文件會交給 MarkItDown 轉成文字；PDF 會先使用 `pdfminer.six`，接著使用 `pypdf`，再使用 MarkItDown。文件轉換完成後，SDK 將讀到的文字切分並建立索引。來源本身應提供可讀的文字內容，讓查找結果能回到原始資料。

## 圖片查詢整理：VisionQueryBuilder

參考論文：[Flamingo: a Visual Language Model for Few-Shot Learning](https://arxiv.org/abs/2204.14198)

前面三個模組直接參與 workflow 的 Retrieve 節點；這個配套元件則負責在檢索前先把圖文輸入整理成可檢索的查詢字串，讓圖像輸入也能順利接上同一套檢索流程。

`VisionQueryBuilder` 可搭配 `TextImagePerceive` 或 `SemanticRetrieve` 使用。它將圖片與文字整理成一段查找用文字，交給後續步驟使用。

`VisionQueryBuilder` 是一個介面規格；SDK 內建的 `DefaultVisionQueryBuilder` 使用 OpenAI 相容服務的連線設定建立模型用戶端。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 圖文模型名稱；端點需支援圖片輸入。 |
| `max_keywords_chars` | `integer` | 否 | `60` | 查詢改寫結果最多保留的字元數。 |