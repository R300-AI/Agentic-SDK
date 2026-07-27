# Workflow 引擎選項

這一頁說明 `Workflow` 執行時依賴的引擎層。對外文件的正確分層是：`Workflow` 負責串接節點，也負責決定執行過程要使用哪個引擎承接狀態、累積上下文與提供 recall 能力。

## 預設引擎：InContextMemory

在這套文件站裡，`InContextMemory` 是 `Workflow` 的預設引擎。也就是說，當你沒有另外指定其他引擎時，workflow 會用 `InContextMemory` 承接單次執行期間需要保存的輸入、中繼結果與暫時狀態。

適合把它理解成：

- workflow 本輪執行的預設引擎
- 節點之間共享狀態的預設承接層
- 沒有額外外部存儲時，workflow 內建的執行引擎

這一層通常承接的資料，會對應到文件裡定義的 `Entities` 物件。重點不是逐一記欄位名稱，而是理解 `InContextMemory` 會在單次執行期間持續保存 workflow 的中間狀態，讓後續節點可以從同一份執行記憶繼續往下推進。

這些資料應被理解成預設 workflow 引擎內承接的狀態，而不是另外脫離 workflow、再獨立定一套不同名稱的 memory 契約。

## Preview 引擎：PersistentMemory

`PersistentMemory` 是文件先行定義的 durable memory engine。它不是單次執行期的工作記憶，而是跨執行期可保存、可索引、可回查的記憶引擎，用來承接之後仍可能被 workflow 重新取回與再利用的記憶資料。

適合把它理解成：

- workflow 結束後仍可保留的 durable memory
- 可供後續執行再次索引與回查的 recall engine
- 不再侷限於單輪狀態，而是可持續累積的外部記憶層

這一層對外先定義的是技術性質，而不是應用用途。也就是說，文件目前只先確立 `PersistentMemory` 代表「跨執行期可保存、可索引、可回查」這種記憶引擎類型；至於實際使用哪種 backend、索引方式或治理策略，仍屬後續 implementation slice 的範圍。

## Workflow 可注入的其他引擎層

從目前程式結構看，`Workflow` 本身保留了引擎注入點，至少包含下列兩個方向：

| 引擎位置 | 目前程式對應 | 角色 |
| --- | --- | --- |
| active context engine | `ActiveStore` | 保存本輪或近期可直接取用的上下文條目 |
| recall / memory engine | `MemoryStore` | 保存跨 run 可回查的記憶流，供後續 workflow 再利用 |

因此這套文件站把 `memory` 視為 workflow engine layer 的一部分，而不是跟 `Workflow` 平行的一張契約頁。

## 什麼時候看這一頁

- 當你要理解 workflow 預設是用哪個引擎來承接狀態
- 當你要判斷是否維持預設 `InContextMemory`
- 當你要替 workflow 注入 `ActiveStore` 或 `MemoryStore` 這類外部引擎
- 當你要分清楚「workflow 節點規格」與「workflow 執行引擎」是兩個不同層次

## 與模組頁的分工

模組頁負責回答每個節點做什麼，以及 workflow 邊界上有哪些模組化差異。

這一頁負責回答 `Workflow` 在執行時預設使用哪個引擎，以及 `Entities` 這類中間狀態是由哪一層引擎承接。

如果你現在要先理解 workflow 如何組裝，先看 [Workflow Overview](workflow-overview.md)。如果你接下來要看節點層的規格，再進 [Module Family](modules/index.md) 與對應模組頁。