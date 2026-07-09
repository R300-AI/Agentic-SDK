# Reflect Modules

Reflect 模組負責檢查 action 產出的候選答案，判斷是否已可交付，或是否應回饋新的修正方向給 workflow 下一輪使用。

## MVP 模組

| 模組 | 需要模型 | 讀取 | 寫入 |
| --- | --- | --- | --- |
| Reflexion Reflect | 是 | `draft_answer`、`retrieved_items`、`plan` | `reflection` 或 `final_answer` |

## Reflexion Reflect

!!! info "模型規格"
    Reflect 家族在這一版 MVP 只公開一個正式模組，且統一以 `OpenAI SDK form` 表達模型接入方式。

**對應論文：** [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client。 |
| `model` | 是 | 反思與評估用模型名稱。 |
| `system_prompt` | 否 | 定義評估標準、回饋格式與何時可直接放行答案。 |
| `max_retries` | 否 | 限制 workflow 因反思而重試的次數。 |

當反思判定答案已足夠時，可直接提升為 `final_answer`；若仍需修正，則應寫出 `reflection` 供下一輪 planner 或 action 使用。

Reflect 並不是所有 workflow 都必備，但只要你需要重試、品質檢查或自我修正，它就會變成關鍵節點。