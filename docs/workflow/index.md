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
    events_schema={
        "perceive": {
            "label": "理解輸入",
            "fields": ["summary", "details.next_step"],
        },
        "plan": {
            "label": "判斷工具順序",
            "fields": ["thought", "next_module"],
        },
        "retrieve": {"label": "整理相關來源"},
        "action": {"label": "準備輸出回覆"},
    },
    perceive=...,
    plan=...,
    retrieve=...,
    action=...,
    reflect=...,
)
```

`workflow_name` 用來標示這條流程的公開名稱；未顯式指定時，SDK 與 Playground 都使用 `default`。`description` 是流程說明文字，會保存在 `Workflow` 與 `WorkflowState` 上，供應用層或自訂模組使用。省略 `events_schema` 時，SDK 預設完整送出事件：每個執行到的 module 都會送出 start、finish、abort stage event，標準 label 分別是 Perceive「理解輸入」、Plan「判斷工具順序」、Retrieve「整理相關來源」、Action「準備輸出回覆」、Reflect「檢查回覆」；所有 LLM token delta 與結構化 JSON 欄位（含巢狀值）也會送出。傳入 `events_schema` 是明確覆寫／限制：只有列出的 module 送出 stage event，`fields` 只送出明確 dot path 的完整 JSON value；`"*"` 可明確要求全部欄位。`Workflow` 建立完成後，未顯式指定的節點會由內建預設實作補上；本次執行會走到哪些節點，取決於前一節點回傳的 `next_module`。`events_schema` 是唯一的事件設定入口。

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

## 執行事件

如果呼叫 `run()` 或 `stream()` 時傳入 `event_callback`，省略 `events_schema` 的 `Workflow` 會對所有執行到的模組，在開始、完成或中止時送出 `stage` event，並送出完整的結構化 JSON 欄位。自訂 `events_schema` 時，則只對列出的模組與 `fields` 送出事件。MVP UI 可在開始時顯示 label，並在完成時直接讀取 SDK 依 schema 彙整的 fields：

```python
def on_event(event):
    if event["type"] == "stage" and event["phase"] == "start":
        show_status(event["label"])
    elif event["type"] == "stage" and event["phase"] == "finish":
        for item in event["fields"]:
            show_process_detail(event["label"], item["field"], item["value"])

result = workflow.run("請介紹 SDK", event_callback=on_event)
```

事件保留既有的 `phase`、`module`、`state`、`visit_count` 等欄位，也會額外提供前端更容易使用的欄位：

```python
{
    "type": "stage",
    "phase": "start",
    "status": "running",
    "stage": "retrieve",
    "label": "整理相關來源",
    "module": "retrieve",
    "module_class": "KeywordRetrieve",
    "workflow_name": "WebUI 階段提示 Agent",
    "workflow_id": "...",
    "session_id": "...",
    "visit_count": 1,
}
```

`structured_field` 的 `value` 是完整 JSON scalar、object 或 array，不是 token fragment，且每個 module visit 與欄位只會發送一次。對需要「節點完成後才顯示」的 UI，`stage.finish["fields"]` 是 SDK 依 schema 彙整的 list，格式為 `[{"field": "...", "value": ...}]`：明確列出的 field 依 `events_schema.fields` 順序排列；`"*"` 則列出該次實際完成的所有 path。需要最小化觀測面時，請用自訂 `events_schema.fields` 明確列出要給使用者或 UI 顯示的摘要與決策欄位；不要把模型的隱藏推理或未經審核的任意文字當作觀測欄位。這不是完整 tracing 規格；它是給 MVP Chat WebUI 使用的輕量階段提示。前端應顯示 SDK 事件提供的 `label`，不要另外硬編模組名稱與畫面文字；Playground 會把這些事件轉換成 NDJSON process event。若要做除錯、成本分析或跨服務追蹤，可以在這個 callback 之上另外接 OpenTelemetry、LangSmith 或自訂 exporter。

## 直接串流 Action 回覆

`Workflow.stream(...) -> WorkflowStream` 提供只含使用者可見 Action text 的 iterator；它不會將 Perceive、Plan 或 Reflect 的結構化 JSON yield 給 iterator。可串流的 Action 會即時產生 token，非串流 Action 則會在完成時產生一次最終文字。其參數與 `run()` 相同，包含可選的 `event_callback`；該 callback 仍會收到相同的 stage、token_delta 與 structured_field events。callback 存在時，iterator 預設不再 yield Action token，避免兩條輸出通道重複渲染；以 `yield_action_deltas=True` 可顯式開啟雙通道。

```python
def on_event(event):
    if event["type"] == "stage" and event["phase"] == "start":
        print(f"\n【{event['module']}】{event['label']}")


stream = workflow.stream("請介紹 SDK", event_callback=on_event)
for delta in stream:
    print(delta, end="", flush=True)

result = stream.result
```

`WorkflowStream.result` 只會在 iterator 耗盡後提供 `WorkflowResult`。未由 workflow 或模組處理的例外會在已排入的 token 都輸出後由 iterator 重新拋出；Action 模組自行轉換成結果的錯誤，則與 `run()` 一樣保存在最終結果中。

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