# Agentic SDK

Agentic SDK 是一個 Python 程式庫，用來建立一個完整從AI Agent接收輸入到輸出的完整過程。這個過程是依照　Park 等人 2023 年發表的 [Generative Agents](https://arxiv.org/abs/2304.03442)作為核心概念，將人類的各種決策行為視為一種可以持續循環的**流程**（Ｗorkflow），這個流程會由**功能模組**（Module）與**記憶單元**（Memory）所組成：**感知**（Perceive）負責把進來的東西變成看得懂的內容，**規劃**（Plan）負責決定接下來要做什麼，**查找**（Retrieve）負責去找手上沒有的資料，**行動**（Action）負責實際動手做，**反思**（Reflect）負責判斷結果行不行；中間過程的內容都交給記憶單元保存，需要時再取回來用。每一類功能目前內建的模組如下：

| 功能模組 | 內建的模組 |
| --- | --- |
| 感知（Perceive） | 原樣帶過、純文字、文字加圖片、即時語音 |
| 規劃（Plan） | 判斷下一步該做什麼 |
| 查找（Retrieve） | 不查直接過、關鍵字比對、語意相似 |
| 行動（Action） | 直接作答、模型生成、呼叫工具、語音輸出 |
| 反思（Reflect） | 檢查回應答不答得上、檢查行動結果有沒有出錯 |

上表每一類選一個模組就組成一條完整的流程，不需要自己實作。要換掉其中一個就依照同一組介面寫一個放進來，其他模組不受影響。

## 為什麼要使用 Agentic SDK？

Agentic SDK 的目的是為了讓各類 AI 晶片上的模型都能變成落地的應用。它不限定晶片供應商，只要推論服務提供 OpenAI 相容端點就接得上；接上之後再透過 AI Hub 交到場域手上驗證，晶片廠商也可以用自己的硬體交出場域驗收過的應用成果。

1. **自訂 AI 晶片部署** — 部署在 AI 晶片上的模型只要封裝成 OpenAI 相容端點就能接進流程，使原本只提供推論的運算資源直接升級成一個 AI　代理。
2. **快速整合代理技術** — 把自己開發的模型或方法按照介面規範包成其中一類的模組，就可以直接整合內建的模組組合完整的代理服務。
3. **落地應用驗證** — [Playground](playground/README.md) 這個網頁工具不用寫程式就能把模組組成流程並試跑，使落地場域可以在整套系統建置完成前先確認效果。

場域試用的的 Playground可以直接「檢視程式碼」取得整條流程的完整語法，再把端點換成現場晶片上的推論服務就能上線運作。

## 安裝

需要 Python 3.11 以上、3.13 以下，開發環境建議 3.12；下面第一行的 `@v0.2.0` 是版本標籤，
指定它才會固定在該版的行為，省略時裝到 `main` 的最新內容，而 `main` 改變行為時程式不會報錯、只是結果不一樣。

```bash
python -m pip install "git+https://github.com/R300-AI/Agentic-SDK.git@v0.2.0"
python -c "import agentic_sdk; print('Agentic SDK import ok')"
```

## 三個例子

第一個用三類模組組出一條可執行的流程，不需要任何模型服務；第二個把 Action 換成模型生成；
第三個把 Plan 換成自訂物件。沒有指定的類別不會出現在這一輪，所以第一個例子只跑 Perceive、Retrieve、Action 三類。

### 用現成模組組一條流程

```python
from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
    workflow_name="請假問答",
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {"keywords": ["特休", "年假"], "content": "年資滿一年可休七天特休。"},
            {"keywords": ["病假"], "content": "病假一年三十天，超過三十天需附診斷證明。"},
        ],
    ),
    action=DirectAnswerAction(),
)

result = workflow.run("特休有幾天？")
print(result.final_message)   # 年資滿一年可休七天特休。
```

`PassThroughPerceive` 原樣保留輸入，`KeywordRetrieve` 逐字比對關鍵字取出條目，`DirectAnswerAction`
直接回傳取到的內容；沒有命中時回傳預設的 `No matching entries.`，改成自己的句子傳 `KeywordRetrieve(fallback="...")`。

### 換掉推論服務

```python
from agentic_sdk.modules import GenerativeAction

workflow = Workflow(
    workflow_name="請假問答",
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {"keywords": ["特休", "年假"], "content": "年資滿一年可休七天特休。"},
        ],
    ),
    action=GenerativeAction(
        api_key="ollama",
        base_url="http://localhost:11434/v1/",
        model="llama3.2:1b",
    ),
)

print(workflow.run("我到職滿一年了，可以請幾天特休？").final_message)
```

把回覆改由模型整理，`base_url` 指到哪裡就跑在哪裡，Azure AI Foundry、本機的 Ollama、
自家硬體上的服務都是同一個寫法；這個例子連的是本機的 Ollama，需要先在本機把它跑起來。

### 換掉一個模組

```python
from agentic_sdk.core import ModuleOutput

class AlwaysRetrieveOnce:
    """自訂的規劃機制：第一次先查資料，查過就回答。"""

    name = "plan"

    def __call__(self, state):
        looked_up = state.lookup("latest_retrieved_content")
        return ModuleOutput(next_module="action" if looked_up else "retrieve")


workflow = Workflow(
    workflow_name="自訂規劃",
    perceive=PassThroughPerceive(),
    plan=AlwaysRetrieveOnce(),
    retrieve=KeywordRetrieve(
        items=[{"keywords": ["特休"], "content": "年資滿一年可休七天特休。"}],
    ),
    action=DirectAnswerAction(),
)

print(workflow.run("特休有幾天？").final_message)
# 依序經過 perceive、plan、retrieve、plan、action
```

自訂模組不必繼承任何基底類別，只要有 `name` 說明它屬於哪一類、有 `__call__` 收下當前狀態並回傳
`ModuleOutput`。下一站由規劃模組選：感知、檢索與反思做完都回到規劃模組，行動做完這一輪結束；
沒有指定規劃模組時，流程用不呼叫模型的 `PassThroughPlan` 先查一次再回答。完整合約見[五大模組的共同寫法](https://r300-ai.github.io/Agentic-SDK/tutorials/module-writing-basics/)。

## 延伸閱讀

[Agentic SDK 文件網站](https://r300-ai.github.io/Agentic-SDK/)有完整的模組規格與教材。教材從安裝開始，都附可以直接執行的 Notebooks 程式碼：

* [安裝與第一條流程](https://r300-ai.github.io/Agentic-SDK/tutorials/getting-started/)
* [用內建模組組出流程](https://r300-ai.github.io/Agentic-SDK/tutorials/build-and-run-a-workflow/)
* [推論過程即時顯示](https://r300-ai.github.io/Agentic-SDK/tutorials/watch-a-workflow-run/)
* [自訂推論過程顯示的內容](https://r300-ai.github.io/Agentic-SDK/tutorials/configure-workflow-events/)
* [記住前幾輪的對話](https://r300-ai.github.io/Agentic-SDK/tutorials/multi-turn-conversation/)
* [回答依據檢查](https://r300-ai.github.io/Agentic-SDK/tutorials/search-documents-and-answer/)
* [工具呼叫與選擇面板](https://r300-ai.github.io/Agentic-SDK/tutorials/call-tools-from-a-workflow/)
* [自訂模組](https://r300-ai.github.io/Agentic-SDK/tutorials/module-writing-basics/)
* [語音回答與插話中斷](https://r300-ai.github.io/Agentic-SDK/tutorials/talk-to-a-workflow/)

## 貢獻者

[![Contributors](https://contrib.rocks/image?repo=R300-AI/Agentic-SDK)](https://github.com/R300-AI/Agentic-SDK/graphs/contributors)

由工業技術研究院的團隊開發與維護。[貢獻指南](CONTRIBUTING.md)列出每一位貢獻者的所屬單位與負責範疇。
