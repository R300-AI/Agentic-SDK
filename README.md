# Agentic SDK

Agentic SDK 是一個以 Python workflow 組裝 Agent 行為的 SDK。你可以用 Perceive、Plan、Retrieve、Action、Reflect 等模組建立可測試、可替換、可觀測的 Agent 流程，並在 Playground 中用 Builder / Runner 快速試作。

從這個版本開始，SDK 的共同 memory 抽象是 `MemoryStore`，而 `InContextMemory` 與 `PersistentMemory` 是同層、可互換的 memory 類型。`InContextMemory` 偏重以時間順序保存同一個 session 的 `user -> assistant -> user -> assistant` 完整 turn 歷史；所有需要模型的模組都會透過 `MemoryStore` 讀取這份歷史，不再只看當輪 `user_message`。

## 核心概念

一個 workflow 由幾個可選模組組成：

- Perceive：整理使用者輸入，產生可供後續步驟使用的感知結果。
- Plan：決定下一步要 Retrieve、Action，或結束流程。
- Retrieve：從規則、關鍵字或語意檢索中取得支援資料。
- Action：產生最終回覆、呼叫工具，或執行自訂處理邏輯。
- Reflect：檢查結果品質或資料依據，必要時中止或重新規劃。

最小 workflow 只需要 `Workflow` 加上你需要的模組。所有模組都可以用一般 Python 物件替換，因此適合從小型 PoC 擴充到正式應用。

`Workflow.run(...)` 仍支援最簡單的單輪呼叫。`Workflow` 預設會以 `InContextMemory` 承接同一個 `session_id` 的完整對話歷史；若你之後需要替換記憶實作，可以在建立 workflow 時傳入 memory 物件，例如 `memory = InContextMemory()` 搭配 `Workflow(memory_type=memory)`。`memory_type` 也接受 `"in_context"`、`"persistent"` 或既有的 memory class 形式。`WorkflowState` 則保留執行中的中繼結果、payload 與觀測資料。

## 安裝

需要 Python 3.10 以上、3.13 以下；本 repo 的開發環境建議使用 Python 3.12。

```bash
python -m pip install "git+https://github.com/R300-AI/Agentic-SDK.git"
python -c "import agentic_sdk; print('Agentic SDK import ok')"
```

`pip install https://github.com/R300-AI/Agentic-SDK.git` 不是 pip 的 Git repository 語法；pip 會把它當成一般下載檔。請使用上面的 `git+https://...` VCS URL，或命名形式：`python -m pip install "agentic-sdk @ git+https://github.com/R300-AI/Agentic-SDK.git"`。

## 快速開始

### 1. 最小可執行 Workflow

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
    workflow_name="知識問答 Agent",
    description="根據內建關鍵字知識庫回答常見問題。",
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["agentic sdk", "sdk"],
                "content": "Agentic SDK 是一個以 workflow 組裝 agent 行為的 Python library。",
            },
            {
                "keywords": ["tsip"],
                "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            },
        ],
    ),
    action=DirectAnswerAction(),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)
```

`PassThroughPerceive` 會保留原始輸入，`KeywordRetrieve` 依關鍵字取得支援資料，`DirectAnswerAction` 則直接回傳檢索到的內容。

如果你之後用同一個 `session_id` 再次呼叫同一個 `Workflow`，新的使用者輸入與前一次 assistant 回覆都會保留在 `result.memory` 中。

### 2. 使用 OpenAI-compatible 生成回覆

可搭配任何 OpenAI-compatible endpoint，例如 Azure AI Foundry、Ollama 或其他相容服務。

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
    workflow_name="Foundry 回覆 Agent",
    description="用 OpenAI-compatible 模型整理檢索結果並生成自然語句回覆。",
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["tsip"],
                "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            },
        ],
    ),
    action=GenerativeAction(
        api_key="ollama",
        base_url="http://localhost:11434/v1/",
        model="llama3.2:1b",
    ),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)
```

### 3. 直接串流 Action 回覆

`Workflow.stream(...)` 會直接迭代使用者可見的 Action text，不會輸出 Perceive、Plan 或 Reflect 的結構化 JSON。可串流的 Action 會即時產生 token；非串流 Action 會在完成時產生一次最終文字。完整迭代後可從 `stream.result` 取得 `WorkflowResult`：

