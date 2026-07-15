# Reflect

Reflect 模組負責檢查 Action 產出的候選答案，判斷答案是否可直接交付，或是否應退回前面的節點修正。依這套文件的流程定義，Reflect 可能將流程導向 `Retrieve` 或 `Action`。現行程式碼中已實作 `RuleBasedReflect` 與 `ReflexionReflect`。

## RuleBasedReflect

`RuleBasedReflect` 是最小反思基線，只會檢查 `state.last_action_error` 是否存在；若 Action 失敗，則依策略決定後續要回到檢索或重新執行回答。這屬於 deterministic fallback rule，沒有直接對應單一研究論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `on_failure` | `str` | `"retry_plan"` | 失敗時的後續策略；目前文件定義將其理解為導向新一輪檢索或重新回答的控制點。 |

## ReflexionReflect

`ReflexionReflect` 會把 `user_message`、`action_result` 與 `action_error` 交給 LLM 判斷，要求模型輸出 `pass/fail`、失敗原因與改進建議；其設計思路對應 Reflexion 論文 [Arxiv](https://arxiv.org/abs/2303.11366)。在這套文件定義中，反思結果可作為後續重取資料或重新回答的依據。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `on_failure` | `str` | `"retry_plan"` | 失敗時的後續策略；目前文件定義將其理解為導向新一輪檢索或重新回答的控制點。 |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | 反思使用的 LLM client。 |