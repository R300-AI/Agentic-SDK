# Retrieve

Retrieve 模組負責把 workflow 需要的內容取回來。這一頁先整理 Retrieve 家族共用的輸入輸出骨架，再依序展開目前文件採用的檢索模組與輔助元件。Retrieve 的標準輸入固定是查詢字串與篩選條件，標準輸出固定是命中條目、摘要片段、命中數與檢索來源；這一頁保留的是目前在 README 或三個 use case 中實際使用到的檢索模組。

## KeywordRetrieve

舊名對應：`KeywordRetrieve`

`KeywordRetrieve` 依關鍵字規則取回內容，適合 README 的最小流程與條目式知識查找。它代表的是最直接的檢索路徑：有明確查詢字串，就回傳最對應的條目內容。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieve_query` | `string` | `"TSiP 定義"` | 檢索查詢字串。 |
| `retrieve_filters` | `object` | `{}` | 篩選條件；沒有條件時固定 `{}`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieved_items` | `array<object>` | `[{"id":"doc-001","title":"TSiP 說明","content":"TSiP 是工研院主導的國產 AI 晶片落地藍圖。","score":1.0,"source":"keyword","metadata":{}}]` | 命中的條目清單；沒有命中時固定 `[]`。 |
| `retrieved_snippet` | `string` | `"TSiP 是工研院主導的國產 AI 晶片落地藍圖。"` | 給後續節點直接使用的文字摘要。 |
| `retrieved_hit_count` | `integer` | `1` | 命中數。 |
| `retrieved_source` | `string` | `"keyword"` | 檢索來源標記。 |

### 對應 use case

README 最小流程、README 自訂 Action 流程、LaNew 條目型鞋款查找。

## SemanticRetrieve

舊名對應：`SemanticRetrieve`

`SemanticRetrieve` 依語意相似度從知識來源取回內容。當流程需要從較長知識片段裡找出真正相關的內容時，這個模組會把檢索重心放在語意接近度。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieve_query` | `string` | `"足弓支撐 久站 鞋款 推薦"` | 檢索查詢字串。 |
| `retrieve_filters` | `object` | `{"category":["shoe"],"tags":[]}` | 篩選條件；沒有條件時固定 `{}`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieved_items` | `array<object>` | `[{"id":"shoe-001","title":"支撐型慢跑鞋","content":"適合久站與足弓支撐需求。","score":0.91,"source":"semantic","metadata":{"category":"shoe"}}]` | 命中的條目清單；沒有命中時固定 `[]`。 |
| `retrieved_snippet` | `string` | `"支撐型慢跑鞋適合久站與足弓支撐需求。"` | 給後續節點直接使用的文字摘要。 |
| `retrieved_hit_count` | `integer` | `1` | 命中數。 |
| `retrieved_source` | `string` | `"semantic"` | 檢索來源標記。 |

### 對應 use case

LaNew 語意型鞋款推薦、BCI 歷史訓練片段比對、ICOPE 追蹤紀錄查找。

## HybridRetrieve

舊名對應：`HybridRetrieve`

`HybridRetrieve` 混合關鍵字、語意與欄位條件取回內容。當流程同時需要欄位比對與語意補證據時，這個模組會把多種檢索線索合併成同一輪結果。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieve_query` | `string` | `"足弓支撐 久站 鞋款 推薦"` | 檢索查詢字串。 |
| `retrieve_filters` | `object` | `{"category":["shoe"],"date_from":"","date_to":"","tags":[]}` | 篩選條件；沒有條件時固定 `{}`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieved_items` | `array<object>` | `[{"id":"shoe-001","title":"支撐型慢跑鞋","content":"適合久站與足弓支撐需求。","score":0.95,"source":"hybrid","metadata":{"category":"shoe"}}]` | 命中的條目清單；沒有命中時固定 `[]`。 |
| `retrieved_snippet` | `string` | `"支撐型慢跑鞋適合久站與足弓支撐需求。"` | 給後續節點直接使用的文字摘要。 |
| `retrieved_hit_count` | `integer` | `1` | 命中數。 |
| `retrieved_source` | `string` | `"hybrid"` | 檢索來源標記。 |

### 對應 use case

LaNew 欄位加語意鞋款推薦、BCI 歷史片段與標註混合查找、ICOPE 能力面向加紀錄比對。

## Retrieve 輔助元件：VisionQueryBuilder

舊名對應：`FoundryVisionQuery`

前面三個模組是直接參與 workflow 的 Retrieve 節點；最後這個輔助元件則負責在檢索前先把圖文輸入整理好。

`VisionQueryBuilder` 是搭配 `TextImagePerceive` 或 `SemanticRetrieve` 使用的查詢改寫器。它的責任是把圖片與文字整理成一段可檢索的查詢字串，供後續檢索流程使用。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請根據這張足測圖推薦鞋款"` | 使用者原始文字。 |
| `input_images` | `array<object>` | `[{"mime_type":"image/png","name":"foot_scan.png","content_ref":"blob://foot_scan.png"}]` | 圖片清單；只允許 `image/png`、`image/jpeg`、`image/webp`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `retrieve_query` | `string` | `"足測圖 足弓支撐 鞋款 推薦"` | 給後續檢索節點使用的查詢字串。 |