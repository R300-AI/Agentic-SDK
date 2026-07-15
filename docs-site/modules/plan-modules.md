# Plan Modules

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。現行程式碼中真正實作的 planner 只有 `ReActPlan` 一個類別；舊文件中的 Chain-of-Thought 與 Plan-and-Solve 不是獨立 class，而是同一個 planner 內部可切換的 prompt strategy。

## 已實作模組

| 模組 | 需要模型 | 可輸出下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `ReActPlan` | 是 | `retrieve` / `action` | 根據目前上下文決定先查詢還是直接回答 |

## ReActPlan

`ReActPlan` 是目前唯一的規劃節點實作，基礎策略對應 [Arxiv](https://arxiv.org/abs/2210.03629)；同一份 class 也內建了 Chain-of-Thought 風格提示 [Arxiv](https://arxiv.org/abs/2201.11903) 與 Plan-and-Solve 風格提示 [Arxiv](https://arxiv.org/abs/2305.04091) 的模板變體，但對外仍是一個 `ReActPlan` 模組。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | planner 使用的 LLM client。 |
| `system_prompt` | `str | None` | `None` | 若提供，直接覆蓋內建 planner prompt。 |
| `retrieve_description` | `str | None` | `None` | 未顯式提供 `system_prompt` 時，用來組出 retrieve index 描述。 |
| `retrieve_name` | `str | None` | `None` | 未顯式提供 `system_prompt` 時，用來組出 retrieve index 名稱。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | 使用者原始輸入，會直接放入 planner prompt。 |
| `perceived_intent` | `str` | `"general"` | 從最近一筆 `PERCEIVED` context 的 metadata 讀取；若不存在則退回 `general`。 |
| `has_retrieved_context` | `bool` | `False` | 由最近是否存在 `RETRIEVED` context 推導。 |
| `has_attachment` | `bool` | `False` | 由 `len(state.attachments) > 0` 推導。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"retrieve" | "action"` | planner 的路由決策；若 LLM 回傳非法值，會 fallback 成 `"action"`。 |
| `NodeOutput.payload.plan_thought` | `str` | planner 的推理摘要。 |
| `NodeOutput.payload.plan_subtasks` | `list[str]` | 若模型回傳 `subtasks`，會整理成字串陣列；否則為空陣列。 |
| `NodeOutput.payload._llm_usage` | `dict` | 包含 `model`、`input_tokens`、`output_tokens`。 |
| `NodeOutput.context_updates[0].type` | `"plan_decision"` | 追加一筆 `PLAN_DECISION` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `thought`、`next_node`、`fallback`、`llm`；若有 `subtasks` 也會一併保存。 |