# Reflect Modules

Reflect 模組負責檢查 Action 產出的候選答案，判斷答案是否可直接交付，或是否應退回前面的節點修正。現行程式碼中已實作 `RuleBasedReflect` 與 `ReflexionReflect`。

## 已實作模組

| 模組 | 需要模型 | 可能下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `RuleBasedReflect` | 否 | `plan` / `END` | 只根據 Action 是否報錯做最低成本判斷 |
| `ReflexionReflect` | 是 | `plan` / `END` | 用 LLM 對 Action 結果做反思式評估 |

## RuleBasedReflect

`RuleBasedReflect` 是最小反思基線，只會檢查 `state.last_action_error` 是否存在；若 Action 失敗，則依策略退回 `plan` 或直接結束。這屬於 deterministic fallback rule，沒有直接對應單一研究論文。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `on_failure` | `str` | `"retry_plan"` | 只接受 `retry_plan` 或 `end`；分別代表失敗時回到 `plan` 或直接結束。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `last_action_error` | `dict | None` | `None` | 若為 `None` 視為 `pass`；若存在則視為 `fail`。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"plan" | None` | 失敗時依 `on_failure` 轉成 `plan` 或 `END`；成功時為 `None`。 |
| `NodeOutput.payload.reflect_verdict` | `"pass" | "fail"` | 規則式反思結論。 |
| `NodeOutput.context_updates[0].type` | `"reflection"` | 追加一筆 `REFLECTION` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `verdict`、`reason`、`strategy="rule_based"`、`on_failure`。 |

## ReflexionReflect

`ReflexionReflect` 會把 `user_message`、`action_result` 與 `action_error` 交給 LLM 判斷，要求模型輸出 `pass/fail`、失敗原因與改進建議；其設計思路對應 Reflexion 論文 [Arxiv](https://arxiv.org/abs/2303.11366)。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `on_failure` | `str` | `"retry_plan"` | 只接受 `retry_plan` 或 `end`；分別代表失敗時回到 `plan` 或直接結束。 |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | 反思使用的 LLM client。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | 使用者原始問題。 |
| `action_result` | `str` | `""` | 來自 `state.last_action_result["content"]`；若 Action 尚未成功，則可能為空字串。 |
| `action_error` | `str` | `"none"` | 來自 `state.last_action_error["message"]`；若 Action 成功則為字串 `none`。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"plan" | None` | 反思失敗時依 `on_failure` 回到 `plan` 或直接結束；通過時為 `None`。 |
| `NodeOutput.payload.reflect_verdict` | `"pass" | "fail"` | LLM 或 fallback 規則給出的最終 verdict。 |
| `NodeOutput.payload._llm_usage` | `dict | None` | LLM 可用時包含 `model`、`input_tokens`、`output_tokens`。 |
| `NodeOutput.context_updates[0].type` | `"reflection"` | 追加一筆 `REFLECTION` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `verdict`、`reason`、`strategy="reflexion"`、`on_failure`；若有建議會額外包含 `suggestion`。 |