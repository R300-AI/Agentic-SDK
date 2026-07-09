# Action Modules

Action 模組負責把前面節點收集到的資訊，轉成流程要交付給呼叫端的答案。MVP 先保留一個最小直接輸出模組，再提供模型型 completion 模組。

## MVP 模組

| 模組 | 需要模型 | 讀取 | 寫入 |
| --- | --- | --- | --- |
| DirectAnswerAction | 否 | `perceived_input`、`retrieved_items` | `final_answer` |
| CompletionAction | 是 | `perceived_input`、`retrieved_items`、`plan` | `draft_answer` 或 `final_answer` |

## DirectAnswerAction

這是 README 最小輸出模組，適合把已命中的知識條目整理成直接答案，不需要再經過模型生成。

**對應論文：** 無單一對應論文；此模組屬 deterministic answer composition，重點在工程上的可預測輸出，而不是特定論文方法。

### 建構參數

無必填模型參數。只要求能根據既有輸入組裝最終回答。

### 輸入契約

至少能讀取 `perceived_input` 與 `retrieved_items`。

### 輸出契約

至少寫入 `final_answer`。

## CompletionAction

!!! info "模型規格"
    CompletionAction 是 README 中第二個快速開始例子的核心，對外只描述為 `OpenAI SDK form` 的 completion client 接入。

**對應論文：** [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client。 |
| `model` | 是 | 回答生成用模型名稱。 |
| `system_prompt` | 否 | 定義回答格式、口吻與引用邊界。 |
| `response_schema` | 否 | 限制輸出結構，方便下游再利用。 |

若答案能直接由既有資料組裝，選 DirectAnswerAction；若要把知識與上下文重新生成自然語言輸出，選 CompletionAction。