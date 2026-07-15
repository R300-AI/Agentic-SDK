# Reflect

Reflect 模組負責檢查 Action 產出的候選答案，判斷答案是否可直接交付，或是否應退回前面的節點修正。這一頁使用文件標準名來定義 Reflect 家族的 MVP 邊界；標準輸入固定包含使用者問題、最終回應、結構化結果、Action 狀態與檢查規則，標準輸出固定包含判定、原因、修補建議與下一節點。

## ErrorCheckReflect

舊名對應：`RuleBasedReflect`

`ErrorCheckReflect` 依固定規則檢查 Action 是否失敗，並決定結束或退回。它是最小驗收基線，重點不是回應品質，而是先判斷這輪輸出有沒有明顯錯誤。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"TSiP 是什麼？"` | 使用者單輪原始文字。 |
| `final_message` | `string` | `"TSiP 是工研院主導的國產 AI 晶片落地藍圖。"` | Action 交出的對外文字。 |
| `final_data` | `object|null` | `null` | 結構化結果；純文字回應時固定 `null`。 |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |
| `reflect_rules` | `array<string>` | `["check_action_error"]` | 驗收規則清單。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `reflect_verdict` | `string` | `"pass"` | 只允許 `pass` 或 `fail`。 |
| `reflect_reason` | `string` | `"action_result ok"` | 驗收判定原因。 |
| `reflect_patch` | `string` | `""` | 通過時固定空字串；失敗時提供修補方向。 |
| `next_node` | `string` | `"end"` | 只允許 `end` 或 `plan`。 |

### 對應 use case

所有需要最小失敗檢查的流程，包含 README 進階流程、LaNew、BCI、ICOPE。

## ResponseCheckReflect

舊名對應：`ReflexionReflect`

`ResponseCheckReflect` 檢查目前回應是否回到問題本身，並提出修正方向。它適合已經有自然語言輸出，但還需要檢查是否漏答或答非所問的流程。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請幫我推薦適合久站的鞋"` | 使用者單輪原始文字。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋。"` | Action 交出的對外文字。 |
| `final_data` | `object|null` | `null` | 結構化結果；純文字回應時固定 `null`。 |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |
| `reflect_rules` | `array<string>` | `["answer_question","avoid_off_topic"]` | 驗收規則清單。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `reflect_verdict` | `string` | `"pass"` | 只允許 `pass` 或 `fail`。 |
| `reflect_reason` | `string` | `"回答有回到鞋款推薦問題"` | 驗收判定原因。 |
| `reflect_patch` | `string` | `"補充推薦理由與使用情境"` | 通過時固定空字串；失敗時提供修補方向。 |
| `next_node` | `string` | `"end"` | 只允許 `end` 或 `plan`。 |

### 對應 use case

LaNew 推薦說明、BCI 訓練建議、ICOPE 追蹤建議。

## EvidenceCheckReflect

舊名對應：`EvidenceCheckReflect`

`EvidenceCheckReflect` 檢查目前回應是否有足夠證據、是否漏答，以及是否符合固定格式。它適合需要把回應與檢索內容綁在一起驗收的流程。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請幫我推薦適合久站的鞋"` | 使用者單輪原始文字。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋。"` | Action 交出的對外文字。 |
| `final_data` | `object|null` | `{"recommendation":"支撐型慢跑鞋","reason":"較適合久站與足弓支撐需求"}` | 結構化結果；純文字回應時可為 `null`。 |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |
| `reflect_rules` | `array<string>` | `["answer_question","use_evidence","match_schema"]` | 驗收規則清單。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `reflect_verdict` | `string` | `"pass"` | 只允許 `pass` 或 `fail`。 |
| `reflect_reason` | `string` | `"回答有使用檢索內容作為依據，且欄位格式正確"` | 驗收判定原因。 |
| `reflect_patch` | `string` | `"補充推薦理由與對應證據欄位"` | 通過時固定空字串；失敗時提供修補方向。 |
| `next_node` | `string` | `"end"` | 只允許 `end` 或 `plan`。 |

### 對應 use case

LaNew 固定欄位推薦、BCI 回應驗收、ICOPE 追蹤建議驗收。