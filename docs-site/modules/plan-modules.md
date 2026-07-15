# Plan

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。依這套文件與目前程式物件的定義，Plan 主要會把流程導向 `Retrieve` 或 `Action`。這個家族目前聚焦在 `ReActPlan`：舊文件中的 Chain-of-Thought 與 Plan-and-Solve 不是獨立 class，而是同一個 planner 內部可切換的 prompt strategy。

## ReActPlan

`ReActPlan` 是目前唯一的規劃節點實作，基礎策略對應 [Arxiv](https://arxiv.org/abs/2210.03629)；同一份 class 也內建了 Chain-of-Thought 風格提示 [Arxiv](https://arxiv.org/abs/2201.11903) 與 Plan-and-Solve 風格提示 [Arxiv](https://arxiv.org/abs/2305.04091) 的模板變體，但對外仍是一個 `ReActPlan` 模組。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | planner 使用的 LLM client。 |
| `system_prompt` | `str | None` | `None` | 若提供，直接覆蓋內建 planner prompt。 |
| `retrieve_description` | `str | None` | `None` | 未顯式提供 `system_prompt` 時，用來組出 retrieve index 描述。 |
| `retrieve_name` | `str | None` | `None` | 未顯式提供 `system_prompt` 時，用來組出 retrieve index 名稱。 |