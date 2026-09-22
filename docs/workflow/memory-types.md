# 記憶類型

這一頁說明 `Workflow` 執行時使用的引擎層。分工如下：`Workflow` 負責串接節點，`MemoryStore` 是上層記憶抽象，`InContextMemory` 與 `CrossContextMemory` 是同層、可互換的記憶類型，`WorkflowState` 承接本次 `run()` 的中繼狀態。

## MemoryStore：共同 memory 抽象

`MemoryStore` 是模組層依賴的共同記憶抽象。它負責保存模組需要讀取的對話內容與順序，讓不同記憶實作可以使用同一個介面。

模組依賴 `MemoryStore` 介面，就能在 `InContextMemory` 與 `CrossContextMemory` 之間切換。

## InContextMemory：對話工作記憶

`InContextMemory` 是 `MemoryStore` 的一種實作，偏重對話工作記憶。它保存同一段對話中依時間排序的完整 turn 歷史，讓需要模型的模組可以直接讀取前文。

適合把它理解成：

- 本次與前次 turn 共同組成的對話工作記憶
- 所有需要模型的模組共用的對話輸入
- 可建立成 `memory = InContextMemory()`，再由 `Workflow(memory_type=memory)` 直接使用的對話紀錄

`InContextMemory` 的責任是保存完整對話順序；`WorkflowState` 與 `Entities` 則處理單次 `run()` 期間的中繼資料。

## CrossContextMemory：跨對話記憶

`CrossContextMemory` 是 `MemoryStore` 的一個協定，和 `InContextMemory` 同層、由 `memory_type` 擇一。它偏重跨執行期保留、搜尋、索引、回查與長期累積。

目前有兩個實作：

- `FileMemoryStore` 把一則條目寫成一個 markdown 檔，目錄按流程的名字分，同一條流程的各段對話共用。建立時要給 `root`；`raw_retention_seconds` 不填就是永久保留。附件與 embedding 不寫進檔案——兩者都大、都不是人讀得懂的東西，原本有附件的條目會在 front matter 記下它有幾個。理由與部署注意事項見 [ADR-0011](../adr/0011-cross-context-memory-is-kept-as-files.md)。

  設了 `compaction_threshold_tokens` 之後，它會在要把內容交給模組之前把最舊的部分收成主題，收到用量回到門檻以下為止；被收走的原始紀錄留著、搜尋得到，主題補在它們原本的位置。合成要一組自己的 `api_key`、`base_url` 與 `model`——那是比回答容易的工作，可以指到更小的端點。不設門檻就完全不會發生。token 數是估的，要精確就傳一個 `count_tokens`。理由見 [ADR-0012](../adr/0012-the-memory-collects-its-own-oldest-parts.md)。
- `InMemoryStore` 把條目留在行程裡，跨得了對話但跨不了重啟，適合測試與不需要落地的程式。

**`turns` 只給這一段對話，跨對話要用 `search`。** 模組讀 `turns` 當前文，所以另一段對話的內容不會以前文的身分出現在提示詞裡；要取用先前那幾段留下來的東西走 `search`，它只按流程的名字過濾。

## WorkflowState：本次 run 的執行狀態

`WorkflowState` 是節點在單次 `run()` 期間直接讀寫的狀態物件。它會持有：

- `memory`
- `entities`
- `entries`
- `visit_counts`
- `attachments`
- `last_action_result` 與 `last_action_error`

`WorkflowState` 關心的是「這次 `run()` 目前推進到哪裡」。完整對話紀錄由 `memory` 承接，模組需要前文時應讀取 `memory`。

## 被打斷的回合記了什麼

助理回合記下的是**實際交付給使用者的內容**。一般情況下那就是完整回覆；被打斷時則是使用者已經收到的那一段，回合的 metadata 會標上 `interrupted`。

`MemoryStore` 沒有為此增加任何方法。交付在執行結束之前就確定的情況（文字串流、在傳輸迴圈裡播放的音訊），由工作流直接寫入正確內容；交付在執行之後才完成的情況（例如播放發生在瀏覽器），更正屬於**持有那份對話記錄的呼叫端**，各種記憶自行決定怎麼折進去。理由是記憶是擴充點：跨對話與階層式記憶都得能實作同一份協定，而「修訂過去的回合」不是每一種都做得到的事。詳見 ADR-0002。

## Workflow 可注入的其他引擎層

從目前程式結構看，`Workflow` 本身保留了下列幾個引擎注入點：

| 引擎位置 | 目前程式對應 | 角色 |
| --- | --- | --- |
| workflow memory type | `memory_type` | 決定 workflow 以哪一種 memory 策略或 memory 物件承接對話歷史；可用 `"in_context"`、`"cross_context"`、memory class 或 memory 物件 |
| module-facing memory abstraction | `MemoryStore` | 模組讀取完整對話與 turn 歷史時依賴的共同抽象 |
| conversation-oriented memory | `InContextMemory` | 偏重一段對話內完整承接的 `MemoryStore` 實作 |
| cross-context memory | `CrossContextMemory` | 偏重跨執行期保留、搜尋與回查的協定，實作為 `FileMemoryStore` 與 `InMemoryStore` |

這套文件站把 `MemoryStore` 視為共同抽象，`InContextMemory` 與 `CrossContextMemory` 則是同層記憶類型。

## 什麼時候看這一頁

- 要理解 workflow 內哪一層保存完整對話時
- 要判斷只用單輪 `run()`，或建立 `memory = InContextMemory()` 交給 `Workflow(memory_type=memory)` 承接多輪對話時
- 要替 workflow 指定特定 `MemoryStore` 類型或物件時，例如 `"in_context"`、`"cross_context"`、`InContextMemory` 或自訂 memory instance
- 要分清楚「workflow 節點規格」與「workflow 執行引擎」兩個層次時

## 與模組頁的分工

模組頁負責回答每個節點做什麼，以及 workflow 邊界上有哪些模組化差異。

這一頁負責回答 `Workflow` 在執行時由哪一層提供共同記憶抽象、哪兩種記憶類型可以互換、以及哪一層保存本次 `run()` 狀態。

要先理解 workflow 如何組裝，看 [工作流程](index.md)。要看節點層的規格，進 [模組家族](../modules/index.md) 與對應模組頁。