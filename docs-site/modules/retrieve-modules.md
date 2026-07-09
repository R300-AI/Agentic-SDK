# Retrieve Modules

Retrieve 模組負責把 workflow 需要的知識內容取回來。MVP 先保留一條 README 可直接理解的最小檢索路徑，再提供正式語意檢索模組。

## MVP 模組

| 模組 | 需要模型 | 讀取 | 寫入 | 定位 |
| --- | --- | --- | --- | --- |
| KeywordRetrieve | 否 | `query` 或 `perceived_input` | `retrieved_items` | README 最小檢索模組 |
| Semantic Search Retrieve | 是 | `query` | `retrieved_items` | 正式語意檢索模組 |

## KeywordRetrieve

這是 README 中最容易理解的 retrieve 入口，適合知識條目數量有限、欄位明確、查詢條件直觀的情境。

**對應論文：** [Okapi at TREC-3](https://trec.nist.gov/pubs/trec3/papers/city.ps.gz)

### 建構參數

公開敘事只要求你提供可搜尋的知識來源，不要求模型或向量索引。

### 輸入契約

可直接讀 `query`，若 workflow 未額外建立 query，也可退回使用 `perceived_input`。

### 輸出契約

至少寫入 `retrieved_items`。

## Semantic Search Retrieve

!!! info "模型規格"
    此模組的 embedding / reasoning 接入，一律使用 `OpenAI SDK form` 作為公開表達方式。

**對應論文：** [Dense Passage Retrieval for Open-Domain Question Answering](https://arxiv.org/abs/2004.04906)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client。 |
| `model` | 是 | 語意檢索用模型名稱。 |
| `knowledge_source` | 是 | 被檢索的知識集合。 |
| `top_k` | 否 | 控制回傳結果數量。 |

如果你的需求還停留在 README 層級，先用 KeywordRetrieve；若要提高召回與語意匹配，再升級為 Semantic Search Retrieve。