# 配置 workflow 的畫面事件

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/03-configure-workflow-events.ipynb)

這份教材說明如何用 `events_schema` 把 workflow 的觀測資料變成穩定的畫面契約。

## 你會學到

- 未傳 `events_schema` 時，SDK 會傳送所有標準 stage、LLM token delta，以及 Perceive、Plan、Reflect 的完整結構化欄位。
- 傳入 schema 時，只有列出的 module 會送出 stage event；`fields` 只送出指定的 dot path，`"*"` 代表所有完整 JSON 值。
- `label` 是 SDK 送給畫面的階段文字，畫面直接使用 `event["label"]`，不另建 module-to-label mapping。
- `structured_field` 只在 value 已是完整 JSON 時送出；它是狀態摘要的顯示契約，不應用來顯示 chain-of-thought。

## 相關文件

- [工作流程事件](../workflow/index.md)
- [讓畫面知道 Agent 跑到哪一步](watch-a-workflow-run.md)
