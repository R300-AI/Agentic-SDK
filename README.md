# Agentic SDK

當你要把 Agent 接進實際應用時，往往需要把輸入處理、資料查詢、外部工具與回應流程一起串起來。這些步驟若各自分散實作，後續要調整流程、替換模組或接進既有系統時，整合成本會很快上升。本專案聚焦這類需求，提供一套可在 Python 應用程式中組裝 Agent workflow 的統一框架，讓開發者在整合不同系統時，不必每次都從頭重寫相似的流程骨架。

## Agentic SDK 是什麼

Agentic SDK 是一套用於在 Python 應用程式中組裝 Agent workflow 的 SDK。你可以透過 `Workflow` 串接感知、檢索、執行等模組，並把自訂模型或既有系統整合進同一條流程。

### 核心概念

一條 Agent workflow 通常由幾類模組組成，各自負責不同工作：

- 感知（Perceive）負責整理使用者輸入，形成後續模組可用的結構化理解。
- 規劃（Plan）負責根據當前狀態判斷下一步應前往的模組。
- 檢索（Retrieve）負責補充相關內容、命中條目或其他可用證據。
- 執行（Action）負責產生主要輸出或最終回應。
- 反思（Reflect）負責檢查結果是否可接受，並決定結束或重試。

## 安裝環境

若你要跟著本頁範例實際跑一次 Agentic SDK，請先準備 Python 3.12 環境。下列步驟會帶你完成 repo 下載、依賴安裝與模組匯入確認。若要執行第二個範例，再另外準備 OpenAI-compatible 端點。

1. 依 [Git 官方安裝頁](https://git-scm.com/downloads) 完成安裝。

2. 依 [Python 官方安裝頁](https://www.python.org/downloads/) 安裝 Python 3.12。

3. 複製這個 repo，並切換到專案目錄。

   ```bash
   git clone https://github.com/R300-AI/Agentic-SDK.git
   cd Agentic-SDK
   ```

4. 安裝閱讀原始碼與檢查模組匯入所需的 Python 依賴。

   ```bash
   python -m pip install -r requirements.txt
   ```

5. 執行 import 檢查，以確認 Python 可載入 `agentic_sdk`。

   ```bash
   python -c "import agentic_sdk; print('Agentic SDK import ok')"
   ```


## 快速開始

你可以先照著第一個範例跑出一條最小 workflow，再把模型能力接進同一條流程，最後只替換需要客製化的模組。以下三個範例就依照這個順序安排，讓你逐步熟悉 Agentic SDK 的導入方式。

### 1. 用最少的三類模組組出第一條 workflow

第一個範例會帶你建立第一條可執行流程。你會先用最少的模組組合完成輸入整理、內容命中與回應生成，並熟悉 Agentic SDK 的基本組裝方式。

```python
# 公開介面範例
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

`PassThroughPerceive` 會先讀取使用者問題。`KeywordRetrieve` 會從 `items` 條目中比對 `keywords`，命中後取回對應的 `content`。`DirectAnswerAction` 則直接把前面取回的內容組成回應。`Workflow` 會把這些中間資料保留下來，讓後面的步驟可以直接使用。

### 2. 把 OpenAI SDK client 注入需要模型的模組

第二個範例會把模型能力接進既有 workflow，並示範如何把 OpenAI SDK client 注入需要模型的模組。

以下以本地 Ollama 端點示意 OpenAI SDK 相容端點。

```bash
ollama pull llama3.2:1b
ollama serve
```

`OpenAI(...)` 建立完成後，直接將 client 交給 `GenerativeAction`：

```python
# 公開介面範例
from openai import OpenAI

from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, KeywordRetrieve, PassThroughPerceive

openai_client = OpenAI(
    api_key="not-needed",
    base_url="http://localhost:11434/v1",
)

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
        client=openai_client,
    ),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)
```

此一範例保留原本的輸入處理與條目查詢方式，僅將輸出步驟改為透過 OpenAI Python client 呼叫模型端點。對 AI Hub 而言，重點不在特定 provider，而在模型服務與 Agent workflow 皆沿用 OpenAI SDK 介面。當模型端點遵循同一協定時，模型封裝與 Agent 功能即可使用一致的調用方式，降低不同生態各自定義呼叫介面的整合成本。

### 3. 用最小 custom module 替換內建 Action

到這一步，你已經可以保留前段流程，只把最後的輸出模組換成自己的程式邏輯。

```python
# 公開介面範例
from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive

class SummaryAction:
    def __call__(self, memory):
        summary = memory.lookup("latest_retrieved_content") or "沒有命中任何條目。"
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

`SummaryAction` 直接接收 `Workflow` 建立的 `InContextMemory`，並自記憶體讀取前面模組留下的內容，再組成輸出。這樣你可以保留既有流程，只替換最後的輸出邏輯。

> 這個範例會用到兩個 memory 約定。
>
> - `memory` 是 `Workflow` 建立的 `InContextMemory`。
> - `latest_retrieved_content` 表示最近一次檢索模組命中的主要內容，供後續 `Action` 模組直接讀取。

## 下一步

相關文件如下。

1. 瀏覽器介面操作流程：[demo/README.md](demo/README.md)。
2. 設計藍圖與分階段交付內容：[sdk_blueprint/README.md](sdk_blueprint/README.md)。
