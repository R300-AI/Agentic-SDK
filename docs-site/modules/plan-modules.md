# Plan

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。文件標準名將這個家族統一寫成 `NextStepPlan`，用來強調它交出的核心結果是下一節點決策，而不是論文策略名稱。

## NextStepPlan

舊名對應：`ReActPlan`

`NextStepPlan` 根據感知摘要與已有上下文，決定下一步要查資料還是直接回答。文件上的 MVP 邊界先只處理單輪決策，因此標準輸出固定只交出 `next_node`、`retrieve_query` 與 `plan_reason`。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `perceive_query` | `string` | `"推薦適合久站的鞋"` | 由 Perceive 交來的查詢字串。 |
| `perceive_label` | `string` | `"shoe_recommendation"` | 由 Perceive 交來的路由標籤。 |
| `perceive_summary` | `string` | `"使用者想找適合久站情境的鞋款推薦"` | 由 Perceive 交來的需求摘要。 |
| `retrieved_snippet` | `string` | `""` | 先前已查回的資料；第一次進入 Plan 時可為空字串。 |
| `retrieved_hit_count` | `integer` | `0` | 先前查回的命中數。 |

### 標準輸出參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `plan_mode` | `string` | `"single_step"` | 本輪規劃模式；MVP 固定為單步決策。 |
| `next_node` | `string` | `"retrieve"` | 只允許 `retrieve` 或 `action`。 |
| `retrieve_query` | `string` | `"久站 鞋款 推薦"` | 當 `next_node` 為 `retrieve` 時，交給檢索節點使用的查詢字串。 |
| `plan_reason` | `string` | `"需要先查鞋款條目再組成推薦"` | 說明本輪為何走這個分支。 |
| `plan_steps` | `array<string>` | `["查詢鞋款條目","整理推薦理由"]` | 這輪規劃的步驟摘要；沒有子步驟時固定 `[]`。 |

### 對應 use case

LaNew 鞋款推薦前的條目查找、BCI 歷史片段追查、ICOPE 追蹤記錄比對。