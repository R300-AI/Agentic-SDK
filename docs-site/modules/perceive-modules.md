# Perceive Modules

Perceive 模組負責把原始輸入整理成 workflow 後續節點可直接消費的理解結果。現行程式碼中已實作 `InputPerceive`、`RuleBasedPerceive` 與 `LLMBasedPerceive` 三種路徑，從最小轉接到模型型理解皆有覆蓋。

## 已實作模組

| 模組 | 需要模型 | 下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `InputPerceive` | 否 | `retrieve` | README 最小入口，直接轉交原始輸入 |
| `RuleBasedPerceive` | 否 | `plan` | 以規則判斷基本 intent |
| `LLMBasedPerceive` | 是 | `plan` | 用 LLM 產生 intent 與語意摘要 |

## InputPerceive

`InputPerceive` 是 README 第一與第三個快速開始範例使用的最小感知模組。它不做語意推理，只會將 `user_message` 直接整理成 `perceived_input` 與 `query` 供後續檢索使用；這是 SDK 的工程型入口，沒有對應單一研究論文。

### 配置參數

此節點沒有 `__init__` 配置參數。

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | `WorkflowState.user_message`；會先做 `strip()` 再寫入 payload。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"retrieve"` | Perceive 結束後直接進入檢索節點。 |
| `NodeOutput.payload.perceived_input` | `str` | 去除前後空白後的使用者輸入。 |
| `NodeOutput.payload.query` | `str` | 與 `perceived_input` 相同，供 retrieve 模組直接使用。 |
| `NodeOutput.context_updates[0].type` | `"perceived"` | 追加一筆 `PERCEIVED` context entry。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 固定包含 `source="input_perceive"`。 |

## RuleBasedPerceive

`RuleBasedPerceive` 以輕量規則將輸入分成 `question`、`diagnose` 或 `general` 等 intent，適合不依賴外部模型的基線流程。它屬於 heuristic intent classification，沒有直接對應單一論文。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `welcome_message` | `str` | `""` | 若提供，會寫入 `PERCEIVED` metadata，供 UI 顯示初始提示。 |
| `options` | `list[dict] | None` | `None` | 可選選項列表；若 user input 剛好命中 `label` 或 `value`，會優先採用該 option 的 `intent` 或 `value`。 |
| `importance` | `float` | `1.0` | 若 workflow 有接 `memory_store`，此值會寫入 `MemoryEntry.importance`。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | 主要輸入，會先做 `strip()`，再用正則規則判斷 intent。 |
| `available_options` | `list[dict]` | `[]` | 若模組有配置 `options`，且使用者輸入剛好等於某個 `label` 或 `value`，會優先使用該 option 的 `intent` 或 `value`。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"plan"` | 感知完成後交給規劃節點。 |
| `NodeOutput.payload.perceived_intent` | `str` | 規則判斷出的 intent。 |
| `NodeOutput.context_updates[0].type` | `"perceived"` | 追加一筆 `PERCEIVED` context entry。 |
| `NodeOutput.context_updates[0].content` | `str` | 形如 `intent=<intent> role=user msg_len=<n>`。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `intent`、`role`、`msg_len`；若有 welcome/options 也會帶入。 |

## LLMBasedPerceive

`LLMBasedPerceive` 會把使用者輸入與可選項目一起交給 LLM，要求模型只回 JSON，輸出 `intent` 與 `summary`。這屬於 LLM-based intent understanding，可參考 in-context/few-shot 類生成式理解方法的代表作 [Arxiv](https://arxiv.org/abs/2005.14165)。

### 配置參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `welcome_message` | `str` | `""` | 若提供，會寫入 `PERCEIVED` metadata，供 UI 顯示初始提示。 |
| `options` | `list[dict] | None` | `None` | 可選選項列表，會作為 `available_options` 背景資訊送給 LLM。 |
| `importance` | `float` | `1.0` | 若 workflow 有接 `memory_store`，此值會寫入 `MemoryEntry.importance`。 |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | 注入既有 Foundry client；未提供時會自建。 |

### 執行時輸入

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | 主要輸入，會被包進 `user_prompt` 送往 LLM。 |
| `available_options` | `list[dict]` | `[]` | 若模組有配置 `options`，會以 JSON 陣列形式提供給 LLM 作為背景參考，但不直接覆蓋語意判斷。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `"plan"` | 感知完成後交給規劃節點。 |
| `NodeOutput.payload.perceived_intent` | `str` | LLM JSON 中的 `intent` 欄位。 |
| `NodeOutput.context_updates[0].type` | `"perceived"` | 追加一筆 `PERCEIVED` context entry。 |
| `NodeOutput.context_updates[0].content` | `str` | 形如 `intent=<intent> summary=<summary>`。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 至少包含 `intent`、`intent_summary`、`role`、`msg_len`；若有 welcome/options 也會帶入。 |