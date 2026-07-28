# Workflow Overview

`Workflow` 是 Agentic SDK 的公開組裝入口。它負責把可用節點接成一條可執行流程，並在執行期間承接節點之間的狀態流轉。單次執行實際會走到哪些節點，取決於各節點回傳的 `next_module`。

這一頁先說明 `Workflow` 的公開組裝方式、執行時如何保存中間資料，以及一條 workflow 在 runtime 中如何被推進。

## 公開組裝模型

!!! info "公開契約"
    所有需要模型的節點，一律以 OpenAI SDK 相容介面接入。

```python
Workflow(
    workflow_name="...",
    description="...",
    perceive=...,
    plan=...,
    retrieve=...,
    action=...,
    reflect=...,
)
```

`workflow_name` 用來標示這條 workflow 的公開名稱；未顯式指定時，SDK 與 Playground 都使用 `default`。`description` 則是這條 workflow 的說明文字，會保存在 `Workflow` 與 `WorkflowState` 上供應用層或自訂模組使用。`Workflow` 建立完成後，未顯式指定的節點會由內建預設實作補上；但某個節點會不會真的在這次執行中被走到，仍取決於前一節點回傳的 `next_module`。

執行期間有四層資料分工：

- `MemoryStore`：模組可讀的共同 memory 抽象。
- `InContextMemory` / `PersistentMemory`：同層、可互換的 memory 類型；前者偏重對話承接，後者偏重持久化與回查。
- `WorkflowState`：本次 run 的執行狀態，持有 `entities`、`entries`、`visit_counts`、`attachments` 與 `memory`。
- `Entities`：節點間交換的結構化中繼結果，例如 `perceived_intent`、`retrieved_snippet`、`latest_final_message`。

下圖整理目前文件站採用的 workflow 執行模型：

![Framework](assets/framework.png)

圖 1：workflow 在單次執行期間的推進方式。

## 執行狀態

`Workflow` 執行時會持續更新一份共用狀態，讓後續節點可以讀取前一步留下的結果。這份共用狀態不是單一物件，而是 `WorkflowState` 與某個 `MemoryStore` 實作的合作：

- `WorkflowState` 承接本次 run 的中繼結果與觀測資料。
- `InContextMemory` 或 `PersistentMemory` 承接跨 turn 的完整對話歷史。

這樣的設計讓模型模組可以穩定讀到完整前文，同時也讓規則式模組只專注在本次 run 需要的 payload 與 context entries。

## 執行流程

一條 workflow 啟動後，會從起始節點開始執行。每個節點都會讀取目前的 `WorkflowState`，完成自己的處理，再回傳包含 `next_module` 的 `ModuleOutput`。`Workflow` 會根據這個結果決定下一個要執行的節點，直到某個節點回傳結束條件為止。

這種設計的重點不是把流程寫死，而是讓節點在 runtime 中決定接下來要把控制權交給誰。也因此，同一個 `Workflow` 物件可以支援不同長度、不同分支的執行路徑。

## README 流程對應

README 裡的幾個範例，實際上都是在示範同一個公開組裝模型可以如何替換節點組合：你可以保留預設實作，也可以只替換其中一個節點，或另外注入自訂節點物件。對 `Workflow` 來說，這些差異都會回到同一套執行規則，也就是讀取 `WorkflowState`、必要時補進最新 user turn、執行目前節點、根據 `next_module` 推進下一步，最後把 assistant turn 追加回當前的 `MemoryStore` 實作。

如果你要進一步看 workflow 執行時由哪一層承接這份狀態，下一步應該看 [Workflow 引擎選項](workflow-engines.md)。

## Entities

`Entities` 是 workflow 內部節點交換資料時使用的核心標準物件，用來描述 workflow 在單次執行期間會持續累積與更新的結構化中間資料。

```json
{
    "perceived_intent": "",
    "perceived_summary": "",
    "perceived_details": {},
    "plan_thought": "",
    "retrieved_items": [],
    "retrieved_snippet": "",
    "latest_retrieved_content": "",
    "latest_final_message": "",
    "latest_tool_calls": [],
    "reflect_verdict": ""
}
```

像是 `input_fields`、`input_images`、`response_schema`、`final_data` 這類欄位，仍可以存在各節點自己的輸入輸出規格裡；只是它們不屬於所有節點都必須共享的核心 `Entities`。完整對話 turn 歷史則不放在 `Entities`，而是放在當前的 `MemoryStore` 實作中。

## 文件站閱讀路徑

| 你現在要做的事 | 先看哪一頁 | 再看哪一頁 |
| --- | --- | --- |
| 理解 workflow 怎麼組 | Workflow Overview | [Workflow 引擎選項](workflow-engines.md) |
| 理解 workflow 預設使用哪個引擎 | [Workflow 引擎選項](workflow-engines.md) | [Module Family](modules/index.md) |
| 直接找某一類模組規格 | [Module Family](modules/index.md) | 對應的功能模組頁 |

下一步建議先看 [Workflow 引擎選項](workflow-engines.md)，再回到 [Module Family](modules/index.md) 與各功能模組頁查節點規格。