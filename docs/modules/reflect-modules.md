# Reflect

Reflect 模組負責檢查 Action 產出的候選答案，交出可直接交付或回到前一階段修正的判定。這一頁先整理 Reflect 家族共用的驗收責任，再展開目前文件採用的兩種 Reflect 模組。每個模組會先列出建立物件時使用的初始化參數；驗收過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解。

## ResponseCheckReflect

舊名對應：`ReflexionReflect`

`ResponseCheckReflect` 檢查目前回應是否回到問題本身，並提出修正方向。當流程已經有自然語言輸出，接下來要確認回答是否完整貼合問題時，就會接到這個模組。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。若不需要模型檢查，可改用規則式的 `EvidenceCheckReflect`。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `on_failure` | `string` | 否 | `"retry_plan"` | 檢查失敗時的下一步；可用值為 `"retry_plan"` 或 `"end"`。 |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱。 |

## EvidenceCheckReflect

舊名對應：`EvidenceCheckReflect`

`EvidenceCheckReflect` 檢查目前回應是否有足夠證據、是否涵蓋重點，以及是否符合固定格式。當流程需要把回應與檢索內容一起驗收時，這個模組會補上證據與格式層的檢查。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `on_failure` | `string` | 否 | `"retry_plan"` | 檢查失敗時的下一步；可用值為 `"retry_plan"` 或 `"end"`。 |