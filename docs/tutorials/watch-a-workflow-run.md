# 讓畫面知道 Agent 跑到哪一步

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/02-watch-a-workflow-run.ipynb)

這份教材只示範 MVP 階段最重要的執行提示：Chat WebUI 在最終文字開始輸出前，要如何知道目前 workflow 正在哪個階段。SDK 會透過 `event_callback` 送出 stage event，畫面直接讀取事件裡的 `label` 更新狀態列。

## 你會學到

- 不設定 `events_schema` 時，直接使用 SDK 的完整預設事件與標準 label。
- 用 `event_callback=on_event` 顯示 stage start event。
- 直接使用 SDK 提供的 `label`，不在 UI 自建 module-to-label mapping。
- 把 notebook 看到的事件格式對照到 Playground Runner 的即時流程畫面。

## 直接使用標準事件

沒有傳入 `events_schema` 時，SDK 對所有實際執行的 module 發送 `stage` 事件，標準 label 是「理解輸入」、「判斷工具順序」、「整理相關來源」、「準備輸出回覆」、「檢查回覆」。

```python
workflow = Workflow(
    workflow_name='WebUI 階段提示 Agent',
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(items=[{'keywords': ['sdk'], 'content': 'Agentic SDK 可以把工作流階段交給畫面顯示。'}]),
    action=DirectAnswerAction(),
)
```

def on_event(event):
    if event['type'] == 'stage' and event['phase'] == 'start':
        print(event['label'])

result = workflow.run('請介紹 SDK 的階段提示方式', event_callback=on_event)
```

正式 WebUI 不需要把整包事件印出來；收到 `type == "stage"` 且 `phase == "start"` 的事件時顯示 `event["label"]` 即可。label 永遠由 SDK 的 `events_schema` 提供。如何配置 label／fields，以及如何在 `stage.finish["fields"]` 顯示欄位，是下一章 [配置 workflow 的畫面事件](configure-workflow-events.md) 的單一主題。

## 相關文件

- [工作流程](../workflow/index.md)
- [模組家族](../modules/index.md)
