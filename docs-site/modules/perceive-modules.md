# Perceive

Perceive 模組負責把原始輸入整理成 workflow 後續節點可直接消費的感知結果。這一頁先定義 Perceive 家族處理哪些輸入型態，再依序展開目前文件採用的四個標準模組。輸入來源包含純文字、結構化欄位與圖片檔，圖片格式支援 `image/png`、`image/jpeg`、`image/webp`；目前保留的是實際在 README 或三個 use case 中有使用到的感知模組。

## PassThroughPerceive

舊名對應：`InputPerceive`

`PassThroughPerceive` 將原始文字輸入直接整理成查詢內容，交給後續節點接手。它適合 README 的最小流程，也適合作為文字型流程的直接入口。這個模組代表的是最短路徑：收到文字後，先把可查詢的內容穩定交出去。

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

## TextPerceive

舊名對應：`LLMBasedPerceive`

`TextPerceive` 依文字內容做語意判讀，將輸入整理成後續可用的查詢、標籤與摘要。當流程需要的不只是原句，而是對需求做一次語意整理時，就會接到這個模組。

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

`StructuredPerceive` 將結構化欄位整理成後續可用的查詢與摘要。當流程的主要輸入來自欄位資料時，這個模組會把欄位內容直接組成查詢與需求摘要。

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

## TextImagePerceive

舊名對應：`MultimodalPerceive`

`TextImagePerceive` 將文字與圖片內容一起整理成後續可用的查詢與摘要。當流程同時需要讀取文字與圖片時，這個模組會把兩類資訊整合成後續可用的感知結果，支援 `image/png`、`image/jpeg`、`image/webp` 三種格式。

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