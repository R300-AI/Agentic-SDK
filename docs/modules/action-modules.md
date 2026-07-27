# Action

Action 模組負責把前面節點收集到的資訊轉成回應內容。這一頁先整理 Action 家族的交付方式，再依序展開三種不同的回應產生模組。每個模組會先列出建立物件時使用的初始化參數，再列出 Action 對外交付的標準輸出參數；前段帶入的內容主要來自 `Entities`，可回到 [Module Family](index.md) 的中央定義理解。

## DirectAnswerAction

舊名對應：`DirectAnswerAction`

`DirectAnswerAction` 直接根據取回內容組成最終回應，以條目內容為主完成回答。它適合 README 最小流程與條目式固定回答，也代表 Action 家族裡最直接的交付方式。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `memory_key` | `string` | 否 | `"latest_retrieved_content"` | 從 workflow state 讀取最終回答內容的 key。 |
| `fallback` | `string` | 否 | `"沒有命中任何條目。"` | 指定 key 沒有內容時使用的回答文字。 |
| `prefix` | `string` | 否 | `""` | 加在回答文字前的固定前綴。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"TSiP 是工研院主導的國產 AI 晶片落地藍圖。"` | 對外回應文字。 |
| `final_data` | `object|null` | `null` | 純文字回應時固定 `null`。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

## GenerativeAction

舊名對應：`CompletionAction`

`GenerativeAction` 根據完整對話歷史、輸入摘要與取回內容生成最終回應。當流程要把多筆條目、歷史紀錄或摘要整合成一段自然語言時，就會接到這個模組。

固定格式輸出也使用 `GenerativeAction`，透過 `system_prompt` 指定 JSON、表格或欄位格式。若需要 OpenAI 標準工具呼叫或把互動欄位提交給外部 API，請改用 `ToolCallAction`。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。模組會在內部建立 OpenAI client，並在推論呼叫時使用指定的 `model`。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱。 |
| `temperature` | `number|null` | 否 | `null` | 生成溫度；`null` 時不傳此參數，交由端點預設處理。 |
| `system_prompt` | `string|null` | 否 | `null` | 覆寫 Action 系統提示；未提供時使用 SDK 預設 prompt。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"建議優先考慮支撐型慢跑鞋，因為較適合久站與足弓支撐需求。"` | 對外回應文字。 |
| `final_data` | `object|null` | `null` | SDK 不解析模型文字；若需要固定格式，請在 `system_prompt` 約束輸出內容，應用層再自行解析。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

## ToolCallAction

舊名對應：無。這是 OpenAI tool calling 專用 Action。

`ToolCallAction` 使用 OpenAI SDK 標準的 `tools`、`tool_choice` 與 `message.tool_calls` 介面。當 workflow 需要讓模型根據完整對話與目前檢索內容決定是否呼叫外部 API、後端函式或應用程式工具時，這個模組會把 tool schema 交給模型，並把模型回傳的 tool calls 保存到 workflow 結果中。

此模組只產生 OpenAI 標準 tool call，不會在 SDK 內直接執行外部工具。應用層可以讀取 `latest_tool_calls`，再依照自己的權限控管、驗證與錯誤處理流程執行實際 API 或函式。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱；需選用支援 tool calling 的模型。 |
| `temperature` | `number|null` | 否 | `null` | 生成溫度；`null` 時不傳此參數。 |
| `system_prompt` | `string|null` | 否 | `null` | 覆寫 Action 系統提示；未提供時使用 SDK 預設 prompt。 |
| `tools` | `array<object>` | 否 | `[]` | OpenAI Chat Completions tools schema；目前主要使用 `type="function"` 的 function tool。 |
| `tool_choice` | `string|object|null` | 否 | `"auto"` | 傳給 OpenAI SDK 的 tool choice 設定，例如 `"auto"`、`"none"` 或指定 function。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `action_status` | `string` | `"ok"` | 只允許 `ok` 或 `error`。 |
| `final_message` | `string` | `"已產生工具呼叫。"` | 對外回應文字；若模型只回傳 tool calls 而沒有文字內容，SDK 會保留一段簡短訊息。 |
| `tool_calls` | `array<object>` | `[{"id":"call_123","type":"function","function":{"name":"submit_booking","arguments":"{...}"}}]` | OpenAI `message.tool_calls` 的標準化結果，會保存在 workflow `Entities` 的 `latest_tool_calls`。 |
| `final_data` | `object|null` | `null` | `ToolCallAction` 不直接執行工具，因此不在此放入外部 API 執行結果。 |
| `action_error` | `string` | `""` | 成功時固定空字串；失敗時填錯誤訊息。 |

### 範例

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive, ToolCallAction

tools = [
	{
		"type": "function",
		"function": {
			"name": "submit_booking",
			"description": "提交球場預約資料。",
			"parameters": {
				"type": "object",
				"properties": {
					"customer_name": {"type": "string", "description": "預約人姓名。"},
					"booking_time": {"type": "string", "description": "使用者想預約的日期與時間。"},
				},
				"required": ["customer_name", "booking_time"],
				"additionalProperties": False,
			},
		},
	}
]

workflow = Workflow(
	perceive=PassThroughPerceive(),
	retrieve=KeywordRetrieve(
		items=[
			{
				"keywords": ["booking", "預約", "球場"],
				"content": "球場預約需要留下姓名與預約時間。",
			}
		]
	),
	action=ToolCallAction(
		api_key="<填入 API key>",
		base_url="<填入 OpenAI-compatible base_url>",
		model="<填入支援 tool calling 的模型名稱>",
		tools=tools,
	),
)

result = workflow.run("我想預約明天下午三點的球場，姓名是王小明。")
print(result.final_message)
print(result.entities["latest_tool_calls"])
```