# 五大模組的共同寫法

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/07-from-playground-to-code.ipynb)

這份教材說明如何用 Python 撰寫可放進工作流程的模組。五大模組都遵循同一個基本寫法：物件提供 `name`，以 `__call__(state)` 接收目前狀態，完成後回傳 `ModuleOutput`。

## 涵蓋內容

- 看懂模組共同的最小寫法。
- 分辨 `WorkflowState`、`ModuleOutput`、`payload` 與 `context_updates` 各自保存的資料。
- 知道只有規劃模組回傳的 `next_module` 會決定下一個步驟，其他模組做完一律交回規劃模組，行動做完這次執行結束。
- 用一個小型回覆步驟確認模組是否能放入工作流程。

## 會跑很久的模組要看得懂停止訊號

`WorkflowState` 上有 `cancel`（一個 `CancellationToken` 或 `None`）與 `should_stop()`。工作流會在模組之間檢查，但**一個模組內部跑很久就必須自己看**——否則有人請它停下來時，它會把整件事做完才發現。

會逐步把內容送給使用者的模組，另外用 `state.report_delivered(...)` 說明實際交付了多少。透過 `emit_token_delta` 送出的內容會自動累積，所以只有「交付方式不是 delta」的模組才需要自己回報。

## 相關文件

- [工作流程](../workflow/index.md)
- [模組家族](../modules/index.md)