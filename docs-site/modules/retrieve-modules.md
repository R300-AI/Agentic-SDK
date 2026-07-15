# Retrieve Modules

Retrieve 模組負責把 workflow 需要的知識內容取回來。現行程式碼中已實作 `KeywordRetrieve`、`StubRetrieve` 與 `SemanticRetrieve` 三個節點；另外還有 `FoundryVisionQuery` 作為圖像附件轉檢索查詢的輔助元件。

## 已實作模組

| 模組 | 需要模型 | 下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `KeywordRetrieve` | 否 | `action` | README 最小檢索，直接比對關鍵字條目 |
| `StubRetrieve` | 否 | `plan` | 內建測試語料的 PoC 檢索基線 |
| `SemanticRetrieve` | 視設定而定 | `plan` | 從 Knowledge Base 與 Memory Stream 做語意/記憶檢索 |

## KeywordRetrieve

`KeywordRetrieve` 是 README 第一與第三個快速開始範例使用的最小檢索模組。它會用 `query` 或 `perceived_input` 與每個條目的 `keywords` 做字串包含比對；這是工程上易懂的 lexical baseline，概念上接近傳統關鍵字檢索，可參考經典 IR 基線 [Arxiv](https://arxiv.org/abs/cmp-lg/9606016)。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `items` | `list[dict] | None` | `None` | 可搜尋條目列表；每筆通常包含 `keywords: list[str]` 與 `content: str`。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `query` | `str | None` | `state.lookup("perceived_input")`，再退回 `state.user_message` | 優先使用上游寫入的查詢字串。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"action"` | 命中後直接交給 Action 節點。 |
| `NodeOutput.payload.query` | `str` | 實際使用的小寫查詢字串。 |
| `NodeOutput.payload.retrieved_items` | `list[dict]` | 所有命中的原始條目。 |
| `NodeOutput.payload.retrieved_snippet` | `str` | 以換行串接的命中 `content`；無命中時為 `"沒有命中任何條目。"`。 |
| `NodeOutput.payload.latest_retrieved_content` | `str` | 與 `retrieved_snippet` 相同，供後續 Action 直接讀取。 |
| `NodeOutput.context_updates[0].type` | `"retrieved"` | 追加一筆 `RETRIEVED` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `hit_count` 與 `source="keyword_retrieve"`。 |

## StubRetrieve

`StubRetrieve` 會對內建字典語料做最小關鍵字命中，主要用途是讓 planner / retrieve / reflect 的開發與測試在沒有外部知識庫時仍可跑通。它是 PoC 用的工程基線，沒有直接對應單一研究論文。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `corpus` | `dict[str, str] | None` | 內建 `_DEFAULT_CORPUS` | 可選的測試語料字典；key 為關鍵字，value 為回傳片段。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | 會轉成小寫，直接與內建 `corpus` 的 key 做包含比對。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"plan"` | 取回內容後交回 planner 重新決策。 |
| `NodeOutput.payload.retrieved_snippet` | `str` | 命中片段；若無命中則為固定 fallback 訊息。 |
| `NodeOutput.context_updates[0].type` | `"retrieved"` | 追加一筆 `RETRIEVED` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `hit_count` 與 `source="stub"`。 |

## SemanticRetrieve

`SemanticRetrieve` 會先選擇性地用圖像附件改寫查詢，再優先檢索 `KnowledgeBase`，最後檢索 `MemoryStore`，並把命中結果整合成單一 `retrieved_snippet`。它屬於 retrieval-augmented memory / dense retrieval 風格，可參考 Dense Passage Retrieval 的代表作 [Arxiv](https://arxiv.org/abs/2004.04906)。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `top_k` | `int` | `3` | Knowledge Base 與 Memory Stream 各自最多取回幾筆結果。 |
| `similarity_weight` | `float` | `0.5` | 記憶排序中的語意相似度權重。 |
| `recency_weight` | `float` | `0.3` | 記憶排序中的時間新近性權重。 |
| `importance_weight` | `float` | `0.2` | 記憶排序中的 importance 權重。 |
| `embedder` | `Embedder | None` | `None` | 若注入，Memory Stream 搜尋會先產生 query embedding。 |
| `knowledge_base` | `KnowledgeBase | None` | `None` | 靜態知識來源；若存在會先查 Knowledge Base。 |
| `vision_query` | `VisionQueryBuilder | None` | `None` | 若同時有 image attachments，先將圖文改寫為較適合檢索的查詢。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | 基礎查詢文字；若有圖像改寫，這個值會被改寫結果覆蓋。 |
| `attachments` | `list[Attachment]` | `[]` | 若同時配置 `vision_query`，圖像附件可先被轉成更適合檢索的文字查詢。 |
| `memory_store` | `MemoryStore | None` | `None` | 若存在，會再對 workflow 記憶做排序搜尋。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"plan"` | 取回內容後交回 planner 重新決策。 |
| `NodeOutput.payload.retrieved_snippet` | `str` | 綜合 Knowledge Base 與 Memory Stream 的檢索結果；無命中時回傳 fallback 訊息。 |
| `NodeOutput.context_updates[0].type` | `"retrieved"` | 追加一筆 `RETRIEVED` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 可能包含 `source`、`hit_count`、`kb_name`、`kb_scores`、`scores`、`vision_augmented` 等欄位。 |

## Retrieve 輔助元件：FoundryVisionQuery

`FoundryVisionQuery` 不是獨立的 workflow 節點，而是 `SemanticRetrieve` 可選的圖像查詢改寫器。它會把文字與圖片附件送到 vision-capable Foundry deployment，輸出一段短關鍵字查詢，適合多模態檢索前處理；方法上可視為 vision-language query rewriting，沒有直接對應單一固定論文。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `settings` | `Settings | None` | `get_settings()` | 預設設定來源。 |
| `client` | `Any` | `None` | 可直接注入 Azure OpenAI-compatible client。 |
| `deployment` | `str | None` | `settings.azure_foundry_deployment` | 使用的 vision-capable deployment。 |
| `endpoint` | `str | None` | `None` | 覆蓋 Azure Foundry endpoint。 |
| `api_key` | `str | None` | `None` | 覆蓋 Azure Foundry API key。 |
| `max_keywords_chars` | `int` | `60` | 限制回傳關鍵字字串的最大長度。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `text` | `str` | `"（無文字）"` | 使用者原始文字；若空字串會退回預設文案。 |
| `attachments` | `list[Attachment]` | `[]` | 只有 `kind="image"` 的附件會被送入 vision model。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `return value` | `str` | 成功時為改寫後的檢索關鍵字字串；失敗或空輸出時退回原始 `text`。 |