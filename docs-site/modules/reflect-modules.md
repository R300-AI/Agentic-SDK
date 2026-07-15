# Reflect Modules

Reflect 模組負責檢查 Action 產出的候選答案，判斷答案是否可直接交付，或是否應退回前面的節點修正。現行程式碼中已實作 `RuleBasedReflect` 與 `ReflexionReflect`。

## 已實作模組

| 模組 | 需要模型 | 可能下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `RuleBasedReflect` | 否 | `plan` / `END` | 只根據 Action 是否報錯做最低成本判斷 |
| `ReflexionReflect` | 是 | `plan` / `END` | 用 LLM 對 Action 結果做反思式評估 |

## RuleBasedReflect

`RuleBasedReflect` 是最小反思基線，只會檢查 `state.last_action_error` 是否存在；若 Action 失敗，則依策略退回 `plan` 或直接結束。這屬於 deterministic fallback rule，沒有直接對應單一研究論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `on_failure` | `str` | `"retry_plan"` | 只接受 `retry_plan` 或 `end`；分別代表失敗時回到 `plan` 或直接結束。 |

## ReflexionReflect

`ReflexionReflect` 會把 `user_message`、`action_result` 與 `action_error` 交給 LLM 判斷，要求模型輸出 `pass/fail`、失敗原因與改進建議；其設計思路對應 Reflexion 論文 [Arxiv](https://arxiv.org/abs/2303.11366)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `on_failure` | `str` | `"retry_plan"` | 只接受 `retry_plan` 或 `end`；分別代表失敗時回到 `plan` 或直接結束。 |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | 反思使用的 LLM client。 |