```python
def on_event(event):
    if event["type"] == "stage" and event["phase"] == "start":
        print(f"\n【{event['module']}】{event['label']}")


stream = workflow.stream("TSiP 是什麼？", event_callback=on_event)
for delta in stream:
    print(delta, end="", flush=True)

result = stream.result
```

`stream()` 接受與 `run()` 相同的輸入、session、memory 與 attachment 參數（不包含 `event_callback`）。若 workflow 發生未由模組處理的例外，迭代器會在已產生的 token 輸出後重新拋出該例外；Action 自行處理的錯誤則保留 `run()` 的 `WorkflowResult` 行為。

### 4. 使用 ToolCallAction 產生 OpenAI 標準工具呼叫

`ToolCallAction` 使用 OpenAI SDK 的 `tools` / `tool_choice` 標準格式，並把模型回傳的 `message.tool_calls` 正規化到 `result.entities["latest_tool_calls"]`。

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
                    "customer_name": {
                        "type": "string",
                        "description": "預約人姓名。",
                    },
                    "booking_time": {
                        "type": "string",
                        "description": "使用者想預約的日期與時間。",
                    },
                },
                "required": ["customer_name", "booking_time"],
                "additionalProperties": False,
            },
        },
    }
]

workflow = Workflow(
    workflow_name="預約工具 Agent",
    description="根據使用者輸入判斷是否要發出預約工具呼叫。",
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["booking", "預約", "球場"],
                "content": "球場預約需要留下姓名與預約時間。",
            },
        ],
    ),
    action=ToolCallAction(
        api_key="<API key>",
        base_url="<OpenAI-compatible base_url>",
        model="<支援 tool calling 的模型>",
        tools=tools,
    ),
)

result = workflow.run("我想預約明天下午三點的球場，姓名是王小明。")
print(result.final_message)
print(result.entities["latest_tool_calls"])
```

SDK 只負責產生與保存標準 tool call 結果；真正呼叫外部 API、呈現確認面板或提交表單，可以由應用層或 Playground Runner 承接。

### 5. 自訂 Action

Action 也可以是一般 Python class。自訂 Action 會收到 `WorkflowState`，可以透過 `state.lookup(...)` 讀取前面模組產生的資料。

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive


class SummaryAction:
    def __call__(self, state):
        summary = state.lookup("latest_retrieved_content") or "沒有命中任何條目。"
        return f"自訂 Action 回傳：{summary}"


workflow = Workflow(
    workflow_name="摘要處理 Agent",
    description="把檢索內容交給自訂 Action 做二次整理。",
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["agentic sdk", "sdk"],
                "content": "Agentic SDK 讓你用 workflow 組裝 agent 行為。",
            },
        ],
    ),
    action=SummaryAction(),
)

result = workflow.run("請介紹 Agentic SDK")
print(result.final_message)
```

若自訂模組需要直接讀取完整對話，應優先透過 `state.memory` 這個通用 `MemoryStore` 介面，而不是把模組綁死在特定 `InContextMemory` 類別；要讀取最新一輪使用者文字，則可使用 `state.latest_user_message()`。

## Playground

正式 Playground 是 Flask app，包含 Entry、Builder、Runner、Source preview/export、AI Hub 登入與儲存串接，以及 ToolCallAction 互動面板。

```bash
uv run python -m flask --app playground.app:app run --host 127.0.0.1 --port 5050 --no-reload --no-debugger
```

啟動後開啟 Playground 入口：

```text
http://127.0.0.1:5050/playground
```

以下流程都從 `http://127.0.0.1:5050/playground` 開始；第一頁會看到「使用 AI Hub 登入」與「不登入，匿名試用」兩張卡片。

### 基本功能

操作：**`/playground`** -> **開始匿名試用** -> **Builder** -> **開始建立 Agent** -> **Runner**

### 新建與儲存

操作：**`/playground`** -> **登入並開始建立** -> **開始新建** -> **Builder** -> **開始建立 Agent** -> **Runner** -> **儲存**

### 載入與更新

操作：**`/playground`** -> **登入並開始建立** -> **編輯** -> **Runner** -> **編輯設定** -> **Runner** -> **儲存**

> Runner 若要呼叫 OpenAI-compatible endpoint，請在啟動 Flask 前於 `.env` 或環境變數提供對應的 `*_MODEL`、`*_BASE_URL`、`*_API_KEY`。