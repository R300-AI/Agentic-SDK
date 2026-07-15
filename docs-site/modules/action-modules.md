# Action

Action 模組負責把前面節點收集到的資訊轉成回應內容。這一頁使用文件標準名來定義 Action 家族的 MVP 邊界；標準輸入固定包含使用者問題、感知摘要、檢索摘要與檢索條目，標準輸出固定包含狀態、文字回應、結構化資料與錯誤訊息。

## DirectAnswerAction

舊名對應：`DirectAnswerAction`

`DirectAnswerAction` 直接根據取回內容組成最終回應，不再做額外生成。它適合 README 最小流程與條目式固定回答。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"TSiP 是什麼？"` | 使用者單輪原始文字。 |
| `perceive_summary` | `string` | `"使用者想知道 TSiP 的定義"` | 感知摘要。 |
| `retrieved_snippet` | `string` | `"TSiP 是工研院主導的國產 AI 晶片落地藍圖。"` | 檢索摘要。 |
| `retrieved_items` | `array<object>` | `[{"id":"doc-001","title":"TSiP 說明","content":"TSiP 是工研院主導的國產 AI 晶片落地藍圖。","score":1.0,"source":"keyword","metadata":{}}]` | 檢索條目；沒有命中時固定 `[]`。 |
| `response_schema` | `object` | `{"type":"text","fields":[]}` | 回應格式定義。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"TSiP 是工研院主導的國產 AI 晶片落地藍圖。"` | 對外回應文字。 |
| `final_data` | `object|null` | `null` | 純文字回應時固定 `null`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

### 對應 use case

README 最小流程、條目型 FAQ、固定知識回覆。

## GenerativeAction

舊名對應：`CompletionAction`

`GenerativeAction` 根據輸入摘要與取回內容生成最終回應。它適合需要把多筆條目、歷史紀錄或摘要整合成自然語言輸出的流程。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請幫我推薦適合久站的鞋"` | 使用者單輪原始文字。 |
| `perceive_summary` | `string` | `"使用者想找適合久站情境的鞋款推薦"` | 感知摘要。 |
| `retrieved_snippet` | `string` | `"支撐型慢跑鞋適合久站與足弓支撐需求。"` | 檢索摘要。 |
| `retrieved_items` | `array<object>` | `[{"id":"shoe-001","title":"支撐型慢跑鞋","content":"適合久站與足弓支撐需求。","score":0.91,"source":"semantic","metadata":{"category":"shoe"}}]` | 檢索條目；沒有命中時固定 `[]`。 |
| `response_schema` | `object` | `{"type":"text","fields":[]}` | 回應格式定義。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋，因為較適合久站與足弓支撐需求。"` | 對外回應文字。 |
| `final_data` | `object|null` | `null` | 純文字回應時固定 `null`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

### 對應 use case

README 模型型輸出流程、LaNew 推薦說明、BCI 訓練建議、ICOPE 追蹤建議。

## StructuredAction

舊名對應：`StructuredOutputAction`

`StructuredAction` 依固定欄位規格輸出結構化結果。它適合後續還要把回應交給別的系統處理，或需要將推薦理由、建議與證據拆成固定欄位的流程。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請幫我推薦適合久站的鞋"` | 使用者單輪原始文字。 |
| `perceive_summary` | `string` | `"使用者想找適合久站情境的鞋款推薦"` | 感知摘要。 |
| `retrieved_snippet` | `string` | `"支撐型慢跑鞋適合久站與足弓支撐需求。"` | 檢索摘要。 |
| `retrieved_items` | `array<object>` | `[{"id":"shoe-001","title":"支撐型慢跑鞋","content":"適合久站與足弓支撐需求。","score":0.91,"source":"semantic","metadata":{"category":"shoe"}}]` | 檢索條目；沒有命中時固定 `[]`。 |
| `response_schema` | `object` | `{"type":"json","fields":[{"name":"recommendation","value_type":"string"},{"name":"reason","value_type":"string"}]}` | 結構化輸出格式定義。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋。"` | 對外回應文字；若只需要結構化資料也仍保留摘要文字。 |
| `final_data` | `object|null` | `{"recommendation":"支撐型慢跑鞋","reason":"較適合久站與足弓支撐需求"}` | 結構化輸出資料。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

### 對應 use case

LaNew 固定欄位推薦、BCI 訓練建議欄位化、ICOPE 追蹤建議欄位化。