# Action

Action 模組負責把前面節點收集到的資訊轉成回應內容。這一頁先整理 Action 家族的交付方式，再依序展開三種不同的回應產生模組。Action 的重點在交付什麼輸出，因此這一頁只列各模組的標準輸出參數；前段帶入的內容主要來自 `Entities`，可回到 [Module Family](index.md) 的中央定義理解。

## DirectAnswerAction

舊名對應：`DirectAnswerAction`

`DirectAnswerAction` 直接根據取回內容組成最終回應，以條目內容為主完成回答。它適合 README 最小流程與條目式固定回答，也代表 Action 家族裡最直接的交付方式。

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"TSiP 是工研院主導的國產 AI 晶片落地藍圖。"` | 對外回應文字。 |
| `final_data` | `object|null` | `null` | 純文字回應時固定 `null`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

## GenerativeAction

舊名對應：`CompletionAction`

`GenerativeAction` 根據輸入摘要與取回內容生成最終回應。當流程要把多筆條目、歷史紀錄或摘要整合成一段自然語言時，就會接到這個模組。

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋，因為較適合久站與足弓支撐需求。"` | 對外回應文字。 |
| `final_data` | `object|null` | `null` | 純文字回應時固定 `null`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

## StructuredAction

舊名對應：`StructuredOutputAction`

`StructuredAction` 依固定欄位規格輸出結構化結果。當回應還要交給別的系統處理，或需要把推薦理由、建議與證據拆成固定欄位時，這個模組會把輸出整理成穩定的資料結構。

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋。"` | 對外回應文字；若只需要結構化資料也仍保留摘要文字。 |
| `final_data` | `object|null` | `{"recommendation":"支撐型慢跑鞋","reason":"較適合久站與足弓支撐需求"}` | 結構化輸出資料。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |