# Perceive

Perceive 模組負責把原始輸入整理成 workflow 後續節點可直接消費的感知結果。這一頁先定義 Perceive 家族處理哪些輸入型態，再依序展開目前文件採用的四個標準模組。Perceive 的重點在接收什麼輸入，因此這一頁只列各模組的標準輸入參數；整理後寫入 `Entities` 的欄位，會回到 [Module Family](index.md) 的中央定義理解。輸入來源包含純文字、結構化欄位與圖片檔，圖片格式支援 `image/png`、`image/jpeg`、`image/webp`。

## PassThroughPerceive

舊名對應：`InputPerceive`

`PassThroughPerceive` 將原始文字輸入直接整理成查詢內容，交給後續節點接手。它適合 README 的最小流程，也適合作為文字型流程的直接入口。這個模組代表的是最短路徑：收到文字後，先把可查詢的內容穩定交出去。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請介紹 TSiP"` | 使用者單輪原始文字。 |

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
