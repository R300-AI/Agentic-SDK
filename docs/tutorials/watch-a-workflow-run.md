# 讓畫面知道 Agent 跑到哪一步

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/02-watch-a-workflow-run.ipynb)

這份教材說明應用程式如何在最後回覆產生前，知道工作流程目前進行到哪一個步驟。SDK 會透過 `event_callback` 送出階段事件，應用程式可讀取事件裡的 `label` 更新狀態。

## 你會學到

- 不設定 `events_schema` 時，直接使用 SDK 的完整預設事件與標準 label。
- 用 `event_callback=on_event` 顯示 stage start event。
- 直接使用 SDK 提供的 `label`，不在 UI 自建 module-to-label mapping。
- 將事件內容接到你的狀態顯示、執行紀錄或監測程式。

## 直接使用標準事件

沒有傳入 `events_schema` 時，SDK 對所有實際執行的 module 發送 `stage` 事件，標準 label 是「理解輸入」、「判斷工具順序」、「整理相關來源」、「準備輸出回覆」、「檢查回覆」。

```python
workflow = Workflow(
    workflow_name='執行狀態範例',
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

應用程式收到 `type == "stage"` 且 `phase == "start"` 的事件時，可使用 `event["label"]` 顯示目前步驟。`label` 由 SDK 的 `events_schema` 提供。如何設定步驟名稱與欄位，以及如何讀取 `stage.finish["fields"]`，可接著閱讀 [設定工作流程的畫面事件](configure-workflow-events.md)。

## 相關文件

- [工作流程](../workflow/index.md)
- [模組家族](../modules/index.md)
