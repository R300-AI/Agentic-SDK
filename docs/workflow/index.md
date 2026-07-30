# 工作流程

`Workflow` 是 Agentic SDK 的公開組裝入口。它負責把可用節點接成一條可執行流程，並在執行期間承接節點之間的狀態流轉。單次執行實際會走到哪些節點，取決於各節點回傳的 `next_module`。

這一頁先說明 `Workflow` 的公開組裝方式、執行時如何保存中間資料，以及一條流程在執行期間如何推進。

## 公開組裝模型

!!! info "公開契約"
    所有需要模型的節點，一律以 OpenAI SDK 相容介面接入。

```python
Workflow(
    workflow_name="...",
    description="...",
    stage_labels={
        "perceive": "正在理解你的問題",
        "retrieve": "正在查找參考資料",
        "action": "正在準備回覆",
    },
    perceive=...,
    plan=...,
    retrieve=...,
    action=...,
    reflect=...,
)
```

`workflow_name` 用來標示這條流程的公開名稱；未顯式指定時，SDK 與 Playground 都使用 `default`。`description` 是流程說明文字，會保存在 `Workflow` 與 `WorkflowState` 上，供應用層或自訂模組使用。`stage_labels` 是工作流階段提示文字，供 Chat WebUI、Playground Runner 或其他前端在最終文字輸出前顯示「目前正在哪個模組執行」。`Workflow` 建立完成後，未顯式指定的節點會由內建預設實作補上；本次執行會走到哪些節點，取決於前一節點回傳的 `next_module`。

執行期間有四層資料分工：

- `MemoryStore`：模組可讀的共同 memory 抽象。
- `InContextMemory` / `PersistentMemory`：同層、可互換的 memory 類型；前者偏重對話承接，後者偏重持久化與回查。
- `WorkflowState`：本次 run 的執行狀態，持有 `entities`、`entries`、`visit_counts`、`attachments` 與 `memory`。
- `Entities`：節點間交換的結構化中繼結果，例如 `perceived_intent`、`retrieved_snippet`、`latest_final_message`。

下圖整理目前文件站採用的 workflow 執行模型：

![Framework](../assets/framework.png)

圖 1：workflow 在單次執行期間的推進方式。

## 執行狀態

`Workflow` 執行時會持續更新共用狀態，讓後續節點可以讀取前一步留下的結果。這份狀態由 `WorkflowState` 與某個 `MemoryStore` 實作共同承接：

- `WorkflowState` 承接本次 run 的中繼結果與觀測資料。
- `InContextMemory` 或 `PersistentMemory` 承接跨 turn 的完整對話歷史。

這樣的設計讓模型模組可以穩定讀到完整前文，也讓規則式模組專注處理本次 `run()` 的輸入資料與脈絡條目。

## 執行流程

一條 workflow 啟動後，會從起始節點開始執行。每個節點都會讀取目前的 `WorkflowState`，完成自己的處理，再回傳包含 `next_module` 的 `ModuleOutput`。`Workflow` 會根據這個結果決定下一個要執行的節點，直到某個節點回傳結束條件為止。

這種設計讓節點在執行期間決定下一步要交給誰。同一個 `Workflow` 物件因此可以支援不同長度、不同分支的執行路徑。

## 階段事件

如果呼叫 `run()` 時傳入 `event_callback`，`Workflow` 會在每個模組開始、完成或中止時送出事件。MVP UI 最常用的是開始事件：

```python
def on_event(event):
    if event.get("type") == "stage" and event.get("status") == "running":
        show_status(event["label"])

result = workflow.run("請介紹 SDK", event_callback=on_event)
```

事件保留既有的 `phase`、`module`、`state`、`visit_count` 等欄位，也會額外提供前端更容易使用的欄位：

```python
{
    "type": "stage",
    "phase": "start",
    "status": "running",
    "stage": "retrieve",
    "label": "正在查找參考資料",
    "module": "retrieve",
    "module_class": "KeywordRetrieve",
    "workflow_name": "WebUI 階段提示 Agent",
    "workflow_id": "...",
    "session_id": "...",
    "visit_count": 1,
}
```

這不是完整 tracing 規格；它是給 MVP Chat WebUI 使用的輕量階段提示。若要做除錯、成本分析或跨服務追蹤，可以在這個 callback 之上另外接 OpenTelemetry、LangSmith 或自訂 exporter。

## README 流程對應

README 裡的幾個範例，實際上都是在示範同一個公開組裝模型可以如何替換節點組合：你可以保留預設實作，也可以只替換其中一個節點，或另外注入自訂節點物件。對 `Workflow` 來說，這些差異都會回到同一套執行規則，也就是讀取 `WorkflowState`、必要時補進最新 user turn、執行目前節點、根據 `next_module` 推進下一步，最後把 assistant turn 追加回當前的 `MemoryStore` 實作。

如果你要進一步看 workflow 執行時由哪一層承接這份狀態，下一步應該看 [記憶類型](memory-types.md)。

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

`input_fields`、`input_images`、`response_schema`、`final_data` 這類欄位由各節點自己的輸入輸出規格定義。核心 `Entities` 保存跨節點共享的中間資料；完整對話 turn 歷史由當前的 `MemoryStore` 實作保存。

## 文件站閱讀路徑

| 你現在要做的事 | 先看哪一頁 | 再看哪一頁 |
| --- | --- | --- |
| 理解 workflow 怎麼組 | 工作流程 | [記憶類型](memory-types.md) |
| 理解 workflow 預設使用哪種記憶體 | [記憶類型](memory-types.md) | [模組家族](../modules/index.md) |
| 直接找某一類模組規格 | [模組家族](../modules/index.md) | 對應的功能模組頁 |

下一步建議先看 [記憶類型](memory-types.md)，再回到 [模組家族](../modules/index.md) 與各功能模組頁查節點規格。