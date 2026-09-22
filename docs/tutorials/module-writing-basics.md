# 五大模組的共同寫法

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/07-from-playground-to-code.ipynb)

這份教材說明如何用 Python 撰寫可放進工作流程的模組。五大模組都遵循同一個基本寫法：物件提供 `name`，以 `__call__(state)` 接收目前狀態，完成後回傳 `ModuleOutput`。

## 涵蓋內容

- 看懂模組共同的最小寫法。
- 分辨 `WorkflowState`、`ModuleOutput`、`payload` 與 `context_updates` 各自保存的資料。
- 知道只有規劃模組回傳的 `next_module` 會決定下一個步驟，其他模組做完一律交回規劃模組，行動做完這次執行結束。
- 知道做不到的時候只要把例外丟出來，剩下的由工作流程負責。
- 用一個小型回覆步驟確認模組是否能放入工作流程。

## 做不到的時候把例外丟出來

模組不必自己處理失敗。做不到它的工作時把例外丟出來就好，工作流程會接住，把它記成一筆帶 `is_error` 的紀錄、附上例外的型別與訊息、在推論訊息上說出是哪一個模組失敗的，然後照原本的路由往下走——感知、查找與反思交回規劃模組，行動結束這次執行。理由見 [ADR-0010](../adr/0010-the-workflow-catches-every-module-failure.md)。

所以模組裡不要寫「捕捉例外然後回一個看起來正常的 `ModuleOutput`」。那會讓規劃模組以為這一步成功了。

有兩個例外不要攔：`WorkflowInterrupted` 是有人請它停下來，`WorkflowAborted` 是工作流程自我保護，兩者都不是模組做不到它的工作，攔下來會把它們記成錯誤。

## 會跑很久的模組要看得懂停止訊號

`WorkflowState` 上有 `cancel`（一個 `CancellationToken` 或 `None`）與 `should_stop()`。工作流會在模組之間檢查，但**一個模組內部跑很久就必須自己看**——否則有人請它停下來時，它會把整件事做完才發現。

會逐步把內容送給使用者的模組，另外用 `state.report_delivered(...)` 說明實際交付了多少。透過 `emit_token_delta` 送出的內容會自動累積，所以只有「交付方式不是 delta」的模組才需要自己回報。

有些模組把內容交出去的當下還不知道對方收到多少——例如把整段話交給別處播放。這種模組回報時多給一個 `cut_short`：一個函式，收到中斷自述的內容（例如聽了幾秒），回傳其中實際到達的部分。工作流程會在中斷真正落地時才呼叫它，核心本身不做這個換算。

## 相關文件

- [工作流程](../workflow/index.md)
- [模組家族](../modules/index.md)