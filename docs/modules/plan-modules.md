# Plan

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。每個流程都有一個規劃模組：感知、檢索與反思做完都交回它，由它在檢索、反思、行動之中選一個，行動之後這次執行結束。這一頁的 `PassThroughPlan` 用固定規則選擇，`NextStepPlan` 用模型選擇。每個模組會先列出建立物件時使用的初始化參數；規劃過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解。

透過 `WorkflowConfig` / `ModuleSpec.params` 建立 Plan 模組時，SDK 只接受本頁列出的初始化參數。個案名稱或 UI 顯示標籤不應透過初始化參數注入 planner。

規劃模組每次被造訪時，`state.plan_options` 列出這一次可以選的步驟。自訂規劃模組回傳不在其中的步驟時，`Workflow` 改走行動。

## PassThroughPlan

`PassThroughPlan` 不呼叫模型。`Workflow` 沒有指定 `plan` 時使用它。每次造訪依序判斷：

1. 這次執行還沒檢索過，選檢索。
2. 反思可選、且這次執行還沒反思過，選反思。
3. 其他情況，選行動。

每次造訪留下一筆 `plan_decision` 條目，metadata 的 `next_module` 是選擇的步驟，`strategy` 為 `pass_through`。

### 初始化參數

無。透過 `WorkflowConfig` 建立時，種類名稱是 `pass_through_plan`。

## NextStepPlan

參考論文：[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

`NextStepPlan` 根據感知摘要、完整對話歷史與已有上下文，決定下一步要查資料、先送反思，還是直接回答。閱讀這個模組時，可以把它理解成一個明確的路由點：先看它讀進哪些線索，再看它交出哪些決策欄位給後續節點使用。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。不同 Plan 模組可以與 Perceive 或 Action 使用不同模型。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱。 |
| `system_prompt` | `string|null` | 否 | `null` | 覆寫 planner 系統提示；未提供時由 SDK 根據 retrieve 描述產生預設 prompt。 |
| `retrieve_description` | `string|null` | 否 | `null` | 取回節點用途說明，會被放入 planner prompt；不應放入個案名稱或展示用標籤。傳入自訂 `system_prompt` 時仍然生效。 |
| `route_policy` | `callable|null` | 否 | `null` | 由呼叫方決定最終路由。收到 `(state, 模型選的模組)`，回傳要採用的模組；回傳模型的選擇即表示接受。SDK 不附預設政策——哪些問題需要查資料取決於題材，那是應用程式知道而通用 planner 不知道的事。 |