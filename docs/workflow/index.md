# 工作流程

`Workflow` 是 Agentic SDK 的公開組裝入口。它負責把可用節點接成一條可執行流程，並在執行期間承接節點之間的狀態流轉。單次執行實際會走到哪些節點，取決於規劃模組每一步的選擇。

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

`workflow_name` 用來標示這條流程的名稱；未指定時使用 `default`。`description` 是流程說明文字，會保存在 `Workflow` 與 `WorkflowState`，供呼叫端或自訂模組讀取。省略 `events_schema` 時，SDK 會送出每個實際執行步驟的開始、完成與中止事件，並提供模型輸出文字與完整結構化欄位。傳入 `events_schema` 後，可指定要觀察的步驟、中文名稱與欄位。`Workflow` 會為未指定的步驟補上內建實作；沒有指定 `plan` 時，規劃模組是不呼叫模型的 `PassThroughPlan`。每次執行實際經過哪些步驟，由規劃模組決定，規則見下方「執行流程」一節。

### 用程式直接建立

直接在 Python 程式裡建立 `Workflow`，適合流程結構固定、設定和應用程式一起維護的情況。需要的模組放進建構子，名稱、說明與事件設定寫在同一處。

### 用設定資料建立

流程選項要保存成 JSON、YAML 或資料庫資料時，先建立一份設定資料，再由 SDK 組成工作流程。`WorkflowConfig` 表示整條流程，`ModuleSpec` 表示其中一個步驟的種類與參數，`build_workflow()` 則依設定建立 `Workflow`。

```python
from agentic_sdk import GateConfig, ModuleSpec, WorkflowConfig, build_workflow

config = WorkflowConfig(
    name="保險接待人員",
    description="根據常見保單問題提供初步說明。",
    modules={
        "perceive": ModuleSpec(kind="pass_through"),
        "retrieve": ModuleSpec(
            kind="keyword",
            params={
                "items": [
                    {"keywords": ["理賠", "申請"], "content": "請先準備保單號碼與事故資料。"},
                ]
            },
        ),
        "action": ModuleSpec(kind="direct_answer"),
    },
)

workflow = build_workflow(config)
result = workflow.run("我要申請理賠，需要先準備什麼？")
print(result.final_message)
```

設定資料中的步驟種類使用固定名稱，SDK 會依名稱建立對應模組，並檢查參數是否適用。種類名稱包括 `pass_through`、`text`、`text_image`、`voice_text`、`pass_through_plan`、`next_step`、`keyword`、`pass_through_retrieve`、`semantic`、`direct_answer`、`generative`、`tool_call_action`、`voice_answer`、`plan_check` 與 `evidence_check`。語音的兩個種類以物件承載音訊來源：`voice_text` 收 `transport`，`voice_answer` 收 `speech`，與 `semantic` 收 `embedder` 的方式相同。程式直接建立與設定資料建立，最後都會得到相同的 `Workflow` 物件和執行方式。

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

