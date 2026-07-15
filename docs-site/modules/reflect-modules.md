# Reflect

Reflect 模組負責檢查 Action 產出的候選答案，判斷答案是否可直接交付，或是否應退回前面的節點修正。依這套文件與目前程式物件的定義，Reflect 在失敗時主要會把流程導回 `Plan`，或直接結束本次執行。這一頁先列出可直接使用的 `RuleBasedReflect` 與 `ReflexionReflect`，再補上 `EvidenceCheckReflect` 這種常見的驗收型反思物件型態，方便你定義自訂模組。

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

## EvidenceCheckReflect

`EvidenceCheckReflect` 會檢查輸出是否有回應問題、是否引用足夠證據，以及是否符合預期格式，適合三個 use case 都需要的最小驗收節點。方法方向可參考 Reflexion [Arxiv](https://arxiv.org/abs/2303.11366) 與 Self-RAG [Arxiv](https://arxiv.org/abs/2310.11511)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `client` | `Any` | `None` | 反思用 LLM client。 |
| `checklist` | `list[str] | None` | `None` | 驗收規則清單，例如是否漏答、是否缺證據、格式是否正確。 |
| `on_failure` | `str` | `"retry_plan"` | 檢查失敗時的後續策略。 |