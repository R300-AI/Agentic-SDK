# 設定工作流程的畫面事件

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/03-configure-workflow-events.ipynb)

這份教材說明如何用 `events_schema` 決定工作流程要提供哪些執行資訊給應用程式。

## 你會學到

- 省略 `events_schema` 時，SDK 會提供所有標準步驟、模型文字片段與完整結構化欄位。
- 傳入設定後，SDK 會提供列出的步驟；`fields` 指定要提供的欄位，`"*"` 代表該步驟取得的全部完整 JSON 值。
- `label` 是 SDK 提供的步驟名稱，應用程式可直接使用 `event["label"]` 顯示狀態。
- `structured_field` 提供完整 JSON 值，適合顯示或記錄每個步驟完成後的摘要資料。

## 相關文件

- [工作流程事件](../workflow/index.md)
- [讓畫面知道 Agent 跑到哪一步](watch-a-workflow-run.md)
