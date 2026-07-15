# Reflect

Reflect 模組負責檢查 Action 產出的候選答案，交出可直接交付或回到前一階段修正的判定。這一頁先整理 Reflect 家族共用的驗收輸入與輸出，再展開目前文件採用的兩種檢查模組。標準輸入包含使用者問題、最終回應、結構化結果、Action 狀態與檢查規則，標準輸出包含判定、原因、修補建議與下一節點；這一頁保留的是目前在三個 use case 中實際使用到的反思模組。

## ResponseCheckReflect

舊名對應：`ReflexionReflect`

`ResponseCheckReflect` 檢查目前回應是否回到問題本身，並提出修正方向。當流程已經有自然語言輸出，接下來要確認回答是否完整貼合問題時，就會接到這個模組。

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

`EvidenceCheckReflect` 檢查目前回應是否有足夠證據、是否涵蓋重點，以及是否符合固定格式。當流程需要把回應與檢索內容一起驗收時，這個模組會補上證據與格式層的檢查。

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