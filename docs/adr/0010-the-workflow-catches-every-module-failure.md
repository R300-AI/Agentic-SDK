# 10. 失敗由流程層統一接住

Date: 2026-09-22

## Status

Accepted

## Context

同一件事——某一個模組做不到它的工作——原本有三種結果，取決於使用者在那個位置選了哪一個模組。

**`TextPerceive` 與 `NextStepPlan` 自己結束整輪。** 兩者各有一份 `_abort_for_provider_failure`，捕捉 provider 例外、寫 `last_workflow_error` 與一筆 `metadata["ok"] = False` 的 entry，然後 `raise WorkflowAborted`。呼叫端拿到的 `final_message` 是 `[workflow ended with error] ...`。

**`GenerativeAction` 與 `ToolCallAction` 自己吞下。** 兩者寫 `last_action_error` 與一筆同樣帶 `ok: False` 的 entry，回覆的內容說它失敗了，流程照走到結束。

**Retrieve 與 Reflect 的所有模組沒有任何處理。** 例外直接穿出 `run()`，呼叫端拿到 traceback。第三方自己寫的模組落在這一類——沒有約定可循，而 `docs/tutorials/module-writing-basics.md` 對失敗一個字也沒寫。

場域使用者看到的是同一件事：這個 agent 壞了。正在講話的人得到的是中斷，不是一句交代。

還有一個前提決定了不能怎麼做：目標端點是晶片上的小模型，demo 預設 `llama3.2:1b`。把錯誤原文交回去讓模型自己修不會成功，它會再錯一次，然後撞上限。

考慮過並否決的做法：

- **每個模組各自 try/except。** 就是現況，三種結果並存，而且第三方模組沒有約定可循。
- **只在推論服務那一層重試。** 只涵蓋會呼叫模型的模組，Retrieve 讀不到索引、Perceive 轉寫失敗都漏掉。
- **把錯誤原文包成觀察交回模型自己修。** 那是 Anthropic 的做法，前提是一個推得動的模型；這裡的端點推不動。
- **新增一個失敗專屬的 `ContextEntryType`。** 那會丟掉「是哪一個模組失敗」這個資訊，規劃還得再翻 metadata 才知道。
- **新增失敗次數上限。** 兩家標竿都沒有把失敗當獨立的計數對象，整輪的保護是預算。

## Decision

**接住的位置是 `Workflow` 呼叫模組的那唯一一行**，就在 `Gates` 檢查的下一行。五類模組與任何第三方模組都涵蓋，模組從此不必知道失敗這件事——那兩份 `_abort_for_provider_failure` 一併移除。`WorkflowInterrupted` 與 `WorkflowAborted` 照原樣往上傳：一個是人在操控，一個是流程自我保護，兩者都不是模組做不到它的工作。

**失敗不改變路由，只改變記錄。** 感知、查找與反思失敗之後照樣交回規劃，行動失敗之後照樣結束這一輪——那是 ADR-0005 定下的路由，這份決議不動它。改變的是失敗被寫到 context 上讓規劃讀，而不是由模組從內部結束整輪。規劃自己失敗是唯一沒有去處的情況：沒有別的模組可以問，所以那一輪結束，維持既有的 `WorkflowAborted` 路徑。

**那一筆 context entry 的四個性質各有理由：**

- **型別是那個模組原本會寫的型別**（`PERCEIVED`、`PLAN_DECISION`、`RETRIEVED`、`ACTION_RESULT`、`REFLECTION`），規劃因此看得出是誰缺了結果。
- **一級欄位 `is_error` 標記它**，不放進 `metadata` 那個自由字典。讀它不該依賴哪個模組怎麼拼那個鍵，而 `ok: False` 正是一個沒有東西保證會被填的約定。自己捕捉失敗的 `GenerativeAction` 與 `ToolCallAction` 也一併設上這個欄位，否則最常見的那種失敗反而標不到。`metadata["ok"]` 同時留著，因為 Playground 的推論訊息一直讀它。
- **`content` 是給人看的一句話**，五句集中在 `agentic_sdk/defaults.py`，和這個 repo 其餘使用者可見的預設字串放在一起。例外的型別與訊息進 `metadata`，那是給開發者的。
- **事件流用既有的階段事件**，`phase=finish` 配 `status=error`——那個模組確實跑完了，只是跑壞了。規劃自己失敗時不發這個事件，中止事件已經說了同一件事，發兩次會讀成兩個故障。

**失敗過的那個模組仍留在規劃的選項裡**，循環由既有的 `max_revisit` 擋，不新增失敗次數上限。

## Consequences

感知的 provider 失敗從「整輪結束並回一句錯誤」變成「交回規劃決定」。使用者拿到的是一個答案而不是一句道歉。這是破壞性變更，`tests/test_workflow_failure_contract.py` 原本斷言的 `aborted is True` 只剩規劃自己失敗時成立。

行動失敗的結果和原本的 `GenerativeAction` 一致——那一輪結束，交付的是那句中性訊息。所以一個連不上的端點不會被重打五次，正在講話的人也不會拿到空白。

`except Exception` 接住的範圍比「模組失敗」寬。`event_callback` 與 token delta 的回呼是在模組內部被呼叫的，所以**呼叫端自己的回呼出錯會被記成模組失敗**；同理，模組裡一個普通的 `TypeError` 也會變成一句道歉而不是一個 traceback。依失敗種類分流留給另一份工單，在那之前這是已知的代價。

`ContextEntry.is_error` 與 `metadata["ok"]` 兩個標記並存。前者是要讀的那一個，後者留給既有的推論訊息，兩者尚未收攏成一套。

「帶錯誤標記的紀錄不進記憶」這一條目前沒有落地的地方：`run()` 只把交付給使用者的那一則寫進記憶，沒有任何路徑把 context entry 寫進去。等記憶層開始保存逐輪紀錄時，那個守衛要放在寫入的那一側——而且要放兩處，因為中性訊息會以交付內容的身分進入記憶。

`docs/tutorials/module-writing-basics.md` 仍然沒有寫失敗。現在第三方模組的約定是「把例外丟出來就好」，那句話還沒有寫進那一頁。
