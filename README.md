# Agentic SDK

Agentic SDK 是一個以 Python workflow 組裝 Agent 行為的 SDK。你可以用 Perceive、Plan、Retrieve、Action、Reflect 等模組建立可測試、可替換、可觀測的 Agent 流程，並在 Playground 中用 Builder / Runner 快速試作。

## 核心概念

一個 workflow 由幾個可選模組組成：

- Perceive：整理使用者輸入，產生可供後續步驟使用的感知結果。
- Plan：決定下一步要 Retrieve、Action，或結束流程。
- Retrieve：從規則、關鍵字、語意或混合檢索中取得支援資料。
- Action：產生最終回覆、呼叫工具，或執行自訂處理邏輯。
- Reflect：檢查結果品質或資料依據，必要時中止或重新規劃。

最小 workflow 只需要 `Workflow` 加上你需要的模組。所有模組都可以用一般 Python 物件替換，因此適合從小型 PoC 擴充到正式應用。

## 安裝

需要 Python 3.12。

```bash
git clone https://github.com/R300-AI/Agentic-SDK.git
cd Agentic-SDK
python -m pip install -r requirements.txt
python -c "import agentic_sdk; print('Agentic SDK import ok')"
```

## 快速開始

### 1. 最小可執行 Workflow

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
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

### 2. 使用 OpenAI-compatible 生成回覆

可搭配任何 OpenAI-compatible endpoint，例如 Azure AI Foundry、Ollama 或其他相容服務。

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
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

### 3. 使用 ToolCallAction 產生 OpenAI 標準工具呼叫

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

### 4. 自訂 Action

Action 也可以是一般 Python class。自訂 Action 會收到 `WorkflowState`，可以透過 `state.lookup(...)` 讀取前面模組產生的資料。

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive


class SummaryAction:
    def __call__(self, state):
        summary = state.lookup("latest_retrieved_content") or "沒有命中任何條目。"
        return f"自訂 Action 回傳：{summary}"


workflow = Workflow(
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

## Playground

正式 Playground 是 Flask app，包含 Entry、Builder、Runner、Source preview/export、AI Hub 登入與儲存串接，以及 ToolCallAction 互動面板。

```bash
python -m flask --app playground.app:app run --host 127.0.0.1 --port 5050 --no-reload --no-debugger
```

開啟：

- `http://127.0.0.1:5050/playground`
- `http://127.0.0.1:5050/playground/builder`
- `http://127.0.0.1:5050/playground/run`

Runner 若要使用 OpenAI-compatible endpoint，可以在本機環境或部署環境提供對應的 `*_MODEL`、`*_BASE_URL`、`*_API_KEY` 變數。Azure 部署建議透過 Key Vault 與 App Service managed identity 管理機密。

AI Hub 登入模式會呼叫 AI Hub 提供的帳密驗證 API：`POST /api/playground/auth/verify`。專案根目錄的 [.env](.env) 已記錄 `AI_HUB_BASE_URL`，本機啟動時會自動讀取，不需要另外設定系統環境變數：

```bash
AI_HUB_BASE_URL=https://ai-hub-portal.azurewebsites.net
AI_HUB_PLAYGROUND_ORIGIN=https://agentic-sdk-playground.azurewebsites.net
```

驗證成功且回傳 `{"valid": true}` 時，Playground 才會進入已登入模式；AI Hub 回傳 invalid，或 API 暫時不可用時，都會拒絕登入。登入成功後，Playground 會以 server-side 暫存 ticket 保留本次 session 的 AI Hub credential，呼叫 `POST /api/playground/agents` 列出同帳號所有 Agent，並可用 `POST /api/playground/agents/<agent_id>/config/load` 載入或重新載入配置。Runner 按「儲存」時會呼叫 `POST /api/playground/config/save`；若 session 尚無 `agent_id`，AI Hub 會建立新 Agent 並回傳 `agent_id`，後續儲存會更新同一個 Agent。若 AI Hub host 之後更換，只需要修改 [.env](.env) 的 `AI_HUB_BASE_URL`。

## Demo 與文件

- Demo 範例在 `demo/README.md`。
- 文件網站來源在 `docs/`，本機可用 `python -m mkdocs build --strict` 驗證。
- GitHub Actions 到 Azure App Service 的部署說明在 `docs/github_cicd_workflow.md`。

## 測試

```bash
python -m pytest -q
```
