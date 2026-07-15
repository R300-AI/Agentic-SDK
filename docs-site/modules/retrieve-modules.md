# Retrieve

Retrieve 模組負責把 workflow 需要的知識內容取回來。依這套文件的流程定義，Retrieve 完成後會將結果交回 Plan，再由 Plan 決定後續路徑。現行程式碼中已實作 `KeywordRetrieve`、`StubRetrieve` 與 `SemanticRetrieve` 三個節點；另外還有 `FoundryVisionQuery` 作為圖像附件轉檢索查詢的輔助元件。

## KeywordRetrieve

`KeywordRetrieve` 是 README 第一與第三個快速開始範例使用的最小檢索模組。它會用 `query` 或 `perceived_input` 與每個條目的 `keywords` 做字串包含比對；這是工程上易懂的 lexical baseline，概念上接近傳統關鍵字檢索，可參考經典 IR 基線 [Arxiv](https://arxiv.org/abs/cmp-lg/9606016)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `items` | `list[dict] | None` | `None` | 可搜尋條目列表；每筆通常包含 `keywords: list[str]` 與 `content: str`。 |

## StubRetrieve

`StubRetrieve` 會對內建字典語料做最小關鍵字命中，主要用途是讓 planner / retrieve / reflect 的開發與測試在沒有外部知識庫時仍可跑通。它是 PoC 用的工程基線，沒有直接對應單一研究論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `corpus` | `dict[str, str] | None` | 內建 `_DEFAULT_CORPUS` | 可選的測試語料字典；key 為關鍵字，value 為回傳片段。 |

## SemanticRetrieve

`SemanticRetrieve` 會先選擇性地用圖像附件改寫查詢，再優先檢索 `KnowledgeBase`，最後檢索 `MemoryStore`，並把命中結果整合成單一 `retrieved_snippet`。它屬於 retrieval-augmented memory / dense retrieval 風格，可參考 Dense Passage Retrieval 的代表作 [Arxiv](https://arxiv.org/abs/2004.04906)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `top_k` | `int` | `3` | Knowledge Base 與 Memory Stream 各自最多取回幾筆結果。 |
| `similarity_weight` | `float` | `0.5` | 記憶排序中的語意相似度權重。 |
| `recency_weight` | `float` | `0.3` | 記憶排序中的時間新近性權重。 |
| `importance_weight` | `float` | `0.2` | 記憶排序中的 importance 權重。 |
| `embedder` | `Embedder | None` | `None` | 若注入，Memory Stream 搜尋會先產生 query embedding。 |
| `knowledge_base` | `KnowledgeBase | None` | `None` | 靜態知識來源；若存在會先查 Knowledge Base。 |
| `vision_query` | `VisionQueryBuilder | None` | `None` | 若同時有 image attachments，先將圖文改寫為較適合檢索的查詢。 |

## Retrieve 輔助元件：FoundryVisionQuery

`FoundryVisionQuery` 不是獨立的 workflow 節點，而是 `SemanticRetrieve` 可選的圖像查詢改寫器。它會把文字與圖片附件送到 vision-capable Foundry deployment，輸出一段短關鍵字查詢，適合多模態檢索前處理；方法上可視為 vision-language query rewriting，沒有直接對應單一固定論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `settings` | `Settings | None` | `get_settings()` | 預設設定來源。 |
| `client` | `Any` | `None` | 可直接注入 Azure OpenAI-compatible client。 |
| `deployment` | `str | None` | `settings.azure_foundry_deployment` | 使用的 vision-capable deployment。 |
| `endpoint` | `str | None` | `None` | 覆蓋 Azure Foundry endpoint。 |
| `api_key` | `str | None` | `None` | 覆蓋 Azure Foundry API key。 |
| `max_keywords_chars` | `int` | `60` | 限制回傳關鍵字字串的最大長度。 |