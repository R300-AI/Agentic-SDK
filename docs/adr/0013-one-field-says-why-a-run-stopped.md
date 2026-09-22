# 13. 一次執行為什麼停下來，用一個欄位說完

Date: 2026-09-22

## Status

Accepted

## Context

`WorkflowResult` 原本用三個欄位說同一件事：`aborted` 這個布林、`abort_reason` 這個字串、以及 `interrupted` 這個布林。呼叫端要說出「這一輪為什麼停」，得把三個讀在一起，而且它們可以互相矛盾——`aborted=False` 配一個非空的 `abort_reason` 沒有任何東西擋得住。

分辨得出來的也只有三種狀態：跑完、被打斷、流程自我中止。但流程自我中止的原因有五種，彼此對場域人員的意義完全不同：繞太多圈要改流程，逾時要換端點，而指向一個不存在的模組是設定打錯了。三者共用一個 `True`，差別只寫在一句給開發者看的字串裡。

兩家標竿在這件事上一致，而且形狀比這裡清楚：Anthropic 的 `stop_reason` 每一次回應都有值，正常結束是 `end_turn`，其餘 `max_tokens`、`stop_sequence`、`tool_use`、`pause_turn`、`refusal` 各自一個值——撞到長度上限和被安全機制擋下不共用一個值。

## Decision

**一個 `stop_reason` 欄位，每一次執行都有值，正常結束也有。** 三個舊欄位移除，不留相容別名——和這一版其他破壞性變更同一條規則。

**一種情況一個值。** 程式裡實際會停下來的情況有八種，不是六種：

| 值 | 什麼情況 |
| --- | --- |
| `end_turn` | 跑完了 |
| `interrupted` | 有人請它停下來 |
| `max_hops` | 在模組之間繞的次數超過上限 |
| `max_revisit` | 同一個模組重複的次數超過上限 |
| `timeout` | 花的時間超過上限 |
| `budget_exhausted` | 這一輪可用的內容量用完了 |
| `endpoint_unavailable` | 推論服務不回應 |
| `planning_failed` | 規劃自己失敗，沒有別的模組可以決定下一步 |
| `misconfigured` | 指向一個不存在的模組 |

工單當初列了六種。`endpoint_unavailable` 是後來拆開兩種失敗時加的（ADR-0015）；`planning_failed` 與 `misconfigured` 則是清點程式時才發現的——`planning_failed` 是 ADR-0010 那一版加進來的，`misconfigured` 一直都在。把它們折進某個上限值會違反工單自己定的原則（一種情況一個值），所以這裡照原則走，值比當初列的多兩個。

`budget_exhausted` 現在沒有任何東西會設它：預算屬於另一份工單。先定好這個值，是為了那份工單落地時不必再改一次公開契約；文件上標明它目前不會出現。

**這個集合是封閉的，而且真的被檢查。** `STOP_REASONS` 列出全部八個，`STOPPED_ITSELF` 是其中「流程自我中止」那六個。`WorkflowAborted` 建構時就驗證傳進來的值在後者之內——一個只寫在註解裡的封閉集合會慢慢變成開放的。`stop_reason` 沒有預設值可以省略，因為省略只會讓下一個丟出它的人被默默歸到某一類。

**「交付了多少」留著，而且刻意和停止原因分開。** `interrupt_payload` 說的是使用者實際收到多少，那和為什麼停是兩回事：跑完的執行和被打斷的執行都可能交付了全部或什麼都沒交付。

**撞到上限照樣把已經交付的內容交出去。** 上限的原始措辭（哪一個模組、第幾次）只留在事件流的中止事件上，那是寫給看推論訊息的人的；使用者拿到的是 agent 已經說出口的那一段。

## Consequences

這是破壞性變更。`WorkflowResult` 的三個欄位消失，`WorkflowAborted` 的第二個參數變成必填。全庫四十餘處引用跟著改，含 Playground、範例、教材 notebook 與測試。依這個 repo 的慣例，破壞性變更走發布流程記錄。

Playground 不再借用 SDK 的措辭。舊的做法是把 `abort_reason` 直接顯示出來，而那句話寫著模組名與上限數字——給讀推論訊息的人看的。現在 Playground 自己按 `stop_reason` 給一句場域人員讀得懂的話。

`STOPPED_ITSELF` 收攏了原本重複四次的同一個判斷。它是公開的，因為 Playground 要用；這也表示日後新增一個值時，那四個地方會自動跟著對。

測試裡原本斷言 `abort_reason` 那句完整措辭的，現在斷言的是 `max_revisit` 這個值。哪一個模組、第幾次，只在事件流上還驗得到——這一點是這次換來的代價。