每次執行都照同一條規則推進，規則由 `Workflow` 執行，依據是 [ADR 0005](https://github.com/R300-AI/Agentic-SDK/blob/main/docs/adr/0005-every-run-closes-the-loop-through-planning.md)：

| 做完的步驟 | 下一步 |
| --- | --- |
| 感知（Perceive） | 規劃 |
| 規劃（Plan） | 規劃模組選的檢索、反思或行動 |
| 檢索（Retrieve） | 規劃 |
| 反思（Reflect） | 規劃 |
| 行動（Action） | 結束這次執行 |

規劃模組是唯一選擇下一步的角色，其他模組回傳的 `next_module` 不影響路由。每次造訪規劃模組之前，`Workflow` 把這一次可以選的步驟寫進 `WorkflowState.plan_options`：檢索與行動一律可選，反思只在掛了反思模組時可選。規劃模組選了不在其中的步驟，下一步改為行動。

行動是一次執行的最後一步，行動出錯也一樣。行動造成的結果由下一輪的感知觀測，下一輪由使用者或呼叫端的程式啟動。

沒有指定規劃模組時，`PassThroughPlan` 依固定規則選擇：這次執行還沒檢索就檢索；掛了反思模組、且還沒反思就反思；其他情況行動。只有感知、檢索與行動的流程因此依序經過感知、規劃、檢索、規劃、行動。

## 執行上限

每次執行都有四項上限，讓流程能在合理時間內完成。`GateConfig` 用來調整這些數值；未設定時，SDK 使用預設值。

| 中文意義 | 設定欄位 | 預設值 | 作用 |
| --- | --- | --- | --- |
| 全部步驟次數 | `max_node_hops` | `50` | 一次執行最多經過的步驟數。 |
| 同一步驟重複次數 | `max_revisit` | `5` | 同一個步驟最多重複執行的次數。規劃模組與反思不計入。 |
| 最長執行時間 | `timeout_sec` | `300.0` | 一次執行可使用的最長秒數。 |
| 規劃與反思來回次數 | `max_reflect_rounds` | `5` | 一次執行最多送反思的次數。 |

達到前三項上限時，SDK 會結束本次執行，並在結果中提供中止原因。`max_reflect_rounds` 是唯一不中止執行的上限：達到後，反思從規劃模組的可選步驟中移除，執行照常往檢索或行動走。

規劃模組與反思不計入 `max_revisit`。反思的次數由 `max_reflect_rounds` 限制，調高它不需要同時調高 `max_revisit`；規劃模組在每次檢索與每次反思之後各被造訪一次，造訪次數等於 1 加檢索次數加反思次數，已經被另外兩項限制住。預設值下最長路徑是感知 1、檢索 5、反思 5、規劃 11、行動 1，共 23 步，低於 `max_node_hops` 的 50。一般應用程式可保留預設值；當流程有明確的外部等待或重試需求時，再依實際執行紀錄調整。

```python
config.gates = GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=120.0)
workflow = build_workflow(config)
```

## 執行參數

`run()` 與 `stream()` 接受同一組參數。兩者的差別在返回形式：`run()` 完成後返回 `WorkflowResult`，`stream()` 返回逐段產生 Action 文字的 iterator，完成後由 `stream.result` 取得同一份結果。

| 參數 | 型態 | 說明 |
| --- | --- | --- |
| `user_message` | `str \| None` | 這一輪的輸入。模組已透過 `pending_input()` 收取輸入時可省略。 |
| `memory` | `MemoryStore \| None` | 這一輪使用的對話記憶；省略時使用工作流自己持有的那一份。 |
| `memory_store` | `PersistentMemory \| None` | 跨 session 的持久化記憶。 |
| `session_id` | `str \| None` | 對話識別碼，寫入每一則回合。 |
| `workflow_id` | `str \| None` | 工作流識別碼，寫入每一則回合。 |
| `attachments` | `list \| None` | 這一輪的附件。 |
| `cancel` | `CancellationToken \| None` | 停止這一次執行的權杖，見下一節。 |
| `event_callback` | `Callable \| None` | 接收 stage、token_delta 與 structured_field 事件。 |
| `events_schema` | `dict \| None` | 覆寫事件的階段名稱與文案。 |
| `yield_action_deltas` | `bool \| None` | 僅 `stream()` 適用。提供 `event_callback` 時預設不再由 iterator 產生 Action token，避免兩條通道重複渲染；設為 `True` 則兩者同時輸出。 |

## 被打斷

執行上限是流程自我中止；**被打斷**是有人請它停下來，兩者不同，結果也分得開。

`run()` 與 `stream()` 都收一個 `cancel`。任何持有這個權杖的人——背景執行緒、另一條連線、正在聽的模組——都可以要求停止：

```python
from agentic_sdk.core.cancellation import CancellationToken

token = CancellationToken()
result = workflow.run("保固多久？", cancel=token)
```

| 欄位 | 中止（上限） | 被打斷 |
| --- | --- | --- |
| `result.aborted` | `True` | `False` |
| `result.abort_reason` | 中止原因 | `None` |
| `result.interrupted` | `False` | `True` |
| `result.interrupt_payload` | `{}` | 含 `reason` 與 `delivered` |

分開的理由是呈現：上限是流程保護自己，該顯示錯誤；被打斷是使用者在主導，**對一件他故意做的事顯示錯誤是荒謬的**。

### 這一輪記下的是已交付的內容

被打斷的那一輪，記憶留下的不是模型產出的內容，而是**實際到達使用者的內容**。有人在看串流輸出時，`emit_token_delta` 會在送出的當下累積；一段被中斷的文字回覆因此記下使用者已經讀到的那半句，而不是整段，也不是空的。

`result.interrupt_payload["delivered"]` 是同一份內容。這與音訊無關——螢幕會交付，喇叭也會，而核心不被允許知道是哪一種。

執行途中，模組可以從 `state.delivered_so_far` 讀到目前為止交付了多少，並用 `state.report_delivered(...)` 更正它。透過 `emit_token_delta` 送出的內容會自動累積，所以**只有交付方式不是 delta 的模組**才需要自己回報——例如一個把音訊交給喇叭的模組。

### 話還沒說出口就先問清楚

有些模組在工作流開始前就已經拿到這一輪的輸入。語音是最明顯的例子：話什麼時候來取決於人什麼時候想講，不是取決於呼叫端什麼時候呼叫 `run()`。

這種模組實作 `pending_input()`，回傳它已經收下、還沒用掉的輸入；`Workflow.run()` 因此不必再被告知一次：

```python
if perceive.pending_input():
    result = workflow.run()          # 不必再傳一次使用者說了什麼
```

這個約定**不是語音專屬**，任何模組都可以實作它——它承認的是「呼叫端不一定是最先知道這一輪要處理什麼的人」。收下的內容用掉就沒了，不會殘留到下一輪。

## 執行事件

如果呼叫 `run()` 或 `stream()` 時傳入 `event_callback`，省略 `events_schema` 的 `Workflow` 會對所有執行到的模組，在開始、完成或中止時送出 `stage` event，並送出完整的結構化 JSON 欄位。自訂 `events_schema` 時，則只對列出的模組與 `fields` 送出事件。呼叫端在開始時更新狀態，並在完成時讀取 SDK 依設定整理的欄位：

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
    "workflow_name": "執行狀態範例",
    "workflow_id": "...",
    "session_id": "...",
    "visit_count": 1,
}
```

`structured_field` 的 `value` 是完整 JSON 值，每個步驟與欄位各送出一次。`stage.finish["fields"]` 是 SDK 依設定整理的欄位清單，格式為 `[{"field": "...", "value": ...}]`；明確列出的欄位依 `events_schema.fields` 順序排列，`"*"` 則列出該步驟完成時取得的所有欄位。應用程式可選擇要顯示或記錄的摘要與決策欄位，並在 callback 上串接自己的除錯、成本分析或跨服務追蹤工具。

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

README 裡的幾個範例示範同一個公開組裝模型的三種替換方式：保留預設實作、只替換其中一個節點，或注入自訂節點物件。對 `Workflow` 來說，這些差異都會回到同一套執行規則，也就是讀取 `WorkflowState`、必要時補進最新 user turn、執行目前節點、根據 `next_module` 推進下一步，最後把 assistant turn 追加回當前的 `MemoryStore` 實作。

要進一步了解 workflow 執行時由哪一層承接這份狀態，下一步看 [記憶類型](memory-types.md)。

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

| 要做的事 | 先看哪一頁 | 再看哪一頁 |
| --- | --- | --- |
| 理解 workflow 怎麼組 | 工作流程 | [記憶類型](memory-types.md) |
| 理解 workflow 預設使用哪種記憶體 | [記憶類型](memory-types.md) | [模組家族](../modules/index.md) |
| 直接找某一類模組規格 | [模組家族](../modules/index.md) | 對應的功能模組頁 |

下一步建議先看 [記憶類型](memory-types.md)，再回到 [模組家族](../modules/index.md) 與各功能模組頁查節點規格。