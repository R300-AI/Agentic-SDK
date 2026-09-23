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

記憶交出去的內容裡，第一則系統訊息除了模組自己的系統提示，還帶著 `remembered_topics`——所有主題各自那一句話。它讓規劃知道有哪些主題可以查，因此永遠不會被預算裁掉：切掉它等於讓規劃看不見那些主題，也就等於沒有那份記憶。

## 在組裝設定裡宣告

記憶是 `WorkflowConfig` 自己的一個欄位，不在 `modules` 那本字典裡——那本字典是走訪會經過的五格，而記憶是每一格讀寫的那個東西。形狀和模組一樣是種類加參數：

```python
WorkflowConfig(memory=MemorySpec(kind="cross_context", params={"root": "/var/lib/agent-memory"}))
```

種類只有 `in_context` 與 `cross_context`，命名的是記憶型態而不是後端，所以換掉後端不必改已經存下來的設定。`cross_context` 給了 `root` 就寫在那裡，沒給就留在行程的記憶體裡——後者跨得了對話、跨不了重啟。其餘可給的參數是合成用的 `api_key`、`base_url`、`model`、`compaction_threshold_tokens` 與 `raw_retention_seconds`；給了別的會被連名字一起退回。理由見 [ADR-0017](../adr/0017-the-memory-is-declared-not-walked-to.md)。

Playground 的 Q1 問的是型態與要不要合成，記憶根目錄讀環境變數 `PLAYGROUND_MEMORY_ROOT`，合成用的端點由部署在審閱頁綁——兩者都是機器的性質，不存進 Agent 的設定。

**記錯的主題可以刪掉。** `remembered_topics()` 讀得出這條流程記住的每一則，`forget_topic(entry_id)` 刪掉其中一則並把合成它的那幾筆原始紀錄標記為排除，下次合成略過它們，所以那一則不會自己長回來。原始紀錄本身留著，仍然搜尋得到——被刪掉的是記憶做出的一個判斷，不是發生過的事。不提供編輯，理由見 [ADR-0019](../adr/0019-a-topic-can-be-struck-out-but-not-rewritten.md)。Playground 在承接前文的 Agent 上有一個「記憶內容」面板走同一條路。

**跨對話跨的是同一個人的對話。** 每一筆記憶帶著 `user_id`，`Workflow.run()` 與 `stream()` 收它。搜尋、索引與合成都只看得到擁有者相同的那些——兩個各自被識別的人讀不到對方的，沒有身分的執行讀不到被識別的人的、寫的也不會流到那個人那裡。什麼身分都不給時（直接用 SDK 的程式）擁有者是 `None`，它寫的都是它自己的，和以前一樣。理由見 [ADR-0020](../adr/0020-a-memory-belongs-to-the-person-it-was-built-from.md)。

Playground 這一端：登入的用 AI Hub 帳號，匿名試用每個瀏覽器發一個自己的識別碼——換一個瀏覽器要重來，但不會把前一個訪客的記憶交給下一個。

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