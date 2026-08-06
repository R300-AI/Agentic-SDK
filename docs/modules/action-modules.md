# 回覆與動作

回覆與動作模組把前面步驟整理的資料轉成使用者可讀的回覆，或整理成你的程式可以執行的工具請求。前段資料主要來自 [模組家族](index.md) 所說的共用資料。

## 取得回覆結果

每次工作流程完成後，應用程式從 `result.final_message` 取得最後回覆文字。需要讓後續步驟或周邊程式讀取本輪資料時，可從 `result.entities` 取得最新回覆、工具請求和模型用量。

| 你要取得的資料 | 程式欄位 | 用途 |
| --- | --- | --- |
| 最後回覆 | `result.final_message` | 顯示或傳回給使用者的文字。 |
| 最新回覆內容 | `result.entities["latest_final_message"]` | 供後續步驟或你的程式接續處理。 |
| 工具請求 | `result.entities["latest_tool_calls"]` | `ToolCallAction` 整理出的工具名稱與參數。 |
| 模型用量 | `result.entities["_llm_usage"]` | 生成回覆或工具請求時使用的模型和 token 數。 |

## DirectAnswerAction

參考論文：無特定 arXiv 對應；此模組是工程化 baseline。

`DirectAnswerAction` 直接根據取回內容組成最終回應，以條目內容為主完成回答。它適合 README 最小流程與條目式固定回答，也代表 Action 家族裡最直接的交付方式。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `memory_key` | `string` | 否 | `"latest_retrieved_content"` | 從 workflow state 讀取最終回答內容的 key。 |
| `fallback` | `string` | 否 | `"No matching entries."` | 指定 key 沒有內容時使用的回答文字。 |
| `prefix` | `string` | 否 | `""` | 加在回答文字前的固定前綴。 |

### 回覆內容

`DirectAnswerAction` 會把取回內容放入 `result.final_message`，並同步寫入 `result.entities["latest_final_message"]`。

## GenerativeAction

參考論文：[Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)

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

### 回覆內容與用量

`GenerativeAction` 會把模型產生的文字放入 `result.final_message` 和 `result.entities["latest_final_message"]`。`result.entities["_llm_usage"]` 會記錄模型名稱、輸入 token 數與輸出 token 數。需要 JSON、表格或固定欄位時，可在 `system_prompt` 說明回覆格式，再由你的程式讀取與驗證。

## ToolCallAction

參考論文：[Toolformer: Language Models Can Teach Themselves to Use Tools](https://arxiv.org/abs/2302.04761)

`ToolCallAction` 使用 OpenAI SDK 標準的 `tools`、`tool_choice` 與 `message.tool_calls` 介面。當 workflow 需要讓模型根據完整對話與目前檢索內容決定是否呼叫外部 API、後端函式或應用程式工具時，這個模組會把 tool schema 交給模型，並把模型回傳的 tool calls 保存到 workflow 結果中。

若 `tool_choice="none"`，SDK 會把該輪請求視為文字優先模式，不把 `tools` 傳給模型。這可避免部分 OpenAI-compatible 端點在收到 tools 後仍提前產生 tool call；應用層仍可保留同一份 schema 作為 UI 表單或確認面板的呈現合約。

此模組產生 OpenAI 標準工具請求，並將結果保存到 `latest_tool_calls`。應用程式讀取後，依自身的權限、驗證與錯誤處理規則執行對應的 API 或函式。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱；需選用支援 tool calling 的模型。 |
| `temperature` | `number|null` | 否 | `null` | 生成溫度；`null` 時不傳此參數。 |
| `system_prompt` | `string|null` | 否 | `null` | 覆寫 Action 系統提示；未提供時使用 SDK 預設 prompt。 |
| `tools` | `array<object>` | 否 | `[]` | OpenAI Chat Completions 的工具定義；常用 `type="function"` 表示函式工具。 |
| `tool_choice` | `string|object|null` | 否 | `"auto"` | Tool choice 設定，例如 `"auto"`、`"none"` 或指定 function；其中 `"none"` 會讓 SDK 不送出 `tools`，改為只產生文字回覆。 |

### 工具請求與回覆內容

`ToolCallAction` 會把回覆文字放入 `result.final_message`，並將工具請求整理到 `result.entities["latest_tool_calls"]`。每一筆工具請求包含識別碼、工具名稱和參數文字；你的程式讀取後驗證參數、執行對應工作，再決定如何回覆使用者。`result.entities["_llm_usage"]` 會記錄本輪模型用量。

### 範例

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive, ToolCallAction

tools = [
	{
		"type": "function",
		"function": {
			"name": "record_task",
			"description": "建立任務記錄。",
			"parameters": {
				"type": "object",
				"properties": {
					"task_summary": {"type": "string", "description": "使用者要記錄的任務摘要。"},
					"priority": {"type": "string", "description": "任務優先度。"},
				},
				"required": ["task_summary", "priority"],
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
				"keywords": ["任務", "記錄", "優先度"],
				"content": "建立任務記錄時需要任務摘要與優先度。",
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

result = workflow.run("請把這件事記成高優先度任務：整理部署檢查清單。")
print(result.final_message)
print(result.entities["latest_tool_calls"])
```