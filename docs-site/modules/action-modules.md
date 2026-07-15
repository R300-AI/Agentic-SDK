# Action Modules

Action 模組負責把前面節點收集到的資訊轉成 workflow 的最終輸出。現行程式碼中可直接使用的 Action 節點只有兩個：`DirectAnswerAction` 與 `CompletionAction`。

## 已實作模組

| 模組 | 需要模型 | 下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `DirectAnswerAction` | 否 | `END` | 直接把最近一次檢索結果整理成答案 |
| `CompletionAction` | 是 | `END` | 透過 OpenAI-compatible client 或 Foundry 生成最終回答 |

## DirectAnswerAction

`DirectAnswerAction` 是 README 第一個快速開始範例使用的最小輸出模組。它不依賴生成模型，只會讀取 `latest_retrieved_content`，然後把該內容原樣提升為最終答案；這屬於 deterministic answer composition 的工程型基線，沒有對應單一研究論文。

### 輸入參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `latest_retrieved_content` | `str | None` | `"沒有命中任何條目。"` | 由 `state.lookup("latest_retrieved_content")` 讀取的最近一次檢索主內容；若不存在則退回固定訊息。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `None` | Action 執行完後直接結束 workflow。 |
| `NodeOutput.payload.latest_final_message` | `str` | 最終答案文字。 |
| `NodeOutput.context_updates[0].type` | `"action_result"` | 追加一筆 `ACTION_RESULT` context entry。 |
| `NodeOutput.context_updates[0].content` | `str` | 與最終答案相同的內容。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 固定包含 `ok=True` 與 `model="direct-answer"`。 |
| `state.last_action_result` | `dict` | 會被寫成 `{"content": <答案>, "model": "direct-answer"}`，供 engine 產生 `final_message`。 |

## CompletionAction

`CompletionAction` 會把使用者問題與最近一次檢索上下文組成 chat completion 請求，交給 OpenAI-compatible client、AMD upstream，或 Azure Foundry deployment 生成自然語言答案。它屬於 generative completion 類型的節點，論文背景可參考 GPT 類 few-shot/completion 範式的代表作 [Arxiv](https://arxiv.org/abs/2005.14165)。

### 輸入參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `str` | 無 | `WorkflowState.user_message`；模型回答的主要問題來源。 |
| `retrieved_context` | `str | None` | `None` | 最近一筆 `RETRIEVED` context 的 `content`；若存在，會被拼進 prompt 作為回答依據。 |
| `attachments` | `list[Attachment]` | `[]` | 若 workflow 帶有圖片附件，會在支援的路徑中一併送給模型。 |
| `model` | `str` | `"default"` | upstream 路徑下，若沒有顯式指定模型，會退回 `state.payload["model"]`，再退回字串 `"default"`。 |

### 輸出格式

| 欄位 | 型態 | 說明 |
| --- | --- | --- |
| `NodeOutput.next_node` | `None` | Action 執行完後直接結束 workflow。 |
| `NodeOutput.context_updates[0].type` | `"action_result"` | 追加一筆 `ACTION_RESULT` context entry。 |
| `NodeOutput.context_updates[0].content` | `str` | 模型生成的最終答案。 |
| `NodeOutput.context_updates[0].metadata` | `dict` | 成功時至少包含 `ok=True` 與實際 `model`；失敗時為 `ok=False` 並附帶 `error`。 |
| `NodeOutput.payload._llm_usage` | `dict | None` | 成功時包含 `model`、`input_tokens`、`output_tokens`；失敗時為 `None`。 |
| `state.last_action_result` | `dict | None` | 成功時寫入 `{"content": <答案>, "model": <模型名>}`。 |
| `state.last_action_error` | `dict | None` | 失敗時寫入 `{"type": <例外型別>, "message": <錯誤訊息>}`。 |