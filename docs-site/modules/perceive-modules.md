# Perceive

Perceive 模組負責把原始輸入整理成 workflow 後續節點可直接消費的感知結果。這一頁使用文件標準名來定義 Perceive 家族的 MVP 邊界；輸入來源只包含純文字、結構化欄位與圖片檔，圖片檔只接受 `image/png`、`image/jpeg`、`image/webp`。

## PassThroughPerceive

舊名對應：`InputPerceive`

`PassThroughPerceive` 將原始文字輸入直接轉成查詢內容，不做額外判讀。它適合 README 的最小流程，也適合作為所有文字型流程的最小入口。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請介紹 TSiP"` | 使用者單輪原始文字。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `query` | `string` | `"請介紹 TSiP"` | 直接給後續檢索節點使用的查詢字串。 |

### 對應 use case

README 最小流程、README 自訂 Action 流程。

## PatternPerceive

舊名對應：`RuleBasedPerceive`

`PatternPerceive` 依固定模式、關鍵詞或選項命中來整理輸入重點。它的責任是把輸入轉成可以讓後續 `Plan` 判斷分支的路由標籤。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請幫我推薦適合久站的鞋"` | 使用者單輪原始文字。 |
| `input_options` | `array<object>` | `[{"label":"鞋款推薦","value":"shoe_recommendation","hint":"recommendation"}]` | UI 提供的選項清單；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[]` | 圖片清單；沒有圖片時固定 `[]`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `perceive_type` | `string` | `"pattern"` | 標記本次使用模式比對路徑。 |
| `perceive_query` | `string` | `"推薦適合久站的鞋"` | 後續檢索或規劃可直接使用的查詢字串。 |
| `perceive_label` | `string` | `"shoe_recommendation"` | 供 `Plan` 判斷分支的標籤。 |
| `perceive_summary` | `string` | `"使用者想找適合久站情境的鞋款推薦"` | 對本輪需求的一句摘要。 |
| `perceive_fields` | `object` | `{}` | 摘出的結構化欄位。 |
| `perceive_images` | `array<object>` | `[]` | 本輪保留的圖片資訊。 |

### 對應 use case

LaNew 的選項導流、BCI 的快速問題分流、ICOPE 的評估入口分流。

## SemanticPerceive

舊名對應：`LLMBasedPerceive`

`SemanticPerceive` 依語意判讀來整理輸入內容與重點。它和 `PatternPerceive` 的輸出格式相同，但適合需求表達較長、較依賴語意理解的流程。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"我最近久站後足弓很酸，想找比較有支撐的鞋"` | 使用者單輪原始文字。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[]` | 圖片清單；沒有圖片時固定 `[]`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `perceive_type` | `string` | `"semantic"` | 標記本次使用語意理解路徑。 |
| `perceive_query` | `string` | `"足弓支撐 久站 鞋款 推薦"` | 後續檢索或規劃可直接使用的查詢字串。 |
| `perceive_label` | `string` | `"shoe_recommendation"` | 供 `Plan` 判斷分支的標籤。 |
| `perceive_summary` | `string` | `"使用者想找適合久站且足弓支撐較好的鞋款"` | 對本輪需求的一句摘要。 |
| `perceive_fields` | `object` | `{}` | 摘出的結構化欄位。 |
| `perceive_images` | `array<object>` | `[]` | 本輪保留的圖片資訊。 |

### 對應 use case

LaNew 的自然語言鞋款需求、BCI 的訓練情境描述、ICOPE 的追蹤建議需求。

## StructuredPerceive

舊名對應：`StructuredPerceive`

`StructuredPerceive` 將結構化欄位整理成後續可用的查詢與摘要。它適合以欄位資料為主的流程，不要求使用者先把資訊寫成完整自然語言。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `""` | 沒有自由輸入時固定空字串。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{"age":72,"left_foot_length_mm":250,"pain":true}` | 欄位資料；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[]` | 圖片清單；沒有圖片時固定 `[]`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `perceive_type` | `string` | `"structured"` | 標記本次使用欄位整理路徑。 |
| `perceive_query` | `string` | `"72歲 左足長250mm 足弓疼痛 鞋款建議"` | 將欄位轉成後續可搜尋的查詢字串。 |
| `perceive_label` | `string` | `"structured_assessment"` | 供 `Plan` 判斷分支的標籤。 |
| `perceive_summary` | `string` | `"使用者提供了年齡、足長與疼痛欄位，需整理成建議"` | 對欄位內容的一句摘要。 |
| `perceive_fields` | `object` | `{"age":72,"left_foot_length_mm":250,"pain":true}` | 摘出的結構化欄位。 |
| `perceive_images` | `array<object>` | `[]` | 本輪保留的圖片資訊。 |

### 對應 use case

LaNew 足測欄位、ICOPE 六大能力欄位輸入。

## ImageAwarePerceive

舊名對應：`MultimodalPerceive`

`ImageAwarePerceive` 將文字與圖片內容整理成後續可用的查詢與摘要。這個標準名只處理圖片檔，不延伸到任意附件格式。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請根據這張足測圖推薦鞋款"` | 使用者單輪原始文字。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[{"mime_type":"image/png","name":"foot_scan.png","content_ref":"blob://foot_scan.png"}]` | 圖片清單；只允許 `image/png`、`image/jpeg`、`image/webp`。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `perceive_type` | `string` | `"image_aware"` | 標記本次使用圖像感知路徑。 |
| `perceive_query` | `string` | `"足測圖 足弓支撐 鞋款 推薦"` | 將圖文內容整理成後續可搜尋的查詢字串。 |
| `perceive_label` | `string` | `"image_based_recommendation"` | 供 `Plan` 判斷分支的標籤。 |
| `perceive_summary` | `string` | `"使用者附上足測圖，希望得到鞋款推薦"` | 對圖文輸入的一句摘要。 |
| `perceive_fields` | `object` | `{}` | 摘出的結構化欄位。 |
| `perceive_images` | `array<object>` | `[{"mime_type":"image/png","name":"foot_scan.png","content_ref":"blob://foot_scan.png"}]` | 本輪保留的圖片資訊。 |

### 對應 use case

LaNew 足測圖、BCI 視覺輔助輸入。