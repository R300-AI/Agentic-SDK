# Agentic SDK

如果你是 Python 開發者，想先把 Agentic SDK 安裝起來、跑出第一條 workflow、看懂內建節點怎麼組合，然後再決定什麼時候接模型節點，這一頁就是入口。這份 README 只做兩件事：先帶你完成安裝，再用三個由淺到深的 quickstart 範例帶你理解 SDK 的基本用法。

## 安裝

1. 先依 [Git 官方安裝頁](https://git-scm.com/downloads) 完成安裝，然後確認終端機能找到 Git。

   ```bash
   git --version
   ```

2. 再依 [Python 官方安裝頁](https://www.python.org/downloads/) 安裝 Python 3.12，然後確認版本正確。

   ```bash
   python --version
   ```

3. 依 [uv 官方安裝說明](https://docs.astral.sh/uv/getting-started/installation/) 安裝 `uv`，然後確認終端機能找到 `uv`。

   ```bash
   uv --version
   ```

4. 複製這個 repo，並切換到專案目錄。

   ```bash
   git clone https://github.com/<your-org>/Agentic-SDK.git
   cd Agentic-SDK
   ```

5. 安裝專案依賴。

   ```bash
   uv sync --extra dev
   ```

6. 驗證安裝結果，確認 Python 已經能 import 這個套件。

   ```bash
   python -c "import agentic_sdk; print('Agentic SDK import ok')"
   ```

7. 只有在你要跑 `demo/` 時，才需要依 [Node.js 官方安裝頁](https://nodejs.org/en/download) 安裝 Node.js 22 以上，然後確認版本。

   ```bash
   node --version
   ```

## 快速開始

### 1. 本地知識查詢基本範例

這個 agent workflow 會先接住使用者問題，再從你本地準備好的條目中找答案，最後直接把命中的內容回傳出去。它的用途不是展示模型能力，而是先讓你用最小成本看懂：就算完全不接模型，Agentic SDK 也可以先組出一條可執行、可驗證的 workflow。

```python
from agentic_sdk import Workflow
from agentic_sdk.nodes.perceive import RuleBasedPerceive
from agentic_sdk.nodes.retrieve import StubRetrieve
from agentic_sdk.nodes.action import ContentAction

workflow = Workflow(
    perceive=RuleBasedPerceive(
        welcome_message="你好，我可以回答 Agentic SDK 的基本問題。",
    ),
    retrieve=StubRetrieve(
        items=[
            {
                "keywords": ["agentic sdk", "sdk"],
                "content": "Agentic SDK 是一個可組裝 Agents Workflow 的 Python 開發庫。",
            },
            {
                "keywords": ["tsip"],
                "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            },
        ],
    ),
    action=ContentAction(
        fallback_answer="目前沒有命中知識庫條目。",
    ),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)
```

如果設定正確，你應該看到：

> TSiP 是工研院主導的國產 AI 晶片落地藍圖。

### 2. 用內建節點接 OpenAI-compatible 模型 API 範例

這個 agent workflow 示範的重點不是某一個特定 provider，而是你如何直接沿用 Agentic SDK 內建節點，同時把模型呼叫交給你自己建立的 OpenAI SDK client。這比較符合平台的核心定位：不同加速器包出來的模型服務只要對外長得像 OpenAI-compatible API，使用者就能自己決定要接哪個端點。

先確認你的 OpenAI-compatible 模型服務已經啟動。以下用 Ollama 當例子：

```bash
ollama pull llama3.1:8b
ollama serve
```

接著把你建立好的 OpenAI client 直接交給 `CompletionAction`：

```python
from openai import OpenAI

from agentic_sdk import Workflow
from agentic_sdk.nodes.action import CompletionAction
from agentic_sdk.nodes.perceive import RuleBasedPerceive
from agentic_sdk.nodes.retrieve import StubRetrieve


openai_client = OpenAI(
    base_url="http://localhost:11434/v1",
)


workflow = Workflow(
    perceive=RuleBasedPerceive(),
    retrieve=StubRetrieve(
        items=[
            {
                "keywords": ["tsip"],
                "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            },
        ],
    ),
    action=CompletionAction(
        client=openai_client,
    ),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)
```

這個範例的重點是：模型服務不需要先被包進 Agentic SDK。只要你最後交給 `CompletionAction` 的物件具備 OpenAI client 常用的呼叫形狀，例如 `chat.completions.create(...)`，你就可以先用 `OpenAI(...)` 建 client，再把它直接交給 Agentic SDK 內建節點。若你的 endpoint 本身已經綁定模型，`CompletionAction` 也可以省略 `model`。

### 3. 把 Azure Foundry client 注入同一個 CompletionAction 範例

這題示範的是另一種情境：當 Azure Foundry 端的連線與 deployment 綁定已經在你的應用程式裡處理好時，Agentic SDK 只需要接收最後要用的 client。README 只保留注入方式，不在這裡展開 adapter 細節。

```python
from agentic_sdk import Workflow
from agentic_sdk.nodes.action import CompletionAction
from agentic_sdk.nodes.perceive import RuleBasedPerceive
from agentic_sdk.nodes.retrieve import StubRetrieve


# 你的應用程式先把 Azure Foundry client 整理成 CompletionAction 可用的 OpenAI-style 物件
foundry_client = build_foundry_openai_client()


workflow = Workflow(
    perceive=RuleBasedPerceive(),
    retrieve=StubRetrieve(
        items=[
            {
                "keywords": ["tsip"],
                "content": "TSiP is the ITRI-led domestic AI chip landing blueprint.",
            },
        ],
    ),
    action=CompletionAction(
        client=foundry_client,
    ),
)

result = workflow.run("What is TSiP?")
print(result.final_message)
```

這個範例的重點是：第二題在示範「直接交 OpenAI client」，第三題在示範「先在應用程式側完成 Azure Foundry 整合，再把整理好的 OpenAI-style client 注入 `CompletionAction`」。如果你要看注入節點實例的正式入口，可以接著看 docs 裡的 `node_overrides` 範例。


If you want more detail:

1. Docs index: [docs/README.md](docs/README.md)
2. Python SDK integration: [docs/05-api-reference/python-sdk-integration.md](docs/05-api-reference/python-sdk-integration.md)
3. Workflow engine: [agentic_sdk/workflow/engine.py](agentic_sdk/workflow/engine.py)
4. Demo app: [demo/README.md](demo/README.md)

