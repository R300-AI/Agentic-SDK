# Workflow 引擎選項

這一頁說明 `Workflow` 執行時依賴的引擎層。對外文件的正確分層是：`Workflow` 負責串接節點，`MemoryStore` 是上層 memory 抽象，`InContextMemory` 與 `PersistentMemory` 是同層、可互換的 memory 類型，`WorkflowState` 則承接本次 run 的中繼狀態。

## MemoryStore：共同 memory 抽象

`MemoryStore` 是模組層依賴的共同 memory 抽象。如果這個專案裡的 memory 都必須保有對話順序，那 conversation 就不是另一層額外抽象，而是 `MemoryStore` 共同核心的一部分。

模組只應依賴這個共同抽象，不應直接綁死在 `InContextMemory` 這個 concrete class。

## InContextMemory：對話工作記憶類型

`InContextMemory` 是 `MemoryStore` 的一種實作，偏重對話工作記憶。它保存同一個 session 中依時間排序的完整 turn 歷史，讓需要模型的模組可以直接讀取前文。

適合把它理解成：

- 本次與前次 turn 共同組成的對話工作記憶
- 所有需要模型的模組共用的 conversation input
- 可由 `Workflow(memory_type=InContextMemory)` 直接承接的 transcript

`InContextMemory` 不是 `WorkflowState` 的別名，也不是 `Entities` 的別名。它的責任只有一件事：保存完整對話順序。

## PersistentMemory：持久化記憶類型

`PersistentMemory` 也是 `MemoryStore` 的一種實作，和 `InContextMemory` 同層。它的差異不在於層級比較低，而在於記憶策略不同：通常更強調跨執行期保留、搜尋、索引、回查與長期累積。

## WorkflowState：本次 run 的執行狀態

`WorkflowState` 是節點在單次 `run()` 期間直接讀寫的狀態物件。它會持有：

- `memory`
- `entities`
- `entries`
- `visit_counts`
- `attachments`
- `last_action_result` 與 `last_action_error`

也就是說，`WorkflowState` 關心的是「這次 run 現在推進到哪裡」，不是「完整對話 transcript 長什麼樣」。新的模組契約應以 `memory` 為主。

## Workflow 可注入的其他引擎層

從目前程式結構看，`Workflow` 本身保留了下列幾個引擎注入點：

| 引擎位置 | 目前程式對應 | 角色 |
| --- | --- | --- |
| workflow memory type | `memory_type` | 決定 workflow 以哪一種 memory 類型承接同一個 `session_id` 的對話歷史 |
| module-facing memory abstraction | `MemoryStore` | 模組讀取完整對話與 turn 歷史時依賴的共同抽象 |
| conversation-oriented memory | `InContextMemory` | 偏重 session 內完整對話承接的 `MemoryStore` 實作 |
| durable memory | `PersistentMemory` | 偏重跨執行期保留、搜尋與回查的 `MemoryStore` 實作 |

因此這套文件站把 `InContextMemory` 與 `PersistentMemory` 視為同層 memory 類型，而不是上下層關係；真正的上層抽象是 `MemoryStore`。

## 什麼時候看這一頁

- 當你要理解 workflow 內到底哪一層保存完整對話
- 當你要判斷是否只用單輪 `run()`，還是要用 `memory_type=InContextMemory` 承接多輪對話
- 當你要替 workflow 指定特定 `MemoryStore` 類型，例如 `InContextMemory` 或 `PersistentMemory`
- 當你要分清楚「workflow 節點規格」與「workflow 執行引擎」是兩個不同層次

## 與模組頁的分工

模組頁負責回答每個節點做什麼，以及 workflow 邊界上有哪些模組化差異。

這一頁負責回答 `Workflow` 在執行時由哪一層提供共同 memory 抽象、哪兩種 memory 類型可以互換、以及哪一層保存本次 run 狀態。

如果你現在要先理解 workflow 如何組裝，先看 [Workflow Overview](workflow-overview.md)。如果你接下來要看節點層的規格，再進 [Module Family](modules/index.md) 與對應模組頁。