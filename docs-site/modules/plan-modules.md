# Plan Modules

Plan 模組負責把感知結果轉成可執行路徑。它們的差別不在於是否會「想」，而在於用什麼 reasoning strategy 來拆問題、安排查詢與決定後續步驟。

## MVP 模組

| 模組 | 主要用途 | 輸入 | 輸出 |
| --- | --- | --- | --- |
| Chain-of-Thought Planner | 建立單一路徑 reasoning baseline | `perceived_input` | `plan` |
| ReAct Planner | 在 reasoning 與後續 action 之間交替安排步驟 | `perceived_input`、`reflection` | `plan`、`query` |
| Plan-and-Solve Planner | 先拆步驟，再生成後續執行路徑 | `perceived_input` | `plan` |

## Chain-of-Thought Planner

**對應論文：** [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client。 |
| `model` | 是 | 規劃用模型名稱。 |
| `system_prompt` | 否 | 定義推理邊界與計畫輸出格式。 |

## ReAct Planner

適合需要邊思考邊決定後續查詢或步驟的情境。公開文件只保證它遵守 OpenAI SDK form 與 workflow 引擎分層，不把內部 prompt 寫法暴露成對外契約。

**對應論文：** [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client。 |
| `model` | 是 | 規劃用模型名稱。 |
| `max_iterations` | 否 | 限制規劃可展開的步數。 |

## Plan-and-Solve Planner

適合先把問題拆成清楚步驟，再交給後續 retrieve 或 action 執行的情境。

**對應論文：** [Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models](https://arxiv.org/abs/2305.04091)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client。 |
| `model` | 是 | 規劃用模型名稱。 |
| `system_prompt` | 否 | 定義先拆步驟、後產出計畫的格式要求。 |

如果你目前只需要 README 級別的簡單流程，可以暫時不接 planner；一旦需要可變路徑，再從這三個模組中挑選策略。