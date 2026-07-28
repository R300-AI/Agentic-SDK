# Plan

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。這一頁先把 Plan 家族的核心責任收斂成「交出下一節點決策」，再用單一標準名 `NextStepPlan` 來承接這個角色。每個模組會先列出建立物件時使用的初始化參數；規劃過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解。

透過 `WorkflowConfig` / `ModuleSpec.params` 建立 Plan 模組時，SDK 只接受本頁列出的初始化參數。個案名稱或 UI 顯示標籤不應透過初始化參數注入 planner。

## NextStepPlan

`NextStepPlan` 根據感知摘要、完整對話歷史與已有上下文，決定下一步要查資料還是直接回答。閱讀這個模組時，可以把它理解成一個明確的路由點：先看它讀進哪些線索，再看它交出哪些決策欄位給後續節點使用。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。不同 Plan 模組可以與 Perceive 或 Action 使用不同模型。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱。 |
| `system_prompt` | `string|null` | 否 | `null` | 覆寫 planner 系統提示；未提供時由 SDK 根據 retrieve 描述產生預設 prompt。 |
| `retrieve_description` | `string|null` | 否 | `null` | 取回節點用途說明，會被放入預設 planner prompt；不應放入個案名稱或展示用標籤。 |