# 讓畫面知道 Agent 跑到哪一步

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/02-watch-a-workflow-run.ipynb)

這份教材示範 MVP 階段最重要的執行提示：Chat WebUI 在最終文字開始輸出前，要如何知道目前 workflow 正在哪個階段。SDK 會透過 `event_callback` 送出 stage event，畫面只要讀取事件裡的 `label` 就能更新狀態列。

## 你會學到

- 用 `Workflow(stage_labels=...)` 設定每個階段的畫面文字。
- 用 `event_callback=on_event` 直接印出 SDK 送出的事件格式。
- 看懂 `type == "stage"`、`status == "running"`、`label` 這幾個欄位如何供 WebUI 顯示。
- 把 notebook 看到的事件格式對照到 Playground Runner 的即時流程畫面。

## 核心寫法

```python
stage_labels = {
	"perceive": "正在理解你的問題",
	"retrieve": "正在查找參考資料",
	"action": "正在準備回覆",
}

workflow = Workflow(
	workflow_name="WebUI 階段提示 Agent",
	stage_labels=stage_labels,
	perceive=PassThroughPerceive(),
	retrieve=KeywordRetrieve(items=[{"keywords": ["sdk"], "content": "Agentic SDK 可以把工作流階段交給畫面顯示。"}]),
	action=DirectAnswerAction(),
)

def on_event(event):
	print(event)

result = workflow.run("請介紹 SDK 的階段提示方式", event_callback=on_event)
```

正式 WebUI 不需要把整包事件印出來；收到 `type == "stage"` 且 `status == "running"` 的事件時，顯示 `event["label"]` 即可。等最終文字開始輸出，再切換成回覆輸出狀態。

## 相關文件

- [工作流程](../workflow/index.md)
- [模組家族](../modules/index.md)
